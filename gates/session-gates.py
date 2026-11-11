#!/usr/bin/env python3
"""Session gates for rules that slipped as plain text (APS-66, APS-67). Hooks for every session:

  PreToolUse (Bash|Edit|Write|MultiEdit|NotebookEdit|Read|Grep|Glob):  session-gates.py pre-tool
  SubagentStop:                                                        session-gates.py subagent-stop
  By hand:  session-gates.py clear <agent id>     forget one agent (all sessions)
            session-gates.py clear --all          forget every recorded agent
            session-gates.py --self-test

Three gates, all for the main session (a call that carries `agent_id` comes from a subagent and is only recorded):
1. Branch names. A repo with `.claude/branch-name.json` ({"pattern": "<regex>", "example": "<name>"}) refuses a
   branch the main session creates, renames to or pushes with another name: `git checkout -b/-B/--orphan/--track`,
   `git switch -c/-C`, `git branch <name>`, `git branch -m`, `git worktree add` (with `-b`, or the new branch git
   names after the path), `git push` (named refs that are local branches, or the current branch) and
   `dispatch.py new <repo> <branch>`. `main` and `master` are never checked against the pattern; an optional
   "no_push": ["main"] refuses any push to or delete of the branches it lists (`git push`, `HEAD:main`, `x:main`,
   `--delete main`, `--all`).
2. Trees under review. Each subagent call records the git work trees it touches; until that agent stops (or 2 hours
   pass without a call from it), the main session may not Edit/Write a file in those trees or run a command that
   changes them there (git writes, `gh pr checkout`, `gh pr merge --delete-branch`) (lesson
   `no-edits-in-trees-agents-read`). Paths inside quoted strings of a subagent's command count too.
3. Lesson recall. A Bash command that a shared-memory lesson's `match:` regex finds, or (a lesson without `match:`)
   that contains a backticked token of six or more characters from its `applies_when`, gets that lesson named once
   per session as context.

Commands are read quote-aware over the whole text: heredoc bodies are dropped (any delimiter, quoted or backslashed),
line continuations joined, `;`, `&&`, `||`, `|`, `&`, newlines and parentheses split commands only outside quotes,
each `$( … )` or backtick substitution counts as one word holding `$`, redirections and leading shell keywords and wrappers (`if`, `then`, `do`, `{`, `!`, `time -p`, `env`, `sudo`,
`timeout 30`, ...) are dropped, and
`cd`/`pushd` carry to later commands of the same subshell. These catch mistakes, not evasion: an interpreter or a
script that runs git passes. The hook never blocks on its own error: it
prints nothing and exits 0, and its settings entry ends in `|| true`.
"""
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # not POSIX: no lock (the hook fails open there anyway)
    fcntl = None

STALE = 2 * 3600
MEMORY = Path(os.environ.get("SESSION_GATES_MEMORY", "~/work/ambysto/ambysto-memory")).expanduser()
GIT_WRITES = {"add", "commit", "merge", "rebase", "reset", "checkout", "switch", "stash", "pull", "am", "cherry-pick",
              "revert", "restore", "rm", "mv", "apply", "clean"}
UID = os.getuid() if hasattr(os, "getuid") else "u"


# ---------- state ----------

def folder():
    d = Path(tempfile.gettempdir()) / f"session-gates-{UID}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_path(session):
    return folder() / (hashlib.sha256((session or "-").encode()).hexdigest()[:24] + ".json")


class Locked:
    """load, change, save under one flock, so a SubagentStop is never lost to a concurrent call's save."""

    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.lock = open(str(self.path) + ".lock", "a")
        if fcntl:
            fcntl.flock(self.lock, fcntl.LOCK_EX)
        try:
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self.state, dict):
                raise ValueError
        except (OSError, ValueError):
            self.state = {}
        self.state.setdefault("agents", {})
        self.state.setdefault("hinted", [])
        return self.state

    def __exit__(self, *exc):
        if exc[0] is None:
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.state, f)
            os.replace(tmp, self.path)
        if fcntl:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
        self.lock.close()
        return False


# ---------- command reading ----------

HEREDOC = re.compile(r"<<(-?)[ \t]*(?:'([^'\n]+)'|\"([^\"\n]+)\"|\\?([^\s'\"<>|;&()]+))")


def strip_heredocs(text):
    """Drops heredoc bodies (up to each delimiter line), reading quotes over the whole text: a `<<` inside quotes, or
    `<<<`, starts none; `$(` inside double quotes is unquoted until its `)`; a `#` comment is copied as it is."""
    out, i, n, quote, outer, pending = [], 0, len(text), None, [], []
    while i < n:
        c = text[i]
        if quote == "'":
            out.append(c)
            quote = None if c == "'" else quote
            i += 1
        elif quote == '"':
            if c == "\\":
                out.append(text[i:i + 2])
                i += 2
                continue
            if text.startswith("$(", i):
                outer.append('"')
                quote = None
                out.append("$(")
                i += 2
                continue
            quote = None if c == '"' else quote
            out.append(c)
            i += 1
        elif c in "'\"":
            quote = c
            out.append(c)
            i += 1
        elif c == "\\":
            out.append(text[i:i + 2])
            i += 2
        elif c == ")" and outer:
            quote = outer.pop()
            out.append(c)
            i += 1
        elif c == "#" and (not out or out[-1][-1:].isspace() or out[-1][-1:] in ";&|("):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(text[i:j])
            i = j
        elif text.startswith("$((", i):
            j = text.find("))", i)
            j = n if j < 0 else j + 2
            out.append(text[i:j])
            i = j
        elif text.startswith("<<", i) and not text.startswith("<<<", i) and not (i and text[i - 1] == "<"):
            m = HEREDOC.match(text, i)
            if m:
                pending.append(m.group(2) or m.group(3) or m.group(4))
                out.append(m.group(0))
                i = m.end()
            else:
                out.append(c)
                i += 1
        elif c == "\n" and pending:
            out.append(c)
            i += 1
            for d in pending:
                while i < n:
                    j = text.find("\n", i)
                    j = n if j < 0 else j
                    line, i = text[i:j], j + 1
                    if line.strip() == d:
                        break
            pending = []
        else:
            out.append(c)
            i += 1
    return "".join(out)


