---
status: shipped (ambysto/coding-playbook PR #56, here PR #14; owner 2026-11-11: "tìm cách giải quyết những issue này một cách nhẹ nhàng, đơn giản và hiệu quả"; plan intent/2026-11-11-loop-evidence.plan.md) # draft → approved → planned → building → verified → shipped (PR #n)
---
# A one-prompt run is done on evidence, not on the agent's word, and tells the owner when it needs them

Ticket: Plane APS-58. Source: owner 2026-11-11, after the assessment "is the playbook enough to run to the goal, the
human only joining after repeated fails?": "find a light, simple and effective way to solve these issues".

## Problem

1. **Done rests on the agent's word.** The Stop hook closes a run as done when `converge` finds the plan's files
   touched and a Result line under every Proof item. It never runs a task's `check:` commands, and `loop.py pass` is
   typed by the same session that wrote the code: a hurried agent can write PASS and be let go.
2. **Failing tests are not counted.** Only the second review FAIL of one task ends a run. Checks can fail any number
   of times; the owner asked for the human to come in after three failing rounds.
3. **A run can wait or run without anyone knowing.** In a permission mode that asks, every unknown command waits for
   the owner; a run has no time limit; and when the hook closes a run (idle, limit) nothing tells the owner.
4. **No real run yet.** The loop was proven on two scratch plans of two tasks.

## Outcome

1. `sdlc-check.py converge --checks` runs each task's `check:` commands once nothing else is missing; a failing or
   timed-out check is a gap. The Stop hook judges with `--checks`, so done means the checks passed just now.
2. Three rounds of failing checks close the run ("checks failed 3 rounds"), beside the two review FAILs rule.
3. A SubagentStop hook records the verdict of every `reviewer` and `hard-reviewer` run of the session in the run file.
   `loop.py pass` is refused unless the last such verdict is PASS; a run whose last reviewer verdict is FAIL, or whose
   Proof asks for a review and has no reviewer PASS on record, is not done.
4. `loop.py start --hours N` (default 12) sets a time limit; past it the hook closes the run. When a run closes and
   needs the owner (ask, two fails, idle, limit, checks), the hook comments on the plan's Plane ticket, once. When the
   session's permission mode asks before tool calls, the hook says so once.
5. This work is itself the first real run: four tasks on this repo, started with `loop.py start`.

## Constraints

- Light: no new file; standard library only. The hook still never traps a session on its own failure.
- A check runs through the shell from the work tree's top with a time limit; a heavy check carries its own memory cap
  in its command.
- HARD (a hook that can hold a session, the installer's writes to `settings.json`): the main session builds it; the
  review is by a model other than the one that wrote it.

## Success

The self-tests cover each rule (a failing check is a gap and three rounds close; a reviewer verdict is recorded and
`pass` needs it; the time limit; the ticket comment through a fake `plane.py`; the mode note). `check.py` passes with
the SubagentStop entry registered once and the Stop entry's timeout raised in place. This run reaches done, or stops
by a rule, without a "continue" from the owner.

## Decisions

- Out of scope, as the owner decided on 2026-11-10: waking a dead session (crash, HTTP 429, quota) stays with
  `ambysto-1prompt`'s headless driver. Proposed there as a next ticket, not built here.
- No `HANDOFF.md` at start: after a compaction the hook's own message lists what is left at every stop.
- The stop rules: two review FAILs of one task (owner 2026-11-10) and three failing check rounds (owner 2026-11-11,
  "test 3 vòng fail").

## Open questions

None.
