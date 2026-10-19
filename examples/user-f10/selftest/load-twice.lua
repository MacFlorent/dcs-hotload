-- Expected: "done ... -> {reads = N, same = true, version = 1}", where N goes up by exactly 1
-- per click. Edit user-lib/selftest-counter.lua to "version = 2" and click again: version = 2,
-- with no mission restart.
local a = Hotload.load("selftest-counter")
local b = Hotload.load("selftest-counter")
return { version = a.version, reads = SelftestCounterReads, same = a == b }
