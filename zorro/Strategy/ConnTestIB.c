// Connection test for the IB paper account: reads the account and one price per asset, then stops.
// It has no enter call, so it cannot send an order. Run it in Trade mode with the IB-Paper account.

void show(string Name)
{
	if(!asset(Name)) { printf("\n%s: NOT AVAILABLE", Name); return; }
	if(!is(INITRUN))
		printf("\n%s  price %.2f  spread %.4f", Name, priceClose(), Spread);
}

function run()
{
	set(LOGFILE);
	BarPeriod = 1;
	LookBack = 0;
	assetList("AssetsIBPaper");
	show("MES"); show("MNQ"); show("MGC"); show("MCL"); show("QQQ");
	if(is(INITRUN)) return;
	printf("\nBalance %.2f  Equity %.2f", Balance, Equity);
	quit("Connection test done");
}
