// ZigZagCore.h -- vol-scaled zigzag continuation on 1-minute futures bars.
// Included by ZigZagCL.c (rule R2) and ZigZagGC.c (rule R1), which set the ZZ_* parameters.
// Port of Hermes/notebooks/zigzag_segment_bootstrap (zz_engine.zigzag_var + sim_one_position, as run by
// volscale.py / vs_report.py). parity.py compares this script's event log with a Python mirror and the research engine.
//
// Rules
//   d       = log(1 + k * sigma), sigma = RMS of daily log returns over the previous 60 sessions (18:00 ET sessions).
//   Zigzag  a leg is confirmed when price moves d (in log terms) off the last extreme.
//   Signal  each confirmation; traded only if the filter passes (k >= 3 and
//           prev<1.5: the leg before it was shorter than 1.5 d, or
//           avg3:     the last three legs averaged under 2 - 0.67/sqrt(3) d).
//   Entry   stop order at the confirmation level (or the open when the bar gaps through it).
//   Exits   take profit ZZ_TP x d beyond entry (triggers on a one-tick trade-through, fills at the target), stop
//           ZZ_SL x d, and at an opposite
//           confirmation: always with ZZ_REV, else only when that signal is traded (stop and reverse).
//   One position at a time. Costs: half a tick on entry and on every exit but a take profit, plus $4.50 per contract.
//
// As Zorro trades it: every level is a resting order placed at a bar's close for the next bar. The research engine
// instead moves the confirmation level inside a bar that makes a new extreme, and switches to a new session's
// threshold on its first bar. Both are rare; parity.py counts them.
// The take profit rests at the target; the TMF vetoes an exit on a bar that only touched it (no trade-through).
//
// Sizing: 1 unit = 1 point of the adjusted price (History/AssetsZZ.csv); NOTIONAL / price units per trade, so the
// dollar P&L is the research engine's return at 1x notional times NOTIONAL.

#include "ZZFactors.h"

// -d LIVE (trade mode) trades ZZ_LIVE_LOTS whole contracts of the real contract behind ZZ_ASSET in
//   History/AssetsLive.csv. The state (60 sessions of returns, then the zigzag) is rebuilt on every start from
//   ZZ_LIVE_LOOKBACK bars: PRELOAD reads them from our .t6 history and the broker fills the days after it. The
//   history is on the adjusted scale, which equals the traded contract's prices only since the last roll, so it
//   must be exported again after every roll and the asset list must name the contract the history ends on.
//   A sleeve always starts flat or with the trades Zorro resumes; it never opens a position the full-history run
//   would be holding from before the start.
// -d LIVETEST (test mode) runs that start on history: one year of data, the first ZZ_LIVE_LOOKBACK bars as
//   lookback, then the backtest's own sizing and costs. Its events must equal the full run's
//   (zigzag_zorro/warm_check.py).
// SIM = simulated fills on the adjusted history: every test-mode run.
#ifdef LIVETEST
#define LIVE
#define SIM
#define ZZ_LOG ZZ_WARM_EVENTS
#endif
#ifndef LIVE
#define SIM
#define ZZ_LOG ZZ_EVENTS
#endif
#ifndef SIM
#define ZZ_LOG ZZ_LIVE_EVENTS
#endif
#define ZZ_LIVE_LOOKBACK 180000    // about 130 sessions; the state locks on after about 65 (warm_check.py)
// what an open trade needs after a restart, kept with the trade
#define TV_SL TradeVar[0]
#define TV_TARGET TradeVar[1]
#define TV_TP TradeVar[2]
#define TV_BARS TradeVar[3]

#define VOL_N 60
#define MAX_BARS 60000
#define NOTIONAL 1000000
#define NO_D 1e30          // threshold before 60 sessions of returns exist: nothing confirms
#define COMM_TICKS (4.5 / ZZ_TICK_USD)

// events: 1 session (a = session count, b = d)            2 confirmation (a = index, b = dir, c = pivot px,
//         d = entry px, e = d in force, f = traded)        3 trade opened (a = dir, b = fill, c = stop, d = target,
//         e = lots)   4 trade closed (a = dir, b = open px, c = close px, d = reason 1 stop 2 target 0 other,
//         e = lots, f = open time, g = profit)             9 warning (a = code: 1 two positions open,
//         2 a fill without a traded confirmation or the reverse)
//         8 take-profit touched (a = traded through, b..d = the bar's open, high, low as the TMF sees them,
//         e = limit, f = trade-through level)
void logEvent(int kind, var v1, var v2, var v3, var v4, var v5, var v6, var v7)
{
	if(!robustLogging()) return;
#ifndef SIM
	if(is(LOOKBACK)) return;
#endif
	file_append(ZZ_LOG, strf("%.10f,%i,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g\n", wdate(0), kind, v1, v2, v3, v4, v5, v6, v7));
}

