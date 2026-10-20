# Changelog

What each version of dcs-hotload changed. Versions follow [semantic versioning](https://semver.org/)
of `Hotload.version`; `CONTRIBUTING.md` says when an entry is due.

## [Unreleased]

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
