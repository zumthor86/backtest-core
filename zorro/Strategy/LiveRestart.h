// Re-login after the IB Gateway's daily restart.
//
// The Gateway restarts once a day and drops every API connection. Without this command the Zorro IB plugin kept its
// dead connection. SET_RESTART makes the plugin release the API and log in again at the given HHMM time.
// With it set, the sleeves still stayed disconnected on most nights (10-13 to 10-19), so Heartbeat.h's hbRelogin()
// also logs in again when the feed stays dead, and hbScheduledRelogin() once a night.
// Call liveRestart() once, in the INITRUN branch of run(), after the asset is selected.
//
// The restart is at 17:05 New York time (`restart_time_new_york` of the paper login in ares/gateway_logins.json), in the
// futures break (17:00 to 18:00 New York), so a re-login that fails costs no market time. This value is a few minutes
// after it, worked out by GatewayClock.h when the sleeve starts: 22:10 UK time, or 21:10 in the weeks when the UK and the
// US clocks differ. A change of clocks is on a Sunday and the week start starts the sleeves after it. The manual does not
// say which time zone HHMM is in; the local clock is assumed, as before.
#include "GatewayClock.h"
#ifdef LIVE
#define LIVE_RESTART_AFTER_MIN 5

function liveRestart()
{
	int hhmm = gwRestartLocalHhmm(wdate(NOW), LIVE_RESTART_AFTER_MIN);
	var r = brokerCommand(SET_RESTART, hhmm);
	printf("\nSET_RESTART %i returned %.0f", hhmm, r);
}
#else
function liveRestart() {}
#endif
