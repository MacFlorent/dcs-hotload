# Setting dcs-hotload up in a mission

`scripts/hotload-setup.py` (in this skill's folder, Python 3) does each step, from the mission
folder: the folder that holds the `.miz` and holds, or will hold, `dcs-hotload/`. Every step
checks first and changes only what is missing, so running it again is harmless.

```bash
python <skill>/scripts/hotload-setup.py status        # what is missing; exit 0 when all set
```

Exit codes: 0 done or nothing to do, 1 failed or refused, 2 a decision is needed, 3 usage. **On a
2, tell the user what the message says and ask; rerun with the flag it names only once they
agree.**

## 1. Deploy the tool

```bash
python <skill>/scripts/hotload-setup.py deploy
```

Copies the tool into `dcs-hotload/` — the release package's files, nothing else — and creates
`user-lib/`, `user-scripts/`, `user-inbox/` and `user-outbox/` (the last two turn the mailbox on).
Never touches the `user-*` folders of an existing copy.

A mission already holding an **older** version returns 2: a mission keeps the version it was
tested with. Updating is `deploy --update`, after asking. A **newer** version is left alone.

## 2. Unlock the scripting environment

```bash
python <skill>/scripts/hotload-setup.py unlock
```

hotload needs `io` and `lfs`, which DCS's `Scripts/MissionScripting.lua` removes from missions.
The script finds the install (`--dcs <install>` or `DCS_INSTALL` when it is not in a usual place)
and returns 2 while they are locked. **Ask the user first**, with the message's reasons: the edit
is install-wide, gives every mission file access (multiplayer ones included), affects multiplayer
integrity checks, and DCS updates revert it. Then `unlock --yes` comments out the two lines and
keeps the original as `MissionScripting.lua.bak`. Under `Program Files`, writing may need an
administrator; the message says so.

## 3. Make the `.miz` load it

```bash
python <skill>/scripts/hotload-setup.py patch-miz <mission>.miz
```

Adds a MISSION START trigger running `dofile([[<mission>\dcs-hotload\dcs-hotload.lua]])`, with an
absolute path, and keeps the original as `<mission>.miz.bak`. Nothing else in the file changes.

- A boot line already loading this mission's copy, from a trigger or from a script the mission
  embeds: nothing to do.
- A boot line loading **another folder's** copy (a mission moved or copied) returns 2: say which,
  and `patch-miz --retarget` rewrites it after asking.

Then **the user re-opens the mission from the Mission menu**: Restart replays the copy loaded at
launch, not the patched file.

## 4. Verify

Needs the mission running. From the mission folder:

```bash
bash dcs-hotload/bin/hotload.sh log ready              # ready, its version, mailbox on
bash dcs-hotload/bin/hotload.sh run -e 'return "pong"'  # done, with "pong" as result
```

These run in Bash: Git Bash on Windows. When the user runs them, tell them to use Git Bash
(*Open Git Bash here* in the mission folder): `bash` is usually not on the `PATH` of PowerShell or
cmd.

When DCS is not running, say that this step is still to do.
