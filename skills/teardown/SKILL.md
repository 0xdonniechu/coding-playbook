---
name: teardown
description: Decompose an existing product to understand its internals, write a clean-room specification, and build your own version in a fresh session that reads only the spec. Uses the industry-standard two-team clean-room method to learn from competitors lawfully. Triggered when saying "teardown", "decompose product", "reverse engineer", "build something like X", or "how does product X work".
---

# /teardown

Learn from competitors by decomposing, not by copying. Two teams, one wall:
Team A inspects the original product and writes the specification; Team B reads only the specification and builds. Team B has never seen the original product, so what gets built is cleanly yours.

This method has real legal precedent: a small company decomposed IBM PCs using this exact two-team clean-room model, was sued by IBM, and won—because the build team had never seen the original code or hardware schematics. From that landmark case, the tech industry established lawful teardown and clean-room reverse engineering.

## When to use

After `/market-research` has identified which market segment to enter. Market research answers "which segment to enter"; teardown answers "how the reference product works so we can build our own version". Reversing this order means decomposing a product before knowing whether it is worth building.

## Step 0 — Is it worth building? Answer before spending hours

Write down the answers to three questions:

1. Why this product, why now, and who specifically is YOUR target user?
2. What is your wedge: replicate the core table-stakes plus improve 10x on which exact pain point?
3. Are you building for personal use, shipping publicly, or raising capital / commercializing at scale? The further you go, the stricter the clean-room rules below must be enforced from day one.

If answering these leads to "not worth building yet", stop here. That is a successful outcome, not a failure.

## Step 1 — Gather sources (public sources only)

