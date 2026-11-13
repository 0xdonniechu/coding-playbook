#!/usr/bin/env python3
"""Hooks of the one-prompt loop: hold the session that started a run until its plan converges and its checks pass.

  python3 loop-stop.py                the Stop hook (Claude Code's Stop input on stdin; install.py --settings)
  python3 loop-stop.py subagent-stop  the SubagentStop hook: record a reviewer's verdict in the session's open run
  python3 loop-stop.py --self-test    exit 0 = PASS

The Stop hook acts only when the stopping session has a running run file (`<git dir>/1prompt-run.json`, written by
loop.py start) whose session is the one stopping. Then, in this order:
  1. 40 stops held, or the run's time limit passed: the run closes ("limit") and the session stops;
  2. a subagent of the session still running in the background (the Stop input's `background_tasks`): no decision,
     the session waits and is woken when it ends; not counted as a stop without progress, 10 times in a row at most.
     A background shell is not waited for (a dev server never ends, and nothing would wake the session);
  3. the same fingerprint for the third stop in a row: the run closes ("no progress in 3 stops");
  4. the reviewers' word, task by task: no task's last verdict may be FAIL, a Proof item that names a review needs a
     PASS for some task, and every reviewer FAIL of a task must have its `loop.py fail`. The verdicts come from the
     SubagentStop hook, which records what each run of an agent whose type ends in `reviewer` returned (the first PASS
     or FAIL word of its last message, or, when that has none, of the report it handed back with SubagentHandback
     after its latest prompt) for each plan task named on a prompt line that starts with `loop task: T<n>`
     (`loop tasks: T1, T2`); a verdict that names none is kept but counts for nothing, so a review of other work in the
     same session, given no marker, does not pass this run (the marker is for reviews of the open run's plan only). The run file is a plain file: this guards against haste, not against a session that sets out to
     cheat;
  5. the run's judge, `sdlc-check.py converge <plan> --base <base>`, with `--checks` once step 4 leaves nothing: a
     gap, a failing check or a proof result that is a FAIL blocks the stop and gives the session the list as its next
     work; a plan the judge cannot read blocks with its error. The third round with a failing check closes the run
     ("checks"; the count starts again only at `loop.py resume`);
  6. nothing left: the run closes as done and the session stops.
When a run closed and needs the owner (ask, two fails, idle, limit, checks), the hook comments once on the plan's
Plane ticket (`Plane <KEY-N>` in the plan; `plane.py` beside the judge; waited for, 30 s at most, best effort; a failing check is
named by its task and command, never by its output). When the session's
permission mode asks before tool calls it says so once: such a run waits for the owner at every unknown command.
The session's permission mode is recorded in the run (`mode`) at every stop it judges, for loop-wake.py.
The run is found through ~/.claude/1prompt-runs/<session id> (written by loop.py start), whatever the session's cwd.
The fingerprint is HEAD, the content of every tracked change and untracked file, the plan and the verdicts. Done needs
the judge's own "PASS: converge" line and exit 0: a judge that crashes, times out or prints something else holds the
session with the error (the breakers bound it), never reads as done.
It never traps a session on its own failure: no pointer or run file, another session, a closed run, a broken run file,
a missing judge or any error inside the hook means no decision (exit 0, the session stops), and settings.json runs it
with `|| true`.
Standard library only.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

RUN_FILE = "1prompt-run.json"
IDLE_LIMIT = 3
BLOCK_LIMIT = 40  # stops held per run, whatever moves: a hard cap on a run that never converges
CHECK_FAIL_LIMIT = 3  # rounds with a failing check before the run closes for the owner
WAIT_LIMIT = 10  # stops in a row that may wait for a background subagent before the run is judged anyway
# The judge gives its checks 1500 s in all (SDLC_CHECKS_TOTAL); settings.json gives the hook 1800.
JUDGE_TIMEOUT = int(os.environ.get("LOOP_JUDGE_TIMEOUT", "1620"))
TIMEOUT = 30  # seconds per git call
NEEDS_OWNER = ("ask", "two-fails", "idle", "limit", "checks")
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
    h.update(json.dumps([run.get("fails"), run.get("passes"), run.get("open_fails"), run.get("reviews")], sort_keys=True).encode())
    return h.hexdigest()


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def session_run(payload):
    """(path, run) of the run this hook's session started, open or closed, or None."""
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
    if not isinstance(run, dict) or run.get("version") != 1 or not run.get("session") or run.get("session") != session:
        return None
    return path, run


