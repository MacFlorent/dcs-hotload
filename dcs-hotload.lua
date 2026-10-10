--[==[
dcs-hotload -- run Lua scripts inside a live DCS mission from the F10 menu or a file mailbox,
re-read from disk on every run, with sim-time waits. No external executable.

Load once at mission start:
  dofile([[D:\...\dcs-hotload\dcs-hotload.lua]])

Folders next to this file:
  user-lib/       mission-owned, re-read through Hotload.load, once per run
  user-scripts/   mission-owned, re-read on every click; one file = one menu command
  user-inbox/     optional; each *.lua saved here runs once
  user-outbox/    optional; the outcome of each inbox file

Needs the MissionScripting.lua sanitisation edit (io and lfs).
]==]

do

-- A second dofile must not build a second menu or arm a second tick. The started instance is
-- kept in HotloadCore, outside the Hotload table: a `Hotload = { root = ... }` line (the
-- fallback the startup error suggests) re-run before a second dofile replaces Hotload, and must neither
-- start a second instance nor strip the API from scripts that are still running.
if HotloadCore then
  Hotload = HotloadCore
  return
end

Hotload = Hotload or {}
Hotload.version = "1.1.1"   -- semantic versioning; CHANGELOG.md says what each version changed

local TAG = "HOTLOAD"
local TICK = 0.1
local SCREEN_SECONDS = 10
local SCREEN_RESULT_CHARS = 200   -- a run's result on screen is cut here; dcs.log has all of it

-- ── Output ──────────────────────────────────────────────────────────────────────────────────

local current = nil   -- the run being resumed right now; set by the runner, read by log and waits

local function logLine(text)
  env.info(TAG .. ": " .. text)
end

local function screen(text, seconds)
  trigger.action.outText(text, seconds or SCREEN_SECONDS)
end

--- A setup problem: on screen long enough to read, and logged.
local function fail(message)
  screen("dcs-hotload: " .. message, 60)
  logLine(message)
end

--- tostring that always gives a string. Script values reach the runner's own formatting (error
--- objects, returned values), and a __tostring that raises or returns a non-string would otherwise
--- break the runner instead of the script.
local function textOf(value)
  local ok, text = pcall(tostring, value)
  if ok and type(text) == "string" then
    return text
  end
  return "<" .. type(value) .. ">"
end

local function truncate(text, limit)
  if #text <= limit then
    return text
  end
  return text:sub(1, limit) .. "..."
end

local function describeKey(key)
  if type(key) == "string" and key:match("^[%a_][%w_]*$") then
    return key
  end
  return "[" .. textOf(key) .. "]"
end

