# coding-playbook: which model does which job in Claude Code, and the skills and scripts that go with it

## What it does
The four subagents (builder, reviewer, hard-reviewer, transcriber), the global instructions, nine skills (`starter-kit`, `handoff`, `sdlc`, `teardown`, `orca-worktree-setup`, `agent-team`, `create-skill`, `secrets`, `whats-next`), the builder dispatch and sdlc check scripts, a one-command model switch and the switch test kit, the agent-guard hooks, the owner-token guard and the save-it hooks, the Plane and progress-diagram scripts, the one-prompt loop (`loop/loop.py` and its Stop hook), the session graph hook, the session gates, the owner time log report, the cost report, plus a check script and an installer. Standard library Python only. Every session on every machine follows these files, so a wrong rule rates HARD work as EASY or lets an unreviewed change through.

## Verify
- `python3 scripts/check.py`: agent frontmatter and pinned models, `hard-reviewer` body equal to `reviewer` body, `rores/global/CLAUDE.md` matches the pins, the starter-kit template's sections, skill frontmatter, `settings-defaults.json`, and the self-tests of `dispatch.py`, `sdlc-check.py`, `switch-model.py`, `saveit/saveit-hook.py`, `plane.py`, `progress-diagram.py`, `graph/graph-hook.py` (a fake `ambysto-graph` and `systemd-run` on a scratch repo: refresh, skip with no change, lock, failing or killed jobs keeping the old graph, the start lines), `loop/loop.py` and `loop/loop-stop.py` (the run file and the Stop hook on scratch repos and plans: gaps and failing checks block, reviewer verdicts recorded and required, done, two fails, three check rounds, idle, the time limit, the ticket comment, never trapping a session), `scripts/cost-report.py` and `scripts/sync-public.py` (scratch transcripts and scratch repos), `loop/loop-wake.py --self-test` (a fake `claude`, `systemd-run`, `systemctl` and `plane.py` in a scratch HOME: a dead quiet run woken once and bound to the fork, every reason not to wake, each cap closing the run, the spend ledger, the timer install), plus `install.py --settings` registering the session hooks once each and a refusal writing nothing (scratch HOMEs).
- `HOME=$(mktemp -d) python3 scripts/install.py` then `--check` under the same `HOME`: installs and reports no drift, without touching `~/.claude`.
- A change to an agent's behaviour: start a new session, run the agent once on a known diff, and record what it returned in the PR.
- A change to a skill's steps: run it once in a fresh agent on a scratch repo, given only the skill, and record where it had to guess.

## HARD: the main session does it directly, then hard-reviewer
Rated by undo cost (global "Task rating", owner decision 2026-11-11): HARD here is what no revert undoes (a guard that let something through, money spent, something published, a setting the installer spread to every machine) and any change of a rule (what the global block, a skill's steps or an agent's instructions tell a session to do or not do). Read an item's section in `docs/internals.md` before changing it.
- The model choice and switching: the "Current choice" line, any agent's `model:` or `effort:`, `scripts/switch-model.py`.
- Task rating (EASY / MEDIUM / HARD), the review loop, who may commit or merge, the honesty rules.
- The reviewers' checklist and their PASS/FAIL rule.
- `scripts/dispatch.py`: the task contract a builder works to, which `hooks/agent-guard.py` enforces, and the task parser in `scripts/sdlc-check.py` that `--task` reads it from.
- `loop/loop.py` and `loop/loop-stop.py`: the one-prompt run, its evidence-based done and verdicts per task.
- `loop/loop-wake.py`: waking a dead run under spend caps.
- `gates/session-gates.py` and `.claude/branch-name.json`: the session gates (branch names, trees a running subagent read, lesson recall); a gate that wrongly allows lets the slip through, one that wrongly refuses stalls every session.
- The installer's writes to `~/.claude` (backups, the marker block, which also takes over a block left by an earlier `coding-playbook` or `claudecode-guide` install, skill folders, `hooks/saveit`, `hooks/loop`, `hooks/graph` and `hooks/gates`, and with `--settings` the entries of `rores/global/settings-defaults.json` and the session hook entries in `settings.json` (PreToolUse, SessionStart, PreCompact, Stop, SubagentStop, SessionEnd; an entry already there is brought to this repo's timeout), each appended once beside any other hooks; it never sets the model and never deletes).

