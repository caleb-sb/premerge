"""End-to-end agent loop: comment in the app, read it via the CLI, fix and reply as the agent."""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from tests import qt
from tests.base import FixtureCase
from tests.fixture import isolated_env

qt.app()

from premerge.core.gitrepo import Repo  # noqa: E402
from premerge.ui.app import create_window  # noqa: E402
from premerge.ui.comments import CommentThread  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class AgentLoopTests(FixtureCase):
    def setUp(self) -> None:
        self._cfg = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self._cfg.name) / "s.ini"), QSettings.Format.IniFormat)
        self.keep = self.work / "keep.txt"
        self._orig = self.keep.read_text()
        _, self.window, self.session = create_window(Repo(str(self.work)), settings)
        self.session.start()
        qt.wait_until(lambda: self.session.meta is not None and self.session.files and not self.session.busy)
        self.session.set_mode("worktree")
        qt.wait_until(lambda: not self.session.busy)
        self.window.show_tab("files")
        self.page = self.window.files_page
        self.page.show_file("keep.txt")

    def tearDown(self) -> None:
        self.keep.write_text(self._orig)
        self.window.close()
        self.session.stop()
        self._cfg.cleanup()

    def cli(self, *args: str) -> str:
        env = {**isolated_env(), "PYTHONPATH": str(ROOT)}
        p = subprocess.run([sys.executable, "-m", "premerge", "-C", str(self.work), *args],
                           capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_agent_loop(self) -> None:
        qt.wait_until(lambda: any(r.line and r.line["s"] == "B" for r in self.page.diff.rows()))
        self.page._range_selected("new", 2, 2)
        self.page._submit_line(("keep.txt", "new", 2, 2), "Please make this spell it out")
        self.assertTrue(qt.wait_until(lambda: self.session.open_count() == 1))
        cid = self.session.review["comments"][-1]["id"]

        out = self.cli("comments")
        self.assertIn(cid, out)
        self.assertIn("```diff", out)

        self.keep.write_text(self._orig.replace("B\n", "beta\n", 1))
        self.cli("reply", cid, "--resolve", "Fixed")

        def resolved() -> bool:
            threads = self.page.findChildren(CommentThread)
            return (self.session.open_count() == 0 and any(
                t.comment_id() == cid and t._is_collapsed() for t in threads))

        self.assertTrue(qt.wait_until(resolved, timeout=5.0))
        thread = next(t for t in self.page.findChildren(CommentThread) if t.comment_id() == cid)

        replies = thread._comment["replies"]
        self.assertEqual([(r["author"], r["body"]) for r in replies], [("agent", "Fixed")])
        self.assertEqual(self.window.agent_button.text(), "Agent prompt")

        def shows_edit() -> bool:
            rows = self.page.diff.rows()
            return any(r.line and r.line["s"] == "beta" and r.line["t"] == "+" for r in rows)

        self.assertTrue(qt.wait_until(shows_edit, timeout=5.0))
        self.assertTrue(re.fullmatch(r"[0-9a-f]{6}", cid))


if __name__ == "__main__":
    unittest.main()
