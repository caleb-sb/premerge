"""The Commits tab."""
from __future__ import annotations

from datetime import date, datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea, QToolButton, QVBoxLayout,
                               QWidget)

from premerge.ui import icons


def ago(when: datetime, now: datetime | None = None) -> str:
    """Human 'time ago' text."""
    secs = int(((now or datetime.now(timezone.utc)) - when).total_seconds())
    if secs < 60:
        return "just now"
    for size, unit in ((86400 * 365, "year"), (86400 * 30, "month"), (86400 * 7, "week"),
                       (86400, "day"), (3600, "hour"), (60, "minute")):
        if secs >= size:
            n = secs // size
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "just now"


class CommitRow(QFrame):
    """One commit card."""

    def __init__(self, commit: dict, when: datetime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.commit = commit
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 10, 10)
        outer.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(2)
        subject = QLabel(commit["subject"])
        subject.setStyleSheet("font-weight: 600;")
        subject.setWordWrap(True)
        meta = QLabel(f"{commit['author']} committed {ago(when)}")
        meta.setObjectName("muted")
        text.addWidget(subject)
        text.addWidget(meta)
        top.addLayout(text, 1)
        self.body_label: QLabel | None = None
        if commit.get("body", "").strip():
            self.toggle = QToolButton()
            self.toggle.setIcon(icons.icon("chevron_down"))
            self.toggle.setToolTip("Show description")
            self.toggle.setCheckable(True)
            self.toggle.toggled.connect(self._toggle_body)
            top.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignTop)
            self.body_label = QLabel(commit["body"].strip())
            self.body_label.setObjectName("muted")
            self.body_label.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
            self.body_label.setWordWrap(True)
            self.body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.body_label.hide()
        self.sha_button = QToolButton()
        self.sha_button.setText(commit["short"])
        self.sha_button.setToolTip("Copy full SHA")
        self.sha_button.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.sha_button.clicked.connect(self._copy)
        top.addWidget(self.sha_button, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(top)
        if self.body_label:
            outer.addWidget(self.body_label)

    def _toggle_body(self, on: bool) -> None:
        self.body_label.setVisible(on)
        self.toggle.setIcon(icons.icon("chevron_down"))

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.commit["sha"])
        win = self.window()
        bar = getattr(win, "statusBar", None)
        if bar:
            bar().showMessage("Copied", 3000)


class CommitsPage(QScrollArea):
    """Commits grouped by local date."""

    MAX_WIDTH = 1000

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.rows: list[CommitRow] = []
        self._holder = QWidget()
        self.setWidget(self._holder)
        outer = QHBoxLayout(self._holder)
        outer.setContentsMargins(24, 20, 24, 24)
        self._col = QWidget()
        self._col.setMaximumWidth(self.MAX_WIDTH)
        self._layout = QVBoxLayout(self._col)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        outer.addWidget(self._col, 100, Qt.AlignmentFlag.AlignTop)
        outer.addStretch(1)

    def set_commits(self, commits: list[dict]) -> None:
        """Replace the list."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.rows = []
        if not commits:
            empty = QLabel("No commits on this branch yet.")
            empty.setObjectName("muted")
            self._layout.addWidget(empty)
            return
        current: date | None = None
        for c in commits:
            when = datetime.fromisoformat(c["date"])
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            day = when.astimezone().date()
            if day != current:
                current = day
                head = QLabel(f"Commits on {day.day} {day:%b %Y}")
                head.setObjectName("muted")
                head.setContentsMargins(0, 8 if self.rows else 0, 0, 0)
                self._layout.addWidget(head)
            row = CommitRow(c, when)
            self.rows.append(row)
            self._layout.addWidget(row)
