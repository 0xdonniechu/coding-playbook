---
status: building # draft → planned (owner accepts) → building → verified
---
# Plan: session gates follow-ups

Intent: `2026-11-11-session-gates-follow-ups.md` (approved). Ticket: Plane APS-67. HARD (a hook in every session, and
the lesson format of ambysto-memory): the main session builds; hard-reviewer (Fable 5.2) reviews both diffs.

## Tasks

### T1 (main) The hook
- allow: `gates/session-gates.py` `.claude/branch-name.json` `docs/internals.md` `README.md` `CLAUDE.md` `intent/**`
- check: `python3 gates/session-gates.py --self-test`
- check: `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py`

### T2 (main) Lesson `match:` in ambysto-memory (branch `aps-67-lesson-match`; the owner merges)
- check: `python3 -m unittest scripts/test_check.py scripts/test_wire.py` (in ambysto-memory)

## Proof

1. Self-test passes; every hand-made mutation of the new code is caught, or named as equivalent.
2. `check.py` passes; memory unit tests pass and their `match` test catches its mutations.
3. After merge: `install.py --settings`, then a live check (a push to `main` refused).
4. Review PASS by hard-reviewer (Fable 5.2).

## Result
- Hard review (Fable 5.2) of d5f9a78 and memory e02aaa5: PASS with MINOR follow-ups; the owner asked to resolve what is
  left, so they were fixed before merge (push --all/--delete/--tags under no_push, `$(( ))`, `-sd`, sudo/timeout/xargs,
  quoted `match:` values, remote paths, path cap, narrower lesson regexes, self-test gaps). Delta sent back for review.
- Delta reviews (313be77, 3b57ef0): PASS. Left as follow-ups on APS-67: quoted `$(( ))` and bare `(( ))` read as heredocs;
  `--all` with no local guarded branch untested; two performance caps untested.
