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
//
// -d STATE (test mode) writes every session close to DB_STATE, on the adjusted scale.
// -d LIVE  (trade mode) trades the real contract DB_LIVE_ASSET from History/AssetsIBPaper.csv, DB_LIVE_LOTS whole
//        contracts. Zorro allows one year of lookback in trade mode and QPI needs five, so the closes come from
//        DB_STATE and the broker's bars only fill the days after it. The state must be exported again after every
//        roll: it is on the adjusted scale, which equals the traded contract's prices only since the last roll.
//        The bar still ends at 18:00 ET, when Globex reopens, so an order fills at the reopen, not at the 17:00
//        close (next-open fills in murphy_futures.py: Sharpe 1.01 against 1.06 on NQ).
// -d LIVETEST (test mode) runs the LIVE start on history: closes from DB_STATE up to DB_STATE_CUT, then the
//        backtest's own bars, sizing and costs. Its trades after the cut must equal the base run's
//        (dipbuy_live_check.py).

#include "ZZFactors.h"

// Zorro takes one -d name per run, so the export to the end of the history is its own name.
#ifdef STATE_LATEST
#define STATE
#endif

// SIM = simulated fills on the adjusted history (every test-mode run); LIVE = start from the state file.
#ifdef LIVETEST
#define LIVE
#define SIM
#define DB_STATE_CUT 20260115   // a day the base run is flat
#define DB_LOG DB_LIVETEST_TRADES
#endif
#ifndef LIVE
#define SIM
#define DB_LOG DB_TRADES
#endif

#define NOTIONAL 1000000
#define QPI_MIN 252
#define QPI_MAX 1260
#define SMA_N 200
#define MAXB 8000
#define COMM_TICKS (4.5 / DB_TICK_USD)

var C[MAXB]; var R3[MAXB];
int NBar, FI, InPos, EntryDate, StateDate, Stale;
var AU, AD, EntryPx, EntryRaw;

#define STATE_GAP_DAYS 5                             // a long weekend; more than this is a hole in the closes

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

// Append one session close: r3 and the Wilder RSI(2) state (seeded on the first bar with a change, as
// murphy_futures.rsi2). Returns the RSI, NIL while it is undefined.
var pushClose(var c)
{
	int i = NBar;
	var d;
	var up;
	var dn;
	var rsi = NIL;
	C[i] = c;
	R3[i] = NIL;
	if(i >= 3) R3[i] = c / C[i - 3] - 1;
	if(i >= 1) {
		d = c - C[i - 1];
		up = max(d, 0.);
		dn = max(-d, 0.);
		if(i == 1) { AU = up; AD = dn; }
		else { AU = 0.5 * AU + 0.5 * up; AD = 0.5 * AD + 0.5 * dn; }
		if(AD > 0) rsi = 100. - 100. / (1. + AU / AD);
		else if(AU > 0) rsi = 100.;
	}
	NBar++;
	return rsi;
}

#ifdef LIVE
// The closes up to the last export, one "yyyymmdd,close" line per session.
void loadState()
{
	string txt = file_content(DB_STATE);
	string line;
	string comma;
	StateDate = 0;
	if(!txt) { printf("\n%s missing: export it with -d STATE", DB_STATE); return; }
	line = strtok(txt, "\n");
	while(line && NBar < MAXB) {
		comma = strchr(line, ',');
		if(comma) {
#ifdef LIVETEST
			if(atoi(line) > DB_STATE_CUT) break;
#endif
			StateDate = atoi(line);
			pushClose(atof(comma + 1));
		}
		line = strtok(0, "\n");
	}
	printf("\n%s: %i closes to %i", DB_STATE, NBar, StateDate);
}
#endif

