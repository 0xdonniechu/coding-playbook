#!/usr/bin/env python3
"""Keep the public copy of this repo in step with this one (APS-65).

The public repo (for students) holds every file of this repo's merged main, with the rewrites in
`public-sync.json` "replace" applied to the files each one names, except the files listed as "public_only"
(its own CLAUDE.md, README.md and branch rule, written for that audience). Those are never written; each is
reported until it has been brought in step by hand after its internal counterpart changed (`--reviewed`).

  python3 scripts/sync-public.py            report what differs between internal and public main
                                            (exit 0 in step, 1 out of step, 2 refused or failed)
  python3 scripts/sync-public.py --write    bring the public work tree in step, on a branch that contains public main
                                            (exit 0 done, 3 done with public-only files still to review, 2 refused)
  python3 scripts/sync-public.py --reviewed CLAUDE.md README.md
                                            record that those public-only files are in step with internal main
  python3 scripts/sync-public.py --self-test

Both sides are read from refs, never a work tree or index: the source is this repo's origin/main (fetched
first; the config too is read there), the comparison is against "public_ref" of the public repo (default
origin/main, fetched first). A failed fetch makes a report exit 2 instead of "in step", and refuses a write. So a run from a feature branch or worktree publishes only what is merged, and "in step" means the
published repo, not an unmerged branch. `--write` refuses, writing nothing, when the public tree has uncommitted
changes, a directory to replace by a file still holds files that stay, is on main, master or a detached HEAD, does not contain public_ref, has a symlink where a file goes, or a
file to publish matches a leak pattern (secret shapes and internal names). It never commits, pushes or merges: the
main session reads the diff and does that. State lives in the public repo's `.sync-source.json`.
"""
import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = "public-sync.json"
STATE = ".sync-source.json"


class Refused(Exception):
    pass


def git(repo, *args, binary=False, check=True):
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if check and out.returncode != 0:
        raise Refused(f"git {' '.join(args)} in {repo}: {out.stderr.decode(errors='replace').strip()}")
    return out.stdout if binary else out.stdout.decode()


def ok(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True).returncode == 0


def fetch_if_remote(repo, ref, notes):
    if ref.startswith("origin/") and not ok(repo, "fetch", "-q", "origin"):
        notes.append(f"could not fetch origin in {repo}; {ref} is the last fetched one")
    if not ok(repo, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}"):
        raise Refused(f"{repo}: no commit at {ref}")


def tree(repo, ref):
    """{path: (mode, blob sha)} of a commit; a submodule or symlink entry is refused."""
    files = {}
    for entry in git(repo, "ls-tree", "-r", "-z", ref).split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        mode, kind, sha = meta.split()
        if kind != "blob" or mode == "120000":
            raise Refused(f"{repo} {ref}: {path} is a {'symlink' if mode == '120000' else kind}; not supported")
        files[path] = (mode, sha)
    return files


def blob(repo, sha):
    return git(repo, "cat-file", "blob", sha, binary=True)


def merged_config(src, ref, notes):
    """The config as merged at the source ref, never the work tree's, so a local edit changes nothing."""
    fetch_if_remote(src, ref, notes)
    try:
        cfg = json.loads(git(src, "show", f"{ref}:{CONFIG}"))
    except ValueError as e:
        raise Refused(f"{CONFIG} at {ref}: not JSON ({e})")
    for key in ("target", "replace", "public_only", "leak_patterns"):
        if key not in cfg:
            raise Refused(f"{CONFIG} at {ref}: missing '{key}'")
    cfg["source_ref"] = ref
    cfg.setdefault("public_ref", "origin/main")
    return cfg


def load_state(text):
    try:
        state = json.loads(text) if text else {}
    except ValueError as e:
        raise Refused(f"{STATE}: not JSON ({e})")
    if not isinstance(state, dict) or not isinstance(state.get("reviewed", {}), dict):
        raise Refused(f"{STATE}: not the expected object")
    state.setdefault("internal_commit", None)
    state.setdefault("reviewed", {})
    return state


def rewrite(path, data, cfg):
    rules = [r for r in cfg["replace"] if any(fnmatch.fnmatchcase(path, g) for g in r["paths"])]
    if not rules:
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused(f"{path}: a replace rule names it but it is not UTF-8")
    for r in rules:
        text = text.replace(r["from"], r["to"])
    return text.encode("utf-8")


