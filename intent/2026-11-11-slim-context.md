---
status: approved # owner approved 2026-11-11 ("approve. tạo ticket triển khai.")
---
# Intent: slim the context every session loads (APS-62)

## Why
`~/.claude/CLAUDE.md` (about 3,900 words) is loaded into every session of every project, subagents included, and
this repo's `CLAUDE.md` (about 3,900 words in 44 lines) into every session here. Much of both is how a tool works
inside, not a rule a session acts on. That costs tokens on every turn and buries the rules.

## What
1. `rores/global/CLAUDE.md`: the one-prompt run bullet keeps the rules a session acts on and points to the sdlc
   skill's "One-prompt run" section for the process it already holds; the Tools bullets keep what to run and when,
   one or two lines each. No rule is dropped or changed.
2. The machine section outside the marker block ("This machine: Ubuntu builds Windows only", about 1,000 words)
   moves to `~/work/ambysto/CLAUDE.md`, which Claude Code loads for sessions started under `~/work/ambysto/`;
   `~/.claude/CLAUDE.md` keeps a pointer for a session started elsewhere and the two-identities rule, which holds
   for every repo. That file is local to this machine, as the section was; it is not in any repo.
3. This repo's `CLAUDE.md`: Verify, the HARD / MEDIUM / EASY lists, Rules and Open keep one line per item; how each
   hook and script works inside moves verbatim to `docs/internals.md`.
4. Owner decision 2026-11-11, recorded under "Current choice": the models stay as pinned, Fable 5.2 as
   hard-reviewer; the switch test runs only when a new model ships.
5. The mirror `0xdonniechu/coding-playbook` gets the same change.

## Not
No rule, threshold, model or check changes meaning. No code changes.

## Done when
Every rule in the old texts is still in the new ones (in the file a session loads, or in the skill or doc it is
pointed to), `check.py` passes, `install.py --check` is equal after install, and hard-reviewer PASSes.
