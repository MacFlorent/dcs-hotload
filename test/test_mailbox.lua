--- The mailbox: user-inbox/*.lua runs once each; user-outbox/<same name>.lua is the token and then
--- the outcome. Pickup needs a stable file (size + modification unchanged over a poll), no outbox
--- file, and no active run of the same name.

local dir = debug.getinfo(1, "S").source:match("^@(.+)[\\/]") or "."
local lu = dofile(dir .. "/luaunit.lua")
local Stub = dofile(dir .. "/dcs-stub.lua")

local sim, root

local function inbox(name, text)
  Stub.write(root .. "/user-inbox/" .. name, text)
end

local function outbox(name)
  local handle = io.open(root .. "/user-outbox/" .. name, "r")
  if not handle then
    return nil
  end
  local text = handle:read("*a")
  handle:close()
  return assert(loadstring(text))()
end

TestMailbox = {}

function TestMailbox:setUp()
  sim = Stub.new()
  root = Stub.tempRoot("mailbox", {
    ["user-inbox/"] = true,
    ["user-outbox/"] = true,
    ["user-scripts/hello.lua"] = "return { hi = true }",
    ["user-scripts/slow.lua"] = "Hotload.wait(100) return 1",
  })
  sim:load(root)
end

function TestMailbox:testTheReadyLineSaysMailboxOn()
  lu.assertStrContains(sim:line("HOTLOAD: ready"), "mailbox on")
end

function TestMailbox:testACommandRunsOnceAndItsOutboxHoldsTheResult()
  inbox("c1.lua", "return 6 * 7")
  sim:advance(0.5)
  lu.assertNil(outbox("c1.lua"), "picked up before the file held still for a poll")
  sim:advance(3)
  local r = outbox("c1.lua")
  lu.assertEquals(r.status, "done")
  lu.assertEquals(r.result, 42)
  lu.assertEquals(r.label, "inbox/c1")
  lu.assertNotNil(r.started)
  lu.assertNotNil(r.duration)
  sim:advance(5)
  lu.assertEquals(sim:count("start inbox/c1"), 1)
end

function TestMailbox:testHotloadRunReturnsTheEntrysOutcome()
  inbox("c2.lua", 'return Hotload.run("hello")')
  sim:advance(4)
  local r = outbox("c2.lua")
  lu.assertEquals(r.status, "done")
  lu.assertEquals(r.result.outcome, "done")
  lu.assertEquals(r.result.result, { hi = true })
end

function TestMailbox:testFailuresAndRefusalsAreReported()
  inbox("c3.lua", 'error("boom")')
  inbox("c4.lua", "local x = = 1")
  sim:advance(4)
  local failed, refused = outbox("c3.lua"), outbox("c4.lua")
  lu.assertEquals(failed.status, "fail")
  lu.assertStrContains(failed.error, "boom")
  lu.assertNotNil(failed.traceback)
  lu.assertEquals(refused.status, "refused")
  lu.assertStrContains(refused.error, "unexpected symbol")
end

function TestMailbox:testUnderscoreAndNonLuaFilesAreIgnored()
  inbox("_draft.lua", "return 1")
  inbox("notes.txt", "x")
  sim:advance(4)
  lu.assertNil(outbox("_draft.lua"))
  lu.assertNil(outbox("notes.txt"))
end

function TestMailbox:testAFileSavedInTwoStepsRunsOnlyWhenComplete()
  inbox("c5.lua", "return ")
  sim:advance(1)
  inbox("c5.lua", "return 'complete'")
  sim:advance(5)
  local r = outbox("c5.lua")
  lu.assertEquals(r.status, "done")
  lu.assertEquals(r.result, "complete")
end

function TestMailbox:testAnEmptyFileWaitsForItsFirstSave()
  inbox("c6.lua", "")
  sim:advance(4)
  lu.assertNil(outbox("c6.lua"))
  inbox("c6.lua", "return 'typed'")
  sim:advance(4)
  lu.assertEquals(outbox("c6.lua").result, "typed")
end

function TestMailbox:testDeletingTheOutboxMidRunStartsNoDuplicate()
  inbox("c7.lua", "Hotload.wait(10) return 'slow'")
  sim:advance(3)
  lu.assertEquals(outbox("c7.lua").status, "started")
  os.remove(root .. "/user-outbox/c7.lua")
  sim:advance(3)
  lu.assertEquals(sim:count("start inbox/c7"), 1)
  sim:advance(10)
  lu.assertEquals(outbox("c7.lua").result, "slow")
end

function TestMailbox:testDeletingAFinishedOutboxRunsTheCommandAgain()
  inbox("c8.lua", "return 1")
  sim:advance(4)
  os.remove(root .. "/user-outbox/c8.lua")
  sim:advance(4)
  lu.assertEquals(sim:count("start inbox/c8"), 2)
end

function TestMailbox:testAfterARestartAStartedCommandIsNotRunAgain()
  inbox("c9.lua", "Hotload.wait(100) return 1")
  sim:advance(3)
  lu.assertEquals(outbox("c9.lua").status, "started")
  sim:load(root)
  sim:advance(5)
  lu.assertEquals(sim:count("start inbox/c9"), 1)
end

function TestMailbox:testUnwritableValuesStillGiveAReadableOutbox()
  inbox("c10.lua", "local t = { f = print, n = 0/0 } t.me = t return t")
  sim:advance(4)
  local r = outbox("c10.lua")
  lu.assertEquals(r.result.f, "<function>")
  lu.assertEquals(r.result.me, "<cycle>")
end

function TestMailbox:testStopAllMarksACommandStopped()
  inbox("c11.lua", 'return Hotload.run("slow")')
  sim:advance(4)
  sim:click("Stop all runs")
  lu.assertEquals(outbox("c11.lua").status, "stopped")
end

function TestMailbox:testAnInternalErrorStillWritesTheOutbox()
  inbox("c12.lua", "coroutine.yield({ hotload = true }) return 1")
  sim:advance(4)
  local r = outbox("c12.lua")
  lu.assertEquals(r.status, "fail")
  lu.assertStrContains(r.error, "internal error")
end

TestMailboxSetup = {}

function TestMailboxSetup:testNoInboxFolderMeansNoMailboxAndNoMessage()
  local s = Stub.new()
  s:load(Stub.tempRoot("nobox", { ["user-scripts/"] = true }))
  lu.assertStrContains(s:line("HOTLOAD: ready"), "mailbox off")
  lu.assertEquals(s.screen, { "dcs-hotload " .. Hotload.version .. " ready, mailbox off" })
end

function TestMailboxSetup:testAnInboxWithoutAnOutboxIsReported()
  local s = Stub.new()
  s:load(Stub.tempRoot("halfbox", { ["user-scripts/"] = true, ["user-inbox/"] = true }))
  lu.assertStrContains(s:line("HOTLOAD: ready"), "mailbox off")
  lu.assertNotNil(s:line("user-outbox"))
end

os.exit(lu.LuaUnit.run())
