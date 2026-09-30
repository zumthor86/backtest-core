// BreakGC.c -- slow-approach break of old zigzag levels on GC (gold) 1-minute bars. Logic in BreakCore.h.
#include <default.c>

#define BK_ASSET "GC"
#define BK_EVENTS "Log/BreakGC_events.csv"
#define BK_TICK 0.1            // $ per ounce
#define BK_TICK_USD 10.        // $ per tick per contract
#define BK_K 1.
#define BK_R 0.5
#define BK_NF GC_NF
#define BK_FT GC_FT
#define BK_FV GC_FV

#include "Robust.h"
#include "BreakCore.h"
