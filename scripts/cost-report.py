#!/usr/bin/env python3
"""What each agent role, ticket, model, day or project costs, from Claude Code's own transcripts.

Reads ~/.claude/projects/<project-dir>/<session>.jsonl (role `main`) and
<project-dir>/<session>/subagents/agent-<id>.jsonl (role from agent-<id>.meta.json).
Each API response is counted once (message.id, else requestId). Prices come from
scripts/model-prices.json; a model with no price shows `?` and is never guessed.

  python3 scripts/cost-report.py [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--project P]
      [--ticket KEY-N] [--by role|ticket|model|day|project ...] [--json] [--root DIR]
  python3 scripts/cost-report.py --self-test
"""
import argparse, glob, json, os, re, subprocess, sys, tempfile
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
PRICES = os.path.join(HERE, "model-prices.json")
BY = ("role", "ticket", "model", "day", "project")
TOKENS = ("input", "cache_write", "cache_read", "output")
BRANCH_RE = re.compile(r"^([a-z]+)-(\d+)\b")
DESC_RE = re.compile(r"\b([A-Z]{2,6}-\d+)\b")


def load_prices(path=PRICES):
    try:
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        return p["models"], float(p["cache_write_5m"]), float(p["cache_write_1h"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        sys.exit(f"{path}: bad price file ({e})")


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def cost_of(u, price, m5, m1):
    """USD for one usage block, or None when the model has no price."""
    if not price:
        return None
    return (u["input"] * price["input"] + u["output"] * price["output"] + u["cache_read"] * price["cache_read"]
            + u["cw5"] * price["input"] * m5 + u["cw1"] * price["input"] * m1) / 1e6


def usage_of(raw):
    cc = raw.get("cache_creation") if isinstance(raw.get("cache_creation"), dict) else {}
    cw5, cw1 = num(cc.get("ephemeral_5m_input_tokens")), num(cc.get("ephemeral_1h_input_tokens"))
    total = num(raw.get("cache_creation_input_tokens"))
    if cw5 + cw1 < total:  # no (or partial) breakdown: the rest is priced as a 5 minute write
        cw5 += total - cw5 - cw1
    return {"input": num(raw.get("input_tokens")), "output": num(raw.get("output_tokens")),
            "cache_read": num(raw.get("cache_read_input_tokens")), "cw5": cw5, "cw1": cw1}


def ticket_of(branch, desc):
    m = BRANCH_RE.match(branch or "")
    if m:
        return f"{m.group(1).upper()}-{m.group(2)}"
    found = DESC_RE.findall(desc or "")
    return found[-1] if found else "-"


def transcripts(root):
    """(path, project dir name, role, meta description) for every main session and subagent file."""
    for path in sorted(glob.glob(os.path.join(root, "*", "*.jsonl"))):
        yield path, os.path.basename(os.path.dirname(path)), "main", None
    for path in sorted(glob.glob(os.path.join(root, "*", "*", "subagents", "agent-*.jsonl"))):
        role, desc = "unknown", None
        try:
            with open(path[:-len(".jsonl")] + ".meta.json", encoding="utf-8") as f:
                meta = json.load(f)
            role = meta.get("agentType") or "unknown"
            desc = meta.get("description")
        except (OSError, ValueError, AttributeError):
            pass
        yield path, os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(path)))), role, desc


def collect(root, prices, m5, m1):
    """One record per API response, deduplicated across all files."""
    seen, out = {}, []
    for path, pdir, role, desc in transcripts(root):
        try:
            lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("type") != "assistant" or not isinstance(d.get("message"), dict):
                continue
            msg = d["message"]
            if not isinstance(msg.get("usage"), dict) or msg.get("model") in (None, "<synthetic>"):
                continue
            key = msg.get("id") or d.get("requestId")
            u = usage_of(msg["usage"])
            if key and key in seen:  # another content block of the same response
                old = out[seen[key]]
                if u["output"] > old["u"]["output"]:  # a streaming line that ended later
                    old["u"], old["cost"] = u, cost_of(u, prices.get(msg["model"]), m5, m1)
                continue
            ts = str(d.get("timestamp") or "")
            cwd = d.get("cwd")
            rec = {"role": role, "model": msg["model"], "day": ts[:10] or "?",
                   "ticket": ticket_of(d.get("gitBranch"), desc if role != "main" else None),
                   "project": os.path.basename(str(cwd).rstrip("/")) if cwd else pdir,
                   "u": u, "cost": cost_of(u, prices.get(msg["model"]), m5, m1)}
            if key:
                seen[key] = len(out)
            out.append(rec)
    return out


