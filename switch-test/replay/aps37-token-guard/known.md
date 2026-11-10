# Known findings: aps37-token-guard

The original first-round report on the original commit 1f8064f, verbatim (claude-fable-5-1). Issue n is `K{n}`. A replay is scored on which of these mistakes it repeats.

---

**FAIL**

Issues:

1. **MAJOR** `/home/dc-group/work/ambysto/claudecode-guide-guard/guard/owner-token-guard.py:26-32` — the deny list misses the token paths an agent most plausibly runs by accident, confirmed by experiment (allowed by the hook):
   - `printf 'protocol=https\nhost=github.com\n' | git credential fill` run in any `~/work/ambysto/*` dir returns `username=ambysto password=<owner token>` (verified, redacted). Also `git-credential-ambysto.sh get` directly.
   - `gh auth --user ambysto token`: cobra accepts flags before the subcommand (verified with `gh auth --hostname github.com status`), so the `auth\W{1,8}token` adjacency is trivially broken; likewise `gh auth -t status`.
   - `gh alias set --shell e 'echo $GH_TOKEN'; gh e`: the wrapper exports the owner's token into `GH_TOKEN` and execs gh, so any shell alias or `gh extension` prints it, and the alias persists in config.yml.
   - `GIT_TRACE_REDACT=0 GIT_CURL_VERBOSE=1 git ls-remote https://github.com/ambysto/...`.
   Fix now: deny `git credential` (fill/get) and the helper by name, `gh alias set`/`gh extension install`, `GIT_TRACE_REDACT`, and flags between `auth` and `token`/`status`. Document only: `au''th`, `$a token`, `eval`+base64, `xargs` assembly, `from keyring import`, `secretstorage`, `cat ~/.config/gh/*.yml`, `cd ~/.config/gh && cat hosts.yml`.

2. **MAJOR** same file:26 — false positives on ordinary work in every session: `git commit -m 'Fix auth token refresh'`, `git log --grep 'auth token'`, `grep -rn 'auth-token' src/`, `echo 'see docs/auth/token.md'`, `cat docs/auth.token.md` are all **denied**. Any project with authentication code hits this daily. Anchor the pattern to `gh` (or the quoted-list form) rather than bare `auth…token`.

3. **MINOR** same file:34 — the `ask` rule needs the literal word: `export $(cat f)`, `env $(echo QU1CWVNUT19PV05FUj0x | base64 -d) gh pr merge`, `A=AMBYSTO_; export ${A}OWNER=1` all pass silently. Document (the wrapper's own comment already calls it a convention). Conversely `grep AMBYSTO_OWNER ~/.local/bin/gh` prompts the owner.

4. **MINOR** same file:55-58 — `Grep pattern=oauth path=~/.config/gh` (directory) is allowed and reads hosts.yml; irrelevant here (token is in the keyring, `hosts.yml` has 0 `oauth_token` lines) but matters on a machine without a keyring.

5. **MINOR** `/home/dc-group/work/ambysto/claudecode-guide-guard/scripts/install.py:203` — `"hooks": null` → `AttributeError` traceback (exit 1) after the defaults were already written. Also with `hooks` a list or `PreToolUse` a dict, `--settings` writes the defaults first and then refuses with exit 2, contradicting the docstring "exit 2 and nothing written".

6. **MINOR** install.py:184-208 — when defaults drift and the guard is missing, settings.json is written twice with two backups in the same second (`.bak-…`, `.bak-…-1`); the second backs up the intermediate file. Harmless, document or merge the writes.

7. **MINOR** install.py `--check` without `--settings` on an unreadable settings.json exits 0 without checking the guard entry (verified).

Not verified: whether a hook `ask` reaches the owner under the real settings' `autoMode`/bypass modes (needs a live session); PR body "Limits" section not compared line by line.

Commands run:
- `python3 guard/owner-token-guard.py --self-test` → PASS 0 failures; `python3 scripts/check.py` → PASS.
- 45-case probe via stdin (scratchpad `probe.py`): 24 gaps listed above; JSON output matches `hookSpecificOutput.permissionDecision` deny/ask; malformed JSON → exit 2 (fail-closed, acceptable for all four matched tools); `[]`, `null`, `42`, empty → allow.
- Installer on temp HOMEs (copy of real settings, none, no file, hooks list, PreToolUse dict, hooks null, BOM+CRLF, not-JSON): real-shape run appended exactly one entry, all 13 Orca events and PreToolUse order byte-identical, idempotent, `--check` exit 0, BOM and CRLF preserved; failures as in 5-7.
- Mutation: removing the `auth token` pattern → self-test 5 failures; `ask`→`allow` → 3 failures.
- Not run: real-HOME install (forbidden), live Claude Code `ask` prompt.
