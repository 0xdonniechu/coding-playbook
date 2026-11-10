# Known findings: aps32-guard

The original first-round report, verbatim (claude-fable-5-1). Issue n of the report is `K{n}` in results.md.

---

**FAIL** (one MAJOR; the rest MINOR)

Issues

1. MAJOR `/home/dc-group/work/ambysto/claudecode-guide/hooks/agent-guard.py:48,216,183-194` — combined short flags slip through, and these are plausible mistake-forms, not evasion. Review mode allows `sed -Ei 's/a/b/' f`, `sed -ri`, `sed -ni`, `perl -ni -e 1 f` (only a flag *starting* with `-i`/`-pi` is caught). Build mode allows `bash -lc 'git push'` (`-c` must be a separate word) and `gh api -XPOST repos/o/r/issues` (`-X` glued to its value). Fix: treat any single-dash flag cluster containing `i` for sed/perl, any `-…c` cluster for shells, and `-X<METHOD>` for gh.

2. MINOR `agent-guard.py:20,110` — glued operators: `test -f x ||(git push)` and `true &&(git commit -m x)` pass (shlex yields the token `||(`, which is not in OPERATORS). Strip trailing `(`/leading `)` from operator tokens.

3. MINOR `agent-guard.py:65` — a `<<WORD` with no matching terminator line (here-string `grep x <<< "git"`, or a quoted `"<<EOF"` pattern) drops every following line, so `grep x <<< "git"\ngit push` is allowed. Fail-open for everything after it.

4. MINOR `agent-guard.py:172` — `git checkout -b topic --` / `-B main --` create or reset a branch but pass because `--` is present. Also `nice -n 10 git push` and `sudo -u x git push` pass (the wrapper's option value becomes the "command"). Windows: `git.exe push` and `Git push` pass (basename compared case-sensitively, `.exe` kept).

5. MINOR `agent-guard.py:239-259` — uncaught exceptions fail open: input `[]`, `"x"`, `{"tool_input":"git push"}` or `command: ["git","push"]` raise AttributeError, exit 1, which Claude Code treats as non-blocking. Contradicts the docstring "when it cannot parse a command it blocks it". Wrap `main` in `except Exception` → exit 2. Also, a missing `python3` exits 127 (fail-open, command runs); a missing script exits 2 (fail-closed). Neither is stated in README/CLAUDE.md "Open".

6. MINOR false positives (clear reasons, alternatives exist, but worth a doc line or a whitelist): bare `git tag`, `git branch --sort=…`, `git config user.name` (read), `git submodule update --init` (may be needed for a build), `gh api graphql -f query=…` (read), reviewer `git apply --check`, `chmod +x /tmp/x`, `echo x > "$TMPDIR/x"` (variables are not expanded; `TMPDIR` is unset here, and `scratchpad_dir` is not a documented hook field, so only the hard-coded `/tmp` list works), and any backtick-quoted `git push` inside a grep/echo string (`grep -rn '`git push`' docs/` is blocked).

7. MINOR docs — `CLAUDE.md` HARD bullet on installer writes does not list `~/.claude/hooks/claudecode-guide`; README install comment still says "agents and skills"; `CLAUDE.md` Rules still require the Co-Authored-By trailer although this commit (correctly, per the 2026-10-20 owner decision) omits it and that decision says to fix the line in the next PR.

Checked and sound: install.py backs up differing files, never deletes, `--check` reports hooks (verified "unchanged"); check.py fails when the hook block is removed, the mode is wrong, a shell is added to transcriber, or `commit` is dropped from the guard (mutation check done on a scratch copy); `git -C`, `-c`, `$(…)`, subshells, functions, `;`/`&&`/`|`, line continuation, heredoc commit messages, quoted/pathed `git`, PowerShell `Remove-Item` are all blocked; 26 odd fragments (`>`, `$(`, `((`, `gh api -X`…) raise no exception.

Commands run
- `python3 scripts/check.py` → PASS (exit 0)
- `python3 hooks/agent-guard.py --self-test` → PASS 58/58
- `python3 scripts/install.py --check` → exit 1, only the pre-existing global-block difference; agents, hook and skills "unchanged"
- 56 crafted guard probes + 11 odd-JSON inputs + 26 fragment fuzz (script in `/tmp/claude-1000/-home-dc-group-work-ambysto/d0b7e864-6014-493d-bb07-8e86bb56207f/scratchpad/probe.py`)
- Mutation checks of check.py on a scratch copy (4/4 caught)

Not run: `install.py` without `--check` (forbidden by task); the Verify step "run the agent once on a known diff and record it in the PR" (no PR yet; this review session itself ran under the installed hook without a false block); Windows/PowerShell hook invocation (no VM run; CLAUDE.md already lists it as untested).
