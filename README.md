# coding-playbook

Which model does which job in a Claude Code setup, how work is handed from one role to another, and the skills that go with it. Everything here installs into `~/.claude`.

## Roles and rules (`rores/`)

Which model does which job and the rules every session follows. Only `rores/` holds these; everything else here is tooling around them or a skill.

| File | Installs to | What it is |
|---|---|---|
| `rores/agents/builder.md` | `~/.claude/agents/` | Sonnet 5.5: implements an approved plan step; edits the working tree only |
| `rores/agents/reviewer.md` | `~/.claude/agents/` | Opus 5.5: independent review of a MEDIUM change; never edits |
| `rores/agents/hard-reviewer.md` | `~/.claude/agents/` | Fable 5.2: the same review for HARD changes, by a different model from the one that wrote them |
| `rores/agents/transcriber.md` | `~/.claude/agents/` | Haiku 5.5: mechanical copying and conversion only |
| `rores/global/CLAUDE.md` | `~/.claude/CLAUDE.md`, between markers | Model economy, task rating (EASY / MEDIUM / HARD), the review loop, working practice, switching models, honesty |
| `rores/global/settings-defaults.json` | `~/.claude/settings.json`, with `--settings` | The `enabledPlugins` and `skillOverrides` every machine shares |

## Skills (`skills/`)

Skills are separate from the roles: each folder is one skill, invoked by name or by hand, and installs on its own.

| File | Installs to | What it is |
|---|---|---|
| `skills/starter-kit/` | `~/.claude/skills/` | `/starter-kit`, run once per repo: `CLAUDE.md` from the template, git identity, only the plugins, MCP servers and skills the repo needs. Invoked by hand only |
| `skills/handoff/` | `~/.claude/skills/` | `/handoff`: `save` writes where the work stands to `HANDOFF.md` before `/clear`; `resume` reads it in the new session |
| `skills/agent-team/` | `~/.claude/skills/` | A one-approval run-to-done playbook: build, independent review, fix, merge, verify, with role agents across waves (hand-invoked in the defaults) |
| `skills/create-skill/` | `~/.claude/skills/` | Turn a recurring job into a skill from a one-page template, trial it, with an eval and a feedback log (hand-invoked in the defaults) |
| `skills/secrets/` | `~/.claude/skills/` | Keep API keys and passwords safe when delegating work to an agent, and push code to GitHub without leaking anything |
| `skills/whats-next/` | `~/.claude/skills/` | Triage the session: sweep for unfinished work, propose next steps and the dependencies of large changes; read and propose only |
| `skills/teardown/` | `~/.claude/skills/` | Decompose an existing product, write a clean-room spec, then build from the spec only |
| `skills/orca-worktree-setup/` | `~/.claude/skills/` | Setup scripts so every new Orca worktree gets the gitignored local files it needs |
| `skills/sdlc/` | `~/.claude/skills/` | The artifact chain intent, plan, build, verify, ship; a plan's `## Tasks` section feeds the builder's contract |

## Tooling, hooks and history

Run from the repo, or installed as hooks. None of it assigns a role.

