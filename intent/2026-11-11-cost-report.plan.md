---
status: verified # draft → planned (owner accepts) → building → verified
---
# Plan: cost report per role and ticket

Intent: `2026-11-11-cost-report.md` (approved). Ticket: Plane APS-64. MEDIUM (a read-only report; a revert undoes it):
builder (Sonnet 5.5) builds, reviewer (Opus 5.5) reviews.

## Tasks

### T1 (builder) The report
- allow: `scripts/cost-report.py` `scripts/model-prices.json` `scripts/check.py` `README.md` `docs/internals.md`
- check: `python3 scripts/cost-report.py --self-test`
- check: `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py`

## Proof

1. Self-test and `check.py` pass.
2. A run on this machine's transcripts since 2026-11-11, by role and by model.
3. Review PASS by reviewer (Opus 5.5).

## Result

1. PASS: `python3 scripts/cost-report.py --self-test` and `check.py` (4G cap).
2. PASS: real transcripts since 2026-11-11 (reviewer run): 824 responses, $82.41, 71% without a ticket. By role at
   the build: main $43.80, hard-reviewer $26.90, reviewer $3.37, builder $1.03. Models without a price
   (`claude-fable-5-1`, `claude-sonnet-5`) are counted with cost unknown.
3. PASS: reviewer (Opus 5.5) round 1 FAIL (MAJOR: the fullest-line dedupe was untested; 2 MINOR), fixed by the
   builder; round 2 PASS, 9 mutations caught; one MINOR left (the no-timestamp count is taken before the project and
   ticket filters; no real line lacks a timestamp).
