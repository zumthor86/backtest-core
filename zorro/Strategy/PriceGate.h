// Live price gate for the futures sleeves: no price updates while CME Globex is shut.
//
// During the daily halt IB sends the previous session's settlement as a price, and the IB plugin passes it on as a
// trade: CL 88.28 against a real 91.17 at 17:40 New York on 2026-10-08 (the 10-07 settlement was 88.22), GC 4157.0
// and 4107.9 on 10-09 and 10-15. The sleeves took those prints as real: a ZigZagCL stop fired on one, and the ZigZag
// cores recorded false pivots most evenings. The backtest bars hold no trade in the halt, so the live sleeves must
// not see one either. While the gate is shut the asset carries Zorro's NOPRICE flag (manual: "prevents price updates
// in live trading").
//
// Shut: Friday 17:00 to Sunday 17:59 New York, and 17:00 to 17:59 every weekday. Prices are taken again from 17:59,
// one minute before the reopen, because tock() runs only once a minute. Holidays are not known here.
// A futures sleeve defines PG_GLOBEX before it includes Heartbeat.h; Heartbeat.h's tock() calls priceGate().
#ifdef LIVE
#ifndef SIM
#ifdef PG_GLOBEX
#define PG_ON
#endif
#endif
#endif

#ifdef PG_ON
int PgShut = 0;

// New York time from UTC, the cores' own rule (Zorro's zone table is only documented to 2024).
var pgEtFromUtc(var t)
{
	int y = ymd(t) / 10000;
	var mar1 = dmy(y * 10000 + 301);
	var nov1 = dmy(y * 10000 + 1101);
	var dstStart = mar1 + ((7 - (((int)floor(mar1) + 6) % 7)) % 7) + 7 + 7. / 24;
	var dstEnd = nov1 + ((7 - (((int)floor(nov1) + 6) % 7)) % 7) + 6. / 24;
	if(t >= dstStart && t < dstEnd) return t - 4. / 24;
	return t - 5. / 24;
}

int globexShut(var utc)
{
	var et = pgEtFromUtc(utc);
	int dow = ((int)floor(et) + 6) % 7;                // 0 = Sunday
	int minute = (int)floor((et - floor(et)) * 1440);
	if(dow == 6) return 1;                              // Saturday
	if(dow == 5 && minute >= 17 * 60) return 1;         // Friday after the close
	if(dow == 0 && minute < 17 * 60 + 59) return 1;     // Sunday before the open
	if(minute >= 17 * 60 && minute < 17 * 60 + 59) return 1;   // the daily halt
	return 0;
}

// Called from tock(). While the lookback replays, tock() sees the replayed time: the gate acts on real minutes only.
function priceGate()
{
	if(wdate(0) < wdate(NOW) - 10. / 1440) return;
	int shut = globexShut(wdate(NOW));
	if(shut == PgShut) return;
	if(shut) setf(AssetMode, NOPRICE);
	else resf(AssetMode, NOPRICE);
	PgShut = shut;
	if(shut) printf("\nPrice gate shut: Globex is closed");
	else printf("\nPrice gate open");
}
#else
function priceGate() {}
#endif
