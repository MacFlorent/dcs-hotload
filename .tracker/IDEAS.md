# Ideas

Prospective work. An idea taken up leaves this file in the commit that opens its spec; a dropped
idea stays, with its reason.

## A test tool that drives hotload

A separate tool, run on the developer's machine, that uses the mailbox as its only interface.
Measure in DCS, judge outside: a scenario is an inbox command returning measurements; verdicts are
luaunit tests in plain Lua 5.1 that send their scenario, wait, save the result, and assert. Serial,
one scenario at a time with a timeout each (concurrent heavy engagements have frozen DCS);
results saved so assertions can be re-run offline; scenarios clean up their own world; in-sim
helpers ship as a `user-lib/` package. Open: name and location, result archiving without a wall
clock, a preflight check, how existing in-sim suites move to it, whether it ships a skill.

## An MCP front end

Deferred: the mailbox driven with plain file tools and `bin/hotload.sh` has been enough. Worth it
only if a tool-call interface brings something the mailbox cannot.

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
- `Hotload.run` inside a `pcall` starts the child run, then fails to wait for it.
- A `user-scripts/inbox/` folder would share labels with inbox commands.
- Each poll stats every inbox file twice.
- An inbox or outbox folder that exists but cannot be read is reported as missing.
- `duration` in outbox files keeps float noise (`0.10000000000000142`).
- A predicate failure carries no traceback; argument errors in `Hotload.*` point inside the core
  rather than at the caller's line.
- `README.md` says `Hotload.load` cannot be called inside a `pcall` (it can; only waits cannot)
  and that a predicate should not log (it may).
