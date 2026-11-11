---
status: shipped (PR #55; owner 2026-11-11: "Chủ động merge & clean worktree; sau mỗi khi kết thúc phiên làm việc thì cập nhật graph 1 lần"; plan intent/2026-11-11-session-graph.plan.md) # draft → approved → planned → building → verified → shipped (PR #n)
---
# The architecture graph is refreshed when a session ends, and the next session reads it; merges happen on their own

Ticket: Plane APS-57. Source: owner 2026-11-11, in reply to "record 'merge proactively' as a standing rule?":
"Chủ động merge & clean worktree. Sau mỗi khi kết thúc phiên làm việc thì cập nhật graph 1 lần, agent làm việc ở
phiên sau có thể xem graph để hiểu kiến trúc hệ thống."

## Problem

1. **Each session learns the architecture again.** A new session in a repo reads files, or runs `ambysto-graph
   overview` itself, to find the modules, entrypoints and hotspots. The diagram `progress-diagram.py` draws is
   refreshed only when a session remembers to run it, so it is often missing or stale, and nothing tells the next
   session it is there.
2. **Merges wait for the owner.** The global instructions say the main session "merges only when I ask", so a change
   that passed its gate, review and Verify still waits for an owner message, and merged branches and worktrees pile
   up until the owner asks for a cleanup.

## Outcome

1. When a session ends in a git work tree, a hook refreshes that work tree's graph once: `overview.md` (the
   `ambysto-graph overview` map, for agents) and `architecture.html` (the drawing, for the owner) in
   `<git dir>/progress-diagram/`, the folder `progress-diagram.py` already uses and git never commits. It runs in the
   background under a memory cap and a time limit, so ending a session is not slowed; it is skipped when nothing
   changed since the last refresh, and two sessions ending together refresh once.
2. When a session starts in a work tree that has such a graph, a hook adds two lines to its context: where
   `overview.md` and `architecture.html` are, when and at which commit they were drawn, and how far HEAD moved since.
   Not the overview itself: the session reads it when it needs it (standard 6, fewer tokens).
3. The global instructions say to read that `overview.md` before exploring a repo, and that the main session merges
   on its own once the change passed its gate and review and the project's whole Verify ran on the branch, then
   deletes the merged branch and removes its worktree. It still asks when the merge publishes or deploys something
   outside (as in `ambysto-optimer`, where a merge to `main` publishes the page and the downloads), or when it cannot
   tell (a site, hosting config, downloads or a workflow on push to `main`, and a `CLAUDE.md` that does not say
   what a merge publishes), in
   `ambysto-memory` and `ambysto-1prompt` (GitHub keeps merges with the owner), and for tags and releases. The rule
   overrides a repo line written before 2026-11-11 that keeps every merge with the owner. The starter-kit template and the sdlc skill say the
   same; inside a one-prompt run the session ends the run before it merges.

## Constraints

- Hooks never block or slow a session: they always exit 0, settings.json runs them with `|| true`, the SessionEnd hook
  only starts the job (Claude Code gives SessionEnd hooks a short budget) and the job runs detached
  (`systemd-run --user`; without systemd, as on macOS, a new process session; a failing `systemd-run` starts nothing).
- Nothing is written into the work tree: only into the git folder. No tool installed (`ambysto-graph`) → nothing.
- HARD (session hooks, the installer's writes to `settings.json`, who may merge): the main session builds it,
  hard-reviewer reviews.

## Success

The hook's self-test (scratch repos and a fake `ambysto-graph`): end → the graph is written, a second end with no
change skips, a change refreshes, a concurrent refresh is skipped, a failing tool keeps the old graph and records the
error; start → the two lines with the commit and how far HEAD moved, nothing without a graph or outside git. `check.py`
passes with both hooks registered once. On this machine: after a real session ends, the graph appears and the next
session's context names it.

## Decisions

- The graph lives in the work tree's git folder, next to `progress-diagram.py`'s output, not in the repo: it changes
  every session and would make a commit each time.
- The start hook names the files instead of pasting the overview (a few lines, not a thousand tokens per session).
- Owner 2026-11-11: merge on its own and clean worktrees, as a standing rule, not only for one piece of work.
- Owner 2026-11-11, asked after hard-review round 2 (13 repos keep every merge with the owner in their `CLAUDE.md`):
  "Tự merge, trừ khi phát hành": merge on its own everywhere except a merge that publishes or deploys outside and the
  two bot repos; each repo's old line is fixed in its next PR.

## Open questions

None.
