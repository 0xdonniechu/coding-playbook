# roles-assign: which model does which job in Claude Code, and the skills and scripts that go with it

## What it does
The four subagents (builder, reviewer, hard-reviewer, transcriber), the global instructions, nine skills (`starter-kit`, `handoff`, `sdlc`, `teardown`, `orca-worktree-setup`, `agent-team`, `create-skill`, `secrets`, `whats-next`), the builder dispatch and sdlc check scripts, a one-command model switch and the switch test kit, the agent-guard hooks and the owner-token guard, the owner time log report, plus a check script and an installer. Standard library Python only. Every session on every machine follows these files, so a wrong rule rates HARD work as EASY or lets an unreviewed change through.

## Verify
- `python3 scripts/check.py`: agent frontmatter and pinned models, `hard-reviewer` body equal to `reviewer` body, `rores/global/CLAUDE.md` matches the pins, the starter-kit template's sections, skill frontmatter, `settings-defaults.json`, and the self-tests of `dispatch.py`, `sdlc-check.py` and `switch-model.py`.
- `HOME=$(mktemp -d) python3 scripts/install.py` then `--check` under the same `HOME`: installs and reports no drift, without touching `~/.claude`.
- A change to an agent's behaviour: start a new session, run the agent once on a known diff, and record what it returned in the PR.
- A change to a skill's steps: run it once in a fresh agent on a scratch repo, given only the skill, and record where it had to guess.

## HARD: the main session does it directly, then hard-reviewer
- The model choice and switching: the "Current choice" line, any agent's `model:` or `effort:`, `scripts/switch-model.py`.
- Task rating (EASY / MEDIUM / HARD), the review loop, who may commit or merge, the honesty rules.
- The reviewers' checklist and their PASS/FAIL rule.
- `scripts/dispatch.py`: the task contract a builder works to, which `hooks/agent-guard.py` enforces, and the task parser in `scripts/sdlc-check.py` that `--task` reads it from.
- The installer's writes to `~/.claude` (backups, the marker block, which also takes over a block left by an earlier `coding-playbook` or `claudecode-guide` install, skill folders, and with `--settings` the entries of `rores/global/settings-defaults.json`; it never sets the model and never deletes).

## MEDIUM: builder builds, reviewer reviews
- Builder and transcriber wording that changes what they do or when they stop; the template's sections; a skill's steps or stop points; `scripts/check.py`; `scripts/sdlc-check.py`.

## EASY: transcriber or builder, no review
- README wording, typos, examples that do not change a rule.

## Rules
- Models are pinned to full model IDs (`claude-opus-5-5`), never aliases. A model change edits every agent file, the "Current choice" line and the README in one PR (`scripts/switch-model.py` does it in one command).
- The body of `hard-reviewer.md` is the body of `reviewer.md`: edit `reviewer.md`, then copy its body; `check.py` fails otherwise.
- Universal only: no project's paths, commands or names in `rores/agents/`, `rores/global/` or `skills/`.
- Nothing secret: no keys, tokens, hosts or ids.
- The builder's task contract is enforced by `hooks/agent-guard.py`. The main session still reruns the contract's checks and runs `sdlc-check.py converge` before review.
- `hooks/agent-guard.py` and `hooks/autonomous-settings.json` are copied from `ambysto/1prompt` at the commit `hooks/pin.json` names: change them there, copy them here, update the pin.
- Git: English only; the `0xdonniechu` account (check with `gh api user --jq .login` before the first PR of a session; do not switch accounts); branches `feat/...` or `fix/...`, never a push to `main`; only the main session commits, pushes and opens PRs, and it merges only when the owner asks.

## Read when
- Changing the switch script: `scripts/switch-model.py --self-test` runs it on a scratch copy of this repo.
- Adding a skill: add its name to `SKILLS` in `scripts/check.py`.

## Session state
`HANDOFF.md` (gitignored) holds only where the current goal stands. Plans, decisions and dead ends go in files, not in the chat.

## Open
- The switch-test cases and replays are diffs from `ambysto/coding-playbook`; their runner needs a clone of it at `~/work/ambysto/coding-playbook`. Keep that clone, or the kit cannot replay them.
- `intent/` and `docs/` are the history of these files as they were made in `coding-playbook`.
