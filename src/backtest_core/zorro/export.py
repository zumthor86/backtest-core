"""Write bar-store series as Zorro history: ``.t6`` files, a lite-C factor table, and an asset-list row.

``.t6`` record (28 bytes, little-endian): double OLE date (days since 1899-12-30, UTC, the bar's CLOSE),
float high, low, open, close, val, vol — newest record first, one file per UTC year. ``val`` carries the
adjustment factor (adjusted / raw), ``vol`` the volume.

``prices="adjusted"`` is the futures convention (P&L on the continuous series; ``to_t6.py`` wrote exactly this).
``prices="raw"`` writes as-traded prices, the convention of the QQQ noise-area port.
"""
from __future__ import annotations

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


def t6(symbol: str, source: str = "databento", freq: str = "1m", prices: str = "adjusted",
       out_dir: Path | str | None = None, only_year: int | None = None) -> dict[int, int]:
    """Write ``<out_dir>/<SYMBOL>_<YYYY>.t6``. Returns ``{year: records}``."""
    if prices not in ("adjusted", "raw"):
        raise ValueError(f"prices must be 'adjusted' or 'raw', not {prices!r}")
    out = Path(out_dir) if out_dir else paths.history_dir()
    minutes = {"1m": 1, "1h": 60}[freq]
    b = _with_close_utc(bars.intraday(symbol, source, freq), minutes)
    if prices == "raw":
        b = b.with_columns([(pl.col(k) / pl.col("factor")) for k in ("open", "high", "low", "close")])
    written: dict[int, int] = {}
    for (yr,), g in b.group_by(pl.col("close_utc").dt.year(), maintain_order=True):
        if only_year and yr != only_year:
            continue
        g = g.reverse()
        a = np.empty(len(g), T6)
        a["t"] = (g["close_utc"].to_numpy().astype("datetime64[ns]") - OLE0) / np.timedelta64(1, "D")
        for f, c in (("h", "high"), ("l", "low"), ("o", "open"), ("c", "close"), ("v", "factor"), ("vol", "volume")):
            a[f] = g[c].to_numpy()
        a.tofile(out / f"{symbol.upper()}_{yr}.t6")
        written[yr] = len(a)
    return written


def factor_block(symbol: str, source: str = "databento", freq: str = "1m") -> str:
    """lite-C roll / dividend table: ``<SYM>_NF``, ``<SYM>_FT`` (bar-close minute, UTC, since 1899-12-30, where
    the factor changes) and ``<SYM>_FV`` (the factor from then on). Minutes as ``int``, because a decimal DATE
    literal loses minutes of precision in lite-C."""
    minutes = {"1m": 1, "1h": 60}[freq]
    b = _with_close_utc(bars.intraday(symbol, source, freq, ["start", "factor"]), minutes)
    ch = b.filter(pl.col("factor") != pl.col("factor").shift(1).fill_null(-1.0))
    ft = ((ch["close_utc"].to_numpy().astype("datetime64[ns]") - OLE0) // np.timedelta64(1, "m")).astype(np.int64)
    fv = ch["factor"].to_list()
    n = len(ft)
    sym = symbol.upper()

    def rows(xs, w):
        return ",\n".join("\t" + ", ".join(xs[i:i + w]) for i in range(0, len(xs), w))

    return (f"#define {sym}_NF {n}\nint {sym}_FT[{n}] = {{\n{rows([str(x) for x in ft], 6)} }};\n"
            f"var {sym}_FV[{n}] = {{\n{rows([repr(x) if x != 1 else '1' for x in fv], 6)} }};\n")


def asset_row(symbol: str, price: float, commission: float = 0.0) -> str:
    """Asset-list row where 1 unit = 1 point = $1 (``PIP = PIPCost``); costs belong in the script's Commission."""
    return f"{symbol.upper()},{price:g},0,0,0,0.0001,0.0001,-100,0,1,{commission:g},{symbol.upper()}"
