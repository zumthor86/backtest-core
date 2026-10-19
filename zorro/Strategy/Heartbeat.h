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
//
// tock() also logs in again when the price feed stays dead (hbRelogin). After the Gateway's nightly restart the sleeves
// most nights never got their connection back, SET_RESTART (LiveRestart.h) included: Zorro's own retries kept failing.
// The manual's fix for a hung broker API is login(4), then login(1), the same as [Stop], [No], [No] by hand; open
// trades stay. It runs after HB_RELOGIN_MIN real minutes with at most 1 quote a minute while the market is open, and
// again each HB_RELOGIN_MIN minutes until quotes come back. A disconnected sleeve still gets a quote now and then (one
// a reconnect attempt), and a healthy one gets at least 5 a minute. Each attempt is a line in Log\Relogin_<Script>.csv.
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

#ifndef SIM
#define HB_RELOGIN_MIN 10
var HbQuietSince = 0;
char HbReloginFile[80];

// Globex open and, for a sleeve with its own session (BR_MARKET: NoiseAreaNQ, BarZone UTC), inside StartMarket..EndMarket:
// out of its session Zorro passes it no quotes, connected or not.
int hbMarketOpen(var utc)
{
	if(globexShut(utc)) return 0;
	if(BarMode & BR_MARKET) {
		var d = utc - floor(utc);
		int hhmm = (int)floor(d * 24) * 100 + ((int)floor(d * 1440)) % 60;
		if(hhmm < StartMarket || hhmm >= EndMarket) return 0;
	}
	return 1;
}

function hbRelogin()
{
	var now = wdate(NOW);
	if(HbTicks > 1 || !hbMarketOpen(now)) { HbQuietSince = 0; return; }
	if(HbQuietSince == 0) { HbQuietSince = now; return; }
	if(now - HbQuietSince < HB_RELOGIN_MIN / 1440.) return;
	printf("\nNo prices for %i minutes: logging in again", HB_RELOGIN_MIN);
	login(4);
	int ok = login(1);
	printf("\nLogin again: %i", ok);
	sprintf(HbReloginFile, "Log\\Relogin_%s.csv", Script);
	if(!file_length(HbReloginFile)) file_append(HbReloginFile, "now_utc,quiet_since_utc,logged_in\n");
	file_append(HbReloginFile, strf("%.8f,%.8f,%i\n", now, HbQuietSince, ok));
	HbQuietSince = now;
}
#else
function hbRelogin() {}
#endif

function tock()                        // once a minute whether or not a quote arrived
{
	priceGate();
	sprintf(HbFile, "Log\\Heartbeat_%s.csv", Script);
	if(!file_length(HbFile))
		file_append(HbFile, "now_utc,ticks_in_last_min,last_quote_utc,last_quote,live_bars,last_bar_utc,lookback_bars\n");
	file_append(HbFile, strf("%.8f,%i,%.8f,%.6g,%i,%.8f,%i\n", wdate(0), HbTicks, HbQuoteUtc, HbQuote, HbBars, HbBarUtc, HbLookbackBars));
	// While the lookback replays, tock() fires once per replayed minute with the replayed time; is(LOOKBACK) is not set
	// there. No trade exists yet and the file would be rewritten tens of thousands of times, so act only when the
	// time tock() sees is within 10 minutes of the real clock.
	int real = wdate(0) > wdate(NOW) - 10. / 1440;
	if(real) hbRelogin();
	HbTicks = 0;
	if(real) { writeState(); poolSync(); }
}
#else
function hbBar() {}
#endif
