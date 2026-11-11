# Ship the setup script with hotload

Status: in-progress

Takes up the idea *Ship `hotload-setup.py` where a build script can find it*.

## The problem

`hotload-setup.py` lives only in the Claude Code plugin, in a versioned cache folder. Two kinds of
users cannot reach it:

- **A mission's build script.** It clears the boot path after each build (`boot-path --clear`), so
  it has to search `~/.claude/plugins/cache/dcs-agent-skills/dcs-hotload/<version>/skills/...` and
  pick the newest. That depends on how Claude Code lays out its cache, and on a script version
  unrelated to the mission's copy.
- **Someone without Claude Code.** The release package has no setup tool: the README's *Setup*
  has them edit `MissionScripting.lua` and type the trigger by hand.

## What to build

### 1. `bin/hotload-setup.py`, shipped in every copy

The script moves from `skills/piloting-dcs-hotload/scripts/` to `bin/`, with `boot-guard.lua` next
to it. `bin` is already in `shipped.txt`, so both reach the release package and every deployed
mission without changing the list.

It stands on its own: it reads nothing outside its copy, and needs no plugin, repository or
`shipped.txt`. It works on the copy it belongs to and on that copy's mission.

**The structure it assumes** (the one the README recommends):

```
<mission folder>/
  <mission>.miz              the only .miz
  dcs-hotload/               the copy: dcs-hotload.lua, bin/hotload-setup.py, user-*/
```

- The copy is `Path(__file__).parents[1]`; the mission folder is its parent.
- The `.miz` is the only one in the mission folder. `--miz FILE` names it when there are several
  or none; the error says so.
- Anything else is refused with a message naming what was expected, unless `--miz` makes it
  workable. Run from the repository (hotload's own development), `--miz` points a test mission at
  the repository's copy; that stays possible.

**Commands:**

```
python dcs-hotload/bin/hotload-setup.py status    [--miz FILE] [--dcs DCS]
python dcs-hotload/bin/hotload-setup.py unlock    --dcs DCS
python dcs-hotload/bin/hotload-setup.py patch-miz [--miz FILE]
python dcs-hotload/bin/hotload-setup.py boot-path [--miz FILE] [--set DIR | --clear]
```

- `status`: this copy's version; whether the mailbox is on (reported, not counted in the exit
  code); whether the `.miz` boots this copy (or another folder, a cleared path, a bare `dofile`,
  nothing); with `--dcs`, whether `io` and `lfs` are unlocked. Without `--dcs` the unlock is
  reported as not checked.
- `unlock`: makes the edit, with no `--yes`; it says what the edit means once done.
- `patch-miz`: adds the boot trigger pointing at this copy, or points an existing boot at it.
  `--mission` and `--retarget` go: the folder written is always the copy's own.
- `boot-path`: unchanged, except that the `.miz` is found as above. `--set DIR` still accepts any
  folder holding `dcs-hotload.lua`.

The command names stay: they are documented in released versions.

### 2. `deploy`, a script of the skill

`skills/piloting-dcs-hotload/scripts/hotload-deploy.py` does what `hotload-setup.py deploy` does
today: copies the files `shipped.txt` lists from the plugin into `<mission>/dcs-hotload/`,
replaces an older copy only with `--update`, leaves a newer one alone, creates any missing
`user-*` folders (even when the copy is already current), and asks for `user-scripts/` to be
renamed. It also reports the deployed version against the plugin's, which `status` did until now.

It duplicates the few helpers it needs (`lua_version`, `version_key`, reading `shipped.txt`) rather
than importing the shipped script: about sixty lines, and no coupling between the plugin's layout
and a copy's.

**The skill's flow:** deploy from the plugin, then run the *mission's* copy for everything else:

```
python <skill>/scripts/hotload-deploy.py --mission DIR [--update]
python DIR/dcs-hotload/bin/hotload-setup.py status --dcs DCS
python DIR/dcs-hotload/bin/hotload-setup.py unlock --dcs DCS     # once the user agrees
python DIR/dcs-hotload/bin/hotload-setup.py patch-miz
```

The plugin is installed from this repository at a release tag, so its cache folder holds a copy
of `bin/hotload-setup.py` too. The skill never runs that one: its `patch-miz` would point the
mission at the plugin cache.

### 3. Output and errors fit for public use

The command line becomes a public interface (build scripts call it), so these are settled before
the first release that ships it:

