"""The daily paper check, Zorro side: rerun each paper sleeve's own script over the bars it traded on.

    python -m backtest_core.zorro.paper setup                 # once: create the separate Zorro copy
    python -m backtest_core.zorro.paper replay --out <dir>    # each morning, from a desktop session

Both need ``ZORRO_DIR`` set to the replay copy (never the live folder: both commands refuse it) and ``BARS_DIR``.

The copy has its own History, Strategy, Data and Log, and no ``Accounts.csv``, so no ``-trade`` run can log in from
it. For each sleeve the replay runs the script with ``-d LIVETEST``: the live start-up (lookback, state files, live
exit timing) on the stored history, from the script's fixed start date to the end of the history. The trades that
come out are the ones the live code should have made. ``<out>/replay_<Script>.csv`` gets them on the raw
(as-traded) price scale; ``<out>/replay_status.json`` says what ran. Argus compares them with the live sleeves
(``argus.paper``).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from .. import bars
from . import live, paths, report, run

LIVE_ZORRO = Path(os.environ.get("ZORRO_LIVE_DIR", "C:/Users/Christopher/Zorro"))

#: script -> (history symbol, bar source, price scale of its history: futures are back-adjusted, QQQ is raw)
SLEEVES: dict[str, tuple[str, str, str]] = {
    "ZigZagGC": ("GC", "databento", "adjusted"),
    "ZigZagCL": ("CL", "databento", "adjusted"),
    "BreakGC": ("GC", "databento", "adjusted"),
    "BreakES": ("ES", "databento", "adjusted"),
    "DipBuyNQ": ("NQ", "databento", "adjusted"),
    "NoiseAreaNQ": ("NQ", "databento", "raw"),
}
#: a Zorro install's data folders; the copy takes everything else (the program, include, plugins, Zorro.ini)
DATA_DIRS = {"History", "Data", "Log", "Cache", "Strategy", "Job"}
BAR_DAYS = 14               # the reference bars exported for the live bar check: two weeks covers a missed morning run
COLUMNS = ["script", "asset", "side", "lots", "entry_utc", "exit_utc", "entry_raw", "exit_raw", "exit_type",
           "open_at_end", "history_end_utc"]


def _guard() -> None:
    if paths.ZORRO_DIR.resolve() == LIVE_ZORRO.resolve():
        raise SystemExit(f"ZORRO_DIR names the live Zorro folder ({LIVE_ZORRO}); the replay runs only in its own copy")


def setup() -> Path:
    """Copy Zorro's program files from the live folder into ``ZORRO_DIR``, with every asset list but no accounts."""
    _guard()
    dst = paths.ZORRO_DIR
    dst.mkdir(parents=True, exist_ok=True)
    for item in LIVE_ZORRO.iterdir():
        if item.name in DATA_DIRS or (item.is_file() and item.suffix.lower() == ".csv"):
            continue
        if item.is_dir():
            shutil.copytree(item, dst / item.name, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst / item.name)
    for d in DATA_DIRS:
        (dst / d).mkdir(exist_ok=True)
    for f in (LIVE_ZORRO / "History").glob("Assets*.csv"):
        shutil.copy2(f, dst / "History" / f.name)
    for f in (dst / "History").glob("Account*.csv"):
        f.unlink()
    return dst


def refresh_history() -> None:
    """The futures history (with the noise-area NQF history), roll table and state files (``live.refresh``), in the
    copy."""
    _guard()
    live.refresh(factors_in_zorro=True, low_priority=True)


def _close_utc(symbol: str, source: str) -> pl.DataFrame:
    """Each bar's close in UTC and its factor (adjusted / raw)."""
    b = bars.intraday(symbol, source, "1m", ["start", "factor"])
    return b.with_columns(
        close_utc=(pl.col("start") + pl.duration(minutes=1)).dt.replace_time_zone("America/New_York")
        .dt.convert_time_zone("UTC").dt.replace_time_zone(None)).select("close_utc", "factor").sort("close_utc")


