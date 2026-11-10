The owner-token guard is built and committed as **`afb1879`** on `replay`. Nothing pushed, no PR, worktree clean. The decisions the task left open are written in the commit message.

**What it does:** `guard/owner-token-guard.py` (standard library only) runs before every tool call:
- **Denied:** commands that read, print, change or remove the owner's GitHub token. That covers `gh auth token`, login and switch, `git credential`, the system keyring, gh's `hosts.yml`, `.netrc`, process environments and the token variables.
- **Asked every time:** any call that sets `AMBYSTO_OWNER`, whether in a shell command, a file an agent writes, or an MCP tool's arguments. A headless run refuses the ask. Reading or testing the variable passes.
- **On error:** bad input or an internal error blocks the call, because a leaked token cannot be taken back.

`install.py` copies the script, and with `--settings` appends one hook entry after the existing ones, which it never touches. If there are two guard entries, or one mixed with other hooks, it writes nothing and exits 2. A missing guard entry now makes `--check` exit 1, even on a machine that never ran `--settings`. `check.py` runs the self-test (146 cases), and `CLAUDE.md` lists the guard as HARD with its limits.

**Checks:**
- `check.py` passes, and fails when I break the guard on purpose.
- The installer was only ever run against temporary HOMEs; `--settings` then `--check` exits 0 there.
- Hard-reviewer failed round 1 (two major false negative/positive issues), all fixed; round 2 passed.
- Not run: a live session with this version installed (it would write the real `settings.json`), and Windows.

**For the owner:** add `guard/*` to `.claude/boundary.json`, run the installer on the real machine, and merge.
