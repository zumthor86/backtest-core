// Re-login after the IB Gateway's daily restart.
//
// The Gateway restarts once a day (03:00 local on olympus) and drops every API connection. Without this command the
// Zorro IB plugin kept its dead connection: on 2026-10-08 all six sleeves stopped at 02:59 and never traded again until
// they were started by hand. SET_RESTART makes the plugin release the API and log in again at the given HHMM time.
// Call liveRestart() once, in the INITRUN branch of run(), after the asset is selected.
//
// The manual does not say which time zone HHMM is in. 0305 is safe for both: 03:05 local follows the 03:00 restart, and
// if the plugin reads UTC the re-login comes at 04:05 local, one hour late but still a recovery.
#ifdef LIVE
#define LIVE_RESTART_HHMM 305

function liveRestart()
{
	var r = brokerCommand(SET_RESTART, LIVE_RESTART_HHMM);
	printf("\nSET_RESTART %i returned %.0f", LIVE_RESTART_HHMM, r);
}
#else
function liveRestart() {}
#endif
