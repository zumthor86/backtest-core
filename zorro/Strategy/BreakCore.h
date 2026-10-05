// BreakCore.h -- slow-approach break of an old zigzag level, on 1-minute futures bars.
// Included by BreakGC.c and BreakES.c, which set the BK_* parameters.
// Port of Hermes/notebooks/zigzag_segment_bootstrap/break_honest.py variant C (the causal version of break_trade.py:
// every first touch, a stop entry that must actually trade). break_parity.py compares this script's event log with
// a Python mirror of the same bar loop (break_mirror.py) and the research engine.
//
// Rules
//   d        = log(1 + k * sigma), sigma = RMS of daily log returns over the previous 60 sessions (18:00 ET sessions),
//              in force from the first bar of each session.
//   Zigzag   as zz_engine.zigzag_var: a pivot is recorded when price moves d off the running extreme.
//   Level    pivot j becomes a level once pivot j+1 is recorded; it is live for 20 sessions from pivot j's session.
//   Touch    the first bar that trades at or through a live level.
//   Speed    (bars since the last extreme before the touch / mean bars per session over the previous 60 sessions)
//            / (distance from that extreme to the level / d). Slow = top tercile of all earlier touches (causal,
//            after 200 touches).
//   Entry    for a slow touch: a stop one tick through the level (fills there, or at the open on a gap). It rests
//            from the bar before the touch (when the touch would be slow) until filled, until price reaches the
//            stop level first, or for 20 sessions. A stop that trades while a position is open is dropped.
//   Exits    from the stop price S: target S + r*d (needs a one-tick trade-through, fills at the target), stop S - r*d
//            (not on the fill bar), and at the close of the first bar more than 20 sessions after the fill.
//   One position at a time; when flat, the nearest long and the nearest short stop rest.
//   Costs: half a tick on entry and on stop exits, plus $4.50 per contract.
//
// Sizing: 1 unit = 1 point of the adjusted price (History/AssetsZZ.csv); NOTIONAL / price units per trade.

#include "ZZFactors.h"

// Zorro takes one -d name per run, so the export to the end of the history is its own name.
#ifdef STATE_LATEST
#define STATE
#endif

// -d STATE (test mode) writes every touch of the full run (time, speed) to BK_STATE.
// -d LIVE (trade mode) trades BK_LIVE_LOTS whole contracts of the real contract behind BK_ASSET in
//   History/AssetsLive.csv. The zigzag, the levels and the armed stops are rebuilt on every start from
//   BK_LIVE_LOOKBACK bars (PRELOAD reads them from our .t6 history, the broker fills the days after it). "Slow"
//   is a rank against every touch since 2010, which no lookback Zorro can load reaches, so those speeds come
//   from BK_STATE: each bar first takes the full run's touches up to that bar, and the sleeve's own touches
//   count only after the file ends. The history is on the adjusted scale, which equals the traded contract's
//   prices only since the last roll, so history and state must be exported again after every roll and the asset
//   list must name the contract the history ends on. A sleeve always starts flat or with the trades Zorro
//   resumes.
// -d LIVETEST (test mode) runs that start on history: BK_STATE up to BK_STATE_CUT, BK_LIVE_LOOKBACK bars of
//   lookback before 2025-09-19, then the backtest's own sizing and costs. Its events must equal the full run's
//   (zigzag_zorro/break_live_check.py).
// SIM = simulated fills on the adjusted history: every test-mode run.
#ifdef LIVETEST
#define LIVE
#define SIM
#define BK_LOG BK_WARM_EVENTS
#endif
#ifndef LIVE
#define SIM
#define BK_LOG BK_EVENTS
#endif
#ifndef SIM
#define BK_LOG BK_LIVE_EVENTS
#endif
#define BK_LIVE_LOOKBACK 250000    // about 180 sessions: 60 for the threshold, the zigzag, then 20-session levels
#define BK_STATE_CUT 45919.        // LIVETEST: 2025-09-19 00:00 UTC, as an OLE date
#define HALF_MIN (0.5 / 1440)
// what an open trade needs after a restart, kept with the trade
#define TV_TP TradeVar[0]
#define TV_SESS TradeVar[1]

