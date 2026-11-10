---
name: piloting-dcs-hotload
description: Use when setting up dcs-hotload in a DCS mission folder (deploying or updating the tool, checking that the .miz loads it), or when running Lua in a live DCS mission through it (user-inbox / user-outbox, bin/hotload.py).
---

# Piloting DCS through dcs-hotload

## Overview

dcs-hotload runs Lua inside a live mission; you drive it by dropping files. Its `README.md` (in the
mission's `dcs-hotload/` folder) is the protocol reference: the `Hotload.*` calls, the mailbox,
the rules for `user-lib/`. This skill adds what an agent needs on top: a one-call client, what is
live after what, and the limits a script runs under.

This skill covers the tool only. What the Lua does in DCS — spawning, tasking, measuring — is DCS
scripting, not hotload.

## Is this mission set up?

From the mission folder, ask the mission's copy:

```bash
python dcs-hotload/bin/hotload-setup.py status --dcs DCS
```

No `dcs-hotload/bin/hotload-setup.py` there: hotload is not deployed, or its copy is 3.0.1 or
older; follow `setup.md`.

`DCS` is the DCS World folder: find it once and pass it wherever `--dcs` is asked. On Windows, the
installer records it as `Path` under the registry key `HKCU\Software\Eagle Dynamics\DCS World`
(seen with DCS 2.9.30); check that the folder holds `Scripts/MissionScripting.lua`. When it does
not, ask the user.

`status` exits 0 when DCS lets missions use `io` and `lfs` and the `.miz` loads this mission's
copy. Otherwise it names what is missing: follow `setup.md`, which also says how to check a
running mission and how a copy older than the plugin is updated.

## Send a command: one call

`hotload.py` is hotload's mailbox client (Python 3.8+), shipped in the mission's
`dcs-hotload/bin/`. From the mission folder:

```bash
python dcs-hotload/bin/hotload.py run -e 'return timer.getTime()'
python dcs-hotload/bin/hotload.py run --name lane-1 --timeout 1800 my-command.lua
```

Prints the outbox result and cleans the mailbox. Exit 0 done, 1 fail/refused/stopped, 2 timeout,
3 usage, 4 lost, 5 silent. A `fail` carries `error` and `traceback`. Root: `--root`, else
`$HOTLOAD_ROOT`, else the `dcs-hotload/` folder the client is in.

- `--timeout` counts **sim** seconds (default 600), so a pause never times a command out. Past it,
  the client stops the command with `Hotload.stop`: exit 2.
- Exit 4: the mission restarted under the command, which will never finish.
- Exit 5: no heartbeat for `--silence` real seconds (default 60): the mission is paused, not started
  (no slot taken yet), or DCS is down. The files are kept and the command still runs once the
  mission does: read `user-outbox/<name>.lua` later, or send
  `return Hotload.stop("inbox/<name>")`.
- A command that may take more than 2 minutes needs a longer timeout on the Bash call.
- `hotload.py status` — which mission is open, its sim time and the active runs, from the
  heartbeat (the README's *Heartbeat*); exit 0 while it advances, 1 when paused, not started or
  down.
- `hotload.py log [PATTERN]` — HOTLOAD lines since the last `ready`, from
  `Saved Games/DCS/Logs/dcs.log` (`--log FILE` for another). `dcs.log` times are **UTC**.

## Which code is live?

| You changed | It is live after | Verify |
|---|---|---|
| `user-lib/`, `user-f10/`, an inbox command | nothing (re-read every run) | — |
| `dcs-hotload.lua` | mission Restart (the boot line `dofile`s it from disk) | `hotload.py log ready` |
| a file the `.miz` embeds | the `.miz` rebuilt and re-opened | `hotload.py check <name-in-miz> <file-on-disk>` |

`check` compares with DCS's copy of the running mission, `%TEMP%/DCS/tempMission.miz`: a mission
must be running on this machine.

## Limits a command runs under

These come from how hotload runs a script; they hold whatever the script does.

- **What a command returns is its result**: the outbox carries it. Measure inside the command and
  return the numbers.
- **Where the `Hotload.*` calls work, and where the ones that pause cannot go**: the README's
  *Writing a script*.
- **_Stop all runs_ and `Hotload.stop` abandon a command mid-wait without running its cleanup.** A
  command that leaves objects in the world needs a cleanup that does not depend on reaching its
  end.
- **Anything that may arm a timer or register an event handler, directly or through a library,
  goes through `Hotload.callOnMain`**: the README's *Writing a script* says why and how.

## Common mistakes

| Symptom | Cause |
|---|---|
| Outbox stuck on `started` after a mission restart | by design: it never finished; delete the outbox file to rerun it, or both files to drop it |
| A command never runs | its outbox file already exists (delete it), or its name starts with `_` |
| A change to `dcs-hotload.lua` has no effect | the mission was not restarted |
