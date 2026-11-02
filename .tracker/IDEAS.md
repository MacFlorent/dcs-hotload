# Ideas

Prospective work. An idea taken up leaves this file in the commit that opens its spec; a dropped
idea stays, with its reason.

## A tool that drives hotload

A separate tool, run on the developer's machine, that uses the mailbox as its only interface.
This is extracted from Skynet-IADS's in-sim test engine, which was built to leave that
repository. `bin/hotload.sh run` is ported to Python with it, so the tooling is in one language.

Lessons from the SkynetMunitionTests campaign (about 300 runs) that the tool must keep: each run
appends its own result, so a crash costs one run and the series resumes; every command gets a unique
mailbox name, since a reused one lets a stale waiter pick up a later result; a run checks its own
preconditions before a "no" is trusted; a framework is driven through `Hotload.callOnMain`; on
Windows, a background driver that Claude Code stops keeps running and is killed by process id; a bash
driver is never edited while it runs, since bash reads it as it goes.

It reads the mission's state from the heartbeat (`feat-heartbeat`), in place of Skynet's probe.

## Check the skill against a live mission

The skill was tested against a stand-in DCS. Run its scenarios in a real mission, from a fresh
install following `skills/README.md`.

## Record the executable bit of `bin/hotload.sh`

Git for Windows commits every file as `100644`, so a Linux or macOS clone gets a `hotload.sh`
that `./bin/hotload.sh` refuses to run. Nothing breaks: every document runs it as
`bash bin/hotload.sh`. Fix once with `git add --chmod=+x bin/hotload.sh`; check with
`git ls-files -s bin/hotload.sh` (`100755`).

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

The mailbox driven with plain file tools and `bin/hotload.sh` has been enough. Worth it
only if a tool-call interface brings something the mailbox cannot.
