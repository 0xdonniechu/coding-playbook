---
status: shipped (PR #54; approved: owner answers 2026-11-10, "merge proactively" 2026-11-11; plan intent/2026-11-10-one-prompt-loop.plan.md) # draft → approved → planned → building → verified → shipped (PR #n)
---
# One prompt runs the coding loop to the goal, and stops when something fails twice

Ticket: Plane APS-56. Source: owner 2026-11-10, standard 5 of eight: "chỉ cần 1prompt là coding loop chạy tới khi
hoàn thành goal, chỉ dừng loop khi fail 2 lần". Order of work (owner, same day): 6, 7, 8, then 5.

## Problem

1. **A session stops whenever the agent stops.** The loop today (rate, dispatch, gate, review, fix at most 2 rounds)
   lives in the global instructions as prose. After each answer the session waits for the owner, so a goal of ten tasks
   needs about ten "continue" messages. The owner's log calls these `unblock` and `status`; they are the ones to remove.
2. **Nothing decides "done" from evidence.** The only thing that ends a run is the agent saying it is done. Claude
   Code's `/goal` keeps a session going, but its judge is a small model that reads only the transcript: it runs nothing
   and believes what the agent printed (`ambysto-1prompt`, prior art 11).
3. **The stop rule is per review, not per run.** "Fix a failed review at most 2 rounds, then stop and ask" exists, but
   nothing counts the rounds or holds the session to it.
4. **The full design is far off.** `ambysto-1prompt/docs/design.md` plans a headless driver (systemd timer and
   `claude -p`), a beads graph, auto-merge, a $50 daily cap and a morning report. Each of those waits on owner
   decisions and a pilot. None of it helps an interactive session today.

## Outcome

An opt-in loop for one interactive session, built in this repo from what exists (the sdlc chain, `sdlc-check.py
converge`, the task contract, the reviewers):

1. **One prompt starts it.** The owner gives a goal. The main session writes the intent and the plan (with `## Tasks`
   and `## Proof`) and runs `clarify`. An open point that only the owner can settle is asked once, all together, at
   the start; then the prompt counts as the approval of that intent and plan. Then the run starts: `loop.py start <plan>` writes a run file in the repo's git
   folder.
2. **A Stop hook holds the session to the plan.** While a run is open, each time the session would stop, a command
   Stop hook runs `converge` on the plan and reads the run file. Gaps left (a task untouched, a proof item without a
   PASS) → it blocks the stop and hands the session the list as its next work. No gaps → it lets the session stop with
   "goal done". The judge is a program reading git and the plan, never the transcript.
3. **Two fails stop it.** The main session records each review verdict with `loop.py fail <task> "<reason>"` or
   `loop.py pass <task>`. The second FAIL of the same task closes the whole run, and the hook lets the session stop with
   the reason and the numbered issues.
4. **Safety stops.** The run also closes, with its reason, when: the session asks a human-only question (the list in
   the global instructions); three stops in a row show no change in git or the plan (a loop that is not moving); or the
   owner runs `loop.py stop`. Without a run file the hook does nothing, so every other session is as today.
5. **What the loop does not do.** It never merges (merges stay the owner's), never tags, releases or publishes, and
   never raises a limit. It ends with verified PRs and the same short summary the global instructions ask for.
6. The global instructions ("The loop") and the sdlc skill say how to start and end a run; the "Not built yet" line in
   the Tools section goes.

Success: self-tests for the hook and `loop.py` (scratch repo and plan: gaps block, no gaps let it stop, the second FAIL
closes, three idle stops close, no run file does nothing, a broken run file never traps a session). Then one real goal
of at least three tasks on a pilot repo, started by one prompt, reaches "goal done" or a two-fail stop with no
`continue` from the owner; its time-log lines are counted.

## Constraints

- A hook that blocks stopping can trap a session: every failure inside the hook (no git, a bad run file, a crash)
  must let the session stop. A judge that crashes, times out or gives no verdict is never read as done: the hook holds
  the session with the error and the idle breaker ends the run on the third stop with no change (hard-review round 1). This is HARD: the main session builds it, hard-reviewer reviews.
- Opt-in per run; no run file, no effect. Standard library Python; Linux and Windows (the VM); `|| true` as for the
  save-it hooks.
- Existing rules stand: the task contract and agent-guard for builders, the reviewers, the human-only list, "merges
  only when asked", the owner time log.
- `converge` is the judge; it is not changed for this, only called.

## Out of scope

- The headless driver, beads, auto-merge, the daily spend cap and the morning report (`ambysto-1prompt`, after a
  pilot). This loop is the interactive part they can later drive.
- Parallel builders inside one run beyond what `dispatch.py new` already allows.

## Decisions

Settled by the owner on 2026-11-10, answering the four open questions of the draft: build the interactive loop here,
in coding-playbook, and leave the headless driver, beads, auto-merge, the cap and the morning report to
ambysto-1prompt; the one prompt approves the intent and plan the loop writes, with any point only the owner can settle
asked once, all together, at the start, and HARD tasks keeping hard-reviewer; the second FAIL of one task stops the
whole run (no parking). The pilot repo and goal are the owner's pick once the build is verified.

## Open questions

None.
