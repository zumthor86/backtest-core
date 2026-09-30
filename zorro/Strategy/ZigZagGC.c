// ZigZagGC.c -- zigzag continuation on GC (gold) 1-minute bars, rule R1. Logic in ZigZagCore.h.
// R1: threshold 1 x daily vol, trade only when the last three legs averaged under 1.61 thresholds, take profit 2,
// stop 1, no exit on an untraded opposite confirmation.
#include <default.c>

#define ZZ_ASSET "GC"
#define ZZ_EVENTS "Log\\ZigZagGC_events.csv"
#define ZZ_TICK 0.1            // $ per ounce
#define ZZ_TICK_USD 10.        // $ per tick per contract
#define ZZ_K 1.
#define ZZ_PREV_FILTER 0       // 1 = prev<1.5, 0 = avg3
#define ZZ_TP 2.
#define ZZ_SL 1.
#define ZZ_REV 0
#define ZZ_NF GC_NF
#define ZZ_FT GC_FT
#define ZZ_FV GC_FV

#include "Robust.h"
#include "ZigZagCore.h"
