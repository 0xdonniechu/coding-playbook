---
status: shipped (PR #75) # draft → approved → planned → building → verified → shipped (PR #n)
---
# Adopt diff floor guard, skill routing checks, and reviewer/sdlc refinements from agent-skills

Ticket: Plane APS-77. Source: evaluation of `addyosmani/agent-skills` on 2026-11-13.

## Problem

1. `scripts/sdlc-check.py converge` checks whether changed paths stay inside the plan's tasks and whether each task's `check:` commands exit 0, but does not inspect the diff for bar-lowering moves (added linter or type-checker suppressions, skipped or deleted tests, or removed assertions) before handing the work to the reviewer.
2. `scripts/check.py` checks skill frontmatter length and YAML syntax, but does not check whether two skills' descriptions near-collide lexically or whether each skill ranks #1 on representative trigger prompts and not #1 on sound-alike prompts for other skills. Also, `split_frontmatter` reads only the `description:` line itself, so a multi-line YAML block scalar (`description: |`) has an empty description in `check.py`.
3. `skills/sdlc/SKILL.md` Phase 1 asks clarifying questions without requiring a best-guess default attached to each question, and `rores/agents/reviewer.md` (and `hard-reviewer.md`) does not explicitly call out silent bar-lowering (new suppressions, skipped/deleted tests, stripped assertions) in its checklist.

## Outcome

1. `scripts/sdlc-check.py converge` inspects the branch diff (tracked changes since the merge base plus untracked files, excluding the plan and its intent) and reports `floor:` notes in its output (handed to the reviewer) whenever a change adds a linter/type suppression (`# noqa`, `# type: ignore`, `// @ts-ignore`, `// @ts-expect-error`, `eslint-disable`), adds a test-skip marker, deletes a test file, or removes more `assert` lines than it adds in a file.
2. `scripts/check.py` parses folded/block `description: |` frontmatter lines, checks that no two skills in `skills/` have TF-IDF cosine similarity above `0.60`, and verifies that every skill in `skills/` ranks #1 on its positive trigger prompts and not #1 on its negative sound-alike prompts.
3. `skills/sdlc/SKILL.md` Phase 1 instructs the agent to attach its best guess (default or recommendation from the codebase) to each clarifying question so the owner can confirm in one word.
4. `rores/agents/reviewer.md` and `rores/agents/hard-reviewer.md` explicitly check for silent bar-lowering (new suppressions, skipped/deleted tests, stripped assertions) under Rules held and Tests.

## Constraints

- Standard library Python only; no new dependencies or external tools.
- `floor:` notes in `sdlc-check.py converge` are informational notes printed in `converge` output (not blocking gaps that break legitimate suppressions in a one-prompt run), so the reviewer sees every bar-lowering line with `file:line` without deadlocking `loop-stop.py`.
- Keep `rores/agents/hard-reviewer.md` body identical to `rores/agents/reviewer.md`.

## Out of scope

- Adopting the 25 generic coding skills or the in-place file-rewriting `simplify-ignore` hook from `addyosmani/agent-skills`.
- Adding a WebFetch cache hook (not needed in the core playbook).

## Open questions

None.
