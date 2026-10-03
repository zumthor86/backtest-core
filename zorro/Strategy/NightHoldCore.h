// NightHoldCore.h -- hold an index future overnight only: buy the 16:00 ET close, sell the next 09:30 ET open.
// Included by NightHoldNQ.c, which sets the NH_* parameters and includes Robust.h first.
// Port of Hephaestus/backtests/nq_night_hold/night.py; parity.py compares the two trade logs.
//
// Bars   1-minute, ratio-adjusted history (1 unit = 1 adjusted index point, History/AssetsZZ.csv).
// Rules  Flat and the bar ends at 16:00 ET: buy at its close.
//        Long, a later date, the bar ends between 09:30 and 16:00 ET: sell at the next bar's open.
//        (Normally the bar ending 09:30, so the fill is the 09:30 open.)
// Costs  2 ticks + NH_FEE_USD per round trip, as Zorro Commission in adjusted points (raw ticks x roll factor).
// Sizing NOTIONAL / price units per trade.
// Window in-sample by default; -d HOLDOUT runs the holdout window.

#include "ZZFactors.h"

#define NOTIONAL 1000000
#define COMM_TICKS (NH_FEE_USD / NH_TICK_USD)

int FI, InPos, EntryDate, Pending, PendingDate;
var EntryPx, EntryRaw;

var factorNow()
{
	int m = (int)floor(wdate(0) * 1440 + 0.5);
	while(FI + 1 < NH_NF && NH_FT[FI + 1] <= m) FI++;
	return NH_FV[FI];
}

// US Eastern time from UTC (DST rules from 2007): Zorro's own zone table is only documented to 2024.
int dowOle(var t) { return ((int)floor(t) + 6) % 7; }          // 0 = Sunday
var etFromUtc(var t)
{
	int y = ymd(t) / 10000;
	var mar1 = dmy(y * 10000 + 301);
	var nov1 = dmy(y * 10000 + 1101);
	var dstStart = mar1 + ((7 - dowOle(mar1)) % 7) + 7 + 7. / 24;
	var dstEnd = nov1 + ((7 - dowOle(nov1)) % 7) + 6. / 24;
	if(t >= dstStart && t < dstEnd) return t - 4. / 24;
	return t - 5. / 24;
}

function run()
{
	BarPeriod = 1;
	BarMode = 0;               // every bar in the history
	Outlier = 1000;            // off: never let Zorro "repair" a real price move
	LookBack = 0;
	TickFix = -30000;          // history stamps each minute at its close; move every stamp to mid-minute
#ifdef HOLDOUT
	StartDate = 20200101;
	EndDate = 20260918;
#else
	StartDate = 20100607;
	EndDate = 20191231;
#endif
	robustBars(0);
	robustCapital(NOTIONAL);
	assetList("AssetsZZ");
	asset(NH_ASSET);
	Spread = 0; Slippage = 0; Penalty = 0;
	Fill = 1;                  // at the bar's close
	setf(TradeMode, TR_FRC);

	if(is(INITRUN)) {
		FI = 0; InPos = 0; Pending = 0;
		if(robustLogging()) {
			file_delete(NH_TRADES);
			file_append(NH_TRADES, "entry_date,exit_date,entry_px,exit_px,entry_raw\n");
		}
		return;
	}

	if(Pending) {              // the sell ordered on the previous bar filled at this bar's open
		if(robustLogging())
			file_append(NH_TRADES, strf("%i,%i,%.10g,%.10g,%.10g\n", EntryDate, PendingDate, EntryPx, priceOpen(0), EntryRaw));
		Pending = 0;
	}

	var et = etFromUtc(wdate(0));                                        // bar CLOSE time, New York
	int m = (int)floor((et - floor(et)) * 1440 + 0.5);                   // minute of the day the bar ends at
	int today = ymd(et - 0.5 / 1440);                                    // date of the bar's own minute
	var factor = factorNow();
	var c = priceClose(0);

	if(InPos) {
		if(today > EntryDate) {
			if(m >= 570) {
				if(m <= 960) {
					Fill = 3;                                                // next bar's open
					exitLong();
					InPos = 0; Pending = 1; PendingDate = today;
				}
			}
		}
	} else if(m == 960) {
		Lots = (int)(NOTIONAL / c);
		Commission = NH_TICK * factor * (2. + COMM_TICKS) * robustCostMult();
		enterLong();
		InPos = 1; EntryDate = today; EntryPx = c; EntryRaw = c / factor;
	}
}
