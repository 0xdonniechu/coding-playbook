---
name: orca-worktree-setup
description: Configure Orca Setup Scripts so every new worktree automatically receives gitignored local files (.claude/settings.local.json, CLAUDE.local.md, .env) and Orca stops prompting on worktree creation. Use when Orca shows the "Setup Script / When to run" prompt when creating a worktree, when a new worktree is missing local files or permissions, or when asked for "setup script orca" or "orca worktree config". Do not use for managing Orca worktrees, terminals, or browsers (use `orca-cli`).
---

# /orca-worktree-setup

Every worktree Orca creates is a clean checkout — gitignored files from the root repository (`.claude/settings.local.json`, `CLAUDE.local.md`, `.env*`, etc.) do not carry over automatically. The Setup Script runs right after a worktree is created, making it the right place to copy those local files.

Verified on Orca 1.4.224 (Windows) by inspecting `resources/app.asar` and testing the runner script. Other Orca versions may differ; re-verify Section 2 ("How Orca runs the script") if behavior changes.

## 1. Check what a new worktree is missing

Copy only **true local configuration files**, never runtime or build artifacts:

```bash
git status --ignored --short | grep '^!!'
```

Typically needed: `.claude/settings.local.json` (saved tool permissions so agents do not prompt from scratch in every worktree), `CLAUDE.local.md`, `.env*`. Not needed: git identity, remotes, `.git/hooks` (worktrees share `.git`), `__pycache__`, `build/`, `dist/`, or runtime data folders.

If the repository uses per-directory dependencies (`node_modules`, `.venv`), add the install command to the script; if dependencies are installed globally, omit it.

## 2. How Orca runs the script (critical)

| Platform | Execution mechanism | Consequence |
|---|---|---|
| Windows | Writes the script to `.git/orca/setup-runner.cmd`, wraps **every non-empty line as `call <line>`** followed by `if errorlevel 1 exit /b`, and executes via `cmd.exe` | Not bash. Environment variables use `%ORCA_ROOT_PATH%`, not `$ORCA_…`. A first line starting with `#!` is rejected by Orca with a Git Bash error. `call` cannot wrap multi-line `if`/`for` blocks. Any command returning a non-zero exit code (including `copy`/`xcopy` when a source file is missing, or `robocopy` when files *are* copied) aborts setup immediately. |
| macOS/Linux | Writes to `.git/orca/setup-runner.sh` with `#!/usr/bin/env bash` + `set -e` | Standard bash; any failing command aborts execution. |
| Windows + WSL runtime | Runs via `wsl.exe … sh -c` | Write standard POSIX `sh`. |

Available environment variables: `ORCA_ROOT_PATH` (root repository path), `ORCA_WORKTREE_PATH` (new worktree path), `ORCA_WORKSPACE_NAME`.

Because of `cmd.exe` line wrapping on Windows, pack the entire Windows logic into a **single-line** PowerShell command.

## 3. Template scripts

Edit the file list inside `foreach (...)`. The script skips files that do not exist in the root repository, never overwrites files already present in the worktree, and is idempotent across repeated runs.

**Windows** (single line — paste as-is):

```
powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach ($f in '.claude\settings.local.json','CLAUDE.local.md') { $s = Join-Path $env:ORCA_ROOT_PATH $f; $d = Join-Path $env:ORCA_WORKTREE_PATH $f; if ((Test-Path $s) -and -not (Test-Path $d)) { New-Item -ItemType Directory -Force -Path (Split-Path $d) | Out-Null; Copy-Item $s $d; Write-Output ('Copied ' + $f) } }"
```

**macOS/Linux**:

```bash
for f in .claude/settings.local.json CLAUDE.local.md; do
  if [ -f "$ORCA_ROOT_PATH/$f" ] && [ ! -f "$ORCA_WORKTREE_PATH/$f" ]; then
    mkdir -p "$(dirname "$ORCA_WORKTREE_PATH/$f")"
    cp "$ORCA_ROOT_PATH/$f" "$ORCA_WORKTREE_PATH/$f" && echo "Copied $f"
  fi
done
```

Test before handing off to the user: create two temporary directories `root/` and `wt/`, set the environment variables, and run the script the exact way Orca runs it (on Windows: write a `.cmd` file with `@echo off`, `call <line>`, `if errorlevel 1 exit /b %errorlevel%`, and run via `cmd /c`). Run twice: the first run copies existing files, the second run succeeds without overwriting, and missing source files do not fail the script.

## 4. Where to configure the script

- **Local (recommended for personal files)**: Orca → **Settings** → left sidebar **Projects** → select repository → **Setup Script**. Stored on this machine only and scoped per **repository** (not per worktree).
- **`orca.yaml` at the repository root** (`scripts.setup`, `scripts.archive`, `setupAgentStartupPolicy: wait-for-setup`, `worktree.sharedDirectories`): shared across the team and committed to git. Avoid when the repository is public, when the team mixes OSes and the script is single-OS, or when referencing personal local files. When both exist, **Advanced** lets you choose local-only, `orca.yaml` only, or run both.

Other settings on the page:
- **When to run**: *Run by default*.
- **Wait for setup to complete before starting agent**: **Enabled**, so the agent starts with permissions and local files already in place.
- **Archive Script**, **Custom GitHub Issue Command**: leave blank unless cleanup is needed or issues live outside GitHub.

The setup prompt on worktree creation only appears when a repository has no setup script (or when *When to run* is set to *Ask every time*). Saving the script with *Run by default* suppresses the prompt.

## 5. Never write to Orca's state database directly

Orca has no CLI command for hook settings. Configuration lives in `%APPDATA%\orca\profiles\<profile>\profile-state.db` (SQLite WAL, `profile_state_documents` table, `repos` domain, `hookSettings` field), which the running app writes continuously with revision numbers and content hashes. **Never modify the database externally** — the running app will overwrite it or corrupt state. Have the user paste the script in the UI.

## 6. Verify after the user saves

UI input fields can truncate pasted strings (observed failure: dropping the leading `powershell -NoProfile -ExecutionPolicy `, causing `'Bypass' is not recognized`). Verify the saved value **read-only** via a backup copy of the SQLite database:

```bash
python -I -c "
import sqlite3,sys,json
src=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); dst=sqlite3.connect(sys.argv[2]); src.backup(dst)
repos=json.loads(dst.execute(\"select payload from profile_state_documents where domain='repos'\").fetchone()[0])
for r in repos:
  if sys.argv[3] in r['path']: print(json.dumps(r.get('hookSettings'),indent=1))
" "$APPDATA/orca/profiles/local-default/profile-state.db" "<scratch>/ps.db" "<repo-name>"
```

Pass criteria: `scripts.setup` matches the tested command character-for-character, `setupRunPolicy: run-by-default`, and `setupAgentStartupPolicy: wait-for-setup`. Delete the temporary `.db` copy after reading.

Final step by the user: create a real worktree, confirm `Copied …` appears in the setup tab, and verify the agent starts without re-prompting for permissions.
