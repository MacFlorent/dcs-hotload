-- Expected: "t=   0.1 [selftest/wait] waiting 5 s", "t=   5.1 [selftest/wait] waited",
-- then "done selftest/wait (5.1s) -> "waited 5 s"". The first resume happens on the first tick,
-- 0.1 s after the click, so every time here may be a tick or two later than the round number.
Hotload.log("waiting 5 s")
Hotload.wait(5)
Hotload.log("waited")
return "waited 5 s"
