// DipBuyNQ.c -- daily dip-buying on NQ (Nasdaq-100 e-mini). Logic in DipBuyCore.h, checks in Robust.h.
#include <default.c>

#define DB_ASSET "NQ"
#define DB_TRADES "Log/DipBuyNQ_trades.csv"
#define DB_TICK 0.25           // index points
#define DB_TICK_USD 5.0        // $ per tick per contract
#define DB_NF NQ_NF
#define DB_FT NQ_FT
#define DB_FV NQ_FV

#include "Robust.h"
#include "DipBuyCore.h"
