--- Startup: the sanitisation check, finding the root folder from the chunk name DCS reports
--- (DCS's dofile names a chunk with the plain path, no "@"), and a root that cannot be read.

local dir = debug.getinfo(1, "S").source:match("^@(.+)[\\/]") or "."
local lu = dofile(dir .. "/luaunit.lua")
local Stub = dofile(dir .. "/dcs-stub.lua")

local REPO = Stub.REPO
local CORE_FILE = (REPO .. "/dcs-hotload.lua")
local realGetinfo = debug.getinfo

--- Loads the core with no explicit root and debug.getinfo reporting `info`.
local function loadReporting(sim, info)
  HotloadCore, Hotload = nil, nil
  sim.scheduled = {}
  debug.getinfo = function() return info end
  local ok, err = pcall(dofile, CORE_FILE)
  debug.getinfo = realGetinfo
  assert(ok, err)
end

TestRoot = {}

function TestRoot:testFindsItsFolderFromAStockLuaChunkName()
  local sim = Stub.new()
  HotloadCore, Hotload = nil, nil
  dofile(CORE_FILE)
  lu.assertNotNil(sim:line("HOTLOAD: ready"))
  lu.assertEquals(Hotload.root:gsub("\\", "/"):lower(), REPO:gsub("\\", "/"):lower())
end

function TestRoot:testFindsItsFolderFromAPathWithoutTheAtSign()
  local sim = Stub.new()
  loadReporting(sim, { source = CORE_FILE, short_src = "..." })
  lu.assertNotNil(sim:line("HOTLOAD: ready"))
end

function TestRoot:testFindsItsFolderFromShortSrc()
  local sim = Stub.new()
  loadReporting(sim, { source = "=?", short_src = CORE_FILE })
  lu.assertNotNil(sim:line("HOTLOAD: ready"))
end

function TestRoot:testSaysWhatItSawWhenNoPathIsUsable()
  local sim = Stub.new()
  loadReporting(sim, { source = "dofile(...)", short_src = '[string "dofile(...)"]' })
  lu.assertStrContains(sim:line("cannot tell where dcs-hotload.lua is"), 'source="dofile(...)"')
  lu.assertNil(HotloadCore)
end

function TestRoot:testAPathToAMissingFileIsNotTrusted()
  local sim = Stub.new()
  loadReporting(sim, { source = "@/nowhere/dcs-hotload.lua", short_src = "x" })
  lu.assertNotNil(sim:line("cannot tell where dcs-hotload.lua is"))
end

function TestRoot:testAnUnreadableUserScriptsFolderIsReported()
  local sim = Stub.new()
  sim:load(REPO .. "/no-such-root")
  lu.assertStrContains(sim:line("cannot read"), "user-scripts")
  lu.assertStrContains(sim.screen[1], "dcs-hotload:")
end

function TestRoot:testMissingSanitisationEditStopsWithAMessage()
  local sim = Stub.new()
  local realIo = io
  io = nil   -- luacheck: ignore
  local ok, err = pcall(sim.load, sim, REPO .. "/examples")
  io = realIo   -- luacheck: ignore
  assert(ok, err)
  lu.assertStrContains(sim:line("re-apply the edit"), "missing: io")
  lu.assertNil(HotloadCore)
end

os.exit(lu.LuaUnit.run())
