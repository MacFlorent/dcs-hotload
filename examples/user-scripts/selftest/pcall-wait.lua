-- Stock Lua 5.1 cannot yield across pcall. Expected: done, result ok = false with an error
-- mentioning "attempt to yield across"; the run ends, nothing hangs. If DCS turns out to run
-- LuaJIT (which can), the result is ok = true after 1 s instead -- record which one you see.
local ok, err = pcall(function()
  Hotload.wait(1)
end)
return { ok = ok, err = tostring(err) }
