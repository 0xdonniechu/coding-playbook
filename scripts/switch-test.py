#!/usr/bin/env python3
"""Model switch kit (APS-45): run a model as reviewer on recorded cases, or replay a HARD task, blind to the known findings.

  python3 scripts/switch-test.py review --model ID [--effort high] [--case ID]
  python3 scripts/switch-test.py replay --model ID --effort LEVEL
  python3 scripts/switch-test.py probe --model ID      one cheap run that must hit the reviewer's agent-guard hook
  python3 scripts/switch-test.py void-check STREAM     exit 1 when the run touched the kit or old transcripts
  python3 scripts/switch-test.py --self-test

Each case runs headless (`claude -p`) in a fresh clone of the case's repo, detached at the case's head, with no remote,
under ~/.cache/model-switch-runs/<run>/<case>/. The reviewer is the session itself: the body of rores/agents/reviewer.md is
appended to the system prompt, its tools and agent-guard hooks are given on the command line, and --model/--effort
set the model under test. The raw stream stays in the cache; report.md and run.json go to switch-test/runs/<run>/<case>/.
Matching the report against known.md is the main session's proposal and the owner's verdict (switch-test/README.md).
Standard library only. Spends money: every review or replay is a real model run.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "switch-test"
HOME = Path.home()
CACHE = HOME / ".cache" / "model-switch-runs"
SOURCES = HOME / "work"  # case repo "ambysto/x" is the local clone ~/work/ambysto/x
GUARD = 'python3 "$HOME/.claude/hooks/1prompt/agent-guard.py" {mode}'
REVIEW_HOOKS = {
    "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": GUARD.format(mode="review")}]}],
    "PostToolUse": [{"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command": GUARD.format(mode="review-after")}]}],
    "Stop": [{"hooks": [{"type": "command", "command": GUARD.format(mode="review-stop")}]}],
}
AUTONOMOUS = HOME / ".claude" / "hooks" / "1prompt" / "autonomous-settings.json"
WATCHED = [HOME / ".claude" / p for p in ("settings.json", "CLAUDE.md", "agents", "hooks", "hil/log.jsonl")]
# A tool call naming any of these voids the run: the kit holds the answers, old transcripts hold the original reports.
VOID_MARKERS = ["switch-test/cases", "switch-test/replay", "switch-test/runs", "known.md", ".claude/projects"]
CASE_KEYS = {"id", "kind", "repo", "base", "head", "rating", "original_model", "source", "source_line"}
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
REVIEW_PREFACE = ("The repository is a throwaway clone, detached at the change's head, with no remote. Read files from the "
                  "working tree or with `git show <commit>:<path>`; never check out, switch or reset.\n\n")


def die(msg):
    print(f"switch-test: {msg}", file=sys.stderr)
    sys.exit(2)


def git(*args, cwd=None):
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        die(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def load_cases(kind=None):
    cases = []
    for folder in sorted([*(KIT / "cases").glob("*/"), *(KIT / "replay").glob("*/")]):
        case = json.loads((folder / "case.json").read_text(encoding="utf-8"))
        missing = CASE_KEYS - set(case)
        if missing or case["id"] != folder.name or case["kind"] not in ("review", "replay"):
            raise ValueError(f"{folder}: bad case.json (missing {sorted(missing)}, or id/kind wrong)")
        if case["kind"] == "replay" and "review_task" not in case:
            raise ValueError(f"{folder}: a replay needs review_task")
        case["task"] = (folder / "task.md").read_text(encoding="utf-8")
        if not (folder / "known.md").is_file():
            raise ValueError(f"{folder}: no known.md")
        if kind is None or case["kind"] == kind:
            cases.append(case)
    return cases


def reviewer_body():
    text = (ROOT / "rores" / "agents" / "reviewer.md").read_text(encoding="utf-8")
    head, _, body = text[4:].partition("\n---\n")
    for entries in REVIEW_HOOKS.values():
        for command in (h["command"] for e in entries for h in e["hooks"]):
            if command not in head:
                die(f"rores/agents/reviewer.md no longer runs `{command}`; update REVIEW_HOOKS to match its frontmatter")
    tools = re.search(r"^tools:\s*(.+)$", head, re.M)
    return body.strip() + "\n", [t.strip() for t in tools.group(1).split(",")] if tools else []


def fill(text, **values):
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    left = re.findall(r"\{(repo|range|task)\}", text)
    if left:
        die(f"unfilled placeholders {left}")
    return text


def clone(case, dest, at):
    source = SOURCES / case["repo"]
    if not (source / ".git").exists():
        die(f"no local clone at {source}")
    # only the history up to `at`: a plain clone would carry the source's branches (the kit, its known.md) and tags
    full = git("rev-parse", "--verify", f"{at}^{{commit}}", cwd=source)
    git("init", "--quiet", str(dest))
    git("fetch", "--quiet", "--no-tags", f"file://{source}", full, cwd=dest)
    git("checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=dest)
    (Path(dest) / ".git" / "FETCH_HEAD").unlink(missing_ok=True)
    return source


def fingerprint(paths):
    """sha256 over each file (or every file under a folder); missing paths count too."""
    digest = {}
    for path in paths:
        files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
        h = hashlib.sha256()
        for f in files:
            h.update(str(f).encode())
            h.update(f.read_bytes() if f.exists() else b"<missing>")
        digest[str(path)] = h.hexdigest()
    return digest


def repo_state(source):
    """Branch and status of a source repo; the kit's own output folder (switch-test/runs/) does not count."""
    status = [line for line in git("status", "--porcelain", "--untracked-files=all", cwd=source).splitlines()
              if not (Path(source) == ROOT and line[3:].startswith("switch-test/runs/"))]
    return {"branch": git("branch", "--show-current", cwd=source), "status": status}