def to_raw(trades: pl.DataFrame, bars_utc: pl.DataFrame) -> pl.DataFrame:
    """Entry and exit prices of an adjusted history on the raw scale: divided by the factor of the last bar that
    closed at or before the fill."""
    def at(col: str, out: str) -> pl.DataFrame:
        j = trades.select("i", col).sort(col).join_asof(bars_utc, left_on=col, right_on="close_utc", strategy="backward")
        return j.select("i", pl.col("factor").alias(out))
    t = trades.join(at("entry_utc", "f_in"), on="i").join(at("exit_utc", "f_out"), on="i")
    return t.with_columns(entry_raw=pl.col("entry_raw") / pl.col("f_in"),
                          exit_raw=pl.col("exit_raw") / pl.col("f_out")).drop("f_in", "f_out")


def _when(trd: pl.DataFrame, col: str) -> pl.Expr:
    """A trade-list time column as a datetime, whether ``report.trades_csv`` already parsed it or left it as text."""
    if trd.schema[col] == pl.Utf8:
        return pl.col(col).str.to_datetime(time_unit="us")
    return pl.col(col).cast(pl.Datetime("us"))


def trade_rows(script: str, trd: pl.DataFrame, history_end: datetime, scale: str,
               bars_utc: pl.DataFrame | None) -> pl.DataFrame:
    """Zorro's trade list (``_trd.csv``) as replay rows. A trade whose exit is the last bar of the history was still
    open when the history ended: Zorro closes it there, and its exit is not a real one."""
    t = trd.with_row_index("i").select(
        "i", pl.lit(script).alias("script"), pl.col("Asset").alias("asset"),
        pl.when(pl.col("Type").str.to_lowercase().str.starts_with("long")).then(1).otherwise(-1).alias("side"),
        pl.col("Lots").cast(pl.Int64).alias("lots"),
        _when(trd, "Open").alias("entry_utc"), _when(trd, "Close").alias("exit_utc"),
        pl.col("Entry").cast(pl.Float64).alias("entry_raw"), pl.col("Exit").cast(pl.Float64).alias("exit_raw"),
        pl.col("ExitType").cast(pl.Utf8).alias("exit_type"))
    if scale == "adjusted":
        t = to_raw(t, bars_utc)
    end = history_end.replace(second=0, microsecond=0)
    t = t.with_columns(open_at_end=pl.col("exit_utc") >= pl.lit(end - timedelta(minutes=2)),
                       history_end_utc=pl.lit(end))
    t = t.with_columns(exit_utc=pl.when(pl.col("open_at_end")).then(None).otherwise(pl.col("exit_utc")),
                       exit_raw=pl.when(pl.col("open_at_end")).then(None).otherwise(pl.col("exit_raw")))
    return t.sort("entry_utc").select(COLUMNS)


def replay_one(script: str, end: date) -> pl.DataFrame:
    symbol, source, scale = SLEEVES[script]
    trd = paths.log_dir() / f"{script}_trd.csv"
    trd.unlink(missing_ok=True)
    run.run(script, 0, int(end.strftime("%Y%m%d")), defines=["LIVETEST"], timeout=2400, low_priority=True)
    bars_utc = _close_utc(symbol, source)
    history_end = bars_utc["close_utc"].max()
    trades = report.trades_csv(trd) if trd.exists() else pl.DataFrame()
    if trades.is_empty():
        return pl.DataFrame(schema={"script": pl.Utf8, "asset": pl.Utf8, "side": pl.Int64, "lots": pl.Int64,
                                    "entry_utc": pl.Datetime, "exit_utc": pl.Datetime, "entry_raw": pl.Float64,
                                    "exit_raw": pl.Float64, "exit_type": pl.Utf8, "open_at_end": pl.Boolean,
                                    "history_end_utc": pl.Datetime})
    return trade_rows(script, trades, history_end, scale, bars_utc if scale == "adjusted" else None)


