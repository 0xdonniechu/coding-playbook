---
status: verified # draft → planned (owner accepts) → building → verified
---
# Plan: done on evidence (checks rerun, reviewer verdicts), a time limit and a note to the owner

Intent: `2026-11-11-loop-evidence.md` (approved). Ticket: Plane APS-58. HARD throughout: the main session builds every
task; the review is by `reviewer` (Opus 5.5), because the main session runs Fable 5.2 today, the hard-reviewer's model.

## How it works

- `converge <plan> [--base ref] [--checks]`: with `--checks` and no other gap, each distinct `check:` command of the
  live tasks runs through the shell at the work tree's top, in its own process group (`SDLC_CHECK_TIMEOUT`, default
  900 s each; `SDLC_CHECKS_TOTAL`, 1500 s for all); a non-zero exit, a timeout (the group is killed) or no time left
  is the gap `check failed: <task> …`.
- `loop-stop.py` (Stop): judges with `--checks` (only once the run file itself lists nothing; judge timeout 1620 s, the hook's 1800 s in settings.json: this repo's own `check.py` takes about 9 minutes); counts the
  rounds with a `check failed` gap and closes the run at 3 (`checks`); closes at the deadline (`limit`); the last
  reviewer verdict on record must not be FAIL, must be PASS when a Proof item names a review, and every reviewer
  FAIL must have its `loop.py fail`; comments on the
  plan's Plane ticket (`Plane <KEY-N>` in the plan, `plane.py` beside the judge, detached) once when a run closed by
  ask, two fails, idle, limit or checks; says once when `permission_mode` is `default`; gives no decision and counts
  nothing while a subagent is in `background_tasks`, 10 stops in a row at most (a reviewer in the background:
  waiting is not idling; a background shell is not waited for, it may never end).
- `loop-stop.py subagent-stop` (SubagentStop): for an `agent_type` ending in `reviewer` in a session with an open
  run, appends `{agent, verdict, at}` to the run's `reviews` (the first PASS or FAIL word of its last message).
- `loop.py`: `start … [--hours N]` (default 12) writes the deadline; `pass` needs the last recorded reviewer verdict
  to be PASS; `resume` reopens a run closed by `checks` too, with a new deadline and the counter at zero.
- `install.py --settings`: registers the SubagentStop entry and updates the timeout of an entry already registered.

## Tasks

### T1 (main) The judge runs the checks
- allow: `scripts/sdlc-check.py`
- check: `python3 scripts/sdlc-check.py --self-test`

### T2 (main) The run file and the hooks
- allow: `loop/**`
- check: `python3 loop/loop.py --self-test`
- check: `python3 loop/loop-stop.py --self-test`

### T3 (main) Install, register and check
- allow: `scripts/install.py` `scripts/check.py`
- check: `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py`

### T4 (main) Instructions and docs
- allow: `rores/global/CLAUDE.md` `skills/sdlc/SKILL.md` `README.md` `CLAUDE.md` `intent/**`
- check: `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py`

## Proof

1. `python3 scripts/sdlc-check.py --self-test` passes: `--checks` runs the checks only when nothing else is missing,
   once per distinct command; a failing check and a timed-out one are gaps; without `--checks` nothing runs.
2. `python3 loop/loop.py --self-test` and `python3 loop/loop-stop.py --self-test` pass: `pass` refused without a
   reviewer PASS and after a reviewer FAIL; the SubagentStop mode records reviewer verdicts only; done is refused on a
   last FAIL and on a Proof that names a review without a PASS; three check rounds close; the deadline closes;
   `resume` reopens both; one ticket comment per close that needs the owner; the mode note once.
3. `python3 scripts/check.py` passes, with SubagentStop registered once and the Stop timeout updated in place.
4. This run: `loop.py start` on this plan in the building session; the Stop hook holds it until the plan converges.
5. A live `claude -p` session with the new hooks: a `reviewer` run is recorded, `loop.py pass` is refused before it
   and accepted after it, and a failing check keeps the run open.
