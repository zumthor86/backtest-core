// Robust.h -- the standard robustness battery for our strategy scripts.
// Include it after <default.c> and before the strategy core. The mode comes from the command line:
//   Zorro.exe -run <Script> -i <mode> [-i <k>] -quiet            (modes 0-7)
//   Zorro.exe -train <Script> -i <mode> -quiet                    (modes 8-9: training), then -run for mode 9's test
//
//   0  base run: LOGFILE on (Log/<Script>_trd.csv, _pnl.csv), strategy writes its parity trade log
//   1  daily close / bar start moved: BarOffset = base - k * BarPeriod / 6 (k = Command[1], 0..5; k = 0 is the base).
//      Zorro's own oversampling (NumSampleCycles) is NOT used: it cannot be combined with a set BarOffset.
//   2  Detrend = TRADES   (trade returns corrected for the market's drift)
//   3  Detrend = CURVE    (history tilted flat, report only)
//   4  reality check: RB_MRC_CYCLES cycles, cycle 1 original, the rest on shuffled prices (Zorro's MRC.c)
//   5  Monte Carlo confidence table (Capital left unset, which Zorro requires)
//   6  costs doubled (the strategy multiplies its Commission by robustCostMult())
//   7  Detrend = INVERT   (price curve mirrored; meaningful for long-short rules only)
//   8  parameter plateau: brute-force training over every robustParam(); grid in Log/<Script>par.csv
//   9  walk-forward: RB_WFO_CYCLES rolling cycles (DataSplit RB_WFO_SPLIT), train with -train, test with -run
//
// The strategy core must:
//   - call robustBars(<base BarOffset>) after setting BarPeriod / BarZone and BEFORE assetList() / asset();
//   - call robustCapital(<capital>) instead of setting Capital;
//   - multiply its cost by robustCostMult() when it sets Commission;
//   - wrap each rule constant in robustParam(default, min, max, step) (all values > 0, ideally 1..10000);
//   - write its own trade log only when robustLogging() is true;
//   - NOT define evaluate() (this file owns it).

#ifndef RB_MRC_CYCLES
#define RB_MRC_CYCLES 100
#endif
#ifndef RB_MRC_SEED
#define RB_MRC_SEED 1234
#endif
#ifndef RB_WFO_CYCLES
#define RB_WFO_CYCLES 5
#endif
#ifndef RB_WFO_SPLIT
#define RB_WFO_SPLIT 85
#endif
#ifndef RB_MONTECARLO
#define RB_MONTECARLO 1000
#endif

#define RB_MODE (Command[0])

int robustLogging() { return RB_MODE == 0; }

var robustCostMult()
{
	if(RB_MODE == 6) return 2.;
	return 1.;
}

void robustBars(int baseOffset)
{
	int k = 0;
	int bp = (int)BarPeriod;                       // BarPeriod is a var; lite-C's % needs ints
	if(RB_MODE == 1) k = Command[1];
	BarOffset = ((baseOffset - k * bp / 6) % bp + bp) % bp;
	MonteCarlo = RB_MONTECARLO;
	if(RB_MODE == 5 && is(INITRUN)) seed(RB_MRC_SEED);   // repeatable confidence table
	if(RB_MODE == 0) set(LOGFILE);
	if(RB_MODE == 2) Detrend = TRADES;
	if(RB_MODE == 3) Detrend = CURVE;
	if(RB_MODE == 7) Detrend = INVERT;
	if(RB_MODE == 4) {
		NumTotalCycles = RB_MRC_CYCLES;
		if(TotalCycle == 1) seed(RB_MRC_SEED);
		else Detrend = SHUFFLE;
		set(PRELOAD);
	}
	if(RB_MODE == 8) { set(PARAMETERS); TrainMode = BRUTE; }
	if(RB_MODE == 9) { set(PARAMETERS); NumWFOCycles = RB_WFO_CYCLES; DataSplit = RB_WFO_SPLIT; }
}

void robustCapital(var capital)
{
	if(RB_MODE != 5) Capital = capital;
}

var robustParam(var def, var lo, var hi, var step)
{
	if(RB_MODE == 8 || RB_MODE == 9) return optimize(def, lo, hi, step);
	return def;
}

// Reality check (mode 4): share of shuffled-price cycles whose profit factor reaches the original run's.
function evaluate()
{
	if(RB_MODE != 4) return;
	static var OriginalPF, Beat;
	var PF = 10;
	if(LossTotal > 0) PF = WinTotal / LossTotal;
	if(TotalCycle == 1) { OriginalPF = PF; Beat = 0; }
	else if(PF >= OriginalPF) Beat += 1;
	string path = strf("Log/%s_mrc.csv", Script);
	if(TotalCycle == 1) file_delete(path);
	file_append(path, strf("%i,%.6f,%.2f,%.2f,%i\n", TotalCycle, PF, WinTotal, LossTotal, NumWinTotal + NumLossTotal));
	if(TotalCycle == NumTotalCycles)
		printf("\nMRC: original PF %.3f, shuffled runs at or above it %.0f of %i, p = %.1f%%",
			OriginalPF, Beat, NumTotalCycles - 1, 100. * Beat / (NumTotalCycles - 1));
}
