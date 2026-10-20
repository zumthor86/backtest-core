// CloseTest0.c -- CloseTest with Hedge = 0: does a plain close reach the broker? No stop. See StopTestCore.h.
//   Zorro.exe -trade CloseTest0 -c IB-Paper-7 -d LIVE -stay
// Add -d TEST_NO_NFA to leave the NFA flag out and see whether mode 0 needs it.
#include <default.c>
#define TEST_NO_STOP
#define TEST_HEDGE 0
#include "StopTestCore.h"
