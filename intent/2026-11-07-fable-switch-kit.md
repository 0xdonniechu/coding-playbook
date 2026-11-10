---
status: shipped (PR #26) # draft → approved → planned → building → verified → shipped (PR #n)
---
# Model switch kit: ready for Fable 5.5 before it ships

Ticket: Plane APS-45. Source: owner request, 2026-11-07.
Sibling: APS-46 (per-dispatch task contract, path check, worktrees for parallel builders) gets its own intent after
this one is approved.

## Problem

`global/CLAUDE.md` defines the switch test in three lines ("pick 2-3 past diffs whose findings are on record, run the
candidate as reviewer without the old findings, count"), and `CLAUDE.md` lists "the switch test runs when Fable 5.5
ships" as open. Nothing is prepared:
- No diffs are chosen and no known findings are written down, so on release day someone must dig through PRs and
  review logs first, under pressure to switch.
- There are no baseline numbers for today's models (Fable 5.1 as hard-reviewer, Opus 5.5 as reviewer), so "catches at
  least as many known issues" has nothing to compare against.
- The test only measures reviewing. It cannot answer the second question the owner wants answered: should Fable 5.5
  replace Opus 5.5 as the main session. If it does, `hard-reviewer` must move off Fable, since it must be a different
  model from the one that wrote the change.

## Outcome

1. **Cases.** 3 cases in the repo, at least one HARD: each names a repo, a base and head commit, the task text the
   reviewer would have had, and the known findings (from PR comments or review logs) with their severity.
2. **Runner.** One documented way to run any model ID as reviewer on every case, given a diff range and never the
   known findings, recording per case: known issues caught, new real issues, false alarms, tokens and cost, effort.
3. **Baseline.** The kit run once each with `claude-fable-5-1` and `claude-opus-5-5` at the efforts in the agent files,
   numbers committed. The owner judges "new real issue" vs "false alarm"; the kit records the owner's verdict.
4. **Main-session check, question (b).** One past HARD task replayed from its approved plan by the candidate as main
   session in a scratch worktree, then reviewed by a model other than the candidate; record review rounds, BLOCKER and
   MAJOR issues, cost. Baseline: the same replay by Opus 5.5.
5. **Release-day sheet.** A checklist in the repo: fill in the real Fable 5.5 ID, run 2 and 4, compare with 3, then
   the decision table:
   - (a) Fable 5.5 ≥ Fable 5.1 on known issues at acceptable cost → `hard-reviewer` moves to Fable 5.5.
   - (b) Fable 5.5 ≥ Opus 5.5 as main session → the owner decides; if yes, `hard-reviewer` moves to Opus 5.5 and the
     builder/reviewer pins are reconsidered in the same PR.
   Whatever wins, the existing rule holds: `settings.json` (by the owner), every agent file and the "Current choice"
   line change in one PR with the numbers.

Done when: cases, runner, sheet and baseline numbers are merged, and a dry run of the release-day sheet with
`claude-opus-5-5` standing in for the candidate goes through end to end.

## Constraints

- No model change now. No agent file's `model:` or `effort:` changes. No Fable 5.5 ID is guessed or written anywhere
  until it is published.
- The candidate never sees the known findings. A run whose transcript shows it read the cases' findings is void.
- Reviewers get a diff range and read files with `git show`, never a checkout (lesson
  `give-reviewers-a-diff-range`).
- Universal repo: cases may name Ambysto repos and commits (they are data, not rules) but live outside `agents/`,
  `global/` and `skills/`; nothing secret.
- Cost: the baseline (2 models × 3 cases, plus 1 replay by Opus 5.5) is a one-time spend with no ceiling (owner decision
  2026-11-07); the plan still states the estimate, and the kit records the actual cost per run.
- English only; Ambysto account; no Co-Authored-By trailer; PR per phase; the owner merges.

## Out of scope

- APS-46: task contract, path allowlist in `agent-guard.py`, worktree rule.
- A Haiku-based command gate.
- Switching any model, or changing the main session's model or effort in `settings.json`.
- Automating the owner's "real vs false alarm" judgement.
- macOS anything.

## Decisions (owner, 2026-11-07)

1. Cases come from PRs with a recorded reviewer FAIL: aps-32 (agent-guard), aps-34 (boundary hook), and one app repo
   change; the plan names the exact commits and findings.
2. Question (b) starts with one HARD-task replay; a second only if (a) and (b) disagree.
3. No budget ceiling.

## Open questions

None.
