"""cot.known_at and cot.wide on made-up reports, and futures_book.dated_book (no database)."""
from datetime import date

import numpy as np
import polars as pl
import pytest

from backtest_core import cot, futures_book


def _reports(rows):
    return pl.DataFrame(rows, schema={"root": pl.Utf8, "as_of_date": pl.Date, "release_date": pl.Date,
                                      "commercial_net": pl.Int64}, orient="row")


def test_a_friday_release_is_not_seen_on_friday_but_is_on_monday():
    r = _reports([("CL", date(2026, 10, 6), date(2026, 10, 9), 5)])
    k = cot.known_at(r, [date(2026, 10, 9), date(2026, 10, 12)])
    assert k["as_of_date"].to_list() == [None, date(2026, 10, 6)]
    assert k["age_days"].to_list() == [None, 6]


def test_the_latest_released_report_wins_and_a_catch_up_tie_takes_the_later_week():
    r = _reports([
        ("CL", date(2013, 9, 24), date(2013, 9, 27), 1),
        ("CL", date(2013, 10, 8), date(2013, 11, 1), 2),      # two reports out on one day (2013 catch-up)
        ("CL", date(2013, 10, 15), date(2013, 11, 1), 3),
    ])
    k = cot.known_at(r, [date(2013, 10, 30), date(2013, 11, 4)])
    assert k["commercial_net"].to_list() == [1, 3]
    assert k["age_days"].to_list() == [36, 20]


def test_each_root_gets_its_own_reports():
    r = _reports([("CL", date(2026, 10, 6), date(2026, 10, 9), 5), ("GC", date(2026, 9, 29), date(2026, 10, 2), 7)])
    k = cot.known_at(r, [date(2026, 10, 12)])
    assert dict(zip(k["root"], k["commercial_net"])) == {"CL": 5, "GC": 7}


def test_known_at_refuses_one_row_per_trader_group():
    r = _reports([("CL", date(2026, 10, 6), date(2026, 10, 9), 5), ("CL", date(2026, 10, 6), date(2026, 10, 9), 6)])
    with pytest.raises(ValueError, match="one row per root"):
        cot.known_at(r, [date(2026, 10, 12)])


def test_wide_gives_net_positions_per_group():
    rows = pl.DataFrame({
        "root": ["CL"] * 2, "as_of_date": [date(2026, 10, 6)] * 2, "release_date": [date(2026, 10, 9)] * 2,
        "release_basis": ["rule"] * 2, "open_interest": [100] * 2, "trader_group": ["commercial", "noncommercial"],
        "positions_long": [50, 30], "positions_short": [60, 25], "positions_spread": [None, 5]})
    w = cot.wide(rows)
    assert w.height == 1
    assert (w["commercial_net"].item(), w["noncommercial_net"].item()) == (-10, 5)
    assert w["noncommercial_spread"].item() == 5


def _market(n=400, seed=2):
    rng = np.random.default_rng(seed)
    ses = np.arange(np.datetime64("2019-01-01"), np.datetime64("2019-01-01") + n).astype("datetime64[D]")
    return futures_book.market(ses, 100 * np.cumprod(1 + 0.001 + rng.normal(0, 0.01, n)))


def test_dated_book_on_month_ends_is_cross_section_book():
    mk = {s: _market(seed=i) for i, s in enumerate("ABCDE")}
    ses = mk["A"]["ses"]
    ends = futures_book.month_ends(ses)
    rng = np.random.default_rng(9)
    by_month = {s: {} for s in mk}
    by_day = {s: {} for s in mk}
    for e in ends[2:]:
        for s in mk:
            x = (float(rng.normal()), 0.1 + rng.random())
            by_month[s][ses[e].astype("datetime64[M]")] = x
            by_day[s][ses[e]] = x
    a = futures_book.cross_section_book(mk, by_month)
    b = futures_book.dated_book(mk, by_day, np.append(ses[ends[2:]], ses[-1]))
    for x, y in zip(a, b, strict=True):
        assert np.array_equal(x, y) if x.dtype.kind == "M" else np.allclose(x, y)


def test_dated_book_holds_until_the_next_date_and_charges_each_change():
    mk = {s: _market(seed=i) for i, s in enumerate("ABCD")}
    ses = mk["A"]["ses"]
    dates = ses[[100, 107, 114]]
    scores = {s: {dates[0]: (float(i), 0.2), dates[1]: (float(i), 0.2)} for i, s in enumerate("ABCD")}
    days, net, gross = futures_book.dated_book(mk, scores, dates)
    assert days[0] == ses[101] and days[-1] == ses[114] and len(days) == 14
    assert gross[0] - net[0] > 0                       # the first formation builds the book
    assert gross[7] - net[7] == pytest.approx(0.0)     # same weights a week later: no cost
