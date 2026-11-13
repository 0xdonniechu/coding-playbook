<!-- coding-playbook:begin -->
# Global Antigravity / Gemini instructions (installed in ~/.gemini/GEMINI.md, applies to every project)

## Model economy
The main session runs the model with the best quality per cost for everyday deciding, rating, dispatching and gating, while escalating HARD implementation and MEDIUM reviews to the Code & analysis tier. It decides, rates each task, dispatches, gates, commits, merges and talks to me.
**Current choice (2026-11-13): Gemini 4 Hydrogen (`gemini-4-hydrogen`, Everyday help) for the main session & `builder` + Gemini 4 Argon (`gemini-4-argon`, Code & analysis) for HARD work & `reviewer` + Gemini 3.1 Pro (`gemini-3.1-pro`, Detailed research — auto-upgrade to Gemini 4 Carbon `gemini-4-carbon` once released to general users) as `hard-reviewer` + Gemini Decision 1 (`gemini-decision-1`, with `gemini-3.5-flash-lite` Quick answers fallback) as the real-time command and routing gate.**

Where each setting lives (`GEMINI.md` records the policy; hooks and `invoke_subagent` enforce it):
- Main session model: selected in Antigravity (`gemini-4-hydrogen` for everyday session / orchestration; `gemini-4-argon` for HARD implementation & `reviewer`), pinned by decision rather than changed ad-hoc.
- **Gemini Decision 1 (`gemini-decision-1`)**: runs in two places:
  1. **PreToolUse Safety Gate (`~/.antigravity/hooks/gd1_hook.py`)**: intercepts every `run_command` / `bash` / `execute_command` call and classifies it with calibrated probabilities (`returnProbabilities: true`, fallback `gemini-3.5-flash-lite`):
     - `safe_read_or_dev` (confidence $\ge 0.95$) $\rightarrow$ `allow` automatically (read-only inspection, `git status`, `ls`, `cat`, local test/build).
     - `destructive_danger` (confidence $\ge 0.70$) $\rightarrow$ `deny` immediately (`rm -rf`, disk format, killing system processes, leaking secrets).
     - `risky_modify` or lower confidence $\rightarrow$ `ask` for manual Y/N confirmation in the CLI (`pip install`, config edits, `git push`, system state changes).
  2. **Task Triage & Dispatch Gate**: before dispatching non-trivial work, use Gemini Decision 1 (or the 4-axis rubric below) to classify the task into `EASY`, `MEDIUM`, or `HARD` with calibrated confidence.

Subagents (invoked via `invoke_subagent` or defined via `define_subagent` using the role specs in `~/work/0xdonniechu/coding-playbook/rores/agents/`):
- **decision-gate** (`gemini-decision-1` / `gemini-3.5-flash-lite` `flash_lite`): fast calibrated classification for tool safety (`PreToolUse`) and task triage (`EASY` / `MEDIUM` / `HARD`). Never edits files.
- **builder** (Gemini 4 Hydrogen `gemini-4-hydrogen`, `high` / `flash` tier, `Workspace: "share"` when parallel): implements an approved plan step (Everyday help tier). Edits the working tree only; never commits, pushes, opens PRs, merges or updates an issue tracker.
- **reviewer** (Gemini 4 Argon `gemini-4-argon`, `high` / `pro` tier): independent review of a MEDIUM diff written by `builder` (`gemini-4-hydrogen`); returns PASS/FAIL with numbered issues. Never edits.
- **hard-reviewer** (Gemini 3.1 Pro `gemini-3.1-pro` Detailed research, or **Gemini 4 Carbon** `gemini-4-carbon` `high` once it replaces `3.1 Pro` in general release; or Orca worker via `orchestration` when cross-family review is needed): independent review for HARD changes written by `gemini-4-argon`, by a different model from the one that wrote them so it does not share its blind spots. When `gemini-4-carbon` ships to general users on the Detailed research tier, update this role to `gemini-4-carbon` (`high`).
- **transcriber** (Gemini 3.5 Flash-Lite `gemini-3.5-flash-lite`, `low` / `flash_lite` Quick answers): mechanical copying and conversion only, no judgment.

