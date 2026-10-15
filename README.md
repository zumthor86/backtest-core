# backtest-core

Shared research code for **bar strategies** — futures, ETFs, single stocks, FX. Options research stays in
Hephaestus (`processing/backtest/`, the `backtest-agent`). Sibling to `ingest-core` (acquisition) and `store-core`
(storage): this library owns neither; it reads bars through `store-core` and holds the statistics, the
pre-registration helper, the stage-1 simulator and (planned) the Zorro toolkit.

## The standard path a strategy takes

1. **Pre-register** — rules, markets, in-sample / holdout dates and pass bars in a markdown file, hashed with
   `prereg.register` before anything runs.
2. **Quick test in Python** — `bars` + `sim` + `stats`, in-sample only.
3. **Port to Zorro**, 4. **reconcile** trade by trade, 5. **robustness battery** in Zorro,
   6. **holdout** once (`prereg.spend_holdout`), 7. portfolio fit, 8. paper then live.

Zorro is the engine from step 3 on. See `Hephaestus/.claude/skills/bar-backtest-agent/references/`.

## Contents

| Module | Purpose |
|---|---|
| `backtest_core.stats` | `sharpe`, `iid_t`, `nw_t` (Newey-West), `block_t` (calendar-block clusters), `cagr`, `max_drawdown`, `vol_matched_diff`, `summary`, `halves`. Conventions match the frozen studies (population std, 252 days) |
| `backtest_core.prereg` | `register` / `verify` a spec against a `sha256sum`-format ledger (`spec.sha256`); `spend_holdout` refuses a second run and refuses rules edited since registration |
| `backtest_core.bars` | `intraday(symbol, source, freq)` and `daily(...)` (one bar per session, 18:00 ET futures split) through `store_core.BarStore` (`BARS_DIR`) |
| `backtest_core.universe` | `panel(index)`: days x stays matrices (`ac`, `op` adjusted open, `ret`, `has`, `mem`, `weight`) for Russell 3000 or S&P 500 members since 2007, delisted companies included; `earnings(panel)`: SEC earnings notices as (column, first session that could react). Needs `HERMES_DB_URL` and `RESEARCH_PRICES_DIR` |
| `backtest_core.price_flags` | `build` (CLI: `python -m backtest_core.price_flags build`) writes flags beside the Hermes price store (`HERMES_PRICES_DIR`), one row per bad price: `spike`, `stale`, `scale_break`; `universe.panel` reads them and blanks those days, restating each code on one price scale. The price files are never edited. `panel` raises if the flags are missing or older than the store |
| `backtest_core.xs` | `sort_book(panel, signal, quantile, form, lev, rf, side, borrow, start, min_names)`: quantile long-short on a member panel, any formation schedule, leverage per leg and a risk-free leg; `month_ends`, `trailing_return`. Reproduces register rows 107, 110, 112 |
| `backtest_core.events` | `flag_days`, `hold_flagged` (long on event days, one trade per run, row 117), `mark_to_mark` (entry mark before the event to the exit mark on it, row 111), `cohort_book` (overlapping cohorts held a fixed span), `welch_t`, `check_dates` (the move must be larger on event days) |
| `backtest_core.futures_book` | `market(ses, close)` (returns, EWMA vol), `time_series_book` (each market on its own signal, mean over live markets, row 106), `cross_section_book` (ranked or signed across markets each month, 1/n each, row 114), `trailing_sign`, `ewma_sigma` |
| `backtest_core.scoring` | `daily(days, net, gross, mask, sharpe_bar, t_bar)` and `per_trade(...)`: the numbers a register row prints and the pass against the pre-registered bars, in place of each study's copied `score()` |
| `backtest_core.fidelity` | `compare(days, daily, pub_months, pub_monthly)`: our daily series on months against a published monthly series (correlation, beta, tracking error, means); `verdict(f, floor)` is "fit" or "uninformative" |
| `backtest_core.sim` | `run(...)`: one position at a time from boolean entry / exit signals, fills at the signal close or the next open, costs split half and half; `cost_fraction` charges ticks + fees on the raw price |
| `backtest_core.zorro.export` | `t6(symbol, source, freq, prices)` writes Zorro `.t6` history from the bar store (byte-identical to the old `to_t6.py` for ES, NQ, GC, CL); `factor_block` the lite-C roll table; `asset_row` |
| `backtest_core.zorro.run` | `deploy(names)` copies scripts from `zorro/Strategy` in this repo (the source of truth) into Zorro; `run(script, *ints)` runs `Zorro.exe -run/-train ... -quiet` and raises if no fresh report appears (a compile error is otherwise silent) |
| `backtest_core.zorro.report` | Parses `Log/<Script>.txt` (Sharpe, profit factor, trades, drawdown, Monte Carlo table, sample cycles) and reads `_trd.csv` / `_pnl.csv` |
| `backtest_core.zorro.parity` | `compare(zorro, python, keys, values, tol)` — trade-by-trade parity with only-Zorro / only-Python / value-mismatch rows |
| `backtest_core.zorro.battery` | `run_battery(script)` runs `Robust.h` modes 0-7 (bar start moved x6, detrend, shuffled-price reality check, Monte Carlo, costs x2, inverted) and returns one table with default pass bars |

## Usage

```python
from backtest_core import bars, sim, stats

d = bars.daily("NQ")
o, h, l, c = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
cost = sim.cost_fraction(c / d["factor"].to_numpy(), tick=0.25, usd_per_tick=5.0)   # 2 ticks + $4.50
res = sim.run(o, c, enter, exit_, valid, cost, side=1, fill="close")
print(stats.summary(res.returns, res.trades).line())
```

## Tests

