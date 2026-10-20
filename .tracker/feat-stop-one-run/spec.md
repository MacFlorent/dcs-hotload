# Stop one run

Status: done

Meant for `2.0.0` with `feat-user-f10`; the labels below are the ones it gives. Written from the
Skynet-IADS in-sim test suite, its first user; nothing below is specific to Skynet.

## The problem

A test driver outside DCS runs each scenario as a string of mailbox commands: setup, run, teardown.
Each command is its own run, so a raise in one fails only that command, and the driver still sends
the next. Waits inside a scenario are bounded by `Hotload.waitFor(fn, timeout)`.

Those bounds are cooperative. A command that waits forever any other way (a `Hotload.wait(3600)`
by mistake, a loop of waits that never exits) never ends. The driver gives up waiting on it, but the
run carries on in the mission: the teardown and the next scenario would then run alongside it,
acting on the same world.

The only stop is F10 *Stop all runs*. It ends every run, and it cannot be reached from the mailbox.

A run that never pauses (`while true do end`) freezes the sim; nothing can stop it, this included.

## What to build

### `Hotload.stop(label)`

```lua
return Hotload.stop("inbox/skynet-smoke-run-1729260000")   -- true: it was running, and is stopped
```

- `label` is a run label exactly as the log and the outbox's `label` field print it: `inbox/<name>`
  or `f10/<path>`. No normalisation.
- The run ends as `stopped`, as under *Stop all runs*: `stopped <label>` in the log and on screen,
  and `onFinish` called once, so an inbox command's outbox reads `status = "stopped"`.
- **It takes effect between resumes.** One run executes at a time, so the target is paused, never
  inside a resume. What it was paused on is dropped: a `callOnMain` function that has not run yet
  never runs. What it armed through `callOnMain` stays armed: cleaning up is the caller's job.
- It logs who asked: `stop <label> (from <caller's label>)`, or `(from outside a run)`.
- It does not pause, so it works anywhere: in a run, in a `callOnMain` function, in a `waitFor`
  predicate, in a DCS callback, at the mission's top level.

| Case | Result |
|---|---|
| the run was active | `true`, once it is stopped |
| no active run has that label | `false`; a target that just ended is not an error |
| the label is the caller's own | raises: the run would be finished in the middle of its own resume, then finished again when the resume returns |
| `label` is not a non-empty string | raises |

"The caller" is `current`, the run hotload is executing, so a stop from the caller's own
`callOnMain` function or predicate is refused too.

### One way to stop, shared with *Stop all runs*

- **`stopRun(run)`**, the only code that stops a run: `finishRun(run, "stopped")`. `Hotload.stop` adds
  its checks and its log line; *Stop all runs* is `stopRun` on each active run, with its
  `nothing running` message unchanged.
- A stop from inside a run happens during the tick. The tick already skips a run that ended earlier
  in the same tick (`runs[run.label] == run`), so a target later in the tick's snapshot is not
  stepped.

### The mailbox client

- A stop is a command like any other: `hotload.sh run -e 'return Hotload.stop("inbox/NAME")'`.
  The only change to `bin/hotload.sh`: its timeout message also prints the label to stop,
  `inbox/NAME`.
- A stop subcommand belongs to the Python mailbox client meant to come with the test driver.

## Decisions

| Decision | Turned down | Why |
|---|---|---|
| Stop one run, called by whoever drives | a timeout on each inbox command | the driver already knows how long it is prepared to wait; one primitive covers every run that waits forever |
| Refuse the caller's own label, by raising | return `false` | asking for it is a bug in the script, not a race; a run that wants to end returns |
| `false` for an unknown label | raise | the target may have just ended: the caller decides |
| Callable anywhere | only inside a run | it does not pause; a DCS callback or a trigger may well need it |
| One `stopRun`, shared with *Stop all runs* | two ways to stop | a stopped run ends the same way, whoever stops it |
| No subcommand in `hotload.sh` | `hotload.sh stop NAME` | the Python client is meant to replace or join it; one line of `run -e` does it meanwhile |
| No per-run stop in F10 | a dynamic menu of active runs | the menu would have to be rebuilt on every start and end; no one has asked for it |

## Versioning

A new function: part of `2.0.0` with `feat-user-f10`, or a minor version if it ships alone. No
status or outcome value changes: `stopped` exists already. `CHANGELOG.md` under `[Unreleased]`. The
README's call table and its *Stop all runs* paragraph; the skill's limit "*Stop all runs* abandons
a command mid-wait without running its cleanup" covers `Hotload.stop` too, and its client section
says how to stop a command that timed out.

## Tests

Offline, against `test/dcs-stub.lua`, each seen failing first:

- `Hotload.stop` from one inbox command ends another that is waiting; the target's outbox reads
  `stopped`; the caller's reads `done` with `true`;
- a target later in the same tick than its caller is not stepped once stopped;
- `onFinish` is called once per stopped run;
- an unknown label returns `false`;
- the caller's own label raises: from its code; from its `callOnMain` function, which then returns
  `false` and the message; from its predicate, which fails the run as any raise there does;
- a target paused on `callOnMain`: stopped, and its function never runs;
- a stop from outside any run works;
- *Stop all runs* still ends everything.

## Out of scope

- A timeout on inbox commands.
- A per-run stop in F10.
- Stopping a run that never pauses.
- A test driver, scenario format or report, and a mailbox client in Python: built in Skynet-IADS
  first, meant to come back here later (`IDEAS.md`, "A test tool that drives hotload", stays).
