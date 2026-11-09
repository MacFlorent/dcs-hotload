# A boot trigger that stays quiet where hotload is not installed

Status: in-progress

Takes up two ideas: *Boot from a mission variable, and stop quietly without it* and *Set or clear
the boot path of a built `.miz`*. The working templates are in
`D:\Projects\DcsMissions\VEAF-IADS-Caucasus-Mk2`: the triggers "dcs-hotload path" and
"dcs-hotload boot" in `src/mission/mission`, and `build-hotload.py` (2026-11-08).

## The problem

The boot line `patch-miz` writes, and the README gives, is a bare
`dofile([[<absolute path>\dcs-hotload\dcs-hotload.lua]])`. Where that file does not exist, which
is every machine but the developer's, DCS raises a script error when the mission starts. A
mission whose trigger stays in the copy handed to players shows that error to anyone who opens or
hosts it. A mission rebuilt from source at every build cannot leave the trigger out of one build
only.

In multiplayer, mission scripts run on the server only, so a client never sees the error. It
shows to a player who opens the mission alone or hosts it.

`fail()` (60 seconds on screen) is not what players see: on their machine the `dofile` fails
first.

## What to build

### 1. The guarded boot trigger

`patch-miz` writes one MISSION START trigger, commented `dcs-hotload boot`, with two DO SCRIPT
actions:

```lua
BASE_HOTLOAD_PATH = [[D:\Missions\M\dcs-hotload]]
```

```lua
local p, f, err = BASE_HOTLOAD_PATH
if type(p) ~= "string" or p == "" then err = "BASE_HOTLOAD_PATH is not set"
else f, err = loadfile(p .. "/dcs-hotload.lua") end
if not f then env.info("HOTLOAD: not booted: " .. tostring(err)) return end
Hotload = Hotload or {}; Hotload.root = p; f()
```

The second action is the same text in every mission: `boot-guard.lua`, next to the setup
script, which `patch-miz` writes as it is and `test/test_boot.lua` runs against the stub. A
test checks that the README gives the same text. Where the variable is empty or the file
absent, the mission logs one `HOTLOAD: not booted:` line in `dcs.log` and shows nothing.
`loadfile` is not removed by a stock `MissionScripting.lua`, so the guard needs neither `io` nor
`lfs`. Once the file is found, a missing `io`/`lfs` is still reported on screen by hotload: only a
developer's machine gets that far.

`find_boot` reads the variable's value as the boot folder, wherever the assignment is: in the
trigger that holds the guard or in a trigger of its own. `status` tells a cleared path apart from
a missing trigger. `--retarget` rewrites the variable, in both copies DCS keeps of the text. The
bare `dofile` keeps being recognized, in triggers and in embedded scripts.

The README's setup step and the skill's `setup.md` give the two actions; the header of
`dcs-hotload.lua` points at the README.

### 2. `boot-path`: show, set or clear the folder

```
python hotload-setup.py boot-path FILE [--set DIR | --clear]
```

Prints the folder the trigger points at, writes another, or empties it. The post-build step of a
mission that is handed out: forgetting it is harmless (the folder does not exist on a player's
machine), and running it keeps the developer's folder layout out of the shared file.

DCS keeps two copies of a DO SCRIPT text: the `trigrules` action (what the editor shows) and the
compiled `trig.actions` string (what DCS runs). Both change, and the command refuses a mission
where it does not find exactly one assignment in each. `--set` refuses a folder without
`dcs-hotload.lua`. The rewrite is atomic and keeps every other zip entry byte for byte.

### 3. Guidance: handing a mission to players

The skill's `setup.md` says what is safe to ship: the guarded trigger is; a bare `dofile` is not.
It says to clear the path when a mission leaves the developer's machine. The README gets one line
on the same point.

## Decisions

- **A variable, then a constant guard**, rather than one action with the path inside the guard:
  the guard is the same text in every mission, and `boot-path` changes one line that says
  nothing but the folder.
- **`BASE_HOTLOAD_PATH`, not `Hotload = { root = ... }`** as the variable: a `Hotload` table that
  exists before the boot would look to other scripts like hotload is running, booted or not.
  The name follows the Skynet-IADS in-sim template.
- **`loadfile`, not `lfs.attributes`**, to test for the file: it is there on a stock install, and
  it also catches a file that does not compile, which the log line then names.
- **A bare `dofile` already in a mission is left as it is.** `patch-miz` does not rewrite it to
  the guarded form; `status` says it is unguarded.

## Out of scope

- Any mission build tool. hotload works on a `.miz`. A mission built from source gets the
  trigger the way that tool takes any trigger, for instance by patching a built `.miz` and
  extracting it back into the source. Running `boot-path --clear` after a build is the mission's
  own build step.
- Reading or writing an extracted `mission` file: patching the `.miz` and extracting it back
  covers that need.
- Hiding hotload's F10 menu or its `ready` message from players: both appear only where hotload
  booted, which the guard limits to the developer's machine.

## Pull requests

1. The guarded trigger: `patch-miz`, `find_boot`, `status`, `--retarget`; the README and the
   header of `dcs-hotload.lua`. **Needs an in-game check**: a boot through `loadfile` with
   `Hotload.root` set; a cleared path; an unlocked install without the folder; a stock install.
2. `boot-path`.
3. The guidance in `setup.md`, unless it rode with 2.

## Comments
