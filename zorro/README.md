# backtest-core/zorro/

Our Zorro S scripts and asset lists. **This folder is the source of truth.** Zorro runs copies in its own
`C:\Users\Christopher\Zorro\Strategy\` and `History\` folders; `backtest_core.zorro.run.deploy([...])` copies
scripts from here into Zorro before a run. Edit here, never in Zorro's folder.

| Script | What | Parity check |
|---|---|---|
| `Robust.h` | The standard robustness battery: modes 0-9 via `-i` (bar start moved, detrend, shuffled-price reality check, Monte Carlo, costs x2, inverted, parameter plateau, walk-forward). Driven by `backtest_core.zorro.battery` | — |
| `DipBuyCore.h`, `DipBuyES.c`, `DipBuyNQ.c` | Daily dip-buying (Murphy's Law rules) on ES / NQ; uses `Robust.h` | `Hephaestus/backtests/murphys_law/dipbuy_parity.py` (109/109, 125/125) |
| `ZigZagCore.h`, `ZigZagGC.c` (R1), `ZigZagCL.c` (R2) | Vol-scaled zigzag continuation, GC / CL 1-min | `Hermes/notebooks/zigzag_segment_bootstrap/parity.py` |
| `BreakCore.h`, `BreakGC.c`, `BreakES.c` | Slow-approach break of old zigzag levels (causal variant C) | `.../break_parity.py` (823/823, 866/866 identical) |
| `NoiseArea.c` | QQQ noise area, in-sample window (parity artefact — do not edit) | `Hephaestus/backtests/qqq_noise_area/` |
| `NoiseAreaFull.c` | The same run to 2026-09 for the portfolio | — |
| `NoiseAreaCore.h`, `NoiseAreaQQQ.c` | The same rules with VWAP computed in the script (needs Zorro S); uses `Robust.h` | `Hephaestus/backtests/qqq_noise_area_zorro_battery/parity.py` (against `NoiseAreaFull.c`) |
| `ZZFactors.h`, `NAFactors.h` | Generated roll / dividend factor tables (`backtest_core.zorro.export.factor_block`; `export_t6.py` for QQQ) | — |
| `History/AssetsLive.csv` | Trade-mode asset list for `-d LIVE`: history names (GC, CL, ES, NQ) with the micro contract as the symbol. The contract must be the one the `.t6` history ends on | — |
| `Heartbeat.h`, `StateExport.h`, `LiveRestart.h` | Live-only helpers the sleeve cores include (empty outside `-d LIVE`). `Heartbeat.h`: one line a minute in `Log\Heartbeat_<Script>.csv` (price ticks and bars handled). `StateExport.h`: the sleeve's pending entries and open trades with stop and target, rewritten each minute in `Log\State_<Script>.csv`. `LiveRestart.h`: `brokerCommand(SET_RESTART, 305)` so the IB plugin re-logs in after the Gateway's 03:00 restart | — |
| `ConnTestIB.c`, `History/AssetsIBPaper.csv` | Connection test for the IB paper account (Trade mode, account `IB-Paper`): one price per asset and the balance, no enter call. The asset list holds the micro contracts and QQQ with dated IB symbols | — |
| `EhlersZZ.c`, `GapZZ.c`, `Workshop4ZZ.c` | Early experiments | — |

## Live trading: what the broker sees

- **The broker sees almost nothing.** Zorro handles entry stops, stop losses and profit targets itself and does not send
  them (`stop.txt`: "unknown to the broker"). The sleeves set none of `OrderLimit`, `StopFactor` or `SET_ORDERTYPE`, so
  the broker gets a market order only when Zorro enters or exits, and its open-order list is empty. A position held while
  Zorro is down, disconnected or stuck has **no stop at the broker**. There is no broker-side safety stop yet.
- **One paper account for all six sleeves.** The rows `IB-Paper` to `IB-Paper-6` in `History\Accounts.csv` share one
  `AccountId` and differ only in IBKR client ID (1 to 6) and plugin copy (`IB` to `IB6`). IBKR nets positions per
  instrument, so the broker cannot say which sleeve owns what; two sleeves on one contract (ZigZagGC and BreakGC trade GC)
  can cancel each other there while each Zorro still holds its trade.
- **Where to look.** `python -m argus state` (in `argus/`) reads `Log\State_<Script>.csv` for pending entries and open trades per
  sleeve, then the broker's positions and orders through the `ares` gateway (`GET /open-orders`, `GET /positions`), and
  reconciles the sum of the sleeves' open trades with the broker's position per instrument. `python -m argus health`
  judges whether the processes and their price feed are alive. Never open `Log\<Script>*_demo.log` while Zorro runs.

History (`.t6`) files are data, rebuilt with `backtest_core.zorro.export.t6(symbol)`; not tracked. How the
workflow uses all this: `Hephaestus/.claude/skills/bar-backtest-agent/references/workflow.md`.
