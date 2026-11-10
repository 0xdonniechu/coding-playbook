# Global Claude Code instructions (install into ~/.claude/CLAUDE.md, applies to every project)

## Model economy
The main session runs the model with the best quality per cost for deciding, rating, gating and HARD work. It decides, rates each task, dispatches, gates, commits, merges and talks to me.
**Current choice (2026-10-16): Opus 5.5.** On cost/quality it is ahead of Fable 5.1. Revisit when the next model ships, by the switch test below.
Switch (2026-11-10): hard-reviewer → Fable 5.2 (`claude-fable-5-2`); owner decision, the switch test was skipped, so the main session was not re-compared with Fable 5.2

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
- Every builder dispatch carries a task contract, written with `scripts/dispatch.py` in the coding-playbook repo (`~/work/0xdonniechu/coding-playbook`): `new <repo> <branch> --allow … --check …` gives a builder that runs beside another its own worktree and contract; `contract <tree> --allow … --check …` serves a single builder in the main checkout. agent-guard refuses the builder's writes outside the contract (and all writes without one) and locks the run when anything changes outside it. The main session reruns the contract's checks as its gate before review, judges an `OUTSIDE CONTRACT` report before anything else, and runs `dispatch.py done <tree>` when the work is committed.
- When the plan has a `## Tasks` section (the sdlc skill), a builder's contract comes from its task: `dispatch.py new <repo> <branch> --task <plan> <id>` (or `contract <tree> --task …`), not from flags typed again.
- Before the review of a plan's build, `scripts/sdlc-check.py converge <plan>` lists every changed file outside the plan's tasks, every task left untouched and every Proof item without a result; the reviewer gets its output with the diff. `sdlc-check.py clarify <intent>` fails while an intent still has an open point.
- The reviewer gets the task and the diff, not the builder's or the main session's summary.
- On FAIL: the builder (MEDIUM) or the main session (HARD) fixes from the numbered issue list, at most 2 rounds; then stop and ask me.
- A BLOCKER or MAJOR issue is never waived silently: fix it, or ask me.
- Only the main session commits, pushes, opens or merges PRs, and updates the issue tracker. It merges only when I ask.

## Owner time log
- The main session (never a subagent) appends one line to `~/.claude/hil/log.jsonl` (create the folder if it is missing) each time the owner steps in, at the time it happens. One line per owner message, a plain "ok", "continue" or "wait" included; give it one `kind`, the main one when several apply. A headless run (`claude -p`, a scheduled or scripted run, a test session) has no owner at the keyboard and never writes this log; its prompt is not an owner message (lesson 2026-10-22: two test runs each wrote a fake owner line).
- Line: `{"ts":"2026-10-18T14:05Z","project":"<repo name, or the shared effort's short name>","task":"<ticket id, or a short slug when there is none>","kind":"…","trigger":"…","note":"<one line, no secrets>"}`. `ts` is UTC and ends in `Z`. Add `"minutes": <number>` only when the owner says how long it took.
- `kind`, by design: `decision` (the owner answers a question about what to build or how), `approval` (the owner accepts an intent, plan or change as written), `merge` (the owner asks to commit, push, merge or tag), `direction` (the owner brings new scope or steering nobody asked for). To reduce: `setup` (an owner-only step: sign-in, token, device), `incident` (something broken), `unblock` (the agent had stopped and needed a nudge), `status` (the owner had to ask where things stand).
- `trigger`: `agent-asked` when the session asked the owner (a question, a request for approval, an owner-only step), `owner` when the owner started it. A reply to a question is `agent-asked`, even when it also adds steering.
- An incident the owner noticed first (`incident`, `owner`) is the signal that matters. After the fix, ask whether a gate would have caught it. If the lesson holds only for that project, it goes in the project's CLAUDE.md. If it holds across projects, propose it for the working practice below. Either way it is guidance first, and becomes a gate only when the project decides so.
- The report: `python scripts/hil-report.py [--since YYYY-MM-DD] [--project P]` in the coding-playbook repo (`~/work/0xdonniechu/coding-playbook`).

## Shared memory
Ambysto repos share one owner-reviewed memory in `~/work/ambysto/ambysto-memory` (its `AGENTS.md` says how to use it). Do not use Claude Code's per-folder auto-memory (turn it off with `"autoMemoryEnabled": false` in `~/.claude/settings.json`).
- Before non-trivial work, and when a command fails in a way that may have a known fix: if the clone is on `main`, run `git -C ~/work/ambysto/ambysto-memory pull --ff-only` (on another branch, offline, or when a sandbox refuses the pull, read it as it is and say so); read its `INDEX.md`; open the lessons whose line matches the task.
- When a lesson changes what you do, name it in one line. If a lesson conflicts with the owner or the project's own docs, follow those and say so.
- To add or change a lesson (something learned that a later session needs), draft it on a branch there and open a PR, as its `AGENTS.md` says; the owner's merge is the approval. Never merge it yourself.