#define VOL_N 60
#define NOTIONAL 1000000
#define NO_D 1e30
#define WINDOW 20
#define SEED_N 200
#define MAXP 30000
#define MAXW 400
#define MAXA 400
#define COMM_TICKS (4.5 / BK_TICK_USD)

// events: 1 session (a = session, b = d, c = bars per session)   2 pivot (a = index, b = dir, c = log px, d = bar)
//         5 touch (a = pivot, b = level (log), c = speed, d = tercile, e = bar)
//         6 armed (a = pivot, b = stop (log), c = d at touch)     7 drop (a = pivot, b = reason 1 traded while busy,
//         2 stop level first, 3 window)
//         3 trade opened (a = dir, b = fill, c = stop, d = trade-through target, e = lots, f = pivot)
//         4 trade closed (a = dir, b = open px, c = close px, d = reason 1 stop 2 target 0 other, e = lots,
//         f = open time, g = profit)   8 take-profit touched   9 warning (a = 1 two positions)
void logEvent(int kind, var v1, var v2, var v3, var v4, var v5, var v6, var v7)
{
	if(!robustLogging()) return;
#ifndef SIM
	if(is(LOOKBACK)) return;
#endif
	file_append(BK_LOG, strf("%.10f,%i,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g\n", wdate(0), kind, v1, v2, v3, v4, v5, v6, v7));
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
var f32(var x) { float y = x; return y; }

// zigzag (research engine's own rule)
int ZBar, ZState, HiI, LwI, ExtI, HiS, LwS, ExtS, NP, FI;
var LEV; int LEB;                                 // lastExtreme() result
var Hi, Lw, Ext;
var PivV[MAXP]; int PivI[MAXP]; int PivS[MAXP]; int PivDir[MAXP];
// sessions
int SessN, HavePrevSess, NR, NB, BarsInSess;
var CurSess, LastLogC, PrevSessC, D, BB;
var RetSq[VOL_N]; var SessBars[VOL_N];
// levels: watched pivots, armed stops, and the touch-speed history
int W[MAXW]; int NW;
int AP[MAXA]; var AS[MAXA]; var AD[MAXA]; var ATk[MAXA]; int ABar[MAXA]; int ASess[MAXA]; int NA;
var Seen[MAXP]; int NSeen;
// orders and position
int PendP[2]; var PendS[2]; var PendD[2]; var PendTk[2];      // [0] long, [1] short: pivot, stop, d, tick
int Pos, PosSessEnd, TimeExit;
var PosTP;

var factorNow()
{
	int m = (int)floor(wdate(0) * 1440 + 0.5);
	while(FI + 1 < BK_NF && BK_FT[FI + 1] <= m) FI++;
	return BK_FV[FI];
}

int bkTMF()
{
	if(TradeIsClosed && !TradeIsUnfilled) {
		int reason = 0;
		if(TradeIsStop) reason = 1;
		else if(TradeIsProfit) reason = 2;
		logEvent(4, TradeDir, TradePriceOpen, TradePriceClose, reason, TradeLots, TradeDate, TradeProfit);
	} else if(TradeIsOpen && !TradeIsStop && TradeIsProfit) {
		int through = ifelse(TradeIsLong, priceHigh(0) >= PosTP, priceLow(0) <= PosTP);
		logEvent(8, through, priceOpen(0), priceHigh(0), priceLow(0), TradeProfitLimit, PosTP, 0);
		if(!through) return 4 + 16;
		TradeCommission *= (0.5 + COMM_TICKS) / (1. + COMM_TICKS);   // a limit fill pays no half-tick charge
	}
	return 16;
}

void recordPivot(int dir, var v, int bar, int sess)
{
	if(NP >= MAXP) { logEvent(9, 3, NP, 0, 0, 0, 0, 0); return; }
	PivV[NP] = v; PivI[NP] = bar; PivS[NP] = sess; PivDir[NP] = dir;
	logEvent(2, NP, dir, v, bar, 0, 0, 0);
	if(NP >= 1 && NW < MAXW) W[NW++] = NP - 1;       // the previous pivot is now a level
	NP++;
}

// the last extreme before bar `bar`, on the side a level of type `hiLevel` is approached from
void lastExtreme(int hiLevel)
{
	int wantDir = -1;
	if(hiLevel) wantDir = 1;                          // a high level is approached from a low (pivot dir 1)
	if(NP > 0 && PivDir[NP - 1] == wantDir) { LEV = PivV[NP - 1]; LEB = PivI[NP - 1]; }
	else { LEV = Ext; LEB = ExtI; }
}

var speedAt(int j, int bar)
{
	if(!(BB > 0) || D >= NO_D) return -1;
	lastExtreme(PivDir[j] == -1);
	var dist = abs(PivV[j] - LEV) / D;
	return ((var)(bar - LEB) / BB) / max(dist, 1e-9);
}

int tercile(var x)
{
	if(x < 0 || NSeen < SEED_N) return -1;
	int a = 0;                                        // upper bound: count of seen <= x
	int b = NSeen;
	int mid;
	while(a < b) { mid = (a + b) / 2; if(Seen[mid] <= x) a = mid + 1; else b = mid; }
	var p = (var)a / NSeen;
	if(p <= 1. / 3) return 0;
	if(p > 2. / 3) return 2;
	return 1;
}

void insertSeen(var x)
{
	if(x < 0 || NSeen >= MAXP) return;
	int k = NSeen;
	while(k > 0 && Seen[k - 1] > x) { Seen[k] = Seen[k - 1]; k--; }
	Seen[k] = x; NSeen++;
}

#ifdef LIVE
// the full run's touches, in time order: "ole date,speed" per line
var StT[MAXP]; var StV[MAXP]; int NSt, StI;
var StEnd;

void loadTouches()
{
	string txt = file_content(BK_STATE);
	string line;
	string comma;
	NSt = 0; StI = 0; StEnd = 0;
	if(!txt) { printf("\n%s missing: export it with -d STATE", BK_STATE); return; }
	line = strtok(txt, "\n");
	while(line && NSt < MAXP) {
		comma = strchr(line, ',');
		if(comma) {
#ifdef LIVETEST
			if(atof(line) >= BK_STATE_CUT) break;
#endif
			StT[NSt] = atof(line); StV[NSt] = atof(comma + 1); NSt++;
		}
		line = strtok(0, "\n");
	}
	if(NSt > 0) StEnd = StT[NSt - 1];
	printf("\n%s: %i touches to %i", BK_STATE, NSt, ymd(StEnd));
}

// the full run's touches on earlier bars
void seenBefore(var t) { while(StI < NSt && StT[StI] < t - HALF_MIN) { insertSeen(StV[StI]); StI++; } }

// A touch on this bar. While the state file covers the bar, the file's touch counts, not the sleeve's own: the
// sleeve's zigzag is not locked on yet early in the lookback.
void seenTouch(var t, var sp)
{
	if(t > StEnd + HALF_MIN) insertSeen(sp);
	else if(StI < NSt && StT[StI] < t + HALF_MIN) { insertSeen(StV[StI]); StI++; }
}
#endif

var tickLog(var c, var factor) { return log(1. + BK_TICK / (exp(c) / factor)); }

function run()
{
	BarPeriod = 1;
	robustBars(0);              // Robust.h modes; 1-minute bars have no bar start to move
	Outlier = 1000;
	BarMode = 0;
	LookBack = 0;
	StartDate = 20100606;
#ifdef LIVE
	LookBack = BK_LIVE_LOOKBACK;
	StartDate = 20250919;       // LIVETEST; trade mode starts now and ignores it
#endif
#ifdef SIM
	EndDate = 20260919;
#ifdef STATE_LATEST
	EndDate = Command[1];        // a state export for a live start runs to the end of the history
#endif
	robustCapital(NOTIONAL);
	assetList("AssetsZZ");
	asset(BK_ASSET);
	Spread = 0; Slippage = 0; Penalty = 0;
	Fill = 1;
	Hedge = 2;
	setf(TradeMode, TR_FRC);
#else
	set(PRELOAD);               // the lookback comes from our .t6 history, the broker fills the days after it
	set(LOGFILE);
	assetList("AssetsLive");
	asset(BK_ASSET);
	Hedge = 4;                  // IB keeps one net position (NFA): Zorro holds a long and a short as separate
	                            // trades and sends the net
#endif

	int k;
	if(is(INITRUN)) {
		ZBar = 0; ZState = 0; NP = 0; FI = 0; SessN = 0; HavePrevSess = 0; NR = 0; NB = 0; BarsInSess = 0;
		D = NO_D; BB = 0; NW = 0; NA = 0; NSeen = 0; Pos = 0; TimeExit = 0;
		PendP[0] = PendP[1] = -1;
#ifdef LIVE
		loadTouches();
#endif
#ifdef STATE
		file_delete(BK_STATE);
#endif
#ifdef SIM
		if(robustLogging()) {
			file_delete(BK_LOG);
			file_append(BK_LOG, "ole_utc,type,a,b,c,d,e,f,g\n");
		}
#endif
		return;
	}

	var o = priceOpen(0);
	var h = priceHigh(0);
	var l = priceLow(0);
	var c = priceClose(0);
	var lo = log(o);
	var lh = log(h);
	var ll = log(l);
	var lc = log(c);
	var factor = factorNow();

	// --- 1. session: a new session's threshold and bar baseline apply from its first bar ---
	var sess = floor(etFromUtc(wdate(0)) - 0.5 / 1440 + 0.25);
	int newSess = 0;
	if(ZBar == 0) CurSess = sess;
	else if(sess != CurSess) {
		newSess = 1;
		if(HavePrevSess) { var r = LastLogC - PrevSessC; RetSq[NR % VOL_N] = r * r; NR++; }
		PrevSessC = LastLogC; HavePrevSess = 1;
		SessBars[NB % VOL_N] = BarsInSess; NB++; BarsInSess = 0;
		CurSess = sess; SessN++;
		if(NR >= VOL_N) { var acc = 0; for(k = 0; k < VOL_N; k++) acc += RetSq[k]; D = log(1. + BK_K * sqrt(acc / VOL_N)); }
		if(NB >= VOL_N) { var accb = 0; for(k = 0; k < VOL_N; k++) accb += SessBars[k]; BB = accb / VOL_N; }
		logEvent(1, SessN, D, BB, 0, 0, 0, 0);
	}
	BarsInSess++;

	// --- 2. zigzag on this bar ---
	if(ZBar == 0) { Hi = lh; HiI = 0; HiS = SessN; Lw = ll; LwI = 0; LwS = SessN; }
	else if(ZState == 0) {
		if(lh > Hi) { Hi = lh; HiI = ZBar; HiS = SessN; }
		if(ll < Lw) { Lw = ll; LwI = ZBar; LwS = SessN; }
		if(Hi - Lw >= D) {
			if(HiI > LwI) { recordPivot(1, Lw, LwI, LwS); ZState = 1; Ext = lh; ExtI = ZBar; ExtS = SessN; }
			else if(LwI > HiI) { recordPivot(-1, Hi, HiI, HiS); ZState = -1; Ext = ll; ExtI = ZBar; ExtS = SessN; }
			else { Hi = lh; HiI = ZBar; HiS = SessN; Lw = ll; LwI = ZBar; LwS = SessN; }
		}
	} else if(ZState == 1) {
		if(lh > Ext) { Ext = lh; ExtI = ZBar; ExtS = SessN; }
		if(ll <= Ext - D) { recordPivot(-1, Ext, ExtI, ExtS); ZState = -1; Ext = ll; ExtI = ZBar; ExtS = SessN; }
	} else {
		if(ll < Ext) { Ext = ll; ExtI = ZBar; ExtS = SessN; }
		if(lh >= Ext + D) { recordPivot(1, Ext, ExtI, ExtS); ZState = 1; Ext = lh; ExtI = ZBar; ExtS = SessN; }
	}

	// --- 3. what Zorro filled during this bar ---
	int nOpen = 0;
	int newDir = 0;
	int filledP = -1;
	for(open_trades) {
		if(!TradeIsOpen) continue;
		nOpen++;
		if(TradeStopLimit == 0) {
			int side = ifelse(TradeIsLong, 0, 1);
			var S = PendS[side];
			var dd = PendD[side];
			var tk = PendTk[side];
			var sgn = ifelse(TradeIsLong, 1., -1.);
			TradeStopLimit = f32(exp(S - sgn * BK_R * dd));
			TradeProfitLimit = f32(exp(S + sgn * BK_R * dd));
			PosTP = f32(exp(S + sgn * (BK_R * dd + tk)));
			newDir = TradeDir; filledP = PendP[side];
			PosSessEnd = SessN + WINDOW;
			logEvent(3, TradeDir, TradePriceOpen, TradeStopLimit, PosTP, TradeLots, filledP, 0);
#ifndef SIM
			TV_TP = PosTP; TV_SESS = 0;
		} else {
			// open from an earlier bar, or resumed by Zorro after a restart: the script's own copy of the target
			// and of the time limit is gone after a restart, the trade's is not
			if(newSess) TV_SESS += 1;
			PosTP = TV_TP;
			PosSessEnd = SessN + WINDOW - (int)TV_SESS;
			if(Pos == 0) newDir = TradeDir;
#endif
		}
	}
	if(nOpen > 1) {                                    // a long and a short stop both traded in one bar
		logEvent(9, 1, nOpen, 0, 0, 0, 0, 0);
		for(open_trades) if(TradeIsOpen && TradeIsShort) exitTrade(ThisTrade);
		if(newDir < 0) newDir = 0;
	}
	if(newDir != 0) Pos = newDir;
	else if(nOpen == 0) Pos = 0;

	// --- 4. armed stops: dropped when they trade unfilled, when price reaches the stop level first, or on time ---
	int a;
	int keep = 0;
	for(a = 0; a < NA; a++) {
		int hiL = PivDir[AP[a]] == -1;
		int traded = ifelse(hiL, h >= f32(exp(AS[a])), l <= f32(exp(AS[a])));
		int drop = 0;
		if(AP[a] == filledP) drop = 4;
		else if(traded) drop = 1;
		else if(ZBar > ABar[a] && ifelse(hiL, ll <= PivV[AP[a]] - BK_R * AD[a], lh >= PivV[AP[a]] + BK_R * AD[a])) drop = 2;
		else if(SessN > ASess[a] + WINDOW) drop = 3;
		if(drop) { if(drop != 4) logEvent(7, AP[a], drop, 0, 0, 0, 0, 0); continue; }
		AP[keep] = AP[a]; AS[keep] = AS[a]; AD[keep] = AD[a]; ATk[keep] = ATk[a]; ABar[keep] = ABar[a]; ASess[keep] = ASess[a];
		keep++;
	}
	NA = keep;

	// --- 5. touches of live levels on this bar ---
	keep = 0;
	int w;
#ifdef LIVE
	seenBefore(wdate(0));
#endif
	for(w = 0; w < NW; w++) {
		int j = W[w];
		if(SessN > PivS[j] + WINDOW) continue;         // level expired
		int hiL = PivDir[j] == -1;
		if(!ifelse(hiL, lh >= PivV[j], ll <= PivV[j])) { W[keep++] = j; continue; }
		var sp = speedAt(j, ZBar);
		int ter = tercile(sp);
#ifdef LIVE
		seenTouch(wdate(0), sp);
#else
		insertSeen(sp);
#endif
#ifdef STATE
		file_append(BK_STATE, strf("%.10f,%.12g\n", wdate(0), sp));
#endif
		logEvent(5, j, PivV[j], sp, ter, ZBar, 0, 0);
		if(ter != 2 || j == filledP) continue;
		// armed from this touch; a stop rested for it this bar keeps its price
		var tk = tickLog(lc, factor);
		var S = ifelse(hiL, PivV[j] + tk, PivV[j] - tk);
		var dd = D;
		int side = ifelse(hiL, 0, 1);
		if(PendP[side] == j) { S = PendS[side]; dd = PendD[side]; tk = PendTk[side]; }
		if(ifelse(hiL, h >= f32(exp(S)), l <= f32(exp(S)))) { logEvent(7, j, 1, 0, 0, 0, 0, 0); continue; }
		if(NA < MAXA) {
			AP[NA] = j; AS[NA] = S; AD[NA] = dd; ATk[NA] = tk; ABar[NA] = ZBar; ASess[NA] = SessN; NA++;
			logEvent(6, j, S, dd, 0, 0, 0, 0);
		}
	}
	NW = keep;

	// --- 6. time exit at this bar's close ---
	if(Pos != 0 && SessN > PosSessEnd) {
		for(open_trades) if(TradeIsOpen) TradeCommission *= (0.5 + COMM_TICKS) / (1. + COMM_TICKS);
		if(Pos > 0) exitLong(); else exitShort();
		Pos = 0;
	}
	LastLogC = lc;

	// --- 7. stops resting for the next bar (flat only): nearest long and nearest short ---
	int bestP[2]; var bestS[2]; var bestD[2]; var bestTk[2];
	bestP[0] = bestP[1] = -1;
	if(Pos == 0) {
		var tkNow = tickLog(lc, factor);
		for(a = 0; a < NA; a++) {
			int sd = ifelse(PivDir[AP[a]] == -1, 0, 1);
			if(bestP[sd] < 0 || ifelse(sd == 0, AS[a] < bestS[sd], AS[a] > bestS[sd])) {
				bestP[sd] = AP[a]; bestS[sd] = AS[a]; bestD[sd] = AD[a]; bestTk[sd] = ATk[a];
			}
		}
		for(w = 0; w < NW; w++) {                      // untouched levels whose touch on the next bar would be slow
			int j2 = W[w];
			if(tercile(speedAt(j2, ZBar + 1)) != 2) continue;
			int sd2 = ifelse(PivDir[j2] == -1, 0, 1);
			var S2 = ifelse(sd2 == 0, PivV[j2] + tkNow, PivV[j2] - tkNow);
			if(bestP[sd2] < 0 || ifelse(sd2 == 0, S2 < bestS[sd2], S2 > bestS[sd2])) {
				bestP[sd2] = j2; bestS[sd2] = S2; bestD[sd2] = D; bestTk[sd2] = tkNow;
			}
		}
	}
	int have[2]; have[0] = have[1] = 0;
	for(open_trades) if(TradeIsPending) {
		int ps = ifelse(TradeIsLong, 0, 1);
		if(bestP[ps] >= 0 && !have[ps]) { TradeEntryLimit = f32(exp(bestS[ps])); have[ps] = 1; }
		else exitTrade(ThisTrade);
	}
	int s2;
	for(s2 = 0; s2 < 2; s2++) {
		PendP[s2] = bestP[s2]; PendS[s2] = bestS[s2]; PendD[s2] = bestD[s2]; PendTk[s2] = bestTk[s2];
		if(bestP[s2] >= 0 && !have[s2]) {
			Entry = f32(exp(bestS[s2]));
			EntryTime = 1000000;
			Stop = 0; TakeProfit = 0;
#ifdef SIM
			Lots = (int)(NOTIONAL / Entry);
			Commission = BK_TICK * factor * (1. + COMM_TICKS) * robustCostMult();
#else
			Lots = BK_LIVE_LOTS;                 // whole contracts; the broker charges the real cost
#endif
			if(s2 == 0) enterLong(bkTMF); else enterShort(bkTMF);
		}
	}
	ZBar++;
}
