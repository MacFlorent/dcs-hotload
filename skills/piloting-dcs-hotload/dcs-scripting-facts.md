# DCS scripting facts for live-mission Lua

## The API: Hoggit wiki

Look API details up rather than recalling them; values from memory are often wrong.

| Need | Page |
|---|---|
| Index of singletons, classes, enums, tasks, events | https://wiki.hoggitworld.com/view/Simulator_Scripting_Engine_Documentation |
| Spawning (`coalition.addGroup`): group table, payload, route | https://wiki.hoggitworld.com/view/DCS_func_addGroup |
| Bombing task parameters | https://wiki.hoggitworld.com/view/DCS_task_bombing |
| Weapon flags (`weaponType`) | https://wiki.hoggitworld.com/view/DCS_enum_weapon_flag |
| AI options (ROE, REACTION_ON_THREAT) | https://wiki.hoggitworld.com/view/DCS_enum_AI |
| Shot event (`S_EVENT_SHOT`; guns use `S_EVENT_SHOOTING_START`) | https://wiki.hoggitworld.com/view/DCS_event_shot |

Two wiki rules that bite in tests: a spawned group needs a delay before its controller is given
tasks, commands or options (in a hotload run, `Hotload.wait(1)` first); a spawn with an existing
group name destroys that group, so make names unique.

## Measured, not in the wiki (DCS 2.9, through dcs-hotload)

**A task on waypoint 1 of an air-started group is ignored.** The aircraft flies the route and never
attacks; Weapon Free does not fix it (it then attacks whatever it sees, late). The same task on
waypoint 2, or pushed with `controller:pushTask` after the spawn delay, executes.

A combination proven to release (GBU-38 about 20 km short of the aim point, from 40 km at 18,000 ft):
F-16C_50, `{GBU-38}` on pylons 3 and 7, `weaponType = 2147485694` (any bomb), `expend = "One"`,
`attackQty = 1`, speed 230 m/s, the Bombing task on a waypoint 5 km after the spawn point, then
`SetInvisible` and `REACTION_ON_THREAT = NO_REACTION` after `Hotload.wait(1)`.

**Observing a munition.**
- Follow `e.weapon` from the shot event; poll `Object.isExist(weapon)` in `Hotload.waitFor` for its
  end. Its height above ground when it disappears tells interception (hundreds of metres) from
  impact.
- A weapon's `getName()` is `""`; Skynet names its contact `tostring(weapon.id_)`.
- `Hotload.waitFor` resolves to 0.1 sim-second; Skynet refreshes contacts every 5 s.

**Skynet.**
- Last line of defence finds aircraft through `coalition.getGroups`, which ignores invisibility:
  disable it (`iads:setLastLineOfDefence(false)`, where the build has it) when the munition must be
  the only contact.
- A site out of ammunition stays dark (`site:hasRemainingAmmo()` is false).
- Create the IADS once and keep it in a guarded global (`State.iads = State.iads or create()`).

**Ground units.**
- A stationary unit within ~30 m of a red ammo truck (`Ural-375`, `Ural-4320-31`) rearms from about
  50 s after the truck appears: IRIS-T one missile per ~15 s, C-RAM ~68 rounds per 15 s.
- Several fully loaded short-range systems engaging at once (C-RAM 1,550 rounds plus IRIS-T 16
  missiles) froze DCS once. Stagger heavy engagements.

**The environment.**
- Stock Lua 5.1 (no yield across `pcall`). With the usual `MissionScripting.lua` edit only `io` and
  `lfs` are unlocked; `os`, `require` and `package` stay removed: no clock, no file rename or delete.
- `dofile` names a chunk with the plain path, no `@`.
- F10 menus show at most 10 entries per level and do not page; a 13th breaks the menu.
- `dcs.log` timestamps are UTC.
- Restart replays `%TEMP%\DCS\tempMission.miz`; only a fresh open reads a rebuilt `.miz`.
