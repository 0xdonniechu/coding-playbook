---
status: verified # draft → planned (owner accepts) → building → verified
---
# Plan: Tasks, converge and clarify in the sdlc chain (APS-51)

Contract: `intent/2026-11-10-sdlc-tasks-converge-clarify.md` (approved 2026-11-10). This plan is written in the new
format, so its own Tasks drive the dispatch and its own build is checked by converge.

## Formats (what the checks read)

**Intent.** An open point stays where it is written as `[NEEDS CLARIFICATION: <question>]`. The section
`## Open questions` begins with `None` when nothing is open. `clarify` fails on any marker, on a missing section, or on
a section that does not begin with `None`.

**Plan, `## Tasks`.** One `###` heading per task, then bullets:

```
### T3 (builder, parallel) The skill in English, with the three changes
- allow: `skills/sdlc/**` `scripts/check.py`
- forbid: `scripts/dispatch.py`
- check: `python3 scripts/check.py`
```

- Heading: an id (`T` and a number), then `(builder)` or `(main)`, optionally `, parallel` (may run beside another
  task, so `dispatch.py new` gives it its own worktree), then a title.
- `allow` and `forbid`: globs in backticks, relative to the repo, as `dispatch.py --allow/--forbid` takes them.
  `check`: one command per bullet, in backticks; at least one per task.
- `- not needed: <reason>`: the task was dropped during the build; converge then does not ask for its files.

**Plan, `## Proof` and `## Result`.** Proof is a numbered list. Result has one numbered item per Proof item, starting
with `PASS`, `FAIL` or `not run: <reason>`, then the numbers (counts, commit, output).

**Converge** (`converge <plan> [--base <ref>]`, default base: the merge base with `origin/main`): gaps are (a) a
changed path that matches no task's `allow` and is not the plan or its intent; (b) a task, neither `not needed` nor
touched, whose `allow` matches no changed path; (c) a Proof item with no Result item, or a Result item that does not
start with one of the three words; (d) a plan with no Tasks section (nothing to compare: reported, exit 0, so old
plans stay valid). Each gap is one line; exit 1 while any gap of kind a, b or c remains.

## Tasks

### T1 (main) The plan parser, clarify and converge
- allow: `scripts/sdlc-check.py`
- check: `python3 scripts/sdlc-check.py --self-test`
- check: `python3 scripts/check.py`

### T2 (main) dispatch.py builds a contract from a task
- allow: `scripts/dispatch.py`
- check: `python3 scripts/dispatch.py --self-test`
- check: `python3 scripts/check.py`

### T3 (builder, parallel) The skill in English, with the three changes
- allow: `skills/sdlc/**` `scripts/check.py`
- forbid: `scripts/dispatch.py` `scripts/sdlc-check.py`
- check: `python3 scripts/check.py`

### T4 (main) The loop, the README and the install
- allow: `global/CLAUDE.md` `README.md` `CLAUDE.md`
- check: `python3 scripts/check.py`
- check: `python3 scripts/install.py --check`

## Deviations during the build (from the reviews, all MINOR)

- `scripts/check.py` (T3's file) also runs the `dispatch.py` and `sdlc-check.py` self-tests, and refuses a
  `skillOverrides` entry for any of the guide's skills, `sdlc` included.
- The repo's `CLAUDE.md` lists the task parser under HARD beside `dispatch.py` (added to T4's allow).
- The parser also refuses two commands in one `check` bullet and a Proof or Result number used twice; `## Tasks …`
  with words after it is still the Tasks section; `clarify` wants `None` as a word, with no list under it.
- The skill names the plan `intent/<yyyy-mm-dd>-<slug>.plan.md` (converge finds the intent by that name) and the
  script as `<claudecode-guide>/scripts/sdlc-check.py`, with no machine path (the repo's "Universal only" rule).

## Steps, in order

1. **T1, HARD (main session; hard-reviewer).** `scripts/sdlc-check.py`, standard library only:
   `clarify <intent>`, `converge <plan> [--base <ref>]`, `--self-test`, and `parse_tasks(plan)` returning each task's
   id, who, parallel, allow, forbid, checks and not-needed reason. The parser refuses a task with no `allow` or no
   `check`, a duplicate id, or a bullet it does not know, rather than guess. Self-test on a scratch repo: a marker
   fails, `None` passes, a missing Open questions fails; converge finds each of gaps a, b and c and passes a clean
   branch; an old plan with no Tasks exits 0.
2. **T2, HARD (main session; hard-reviewer).** `dispatch.py new <repo> <branch> --task <plan> <id>` and
   `dispatch.py contract <tree> --task <plan> <id>`: load the parser from `scripts/sdlc-check.py` (importlib, no
   bytecode written, as the self-test already does for agent-guard). Refused: `--task` together with
   `--allow/--forbid/--check`; an unknown id; a `(main)` task; a `not needed` task. The contract's `task` field is
   `<branch> <id>`. The globs still go through `check_globs`. Self-test: a contract from a task equals the one from the
   same flags (all fields but `task` and `written`); each refusal.
3. **T3, MEDIUM (builder via `dispatch.py new … --task <this plan> T3`, after T2; reviewer).** `skills/sdlc/SKILL.md`:
   the installed `~/.claude/skills/sdlc/SKILL.md` in English (the meaning kept, the examples kept), plus: Phase 1 marks
   open points and runs `clarify` before `approved` and before the plan; Phase 2's plan template gains the Tasks,
   Proof and Result formats above; Phase 4 runs `converge` before the review and gives its output to the reviewer.
   `scripts/check.py`: `SKILLS` gains `sdlc`. The builder gets the formats section of this plan, not the chat.
4. **T4 (main).** `global/CLAUDE.md`, "The loop": one line each for `--task` and converge. `README.md`: the skills
   table gains `skills/sdlc/`. Then `python3 scripts/install.py --global`: the hand copy of the skill is backed up and
   replaced; `install.py --check` reports no difference.

## Risks, and the check that catches each

- **A wrong contract from a plan** (a glob lost or widened by the parser): T2's self-test compares the task contract
  with the flag contract field by field; hard-reviewer on T1 and T2.
- **The parser guesses at a malformed task** and gives the builder more than the plan says: it refuses unknown bullets,
  a missing `allow` or `check`, duplicate ids (T1 self-test cases).
- **Converge passes a branch that left the plan** (glob matching that differs from agent-guard's): converge matches
  with the same rule as the contract (`fnmatch` on the repo-relative path, `**` across folders); a self-test case for
  a nested path; the real run on this branch in step 5 of the proof.
- **Old plans break**: converge on `intent/2026-11-10-1prompt-bot-pushes.plan.md` reports "no Tasks section" and exits
  0; `dispatch.py` without `--task` keeps its self-test cases unchanged.
- **The English skill drifts in meaning** from the one in use: the reviewer gets both files and checks section by
  section.
- **The install replaces the hand copy without a trace**: install.py backs up a differing file first (its existing
  rule); the backup path is in the closing summary.

## Proof

1. `python3 scripts/sdlc-check.py --self-test` PASS.
2. `python3 scripts/dispatch.py --self-test` PASS, with the new `--task` cases.
3. `python3 scripts/check.py` PASS, 3 skills.
4. `python3 scripts/sdlc-check.py clarify intent/2026-11-10-sdlc-tasks-converge-clarify.md` PASS.
5. `python3 scripts/sdlc-check.py converge intent/2026-11-10-sdlc-tasks-converge-clarify.plan.md` on this branch:
   0 gaps; on the 1prompt-bot plan: "no Tasks section", exit 0.
6. T3 dispatched with `dispatch.py new … --task … T3`; `dispatch.py show` prints that task's allow, forbid and check.
7. `python3 scripts/install.py --global` then `--check`: no difference; the old skill copy is in its backup.
8. hard-reviewer PASS on T1 and T2; reviewer PASS on T3.

Not in this plan: the personal repo the skill came from; hooks that run the checks; other repos' Verify.

## Result (2026-11-10)

1. PASS `sdlc-check.py --self-test`: clarify, the parser and each refusal, converge on a scratch repo; mutation check
   16 of 16 caught (10 on the first build, 6 on the review fixes, one per fix).
2. PASS `dispatch.py --self-test`, with the `--task` cases: the same contract as its flags, and each refusal leaves no
   folder or branch (with flags beside it, an unknown id, a main task, a not-needed task, no Tasks, a `..` glob, a
   malformed plan, a missing plan, a missing `sdlc-check.py`).
3. PASS `check.py`: 3 skills valid; it now runs both self-tests.
4. PASS `clarify` on this intent, 0 gaps.
5. PASS `converge` on this plan: see the run recorded in the PR; on the 1prompt-bot plan "no Tasks section", exit 0.
6. PASS T3 dispatched with `dispatch.py new … --task <this plan> T3`; `show` printed allow `skills/sdlc/**`
   `scripts/check.py`, forbid `scripts/dispatch.py` `scripts/sdlc-check.py`, check `python3 scripts/check.py`.
7. PASS `install.py --global` installed the skill (old copy kept as `SKILL.md.bak-20261110-143703`), then
   `install.py --check` exit 0.
8. PASS hard-reviewer on T1 and T2, reviewer on T3, each with MINOR notes only, all fixed (Deviations above). The
   repo's Verify for a skill change: one fresh headless agent (Sonnet 5.5) ran the skill on a scratch repo; clarify
   failed on its marker then passed, converge caught a stray `__pycache__` file; three guesses it reported are now
   answered in the skill (the plan's status line, an empty Result at plan time, no `allow` for the plan and intent).
