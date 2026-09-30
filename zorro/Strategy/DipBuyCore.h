// DipBuyCore.h -- daily dip-buying (Quantitativo "Murphy's Law" rules) on futures, one market, long only.
// Included by DipBuyES.c and DipBuyNQ.c, which set the DB_* parameters and include Robust.h first.
// Port of Hephaestus/backtests/murphys_law/murphy_futures.py (register row 72). dipbuy_parity.py compares this script's
// trade log with a Python mirror.
//
// Bars   one per Globex session: daily bars ending 18:00 ET (BarZone ET, BarOffset 18:00), built from the 1-minute
//        ratio-adjusted history (1 unit = 1 adjusted index point, History/AssetsZZ.csv).
// Rules  r3   = close / close 3 bars ago - 1
//        QPI  = share of all earlier r3 values (at most the last 1,260, at least 252) at or below today's
//        IBS  = (close - low) / (high - low), 0.5 on a zero range
//        SMA  = 200-bar mean of the close;  RSI(2) Wilder, smoothing 0.5, seeded on the first bar
//        Entry at the bar close: r3 < 0, QPI <= 0.30, IBS < 0.10, close > SMA.
//        Exit at the bar close: IBS > 0.90 or RSI(2) > 90. One position at a time.
// Costs  2 ticks + $4.50 per round trip, charged as Zorro Commission in adjusted points (raw ticks x roll factor).
// Sizing NOTIONAL / price units per trade.
// Checks Robust.h modes (-i n). The four thresholds are robustParam()s, written in percent so they sit in Zorro's
//        positive integer range for optimize().

#include "ZZFactors.h"

#define NOTIONAL 1000000
#define QPI_MIN 252
#define QPI_MAX 1260
#define SMA_N 200
#define MAXB 8000
#define COMM_TICKS (4.5 / DB_TICK_USD)

var C[MAXB]; var R3[MAXB];
int NBar, FI, InPos, EntryDate;
var AU, AD, EntryPx, EntryRaw;

var factorNow()
{
	int m = (int)floor(wdate(0) * 1440 + 0.5);
	while(FI + 1 < DB_NF && DB_FT[FI + 1] <= m) FI++;
	return DB_FV[FI];
}

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

int sessionDate() { return ymd(etFromUtc(wdate(0)) - 1. / 1440); }   // the ET date of the bar's close

function run()
{
	BarPeriod = 1440;
	BarZone = ET;
	robustBars(18 * 60);                           // sessions split at 18:00 ET (the Python bars' rule: session = date of
	                                               // start + 6h), so 17:00-17:15 trading in 2012-15 stays in its day
	TickFix = -30000;                              // history stamps each minute at its close (a float date that can land
	                                               // either side of a bar edge); move every stamp to mid-minute
	BarMode = 0;                                   // keep holiday sessions that have quotes, as the Python bars do
	LookBack = SMA_N + 10;
	Outlier = 1000;
	StartDate = 20100606;
	EndDate = 20260919;
	robustCapital(NOTIONAL);
	assetList("AssetsZZ");
	asset(DB_ASSET);
	Spread = 0; Slippage = 0; Penalty = 0;
	Fill = 1;
	setf(TradeMode, TR_FRC);

	var qpiMax = robustParam(30, 10, 50, 5) / 100.;
	var ibsIn = robustParam(10, 5, 25, 5) / 100.;
	var ibsOut = robustParam(90, 70, 95, 5) / 100.;
	var rsiOut = robustParam(90, 70, 95, 5);

	if(is(INITRUN)) {
		NBar = 0; FI = 0; InPos = 0; AU = 0; AD = 0;
		if(robustLogging()) {
			file_delete(DB_TRADES);
			file_append(DB_TRADES, "entry_date,exit_date,entry_px,exit_px,entry_raw,exit_raw,factor_entry\n");
		}
		return;
	}
	if(NBar >= MAXB) return;

	var h = priceHigh(0);
	var l = priceLow(0);
	var c = priceClose(0);
	int i = NBar;
	int j;
	int cnt;
	int le;
	var d;
	var up;
	var dn;
	var acc;
	C[i] = c;
	R3[i] = NIL;
	if(i >= 3) R3[i] = c / C[i - 3] - 1;
	// Wilder RSI(2), seeded on the first bar with a change (as murphy_futures.rsi2)
	var rsi = NIL;
	if(i >= 1) {
		d = c - C[i - 1];
		up = max(d, 0.);
		dn = max(-d, 0.);
		if(i == 1) { AU = up; AD = dn; }
		else { AU = 0.5 * AU + 0.5 * up; AD = 0.5 * AD + 0.5 * dn; }
		if(AD > 0) rsi = 100. - 100. / (1. + AU / AD);
		else if(AU > 0) rsi = 100.;
	}
	// QPI over the earlier r3 values
	var qpi = NIL;
	if(i >= 3) {
		cnt = 0; le = 0;
		for(j = max(3, i - QPI_MAX); j < i; j++) { cnt++; if(R3[j] <= R3[i]) le++; }
		if(cnt >= QPI_MIN) qpi = (var)le / cnt;
	}
	var sma = NIL;
	if(i >= SMA_N - 1) { acc = 0; for(j = i - SMA_N + 1; j <= i; j++) acc += C[j]; sma = acc / SMA_N; }
	var ibs = 0.5;
	if(h > l) ibs = (c - l) / (h - l);
	NBar++;
#ifdef DB_DEBUG
	file_append(DB_DEBUG, strf("%.8f,%i,%.10g,%.10g,%.10g\n", wdate(0), ymd(wdate(0)), h, l, c));
#endif

	if(qpi == NIL || sma == NIL || is(LOOKBACK)) return;
	var factor = factorNow();
	if(InPos) {
		if(ibs > ibsOut || (rsi != NIL && rsi > rsiOut)) {
			exitLong();
			if(robustLogging())
				file_append(DB_TRADES, strf("%i,%i,%.10g,%.10g,%.10g,%.10g,%.10g\n", EntryDate, sessionDate(), EntryPx, c,
					EntryRaw, c / factor, EntryPx / EntryRaw));
			InPos = 0;
		}
	} else if(R3[i] < 0 && qpi <= qpiMax && ibs < ibsIn && c > sma) {
		Lots = (int)(NOTIONAL / c);
		Commission = DB_TICK * factor * (2. + COMM_TICKS) * robustCostMult();
		enterLong();
		InPos = 1; EntryDate = sessionDate(); EntryPx = c; EntryRaw = c / factor;
	}
}
