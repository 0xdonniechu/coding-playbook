---
status: approved # owner 2026-11-11: "còn việc gì thì resolve nốt" (resolve what is left), after the APS-66 follow-up list
---
# Intent: session gates follow-ups (APS-67)

The APS-66 hard review left MINOR follow-ups. The owner asked to resolve what is left.

## What changes
1. `.claude/branch-name.json` gains an optional `no_push` list; this repo lists `main` and `master`, so "never a push
   to `main`" is held by the hook, not only written.
2. Command reading: heredocs found over the whole text (multi-line quoted `<<` is no heredoc; any delimiter, quoted or
   `\EOF`), line continuations joined, leading shell keywords dropped (`then`, `do`, `{`, `time -p`, ...).
3. Trees under review: paths inside quoted strings of a subagent's command are recorded; `gh pr merge` changes the
   local tree only with `--delete-branch`.
4. Lesson recall: a lesson's optional `match:` regex (ambysto-memory, same ticket) is used before backticked tokens;
   13 command-shaped lessons get one, and the systemd lesson no longer fires on the memory-cap command.
5. The self-test covers `flock` with parallel processes.

## Not changed
- A `git pull` in the shared memory stays refused while a subagent that read it runs (agent-guard's scope).
- Interpreters and scripts that run git still pass: the gates catch mistakes, not evasion.
