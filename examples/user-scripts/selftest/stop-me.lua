-- Waits forever in 30 s steps. "Stop all runs" ends it: "stopped selftest/stop-me".
while true do
  Hotload.wait(30)
  Hotload.log("still here")
end
