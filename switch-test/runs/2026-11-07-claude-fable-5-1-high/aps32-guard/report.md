**FAIL**

Checks run: `python3 scripts/check.py` PASS; `python3 hooks/agent-guard.py --self-test` PASS 58/58; `python3 scripts/install.py --check` exit 1 (agents, hook and global block differ from this machine, as expected); 44 extra cases piped into the guard from a script in /tmp. Installer: copies `hooks/*.py` to `~/.claude/hooks/claudecode-guide/`, backs up a differing file, never deletes, and `--check` reports the hook. check.py's new checks hold (the nested `hooks:` lines fold into harmless extra frontmatter keys).

1. **MAJOR** `hooks/agent-guard.py:137` A shell keyword hides the command after it: `command_words` does not skip `if`/`then`/`do`/`else`/`while`/`for`, so the segment's name becomes the keyword. Confirmed allowed in build mode: `if ! git diff --quiet; then git commit -am wip; fi` and `for f in a b; do git push origin $f; done`. This is a mistake-grade pattern, not evasion.

2. **MAJOR** `hooks/agent-guard.py:230` Combined short flags beat the in-place check: `sed -Ei 's/a/b/' f.py`, `sed -ni …`, `perl -lpi -e …` all allowed in review mode. `sed -Ei` is the common idiom.

3. **MAJOR** fail-open paths, undocumented. Claude Code treats any exit other than 2 as non-blocking, so: (a) no `python3` on PATH → exit 127 → every Bash call runs unguarded with no sign (README says only "Needs python3"; CLAUDE.md Open says the PATH is "assumed"); (b) odd input → traceback → exit 1 → runs: confirmed with `[]`, `"tool_input":"x"`, `"command":123` (AttributeError). The docstring's "when it cannot parse a command it blocks it" is only true for shlex errors. A `|| exit 2` on the hook command and a catch-all around `check` would close both.

4. **MINOR** further slips (evasion-adjacent, but cheap to close): wrapper with a valued flag (`nice -n 10 git push`, `timeout -s KILL 30 git push`, `xargs -n 1 git push`); `bash -lc`/`bash -ec "git push"`; `gh api -XPOST …`; backslash-newline (`git \⏎push`); `find … -exec rm {} \;`; `<(git add .)`; PowerShell aliases (`del`, `Add-Content`, `Rename-Item`) and `git.exe`/`Git` on Windows; `npm version patch` (commit + tag); `curl -X POST api.github.com/…`.

5. **MINOR** false positives on normal read work, against the task's "must not get in the way": `git tag` (bare list), `git fetch origin`, `git submodule update --init`, `git branch --sort=…`, `git config user.name` (a read), `gh --version`, `gh help pr`, `gh api graphql -f query=…` (every GraphQL read), `gh release download`, `mkdir -p "$TMPDIR/rv"` (variables are not expanded, though the message says a temp dir is fine), and any `# comment` containing an apostrophe blocks the whole command (`commenters` disabled). Blocking `git fetch` is also not in the task's list.

6. **MINOR** `agents/builder.md`, `agents/reviewer.md`: the bodies still describe the limits as prompt rules and say nothing about the hook or what a blocked agent should do; only the stderr line does. CLAUDE.md "Open" and README otherwise match the behaviour.

Not run: `install.py` without `--check` (forbidden here); the Verify step "run the agent once on a known diff from `/agents`" (needs a fresh session); Windows/PowerShell hook invocation (no Windows shell here).
