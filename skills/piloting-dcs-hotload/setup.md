# Setting dcs-hotload up in a mission

`scripts/hotload-setup.py` (in this skill's folder, Python 3) does each step, from the mission
folder: the folder that holds the `.miz` and holds, or will hold, `dcs-hotload/`. Every step
checks first and changes only what is missing, so running it again is harmless.

```bash
python <skill>/scripts/hotload-setup.py status --dcs DCS     # what is missing; exit 0 when all set
```

Exit codes: 0 done or nothing to do, 1 failed or refused, 2 a decision is needed, 3 usage. **On a
2, tell the user what the message says and ask; rerun with the flag it names only once they
agree.**

## 1. Deploy the tool

```bash
python <skill>/scripts/hotload-setup.py deploy
```

Copies the tool into `dcs-hotload/` — the release package's files, nothing else — and creates
`user-lib/`, `user-f10/`, `user-inbox/` and `user-outbox/` (the last two turn the mailbox on).
Never touches the `user-*` folders of an existing copy; over a `user-scripts/` folder, it says to
rename it to `user-f10/`.

A mission already holding an **older** version returns 2: a mission keeps the version it was
tested with. Updating is `deploy --update`, after asking. A **newer** version is left alone.

## 2. Unlock the scripting environment

```bash
python <skill>/scripts/hotload-setup.py unlock --dcs DCS
```

hotload needs `io` and `lfs`, which DCS's `Scripts/MissionScripting.lua` removes from missions.
`DCS` is the DCS World folder, found as `SKILL.md` says. The script returns 2 while they are
locked. **Ask the user first**, with the message's reasons: the edit is install-wide, gives every
mission file access (multiplayer ones included), affects multiplayer integrity checks, and DCS
updates revert it. Then `unlock --dcs DCS --yes` comments out the two lines and keeps the original
as `MissionScripting.lua.bak`. Under `Program Files`, writing may need an administrator; the
message says so.

## 3. Make the `.miz` load it

```bash
python <skill>/scripts/hotload-setup.py patch-miz <mission>.miz
```

Adds a MISSION START trigger that sets `BASE_HOTLOAD_PATH` to `<mission>\dcs-hotload` (an
absolute path), then loads `dcs-hotload.lua` from it, and keeps the original as
`<mission>.miz.bak`. Nothing else in the file changes. Where the folder is missing, the mission
only logs `HOTLOAD: not booted:` in `dcs.log`.

- A boot already loading this mission's copy, from a trigger or from a script the mission
  embeds: nothing to do. A bare `dofile` is reported as such, since it raises a script error
  where the file is missing; it stays until the user removes it, and `patch-miz` then adds the
  trigger.
- A boot loading **another folder's** copy (a mission moved or copied), or whose path is
  cleared, returns 2: say which, and `patch-miz --retarget` rewrites it after asking.

Then **the user re-opens the mission from the Mission menu**: Restart replays the copy loaded at
launch, not the patched file.

## 4. Verify

Needs the mission running. From the mission folder:

```bash
python dcs-hotload/bin/hotload.py log ready              # ready, its version, mailbox on
python dcs-hotload/bin/hotload.py run -e 'return "pong"'  # done, with "pong" as result
```

The quoting is Bash's, which PowerShell also takes; cmd does not take single quotes. On Windows,
`py` stands in for `python` when only the launcher is on the `PATH`.

When DCS is not running, say that this step is still to do.

## Handing the mission to players

The trigger `patch-miz` adds is safe to ship: where its folder is missing, which is every machine
but this one, the mission only logs a line. A bare `dofile` is not: it raises a script error
there.

Before a `.miz` leaves this machine, empty the path, so the shared file carries no local folder:

```bash
python <skill>/scripts/hotload-setup.py boot-path <mission>.miz --clear
python <skill>/scripts/hotload-setup.py boot-path <mission>.miz              # shows it
python <skill>/scripts/hotload-setup.py boot-path <mission>.miz --set dcs-hotload
```

`--set` takes the folder holding `dcs-hotload.lua`, and gives the path back for testing here. A
mission rebuilt by a build tool keeps the trigger as that tool keeps any other; clearing is then
a step after each build that makes a copy to share.
