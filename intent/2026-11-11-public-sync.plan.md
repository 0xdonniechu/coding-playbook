---
status: building # draft → planned (owner accepts) → building → verified
---
# Plan: keep the public coding-playbook in step

Intent: `2026-11-11-public-sync.md` (approved). Ticket: Plane APS-65. HARD (what it writes is published; no revert
takes it back): the main session (Opus 5.5) builds; hard-reviewer (Fable 5.2) reviews.

## Tasks

### T1 (main) Sync script and rule
- allow: `scripts/sync-public.py` `public-sync.json` `scripts/check.py` `.gitignore` `CLAUDE.md` `README.md` `docs/internals.md` `intent/**`
- check: `python3 scripts/sync-public.py --self-test`
- check: `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py`

## Proof

1. Self-test passes; each guard mutated once (dirty tree, main, detached, behind public main, leak, leak in an added
   file, public-only, rewrite scope, rewrite, delete, mode report, mode write, review changed, review unknown commit,
   exit 3, public ref, config from the ref, `--reviewed` guard) is caught. Round 3 adds: a source ref fixed in the
   script, a failed fetch (report exit 2, write and review refused), public-only missing on both sides, `--reviewed`
   before the commit and only against the synced commit, a directory replaced by a file, submodule, symlink in a tree,
   an ignored symlink, state shape and state kept across writes: 14 new mutations and every applicable round 2
   mutation caught.
2. `check.py` passes.
3. The first real sync: `--write` on a branch of the public clone, its `check.py`, then `sync-public.py` reports in step.
4. Review PASS by hard-reviewer (Fable 5.2).

## Result
- Round 1 and 2 (hard-reviewer): FAIL. After round 2 the owner allowed a third round ("proceed", 2026-11-11).
  Round 3 fixes: internal names out of `docs/internals.md`, `.claude/branch-name.json` missing on both sides counts as
  in step, the diff is read with `git add -A && git diff --cached` and `--reviewed` runs before the commit, plus the
  MINORs above.
- Round 3 (hard-reviewer): PASS, 4 MINORs; three were missing self-test cases, now added (fixed source ref, write after a
  failed fetch, leak in an updated file); the fourth is Proof 3, which runs after this merge.
