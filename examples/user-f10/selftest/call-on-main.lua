-- Expected: "done f10/selftest/call-on-main (0.2s) -> true", then, from a timer armed through
-- Hotload.callOnMain, "call-on-main: beat 1 of 10" to "beat 10 of 10", one a second, with
-- "call-on-main: collected" after beat 3. By then this run has ended, and the collection frees its
-- coroutine: a timer armed from the run itself would crash DCS at its next beat. DCS keeps running.
local beats = 0
local function beat(_, t)
  beats = beats + 1
  Hotload.log("call-on-main: beat %d of 10", beats)
  if beats == 3 then
    collectgarbage("collect")
    Hotload.log("call-on-main: collected")
  end
  if beats < 10 then
    return t + 1
  end
  return nil
end
return (Hotload.callOnMain(function()
  timer.scheduleFunction(beat, nil, timer.getTime() + 1)
end))
