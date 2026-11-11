#!/usr/bin/env python3
"""Wake a one-prompt run whose session died: fork that session headless, within caps, and tell the owner.

  python3 loop-wake.py tick [--dry-run]   one pass over the open runs (the systemd user timer runs it every 10 min);
                                          --dry-run only prints what it would do
  python3 loop-wake.py install            write and start the user timer (1prompt-wake.timer) for this copy
  python3 loop-wake.py uninstall          stop and remove it
  python3 loop-wake.py child <run file> <old session> <new session> <budget> <day>
                                          (started by tick in its own systemd unit) run the woken session, then
                                          record its cost
  python3 loop-wake.py --self-test        exit 0 = PASS

A run (loop.py start) lives in its session; when that session dies (crash, out of memory, HTTP 429, a spent quota, a
closed window) the run stays open and nothing picks it up. For each pointer in ~/.claude/1prompt-runs/ whose run is
running and bound to that session, tick acts only when the session is quiet: its transcript and every file under its
folder (subagents) unchanged for 30 minutes (LOOP_WAKE_QUIET_MIN), and no live record in ~/.claude/sessions/ marked
busy. A wake whose session never started (the unit failed, the CLI was missing) counts as quiet from that wake, and the
next one forks its source again. Then, in this order:
  1. the run's time limit passed: the run closes ("limit") and the plan's Plane ticket gets a comment;
  2. the permission mode (recorded by the Stop hook, else the transcript's last) asks before tool calls or is unknown,
     or 1prompt's boundary settings (~/.claude/hooks/1prompt/autonomous-settings.json) are missing: not woken, and the
     ticket is told once (a headless session cannot answer a permission prompt, and never runs without the boundary);
  3. 4 wakes used: the run closes ("limit"); before the run's `next_wake`: not yet (waits of 30, 60, 120 minutes);
  4. less than $1 left of the day's $50 of wake spend (LOOP_WAKE_DAILY_USD, decision 2 of the 1prompt design): the
     run closes ("limit");
  5. else the run is bound to a new session id first (its pointer moved, so the old session, if still open somewhere,
     is no longer held), a budget of $20 at most (LOOP_WAKE_RUN_USD) is reserved in the day's ledger, and
     `claude -p --resume <old> --fork-session --session-id <new> --settings <boundary>` runs in a systemd unit named
     after the run (MemoryMax=8G, RuntimeMaxSec up to the run's time limit), in the session's own working directory and
     model, in its mode, with `--max-budget-usd` = that budget; the ticket is told. A fork, never a second writer.
The child turns the reservation into the CLI's `total_cost_usd` in the ledger (~/.claude/1prompt-runs/.wake-spend.json),
on the reservation's day; killed first, or with no cost in the CLI's output, the whole reservation stays spent. It adds the cost to the run (`wake_cost`) and appends one line to
`<git dir>/1prompt-wake.log` (never the session's output to the ticket). Ticket comments wait for plane.py (30 s at
most): the timer's oneshot service would kill a detached one. `install` runs only from the installed copy
(~/.claude/hooks/loop/), so the timer never runs a checkout whose branch changes.
A woken session counts as busy while its unit runs (a headless session writes no ~/.claude/sessions record).
LOOP_WAKE_CLAUDE names the claude CLI to run (default: `claude` on PATH). A ledger that cannot be read counts as the
day's cap reached. Standard library only; Linux with systemd user units (without systemd-run nothing is woken).
"""
import fcntl
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUIET_MIN = float(os.environ.get("LOOP_WAKE_QUIET_MIN", "30"))
DAILY_CAP = float(os.environ.get("LOOP_WAKE_DAILY_USD", "50"))
WAKE_USD = float(os.environ.get("LOOP_WAKE_RUN_USD", "20"))  # budget of one wake, reserved in the ledger at start
MIN_USD = 1.0  # less than this left today: no wake
WAKE_LIMIT = 4
BACKOFF_MIN = 30  # wait after wake n: 30 × 2^(n-1) minutes
WAKE_MODES = ("acceptEdits", "auto", "bypassPermissions", "dontAsk")  # modes that never wait for a person
DEFAULT_HOURS = 12  # unit runtime when a run has no time limit
UNIT = "1prompt-wake"
SESSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z_-]*$")


def claude_dir():
    return Path.home() / ".claude"


def now(minutes=0):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%MZ")


