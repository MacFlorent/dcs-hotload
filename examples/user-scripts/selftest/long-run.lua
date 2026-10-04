-- 60 s, logging every 10 s. While it runs: a second click on it is refused
-- ("selftest/long-run is still running"), and other entries run alongside it.
for i = 1, 6 do
  Hotload.wait(10)
  Hotload.log("tick %d of 6", i)
end
return "long run complete"
