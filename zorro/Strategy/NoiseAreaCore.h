// NoiseAreaCore.h -- "Noise Area" intraday momentum (Zarattini, Aziz & Barbon 2024), the rules of NoiseArea.c
// with VWAP computed in the script and the Robust.h battery wired in. Needs Zorro S (marketVol).
//
// The wrapper defines, before including this file:
//   NA_ASSET        asset name, e.g. "QQQ"
//   NA_ASSETLIST    asset list, e.g. "AssetsNoiseArea"
//   NA_NF, NA_FT, NA_FV   dividend factor table (NAFactors.h)
//   NA_COST         round-trip cost per lot (a share, a contract), e.g. 0.017
// and may define:
//   NA_LOTS         a fixed number of lots (default: 1x NOTIONAL in lots of one unit, as for QQQ shares)
//   NA_LIVE_LOOKBACK  live lookback in bars (default 6240 = 16 sessions of regular-hours bars)
//   NA_START, NA_END      test window, yyyymmdd
//   NA_SIGNAL_LOG   parity log path, forward slashes
// and includes <default.c>, the factor table and "Robust.h" first.
//
// Rules
//   sigma(m) = mean over the prior 14 full sessions of |close(m) / open(09:30) - 1|, per minute of the day
//   Upper    = max(today's open, prior close) * (1 + sigma)
//   Lower    = min(today's open, prior close) * (1 - sigma)
//   VWAP     = session sum of typical price x volume / sum of volume, regular hours; the close until volume trades
//   Checks at 10:00, 10:30 ... 15:30 on the close of the bar ending then; fills at the NEXT bar's open.
//   Flat: long above Upper, short below Lower. Long exits below max(Upper, VWAP); short exits above
//   min(Lower, VWAP); then the entry rule is applied again at the same check. Flat at the 16:00 close.
//   Live only: on a session where a bar loaded before the start had no volume (IB's history bars carry none),
//   the VWAP is not known, and the exit is the opposite band until the close (long below Lower, short above Upper).
//   1x notional (or NA_LOTS lots), cost NA_COST per lot round trip.
//
// Why VWAP is computed here: NoiseArea.c reads it from a second asset (QQQVW). A shuffled-price reality check
// would shuffle that asset separately from the traded one, so the exit rule would compare unrelated curves.
// Here the shuffled prices carry their own VWAP (volume is not shuffled).

#define LOOKBACK_SESSIONS 14
#define NBARS 390          // 1-minute bars, 09:30 -> 16:00 ET
#define DONE_IDX 385       // a session counts only if it has a bar starting 15:55 or later
#define NOTIONAL 100000

// -d LIVE (trade mode) trades QQQ shares on the paper account. The 14-session state is rebuilt on every start from
//   NA_LIVE_LOOKBACK bars (16 sessions): PRELOAD reads them from our .t6 history and the broker fills the days after
//   it. Orders go out only after the lookback, so at its end the sleeve takes the position the rule holds then
//   (a start in the middle of a trade enters at once). The dividend factor table ends with the history, so a new ex-dividend date needs the
//   history and NAFactors.h exported again (export_t6.py) before it.
// -d LIVETEST (test mode) runs the same start on history, with the backtest's costs and fills.
#ifdef LIVETEST
#define LIVE
#define SIM
#endif
#ifndef LIVE
#define SIM
#endif
#ifndef NA_LIVE_LOOKBACK
#define NA_LIVE_LOOKBACK 6240
#endif
// The last bar closes at 16:00 sharp, when the market has shut: a market order sent then waits for tomorrow's open
// and the sleeve would hold overnight. Live flattens on the bar closing 15:59 instead.
#ifdef LIVE
#define NA_FLAT_IDX 388
#else
#define NA_FLAT_IDX 389
#endif

var Ring[5460];            // NBARS * LOOKBACK_SESSIONS: [minute index * 14 + session column]
var Today[390];
int Committed, LastIdx, StartOk, CurDate, Pos, FI, NaShown, Synced, DayNoVol;
var DayOpen, DayFactor, LastClose, LastFactor, CprevRaw, CprevFactor, CumPV, CumV, PrevAcc;

