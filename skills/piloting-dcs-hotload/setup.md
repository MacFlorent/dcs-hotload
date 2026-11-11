# Setting dcs-hotload up in a mission

Run everything from the mission folder: the folder that holds the `.miz` and holds, or will hold,
`dcs-hotload/`. Deploy with this skill's script; every later step uses the mission's copy of the
setup script, `dcs-hotload/bin/hotload-setup.py`. What it does, command by command, is in the
mission's `dcs-hotload/README.md`, under *Setup* and *Setup script*. **Run the mission's copy,
never the one in the plugin's own folder**: `patch-miz` points the mission at the copy it runs
from.

Each step checks first and changes only what is missing. Three changes are the user's to decide:
updating an older copy, unlocking DCS, and repointing a mission that boots another folder. **Say
what the change does and ask; run it only once they agree.**

## 1. Deploy the tool

```bash
python <this skill's folder>/scripts/hotload-deploy.py
```

Copies the release package's files into `dcs-hotload/`, and creates any missing `user-lib/`,
`user-f10/`, `user-inbox/` and `user-outbox/`, even over a current copy. It never touches what the
`user-*` folders hold; over a `user-scripts/` folder, it says to rename it to `user-f10/`.

Over an **older** copy it exits 2: a mission keeps the version it was tested with, so ask before
`--update`. A **newer** copy is left alone. A copy without `bin/hotload-setup.py` (3.0.1 and
older) cannot do the steps below: the mission then needs `--update`, or the README's manual steps.

Then see what is missing, with `DCS` found as `SKILL.md` says:

```bash
python dcs-hotload/bin/hotload-setup.py status --dcs DCS
```

## 2. Unlock the scripting environment

```bash
python dcs-hotload/bin/hotload-setup.py unlock --dcs DCS
```

Only when `status` reports `io` or `lfs` locked, and only after asking, with the reasons the
README's *Setup* step 2 gives. Under `Program Files`, writing may need an administrator; the
message says so.

## 3. Make the `.miz` load it

```bash
python dcs-hotload/bin/hotload-setup.py patch-miz
```

- With several `.miz` in the folder, ask which one, and pass `--miz FILE`.
- When `status` reports a boot of **another folder** (a mission moved or copied, or pointed at a
  shared copy on purpose) or a cleared path, ask first: `patch-miz` points it at this copy.
- A bare `dofile` is reported as such; it stays until the user removes it.

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

The trigger is safe to share; clearing its path in a copy that leaves this machine is good
practice. Both are in the README's *Setup* step 3; the command is `boot-path --clear`, and a build
that makes a copy to share runs it after each build.
