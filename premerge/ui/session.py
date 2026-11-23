"""Session: the single owner of repo/store state for the UI."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from premerge.core import prompt
from premerge.core.gitrepo import Repo
from premerge.core.paths import tree_order
from premerge.core.store import Store, StoreError
from premerge.ui import jobs

POLL_MS = 2000


class Session(QObject):
    """Loads review data off the UI thread, polls for changes and performs mutations."""

    metaChanged = Signal()
    filesChanged = Signal()
    commitsChanged = Signal()
    reviewChanged = Signal()
    busyChanged = Signal(bool)
    error = Signal(str)
    modeChanged = Signal(str)
    viewChanged = Signal(str)

    def __init__(self, repo: Repo, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.store = Store(repo)
        self.mode = "committed"
        self.view = "unified"
        self.meta: dict | None = None
        self.files: list[dict] = []
        self.commits: list[dict] = []
        self.review: dict = {"comments": [], "viewed": {}, "description": None}
        self.busy = False
        self.last_refresh: datetime | None = None
        self._gen = {"code": 0, "review": 0}
        self._running = {"code": False, "review": False}
        self._pending = {"code": False, "review": False}
        self._full_cache: dict[tuple, list] = {}
        self._poll_busy = False
        self._poll_prev: tuple | None = None
        self._poll_err: str | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)

    # ---- loading -------------------------------------------------------

    def reload_all(self) -> None:
        """Reload meta, files, commits and review."""
        self.reload_code()
        self.reload_review()

    def reload_code(self) -> None:
        """Reload meta, files and commits."""
        self._load("code")

    def reload_review(self) -> None:
        """Reload comments, viewed state and the description."""
        self._load("review")

    def _load(self, kind: str) -> None:
        if self._running[kind]:
            self._pending[kind] = True
            return
        self._gen[kind] += 1
        gen, mode = self._gen[kind], self.mode
        self._set_running(kind, True)
        fn = self._fetch_code if kind == "code" else self._fetch_review
        args = (mode,) if kind == "code" else ()
        jobs.run(fn, *args,
                 on_done=lambda res: self._loaded(kind, gen, mode, res),
                 on_error=lambda exc: self._failed(kind, exc))

    def _set_running(self, kind: str, value: bool) -> None:
        self._running[kind] = value
        busy = any(self._running.values())
        if busy != self.busy:
            self.busy = busy
            self.busyChanged.emit(busy)

    def _finish(self, kind: str) -> None:
        self._set_running(kind, False)
        if self._pending[kind]:
            self._pending[kind] = False
            self._load(kind)

    def _failed(self, kind: str, exc: Exception) -> None:
        self.error.emit(str(exc))
        self._finish(kind)

    def _fetch_code(self, mode: str) -> dict:
        files = self.repo.files(mode)
        order = {p: i for i, p in enumerate(tree_order([f["path"] for f in files]))}
        files.sort(key=lambda f: order[f["path"]])
        return {"meta": self.repo.meta(), "files": files, "commits": self.repo.commits()}

    def _fetch_review(self) -> dict:
        data = self.store.load()
        return {"comments": data["comments"], "viewed": data["viewed"],
                "description": self.store.description(data)}

    def _loaded(self, kind: str, gen: int, mode: str, res: dict) -> None:
        if gen == self._gen[kind] and (kind == "review" or mode == self.mode):
            if kind == "code":
                self.meta, self.files, self.commits = res["meta"], res["files"], res["commits"]
                self._full_cache.clear()
                self.last_refresh = datetime.now()
                self.metaChanged.emit()
                self.filesChanged.emit()
                self.commitsChanged.emit()
            else:
                self.review = res
                self.reviewChanged.emit()
        elif kind == "code" and mode != self.mode:
            self._pending[kind] = True
        self._finish(kind)

    # ---- setters -------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        """Switch between committed and worktree diffs and reload."""
        if mode == self.mode:
            return
        self.mode = mode
        self.modeChanged.emit(mode)
        self.reload_code()

    def set_view(self, view: str) -> None:
        """Switch between unified and split layout."""
        if view == self.view:
            return
        self.view = view
        self.viewChanged.emit(view)

    # ---- queries -------------------------------------------------------

    def file(self, path: str) -> dict | None:
        """The FileDiff for `path`, if any."""
        return next((f for f in self.files if f["path"] == path), None)

    def comments_for(self, path: str) -> list[dict]:
        """Line and file comments attached to `path`."""
        return [c for c in self.review["comments"]
                if c["kind"] in ("line", "file") and c.get("path") == path]

    def general_comments(self) -> list[dict]:
        """Comments not attached to a file."""
        return [c for c in self.review["comments"] if c["kind"] == "general"]

    def open_count(self) -> int:
        """Number of open comments."""
        return sum(1 for c in self.review["comments"] if c["status"] == "open")

    def is_viewed(self, f: dict) -> bool:
        """True when the stored viewed hash equals the file's current hash."""
        return self.review["viewed"].get(f["path"]) == f["hash"]

    def viewed_changed(self, f: dict) -> bool:
        """True when the file was viewed but has changed since."""
        stored = self.review["viewed"].get(f["path"])
        return stored is not None and stored != f["hash"]

    def prompt_text(self) -> str:
        """The agent prompt for the open comments (reads the store synchronously)."""
        return prompt.render_prompt(self.repo, self.store.load())

    def full_hunks(self, path: str, callback: Callable[[list], None]) -> None:
        """Asynchronously deliver the whole file as hunks (cached per mode, path and hash)."""
        f = self.file(path)
        if f is None:
            return
        key = (self.mode, path, f["hash"])
        if key in self._full_cache:
            callback(self._full_cache[key])
            return
        mode = self.mode

        def done(hunks: list) -> None:
            self._full_cache[key] = hunks
            callback(hunks)

        jobs.run(self.repo.file_full, mode, path, f.get("oldPath"), on_done=done,
                 on_error=lambda exc: self.error.emit(str(exc)))

    # ---- mutations -----------------------------------------------------

    def _mutate(self, fn: Callable, *args):
        try:
            result = fn(*args)
        except StoreError as exc:
            self.error.emit(str(exc))
            return None
        self.reload_review()
        return result

    def add_comment(self, fields: dict) -> dict | None:
        """Add a comment; returns it, or None on invalid input."""
        return self._mutate(self.store.add_comment, fields)

    def reply(self, cid: str, text: str, resolve: bool = False) -> None:
        """Reply as the user, optionally resolving."""
        self._mutate(self.store.reply, cid, "you", text, resolve)

    def set_status(self, cid: str, status: str) -> None:
        """Resolve or reopen a comment."""
        self._mutate(self.store.set_status, cid, status)

    def edit_body(self, cid: str, text: str) -> None:
        """Replace a comment's body."""
        self._mutate(self.store.edit_body, cid, text)

    def delete_comment(self, cid: str) -> None:
        """Delete a comment."""
        self._mutate(self.store.delete, cid)

    def set_viewed(self, f: dict, viewed: bool) -> None:
        """Mark a file viewed (at its current hash) or not; the UI updates immediately."""
        value = f["hash"] if viewed else None
        try:
            self.store.set_viewed(f["path"], value)
        except StoreError as exc:
            self.error.emit(str(exc))
            return
        if viewed:
            self.review["viewed"][f["path"]] = value
        else:
            self.review["viewed"].pop(f["path"], None)
        self.reviewChanged.emit()
        self.reload_review()

    def save_description(self, title: str, body: str) -> None:
        """Store a custom PR title and body."""
        self._mutate(self.store.set_description, title, body)

    def reset_description(self) -> None:
        """Drop the custom description."""
        self._mutate(self.store.set_description, None, None)

    # ---- polling -------------------------------------------------------

    def start(self) -> None:
        """Start polling for external changes."""
        self._timer.start()

    def stop(self) -> None:
        """Stop polling."""
        self._timer.stop()

    def _signature(self, mode: str) -> tuple:
        sig = self.repo.worktree_sig() if mode == "worktree" else None
        return (self.repo.branch(), self.repo.head(), sig, self.store.rev())

    def _poll(self) -> None:
        if self._poll_busy:
            return
        self._poll_busy = True
        jobs.run(self._signature, self.mode, on_done=self._polled, on_error=self._poll_failed)

    def _poll_failed(self, exc: Exception) -> None:
        self._poll_busy = False
        if str(exc) != self._poll_err:
            self._poll_err = str(exc)
            self.error.emit(self._poll_err)

    def _polled(self, cur: tuple) -> None:
        self._poll_busy = False
        self._poll_err = None
        prev, self._poll_prev = self._poll_prev, cur
        if prev is None:
            return
        if cur[:2] != prev[:2]:
            self.reload_all()
            return
        if cur[2] != prev[2]:
            self.reload_code()
        if cur[3] != prev[3]:
            self.reload_review()
