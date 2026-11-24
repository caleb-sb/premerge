"""Comment thread and composer widgets. They only emit signals; pages wire them to the Session."""

import sys
from datetime import datetime, timezone

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QKeyEvent, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .markdown import MarkdownView
from .theme import NIGHT

EXPANDED: set[str] = set()  # ids of resolved threads the user expanded (survives widget rebuilds)

_AVATAR = 20
_SUBMIT_KEYS = "⌘↩" if sys.platform == "darwin" else "Ctrl+Enter"


def ago(iso: str, now: datetime | None = None) -> str:
    """A short relative time such as "5m ago"; dates older than 30 days read "23 Nov"."""
    when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    secs = (now - when).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    if secs < 30 * 86400:
        return f"{int(secs // 86400)}d ago"
    return f"{when.day} {when:%b}"


def _rgba(color: str, alpha: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {int(alpha * 255)})"


def _blend(fg: str, bg: str, alpha: float) -> str:
    a, b = QColor(fg), QColor(bg)
    mix = [round(x * alpha + y * (1 - alpha)) for x, y in ((a.red(), b.red()), (a.green(), b.green()), (a.blue(), b.blue()))]
    return QColor(*mix).name()


def _avatar(author: str, user_name: str) -> QLabel:
    """A 20 px circle: the user's initial, or the bot icon for the agent."""
    scale = 2
    pix = QPixmap(_AVATAR * scale, _AVATAR * scale)
    pix.setDevicePixelRatio(scale)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(NIGHT.agent if author == "agent" else NIGHT.you))
    painter.drawEllipse(0, 0, _AVATAR, _AVATAR)
    if author == "agent":
        inner = icons.pixmap("bot", NIGHT.on_accent, 12 * scale)
        inner.setDevicePixelRatio(scale)
        painter.drawPixmap(4, 4, inner)
    else:
        font = painter.font()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(NIGHT.on_accent))
        painter.drawText(0, 0, _AVATAR, _AVATAR, Qt.AlignmentFlag.AlignCenter, (user_name[:1] or "Y").upper())
    painter.end()
    label = QLabel()
    label.setPixmap(pix)
    label.setFixedSize(_AVATAR, _AVATAR)
    return label


class _Editor(QPlainTextEdit):
    """Plain text editor that reports Ctrl+Enter, Esc and focus-in."""

    submit = Signal()
    escape = Signal()
    focused = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if enter and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.submit.emit()
        elif event.key() == Qt.Key.Key_Escape:
            self.escape.emit()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.focused.emit()


class Composer(QFrame):
    """A text box with submit/cancel buttons. Does not clear itself after `submitted`."""

    submitted = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        label: str = "",
        placeholder: str = "Leave a comment…",
        submit_text: str = "Comment",
        cancellable: bool = True,
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("thread")
        self._compact = compact
        self._cancellable = cancellable
        self._min_lines = 1 if compact else 3
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        self._label = QLabel(label)
        self._label.setObjectName("muted")
        self._label.setVisible(bool(label))
        layout.addWidget(self._label)

        self._edit = _Editor()
        self._edit.setPlaceholderText("Reply…" if compact else placeholder)
        self._edit.setTabChangesFocus(True)
        layout.addWidget(self._edit)

        self._buttons = QWidget()
        row = QHBoxLayout(self._buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        hint = QLabel(f"{_SUBMIT_KEYS} to submit")
        hint.setStyleSheet(f"color: {NIGHT.muted}; font-size: 11px;")
        row.addWidget(hint)
        row.addStretch(1)
        self._cancel = QPushButton("Cancel")
        self._cancel.setVisible(cancellable)
        self._cancel.clicked.connect(self._on_cancel)
        row.addWidget(self._cancel)
        self._submit = QPushButton(submit_text)
        self._submit.setDefault(True)
        self._submit.setEnabled(False)
        self._submit.clicked.connect(self._on_submit)
        row.addWidget(self._submit)
        layout.addWidget(self._buttons)
        self._buttons.setVisible(not compact)

        self._edit.textChanged.connect(self._on_changed)
        self._edit.document().documentLayout().documentSizeChanged.connect(self._fit)
        self._edit.submit.connect(self._on_submit)
        self._edit.escape.connect(self._on_escape)
        self._edit.focused.connect(self._on_focus)
        self._fit()

    def text(self) -> str:
        return self._edit.toPlainText()

    def set_text(self, s: str) -> None:
        self._edit.setPlainText(s)

    def clear(self) -> None:
        """Empty the editor (compact composers fold their buttons away again)."""
        self._edit.clear()
        if self._compact:
            self._buttons.setVisible(False)

    def focus_editor(self) -> None:
        self._edit.setFocus()

    def set_label(self, s: str) -> None:
        self._label.setText(s)
        self._label.setVisible(bool(s))

    def _fit(self, *_: object) -> None:
        lines = int(self._edit.document().size().height()) if self._edit.document().size().height() >= 1 else 1
        lines = max(self._min_lines, min(12, lines))
        fm = QFontMetrics(self._edit.font())
        pad = int(self._edit.document().documentMargin() * 2) + self._edit.frameWidth() * 2 + 14
        self._edit.setFixedHeight(lines * fm.lineSpacing() + pad)

    def _on_changed(self) -> None:
        has_text = bool(self.text().strip())
        self._submit.setEnabled(has_text)
        if self._compact and has_text:
            self._buttons.setVisible(True)

    def _on_focus(self) -> None:
        if self._compact:
            self._buttons.setVisible(True)

    def _on_submit(self) -> None:
        text = self.text().strip()
        if text:
            self.submitted.emit(text)

    def _on_cancel(self) -> None:
        if self._compact:
            self.clear()
        self.cancelled.emit()

    def _on_escape(self) -> None:
        if self._cancellable:
            self._on_cancel()


class _ElidedLabel(QLabel):
    """A one-line label that elides its text to the available width."""

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        self.setText(QFontMetrics(self.font()).elidedText(self._full, Qt.TextElideMode.ElideRight, max(self.width(), 0)))

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())


