// DipBuyES.c -- daily dip-buying on ES (S&P 500 e-mini). Logic in DipBuyCore.h, checks in Robust.h.
#include <default.c>

#define DB_ASSET "ES"
#define DB_TRADES "Log/DipBuyES_trades.csv"
#define DB_TICK 0.25           // index points
#define DB_TICK_USD 12.5       // $ per tick per contract
#define DB_STATE "Data/DipBuyES_state.csv"
#define DB_LIVETEST_TRADES "Log/DipBuyES_livetest_trades.csv"
#define DB_LIVE_ASSET "MES"
#define DB_LIVE_LOTS 1
#define DB_NF ES_NF
#define DB_FT ES_FT
#define DB_FV ES_FV

#include "Robust.h"
#include "DipBuyCore.h"
