#!/usr/bin/env python3
"""Draws a repo's diagrams with ambysto-graph, including where the current plan stands. No LLM tokens; read-only on the repo.

  python scripts/progress-diagram.py [<repo>] [--plan <plan.md>] [--base <ref>]
  python scripts/progress-diagram.py --self-test

Writes into the repo's git folder (`<git dir>/progress-diagram/`), which git never commits, and prints each path:
  architecture.html  modules and their links (`ambysto-graph render --auto`)
  delta.html         what this branch changed since the merge base with --base (default origin/main, else main)
  progress.html      with --plan: one card per task of the plan's `## Tasks` (its files changed on this branch, not
                     yet, or not needed) and one per `## Proof` item with its Result (PASS, FAIL, not run, none yet);
                     the plan's status line is the subtitle
Run it again whenever the work moves (a task done, a proof run, a status change): each run replaces the files.
Task progress uses the same rule as `sdlc-check.py converge`: a task has started when a path changed on this branch
falls inside its `allow` and outside its `forbid`.
Exit 0 written, 1 ambysto-graph failed, 2 usage, not a git work tree, ambysto-graph missing or a plan it cannot read.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


class Stop(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def sdlc():
    spec = importlib.util.spec_from_file_location("sdlc_check", HERE / "sdlc-check.py")
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
        raise Stop(2, f"git {' '.join(args)}: {out.stderr.strip()}")
    return out.stdout.strip()


def progress_ir(plan_path, top, base):
    """The workflow diagram (ambysto-graph's typed IR) of a plan's tasks and proof items."""
    s = sdlc()
    try:
        text = plan_path.read_text(encoding="utf-8")
        tasks = s.parse_tasks(text)
        base, paths = s.changed_paths(top, base)
        proof = s.numbered(s.section(text, "Proof"), "Proof")
        result = s.numbered(s.section(text, "Result"), "Result")
    except (OSError, UnicodeDecodeError) as error:
        raise Stop(2, f"cannot read {plan_path}: {error}") from None
    except s.Malformed as error:
        raise Stop(2, f"{plan_path.name}: {error}") from None
    if tasks is None:
        raise Stop(2, f"{plan_path.name} has no `## Tasks` section; nothing to draw")
    status = next((m[1].strip() for m in (re.match(r"^status:\s*([^#]*)", l) for l in text.splitlines()) if m), "not set")
    in_contract = s.guard().in_contract
    nodes, edges, started = [], [], 0
    for i, t in enumerate(tasks):
        mine = [] if t["not_needed"] else [p for p in paths if in_contract(p, {"allow": t["allow"], "forbid": t["forbid"]})]
        if t["not_needed"]:
            badge, delta = "not needed", None
        elif mine:
            badge, delta = f"started: {len(mine)} file(s) changed", "modified"
            started += 1
        else:
            badge, delta = "not started", "unchanged"
        node = {"id": t["id"].lower(), "label": f"{t['id']} {t['title']}"[:70], "boundary": "tasks", "row": i, "col": 0,
                "sublabel": t["who"] + (", parallel" if t["parallel"] else ""), "badges": [badge],
                "items": [{"name": p} for p in mine[:6]] + ([{"name": f"… {len(mine) - 6} more"}] if len(mine) > 6 else [])}
        if delta:
            node["delta"] = delta
        nodes.append(node)
        if i and not t["parallel"]:  # a parallel task does not wait for the one before it
            edges.append({"from": tasks[i - 1]["id"].lower(), "to": t["id"].lower(), "kind": "next"})
    for j, n in enumerate(sorted(proof)):
        r = result.get(n, "")
        if not r:
            verdict = "no result yet"
        elif not s.RESULT.match(r):  # converge's own rule: "not run" needs its reason
            verdict = "result not in the format"
        else:
            verdict = next(v for v in ("PASS", "FAIL", "not run") if r.startswith(v))
        nodes.append({"id": f"proof{n}", "label": f"Proof {n}: {proof[n]}"[:70], "boundary": "proof", "row": j, "col": 1,
                      "badges": [verdict], "items": [{"name": r[:120]}] if r else []})
    live = sum(1 for t in tasks if not t["not_needed"])
    passed = sum(1 for n in proof if result.get(n, "").startswith("PASS"))
    return {
        "mode": "workflow",
        "title": f"Progress: {plan_path.name}",
        "subtitle": f"status: {status} · {started}/{live} tasks started · {passed}/{len(proof)} proof items PASS · "
                    f"{len(paths)} path(s) changed since {base}",
        "boundaries": [{"id": "tasks", "label": "Tasks"}, {"id": "proof", "label": "Proof"}],
        "nodes": nodes,
        "edges": edges,
    }


def render(binary, args):
    try:
        out = subprocess.run([binary, "render", *args], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise Stop(1, f"ambysto-graph render {' '.join(args[:2])} took over 600 s; run it under a memory cap on a big repo") from None
    if out.returncode != 0:
        raise Stop(1, f"ambysto-graph render {' '.join(args[:2])} failed: {(out.stderr or out.stdout).strip()[:400]}")


def main(argv):
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__.strip())
        return 0
    positional, opts, i = [], {}, 0
    while i < len(argv):
        if argv[i] in ("--plan", "--base"):
            if i + 1 >= len(argv):
                raise Stop(2, f"{argv[i]} needs a value")
            opts[argv[i]] = argv[i + 1]
            i += 2
        elif argv[i].startswith("-"):
            raise Stop(2, f"unknown option {argv[i]}")
        else:
            positional.append(argv[i])
            i += 1
    if len(positional) > 1:
        raise Stop(2, "one repo at most")
    binary = shutil.which("ambysto-graph")
    if not binary:
        raise Stop(2, "ambysto-graph is not on PATH")
    top = Path(git(Path(positional[0] if positional else "."), "rev-parse", "--show-toplevel")).resolve()
    out_dir = Path(git(top, "rev-parse", "--absolute-git-dir")) / "progress-diagram"
    base = opts.get("--base")
    if base is None:
        base = next((r for r in ("origin/main", "main") if subprocess.run(
            ["git", "-C", str(top), "rev-parse", "-q", "--verify", r + "^{commit}"], capture_output=True).returncode == 0), None)
        if base is None:
            raise Stop(2, "no origin/main or main to compare with; pass --base")
    ir = progress_ir(Path(opts["--plan"]).resolve(), top, base) if "--plan" in opts else None
    out_dir.mkdir(parents=True, exist_ok=True)
    if ir is None:  # each run replaces the set: no progress from an earlier plan is left to mislead
        for stale in ("progress.html", "progress.json"):
            (out_dir / stale).unlink(missing_ok=True)
    written = []
    render(binary, ["--auto", str(top), "-o", str(out_dir / "architecture.html")])
    written.append(out_dir / "architecture.html")
    merge_base = git(top, "merge-base", base, "HEAD")
    render(binary, ["--auto", str(top), "--mode", "delta", "--diff", merge_base, "-o", str(out_dir / "delta.html")])
    written.append(out_dir / "delta.html")
    if ir is not None:
        ir_file = out_dir / "progress.json"
        ir_file.write_text(json.dumps(ir, indent=1, ensure_ascii=False), encoding="utf-8")
        render(binary, [str(ir_file), "--repo-root", str(top), "-o", str(out_dir / "progress.html")])
        written.append(out_dir / "progress.html")
        print(ir["subtitle"])
    for path in written:
        print(path)
    return 0


def self_test():
    failures = []
    if not shutil.which("ambysto-graph"):
        print("not run: ambysto-graph is not on PATH")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["XDG_CACHE_HOME"] = str(Path(tmp) / "cache")  # ambysto-graph's index of the scratch repo goes here
        repo = Path(tmp) / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "intent").mkdir()
        run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True)
        run("init", "-q", "-b", "main")
        (repo / "src" / "app.py").write_text("def main():\n    return helper()\n\n\ndef helper():\n    return 1\n", encoding="utf-8")
        (repo / "README.md").write_text("# demo\n", encoding="utf-8")
        run("add", ".")
        run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        run("switch", "-q", "-c", "work")
        (repo / "src" / "app.py").write_text("def main():\n    return helper() + 1\n\n\ndef helper():\n    return 1\n", encoding="utf-8")
        plan = repo / "intent" / "demo.plan.md"
        plan.write_text("---\nstatus: building # draft → planned → building → verified\n---\n# Demo\n\n## Tasks\n\n"
                        "### T1 (builder) Change the app\n- allow: `src/**`\n- check: `python3 -m pytest`\n\n"
                        "### T2 (main, parallel) Docs\n- allow: `docs/**`\n- check: `true`\n\n"
                        "### T3 (builder) Old part\n- allow: `old/**`\n- check: `true`\n- not needed: dropped\n\n"
                        "## Proof\n\n1. tests pass\n2. docs read well\n3. on Windows\n\n## Result\n\n1. PASS 3 tests\n3. not run\n", encoding="utf-8")
        out = subprocess.run([sys.executable, __file__, str(repo), "--plan", str(plan), "--base", "main"],
                             capture_output=True, text=True, timeout=600)
        gitdir = repo / ".git" / "progress-diagram"
        if out.returncode != 0:
            failures.append(f"render: exit {out.returncode}: {out.stdout.strip()} {out.stderr.strip()}")
        for name in ("architecture.html", "delta.html", "progress.html"):
            f = gitdir / name
            if not f.is_file() or not f.read_text(encoding="utf-8", errors="replace").lstrip().lower().startswith("<!doctype html"):
                failures.append(f"{name} not written as HTML")
        ir = json.loads((gitdir / "progress.json").read_text(encoding="utf-8")) if (gitdir / "progress.json").is_file() else {}
        badges = {n["id"]: n["badges"][0] for n in ir.get("nodes", [])}
        want = {"t1": "started: 1 file(s) changed", "t2": "not started", "t3": "not needed", "proof1": "PASS", "proof2": "no result yet",
                "proof3": "result not in the format"}
        if badges != want:
            failures.append(f"badges {badges}, expected {want}")
        if [(e["from"], e["to"]) for e in ir.get("edges", [])] != [("t2", "t3")]:
            failures.append(f"edges {ir.get('edges')}: T2 is parallel, so only T2 -> T3 is expected")
        if "status: building · 1/2 tasks started · 1/3 proof items PASS" not in ir.get("subtitle", ""):
            failures.append(f"subtitle {ir.get('subtitle')!r}")
        status = sorted(l.strip() for l in run("status", "--porcelain", "-uall").stdout.splitlines())
        if status != ["?? intent/demo.plan.md", "M src/app.py"]:  # the test's own edits only: the script wrote nothing there
            failures.append(f"the work tree changed: {status!r}")
        bad = subprocess.run([sys.executable, __file__, str(repo), "--plan", str(repo / "README.md"), "--base", "main"],
                             capture_output=True, text=True, timeout=120)
        if bad.returncode != 2 or "no `## Tasks`" not in bad.stderr:
            failures.append(f"a plan without tasks: exit {bad.returncode}, {bad.stderr.strip()!r}")
        again = subprocess.run([sys.executable, __file__, str(repo), "--base", "main"], capture_output=True, text=True, timeout=600)
        if again.returncode != 0 or (gitdir / "progress.html").exists():
            failures.append(f"a run without --plan: exit {again.returncode}, old progress.html left: {(gitdir / 'progress.html').exists()}")
        outside = subprocess.run([sys.executable, __file__, tmp], capture_output=True, text=True, timeout=120)
        if outside.returncode != 2:
            failures.append(f"not a git tree: exit {outside.returncode}")
        unknown = subprocess.run([sys.executable, __file__, str(repo), "--bogus"], capture_output=True, text=True, timeout=120)
        if unknown.returncode != 2:
            failures.append(f"unknown option: exit {unknown.returncode}")
    print("FAIL\n" + "\n".join(failures) if failures else "PASS: progress-diagram self-test")
    return 1 if failures else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    try:
        sys.exit(main(sys.argv[1:]))
    except Stop as stop:
        print(f"progress-diagram: {stop}", file=sys.stderr)
        sys.exit(stop.code)
