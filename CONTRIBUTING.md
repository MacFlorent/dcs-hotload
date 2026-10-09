# Contributing

dcs-hotload is one Lua file that runs other Lua inside a live DCS World mission, plus a small
shell client. This file holds every rule for changing it; `CLAUDE.md` only points here.

## What you need

- **Lua 5.1 with LuaFileSystem**, to run the tests. On Windows, *Lua for Windows* has both, at
  `C:\Program Files (x86)\Lua\5.1\lua.exe`. On Linux, `lua5.1` and
  `luarocks --lua-version=5.1 install luafilesystem`.
- **A Bash shell** (Git Bash on Windows), for `bin/hotload.sh` and the commands below, and `curl`,
  with which `.github/scripts/lint.sh` fetches luacheck.
- **DCS World** with the `MissionScripting.lua` edit described in `README.md`, for checks only the
  simulator can answer.

## Layout

| Path | What it is |
|---|---|
| `dcs-hotload.lua` | the tool: everything a mission loads |
| `bin/hotload.sh` | the mailbox client |
| `examples/` | self-test scripts, run in DCS and by the tests |
| `.claude-plugin/`, `skills/` | the Claude Code plugin: its manifest and its skill — see *Writing guidance*; not in the release package |
| `test/` | the offline suite: plain Lua 5.1 against a stub DCS |
| `.tracker/` | work in progress and work done, and `IDEAS.md` — see *Tracking work* |
| `.drafts/` | local working space, git-ignored |
| `.github/scripts/package.sh` | builds the release package into `dist/` — see *Releasing* |
| `.github/scripts/lint.sh` | runs luacheck at a pinned version, downloaded into `.tools/` (git-ignored) |
| `dist/` | the release package, git-ignored |
| `CHANGELOG.md` | what each version changed |

## Commands

```
lua5.1 test/run.lua            # every suite; a name filters: lua5.1 test/run.lua mailbox
bash .github/scripts/lint.sh   # luacheck at its pinned version, as CI runs it
```

On Windows without `lua5.1` on `PATH`: `"/c/Program Files (x86)/Lua/5.1/lua.exe" test/run.lua`.

## Test first

Write the failing test, then make it pass. **Do not open a pull request with tests failing.**

There are two levels, and which one a check belongs to is decided by whether the stub can answer
it:

| | Where it runs | What belongs in it |
|---|---|---|
| `test/` | plain Lua 5.1 and CI, against `test/dcs-stub.lua` | the runner, waits, the guard, the mailbox, the menu, the serializer, startup. **New tests go here** |
| `examples/` self-tests | inside DCS, copied into a mission | what a stub cannot show: how DCS renders the menu, real sim timing, how DCS names a loaded chunk |

To run the self-tests, copy `examples/user-scripts/selftest/` into a mission's `user-scripts/`
and `examples/user-lib/*` into its `user-lib/`, then click each entry: every script states its
expected log line at the top. Run them after a DCS update, or after a change the stub cannot judge.

A suite is `test/test_<area>.lua`. It loads `luaunit.lua` and `dcs-stub.lua`, builds a sim with
`Stub.new()`, loads hotload on a folder (`sim:load(root)`, with `Stub.tempRoot` for a throwaway
one or `examples/`), drives it with `sim:click(path)` and `sim:advance(seconds)`, reads
`sim.logs` and `sim.screen`, and ends with `os.exit(lu.LuaUnit.run())`. `test/dcs-stub.lua`
documents the rest.

A test that passes before its change has proved nothing: break the code on purpose once and watch
the test fail.

## How a change is made

These steps are mandatory, whatever tools you work with.

1. **Check what is already known** before proposing a change to how something behaves: search
   `.tracker/`, its archive and `IDEAS.md` included.
2. **Open the work**, if it needs a spec — see *Tracking work*: commit
   `.tracker/<type>-<slug>/spec.md` straight to `main` with `Status: in-progress`, then branch from
   that commit. The idea the work takes up, if any, leaves `IDEAS.md` in the same commit.
3. **Branch** from an up-to-date `main`, named as *Git flow* says.
4. **Test first** — see *Test first*.
5. **Run the tests and the lint script.** When only DCS can show that the change works, say so.
6. **Add a `CHANGELOG.md` entry** for any change to `dcs-hotload.lua` or `bin/hotload.sh` — what a
   user installs.
7. **Commit** as *Git flow* says.
8. **Open a pull request to `main`.** Its description says what changed and why, and how it was
   verified — including "not flown" when it was not tried in DCS. Amendments to the spec ride with
   the pull request, down to `Status: done`, set by the last pull request of the work.
9. **Merging is a maintainer's call.**
10. **Archive** the work's folder, at your discretion, once its last pull request has merged or it
    has been dropped.

## Tracking work

`.tracker/` records work in progress and work done. It is not a backlog: what might be done some
day is an entry in `.tracker/IDEAS.md`, or a GitHub issue when it comes from outside.

