"""The main window: toolbar, PR header, tabs, status bar and menus."""
from __future__ import annotations

import importlib.metadata
from datetime import datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
                               QSizePolicy, QStackedWidget, QTabBar, QToolButton, QVBoxLayout, QWidget)

from premerge.core import prompt
from premerge.core.gitrepo import GitError, Repo
from premerge.ui import icons, theme
from premerge.ui.commits import CommitsPage
from premerge.ui.filepage import FilesPage
from premerge.ui.overview import OverviewPage
from premerge.ui.prdialog import CreatePrDialog, PromptDialog
from premerge.ui.session import Session

TABS = ("overview", "commits", "files")
RECENT_MAX = 8
_windows: list["MainWindow"] = []


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class MainWindow(QMainWindow):
    """premerge's top-level window."""

    def __init__(self, session: Session, settings: QSettings | None = None) -> None:
        super().__init__()
        self.session = session
        self.settings = settings or QSettings()
        self._t = theme.NIGHT
        self._branch: str | None = None
        self.setWindowTitle("premerge")
        self.resize(1440, 900)
        self._build_toolbar()
        self._build_central()
        self._build_status()
        self._build_menus()

        session.metaChanged.connect(self.refresh_meta)
        session.filesChanged.connect(self.refresh_files)
        session.commitsChanged.connect(self.refresh_commits)
        session.reviewChanged.connect(self.refresh_review)
        session.busyChanged.connect(self.refresh_busy)
        session.modeChanged.connect(self._sync_mode)
        session.viewChanged.connect(self._sync_view)
        session.error.connect(self._show_error)

        self._restore()
        self._remember_recent(session.repo.root)
        self.refresh_meta()
        self.refresh_files()
        self.refresh_commits()
        self.refresh_review()

    # ---- construction --------------------------------------------------

    def _segment(self, specs: list[tuple[str, str | None, str]]) -> tuple[QFrame, dict[str, QToolButton]]:
        """A QFrame#segment of exclusive checkable buttons: (key, icon, text)."""
        frame = QFrame()
        frame.setObjectName("segment")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        buttons: dict[str, QToolButton] = {}
        for key, icon_name, text in specs:
            b = QToolButton()
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setText(text)
            if icon_name:
                b.setIcon(icons.icon(icon_name))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if icon_name
                                 else Qt.ToolButtonStyle.ToolButtonTextOnly)
            lay.addWidget(b)
            buttons[key] = b
        return frame, buttons

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main")
        tb.setObjectName("main")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        tb.setIconSize(QSize(18, 18))

        branch_icon = QLabel()
        branch_icon.setPixmap(icons.pixmap("git_branch", self._t.muted, 18))
        self.repo_label = QLabel()
        self.repo_label.setTextFormat(Qt.TextFormat.RichText)
        tb.addWidget(branch_icon)
        tb.addWidget(self.repo_label)
        tb.addSeparator()

        seg, self.mode_buttons = self._segment(
            [("committed", None, "Committed"), ("worktree", None, "+ Working tree")])
        tb.addWidget(seg)
        for key, b in self.mode_buttons.items():
            b.clicked.connect(lambda _=False, k=key: self.session.set_mode(k))
        spacer = QWidget()
        spacer.setFixedWidth(6)
        tb.addWidget(spacer)
        seg2, self.view_buttons = self._segment(
            [("unified", "rows", "Unified"), ("split", "columns", "Split")])
        tb.addWidget(seg2)
        for key, b in self.view_buttons.items():
            b.clicked.connect(lambda _=False, k=key: self.session.set_view(k))

        self.refresh_button = QToolButton()
        self.refresh_button.setIcon(icons.icon("refresh"))
        self.refresh_button.setToolTip("Reload (Ctrl+R)")
        self.refresh_button.clicked.connect(self.session.reload_all)
        tb.addWidget(self.refresh_button)

        stretch = QWidget()
        stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(stretch)

        self.agent_button = QToolButton()
        self.agent_button.setIcon(icons.icon("copy"))
        self.agent_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.agent_button.setToolTip("Copy the open comments as a prompt for your coding agent")
        self.agent_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.agent_button.clicked.connect(lambda: self.copy_agent_prompt())
        agent_menu = QMenu(self.agent_button)
        agent_menu.addAction("Copy prompt including resolved").triggered.connect(
            lambda: self.copy_agent_prompt(include_all=True))
        agent_menu.addAction("Show prompt…").triggered.connect(self.show_prompt)
        agent_menu.addAction("Copy agent instructions").triggered.connect(self.copy_agent_instructions)
        self.agent_button.setMenu(agent_menu)
        tb.addWidget(self.agent_button)

        self.create_pr_button = QToolButton()
        self.create_pr_button.setObjectName("primary")
        self.create_pr_button.setText("Create PR…")
        self.create_pr_button.setIcon(icons.icon("git_pr", color=self._t.on_accent))
        self.create_pr_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.create_pr_button.setToolTip("Push this branch and create the pull request (Ctrl+Shift+Enter)")
        self.create_pr_button.clicked.connect(self.create_pr)
        tb.addWidget(self.create_pr_button)

    def _build_central(self) -> None:
        central = QWidget()
        col = QVBoxLayout(central)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        header = QWidget()
        hl = QVBoxLayout(header)
        hl.setContentsMargins(24, 16, 24, 0)
        hl.setSpacing(6)
        self.title_label = QLabel()
        self.title_label.setObjectName("h1")
        self.title_label.setWordWrap(True)
        hl.addWidget(self.title_label)
        row = QHBoxLayout()
        row.setSpacing(10)
        chip = QLabel("Local preview")
        chip.setObjectName("chip")
        self.summary_label = QLabel()
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(chip)
        row.addWidget(self.summary_label, 1)
        hl.addLayout(row)
        col.addWidget(header)

        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(24, 4, 24, 0)
        self.tab_bar = QTabBar()
        self.tab_bar.setDocumentMode(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        for name in ("Overview", "Commits", "Files changed"):
            self.tab_bar.addTab(name)
        self.tab_bar.currentChanged.connect(self._tab_changed)
        self.totals_label = QLabel()
        self.totals_label.setTextFormat(Qt.TextFormat.RichText)
        tab_row.addWidget(self.tab_bar)
        tab_row.addStretch(1)
        tab_row.addWidget(self.totals_label)
        col.addLayout(tab_row)
        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {self._t.border};")
        col.addWidget(rule)

        self.stack = QStackedWidget()
        self.overview_page = self._make_overview()
        self.commits_page = CommitsPage()
        self.files_page = self._make_files()
        for page in (self.overview_page, self.commits_page, self.files_page):
            self.stack.addWidget(page)
        col.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    def _make_overview(self) -> QWidget:
        page = OverviewPage(self.session)
        page.openComment.connect(self.show_file)
        return page

    def _make_files(self) -> QWidget:
        return FilesPage(self.session, self.settings)

    def _build_status(self) -> None:
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        self.status_left = QLabel()
        self.status_right = QLabel()
        self.status_error = QLabel()
        self.status_error.setStyleSheet(f"color: {self._t.bad};")
        bar.addWidget(self.status_left)
        bar.addWidget(self.status_error)
        bar.addPermanentWidget(self.status_right)

    def _build_menus(self) -> None:
        mb = self.menuBar()
        file_menu = mb.addMenu("&File")
        self.open_action = file_menu.addAction("Open Repository…")
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_repository)
        self.recent_menu = file_menu.addMenu("Open Recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("Quit")
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.triggered.connect(self.close)
        self.create_action = file_menu.addAction("Create Pull Request…")
        self.create_action.setShortcut(QKeySequence("Ctrl+Shift+Return"))
        self.create_action.triggered.connect(self.create_pr)

        view = mb.addMenu("&View")
        self.mode_actions: dict[str, QAction] = {}
        self.view_actions: dict[str, QAction] = {}
        for actions, group_specs, setter in (
            (self.mode_actions, [("committed", "Committed"), ("worktree", "Working tree")],
             self.session.set_mode),
            (self.view_actions, [("unified", "Unified"), ("split", "Split")], self.session.set_view),
        ):
            group = QActionGroup(self)
            for key, text in group_specs:
                a = view.addAction(text)
                a.setCheckable(True)
                group.addAction(a)
                a.triggered.connect(lambda _=False, k=key, s=setter: s(k))
                actions[key] = a
            view.addSeparator()
        reload_action = view.addAction("Reload")
        reload_action.setShortcuts([QKeySequence.StandardKey.Refresh, QKeySequence("Ctrl+R")])
        reload_action.triggered.connect(self.session.reload_all)
        self.addAction(reload_action)

        go = mb.addMenu("&Go")
        for i, (name, text) in enumerate(zip(TABS, ("Overview", "Commits", "Files changed")), 1):
            a = go.addAction(text)
            a.setShortcut(QKeySequence(f"Ctrl+{i}"))
            a.triggered.connect(lambda _=False, n=name: self.show_tab(n))
        go.addSeparator()
        for text, key, delta in (("Next File", "Alt+Down", 1), ("Previous File", "Alt+Up", -1)):
            a = go.addAction(text)
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(lambda _=False, d=delta: self.step_file(d))

        about = mb.addMenu("&Help").addAction("About premerge")
        about.setMenuRole(QAction.MenuRole.AboutRole)
        about.triggered.connect(self.show_about)

    def step_file(self, delta: int) -> None:
        """Show the next (1) or previous (-1) changed file."""
        self.show_tab("files")
        self.files_page.step(delta)

    def show_file(self, path: str, comment_id: str | None = None) -> None:
        """Open the Files tab on `path`, optionally flashing a comment thread."""
        self.show_tab("files")
        self.files_page.show_file(path, comment_id)

    # ---- state ---------------------------------------------------------

    def show_tab(self, name: str) -> None:
        """Switch to "overview", "commits" or "files"."""
        self.tab_bar.setCurrentIndex(TABS.index(name))

    def _tab_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

    def _choose_directory(self) -> str:
        """Ask for a repository directory ("" if cancelled); overridable in tests."""
        return QFileDialog.getExistingDirectory(self, "Open repository", self.session.repo.root)

    def open_repository(self) -> None:
        """Pick a directory and open it in a new window, closing this one."""
        path = self._choose_directory()
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> bool:
        """Open the repository at `path` in a new window; show the error and return False if it isn't one."""
        try:
            repo = Repo(path)
        except GitError as exc:
            QMessageBox.warning(self, "premerge", str(exc))
            return False
        session = Session(repo)
        window = MainWindow(session, self.settings)
        _windows.append(window)
        window.show()
        session.reload_all()
        session.start()
        self.close()
        return True

    def _recent(self) -> list[str]:
        value = self.settings.value("recent", [])
        return [value] if isinstance(value, str) else [str(v) for v in value or []]

    def _remember_recent(self, root: str) -> None:
        recent = [root] + [r for r in self._recent() if r != root]
        self.settings.setValue("recent", recent[:RECENT_MAX])

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        recent = [r for r in self._recent() if r != self.session.repo.root]
        for root in recent:
            self.recent_menu.addAction(root).triggered.connect(lambda _=False, r=root: self.open_path(r))
        self.recent_menu.setEnabled(bool(recent))

    def create_pr(self) -> None:
        """Open the Create PR/MR dialog (nothing runs until the user clicks Create there)."""
        self._dialog = CreatePrDialog(self.session, self)
        self._dialog.open()

    def copy_agent_prompt(self, include_all: bool = False) -> None:
        """Copy the agent prompt (open comments, or everything) to the clipboard."""
        n = self.session.open_count()
        QGuiApplication.clipboard().setText(
            prompt.render_prompt(self.session.repo, self.session.store.load(), include_all=include_all))
        self.statusBar().showMessage(
            f"Copied {_plural(n, 'comment')} \u2014 paste into your agent, or run `premerge comments` there", 6000)

    def show_prompt(self) -> None:
        """Show the agent prompt in a dialog."""
        self._dialog = PromptDialog(self.session.prompt_text(), self)
        self._dialog.open()

    def copy_agent_instructions(self) -> None:
        """Copy a one-paragraph instruction telling an agent how to use the CLI."""
        cli = prompt.cli_cmd()
        QGuiApplication.clipboard().setText(
            f'Run `{cli} comments` in {self.session.repo.root}, address each comment, then reply with '
            f'`{cli} reply <id> --resolve "\u2026"`.')
        self.statusBar().showMessage("Copied agent instructions", 4000)

    def show_about(self) -> None:
        """Show the About box."""
        try:
            version = importlib.metadata.version("premerge")
        except importlib.metadata.PackageNotFoundError:
            version = "dev"
        QMessageBox.about(self, "About premerge",
                          f"<b>premerge</b> {escape(version)}<br>Preview your branch as a pull request.")

    def _sync_mode(self, mode: str) -> None:
        self.mode_buttons[mode].setChecked(True)
        self.mode_actions[mode].setChecked(True)
        self.refresh_meta()

    def _sync_view(self, view: str) -> None:
        self.view_buttons[view].setChecked(True)
        self.view_actions[view].setChecked(True)

    def _show_error(self, msg: str) -> None:
        self.status_error.setText(msg)
        QTimer.singleShot(8000, lambda: self.status_error.clear() if self.status_error.text() == msg else None)

    # ---- refresh -------------------------------------------------------

    def refresh_meta(self) -> None:
        """Update toolbar, header and status line from session.meta."""
        m = self.session.meta
        t = self._t
        self.mode_buttons[self.session.mode].setChecked(True)
        self.mode_actions[self.session.mode].setChecked(True)
        self.view_buttons[self.session.view].setChecked(True)
        self.view_actions[self.session.view].setChecked(True)
        if not m:
            return
        if self._branch is not None and m["branch"] != self._branch:
            self.statusBar().showMessage(f"Switched to {m['branch']}", 6000)
        self._branch = m["branch"]
        self.create_pr_button.setText("Create MR…" if m["forge"] == "gitlab" else "Create PR…")
        self.repo_label.setText(
            f"<b>{escape(m['repo'])}</b> &nbsp;<span style='color:{t.accent}'>{escape(m['branch'])}</span>"
            f" → <span style='color:{t.accent}'>{escape(m['target'])}</span>")
        text = (f"{escape(m['user'] or 'Someone')} wants to merge {_plural(m['ahead'], 'commit')} "
                f"into {escape(m['target'])} from {escape(m['branch'])}")
        html = f"<span style='color:{t.muted}'>{text}</span>"
        if m["behind"] > 0:
            html += (f"<span style='color:{t.warn}'> · {escape(m['target'])} is "
                     f"{_plural(m['behind'], 'commit')} ahead — consider rebasing</span>")
        if self.session.mode == "committed" and m["dirty"]:
            html += f"<span style='color:{t.muted}'> · uncommitted changes not shown</span>"
        self.summary_label.setText(html)
        self.status_left.setText(f"base {m['base']} @ {m['mergeBase']} · HEAD {m['head']}")

    def refresh_review(self) -> None:
        """Update the title, and the open-comment count."""
        desc = self.session.review.get("description")
        title = desc["title"] if desc else (self.session.meta or {}).get("branch", "")
        self.title_label.setText(title)
        repo = (self.session.meta or {}).get("repo", "")
        self.setWindowTitle(" \u2014 ".join(p for p in (title, repo, "premerge") if p))
        n = self.session.open_count()
        self.agent_button.setText(f"Agent prompt · {n}" if n else "Agent prompt")

    def refresh_files(self) -> None:
        """Update the Files tab label and totals."""
        files = self.session.files
        self.tab_bar.setTabText(2, f"Files changed  {len(files)}")
        add = sum(f["additions"] for f in files)
        dele = sum(f["deletions"] for f in files)
        self.totals_label.setText(
            f"<span style='color:{self._t.ok}'>+{add}</span> "
            f"<span style='color:{self._t.bad}'>−{dele}</span>")

    def refresh_commits(self) -> None:
        """Update the Commits tab label and list."""
        self.tab_bar.setTabText(1, f"Commits  {len(self.session.commits)}")
        self.commits_page.set_commits(self.session.commits)

    def refresh_busy(self, busy: bool) -> None:
        """Show Refreshing… or the last refresh time."""
        if busy:
            self.status_right.setText("Refreshing…")
        else:
            last = self.session.last_refresh or datetime.now()
            self.status_right.setText(f"Refreshed {last:%H:%M:%S}")

    # ---- persistence ---------------------------------------------------

    def _restore(self) -> None:
        s = self.settings
        geo = s.value("geometry")
        if isinstance(geo, (QByteArray, bytes)):
            self.restoreGeometry(geo)
        tab = s.value("tab", "overview")
        self.show_tab(tab if tab in TABS else "overview")
        mode = s.value("mode", "committed")
        view = s.value("view", "unified")
        self.session.mode = mode if mode in ("committed", "worktree") else "committed"
        self.session.view = view if view in ("unified", "split") else "unified"
        self.mode_buttons[self.session.mode].setChecked(True)
        self.mode_actions[self.session.mode].setChecked(True)
        self.view_buttons[self.session.view].setChecked(True)
        self.view_actions[self.session.view].setChecked(True)

    def closeEvent(self, event) -> None:
        s = self.settings
        s.setValue("geometry", self.saveGeometry())
        s.setValue("tab", TABS[self.tab_bar.currentIndex()])
        s.setValue("mode", self.session.mode)
        s.setValue("view", self.session.view)
        s.sync()
        self.session.stop()
        super().closeEvent(event)
