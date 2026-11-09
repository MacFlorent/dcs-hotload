# Ideas

Prospective work. An idea taken up leaves this file in the commit that opens its spec; a dropped
idea stays, with its reason.

## Check the skill against a live mission

The skill was tested against a stand-in DCS. Run its scenarios in a real mission, from a fresh
install following `skills/README.md`.

## Ship `hotload-setup.py` where a build script can find it

The release package holds `bin/hotload.py` but not `hotload-setup.py`, which lives in the plugin's
versioned cache folder. A mission's build script that clears the path after each build
(`boot-path --clear`; VEAF MCT has no post-build hook) has to look for it under
`~/.claude/plugins/cache/dcs-agent-skills/dcs-hotload/<version>/skills/...` and pick the newest
(IADS-Caucasus Mk2's `build.py`, with `$HOTLOAD_SETUP` to override). Shipping it in `bin/`, next to
`hotload.py`, would let a mission call the copy it was deployed with.

## Known rough edges

- `status --miz FILE` on a file that does not exist ends in a Python traceback
  (`FileNotFoundError` from `Miz.read`) instead of a `hotload-setup:` line and exit 1.
- A command name whose outbox could not be written stays blocked until the mission restarts, and
  that is only logged, not shown.
- A final outbox write that fails loses the outcome; retrying it from the poll would keep it.
- `writeOutbox` truncates the file before serializing; serializing first would never leave an
  empty outbox.
- Results deeper than about 197 levels, or with more than about 131,000 distinct values, are
  written but cannot be read back by `dofile`.
- Each poll stats every inbox file twice.
- An inbox or outbox folder that exists but cannot be read is reported as missing.
- `duration` in outbox files keeps float noise (`0.10000000000000142`).
- A predicate failure carries no traceback; argument errors in `Hotload.*` point inside the core
  rather than at the caller's line.

## Dropped

### Patch a mission's source, not only a `.miz`

The idea: let `patch-miz` and `boot-path` open an extracted `mission` file or folder, for missions
kept as source and rebuilt by a tool (VEAF MCT v6's `src/mission/`). Dropped:

- hotload should not know how a build tool works;
- the trigger is added in the `.miz`, just as a mission maker would add it in DCS, and the tool's
  own extract (`veaf-tools mission extract`) puts it in the extracted mission file.

### An MCP front end

The mailbox driven with plain file tools and the mailbox client has been enough. Worth it
only if a tool-call interface brings something the mailbox cannot.

### Record the executable bit of `bin/hotload.sh`

`bin/hotload.sh` is gone: `bin/hotload.py` is run as `python hotload.py`, which needs no bit.
