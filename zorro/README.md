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
| `ConnTestIB.c`, `History/AssetsIBPaper.csv` | Connection test for the IB paper account (Trade mode, account `IB-Paper`): one price per asset and the balance, no enter call. The asset list holds the micro contracts and QQQ with dated IB symbols | — |
| `EhlersZZ.c`, `GapZZ.c`, `Workshop4ZZ.c` | Early experiments | — |

History (`.t6`) files are data, rebuilt with `backtest_core.zorro.export.t6(symbol)`; not tracked. How the
workflow uses all this: `Hephaestus/.claude/skills/bar-backtest-agent/references/workflow.md`.