- **No tracebacks.** Each of these ends in a `hotload-setup:` line and exit 1:
  - a `.miz` that does not exist (taken from *Known rough edges* in `IDEAS.md`);
  - a folder the `.miz` or its backup cannot be written in (`PermissionError` from the backup copy
    and from `mkstemp`);
  - a `mission` entry or a `MissionScripting.lua` that is not UTF-8;
  - a `.miz` without a `mission` entry: "not a mission", instead of the `KeyError` text `'mission'`;
  - `boot-guard.lua` missing next to the script: read when `patch-miz` needs it, not at start, so
    `unlock`, `status` and `boot-path` still work.
- **`main` stops catching `KeyError`**: a bug is not reported as an unreadable mission.
- **Output that a captured, non-UTF-8 stdout cannot encode** (a build script on Windows, a
  mission name outside cp1252) is escaped instead of crashing after the `.miz` was written:
  `reconfigure(errors="backslashreplace")` on stdout and stderr.
- **Streams, as `bin/hotload.py` does**: results (`status` lines, the path `boot-path` shows) on
  stdout; refusals, failures and the decision prompts on stderr. Same `hotload-setup:` prefix.
- **Exit codes**: 0 done or nothing to do, 1 failed or refused, 2 not set up (`status`), 3 usage.
  `status` gives 1, not 2, for a `--dcs` that is not a DCS install.
- **Messages addressed to whoever runs it**, never "once the user agrees". The rule to ask first
  is the skill's.
- **`--help`** is usage only. The paragraph on the `.miz` writer becomes a comment.
- **Python 3.8 or later**, as the client.

### 4. Documentation

- **README**, *Setup*: step 2 and 3 give the script first (`unlock`, `patch-miz`), the manual edit
  and the two DO SCRIPT actions as the alternative. A section on the script: the structure it
  assumes, its commands, exit codes, and clearing the path in a build. The command line is stated
  as a public interface.
- **The skill**: `setup.md` keeps what is the agent's to do: deploy first, then the mission's copy;
  ask before `--update`, `unlock`, and `patch-miz` over a boot of another folder. Usage points at the README.
- **CONTRIBUTING**: layout table, the test table, the versioning paragraph (the script's command
  line and exit codes join the mailbox as a public interface).
- **CLAUDE.md**: the *Never* line on incompatible changes names the setup script's command line;
  the *Before you do these, read* row for `bin/hotload.py` covers `bin/hotload-setup.py`.
- **CHANGELOG**: the script ships; the skill deploys with `hotload-deploy.py`; a build script that
  looked in the plugin cache should call the mission's `dcs-hotload/bin/hotload-setup.py`.

### 5. Tests and paths

- `test/python/test_hotload_setup.py` loads `bin/hotload-setup.py`; it gains tests run from a copy
  laid out as a mission (a temp folder with a `.miz` and `dcs-hotload/bin/`), for the structure
  rules and each error above.
- A new `test/python/test_hotload_deploy.py` takes over the deploy tests.
- `test/test_boot.lua`, `.luacheckrc`: `bin/boot-guard.lua`.
- The README's copy of the guard is still checked against `boot-guard.lua`.

## Decisions

- **`patch-miz` takes no `--retarget`.** Running it is the decision to boot this copy: a boot of
  another folder, or a cleared one, is pointed at it and the output says what it was. The agent
  asks first when `status` reports such a boot. With it gone, exit 2 has one meaning in the
  shipped script: `status`'s "not set up". Turned down: keeping `--retarget`, a second step for a
  decision already made.
- **`unlock` takes no `--yes`.** Whoever types `unlock --dcs <their install>` has decided; the
  `--dcs` path is theirs, so the command cannot be pasted from a guide unchanged. The agent asks
  before running it, by the skill's rule. Turned down: keeping `--yes`, a second step for a
  decision already made.
- **The script acts on its own copy, not on the current folder.** Turned down: `--mission`
  defaulting to `.`, which points a mission at whatever folder the command was run from.
- **Deploy stays in the plugin.** A copy cannot deploy itself, and someone with the release zip
  deploys by extracting it. Turned down: one script with a deploy that works from the plugin and
  refuses from a copy.
- **A missing mailbox does not make `status` exit 2.** `status` reports it (`mailbox off
  (user-inbox/ missing)`) and leaves it out of the exit code: for someone using only the F10 menu
  the mailbox is optional, and in the skill's flow deploy, run first, has already created the
  folders. Turned down: counting it only with a new `--mailbox` option, one more option in a public
  command line for a case deploy already covers.
- **A separate deploy script, duplicating its helpers.** Turned down: importing the shipped
  script from the plugin's `bin/`, which ties the skill to that module's internals.

## Out of scope

- Creating the `user-*` folders from the shipped script.
- Any change to the trigger, the guard, or the `.miz` reader and writer.

