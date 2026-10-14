# Changelog

What each version of dcs-hotload changed. Versions follow [semantic versioning](https://semver.org/)
of `Hotload.version`; `CONTRIBUTING.md` says when an entry is due.

## [Unreleased]

- **`Hotload.callOnMain(fn)`** runs `fn` on the mission's main Lua state and returns like `pcall`.
  A timer armed from a script is called back on the script's coroutine and crashes DCS once that
  coroutine has been collected; set up timers, event handlers and frameworks such as Skynet inside
  `callOnMain` instead. The skill says so in place of its advice to cancel such a timer.

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
