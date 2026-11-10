#!/usr/bin/env python3
"""Moves one role to another model in one edit, for the PR that switches a model.

    python3 scripts/switch-model.py --role hard-reviewer --to <published id> --note "<switch test numbers>" [--dry-run]
    python3 scripts/switch-model.py --role main --to <id> --effort <level> --note "<numbers>" [--dry-run]
    python3 scripts/switch-model.py --self-test

For an agent role it edits the agent file's `model:`, the role's line in global/CLAUDE.md ("Subagents"), its README
row, and one dated "Switch (...)" line under "Current choice". For `main` it edits the "Current choice" line and the
main session's effort entry, then prints the owner's steps: settings.json stays owner-only. It edits this repo's
working tree only (never ~/.claude), never commits or installs, and writes nothing unless every edit applies and
check.py passes before and after (a failure after writing restores the files). Standard library only.
"""
import argparse
import ast
import datetime
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROLES = ("builder", "reviewer", "hard-reviewer", "transcriber")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
SELF_TEST_ENV = "SWITCH_MODEL_SELF_TEST"  # set while the self-test runs a copy's check.py, which would run it again
CURRENT = re.compile(r"^\*\*Current choice \((\d{4}-\d{2}-\d{2})\): ([A-Z][a-z]+ \d+\.\d+)\.\*\*(.*)$", re.M)
EFFORT_ENTRY = re.compile(r"for the main session \(([A-Z][a-z]+ \d+\.\d+): `(\w+)`, owner decision (\d{4}-\d{2}-\d{2})\)")


class Refused(Exception):
    pass


def from_check(root):
    """PINNED and model_label from the root's check.py (one source), without running its checks."""
    tree = ast.parse((root / "scripts" / "check.py").read_text(encoding="utf-8"))
    keep = [n for n in tree.body
            if (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "PINNED" for t in n.targets))
            or (isinstance(n, ast.FunctionDef) and n.name == "model_label")]
    space = {"re": re}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "check.py", "exec"), space)
    return space["PINNED"], space["model_label"]


def check(root):
    out = subprocess.run([sys.executable, str(root / "scripts" / "check.py")], cwd=root, capture_output=True, text=True)
    return out.returncode == 0, (out.stdout + out.stderr).strip()


def pin(text):
    head = text.split("\n---\n", 1)[0]
    found = re.findall(r"^model: (\S+)$", head, re.M)
    if len(found) != 1:
        raise Refused("an agent file without exactly one `model:` line in its frontmatter")
    return found[0]


def once(text, pattern, repl, what):
    """Applies one regex replacement that must match exactly once."""
    new, count = re.subn(pattern, repl, text, flags=re.M)
    if count != 1:
        raise Refused(f"{what}: expected exactly one match, found {count}")
    return new


