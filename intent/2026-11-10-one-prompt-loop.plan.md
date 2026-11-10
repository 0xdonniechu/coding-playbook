---
status: verified # draft → planned (owner accepts) → building → verified
---
# Plan: one prompt runs the coding loop to the goal, and stops when something fails twice

Intent: `2026-11-10-one-prompt-loop.md` (approved). Ticket: Plane APS-56. HARD throughout (a hook that can keep a
session from stopping): the main session builds every task, hard-reviewer reviews the whole branch.

## How it works

- **Run file.** `loop/loop.py start <plan> [--base <ref>]` writes `<git dir>/1prompt-run.json`: the plan's absolute
  path, the base, this session's id (`CLAUDE_CODE_SESSION_ID`; refused without it), the absolute path of the
  `sdlc-check.py` that judges it, `state: running`, and empty fail lists. One run per work tree; a second `start` while
  one runs is refused.
- **Verdicts.** `loop.py pass <task>` and `loop.py fail <task> "<reason>"`. The second `fail` of one task closes the
  run (`closed: T<n> failed review twice: …`). `loop.py ask "<question>"` closes it for a human-only question.
  `loop.py stop [reason]` closes it for any other reason. `loop.py resume` reopens a run closed by `ask`, `stop` or the
  idle breaker (never one closed by two fails or by "done"); `loop.py status` prints it.
- **Stop hook** (`loop/loop-stop.py`, installed to `~/.claude/hooks/loop/`, registered for `Stop` by
  `install.py --settings`, command ending in `|| true`). On each stop of the session named in the run file:
  1. no run file, another session, a closed run, or an error inside the hook → exit 0 with no decision (the session
     stops);
  2. the fingerprint (HEAD, the bytes of every tracked change and untracked file, the plan, the verdict lists) equals
     the last one for the
     third stop in a row → close the run (`no progress in 3 stops`) and let it stop;
  3. `sdlc-check.py converge <plan> --base <base>`; exit 2 (the plan cannot be read) → block once with the error
     (the idle breaker ends it if nothing changes);
  4. a gap, or a proof result that begins with FAIL → block with the list as the next work, plus how to record a
     verdict and how to end the run;
  5. none → close the run as `done` and let it stop.
  `not run: <reason>` counts as settled, as in `converge`: an honest "not run" does not keep the session going.
  A recorded review FAIL with no later PASS of that task is a gap. Done needs the judge's own PASS line and exit 0.
- **Bounds** (review round 1): 3 stops with no change (content, not only names) or 40 stops held close the run;
  the run is found through `~/.claude/1prompt-runs/<session id>`, whatever the cwd; the hook's writes merge onto
  the run file as it is, so a `stop` written meanwhile holds.
- **Never trap a session**: every failure inside the hook exits 0 without a decision; the hook has a 60 s timeout. A
  judge that crashes, times out or prints no verdict holds the session with the error (never done); the idle breaker
  and the 40-stop limit bound it, and the reason says not to edit the judge but to `loop.py stop` and tell the owner.

## Tasks

### T1 (main) The run file, the verdicts and the Stop hook
- allow: `loop/**`
- check: `python3 loop/loop.py --self-test`
- check: `python3 loop/loop-stop.py --self-test`

### T2 (main) Install, register and check
- allow: `scripts/install.py` `scripts/check.py`
- check: `python3 scripts/check.py`

### T3 (main) Instructions and docs
- allow: `rores/global/CLAUDE.md` `skills/sdlc/SKILL.md` `README.md` `CLAUDE.md` `intent/**`
- check: `python3 scripts/check.py`

## Proof

1. `python3 loop/loop.py --self-test` passes: start (session id, refusals), pass and fail, the second fail closes,
   ask, stop, resume (not after two fails or done), status.
2. `python3 loop/loop-stop.py --self-test` passes, in scratch repos and plans: gaps block with the list; no gaps
   close as done; a FAIL result blocks; another session, no run file, a closed run, a broken run file and a missing
   judge all let the session stop; three idle stops close the run; a plan that cannot be read blocks with the error.
3. `python3 scripts/check.py` passes, with both self-tests and `--settings` registering the Stop hook once.
4. A live run in a real session on a scratch repo: a two-task plan, `loop.py start`, the session is held at the first
   stop and released when the plan converges.
5. Hard-reviewer PASS on the branch.

## Result

1. PASS `python3 loop/loop.py --self-test` (start with and without a session id, second start refused, pass, fail 1,
   fail 2 closes with both reasons, ask, stop, resume refused after two fails and done, broken run file, outside git).
2. PASS `python3 loop/loop-stop.py --self-test` (another session and a stale pointer, gaps, the session's cwd
   elsewhere, FAIL result, an open review FAIL, done, closed run, a judge that crashes, has a syntax error, exits 3,
   prints PASS but exits 1 or times out (never done, run kept), Tasks removed mid-run, a stop during the judge kept,
   idle 3 closes while an edit to a dirty file counts as progress, block limit, resume, closed by ask, unreadable plan,
   missing judge, broken and unknown run files, no run file, bad stdin, NUL in the pointer). Mutations: 8 of 8 caught
   after review round 1 (round 1 had 8 of 10).
3. PASS `python3 scripts/check.py` (both self-tests; `--settings` registers the Stop hook once in a scratch HOME).
4. PASS a headless `claude -p` (Sonnet 5.5) on a scratch repo with a two-task plan, the Stop hook loaded with
   `--settings`, told only to run `loop.py start` and reply "started": the hook held it, it built T1 and T2, ran the
   proof, filled Result, recorded `pass T1` and `pass T2`; the run closed `done` (12 turns, $0.22). Again after the
   round-1 fixes, on a branch with base main: held once, built both tasks, closed `done` (9 turns, $0.21).
5. PASS hard-reviewer round 2 (round 1 FAIL: 1 MAJOR, a crashing judge read as done; 6 MINOR, 1 NIT; all fixed).
   Round 2's follow-ups fixed too: the fingerprint hashes bytes (a non-UTF-8 diff or file), done needs the judge's PASS
   line, a run closed or restarted while the judge ran is left as it is (no block), one open run per session, the
   catch-all, the blocks count and an untracked non-UTF-8 edit are tested.

