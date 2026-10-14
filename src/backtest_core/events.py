"""Event rules on a list of dates.

- `flag_days`: which sessions are event days (a date that is not a session moves to the next session).
- `hold_flagged`: a daily book that is long on event days only; a run of consecutive event days is one trade, charged
  on its first day (register row 117).
- `mark_to_mark`: one trade per event, from the last entry mark before the event day to the exit mark on it
  (register row 111, pre-FOMC drift).
- `cohort_book`: each day's selection is held for a fixed span, cohorts overlapping (the high-volume premium).
- `welch_t` and `check_dates`: the date check made before a date list is used (the move must be larger on event days).
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional, Sequence

import numpy as np


def flag_days(days: np.ndarray, event_dates: Sequence[date]) -> np.ndarray:
    """Boolean per session: True on the session that holds each event (on the date, or the next session after it).
    The first session is never flagged: it has no prior close to buy at."""
    wanted = np.array(sorted(set(event_dates)), dtype="datetime64[D]")
    idx = np.searchsorted(days, wanted)
    flag = np.zeros(len(days), dtype=bool)
    flag[idx[idx < len(days)]] = True
    flag[0] = False
    return flag


def run_starts(flag: np.ndarray) -> np.ndarray:
    """Index of the first day of each run of flagged days."""
    return np.flatnonzero(flag & ~np.concatenate([[False], flag[:-1]]))


def hold_flagged(r: np.ndarray, flag: np.ndarray, entry_cost: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    """Gross and net daily returns of holding on flagged days. ``entry_cost[i]`` is the round-trip cost of a trade
    whose first day is ``i``; it is charged on that day. Returns ``(gross, net, trades)``."""
    starts = run_starts(flag)
    cost = np.zeros(len(r))
    cost[starts] = entry_cost[starts]
    gross = np.where(flag, r, 0.0)
    return gross, gross - cost, len(starts)


def mark_to_mark(
    event_dates: Sequence[date],
    entry_days: Sequence[date],
    entry_px: np.ndarray,
    exit_px: dict[date, float],
    cost: Callable[[int], float],
    max_gap_days: int = 5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For each event day ``d``: buy at the last entry mark strictly before ``d`` (no more than ``max_gap_days`` before
    it) and sell at ``exit_px[d]``. ``cost(i)`` is the round-trip cost as a fraction for entry mark ``i``. Events with
    no exit mark or no recent entry mark are skipped. Returns ``(days, net, gross)`` per trade."""
    ad = np.array(entry_days, dtype="datetime64[D]")
    out_d, net, gross = [], [], []
    for d in event_dates:
        i = int(np.searchsorted(ad, np.datetime64(d))) - 1
        if i < 0 or d not in exit_px or (d - entry_days[i]).days > max_gap_days:
            continue
        g = exit_px[d] / entry_px[i] - 1
        out_d.append(d)
        gross.append(g)
        net.append(g - float(cost(i)))
    return np.array(out_d, dtype="datetime64[D]"), np.array(net), np.array(gross)


def cohort_book(
    weights: np.ndarray,
    ret: np.ndarray,
    hold: int,
    lag: int = 2,
) -> np.ndarray:
    """Position matrix of overlapping cohorts: the selection of day ``t`` (rows of ``weights`` sum to 1 or 0) earns
    the returns of days ``t + lag`` .. ``t + lag + hold - 1``, each cohort at ``1 / hold`` of capital.

    With ``lag=2, hold=20`` this is the 20-session cohort book of the high-volume premium (formed at the close of
    ``t``, entered at the close of ``t + 1``)."""
    T, N = weights.shape
    c = np.cumsum(np.vstack([np.zeros((1, N)), weights]), axis=0)
    p = np.zeros((T, N))
    # Day s holds the cohorts formed on s - lag - hold + 1 .. s - lag.
    for s in range(lag, T):
        lo = max(0, s - lag - hold + 1)
        p[s] = (c[s - lag + 1] - c[lo]) / hold
    return p


def welch_t(a: np.ndarray, b: np.ndarray) -> float:
    return float((a.mean() - b.mean()) / np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))


def check_dates(r: np.ndarray, flag: np.ndarray, min_ratio: Optional[float] = None) -> dict:
    """The size of the move on event days against other days. It reads no signed return, so it can be run before a
    pre-registration: a list of real event dates shows a larger mean absolute move on its days."""
    on, off = np.abs(r[flag]), np.abs(r[~flag])
    out = {"event_days": int(flag.sum()), "abs_move_event_bps": on.mean() * 1e4, "abs_move_other_bps": off.mean() * 1e4,
           "ratio": on.mean() / off.mean(), "welch_t_abs": welch_t(on, off)}
    if min_ratio is not None and out["ratio"] < min_ratio:
        raise ValueError(f"date list fails its check: event-day move {out['ratio']:.2f}x other days (< {min_ratio})")
    return out
