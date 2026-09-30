from datetime import date, timedelta

import numpy as np
import pytest

from backtest_core import stats


def test_sharpe_uses_population_std_and_252_periods():
    r = np.array([0.01, -0.005, 0.02, 0.0])
    assert stats.sharpe(r) == pytest.approx(r.mean() / r.std(ddof=0) * np.sqrt(252))


def test_sharpe_ignores_nan_and_returns_nan_on_flat_series():
    assert np.isnan(stats.sharpe([0.01, 0.01, 0.01]))
    assert stats.sharpe([0.01, np.nan, -0.01, 0.02]) == pytest.approx(stats.sharpe([0.01, -0.01, 0.02]))


def test_nw_t_with_zero_lags_is_the_plain_t_on_population_variance():
    x = np.array([0.3, -0.1, 0.4, 0.2, -0.2, 0.5])
    plain = x.mean() / np.sqrt(x.var() / len(x))
    assert stats.nw_t(x, lags=0) == pytest.approx(plain)


def test_nw_t_matches_the_frozen_study_formula():
    rng = np.random.default_rng(7)
    x = rng.normal(0.001, 0.01, 500)
    n, u = len(x), x - x.mean()
    v = u @ u / n
    for L in range(1, 6):
        v += 2 * (1 - L / 6) * (u[L:] @ u[:-L]) / n
    assert stats.nw_t(x, 5) == pytest.approx(x.mean() / np.sqrt(v / n))


def test_block_t_clusters_by_calendar_blocks():
    d0 = date(2020, 1, 1)
    dates = [d0 + timedelta(days=i) for i in range(63)]
    x = np.r_[np.full(21, 1.0), np.full(21, 2.0), np.full(21, 3.0)]
    t, nb = stats.block_t(x, dates, 21)
    assert nb == 3
    assert t == pytest.approx(2.0 / (1.0 / np.sqrt(3)))


def test_max_drawdown_and_cagr():
    r = np.array([0.10, -0.50, 0.20])
    assert stats.max_drawdown(r) == pytest.approx(-0.5)
    assert stats.cagr(np.full(252, 0.001)) == pytest.approx(1.001 ** 252 - 1)


def test_vol_matched_diff_is_zero_for_a_rescaled_copy():
    rng = np.random.default_rng(1)
    base = rng.normal(0, 0.01, 300)
    mean, _ = stats.vol_matched_diff(3 * base, base)
    assert mean == pytest.approx(0.0, abs=1e-12)


def test_summary_line_mentions_trades_only_when_there_are_some():
    s = stats.summary(np.array([0.01, -0.01, 0.02]), trades=np.array([0.05, -0.02]))
    assert s.n_trades == 2 and s.win_rate == 0.5
    assert "trades" in s.line()
    assert "trades" not in stats.summary(np.array([0.01, -0.01, 0.02])).line()
