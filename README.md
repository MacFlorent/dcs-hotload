# dcs-hotload

Run Lua scripts inside a live DCS mission, two ways:

- **from the F10 menu**: every click re-reads the script from disk, so editing a file and
  clicking again is the whole edit→run loop;
- **from a file mailbox**: a script saved into `user-inbox/` runs once and its outcome is written
  to `user-outbox/`, so a shell, an editor or an agent can drive the mission without a click.

Scripts can wait in sim time. No external executable.

## Setup

1. **Get it.** Download `dcs-hotload-<version>.zip` from the repository's GitHub releases and
   extract it into the mission folder: it holds a single `dcs-hotload/` folder.
2. **Unlock the mission scripting environment.** From the mission folder, the setup script does
   it (see *Setup script*):

   ```bash
   python dcs-hotload/bin/hotload-setup.py unlock --dcs "<DCS install>" --yes
   ```

   By hand: in `<DCS install>\Scripts\MissionScripting.lua`, comment out `sanitizeModule('io')`
   and `sanitizeModule('lfs')`. The edit is install-wide, affects multiplayer integrity checks, and
   DCS updates revert it; dcs-hotload says so on screen when it is missing.

3. **Load it at mission start**: a MISSION START trigger with two `DO SCRIPT` actions. The setup
   script adds it to the mission's `.miz`; then re-open the mission from the Mission menu, since
   Restart replays the copy loaded at launch:

   ```bash
   python dcs-hotload/bin/hotload-setup.py patch-miz
   ```

   By hand, in the Mission Editor, the first action names the folder:

   ```lua
   BASE_HOTLOAD_PATH = [[D:\path\to\mission\dcs-hotload]]
   ```

   The second loads hotload from it:

   ```lua
   local p, f, err = BASE_HOTLOAD_PATH
   if type(p) ~= "string" or p == "" then err = "BASE_HOTLOAD_PATH is not set"
   else f, err = loadfile(p .. "/dcs-hotload.lua") end
   if not f then env.info("HOTLOAD: not booted: " .. tostring(err)) return end
   Hotload = Hotload or {}; Hotload.root = p; f()
   ```

   Where the folder does not exist, as on a player's machine, the mission only logs a
   `HOTLOAD: not booted:` line in `dcs.log` and shows nothing. A bare
   `dofile([[...\dcs-hotload.lua]])` would raise a script error there instead. In a copy you share,
   emptying the path (`boot-path --clear`, or `BASE_HOTLOAD_PATH = [[]]` by hand) is good
   practice: the file then names no local folder.

4. `dcs-hotload <version> ready` shows on screen (and `HOTLOAD: ready` in `dcs.log`); open
   **F10 → Hotload**.

## Folders

| Folder | Owner | Loaded |
|---|---|---|
| `user-lib/` | the mission | through `Hotload.load`, re-read once per run |
| `user-f10/` | the mission | on click, re-read every time; one file = one F10 command |
| `user-inbox/`, `user-outbox/` | whoever drives the mailbox | optional — see *Mailbox* |

In `user-f10/`, subfolders become submenus; names starting with `_` are skipped; a leading
`NN-` orders entries and is dropped from the menu text (`10-clear-arena.lua` → `clear-arena`). In
dcs.log, its run is labelled by source and path, prefix included: `f10/10-clear-arena`.
After adding, renaming or deleting files, use **Refresh menu**.

F10 shows at most 10 entries per level and does not page, so a level with more shows the first
9 and a **More...** submenu holding the rest.

## Writing a script

A script is a plain Lua file run as a coroutine. What it returns is shown when it finishes: on
screen (cut at 200 characters) and in full in dcs.log.

**Code goes in `user-lib/`; an F10 entry or an inbox command is a thin call into it**, such as
`return Hotload.load("arena").reset()`. A library function takes arguments, a file does not, and
the same call works from F10 and from the mailbox.

```lua
local arena = Hotload.load("arena")         -- user-lib/arena.lua, fresh this run
arena.reset()
Hotload.log("arena reset, waiting for the SAM")
local live = Hotload.waitFor(function() return arena.samIsLive() end, 120)
return { live = live }
```

