---
status: shipped (1prompt PR #8; plan and close in claudecode-guide PR #40) # draft → approved → planned → building → verified → shipped (PR #n)
---
# Push to ambysto/1prompt as ambystobot, so the owner approves on the web

Ticket: Plane APS-49. Source: session review 2026-11-08 (`docs/reviews/2026-11-08-switch-kit-and-task-contract.md`,
proposal 1), approved by the owner 2026-11-10.

## Problem

`ambysto/1prompt`'s ruleset (`1prompt-boundary-main`, set up in APS-38) asks for a code owner's review and an
approval of the last push by someone other than the pusher, and only the repository admin role may bypass it.
`ambystobot` already has write access there for this purpose. But on this machine the `gh` wrapper and the git
credential helper pick the bot only for `ambysto-memory`; in the 1prompt clone agents push as `ambysto`, which is
the owner's own account. The owner cannot approve their own push, so the rule can never be met: PR #6 and #7 both
merged with `--admin`, and #7 cost the owner an extra message ("use --admin").

## Outcome

1. In `~/work/ambysto/ambysto-1prompt` (its clone and its worktrees), `gh api user --jq .login` prints
   `ambystobot`, and a push there goes up as the bot, as in `ambysto-memory`.
2. The owner approves and merges a 1prompt PR on the web. Or the owner says "merge" and the session runs that one
   merge with `AMBYSTO_OWNER=1` (the same path as `ambysto-memory`).
3. The account rule in `~/.claude/CLAUDE.md` ("GitHub accounts", machine section) names 1prompt beside
   ambysto-memory. 1prompt's own `CLAUDE.md` names the bot (public wording: "agents push as a bot account with
   write access; the owner approves").
4. Proof: one small real 1prompt PR pushed as the bot, approved by the owner on the web, merged without `--admin`.

## Constraints

- The wrapper (`~/.local/bin/gh`) and the credential helper are owner-only: owner-token-guard refuses agents that
  read or run them (APS-37). The owner makes that change; the session writes the exact lines to add and the check.
- 1prompt is public: no ticket ids, names or private paths in its files, commits or PR bodies; its scrub gate stays
  at zero hits.
- The rulesets do not change: no new bypass actor, no lower requirement.

## Out of scope

- Other repos. The repos in `scripts/github-boundary.json` have no ruleset applied today (claudecode-guide has
  none), so the pusher's account does not block their merges.
- Moving any other machine or harness to the bot.

## Open questions

None. Merge path (owner, 2026-11-10: "làm như memory"): the same as ambysto-memory. The owner approves and merges on
the web, or says "merge" and the session runs that one merge with `AMBYSTO_OWNER=1` (the owner's admin role
bypasses the ruleset, as in ambysto-memory).
