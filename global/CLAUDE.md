# Global Claude Code instructions (install into ~/.claude/CLAUDE.md, applies to every project)

## Model economy
The main session runs the model with the best quality per cost for deciding, rating, gating and HARD work. It decides, rates each task, dispatches, gates, commits, merges and talks to me.
**Current choice (2026-11-10): Opus 5.5.** Fable 5.2 (owner decision 2026-11-10) as hard-reviewer. The switch test was skipped for Fable 5.2 by the owner's decision, so the main session was not re-compared with it. Revisit the next time a model ships, by the switch test below.

Where each setting lives (CLAUDE.md only records the choice; it cannot set a model):
- Main session model: `"model"` in `~/.claude/settings.json`, as a full model ID (`claude-opus-5-5`), never an alias, so an upgrade is always a decision.
- Effort: `modelSettings.<model id>.effortLevel` in `~/.claude/settings.json` for the main session (Opus 5.5: `high`, owner decision 2026-11-08); `effort:` in each agent file for subagents (builder, reviewers `high`, transcriber `low`). Set once per session, never changed mid-session.
- Subagent models: `model:` in each agent file, pinned to full model IDs. They change together with the main session, in one edit.

Subagents (in `~/.claude/agents/`; a project's `.claude/agents/` overrides them):
- **builder** (Sonnet 5.5): implements an approved plan step. Edits the working tree only.
- **reviewer** (Opus 5.5): independent review of a MEDIUM diff; returns PASS/FAIL with numbered issues. Never edits.
- **hard-reviewer** (Fable 5.2): the same review for HARD changes. A different model from the one that wrote the change, so it does not share its blind spots.
- **transcriber** (Haiku 5.5): mechanical copying and conversion only, no judgment.

Subagents return concise summaries, never full file dumps: builder and transcriber at most 200 words (the builder's contract check commands not counted), reviewers at most 300 (500 for a HARD change).
Small tasks (1-2 files, obvious change) are done directly, not dispatched.

## Task rating (do this before dispatching)
Rate on four axes: ambiguity, coupled decisions, verifiability, cost of error.
- All low → **EASY**: transcriber or builder, no review.
- One high → **MEDIUM**: builder, then reviewer.
- Two or more high, **or** an error could lose user data, break security, move money or cannot be undone → **HARD**: the main session does it directly, then hard-reviewer reviews it.
Each project's CLAUDE.md lists its own HARD / MEDIUM / EASY examples; those override this default.

## The loop
- Every builder dispatch carries a task contract, written with `scripts/dispatch.py` in the roles-assign repo: `new <repo> <branch> --allow … --check …` gives a builder that runs beside another its own worktree and contract; `contract <tree> --allow … --check …` serves a single builder in the main checkout. The builder edits only inside the contract and names every check in its report. Nothing blocks a write, so the main session reruns the contract's checks as its gate before review, judges an `OUTSIDE CONTRACT` report before anything else, and runs `dispatch.py done <tree>` when the work is committed.
- When the plan has a `## Tasks` section (the sdlc skill), a builder's contract comes from its task: `dispatch.py new <repo> <branch> --task <plan> <id>` (or `contract <tree> --task …`), not from flags typed again.
- Before the review of a plan's build, `scripts/sdlc-check.py converge <plan>` lists every changed file outside the plan's tasks, every task left untouched and every Proof item without a result; the reviewer gets its output with the diff. `sdlc-check.py clarify <intent>` fails while an intent still has an open point.
- The reviewer gets the task and the diff, not the builder's or the main session's summary.
- On FAIL: the builder (MEDIUM) or the main session (HARD) fixes from the numbered issue list, at most 2 rounds; then stop and ask me.
- A BLOCKER or MAJOR issue is never waived silently: fix it, or ask me.
- Only the main session commits, pushes, opens or merges PRs, and updates the issue tracker. It merges only when I ask.

## Working practice (guidance from lessons that held in more than one context; not gates)
- After any subagent has run, check the branch in the same command as a commit, amend or reset; agents share the working tree and can switch it.
- Give each agent that runs at the same time its own worktree. Never edit a worktree while an agent is running in it: it may stage everything there.
- After stopping an agent, look for processes it started that outlive it.
- Before a merge, run the project's whole Verify on that branch, not only the suite for the part that changed.
- After a merge or rebase, check `git status` for unmerged paths before committing.
- End every finished task, and every session, with the same short summary so the owner never has to ask "done?": what changed and its PR or commit, pushed or not, merged or not (and who merges), worktree clean or what is left uncommitted, checks run and "not run: <reason>" for the rest, and what waits for the owner.
- An installer or update proof also installs over the previous build, not only on a clean machine.
- Never edit a shell script while it is running; write the new version beside it and swap it in afterwards.
- Run a heavy job (benchmark, large test suite, indexing, parallel build) under its own memory cap: `systemd-run --user --scope -p MemoryMax=<N>G <command>`. Over the cap only that job is killed.

## Switching models (when a new model ships)
1. Pick 2-3 past diffs whose review findings are on record (review logs, PR comments), including at least one HARD change.
2. Run the candidate as reviewer on each diff, without the old findings. Count the known issues it catches, the new real issues it finds, the false alarms, and the cost.
3. Switch only if it catches at least as many known issues at an acceptable cost. Then change `settings.json`, the effort entry and every agent file in one edit, and update the "Current choice" line with the date and the numbers (`scripts/switch-model.py` in the roles-assign repo makes the repo's part of that edit in one command).

## Honesty
- Never report a check as passing that was not run. Write "not run: <reason>" (wrong OS, owner-only step, missing credentials).
- Never silently change a threshold, default, data format, public API or protected list. Flag it and ask.
- When a project has no CLAUDE.md with Verify, Rules and the HARD / MEDIUM / EASY lists, propose one from the project template before the first MEDIUM task.
