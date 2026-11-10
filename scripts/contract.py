"""Reads a builder's task contract and matches paths against it. Standard library only.

The contract is `agent-contract.json` in a tree's git folder, written by dispatch.py:
{"version": 1, "allow": [globs], "forbid": [globs], "checks": [commands]}. A path is inside the contract when it
matches `allow` and does not match `forbid`. `**` crosses folders, `*` and `?` stay in one, `[...]` is a set, and a
pattern ending in `/` means everything under it.
"""
import json
import os
import re
import subprocess
import sys

CONTRACT_NAME = "agent-contract.json"
FOLD_CASE = sys.platform in ("win32", "darwin")  # file systems that ignore case


def read_contract(top):
    """The tree's contract, or None when it has none. A file that is not a valid contract allows nothing."""
    out = subprocess.run(["git", "-C", str(top), "rev-parse", "--absolute-git-dir"], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    try:
        with open(os.path.join(os.path.realpath(out.stdout.strip()), CONTRACT_NAME), "rb") as f:
            raw = f.read()
    except OSError:
        return None
    contract = {"allow": [], "forbid": [], "checks": [], "broken": True}
    try:
        data = json.loads(raw.decode("utf-8"))
        lists = [data.get(k, []) for k in ("allow", "forbid", "checks")]
        if data.get("version") == 1 and all(isinstance(v, list) and all(isinstance(s, str) for s in v) for v in lists):
            contract = dict(zip(("allow", "forbid", "checks"), lists), broken=False)
    except (ValueError, AttributeError):
        pass
    return contract


def glob_regex(pattern):
    p, out, i = re.sub(r"^(\./)+", "", pattern.strip().replace("\\", "/")).lstrip("/"), "", 0
    p += "**" if p.endswith("/") else ""
    while i < len(p):
        if p.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif p.startswith("**", i):
            out, i = out + ".*", i + 2
        elif p[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif p[i] == "?":
            out, i = out + "[^/]", i + 1
        elif p[i] == "[" and "]" in p[i + 2:]:
            j = p.index("]", i + 2)
            inner = p[i + 1:j]
            out, i = out + "[" + ("^" + inner[1:] if inner.startswith("!") else inner).replace("\\", "\\\\") + "]", j + 1
        else:
            out, i = out + re.escape(p[i]), i + 1
    return re.compile(out + r"\Z", re.IGNORECASE if FOLD_CASE else 0)


def in_contract(rel, contract):
    if not contract or contract.get("broken"):
        return False
    hit = lambda patterns: any(glob_regex(p).match(rel) for p in patterns if p.strip())
    return hit(contract["allow"]) and not hit(contract["forbid"])
