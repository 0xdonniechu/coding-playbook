---
name: agent-team
description: A one-approval run-to-done playbook — build → independent review → fix → merge → verify — with multiple role agents (backend, frontend, design, data) across waves. Use when saying "split waves", "one approval run to done", "/agent-team", or handing over a multi-part change at once.
---

# /agent-team

The model: gather all context → **one approval** → agents run to done (build, review, fix, merge, test, verify) → you only check the final result.

Day: approve + write the brief. Night: agents run. Two separate roles on **one machine**:

- **Executor** — spawns role agents, pushes code, keeps reports.
- **Coordinator** — reviews, merges, applies migrations, measures after deploy. Does **not** edit feature code itself.

**A writer never reviews their own code.**

---

## 0. Before running: one brief file, one approval

Write `docs/plans/handoff/<date>-<work>-wave<N>.md` (or the repo's plan folder) with all sections:

1. **Read first** — at most 3 files (plan, evidence, START-HERE if present).
2. **Starting state** — what is live, current numbers.
3. **Setup** — one worktree or branch per role; lock file per role; **unique** scratchpad file names; dependencies installed (sub-packages included).
4. **Per-ticket contract** — table: item · files allowed to touch · acceptance evidence (one number or a red guard on violation). Cross-role contracts (API shape, event names, cache keys) go here, not negotiated in chat.
5. **Rules** — §3 below + repo-specific rules.
6. **Handoff** — report file: 5 fields/ticket (output · done · evidence · left · next owner) + time/tokens.

List **every permission** the run will need (prod DB, merge, secrets, env, sending mail) in the same approval message. Classifier blocked mid-run: record the exact command for you to run, continue with the rest.

**Long prompts:** put the brief in a file; the spawn command is one short sentence pointing at that file. A prompt cut mid-string means the agent never starts.

---

## 1. Roles (executor spawns; each role = one job)

| Role | Owns | Suggested model | Deliverable |
|---|---|---|---|
| Backend | server, migration, RPC | strong | endpoint shape + before/after numbers |
| Frontend | page, hook, component | strong | cache keys, skeleton, before/after numbers |
| Design | design system, primitives | medium | spec + acceptance screenshots |
| Data | measurement scripts, dashboard | medium | baseline + link + thresholds |
| Reviewer (coordinator) | no edits | strong | MERGE / FIX FIRST with file:line |

Rules: two agents never share a file (locks); design before frontend when sharing components; migration writer stops after dry-run, hands the file to the coordinator; frontend depending on backend shape merges after backend deploys.

---

## 2. Per-PR pipeline (coordinator)

1. Executor sends: PR number, ticket, before/after table, guards already run.
2. Coordinator runs **full local CI** on the PR head alongside remote CI — CI has missed before.
3. Coordinator reads the sensitive slice (auth, cache, migration, money).
4. Independent review agent with a concrete risk checklist; must have file:line, scenario, verdict. Spot-check — agents also report wrong.
5. Fix list back to executor: BLOCKING / fold-in-if-cheap / next-wave. Same branch, new SHA.
6. Verify the fix in code, CI green, local green → squash-merge → measure production → record numbers → next PR.

Merge order: backend → deploy → migration needing new code → frontend.

---

## 3. Non-negotiable rules (each from a real incident)

- Branch from latest `origin/main`; no stacked PRs; `git status` after every rebase.
- Important rule → a guard that proves red on deliberate violation; guards sweep the tree, never hand-list files.
- Review every RETURN branch of endpoints against every consumer (skewed fallback shape = crash).
- GET never writes (hover must not create records).
- Secondary cache/triggers never roll back the primary write (EXCEPTION + reconcile).
- Views with `security_invoker`; check the anon surface after migration.
- Read `error` from every RPC/DB; unbounded SELECTs go through a pagination helper; clamp query params.
- Migrations: separate dry-run script (ROLLBACK, `ON_ERROR_STOP`); apply file by file; `lock_timeout`; CONCURRENTLY indexes when needed.
- Measure what decides: same transaction, same warmth, twice; know which body is live before labeling.
- Unique scratchpad names per agent.
- New worktrees: install all sub-package dependencies.
- No `pkill -f`, no kill-by-port; only PIDs you started.
- Local runners must fail on empty logs; CI is the signal of record.
- Free GitHub has no branch protection: **wait for green checks** before `gh pr merge`; don't use `--auto` as a way to wait.
- Server-side HTML prefetch = everything the endpoint returns may land in cache/proxy — never prefetch secret-bearing endpoints.

---

## 4. Quota / interruption

At ≥ 80% quota: every agent commits + pushes WIP per unit; executor keeps a `## RESUME` block at the report head (branch, commit, file in progress, next command, per role), refreshed every 15 minutes; no unrecoverable step in the last 15 minutes.

---

## 5. Closing a wave

Executor: report (5 fields/ticket, tokens/time, lessons, next-wave, your manual tasks) → docs PR → coordinator merges.

Coordinator: production numbers after deploy, START-HERE updated, next wave's brief written **before** the executor idles.

Final wave: one-page FINAL report — before/after per wave, incidents, manual work, remaining debt.

---

## 6. Permission boundary (Session 7)

State clearly in the brief and `AGENTS.md`:

- Which agent reads/writes/runs commands/calls which API.
- Which tasks agents decide alone, which **wait for your approval** (production deploys, customer mail, paid API spend).
- Every agent has an identity (name, log) for audit.

Three fatal mistakes to block at the tool layer: self-deploying prod, self-sending customer mail, self-spending API money.
