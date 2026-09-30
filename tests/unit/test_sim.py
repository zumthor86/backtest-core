import numpy as np
import pytest

from backtest_core import sim

C = np.array([100.0, 100.0, 90.0, 99.0, 108.9, 108.9])
O = np.array([100.0, 100.0, 95.0, 90.0, 99.0, 108.9])
ENTER = np.array([0, 0, 1, 0, 0, 0], bool)
EXIT = np.array([0, 0, 0, 0, 1, 0], bool)
VALID = np.ones(6, bool)


def test_close_fill_earns_close_to_close_after_the_entry_bar():
    r = sim.run(O, C, ENTER, EXIT, VALID, cost_rt=0.0)
    assert list(r.entries) == [2] and list(r.exits) == [4]
    assert r.returns[3] == pytest.approx(0.10) and r.returns[4] == pytest.approx(0.10)
    assert r.trades[0] == pytest.approx(108.9 / 90 - 1)


def test_costs_are_split_half_at_entry_and_half_at_exit():
    r = sim.run(O, C, ENTER, EXIT, VALID, cost_rt=0.002)
    assert r.returns[2] == pytest.approx(-0.001)
    assert r.returns[4] == pytest.approx(0.10 - 0.001)
    assert r.trades[0] == pytest.approx(108.9 / 90 - 1 - 0.002)


def test_open_fill_enters_and_exits_at_the_next_open():
    r = sim.run(O, C, ENTER, EXIT, VALID, cost_rt=0.0, fill="open")
    assert list(r.entries) == [3] and list(r.exits) == [5]
    assert r.returns[3] == pytest.approx(99 / 90 - 1)
    assert r.trades[0] == pytest.approx(108.9 / 90 - 1)


def test_short_side_flips_the_sign():
    r = sim.run(O, C, ENTER, EXIT, VALID, cost_rt=0.0, side=-1)
    assert r.trades[0] == pytest.approx(-(108.9 / 90 - 1))


def test_signals_are_ignored_during_warm_up_and_returns_start_at_the_first_valid_bar():
    valid = np.array([0, 0, 0, 1, 1, 1], bool)
    r = sim.run(O, C, ENTER, EXIT, valid, cost_rt=0.0)
    assert r.start == 3 and len(r.trades) == 0 and len(r.returns) == 3


def test_cost_fraction_charges_on_the_raw_price():
    assert sim.cost_fraction(5000.0, 0.25, 12.5) == pytest.approx((2 * 0.25 + 4.5 * 0.25 / 12.5) / 5000)