def pieces(text):
    """Splits a command line outside quotes into word strings and the markers '(' and ')'."""
    text = strip_heredocs(text).replace("\\\n", " ")
    out, cur, i, quote, depth = [], [], 0, None, 0
    while i < len(text):
        c = text[i]
        if quote:
            cur.append(c)
            if c == "\\" and quote == '"' and i + 1 < len(text):
                cur.append(text[i + 1])
                i += 1
            elif quote == '"' and text.startswith("$(", i):
                depth += 1
                cur.append("(")
                i += 1
            elif quote == '"' and c == ")" and depth:
                depth -= 1
            elif c == quote and not depth:
                quote = None
        elif c in "'\"":
            quote = c
            cur.append(c)
        elif c == "\\" and i + 1 < len(text):
            cur.append(text[i:i + 2])
            i += 1
        elif text.startswith("$(", i):
            j, level = i + 2, 1
            while j < len(text) and level:
                level += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            cur.append(text[i:j])
            i = j - 1
        elif c == "&" and ((i and text[i - 1] in "<>") or text.startswith("&>", i)):
            cur.append(c)
        elif c in ";&|\n()":
            if "".join(cur).strip():
                out.append("".join(cur))
            cur = []
            if c in "()":
                out.append(c)
        elif c == "#" and (not cur or cur[-1].isspace()):
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        else:
            cur.append(c)
        i += 1
    if "".join(cur).strip():
        out.append("".join(cur))
    return out


REDIRECT_OP = re.compile(r"(\d*|&)(>>?|<)")
REDIRECT = re.compile(r"^(\d*|&)(>>?|<)")


def substitution_end(s, i):
    """Index just past the `)` that closes a `$(` whose body starts at i; None when it never closes (the caller then
    leaves the text as it is). A stack of contexts keeps nesting exact: code inside a substitution (with its own
    parenthesis count, single quotes skipped whole) and double-quoted text (where `$(` opens a new substitution)."""
    stack = [["sub", 0]]
    while i < len(s):
        c, top = s[i], stack[-1]
        if c == "\\":
            i += 2
            continue
        if top[0] == '"':
            if c == '"':
                stack.pop()
            elif s.startswith("$(", i) and not s.startswith("$((", i):
                stack.append(["sub", 0])
                i += 2
                continue
        elif c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                return None
            i = j + 1
            continue
        elif c == '"':
            stack.append(['"'])
        elif c == "(":
            top[1] += 1
        elif c == ")":
            if top[1]:
                top[1] -= 1
            else:
                stack.pop()
                if not stack:
                    return i + 1
        i += 1
    return None


def blank_substitutions(s):
    """Each `$( … )` and backtick substitution outside single quotes becomes the one word-safe token `$SUBST`, so
    its inner words are not read as the outer command's arguments (`-b feat-$(git -C x rev-parse HEAD)`)."""
    out, i, quote = [], 0, None
    while i < len(s):
        c = s[i]
        if quote == "'":
            quote = None if c == "'" else quote
        elif c == "'" and quote is None:
            quote = "'"
        elif c == '"':
            quote = None if quote == '"' else '"'
        elif c == "\\":
            out.append(s[i:i + 2])
            i += 2
            continue
        elif s.startswith("$(", i) and not s.startswith("$((", i):
            j = substitution_end(s, i + 2)
            if j is None:
                out.append(s[i:])
                break
            out.append("$SUBST")
            i = j
            continue
        elif c == "`":
            j = i + 1
            while j < len(s) and s[j] != "`":
                j += 2 if s[j] == "\\" else 1
            if j >= len(s):
                out.append(s[i:])
                break
            out.append("$SUBST")
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def split_words(piece, keep_redirects=False):
    """Words of one simple command; redirections (an unquoted operator and its target) dropped unless kept,
    then with the operator stripped from the word. Substitutions count as one word, except when recording paths."""
    if not keep_redirects:
        piece = blank_substitutions(piece)
    try:
        words = shlex.split(piece)
        raw = shlex.split(piece, posix=False)
    except ValueError:
        words = raw = piece.split()
    if len(raw) != len(words):
        raw = words
    kept, skip = [], False
    for w, r in zip(words, raw):
        if skip:
            skip = False
            if keep_redirects:
                kept.append(w)
        elif r[:1] in "'\"" or not REDIRECT.match(r):
            kept.append(w)
        elif REDIRECT_OP.fullmatch(r):
            skip = True
        elif keep_redirects:
            kept.append(REDIRECT.sub("", w).lstrip("&"))
    return kept


KEYWORDS = {"if", "then", "elif", "else", "while", "until", "do", "{", "!", "time", "nohup", "env", "command", "exec",
            "sudo", "xargs", "timeout"}
TAKES_OPTIONS = ("time", "nohup", "env", "command", "exec", "sudo", "xargs", "timeout")