def desired(src, cfg):
    """{path: (mode, bytes)} the public repo should hold, public-only files and the config left out."""
    skip = set(cfg["public_only"]) | {CONFIG, STATE}
    return {p: (mode, rewrite(p, blob(src, sha), cfg))
            for p, (mode, sha) in tree(src, cfg["source_ref"]).items() if p not in skip}


def compare(want, have_files, read):
    """add / update / mode / delete lists between the wanted files and a public file set."""
    add, update, mode, delete = [], [], [], []
    for p, (m, data) in sorted(want.items()):
        if p not in have_files:
            add.append(p)
            continue
        if read(p) != data:
            update.append(p)
        if have_files[p] != m:
            mode.append(p)
    return add, update, mode, delete


def reviews(src, dst_files, state, cfg, head):
    out = []
    for path in cfg["public_only"]:
        last = state["reviewed"].get(path)
        if path not in dst_files:
            if ok(src, "cat-file", "-e", f"{head}:{path}"):
                out.append((path, "missing in the public repo"))
        elif not last:
            out.append((path, "never recorded as in step"))
        elif not ok(src, "cat-file", "-e", f"{last}^{{commit}}"):
            out.append((path, f"recorded commit {last} not found"))
        elif not ok(src, "diff", "--quiet", last, head, "--", path):
            out.append((path, f"internal {path} changed since {last}"))
    return out


def leaks(want, paths, cfg):
    pats = [re.compile(p.encode()) for p in cfg["leak_patterns"]]
    return [f"{p}: matches {pat.pattern.decode()}" for p in paths for pat in pats if pat.search(want[p][1])]


def run(src, override=None, write=False, reviewed=None, out=print, source_ref="origin/main"):
    notes = []
    cfg = merged_config(src, source_ref, notes)
    dst = Path(os.path.expanduser(override or cfg["target"])).resolve()
    if not (dst / ".git").exists():
        raise Refused(f"public repo not found at {dst}")
    fetch_if_remote(dst, cfg["public_ref"], notes)
    if notes and (write or reviewed):
        raise Refused("; ".join(notes) + "; writing from a stale ref is refused")
    for n in notes:
        out("note: " + n)
    head = git(src, "rev-parse", "--short", cfg["source_ref"]).strip()
    if write or reviewed:
        if write and git(dst, "status", "--porcelain").strip():
            raise Refused(f"{dst} has uncommitted changes; commit or stash them first")
        branch = git(dst, "rev-parse", "--abbrev-ref", "HEAD").strip()
        if branch in ("main", "master", "HEAD"):
            raise Refused(f"{dst} is on {branch}; create a branch from {cfg['public_ref']} first")
        if not ok(dst, "merge-base", "--is-ancestor", cfg["public_ref"], "HEAD"):
            raise Refused(f"{dst}: branch {branch} does not contain {cfg['public_ref']}; start it from there")
    if reviewed:
        bad = [p for p in reviewed if p not in cfg["public_only"]]
        if bad:
            raise Refused(f"not public-only: {', '.join(bad)}")
        state = load_state((dst / STATE).read_text(encoding="utf-8") if (dst / STATE).exists() else "")
        synced = state["internal_commit"]
        if not synced or git(src, "rev-parse", f"{synced}^{{commit}}", check=False).strip() != \
                git(src, "rev-parse", f"{head}^{{commit}}").strip():
            raise Refused(f"the public tree was synced from {synced or 'nothing yet'}, internal is now {head}; "
                          f"run --write first, then review against that")
        for p in reviewed:
            state["reviewed"][p] = head
        (dst / STATE).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        out(f"recorded {', '.join(reviewed)} in step with internal {head}")
        return 0
    want = desired(src, cfg)
    if not write:
        pub = tree(dst, cfg["public_ref"])
        add, update, mode, _ = compare(want, {p: m for p, (m, _) in pub.items()}, lambda p: blob(dst, pub[p][1]))
        delete = sorted(set(pub) - set(want) - set(cfg["public_only"]) - {STATE})
        state = load_state(blob(dst, pub[STATE][1]).decode("utf-8") if STATE in pub else "")
        todo = reviews(src, pub, state, cfg, head)
        for label, items in (("add", add), ("update", update), ("mode", mode), ("delete", delete)):
            for p in items:
                out(f"{label:7} {p}")
        for p, why in todo:
            out(f"review  {p} by hand: {why}")
        if add or update or mode or delete or todo:
            out(f"OUT OF STEP: {len(add)} to add, {len(update)} to update, {len(mode)} mode, {len(delete)} to delete, "
                f"{len(todo)} public-only to review (internal {cfg['source_ref']} {head} vs public {cfg['public_ref']})")
            return 1
        if notes:
            out(f"UNKNOWN: in step with the last fetched refs only ({'; '.join(notes)})")
            return 2
        out(f"IN STEP: public {cfg['public_ref']} matches internal {cfg['source_ref']} {head}")
        return 0
    have = {p: m for p, (m, _) in tree(dst, "HEAD").items()}
    for p in list(want) + [STATE]:
        for parent in [dst / p, *list((dst / p).parents)]:
            if parent == dst:
                break
            if parent.is_symlink():
                raise Refused(f"{parent} is a symlink; not written through")
    add, update, mode, _ = compare(want, have, lambda p: (dst / p).read_bytes())
    delete = sorted(set(have) - set(want) - set(cfg["public_only"]) - {STATE})
    found = leaks(want, add + update, cfg)
    if found:
        raise Refused("leak pattern in a file to publish: " + "; ".join(found))
    gone = set(delete)
    clear_dirs = []
    for p in add:
        if (dst / p).is_dir():
            inside = [os.path.relpath(os.path.join(d, f), dst) for d, _, fs in os.walk(dst / p) for f in fs]
            kept = [f for f in inside if f.replace(os.sep, "/") not in gone]
            if kept:
                raise Refused(f"{p} is a directory in the public tree holding files that stay ({kept[0]}); not replaced")
            clear_dirs.append(dst / p)
    for p in delete:
        (dst / p).unlink()
        parent = (dst / p).parent
        while parent != dst and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    for d in clear_dirs:
        if d.is_dir():
            shutil.rmtree(d)
    for p in sorted(set(add + update + mode)):
        f = dst / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(want[p][1])
        os.chmod(f, 0o755 if want[p][0] == "100755" else 0o644)
    state = load_state((dst / STATE).read_text(encoding="utf-8") if (dst / STATE).exists() else "")
    state["internal_commit"] = head
    (dst / STATE).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out(f"wrote {len(add)} added, {len(update)} updated, {len(mode)} mode, {len(delete)} deleted from internal {head}; "
        f"read `git -C {dst} add -A && git -C {dst} diff --cached` (new files included) before committing")
    todo = reviews(src, have, state, cfg, head)
    for p, why in todo:
        out(f"review  {p} by hand: {why}")
    return 3 if todo else 0