// action: 1 long, -1 short, 0 exit on the stop, 9 flat at the close, 2 check with no action,
//         3 / -3 long / short entered at the end of the lookback (the rule held it then)
void logSignal(int action, var P, var UB, var LB, var VWAP)
{
	if(!robustLogging()) return;
	file_append(NA_SIGNAL_LOG, strf("%.8f,%i,%.4f,%.4f,%.4f,%.4f\n", wdate(0), action, P, UB, LB, VWAP));
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

int naLots(var P)
{
#ifdef NA_LOTS
	return NA_LOTS;
#else
	return (int)(NOTIONAL / P);
#endif
}

var factorNow()
{
	int m = (int)floor(wdate(0) * 1440 + 0.5);      // bar close in whole minutes since 1899-12-30
	while(FI + 1 < NA_NF && NA_FT[FI + 1] <= m) FI++;
	return NA_FV[FI];
}

#include "Heartbeat.h"
#include "LiveRestart.h"
#include "ExpiryGuard.h"

function run()
{
	BarPeriod = 1;
	BarMode = 0;               // every bar in the history: the default week end blocked Friday 16:00 close-outs
	Outlier = 1000;            // off: never let Zorro "repair" a real price move
	LookBack = 0;              // the 14-session warm-up is handled below, not by Zorro's series
	StartDate = NA_START;
	EndDate = NA_END;
#ifdef LIVE
	LookBack = NA_LIVE_LOOKBACK;
	StartDate = 20250101;      // LIVETEST; trade mode starts now and ignores it
#endif
#ifdef LIVETEST
	if(Command[1]) EndDate = Command[1];   // the daily paper replay (backtest_core.zorro.paper) runs to the history's end
#endif
	robustBars(0);
#ifdef SIM
	robustCapital(NOTIONAL);
	assetList(NA_ASSETLIST);
	asset(NA_ASSET);
	Spread = 0;                // the tick is inside the commission, as in the Python engine
	Slippage = 0;
	Commission = NA_COST * robustCostMult();
	Fill = 3;                  // market orders fill at the next bar's open
#ifdef HEDGE0
	Hedge = 0;                 // test build: one position per asset, as the live account allows
#endif
#else
	set(PRELOAD);              // the lookback comes from our .t6 history, the broker fills the days after it
	set(LOGFILE);
	set(NOLOCK);               // own API connection; see ZigZagCore.h
	// Regular hours only, as the backtest's history. IB sends QQQ quotes through the night, and without this Zorro
	// made a bar every clock minute: the 6,240-bar lookback then held about 4 sessions, the script never committed the
	// 14 it needs, and it made no check from 2026-10-06 on. BarZone is UTC; the hours follow New York's daylight time
	// on the day the sleeve starts (it starts every week).
	var etOff = (wdate(NOW) - etFromUtc(wdate(NOW))) * 24;           // 4 or 5 hours
	StartMarket = 930 + (int)(etOff + 0.5) * 100;
	EndMarket = 1601 + (int)(etOff + 0.5) * 100;
	StartWeek = 10000;         // Monday 00:00 UTC
	EndWeek = 52359;           // Friday 23:59 UTC
	BarMode = BR_MARKET + BR_WEEKEND + BR_SLEEP;
	assetList("AssetsLive");
	asset(NA_ASSET);
	Hedge = 0;                 // IB keeps one net position (NFA), so Zorro does too. The backtest gives the same trades
	nfaOn();
#endif

	int k;
	if(is(INITRUN)) {
		liveRestart();
		expiryGuard();
#ifndef SIM
		brokerCommand(SET_VOLTYPE, 4);   // trade volume, for the broker's history and live bars; IB's default is quote size
#endif
		Committed = 0; LastIdx = -1; StartOk = 0; CurDate = 0; Pos = 0; FI = 0; NaShown = 0; Synced = 0;
		CprevRaw = 0; CprevFactor = 1; CumPV = 0; CumV = 0; PrevAcc = 0; DayNoVol = 0;
		for(k = 0; k < 5460; k++) Ring[k] = 0;
#ifdef SIM
		if(robustLogging()) {
			file_delete(NA_SIGNAL_LOG);
			file_append(NA_SIGNAL_LOG, "ole_utc,action,price,upper,lower,vwap\n");
		}
#else
		if(!file_length(NA_SIGNAL_LOG)) file_append(NA_SIGNAL_LOG, "ole_utc,action,price,upper,lower,vwap\n");
#endif
		return;                // the first run comes before any prices are loaded
	}
	hbBar();
#ifndef SIM
	if(!is(LOOKBACK) && !NaShown) {   // the start's proof: 14 or more, or the sleeve cannot trade yet
		NaShown = 1;
		printf("\nLookback done: %i full sessions committed (%i needed)", Committed, LOOKBACK_SESSIONS);
	}
#endif

	var et = etFromUtc(wdate(0));                                        // bar CLOSE time, New York
	int minuteOfDay = (int)floor((et - floor(et)) * 1440 + 0.5);
	int idx = minuteOfDay - 570 - 1;                                     // 0 = bar starting 09:30
	if(idx < 0 || idx >= NBARS) return;
	int today = ymd(et);
	var factor = factorNow();

	// New session: commit yesterday to the lookback if it was a full session.
	if(today != CurDate) {
		if(CurDate != 0 && StartOk && LastIdx >= DONE_IDX) {
			var lastMove = abs(LastClose / DayOpen - 1);
			for(k = LastIdx + 1; k < NBARS; k++) Today[k] = lastMove;   // missing minutes carry the last close
			int col = Committed % LOOKBACK_SESSIONS;
			for(k = 0; k < NBARS; k++) Ring[k * LOOKBACK_SESSIONS + col] = Today[k];
			Committed++;
			CprevRaw = LastClose;
			CprevFactor = LastFactor;
		}
		CurDate = today;
		DayOpen = priceOpen(0);
		DayFactor = factor;
		StartOk = (idx == 0);
		LastIdx = -1;
		Pos = 0;
		CumPV = 0;
		CumV = 0;
		PrevAcc = 0;
		DayNoVol = 0;
		for(k = 0; k < NBARS; k++) Today[k] = 0;
	}

	// Record this minute's move (carrying the last close over any missing minutes).
	if(LastIdx >= 0 && idx > LastIdx + 1) {
		var fillMove = abs(LastClose / DayOpen - 1);
		for(k = LastIdx + 1; k < idx; k++) Today[k] = fillMove;
	}
	var P = priceClose(0);
	Today[idx] = abs(P / DayOpen - 1);
	LastIdx = idx;
	LastClose = P;
	LastFactor = factor;

	var vol = marketVol(0);
#ifndef SIM
	// Live, IB reports the day's running volume (ib.txt), history the volume of each minute. A live bar's volume is
	// the change since the last live bar; the first live bar of a session or of a start has no earlier total and
	// counts nothing.
	if(!is(LOOKBACK)) {
		var acc = vol;
		vol = 0;
		if(PrevAcc > 0 && acc >= PrevAcc) vol = acc - PrevAcc;
		PrevAcc = acc;
	} else if(vol <= 0) {
		DayNoVol = 1;
	}
#endif
	CumPV += (priceHigh(0) + priceLow(0) + P) / 3 * vol;
	CumV += vol;
	var VWAP = P;
	if(CumV > 0) VWAP = CumPV / CumV;

	if(Committed < LOOKBACK_SESSIONS || CprevRaw <= 0) return;

	var acc = 0;
	for(k = 0; k < LOOKBACK_SESSIONS; k++) acc += Ring[idx * LOOKBACK_SESSIONS + k];
	var sigma = acc / LOOKBACK_SESSIONS;
	var cprev = CprevRaw * CprevFactor / DayFactor;          // yesterday's close on today's price scale
	var UB = max(DayOpen, cprev) * (1 + sigma);
	var LB = min(DayOpen, cprev) * (1 - sigma);

#ifdef LIVE
	// The lookback runs the rule but sends no order: at its end, hold what the rule holds.
	if(!is(LOOKBACK) && !Synced) {
		Synced = 1;
#ifndef SIM
		if(DayNoVol) printf("\nNo volume before the start today: the exit is the opposite band until the close");
#endif
		if(idx < NA_FLAT_IDX && Pos == 1 && !NumOpenLong) {
			Lots = naLots(P);
			enterLong(); logSignal(3, P, UB, LB, VWAP);
		} else if(idx < NA_FLAT_IDX && Pos == -1 && !NumOpenShort) {
			Lots = naLots(P);
			enterShort(); logSignal(-3, P, UB, LB, VWAP);
		}
	}
#endif

	// Checks: bars closing 10:00, 10:30 ... 15:30.
	if(idx >= 29 && idx <= 359 && (idx + 1) % 30 == 0) {
		int acted = 0;
		var longStop = max(UB, VWAP);
		var shortStop = min(LB, VWAP);
		if(DayNoVol) { longStop = LB; shortStop = UB; }
		if(Pos == 1 && P < longStop) {
			exitLong(); Pos = 0; acted = 1; logSignal(0, P, UB, LB, VWAP);
		} else if(Pos == -1 && P > shortStop) {
			exitShort(); Pos = 0; acted = 1; logSignal(0, P, UB, LB, VWAP);
		}
		if(Pos == 0) {
			if(P > UB) {
				Lots = naLots(P);
				enterLong(); Pos = 1; acted = 1; logSignal(1, P, UB, LB, VWAP);
			} else if(P < LB) {
				Lots = naLots(P);
				enterShort(); Pos = -1; acted = 1; logSignal(-1, P, UB, LB, VWAP);
			}
		}
		if(!acted) logSignal(2, P, UB, LB, VWAP);
	}

	// Flat at the 16:00 close, filled at this bar's close rather than tomorrow's open.
	if(idx == NA_FLAT_IDX && Pos != 0) {
		Fill = 1;
		if(Pos == 1) exitLong(); else exitShort();
		Pos = 0;
		logSignal(9, P, UB, LB, VWAP);
	}
}
