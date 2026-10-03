// NightHoldNQ.c -- NQ (Nasdaq-100 e-mini) held overnight only. Logic in NightHoldCore.h, checks in Robust.h.
#include <default.c>

#define NH_ASSET "NQ"
#define NH_TRADES "Log/NightHoldNQ_trades.csv"
#define NH_TICK 0.25           // index points
#define NH_TICK_USD 5.0        // $ per tick per contract
#define NH_FEE_USD 4.5         // per round trip
#define NH_NF NQ_NF
#define NH_FT NQ_FT
#define NH_FV NQ_FV

#include "Robust.h"
#include "NightHoldCore.h"
