**FAIL**

I ran the checks myself and probed the guard with about 160 commands. It misses common forms of forbidden commands, and it lets the command through when it crashes.

1. **MAJOR** `hooks/agent-guard.py:137-156, 210-219`: Shell keywords and joined flags hide the real command. These all exit 0 (allowed):
   - `if true; then git push; fi` and `for f in *; do git commit -m x; done`: the guard reads `then`/`do` as the command name.
   - `bash -lc 'git push'`, `sh -xc …`, `bash -ec …`: only a bare `-c` is matched.
   - `nice -n 5 git push`, `sudo -u x git push`, `env -u FOO git push`, `xargs -I {} git push`: the wrapper's option value is read as the command.
   - `pwsh -Command`, `powershell -c`, `cmd /c` are not in `SHELLS`.
   - `cat <<EOF | sh` with `git push` inside the heredoc.

   Loops and `bash -lc` are normal agent habits, not evasion. This is the class of mistake the task asked to block.
2. **MAJOR** `hooks/agent-guard.py:191, 230`: Joined short flags slip through.
   - `gh api …/pulls/1/merge -XPUT` and `gh api -XPOST …` are allowed. That merges a PR, a GitHub write the task forbids.
   - `gh api … -fx=1` is allowed.
   - In review mode, `sed -Ei 's/a/b/' f` and `sed -ni …` are allowed, so in-place edits get through. `sed -Ei` is a common form.
3. **MAJOR** `hooks/agent-guard.py:239-259`: It fails open on any unexpected exception. `main` catches only `Blocked` and the JSON error; anything else exits 1, which Claude Code treats as non-blocking, so the command runs.
   - Reproduced with: a command containing a NUL (`echo x > a\0b`), a non-string `command`, input of `[]` or `null`, and `scratchpad_dir: 5` together with `git push`.
   - This contradicts the docstring ("When it cannot parse a command it blocks it").
   - A missing `python3` (exit 127) also fails open. Only the Windows part of that is documented.
4. **MAJOR** `hooks/agent-guard.py:44-46`: The `PowerShell` matcher is set, but PowerShell is barely covered. `remove-item f` (lowercase), `ri`, `del`, `rm.exe` and `Add-Content` are all allowed for reviewers. PowerShell cmdlet names ignore case, and `Add-Content` is missing from the list.
5. **MINOR** `hooks/agent-guard.py:224-229`: In review mode, `find . -delete` and `find … -exec rm {} +` are allowed. `git remote -v add x y`, `git tag --list -d v1` and `git branch --show-current x` pass because only the first argument is checked.
6. **MINOR** False positives that will get in the reviewers' way:
   - Temp dirs written through a variable are blocked: `mkdir -p "$TMPDIR/x"`, `d=$(mktemp -d) && cp a $d/`, `echo x > "$(mktemp)"`.
   - Plain reads are blocked: `git config user.name`, `git config --get-regexp`, `chmod +x /tmp/s.sh`.
   - `echo '$(git push)'` is blocked although the single quotes make it plain text.
   - Relative paths resolve against the hook's working folder, not the agent's after a `cd`.
7. **MINOR** `scripts/check.py:94-97`: The frontmatter check only looks for the strings anywhere in the text. A matcher placed under `PostToolUse` would still pass.
8. **MINOR** `hooks/agent-guard.py:30, 172`: The builder may run `git stash` and `git stash pop`. They write `refs/stash`, and the task does not list them as allowed.
9. **MINOR** `CLAUDE.md:31`: The Rules line still asks for the Co-Authored-By trailer. The global owner decision of 2026-10-20 says the next PR that touches a repo fixes it; this commit edits `CLAUDE.md` but leaves that line. The commit itself correctly has no trailer.

Installer: it is fine. Hooks go through `install_file` (backup first, never deletes), `--check` covers the hooks folder, and the docs match. Since agents are installed before hooks, an interrupted install leaves the hook script missing. Then python exits 2 and every guarded agent's Bash is blocked, which fails closed.

The self-test's 58 cases do not cover items 1–5.

**Commands run:**
- `python3 scripts/check.py`: PASS (exit 0).
- `python3 hooks/agent-guard.py --self-test`: PASS 58/58.
- `python3 scripts/install.py --check`: exit 1. This machine's installed copy differs from the repo (3 agents, the hook, 2 skill files, global block). That is expected before installing and is not a defect in the change.
- My guard probes, run with `/tmp/rvprobe/probe.py`.

**Not run:**
- `install.py` without `--check`: forbidden.
- Live `/agents` run of the hooked agents: needs a new session.
- Windows / PowerShell host: not available here.
- Mutation check: not needed, because no fix is claimed for a dangerous path.
