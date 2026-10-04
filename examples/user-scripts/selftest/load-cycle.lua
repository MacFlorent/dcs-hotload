-- Expected: "FAIL selftest/load-cycle: ...load cycle: selftest-cycle-a" -- no stack overflow.
Hotload.load("selftest-cycle-a")
return "unreachable"
