"""Overview tab: PR description draft, conversation, review-comment summary and details sidebar."""
from __future__ import annotations

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QFontDatabase, QKeySequence, QMouseEvent, QShortcut
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from premerge.core.paths import tree_order
from premerge.ui import icons
from premerge.ui.comments import CommentThread, Composer, _avatar
from premerge.ui.markdown import MarkdownView, plain_first_line
from premerge.ui.theme import NIGHT

MAIN_MAX = 900
SIDEBAR_W = 260
NARROW = 1000
FORGES = {"github": "GitHub", "gitlab": "GitLab"}


class _BodyEditor(QPlainTextEdit):
    """Plain-text editor where Tab inserts two spaces."""

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Tab and not event.modifiers():
            self.insertPlainText("  ")
            return
        super().keyPressEvent(event)


class _SummaryRow(QFrame):
    """One clickable row of the review-comment summary."""

    clicked = Signal()

    def __init__(self, comment: dict, t=NIGHT) -> None:
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 6, 12, 6)
        row.setSpacing(10)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        colour = t.warn if comment["status"] == "open" else t.ok
        dot.setStyleSheet(f"background: {colour}; border-radius: 4px;")
        row.addWidget(dot)
        where = comment["path"] if comment["kind"] == "file" else f"{comment['path']}:{comment['line']}"
        loc = QLabel(where)
        loc.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        row.addWidget(loc)
        body = plain_first_line(comment["body"])
        text = QLabel(body)
        text.setObjectName("muted")
        text.setMinimumWidth(0)
        text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row.addWidget(text, 1)
        replies = comment.get("replies") or []
        if replies and replies[-1]["author"] == "agent":
            bot = QLabel()
            bot.setPixmap(icons.pixmap("bot", t.agent, 16))
            bot.setToolTip("The agent replied last")
            row.addWidget(bot)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size: 15px; font-weight: bold;")
    return label


