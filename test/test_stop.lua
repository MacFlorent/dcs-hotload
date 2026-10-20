--- Hotload.stop: one run stopped by its label, from a run, its callOnMain function or predicate,
--- or from outside any run.

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

--- The index in sim.logs of the first line containing `text`.
local function indexOf(text)
  for i, line in ipairs(sim.logs) do
    if line:find(text, 1, true) then
      return i
    end
  end
  error("no log line contains " .. text)
end

TestStop = {}

function TestStop:setUp()
  sim = Stub.new()
  root = Stub.tempRoot("stop", { ["user-inbox/"] = true, ["user-outbox/"] = true, ["user-f10/"] = true })
  sim:load(root)
end

function TestStop:testACommandStopsAnotherThatIsWaiting()
  inbox("target.lua", "Hotload.wait(1000) return 1")
  sim:advance(4)
  inbox("stopper.lua", 'return Hotload.stop("inbox/target")')
  sim:advance(4)
  lu.assertEquals(outbox("target.lua").status, "stopped")
  local r = outbox("stopper.lua")
  lu.assertEquals(r.status, "done")
  lu.assertEquals(r.result, true)
  lu.assertNotNil(sim:line("stop inbox/target (from inbox/stopper)"))
  lu.assertEquals(sim:count("stopped inbox/target"), 1)
end

function TestStop:testAnUnknownOrFinishedLabelReturnsFalse()
  inbox("quick.lua", "return 7")
  sim:advance(4)
  inbox("stopper.lua", 'return { Hotload.stop("inbox/quick"), Hotload.stop("inbox/nobody") }')
  sim:advance(4)
  lu.assertEquals(outbox("stopper.lua").result, { false, false })
  lu.assertEquals(outbox("quick.lua").status, "done")
end

function TestStop:testTwoStopsOfOneTargetFinishItOnce()
  inbox("target.lua", "Hotload.wait(1000) return 1")
  sim:advance(4)
  inbox("stopper.lua", 'return { Hotload.stop("inbox/target"), Hotload.stop("inbox/target") }')
  sim:advance(4)
  lu.assertEquals(outbox("stopper.lua").result, { true, false })
  lu.assertEquals(sim:count("stopped inbox/target"), 1)
end

function TestStop:testAStoppedTargetIsNotSteppedAgain()
  -- Logs on every resume; nothing of it may follow the stop, whichever order the tick visits them.
  inbox("target.lua", 'while true do Hotload.log("alive") Hotload.wait(0.1) end')
  sim:advance(4)
  inbox("stopper.lua", 'return Hotload.stop("inbox/target")')
  sim:advance(4)
  local at = indexOf("stop inbox/target")
  for i = at + 1, #sim.logs do
    lu.assertNil(sim.logs[i]:find("[inbox/target] alive", 1, true), sim.logs[i])
  end
end

function TestStop:testARunCannotStopItself()
  inbox("self.lua", 'return Hotload.stop("inbox/self")')
  sim:advance(4)
  local r = outbox("self.lua")
  lu.assertEquals(r.status, "fail")
  lu.assertStrContains(r.error, "Hotload.stop: inbox/self cannot stop itself -- return instead")
end

function TestStop:testNorFromItsOwnCallOnMainFunction()
  inbox("self.lua", [[local ok, err = Hotload.callOnMain(function() return Hotload.stop("inbox/self") end)
return { ok = ok, err = err }]])
  sim:advance(4)
  local r = outbox("self.lua")
  lu.assertEquals(r.status, "done")
  lu.assertEquals(r.result.ok, false)
  lu.assertStrContains(r.result.err, "cannot stop itself")
end

function TestStop:testNorFromItsOwnPredicate()
  inbox("self.lua", 'return Hotload.waitFor(function() return Hotload.stop("inbox/self") end, 5)')
  sim:advance(4)
  local r = outbox("self.lua")
  lu.assertEquals(r.status, "fail")
  lu.assertStrContains(r.error, "cannot stop itself")
end

function TestStop:testFromOutsideARunAndTheTargetsCallOnMainNeverRuns()
  Stub.write(root .. "/user-f10/pending.lua", [[Hotload.callOnMain(function() Hotload.log("fn ran") end)]])
  sim:click("Refresh menu")
  sim:click("pending")
  sim:advance(0.15)                     -- first resume at 0.1: the run asks for the call
  lu.assertTrue(Hotload.stop("f10/pending"))
  sim:advance(1)
  lu.assertNotNil(sim:line("stop f10/pending (from outside a run)"))
  lu.assertEquals(sim:count("stopped f10/pending"), 1)
  lu.assertEquals(sim:count("fn ran"), 0)
end

function TestStop:testABadLabelRaises()
  lu.assertErrorMsgContains("Hotload.stop: label must be a non-empty string", Hotload.stop, nil)
  lu.assertErrorMsgContains("Hotload.stop: label must be a non-empty string", Hotload.stop, "")
end

os.exit(lu.LuaUnit.run())
