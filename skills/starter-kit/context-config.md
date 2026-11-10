# Context config: on and off per repo

Open this at step 4 of `/starter-kit`. The facts below were checked against the Claude Code docs
on 2026-10-17. Once they are a few months old, check them at the source before relying on them.

## What every turn carries

| Item | In context | Source |
|---|---|---|
| MCP tools | Names only by default: schemas load when called (tool search). `ENABLE_TOOL_SEARCH=auto` loads them upfront when they fit in 10% of the window | code.claude.com/docs/en/context-window |
| MCP server instructions | In full | same |
| Skills | Name + description. The body loads when invoked | code.claude.com/docs/en/skills |
| Skill with `disable-model-invocation: true` | Nothing until `/name` is typed | same |
| Root and parent-directory CLAUDE.md | In full, and reloaded after `/compact` | code.claude.com/docs/en/memory |
| `@path` imports in CLAUDE.md | In full, loaded at launch. They save nothing | same |
| CLAUDE.md in a subdirectory | Only when Claude reads files in that directory | same |

## The model: off globally, on per repo

Lean defaults in `~/.claude`; a repo that needs more turns it on in `.claude/settings.local.json`
(personal, never committed). Precedence, lowest to highest: user, project, local, flag, managed.

### Plugins
- Global: `"enabledPlugins": {"<plugin>@<marketplace>": false}` in `~/.claude/settings.json`.
- On for a repo: the same key with `true` in `.claude/settings.local.json`.
- Source: code.claude.com/docs/en/plugins/loading

### MCP servers in user scope
- No settings key turns off one user-scope server for one repo. So rarely used servers do not
  live in user scope: their entries are in `~/.claude/mcp-catalog.json`, the owner's own file (not a
  Claude Code one): one object per server, copied from `mcpServers.<name>` in `~/.claude.json`,
  which is the JSON `claude mcp add-json` takes.
- On for a repo: `claude mcp add-json --scope local <name> '<json from the catalog>'`.
- Off for a while in one repo: the owner runs `/mcp` and turns the server off. Do not edit
  `disabledMcpServers` in `~/.claude.json` by hand (its shape is not documented).
- Never use `claude mcp remove` to "turn off": it deletes the entry.
- Source: code.claude.com/docs/en/mcp

### claude.ai connectors (shown as `claude.ai <Name>` in `/mcp`)
- `"disableClaudeAiConnectors": true` turns them off everywhere and a repo cannot turn them back
  on. Do not use it while a connector is still needed for coding.
- Off for a repo: the owner turns each one off in `/mcp`. The starter kit can only list them.
- One session: `ENABLE_CLAUDEAI_MCP_SERVERS=false claude`.
- A claude.ai account shared with other people: never disconnect a connector or delete a synced
  skill on claude.ai, since that removes it for everyone. Turn connectors off in `/mcp`, and
  synced skills off with `skillOverrides` in `~/.claude/settings.json` (next section).

### Personal and claude.ai-synced skills
- `"skillOverrides": {"<skill>": "<value>"}`, value `on`, `name-only`, `user-invocable-only` (only
  `/name` invokes it) or `off` (nothing invokes it). Plugin skills are not affected.
- Personal skills (`~/.claude/skills`) are keyed by name. Skills synced from claude.ai are keyed
  `anthropic-skills:<name>`.
- Global: rarely used skills at `user-invocable-only`, unrelated ones at `off`, in
  `~/.claude/settings.json`. Observed 2026-10-17: a user-scope override applies to both kinds
  (`/skills` labels them `user-only` or shows them off).
- On for a repo: `"on"` in `.claude/settings.local.json`.
- Observed 2026-10-17: turning skills off in the `/skills` menu wrote `"off"` entries to the open
  repo's `.claude/settings.local.json`; `~/.claude/settings.json` was unchanged. By precedence,
  those entries win over the global value in that repo. Make global choices in
  `~/.claude/settings.json`, and clear menu-made entries from a repo once they are global.
- A skill you only ever invoke by hand: put `disable-model-invocation: true` in its frontmatter
  instead of an override.

## Global defaults (set once per machine, outside this skill)

The starter kit only makes context smaller once the global defaults are lean:
- `enabledPlugins` and `skillOverrides`: the guide's `global/settings-defaults.json`, merged by
  `install.py --settings`; `install.py --check` reports drift. Change them there, not by hand.
- User-scope MCP holds only servers most repos use. The rest are in `~/.claude/mcp-catalog.json`,
  written per machine (see the guide's README, "New machine").

## What to turn on

| Sign in the repo | Turn on |
|---|---|
| A hosting platform's config file (`vercel.json`, `netlify.toml`...) | that platform's plugin |
| Reverse engineering third-party binaries, APKs or bundles | the reverse-engineering MCP server |
| A website with analytics or page-speed work | the analytics and page-quality skills |
| Unclear | Nothing. Ask the owner |

## Measure

Settings apply from the next session. The owner runs `/context` in a new session to see what
fills the window, and `/skills` (key `t` sorts by tokens) to see the heaviest skills.
