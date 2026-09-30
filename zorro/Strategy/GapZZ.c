// GapZZ.c -- Zorro's Gap.c (David Bean's gap system) set up for our QQQ data. Pick QQQ in the [Asset] box.
//
// Rule (Zorro's): at the open, fade the gap back toward yesterday's close when the open sits inside yesterday's
// range and on the far side of a 100-day average:
//   open above yesterday's close, below yesterday's high, below the average  -> short
//   open below yesterday's close, above yesterday's low,  above the average  -> long
// One position; the opposite signal reverses it; otherwise a fixed stop.
//
// What changes for our data, and why:
//   - The original enters on a 30-minute bar closing at 09:30 ET. Our QQQ bars are market hours only, so no bar
//     closes then. BarOffset = 1 makes the day's first 30-minute bar close at 09:31 and hold just the opening
//     minute: its close is the open price.
//   - Yesterday's high, low and close are tracked by the script. Zorro's dayHigh/dayLow/dayClose read an empty
//     day on Mondays with market-hours data, and its New York time table is only documented to 2024.
//   - The 100-day average is 100 x 14 of our 30-minute bars (the original's 4,800 assumed 24-hour CFD data).
//   - Stop: 1% of price. The original's 200 pips of SPX500 are 20 index points, about 1% when the example was
//     written; a fixed dollar stop on QQQ would be 4% in 2011 and 0.3% in 2026.
//   - About $100k per trade, one tick + commission ($0.017 a share) round trip, from AssetsFix.csv.

var PrevHigh, PrevLow, PrevClose, SessHigh, SessLow, LastClose;

int dowOle(var t) { return ((int)floor(t) + 6) % 7; }          // 0 = Sunday
var etFromUtc(var t)                                           // US Eastern time, DST rules from 2007
{
	int y = ymd(t) / 10000;
	var mar1 = dmy(y * 10000 + 301);
	var nov1 = dmy(y * 10000 + 1101);
	var dstStart = mar1 + ((7 - dowOle(mar1)) % 7) + 7 + 7. / 24;
	var dstEnd = nov1 + ((7 - dowOle(nov1)) % 7) + 6. / 24;
	if(t >= dstStart && t < dstEnd) return t - 4. / 24;
	return t - 5. / 24;
}

function run()
{
	set(LOGFILE);
	BarPeriod = 30;
	BarOffset = 1;             // 30-minute bars close at hh:01 and hh:31
	BarMode = 0;               // every bar: the default week end blocks Friday exits on our data
	Outlier = 1000;            // off: never "repair" a real move
	StartDate = 2011;
	EndDate = 2026;
	LookBack = 100 * 14;       // 100 days of market-hours 30-minute bars
	Capital = 100000;
	MaxLong = MaxShort = -1;

	if(is(INITRUN)) { PrevHigh = PrevLow = PrevClose = SessHigh = SessLow = LastClose = 0; return; }

	vars Prices = series(priceClose());
	var et = etFromUtc(wdate(0));
	int minuteOfDay = (int)floor((et - floor(et)) * 1440 + 0.5);
	int isOpenBar = (minuteOfDay == 9 * 60 + 31);

	if(isOpenBar) {
		if(SessHigh > 0) { PrevHigh = SessHigh; PrevLow = SessLow; PrevClose = LastClose; }
		SessHigh = priceHigh(); SessLow = priceLow();
	} else {
		SessHigh = max(SessHigh, priceHigh()); SessLow = min(SessLow, priceLow());
	}
	LastClose = priceClose();

	Stop = 0.01 * priceClose();
	Lots = (int)(100000 / priceClose());

	if(isOpenBar && PrevHigh > 0 && PrevLow > 0 && PrevClose > 0) {
		var Avg = SMA(Prices, LookBack);
		if(Prices[0] > PrevClose && Prices[0] < PrevHigh && Prices[0] < Avg)
			enterShort();
		if(Prices[0] < PrevClose && Prices[0] > PrevLow && Prices[0] > Avg)
			enterLong();
	}
}