function run()
{
	BarPeriod = 1440;
	BarZone = ET;
	robustBars(18 * 60);                           // sessions split at 18:00 ET (the Python bars' rule: session = date of
	                                               // start + 6h), so 17:00-17:15 trading in 2012-15 stays in its day
	TickFix = -30000;                              // history stamps each minute at its close (a float date that can land
	                                               // either side of a bar edge); move every stamp to mid-minute
	BarMode = 0;                                   // keep holiday sessions that have quotes, as the Python bars do
	Outlier = 1000;
	LookBack = SMA_N + 10;
	StartDate = 20100606;
#ifdef LIVE
	LookBack = 30;                                 // only the sessions after the state file; the rest is loaded
	StartDate = 20251101;                          // LIVETEST; trade mode starts now and ignores it
#endif
#ifdef SIM
	EndDate = 20260919;
#ifdef STATE_LATEST
	EndDate = Command[1];        // a state export for a live start runs to the end of the history
#endif
	robustCapital(NOTIONAL);
	assetList("AssetsZZ");
	asset(DB_ASSET);
	Spread = 0; Slippage = 0; Penalty = 0;
	Fill = 1;
	setf(TradeMode, TR_FRC);
#else
	assetList("AssetsIBPaper");
	asset(DB_LIVE_ASSET);
#endif

	var qpiMax = robustParam(30, 10, 50, 5) / 100.;
	var ibsIn = robustParam(10, 5, 25, 5) / 100.;
	var ibsOut = robustParam(90, 70, 95, 5) / 100.;
	var rsiOut = robustParam(90, 70, 95, 5);

	if(is(INITRUN)) {
		NBar = 0; FI = 0; InPos = 0; AU = 0; AD = 0; Stale = 0;
#ifdef LIVE
		loadState();
#endif
#ifdef STATE
		file_delete(DB_STATE);
#endif
#ifdef SIM
		if(robustLogging()) {
			file_delete(DB_LOG);
			file_append(DB_LOG, "entry_date,exit_date,entry_px,exit_px,entry_raw,exit_raw,factor_entry\n");
		}
#endif
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
	var acc;
#ifdef LIVE
	if(sessionDate() <= StateDate) return;         // already in the state file
	// The first bar after the state file must be the next session, or a close is missing and every rule value
	// after it would be wrong. Stale stops all orders until the state is exported again.
	if(i > 0 && StateDate > 0 && dmy(sessionDate()) - dmy(StateDate) > STATE_GAP_DAYS) Stale = 1;
	StateDate = sessionDate();
#ifndef SIM
	InPos = NumOpenLong > 0;                       // Zorro resumes its open trades after a restart; this does not
#endif
#endif
	var rsi = pushClose(c);
#ifdef STATE
	file_append(DB_STATE, strf("%i,%.10g\n", sessionDate(), c));
#endif
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
#ifdef DB_DEBUG
	file_append(DB_DEBUG, strf("%.8f,%i,%.10g,%.10g,%.10g\n", wdate(0), ymd(wdate(0)), h, l, c));
#endif

	if(qpi == NIL || sma == NIL || is(LOOKBACK)) return;
#ifdef LIVE
	printf("\n%i  close %.2f  r3 %.4f  QPI %.3f  IBS %.3f  SMA %.2f  RSI %.1f  in %i", sessionDate(), c, R3[i], qpi, ibs, sma, rsi, InPos);
	if(Stale) { printf("\nState file too old: no orders. Export it again with -d STATE"); return; }
#endif
	var factor = factorNow();
	if(InPos) {
		if(ibs > ibsOut || (rsi != NIL && rsi > rsiOut)) {
			exitLong();
#ifdef SIM
			if(robustLogging())
				file_append(DB_LOG, strf("%i,%i,%.10g,%.10g,%.10g,%.10g,%.10g\n", EntryDate, sessionDate(), EntryPx, c,
					EntryRaw, c / factor, EntryPx / EntryRaw));
#endif
			InPos = 0;
		}
	} else if(R3[i] < 0 && qpi <= qpiMax && ibs < ibsIn && c > sma) {
#ifdef SIM
		Lots = (int)(NOTIONAL / c);
		Commission = DB_TICK * factor * (2. + COMM_TICKS) * robustCostMult();
#else
		Lots = DB_LIVE_LOTS;                         // whole contracts; the broker charges the real cost
#endif
		enterLong();
		InPos = 1; EntryDate = sessionDate(); EntryPx = c; EntryRaw = c / factor;
	}
}
