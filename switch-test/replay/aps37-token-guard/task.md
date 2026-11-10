You are the main session in {repo}, a clone of ambysto/claudecode-guide (no remote). Build the change below
directly, as a HARD task, and commit it on the current branch. Do not push, open PRs or ask questions: decide
what the task leaves open and write each decision in the commit message. When done, reply with the commit id
and a summary of at most 200 words.

Task (Plane APS-37). Owner decisions 2026-10-23: agents act as the bot `ambystobot` in ambysto-memory (GitHub
refuses its merges). A PreToolUse hook for EVERY Claude Code session must stop an agent from taking the owner's
GitHub token (keyring), and every command that sets `AMBYSTO_OWNER` (the owner's own merge) must ask the owner
each time. The hook lives in claudecode-guide and is installed by its installer.

Contract:
- a new `guard/owner-token-guard.py` (standard library only), with a `--self-test`;
- `scripts/install.py` copies it, and with `--settings` appends one PreToolUse entry to `~/.claude/settings.json`
  beside existing hooks, which on the owner's machine belong to other tools and must never change; it still backs
  up first, never deletes, and keeps `--check` correct;
- `scripts/check.py` runs the guard's self-test;
- `CLAUDE.md` lists the guard on the HARD list and its limits.

Safety for this run: NEVER run the installer against the real home. Test it only with a temporary HOME, for
example `HOME=$(mktemp -d) python3 scripts/install.py --settings`, then `--check`. Never print a token.
