// GatewayClock.h -- when the paper IB Gateway restarts, from the clock rules of the US and the UK.
//
// The Gateway restarts once a night at 17:05 New York time (`restart_time_new_york` of the paper login in
// ares/gateway_logins.json). That is inside the Globex break (17:00 to 18:00 New York) all year, so the restart drops every
// API connection while the market is shut. A fixed local time cannot do that: the UK changes its clocks on the last Sunday
// of March and October, the US on the second Sunday of March and the first Sunday of November. In UTC the restart is 21:05
// while New York has summer time and 22:05 while it has winter time; in UK time it is 22:05, except in the weeks between the
// two changes (2026-10-25 to 11-01, 2027-03-14 to 03-28), when it is 21:05. Before 2026-10-22 the sleeves assumed 22:05 UK
// time, which put the restart five minutes after the open in the first of those weeks.
//
// US summer time runs from 07:00 UTC on the second Sunday of March to 06:00 UTC on the first Sunday of November (02:00 local
// both times); UK summer time from 01:00 UTC on the last Sunday of March to 01:00 UTC on the last Sunday of October.
// `ares` start-gateway.ps1 and ares.adapters.login_config.local_restart work out the same moment for the Gateway itself.
#ifndef GATEWAY_CLOCK_H
#define GATEWAY_CLOCK_H
#ifdef LIVE
#define GW_RESTART_NY_MIN (17 * 60 + 5)

int gwDayOfWeek(var date) { return ((int)floor(date) + 6) % 7; }       // 0 = Sunday

var gwNthSunday(int y, int month, int n)       // the n-th Sunday (1 = first) of a month, as a date
{
	var d1 = dmy(y * 10000 + month * 100 + 1);
	return d1 + (7 - gwDayOfWeek(d1)) % 7 + 7 * (n - 1);
}

var gwLastSunday(int y, int month)             // the last Sunday of a month before December
{
	var next = dmy(y * 10000 + (month + 1) * 100 + 1);
	int back = gwDayOfWeek(next);
	if(back == 0) back = 7;
	return next - back;
}

int gwUkOffsetHours(var utc)                   // local UK time minus UTC
{
	int y = ymd(utc) / 10000;
	return utc >= gwLastSunday(y, 3) + 1. / 24 && utc < gwLastSunday(y, 10) + 1. / 24;
}

int gwUsOffsetHours(var utc)                   // UTC minus New York time: 4 in summer time, 5 in winter time
{
	int y = ymd(utc) / 10000;
	return ifelse(utc >= gwNthSunday(y, 3, 2) + 7. / 24 && utc < gwNthSunday(y, 11, 1) + 6. / 24, 4, 5);
}

int gwRestartUtcMinute(var utc)                // minutes after 00:00 UTC, on the UTC day of `utc`
{
	return GW_RESTART_NY_MIN + 60 * gwUsOffsetHours(utc);
}

int gwRestartLocalHhmm(var utc, int afterMin)  // the restart plus a few minutes, as the local clock reads it, HHMM
{
	int m = (gwRestartUtcMinute(utc) + afterMin + 60 * gwUkOffsetHours(utc)) % 1440;
	return (m / 60) * 100 + m % 60;
}
#endif
#endif
