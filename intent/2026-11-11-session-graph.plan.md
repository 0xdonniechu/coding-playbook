---
status: verified # draft → planned (owner accepts) → building → verified
---
# Plan: refresh the graph at session end, name it at session start, merge on its own

Intent: `2026-11-11-session-graph.md` (approved). Ticket: Plane APS-57. HARD: the main session builds every task,
hard-reviewer reviews the branch.

## How it works

- `graph/graph-hook.py session-end` (SessionEnd): reads `cwd` from the hook JSON; in a git work tree with
  `ambysto-graph` installed, it starts `graph-hook.py refresh <top>` detached: `systemd-run --user --collect
  --no-block -p MemoryMax=4G -p RuntimeMaxSec=900`; without systemd (macOS) a new process session; a failing `systemd-run` starts nothing. It returns at once, exit 0.
- `refresh <top>`: takes `<git dir>/progress-diagram/refresh.lock` (another refresh holds it → exit; a lock older than
  30 minutes is stale; a job removes only its own lock), computes a fingerprint (HEAD, the bytes of `git diff HEAD`, the untracked names), skips when
  it equals the last one and both files exist, else writes `overview.md` and `architecture.html` through temporary
  files and renames (a state whose refresh failed is not tried again until the work tree changes; a job that died
  leaves `pending`, and its state is tried once more after its lock is stale, then recorded), then `session-graph.json` (commit, fingerprint, time, or the error with the old files kept).
- `graph-hook.py session-start` (SessionStart): with `overview.md` there, prints two lines: the paths, the time and
  commit they were drawn at, and how many commits HEAD moved since. Nothing otherwise.
- `install.py --settings` installs it to `~/.claude/hooks/graph/` and registers both events, `|| true`, once each.

## Tasks

### T1 (main) The graph hook
- allow: `graph/**`
- check: `python3 graph/graph-hook.py --self-test`

### T2 (main) Install, register and check
- allow: `scripts/install.py` `scripts/check.py`
- check: `python3 scripts/check.py`

### T3 (main) Instructions and docs
- allow: `rores/global/CLAUDE.md` `README.md` `CLAUDE.md` `intent/**` `skills/sdlc/SKILL.md` `skills/starter-kit/project-CLAUDE.md`
- check: `python3 scripts/check.py`

## Proof

1. `python3 graph/graph-hook.py --self-test` passes: end writes the graph; no change skips; a change refreshes; a held
   lock skips and a stale one is taken; a failing tool keeps the old files and records the error; start prints the
   paths, commit and commits since; nothing without a graph, outside git, with bad input or without the tool; every
   mode exits 0.
2. `python3 scripts/check.py` passes, with `--settings` registering SessionEnd and the second SessionStart entry once.
3. On this machine: a real `claude -p` session ends in a scratch repo, its graph appears within a minute, and the next
   session's SessionStart output names it.
4. Hard-reviewer PASS on the branch.

## Result

1. PASS `python3 graph/graph-hook.py --self-test`, after hard-review round 1: end writes the graph and a stamp of the
   drawn commit and fingerprint alone, nothing in the work tree, no lock or temporary file left; start names it with
   the commit in a short line; no change skips, a missing drawing is drawn again, an edit and a new untracked file
   refresh; HEAD moved, HEAD behind the drawn commit and an unknown commit are each said; a held lock skips, a stale
   one is taken with a killed job's temporary file removed, a lock that is not the job's own is never removed; both
   tools failing, overview failing or empty, render failing or empty all keep the old files and record the failure,
   which is not retried until the work tree changes and is cleared when it goes back to the drawn state; a job killed
   mid-refresh (a real kill of the job) leaves its lock and `pending`, is tried once more after the lock is stale,
   and after a second death is recorded and not run again, while two deaths on one state never count against
   another; unchecked stamp values, a head that is not a commit id and a
   newline in the path never reach the context; bad input, outside git, no tool, an unknown mode and an error inside
   all exit 0 with nothing; the start through a fake systemd-run carries `--user --collect --no-block`, `MemoryMax`
   and `RuntimeMaxSec`, keeps a `$` in the repo path and outlives the hook; a failing systemd-run starts nothing;
   without systemd the job runs detached. Mutations: 28 of 29 caught after round 3 (round 1's review found 6 of 10 missed, round 2's 3 of 28, round 3's 2
   of 7, round 4's 0 of 5); the one left, `--no-optional-locks`, is checked by reading.
2. PASS `python3 scripts/check.py` (the self-test; `--settings` registers SessionEnd and the second SessionStart entry
   once, beside another tool's hook).
3. PASS (again after round 1) two headless `claude -p` (Haiku 5.5) sessions in a scratch repo with both hooks loaded by `--settings`: the
   first ended, its refresh ran as a `systemd-run --user` service (journal) and wrote the three files within seconds;
   the second quoted the SessionStart line and the exact `overview.md` path. The hook itself returned in 24 ms. Real
   systemd also kept a `$HOME` and a `%h` in a repo path literal (both graphs written).
4. PASS hard-reviewer (Fable 5.2) round 4, with the owner's leave for rounds 3 and 4. Round 1 FAIL (MAJOR: the merge
   rule contradicted the sdlc skill and the template); round 2 FAIL (MAJOR: a reading of the merge rule the owner had
   not given; the owner then answered "merge on its own, except a merge that publishes"); round 3 FAIL (MAJOR: a repo
   that publishes without saying so would merge); all fixed. Round 4 applied the rule to the real repos: power, tune,
   devbox, kit and steady ask; gate and platform merge on their own. NITs left: graph and saveit ask until their
   `CLAUDE.md` says a merge publishes nothing; the "HEAD moved since" fallback is untested.
