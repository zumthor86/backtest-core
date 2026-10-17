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
// with "Error 075 - closing not supported (NFA?)" on 10-14, 10-15 and 10-16. Each minute it prints the script's net
// (LotsPhantom), Zorro's net at the broker (LotsPool) and the broker's own net (GET_POSITION). Turn on the Gateway's
// API message log first (Configure, API, Settings): Error 075 may be any rejected close, and IB's reason is only there.
// This Zorro version has no TR_BSTOP flag, although the manual names one.
//
// RUN BY THE USER, once per variant, with futures open and no sleeve holding MNQ (DipBuyNQ trades NQ only around the
// daily close), on the spare account row IB-Paper-7 (IBKR client ID 7):
//   Zorro.exe -trade StopTest1 -c IB-Paper-7 -d LIVE -stay
// It buys ONE MNQ at market with a 150-point Zorro stop and StopFactor 1.5, holds it TEST_HOLD_BARS minutes, closes it
// at market, waits TEST_AFTER_BARS minutes, then quits. While it runs, `python -m argus stoptest` (in argus\) records what the broker shows.
// The test sends real orders to the paper account. It is not on the sleeve list: the user starts it.
#define TEST_ASSET "MNQ"
#define TEST_STOP 150.           // MNQ points, about 0.5% of the price
#define TEST_HOLD_BARS 4
#define TEST_AFTER_BARS 4

#include "Heartbeat.h"           // also exercises the state export with a real trade

int TStep = 0, TEnterBar = 0, TExitBar = 0;

function run()
{
	BarPeriod = 1;
	LookBack = 0;
	Hedge = 4;                   // as the sleeves: virtual hedging, only the net position reaches the broker
	set(LOGFILE);
	assetList("AssetsIBPaper");
	asset(TEST_ASSET);
	if(is(INITRUN)) return;
	hbBar();

	printf("\nPositions: phantom %.0f pool %.0f broker %.0f", (var)LotsPhantom, (var)LotsPool,
		brokerCommand(GET_POSITION, SymbolTrade));
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
