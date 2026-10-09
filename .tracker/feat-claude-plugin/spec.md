# dcs-hotload as a Claude Code plugin

Status: in-progress

The general DCS knowledge that the current skill mixes in moves to the `dcs-missions` plugin of
`MacFlorent/dcs-agent-skills`, which also lists this plugin in its marketplace once released.

## Goal

The repository ships the tool **and** the Claude Code plugin that teaches an agent to use it, in
one versioned unit. Installing the plugin gives an agent everything it needs to:

1. deploy dcs-hotload into a mission folder and keep it up to date,
2. make sure DCS and the `.miz` are configured to load it,
3. drive a running mission through the mailbox.

**The plugin is an addition, not a replacement.** dcs-hotload stays a standalone tool: the
release pipeline keeps publishing `dcs-hotload-<version>.zip` on GitHub releases, and the
README's manual setup (extract into the mission folder, unlock `MissionScripting.lua`, add the
`dofile` line) stays complete and supported. Someone without Claude Code, or driving the mailbox
from their own scripts, needs nothing from the plugin. The zip and the plugin come from the same
tagged commit and carry the same version.

## Principles

- **The skill documents the tool, nothing else.** It does not teach DCS scripting, mission
  building, or how a user's scripts should be written. Scripts may come from the user; the agent
  combines this skill with whatever DCS knowledge it has (for example the `dcs-missions` plugin
  from `dcs-agent-skills`, which this plugin never mentions).
- **Tool constraints are tool knowledge.** Anything true *because of hotload* stays: runs are
  coroutines, `Hotload.wait` cannot cross `pcall`, *Stop all runs* skips cleanup, results travel
  through the outbox.
- **One source of truth per fact.** The README stays the protocol reference; the skill links to it
  instead of restating it, and adds only what an agent needs on top (one-call client, setup
  procedure, what is live after what).
- **DCS never loads files from the plugin cache.** Claude Code installs plugins under
  `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`; that path changes on every update
  and old versions are removed. The plugin is the *source*; the mission's `dcs-hotload/` folder is
  the deployed copy.

## Repository layout (target)

```
.claude-plugin/
  plugin.json            name "dcs-hotload", version = the tool's version
  marketplace.json       single-plugin marketplace, so the tool installs on its own
skills/
  piloting-dcs-hotload/
    SKILL.md             driving a running mission (reworked, see below)
    setup.md             deploy / configure / update procedure (new)
    scripts/             setup helpers (new, see "Setup tooling")
bin/hotload.sh           unchanged
dcs-hotload.lua          unchanged
examples/ ...            unchanged
README.md                Setup section gains "with Claude Code"; skills/README.md removed
```

`skills/` already sits at the repository root, which is where a plugin expects it, so the
repository root is the plugin root.

- `plugin.json` `version` must equal the tool version (the one `dcs-hotload <version> ready`
  prints). Add the check to the release steps in `CONTRIBUTING.md`, or derive one from the other.
- `marketplace.json` lists one plugin, pinned to the current release tag (see Releases). The
  `dcs-agent-skills` marketplace also lists this plugin, pinned the same way; both are fine at once.
- **The release zip must not contain `skills/` or `.claude-plugin/`.** A deployed mission folder
  holds only the tool. Today `skills/` is copied into every mission, which is how skill copies
  drift.

## Releases

How Claude Code delivers plugins (from the Claude Code plugin docs, `plugins/host-marketplace`
and `plugins/marketplace-reference`):

- A marketplace entry's source decides what is fetched. A `github` source without `ref` takes
  the default branch; with `ref` (branch or tag) or `sha`, that exact point. A relative source
  (`"./"`) takes whatever commit of the marketplace repository the user cloned, i.e. the default
  branch unless they added the marketplace as `owner/repo#ref`.
- Users get a new copy **only when the plugin's computed version changes**: `plugin.json`
  `version` first, then the entry's `version`, and when both are omitted the commit SHA. A
  pushed change with an unchanged `version` never reaches anyone who already installed.
- Background auto-update is off for third-party marketplaces until each user turns it on in
  `/plugin`. Otherwise users update with `/plugin marketplace update <name>` or
  `claude plugin update <plugin>@<marketplace>`.

