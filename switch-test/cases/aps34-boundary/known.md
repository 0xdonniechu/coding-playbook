# Known findings: aps34-boundary

The original first-round report, verbatim (claude-fable-5-1). Issue n of the report is `K{n}` in results.md.

---

**FAIL**

1. **MAJOR** `hooks/agent-guard.py:531-533` (`boundary_bd`, status detection). `rest[:-1] + [""]` drops the last argument, so `bd update <gate> --status=closed` or `-s=closed` with the flag last never reaches the gate/human check. Probe with real bd 1.3.1: `bd close tr-ur2` (type `gate`) blocked, `bd update tr-ur2 --status=closed` ALLOWED. Both the `-s closed` and `--status closed` forms are fine.

2. **MAJOR** `hooks/agent-guard.py:425-437` (`boundary_git`). The current-branch check only runs when `git push` names no ref; `git push origin HEAD` and `git push -u origin HEAD` on `main` are ALLOWED (probe on a scratch repo, branch main). `HEAD`/`@` as the destination must resolve the branch like the bare form.

3. **MAJOR** `hooks/agent-guard.py:541-546`. "Fail closed" is only true when `bd` is absent. Real `bd show <missing> --json` exits 1 but prints a JSON object `{"error": …}` on stdout; the code never checks `returncode`, `.get("issue_type")` is None, and `bd close tr-zzz` is ALLOWED. Any `bd show` failure that prints JSON (locked database, schema skew) lets a close through. The self-test's fake `bd` does not model this, and CLAUDE.md's "blocks when it cannot [read]" overstates the code.

4. **MINOR** Protected paths are caught only through Edit/Write, `>` and `tee`. Allowed in probes: `rm docs/spec/a.md`, `git rm docs/spec/a.md`, `mv docs/spec/a.md …`, `cp x docs/spec/a.md`, `git checkout other -- docs/spec/a.md`. `cp`/`sed -i` are documented in CLAUDE.md Open; `rm`, `mv`, `git rm/mv/checkout/restore` are not, and are ordinary mistakes. Cheap to close: run `boundary_path` on the non-flag args of those commands.

5. **MINOR** Cheap evasions/omissions: `npx vsce publish`, `xcrun codesign …` (wrapper not unwrapped); `git update-ref refs/tags/v1 HEAD` then `git push origin v1` (tag name without `refs/tags/`); `gh api repos/o/r/git/refs -f ref=refs/tags/v1`; `gh api graphql -f query='mutation …'`; `.env` and `~/.claude.json` (holds the Plane key) are not in `SECRET_PATH`.

6. **MINOR** `bd update -p 4`, `--add-label optional`, `--defer` are allowed: they make a bead optional or hide it from `bd ready`, which changes what blocks "done" although the Graph section allows only status, evidence, cost and claim. `bd create --deps blocks:<owner-bead>` adds a blocker to an existing bead.

7. **MINOR** `cd` inside a subshell leaks: `(cd docs/spec && cat a.md); echo y > notes.txt` is blocked as `docs/spec/notes.txt`.

8. **NIT** False blocks: `bd done` (documented alias of `close`); `openssl x509 -in c.pem -text` (any `.pem` word); `cat .npmrc`; `yarn npm info`; `--append-notes '-evidence'`. `DO_NOT_TRACK=1 echo; bd ready` passes the regex. Case variants (`license.md`, `DOCS/SPEC`) are not protected.

Scope, wiring, docs: scope matches the ticket; only `autonomous-settings.json` wires `boundary` (settings-defaults untouched, check.py validates the JSON, install.py installs `hooks/*.json`); interactive sessions unaffected. Symlinks resolve (`specs -> docs/spec` blocked), invalid or non-list `boundary.json` blocks every edit, paths outside a repo pass only the guard/secret regexes. Ordinary work passes: commit, `push -u origin topic`, `gh pr create`, comments, `bd ready/show/create/update --claim/close`.

Commands run (on an exported copy of 852a39a, never the checkout):
- `python3 scripts/check.py`: PASS.
- `hooks/agent-guard.py --self-test`: PASS, 132 command cases + 77 boundary cases.
- Mutation checks: gate type compared to `gatex` → 2 failures; `--tags` removed from push flags → 1 failure; `docs/spec/*` removed → 3 failures. All detected.
- Probe scripts in `/tmp/claude-1000/-home-dc-group-work-ambysto-ambysto-space/69e03d46-061c-4c31-941c-cd57f6f4f100/scratchpad/probe1.py` and `probe2.py` (real bd 1.3.1, scratch HOME, DO_NOT_TRACK=1).

Not run: `install.py --check` (branch not installed on this machine); a real `claude --settings` headless run (owner-level).
