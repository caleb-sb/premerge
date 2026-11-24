"""The Files changed tab: file tree, file header, diff with inline threads and composers."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings, Qt, QTimer
from PySide6.QtGui import QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSplitter,
                               QToolButton, QVBoxLayout, QWidget)

from premerge.core.anchors import line_no, locate_in_rows
from premerge.ui import icons
from premerge.ui.comments import CommentThread, Composer
from premerge.ui.diffview import DiffBody
from premerge.ui.filetree import FileTree
from premerge.ui.session import Session
from premerge.ui.theme import NIGHT

LARGE_DIFF = 3000
CONTEXT_BEFORE = 3
MAX_CONTEXT = 60
FLASH_MS = 1200


def _mono(px: int = 13, bold: bool = False):
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPixelSize(px)
    font.setBold(bold)
    return font


def _range_label(side: str, start: int, end: int) -> str:
    suffix = " (old)" if side == "old" else ""
    if start == end:
        return f"Commenting on line {start}{suffix}"
    return f"Commenting on lines {start}–{end}{suffix}"


class _MiniDiff(QFrame):
    """Read-only rendering of a comment's stored context lines."""

    def __init__(self, context: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        t = NIGHT
        self.setStyleSheet(f"_MiniDiff {{ border: 1px solid {t.border}; }}")
        self.setMaximumWidth(920)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        for raw in context:
            sign, text = (raw[:1] or " "), raw[1:]
            bg = {"+": t.diff_add_bg, "-": t.diff_del_bg}.get(sign, t.bg)
            label = QLabel(f"{sign} {text}".replace("\t", "    "))
            label.setFont(_mono())
            label.setStyleSheet(f"background: {bg}; color: {t.fg}; padding: 0 8px;")
            lay.addWidget(label)


class _Slot(QWidget):
    """Padding around a thread or composer inserted between diff rows."""

    def __init__(self, inner: QWidget) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.addWidget(inner, 100)
        lay.addStretch(1)


class FilesPage(QWidget):
    """Tree on the left; header, diff, threads and composers for the selected file on the right."""

    def __init__(self, session: Session, settings: QSettings | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self._settings = settings
        self._path: str | None = None
        self._order: list[str] = []
        self._full = False
        self._full_hunks: dict[str, list] = {}
        self._large_ok: set[tuple[str, str]] = set()
        self._shown: tuple[str, str] | None = None
        self._flat: list[dict] = []
        self._diff_visible = False
        self._threads: dict[str, CommentThread] = {}
        self._composers: dict[tuple, Composer] = {}
        self._slots: dict[QWidget, _Slot] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        lay.addWidget(self.splitter)
        self.tree = FileTree()
        self.tree.setMinimumWidth(200)
        self.tree.fileActivated.connect(self.show_file)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self._build_right())
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([300, 1000])
        if settings is not None:
            state = settings.value("files/splitter")
            if isinstance(state, (QByteArray, bytes)):
                self.splitter.restoreState(state)
            self.splitter.splitterMoved.connect(lambda *_: settings.setValue("files/splitter", self.splitter.saveState()))

        self._shortcuts: list[QShortcut] = []
        for keys, fn in (("J", lambda: self.step(1)), ("K", lambda: self.step(-1)),
                         ("V", self._toggle_viewed_key), ("F", self.tree.focus_filter),
                         ("Ctrl+P", self.tree.focus_filter), ("C", self._comment_on_file),
                         ("N", lambda: self._jump_thread(1)), ("Shift+N", lambda: self._jump_thread(-1))):
            sc = QShortcut(QKeySequence(keys), self, activated=fn)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self._shortcuts.append(sc)

        session.filesChanged.connect(self._files_changed)
        session.reviewChanged.connect(self._review_changed)
        session.viewChanged.connect(lambda _v: self._apply())
        self._files_changed()

    # ---- construction --------------------------------------------------

    def _build_right(self) -> QWidget:
        t = NIGHT
        right = QWidget()
        col = QVBoxLayout(right)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        self._header = QFrame()
        self._header.setObjectName("fileHeader")
        self._header.setStyleSheet(f"QFrame#fileHeader {{ background: {t.bg_dark}; border-bottom: 1px solid {t.border}; }}")
        h = QHBoxLayout(self._header)
        h.setContentsMargins(12, 6, 12, 6)
        h.setSpacing(8)
        self._status = QLabel()
        self._status.setFont(_mono(13, True))
        h.addWidget(self._status)
        self._old_path = QLabel()
        self._old_path.setFont(_mono())
        self._old_path.setStyleSheet(f"color: {t.muted};")
        h.addWidget(self._old_path)
        self._arrow = QLabel()
        self._arrow.setPixmap(icons.pixmap("arrow_right", t.muted, 14))
        h.addWidget(self._arrow)
        self._title = QLabel()
        self._title.setFont(_mono(13, True))
        self._title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        h.addWidget(self._title)
        self._stats = QLabel()
        h.addWidget(self._stats)
        self._count_icon = QLabel()
        self._count_icon.setPixmap(icons.pixmap("message", t.muted, 14))
        h.addWidget(self._count_icon)
        self._count = QLabel()
        self._count.setStyleSheet(f"color: {t.muted};")
        h.addWidget(self._count)
        h.addStretch(1)
        self._prev = self._tool("chevron_left", "Previous file (K)", lambda: self.step(-1))
        self._next = self._tool("chevron_right", "Next file (J)", lambda: self.step(1))
        h.addWidget(self._prev)
        h.addWidget(self._next)
        self._full_btn = self._tool("unfold", "Show the whole file", self._full_toggled, "Full file")
        self._full_btn.setCheckable(True)
        h.addWidget(self._full_btn)
        self._comment_btn = self._tool("message", "Comment on this file (C)", self._comment_on_file, "Comment on file")
        h.addWidget(self._comment_btn)
        self._changed = QLabel("Changed since viewed")
        self._changed.setStyleSheet(f"color: {t.warn};")
        h.addWidget(self._changed)
        self._viewed = QCheckBox("Viewed")
        self._viewed.setToolTip("Mark this file as viewed (V)")
        self._viewed.clicked.connect(self._viewed_clicked)
        h.addWidget(self._viewed)
        col.addWidget(self._header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self._body = QVBoxLayout(body)
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(0)
        self._area = QWidget()
        self._area_layout = QVBoxLayout(self._area)
        self._area_layout.setContentsMargins(16, 12, 16, 4)
        self._area_layout.setSpacing(10)
        self._body.addWidget(self._area)
        self._note = QWidget()
        note = QVBoxLayout(self._note)
        note.setContentsMargins(16, 24, 16, 24)
        self._note_label = QLabel()
        self._note_label.setStyleSheet(f"color: {t.muted};")
        self._note_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.addWidget(self._note_label)
        self._load_btn = QPushButton("Load diff")
        self._load_btn.clicked.connect(self._load_large)
        note.addWidget(self._load_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        self._body.addWidget(self._note)
        self.diff = DiffBody()
        self.diff.rangeSelected.connect(self._range_selected)
        self._body.addWidget(self.diff)
        self._body.addStretch(1)
        self._scroll.setWidget(body)
        col.addWidget(self._scroll, 1)
        return right

    @staticmethod
    def _tool(icon: str, tip: str, slot, text: str = "") -> QToolButton:
        b = QToolButton()
        b.setIcon(icons.icon(icon))
        b.setToolTip(tip)
        b.setAutoRaise(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if text:
            b.setText(text)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.clicked.connect(lambda _=False: slot())
        return b

    # ---- navigation ----------------------------------------------------

    def current_path(self) -> str | None:
        """Path of the file being shown."""
        return self._path

    def show_file(self, path: str, comment_id: str | None = None) -> None:
        """Select `path`; with `comment_id`, scroll to that thread and flash it."""
        if self.session.file(path) is None:
            return
        if path != self._path:
            self._path = path
            self._full = False
            self._full_btn.setChecked(False)
            self.tree.select_path(path)
            self._update_header()
            self._apply()
        if comment_id:
            QTimer.singleShot(0, lambda: self._reveal(comment_id))

    def step(self, delta: int) -> None:
        """Show the next (1) or previous (-1) file in tree order."""
        order = self.tree.ordered_paths()
        if self._path not in order:
            return
        i = order.index(self._path) + delta
        if 0 <= i < len(order):
            self.show_file(order[i])

    def _reveal(self, cid: str) -> None:
        thread = self._threads.get(cid)
        if thread is None or thread.parent() is None:
            return
        self._scroll.widget().layout().activate()
        self._scroll.ensureWidgetVisible(thread, 0, 60)
        thread.setStyleSheet(f"QFrame#thread {{ border: 2px solid {NIGHT.accent}; }}")
        QTimer.singleShot(FLASH_MS, lambda: thread.setStyleSheet(""))

    def _jump_thread(self, direction: int) -> None:
        body = self._scroll.widget()
        ys = sorted(w.mapTo(body, w.rect().topLeft()).y() for w in self._threads.values()
                    if w.parent() is not None and w.isVisibleTo(body))
        if not ys:
            return
        bar = self._scroll.verticalScrollBar()
        here = bar.value() + 70
        if direction > 0:
            target = next((y for y in ys if y > here), ys[0])
        else:
            target = next((y for y in reversed(ys) if y < here - 10), ys[-1])
        bar.setValue(max(0, target - 60))

    # ---- session events ------------------------------------------------

    def _viewed_set(self) -> tuple[set[str], set[str], dict[str, int]]:
        s = self.session
        viewed = {f["path"] for f in s.files if s.is_viewed(f)}
        changed = {f["path"] for f in s.files if s.viewed_changed(f)}
        counts: dict[str, int] = {}
        for c in s.review["comments"]:
            if c["kind"] in ("line", "file") and c["status"] == "open" and c.get("path"):
                counts[c["path"]] = counts.get(c["path"], 0) + 1
        return viewed, changed, counts

    def _files_changed(self) -> None:
        old_order = self._order
        self.tree.set_files(self.session.files, *self._viewed_set())
        self._order = self.tree.ordered_paths()
        paths = {f["path"] for f in self.session.files}
        order = self._order
        if self._path not in paths:
            nxt = None
            if self._path in old_order:
                i = old_order.index(self._path)
                nxt = next((p for p in old_order[i + 1:] if p in paths), None)
                nxt = nxt or next((p for p in reversed(old_order[:i]) if p in paths), None)
            self._path = nxt or (order[0] if order else None)
            self._full = False
            self._full_btn.setChecked(False)
        if self._path is not None:
            self.tree.select_path(self._path)
        self._update_header()
        self._apply()

    def _review_changed(self) -> None:
        self.tree.set_files(self.session.files, *self._viewed_set())
        if self._path is not None:
            self.tree.select_path(self._path)
        self._update_header()
        self._sync_threads()
        self._place()

    # ---- header --------------------------------------------------------

    def _update_header(self) -> None:
        t = NIGHT
        f = self.session.file(self._path) if self._path else None
        for w in (self._status, self._old_path, self._arrow, self._title, self._stats, self._count_icon,
                  self._count, self._prev, self._next, self._full_btn, self._comment_btn, self._changed,
                  self._viewed):
            w.setVisible(f is not None)
        if f is None:
            return
        letter = {"added": "A", "modified": "M", "deleted": "D", "renamed": "R", "copied": "C"}[f["status"]]
        color = getattr(t, f"st_{f['status']}", t.st_renamed) if f["status"] != "copied" else t.st_renamed
        self._status.setText(letter)
        self._status.setStyleSheet(f"color: {color};")
        renamed = f["status"] in ("renamed", "copied") and f.get("oldPath")
        self._old_path.setVisible(bool(renamed))
        self._arrow.setVisible(bool(renamed))
        self._old_path.setText(f["oldPath"] if renamed else "")
        self._title.setText(f["path"])
        self._stats.setText(f"<span style='color:{t.ok}'>+{f['additions']}</span> "
                            f"<span style='color:{t.bad}'>−{f['deletions']}</span>")
        n = sum(1 for c in self.session.comments_for(f["path"]) if c["status"] == "open")
        self._count.setText(str(n))
        self._count.setVisible(n > 0)
        self._count_icon.setVisible(n > 0)
        order = self.tree.ordered_paths()
        i = order.index(f["path"]) if f["path"] in order else 0
        self._prev.setEnabled(i > 0)
        self._next.setEnabled(i < len(order) - 1)
        self._full_btn.setEnabled(not f["binary"] and f["status"] not in ("added", "deleted"))
        self._changed.setVisible(self.session.viewed_changed(f))
        self._viewed.setChecked(self.session.is_viewed(f))

    def _full_toggled(self) -> None:
        self._full = self._full_btn.isChecked()
        self._apply()

    def _viewed_clicked(self, checked: bool) -> None:
        f = self.session.file(self._path) if self._path else None
        if f is None:
            return
        self.session.set_viewed(f, checked)
        if checked:
            self._next_unviewed()

    def _toggle_viewed_key(self) -> None:
        self._viewed.click()

    def _next_unviewed(self) -> None:
        order = self.tree.ordered_paths()
        if self._path not in order:
            return
        i = order.index(self._path)
        for p in order[i + 1:] + order[:i]:
            f = self.session.file(p)
            if f is not None and not self.session.is_viewed(f):
                self.show_file(p)
                return

    # ---- content -------------------------------------------------------

    def _load_large(self) -> None:
        f = self.session.file(self._path) if self._path else None
        if f is not None:
            self._large_ok.add((f["path"], f["hash"]))
            self._apply()

    def _apply(self) -> None:
        """Re-render the body of the current file, keeping the scroll position when it is the same file."""
        f = self.session.file(self._path) if self._path else None
        bar = self._scroll.verticalScrollBar()
        key = (f["path"], f["hash"]) if f else None
        keep = bar.value() if key is not None and key == self._shown else 0
        self._shown = key
        self._flat = []
        self._diff_visible = False
        self.diff.hide()
        self._note.hide()
        if f is None:
            self._set_note("No changes to show.")
            self._sync_threads()
            self._place()
            return
        hunks = f["hunks"]
        if self._full and not f["binary"] and f["status"] not in ("added", "deleted"):
            cached = self._full_hunks.get(f["path"])
            if cached is not None and cached[0] == f["hash"]:
                hunks = cached[1]
            else:
                self.session.full_hunks(f["path"], lambda hs, p=f["path"], h=f["hash"]: self._got_full(p, h, hs))
        lines = sum(len(h["lines"]) for h in hunks)
        if f["binary"]:
            self._set_note("Binary file not shown")
        elif not hunks:
            self._set_note(self._empty_note(f))
        elif lines > LARGE_DIFF and key not in self._large_ok:
            self._set_note(f"Large diff — {lines} lines", button=True)
        else:
            self.diff.set_content(f["path"], hunks, self.session.view)
            self.diff.show()
            self._diff_visible = True
            self._flat = [ln for h in hunks for ln in h["lines"]]
        self._sync_threads()
        self._place()
        self._scroll.widget().layout().activate()
        bar.setValue(keep)
        QTimer.singleShot(0, lambda: bar.setValue(keep))

    def _got_full(self, path: str, fhash: str, hunks: list) -> None:
        self._full_hunks[path] = (fhash, hunks)
        f = self.session.file(self._path) if self._path else None
        if self._full and f is not None and f["path"] == path and f["hash"] == fhash:
            self._apply()

    @staticmethod
    def _empty_note(f: dict) -> str:
        if f["status"] == "renamed":
            return "File renamed without changes"
        if f.get("oldMode") and f.get("newMode") and f["oldMode"] != f["newMode"]:
            return f"Mode changed {f['oldMode']} → {f['newMode']}"
        return "No content changes"

    def _set_note(self, text: str, button: bool = False) -> None:
        self._note_label.setText(text)
        self._load_btn.setVisible(button)
        self._note.show()

    # ---- threads and composers ----------------------------------------

    def _sync_threads(self) -> None:
        """Create, update and delete CommentThread widgets to match the current file's comments."""
        comments = {c["id"]: c for c in self.session.comments_for(self._path)} if self._path else {}
        for cid in [c for c in self._threads if c not in comments]:
            self._forget(self._threads.pop(cid))
        user = (self.session.meta or {}).get("user", "")
        for cid, c in comments.items():
            existing = self._threads.get(cid)
            if existing is not None:
                existing.update_comment(c)
                continue
            w = CommentThread(c, user)
            w.replyRequested.connect(lambda i, text: self.session.reply(i, text))
            w.statusRequested.connect(self.session.set_status)
            w.editRequested.connect(self.session.edit_body)
            w.deleteRequested.connect(self.session.delete_comment)
            self._threads[cid] = w

    def _clear_area(self) -> None:
        keep = set(self._threads.values()) | set(self._composers.values())
        while self._area_layout.count():
            w = self._area_layout.takeAt(0).widget()
            if w is None:
                continue
            w.setParent(None)
            if w not in keep:
                w.deleteLater()

    def _place(self) -> None:
        """Put threads and composers in the diff (inserts) or the file comments area."""
        for w in self._composers.values():
            if self._path is None or w.property("path") != self._path:
                w.hide()
        self._clear_area()
        inserts: dict[int, list[QWidget]] = {}
        outdated: list[dict] = []
        if self._path is None:
            self.diff.set_inserts({})
            return
        file_threads: list[QWidget] = []
        for c in self.session.comments_for(self._path):
            if c["kind"] == "file":
                file_threads.append(self._threads[c["id"]])
                continue
            row = self._row_for(c)
            if row is None:
                outdated.append(c)
            else:
                inserts.setdefault(row, []).append(self._threads[c["id"]])
        drafts: list[Composer] = []
        file_composer: Composer | None = None
        for key, comp in list(self._composers.items()):
            if key[0] != self._path:
                continue
            if key[1] == "file":
                file_composer = comp
                continue
            row = self.diff.row_index(f"{key[1]}:{key[3]}") if self._diff_visible else None
            if row is not None:
                inserts.setdefault(row, []).append(comp)
            elif comp.text().strip():
                comp.set_label("Draft for a line that changed")
                drafts.append(comp)
            else:
                self._drop_composer(key)
        if file_composer is not None:
            self._add_area(file_composer)
        for w in file_threads:
            self._add_area(w)
        for c in outdated:
            label = QLabel(f"Outdated · line {c['line']}")
            label.setStyleSheet(f"color: {NIGHT.muted};")
            self._add_area(label)
            if c.get("context"):
                self._add_area(_MiniDiff(c["context"]))
            self._add_area(self._threads[c["id"]])
        for comp in drafts:
            self._add_area(comp)
        self._area.setVisible(self._area_layout.count() > 0)
        self.diff.set_inserts({i: [self._slot(w) for w in ws] for i, ws in inserts.items()}
                              if self._diff_visible else {})

    def _slot(self, w: QWidget) -> _Slot:
        slot = self._slots.get(w)
        if slot is None:
            slot = self._slots[w] = _Slot(w)
        elif w.parent() is not slot:
            slot.layout().insertWidget(0, w)
        w.show()
        return slot

    def _forget(self, w: QWidget) -> None:
        slot = self._slots.pop(w, None)
        w.setParent(None)
        w.deleteLater()
        if slot is not None:
            slot.deleteLater()

    def _add_area(self, w: QWidget) -> None:
        self._area_layout.addWidget(w)
        w.show()

    def _row_for(self, c: dict) -> int | None:
        if not self._diff_visible:
            return None
        idx, state = locate_in_rows(self._flat, c)
        if idx is None or state == "missing":
            return None
        n = line_no(self._flat[idx], c["side"])
        return self.diff.row_index(f"{c['side']}:{n}")

    def _drop_composer(self, key: tuple) -> None:
        comp = self._composers.pop(key, None)
        if comp is not None:
            self._forget(comp)

    def _open_composer(self, key: tuple, label: str, submit) -> Composer:
        comp = self._composers.get(key)
        if comp is None:
            comp = Composer(label=label)
            comp.setProperty("path", key[0])
            comp.setMaximumWidth(920)
            comp.submitted.connect(lambda text, k=key: submit(k, text))
            comp.cancelled.connect(lambda k=key: self._cancel(k))
            self._composers[key] = comp
        self._place()
        comp.focus_editor()
        return comp

    def _cancel(self, key: tuple) -> None:
        self._drop_composer(key)
        self.diff.clear_selection()
        self._place()

    def _range_selected(self, side: str, start: int, end: int) -> None:
        if self._path is None:
            return
        self._open_composer((self._path, side, start, end), _range_label(side, start, end), self._submit_line)

    def _submit_line(self, key: tuple, text: str) -> None:
        path, side, start, end = key
        f = self.session.file(path)
        if f is None or not text.strip():
            return
        nums = [line_no(ln, side) for ln in self._flat]
        if start not in nums or end not in nums:
            return
        first, last = nums.index(start), nums.index(end)
        context = [ln["t"] + ln["s"] for ln in self._flat[max(0, first - CONTEXT_BEFORE):last + 1]][-MAX_CONTEXT:]
        fields = {"kind": "line", "body": text.strip(), "path": path, "oldPath": f.get("oldPath"), "side": side,
                  "startLine": start, "line": end, "anchorText": self._flat[last]["s"], "context": context}
        if self.session.add_comment(fields) is not None:
            self._drop_composer(key)
            self.diff.clear_selection()
            self._place()

    def _comment_on_file(self) -> None:
        if self._path is None:
            return
        self._open_composer((self._path, "file", 0, 0), "Commenting on this file", self._submit_file)

    def _submit_file(self, key: tuple, text: str) -> None:
        if text.strip() and self.session.add_comment({"kind": "file", "body": text.strip(), "path": key[0]}) is not None:
            self._drop_composer(key)
            self._place()
