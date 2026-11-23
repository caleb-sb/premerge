#!/usr/bin/env python3
"""evie — preview your branch as a pull/merge request locally, and review it with an agent.

  evie                      open the review UI for the current branch (same as `evie serve`)
  evie comments             print open review comments as a prompt for an agent
  evie reply ID [--resolve] "text"   reply to a comment (as the agent by default)
  evie resolve ID / reopen ID
  evie describe [--title T] [--body-file F|-]   read or update the PR title/description draft
  evie pr [--draft]         push and create the PR (gh) / MR (glab) from the draft

Review state lives in <git-common-dir>/evie/<branch>.json — never committed.
Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import traceback
import webbrowser
from datetime import datetime, timezone
from functools import cached_property
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"
MAX_UNTRACKED = 200
FULL_CONTEXT = 1_000_000


class GitError(Exception):
    pass


class ApiError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


def run_git(cwd, *args, check=True, ok=(0,), stdin=None):
    p = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=cwd, capture_output=True, input=stdin.encode() if stdin is not None else None,
    )
    if check and p.returncode not in ok:
        msg = p.stderr.decode("utf-8", "replace").strip()
        raise GitError(msg or f"git {args[0]} exited with {p.returncode}")
    return p.stdout.decode("utf-8", "replace")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def literal(paths):
    return [f":(literal){p}" for p in paths]


# --------------------------------------------------------------------------- patch parsing

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")
_ESC = {"n": 10, "t": 9, '"': 34, "\\": 92, "a": 7, "b": 8, "f": 12, "r": 13, "v": 11}


def unquote_path(p: str) -> str:
    if not (len(p) >= 2 and p[0] == '"' and p[-1] == '"'):
        return p
    s, out, i = p[1:-1], bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt in _ESC:
                out.append(_ESC[nxt]); i += 2; continue
            if re.fullmatch(r"[0-7]{3}", s[i + 1:i + 4]):
                out.append(int(s[i + 1:i + 4], 8)); i += 4; continue
        out += c.encode(); i += 1
    return out.decode("utf-8", "replace")


def _side_path(raw: str):
    raw = raw.rstrip("\t\r")
    if raw == "/dev/null":
        return None
    p = unquote_path(raw)
    return p[2:] if p[:2] in ("a/", "b/") else p


def _git_header_paths(rest: str):
    if rest.startswith('"'):
        m = re.match(r'^("(?:[^"\\]|\\.)*")\s+(.*)$', rest)
        if m:
            return _side_path(m[1]), _side_path(m[2])
    half = (len(rest) - 1) // 2
    a, b = rest[:half], rest[half + 1:]
    if a[2:] == b[2:]:
        return _side_path(a), _side_path(b)
    m = re.match(r"^(a/.*?) (b/.*)$", rest)
    return (_side_path(m[1]), _side_path(m[2])) if m else (None, None)


def parse_patch(text: str) -> list[dict]:
    files: list[dict] = []
    f = hk = None
    rem_o = rem_n = o = n = 0

    def finish():
        if f is None:
            return
        f["hash"] = hashlib.sha1("\n".join(f.pop("_hdr")).encode()).hexdigest()[:12]
        if f["status"] == "added":
            f["oldPath"] = None
        elif f["status"] == "deleted":
            f["newPath"] = None
        f["path"] = f["newPath"] or f["oldPath"]

    for line in text.split("\n"):
        if hk is not None and (rem_o > 0 or rem_n > 0) and line[:1] in (" ", "-", "+", "\\", ""):
            tag, s = line[:1], line[1:]
            if tag == "\\":
                if hk["lines"]:
                    hk["lines"][-1]["noeol"] = True
            elif tag == "-":
                hk["lines"].append({"t": "-", "o": o, "n": None, "s": s})
                o += 1; rem_o -= 1; f["deletions"] += 1
            elif tag == "+":
                hk["lines"].append({"t": "+", "o": None, "n": n, "s": s})
                n += 1; rem_n -= 1; f["additions"] += 1
            else:
                hk["lines"].append({"t": " ", "o": o, "n": n, "s": s})
                o += 1; n += 1; rem_o -= 1; rem_n -= 1
            continue
        if line.startswith("\\") and hk is not None:
            if hk["lines"]:
                hk["lines"][-1]["noeol"] = True
            continue
        if line.startswith("diff --git "):
            finish()
            f = {"path": None, "oldPath": None, "newPath": None, "status": "modified", "binary": False,
                 "additions": 0, "deletions": 0, "hunks": [], "_hdr": [line]}
            f["oldPath"], f["newPath"] = _git_header_paths(line[11:])
            files.append(f)
            hk = None
            continue
        if f is None:
            continue
        if line.startswith("@@"):
            m = HUNK_RE.match(line)
            if not m:
                continue
            o, n = int(m[1]), int(m[3])
            rem_o = int(m[2]) if m[2] is not None else 1
            rem_n = int(m[4]) if m[4] is not None else 1
            hk = {"header": line, "lines": []}
            f["hunks"].append(hk)
            continue
        if hk is not None:
            continue
        f["_hdr"].append(line)
        if line.startswith("new file mode"):
            f["status"] = "added"
        elif line.startswith("deleted file mode"):
            f["status"] = "deleted"
        elif line.startswith("rename from "):
            f["oldPath"] = unquote_path(line[12:]); f["status"] = "renamed"
        elif line.startswith("rename to "):
            f["newPath"] = unquote_path(line[10:])
        elif line.startswith("copy from "):
            f["oldPath"] = unquote_path(line[10:]); f["status"] = "copied"
        elif line.startswith("copy to "):
            f["newPath"] = unquote_path(line[8:])
        elif line.startswith("similarity index "):
            with contextlib.suppress(ValueError):
                f["similarity"] = int(line[17:].rstrip("%"))
        elif line.startswith("old mode "):
            f["oldMode"] = line[9:]
        elif line.startswith("new mode "):
            f["newMode"] = line[9:]
        elif line.startswith("Binary files ") or line == "GIT binary patch":
            f["binary"] = True
        elif line.startswith("--- "):
            f["oldPath"] = _side_path(line[4:])
        elif line.startswith("+++ "):
            f["newPath"] = _side_path(line[4:])
    finish()
    return files


# --------------------------------------------------------------------------- repository

DIFF_OPTS = ["diff", "--no-color", "--no-ext-diff", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/"]

TEMPLATES = {
    "github": [".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md",
               "pull_request_template.md", "PULL_REQUEST_TEMPLATE.md",
               "docs/pull_request_template.md", "docs/PULL_REQUEST_TEMPLATE.md"],
    "gitlab": [".gitlab/merge_request_templates/Default.md", ".gitlab/merge_request_templates/default.md"],
}


class Repo:
    def __init__(self, path=".", base=None, remote=None, forge=None):
        try:
            self.root = run_git(path, "rev-parse", "--show-toplevel").strip()
        except (GitError, OSError):
            raise SystemExit(f"evie: {os.path.abspath(path)} is not inside a git work tree")
        self.common_dir = Path(run_git(self.root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
        self._remote, self._base, self._forge = remote, base, forge

    def git(self, *a, **k):
        return run_git(self.root, *a, **k)

    def _verify(self, ref):
        return bool(self.git("rev-parse", "--verify", "--quiet", ref + "^{commit}", check=False).strip())

    @cached_property
    def remote(self):
        if self._remote:
            return self._remote
        remotes = self.git("remote").split()
        if not remotes:
            return None
        up = self.git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False).strip()
        r = up.split("/", 1)[0] if "/" in up else ""
        if r in remotes:
            return r
        return "origin" if "origin" in remotes else remotes[0]

    @cached_property
    def base(self):
        if self._base:
            if not self._verify(self._base):
                raise GitError(f"base ref {self._base!r} not found")
            return self._base
        cands = []
        cfg = self.git("config", "--get", "evie.base", check=False).strip()
        if cfg:
            cands.append(cfg)
        if self.remote:
            sym = self.git("symbolic-ref", "--quiet", "--short", f"refs/remotes/{self.remote}/HEAD", check=False).strip()
            if sym:
                cands.append(sym)
            cands += [f"{self.remote}/main", f"{self.remote}/master"]
        cands += ["main", "master"]
        for c in cands:
            if self._verify(c):
                return c
        raise GitError(f"could not find a base branch (tried {', '.join(cands)}); pass --base")

    @property
    def target_branch(self):
        b = self.base
        if self.remote and b.startswith(self.remote + "/"):
            return b[len(self.remote) + 1:]
        return b

    def head(self):
        return self.git("rev-parse", "HEAD").strip()

    def branch(self):
        b = self.git("rev-parse", "--abbrev-ref", "HEAD").strip()
        return b if b != "HEAD" else "detached-" + self.head()[:8]

    def merge_base(self):
        mb = self.git("merge-base", self.base, "HEAD", check=False).strip()
        if not mb:
            raise GitError(f"{self.base} and HEAD have no common ancestor")
        return mb

    def untracked(self, paths=None):
        args = ["ls-files", "--others", "--exclude-standard", "-z"]
        if paths:
            args += ["--", *literal(paths)]
        return [p for p in self.git(*args).split("\0") if p][:MAX_UNTRACKED]

    def patch(self, mode, ctx=3, paths=None):
        args = [*DIFF_OPTS, "-M", f"-U{ctx}", self.merge_base()]
        if mode == "committed":
            args.append("HEAD")
        if paths:
            args += ["--", *literal(paths)]
        text = self.git(*args)
        if mode == "worktree":
            for p in self.untracked(paths):
                if text and not text.endswith("\n"):
                    text += "\n"
                text += self.git(*DIFF_OPTS, "--no-index", f"-U{ctx}", "--", "/dev/null", p, ok=(0, 1))
        return text

    def files(self, mode, ctx=3, paths=None):
        return parse_patch(self.patch(mode, ctx, paths))

    def commits(self):
        out = self.git("log", "--format=%H%x1f%h%x1f%an%x1f%aI%x1f%s%x1f%b%x1e", f"{self.merge_base()}..HEAD")
        res = []
        for rec in out.split("\x1e"):
            rec = rec.strip("\n")
            if not rec:
                continue
            sha, short, author, date, subject, body = (rec.split("\x1f") + [""] * 6)[:6]
            res.append({"sha": sha, "short": short, "author": author, "date": date,
                        "subject": subject, "body": body.strip()})
        return res

    def status_text(self):
        return self.git("status", "--porcelain=v1", "-z", "--untracked-files=all")

    def worktree_sig(self):
        out = self.status_text()
        sig = hashlib.sha1(out.encode())
        for ent in out.split("\0"):
            if len(ent) > 3:
                with contextlib.suppress(OSError):
                    st = os.stat(os.path.join(self.root, ent[3:]))
                    sig.update(f"{st.st_mtime_ns}:{st.st_size}".encode())
        return sig.hexdigest()[:16]

    def remote_info(self):
        url = self.git("remote", "get-url", self.remote, check=False).strip() if self.remote else ""
        host = path = ""
        m = re.match(r"^(?:[a-z+]+://)?(?:[^@/]+@)?([^/:]+)(?::\d+)?[:/](.+?)(?:\.git)?/?$", url)
        if m:
            host, path = m[1], m[2]
        forge = self._forge or self.git("config", "--get", "evie.forge", check=False).strip() or None
        if not forge:
            forge = "github" if "github" in host else "gitlab" if "gitlab" in host else None
        return {"forge": forge, "host": host, "project": path, "webUrl": f"https://{host}/{path}" if host else None}

    def find_template(self, forge):
        order = TEMPLATES.get(forge, []) + [x for k, v in TEMPLATES.items() if k != forge for x in v]
        for rel in order:
            p = Path(self.root, rel)
            if p.is_file():
                return rel, p.read_text(errors="replace")
        d = Path(self.root, ".gitlab/merge_request_templates")
        if d.is_dir():
            for p in sorted(d.glob("*.md")):
                return str(p.relative_to(self.root)), p.read_text(errors="replace")
        return None, None

    def default_description(self, forge):
        commits = self.commits()
        if len(commits) == 1:
            title = commits[0]["subject"]
        else:
            b = re.sub(r"^[^/]+/", "", self.branch())
            b = re.sub(r"[-_]+", " ", b).strip()
            title = b[:1].upper() + b[1:]
        rel, tpl = self.find_template(forge)
        if tpl:
            return title, tpl, f"template {rel}"
        if len(commits) == 1:
            return title, commits[0]["body"], "the commit message"
        if commits:
            return title, "\n".join(f"- {c['subject']}" for c in reversed(commits)), "the commit list"
        return title, "", "nothing"


# --------------------------------------------------------------------------- review store

class Store:
    def __init__(self, repo: Repo):
        self.repo = repo
        self.dir = repo.common_dir / "evie"

    def path(self, branch=None):
        slug = re.sub(r"[^A-Za-z0-9._-]+", "__", branch or self.repo.branch())
        return self.dir / f"{slug}.json"

    def load(self):
        b = self.repo.branch()
        try:
            data = json.loads(self.path(b).read_text())
        except FileNotFoundError:
            data = {}
        base = {"version": 1, "branch": b, "title": None, "body": None, "comments": [], "viewed": {}}
        return {**base, **data}

    @contextlib.contextmanager
    def edit(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / ".lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            data = self.load()
            yield data
            p = self.path(data["branch"])
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            os.replace(tmp, p)

    def rev(self):
        try:
            return self.path().stat().st_mtime_ns
        except FileNotFoundError:
            return 0

    @staticmethod
    def find(data, cid):
        cs = data["comments"]
        for c in cs:
            if c["id"] == cid:
                return c
        hits = [c for c in cs if c["id"].startswith(cid)] if len(cid) >= 3 else []
        if len(hits) == 1:
            return hits[0]
        raise ApiError(404, f"no comment with id {cid!r}" if not hits else f"ambiguous id {cid!r}")

    def description(self, data):
        forge = self.repo.remote_info()["forge"]
        saved = data.get("title") is not None or data.get("body") is not None
        dt, db, src = self.repo.default_description(forge)
        return {
            "title": data["title"] if data.get("title") is not None else dt,
            "body": data["body"] if data.get("body") is not None else db,
            "saved": saved,
            "source": "saved draft" if saved else src,
        }


def new_comment(body: dict, head: str, existing: list) -> dict:
    kind = body.get("kind")
    text = (body.get("body") or "").strip()
    if not text:
        raise ApiError(400, "comment is empty")
    ids = {c["id"] for c in existing}
    cid = secrets.token_hex(3)
    while cid in ids:
        cid = secrets.token_hex(3)
    c = {"id": cid, "kind": kind, "body": text, "author": "you", "status": "open",
         "created": now(), "updated": now(), "head": head, "replies": []}
    if kind == "line":
        side = body.get("side")
        if side not in ("old", "new"):
            raise ApiError(400, "side must be old or new")
        try:
            line = int(body["line"])
            start = int(body.get("startLine") or line)
            path = str(body["path"])
        except (KeyError, TypeError, ValueError):
            raise ApiError(400, "line comments need path and line")
        c.update(path=path, oldPath=body.get("oldPath"), side=side, line=line, startLine=min(start, line),
                 anchorText=str(body.get("anchorText", "")),
                 context=[str(x) for x in (body.get("context") or [])][:60])
    elif kind == "file":
        if not body.get("path"):
            raise ApiError(400, "file comments need a path")
        c["path"] = str(body["path"])
    elif kind != "general":
        raise ApiError(400, "kind must be line, file or general")
    return c


def add_reply(c: dict, author: str, text: str, resolve=False):
    text = (text or "").strip()
    if text:
        c.setdefault("replies", []).append(
            {"id": secrets.token_hex(3), "author": author, "body": text, "created": now()})
    if resolve:
        c["status"] = "resolved"
    elif author == "you" and text:
        c["status"] = "open"  # a reviewer reply puts the thread back in the agent's queue
    c["updated"] = now()


# --------------------------------------------------------------------------- agent prompt

def evie_cmd():
    me = Path(__file__).resolve()
    w = shutil.which("evie")
    if w and Path(w).resolve() == me:
        return "evie"
    return shlex.quote(str(me))


def locate(repo: Repo, c: dict):
    """Where a line comment's anchor line is now: ('ok'|'moved'|'outdated', line)."""
    try:
        if c["side"] == "new":
            text = Path(repo.root, c["path"]).read_text(errors="replace")
        else:
            text = repo.git("show", f"{repo.merge_base()}:{c.get('oldPath') or c['path']}")
    except (OSError, GitError):
        return "outdated", None
    lines, want, ln = text.split("\n"), c.get("anchorText", ""), c["line"]
    if 0 < ln <= len(lines) and lines[ln - 1] == want:
        return "ok", ln
    hits = [i + 1 for i, s in enumerate(lines) if s == want]
    if hits and want.strip():
        return "moved", min(hits, key=lambda i: abs(i - ln))
    return "outdated", None


