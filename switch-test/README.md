# Model switch kit (APS-45)

The switch test of `global/CLAUDE.md` ("Switching models"), prepared before the candidate ships. It answers two questions:

- **(a) Reviewer.** Does the candidate, as `hard-reviewer`, catch at least as many known issues as the model it would
  replace, at an acceptable cost?
- **(b) Main session.** Does the candidate, as main session on a HARD task, leave fewer serious issues than Opus 5.5?
  If it replaces Opus there, `hard-reviewer` moves to Opus 5.5, since it must be a different model from the author.

On release day, follow `RELEASE-DAY.md`.

## Contents

| path | what |
|---|---|
| `cases/<id>/` | a review case: `case.json` (repo, base, head, rating, original reviewer, source transcript), `task.md` (the prompt the original reviewer got, with `{repo}` and `{range}` filled in at run time), `known.md` (the original first-round report, verbatim; issue n is `Kn`) |
| `replay/aps37-token-guard/` | the HARD task replayed for (b): `task.md` is the author's task, `known.md` the first-round report on the original author's commit, `case.json` adds `review_task` and the fixed `replay_reviewer` |
| `runs/<date>-<model>-<effort>/<case>/` | written by the runner: `report.md` (the run's final message) and `run.json` (model from the stream, effort, cost, tokens, duration, void check) |
| `results.md` | the scores, with the owner's verdicts |
| `candidates.txt` | created on release day: one published model ID per line; `check.py` refuses any other unpinned ID in the kit |

| case | repo, range | rating | original reviewer | known |
|---|---|---|---|---|
| `aps32-guard` | roles-assign `d5bc1dc..ea89167` | HARD | Fable 5.1, FAIL | 1 MAJOR, 6 MINOR |
| `aps34-boundary` | roles-assign `bcc4708..852a39a` | HARD | Fable 5.1, FAIL | 3 MAJOR, 4 MINOR, 1 NIT |
| `asp18-overview` | ambysto-space `266e95c..8f0356d` | MEDIUM | Opus 5.5, FAIL | 2 MAJOR, 2 MINOR |
| replay `aps37-token-guard` | roles-assign from `d33a160` (original commit `1f8064f`) | HARD | Fable 5.1, FAIL | 2 MAJOR, 5 MINOR |

Cases 1-3 were first found by Fable 5.1, so its baseline repeats its own review of the same diff in a new run. That
is a fair floor for "catches at least as many"; Opus 5.5 on the same cases shows what a different model catches.

## Running

```
python3 scripts/switch-test.py --self-test                      # no model calls
python3 scripts/switch-test.py probe --model <id>               # one cheap run: the reviewer's hook must block a checkout
python3 scripts/switch-test.py review --model <id> [--effort high] [--case <id>]
python3 scripts/switch-test.py replay --model <id> --effort <main session effort>
python3 scripts/switch-test.py void-check ~/.cache/model-switch-runs/<run>/<case>/stream.jsonl
```

- Every case runs in a fresh clone of the local repo (`~/work/<repo>`) under `~/.cache/model-switch-runs/`, detached
  at the case's head, with no remote. The clone fetches that one commit by hash (no branches, no tags), so it holds
  the case's history and nothing later: not the kit, not the fix. The runner never touches the source repos; it checks their branch and status,
  and the hashes of `~/.claude/settings.json`, `CLAUDE.md`, `agents/`, `hooks/` and the owner time log, before and
  after each run, and records any change in `run.json` (`watch_changed`) with a warning. It does not stop: the owner
  (`/model`, `/effort`) and the main session (the owner time log) write there too during a run, so the main session
  judges each change by hand, and a replay that touched `~/.claude` is investigated before it is scored.
- **Reviewer runs** are the session itself, not a subagent: `agents/reviewer.md`'s body is appended to the system
  prompt, its tools are allowed and its three agent-guard hooks are passed with `--settings`; `--model` and
  `--effort` set the model under test. The runner stops if the stream's init event names another model.
- **The replay** runs the candidate as main session with the autonomous-run settings (the boundary hook), on a branch
  `replay` in the clone, then the fixed reviewer (`replay_reviewer`, Fable 5.1, a different model from both Opus 5.5
  and the candidate) reviews its commit at `high`. One round of that review, no fixes after it. Before committing,
  the replay runs the HARD loop the global rules give every main session: it may call `hard-reviewer` (Fable 5.1 when the baseline was recorded, Fable 5.2 since 2026-11-10; from
  `~/.claude/agents`) and fix, as the Opus 5.5 baseline did (two rounds). So its commit is the loop's output, and the
  replay's `review_task` is the kit's own, the same for every replay (`case.json` `prompt_edits`): compare candidate
  replays with each other; the original author's first-round numbers in `known.md` are context, not a like-for-like
  baseline.
- Runs use `--no-session-persistence`, so they add nothing to `~/.claude/projects`.
- Cost: every review and replay is a real model run; `run.json` records it.

## Blindness

The candidate must never see the known findings. A run is **void** if any tool call names `switch-test/cases`,
`switch-test/replay`, `switch-test/runs`, a `known.md`, `~/.claude/projects` (old transcripts hold the original
reports) or another run's folder in the cache. `void-check` reads the raw stream; the runner applies it to every run.
A case's answer keys (the live source repo, the `void_extra` paths) count when read: named in a read or a shell
command (as `~/…`, `$HOME/…`, `${HOME}/…` or the absolute path), or at or below a folder that a content search names:
the Grep tool's `path`, `grep -r`/`-R`, `rg`, `ag`, `ack`, or `find` and `rg --files` when what they find is read
(`-exec`/`-ok`, inside `$( )`, or with `xargs`, `while` or `parallel` at any later stage of the same pipeline); and a
glob path read by any program but a name-only one (`cat ~/.claude/hooks/*/*.py`). A glob counts from the folder above
it; `/` holds everything. Commands are split outside quotes (so `grep -rnE 'a|b' ~/.claude` is one command), at
subshells and groups, and around `$( )` (also inside `"…"`); wrappers (`timeout`, `env`, `nice`, `nohup`, `sudo`, …)
are skipped, and `bash -c '…'` is searched as the commands it runs. The search pattern of grep, rg, ag and ack is not
a folder, even when it looks like a path. Listings of names (Glob, `ls`, `tree`, a plain `find`) do not count; nor
does Write or Edit content; nor `$HOME/…` or `~/…` in a command that sets `HOME=` itself (a temporary install).

Limits: a path built at run time (an interpreter assembling it, `..` steps, a relative path after `cd` to a parent) is
not seen. Heredoc bodies are data to the search rules (a heredoc fed to `bash` is not followed); the direct markers
still see them. A command that sets `HOME=` only as a prefix (`HOME=$T python3 x && cat $HOME/…`) has its later real
`$HOME` read missed. A shell command that writes the install target (`sed -i`, a heredoc into `~/.claude/hooks/…`)
is flagged like a read: the main session reads the flagged call, and when it only writes, records why in `run.json`
(`void_note`) and scores the run.

The 2026-11-07 baseline ran on plain clones, which still carried the source's current branch (the kit included).
Every git command in those streams was checked afterwards: none named a branch, tag or commit past the case's range.
`prompt_edits` in a `case.json` lists any change to the original prompt beyond `{repo}` and `{range}`.

## Scoring

Matching is judgement and is never left to a model. For each run the main session proposes, in `results.md`, which
reported issue matches which `Kn` (same defect, even if worded differently) and lists the unmatched ones; the owner
confirms each match and marks each unmatched issue **new real** or **false alarm**. Per case: known caught / known
total, MAJOR-or-worse caught, new real, false alarm, cost, tokens, effort, minutes. For the replay: BLOCKER and MAJOR
counts in the fixed reviewer's report, which `Kn` the replay repeated, and the cost of both runs.

Reports from the ambysto-space case cannot run its Windows tests here; "not run" lines count neither way.
