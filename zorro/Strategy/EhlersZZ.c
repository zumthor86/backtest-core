// EhlersZZ.c -- Zorro's Ehlers.c (John Ehlers, "Predictive Indicators for Effective Trading Strategies") set up
// for our data. Pick QQQ (or CL / GC) in the [Asset] box.
//
// Rule (Zorro's, unchanged): daily bars; Ehlers' stochastic of the price (10, 20, 10). Short when it is predicted
// to cross above 0.8 within the next bars, long when predicted to cross below 0.2 (predict(), polynomial
// extrapolation). One position per side; an opposite entry closes the open trade. No stop.
//
// What changes for our data: the asset comes from the [Asset] box (the original hard-codes SPX500, which we have
// no history for -- hence "no bars generated"); 2011-2026; about $100k per trade; weekend skipping and the
// outlier filter off; daily bars set to close at midnight UTC (Zorro's default is 15:40), after the US close, so each
// holds one full session and trades fill at that session's close.

#define USE_PREDICT

function run()
{
	BarPeriod = 1440;
	BarOffset = 0;             // daily bars close at midnight UTC; Zorro's default (15:40) would split each session
	BarMode = 0;              // every bar: the default week end blocks Friday exits on our data
	Outlier = 1000;            // off: never "repair" a real move
	StartDate = 2011;
	EndDate = 2026;
	Capital = 100000;
	MaxLong = MaxShort = 1;

	Lots = (int)(100000 / priceClose());
	vars Osc = series(StochEhlers(series(price()),10,20,10));

#ifndef USE_PREDICT
	if(crossOver(Osc,0.8))
		enterShort();
	if(crossUnder(Osc,0.2))
		enterLong();
#else
	if(predict(CROSSOVER,series(Osc[0]-0.8),10,0.01) > -5)
		enterShort();
	if(predict(CROSSOVER,series(0.2-Osc[0]),10,0.01) > -5)
		enterLong();
#endif

	PlotWidth = 800;
	plot("StochEhlers",Osc,NEW,RED);
	plot("Threshold1",.2,0,BLACK);
	plot("Threshold2",.8,0,BLACK);
	set(PLOTNOW);
}
