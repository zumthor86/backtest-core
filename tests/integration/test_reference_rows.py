"""xs, events and futures_book must reproduce register rows on record, every printed number.

Rows 107, 110, 112 (stock sorts, `lit_refs_sweep`), 106 (time-series momentum, `lit_refs_sweep`), 111 (pre-FOMC, same),
117 (announcement days, `announcement_days`) and 114 (carry, `futures_carry`). The data loaders and the signals come
from the study folders, unchanged; the books come from this library. Skipped where the studies or the data are absent.
Run in the Hephaestus venv.
"""
from __future__ import annotations

import re
import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from backtest_core import events, futures_book, scoring, sim, xs

STUDIES = Path("C:/Users/Christopher/Documents/python/Hephaestus/backtests")
SPLIT = np.datetime64("2020-01-01")

pytestmark = pytest.mark.skipif(not (STUDIES / "lit_refs_sweep" / "sweep.py").exists(), reason="needs Hephaestus")


def _study(name: str, module: str):
    sys.path.insert(0, str(STUDIES / name))
    try:
        return __import__(module)
    except (ImportError, KeyError) as exc:          # dotenv or a data path missing
        pytest.skip(f"{name}: {exc}")


def _printed(path: Path, label: str) -> dict:
    line = next(x for x in path.read_text(encoding="utf-8").splitlines() if x.strip().startswith(label))
    nums = dict(re.findall(r"(net Sharpe|block t|CAGR|max DD|gross Sharpe) ([+-]?[\d.]+)%?", line))
    span = re.search(r"(\d{4}-\d\d-\d\d) \.\. (\d{4}-\d\d-\d\d)", line)
    return {"line": line, **{k: float(v) for k, v in nums.items()}, "first": span.group(1), "last": span.group(2)}


def _assert_daily(s: scoring.Daily, want: dict):
    assert str(s.first) == want["first"] and str(s.last) == want["last"], want["line"]
    assert round(s.sharpe, 2) == want["net Sharpe"], want["line"]
    assert round(s.block_t, 2) == want["block t"], want["line"]
    assert round(s.cagr * 100, 1) == want["CAGR"], want["line"]
    assert round(s.max_dd * 100, 1) == want["max DD"], want["line"]
    if "gross Sharpe" in want:
        assert round(s.gross_sharpe, 2) == want["gross Sharpe"], want["line"]


@pytest.fixture(scope="module")
def sweep():
    return _study("lit_refs_sweep", "sweep")


@pytest.fixture(scope="module")
def panel(sweep):
    return sweep.stock_panel()


RESULTS_SWEEP = STUDIES / "lit_refs_sweep" / "results_insample.txt"


def _sort(panel, sig, **kw):
    days, net, gross = xs.sort_book(panel, sig, start=np.datetime64("2004-12-31"), **kw)
    return scoring.daily(days, net, gross, days < SPLIT)


def test_row_107_momentum(panel):
    me, ac = panel["me"], panel["ac"]
    s = _sort(panel, lambda k: xs.trailing_return(ac, me, k, 1, 12))
    _assert_daily(s, _printed(RESULTS_SWEEP, "H4 "))


def test_row_110_seasonality(panel):
    ac, me = panel["ac"], panel["me"]
    with np.errstate(invalid="ignore", divide="ignore"):
        mret = np.vstack([np.full((1, panel["N"]), np.nan), ac[me[1:]] / ac[me[:-1]] - 1])

    def sig(k):
        lags = [k + 1 - 12 * y for y in range(1, 6)]
        if lags[-1] < 1:
            return None
        x = mret[lags]
        cnt = np.isfinite(x).sum(axis=0)
        with np.errstate(invalid="ignore"):
            m = np.nansum(x, axis=0) / np.maximum(cnt, 1)
        m[cnt < 3] = np.nan
        return m
    _assert_daily(_sort(panel, sig), _printed(RESULTS_SWEEP, "H7 "))


def test_row_112_betting_against_beta(sweep, panel):
    # The study's H9 builds its signal, leverage and risk-free leg inside one function; it is rerun through the
    # library by swapping its monthly_ls for xs.sort_book (same arguments).
    orig = sweep.monthly_ls
    sweep.monthly_ls = lambda S, sig, lev=None, rf=None: xs.sort_book(S, sig, lev=lev, rf=rf,
                                                                      start=np.datetime64("2004-12-31"))
    try:
        days, net, gross = sweep.h9(panel)
    finally:
        sweep.monthly_ls = orig
    _assert_daily(scoring.daily(days, net, gross, days < SPLIT), _printed(RESULTS_SWEEP, "H9 "))