def keep(r, a):
    if r["day"] == "?" and (a.since or a.until):  # no timestamp: cannot be placed in a date range
        return False
    if a.since and r["day"] < a.since.isoformat() or a.until and r["day"] > a.until.isoformat():
        return False
    return (not a.project or r["project"] == a.project) and (not a.ticket or r["ticket"] == a.ticket.upper())


def new_group():
    return {"responses": 0, "input": 0, "cache_write": 0, "cache_read": 0, "output": 0, "usd": 0.0, "unpriced": 0}


def add(g, r):
    u = r["u"]
    g["responses"] += 1
    g["input"] += u["input"]
    g["cache_write"] += u["cw5"] + u["cw1"]
    g["cache_read"] += u["cache_read"]
    g["output"] += u["output"]
    if r["cost"] is None:
        g["unpriced"] += 1
    else:
        g["usd"] += r["cost"]


def report(records, by):
    groups, total, unattr = {}, new_group(), new_group()
    for r in records:
        add(groups.setdefault(tuple(r[k] for k in by), new_group()), r)
        add(total, r)
        if r["ticket"] == "-":
            add(unattr, r)
    rows = [{"keys": dict(zip(by, k)), **g} for k, g in groups.items()]
    rows.sort(key=lambda g: (-g["usd"], tuple(g["keys"].values())))
    for g in rows + [total, unattr]:
        if g["responses"] and g["unpriced"] == g["responses"]:
            g["usd"] = None  # nothing in the group has a price
    return {"by": list(by), "groups": rows, "total": total, "unattributed": unattr}


def usd(g):
    if g["unpriced"] and g["unpriced"] == g["responses"]:
        return "?"
    return f"{g['usd']:.2f}" + ("+?" if g["unpriced"] else "")


def text(rep):
    by = rep["by"]
    widths = [max([len(k)] + [len(str(g["keys"][k])) for g in rep["groups"]]) for k in by]
    head = [f"{k:<{w}}" for k, w in zip(by, widths)] + [f"{h:>11}" for h in ("responses", "input", "cache write", "cache read", "output")] + [f"{'USD':>10}"]
    lines = ["  ".join(head)]

    def row(label, g):
        return "  ".join([label] + [f"{g[k]:>11,}" for k in ("responses",) + TOKENS] + [f"{usd(g):>10}"])
    for g in rep["groups"]:
        lines.append(row("  ".join(f"{str(g['keys'][k]):<{w}}" for k, w in zip(by, widths)), g))
    t, un = rep["total"], rep["unattributed"]
    lines.append(row("  ".join(["total".ljust(sum(widths) + 2 * (len(by) - 1))]), t))
    if t["unpriced"]:
        lines.append(f"{t['unpriced']} of {t['responses']} responses had no price (model not in model-prices.json); "
                     f"their tokens count, their cost is not in USD.")
    if t["responses"]:
        lines.append(f"Unattributed (no ticket): {un['responses']} of {t['responses']} responses "
                     f"({100 * un['responses'] / t['responses']:.0f}%)"
                     + (f", {100 * (un['usd'] or 0) / t['usd']:.0f}% of the priced USD" if t["usd"] else ""))
    else:
        lines.append("no responses")
    return "\n".join(lines)


def run(root, a):
    prices, m5, m1 = load_prices()
    recs = collect(root, prices, m5, m1)
    dated = bool(a.since or a.until)
    rep = report([r for r in recs if keep(r, a)], a.by or ["role"])
    rep["no_timestamp"] = sum(1 for r in recs if r["day"] == "?") if dated else 0
    return rep


# ---------------------------------------------------------------- self-test

