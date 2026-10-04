"""Flags on bad prices in the research price store, kept beside the store and never written into it.

A flag is one row ``(code, date, reason, detail)``. The price files stay exactly as the vendor sent them; the
loader (``universe.panel``) reads the flags and blanks what they name. So every study cleans the same way, and a
reader can see which days were blanked and why.

    python -m backtest_core.price_flags build     # needs RESEARCH_PRICES_DIR; rewrites the flags beside the store

Reasons, and what the loader does with each:

* ``spike``       a one-day jump of ``SPIKE_FACTOR`` or more that is back within ``SPIKE_UNDONE`` a day later:
                  the price is blanked.
* ``stale``       the same close ``STALE_RUN`` or more sessions in a row (a vendor fill after a halt or delisting):
                  the repeated prices are blanked.
* ``scale_break`` a return above +900% or below -98% between two prices that survived the rules above, i.e. the
                  file changed price scale and stayed there: the return is blanked, the prices are kept.

The rules are the same ones the loader used before the flags existed, plus ``stale``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import polars as pl

SPIKE_FACTOR = 4.0            # a one-day price jump of this size (up or down) ...
SPIKE_UNDONE = 2.0            # ... that is back within this factor of the prior price a day later is a bad tick
STALE_RUN = 10                # this many sessions at the identical close is a fill, not trading
SCALE_BREAK_UP = 9.0          # a one-day return above +900% ...
SCALE_BREAK_DOWN = -0.98      # ... or below -98% is a change of price scale in the file
BLANK_PRICE = ("spike", "stale")
BLANK_RETURN = ("scale_break",)
SCHEMA = {"code": pl.String, "date": pl.Date, "reason": pl.String, "detail": pl.Float64}


def flags_path(prices_dir: str | os.PathLike) -> Path:
    """Beside the store, not inside it: the store reads every parquet file under its folder."""
    p = Path(prices_dir)
    return p.parent / f"{p.name}_flags" / "price_flags.parquet"


def _stale_mask(prices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rows that repeat the previous close inside a run of ``STALE_RUN`` or more identical closes (the first close of
    a run is a real print and is not flagged), and the length of the run."""
    T, N = prices.shape
    with np.errstate(invalid="ignore"):
        same = np.vstack([np.zeros((1, N), bool), (prices[1:] == prices[:-1]) & np.isfinite(prices[1:])])
    run = np.zeros((T, N), dtype=np.int32)
    for t in range(1, T):
        run[t] = np.where(same[t], run[t - 1] + 1, 0)
    total = run.copy()
    for t in range(T - 2, -1, -1):
        total[t] = np.where(same[t + 1] & (run[t] > 0), total[t + 1], total[t])
    total = np.where(run > 0, total, 0)
    return (run >= 1) & (total >= STALE_RUN - 1), total + 1


def detect(days: np.ndarray, codes: list[str], prices: np.ndarray) -> pl.DataFrame:
    """Flags for ``prices`` (days by codes, adjusted close, NaN where there is none). The rules apply in order: a
    price blanked by an earlier rule does not count as a neighbour for a later one."""
    rows: list[pl.DataFrame] = []

    def add(mask: np.ndarray, reason: str, detail: np.ndarray) -> None:
        ti, ci = np.nonzero(mask)
        rows.append(pl.DataFrame({"code": np.array(codes)[ci], "date": days[ti], "reason": reason,
                                  "detail": detail[ti, ci].astype(float)}, schema=SCHEMA))

    p = prices.copy()
    spike = np.zeros(p.shape, bool)
    with np.errstate(invalid="ignore", divide="ignore"):
        jump = np.abs(np.log(p[1:-1] / p[:-2])) > np.log(SPIKE_FACTOR)
        undone = np.abs(np.log(p[2:] / p[:-2])) < np.log(SPIKE_UNDONE)
        ratio = np.full(p.shape, np.nan)
        ratio[1:-1] = p[1:-1] / p[:-2]
    spike[1:-1] = jump & undone
    add(spike, "spike", ratio)
    p[spike] = np.nan

    stale, run = _stale_mask(p)
    add(stale, "stale", run.astype(float))
    p[stale] = np.nan

    move = _move_from_last_price(p)
    with np.errstate(invalid="ignore"):
        broke = (move > SCALE_BREAK_UP) | (move < SCALE_BREAK_DOWN)
    add(broke, "scale_break", move)
    return pl.concat(rows).sort("code", "date", "reason")