```bash
<venv>/Scripts/python.exe -m pytest tests/unit -q          # hermetic
BARS_DIR=... <venv>/Scripts/python.exe -m pytest tests/integration -q   # reproduces results on record
```
`tests/integration/test_frozen_studies.py` rebuilds the ES / NQ daily dip-buy (register row 72) on this library and
checks every printed number of `Hephaestus/backtests/murphys_law/results_futures.txt`.
`tests/integration/test_reference_rows.py` rebuilds register rows 106, 107, 110, 111, 112, 114 and 117 with `xs`,
`events` and `futures_book` (data loaders and signals from the study folders) and checks every printed number. Run it
in the Hephaestus venv; it skips where the studies are absent.

Installed editable into the Hephaestus venv (`pip install -e ../backtest-core`).

## Changelog

- 2026-09-30 — Created: `stats`, `prereg`, `bars`, `sim`. Reproduces the ES / NQ futures dip-buy record exactly.
- 2026-09-30 — Added the Zorro toolkit: `zorro.export`, `zorro.run`, `zorro.report`, `zorro.parity`, `zorro.battery`
  (drives `zorro/Strategy/Robust.h`).
- 2026-10-03 — Added `NoiseAreaCore.h` + `NoiseAreaQQQ.c`: QQQ noise area with VWAP computed in the script
  (`marketVol`) and `Robust.h` wired in, so the shuffled-price check applies. `NoiseArea.c` / `NoiseAreaFull.c` unchanged.
- 2026-10-04 — Added `NightHoldCore.h` + `NightHoldNQ.c`: an index future held 16:00 -> 09:30 ET only, with `Robust.h` and a
  `-d HOLDOUT` window. Matches `Hephaestus/backtests/nq_night_hold/night.py` trade for trade; failed its battery.
- 2026-10-04 — Added `universe`: `panel("R3000" | "SP500")` (daily matrices by stay, dead companies included, from
  Hermes's member snapshots, `index_listing` and the research price store), `earnings(panel)` (SEC notices mapped to the
  first session that could react), `members`, `listings`. Bad ticks are blanked and broken price files dropped by rule.
- 2026-10-04 — Added `price_flags`: bad prices (one-day spikes, 10+ sessions at one close, scale breaks) are listed in flags beside the research price store and `universe.panel` blanks them. **Behaviour change:** `panel` now raises until `python -m backtest_core.price_flags build` has run; stale runs are blanked (new); scale breaks are found against the last price across gaps; `ac` is restated so price ratios equal compounded returns across a break. `universe.drop_spikes` and its constants moved to `price_flags`.
- 2026-10-04 — `universe.Panel` gained `op` (adjusted open on the scale of `ac`; NaN when the open is missing or outside 0.5x-2x of its own close). `price_matrix` now returns four arrays (it returns the open-over-close ratio last). Additive for `panel` users.
- 2026-10-05 — Live start for the dip-buy, zigzag and break cores. `-d LIVE` trades the real micro contract (`History/AssetsLive.csv`, or `AssetsIBPaper.csv` for the dip-buy) and rebuilds its state on every start; `-d LIVETEST` runs that start on history; `-d STATE` (dip-buy, break) writes the state file the start loads (`Data/<Script>_state.csv`, `Data/<Script>_touches.csv`). Backtests are unchanged: the four intraday event logs are byte-identical to the 2026-09-28 baseline. Added `ConnTestIB.c`. The trade-mode-only part of `-d LIVE` has not run yet. See bar-backtest-agent `production.md`.
- 2026-10-05 — Added `backtest_core.zorro.live`: `python -m backtest_core.zorro.live` exports the `.t6` history, `ZZFactors.h` and the live state files from the bar store, to the end of the history. `ZZFactors.h` is now generated by it.
- 2026-10-10 — Added `zorro.export.t6_daily(symbol, daily_frame)`: one adjusted `.t6` record per session from a daily
  price-store frame, stamped 20:30 UTC (for `BarPeriod = 1440; BarOffset = 21*60`). Added `TLTMonthEndCore.h` +
  `TLTMonthEnd.c` + the generated `NYSECalendar.h` (month-end calendar rule on TLT, `Robust.h`, `-d HOLDOUT`) and
  `History/AssetsETFDaily.csv`.
- 2026-10-14 — Added `xs` (sort books), `events` (event rules), `futures_book` (volatility-scaled books across
  markets) and `scoring` (the printed numbers and the pass, in place of each study's `score()`). New modules only;
  nothing existing changed. `tests/integration/test_reference_rows.py` reproduces register rows 106, 107, 110, 111,
  112, 114 and 117 to every printed digit. Built for the idea pipeline (`pythia`, plan M3).
- 2026-10-14 — Added `fidelity` (`compare`, `to_monthly`, `verdict`): does a build track the published series of its
  rule? New module only. The floor is set from data in `Hephaestus/backtests/fidelity_floor/` (plan M6).
- 2026-10-14 — Added `SPYTLTMidMonthCore.h` + `SPYTLTMidMonth.c` (SPY / TLT second half of the month, register row 166;
  `Robust.h`, `-d HOLDOUT`). `BreakCore.h` and `ZigZagCore.h` skip pool trades (`TradeIsPool`): in live trading a pool
  trade is Zorro's net position at the broker, never one of the script's own, so stops, exits and fees leave it alone.
- 2026-10-15 — `universe` and `price_flags` read `HERMES_PRICES_DIR` (the Hermes price store, which now holds the dead
  companies too) in place of `RESEARCH_PRICES_DIR`; `price_matrix` reads `exchange=US` files only. The flags now sit in
  `Hermes/data/prices_flags/`: rebuild them once (`python -m backtest_core.price_flags build`).