--- One-line rendering of a run's return value: strings quoted, tables with sorted keys, nested
--- to a depth of 4. Sorted so the same value always reads the same in the log.
local function describe(value, depth)
  depth = depth or 0
  local kind = type(value)
  if kind == "string" then
    return string.format("%q", value)
  end
  if kind ~= "table" then
    return textOf(value)
  end
  if depth >= 4 then
    return "{...}"
  end
  local keys = {}
  for key in pairs(value) do
    keys[#keys + 1] = key
  end
  table.sort(keys, function(a, b)
    if type(a) == type(b) and (type(a) == "number" or type(a) == "string") then
      return a < b
    end
    return type(a) < type(b)
  end)
  local parts = {}
  for _, key in ipairs(keys) do
    parts[#parts + 1] = describeKey(key) .. " = " .. describe(value[key], depth + 1)
  end
  return "{" .. table.concat(parts, ", ") .. "}"
end

local function placeholder(value)
  return string.format("%q", "<" .. type(value) .. ">")
end

--- Exact Lua text for a scalar. Numbers use the shortest form that reads back to the same double;
--- 0/0 and math.huge are written as expressions, since %g gives text Lua cannot read back.
local function serializeScalar(value)
  local kind = type(value)
  if kind == "string" then
    return string.format("%q", value)
  end
  if kind == "number" then
    if value ~= value then
      return "0/0"
    end
    if value == math.huge then
      return "math.huge"
    end
    if value == -math.huge then
      return "-math.huge"
    end
    local short = string.format("%.14g", value)
    if tonumber(short) == value then
      return short
    end
    return string.format("%.17g", value)
  end
  if kind == "boolean" or kind == "nil" then
    return tostring(value)
  end
  return placeholder(value)
end

--- Exact Lua text for a result file, readable back with dofile: sorted keys (numbers, then
--- strings, then the rest), one entry per line. Values Lua cannot write back become placeholder
--- strings and a table reached again while writing itself becomes "<cycle>", so writing a result
--- never fails.
local function serialize(value, indent, writing)
  if type(value) ~= "table" then
    return serializeScalar(value)
  end
  writing = writing or {}
  if writing[value] then
    return string.format("%q", "<cycle>")
  end
  writing[value] = true
  indent = indent or ""
  local inner = indent .. "  "
  local numbers, strings, others = {}, {}, {}
  for key in pairs(value) do
    local kind = type(key)
    if kind == "number" then
      numbers[#numbers + 1] = key
    elseif kind == "string" then
      strings[#strings + 1] = key
    else
      others[#others + 1] = key
    end
  end
  table.sort(numbers)
  table.sort(strings)
  local parts = {}
  local function add(key)
    parts[#parts + 1] = string.format("%s[%s] = %s", inner, serializeScalar(key),
      serialize(value[key], inner, writing))
  end
  for _, key in ipairs(numbers) do add(key) end
  for _, key in ipairs(strings) do add(key) end
  for _, key in ipairs(others) do add(key) end
  writing[value] = nil
  if #parts == 0 then
    return "{}"
  end
  return "{\n" .. table.concat(parts, ",\n") .. ",\n" .. indent .. "}"
end

Hotload._serialize = serialize   -- internal; exposed for offline checks only

--- One line to dcs.log. Formats only when extra arguments are given, so a lone message
--- containing a percent sign is safe. Inside a run the line carries the seconds since the run
--- started and the run's label.
function Hotload.log(message, ...)
  local text = textOf(message)
  if select("#", ...) > 0 then
    text = string.format(text, ...)
  end
  if current then
    text = string.format("t=%6.1f [%s] %s", timer.getTime() - current.startedAt, current.label, text)
  end
  logLine(text)
end

--- On screen, and logged.
function Hotload.say(text, seconds)
  text = tostring(text)
  screen(text, seconds)
  Hotload.log("%s", text)
end

-- ── Files ───────────────────────────────────────────────────────────────────────────────────

--- Sorted file and folder names in `dir`. A folder that cannot be read lists as empty, with the
--- error returned third. LuaFileSystem builds disagree on a missing path: some raise when the
--- iterator is created, some on its first step, and 1.4.2 on Windows yields nothing and raises
--- nothing. So existence is checked first, and the walk itself is protected.
local function listDir(dir)
  local files, dirs = {}, {}
  local info = lfs.attributes(dir)
  if not info or info.mode ~= "directory" then
    return files, dirs, "no such folder"
  end
  local ok, err = pcall(function()
    for entry in lfs.dir(dir) do
      if entry ~= "." and entry ~= ".." then
        local attributes = lfs.attributes(dir .. "/" .. entry)
        if attributes and attributes.mode == "directory" then
          dirs[#dirs + 1] = entry
        elseif attributes and attributes.mode == "file" then
          files[#files + 1] = entry
        end
      end
    end
  end)
  table.sort(files)
  table.sort(dirs)
  return files, dirs, (not ok) and tostring(err) or nil
end

--- A menu label: the name without .lua, and without a leading "NN-" ordering prefix.
local function menuLabel(name)
  local label = name:gsub("%.lua$", "")
  label = label:gsub("^%d+%-", "")
  return label
end

-- ── Runner ──────────────────────────────────────────────────────────────────────────────────

--[[
One run = one execution of one user-scripts/ file, as a coroutine resumed on a shared tick.
coroutine.resume IS the protected call for script code: a raise ends the run, never the tick.
Lua 5.1 cannot yield across pcall, so nothing between the tick and a script's yield may be a
pcall.
]]

local runs = {}          -- run label -> run; the duplicate-run guard
local tickArmed = false

local function finishRun(run, outcome, detail, traceback)
  runs[run.label] = nil
  run.outcome = outcome
  run.finishedAt = timer.getTime()
  if outcome == "done" then
    run.result = detail
  elseif outcome == "fail" then
    run.error = textOf(detail)
    run.traceback = traceback
  end
  local line
  if outcome == "done" then
    line = string.format("done %s (%.1fs)", run.label, timer.getTime() - run.startedAt)
    if detail ~= nil then
      -- On screen too: a script clicked from F10 (a status, a refusal) is read in the cockpit.
      local result = describe(detail)
      screen(line .. " -> " .. truncate(result, SCREEN_RESULT_CHARS), SCREEN_SECONDS)
      logLine(line .. " -> " .. result)
    else
      screen(line, SCREEN_SECONDS)
      logLine(line)
    end
  elseif outcome == "fail" then
    line = string.format("FAIL %s: %s", run.label, textOf(detail))
    screen(line, SCREEN_SECONDS)
    logLine(traceback and (line .. "\n" .. traceback) or line)
  else
    line = "stopped " .. run.label
    screen(line, SCREEN_SECONDS)
    logLine(line)
  end
  if run.onFinish then
    -- Writing an outbox file, for instance. Its failure must not touch the tick.
    local ok, err = pcall(run.onFinish, run)
    if not ok then
      logLine("after " .. run.label .. ": " .. tostring(err))
    end
  end
end

--- Evaluates a waitFor predicate in its own coroutine: it is arbitrary script code and it can
--- raise (querying a destroyed unit raises), and that must end this run, not the tick.
--- Returns satisfied, failureMessage.
local function probe(run, predicate)
  local co = coroutine.create(predicate)
  current = run
  local ok, value = coroutine.resume(co)
  current = nil
  if not ok then
    return false, "waitFor predicate raised: " .. textOf(value)
  end
  if coroutine.status(co) ~= "dead" then
    return false, "waitFor predicate yielded; a predicate must not wait"
  end
  return value and true or false, nil
end

--- Advances one run by at most one resume.
local function step(run, now)
  local resumeValue = nil
  local pending = run.pending

  if pending then
    if pending.kind == "waitFor" then
      local satisfied, failure = probe(run, pending.predicate)
      if failure then
        return finishRun(run, "fail", failure)
      end
      if satisfied then
        resumeValue = true
      elseif now >= pending.deadline then
        resumeValue = false
      else
        return
      end
    else
      if now < pending.deadline then
        return
      end
      resumeValue = true
    end
    run.pending = nil
  end

  current = run
  local ok, result = coroutine.resume(run.co, resumeValue)
  current = nil

  if not ok then
    return finishRun(run, "fail", result, debug.traceback(run.co, textOf(result)))
  end

  if coroutine.status(run.co) == "dead" then
    return finishRun(run, "done", result)
  end

  -- Still alive, so it yielded. Only Hotload.wait / Hotload.waitFor may yield a run.
  if type(result) ~= "table" or result.hotload ~= true then
    return finishRun(run, "fail", "the script yielded something that is not a Hotload wait")
  end
  result.deadline = now + result.timeout
  run.pending = result
end

local function tick(_, now)
  -- Snapshot: finishRun removes entries while we walk.
  local active = {}
  for _, run in pairs(runs) do
    active[#active + 1] = run
  end
  for _, run in ipairs(active) do
    if runs[run.label] == run then
      local ok, err = pcall(step, run, now)
      if not ok then
        -- A bug in the runner itself. End the run as a failure rather than leave it wedged:
        -- a Hotload.run caller waits on its outcome, and an inbox command on its outbox file.
        runs[run.label] = nil
        current = nil
        run.outcome = "fail"
        run.finishedAt = now
        run.error = "internal error: " .. textOf(err)
        logLine("internal error while running " .. run.label .. ": " .. textOf(err))
        if run.onFinish then
          pcall(run.onFinish, run)
        end
      end
    end
  end
  if next(runs) == nil then
    tickArmed = false
    return nil
  end
  return now + TICK
end

local function ensureTick()
  if tickArmed then
    return
  end
  tickArmed = true
  timer.scheduleFunction(tick, nil, timer.getTime() + TICK)
end

--- Starts one run from a file, re-read from disk. Returns the run, or nil and the reason it was
--- refused (already running, or the file does not compile). `onFinish(run)` is called once the
--- run has ended, whatever the outcome.
local function startRun(path, label, onFinish)
  if runs[label] then
    local reason = label .. " is still running"
    Hotload.say(reason)
    return nil, reason
  end
  local chunk, err = loadfile(path)
  if not chunk then
    local line = "refused " .. label .. ": " .. tostring(err)
    screen(line, SCREEN_SECONDS)
    logLine(line)
    return nil, tostring(err)
  end
  local run = {
    path = path,
    label = label,
    co = coroutine.create(chunk),
    startedAt = timer.getTime(),
    loaded = {},
    pending = nil,
    onFinish = onFinish,
  }
  runs[label] = run
  logLine("start " .. label)
  screen("start " .. label, 5)
  ensureTick()
  return run
end

--- The run whose own coroutine is executing, or a raise. Waiting from anywhere else -- the
--- mission's top level, a library's top level, a predicate, a coroutine the script made itself --
--- would yield into the wrong resumer.
local function currentRun(fname)
  if not current or coroutine.running() ~= current.co then
    error(fname .. " can only be called inside a hotload run", 3)
  end
  return current
end

--- Yields for `seconds` sim-seconds.
function Hotload.wait(seconds)
  assert(type(seconds) == "number" and seconds > 0,
    "Hotload.wait: seconds must be a positive number")
  currentRun("Hotload.wait")
  coroutine.yield({ hotload = true, kind = "wait", timeout = seconds })
end

--- Yields until predicate() is truthy (true) or `timeout` sim-seconds pass (false). Never
--- raises on timeout: the script decides what a timeout means. The predicate runs on the
--- tick, never inside the script's coroutine.
function Hotload.waitFor(predicate, timeout)
  assert(type(predicate) == "function", "Hotload.waitFor: predicate must be a function")
  assert(type(timeout) == "number" and timeout > 0,
    "Hotload.waitFor: timeout must be a positive number of seconds")
  currentRun("Hotload.waitFor")
  return coroutine.yield({ hotload = true, kind = "waitFor", predicate = predicate,
    timeout = timeout }) == true
end

--- Runs a user-scripts/ entry as its own run (own label, guard, log lines) and waits for it to
--- end. A missing, broken or already-running entry is not an error here: it comes back as
--- outcome "refused", and the caller decides what that means.
function Hotload.run(label)
  assert(type(label) == "string" and label ~= "", "Hotload.run: label must be a non-empty string")
  currentRun("Hotload.run")
  local child, reason = startRun(Hotload.root .. "/user-scripts/" .. label .. ".lua", label)
  if not child then
    return { outcome = "refused", error = reason }
  end
  Hotload.waitFor(function()
    return child.outcome ~= nil
  end, math.huge)
  return { outcome = child.outcome, result = child.result, error = child.error }
end

--- Abandons every active run. Menu callbacks never run during the tick, so no run is
--- mid-resume here.
local function stopAll()
  local active = {}
  for _, run in pairs(runs) do
    active[#active + 1] = run
  end
  if #active == 0 then
    Hotload.say("nothing running")
    return
  end
  for _, run in ipairs(active) do
    finishRun(run, "stopped")
  end
end

-- ── Libraries ───────────────────────────────────────────────────────────────────────────────

local LOADING = {}   -- marker: this name is being loaded in this run (cycle detection)

--- Reads user-lib/<name>.lua once per run and returns what it returns. The next run reads it
--- again, so edits show up on the next click. A library's top level must not wait: it runs
--- inside a pcall, and Lua 5.1 cannot yield across one.
function Hotload.load(name)
  assert(type(name) == "string" and name ~= "", "Hotload.load: name must be a non-empty string")
  local run = currentRun("Hotload.load")
  local cached = run.loaded[name]
  if cached == LOADING then
    error("load cycle: " .. name, 2)
  end
  if cached then
    return cached.value
  end

  local chunk, err = loadfile(Hotload.root .. "/user-lib/" .. name .. ".lua")
  if not chunk then
    error("load " .. name .. ": " .. tostring(err), 2)
  end

  run.loaded[name] = LOADING
  local ok, value = pcall(chunk)
  if not ok then
    run.loaded[name] = nil
    error("load " .. name .. ": " .. textOf(value), 2)
  end
  run.loaded[name] = { value = value }
  return value
end

-- ── Mailbox ─────────────────────────────────────────────────────────────────────────────────

--[[
user-inbox/*.lua runs once each; user-outbox/<same name>.lua is the token saying it was taken, and
then holds its outcome. The mission cannot rename or delete files (os stays sanitised), so
"taken" is the outbox file's existence. A command starts only once its size and modification
time held still across two polls, so a file still being saved is never read half-written,
whoever writes it.
]]

local POLL = 1.0
local inboxDir, outboxDir
local lastSeen = {}   -- inbox name -> "size:modification" at the previous poll
local blocked = {}    -- inbox names whose token could not be written; never retried

local function isFile(path)
  local info = lfs.attributes(path)
  return info ~= nil and info.mode == "file"
end

--- Writes one outbox record in a single write call.
local function writeOutbox(name, record)
  local path = outboxDir .. "/" .. name
  local handle, err = io.open(path, "w")
  if not handle then
    logLine("cannot write " .. path .. ": " .. tostring(err))
    return false
  end
  handle:write("-- dcs-hotload result\nreturn " .. serialize(record) .. "\n")
  handle:close()
  return true
end

local function outcomeRecord(run)
  return {
    label = run.label,
    status = run.outcome,
    started = run.startedAt,
    finished = run.finishedAt,
    duration = run.finishedAt - run.startedAt,
    result = run.result,
    error = run.error,
    traceback = run.traceback,
  }
end

local function pickUp(name, label)
  local startedAt = timer.getTime()
  -- The token first: without it, a command could run again on the next poll.
  if not writeOutbox(name, { label = label, status = "started", started = startedAt }) then
    blocked[name] = true
    return
  end
  local run, reason = startRun(inboxDir .. "/" .. name, label, function(finished)
    writeOutbox(name, outcomeRecord(finished))
  end)
  if not run then
    local now = timer.getTime()
    writeOutbox(name, { label = label, status = "refused", started = startedAt, finished = now,
      duration = now - startedAt, error = reason })
  end
end

local function poll(_, now)
  local ok, err = pcall(function()
    local present = {}
    for _, name in ipairs((listDir(inboxDir))) do
      if name:match("%.lua$") and name:sub(1, 1) ~= "_" then
        present[name] = true
        local info = lfs.attributes(inboxDir .. "/" .. name)
        -- An empty file is not a command yet: editors create the file before the first save.
        local stamp = info and info.size > 0 and (tostring(info.size) .. ":" .. tostring(info.modification))
        local label = "inbox/" .. (name:gsub("%.lua$", ""))
        if stamp and lastSeen[name] == stamp and not blocked[name] and not runs[label]
            and not isFile(outboxDir .. "/" .. name) then
          pickUp(name, label)
        end
        lastSeen[name] = stamp
      end
    end
    for name in pairs(lastSeen) do
      if not present[name] then
        lastSeen[name] = nil
      end
    end
  end)
  if not ok then
    logLine("mailbox poll error: " .. tostring(err))
  end
  return now + POLL
end

--- Arms the poller when user-inbox/ exists. Returns whether the mailbox is on.
local function startMailbox()
  inboxDir = Hotload.root .. "/user-inbox"
  outboxDir = Hotload.root .. "/user-outbox"
  local _, _, noInbox = listDir(inboxDir)
  if noInbox then
    return false   -- opt-in: no inbox folder, no mailbox, nothing to say
  end
  local _, _, noOutbox = listDir(outboxDir)
  if noOutbox then
    fail("user-inbox/ exists but " .. outboxDir .. " does not -- create it to turn the mailbox on")
    return false
  end
  timer.scheduleFunction(poll, nil, timer.getTime() + POLL)
  return true
end

-- ── Menu ────────────────────────────────────────────────────────────────────────────────────

local menuRoot = nil

local function onClick(entry)
  startRun(entry.path, entry.label)
end

--- DCS's radio panel has 12 rows and does not page: item n goes to row n, rows 11 and 12 are
--- then overwritten by "Previous Menu" and "Exit", and an item at row 13 or beyond fails an
--- assert that aborts the whole menu. So no level may hold more than 10 entries.
local MENU_ROWS = 10

--- Adds `entries` (functions that each add one item to a parent) using at most `rows` rows.
--- Past that, the last row becomes "More..." holding the rest, paged the same way.
local function addPaged(parent, entries, rows)
  if #entries <= rows then
    for _, add in ipairs(entries) do
      add(parent)
    end
    return
  end
  local rest = {}
  for i, add in ipairs(entries) do
    if i < rows then
      add(parent)
    else
      rest[#rest + 1] = add
    end
  end
  addPaged(missionCommands.addSubMenu("More...", parent), rest, MENU_ROWS)
end

--- One menu level: folders first as submenus, then one command per *.lua file, paged to fit
--- `rows`. Nothing is executed here; a file only ever runs when clicked.
local function buildLevel(dir, relative, parent, rows)
  local files, dirs = listDir(dir)
  local entries = {}
  for _, name in ipairs(dirs) do
    if name:sub(1, 1) ~= "_" then
      entries[#entries + 1] = function(menu)
        local sub = missionCommands.addSubMenu(menuLabel(name), menu)
        buildLevel(dir .. "/" .. name, relative .. name .. "/", sub, MENU_ROWS)
      end
    end
  end
  for _, name in ipairs(files) do
    if name:sub(1, 1) ~= "_" and name:match("%.lua$") then
      local label = relative .. (name:gsub("%.lua$", ""))
      entries[#entries + 1] = function(menu)
        missionCommands.addCommand(menuLabel(name), menu, onClick,
          { path = dir .. "/" .. name, label = label })
      end
    end
  end
  addPaged(parent, entries, rows)
end

local function buildMenu()
  if menuRoot then
    missionCommands.removeItem(menuRoot)
  end
  menuRoot = missionCommands.addSubMenu(Hotload.menu or "Hotload")
  local scriptsDir = Hotload.root .. "/user-scripts"
  -- A wrong root would otherwise give a menu holding only Refresh and Stop, and no reason.
  local _, _, err = listDir(scriptsDir)
  if err then
    fail("cannot read " .. scriptsDir .. " -- " .. err)
  end
  -- Two rows of the root page are kept for Refresh and Stop, so they never move into "More...".
  buildLevel(scriptsDir, "", menuRoot, MENU_ROWS - 2)
  missionCommands.addCommand("Refresh menu", menuRoot, function()
    buildMenu()
    Hotload.say("menu refreshed")
  end)
  missionCommands.addCommand("Stop all runs", menuRoot, stopAll)
end

-- ── Startup ─────────────────────────────────────────────────────────────────────────────────

local function sanitisationCheck()
  local missing = {}
  if not io then missing[#missing + 1] = "io" end
  if not lfs then missing[#missing + 1] = "lfs" end
  if #missing > 0 then
    fail("re-apply the edit in <DCS install>\\Scripts\\MissionScripting.lua -- missing: "
      .. table.concat(missing, ", ") .. ". A DCS update reverts it.")
    return false
  end
  return true
end

local function stripTrailingSlash(path)
  return (path:gsub("[\\/]+$", ""))
end

--- The folder of a chunk name, when it names a .lua file that exists. Stock Lua names a file
--- chunk "@<path>"; DCS's dofile may drop the "@", so both forms are accepted.
local function folderOfChunk(name)
  if type(name) ~= "string" then
    return nil
  end
  local path = name:gsub("^@", "")
  local dir = path:match("^(.+)[\\/][^\\/]+%.lua$")
  local info = dir and lfs.attributes(path)
  if info and info.mode == "file" then
    return dir
  end
  return nil
end

--- The explicit Hotload.root wins. Otherwise the folder this file was dofile'd from, read from
--- the chunk name debug.getinfo reports. Returns root, or nil and what was seen.
local function discoverRoot()
  if type(Hotload.root) == "string" and Hotload.root ~= "" then
    return stripTrailingSlash(Hotload.root)
  end
  if not (debug and debug.getinfo) then
    return nil, "the debug library is not available"
  end
  local info = debug.getinfo(1, "S")
  local root = folderOfChunk(info.source) or folderOfChunk(info.short_src)
  if root then
    return root
  end
  return nil, string.format("debug.getinfo reported source=%s short_src=%s",
    describe(truncate(tostring(info.source), 120)), describe(truncate(tostring(info.short_src), 120)))
end

local function start()
  if not sanitisationCheck() then
    return
  end

  local root, seen = discoverRoot()
  if not root then
    fail("cannot tell where dcs-hotload.lua is: " .. seen
      .. ". Set Hotload = { root = [[<folder>]] } before the dofile.")
    return
  end
  Hotload.root = root

  buildMenu()
  local mailbox = startMailbox()

  HotloadCore = Hotload
  local mailboxState = mailbox and "on" or "off"
  logLine(string.format("ready, version %s, root %s, mailbox %s", Hotload.version, root, mailboxState))
  screen(string.format("dcs-hotload %s ready, mailbox %s", Hotload.version, mailboxState))
end

start()

end