// US Eastern time from UTC (DST rules from 2007): Zorro's own zone table is only documented to 2024.
int dowOle(var t) { return ((int)floor(t) + 6) % 7; }          // 0 = Sunday
var etFromUtc(var t)
{
	int y = ymd(t) / 10000;
	var mar1 = dmy(y * 10000 + 301);
	var nov1 = dmy(y * 10000 + 1101);
	var dstStart = mar1 + ((7 - dowOle(mar1)) % 7) + 7 + 7. / 24;   // second Sunday of March, 02:00 EST
	var dstEnd = nov1 + ((7 - dowOle(nov1)) % 7) + 6. / 24;         // first Sunday of November, 02:00 EDT
	if(t >= dstStart && t < dstEnd) return t - 4. / 24;
	return t - 5. / 24;
}

// Zorro keeps order levels and fill prices as 32-bit floats; rounding every level the same way keeps this
// script's own zigzag in step with Zorro's fills.
var f32(var x) { float y = x; return y; }

int ZBar, ZState, HiI, LwI, NSig, NSess, HavePrevSess, NR, RestTake, Pos, PosBar, FI;
var Hi, Lw, Ext, PivPrev, DsigPrev, Seg1, Seg2, RestLvl, RestD, RestE, CurSess, LastLogC, PrevSessC, D;
var PosSL, PosTP, PosTarget, Avg3Cut;
var RetSq[VOL_N];

var factorNow()
{
	int m = (int)floor(wdate(0) * 1440 + 0.5);      // bar close in whole minutes since 1899-12-30
	while(FI + 1 < ZZ_NF && ZZ_FT[FI + 1] <= m) FI++;
	return ZZ_FV[FI];
}

int zzTMF()
{
	if(TradeIsClosed && !TradeIsUnfilled) {          // a filled trade that just closed (not an expired entry order)
		int reason = 0;
		if(TradeIsStop) reason = 1;
		else if(TradeIsProfit) reason = 2;
		logEvent(4, TradeDir, TradePriceOpen, TradePriceClose, reason, TradeLots, TradeDate, TradeProfit);
	} else if(TradeIsOpen && !TradeIsStop && TradeIsProfit) {
		// TradeIsProfit stays set after a vetoed touch, so a later STOP event must be recognised first.
		// The limit rests AT the target, so it fills there (or at the open on a gap), as the engine's does. But the
		// engine counts it only when the bar trades one tick through the target (PosTP); a mere touch stays open.
		// Zorro prices the fill before the TMF runs, so the check has to veto the exit rather than move the limit.
		int through = ifelse(TradeIsLong, priceHigh(0) >= PosTP, priceLow(0) <= PosTP);
		logEvent(8, through, priceOpen(0), priceHigh(0), priceLow(0), TradeProfitLimit, PosTP, 0);
		if(!through) return 4 + 16;                  // touched, not traded through: wait for the next hit
		TradeCommission *= (0.5 + COMM_TICKS) / (1. + COMM_TICKS);   // a limit fill pays no half-tick charge
	}
	return 16;              // run only at entry, stop / target exits and after the close
}

void confirm(int dir, var piv, var entryPx)
{
	int k = NSig;
	if(k >= 1) {
		Seg2 = Seg1;
		Seg1 = abs(piv - PivPrev) / DsigPrev;                        // the leg that ends at this pivot
	}
	logEvent(2, k, dir, exp(piv), entryPx, RestD, (ZState != 0 && RestTake), 0);
	PivPrev = piv;
	DsigPrev = RestD;
	NSig = k + 1;
}

void placeEntry(int dir, var factor)
{
	Entry = RestE;                                   // stop entry at the confirmation level, moved every bar
	EntryTime = 1000000;                             // rests until filled or cancelled by the script
	Stop = 0; TakeProfit = 0;                        // set from the fill at the next close
#ifdef SIM
	Lots = (int)(NOTIONAL / RestE);                  // sized once, when the order is first placed
	Commission = ZZ_TICK * factor * (1. + COMM_TICKS) * robustCostMult();
#else
	Lots = ZZ_LIVE_LOTS;                             // whole contracts; the broker charges the real cost
#endif
	if(dir > 0) enterLong(zzTMF); else enterShort(zzTMF);
}

