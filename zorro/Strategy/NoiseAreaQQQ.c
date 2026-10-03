// NoiseAreaQQQ.c -- QQQ noise area, full history, VWAP computed in the script, with the Robust.h battery.
// Mode 0 must trade exactly as NoiseAreaFull.c does (Hephaestus/backtests/qqq_noise_area_zorro_battery/parity.py).
// Data: History/QQQ_YYYY.t6 (raw prices, volume in fVol). Asset list: History/AssetsNoiseArea.csv.

#include <default.c>
#include "NAFactors.h"
#include "Robust.h"

#define NA_ASSET "QQQ"
#define NA_ASSETLIST "AssetsNoiseArea"
#define NA_NF QQQ_NF
#define NA_FT QQQ_FT
#define NA_FV QQQ_FV
#define NA_COST 0.017          // one tick + IBKR commission, per share round trip
#define NA_START 20110323
#define NA_END 20260922
#define NA_SIGNAL_LOG "Log/NoiseAreaQQQ_signals.csv"

#include "NoiseAreaCore.h"
