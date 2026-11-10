#!/usr/bin/env python3
"""Prepares a builder dispatch: a worktree and the task contract the builder works to.

    python3 scripts/dispatch.py new <repo> <branch> --allow <glob>... [--forbid <glob>...] --check <cmd> [--check <cmd>]
    python3 scripts/dispatch.py contract <tree> --allow <glob>... [--forbid <glob>...] --check <cmd> [...]
    python3 scripts/dispatch.py new <repo> <branch> --task <plan.md> <id>      (also `contract <tree> --task …`)
    python3 scripts/dispatch.py show <tree>
    python3 scripts/dispatch.py done <tree>
    python3 scripts/dispatch.py --self-test

`new` adds a worktree `<repo>-<slug>` beside the repo, on a new branch from the repo's HEAD (slug: the branch name
without a leading ticket prefix such as `abc-12-`), and writes its contract. `contract` writes or replaces the contract of an existing
tree (one builder in the main checkout, or a wider task for a second round; never while a builder runs there).
The contract is `agent-contract.json` in the tree's git folder (scripts/contract.py reads it): the builder
edits only inside `allow` and outside `forbid` and names every check in its report. Nothing here blocks a write; the
main session holds the builder to it by running `sdlc-check.py converge` on the diff and rerunning the checks. `--task <plan> <id>` takes allow, forbid and checks from that `(builder)` task in the plan's `## Tasks` section
(read by `sdlc-check.py`'s parser; the formats are in the sdlc skill) instead of flags typed by hand, and refuses
flags beside it, an unknown id, a `(main)` task and a `not needed` one. `done` removes the contract, and a linked worktree too
when nothing in it is uncommitted; the branch stays. Run `done` from the repo, not from inside the worktree (Windows
will not delete a folder that is a process's working folder; the remove is then refused and both stay). It never
commits, pushes or touches ~/.claude. Standard library only.
"""
import argparse
import datetime
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CONTRACT_NAME = "agent-contract.json"  # the same name scripts/contract.py reads


class Refused(Exception):
    pass


def git(cwd, *args, check=True):
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        raise Refused(f"git {' '.join(args)} failed in {cwd}: {out.stderr.strip()}")
    return out.stdout.strip() if out.returncode == 0 else None


def top_of(path):
    path = Path(path).expanduser().resolve()
    claude = (Path.home() / ".claude").resolve()
    if path == claude or claude in path.parents:
        raise Refused(f"{path} is inside ~/.claude; a builder never works there")
    if not path.is_dir():
        raise Refused(f"{path} is not a folder")
    top = git(path, "rev-parse", "--show-toplevel", check=False)
    if not top:
        raise Refused(f"{path} is not in a git work tree")
    return Path(top).resolve()


def contract_path(top):
    return Path(git(top, "rev-parse", "--absolute-git-dir")) / CONTRACT_NAME


def is_main_checkout(top):
    common = Path(git(top, "rev-parse", "--git-common-dir"))
    common = common if common.is_absolute() else (top / common)
    return common.resolve() == Path(git(top, "rev-parse", "--absolute-git-dir")).resolve()


def check_globs(globs, what):
    for g in globs:
        parts = g.replace("\\", "/").split("/")
        if not g.strip():
            raise Refused(f"an empty {what} glob")
        if g.startswith(("/", "\\", "~")) or re.match(r"^[A-Za-z]:", g):
            raise Refused(f"{what} glob {g!r} is absolute; globs are relative to the tree")
        if ".." in parts:
            raise Refused(f"{what} glob {g!r} steps out of the tree with '..'")
        if parts[0].lower() == ".git":
            raise Refused(f"{what} glob {g!r} names the git folder, which a builder never writes")