```
.tracker/
  IDEAS.md                           prospective work
  <type>-<slug>/                     one piece of work, named like its branch <type>/<slug>
    spec.md                          the only required file
  archive/
    YYYY-MM-DD-<type>-<slug>/        merged or dropped
```

**A spec is worth writing** when there is something to decide before coding, or when the work
spans several pull requests; otherwise a branch and a pull request are enough. A suggested shape:
the problem, what to build, the decisions with the alternatives turned down, what is out of scope,
discussion under `## Comments`. A spec is kept true while the work is under way and is not edited
once its pull request has merged.

What is strict is what a search relies on:

- **The location**: a folder directly under `.tracker/`, with `spec.md` at its root.
- **The `Status:` line**, the first line after the title:

  | Status | Meaning |
  |---|---|
  | `open` | written, not started |
  | `in-progress` | taken on; carried by the branch `<type>/<slug>` |
  | `blocked` | waiting — the line says on what, and who is expected to act |
  | `paused` | deliberately set aside — the line says what would restart it |
  | `done` | complete; set in the pull request itself |
  | `dropped` | decided against — the line or the spec says why |

  What is under way is found by search: `grep -l "Status: in-progress" .tracker/*/spec.md`.
- **The archive**: a folder moves as it is to `archive/YYYY-MM-DD-<type>-<slug>/`, dated the day its
  last pull request merged or the work was dropped. The state is never part of a file name.
- **`IDEAS.md`** is a free list. An idea taken up leaves it in the commit that opens its spec; a
  dropped idea stays, with its reason.

## Git flow

- `main` is the only long-lived branch and the target of every pull request.
- Branch from `main` as `<type>/<slug>`: `<type>` is one of `feat`, `fix`, `docs`, `chore`,
  `refactor`, `test`; `<slug>` is lowercase kebab.
- Never commit directly to `main`, with one exception: a change confined to `.tracker/` (opening a
  piece of work, a status change, an idea, archiving). Anything else goes through a pull request,
  guidance files included.
- [Conventional Commits](https://www.conventionalcommits.org/), in English. A commit does one thing.
- Pull requests are merged with a merge commit, so their commits stay readable apart.

## Changelog and versioning

Every pull request that changes `dcs-hotload.lua` or `bin/hotload.sh` appends an entry at the end of
the `[Unreleased]` section of `CHANGELOG.md`. Missions carry a copy of hotload, so the changelog is
how whoever updates one knows whether it is worth it.

[Semantic versioning](https://semver.org/) of `Hotload.version`, in `dcs-hotload.lua`, which the
`HOTLOAD: ready` log line prints. The mailbox is a public interface other tools depend on — the
`user-inbox/` and `user-outbox/` folders, the outbox file format and its status values,
`Hotload.run` — so changing it incompatibly is a major version.

## Releasing

A release is a GitHub release holding `dcs-hotload-<x.y.z>.zip`: a single `dcs-hotload/` folder
with `dcs-hotload.lua`, `README.md`, `LICENSE.md`, `bin/` and `examples/` — what a
mission needs, extracted into its folder. `.github/scripts/package.sh` builds it from an allowlist,
so a new file reaches missions only once it is named there. `LICENSE.md` ships because the license
requires a copy in every redistribution.

1. Optionally, check the package first: run the *Release* workflow by hand from the Actions tab and
   download the zip it attaches, or run `bash .github/scripts/package.sh` and look in
   `dist/dcs-hotload/` (Git Bash has no `zip`, so locally only the folder is built).
2. On a `release/<x.y.z>` branch, set `Hotload.version` and rename `[Unreleased]` in
   `CHANGELOG.md` to `[x.y.z] — YYYY-MM-DD`, with a fresh `[Unreleased]` above it. Pull request to
   `main`.
3. Tag `v<x.y.z>` on `main` once merged, and push the tag. The *Release* workflow runs the tests,
   checks that the tag matches `Hotload.version`, is on `main` and has its `CHANGELOG.md` section,
   then publishes the release with that section as its notes. A tag is never moved; a wrong
   release is fixed by the next.

## Writing guidance

The guidance files are `README.md`, this file and `CLAUDE.md`. The skill in `skills/` follows the
same rules, and one more: **it documents the tool, and nothing else.** No DCS scripting advice —
how to spawn, task or measure belongs to whatever DCS knowledge the agent has — and no findings of
a project that uses hotload. Anything true because of hotload, such as a limit a script runs
under, belongs in it.

- **A rule is stated once**, here, with its reason; other files point at it. A command may be
  repeated.
- **A rule states its own reason.** It never cites a piece of work, a commit, a person or a date;
  that history is in `.tracker/` and the pull requests.
- **A pointer names a file**, never a heading.
- **`CLAUDE.md` is read in every agent session**, so each of its lines must prevent a mistake.
- Everything written in the repository is in English.