| Call | Pauses | Does |
|---|---|---|
| `Hotload.wait(s)` | ✓ | waits `s` sim-seconds |
| `Hotload.waitFor(fn, timeout)` | ✓ | waits until `fn()` is truthy → `true`, or `timeout` s → `false` |
| `Hotload.load(name)` | | runs `user-lib/<name>.lua` (once per run) and returns its result |
| `Hotload.callOnMain(fn)` | ✓ | runs `fn` on the mission's main Lua state, returns like `pcall` |
| `Hotload.log(fmt, ...)` | | a `HOTLOAD:` line in dcs.log, stamped with the run's time and label |
| `Hotload.say(text, s)` | | on screen, and logged |
| `Hotload.stop(label)` | | stops the active run `label` (as dcs.log and the outbox name it) → `true`, or `false` if none is running; a run cannot stop itself |

`wait`, `waitFor`, `load` and `callOnMain` work only in the script's own code, not in a
coroutine of your own or a DCS callback. The calls that pause cannot go under a `pcall`, a
`table.sort` comparator or a library's top level either: Lua 5.1 cannot pause across those. Under
a `pcall` the call fails, and the script carries on unless it checks what the `pcall` returned.

The function given to `waitFor` is called every 0.1 s until it returns a truthy value or the
timeout passes: keep it cheap, and don't wait or log in it.

A timer armed from a script is called back on the script's coroutine, and crashes DCS once the
script has ended and its coroutine has been collected, which can be seconds or minutes later.
Anything that may arm a timer or register an event handler, directly or through a library, goes
through `Hotload.callOnMain`. `fn` runs on the next tick; it cannot pause, and of `Hotload.*` only
`log` and `say` work in it, so load modules before the call. A raise in `fn` comes back as
`false, message` and is logged with its traceback.

Different scripts can run at once, taking turns at each pause; the same script cannot run twice
at once. **Stop all runs** ends every running script; `Hotload.stop` ends one. A script that never pauses
(`while true do end`) freezes the sim — nothing can stop it.

### Libraries in `user-lib/`

1. **The top level defines, it does not act.** Define functions and state; don't wait or touch
   the world while the file loads.
2. **State that must survive a reload** goes in a guarded global: `Arena = Arena or {}`. A plain
   `Arena = {}` wipes it on every reload, even under another script that is still waiting.
3. **Use other files at call time**, inside functions. A load-time dependency is a
   `Hotload.load("other")` at the top.
4. **Never reload code that owns live objects.** Something that creates instances for the whole
   mission (an IADS, a recorder) is loaded by the mission, not by `Hotload.load`: reloading it
   replaces its classes underneath the live instances.

## Mailbox

Create `user-inbox/` and `user-outbox/` next to `dcs-hotload.lua` to turn it on (the ready
message then says `mailbox on`). Any `*.lua` saved into `user-inbox/` runs once, like a menu
click, and its outcome is written to `user-outbox/<same name>.lua`:

```lua
-- dcs-hotload result
return {
  ["duration"] = 0.1,
  ["finished"] = 1290.1,
  ["label"] = "inbox/status",
  ["result"] = { ... },
  ["started"] = 1290,
  ["status"] = "done",      -- started | done | fail | stopped | refused
}
```

- A file runs once it has held still for a second (so a half-saved file is never read), if its
  outbox file does not exist yet and it is not already running.
- To run it again, delete its outbox file. Names starting with `_` are ignored.
- The mission cannot delete files (`os` stays sanitized: *Setup* unlocks only `io` and `lfs`), so
  clean both folders yourself.
- After a mission restart, a command whose outbox still says `started` is not run again.

To do what an F10 entry does from the mailbox, send what the entry contains.

### Heartbeat

While the mailbox is on, hotload rewrites `user-outbox/_heartbeat.lua` at startup and every
second of sim time, so a driver can tell what the mission is doing without sending a command:

```lua
-- dcs-hotload heartbeat
return {
  ["mission"] = "my-mission",                 -- the sortie name; absent when the mission has none
  ["runs"] = { ["inbox/lane-1"] = 412.3 },    -- every active run -> its start, in sim time
  ["time"] = 431,                             -- timer.getTime()
  ["version"] = "3.0.0",
}
```

- Its modification time advancing means the mission is running. A file that stays still means
  paused, not started yet (`time = 0` until a slot is taken), or not running: a mission runs no
  timer then, so the heartbeat cannot tell those apart.
- `time` going back, or another `mission`, means the mission restarted or another one is open. A
  command in neither `runs` nor a final outbox is gone: its mission restarted under it.
- It is rewritten in place, so a read can catch it half-written: read it again.

### Mailbox client

`bin/hotload.py` drives the mailbox in one call. It needs Python 3.8 or later, and nothing
else:

