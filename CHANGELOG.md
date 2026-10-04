# Changelog

What each version of dcs-hotload changed. Versions follow [semantic versioning](https://semver.org/)
of `Hotload.version`; `CONTRIBUTING.md` says when an entry is due.

## [Unreleased]

First version, 0.1.0.

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