def test_row_106_time_series_momentum(sweep):
    from backtest_core import bars

    mk = {}
    for sym in sweep.FUTURES:
        d = bars.daily(sym, "databento", "1h")
        mk[sym] = futures_book.market(d["session"].to_numpy().astype("datetime64[D]"), d["close"].to_numpy())
    days, net, gross = futures_book.time_series_book(mk, futures_book.trailing_sign)
    _assert_daily(scoring.daily(days, net, gross, days < SPLIT), _printed(RESULTS_SWEEP, "H3 "))


def test_row_111_pre_fomc(sweep):
    a = sweep.marks("ES", 14, 0, "open").sort("d")
    b = sweep.marks("ES", 12, 0, "open").sort("d")
    exit_px = dict(zip(b["d"].to_list(), b["px"].to_list()))
    raw = a["raw"].to_numpy()
    days, net, gross = events.mark_to_mark([date.fromisoformat(s) for s in sweep.FOMC], a["d"].to_list(),
                                           a["px"].to_numpy(), exit_px,
                                           cost=lambda i: sim.cost_fraction(raw[i], 0.25, 12.50))
    p = scoring.per_trade(days, net, gross, days < SPLIT)
    line = next(x for x in RESULTS_SWEEP.read_text(encoding="utf-8").splitlines() if x.startswith("H8 "))
    want = re.search(r"(\d+) trades, net mean ([+-][\d.]+) bps \(t ([+-][\d.]+)\), gross mean ([+-][\d.]+) bps, win (\d+)%", line)
    assert (p.trades, round(p.mean * 1e4, 1), round(p.t, 2), round(p.gross_mean * 1e4, 1), round(p.win * 100)) == (
        int(want.group(1)), float(want.group(2)), float(want.group(3)), float(want.group(4)), int(want.group(5))), line


def test_row_117_announcement_days():
    ann = _study("announcement_days", "announce")
    d = ann.closes("ES")
    days = d["d"].to_numpy().astype("datetime64[D]")
    c, raw = d["close"].to_numpy(), d["raw"].to_numpy()
    r = np.concatenate([[0.0], c[1:] / c[:-1] - 1])
    sched = ann.schedule()
    flag = events.flag_days(days, [x for k in ("jobs", "cpi", "fomc") for x in sched[k]])
    entry_cost = np.zeros(len(days))
    entry_cost[1:] = sim.cost_fraction(raw[:-1], 0.25, 12.50)          # bought at the prior close
    gross, net, _ = events.hold_flagged(r, flag, entry_cost)
    lo, hi = ann.WINDOWS["insample"]
    m = (days >= np.datetime64(lo)) & (days <= np.datetime64(hi))
    m[0] = False
    s = scoring.daily(days, net, gross, m)
    path = STUDIES / "announcement_days" / "results_insample.txt"
    want = _printed(path, "ES, all three releases")
    want.pop("gross Sharpe", None)
    _assert_daily(s, want)
    trades = int((m & (gross - net > 0)).sum())
    w = events.welch_t(r[m][flag[m]], r[m][~flag[m]])
    assert trades == int(re.search(r"in (\d+) trades", want["line"]).group(1))
    assert round(w, 2) == float(re.search(r"Welch t ([+-][\d.]+)", want["line"]).group(1))


def test_row_114_carry():
    carry = _study("futures_carry", "carry")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        data = {s: carry.market(s) for s in carry.MARKETS}
    mk = {s: {"ses": v["ses"], "r": v["r"], "months": v["months"]} for s, v in data.items()}
    scores = {s: {mo: (raw / sig, sig) for mo, (raw, sig) in v["carry"].items()} for s, v in data.items()}
    days, net, gross = futures_book.cross_section_book(mk, scores, names=carry.MARKETS)
    path = STUDIES / "futures_carry" / "results_insample.txt"
    _assert_daily(scoring.daily(days, net, gross, days < SPLIT), _printed(path, "Ranked carry book"))
