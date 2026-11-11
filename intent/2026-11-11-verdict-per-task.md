---
status: approved (owner 2026-11-11: "làm ticket verdict"; plan intent/2026-11-11-verdict-per-task.plan.md) # draft → approved → planned → building → verified → shipped (PR #n)
---
# A reviewer's verdict counts only for the task it reviewed

Ticket: Plane APS-61. Source: the assessment of 2026-11-11, gap 2: verdicts were not tied to a task, and it happened
live: a reviewer PASS for APS-60 was recorded in the APS-59 run of the same session.

## Problem

The SubagentStop hook records every reviewer verdict of the session in its open run. `loop.py pass <task>` and done
look only at the last verdict, whatever it reviewed: a PASS of other work, or of another task, passes this one.

## Outcome

1. A reviewer's prompt names its task as `loop task: T<n>` (or `loop tasks: T1, T2`). The hook reads it from the
   reviewer's transcript and records the verdict for each named task the plan has.
2. `loop.py pass <task>` needs that task's last verdict to be PASS. Done is refused while any task's last verdict is
   FAIL or a task has a reviewer FAIL with no `loop.py fail`; a Proof that names a review needs a PASS for some task.
3. A verdict that names no task of the plan is kept (status shows it) and counts for nothing.
4. The global instructions and the sdlc skill tell the session to name the task in every reviewer prompt.

## Constraints

- HARD (the hook that holds a session): the main session builds it; hard-reviewer reviews it.
- Light: no new file; the marker is plain text in the prompt, nothing to install.

## Success

Self-tests cover each rule (a PASS of another task or of no task does not pass; a later PASS of one task does not hide
another task's FAIL; a review of two tasks counts for both; a task the plan lacks counts for nothing), with every rule
mutated once and caught; `check.py` passes.

## Open questions

None.
