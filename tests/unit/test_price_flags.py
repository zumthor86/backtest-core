import numpy as np
import polars as pl

from backtest_core import price_flags as pf


def _days(n):
    return np.datetime64("2020-01-01") + np.arange(n)


def _flags(*columns):
    prices = np.array(columns, dtype=float).T
    codes = [f"C{i}" for i in range(prices.shape[1])]
    return pf.detect(_days(prices.shape[0]), codes, prices), prices, codes


def test_a_one_day_spike_is_flagged_and_a_jump_that_holds_is_not():
    spike = [10.0, 10.1, 0.002, 10.2, 10.3]          # a bad tick: gone the next day
    real = [10.0, 10.1, 45.0, 46.0, 44.0]            # a real move: still there
    crash = [10.0, 10.1, 1.0, 1.1, 1.0]              # a real collapse: still there
    f, *_ = _flags(spike, real, crash)
    assert f.filter(pl.col("reason") == "spike")["code"].to_list() == ["C0"]
    assert f.filter(pl.col("reason") == "spike")["date"].to_list() == [np.datetime64("2020-01-03")]


def test_a_long_run_of_the_same_close_is_flagged_after_its_first_print_but_a_short_one_is_not():
    flat = [5.0, 6.0] + [7.0] * 10 + [8.0]           # ten sessions at 7.0: nine repeats flagged
    short = [5.0, 6.0] + [7.0] * 4 + [8.0] * 8       # a quiet stock: runs of 4 and 8
    f, *_ = _flags(flat, short)
    s = f.filter(pl.col("reason") == "stale")
    assert s["code"].unique().to_list() == ["C0"] and s.height == 9
    assert np.datetime64("2020-01-03") not in s["date"].to_numpy()          # the first 7.0 is a real print


def test_a_scale_break_is_flagged_and_the_restated_price_chain_has_no_jump():
    broke = [10.0, 10.2, 10.1, 1010.0, 1020.0, 1030.0]       # the file moves to 100x and stays
    f, prices, _ = _flags(broke)
    assert f["reason"].to_list() == ["scale_break"]
    codes = np.array(["C0"])
    out, ret_mask = pf.apply(prices, _days(6), codes, f)
    assert ret_mask[:, 0].tolist() == [False, False, False, True, False, False]
    assert out[5, 0] / out[0, 0] < 1.2                       # not 103x
    assert np.isclose(out[1, 0] / out[0, 0], 10.2 / 10.0)    # moves before the break are untouched


def test_the_move_a_blanked_spike_hid_is_still_seen_across_the_gap():
    p = np.array([[10.0], [10.0], [0.002], [12.0]])          # spike on day 2, the real move is 10 -> 12
    f = pf.detect(_days(4), ["C0"], p)
    out, _ = pf.apply(p, _days(4), np.array(["C0"]), f)
    assert np.isnan(out[2, 0]) and np.isclose(out[3, 0] / out[1, 0], 1.2)


def test_flags_older_than_the_store_are_refused(tmp_path):
    store = tmp_path / "research_prices"
    store.mkdir()
    path = pf.flags_path(store)
    path.parent.mkdir()
    pl.DataFrame(schema=pf.SCHEMA).write_parquet(path)
    path.with_name("built.json").write_text('{"built_through": "2020-01-10"}')
    assert pf.read(store, np.datetime64("2020-01-10")).is_empty()
    try:
        pf.read(store, np.datetime64("2020-01-11"))
    except LookupError:
        pass
    else:
        raise AssertionError("stale flags were accepted")
