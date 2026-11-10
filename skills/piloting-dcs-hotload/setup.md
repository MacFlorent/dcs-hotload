# Setting dcs-hotload up in a mission

Two scripts, both Python 3.8+, run from the mission folder: the folder that holds the `.miz` and
holds, or will hold, `dcs-hotload/`.

- `scripts/hotload-deploy.py`, in this skill's folder, copies the tool into the mission.
- `dcs-hotload/bin/hotload-setup.py`, the mission's copy of the setup script, does the rest. Its
  commands are in the README's *Setup script* (`dcs-hotload/README.md`). **Run the mission's copy,
  never the one in the plugin's own folder**: `patch-miz` points the mission at the copy it runs
  from.

Every step checks first and changes only what is missing, so running it again is harmless. Exit
codes: 0 done or nothing to do, 1 failed or refused, 2 a decision is needed, 3 usage. **On a 2,
tell the user what the message says and ask; rerun with the flag it names only once they agree.**

## 1. Deploy the tool

```bash
python <this skill's folder>/scripts/hotload-deploy.py
```

Copies the tool into `dcs-hotload/` — the release package's files, nothing else — and creates any
missing `user-lib/`, `user-f10/`, `user-inbox/` and `user-outbox/` (the last two turn the mailbox
on), even over a copy that is already current. Never touches what the `user-*` folders hold; over
a `user-scripts/` folder, it says to rename it to `user-f10/`.

A mission already holding an **older** version returns 2: a mission keeps the version it was
tested with. Updating is `--update`, after asking. A **newer** version is left alone.

Then, to see what is still missing:

```bash
python dcs-hotload/bin/hotload-setup.py status --dcs DCS
```

`DCS` is the DCS World folder, found as `SKILL.md` says.

## 2. Unlock the scripting environment

```bash
python dcs-hotload/bin/hotload-setup.py unlock --dcs DCS
```

hotload needs `io` and `lfs`, which DCS's `Scripts/MissionScripting.lua` removes from missions.
The script returns 2 while they are locked. **Ask the user first**, with the message's reasons:
the edit is install-wide, gives every mission file access (multiplayer ones included), affects
multiplayer integrity checks, and DCS updates revert it. Then `--yes` makes the edit. Under
`Program Files`, writing may need an administrator; the message says so.

## 3. Make the `.miz` load it

```bash
python dcs-hotload/bin/hotload-setup.py patch-miz
```

Adds the boot trigger, pointing at the mission's `dcs-hotload/`. Nothing else in the file changes.
Where the folder is missing, the mission only logs `HOTLOAD: not booted:` in `dcs.log`. With
several `.miz` in the folder, ask which one, and pass `--miz FILE`.

- A boot already loading this mission's copy, from a trigger or from a script the mission
  embeds: nothing to do. A bare `dofile` is reported as such, since it raises a script error
  where the file is missing; it stays until the user removes it, and `patch-miz` then adds the
  trigger.
- A boot loading **another folder's** copy (a mission moved or copied), or whose path is
  cleared, returns 2: say which, and `--retarget` rewrites it after asking.

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

## Sharing the mission

The trigger `patch-miz` adds is safe to share: where its folder is missing, which is every machine
but this one, the mission only logs a line. A bare `dofile` is not: it raises a script error
there.

Emptying the path in a copy you share is still good practice: the file then names no folder of
this machine, and the mission does not look for hotload anywhere, even where that folder happens
to exist. `boot-path --clear` empties it, `boot-path` shows it, `boot-path --set dcs-hotload`
gives it back for testing here. A mission rebuilt by a build tool keeps the trigger as that tool
keeps any other; clearing then fits as a step after each build that makes a copy to share.
