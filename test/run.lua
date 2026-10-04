--- Runs every test/test_*.lua as its own process (each gets a fresh hotload instance) and fails if
--- any fails.   Usage:  lua5.1 test/run.lua [filename-substring]

assert(_VERSION == "Lua 5.1", "test/run.lua needs Lua 5.1, the DCS mission runtime; got " .. _VERSION)
require("lfs")

local dir = debug.getinfo(1, "S").source:match("^@(.+)[\\/]") or "."
local lua = arg[-1] or "lua"
local filter = arg[1]
local windows = package.config:sub(1, 1) == "\\"

local suites = {}
for entry in lfs.dir(dir) do
  if entry:match("^test_.+%.lua$") and (not filter or entry:find(filter, 1, true)) then
    suites[#suites + 1] = entry
  end
end
table.sort(suites)
if #suites == 0 then
  print("test/run.lua: no suites" .. (filter and (" match '" .. filter .. "'") or ""))
  os.exit(filter and 0 or 1)
end

local failed = {}
for _, name in ipairs(suites) do
  print("== " .. name)
  local command = string.format('"%s" "%s/%s"', lua, dir, name)
  if windows then
    command = '"' .. command .. '"'   -- cmd.exe strips one pair of quotes around the whole line
  end
  if os.execute(command) ~= 0 then
    failed[#failed + 1] = name
  end
end

if #failed > 0 then
  print("\nFAILED: " .. table.concat(failed, ", "))
  os.exit(1)
end
print("\nall " .. #suites .. " suites passed")
