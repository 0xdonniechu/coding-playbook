---
status: verified # draft → planned (owner accepts) → building → verified
---
# Plan: verdicts tied to tasks

Intent: `2026-11-11-verdict-per-task.md` (approved). Ticket: Plane APS-61. HARD: the main session (Opus 5.5) builds;
hard-reviewer (Fable 5.2) reviews. Stacked on the APS-59 branch (`loop-wake`), which changes the same files.

## How it works

- `loop-stop.py subagent-stop`: reads the first user message of `agent_transcript_path` (a string or text blocks);
  every line that starts with `loop task:` or `loop tasks:` (any case; spaces, `>`, `*`, `-`, `_`, backticks before)
  names the task ids on it; each named task that has a `### T<n> (` heading in the plan gets its own
  `{agent, verdict, at, task}` entry; none named: one entry with `task: null`.
- `loop-stop.py` (Stop): only entries whose task the plan still has count; per task, the last verdict must not be FAIL and its FAIL
  verdicts must not outnumber its `loop.py fail` records; a Proof that names a review needs a PASS for some task.
- `loop.py pass <task>`: that task's last counted verdict must be PASS; `status` shows each verdict's task.

## Tasks

### T1 (main) Verdicts by task
- allow: `loop/loop.py` `loop/loop-stop.py`
- check: `python3 loop/loop.py --self-test`
- check: `python3 loop/loop-stop.py --self-test`

### T2 (main) Instructions and docs
- allow: `rores/global/CLAUDE.md` `skills/sdlc/SKILL.md` `README.md` `CLAUDE.md` `intent/**`
- check: `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py`

## Proof

1. `python3 loop/loop.py --self-test` and `python3 loop/loop-stop.py --self-test` pass with each rule above tested.
2. Each rule mutated once is caught.
3. `python3 scripts/check.py` passes.
4. Review PASS by hard-reviewer (Fable 5.2).
5. The sdlc skill's changed step, run once by a fresh agent given only the skill (CLAUDE.md Verify): where it guessed.

## Result

Hard review round 1 FAILed (MAJOR: the marker counted anywhere in the prompt, so a quoted phrase or another plan's
marker passed this run; MINOR: separators other than commas, markdown around the marker, a removed task holding the
run, four surviving mutations, usage text, branch and commit naming, the skill's fresh-agent check). Fixed: the marker
counts only at the start of a line, every such line, every task id on it; markdown around it allowed; verdicts count
only for tasks the plan still has; the docs limit the marker to reviews of the open run's plan and ask for a `fail` per
task named; branch `aps-61-verdict-per-task`. Accepted limit, documented: a `loop.py fail` counts for its task
whatever verdict it answered.

1. PASS both self-tests: `pass` refused after a PASS that names no task and after a PASS of another task; a later
   PASS of T1 does not hide T2's last FAIL; FAILs and `fail` records counted task by task; a FAIL that names no task,
   or a task the plan no longer has, counts for nothing; a quoted marker or one in a later message is not counted;
   the bold form with backticks around the id, the form with "and" between two ids, two marker lines and a prompt
   of text blocks are; a Proof that names a review needs a PASS for a task.
2. PASS: 6 of 6 mutations caught in round 1, then 8 of 8 on the fixes (text blocks, FAILs or fails counted across
   tasks, a later message, an inline marker, a removed task, no task read, `pass` not filtered).
3. PASS `python3 scripts/check.py`.
4. PASS hard-reviewer (Fable 5.2) round 2: no BLOCKER or MAJOR, 7 MINOR. Fixed after the PASS: the shipped doc lines
   that were markers themselves rewrapped (no tracked Markdown line starts with one); only the ids before the first
   other word count, and `#` may come first; text blocks joined by line breaks; an open FAIL of a task the plan no
   longer has holds nothing; tests for the `-`/`_` prefixes, markup before the colon and per-task FAIL counting
   (mutations 7 of 7 caught). Accepted limits: only the reviewer's first message is read; commit a8a67b7's subject
   lacks the ticket id (the merge title has it).
5. PASS fresh agent (Sonnet 5.5) given only the sdlc skill: it wrote the single and two-task markers, gave the review
   of other work no marker and ran `fail` once per task after a joint FAIL. Where it guessed, and what changed: whether
   the line must come first (now "anywhere"), whether a joint FAIL counts once per task (now "one FAIL for each") and
   whether another review's FAIL holds the run (now "neither holds nor passes"). Its other guesses (the loop tool's
   path, which reviewer agent, which diff) predate this change and stay with the global instructions.