def stop_hook():
    """loop-stop.py beside this file: its run lookup and atomic save are the single source."""
    spec = importlib.util.spec_from_file_location("loop_stop", HERE / "loop-stop.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def transcript(session):
    hits = sorted((claude_dir() / "projects").glob(f"*/{session}.jsonl")) if SESSION_RE.match(session) else []
    return hits[0] if hits else None


def last_activity(path):
    """Newest mtime of the transcript and of every file under its session folder (subagents write there)."""
    newest = path.stat().st_mtime
    folder = path.with_suffix("")
    if folder.is_dir():
        for f in folder.rglob("*"):
            try:
                newest = max(newest, f.stat().st_mtime)
            except OSError:
                pass
    return newest


def session_facts(path):
    """(cwd, model, mode): the first cwd the transcript records (its project folder), the last model that answered and
    the last permission mode a prompt ran in (for a session that died before its first stop recorded `mode`)."""
    cwd = model = mode = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            if cwd is None and isinstance(entry.get("cwd"), str):
                cwd = entry["cwd"]
            if isinstance(entry.get("permissionMode"), str):
                mode = entry["permissionMode"]
            message = entry.get("message")
            if entry.get("type") == "assistant" and isinstance(message, dict) \
                    and str(message.get("model") or "").startswith("claude-"):
                model = message["model"]
    return cwd, model, mode


def alive(pid, started):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    try:  # a reused pid: its start time differs from the record's
        stat = Path(f"/proc/{pid}/stat").read_text()
        return not started or stat.rsplit(")", 1)[1].split()[19] == str(started)
    except (OSError, IndexError):
        return True


def busy(session):
    for record in (claude_dir() / "sessions").glob("*.json"):
        try:
            d = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("sessionId") == session and d.get("status") == "busy" \
                and isinstance(d.get("pid"), int) and alive(d["pid"], d.get("procStart")):
            return True
    return False


def unit_active(run):
    """A unit of one of the run's wakes still runs (any wake number, so a resume that reset the count still sees an old
    fork): a headless `claude -p` writes no record in ~/.claude/sessions/, and its transcript may sit unchanged through a
    long command. Anything but a clear answer from systemd (no user bus, a timeout) counts as running."""
    try:
        out = subprocess.run(["systemctl", "--user", "list-units", f"{UNIT}-{run.get('run_id')}-*", "--state=active",
                              "--no-legend", "--plain"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return "unknown" if out.returncode != 0 else bool(out.stdout.strip())


def ledger_update(add=0.0, day=None):
    """A day's wake spend (UTC, today by default), with `add` added under a lock; returns the new total."""
    runs = claude_dir() / "1prompt-runs"
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / ".wake-spend.json"
    with open(runs / ".wake-spend.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            book = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            book = None
        day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            total = max(0.0, float(book.get(day) or 0) + add)  # a settle with no reservation on record never goes below 0
        except (AttributeError, TypeError, ValueError):  # a ledger nobody can read counts as the cap reached: fail closed
            return DAILY_CAP
        if add:
            book = {k: v for k, v in book.items() if k >= (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")}
            book[day] = round(total, 4)
            fd, tmp = tempfile.mkstemp(dir=runs, prefix=".wake-spend.")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(book, f)
            os.replace(tmp, path)
        return total


def comment(run, text):
    """A comment on the plan's Plane ticket (`Plane KEY-N` in the plan, plane.py beside the judge). It waits (30 s at
    most): a detached child of the timer's oneshot service would be killed with it."""
    try:
        plan = Path(str(run.get("plan")))
        key = re.search(r"\bPlane ([A-Z][A-Z0-9]*-\d+)\b", plan.read_text(encoding="utf-8", errors="replace"))
        plane = Path(str(run.get("judge"))).parent / "plane.py"
        if key and plane.is_file():
            subprocess.run([sys.executable, str(plane), "comment", key[1], "--body", f"{text} (plan {plan.name})"],
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass


def boundary():
    """1prompt's boundary hooks (agent-guard in boundary mode), loaded into every woken session with --settings."""
    return claude_dir() / "hooks" / "1prompt" / "autonomous-settings.json"


def update_run(hook, path, run, fields):
    """Writes `fields` onto the run file as it is now, only while it is the same running run of the same session."""
    try:
        fresh = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(fresh, dict) or fresh.get("state") != "running" or fresh.get("run_id") != run.get("run_id") \
            or fresh.get("session") != run.get("session"):
        return None
    fresh.update(fields)
    hook.save(path, fresh)
    return fresh


def write_pointer(session, target):
    runs = claude_dir() / "1prompt-runs"
    fd, tmp = tempfile.mkstemp(dir=runs, prefix=".pointer.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(str(target))
    os.replace(tmp, runs / session)


def consider(hook, session, dry):
    """One run: returns a line to print, or None when there is nothing to say (no run, not quiet)."""
    found = hook.session_run({"session_id": session})
    if not found:
        return None
    path, run = found
    if run.get("state") != "running":
        return None
    plan = Path(str(run.get("plan")))
    label = f"{plan.name} (session {session[:8]})"
    woken = [w for w in run.get("woken") or [] if isinstance(w, dict)]
    source, t = session, transcript(session)
    if t is not None:
        quiet = (time.time() - last_activity(t)) / 60
    else:  # a wake whose session never started (unit failed, CLI missing): quiet since that wake, forked again from its source
        last = woken[-1] if woken and woken[-1].get("to") == session else None
        source = str(last.get("from")) if last else ""
        t = transcript(source) if source else None
        if t is None:
            return f"{label}: no transcript found for its session; not woken"
        try:
            at = datetime.strptime(str(last.get("at")), "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            at = 0
        quiet = (time.time() - max(at, last_activity(t))) / 60
    if quiet < QUIET_MIN or busy(session):
        return None
    running = unit_active(run)
    if running == "unknown":
        return f"{label}: quiet {quiet:.0f} min, but systemctl cannot say whether a wake of it still runs; not woken"
    if running:
        return None
    cwd, _, seen_mode = session_facts(t)
    mode = run.get("mode") or seen_mode
    wakes = run.get("wakes") if isinstance(run.get("wakes"), int) else 0
    deadline = run.get("deadline")

    def close(limit):
        if dry:
            return f"{label}: would close: {limit}"
        if update_run(hook, path, run, dict(state="closed", closed_by="limit", reason=limit, closed_at=now(),
                                            notified=True)):
            comment(run, f"1prompt run closed, needs the owner: {limit}. `loop.py resume` reopens it.")
            return f"{label}: closed: {limit}"
        return None

    if isinstance(deadline, str) and deadline and now() > deadline:
        return close(f"its time limit passed ({deadline}) while its session was stopped")
    why = None
    if mode not in WAKE_MODES:
        why = f"its session is quiet {quiet:.0f} min in permission mode {mode or 'unknown'}, which a headless wake cannot use"
    elif not boundary().is_file():
        why = f"its session is quiet {quiet:.0f} min and {boundary()} (the boundary hooks a woken session runs under) is missing"
    if why:
        if not dry and not run.get("wake_noted") and update_run(hook, path, run, {"wake_noted": True}):
            comment(run, f"1prompt run waits for the owner: {why}")
        return f"{label}: not woken: {why}"
    if wakes >= WAKE_LIMIT:
        return close(f"its session stopped again after {WAKE_LIMIT} wakes")
    if isinstance(run.get("next_wake"), str) and now() < run["next_wake"]:
        return f"{label}: quiet {quiet:.0f} min; next wake after {run['next_wake']}"
    spent = ledger_update()
    budget = min(WAKE_USD, DAILY_CAP - spent)
    if budget < MIN_USD:
        return close(f"the day's wake spend reached ${DAILY_CAP:g} (${spent:.2f})")
    if not cwd or not Path(cwd).is_dir():
        return f"{label}: its session's working directory is gone; not woken"
    runner = shutil.which("systemd-run")
    if not runner:  # the unit is what tells a later tick that the woken session still runs
        return f"{label}: systemd-run not found; not woken"
    if dry:
        return f"{label}: would wake (quiet {quiet:.0f} min, wake {wakes + 1} of {WAKE_LIMIT}, ${budget:.2f} budget)"
    new, n = str(uuid.uuid4()), wakes + 1
    write_pointer(new, path)  # first: a tick killed after the bind still leaves a pointer that matches the run
    bound = update_run(hook, path, run, dict(session=new, wakes=n, woken=woken + [{"from": source, "to": new, "at": now()}],
                                              idle=0, waits=0, mode=mode, next_wake=now(BACKOFF_MIN * 2 ** (n - 1))))
    if not bound:
        (claude_dir() / "1prompt-runs" / new).unlink(missing_ok=True)
        return f"{label}: the run changed meanwhile; not woken"
    try:
        (claude_dir() / "1prompt-runs" / session).unlink()
    except OSError:
        pass
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ledger_update(budget, day)  # reserved now, so a second wake in this tick or a child killed early cannot pass the cap
    seconds = DEFAULT_HOURS * 3600
    if isinstance(deadline, str) and deadline:
        try:
            end = datetime.strptime(deadline, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
            seconds = max(600, int((end - datetime.now(timezone.utc)).total_seconds()) + 600)
        except ValueError:
            pass
    child = [sys.executable, str(Path(__file__).resolve()), "child", str(path), source, new, f"{budget:.2f}", day]
    out = subprocess.run([runner, "--user", "--collect", "--no-block", "--quiet",
                              f"--unit={UNIT}-{run.get('run_id')}-{n}", "-p", "MemoryMax=8G",
                              "-p", f"RuntimeMaxSec={seconds}", f"--working-directory={cwd}",
                              f"--setenv=PATH={os.environ.get('PATH', '')}", f"--setenv=HOME={Path.home()}",
                              "--", *child], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        ledger_update(-budget, day)
        return (f"{label}: bound to {new[:8]}, but systemd-run failed ({out.stderr.strip()[:200]}); "
                f"it is woken again from {source[:8]} after {QUIET_MIN:g} quiet minutes")
    comment(run, f"1prompt run woken (wake {n} of {WAKE_LIMIT}, ${budget:.2f} budget): its session was quiet "
                 f"{quiet:.0f} min, so a headless session was started. `loop.py stop` in the repo ends the run.")
    return f"{label}: woken as session {new[:8]} (wake {n} of {WAKE_LIMIT}, ${budget:.2f} budget)"


def tick(dry=False):
    runs = claude_dir() / "1prompt-runs"
    if not runs.is_dir():
        return 0
    with open(runs / ".wake.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("another tick is running")
            return 0
        hook = stop_hook()
        for pointer in sorted(runs.iterdir()):
            if pointer.name.startswith(".") or not pointer.is_file():
                continue
            try:
                line = consider(hook, pointer.name, dry)
            except Exception as error:  # one broken run never stops the others
                line = f"{pointer.name[:8]}: error {type(error).__name__}: {error}"
            if line:
                print(line)
    return 0


PROMPT = """loop-wake: this is a headless session, forked from a session that stopped while its one-prompt run was still \
open (a crash, a usage limit or a closed window). No owner is at the keyboard, and this run writes no owner time log.
Carry the run on: in {top}, run `python3 {loop} status`, read HANDOFF.md if it exists, check `git status` and the \
branch, then continue with what is left of {plan}. The Stop hook holds this session until the plan converges and its \
checks pass. A question only the owner can answer: `python3 {loop} ask "<question>"`, then stop."""


def child(runfile, old, new, budget, day):
    """Runs the woken session to its end, then turns the budget tick reserved into what it cost. Never raises past the
    log line; killed before that, the whole reservation stays in the ledger."""
    runfile = Path(runfile)
    log = runfile.parent / "1prompt-wake.log"
    started = now()
    reserved = float(budget)
    try:
        run = json.loads(runfile.read_text(encoding="utf-8"))
        t = transcript(old)
        cwd, model, _ = session_facts(t) if t else (None, None, None)
        claude = os.environ.get("LOOP_WAKE_CLAUDE") or shutil.which("claude")
        if not claude or not cwd or not boundary().is_file():
            ledger_update(-reserved, day)
            raise RuntimeError("claude not found" if not claude else "no cwd" if not cwd else f"{boundary()} missing")
        mode = str(run.get("mode"))
        args = [claude, "-p", "--resume", old, "--fork-session", "--session-id", new, "--permission-mode", mode,
                "--max-budget-usd", f"{reserved:.2f}", "--settings", str(boundary()), "--output-format", "json"]
        args += ["--model", model] if model else []
        args += ["--dangerously-skip-permissions"] if mode == "bypassPermissions" else []
        loop = Path(str(run.get("judge"))).parent.parent / "loop" / "loop.py"
        prompt = PROMPT.format(top=run.get("top"), loop=loop, plan=Path(str(run.get("plan"))).name)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_CODE_", "CLAUDECODE"))}
        out = subprocess.run(args, input=prompt, capture_output=True, text=True, cwd=cwd, env=env)
        result = {}
        for raw in reversed(out.stdout.splitlines()):  # the CLI's result object, wherever it is in the output
            try:
                item = json.loads(raw)
            except ValueError:
                continue
            if isinstance(item, dict) and "total_cost_usd" in item:
                result = item
                break
        try:
            cost = float(result["total_cost_usd"])
            known = cost >= 0
        except (KeyError, TypeError, ValueError):
            known = False
        if not known:  # a crash or an output without its cost: the whole reservation stays spent
            cost = reserved
        ledger_update(cost - reserved, day)  # on the reservation's day, not the day the session ended
        try:
            fresh = json.loads(runfile.read_text(encoding="utf-8"))
            if isinstance(fresh, dict) and fresh.get("run_id") == run.get("run_id"):
                fresh["wake_cost"] = round(float(fresh.get("wake_cost") or 0) + cost, 4)
                stop_hook().save(runfile, fresh)
        except (OSError, ValueError, TypeError):
            pass
        status = "error" if out.returncode != 0 or result.get("is_error") else "ok"
        detail = f"exit {out.returncode} {result.get('subtype') or ''} {result.get('api_error_status') or ''}".strip()
        line = (f"{started} wake {old[:8]} -> {new[:8]}: {status} ({detail}), ${cost:.2f}"
                f"{'' if known else ' (cost unknown: the reservation is counted)'}, ended {now()}")
        if status == "error":
            line += f": {(out.stderr or str(result.get('result') or '')).strip()[-200:]}"
    except Exception as error:
        line = f"{started} wake {old[:8]} -> {new[:8]}: not run: {type(error).__name__}: {error}"
    with open(log, "a", encoding="utf-8") as f:
        f.write(line.replace("\n", " ") + "\n")
    return 0


def units():
    folder = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "systemd" / "user"
    return folder / f"{UNIT}.service", folder / f"{UNIT}.timer"


def install():
    me = Path(__file__).resolve()
    home_copy = (claude_dir() / "hooks" / "loop").resolve()
    if me.parent != home_copy:
        print(f"refused: install from the installed copy ({home_copy / me.name}, written by install.py), not from "
              f"{me}: a timer must not run a checkout whose branch changes")
        return 1
    service, timer = units()
    service.parent.mkdir(parents=True, exist_ok=True)
    esc = lambda v: v.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$")
    service.write_text(
        "[Unit]\nDescription=Wake one-prompt runs whose session died (coding-playbook loop-wake.py)\n\n"
        f"[Service]\nType=oneshot\nEnvironment=\"PATH={esc(os.environ.get('PATH', '/usr/bin:/bin'))}\"\n"
        f"ExecStart=\"{esc(sys.executable)}\" \"{esc(str(me))}\" tick\n", encoding="utf-8")
    timer.write_text(
        "[Unit]\nDescription=Look for one-prompt runs to wake every 10 minutes\n\n"
        "[Timer]\nOnBootSec=10min\nOnUnitActiveSec=10min\n\n[Install]\nWantedBy=timers.target\n", encoding="utf-8")
    for args in (["daemon-reload"], ["enable", "--now", f"{UNIT}.timer"]):
        out = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)
        if out.returncode != 0:
            print(f"systemctl --user {' '.join(args)} failed: {out.stderr.strip()}")
            return 1
    print(f"installed {timer} (every 10 min, runs {me} tick)")
    return 0


def uninstall():
    subprocess.run(["systemctl", "--user", "disable", "--now", f"{UNIT}.timer"], capture_output=True)
    for path in units():
        path.unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    print("removed the 1prompt-wake timer")
    return 0


def self_test():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        home, bin_, repo = tmp / "home", tmp / "bin", tmp / "repo"
        for d in (home / ".claude" / "1prompt-runs", home / ".claude" / "sessions", bin_, repo / "scripts"):
            d.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        calls = tmp / "calls.jsonl"
        (bin_ / "claude").write_text(f"""#!{sys.executable}
import json, os, sys
with open({str(calls)!r}, "a") as f:
    ledger = os.path.join(os.environ["HOME"], ".claude", "1prompt-runs", ".wake-spend.json")
    f.write(json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd(), "stdin": sys.stdin.read(),
                        "ledger": open(ledger).read() if os.path.exists(ledger) else "",
                        "env": sorted(k for k in os.environ if k.startswith("CLAUDE_CODE_"))}}) + "\\n")
print(os.environ.get("FAKE_CLAUDE_OUT") or json.dumps({{"total_cost_usd": 0.25, "is_error": False, "subtype": "success"}}))
sys.exit(int(os.environ.get("FAKE_CLAUDE_EXIT", "0")))
""")
        (bin_ / "systemd-run").write_text(f"""#!{sys.executable}
import json, os, subprocess, sys
args = sys.argv[1:]
with open({str(tmp / 'units.jsonl')!r}, "a") as f:
    f.write(json.dumps(args) + "\\n")
if os.environ.get("FAKE_SYSTEMD_FAIL"):
    sys.exit("Failed to start transient service unit")
cwd = [a.split("=", 1)[1] for a in args if a.startswith("--working-directory=")][0]
sys.exit(subprocess.run(args[args.index("--") + 1:], cwd=cwd).returncode)
""")
        (bin_ / "systemctl").write_text(f"""#!/bin/sh\necho "$@" >> {tmp / 'systemctl.log'}\n"""
                                        """case "$*" in *list-units*) [ -n "$FAKE_UNIT_ACTIVE" ] && echo "$FAKE_UNIT_ACTIVE loaded active running x";;\n"""
                                        """ esac\nexit ${FAKE_SYSTEMCTL_EXIT:-0}\n""")
        comments = tmp / "comments.log"
        (repo / "scripts" / "plane.py").write_text(f"import sys\nopen({str(comments)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n")
        (repo / "scripts" / "sdlc-check.py").write_text("")
        for f in bin_.iterdir():
            f.chmod(0o755)
        plan = repo / "work.plan.md"
        plan.write_text("# Work\n\nTicket: Plane APS-1.\n", encoding="utf-8")
        project = home / ".claude" / "projects" / "-repo"
        project.mkdir(parents=True)
        runfile = repo / ".git" / "1prompt-run.json"
        fence = home / ".claude" / "hooks" / "1prompt" / "autonomous-settings.json"
        fence.parent.mkdir(parents=True)
        fence.write_text("{}")
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ledger = home / ".claude" / "1prompt-runs" / ".wake-spend.json"
        env = {**{k: v for k, v in os.environ.items()
                  if k not in ("LOOP_WAKE_QUIET_MIN", "LOOP_WAKE_DAILY_USD", "LOOP_WAKE_RUN_USD", "LOOP_WAKE_CLAUDE")},
               "HOME": str(home), "PATH": f"{bin_}:{os.environ.get('PATH', '')}", "XDG_CONFIG_HOME": str(home / ".config"),
               "CLAUDE_CODE_SESSION_ID": "outer"}
        old = "aaaaaaaa-0000-4000-8000-000000000001"

        def setup(seen_mode=None, **fields):
            for p in (home / ".claude" / "1prompt-runs").iterdir():
                p.unlink()
            for p in (calls, comments, tmp / "units.jsonl", repo / ".git" / "1prompt-wake.log"):
                p.unlink(missing_ok=True)
            run = {"version": 1, "state": "running", "run_id": "r1", "plan": str(plan), "base": "main", "session": old,
                   "top": str(repo), "judge": str(repo / "scripts" / "sdlc-check.py"), "mode": "bypassPermissions",
                   "deadline": now(600)}
            run.update(fields)
            run = {k: v for k, v in run.items() if v is not None}
            runfile.write_text(json.dumps(run), encoding="utf-8")
            (home / ".claude" / "1prompt-runs" / old).write_text(str(runfile))
            t = project / f"{old}.jsonl"
            t.write_text(json.dumps({"type": "user", "cwd": str(repo), **({"permissionMode": seen_mode} if seen_mode else {})}) + "\n"
                         + json.dumps({"type": "assistant", "message": {"model": "claude-haiku-5-5"}}) + "\n")
            os.utime(t, (time.time() - 7200, time.time() - 7200))
            sub = project / old
            if sub.exists():
                shutil.rmtree(sub)
            for rec in (home / ".claude" / "sessions").iterdir():
                rec.unlink()

        def tick_(*extra, **envs):
            out = subprocess.run([sys.executable, __file__, "tick", *extra], env={**env, **envs},
                                 capture_output=True, text=True, timeout=60)
            if out.returncode != 0:
                failures.append(f"tick exit {out.returncode}: {out.stderr.strip()[-300:]}")
            return out.stdout

        def state():
            return json.loads(runfile.read_text(encoding="utf-8"))

        def lines(path):
            return path.read_text().splitlines() if path.exists() else []

        def expect_no_wake(name, has=None, **envs):
            out = tick_(**envs)
            if calls.exists() or state().get("session") != old or state().get("state") != "running":
                failures.append(f"{name}: woken or changed: {out!r} {state()}")
            if has and has not in out:
                failures.append(f"{name}: output lacks {has!r}: {out!r}")
            return out

        # a dead, quiet run is woken once, bound to the new session first, with the expected command
        setup()
        out = tick_()
        s = state()
        new = s.get("session")
        call = json.loads(calls.read_text().splitlines()[0]) if calls.exists() else {}
        argv = call.get("argv", [])
        pointers = sorted(p.name for p in (home / ".claude" / "1prompt-runs").iterdir() if not p.name.startswith("."))
        if "woken as session" not in out or new == old or s.get("wakes") != 1 or pointers != [new] \
                or (home / ".claude" / "1prompt-runs" / new).read_text() != str(runfile):
            failures.append(f"a dead quiet run was not woken and bound: {out!r} {s} {pointers}")
        want = ["-p", "--resume", old, "--fork-session", "--session-id", new, "--permission-mode", "bypassPermissions"]
        if argv[:len(want)] != want or "--max-budget-usd" not in argv or argv[argv.index("--max-budget-usd") + 1] != "20.00" \
                or "--settings" not in argv or argv[argv.index("--settings") + 1] != str(fence) \
                or argv[-3:] != ["--model", "claude-haiku-5-5", "--dangerously-skip-permissions"] \
                or call.get("cwd") != str(repo) or "work.plan.md" not in call.get("stdin", "") or call.get("env"):
            failures.append(f"the woken session's command is wrong: {call}")
        if json.loads(call.get("ledger") or "{}").get(day) != 20.0:
            failures.append(f"the wake's budget was not reserved in the ledger before the session ran: {call.get('ledger')!r}")
        unit = json.loads((tmp / "units.jsonl").read_text().splitlines()[0]) if (tmp / "units.jsonl").exists() else []
        runtime = [int(a.split("=")[1]) for a in unit if a.startswith("RuntimeMaxSec=")]
        if f"--unit={UNIT}-r1-1" not in unit or "MemoryMax=8G" not in unit or not runtime \
                or not 36000 <= runtime[0] <= 36700 or f"--setenv=HOME={home}" not in unit \
                or not any(a.startswith(f"--setenv=PATH={bin_}") for a in unit):
            failures.append(f"the wake did not run in its own capped unit, to the run's time limit, with PATH and HOME: {unit}")
        spend = home / ".claude" / "1prompt-runs" / ".wake-spend.json"
        today = json.loads(spend.read_text()).get(datetime.now(timezone.utc).strftime("%Y-%m-%d")) if spend.exists() else None
        if s.get("wake_cost") != 0.25 or today != 0.25 or not s.get("next_wake") \
                or not s.get("woken") or s["woken"][0].get("from") != old:
            failures.append(f"the cost, the ledger or the wake record is wrong: {s}")
        log = lines(repo / ".git" / "1prompt-wake.log")
        if len(log) != 1 or ": ok (exit 0 success)" not in log[0]:
            failures.append(f"the wake log is wrong: {log}")
        if not any("comment APS-1" in c and "woken (wake 1 of 4, $20.00 budget)" in c for c in lines(comments)):
            failures.append(f"the wake was not told on the ticket: {lines(comments)}")
        # the next tick does not wake again: the new session has no transcript yet, then is before next_wake
        calls.unlink(missing_ok=True)
        out = tick_()
        if calls.exists():
            failures.append(f"a second tick woke the run again: {out!r}")
        (project / f"{new}.jsonl").write_text(json.dumps({"type": "user", "cwd": str(repo)}) + "\n")
        os.utime(project / f"{new}.jsonl", (time.time() - 7200, time.time() - 7200))
        out = tick_()
        if calls.exists() or "next wake after" not in out:
            failures.append(f"a wake before next_wake: {out!r}")
        s = state()
        s["next_wake"] = now(-1)
        runfile.write_text(json.dumps(s), encoding="utf-8")
        out = tick_(FAKE_UNIT_ACTIVE=f"{UNIT}-r1-1.service")
        if calls.exists() or out.strip() or f"list-units {UNIT}-r1-* --state=active" not in (tmp / "systemctl.log").read_text():
            failures.append(f"a woken session whose unit still runs was woken again: {out!r}")
        out = tick_(FAKE_SYSTEMCTL_EXIT="1")
        if calls.exists() or "systemctl cannot say" not in out:
            failures.append(f"a systemctl that cannot answer (no user bus) was read as no unit running: {out!r}")
        nothing = tmp / "no-tools"
        nothing.mkdir()
        (nothing / "systemctl").symlink_to(bin_ / "systemctl")
        out = tick_(PATH=str(nothing))
        if calls.exists() or "systemd-run not found" not in out or state().get("session") != new:
            failures.append(f"a wake without systemd-run was started or bound: {out!r}")
        (home / ".claude" / "1prompt-runs" / ".wake-spend.json").unlink()

        # reasons not to wake
        setup()
        os.utime(project / f"{old}.jsonl", None)
        expect_no_wake("a fresh transcript")
        setup()
        (project / old / "subagents").mkdir(parents=True)
        (project / old / "subagents" / "agent-1.jsonl").write_text("{}\n")
        expect_no_wake("a fresh subagent file")
        setup()
        (home / ".claude" / "sessions" / "1.json").write_text(json.dumps(
            {"pid": os.getpid(), "sessionId": old, "status": "busy"}))
        expect_no_wake("a busy live session")
        setup()
        (home / ".claude" / "sessions" / "1.json").write_text(json.dumps(
            {"pid": 999999999, "sessionId": old, "status": "busy"}))
        out = tick_()
        if not calls.exists():
            failures.append(f"a dead process's busy record blocked the wake: {out!r}")
        setup()
        (home / ".claude" / "sessions" / "1.json").write_text(json.dumps(
            {"pid": os.getpid(), "procStart": "1", "sessionId": old, "status": "busy"}))
        out = tick_()
        if not calls.exists():
            failures.append(f"a reused pid's busy record (another start time) blocked the wake: {out!r}")
        setup()
        with open(home / ".claude" / "1prompt-runs" / ".wake.lock", "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            expect_no_wake("a tick while another holds the lock", "another tick is running")
        setup()
        fence.unlink()
        expect_no_wake("no boundary settings", "autonomous-settings.json")
        fence.write_text("{}")
        setup(mode=None, seen_mode="bypassPermissions")
        out = tick_()
        if not calls.exists() or state().get("mode") != "bypassPermissions":
            failures.append(f"a session that died before its first stop was not woken in its transcript's mode: {out!r}")
        setup(mode="default")
        out = expect_no_wake("an asking mode", "permission mode default")
        tick_()
        if len([c for c in lines(comments) if "waits for the owner" in c]) != 1:
            failures.append(f"the asking mode was not told on the ticket exactly once: {lines(comments)}")
        setup(mode=None)
        expect_no_wake("an unknown mode", "permission mode unknown")
        setup(mode="default")
        expect_no_wake("an asking mode with the day's spend at the cap: not closed", "permission mode default",
                       LOOP_WAKE_DAILY_USD="0")
        setup(state="closed")
        out = tick_()
        if calls.exists() or out.strip():
            failures.append(f"a closed run was acted on: {out!r}")
        setup(next_wake=now(60))
        expect_no_wake("before next_wake", "next wake after")
        setup(session="someone-else")
        out = tick_()
        if calls.exists() or state().get("session") != "someone-else" or out.strip():
            failures.append(f"a pointer to another session's run was acted on: {out!r} {state()}")
        setup()
        (home / ".claude" / "1prompt-runs" / ".junk").write_text("x")
        (home / ".claude" / "1prompt-runs" / "broken").write_text(str(tmp / "missing.json"))
        out = tick_("--dry-run")
        if calls.exists() or state().get("session") != old or "would wake" not in out:
            failures.append(f"--dry-run acted or said nothing: {out!r}")

        setup(deadline=now(-5))
        out = tick_("--dry-run")
        if state().get("state") != "running" or "would close" not in out:
            failures.append(f"--dry-run closed a run or said nothing: {out!r}")
        # caps close the run, with one comment each
        for name, fields, env_extra, has in (
                ("the time limit", {"deadline": now(-5)}, {}, "time limit passed"),
                ("the wake count", {"wakes": WAKE_LIMIT}, {}, f"after {WAKE_LIMIT} wakes"),
                ("the day's spend", {}, {"LOOP_WAKE_DAILY_USD": "0"}, "wake spend reached $0")):
            setup(**fields)
            out = tick_(**env_extra)
            s = state()
            if calls.exists() or s.get("state") != "closed" or s.get("closed_by") != "limit" or has not in s.get("reason", ""):
                failures.append(f"{name} did not close the run: {out!r} {s}")
            if len([c for c in lines(comments) if "needs the owner" in c and has in c]) != 1:
                failures.append(f"{name}: no single ticket comment: {lines(comments)}")

        # a failing CLI is logged, its cost still counted, and the next wake waits longer
        setup(wakes=2)
        tick_(FAKE_CLAUDE_OUT=json.dumps({"total_cost_usd": 0.1, "is_error": True, "subtype": "error",
                                          "api_error_status": 429, "result": "usage limit"}), FAKE_CLAUDE_EXIT="1")
        s, log = state(), lines(repo / ".git" / "1prompt-wake.log")
        if not log or ": error (exit 1 error 429)" not in log[0] or "usage limit" not in log[0] or s.get("wake_cost") != 0.1 \
                or json.loads(ledger.read_text()).get(day) != 0.1:
            failures.append(f"a failing wake was not logged with its cost: {log} {s}")
        waited = (datetime.strptime(s.get("next_wake", "2000-01-01T00:00Z"), "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
                  - datetime.now(timezone.utc)).total_seconds() / 60
        if s.get("wakes") != 3 or not 115 <= waited <= 121:
            failures.append(f"the third wake does not wait 120 min before the next: {waited:.0f} min, {s}")
        (home / ".claude" / "1prompt-runs" / ".wake-spend.json").unlink(missing_ok=True)
        # the budget is $20 at most and never more than is left today; the reservation becomes the real cost
        for cap, before, want_budget, after in (("50", 12.5, "20.00", 12.75), ("30", 12.5, "17.50", 12.75)):
            setup()
            ledger.write_text(json.dumps({day: before}))
            tick_(LOOP_WAKE_DAILY_USD=cap)
            argv = json.loads(calls.read_text().splitlines()[0])["argv"] if calls.exists() else []
            if "--max-budget-usd" not in argv or argv[argv.index("--max-budget-usd") + 1] != want_budget \
                    or json.loads(ledger.read_text()).get(day) != after:
                failures.append(f"cap {cap}: the budget or the ledger is wrong: {argv} {ledger.read_text()}")
        ledger.unlink()
        # a crash with no cost in the output keeps the whole reservation; a result line followed by other output counts
        for name, out_text, code, want in (("a crash with no result", "", "134", 20.0),
                                           ("a result line, then more output", json.dumps({"total_cost_usd": 0.25}) + "\nbye", "0", 0.25)):
            setup()
            tick_(FAKE_CLAUDE_OUT=out_text or " ", FAKE_CLAUDE_EXIT=code)
            if json.loads(ledger.read_text()).get(day) != want or state().get("wake_cost") != want:
                failures.append(f"{name}: the ledger or the run counts {ledger.read_text()} {state().get('wake_cost')}, not {want}")
            if (want == 20.0) != ("cost unknown" in "".join(lines(repo / ".git" / "1prompt-wake.log"))):
                failures.append(f"{name}: the log names an unknown cost wrongly: {lines(repo / '.git' / '1prompt-wake.log')}")
        # no systemctl at all: not woken; a ledger nobody can read: the cap counts as reached (fail closed)
        setup(wakes=1)
        bare = tmp / "bare-tools"
        bare.mkdir(exist_ok=True)
        (bare / "systemd-run").unlink(missing_ok=True)
        (bare / "systemd-run").symlink_to(bin_ / "systemd-run")
        out = tick_(PATH=str(bare))
        if calls.exists() or "systemctl cannot say" not in out:
            failures.append(f"a missing systemctl was read as no wake running: {out!r}")
        setup()
        ledger.write_text("not json")
        out = tick_()
        if calls.exists() or state().get("closed_by") != "limit" or "wake spend reached" not in state().get("reason", ""):
            failures.append(f"an unreadable ledger did not count as the cap reached: {out!r} {state()}")
        # the reservation is settled on its own day, even when the session ends the next day
        setup()
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        ledger.write_text(json.dumps({yesterday: 20.0}))
        subprocess.run([sys.executable, __file__, "child", str(runfile), old, "bbbbbbbb-0000-4000-8000-000000000002",
                        "20.00", yesterday], env=env, capture_output=True, text=True, timeout=60)
        if json.loads(ledger.read_text()) != {yesterday: 0.25}:
            failures.append(f"a reservation was not settled on its own day: {ledger.read_text()}")
        # update_run writes only onto the same running run of the same session
        setup(session="s2")
        if update_run(stop_hook(), runfile, {"run_id": "r1", "session": old}, {"wakes": 9}) or state().get("wakes"):
            failures.append(f"update_run wrote onto a run bound to another session: {state()}")
        # a wake whose unit never starts: the reservation is given back, and it is woken again from its source later
        setup()
        out = tick_(FAKE_SYSTEMD_FAIL="1")
        s = state()
        if "systemd-run failed" not in out or calls.exists() or json.loads(ledger.read_text()).get(day) != 0 \
                or s.get("session") == old or s.get("wakes") != 1:
            failures.append(f"a failed unit start was not reported, or its reservation kept: {out!r} {s}")
        if tick_().strip() or calls.exists():
            failures.append("a stranded wake was woken again before it was quiet")
        s["woken"][-1]["at"] = now(-120)
        s["next_wake"] = now(-1)
        runfile.write_text(json.dumps(s), encoding="utf-8")
        out = tick_()
        argv = json.loads(calls.read_text().splitlines()[0])["argv"] if calls.exists() else []
        s = state()
        if argv[:3] != ["-p", "--resume", old] or s.get("wakes") != 2 or s["woken"][-1].get("from") != old:
            failures.append(f"a stranded wake was not woken again from its source: {out!r} {argv} {s}")
        ledger.unlink(missing_ok=True)

        # install runs only from the installed copy; it writes both units, quoted, and starts the timer
        out = subprocess.run([sys.executable, __file__, "install"], env=env, capture_output=True, text=True, timeout=60)
        if out.returncode != 1 or "refused" not in out.stdout:
            failures.append(f"install from a checkout was not refused: {out.stdout}")
        installed = home / ".claude" / "hooks" / "loop"
        installed.mkdir(parents=True)
        for name in ("loop-wake.py", "loop-stop.py"):
            shutil.copy(HERE / name, installed / name)
        out = subprocess.run([sys.executable, str(installed / "loop-wake.py"), "install"], env=env, capture_output=True,
                             text=True, timeout=60)
        service = home / ".config" / "systemd" / "user" / f"{UNIT}.service"
        text = service.read_text() if service.exists() else ""
        log = (tmp / "systemctl.log").read_text() if (tmp / "systemctl.log").exists() else ""
        if out.returncode != 0 or f'ExecStart="{sys.executable}" "{installed.resolve() / "loop-wake.py"}" tick' not in text \
                or f'Environment="PATH={bin_}:' not in text or f"enable --now {UNIT}.timer" not in log \
                or not (service.parent / f"{UNIT}.timer").exists():
            failures.append(f"install did not write and start the timer: {out.stdout}{out.stderr} {log} {text}")
        subprocess.run([sys.executable, str(installed / "loop-wake.py"), "uninstall"], env=env, capture_output=True,
                       text=True, timeout=60)
        if service.exists():
            failures.append("uninstall left the service")
    print("FAIL\n" + "\n".join(failures) if failures else "PASS: loop-wake self-test")
    return 1 if failures else 0


def main():
    args = sys.argv[1:]
    if args == ["--self-test"]:
        return self_test()
    if args in (["tick"], ["tick", "--dry-run"]):
        return tick(dry="--dry-run" in args)
    if len(args) == 6 and args[0] == "child":
        return child(*args[1:])
    if args == ["install"]:
        return install()
    if args == ["uninstall"]:
        return uninstall()
    print(__doc__.split("\n\n")[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
