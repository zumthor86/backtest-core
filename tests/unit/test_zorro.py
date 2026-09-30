import polars as pl
import pytest

from backtest_core.zorro import battery, export, parity, report

REPORT = """Test DipBuyNQ NQ, Zorro 3.112

Test period         2011-03-31..2026-09-18 (3983 bars)
Max drawdown        -171536$ 13.2% (MAE -174989$)
Number of trades    125 (9/year)
Percent winning     80.0%
Annual growth rate  2.29% (ROI 2.71%)
Profit factor       3.97 (PRR 2.98)
Sharpe ratio        1.09 (Sortino 1.24)
Sample cycles ProF  1.61 2.31 1.80

 50% Confidence     8% 183649 1080683$
 95% Confidence     7% 306934 1134975$
100% Confidence     7% 504531 1221994$
"""


def test_report_parses_headline_numbers_and_monte_carlo_table():
    r = report.parse(REPORT, "DipBuyNQ")
    assert (r.sharpe, r.profit_factor, r.trades) == (1.09, 3.97, 125)
    assert r.win_rate == pytest.approx(0.80) and r.annual_growth == pytest.approx(0.0229)
    assert r.max_dd_usd == -171536 and r.test_period == "2011-03-31..2026-09-18"
    assert r.sample_cycle_pf == [1.61, 2.31, 1.80]
    assert r.monte_carlo["confidence"].to_list() == [50, 95, 100]
    assert r.monte_carlo["max_dd_usd"].to_list() == [183649, 306934, 504531]


def test_report_missing_fields_are_none_not_zero():
    r = report.parse("Test X\n", "X")
    assert r.sharpe is None and r.trades is None and r.monte_carlo is None


def test_parity_exact_and_mismatch():
    z = pl.DataFrame({"entry": [1, 2, 3], "px": [10.0, 20.0, 30.0]})
    assert parity.compare(z, z.clone(), ["entry"], ["px"]).exact
    p = parity.compare(z, pl.DataFrame({"entry": [1, 2, 4], "px": [10.0, 20.1, 40.0]}), ["entry"], ["px"])
    assert not p.exact
    assert p.only_zorro["entry"].to_list() == [3] and p.only_python["entry"].to_list() == [4]
    assert p.value_mismatches["entry"].to_list() == [2]


def test_mrc_p_counts_shuffled_runs_at_or_above_the_original(tmp_path):
    f = tmp_path / "X_mrc.csv"
    f.write_text("1,2.0,1,1,10\n2,1.0,1,1,10\n3,2.0,1,1,10\n4,3.0,1,1,10\n5,1.5,1,1,10\n", encoding="utf-8")
    pf, p, n = battery.mrc_result(f)
    assert (pf, n) == (2.0, 5) and p == pytest.approx(2 / 4)


def test_battery_verdicts_use_default_bars():
    b = battery.Battery("X", close_times=[0.6, 0.4], detrend_trades=0.31, mrc_p=0.06, costs_x2=0.1)
    assert b.verdicts() == {"close_avg": True, "detrend_trades": True, "mrc_p": False, "costs_x2": True}
    assert b.verdicts({"close_avg": 0.6})["close_avg"] is False


def test_asset_row_defines_one_unit_as_one_point():
    assert export.asset_row("NQ", 20000) == "NQ,20000,0,0,0,0.0001,0.0001,-100,0,1,0,NQ"
