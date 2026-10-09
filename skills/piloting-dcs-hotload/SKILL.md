---
name: piloting-dcs-hotload
description: Use when setting up dcs-hotload in a DCS mission folder (deploying or updating the tool, checking that the .miz loads it), or when running Lua in a live DCS mission through it (user-inbox / user-outbox, Hotload.run, bin/hotload.sh).
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

From the mission folder, hotload is ready when:

- `dcs-hotload/dcs-hotload.lua` exists, with `user-inbox/` and `user-outbox/` beside it (the
  mailbox is on);
- the `.miz` loads it at mission start (`dofile` of that file, from a trigger or an embedded
  script);
- with the mission running, `bash dcs-hotload/bin/hotload.sh log ready` shows `ready` and
  `mailbox on`.

When one is missing, follow the setup in `dcs-hotload/README.md`.

## Send a command: one call

`hotload.sh` is hotload's mailbox client, shipped in the mission's `dcs-hotload/bin/`. From the
mission folder:

```bash
bash dcs-hotload/bin/hotload.sh run -e 'return Hotload.run("selftest/wait")'
bash dcs-hotload/bin/hotload.sh run --name lane-1 --timeout 1800 my-command.lua
```

Prints the outbox result and cleans the mailbox. Exit 0 done, 1 fail/refused/stopped, 2 timeout,
3 usage. Root: `--root`, else `$HOTLOAD_ROOT`, else `./dcs-hotload` (right when run from the
mission folder).

- A command that may outlast ~9 minutes goes in a background Bash call (`run_in_background`) with a
  matching `--timeout`: foreground calls stop at 10 minutes.
- On timeout the command stays in the inbox and still runs; its result lands in
  `user-outbox/<name>.lua` later. Read it or delete both files yourself.
- `hotload.sh log [PATTERN]` — HOTLOAD lines since the last `ready`. `dcs.log` times are **UTC**.
- The mission must be running and unpaused: sim time drives every wait.

## Which code is live?

| You changed | It is live after | Verify |
|---|---|---|
| `user-lib/`, `user-scripts/`, an inbox command | nothing (re-read every run) | — |
| `dcs-hotload.lua` | mission Restart (the boot line `dofile`s it from disk) | `hotload.sh log ready` |
| a file the `.miz` embeds | the `.miz` rebuilt and re-opened | `hotload.sh check <name-in-miz> <file-on-disk>` |

## Limits a command runs under

These come from how hotload runs a script; they hold whatever the script does.

- **What a command returns is its result**: the outbox carries it. Measure inside the command and
  return the numbers.
- **`Hotload.wait`, `waitFor`, `load` and `run` work only inside a run.** The ones that wait —
  `wait`, `waitFor`, `run` — never inside a `pcall` or a coroutine of your own: a run is a
  coroutine, and DCS's Lua 5.1 cannot yield across those.
- **_Stop all runs_ abandons a command mid-wait without running its cleanup.** A command that leaves
  objects in the world needs a cleanup that does not depend on reaching its end.
- **A `timer.scheduleFunction` armed inside a run and firing after the run ended has crashed DCS**
  (twice, DCS 2.9.30, an access violation in `lua.dll`; intermittent, cause unproven). Keep its id
  and `timer.removeFunction` it on the normal exit path.
- **The same script cannot run twice at once**; a second start is `refused`.

## Common mistakes

| Symptom | Cause |
|---|---|
| Outbox stuck on `started` after a mission restart | by design: it never finished; delete it to rerun |
| A command never runs | its outbox file already exists (delete it), or its name starts with `_` |
| A change to `dcs-hotload.lua` has no effect | the mission was not restarted |