def fence(lines, lang=""):
    tick = "````" if any("```" in s for s in lines) else "```"
    return [tick + lang, *lines, tick]


def quote(who, body):
    return f"**{who}:**\n" + "\n".join("> " + s if s else ">" for s in body.split("\n"))


def render_prompt(repo: Repo, data: dict, include_all=False):
    cmd = evie_cmd()
    cs = [c for c in data["comments"] if include_all or c["status"] == "open"]
    out = [f"# Local review of `{data['branch']}` → `{repo.target_branch}`", ""]
    if not cs:
        out.append("No open review comments.")
        return "\n".join(out) + "\n"
    out += [
        f"Repository: `{repo.root}`",
        "",
        f"The reviewer left {len(cs)} comment(s) on this branch's diff against `{repo.base}` "
        "(the diff a pull request would show). For each one, make the requested change in the working "
        "tree — or, if no change is warranted, explain why. Then record the outcome:",
        "",
        f"    {cmd} reply <id> --resolve \"what you changed\"   # addressed",
        f"    {cmd} reply <id> \"question or pushback\"         # needs the reviewer",
        "",
        "Line numbers refer to the current working tree. The PR title/description draft can be read with "
        f"`{cmd} describe` and updated with `{cmd} describe --title \"…\" --body-file FILE`. "
        "Do not commit unless asked.",
        "",
        "---",
    ]
    for i, c in enumerate(cs, 1):
        out.append("")
        if c["kind"] == "line":
            st, ln = locate(repo, c)
            rng = f"{c['startLine']}–{c['line']}" if c.get("startLine") and c["startLine"] != c["line"] else str(c["line"])
            where = f"line {rng}" if c["side"] == "new" else f"removed line {rng} (base version)"
            out.append(f"## {i}. `{c['path']}` {where} · id `{c['id']}`")
            if c["side"] == "new" and st == "moved":
                out.append(f"_The code has moved since this comment; the anchor line is now line {ln}._")
            elif c["side"] == "new" and st == "outdated":
                out.append("_Outdated: the commented line no longer exists in the working tree — it may already be addressed._")
            if c.get("context"):
                out += fence(c["context"], "diff")
        elif c["kind"] == "file":
            out.append(f"## {i}. `{c['path']}` (whole file) · id `{c['id']}`")
        else:
            out.append(f"## {i}. General comment · id `{c['id']}`")
        if c["status"] != "open":
            out.append(f"_status: {c['status']}_")
        out += ["", quote("Reviewer", c["body"])]
        for r in c.get("replies", []):
            out += ["", quote("Agent" if r["author"] == "agent" else "Reviewer", r["body"])]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- HTTP