Collect everything into an `input/` directory: demo videos, landing pages, pricing pages, documentation, screenshots, and the repository if open-source. For videos, feed the agent the transcript plus timestamped frame captures (use [watch-cli](https://github.com/sonpiaz/watch-cli) or capture key frames manually).

**Use public sources only.** Never crack binaries, never access someone else's authenticated data, and never purchase accounts to extract proprietary source code.

**Team A's directory must live outside every product repository.** Place it alongside the repo (e.g., `research-<category>/`), never inside the product repository, and do not name it after the reference product. Never commit `input/`, `analysis/`, or audit notes into the repository where code will be built. If the reference product uses a copyleft license (GPL, AGPL), this rule is even stricter: a single leaked snippet in a proprietary repo can contaminate the entire product. Before cloning any repo, record the reference product's license and version in `step0.md`.

## Step 2 — Decompose to the core, not the surface shell

From `input/`, have the agent extract structured analysis files:

```
features.md        what the product does, feature by feature
ui-states.md       screens, states, and user flows
api-endpoints.md   how the client communicates with the backend
tech-stack.md      runtime, what is built in-house vs. rented third-party services
pricing.md         tier prices and billing unit · required column
```

**For desktop apps or system utilities:** replace `api-endpoints.md` with `system-interfaces.md`. Desktop/system tools rarely rely on server APIs—their core logic lives in how they interact with the OS. Document: OS services used; permissions and entitlements requested; privileged helper components; inter-process communication (IPC) channels; files and directories written; and fallback behavior when permissions are denied or a helper crashes.

Every analysis file should end with a **"Gaps"** section listing what the reference product does not do or does poorly. Your Step 4 wedge almost always comes from this section.

**Clean-room rule (non-negotiable):** in all analysis files, describe behavior in your own words. Paste NO MORE than 3 lines of code, and never copy prose longer than a single sentence verbatim. Verbatim strings are permitted only for short factual UI labels or error codes.

## Step 3 — Write the clean specification (`SPEC.md`)

From the analysis files, write `SPEC.md`: for each feature, specify what the user gets, what triggers it, inputs and outputs, state transitions, error handling, and **what it explicitly does NOT do in v1**.

Include two mandatory sections that the build agent needs from line one:

- **"Glossary" at the top of the file.** Every domain concept (e.g., "rule", "pending connection") gets exactly one canonical name used consistently everywhere. Most questions in the first wall-test round happen because one concept is referred to by two different names.
- **"Open Questions for Product Owner" at the bottom of the file.** Record any behavioral default you chose that requires owner sign-off. Once approved, rename this section to "Locked Decisions" with the approval date. The spec cannot cross the wall until this section has zero open questions.

### Run the Wall Test as an iterative loop until zero blockers remain

A single wall test is never enough. For stateful products (firewalls, sync engines, editors), it typically takes 6 to 8 rounds to reach zero blocking questions. Run each round as follows:

1. Copy **only** `SPEC.md` into a clean temporary directory, e.g., `wall-test<N>/`.
2. Spawn a **FRESH** agent that has zero context from the current session. Instruct it to read only that file and plan the build using the prompt below.
3. Classify every behavioral question into one of two buckets:
   - **BLOCKER:** two strong engineers reading the spec would build two visibly different user-facing behaviors. Update the spec to resolve it.
   - **MINOR:** a reasonable default exists. Write that explicit default into the spec so future rounds never ask again.
4. Before editing, archive the current spec as `SPEC.round<N>.md`. This gives you a rollback point and lets you track whether blocker counts are converging across rounds.
5. **Expand scope progressively.** Round 1 scopes only the core engine (e.g., decision precedence). Subsequent rounds expand to full v1. A slight bump in blockers when expanding scope is normal.
6. **Stop only when a round returns 0 BLOCKER questions** and every MINOR question has an explicit default in the spec. Answering the last round's blockers does not count as finished—you must run one confirmation round that returns `0` blockers cleanly.
7. **In the final rounds, run 2 independent agents concurrently on the exact same spec.** Two agents will surface different minor edge cases; any blocker raised by both agents pinpoints a genuine spec weakness to fix first.

Prompt for the wall-test agent:

```
Read ONLY <path>/SPEC.md. Do not read any other files, repositories, or web pages.
Do not edit any files. Plan the build for <scope>. For every place where you would
have to ask the product owner about BEHAVIOR (what the user sees, what is allowed,
edge-case handling) because the spec is silent, ambiguous, or contradictory, write
one question. Do not list technical implementation choices. Classify each question
as BLOCKER or MINOR; for MINOR questions, include the default you would choose.
Return: counts per category, the two lists, and a one-line verdict on whether Part 1
can be built today without guessing behavior.
```

Real production benchmark: the firewall spec for a desktop security app saw blocker counts progress across 8 rounds as `21 -> 7 -> 4 -> 5 (scope expanded to full v1) -> 2 -> 2 -> 2 -> 0`. The penultimate three rounds each had 2 blockers, but each round uncovered deeper state interactions (e.g., an app matching two trust toggles simultaneously)—a sign of convergence, not stagnation. The final round ran 2 independent agents, both returning `0` blockers.

## Step 4 — Choose your own name and lock your wedge

- **Pick an original product name completely distinct from the reference product.** Ban all `X-clone`, `X-port`, or `my-X` naming in folders and repos. Directory names live permanently in git history; a `stripe-clone` folder name is an admission against interest in any future audit.
- **First-principles audit:** ask "if I didn't know the reference product existed, what is the minimum viable spec that solves my user's exact pain?". Compare against `SPEC.md`:
  - Features in `SPEC.md` absent from your first-principles answer should be cut or deferred.
  - Capabilities in your first-principles answer missing from `SPEC.md` form your **wedge**. Without this step, you end up building a 5%-better clone rather than a 10x differentiated product.
- Record the audit in `audit.md` as a three-column table: **What the reference product does** | **Our decision** | **Why**, ending with a one-sentence wedge statement. Because `audit.md` names the reference product, it stays strictly on Team A's side and never crosses the wall.
- **`SPEC.md` must never mention the reference product's name anywhere**, not even for comparison. If a build agent sees the competitor's name, it has a cue to search for or mimic the original.

## Step 5 — Build behind the wall (Team B)

Open a **new directory and a fresh agent session**. Copy across **only two files**: `SPEC.md` and `V0.1-TASKS.md`. Start that session with:

```
Read only SPEC.md in this directory. Do not read anything outside it.
Do not ask me about product behavior—only ask about technical choices if needed.
Build Part 1.
```

From this point forward, Team A's session writes zero code, and Team B's session never sees the original product. If a behavioral gap is discovered during implementation, return to Team A's session, update `SPEC.md`, and copy the updated spec across the wall.

**The v0.1 task list (`V0.1-TASKS.md`)** breaks the build into numbered parts in dependency order. Each part points to the corresponding sections of `SPEC.md` and is complete only when its automated tests pass. Part 1 should always be the pure core engine with zero OS/network side effects—decision logic plus a mock harness and fake clock so every edge case can be unit-tested without elevated permissions.

**When building inside a product repository**, that repository belongs strictly to Team B. It contains `docs/spec/SPEC.md`, `V0.1-TASKS.md`, and source code—nothing from Team A. Add a clean-room rule block to the repository's `CLAUDE.md` so every future session enforces it automatically:

- Read only files inside this repository; never search for code, docs, or screenshots of competing products.
- Behavior is governed strictly by `docs/spec/SPEC.md`; if a gap is found, ask the spec owner.
- All UI copy must be written fresh from scratch.

## Pre-wall self-check

- [ ] Team A directory lives outside all product repositories; reference product's license is recorded in `step0.md`
- [ ] Analysis files contain no code snippets longer than 3 lines and no verbatim prose longer than one sentence
- [ ] `SPEC.md` includes a Glossary, an explicit "Out of Scope for v1" section, and zero mentions of the reference product's name
- [ ] Latest wall-test round returned `0` BLOCKER questions (verified with 2 independent agents), and all MINOR questions have explicit defaults written into the spec
- [ ] Open questions have been signed off by the product owner and dated under "Locked Decisions"
- [ ] `audit.md` (with 3-column table and one-sentence wedge) and `V0.1-TASKS.md` are complete
- [ ] Only `SPEC.md` and `V0.1-TASKS.md` cross the wall into Team B's repo

## Step 6 — Verify equivalence & wedge differentiation

Run the same end-to-end user flows on both the reference product and your build: verify that baseline table-stakes behavior is equivalent and that deliberate differences (your wedge) work as designed and are documented as intentional. If it passes, ship; if not, loop back to Step 5.

## One sentence to remember

Teardown to understand why they win, then differentiate sharply in the gap. A conclusion of "build the exact same thing but cheaper" means the research is unfinished—return to the market matrix to find an underserved wedge.

## Continuous self-improvement

1. **Eval after every run.** Grade the run against the checklist above: note any skipped steps or manual fixes required by the user, and propose updates directly to `SKILL.md` in `0xdonniechu/Coding-5.5` (private) and `CHANGELOG.md`.
2. **Periodic tool & source refresh.** Re-verify any external tool or workflow reference that is more than a few months old.
3. **Ask when out of bounds.** If a legal, licensing, or behavioral question is outside scope, state it plainly and ask the user—never guess.
