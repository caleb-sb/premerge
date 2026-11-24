import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from tests import qt
from tests.base import FixtureCase

qt.app()

from premerge.core.gitrepo import Repo  # noqa: E402
from premerge.ui.app import create_window  # noqa: E402


class WindowTests(FixtureCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._cfg = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(cls._cfg.name) / "s.ini"), QSettings.Format.IniFormat)
        _, cls.window, cls.session = create_window(Repo(str(cls.work)), settings)
        cls.session.reload_all()
        qt.wait_until(lambda: cls.session.meta is not None and cls.session.files and not cls.session.busy)

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.session.stop()
        cls._cfg.cleanup()
        super().tearDownClass()

    def test_title_and_counts(self) -> None:
        w = self.window
        self.assertEqual(w.title_label.text(), "Thing")
        self.assertEqual(w.tab_bar.tabText(1), "Commits  2")
        self.assertEqual(w.tab_bar.tabText(2), "Files changed  7")

    def test_commits_tab(self) -> None:
        self.window.show_tab("commits")
        self.assertEqual(len(self.window.commits_page.rows), 2)

    def test_worktree_toggle(self) -> None:
        w = self.window
        w.mode_buttons["worktree"].click()
        self.assertEqual(self.session.mode, "worktree")
        self.assertTrue(qt.wait_until(lambda: w.tab_bar.tabText(2) == "Files changed  8"))
        w.mode_buttons["committed"].click()
        self.assertTrue(qt.wait_until(lambda: w.tab_bar.tabText(2) == "Files changed  7"))


if __name__ == "__main__":
    unittest.main()
