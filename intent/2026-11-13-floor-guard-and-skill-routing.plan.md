---
status: verified # draft → planned → building → verified
---
# Plan: diff floor guard, skill routing checks, and reviewer/sdlc refinements

Intent: `2026-11-13-floor-guard-and-skill-routing.md` (approved). Ticket: Plane APS-77.
HARD (`rores/agents/reviewer.md`, `skills/sdlc/SKILL.md`): the main session builds; hard-reviewer reviews.

## Files

1. `scripts/sdlc-check.py` — add `floor_notes(top, mb, paths, own)` called by `converge` to scan diff additions/deletions and untracked files (excluding `own` plan/intent and self-test literals on the same line) for added linter/type suppressions, added test skips, deleted test files, and net removed assertions; report each as a `floor: <path>: <detail>` note, with self-tests.
2. `scripts/check.py` — support multi-line block scalars (`|` / `>`) in `split_frontmatter`; add deterministic TF-IDF cosine collision check (`< 0.60`) and positive/negative trigger ranking checks across all 9 skills in `skills/`.
3. `skills/sdlc/SKILL.md` — in Phase 1 (Intent), attach a best-guess default/recommendation to each question; in Phase 4 (Verify), note that `converge` also prints `floor:` lines for the reviewer.
4. `rores/agents/reviewer.md` and `rores/agents/hard-reviewer.md` — in Check #2 (Rules held) and Check #6 (Tests), flag unrequested linter/type suppressions (`noqa`, `type: ignore`, `@ts-ignore`, `eslint-disable`), skipped or deleted tests, and stripped assertions.
5. `docs/internals.md`, `README.md`, `CLAUDE.md` — document the floor notes in `sdlc-check.py` and skill routing check in `check.py`.

## Risks

- A test fixture or self-test in a repo intentionally contains `# noqa` or `.skip` strings on a single line: `floor_notes` checks actual comment/decorator shapes on added lines and reports `floor:` notes (which `converge` prints for the reviewer without failing exit code 0), so a legitimate suppression or self-test never blocks `loop-stop.py`.
- `split_frontmatter` in `check.py` previously left `whats-next` with `description == "|"` instead of its indented body: reading indented continuation lines after `:` with `|` or `>` fixes `whats-next` and lets the description length, `: ` and TF-IDF routing checks cover the real text.

## Tasks

### T1 (main) Diff floor notes in sdlc-check.py and skill routing check in check.py
- allow: `scripts/sdlc-check.py` `scripts/check.py`
- check: `python3 scripts/sdlc-check.py --self-test`
- check: `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py`

### T2 (main) Reviewer checklist, sdlc Phase 1 best-guess rule, and docs
- allow: `rores/agents/reviewer.md` `rores/agents/hard-reviewer.md` `skills/sdlc/SKILL.md` `docs/internals.md` `README.md` `CLAUDE.md`
- check: `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py`

## Proof

1. `python3 scripts/sdlc-check.py clarify intent/2026-11-13-floor-guard-and-skill-routing.md` passes.
2. `python3 scripts/sdlc-check.py --self-test` passes, covering `floor:` notes for added suppressions, skipped tests, deleted test files, and net removed assertions.
3. Mutations of the new floor-note and skill-routing guards in `scripts/sdlc-check.py` and `scripts/check.py` are each caught by `--self-test` / `check.py`.
4. `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py` passes.
5. `HOME=$(mktemp -d) python3 scripts/install.py` then `--check` under the same `HOME` passes.
6. `python3 scripts/sdlc-check.py converge intent/2026-11-13-floor-guard-and-skill-routing.plan.md --checks` passes.
7. Independent review by `hard-reviewer` ( plus agent and skill trial checks from `CLAUDE.md` Verify) returns PASS.

## Result

1. PASS: `python3 scripts/sdlc-check.py clarify intent/2026-11-13-floor-guard-and-skill-routing.md`, 0 gap(s).
2. PASS: `python3 scripts/sdlc-check.py --self-test` passed, covering deleted test files, added suppressions, added test skips, net removed assertions, and quiet runs when assertions increase.
3. PASS: 7 of 7 mutations caught (5 in `sdlc-check.py`: deleted test file, tracked suppression, tracked skip, removed assertions, untracked scan; 2 in `check.py`: duplicate skill description collision `0.97 > 0.60`, and broken folded/block scalar parser on `whats-next`).
4. PASS: `systemd-run --user --scope -q -p MemoryMax=4G python3 scripts/check.py` (4 agents pinned, reviewer bodies equal, guard hooks set and self-tested, session hooks registered once, 9 skills valid with TF-IDF collision and trigger checks).
5. PASS: `HOME=$(mktemp -d) python3 scripts/install.py --global --settings` then `--check` under the same `HOME` exited 0 with no drift.
6. PASS: `python3 scripts/sdlc-check.py converge intent/2026-11-13-floor-guard-and-skill-routing.plan.md --checks`, 0 gap(s).
7. PASS: `hard-reviewer` returned PASS (0 BLOCKER, 0 MAJOR, 1 MINOR: fill `## Result`, done here); fresh SDLC trial agent given only `skills/sdlc/SKILL.md` produced 3 Phase 1 questions with best-guess defaults and named the Phase 4 `floor:` output lines without guessing.
