"""Cross-sectional sort books on a member panel (stock sorts).

A panel is a dict of day x stock matrices, as `Hephaestus/backtests/lit_refs_sweep/sweep.py::stock_panel()` builds:
``days`` (datetime64[D]), ``ret`` (daily return, 0 where missing), ``mem`` (member on that day), and ``me`` (the index
of the last session of each month). A signal is a function of the formation index ``k`` that returns one value per
stock (high = long) or None to skip that formation.

`sort_book` is `monthly_ls` of that study made general: any quantile, any formation schedule, leverage per leg, a
risk-free leg, and the cost and borrow as arguments. With the defaults it reproduces register rows 107, 110 and 112.
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np

SIDE = 0.0005             # 5 bps a side
BORROW = 0.01 / 252       # short leg, per day


def month_ends(days: np.ndarray) -> np.ndarray:
    """Index of the last session of each complete month (the last month of the panel is not complete)."""
    months = days.astype("datetime64[M]")
    return np.flatnonzero(np.append(months[1:] != months[:-1], False))


def sort_book(
    panel: dict,
    signal: Callable[[int], Optional[np.ndarray]],
    *,
    quantile: int = 10,
    form: Optional[np.ndarray] = None,
    lev: Optional[Callable[[int, np.ndarray, np.ndarray], tuple[float, float]]] = None,
    rf: Optional[np.ndarray] = None,
    side: float = SIDE,
    borrow: float = BORROW,
    start: Optional[np.datetime64] = None,
    min_names: int = 100,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Long the top quantile, short the bottom, equal weight, formed at ``form[k]`` and held to ``form[k + 1]``.

    Each leg's daily return is that of a buy-and-hold basket (weights drift within the holding period). The cost is
    ``side`` per unit of turnover on the first held day (a full rebuild is turnover 2 per leg) and ``borrow`` per day on
    the short leg. Returns ``(days, net, gross)`` from the first held day.
    """
    days, ret, mem = panel["days"], panel["ret"], panel["mem"]
    form = panel["me"] if form is None else form
    T = len(days)
    gross, net = np.zeros(T), np.zeros(T)
    rf = np.zeros(T) if rf is None else rf
    prev_l = prev_s = None
    first = None
    for k in range(len(form) - 1):
        t = form[k]
        sig = signal(k)
        if sig is None or (start is not None and days[t] < start):
            continue
        ok = np.flatnonzero(mem[t] & np.isfinite(sig))
        if len(ok) < min_names:
            continue
        order = ok[np.argsort(sig[ok], kind="stable")]
        n = len(ok) // quantile
        short, long_ = order[:n], order[-n:]
        l_lev, s_lev = lev(k, long_, short) if lev else (1.0, 1.0)
        seg = slice(t + 1, form[k + 1] + 1)

        def leg(idx):
            v = np.cumprod(1 + ret[seg][:, idx], axis=0).mean(axis=1)
            return np.diff(np.concatenate([[1.0], v])) / np.concatenate([[1.0], v[:-1]])

        g = l_lev * (leg(long_) - rf[seg]) - s_lev * (leg(short) - rf[seg])
        turn_l = 2.0 if prev_l is None else 2.0 * (1 - len(np.intersect1d(long_, prev_l)) / n)
        turn_s = 2.0 if prev_s is None else 2.0 * (1 - len(np.intersect1d(short, prev_s)) / n)
        cost = np.full(len(g), borrow * s_lev)
        cost[0] += side * (l_lev * turn_l + s_lev * turn_s)
        gross[seg], net[seg] = g, g - cost
        prev_l, prev_s = long_, short
        first = first if first is not None else t + 1
    if first is None:
        raise ValueError("no formation had enough names: nothing was held")
    return days[first:], net[first:], gross[first:]


def trailing_return(ac: np.ndarray, form: np.ndarray, k: int, skip: int, look: int) -> Optional[np.ndarray]:
    """Return from formation ``k - look`` to ``k - skip`` (12-1 momentum is ``skip=1, look=12``); None before history."""
    if k < look:
        return None
    with np.errstate(invalid="ignore", divide="ignore"):
        return ac[form[k - skip]] / ac[form[k - look]] - 1
