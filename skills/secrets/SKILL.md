---
name: secrets
description: Keep API keys and passwords safe when delegating work to an AI agent, and push code to GitHub without leaking anything. Use when touching API keys, secrets, .env, 1Password, environment variables, when connecting a new API or MCP, before a commit or push, when setting up CI, when letting a second person or another agent into the repo, and when hitting "merged but the page didn't change". Distilled from real failures; every rule comes with a story of what happened.
---

# /secrets

Delegate work to agents without handing over the keys, and push code without leaking anything.

Every rule below comes from a real failure during system building,
not from a book. Wherever there is a number, it is a measured number.

---

## When to use

Read this file before doing any of the following:

- Touch API keys, secrets, `.env`, environment variables
- Connect a new API or MCP into the agent
- Commit or push, especially a project's first one
- Let a second person, or another agent, into your repo
- Set up CI, or decide which rules need automated checks
- Hit the phrase "merged but the page didn't change"

---

## 1. Two kinds of keys, don't confuse them

A **public key** is like a bank account number. Anyone may know it; they can only
transfer money in.

A **private key**, also called a secret key, is like an Internet Banking password. Leaked means lost.

The trouble is many services call both an "API key". One-line rule:

> Any key starting with `sk_`, `sb_secret_`, `secret`, `service_role`, or one the
> service calls a **secret**, **never leaves your machine**.

---

## 2. Where to store them, three tiers

| Tier | Tool | Use when |
|---|---|---|
| Password manager | 1Password, Bitwarden, Doppler | Source of truth for the whole team. The agent must ask permission on every fetch |
| The platform's own secrets | Vercel env, GitHub Actions secrets, Supabase Vault, Cloudflare Workers secrets | Key used by a single service only |
| Dedicated key store | AWS Secrets Manager, Google Secret Manager, HashiCorp Vault | Many environments, need a log of who fetched which key when |

On your machine: macOS Keychain, `.env` in `.gitignore` with no exceptions, and
`.env.example` containing **variable names only, never values**.

### Four places people actually lose keys

None of them are in the table above:

```
export API_KEY=...   in .zshrc
pasting a key into Slack or Zalo to yourself
keeping it in Notion, Google Keep, Apple Notes
the clipboard — just copied and then forgotten
```

### The clipboard story, measured not threatened

Three measured facts on macOS:

1. **The clipboard is the only sensitive surface the OS doesn't guard.** Camera,
   microphone, screen recording, and keyboard all trigger permission dialogs. The clipboard
   doesn't. A running machine has around 475 processes, and every process can read
   the clipboard, silently, leaving no trace.
2. **"On my machine" no longer holds.** Universal Clipboard pushes it over iCloud to
   your iPhone and iPad. Copy on the Mac, paste on the phone. Three devices, not
   one.
3. **It stays there until overwritten.** The clipboard has no expiry.

One command to clear it, run right after you're done with a key:

```bash
pbcopy < /dev/null
```

**To say it right — and this is the part more worth learning than the command:** you can't prove
*someone is watching*. You can only prove *everyone can read it*. The correct statement is: clear
the clipboard not because someone is watching, but because a live credential is sitting on
the only surface with no access control, already synced to two other devices,
and will sit there indefinitely.

Telling **measured risk** apart from **vague fear** is a skill, not a detail.

---

## 3. Four rules when delegating to agents

Copy these four lines into your project's `AGENTS.md`.

### Rule 1. Give the variable name, not the value

```
WRONG     Call the Linear API for me, the key is lin_api_a1b2c3...
RIGHT     The key lives in LINEAR_API_KEY. Read it from process.env, don't print it.
```

Pasting a key string into the chat means it lives forever in conversation history and
in third-party logs. You can't delete it. A variable name is harmless to any reader.

### Rule 2. Don't let it print the key on screen

Agents habitually do these three things to self-check:

```
WRONG     console.log('key:', process.env.API_KEY)
        echo $API_KEY
        curl -v ...                    the -v flag prints the Authorization header too

RIGHT     echo ${API_KEY:0:8}...                     first eight characters only
        [ -n "$API_KEY" ] && echo "key present"     presence check only
        curl -s ... -o /dev/null -w "%{http_code}"  status code only
```

Your terminal may be screen-shared or recorded. Platform
and CI logs keep everything too.

### Rule 3. Scan before pushing, even private repos

```bash
git diff --cached | grep -inE "sk-[a-zA-Z0-9]{20}|sb_secret_[A-Za-z0-9_-]{10}|AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{36}|xox[baprs]-|-----BEGIN"
```

Any hit means stop. Private today, tomorrow you change your mind and open-source it, and everything
already in history leaks.

### Rule 4. Leaked means rotate the key, don't go deleting commits

**Git keeps every blob forever.** These three are verified, not guessed:

- Deleting a file in a later commit does **not** remove it from history
- Force-pushing after `git filter-repo` does **not** remove it from already-cloned copies
- Switching the repo to private does **not** remove it, because forks share the object store

The only thing that still works is going to that service, revoking the old key, creating a new one.

---

## 4. Letting the agent reach keys without holding them

This is the model to aim for, not `.env`.

```
KEEP IN .env                      KEEP IN 1PASSWORD
agent needs one key               agent needs one key
   ↓                                   ↓
it opens the .env file itself     it only has the storage name: op://...
   ↓                                   ↓
has the key, calls the API        1Password receives the request
                                       ↓
Nobody gets asked.                YOUR FINGERPRINT ON THE MACHINE   ← the difference is here
No step in between.                    ↓
No trace left.                    returns the key to exactly that command
                                   the value never appears on screen
```

