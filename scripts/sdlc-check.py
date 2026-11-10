#!/usr/bin/env python3
"""Checks the sdlc chain's artifacts (APS-51).

    python3 scripts/sdlc-check.py clarify <intent.md>
    python3 scripts/sdlc-check.py converge <plan.md> [--base <ref>]
    python3 scripts/sdlc-check.py --self-test

`clarify` fails while the intent still has a `[NEEDS CLARIFICATION: …]` marker, or its `## Open questions` section
is missing or does not begin with `None`. Run it before the intent goes to `approved`, and again before the plan.

`converge` compares a plan with its branch: the paths changed since the merge base with `--base` (default
`origin/main`, else `main`), the working tree and untracked files included. Each gap is one line:
  - a changed path that no task allows (agent-guard's own rule: inside `allow`, outside `forbid`), other than the
    plan and its intent;
  - a task, not marked `not needed`, whose `allow` matches no changed path;
  - a Proof item with no Result item, or a Result item that does not begin with PASS, FAIL or `not run: <reason>`.
A plan with no `## Tasks` section has nothing to compare: it is reported and passes, so older plans stay valid.

The formats are in the sdlc skill (`skills/sdlc/SKILL.md`). `dispatch.py --task` reads tasks with `parse_tasks`
here. Exit 0: pass; 1: a gap or a marker; 2: the file cannot be read as the format says (nothing is guessed).
It never edits a file. Standard library only.
"""
import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADING = re.compile(r"^### (T\d+) \((builder|main)(, parallel)?\) (\S.*)$")
TICKED = re.compile(r"`([^`]+)`")
RESULT = re.compile(r"^(PASS|FAIL|not run: \S)")


class Malformed(Exception):
    pass


def sections(text):
    """`## ` heading line → its lines (up to the next `## `), in order; fenced code blocks are not headings."""
    out, name, fenced = [], None, False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            name = line[3:].strip()
            out.append((name, []))
        elif name is not None:
            out[-1][1].append(line)
    return out


def section(text, name):
    """The lines of `## <name>`, also when the heading goes on (`## Result (2026-11-10)`); None if absent."""
    found = [lines for title, lines in sections(text) if title == name or title.startswith(name + " ")]
    if len(found) > 1:
        raise Malformed(f"more than one `## {name}` section")
    return found[0] if found else None


def ticked_only(value, what):
    globs = TICKED.findall(value)
    if not globs or TICKED.sub("", value).strip():
        raise Malformed(f"{what}: write each glob in backticks, separated by spaces, and nothing else: {value!r}")
    return globs


def parse_tasks(text):
    """The plan's tasks as dicts (id, who, parallel, title, allow, forbid, checks, not_needed), or None without a
    `## Tasks` section. A line the format does not know is refused, never skipped."""
    lines = section(text, "Tasks")
    if lines is None:
        return None
    tasks, task = [], None
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("###"):
            m = HEADING.match(line)
            if not m:
                raise Malformed(f"task heading not in the form `### T<n> (builder|main[, parallel]) <title>`: {line!r}")
            task = {"id": m[1], "who": m[2], "parallel": bool(m[3]), "title": m[4].strip(), "allow": [],
                    "forbid": [], "checks": [], "not_needed": None}
            tasks.append(task)
            continue
        if task is None:
            continue  # prose before the first task
        m = re.match(r"^- (allow|forbid|check|not needed): (.*\S)\s*$", line)
        if not m:
            raise Malformed(f"{task['id']}: a line the format does not know: {line!r}")
        key, value = m[1], m[2]
        if key in ("allow", "forbid"):
            task[key] += ticked_only(value, f"{task['id']} {key}")
        elif key == "check":
            c = re.fullmatch(r"`(.+)`", value)
            if not c or not c[1].strip() or re.search(r"`\s+`", c[1]):
                raise Malformed(f"{task['id']}: one command per `check`, in backticks: {value!r}")
            task["checks"].append(c[1])
        else:
            task["not_needed"] = value
    ids = [t["id"] for t in tasks]
    for t in tasks:
        if ids.count(t["id"]) > 1:
            raise Malformed(f"task id {t['id']} is used twice")
        if not t["allow"]:
            raise Malformed(f"{t['id']} has no `allow`")
        if not t["checks"]:
            raise Malformed(f"{t['id']} has no `check`")
    if not tasks:
        raise Malformed("the `## Tasks` section has no task")
    return tasks


