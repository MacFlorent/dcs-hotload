--- The heartbeat: while the mailbox is on, user-outbox/_heartbeat.lua is rewritten at startup and
--- at every poll with the sortie name, the sim time, the version and the active runs.

local dir = debug.getinfo(1, "S").source:match("^@(.+)[\\/]") or "."
local lu = dofile(dir .. "/luaunit.lua")
local Stub = dofile(dir .. "/dcs-stub.lua")

local sim, root

local function mailboxRoot(files)
  files = files or {}
  files["user-inbox/"] = true
  files["user-outbox/"] = true
  return Stub.tempRoot("heartbeat", files)
end

local function heartbeat()
  local handle = io.open(root .. "/user-outbox/_heartbeat.lua", "r")
  if not handle then
    return nil
  end
  local text = handle:read("*a")
  handle:close()
  return assert(loadstring(text))()
end

TestHeartbeat = {}

function TestHeartbeat:setUp()
  sim = Stub.new()
end

function TestHeartbeat:testWrittenAtStartup()
  root = mailboxRoot()
  sim:load(root)
  local beat = heartbeat()
  lu.assertNotNil(beat, "no heartbeat after startup")
  lu.assertEquals(beat.mission, "stub-mission")
  lu.assertEquals(beat.time, 0)
  lu.assertEquals(beat.version, Hotload.version)
  lu.assertEquals(beat.runs, {})
end

function TestHeartbeat:testTheFileReadsAsAnOutboxRecordDoes()
  root = mailboxRoot()
  sim:load(root)
  local handle = assert(io.open(root .. "/user-outbox/_heartbeat.lua", "r"))
  local first = handle:read("*l")
  handle:close()
  lu.assertEquals(first, "-- dcs-hotload heartbeat")
end

function TestHeartbeat:testTheTimeFollowsTheSimClock()
  root = mailboxRoot()
  sim:load(root)
  sim:advance(5.5)
  lu.assertEquals(heartbeat().time, 5)
end

function TestHeartbeat:testRunsListsActiveRunsWithTheirStart()
  root = mailboxRoot({
    ["user-inbox/long.lua"] = "Hotload.wait(10) return 1",
    ["user-f10/menu.lua"] = "Hotload.wait(10)",
  })
  sim:load(root)
  sim:advance(2.5)   -- held still over one poll, picked up at the second, at t=2
  sim:click("menu")
  sim:advance(0.5)   -- the next poll writes the heartbeat, at t=3
  local runs = heartbeat().runs
  lu.assertEquals(runs["inbox/long"], 2)
  lu.assertEquals(runs["f10/menu"], 2.5)
  sim:advance(15)
  lu.assertEquals(heartbeat().runs, {})
end

function TestHeartbeat:testNoHeartbeatWhenTheMailboxIsOff()
  root = Stub.tempRoot("heartbeat", { ["user-outbox/"] = true })
  sim:load(root)
  sim:advance(3)
  lu.assertNil(heartbeat())
end

function TestHeartbeat:testAnEmptySortieLeavesMissionOut()
  sim.dict.DictKey_sortie_1 = ""
  root = mailboxRoot()
  sim:load(root)
  lu.assertNil(heartbeat().mission)
end

function TestHeartbeat:testASortieThatRaisesLeavesMissionOut()
  env.getValueDictByKey = function() error("no dictionary") end
  root = mailboxRoot()
  sim:load(root)
  local beat = heartbeat()
  lu.assertNotNil(beat)
  lu.assertNil(beat.mission)
end

function TestHeartbeat:testAFailedWriteIsLoggedOnceUntilAWriteSucceeds()
  root = mailboxRoot()
  sim:load(root)
  Stub.rmtree(root .. "/user-outbox")
  sim:advance(5)
  lu.assertEquals(sim:count("cannot write the heartbeat"), 1)
  lu.assertEquals(sim:count("mailbox poll error"), 0)
  lfs.mkdir(root .. "/user-outbox")
  sim:advance(2)
  lu.assertNotNil(heartbeat(), "not retried once the folder is back")
  Stub.rmtree(root .. "/user-outbox")
  sim:advance(2)
  lu.assertEquals(sim:count("cannot write the heartbeat"), 2)
end

function TestHeartbeat:testACommandStillRunsBesideIt()
  root = mailboxRoot({ ["user-inbox/c.lua"] = "return 1" })
  sim:load(root)
  sim:advance(4)
  lu.assertEquals(sim:count("done inbox/c"), 1)
  lu.assertEquals(sim:count("_heartbeat"), 0)
end

os.exit(lu.LuaUnit.run())
