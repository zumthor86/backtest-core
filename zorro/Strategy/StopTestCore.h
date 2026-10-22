// StopTestCore.h -- Option A of the broker-side safety stop. Included by StopTest1.c and StopTest2.c.
//
// The question: on this NFA paper account, with the same Hedge mode as the sleeves, does Zorro send a stop order to the
// broker together with its own trade, which client ID carries it, and does it go away when Zorro closes the trade itself?
// Zorro's manual warns that such a stop "might stay alive even when the original trade was closed, possibly triggering an
// unwanted position in reverse direction" (trademode.txt). This script finds out on one micro contract.
//
// StopTest1.c: StopFactor only (what stop.txt describes).
// StopTest2.c: StopFactor plus brokerCommand(SET_ORDERTYPE, 8), the "+8 STOP" order type (brokercommand.txt).
// CloseTest.c: no stop at all: does Zorro's own close of a pool trade reach the broker? The sleeves' pool closes failed
// with "Error 075 - closing not supported (NFA?)" on 10-14, 10-15, 10-16 and 10-19; on 10-19 the Gateway's API log
// showed that no close order reached IB, so the NFA flag was off. The test now sets it as the sleeves do (NfaOn.h);
// -d TEST_NO_NFA leaves it out. Each minute it prints the script's net (LotsPhantom), Zorro's net at the broker
// (LotsPool), the broker's own net (GET_POSITION) and the NFA flag.
// This Zorro version has no TR_BSTOP flag, although the manual names one.
//
// RUN BY THE USER, once per variant, with futures open and no sleeve running on MES (BreakES is its only sleeve),
// on the spare account row IB-Paper-7 (IBKR client ID 7):
//   Zorro.exe -trade StopTest1 -c IB-Paper-7 -d LIVE -stay
// It buys ONE MES at market with a 35-point Zorro stop and StopFactor 1.5, holds it TEST_HOLD_BARS minutes, closes it
// at market, waits TEST_AFTER_BARS minutes, then quits. While it runs, `python -m argus stoptest --symbol MES` (in argus\) records what the broker shows.
// The test sends real orders to the paper account. It is not on the sleeve list: the user starts it.
#define TEST_ASSET "MES"         // not MNQ: DipBuyNQ holds MNQ, and the broker shows only the net
#define TEST_STOP 35.            // MES points, about 0.5% of the price
#define TEST_HOLD_BARS 4
#define TEST_AFTER_BARS 4
#ifndef TEST_HEDGE
#define TEST_HEDGE 0
#endif

#include "Heartbeat.h"           // also exercises the state export with a real trade

int TStep = 0, TEnterBar = 0, TExitBar = 0;

function run()
{
	BarPeriod = 1;
	LookBack = 0;
	Hedge = TEST_HEDGE;          // 0 as the sleeves (CloseTest.c keeps 4, the mode the sleeves ran until 2026-10-20)
#ifndef TEST_NO_NFA
	nfaOn();                     // as the sleeves since 10-19
#endif
	set(LOGFILE);
	assetList("AssetsIBPaper");
	asset(TEST_ASSET);
	if(is(INITRUN)) return;
	hbBar();

	printf("\nPositions: phantom %.0f pool %.0f broker %.0f  NFA %i", (var)LotsPhantom, (var)LotsPool,
		brokerCommand(GET_POSITION, SymbolTrade), (int)(is(NFA) != 0));
	if(TStep == 0) {
#ifndef TEST_NO_STOP
		Stop = TEST_STOP;
		StopFactor = 1.5;
#endif
		Lots = 1;
#ifdef STOP_TYPE_8
		brokerCommand(SET_ORDERTYPE, 8);
#endif
		enterLong();
		TStep = 1; TEnterBar = Bar;
		printf("\nStopTest: bought 1 %s, Stop %.0f, StopFactor %.1f", Asset, Stop, StopFactor);
	} else if(TStep == 1 && Bar >= TEnterBar + TEST_HOLD_BARS) {
		exitLong();
		TStep = 2; TExitBar = Bar;
		printf("\nStopTest: closed the trade at market");
	} else if(TStep == 2 && Bar >= TExitBar + TEST_AFTER_BARS) {
		quit("StopTest finished");
	}
}
