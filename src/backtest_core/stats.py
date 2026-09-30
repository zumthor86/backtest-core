"""Performance statistics for daily return series and trade lists.

Conventions match the frozen studies these replace, so a rerun reproduces their printed numbers:
standard deviations use ``ddof=0`` (numpy's default) for Sharpe and Newey-West, ``ddof=1`` across blocks
in ``block_t``, and 252 periods a year unless a caller says otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

PERIODS = 252


def _finite(x) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    return x[np.isfinite(x)]


def sharpe(r, periods: int = PERIODS) -> float:
    r = _finite(r)
    if len(r) < 2 or r.std() == 0:
        return float("nan")
    return float(r.mean() / r.std() * np.sqrt(periods))


def iid_t(r, periods: int = PERIODS) -> float:
    """t-stat of the mean assuming independent returns: Sharpe x sqrt(years)."""
    r = _finite(r)
    return sharpe(r, periods) * float(np.sqrt(len(r) / periods))


def nw_t(x, lags: int = 5) -> float:
    """t-stat of the mean with a Newey-West (Bartlett) variance."""
    x = _finite(x)
    n = len(x)
    if n < 3:
        return float("nan")
    u = x - x.mean()
    v = u @ u / n
    for lag in range(1, min(lags, n - 1) + 1):
        v += 2 * (1 - lag / (lags + 1)) * (u[lag:] @ u[:-lag]) / n
    return float(x.mean() / np.sqrt(v / n)) if v > 0 else float("nan")


def block_t(x, dates, block_days: int = 21) -> tuple[float, int]:
    """t-stat on the means of consecutive ``block_days``-calendar-day blocks (clusters overlapping trades).

    Returns ``(t, number_of_blocks)``.
    """
    x = np.asarray(x, dtype=float)
    if len(x) < 3:
        return float("nan"), 0
    d0 = min(dates)
    blk = np.array([(d - d0).days for d in dates]) // block_days
    means = np.array([x[blk == b].mean() for b in np.unique(blk)])
    if len(means) < 3 or means.std(ddof=1) == 0:
        return float("nan"), len(means)
    return float(means.mean() / (means.std(ddof=1) / np.sqrt(len(means)))), len(means)


def cagr(r, periods: int = PERIODS) -> float:
    r = _finite(r)
    if len(r) == 0:
        return float("nan")
    return float(np.prod(1 + r) ** (periods / len(r)) - 1)


def max_drawdown(r) -> float:
    """Worst peak-to-trough fall of the compounded equity curve, as a negative fraction.

    Peaks come from the curve itself (not from a starting value of 1), as in the frozen studies.
    """
    r = _finite(r)
    if len(r) == 0:
        return float("nan")
    eq = np.cumprod(1 + r)
    return float((eq / np.maximum.accumulate(eq) - 1).min())


def vol_matched_diff(alt, base, lags: int = 5) -> tuple[float, float]:
    """Scale ``alt`` to ``base``'s volatility, then test the daily difference.

    Returns ``(annualised mean difference, Newey-West t)``. Inputs must be aligned day by day.
    """
    alt = np.asarray(alt, dtype=float)
    base = np.asarray(base, dtype=float)
    diff = alt * base.std() / alt.std() - base
    return float(diff.mean() * PERIODS), nw_t(diff, lags)


@dataclass(frozen=True)
class Summary:
    sharpe: float
    t: float
    cagr: float
    max_dd: float
    n_trades: int
    win_rate: float
    mean_trade: float

    def line(self) -> str:
        s = f"CAGR {self.cagr:+6.1%}  Sharpe {self.sharpe:+5.2f}  t {self.t:+5.1f}  max DD {self.max_dd:6.1%}"
        if self.n_trades:
            s += f"  trades {self.n_trades:>5}  win {self.win_rate:4.0%}  mean/trade {self.mean_trade:+.2%}"
        return s


def summary(daily_returns, trades=None, periods: int = PERIODS) -> Summary:
    trades = _finite(trades) if trades is not None else np.array([])
    return Summary(
        sharpe=sharpe(daily_returns, periods),
        t=iid_t(daily_returns, periods),
        cagr=cagr(daily_returns, periods),
        max_dd=max_drawdown(daily_returns),
        n_trades=len(trades),
        win_rate=float(np.mean(trades > 0)) if len(trades) else float("nan"),
        mean_trade=float(trades.mean()) if len(trades) else float("nan"),
    )


def halves(daily_returns, dates, split: date, periods: int = PERIODS) -> tuple[float, float]:
    """Sharpe before and on/after ``split``."""
    r = np.asarray(daily_returns, dtype=float)
    d = np.asarray(dates)
    s = np.datetime64(split)
    return sharpe(r[d < s], periods), sharpe(r[d >= s], periods)
