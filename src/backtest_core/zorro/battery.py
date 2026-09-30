"""Run the standard robustness battery (Robust.h modes) on one script and collect one results table.

Default pass bars (a pre-registration may set others, and its bars win):

| check                         | mode | bar                          |
|-------------------------------|------|------------------------------|
| bar start moved (6 runs)      | 1    | average Sharpe >= 0.5        |
| drift removed                 | 2    | Sharpe >= 0.3                |
| reality check (shuffled)      | 4    | p <= 5%                      |
| costs doubled                 | 6    | Sharpe > 0                   |
| inverted prices (long-short)  | 7    | Sharpe > 0 (long-short only) |
| history tilted flat           | 3    | report only                  |
| Monte Carlo drawdown          | 5    | report only                  |
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from . import paths, report
from .run import run

DEFAULT_BARS = {"close_avg": 0.5, "detrend_trades": 0.3, "mrc_p": 0.05, "costs_x2": 0.0, "invert": 0.0}


def _fmt(x, fmt="{:.2f}"):
    return "-" if x is None else fmt.format(x)


@dataclass
class Battery:
    script: str
    base: report.Report | None = None
    close_times: list[float] = field(default_factory=list)      # Sharpe per shifted bar start, k = 0..5
    detrend_trades: float | None = None
    detrend_curve: float | None = None
    mrc_pf: float | None = None
    mrc_p: float | None = None
    mrc_cycles: int = 0
    monte_carlo: pl.DataFrame | None = None
    costs_x2: float | None = None
    invert: float | None = None

    @property
    def close_avg(self) -> float | None:
        return sum(self.close_times) / len(self.close_times) if self.close_times else None

    def verdicts(self, bars: dict | None = None, long_short: bool = False) -> dict[str, bool | None]:
        b = {**DEFAULT_BARS, **(bars or {})}

        def ok(x, test):
            return None if x is None else bool(test(x))

        out = {
            "close_avg": ok(self.close_avg, lambda x: x >= b["close_avg"]),
            "detrend_trades": ok(self.detrend_trades, lambda x: x >= b["detrend_trades"]),
            "mrc_p": ok(self.mrc_p, lambda x: x <= b["mrc_p"]),
            "costs_x2": ok(self.costs_x2, lambda x: x > b["costs_x2"]),
        }
        if long_short:
            out["invert"] = ok(self.invert, lambda x: x > b["invert"])
        return out

    def table(self) -> str:
        mc50 = mc95 = None
        if self.monte_carlo is not None:
            rows = {r["confidence"]: r["max_dd_usd"] for r in self.monte_carlo.iter_rows(named=True)}
            mc50, mc95 = rows.get(50), rows.get(95)
        base = (f"{_fmt(self.base.sharpe)} / {_fmt(self.base.profit_factor)} / {self.base.trades}"
                if self.base else "-")
        mrc = f"{_fmt(self.mrc_pf)}, p {_fmt(self.mrc_p, '{:.1%}')} ({max(self.mrc_cycles - 1, 0)} shuffled)"
        return "\n".join([
            f"| check | {self.script} |", "|---|---|",
            f"| base Sharpe / profit factor / trades | {base} |",
            f"| bar start moved, Sharpe for k = 0..5 | {' '.join(_fmt(x) for x in self.close_times) or '-'} |",
            f"| bar start moved, average | {_fmt(self.close_avg)} |",
            f"| drift removed (Detrend TRADES) | {_fmt(self.detrend_trades)} |",
            f"| history tilted flat (Detrend CURVE) | {_fmt(self.detrend_curve)} |",
            f"| reality check: real profit factor, p | {mrc} |",
            f"| costs doubled, Sharpe | {_fmt(self.costs_x2)} |",
            f"| inverted prices, Sharpe | {_fmt(self.invert)} |",
            f"| Monte Carlo max drawdown, 50% / 95% | {_fmt(mc50, '${:,.0f}')} / {_fmt(mc95, '${:,.0f}')} |",
        ])


def mrc_result(path: Path | str) -> tuple[float, float, int]:
    """``(original profit factor, p, cycles)`` from Robust.h's ``Log/<Script>_mrc.csv``."""
    df = pl.read_csv(path, has_header=False, new_columns=["cycle", "pf", "win", "loss", "trades"]).sort("cycle")
    pf = df["pf"].to_list()
    beat = sum(1 for x in pf[1:] if x >= pf[0])
    return pf[0], beat / (len(pf) - 1), len(pf)


def _keep(script: str, tag: str, out_dir: Path | None, *extra: str):
    if out_dir is None:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(paths.log_dir() / f"{script}.txt", out_dir / f"{script}_{tag}.txt")
    for name in extra:
        src = paths.log_dir() / name
        if src.exists():
            shutil.copy2(src, out_dir / name)


def run_battery(script: str, modes=(0, 1, 2, 3, 4, 5, 6, 7), out_dir: Path | str | None = None) -> Battery:
    """Run the listed Robust.h modes for ``script`` and collect the results. Reports are copied to ``out_dir``."""
    out = Path(out_dir) if out_dir else None
    b = Battery(script)
    for m in modes:
        if m == 0:
            b.base = run(script, 0)
            _keep(script, "base", out, f"{script}_trd.csv", f"{script}_pnl.csv")
        elif m == 1:
            b.close_times = []
            for k in range(6):
                b.close_times.append(run(script, 1, k).sharpe)
                _keep(script, f"close{k}", out)
        elif m == 2:
            b.detrend_trades = run(script, 2).sharpe
            _keep(script, "detrend_trades", out)
        elif m == 3:
            b.detrend_curve = run(script, 3).sharpe
            _keep(script, "detrend_curve", out)
        elif m == 4:
            mrc = paths.log_dir() / f"{script}_mrc.csv"
            run(script, 4, output=mrc, timeout=None)         # many cycles, hours on 1-minute bars; writes only our CSV
            b.mrc_pf, b.mrc_p, b.mrc_cycles = mrc_result(mrc)
            if out is not None:
                out.mkdir(parents=True, exist_ok=True)
                shutil.copy2(mrc, out / mrc.name)
        elif m == 5:
            b.monte_carlo = run(script, 5).monte_carlo
            _keep(script, "montecarlo", out)
        elif m == 6:
            b.costs_x2 = run(script, 6).sharpe
            _keep(script, "costs_x2", out)
        elif m == 7:
            b.invert = run(script, 7).sharpe
            _keep(script, "invert", out)
        else:
            raise ValueError(f"mode {m} is a training mode; use plateau() / walk_forward()")
    return b
