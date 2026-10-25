// GatewayClockTest.c -- checks GatewayClock.h against the dates the UK and the US change their clocks. No broker, no data.
//
//   Zorro.exe -run GatewayClockTest -quiet   (in the ZorroReplay copy)
//
// Log\GatewayClockTest.txt gets the result: each failure, then PASS or FAIL. printf is not saved in -quiet mode, so the file
// is the result.
//
// Expected values are from the rules, not from the code: US summer time 2026-03-08 to 2026-11-01 and 2027-03-14 to 2027-11-07
// (02:00 local, 07:00 and 06:00 UTC); UK summer time 2026-03-29 to 2026-10-25 and 2027-03-28 to 2027-10-31 (01:00 UTC).
#define LIVE
#include <default.c>
#include "GatewayClock.h"

#define RESULT "Log\\GatewayClockTest.txt"
int Fails = 0;

function note(string text)
{
	file_append(RESULT, text);
	file_append(RESULT, "\n");
}

function check(int ymd8, int hhmm, string what, int got, int want)
{
	if(got != want) { Fails++; note(strf("FAIL %i %04i %s: got %i, want %i", ymd8, hhmm, what, got, want)); }
}

// a UTC date and time as YYYYMMDD and HHMM, and what the rules give there
function at(int ymd8, int hhmm, int usOffset, int ukOffset, int restartUtcMin, int localHhmm)
{
	var utc = dmy(ymd8) + (hhmm / 100) / 24. + (hhmm % 100) / 1440.;
	check(ymd8, hhmm, "US offset", gwUsOffsetHours(utc), usOffset);
	check(ymd8, hhmm, "UK offset", gwUkOffsetHours(utc), ukOffset);
	check(ymd8, hhmm, "restart UTC minute", gwRestartUtcMinute(utc), restartUtcMin);
	check(ymd8, hhmm, "local HHMM, 5 min after", gwRestartLocalHhmm(utc, 5), localHhmm);
}

function main()
{
	file_delete(RESULT);
	// an ordinary day: both on summer time, then both on winter time
	at(20261020, 1200, 4, 1, 21 * 60 + 5, 2210);
	at(20261203, 1200, 5, 0, 22 * 60 + 5, 2210);
	// 2026-10-25 UK back to GMT at 01:00 UTC; the US is still on summer time until 11-01: the restart is 21:10 UK time
	at(20261025, 30, 4, 1, 21 * 60 + 5, 2210);
	at(20261025, 130, 4, 0, 21 * 60 + 5, 2110);
	at(20261027, 1200, 4, 0, 21 * 60 + 5, 2110);
	// 2026-11-01 the US back to winter time at 06:00 UTC
	at(20261101, 559, 4, 0, 21 * 60 + 5, 2110);
	at(20261101, 601, 5, 0, 22 * 60 + 5, 2210);
	// 2027-03-14 the US on summer time at 07:00 UTC, the UK still on GMT until 03-28
	at(20270314, 659, 5, 0, 22 * 60 + 5, 2210);
	at(20270314, 701, 4, 0, 21 * 60 + 5, 2110);
	at(20270316, 1200, 4, 0, 21 * 60 + 5, 2110);
	// 2027-03-28 the UK on summer time at 01:00 UTC
	at(20270328, 30, 4, 0, 21 * 60 + 5, 2110);
	at(20270328, 130, 4, 1, 21 * 60 + 5, 2210);
	// the spring of 2026: US 03-08, UK 03-29
	at(20260310, 1200, 4, 0, 21 * 60 + 5, 2110);
	at(20260330, 1200, 4, 1, 21 * 60 + 5, 2210);
	// the scheduled login (3 minutes after the restart) stays on the same UTC day
	check(20261203, 1200, "scheduled login, minute of the UTC day", gwRestartUtcMinute(dmy(20261203) + 0.5) + 3, 22 * 60 + 8);
	if(Fails == 0) note("PASS"); else note("FAIL");
	quit("GatewayClockTest done");
}
