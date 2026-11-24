"""GUI entry point."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
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


def _log_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "premerge.log"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "premerge.log"


def _redirect_output() -> Path | None:
    """A bundled app started from Finder/Spotlight has no terminal: send stdout/stderr to a log file."""
    if not getattr(sys, "frozen", False):
        return None
    if sys.stderr is not None and sys.stderr.isatty():
        return None
    path = _log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        log = open(path, "a", buffering=1, encoding="utf-8", errors="replace")
    except OSError:
        return None
    sys.stdout = sys.stderr = log
    return path


def _report(exc: BaseException, log: Path | None) -> None:
    """Print the traceback and show it in a dialog, so a failure is never silent."""
    text = "".join(traceback.format_exception(exc))
    print(text, file=sys.stderr, flush=True)
    where = f"\n\nDetails were written to {log}" if log else ""
    box = QMessageBox(QMessageBox.Icon.Critical, "premerge", f"premerge hit an error: {exc}{where}")
    box.setDetailedText(text)
    box.exec()


def run_gui(args) -> int:
    """Open the app for the repository named by the parsed CLI `args`."""
    log = _redirect_output()
    _fix_platform_theme()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("premerge")
    app.setOrganizationName("premerge")
    sys.excepthook = lambda t, e, tb: _report(e, log)
    keep: list = []

    def start() -> None:
        # Runs once the event loop is up: on macOS, windows and dialogs shown before the app has
        # finished launching (as happens from Finder/Spotlight) may never appear.
        try:
            path = args.repo
            if args.repo == "." and _launched_from_desktop():
                path = _initial_repo_path()
                if path is None:
                    app.exit(1)
                    return
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
                        app.exit(1)
                        return
                    chosen = QFileDialog.getExistingDirectory(None, "Choose repository", path)
                    if not chosen:
                        app.exit(1)
                        return
                    path = chosen
            _, window, session = create_window(repo)
            keep.append(window)
            window.show()
            window.raise_()
            window.activateWindow()
            session.reload_all()
            session.start()
        except Exception as exc:
            _report(exc, log)
            app.exit(1)

    QTimer.singleShot(0, start)
    return app.exec()
