---
status: verified # draft → planned (owner accepts) → building → verified
---
# Plan: one-command model switch (APS-47)

Contract: `intent/2026-11-08-model-switch-command.md` (approved 2026-11-08). Rating: HARD (model switching is on this
repo's HARD list): the main session builds, `hard-reviewer` reviews the diff (range given, no checkout). Builds on
APS-45 (`switch-test/candidates.txt`, `RELEASE-DAY.md`); the build branch starts after PR #26 is merged.

## What the command edits (for an agent role, e.g. `hard-reviewer` → `claude-fable-5-5`)

| file | line today | after |
|---|---|---|
| `agents/hard-reviewer.md` | `model: claude-fable-5-1` | `model: claude-fable-5-5` |
| `global/CLAUDE.md` "Subagents" | `- **hard-reviewer** (Fable 5.1): …` | `(Fable 5.5)`, rest kept |
| `README.md` | `` | `agents/hard-reviewer.md` | … | Fable 5.1: … `` | `Fable 5.5:`, rest kept |
| `global/CLAUDE.md` "Model economy" | (none) | a line right after "Current choice": `Switch (<date>): hard-reviewer → Fable 5.5 (`claude-fable-5-5`); switch test: <note>.` One line per role: a later switch of the same role replaces it. |

For `--role main`: the "Current choice" line becomes `**Current choice (<date>): <Label>.** <note>`, and the effort
line's `(<Old label>: `<level>`, …)` gets the new label; the command then prints the owner's steps (`/model <id>`, the
effort entry, `install.py`). `settings.json` is never touched.

Labels come from `check.py`'s `model_label` (`claude-fable-5-5` → `Fable 5.5`), imported, not copied.

## Files, in order

1. `scripts/switch-model.py` (standard library only):
   - `--role {builder,reviewer,hard-reviewer,transcriber,main} --to <id> --note <text> [--dry-run] [--root <path>]`,
     and `--self-test`. `--root` defaults to this repo; the self-test points it at a scratch copy.
   - Before editing: the ID matches `check.py`'s `PINNED`; it is pinned by an agent or listed in
     `switch-test/candidates.txt`; `reviewer` and `hard-reviewer` may not get the main session's model (the label in
     "Current choice"), and `main` may not get `hard-reviewer`'s model; `--note` is not empty; `python3
     scripts/check.py` in the root passes. Any refusal exits 1 and writes nothing.
   - Every edit is computed in memory first; each anchor must match exactly once, or nothing is written. Already at the
     target: "nothing to change", exit 0. `--dry-run` prints the diff only. Otherwise it writes, prints the diff, runs
     `check.py` in the root, and on a failure restores every file it wrote and exits 1.
   - It writes only under the root, and refuses a root inside `~/.claude`. It never commits or installs.
2. The self-test, on a scratch copy of the tracked files (`git ls-files`), with `candidates.txt` listing the
   placeholder `claude-test-9-9` (label `Test 9.9`):
   - `hard-reviewer` → placeholder changes exactly the four lines above, and `check.py` passes on the copy;
   - the same command again changes nothing;
   - switching back to `claude-fable-5-1` restores every file byte for byte except the role's Switch line, which now
     records the switch back (the intent said "byte for byte"; the Switch line is the record, so it stays);
   - refused, with nothing written: a guessed `claude-fable-5-5` not in `candidates.txt`; `hard-reviewer` →
     `claude-opus-5-5` (the main session's model); an empty note; role `foo`; a copy whose `check.py` fails first.
   - `check.py` runs `switch-model.py --self-test`, and the copy's `check.py` would run it again: the self-test sets
     `SWITCH_MODEL_SELF_TEST=1` and `check.py` skips that one step when it is set.
3. `scripts/check.py`: runs `switch-model.py --self-test` (unless the variable above is set).
4. `switch-test/RELEASE-DAY.md` step 7: `switch-model.py --dry-run` first, then the same without it, with the
   `results.md` numbers as the note; then the owner's `/model` step when `main` moves; `install.py` after the merge.
5. `global/CLAUDE.md` "Switching models" step 3 names the command; this repo's `CLAUDE.md` Verify mentions its
   self-test; `README.md` gets one row for `scripts/switch-model.py`.

## Risks, and the check that catches each

- **A wrong line edited** (for example "ahead of Fable 5.1" in the Current choice sentence). Edits are anchored to
  the exact patterns in the table, each must match once; the self-test compares the whole copy with the expected
  four-line change.
- **A half-applied switch.** Nothing is written until every anchor matches; after writing, a failing `check.py`
  restores the files. The self-test plants a failing copy and checks nothing changed.
- **A guessed ID**, **a reviewer on the author's model**: refusals above, each one in the self-test.
- **Endless recursion** between `check.py` and the self-test: the environment variable; the self-test must finish
  (it runs under `check.py` in this repo's Verify, which would hang otherwise).
- **The real `~/.claude` edited**: the root check; the installed copy changes only through `install.py`, run by the
  main session after the owner merges.
- **The kit's yardstick moves with the switch.** `replay_reviewer` and the baseline stay Fable 5.1 by design; the
  command does not touch `switch-test/`, and the self-test checks that folder is unchanged.

## Proof

1. `python3 scripts/check.py`: PASS, with the new self-test.
2. `python3 scripts/switch-model.py --self-test`: PASS.
3. Mutations on a scratch copy, each must turn the self-test FAIL: skip the README edit; drop the main-model
   refusal; write before every anchor matched.
4. On this repo: `switch-model.py --role hard-reviewer --to claude-opus-5-5 --note x --dry-run` is refused (main
   session model); `--to claude-fable-5-5` is refused (not published, not in `candidates.txt`); `git status` clean
   after both.
5. `hard-reviewer` on the build diff (range given, no checkout): PASS, or FAIL fixed within 2 rounds.

**Changed in build (2026-11-08):** only `hard-reviewer` is refused on the main session's model (`reviewer` reviews the
builder's work and is Opus 5.5 today, like the main session; the intent named both by mistake). `--note` is required
for every role. An ID is accepted when pinned, listed in `candidates.txt`, or recorded by a real run in
`switch-test/runs/**/run.json`, so a switch back to the replaced model (no longer pinned) works. The labels and
`PINNED` come from `check.py` through its syntax tree, without running its checks. `check.py` also checks each
agent's README row names its pinned model. The self-test adds a missing anchor that `check.py` does not guard (the
main-session effort entry): the whole switch is refused.

**Changed after review round 1 (2026-11-08):** the self-test's guessed ID is `claude-guess-1-1` (on release day the
candidate's own runs record its ID, which the first version used as the "guessed" case and would have blocked the
switch). A run is a list of moves checked on the end state: `--role main … --hard-reviewer <id>` moves both in one
command, since moving them one at a time can deadlock (hard-reviewer must always differ from the main session).
`--role main` also edits the model example in `global/CLAUDE.md` ("as a full model ID (`…`)") and the README settings
line, and updates the effort alone when the model stays; `check.py` checks the four main-session places agree.
Refusals are tested with their reasons. Proof 4's `--to claude-fable-5-5` refusal holds only until a run records that
ID.

**Review (2026-11-08):** round 1 FAIL (1 BLOCKER, 2 MAJOR), fixed; round 2 PASS. Its MINOR items were fixed after:
the main session is compared by ID (a dated ID of the same model is written), a note with a line break and `--effort`
with an agent role are refused, the self-test runs outside a git tree, and hard-reviewer's Switch line says it moved
with the main session. Each has a self-test case and a mutation that it catches.

**Found in real use (2026-11-08):** the first real run (`--role main --to claude-opus-5-5 --effort high`, the owner's
effort decision) was refused, and every file restored, because the self-test hard-coded the state of the day it was
written (an effort-only switch to `high`, hard-reviewer on Fable 5.1, a Switch line added rather than replaced, and
a fresh `candidates.txt`). The self-test now reads the main model, label and effort and hard-reviewer's model from the
copy, adds to `candidates.txt`, and allows an existing Switch line. Proof: it passes on scratch copies in four states
(effort `high`; after (a); after (b); after (a) then (b)), and 14 mutations each turn it FAIL (one, a dropped check
before the switch, was missed until the test required the refusal's reason).

Not in this plan: switching any model; changing the switch test; `settings.json`; APS-46.
