Independent hard review of APS-34 in {repo} (head 852a39a). Diff: `git diff {range}`. Do not switch branches or edit that checkout; probe by importing a scratch copy of hooks/agent-guard.py from Python, and with scratch repos made through Python subprocess under /tmp. If you need real `bd show` output and a beads binary (v1.3.1) is on PATH, always run it with DO_NOT_TRACK=1 and HOME pointed at a scratch folder (it sends usage metrics otherwise).

Task (Plane APS-34, verbatim): "A PreToolUse hook loaded only by autonomous runs (a settings file passed with claude --settings) that blocks the human-only list of the APS-31 intent: tags, releases, publishing; signing, keys and secret files; force push, remote deletes, pushes to main; edits to protected paths (specs, licences, the guard's own settings and hooks); bd commands outside an allowlist (frozen bead fields, closing gates or human items, bd without DO_NOT_TRACK). Interactive sessions unchanged. HARD: main session, then hard-reviewer."
Context: the human-only list is in `intent/2026-10-22-autonomous-run.md` ("Human-only boundary"), and the bead rules ("Frozen definitions": an agent may change only status, evidence, cost and the claim) are in its Graph section. The builder/reviewer modes of the same script (APS-32) are already merged and reviewed; review them only where this change touches them.

Check especially:
- items of the human-only list that a plain, non-evasive command still gets past (ordinary mistakes matter most; evasion is a documented non-goal, but say which evasions are cheap to close);
- false blocks of the ordinary work an autonomous run must do: build, test, commit and push a feature branch, open PRs, comment, `bd ready/show/create/update --claim/close`;
- the bd allowlist against bd 1.3.1's real flags (`bd update --help`, `bd close --help`): any flag that changes title, acceptance, design, type, deps or parent and slips through; the gate/human close check, fail-closed paths;
- the protected-path check (fnmatch semantics, symlinks, paths outside a repo, `.claude/boundary.json` validation);
- that interactive sessions are not affected (only the settings file wires `boundary`), install.py installs the JSON and check.py validates it;
- docs claim no more than the code does.
Run `python3 scripts/check.py`, `python3 hooks/agent-guard.py --self-test`, and at least two mutation checks of your own. Return PASS or FAIL with numbered issues (BLOCKER/MAJOR/MINOR/NIT), at most 500 words; FAIL only for BLOCKER or MAJOR.
