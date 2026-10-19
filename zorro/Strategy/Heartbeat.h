// Live heartbeat: one line a minute in Log\Heartbeat_<Script>.csv that shows how often prices and bars reach the sleeve.
//
// The status page lists a bar only now and then, so it cannot tell a slow price feed from sparse logging. This file can:
// ticks_in_last_min counts price quotes, live_bars counts the bars run() has handled since the lookback ended.
// A healthy 1-minute sleeve shows a live_bars step of 1 per line. The file is separate from Zorro's own bar log
// (Log\<Script>*_demo.log), which must never be read while Zorro runs.
//
// hbBar() also appends each live bar (time, OHLC, volume) to Log\Bars_<Script>.csv, so the paper check (`argus paper`,
// barcheck.py) can compare the bars Zorro built from the IB feed with Databento's: trade recon holds only if they are the same.
//
// It only counts and writes. It sets no variable that a signal reads and sends no order.
// Include it in a sleeve's core header and call hbBar() once per run() after the INITRUN return.
// tock() also writes the sleeve's trade state (StateExport.h), runs the futures price gate (PriceGate.h) and checks
// Zorro's broker record against the broker (PoolSync.h), because a script can define tock() only once.
// It also carries nfaOn() (NfaOn.h), which the Hedge-4 cores call in their live branch; this file never calls it.
#include "StateExport.h"
#include "PriceGate.h"
#include "PoolSync.h"
#include "NfaOn.h"
#ifdef LIVE
int HbTicks = 0;
int HbBars = 0;
int HbLookbackBars = 0;
var HbQuoteUtc = 0;
var HbQuote = 0;
var HbBarUtc = 0;
char HbFile[80];
char HbBarFile[80];

function hbBar()
{
	if(is(LOOKBACK)) { HbLookbackBars++; return; }
	HbBars++;
	HbBarUtc = wdate(0);                // inside run() this is the bar's own time
	sprintf(HbBarFile, "Log\\Bars_%s.csv", Script);
	if(!file_length(HbBarFile))
		file_append(HbBarFile, "bar_utc,open,high,low,close,volume\n");
	file_append(HbBarFile, strf("%.8f,%.8g,%.8g,%.8g,%.8g,%.8g\n", HbBarUtc, priceOpen(0), priceHigh(0), priceLow(0), priceClose(0), marketVol(0)));
}

function tick()                        // each price quote, at most one per TickTime per asset
{
	HbTicks++;
	HbQuote = priceClose(0);
	HbQuoteUtc = wdate(0);              // inside tick() this is the quote's time stamp
}

function tock()                        // once a minute whether or not a quote arrived
{
	priceGate();
	sprintf(HbFile, "Log\\Heartbeat_%s.csv", Script);
	if(!file_length(HbFile))
		file_append(HbFile, "now_utc,ticks_in_last_min,last_quote_utc,last_quote,live_bars,last_bar_utc,lookback_bars\n");
	file_append(HbFile, strf("%.8f,%i,%.8f,%.6g,%i,%.8f,%i\n", wdate(0), HbTicks, HbQuoteUtc, HbQuote, HbBars, HbBarUtc, HbLookbackBars));
	HbTicks = 0;
	// While the lookback replays, tock() fires once per replayed minute with the replayed time; is(LOOKBACK) is not set
	// there. No trade exists yet and the file would be rewritten tens of thousands of times, so write only when the
	// time tock() sees is within 10 minutes of the real clock.
	if(wdate(0) > wdate(NOW) - 10. / 1440) { writeState(); poolSync(); }
}
#else
function hbBar() {}
#endif
