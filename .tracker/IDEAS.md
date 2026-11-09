# Ideas

Prospective work. An idea taken up leaves this file in the commit that opens its spec; a dropped
idea stays, with its reason.

## Check the skill against a live mission

The skill was tested against a stand-in DCS. Run its scenarios in a real mission, from a fresh
install following `skills/README.md`.

## Read a `mission` table in any key style

`hotload-setup.py` reads a `.miz`'s `mission` only in the Mission Editor's style
(`["coalition"] = {`) and fails on any other valid Lua table: `cannot read the mission: line 3:
expected '['` on every `.miz` built by VEAF MCT 6.36.0, which writes bare keys
(`coalition = {`), a different layout and indentation, and keeps the same content (checked on
IADS-Caucasus Mk2: the tables are equal outside the triggers). `status --miz` and `patch-miz`
are unusable on those missions. Accept bare identifier keys; keep writing in the style of the
file read, as the help already says.

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
