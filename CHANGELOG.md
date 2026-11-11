# Changelog

What each version of dcs-hotload changed. Versions follow [semantic versioning](https://semver.org/)
of `Hotload.version`; `CONTRIBUTING.md` says when an entry is due.

## [Unreleased]

## [3.1.0] — 2026-11-11

- **The setup script ships with hotload**: `bin/hotload-setup.py`, in the release package and in
  every deployed copy, checks a mission (`status`), unlocks `MissionScripting.lua` (`unlock`), adds
  or retargets the boot trigger (`patch-miz`) and shows, sets or clears the boot path
  (`boot-path`), without Claude Code. It works on the copy it is in and on the mission's only
  `.miz` next to that copy; `--miz FILE` names another. `patch-miz` and `boot-path` take `--miz`
  instead of a file argument, `status` and `patch-miz` no longer take `--mission`, `unlock` no
  longer takes `--yes` and `patch-miz` no longer takes `--retarget`: each makes its change, then
  says what it was. `boot-path --set` without a folder points the mission back at this copy, as
  after a `--clear`. Exit 2 now means only that `status` found the mission not set up. A build
  script that looked for the script in the plugin cache now calls the mission's
  `dcs-hotload/bin/hotload-setup.py`. Until now its command line was the skill's own, not a
  public interface; from this version its command line, exit codes and output prefix are one,
  changed incompatibly only with a major version.
- **The setup script reports problems in one line**: a missing or unreadable `.miz`, a folder it
  cannot write in, a file that is not UTF-8 or a missing `boot-guard.lua` end in a
  `hotload-setup:` line and exit 1, not a Python traceback. Refusals and errors go to stderr,
  and a console that cannot show a path no longer stops it. `status` no longer needs `--dcs`, and
  no longer counts a missing mailbox, which is optional.
- **The plugin deploys with its own script**: `deploy` leaves the setup script for the skill's
  `hotload-deploy.py`, which also recreates a copy's missing `user-*` folders. The skill then runs
  the mission's copy of the setup script for the other steps.

## [3.0.1] — 2026-11-09

- **Setup reads a `.miz` built by VEAF Mission Creation Tools**: `status --miz` and `patch-miz`
  failed with `expected '['` on a mission written with bare keys (`coalition = {`), as VEAF MCT
  6.36 writes it. They now read any of the layouts these missions come in, and `patch-miz` writes
  the mission back in the layout it read, so only the added trigger changes.
- **A boot trigger that stays quiet where hotload is not installed**: the setup step in the README
  and `patch-miz` now give a MISSION START trigger that sets `BASE_HOTLOAD_PATH`, then loads
  `dcs-hotload.lua` from it. Where the folder is missing, as on a player's machine, the mission
  logs one `HOTLOAD: not booted:` line and shows nothing; a bare `dofile` raised a script error
  there. A mission booting with a bare `dofile` keeps it: `status` and `patch-miz` say so, and
  removing it before running `patch-miz` gives the new trigger.
- **`boot-path` shows, sets or empties the folder a mission boots hotload from**:
  `hotload-setup.py boot-path FILE --clear` empties it in a copy you share, so the file names no
  local folder; `--set DIR` gives it back. It changes both copies DCS keeps of the trigger text,
  and refuses a mission where it does not find exactly one.

## [3.0.0] — 2026-11-02

- **A heartbeat for drivers**: while the mailbox is on, `user-outbox/_heartbeat.lua` holds the
  sortie name, the sim time, the version and the active runs, rewritten every second. A driver can
  tell a restarted mission from the same one and count its timeouts in sim time, without a probe
  command.
- **Breaking: `bin/hotload.sh` is replaced by `bin/hotload.py`**, which needs Python 3.8 or later:
  `python dcs-hotload/bin/hotload.py run|log|check` as before, from any folder. `run` waits in
  sim time, so a paused mission no longer times a command out, and a command past its timeout
  is stopped rather than left running. New exits: 4 when the mission restarted under the command,
  5 when the heartbeat stays silent for `--silence` seconds. `status` prints the heartbeat. A
  Python driver imports the client for its Lua data reader, waits and journal.

## [2.0.0] — 2026-10-20

- **Breaking: `user-scripts/` is now `user-f10/`**, read only by the F10 menu: rename the folder.
  Hotload says so when it finds only the old one. F10 runs are labelled `f10/<path>` in dcs.log,
  so an entry never shares a label with an inbox command. Setup deploys `user-f10/`, and an update
  over `user-scripts/` says to rename it.
- **Breaking: `Hotload.run` is removed.** Send what the entry contains, or call into `user-lib/`;
  a step that may fail without failing the rest is a separate mailbox command.
- **A library that waits at its top level says so**: `load <name>: a library's top level cannot
  wait ... -- move it into a function`, in place of Lua's "attempt to yield across
  metamethod/C-call boundary".
- **`Hotload.stop(label)`** stops one run by its label, from the mailbox or anywhere: a driver can
  end a command that waits forever without *Stop all runs*. `hotload.sh`'s timeout message says
  how.

## [1.3.0] — 2026-10-15

- **`Hotload.callOnMain(fn)`** runs `fn` on the mission's main Lua state and returns like `pcall`.
  A timer armed from a script is called back on the script's coroutine and crashes DCS once that
  coroutine has been collected; set up timers, event handlers and frameworks such as Skynet inside
  `callOnMain` instead. The skill says so in place of its advice to cancel such a timer.
- **A self-test for `callOnMain`**, `selftest/call-on-main`: a timer armed through it keeps
  beating after the ended run's coroutine has been collected. Run it after a DCS update.
- **The skill says how to drop an interrupted command:** deleting only its outbox file runs it
  again; deleting both its files drops it.

## [1.2.0] — 2026-10-10

- **Setup takes the DCS install as a parameter**: `hotload-setup.py status` and `unlock` require
  `--dcs`, and no longer read `DCS_INSTALL` or guess from usual places. The skill says how to find
  the install once (the installer's registry key) and to ask the user otherwise.

## [1.1.1] — 2026-10-10

- **Documentation**: the README says where the `Hotload.*` calls work and which ones pause, that
  `Hotload.run` takes the file name with its `NN-` prefix, and that the outbox `status` is the
  command's, not the entry's; the `user-lib/` rules move under *Writing a script*. The skill
  points at the README for those limits, and says what `hotload.sh`'s exit code, `log` and `check`
  mean.

## [1.1.0] — 2026-10-09

- **Claude Code plugin**: the repository is a plugin, installed from the repository instead of
  copied into each mission. Its skill documents the tool only: the DCS scripting advice it carried
  is gone. The release package no longer contains `skills/`.
- **Setup from the plugin**: `hotload-setup.py` deploys the tool into a mission folder (an older
  copy only on request, `user-*` folders never touched), unlocks `io` and `lfs` in
  `MissionScripting.lua` once the user agrees, and adds the boot trigger to the `.miz`. Python 3
  only: it reads and writes the mission without Lua.

## [1.0.0] — 2026-10-07

Initial release.

- **F10 menu** built from `user-scripts/`: subfolders as submenus, `_` names skipped, `NN-`
  ordering prefixes, paging past 10 entries per level (DCS does not page), *Refresh menu* and
  *Stop all runs*.
- **Runs** re-read from disk on every click, as coroutines with `Hotload.wait`,
  `Hotload.waitFor`, `Hotload.load`, `Hotload.log` and `Hotload.say`; different scripts run
  concurrently, the same script never twice at once; results shown on screen and logged.
- **Mailbox**: `user-inbox/*.lua` runs once each, its outcome written to
  `user-outbox/<same name>.lua`; opt-in by creating the folders. `Hotload.run(label)` runs a menu
  entry and waits for it.
- **Startup** checks the `MissionScripting.lua` edit, finds its own folder from the chunk name
  DCS reports, and announces itself with its version on screen and in the `HOTLOAD: ready` line.
- **`bin/hotload.sh`**: `run`, `log` and `check` from a shell.