class _ClickRow(QFrame):
    """A frame that emits `clicked` on a left click."""

    clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        else:
            super().mousePressEvent(event)


def _tool(icon_name: str, tip: str) -> QToolButton:
    btn = QToolButton()
    btn.setIcon(icons.icon(icon_name, color=NIGHT.muted))
    btn.setIconSize(QSize(14, 14))
    btn.setToolTip(tip)
    btn.setAutoRaise(True)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


class CommentThread(QFrame):
    """One comment with its replies, reply box and resolve/reopen actions."""

    replyRequested = Signal(str, str)
    statusRequested = Signal(str, str)
    editRequested = Signal(str, str)
    deleteRequested = Signal(str)

    def __init__(self, comment: dict, user_name: str = "", show_location: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("thread")
        self.setMaximumWidth(920)
        self._comment = comment
        self._user = user_name
        self._show_location = show_location
        self._edit_box: Composer | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._collapsed = _ClickRow()
        self._collapsed.setCursor(Qt.CursorShape.PointingHandCursor)
        self._collapsed.clicked.connect(self._expand)
        QHBoxLayout(self._collapsed).setContentsMargins(10, 7, 10, 7)
        outer.addWidget(self._collapsed)

        self._entries = QWidget()
        self._entries_layout = QVBoxLayout(self._entries)
        self._entries_layout.setContentsMargins(0, 0, 0, 0)
        self._entries_layout.setSpacing(0)
        outer.addWidget(self._entries)

        self._foot = QFrame()
        self._foot.setObjectName("threadFoot")
        foot = QHBoxLayout(self._foot)
        foot.setContentsMargins(10, 8, 10, 8)
        foot.setSpacing(8)
        self._reply = Composer(compact=True, cancellable=True, submit_text="Reply")
        self._reply.setStyleSheet("QFrame#thread { border: none; background: transparent; }")
        self._reply.layout().setContentsMargins(0, 0, 0, 0)
        self._reply.submitted.connect(lambda text: self.replyRequested.emit(self._comment["id"], text))
        foot.addWidget(self._reply, 1)
        side = QVBoxLayout()
        side.setSpacing(4)
        self._status_btn = QPushButton()
        self._status_btn.clicked.connect(self._toggle_status)
        side.addWidget(self._status_btn)
        self._collapse_btn = QToolButton()
        self._collapse_btn.setText("Collapse")
        self._collapse_btn.setAutoRaise(True)
        self._collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._collapse_btn.setStyleSheet(f"QToolButton {{ color: {NIGHT.accent}; }}")
        self._collapse_btn.clicked.connect(self._collapse)
        side.addWidget(self._collapse_btn)
        side.addStretch(1)
        foot.addLayout(side)
        outer.addWidget(self._foot)

        self._render()

    def comment_id(self) -> str:
        return self._comment["id"]

    def reply_draft(self) -> str:
        return self._reply.text()

    def update_comment(self, comment: dict) -> None:
        """Refresh in place, keeping the reply draft, its focus and any open edit."""
        self._comment = comment
        self._render()

    def _is_collapsed(self) -> bool:
        return self._comment["status"] == "resolved" and self._comment["id"] not in EXPANDED

    def _expand(self) -> None:
        EXPANDED.add(self._comment["id"])
        self._render()

    def _collapse(self) -> None:
        EXPANDED.discard(self._comment["id"])
        self._render()

    def _toggle_status(self) -> None:
        target = "open" if self._comment["status"] == "resolved" else "resolved"
        self.statusRequested.emit(self._comment["id"], target)

    def _author_name(self, author: str) -> str:
        if author == "agent":
            return "Agent"
        return self._user or "You"

    @staticmethod
    def _clear(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                CommentThread._clear(item.layout())

    def _render(self) -> None:
        c = self._comment
        collapsed = self._is_collapsed()
        self._collapsed.setVisible(collapsed)
        self._entries.setVisible(not collapsed)
        self._foot.setVisible(not collapsed)
        if collapsed:
            self._fill_collapsed()
            return
        draft = self._edit_box.text() if self._edit_box is not None else None
        self._edit_box = None
        self._clear(self._entries_layout)
        for index, entry in enumerate([c, *c.get("replies", [])]):
            self._entries_layout.addWidget(self._entry(entry, root=index == 0))
        if draft is not None:
            self._start_edit(draft)
        resolved = c["status"] == "resolved"
        self._status_btn.setText("Reopen" if resolved else "Resolve")
        self._collapse_btn.setVisible(resolved)

    def _fill_collapsed(self) -> None:
        c = self._comment
        layout = self._collapsed.layout()
        self._clear(layout)
        self._collapsed.setObjectName("collapsedRow")
        self._collapsed.setStyleSheet("QFrame#collapsedRow { background: transparent; border: none; }")
        icon = QLabel()
        icon.setPixmap(icons.pixmap("valid", NIGHT.ok, 16))
        layout.addWidget(icon)
        title = QLabel("Resolved")
        title.setStyleSheet(f"color: {NIGHT.ok}; font-weight: bold;")
        layout.addWidget(title)
        first = (c["body"].strip().splitlines() or [""])[0]
        snippet = _ElidedLabel(first)
        snippet.setStyleSheet(f"color: {NIGHT.fg_dark};")
        layout.addWidget(snippet, 1)
        replies = c.get("replies", [])
        meta = []
        if replies:
            meta.append(f"{len(replies)} {'reply' if len(replies) == 1 else 'replies'}")
            meta.append(self._author_name(replies[-1]["author"]))
        else:
            meta.append(self._author_name(c["author"]))
        tail = QLabel("· " + " · ".join(meta))
        tail.setObjectName("muted")
        layout.addWidget(tail)

    def _location(self) -> str:
        c = self._comment
        if c["kind"] != "line":
            return c.get("path", "") if c["kind"] == "file" else ""
        start = c.get("startLine", c["line"])
        span = str(c["line"]) if start == c["line"] else f"{start}–{c['line']}"
        return f"{c['path']}:{span}"

    def _entry(self, entry: dict, root: bool) -> QFrame:
        c = self._comment
        author = entry["author"]
        frame = QFrame()
        frame.setObjectName("entry")
        bg = _blend(NIGHT.agent, NIGHT.bg, 0.08) if author == "agent" else "transparent"
        top = "none" if root else f"1px solid {NIGHT.border}"
        frame.setStyleSheet(f"QFrame#entry {{ background: {bg}; border: none; border-top: {top}; }}")
        col = QVBoxLayout(frame)
        col.setContentsMargins(10, 8, 10, 10)
        col.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(_avatar(author, self._user))
        name = QLabel(self._author_name(author))
        name.setStyleSheet("font-weight: bold;")
        head.addWidget(name)
        when = QLabel(ago(entry["created"]))
        when.setObjectName("muted")
        head.addWidget(when)
        if root and self._show_location and self._location():
            where = QLabel(self._location())
            where.setObjectName("muted")
            head.addWidget(where)
        if root and c["status"] == "resolved":
            pill = QLabel("Resolved")
            pill.setStyleSheet(
                f"background: {_rgba(NIGHT.ok, 0.15)}; color: {NIGHT.ok}; border-radius: 9px; padding: 1px 8px;"
            )
            head.addWidget(pill)
        head.addStretch(1)
        body = MarkdownView()
        body.set_markdown(entry["body"])
        if root:
            if author == "you":
                edit = _tool("pencil", "Edit")
                edit.clicked.connect(lambda: self._start_edit(c["body"]))
                head.addWidget(edit)
            delete = _tool("trash", "Delete")
            delete.clicked.connect(self._confirm_delete)
            head.addWidget(delete)
            self._root_body = body
        col.addLayout(head)
        body_row = QHBoxLayout()
        body_row.setContentsMargins(_AVATAR + 8, 0, 0, 0)
        body_row.addWidget(body)
        col.addLayout(body_row)
        return frame

    def _confirm_delete(self) -> None:
        answer = QMessageBox.question(self, "Delete comment", "Delete this comment and its replies?")
        if answer == QMessageBox.StandardButton.Yes:
            self.deleteRequested.emit(self._comment["id"])

    def _start_edit(self, text: str) -> None:
        if self._edit_box is None:
            box = Composer(placeholder="Edit comment…", submit_text="Save")
            box.setStyleSheet("QFrame#thread { border: none; background: transparent; }")
            box.layout().setContentsMargins(0, 0, 0, 0)
            box.submitted.connect(self._save_edit)
            box.cancelled.connect(self._cancel_edit)
            self._root_body.setVisible(False)
            self._root_body.parentWidget().layout().addWidget(box)
            self._edit_box = box
            box.set_text(text)
            box.focus_editor()

    def _save_edit(self, text: str) -> None:
        self._cancel_edit()
        self.editRequested.emit(self._comment["id"], text)

    def _cancel_edit(self) -> None:
        self._edit_box = None
        self._render()
