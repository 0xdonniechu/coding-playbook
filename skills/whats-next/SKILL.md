---
name: whats-next
description: |
  Triage the working session — answer "what next?" by sweeping the whole session for unfinished work, proposing next steps and dependencies of large changes. Use when saying "what next", "what's left", "session recap". Read and propose only — never start doing the work.
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
---

# /whats-next

Answer **"what should I do next?"**. Summarize the current session state with clear priorities. **Read-only** — gather evidence, propose; **never** start working.

Output language = the conversation language. PR/commit names stay English.

Matches Session 7: the boundary between work agents decide alone and work that must wait for your approval.

---

## 1. Gather evidence (parallel, cheap)

Run in parallel; skip what doesn't apply:

- **Loose threads in this chat** — unanswered questions; "will continue / pending"; merged-to-staging-not-yet-prod; still-running background tasks; deferred work ("later").
- **Open PRs** in repos the session touched: `gh pr list --state open --json number,title,headRefName` (once per repo).
- **Merged but not prod** (if the repo has a staging branch): `git rev-list --count origin/main..origin/staging` plus a short log — which belong to this session vs another session.
- **Background tasks** — live shell/agent background jobs.
- **Project notes** (optional): `README`, `docs/START-HERE.md`, or the repo TODO file — `MEMORY.md` is **not** required.
- **Deploys / envs** this session created but not yet propagated.

Keep a few quick commands. No deep code digging unless ambiguous.

---

## 2. Summarize — exactly 4 sections, prioritized

Each item states its **owner** (🧑 you vs 🤖 agent). Link PR#/files for clicking.

1. **🔵 Unfinished** — open PRs, waiting on your test/approval, merged-to-staging-not-prod, background tasks, loose threads. Mark blockers.
2. **🟡 Recommendations** — highest-leverage work, ranked. Includes earlier proposals you haven't decided. One line + tradeoff.
3. **🔴 Impact & dependencies** — this session's large changes: cross-repo, merge order (X before Y), risks before prod promotion (route/API changes, schema, secrets, migrations).
4. **✅ Done** — 2–4 line recap.

---

## Rules

- **Propose, don't execute.** End by asking which item you pick.
- **Prioritize 1–2 things** that truly matter.
- **Be honest about prod risk** — a large staging batch must not be called safe without QA.
- **Cross-repo / cross-env** — a fix in repo A usually needs a deploy/promote in repo B; check both.
- Trivial session / nothing pending → say so plainly in 2 lines, don't invent work.
