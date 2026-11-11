---
status: approved # owner 2026-11-11: "2,3 và 4: approve" (item 2: measure tokens and cost per role and ticket before optimizing)
---
# Intent: cost report per role and ticket (APS-64)

## Why
The architecture review found no measure of what each role or ticket costs, so "optimal cost" could not be checked
and the rating and model choices rested on guesses. Claude Code's transcripts already hold the usage of every response.

## What
`scripts/cost-report.py`: tokens and USD from `~/.claude/projects`, main sessions and subagents, grouped by role,
ticket, model, day or project; prices in `scripts/model-prices.json`; a model without a price counts its tokens and
shows its cost as unknown; responses written on several lines count once; the unattributed share is shown, never
guessed.

## Not
No hook, no change to how agents run; no estimate for a model without a price.

## Done when
Self-test and `check.py` pass, a run on real data gives numbers, reviewer PASSes.