def write_contract(top, task, allow, forbid, checks):
    if not allow:
        raise Refused("--allow is empty: name the paths the builder may change")
    if not checks or not all(c.strip() for c in checks):
        raise Refused("--check is empty: name the commands the builder must run (the project's Verify for this task)")
    check_globs(allow, "--allow")
    check_globs(forbid, "--forbid")
    path = contract_path(top)
    old = path.read_text(encoding="utf-8") if path.exists() else None
    data = {"version": 1, "task": task, "allow": allow, "forbid": forbid, "checks": checks,
            "written": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")}
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".agent-contract-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)
    return old, data


def brief(top, data):
    forbid = f"; never {', '.join(data['forbid'])}" if data["forbid"] else ""
    return (f"Give the builder:\n"
            f"  Work only in {top} (`cd {top}` first; give paths under it).\n"
            f"  Your task contract: you may change {', '.join(data['allow'])}"
            f"{forbid}. Run each check and name it verbatim in your report with its result: "
            + "; ".join(f"`{c}`" for c in data["checks"]) + ".\n"
            "Allow every file a check or formatter rewrites (lock files, snapshots, generated code), or the diff "
            "falls outside the contract. Afterwards rerun the checks yourself, then `dispatch.py done` once the work is committed.")


def load_sdlc():
    path = Path(__file__).resolve().parent / "sdlc-check.py"
    if not path.is_file():
        raise Refused(f"--task needs {path}, which is missing")
    spec = importlib.util.spec_from_file_location("sdlc_check", path)
    module = importlib.util.module_from_spec(spec)
    dont = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = dont
    return module


def task_terms(args):
    """(allow, forbid, checks, task id or None): from the flags, or from one builder task of a plan with --task."""
    if not args.task:
        return args.allow or [], args.forbid or [], args.check, None
    if args.allow or args.forbid or args.check:
        raise Refused("--task takes allow, forbid and checks from the plan; drop --allow, --forbid and --check")
    plan, tid = args.task
    sdlc = load_sdlc()
    try:
        tasks = sdlc.parse_tasks(Path(plan).read_text(encoding="utf-8"))
    except (sdlc.Malformed, OSError, UnicodeDecodeError) as e:
        raise Refused(f"{plan}: {e}")
    if tasks is None:
        raise Refused(f"{plan} has no `## Tasks` section")
    task = next((t for t in tasks if t["id"] == tid), None)
    if task is None:
        raise Refused(f"{plan} has no task {tid} (it has {', '.join(t['id'] for t in tasks)})")
    if task["who"] != "builder":
        raise Refused(f"{tid} is a ({task['who']}) task: the main session does it, no builder contract")
    if task["not_needed"]:
        raise Refused(f"{tid} is marked not needed: {task['not_needed']}")
    return task["allow"], task["forbid"], task["checks"], tid


def cmd_new(args):
    allow, forbid, checks, tid = task_terms(args)
    repo = top_of(args.repo)
    if git(repo, "check-ref-format", "--branch", args.branch, check=False) is None:
        raise Refused(f"{args.branch!r} is not a valid branch name")
    if git(repo, "rev-parse", "-q", "--verify", f"refs/heads/{args.branch}", check=False):
        raise Refused(f"branch {args.branch} already exists; pick a new one, or use `contract` on its tree")
    slug = re.sub(r"^[a-z]+-\d+-", "", args.branch, flags=re.I).replace("/", "-")
    target = repo.parent / f"{repo.name}-{slug}"
    if target.exists():
        raise Refused(f"{target} already exists")
    check_globs(allow, "--allow")
    check_globs(forbid, "--forbid")
    if not allow or not checks:
        raise Refused("--allow and --check are both needed")
    git(repo, "worktree", "add", "-q", "-b", args.branch, str(target), "HEAD")
    try:
        _, data = write_contract(target.resolve(), f"{args.branch} {tid}" if tid else args.branch, allow, forbid, checks)
    except BaseException:  # a refusal or an OSError (an unwritable git folder): leave nothing behind
        git(repo, "worktree", "remove", "--force", str(target), check=False)
        git(repo, "branch", "-D", args.branch, check=False)
        raise
    print(f"worktree {target} on branch {args.branch} (from {git(repo, 'rev-parse', '--short', 'HEAD')}), "
          f"contract {contract_path(target.resolve())}")
    print(brief(target.resolve(), data))


def cmd_contract(args):
    allow, forbid, checks, tid = task_terms(args)
    top = top_of(args.tree)
    branch = git(top, "branch", "--show-current") or "detached"
    old, data = write_contract(top, f"{branch} {tid}" if tid else branch, allow, forbid, checks)
    print(f"contract {contract_path(top)}: " + ("replaced; it was:\n" + old if old else "written"))
    print(brief(top, data))


def cmd_show(args):
    top = top_of(args.tree)
    path = contract_path(top)
    print(path.read_text(encoding="utf-8").rstrip() if path.exists() else f"no task contract in {top}: a builder may only read there")


def cmd_done(args):
    top = top_of(args.tree)
    path = contract_path(top)
    if is_main_checkout(top):
        path.unlink(missing_ok=True)
        print(f"contract removed from {top} (the main checkout stays)")
        return
    dirty = git(top, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise Refused(f"{top} has uncommitted work; commit or drop it first:\n{dirty}")
    branch = git(top, "branch", "--show-current")
    # Run git from the shared git folder, not from the tree it deletes (Windows refuses to delete a process's
    # working folder). The contract lives in the worktree's git folder, so it goes with it; a refused remove
    # keeps both.
    common = Path(git(top, "rev-parse", "--git-common-dir"))
    git(common if common.is_absolute() else top / common, "worktree", "remove", str(top))
    path.unlink(missing_ok=True)
    print(f"worktree {top} removed; branch {branch} kept")


def self_test():
    problems = []
    me = [sys.executable, str(Path(__file__).resolve())]
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "proj"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "a.py").write_text("a\n")
        git(tmp, "init", "-q", str(repo))
        git(repo, "add", "-A")
        git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")

        def run(*args):
            return subprocess.run(me + list(args), capture_output=True, text=True)

        def refused(label, out, reason):
            if out.returncode != 1 or reason not in out.stderr:
                problems.append(f"{label}: not refused for {reason!r}: {out.stdout + out.stderr}")

        out = run("new", str(repo), "job-9-parser", "--allow", "src/**", "--forbid", "src/b.py", "--check", "make test")
        wt = Path(tmp) / "proj-parser"
        cfile = Path(git(wt, "rev-parse", "--absolute-git-dir")) / CONTRACT_NAME if wt.exists() else None
        data = json.loads(cfile.read_text()) if cfile and cfile.exists() else {}
        if out.returncode != 0 or git(wt, "branch", "--show-current", check=False) != "job-9-parser" or \
                data.get("allow") != ["src/**"] or data.get("forbid") != ["src/b.py"] or data.get("checks") != ["make test"] \
                or data.get("version") != 1 or "Give the builder" not in out.stdout:
            problems.append(f"new: wrong worktree or contract: {data} {out.stdout + out.stderr}")
        if git(repo, "status", "--porcelain") or (Path(git(repo, "rev-parse", "--absolute-git-dir")) / CONTRACT_NAME).exists():
            problems.append("new: the main checkout changed or got a contract")
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        sys.dont_write_bytecode = True  # no __pycache__ beside the scripts
        from contract import read_contract  # the contract must read back as written
        seen = read_contract(str(wt)) if wt.exists() else None  # the contract must read back as written
        if wt.exists() and (not seen or seen.get("broken") or seen.get("allow") != ["src/**"]
                            or seen.get("forbid") != ["src/b.py"] or seen.get("checks") != ["make test"]):
            problems.append(f"read_contract reads the written contract differently: {seen}")
        (Path(tmp) / "proj-taken").mkdir()
        refused("a target folder that exists", run("new", str(repo), "job-9-taken", "--allow", "x", "--check", "t"),
                "already exists")
        if not (Path(tmp) / "proj-taken").is_dir() or \
                git(repo, "rev-parse", "-q", "--verify", "refs/heads/job-9-taken", check=False):
            problems.append("a refused new (target folder exists) made the branch")
        refused("a branch that exists", run("new", str(repo), "job-9-parser", "--allow", "x", "--check", "t"), "already exists")
        git(repo, "branch", "job-9-kept")
        refused("a branch without a worktree", run("new", str(repo), "job-9-kept", "--allow", "x", "--check", "t"), "pick a new one")
        before = sorted(p.name for p in Path(tmp).iterdir())
        refused("no --allow", run("new", str(repo), "job-9-other", "--check", "t"), "--allow and --check")
        refused("'..'", run("new", str(repo), "job-9-other", "--allow", "../x", "--check", "t"), "steps out")
        refused("absolute", run("new", str(repo), "job-9-other", "--allow", "/etc/x", "--check", "t"), "absolute")
        refused("git folder", run("new", str(repo), "job-9-other", "--allow", ".git/**", "--check", "t"), "git folder")
        refused("a blank check", run("new", str(repo), "job-9-other", "--allow", "x", "--check", " "), "--check is empty")
        if sorted(p.name for p in Path(tmp).iterdir()) != before or git(repo, "rev-parse", "-q", "--verify", "refs/heads/job-9-other", check=False):
            problems.append("a refused new left a folder or a branch")
        refused("~/.claude", run("contract", str(Path.home() / ".claude"), "--allow", "x", "--check", "t"), "inside ~/.claude")

        out2 = run("new", str(repo), "job-9-docs", "--allow", "docs/**", "--check", "make docs")
        wt2 = Path(tmp) / "proj-docs"
        c2 = Path(git(wt2, "rev-parse", "--absolute-git-dir")) / CONTRACT_NAME if wt2.exists() else None
        if out2.returncode != 0 or not c2 or c2 == cfile or json.loads(c2.read_text())["allow"] != ["docs/**"] or \
                json.loads(cfile.read_text())["allow"] != ["src/**"]:
            problems.append("two worktrees do not have their own contracts")
        if "; never" in out2.stdout or "you may change docs/**." not in out2.stdout:
            problems.append(f"the brief without --forbid is wrong: {out2.stdout}")

        out = run("contract", str(wt), "--allow", "src/**", "tests/**", "--check", "make test", "--check", "make lint")
        if out.returncode != 0 or "replaced; it was" not in out.stdout or json.loads(cfile.read_text())["checks"] != ["make test", "make lint"]:
            problems.append(f"contract: not replaced: {out.stdout + out.stderr}")
        refused("contract with an empty check", run("contract", str(wt), "--allow", "x", "--check", " "), "--check is empty")
        if "make lint" not in run("show", str(wt)).stdout or "no task contract" not in run("show", str(repo)).stdout:
            problems.append("show: wrong output")

        (wt / "src" / "new.py").write_text("n\n")
        refused("done with uncommitted work", run("done", str(wt)), "uncommitted work")
        if not wt.exists() or not cfile.exists():
            problems.append("a refused done removed something")
        (wt / "src" / "new.py").unlink()
        git(repo, "worktree", "lock", str(wt))  # git refuses to remove it: the tree must keep its contract
        out = run("done", str(wt))
        if out.returncode != 1 or not wt.exists() or not cfile.exists():
            problems.append(f"a refused worktree remove lost the tree or its contract: {out.stdout + out.stderr}")
        git(repo, "worktree", "unlock", str(wt))
        out = run("done", str(wt))
        if out.returncode != 0 or wt.exists() or not git(repo, "rev-parse", "-q", "--verify", "refs/heads/job-9-parser", check=False):
            problems.append(f"done: the worktree was not removed or the branch went with it: {out.stdout + out.stderr}")

        plan = Path(tmp) / "x.plan.md"
        plan.write_text("# Plan\n\n## Tasks\n\n### T1 (builder, parallel) Parser\n- allow: `src/**` `tests/**`\n"
                        "- forbid: `src/b.py`\n- check: `make test`\n- check: `make lint`\n\n### T2 (main) Guard\n"
                        "- allow: `hooks/**`\n- check: `make test`\n\n### T3 (builder) Docs\n- allow: `docs/**`\n"
                        "- check: `make docs`\n- not needed: merged into T1\n\n## Proof\n1. tests\n")
        flags = ("--allow", "src/**", "tests/**", "--forbid", "src/b.py", "--check", "make test", "--check", "make lint")
        out_t, out_f = run("new", str(repo), "job-9-fromtask", "--task", str(plan), "T1"), run("new", str(repo), "job-9-fromflags", *flags)
        read = lambda name: json.loads((Path(git(Path(tmp) / name, "rev-parse", "--absolute-git-dir")) / CONTRACT_NAME).read_text()) \
            if (Path(tmp) / name).exists() else {}
        from_task, from_flags = read("proj-fromtask"), read("proj-fromflags")
        strip = lambda d: {k: v for k, v in d.items() if k not in ("task", "written")}
        if out_t.returncode != 0 or out_f.returncode != 0 or not from_task or strip(from_task) != strip(from_flags) \
                or from_task.get("task") != "job-9-fromtask T1" or "make lint" not in out_t.stdout:
            problems.append(f"--task: the contract differs from the same flags: {from_task} vs {from_flags} {out_t.stderr}")
        (Path(tmp) / "old.plan.md").write_text("## Steps\n1. x\n")
        (Path(tmp) / "bad.plan.md").write_text("")
        solo = Path(tmp) / "solo"
        solo.mkdir()
        (solo / "dispatch.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
        before = sorted(p.name for p in Path(tmp).iterdir())
        refused("--task with flags", run("new", str(repo), "job-9-t", "--task", str(plan), "T1", "--check", "x"), "drop --allow")
        refused("--task unknown id", run("new", str(repo), "job-9-t", "--task", str(plan), "T9"), "has no task T9")
        refused("--task main task", run("new", str(repo), "job-9-t", "--task", str(plan), "T2"), "is a (main) task")
        refused("--task not needed", run("new", str(repo), "job-9-t", "--task", str(plan), "T3"), "marked not needed")
        refused("--task no Tasks", run("new", str(repo), "job-9-t", "--task", str(Path(tmp) / "old.plan.md"), "T1"), "no `## Tasks`")
        (Path(tmp) / "bad.plan.md").write_text("## Tasks\n### T1 (builder) X\n- allow: `../up/**`\n- check: `t`\n")
        refused("--task glob out of the tree", run("new", str(repo), "job-9-t", "--task", str(Path(tmp) / "bad.plan.md"), "T1"), "steps out")
        (Path(tmp) / "bad.plan.md").write_text("## Tasks\n### T1 (builder) X\n- allow: `a`\n- files: `b`\n- check: `t`\n")
        refused("--task malformed plan", run("new", str(repo), "job-9-t", "--task", str(Path(tmp) / "bad.plan.md"), "T1"), "does not know")
        refused("--task without sdlc-check.py", subprocess.run([sys.executable, str(solo / "dispatch.py"), "new", str(repo),
                "job-9-t", "--task", str(plan), "T1"], capture_output=True, text=True), "which is missing")
        refused("--task missing plan", run("new", str(repo), "job-9-t", "--task", str(Path(tmp) / "none.md"), "T1"), "none.md")
        if sorted(p.name for p in Path(tmp).iterdir()) != before or git(repo, "rev-parse", "-q", "--verify", "refs/heads/job-9-t", check=False):
            problems.append("a refused --task left a folder or a branch")
        out = run("contract", str(repo), "--task", str(plan), "T1")
        mc = Path(git(repo, "rev-parse", "--absolute-git-dir")) / CONTRACT_NAME
        if out.returncode != 0 or not mc.exists() or not json.loads(mc.read_text())["task"].endswith(" T1") or \
                strip(json.loads(mc.read_text())) != strip(from_flags):
            problems.append(f"contract --task on the main checkout: {out.stdout + out.stderr}")
        run("done", str(repo))

        out = run("contract", str(repo), "--allow", "src/a.py", "--check", "make test")
        main_contract = Path(git(repo, "rev-parse", "--absolute-git-dir")) / CONTRACT_NAME
        out = run("done", str(repo)) if out.returncode == 0 else out
        if out.returncode != 0 or main_contract.exists() or not repo.exists():
            problems.append(f"done on the main checkout: {out.stdout + out.stderr}")
    print("FAIL\n" + "\n".join(f"- {p}" for p in problems) if problems else
          "PASS: new (worktree, branch, contract), refusals with their reasons and nothing left behind, two worktrees "
          "with their own contracts, contract replaced, show, done refusing uncommitted work and removing a clean "
          "worktree, done on the main checkout, --task: the same contract as its flags and each refusal")
    return 1 if problems else 0


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    parser = argparse.ArgumentParser(description="Prepare a builder dispatch: worktree and task contract.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("new", "contract"):
        p = sub.add_parser(name)
        if name == "new":
            p.add_argument("repo")
            p.add_argument("branch")
        else:
            p.add_argument("tree")
        p.add_argument("--allow", nargs="+", default=[])
        p.add_argument("--forbid", nargs="+", default=[])
        p.add_argument("--check", action="append", default=[])
        p.add_argument("--task", nargs=2, metavar=("PLAN", "ID"))
    for name in ("show", "done"):
        sub.add_parser(name).add_argument("tree")
    args = parser.parse_args()
    try:
        {"new": cmd_new, "contract": cmd_contract, "show": cmd_show, "done": cmd_done}[args.cmd](args)
    except Refused as reason:
        print(f"refused: {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
