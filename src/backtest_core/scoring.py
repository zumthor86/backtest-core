"""One scoring helper for a daily book or a list of trades, in place of the `score()` each study copied.

`daily` gives the numbers a register row prints for a daily net series (net Sharpe, block t on calendar blocks, CAGR,
max drawdown, gross Sharpe) and whether the pre-registered bars pass. `per_trade` does the same for one return per
trade (mean and t). Both take a window mask, so one function serves the in-sample and the holdout run.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from backtest_core import stats


@dataclass(frozen=True)
class Daily:
    first: object
    last: object
    sharpe: float
    block_t: float
    blocks: int
    cagr: float
    max_dd: float
    gross_sharpe: float
    passed: Optional[bool]

    def line(self, label: str) -> str:
        text = (f"{label}: {self.first} .. {self.last}, net Sharpe {self.sharpe:+.2f}, block t {self.block_t:+.2f} "
                f"({self.blocks} blocks), CAGR {self.cagr:+.1%}, max DD {self.max_dd:.1%}; gross Sharpe {self.gross_sharpe:+.2f}")
        return text if self.passed is None else text + f" -> {'PASS' if self.passed else 'FAIL'}"


@dataclass(frozen=True)
class PerTrade:
    first: object
    last: object
    trades: int
    mean: float
    t: float
    gross_mean: float
    win: float
    passed: Optional[bool]

    def line(self, label: str) -> str:
        text = (f"{label}: {self.first} .. {self.last}, {self.trades} trades, net mean {self.mean * 1e4:+.1f} bps "
                f"(t {self.t:+.2f}), gross mean {self.gross_mean * 1e4:+.1f} bps, win {self.win:.0%}")
        return text if self.passed is None else text + f" -> {'PASS' if self.passed else 'FAIL'}"


def _mask(days: np.ndarray, mask) -> np.ndarray:
    return np.ones(len(days), dtype=bool) if mask is None else np.asarray(mask, dtype=bool)


def daily(days: np.ndarray, net: np.ndarray, gross: Optional[np.ndarray] = None, mask=None,
          sharpe_bar: Optional[float] = None, t_bar: Optional[float] = None, block_days: int = 21) -> Daily:
    m = _mask(days, mask)
    d, n = days[m], net[m]
    g = n if gross is None else gross[m]
    s = stats.summary(n)
    bt, nb = stats.block_t(n, d.astype(object), block_days)
    passed = None
    if sharpe_bar is not None or t_bar is not None:
        passed = (sharpe_bar is None or s.sharpe >= sharpe_bar) and (t_bar is None or bt >= t_bar)
    return Daily(d[0], d[-1], s.sharpe, bt, nb, s.cagr, s.max_dd, stats.sharpe(g), passed)


def per_trade(days: np.ndarray, net: np.ndarray, gross: Optional[np.ndarray] = None, mask=None,
              t_bar: Optional[float] = None) -> PerTrade:
    m = _mask(days, mask)
    d, n = days[m], net[m]
    g = n if gross is None else gross[m]
    t = n.mean() / (n.std(ddof=1) / np.sqrt(len(n)))
    passed = None if t_bar is None else bool(n.mean() > 0 and t >= t_bar)
    return PerTrade(d[0], d[-1], len(n), n.mean(), t, g.mean(), float(np.mean(n > 0)), passed)
