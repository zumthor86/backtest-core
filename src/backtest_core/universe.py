"""Stock universes by date: index members, their prices (dead companies included) and their earnings notices.

Everything is read from Hermes: member snapshots (``v_index_membership``), who each member was
(``v_index_listing``: price code, SEC company number, industry code), SEC earnings notices
(``v_earnings_filings``) and the research price store (``RESEARCH_PRICES_DIR``).

A column of a :class:`Panel` is one **stay**: an unbroken run of a ticker in the Russell 3000. A ticker is not a
company (it is reused, and a delisted company has none), so nothing here is keyed by ticker alone.

    P = universe.panel("R3000")          # or "SP500": the same columns, S&P 500 membership
    E = universe.earnings(P)             # one row per notice: column k, first session i that could react
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

import numpy as np
import polars as pl

from . import price_flags

IDENTITY_INDEX = "R3000"      # the index whose stays carry price codes and SEC numbers
MIN_PRICED_NAMES = 1000       # a date is a trading day if at least this many names have a price
AFTER_CLOSE_HOUR = 16         # New York; a notice stamped from here on is first tradable the next session
OPEN_RANGE = (0.5, 2.0)       # an open outside this band around its own close is a bad print, not a price
BROKEN_STAY_DAYS = 3        # member-days above +-100% after which a stay's price file is not believed


@dataclass
class Panel:
    """Daily matrices, ``days`` by stays. ``ret`` is 0 where a price is missing; ``has`` says where it is real."""

    days: np.ndarray          # datetime64[D], trading days
    stays: pl.DataFrame       # one row per column: symbol, first_date, last_date, name, sector, eodhd_code, cik, sic_code
    ac: np.ndarray            # adjusted close (NaN where none)
    op: np.ndarray            # adjusted open on the same scale as ``ac`` (NaN where there is no usable open)
    ret: np.ndarray           # close-to-close return on the adjusted close
    has: np.ndarray           # a price today and on the previous trading day
    mem: np.ndarray           # index member that day (latest snapshot on or before it)
    weight: np.ndarray        # index weight in percent from that snapshot (NaN where not a member or not stated)
    dropped: pl.DataFrame     # stays removed because their price file is broken

    @property
    def month_ends(self) -> np.ndarray:
        """Index of the last trading day of each complete month."""
        months = self.days.astype("datetime64[M]")
        return np.flatnonzero(np.append(months[1:] != months[:-1], False))


def _read(sql: str, params: dict, db_url: str | None) -> pl.DataFrame:
    from sqlalchemy import create_engine, text  # lazy: statistics must work in a venv without a database driver
    from sqlalchemy.pool import NullPool

    engine = create_engine(db_url or os.environ["HERMES_DB_URL"], poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return pl.read_database(text(sql), connection=conn, execute_options={"parameters": params},
                                    infer_schema_length=None)
    finally:
        engine.dispose()


def members(index: str, db_url: str | None = None) -> pl.DataFrame:
    """Every dated snapshot of an index: ``symbol, as_of_date, weight_pct``."""
    df = _read("SELECT symbol, as_of_date, weight_pct FROM v_index_membership WHERE index_code = :i", {"i": index}, db_url)
    if df.is_empty():
        raise LookupError(f"no member snapshots for index {index!r} in v_index_membership")
    return df.with_columns(pl.col("as_of_date").cast(pl.Date), pl.col("weight_pct").cast(pl.Float64))


def listings(db_url: str | None = None) -> pl.DataFrame:
    """Stays that have a proven price code. Unproven stays are left out: a guessed code is another company."""
    df = _read("SELECT symbol, first_date, last_date, name, sector, eodhd_code, cik, sic_code FROM v_index_listing "
               "WHERE index_code = :i AND eodhd_code IS NOT NULL ORDER BY symbol, first_date", {"i": IDENTITY_INDEX}, db_url)
    return df.with_columns(pl.col("first_date").cast(pl.Date), pl.col("last_date").cast(pl.Date))


def membership_matrix(days: np.ndarray, snapshots: pl.DataFrame, stays: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """``(mem, weight)``, days by stays: each day carries the latest snapshot on or before it.

    A snapshot row belongs to the stay of its ticker that covers the snapshot date, so a ticker reused by a later
    company lands in the later company's column.
    """
    st = stays.with_row_index("k").select("k", "symbol", "first_date", "last_date")
    hit = (snapshots.join(st, on="symbol", how="inner")
                    .filter((pl.col("as_of_date") >= pl.col("first_date")) & (pl.col("as_of_date") <= pl.col("last_date"))))
    snap_days = snapshots["as_of_date"].unique().sort().to_numpy().astype("datetime64[D]")
    s = np.searchsorted(snap_days, hit["as_of_date"].to_numpy().astype("datetime64[D]"))
    in_snap = np.zeros((len(snap_days), stays.height), dtype=bool)
    w_snap = np.full((len(snap_days), stays.height), np.nan)
    k = hit["k"].to_numpy()
    in_snap[s, k] = True
    w_snap[s, k] = hit["weight_pct"].to_numpy()
    latest = np.searchsorted(snap_days, days, side="right") - 1          # -1: before the first snapshot
    mem = np.where((latest >= 0)[:, None], in_snap[np.clip(latest, 0, None)], False)
    weight = np.where(mem, w_snap[np.clip(latest, 0, None)], np.nan)
    return mem, weight


def panel(index: str = "R3000", start: date | str = "2006-01-01", prices_dir: str | None = None,
          db_url: str | None = None) -> Panel:
    """Daily prices and membership for every stay with a proven price code, from ``start``."""
    prices_dir = prices_dir or os.environ["RESEARCH_PRICES_DIR"]
    stays = listings(db_url)
    days, codes, raw, open_rel = price_matrix(prices_dir, start)
    # Bad prices are named in the flags built beside the store (``price_flags``); the files are never edited.
    by_code, ret_blank = price_flags.apply(raw, days, codes, price_flags.read(prices_dir, days[-1]))
    stays = stays.filter(pl.col("eodhd_code").is_in(codes.tolist()))
    cols = codes.searchsorted(stays["eodhd_code"].to_numpy())
    ac, ret_blank, open_rel = by_code[:, cols], ret_blank[:, cols], open_rel[:, cols]
    with np.errstate(invalid="ignore", divide="ignore"):
        ret = np.vstack([np.full((1, ac.shape[1]), np.nan), ac[1:] / ac[:-1] - 1])
    ret[ret_blank] = np.nan
    has = np.isfinite(ret)
    ret = np.nan_to_num(ret)
    mem, weight = membership_matrix(days, members(index, db_url), stays)
    # A stay that still doubles in a day this often is a broken price file, not a stock (one code flips between
    # two price scales 235 times). It is removed whole and named, never patched day by day.
    broken = ((np.abs(ret) > 1.0) & mem).sum(axis=0) >= BROKEN_STAY_DAYS
    keep = np.flatnonzero(~broken)
    return Panel(days=days, stays=stays[keep], ac=ac[:, keep], op=(ac * open_rel)[:, keep], ret=ret[:, keep],
                 has=has[:, keep], mem=mem[:, keep], weight=weight[:, keep], dropped=stays[np.flatnonzero(broken)])


def price_matrix(prices_dir: str, start: date | str = "2006-01-01") -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The research price store as it is: trading days, price codes (sorted), adjusted closes, and each day's
    open over its own close (NaN where the open is missing or outside ``OPEN_RANGE`` of the close), days by codes.
    A trading day is a date on which at least ``MIN_PRICED_NAMES`` codes have a price."""
    from store_core import PriceStore  # lazy, as in ``bars``

    px = PriceStore(prices_dir).read(start_date=start)
    if px.is_empty():
        raise LookupError("the research price store returned nothing; is RESEARCH_PRICES_DIR set?")
    rel = pl.col("open") / pl.col("close")
    px = (px.filter((pl.col("adjusted_close") > 0) & (pl.col("close") > 0))
            .select("symbol", pl.col("date").cast(pl.Date), "adjusted_close",
                    pl.when(rel.is_between(*OPEN_RANGE)).then(rel).otherwise(None).alias("open_rel"))
            .unique(["symbol", "date"]))
    counts = px.group_by("date").len().filter(pl.col("len") >= MIN_PRICED_NAMES)
    cal = counts["date"].sort()
    px = px.join(counts.select("date"), on="date")
    codes = px["symbol"].unique().sort()
    out, open_rel = np.full((len(cal), len(codes)), np.nan), np.full((len(cal), len(codes)), np.nan)
    ti, ci = cal.search_sorted(px["date"]).to_numpy(), codes.search_sorted(px["symbol"]).to_numpy()
    out[ti, ci] = px["adjusted_close"].to_numpy()
    open_rel[ti, ci] = px["open_rel"].fill_null(float("nan")).to_numpy()
    return cal.to_numpy().astype("datetime64[D]"), codes.to_numpy(), out, open_rel


