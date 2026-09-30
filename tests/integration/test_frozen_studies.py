"""The library must reproduce studies already on record, digit for digit as printed.

Needs the bar store (BARS_DIR) and the Hephaestus research record; skipped where either is absent.
"""
import os
import re
from pathlib import Path

import numpy as np
import pytest

from backtest_core import bars, sim, stats

RECORD = Path("C:/Users/Christopher/Documents/python/Hephaestus/backtests/murphys_law/results_futures.txt")
TICK = {"ES": (0.25, 12.5), "NQ": (0.25, 5.0)}

pytestmark = pytest.mark.skipif(not (os.environ.get("BARS_DIR") and RECORD.exists()),
                                reason="needs BARS_DIR and the Hephaestus record")


def _qpi(r3, lo=252, hi=1260):
    q = np.full(len(r3), np.nan)
    for i in range(len(r3)):
        if not np.isfinite(r3[i]):
            continue
        w = r3[max(0, i - hi):i]
        w = w[np.isfinite(w)]
        if len(w) >= lo:
            q[i] = np.mean(w <= r3[i])
    return q


def _rsi2(c):
    d = np.diff(c, prepend=np.nan)
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    au, ad = np.full(len(c), np.nan), np.full(len(c), np.nan)
    for i in range(1, len(c)):
        au[i] = up[i] if i == 1 else 0.5 * au[i - 1] + 0.5 * up[i]
        ad[i] = dn[i] if i == 1 else 0.5 * ad[i - 1] + 0.5 * dn[i]
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100 - 100 / (1 + au / ad)


def _dip_buy(m, fill):
    d = bars.daily(m)
    o, h, l, c = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
    r3 = np.r_[np.full(3, np.nan), c[3:] / c[:-3] - 1]
    q = _qpi(r3)
    ibs = np.where(h > l, (c - l) / (h - l), 0.5)
    sma = np.r_[np.full(199, np.nan), np.convolve(c, np.ones(200) / 200, "valid")]
    enter = (r3 < 0) & (q <= 0.30) & (ibs < 0.10) & (c > sma)
    exit_ = (ibs > 0.90) | (_rsi2(c) > 90)
    cost = sim.cost_fraction(c / d["factor"].to_numpy(), *TICK[m])
    return sim.run(o, c, enter, exit_, np.isfinite(q) & np.isfinite(sma), cost, fill=fill)


def _recorded(m):
    line = next(x for x in RECORD.read_text(encoding="utf-8").splitlines() if x.strip().startswith(m + " "))
    nums = re.findall(r"[+-]?\d+\.?\d*", line)
    return {"cagr": float(nums[0]), "sharpe": float(nums[1]), "t": float(nums[2]), "trades": int(nums[3]),
            "win": int(nums[4]), "in_mkt": int(nums[5]), "open_sharpe": float(nums[6])}


@pytest.mark.parametrize("m", ["ES", "NQ"])
def test_futures_dip_buy_matches_results_futures_txt(m):
    rec = _recorded(m)
    r = _dip_buy(m, "close")
    ro = _dip_buy(m, "open")
    s = stats.summary(r.returns, r.trades)
    assert f"{s.cagr * 100:+.1f}" == f"{rec['cagr']:+.1f}"
    assert f"{s.sharpe:+.2f}" == f"{rec['sharpe']:+.2f}"
    assert f"{s.t:+.1f}" == f"{rec['t']:+.1f}"
    assert s.n_trades == rec["trades"]
    assert round(s.win_rate * 100) == rec["win"]
    assert round(r.in_market * 100) == rec["in_mkt"]
    assert f"{stats.sharpe(ro.returns):+.2f}" == f"{rec['open_sharpe']:+.2f}"
