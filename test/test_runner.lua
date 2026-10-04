--- The runner: clicks, waits, errors, the duplicate-run guard, Stop all, Hotload.load and
--- Hotload.run. Uses examples/ as the hotload root, so the shipped self-tests are exercised too.

local dir = debug.getinfo(1, "S").source:match("^@(.+)[\\/]") or "."
local lu = dofile(dir .. "/luaunit.lua")
local Stub = dofile(dir .. "/dcs-stub.lua")

local EXAMPLES = Stub.REPO .. "/examples"
local sim

local function clickAndRun(path, seconds)
  sim:click(path)
  sim:advance(seconds or 0.5)
end

TestRunner = {}

function TestRunner:setUp()
  sim = Stub.new()
  sim:load(EXAMPLES)
end

function TestRunner:testReadyLineCarriesTheVersionAndTheMailboxState()
  lu.assertNotNil(sim:line("HOTLOAD: ready, version " .. Hotload.version .. ", root "))
  lu.assertStrContains(sim:line("HOTLOAD: ready"), "mailbox off")
end

function TestRunner:testReadyIsShownOnScreenWithTheVersion()
  lu.assertEquals(sim.screen[1], "dcs-hotload " .. Hotload.version .. " ready, mailbox off")
end

function TestRunner:testAReturnedValueIsLoggedAndShown()
  clickAndRun("selftest/return-value")
  lu.assertNotNil(sim:line("done selftest/return-value (0.1s) -> {answer = 42, ok = true}"))
  lu.assertStrContains(sim.screen[#sim.screen], "{answer = 42, ok = true}")
end

function TestRunner:testARuntimeErrorFailsWithATraceback()
  clickAndRun("selftest/runtime-error")
  local line = sim:line("FAIL selftest/runtime-error")
  lu.assertStrContains(line, "attempt to index local 'missing'")
  lu.assertStrContains(line, "stack traceback")
end

function TestRunner:testASyntaxErrorIsRefusedWithoutARun()
  clickAndRun("selftest/syntax-error")
  lu.assertStrContains(sim:line("refused selftest/syntax-error"), "unexpected symbol")
  lu.assertEquals(sim:count("start selftest/syntax-error"), 0)
end

function TestRunner:testUnderscoreFilesAreNotInTheMenu()
  lu.assertError(function() sim:find("selftest/_draft") end)
  lu.assertError(function() sim:find("selftest/draft") end)
end

function TestRunner:testWaitTakesSimTime()
  clickAndRun("selftest/wait", 4)
  lu.assertEquals(sim:count("done selftest/wait"), 0)
  sim:advance(2)
  lu.assertStrContains(sim:line("done selftest/wait"), '"waited 5 s"')
end

function TestRunner:testWaitForReturnsTrueOrFalseAndNeverRaises()
  clickAndRun("selftest/waitfor-ok", 4)
  clickAndRun("selftest/waitfor-timeout", 4)
  lu.assertStrContains(sim:line("done selftest/waitfor-ok"), "-> true")
  lu.assertStrContains(sim:line("done selftest/waitfor-timeout"), "-> false")
end

function TestRunner:testARaisingPredicateFailsOnlyItsRun()
  clickAndRun("selftest/long-run", 1)
  clickAndRun("selftest/predicate-raises", 1)
  lu.assertStrContains(sim:line("FAIL selftest/predicate-raises"), "waitFor predicate raised")
  sim:advance(10)
  lu.assertNotNil(sim:line("[selftest/long-run] tick 1 of 6"))
end

function TestRunner:testTheSameScriptCannotRunTwiceButOthersRunAlongside()
  clickAndRun("selftest/long-run", 1)
  clickAndRun("selftest/long-run", 1)
  lu.assertEquals(sim:count("selftest/long-run is still running"), 1)
  clickAndRun("selftest/wait", 6)
  lu.assertNotNil(sim:line("done selftest/wait"))
  lu.assertEquals(sim:count("done selftest/long-run"), 0)
end

function TestRunner:testTheGuardSurvivesAMenuRefresh()
  clickAndRun("selftest/long-run", 1)
  sim:click("Refresh menu")
  clickAndRun("selftest/long-run", 1)
  lu.assertEquals(sim:count("selftest/long-run is still running"), 1)
end

function TestRunner:testStopAllEndsEveryRun()
  clickAndRun("selftest/stop-me", 1)
  clickAndRun("selftest/long-run", 1)
  sim:click("Stop all runs")
  lu.assertEquals(sim:count("stopped selftest/stop-me"), 1)
  lu.assertEquals(sim:count("stopped selftest/long-run"), 1)
  sim:click("Stop all runs")
  lu.assertEquals(sim:count("nothing running"), 1)
end

function TestRunner:testWaitingInsideAPcallEndsTheRunCleanly()
  clickAndRun("selftest/pcall-wait", 2)
  lu.assertStrContains(sim:line("done selftest/pcall-wait"), "attempt to yield across")
end

function TestRunner:testWaitingFromTheScriptsOwnCoroutineIsRefused()
  clickAndRun("selftest/nested-coroutine", 2)
  lu.assertStrContains(sim:line("done selftest/nested-coroutine"), "inside a hotload run")
end

function TestRunner:testALibraryIsReadOncePerRunAndAgainNextRun()
  clickAndRun("selftest/load-twice")
  clickAndRun("selftest/load-twice")
  local first = tonumber(sim.logs[#sim.logs - 2]:match("reads = (%d+)"))
  local second = tonumber(sim.logs[#sim.logs]:match("reads = (%d+)"))
  lu.assertEquals(second, first + 1)
  lu.assertStrContains(sim.logs[#sim.logs], "same = true")
end

function TestRunner:testLibraryCyclesAndMissingLibrariesFailTheRun()
  clickAndRun("selftest/load-cycle")
  clickAndRun("selftest/load-missing")
  lu.assertStrContains(sim:line("FAIL selftest/load-cycle"), "load cycle: selftest-cycle-a")
  lu.assertStrContains(sim:line("FAIL selftest/load-missing"), "load no-such-lib")
end

function TestRunner:testRunStartsEachEntryAsItsOwnRunAndWaits()
  clickAndRun("selftest/run-chain", 2)
  lu.assertNotNil(sim:line("start selftest/return-value"))
  lu.assertStrContains(sim:line("done selftest/run-chain"),
    '{broken = "fail", missing = "refused", ok = "done", value = {answer = 42, ok = true}}')
end

function TestRunner:testRunningYourselfIsRefusedNotDeadlocked()
  clickAndRun("selftest/run-self", 2)
  lu.assertStrContains(sim:line("done selftest/run-self"),
    '{error = "selftest/run-self is still running", outcome = "refused"}')
end

function TestRunner:testASecondLoadDoesNothingEvenAfterTheConfigLineRunsAgain()
  Hotload = { root = EXAMPLES }
  dofile(Stub.REPO .. "/dcs-hotload.lua")
  lu.assertEquals(#sim.roots, 1)
  lu.assertEquals(type(Hotload.wait), "function")
end

TestRunnerEdges = {}

function TestRunnerEdges:setUp()
  sim = Stub.new()
end

function TestRunnerEdges:testAStaleMenuEntryIsRefusedNotFatal()
  local root = Stub.tempRoot("stale", { ["user-scripts/gone.lua"] = "return 1",
    ["user-scripts/kept.lua"] = "return 2" })
  sim:load(root)
  os.remove(root .. "/user-scripts/gone.lua")
  clickAndRun("gone")
  lu.assertStrContains(sim:line("refused gone"), "gone.lua")
  clickAndRun("kept")
  lu.assertNotNil(sim:line("done kept"))
end

function TestRunnerEdges:testALongResultIsCutOnScreenButFullInTheLog()
  local root = Stub.tempRoot("long", { ["user-scripts/long.lua"] = 'return string.rep("x", 500)' })
  sim:load(root)
  clickAndRun("long")
  lu.assertTrue(#sim.screen[#sim.screen] < 260)
  lu.assertStrContains(sim:line("done long"), string.rep("x", 500))
end

function TestRunnerEdges:testAnInternalErrorStillEndsTheRun()
  local root = Stub.tempRoot("internal", {
    ["user-scripts/odd.lua"] = "coroutine.yield({ hotload = true }) return 1" })
  sim:load(root)
  clickAndRun("odd")
  lu.assertEquals(sim:count("internal error while running odd"), 1)
  clickAndRun("odd")
  lu.assertEquals(sim:count("odd is still running"), 0)
end

function TestRunnerEdges:testAWeirdErrorObjectStillFailsTheRun()
  local root = Stub.tempRoot("weird", { ["user-scripts/weird.lua"] =
    "error(setmetatable({}, { __tostring = function() return nil end }))" })
  sim:load(root)
  clickAndRun("weird")
  lu.assertNotNil(sim:line("FAIL weird: <table>"))
end

os.exit(lu.LuaUnit.run())