## MEDIUM: builder builds, reviewer reviews
- Builder and transcriber wording that changes what they do or when they stop; the template's sections; a skill's steps or stop points; `scripts/check.py`; `scripts/sdlc-check.py`.
- Shortening or rewording `rores/global/CLAUDE.md` or a skill without changing a rule: the reviewer compares the old and new text rule by rule; a rule found changed makes the change HARD.
- `graph/graph-hook.py` (the session graph): it must never block or break a session (exit 0, `|| true`) and writes only under `<git dir>/progress-diagram/`.
- `docs/internals.md`, `scripts/plane.py`, `scripts/progress-diagram.py`, `scripts/hil-report.py`, `scripts/cost-report.py`.

## EASY: transcriber or builder, no review
- README wording, typos, examples that do not change a rule, intent and plan status lines that record work done.

## Rules
- Models are pinned to full model IDs (`claude-opus-5-5`), never aliases. A model change edits every agent file, the "Current choice" line and the README in one PR (`scripts/switch-model.py` does it in one command).
- The body of `hard-reviewer.md` is the body of `reviewer.md`: edit `reviewer.md`, then copy its body; `check.py` fails otherwise.
- Universal only: no project's paths, commands or names in `rores/agents/`, `rores/global/` or `skills/`. Three exceptions: `rores/global/CLAUDE.md` names this repo's own folder (`~/work/0xdonniechu/coding-playbook`) where it points at `dispatch.py`, `hil-report.py`, `loop/loop.py`, `progress-diagram.py`, `plane.py` and the switch-test kit; its Tools section names the owner's local tools (`ambysto-saveit`, `ambysto-graph`, Plane, `ambysto-1prompt`'s design) because every session needs to know them (owner instruction 2026-11-10: load the existing tools, one step at a time); it tells a session to skip a tool that is not installed; and "The loop" names `ambysto-memory` and `ambysto-1prompt` as the repos where GitHub keeps merges with the owner.
- Nothing secret: no keys, tokens, hosts or ids.
- Synced from the internal copy (owner decision 2026-11-11): every file except this `CLAUDE.md`, `README.md`, `.claude/branch-name.json` and `.sync-source.json` comes from the maintainer's internal repo through `scripts/sync-public.py`, on a `feat/` branch, after a leak check and a read of the whole diff. Change those files there, not here: a change made only here is overwritten by the next sync. The three files of this repo's own are brought in step by hand when the sync reports them.
- The builder's task contract is enforced by `hooks/agent-guard.py`. The main session still reruns the contract's checks and runs `sdlc-check.py converge` before review.
- `hooks/agent-guard.py` and `hooks/autonomous-settings.json` are copied from `ambysto/1prompt` at the commit `hooks/pin.json` names: change them there, copy them here, update the pin.
- Git: English only; the `0xdonniechu` account (check with `gh api user --jq .login` before the first PR of a session; do not switch accounts); branches `feat/...` or `fix/...`, never a push to `main`; only the main session commits, pushes, opens and merges PRs: this repo is public, so a merge publishes to its readers; it merges on its own under the global rule (owner decision 2026-11-11: the public copy is kept in step without asking) once the whole Verify passed on the branch and the review passed (a change of model, rating or review rule needs the owner's approval first), then deletes the branch and its worktree (owner decision 2026-11-11).

## Read when
- Changing a hook or script in the HARD list: its section in `docs/internals.md` first (how it works inside, its limits).
- Changing the switch script: `scripts/switch-model.py --self-test` runs it on a scratch copy of this repo.
- Adding a skill: add its name to `SKILLS` in `scripts/check.py`.

## Session state
`HANDOFF.md` (gitignored) holds only where the current goal stands. Plans, decisions and dead ends go in files, not in the chat.

## Open
- The switch-test cases and replays are diffs from `ambysto/coding-playbook`; their runner needs a clone of it at `~/work/ambysto/coding-playbook`. Keep that clone, or the kit cannot replay them.
- `intent/` and `docs/` are the history of these files as they were made in `coding-playbook`.