def parse_stream(path):
    """Returns init model, final text, cost, usage, duration, error flag, and every tool input as text."""
    info = {"model": None, "result": "", "cost_usd": None, "usage": None, "duration_ms": None, "is_error": None, "tool_inputs": [], "tool_results": []}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            info["model"] = event.get("model")
        elif event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    info["tool_inputs"].append(json.dumps({"name": block.get("name"), "input": block.get("input", {})}))
        elif event.get("type") == "user":
            content = event.get("message", {}).get("content", [])
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    info["tool_results"].append(json.dumps(block.get("content", "")))
        elif event.get("type") == "result":
            info.update(result=event.get("result") or "", cost_usd=event.get("total_cost_usd"), usage=event.get("usage"),
                        duration_ms=event.get("duration_ms"), is_error=event.get("is_error"))
    return info


def session_folder(repo):
    """Claude Code keeps a run's large tool outputs in ~/.claude/projects/<cwd with non-alphanumerics as '-'>/, even
    with --no-session-persistence; reading back its own output there is not a leak."""
    return ".claude/projects/" + re.sub(r"[^A-Za-z0-9]", "-", str(repo)) + "/"


def case_markers(case):
    """A case's own answer keys: the live source repo (it holds the later fixes) and the case's `void_extra` paths
    (the installed copy of the fixed code, its upstream repo)."""
    end = r"(?![\w.-])"  # a path ends at anything but a name character (text is JSON: \n, \" start with a backslash)
    return [re.escape(f"work/{case['repo']}") + end,
            *(re.escape(form.rstrip("/")) + end for m in case.get("void_extra", []) for form in expand_home(m))]


# options that take a value, per search program (the value is not a path to search)
VALUE_OPTS = {"grep": {"-e", "-f", "-A", "-B", "-C", "-m", "-d", "-D", "--include", "--exclude", "--exclude-dir",
                       "--regexp", "--file", "--max-count", "--context", "--after-context", "--before-context"},
              "rg": {"-e", "-f", "-g", "-t", "-T", "-A", "-B", "-C", "-m", "-j", "-M", "--glob", "--iglob", "--type",
                     "--type-not", "--regexp", "--file", "--max-count", "--max-depth", "--context"},
              "ag": {"-G", "-A", "-B", "-C", "-m", "--ignore", "--file-search-regex", "--depth"},
              "ack": {"-A", "-B", "-C", "-m", "--type", "--ignore-dir", "--match"}}
VALUE_OPTS["egrep"] = VALUE_OPTS["fgrep"] = VALUE_OPTS["grep"]
PATH_WORD = r"^(~|\$HOME|\$\{HOME\}|/)(?=/|$)|^(~|\$HOME|\$\{HOME\})$|^/"


def split_commands(command):
    """The simple commands of a shell line, split outside quotes at | ; & and newlines, and around $( ) and backticks.
    Returns (text, the separator after it, nested in a command substitution) for each."""
    parts, buf, quote, outer, tick = [], [], None, [], False  # outer: the quote state at each open $(
    def flush(sep):
        parts.append(("".join(buf), sep, bool(outer) or tick))
        buf.clear()
    i = 0
    while i < len(command):
        c = command[i]
        if quote == "'":
            buf.append(c)
            quote = None if c == "'" else quote
        elif c == "\\" and i + 1 < len(command):
            buf.append(command[i:i + 2])
            i += 1
        elif c == "$" and command[i + 1:i + 2] == "(":  # a substitution opens even inside "...", and resets quoting
            flush("$(")
            outer.append(quote)
            quote = None
            i += 1
        elif c == "`":
            flush("`")
            tick = not tick
        elif c == ")" and outer and quote is None:
            flush(")")
            quote = outer.pop()
        elif quote == '"':
            buf.append(c)
            quote = None if c == '"' else quote
        elif c in "'\"":
            buf.append(c)
            quote = c
        elif c in "|;&\n)" and quote is None:  # a ) here closes a subshell
            flush(c)
        elif c in "({}" and quote is None and (c == "(" or (command[i + 1:i + 2] in ("", " ", "\t", "\n", ";")
                                                       and (not buf or buf[-1][-1:] in (" ", "\t")))):
            # a subshell, or a group's { } (a brace followed by a word is ${VAR}, {a,b} or find's {})
            flush(c)
        else:
            buf.append(c)
        i += 1
    flush("")
    return parts


def strip_heredocs(command):
    """The command without heredoc bodies (data such as a script fed to python3, not commands). The direct path
    markers still see the bodies; only the search-root rules skip them."""
    lines, out, i = command.split("\n"), [], 0
    while i < len(lines):
        out.append(lines[i])
        tags = [m.group(2) for m in re.finditer(r"(?<!<)<<-?\s*(['\"]?)(\w+)\1", lines[i])
                if not split_quoted(lines[i][:m.start()])]
        i += 1
        for tag in tags:
            while i < len(lines) and lines[i].strip() != tag:
                i += 1
            if i < len(lines):
                out.append(lines[i])
                i += 1
    return "\n".join(out)