So a relative `"./"` source would serve the default branch's head, development commits included,
under the last released version string. Instead, **the plugin follows releases, not the
default branch**:

- `plugin.json` `version` is set to the release version, and only in the release commit.
- The release commit also sets the entry in this repository's `marketplace.json` to
  `{ "source": "github", "repo": "MacFlorent/dcs-hotload", "ref": "v<version>" }`, the tag that
  commit receives. A fresh install and an update both get exactly the released tree.
- The same tag builds the zip. One version, one commit, two packagings.
- After the release, bump the `ref` in the `dcs-agent-skills` marketplace too (see its spec).
- Add these steps to the release checklist in `CONTRIBUTING.md`, and make `claude plugin
  validate .` part of it.

During development, load the working tree instead: `claude --plugin-dir <repo>` or a local
marketplace added from the checkout's path, which reads files in place without a version bump.

Note: claude.ai organization sync (Team/Enterprise) refuses plugins with a top-level `bin/`
directory. It does not affect `/plugin marketplace add`; it matters only if the plugin is ever
distributed that way, in which case `hotload.sh` moves out of `bin/` in the plugin layout.

## Skill: `piloting-dcs-hotload`

One skill, with the setup procedure in `setup.md` loaded on demand. The description must trigger
on both setting up and driving, and nothing broader:

> Use when setting up dcs-hotload in a DCS mission folder (deploying or updating the tool,
> checking that the .miz loads it), or when running Lua in a live DCS mission through it
> (user-inbox / user-outbox, Hotload.run, bin/hotload.sh).

Remove the current triggers on "writing Lua that spawns, tasks or measures units" and "a change to
a DCS mission does not seem to take effect after a restart": those are DCS knowledge.

### SKILL.md keeps / gains

- Overview: what hotload is, README as the protocol reference.
- **Is this mission set up?** One quick check (`dcs-hotload/` present, its `Hotload.version` matches the
  plugin, `.miz` boot line present) and a pointer to `setup.md` when any fails.
- **Send a command** with `bin/hotload.sh` (current section, unchanged).
- **Which code is live** after what, limited to hotload's own files: `user-lib/`,
  `user-scripts/` and inbox commands are re-read every run; `dcs-hotload.lua` needs a mission
  Restart; `hotload.sh check` verifies an embedded file matches the disk.
- **Tool constraints for run scripts** (facts about hotload, not style advice):
  - `Hotload.wait` / `waitFor` / `load` / `run` only inside a run, never inside `pcall` or another
    coroutine (Lua 5.1 cannot yield across them).
  - The result of a command is what it returns; the outbox carries it.
  - *Stop all runs* abandons a command mid-wait without running its cleanup, so a script that
    leaves objects in the world needs a cleanup that does not depend on reaching its end.
  - A `timer.scheduleFunction` armed from inside a run and firing after that run has ended has
    crashed DCS (twice, DCS 2.9.30, `lua.dll` access violation in `wSimCalendar::DoActionsUntil`;
    intermittent, cause unproven). Keep its id and `timer.removeFunction` it on the normal exit
    path.
- Common mistakes: keep the outbox-stuck-on-`started` row.

### SKILL.md loses

| Content | Goes to |
|---|---|
| `dcs-scripting-facts.md` (whole file) | split between `dcs-agent-skills` and SkynetMunitionTests; delete here |
| Hoggit wiki links, waypoint-1 trap, spawn delay, spawn-name collision | `dcs-agent-skills` |
| Payload / CLSID / weapon-flag lookups, `getAmmo()` check, veaf MCP queries | `dcs-agent-skills` |
| "Restart replays `tempMission.miz`" as general advice, VEAF `src/scripts/` note | `dcs-agent-skills` |
| Skynet row in Common mistakes | SkynetMunitionTests |

Exception: `setup.md` tells the user to **re-open the `.miz` from the Mission menu** after it
patches the file, because that is a step of hotload's own procedure. One sentence, no general
explanation.

## Setup procedure (`setup.md`)

Run from the mission folder (the folder that holds, or will hold, `dcs-hotload/`). Every step
checks first and changes only what is missing, so running it again is harmless.

### 1. Deploy the tool

