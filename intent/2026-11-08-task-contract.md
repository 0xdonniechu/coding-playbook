---
status: shipped (PR #35) # draft → approved → planned → building → verified → shipped (PR #n)
---
# Task contract per builder dispatch, path check in agent-guard, a worktree per parallel builder

Ticket: Plane APS-46. Source: owner decision 2026-11-07 (a write outside the allowed paths is reported and the run
locks to reading); owner answers 2026-11-08 (below). Comes after the model switch kit (APS-45, APS-47).

## Problem

The builder's only guard is `agent-guard.py build`: a PreToolUse hook on Bash that blocks git and gh commands that
commit, push, merge or switch branches. Nothing limits which files it changes. Edit and Write are not hooked at all,
so a builder told to change `src/a.py` can rewrite a spec, a test fixture, `CLAUDE.md` or a file in another repo,
and the main session learns it only by reading the diff. Parallel builders share one working tree today unless the
main session remembers to make worktrees by hand ("Working practice": an agent may stage everything in its tree).

## Outcome

1. **A contract per dispatch.** Before dispatching a builder, the main session writes a contract: allowed paths
   (globs, relative to the worktree), forbidden paths (globs that win over allowed), and the checks the builder must
   run. It lives in the worktree's own git folder (`$(git rev-parse --git-dir)/agent-contract.json`): untracked,
   one per worktree, outside the files the builder edits.
2. **agent-guard enforces it** (new builder hooks, source `ambysto/1prompt`):
   - before an Edit, Write or NotebookEdit: refused if the path is outside the allowed paths, inside a forbidden
     path, or inside the git folder;
   - after every tool call: each git work tree the builder touched is compared with its snapshot; any changed path
     outside the contract (by any writer: a script, a formatter, `sed -i`) is reported to the builder at once and the
     run **locks to reading** (Read, Grep, Glob only) for the rest of the dispatch;
   - **no contract → no writes** (owner, 2026-11-08): a builder in a tree without a contract can read, and its first
     write is refused, or locks the run if it came through a shell, with a message saying the main session must
     write the contract;
   - at the end (SubagentStop): the builder cannot finish until its report's first line is
     `OUTSIDE CONTRACT: <paths>` when the run locked, and its report names every contract check with a result
     (passed with counts, failed, or "not run: <reason>").
3. **Checks: reported, then rerun** (owner, 2026-11-08). The hook never runs a test suite. The main session reruns
   the contract's checks as its gate before review, as today.
4. **A helper for worktrees** (owner, 2026-11-08), `scripts/dispatch.py` in this repo:
   `new <repo> <slug> --allow <glob>… [--forbid <glob>…] --check <command>…` creates `<repo>-<slug>` next to the
   repo on a new branch from the current HEAD, writes the contract, and prints the path and a prompt line for the
   builder; `done <path>` removes the worktree only when it has no uncommitted change. Parallel builders each get
   one; a single builder may use the main checkout with a contract (`dispatch.py contract <repo> …`).
5. `global/CLAUDE.md` (the loop and "Working practice") says every builder dispatch goes through `dispatch.py`; the
   builder's own instructions name the contract and the report lines. `install.py` installs the new hook pin.

Success is measured by the self-tests: agent-guard's on a scratch repo (an allowed edit passes; an outside Edit is
refused; an outside write through Bash locks the run; no contract refuses the first write; the Stop rules), and
`dispatch.py --self-test` (new, contract, done refusing a dirty tree). Then one real MEDIUM task run through it.

## Constraints

- `agent-guard.py` changes in `ambysto/1prompt` first, under that repo's rules (public: no ticket ids, names or
  private paths in its files, commits or PRs; HARD there), then this repo copies the merged files and updates
  `hooks/pin.json`. HARD in both repos: the main session builds, hard-reviewer reviews.
- Standard library Python only; no new dependency; works where Claude Code runs (Linux, macOS, Windows).
- The reviewer and boundary modes keep their behaviour; their self-tests stay green.
- The hook stays fast: one `git status` and hashing of changed files per touched tree per call, like the reviewer
  watch.

## Out of scope

- Contracts for the reviewers (they already have the tree watch and never edit) and for the transcriber.
- Claude Code's own `isolation: worktree` (its path is unknown before the run, and it starts from the default branch).
- Running checks inside a hook; changing the autonomous-run boundary.
- Files git ignores (build output) are not compared, as in the reviewer watch; a write outside every git tree (a temp
  folder) is not checked.

## Open questions

None.
