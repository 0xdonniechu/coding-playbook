---
name: sdlc
description: The artifact chain intent, plan, build, verify, ship for any piece of work big enough to need it in a repo. Use when you start a new feature or a large refactor, or say "write the intent", "follow the plan", "/sdlc". Not for a one-line fix, a quick diagnosis, or a one-off ops task.
---

# /sdlc

Each phase ends with an artifact committed to the repo. A later session (or another agent) only needs to read that file, not the chat history.

You are both the one who sets the requirements and the one who builds, so every approval gate comes down to one rule: **you approve the artifact before the next phase runs.**

The chain lives in the repo's `intent/` folder:

```
intent/
  2026-09-01-dark-mode.md        # WHY + WHAT (intent, approved)
  2026-09-01-dark-mode.plan.md   # HOW (plan, complete on its own)
```

Spec first, code after; verify layer by layer instead of reading every line.

---

## Phase 1: Intent (why + what)

When you describe a feature or a problem, the agent asks a few sharp questions (3 to 6) until the scope is clear: technical constraints, the systems affected, what is **not** done. Then it writes `intent/<yyyy-mm-dd>-<slug>.md`:

```markdown
---
status: draft   # draft → approved → planned → building → verified → shipped (PR #n)
---
# <Title>
## Problem
What hurts now, in your words.
## Outcome
What exists when this is done; the success criteria (measurable).
## Constraints
Tech, budget, policy (lean, no new dependency, …).
## Out of scope
What this work deliberately does NOT do.
## Open questions
None.
```

Mark every open point where it stands in the text as `[NEEDS CLARIFICATION: <question>]`, and list it under `## Open questions`. That section begins with `None` when nothing is open. Run

```
python3 <coding-playbook>/scripts/sdlc-check.py clarify intent/<yyyy-mm-dd>-<slug>.md
```

(`scripts/sdlc-check.py` in the coding-playbook repo) before the intent goes to `approved`, and again before the plan is written. It fails while any marker remains or `## Open questions` does not begin with `None`.

You edit it → `status: approved`, commit. **Do not write the plan before the intent is approved.**

For a new product: the intent must state how it earns money (who pays, and for what).

---

## Phase 2: Plan (how)

Feed only the intent file into plan mode. For large or architectural work, split the product review from the technical review before settling. Ask: "what could break?" Output `intent/<yyyy-mm-dd>-<slug>.plan.md`, the intent's own name with `.plan` before `.md` (converge finds the intent by that name):

- **Files**: every file that will be touched, in the order of work.
- **Risks**: what could break, and the check that would catch it.
- **Tasks**: one entry per builder dispatch, or per step the main session does itself.
- **Proof**: the commands or evidence that show it is done (test, build, screenshot, curl). "Done" is defined here, before any code is typed.
- **Result**: an empty heading for now, filled in Phase 4.

The plan starts with its own status line, `status: draft # draft → planned → building → verified`.

`## Tasks` has one `###` heading per task, then bullets:

