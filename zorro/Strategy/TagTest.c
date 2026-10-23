// TagTest.c -- does a text in SET_ORDERTEXT reach IB as the order's orderRef? One MES, no stop. See StopTestCore.h.
//   Zorro.exe -trade TagTest -c IB-Paper-7 -d LIVE -stay
// Afterwards, from ares\:  python -m ares.services.fill_capture   then look at the order_ref of the client-7 fills.
#include <default.c>
#define TEST_NO_STOP
#define TEST_TAG "TagTest"
#include "StopTestCore.h"