- Copy the release file set from the plugin root into `<mission>/dcs-hotload/`. The file set is
  the one the release zip uses: one list, read by `package.sh` and by the setup script, so they
  cannot diverge.
- The deployed version is `Hotload.version` in the deployed `dcs-hotload.lua`, the same line the
  release workflow reads; there is no separate version file. Equal to the plugin's: skip. Older:
  say so and update only when the user agrees (a mission keeps the version it was tested with
  until updated on purpose). Newer: say so and change nothing.
- **Never overwrite or delete** `user-lib/`, `user-scripts/`, `user-inbox/`, `user-outbox/`.
  Create `user-inbox/` and `user-outbox/` if missing (that turns the mailbox on).
- A mission that got hotload from a release zip is adopted as it is: it already carries its
  version.

### 2. Unlock the scripting environment

- Locate the DCS install (same candidates as the README; ask when none matches) and check
  `Scripts\MissionScripting.lua` for active `sanitizeModule('io')` / `sanitizeModule('lfs')`
  lines.
- When they are active: **ask before editing**, saying why (install-wide, every mission including
  multiplayer gets file access, multiplayer integrity checks, DCS updates revert it). Then comment
  the two lines out, keeping a `.bak` of the original.

### 3. Make the `.miz` load it

- Find the mission's `.miz` (ask when there are several).
- Look for an existing boot line: any trigger action text or embedded script that `dofile`s a
  `dcs-hotload.lua`. Missions built by other tools (VEAF) may load it from an embedded script;
  that counts.
- Present and pointing at this mission's `dcs-hotload\dcs-hotload.lua`: done. Present but
  pointing elsewhere (mission moved or copied): report it, offer to fix.
- Absent: add a MISSION START trigger with a DO SCRIPT action
  `dofile([[<absolute path>\dcs-hotload\dcs-hotload.lua]])`. The `.miz` stores triggers twice
  (`mission.trigrules`, shown by the editor, and `mission.trig`, run by DCS); both must be written,
  index for index, or the editor and DCS disagree.
- Keep a backup of the `.miz` before writing. Then tell the user to re-open it from the Mission
  menu (Restart replays the copy loaded at launch).

### 4. Verify

With the mission running: `hotload.sh log ready` shows the expected version and `mailbox on`, and
`hotload.sh run -e 'return Hotload.run("selftest/wait")'` returns `done`. When DCS is not running,
say that this step is still pending.

## Setup tooling

The skill ships its own helper; it must not depend on the `dcs-missions` plugin.

- **One Python 3 script, standard library only**: `skills/piloting-dcs-hotload/scripts/hotload-setup.py`
  with `status` (what steps 1 to 3 would change), `deploy`, `unlock`, `patch-miz <file.miz>`.
  Exit codes in the style of `hotload.sh`. Not `setup.py`, which Python tooling takes for a
  package build script.
- **The `.miz` is read and written in Python, without Lua.** Python's `zipfile` handles the zip; a
  small reader and writer handle the Mission Editor's Lua table format (the `mission` file and
  `l10n/DEFAULT/mapResource`). This is a deliberate change from the `dcs-missions` plugin, whose
  `miz.py` runs `mizedit.lua` through Lua 5.1: hotload users would otherwise need Lua only for
  setup. If it works well, the `dcs-missions` plugin can adopt it later. Prior art for the format
  and for writing `trig` and `trigrules` together: `mizedit.lua` (serializer, `M.onStart`) in
  `dcs-agent-skills/plugins/dcs-missions/skills/building-dcs-missions/scripts/`.
- **The writer must not change what it does not touch.** Reading then writing a mission without a
  change gives back the same tables; the patch adds one trigger and nothing else.
- **Tests**, in Python's `unittest`, beside the Lua suite and run by CI:
  - round trip on a fixture: an empty mission saved by the Mission Editor (the `caucasus.miz`
    template of `dcs-agent-skills`), and the same file after the patch;
  - the patch: boot line absent (added, `trig` and `trigrules` agree index for index), present
    (no change), pointing at another folder (reported, rewritten only on request);
  - deploy: a fresh folder, an up-to-date one (no change), an older one (`user-*` untouched);
  - locally, when a DCS install is found: the round trip on every mission DCS ships, a wide
    corpus of real files; skipped in CI.

