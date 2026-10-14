"""xs, events, futures_book and scoring on small made-up data."""
from datetime import date

import numpy as np
import pytest

from backtest_core import events, futures_book, scoring, xs


def _panel(T=80, N=20, seed=1):
    rng = np.random.default_rng(seed)
    days = np.arange(np.datetime64("2020-01-01"), np.datetime64("2020-01-01") + T).astype("datetime64[D]")
    ret = rng.normal(0, 0.01, (T, N))
    ac = np.cumprod(1 + ret, axis=0)
    return {"days": days, "ret": ret, "ac": ac, "mem": np.ones((T, N), bool), "me": xs.month_ends(days)}


def test_sort_book_longs_the_top_and_charges_a_full_rebuild_first():
    P = _panel()
    sig = np.arange(20, dtype=float)          # stock 19 is the top, stock 0 the bottom
    days, net, gross = xs.sort_book(P, lambda k: sig, quantile=5, min_names=10, side=0.001, borrow=0.0)
    t0 = P["me"][0] + 1
    assert days[0] == P["days"][t0]
    long_ = P["ret"][t0, 16:20].mean()
    short = P["ret"][t0, 0:4].mean()
    assert gross[0] == pytest.approx(long_ - short)
    assert net[0] == pytest.approx(gross[0] - 0.001 * 4)       # turnover 2 per leg
    nxt = P["me"][1] + 1 - t0
    assert gross[nxt] - net[nxt] == pytest.approx(0.0)          # same names: no cost at the next formation


def test_sort_book_refuses_when_nothing_is_held():
    with pytest.raises(ValueError):
        xs.sort_book(_panel(), lambda k: None)


def test_trailing_return():
    ac = np.array([[1.0], [2.0], [4.0]])
    assert xs.trailing_return(ac, np.array([0, 1, 2]), 2, 1, 2)[0] == pytest.approx(1.0)
    assert xs.trailing_return(ac, np.array([0, 1, 2]), 1, 1, 2) is None


def test_flag_days_moves_a_holiday_forward_and_hold_charges_each_run_once():
    days = np.array(["2024-01-02", "2024-01-03", "2024-01-05", "2024-01-08"], dtype="datetime64[D]")
    flag = events.flag_days(days, [date(2024, 1, 4), date(2024, 1, 5), date(2024, 1, 8)])
    assert flag.tolist() == [False, False, True, True]
    r = np.array([0.0, 0.01, 0.02, -0.01])
    gross, net, trades = events.hold_flagged(r, flag, np.full(4, 0.001))
    assert trades == 1 and gross.tolist() == [0.0, 0.0, 0.02, -0.01]
    assert net[2] == pytest.approx(0.019) and net[3] == pytest.approx(-0.01)


def test_mark_to_mark_skips_a_stale_entry():
    entry_days = [date(2024, 1, 2), date(2024, 1, 20)]
    out = events.mark_to_mark([date(2024, 1, 3), date(2024, 1, 30)], entry_days, np.array([100.0, 100.0]),
                              {date(2024, 1, 3): 101.0, date(2024, 1, 30): 99.0}, cost=lambda i: 0.001)
    days, net, gross = out
    assert list(days) == [np.datetime64("2024-01-03")]          # the 2024-01-30 entry is 10 days old
    assert gross[0] == pytest.approx(0.01) and net[0] == pytest.approx(0.009)


def test_cohort_book_holds_each_selection_for_the_span():
    w = np.zeros((10, 1))
    w[0, 0] = 1.0
    p = events.cohort_book(w, np.zeros((10, 1)), hold=3, lag=2)
    assert p[:, 0].tolist() == [0, 0, 1 / 3, 1 / 3, 1 / 3, 0, 0, 0, 0, 0]


def test_check_dates_refuses_a_list_with_no_bigger_move():
    r = np.r_[np.full(50, 0.01), np.full(50, -0.01)]
    flag = np.zeros(100, bool)
    flag[::10] = True
    with pytest.raises(ValueError):
        events.check_dates(r, flag, min_ratio=1.2)


def _market(n=400, drift=0.001, seed=2):
    rng = np.random.default_rng(seed)
    ses = np.arange(np.datetime64("2019-01-01"), np.datetime64("2019-01-01") + n).astype("datetime64[D]")
    return futures_book.market(ses, 100 * np.cumprod(1 + drift + rng.normal(0, 0.01, n)))


def test_ewma_sigma_matches_its_recursion():
    r = np.r_[0.0, np.full(99, 0.01)]
    s = futures_book.ewma_sigma(r, com=60)
    # The seed is the variance of a constant run, 0; the weight of the new squares then builds up.
    assert s[50] == pytest.approx(np.sqrt(252 * (1 - (60 / 61) ** 50) * 1e-4))


def test_time_series_book_is_long_a_rising_market():
    m = {"A": _market(drift=0.003)}
    days, net, gross = futures_book.time_series_book(m, futures_book.trailing_sign, min_history=252)
    assert len(days) > 0 and gross.sum() > 0
    assert np.all(net <= gross + 1e-12)


def test_cross_section_book_ranks_and_scales():
    mk = {s: _market(seed=i) for i, s in enumerate("ABCD")}
    mo = mk["A"]["months"][300]
    scores = {s: {mo: (float(i), 0.2)} for i, s in enumerate("ABCD")}
    days, net, gross = futures_book.cross_section_book(mk, scores)
    hold = mk["A"]["months"] == mo + 1
    expect = sum(((i + 1) - 2.5) / 2 * 0.40 / 0.2 * mk[s]["r"][hold] / 4 for i, s in enumerate("ABCD"))
    assert gross == pytest.approx(expect)


def test_scoring_daily_and_per_trade():
    days = np.arange(np.datetime64("2020-01-01"), np.datetime64("2020-01-01") + 300).astype("datetime64[D]")
    net = np.random.default_rng(3).normal(0.001, 0.01, 300)
    s = scoring.daily(days, net, sharpe_bar=0.7, t_bar=2.5)
    assert s.first == days[0] and s.passed in (True, False) and "net Sharpe" in s.line("x")
    p = scoring.per_trade(days, net, t_bar=2.0)
    assert p.trades == 300 and p.t == pytest.approx(net.mean() / (net.std(ddof=1) / np.sqrt(300)))
