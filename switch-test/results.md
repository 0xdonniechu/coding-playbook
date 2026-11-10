# Switch test results

Matches are the main session's proposal until the owner confirms them; "owner" columns stay empty until then.
`Kn` is issue n of the case's `known.md`; `Rn` is issue n of the run's `report.md`. A partial match (the run found
part of the known issue, or the same defect through a different example) counts as caught and is marked (p).

## Baseline, 2026-11-07 (reviews at effort `high`)

Conditions: headless runs in fresh clones; no `bd` binary on the machine (the original aps34 review had one, which
K1 and K3 there needed to confirm); Windows tests not runnable for asp18 (all runs say "not run"). Settings changed
during the first two runs (the owner ran `/model` and `/effort`, the main session wrote the owner log); no run touched
`~/.claude` itself. Two Opus runs were first marked VOID for reading their own large tool output from their own
session folder; the void check was fixed and both rechecked clean (`run.json` `void_note`).

### Summary

| model | known caught | MAJOR-or-worse caught | new issues to judge | cost | minutes |
|---|---|---|---|---|---|
| `claude-opus-5-5` | 14/19 | 4/6 | 9 | $2.66 | 6.4 |
| `claude-fable-5-1` | 13/19 | 5/6 | 7 | $8.48 | 16.7 |

### aps32-guard (known: K1 MAJOR, K2-K7 MINOR)

| known | Opus 5.5 | Fable 5.1 |
|---|---|---|
| K1 MAJOR joined short flags (`sed -Ei`, `bash -lc`, `gh api -XPOST`) | R2 (+R1 `bash -lc`) | R2 (+R4 `bash -lc`, `-XPOST`) |
| K2 glued operators `\|\|(` | missed | missed |
| K3 `<<WORD` without terminator drops later lines | missed | missed |
| K4 `checkout -b --`, wrappers with option values, `git.exe` | R1 (p, wrappers only) | R4 (p, wrappers only) |
| K5 uncaught exceptions fail open; missing python3 | R3 (MAJOR) | R3 (MAJOR) |
| K6 false positives on reads | R6 | R5 |
| K7 docs drift (hooks path, README, Co-Authored-By line) | R9 (p, Co-Authored-By only) | missed |
| **caught** | **5/7**, MAJOR 1/1 | **4/7**, MAJOR 1/1 |
| new, to judge | R1 `then`/`do` keywords (MAJOR; the later fresh hard review found the same and it was fixed), R4 PowerShell coverage (MAJOR), R5 `find -delete` and first-argument-only checks, R7 check.py matcher position, R8 `git stash` | R1 `then`/`do` keywords (MAJOR, same as Opus R1), R6 agent bodies do not mention the hook |
| cost, minutes | $0.52, 1.9 | $2.05, 5.9 |

### aps34-boundary (known: K1-K3 MAJOR, K4-K7 MINOR, K8 NIT)

| known | Opus 5.5 | Fable 5.1 |
|---|---|---|
| K1 MAJOR `rest[:-1]` drops `--status=closed` | missed | R2 |
| K2 MAJOR `git push origin HEAD` on main | R1 | R1 |
| K3 MAJOR `bd show` failure not checked | missed | missed |
| K4 protected paths through `rm`/`mv`/`git rm` | R4 | R10 (as NIT) |
| K5 publishing/tag/secret gaps (tag by name, `gh api` refs, graphql, `.env`) | R2 (MAJOR), R5, R6 | R3 (MAJOR), R4, R6, R9 |
| K6 bd fields beyond status/evidence/cost/claim | R7 | missed |
| K7 `cd` in a subshell leaks | missed | missed |
| K8 NIT false blocks, DO_NOT_TRACK regex | R7, R8 (p) | R6 (p, `.pem`) |
| **caught** | **5/8**, MAJOR 1/3 | **5/8**, MAJOR 2/3 |
| new, to judge | R3 close without an id (MAJOR, unconfirmed), R5 Read tool on keys and signing, R6 twine/docker, R9 symlinked `~/.claude` | R5 signing flags, R7 `LICENCE` spelling and CLAUDE.md unprotected, R8 `bd -C` unverified, `--remove-label` |
| cost, minutes | $1.28, 3.3 | $3.42, 7.2 |

