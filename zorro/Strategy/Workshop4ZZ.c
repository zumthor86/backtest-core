// Workshop4ZZ.c -- Zorro's Workshop 4 trend system, logic unchanged, set up for our data.
// Pick CL, GC or QQQ in the [Asset] box (they are in History\AssetsFix.csv; the original list is saved as
// AssetsFix_original.csv). The original script hard-codes EUR/USD and 2012-2017.
//
// Rule (Zorro's): trade the turns of a 300-bar low-pass filter of hourly closes -- long at a valley, short at a
// peak -- only while the smoothed Market Meanness Index is falling (a trending market). Stop 30 x ATR(100).
//
// Our data: CL and GC are 1 unit = 1 point of the ratio-adjusted continuous price, so the P&L is a return on
// notional. Their commission in AssetsFix.csv is one raw tick plus $4.50 a contract, per unit -- right on today's
// price scale, approximate in old years (the adjustment factor was up to 2x for CL).

#include <profile.c>

function run()
{
	set(LOGFILE,PLOTNOW);
	BarMode = 0;               // every bar: the default week end blocks Friday exits on our data
	Outlier = 1000;            // off: never "repair" a real move (April 2020 oil)
	StartDate = 2011;
	EndDate = 2026;
	Capital = 1000000;
	LookBack = 300;            // needed for MMI

	vars Prices = series(priceC(0));
	vars Trends = series(LowPass(Prices,300));

	MaxLong = MaxShort = -1;   // one position at a time (Zorro's original piles up to 5); negative so a blocked
	                           // signal does not move the open trade's stop either
	Stop = 30*ATR(100);        // very distant stop
	Lots = (int)(1000000 / priceC(0));   // about $1M notional per trade

	vars MMI_Raws = series(MMI(Prices,300));
	vars MMI_Smooths = series(LowPass(MMI_Raws,300));

	if(falling(MMI_Smooths))
	{
		if(valley(Trends))
			enterLong();
		else if(peak(Trends))
			enterShort();
	}

	plot("MMI_Raw",MMI_Raws,NEW,GREY);
	plot("MMI_Smooth",MMI_Smooths,0,BLACK);
}
