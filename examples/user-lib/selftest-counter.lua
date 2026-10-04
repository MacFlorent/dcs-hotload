-- Counts how often this file is read from disk: once per run that loads it, however many
-- times that run calls Hotload.load("selftest-counter"). The guarded global survives reloads.
SelftestCounterReads = (SelftestCounterReads or 0) + 1
return { version = 1 }
