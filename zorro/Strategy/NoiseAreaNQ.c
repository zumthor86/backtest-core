// NoiseAreaNQ.c -- the noise area rule of NoiseAreaQQQ.c on full-size Nasdaq-100 futures, one contract.
// IBKR does not let this account trade QQQ (a US ETF has no KID for a MiFID retail client), so the paper sleeve trades
// NQ instead. Register row 53: the rule fails its bar at micro (MNQ) cost and passes at full-size NQ cost; it is paper
// traded by the user's decision of 2026-10-16, not as a validated result.
// Data: History/NQF_YYYY.t6 (the front month on raw prices, the roll factor in fVal, volume in fVol), written by
// backtest_core.zorro.export.write_noise_area_nq. Rolls fall at 19:00 or 20:00 ET, outside the session the rule
// trades, so a session never spans two contracts. Asset lists: AssetsNoiseAreaNQ (tests), AssetsLive (trade).

#include <default.c>
#include "ZZFactors.h"
#include "Robust.h"

#define NA_ASSET "NQF"
#define NA_ASSETLIST "AssetsNoiseAreaNQ"
#define NA_NF NQ_NF
#define NA_FT NQ_FT
#define NA_FV NQ_FV
#define NA_COST 9.50           // one tick ($5) + $4.50 commission per contract round trip: row 53's full-size cost
#define NA_LOTS 1
#define NA_START 20100607
#define NA_END 20261231
#define NA_LIVE_LOOKBACK 30000 // the history holds every hour: about 21 days in a test; live keeps market hours only
#define NA_SIGNAL_LOG "Log/NoiseAreaNQ_signals.csv"

#include "NoiseAreaCore.h"
