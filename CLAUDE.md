# dcs-hotload — Claude Code instructions

> One Lua 5.1 file (`dcs-hotload.lua`) that runs Lua inside a live DCS World mission from the F10
> menu or a file mailbox, plus a shell client (`bin/hotload.sh`). Missions copy it; nothing is
> built.

**`CONTRIBUTING.md` is the guide, and its steps for a change are mandatory.** Read them before
starting a change, and again after a context compaction: this file is the only one that stays
loaded.

## Never

- **Use `os`, `require` or `package` in `dcs-hotload.lua`.** DCS removes them from the mission
  environment; only `io` and `lfs` are unlocked.
- **Yield across a `pcall`** in `dcs-hotload.lua`: DCS runs stock Lua 5.1.
- **Commit directly to `main`**, except a change confined to `.tracker/`. Branch as `<type>/<slug>`.
- **Merge a pull request** unless asked to.
- **"Fix" the broken scripts in `examples/`** (`syntax-error.lua`, `runtime-error.lua`, the load
  cycle): they are self-tests of how hotload reports failures.
- **Change the mailbox format or `Hotload.*` incompatibly** without a major version: other tools
  depend on them.

## Commands

```
lua5.1 test/run.lua        # the offline suite; a name filters
bash .github/scripts/lint.sh   # luacheck at its pinned version, as CI runs it
```

On Windows without `lua5.1` on `PATH`: `"/c/Program Files (x86)/Lua/5.1/lua.exe" test/run.lua`.

## Workflow

- When only DCS can show whether a change works, stop and ask the user to try it in-game.
- Specs and plans written while planning go to `.drafts/` (git-ignored). What is worth keeping
  becomes a spec in `.tracker/`.

## Before you do these, read

| About to… | Read |
|---|---|
| change `dcs-hotload.lua` or `bin/hotload.sh` | `CONTRIBUTING.md` — test first, changelog |
| add or change a test | `CONTRIBUTING.md`; `test/dcs-stub.lua` |
| open a pull request, or open, update or archive a piece of work | `CONTRIBUTING.md` |
| edit a guidance file | `CONTRIBUTING.md` — how guidance is written |
| cut a release, or change what a release ships | `CONTRIBUTING.md` |
