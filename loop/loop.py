#!/usr/bin/env python3
"""The one-prompt loop's run file: start a run on a plan, record review verdicts, close or reopen it.

  python3 loop.py start <plan.md> [--base <ref>] [--hours <n>]
                                                   open a run for this session on that plan (in its git work tree);
                                                   it closes itself after <n> hours (default 12)
  python3 loop.py pass <task>                      record a review PASS for a task (T1, T2, …); refused unless that
                                                   task's last reviewer verdict the SubagentStop hook recorded (from a
                                                   reviewer prompt line `loop task: T<n>`) is PASS
  python3 loop.py fail <task> "<reason>"           record a review FAIL; the second FAIL of one task closes the run
  python3 loop.py ask "<question>"                 close the run for a question only the owner can answer
  python3 loop.py stop [reason]                    close the run for any other reason
  python3 loop.py resume                           (in the session that will hold it) reopen a run closed by ask, stop,
                                                   the idle breaker, a limit (loop-wake.py's caps too) or
                                                   three failing check rounds (a new time limit, counters at zero)
  python3 loop.py status                           print the run
  python3 loop.py --self-test                      exit 0 = PASS

The run file is `<git dir>/1prompt-run.json` of the work tree `start` runs in (the plan must be in it; never
committed), and `~/.claude/1prompt-runs/<session id>` points the Stop hook and the other commands at it, wherever the
shell is. The plan needs `## Tasks` and `## Proof`; the base must not be the branch being worked on. A review FAIL
keeps the run open until a later PASS of that task. While a run is open,
the Stop hook (loop-stop.py) keeps this session going until `sdlc-check.py converge --checks` finds no gap in the plan,
its checks pass and no proof result is a FAIL; the session then stops with "done". A review verdict is evidence, not
the session's word: the SubagentStop hook records what each run of a reviewer agent (a type ending in `reviewer`) of
this session returned for the task its prompt names (`loop task: T<n>`), and `pass <task>` needs that task's last one
to be PASS (`fail` needs nothing: it only makes the run stricter, and every reviewer FAIL of a task must have one). A
verdict that names no task counts for nothing. The run file is a plain file: a guard against haste, not against a session that sets out to cheat. The run is bound to the session that started it
(CLAUDE_CODE_SESSION_ID), so other sessions in the same tree are not held. A run closed by two fails or by "done"
is not reopened: start a new one. Exit 0 done, 1 refused by the run's state, 2 usage or not a git work tree.
Standard library only.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

RUN_FILE = "1prompt-run.json"
POINTERS = Path.home() / ".claude" / "1prompt-runs"  # <session id> -> run file path; the Stop hook reads it
JUDGE = Path(__file__).resolve().parent.parent / "scripts" / "sdlc-check.py"
REOPENABLE = ("ask", "stop", "idle", "limit", "checks")
DEFAULT_HOURS = 12


class Stop(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def now(hours=0):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%MZ")


def git(cwd, *args):
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise Stop(2, f"not a git work tree here ({out.stderr.strip() or 'git failed'})")
    return out.stdout.strip()


def session_id():
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
    return session if session and "/" not in session and not session.startswith(".") else ""


def run_path(cwd="."):
    """This session's run (by its pointer) wherever the shell is now; else the run of the cwd's work tree."""
    session = session_id()
    if session:
        try:
            pointed = Path((POINTERS / session).read_text(encoding="utf-8").strip())
            if pointed.is_file():
                return pointed
        except OSError:
            pass
    return Path(git(cwd, "rev-parse", "--absolute-git-dir")) / RUN_FILE


def load(path):
    if not path.is_file():
        raise Stop(1, "no run in this work tree; start one with `loop.py start <plan>`")
    try:
        run = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Stop(1, f"the run file {path} cannot be read ({type(error).__name__}); remove it and start again") from None
    if not isinstance(run, dict) or run.get("version") != 1:
        raise Stop(1, f"the run file {path} is not a version 1 run; remove it and start again")
    return run


def save(path, run):
    """Atomic write, so the Stop hook never reads half a file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".1prompt-run.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(run, f, indent=1)
    os.replace(tmp, path)


def close(run, kind, reason):
    run.update(state="closed", closed_by=kind, reason=reason, closed_at=now())


