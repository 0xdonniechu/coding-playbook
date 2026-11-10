---
status: shipped (PR #30) # draft → approved → planned → building → verified → shipped (PR #n)
---
# One-command model switch: ready for Fable 5.5 to replace Fable 5.1

Ticket: Plane APS-47. Source: owner direction, 2026-11-08 ("Fable 5.5 is about to ship; get the whole process ready
for it to replace 5.1"). Comes after APS-45 (the switch kit, which decides whether it may) and before APS-46.

## Problem

Fable 5.1 has one role: `hard-reviewer`. Moving that role to another model today means editing by hand, in one PR,
the agent file's `model:`, its line in `global/CLAUDE.md` ("Subagents"), its README row and the "Current choice"
paragraph with the date and the switch test's numbers, then installing. `check.py` catches a mismatch between the pin
and `global/CLAUDE.md`, but not a stale README row, a missing date or numbers, a guessed ID, or a reviewer pinned to the
main session's own model (which defeats "a different model from the one that wrote the change"). On release day this
should be one command, already proven.

## Outcome

- `scripts/switch-model.py --role <agent> --to <model id> --note "<switch test numbers>" [--dry-run]` (standard
  library only). For one agent role (`builder`, `reviewer`, `hard-reviewer`, `transcriber`) it edits, in this repo's
  working tree only: the agent file's `model:`; the role's line in `global/CLAUDE.md`; the role's README row; and one
  dated line under "Current choice" (`hard-reviewer: Fable 5.5 since <date>, switch test: <note>`). It prints the diff,
  then runs `check.py`. It never commits, installs, or touches `~/.claude` or `settings.json`.
- It refuses: an ID that is not pinned by another agent and not listed in `switch-test/candidates.txt` (no guessed
  IDs); `hard-reviewer` or `reviewer` set to the main session's model as written in "Current choice"; an empty `--note`
  for a reviewer role; a role it does not know; a tree whose `check.py` fails before the edit.
- For the main session (question (b) of the kit), `--role main` edits only the docs ("Current choice", README) and
  prints the `/model <id>` and effort lines the owner runs; `settings.json` stays owner-only.
- A self-test (run by `check.py`) on a scratch copy of the repo: switching `hard-reviewer` to a placeholder ID changes
  exactly the expected lines and `check.py` passes on the copy; switching back restores the files byte for byte; a
  second identical run changes nothing; each refusal above fires.
- `switch-test/RELEASE-DAY.md` step 7 uses the command; `global/CLAUDE.md` "Switching models" step 3 names it.

Success: the self-test passes in `check.py`; a dry run on this repo with the stand-in ID `claude-opus-5-5` for
`hard-reviewer` is refused (it is the main session's model), and with a placeholder listed in a scratch
`candidates.txt` prints the full diff.

## Constraints

- The switch still happens only when the switch test passes (owner decision 2026-11-08): the command is the tool for
  that PR, not a gate around it. The owner merges the switch PR.
- The kit's yardstick stays: `replay_reviewer` and the baseline remain Fable 5.1, a model different from both Opus 5.5
  and the candidate.
- HARD (model switching is on this repo's HARD list): the main session builds it, `hard-reviewer` reviews.

## Out of scope

- Switching any model now; changing the switch test's rule or thresholds.
- Editing `settings.json` or the installed `~/.claude` (the owner runs `/model`; `install.py` runs after the merge).
- Other repos (none pins Fable 5.1 today: checked 2026-11-08), APS-46.

## Open questions

None.
