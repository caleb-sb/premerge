"""Offscreen screenshots for visual review: python tools/shot.py OUT_DIR [--only NAME ...]."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings  # noqa: E402

from premerge.core.gitrepo import Repo  # noqa: E402
from premerge.ui.app import create_window  # noqa: E402
from tests import qt  # noqa: E402
from tests.fixture import isolated_env, make_fixture  # noqa: E402

SHOTS: dict[str, callable] = {}


def shot(name: str):
    """Register a shot function `fn(window, session)`."""
    def deco(fn):
        SHOTS[name] = fn
        return fn
    return deco


@shot("overview")
def _overview(window, session) -> None:
    window.show_tab("overview")


@shot("commits")
def _commits(window, session) -> None:
    window.show_tab("commits")


@shot("files")
def _files(window, session) -> None:
    window.show_tab("files")


@shot("filetree")
def _filetree(window, session):
    from premerge.ui.filetree import FileTree
    tree = FileTree()
    tree.resize(320, 600)
    tree.show()
    paths = [f["path"] for f in session.files]
    tree.set_files(session.files, {paths[0]}, {paths[1]} if len(paths) > 1 else set(),
                   {paths[-1]: 2, paths[min(2, len(paths) - 1)]: 1})
    tree.select_path(paths[min(2, len(paths) - 1)])
    return tree


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--only", nargs="*", default=[])
    args = ap.parse_args(argv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    env = isolated_env()
    os.environ["GIT_CONFIG_GLOBAL"], os.environ["GIT_CONFIG_NOSYSTEM"] = env["GIT_CONFIG_GLOBAL"], "1"
    with tempfile.TemporaryDirectory() as tmp:
        work = make_fixture(Path(tmp) / "fixture")
        settings = QSettings(str(Path(tmp) / "settings.ini"), QSettings.Format.IniFormat)
        app, window, session = create_window(Repo(str(work)), settings)
        window.resize(1440, 900)
        window.show()
        session.reload_all()
        qt.wait_until(lambda: session.meta is not None and not session.busy)
        qt.wait_until(lambda: False, 0.3)
        for name, fn in SHOTS.items():
            if args.only and name not in args.only:
                continue
            target = fn(window, session) or window
            qt.wait_until(lambda: not session.busy)
            qt.wait_until(lambda: False, 0.2)
            path = out / f"{name}.png"
            target.grab().save(str(path))
            print(path)
        session.stop()
        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
