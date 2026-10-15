// TLTMonthEnd.c -- month-end calendar rule on TLT. Logic in TLTMonthEndCore.h, checks in Robust.h.
#include <default.c>

#define ME_ASSET "TLT"
#define ME_MISS "Log/TLTMonthEnd_miss.csv"
#ifdef HOLDOUT
#define ME_TRADES "Log/TLTMonthEnd_holdout_trades.csv"
#else
#define ME_TRADES "Log/TLTMonthEnd_trades.csv"
#endif

#include "Robust.h"
#include "TLTMonthEndCore.h"
