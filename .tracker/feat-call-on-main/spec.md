# Run a function on the mission's main Lua state

Status: in-progress

## Problem

A run is a coroutine, and to DCS a coroutine is a Lua state of its own. A `timer.scheduleFunction`
armed from a run, directly or through a library, has crashed DCS once the run ended (an access
violation in `lua_pushcclosure`, under `Scripting::regLuaStaticObject` and
`wSimCalendar::DoActionsUntil`). The likely cause: DCS calls a timer back on the state that armed
it, and that state is gone once the run's coroutine is collected. Re-arming from such a callback
does not help, since the callback runs on the same state.

So a framework that keeps timers alive (Skynet IADS, MOOSE, MIST) cannot be set up or torn down
from a run: not only loading it, but any call that arms its timers, such as activating a Skynet
network. A campaign that drove Skynet through hotload ran crash-free only once every such call went
through a function queue on the main state, loaded by a MISSION START trigger in its `.miz`.

Hotload's tick already runs on the main state: it is armed from the F10 menu or the mailbox poll,
never from inside a run. It can run those functions itself, without any trigger.

## What to build

`Hotload.callOnMain(fn)`: runs `fn` on the mission's main Lua state and returns like `pcall`:

```lua
local ok, iads = Hotload.callOnMain(function()
  dofile(lfs.writedir() .. "Scripts/skynet-iads-compiled.lua")
  local iads = SkynetIADS:create("RED")
  iads:activate()
  return iads
end)
```

- It pauses the run, so the rules of `wait` and `waitFor` apply: only in the script's own code,
  never under a `pcall`.
- The run yields a pause of kind `main`. On the next tick, `step` calls `fn` directly, with no
  coroutine of its own (unlike a `waitFor` predicate, which `probe` runs in one), and resumes the
  run with `true, ...` (what `fn` returned) or `false, message`.
- A raise in `fn` is logged with its traceback, and comes back as `false, message`.
- Inside `fn`, `Hotload.log` and `Hotload.say` work, stamped with the run's label. The other
  `Hotload.*` calls raise, since `fn` is not the run's code: a script loads its modules before
  calling `callOnMain`, and `fn` uses them through its closure.
- Whatever `fn` arms belongs to the main state and outlives the run.
- *Stop all runs* before the next tick: `fn` never runs. After it: its effects stay, like anything
  else a stopped run did.

A minor version: it only adds to `Hotload.*`.

## Decisions

- **Returns like `pcall`, rather than raising in the run.** A script cannot catch a raise from a
  call that pauses (Lua 5.1 cannot pause across `pcall`), and a test's teardown must be able to try
  every step. `Hotload.run` already returns its outcome rather than raising.
- **In the core, not in a `user-lib/` package or a mission trigger.** A `user-lib/` module is
  loaded from a run, so it cannot arm a main-state timer; the alternative is a MISSION START
  trigger in every mission, where hotload asks for one boot line.
- **Called `callOnMain`, not `onMain`:** `on…` reads as an event handler, and this is a call.
- **No timeout:** `fn` runs on the next tick, so there is nothing to wait for.

## Out of scope

- A queue that outlives the run, or `callOnMain` from a mission trigger or a DCS callback: there is
  no run to resume there.
- Making `timer.scheduleFunction` safe by itself inside a run (wrapping the global): a library
  calling it under a `pcall` would then pause across that `pcall`.
- The skill's guidance on timers and frameworks: rewritten once this is tested in DCS.

## Verification

- **Offline:** the stub records whether each `scheduleFunction` came from inside a coroutine. A
  timer armed in `fn` comes from the main state; the same timer armed directly from a run does not
  (so the test can tell). Return values and `false, message` reach the run; `callOnMain` raises
  outside a run and inside `fn`; *Stop all runs* before the next tick means `fn` never runs.
- **In DCS, before merging:** a command loads Skynet and activates a network through `callOnMain`,
  then ends; the mission runs several minutes without a crash; a second command deactivates the
  network through `callOnMain`.
