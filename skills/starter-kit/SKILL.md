---
name: starter-kit
description: Sets up a new repo so coding-agent sessions keep a small context. Writes CLAUDE.md from the template, sets the git identity, keeps only the plugins, MCP servers and skills the repo needs, gitignores HANDOFF.md for /handoff, and creates the tracker project. Invoked only as /starter-kit, when a repo starts or when an older repo joins this way of working.
disable-model-invocation: true
---

# /starter-kit

Run once per repo: a new one, or an older one without a `CLAUDE.md` in the template's shape. The
input is the open repo. The output is a short `CLAUDE.md`, a `.claude/settings.local.json` that
turns on only what the repo needs, `HANDOFF.md` gitignored, the right git identity and, if the
owner wants one, a tracker project.

This skill costs no context: `disable-model-invocation` keeps it out of the session until it is
typed. Day-to-day work uses `/handoff`.

## Read first

1. `~/.claude/CLAUDE.md`: the GitHub account rules, the issue tracker, HARD/MEDIUM/EASY rating.
   Apply them; do not copy them into the repo.
2. [project-CLAUDE.md](project-CLAUDE.md): the template for step 3. This is the only copy; edit it here.
3. [context-config.md](context-config.md): open it at step 4.

## Steps

### 1. Survey the repo, read only
- Do: `git rev-parse --is-inside-work-tree`, `git remote -v`, `git config user.email`. List the
  manifests at the root (`package.json`, `Cargo.toml`, `pyproject.toml`, `go.mod`, `*.csproj`...)
  and read only their scripts and package names. Check for `CLAUDE.md`, `AGENTS.md`, `.claude/`,
  `.gitignore`, `.mcp.json`. Skim only the entry points (file names, main exports), enough to say
  what owns what; do not read all the source.
  When `git config user.email` returns the global value (none set for the repo), say so: the
  first commit would carry that address.
- Done when: a short table shows the stack, the test/lint/build commands found, the files that
  exist and what is missing.

