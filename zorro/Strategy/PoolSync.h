// Live check of Zorro's broker record against the broker, once a minute from tock() in Heartbeat.h.
//
// IB keeps only a net position per instrument and does not report back what Zorro sent (manual ib.txt: "the positions
// of Zorro and IB [can] get out of sync"). On 10-14, 10-15 and 10-16 Zorro's own pool close failed (Error 075) after
// the script's trade ended; Zorro kept retrying a close for a position the broker held, and after that position was
// closed by hand it kept a pool trade the broker no longer held, reloaded from Data\<Script>_d.trd at every start.
// The manual's remedy: compare brokerCommand(GET_POSITION) with LotsPool, and cancelTrade a position closed outside
// Zorro (cancelTrade sends no order).
//
// Each minute this compares LotsPhantom (the script's own net), LotsPool (Zorro's net at the broker) and the broker's
// net, and appends a line to Log\PoolSync_<Script>.csv whenever the three disagree or the state changes.
// It cancels only in one case: the script is flat, Zorro's pool holds a position, and the broker holds none in that
// instrument for PS_STALE_MIN checks in a row. Two conditions keep it from cancelling a real position:
//   - PS_SOLE_OWNER: only a sleeve that is the one sleeve on its broker instrument may cancel. All sleeves share one
//     account, so for two sleeves on one instrument (ZigZagGC and BreakGC on MGC) the broker net is not this sleeve's.
//   - GET_POSITION must first have returned this pool's own nonzero position once since the start, which shows the
//     command works for this symbol. A command that is not supported returns 0, which would look like a flat broker.
// A close that failed (pool and broker still hold, script flat) is only logged: fixing it needs an order.
#ifdef LIVE
#define PS_STALE_MIN 3
int PsVerified = 0;
int PsStale = 0;
int PsLastCode = -1;
char PsFile[80];

function psLog(int code, var phantom, var pool, var held, char* what)
{
	sprintf(PsFile, "Log\\PoolSync_%s.csv", Script);
	if(!file_length(PsFile))
		file_append(PsFile, "now_utc,asset,symbol,lots_phantom,lots_pool,broker_net,verified,code,what\n");
	file_append(PsFile, strf("%.8f,%s,%s,%.0f,%.0f,%.0f,%i,%i,%s\n", wdate(NOW), Asset, SymbolTrade, phantom, pool, held,
		PsVerified, code, what));
}

function poolSync()
{
	var phantom = LotsPhantom;
	var pool = LotsPool;
	var held = brokerCommand(GET_POSITION, SymbolTrade);
	if(pool != 0 && held == pool) PsVerified = 1;
	// code 0 agree; 1 failed send (pool = broker, script differs); 2 stale pool (script flat, broker flat);
	// 3 other mismatch (order in flight, or a shared instrument)
	int code = 3;
	if(phantom == pool && pool == held) code = 0;
	else if(pool == held) code = 1;
	else if(phantom == 0 && pool != 0 && held == 0) code = 2;
	if(code == 2) PsStale++; else PsStale = 0;
	if(code != PsLastCode) {
		if(code == 0) psLog(code, phantom, pool, held, "agree");
		if(code == 1) psLog(code, phantom, pool, held, "Zorro did not send the change to the broker");
		if(code == 2) psLog(code, phantom, pool, held, "Zorro holds a pool position the broker does not");
		if(code == 3) psLog(code, phantom, pool, held, "mismatch");
		PsLastCode = code;
	}
#ifdef PS_SOLE_OWNER
	if(code == 2 && PsStale >= PS_STALE_MIN && PsVerified) {
		int n = 0;
		for(open_trades)
			if(TradeIsPool && TradeIsOpen) { cancelTrade(ThisTrade); n++; }   // the sleeves trade one asset each
		printf("\nPoolSync: cancelled %i stale pool trade(s) of %s; the broker holds none", n, Asset);
		psLog(code, phantom, pool, held, strf("cancelled %i stale pool trade(s)", n));
		PsStale = 0;
		PsLastCode = -1;
	}
#endif
}
#else
function poolSync() {}
#endif
