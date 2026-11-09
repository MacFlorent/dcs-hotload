# Ideas

Prospective work. An idea taken up leaves this file in the commit that opens its spec; a dropped
idea stays, with its reason.

## Check the skill against a live mission

The skill was tested against a stand-in DCS. Run its scenarios in a real mission, from a fresh
install following `skills/README.md`.

## Boot from a mission variable, and stop quietly without it

Today the boot line is a bare `dofile([[<absolute path>\dcs-hotload.lua]])`, and every way it can
miss is loud: a missing file raises a script error, and missing `io`/`lfs` or an unknown root make
`fail()` print for 60 seconds. A mission that keeps its hotload trigger in the copy it hands to
players (a VEAF MCT v6 mission rebuilds its `.miz` from `src/mission/` at every build, so the
trigger cannot be added to one build only) then shows that to every player.

Make the boot follow the Skynet-IADS in-sim template (`test/insim/miz/*.template.miz`): one
MISSION START trigger whose first action sets `BASE_HOTLOAD_PATH = [[<folder>]]`, and whose next
action loads `BASE_HOTLOAD_PATH .. "/dcs-hotload.lua"`. When the variable is unset or empty,
`lfs` is missing (the install is not unlocked) or the file is not there, the boot stops with
one `HOTLOAD:` line in `dcs.log` and nothing on screen. A missing `io`/`lfs` stays loud only once
the path has been found, since only a developer's machine gets that far.

Then shipping a mission is a matter of clearing the value as a post-build step, and forgetting to do
so is harmless: the folder does not exist on a player's machine. `patch-miz` writes this trigger
instead of the bare `dofile`; the README gives it as the setup line.

Working template: trigger "dcs-hotload boot" in
`D:\Projects\DcsMissions\VEAF-IADS-Caucasus-Mk2\src\mission\mission` (2026-11-08). Its second action
logs `HOTLOAD: not booted: BASE_HOTLOAD_PATH is not set`, `... lfs is not available ...` or
`... no dcs-hotload.lua in <path>`, else sets `Hotload.root = p` and `dofile`s. It survives a
VEAF MCT 6.36.0 build (which renumbers it but keeps it); checked offline against stubs, not yet
in DCS.

## Set or clear the boot path of a built `.miz`

The post-build step above, as a `hotload-setup.py` command: write a folder into
`BASE_HOTLOAD_PATH`, or clear it, in a `.miz` that already has the trigger. Like the in-sim
`engine/mission.py`, it has to change both copies DCS keeps of a DO SCRIPT text (the `trigrules`
action and the compiled `trig.actions` string), and refuse a `.miz` where it does not find exactly
those two.

Working template: `D:\Projects\DcsMissions\VEAF-IADS-Caucasus-Mk2\build-hotload.py`
(`show|set|clear`, on a `.miz` or an extracted `mission` file; atomic rewrite keeping every other zip
entry byte for byte; `set` refuses a folder without `dcs-hotload.lua`). VEAF MCT 6.36.0 has no
post-build hook, so the mission's `build.py` runs `veaf-tools.exe mission build` and then `clear` on
each `.miz` the build wrote (new or changed since a snapshot taken before it; a timestamp threshold
also caught a `.miz` the previous run's `clear` had just rewritten), unless `--hotload`.

## Known rough edges

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

### An MCP front end

The mailbox driven with plain file tools and the mailbox client has been enough. Worth it
only if a tool-call interface brings something the mailbox cannot.

### Record the executable bit of `bin/hotload.sh`

`bin/hotload.sh` is gone: `bin/hotload.py` is run as `python hotload.py`, which needs no bit.
