// SPYTLTMidMonthCore.h -- second-half-of-month rule on SPY and TLT: at the close of session 15 buy the ETF with the
// lower month-to-date return, sell it at the month-end close. Included by SPYTLTMidMonth.c, which includes Robust.h
// first. Port of Hephaestus/backtests/spy_tlt_mid_month/mid_month.py; parity.py there compares the two trade lists.
//
// Bars   one per NYSE session, as in TLTMonthEndCore.h: one adjusted record a day stamped 20:30 UTC, and the session
//        date derived from the bar end and the offset.
// Rules  On the last session of a month: exit, then keep both closes as the next month's base. On session MM_DAY:
//        month-to-date = close / base - 1 for each ETF; long the lower one (equal: flat).
// Costs  MM_COST_BP per side, charged as Zorro Commission per round trip in price points: entry price x 2 x cost.
// Sizing NOTIONAL / price shares a trade, not compounded.
// Window in-sample by default; -d HOLDOUT runs the holdout. Entries from MM_FROM, exits up to MM_LAST.

#include "NYSECalendar.h"

#define NOTIONAL 1000000
#define MM_COST_BP 1
#define MM_BASE_OFFSET 1260      // bars end 21:00 UTC
#define MM_STAMP_BACK 30         // the record sits 30 minutes before that

#ifdef HOLDOUT
#define MM_START 20191220
#define MM_FROM 20200101
#define MM_LAST 20260930
#else
#define MM_START 20020726
#define MM_FROM 20020801
#define MM_LAST 20191231
#endif

int CI, Held, EntryDate;         // Held: 0 flat, 1 SPY, 2 TLT
var EntryPx, EntryCost, BaseSPY, BaseTLT;

int sessionDate()
{
	var t = wdate(0);
	int m = (int)floor((t - floor(t)) * 1440 + 0.5);
	int back = (m - MM_BASE_OFFSET + 2880) % 1440 + MM_STAMP_BACK;
	return ymd(t - back / 1440.);
}

void logTrade(int today, var c)
{
	if(robustLogging()) {
		string name = "SPY";
		if(Held == 2) name = "TLT";
		file_append(MM_TRADES, strf("%s,%i,%i,%.10g,%.10g,%.10g\n", name, EntryDate, today, EntryPx, c,
			c / EntryPx - 1 - EntryCost));
	}
}

function run()
{
	BarPeriod = 1440;
	robustBars(MM_BASE_OFFSET);
	BarMode = 0;
	Outlier = 1000;
	LookBack = 0;
	StartDate = MM_START;
	EndDate = MM_LAST;
	robustCapital(NOTIONAL);
	assetList("AssetsETFDaily");
	asset("SPY");
	asset("TLT");
	Spread = 0; Slippage = 0; Penalty = 0;
	Fill = 1;
	setf(TradeMode, TR_FRC);

	int day = (int)(robustParam(15, 13, 17, 1) + 0.5);
	var cost = MM_COST_BP;
	cost = cost / 10000;       // lite-C keeps 7 digits of a decimal constant; divide in a var instead

	if(is(INITRUN)) {
		CI = 0; Held = 0; BaseSPY = 0; BaseTLT = 0;
		if(robustLogging()) {
			file_delete(MM_TRADES);
			file_append(MM_TRADES, "asset,entry_date,exit_date,entry_px,exit_px,net\n");
			file_delete(MM_MISS);
		}
		return;
	}

	int today = sessionDate();
	while(CI + 1 < NYSE_N && NYSE_D[CI] < today) CI++;
	if(NYSE_D[CI] != today) {
		if(robustLogging()) file_append(MM_MISS, strf("%i,%.6f\n", today, wdate(0)));
		return;
	}

	asset("SPY");
	var cS = priceClose(0);
	asset("TLT");
	var cT = priceClose(0);

	if(NYSE_L[CI] == 0) {
		if(Held == 1) { asset("SPY"); exitLong(); logTrade(today, cS); }
		if(Held == 2) { asset("TLT"); exitLong(); logTrade(today, cT); }
		Held = 0;
		BaseSPY = cS; BaseTLT = cT;
		return;
	}

	if(NYSE_I[CI] != day || Held != 0 || BaseSPY <= 0) return;
	if(today < MM_FROM || today >= MM_LAST) return;

	var mtdS = cS / BaseSPY - 1;
	var mtdT = cT / BaseTLT - 1;
	var c = 0;
	if(mtdS > mtdT) { asset("TLT"); c = cT; Held = 2; }
	else if(mtdT > mtdS) { asset("SPY"); c = cS; Held = 1; }
	else return;

	Lots = (int)(NOTIONAL / c);
	EntryCost = 2 * cost * robustCostMult();
	Commission = c * EntryCost;
	enterLong();
	EntryDate = today; EntryPx = c;
}