## Optional: version check at session start

A plugin `SessionStart` hook (it gets `${CLAUDE_PLUGIN_ROOT}`) can compare the `Hotload.version`
of `./dcs-hotload/dcs-hotload.lua` with the plugin's and print one line when the mission is
behind. Silent when there is no `dcs-hotload/` in the working folder. Do it after the rest works.

## README changes

- Setup: add "With Claude Code: install the plugin (`/plugin marketplace add MacFlorent/dcs-hotload`,
  then `/plugin install dcs-hotload@dcs-hotload`; the marketplace is named `dcs-hotload`) and ask Claude to set up hotload in the mission." Manual steps
  stay as they are.
- Replace the "Claude Code skill (optional)" section and delete `skills/README.md` (its copy-into-
  each-mission install is what this change removes).

## Migration of existing missions

SkynetMunitionTests has `dcs-hotload/skills/` and `.claude/skills/piloting-dcs-hotload/` copies.
After the plugin is released, and only when the user says so: delete both, install the plugin,
run setup (adopts the existing `dcs-hotload/`).

## Acceptance

- Fresh mission folder holding only an empty `.miz`, plugin installed, nothing else: "set up
  hotload in this mission" deploys, asks before unlocking, patches the `.miz`, and the selftest
  returns `done` after re-opening.
- Running setup a second time changes nothing.
- Updating: with an older deployed version, setup reports it and updates without touching `user-*`.
- `grep -ri` over `skills/` finds no Hoggit link, no waypoint/payload/CLSID advice, no Skynet.
- The release zip contains no `skills/` and no `.claude-plugin/`.
- Offline tests pass: `lua5.1 test/run.lua` and the Python tests.

## Pull requests

1. `chore/pinned-luacheck` (outside this spec, independent): luacheck at a pinned version through
   `.github/scripts/lint.sh`.
2. The skill trimmed to the tool, `.claude-plugin/`, the release zip without `skills/`, the
   README.
3. The setup procedure: `setup.md`, `hotload-setup.py`, its tests.
4. `release/1.1.0`: the version, the marketplace entry pinned to `v1.1.0`. Then, in
   dcs-agent-skills, its marketplace entry for this plugin.

## Decisions

- **The `.miz` patcher is Python only** (see Setup tooling). Turned down: Python with Lua 5.1, as
  `miz.py` does (proven, but a Lua install only for setup); Lua with an outside zip tool (Git Bash
  has none).
- **The deployed version is read from `dcs-hotload.lua`.** Turned down: a `VERSION` file written
  at deploy, easier for shell scripts but a second copy of the version that can disagree.

## Comments

Decided while building the setup (third pull request):

- **One list of shipped files**, `.github/scripts/shipped.txt`, read by `package.sh` and by
  `hotload-setup.py`, so the release package and a deployed mission hold the same files.
- **Exit codes**: 0 done or nothing to do, 1 failed or refused, 2 a decision is needed (rerun with
  the flag the message names once the user agrees), 3 usage. The script never decides for the
  user: `deploy --update`, `unlock --yes` and `patch-miz --retarget` are explicit.
- **`status` does not count an older deployed version as missing**: a mission keeps the version it
  was tested with; it reports it.
- **The writer follows the style of the file it read**: DCS 2.9.30 writes tabs and `{}` for an empty
  table, older missions four spaces and an open pair. Numbers are kept as written. The round trip
  is exact on all 951 missions DCS ships here; that check takes about a minute and a half, so it
  runs on request (`HOTLOAD_TEST_SHIPPED_MISSIONS=1`), not in CI.
- **The verify step runs `return "pong"`** through the mailbox rather than a self-test, which a
  fresh `user-scripts/` does not hold.
- `.luacheckrc` excludes `dist/`: a local `package.sh` run left a copy of the broken self-tests
  there for luacheck to find.
- **Tried in DCS 2.9.30**: a mission set up by a headless agent (`deploy`, `patch-miz`) opened in DCS,
  its trigger loaded the mission's `dcs-hotload.lua`, and `hotload.sh run -e 'return "pong"'` came back
  `done` with `pong`.
