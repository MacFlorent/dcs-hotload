-- Running yourself is refused by the guard, not deadlocked.
-- Expected: done, result {error = "selftest/run-self is still running", outcome = "refused"}.
local r = Hotload.run("selftest/run-self")
return { outcome = r.outcome, error = r.error }