Subagents return concise summaries, never full file dumps: builder and transcriber at most 200 words (the builder's contract check commands not counted), reviewers at most 300 (500 for a HARD change).
Small tasks (1-2 files, obvious change) are done directly, not dispatched.

## Task rating (do this before dispatching, assisted by Gemini Decision 1)
Rate on four axes: ambiguity, coupled decisions, verifiability, cost of error. Judge the cost of error by what undoing it takes, never by how sure the model is (owner decision 2026-11-11):
- One-click undo (docs, tests, one function: a revert fixes it): low.
- Cleanup undo (shared helpers, an interface other code calls, rules every session acts on: a revert leaves work or decisions to redo): high.
- No undo: **HARD**, whatever the other axes say. User data lost or migrated (schema migrations included), auth or any other security boundary weakened, money moved, something published or sent, and anything else no revert takes back (a force push, a production setting, a deletion).
- All low → **EASY**: transcriber (`gemini-3.5-flash-lite`) or builder (`gemini-4-hydrogen`), no review.
- One high → **MEDIUM**: builder (`gemini-4-hydrogen`), then reviewer (`gemini-4-argon`).
- Two or more high, **or** no undo → **HARD**: Gemini 4 Argon (`gemini-4-argon`) does it directly, then hard-reviewer (`gemini-3.1-pro`, or `gemini-4-carbon` once released) reviews it.
Each project's `GEMINI.md` / `CLAUDE.md` lists its own HARD / MEDIUM / EASY examples; those override this default.

## The loop
- Every builder dispatch carries a task contract, written with `scripts/dispatch.py` in the coding-playbook repo (`~/work/0xdonniechu/coding-playbook`): `new <repo> <branch> --allow … --check …` gives a builder that runs beside another its own worktree and contract; `contract <tree> --allow … --check …` serves a single builder in the main checkout. The main session reruns the contract's checks as its gate before review, judges an `OUTSIDE CONTRACT` report before anything else, and runs `dispatch.py done <tree>` when the work is committed.
- When the plan has a `## Tasks` section (the sdlc skill), a builder's contract comes from its task: `dispatch.py new <repo> <branch> --task <plan> <id>` (or `contract <tree> --task …`), not from flags typed again.
- Before the review of a plan's build, `scripts/sdlc-check.py converge <plan>` lists every changed file outside the plan's tasks, every task left untouched and every Proof item without a result; the reviewer gets its output with the diff. `sdlc-check.py clarify <intent>` fails while an intent still has an open point.
- The reviewer gets the task and the diff, not the builder's or the main session's summary.
- On FAIL: the builder (MEDIUM) or the main session (HARD) fixes from the numbered issue list, at most 2 rounds; then stop and ask me.
- **One-prompt run** (opt-in, when the owner gives a goal to carry to done): follow the sdlc skill's "One-prompt run" section. Its loop tool is `python3 ~/work/0xdonniechu/coding-playbook/loop/loop.py` (`start <plan> [--hours <n>]`, default 12 hours; `pass <task>`, `fail <task> "<reason>"`, `ask "<question>"` and then ask it, `stop`, `resume`, `status`). Every reviewer prompt for the open run's plan has a line of its own `loop task: T<n>` (two tasks: `loop tasks: T1, T2`); a review of other work gets none. Record every reviewer FAIL with `loop.py fail`, once per task it named (the run is not done without it); a task whose last verdict is FAIL holds the run until a later PASS. A path outside every task that is not this work's: ask, never delete it or widen the plan. To merge inside a run: once `converge` passes and every review is recorded, `loop.py stop "converged"`, then merge as the rules below say.
- A BLOCKER or MAJOR issue is never waived silently: fix it, or ask me.
- Only the main session commits, pushes, opens or merges PRs, and updates the issue tracker. It merges on its own (owner decisions 2026-11-11) once the change passed its gate and review and the project's whole Verify ran on the branch; then it deletes the merged branch, local and remote, and removes its worktree once `git status --ignored` there shows nothing to keep (a gitignored `HANDOFF.md` or local settings go first to where they are still needed). It asks first when the merge publishes or deploys something outside (a public page or download, a release, a production deploy on merge), and when it cannot tell: the repo has a site, hosting config, download files or a workflow on push to `main`, and its `CLAUDE.md` / `GEMINI.md` does not say what a merge to `main` publishes. It asks also in `ambysto-memory` and `ambysto-1prompt` (GitHub keeps merges with the owner there), for tags and releases, and for a change whose content needs the owner's approval first.

## Owner time log
- The main session (never a subagent) appends one line to `~/.claude/hil/log.jsonl` (create the folder if it is missing) each time the owner steps in, at the time it happens. One line per owner message, a plain "ok", "continue" or "wait" included; give it one `kind`, the main one when several apply. A headless run, a scheduled or scripted run, or a test session has no owner at the keyboard and never writes this log; its prompt is not an owner message (lesson 2026-10-22: two test runs each wrote a fake owner line).
- Line: `{"ts":"2026-10-18T14:05Z","project":"<repo name, or the shared effort's short name>","task":"<ticket id, or a short slug when there is none>","kind":"…","trigger":"…","note":"<one line, no secrets>"}`. `ts` is UTC and ends in `Z`. Add `"minutes": <number>` only when the owner says how long it took.
- `kind`, by design: `decision` (the owner answers a question about what to build or how), `approval` (the owner accepts an intent, plan or change as written), `merge` (the owner asks to commit, push, merge or tag), `direction` (the owner brings new scope or steering nobody asked for). To reduce: `setup` (an owner-only step: sign-in, token, device), `incident` (something broken), `unblock` (the agent had stopped and needed a nudge), `status` (the owner had to ask where things stand).
- `trigger`: `agent-asked` when the session asked the owner (a question, a request for approval, an owner-only step), `owner` when the owner started it. A reply to a question is `agent-asked`, even when it also adds steering.
- An incident the owner noticed first (`incident`, `owner`) is the signal that matters. After the fix, ask whether a gate (including a Gemini Decision 1 candidate rule in `gd1_hook.py`) would have caught it. If the lesson holds only for that project, it goes in the project's `CLAUDE.md` / `GEMINI.md`. If it holds across projects, propose it for the working practice below. Either way it is guidance first, and becomes a gate only when the project decides so.
- The report: `python scripts/hil-report.py [--since YYYY-MM-DD] [--project P]` in the coding-playbook repo (`~/work/0xdonniechu/coding-playbook`).

<!-- ambysto-memory:begin -->
## Shared memory
Ambysto repos share one owner-reviewed memory in `~/work/ambysto/ambysto-memory` (its `AGENTS.md` says how to use it). Do not use Claude Code's per-folder auto-memory (turn it off with `"autoMemoryEnabled": false` in `~/.claude/settings.json`).
- Before non-trivial work, and when a command fails in a way that may have a known fix: if the clone is on `main`, run `git -C ~/work/ambysto/ambysto-memory pull --ff-only` (on another branch, offline, or when a sandbox refuses the pull, read it as it is and say so); read its `INDEX.md`; open the lessons whose line matches the task.
- When a lesson changes what you do, name it in one line. If a lesson conflicts with the owner or the project's own docs, follow those and say so.
- To add or change a lesson (something learned that a later session needs), draft it on a branch there and open a PR, as its `AGENTS.md` says; the owner's merge is the approval. Never merge it yourself.
<!-- ambysto-memory:end -->

## Working practice (guidance from lessons that held in more than one context; not gates)
- After any subagent has run, check the branch in the same command as a commit, amend or reset; agents share the working tree and can switch it.
- Give each agent that runs at the same time its own worktree (`dispatch.py new` or `Workspace: "share"` for subagents). Never edit a worktree while an agent is running in it: it may stage everything there.
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
- **Gemini Decision 1 Gate** (`~/.antigravity/hooks/gd1_hook.py`, registered in `~/.gemini/config/hooks.json` under `gd1-safety-guard`): gates `PreToolUse` on `run_command|bash|execute_command` via `gemini-decision-1:decide` (with `gemini-3.5-flash-lite` structured fallback). Reads API key from `GEMINI_API_KEY` or `~/.antigravity/gemini_api_key`.
- **Resume** (`ambysto-saveit`): `ambysto-saveit resume` briefs `HANDOFF.md` and the work tree at the start of a session or after one died (crash, HTTP 429); still read `HANDOFF.md` itself, and pass a dead session's file as `--transcript <old.jsonl>` (the newest transcript is this session's own). `tail --write` and `dead-end "<entry>"` write `HANDOFF.md`: it must be gitignored, and the tail copies commands as typed, so check it for keys. `ambysto-saveit gate -- <cmd>` runs a noisy suite quietly (no shell: no `&&`).
- **Orientation and diagrams** (`ambysto-graph`, local CLI and MCP server `ambysto-graph`): `overview --dir <repo>` to orient in a repo you do not know (Grep, Glob and Read still do the navigation; it indexes the repo first, so run it under a memory cap on a big one); `impact --dir <repo> --diff HEAD` for the blast radius of uncommitted changes (a bare `--diff` finds nothing); `render --auto <repo> -o <file>.html` (no LLM tokens) draws the project diagram. For progress, `python3 ~/work/0xdonniechu/coding-playbook/scripts/progress-diagram.py <repo> --plan <plan.md>` (under a memory cap on a big repo) draws the architecture, what the branch changed and the plan's tasks and proof items with their state into the repo's git folder (never committed); the main session runs it again each time the work moves and gives the owner the `progress.html` path.
- **Tracker** (Plane): `python3 ~/work/0xdonniechu/coding-playbook/scripts/plane.py` with `projects`, `show <KEY-N>`, `create <KEY> --name …`, `state <KEY-N> <state>`, `comment <KEY-N> --body …`, `link <KEY-N> <url>`; it reads the key at run time and never prints it (lesson `plane-rest-api`). The ticket follows the chain (sdlc skill, "Conventions"): the main session moves it as each step happens, not in a batch at the end.
- **Architecture graph** (owner decision 2026-11-11): at session end a hook refreshes `<git dir>/progress-diagram/overview.md` and `architecture.html` in the background; the next session's start names them and their commit. Read that `overview.md` before exploring a repo; when HEAD moved far since or the last refresh failed, run `ambysto-graph overview --dir <repo>`.

## Switching models (when a new model ships)
1. Pick 2-3 past diffs whose review findings are on record (review logs, PR comments), including at least one HARD change. The prepared cases, runner and release-day checklist are in the coding-playbook repo (`~/work/0xdonniechu/coding-playbook`), `switch-test/`.
2. Run the candidate as reviewer on each diff, without the old findings. Count the known issues it catches, the new real issues it finds, the false alarms, and the cost.
3. Switch only if it catches at least as many known issues at an acceptable cost. For Gemini Decision 1 thresholds (`0.95` allow on `safe_read_or_dev`, `0.70` deny on `destructive_danger`), re-calibrate on recorded command logs before lowering any threshold.

## Honesty
- Never report a check as passing that was not run. Write "not run: <reason>" (wrong OS, owner-only step, missing credentials).
- Never silently change a threshold, default, data format, public API or protected list. Flag it and ask.
- When a project has no `CLAUDE.md` / `GEMINI.md` with Verify, Rules and the HARD / MEDIUM / EASY lists, propose one from the project template before the first MEDIUM task.
<!-- coding-playbook:end -->
