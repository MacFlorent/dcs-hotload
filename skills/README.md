# Claude Code skills (optional)

Skills that teach Claude Code to work with dcs-hotload. dcs-hotload works without them.

| Skill | Teaches |
|---|---|
| `piloting-dcs-hotload/` | driving a running mission: sending commands with `bin/hotload.sh`, checking which code is live, and writing live-mission Lua that avoids known DCS traps |

## Install for one mission

Copy a skill folder into the mission's `.claude/skills/`, next to the mission's `dcs-hotload/`:

```
<mission>/
  dcs-hotload/                         this tool
  .claude/skills/piloting-dcs-hotload/ copied from dcs-hotload/skills/piloting-dcs-hotload/
```

From Git Bash, in the mission folder:

```bash
mkdir -p .claude/skills && cp -r dcs-hotload/skills/piloting-dcs-hotload .claude/skills/
```

Start Claude Code in the mission folder: the skill loads with the session. It runs
`dcs-hotload/bin/hotload.sh` relative to that folder, so the mission must have hotload at
`dcs-hotload/`.

## Updating

The copy does not follow the repository. After updating `dcs-hotload/`, copy the skill again.
