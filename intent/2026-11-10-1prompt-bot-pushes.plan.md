---
status: verified # draft → planned (owner accepts) → building → verified
---
# Plan: push to ambysto/1prompt as ambystobot (APS-49)

Contract: `intent/2026-11-10-1prompt-bot-pushes.md` (approved 2026-11-10). Rating: HARD (which account pushes,
credential helpers). The owner makes the account change; the session changes the rules that name the account,
opens the proof PR and sends the doc diffs to `hard-reviewer`.

Two points differ from the intent's words, for the owner to accept with this plan:
- 1prompt keeps its account rule in `CLAUDE.local.md` (gitignored), not in the public `CLAUDE.md` ("Maintainer-
  specific rules (account, author, tracker) live in `CLAUDE.local.md`"). The bot rule goes there; the public file
  only gets one reworded line (step 3).
- The public `CLAUDE.md` lists "anything run as the bot account" as owner-only, which would forbid exactly what this
  ticket sets up. It becomes "the bot account's own setup (its token and access)".

## Steps, in order

1. **Owner (the wrapper and the credential helper; agents are refused there, APS-37).** Wherever
   `~/.local/bin/gh` and the git credential helper pick `ambystobot` for ambysto-memory, and let `AMBYSTO_OWNER=1`
   pick `ambysto` there, add the 1prompt clone the same way:
   - the folder `~/work/ambysto/ambysto-1prompt` and its worktrees `~/work/ambysto/ambysto-1prompt-*` (the
     `dispatch.py new` naming);
   - a command naming the repo from elsewhere (`-R ambysto/1prompt`, `--repo ambysto/1prompt`, a
     `repos/ambysto/1prompt` API path), if the memory rule matches those too;
   - for git: the remote `github.com/ambysto/1prompt`, if the helper matches by remote rather than by folder.
   Then run and paste the four outputs (step 2 checks them):
   ```
   cd ~/work/ambysto/ambysto-1prompt && gh api user --jq .login                       # ambystobot
   cd ~/work/ambysto/ambysto-1prompt && AMBYSTO_OWNER=1 gh api user --jq .login       # ambysto
   cd ~/work/ambysto/claudecode-guide && gh api user --jq .login                       # ambysto
   cd ~ && gh api user --jq .login                                                     # 0xdonniechu
   ```
2. **Session: check the switch** without touching the helper: the same four commands from the session (the wrapper
   prints only the login). Any other output stops the plan here.
3. **Session: 1prompt rules** (branch in a worktree of 1prompt, made as the bot):
   - `CLAUDE.local.md` line 3: "the `ambystobot` account for pushes and PRs (`gh api user --jq .login` prints
     `ambystobot` in this clone and its worktrees); the owner (`ambysto`, code owner and admin) approves and
     merges on the web, or says "merge" and the session runs that one merge with `AMBYSTO_OWNER=1`"; the rest of
     the line (author, no trailer) unchanged. Untracked file: no PR, it changes in place.
   - `CLAUDE.md` (public) Verify, "Owner-only" line: "anything run as the bot account" → "the bot account's own
     setup (its token and access)". Commit subject and PR body in generic words (no ticket id, no names beyond
     the repo's own). `python3 scripts/check.py` with the scrub gate at zero hits before the push.
4. **Session: this machine's account rule.** `~/.claude/CLAUDE.md`, machine section, "GitHub accounts" bullet:
   "except in `ambysto-memory` (…), where agents act as the bot `ambystobot`" → names `ambysto-1prompt` beside it,
   with the same merge path. This section is outside the claudecode-guide block, so it is edited in place (no PR);
   the diff is shown in the closing summary.
5. **Proof PR.** The step-3 1prompt PR is the proof: opened by `ambystobot`, reviewed by `hard-reviewer` (diff range),
   approved by the owner on the web, merged without `--admin` (on the web, or `AMBYSTO_OWNER=1 gh pr merge` with no
   `--admin`).
6. **Close.** Plan → verified, intent → shipped, in a small claudecode-guide PR; APS-49 → Done.

## Risks, and the check that catches each

- **The wrapper change breaks `gh` elsewhere** (wrong account in another repo or outside Ambysto): step 1 and 2's
  four outputs, two of which are outside 1prompt.
- **The bot cannot push a branch or open a PR in 1prompt** (write access missing, the tags ruleset matching a branch):
  step 5 fails at the push; the bot's access was set in APS-38 and read on 2026-11-10 (`ambystobot: write`).
- **The owner's approval still does not unblock the merge** (another rule in the ruleset): step 5 shows
  `mergeStateStatus` after the approval; if it stays BLOCKED, the session reads the ruleset again and asks the owner,
  never adds `--admin` on its own.
- **A leak into the public repo**: the scrub gate at zero hits; the PR body names no ticket, person or machine path.
- **Sessions in other worktrees of 1prompt keep pushing as `ambysto`** until the wrapper matches them: the
  `ambysto-1prompt-*` pattern in step 1, checked in step 2 from a worktree made for step 3.

## Proof

1. Step 2: the four logins as listed, from the session.
2. Step 3: 1prompt `python3 scripts/check.py` PASS, scrub gate 0 hits.
3. Step 5: `gh pr view <n> --json author,reviews,mergedBy` shows author `ambystobot`, an approval by `ambysto`, merged
   with no bypass (`mergeStateStatus` CLEAN before the merge).
4. `hard-reviewer` PASS on the 1prompt diff and on the `~/.claude/CLAUDE.md` diff.

## Result (2026-11-10)

1. Step 1: the owner ran the patch (four `case` lines, backups `.bak-aps49`, `bash -n` both files); four logins ok.
2. Step 2, from the session: 1prompt clone `ambystobot`, a new worktree `ambysto-1prompt-bot-rule` `ambystobot`,
   1prompt with `AMBYSTO_OWNER=1` `ambysto`, claudecode-guide `ambysto`, `~` `0xdonniechu`.
3. Step 3: `CLAUDE.local.md` line 3 edited in place; public `CLAUDE.md` line 12 in 1prompt PR #8; `check.py` PASS,
   scrub gate 0 hits (16 patterns, 20 files, 18 commit messages).
4. Step 4: `~/.claude/CLAUDE.md` "GitHub accounts" names `ambysto-1prompt` (`ambysto/1prompt`) beside
   `ambysto-memory`, same merge path.
5. Step 5: 1prompt PR #8 author `ambystobot`, review APPROVED by `ambysto` on the web, `mergeStateStatus` CLEAN,
   merged by `ambysto` with `AMBYSTO_OWNER=1 gh pr merge 8 --merge` (no `--admin`), merge commit 8698c9e.
6. `hard-reviewer`: PASS on the three diffs, two MINOR notes: the "Two identities" bullet in `~/.claude/CLAUDE.md`
   still says Ambysto repos use only `ambysto` (true of ambysto-memory before this ticket too); the public file names
   "the bot account" without introducing it (the deviation stated above).

Not in this plan: other repos (no ruleset applied there today); changing any ruleset; the bot for any other machine
or harness.
