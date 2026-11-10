#!/usr/bin/env python3
"""PreToolUse hook for every Claude Code session: an agent never takes the owner's GitHub token (APS-37).

Agents act as the bot account where the owner said so (ambysto-memory), and GitHub refuses the bot's merges.
That boundary holds only while no agent can read the owner's token, which sits in the system keyring and is
reachable by any process of this user. This hook closes the paths an agent would use through its tools:

  deny  a command that asks gh for a token or switches account (`gh auth token`, `auth status --show-token`,
        `auth switch`, `auth logout`, and the same words written as a list, e.g. `["gh", "auth", "token"]`),
        reads gh's hosts file, or reads the keyring (`secret-tool lookup`, the keyring folder, python `keyring`);
        a Read, Grep or Glob of gh's hosts file or the keyring folder
  ask   a command that sets AMBYSTO_OWNER (the owner's own merge in ambysto-memory): Claude Code asks the owner
        to confirm each time; a run with nobody at the keyboard cannot confirm, so it is refused there

It reads the hook JSON on stdin and prints a decision; anything else is let through. It catches mistakes and
casual use, not every way a determined process could reach the keyring: a script file that does it, words split
or encoded (`au''th`, `$a token`, base64 with `eval`), or `cd` into gh's folder before reading a file are not
seen, nor `git credential-store get` (it reads `~/.git-credentials`, not the keyring); nor is AMBYSTO_OWNER set without the literal word (`export $(cat f)`). Matching is anchored to `gh`, git's
credential commands and the keyring, so prose such as a commit message about "auth tokens" is not refused. The scripts that legitimately need the owner's token (the gh wrapper, the git credential helper) run
outside the agent's tools and are not seen here.

  python3 owner-token-guard.py --self-test
"""
import json
import re
import sys

# One shell command segment (up to ; & | or a new line), so words of two different commands never combine.
SEG = r"(?:[^;&|\n\\]|\\\n|\\.)*"  # a backslash-continued line stays one segment
GH = r"(?:^|[\s;&|(`'\"/])gh(?:\.real)?\b"
TOKEN_COMMANDS = [
    (re.compile(GH + SEG + r"\bauth\b" + SEG + r"\btoken\b", re.I), "asks gh for a token"),
    (re.compile(GH + SEG + r"\bauth\b" + SEG + r"(?:--show-token|\s-t\b|\s-[a-z]*t[a-z]*\b)", re.I),
     "asks gh to show a token"),
    (re.compile(GH + SEG + r"\bauth\b" + SEG + r"\b(?:switch|logout|refresh)\b", re.I),
     "switches, refreshes or signs out a gh account"),
    (re.compile(r"[\"']gh[\"']" + r"[^\]\n]*[\"']auth[\"'][^\]\n]*[\"'](?:token|switch|logout)[\"']", re.I),
     "asks gh for a token"),
    (re.compile(GH + SEG + r"\b(?:alias\s+(?:set|import)|extension\s+(?:install|create|upgrade))\b", re.I),
     "adds a gh alias or extension, which runs with the owner's token"),
    (re.compile(r"\bgit\b" + SEG + r"\bcredential\s+(?:fill|get)\b", re.I), "asks git for a stored credential"),
    (re.compile(r"git-credential-[\w.-]+(?:\s|$)" + SEG + r"\bget\b|\bcredential-ambysto\b", re.I),
     "runs a git credential helper"),
    (re.compile(r"\bGIT_TRACE_REDACT\s*=|\bGIT_TRACE_CURL\b|\bGIT_CURL_VERBOSE\b"), "turns on git's credential traces"),
    (re.compile(r"\.config/gh/(?:[\w.*-]*\.ya?ml|\*)", re.I), "reads gh's config files"),
    (re.compile(r"\bsecret-tool\s+(?:lookup|search)\b", re.I), "reads the system keyring"),
    (re.compile(r"\.local/share/keyrings\b", re.I), "reads the keyring folder"),
    (re.compile(r"\b(?:import\s+keyring|from\s+keyring\s+import|import\s+secretstorage)\b|\bkeyring\.get_password\b"
                r"|(?:^|[\s;&|])keyring\s+get\b", re.I), "reads the keyring"),
]
OWNER = re.compile(r"\bAMBYSTO_OWNER\b")
PATH_FIELDS = ("file_path", "path", "pattern")
SECRET_PATHS = re.compile(r"\.config/gh(?:/|$)|\.local/share/keyrings", re.I)