def commands(text, cwd, keep_redirects=False):
    """(directory, words) for each simple command, following cd/pushd within its subshell; leading variable
    assignments and shell keywords (`then`, `do`, `{`, `time -p`, ...) dropped."""
    stack, here, out = [], cwd, []
    for p in pieces(text or ""):
        prev_kw = False
        if p == "(":
            stack.append(here)
            continue
        if p == ")":
            here = stack.pop() if stack else here
            continue
        words = split_words(p, keep_redirects)
        while words and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]) or words[0] in KEYWORDS
                         or (words[0].startswith("-") and len(words) > 1 and words[1] != "--" and prev_kw)):
            if words[0] == "timeout" and len(words) > 2:
                rest = words[1:]
                while rest and rest[0].startswith("-"):
                    rest = rest[2:] if rest[0] in ("-s", "--signal", "-k", "--kill-after") else rest[1:]
                words = ["timeout"] + rest[1:]
            if words[0] in ("-u", "-g", "--user", "--group", "--unset") and prev_kw and len(words) > 2:
                words = words[1:]
            prev_kw = prev_kw if words[0].startswith("-") else words[0] in TAKES_OPTIONS
            words = words[1:]
        if not words:
            continue
        if words[0] in ("cd", "pushd") and len(words) > 1 and "$" not in words[1]:
            here = os.path.normpath(os.path.join(here, os.path.expanduser(words[1])))
            continue
        out.append((here, words))
    return out


