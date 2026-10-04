-- A wait from a coroutine the script made itself must refuse, not yield into the wrong place.
-- Expected: done, result ok = false, err contains "can only be called inside a hotload run".
local co = coroutine.create(function()
  Hotload.wait(1)
end)
local ok, err = coroutine.resume(co)
return { ok = ok, err = tostring(err) }