class OverviewPage(QWidget):
    """The Overview tab."""

    openComment = Signal(str, str)

    def __init__(self, session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self._editing = False
        self._loaded: tuple[str, str] = ("", "")
        self._latest: dict | None = None
        self._threads: dict[str, CommentThread] = {}
        self._rows: list[_SummaryRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        outer.addWidget(self.scroll)
        content = QWidget()
        self.scroll.setWidget(content)
        self._cols = QBoxLayout(QBoxLayout.Direction.LeftToRight, content)
        self._cols.setContentsMargins(24, 20, 24, 24)
        self._cols.setSpacing(24)

        self.main = QWidget()
        self.main.setMaximumWidth(MAIN_MAX)
        main = QVBoxLayout(self.main)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(14)
        main.addWidget(self._build_card())
        main.addSpacing(6)
        main.addWidget(_heading("Conversation"))
        self.threads_box = QVBoxLayout()
        self.threads_box.setSpacing(10)
        main.addLayout(self.threads_box)
        self.composer = Composer(
            placeholder="Leave a general comment for the agent — about the approach, the description, anything…",
            cancellable=False,
        )
        self.composer.submitted.connect(self._add_general)
        main.addWidget(self.composer)
        main.addSpacing(6)
        self.summary = QWidget()
        sv = QVBoxLayout(self.summary)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(_heading("Review comments"))
        self.summary_count = QLabel()
        self.summary_count.setObjectName("muted")
        head.addWidget(self.summary_count)
        head.addStretch(1)
        sv.addLayout(head)
        self.summary_list = QFrame()
        self.summary_list.setObjectName("card")
        self.summary_layout = QVBoxLayout(self.summary_list)
        self.summary_layout.setContentsMargins(0, 4, 0, 4)
        self.summary_layout.setSpacing(0)
        sv.addWidget(self.summary_list)
        main.addWidget(self.summary)
        main.addStretch(1)

        self.sidebar = self._build_sidebar()
        self._cols.addWidget(self.main, 1, Qt.AlignmentFlag.AlignTop)
        self._cols.addWidget(self.sidebar, 0, Qt.AlignmentFlag.AlignTop)

        save = QShortcut(QKeySequence.StandardKey.Save, self.edit_box)
        save.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        save.activated.connect(self._save)
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.edit_box)
        esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc.activated.connect(self._cancel)

        session.reviewChanged.connect(self.refresh)
        session.metaChanged.connect(self.refresh)
        session.filesChanged.connect(self.refresh)
        session.commitsChanged.connect(self.refresh)
        self.refresh()

    # ---- description card ----------------------------------------------

    def _build_card(self) -> QFrame:
        self.card = QFrame()
        self.card.setObjectName("card")
        col = QVBoxLayout(self.card)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        header = QFrame()
        header.setObjectName("cardHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 8, 12, 8)
        hl.setSpacing(8)
        self.avatar_slot = QHBoxLayout()
        self.avatar_slot.setContentsMargins(0, 0, 0, 0)
        hl.addLayout(self.avatar_slot)
        self.author_label = QLabel()
        self.author_label.setStyleSheet("font-weight: bold;")
        hl.addWidget(self.author_label)
        self.state_label = QLabel()
        self.state_label.setObjectName("muted")
        hl.addWidget(self.state_label)
        hl.addStretch(1)
        self.edit_button = QPushButton("Edit")
        self.edit_button.setIcon(icons.icon("pencil"))
        self.edit_button.clicked.connect(self.start_edit)
        hl.addWidget(self.edit_button)
        col.addWidget(header)

        self.view_box = QWidget()
        vl = QVBoxLayout(self.view_box)
        vl.setContentsMargins(16, 14, 16, 14)
        self.body_view = MarkdownView(placeholder="No description provided.")
        vl.addWidget(self.body_view)
        col.addWidget(self.view_box)

        self.edit_box = QWidget()
        el = QVBoxLayout(self.edit_box)
        el.setContentsMargins(16, 14, 16, 14)
        el.setSpacing(10)
        self.warn_bar = QFrame()
        self.warn_bar.setStyleSheet(
            f"QFrame {{ background: {NIGHT.bg_dark}; border: 1px solid {NIGHT.warn}; border-radius: 6px; }}"
            f"QLabel {{ border: none; color: {NIGHT.warn}; }}"
        )
        wl = QHBoxLayout(self.warn_bar)
        wl.setContentsMargins(10, 6, 10, 6)
        wl.addWidget(QLabel("The description was changed outside the editor."), 1)
        self.load_button = QPushButton("Load it")
        self.load_button.clicked.connect(self._load_latest)
        self.keep_button = QPushButton("Keep mine")
        self.keep_button.clicked.connect(self._keep_mine)
        wl.addWidget(self.load_button)
        wl.addWidget(self.keep_button)
        self.warn_bar.hide()
        el.addWidget(self.warn_bar)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Title")
        self.title_edit.setStyleSheet("font-size: 18px; padding: 4px 6px;")
        el.addWidget(self.title_edit)
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self.write_button = QPushButton("Write")
        self.preview_button = QPushButton("Preview")
        for b in (self.write_button, self.preview_button):
            b.setCheckable(True)
            b.setFlat(True)
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; color: {NIGHT.fg_dark}; padding: 4px 12px; }}"
                f"QPushButton:checked {{ background: {NIGHT.accent_soft}; color: {NIGHT.accent}; }}"
            )
            tabs.addWidget(b)
        tabs.addStretch(1)
        self.write_button.clicked.connect(lambda: self._set_preview(False))
        self.preview_button.clicked.connect(lambda: self._set_preview(True))
        el.addLayout(tabs)
        self.body_edit = _BodyEditor()
        self.body_edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.body_edit.setMinimumHeight(280)
        self.body_edit.setPlaceholderText("Describe the change…")
        el.addWidget(self.body_edit)
        self.preview = MarkdownView(placeholder="Nothing to preview.")
        self.preview.hide()
        el.addWidget(self.preview)
        buttons = QHBoxLayout()
        self.reset_button = QPushButton("Reset to default")
        self.reset_button.clicked.connect(self._reset)
        buttons.addWidget(self.reset_button)
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel)
        self.save_button = QPushButton("Save")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._save)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        el.addLayout(buttons)
        self.edit_box.hide()
        col.addWidget(self.edit_box)
        return self.card

    def _description(self) -> dict:
        return self.session.review.get("description") or {"title": "", "body": "", "saved": False, "source": ""}

    @property
    def editing(self) -> bool:
        """True while the description editor is open."""
        return self._editing

    def start_edit(self) -> None:
        """Open the description editor."""
        if self._editing:
            return
        d = self._description()
        self._editing = True
        self._loaded = (d["title"], d["body"])
        self.title_edit.setText(d["title"])
        self.body_edit.setPlainText(d["body"] or "")
        self.warn_bar.hide()
        self._latest = None
        self._set_preview(False)
        self.reset_button.setVisible(bool(d["saved"]))
        self.view_box.hide()
        self.edit_box.show()
        self.edit_button.hide()
        self.body_edit.setFocus()

    def _set_preview(self, on: bool) -> None:
        self.preview_button.setChecked(on)
        self.write_button.setChecked(not on)
        if on:
            self.preview.set_markdown(self.body_edit.toPlainText())
        self.preview.setVisible(on)
        self.body_edit.setVisible(not on)

    def _modified(self) -> bool:
        return (self.title_edit.text(), self.body_edit.toPlainText()) != (self._loaded[0], self._loaded[1] or "")

    def _leave_edit(self) -> None:
        self._editing = False
        self._latest = None
        self.edit_box.hide()
        self.view_box.show()
        self.edit_button.show()
        self.refresh()

    def _confirm(self, title: str, text: str) -> bool:
        return QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes

    def _save(self) -> None:
        if not self._editing:
            return
        self.session.save_description(self.title_edit.text().strip(), self.body_edit.toPlainText())
        self._leave_edit()

    def _cancel(self) -> None:
        if not self._editing:
            return
        if self._modified() and not self._confirm("Discard changes", "Discard your changes to the description?"):
            return
        self._leave_edit()

    def _reset(self) -> None:
        if self._confirm("Reset description", "Discard the saved title and description and use the defaults?"):
            self.session.reset_description()
            self._leave_edit()

    def _load_latest(self) -> None:
        if self._latest is not None:
            d = self._latest
            self._loaded = (d["title"], d["body"])
            self.title_edit.setText(d["title"])
            self.body_edit.setPlainText(d["body"] or "")
            self.reset_button.setVisible(bool(d["saved"]))
        self._keep_mine()

    def _keep_mine(self) -> None:
        self.warn_bar.hide()
        self._latest = None

    def _check_external(self) -> None:
        d = self._description()
        known = self._latest if self._latest is not None else {"title": self._loaded[0], "body": self._loaded[1]}
        if (d["title"], d["body"]) != (known["title"], known["body"]):
            self._latest = d
            self.warn_bar.show()

    # ---- conversation --------------------------------------------------

    def _add_general(self, text: str) -> None:
        if self.session.add_comment({"kind": "general", "body": text}) is not None:
            self.composer.clear()

    def _sync_threads(self) -> None:
        comments = sorted(self.session.general_comments(), key=lambda c: c["created"])
        ids = {c["id"] for c in comments}
        for cid in [i for i in self._threads if i not in ids]:
            w = self._threads.pop(cid)
            self.threads_box.removeWidget(w)
            w.deleteLater()
        user = (self.session.meta or {}).get("user", "")
        for c in comments:
            existing = self._threads.get(c["id"])
            if existing is not None:
                existing.update_comment(c)
                continue
            w = CommentThread(c, user)
            w.replyRequested.connect(lambda i, text: self.session.reply(i, text))
            w.statusRequested.connect(self.session.set_status)
            w.editRequested.connect(self.session.edit_body)
            w.deleteRequested.connect(self.session.delete_comment)
            self._threads[c["id"]] = w
        for pos, c in enumerate(comments):
            w = self._threads[c["id"]]
            if self.threads_box.indexOf(w) != pos:
                self.threads_box.insertWidget(pos, w)

    # ---- summary -------------------------------------------------------

    def _sync_summary(self) -> None:
        comments = [c for c in self.session.review["comments"] if c["kind"] in ("line", "file")]
        while self.summary_layout.count():
            item = self.summary_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._rows = []
        self.summary.setVisible(bool(comments))
        if not comments:
            return
        open_n = sum(1 for c in comments if c["status"] == "open")
        self.summary_count.setText(f"{open_n} open · {len(comments) - open_n} resolved")
        order = {p: i for i, p in enumerate(tree_order(sorted({c["path"] for c in comments})))}
        comments.sort(key=lambda c: (order[c["path"]], c["status"] != "open", c.get("line") or 0))
        for c in comments:
            row = _SummaryRow(c)
            row.clicked.connect(lambda p=c["path"], i=c["id"]: self.openComment.emit(p, i))
            self.summary_layout.addWidget(row)
            self._rows.append(row)

    # ---- sidebar -------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        box = QWidget()
        box.setMinimumWidth(SIDEBAR_W)
        box.setMaximumWidth(SIDEBAR_W)
        self.side_layout = QVBoxLayout(box)
        self.side_layout.setContentsMargins(0, 0, 0, 0)
        self.side_layout.setSpacing(10)
        self._side_values: dict[str, QLabel] = {}
        for key in ("Target", "Forge", "Base", "Head", "Commits", "Files", "Changes", "Comments"):
            label = QLabel(key)
            label.setStyleSheet(f"color: {NIGHT.muted}; font-size: 12px; font-weight: bold;")
            value = QLabel()
            value.setTextFormat(Qt.TextFormat.RichText)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.side_layout.addWidget(label)
            self.side_layout.addWidget(value)
            self._side_values[key] = value
        self.repo_link = QToolButton()
        self.repo_link.setText("Open repository ↗")
        self.repo_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.repo_link.setStyleSheet(f"QToolButton {{ color: {NIGHT.accent}; border: none; padding: 0; }}")
        self.repo_link.clicked.connect(self._open_repo)
        self.side_layout.insertWidget(4, self.repo_link, 0, Qt.AlignmentFlag.AlignLeft)
        hint = QLabel("When you're ready: <b>Create PR…</b> (toolbar) or <code>premerge pr</code>")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        self.side_layout.addSpacing(6)
        self.side_layout.addWidget(hint)
        return box

    def _open_repo(self) -> None:
        url = (self.session.meta or {}).get("webUrl")
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _sync_sidebar(self) -> None:
        m = self.session.meta or {}
        v = self._side_values
        v["Target"].setText("/".join(x for x in (m.get("remote"), m.get("target")) if x))
        forge = m.get("forge")
        v["Forge"].setText(FORGES.get(forge, "Unknown — set <code>git config premerge.forge</code>"))
        self.repo_link.setVisible(bool(m.get("webUrl")))
        v["Base"].setText(f"{m.get('base', '')} @ {m.get('mergeBase', '')}")
        v["Head"].setText(m.get("head", ""))
        v["Commits"].setText(str(len(self.session.commits)))
        v["Files"].setText(str(len(self.session.files)))
        adds = sum(f["additions"] for f in self.session.files)
        dels = sum(f["deletions"] for f in self.session.files)
        v["Changes"].setText(f'<span style="color:{NIGHT.ok}">+{adds}</span> <span style="color:{NIGHT.bad}">−{dels}</span>')
        comments = self.session.review["comments"]
        open_n = sum(1 for c in comments if c["status"] == "open")
        v["Comments"].setText(f"{open_n} open, {len(comments) - open_n} resolved")

    # ---- refresh / layout ----------------------------------------------

    def refresh(self) -> None:
        """Bring every section up to date with the session."""
        m = self.session.meta or {}
        user = m.get("user", "")
        d = self._description()
        while self.avatar_slot.count():
            item = self.avatar_slot.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.avatar_slot.addWidget(_avatar("you", user))
        self.author_label.setText(user or "You")
        if d["saved"]:
            self.state_label.setText("· description draft")
        else:
            src = d["source"]
            self.state_label.setText("· not saved yet" if src == "nothing" else f"· not saved yet — prefilled from {src}")
        if self._editing:
            self._check_external()
        else:
            self.body_view.set_markdown(d["body"] or "")
        self._sync_threads()
        self._sync_summary()
        self._sync_sidebar()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        narrow = self.width() < NARROW
        want = QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight
        if self._cols.direction() != want:
            self._cols.setDirection(want)
            self.sidebar.setMaximumWidth(MAIN_MAX if narrow else SIDEBAR_W)