```markdown
## Tasks

### T1 (builder, parallel) <title>
- allow: `src/feature/**` `tests/feature/**`
- forbid: `src/core/**`
- check: `make test`
- check: `make lint`

### T2 (main) <title>
- allow: `src/core/auth.py`
- check: `make test`
```

- Heading: `### T<n> (builder|main[, parallel]) <title>`. `builder` is dispatched to a builder; `main` is done by the main session. `parallel` means it may run beside another task, so it gets its own worktree.
- `- allow:` and `- forbid:` are globs in backticks, relative to the repo. `- check:` is one command in backticks per bullet, at least one per task.
- `- not needed: <reason>` marks a task dropped during the build.
- The plan and its intent need no `allow`: converge counts them as part of the plan.

A builder task is dispatched with `dispatch.py new <repo> <branch> --task <plan> <id>` (or `dispatch.py contract <tree> --task <plan> <id>`), so the contract comes from the accepted plan and not from flags typed by hand.

`## Proof` is a numbered list. `## Result` has one numbered item per Proof item, each beginning with `PASS`, `FAIL` or `not run: <reason>`, then the numbers (counts, commit, output):

```markdown
## Proof

1. `make test` passes.
2. `curl localhost:8080/health` returns 200.

## Result

1. PASS, 42 tests, 0 failed.
2. not run: the server needs credentials.
```

You accept the plan → `status: planned`, commit. The plan is the handoff contract: the implementing agent reads only the plan, not the chat.

---

## Phase 3: Build

The repo's normal rules apply (one logical unit at a time; a worktree if tasks run in parallel). In addition:

- If the work departs from the plan → **update plan.md in the same commit**. The diff must match the plan.
- When coding starts → `status: building`.

---

## Phase 4: Verify

Run exactly the **Proof** items in the plan, and fill `## Result`: one numbered item per Proof item, beginning `PASS`, `FAIL` or `not run: <reason>`. Then run

```
python3 <coding-playbook>/scripts/sdlc-check.py converge intent/<yyyy-mm-dd>-<slug>.plan.md
```

It lists each gap between the plan and the branch's diff: a changed path no task allows, a task never touched (and not marked `not needed`), a Proof item with no Result. It fails while any gap remains. A plan without `## Tasks` is reported and passes, so older plans stay valid.

The author does **not** approve their own work: it passes an independent review (`code-reviewer` or another review agent) with the intent and the plan as the contract. Give the reviewer converge's output together with the diff. Proof green → `status: verified`.

A mistake that happens a second time in any repo → write it down at once in that repo's `CLAUDE.md` or `lessons.md`.

---

## Phase 5: Ship

Merge following the repo's flow (feature branch → PR → main; or uat → main if the repo is set up that way). After the merge: `status: shipped (PR #n)` in the intent. The chain is closed, and git history is the audit trail.

---

## Phase 6: Maintain (the loop)

Health checks, cron jobs and alert emails can flag issues by themselves. Convention: an issue that is worth doing and bigger than a one-line fix starts with a new intent file in the repo that owns it. A small, bounded fix → a PR straight away, skipping the chain.

---

## Evals: regression for the process

An `evals/` folder per repo: one file per case, with a **Task** (a real prompt) and an **Expect** (a result that can be checked). Every production incident and every "the agent got it wrong" adds a permanent case.

Run the evals **before merging** a change to `CLAUDE.md`, a skill or a hook. If the config lowers the pass rate, do not merge. Five cases are better than none.

---

## Conventions used for real

- **Rate the difficulty before handing out work.** Rate four things: ambiguity, decisions that depend on each other, how easy it is to check, and the cost if it is wrong. None high is **EASY**: give it to an agent to do, no review. One high is **MEDIUM**: an agent builds, then another agent reviews. Two or more high is **HARD**: the main session does it itself. Each repo's `CLAUDE.md` gives its own examples for the three levels.
- **One ticket, one branch; one phase, one PR.** The intent is one PR; wait for approval before writing the plan. No push straight to `main`, no merge unless told to.
- **A ticket lives in two places** (the tracker and a GitHub issue), each linking to the other. The issue title carries the ticket code, for example `[AGD-2]`. When a ticket moves to another project, close the old one and leave a comment pointing to the new place.
- **One product, one repo.** A shared library is depended on by semver tag, never by branch.
- **A product that comes out of a teardown:** the intent points to `docs/spec/SPEC.md` as the WHAT, and does not rewrite the spec. When behaviour is missing from the spec, ask whoever owns the spec; do not decide alone.
- **Before pushing, check the GitHub account** with `gh api user --jq .login`. Do not change the active account; use `GH_TOKEN=$(gh auth token -u <account>)`.
- **Proof must be evidence that was run** (a command, a test count, a screenshot), not a claim. The reviewer judges the proof against the intent and the plan.

---

## When NOT to use

A one-line fix, a diagnosis, a one-off ops task: the chain is overhead. When in doubt: if it deserves a feature branch, it deserves an intent file.