def numbered(lines, what):
    items = {}
    for m in (re.match(r"^(\d+)\. (.*)$", l) for l in lines or []):
        if m and int(m[1]) in items:
            raise Malformed(f"`## {what}` item {m[1]} is numbered twice")
        if m:
            items[int(m[1])] = m[2]
    return items


def clarify(text):
    """Markers outside code (a backticked span or a fenced block names the marker, it does not use it)."""
    gaps, fenced = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and "[NEEDS CLARIFICATION" in re.sub(r"`[^`]*`", "", line):
            gaps.append(f"line {n}: {line.strip()}")
    lines = section(text, "Open questions")
    if lines is None:
        gaps.append("no `## Open questions` section")
    else:
        first = next((l.strip() for l in lines if l.strip()), "")
        if not re.match(r"None\b", first):
            gaps.append(f"`## Open questions` does not begin with `None`: {first[:80]!r}")
        elif any(re.match(r"\s*(?:[-*]|\d+\.) ", l) for l in lines):
            gaps.append("`## Open questions` begins with `None` but lists questions under it")
    return gaps


def guard():
    spec = importlib.util.spec_from_file_location("agent_guard", ROOT / "hooks" / "agent-guard.py")
    module = importlib.util.module_from_spec(spec)
    dont = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = dont
    return module


