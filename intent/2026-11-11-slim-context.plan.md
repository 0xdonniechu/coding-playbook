---
status: verified # draft → planned (owner accepts) → building → verified
---
# Plan: slim the context every session loads

Intent: `2026-11-11-slim-context.md` (approved). Ticket: Plane APS-62. HARD (the rules every session follows): the
main session (Opus 5.5) does it; hard-reviewer (Fable 5.2) checks that no rule was lost or changed.

## Tasks

### T1 (main) Global instructions
- allow: `rores/global/CLAUDE.md` `skills/sdlc/SKILL.md`
- check: `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py`

### T2 (main) This repo's CLAUDE.md and docs/internals.md
- allow: `CLAUDE.md` `docs/internals.md` `README.md` `intent/**`
- check: `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py`

## Proof

1. Word counts before and after for `~/.claude/CLAUDE.md`, `rores/global/CLAUDE.md` and `CLAUDE.md`.
2. A rule-by-rule list (old sentence → where it is now) checked by hard-reviewer: nothing lost or changed.
3. `python3 scripts/check.py` passes; after `install.py --global`, `install.py --check` exits 0.
4. Review PASS by hard-reviewer (Fable 5.2).

## Result

1. PASS: word counts (`wc -w`), before → after: `~/.claude/CLAUDE.md` 3920 → 2870 (the Ubuntu machine section,
   1017 words, now in `~/work/ambysto/CLAUDE.md`, loaded only by sessions started under `~/work/ambysto/`);
   `rores/global/CLAUDE.md` 2922 → 2680; this repo's `CLAUDE.md` 3857 → 1022 (`docs/internals.md` 3237, verbatim).
2. PASS: rule-by-rule check by hard-reviewer. Round 1: every moved bullet byte-verbatim in `docs/internals.md`, all
   12 HARD items still HARD, the machine section moved whole; one changed rule (MAJOR: owner-token-guard put under
   "never block a session") and five MINOR. The MAJOR and four MINOR were fixed; one (an owner decision of
   2026-10-23 now only in `docs/internals.md`, with a pointer) was accepted by the reviewer as is.
3. PASS: `python3 scripts/check.py`; `install.py --global` then `install.py --check` exit 0.
4. PASS: hard-reviewer (Fable 5.2) round 1 FAIL, round 2 PASS with three MINOR (guard wording, this Result's
   format, the mirror), all addressed; the mirror is its own PR on `0xdonniechu/coding-playbook`.