def split_quoted(prefix):
    """True when the end of `prefix` is inside a quote."""
    quote = None
    for c in prefix:
        if quote:
            quote = None if c == quote else quote
        elif c in "'\"":
            quote = c
    return quote is not None


WRAPPERS = {"sudo", "command", "exec", "time", "nice", "nohup", "timeout", "env", "stdbuf", "ionice", "do", "then",
            "else", "if", "elif", "while", "until", "!"}
WRAPPER_VALUES = {"sudo": {"-u", "-g"}, "nice": {"-n"}, "timeout": {"-s", "-k"}, "env": {"-u"}, "ionice": {"-c", "-n"}}


def shell_words(text):
    try:
        return shlex.split(text, comments=False)
    except ValueError:  # an unclosed quote (a heredoc body, a probe string): plain split
        return [w.strip("\"'") for w in text.split()]


NAME_ONLY = {"ls", "echo", "printf", "stat", "du", "file", "test", "[", "cd", "mkdir", "touch", "basename", "dirname",
             "realpath", "readlink"}


def search_roots(command):
    """Folders a Bash command reads below. Per simple command (split_commands): a content search (grep/egrep/fgrep -r
    or -R, rg, ag, ack) gives its folder arguments, not its pattern (the first operand, unless -e/-f or --regexp/--file
    give it); find, or rg --files, gives its folders when it runs something on what it finds (-exec/-ok, inside $( ),
    or piped into xargs, while or parallel), and lists names only otherwise, like Glob, ls -R and tree; and any program
    but a name-only one (NAME_ONLY) reading a glob path gives the folder above the glob."""
    roots = []
    parts = split_commands(strip_heredocs(command))
    for n, (text, sep, nested) in enumerate(parts):
        words = shell_words(text)
        while words and (re.match(r"^\w+=", words[0]) or words[0] in WRAPPERS):
            wrapper = words.pop(0)
            while words and (words[0].startswith("-") or re.match(r"^\w+=", words[0])):  # its options, env's VAR=x
                opt = words.pop(0)
                if opt in WRAPPER_VALUES.get(wrapper, ()) and words:
                    words.pop(0)  # an option value (nice -n 5, timeout -s KILL, env -u VAR)
            if wrapper == "timeout" and words and re.fullmatch(r"\d+(\.\d+)?[smhd]?", words[0]):
                words.pop(0)  # the duration
        if not words or not re.fullmatch(r"[\w./+-]+", words[0]):  # not a command (a fragment of a string)
            continue
        prog, args = Path(words[0]).name, words[1:]
        if prog in ("bash", "sh", "zsh", "dash") and any(re.match(r"^-[a-zA-Z]*c", w) for w in args):
            script = next((w for w in args if not w.startswith("-")), "")
            roots += search_roots(script)  # the shell runs its -c string as commands
            continue
        if prog not in NAME_ONLY:
            roots += [w for w in args if re.match(PATH_WORD, w) and re.search(r"[*?[]", w)]
        flags = [w for w in args if w.startswith("-")]
        later, j = [], n
        while j + 1 < len(parts) and parts[j][1] == "|":  # every later stage of the same pipeline
            later.append(Path((shell_words(parts[j + 1][0]) or [""])[0]).name)
            j += 1
        feeds = nested or bool({"xargs", "while", "parallel"} & set(later))
        listing = prog == "find" or (prog == "rg" and "--files" in args)
        if prog in ("grep", "egrep", "fgrep"):
            recursive = any(re.match(r"^-[a-zA-Z]*[rR]|^--recursive$|^--dereference-recursive$", f) for f in flags)
        elif listing:
            recursive = bool({"-exec", "-execdir", "-ok", "-okdir"} & set(args)) or feeds
        else:
            recursive = prog in ("rg", "ag", "ack")
        if not recursive:
            continue
        if prog == "find":  # the folders come before the first expression
            operands = []
            for w in args:
                if w.startswith(("-", "(", "!")):
                    break
                operands.append(w)
        else:
            operands, skip, given = [], False, listing  # rg --files takes no pattern
            for w in args:
                if skip:
                    skip = False
                elif w == "--":
                    continue
                elif w.startswith("--"):
                    given |= w.split("=", 1)[0] in ("--regexp", "--file")
                    skip = "=" not in w and w in VALUE_OPTS.get(prog, ())
                elif w.startswith("-"):  # short flags, maybe combined (-rn, -rne PATTERN): the last one may take a value
                    given |= w[-1] in "ef"
                    skip = len(w) > 1 and "-" + w[-1] in VALUE_OPTS.get(prog, ())
                else:
                    operands.append(w)
            if not given and operands:
                operands = operands[1:]  # the pattern
        roots += [w for w in operands if re.match(PATH_WORD, w)]
    return roots


def answer_key_paths(case):
    """Absolute paths of a case's answer keys: the live source repo and the `~/` entries of `void_extra`."""
    keys = [str(SOURCES / case["repo"])]
    keys += [str(HOME) + m[1:].rstrip("/") for m in case.get("void_extra", []) if m.startswith("~/")]
    return keys


