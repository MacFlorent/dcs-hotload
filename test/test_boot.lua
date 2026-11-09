--- The guarded boot that hotload-setup.py writes into a mission: its second DO SCRIPT action, read
--- from skills/piloting-dcs-hotload/scripts/boot-guard.lua, after BASE_HOTLOAD_PATH is set.

local dir = debug.getinfo(1, "S").source:match("^@(.+)[\\/]") or "."
local lu = dofile(dir .. "/luaunit.lua")
local Stub = dofile(dir .. "/dcs-stub.lua")

local REPO = Stub.REPO
local GUARD_FILE = REPO .. "/skills/piloting-dcs-hotload/scripts/boot-guard.lua"

local function guard()
  local f = assert(io.open(GUARD_FILE, "r"))
  local text = f:read("*a")
  f:close()
  return assert(loadstring(text, "guard"))
end

--- A new mission: a fresh sim, no hotload yet, BASE_HOTLOAD_PATH as the first action sets it.
local function boot(path)
  local sim = Stub.new()
  HotloadCore, Hotload = nil, nil
  BASE_HOTLOAD_PATH = path
  guard()()
  return sim
end

TestBoot = {}

function TestBoot:tearDown()
  BASE_HOTLOAD_PATH = nil
end

function TestBoot:testBootsHotloadFromTheFolderItNames()
  local sim = boot(REPO)
  lu.assertNotNil(sim:line("HOTLOAD: ready"))
  lu.assertEquals(Hotload.root, REPO)
  lu.assertNotNil(HotloadCore)
end

function TestBoot:testAnUnsetPathOnlyLogs()
  local sim = boot(nil)
  lu.assertEquals(sim:line("HOTLOAD: not booted:"), "HOTLOAD: not booted: BASE_HOTLOAD_PATH is not set")
  lu.assertEquals(sim.screen, {})
  lu.assertNil(Hotload)
end

function TestBoot:testAClearedPathOnlyLogs()
  local sim = boot("")
  lu.assertEquals(sim:line("HOTLOAD: not booted:"), "HOTLOAD: not booted: BASE_HOTLOAD_PATH is not set")
  lu.assertEquals(sim.screen, {})
end

function TestBoot:testAFolderWithoutHotloadOnlyLogs()
  local sim = boot(REPO .. "/no-such-folder")
  lu.assertStrContains(sim:line("HOTLOAD: not booted:"), "no-such-folder")
  lu.assertEquals(sim.screen, {})
  lu.assertNil(Hotload)
end

function TestBoot:testNeedsNeitherIoNorLfs()
  local realIo, realLfs = io, lfs
  local text = guard()
  io, lfs = nil, nil
  local sim = Stub.new()
  HotloadCore, Hotload = nil, nil
  BASE_HOTLOAD_PATH = "/no-such-folder"
  local ok, err = pcall(text)
  io, lfs = realIo, realLfs
  lu.assertTrue(ok, err)
  lu.assertNotNil(sim:line("HOTLOAD: not booted:"))
  lu.assertEquals(sim.screen, {})
end

os.exit(lu.LuaUnit.run())
