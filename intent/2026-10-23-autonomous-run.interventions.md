# Owner interventions before the pilot: the baseline (APS-31, 2026-10-23)

Success criterion 2 of `2026-10-22-autonomous-run.md` compares the pilot with a baseline: owner interventions per
finished node at most half of it, with zero `status` and `unblock`. This is that baseline, taken from
`~/.claude/hil/log.jsonl` before any autonomous mode exists, and what it says about the design.

## Data
- Window: 2026-10-22T01:04Z to 2026-10-23T03:41Z (1.1 days), every project on this machine.
- `python scripts/hil-report.py --since 2026-10-22`: 252 entries, 14 sittings, about 613 minutes of owner time
  (estimated from bursts; no entry gave minutes). By design (decision, approval, merge, direction): 199. To reduce
  (setup, incident, unblock, status): 53. Trigger: 152 `agent-asked`, 100 `owner`.
- The classification below is the main session's reading of each entry's note (one line each). The counts are
  estimates from those notes, not measurements, and are labelled as such.

## What the design removes, and what it does not

| kind | n | removed by the candidate design | stays with the owner |
|---|---|---|---|
| merge | 26 | about 20: auto-merge on green (decision 1) | tags, releases, deploys, force pushes, history rewrites |
| approval | 40 | about 25 are "continue", "go ahead in the stated order", "plan accepted": an approved plan already authorises its steps | deleting user data, production deploys, new wording users read |
| status | 22 | about 12 are "done?", "what remains?", "anything uncommitted?": the morning report, and an end-of-task summary in interactive sessions | about 6 were about the machine (RAM, crashes): infrastructure, not the loop |
| unblock | 7 | 4 followed a crash or a disconnect with a stale `HANDOFF.md`; 2 were "continue" while a job was still running (no visible progress): the graph as the only state, leases, and progress the owner can see | none expected |
| setup | 19 | none removed; all can be batched (one owner queue per morning, with the exact commands) | DNS records, sign-ins, tokens, sudo, account creation |
| incident | 5 | none by fewer questions; they need gates or practice (a token shown in screenshots; every session dropped at once; a deploy loop across two hosting orgs) | the owner noticed each first |
| decision | 70 | about 10 were extra review rounds or a redesign after a second FAIL: the design parks the node and asks in the morning report while other nodes run; about 5 were research steering a plan could hold | about 50 product or method decisions (prices, legal wording, scope, measurement design) |
| direction | 63 | none: the owner's own steering | all |

Estimate: about 75–80 of 252 (about 30 %) go away with the candidate design, and about 20 more move into one
batched sitting. Criterion 2 needs half per finished node, so the design alone is not enough on today's mix; the
pilot's own baseline period, measured the same way on the pilot project, decides.

## Gaps the data shows (not yet in the design)
1. **Sessions die with the machine.** Memory pressure from parallel jobs killed every session at once (2026-10-22).
   Per-job memory caps are now a working practice; the driver must also restart from the graph without the owner.
2. **Messages land in the wrong session.** With many sessions open, an owner instruction meant for another
   project was acted on here (2026-10-23). One driver per project, and the agent names the conflict before acting.
3. **"Done?" in interactive sessions.** Owners ask whether work is committed, pushed, merged and ticketed. A fixed
   end-of-task summary answers it before it is asked (proposed as a working practice in `global/CLAUDE.md`).
4. **Owner-only steps arrive one by one.** DNS, tokens and accounts came in separate sittings across projects. One
   queue, shown in the morning report with exact commands, turns them into one sitting.
5. **Review loops on unbounded problems.** APS-32 and APS-34 each needed owner decisions after reviews kept
   finding new command forms: guessing writes from command text does not converge. The fix both times was a state
   comparison (git before and after). Lesson for node design: a gate that reads text should be backed by one that
   compares state.

## How to re-measure
Run the same report on the pilot project for its baseline period and for the autonomous period, and count per
finished node: `python scripts/hil-report.py --project <pilot> --since <date>`. Read the notes of `status`,
`unblock` and `approval` entries the same way as above.