The entire difference sits in exactly one box: a human pressing a finger.

One-time setup: 1Password → `Settings` → `Developer` → enable `Command-Line Interface`.
Then hand to the agent:

```
Take all the secret keys currently in my .env, push them up to 1Password,
organized into one vault per project.
Don't print any key's value on screen.
```

**The tradeoff, stated plainly:** this is slower, because every time the agent needs something you must touch
your fingerprint. A project with no sensitive data is fine on `.env`. With customer data,
money, or bank accounts, that inconvenience is worth it.

---

## 5. A key living in exactly one place is a risk nobody named

The Campus all-power database key once **existed only as an environment variable on
Vercel**. No other copy anywhere. If Vercel broke or someone rotated it by mistake, it was gone, with
no recovery from anywhere.

> The most important key must live in **at least two places**, and **one of those
> places must ask a human** before handing it out.

Audit your project now: how many places does each key live in?

---

## 6. Three things never to commit

**Security keys.** No API keys, no tokens, no `.env`.

**Real user lists.** No `.xlsx`, no `.csv` with real names and emails.
One accidental commit of a hundred-plus people can't be taken back, and if someone requests
deletion of their data, you can't comply.

**Heavy files.** Video, original images, builds. They go through a separate store, not git.

Before every commit, glance at `git status` once, and `git add <specific file>` — never
`git add -A`.

---

## 7. Working with a second person, and with another agent

### Put the rules where agents actually read

An agent only auto-loads `AGENTS.md` or `CLAUDE.md` at the **exact repo root it stands in**.
Brilliant guidance left in another repo never gets read. This
mistake happened, and it cost a session.

### Write out a "stop and ask a human" list

Technical permission for an agent doesn't mean it may decide alone. The Campus list:

1. Run any command with `--apply`, because that flag writes for real
2. Push straight to `main`
3. Touch user identity
4. Delete or edit data someone else submitted
5. Change login session keys, because changing kicks out everyone currently logged in

### Make the agent pull latest before working

```bash
git checkout main && git pull
```

The repo changes daily, and most of what changes is **working rules**, not
content. Working on an old copy means working under rules already
edited, and that error only surfaces after
pushing.

---

## 8. Documentation is not a guarantee

Writing rules into `CONTRIBUTING.md` stops nobody from erring. Only CI stops them.

Campus once had five workflows and **none ran on pull requests**. Every guarantee
lived in people's memory.

The minimum check set for a small project, running on every pull request:

```yaml
- No forbidden files, no key-like strings in the repo
- Old tests don't break
- Machine-generated files must match their source
- Every path to an outside file must point at something real
```

And each step, when red, must **print what to do**, not just print that it's wrong.

**One flaky check gate is worse than no gate**, because people learn to
ignore it. Trial it on real data before turning it on.

---

## 9. Merged doesn't mean it's on the page

A deploy platform may block by **commit author**. Vercel only builds when the
commit creator is on the team. Outside it, the deploy shows
`Deployment was blocked`, the code sits correctly on `main`, yet the page doesn't change.

It blocks `github-actions[bot]` too — blocking your own automation workflow.

Hitting "merged but the page didn't change" means **check deploy permissions before hunting
for bugs in the code**.

---

## 10. The through-line rule: silent failure is the most expensive kind

Four failures in one Campus build week, none with an error message:

| What broke | What it looked like |
|---|---|
| Vercel blocked the deploy | merged, page unchanged |
| Video uploaded to the store short, 1 MB for 19 minutes | store returned HTTP 200, script reported done |
| Forgot to re-translate content | clean commit, page unchanged by a single word |
| File blocked on wrong format | red report with no reason why |

All four **looked done**.

> Every path must have one place that reports when the thing that should have happened didn't happen.
> Without that place, silence reads as success.

Apply to everything you build: after writing, read back and compare. After uploading,
re-measure the size. After merging, check it really went up.

---

## Quick lookup

| Situation | Do this |
|---|---|
| Just copied a key | `pbcopy < /dev/null` after use |
| Agent asks for a key to call an API | Give the variable name, not the value |
| About to push for the first time | Scan per Rule 3, check `.gitignore` has `.env` |
| Accidentally pasted a key into chat | Rotate the key now. Don't delete commits, useless |
| Onboarding someone new to the repo | Write `AGENTS.md` at that repo's root |
| Merged but the page didn't change | Check deploy permissions first, don't touch code |
| Suspect a file uploaded short | Re-read the size on the store, compare with local |
| About to buy a new tool | Ask first: does it have an API |

## This skill must improve itself

Three rules for the agent reading this file, taken from exactly how Son runs skills:

1. **Eval after every run.** When done, self-grade briefly against the skill's checklist:
   which steps were missing, where the user had to fix by hand. Anything worth fixing,
   propose the user update straight into this SKILL.md file. A skill is a living
   document with a feedback loop; every run must make it slightly better.
2. **Look things up occasionally to update.** Prices, tools, and how sites organize
   data change constantly. Any number or tool name in this file a few months
   old gets rechecked against the original page before trusting.
3. **When unsure, ask a human.** Whatever is out of scope, say so plainly, and only
   the user asks in the open-source community (the program's Discord,
   members in it are a help source) or asks Son Piaz. A real person is a
   help source, not just documentation.
