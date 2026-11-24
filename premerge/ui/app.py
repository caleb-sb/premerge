"""GUI entry point."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from premerge.core.gitrepo import GitError, Repo
from premerge.ui import icons, theme
from premerge.ui.session import Session
from premerge.ui.window import MainWindow


def _fix_platform_theme() -> None:
    """Fall back to the portal theme when the requested Qt platform theme plugin is missing."""
    if not sys.platform.startswith("linux"):
        return
    name = os.environ.get("QT_QPA_PLATFORMTHEME")
    if name:
        import PySide6

        plugins = Path(PySide6.__file__).parent / "Qt" / "plugins" / "platformthemes"
        if not list(plugins.glob(f"*{name}*")):
            os.environ["QT_QPA_PLATFORMTHEME"] = "xdgdesktopportal"
    os.environ.pop("QT_STYLE_OVERRIDE", None)


def create_window(repo: Repo, settings=None) -> tuple[QApplication, MainWindow, Session]:
    """Create (or reuse) the themed QApplication plus a session and main window for `repo`."""
    app = QApplication.instance()
    if app is None:
        _fix_platform_theme()
        app = QApplication(sys.argv[:1])
    app.setApplicationName("premerge")
    app.setOrganizationName("premerge")
    app.setWindowIcon(icons.icon("git_pr", color=theme.NIGHT.accent))
    theme.apply(app)
    session = Session(repo)
    window = MainWindow(session, settings)
    return app, window, session


def _launched_from_desktop() -> bool:
    """True when started as a bundled app (Finder, Spotlight, Dock) rather than from a shell inside a repo."""
    if not getattr(sys, "frozen", False):
        return False
    try:
        Repo(".")
    except GitError:
        return True
    return False


def _initial_repo_path() -> str | None:
    """The most recent repository that still opens, else one the user picks; None when they cancel."""
    recent = QSettings().value("recent", [])
    if isinstance(recent, str):
        recent = [recent]
    for root in recent or []:
        try:
            Repo(root)
            return root
        except GitError:
            continue
    chosen = QFileDialog.getExistingDirectory(None, "Choose a git repository to preview", str(Path.home()))
    return chosen or None


def run_gui(args) -> int:
    """Open the app for the repository named by the parsed CLI `args`."""
    _fix_platform_theme()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("premerge")
    app.setOrganizationName("premerge")
    path = args.repo
    if args.repo == "." and _launched_from_desktop():
        path = _initial_repo_path()
        if path is None:
            return 1
    while True:
        try:
            repo = Repo(path, args.base, args.remote, args.forge)
            break
        except GitError as exc:
            box = QMessageBox(QMessageBox.Icon.Critical, "premerge", str(exc))
            choose = box.addButton("Choose repository…", QMessageBox.ButtonRole.AcceptRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is not choose:
                return 1
            chosen = QFileDialog.getExistingDirectory(None, "Choose repository", path)
            if not chosen:
                return 1
            path = chosen
    _, window, session = create_window(repo)
    window.show()
    session.reload_all()
    session.start()
    return app.exec()
