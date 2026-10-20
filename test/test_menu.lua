--- The F10 menu: discovery, labels, order, and paging under DCS's limit of 10 entries per level
--- (DCS does not page: an 11th or 12th entry is hidden, a 13th breaks the menu).

local dir = debug.getinfo(1, "S").source:match("^@(.+)[\\/]") or "."
local lu = dofile(dir .. "/luaunit.lua")
local Stub = dofile(dir .. "/dcs-stub.lua")

local function names(menu)
  local out = {}
  for _, kid in ipairs(menu.kids) do
    out[#out + 1] = kid.name
  end
  return out
end

local function walk(menu, visit)
  visit(menu)
  for _, kid in ipairs(menu.kids or {}) do
    if kid.kids then
      walk(kid, visit)
    end
  end
end

TestMenu = {}

function TestMenu:testLabelsOrderAndSkippedNames()
  local sim = Stub.new()
  sim:load(Stub.tempRoot("labels", {
    ["user-f10/20-second.lua"] = "return 2",
    ["user-f10/10-first.lua"] = "return 1",
    ["user-f10/_draft.lua"] = "return 0",
    ["user-f10/notes.txt"] = "x",
    ["user-f10/folder/a.lua"] = "return 3",
    ["user-f10/_old/b.lua"] = "return 4",
  }))
  lu.assertEquals(names(sim:menu()), { "folder", "first", "second", "Refresh menu", "Stop all runs" })
  sim:click("first")
  sim:advance(0.5)
  lu.assertNotNil(sim:line("done f10/10-first"))   -- the run label is f10/ and the file path, prefix included
end

function TestMenu:testTheRootMenuNameCanBeSet()
  local sim = Stub.new()
  sim:load(Stub.tempRoot("menuname", { ["user-f10/"] = true }), { menu = "My Tests" })
  lu.assertEquals(sim:menu().name, "My Tests")
end

function TestMenu:testAnF10EntryAndAnInboxCommandOfTheSameNameBothRun()
  local sim = Stub.new()
  local root = Stub.tempRoot("samename", {
    ["user-f10/inbox/x.lua"] = "Hotload.wait(5) return 1",
    ["user-inbox/"] = true, ["user-outbox/"] = true,
  })
  sim:load(root)
  Stub.write(root .. "/user-inbox/x.lua", "Hotload.wait(5) return 2")
  sim:advance(3)                     -- the inbox command is picked up and running
  sim:click("inbox/x")
  sim:advance(0.5)
  lu.assertNotNil(sim:line("start f10/inbox/x"))
  lu.assertNotNil(sim:line("start inbox/x"))
  lu.assertEquals(sim:count("is still running"), 0)
end

function TestMenu:testRefreshPicksUpNewFiles()
  local sim = Stub.new()
  local root = Stub.tempRoot("refresh", { ["user-f10/a.lua"] = "return 1" })
  sim:load(root)
  Stub.write(root .. "/user-f10/b.lua", "return 2")
  lu.assertError(function() sim:find("b") end)
  sim:click("Refresh menu")
  lu.assertEquals(#sim.roots, 1)
  sim:click("b")
  sim:advance(0.5)
  lu.assertNotNil(sim:line("done f10/b"))
end

function TestMenu:testNoLevelEverHoldsMoreThanTenEntries()
  local files, expected = {}, {}
  local function folder(name, count)
    for i = 1, count do
      local file = string.format("f%02d", i)
      files["user-f10/" .. name .. "/" .. file .. ".lua"] = "return 1"
      expected[#expected + 1] = "f10/" .. name .. "/" .. file
    end
  end
  folder("a9", 9)
  folder("b10", 10)
  folder("c11", 11)
  folder("d25", 25)
  for i = 1, 5 do
    folder("e" .. i, 1)                       -- root: 9 folders, plus Refresh and Stop
  end
  local sim = Stub.new()
  sim:load(Stub.tempRoot("paging", files))

  local largest, found = 0, {}
  walk(sim:menu(), function(menu)
    largest = math.max(largest, #menu.kids)
    for _, kid in ipairs(menu.kids) do
      if kid.arg then
        found[#found + 1] = kid.arg.label
      end
    end
  end)
  table.sort(found)
  table.sort(expected)
  lu.assertTrue(largest <= 10, "a level holds " .. largest .. " entries")
  lu.assertEquals(found, expected)

  local root = names(sim:menu())
  lu.assertEquals(root[#root - 1], "Refresh menu")
  lu.assertEquals(root[#root], "Stop all runs")
  lu.assertEquals(names(sim:find("d25"))[10], "More...")
  lu.assertEquals(#names(sim:find("b10")), 10)   -- exactly ten: no More... page
end

os.exit(lu.LuaUnit.run())
