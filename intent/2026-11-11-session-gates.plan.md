---
status: building # draft → planned (owner accepts) → building → verified
---
# Plan: session gates for rules that slipped

Intent: `2026-11-11-session-gates.md` (approved). Ticket: Plane APS-66. HARD (a hook in every session: a gate that
wrongly refuses stalls every session): the main session (Opus 5.5) builds; hard-reviewer (Fable 5.2) reviews.

## Tasks

### T1 (main) The hook and its registration
- allow: `gates/session-gates.py` `.claude/branch-name.json` `scripts/install.py` `scripts/check.py` `CLAUDE.md` `README.md` `docs/internals.md` `intent/**`
- check: `python3 gates/session-gates.py --self-test`
- check: `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py`

## Proof

1. Self-test passes; every hand-made mutation of the gates is caught (round 2: 36 of 36, covering quoting, heredocs,
   subshells, `cd`/`pushd`, `-C`, branch create/rename/push refs, `dispatch.py new` options, git write verbs and reads,
   `gh pr merge`, stale agents, SubagentStop, `clear`, the edit tools, lesson status and hint once). The `match:` field
   was dropped: shared-memory lessons have no such field (its `check.py` FIELDS), so lessons match by backticked tokens.
2. `check.py` passes, including `install.py --settings` registering both entries once.
3. After merge: `install.py --settings`, then a live check in this session (a wrong branch name refused).
4. Review PASS by hard-reviewer (Fable 5.2).

## Result

- Round 1 (hard-reviewer): FAIL, 2 MAJOR (parser split inside quotes and heredocs; self-test missed 15 of 18 mutations) and
  MINORs. Round 2: quote- and heredoc-aware reader, subshells, wider write and push coverage, flock state, Read/Grep/Glob
  recorded for subagents, 36 of 36 mutations caught; check.py PASS.
- Round 2 (hard-reviewer): PASS; two post-PASS deltas (cb28f23, 2242e74) confirmed PASS. Follow-ups recorded on APS-66:
  flock not self-tested, multi-line quoted `<<`, non-identifier heredoc delimiters, paths only inside quoted strings,
  memory pulls refused while a subagent read memory, pushes to `main` not held here, lesson recall coverage (3 of 46),
  shell keywords and line continuations.