def git(top, *args):
    out = subprocess.run(["git", "-C", str(top), *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise Malformed(f"git {' '.join(args)}: {out.stderr.strip()}")
    return out.stdout


def changed_paths(top, base):
    if base is None:
        refs = [r for r in ("origin/main", "main")
                if subprocess.run(["git", "-C", str(top), "rev-parse", "-q", "--verify", r + "^{commit}"],
                                  capture_output=True).returncode == 0]
        if not refs:
            raise Malformed("no origin/main or main to compare with; pass --base")
        base = refs[0]
    mb = git(top, "merge-base", base, "HEAD").strip()
    paths = set(git(top, "-c", "core.quotePath=false", "diff", "--name-only", "--no-renames", mb).splitlines())
    paths |= set(git(top, "-c", "core.quotePath=false", "ls-files", "--others", "--exclude-standard").splitlines())
    return base, sorted(p for p in paths if p)


def converge(plan_path, base=None):
    """(notes, gaps) for a plan file in a git work tree."""
    plan_path = Path(plan_path).resolve()
    text = plan_path.read_text(encoding="utf-8")
    tasks = parse_tasks(text)
    if tasks is None:
        return [f"{plan_path.name}: no `## Tasks` section; nothing to compare"], []
    top = Path(git(plan_path.parent, "rev-parse", "--show-toplevel").strip()).resolve()
    base, paths = changed_paths(top, base)
    own = {plan_path.relative_to(top).as_posix()}
    if plan_path.name.endswith(".plan.md"):
        own.add(plan_path.relative_to(top).as_posix()[: -len(".plan.md")] + ".md")
    in_contract = guard().in_contract
    live = [t for t in tasks if not t["not_needed"]]
    contracts = {t["id"]: {"allow": t["allow"], "forbid": t["forbid"]} for t in live}
    notes, gaps = [f"{len(paths)} changed path(s) since the merge base with {base}"], []
    for p in paths:
        if p not in own and not any(in_contract(p, c) for c in contracts.values()):
            gaps.append(f"outside every task: {p}")
    for t in tasks:
        if t["not_needed"]:
            notes.append(f"{t['id']} not needed: {t['not_needed']}")
        elif not any(in_contract(p, contracts[t["id"]]) for p in paths):
            gaps.append(f"{t['id']} ({t['title']}) changed none of its files")
    proof = numbered(section(text, "Proof"), "Proof")
    result = numbered(section(text, "Result"), "Result")
    if not proof:
        gaps.append("no numbered `## Proof` items")
    for n in sorted(proof):
        if n not in result:
            gaps.append(f"proof {n} has no result")
        elif not RESULT.match(result[n]):
            gaps.append(f"result {n} does not begin with PASS, FAIL or `not run: <reason>`: {result[n][:60]!r}")
        elif result[n].startswith("FAIL"):
            notes.append(f"proof {n} recorded FAIL")
    for n in sorted(set(result) - set(proof)):
        gaps.append(f"result {n} has no proof item")
    return notes, gaps


def self_test():
    failures = []

    def expect(name, got, want):
        if got != want:
            failures.append(f"{name}: got {got!r}, want {want!r}")

    def refused(name, fn):
        try:
            fn()
            failures.append(f"{name}: not refused")
        except Malformed:
            pass

    expect("clarify clean", clarify("# I\n\n## Open questions\n\nNone.\n"), [])
    expect("clarify marker", len(clarify("Do [NEEDS CLARIFICATION: which?]\n## Open questions\nNone.\n")), 1)
    expect("clarify open", len(clarify("## Open questions\n\n1. Which account?\n")), 1)
    expect("clarify missing", clarify("# I\n"), ["no `## Open questions` section"])
    expect("clarify None then a list", len(clarify("## Open questions\nNone, but:\n- which account?\n")), 1)
    expect("clarify Nonetheless", len(clarify("## Open questions\nNonetheless, one thing.\n")), 1)
    expect("clarify None with a reason", clarify("## Open questions\nNone. Decided by the owner on 2026-11-10.\n"), [])
    expect("clarify fenced heading", len(clarify("```\n## Open questions\nNone\n```\n")), 1)
    expect("clarify named in code", clarify("Mark it as `[NEEDS CLARIFICATION: q]`.\n```\n[NEEDS CLARIFICATION: x]\n```\n"
                                            "## Open questions\nNone.\n"), [])

    task = "### T1 (builder, parallel) Build a\n- allow: `src/**` `README.md`\n- forbid: `src/x.py`\n- check: `make test`\n"
    expect("parse", parse_tasks(f"## Tasks\n\n{task}\n## Steps\n"),
           [{"id": "T1", "who": "builder", "parallel": True, "title": "Build a", "allow": ["src/**", "README.md"],
             "forbid": ["src/x.py"], "checks": ["make test"], "not_needed": None}])
    expect("no tasks", parse_tasks("## Steps\n1. x\n"), None)
    expect("check keeps inner text", parse_tasks("## Tasks\n### T2 (main) M\n- allow: `a`\n- check: `sh -c 'x | y'`\n")[0]["checks"],
           ["sh -c 'x | y'"])
    refused("unknown bullet", lambda: parse_tasks(f"## Tasks\n{task}- files: `x`\n"))
    refused("bad heading", lambda: parse_tasks("## Tasks\n### Task one\n- allow: `a`\n- check: `x`\n"))
    refused("untick glob", lambda: parse_tasks("## Tasks\n### T1 (main) M\n- allow: src/**\n- check: `x`\n"))
    refused("text beside globs", lambda: parse_tasks("## Tasks\n### T1 (main) M\n- allow: `a` and `b`\n- check: `x`\n"))
    refused("no allow", lambda: parse_tasks("## Tasks\n### T1 (main) M\n- check: `x`\n"))
    refused("no check", lambda: parse_tasks("## Tasks\n### T1 (main) M\n- allow: `a`\n"))
    refused("duplicate id", lambda: parse_tasks(f"## Tasks\n{task}{task}"))
    refused("empty section", lambda: parse_tasks("## Tasks\nprose only\n"))
    refused("two sections", lambda: parse_tasks(f"## Tasks\n{task}## Tasks\n{task}"))
    refused("two commands in one check", lambda: parse_tasks("## Tasks\n### T1 (main) M\n- allow: `a`\n- check: `make test` `make lint`\n"))
    expect("Tasks heading that goes on", parse_tasks(f"## Tasks (dispatch)\n{task}")[0]["id"], "T1")
    refused("a proof number twice", lambda: numbered(["1. a", "1. b"], "Proof"))

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        run = lambda *a: subprocess.run(["git", "-C", tmp, *a], check=True, capture_output=True)
        run("init", "-q", "-b", "main")
        run("config", "user.email", "t@example.com")
        run("config", "user.name", "t")
        (repo / "intent").mkdir()
        (repo / "README.md").write_text("r\n")
        run("add", ".")
        run("commit", "-qm", "base")
        run("checkout", "-qb", "work")
        plan = repo / "intent" / "x.plan.md"
        tasks = ("## Tasks\n### T1 (builder) A\n- allow: `src/**`\n- forbid: `src/secret.py`\n- check: `t`\n"
                 "### T2 (main) B\n- allow: `docs/*.md`\n- check: `t`\n")
        proof = "## Proof\n1. tests\n2. build\n"
        plan.write_text(tasks + proof + "## Result\n1. PASS 3 tests\n2. not run: no build here\n")
        (repo / "intent" / "x.md").write_text("i\n")
        (repo / "src" / "deep").mkdir(parents=True)
        (repo / "src" / "deep" / "a.py").write_text("a\n")
        (repo / "docs").mkdir()
        (repo / "docs" / "n.md").write_text("n\n")
        run("add", ".")
        run("commit", "-qm", "work")
        notes, gaps = converge(plan)
        expect("converge clean", gaps, [])
        (repo / "src" / "secret.py").write_text("s\n")  # untracked, inside allow but forbidden
        (repo / "README.md").write_text("changed\n")    # uncommitted, outside every task
        expect("converge outside", sorted(converge(plan)[1]),
               ["outside every task: README.md", "outside every task: src/secret.py"])
        run("checkout", "-q", "--", "README.md")
        (repo / "src" / "secret.py").unlink()
        plan.write_text(tasks + "### T3 (main) C\n- allow: `web/**`\n- check: `t`\n" + proof + "## Result\n1. PASS\n")
        expect("converge untouched task and missing result", sorted(converge(plan)[1]),
               ["T3 (C) changed none of its files", "proof 2 has no result"])
        plan.write_text(tasks + "### T3 (main) C\n- allow: `web/**`\n- check: `t`\n- not needed: merged into T2\n"
                        + proof + "## Result (2026-11-10)\n1. FAIL 1 test\n2. done\n3. PASS\n")
        notes, gaps = converge(plan)
        expect("converge result words", sorted(gaps),
               ["result 2 does not begin with PASS, FAIL or `not run: <reason>`: 'done'", "result 3 has no proof item"])
        expect("converge notes", [n for n in notes if not n[0].isdigit()],
               ["T3 not needed: merged into T2", "proof 1 recorded FAIL"])
        old = repo / "intent" / "old.plan.md"
        old.write_text("## Steps\n1. x\n## Proof\n1. y\n")
        expect("converge old plan", converge(old)[1], [])

    if failures:
        print("FAIL: sdlc-check self-test\n  " + "\n  ".join(failures))
        return 1
    print("PASS: sdlc-check self-test (clarify, the task parser and its refusals, converge on a scratch repo)")
    return 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if len(argv) == 2 and argv[0] == "clarify":
        cmd = "clarify"
    elif argv[:1] == ["converge"] and (len(argv) == 2 or (len(argv) == 4 and argv[2] == "--base")):
        cmd = "converge"
    else:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        if cmd == "clarify":
            gaps = clarify(Path(argv[1]).read_text(encoding="utf-8"))
            notes = []
        else:
            notes, gaps = converge(argv[1], argv[3] if len(argv) == 4 else None)
    except (Malformed, OSError, UnicodeDecodeError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    for line in notes:
        print(line)
    for line in gaps:
        print(f"gap: {line}")
    print(f"{'FAIL' if gaps else 'PASS'}: {cmd} {argv[1]}, {len(gaps)} gap(s)")
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
