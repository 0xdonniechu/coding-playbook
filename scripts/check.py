#!/usr/bin/env python3
"""Checks this repo's files: agent frontmatter, pinned models, reviewer bodies, the agent-guard hooks, global and template sections, skills, settings defaults.

Run: python scripts/check.py   (exit 0 = PASS, 1 = FAIL). Standard library only.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINNED = re.compile(r"^claude-[a-z]+-\d+-\d+(-\d{8})?$")  # optional date suffix
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
TOOLS = {"Read", "Write", "Edit", "Glob", "Grep", "Bash", "PowerShell", "WebFetch", "WebSearch", "NotebookEdit"}
AGENTS = {"builder", "reviewer", "hard-reviewer", "transcriber"}
GUARD_COMMAND = 'python3 "$HOME/.claude/hooks/1prompt/agent-guard.py" {mode}'
# agents with a shell whose limits the hooks enforce: (event, matcher or None, mode) each must have
REVIEW_HOOKS = [("PreToolUse", "*", "review"), ("PostToolUse", "Bash|PowerShell", "review-after"), ("Stop", None, "review-stop")]
BUILD_HOOKS = [("PreToolUse", "*", "build"), ("PostToolUse", "Bash|PowerShell|Edit|Write|MultiEdit|NotebookEdit", "build-after"),
               ("Stop", None, "build-stop")]  # the task contract (APS-46); scripts/dispatch.py writes it
GUARDED = {"builder": BUILD_HOOKS, "reviewer": REVIEW_HOOKS, "hard-reviewer": REVIEW_HOOKS}
TEMPLATE_SECTIONS = ["## What it does", "## Verify", "## HARD", "## MEDIUM", "## EASY", "## Rules", "## Read when", "## Session state"]
SKILLS = {"starter-kit", "handoff", "sdlc", "teardown", "orca-worktree-setup", "agent-team", "create-skill", "secrets", "whats-next"}
HAND_INVOKED = {"orca-worktree-setup", "agent-team", "create-skill"}  # own skills that settings-defaults.json may set to user-invocable-only
DEFAULT_KEYS = {"enabledPlugins", "skillOverrides"}
OVERRIDES = {"on", "name-only", "user-invocable-only", "off"}
DESCRIPTION_LIMIT = 1024  # the Agent Skills spec maximum; Claude Code's own cut-off is higher

failures = []

# The scripts' own --self-test runs are independent of each other and of the file checks below, so they start at once on a
# few worker threads (slowest first) and each result is read, and its failure reported, at the place it always was: the
# order of the output does not depend on which finishes first. scripts/switch-model.py's self-test runs this file in scratch
# copies with SWITCH_MODEL_SELF_TEST set: a copy differs from this tree only in the files a model switch edits, so there
# the script self-tests (same code, already run by the outer run) are skipped and the file and consistency checks run.
SELF_TESTS = [("scripts/switch-model.py", False, None), ("scripts/sdlc-check.py", False, None), ("loop/loop-stop.py", False, 600),
              ("graph/graph-hook.py", False, 600), ("scripts/plane.py", False, None), ("hooks/agent-guard.py", True, None),
              ("scripts/dispatch.py", False, None), ("loop/loop.py", False, 600), ("loop/loop-wake.py", False, 600), ("saveit/saveit-hook.py", False, None),
              ("scripts/progress-diagram.py", False, None), ("scripts/github-boundary.py", True, None),
              ("guard/owner-token-guard.py", True, None), ("scripts/switch-test.py", False, None)]
IN_SWITCH_COPY = bool(os.environ.get("SWITCH_MODEL_SELF_TEST"))
_pool = ThreadPoolExecutor(max_workers=6)
_futures = {} if IN_SWITCH_COPY else {
    rel: _pool.submit(subprocess.run, [sys.executable, str(ROOT / rel), "--self-test"], capture_output=True, text=True, timeout=timeout)
    for rel, _, timeout in SELF_TESTS}
_stdout_only = {rel: only for rel, only, _ in SELF_TESTS}


def self_test(rel):
    """The finished run of rel --self-test (None in a switch-model copy); a failure is reported as it always was."""
    if IN_SWITCH_COPY:
        return None
    run = _futures[rel].result()
    if run.returncode != 0:
        fail(f"{rel} --self-test failed:\n" + (run.stdout if _stdout_only[rel] else run.stdout + run.stderr).strip())
    return run


def fail(msg):
    failures.append(msg)


def read(rel):
    path = ROOT / rel
    if not path.exists():
        fail(f"{rel}: missing")
        return ""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def split_frontmatter(rel):
    """Returns (fields, body). A file whose frontmatter is not opened and closed by '---' lines fails."""
    text = read(rel)
    if not text.startswith("---\n"):
        fail(f"{rel}: no frontmatter")
        return {}, None
    head, fence, body = text[4:].partition("\n---\n")
    if not fence:
        fail(f"{rel}: frontmatter is not closed by a '---' line")
        return {}, None
    fields = {}
    for line in head.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip().strip("\"'")
    return fields, body


def model_label(model_id):
    """claude-sonnet-5-5 -> 'Sonnet 5.5', the way rores/global/CLAUDE.md names it."""
    _, family, major, minor = model_id.split("-")[:4]
    return f"{family.capitalize()} {major}.{minor}"


agents = {}
for path in sorted((ROOT / "rores" / "agents").glob("*.md")):
    rel = f"rores/agents/{path.name}"
    fields, body = split_frontmatter(rel)
    name = path.stem
    agents[name] = (fields, body)
    if fields.get("name") != name:
        fail(f"{rel}: name '{fields.get('name')}' does not match the file name")
    if not fields.get("description"):
        fail(f"{rel}: no description")
    if not PINNED.match(fields.get("model", "")):
        fail(f"{rel}: model '{fields.get('model')}' is not a pinned full model ID (aliases upgrade silently)")
    if fields.get("effort") not in EFFORTS:
        fail(f"{rel}: effort '{fields.get('effort')}' is not one of {sorted(EFFORTS)}")
    if "tools" in fields:
        unknown = {t.strip() for t in fields["tools"].split(",")} - TOOLS
        if unknown:
            fail(f"{rel}: unknown tools {sorted(unknown)}")

if set(agents) != AGENTS:
    fail(f"rores/agents/: expected {sorted(AGENTS)}, found {sorted(agents)}")

rev, hard = agents.get("reviewer", ({}, None)), agents.get("hard-reviewer", ({}, None))
if rev[1] is None or hard[1] is None or rev[1] != hard[1]:
    fail("rores/agents/hard-reviewer.md body differs from rores/agents/reviewer.md body (edit reviewer.md, then copy its body)")
for name, (fields, _) in agents.items():
    writers = {"Write", "Edit", "NotebookEdit"} & {t.strip() for t in fields.get("tools", "Write").split(",")}
    if "reviewer" in name and writers:
        fail(f"rores/agents/{name}.md: a reviewer needs an explicit tools list without {sorted(writers)}")

for name, hooks in GUARDED.items():
    text = read(f"rores/agents/{name}.md").split("\n---\n", 1)[0]
    blocks = re.split(r"\n  (?=\w+:\n)", text.split("\nhooks:\n", 1)[1]) if "\nhooks:\n" in text else []
    for event, matcher, mode in hooks:
        block = next((b for b in blocks if b.lstrip().startswith(f"{event}:")), "")
        if GUARD_COMMAND.format(mode=mode) not in block or (matcher and f'- matcher: "{matcher}"' not in block):
            fail(f"rores/agents/{name}.md: no {event} hook running agent-guard.py {mode}" + (f" on {matcher}" if matcher else ""))
for name, (fields, _) in agents.items():
    tools = {t.strip() for t in fields.get("tools", "Bash").split(",")}
    if name not in GUARDED and tools & {"Bash", "PowerShell"}:
        fail(f"rores/agents/{name}.md: has a shell but no agent-guard hook (add it to GUARDED in check.py and to its frontmatter)")
try:  # the settings file an autonomous run loads: the boundary hook before and after every tool, and at each stop
    auto = json.loads(read("hooks/autonomous-settings.json"))
    want = {"PreToolUse": ("*", "boundary"), "PostToolUse": ("*", "boundary-after"), "Stop": (None, "boundary-stop"),
            "SubagentStop": (None, "boundary-stop")}
    if set(auto) != {"hooks"} or set(auto["hooks"]) != set(want):
        raise ValueError(f"events must be exactly {sorted(want)}")
    for event, (matcher, mode) in want.items():
        entries = auto["hooks"][event]
        if len(entries) != 1 or entries[0].get("matcher") != matcher or \
                [h.get("command") for h in entries[0]["hooks"]] != [GUARD_COMMAND.format(mode=mode)]:
            raise ValueError(f"{event} must run agent-guard.py {mode}" + (f" on matcher \"{matcher}\"" if matcher else ""))
except (ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
    fail(f"hooks/autonomous-settings.json: not the expected settings ({type(error).__name__}: {error})")
self_test("guard/owner-token-guard.py")
self_test("saveit/saveit-hook.py")
self_test("loop/loop.py")
self_test("loop/loop-stop.py")
self_test("graph/graph-hook.py")
self_test("scripts/plane.py")
diagram = self_test("scripts/progress-diagram.py")
if diagram and diagram.returncode == 0 and diagram.stdout.startswith("not run"):
    print("note: " + diagram.stdout.strip())
self_test("scripts/github-boundary.py")
try:
    gb = json.loads(read("scripts/github-boundary.json"))
    if not (isinstance(gb.get("owner"), str) and isinstance(gb.get("repos"), list) and isinstance(gb.get("codeowners"), list)
            and "/docs/spec/" in gb["codeowners"] and "/.github/CODEOWNERS" in gb["codeowners"]):
        raise ValueError("owner, repos and codeowners (with /docs/spec/ and /.github/CODEOWNERS) are required")
    extra = gb.get("repo_codeowners", {})
    if not (isinstance(extra, dict) and all(name in gb["repos"] and isinstance(paths, list)
                                            and all(isinstance(p, str) and p.startswith("/") for p in paths)
                                            for name, paths in extra.items())):
        raise ValueError("repo_codeowners must map listed repos to lists of paths starting with /")
except (ValueError, TypeError) as error:
    fail(f"scripts/github-boundary.json: {error}")
# The hooks are copied from ambysto/1prompt at the commit hooks/pin.json names; never edited here. Their hashes must
# match the pin; when a clone of 1prompt sits next to this repo, the pinned commit's files must match too.
try:
    pin = json.loads(read("hooks/pin.json"))
    if set(pin) != {"repo", "commit", "files"} or not re.fullmatch(r"[0-9a-f]{40}", pin["commit"]) or \
            set(pin["files"]) != {"agent-guard.py", "autonomous-settings.json"}:
        raise ValueError("needs repo, a full commit sha and exactly agent-guard.py and autonomous-settings.json")
    for name, digest in pin["files"].items():
        if hashlib.sha256((ROOT / "hooks" / name).read_bytes()).hexdigest() != digest:
            fail(f"hooks/{name}: differs from hooks/pin.json (edit it in 1prompt, then copy it here and update the pin)")
    upstream = ROOT.parent / "ambysto-1prompt"
    if (upstream / ".git").exists():
        url = subprocess.run(["git", "-C", str(upstream), "remote", "get-url", "origin"], capture_output=True, text=True)
        if not re.search(r"github\.com[/:]" + re.escape(pin["repo"]) + r"(\.git)?/?$", url.stdout.strip()):
            fail(f"hooks/pin.json: {upstream.name}'s origin is not {pin['repo']}")
        merged = subprocess.run(["git", "-C", str(upstream), "merge-base", "--is-ancestor", pin["commit"],
                                 "refs/remotes/origin/main"], capture_output=True)
        if merged.returncode != 0:
            fail(f"hooks/pin.json: commit {pin['commit'][:12]} is not on {pin['repo']} origin/main in {upstream.name} "
                 "(pin a merged commit; fetch first)")
        for name in pin["files"]:
            shown = subprocess.run(["git", "-C", str(upstream), "show", f"{pin['commit']}:hooks/{name}"], capture_output=True)
            if shown.returncode != 0:
                fail(f"hooks/pin.json: commit {pin['commit'][:12]} or hooks/{name} not found in {upstream.name} (fetch it)")
            elif shown.stdout != (ROOT / "hooks" / name).read_bytes():
                fail(f"hooks/{name}: differs from {upstream.name} at {pin['commit'][:12]}")
    else:
        print("note: no ambysto-1prompt clone next to this repo; hooks checked against pin.json hashes only")
except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
    fail(f"hooks/pin.json: {type(error).__name__}: {error}")
self_test("hooks/agent-guard.py")

global_md = read("rores/global/CLAUDE.md")
for name in sorted(AGENTS & set(agents)):
    model = agents[name][0].get("model", "")
    if PINNED.match(model) and f"**{name}** ({model_label(model)})" not in global_md:
        fail(f"rores/global/CLAUDE.md: does not list '**{name}** ({model_label(model)})', the model pinned in rores/agents/{name}.md")
readme_md = read("README.md")
for name in sorted(AGENTS & set(agents)):
    model = agents[name][0].get("model", "")
    if PINNED.match(model) and not re.search(rf"^\| `rores/agents/{re.escape(name)}\.md` \|[^|\n]*\| {re.escape(model_label(model))}:", readme_md, re.M):
        fail(f"README.md: the row for rores/agents/{name}.md does not start with '{model_label(model)}:', the model pinned there")
efforts = {n: agents[n][0].get("effort") for n in AGENTS & set(agents)}
if efforts.get("reviewer") == efforts.get("hard-reviewer"):
    line = f"builder, reviewers `{efforts.get('builder')}`, transcriber `{efforts.get('transcriber')}`"
    if efforts.get("builder") == efforts.get("reviewer"):
        if line not in global_md:
            fail(f"rores/global/CLAUDE.md: the effort line does not read '{line}' (the agent files' efforts)")
    else:
        fail("rores/agents/: builder and reviewers have different efforts; update rores/global/CLAUDE.md's effort line and check.py together")
else:
    fail("rores/agents/: reviewer and hard-reviewer have different efforts (they must review alike)")
if "Current choice" not in global_md:
    fail("rores/global/CLAUDE.md: no 'Current choice' line for the main session model")
# The main session's model and effort, written in three places (scripts/switch-model.py --role main edits all three)
choice = re.search(r"^\*\*Current choice \(\d{4}-\d{2}-\d{2}\): ([A-Z][a-z]+ \d+\.\d+)\.\*\*", global_md, re.M)
entry = re.search(r"for the main session \(([A-Z][a-z]+ \d+\.\d+): `(\w+)`", global_md)
example = re.search(r"as a full model ID \(`(claude-[a-z]+-\d+-\d+)", global_md)
settings_line = re.search(r'`"model": "(claude-[a-z]+-\d+-\d+)[^"]*"`, and `(\w+)` effort under `modelSettings`', readme_md)
if not (choice and entry and example and settings_line):
    fail("rores/global/CLAUDE.md or README.md: the main session's Current choice, effort entry, model example or settings line is missing")
elif len({choice.group(1), entry.group(1), model_label(example.group(1)), model_label(settings_line.group(1))}) != 1 \
        or entry.group(2) != settings_line.group(2):
    fail(f"rores/global/CLAUDE.md and README.md disagree on the main session: Current choice {choice.group(1)}, effort entry "
         f"{entry.group(1)} `{entry.group(2)}`, example {example.group(1)}, README {settings_line.group(1)} `{settings_line.group(2)}`")

# The model switch kit (APS-45): cases valid (its self-test), and no model ID in the kit that nobody chose: the agents'
# pins, the one the kit measures against (Fable 5.1), and a published candidate the owner wrote in candidates.txt.
# The sdlc chain (APS-51): the task contract from a plan, clarify and converge.
self_test("scripts/dispatch.py")  # the builder dispatch helper (APS-46): worktree and task contract
self_test("scripts/sdlc-check.py")
self_test("scripts/switch-test.py")
# The one-command switch (APS-47). Its self-test runs this file in a scratch copy, with the variable set: skip it there.
if IN_SWITCH_COPY:
    print("note: SWITCH_MODEL_SELF_TEST is set (a switch-model self-test copy); the script self-tests, switch-model's own included, are not run here")
else:
    self_test("scripts/switch-model.py")
candidates = ROOT / "switch-test" / "candidates.txt"
allowed = {f.get("model") for f, _ in agents.values()} | {"claude-fable-5-1"} | \
    ({line.split()[0] for line in candidates.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")}
     if candidates.exists() else set())
for run_json in sorted((ROOT / "switch-test" / "runs").rglob("run.json")):  # a model a real run reported (init event)
    try:
        allowed.add(json.loads(run_json.read_text(encoding="utf-8")).get("model"))
    except (ValueError, AttributeError):
        fail(f"{run_json.relative_to(ROOT)}: not a JSON object")
for path in [ROOT / "scripts" / "switch-test.py", *sorted((ROOT / "switch-test").rglob("*"))]:
    if path.is_file() and path.name != "candidates.txt":
        for model_id in sorted(set(re.findall(r"claude-[a-z]+-\d+-\d+", path.read_text(encoding="utf-8", errors="replace")))
                               - allowed - {"claude-test-1-0"}):
            fail(f"{path.relative_to(ROOT)}: model ID {model_id} is not pinned, measured or listed in switch-test/candidates.txt")

template = read("skills/starter-kit/project-CLAUDE.md")
for section in TEMPLATE_SECTIONS:
    if section not in template:
        fail(f"skills/starter-kit/project-CLAUDE.md: missing section '{section}'")
if "## HARD" in template and "hard-reviewer" not in template.split("## HARD", 1)[1].split("\n", 1)[0]:
    fail("skills/starter-kit/project-CLAUDE.md: the HARD heading does not name hard-reviewer")

defaults_text = read("rores/global/settings-defaults.json")
try:
    defaults = json.loads(defaults_text) if defaults_text else {}
except ValueError as error:
    fail(f"rores/global/settings-defaults.json: not valid JSON ({error})")
    defaults = {}
if not isinstance(defaults, dict) or set(defaults) - DEFAULT_KEYS:
    fail(f"rores/global/settings-defaults.json: only {sorted(DEFAULT_KEYS)} may be set; the rest of settings.json is the owner's")
elif any(not isinstance(defaults.get(key, {}), dict) for key in DEFAULT_KEYS):
    fail(f"rores/global/settings-defaults.json: {sorted(DEFAULT_KEYS)} must each be an object")
else:
    for name, value in (defaults.get("enabledPlugins") or {}).items():
        if not isinstance(value, bool):
            fail(f"rores/global/settings-defaults.json: enabledPlugins.{name} must be true or false")
    for name, value in (defaults.get("skillOverrides") or {}).items():
        if value not in OVERRIDES:
            fail(f"rores/global/settings-defaults.json: skillOverrides.{name} '{value}' is not one of {sorted(OVERRIDES)}")
    if set(defaults.get("skillOverrides") or {}) & (SKILLS - HAND_INVOKED):
        fail("rores/global/settings-defaults.json: must not override this repo's own skills (only " + ", ".join(sorted(HAND_INVOKED)) + " may be set there)")

skills = sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir()) if (ROOT / "skills").is_dir() else []
if set(skills) != SKILLS:
    fail(f"skills/: expected {sorted(SKILLS)}, found {skills}")
for name in skills:
    rel = f"skills/{name}/SKILL.md"
    fields, _ = split_frontmatter(rel)
    description = fields.get("description", "")
    if fields.get("name") != name:
        fail(f"{rel}: name '{fields.get('name')}' does not match the folder name")
    if not description:
        fail(f"{rel}: no description")
    if len(description) > DESCRIPTION_LIMIT:
        fail(f"{rel}: description is {len(description)} characters, over {DESCRIPTION_LIMIT}")
    if ": " in description:
        fail(f"{rel}: description contains ': ', which breaks YAML")
if "starter-kit" in skills:
    if split_frontmatter("skills/starter-kit/SKILL.md")[0].get("disable-model-invocation") != "true":
        fail("skills/starter-kit/SKILL.md: needs 'disable-model-invocation: true' (it must cost no context)")

# install.py must write nothing for --help or an unknown argument (2026-11-08: an ignored `--help` ran the real
# install). Run against a temporary HOME, so a regression writes there, never into the real ~/.claude.
# HOME is what Path.home() reads on Linux and macOS, USERPROFILE on Windows; the probe stops the test if neither holds.
for args, code, stream in ((["--help"], 0, "stdout"), (["-h"], 0, "stdout"), (["--hlep"], 2, "stderr"),
                           (["--check", "-x"], 2, "stderr")):
    with tempfile.TemporaryDirectory() as home:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "CLAUDE"))
               and k not in ("HOMEDRIVE", "HOMEPATH")} | {"HOME": home, "USERPROFILE": home}
        probe = subprocess.run([sys.executable, "-c", "from pathlib import Path; print(Path.home())"], env=env,
                               capture_output=True, text=True, timeout=60).stdout.strip()
        if Path(probe).resolve() != Path(home).resolve():
            fail(f"install.py argument test not run: Path.home() is {probe!r} under a temporary HOME, not the temp folder")
            break
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "install.py"), *args], env=env,
                             capture_output=True, text=True, timeout=60)
        if out.returncode != code or "install.py --global" not in getattr(out, stream) or any(Path(home).iterdir()):
            fail(f"install.py {' '.join(args)}: expected exit {code}, usage on {stream} and nothing written; "
                 f"got exit {out.returncode}, wrote {sorted(p.name for p in Path(home).iterdir())}")

# An earlier install's block (roles-assign or claudecode-guide markers) is taken over, never duplicated: the reviewer
# of the roles-assign sync found a second full block appended (2026-11-10). Temporary HOME again.
for legacy in ("roles-assign", "claudecode-guide"):
    with tempfile.TemporaryDirectory() as home:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "CLAUDE"))
               and k not in ("HOMEDRIVE", "HOMEPATH")} | {"HOME": home, "USERPROFILE": home}
        claude = Path(home) / ".claude"
        claude.mkdir()
        (claude / "CLAUDE.md").write_text(f"# mine\n\n<!-- {legacy}:begin -->\nold block text\n<!-- {legacy}:end -->\n\n## local\nkeep me\n",
                                          encoding="utf-8")
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "install.py"), "--global"], env=env,
                             capture_output=True, text=True, timeout=120)
        text = (claude / "CLAUDE.md").read_text(encoding="utf-8")
        if out.returncode != 0 or text.count("<!-- coding-playbook:begin -->") != 1 or text.count("<!-- coding-playbook:end -->") != 1 \
                or f"<!-- {legacy}:" in text or "old block text" in text or "keep me" not in text or "# mine" not in text:
            fail(f"install.py --global over a '{legacy}' block: expected one coding-playbook block, the old one gone and "
                 f"the owner's text kept; got exit {out.returncode}, {text.count('coding-playbook:begin')} block(s)")

# --settings registers the session hooks once each, after hooks already there (another tool's SessionStart entry
# stays first and unchanged), and a second run changes nothing. Temporary HOME again.
with tempfile.TemporaryDirectory() as home:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "CLAUDE"))
           and k not in ("HOMEDRIVE", "HOMEPATH")} | {"HOME": home, "USERPROFILE": home}
    claude = Path(home) / ".claude"
    claude.mkdir()
    other = {"hooks": [{"type": "command", "command": "other-tool session-start"}]}
    # the loop's Stop hook as an earlier install registered it (timeout 60): --settings brings it to this repo's
    old_stop = {"hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/loop/loop-stop.py" || true', "timeout": 60}]}
    (claude / "settings.json").write_text(json.dumps({"model": "claude-opus-5-5", "hooks": {"SessionStart": [other], "Stop": [old_stop]}}), encoding="utf-8")
    before = subprocess.run([sys.executable, str(ROOT / "scripts" / "install.py"), "--check"], env=env,
                            capture_output=True, text=True, timeout=120)
    if before.returncode != 1 or "save-it PreCompact hook not registered" not in before.stdout \
            or "one-prompt loop Stop hook: timeout 60" not in before.stdout:
        fail(f"install.py --check without the session hooks: expected exit 1 naming them; got exit {before.returncode}")
    runs = [subprocess.run([sys.executable, str(ROOT / "scripts" / "install.py"), *args], env=env,
                           capture_output=True, text=True, timeout=120) for args in (["--settings"], ["--settings"], ["--check"])]
    hooks = json.loads((claude / "settings.json").read_text(encoding="utf-8")).get("hooks", {})
    commands = {event: [h.get("command") for e in hooks.get(event, []) for h in e.get("hooks", [])] for event in hooks}
    stop_timeouts = [h.get("timeout") for e in hooks.get("Stop", []) for h in e.get("hooks", [])]
    want = {"PreToolUse": ['python3 "$HOME/.claude/hooks/owner-token-guard/owner-token-guard.py"'],
            "SessionStart": ["other-tool session-start", 'python3 "$HOME/.claude/hooks/saveit/saveit-hook.py" session-start || true',
                             'python3 "$HOME/.claude/hooks/graph/graph-hook.py" session-start || true'],
            "SessionEnd": ['python3 "$HOME/.claude/hooks/graph/graph-hook.py" session-end || true'],
            "PreCompact": ['python3 "$HOME/.claude/hooks/saveit/saveit-hook.py" pre-compact || true'],
            "Stop": ['python3 "$HOME/.claude/hooks/loop/loop-stop.py" || true'],
            "SubagentStop": ['python3 "$HOME/.claude/hooks/loop/loop-stop.py" subagent-stop || true']}
    if [r.returncode for r in runs] != [0, 0, 0] or commands != want or "installed  " + str(claude / "settings.json") in runs[1].stdout \
            or stop_timeouts != [1800] \
            or not (claude / "hooks" / "saveit" / "saveit-hook.py").is_file() \
            or not (claude / "hooks" / "loop" / "loop-stop.py").is_file() \
            or not (claude / "hooks" / "graph" / "graph-hook.py").is_file():
        fail(f"install.py --settings session hooks: expected {want} registered once, the second run unchanged and --check clean; "
             f"got exits {[r.returncode for r in runs]}, {commands}")

# A refusal writes nothing: with --settings and a hooks event that is not a list, exit 2 before any file is copied
# (hard-reviewer, 2026-11-10: the agents, skills and hooks used to be written first). Temporary HOME again.
with tempfile.TemporaryDirectory() as home:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "CLAUDE"))
           and k not in ("HOMEDRIVE", "HOMEPATH")} | {"HOME": home, "USERPROFILE": home}
    claude = Path(home) / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(json.dumps({"hooks": {"PreCompact": {}}}), encoding="utf-8")
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "install.py"), "--settings"], env=env,
                         capture_output=True, text=True, timeout=120)
    left = sorted(p.relative_to(claude).as_posix() for p in claude.rglob("*"))
    if out.returncode != 2 or left != ["settings.json"]:
        fail(f"install.py --settings over a bad hooks shape: expected exit 2 and nothing written; got exit {out.returncode}, {left[:5]}")

if failures:
    print("FAIL")
    for f in failures:
        print(f"- {f}")
    sys.exit(1)
print(f"PASS: {len(agents)} agents pinned, reviewer bodies equal, guard hooks set and " + ("not self-tested (SWITCH_MODEL_SELF_TEST is set: script self-tests skipped)" if IN_SWITCH_COPY else "self-tested") + f", session hooks registered once, global matches the pinned models, template sections present, {len(skills)} skills valid, settings defaults valid")
