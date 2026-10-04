--[[
A minimal DCS for hotload's tests.

  * a sim clock: timer.getTime and timer.scheduleFunction, advanced by sim:advance(seconds);
  * env and trigger that record what they are given (sim.logs, sim.screen);
  * missionCommands that builds a tree the tests can walk and click (sim:click("a/b"));
  * the real lfs and io, so hotload reads real folders made by Stub.tempRoot.

Usage:
  local Stub = dofile(testDir .. "/dcs-stub.lua")
  local sim = Stub.new()
  sim:load(root)                -- a fresh hotload instance on that root
  sim:click("selftest/wait")
  sim:advance(6)
  lu.assertEquals(sim:count("done selftest/wait"), 1)
]]

require("lfs")

local Stub = {}
Stub.__index = Stub

Stub.TEST_DIR = debug.getinfo(1, "S").source:match("^@(.+)[\\/]") or "."
Stub.REPO = Stub.TEST_DIR .. "/.."

--- A new sim, and the DCS globals hotload uses, pointing at it.
function Stub.new()
  local sim = setmetatable({ now = 0, scheduled = {}, logs = {}, screen = {}, roots = {} }, Stub)
  env = {
    info = function(text) sim.logs[#sim.logs + 1] = text end,
    warning = function(text) sim.logs[#sim.logs + 1] = text end,
    error = function(text) sim.logs[#sim.logs + 1] = text end,
  }
  trigger = { action = { outText = function(text) sim.screen[#sim.screen + 1] = text end } }
  timer = {
    getTime = function() return sim.now end,
    scheduleFunction = function(fn, arg, t)
      sim.scheduled[#sim.scheduled + 1] = { fn = fn, arg = arg, t = t }
    end,
  }
  missionCommands = {
    addSubMenu = function(name, parent)
      local menu = { name = name, kids = {} }
      if parent then
        parent.kids[#parent.kids + 1] = menu
      else
        sim.roots[#sim.roots + 1] = menu
      end
      return menu
    end,
    addCommand = function(name, parent, fn, arg)
      local command = { name = name, fn = fn, arg = arg }
      parent.kids[#parent.kids + 1] = command
      return command
    end,
    removeItem = function(item)
      for i, root in ipairs(sim.roots) do
        if root == item then
          table.remove(sim.roots, i)
          return
        end
      end
    end,
  }
  return sim
end

--- A fresh hotload on `root`, as a new mission would load it. `options` is merged into the
--- Hotload table set before the dofile (e.g. { menu = "Tests" }).
function Stub:load(root, options)
  HotloadCore = nil
  Hotload = { root = root }
  for k, v in pairs(options or {}) do
    Hotload[k] = v
  end
  self.scheduled = {}
  dofile(Stub.REPO .. "/dcs-hotload.lua")
end

--- Runs every scheduled function due within the next `seconds` of sim time, in order.
function Stub:advance(seconds)
  local target = self.now + seconds
  while true do
    table.sort(self.scheduled, function(a, b) return a.t < b.t end)
    local nextCall = self.scheduled[1]
    if not nextCall or nextCall.t > target then
      break
    end
    table.remove(self.scheduled, 1)
    self.now = nextCall.t
    local again = nextCall.fn(nextCall.arg, self.now)
    if again then
      self.scheduled[#self.scheduled + 1] = { fn = nextCall.fn, arg = nextCall.arg, t = again }
    end
  end
  self.now = target
end

--- The current root menu (the last one built).
function Stub:menu()
  return self.roots[#self.roots]
end

--- The menu item at "a/b/c" under the root, looking through "More..." pages as a pilot would.
function Stub:find(path)
  local node = self:menu()
  for name in path:gmatch("[^/]+") do
    local hit, level = nil, node
    while level and not hit do
      local more = nil
      for _, kid in ipairs(level.kids) do
        if kid.name == name then
          hit = kid
        elseif kid.name == "More..." then
          more = kid
        end
      end
      level = more
    end
    assert(hit, "no menu item '" .. name .. "' in '" .. path .. "'")
    node = hit
  end
  return node
end

function Stub:click(path)
  local command = self:find(path)
  command.fn(command.arg)
end

--- How many log lines contain `text` (plain match).
function Stub:count(text)
  local n = 0
  for _, line in ipairs(self.logs) do
    if line:find(text, 1, true) then
      n = n + 1
    end
  end
  return n
end

--- The first log line containing `text`, or nil.
function Stub:line(text)
  for _, line in ipairs(self.logs) do
    if line:find(text, 1, true) then
      return line
    end
  end
  return nil
end

local function rmtree(path)
  local info = lfs.attributes(path)
  if not info then
    return
  end
  if info.mode == "directory" then
    for entry in lfs.dir(path) do
      if entry ~= "." and entry ~= ".." then
        rmtree(path .. "/" .. entry)
      end
    end
    lfs.rmdir(path)
  else
    os.remove(path)
  end
end

local function mkdirs(path)
  path = path:gsub("\\", "/")
  local built = path:match("^/") and "/" or ""   -- keep an absolute Unix path absolute
  for part in path:gmatch("[^/]+") do
    built = (built == "" or built == "/") and built .. part or built .. "/" .. part
    if not lfs.attributes(built) then
      lfs.mkdir(built)
    end
  end
end

--- Writes a file, creating its folders.
function Stub.write(path, text)
  mkdirs(path:match("^(.+)[/\\][^/\\]+$"))
  local handle = assert(io.open(path, "w"))
  handle:write(text)
  handle:close()
end

--- A clean folder under the system temp directory, filled from `files`:
--- { ["user-scripts/a.lua"] = "return 1", ["user-inbox/"] = true }   (true: an empty folder)
function Stub.tempRoot(name, files)
  local base = (os.getenv("TEMP") or os.getenv("TMPDIR") or "/tmp"):gsub("\\", "/")
  local root = base .. "/hotload-test-" .. name
  rmtree(root)
  mkdirs(root)
  for path, content in pairs(files or {}) do
    if content == true then
      mkdirs(root .. "/" .. path)
    else
      Stub.write(root .. "/" .. path, content)
    end
  end
  return root
end

Stub.rmtree = rmtree

return Stub
