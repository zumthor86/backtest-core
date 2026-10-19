// NfaOn.h -- sets Zorro's NFA flag in a live sleeve, and logs the state it found.
//
// IB keeps no individual trades, so the IB plugin cannot close one (ib.txt: "The NFA flag or an according NFA account
// list entry must be set for IB accounts"). With the NFA flag, an exit opens an opposite trade instead (mode.txt).
// The account rows set NFA = 14, which only "affects the default state" of the flag (account.txt). On 10-19 the
// NoiseAreaNQ exit still went to the close call: "Error 075 - closing not supported (NFA?)", 37 times, and the
// Gateway's API log shows that no order reached IB. Hedge-4 sleeves failed in the same way on 10-14, 10-15 and 10-16.
// The flag must be set in the INITRUN (mode.txt); run() sets it on every run, as the other flags.
// Call nfaOn() in the live branch of run(), after Hedge is set.
function nfaOn()
{
	if(is(INITRUN)) printf("\nNFA flag before nfaOn: %i, Hedge %i", (int)(is(NFA) != 0), Hedge);
	set(NFA);
	if(is(INITRUN)) printf("\nNFA flag after nfaOn: %i", (int)(is(NFA) != 0));
}
