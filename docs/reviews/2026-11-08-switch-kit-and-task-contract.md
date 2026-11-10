# Session review: switch kit and task contract (2026-11-08)

Tickets: APS-45 (switch-test kit), APS-47 (one-command model switch, main-session effort `high`), APS-48
(installer refuses unknown arguments), APS-46 (task contract per builder dispatch). Kept at the owner's request
(2026-11-10). The starter-kit skill's files did not change; the way work is handed out did.

## How the work changed

| Area | Before | After |
|---|---|---|
| What a builder may change | agent-guard blocked only git/gh commands that commit, push, merge or switch branch; Edit and Write were unchecked | Every dispatch carries a task contract (allowed and forbidden paths, checks) in the tree's git folder. No contract: read only. A change outside it, by any writer, locks the run to reading, and the report starts `OUTSIDE CONTRACT:` |
| Checks | The builder said "passed" | The builder names every contract check verbatim with its result; the main session reruns them as its gate |
| Parallel builders | "Give each agent its own worktree", by hand | `dispatch.py new` makes the worktree, branch and contract in one command; `done` refuses uncommitted work |
| Switching models | Hand edits to settings, effort and each agent file; no standard test | `switch-test/` prepared for the next release; `switch-model.py` makes the repo's edit in one command; main-session effort recorded (`high`) |
| Installer | A mistyped argument still ran | Unknown arguments are refused with nothing written |
| After installing an agent | Not considered | The new definition takes effect in the next session (lesson `agent-file-loads-at-session-start`) |

Cost: one extra command per builder dispatch; a check that writes files must be allowed in the contract or the
run locks; small tasks (one or two files) are still done directly.

## What we learned

1. A reviewer on a different model finds real defects: hard-reviewer found a MAJOR in the guard (a tree removed
   mid-run blocked the builder and its Stop for good) that the author's own tests missed.
2. Mutation checks keep self-tests honest, but each fix needs its own: 41 mutations were caught, and the reviewer
   still found a fix (the order of removal in `dispatch.py done`) that no test exercised (lesson
   `mutation-check-self-tests`, updated).
3. A real run finds what a self-test does not: the builder brief said "never nothing" when no path was forbidden.
4. Prove an agent change in a new session: the first live lock proof showed no guard because the installing session
   still ran the old builder; a new headless session locked at once.
5. Owner time goes to merges: APS-46 took 10 owner steps, 5 of them merges, and no "done?" question (APS-47 had 2),
   since every task ended with the standard summary.

## Proposals (approved by the owner 2026-11-10)

1. APS-49: push to `ambysto/1prompt` as `ambystobot`. The ruleset there asks for an approval of the last push by
   someone else, and `ambysto` is the owner's own account, so the rule can never be met and every PR merged with
   `--admin`. As the bot, the owner approves on the web. The account switch itself is an owner-only step.
2. APS-50: the project template's Verify says its commands are the builder's default contract checks (this PR).
