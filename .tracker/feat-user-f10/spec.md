# One reader per folder

Status: done

Independent of `feat-stop-one-run`; both are meant for `2.0.0`.

## The problem

`user-scripts/` has two readers: the F10 menu, and `Hotload.run(name)`, which runs one of its files
as a child run and waits for it. In practice the mailbox has replaced both. A campaign of about 300
runs (SkynetMunitionTests, October 2026) left `user-scripts/` empty and never called `Hotload.run`.
Every command was a one-liner into a library, such as
`return Hotload.load("t1").run{ system = "Tor M2", munition = "GBU-38", count = 1 }`.

The reason is structural: a file takes no arguments; a library function does. As soon as a step
needs parameters, it becomes a library function, and the entry that runs it becomes a thin call.

What `Hotload.run` alone gives, a step that can fail without ending the command that runs it, is
not what hotload is for. A driver outside the mission gets it by sending setup, run and cleanup as
separate commands, and that is how the campaign ran.

Two rough edges in `IDEAS.md` come from the same place:

- a `user-scripts/inbox/` folder would share labels with inbox commands;
- `Hotload.run` inside a `pcall` starts the child run, then fails to wait for it.

## What to build

### Each folder has one reader

| Folder | Read by | For |
|---|---|---|
| `user-lib/` | `Hotload.load` | the code: modules returning functions |
| `user-f10/` | the F10 menu, only | one button per file, typically a one-liner into `user-lib/` |
| `user-inbox/`, `user-outbox/` | the mailbox | unchanged |

- **`user-scripts/` becomes `user-f10/`.**
- **When the menu is built** (at startup, and on *Refresh menu*), if `user-f10/` cannot be read
  and `user-scripts/` exists, hotload says so (`fail`) instead of `cannot read`:
  `user-scripts/ is now user-f10/ -- rename it`. The menu is still built, from `user-f10/`.
- Nothing enforces what goes where: a long F10 file works. It is just reachable from nowhere else.

### `Hotload.run` is removed

- No replacement. To run an F10 entry from the mailbox, send what the entry contains.
- With it go child runs: every run is now a click or an inbox command.

### Every label says where its run came from

| Run | Label |
|---|---|
| F10 click on `user-f10/folder/10-name.lua` | `f10/folder/10-name` |
| inbox command `user-inbox/name.lua` | `inbox/name` (unchanged) |

- The menu text is unchanged: `menuLabel` still drops `.lua` and the `NN-` prefix.
- An F10 entry and an inbox command can no longer share a label, whatever the folders are called.

## Versioning

`2.0.0`: `Hotload.run` is removed, the folder is renamed, and F10 labels change (log lines). The
mailbox format, its status values and `bin/hotload.sh` do not change.

### Everything that follows

- `dcs-hotload.lua`: the folder, the labels, `Hotload.run` removed, the startup message, the header
  comment, the runner's comment ("one execution of one user-scripts/ file").
- `examples/user-scripts/` becomes `examples/user-f10/`. The deliberately broken self-tests move
  unchanged. `selftest/run-chain` and `selftest/run-self` are deleted: they test `Hotload.run`.
- The plugin: `hotload-setup.py` creates `user-f10/`, and its test; `setup.md`; the skill, including
  "When the command is `return Hotload.run(...)`" and its *Which code is live?* table.
- `README.md`: the folder table and its paragraph, *Writing a script* (the call table, where the
  calls work, the paragraph on `Hotload.run`'s outcomes), the mailbox paragraph that runs a menu
  entry through `Hotload.run`. *Writing a script* says where code goes: in `user-lib/`, with thin
  entries in `user-f10/` and the inbox.
- `CONTRIBUTING.md`: the self-test copy instructions; `Hotload.run` leaves the list of public
  interfaces under *Changelog and versioning*.
- `test/`: every `user-scripts/` path in the suites and in the stub's doc comment; the tests of
  `Hotload.run` deleted.
- `IDEAS.md`: the two rough edges above leave it.
- `CHANGELOG.md`: an entry under `[Unreleased]` that says what to rename, and what to send instead
  of `Hotload.run`.

## Decisions

| Decision | Turned down | Why |
|---|---|---|
| Remove `Hotload.run` | `Hotload.run(name, fn)`, a function child run | a step that may fail without failing its command is the driver's job, done with separate commands; a function child brings labels, a shared library cache and child stops for a need no one has had |
| Rename to `user-f10/` | keep `user-scripts/` | the name says the folder's only reader |
| Prefix F10 labels with `f10/` | reserve an `inbox` folder name in the menu | every label says its source, and no folder name is special |
| Say so when the menu is built and only `user-scripts/` exists | rename it automatically, or say nothing | the mission cannot rename files (`os` is sanitized); silence would give an empty menu with no reason |

## Tests

Offline, against `test/dcs-stub.lua`, each seen failing first:

- the menu is built from `user-f10/`; a click's label is `f10/<path>`; the menu text is unchanged;
- only `user-scripts/` present: the startup message names the rename;
- `user-scripts/` and `user-f10/` both present: no rename message;
- `Hotload.run` is `nil`.

In DCS: the self-tests from `examples/user-f10/`, and the menu they build.

## Out of scope

- `Hotload.stop`: `feat-stop-one-run`.
- Moving an existing mission's `user-scripts/` for the user, in the setup script or in hotload.
- A mailbox client in Python.