6. Review PASS on the branch by `reviewer` (Opus 5.5).

## Result

1. PASS `python3 scripts/sdlc-check.py --self-test`: without `--checks` nothing runs; with it each distinct command
   runs once, at the work tree's top, only when nothing else is missing; a failing check and one over its time are
   gaps; a task that is not needed runs no check; the options in either order, an unknown one refused. Mutations: 6
   of 6 caught.
2. PASS `python3 loop/loop.py --self-test` and `python3 loop/loop-stop.py --self-test`: `pass` refused with no
   verdict, after a FAIL and after a verdict that was neither, accepted after a PASS; verdicts recorded only for
   reviewers of this session's open run; a last FAIL is not done; a Proof that names a review needs a PASS; failing
   check rounds 1 and 2 block, the third closes, `resume` reopens with the count at zero; the time limit closes; one
   ticket comment per close that needs the owner (hook closes at once, `ask` at the next stop, none for a stop by
   hand or done); the mode note once, none in a mode that does not ask; waiting for background work is not counted.
   After review round 1 also: a background subagent is waited for 10 stops at most and only while it runs, a
   background shell never; a reviewer FAIL without its `loop.py fail` is not done; the checks run only when the run
   file lists nothing; the ticket names a failing check without its output; "preview" names no review, "reviews"
   does; a timed-out check's whole process group is killed; the checks share one total time. Mutations: 27 of 27
   before the review (two missed at first got a test each), then 11 of 11, 4 of 4 and 2 of 2 on the fixes.
3. PASS `python3 scripts/check.py`: SubagentStop registered once, and a Stop entry registered with timeout 60 brought
   to 1800 in place (`--check` names it first). Mutations of the timeout update: 2 of 2 caught.
4. PASS this run, the first on a real goal: `loop.py start` at 03:12Z on this plan (four tasks) in the building
   session; the owner's prompt was the last owner message until the work was merged. The session built T1 to T4, had
   the branch reviewed twice (round 1 FAIL recorded with `loop.py fail T2`, round 2 PASS) and stopped once on its
   own with this item still open: the Stop hook held it ("1 item(s) left: proof 4 has no result", 1 stop held) and it
   went on without a word from the owner. Limits of this proof: the hook loaded in this session is the one from
   before this change (no checks rerun, no reviewer evidence; proof 5 covers those), so T2's PASS was recorded with
   `main`'s `loop.py`; and the run was ended with `loop.py stop "converged"` before the merge, as the global
   instructions say, not closed by the hook as done.
5. PASS live, on a scratch repo with the branch's hooks loaded by `--settings` (user settings left out, so the hook
   installed before this change did not judge too) and a `reviewer` agent: a `claude -p` session (Sonnet 5.5) started
   the run; `loop.py pass` was refused three times ("no reviewer PASS on record") before the review; the reviewer ran
   in the background, the hook let the session wait, its PASS was recorded, `pass T1` and `pass T2` were accepted and
   the run closed done with both checks passing (5 turns, $0.15). The first such run found a defect: stops made while
   waiting for the background reviewer counted as idle and closed the run before its verdict came; fixed (no
   decision while `background_tasks` is not empty) and tested. The failing check, by hand on the same repo with the
   real hook and judge: rounds 1 and 2 blocked with `check failed: T2 …`, round 3 closed the run (`checks`).
6. PASS `reviewer` (Opus 5.5) round 2. Round 1 FAIL: 1 MAJOR (the wait for background work had no bound: a dev server
   left the run open with nobody told), 5 MINOR, 3 NIT; all fixed, recorded with `loop.py fail T2`. Round 2 PASS, its
   own 15 mutations all caught; of its follow-ups, fixed: `resume` resets the wait count, only a running subagent is
   waited for, "reviews" and "reviewing" name a review, the drain after a kill has a time limit, the global wording.
   Left as documented limits: a FAIL the session records on its own counts toward the reviewer FAILs it must record;
   the total-time self-test depends on timing.

