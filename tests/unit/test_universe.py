from datetime import date, datetime, timezone

import numpy as np
import polars as pl

from backtest_core import universe

DAYS = np.array(["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-04", "2020-03-02"], dtype="datetime64[D]")


def _stays():
    return pl.DataFrame({
        "symbol": ["AAA", "THOR", "THOR"],
        "first_date": [date(2019, 1, 31), date(2009, 1, 30), date(2019, 6, 28)],
        "last_date": [date(2020, 2, 28), date(2015, 6, 30), date(2020, 2, 28)],
    })


def test_a_day_carries_the_latest_snapshot_on_or_before_it():
    snaps = pl.DataFrame({"symbol": ["AAA", "AAA"], "as_of_date": [date(2020, 1, 31), date(2020, 2, 28)],
                          "weight_pct": [0.5, 0.7]})
    mem, weight = universe.membership_matrix(DAYS, snaps, _stays())
    assert mem[:, 0].tolist() == [False, True, True, True, True]      # nothing before the first snapshot
    assert weight[1, 0] == 0.5 and weight[4, 0] == 0.7
    assert np.isnan(weight[0, 0])


def test_a_member_that_left_is_out_from_the_next_snapshot():
    snaps = pl.DataFrame({"symbol": ["AAA", "THOR", "THOR"],
                          "as_of_date": [date(2020, 1, 31), date(2020, 1, 31), date(2020, 2, 28)],
                          "weight_pct": [0.5, 0.1, 0.1]})
    mem, _ = universe.membership_matrix(DAYS, snaps, _stays())
    assert mem[3, 0] and not mem[4, 0]


def test_a_reused_ticker_lands_in_the_stay_that_covers_the_snapshot_date():
    snaps = pl.DataFrame({"symbol": ["THOR"], "as_of_date": [date(2020, 1, 31)], "weight_pct": [0.1]})
    mem, _ = universe.membership_matrix(DAYS, snaps, _stays())
    assert not mem[:, 1].any()            # the 2009-2015 company
    assert mem[1:, 2].all()               # the 2019-2020 company


def _stamps(*utc):
    return pl.Series([datetime(*t, tzinfo=timezone.utc) for t in utc]).cast(pl.Datetime("us", "UTC"))


def test_a_notice_before_the_close_trades_that_day_and_one_after_it_the_next_session():
    # 2020-01-31 is a Friday. 20:59 UTC is 15:59 in New York (winter); 21:01 UTC is 16:01.
    i, ny = universe.first_session(DAYS, _stamps((2020, 1, 31, 20, 59), (2020, 1, 31, 21, 1), (2020, 1, 31, 12, 0)))
    assert i.tolist() == [1, 2, 1]
    assert ny.dt.hour().to_list() == [15, 16, 7]


def test_a_notice_on_a_day_the_market_is_shut_trades_the_next_session_once():
    # Saturday 2020-02-01, late in the evening: Monday, not Tuesday.
    i, _ = universe.first_session(DAYS, _stamps((2020, 2, 1, 23, 0)))
    assert i.tolist() == [2]


def test_summer_time_moves_the_close_to_twenty_hundred_utc():
    days = np.array(["2020-07-01", "2020-07-02"], dtype="datetime64[D]")
    i, _ = universe.first_session(days, _stamps((2020, 7, 1, 19, 59), (2020, 7, 1, 20, 1)))
    assert i.tolist() == [0, 1]
