---
status: shipped (PR #43; intent #41, plan #42) # draft → approved → planned → building → verified → shipped (PR #n)
---
# Tasks, converge and clarify in the sdlc chain; the sdlc skill moves into this repo

Ticket: Plane APS-51. Source: owner 2026-11-10, after reading GitHub Spec Kit (`github.github.com/spec-kit`): "áp
dụng Task, converge & clarify", without installing Spec Kit itself. Where the skill lives (owner answer,
2026-11-10): in this repo, `skills/sdlc/`.

## Problem

1. **The skill has no home.** `/sdlc` runs from `~/.claude/skills/sdlc/SKILL.md`, a hand copy with no git. Its
   source is a personal repo outside Ambysto, and the copy has already drifted from it. `install.py` does not install
   it and `check.py` does not check it, so a change to the chain reaches no other machine and nothing catches a broken
   skill file.
2. **Plans do not name the dispatches.** A plan lists files, risks and proof, but not which builder gets which files
   and checks. For every dispatch the main session types the contract again by hand (`dispatch.py --allow … --check
   …`), and nothing ties that contract back to the accepted plan.
3. **"Matches the plan" is checked by eye.** At verify the main session reads the diff against the plan's file list
   and looks for each proof result itself. A file changed outside the plan, or a proof item never run, is caught only
   if the session or the reviewer notices.
4. **Open points hide in the text.** An intent's "Open questions" is free text. A question left inside Problem or
   Outcome, or a non-empty Open questions section, does not stop a plan from being written.

## Outcome

1. **The skill in this repo.** `skills/sdlc/SKILL.md` holds the skill, from the installed copy plus the changes below,
   in English like the repo's other two skills. `install.py` installs it over the hand copy (a differing file is backed
   up first, as for every skill); `check.py` requires it. The unused upstream sdlc link in `~/.claude/skills` is gone
   (removed 2026-11-10).
2. **Clarify.** An intent marks every open point where it stands as `[NEEDS CLARIFICATION: <question>]`, and lists
   it under Open questions. A check fails while any marker remains or Open questions is not "None". The skill says to
   run it before an intent goes to `approved`, and again before a plan is written.
3. **Tasks.** A plan has a `## Tasks` section: one entry per builder dispatch, or per step the main session does
   itself (HARD), each with an id, what it builds, its allowed and forbidden paths, its checks, and whether it may run
   beside another task. `dispatch.py` can build a contract from one entry (`new … --task <plan> <id>`,
   `contract … --task <plan> <id>`) instead of flags typed by hand; the hand flags keep working.
4. **Converge.** A check compares a plan with a branch's diff: every changed path is inside the plan's files or a
   task's allowed paths, every task has been touched or is marked not needed, and every Proof item has a recorded
   result in the plan (passed with numbers, failed, or "not run: <reason>"). It lists each gap and fails while any
   remains. The skill's Verify phase runs it before the review, and the reviewer gets its output with the diff.
5. `global/CLAUDE.md` ("The loop") names `--task` and the converge check in one line each.

Success: self-tests for the clarify and converge checks and for `dispatch.py --task` (a sample intent and plan in a
scratch repo: a marker fails, "None" passes; an out-of-plan file, an untouched task and a proof without a result each
fail; a contract built from a task equals the one built from the same flags). Then this ticket's own plan is written
with a Tasks section, and its build is verified with the converge check.

## Constraints

- Standard library Python only; no Spec Kit install, no `uv`, no download; Linux, macOS and Windows.
- Existing intents and plans (no markers, no Tasks section) stay valid; the checks apply to plans that have the new
  sections, and `dispatch.py` without `--task` behaves as today.
- `dispatch.py` writes the builder's contract, which agent-guard enforces: a wrong contract from `--task` is a security
  error, so that part is HARD (the main session builds it, hard-reviewer reviews).
- The checks report and fail; they never edit an intent or a plan.

## Out of scope

- Spec Kit's own layout and commands (`.specify/`, numbered `specs/`, constitution, `/speckit-*`); the repo's
  `CLAUDE.md` stays the constitution.
- The personal repo the skill came from, and the upstream skills repo (its `setup` script would link its own sdlc
  again if run; it is not run here).
- Running the checks from a hook, or making them gates in other repos; each repo opts in through its own Verify.
- Spec Kit's other extras (checklists, idea assessment, bug extension).

## Open questions

None.
