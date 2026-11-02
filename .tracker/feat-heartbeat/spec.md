# The mission tells a driver its state

Status: done

Meant for `2.1.0`. Written from the Skynet-IADS in-sim test suite, whose driver core is to move
here as hotload's own client; that move is a later piece of work and needs this first.

## The problem

A driver waiting on a long command needs to know three things about the mission, and the mailbox
tells it none of them:

- **Is it the same mission?** A mission that restarted lost every run in flight. A command whose
  outbox still says `started` is then never going to end, and a driver waiting on it waits
  forever.
- **How much sim time has passed?** A timeout counted in real time fires while DCS is paused. A
  driver that counts in sim time never times a paused run out.
- **Which mission is open?** A driver with commands for one mission should not send them to
  another.

Skynet's driver learns this by sending its own probe command every few seconds, answered by a
library in the mission's `user-lib/` with `{ mission = <sortie>, time = timer.getTime() }`. That costs
a round trip and probe files to clear per look. It ties the driver to a library the mission has to
carry. And it finds a restart only by sim time dropping below the time the command was sent, which
misses a restart the driver did not see if the new mission has already run past that time.

**What none of this tells apart: a paused DCS from a dead one.** Mission timers stop during a
pause, so a paused mission answers nothing, as a dead one does. A driver that needs the
difference checks the DCS process on its own side. The heartbeat does not claim to.

## What to build

### `user-outbox/_heartbeat.lua`

While the mailbox is on, hotload rewrites `user-outbox/_heartbeat.lua` at every mailbox poll (each
second of sim time), and once at startup:

```lua
-- dcs-hotload heartbeat
return {
  ["mission"] = "insim-ca-main",       -- the Mission Editor's sortie name; absent if DCS gives none
  ["runs"] = {                          -- active run label -> its start, in sim time
    ["inbox/iads-builds-run-18f3a"] = 412.3,
  },
  ["time"] = 431.0,                     -- timer.getTime()
  ["version"] = "2.1.0",                -- Hotload.version
}
```

- The format is the outbox's: the same reader parses both.
- **The `_` name can never be a command's.** The inbox ignores names starting with `_`, so no
  command's outbox can ever take that name.
- `runs` lists every active run, F10 ones included. A command that is in neither `runs` nor a final
  outbox is gone: the mission restarted under it.
- The file is rewritten in place (the mission has no `os.rename`), so a reader can catch it
  half-written and reads again.
- What a driver reads from it:

  | It sees | It means |
  |---|---|
  | the file's modification time advancing | the mission is running and not paused |
  | the file still | paused, not started yet (`time = 0` until a slot is taken), or not running: DCS down, or back at the menu |
  | `time` lower than it last read, or another `mission` | the mission restarted, or another one is open |
  | its command absent from `runs`, with no final outbox | the run is gone: the mission restarted |

- A write that fails is logged once, then again once a write has succeeded and another fails. It
  is retried at every poll, and never stops the mailbox.

### Reading the sortie

`env.getValueDictByKey(env.mission.sortie)`, called under `pcall` once at startup: an empty string
or an error leaves `mission` out.

## Decisions

| Decision | Turned down | Why |
|---|---|---|
| A heartbeat file rewritten by hotload | `Hotload.status()` called by a probe command | no round trip, no probe files, nothing the mission has to carry, readable while the mailbox is busy |
| In `user-outbox/`, named `_heartbeat.lua` | at the root, beside `dcs-hotload.lua` | the outbox is the driver's folder and already kept out of version control; the root is the release folder, often committed |
| On the mailbox poll, only while the mailbox is on | its own timer; always | only a driver reads it, and a driver needs the mailbox; the poll already runs every second |
| `runs` with labels and starts | a count of runs | restart detection needs to know whether one particular run is still there |
| Outbox format | JSON; `key=value` lines | one reader for everything hotload writes; drivers already parse it |
| No paused-or-dead claim | a field that pretends to tell them apart | a paused mission runs no timer, so nothing the mission writes can tell |
| `hotload.sh` unchanged | sim-time waits in `hotload.sh run` | the Python client that replaces it is the next piece of work; bash would have to parse Lua tables |

## Versioning

A new file in the outbox, and nothing changed in what was there: a minor version, `2.1.0`.

## Out of scope

- The Python client and the move of Skynet's driver core (the next piece of work, from `IDEAS.md`).
- Moving Skynet off its probe: done there, once a release ships this.
- Telling a paused DCS from a dead one.