class App:
    def __init__(self, repo: Repo, store: Store):
        self.repo, self.store = repo, store

    def meta(self):
        r = self.repo
        mb = r.merge_base()
        info = r.remote_info()
        return {
            "repo": os.path.basename(r.root), "root": r.root, "branch": r.branch(),
            "base": r.base, "target": r.target_branch, "remote": r.remote, **info,
            "head": r.head()[:10], "mergeBase": mb[:10],
            "ahead": int(r.git("rev-list", "--count", f"{mb}..HEAD").strip() or 0),
            "behind": int(r.git("rev-list", "--count", f"HEAD..{r.base}").strip() or 0),
            "user": r.git("config", "--get", "user.name", check=False).strip(),
            "dirty": bool(r.status_text()),
            "evie": evie_cmd(),
        }

    def review(self):
        d = self.store.load()
        return {"branch": d["branch"], "comments": d["comments"], "viewed": d["viewed"],
                "description": self.store.description(d)}

    def route(self, m, path, q, body):
        r, s = self.repo, self.store
        mode = q.get("mode", "committed")
        if mode not in ("committed", "worktree"):
            raise ApiError(400, "mode must be committed or worktree")
        if m == "GET":
            if path == "/api/meta":
                return self.meta()
            if path == "/api/diff":
                return {"files": r.files(mode)}
            if path == "/api/file":
                p, old = q.get("path"), q.get("old")
                if not p:
                    raise ApiError(400, "path required")
                fs = r.files(mode, FULL_CONTEXT, [old, p] if old and old != p else [p])
                f = next((x for x in fs if x["path"] == p), fs[0] if fs else None)
                return {"hunks": f["hunks"] if f else []}
            if path == "/api/commits":
                return {"commits": r.commits()}
            if path == "/api/review":
                return self.review()
            if path == "/api/state":
                return {"head": r.head(), "worktree": r.worktree_sig(), "review": s.rev(), "branch": r.branch()}
            if path == "/api/prompt":
                return {"text": render_prompt(r, s.load())}
            raise ApiError(404, "not found")
        body = body if isinstance(body, dict) else {}
        if path == "/api/description" and m == "PUT":
            with s.edit() as d:
                d["title"] = body.get("title")
                d["body"] = body.get("body")
            return self.review()
        if path == "/api/viewed" and m == "PUT":
            with s.edit() as d:
                if body.get("viewed"):
                    d["viewed"][str(body["path"])] = str(body.get("hash", ""))
                else:
                    d["viewed"].pop(str(body.get("path")), None)
            return {"viewed": s.load()["viewed"]}
        if path == "/api/comments" and m == "POST":
            head = r.head()
            with s.edit() as d:
                c = new_comment(body, head, d["comments"])
                d["comments"].append(c)
            return c
        mm = re.fullmatch(r"/api/comments/([0-9a-f]+)(/replies)?", path)
        if mm:
            with s.edit() as d:
                c = Store.find(d, mm[1])
                if mm[2] and m == "POST":
                    add_reply(c, "you", body.get("body", ""), bool(body.get("resolve")))
                elif not mm[2] and m == "PATCH":
                    if "status" in body:
                        if body["status"] not in ("open", "resolved"):
                            raise ApiError(400, "status must be open or resolved")
                        c["status"] = body["status"]
                    if body.get("body", "").strip():
                        c["body"] = body["body"].strip()
                    c["updated"] = now()
                elif not mm[2] and m == "DELETE":
                    d["comments"].remove(c)
                    return {"deleted": c["id"]}
                else:
                    raise ApiError(405, "method not allowed")
            return c
        raise ApiError(404, "not found")


STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}


def make_handler(app: App, verbose=False):
    class Handler(BaseHTTPRequestHandler):
        server_version = "evie"

        def log_message(self, fmt, *args):
            if verbose:
                super().log_message(fmt, *args)

        def _send(self, code, payload, ctype="application/json"):
            data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _static(self, path):
            rel = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
            p = (WEB / rel).resolve()
            if not p.is_relative_to(WEB) or not p.is_file():
                return self._send(404, {"error": "not found"})
            self._send(200, p.read_bytes(), STATIC_TYPES.get(p.suffix, "application/octet-stream"))

        def _dispatch(self, method):
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host not in ("127.0.0.1", "localhost"):
                return self._send(403, {"error": "forbidden host"})
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            # A custom header forces a CORS preflight, which we never grant: blocks cross-site writes.
            if method != "GET" and self.headers.get("X-Evie") != "1":
                return self._send(403, {"error": "missing X-Evie header"})
            body = None
            if method in ("POST", "PUT", "PATCH"):
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._send(400, {"error": "invalid JSON"})
            try:
                if method == "GET" and not u.path.startswith("/api/"):
                    return self._static(u.path)
                self._send(200, app.route(method, u.path, q, body))
            except ApiError as e:
                self._send(e.code, {"error": str(e)})
            except GitError as e:
                self._send(500, {"error": str(e)})
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self._send(500, {"error": f"{type(e).__name__}: {e}"})

        def do_GET(self): self._dispatch("GET")
        def do_POST(self): self._dispatch("POST")
        def do_PUT(self): self._dispatch("PUT")
        def do_PATCH(self): self._dispatch("PATCH")
        def do_DELETE(self): self._dispatch("DELETE")

    return Handler


