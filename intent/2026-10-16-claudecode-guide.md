---
status: verified   # draft → approved → planned → building → verified → shipped (PR #n)
---
# Claude Code guide: one model economy for every Ambysto repo

Ticket: Plane APS-22. Source: the owner's guidelines folder (a model-economy draft written for another project), made universal and fitted to the Ambysto repos on 2026-10-16.

## Problem

Six Ambysto repos rate their work HARD / MEDIUM / EASY in `CLAUDE.md` and name a builder (Sonnet), a reviewer (Opus) and a transcriber (Haiku). But no agent files existed on the owner's machine, so the delegation was on paper only. The draft agents were written for another project (its test command and its domain rules), the global file was never installed, and every model was an alias that upgrades silently.

## Outcome

A private repo with the global instructions, four universal agents, the project template, a check script and an installer (see `README.md`).

## Decisions (owner, 2026-10-16)

1. **Main session: Opus 5.5.** On cost and quality it is ahead of Fable 5.1. Revisit when Fable 5.5 ships, by the switch test in `global/CLAUDE.md`.
2. **HARD work: Opus does it, Fable reviews it.** A reviewer from a different model does not share the author's blind spots. MEDIUM review stays on Opus.
3. **Model and effort live where they take effect.** The main session's model and effort are set in `~/.claude/settings.json` (done on the owner's machine: `claude-opus-5-5`, effort `high`), and each subagent's model and effort are set in its agent file. `CLAUDE.md` only records the choice.
4. **Pinned, never aliases.** Every model is a full model ID, so an upgrade is always a decision.
5. **A repo of its own, private.**
6. **Measure the owner's time (owner, 2026-10-18).** Every intervention is logged (`global/CLAUDE.md`, "Owner time log") and counted by `scripts/hil-report.py`: how many, how often and how long, by kind and trigger. Credit top-ups and incidents a model could not know on first contact are not loop defects.
7. **Lessons are guidance, not gates (owner, 2026-10-18).** A lesson that holds in more than one context goes into the global working practice. A lesson for one project stays in that project's CLAUDE.md. A lesson becomes a gate only when the project decides so.
8. **Main session effort: `medium` (owner, 2026-10-18).** Replaces the `high` of decision 3 (briefly `low` the same day); subagent efforts are unchanged.

## Success criteria

| # | Criterion | How it is checked |
|---|---|---|
| 1 | Frontmatter valid, models pinned, reviewer bodies equal, global and template sections present | `scripts/check.py` PASS. Mutation-checked: an alias model and an edited `hard-reviewer` body each make it FAIL |
| 2 | The owner's machine runs the repo's agents | `scripts/install.py --check` exits 0 |
| 3 | Each agent starts with its pinned model | a new session after install, one run per agent; each reports the model ID it runs as |

## Proof

1. `check.py`: PASS. Mutation: `model: sonnet` in `builder.md` → FAIL; a line appended to `hard-reviewer.md` → FAIL; both restored → PASS.
2. `install.py --check` on the owner's machine: the four agents are unchanged; the global block is not installed (optional); `settings.json` reports `model=claude-opus-5-5 effort=high`. Exit 0.
3. New session on the owner's machine, 2026-10-16, after `install.py --check` exit 0. Each agent was run once on a read-only task (one-line summary of `README.md`) and reported its model ID: builder `claude-sonnet-5-5`, reviewer `claude-opus-5-5`, transcriber `claude-haiku-5-5`, hard-reviewer `claude-fable-5-1` (asked after a real review of ambysto-space PR #14). All four equal the pinned IDs; no model ID was rejected. The ID is what each agent reads from its own system prompt. `/agents` was not run: it is an interactive screen; the session started after the install, so the agents were loaded from the installed files.

## Review log

**Round 1 (hard-reviewer: Fable 5.1, FAIL, 2026-10-16).** The 4 MAJOR issues and 3 of the 4 MINOR issues are fixed; MINOR 8 is noted in `CLAUDE.md` (Open).
1. MAJOR: `install.py` lost the owner's text when the markers were out of order or orphaned. Fixed: anything but exactly one begin before one end is refused (exit 2) and nothing is written.
2. MAJOR: a second run the same day overwrote the backup. Fixed: backups are named to the second and never overwritten.
3. MAJOR: `check.py` passed differing reviewer bodies when both frontmatters were unclosed. Fixed: an unclosed frontmatter fails.
4. MAJOR: the template's HARD line named reviewer, not hard-reviewer. Fixed, and `check.py` now checks it.
5. MINOR: builder said "the main session takes over" while global said "stop and ask", and the word limits differed. Aligned.
6. MINOR: model drift between global and the agents went unseen, and missing files crashed `check.py`. Both now FAIL.
7. MINOR: a non-UTF-8 `CLAUDE.md`, a null or BOM `settings.json` and CRLF files crashed or were rewritten. Fixed: refused, reported or preserved.
8. MINOR: agent limits are prompt-only. Noted, not fixed.

Re-run after the fixes (temp HOME and a temp copy of the repo, recorded 2026-10-16): the reviewer's experiments T1–T7 and T9–T10, plus CRLF preservation, an idempotent second install and a reviewer given Write, all behave as fixed; `check.py` PASS on the real repo.

**Round 2 (hard-reviewer: Fable 5.1, PASS, 2026-10-16).** All round-1 items were verified as fixed (item 8 noted). Five MINOR issues were found and fixed after the PASS, then checked by mutation:
1. A pinned ID with a date suffix, or a quoted `model:` value, was refused. Both are now accepted.
2. A reviewer given `Edit` or `NotebookEdit` passed. Any writing tool now fails.
3. `--check` exit 2 was not documented. README and `CLAUDE.md` now document it.
4. `--check` on a non-UTF-8 `CLAUDE.md` passed silently. It now exits 2.
5. Effort drift between the agents and `global/CLAUDE.md` went unseen. It now fails, as does a difference in effort between reviewer and hard-reviewer.
Not changed: in a file with mixed line endings, the block is written with CRLF (cosmetic; the owner's lines are kept byte for byte).
