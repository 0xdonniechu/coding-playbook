---
status: verified # draft → planned (owner accepts) → building → verified
---
# Plan: task contract per builder dispatch (APS-46)

Contract: `intent/2026-11-08-task-contract.md` (approved 2026-11-08). Rating: HARD in both repos (`agent-guard.py`
is on the HARD list of `ambysto/1prompt` and of this repo): the main session builds, `hard-reviewer` reviews each
PR's diff (range given, no checkout). Two build PRs, in order: 1prompt first, then this repo pins it.

Threat model, as for the rest of agent-guard: it catches a builder's mistakes and casual overreach (a wrong file, a
formatter run on the whole repo, a script that writes elsewhere), not a builder working to get around it (editing
the guard's state file in the temp folder, a write into a tree no call ever names).

Two points go past the intent's words, for the owner to accept with the plan: a locked run may also run read-only
shell commands (`cat`, `git status/diff/log/show`, as the boundary lock allows), so the builder can describe what
changed; and an Edit or Write outside every git tree is refused unless it is in the temp folder or the session's
scratchpad (the intent left writes outside git trees unchecked; for the edit tools a check is cheap).

## The contract

`$(git rev-parse --git-dir)/agent-contract.json` of the tree (the main checkout: `.git/`; a worktree:
`.git/worktrees/<name>/`). Untracked, one per tree, outside what `git status` sees.

```json
{"version": 1, "task": "aps-12-fix-parser", "allow": ["src/parser/**", "tests/test_parser.py"],
 "forbid": ["docs/spec/**"], "checks": ["python3 -m pytest -q tests/test_parser.py"], "written": "2026-11-08T10:00Z"}
```

Paths are relative to the tree, `/`-separated. A glob matches with `fnmatch` where `*` stays in one folder and
`**` crosses folders; a pattern ending in `/` means everything under it. Case-insensitive on Windows and macOS,
exact on Linux. `forbid` wins over `allow`. A change to a path counts when its content, its existence or its mode
differs from the snapshot; a rename counts for both names.

## Part 1: `ambysto/1prompt` `hooks/agent-guard.py` (public repo: no ticket id anywhere)

New modes, beside today's `build` (unchanged for Bash: git and gh rules):

| mode | hook (builder frontmatter) | does |
|---|---|---|
| `build` | PreToolUse `*` | today's git/gh rules for Bash; then: snapshot each git tree the call touches (as the reviewer watch, `touched_paths`), storing the tree's contract as read at that moment; if the run is locked, refuse everything but Read, Grep, Glob and read-only Bash (`after_change_ok` without `bd`); for Edit, Write, MultiEdit, NotebookEdit: refuse a path inside a git folder, a path in a tree with no contract, a path outside `allow` or inside `forbid`, and a path outside every git tree unless it is under the temp folder or the event's `scratchpad_dir` |
| `build-after` | PostToolUse `Bash\|PowerShell\|Edit\|Write\|MultiEdit\|NotebookEdit` | compare each snapshotted tree path by path (a per-path digest of every changed and untracked file, HEAD, and the contract file's digest); any changed path outside the stored contract, or in a tree without one, or a changed contract file: lock the run, tell the builder at once (exit 2: "outside the task contract: …; stop, do not undo it, report it") |
| `build-stop` | Stop (runs as SubagentStop) | if locked: refuse to finish until the report's first line starts `OUTSIDE CONTRACT:`; for each tree with a contract and a change: refuse until the report contains every `checks` command verbatim; asks once (`stop_hook_active` lets it finish); then deletes the state file |

- State: the reviewer watch's state file, kind `build` (`session_id:agent_id:build` in the temp folder), holding the
  per-tree snapshot, the contract seen, the changed paths and the lock.
- Per-path digest: `git status --porcelain=v1 -z --untracked-files=all` (rename entries carry two paths), each listed
  path's bytes and mode hashed. Files git ignores are not seen (as the reviewer watch).
- Messages name the fix: no contract → "the main session writes one with `dispatch.py` (claudecode-guide)" in
  generic words (the public repo says "the main session writes a task contract"; the README documents the file).
- `--self-test` gains a `contract_test()` on a scratch repo: allowed edit passes; Edit outside `allow`, inside
  `forbid`, into `.git/`, into a tree without a contract, outside every tree (not temp) refused; temp-folder Write
  allowed; Bash write outside (`echo x > docs/a.md`) locks, then Write and a writing Bash are refused while `cat`,
  `git diff` pass; a change to an already-changed allowed file passes, to an already-changed outside file locks;
  a rename from inside to outside locks; a contract rewritten mid-run locks and the stored contract still applies;
  Stop: locked without the line → refused, with it → allowed; a check missing from the report → refused;
  `stop_hook_active` → allowed. Today's CASES and watches unchanged.
- `README.md` and `docs/design.md` (1prompt): the contract file, the three modes, the limits.

## Part 2: this repo (claudecode-guide), after Part 1 merges

1. `hooks/agent-guard.py` copied from the merged 1prompt commit; `hooks/pin.json` commit and hashes.
2. `agents/builder.md` frontmatter: the three hooks above (replacing the single Bash one); body: "Your task
   contract", how to find it (`cat "$(git rev-parse --git-dir)/agent-contract.json"`), work only inside `allow`,
   ask before needing a path outside it, run every `checks` command and name each one verbatim with its result, the
   `OUTSIDE CONTRACT:` first line.
3. `scripts/check.py`: `GUARDED["builder"]` lists the three hooks; runs `dispatch.py --self-test`.
4. `scripts/dispatch.py` (standard library only):
   - `new <repo> <branch> --allow <glob>… [--forbid <glob>…] --check <cmd>…`: refuses a branch that exists or a
     target folder that exists; `git worktree add -b <branch> <repo>-<slug> HEAD` (slug = the branch name after
     `aps-NN-`); writes the contract; prints the path and the prompt lines to give the builder ("Work only in
     <path>; `cd` there first. Your task contract: …").
   - `contract <tree> --allow … --check …`: writes or replaces the contract of an existing tree (one builder in the
     main checkout; a second round with a wider task). Prints the old and the new contract.
   - `show <tree>`; `done <tree>`: refuses when `git status --porcelain` is not empty; else removes the contract
     and the worktree (`git worktree remove`), keeps the branch. Never on the main checkout.
   - Refuses an empty `--allow` or `--check`, a glob with `..` or an absolute path, a tree inside `~/.claude`.
   - `--self-test` on a scratch repo: new → files, branch, contract; a second `new` with the same branch refused;
     `contract` replaces; `done` refuses a dirty tree, removes a clean one.
5. `global/CLAUDE.md`: the loop and "Working practice" say every builder dispatch goes through `dispatch.py`
   (`new` for each builder that runs beside another, `contract` for a single one), the main session reruns the
   contract's checks as its gate, and an `OUTSIDE CONTRACT` report is judged before anything else. `README.md` row
   for `dispatch.py`; this repo's `CLAUDE.md` Verify names its self-test.
6. After the merge: `install.py --global`, `install.py --check`.

**Changed in build (2026-11-08):** `dispatch.py done` on the main checkout removes the contract only (a contract
left there would hold the next builder to an old task); on a linked worktree it removes both, refusing uncommitted
work. `dispatch.py` is on this repo's HARD list (the contract it writes is what the guard trusts). In 1prompt, an
Edit or Write anywhere under a folder named `.git` is refused (git sees no work tree from inside its own folder,
so the scratch repo in the temp folder let a write into `.git/` through in the first self-test run). `dispatch.py
contract` prints the old contract and the builder's brief for the new one (`show` prints the new file).

**After review (PR #35 PASS, five MINOR, fixed in the closing PR):** `done` removes the worktree before the
contract and runs git from the shared git folder (a refused remove no longer leaves a tree without a contract);
`new` also cleans up after an OSError; the self-test covers an existing target folder and reads the written contract
with agent-guard's own `read_contract`; the brief no longer says "never nothing" when `--forbid` is empty (found in
Proof 5); the builder's 200-word limit does not count the check commands.

**Proof results (2026-11-08):** 1. 1prompt self-test PASS, scrub gate 0 hits (00c24b7). 2. 23 guard mutations and 14
dispatch.py mutations, all caught. 3. `check.py` PASS. 4. hard-reviewer: 1prompt #7 PASS after one fix round,
claudecode-guide #35 PASS (five MINOR, fixed above), #36 PASS (four MINOR, fixed in it: a locked worktree proves a
refused remove keeps the contract; the global word limit matches the builder's; `done` is run from the repo). 5. A builder made the README fix above inside its contract
(`dispatch.py new`, the check named verbatim, rerun by the main session, `done` removed the worktree). The lock run
first showed nothing: Claude Code reads agent files when a session starts, so the session that installed the new
builder still ran the old frontmatter (one Bash hook). In a fresh session the same planted write locked the run at
once, a read-only `git status` still ran, and the report's first line was `OUTSIDE CONTRACT:
…/claudecode-guide-proof-lock: contract-probe.txt`. 6. `install.py --check` exit 0.

## Risks, and the check that catches each

- **Every builder in every project stops writing** the moment the new builder is installed (no contract → no
  writes, by design). `global/CLAUDE.md` and the builder's refusal message both name `dispatch.py`; the install
  happens only after the merge, in one step with the new guard (a builder file naming `build-after` with an old
  guard would block every call: "unknown mode"). Proof 5 runs a real task end to end before the session closes.
- **A false lock** on files a check writes (a lock file, a snapshot, generated code that is tracked). The contract
  must allow them; `dispatch.py new` prints a reminder; the lock message names each path so the main session widens
  the contract (`dispatch.py contract`) and reruns the builder.
- **A miss**: a write into a tree no call names, an ignored file, a write outside every git tree through Bash, the
  state file edited. Stated as limits in 1prompt's README; outside the threat model.
- **Speed**: one `git status` and the hashing of changed files per touched tree per write call (the reviewer watch
  does the same); reads (Read, Grep, Glob) skip the after-hook.
- **The reviewer and boundary modes change by accident**: their CASES, watch tests and boundary tests stay in the
  self-test unchanged; a diff of those functions is part of the review.
- **A leak into the public repo** (a ticket id, a private path in a test): 1prompt's `check.py` scrub gate at zero
  hits before the push.
- **Parallel worktrees confused**: each worktree has its own git folder, so its own contract; the self-test makes two
  worktrees with different contracts and checks an edit allowed in one is refused in the other.

## Proof

1. 1prompt: `python3 hooks/agent-guard.py --self-test` PASS (all old cases plus the contract test);
   `python3 scripts/check.py` PASS, scrub gate zero hits.
2. Mutations of the new code, each must turn the self-test FAIL: no lock after an outside Bash write; `forbid`
   ignored; no-contract tree allowed; the stored contract replaced by the rewritten one; Stop without the line
   allowed.
3. This repo: `python3 scripts/check.py` PASS (pin hashes, the builder's three hooks, `dispatch.py --self-test`).
4. `hard-reviewer` on each PR (range given, no checkout): PASS, or FAIL fixed within 2 rounds.
5. After both merges and `install.py`: one real builder dispatch through `dispatch.py new` on a small task in this
   repo (the owner may name one; otherwise a README wording fix): the builder edits inside the contract, its report
   names the checks; then a planted outside write in a scratch worktree locks a builder run and its report starts
   `OUTSIDE CONTRACT:`. `dispatch.py done` removes the worktree.
6. `install.py --check` exit 0.

Not in this plan: contracts for reviewers and the transcriber; Claude Code's `isolation: worktree`; running checks
in a hook; the autonomous-run boundary.
