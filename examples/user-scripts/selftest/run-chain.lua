-- Hotload.run starts each entry as its own run and waits for it.
-- Expected: done, result {broken = "fail", missing = "refused", ok = "done",
-- value = {answer = 42, ok = true}}; the log also shows the three child runs by their own labels.
local ok = Hotload.run("selftest/return-value")
local broken = Hotload.run("selftest/runtime-error")
local missing = Hotload.run("selftest/no-such-script")
return { ok = ok.outcome, value = ok.result, broken = broken.outcome, missing = missing.outcome }
