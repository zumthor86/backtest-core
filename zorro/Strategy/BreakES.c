// BreakES.c -- slow-approach break of old zigzag levels on ES (S&P 500 e-mini) 1-minute bars. Logic in BreakCore.h.
#include <default.c>

#define BK_ASSET "ES"
#define BK_EVENTS "Log/BreakES_events.csv"
#define BK_WARM_EVENTS "Log/BreakES_warm_events.csv"
#define BK_LIVE_EVENTS "Log/BreakES_live_events.csv"
#define BK_LIVE_LOTS 1
#define BK_STATE "Data/BreakES_touches.csv"
#define BK_TICK 0.25           // index points
#define BK_TICK_USD 12.5       // $ per tick per contract
#define BK_K 1.
#define BK_R 0.5
#define BK_NF ES_NF
#define BK_FT ES_FT
#define BK_FV ES_FV

#include "Robust.h"
#include "BreakCore.h"
