// Zorro's own view of its trades, written once a minute to Log\State_<Script>.csv.
//
// Entry stops, stop losses and profit targets live inside Zorro and are never sent to the broker (manual stop.txt:
// "unknown to the broker and not visible on their trading platform"), so the broker's open-order list shows none of
// them. This file is the only place a pending entry, an open sleeve trade and its stop and target can be read from
// outside Zorro. Called from tock() in Heartbeat.h.
//
// One row per trade. With virtual hedging (Hedge = 4) Zorro keeps two layers: the sleeve's own "phantom" trades and the
// "pool" trades that are the net it sends to the broker. Both are written; layer tells them apart.
//   layer    0 = plain trade, 1 = phantom (the sleeve's own trade), 2 = pool (the net at the broker)
//   pending  1 = entry not filled yet, 0 = open
//   side     +1 long, -1 short
//   entry_limit is the level of a pending entry (0 for an open trade); fill, stop and target are the fill price and the
//   stop and profit levels of an open trade (0 for a pending one, where Zorro holds raw distances that must not be read)
// Times are OLE dates in UTC. The last line is "#end,<rows>": a reader that does not find it read a half-written file.
// The file is rewritten whole each minute, so it holds the state as of asof_ole_utc and no history.
#ifdef LIVE
#define ST_MAXTEXT 7000
char StBuf[ST_MAXTEXT];
char StLine[260];
char StFile[80];

function writeState()
{
	var asof = wdate(0);
	int rows = 0;
	sprintf(StFile, "Log\\State_%s.csv", Script);
	strcpy(StBuf, "asof_ole_utc,script,asset,layer,pending,side,lots,entry_limit,fill,stop,target,opened_ole_utc\n");
	for(open_trades) {
		sprintf(StLine, "%.8f,%s,%s,%i,%i,%i,%i,%.8g,%.8g,%.8g,%.8g,%.8f\n",
			asof, Script, Asset,
			(int)ifelse(TradeIsPool, 2, ifelse(TradeIsPhantom, 1, 0)),
			(int)ifelse(TradeIsPending, 1, 0),
			(int)ifelse(TradeIsShort, -1, 1),
			(int)TradeLots,
			(var)ifelse(TradeIsPending, TradeEntryLimit, 0),
			(var)ifelse(TradeIsPending, 0, TradePriceOpen),
			(var)ifelse(TradeIsPending, 0, TradeStopLimit),
			(var)ifelse(TradeIsPending, 0, TradeProfitLimit),
			(var)TradeDate);
		if(strlen(StBuf) + strlen(StLine) + 40 < ST_MAXTEXT) {
			strcat(StBuf, StLine);
			rows++;
		}
	}
	sprintf(StLine, "#end,%i\n", rows);
	strcat(StBuf, StLine);
	file_write(StFile, StBuf, 0);
}
#else
function writeState() {}
#endif
