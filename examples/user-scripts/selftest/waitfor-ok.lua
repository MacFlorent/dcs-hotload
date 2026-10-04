-- Expected: "done selftest/waitfor-ok (3.1s) -> true" (about 3 s, never the 10 s timeout).
local readyAt = timer.getTime() + 3
return Hotload.waitFor(function()
  return timer.getTime() >= readyAt
end, 10)
