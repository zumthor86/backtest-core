"""Bar loading through store-core, with the session rules done once.

Intraday series come from ``store_core.BarStore`` (1m / 1h, one back-adjusted series per symbol, ``BARS_DIR``).
Every price is adjusted; the raw (as traded) price is ``adjusted / factor``, which is what costs in ticks must be
charged against.
"""
from __future__ import annotations

import os

import polars as pl

BAR_COLUMNS = ["start", "session", "open", "high", "low", "close", "volume", "factor"]


def _store(base_dir: str | None):
    from store_core import BarStore  # lazy: statistics must work in a venv without store-core

    return BarStore(base_dir or os.environ["BARS_DIR"])


def intraday(symbol: str, source: str = "databento", freq: str = "1m", columns=None,
             base_dir: str | None = None) -> pl.DataFrame:
    """The stored series, sorted by bar open time. ``source`` is ``databento`` (futures) or ``eodhd`` (stocks)."""
    return _store(base_dir).read(symbol, source, freq=freq, columns=columns or BAR_COLUMNS).sort("start")


def daily(symbol: str, source: str = "databento", freq: str = "1m", base_dir: str | None = None) -> pl.DataFrame:
    """One bar per trading session: first open, max high, min low, last close, last factor.

    Futures sessions run 18:00 ET to 18:00 ET (the store's ``session`` = date of bar open + 6 h), which is also
    how the Zorro scripts cut daily bars (``BarZone = ET; BarOffset = 18*60``).
    """
    b = intraday(symbol, source, freq, ["start", "session", "open", "high", "low", "close", "factor"], base_dir)
    return (b.group_by("session", maintain_order=True)
             .agg(pl.col("open").first(), pl.col("high").max(), pl.col("low").min(), pl.col("close").last(),
                  pl.col("factor").last())
             .sort("session"))
