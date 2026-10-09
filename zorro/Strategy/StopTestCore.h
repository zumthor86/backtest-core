// StopTestCore.h -- Option A of the broker-side safety stop. Included by StopTest1.c and StopTest2.c.
//
// The question: on this NFA paper account, with the same Hedge mode as the sleeves, does Zorro send a stop order to the
// broker together with its own trade, which client ID carries it, and does it go away when Zorro closes the trade itself?
// Zorro's manual warns that such a stop "might stay alive even when the original trade was closed, possibly triggering an
// unwanted position in reverse direction" (trademode.txt). This script finds out on one micro contract.
//
// StopTest1.c: StopFactor only (what stop.txt describes).
// StopTest2.c: StopFactor plus brokerCommand(SET_ORDERTYPE, 8), the "+8 STOP" order type (brokercommand.txt).
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

	if(TStep == 0) {
		Stop = TEST_STOP;
		StopFactor = 1.5;
		Lots = 1;
#ifdef STOP_TYPE_8
		brokerCommand(SET_ORDERTYPE, 8);
#endif
		enterLong();
		TStep = 1; TEnterBar = Bar;
		printf("\nStopTest: bought 1 %s, Stop %.0f, StopFactor 1.5", Asset, Stop);
	} else if(TStep == 1 && Bar >= TEnterBar + TEST_HOLD_BARS) {
		exitLong();
		TStep = 2; TExitBar = Bar;
		printf("\nStopTest: closed the trade at market");
	} else if(TStep == 2 && Bar >= TExitBar + TEST_AFTER_BARS) {
		quit("StopTest finished");
	}
}
