**FAIL**

1. **MAJOR** `hooks/agent-guard.py:167-180`: a push to main through ordinary commands gets past the hook. If you name a refspec, the current branch is never checked, so `HEAD` and `@` are let through as targets. I tested this on a scratch repo checked out on `main`: `git push origin HEAD`, `git push -u origin HEAD` and `git push origin @` were all allowed, while `git push origin` was blocked. `git push -u origin HEAD` is a very common idiom. The CLAUDE.md line "a push to main is [blocked]" claims more than the code does.

2. **MAJOR** `agent-guard.py:167-170`: a tag can be pushed by its name. `git push origin v1.2.4` and `git push origin tag v1.2.4` are allowed. The local tag comes from ordinary release steps the hook does not block: `npm version patch`, `yarn version --patch`, `pnpm version patch`. Tags are on the human-only list.

3. **MAJOR (unconfirmed: bd 1.3.1 is not on this machine)** `agent-guard.py:274-289`: `bd close --reason done`, `bd close` and `bd update --status closed` without a bead id leave `ids` empty, so `bd show` never runs and the close is allowed. If bd 1.3.1 then acts on the last-touched bead, a gate closes without the check. Either way the "blocks when it cannot read the bead" rule is not met. A close with no id should be blocked.

4. **MINOR** Protected paths can still be deleted or replaced with plain commands: `rm docs/spec/a.md`, `mv x LICENSE`, `git rm docs/spec/a.md`, `git checkout main -- docs/spec/a.md`, and `rm -rf .claude`, which also removes `boundary.json`. The docs name only `cp`, `sed -i` and interpreters as gaps. Checking the path arguments of rm, mv, cp, `git rm` and `git restore`/`checkout --` would be cheap.

5. **MINOR** Secrets and signing that still get through:
   - `cat .env` and `cat ~/.aws/credentials` are allowed.
   - The Read tool on `~/.ssh/id_*` is not checked at all; only Bash words are.
   - Signing: `git commit -S`, `gpg -bsa`, `gpg --sign-key` and `gpg --detach-sig` are allowed.
   - Key creation: `openssl ecparam -genkey` and `openssl rsa` are allowed.

6. **MINOR** Publishing that still gets through:
   - Uploads and pushes: `python -m twine upload`, `docker buildx build --push`, `docker image push` and `vercel --prod=true`.
   - GitHub API: `gh api graphql` mutations, and a tag made through the API (`gh api …/git/refs -f ref=refs/tags/v1`).
   - MCP tools pass with rc 0. The README says it "blocks the human-only list" with no caveats.

7. **MINOR** The bd allowlist lets through more than the intent's "status, evidence, cost, claim":
   - `--priority`, `--defer` and `--due` are allowed.
   - `bd create x --deps blocks:tr-1` and `--parent tr-1` change an existing bead's deps.
   - `--set-metadata Gate=x` (capital G), `bd reopen` and `echo DO_NOT_TRACK=1; bd ready` pass. The last is a cheap evasion to close.
   - I could not check the flags against bd 1.3.1's `--help`, and could not check that `bd -C <dir> show --json` works the way the close check assumes.

8. **MINOR (false blocks)** SECRET_PATH and GUARD_PATH are matched against every word of a command:
   - `git commit -m 'parse .npmrc registry'`, `ls app/secrets/` and `grep -rn id_rsa src/` are blocked.
   - `git diff -- .claude/settings.json` and `git log -p -- .claude/agents` are blocked.
   - A repo with a `secrets/` folder becomes hard to work in.

9. **NIT** GUARD_PATH is checked only on the resolved real path. If `~/.claude` is a symlink into a dotfiles folder, its settings and hooks are not protected.

**What holds:**
- The ordinary-work cases pass: feature-branch commit and push, `gh pr create`, `gh pr comment`, `gh api …/comments`, and `bd ready`, `show`, `create`, `update --claim`, `close`.
- A `boundary.json` that is malformed, a list, or has a non-list `protected` blocks writes, so it fails closed.
- Only `hooks/autonomous-settings.json` uses `boundary` mode; agents/, global/, skills/ and templates/ have no match, so interactive sessions are unchanged.
- install.py installs `hooks/*.json`, and check.py validates the settings file.
- `docs/spec/*` matches nested paths under fnmatch.

**Commands run:**
- `python3 scripts/check.py`: PASS, exit 0.
- `python3 hooks/agent-guard.py --self-test`: PASS, 132 command cases plus 77 boundary cases, 0 failures.
- About 150 probe commands against a scratch copy of the hook, on scratch repos under `/tmp` (one on `main`, one on a feature branch).
- Six end-to-end runs of the hook in `boundary` mode, with JSON on stdin.
- Six mutation checks: removing the refs/tags check, the gate-type check, the frozen-metadata check, the DO_NOT_TRACK check, the `boundary.json` extra patterns or the tee targets. The self-test failed on each one.

**Not run:**
- Real `bd` 1.3.1 (`--help`, `show --json`): no binary on this machine.
- `install.py --check`: it compares `~/.claude` on this machine with the repo, so it does not tell anything about this commit.
- A live `claude --settings` run: it is outside a reviewer's scope.
