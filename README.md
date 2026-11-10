# roles-assign

Which model does which job in a Claude Code setup, how work is handed from one role to another, and the skills that go with it. Everything here installs into `~/.claude`.

## What is in it

| File | Installs to | What it is |
|---|---|---|
| `agents/builder.md` | `~/.claude/agents/` | Sonnet 5.5: implements an approved plan step; edits the working tree only |
| `agents/reviewer.md` | `~/.claude/agents/` | Opus 5.5: independent review of a MEDIUM change; never edits |
| `agents/hard-reviewer.md` | `~/.claude/agents/` | Fable 5.2: the same review for HARD changes, by a different model from the one that wrote them |
| `agents/transcriber.md` | `~/.claude/agents/` | Haiku 5.5: mechanical copying and conversion only |
| `global/CLAUDE.md` | `~/.claude/CLAUDE.md`, between markers | Model economy, task rating (EASY / MEDIUM / HARD), the review loop, working practice, switching models, honesty |
| `global/settings-defaults.json` | `~/.claude/settings.json`, with `--settings` | The `enabledPlugins` and `skillOverrides` every machine shares |
| `skills/starter-kit/` | `~/.claude/skills/` | `/starter-kit`, run once per repo: `CLAUDE.md` from the template, git identity, only the plugins, MCP servers and skills the repo needs. Invoked by hand only |
| `skills/handoff/` | `~/.claude/skills/` | `/handoff`: `save` writes where the work stands to `HANDOFF.md` before `/clear`; `resume` reads it in the new session |
| `skills/market-research/` | `~/.claude/skills/` | Decision-oriented, source-traceable research on markets, competitors, pricing and vendors, with a positioning chart script |
| `skills/teardown/` | `~/.claude/skills/` | Decompose an existing product, write a clean-room spec, then build from the spec only |
| `skills/orca-worktree-setup/` | `~/.claude/skills/` | Setup scripts so every new Orca worktree gets the gitignored local files it needs |
| `skills/sdlc/` | `~/.claude/skills/` | The artifact chain intent, plan, build, verify, ship; a plan's `## Tasks` section feeds the builder's contract |
| `scripts/dispatch.py` | run from the repo | Writes a builder's worktree and task contract (`new`, `contract`, `show`, `done`) |
| `scripts/sdlc-check.py` | run from the repo | `clarify` fails while an intent has an open point; `converge` lists changed files outside the plan's tasks, tasks left untouched and Proof items without a result |
| `hooks/agent-guard.py`, `hooks/autonomous-settings.json`, `hooks/pin.json` | `~/.claude/hooks/1prompt/` | The hooks the builder and the reviewers run: a builder edits only inside its contract, the reviewers cannot change a tree. Copied from `ambysto/1prompt` at the commit `pin.json` names; never edited here |
| `guard/owner-token-guard.py` | `~/.claude/hooks/owner-token-guard/` | A PreToolUse hook for every session: denies a command that would take the owner's GitHub token or switch an account |
| `scripts/switch-test.py`, `switch-test/` | run from the repo | The model switch kit: recorded review cases, the blind runner, the runs and results, and the release-day checklist |
| `scripts/hil-report.py` | run from the repo | Reports the owner time log (`~/.claude/hil/log.jsonl`) |
| `scripts/github-boundary.py`, `.json` | run from the repo | The server-side boundary for paths only the owner changes |
| `intent/`, `docs/` | read | The intents and plans behind these files, review records and brand assets |
| `scripts/switch-model.py` | run from the repo | Moves one role to another model in one edit |
| `scripts/check.py`, `scripts/install.py` | run from the repo | The checks and the installer |

## Models

Every model is pinned to a full model ID, never an alias, so an upgrade is always a decision (`global/CLAUDE.md`, "Switching models"). The main session's model and effort live in `~/.claude/settings.json` (`"model": "claude-opus-5-5"`, and `high` effort under `modelSettings`). The installer only reports them; the owner sets them.

## Use

```sh
python3 scripts/check.py                 # exit 0 = PASS
python3 scripts/install.py               # copy agents and skills into ~/.claude (a differing file is backed up first)
python3 scripts/install.py --global      # also put global/CLAUDE.md into ~/.claude/CLAUDE.md, between markers
python3 scripts/install.py --settings    # also merge global/settings-defaults.json into settings.json
python3 scripts/install.py --check       # change nothing; exit 1 if the installed copy differs
```

The builder's task contract is enforced by `agent-guard`: an edit outside it is refused and a change outside it by any means locks the run. The main session also checks the diff with `sdlc-check.py converge` and reruns the contract's checks before review.

## Sources

`market-research` and `teardown` started from skills by Son Piaz (MIT, (c) 2026 Son Piaz; licence in `skills/LICENSE-adapted-skills`), then changed from real use.
