"""GUI entry point."""
from __future__ import annotations

import os
import sys
from pathlib import Path

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


def run_gui(args) -> int:
    """Open the app for the repository named by the parsed CLI `args`."""
    _fix_platform_theme()
    app = QApplication(sys.argv[:1])
    path = args.repo
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
