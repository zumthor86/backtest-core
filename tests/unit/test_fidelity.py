import numpy as np
import pytest

from backtest_core import fidelity


def _days(n=1200):
    return np.arange(np.datetime64("2010-01-01"), np.datetime64("2010-01-01") + n).astype("datetime64[D]")


def test_to_monthly_compounds_within_each_month():
    days = np.array(["2020-01-30", "2020-01-31", "2020-02-03"], dtype="datetime64[D]")
    m, r = fidelity.to_monthly(days, np.array([0.1, 0.1, 0.05]))
    assert m.tolist() == [np.datetime64("2020-01"), np.datetime64("2020-02")]
    assert r == pytest.approx([0.21, 0.05])


def test_a_faithful_build_passes_and_a_wrong_one_does_not():
    rng = np.random.default_rng(0)
    days = _days()
    daily = rng.normal(0, 0.01, len(days))
    months, pub = fidelity.to_monthly(days, daily)
    good = fidelity.compare(days, daily + rng.normal(0, 0.001, len(days)), months, pub)
    bad = fidelity.compare(days, rng.normal(0, 0.01, len(days)), months, pub)
    assert fidelity.verdict(good, 0.7) == "fit" and good.corr > 0.95 and good.beta == pytest.approx(1.0, abs=0.1)
    assert fidelity.verdict(bad, 0.7) == "uninformative"


def test_too_few_common_months_refuses():
    days = _days(200)
    m, r = fidelity.to_monthly(days, np.zeros(len(days)))
    with pytest.raises(ValueError):
        fidelity.compare(days, np.zeros(len(days)), m, r)