def describe(run):
    lines = [f"run: {run.get('state')}" + (f" ({run.get('closed_by')}: {run.get('reason')})" if run.get("state") == "closed" else ""),
             f"plan: {run.get('plan')}", f"base: {run.get('base')}", f"started: {run.get('started')}",
             f"time limit: {run.get('deadline', 'none')}"]
    reviews = run.get("reviews") or []
    if reviews:
        lines.append("reviewer verdicts on record: " + ", ".join(
            f"{r.get('agent')} {r.get('verdict')} ({r.get('task') or 'no task: not counted'})" for r in reviews[-5:]))
    if run.get("check_fails"):
        lines.append(f"failing check rounds: {run['check_fails']} of 3")
    for task, reasons in sorted((run.get("fails") or {}).items()):
        lines.append(f"{task}: {len(reasons)} FAIL(s): " + " | ".join(reasons))
    if run.get("passes"):
        lines.append("PASS: " + ", ".join(sorted(run["passes"])))
    return "\n".join(lines)


def task_id(value, run):
    """A task the plan names (`### T<n> (…`), so one task never gets two fail counts."""
    m = re.fullmatch(r"[Tt]([1-9]\d*)", value)
    if not m:
        raise Stop(2, f"not a task id: {value!r} (T1, T2, …)")
    task = "T" + m[1]
    try:
        text = Path(run["plan"]).read_text(encoding="utf-8")
    except (OSError, KeyError):
        raise Stop(1, "the run's plan cannot be read") from None
    if not re.search(rf"^### {task} \(", text, re.M):
        raise Stop(2, f"the plan has no task {task}")
    return task


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    command, rest = argv[0], argv[1:]
    if command == "start":
        base, hours, options = None, DEFAULT_HOURS, rest[1:]
        if not rest or rest[0].startswith("--") or len(options) % 2:
            raise Stop(2, "usage: start <plan.md> [--base <ref>] [--hours <n>]")
        for name, value in zip(options[::2], options[1::2]):
            if name == "--base" and base is None:
                base = value
            elif name == "--hours":
                try:
                    hours = float(value)
                except ValueError:
                    hours = 0
                if not 0 < hours <= 168:
                    raise Stop(2, f"--hours needs a number of hours up to 168, not {value!r}")
            else:
                raise Stop(2, "usage: start <plan.md> [--base <ref>] [--hours <n>]")
        plan = Path(rest[0]).resolve()
        if not plan.is_file():
            raise Stop(2, f"no plan at {plan}")
        session = session_id()
        if not session:
            raise Stop(2, "CLAUDE_CODE_SESSION_ID is not set: start a run from inside the Claude Code session it holds")
        top = Path(git(".", "rev-parse", "--show-toplevel")).resolve()
        if top not in plan.parents:
            raise Stop(2, f"the plan is not in this work tree ({top}); start the run from the plan's tree")
        text = plan.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"^## Tasks\s*$", text, re.M) or not re.search(r"^## Proof\s*$", text, re.M):
            raise Stop(2, "the plan needs a `## Tasks` and a `## Proof` section (sdlc skill): without them nothing judges done")
        path = Path(git(".", "rev-parse", "--absolute-git-dir")) / RUN_FILE
        try:  # this session's run in another tree, still open: one run per session
            mine = Path((POINTERS / session).read_text(encoding="utf-8").strip())
            if mine != path and json.loads(mine.read_text(encoding="utf-8")).get("state") == "running":
                raise Stop(1, f"this session already has an open run at {mine}; `loop.py stop` it first")
        except (OSError, ValueError, AttributeError):
            pass
        if path.is_file():
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                old = {}
            if isinstance(old, dict) and old.get("state") == "running":
                raise Stop(1, f"a run is already open here on {old.get('plan')}; `loop.py stop` it first")
        if base is None:
            base = next((r for r in ("origin/main", "main") if subprocess.run(
                ["git", "-C", str(plan.parent), "rev-parse", "-q", "--verify", r + "^{commit}"],
                capture_output=True).returncode == 0), None)
            if base is None:
                raise Stop(2, "no origin/main or main to compare with; pass --base")
        branch = subprocess.run(["git", "-C", str(top), "symbolic-ref", "-q", "--short", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        if base == "HEAD" or (branch and base in (branch, f"origin/{branch}", f"refs/heads/{branch}")):
            raise Stop(2, f"the base {base!r} is the branch being worked on: every commit would hide the work from the "
                          "judge; work on a branch and compare with its base (main)")
        if not JUDGE.is_file():
            raise Stop(2, f"the judge {JUDGE} is missing")
        run = {"version": 1, "state": "running", "run_id": os.urandom(8).hex(), "plan": str(plan), "base": base, "session": session, "top": str(top),
               "judge": str(JUDGE), "started": now(), "hours": hours, "deadline": now(hours), "fails": {}, "passes": [],
               "open_fails": [], "reviews": [], "check_fails": 0, "idle": 0, "blocks": 0, "fingerprint": None}
        save(path, run)
        POINTERS.mkdir(parents=True, exist_ok=True)
        (POINTERS / session).write_text(str(path), encoding="utf-8")
        print(f"run open on {plan.name} (base {base}, until {run['deadline']}); the Stop hook holds this session until the "
              "plan converges and its checks pass")
        return 0
    path = run_path()
    run = load(path)
    if command == "status":
        print(describe(run))
        return 0
    if command == "resume":
        if run.get("state") == "running":
            raise Stop(1, "the run is already open")
        if run.get("closed_by") not in REOPENABLE:
            raise Stop(1, f"a run closed by {run.get('closed_by')} is not reopened; start a new one")
        hours = run.get("hours") if isinstance(run.get("hours"), (int, float)) and run.get("hours") > 0 else DEFAULT_HOURS
        run.update(state="running", idle=0, blocks=0, waits=0, check_fails=0, wakes=0, fingerprint=None, deadline=now(hours))
        for key in ("closed_by", "reason", "closed_at", "notified", "next_wake", "wake_noted"):
            run.pop(key, None)
        me, before = session_id(), run.get("session")
        if me and me != before:  # the session that resumes holds the run from now on (loop-wake may have bound a fork)
            run["session"] = me
        save(path, run)
        if me and me != before:
            POINTERS.mkdir(parents=True, exist_ok=True)
            (POINTERS / me).write_text(str(path), encoding="utf-8")
            if isinstance(before, str) and before and "/" not in before and not before.startswith("."):
                try:
                    (POINTERS / before).unlink()
                except OSError:
                    pass
        print("run reopened" + (f", now held by this session ({me[:8]})" if me and me != before else ""))
        return 0
    if run.get("state") != "running":
        raise Stop(1, f"the run is closed ({run.get('closed_by')}: {run.get('reason')})")
    if command == "pass":
        if len(rest) != 1:
            raise Stop(2, "usage: pass <task>")
        task = task_id(rest[0], run)
        reviews = [r for r in run.get("reviews") or [] if isinstance(r, dict) and r.get("task") == task]
        last = reviews[-1].get("verdict") if reviews else None
        if last != "PASS":
            raise Stop(1, f"{task}: no reviewer PASS on record for it (its last reviewer verdict: {last or 'none'}). A PASS "
                          "comes from a reviewer agent's run in this session (`reviewer`, `hard-reviewer`) whose prompt "
                          f"names the task as `loop task: {task}`; the SubagentStop hook records it. "
                          "If a reviewer did return PASS, that hook is not loaded here: run `install.py --settings`, "
                          "then `loop.py ask` and tell the owner.")
        run["passes"] = sorted(set(run.get("passes") or []) | {task})
        run["open_fails"] = sorted(set(run.get("open_fails") or []) - {task})
        save(path, run)
        print(f"{task}: PASS recorded")
        return 0
    if command == "fail":
        if len(rest) != 2 or not rest[1].strip():
            raise Stop(2, 'usage: fail <task> "<reason>"')
        task = task_id(rest[0], run)
        run["open_fails"] = sorted(set(run.get("open_fails") or []) | {task})
        fails = run.setdefault("fails", {}).setdefault(task, [])
        fails.append(rest[1].strip())
        if len(fails) >= 2:
            close(run, "two-fails", f"{task} failed review twice: {' | '.join(fails)}")
            save(path, run)
            print(f"run closed: {run['reason']}\nStop here and report to the owner with the numbered issues.")
            return 0
        save(path, run)
        print(f"{task}: FAIL 1 of 2 recorded; fix from the numbered issues and review again")
        return 0
    if command == "ask":
        if len(rest) != 1 or not rest[0].strip():
            raise Stop(2, 'usage: ask "<question>"')
        close(run, "ask", f"needs the owner: {rest[0].strip()}")
        save(path, run)
        print(f"run closed: {run['reason']}\nAsk the owner, with your recommendation; `loop.py resume` after the answer.")
        return 0
    if command == "stop":
        if len(rest) > 1:
            raise Stop(2, "usage: stop [reason]")
        close(run, "stop", rest[0] if rest else "stopped by hand")
        save(path, run)
        print(f"run closed: {run['reason']}")
        return 0
    raise Stop(2, f"unknown command {command!r}; run with --help")


def self_test():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        (repo / "f").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "i"], check=True)
        plan = repo / "p.plan.md"
        plan.write_text("# plan\n\n## Tasks\n\n### T1 (main) a\n\n### T2 (main) b\n\n## Proof\n\n1. x\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "switch", "-q", "-c", "work"], check=True)
        env = {**os.environ, "CLAUDE_CODE_SESSION_ID": "sess-1", "HOME": tmp, "USERPROFILE": tmp}
        runfile = repo / ".git" / RUN_FILE

        def call(*args, use_env=None):
            return subprocess.run([sys.executable, __file__, *args], cwd=repo, env=use_env or env,
                                  capture_output=True, text=True, timeout=60)

        def expect(name, out, code, has=None):
            if out.returncode != code:
                failures.append(f"{name}: exit {out.returncode}, expected {code}: {out.stdout.strip()} {out.stderr.strip()}")
            if has and has not in out.stdout + out.stderr:
                failures.append(f"{name}: output lacks {has!r}: {(out.stdout + out.stderr).strip()!r}")

        def state():
            return json.loads(runfile.read_text(encoding="utf-8")) if runfile.is_file() else {}

        no_session = {k: v for k, v in env.items() if k != "CLAUDE_CODE_SESSION_ID"}
        expect("start without a session id", call("start", str(plan), use_env=no_session), 2, "CLAUDE_CODE_SESSION_ID")
        expect("pass with no run", call("pass", "T1"), 1, "no run")
        bare = repo / "bare.plan.md"
        bare.write_text("# plan\n", encoding="utf-8")
        expect("a plan without Tasks", call("start", str(bare)), 2, "## Tasks")
        expect("base is the branch worked on", call("start", str(plan), "--base", "work"), 2, "branch being worked on")
        expect("base HEAD", call("start", str(plan), "--base", "HEAD"), 2, "branch being worked on")
        other = Path(tmp) / "other"
        other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        out = subprocess.run([sys.executable, __file__, "start", str(plan)], cwd=other, env=env, capture_output=True, text=True)
        expect("plan in another tree", out, 2, "not in this work tree")
        expect("start", call("start", str(plan)), 0, "run open")
        pointer = Path(tmp) / ".claude" / "1prompt-runs" / "sess-1"
        if not pointer.is_file() or pointer.read_text(encoding="utf-8") != str(runfile):
            failures.append("start did not write the session pointer")
        out = subprocess.run([sys.executable, __file__, "status"], cwd=other, env=env, capture_output=True, text=True)
        expect("status from another folder finds the session's run", out, 0, "run: running")
        expect("a task the plan does not have", call("pass", "T9"), 2, "no task T9")
        expect("T01 is not a task id", call("pass", "T01"), 2, "not a task id")
        s = state()
        if (s.get("session"), s.get("base"), s.get("state"), Path(s.get("judge", "")).name) != ("sess-1", "main", "running", "sdlc-check.py"):
            failures.append(f"start wrote {s}")
        expect("second start while running", call("start", str(plan)), 1, "already open")
        expect("bad task id", call("pass", "X1"), 2, "not a task id")
        def reviewed(*verdicts, task="T2"):  # what the SubagentStop hook writes when a reviewer run of a task ends
            s = state()
            s["reviews"] = (s.get("reviews") or []) + [{"agent": "reviewer", "verdict": v, "at": "t", "task": task}
                                                       for v in verdicts]
            runfile.write_text(json.dumps(s), encoding="utf-8")

        s = state()
        if not s.get("deadline") or s.get("hours") != DEFAULT_HOURS or s.get("deadline") <= s.get("started"):
            failures.append(f"start wrote no time limit: {s.get('hours')} {s.get('deadline')}")
        expect("pass with no reviewer verdict on record", call("pass", "t2"), 1, "no reviewer PASS on record")
        reviewed("PASS", "FAIL")
        expect("pass after a reviewer FAIL", call("pass", "t2"), 1, "its last reviewer verdict: FAIL")
        reviewed("none")
        expect("pass after a verdict that was neither", call("pass", "t2"), 1, "its last reviewer verdict: none")
        if state().get("passes"):
            failures.append("a refused pass was recorded")
        reviewed("PASS", task=None)
        expect("pass after a PASS that named no task", call("pass", "t2"), 1, "no reviewer PASS on record for it")
        reviewed("PASS", task="T1")
        expect("pass after a PASS for another task", call("pass", "t2"), 1, "no reviewer PASS on record for it")
        reviewed("PASS")
        expect("pass", call("pass", "t2"), 0, "T2: PASS")
        expect("status shows the verdicts", call("status"), 0, "reviewer verdicts on record")
        expect("fail 1", call("fail", "T1", "test missing"), 0, "FAIL 1 of 2")
        if state().get("open_fails") != ["T1"]:
            failures.append(f"open_fails after a FAIL: {state().get('open_fails')}")
        expect("pass clears the open FAIL", call("pass", "T1"), 0, "T1: PASS")
        if state().get("open_fails") != []:
            failures.append(f"open_fails after a PASS: {state().get('open_fails')}")
        expect("fail with no reason", call("fail", "T1", " "), 2, "usage")
        if state().get("state") != "running":
            failures.append("one FAIL closed the run")
        expect("fail 2 closes", call("fail", "T1", "still missing"), 0, "failed review twice")
        s = state()
        if (s.get("state"), s.get("closed_by")) != ("closed", "two-fails") or "test missing | still missing" not in s.get("reason", ""):
            failures.append(f"after two fails: {s}")
        expect("pass after close", call("pass", "T1"), 1, "closed")
        expect("resume after two fails", call("resume"), 1, "not reopened")
        expect("status", call("status"), 0, "T1: 2 FAIL(s)")
        for bad in (("--hours", "0"), ("--hours", "x"), ("--hours", "500"), ("--hours",), ("--frob", "1"), ("--base", "main", "--base", "main")):
            expect(f"start {' '.join(bad)}", call("start", str(plan), *bad), 2)
        expect("new start after a closed run", call("start", str(plan), "--hours", "0.5", "--base", "main"), 0, "base main")
        if state().get("hours") != 0.5 or state().get("reviews") != []:
            failures.append(f"a new run did not start with its own limit and no verdicts: {state()}")
        expect("ask", call("ask", "which licence?"), 0, "needs the owner")
        expect("resume after ask", call("resume"), 0, "reopened")
        expect("resume while running", call("resume"), 1, "already open")
        expect("stop", call("stop", "owner said so"), 0, "owner said so")
        expect("resume after stop", call("resume"), 0, "reopened")
        s = state()
        s.update(state="closed", closed_by="checks", reason="checks failed 3 rounds", check_fails=3, waits=10, deadline="2000-01-01T00:00Z", notified=True)
        runfile.write_text(json.dumps(s), encoding="utf-8")
        expect("resume after three failing check rounds", call("resume"), 0, "reopened")
        s = state()
        if s.get("check_fails") != 0 or s.get("waits") != 0 or s.get("deadline", "") < s.get("started", "x") or "notified" in s:
            failures.append(f"resume did not reset the check rounds, the time limit and the notice: {s}")
        # closed by loop-wake's caps while bound to a fork: resumed from the owner's session, it is held by that session
        s.update(state="closed", closed_by="limit", reason="its session stopped again after 4 wakes", wakes=4,
                 next_wake="2999-01-01T00:00Z", wake_noted=True, session="fork-4")
        runfile.write_text(json.dumps(s), encoding="utf-8")
        (Path(tmp) / ".claude" / "1prompt-runs" / "fork-4").write_text(str(runfile), encoding="utf-8")
        expect("resume after the wake cap", call("resume"), 0, "now held by this session")
        s = state()
        if s.get("wakes") != 0 or "next_wake" in s or "wake_noted" in s or s.get("session") != "sess-1" \
                or (Path(tmp) / ".claude" / "1prompt-runs" / "fork-4").exists() \
                or (Path(tmp) / ".claude" / "1prompt-runs" / "sess-1").read_text() != str(runfile):
            failures.append(f"resume did not reset the wakes or bind the resuming session: {s}")
        s.update(state="closed", closed_by="done", reason="goal done")
        runfile.write_text(json.dumps(s), encoding="utf-8")
        expect("resume after done", call("resume"), 1, "not reopened")
        runfile.write_text("{broken", encoding="utf-8")
        expect("broken run file", call("status"), 1, "cannot be read")
        expect("start over a broken run file", call("start", str(plan)), 0, "run open")
        no_ptr = {**env, "CLAUDE_CODE_SESSION_ID": "sess-2"}
        outside = subprocess.run([sys.executable, __file__, "status"], cwd=tmp, env=no_ptr, capture_output=True, text=True, timeout=60)
        expect("outside a git tree", outside, 2, "not a git work tree")
        expect("unknown command", call("frob"), 2, "unknown command")
        if list((repo / ".git").glob(".1prompt-run.*")):
            failures.append("a temporary run file was left behind")
    print("FAIL\n" + "\n".join(failures) if failures else "PASS: loop.py self-test")
    return 1 if failures else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    try:
        sys.exit(main(sys.argv[1:]))
    except Stop as stop:
        print(f"loop.py: {stop}", file=sys.stderr)
        sys.exit(stop.code)
