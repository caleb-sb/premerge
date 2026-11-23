"""The per-branch review store (comments, viewed files, PR draft) kept inside the git dir."""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from premerge.core.gitrepo import Repo


class StoreError(Exception):
    """Bad input or an unknown comment id."""


def now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    """Reads and writes `<git-common-dir>/premerge/<branch-slug>.json` under a file lock."""

    def __init__(self, repo: Repo):
        self.repo = repo
        self.dir = repo.common_dir / "premerge"

    def path(self, branch: str | None = None) -> Path:
        """Store file for a branch (default: the current one)."""
        slug = re.sub(r"[^A-Za-z0-9._-]+", "__", branch or self.repo.branch())
        return self.dir / f"{slug}.json"

    def load(self) -> dict:
        """The StoreFile for the current branch (defaults filled in if none exists)."""
        b = self.repo.branch()
        try:
            data = json.loads(self.path(b).read_text())
        except FileNotFoundError:
            data = {}
        base = {"version": 1, "branch": b, "title": None, "body": None, "comments": [], "viewed": {}}
        return {**base, **data}

    @contextlib.contextmanager
    def edit(self):
        """Lock the store, yield its data for mutation, and save it atomically on exit."""
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / ".lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            data = self.load()
            yield data
            p = self.path(data["branch"])
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            os.replace(tmp, p)

    def rev(self) -> int:
        """Modification time (ns) of the store file; 0 if it doesn't exist."""
        try:
            return self.path().stat().st_mtime_ns
        except FileNotFoundError:
            return 0

    @staticmethod
    def find(data: dict, cid: str) -> dict:
        """The comment with this id (exact, or a unique prefix of at least 3 chars)."""
        cs = data["comments"]
        for c in cs:
            if c["id"] == cid:
                return c
        hits = [c for c in cs if c["id"].startswith(cid)] if len(cid) >= 3 else []
        if len(hits) == 1:
            return hits[0]
        raise StoreError(f"no comment with id {cid!r}" if not hits else f"ambiguous id {cid!r}")

    def description(self, data: dict | None = None) -> dict:
        """The PR Description: the saved draft, else defaults from the template/commits."""
        if data is None:
            data = self.load()
        forge = self.repo.remote_info()["forge"]
        saved = data.get("title") is not None or data.get("body") is not None
        dt, db, src = self.repo.default_description(forge)
        return {
            "title": data["title"] if data.get("title") is not None else dt,
            "body": data["body"] if data.get("body") is not None else db,
            "saved": saved,
            "source": "saved draft" if saved else src,
        }

    def add_comment(self, fields: dict) -> dict:
        """Validate and store a new comment from `fields`; returns it."""
        head = self.repo.head()
        with self.edit() as d:
            c = new_comment(fields, head, d["comments"])
            d["comments"].append(c)
        return c

    def reply(self, cid: str, author: str, text: str, resolve: bool = False) -> dict:
        """Add a reply (and optionally resolve). A reply by `you` re-opens the thread."""
        with self.edit() as d:
            c = self.find(d, cid)
            add_reply(c, author, text, resolve)
        return c

    def set_status(self, cid: str, status: str) -> dict:
        """Set a comment's status to 'open' or 'resolved'."""
        if status not in ("open", "resolved"):
            raise StoreError("status must be open or resolved")
        with self.edit() as d:
            c = self.find(d, cid)
            c["status"] = status
            c["updated"] = now()
        return c

    def edit_body(self, cid: str, text: str) -> dict:
        """Replace a comment's body."""
        text = (text or "").strip()
        if not text:
            raise StoreError("comment is empty")
        with self.edit() as d:
            c = self.find(d, cid)
            c["body"] = text
            c["updated"] = now()
        return c

    def delete(self, cid: str) -> None:
        """Delete a comment."""
        with self.edit() as d:
            d["comments"].remove(self.find(d, cid))

    def set_viewed(self, path: str, hash_or_none: str | None) -> None:
        """Mark a file viewed at the given hash, or clear the mark with None."""
        with self.edit() as d:
            if hash_or_none:
                d["viewed"][path] = hash_or_none
            else:
                d["viewed"].pop(path, None)

    def set_description(self, title: str | None, body: str | None) -> None:
        """Save the PR draft; both None resets it to the defaults."""
        with self.edit() as d:
            d["title"], d["body"] = title, body


def new_comment(body: dict, head: str, existing: list) -> dict:
    """Build a validated Comment dict from user fields."""
    kind = body.get("kind")
    text = (body.get("body") or "").strip()
    if not text:
        raise StoreError("comment is empty")
    ids = {c["id"] for c in existing}
    cid = secrets.token_hex(3)
    while cid in ids:
        cid = secrets.token_hex(3)
    c = {"id": cid, "kind": kind, "body": text, "author": "you", "status": "open",
         "created": now(), "updated": now(), "head": head, "replies": []}
    if kind == "line":
        side = body.get("side")
        if side not in ("old", "new"):
            raise StoreError("side must be old or new")
        try:
            line = int(body["line"])
            start = int(body.get("startLine") or line)
            path = str(body["path"])
        except (KeyError, TypeError, ValueError):
            raise StoreError("line comments need path and line") from None
        c.update(path=path, oldPath=body.get("oldPath"), side=side, line=line, startLine=min(start, line),
                 anchorText=str(body.get("anchorText", "")),
                 context=[str(x) for x in (body.get("context") or [])][:60])
    elif kind == "file":
        if not body.get("path"):
            raise StoreError("file comments need a path")
        c["path"] = str(body["path"])
    elif kind != "general":
        raise StoreError("kind must be line, file or general")
    return c


def add_reply(c: dict, author: str, text: str, resolve: bool = False) -> None:
    """Append a reply to comment `c` in place and update its status."""
    text = (text or "").strip()
    if text:
        c.setdefault("replies", []).append(
            {"id": secrets.token_hex(3), "author": author, "body": text, "created": now()})
    if resolve:
        c["status"] = "resolved"
    elif author == "you" and text:
        c["status"] = "open"  # a reviewer reply puts the thread back in the agent's queue
    c["updated"] = now()
