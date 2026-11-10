---
status: verified # draft → planned (owner accepts) → building → verified
---
# Plan: model switch kit (APS-45)

Contract: `intent/2026-11-07-fable-switch-kit.md` (approved 2026-11-07). Rating: HARD (the switch test is on this
repo's HARD list): the main session builds, `hard-reviewer` reviews the diff.

## Cases (from recorded first-round reviews, checked against the transcripts on 2026-11-07)

Each known-findings list is the first review round's report, copied verbatim (severity and one line per issue).
The transcript paths below stay in the case file as the source, so the copy can be checked.

| id | repo | range given to the reviewer | rating | original reviewer | known |
|---|---|---|---|---|---|
| `aps32-guard` | claudecode-guide | `d5bc1dc..ea89167` | HARD | Fable 5.1, FAIL | 1 MAJOR, 6 MINOR |
| `aps34-boundary` | claudecode-guide | `bcc4708..852a39a` | HARD | Fable 5.1, FAIL | 3 MAJOR, 4 MINOR, 1 NIT |
| `asp18-overview` | ambysto-space | `266e95c..8f0356d` | MEDIUM | Opus 5.5, FAIL | 2 MAJOR, 2 MINOR |

Replay for question (b): `aps37-token-guard`, claudecode-guide, from `d33a160`; the original first commit
`1f8064f` got 2 MAJOR and 5 MINOR from Fable 5.1 in round 1.

Sources: `aps32` `~/.claude/projects/-home-dc-group-work-ambysto/d0b7e864…/subagents/agent-ae1199c….jsonl:117`;
`aps34` `…-ambysto-space/69e03d46…/subagents/agent-aa5cfb97….jsonl:185`; `asp18`
`…-ambysto-space/453d966b…/subagents/agent-a355e14d….jsonl:130`; `aps37` `…-ambysto/ecb8bd61…/subagents/agent-a1d20fac….jsonl:175`
(full ids in the case files). Line 1 of each file is the prompt the reviewer got; the case's `task.md` is that
prompt with the run-specific paths replaced by `{repo}` and `{range}`.

A known limit, written in the results: cases 1-3 were first found by Fable 5.1, so its baseline is a repeat of its
own review on the same diff (not the same run, so not a guaranteed match). That makes it a fair floor for the
"catches at least as many" rule, and Opus 5.5 on the same cases shows what a different model catches.

## Files, in order

1. `switch-test/cases/<id>/case.json` (repo, base, head, rating, original model, source transcript and line),
   `task.md` (the reviewer's prompt as above), `known.md` (verbatim known issues, numbered `K1…`). Three review cases
   plus `switch-test/replay/aps37-token-guard/` with the same files, where `task.md` is the task the main session
   was given (extracted from the parent transcript's owner messages and the intent text it pointed to; the owner
   checks it before the replay runs).
2. `scripts/switch-test.py` (standard library only):
   - `review --model <id> [--effort high] [--case <id>]`: for each case, a fresh clone of the case's repo into
     `~/.cache/switch-test/<run>/<case>/repo` (`git clone --no-local`, detached at `head`, no remote), then
     `claude -p` in that folder with `--agents` defining `switch-reviewer` from `agents/reviewer.md` (its body,
     tools and hooks; only `model` and `effort` replaced), `--agent switch-reviewer`, `--output-format stream-json
     --verbose`, `--no-session-persistence`. Prompt: `task.md` with `{repo}` and `{range}` filled in. Keeps the raw
     stream in the cache; writes `report.md` (the final message), and `run.json` (the model from the init event,
     effort, tokens, `total_cost_usd`, duration, void-check result) into `switch-test/runs/<date>-<model>/<case>/`.
   - `replay --model <id> [--effort <level>]`: a fresh clone at `d33a160`, `claude -p --model <id> --effort <level>`
     with `--settings hooks/autonomous-settings.json` (the boundary hook) and `HOME`-relative writes checked (below),
     prompt `task.md`; then a `review` of the replay's diff by `claude-fable-5-1` (a fixed reviewer, different
     from both Opus 5.5 and the candidate). Records review rounds = 1 (no fix loop in the replay), BLOCKER/MAJOR
     counts, known issues `K…` the replay repeated, cost of both runs.
   - `void-check <run dir>`: reads the raw stream; the run is void if any tool call names `switch-test/`,
     `known.md`, or `.claude/projects/` (old transcripts hold the original reports).
   - `--self-test`: parses the case files, builds the agent JSON from `agents/reviewer.md` and checks only model and
     effort differ, and runs `void-check` on two fixture streams (one clean, one that reads `known.md`).
3. `switch-test/README.md`: what the kit measures, how to run it, the blindness rules, and how matching works:
   the main session proposes which reported issue matches which `K…`, the owner confirms; an unmatched issue is
   marked by the owner as "new real" or "false alarm". The owner's verdicts go in `results.md`.
4. `switch-test/results.md`: one table per run (per case: known caught / known total, MAJOR+ caught, new real,
   false alarm, cost, tokens, effort, minutes), and the replay table. Baseline rows: Fable 5.1 and Opus 5.5 at
   `high` (the agents' effort); replay baseline Opus 5.5 at the main session's effort in `settings.json` when the
   run starts, written down with the number.
5. `switch-test/RELEASE-DAY.md`: the checklist. Write the published Fable 5.5 ID; `review` and `replay` with it;
   matching and owner verdicts; the decision table from the intent (a) and (b); then the one PR that changes
   `settings.json` (by the owner), every agent file and the "Current choice" line with the numbers.
6. `scripts/check.py`: each case folder has the three files and a valid `case.json`; no model ID in `switch-test/`
   or the script except the ones in `agents/` and `claude-fable-5-1` (so nobody pre-fills a guessed 5.5 ID).
7. `CLAUDE.md`: the Open line "The switch test runs when Fable 5.5 ships" points to `switch-test/RELEASE-DAY.md`;
   Verify lists `scripts/switch-test.py --self-test`. `global/CLAUDE.md` "Switching models" step 1 gets one
   sentence naming the kit. README: one row for `switch-test/`.
   **Changed in build (2026-11-07):** the reviewer is the headless session itself, not an `--agents` subagent: the
   body of `agents/reviewer.md` goes in with `--append-system-prompt`, its tools with `--allowedTools` and its three
   agent-guard hooks with `--settings` (the script stops if `reviewer.md` no longer names them), so `--model` and
   `--effort` act directly. A `probe` command proves the hook is live (a checkout blocked with agent-guard's message
   in the tool result), replacing the "ask the reviewer to try a checkout" step in a real case. The cache folder is
   `~/.cache/model-switch-runs/` (a name the void check does not confuse with the kit). The check in 6 also accepts
   IDs listed in `switch-test/candidates.txt`, which release day creates. The source-repo watch ignores the kit's
   own `switch-test/runs/` output.
   **Changed after review (2026-11-08):** the `~/.claude` and source-repo watch records a change in `run.json`
   (`watch_changed`) with a warning instead of stopping (Risks below said "stops"): the owner and the main session
   write there during a run. A clone fetches the case's one commit by hash (a plain clone carried the kit's branch).
   The replay may run the HARD loop with `hard-reviewer` before committing, so candidate replays compare with each
   other, not with the original's first round; `prompt_edits` in `case.json` records prompt changes. `check.py` also
   accepts a model ID recorded in a `runs/**/run.json` (taken from a real run's init event).
8. Run the baseline (Files 4), fill `results.md`, and run the release-day dry run with `claude-opus-5-5` standing in
   for the candidate. Then the intent goes to `status: verified`.

## Risks, and the check that catches each

- **The candidate sees the answers** (the kit is in this repo; old transcripts hold the reports). Clones are of the
  case's repo at an old commit, `--no-session-persistence` keeps new runs out of `.claude/projects`, and
  `void-check` voids any run whose tools touched the kit, `known.md` or old transcripts. Self-test proves the check
  fires.
- **The wrong model or effort runs** (an agent file's pin or `--model` winning over the other). `run.json` takes
  the model from the stream's init event, and `review` stops with an error when it differs from `--model`.
- **A reviewer changes a real tree or checks out** (lesson `give-reviewers-a-diff-range`). The prompt gives the
  range and says `git show`; clones are throwaway; the reviewer's agent-guard hooks come along in the agent JSON;
  `git status` and `git branch --show-current` of this repo and ambysto-space are checked before and after. If
  `--agents` does not carry `hooks`, the same agent-guard `review` hooks go in through `--settings`; the dry run
  (Proof 3) shows which, by a blocked `git checkout` the prompt asks the reviewer to try once.
- **The replay writes into the real `~/.claude`** (the APS-37 task includes `install.py` writing `settings.json`).
  The boundary hook protects `~/.claude` settings, hooks and agents and locks the run on a change; on top,
  `replay` hashes `~/.claude/settings.json`, `~/.claude/CLAUDE.md`, `~/.claude/agents/` and `~/.claude/hooks/`
  before and after and stops with the diff if any changed (the owner restores from the installer's backups). The
  task tells the replay to test the installer with a temporary `HOME`.
- **A headless run writes the owner time log.** It must not (global rule); `replay` checks
  `~/.claude/hil/log.jsonl` is byte-equal before and after.
- **Matching is judgement.** It is never automated; every match and verdict carries the owner's name and date in
  `results.md`.
- **The ambysto-space case cannot run its tests here** (Windows). The reviewer reads code; its report's "not run"
  lines are expected and do not count either way.
- **Cost.** Estimate: about $3-8 per review case at `high`, so $20-50 for the 6 baseline reviews; the replay
  about $20-60 plus one review. Total roughly $50-120, no ceiling (owner decision); `run.json` records the actual.

## Proof

1. `python3 scripts/check.py`: PASS, including the new case checks.
2. `python3 scripts/switch-test.py --self-test`: PASS; the planted `known.md` read is voided.
3. One dry review: `switch-test.py review --model claude-opus-5-5 --case aps34-boundary` gives a `report.md` with
   PASS or FAIL, `run.json` with init model `claude-opus-5-5`, a cost, and void-check clean.
4. Baseline: `review` with `claude-fable-5-1` and `claude-opus-5-5` on all three cases, and `replay` with
   `claude-opus-5-5`; `results.md` filled, every match and verdict confirmed by the owner.
5. Release-day dry run: `RELEASE-DAY.md` followed end to end with `claude-opus-5-5` as the stand-in, up to (not
   including) the switch PR.
6. Before and after every run: `git status` clean and the same branch in claudecode-guide and ambysto-space;
   `~/.claude` hashes equal; the owner log unchanged by the runs.
7. `hard-reviewer` on the kit diff (range given, no checkout): PASS, or FAIL fixed within 2 rounds.
   **Result (2026-11-08):** rounds 1 and 2 FAIL, fixed; round 3 FAIL with 2 MAJOR and 3 MINOR in `void-check`, merged
   on the owner's approval with them listed in `switch-test/README.md` ("Open before release day"). Fixed in a
   follow-up PR the same day (owner decision: one small PR before the APS-47 build), with a self-test case each.

Not in this plan: APS-46; any model or effort change; matching by a model.