def first_session(days: np.ndarray, filed_at_utc: pl.Series) -> tuple[np.ndarray, pl.Series]:
    """Index into ``days`` of the first session that could react to each stamp, and the stamp in New York time.

    A notice stamped before 16:00 New York on a trading day is tradable that day; from 16:00 on, or on a day the
    market is shut, the next session. A stamp after the last day maps to ``len(days)``.
    """
    ny = filed_at_utc.dt.convert_time_zone("America/New_York")
    day = ny.dt.date().to_numpy().astype("datetime64[D]")
    i = np.searchsorted(days, day)
    on_session = (i < len(days)) & (days[np.clip(i, 0, len(days) - 1)] == day)
    late = (ny.dt.hour() >= AFTER_CLOSE_HOUR).to_numpy()
    return i + (on_session & late), ny


def earnings(P: Panel, db_url: str | None = None) -> pl.DataFrame:
    """SEC earnings notices of the panel's companies: ``k`` (column), ``i`` (first session that could react),
    ``cik``, ``filed_at`` (New York time), ``after_close``. Only notices that fall inside the stay's own dates
    (with a year of slack either side) are kept, so a company with two stays gets each notice once.
    """
    f = _read("SELECT cik, filed_at FROM v_earnings_filings", {}, db_url)
    f = f.with_columns(pl.col("cik").cast(pl.Int64), pl.col("filed_at").cast(pl.Datetime("us", "UTC")))
    st = P.stays.with_row_index("k").filter(pl.col("cik").is_not_null()).select(
        pl.col("k").cast(pl.Int64), pl.col("cik").cast(pl.Int64), "first_date", "last_date")
    e = f.join(st, on="cik", how="inner")
    day = e["filed_at"].dt.date()
    e = e.filter((day >= e["first_date"].dt.offset_by("-1y")) & (day <= e["last_date"].dt.offset_by("1y")))
    i, ny = first_session(P.days, e["filed_at"])
    return (e.with_columns(i=pl.Series(i), filed_at=ny, after_close=ny.dt.hour() >= AFTER_CLOSE_HOUR)
             .filter(pl.col("i") < len(P.days)).select("k", "i", "cik", "filed_at", "after_close").sort("i", "k"))
