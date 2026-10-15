// SPYTLTMidMonth.c -- second-half-of-month rule on SPY and TLT. Logic in SPYTLTMidMonthCore.h, checks in Robust.h.
#include <default.c>

#define MM_MISS "Log/SPYTLTMidMonth_miss.csv"
#ifdef HOLDOUT
#define MM_TRADES "Log/SPYTLTMidMonth_holdout_trades.csv"
#else
#define MM_TRADES "Log/SPYTLTMidMonth_trades.csv"
#endif

#include "Robust.h"
#include "SPYTLTMidMonthCore.h"
