# roles-assign

The `/starter-kit` skill for Claude Code: run once per repo to keep sessions small. It writes a short `CLAUDE.md` from a template, sets the git identity, turns on only the plugins, MCP servers and skills the repo needs, gitignores `HANDOFF.md`, and creates a tracker project if you want one.

## Layout

| File | What it is |
|---|---|
| `skills/starter-kit/SKILL.md` | The skill. Invoked by hand only, so it costs no context. |
| `skills/starter-kit/context-config.md` | What each turn carries and how to turn things off globally and per repo. |
| `skills/starter-kit/project-CLAUDE.md` | The `CLAUDE.md` template the skill fills in. |

## Install

```sh
git clone https://github.com/0xdonniechu/roles-assign.git ~/work/0xdonniechu/roles-assign
ln -sfn ~/work/0xdonniechu/roles-assign/skills/starter-kit ~/.claude/skills/starter-kit
```

Open a new Claude Code session, then run `/starter-kit` inside a repo.
