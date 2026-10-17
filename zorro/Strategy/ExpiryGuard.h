// Refuse a live start on a futures contract close to expiry.
//
// The contract a sleeve trades is set by hand in History\AssetsLive.csv (or AssetsIBPaper.csv), and the history must be
// rolled with it (python -m backtest_core.zorro.live). On 2026-10-16 the CL row still named MCL-FUT-20261019 with the
// week start two days away. Argus warns 5 trading days ahead (trading.expiry_alerts); this is the last stop.
// Call expiryGuard() once, in the INITRUN branch of run(), after the traded asset is selected. A symbol without
// "-FUT-YYYYMMDD" (a stock, or the history name in a test) passes.
#ifdef LIVE
#define EG_MIN_DAYS 3          // trading days left, the expiry day counted; keep equal to Argus's EXPIRY_REFUSE_DAYS

int egDaysLeft(var today, var expiry)  // weekdays after today up to and including expiry; holidays are not known
{
	int n = 0;
	int d = (int)floor(today) + 1;
	for(; d <= (int)floor(expiry); d++)
		if(d % 7 >= 2) n++;         // OLE day 0 (1899-12-30) is a Saturday: d % 7 is 0 Sat, 1 Sun, 2..6 Mon..Fri
	return n;
}

function expiryGuard()
{
	char* p = strstr(SymbolTrade, "-FUT-");
	if(!p) return;
	char digits[9];
	strncpy(digits, p + 5, 8);
	digits[8] = 0;
	int ymdExp = atoi(digits);
	if(ymdExp < 20000101) return;
	int left = egDaysLeft(wdate(NOW), dmy(ymdExp));
	printf("\nExpiryGuard: %s expires %i, %i trading day(s) left", SymbolTrade, ymdExp, left);
	if(left < EG_MIN_DAYS)
		quit(strf("ExpiryGuard: %s expires in %i trading day(s): roll AssetsLive.csv and the history first", SymbolTrade, left));
}
#else
function expiryGuard() {}
#endif