GIT_OPTS_WITH_VALUE = {"-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}


def git_calls(text, cwd):
    """(directory, subcommand, args) for each git call; -C followed."""
    calls = []
    for here, words in commands(text, cwd):
        if Path(words[0]).name != "git":
            continue
        i, d = 1, here
        while i < len(words) and words[i].startswith("-"):
            if words[i] == "-C" and i + 1 < len(words):
                d = os.path.normpath(os.path.join(d, os.path.expanduser(words[i + 1])))
                i += 2
            elif words[i] in GIT_OPTS_WITH_VALUE and i + 1 < len(words):
                i += 2
            else:
                i += 1
        if i < len(words):
            calls.append((d, words[i], words[i + 1:]))
    return calls


def work_tree(path):
    p = Path(os.path.expanduser(str(path)))
    while not p.exists() and p != p.parent:
        p = p.parent
    d = p if p.is_dir() else p.parent
    out = subprocess.run(["git", "-C", str(d), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def git_out(d, *args):
    out = subprocess.run(["git", "-C", str(d), *args], capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


# ---------- gate 1: branch names ----------

PUSH_OPTS_WITH_VALUE = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}


def new_branches(text, cwd, pushes=None):
    """(repo directory, branch name) for each branch a command creates, renames to or pushes (main and master left
    out); every pushed branch name, main included, is also added to `pushes` when a list is given."""
    found = []
    for d, sub, args in git_calls(text, cwd):
        if sub in ("checkout", "switch"):
            for i, a in enumerate(args):
                if a in ("-b", "-B", "-c", "-C", "--create", "--force-create", "--orphan") and i + 1 < len(args):
                    found.append((d, args[i + 1]))
                elif a in ("-t", "--track") and i + 1 < len(args) and not any(x in args for x in ("-b", "-B", "-c", "-C")):
                    found.append((d, args[i + 1].split("/", 1)[-1]))
        elif sub == "branch":
            plain = [a for a in args if not a.startswith("-")]
            flags = [a for a in args if a.startswith("-")]
            if any(f in ("-m", "-M", "--move") for f in flags) and plain:
                found.append((d, plain[-1]))
            elif plain and all(f in ("-f", "--force", "--track", "--no-track") for f in flags):
                found.append((d, plain[0]))
        elif sub == "worktree" and args[:1] == ["add"]:
            rest = args[1:]
            named = [rest[i + 1] for i, a in enumerate(rest) if a in ("-b", "-B") and i + 1 < len(rest)]
            if named:
                found += [(d, n) for n in named]
            elif "--detach" not in rest and "-d" not in rest:
                plain = [a for a in rest if not a.startswith("-")]
                if len(plain) == 1:
                    found.append((d, Path(plain[0]).name))
        elif sub == "push":
            if any(a in ("--all", "--mirror", "--branches") for a in args):
                if pushes is not None:
                    pushes.append((d, None))
                continue
            deleting = any(a in ("-d", "--delete") for a in args)
            plain, skip = [], False
            for a in args:
                if skip:
                    skip = False
                elif a in PUSH_OPTS_WITH_VALUE:
                    skip = True
                elif not a.startswith("-"):
                    plain.append(a)
            if "--tags" in args and not plain[1:]:
                continue
            refs = plain[1:] or ["HEAD"]
            for ref in refs:
                if "$" in ref:
                    continue
                if deleting or ref.startswith(":"):
                    gone = ref.lstrip(":")
                    gone = gone[len("refs/heads/"):] if gone.startswith("refs/heads/") else gone
                    if pushes is not None and gone and ref != "HEAD":
                        pushes.append((d, gone))
                    continue
                src, _, dst = ref.lstrip("+").partition(":")
                name = dst or src
                if name == "HEAD" or src == "HEAD" and not dst:
                    name = git_out(d, "symbolic-ref", "--short", "-q", "HEAD")
                name = name[len("refs/heads/"):] if name.startswith("refs/heads/") else name
                if not name or name.startswith("refs/"):
                    continue
                if dst or git_out(d, "rev-parse", "--verify", "-q", f"refs/heads/{name}"):
                    found.append((d, name))
                    if pushes is not None:
                        pushes.append((d, name))
    for here, words in commands(text, cwd):
        for i, w in enumerate(words):
            if Path(w).name == "dispatch.py" and words[i + 1:i + 2] == ["new"]:
                pos, j, rest = [], i + 2, words
                while j < len(rest) and len(pos) < 2:
                    a = rest[j]
                    if a == "--task":
                        j += 3
                    elif a == "--check":
                        j += 2
                    elif a in ("--allow", "--forbid"):
                        j += 1
                        while j < len(rest) and not rest[j].startswith("-"):
                            j += 1
                    elif a.startswith("-"):
                        j += 1
                    else:
                        pos.append(a)
                        j += 1
                if len(pos) >= 2 and "$" not in pos[1]:
                    found.append((os.path.join(here, os.path.expanduser(pos[0])), pos[1]))
    return [(d, n) for d, n in found if n and "$" not in n and n not in ("main", "master")]


def branch_rule(d):
    """(the repo's .claude/branch-name.json as a dict, its path); an empty dict when there is none or it is bad."""
    top = work_tree(d)
    if not top:
        return {}, None
    rule = Path(top) / ".claude" / "branch-name.json"
    try:
        spec = json.loads(rule.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, rule
    return (spec if isinstance(spec, dict) else {}), rule


def branch_gate(event):
    cmd = (event.get("tool_input") or {}).get("command")
    if not isinstance(cmd, str):
        return None
    pushes = []
    names = new_branches(cmd, event.get("cwd") or os.getcwd(), pushes)
    for d, name in pushes:
        spec, rule = branch_rule(d)
        guarded = spec.get("no_push") if isinstance(spec.get("no_push"), list) else []
        if name is None:
            name = next((b for b in guarded if isinstance(b, str)
                         and git_out(d, "rev-parse", "--verify", "-q", f"refs/heads/{b}")), None)
        if name is not None and name in guarded:
            return (f"a push to `{name}` is not allowed in this repo (`no_push` in {rule}); push a branch and open a "
                    f"PR instead.")
    for d, name in names:
        spec, rule = branch_rule(d)
        try:
            if not isinstance(spec.get("pattern"), str):
                continue
            ok = re.fullmatch(spec["pattern"], name)
        except re.error:
            continue
        if not ok:
            ex = f" (for example `{spec['example']}`)" if spec.get("example") else ""
            return (f"branch name `{name}` does not match this repo's rule `{spec['pattern']}`{ex}, from {rule}. "
                    f"Use a name that matches.")
    return None


# ---------- gate 2: trees a running subagent touched ----------

READ_ONLY = {("stash", "list"), ("stash", "show"), ("apply", "--check"), ("apply", "--stat"), ("clean", "-n"),
             ("clean", "--dry-run")}


def is_write(sub, args):
    if sub == "branch":
        return any(a in ("-f", "-D", "-d", "-m", "-M", "--delete", "--move", "--force") for a in args)
    if sub not in GIT_WRITES:
        return False
    if sub == "clean" and any(re.fullmatch(r"-[a-zA-Z]*n[a-zA-Z]*", a) for a in args):
        return False
    return not any((sub, a) in READ_ONLY for a in args[:2] + [a for a in args if a.startswith("-")])


INNER_PATH = re.compile(r"(?<![\w.~/:-])((?:/|~/)[\w.@%+-][^\s'\"()<>|;&,`]*)")
MAX_DIRS = 200


def touched(event):
    cwd = event.get("cwd") or os.getcwd()
    ti = event.get("tool_input") or {}
    paths = [cwd] + [ti[k] for k in ("file_path", "path", "notebook_path") if isinstance(ti.get(k), str)]
    cmd = ti.get("command")
    if isinstance(cmd, str):
        for here, words in commands(cmd, cwd, keep_redirects=True):
            paths.append(here)
            for i, w in enumerate(words):
                if (i and words[i - 1] == "-C") or w.startswith(("/", "~/")):
                    paths.append(os.path.join(here, os.path.expanduser(w)))
                else:
                    paths += [os.path.expanduser(m) for m in INNER_PATH.findall(w)]
    tops = []
    seen = []
    for p in dict.fromkeys(paths):
        d = os.path.dirname(os.path.normpath(os.path.expanduser(str(p)))) if not os.path.isdir(p) else p
        if d in seen:
            continue
        seen.append(d)
        if len(seen) > MAX_DIRS:
            break
        t = work_tree(p)
        if t and t not in tops:
            tops.append(t)
    return tops


def main_targets(event):
    """Work trees a main-session call would change: an edited file's tree, or where a changing command runs."""
    ti = event.get("tool_input") or {}
    tool = event.get("tool_name")
    if tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        p = ti.get("file_path") or ti.get("notebook_path")
        t = work_tree(p) if isinstance(p, str) else None
        return [t] if t else []
    cmd = ti.get("command")
    if tool != "Bash" or not isinstance(cmd, str):
        return []
    cwd, dirs = event.get("cwd") or os.getcwd(), []
    for d, sub, args in git_calls(cmd, cwd):
        if is_write(sub, args):
            dirs.append(d)
    for here, words in commands(cmd, cwd):
        if words[0] == "gh" and (words[1:3] == ["pr", "checkout"] or words[1:3] == ["pr", "merge"] and any(
                a == "--delete-branch" or re.fullmatch(r"-[a-zA-Z]*d[a-zA-Z]*", a) for a in words[3:])):
            dirs.append(here)
    tops = []
    for d in dirs:
        t = work_tree(d)
        if t and t not in tops:
            tops.append(t)
    return tops


def review_gate(event, state):
    now = time.time()
    live = {a: v for a, v in state["agents"].items() if now - v.get("seen", 0) < STALE}
    for top in main_targets(event):
        for aid, v in live.items():
            if top in v.get("trees", []):
                return (f"{v.get('type') or 'a subagent'} ({aid}) is still running and has read {top}; a change there "
                        f"shows up as its own (TREE CHANGED, lesson no-edits-in-trees-agents-read). Wait for it, or "
                        f"work in another worktree. If it is no longer running: "
                        f"python3 ~/.claude/hooks/gates/session-gates.py clear {aid}")
    return None


# ---------- gate 3: lesson recall ----------

def lessons():
    out = []
    lessons_dir = MEMORY / "lessons"
    if not lessons_dir.is_dir():
        return out
    for f in sorted(lessons_dir.glob("*.md")):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        head = text.split("\n---", 1)[0] if text.startswith("---") else ""
        fields = {k: (v.strip()[1:-1] if len(v.strip()) >= 2 and v.strip()[0] == v.strip()[-1] and v.strip()[0] in "\"'"
                      else v.strip()) for k, v in re.findall(r"^(\w+):\s*(.*)$", head, re.M)}
        if fields.get("status", "active") != "active":
            continue
        if fields.get("match"):
            try:
                out.append((f.stem, fields.get("title", f.stem), re.compile(fields["match"])))
            except re.error:
                pass
            continue
        tokens = re.findall(r"`([^`]{6,})`", fields.get("applies_when", ""))
        if tokens:
            out.append((f.stem, fields.get("title", f.stem), tokens))
    return out


MATCH_CHARS = 20000


def lesson_hint(event, state):
    cmd = (event.get("tool_input") or {}).get("command")
    if not isinstance(cmd, str):
        return None
    hits = []
    for slug, title, tokens in lessons():
        hit = tokens.search(cmd[:MATCH_CHARS]) if isinstance(tokens, re.Pattern) else any(t in cmd for t in tokens)
        if slug not in state["hinted"] and hit:
            hits.append(f"lesson `{slug}`: {title}")
            state["hinted"].append(slug)
    if not hits:
        return None
    return ("Shared memory has a lesson for this command; read it before going on: " + "; ".join(hits)
            + f" ({MEMORY}/lessons/<slug>.md).")


# ---------- hooks ----------

def pre_tool(event):
    session = event.get("session_id")
    aid = event.get("agent_id")
    if aid:
        trees = touched(event)
        with Locked(state_path(session)) as state:
            rec = state["agents"].setdefault(aid, {"type": event.get("agent_type"), "trees": []})
            rec["trees"] = rec["trees"] + [t for t in trees if t not in rec["trees"]]
            rec["seen"] = time.time()
        return None
    reason = branch_gate(event)
    if reason is None:
        with Locked(state_path(session)) as state:
            reason = review_gate(event, state)
            hint = None if reason else (lesson_hint(event, state) if event.get("tool_name") == "Bash" else None)
    if reason:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": reason}}
    if hint:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": hint}}
    return None


def subagent_stop(event):
    aid = event.get("agent_id")
    if aid:
        with Locked(state_path(event.get("session_id"))) as state:
            state["agents"].pop(aid, None)


def clear(arg):
    for f in folder().glob("*.json"):
        with Locked(f) as state:
            if arg == "--all":
                state["agents"] = {}
            else:
                state["agents"].pop(arg, None)
    return 0


# ---------- self-test ----------

def self_test():
    import shutil
    problems = []
    tmp = Path(tempfile.mkdtemp(prefix="session-gates-"))
    global MEMORY
    old_memory, old_tmp = MEMORY, tempfile.tempdir
    try:
        tempfile.tempdir = str(tmp / "t")
        os.makedirs(tempfile.tempdir)
        repo, other = tmp / "repo", tmp / "other"
        for r in (repo, other):
            r.mkdir()
            for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@example.invalid"],
                         ["config", "user.name", "t"], ["commit", "-q", "--allow-empty", "-m", "0"]):
                subprocess.run(["git", "-C", str(r), *args], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "branch", "aps-9-ok"], check=True)
        subprocess.run(["git", "-C", str(repo), "branch", "feature-old"], check=True)
        (repo / ".claude").mkdir()
        (repo / ".claude" / "branch-name.json").write_text(json.dumps({"pattern": r"aps-\d+-[a-z0-9-]+", "example": "aps-1-x",
                                                                            "no_push": ["main"]}))
        MEMORY = tmp / "memory"
        (MEMORY / "lessons").mkdir(parents=True)
        (MEMORY / "lessons" / "kill-own-shell.md").write_text(
            "---\ntitle: Do not pkill -f your own command line\napplies_when: when `pkill -f` targets a pattern\nstatus: active\n---\nbody\n")
        (MEMORY / "lessons" / "units.md").write_text(
            "---\ntitle: Units kill detached children\napplies_when: when code starts `--no-block` units\n"
            "match: systemd-run\\b(?![^\\n]*--scope)\nstatus: active\n---\n")
        (MEMORY / "lessons" / "quoted.md").write_text(
            "---\ntitle: Quoted\napplies_when: when x\nmatch: \"\\bfoo-quoted\\b\"\nstatus: active\n---\n")
        (MEMORY / "lessons" / "bad-regex.md").write_text(
            "---\ntitle: Bad\napplies_when: when `echo hello` runs\nmatch: echo (\nstatus: active\n---\n")
        (MEMORY / "lessons" / "old.md").write_text(
            "---\ntitle: Old\napplies_when: when `pkill -f` runs\nstatus: superseded\n---\n")

        def call(tool, inp, cwd=repo, agent=None, session="s1"):
            ev = {"session_id": session, "cwd": str(cwd), "tool_name": tool, "tool_input": inp}
            if agent:
                ev.update(agent_id=agent, agent_type="reviewer")
            return pre_tool(ev)

        def bash(cmd, **kw):
            return call("Bash", {"command": cmd}, **kw)

        def denied(out):
            return bool(out) and out["hookSpecificOutput"].get("permissionDecision") == "deny"

        for raw, want in (("a $(b) c", "a $SUBST c"), ('a "$(b "$(c)" d)" e', 'a "$SUBST" e'),
                          ("a $(echo ')') c", "a $SUBST c"), ('a $(echo "(") c', "a $SUBST c"),
                          ("a $(echo (x)) c", "a $SUBST c"), ("a $(echo \\)) c", "a $SUBST c"),
                          ("a $(echo 'x c", "a $(echo 'x c"), ("a `b \\`c\\`` d", "a $SUBST d"),
                          ("a `b c", "a `b c"), ("a $((1+2)) c", "a $((1+2)) c"), ("'$(x)' $(y)", "'$(x)' $SUBST"),
                          ('a $(b "$(c ")")" d) e', "a $SUBST e")):
            if blank_substitutions(raw) != want:
                problems.append(f"blank_substitutions({raw!r}) = {blank_substitutions(raw)!r}, expected {want!r}")
        heredoc_body = "cat > /tmp/x.md <<'EOF'\ngit checkout -b feature/x\ngit push origin feature/y\nEOF"
        quoted_heredoc = ('git commit -m "$(cat <<\'EOF\'\nFix parser (APS-66)\n\nRefuse "cd x && git checkout -b wip"'
                          ' and one more " quote\nEOF\n)"')
        cases = [("git checkout -b feature/x", True), ("git checkout -b aps-12-fix-it", False),
                 ("git switch -c Bad_Name", True), ("git checkout --orphan wip", True),
                 ("git checkout --track origin/wip", True), ("git branch wip", True), ("git branch -d wip", False),
                 ("git branch -a", False), ("git branch --list", False), ("git branch -m feature-old wip", True),
                 ("git branch -m feature-old aps-2-ok", False),
                 ("git worktree add ../w -b wip main", True), ("git worktree add ../wip", True),
                 ("git worktree add ../w aps-9-ok", False), ("git worktree add --detach ../w", False),
                 ("git push -u origin feature-old", True), ("git push origin aps-9-ok", False),
                 ("git push origin HEAD:refs/heads/wip", True), ("git push origin aps-9-ok:wip", True),
                 ("git push -o ci.skip origin aps-9-ok", False), ("git push origin -o feature-old aps-9-ok", False),
                 ("git push origin --delete feature-old", False), ("git push origin -d feature-old", False),
                 ("git push origin :feature-old", False), ("git push origin v1.0.0", False),
                 ("git push --tags", False), ("git push", True), ('git checkout -b "$B"', False),
                 (f"python3 scripts/dispatch.py new {repo} wip", True),
                 (f"python3 scripts/dispatch.py new --task p.md T1 {repo} wip", True),
                 (f"python3 scripts/dispatch.py new {repo} aps-3-x --allow a b --check c", False),
                 (f"python3 scripts/dispatch.py new --task p.md T1 {repo} aps-3-x", False),
                 ("echo a; # note; git checkout -b wip", False),
                 ("git status", False), (heredoc_body, False), (quoted_heredoc, False),
                 (quoted_heredoc + " && git checkout -b Bad", True), ("git branch 2>&1", False),
                 ("git log --grep '>' feature-old", False), ('git commit -m "$(echo "a; git checkout -b wip")"', False),
                 ("git branch > /dev/null", False), ("git branch &> f", False),
                 ("git checkout -B main origin/main", False), ("git branch -M main", False),
                 ("git push origin main", True), ("git push origin HEAD:main", True),
                 ("git push origin aps-9-ok:main", True), ("git push origin main:aps-9-ok", False),
                 ("git push origin main --tags", True), ("git push --all", True), ("git push --mirror origin", True),
                 ("git push origin --delete main", True), ("git push origin :main", True),
                 ("env git checkout -b wip", True), ("command git checkout -b wip", True),
                 ("exec git checkout -b wip", True), ("nohup git checkout -b wip", True),
                 ("for x in a; do git checkout -b wip; done", True), ("if true; then :; else git checkout -b wip; fi", True),
                 ("! git checkout -b wip", True), ("sudo git checkout -b wip", True),
                 ("timeout 30 git checkout -b wip", True), ("timeout -s KILL 30 git checkout -b wip", True),
                 ("xargs -n1 git checkout -b wip", True),
                 ("git checkout -q -b feat-$(git -C /x rev-parse --short HEAD) main", False),
                 ("git checkout -b wip-`git -C /x rev-parse HEAD`", False), ("git checkout -b \"$(echo -C x)\"", False),
                 ("git push \"$(git remote | tr -d '(')\" HEAD:main", True),
                 ("git worktree add \"../$(basename \"$PWD\" | cut -d'(' -f1)-wt\" -b wip", True),
                 ("git push origin `echo \\`echo b\\`` main", True), ("git push origin $(echo x main", True),
                 ("git checkout -q -b aps-70-sync-$(git -C /x rev-parse --short \"$(git -C /x merge-base HEAD origin/main)\") main", False),
                 ('git push origin "$(echo "$(echo b)")" HEAD:main "x)"', True),
                 ("git checkout -b \"x-$(echo ')' -C y)\" main", False), ("git push origin `echo x main", True), ("sudo -u root git checkout -b wip", True),
                 ("env -u X git checkout -b wip", True), ("echo 'a << EOF'\ngit checkout -b wip", True),
                 ("cat <<EOF\nline one\ngit checkout -b wip\nEOF", False),
                 ("echo 'x' && cat <<EOF\ngit checkout -b wip\nEOF", False),
                 ("cat > f <<\\EOF\nbody\nEOF\ngit checkout -b wip", True),
                 ("if git diff --quiet; then git checkout -b wip; fi", True), ("{ git checkout -b wip; }", True),
                 ("time git checkout -b wip", True), ("time -p git checkout -b wip", True),
                 ("git checkout \\\n  -b wip", True),
                 ("cat > f <<'END-OF-FILE'\ngit checkout -b wip\nEND-OF-FILE", False),
                 ("cat > f <<\\EOF\ngit checkout -b wip\nEOF", False),
                 ('cat "$(pwd)/f" <<EOF\ngit checkout -b wip\nEOF', False),
                 ('echo "line one\n<< EOF"\ngit checkout -b wip', True),
                 ("echo a # a comment with << EOF\ngit checkout -b wip", True), ("git worktree add ../bad 2>&1", True),
                 ('gh pr create --body "$(cat <<\'EOF\'\ngit checkout -b feature/x\nEOF\n)"', False),
                 ("FOO=1 git checkout -b wip", True), ("echo a; git checkout -b wip", True),
                 ("echo a\ngit checkout -b wip", True), ('git commit -m "a; git checkout -b wip"', False)]
        for cmd, want in cases:
            if denied(bash(cmd)) != want:
                problems.append(f"branch gate: {cmd!r} expected denied={want}")
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "feature-old"], check=True)
        if not denied(bash("git push")) or not denied(bash("git push -u origin HEAD")):
            problems.append("branch gate: push of the current branch not checked")
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "aps-9-ok"], check=True)
        if not denied(bash("git push --all origin")) or denied(bash("git push origin aps-9-ok")):
            problems.append("no_push: --all from another branch not refused, or a plain push refused")
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], check=True)
        if denied(bash("git push --all", cwd=other)):
            problems.append("no_push applied to a repo without a rule")
        if denied(bash("git checkout -b anything", cwd=other)):
            problems.append("branch gate applied to a repo without a rule")
        if denied(bash(f"git -C {other} checkout -b feature/x")) or \
                not denied(bash(f"cd {other} && git -C {repo} checkout -b feature/x", cwd=other)):
            problems.append("branch gate: -C not followed")

        call("Read", {"file_path": str(repo / "README")}, cwd=tmp, agent="r1")
        writes = ["git commit -qm x", f"cd {repo} && git commit -m \"$(cat <<'EOF'\nmsg; more\nEOF\n)\"",
                  f"git -C {repo} commit -m 'Fix a; b'", "git commit -m 'x && y'", "git checkout main",
                  "git pull --ff-only", "git branch -D wip", "git add -A", f"(cd {repo} && git commit -qm x)",
                  f"pushd {repo} && git commit -qm x", "gh pr merge 3 --delete-branch", "git stash",
                  f"(cd {other} && git status) && git commit -qm x",
                  'python3 -c "print(1 << n)"\ngit commit -qm x', "cat <<< hello\ngit commit -qm x",
                  "git commit -qm x 2>&1 | tail -3", 'echo "$(date) <<EOF"\ngit commit -qm x',
                  'git commit -m "$(cat <<\'EOF\'\nFix parser (APS-66)\n\nRefuse "x\nEOF\n)" && git commit -qm y',
                  "echo $((1 << 2))\ngit commit -qm x", f"git -C {repo} \\\n  commit -qm x", "gh pr checkout 3",
                  "gh pr merge 3 -sd"]
        for cmd in writes:
            start = tmp if cmd.startswith(("cd ", f"(cd {repo}", "pushd", "git -C")) else repo
            if not denied(bash(cmd, cwd=start)):
                problems.append(f"review gate: write allowed: {cmd!r}")
        reads = ["git status", "git diff main", "git log -1", "git fetch -q origin", "git stash list",
                 "git apply --check p.diff", "git clean -n", "git clean -nd", "git worktree add ../w2 -b aps-5-ok main",
                 f"(cd {repo} && git status) && git -C {other} commit -qm x", "gh pr merge 3 --squash"]
        for cmd in reads:
            if denied(bash(cmd)):
                problems.append(f"review gate: read or other tree denied: {cmd!r}")
        for tool, key in (("Edit", "file_path"), ("Write", "file_path"), ("MultiEdit", "file_path"),
                          ("NotebookEdit", "notebook_path")):
            if not denied(call(tool, {key: str(repo / "notes.md")}, cwd=tmp)):
                problems.append(f"review gate: {tool} into a reviewed tree allowed")
        if denied(call("Write", {"file_path": str(other / "n.md")}, cwd=repo)):
            problems.append("review gate: Write into another tree denied")
        if denied(bash("git commit -qm x", cwd=other)) or denied(bash("git commit -qm x", session="s2")):
            problems.append("review gate: another tree or session denied")
        if call("Edit", {"file_path": str(repo / "notes.md")}, agent="r5") or bash("git commit -qm x", agent="r5") \
                or bash("git checkout -b wip", agent="r5"):
            problems.append("a subagent call got a decision")
        subagent_stop({"session_id": "s1", "agent_id": "r5"})
        subagent_stop({"session_id": "s1", "agent_id": "r1"})
        if denied(bash("git commit -qm x")):
            problems.append("review gate: still denied after SubagentStop")
        bash(f"git -C {repo} log -1", cwd=tmp, agent="r2")
        if not denied(bash("git commit -qm x")):
            problems.append("review gate: -C path of a subagent call not recorded")
        clear("r2")
        if denied(bash("git commit -qm x")):
            problems.append("clear <id> did not release the tree")
        bash(f"cat {repo}/x", cwd=tmp, agent="r3")
        if not denied(bash("git commit -qm x")):
            problems.append("review gate: absolute path of a subagent call not recorded")
        with Locked(state_path("s1")) as st:
            st["agents"]["r3"]["seen"] -= STALE + 1
        if denied(bash("git commit -qm x")):
            problems.append("review gate: a stale agent still blocks")
        clear("r3")
        call("Grep", {"pattern": "x", "path": str(repo)}, cwd=tmp, agent="r4")
        if not denied(bash("git commit -qm x")):
            problems.append("review gate: Grep path of a subagent not recorded")
        clear("r4")
        call("Glob", {"pattern": "*"}, cwd=repo, agent="r6")
        if not denied(bash("git commit -qm x")):
            problems.append("review gate: cwd of a subagent call not recorded")
        clear("r6")
        for cmd in (f"wc -l < {repo}/README", f"git diff > {repo}/out.diff", f"grep -n '>' {repo}/README"):
            bash(cmd, cwd=tmp, agent="r9")
            if not denied(bash("git commit -qm x")):
                problems.append(f"review gate: path of a subagent redirect or quoted operator not recorded: {cmd!r}")
            clear("r9")
        bash(f"python3 -c \"open('{repo}/README').read()\"", cwd=tmp, agent="r10")
        if not denied(bash("git commit -qm x")):
            problems.append("review gate: a path inside a quoted string of a subagent call not recorded")
        clear("r10")
        bash(f'cat "$(git -C {repo} rev-parse --show-toplevel)/x"', cwd=tmp, agent="r13")
        if not denied(bash("git commit -qm x")):
            problems.append("review gate: a -C path inside a subagent's substitution not recorded")
        clear("r13")
        bash("cat " + " ".join(f"/tmp/nowhere-{k}/x" for k in range(45)) + f" {repo}/README", cwd=tmp, agent="r11")
        if not denied(bash("git commit -qm x")):
            problems.append("review gate: a path after many others not recorded")
        clear("r11")
        bash(f"scp host:{repo}/README /tmp/x", cwd=tmp, agent="r12")
        if denied(bash("git commit -qm x")):
            problems.append("review gate: a remote host:path recorded as a local tree")
        clear("r12")
        env = dict(os.environ, TMPDIR=tempfile.tempdir)
        procs = [subprocess.Popen([sys.executable, os.path.abspath(__file__), "pre-tool"], stdin=subprocess.PIPE, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(16)]
        for k, pr in enumerate(procs):
            pr.stdin.write(json.dumps({"session_id": "par", "cwd": str(tmp), "tool_name": "Read", "agent_id": f"p{k}",
                                       "tool_input": {"file_path": str(tmp)}}).encode())
            pr.stdin.close()
        for pr in procs:
            pr.wait(timeout=60)
        with Locked(state_path("par")) as st:
            if len(st["agents"]) != 16:
                problems.append(f"parallel records lost: {len(st['agents'])} of 16 kept")
        global fcntl
        saved_fcntl, fcntl = fcntl, None
        try:
            with Locked(state_path("s9")) as st:
                st["agents"]["x"] = {"trees": [], "seen": 0}
            with Locked(state_path("s9")) as st:
                if "x" not in st["agents"]:
                    problems.append("state without fcntl not kept")
        finally:
            fcntl = saved_fcntl
        bash("git -C repo log -1", cwd=tmp, agent="r7")
        if not denied(bash("git commit -qm x")):
            problems.append("review gate: relative -C of a subagent call not recorded")
        call("Glob", {"pattern": "*", "path": str(other)}, cwd=tmp, agent="r8")
        clear("--all")
        if denied(bash("git commit -qm x")):
            problems.append("clear --all did not release")

        out = bash("pkill -f 'python3 x.py'")
        ctx = (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")
        if "kill-own-shell" not in ctx or "`old`" in ctx:
            problems.append(f"lesson hint by token: {out}")
        if bash("pkill -f 'other'"):
            problems.append("lesson hinted twice in one session")
        if "quoted" not in ((bash("run foo-quoted now") or {}).get("hookSpecificOutput", {}).get("additionalContext", "")):
            problems.append("a quoted match: value not unquoted")
        if bash("systemd-run --user --scope -q -p MemoryMax=4G true"):
            problems.append("a lesson's match ignored: hinted on the memory-cap command")
        if "units" not in ((bash("systemd-run --user --no-block true") or {}).get("hookSpecificOutput", {})
                           .get("additionalContext", "")):
            problems.append("second lesson not hinted")
        if bash("echo hello") or call("Read", {"file_path": str(repo / "x")}, session="s4"):
            problems.append("hint on an unrelated call")
        try:
            sys_stdin = sys.stdin
            import io
            sys.stdin = io.StringIO("not json")
            if main_hook(["pre-tool"]) != 0:
                problems.append("bad input did not exit 0")
        finally:
            sys.stdin = sys_stdin
    finally:
        MEMORY, tempfile.tempdir = old_memory, old_tmp
        shutil.rmtree(tmp, ignore_errors=True)
    if problems:
        for p in problems:
            print("FAIL:", p)
        return 1
    print("PASS: session-gates self-test (branch names, trees under review, lesson recall, quoting, heredocs)")
    return 0


def main_hook(args):
    try:
        event = json.load(sys.stdin)
        if args[:1] == ["pre-tool"]:
            out = pre_tool(event)
            if out:
                print(json.dumps(out))
        elif args[:1] == ["subagent-stop"]:
            subagent_stop(event)
    except Exception:
        pass
    return 0


def main():
    args = sys.argv[1:]
    if args[:1] == ["--self-test"]:
        return self_test()
    if args[:1] == ["clear"]:
        if len(args) != 2:
            print("usage: session-gates.py clear <agent id> | --all", file=sys.stderr)
            return 2
        clear(args[1])
        print("cleared")
        return 0
    return main_hook(args)


if __name__ == "__main__":
    sys.exit(main())
