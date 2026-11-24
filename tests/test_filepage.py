import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from tests import qt
from tests.base import FixtureCase

qt.app()

from premerge.core.gitrepo import Repo  # noqa: E402
from premerge.core.store import Store  # noqa: E402
from premerge.ui.app import create_window  # noqa: E402
from premerge.ui.comments import CommentThread, Composer  # noqa: E402
from premerge.ui.markdown import MarkdownView  # noqa: E402


class FilesPageTests(FixtureCase):
    def setUp(self) -> None:
        self._cfg = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self._cfg.name) / "s.ini"), QSettings.Format.IniFormat)
        self.repo = Repo(str(self.work))
        self.store = Store(self.repo)
        with self.store.edit() as data:
            data["comments"] = []
            data["viewed"] = {}
        _, self.window, self.session = create_window(self.repo, settings)
        self.session.reload_all()
        qt.wait_until(lambda: self.session.meta is not None and self.session.files and not self.session.busy)
        self.window.show_tab("files")
        self.page = self.window.files_page
        self.page.show_file("app.py")

    def tearDown(self) -> None:
        self.window.close()
        self.session.stop()
        self._cfg.cleanup()

    def _threads(self):
        return self.page.findChildren(CommentThread)

    def _add(self, **kw) -> dict:
        fields = {"kind": "line", "body": "hm", "path": "app.py", "oldPath": "app.py", "side": "new",
                  "startLine": 2, "line": 2, "anchorText": "x", "context": [" x"]}
        fields.update(kw)
        c = self.store.add_comment(fields)
        self.session.reload_review()
        qt.wait_until(lambda: any(x["id"] == c["id"] for x in self.session.review["comments"]))
        return c

    def test_first_file_and_diff(self) -> None:
        order = self.page.tree.ordered_paths()
        self.page.show_file(order[0])
        self.assertEqual(self.page.current_path(), order[0])
        self.page.tree.fileActivated.emit("app.py")
        self.assertEqual(self.page.current_path(), "app.py")
        hunks = sum(1 for r in self.page.diff.rows() if r.kind == "hunk")
        self.assertGreaterEqual(hunks, 2)

    def test_compose_line_comment(self) -> None:
        self.page.diff.rangeSelected.emit("new", 2, 3)
        comps = self.page.findChildren(Composer)
        self.assertTrue(comps)
        comp = comps[0]
        flat = self.page._flat
        text3 = next(ln["s"] for ln in flat if ln["t"] != "-" and ln["n"] == 3)
        comp.set_text("why?")
        comp.submitted.emit("why?")
        data = self.store.load()["comments"]
        self.assertEqual(len(data), 1)
        c = data[0]
        self.assertEqual((c["startLine"], c["line"]), (2, 3))
        self.assertEqual(c["anchorText"], text3)
        self.assertTrue(c["context"][-1].endswith(text3))
        qt.wait_until(lambda: len(self._threads()) == 1)
        self.assertEqual(len(self._threads()), 1)

    def test_outdated_comment(self) -> None:
        c = self._add(anchorText="no such text anywhere", line=2, startLine=2, context=[" a", "+b"])
        qt.wait_until(lambda: c["id"] in self.page._threads)
        thread = self.page._threads[c["id"]]
        self.assertIs(thread.parent(), self.page._area)

    def test_viewed_moves_on(self) -> None:
        start = self.page.current_path()
        self.page._viewed.click()
        self.assertNotEqual(self.page.current_path(), start)
        self.assertTrue(qt.wait_until(lambda: self.page.tree._label.text().startswith("1")))

    def test_split_keeps_thread(self) -> None:
        c = self._add(anchorText=next(ln["s"] for ln in self.page._flat if ln["t"] != "-" and ln["n"] == 2),
                      line=2, startLine=2)
        qt.wait_until(lambda: c["id"] in self.page._threads)
        self.session.set_view("split")
        thread = self.page._threads[c["id"]]
        self.assertTrue(thread.isVisibleTo(self.page))
        self.assertIsNot(thread.parent(), self.page._area)

    def test_external_reply_appears(self) -> None:
        c = self._add(anchorText=next(ln["s"] for ln in self.page._flat if ln["t"] != "-" and ln["n"] == 2),
                      line=2, startLine=2)
        self.session.start()
        qt.wait_until(lambda: c["id"] in self.page._threads)
        self.assertTrue(qt.wait_until(lambda: self.session._poll_prev is not None, 5.0))
        self.store.reply(c["id"], "agent", "fixed it")
        self.assertTrue(qt.wait_until(
            lambda: len(self.session.comments_for("app.py")[0]["replies"]) == 1, 5.0))
        views = self.page._threads[c["id"]].findChildren(MarkdownView)
        self.assertTrue(qt.wait_until(lambda: any("fixed it" in v.toPlainText() for v in views), 3.0))


if __name__ == "__main__":
    unittest.main()
