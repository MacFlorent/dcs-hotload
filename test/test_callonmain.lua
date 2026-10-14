--- Hotload.callOnMain: a function run on the mission's main Lua state, from inside a run.

local dir = debug.getinfo(1, "S").source:match("^@(.+)[\\/]") or "."
local lu = dofile(dir .. "/luaunit.lua")
local Stub = dofile(dir .. "/dcs-stub.lua")

local sim

--- A fresh hotload on a temp root holding one user-scripts/<name>.lua, clicked and run.
local function run(name, code, seconds)
  sim:load(Stub.tempRoot("callonmain-" .. name, { ["user-scripts/" .. name .. ".lua"] = code }))
  sim:click(name)
  sim:advance(seconds or 1)
end

local function armedFrom(arg)
  for _, call in ipairs(sim.armed) do
    if call.arg == arg then
      return call.fromCoroutine and "coroutine" or "main"
    end
  end
  return "never armed"
end

TestCallOnMain = {}

function TestCallOnMain:setUp()
  sim = Stub.new()
end

function TestCallOnMain:testATimerArmedInFnIsArmedFromTheMainState()
  run("main", [[
    return (Hotload.callOnMain(function()
      timer.scheduleFunction(function() end, "probe", timer.getTime() + 60)
    end))]])
  lu.assertEquals(armedFrom("probe"), "main")
  lu.assertStrContains(sim:line("done main"), "-> true")
end

function TestCallOnMain:testATimerArmedInTheRunIsArmedFromItsCoroutine()
  -- The contrast that shows the stub can tell the two apart.
  run("direct", [[timer.scheduleFunction(function() end, "probe", timer.getTime() + 60)]])
  lu.assertEquals(armedFrom("probe"), "coroutine")
end

function TestCallOnMain:testEveryResultReachesTheRunTrailingNilsIncluded()
  run("results", [[
    local function pack(...) return select("#", ...), ... end
    local n, ok, a, b, c = pack(Hotload.callOnMain(function() return 1, nil, "x", nil end))
    return string.format("%d %s %s %s %s", n, tostring(ok), tostring(a), tostring(b), tostring(c))]])
  lu.assertStrContains(sim:line("done results"), '"5 true 1 nil x"')
end

function TestCallOnMain:testTwoCallsInARowBothRunInOrder()
  run("twice", [[
    local seen = {}
    Hotload.callOnMain(function() seen[#seen + 1] = "a" end)
    Hotload.callOnMain(function() seen[#seen + 1] = "b" end)
    return table.concat(seen)]])
  lu.assertStrContains(sim:line("done twice"), '"ab"')
end

function TestCallOnMain:testARaiseInFnComesBackAsFalseAndIsLoggedWithItsTraceback()
  run("raises", [[
    local ok, message = Hotload.callOnMain(function() error("boom") end)
    return tostring(ok) .. " " .. message]])
  lu.assertStrContains(sim:line("done raises"), "false ")
  lu.assertStrContains(sim:line("done raises"), "boom")
  local logged = sim:line("[raises] callOnMain failed")
  lu.assertStrContains(logged, "boom")
  lu.assertStrContains(logged, "stack traceback")
end

function TestCallOnMain:testPausingInsideFnComesBackAsFalse()
  run("pauses", [[
    local okWait, waitMessage = Hotload.callOnMain(function() Hotload.wait(1) end)
    local okNested, nestedMessage = Hotload.callOnMain(function()
      return Hotload.callOnMain(function() end)
    end)
    return string.format("%s %s | %s %s", tostring(okWait), waitMessage, tostring(okNested), nestedMessage)]])
  local line = sim:line("done pauses")
  lu.assertStrContains(line, "false ")
  lu.assertStrContains(line, "Hotload.wait can only be called inside a hotload run")
  lu.assertStrContains(line, "Hotload.callOnMain can only be called inside a hotload run")
end

function TestCallOnMain:testALogLineInFnCarriesTheRunsLabel()
  run("logs", [[Hotload.callOnMain(function() Hotload.log("from main") end)]])
  lu.assertNotNil(sim:line("[logs] from main"))
end

function TestCallOnMain:testStopAllBeforeTheNextTickMeansFnNeverRuns()
  sim:load(Stub.tempRoot("callonmain-stopped", { ["user-scripts/stopped.lua"] =
    [[Hotload.callOnMain(function() Hotload.log("fn ran") end)]] }))
  sim:click("stopped")
  sim:advance(0.15)        -- the run's first resume, at 0.1: it asks for the call
  sim:click("Stop all runs")
  sim:advance(1)
  lu.assertEquals(sim:count("stopped stopped"), 1)
  lu.assertEquals(sim:count("fn ran"), 0)
end

function TestCallOnMain:testOutsideARunItRaises()
  sim:load(Stub.tempRoot("callonmain-outside", {}))
  lu.assertErrorMsgContains("Hotload.callOnMain can only be called inside a hotload run",
    Hotload.callOnMain, function() end)
end

function TestCallOnMain:testFromAPredicateItFailsTheRun()
  run("predicate", [[Hotload.waitFor(function() return Hotload.callOnMain(function() end) end, 5)]])
  lu.assertStrContains(sim:line("FAIL predicate"), "can only be called inside a hotload run")
end

function TestCallOnMain:testANonFunctionFailsTheRun()
  run("notfn", [[Hotload.callOnMain(42)]])
  lu.assertStrContains(sim:line("FAIL notfn"), "Hotload.callOnMain: fn must be a function")
end

os.exit(lu.LuaUnit.run())
