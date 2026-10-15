"""Books across many futures markets, weights scaled by volatility, rebalanced at month-ends.

A market is a dict with ``ses`` (session dates, datetime64[D]), ``r`` (daily return of the back-adjusted series),
``sigma`` (annualised EWMA volatility) and ``months`` (the session's month). `market` builds one from closes.

- `time_series_book`: each market on its own signal; the day's return is the mean over the markets that are live
  (register row 106, time-series momentum).
- `cross_section_book`: each month the markets with a score are ranked (or signed) against each other and each gets
  ``1 / n`` of the book (register row 114, carry).

Both charge ``cost`` per unit of weight change on the first day of the new month, and return ``(days, net, gross)``.
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import polars as pl

TARGET = 0.40
COST = 0.0003


def ewma_sigma(r: np.ndarray, com: int = 60) -> np.ndarray:
    """Annualised EWMA volatility with centre of mass ``com``, seeded with the variance of the first ``com`` returns."""
    var, a = np.zeros(len(r)), 1 / (com + 1)
    var[0] = r[1:com + 1].var()
    for i in range(1, len(r)):
        var[i] = (1 - a) * var[i - 1] + a * r[i] ** 2
    return np.sqrt(252 * var)


def month_ends(ses: np.ndarray) -> np.ndarray:
    months = ses.astype("datetime64[M]")
    return np.flatnonzero(np.append(months[1:] != months[:-1], False))


def market(ses: np.ndarray, close: np.ndarray, com: int = 60) -> dict:
    if not (close > 0).all():
        raise ValueError("adjusted prices must stay positive for percentage returns")
    r = np.concatenate([[0.0], close[1:] / close[:-1] - 1])
    return {"ses": ses, "c": close, "r": r, "sigma": ewma_sigma(r, com), "months": ses.astype("datetime64[M]")}


def time_series_book(
    markets: dict[str, dict],
    signal: Callable[[dict, int], float],
    *,
    target: float = TARGET,
    cost: float = COST,
    min_history: int = 252,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``signal(m, a)`` is the position sign for market ``m`` formed at month-end index ``a`` (e.g. the sign of the
    past ``min_history``-session return). Weight = signal x target / sigma at the month-end."""
    cols = {}
    for sym, m in markets.items():
        r, sigma = m["r"], m["sigma"]
        ends = month_ends(m["ses"])
        w, pnl, cst, w_prev = np.zeros(len(r)), np.zeros(len(r)), np.zeros(len(r)), 0.0
        for a, b in zip(ends[:-1], ends[1:], strict=True):
            if a < min_history:
                continue
            wk = signal(m, a) * target / sigma[a]
            w[a + 1:b + 1] = wk
            pnl[a + 1:b + 1] = wk * r[a + 1:b + 1]
            cst[a + 1] = cost * abs(wk - w_prev)
            w_prev = wk
        cols[sym] = pl.DataFrame({"d": m["ses"], f"p_{sym}": pnl, f"c_{sym}": cst, f"on_{sym}": (w != 0).astype(float)})
    j = None
    for sym in markets:
        j = cols[sym] if j is None else j.join(cols[sym], on="d", how="full", coalesce=True)
    j = j.sort("d").fill_null(0.0)
    names = list(markets)
    on = j.select([f"on_{s}" for s in names]).to_numpy().sum(axis=1)
    live = on > 0
    g = j.select([f"p_{s}" for s in names]).to_numpy().sum(axis=1)[live] / on[live]
    c = j.select([f"c_{s}" for s in names]).to_numpy().sum(axis=1)[live] / on[live]
    return j["d"].to_numpy().astype("datetime64[D]")[live], g - c, g


def trailing_sign(m: dict, a: int, look: int = 252) -> float:
    """Sign of the return over the ``look`` sessions to month-end index ``a``."""
    return float(np.sign(m["c"][a] / m["c"][a - look] - 1))


def _cross_signal(score: np.ndarray, ranked: bool, half: int) -> np.ndarray:
    """The centred rank scaled to -1..+1, or the sign; ``half`` keeps one side only."""
    if ranked:
        rank = np.argsort(np.argsort(score, kind="stable"), kind="stable") + 1.0
        sig = (rank - rank.mean()) / (len(score) / 2)
    else:
        sig = np.sign(score)
    return np.where(half * sig > 0, sig, 0.0) if half else sig


def _held_month(market: dict, mo, w: float, w_prev: float, n: int, cost: float) -> Optional[pl.DataFrame]:
    """One market's daily gross and net through the month after ``mo``; None when it has no session then."""
    hold = np.flatnonzero(market["months"] == mo + 1)
    if len(hold) == 0:
        return None
    g = w * market["r"][hold] / n
    c = np.zeros(len(hold))
    c[0] = cost * abs(w - w_prev) / n
    return pl.DataFrame({"d": market["ses"][hold], "g": g, "n": g - c})


def _book_month(markets, scores, have, mo, prev, ranked, half, target, cost) -> list[pl.DataFrame]:
    """The frames of one formation month; updates ``prev`` (each market's last weight) for those held."""
    sig = _cross_signal(np.array([scores[s][mo][0] for s in have]), ranked, half)
    frames = []
    for s, x in zip(have, sig, strict=True):
        w = x * target / scores[s][mo][1]
        frame = _held_month(markets[s], mo, w, prev[s], len(have), cost)
        if frame is not None:
            frames.append(frame)
            prev[s] = w
    return frames


def cross_section_book(
    markets: dict[str, dict],
    scores: dict[str, dict],
    *,
    ranked: bool = True,
    half: int = 0,
    target: float = TARGET,
    cost: float = COST,
    min_markets: int = 4,
    names: Optional[list[str]] = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``scores[sym][month] = (score, sigma)`` at that month's end; the book is held through the next month.

    Ranked: the centred rank scaled to -1..+1; else the sign of the score. ``half``: +1 long side only, -1 short side
    only. Weight = signal x target / sigma, and each market carries ``1 / n`` of the book, ``n`` the markets scored
    that month. A market that drops out is treated as flat for its next cost."""
    names = list(markets) if names is None else names
    frames, prev = [], dict.fromkeys(names, 0.0)
    for mo in sorted({mo for s in names for mo in scores[s]}):
        have = [s for s in names if mo in scores[s]]
        if len(have) >= min_markets:
            frames += _book_month(markets, scores, have, mo, prev, ranked, half, target, cost)
            for s in set(names) - set(have):
                prev[s] = 0.0
    j = pl.concat(frames).group_by("d").agg(pl.col("g").sum(), pl.col("n").sum()).sort("d")
    return j["d"].to_numpy().astype("datetime64[D]"), j["n"].to_numpy(), j["g"].to_numpy()