def self_test():
    problems = []
    tmp = Path(tempfile.mkdtemp(prefix="sync-public-"))
    quiet = lambda s: None
    try:
        def sh(repo, *args):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

        def init(repo):
            repo.mkdir()
            sh(repo, "init", "-q", "-b", "main")
            sh(repo, "config", "user.email", "t@example.invalid")
            sh(repo, "config", "user.name", "t")

        def refused(**kw):
            try:
                run(src, None, out=quiet, source_ref="main", **kw)
            except Refused:
                return True
            return False

        def report():
            lines = []
            return run(src, None, out=lines.append, source_ref="main"), "\n".join(lines)

        src, dst = tmp / "internal", tmp / "public"
        init(src)
        init(dst)
        cfg = {"target": str(dst), "public_ref": "main", "source_ref": "no-such-ref",
               "replace": [{"from": "~/work/in/repo", "to": "~/work/pub/repo", "paths": ["rores/*"]},
                           {"from": "secret-name", "to": "a name", "paths": ["intent/*.md"]}],
               "public_only": ["CLAUDE.md", "README.md", "RULES.md"],
               "leak_patterns": ["gh" + "p_[A-Za-z0-9]{20}", "secret-" + "name"]}
        (src / CONFIG).write_text(json.dumps(cfg))
        (src / "rores").mkdir()
        (src / "intent").mkdir()
        (src / "CLAUDE.md").write_text("internal rules\n")
        (src / "README.md").write_text("internal readme\n")
        (src / "rores" / "g.md").write_text("run ~/work/in/repo/x.py\n")
        (src / "keys.txt").write_text("answer key ~/work/in/repo stays\n")
        (src / "intent" / "i.md").write_text("from secret-name\n")
        (src / "bin.dat").write_bytes(b"\xff\x00\xfe")
        (src / "tool.sh").write_text("#!/bin/sh\n")
        os.chmod(src / "tool.sh", 0o755)
        (src / "plain.py").write_text("x = 1\n")
        sh(src, "add", "-A")
        sh(src, "commit", "-qm", "one")
        (dst / "CLAUDE.md").write_text("public rules\n")
        (dst / "README.md").write_text("public readme\n")
        (dst / "old.md").write_text("gone soon\n")
        (dst / "plain.py").write_text("x = 1\n")
        os.chmod(dst / "plain.py", 0o755)
        (dst / "docs" / "a").mkdir(parents=True)
        (dst / "docs" / "a" / "inner.md").write_text("a directory the source replaces by a file\n")
        (dst / "docs" / "a" / "empty").mkdir()
        (src / "docs").mkdir()
        (src / "docs" / "a").write_text("now a file\n")
        sh(src, "add", "-A")
        sh(src, "commit", "-qm", "dir to file")
        sh(dst, "add", "-A")
        sh(dst, "commit", "-qm", "pub")
        rc, text = report()
        for want in ("add     rores/g.md", "delete  old.md", "mode    plain.py", "review  CLAUDE.md"):
            if want not in text:
                problems.append(f"first report lacks {want!r}: {text!r}")
        if "RULES.md" in text:
            problems.append(f"public-only file missing on both sides reported: {text!r}")
        if rc != 1:
            problems.append(f"first report exit {rc}")
        if not refused(write=True):
            problems.append("write on main not refused")
        sh(dst, "checkout", "-q", "--detach")
        if not refused(write=True):
            problems.append("write on a detached HEAD not refused")
        sh(dst, "checkout", "-q", "-b", "sync", "main")
        (dst / "scratch").write_text("x")
        if not refused(write=True):
            problems.append("dirty public tree not refused")
        (dst / "scratch").unlink()
        (src / "rores" / "g.md").write_text("edited in the work tree, not committed\n")
        (src / "staged.md").write_text("staged only\n")
        sh(src, "add", "staged.md")
        if run(src, None, write=True, out=quiet, source_ref="main") != 3:
            problems.append("write with reviews pending did not exit 3")
        if (dst / "rores" / "g.md").read_text() != "run ~/work/pub/repo/x.py\n":
            problems.append("path not rewritten, or work-tree content published")
        if (dst / "staged.md").exists():
            problems.append("staged file published (index read instead of the ref)")
        if (dst / "keys.txt").read_text() != "answer key ~/work/in/repo stays\n":
            problems.append("rewrite applied outside its paths")
        if (dst / "intent" / "i.md").read_text() != "from a name\n":
            problems.append("redaction not applied")
        if (dst / "bin.dat").read_bytes() != b"\xff\x00\xfe":
            problems.append("binary file changed")
        if not os.access(dst / "tool.sh", os.X_OK) or os.access(dst / "plain.py", os.X_OK):
            problems.append("executable bits not taken from the source")
        if (dst / "old.md").exists():
            problems.append("stale file not deleted")
        if not (dst / "docs" / "a").is_file() or (dst / "docs" / "a").read_text() != "now a file\n":
            problems.append("directory not replaced by the source's file")
        if (dst / "CLAUDE.md").read_text() != "public rules\n" or (dst / CONFIG).exists():
            problems.append("public-only file overwritten or config published")
        (dst / "README.md").write_text("public readme, brought in step by hand\n")
        try:
            run(src, None, reviewed=["CLAUDE.md", "README.md"], out=quiet, source_ref="main")
        except Refused as e:
            problems.append(f"--reviewed refused before the commit, with only hand edits pending: {e}")
        if (dst / "README.md").read_text() != "public readme, brought in step by hand\n":
            problems.append("--reviewed touched a public-only file")
        sh(dst, "add", "-A")
        sh(dst, "commit", "-qm", "synced")
        rc, text = report()
        if rc != 1 or not re.search(r"^(add|update|mode|delete) ", text, re.M):
            problems.append(f"unmerged sync branch counted as in step: {text!r}")
        sh(dst, "checkout", "-q", "main")
        sh(dst, "merge", "-q", "--ff-only", "sync")
        rc, text = report()
        if rc != 0:
            problems.append(f"not in step after merge: {text!r}")
        if not refused(reviewed=["CLAUDE.md"]):
            problems.append("--reviewed on main not refused")
        sh(dst, "checkout", "-q", "-b", "review-checks", "main")
        if not refused(reviewed=["plain.py"]):
            problems.append("--reviewed accepted a synced file")
        os.symlink(tmp / "elsewhere", dst / "linked")
        with open(dst / ".git" / "info" / "exclude", "a") as f:
            f.write("linked\n")
        (tmp / "elsewhere").mkdir()
        sh(dst, "checkout", "-q", "main")
        for bad in ("[]", '{"reviewed": []}'):
            try:
                load_state(bad)
                problems.append(f"state {bad} accepted")
            except Refused:
                pass
        notes = []
        sh(src, "remote", "add", "origin", str(tmp / "no-such-remote"))
        sh(src, "update-ref", "refs/remotes/origin/main", "main")
        fetch_if_remote(src, "origin/main", notes)
        if not notes:
            problems.append("failed fetch not noted")
        lines = []
        if run(src, None, out=lines.append, source_ref="origin/main") != 2 or "UNKNOWN" not in "\n".join(lines):
            problems.append(f"failed fetch reported as in step: {lines!r}")
        import inspect
        if inspect.signature(run).parameters["source_ref"].default != "origin/main":
            problems.append("the source ref default is not origin/main")
        sh(dst, "checkout", "-q", "-b", "fetch-failed", "main")
        try:
            run(src, None, write=True, out=quiet, source_ref="origin/main")
            problems.append("--write after a failed fetch not refused")
        except Refused:
            pass
        try:
            run(src, None, reviewed=["CLAUDE.md"], out=quiet, source_ref="origin/main")
            problems.append("--reviewed after a failed fetch not refused")
        except Refused:
            pass
        sh(dst, "checkout", "-q", "main")
        sh(src, "remote", "remove", "origin")
        try:
            rewrite("rores/x.md", b"\xff\xfe", cfg)
            problems.append("non-UTF-8 file under a replace rule not refused")
        except Refused:
            pass
        sub = tmp / "with-submodule"
        init(sub)
        sh(sub, "update-index", "--add", "--cacheinfo", "160000," + git(src, "rev-parse", "main").strip() + ",mod")
        sh(sub, "commit", "-qm", "gitlink")
        try:
            tree(sub, "HEAD")
            problems.append("submodule not refused")
        except Refused:
            pass
        sh(src, "checkout", "-q", "--", "rores/g.md")
        (src / "CLAUDE.md").write_text("internal rules, changed\n")
        (src / "plain.py").write_text("x = 2\n")
        (src / "RULES.md").write_text("internal branch rule\n")
        sh(src, "add", "-A")
        sh(src, "commit", "-qm", "two")
        rc, text = report()
        if rc != 1 or "review  CLAUDE.md" not in text or "README.md" in text:
            problems.append(f"changed internal CLAUDE.md not reported alone: {text!r}")
        if "update  plain.py" not in text or "review  RULES.md by hand: missing in the public repo" not in text:
            problems.append(f"content change or missing public-only file not reported: {text!r}")
        sh(dst, "checkout", "-q", "-b", "stale", "main")
        if not refused(reviewed=["CLAUDE.md"]):
            problems.append("--reviewed against a newer internal commit than the sync not refused")
        (src / "linked").mkdir()
        (src / "linked" / "f.md").write_text("must not land outside the public tree\n")
        sh(src, "add", "-A")
        sh(src, "commit", "-qm", "under an ignored symlink")
        if not refused(write=True) or (tmp / "elsewhere" / "f.md").exists():
            problems.append("write through an ignored symlink not refused")
        sh(src, "rm", "-rq", "linked")
        sh(src, "commit", "-qm", "drop linked")
        os.unlink(dst / "linked")
        run(src, None, write=True, out=quiet, source_ref="main")
        if json.loads((dst / STATE).read_text())["reviewed"].get("README.md") is None:
            problems.append("a write lost the recorded reviews (state deleted)")
        sh(dst, "add", "-A")
        sh(dst, "commit", "-qm", "stale sync")
        sh(dst, "checkout", "-q", "main")
        sh(dst, "checkout", "-q", "-b", "sync2", "main")
        st = json.loads((dst / STATE).read_text())
        st["reviewed"]["README.md"] = "0" * 40
        (dst / STATE).write_text(json.dumps(st))
        sh(dst, "commit", "-qam", "bad review")
        sh(dst, "checkout", "-q", "main")
        sh(dst, "merge", "-q", "--ff-only", "sync2")
        rc, text = report()
        if "review  README.md by hand: recorded commit" not in text:
            problems.append(f"unknown reviewed commit not reported: {text!r}")
        sh(dst, "checkout", "-q", "-b", "sync3", "main")
        (src / "new.md").write_text("token " + "gh" + "p_" + "A" * 24 + "\n")
        sh(src, "add", "-A")
        sh(src, "commit", "-qm", "leak in a new file")
        if not refused(write=True):
            problems.append("leak in an added file not refused")
        loose = dict(cfg, leak_patterns=[])
        (src / CONFIG).write_text(json.dumps(loose))
        if not refused(write=True):
            problems.append("an uncommitted config edit weakened the leak check")
        (src / CONFIG).write_text(json.dumps(cfg))
        if (dst / "new.md").exists():
            problems.append("refused write left a file")
        sh(src, "rm", "-q", "new.md")
        sh(src, "commit", "-qm", "unleak")
        (src / "plain.py").write_text("x = '" + "gh" + "p_" + "B" * 24 + "'\n")
        sh(src, "commit", "-qam", "leak in an updated file")
        if not refused(write=True):
            problems.append("leak in an updated file not refused")
        (src / "plain.py").write_text("x = 2\n")
        sh(src, "commit", "-qam", "unleak update")
        (src / "intent" / "j.md").write_text("plain secret-" + "name outside a redaction\n")
        (src / "notes.txt").write_text("secret-" + "name\n")
        sh(src, "add", "-A")
        sh(src, "commit", "-qm", "internal name")
        if not refused(write=True):
            problems.append("internal name outside a redaction not refused")
        sh(src, "rm", "-q", "notes.txt")
        sh(src, "commit", "-qm", "drop")
        (dst / "docs" / "b").mkdir()
        (dst / "docs" / "b" / "local.tmp").write_text("ignored, not the sync's to delete\n")
        with open(dst / ".git" / "info" / "exclude", "a") as f:
            f.write("local.tmp\n")
        (src / "docs" / "b").write_text("a file where the public tree has a directory\n")
        sh(src, "add", "-A")
        sh(src, "commit", "-qm", "file over a kept directory")
        if not refused(write=True) or not (dst / "docs" / "b" / "local.tmp").exists() \
                or git(dst, "status", "--porcelain").strip():
            problems.append("directory holding a kept file replaced, or a refused write changed the tree")
        sh(src, "rm", "-q", "docs/b")
        sh(src, "commit", "-qm", "undo")
        shutil.rmtree(dst / "docs" / "b")
        sh(dst, "checkout", "-q", "-b", "behind", "main~1")
        if not refused(write=True):
            problems.append("branch that does not contain public main not refused")
        sh(dst, "checkout", "-q", "sync3")
        if not refused(reviewed=["plain.py"]):
            problems.append("--reviewed accepted a synced file")
        sh(dst, "checkout", "-q", "main")
        if not refused(reviewed=["CLAUDE.md"]):
            problems.append("--reviewed on main not refused")
        sh(dst, "checkout", "-q", "sync3")
        (dst / "rores").rename(dst / "rores-real")
        os.symlink(dst / "rores-real", dst / "rores")
        sh(dst, "add", "-A")
        sh(dst, "commit", "-qm", "link")
        if not refused(write=True):
            problems.append("symlinked directory written through")
        try:
            tree(dst, "HEAD")
            problems.append("symlink in a tree not refused")
        except Refused:
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if problems:
        for p in problems:
            print("FAIL:", p)
        return 1
    print("PASS: sync-public self-test (refs not trees, rewrite scope, redaction, modes, delete, public-only review, "
          "leak, dirty, main, detached, behind, symlink, submodule, fetch failure, directory to file, review order)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--reviewed", nargs="+", metavar="FILE")
    ap.add_argument("--target", help="public repo path (default: public-sync.json 'target')")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    try:
        return run(ROOT, a.target, write=a.write, reviewed=a.reviewed)
    except Refused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # anything unexpected is a failure, never "out of step"
        print(f"FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
