# Changelog

What each version of dcs-hotload changed. Versions follow [semantic versioning](https://semver.org/)
of `Hotload.version`; `CONTRIBUTING.md` says when an entry is due.

## [Unreleased]

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
