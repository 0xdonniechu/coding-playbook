#!/usr/bin/env python3
"""Plane tickets over REST, for the main session (the only role that updates the tracker). Standard library only.

  python scripts/plane.py projects                              identifier and name of each project
  python scripts/plane.py show <KEY-N>                          name, state, labels, links of one ticket
  python scripts/plane.py create <KEY> --name <title> [--state <state>] [--label <label>]... [--body <text> | --body-file <f>]
                                                                new ticket; prints its <KEY-N>
  python scripts/plane.py state <KEY-N> <state>                 move a ticket (state name, any case: Todo, In Progress, Done, ...)
  python scripts/plane.py comment <KEY-N> (--body <text> | --body-file <f>)
  python scripts/plane.py link <KEY-N> <url> [--title <title>]  attach a link (a PR, an issue)
  python scripts/plane.py --self-test                           run the tests against a local fake Plane; exit 0 = PASS

Settings are read at run time: PLANE_BASE_URL, PLANE_WORKSPACE_SLUG and PLANE_API_KEY from the environment when all
three are set, otherwise from the `plane` MCP server's env in ~/.claude.json (top-level mcpServers, then the home
folder's project entry), trimmed of line ends. The key is sent only in the X-API-Key header, only over https (plain
http only to localhost), never after a redirect (refused), and never printed; a setting with a control character inside
is refused. A body is plain text, sent as
HTML paragraphs. Exit 0 done, 1 Plane refused or not found, 2 usage or settings missing.
Never put the Plane host, workspace or ids on GitHub: name the ticket only ("Plane: APS-36").
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "coding-playbook-plane/1"  # Python's default User-Agent gets HTTP 403
TICKET = re.compile(r"^([A-Za-z][A-Za-z0-9]*)-(\d+)$")


class Stop(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def get(mapping, *keys):
    """mapping[k1][k2]…, or None when any level is missing or not an object."""
    for key in keys:
        if not isinstance(mapping, dict):
            return None
        mapping = mapping.get(key)
    return mapping


def checked(base, slug, key):
    """Trims the line ends a file or a paste leaves; refuses a control character (it would reach an error message
    that quotes the header) and a base URL that would send the key in clear text or to a path, without printing either."""
    base, slug, key = base.strip(), slug.strip(), key.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in key + slug + base):
        raise Stop(2, "a Plane setting holds a control character (a line break inside the key?); fix it in its source")
    host = urllib.parse.urlsplit(base)
    local = host.hostname in ("127.0.0.1", "localhost", "::1")
    if host.scheme != "https" and not (host.scheme == "http" and local) or not host.hostname:
        raise Stop(2, "PLANE_BASE_URL must be an https:// URL (plain http only for localhost)")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", slug):
        raise Stop(2, "PLANE_WORKSPACE_SLUG must be letters, digits, '-' or '_'")
    return base, slug, key


def settings():
    names = ("PLANE_BASE_URL", "PLANE_WORKSPACE_SLUG", "PLANE_API_KEY")
    if all(os.environ.get(n) for n in names):
        return checked(*(os.environ[n] for n in names))
    try:
        data = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    for env in (get(data, "mcpServers", "plane", "env"), get(data, "projects", str(Path.home()), "mcpServers", "plane", "env")):
        if isinstance(env, dict) and all(isinstance(env.get(n), str) and env.get(n).strip() for n in names):
            return checked(*(env[n] for n in names))
    raise Stop(2, "Plane settings not found: set PLANE_BASE_URL, PLANE_WORKSPACE_SLUG and PLANE_API_KEY, "
                  "or configure the plane MCP server in ~/.claude.json")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the X-API-Key header to whatever host it names: refuse every one."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Stop(1, f"Plane answered with a redirect (HTTP {code}); not followed, so the key is not sent elsewhere")


OPENER = urllib.request.build_opener(NoRedirect)


class Plane:
    def __init__(self):
        base, self.slug, self._key = settings()
        self.root = f"{base.rstrip('/')}/api/v1/workspaces/{self.slug}/"

    def call(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.root + path, data=data, method=method, headers={
            "X-API-Key": self._key, "User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with OPENER.open(request, timeout=30) as response:
                text = response.read().decode("utf-8")
            return json.loads(text) if text.strip() else {}
        except Stop:
            raise
        except urllib.error.HTTPError as error:
            raise Stop(1, f"Plane answered HTTP {error.code} to {method} {path}") from None
        except Exception as error:  # only the type: a message could quote the request and its header
            raise Stop(1, f"Plane call failed ({type(error).__name__}) for {method} {path}") from None

    def all(self, path):
        """Every item of a list endpoint, following next_cursor."""
        items, cursor = [], None
        for _ in range(100):  # 100 pages; more is reported, not hidden
            page = self.call("GET", path + (f"?cursor={cursor}" if cursor else ""))
            if isinstance(page, list):
                return page
            items += page.get("results", [])
            if not page.get("next_page_results") or not page.get("next_cursor"):
                return items
            cursor = page["next_cursor"]
        print(f"plane.py: {path} has more than 100 pages; only the first 100 were read", file=sys.stderr)
        return items

    def project(self, identifier):
        for project in self.all("projects/"):
            if str(project.get("identifier", "")).upper() == identifier.upper():
                return project
        raise Stop(1, f"no Plane project with identifier {identifier}")

    def ticket(self, ref):
        match = TICKET.match(ref)
        if not match:
            raise Stop(2, f"not a ticket reference: {ref!r} (expected KEY-N, for example APS-36)")
        project = self.project(match.group(1))
        issue = self.call("GET", f"work-items/{match.group(1).upper()}-{match.group(2)}/")
        return project, issue

    def state(self, project, name):
        """(id, Plane's own name) of a state, matched without regard to case."""
        states = self.all(f"projects/{project['id']}/states/")
        for state in states:
            if str(state.get("name", "")).lower() == name.lower():
                return state["id"], state.get("name")
        raise Stop(2, f"no state {name!r} in {project['identifier']}; states: {', '.join(s.get('name', '?') for s in states)}")

    def label_ids(self, project, names):
        labels = self.all(f"projects/{project['id']}/labels/")
        found = []
        for name in names:
            match = [l["id"] for l in labels if str(l.get("name", "")).lower() == name.lower()]
            if not match:
                raise Stop(2, f"no label {name!r} in {project['identifier']}; labels: {', '.join(l.get('name', '?') for l in labels)}")
            found.append(match[0])
        return found


def as_html(text):
    return "".join(f"<p>{html.escape(part).replace(chr(10), '<br>')}</p>" for part in text.strip().split("\n\n") if part.strip())


def options(args, flags, repeat=()):
    """Splits args into positionals and {flag: value}; a flag in `repeat` collects a list."""
    positional, found, i = [], {f: [] for f in repeat}, 0
    while i < len(args):
        arg = args[i]
        if arg in flags or arg in repeat:
            if i + 1 >= len(args):
                raise Stop(2, f"{arg} needs a value")
            if arg in repeat:
                found[arg].append(args[i + 1])
            else:
                found[arg] = args[i + 1]
            i += 2
        elif arg.startswith("--"):
            raise Stop(2, f"unknown option {arg}")
        else:
            positional.append(arg)
            i += 1
    return positional, found


def body_of(found, required):
    if "--body" in found and "--body-file" in found:
        raise Stop(2, "give --body or --body-file, not both")
    if "--body-file" in found:
        try:
            return Path(found["--body-file"]).read_text(encoding="utf-8")
        except OSError as error:
            raise Stop(2, f"cannot read {found['--body-file']}: {error.strerror}") from None
    if "--body" in found:
        return found["--body"]
    if required:
        raise Stop(2, "a body is required: --body <text> or --body-file <file>")
    return None


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    command, rest = argv[0], argv[1:]
    if command == "projects":
        if rest:
            raise Stop(2, "projects takes no argument")
        for project in Plane().all("projects/"):
            print(f"{project.get('identifier')}\t{project.get('name')}")
        return 0
    if command == "show":
        if len(rest) != 1:
            raise Stop(2, "usage: show <KEY-N>")
        plane = Plane()
        project, issue = plane.ticket(rest[0])
        states = {s["id"]: s.get("name") for s in plane.all(f"projects/{project['id']}/states/")}
        labels = {l["id"]: l.get("name") for l in plane.all(f"projects/{project['id']}/labels/")}
        links = plane.all(f"projects/{project['id']}/issues/{issue['id']}/links/")
        print(f"{project['identifier']}-{issue.get('sequence_id')}  {issue.get('name')}")
        print(f"state: {states.get(issue.get('state'), '(unknown)')}")  # never a raw id: ids must not reach GitHub
        print(f"labels: {', '.join(labels.get(l, '(unknown)') for l in issue.get('labels') or []) or '-'}")
        for link in links:
            print(f"link: {link.get('title') or ''} {link.get('url')}".replace(":  ", ": "))
        return 0
    if command == "create":
        positional, found = options(rest, {"--name", "--state", "--body", "--body-file"}, repeat=("--label",))
        if len(positional) != 1 or "--name" not in found:
            raise Stop(2, "usage: create <KEY> --name <title> [--state <state>] [--label <label>]... [--body <text> | --body-file <f>]")
        body = body_of(found, required=False)
        plane = Plane()
        project = plane.project(positional[0])
        payload = {"name": found["--name"]}
        if "--state" in found:
            payload["state"] = plane.state(project, found["--state"])[0]
        if found["--label"]:
            payload["labels"] = plane.label_ids(project, found["--label"])
        if body:
            payload["description_html"] = as_html(body)
        issue = plane.call("POST", f"projects/{project['id']}/issues/", payload)
        print(f"{project['identifier']}-{issue.get('sequence_id')}")
        return 0
    if command == "state":
        if len(rest) != 2:
            raise Stop(2, "usage: state <KEY-N> <state>")
        plane = Plane()
        project, issue = plane.ticket(rest[0])
        state_id, state_name = plane.state(project, rest[1])
        plane.call("PATCH", f"projects/{project['id']}/issues/{issue['id']}/", {"state": state_id})
        print(f"{rest[0].upper()} -> {state_name}")
        return 0
    if command == "comment":
        positional, found = options(rest, {"--body", "--body-file"})
        if len(positional) != 1:
            raise Stop(2, "usage: comment <KEY-N> (--body <text> | --body-file <f>)")
        body = body_of(found, required=True)
        plane = Plane()
        project, issue = plane.ticket(positional[0])
        plane.call("POST", f"projects/{project['id']}/issues/{issue['id']}/comments/", {"comment_html": as_html(body)})
        print(f"{positional[0].upper()} commented")
        return 0
    if command == "link":
        positional, found = options(rest, {"--title"})
        if len(positional) != 2 or not positional[1].startswith(("https://", "http://")):
            raise Stop(2, "usage: link <KEY-N> <url> [--title <title>]")
        plane = Plane()
        project, issue = plane.ticket(positional[0])
        payload = {"url": positional[1]}
        if "--title" in found:
            payload["title"] = found["--title"]
        plane.call("POST", f"projects/{project['id']}/issues/{issue['id']}/links/", payload)
        print(f"{positional[0].upper()} linked {positional[1]}")
        return 0
    raise Stop(2, f"unknown command {command!r}; run with --help")


def self_test():
    import subprocess
    import tempfile
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    key = "test-key-0123456789"
    seen, failures = [], []
    projects = {"results": [{"id": "p1", "identifier": "APS", "name": "Platform"}], "next_cursor": "c1", "next_page_results": True}
    projects2 = {"results": [{"id": "p2", "identifier": "SIC", "name": "Steady"}], "next_cursor": None, "next_page_results": False}
    states = {"results": [{"id": "s1", "name": "Todo"}, {"id": "s2", "name": "In Progress"}, {"id": "s3", "name": "Done"}]}
    labels = {"results": [{"id": "l1", "name": "docs"}]}

    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def answer(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def handle_any(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else None
            seen.append((self.command, self.path, self.headers.get("X-API-Key"), self.headers.get("User-Agent"), body))
            if "/workspaces/redirect/" in self.path:
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{server.server_address[1]}/elsewhere")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            if self.headers.get("X-API-Key") != key:
                return self.answer(401, {})
            p = self.path.split("/api/v1/workspaces/ws/", 1)[-1]
            routes = {
                ("GET", "projects/"): projects, ("GET", "projects/?cursor=c1"): projects2,
                ("GET", "work-items/APS-7/"): {"id": "i7", "sequence_id": 7, "name": "A ticket", "state": "s1", "labels": ["l1"]},
                ("GET", "projects/p1/states/"): states, ("GET", "projects/p1/labels/"): labels,
                ("GET", "projects/p1/issues/i7/links/"): {"results": [{"url": "https://example.com/pr/1", "title": "PR"}]},
                ("POST", "projects/p1/issues/"): {"id": "i8", "sequence_id": 8},
                ("PATCH", "projects/p1/issues/i7/"): {"id": "i7"},
                ("POST", "projects/p1/issues/i7/comments/"): {"id": "c"},
                ("POST", "projects/p1/issues/i7/links/"): {"id": "k"},
            }
            if (self.command, p) in routes:
                return self.answer(200, routes[(self.command, p)])
            return self.answer(404, {"detail": "not found"})

        do_GET = do_POST = do_PATCH = handle_any

    server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as home:
        base_env = {k: v for k, v in os.environ.items() if not k.startswith("PLANE_")} | {"HOME": home, "USERPROFILE": home}
        env = base_env | {"PLANE_BASE_URL": f"http://127.0.0.1:{server.server_address[1]}/",
                          "PLANE_WORKSPACE_SLUG": "ws", "PLANE_API_KEY": key}
        body_file = Path(home) / "body.txt"
        body_file.write_text("First <b>para</b>\n\nSecond", encoding="utf-8")

        secrets = [key, "wrong-key-5555", "line-break-key-7777"]

        def run(args, use_env=env):
            seen.clear()
            out = subprocess.run([sys.executable, __file__, *args], env=use_env, capture_output=True, text=True, timeout=60)
            if any(k in out.stdout + out.stderr for k in secrets) or "Traceback" in out.stderr:
                failures.append(f"{args}: a key or a traceback was printed")
            return out, list(seen)

        def expect(args, code, has=None, check=None, use_env=env):
            out, calls = run(args, use_env)
            if out.returncode != code:
                failures.append(f"{args}: exit {out.returncode}, expected {code}; {out.stdout.strip()} {out.stderr.strip()}")
            if has and has not in out.stdout + out.stderr:
                failures.append(f"{args}: output lacks {has!r}: {(out.stdout + out.stderr).strip()!r}")
            if any(c[3] != USER_AGENT for c in calls):
                failures.append(f"{args}: a request without the custom User-Agent")
            if check:
                problem = check(calls)
                if problem:
                    failures.append(f"{args}: {problem}")

        def sent(method, path_end, want):
            def check(calls):
                hits = [c for c in calls if c[0] == method and c[1].endswith(path_end)]
                if not hits:
                    return f"no {method} …{path_end}"
                if hits[-1][4] != want:
                    return f"{method} …{path_end} sent {hits[-1][4]!r}, expected {want!r}"
                return None
            return check

        def writes_nothing(calls):
            return f"wrote: {[c[:2] for c in calls if c[0] != 'GET']}" if any(c[0] != "GET" for c in calls) else None

        expect(["projects"], 0, has="SIC\tSteady")  # second page followed
        expect(["show", "APS-7"], 0, has="state: Todo")
        expect(["create", "APS", "--name", "New", "--state", "in progress", "--label", "docs", "--body-file", str(body_file)], 0,
               has="APS-8", check=sent("POST", "projects/p1/issues/", {
                   "name": "New", "state": "s2", "labels": ["l1"], "description_html": "<p>First &lt;b&gt;para&lt;/b&gt;</p><p>Second</p>"}))
        expect(["state", "aps-7", "done"], 0, has="APS-7 -> Done", check=sent("PATCH", "projects/p1/issues/i7/", {"state": "s3"}))
        expect(["state", "APS-7", "Shipped"], 2, has="states: Todo, In Progress, Done", check=writes_nothing)
        expect(["create", "APS", "--name", "x", "--label", "nope"], 2, has="no label", check=writes_nothing)
        expect(["comment", "APS-7", "--body", "PR opened"], 0, check=sent("POST", "comments/", {"comment_html": "<p>PR opened</p>"}))
        expect(["comment", "APS-7"], 2, has="body is required", check=writes_nothing)
        expect(["link", "APS-7", "https://example.com/pr/2", "--title", "PR 2"], 0,
               check=sent("POST", "i7/links/", {"url": "https://example.com/pr/2", "title": "PR 2"}))
        expect(["link", "APS-7", "not-a-url"], 2, check=writes_nothing)
        expect(["show", "APS-99"], 1, has="HTTP 404")
        expect(["show", "NOPE-1"], 1, has="no Plane project")
        expect(["show", "APS7"], 2, has="not a ticket reference")
        expect(["frobnicate"], 2, has="unknown command")
        expect(["create", "APS", "--name", "x", "--bogus", "y"], 2, has="unknown option", check=writes_nothing)
        expect(["projects"], 2, has="Plane settings not found", use_env=base_env)
        # settings from ~/.claude.json: the home folder's project entry, as on the owner's machine
        Path(home, ".claude.json").write_text(json.dumps({"projects": {str(Path(home)): {"mcpServers": {"plane": {"env": {
            "PLANE_BASE_URL": env["PLANE_BASE_URL"], "PLANE_WORKSPACE_SLUG": "ws", "PLANE_API_KEY": key}}}}}}), encoding="utf-8")
        expect(["projects"], 0, has="APS\tPlatform", use_env=base_env)
        Path(home, ".claude.json").write_text(json.dumps({"mcpServers": {"plane": {"env": {
            "PLANE_BASE_URL": env["PLANE_BASE_URL"], "PLANE_WORKSPACE_SLUG": "ws", "PLANE_API_KEY": "wrong-key-5555"}}}}), encoding="utf-8")
        expect(["projects"], 1, has="HTTP 401", use_env=base_env)
        # a key with a line break inside, or a CRLF file's trailing \r (trimmed, then works)
        expect(["projects"], 2, has="control character", use_env=env | {"PLANE_API_KEY": "line-break-key-7777\nx"})
        expect(["projects"], 0, has="APS\tPlatform", use_env=env | {"PLANE_API_KEY": key + "\r\n"})
        expect(["projects"], 2, has="https://", use_env=env | {"PLANE_BASE_URL": "http://plane.example.com/"})
        # odd shapes in ~/.claude.json: the settings message, never a crash
        for odd in ([], {"projects": {str(Path(home)): {"mcpServers": None}}}, {"mcpServers": {"plane": "x"}}):
            Path(home, ".claude.json").write_text(json.dumps(odd), encoding="utf-8")
            expect(["projects"], 2, has="Plane settings not found", use_env=base_env)
        # a redirect is refused, so the key never follows it
        redirect_env = env | {"PLANE_WORKSPACE_SLUG": "redirect"}
        expect(["projects"], 1, has="redirect", use_env=redirect_env,
               check=lambda calls: "the redirect was followed" if any("/elsewhere" in c[1] for c in calls) else None)
    server.shutdown()
    print("FAIL\n" + "\n".join(failures) if failures else "PASS: plane.py self-test")
    return 1 if failures else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    try:
        sys.exit(main(sys.argv[1:]))
    except Stop as stop:
        print(f"plane.py: {stop}", file=sys.stderr)
        sys.exit(stop.code)
    except Exception as error:  # no traceback: it could quote a setting
        print(f"plane.py: unexpected {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