def notify(run, text):
    """Tells the owner through the plan's Plane ticket; best effort, it never fails the hook. It waits for plane.py (30 s
    at most, only when a run closes): a session woken by loop-wake.py runs in a systemd unit, which kills a detached
    child when the session exits, and the comment with it."""
    try:
        plan = Path(str(run.get("plan")))
        key = re.search(r"\bPlane ([A-Z][A-Z0-9]*-\d+)\b", plan.read_text(encoding="utf-8", errors="replace"))
        plane = Path(str(run.get("judge"))).parent / "plane.py"
        if key and plane.is_file():
            subprocess.run([sys.executable, str(plane), "comment", key[1], "--body",
                            f"1prompt run closed, needs the owner: {text} (plan {plan.name})"],
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass


# A line of its own that starts with the marker (after spaces, `>`, `*`, `-`, `_` or backticks): a phrase quoted inside
# a sentence never counts. Every task id on such a line is named.
TASK_MARK = re.compile(r"^[ \t>*_`#-]*loop tasks?[ \t*_`]*:(.*)$", re.I | re.M)
TASK_LIST = re.compile(r"[ \t*_`]*(T[1-9]\d*(?:[ \t*_`]*(?:,|;|&|and)?[ \t*_`]*T[1-9]\d*)*)", re.I)  # ids up to the first other word


def review_tasks(payload, plan):
    """The plan's tasks a reviewer was asked about: lines of its prompt (the first user message of its transcript) that
    start with `loop task: T<n>` or `loop tasks: T1, T2`. A name the plan does not have counts for nothing."""
    try:
        known = set(re.findall(r"^### (T[1-9]\d*) \(", plan.read_text(encoding="utf-8", errors="replace"), re.M))
        with open(str(payload.get("agent_transcript_path") or ""), encoding="utf-8", errors="replace") as f:
            for _, line in zip(range(50), f):
                entry = json.loads(line)
                if not isinstance(entry, dict) or entry.get("type") != "user":
                    continue
                content = (entry.get("message") or {}).get("content")
                text = content if isinstance(content, str) else "\n".join(
                    str(b.get("text") or "") for b in content or [] if isinstance(b, dict))
                lists = [TASK_LIST.match(line) for line in TASK_MARK.findall(text)]
                named = [t.upper() for m in lists if m for t in re.findall(r"T[1-9]\d*", m[1], re.I)]
                return sorted({t for t in named if t in known}, key=lambda t: int(t[1:]))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return []


def is_prompt(entry):
    """A user entry that is a prompt (a string, or text blocks), not a tool result: it starts a new run of the agent."""
    if entry.get("type") != "user":
        return False
    content = (entry.get("message") or {}).get("content") if isinstance(entry.get("message"), dict) else None
    if isinstance(content, str):
        return bool(content.strip())
    return isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "text" for b in content) \
        and not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def handback_report(payload):
    """The report a subagent handed back with a SubagentHandback tool call (the `message` input) in the run that just
    ended: the last such call after its latest prompt, read from its transcript. A subagent that ends this way has no
    text in its last message, so its verdict is only in this report (APS-73: two reviewer PASSes were recorded as
    `none`). A resumed agent appends to the same transcript, so a handback before the latest prompt belongs to an
    earlier run and never counts. Empty when there is none or anything cannot be read: no verdict, never an error."""
    report = ""
    try:
        with open(str(payload.get("agent_transcript_path") or ""), encoding="utf-8", errors="replace") as f:
            for line in f:
                handback = '"SubagentHandback"' in line
                if not handback and '"user"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if not isinstance(entry, dict):
                    continue
                if is_prompt(entry):
                    report = ""  # a new run starts: an earlier handback is not this run's
                    continue
                if not handback or entry.get("type") != "assistant" or not isinstance(entry.get("message"), dict):
                    continue
                content = entry["message"].get("content")
                for block in content if isinstance(content, list) else []:
                    if (isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "SubagentHandback"
                            and isinstance(block.get("input"), dict)):
                        report = str(block["input"].get("message") or "")
    except Exception:  # the hook never fails a session: anything unreadable means no verdict
        return ""
    return report


def waited_handback(payload):
    """handback_report, polled for a while. Claude Code may still be writing the agent's last transcript lines (its
    SubagentHandback call) when SubagentStop runs: live, two handed-back PASSes were recorded as `none`, and a read of
    the same transcripts a moment later found both reports (APS-75). LOOP_HANDBACK_WAIT seconds: 5 by default and when
    unparsable, at most 20 (the hook has 30), 0 or less reads once."""
    try:
        wait = max(0.0, min(20.0, float(os.environ.get("LOOP_HANDBACK_WAIT", "5"))))
    except ValueError:
        wait = 5.0
    deadline = time.monotonic() + wait
    while True:
        report = handback_report(payload)
        if report or time.monotonic() >= deadline:
            return report
        time.sleep(0.2)


def record_review(payload):
    """SubagentStop: a reviewer's verdict goes into the session's open run. The session cannot write it by hand
    through loop.py, so `pass` and done rest on what a reviewer returned: the first PASS or FAIL word of its last
    message, or, when that has none, of the report it handed back (SubagentHandback)."""
    found = session_run(payload)
    if not found or not str(payload.get("agent_type") or "").endswith("reviewer"):
        return None  # reviewer, hard-reviewer, or a project's own code-reviewer
    if found[1].get("state") != "running":
        return None
    # the verdict is in its last message, or else in its handback, polled while Claude Code finishes writing the
    # transcript (APS-73, APS-75)
    word = (re.search(r"\b(PASS|FAIL)\b", str(payload.get("last_assistant_message") or ""))
            or re.search(r"\b(PASS|FAIL)\b", waited_handback(payload)))
    found = session_run(payload)  # read again after the wait: another reviewer or loop.py may have written meanwhile
    if not found or found[1].get("state") != "running":
        return None
    path, run = found
    reviews = [r for r in run.get("reviews") or [] if isinstance(r, dict)]
    verdict = {"agent": payload["agent_type"], "verdict": word[1] if word else "none", "at": now()}
    tasks = review_tasks(payload, Path(str(run.get("plan"))))
    reviews += [{**verdict, "task": t} for t in tasks] or [{**verdict, "task": None}]  # no task: kept, counts for nothing
    run["reviews"] = reviews[-50:]
    save(path, run)
    return None


