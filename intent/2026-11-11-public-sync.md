---
status: approved # owner 2026-11-11: "bản bên 0xdonniechu tôi để public để sau này chia sẻ cho học viên, bản trong Ambysto là dùng nội bộ; bạn làm thế nào cũng được, miễn là tôi có thể sử dụng được tiện lợi mà ko bị lệch phần nào"
---
# Intent: keep the public coding-playbook in step (APS-65)

## Why
`0xdonniechu/coding-playbook` is this repo published for students; this one is internal. Each change was ported by
hand, twice the work, and the two had drifted (their `CLAUDE.md`, `docs/internals.md`, intent status lines).

## What
1. `scripts/sync-public.py`: reports what differs between internal `origin/main` and public `origin/main` and, with
   `--write`, writes the public clone's branch from internal `origin/main` (never a work tree, index or unmerged
   branch), with scoped rewrites (this repo's path in the global block; redactions of internal names in older
   intents) and executable bits; the public repo's own `CLAUDE.md`, `README.md` and branch rule stay its own and are
   reported for a hand review whenever their internal counterparts change; a leak check refuses secret shapes and
   internal names; it never commits or pushes.
2. A rule here: after every merge, sync; a merge in the public repo is allowed without asking once the main session
   has read the whole diff, the leak check and its `check.py` pass (the owner left the method to the session).
3. `HANDOFF.md` ignored here too, so `.gitignore` needs no public-only copy.

## Not
No automatic push from a hook; the main session still commits, opens and merges the public PR.

## Done when
Self-test with mutations caught, `check.py` passes, the first real sync leaves the public repo in step, hard-reviewer
PASSes.

## Open questions

None.