| File | Installs to | What it is |
|---|---|---|
| `scripts/dispatch.py` | run from the repo | Writes a builder's worktree and task contract (`new`, `contract`, `show`, `done`) |
| `scripts/sdlc-check.py` | run from the repo | `clarify` fails while an intent has an open point; `converge` lists changed files outside the plan's tasks, tasks left untouched and Proof items without a result; `converge --checks` also runs each task's `check:` commands once nothing else is missing (the one-prompt loop's judge) |
| `hooks/agent-guard.py`, `hooks/autonomous-settings.json`, `hooks/pin.json` | `~/.claude/hooks/1prompt/` | The hooks the builder and the reviewers run: a builder edits only inside its contract, the reviewers cannot change a tree. Copied from `ambysto/1prompt` at the commit `pin.json` names; never edited here |
| `guard/owner-token-guard.py` | `~/.claude/hooks/owner-token-guard/` | A PreToolUse hook for every session: denies a command that would take the owner's GitHub token or switch an account |
| `saveit/saveit-hook.py` | `~/.claude/hooks/saveit/`, registered with `--settings` | Save-it hooks for every session: at SessionStart the `ambysto-saveit resume` brief when the repo root has a `HANDOFF.md`; at PreCompact `ambysto-saveit tail --write` into an existing, git-ignored `HANDOFF.md`. Never blocks a session |
| `scripts/plane.py` | run from the repo | Plane tickets over REST (`projects`, `show`, `create`, `state`, `comment`, `link`); the key is read at run time, sent only over https and never printed |
| `scripts/progress-diagram.py` | run from the repo | Draws a repo with `ambysto-graph` into its git folder: architecture, what the branch changed and, with `--plan`, the plan's tasks and proof items with their state |
| `graph/graph-hook.py` | `~/.claude/hooks/graph/`, registered with `--settings` | The session graph: when a session ends in a git work tree, refreshes `<git dir>/progress-diagram/overview.md` and `architecture.html` with `ambysto-graph` in the background (once, skipped when nothing changed, a failing tool keeps the old graph); when the next session starts, names them with the commit they were drawn at |
| `loop/loop.py`, `loop/loop-stop.py` | `loop.py` runs from the repo; `loop-stop.py` to `~/.claude/hooks/loop/`, registered with `--settings` | The one-prompt run: `loop.py start <plan>` opens a run for this session, `pass`/`fail` record review verdicts (the second FAIL of a task ends it), `ask`/`stop`/`resume`/`status`. The Stop hook keeps the session going until `sdlc-check.py converge --checks` finds nothing left, the tasks' checks pass and no proof is a FAIL; a SubagentStop hook records each reviewer's verdict for the task its prompt names (`loop task: T<n>`), which `pass` and done need; three failing check rounds or the time limit (`start --hours`, default 12) close the run, and a close that needs the owner is commented on the plan's Plane ticket; it never traps a session on an error, never reads a judge crash as done, and closes after 3 stops with no change or 40 stops held |
| `loop/loop-wake.py` | `~/.claude/hooks/loop/`; its timer with `python3 ~/.claude/hooks/loop/loop-wake.py install` | Wakes a one-prompt run whose session died (crash, quota, closed window): every 10 min a run quiet for 30 min is forked headless with `claude -p --resume … --fork-session` under 1prompt's boundary settings, in the mode the Stop hook recorded; at most 4 wakes per run, $20 reserved per wake and $50 a day, each wake and cap commented on the plan's Plane ticket; `tick --dry-run` shows what it would do |
| `scripts/switch-test.py`, `switch-test/` | run from the repo | The model switch kit: recorded review cases, the blind runner, the runs and results, and the release-day checklist |
| `gates/session-gates.py` | `~/.claude/hooks/gates/`, registered with `--settings` | Session gates for rules that slipped as text: refuses a branch name a repo's `.claude/branch-name.json` does not allow and a push to a branch it lists in `no_push`, refuses an edit or a changing git command in a tree a still-running subagent has read, and names a shared-memory lesson once when a command matches it |
| `scripts/hil-report.py` | run from the repo | Reports the owner time log (`~/.claude/hil/log.jsonl`) |
| `scripts/cost-report.py`, `scripts/model-prices.json` | run from the repo | What each agent role, ticket, model, day or project costs, from Claude Code's own transcripts in `~/.claude/projects` (`--by role\|ticket\|model\|day\|project`, several for a nested grouping; `--since`, `--until`, `--project`, `--ticket`, `--json`). Each API response counted once; USD from the price table beside it (a model not in the table shows `?`, never a guess); the share with no ticket is always shown. `--self-test` builds its own scratch transcripts |
| `scripts/sync-public.py`, `.sync-source.json` | (the maintainer's tool) | How this repo is kept in step with the maintainer's internal copy: every file comes from there except this repo's own `CLAUDE.md`, `README.md` and `.claude/branch-name.json`; `.sync-source.json` records which internal commit each was last brought in step with. Its config lives only in the internal copy, so here it only runs `--self-test` |
| `scripts/github-boundary.py`, `.json` | run from the repo | The server-side boundary for paths only the owner changes |
| `intent/`, `docs/` | read | The intents and plans behind these files, review records and brand assets |
| `scripts/switch-model.py` | run from the repo | Moves one role to another model in one edit |
| `scripts/check.py`, `scripts/install.py` | run from the repo | The checks and the installer |

## Models

Every model is pinned to a full model ID, never an alias, so an upgrade is always a decision (`rores/global/CLAUDE.md`, "Switching models"). The main session's model and effort live in `~/.claude/settings.json` (`"model": "claude-opus-5-5"`, and `high` effort under `modelSettings`). The installer only reports them; the owner sets them.

## Use

```sh
python3 scripts/check.py                 # exit 0 = PASS
python3 scripts/install.py               # copy agents and skills into ~/.claude (a differing file is backed up first)
python3 scripts/install.py --global      # also put rores/global/CLAUDE.md into ~/.claude/CLAUDE.md, between markers
python3 scripts/install.py --settings    # also merge rores/global/settings-defaults.json and register the session hooks in settings.json
python3 scripts/install.py --check       # change nothing; exit 1 if the installed copy differs
```

The builder's task contract is enforced by `agent-guard`: an edit outside it is refused and a change outside it by any means locks the run. The main session also checks the diff with `sdlc-check.py converge` and reruns the contract's checks before review.

## Sources

`teardown`, `sdlc`, `agent-team`, `create-skill`, `secrets` and `whats-next` started from skills by Son Piaz (MIT, (c) 2026 Son Piaz; licence in `skills/LICENSE-adapted-skills`), then changed from real use.