def decide(payload):
    """Returns the JSON to print (a dict) or None for no decision."""
    found = session_run(payload)
    if not found:
        return None
    path, run = found
    if run.get("state") == "closed" and run.get("closed_by") in NEEDS_OWNER and not run.get("notified"):
        run["notified"] = True  # closed by loop.py (ask, two fails): the note goes out at the session's next stop
        save(path, run)
        notify(run, str(run.get("reason")))
        return None
    if run.get("state") != "running":
        return None
    plan, judge, base, top = Path(str(run.get("plan"))), Path(str(run.get("judge"))), run.get("base"), run.get("top")
    if not judge.is_file() or not isinstance(base, str) or not isinstance(top, str):
        return None
    fields = ("idle", "fingerprint", "blocks", "waits", "check_fails", "mode_noted", "notified", "state", "closed_by",
              "reason", "closed_at", "mode")
    if isinstance(payload.get("permission_mode"), str):
        run["mode"] = payload["permission_mode"]  # loop-wake.py wakes a dead session only in a mode that does not ask

    def closing(kind, reason, message, ticket=None):
        run.update(state="closed", closed_by=kind, reason=reason, closed_at=now(), notified=kind in NEEDS_OWNER)
        if not save_merged(path, run, fields):
            return None  # closed or restarted meanwhile: that state stands
        if kind in NEEDS_OWNER:
            notify(run, ticket or reason)
        return {"systemMessage": message}

    if run.get("blocks", 0) >= BLOCK_LIMIT:
        return closing("limit", f"held {BLOCK_LIMIT} stops without converging",
                       f"1prompt run closed: held {BLOCK_LIMIT} stops without converging ({plan.name}).")
    deadline = run.get("deadline")
    if isinstance(deadline, str) and deadline and now() > deadline:  # same UTC format on both sides
        return closing("limit", f"time limit reached ({run.get('hours')} h, until {deadline})",
                       f"1prompt run closed: its time limit passed ({deadline}, {plan.name}). `loop.py resume` reopens it.")
    tasks = payload.get("background_tasks")
    waiting = [t for t in tasks if isinstance(t, dict) and t.get("type") == "subagent"
               and t.get("status", "running") == "running"] if isinstance(tasks, list) else []
    if waiting and (run.get("waits") or 0) < WAIT_LIMIT:
        # A subagent of this session still runs in the background (a reviewer, a builder): it ends, and Claude Code
        # then wakes the session. Waiting for it is not idling: let the session stop, WAIT_LIMIT times in a row at
        # most. A background shell is not waited for: a dev server never ends, and nothing would wake the session.
        run["waits"] = (run.get("waits") or 0) + 1
        save_merged(path, run, fields)
        return None
    if not waiting:
        run["waits"] = 0

    mark = fingerprint(top, plan, run)
    run["idle"] = run.get("idle", 0) + 1 if mark == run.get("fingerprint") else 1
    run["fingerprint"] = mark
    if run["idle"] >= IDLE_LIMIT:
        return closing("idle", f"no progress in {IDLE_LIMIT} stops",
                       f"1prompt run closed: no progress in {IDLE_LIMIT} stops ({plan.name}). `loop.py resume` reopens it.")

    # What the run file itself says is left: open review FAILs and the reviewers' word, as the SubagentStop hook
    # recorded it. Only when none of that is left does the judge also run the checks (they are the slow step).
    try:
        tasks_now = set(re.findall(r"^### (T[1-9]\d*) \(", plan.read_text(encoding="utf-8", errors="replace"), re.M))
    except OSError:
        tasks_now = set()
    own = [f"{task} has a review FAIL with no PASS after it" for task in sorted(run.get("open_fails") or [])
           if task in tasks_now]  # a task the plan no longer has cannot be passed: it holds nothing
    # a verdict counts for its task, while the plan still has that task
    reviews = [r for r in run.get("reviews") or [] if isinstance(r, dict) and r.get("task") in tasks_now]
    lasts = {r["task"]: r.get("verdict") for r in reviews}
    fails = run.get("fails") if isinstance(run.get("fails"), dict) else {}
    untold = {t: sum(1 for r in reviews if r["task"] == t and r.get("verdict") == "FAIL")
              - len(fails.get(t) if isinstance(fails.get(t), list) else []) for t in lasts}
    try:
        proof = re.search(r"^## Proof\b.*?(?=^## |\Z)", plan.read_text(encoding="utf-8", errors="replace"), re.M | re.S)
    except OSError:
        proof = None
    for task in sorted(lasts, key=lambda t: int(t[1:])):
        if untold[task] > 0:
            own.append(f"{task}: {untold[task]} reviewer FAIL(s) on record without a `loop.py fail {task} \"<reason>\"`: "
                       "record each (the second FAIL of one task ends the run)")
        if lasts[task] == "FAIL":
            own.append(f"{task}: the last reviewer verdict on record for it is FAIL: fix its issues and have it reviewed again")
    if "PASS" not in lasts.values() and proof and re.search(r"\breview(er|ers|ed|s|ing)?\b", proof[0], re.I):
        own.append("the plan's Proof names a review and no reviewer PASS for a task is on record: run the reviewer agent "
                   "with `loop task: T<n>` in its prompt (its verdict is recorded for that task when it ends)")
    try:
        out = subprocess.run([sys.executable, str(judge), "converge", str(plan), "--base", base, *([] if own else ["--checks"])],
                             capture_output=True, text=True, timeout=JUDGE_TIMEOUT, cwd=top)
        code, stdout, stderr = out.returncode, out.stdout, out.stderr
    except subprocess.TimeoutExpired:
        code, stdout, stderr = None, "", f"the judge and its checks took over {JUDGE_TIMEOUT} s"
    lines = stdout.splitlines()
    summary = lines[-1] if lines else ""
    gaps = [l[len("gap: "):] for l in lines if l.startswith("gap: ")]
    gaps += [l for l in lines if l.startswith("proof ") and l.endswith("recorded FAIL")]
    gaps += [l for l in lines if l.endswith("no `## Tasks` section; nothing to compare")]
    passed = code == 0 and summary.startswith("PASS: converge")
    judged = passed or (code == 1 and summary.startswith("FAIL: converge"))
    if code == 2:
        gaps = [f"the judge cannot read the plan: {stderr.strip()[:300]}"]
    elif not judged or (not gaps and not passed):  # a crash, a timeout or output not in the judge's format
        gaps = [f"the judge did not give a verdict (exit {code}): {(stderr or stdout).strip()[-300:]}; do not edit "
                "the judge: end the run with `loop.py stop \"judge broken\"` and tell the owner"]
    else:
        gaps += own
    failing = [g for g in gaps if g.startswith("check failed: ")]
    if failing:
        run["check_fails"] = run.get("check_fails", 0) + 1 if isinstance(run.get("check_fails"), int) else 1
        if run["check_fails"] >= CHECK_FAIL_LIMIT:
            first = failing[0][len("check failed: "):]
            named = re.split(r" \(exit | took over | not run: ", first)[0]  # the task and its command, not its output
            return closing("checks", f"checks failed {CHECK_FAIL_LIMIT} rounds: {first[:300]}",
                           f"1prompt run closed: its checks failed {CHECK_FAIL_LIMIT} rounds ({plan.name}). "
                           "`loop.py resume` reopens it.", ticket=f"checks failed {CHECK_FAIL_LIMIT} rounds: {named}")
    if gaps:
        run["blocks"] = run.get("blocks", 0) + 1
        note = None
        if payload.get("permission_mode") == "default" and not run.get("mode_noted"):
            run["mode_noted"] = True
            note = ("1prompt run: this session asks before tool calls (permission mode `default`), so it will wait for "
                    "you at every command it does not know. For a run nobody watches, start the session in a mode "
                    "that does not ask (acceptEdits with an allowlist, or bypassPermissions behind the boundary hooks).")
        if not save_merged(path, run, fields):
            return None  # closed or restarted while the judge ran: let the session stop
        listed = "\n".join(f"- {g}" for g in gaps[:20]) + (f"\n- … {len(gaps) - 20} more" if len(gaps) > 20 else "")
        return {"decision": "block", "reason":
                f"1prompt run open on {plan.name}: {len(gaps)} item(s) left before the goal is done.\n{listed}\n"
                "Continue with the next one (rate, dispatch or do it, gate, review; a reviewer's prompt names its task as "
                "`loop task: T<n>`, or its verdict counts for nothing). Record each review with "
                "`loop.py pass <task>` or `loop.py fail <task> \"<reason>\"` (`pass` needs a reviewer PASS on record; the second FAIL of a task, or the third round of failing checks, ends the run). "
                "A path outside every task that is not this work's (the owner's file, another change): do not delete "
                "it or widen the plan yourself; ask. A question only the owner can answer: "
                "`loop.py ask \"<question>\"`. To end the run: `loop.py stop`.",
                **({"systemMessage": note} if note else {})}
    return closing("done", "goal done: the plan converges and its checks pass",
                   f"1prompt run done: {plan.name} converges and its checks pass (no gap, no FAIL).")


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
        env = {**os.environ, "CLAUDE_CODE_SESSION_ID": "sess-1", "HOME": tmp, "USERPROFILE": tmp, "LOOP_HANDBACK_WAIT": "1"}
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
        def sub(agent, message, session="sess-1", prompt="Review the change.\nloop task: T1", later=None, handback=None,
                delay=None):  # as Claude Code calls it; delay: the ending reaches the transcript that many seconds late
            transcript = Path(tmp) / f"agent-{os.urandom(4).hex()}.jsonl"
            # handback: the agent ends with a SubagentHandback tool call carrying its report, then its tool result
            ending = (json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "SubagentHandback",
                                                                               "input": {"message": handback}}]}}) + "\n"
                      + json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "content": "delivered"}]}}) + "\n"
                      if handback is not None else
                      json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": message}]}}) + "\n")
            transcript.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": prompt}}) + "\n"
                                  + (json.dumps({"type": "user", "message": {"content": later}}) + "\n" if later else "")
                                  + ("" if delay else ending))
            if delay:  # APS-75: Claude Code may write the handback while SubagentStop already runs
                def append_late():
                    with open(transcript, "a", encoding="utf-8") as f:
                        f.write(ending)
                threading.Timer(delay, append_late).start()
            out = subprocess.run([sys.executable, __file__, "subagent-stop"], capture_output=True, text=True, timeout=60, env=env,
                                 input=json.dumps({"session_id": session, "agent_type": agent, "last_assistant_message": message,
                                                   "agent_transcript_path": str(transcript)}))
            if out.returncode != 0 or out.stdout.strip():
                failures.append(f"subagent-stop {agent}: exit {out.returncode}, printed {out.stdout.strip()[:100]!r}")

        if loopcmd("pass", "T1").returncode != 1:
            failures.append("pass was accepted with no reviewer verdict on record")
        sub("builder", "PASS: all built")
        sub("reviewer", "PASS", session="other")
        if state().get("reviews"):
            failures.append(f"a verdict was recorded from a builder or another session: {state().get('reviews')}")
        sub("hard-reviewer", "**FAIL** (one MAJOR). The round 1 PASS was wrong.")
        sub("reviewer", "I could not read the diff.")
        if [r.get("verdict") for r in state().get("reviews", [])] != ["FAIL", "none"]:
            failures.append(f"reviewer verdicts not recorded as FAIL, none: {state().get('reviews')}")
        # APS-73: a reviewer that hands its report back (SubagentHandback) has no text in its last message
        sub("reviewer", "Done.", handback="")  # an empty report: still no verdict
        sub("reviewer", "", handback="**PASS** (loop task: T1)\n\nNo BLOCKER or MAJOR.")
        if [r.get("verdict") for r in state().get("reviews", [])][-2:] != ["none", "PASS"]:
            failures.append(f"handed-back verdicts not recorded as none, PASS: {state().get('reviews')[-2:]}")
        # APS-75: the handback reaches the transcript after SubagentStop started: still recorded
        sub("reviewer", "Done.")
        sub("reviewer", "", handback="**PASS** (late)", delay=0.5)
        if [r.get("verdict") for r in state().get("reviews", [])][-2:] != ["none", "PASS"]:
            failures.append(f"a late handback not recorded as PASS: {state().get('reviews')[-2:]}")
        started = time.monotonic()
        sub("reviewer", "", handback="**PASS** (soon)", delay=0.2)
        if time.monotonic() - started > 0.8:  # polled, not one read after the whole wait
            failures.append(f"a handback 0.2 s late took {time.monotonic() - started:.1f} s to record")
        started = time.monotonic()
        sub("reviewer", "**PASS** at once")
        if time.monotonic() - started > 0.8:  # a verdict in the last message: no wait
            failures.append(f"a verdict in the last message waited {time.monotonic() - started:.1f} s")
        sub("reviewer", "Done.")
        sub("reviewer", "I have everything for the verdict.", handback="**PASS** (text, then a late handback)", delay=0.5)
        if [r.get("verdict") for r in state().get("reviews", [])][-2:] != ["none", "PASS"]:
            failures.append(f"text then a late handback: not PASS: {state().get('reviews')[-1:]}")
        # APS-75 review: a verdict written while another reviewer's hook waits is kept
        waiting = threading.Thread(target=sub, args=("reviewer", ""))
        waiting.start()
        time.sleep(0.4)
        sub("hard-reviewer", "**PASS** (written while another hook waits)")
        waiting.join()
        if [(r.get("agent"), r.get("verdict")) for r in state().get("reviews", [])][-2:] != [("hard-reviewer", "PASS"), ("reviewer", "none")]:
            failures.append(f"a verdict written during another hook's wait was lost: {state().get('reviews')[-2:]}")
        started = time.monotonic()
        sub("reviewer", "", handback="**PASS** (too late)", delay=4)
        if time.monotonic() - started > 3.2 or [r.get("verdict") for r in state().get("reviews", [])][-1:] != ["none"]:
            failures.append(f"a handback later than LOOP_HANDBACK_WAIT: not none, or the hook waited past it: "
                            f"{state().get('reviews')[-1:]}, {time.monotonic() - started:.1f} s")
        sub("reviewer", "**PASS**: no BLOCKER or MAJOR.")
        if loopcmd("pass", "T1").returncode != 0:
            failures.append("pass was refused after a reviewer PASS")
        expect("converged: done", me, False, "run done")
        if (state().get("state"), state().get("closed_by")) != ("closed", "done"):
            failures.append(f"done not recorded: {state()}")
        expect("closed run", me, False)
        on_record = len(state().get("reviews", []))
        sub("reviewer", "FAIL")
        if len(state().get("reviews", [])) != on_record:
            failures.append("a verdict was recorded into a closed run")
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
        # APS-73: a FAIL handed back (SubagentHandback, no text in the last message) is recorded as FAIL
        sub("reviewer", "", handback="**FAIL**\n\n1. MAJOR: the PASS path is untested.")
        if [r.get("verdict") for r in state().get("reviews", [])][-1:] != ["FAIL"]:
            failures.append(f"a handed-back FAIL not recorded as FAIL: {state().get('reviews')[-1:]}")
        # APS-73 edge cases, written as Claude Code writes an agent transcript (one JSON entry per line)
        def raw(lines, message="", transcript_path=None):
            transcript = transcript_path or Path(tmp) / f"agent-{os.urandom(4).hex()}.jsonl"
            if transcript_path is None:
                transcript.write_text("".join((l if isinstance(l, str) else json.dumps(l)) + "\n" for l in lines), encoding="utf-8")
            subprocess.run([sys.executable, __file__, "subagent-stop"], capture_output=True, text=True, timeout=60, env=env,
                           input=json.dumps({"session_id": "sess-1", "agent_type": "reviewer", "last_assistant_message": message,
                                             "agent_transcript_path": str(transcript)}))
            return (state().get("reviews") or [{}])[-1].get("verdict")
        prompt = {"type": "user", "message": {"role": "user", "content": "Review it.\nloop task: T1"}}
        def hb(text, kind="assistant", name="SubagentHandback"):
            return {"type": kind, "message": {"content": [{"type": "tool_use", "name": name, "input": {"message": text}}]}}
        result = {"type": "user", "message": {"content": [{"type": "tool_result", "content": "delivered"}]}}
        text = lambda t: {"type": "assistant", "message": {"content": [{"type": "text", "text": t}]}}
        for name, lines, message, want in (
                ("two handbacks: the last one counts", [prompt, hb("FAIL: first"), result, hb("**PASS**"), result], "", "PASS"),
                ("a resumed run with no verdict does not replay the earlier PASS",
                 [prompt, hb("**PASS**"), result, {"type": "user", "message": {"content": "Re-review after the new commit."}},
                  text("I found a major problem in x.py:10.")], "I found a major problem in x.py:10.", "none"),
                ("a resumed run (text-block prompt) does not replay the earlier FAIL",
                 [prompt, hb("**FAIL**"), result, {"type": "user", "message": {"content": [{"type": "text", "text": "Again."}]}}],
                 "", "none"),
                ("a resumed run's own handback counts",
                 [prompt, hb("**FAIL**"), result, {"type": "user", "message": {"content": "Again."}}, hb("**PASS**"), result], "", "PASS"),
                ("a bad JSON line is skipped", [prompt, '{"type": "assistant", "SubagentHandback" broken', hb("PASS")], "", "PASS"),
                ("another tool's input is not a report", [prompt, hb("PASS", name="Bash")], "", "none"),
                ("another tool naming SubagentHandback in its input is not a report",
                 [prompt, {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash",
                                                                         "input": {"message": "PASS", "note": "SubagentHandback"}}]}}], "", "none"),
                ("a block that is not a tool_use is not a report",
                 [prompt, {"type": "assistant", "message": {"content": [{"type": "text", "name": "SubagentHandback",
                                                                         "input": {"message": "PASS"}}]}}], "", "none"),
                ("a tool_use in a user entry is not the agent's", [prompt, hb("PASS", kind="user")], "", "none"),
                ("a message that is not an object", [prompt, {"type": "assistant", "message": "SubagentHandback PASS"}], "", "none"),
                ("the last message's word wins over the handback", [prompt, hb("PASS"), text("FAIL: one MAJOR")], "FAIL: one MAJOR", "FAIL"),
                ("deeply nested JSON is skipped", [prompt, '{"type": "user", "x": ' + "[" * 5000 + "]" * 5000 + "}", hb("PASS")], "", "PASS")):
            got = raw(lines, message)
            if got != want:
                failures.append(f"{name}: recorded {got}, expected {want}")
        if raw([], "", transcript_path=Path(tmp) / "no-such-transcript.jsonl") != "none":
            failures.append("a missing transcript did not record none")
        set_run(reviews=[])
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
        # the reviewers' word at done time: a last FAIL is never done; a Proof that names a review needs a PASS
        restart()
        set_run(reviews=[{"agent": "reviewer", "verdict": "PASS", "at": "t", "task": "T1"},
                         {"agent": "reviewer", "verdict": "FAIL", "at": "t", "task": "T1"}])
        expect("the last reviewer verdict is FAIL: not done", me, True, "T1: the last reviewer verdict on record for it is FAIL")
        set_run(reviews=[{"agent": "reviewer", "verdict": "FAIL", "at": "t", "task": "T2"},
                         {"agent": "reviewer", "verdict": "PASS", "at": "t", "task": "T1"}], fails={"T2": ["x"]},
                idle=0, fingerprint=None)
        expect("a later PASS of T1 does not hide T2's last FAIL", me, True, "T2: the last reviewer verdict on record for it is FAIL")
        set_run(reviews=[{"agent": "reviewer", "verdict": "FAIL", "at": "t", "task": "T1"},
                         {"agent": "reviewer", "verdict": "PASS", "at": "t", "task": "T1"},
                         {"agent": "reviewer", "verdict": "PASS", "at": "t", "task": "T2"}], fails={"T2": ["x"]},
                idle=0, fingerprint=None)
        expect("a `fail` of T2 does not stand for T1's FAIL", me, True, "T1: 1 reviewer FAIL(s) on record without")
        set_run(reviews=[{"agent": "reviewer", "verdict": "FAIL", "at": "t", "task": "T2"},
                         {"agent": "reviewer", "verdict": "PASS", "at": "t", "task": "T2"}], fails={}, idle=0, fingerprint=None)
        out, d = hook(me)
        if not d or "T2: 1 reviewer FAIL(s)" not in d.get("reason", "") or "T1: 1 reviewer FAIL" in d.get("reason", ""):
            failures.append(f"a FAIL of T2 was not counted for T2 alone: {d}")
        set_run(reviews=[{"agent": "reviewer", "verdict": "FAIL", "at": "t", "task": "T1"},
                         {"agent": "reviewer", "verdict": "PASS", "at": "t", "task": "T1"},
                         {"agent": "reviewer", "verdict": "FAIL", "at": "t", "task": "T2"},
                         {"agent": "reviewer", "verdict": "PASS", "at": "t", "task": "T2"}], fails={"T1": ["x"]},
                idle=0, fingerprint=None)
        out, d = hook(me)
        if not d or "T2: 1 reviewer FAIL(s)" not in d.get("reason", "") or "T1: " in d.get("reason", ""):
            failures.append(f"FAILs were not counted task by task against their own `fail` records: {d}")
        set_run(reviews=[], fails={"T3": ["x"]}, open_fails=["T3"], idle=0, fingerprint=None)
        expect("an open FAIL of a task the plan no longer has does not hold the run", me, False, "run done")
        restart()
        set_run(reviews=[{"agent": "reviewer", "verdict": "FAIL", "at": "t", "task": "T3"}], fails={}, idle=0, fingerprint=None)
        expect("a FAIL of a task the plan no longer has does not hold the run", me, False, "run done")
        restart()
        set_run(reviews=[{"agent": "reviewer", "verdict": "FAIL", "at": "t", "task": None}], fails={}, idle=0, fingerprint=None)
        expect("a FAIL that names no task counts for nothing: done", me, False, "run done")
        restart()
        for wording in ("Reviewer PASS on the branch", "both reviews pass"):
            plan.write_text(head.replace("1. it works\n", f"1. it works\n2. {wording}\n") + "1. PASS it works\n2. PASS\n",
                            encoding="utf-8")
            set_run(reviews=[], idle=0, fingerprint=None)
            expect(f"Proof says {wording!r}: a reviewer PASS is needed", me, True, "no reviewer PASS for a task is on record")
        for name, reviews in (("none on record", []),
                              ("only one that gave no verdict", [{"agent": "reviewer", "verdict": "none", "task": "T1"}]),
                              ("only a PASS that names no task", [{"agent": "reviewer", "verdict": "PASS", "task": None}])):
            set_run(reviews=reviews, idle=0, fingerprint=None)
            expect(f"Proof names a review, {name}: not done", me, True, "no reviewer PASS for a task is on record")
        sub("reviewer", "PASS", prompt="Review APS-60's check.py change.")  # other work in the same session
        sub("reviewer", "PASS", prompt="loop task: T9")  # a task the plan does not have
        if [r.get("task") for r in state().get("reviews", [])][-2:] != [None, None]:
            failures.append(f"a verdict naming no task of the plan was tied to one: {state().get('reviews')}")
        expect("Proof names a review, PASSes for no task of the plan: not done", me, True, "no reviewer PASS for a task")
        sub("reviewer", "PASS", prompt="Docs for another plan say (or `loop tasks: T1, T2`) inline; no marker line.")
        sub("reviewer", "PASS", prompt="Review it.", later="loop task: T1")  # only the first user message is the prompt
        if [r.get("task") for r in state().get("reviews", [])][-2:] != [None, None]:
            failures.append(f"a quoted marker or one in a later message was counted: {state().get('reviews')}")
        for prompt, want in (("**Loop task:** `T1`", ["T1"]), ("loop tasks: T1 and T2", ["T1", "T2"]),
                             ("- loop task: T2", ["T2"]), ("_loop task_: T1", ["T1"]), ("**loop task**: T2", ["T2"]),
                             ("## loop task: T1", ["T1"]), ("loop task: T1 (not T2, reviewed apart)", ["T1"]),
                             ([{"type": "text", "text": "Review."}, {"type": "text", "text": "loop task: T1"}], ["T1"]),
                             ("loop task: T2\nmore\n> loop task: T1", ["T1", "T2"]),
                             ([{"type": "text", "text": "Review.\nloop task: T2"}], ["T2"])):
            before = len(state().get("reviews", []))
            sub("reviewer", "none yet", prompt=prompt)
            got = [r.get("task") for r in state().get("reviews", [])[before:]]
            if got != want:
                failures.append(f"marker {prompt!r}: recorded for {got}, not {want}")
        sub("code-reviewer", "PASS", prompt="loop tasks: T1, t2 (both)")  # a project's own reviewer counts too
        if [r.get("task") for r in state().get("reviews", [])][-2:] != ["T1", "T2"]:
            failures.append(f"a review of two tasks was not recorded for each: {state().get('reviews')}")
        expect("Proof names a review and a reviewer PASS is on record: done", me, False, "run done")
        restart()
        plan.write_text(head.replace("1. it works\n", "1. the preview page renders\n") + "1. PASS it does\n", encoding="utf-8")
        expect("a Proof with the word preview names no review: done", me, False, "run done")
        # a reviewer FAIL that the session did not record with `loop.py fail` is never hidden by a later PASS; and the
        # checks, the slow step, do not run while the run file itself still lists something
        restart()
        flag = Path(tmp) / "checked.flag"
        plan.write_text(head.replace("- check: `true`\n\n### T2", f"- check: `touch {flag}`\n\n### T2") + "1. PASS it works\n",
                        encoding="utf-8")
        sub("reviewer", "FAIL: T2 is wrong", prompt="loop task: T2")
        sub("reviewer", "PASS", prompt="loop task: T2")
        expect("a reviewer FAIL without its `loop.py fail`: not done", me, True, "T2: 1 reviewer FAIL(s) on record without")
        if flag.exists():
            failures.append("the checks ran while the run file still listed something")
        loopcmd("fail", "T2", "wrong")
        set_run(idle=0, fingerprint=None)
        expect("the FAIL recorded, its task still open", me, True, "T2 has a review FAIL with no PASS after it")
        loopcmd("pass", "T2")
        expect("recorded, passed again: done", me, False, "run done")
        if not flag.exists():
            failures.append("the checks did not run before done")
        # failing checks: a gap each round, the third round closes the run for the owner; resume reopens it
        restart()
        plan.write_text(head.replace("- check: `true`\n\n### T2", "- check: `echo boom; false`\n\n### T2") + "1. PASS it works\n",
                        encoding="utf-8")
        for i in (1, 2):
            set_run(idle=0, fingerprint=None)
            expect(f"failing check round {i}", me, True, "check failed: T1 `echo boom; false` (exit 1): boom")
        set_run(idle=0, fingerprint=None)
        expect("the third failing round closes", me, False, "checks failed 3 rounds")
        if (state().get("closed_by"), state().get("check_fails")) != ("checks", 3):
            failures.append(f"three failing check rounds not recorded: {state().get('closed_by')} {state().get('check_fails')}")
        plan.write_text(head + "1. PASS it works\n", encoding="utf-8")
        if loopcmd("resume").returncode != 0 or state().get("check_fails") != 0:
            failures.append("resume after three failing check rounds did not reopen with the count at zero")
        expect("after resume with the check fixed: done", me, False, "run done")
        # the time limit
        restart()
        set_run(deadline="2000-01-01T00:00Z")
        expect("past the time limit", me, False, "time limit passed")
        if state().get("closed_by") != "limit":
            failures.append(f"the time limit did not close the run: {state().get('closed_by')}")
        # the owner is told once, on the plan's ticket, when a run closed and needs them (a fake plane.py beside the judge)
        scripts = Path(tmp) / "scripts"
        scripts.mkdir()
        (scripts / "sdlc-check.py").write_text(f"import runpy, sys\nsys.argv[0] = {str(judge)!r}\n"
                                               f"runpy.run_path({str(judge)!r}, run_name='__main__')\n", encoding="utf-8")
        said = Path(tmp) / "plane.log"
        (scripts / "plane.py").write_text(f"import sys\nopen({str(said)!r}, 'a').write(' '.join(sys.argv[1:]) + chr(10))\n",
                                          encoding="utf-8")

        def comments(n):
            deadline = datetime.now(timezone.utc).timestamp() + 5
            while datetime.now(timezone.utc).timestamp() < deadline and (not said.exists() or len(said.read_text().splitlines()) < n):
                subprocess.run(["sleep", "0.1"])
            return said.read_text().splitlines() if said.exists() else []

        restart()
        plan.write_text(head.replace("# Work", "# Work\n\nTicket: Plane TST-7."), encoding="utf-8")
        set_run(judge=str(scripts / "sdlc-check.py"), deadline="2000-01-01T00:00Z")
        hook(me)
        if not said.exists():  # read at once: the hook waits for the comment (a woken session's unit kills a detached one)
            failures.append("the hook returned before its ticket comment was written")
        if len(comments(1)) != 1 or not comments(1)[0].startswith("comment TST-7 --body 1prompt run closed, needs the owner: time limit"):
            failures.append(f"the time limit close did not comment on the ticket: {comments(1)}")
        if not state().get("notified"):
            failures.append("a hook close that needs the owner is not marked as told")
        loopcmd("resume")
        loopcmd("ask", "which licence?")
        hook(me)
        hook(me)
        subprocess.run(["sleep", "0.5"])
        if len(comments(2)) != 2 or "needs the owner: which licence?" not in comments(2)[1]:
            failures.append(f"an ask was not commented once at the next stop: {comments(2)}")
        loopcmd("resume")
        loopcmd("stop", "by hand")
        hook(me)
        restart()
        set_run(judge=str(scripts / "sdlc-check.py"))
        plan.write_text(head.replace("# Work", "# Work\n\nTicket: Plane TST-7.") + "1. PASS it works\n", encoding="utf-8")
        expect("done with a ticket", me, False, "run done")
        subprocess.run(["sleep", "0.5"])
        if len(comments(2)) != 2:
            failures.append(f"a stop by hand or done commented on the ticket: {comments(2)}")
        restart()  # three failing check rounds: the ticket gets the task and the command, never the command's output
        (repo / "src" / "t.sh").write_text("echo leaked-output\nexit 1\n", encoding="utf-8")
        plan.write_text(head.replace("# Work", "# Work\n\nTicket: Plane TST-7.").replace(
            "- check: `true`\n\n### T2", "- check: `sh src/t.sh`\n\n### T2") + "1. PASS it works\n", encoding="utf-8")
        for i in range(3):
            set_run(judge=str(scripts / "sdlc-check.py"), idle=0, fingerprint=None)
            hook(me)
        last = comments(3)[-1] if len(comments(3)) == 3 else ""
        if "checks failed 3 rounds: T1 `sh src/t.sh`" not in last or "leaked-output" in last or "leaked-output" not in state().get("reason", ""):
            failures.append(f"the checks close did not name the check on the ticket without its output: {comments(3)}")
        (repo / "src" / "t.sh").unlink()
        # a session that asks before tool calls is told once
        restart()
        plan.write_text(head, encoding="utf-8")
        asking = {**me, "permission_mode": "default"}
        d = expect("mode note", asking, True, "asks before tool calls")
        (repo / "src" / "a.py").write_text("a = 7\n", encoding="utf-8")
        d = expect("mode note only once", asking, True)
        if d and "systemMessage" in d:
            failures.append("the permission mode note was repeated")
        restart()
        d = expect("no mode note in a mode that does not ask", {**me, "permission_mode": "bypassPermissions"}, True)
        if d and "systemMessage" in d:
            failures.append("a session that does not ask got the permission mode note")
        if state().get("mode") != "bypassPermissions":
            failures.append(f"the session's permission mode was not recorded for loop-wake: {state().get('mode')!r}")
        # idle breaker: nothing changes between stops; an edit to an already dirty file is progress
        restart()
        plan.write_text(head, encoding="utf-8")
        waiting = {**me, "background_tasks": [{"id": "a1", "type": "subagent", "status": "running", "agent_type": "reviewer"}]}
        for i in range(4):  # a reviewer in the background: the session waits, the run stays open and is not idle
            expect(f"waiting for a background subagent {i}", waiting, False)
        if (state().get("state"), state().get("idle"), state().get("blocks"), state().get("waits")) != ("running", 0, 0, 4):
            failures.append(f"waiting for a background subagent was counted: {state().get('state')} idle {state().get('idle')} "
                            f"blocks {state().get('blocks')} waits {state().get('waits')}")
        set_run(waits=WAIT_LIMIT)
        expect("a subagent waited for too long: judged anyway", waiting, True)
        set_run(waits=3, idle=0, blocks=0, fingerprint=None)
        expect("a subagent that has ended is not waited for",
               {**me, "background_tasks": [{"id": "a1", "type": "subagent", "status": "completed"}]}, True)
        set_run(waits=3, idle=0, blocks=0, fingerprint=None)
        expect("a background shell is not waited for (a dev server never ends)",
               {**me, "background_tasks": [{"id": "b1", "type": "shell", "status": "running"}]}, True)
        if state().get("waits") != 0:
            failures.append(f"a stop that did not wait kept the wait count: {state().get('waits')}")
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
        sub("reviewer", "FAIL: one issue")
        expect("a reviewer's verdict is progress", me, True)
        if state().get("idle") != fresh_idle:
            failures.append(f"a reviewer's verdict did not reset idle: {state().get('idle')}")
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
        result = record_review(payload) if sys.argv[1:] == ["subagent-stop"] else decide(payload)
    except Exception as error:  # never trap a session
        print(f"loop-stop: {type(error).__name__}: {error}", file=sys.stderr)
        result = None
    if result:
        print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
