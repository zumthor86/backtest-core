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

Installed editable into the Hephaestus venv (`pip install -e ../backtest-core`).

## Changelog

- 2026-09-30 — Created: `stats`, `prereg`, `bars`, `sim`. Reproduces the ES / NQ futures dip-buy record exactly.
- 2026-09-30 — Added the Zorro toolkit: `zorro.export`, `zorro.run`, `zorro.report`, `zorro.parity`, `zorro.battery`
  (drives `zorro/Strategy/Robust.h`).
- 2026-10-03 — Added `NoiseAreaCore.h` + `NoiseAreaQQQ.c`: QQQ noise area with VWAP computed in the script
  (`marketVol`) and `Robust.h` wired in, so the shuffled-price check applies. `NoiseArea.c` / `NoiseAreaFull.c` unchanged.
