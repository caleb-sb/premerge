import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QSettings

from tests import qt
from tests.base import FixtureCase

qt.app()

from premerge.core.gitrepo import Repo  # noqa: E402
from premerge.core.store import Store  # noqa: E402
from premerge.ui.app import create_window  # noqa: E402
from premerge.ui.comments import CommentThread  # noqa: E402


class OverviewTests(FixtureCase):
    def setUp(self) -> None:
        self._cfg = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self._cfg.name) / "s.ini"), QSettings.Format.IniFormat)
        self.repo = Repo(str(self.work))
        self.store = Store(self.repo)
        with self.store.edit() as data:
            data["comments"] = []
            data["viewed"] = {}
            data["title"] = None
            data["body"] = None
        _, self.window, self.session = create_window(self.repo, settings)
        self.session.reload_all()
        qt.wait_until(lambda: self.session.meta is not None and self.session.files and not self.session.busy)
        self.page = self.window.overview_page

    def tearDown(self) -> None:
        self.window.close()
        self.session.stop()
        self._cfg.cleanup()

    def _settle(self) -> None:
        qt.wait_until(lambda: not self.session.busy)
        qt.wait_until(lambda: False, 0.1)

    def test_card_shows_template(self) -> None:
        self.assertIn("Summary", self.page.body_view.toPlainText())
        self.assertIn("prefilled from template .github/pull_request_template.md", self.page.state_label.text())

    def test_edit_and_save(self) -> None:
        self.page.start_edit()
        self.assertTrue(self.page.editing)
        self.page.title_edit.setText("My title")
        self.page.body_edit.setPlainText("My **body**")
        self.page.save_button.click()
        qt.wait_until(lambda: self.store.description()["saved"])
        d = self.store.description()
        self.assertEqual((d["title"], d["body"]), ("My title", "My **body**"))
        self._settle()
        self.assertFalse(self.page.editing)
        self.assertIn("description draft", self.page.state_label.text())
        self.assertEqual(self.window.title_label.text(), "My title")

    def test_cancel_confirms_when_modified(self) -> None:
        self.page.start_edit()
        self.page.title_edit.setText("changed")
        with mock.patch.object(self.page, "_confirm", return_value=False):
            self.page.cancel_button.click()
        self.assertTrue(self.page.editing)
        with mock.patch.object(self.page, "_confirm", return_value=True):
            self.page.cancel_button.click()
        self.assertFalse(self.page.editing)

    def test_external_change_while_editing(self) -> None:
        self.page.start_edit()
        self.page.body_edit.setPlainText("typing")
        self.store.set_description("X", "Y")
        self.session.reload_review()
        qt.wait_until(lambda: not self.page.warn_bar.isHidden())
        self.assertFalse(self.page.warn_bar.isHidden())
        self.assertEqual(self.page.body_edit.toPlainText(), "typing")
        self.page.load_button.click()
        self.assertEqual(self.page.body_edit.toPlainText(), "Y")
        self.assertEqual(self.page.title_edit.text(), "X")
        self.assertTrue(self.page.warn_bar.isHidden())

    def test_general_comment(self) -> None:
        self.page.composer.submitted.emit("What about the approach?")
        qt.wait_until(lambda: self.page.findChildren(CommentThread))
        self.assertEqual(len(self.session.general_comments()), 1)
        self.assertEqual(len(self.page.findChildren(CommentThread)), 1)

    def test_summary_click(self) -> None:
        c = self.store.add_comment({"kind": "file", "body": "split it\nmore", "path": "app.py"})
        self.session.reload_review()
        qt.wait_until(lambda: self.page._rows)
        got = []
        self.page.openComment.connect(lambda p, i: got.append((p, i)))
        self.page._rows[0].clicked.emit()
        self.assertEqual(got, [("app.py", c["id"])])


if __name__ == "__main__":
    unittest.main()