def ancestor_hits(text, case):
    """A search rooted at or above an answer key reads it too (Grep path ~/.claude/hooks, grep -r … ~/.claude, find /):
    flag a Grep tool call, or a searching Bash command, whose folder holds one. Glob lists names only."""
    try:
        call = json.loads(text)
    except ValueError:
        return []
    name, args = call.get("name"), call.get("input", {})
    if name == "Grep":
        roots = [args["path"]] if args.get("path") else []
    elif name == "Bash":
        roots = search_roots(args.get("command", ""))
    else:
        return []
    hits = []
    for root in roots:
        root = re.sub(r"^(~|\$HOME|\$\{HOME\})(?=/|$)", str(HOME), root)
        glob = re.search(r"[*?[]", root)
        root = root[:glob.start()].rsplit("/", 1)[0] if glob else root  # the folder above the first glob
        root = root.rstrip("/")  # "/" becomes "", the folder above everything
        hits += [f"{root or '/'} (holds {k})" for k in answer_key_paths(case) if k == root or k.startswith(root + "/")]
    return hits


def expand_home(marker):
    """A `~/` marker means this machine's real path, however it is written: `~/…`, `$HOME/…`, `${HOME}/…` or absolute.
    Write and Edit content is exempt (an installer's target); a shell command that names it is judged by hand."""
    if not marker.startswith("~/"):
        return [marker]
    return [marker, "$HOME" + marker[1:], "${HOME}" + marker[1:], str(HOME) + marker[1:]]


def sets_home(text):
    """True when a Bash call assigns HOME (HOME=…, export HOME=…), not when it merely names it (grep 'HOME=')."""
    try:
        call = json.loads(text)
    except ValueError:
        return False
    if call.get("name") != "Bash":
        return False
    for part, _, _ in split_commands(call.get("input", {}).get("command", "")):
        words = shell_words(part)
        while words and words[0] in WRAPPERS - {"env"}:
            words.pop(0)
        if words and (words[0].startswith("HOME=") or (words[0] in ("export", "declare", "typeset", "local", "env")
                                                         and any(w.startswith("HOME=") for w in words[1:]))):
            return True
    return False


def void_hits(tool_inputs, own_dir=None, own_repo=None, case=None):
    own = session_folder(own_repo) if own_repo else None
    patterns = [re.escape(m) for m in VOID_MARKERS] + (case_markers(case) if case else [])  # all of them for reads
    hits = []
    for text in tool_inputs:
        seen = text.replace(own, "") if own else text
        if sets_home(text):  # the command sets HOME itself (a temp install): $HOME and ~ are not this home
            text = seen = re.sub(r"\$\{?HOME\}?(?=/)|(?<![\w/.~-])~(?=/)", "$OTHER_HOME", seen)
        # a case's answer keys count only when read; Write/Edit content may name an install target the task asks for
        writes = re.match(r'\{"name": "(Write|Edit|NotebookEdit)"', text)
        for pat in patterns if not writes else [re.escape(m) for m in VOID_MARKERS]:
            hits += [m.group(0) for m in re.finditer(pat, seen)]
        if case and not writes:
            hits += ancestor_hits(text, case)
    allowed = [str(d) for d in (own_dir, own_repo) if d]
    for text in tool_inputs:  # another run's folder in the cache (its stream holds that run's report)
        for found in re.findall(r"model-switch-runs/[^\s\"'\\;,:)`|&<>]+", text):  # text is JSON: a newline is \n
            path = str(HOME / ".cache" / found).rstrip("/")
            if not any(path == a or path.startswith(a + "/") for a in allowed):
                hits.append(found)
    return sorted(set(hits))