function run()
{
	BarPeriod = 1;
	robustBars(0);              // Robust.h modes; 1-minute bars have no bar start to move
	Outlier = 1000;             // off: the default suppresses 1-minute moves over ~15%, which were real in April 2020
	BarMode = 0;                // every bar in the history, no weekend or holiday skipping
	LookBack = 0;
	StartDate = 20100606;
#ifdef LIVE
	LookBack = ZZ_LIVE_LOOKBACK;
	StartDate = 20250919;       // LIVETEST; trade mode starts now and ignores it
#endif
#ifdef SIM
	EndDate = 20260919;
	robustCapital(NOTIONAL);
	assetList("AssetsZZ");
	asset(ZZ_ASSET);
	Spread = 0; Slippage = 0; Penalty = 0;
	Fill = 1;                   // stops fill at the level or at the open when the bar gaps through it
	Hedge = 2;                  // the reversal's exit and entry are separate orders on the same bar
	setf(TradeMode, TR_FRC);    // no rounding of fills to the point size
#else
	set(PRELOAD);               // the lookback comes from our .t6 history, the broker fills the days after it
	set(LOGFILE);
	assetList("AssetsLive");
	asset(ZZ_ASSET);
	Hedge = 4;                  // IB keeps one net position (NFA): Zorro holds the exit and the entry as separate
	                            // trades and sends the net
#endif

	int k;
	if(is(INITRUN)) {
		ZBar = 0; ZState = 0; NSig = 0; NSess = 0; HavePrevSess = 0; NR = 0; RestTake = 0; Pos = 0; FI = 0;
		D = NO_D; RestD = NO_D; Seg1 = 0; Seg2 = 0; PivPrev = 0; DsigPrev = 1;
		Avg3Cut = 2. - 0.67 / sqrt(3.);
		for(k = 0; k < VOL_N; k++) RetSq[k] = 0;
#ifdef SIM
		if(robustLogging()) {
			file_delete(ZZ_LOG);
			file_append(ZZ_LOG, "ole_utc,type,a,b,c,d,e,f,g\n");
		}
#endif
		return;                 // the first run comes before any prices are loaded
	}

	var o = priceOpen(0);
	var h = priceHigh(0);
	var l = priceLow(0);
	var c = priceClose(0);
	var lo = log(o);
	var lh = log(h);
	var ll = log(l);
	var factor = factorNow();

	// --- 1. zigzag, with the level that rested through this bar ---
	int confirmed = 0;                                 // direction of a leg confirmed on this bar
	if(ZBar == 0) {
		Hi = lh; HiI = 0; Lw = ll; LwI = 0;
	} else if(ZState == 0) {                           // before the first leg: the research engine's own rule
		if(lh > Hi) { Hi = lh; HiI = ZBar; }
		if(ll < Lw) { Lw = ll; LwI = ZBar; }
		if(Hi - Lw >= RestD) {
			var lvl;
			if(HiI > LwI) {
				lvl = Lw + RestD;
				confirm(1, Lw, exp(ifelse(lo > lvl, lo, lvl)));
				ZState = 1; Ext = lh;
			} else if(LwI > HiI) {
				lvl = Hi - RestD;
				confirm(-1, Hi, exp(ifelse(lo < lvl, lo, lvl)));
				ZState = -1; Ext = ll;
			} else {
				Hi = lh; HiI = ZBar; Lw = ll; LwI = ZBar;
			}
		}
	} else if(ZState == 1) {
		if(l <= RestE) {
			confirm(-1, Ext, min(o, RestE));
			ZState = -1; Ext = ll; confirmed = -1;
		} else if(lh > Ext) Ext = lh;
	} else {
		if(h >= RestE) {
			confirm(1, Ext, max(o, RestE));
			ZState = 1; Ext = lh; confirmed = 1;
		} else if(ll < Ext) Ext = ll;
	}

	// --- 2. position: what Zorro filled and closed during this bar ---
	int expectEntry = (confirmed && RestTake && Pos != confirmed);   // a traded confirmation must have filled
	int nOpen = 0;
	int newDir = 0;
	for(open_trades) {
		if(!TradeIsOpen) continue;
		nOpen++;
		if(TradeStopLimit == 0) {                      // filled this bar: exits from the fill, as the engine does
			var le = log(TradePriceOpen);
			var dsig = RestD;
			var through = 1. + ZZ_TICK * factor / TradePriceOpen;      // one raw tick, on the adjusted scale
			if(TradeIsLong) {
				PosSL = f32(exp(le - ZZ_SL * dsig));
				PosTarget = f32(exp(le + ZZ_TP * dsig));
				PosTP = f32(exp(le + ZZ_TP * dsig) * through);
			} else {
				PosSL = f32(exp(le + ZZ_SL * dsig));
				PosTarget = f32(exp(le - ZZ_TP * dsig));
				PosTP = f32(exp(le - ZZ_TP * dsig) / through);
			}
			TradeStopLimit = PosSL;
			TradeProfitLimit = PosTarget;
			newDir = TradeDir;
			PosBar = ZBar;
			logEvent(3, TradeDir, TradePriceOpen, PosSL, PosTP, TradeLots, 0, 0);
#ifndef SIM
			TV_SL = PosSL; TV_TARGET = PosTarget; TV_TP = PosTP; TV_BARS = 0;
		} else {
			// open from an earlier bar, or resumed by Zorro after a restart: the script's own copy of its exits
			// is gone after a restart, the trade's is not
			TV_BARS += 1;
			PosSL = TV_SL; PosTarget = TV_TARGET; PosTP = TV_TP;
			PosBar = ZBar - (int)TV_BARS;
			if(Pos == 0) newDir = TradeDir;
#endif
		}
	}
	if(newDir != 0) Pos = newDir;
	else if(nOpen == 0) Pos = 0;
	if(nOpen > 1) logEvent(9, 1, nOpen, 0, 0, 0, 0, 0);
	if(expectEntry != (newDir != 0)) logEvent(9, 2, expectEntry, newDir, 0, 0, 0, 0);

	// time exit, at this bar's close
	if(Pos != 0 && ZBar == PosBar + MAX_BARS) {
		if(Pos > 0) exitLong(); else exitShort();
		Pos = 0;
	}

	// --- 3. session and threshold; the new threshold applies from the next bar ---
	var sess = floor(etFromUtc(wdate(0)) - 0.5 / 1440 + 0.25);   // bar start + 6h, ET date (bar stamped at its close)
	if(ZBar == 0) CurSess = sess;
	else if(sess != CurSess) {
		if(HavePrevSess) {
			var r = LastLogC - PrevSessC;
			RetSq[NR % VOL_N] = r * r;
			NR++;
		}
		PrevSessC = LastLogC;
		HavePrevSess = 1;
		CurSess = sess;
		NSess++;
		if(NR >= VOL_N) {
			var acc = 0;
			for(k = 0; k < VOL_N; k++) acc += RetSq[k];
			D = log(1. + ZZ_K * sqrt(acc / VOL_N));
		}
		logEvent(1, NSess, D, 0, 0, 0, 0, 0);
	}
	LastLogC = log(c);

	// --- 4. resting orders for the next bar ---
	int wantDir = 0;                                   // direction of the entry order wanted for the next bar
	RestD = D;
	if(ZState != 0) {
		RestLvl = Ext - ZState * RestD;
		RestE = f32(exp(RestLvl));
		var prev = abs(Ext - PivPrev) / DsigPrev;
		if(ZZ_PREV_FILTER) RestTake = (NSig >= 3 && prev < 1.5);
		else RestTake = (NSig >= 3 && (Seg2 + Seg1 + prev) / 3 < Avg3Cut);
		int dirNext = -ZState;
		if(Pos != 0) {
			var stop = PosSL;
			if(Pos == -dirNext && (ZZ_REV || RestTake)) {         // the next confirmation exits this position
				if(Pos > 0) stop = max(PosSL, RestE); else stop = min(PosSL, RestE);
			}
			for(open_trades) if(TradeIsOpen) { TradeStopLimit = stop; TradeProfitLimit = PosTarget; }
		}
		if(RestTake && Pos != dirNext) wantDir = dirNext;           // flat, or the next leg reverses the position
	}
	// One resting entry order, moved every bar. A fresh order each bar would leave millions of expired orders in
	// Zorro's trade list; that ran the 32-bit Zorro out of memory in July 2024 (Errors 049 and 036).
	int havePend = 0;
	for(open_trades) if(TradeIsPending) {
		if(wantDir != 0 && !havePend && TradeIsLong == (wantDir > 0)) {
			TradeEntryLimit = RestE;
			havePend = 1;
		} else exitTrade(ThisTrade);                               // cancel an order no longer wanted
	}
	if(wantDir != 0 && !havePend) placeEntry(wantDir, factor);
	ZBar++;
}