def _line(mid, model, branch, ts, rid=None, cwd="/w/repoA", usage=None, **extra):
    d = {"type": "assistant", "timestamp": ts, "requestId": rid or ("req_" + str(mid)),
         "message": {"id": mid, "model": model, "usage": usage if usage is not None else {}}}
    if branch is not None:
        d["gitBranch"] = branch
    if cwd is not None:
        d["cwd"] = cwd
    d.update(extra)
    return json.dumps(d)


def _write(path, lines, meta=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    if meta is not None:
        with open(path[:-len(".jsonl")] + ".meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f)


def self_test():
    close = lambda x, y: abs(x - y) < 1e-12
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "projects")
        ua = _line("m1", "claude-opus-5-5", "aps-62-slim-context", "2026-11-10T10:00:00Z", usage={
            "input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 2000,
            "cache_creation_input_tokens": 4000,
            "cache_creation": {"ephemeral_5m_input_tokens": 3000, "ephemeral_1h_input_tokens": 1000}})
        # no message.id: requestId is the key
        ub = json.loads(_line("x", "claude-sonnet-5-5", "main", "2026-11-11T09:00:00Z", rid="r2",
                              usage={"input_tokens": 100, "output_tokens": 100}))
        del ub["message"]["id"]
        ub = json.dumps(ub)
        main = [ua, ua, "this is not json", "{broken",
                _line("syn", "<synthetic>", "aps-62-x", "2026-11-10T10:01:00Z", usage={"input_tokens": 9, "output_tokens": 9}),
                json.dumps({"type": "assistant", "message": {"id": "nou", "model": "claude-opus-5-5"}}),
                json.dumps({"type": "user", "message": {"content": "hi"}}),
                ub, ub,
                _line("m3", "claude-mystery-9", "aps-62-slim-context", "2026-11-10T11:00:00Z",
                      usage={"input_tokens": 10, "output_tokens": 10})]
        _write(os.path.join(root, "-w-repoA", "S1.jsonl"), main)
        sub = os.path.join(root, "-w-repoA", "S1", "subagents")
        _write(os.path.join(sub, "agent-a.jsonl"), [
            _line("a1", "claude-opus-5-5", "main", "2026-11-10T12:00:00Z",
                  usage={"input_tokens": 200, "output_tokens": 100, "cache_read_input_tokens": 1000}),
            _line("a2", "claude-haiku-5-5", "aps-61-x", "2026-11-11T12:00:00Z",
                  usage={"input_tokens": 1000, "output_tokens": 1000, "cache_read_input_tokens": 10000})],
            {"agentType": "reviewer", "description": "Review (APS-59) then re-review (APS-60)"})
        _write(os.path.join(sub, "agent-b.jsonl"), [
            _line("b1", "claude-sonnet-5-5", "main", "2026-11-11T13:00:00Z", cwd=None,
                  usage={"input_tokens": 50, "output_tokens": 50, "cache_creation_input_tokens": 100})])
        _write(os.path.join(sub, "agent-c.jsonl"), [
            _line("c1", "claude-sonnet-5-5", None, "2026-11-11T14:00:00Z",
                  usage={"input_tokens": 10, "output_tokens": 10})],
            {"agentType": "builder", "description": "no ticket here"})

        prices, m5, m1 = load_prices()
        recs = collect(root, prices, m5, m1)
        n = len(recs)
        assert n == 7, f"expected 7 responses (deduped), got {n}"
        exp = {"m1": 0.0374, "r2": 0.0012, "a1": 0.003, "a2": 0.0007, "b1": 0.00085, "c1": 0.00012}
        assert close(sum(r["cost"] for r in recs if r["cost"] is not None), sum(exp.values())), "priced total (the unpriced model m3 is left out)"

        class A:
            since = until = project = ticket = None
            by = None
        a = A()
        r = report(recs, ["role"])
        g = {x["keys"]["role"]: x for x in r["groups"]}
        assert set(g) == {"main", "reviewer", "unknown", "builder"}, set(g)
        assert g["main"]["responses"] == 3 and g["main"]["unpriced"] == 1, g["main"]
        assert close(g["main"]["usd"], 0.0374 + 0.0012), g["main"]
        assert g["main"]["input"] == 1000 + 100 + 10 and g["main"]["cache_write"] == 4000 and g["main"]["cache_read"] == 2000 and g["main"]["output"] == 500 + 100 + 10
        assert g["reviewer"]["responses"] == 2 and close(g["reviewer"]["usd"], 0.0037), g["reviewer"]
        assert g["reviewer"]["cache_read"] == 11000
        assert close(g["unknown"]["usd"], 0.00085) and g["unknown"]["cache_write"] == 100, g["unknown"]
        assert close(g["builder"]["usd"], 0.00012)
        assert [x["keys"]["role"] for x in r["groups"]] == ["main", "reviewer", "unknown", "builder"], "sorted by USD descending"
        assert r["total"]["responses"] == 7 and r["total"]["unpriced"] == 1
        assert close(r["total"]["usd"], sum(exp.values()))
        # tickets: branch wins, then the last ticket of the meta description, else unattributed
        t = {x["keys"]["ticket"]: x for x in report(recs, ["ticket"])["groups"]}
        assert set(t) == {"APS-62", "APS-61", "APS-60", "-"}, set(t)
        assert t["APS-62"]["responses"] == 2 and t["APS-60"]["responses"] == 1 and t["APS-61"]["responses"] == 1
        assert t["-"]["responses"] == 3 and close(t["-"]["usd"], 0.0012 + 0.00085 + 0.00012), t["-"]
        assert report(recs, ["ticket"])["unattributed"]["responses"] == 3
        # model, day, project
        m = {x["keys"]["model"]: x for x in report(recs, ["model"])["groups"]}
        assert m["claude-mystery-9"]["unpriced"] == 1 and m["claude-mystery-9"]["output"] == 10 and usd(m["claude-mystery-9"]) == "?"
        assert "<synthetic>" not in m
        d = {x["keys"]["day"]: x["responses"] for x in report(recs, ["day"])["groups"]}
        assert d == {"2026-11-10": 3, "2026-11-11": 4}, d
        p = {x["keys"]["project"]: x["responses"] for x in report(recs, ["project"])["groups"]}
        assert p == {"repoA": 6, "-w-repoA": 1}, p  # no cwd: the project dir name
        # nested grouping and filters
        nest = report(recs, ["ticket", "role"])
        assert any(x["keys"] == {"ticket": "APS-62", "role": "main"} and x["responses"] == 2 for x in nest["groups"])
        a.since = date(2026, 11, 11)
        assert len([x for x in recs if keep(x, a)]) == 4
        a.since, a.until = None, date(2026, 11, 10)
        assert len([x for x in recs if keep(x, a)]) == 3
        a.until, a.ticket = None, "aps-60"
        assert [x["role"] for x in recs if keep(x, a)] == ["reviewer"]
        a.ticket, a.project = None, "repoA"
        assert len([x for x in recs if keep(x, a)]) == 6
        out = text(report(recs, ["role"]))
        assert "1 of 7 responses had no price" in out and "Unattributed (no ticket): 3 of 7" in out and "3+?" not in out, out
        assert "0.04+?" in out, out
        # JSON: a group with no priced response has usd null, and keeps its unpriced count
        mj = {x["keys"]["model"]: x for x in report(recs, ["model"])["groups"]}["claude-mystery-9"]
        assert mj["usd"] is None and mj["unpriced"] == 1, mj
        assert json.loads(json.dumps(mj))["usd"] is None
        assert report(recs, ["role"])["total"]["usd"] is not None
        # one response on several lines: the line with the full usage counts, in any order
        root2 = os.path.join(tmp, "projects2")
        full = {"input_tokens": 100, "output_tokens": 400, "cache_read_input_tokens": 1000}
        dl = [_line("d1", "claude-opus-5-5", "aps-70-x", "2026-11-11T01:00:00Z", usage={"input_tokens": 0, "output_tokens": 0}),
              _line("d1", "claude-opus-5-5", "aps-70-x", "2026-11-11T01:00:01Z", usage=full),
              _line("d2", "claude-opus-5-5", "aps-70-x", "2026-11-11T02:00:00Z", usage={"input_tokens": 100, "output_tokens": 5, "cache_read_input_tokens": 1000}),
              _line("d2", "claude-opus-5-5", "aps-70-x", "2026-11-11T02:00:01Z", usage=full),
              _line("d3", "claude-opus-5-5", "aps-70-x", "2026-11-11T03:00:00Z", usage=full),
              _line("d3", "claude-opus-5-5", "aps-70-x", "2026-11-11T03:00:01Z", usage={"input_tokens": 100, "output_tokens": 5}),
              _line("nt", "claude-opus-5-5", "aps-70-x", None, usage=full)]
        dl[-1] = json.dumps({k: v for k, v in json.loads(dl[-1]).items() if k != "timestamp"})
        _write(os.path.join(root2, "-w-repoB", "S2.jsonl"), dl)
        r2 = collect(root2, prices, m5, m1)
        assert len(r2) == 4, len(r2)
        one = (100 * 4 + 400 * 20 + 1000 * 0.2) / 1e6
        assert all(close(x["cost"], one) and x["u"]["output"] == 400 for x in r2), [x["u"] for x in r2]
        assert close(report(r2, ["role"])["total"]["usd"], 4 * one)
        class B:
            since, until, project, ticket, by = date(2026, 11, 11), None, None, None, None
        assert len([x for x in r2 if keep(x, B)]) == 3
        B.since, B.until = None, date(2026, 11, 12)
        assert len([x for x in r2 if keep(x, B)]) == 3
        B.since, B.until = None, None
        assert len([x for x in r2 if keep(x, B)]) == 4
        B.since = date(2026, 11, 11)
        rb = run(root2, B)
        assert rb["total"]["responses"] == 3 and rb["no_timestamp"] == 1, rb
        B.since = None
        assert run(root2, B)["no_timestamp"] == 0
        # the command line, with the real home untouched
        env = dict(os.environ, HOME=os.path.join(tmp, "nohome"), USERPROFILE=os.path.join(tmp, "nohome"))
        run_ = subprocess.run([sys.executable, os.path.abspath(__file__), "--root", root, "--by", "ticket", "role", "--json"],
                              capture_output=True, text=True, env=env)
        assert run_.returncode == 0, run_.stderr
        j = json.loads(run_.stdout)
        assert j["by"] == ["ticket", "role"] and j["total"]["responses"] == 7 and close(j["total"]["usd"], sum(exp.values()))
        run_ = subprocess.run([sys.executable, os.path.abspath(__file__), "--root", root2, "--since", "2026-11-11"],
                              capture_output=True, text=True, env=env)
        assert run_.returncode == 0 and "1 responses without a timestamp left out" in run_.stdout, run_.stdout + run_.stderr
        run_ = subprocess.run([sys.executable, os.path.abspath(__file__), "--root", os.path.join(tmp, "none")],
                              capture_output=True, text=True, env=env)
        assert run_.returncode == 0 and "no responses" in run_.stdout, run_.stdout + run_.stderr
    print("cost-report self-test: ok")


def main():
    ap = argparse.ArgumentParser(description="Cost of agent roles, tickets, models, days and projects from Claude Code transcripts.")
    ap.add_argument("--since", type=date.fromisoformat, help="YYYY-MM-DD (UTC, inclusive)")
    ap.add_argument("--until", type=date.fromisoformat, help="YYYY-MM-DD (UTC, inclusive)")
    ap.add_argument("--project", help="cwd basename of the line")
    ap.add_argument("--ticket", help="KEY-N")
    ap.add_argument("--by", nargs="+", choices=BY, help="grouping, default role; several give a nested grouping")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        try:
            self_test()
        except AssertionError as e:
            sys.exit(f"cost-report self-test FAILED: {e}")
        return
    rep = run(a.root, a)
    print(json.dumps(rep, indent=2) if a.json else text(rep)
          + (f"\n{rep['no_timestamp']} responses without a timestamp left out" if rep["no_timestamp"] else ""))


if __name__ == "__main__":
    main()
