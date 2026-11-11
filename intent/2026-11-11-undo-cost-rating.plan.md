---
status: verified # draft → planned (owner accepts) → building → verified
---
# Plan: rate tasks by undo cost

Intent: `2026-11-11-undo-cost-rating.md` (approved). Ticket: Plane APS-63. HARD (a rating rule): the main session
does it; hard-reviewer (Fable 5.2) reviews.

## Tasks

### T1 (main) Rating text
- allow: `rores/global/CLAUDE.md` `skills/sdlc/SKILL.md` `CLAUDE.md` `intent/**`
- check: `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py`

## Proof

1. `python3 scripts/check.py` passes; `install.py --global` then `install.py --check` exit 0.
2. Review PASS by hard-reviewer (Fable 5.2): no item moved below HARD whose error no revert undoes.

## Result

1. PASS: `python3 scripts/check.py`; `install.py --global` and `install.py --check` run after the merge.
2. PASS: hard-reviewer (Fable 5.2) round 1 FAIL (2 MAJOR: auth and schemas read as cleanup undo, which loosened HARD in
   every repo; save-it moved to MEDIUM though its write guards are no-undo; 6 MINOR), all fixed; round 2 PASS with
   three MINOR (intent wording, what "a rule" means, "does not track"), fixed before merge.
