---
name: create-skill
description: Helps you turn a recurring job into your own skill, written from a one-page SKILL.md template, trialed on a real case, with a countable eval and a feedback log, then installed into Claude Code or Cursor. Use when saying "create a skill", "turn this into a skill", "write a skill", "new skill", "fix a skill", or when you catch yourself pasting the same prompt a second time. Not for one-off work (a prompt is enough), or when a machine-blockable error needs a hook or script.
---

# /create-skill

The skill that creates skills. You describe a job you do often, the agent asks back a few questions, writes `SKILL.md`
from [TEMPLATE.md](TEMPLATE.md), trials it on a real case, then installs it on your machine.

The `description` line always sits in the agent's context; the body is only read when
the job matches the description. The description decides whether the skill gets invoked; the body decides whether the work is done right.

## When to use

- You just finished a multi-step job and said "turn this into a skill".
- You're pasting the same guidance to the agent a second time.
- You want to fix an existing skill because it fires at the wrong time or gets a step wrong.

---

## Step 0. Should this be a skill

Ask before writing a line. Pick one of four:

| Situation | Do this |
|---|---|
| One-off work, however large | **No skill.** Write one prompt or one brief file |
| One rule, one fact ("this repo uses pnpm") | Record in the repo's `CLAUDE.md` / `AGENTS.md`, or a Cursor rule |
| An error a machine can block (leaked keys, straight-to-`main` commits) | **Build a hook, script, or check**, not a skill. A skill may call that script |
| Multi-step work, repeated **2+ times**, still needing agent judgment | **Make a skill** |

- An existing skill already covers over half of this? Check all four places skills can live: `~/.claude/skills`, the repo's `.claude/skills`, `~/.cursor/skills`, `.cursor/skills`. If yes, fix that skill — don't birth a second one.
- Can't name 2 real occurrences (dates, inputs, where it went wrong)? Write it down, wait for the second time.

## Step 1. Ask five questions

If the work just happened in this session, the agent pulls answers from the chat history
first (commands run, step order, where you had to fix), then asks only what's missing.

1. **What job?** One sentence, what goes in, what comes out.
2. **When to invoke?** What do you usually say when you need it. At least 3 phrases in English.
   And which phrases **sound similar but are not** this job.
3. **What steps?** In the order you did them by hand. Which step goes wrong most.
4. **What must it never do?** Things the agent must never do alone (delete, send, push,
   spend money, edit out-of-scope files).
5. **What does done look like?** One visible or measurable thing: which file exists, which command is green,
   which number is hit.

Anything still unclear gets another question — don't guess then write. When no asking back is possible (one-shot run, nobody answering), mark each spot an **assumption**, and don't install the skill until you confirm those assumptions.

## Step 2. Write SKILL.md from the template

Copy [TEMPLATE.md](TEMPLATE.md), fill in from the five answers. Writing rules:

- **`name`**: lowercase, digits, hyphens (`kebab-case`), matching the folder name, English. Do not add a prefix; keep `market-research` for the shared research workflow.
- **`description`**: what it does (one sentence) · when to use (phrases you actually say) ·
  when not to use. Say **when to use**, don't summarize all steps: the agent reads
  the description then follows the description while skipping the body. Agents invoke skills **less**
  than needed, so list keywords generously. Limit: Claude Code cuts at 1,536 characters; the check command below prints the length too.
- **YAML must parse.** No colon-followed-by-space (`: `) inside `description`. This repo's 0.0.7 broke on exactly that bug: one skill's
  description contained `: ` so YAML wouldn't read it. Check with:
  ```bash
  python3 -c "import yaml,sys; d=yaml.safe_load(open(sys.argv[1]).read().split('---')[1]); print(d['name'], len(d['description']))" SKILL.md
  ```
- **Lean.** Body under 150 lines. Long details (price tables, API references, examples)
  split into a sibling file, e.g. `reference.md`, with a clear note on when to open it.
- **Tightness follows risk.** Touching money, secrets, production, outbound sends: write exact commands
  and stop-to-ask-you points. Judgment work: write goals and constraints.
- **No secrets, tokens, or personal machine paths** in skills. Skills get
  reshared often, and a key in a shared file is a leaked key (see the `secrets`
  skill in this same set). Where "which repo, which folder" is needed, write "the open repo" or
  a relative path, never `/Users/…`.

## Step 3. Trial on a real case

Take one time you did this job by hand, with a known-correct result.

1. Open a **fresh agent session** (or a subagent), hand it only the `SKILL.md` and that
   case's input. No answer key, no extra explanation.
2. Compare against your manual run: which steps are missing, where it's wrong, where the agent had to ask back.
3. Fix `SKILL.md`, rerun until that case passes.

Writers always find their skill clear, because the context lives in their head. This very skill, on its
first trial run by a fresh agent (09/28/2026), exposed 5 gaps: dedupe checked
only one folder, no way to measure description length, and three more. All 5 fixed.

## Step 4. Countable eval and feedback log

Fill the template's `Eval` section: **3 to 5 metrics**, each with a measurement and a target.
"'File contains X' is not a measurement. At least one metric measures the **outcome for
you** (did the job come out right), not just the process. Example:

| Metric | How to measure | Target |
|---|---|---|
| Invoked at the right time | 5 should-invoke + 5 sound-alike-but-shouldn't phrases, count correctly handled | ≥ 9/10 |
| Places you must fix by hand | count per run | trending down to 0 |
| Result meets "done when" | check exactly question 5's condition | every time |

The `Feedback log` section: a table of `date · what happened · what changed`, newest on top. Every
time you correct the agent on the skill's job, add a row and fix that exact section.

## Step 5. Install

**Claude Code.** Personal skill, used in every project:
```bash
mkdir -p ~/.claude/skills/<skill-name>
cp SKILL.md ~/.claude/skills/<skill-name>/SKILL.md
```
For one repo only (commit into the repo so collaborators get it too): place at
`.claude/skills/<skill-name>/SKILL.md` in that repo. Invoke with `/<skill-name>`, or
let the agent invoke itself when the job matches `description`. Claude Code usually picks up new skills
right in session; if not seen, open a new session.

**Cursor.** Same `SKILL.md` format. Cursor reads `~/.cursor/skills/` (all projects)
and `.cursor/skills/` (in-repo), and also reads `~/.claude/skills/`, so a skill already
installed for Claude Code usually works as-is (per Cursor docs, checked 09/28/2026).
Invoke with `/<skill-name>` in Agent chat. Short always-on rules (not processes)
belong in a Cursor rule `.cursor/rules/*.mdc`, not a skill.

Verify it landed: open a new session, say one sentence from the Step-4 "should invoke" list.

---

## Don't

- No skills for one-off work, or for errors a script can block.
- No writing a skill before the five questions are answered.
- No calling it done before trialing on a real case in a fresh session.
- No two skills holding one job. On keyword overlap, write "Don't use when" in both.

## This skill must improve itself

1. **Eval after every run.** Did the newly created skill pass the trial case, how many
   places did you fix by hand. Anything worth fixing, propose updating straight into this file or TEMPLATE.md.
2. **Look things up occasionally to update.** Install paths, `description` length limits,
   how Cursor reads skills change with versions. Any number a few months old gets
   rechecked against the Claude Code and Cursor originals before trusting.
3. **With a stronger model, rerun the trial case.** Drop any line the new model no longer needs.
4. **When unsure, ask a human.** Ask in the developer community, or ask Son Piaz.