def run_claude(cwd, prompt, model, effort, settings, tools, stream, append=None):
    cmd = ["claude", "-p", prompt, "--model", model, "--effort", effort, "--output-format", "stream-json", "--verbose",
           "--no-session-persistence", "--settings", json.dumps(settings), "--allowedTools", *tools]
    if append:
        cmd += ["--append-system-prompt", append]
    with open(stream, "w", encoding="utf-8") as out:
        subprocess.run(cmd, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    info = parse_stream(stream)
    if info["model"] != model:
        die(f"the run used model {info['model']!r}, not {model!r} (stream: {stream})")
    return info


def record(out_dir, info, extra):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(info["result"].rstrip() + "\n", encoding="utf-8")
    data = {k: info[k] for k in ("model", "cost_usd", "usage", "duration_ms", "is_error")}
    data.update(extra)
    (out_dir / "run.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def guarded(sources, action, out_dir):
    """Runs action(); if ~/.claude or a source repo's branch or status changed meanwhile, records which in the run's
    run.json (`watch_changed`) and warns. The owner and the main session also write there during a run (/model,
    /effort, the owner time log), so the main session judges each change; the runner cannot tell who wrote it."""
    before = fingerprint(WATCHED), {str(s): repo_state(s) for s in sources}
    result = action()
    after = fingerprint(WATCHED), {str(s): repo_state(s) for s in sources}
    changed = [p for p in before[0] if before[0][p] != after[0][p]] + [s for s in before[1] if before[1][s] != after[1][s]]
    run_json = out_dir / "run.json"
    if run_json.exists():
        data = json.loads(run_json.read_text(encoding="utf-8"))
        data["watch_changed"] = changed
        run_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if changed:
        print(f"WARNING: changed during the run, check who wrote it: {', '.join(changed)}", file=sys.stderr)
    return result


def review_one(case, model, effort, run, task=None, rng=None, repo=None):
    body, tools = reviewer_body()
    work = CACHE / run / case["id"]
    work.mkdir(parents=True, exist_ok=False)
    if repo is None:
        repo = work / "repo"
        clone(case, repo, case["head"])
    prompt = REVIEW_PREFACE + fill(task or case["task"], repo=str(repo), range=rng or f"{case['base']}..{case['head']}")
    info = run_claude(repo, prompt, model, effort, {"hooks": REVIEW_HOOKS}, tools, work / "stream.jsonl", append=body)
    hits = void_hits(info["tool_inputs"], work, repo, case)
    record(KIT / "runs" / run / case["id"], info, {"effort": effort, "case": case["id"], "void": hits,
                                                  "verdict": "VOID" if hits else "scored by the owner in results.md"})
    print(f"{case['id']}: {'VOID ' + str(hits) if hits else 'done'}, cost ${info['cost_usd']}")
    return info


def cmd_review(args):
    cases = [c for c in load_cases("review") if args.case in (None, c["id"])]
    if not cases:
        die(f"no review case {args.case!r}")
    run = f"{datetime.date.today()}-{args.model}-{args.effort}"
    sources = sorted({SOURCES / c["repo"] for c in cases})
    for case in cases:
        guarded(sources, lambda: review_one(case, args.model, args.effort, run), KIT / "runs" / run / case["id"])


def cmd_replay(args):
    case = load_cases("replay")[0]
    run = args.run or f"{datetime.date.today()}-{args.model}-{args.effort}"
    work = CACHE / run / case["id"]
    repo = work / "repo"
    if args.review_only:  # review an existing replay's commit again (after a failed review step)
        task = fill(case["task"], repo=str(repo))
        for old in (CACHE / run / f"{case['id']}-review", KIT / "runs" / run / f"{case['id']}-review"):
            if old.exists():
                die(f"{old} exists: move it aside first (as {old.name}-void1 when it was void), so its evidence stays")
        return replay_review(case, run, repo, task, git("rev-parse", "--short", "HEAD", cwd=repo), SOURCES / case["repo"])
    work.mkdir(parents=True, exist_ok=False)
    source = clone(case, repo, case["base"])
    git("switch", "--quiet", "-c", "replay", cwd=repo)
    settings = json.loads(AUTONOMOUS.read_text(encoding="utf-8"))
    tools = ["Bash", "Read", "Edit", "Write", "Glob", "Grep"]
    task = fill(case["task"], repo=str(repo))

    out_dir = KIT / "runs" / run / case["id"]

    def build():
        info = run_claude(repo, task, args.model, args.effort, settings, tools, work / "stream.jsonl")
        head = git("rev-parse", "--short", "HEAD", cwd=repo)
        record(out_dir, info, {"effort": args.effort, "case": case["id"], "role": "author", "head": head,
                               "committed": head != git("rev-parse", "--short", case["base"], cwd=repo),
                               "void": void_hits(info["tool_inputs"], work, repo, case)})
        return info, head
    info, head = guarded([source], build, out_dir)
    hits = void_hits(info["tool_inputs"], work, repo, case)
    committed = head != git("rev-parse", "--short", case["base"], cwd=repo)
    print(f"{case['id']} build: {'VOID ' + str(hits) if hits else 'done'}, commit {head if committed else 'none'}, cost ${info['cost_usd']}")
    if committed:
        replay_review(case, run, repo, task, head, source)


def replay_review(case, run, repo, task, head, source):
    review_case = dict(case, id=case["id"] + "-review")
    review_task = case["review_task"].replace("{task}", task)  # {repo} and {range} are filled by review_one
    guarded([source], lambda: review_one(review_case, case["replay_reviewer"], "high", run,
                                         task=review_task, rng=f"{case['base']}..{head}", repo=repo),
            KIT / "runs" / run / review_case["id"])


def cmd_probe(args):
    body, tools = reviewer_body()
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        git("init", "--quiet", str(repo))
        git("-c", "user.name=probe", "-c", "user.email=probe@example.invalid", "commit", "--quiet", "--allow-empty",
            "-m", "probe", cwd=repo)
        info = run_claude(repo, "Run exactly this shell command once and report its output verbatim: git checkout -b probe-branch",
                          args.model, "low", {"hooks": REVIEW_HOOKS}, tools, Path(tmp) / "stream.jsonl", append=body)
        branch = git("branch", "--show-current", cwd=repo)
    # the hook, not the model's own caution: the tool result must carry agent-guard's message
    hooked = any("Blocked by agent-guard (review)" in r for r in info["tool_results"])
    blocked = branch != "probe-branch" and hooked
    print(f"probe: model {info['model']}, branch after the run '{branch}', agent-guard message in a tool result: {hooked}, "
          f"{'hook BLOCKED it (ok)' if blocked else 'NOT shown to be blocked by the hook'}")
    sys.exit(0 if blocked else 1)


def cmd_void_check(args):
    stream = Path(args.stream).resolve()
    repo = Path(args.repo).resolve() if args.repo else stream.parent / "repo"
    name = re.sub(r"(-review)?(-void\d+)?$", "", stream.parent.name)  # a kept void run is <case>[-review]-voidN
    case = next((c for c in load_cases() if c["id"] == name), None)
    hits = void_hits(parse_stream(stream)["tool_inputs"], stream.parent, repo, case)
    print("VOID: " + ", ".join(hits) if hits else "clean")
    sys.exit(1 if hits else 0)


def self_test():
    problems = []
    try:
        cases = load_cases()
        if len([c for c in cases if c["kind"] == "review"]) < 3 or not [c for c in cases if c["kind"] == "replay"]:
            problems.append("need at least 3 review cases and 1 replay")
        for c in cases:
            text = c["task"] + c.get("review_task", "")
            for key in re.findall(r"\{(\w+)\}", text):
                if key not in ("repo", "range", "task", "n"):
                    problems.append(f"{c['id']}: unknown placeholder {{{key}}}")
    except (ValueError, OSError, KeyError) as error:
        problems.append(f"cases: {error}")
    body, tools = reviewer_body()
    if not body or {"Write", "Edit"} & set(tools) or "Bash" not in tools:
        problems.append(f"reviewer body or tools wrong: tools {tools}")
    with tempfile.TemporaryDirectory() as tmp:
        def stream(name, tool_input):
            path = Path(tmp) / name
            path.write_text("\n".join(json.dumps(e) for e in [
                {"type": "system", "subtype": "init", "model": "claude-test-1-0"},
                {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": tool_input}]}},
                {"type": "result", "result": "PASS", "total_cost_usd": 0.5, "duration_ms": 9, "is_error": False}]) + "\n")
            return parse_stream(path)
        clean = stream("clean.jsonl", {"command": "git diff abc..def"})
        if clean["model"] != "claude-test-1-0" or clean["cost_usd"] != 0.5 or clean["result"] != "PASS" or void_hits(clean["tool_inputs"]):
            problems.append(f"parse or void-check wrong on a clean stream: {clean}")
        for name, tool_input in [("known", {"file_path": str(KIT / "cases" / "aps32-guard" / "known.md")}),
                                 ("known-copy", {"command": "cat /tmp/somewhere/known.md"}),
                                 ("kit", {"pattern": "MAJOR", "path": "../coding-playbook/switch-test/runs"}),
                                 ("projects", {"command": "grep -r MAJOR ~/.claude/projects/"}),
                                 ("other-run", {"command": "cat ~/.cache/model-switch-runs/2026-01-01-x-high/aps32-guard/stream.jsonl"})]:
            if not void_hits(stream(name + ".jsonl", tool_input)["tool_inputs"], CACHE / "2026-01-01-y-high" / "aps34-boundary"):
                problems.append(f"void-check missed the {name} read")
        own = CACHE / "r1" / "aps32-guard"
        if void_hits([json.dumps({"command": f"git -C {own}/repo diff a..b"})], own) or \
                void_hits([json.dumps({"command": f"R={own}/repo\nls $R; cat {own}/repo;"})], own):
            problems.append("void-check flagged the run's own clone")
        if not void_hits([json.dumps({"command": f"cat {own}-review/stream.jsonl"})], own, own / "repo"):
            problems.append("void-check let a sibling run folder whose name only starts like the run's own pass")
        mine = json.dumps({"file_path": str(HOME / session_folder(own / "repo")) + "/s1/tool-results/x.txt"})
        if void_hits([mine], own, own / "repo"):
            problems.append("void-check flagged the run's own session folder")
        guard_case = next(c for c in cases if c["id"] == "aps32-guard")
        for probe in ["cat ~/work/ambysto/coding-playbook/hooks/agent-guard.py", "git -C /x/work/ambysto/coding-playbook log",
                      "sed -n 1,40p ~/.claude/hooks/1prompt/agent-guard.py", f"cat {HOME}/.claude/hooks/1prompt/agent-guard.py"]:
            if not void_hits([json.dumps({"command": probe})], own, own / "repo", guard_case):
                problems.append(f"void-check missed an answer key: {probe}")
        if not void_hits([json.dumps({"command": 'cat "$HOME/.claude/hooks/1prompt/agent-guard.py"'})], own, own / "repo", guard_case):
            problems.append("void-check missed an answer key written with $HOME")
        if void_hits([json.dumps({"name": "Edit", "input": {"new_string": "installs to ~/.claude/hooks/1prompt/agent-guard.py"}})],
                     own, own / "repo", guard_case):
            problems.append("void-check flagged an install path in content the run writes")
        if not void_hits([json.dumps({"name": "Write", "input": {"content": "see switch-test/cases/x/known.md"}})], own, own / "repo"):
            problems.append("void-check let a write that names the kit's answers through")
        if void_hits([json.dumps({"command": "ls /x/work/ambysto/coding-playbook-guard"})], own, own / "repo", guard_case):
            problems.append("void-check flagged a different repo whose name only starts like the source")
        theirs = json.dumps({"file_path": str(HOME / session_folder(CACHE / "r0" / "aps32-guard" / "repo")) + "/s0/x.jsonl"})
        if not void_hits([theirs], own, own / "repo"):
            problems.append("void-check missed another run's session folder")
        replay_case = next(c for c in cases if c["id"] == "aps37-token-guard")
        def tool(name, **args):
            return json.dumps({"name": name, "input": args})
        for case, probe in [(guard_case, tool("Bash", command="cd ~/work/ambysto/coding-playbook\ncat hooks/agent-guard.py")),
                            (guard_case, tool("Bash", command="cd ~/work/ambysto/coding-playbook&&cat x|head")),
                            (replay_case, tool("Bash", command="cd ~/.claude/hooks/owner-token-guard && cat *.py")),
                            (replay_case, tool("Bash", command="ls -la ~/.claude/hooks/owner-token-guard")),
                            (replay_case, tool("Grep", pattern="asks gh", path=f"{HOME}/.claude/hooks")),
                            (replay_case, tool("Bash", command="grep -rn token ~/.claude")),
                            (replay_case, tool("Bash", command='rg -n token "$HOME/.claude/hooks"')),
                            (replay_case, tool("Bash", command='cat "$HOME/.claude/hooks/owner-token-guard/owner-token-guard.py"')),
                            (replay_case, tool("Bash", command='grep -rn token "$HOME/.claude/hooks/owner-token-guard"')),
                            (replay_case, tool("Bash", command="grep -rn token ~/.claude/hooks/*")),
                            (replay_case, tool("Bash", command="find / -name owner-token-guard.py -exec cat {} \\;")),
                            (replay_case, tool("Bash", command="grep -rne token ~/.claude")),
                            (replay_case, tool("Bash", command="grep -r --include '*.py' token ~/.claude")),
                            (guard_case, tool("Bash", command="grep -rn x ~/work/ambysto")),
                            (guard_case, tool("Bash", command="rg x ~/work")),
                            (replay_case, tool("Bash", command="find ~/.claude -name '*.py' | xargs grep token")),
                            (replay_case, tool("Bash", command="grep -rnE 'token|secret' ~/.claude/hooks")),
                            (replay_case, tool("Bash", command="rg 'gh auth|token' ~/.claude")),
                            (replay_case, tool("Bash", command="cat ~/.claude/hooks/*/*.py")),
                            (replay_case, tool("Bash", command="head -30 ~/.claude/hooks/*/*.py")),
                            (replay_case, tool("Bash", command="for f in $(find ~/.claude/hooks -name '*.py'); do cat $f; done")),
                            (replay_case, tool("Bash", command="find ~/.claude/hooks -name '*.py' | while read f; do cat \"$f\"; done")),
                            (replay_case, tool("Bash", command="rg --files ~/.claude/hooks | xargs cat")),
                            (replay_case, tool("Bash", command="grep -rn token ~/.claude/hook?")),
                            (replay_case, tool("Bash", command="cat > /tmp/x <<'EOF'\nx\nEOF\ngrep -rn token ~/.claude/hooks")),
                            (replay_case, tool("Bash", command="find ~/.claude/hooks -type f | sort | xargs cat")),
                            (replay_case, tool("Bash", command="find ~/.claude/hooks -type f | grep -v test | xargs cat")),
                            (replay_case, tool("Bash", command="timeout 30 grep -rn token ~/.claude/hooks")),
                            (replay_case, tool("Bash", command="env LC_ALL=C nice -n 5 grep -rn token ~/.claude/hooks")),
                            (replay_case, tool("Bash", command="(cd /tmp && grep -rn token ~/.claude/hooks)")),
                            (replay_case, tool("Bash", command="( grep -rn token ~/.claude/hooks ) 2>&1 | head")),
                            (replay_case, tool("Bash", command="{ grep -rn token ~/.claude/hooks; }")),
                            (replay_case, tool("Bash", command="echo \"1 << 2\"\ngrep -rn token ~/.claude/hooks")),
                            (replay_case, tool("Bash", command='echo "$(date)"; grep -rn token ~/.claude/hooks')),
                            (replay_case, tool("Bash", command='grep -rn token "${HOME}/.claude/hooks" | head')),
                            (replay_case, tool("Bash", command="grep -rn ${PAT} ~/.claude/hooks")),
                            (replay_case, tool("Bash", command="find ${HOME} -name owner-token-guard.py -exec cat {} \\;")),
                            (replay_case, tool("Bash", command="grep -rn 'HOME=' guard/ ; cat ~/.claude/hooks/owner-token-guard/owner-token-guard.py")),
                            (replay_case, tool("Bash", command="if grep -rq token ~/.claude/hooks; then echo y; fi")),
                            (replay_case, tool("Bash", command="time -p grep -rn token ~/.claude/hooks")),
                            (replay_case, tool("Bash", command="bash -c 'grep -rn token ~/.claude/hooks'")),
                            (replay_case, tool("Bash", command='cat "${HOME}/.claude/hooks"/*/*.py')),
                            (replay_case, tool("Bash", command="find ~/.claude/hooks -name '*.py' -exec cat {} \\;"))]:
            if not void_hits([probe], own, own / "repo", case):
                problems.append(f"void-check missed an answer key: {probe}")
        for probe in [tool("Glob", pattern="*", path=f"{HOME}/.claude/hooks"),  # names only
                      tool("Bash", command="grep -rn token ."), tool("Grep", pattern="x"),
                      tool("Bash", command='ls -la ~ | grep -E "\\.claude$"'),
                      tool("Bash", command="python3 probe.py 'grep -r x ~/.claude' 'find ~ -name y'"),
                      tool("Bash", command="grep -rn '~/.claude/hooks' ."),
                      tool("Bash", command='grep -rn "$HOME/.claude/hooks" guard/'),
                      tool("Bash", command=f"rg -n '{HOME}/.claude' scripts"),
                      tool("Bash", command="grep -rn -e '~/.claude' -- guard"),
                      tool("Bash", command="ls -ltr ~/.claude"), tool("Bash", command=f"ls -latr {HOME}/.claude"),
                      tool("Bash", command="find . -path '*/.claude/hooks/*'"),
                      tool("Bash", command="find / -maxdepth 5 -name bd -type f 2>/dev/null"),
                      tool("Bash", command="ls -R ~/.claude/hooks"), tool("Bash", command="tree ~/.claude"),
                      tool("Bash", command="export HOME=$(mktemp -d); python3 guard/install.py; ls $HOME/.claude/hooks/owner-token-guard/"),
                      tool("Bash", command="ls ~/.claude/hooks/ ~/.claude/hooks/*"),
                      tool("Bash", command="find / -maxdepth 5 -name bd 2>/dev/null | head -3"),
                      tool("Bash", command="echo 'a|b' | grep -c x; grep -n 'x|y' notes.txt"),
                      tool("Bash", command="python3 - <<'EOF'\nprobe('sed -n p ~/' + CG + '/*.yml')\nprint(open('x').read())\nEOF\necho done"),
                      tool("Bash", command="cat > docs/check.sh <<'EOF'\ngrep -rn token ~/.claude/hooks\nEOF\nchmod +x docs/check.sh"),
                      tool("Bash", command="cat <<<\"$x\" | grep -c y"),
                      tool("Bash", command='echo "$(date)"; find / -maxdepth 5 -name bd 2>/dev/null'),
                      tool("Bash", command='cd "$(git rev-parse --show-toplevel)" && find ~ -maxdepth 2 -name .claude'),
                      tool("Bash", command='R="$(mktemp -d)"\nfind / -maxdepth 3 -name bd'),
                      tool("Bash", command="export HOME=$(mktemp -d); python3 guard/install.py; cat ~/.claude/hooks/owner-token-guard/x.py"),
                      tool("Bash", command="find . -name '*.py' -exec grep -l token {} +"),
                      tool("Bash", command="cat ~/.claude/hooks/owner-token-guard-notes.txt")]:
            if void_hits([probe], own, own / "repo", replay_case):
                problems.append(f"void-check flagged a read that is not an answer key: {probe}")
    with tempfile.TemporaryDirectory() as tmp:  # the source-repo watch ignores only the kit's own output folder
        global ROOT
        saved, ROOT = ROOT, Path(tmp)
        try:
            git("init", "--quiet", tmp)
            base = repo_state(tmp)
            (Path(tmp) / "switch-test" / "runs" / "r").mkdir(parents=True)
            (Path(tmp) / "switch-test" / "runs" / "r" / "report.md").write_text("x")
            if repo_state(tmp) != base:
                problems.append("repo watch counts the kit's own runs/ output")
            (Path(tmp) / "switch-test" / "cases" / "c").mkdir(parents=True)
            (Path(tmp) / "switch-test" / "cases" / "c" / "known.md").write_text("x")
            if repo_state(tmp) == base:
                problems.append("repo watch misses a new file in the kit outside runs/")
        finally:
            ROOT = saved
    with tempfile.TemporaryDirectory() as tmp:  # a clone holds the case's commit and its history, nothing later
        global SOURCES
        saved, SOURCES = SOURCES, Path(tmp)
        try:
            src = Path(tmp) / "o" / "r"
            git("init", "--quiet", str(src))
            ident = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]
            git(*ident, "commit", "--quiet", "--allow-empty", "-m", "one", cwd=src)
            first = git("rev-parse", "--short", "HEAD", cwd=src)
            git(*ident, "commit", "--quiet", "--allow-empty", "-m", "two", cwd=src)
            git(*ident, "tag", "-a", "v2", "-m", "v2", cwd=src)
            later = git("rev-parse", "HEAD", cwd=src)
            clone({"repo": "o/r"}, Path(tmp) / "c", first)
            dest = Path(tmp) / "c"
            leaked = subprocess.run(["git", "cat-file", "-e", later], cwd=dest, capture_output=True).returncode == 0
            if leaked or git("for-each-ref", cwd=dest) or git("rev-parse", "--short", "HEAD", cwd=dest) != first:
                problems.append("clone carries commits or refs past the case's commit")
        finally:
            SOURCES = saved
    for case in load_cases("replay"):  # the review step fills {task} first, then review_one fills {repo} and {range}
        try:
            fill(case["review_task"].replace("{task}", fill(case["task"], repo="r")), repo="r", range="a..b")
        except SystemExit:
            problems.append(f"{case['id']}: review_task does not fill in two steps")
    if fill("{repo} {range}", repo="r", range="a..b") != "r a..b":
        problems.append("fill wrong")
    if problems:
        print("FAIL\n" + "\n".join(f"- {p}" for p in problems))
        sys.exit(1)
    print("PASS: cases valid, reviewer body and hooks read, stream parse and void-check (5 planted reads, answer-key reads direct or by a search rooted above them, another run's session folder and a "
          "sibling run folder caught; own clone, own session folder, name-only listings and writes allowed), "
          "clone holds nothing past the case's commit, repo watch sees the kit outside runs/")


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("review")
    p.add_argument("--model", required=True)
    p.add_argument("--effort", default="high", choices=EFFORTS)
    p.add_argument("--case")
    p = sub.add_parser("replay")
    p.add_argument("--model", required=True)
    p.add_argument("--effort", required=True, choices=EFFORTS)
    p.add_argument("--review-only", action="store_true", help="only the fixed reviewer, on an existing replay")
    p.add_argument("--run", help="the run folder name, for --review-only on an earlier day")
    p = sub.add_parser("probe")
    p.add_argument("--model", required=True)
    p = sub.add_parser("void-check")
    p.add_argument("stream")
    p.add_argument("--repo", help="the run's clone, if not <stream folder>/repo (a replay's review)")
    args = parser.parse_args()
    {"review": cmd_review, "replay": cmd_replay, "probe": cmd_probe, "void-check": cmd_void_check}[args.cmd](args)


if __name__ == "__main__":
    main()
