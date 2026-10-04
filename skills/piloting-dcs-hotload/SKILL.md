---
name: piloting-dcs-hotload
description: Use when driving a running DCS World mission through dcs-hotload (user-inbox / user-outbox, Hotload.run), when writing Lua that spawns, tasks or measures units in a live mission, or when a change to a DCS mission does not seem to take effect after a restart.
---

# Piloting DCS through dcs-hotload

## Overview

dcs-hotload runs Lua inside a live mission; you drive it by dropping files. Its `README.md` (in the
`dcs-hotload/` folder) is the protocol reference. This skill adds a one-call helper and the DCS
behaviours that silently break live-mission Lua.

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
| `dcs-hotload.lua` | mission Restart (the boot line `dofile`s from disk) | `hotload.sh log ready` |
| anything embedded in the `.miz` (custom scripts, Skynet, mission config) | rebuild, then **re-open the `.miz` from the Mission menu** | `hotload.sh check <name-in-miz> <file-on-disk>` |

DCS Restart replays `%TEMP%\DCS\tempMission.miz`, the copy made at launch, so a rebuilt `.miz`
needs a fresh open. (Missions built with VEAF's veaf-tools also embed every leftover `.lua` in
`src/scripts/`.)

## Writing Lua for a live mission

**Before spawning, tasking or measuring units, read [dcs-scripting-facts.md](dcs-scripting-facts.md)**:
links to the Hoggit wiki API pages, plus measured behaviour the wiki does not cover. The traps that
cost runs:

- An AI task on the **first waypoint of an air-started group is ignored**: put the attack task on
  waypoint 2, or `pushTask` it after the spawn delay.
- Wait (`Hotload.wait(1)`) before giving a freshly spawned group's controller any task, command or
  option; the wiki warns that doing it at once can crash the game.
- Measure inside the command and **return the numbers**: the outbox carries them.
- Remove event handlers and spawned groups on **every exit path**, timeouts included. *Stop all
  runs* abandons a command mid-wait without running its cleanup, so a command that spawns units
  also arms a `timer.scheduleFunction` safety net that cleans up after its longest wait.
- No `Hotload.wait` inside `pcall` (stock Lua 5.1 cannot yield across it).
- Payload CLSIDs, weapon flags and unit type names recalled from memory may be wrong and fail
  silently (a jet spawns unarmed). Look flags up on the wiki, query `list_payloads` /
  `list_unit_types` when the veaf-mission-editor MCP server is connected, and return the spawned
  unit's `getAmmo()` in the result.

## Common mistakes

| Symptom | Cause |
|---|---|
| SAM never goes live again | out of ammunition; Skynet keeps it dark (an ammo truck fixes it) |
| Outbox stuck on `started` after a mission restart | by design: it never finished; delete it to rerun |
