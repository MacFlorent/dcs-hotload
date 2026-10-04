--- The serializer behind outbox files: what it writes must read back with dofile, exactly.

local dir = debug.getinfo(1, "S").source:match("^@(.+)[\\/]") or "."
local lu = dofile(dir .. "/luaunit.lua")
local Stub = dofile(dir .. "/dcs-stub.lua")

local sim = Stub.new()
sim:load(Stub.tempRoot("serializer", { ["user-scripts/"] = true }))
local serialize = assert(Hotload._serialize, "Hotload._serialize is the serializer's test hook")

local function roundTrip(value)
  return assert(loadstring("return " .. serialize(value)))()
end

TestSerializer = {}

function TestSerializer:testStringsRoundTripExactly()
  local text = "a \"quoted\"\nline\0with nul\r\n"
  lu.assertEquals(roundTrip(text), text)
end

function TestSerializer:testNumbersUseTheShortestExactForm()
  lu.assertStrContains(serialize({ n = 41.3 }), "41.3,")
  lu.assertEquals(roundTrip(1 / 3), 1 / 3)
  lu.assertEquals(roundTrip(2 ^ 53 + 1), 2 ^ 53 + 1)
end

function TestSerializer:testNanAndInfinitiesReadBack()
  local back = roundTrip({ nan = 0 / 0, inf = math.huge, ninf = -math.huge })
  lu.assertTrue(back.nan ~= back.nan)
  lu.assertEquals(back.inf, math.huge)
  lu.assertEquals(back.ninf, -math.huge)
end

function TestSerializer:testArraysKeepTheirOrder()
  lu.assertEquals(roundTrip({ 3, 1, 2 }), { 3, 1, 2 })
end

function TestSerializer:testValuesLuaCannotWriteBecomePlaceholders()
  local back = roundTrip({ fn = print, co = coroutine.create(function() end) })
  lu.assertEquals(back.fn, "<function>")
  lu.assertEquals(back.co, "<thread>")
end

function TestSerializer:testATableReachedAgainWhileWritingItselfIsACycle()
  local cyclic = { name = "loop" }
  cyclic.self = cyclic
  local back = roundTrip(cyclic)
  lu.assertEquals(back.name, "loop")
  lu.assertEquals(back.self, "<cycle>")
end

function TestSerializer:testASharedTableIsWrittenInFullEachTime()
  local shared = { 1, 2 }
  local back = roundTrip({ a = shared, b = shared })
  lu.assertEquals(back.a, { 1, 2 })
  lu.assertEquals(back.b, { 1, 2 })
end

function TestSerializer:testOddKeysAreKeptOrReplaced()
  local back = roundTrip({ [true] = "bool key", [print] = "function key" })
  lu.assertEquals(back[true], "bool key")
  lu.assertEquals(back["<function>"], "function key")
end

function TestSerializer:testTheSameValueAlwaysGivesTheSameText()
  local value = { b = 2, a = 1, [3] = "x", [1] = "y" }
  lu.assertEquals(serialize(value), serialize(value))
end

os.exit(lu.LuaUnit.run())