### 2. Ask once, only what is missing
- Do: one message with only the questions step 1 could not answer:
  1. What does the app do, for whom, and what does a bug cost (lost data, wrong numbers, downtime)?
  2. Which areas are HARD (user data, security, money, cannot be undone), and which are MEDIUM
     (propose some from the stack; the owner corrects them)?
  3. Which checks only the owner can run (real hardware, accounts, eyes)?
  4. Which account owns the repo (per `~/.claude/CLAUDE.md`), what is the remote, public or private?
  5. Which plugins, MCP servers or skills beyond the defaults does it need (see "What to turn
     on" in `context-config.md`)?
  6. Create a tracker project? Name and identifier?
- Done when: there is enough for steps 3 to 7. Any question left unanswered becomes an
  assumption in the report.

### 3. CLAUDE.md
- Do: fill `project-CLAUDE.md`. No `CLAUDE.md` yet: create it. One exists: **do not overwrite
  it**; show a diff of the missing sections and wait for approval. An `AGENTS.md` keeps the
  shared rules: point to it instead of copying. Detail that only one module needs goes in
  `docs/<module>.md`, listed under "Read when", never as an `@import`.
  Read a script before running it, then run each Verify command once with filtered output
  (`| tail -40`). A command that fails because the repo is still empty gets
  "not run: <reason>"; keep the command. Write "(0 warnings)" only when the linter counts
  warnings. Delete empty sections (such as "Read when" with no module docs yet).
- Done when: `CLAUDE.md` is under 60 lines, has no `<placeholder>` left, and every Verify
  command has run or carries a "not run" reason.

### 4. Keep only what the repo needs
- Do: follow `context-config.md`. Read, never edit, `enabledPlugins` and `skillOverrides` in
  `~/.claude/settings.json`, and `claude mcp list` for the user-scope servers. Read the repo's own
  `.claude/settings*.json` too: an entry there wins over the global one, and a `skillOverrides`
  entry the `/skills` menu wrote that now matches the global value can be dropped. Make two lists:
  what the repo needs that is off, and what is on that the repo does not need. When the global
  defaults are not lean yet ("Global defaults" in `context-config.md`), say so in the report.
- Merge into `.claude/settings.local.json` (read the old file first, keep every key):
  `enabledPlugins` `true`/`false` and `skillOverrides` `"on"`/`"user-invocable-only"` from the
  two lists. An MCP server the repo needs: take its entry from `~/.claude/mcp-catalog.json` and
  give the command `claude mcp add-json --scope local ...`. User-scope servers and claude.ai
  connectors (tools prefixed `mcp__claude_ai_` in this session) the repo does not need: list
  them for the owner to turn off in `/mcp`.
- Nothing to write: create no file.
- Stop and ask the owner before writing the settings file or running `claude mcp add-json`.
  Show the diff.
- Done when: the settings file, if any, is valid JSON
  (`node -e "JSON.parse(require('fs').readFileSync('.claude/settings.local.json','utf8'))"`)
  and the owner approved it.

### 5. HANDOFF.md and .gitignore
- Do: make sure the repo's `.gitignore` (create it if needed) has both `HANDOFF.md` and
  `.claude/settings.local.json`, even when this machine already ignores them in its global git
  config: a clone elsewhere does not have that config. Do not create an empty `HANDOFF.md`;
  `/handoff` creates it when needed.
- Done when: `git check-ignore -v HANDOFF.md .claude/settings.local.json` prints both lines, and
  both come from the repo's `.gitignore`.

### 6. Git identity
- Do: per the account rules in `~/.claude/CLAUDE.md`, set `git config user.name` and
  `git config user.email` for this repo only (never `--global`), with the remote URL form and
  time zone those rules name. Never `gh auth switch`. The owner gave a remote and the repo has
  none: `git remote add origin <url>` (local only, no push).
- Done when: `git config user.name`, `git config user.email` and `git remote -v` are printed and
  match the rules.

### 7. Tracker project (only when the owner said yes in step 2)
- Do: use the tracker named in `~/.claude/CLAUDE.md` (and its skill, if installed) to create the
  project and bind this folder. Put the identifier and language in `CLAUDE.md`'s Rules. No
  tracker: delete that line.
- Stop and ask the owner before creating anything in the tracker.
- Done when: the project exists and the identifier in `CLAUDE.md` matches it.

### 8. Report
- Do: a table, one row per step: done / skipped (reason) / not run (reason). The files created
  or changed. The assumptions. Then three lines for the owner:
  ```
  Start a new session for the settings to apply; run /context and /skills to see the fixed part.
  Turn off in /mcp: <connectors and servers the repo does not need>.
  Commit CLAUDE.md and .gitignore when you want to (nothing is committed).
  ```

## Never

- Overwrite an existing `CLAUDE.md`, `AGENTS.md`, settings file or `.gitignore`. Merge, and show the diff.
- Edit `~/.claude/settings.json`, `~/.claude.json` or `~/.claude/CLAUDE.md` by hand while setting
  up a repo (`claude mcp add-json --scope local` in step 4 is the one approved write). The global defaults change only when the owner asks for that on its own.
- Commit, push, create a remote repo or a tracker project without the owner's yes.
- Turn on a plugin, server or skill "just in case". When unsure, leave it off and ask.
- Copy spec text or global rules into the repo's `CLAUDE.md`. Point to the file.
- Write secrets, tokens or machine paths into a file that will be committed.

## Done when

- `CLAUDE.md` is under 60 lines with Verify, HARD/MEDIUM/EASY, Rules and Session state.
- `git check-ignore` confirms `HANDOFF.md` and `.claude/settings.local.json` are ignored by the repo.
- `git config user.email` matches the account rules.
- In a new session, `/context` no longer shows plugins, servers or skills the repo does not use.

## Eval

| Measure | How | Target |
|---|---|---|
| Lean fixed context | `/context` in a new session: MCP tools + skills tokens, before vs after | lower; record the numbers in the log |
| Needless questions | questions in step 2 that step 1 had already answered | 0 |
| Unintended overwrites | `git diff` on files that existed before the run | 0 unapproved lines |
| First commit on the right account | `git log -1 --format='%an <%ae>'` | matches the rules, every time |
| Hand fixes by the owner | count per run | down to 0 |

## Log

| Date | What happened | What changed |
|---|---|---|
| 2026-10-17 | Global defaults on the owner's machine (Vercel plugins off, one reverse-engineering MCP server moved to the catalog, 31 skill overrides, 14 of them `off`). `/context` in a new session: skills 45 → 25 and 8.4k → 3.8k tokens; MCP tools 38, 640 tokens. Overrides apply to personal and claude.ai-synced skills; the `/skills` menu wrote its toggles into one repo's local settings | `context-config.md`: overrides verified, synced-skill keys, menu scope, shared-account rule |
| 2026-10-17 | Trial in a fresh agent on a scratch Node repo: step 4 could only turn things on, so nothing got smaller while the global defaults were not lean; MEDIUM never asked; `settings.local.json` ignored only by global git config; the global email would have reached the first commit | Step 4 makes "needs" and "does not need" lists; MEDIUM question; the repo `.gitignore` always gets both lines; step 1 flags the global email |
| 2026-10-17 | Created from eight ways of keeping context small | v1 |

## Keeping this skill good

1. **Score each run** against the Eval table. A step the owner had to fix by hand: fix this file
   and add a log row.
2. **Look things up now and then.** `context-config.md` carries its check date. Settings keys and
   the ways to turn off servers and connectors change between Claude Code versions; after a few
   months, check again at code.claude.com/docs.
3. **Rerun the trial on a stronger model.** Drop the lines it no longer needs.
4. **When unsure, ask the owner.** Do not guess.
