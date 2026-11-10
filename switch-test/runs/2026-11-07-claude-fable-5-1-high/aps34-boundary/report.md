**FAIL**

Scope, wiring and docs are sound: only `hooks/autonomous-settings.json` references `boundary`, no agent frontmatter does, `check.py` validates the JSON and `install.py` installs it. The self-test caught 4 of 4 mutations I made. Three plain, non-evasive gaps remain.

1. **MAJOR** `hooks/agent-guard.py:425-437`. `git push origin HEAD` and `git push -u origin HEAD` on `main` are allowed. Two names are given, so the current-branch check is skipped, and `HEAD` is not matched as a destination. This is the most common push form. Resolve `HEAD` (and a bare ref whose name matches no local branch) through `git rev-parse --abbrev-ref`. CLAUDE.md's "a push to main is [blocked]" overclaims until then.

2. **MAJOR** `hooks/agent-guard.py:528-531`. `bd update tr-gate --status=closed` closes a gate or owner item without the `bd show` check. The status scan iterates `rest[:-1] + [""]`, so a `--status=closed` as the last argument is never seen. `-s closed` and `--status closed` are caught. Confirmed with the fake `bd`.

3. **MAJOR** `hooks/agent-guard.py:323-375`. Publishing through a runner is not caught: `python3 -m twine upload dist/*`, `npx vercel --prod`, `pnpm dlx vercel --prod`, `uvx`/`pipx run twine upload`. Also `npm version patch` creates a git tag. Add `npx`, `pnpm dlx`, `bunx`, `yarn dlx`, `uvx`, `pipx run` and `python -m <tool>` as wrappers, and `npm/yarn/pnpm version` to the tag rule.

4. **MINOR** `:432-434`. `git push origin v1.0.0` and `git push origin tag v1.0.0` push an existing tag (creation is blocked, so lower risk). Cheap: `git rev-parse -q --verify refs/tags/<name>`.

5. **MINOR** `:355-356`. `gpg -ab file` (common combined flags) and `git commit -S` sign but pass. Use a `-[a-zA-Z]*[sb]` match like the push rule.

6. **MINOR** `:335-337`. SECRET_PATH misses `.gnupg/`, `.aws/credentials`, `.kube/config`, `.config/vercel/`, `*.key`, `*.snk`, `*.pvk`, `.env*`. `.pem` blocks reading a public cert (`openssl x509 -in c.pem`), and `certutil -hashfile` is a false block on the Windows VM.

7. **MINOR** `:343`. `LICENSE*` does not match `LICENCE` (the spelling this repo's prose uses). `CLAUDE.md` and `~/.claude/CLAUDE.md`, where the rules and protected lists live, are not protected by default.

8. **MINOR** `:534-541`. `bd -C <cwd> show` is unverified against bd 1.3.1 (no binary here); the fake `bd` would hide an unknown flag, which would turn every close into a false block. Use `subprocess.run(..., cwd=cwd)` instead. `--remove-label` is missing from the value list, so `bd update tr-ok --remove-label parked -s closed` tries `bd show parked` and false-blocks.

9. **MINOR** `:470-492`. `gh workflow run` is blocked but `gh api … /dispatches` and `gh run rerun` are not; `gh api repos/o/r/git/refs -f ref=refs/tags/v1` creates a tag; `gh codespace create` spends money. Each is one regex addition.

10. **NIT** `rm`/`mv`/`git rm` on `docs/spec/*` pass (CLAUDE.md names only `sed -i`, `cp`, interpreters). `git -c alias.…` is not checked in boundary mode though `check_git` has the rule. A malformed `.claude/boundary.json` blocks with a generic "could not check" message (fail-closed, acceptable).

**Run:** `python3 scripts/check.py` PASS. `python3 hooks/agent-guard.py --self-test` PASS (132 + 77 cases). `scripts/install.py --check` exit 1: the installed copy is newer than this old head, expected here. 90 probe commands via a scratch import. Mutations: drop `--tags`, drop the gate-type check, blank the boundary.json pattern, drop the bare-push branch check: all four failed the self-test. **Not run:** real `bd update --help`/`bd close --help` (no bd binary on PATH); a live `claude --settings` session.
