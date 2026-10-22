// CloseTest.c -- does Zorro's own close of a pool trade reach the broker? No stop. See StopTestCore.h.
//   Zorro.exe -trade CloseTest -c IB-Paper-7 -d LIVE -stay
#include <default.c>
#define TEST_NO_STOP
#define TEST_HEDGE 4
#include "StopTestCore.h"
