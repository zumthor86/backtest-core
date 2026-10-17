"""CFTC Commitments of Traders from Hermes (view ``v_cot_positions``) and the point-in-time guard.

A report shows positions as of a Tuesday and is public only from its ``release_date`` (normally the
Friday at 15:30 New York; later in holiday weeks, and weeks later after a shutdown). `known_at`
gives each session the latest report released **before** that session's date, so a Friday release is
first used on the Monday. The release day's own close is ruled out on purpose: many futures settle
before 15:30 New York.

    from backtest_core import cot
    w = cot.wide(cot.read(["CL", "GC"]))                   # one row per root and report
    k = cot.known_at(w, sessions)                          # the report each session could use
"""
from __future__ import annotations

import os
from typing import Iterable, Optional

import polars as pl

_COLUMNS = ("root, cftc_code, as_of_date, release_date, release_basis, open_interest, trader_group, positions_long, "
            "positions_short, positions_spread, traders_long, traders_short, traders_spread")
_KEY = ["root", "as_of_date", "release_date", "release_basis", "open_interest"]


def read(
    roots: Optional[Iterable[str]] = None,
    report_type: str = "legacy",
    scope: str = "futures",
    groups: Optional[Iterable[str]] = None,
    db_url: Optional[str] = None,
) -> pl.DataFrame:
    """Rows of ``v_cot_positions`` for our futures roots: one per root, report and trader group.

    ``roots`` are bar-store symbols (CL, GC, ES …); None reads every mapped root. Raises when nothing
    matches, so a wrong root or an unloaded report never reads as "no positions"."""
    from sqlalchemy import create_engine, text  # lazy: statistics must work in a venv without a database driver
    from sqlalchemy.pool import NullPool

    engine = create_engine(db_url or os.environ["HERMES_DB_URL"], poolclass=NullPool)
    try:
        with engine.connect() as conn:
            df = pl.read_database(
                text(f"SELECT {_COLUMNS} FROM v_cot_positions WHERE report_type = :r AND scope = :s AND root IS NOT NULL"),
                connection=conn, execute_options={"parameters": {"r": report_type, "s": scope}},
                infer_schema_length=None)
    finally:
        engine.dispose()
    if roots is not None:
        df = df.filter(pl.col("root").is_in(list(roots)))
    if groups is not None:
        df = df.filter(pl.col("trader_group").is_in(list(groups)))
    if df.is_empty():
        raise LookupError(f"no {report_type}/{scope} COT rows for roots {roots} and groups {groups} in v_cot_positions")
    return df.with_columns(pl.col("as_of_date").cast(pl.Date), pl.col("release_date").cast(pl.Date)).sort(
        "root", "as_of_date", "trader_group")


def wide(rows: pl.DataFrame) -> pl.DataFrame:
    """One row per root and report: ``<group>_long``, ``<group>_short``, ``<group>_spread`` and
    ``<group>_net`` (long minus short) for each trader group in ``rows``."""
    out = rows.select(_KEY).unique()
    for group in rows["trader_group"].unique().sort():
        g = rows.filter(pl.col("trader_group") == group).select(
            "root", "as_of_date",
            pl.col("positions_long").alias(f"{group}_long"),
            pl.col("positions_short").alias(f"{group}_short"),
            pl.col("positions_spread").alias(f"{group}_spread"),
            (pl.col("positions_long") - pl.col("positions_short")).alias(f"{group}_net"))
        out = out.join(g, on=["root", "as_of_date"], how="left")
    return out.sort("root", "as_of_date")


def known_at(reports: pl.DataFrame, days: Iterable) -> pl.DataFrame:
    """For every root in ``reports`` and every date in ``days``: the latest report whose
    ``release_date`` is before that date, and ``age_days`` (date minus the report's as-of date).

    ``reports`` holds one row per root and as-of date (``wide`` output, or one trader group). A date
    before the first release has nulls. A long ``age_days`` means the CFTC published nothing for a
    while (a shutdown); whether to trade on it is the study's rule."""
    if reports.select("root", "as_of_date").is_duplicated().any():
        raise ValueError("known_at needs one row per root and as-of date: use wide(), or filter one trader group")
    d = pl.DataFrame({"day": pl.Series(list(days)).cast(pl.Date)}).unique().sort("day")
    left = (d.join(reports.select(pl.col("root").unique()), how="cross")
             .with_columns(cutoff=pl.col("day") - pl.duration(days=1)).sort("cutoff"))
    # Both sides are sorted on their keys. Two reports can share a release day (a catch-up); the later
    # as-of date then wins.
    right = reports.sort("release_date", "as_of_date")
    out = left.join_asof(right, left_on="cutoff", right_on="release_date", by="root", strategy="backward",
                         check_sortedness=False)
    return out.drop("cutoff").with_columns(age_days=(pl.col("day") - pl.col("as_of_date")).dt.total_days()).sort(
        "root", "day")
