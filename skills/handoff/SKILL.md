---
name: handoff
description: Saves where unfinished work stands into HANDOFF.md so the owner can /clear or start a new session without losing progress, and reads that file back to carry on. Use when the owner says "save progress", "handoff", "write it down and clear", "context is full", "before compact", "pick up where we left off", "resume", the same requests in any language, or when a session has grown long and a piece of work just finished. Not for durable rules or facts (CLAUDE.md or a shared memory), task status for others (the issue tracker), or setting up a repo (/starter-kit).
---

# /handoff

Keeps the conversation holding only the current state. `save` snapshots the work in progress
into `HANDOFF.md` at the repo root; `resume` loads exactly that file in a clean session.
With no argument: `HANDOFF.md` exists and nothing has been done yet in this conversation means
`resume`; otherwise `save`. Run every command from the repo root (`git rev-parse --show-toplevel`).

## Not for

- A rule or fact that should last: edit `CLAUDE.md`, or draft a shared-memory lesson.
- Reporting progress to others: comment in the issue tracker.
- Starting a new repo: `/starter-kit`.

## save

### 1. Take facts from the machine, not from memory
- Do: `git branch --show-current`, `git status --short` (for "Files changed"),
  `git log --oneline -5` (shas for "Done"). Leave out files made by builds and tests
  (`__pycache__`, `node_modules`, `dist`, `target`); when they are not ignored, add "add them to
  `.gitignore`" under "In progress".
  Verify: copy the command and result of the last run in this session; do not rerun it. Nothing
  ran this session: write "not run this session".
- Done when: the list of changed files comes from git, not from recollection.

### 2. Overwrite HANDOFF.md with exactly this shape
```markdown
# Handoff · <yyyy-mm-dd hh:mm local time> · branch <name>

## Goal
<one sentence: what this session is doing, and what done looks like>

## Done
- <item> (commit <sha> if any)

## In progress
- <item, where it stopped, file:line if any>

## Files changed
<from git status --short, uncommitted>

## Decisions
- <decision> · because <reason>

## Dead ends (do not retry)
- <approach tried> · failed because <reason, one line>

## Open problems
- <problem, short error text, what is known>

## Last verify
`<command>` → <result>

## Next steps
1. <first concrete action, enough for a new session to start at once> · <approved | ask first>
2. <at most 3 steps; say so when one depends on the result of the one before> · <approved | ask first>

## To move out
- <durable rule or fact found this session that the next session needs now> → <CLAUDE.md | shared-memory lesson | tracker>
```
- Do: the file is a snapshot, not a log. Overwrite, never append. Under 60 lines.
  Dead ends carry only the conclusion, never the chain of attempts. An empty section says "none".
  Write invisible or confusable characters as escapes (`\u00a0` for a non-breaking space), never the raw character.
  "approved" only when the owner agreed to that exact step this session; commit, push and delete
  are always "ask first".
- Done when: someone reading only this file, with no chat, knows what to do next.

### 3. Move out what does not belong here
- Do: a durable rule or fact just found → propose one line for `CLAUDE.md` or a shared-memory lesson. Something
  others need to see → propose a tracker comment. Ask before writing. Not approved yet, or the
  repo has no `CLAUDE.md` (suggest `/starter-kit`): keep the line under "To move out" so the next
  session still sees it. Once approved and written, remove it from there.
- Done when: everything other than the current goal's state is at its destination or under
  "To move out".

### 4. Check HANDOFF.md will not be committed
- Do: `git check-ignore -q HANDOFF.md || echo NOT-IGNORED`. Not ignored: stop and propose adding
  `HANDOFF.md` to `.gitignore`.
- Done when: the command prints nothing.

### 5. Reply to the owner in exactly three lines
```
Saved HANDOFF.md (<n> lines). Next: <step 1>.
To clear: type /clear, then /handoff
Or compact: /compact Keep the goal, files changed, decisions, dead ends, open problems and next steps as in HANDOFF.md. Drop the exploration and old command output.
```

## resume

### 1. Read and compare
- Do: read `HANDOFF.md`. A `## Live tail (auto-captured)` section, when present, is a snapshot a PreCompact
  hook took from the transcript at its `Captured` time: the last commands (`[ok]` ran clean, `[error]` or `[exit N]`
  failed, `[check]` printed a line that looks like an error; the text after `->` is that line), the last note and the git state then. It adds to the
  hand-written sections and does not replace them; it can be older or newer than they are. Compare the branch,
  `git status --short` and the shas the file names (`git log --oneline -5`) with git. A mismatch
  (other branch, a sha git does not have, files since committed, unknown files): say exactly what differs;
  git wins; do not edit anything to make it match.
- Done when: you know whether the file is current or stale.

### 2. Load selectively
- Do: open only the files named under "In progress" and "Next steps", and only the line ranges
  needed. Do not reread the repo; do not retry a dead end.
- Done when: the next step fits in one sentence, with the files it will touch.

### 3. Say it and do it
- Do: say briefly "Working on <goal>, next <step 1>", then do it when the step says "approved";
  when it says "ask first" or nothing, ask.

## When the goal is finished
Once the results are in commits, the tracker or `CLAUDE.md`, delete `HANDOFF.md` (it is
gitignored and exists only on this machine). Ask first when "Open problems" is not empty.

## Never

- Write secrets, tokens or `.env` content into `HANDOFF.md`. The live tail copies commands as typed: before
  sharing the file or quoting it anywhere, check it for keys.
- Commit `HANDOFF.md`, or delete it while work is unfinished.
- Paste whole logs, diffs or test output into the file. Only the command and the conclusion.
- Type `/clear` or `/compact` yourself: they are the owner's commands. Give the line to paste.

## Done when

- `save`: `HANDOFF.md` is under 60 lines, has all 10 sections, is ignored by git, and a new
  session reading only it names the right next step.
- `resume`: the next step is named and started without asking about anything the file already says.

## Eval

| Measure | How | Target |
|---|---|---|
| New session continues correctly | after `/clear` + `/handoff`, does the agent's first action match "Next steps" | every time |
| Questions after resume | questions about things the file already says | 0 |
| Dead ends retried | a new session tries an approach listed as a dead end | 0 |
| Invoked at the right time | 5 phrases that should invoke it + 5 that sound alike (write a rule, report a task, set up a repo) | ≥ 9/10 |

## Log

| Date | What happened | What changed |
|---|---|---|
| 2026-11-10 | Resume trial in a fresh agent with a live tail: right next step, kept "ask first"; it guessed what the tail is, what `[ok]`/`[check]` mean, which sha wins, and whether sha drift is a mismatch | The tail described as a timed snapshot that adds to the file; shas compared; git wins |
| 2026-10-17 | Resume trial in a fresh agent: right next step, avoided the dead end, kept the decision. It could not tell which step was approved; U+00A0 looked like a space | "approved / ask first" labels; escapes for invisible characters |
| 2026-10-17 | Save trial on a scratch Python repo: 8 guesses (rerun verify?, `__pycache__`, time zone, a durable fact the next session needs) | Copy verify without rerunning; leave out build files; "To move out" section; run from the repo root |
| 2026-10-17 | Created together with `/starter-kit` | v1 |

## Keeping this skill good

1. **Score each run.** A question the new session had to ask: add that section to the shape.
2. **Look things up now and then.** How `/clear`, `/compact` and rewind behave changes between
   Claude Code versions. Check code.claude.com/docs when behaviour looks different.
3. **Rerun the trial on a stronger model.** Drop the sections it no longer needs.
4. **When unsure, ask the owner.** Do not guess.