```bash
python dcs-hotload/bin/hotload.py run -e 'return timer.getTime()'
python dcs-hotload/bin/hotload.py status     # the heartbeat, and whether it is advancing
python dcs-hotload/bin/hotload.py log        # HOTLOAD lines since the last ready (UTC)
python dcs-hotload/bin/hotload.py check skynet-iads-compiled.lua src/scripts/skynet-iads-compiled.lua
```

`run` writes the command, waits for its result in sim time, prints it and cleans up. It exits:

- 0 done; 1 fail, refused or stopped;
- 2 timeout: past `--timeout` sim seconds, it stopped the command;
- 4 lost: the mission restarted under the command;
- 5 silent: no heartbeat for `--silence` real seconds; the files are kept, and the command still
  runs once the mission does.

`check` tells whether the running mission embeds a file as it is on disk. The root is `--root`,
else `$HOTLOAD_ROOT`, else the `dcs-hotload/` folder the client is in. Every option and default is
at the top of `bin/hotload.py`.

A driver written in Python imports it, with `bin/` on `sys.path`. `Driver.call` sends a command
and waits for it as `run` does. `Driver.run` does the same under a journal, so a series of
commands resumes where it stopped after a crash. Their docstrings are the reference.

## Setup script

`bin/hotload-setup.py` does steps 2 and 3 of *Setup*, checks them, and shows or changes the folder
a mission boots hotload from. It needs Python 3.8 or later, and nothing else. It works on the copy
it is in and on the mission next to it:

```
<mission folder>/
  <mission>.miz        the only .miz; --miz FILE names it when there are several or none
  dcs-hotload/         the copy holding this script
```

```bash
python dcs-hotload/bin/hotload-setup.py status    [--miz FILE] [--dcs DCS]    # what is missing
python dcs-hotload/bin/hotload-setup.py unlock    --dcs DCS [--yes]
python dcs-hotload/bin/hotload-setup.py patch-miz [--miz FILE] [--retarget]
python dcs-hotload/bin/hotload-setup.py boot-path [--miz FILE] [--set DIR | --clear]
```

- `DCS` is the DCS World folder, the one holding `Scripts/MissionScripting.lua`: nothing guesses
  it.
- `status` reports the copy's version, whether the mailbox is on, whether the `.miz` boots this
  copy and, with `--dcs`, whether `io` and `lfs` are unlocked. It exits 0 when the `.miz` boots
  this copy and nothing checked is locked, 2 when something is missing; the mailbox is optional
  and does not count.
- `unlock` changes nothing without `--yes`, and keeps the original as `MissionScripting.lua.bak`.
- `patch-miz` keeps the original as `<mission>.miz.bak`. A boot that points at another folder, or
  whose path is cleared, is rewritten only with `--retarget`.
- `boot-path` shows the folder; `--clear` empties it, a step for a build that makes a copy to
  share; `--set DIR` points it at a folder holding `dcs-hotload.lua`. A build that writes the
  `.miz` elsewhere names it:
  `python dcs-hotload/bin/hotload-setup.py boot-path --miz build/<mission>.miz --clear`.

It exits 0 done or nothing to do, 1 failed or refused, 2 a decision is needed (rerun with the flag
the message names), 3 usage. Apart from `--help`, each line it prints starts with
`hotload-setup:`; what it finds and does goes to stdout, refusals and errors to stderr. Its commands, options, exit codes and that
prefix change incompatibly only with a major version, so a build script can rely on them.

## Claude Code plugin (optional)

The repository is also a Claude Code plugin, which teaches an agent to drive the mailbox with
`bin/hotload.py` and which code is live after what. Hotload does not need it, and it is not part
of the release package: install it in Claude Code from the `dcs-agent-skills` marketplace, which
publishes it with the other DCS plugins, with `/plugin marketplace add MacFlorent/dcs-agent-skills`,
then `/plugin install dcs-hotload@dcs-agent-skills`.
Then ask Claude to set hotload up in a mission folder: it deploys the tool, checks
`MissionScripting.lua` and adds the boot trigger to the `.miz`, asking before each change outside
the mission folder. It needs Python 3.8 or later.

## Development

Changing hotload: `CONTRIBUTING.md`, in the repository — the offline tests
(`lua5.1 test/run.lua`), the in-DCS self-tests in `examples/`, the steps for a change, how work is
tracked, versioning and releasing. What changed: `CHANGELOG.md`, in the repository, and each
release's notes.
