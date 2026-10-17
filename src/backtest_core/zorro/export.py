"""Write bar-store series as Zorro history: ``.t6`` files, a lite-C factor table, and an asset-list row.

``.t6`` record (32 bytes, little-endian): double OLE date (days since 1899-12-30, UTC, the bar's CLOSE),
float high, low, open, close, val, vol — newest record first, one file per UTC year. ``val`` carries the
adjustment factor (adjusted / raw), ``vol`` the volume.

``prices="adjusted"`` is the futures convention (P&L on the continuous series; ``to_t6.py`` wrote exactly this).
``prices="raw"`` writes as-traded prices, the convention of the QQQ noise-area port.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import polars as pl

from .. import bars
from . import paths

T6 = np.dtype([("t", "<f8"), ("h", "<f4"), ("l", "<f4"), ("o", "<f4"), ("c", "<f4"), ("v", "<f4"), ("vol", "<f4")])
OLE0 = np.datetime64("1899-12-30T00:00:00", "ns")


def _with_close_utc(b: pl.DataFrame, bar_minutes: int) -> pl.DataFrame:
    return b.with_columns(
        close_utc=(pl.col("start") + pl.duration(minutes=bar_minutes)).dt.replace_time_zone("America/New_York")
        .dt.convert_time_zone("UTC").dt.replace_time_zone(None))


def _raw(b: pl.DataFrame, tick: float | None) -> pl.DataFrame:
    b = b.with_columns([(pl.col(k) / pl.col("factor")) for k in ("open", "high", "low", "close")])
    return b.with_columns([(pl.col(k) / tick).round(0) * tick for k in ("open", "high", "low", "close")]) if tick else b


def t6(symbol: str, source: str = "databento", freq: str = "1m", prices: str = "adjusted",
       out_dir: Path | str | None = None, only_year: int | None = None, name: str | None = None,
       tick: float | None = None) -> dict[int, int]:
    """Write ``<out_dir>/<NAME>_<YYYY>.t6`` (``name`` defaults to the symbol). Returns ``{year: records}``.

    ``tick``: snap raw prices to the tick (adjusted / factor is not exact in floating point)."""
    if prices not in ("adjusted", "raw"):
        raise ValueError(f"prices must be 'adjusted' or 'raw', not {prices!r}")
    out = Path(out_dir) if out_dir else paths.history_dir()
    minutes = {"1m": 1, "1h": 60}[freq]
    b = _with_close_utc(bars.intraday(symbol, source, freq), minutes)
    if prices == "raw":
        b = _raw(b, tick)
    written: dict[int, int] = {}
    for (yr,), g in b.group_by(pl.col("close_utc").dt.year(), maintain_order=True):
        if only_year and yr != only_year:
            continue
        g = g.reverse()
        a = np.empty(len(g), T6)
        a["t"] = (g["close_utc"].to_numpy().astype("datetime64[ns]") - OLE0) / np.timedelta64(1, "D")
        for f, c in (("h", "high"), ("l", "low"), ("o", "open"), ("c", "close"), ("v", "factor"), ("vol", "volume")):
            a[f] = g[c].to_numpy()
        a.tofile(out / f"{(name or symbol).upper()}_{yr}.t6")
        written[yr] = len(a)
    return written


def t6_daily(symbol: str, daily: pl.DataFrame, out_dir: Path | str | None = None,
             stamp_minute_utc: int = 20 * 60 + 30) -> dict[int, int]:
    """Write one ``.t6`` record per session from a daily price frame (the Hermes ``PriceStore`` columns
    ``date, open, high, low, close, adjusted_close, volume``). Returns ``{year: records}``.

    Prices are adjusted (``x adjusted_close / close``) and ``val`` holds that factor. Every record is stamped
    ``stamp_minute_utc`` minutes after UTC midnight of its session: a fixed time inside the daily bar that ends
    21:00 UTC (``BarPeriod = 1440; BarOffset = 21*60``), not the real close, so a stamp never sits on a bar edge
    and does not move with daylight saving.
    """
    out = Path(out_dir) if out_dir else paths.history_dir()
    d = daily.sort("date").with_columns(factor=pl.col("adjusted_close") / pl.col("close"))
    if d.is_empty() or d["date"].n_unique() != d.height:
        raise ValueError(f"{symbol}: the daily frame is empty or has duplicate dates")
    if d.select(pl.any_horizontal(pl.col("open", "high", "low", "close", "adjusted_close").is_null()
                                  | (pl.col("open", "high", "low", "close", "adjusted_close") <= 0)).any()).item():
        raise ValueError(f"{symbol}: null or non-positive prices")
    written: dict[int, int] = {}
    for (yr,), g in d.group_by(pl.col("date").dt.year(), maintain_order=True):
        g = g.reverse()
        a = np.empty(len(g), T6)
        day = (g["date"].to_numpy().astype("datetime64[D]").astype("datetime64[ns]") - OLE0) / np.timedelta64(1, "D")
        a["t"] = day + stamp_minute_utc / 1440.0
        f = g["factor"].to_numpy()
        for field, col in (("h", "high"), ("l", "low"), ("o", "open"), ("c", "close")):
            a[field] = g[col].to_numpy() * f
        a["v"] = f
        a["vol"] = g["volume"].to_numpy()
        a.tofile(out / f"{symbol.upper()}_{yr}.t6")
        written[yr] = len(a)
    return written


def roll_after(symbol: str, source: str, freq: str, last_close_utc):
    """The time (UTC, naive) of a stored roll at or after the last bar's close, or None. On a roll weekend the series already stands
    on the new contract's prices while its last bars are the old contract's, so they carry that roll's ratio; live
    bars, from the new contract, carry 1 from the roll on."""
    try:
        rolls = bars._store(None).read_rolls(symbol, source, freq)
    except LookupError:
        return None
    at = rolls["roll_at"].dt.convert_time_zone("UTC").dt.replace_time_zone(None)
    later = at.filter(at >= last_close_utc)                 # the old contract's last bar closes at the roll itself
    return later[-1] if later.len() else None


def factor_block(symbol: str, source: str = "databento", freq: str = "1m") -> str:
    """lite-C roll / dividend table: ``<SYM>_NF``, ``<SYM>_FT`` (bar-close minute, UTC, since 1899-12-30, where
    the factor changes) and ``<SYM>_FV`` (the factor from then on). Minutes as ``int``, because a decimal DATE
    literal loses minutes of precision in lite-C."""
    minutes = {"1m": 1, "1h": 60}[freq]
    b = _with_close_utc(bars.intraday(symbol, source, freq, ["start", "factor"]), minutes)
    ch = b.filter(pl.col("factor") != pl.col("factor").shift(1).fill_null(-1.0)).select("close_utc", "factor")
    edge = roll_after(symbol, source, freq, b["close_utc"].max())
    if edge is not None:
        ch = pl.concat([ch, pl.DataFrame({"close_utc": [edge + timedelta(minutes=1)], "factor": [1.0]}, schema=ch.schema)])
    ft = ((ch["close_utc"].to_numpy().astype("datetime64[ns]") - OLE0) // np.timedelta64(1, "m")).astype(np.int64)
    fv = ch["factor"].to_list()
    n = len(ft)
    sym = symbol.upper()

    def rows(xs, w):
        return ",\n".join("\t" + ", ".join(xs[i:i + w]) for i in range(0, len(xs), w))

    return (f"#define {sym}_NF {n}\nint {sym}_FT[{n}] = {{\n{rows([str(x) for x in ft], 6)} }};\n"
            f"var {sym}_FV[{n}] = {{\n{rows([repr(x) if x != 1 else '1' for x in fv], 6)} }};\n")


NA_BARS = 390                 # the QQQ noise-area sessions: 09:30-16:00 New York, one bar a minute
NA_ASSETS = ("Name,Price,Spread,RollLong,RollShort,PIP,PIPCost,MarginCost,Market,Multiplier,Commission,Symbol\n"
             "QQQ,600,0,0,0,0.01,0.01,-25,0,1,0.017,QQQ\n"
             "QQQVW,600,0,0,0,0.01,0.01,-25,0,1,0,QQQVW\n")


def noise_area_sessions(b: pl.DataFrame) -> list:
    """The sessions the QQQ noise-area rule trades: a bar at 09:30, one at or after 15:55, every half hour present,
    one adjustment factor, and not an NYSE half-day (EODHD files carry after-hours bars on half-days from 2023, so
    the bar rule alone lets them through). ``b``: the bar store's 1-minute QQQ frame."""
    from ingest_core.calendar import get_early_close_sessions_set  # lazy: only this export needs an exchange calendar

    m = pl.col("start").dt.hour().cast(pl.Int32) * 60 + pl.col("start").dt.minute().cast(pl.Int32) - 570
    d = b.with_columns(m=m).filter((pl.col("m") >= 0) & (pl.col("m") < NA_BARS))
    g = d.group_by("session").agg(first_m=pl.col("m").min(), last_m=pl.col("m").max(),
                                  periods=(pl.col("m") // 30).n_unique(), nf=pl.col("factor").n_unique())
    used = (g.filter((pl.col("first_m") == 0) & (pl.col("last_m") >= 385) & (pl.col("periods") == 13)
                     & (pl.col("nf") == 1))["session"].sort().to_list())
    early = get_early_close_sessions_set(min(used), max(used))
    return [s for s in used if s not in early]


def noise_area_frame(b: pl.DataFrame, sessions: list) -> pl.DataFrame:
    """One row per session and minute 0..389 on raw prices, missing minutes filled (close carried forward, open =
    previous close, volume 0), the session VWAP of the raw typical price, and ``close_utc`` (the bar's close)."""
    df = b.with_columns(m=pl.col("start").dt.hour().cast(pl.Int32) * 60 + pl.col("start").dt.minute().cast(pl.Int32) - 570)
    df = df.filter(pl.col("session").is_in(sessions) & (pl.col("m") >= 0) & (pl.col("m") < NA_BARS))
    raw = df.select("session", "m", "volume", "factor",
                    o=(pl.col("open") / pl.col("factor")).round(4), h=(pl.col("high") / pl.col("factor")).round(4),
                    l=(pl.col("low") / pl.col("factor")).round(4), c=(pl.col("close") / pl.col("factor")).round(4))
    grid = pl.DataFrame({"session": sessions}).join(pl.DataFrame({"m": list(range(NA_BARS))}, schema={"m": pl.Int32}),
                                                    how="cross")
    g = grid.join(raw, on=["session", "m"], how="left").sort("session", "m")
    g = g.with_columns(pl.col("c", "factor").forward_fill().over("session"))
    g = g.with_columns(o=pl.coalesce("o", pl.col("c").shift(1).over("session")), volume=pl.col("volume").fill_null(0.0))
    g = g.with_columns(h=pl.coalesce("h", pl.max_horizontal("o", "c")), l=pl.coalesce("l", pl.min_horizontal("o", "c")))
    cum_pv = ((pl.col("h") + pl.col("l") + pl.col("c")) / 3 * pl.col("volume")).cum_sum().over("session")
    cum_v = pl.col("volume").cum_sum().over("session")
    g = g.with_columns(vwap=pl.when(cum_v > 0).then(cum_pv / cum_v).otherwise(pl.col("c")))
    close_et = pl.col("session").cast(pl.Datetime("us")) + pl.duration(minutes=570 + 1) + pl.duration(minutes=pl.col("m"))
    return g.with_columns(close_utc=close_et.dt.replace_time_zone("America/New_York").dt.convert_time_zone("UTC")
                          .dt.replace_time_zone(None))


def write_noise_area(g: pl.DataFrame, out_dir: Path | str | None = None, factors_path: Path | str | None = None) -> int:
    """NoiseAreaCore.h's input: ``QQQ_<YYYY>.t6`` (raw prices, the adjustment factor in ``val``, volume), ``QQQVW_<YYYY>.t6``
    (the session VWAP as a price: Zorro cannot read volume), ``AssetsNoiseArea.csv`` in ``out_dir`` (default: Zorro's
    History), and ``NAFactors.h`` at ``factors_path`` (default: Zorro's Strategy). Returns the number of bars."""
    out = Path(out_dir) if out_dir else paths.history_dir()
    for f in [*out.glob("QQQ_*.t6"), *out.glob("QQQVW_*.t6")]:
        f.unlink()
    days = (g["close_utc"].to_numpy().astype("datetime64[ns]") - OLE0) / np.timedelta64(1, "D")
    rec, vw = np.empty(g.height, T6), np.empty(g.height, T6)
    rec["t"] = vw["t"] = days
    for f, c in (("h", "h"), ("l", "l"), ("o", "o"), ("c", "c"), ("v", "factor"), ("vol", "volume")):
        rec[f] = g[c].to_numpy()
    for f in ("h", "l", "o", "c"):
        vw[f] = g["vwap"].to_numpy()
    vw["v"] = vw["vol"] = 0
    years = g["session"].dt.year().to_numpy()
    for y in np.unique(years):
        rec[years == y][::-1].tofile(out / f"QQQ_{y}.t6")
        vw[years == y][::-1].tofile(out / f"QQQVW_{y}.t6")
    f = g["factor"].to_numpy()
    at = np.concatenate([[0], np.flatnonzero(np.diff(f) != 0) + 1])

    def rows(xs):
        return ",\n".join("\t" + ", ".join(xs[i:i + 6]) for i in range(0, len(xs), 6))

    text = ("// NAFactors.h -- generated by backtest_core.zorro.export.write_noise_area; do not edit.\n"
            "// Dividend adjustment factor (adjusted / raw) QQQ_FV[j] applies from the bar closing at QQQ_FT[j]\n"
            "// (whole minutes since 1899-12-30, UTC) until the next entry.\n\n"
            f"#define QQQ_NF {len(at)}\n"
            f"int QQQ_FT[{len(at)}] = {{\n{rows([str(int(round(d * 1440))) for d in days[at]])} }};\n"
            f"var QQQ_FV[{len(at)}] = {{\n{rows([f'{v:.17g}' for v in f[at]])} }};\n")
    Path(factors_path or paths.strategy_dir() / "NAFactors.h").write_text(text, encoding="ascii")
    (out / "AssetsNoiseArea.csv").write_text(NA_ASSETS, encoding="ascii")
    return g.height


NQF_ASSETS = ("Name,Price,Spread,RollLong,RollShort,PIP,PIPCost,MarginCost,Market,Multiplier,Commission,Symbol\n"
              "NQF,25000,0,0,0,0.25,5,35000,0,1,0,NQF\n")


def write_noise_area_nq(out_dir: Path | str | None = None) -> dict[int, int]:
    """NoiseAreaNQ.c's input: ``NQF_<YYYY>.t6``, the front-month NQ on raw prices snapped to the tick (the roll factor
    in ``val``, read against ``ZZFactors.h``), and ``AssetsNoiseAreaNQ.csv``, in ``out_dir`` (default: Zorro's History).
    Returns ``{year: records}``."""
    out = Path(out_dir) if out_dir else paths.history_dir()
    n = t6("NQ", "databento", "1m", prices="raw", out_dir=out, name="NQF", tick=0.25)
    (out / "AssetsNoiseAreaNQ.csv").write_text(NQF_ASSETS, encoding="ascii")
    return n


def asset_row(symbol: str, price: float, commission: float = 0.0) -> str:
    """Asset-list row where 1 unit = 1 point = $1 (``PIP = PIPCost``); costs belong in the script's Commission."""
    return f"{symbol.upper()},{price:g},0,0,0,0.0001,0.0001,-100,0,1,{commission:g},{symbol.upper()}"
