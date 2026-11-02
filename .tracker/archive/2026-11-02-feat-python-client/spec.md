# A Python client that drives hotload

Status: done

Meant for `3.0.0`. Taken from Skynet-IADS's in-sim test engine (`test/insim/engine/`: `mailbox.py`,
`luadata.py`, `driver.py`), written to leave that repository, and moved here as hotload's own
client. It reads the mission's state from the heartbeat (`feat-heartbeat`) in place of Skynet's
probe. Moving Skynet onto it is done there, once 3.0.0 is released.

## The problem

`bin/hotload.sh run` waits in real time: a paused DCS times a command out, and a mission that
restarted under a command is waited on until the timeout. On timeout it leaves the command
running. It parses the outbox with `sed`, so a driver that needs the result as data writes its own
reader. Each campaign of the SkynetMunitionTests kind wrote its own bash driver; Skynet's suite
wrote a Python one. The two clients would drift.

## What to build

### `bin/hotload.py`

One file, standard library only, Python 3.8 or later. It is both:

- **the command line**, replacing `bin/hotload.sh`:
  `python dcs-hotload/bin/hotload.py run|status|log|check ...`;
- **a module** a driver imports, with the folder on `sys.path`: `import hotload`.

`bin/hotload.sh` is removed.

### The library

| Name | Does |
|---|---|
| `parse(text)`, `dump(value)`, `LuaDataError` | read a `return <value>` chunk as hotload writes it (tables become `dict`, or `list` when the keys are exactly 1..n); write one back that Lua 5.1 can `dofile` |
| `Mailbox(root)` | `send(name, code)` atomically (`.tmp`, then a rename); `outcome(name)`, the outbox as a dict or `None` while absent or half-written; `clear(name)`, the inbox then the outbox; `heartbeat()`, the heartbeat as a dict plus its modification time, or `None` |
| `Driver(mailbox, journal=None, say=print)` | `call(name, code, timeout, silence=None, keep=False)` sends one command and waits for its `Outcome`; `run(key, prefix, code, timeout, silence=None)` does the same under a journal |
| `Outcome` | `status`, `result`, `error`, `traceback`, `duration` |

`Outcome.status` is hotload's `done`, `fail`, `stopped` or `refused`, or one of the client's:

| Status | When |
|---|---|
| `timeout` | the command ran past `timeout` sim seconds; the client stopped it with `Hotload.stop` |
| `lost` | the mission restarted under it: its run is gone, and its outbox will never be final |
| `silent` | no heartbeat for `silence` real seconds: paused, not started, or DCS is down. The command is left as it is |

### How the client waits

It reads the heartbeat, then the outbox, every half second. Reading the heartbeat first means a
heartbeat without the run proves the final outbox was already written, if it ever will be.

- **Sim time, never real time, for `timeout`.** It is counted from the outbox's `started`. Before
  pickup, the client counts the heartbeat's `time` as it advances from the send.
- **Lost**: the outbox says `started`, and a heartbeat at or after `started` does not list the run.
  Or the heartbeat's `time` went back, or its `mission` changed, while the command was running.
- **Not picked up before a restart** is not lost: the inbox file is still there, and the new
  mission picks it up.
- **Silence**: no new heartbeat for 10 real seconds is said once ("no heartbeat: paused, not
  started, or DCS is down"). Past `silence`, if set, the wait ends `silent`. `silence=None` waits
  for ever, which suits a journalled driver that resumes.
- **A timed-out command is stopped**: `return Hotload.stop("inbox/<name>")` sent as its own
  command, `stop-<unique>`. The wait ends `timeout` once the outbox reads `stopped`.
- Every command name it makes is `<prefix>-<unique>`. A reused name lets a stale waiter pick up a
  later result.

### The journal

JSON lines, one per event, appended and flushed: `sent` with the name and the sim time it was sent
at, then `ended` with the outcome (`result` kept as Lua data text, since JSON would turn its keys
into strings). `run(key, ...)` with a key already `ended` returns its outcome without sending
anything. With a key `sent` but not ended, it waits on the same name, so a driver that was killed
resumes. A torn last line is skipped. What a driver does with a command that was in flight when
DCS crashed (`lost`) is its call.

### The command line

| Subcommand | Does |
|---|---|
| `run [--root DIR] [--name NAME] [--timeout S] [--silence S] [--keep] (-e LUA \| FILE)` | sends one command, waits, prints the outbox, clears both files unless `--keep` |
| `status [--root DIR]` | prints the heartbeat and whether it is advancing |
| `log [--log FILE] [PATTERN]` | HOTLOAD lines of `dcs.log` since the last `ready` |
| `check [--miz FILE] SCRIPT SRC` | whether the running mission embeds `SRC` as it is on disk |

- **Root**: `--root`, else `$HOTLOAD_ROOT`, else the folder above `bin/`, the `dcs-hotload/` it was
  shipped in.
- `run` defaults: `--timeout 600` sim seconds, `--silence 60` real seconds. The silence cap is
  there so a shell call never hangs on a dead DCS.
- **Exit codes**: 0 done; 1 fail, refused or stopped; 2 timeout; 3 usage or setup; 4 lost;
  5 silent, with the files kept.
- `status` exits 0 when the heartbeat is advancing, 1 when it is still or absent.
- `log` and `check` keep what `hotload.sh` printed. `check` reads the `.miz` with `zipfile`
  (Git Bash has no `zip`, and the client no longer needs Bash).

## Decisions

| Decision | Turned down | Why |
|---|---|---|
| Python, standard library only | keep bash; bash plus a Python helper | one language for the client and the drivers that import it; Lua data parsed properly; no Bash needed on Windows |
| One file, `bin/hotload.py` | a package under `bin/` | copied into a mission as it is; importable with one `sys.path` entry |
| Root defaults to the folder above `bin/` | `./dcs-hotload` | right from any working directory |
| `run` stops a command past its timeout | leave it running, as `hotload.sh` did | a timeout in sim time is a real verdict; a run left behind acts on the world under the next command |
| `lost` at the core | Skynet's `crashed` | the core knows the run is gone, not why; `crashed` is a verdict of a test layer |
| A real-time silence cap on the command line, none by default in the library | none; sim time only | an agent's shell call must end; a journalled driver resumes, so it can wait |
| No `series` subcommand | a journalled list of files on the command line | a campaign's runs are parameterized; a few lines of Python over `Driver.run` say it better than flags |
| Skynet's test layer stays there | moving `suite.py` and `verify` too | one project uses it |
| Skynet's `mission.py` stays there | moving the template-to-working-copy step | it serves the template convention of that suite; the plugin's setup script already writes the boot trigger |

## Versioning

`bin/hotload.sh` is removed, so this is a major version, `3.0.0`, with the heartbeat (2.1.0, not
released on its own). The mailbox format is unchanged.

## Out of scope

- Moving Skynet's suite onto the client.
- Telling a paused DCS from a dead one.
- A version check between the client and the mission's hotload.