## Working practice (guidance from lessons that held in more than one context; not gates)
- After any subagent has run, check the branch in the same command as a commit, amend or reset; agents share the working tree and can switch it.
- Give each agent that runs at the same time its own worktree (`dispatch.py new` for builders). Never edit a worktree while an agent is running in it: it may stage everything there.
- After stopping an agent, look for processes it started that outlive it.
- Before a merge, run the project's whole Verify on that branch, not only the suite for the part that changed.
- After a merge or rebase, check `git status` for unmerged paths before committing.
- End every finished task, and every session, with the same short summary so the owner never has to ask "done?": what changed and its PR or commit, pushed or not, merged or not (and who merges), worktree clean or what is left uncommitted, ticket updated or not, checks run and "not run: <reason>" for the rest, and what waits for the owner (lesson 2026-10-23: about 12 of 22 owner status questions in one day were "done?", "what remains?", "anything uncommitted?").
- An installer or update proof also installs over the previous build, not only on a clean machine.
- When the owner says "it worked before", first compare their path with the tested one (upgrade or clean install, machine, account) before blaming their setup.
- Never edit a shell script while it is running; write the new version beside it and swap it in afterwards.
- A shared test machine (VM, device) is stopped, restarted or restored only while holding every lock its job runners take, so no other session's running job is cut; check for running jobs first and stop if any is found, never chain the stop after the check (lesson 2026-10-20: a stop for a snapshot cut another session's console job).
- Run a heavy job (benchmark, large test suite, indexing, parallel build) under its own memory cap: `systemd-run --user --scope -p MemoryMax=<N>G <command>`. Over the cap only that job is killed; without it, systemd-oomd kills the whole terminal host and every session in it (lesson 2026-10-22: one runaway test in a benchmark job pushed memory pressure past 50% and oomd killed the terminal host with all sessions).
- One hosting login per org: before any deploy, check that the project's link (Vercel `.vercel/project.json` `orgId`) is the repo's own org, and deploy production once when the work is done or let git deploy on merge, never after every edit (lesson 2026-10-22: two agents deployed another org's site into the Ambysto Vercel team 64 times in a day, 30 of them from one unchanged commit, and used up its 100/day limit).

## Tools on this machine (main session only; skip a tool that `command -v` does not find)
- **Resume** (`ambysto-saveit`): at the start of a session with a `HANDOFF.md`, or after one died (crash, HTTP 429), `ambysto-saveit resume` gives a short brief of that file and the work tree; still read `HANDOFF.md` itself. The newest transcript is this session's own, so pass the dead session's file as `--transcript <old.jsonl>` to see its tail. `tail --write` and `dead-end "<entry>"` write `HANDOFF.md` into the work tree: it must be gitignored, and the tail copies commands as typed, so check it for keys. `ambysto-saveit gate -- <cmd>` runs a noisy suite quietly (the command runs without a shell: no `&&`).
- **Orientation and diagrams** (`ambysto-graph`, local): `overview --dir <repo>` to orient in a repo you do not know (Grep, Glob and Read still do the navigation; it indexes the repo first, so run it under a memory cap on a big one); `impact --dir <repo> --diff` for the blast radius of uncommitted changes; `render --auto <repo> -o <file>.html` (no LLM tokens) draws the project diagram, rebuilt when the work moves.
- **Tracker**: Plane over REST, the key read at run time and never printed (lesson `plane-rest-api`); that is the way when no Plane tool is loaded.
- **Not built yet**: a loop from one prompt to done (design: `ambysto-1prompt`, `docs/design.md`). Until then the review loop rule stands: fix a failed review at most 2 rounds, then stop and ask.

## Switching models (when a new model ships)
1. Pick 2-3 past diffs whose review findings are on record (review logs, PR comments), including at least one HARD change. The prepared cases, runner and release-day checklist are in the coding-playbook repo (`~/work/0xdonniechu/coding-playbook`), `switch-test/`.
2. Run the candidate as reviewer on each diff, without the old findings. Count the known issues it catches, the new real issues it finds, the false alarms, and the cost.
3. Switch only if it catches at least as many known issues at an acceptable cost. Then change `settings.json`, the effort entry and every agent file in one edit, and update the "Current choice" line with the date and the numbers (`scripts/switch-model.py` in the coding-playbook repo (`~/work/0xdonniechu/coding-playbook`) makes the repo's part of that edit in one command).

## Honesty
- Never report a check as passing that was not run. Write "not run: <reason>" (wrong OS, owner-only step, missing credentials).
- Never silently change a threshold, default, data format, public API or protected list. Flag it and ask.
- When a project has no CLAUDE.md with Verify, Rules and the HARD / MEDIUM / EASY lists, propose one from the project template before the first MEDIUM task.
