"""A single-position bar simulator: one market, long or short, entries and exits from boolean signals.

It is the stage-1 engine (the quick Python test before a Zorro port), so its fill rules are the ones the Zorro
scripts reproduce:

- ``fill="close"``: act at the close of the signal bar. The entry bar earns nothing but half the cost; each later
  bar earns the close-to-close move; the exit bar earns its move and pays the other half.
- ``fill="open"``: act at the next bar's open. The entry bar earns open-to-close; the exit bar earns previous
  close-to-open.

An exit is checked before an entry on the same bar, so a bar can close one trade but never close and reopen.
Returns are fractions of notional at 1x, so the daily series compounds as an account of fixed leverage.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def cost_fraction(raw_price, tick: float, usd_per_tick: float, ticks: float = 2.0, fee_usd: float = 4.50):
    """Round-trip cost as a fraction of price: ``ticks`` of slippage plus a per-contract fee, on the RAW price."""
    return (ticks * tick + fee_usd * tick / usd_per_tick) / np.asarray(raw_price, dtype=float)


@dataclass(frozen=True)
class Result:
    returns: np.ndarray        # daily returns from ``start`` on
    trades: np.ndarray         # net return of each closed trade
    entries: np.ndarray        # bar index of each entry (signal bar in close mode, fill bar in open mode)
    exits: np.ndarray          # bar index of each exit
    start: int                 # first bar where every signal input was valid
    in_market: float           # share of bars from ``start`` holding a position


def run(open_, close, enter, exit_, valid, cost_rt, side: int = 1, fill: str = "close") -> Result:
    """Simulate one position at a time.

    ``enter``/``exit_``/``valid`` are boolean arrays on the bar grid; signals are ignored where ``valid`` is
    false (warm-up), but an open position keeps earning. ``cost_rt`` is the round-trip cost per bar as a
    fraction of price (see ``cost_fraction``).
    """
    o = np.asarray(open_, dtype=float)
    c = np.asarray(close, dtype=float)
    enter = np.asarray(enter, dtype=bool)
    exit_ = np.asarray(exit_, dtype=bool)
    valid = np.asarray(valid, dtype=bool)
    cost = np.broadcast_to(np.asarray(cost_rt, dtype=float), c.shape)
    if fill not in ("close", "open"):
        raise ValueError(f"fill must be 'close' or 'open', not {fill!r}")

    n = len(c)
    ret = np.zeros(n)
    pos, entry_px, pend, held = 0, 0.0, 0, 0
    trades: list[float] = []
    ent_idx: list[int] = []
    ext_idx: list[int] = []
    for t in range(1, n):
        if fill == "open" and pend:
            if pend == 1:
                pos, entry_px = 1, o[t]
                ent_idx.append(t)
                ret[t] += side * (c[t] / o[t] - 1) - cost[t] / 2
            else:
                ret[t] += side * (o[t] / c[t - 1] - 1) - cost[t] / 2
                trades.append(side * (o[t] / entry_px - 1) - cost[t])
                ext_idx.append(t)
                pos = 0
            pend = 0
        elif pos:
            ret[t] += side * (c[t] / c[t - 1] - 1)
        held += pos
        if not valid[t]:
            continue
        if pos and exit_[t] and not (fill == "open" and pend):
            if fill == "close":
                trades.append(side * (c[t] / entry_px - 1) - cost[t])
                ext_idx.append(t)
                ret[t] -= cost[t] / 2
                pos = 0
            else:
                pend = -1
        elif not pos and enter[t]:
            if fill == "close":
                pos, entry_px = 1, c[t]
                ent_idx.append(t)
                ret[t] -= cost[t] / 2
            else:
                pend = 1
    start = int(np.argmax(valid))
    return Result(ret[start:], np.array(trades), np.array(ent_idx), np.array(ext_idx), start,
                  held / max(n - start, 1))