def reference_bars(symbol: str, days: int = BAR_DAYS) -> pl.DataFrame:
    """The last ``days`` of stored 1-minute bars on the raw (as-traded) scale, stamped with their close in UTC: the time
    Zorro stamps its own live bar with. ``despiked`` marks a bar whose prices the store clipped (``despike``)."""
    b = bars.intraday(symbol, "databento", "1m", ["start", "open", "high", "low", "close", "factor", "despiked"])
    b = b.filter(pl.col("start") >= pl.col("start").max() - pl.duration(days=days))
    return b.select(
        (pl.col("start") + pl.duration(minutes=1)).dt.replace_time_zone("America/New_York")
        .dt.convert_time_zone("UTC").dt.replace_time_zone(None).alias("close_utc"),
        *((pl.col(c) / pl.col("factor")).round(6) for c in ("open", "high", "low", "close")), "despiked").sort("close_utc")


def export_bars(out: Path, scripts: list[str]) -> dict[str, int]:
    """``<out>/bars_<SYMBOL>.csv`` for each futures symbol the sleeves trade; argus compares them with the bars the live
    sleeves built from the broker's feed (``Log/Bars_<Script>.csv``)."""
    done = {}
    for symbol in sorted({SLEEVES[s][0] for s in scripts}):
        b = reference_bars(symbol)
        b.write_csv(out / f"bars_{symbol}.csv")
        done[symbol] = b.height
    return done


def replay(out: Path, scripts: list[str], end: date) -> int:
    _guard()
    out.mkdir(parents=True, exist_ok=True)
    status = {"started": datetime.now().isoformat(timespec="seconds"), "zorro_dir": str(paths.ZORRO_DIR), "sleeves": {}}
    try:
        refresh_history()
    except Exception as exc:  # noqa: BLE001 - every failure is reported in the status file, then the run fails
        status["history_error"] = f"{type(exc).__name__}: {exc}"
        (out / "replay_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        print(f"history refresh failed: {status['history_error']}", flush=True)
        return 1
    failed = 0
    try:
        status["bars"] = export_bars(out, scripts)
    except Exception as exc:  # noqa: BLE001 - reported, and the replay still runs
        failed += 1
        status["bars_error"] = f"{type(exc).__name__}: {exc}"
        print(f"reference bars FAILED {status['bars_error']}", flush=True)
    for s in scripts:
        try:
            rows = replay_one(s, end)
            rows.write_csv(out / f"replay_{s}.csv")
            status["sleeves"][s] = {"ok": True, "trades": rows.height,
                                    "history_end_utc": str(rows["history_end_utc"].max()) if rows.height else None}
            print(f"{s}: {rows.height} trades", flush=True)
        except Exception as exc:  # noqa: BLE001 - one sleeve's failure must not hide the others' results
            failed += 1
            status["sleeves"][s] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            print(f"{s}: FAILED {status['sleeves'][s]['error']}", flush=True)
    status["ended"] = datetime.now().isoformat(timespec="seconds")
    (out / "replay_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backtest_core.zorro.paper")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="create the replay copy of Zorro at ZORRO_DIR")
    b = sub.add_parser("bars", help="only export the reference bars (bars_<SYMBOL>.csv) for the live bar check")
    b.add_argument("--out", required=True, type=Path)
    p = sub.add_parser("replay", help="refresh the copy's history and rerun every paper sleeve with -d LIVETEST")
    p.add_argument("--out", required=True, type=Path, help="folder for replay_<Script>.csv and replay_status.json")
    p.add_argument("--scripts", default=",".join(SLEEVES), help="comma-separated sleeve scripts")
    p.add_argument("--end", type=date.fromisoformat, default=date.today() + timedelta(days=1),
                   help="LIVETEST end date (default: tomorrow, i.e. the end of the history)")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "setup":
        print(f"replay copy ready: {setup()}")
        return 0
    if not os.environ.get("BARS_DIR"):
        raise SystemExit("BARS_DIR is not set: the replay reads the bar store")
    if a.cmd == "bars":
        a.out.mkdir(parents=True, exist_ok=True)
        print(export_bars(a.out, list(SLEEVES)))
        return 0
    return replay(a.out, [s.strip() for s in a.scripts.split(",") if s.strip()], a.end)


if __name__ == "__main__":
    raise SystemExit(main())