### asp18-overview (known: K1-K2 MAJOR, K3-K4 MINOR)

| known | Opus 5.5 | Fable 5.1 |
|---|---|---|
| K1 MAJOR Scan again does nothing with C: unticked | R1 | R1 |
| K2 MAJOR no test for that path | R3 (as MINOR) | R5 (as MINOR) |
| K3 spec line contradicts the departure; note inserted mid-note | R2 | R2 (p, as MAJOR, contradiction only) |
| K4 test gaps (focus ring, WrapPanels, Enter, busy rules) | R3 | R5 |
| **caught** | **4/4**, MAJOR 2/2 (K2 at lower severity) | **4/4**, MAJOR 2/2 (K2 at lower severity) |
| new, to judge | none | R3 `CenterLines` centring not in the contract, R4 CheckBox style alignment |
| cost, minutes | $0.86, 1.3 | $3.02, 3.7 |

### Owner verdicts

| run | matches confirmed | new real | false alarm | date |
|---|---|---|---|---|
| Opus 5.5 | all, as proposed above | not judged yet | not judged yet | 2026-11-07 |
| Fable 5.1 | all, as proposed above | not judged yet | not judged yet | 2026-11-07 |

The owner confirmed the matches ("Verified", 2026-11-07). The new issues are not yet sorted into real and false
alarm; the known-issue counts, which decide (a), do not depend on them.

## Replay baseline (question b), 2026-11-07

`replay --model claude-opus-5-5 --effort high` (the main session's effort, set by the owner that day), then the fixed
reviewer `claude-fable-5-1` at `high` on the replay's commit. One round, no fixes. Before committing, the replay ran
the HARD loop itself: two `hard-reviewer` rounds (Fable 5.1 subagent) and fixes. Its commit is that loop's output, and
the review prompt is the kit's own, so the original column below is context, not a like-for-like baseline; a
candidate's replay is compared with the Opus 5.5 column.

| | original author (1f8064f, 2026-10-23) | Opus 5.5 replay (afb1879) |
|---|---|---|
| reviewer's verdict | FAIL: 2 MAJOR, 5 MINOR (`known.md`) | FAIL: 1 MAJOR, 5 MINOR |
| MAJOR | K1 token paths not denied; K2 false positives in every session | R1 tracing the `gh` wrapper (`bash -x`) prints the token (new) |
| known issues repeated | | K1 (p): a gh alias still prints the token (R1's second example, `gh alias set e '!env' && gh e`; K1's third bullet); K2 (p): a commit message or grep naming `gh auth token`/`oauth_token` is still denied (R4, as MINOR); none of K3-K7. K1 (p) added 2026-11-08 from round-2 review; confirmed by the owner ("Verified", 2026-11-08) |
| size | 4 files, +160/-3 | 6 files, +446/-16 |
| cost, minutes | | author $8.55, 25.2; review $5.49, 14.1 |

The first review of the replay was void: it read the guard installed on this machine (the later, fixed version) to
compare (`runs/…/aps37-token-guard-review-void1`, $8.42). The review task now says not to, and the void check counts
reads of a case's answer keys (the live source repo, `void_extra` in `case.json`). The replay author itself listed
`~/.claude/hooks/` but never read the installed guard; the owner-token guard was live during the replay, so a blocked
command showed it the installed deny message (the same for every candidate, and needed for the owner's safety). Its
Glob of `~/.claude/hooks` returned names only; its grep of the `ambysto-memory` index found no APS-37 lesson (none
exists there today).

## Release-day dry run, 2026-11-07 (`claude-opus-5-5` standing in)

- Step 1: not needed for a pinned model (`check.py` allows the agents' pins).
- Step 2: `probe --model claude-opus-5-5`: agent-guard's message in the tool result, the checkout blocked.
- Steps 3-4: the baseline runs above are these commands with the stand-in.
- Step 5: matches proposed and confirmed by the owner, for the reviews ("Verified", 2026-11-07) and the replay row
  ("Verified. Confirmed", 2026-11-08).
- Steps 6-8: not run (no candidate yet).
