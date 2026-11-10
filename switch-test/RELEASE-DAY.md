# Release day: run the switch test on a new model

For the candidate (Fable 5.2 when it ships; the owner corrected 5.5 to 5.2 on 2026-11-10). HARD (this repo's CLAUDE.md): the main session runs it; the owner
confirms every match and makes the decision. Use a branch `aps-NN-switch-<model>`.

1. **The ID.** Take the full model ID from Anthropic's model list (not a guess, not an alias). Add one line to
   `switch-test/candidates.txt`: `<id> published <date> <source>`. `python3 scripts/check.py` must pass.
2. **Probe.** `python3 scripts/switch-test.py probe --model <id>`: the hook must block the checkout, and the printed
   model must be the candidate.
3. **Reviews.** `python3 scripts/switch-test.py review --model <id> --effort high`. If a run prints VOID, rerun that
   case; never score a void run.
4. **Replay.** `python3 scripts/switch-test.py replay --model <id> --effort <the main session's effort in
   settings.json today>`; use the same effort as the Opus 5.5 replay baseline in `results.md`, or rerun that baseline
   at today's effort first.
5. **Score.** Add the run's tables to `results.md` with the proposed matches; the owner confirms each match and marks
   each unmatched issue new real or false alarm.
6. **Decide**, against the baseline rows:
   - (a) Candidate ≥ Fable 5.1 on known issues caught (MAJOR-or-worse first) at a cost the owner accepts →
     `hard-reviewer` moves to the candidate. Fewer → it stays.
   - (b) Candidate as main session leaves fewer BLOCKER/MAJOR and repeats fewer `Kn` than Opus 5.5, at a cost the owner
     accepts → the owner decides whether the main session moves. If it does, `hard-reviewer` moves to Opus 5.5 (it must
     differ from the author), and the builder and reviewer pins are reconsidered in the same PR.
   - (a) and (b) disagree, or a result is within one issue → one more replay (a second HARD task) before deciding.
7. **The switch PR** (only if something moves), on a branch. Each command first with `--dry-run`, then without:
   - (a) only: `python3 scripts/switch-model.py --role hard-reviewer --to <id> --note "<results.md numbers>"`. It
     edits the agent's `model:`, its `global/CLAUDE.md` and README lines and a dated Switch line.
   - (b), the main session moves: `python3 scripts/switch-model.py --role main --to <id> --effort <owner's level>
     --hard-reviewer <a model other than <id>, e.g. claude-opus-5-5> --note "<numbers>"`, one command, so the two
     never coincide (this also works after (a) moved hard-reviewer to the candidate). It edits "Current choice", the
     effort entry, the model example and the README settings line, plus hard-reviewer's lines.
   - Any other agent (builder, reviewer, transcriber): `--role <agent>` the same way.
   Every run checks `check.py` before and after and writes nothing on a refusal. An agent's `effort:` is edited by
   hand if the owner changes it. When the main session moves, the owner runs `/model <full id>` and `/effort <level>`
   (then checks `settings.json` holds the full ID, not an alias). The `results.md` numbers go in the PR body; after the
   merge `install.py --global` and `install.py --check`.
8. Close the "switch test" line in this repo's `CLAUDE.md` Open, or note what is left.

Dry run (2026-11-07): steps 2-5 with `claude-opus-5-5` standing in for the candidate; see `results.md`.
