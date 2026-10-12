// Re-login after the IB Gateway's daily restart.
//
// The Gateway restarts once a day and drops every API connection. Without this command the Zorro IB plugin kept its
// dead connection. SET_RESTART makes the plugin release the API and log in again at the given HHMM time.
// Call liveRestart() once, in the INITRUN branch of run(), after the asset is selected.
//
// The restart is at 22:05 local on olympus (`restart_time_local` of the paper login in ares/gateway_logins.json), in
// the futures break (17:00 to 18:00 New York), so a re-login that fails costs no market time. Keep this value a few
// minutes after that one. The manual does not say which time zone HHMM is in.
#ifdef LIVE
#define LIVE_RESTART_HHMM 2210

function liveRestart()
{
	var r = brokerCommand(SET_RESTART, LIVE_RESTART_HHMM);
	printf("\nSET_RESTART %i returned %.0f", LIVE_RESTART_HHMM, r);
}
#else
function liveRestart() {}
#endif
