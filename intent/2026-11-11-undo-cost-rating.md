---
status: approved # owner 2026-11-11: "2,3 và 4: approve" (item 4: loosen HARD in the playbook repo), after reading "lo-trinh-harness-loop-graph-p7" (gate by undo cost, not model confidence)
---
# Intent: rate tasks by undo cost (APS-63)

## Why
The cost-of-error axis had no scale, so in this repo nearly everything was rated HARD and the main session did it,
while the cheaper builder sat idle. The owner's series ("Đặt cổng theo giá của việc hoàn tác, không theo độ tự tin
của model") gives a scale: one-click undo, cleanup undo, no undo.

## What
1. Global "Task rating": cost of error judged by undo cost: one-click undo low, cleanup undo high, no undo HARD
   whatever the other axes say. This loosens nothing outside this repo: every case the old text made HARD (user data,
   security, money, cannot be undone) is still HARD, and something published or sent is added. The sdlc skill's
   rating convention says the same.
2. This repo's lists: HARD keeps the model and the switch-test runner, any change of a rule, the reviewers'
   checklist, the guards, save-it's write guards, the settings defaults, the dispatch contract, the installer's
   writes, the loop (done rule, spend); MEDIUM gains rewording the global block without a rule change (a rule found
   changed makes it HARD), the graph hook, `docs/internals.md` and the helper scripts; EASY gains intent and plan
   status lines that record work done. (Hard review round 1 kept save-it and the defaults HARD.)

## Not
No rule other than the rating changes; the EASY / MEDIUM / HARD routing itself stays.

## Done when
`check.py` passes and hard-reviewer PASSes.

## Open questions

None.
