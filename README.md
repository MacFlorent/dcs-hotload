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
2. **Unlock the mission scripting environment.** In `<DCS install>\Scripts\MissionScripting.lua`,
   comment out `sanitizeModule('io')` and `sanitizeModule('lfs')`. The edit is install-wide, affects
   multiplayer integrity checks, and DCS updates revert it; dcs-hotload says so on screen when it
   is missing.
3. **Load it at mission start**, from a `DO SCRIPT` trigger or a script the mission already
   embeds:

   ```lua
   dofile([[D:\path\to\mission\dcs-hotload\dcs-hotload.lua]])
   ```

4. `dcs-hotload <version> ready` shows on screen (and `HOTLOAD: ready` in `dcs.log`); open
   **F10 → Hotload**.

## Folders

| Folder | Owner | Loaded |
|---|---|---|
| `user-lib/` | the mission | through `Hotload.load`, re-read once per run |
| `user-scripts/` | the mission | on click, re-read every time; one file = one menu command |
| `user-inbox/`, `user-outbox/` | whoever drives the mailbox | optional — see *Mailbox* |

In `user-scripts/`, subfolders become submenus; names starting with `_` are skipped; a leading
`NN-` orders entries and is dropped from the label (`10-clear-arena.lua` → `clear-arena`).
After adding, renaming or deleting files, use **Refresh menu**.

F10 shows at most 10 entries per level and does not page, so a level with more shows the first
9 and a **More...** submenu holding the rest.

## Writing a script

A script is a plain Lua file run as a coroutine. What it returns is shown when it finishes: on
screen (cut at 200 characters) and in full in dcs.log.

```lua
local arena = Hotload.load("arena")         -- user-lib/arena.lua, fresh this run
arena.reset()
Hotload.log("arena reset, waiting for the SAM")
local live = Hotload.waitFor(function() return arena.samIsLive() end, 120)
return { live = live }
```

| Call | Does |
|---|---|
| `Hotload.wait(s)` | waits `s` sim-seconds |
| `Hotload.waitFor(fn, timeout)` | waits until `fn()` is truthy → `true`, or `timeout` s → `false` |
| `Hotload.load(name)` | runs `user-lib/<name>.lua` (once per run) and returns its result |
| `Hotload.run(label)` | runs a `user-scripts/` entry as its own run, waits, returns `{outcome, result, error}` |
| `Hotload.log(fmt, ...)` | a `HOTLOAD:` line in dcs.log, stamped with the run's time and label |
| `Hotload.say(text, s)` | on screen, and logged |

The first four work only inside a run, and not inside a `pcall` or a coroutine of your own
(DCS runs Lua 5.1, which cannot yield across those). A
predicate runs on the tick, not in your script: keep it cheap, don't wait or log in it.

Different scripts run at the same time; the same script cannot run twice at once. **Stop all
runs** ends every running script. A script that never yields (`while true do end`) freezes the
sim — nothing can stop it.

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
- The mission cannot delete files (DCS keeps `os` out of the mission environment), so clean both
  folders yourself.
- After a mission restart, a command whose outbox still says `started` is not run again.

`Hotload.run(label)` runs a `user-scripts/` entry from any script, inbox or menu, and waits for
it:

```lua
return Hotload.run("selftest/wait")   -- { outcome = "done", result = "waited 5 s" }
```

`outcome` is `done`, `fail`, `stopped` or `refused` (no such file, does not compile, or already
running); it never raises.

### Mailbox client

`bin/hotload.sh` drives the mailbox from a shell (Git Bash on Windows) in one call:

```bash
bash bin/hotload.sh run --root <mission>/dcs-hotload -e 'return Hotload.run("selftest/wait")'
bash bin/hotload.sh log                      # HOTLOAD lines since the last start (UTC)
bash bin/hotload.sh check skynet-iads-compiled.lua src/scripts/skynet-iads-compiled.lua
```

`run` writes the command, waits for its result, prints it, cleans up, and exits 0 done,
1 fail/refused/stopped, 2 timeout. `check` tells whether the running mission embeds a file as it
is on disk. Details: the header of the script.

## Rules for user-lib

1. **The top level defines, it does not act.** Define functions and state; don't wait or touch
   the world while the file loads.
2. **State that must survive a reload** goes in a guarded global: `Arena = Arena or {}`. A plain
   `Arena = {}` wipes it on every reload, even under another script that is still waiting.
3. **Use other files at call time**, inside functions. A load-time dependency is a
   `Hotload.load("other")` at the top.
4. **Never reload code that owns live objects.** Something that creates instances for the whole
   mission (an IADS, a recorder) is loaded by the mission, not by `Hotload.load`: reloading it
   replaces its classes underneath the live instances.

## Claude Code plugin (optional)

The repository is also a Claude Code plugin, which teaches an agent to drive the mailbox with
`bin/hotload.sh` and which code is live after what. Hotload does not need it, and it is not part
of the release package: install it in Claude Code from the repository, with
`/plugin marketplace add MacFlorent/dcs-hotload`, then `/plugin install dcs-hotload@dcs-hotload`.
Then ask Claude to set hotload up in a mission folder: it deploys the tool, checks
`MissionScripting.lua` and adds the boot trigger to the `.miz`, asking before each change outside
the mission folder. It needs Python 3.

## Development

Changing hotload: `CONTRIBUTING.md`, in the repository — the offline tests
(`lua5.1 test/run.lua`), the in-DCS self-tests in `examples/`, the steps for a change, how work is
tracked, versioning and releasing. What changed: `CHANGELOG.md`, in the repository, and each
release's notes.
