#!/usr/bin/env python3
"""Summarise owner interventions from ~/.claude/hil/log.jsonl.

One JSON line per intervention: ts (UTC, ISO), project, task, kind, trigger,
note, and optional minutes (owner's own estimate). Without minutes, time is
estimated from bursts: entries less than GAP minutes apart form one sitting,
counted as its span plus PAD minutes. The per-day rate uses at least one day.

  python scripts/hil-report.py [--log PATH] [--since YYYY-MM-DD] [--project P]
"""
import argparse, json, os, sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone

KINDS_BY_DESIGN = {"decision", "approval", "merge", "direction"}
KINDS_TO_REDUCE = {"setup", "incident", "unblock", "status"}
GAP, PAD = 20, 3


def load(path, since, project):
    if not os.path.exists(path):
        sys.exit(f"{path}: no log yet")
    rows = []
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            t = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
            r["_t"] = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
            if "minutes" in r and (isinstance(r["minutes"], bool) or not isinstance(r["minutes"], (int, float))):
                raise ValueError("minutes is not a number")
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            sys.exit(f"{path}:{n}: bad line ({e})")
        kind = r.setdefault("kind", "?")
        if kind not in KINDS_BY_DESIGN | KINDS_TO_REDUCE:
            print(f"warning: {path}:{n}: unknown kind {kind!r}", file=sys.stderr)
        if since and r["_t"].date() < since:
            continue
        if project and r.get("project") != project:
            continue
        rows.append(r)
    return sorted(rows, key=lambda r: r["_t"])


def sittings(rows):
    out, cur = [], []
    for r in rows:
        if cur and r["_t"] - cur[-1]["_t"] > timedelta(minutes=GAP):
            out.append(cur)
            cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=os.path.expanduser("~/.claude/hil/log.jsonl"))
    ap.add_argument("--since", type=date.fromisoformat, help="YYYY-MM-DD")
    ap.add_argument("--project")
    a = ap.parse_args()
    rows = load(a.log, a.since, a.project)
    if not rows:
        sys.exit("no entries")

    days = max((rows[-1]["_t"] - rows[0]["_t"]).total_seconds() / 86400, 1)
    ss = sittings(rows)
    est = sum((s[-1]["_t"] - s[0]["_t"]).total_seconds() / 60 + PAD for s in ss)
    owned = sum(r["minutes"] for r in rows if "minutes" in r)

    print(f"Entries {len(rows)} over {days:.1f} days ({len(rows)/days:.1f}/day), "
          f"{rows[0]['ts']} .. {rows[-1]['ts']}")
    print(f"Sittings {len(ss)} (gap > {GAP} min), estimated owner time {est:.0f} min"
          + (f"; owner-stated minutes {owned}" if owned else ""))
    by_design = sum(1 for r in rows if r["kind"] in KINDS_BY_DESIGN)
    to_reduce = sum(1 for r in rows if r["kind"] in KINDS_TO_REDUCE)
    print(f"By design (decision/approval/merge/direction): {by_design}; "
          f"to reduce (setup/incident/unblock/status): {to_reduce}"
          + (f"; unknown kind: {len(rows) - by_design - to_reduce}" if len(rows) > by_design + to_reduce else ""))
    for title, key in (("kind", "kind"), ("trigger", "trigger"), ("project", "project")):
        c = Counter(r.get(key, "?") for r in rows)
        print(f"\nBy {title}:")
        for k, v in c.most_common():
            print(f"  {k:<12} {v:>4}")
    print("\nPer day:")
    for d, v in sorted(Counter(r["_t"].date().isoformat() for r in rows).items()):
        print(f"  {d}  {v}")
    inc = [r for r in rows if r["kind"] == "incident" and r.get("trigger") == "owner"]
    if inc:
        print("\nIncidents the owner noticed first:")
        for r in inc:
            print(f"  {r['ts']}  {r.get('task','')}: {r.get('note','')}")


if __name__ == "__main__":
    main()
