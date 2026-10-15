// TLTMonthEndCore.h -- month-end calendar rule on a bond ETF: long the last sessions of each month, short the first
// sessions of the next, flat otherwise. Included by TLTMonthEnd.c, which includes Robust.h first.
// Port of Hephaestus/backtests/tlt_month_end/tlt_month_end.py; parity.py there compares the two trade lists.
//
// Bars   one per NYSE session. The history (backtest_core.zorro.export.t6_daily) holds one adjusted record a day,
//        stamped 20:30 UTC, inside the bar that ends 21:00 UTC. With Robust.h mode 1 the bar end moves and the same
//        record lands in a bar that ends up to 20 hours later, so the session date is derived from the bar end and
//        the offset, never read off the bar end alone.
// Rules  At each close look up the NEXT session in NYSECalendar.h: long if it is one of the last 5 of its month,
//        short if it is one of the first 5, else flat. A change of position trades at this close.
// Costs  ME_COST_BP per side and ME_BORROW_PCT a year on short days, charged as Zorro Commission per round trip in
//        price points: entry price x (2 x cost + days short x borrow / 252 for a short leg).
// Sizing NOTIONAL / price shares per leg, not compounded.
// Window in-sample by default; -d HOLDOUT runs the holdout. No position is opened at the last close of a window.

#include "NYSECalendar.h"

#define NOTIONAL 1000000
#define ME_COST_BP 1
#define ME_BORROW_PCT 1
#define ME_BASE_OFFSET 1260      // bars end 21:00 UTC
#define ME_STAMP_BACK 30         // the record sits 30 minutes before that

#ifdef HOLDOUT
#define ME_START 20191227
#define ME_FROM 20191231
#define ME_LAST 20261007
#else
#define ME_START 20020726
#define ME_FROM 20020731
#define ME_LAST 20191231
#endif

int CI, Pos, EntryDate;
var EntryPx, EntryCost;

// The date of the record inside this bar: step back from the bar end to the 20:30 UTC stamp.
int sessionDate()
{
	var t = wdate(0);
	int m = (int)floor((t - floor(t)) * 1440 + 0.5);
	int back = (m - ME_BASE_OFFSET + 2880) % 1440 + ME_STAMP_BACK;
	return ymd(t - back / 1440.);
}

void logTrade(int today, var c)
{
	if(robustLogging())
		file_append(ME_TRADES, strf("%i,%i,%i,%.10g,%.10g,%.10g\n", Pos, EntryDate, today, EntryPx, c,
			Pos * (c / EntryPx - 1) - EntryCost));
}

function run()
{
	BarPeriod = 1440;
	robustBars(ME_BASE_OFFSET);
	BarMode = 0;               // a bar wherever there is a record, weekends included when the bar end is moved
	Outlier = 1000;            // off: never let Zorro "repair" a real price move
	LookBack = 0;
	StartDate = ME_START;
	EndDate = ME_LAST;
	robustCapital(NOTIONAL);
	assetList("AssetsETFDaily");
	asset(ME_ASSET);
	Spread = 0; Slippage = 0; Penalty = 0;
	Fill = 1;                  // at the daily close
	setf(TradeMode, TR_FRC);

	int nLong = (int)(robustParam(5, 3, 7, 1) + 0.5);
	int nShort = (int)(robustParam(5, 3, 7, 1) + 0.5);
	var cost = ME_COST_BP;
	var borrow = ME_BORROW_PCT;
	cost = cost / 10000;       // lite-C keeps 7 digits of a decimal constant; divide in a var instead
	borrow = borrow / 100 / 252;

	if(is(INITRUN)) {
		CI = 0; Pos = 0;
		if(robustLogging()) {
			file_delete(ME_TRADES);
			file_append(ME_TRADES, "side,entry_date,exit_date,entry_px,exit_px,net\n");
			file_delete(ME_MISS);
		}
		return;
	}

	int today = sessionDate();
	while(CI + 1 < NYSE_N && NYSE_D[CI] < today) CI++;
	if(NYSE_D[CI] != today) {                      // a bar that is not an exchange session: never trade on a guess
		if(robustLogging()) file_append(ME_MISS, strf("%i,%.6f\n", today, wdate(0)));
		return;
	}
	if(today < ME_FROM) return;

	int tgt = 0;
	if(today < ME_LAST) {
		if(CI + 1 < NYSE_N) {
			if(NYSE_L[CI + 1] < nLong) tgt = 1;
			else if(NYSE_I[CI + 1] <= nShort) tgt = -1;
		}
	}
	if(tgt == Pos) return;

	var c = priceClose(0);
	if(Pos == 1) { exitLong(); logTrade(today, c); }
	if(Pos == -1) { exitShort(); logTrade(today, c); }
	Pos = 0;
	if(tgt != 0) {
		Lots = (int)(NOTIONAL / c);
		EntryCost = 2 * cost;
		if(tgt == -1) EntryCost = 2 * cost + nShort * borrow;
		EntryCost = EntryCost * robustCostMult();
		Commission = c * EntryCost;
		if(tgt == 1) enterLong();
		else enterShort();
		Pos = tgt; EntryDate = today; EntryPx = c;
	}
}