def decide(event):
    """Return (decision, reason) or None to let the call through."""
    tool = event.get("tool_name", "")
    params = event.get("tool_input") or {}
    if tool == "Bash":
        command = str(params.get("command", ""))
        for pattern, what in TOKEN_COMMANDS:
            if pattern.search(command):
                return "deny", ("owner-token-guard: this command %s. Agents never take the owner's GitHub token or "
                                "switch accounts (APS-37); in ambysto-memory they act as the bot. If the owner "
                                "asked for this, they run it themselves." % what)
        if OWNER.search(command):
            return "ask", ("owner-token-guard: this command acts as the owner (AMBYSTO_OWNER). Confirm only if you "
                           "asked for exactly this, e.g. merging a reviewed ambysto-memory PR.")
        return None
    if tool in ("Read", "Grep", "Glob"):
        for field in PATH_FIELDS:
            if SECRET_PATHS.search(str(params.get(field, ""))):
                return "deny", ("owner-token-guard: this reads where the owner's GitHub token is kept. Agents never "
                                "take it (APS-37).")
    return None


def output(decision, reason):
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                              "permissionDecisionReason": reason}})


def self_test():
    deny = [
        "gh auth token", "/usr/bin/gh auth token --user ambysto", "GH_TOKEN=$(gh auth token) gh pr merge 3",
        "env -u GH_TOKEN /usr/bin/gh auth token --user ambysto | head -c 4",
        "python3 -c 'import subprocess; subprocess.run([\"gh\", \"auth\", \"token\"])'",
        "gh auth status --show-token", "gh auth status -t", "gh auth switch --user ambysto", "gh auth logout",
        "cat ~/.config/gh/hosts.yml", "grep oauth /home/x/.config/gh/hosts.yaml",
        "secret-tool lookup service gh:github.com", "ls ~/.local/share/keyrings/",
        "python3 -c 'import keyring; print(keyring.get_password(\"gh:github.com\", \"ambysto\"))'",
        "gh auth --user ambysto token", "gh auth --hostname github.com status -t", "gh auth -t status",
        "printf 'protocol=https\\nhost=github.com\\n' | git credential fill", "git -C x credential get",
        "~/work/ambysto/git-credential-ambysto.sh get", "gh alias set --shell e 'echo $GH_TOKEN'",
        "gh extension install someone/gh-x", "GIT_TRACE_REDACT=0 GIT_CURL_VERBOSE=1 git ls-remote https://github.com/x/y",
        "cat ~/.config/gh/*.yml", "python3 -c 'from keyring import get_password'", "gh auth refresh -s repo",
        "gh auth \\\n  token", "gh \\\n auth status \\\n --show-token",
    ]
    ask = ["AMBYSTO_OWNER=1 gh pr merge 23 --merge --admin", "export AMBYSTO_OWNER=1; gh pr merge 23",
           "env AMBYSTO_OWNER=1 gh api user"]
    allow = ["gh pr list", "gh api user --jq .login", "gh auth status", "git push origin main",
             "python3 scripts/check.py", "grep -n token scripts/check.py", "echo authentication tokens are kept",
             "cat ~/.config/ambysto-bot/token.md", "ls ~/.config/gh/", "gh pr create --title 'Auth flow' --body x",
             "git commit -m 'Fix auth token refresh'", "git log --grep 'auth token'", "grep -rn 'auth-token' src/",
             "echo 'see docs/auth/token.md'", "cat docs/auth.token.md", "gh pr view 3 --json title",
             "git credential-cache exit", "gh auth status && git status -t"]
    bad = []
    for command in deny:
        if (decide({"tool_name": "Bash", "tool_input": {"command": command}}) or ("allow",))[0] != "deny":
            bad.append("not denied: %s" % command)
    for command in ask:
        if (decide({"tool_name": "Bash", "tool_input": {"command": command}}) or ("allow",))[0] != "ask":
            bad.append("not asked: %s" % command)
    for command in allow:
        if decide({"tool_name": "Bash", "tool_input": {"command": command}}) is not None:
            bad.append("blocked: %s" % command)
    for tool, params in (("Read", {"file_path": "/home/x/.config/gh/hosts.yml"}),
                         ("Grep", {"pattern": "oauth", "path": "/home/x/.config/gh/hosts.yml"}),
                         ("Glob", {"pattern": "/home/x/.local/share/keyrings/*"}),
                         ("Grep", {"pattern": "oauth", "path": "/home/x/.config/gh"})):
        if (decide({"tool_name": tool, "tool_input": params}) or ("allow",))[0] != "deny":
            bad.append("not denied: %s %s" % (tool, params))
    if decide({"tool_name": "Read", "tool_input": {"file_path": "/home/x/work/README.md"}}) is not None:
        bad.append("blocked an ordinary Read")
    if decide({"tool_name": "Edit", "tool_input": {"file_path": "/home/x/.config/gh/hosts.yml"}}) is not None:
        pass  # Edit/Write are not this hook's concern; the permission system covers writes
    for line in bad:
        print("- " + line)
    print("%s: owner-token-guard, %d failures" % ("FAIL" if bad else "PASS", len(bad)))
    return 1 if bad else 0


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        # Not a hook event: refuse rather than let an unknown call through.
        print("owner-token-guard: unreadable hook input; refusing", file=sys.stderr)
        return 2
    verdict = decide(event if isinstance(event, dict) else {})
    if verdict:
        print(output(*verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
