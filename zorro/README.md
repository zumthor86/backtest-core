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
| `NoiseAreaNQ.c` | The paper sleeve: `NoiseAreaCore.h` on one full-size NQ contract, raw prices with the NQ roll factors (`NQF_<YYYY>.t6`); IBKR does not let this account trade QQQ | `Hephaestus/backtests/nq_noise_area_zorro/parity_nq.py` |
| `ZZFactors.h`, `NAFactors.h` | Generated roll / dividend factor tables (`backtest_core.zorro.export.factor_block`; `export_t6.py` for QQQ) | — |
| `History/AssetsLive.csv` | Trade-mode asset list for `-d LIVE`: history names (GC, CL, ES, NQ) with the micro contract as the symbol. The contract must be the one the `.t6` history ends on | — |
| `Heartbeat.h`, `StateExport.h`, `LiveRestart.h`, `PriceGate.h`, `PoolSync.h`, `ExpiryGuard.h`, `NfaOn.h` | Live-only helpers the sleeve cores include (empty outside `-d LIVE`). `Heartbeat.h`: one line a minute in `Log\Heartbeat_<Script>.csv` (price ticks and bars handled), and each live bar (close time in UTC, OHLC, the day's running volume) in `Log\Bars_<Script>.csv`. `StateExport.h`: the sleeve's pending entries and open trades with stop and target, rewritten each minute in `Log\State_<Script>.csv`. `LiveRestart.h`: `brokerCommand(SET_RESTART, 2210)`, meant to make the IB plugin log in again after the Gateway's 22:05 restart; it is not enough on its own. `Heartbeat.h` logs in again (`login(4)`, then `login(1)`) once a night, 3 minutes after the Gateway's 22:05 UK restart, and again when the market is open (for NoiseAreaNQ, from 15 minutes before its session) and the feed has given at most 1 quote a minute for 10 minutes, and writes each try to `Log\Relogin_<Script>.csv`. `NfaOn.h` (through `Heartbeat.h`): `nfaOn()` sets the NFA flag in the live branch of each sleeve core and logs the flag before and after, so an exit opens an opposite trade; the IB plugin cannot close a trade | — |
| `ConnTestIB.c`, `History/AssetsIBPaper.csv` | Connection test for the IB paper account (Trade mode, account `IB-Paper`): one price per asset and the balance, no enter call. The asset list holds the micro contracts and QQQ with dated IB symbols | — |
| `StopTestCore.h`, `StopTest1.c`, `StopTest2.c`, `CloseTest.c` (`Hedge = 4`), `CloseTest0.c` (`Hedge = 0`); `StopTest1.c` and `StopTest2.c` run `Hedge = 0` | Broker tests the user starts on the spare row `IB-Paper-7`: one MES trade, then a close. `CloseTest.c` proved on 2026-10-19 that a `Hedge = 4` close reaches IB once the NFA flag is set; `CloseTest0.c` proved on 2026-10-20 that a `Hedge = 0` close reaches IB with `nfaOn()`, and fails with Error 075 without it (`-d TEST_NO_NFA`) | — |
| `EhlersZZ.c`, `GapZZ.c`, `Workshop4ZZ.c` | Early experiments | — |

## How Zorro runs here

- **Three folders.** This folder is the source. `C:\Users\Christopher\Zorro\` is the live Zorro: the paper sleeves run
  from it, and research runs use it when no sleeve is up. `C:\Users\Christopher\ZorroReplay\` is a second copy for the
  daily paper replay (`backtest_core.zorro.paper setup` makes it, with no account rows), so a replay never touches the
  live sleeves' files. Copy a changed script into both `Strategy\` folders; a running sleeve keeps the code it compiled
  at its start, so a change takes effect at its next start.
- **One script, three builds**, chosen with `-d` on the command line:
  - no define: the backtest (`SIM`), on our `.t6` history and the test asset list.
  - `-d LIVETEST`: the paper replay. It defines both `SIM` and `LIVE`, so it runs the live signal code on history and
    writes the logs the replay compares; it sends no order.
  - `-d LIVE` with `-trade`: the paper sleeve. Only this build compiles the `#else` (not `SIM`) branch of the cores:
    `PRELOAD`, `NOLOCK`, the live asset list, `Hedge = 0` and `nfaOn()`. A change there cannot alter a backtest.
- **A sleeve's command line** (`argus.trading.zorro_args`): `Zorro.exe -trade <Script> -c <account row> -d LIVE -stay
  -w <x>`. Start sleeves only as the root `CLAUDE.md` allows, 5 minutes apart (`argus` does this): six started together
  starved each other of the API.
- **A start replays its lookback first** (13 to 20 minutes): `PRELOAD` reads our `.t6` history, then IB's history fills the
  days after it. The rule runs but sends no order. At the end the sleeve takes the position the rule holds then, so a
  start in the middle of a trade enters at once.
- **IB's history bars are not the live bars.** The plugin asks for `whatToShow: "ASK"` (Gateway API log), so the bars a
  start loads for today carry ask prices and no volume. NoiseAreaNQ then has no VWAP for that day and falls back to the
  opposite band as its exit. On 2026-10-19 a restart at 19:10 UTC rebuilt a long that the first run had already exited.
  A restart during the session can therefore hold a position the backtest never held.

## Settings we changed, and why

| Where | Setting | Why |
|---|---|---|
| `History\Accounts.csv` | One row per sleeve, `IB-Paper` to `IB-Paper-6`, plus `IB-Paper-7` for tests. `Server` 4002 (the paper Gateway), `Real` 0, `NFA` 14, `Plugin` `IB` to `IB7` | Each row uses its own copy of the IB plugin (`Plugin\IB.dll` to `IB7.dll`) and so its own API client ID (1 to 7), so each sleeve has its own API connection and its own Gateway API log |
| sleeve cores, live branch | `set(NOLOCK)` | Without it every Zorro waits on any other that hangs; one sleeve with no connection slowed all of them to a bar per 8 minutes (2026-10-14) |
| sleeve cores, live branch | `set(PRELOAD)` | The lookback comes from our history, not from IB's (IB gives a few days only) |
| sleeve cores, live branch | `Hedge = 0` | IB keeps one net position per instrument (NFA), so Zorro does too: the script's trade is the broker's trade, and a new entry closes the opposite one. The backtest (`Hedge = 2` for Break and ZigZag) gives the same trades (checked 2026-10-20 with `-d HEDGE0`). All six sleeves since 2026-10-22. Until 2026-10-20 the cores ran `Hedge = 4` (virtual hedging: Zorro kept the script's "phantom" trades and sent only the net, the "pool"); a phantom trade with no pool partner was never sent to the broker (BreakGC, 10-22) |
| sleeve cores, live branch | `nfaOn()` (`NfaOn.h`) | `NFA` 14 in the account row did **not** set the NFA flag: the log showed `NFA flag before nfaOn: 0`. Without it Zorro closes a trade, which the IB plugin cannot do: "Error 075 - closing not supported (NFA?)", and no order reaches IB (10-14, 10-15, 10-16, 10-19). With it an exit opens an opposite trade |
| `LiveRestart.h` | `brokerCommand(SET_RESTART, 2210)` | Meant to make the IB plugin log in again after the Gateway's daily restart. The manual does not say which clock HHMM uses |
| `Heartbeat.h` | `hbRelogin()`: `login(4)`, then `login(1)`, after 10 open-market minutes with at most 1 quote a minute, and every 10 minutes after that until quotes come back | After the Gateway's 22:05 restart the sleeves did not get their connection back on most nights (10-13 to 10-19, SET_RESTART set): Zorro's own retries kept failing until a person restarted them. This is the manual's fix for a hung broker API, the same as [Stop], [No], [No]; open trades stay. "Market open" is Globex open and, for a `BR_MARKET` sleeve (NoiseAreaNQ), `StartMarket` to `EndMarket` in UTC. A CME holiday is not known, so on one it tries every 10 minutes |
| `PriceGate.h` | `NOPRICE` while CME Globex is shut | In the daily halt IB sends the last settlement as a trade; the sleeves took it as real (a false ZigZagCL stop, false pivots), and the backtest bars hold no trade there |
| `NoiseAreaCore.h` | `StartMarket` / `EndMarket` 09:30 to 16:01 New York, `BR_MARKET + BR_WEEKEND + BR_SLEEP` | Regular-hours bars only, as in the history; outside the session the sleeve gets no quotes, by design |
| `NoiseAreaCore.h` | `brokerCommand(SET_VOLTYPE, 4)` | Trade volume, not quote size, for the VWAP |
| `History\AssetsLive.csv` | `Symbol` column: the micro (or full NQ) contract with its expiry | The weekly preparation (`argus week prep`) rewrites it at the roll; never edit it by hand |
| `Zorro.ini` | unchanged | — |

The IB Gateway side (IBC, the per-login settings folder `C:\Users\Christopher\ibgateway-settings\paper\`, port 4002, the
daily restart) is in `ares/docs/gateway.md`.

## Files a live sleeve uses (in `C:\Users\Christopher\Zorro\`)

| File | Written by | Read by |
|---|---|---|
| `Strategy\<Script>.c` and the headers | copied from here | Zorro at the start |
| `History\<NAME>_<YYYY>.t6`, `AssetsLive.csv`, `Accounts.csv` | `backtest_core.zorro.live` / export, the weekly preparation, by hand | Zorro at the start |
| `Data\<Script>_d.trd` | Zorro: its open trades | Zorro at the next start, which reloads them. A trade closed outside Zorro stays in it: stop the sleeve and move the file to `Data\stale_trades\<date>\` |
| `Log\<Script>_demo.log` | Zorro, rewritten at each start | a person, only after the sleeve stops: a reader while Zorro runs makes it stop logging |
| `Log\Heartbeat_<Script>.csv`, `Bars_<Script>.csv` | `Heartbeat.h` | `argus` health, the bar check |
| `Log\State_<Script>.csv` | `StateExport.h` | `argus state` and the reconcile |
| `Log\PoolSync_<Script>.csv` | `PoolSync.h`: each change in the comparison of Zorro's pool and the broker (code 0 agree, 1 the broker holds what Zorro does not, 2 Zorro holds what the broker does not, 3 other). No line while the feed is dead (at most 1 quote a minute): a dead connection reads the broker as flat | a person |
| `Log\Relogin_<Script>.csv` | `Heartbeat.h`: one line per re-login try (time, quiet since, `login(1)` result) | a person |
| `Log\Errors.txt` | Zorro: every error line, all scripts | `argus` alerts |

## Finding the cause of a broker problem

- **Zorro's error text is a guess.** Error 075 can be any refused order. The broker's side is in the Gateway's API message
  log: one file per client ID, `api.<clientId>.<date>.<time>.ibgzenc`, in the login's settings folder (above). The files
  are encrypted; export them as text from the Gateway window's File menu. Turn the log on in Configure, API, Settings
  ("Create API message log file").
- **On 2026-10-19 the log showed no close order at all**: the failure was inside Zorro (the NFA flag), not at IB.
- **A compile check needs `-run`, not `-test`.** `Zorro.exe -test` with a compile error waits on a dialog and never exits.
  Probe instead: a wrapper script `#define LIVE`, `#include "<Script>.c"` and a `main()` that writes a file and quits, run
  with `-run ... -quiet` in `ZorroReplay`. The file appears only if the whole script compiled. Test the probe with a
  script that has a syntax error first.

## Live trading: what the broker sees

- **The broker sees almost nothing.** Zorro handles entry stops, stop losses and profit targets itself and does not send
  them (`stop.txt`: "unknown to the broker"). The sleeves set none of `OrderLimit`, `StopFactor` or `SET_ORDERTYPE`, so
  the broker gets a market order only when Zorro enters or exits, and its open-order list is empty. A position held while
  Zorro is down, disconnected or stuck has **no stop at the broker**. There is no broker-side safety stop yet.
- **One paper account for all six sleeves.** The rows `IB-Paper` to `IB-Paper-6` in `History\Accounts.csv` share one
  `AccountId` and differ only in IBKR client ID (1 to 6) and plugin copy (`IB` to `IB6`); `IB-Paper-7` is the test row. IBKR nets positions per
  instrument, so the broker cannot say which sleeve owns what; two sleeves on one contract (ZigZagGC and BreakGC trade GC)
  can cancel each other there while each Zorro still holds its trade.
- **Where to look.** `python -m argus state` (in `argus/`) reads `Log\State_<Script>.csv` for pending entries and open trades per
  sleeve, then the broker's positions and orders through the `ares` gateway (`GET /open-orders`, `GET /positions`), and
  reconciles the sum of the sleeves' open trades with the broker's position per instrument. `python -m argus health`
  judges whether the processes and their price feed are alive. Never open `Log\<Script>*_demo.log` while Zorro runs.

History (`.t6`) files are data, rebuilt with `backtest_core.zorro.export.t6(symbol)`; not tracked. How the
workflow uses all this: `Hephaestus/.claude/skills/bar-backtest-agent/references/workflow.md`.
