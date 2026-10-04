-- Expected: "FAIL selftest/load-missing: ...load no-such-lib: cannot open ..."
Hotload.load("no-such-lib")
return "unreachable"