def _move_from_last_price(p: np.ndarray) -> np.ndarray:
    """Return of each price against the last price before it (NaN for the first price of a column). Across a gap
    left by a blanked day this is the move the gap hid."""
    T, N = p.shape
    last = np.maximum.accumulate(np.where(np.isfinite(p), np.arange(T)[:, None], -1), axis=0)
    prev = np.vstack([np.full((1, N), -1), last[:-1]])
    prev_price = np.where(prev >= 0, np.take_along_axis(p, np.clip(prev, 0, None), axis=0), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        return p / prev_price - 1


def read(prices_dir: str | os.PathLike, through) -> pl.DataFrame:
    """The flags beside the store. Raises if they are missing or older than the store's last day: a study must not
    run on prices that were never checked."""
    path = flags_path(prices_dir)
    meta = path.with_name("built.json")
    if not path.exists() or not meta.exists():
        raise FileNotFoundError(f"no price flags at {path}; run `python -m backtest_core.price_flags build`")
    built = np.datetime64(json.loads(meta.read_text())["built_through"])
    if built < np.datetime64(through):
        raise LookupError(f"price flags are built through {built}, the store runs to {through}; rebuild them")
    return pl.read_parquet(path)


def apply(prices: np.ndarray, days: np.ndarray, codes: np.ndarray, flags: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """``prices`` with the flagged prices blanked and then restated on one scale, and a days-by-codes mask of the
    scale breaks (the daily return on those days is to be blanked).

    Restating chains the price from its own moves with each scale break counted as no move, so the ratio of any two
    prices of a code equals the compounded cleaned returns between them. Without it a price ratio across a break
    reads thousands of times too large.
    """
    out, ret_mask = prices.copy(), np.zeros(prices.shape, bool)
    f = flags.filter(pl.col("code").is_in(codes.tolist()))
    ti = np.searchsorted(days, f["date"].to_numpy().astype("datetime64[D]"))
    ci = np.searchsorted(codes, f["code"].to_numpy())
    ok = (ti < len(days)) & (days[np.clip(ti, 0, len(days) - 1)] == f["date"].to_numpy().astype("datetime64[D]"))
    kind = f["reason"].to_numpy()
    price_hit = ok & np.isin(kind, BLANK_PRICE)
    out[ti[price_hit], ci[price_hit]] = np.nan
    ret_hit = ok & np.isin(kind, BLANK_RETURN)
    ret_mask[ti[ret_hit], ci[ret_hit]] = True
    step = 1 + _move_from_last_price(out)
    step[ret_mask | ~np.isfinite(step)] = 1.0
    first = np.nanmax(np.where(np.cumsum(np.isfinite(out), axis=0) == 1, out, np.nan), axis=0)    # each code's first price
    chain = np.cumprod(step, axis=0) * first
    return np.where(np.isfinite(out), chain, np.nan), ret_mask


def build(prices_dir: str | os.PathLike | None = None, start: str = "2006-01-01") -> pl.DataFrame:
    from . import universe  # lazy: universe imports this module

    prices_dir = prices_dir or os.environ["RESEARCH_PRICES_DIR"]
    days, codes, raw, _ = universe.price_matrix(prices_dir, start)
    flags = detect(days, codes.tolist(), raw)
    path = flags_path(prices_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags.write_parquet(path)
    counts = {r: int((flags["reason"] == r).sum()) for r in ("spike", "stale", "scale_break")}
    path.with_name("built.json").write_text(json.dumps(
        {"built_through": str(days[-1]), "start": start, "codes": len(codes), "counts": counts,
         "rules": {"SPIKE_FACTOR": SPIKE_FACTOR, "SPIKE_UNDONE": SPIKE_UNDONE, "STALE_RUN": STALE_RUN,
                   "SCALE_BREAK_UP": SCALE_BREAK_UP, "SCALE_BREAK_DOWN": SCALE_BREAK_DOWN}}, indent=1))
    return flags


if __name__ == "__main__":
    import sys

    if sys.argv[1:] != ["build"]:
        raise SystemExit(__doc__)
    f = build()
    print(f.group_by("reason").len().sort("reason"))
