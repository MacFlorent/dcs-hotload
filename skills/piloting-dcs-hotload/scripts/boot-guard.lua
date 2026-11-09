local p, f, err = BASE_HOTLOAD_PATH
if type(p) ~= "string" or p == "" then err = "BASE_HOTLOAD_PATH is not set"
else f, err = loadfile(p .. "/dcs-hotload.lua") end
if not f then env.info("HOTLOAD: not booted: " .. tostring(err)) return end
Hotload = Hotload or {}; Hotload.root = p; f()
