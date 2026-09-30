"""Read Zorro's performance report (``Log/<Script>.txt``) and its CSV outputs."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

_NUM = r"([+-]?\d+(?:\.\d+)?)"


@dataclass
class Report:
    script: str
    sharpe: float | None = None
    profit_factor: float | None = None
    trades: int | None = None
    win_rate: float | None = None           # fraction
    max_dd_usd: float | None = None
    annual_growth: float | None = None      # fraction
    test_period: str | None = None
    sample_cycle_pf: list[float] = field(default_factory=list)
    monte_carlo: pl.DataFrame | None = None  # confidence, return, max_dd, capital
    text: str = ""


def _first(pattern: str, text: str, cast=float):
    m = re.search(pattern, text, re.M)
    return cast(m.group(1)) if m else None


def parse(text: str, script: str = "") -> Report:
    r = Report(script=script, text=text)
    r.sharpe = _first(rf"^Sharpe ratio\s+{_NUM}", text)
    r.profit_factor = _first(rf"^Profit factor\s+{_NUM}", text)
    r.trades = _first(r"^Number of trades\s+(\d+)", text, int)
    wr = _first(rf"^Percent winning\s+{_NUM}%", text)
    r.win_rate = wr / 100 if wr is not None else None
    r.max_dd_usd = _first(rf"^Max drawdown\s+{_NUM}\$", text)
    ag = _first(rf"^Annual growth rate\s+{_NUM}%", text)
    r.annual_growth = ag / 100 if ag is not None else None
    r.test_period = _first(r"^Test period\s+(\S+)", text, str)
    m = re.search(r"^Sample cycles ProF\s+(.+)$", text, re.M)
    if m:
        r.sample_cycle_pf = [float(x) for x in m.group(1).split()]
    rows = re.findall(rf"^\s*(\d+)% Confidence\s+{_NUM}%\s+{_NUM}\s+{_NUM}\$", text, re.M)
    if rows:
        r.monte_carlo = pl.DataFrame(
            {"confidence": [int(a) for a, *_ in rows], "annual_return": [float(b) / 100 for _, b, _, _ in rows],
             "max_dd_usd": [float(c) for *_, c, _ in rows], "capital_usd": [float(d) for *_, d in rows]})
    return r


def read(path: Path | str) -> Report:
    path = Path(path)
    return parse(path.read_text(encoding="utf-8", errors="replace"), path.stem)


def trades_csv(path: Path | str) -> pl.DataFrame:
    """Zorro's ``_trd.csv`` (written with ``set(LOGFILE)``): one row per closed trade."""
    return pl.read_csv(path, try_parse_dates=True)


def pnl_csv(path: Path | str) -> pl.DataFrame:
    """Zorro's ``_pnl.csv``: the daily equity or balance curve."""
    return pl.read_csv(path, try_parse_dates=True)