def known_ids(root, pins):
    """IDs a switch may name: the agents' pins, the published candidates the owner listed, and models a real run
    reported (switch-test/runs/**/run.json, from the stream's init event), such as the model a switch replaces."""
    candidates = root / "switch-test" / "candidates.txt"
    ids = set(pins.values())
    if candidates.exists():
        ids |= {line.split()[0] for line in candidates.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")}
    for run_json in (root / "switch-test" / "runs").rglob("run.json"):
        try:
            ids.add(json.loads(run_json.read_text(encoding="utf-8")).get("model"))
        except (ValueError, AttributeError):
            pass
    return ids


def plan_edits(root, moves, note, effort, today):
    """moves: [(role, model id)], applied in order and checked on the end state (hard-reviewer must differ from the
    main session). Returns {relative path: new text} for the files that change; raises Refused."""
    pinned, label = from_check(root)
    if not note.strip():
        raise Refused("--note is empty: give the switch test's numbers from switch-test/results.md")
    if "\n" in note.strip() or "\r" in note:
        raise Refused("--note has a line break: it is written into one line of global/CLAUDE.md")
    rels = ["global/CLAUDE.md", "README.md", *(f"agents/{r}.md" for r in ROLES)]
    texts = {rel: (root / rel).read_text(encoding="utf-8") for rel in rels}
    pins = {r: pin(texts[f"agents/{r}.md"]) for r in ROLES}
    known = known_ids(root, pins)
    current = CURRENT.search(texts["global/CLAUDE.md"])
    if not current:
        raise Refused("global/CLAUDE.md: no '**Current choice (<date>): <Model>.**' line")
    main_label = current.group(2)
    for role, to in moves:
        if not pinned.match(to):
            raise Refused(f"{to!r} is not a full model ID (claude-<family>-<major>-<minor>)")
        if to not in known:
            raise Refused(f"{to} is not pinned by an agent, listed in switch-test/candidates.txt or recorded by a real "
                          "run in switch-test/runs (no guessed IDs)")
        new_label = label(to)
        glob = texts["global/CLAUDE.md"]
        if role == "main":
            entry = EFFORT_ENTRY.search(glob)
            if not effort:
                raise Refused("--role main needs --effort (the owner's effort for the main session model)")
            example = re.search(r"as a full model ID \(`(claude-[a-z]+-\d+-\d+(?:-\d{8})?)`\)", glob)
            if example and example.group(1) == to and entry and entry.group(2) == effort:
                continue
            if not example or example.group(1) != to:  # a new model, or a dated ID of the same one
                glob = once(glob, CURRENT.pattern, lambda m: f"**Current choice ({today}): {new_label}.** {note.strip()}",
                            "global/CLAUDE.md 'Current choice' line")
                glob = once(glob, r"as a full model ID \(`claude-[a-z]+-\d+-\d+(?:-\d{8})?`\)",
                            lambda m: f"as a full model ID (`{to}`)", "global/CLAUDE.md main-session model example")
            glob = once(glob, EFFORT_ENTRY.pattern,
                        lambda m: f"for the main session ({new_label}: `{effort}`, owner decision {today})",
                        "global/CLAUDE.md main-session effort entry")
            texts["README.md"] = once(texts["README.md"],
                                      r'`"model": "claude-[a-z]+-\d+-\d+(?:-\d{8})?"`, and `\w+` effort under `modelSettings`',
                                      lambda m: f'`"model": "{to}"`, and `{effort}` effort under `modelSettings`',
                                      "README.md main-session settings line")
            texts["global/CLAUDE.md"], main_label = glob, new_label
            continue
        old = pins[role]
        if old == to:
            continue
        old_label, agent = label(old), f"agents/{role}.md"
        texts[agent] = once(texts[agent], rf"^model: {re.escape(old)}$", f"model: {to}", f"{agent} model line")
        glob = once(glob, rf"^(- \*\*{re.escape(role)}\*\* \(){re.escape(old_label)}\)", rf"\g<1>{new_label})",
                    f"global/CLAUDE.md '**{role}** ({old_label})' line")
        because = "moved with the main session, which must differ" if role == "hard-reviewer" and moves[0][0] == "main" \
            else f"switch test: {note.strip()}"
        line = f"Switch ({today}): {role} → {new_label} (`{to}`); {because}"
        previous = rf"^Switch \(\d{{4}}-\d{{2}}-\d{{2}}\): {re.escape(role)} → .*$"
        if re.search(previous, glob, re.M):
            glob = once(glob, previous, lambda m: line, f"global/CLAUDE.md Switch line for {role}")
        else:
            glob = once(glob, r"^(\*\*Current choice \(.*)$", lambda m: m.group(1) + "\n" + line,
                        "global/CLAUDE.md 'Current choice' line")
        texts["global/CLAUDE.md"] = glob
        texts["README.md"] = once(texts["README.md"], rf"^(\| `{re.escape(agent)}` \|[^|\n]*\| ){re.escape(old_label)}:",
                                  rf"\g<1>{new_label}:", f"README.md row for {agent}")
        pins[role] = to
    if label(pins["hard-reviewer"]) == main_label:
        raise Refused(f"hard-reviewer and the main session would both be {main_label}: hard-reviewer must be a different "
                      "model from the author. When the main session moves, move hard-reviewer in the same command "
                      "(--role main ... --hard-reviewer <id>)")
    return {rel: text for rel, text in texts.items() if text != (root / rel).read_text(encoding="utf-8")}


def show(root, edits):
    for rel, new in edits.items():
        old = (root / rel).read_text(encoding="utf-8")
        sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{rel}", f"b/{rel}"))


def switch(root, moves, note, effort=None, dry_run=False, today=None):
    root = root.resolve()
    claude = (Path.home() / ".claude").resolve()
    if root == claude or claude in root.parents:
        raise Refused(f"{root} is inside ~/.claude: switch the repo, then install.py after the merge")
    ok, out = check(root)
    if not ok:
        raise Refused("check.py fails before the switch; fix that first:\n" + out)
    edits = plan_edits(root, moves, note, effort, today or datetime.date.today().isoformat())
    what = ", ".join(f"{role} to {to}" for role, to in moves)
    if not edits:
        print(f"nothing to change: already {what}")
        return
    show(root, edits)
    if dry_run:
        print("dry run: nothing written")
        return
    saved = {rel: (root / rel).read_bytes() for rel in edits}
    for rel, new in edits.items():
        (root / rel).write_text(new, encoding="utf-8")
    ok, out = check(root)
    if not ok:
        for rel, data in saved.items():
            (root / rel).write_bytes(data)
        raise Refused("check.py fails after the switch; every file restored:\n" + out)
    print(f"switched {what} in {', '.join(edits)}; check.py PASS. Not committed, not installed.")
    main = dict(moves).get("main")
    if main:
        print(f"Owner steps: `/model {main}` (then check ~/.claude/settings.json holds the full ID, not an alias), "
              f"`/effort {effort}`; after the merge `python3 scripts/install.py --global`.")
    else:
        print("After the merge: `python3 scripts/install.py --global`, then `python3 scripts/install.py --check`.")


def self_test():
    problems = []
    tracked = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=REPO,
                             capture_output=True, text=True)
    listed = tracked.stdout.split("\0") if tracked.returncode == 0 else \
        [p.relative_to(REPO).as_posix() for p in REPO.rglob("*") if p.is_file() and ".git" not in p.parts]
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "repo"
        for rel in filter(None, listed):
            if (REPO / rel).is_file():
                (copy / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO / rel, copy / rel)
        cands = copy / "switch-test" / "candidates.txt"  # kept: the IDs a switch has already recorded stay valid
        cands.write_text((cands.read_text() if cands.exists() else "") + "claude-test-9-9 published 2026-01-01 self-test\n")
        env = dict(os.environ, **{SELF_TEST_ENV: "1"})

        def snapshot():
            return {p.relative_to(copy).as_posix(): p.read_bytes() for p in copy.rglob("*") if p.is_file()}

        def run(*args, root=copy):
            return subprocess.run([sys.executable, str(REPO / "scripts" / "switch-model.py"), "--root", str(root), *args],
                                  env=env, capture_output=True, text=True)

        def changed(before, after):
            return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))

        base = snapshot()
        # today's state, read from the copy (never assumed: the real switch changes it)
        _, label = from_check(copy)
        glob0 = (copy / "global" / "CLAUDE.md").read_text(encoding="utf-8")
        main_id = re.search(r"as a full model ID \(`([^`]+)`\)", glob0).group(1)
        main_label, main_effort = CURRENT.search(glob0).group(2), EFFORT_ENTRY.search(glob0).group(2)
        hr_id = pin((copy / "agents" / "hard-reviewer.md").read_text(encoding="utf-8"))
        hr_label = label(hr_id)
        cands.write_text(cands.read_text() + f"{hr_id} self-test: the model the switch back returns to\n")
        base = snapshot()  # the copy as every later step starts from
        other_effort = "low" if main_effort != "low" else "medium"
        had_switch = bool(re.search(r"^Switch \([^)]*\): hard-reviewer ", glob0, re.M))  # after release day (a)
        # an ID no run can record: on release day the candidate's own runs put its ID in switch-test/runs
        for args, reason in [(["--role", "hard-reviewer", "--to", "claude-guess-1-1", "--note", "x"], "no guessed IDs"),
                             (["--role", "hard-reviewer", "--to", main_id, "--note", "x"], "must be a different model"),
                             (["--role", "hard-reviewer", "--to", "claude-test-9-9", "--note", " "], "--note is empty"),
                             (["--role", "foo", "--to", "claude-test-9-9", "--note", "x"], "invalid choice"),
                             (["--role", "main", "--to", hr_id, "--effort", "high", "--note", "x"],
                              "must be a different model"),
                             (["--role", "main", "--to", "claude-test-9-9", "--note", "x"], "needs --effort"),
                             (["--role", "reviewer", "--to", "claude-test-9-9", "--hard-reviewer", main_id,
                               "--note", "x"], "goes with --role main"),
                             (["--role", "builder", "--to", "claude-test-9-9", "--effort", "low", "--note", "x"],
                              "--effort goes with --role main"),
                             (["--role", "hard-reviewer", "--to", "claude-test-9-9", "--note", "a\nb"], "line break")]:
            out = run(*args)
            if out.returncode == 0 or reason not in out.stderr or changed(base, snapshot()):
                problems.append(f"not refused for '{reason}', or files written: {out.stdout + out.stderr}")
        out = run("--role", "hard-reviewer", "--to", "claude-test-9-9", "--note", "x",
                  root=Path.home() / ".claude" / "switch-model-self-test")
        if out.returncode == 0 or "inside ~/.claude" not in out.stderr:
            problems.append("a root inside ~/.claude was not refused")
        agent = copy / "agents" / "builder.md"
        good = agent.read_bytes()
        agent.write_bytes(good.replace(b"model: claude-", b"model: not-a-pin-"))
        broken = snapshot()
        out = run("--role", "hard-reviewer", "--to", "claude-test-9-9", "--note", "x")
        if out.returncode == 0 or "fails before the switch" not in out.stderr or changed(broken, snapshot()):
            problems.append("a copy whose check.py fails first was not refused, or was written")
        agent.write_bytes(good)

        out = run("--role", "hard-reviewer", "--to", "claude-test-9-9", "--note", "13/19", "--dry-run")
        if out.returncode != 0 or changed(base, snapshot()) or "+model: claude-test-9-9" not in out.stdout:
            problems.append(f"the dry run wrote files or showed no diff: {out.stdout + out.stderr}")

        out = run("--role", "hard-reviewer", "--to", "claude-test-9-9", "--note", "13/19")
        after = snapshot()
        if out.returncode != 0 or changed(base, after) != ["README.md", "agents/hard-reviewer.md", "global/CLAUDE.md"]:
            problems.append(f"the switch changed {changed(base, after)}: {out.stdout + out.stderr}")
        else:
            for rel, removed, added in [("agents/hard-reviewer.md", 1, 1), ("README.md", 1, 1), ("global/CLAUDE.md", 1 + had_switch, 2)]:
                diff = list(difflib.unified_diff(base[rel].decode().splitlines(), after[rel].decode().splitlines(), n=0, lineterm=""))
                minus = [d for d in diff if d.startswith("-") and not d.startswith("---")]
                plus = [d for d in diff if d.startswith("+") and not d.startswith("+++")]
                if (len(minus), len(plus)) != (removed, added) or any(hr_label not in m and hr_id not in m for m in minus):
                    problems.append(f"{rel}: unexpected change {minus} -> {plus}")
            text = after["global/CLAUDE.md"].decode()
            if "- **hard-reviewer** (Test 9.9)" not in text or not re.search(r"^Switch \(\d{4}-\d\d-\d\d\): hard-reviewer → Test 9\.9 \(`claude-test-9-9`\); switch test: 13/19$", text, re.M):
                problems.append("global/CLAUDE.md lacks the new role line or the Switch line")
        out = run("--role", "hard-reviewer", "--to", "claude-test-9-9", "--note", "13/19")
        if out.returncode != 0 or "nothing to change" not in out.stdout or changed(after, snapshot()):
            problems.append("a second identical run changed something")
        out = run("--role", "hard-reviewer", "--to", hr_id, "--note", "back")
        back = snapshot()
        strip = lambda b: re.sub(rb"(?m)^Switch \([^\n]*\n", b"", b)
        if out.returncode != 0 or changed(base, back) != ["global/CLAUDE.md"] or \
                strip(back["global/CLAUDE.md"]) != strip(base["global/CLAUDE.md"]) or f"hard-reviewer → {hr_label}".encode() not in back["global/CLAUDE.md"]:
            problems.append(f"switching back did not restore every file except the Switch line: {changed(base, back)}")

        def restore(state):
            for rel in changed(state, snapshot()):
                (copy / rel).write_bytes(state[rel])

        def main_lines():
            text = (copy / "global" / "CLAUDE.md").read_text(encoding="utf-8")
            readme = (copy / "README.md").read_text(encoding="utf-8")
            found = (re.search(r"^\*\*Current choice \(\d{4}-\d\d-\d\d\): ([^.]+\.\d+)\.\*\*(.*)$", text, re.M),
                     re.search(r"for the main session \(([^:]+): `(\w+)`", text),
                     re.search(r"as a full model ID \(`([^`]+)`\)", text),
                     re.search(r'`"model": "([^"]+)"`, and `(\w+)` effort', readme))
            if not all(found):  # a broken copy: a clean FAIL line, not a traceback
                return (("?", "?"), ("?", "?"), "?", ("?", "?"))
            return found[0].groups(), found[1].groups(), found[2].group(1), found[3].groups()

        out = run("--role", "main", "--to", main_id, "--effort", other_effort, "--note", "effort only")
        if out.returncode != 0 or changed(back, snapshot()) != ["README.md", "global/CLAUDE.md"] or main_lines()[1:] != \
                ((main_label, other_effort), main_id, (main_id, other_effort)) or main_lines()[0][0] != main_label:
            problems.append(f"an effort-only main switch is wrong: {main_lines()} {out.stdout + out.stderr}")
        restore(back)
        out = run("--role", "main", "--to", "claude-test-9-9", "--effort", "high", "--note", "replay: 0 MAJOR")
        if out.returncode != 0 or changed(back, snapshot()) != ["README.md", "global/CLAUDE.md"] or main_lines() != \
                (("Test 9.9", " replay: 0 MAJOR"), ("Test 9.9", "high"), "claude-test-9-9", ("claude-test-9-9", "high")) \
                or "/model claude-test-9-9" not in out.stdout:
            problems.append(f"the main-session switch is wrong: {main_lines()} {out.stdout + out.stderr}")
        restore(back)
        dated_id = re.sub(r"-\d{8}$", "", main_id) + "-20991231"  # a dated ID of today's main model
        cands.write_text(cands.read_text() + f"{dated_id} published 2099-12-31 self-test\n")
        dated = snapshot()
        out = run("--role", "main", "--to", dated_id, "--effort", main_effort, "--note", "dated")
        if out.returncode != 0 or main_lines()[2] != dated_id or main_lines()[3][0] != dated_id:
            problems.append(f"a dated ID of the main session's model was not written: {main_lines()} {out.stdout + out.stderr}")
        restore(dated)
        cands.write_bytes(back["switch-test/candidates.txt"])
        # (a) then (b): hard-reviewer took the candidate; the main session then moves too, with hard-reviewer to Opus
        run("--role", "hard-reviewer", "--to", "claude-test-9-9", "--note", "a")
        moved = snapshot()
        out = run("--role", "main", "--to", "claude-test-9-9", "--effort", "high", "--note", "b")
        if out.returncode == 0 or "in the same command" not in out.stderr or changed(moved, snapshot()):
            problems.append(f"a main session on hard-reviewer's model was not refused with the way out: {out.stderr}")
        out = run("--role", "main", "--to", "claude-test-9-9", "--effort", "high", "--hard-reviewer", main_id, "--note", "b")
        pinned = re.search(r"^model: (\S+)$", (copy / "agents" / "hard-reviewer.md").read_text(encoding="utf-8"), re.M).group(1)
        moved_line = f"hard-reviewer → {main_label} (`{main_id}`); moved with the main session, which must differ"
        if out.returncode != 0 or pinned != main_id or main_lines()[0][0] != "Test 9.9" or \
                moved_line not in (copy / "global" / "CLAUDE.md").read_text(encoding="utf-8"):
            problems.append(f"moving the main session and hard-reviewer in one command failed: {out.stdout + out.stderr}")
        restore(back)
        # an anchor check.py does not guard (the effort entry's "owner decision" date) is missing: refused, nothing written
        (copy / "global" / "CLAUDE.md").write_bytes(re.sub(rb", owner decision \d{4}-\d\d-\d\d\)", b")", back["global/CLAUDE.md"], count=1))
        odd = snapshot()
        out = run("--role", "main", "--to", "claude-test-9-9", "--effort", "high", "--note", "x")
        if out.returncode == 0 or "expected exactly one match, found 0" not in out.stderr or changed(odd, snapshot()):
            problems.append(f"a missing anchor did not refuse the whole switch: {out.stdout + out.stderr}")
        (copy / "global" / "CLAUDE.md").write_bytes(back["global/CLAUDE.md"])

        checker = copy / "scripts" / "check.py"  # a check that fails only after the edit: everything restored
        checker.write_text(checker.read_text(encoding="utf-8").replace(
            'if "Current choice" not in global_md:', 'if "Test 9.9" in global_md:\n    fail("planted")\nif "Current choice" not in global_md:', 1))
        planted = snapshot()
        out = run("--role", "hard-reviewer", "--to", "claude-test-9-9", "--note", "x")
        if out.returncode == 0 or "restored" not in out.stderr or changed(planted, snapshot()):
            problems.append("a check failing after the edit did not restore every file")
    if problems:
        print("FAIL\n" + "\n".join(f"- {p}" for p in problems))
        sys.exit(1)
    print("PASS: refusals with their reasons (guessed ID, hard-reviewer on the main model, empty note, unknown role, "
          "main on hard-reviewer's model or without effort, --hard-reviewer without main, ~/.claude root, failing check "
          "first), dry run, the four-line switch, rerun no-op, switch back, effort-only and full main-session switches, "
          "main and hard-reviewer moved together, a missing anchor, restore after a failing check")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--role", choices=[*ROLES, "main"])
    parser.add_argument("--to", help="full model ID: pinned by an agent or listed in switch-test/candidates.txt")
    parser.add_argument("--note", help="the switch test's numbers, written into global/CLAUDE.md")
    parser.add_argument("--effort", choices=EFFORTS, help="--role main only: the owner's effort for the main session")
    parser.add_argument("--hard-reviewer", metavar="ID", help="--role main only: move hard-reviewer in the same edit "
                        "(it must differ from the main session)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", type=Path, default=REPO, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not (args.role and args.to and args.note is not None):
        parser.error("--role, --to and --note are required")
    try:
        if args.effort and args.role != "main":
            raise Refused("--effort goes with --role main; an agent's effort: is edited by hand")
        if args.hard_reviewer and args.role != "main":
            raise Refused("--hard-reviewer goes with --role main; for hard-reviewer alone use --role hard-reviewer")
        moves = [(args.role, args.to)] + ([("hard-reviewer", args.hard_reviewer)] if args.hard_reviewer else [])
        switch(args.root, moves, args.note, args.effort, args.dry_run)
    except Refused as why:
        print(f"refused: {why}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
