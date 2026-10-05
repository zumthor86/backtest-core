// ZigZagCL.c -- zigzag continuation on CL (crude oil) 1-minute bars, rule R2. Logic in ZigZagCore.h.
// R2: threshold 1 x daily vol, trade only after a leg shorter than 1.5 thresholds, take profit 1.5, stop 1.5,
// and exit at every opposite confirmation.
#include <default.c>

#define ZZ_ASSET "CL"
#define ZZ_EVENTS "Log\\ZigZagCL_events.csv"
#define ZZ_WARM_EVENTS "Log\\ZigZagCL_warm_events.csv"
#define ZZ_LIVE_EVENTS "Log\\ZigZagCL_live_events.csv"
#define ZZ_LIVE_LOTS 1
#define ZZ_TICK 0.01           // $ per barrel
#define ZZ_TICK_USD 10.        // $ per tick per contract
#define ZZ_K 1.
#define ZZ_PREV_FILTER 1       // 1 = prev<1.5, 0 = avg3
#define ZZ_TP 1.5
#define ZZ_SL 1.5
#define ZZ_REV 1
#define ZZ_NF CL_NF
#define ZZ_FT CL_FT
#define ZZ_FV CL_FV

#include "Robust.h"
#include "ZigZagCore.h"
