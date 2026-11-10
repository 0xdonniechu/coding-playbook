#!/usr/bin/env python3
"""Installs coding-playbook on this machine.

  python scripts/install.py            copy rores/agents/ to ~/.claude/agents, the pinned hooks to ~/.claude/hooks/1prompt
                                       and skills/ to ~/.claude/skills (a differing file is backed up first)
  python scripts/install.py --global   also put rores/global/CLAUDE.md into ~/.claude/CLAUDE.md, between markers
  python scripts/install.py --settings also merge rores/global/settings-defaults.json (enabledPlugins, skillOverrides)
                                       into ~/.claude/settings.json and register the session hooks (owner-token guard,
                                       save-it SessionStart and PreCompact), backing it up first
  python scripts/install.py --check    change nothing; exit 1 if the installed copy differs from this repo
  python scripts/install.py --help     print this and change nothing; any other argument: exit 2, nothing written

settings.json is written only with --settings, and only the entries listed in rores/global/settings-defaults.json
and the session hooks (each appended once to its event's list); every other key keeps its value.
The model and effort there stay the owner's: they are only reported.
With --settings (also under --check) it refuses, exit 2 and nothing written, when settings.json is not a
UTF-8 JSON object, its enabledPlugins or skillOverrides is not an object, or a hooks event it registers is not a list.
It never deletes: a file in an installed skill's folder that this repo does not have is reported and left alone.
It refuses (exit 2, nothing written) when ~/.claude/CLAUDE.md is not UTF-8 or its markers are not exactly one
begin followed by one end: replacing text between broken markers could delete the owner's own instructions.
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home() / ".claude"
BOM = chr(0xFEFF)  # written as a code point so editors cannot strip it
BEGIN, END = "<!-- coding-playbook:begin -->", "<!-- coding-playbook:end -->"
# Markers of earlier installs of this block: a block between exactly one such pair is taken over, not duplicated.
LEGACY = [("<!-- roles-assign:begin -->", "<!-- roles-assign:end -->"),
          ("<!-- claudecode-guide:begin -->", "<!-- claudecode-guide:end -->")]
check_only = "--check" in sys.argv
with_global = "--global" in sys.argv
with_settings = "--settings" in sys.argv
if any(a in ("-h", "--help") for a in sys.argv[1:]):
    print(__doc__.strip())
    sys.exit(0)
unknown = [a for a in sys.argv[1:] if a not in ("--check", "--global", "--settings")]
if unknown:  # an ignored flag would run the real install (2026-11-08: `--help` did)
    print(f"install.py: unknown argument {' '.join(map(repr, unknown))}; nothing written\n\n{__doc__.strip()}", file=sys.stderr)
    sys.exit(2)
differs = []


def backup(path):
    """Copies path to a backup name that does not exist yet; never overwrites an earlier backup."""
    stem = f"{path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    target, n = path.with_name(stem), 1
    while target.exists():
        target, n = path.with_name(f"{stem}-{n}"), n + 1
    shutil.copy2(path, target)
    return target


def refuse(msg):
    print(f"refused    {msg}")
    sys.exit(2)


def install_file(src, dst):
    """Copies src to dst unless they are equal; a differing dst is backed up first. --check only reports."""
    if dst.exists() and dst.read_bytes() == src.read_bytes():
        print(f"unchanged  {dst}")
        return
    differs.append(str(dst))
    if check_only:
        print(f"differs    {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    note = f" (backup: {backup(dst).name})" if dst.exists() else ""
    shutil.copyfile(src, dst)
    print(f"installed  {dst}{note}")


# Hooks for every session, registered in settings.json with --settings: (label, event, entry). An entry counts as
# registered when any hook under that event has the same command. The owner-token guard (APS-37) is a PreToolUse hook;
# the save-it hooks run ambysto-saveit resume at SessionStart and tail --write at PreCompact (saveit/saveit-hook.py).
GUARD_COMMAND = 'python3 "$HOME/.claude/hooks/owner-token-guard/owner-token-guard.py"'
# `|| true`: a missing file or python3 must not exit 2, which refuses a compaction; the guard has no such tail on purpose.
SAVEIT_COMMAND = 'python3 "$HOME/.claude/hooks/saveit/saveit-hook.py" {mode} || true'
SESSION_HOOKS = [
    ("owner-token guard hook", "PreToolUse",
     {"matcher": "Bash|Read|Grep|Glob", "hooks": [{"type": "command", "command": GUARD_COMMAND}]}),
    ("save-it SessionStart hook", "SessionStart",
     {"hooks": [{"type": "command", "command": SAVEIT_COMMAND.format(mode="session-start"), "timeout": 30}]}),
    ("save-it PreCompact hook", "PreCompact",
     {"hooks": [{"type": "command", "command": SAVEIT_COMMAND.format(mode="pre-compact"), "timeout": 30}]}),
]
# Global instructions, between markers, keeping everything else in the file byte for byte. Read and checked here,
# before anything is written, so a refusal leaves the machine as it was; written further down.
claude_md = HOME / "CLAUDE.md"
raw = claude_md.read_bytes() if claude_md.exists() else b""
try:
    current = raw.decode("utf-8")
except UnicodeDecodeError:
    current = None
if current is None:
    if with_global or check_only:
        refuse(f"{claude_md} is not UTF-8; convert it first")
    print(f"skipped    {claude_md} (not UTF-8; the global block was not checked)")
else:
    nl = "\r\n" if "\r\n" in current else "\n"
    guide = (ROOT / "rores" / "global" / "CLAUDE.md").read_text(encoding="utf-8").rstrip()
    block = nl.join([BEGIN, *guide.splitlines(), END])
    original = current  # the file as it is on disk; a taken-over legacy block makes `current` differ from it
    b, e = current.count(BEGIN), current.count(END)
    if b == 0 and e == 0:
        for old_begin, old_end in LEGACY:
            if current.count(old_begin) == 1 and current.count(old_end) == 1 and current.index(old_begin) < current.index(old_end):
                current = current.replace(old_begin, BEGIN).replace(old_end, END)
                b, e = 1, 1
                break
    if b == 0 and e == 0:
        installed = False
        updated = (current.rstrip("\r\n") + nl + nl if current.strip() else "") + block + nl
    elif b == 1 and e == 1 and current.index(BEGIN) < current.index(END):
        installed = True
        before, _, rest = current.partition(BEGIN)
        _, _, after = rest.partition(END)
        updated = before + block + after
    else:
        installed = None
        updated = current
    if installed is None and (with_global or check_only):
        refuse(f"{claude_md} has {b} begin and {e} end markers, or end before begin; fix them by hand")

# Settings: the plugin and skill defaults and the session hooks are merged with --settings; model and effort are
# reported only. Every shape is checked here, before anything is written (a refusal leaves the machine as it was);
# the file is written further down, at most once, with one backup.
settings = HOME / "settings.json"
defaults = json.loads((ROOT / "rores" / "global" / "settings-defaults.json").read_text(encoding="utf-8"))
data, problem, text = {}, None, ""
if settings.exists():
    try:
        text = settings.read_bytes().decode("utf-8")
        data = json.loads(text.lstrip(BOM))
    except (ValueError, UnicodeDecodeError) as error:
        problem = str(error)
    if problem is None and not isinstance(data, dict):
        problem = "it is not a JSON object"
    if problem is None and any(not isinstance(data.get(key, {}), dict) for key in defaults):
        problem = f"one of {sorted(defaults)} is not an object"
    events = sorted({event for _, event, _ in SESSION_HOOKS})
    if problem is None and ("hooks" in data and not isinstance(data["hooks"], dict)
                            or isinstance(data.get("hooks"), dict)
                            and any(event in data["hooks"] and not isinstance(data["hooks"][event], list) for event in events)):
        problem = f"hooks, or one of hooks.{', hooks.'.join(events)}, is not the expected shape"
if problem and with_settings:
    refuse(f"{settings}: {problem}; fix it first")

# Hooks the agents' frontmatter runs (agent-guard.py; without them a guarded agent's Bash calls are all blocked),
# and autonomous-settings.json, which an autonomous run passes with `claude --settings` (the boundary hook).
# Their source is ambysto/1prompt; hooks/pin.json names the commit and the files copied from it (check.py compares
# their hashes). They go where that repo's hooks and the agents' frontmatter expect them, before the agents, so a
# failure here never leaves agents pointing at a hook that is not there.
for name in sorted(json.loads((ROOT / "hooks" / "pin.json").read_text(encoding="utf-8"))["files"]):
    install_file(ROOT / "hooks" / name, HOME / "hooks" / "1prompt" / name)

# The session hooks' files; their settings.json entries are merged further down with --settings.
install_file(ROOT / "guard" / "owner-token-guard.py", HOME / "hooks" / "owner-token-guard" / "owner-token-guard.py")
install_file(ROOT / "saveit" / "saveit-hook.py", HOME / "hooks" / "saveit" / "saveit-hook.py")

# Agents
for src in sorted((ROOT / "rores" / "agents").glob("*.md")):
    install_file(src, HOME / "agents" / src.name)

# Skills: every file of each skills/<name>/
skill_dirs = (ROOT / "skills").iterdir() if (ROOT / "skills").is_dir() else []
for skill in sorted(p for p in skill_dirs if p.is_dir()):
    wanted = {src.relative_to(skill) for src in skill.rglob("*") if src.is_file()}
    for rel in sorted(wanted):
        install_file(skill / rel, HOME / "skills" / skill.name / rel)
    installed_dir = HOME / "skills" / skill.name
    if installed_dir.is_dir():
        for extra in sorted(installed_dir.rglob("*")):
            if extra.is_file() and extra.relative_to(installed_dir) not in wanted and ".bak-" not in extra.name:
                print(f"extra      {extra} (not in this repo; left alone)")

# Global instructions: write (or report) what was computed above
if current is not None:
    if installed is None:  # with --global or --check it was refused above
        print(f"skipped    {claude_md} has {b} begin and {e} end markers, or end before begin; fix them by hand")
    elif updated == original:
        print(f"unchanged  {claude_md} (global block)")
    elif not installed and not with_global:
        print(f"not set    {claude_md} (global block not installed; optional, run with --global)")
    elif check_only:
        differs.append(f"{claude_md} (global block)")
        print(f"differs    {claude_md} (global block)")
    elif not with_global:
        print(f"skipped    {claude_md} (global block differs; run with --global to update it)")
    else:
        HOME.mkdir(parents=True, exist_ok=True)
        note = f" (backup: {backup(claude_md).name})" if claude_md.exists() else ""
        claude_md.write_bytes(updated.encode("utf-8"))
        print(f"installed  {claude_md} (global block){note}")


# Settings: merge (or report) what was checked above
if problem:
    if check_only:
        differs.append(f"{settings} (not checked)")
    print(f"settings   could not read {settings}: {problem} (defaults and the session hooks not checked)")
else:
    changes = []
    drift = [f"{key}.{name}" for key, entries in defaults.items() for name, value in entries.items()
             if data.get(key, {}).get(name) != value]
    present = any(name in data.get(key, {}) for key, entries in defaults.items() for name in entries)
    if not drift:
        print(f"unchanged  {settings} (defaults)")
    elif not present and not with_settings:
        print(f"not set    {settings} (defaults not merged; optional, run with --settings)")
    elif check_only:
        differs.append(f"{settings} (defaults)")
        print(f"differs    {settings} (defaults: {', '.join(drift)})")
    elif not with_settings:
        print(f"skipped    {settings} (defaults differ in {len(drift)} entries; run with --settings to merge them)")
    else:
        for key, entries in defaults.items():
            data.setdefault(key, {}).update(entries)
        changes.append(f"defaults: {len(drift)} entries")
    # The session hooks: each added once, after any other hooks of its event (those are never changed or reordered).
    for label, event, entry in SESSION_HOOKS:
        command = entry["hooks"][0]["command"]
        existing = data.get("hooks", {}).get(event, [])
        registered = any(isinstance(e, dict) and isinstance(e.get("hooks"), list)
                         and any(isinstance(h, dict) and h.get("command") == command for h in e["hooks"])
                         for e in existing)
        if registered:
            print(f"unchanged  {settings} ({label})")
        elif check_only:
            differs.append(f"{settings} ({label})")
            print(f"differs    {settings} ({label} not registered; run with --settings)")
        elif not with_settings:
            print(f"skipped    {settings} ({label} not registered; run with --settings)")
        else:
            data.setdefault("hooks", {}).setdefault(event, []).append(entry)
            changes.append(label)
    if changes:
        nl = "\r\n" if "\r\n" in text else "\n"
        body = json.dumps(data, indent=2, ensure_ascii=False).replace("\n", nl) + nl
        HOME.mkdir(parents=True, exist_ok=True)
        note = f" (backup: {backup(settings).name})" if settings.exists() else ""
        settings.write_bytes(((BOM if text.startswith(BOM) else "") + body).encode("utf-8"))
        print(f"installed  {settings} ({'; '.join(changes)}){note}")
    model = data.get("model") if isinstance(data.get("model"), str) else None
    model_settings = data.get("modelSettings") if isinstance(data.get("modelSettings"), dict) else {}
    per_model = model_settings.get(model or "", {}) or {}
    per_model = per_model if isinstance(per_model, dict) else {}
    effort = per_model.get("effortLevel") or data.get("effortLevel") or "(not set)"
    hint = "" if model and model.startswith("claude-") else "  <- not a pinned model ID (see rores/global/CLAUDE.md)"
    print(f"settings   model={model or '(not set)'} effort={effort}{hint}")

if check_only and differs:
    sys.exit(1)
