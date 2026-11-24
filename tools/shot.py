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


def _diffview(session, view: str):
    from PySide6.QtWidgets import QLabel, QScrollArea
    from premerge.ui.diffview import DiffBody, row_keys
    f = next(f for f in session.files if f["path"].endswith("app.py"))
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.resize(1100, 700)
    body = DiffBody()
    area.setWidget(body)
    area.show()
    body.set_content(f["path"], f["hunks"], view)
    nums = sorted({int(k[4:]) for r in body.rows() for k in row_keys(r) if k.startswith("new:")})
    a = nums[len(nums) // 2]
    body.set_selection("new", a, a + 1)
    label = QLabel("  Inserted widget slot (a comment thread goes here)")
    label.setStyleSheet("background:#1f2335;padding:8px;")
    body.set_inserts({body.row_index(f"new:{a + 1}"): [label]})
    return area


@shot("diffview-unified")
def _diffview_unified(window, session):
    return _diffview(session, "unified")


@shot("diffview-split")
def _diffview_split(window, session):
    return _diffview(session, "split")


@shot("threads")
def _threads(window, session):
    from PySide6.QtWidgets import QVBoxLayout, QWidget
    from premerge.ui import comments
    from premerge.ui.comments import CommentThread, Composer
    comments.EXPANDED.clear()

    def comment(cid, status, replies):
        return {
            "id": cid, "kind": "line", "body": "Why import `sys` here?\n\n- it looks unused\n- is it for `argv`?",
            "author": "you", "status": status, "created": "2026-11-24T10:00:00Z", "updated": "2026-11-24T10:00:00Z",
            "head": "x", "path": "src/app.py", "oldPath": "src/app.py", "side": "new", "line": 14, "startLine": 12,
            "anchorText": "", "context": [], "replies": replies,
        }

    reply = {"id": "r1", "author": "agent", "created": "2026-11-24T10:05:00Z",
             "body": "Removed it; nothing used `sys`.\n\n1. dropped the import\n2. ran the tests"}
    box = QWidget()
    box.resize(960, 700)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(14)
    lay.addWidget(Composer(label="Commenting on lines 12\u201314"))
    lay.addWidget(CommentThread(comment("abc123", "open", [reply]), "Caleb", show_location=True))
    lay.addWidget(CommentThread(comment("def456", "resolved", [reply]), "Caleb"))
    lay.addStretch(1)
    box.show()
    return box


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