# --------------------------------------------------------------------------- commands

def cmd_serve(repo: Repo, args):
    if args.fetch and repo.remote:
        print(f"evie: fetching {repo.remote}…", file=sys.stderr)
        repo.git("fetch", "--quiet", repo.remote)
    _ = repo.base  # fail early if there is no base
    app = App(repo, Store(repo))
    srv = None
    for port in range(args.port, args.port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app, args.verbose))
            break
        except OSError:
            continue
    if srv is None:
        raise SystemExit(f"evie: no free port in {args.port}–{args.port + 19}")
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"evie: {repo.branch()} → {repo.base}   {url}   (ctrl-c to stop)", file=sys.stderr)
    if not args.no_open:
        threading.Timer(0.3, webbrowser.open, [url]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def cmd_comments(repo: Repo, args):
    data = Store(repo).load()
    if args.json:
        cs = [c for c in data["comments"] if args.all or c["status"] == "open"]
        for c in cs:
            if c["kind"] == "line":
                c["current"] = dict(zip(("state", "line"), locate(repo, c)))
        print(json.dumps(cs, indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(render_prompt(repo, data, args.all))


def read_text_arg(v):
    return sys.stdin.read() if v == "-" else v


def cmd_reply(repo: Repo, args):
    text = read_text_arg(args.text) if args.text is not None else ""
    if not text.strip() and not args.resolve:
        raise SystemExit("evie: reply text required (use - to read stdin)")
    with Store(repo).edit() as d:
        c = Store.find(d, args.id)
        add_reply(c, args.author, text, args.resolve)
    print(f"{c['id']}: {'resolved' if c['status'] == 'resolved' else 'replied'}")


def cmd_status(repo: Repo, args, status):
    with Store(repo).edit() as d:
        c = Store.find(d, args.id)
        c["status"] = status
        c["updated"] = now()
    print(f"{c['id']}: {status}")


def cmd_describe(repo: Repo, args):
    store = Store(repo)
    if args.reset:
        with store.edit() as d:
            d["title"] = d["body"] = None
    elif args.title is not None or args.body is not None or args.body_file is not None:
        body = args.body
        if args.body_file is not None:
            body = sys.stdin.read() if args.body_file == "-" else Path(args.body_file).read_text()
        with store.edit() as d:
            cur = store.description(d)
            d["title"] = args.title if args.title is not None else cur["title"]
            d["body"] = body if body is not None else cur["body"]
    desc = store.description(store.load())
    if args.json:
        print(json.dumps(desc, indent=2, ensure_ascii=False))
    else:
        print(f"# {desc['title']}\n\n{desc['body'].rstrip()}\n")
        if not desc["saved"]:
            print(f"<!-- not saved yet: prefilled from {desc['source']} -->", file=sys.stderr)


def cmd_pr(repo: Repo, args):
    store = Store(repo)
    data = store.load()
    desc = store.description(data)
    branch, target, remote = repo.branch(), repo.target_branch, repo.remote
    forge = repo.remote_info()["forge"]
    if not remote:
        raise SystemExit("evie: no git remote configured")
    if forge not in ("github", "gitlab"):
        raise SystemExit("evie: can't tell if the remote is GitHub or GitLab; pass --forge or "
                         "`git config evie.forge gitlab`")
    tool = "gh" if forge == "github" else "glab"
    if not shutil.which(tool):
        raise SystemExit(f"evie: `{tool}` is not installed — it's needed to create the "
                         f"{'PR' if tool == 'gh' else 'MR'}")
    open_n = sum(c["status"] == "open" for c in data["comments"])
    if tool == "gh":
        create = ["gh", "pr", "create", "--base", target, "--head", branch, "--title", desc["title"], "--body-file", "-"]
    else:
        create = ["glab", "mr", "create", "--source-branch", branch, "--target-branch", target,
                  "--title", desc["title"], "--description", desc["body"], "--yes"]
    if args.draft:
        create.append("--draft")
    push = ["git", "push", "-u", remote, branch]
    print(f"Title: {desc['title']}")
    print(f"Description: {len(desc['body'])} chars ({desc['source']})")
    if open_n:
        print(f"warning: {open_n} review comment(s) still open")
    if not args.no_push:
        print("  $ " + shlex.join(push))
    shown = ["<description>" if tool == "glab" and i > 0 and create[i - 1] == "--description" else x
             for i, x in enumerate(create)]
    print("  $ " + shlex.join(shown))
    if not args.yes:
        if input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            raise SystemExit("aborted")
    if not args.no_push:
        subprocess.run(push, cwd=repo.root, check=True)
    subprocess.run(create, cwd=repo.root, check=True,
                   input=desc["body"].encode() if tool == "gh" else None)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="evie", description="Local pull/merge request preview and review.")
    ap.add_argument("-C", dest="repo", default=".", help="run as if started in this directory")
    ap.add_argument("--base", help="base ref (default: git config evie.base, <remote>/HEAD, then main/master)")
    ap.add_argument("--remote", help="remote to target (default: upstream's remote, else origin)")
    ap.add_argument("--forge", choices=["github", "gitlab"], help="override forge detection")
    sub = ap.add_subparsers(dest="cmd")

    sp = sub.add_parser("serve", help="open the review UI (default)")
    sp.add_argument("-p", "--port", type=int, default=7787)
    sp.add_argument("--no-open", action="store_true", help="don't open a browser")
    sp.add_argument("--fetch", action="store_true", help="git fetch the remote first")
    sp.add_argument("-v", "--verbose", action="store_true")

    sc = sub.add_parser("comments", help="print review comments as an agent prompt")
    sc.add_argument("--all", action="store_true", help="include resolved comments")
    sc.add_argument("--json", action="store_true")

    sr = sub.add_parser("reply", help="reply to a comment")
    sr.add_argument("id")
    sr.add_argument("text", nargs="?", help="reply text, or - for stdin")
    sr.add_argument("--resolve", action="store_true", help="also mark the comment resolved")
    sr.add_argument("--as", dest="author", choices=["agent", "you"], default="agent")

    for name in ("resolve", "reopen"):
        x = sub.add_parser(name, help=f"{name} a comment")
        x.add_argument("id")

    sd = sub.add_parser("describe", help="read or update the PR title/description draft")
    sd.add_argument("--title")
    sd.add_argument("--body")
    sd.add_argument("--body-file", help="file with the description, or - for stdin")
    sd.add_argument("--reset", action="store_true", help="discard the draft (back to template/commits)")
    sd.add_argument("--json", action="store_true")

    spr = sub.add_parser("pr", help="push and create the PR/MR from the draft")
    spr.add_argument("--draft", action="store_true")
    spr.add_argument("--no-push", action="store_true")
    spr.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")

    args = ap.parse_args(argv)
    if args.cmd is None:
        args = ap.parse_args(argv + ["serve"])
    repo = Repo(args.repo, args.base, args.remote, args.forge)
    try:
        if args.cmd == "serve":
            cmd_serve(repo, args)
        elif args.cmd == "comments":
            cmd_comments(repo, args)
        elif args.cmd == "reply":
            cmd_reply(repo, args)
        elif args.cmd == "resolve":
            cmd_status(repo, args, "resolved")
        elif args.cmd == "reopen":
            cmd_status(repo, args, "open")
        elif args.cmd == "describe":
            cmd_describe(repo, args)
        elif args.cmd == "pr":
            cmd_pr(repo, args)
    except (GitError, ApiError) as e:
        raise SystemExit(f"evie: {e}")
    except subprocess.CalledProcessError as e:
        raise SystemExit(e.returncode)


if __name__ == "__main__":
    main()
