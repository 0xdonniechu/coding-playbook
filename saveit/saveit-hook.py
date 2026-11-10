#!/usr/bin/env python3
"""Claude Code hooks for ambysto-saveit, registered in settings.json by scripts/install.py --settings.

  python3 saveit-hook.py session-start   SessionStart: when the repo root holds a HANDOFF.md, print
                                         `ambysto-saveit resume` (stdout becomes session context)
  python3 saveit-hook.py pre-compact     PreCompact: `ambysto-saveit tail --write` updates the live tail in an
                                         existing UTF-8 HANDOFF.md, only when git ignores it in that repo
  python3 saveit-hook.py --self-test     run the tests with a fake ambysto-saveit; exit 0 = PASS

The hook JSON arrives on stdin (cwd, transcript_path, source). The hook never blocks a session: it always exits 0,
and does nothing when ambysto-saveit is not installed, the input is not usable, or the folder is not a git work tree.
settings.json runs it with `|| true`, so a missing file or python3 cannot exit 2 (exit 2 refuses a compaction).
Why the git-ignore rule: the tail copies commands as typed (a key on a command line included), so HANDOFF.md must
never be committable. A repo that wants the tail adds HANDOFF.md to its .gitignore (the handoff skill says so).
Why both need an existing HANDOFF.md: a brief on every start would spend tokens in every session, and a tail written
into a repo without one would create the file, so every later start would brief. The hook never creates HANDOFF.md;
the handoff skill does. A HANDOFF.md that is not UTF-8 is left alone (the tool would replace it whole). The brief is
cut at MAX_BRIEF characters. For a fresh start or /clear the brief reads the newest other transcript of the same
project (the session that came before; a subagent's `agent-*.jsonl` is skipped, but a second live session in the same
checkout can be taken for it); after a compaction or --resume it reads this session's own.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT = 20  # seconds per ambysto-saveit or git call; settings.json gives the whole hook 30
MAX_BRIEF = 4000  # characters of resume output put into context


def saveit_binary():
    found = shutil.which("ambysto-saveit")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "ambysto-saveit"
    return str(fallback) if fallback.is_file() and os.access(fallback, os.X_OK) else None


def git_root(cwd):
    try:
        out = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def handoff_ignored(root):
    """True only when git says HANDOFF.md at the root is ignored and it is not tracked."""
    try:
        ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--no-index", "HANDOFF.md"],
                                 capture_output=True, timeout=TIMEOUT).returncode == 0
        tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", "HANDOFF.md"],
                                 capture_output=True, timeout=TIMEOUT).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
    return ignored and not tracked


def previous_transcript(current):
    """The newest other .jsonl in the folder of this session's transcript (the session before this one), or None."""
    folder = current.parent
    if not folder.is_dir():
        return None
    others = [p for p in folder.glob("*.jsonl")
              if p.resolve() != current.resolve() and p.is_file() and not p.name.startswith("agent-")]
    return max(others, key=lambda p: p.stat().st_mtime) if others else None


def utf8_file(path):
    try:
        path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return path.is_file()


