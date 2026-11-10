#!/usr/bin/env python3
"""Stop hook of the one-prompt loop: holds the session that started a run until its plan converges.

  python3 loop-stop.py              the hook (Claude Code's Stop input on stdin; registered by install.py --settings)
  python3 loop-stop.py --self-test  exit 0 = PASS

It acts only when the stopping session has a running run file (`<git dir>/1prompt-run.json`, written by
loop.py start) whose session is the one stopping. Then, in this order:
  1. the same fingerprint for the third stop in a row: the run closes ("no progress in 3 stops") and the session stops;
  2. the run's judge, `sdlc-check.py converge <plan> --base <base>`: a gap, or a proof result that is a FAIL, blocks
     the stop and gives the session the list as its next work; a plan the judge cannot read blocks with its error;
  3. nothing left: the run closes as done and the session stops.
The run is found through ~/.claude/1prompt-runs/<session id> (written by loop.py start), whatever the session's cwd.
The fingerprint is HEAD, the content of every tracked change and untracked file, the plan and the verdicts; 40 held
stops close a run whatever moves. Done needs the judge's own "PASS: converge" line and exit 0: a judge that crashes,
times out or prints something else holds the session with the error (the breakers bound it), never reads as done.
It never traps a session on its own failure: no pointer or run file, another session, a closed run, a broken run file,
a missing judge or any error inside the hook means no decision (exit 0, the session stops), and settings.json runs it
with `|| true`.
Standard library only.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

RUN_FILE = "1prompt-run.json"
IDLE_LIMIT = 3
BLOCK_LIMIT = 40  # stops held per run, whatever moves: a hard cap on a run that never converges
TIMEOUT = int(os.environ.get("LOOP_JUDGE_TIMEOUT", "50"))  # seconds for the judge; settings.json gives the hook 60
POINTERS = Path.home() / ".claude" / "1prompt-runs"  # <session id> -> run file path, written by loop.py start


def git_bytes(cwd, *args):
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, timeout=TIMEOUT)
    return out.stdout if out.returncode == 0 else b""


def git(cwd, *args):
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=TIMEOUT)
    return out.stdout.strip() if out.returncode == 0 else None


def save_merged(path, run, fields):
    """Writes the hook's own fields onto the run file as it is now: a `loop.py stop`, `ask` or verdict written while
    the judge ran is kept, and a run closed meanwhile is never set back to running."""
    try:
        fresh = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(fresh, dict) or fresh.get("state") != "running" or fresh.get("run_id") != run.get("run_id"):
        return False
    fresh.update({k: run[k] for k in fields if k in run})
    save(path, fresh)
    return True


def save(path, run):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".1prompt-run.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(run, f, indent=1)
    os.replace(tmp, path)


def fingerprint(top, plan, run):
    """HEAD, the content of every tracked change and of every untracked file (not only their names), the plan and the
    verdicts: an edit to a file that is already dirty counts as progress."""
    h = hashlib.sha256()
    for part in (git_bytes(top, "rev-parse", "HEAD"), git_bytes(top, "diff", "HEAD", "--binary")):
        h.update(part + b"\0")  # bytes: a file in any encoding is fine
    for name in sorted(git_bytes(top, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")):
        if name:
            h.update(name + b"\0")
            try:
                with open(Path(top) / os.fsdecode(name), "rb") as f:
                    h.update(f.read(1 << 20))
            except OSError:
                h.update(b"unreadable")
    try:
        h.update(plan.read_bytes())
    except OSError:
        h.update(b"no plan")
    h.update(json.dumps([run.get("fails"), run.get("passes"), run.get("open_fails")], sort_keys=True).encode())
    return h.hexdigest()


def decide(payload):
    """Returns the JSON to print (a dict) or None for no decision."""
    if not isinstance(payload, dict):
        return None
    session = payload.get("session_id")
    if not isinstance(session, str) or not session or "/" in session or session.startswith("."):
        return None
    pointer = POINTERS / session  # the session's run, wherever its cwd is now
    try:
        path = Path(pointer.read_text(encoding="utf-8").strip())
    except OSError:
        return None
    if not path.is_file():
        return None
    try:
        run = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(run, dict) or run.get("version") != 1 or run.get("state") != "running":
        return None
    if not run.get("session") or run.get("session") != session:
        return None
    plan, judge, base, top = Path(str(run.get("plan"))), Path(str(run.get("judge"))), run.get("base"), run.get("top")
    if not judge.is_file() or not isinstance(base, str) or not isinstance(top, str):
        return None
    fields = ("idle", "fingerprint", "blocks", "state", "closed_by", "reason", "closed_at")

    def closing(kind, reason, message):
        run.update(state="closed", closed_by=kind, reason=reason,
                   closed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"))
        if not save_merged(path, run, fields):
            return None  # closed or restarted meanwhile: that state stands
        return {"systemMessage": message}

    if run.get("blocks", 0) >= BLOCK_LIMIT:
        return closing("limit", f"held {BLOCK_LIMIT} stops without converging",
                       f"1prompt run closed: held {BLOCK_LIMIT} stops without converging ({plan.name}).")

    mark = fingerprint(top, plan, run)
    run["idle"] = run.get("idle", 0) + 1 if mark == run.get("fingerprint") else 1
    run["fingerprint"] = mark
    if run["idle"] >= IDLE_LIMIT:
        return closing("idle", f"no progress in {IDLE_LIMIT} stops",
                       f"1prompt run closed: no progress in {IDLE_LIMIT} stops ({plan.name}). `loop.py resume` reopens it.")

    try:
        out = subprocess.run([sys.executable, str(judge), "converge", str(plan), "--base", base],
                             capture_output=True, text=True, timeout=TIMEOUT, cwd=top)
        code, stdout, stderr = out.returncode, out.stdout, out.stderr
    except subprocess.TimeoutExpired:
        code, stdout, stderr = None, "", f"the judge took over {TIMEOUT} s"
    lines = stdout.splitlines()
    summary = lines[-1] if lines else ""
    gaps = [l[len("gap: "):] for l in lines if l.startswith("gap: ")]
    gaps += [l for l in lines if l.startswith("proof ") and l.endswith("recorded FAIL")]
    gaps += [l for l in lines if l.endswith("no `## Tasks` section; nothing to compare")]
    gaps += [f"{task} has a review FAIL with no PASS after it" for task in sorted(run.get("open_fails") or [])]
    passed = code == 0 and summary.startswith("PASS: converge")
    judged = passed or (code == 1 and summary.startswith("FAIL: converge"))
    if code == 2:
        gaps = [f"the judge cannot read the plan: {stderr.strip()[:300]}"]
    elif not judged or (not gaps and not passed):  # a crash, a timeout or output not in the judge's format
        gaps = [f"the judge did not give a verdict (exit {code}): {(stderr or stdout).strip()[-300:]}; do not edit "
                "the judge: end the run with `loop.py stop \"judge broken\"` and tell the owner"]
    if gaps:
        run["blocks"] = run.get("blocks", 0) + 1
        if not save_merged(path, run, fields):
            return None  # closed or restarted while the judge ran: let the session stop
        listed = "\n".join(f"- {g}" for g in gaps[:20]) + (f"\n- … {len(gaps) - 20} more" if len(gaps) > 20 else "")
        return {"decision": "block", "reason":
                f"1prompt run open on {plan.name}: {len(gaps)} item(s) left before the goal is done.\n{listed}\n"
                "Continue with the next one (rate, dispatch or do it, gate, review). Record each review with "
                "`loop.py pass <task>` or `loop.py fail <task> \"<reason>\"` (the second FAIL of a task ends the run). "
                "A path outside every task that is not this work's (the owner's file, another change): do not delete "
                "it or widen the plan yourself; ask. A question only the owner can answer: "
                "`loop.py ask \"<question>\"`. To end the run: `loop.py stop`."}
    return closing("done", "goal done: the plan converges", f"1prompt run done: {plan.name} converges (no gap, no FAIL).")


def self_test():
    failures = []
    loop = Path(__file__).resolve().parent / "loop.py"
    judge = Path(__file__).resolve().parent.parent / "scripts" / "sdlc-check.py"
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        (repo / "src").mkdir(parents=True)
        g = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True)
        g("init", "-q", "-b", "main")
        (repo / "src" / "a.py").write_text("a = 1\n", encoding="utf-8")
        g("add", ".")
        g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        g("switch", "-q", "-c", "work")
        plan = repo / "work.plan.md"
        head = ("---\nstatus: building\n---\n# Work\n\n## Tasks\n\n### T1 (main) Code\n- allow: `src/**`\n- check: `true`\n\n"
                "### T2 (main) Docs\n- allow: `docs/**`\n- check: `true`\n\n## Proof\n\n1. it works\n\n## Result\n\n")
        plan.write_text(head, encoding="utf-8")
        env = {**os.environ, "CLAUDE_CODE_SESSION_ID": "sess-1", "HOME": tmp, "USERPROFILE": tmp}
        runfile = repo / ".git" / RUN_FILE

        def loopcmd(*args):
            return subprocess.run([sys.executable, str(loop), *args], cwd=repo, env=env, capture_output=True, text=True)

        def hook(payload, raw=None, extra=None):
            out = subprocess.run([sys.executable, __file__], input=raw if raw is not None else json.dumps(payload),
                                 capture_output=True, text=True, timeout=120, env={**env, **(extra or {})})
            decision = json.loads(out.stdout) if out.stdout.strip() else None
            return out, decision

        def expect(name, payload, blocked, has=None, raw=None, extra=None):
            out, decision = hook(payload, raw, extra)
            if out.returncode != 0:
                failures.append(f"{name}: exit {out.returncode}: {out.stderr.strip()}")
            is_block = bool(decision) and decision.get("decision") == "block"
            if is_block != blocked:
                failures.append(f"{name}: blocked={is_block}, expected {blocked}: {out.stdout.strip()[:300]!r}")
            if has and has not in out.stdout:
                failures.append(f"{name}: output lacks {has!r}: {out.stdout.strip()[:300]!r}")
            return decision

        def state():
            return json.loads(runfile.read_text(encoding="utf-8"))

        def restart():
            loopcmd("stop")
            out = loopcmd("start", str(plan), "--base", "main")
            if out.returncode != 0:
                failures.append(f"start failed: {out.stderr.strip()}")

        def set_run(**changes):
            s = state()
            s.update(changes)
            runfile.write_text(json.dumps(s), encoding="utf-8")

        restart()
        me = {"session_id": "sess-1", "cwd": str(repo), "stop_hook_active": False}
        expect("another session", {**me, "session_id": "other"}, False)
        (Path(tmp) / ".claude" / "1prompt-runs" / "other").write_text(str(runfile), encoding="utf-8")
        expect("a stale pointer of another session to this run", {**me, "session_id": "other"}, False)
        expect("gaps: both tasks untouched, proof without result", me, True, "T1 (Code) changed none of its files")
        (repo / "src" / "a.py").write_text("a = 2\n", encoding="utf-8")
        d = expect("the session's cwd elsewhere: still its run", {**me, "cwd": tmp}, True, "T2 (Docs)")
        if d and "T1 (Code)" in d.get("reason", ""):
            failures.append("T1 still listed after its file changed")
        (repo / "docs").mkdir()
        (repo / "docs" / "x.md").write_text("x\n", encoding="utf-8")
        plan.write_text(head + "1. FAIL it does not\n", encoding="utf-8")
        expect("a FAIL result blocks", me, True, "proof 1 recorded FAIL")
        plan.write_text(head + "1. PASS it works\n", encoding="utf-8")
        loopcmd("fail", "T1", "naming")
        expect("an open review FAIL blocks", me, True, "T1 has a review FAIL with no PASS after it")
        loopcmd("pass", "T1")
        expect("converged: done", me, False, "run done")
        if (state().get("state"), state().get("closed_by")) != ("closed", "done"):
            failures.append(f"done not recorded: {state()}")
        expect("closed run", me, False)
        # the judge must give a verdict: a crash, a timeout or another exit code is never done
        restart()
        bad = Path(tmp) / "bad-judge.py"
        for name, body, extra in (("judge crashes", "raise SystemExit(1)\n", None),
                                  ("judge has a syntax error", "def (:\n", None),
                                  ("judge exits 3", "print('PASS: converge x')\nraise SystemExit(3)\n", None),
                                  ("judge prints PASS but exits 1", "print('PASS: converge x')\nraise SystemExit(1)\n", None),
                                  ("judge times out", "import time\ntime.sleep(5)\n", {"LOOP_JUDGE_TIMEOUT": "1"})):
            bad.write_text(body, encoding="utf-8")
            set_run(judge=str(bad), idle=0, fingerprint=None)
            expect(name, me, True, "did not give a verdict", extra=extra)
            if state().get("state") != "running":
                failures.append(f"{name}: the run was closed: {state().get('closed_by')}")
        set_run(judge=str(judge))
        # Tasks removed from the plan mid-run: a gap, not done
        plan.write_text("# Work\n\n## Proof\n\n1. it works\n\n## Result\n\n1. PASS\n", encoding="utf-8")
        bad.write_text("print('FAIL: converge x, 0 gap(s)')\nraise SystemExit(1)\n", encoding="utf-8")
        set_run(judge=str(bad), idle=0, fingerprint=None)
        expect("a FAIL summary with no gap line is not done", me, True, "did not give a verdict")
        set_run(judge=str(judge))
        expect("plan lost its Tasks", me, True, "no `## Tasks` section")
        plan.write_text(head + "1. PASS it works\n", encoding="utf-8")
        # a stop written while the judge runs is kept
        racer = Path(tmp) / "racing-judge.py"
        racer.write_text("import subprocess, sys\nsubprocess.run([sys.executable, %r, 'stop', 'owner stop'])\n"
                         "print('gap: something')\nprint('FAIL: converge x, 1 gap(s)')\nraise SystemExit(1)\n" % str(loop),
                         encoding="utf-8")
        set_run(judge=str(racer), idle=0, fingerprint=None)
        out, decision = hook(me)
        if decision:
            failures.append(f"a stop during the judge was still blocked once: {decision}")
        if (state().get("state"), state().get("closed_by")) != ("closed", "stop"):
            failures.append(f"a stop during the judge was overwritten: {state().get('state')} {state().get('closed_by')}")
        # idle breaker: nothing changes between stops; an edit to an already dirty file is progress
        restart()
        plan.write_text(head, encoding="utf-8")
        expect("idle 1", me, True)
        if state().get("blocks") != 1:
            failures.append(f"blocks not counted: {state().get('blocks')}")
        fresh_idle = state().get("idle")
        (repo / "src" / "a.py").write_text("a = 3\n", encoding="utf-8")
        expect("an edit to a dirty file is progress", me, True)
        if state().get("idle") != fresh_idle:
            failures.append(f"an edit to a tracked file did not reset idle: {state().get('idle')}")
        (repo / "docs" / "x.md").write_text("caf\xe9 changed\n", encoding="latin-1")
        expect("an edit to an untracked non-UTF-8 file is progress", me, True)
        if state().get("idle") != fresh_idle:
            failures.append(f"an edit to an untracked file did not reset idle: {state().get('idle')}")
        expect("idle 2", me, True)
        expect("idle 3 closes", me, False, "no progress in 3 stops")
        if state().get("closed_by") != "idle":
            failures.append(f"idle close not recorded: {state()}")
        loopcmd("resume")
        expect("after resume it blocks again", me, True)
        loopcmd("ask", "which licence?")
        expect("closed by ask with work left: the session stops", me, False)
        loopcmd("resume")
        set_run(blocks="many")
        out, decision = hook(me)
        if out.returncode != 0 or decision or "loop-stop:" not in out.stderr:
            failures.append(f"an error inside the hook: exit {out.returncode}, {decision}, {out.stderr.strip()!r}")
        set_run(blocks=BLOCK_LIMIT)
        expect("block limit closes", me, False, f"held {BLOCK_LIMIT} stops")
        loopcmd("resume")
        # a plan the judge cannot read
        plan.write_text(head.replace("- check: `true`\n\n### T2", "- bogus line\n\n### T2"), encoding="utf-8")
        expect("unreadable plan blocks with the error", me, True, "cannot read the plan")
        plan.write_text(head, encoding="utf-8")
        # never trap
        s = state()
        set_run(judge=str(Path(tmp) / "missing.py"))
        expect("missing judge", me, False)
        runfile.write_text("{not json", encoding="utf-8")
        expect("broken run file", me, False)
        runfile.write_text(json.dumps({**s, "version": 2}), encoding="utf-8")
        expect("unknown version", me, False)
        runfile.unlink()
        expect("no run file", me, False)
        expect("a session id with a slash", {**me, "session_id": "../x"}, False)
        expect("bad stdin", None, False, raw="not json")
        expect("odd payload", None, False, raw="[1, 2]")
        (Path(tmp) / ".claude" / "1prompt-runs" / "sess-1").write_text("bad\u0000path", encoding="utf-8")
        expect("a NUL byte in the pointer", me, False)
        if list((repo / ".git").glob(".1prompt-run.*")):
            failures.append("a temporary run file was left behind")
    print("FAIL\n" + "\n".join(failures) if failures else "PASS: loop-stop self-test")
    return 1 if failures else 0


def main():
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    try:
        payload = json.loads(sys.stdin.read() or "null")
    except (ValueError, UnicodeDecodeError):
        payload = None
    try:
        result = decide(payload)
    except Exception as error:  # never trap a session
        print(f"loop-stop: {type(error).__name__}: {error}", file=sys.stderr)
        result = None
    if result:
        print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
