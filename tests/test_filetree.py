import unittest

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from tests import qt
from premerge.ui.filetree import KIND, PATH, FileTree

PATHS = ["README.md", "src/a.py", "src/util/b.py", "docs/x/y/z.md"]


def files(paths=PATHS) -> list[dict]:
    return [{"path": p, "status": "modified", "oldPath": p} for p in paths]


class FileTreeTest(unittest.TestCase):
    def setUp(self) -> None:
        qt.app()
        self.tree = FileTree()
        self.tree.resize(320, 600)
        self.tree.show()
        self.tree.set_files(files(), set(), set(), {})
        qt.wait_until(lambda: False, 0.05)

    def tearDown(self) -> None:
        self.tree.close()

    def visible_files(self) -> list[str]:
        view, model = self.tree._view, self.tree._model
        out = []

        def walk(parent):
            for r in range(model.rowCount(parent)):
                idx = model.index(r, 0, parent)
                if view.isRowHidden(r, parent):
                    continue
                if idx.data(KIND) == "file":
                    out.append(idx.data(PATH))
                else:
                    walk(idx)

        from PySide6.QtCore import QModelIndex
        walk(QModelIndex())
        return out

    def test_order_and_compression(self) -> None:
        self.assertEqual(self.tree.ordered_paths(),
                         ["docs/x/y/z.md", "src/util/b.py", "src/a.py", "README.md"])
        self.assertIn("docs/x/y", [i.text() for i in self.tree._dirs.values()])

    def test_filter(self) -> None:
        self.tree._filter.setText("util")
        self.assertEqual(self.visible_files(), ["src/util/b.py"])

    def test_click_activates(self) -> None:
        got = []
        self.tree.fileActivated.connect(got.append)
        idx = self.tree._items["README.md"].index()
        rect = self.tree._view.visualRect(idx)
        QTest.mouseClick(self.tree._view.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        self.assertEqual(got, ["README.md"])

    def test_progress(self) -> None:
        self.tree.set_files(files(), {"src/a.py"}, set(), {})
        self.assertEqual(self.tree._label.text(), "1 of 4 viewed")

    def test_collapse_survives(self) -> None:
        self.tree._view.collapse(self.tree._dirs["src"].index())
        self.tree.set_files(files(), set(), set(), {})
        self.assertFalse(self.tree._view.isExpanded(self.tree._dirs["src"].index()))
        self.assertTrue(self.tree._view.isExpanded(self.tree._dirs["docs/x/y"].index()))

    def test_select_path_silent(self) -> None:
        got = []
        self.tree.fileActivated.connect(got.append)
        self.tree.select_path("src/util/b.py")
        self.assertEqual(self.tree._current_path(), "src/util/b.py")
        self.assertEqual(got, [])


if __name__ == "__main__":
    unittest.main()
