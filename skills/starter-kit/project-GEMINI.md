# <Project name>: <one line on what it is>

## What it does
<Two to four lines: what the product does, what it must never do, and what a bug costs (a wrong alert? lost user data? money?). The cost of a bug decides what is HARD.>

## Verify
These commands are the default checks of a builder's task contract (`dispatch.py --check`): each must run from the repo root with no prompt, and any file it writes (lock file, snapshot, generated code) must be allowed in the contract, or the builder's run locks.
- Unit: `<test command>`
- Build or lint: `<command>` (0 warnings)
- <Any end-to-end, replay or golden check, and when it is required>
- Owner-only or other-machine checks: <list them, so agents write "not run" instead of guessing>

## Gemini Decision 1 (`gemini-decision-1`) Gate & Triage
- **PreToolUse Command Gate (`~/.antigravity/hooks/gd1_hook.py`)**: Every shell command (`run_command`, `bash`, `execute_command`) is scored before execution:
  - `safe_read_or_dev` ($\ge 0.95$): auto-allow (`git status`, `ls`, `cat`, local unit/lint checks in `## Verify`).
  - `destructive_danger` ($\ge 0.70$): auto-deny (`rm -rf`, deleting state/DB, leaking secrets, force-pushing).
  - `risky_modify` (or lower confidence): ask for manual confirmation (`git push`, package install, service restart, config/schema changes).
- **Task Triage**: Before dispatching, rate on the 4 axes (ambiguity, coupled decisions, verifiability, undo cost) with Gemini Decision 1 against the project's `HARD` / `MEDIUM` / `EASY` boundaries below.

## HARD: the main session (`gemini-4-argon-high`) does it directly, then hard-reviewer (`gemini-4-carbon-high`)
- <The code that decides the core behaviour, where a wrong answer is silent>
- <Anything that deletes, migrates, pays, sends, or cannot be undone>
- <Credentials, auth, keys and how they are loaded>
- <Cross-component contracts, formats and test vectors>

## MEDIUM: builder (`gemini-4-hydrogen-high`) builds, reviewer (`gemini-4-argon-high`) reviews (escalate to `gemini-4-carbon-high` if main touched the diff)
- <New integrations, channels, retries and rate limits, scheduling, storage outside the HARD core>
- <A bug with a clear stack trace outside the HARD areas>

## EASY: transcriber (`gemini-3.5-flash-lite`, `low`) or builder (`gemini-4-hydrogen-high`), no review
- <Wording, formatting, reports from stored data, README and docstrings, renames, log cleanup>

## Rules
- Never silently change <thresholds / protected lists / formats>. Flag it and ask.
- <Grep lists or lint scripts that must stay at zero hits>
- <Git: account, author, branch naming, commit format, PR policy; merges: on its own once Verify and review passed, except a merge that publishes or deploys (say what a merge to main publishes)>
- <Issue tracker: where items live, language>

## Read when
- <Docs for one module, read only when a task touches it: "Touching `<path>`: read `docs/<module>.md` first". Not `@imports`: those load at launch and save nothing. Delete the section when there are none.>

## Session state
- Work in progress lives in `HANDOFF.md` (gitignored). If it exists at session start, read it before anything else. Update it with `/handoff` before `/clear`; delete it once the goal is finished and recorded.
- Durable facts go in this file or, when they hold beyond this repo, in your shared memory (a lesson PR); tasks in the tracker. `HANDOFF.md` holds only where the current goal stands.
