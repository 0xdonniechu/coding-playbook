---
name: skill-name
description: <What it does, one sentence>. Use when <concrete job>, or when saying "<phrase 1>", "<phrase 2>", "<english phrase>". Don't use when <sound-alike-but-different job, and what to use instead>.
---
<!--
One-page SKILL.md template. Copy to ~/.claude/skills/<skill-name>/SKILL.md then fill in.
Delete all HTML comment blocks when done. Keep the body under 150 lines.

name        lowercase, digits, hyphens; matches the folder name; English.
description says WHEN to use, doesn't summarize the steps. List generously the phrases you
            actually say, in English. No ": " (colon + space)
            in the sentence — YAML won't parse it. Check with python3 + yaml.safe_load.
-->

# /skill-name

<!-- Two sentences: what this skill does, what goes in, what comes out. -->

## When to use

<!-- 2 to 4 real situations. One situation per line. -->
-

## Don't use when

<!-- Sound-alike phrases that are not this job. Note what to use instead. -->
-

## Read first

<!-- What the agent must read before working, in order: README, spec, config files.
     For files, point at the file only — don't copy content in here. For non-files
     (a few old posts, a sample snippet), write "ask you to paste into chat". Delete this section if none. -->
1.

## Steps

<!-- In exactly the order you did it by hand. Each step records: what to do, and how to know it's done.
     Steps touching money, secrets, production, outbound sends: write the exact command and
     "stop, ask the user before acting". -->

### 1. <Step name>
- Do:
- Done when:

### 2. <Step name>
- Do:
- Done when:

## Don't

<!-- Things the agent must never do alone. Each line should carry a real failure story. -->
-

## Done when

<!-- One visible or measurable thing: which file exists, which command is green, which number is hit. -->
-

## Eval

<!-- 3 to 5 countable metrics. At least one measures the outcome for the user.
     "'File contains X' is not a measurement." -->

| Metric | How to measure | Target |
|---|---|---|
| Invoked at the right time | 5 should-invoke + 5 sound-alike-but-shouldn't phrases | ≥ 9/10 |
| Places the user must fix by hand | count per run | down to 0 |
| <result meets "Done when"> | <command or file to check> | <target> |

## Feedback log

<!-- Newest on top. Each time you correct the agent on the skill's job: add a row,
     and fix the related section in this file right then. -->

| Date | What happened | What changed |
|---|---|---|
| <dd/mm/yyyy> | Created skill, trialed on case <case name> | v1 |

## This skill must improve itself

1. **Eval after every run.** Grade against the Eval table; any missing step gets a proposed fix
   straight into this file plus one Feedback log row.
2. **Look things up occasionally to update.** Numbers, tool names, prices a few months old get
   rechecked against the origin before trusting.
3. **With a stronger model, rerun the trial case.** Drop lines no longer needed.
4. **When unsure, ask a human** — don't guess.
