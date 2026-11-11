---
status: approved # owner 2026-11-11: "2,3 và 4: approve" (item 3: turn the rules that slipped into cheap gates)
---
# Intent: session gates for rules that slipped (APS-66)

## Why
On 2026-11-11 three written rules slipped more than once: branch names (`aps-NN-slug`, broken twice), editing a tree
a running reviewer reads (lesson `no-edits-in-trees-agents-read`, broken three times, each a TREE CHANGED), and
recalling a lesson that existed. The owner's series: each failure becomes a tool or check in the layer that owns it,
not a line in a prompt.

## What
`gates/session-gates.py`, a PreToolUse and a SubagentStop hook for every session (installed by `install.py
--settings`):
1. A repo's `.claude/branch-name.json` pattern refuses a branch the main session creates or pushes with another name.
2. While a subagent that touched a work tree is running, the main session cannot edit a file there or run a changing
   git command there.
3. A Bash command that matches a shared-memory lesson gets that lesson named once per session.
This repo gets `.claude/branch-name.json` (`aps-NN-slug`); the public copy gets its own (`feat/` or `fix/`) as a
public-only file.

## Not
Not a security boundary: a command the parser does not read passes. It never blocks a session on its own error.

## Done when
Self-test with every gate mutated and caught, `check.py` passes, the hooks installed, hard-reviewer PASSes.

## Open questions

None.
