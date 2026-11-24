"""Create PR/MR dialog and the agent-prompt viewer."""
from __future__ import annotations

import re
from html import escape

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)

from premerge.core import publish
from premerge.ui import jobs, theme
from premerge.ui.session import Session

URL_RE = re.compile(r"https://\S+")


def _mono(read_only: bool = True) -> QPlainTextEdit:
    box = QPlainTextEdit()
    box.setReadOnly(read_only)
    box.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
    box.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
    return box


class PromptDialog(QDialog):
    """Shows the agent prompt in a read-only monospace box with a Copy button."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Agent prompt")
        self.resize(820, 620)
        lay = QVBoxLayout(self)
        self.edit = _mono()
        self.edit.setPlainText(text)
        lay.addWidget(self.edit, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(text))
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(self.copy_button)
        row.addWidget(close)
        lay.addLayout(row)


class _Relay(QObject):
    """Carries worker-thread output to the GUI thread."""

    output = Signal(str)


class CreatePrDialog(QDialog):
    """Plan, confirm and run the PR/MR creation. Nothing runs until the user clicks Create."""

    def __init__(self, session: Session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self._t = theme.NIGHT
        self._gen = 0
        self.plan: publish.PrPlan | None = None
        self.url: str | None = None
        self._log_text = ""
        self._relay = _Relay(self)
        self._relay.output.connect(self._append_log)
        noun = "merge request" if session.repo.remote_info()["forge"] == "gitlab" else "pull request"
        self.setWindowTitle(f"Create {noun}")
        self.resize(680, 520)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        self.info = QLabel("Checking…")
        self.info.setTextFormat(Qt.TextFormat.RichText)
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.warn_label = QLabel()
        self.warn_label.setTextFormat(Qt.TextFormat.RichText)
        self.warn_label.setWordWrap(True)
        lay.addWidget(self.warn_label)
        self.problems_label = QLabel()
        self.problems_label.setTextFormat(Qt.TextFormat.RichText)
        self.problems_label.setWordWrap(True)
        lay.addWidget(self.problems_label)
        self.commands = _mono()
        self.commands.setMaximumHeight(110)
        lay.addWidget(self.commands)

        opts = QHBoxLayout()
        self.draft_box = QCheckBox("Draft")
        self.push_box = QCheckBox("Push branch first")
        self.push_box.setChecked(True)
        opts.addWidget(self.draft_box)
        opts.addWidget(self.push_box)
        opts.addStretch(1)
        lay.addLayout(opts)
        self.draft_box.toggled.connect(self.replan)
        self.push_box.toggled.connect(self.replan)

        self.log = _mono()
        self.log.hide()
        lay.addWidget(self.log, 1)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.RichText)
        self.status.hide()
        lay.addWidget(self.status)
        links = QHBoxLayout()
        self.open_button = QPushButton("Open")
        self.copy_link_button = QPushButton("Copy link")
        self.open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.url or "")))
        self.copy_link_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.url or ""))
        links.addWidget(self.open_button)
        links.addWidget(self.copy_link_button)
        links.addStretch(1)
        self.links = QWidget()
        self.links.setLayout(links)
        self.links.hide()
        lay.addWidget(self.links)
        lay.addStretch(0)

        self.buttons = QDialogButtonBox()
        self.cancel_button = self.buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.create_button = self.buttons.addButton("Create", QDialogButtonBox.ButtonRole.AcceptRole)
        self.close_button = self.buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.close_button.hide()
        self.create_button.setDefault(True)
        self.create_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.reject)
        self.close_button.clicked.connect(self.accept)
        self.create_button.clicked.connect(self.create)
        lay.addWidget(self.buttons)
        self.replan()

    # ---- planning ------------------------------------------------------

    def replan(self) -> None:
        """Recompute the plan in a job."""
        self._gen += 1
        gen = self._gen
        self.create_button.setEnabled(False)
        self.info.setText("Checking…")
        draft, push = self.draft_box.isChecked(), self.push_box.isChecked()
        jobs.run(publish.plan, self.session.repo, self.session.store, draft, push,
                 on_done=lambda p: self._planned(gen, p), on_error=lambda e: self._plan_failed(gen, e))

    def _plan_failed(self, gen: int, exc: Exception) -> None:
        if gen == self._gen:
            self.info.setText(f"<span style='color:{self._t.bad}'>{escape(str(exc))}</span>")

    def _planned(self, gen: int, plan: publish.PrPlan) -> None:
        if gen != self._gen:
            return
        t = self._t
        self.plan = plan
        self.info.setText(
            f"<div style='font-size:16px'><b>{escape(plan.title)}</b></div>"
            f"<div style='color:{t.muted}'>into <b>{escape(plan.target)}</b> from <b>{escape(plan.branch)}</b>"
            f" on <b>{escape(plan.remote or '—')}</b></div>"
            f"<div style='color:{t.muted}'>Description from {escape(plan.source or 'the review')} · "
            f"{len(plan.body)} characters</div>")
        n = plan.open_comments
        self.warn_label.setText(
            f"<span style='color:{t.warn}'>{n} review comment{'' if n == 1 else 's'} "
            f"{'is' if n == 1 else 'are'} still open</span>" if n else "")
        self.problems_label.setText("".join(
            f"<div style='color:{t.bad}'>• {escape(p)}</div>" for p in plan.problems))
        self.commands.setPlainText("\n".join(plan.display))
        self.create_button.setEnabled(not plan.problems)

    # ---- running -------------------------------------------------------

    def create(self) -> None:
        """Run the plan (only ever called from the user's click on Create)."""
        plan = self.plan
        if plan is None or plan.problems:
            return
        for w in (self.info, self.warn_label, self.problems_label, self.commands,
                  self.draft_box, self.push_box, self.create_button, self.cancel_button):
            w.hide()
        self.log.show()
        self.status.setText(f"<span style='color:{self._t.muted}'>Creating…</span>")
        self.status.show()
        jobs.run(publish.execute, plan, self.session.repo.root, self._relay.output.emit,
                 on_done=self._finished, on_error=self._execute_failed)

    def _append_log(self, text: str) -> None:
        self._log_text += text
        self.log.setPlainText(self._log_text)

    def _execute_failed(self, exc: Exception) -> None:
        self._finished((1, str(exc)))

    def _finished(self, result: tuple[int, str]) -> None:
        code, text = result
        if text and text != self._log_text:
            self._append_log(text)
        match = URL_RE.search(text) if code == 0 else None
        if code == 0 and match:
            self.url = match.group(0)
            self.status.setText(f"<span style='color:{self._t.ok}'>Created: {escape(self.url)}</span>")
            self.links.show()
        elif code == 0:
            self.status.setText(f"<span style='color:{self._t.ok}'>Created</span>")
        else:
            self.status.setText(f"<span style='color:{self._t.bad}'>Failed (exit {code})</span>")
        self.close_button.show()
        self.close_button.setDefault(True)
