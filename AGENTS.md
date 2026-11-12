# coding-playbook: which model does which job in Claude Code, Codex & Antigravity, and the skills and scripts that go with it

## What it does
The subagent roles (builder, reviewer, hard-reviewer, transcriber), the global instructions, nine skills (`starter-kit`, `handoff`, `sdlc`, `teardown`, `orca-worktree-setup`, `agent-team`, `create-skill`, `secrets`, `whats-next`), the builder dispatch and sdlc check scripts, a one-command model switch and the switch test kit, the agent-guard hooks, the owner-token guard and the save-it hooks, the Plane and progress-diagram scripts, the one-prompt loop (`loop/loop.py` and its Stop hook), the session graph hook, the session gates, the owner time log report, the cost report, plus a check script and an installer. Standard library Python only. Every session on every machine follows these files, so a wrong rule rates HARD work as EASY or lets an unreviewed change through.

## Verify
- `python3 scripts/check.py`: agent frontmatter and pinned models, `hard-reviewer` body equal to `reviewer` body, `rores/global/CLAUDE.md` matches the pins, the starter-kit template's sections, skill frontmatter, `settings-defaults.json`, and the self-tests of `dispatch.py`, `sdlc-check.py`, `switch-model.py`, `saveit/saveit-hook.py`, `plane.py`, `progress-diagram.py`, `graph/graph-hook.py`, `loop/loop.py` and `loop/loop-stop.py`, `scripts/cost-report.py` and `scripts/sync-public.py`, `loop/loop-wake.py --self-test`, plus `install.py --settings`.
- `HOME=$(mktemp -d) python3 scripts/install.py` then `--check` under the same `HOME`: installs and reports no drift, without touching `~/.claude`.

## HARD: the main session (`gpt-6.1-sol`, `high`) does it directly, then hard-reviewer (`gpt-6-astra`, `high`)
- The model choice and switching: the "Current choice" line, any agent's `model:` or `effort:`, `scripts/switch-model.py`.
- Task rating (EASY / MEDIUM / HARD), the review loop, who may commit or merge, the honesty rules.
- The reviewers' checklist and their PASS/FAIL rule.
- `scripts/dispatch.py`, `hooks/agent-guard.py`, and the task parser in `scripts/sdlc-check.py`.
- `loop/loop.py`, `loop/loop-stop.py`, and `loop/loop-wake.py`.
- `gates/session-gates.py` and `.claude/branch-name.json`.
- The installer's writes to `~/.claude`, `~/.codex`, and `~/.gemini`.

## MEDIUM: builder (`gpt-6.1-terra`, `high`) builds, reviewer (`gpt-6.1-sol`, `high`) reviews
- Builder and transcriber wording that changes what they do or when they stop; the template's sections; a skill's steps or stop points; `scripts/check.py`; `scripts/sdlc-check.py`.
- Shortening or rewording global instructions or a skill without changing a rule.
- `graph/graph-hook.py`, `docs/internals.md`, `scripts/plane.py`, `scripts/progress-diagram.py`, `scripts/hil-report.py`, `scripts/cost-report.py`.

## EASY: transcriber (`gpt-6-luna`, `low`) or builder (`gpt-6.1-terra`), no review
- README wording, typos, examples that do not change a rule, intent and plan status lines that record work done.

## Rules
- Follow all rules in [CLAUDE.md](CLAUDE.md) (pinned model IDs, `reviewer.md` / `hard-reviewer.md` body parity, universal paths, no secrets, `sync-public.py` flow, `0xdonniechu` git identity).

## Session state
`HANDOFF.md` (gitignored) holds only where the current goal stands. Plans, decisions and dead ends go in files, not in the chat.