def run(argv, payload):
    mode = argv[0] if argv else ""
    if mode not in ("session-start", "pre-compact"):
        print(f"saveit-hook: unknown mode {mode!r}; nothing done", file=sys.stderr)
        return
    if not isinstance(payload, dict):
        return
    binary = saveit_binary()
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
    root = git_root(cwd) if binary else None
    if root is None:
        return
    transcript = payload.get("transcript_path")
    transcript = Path(transcript) if isinstance(transcript, str) and transcript else None

    if mode == "session-start":
        if not (root / "HANDOFF.md").is_file():
            return
        source = payload.get("source")
        if transcript is not None and source not in ("compact", "resume"):
            transcript = previous_transcript(transcript)
        cmd = [binary, "resume", str(root)]
        if transcript is not None and transcript.is_file():
            cmd += ["--transcript", str(transcript)]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        except (OSError, subprocess.SubprocessError):
            return
        brief = out.stdout.strip()
        if out.returncode == 0 and brief:
            if len(brief) > MAX_BRIEF:
                brief = brief[:MAX_BRIEF].rstrip() + "\n… (brief cut; read HANDOFF.md)"
            print("ambysto-saveit resume (SessionStart hook; HANDOFF.md is in this repo, read it before acting):")
            print(brief)
        return

    # pre-compact
    if transcript is None or not transcript.is_file():
        return
    handoff = root / "HANDOFF.md"
    if not handoff.is_file():
        return
    if not utf8_file(handoff):
        print(f"saveit-hook: {handoff} is not UTF-8; live tail not written", file=sys.stderr)
        return
    if not handoff_ignored(root):
        print(f"saveit-hook: HANDOFF.md is not git-ignored in {root}; live tail not written", file=sys.stderr)
        return
    try:
        subprocess.run([binary, "tail", "--repo", str(root), "--transcript", str(transcript), "--write"],
                       capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return


def self_test():
    import tempfile
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log = tmp / "calls.log"
        fake_dir = tmp / "bin"
        fake_dir.mkdir()
        fake = fake_dir / "ambysto-saveit"
        fake.write_text("#!/bin/sh\necho \"$@\" >> \"$SAVEIT_LOG\"\necho brief-text\n"
                        "if [ -n \"$SAVEIT_LONG\" ]; then i=0; while [ $i -lt 300 ]; do echo 0123456789012345678901234567890123456789; i=$((i+1)); done; fi\n",
                        encoding="utf-8")
        fake.chmod(0o755)
        projects = tmp / "projects"
        projects.mkdir()
        old = projects / "old.jsonl"
        old.write_text("{}\n", encoding="utf-8")
        current = projects / "current.jsonl"
        current.write_text("{}\n", encoding="utf-8")
        os.utime(old, (1, 1))
        (projects / "agent-sub.jsonl").write_text("{}\n", encoding="utf-8")  # a subagent's, newer than old.jsonl

        def repo(name, ignore, handoff, track=False):
            path = tmp / name
            path.mkdir()
            subprocess.run(["git", "init", "-q", str(path)], check=True)
            if ignore:
                (path / ".gitignore").write_text("HANDOFF.md\n", encoding="utf-8")
            if handoff:
                (path / "HANDOFF.md").write_text("# Handoff\n", encoding="utf-8")
            if track:
                subprocess.run(["git", "-C", str(path), "add", "-f", "HANDOFF.md"], check=True)
            (path / "sub").mkdir()
            return path

        ignored, plain, tracked = repo("ignored", True, True), repo("plain", False, True), repo("tracked", True, True, True)
        bare = repo("nohandoff", True, False)
        latin = repo("latin", True, False)
        (latin / "HANDOFF.md").write_bytes(b"# Handoff\ncaf\xe9\n")
        git_only = tmp / "gitonly"
        git_only.mkdir()
        (git_only / "git").symlink_to(shutil.which("git"))
        outside = tmp / "outside"
        outside.mkdir()
        env = {**os.environ, "PATH": f"{fake_dir}{os.pathsep}{os.environ.get('PATH', '')}", "SAVEIT_LOG": str(log)}

        def call(mode, payload, path_env=None):
            log.write_text("", encoding="utf-8")
            out = subprocess.run([sys.executable, __file__, mode], input=json.dumps(payload) if payload is not None else "not json",
                                 capture_output=True, text=True, env=path_env or env, timeout=60)
            return out, log.read_text(encoding="utf-8").strip()

        def expect(name, out, calls, rc=0, stdout_has=None, calls_has=None, no_calls=False):
            if out.returncode != rc:
                failures.append(f"{name}: exit {out.returncode}, expected {rc}")
            if stdout_has is not None and stdout_has not in out.stdout:
                failures.append(f"{name}: stdout lacks {stdout_has!r}: {out.stdout!r}")
            if stdout_has is None and out.stdout.strip():
                failures.append(f"{name}: unexpected stdout {out.stdout!r}")
            if no_calls and calls:
                failures.append(f"{name}: ambysto-saveit called: {calls!r}")
            for part in calls_has or []:
                if part not in calls:
                    failures.append(f"{name}: call lacks {part!r}: {calls!r}")

        tp = str(current)
        out, calls = call("session-start", {"cwd": str(ignored / "sub"), "transcript_path": tp, "source": "startup"})
        expect("start, handoff, from a subfolder", out, calls, stdout_has="brief-text",
               calls_has=[f"resume {ignored}", f"--transcript {old}"])
        out, calls = call("session-start", {"cwd": str(ignored), "transcript_path": tp, "source": "compact"})
        expect("start after compact reads its own transcript", out, calls, stdout_has="brief-text", calls_has=[f"--transcript {current}"])
        out, calls = call("session-start", {"cwd": str(ignored), "transcript_path": tp, "source": "resume"})
        expect("start on --resume reads its own transcript", out, calls, stdout_has="brief-text", calls_has=[f"--transcript {current}"])
        out, calls = call("session-start", {"cwd": str(ignored), "transcript_path": tp, "source": "startup"}, {**env, "SAVEIT_LONG": "1"})
        expect("start, long brief is cut", out, calls, stdout_has="(brief cut; read HANDOFF.md)")
        if len(out.stdout) > MAX_BRIEF + 200:
            failures.append(f"start, long brief: {len(out.stdout)} characters printed")
        out, calls = call("session-start", {"cwd": str(plain), "transcript_path": tp, "source": "clear"})
        expect("start, handoff not ignored still briefs (read only)", out, calls, stdout_has="brief-text", calls_has=[f"--transcript {old}"])
        out, calls = call("session-start", {"cwd": str(bare), "transcript_path": tp, "source": "startup"})
        expect("start, no handoff", out, calls, no_calls=True)
        out, calls = call("session-start", {"cwd": str(outside), "transcript_path": tp, "source": "startup"})
        expect("start, not a git tree", out, calls, no_calls=True)
        out, calls = call("pre-compact", {"cwd": str(ignored / "sub"), "transcript_path": tp, "trigger": "auto"})
        expect("compact, ignored", out, calls, calls_has=[f"tail --repo {ignored} --transcript {current} --write"])
        out, calls = call("pre-compact", {"cwd": str(bare), "transcript_path": tp, "trigger": "auto"})
        expect("compact, ignored but no HANDOFF.md: never created", out, calls, no_calls=True)
        if out.stderr.strip() or (bare / "HANDOFF.md").exists():
            failures.append(f"compact, no HANDOFF.md: stderr {out.stderr.strip()!r} or the file was created")
        out, calls = call("pre-compact", {"cwd": str(latin), "transcript_path": tp, "trigger": "auto"})
        expect("compact, HANDOFF.md not UTF-8", out, calls, no_calls=True)
        if "not UTF-8" not in out.stderr:
            failures.append("compact, HANDOFF.md not UTF-8: no note on stderr")
        for name, path in (("not ignored", plain), ("tracked", tracked)):
            out, calls = call("pre-compact", {"cwd": str(path), "transcript_path": tp, "trigger": "auto"})
            expect(f"compact, {name}", out, calls, no_calls=True)
            if "not git-ignored" not in out.stderr:
                failures.append(f"compact, {name}: no note on stderr")
        out, calls = call("pre-compact", {"cwd": str(outside), "transcript_path": tp})
        expect("compact, not a git tree", out, calls, no_calls=True)
        out, calls = call("pre-compact", {"cwd": str(ignored), "transcript_path": str(tmp / "missing.jsonl")})
        expect("compact, transcript missing", out, calls, no_calls=True)
        out, calls = call("pre-compact", None)
        expect("bad stdin", out, calls, no_calls=True)
        out, calls = call("bogus", {"cwd": str(ignored)})
        expect("unknown mode", out, calls, no_calls=True)
        no_bin = {**env, "PATH": str(git_only), "HOME": str(tmp)}
        out, calls = call("session-start", {"cwd": str(ignored), "transcript_path": tp, "source": "startup"}, no_bin)
        expect("binary missing", out, calls, no_calls=True)
        if out.stderr.strip():
            failures.append(f"binary missing: stderr {out.stderr.strip()!r}")
        out, calls = call("session-start", {"cwd": "bad\u0000path", "transcript_path": tp, "source": "startup"})
        expect("an unexpected error still exits 0", out, calls, no_calls=True)
        if "saveit-hook:" not in out.stderr:
            failures.append(f"an unexpected error: no note on stderr: {out.stderr!r}")
    print("FAIL\n" + "\n".join(failures) if failures else "PASS: saveit-hook self-test")
    return 1 if failures else 0


def main():
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    try:
        payload = json.loads(sys.stdin.read() or "null")
    except (ValueError, UnicodeDecodeError):
        payload = None
    try:
        run(sys.argv[1:], payload)
    except Exception as error:  # a hook must never stop a session
        print(f"saveit-hook: {type(error).__name__}: {error}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
