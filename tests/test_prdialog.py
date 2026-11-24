import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication

from tests import qt
from tests.base import FixtureCase

qt.app()

from premerge.core.gitrepo import Repo  # noqa: E402
from premerge.ui.app import create_window  # noqa: E402
from premerge.ui.prdialog import CreatePrDialog  # noqa: E402

FAKE_GH = """#!/bin/sh
printf '%s\\n' "$@" > "$FAKE_GH_OUT"
cat > /dev/null
echo https://github.com/o/r/pull/1
"""


class PrDialogTests(FixtureCase):
    def setUp(self) -> None:
        self._cfg = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self._cfg.name) / "s.ini"), QSettings.Format.IniFormat)
        _, self.window, self.session = create_window(Repo(str(self.work)), settings)
        self.session.reload_all()
        qt.wait_until(lambda: self.session.meta is not None and not self.session.busy)

    def tearDown(self) -> None:
        self.window.close()
        self.session.stop()
        self._cfg.cleanup()

    def test_prompt_button_copies(self) -> None:
        self.window.agent_button.click()
        self.assertIn("Local review of", QGuiApplication.clipboard().text())
        self.assertIn("Copied", self.window.statusBar().currentMessage())

    def test_agent_instructions(self) -> None:
        self.window.copy_agent_instructions()
        self.assertIn(" comments` in ", QGuiApplication.clipboard().text())

    def test_no_forge_disables_create(self) -> None:
        dialog = CreatePrDialog(self.session)
        dialog.show()
        self.assertTrue(qt.wait_until(lambda: dialog.plan is not None))
        self.assertTrue(dialog.plan.problems)
        self.assertFalse(dialog.create_button.isEnabled())
        self.assertIn("GitHub or GitLab", dialog.problems_label.text())

    def test_open_recent_recorded(self) -> None:
        self.assertEqual(self.window._recent()[0], self.session.repo.root)

    def test_create_with_fake_gh(self) -> None:
        repo = Repo(str(self.work), forge="github")
        self.session.repo = repo
        with tempfile.TemporaryDirectory() as d:
            gh = Path(d, "bin", "gh")
            gh.parent.mkdir()
            gh.write_text(FAKE_GH)
            gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
            out = Path(d, "out.txt")
            path = f"{gh.parent}{os.pathsep}{os.environ['PATH']}"
            with mock.patch.dict(os.environ, {"PATH": path, "FAKE_GH_OUT": str(out)}):
                self.assertEqual(shutil.which("gh"), str(gh))
                dialog = CreatePrDialog(self.session)
                dialog.show()
                dialog.push_box.setChecked(False)
                self.assertTrue(qt.wait_until(
                    lambda: dialog.plan is not None and dialog.plan.push_cmd is None))
                self.assertEqual(dialog.plan.problems, [])
                self.assertTrue(dialog.create_button.isEnabled())
                dialog.create_button.click()
                self.assertTrue(qt.wait_until(lambda: dialog.url is not None))
            self.assertEqual(dialog.url, "https://github.com/o/r/pull/1")
            self.assertIn("Created: https://github.com/o/r/pull/1", dialog.status.text())
            self.assertIn("--title", out.read_text())


if __name__ == "__main__":
    unittest.main()
