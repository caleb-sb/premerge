import time
import unittest

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel

from tests import qt
from premerge.ui import diffview, syntax


def L(t, o, n, s):
    return {"t": t, "o": o, "n": n, "s": s}


def hunk():
    return {"header": "@@ -1,4 +1,5 @@", "lines": [
        L(" ", 1, 1, "a"), L("-", 2, None, "b"), L("-", 3, None, "c"),
        L("+", None, 2, "B"), L(" ", 4, 3, "d"), L("+", None, 4, "e")]}


def mouse(w, kind, x, y):
    pos = QPointF(x, y)
    ev = QMouseEvent(kind, pos, w.mapToGlobal(pos), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, ev)


class RowsTest(unittest.TestCase):
    def test_split_and_keys(self):
        rows = diffview.build_rows([hunk()], "split")
        self.assertEqual(rows[0].kind, "hunk")
        pairs = [(r.left and r.left["s"], r.right and r.right["s"]) for r in rows[1:]]
        self.assertEqual(pairs, [("a", "a"), ("b", "B"), ("c", None), ("d", "d"), (None, "e")])
        keys = [diffview.row_keys(r) for r in rows]
        self.assertEqual(keys, [[], ["new:1", "old:1"], ["new:2", "old:2"], ["old:3"],
                                ["new:3", "old:4"], ["new:4"]])

    def test_unified_keys(self):
        rows = diffview.build_rows([hunk()], "unified")
        self.assertEqual(len(rows), 7)
        self.assertEqual([diffview.row_keys(r) for r in rows[1:]],
                         [["new:1", "old:1"], ["old:2"], ["old:3"], ["new:2"], ["new:3", "old:4"], ["new:4"]])


class BodyTest(unittest.TestCase):
    def setUp(self):
        qt.app()
        self.body = diffview.DiffBody()
        self.body.resize(600, 300)
        self.body.show()

    def tearDown(self):
        self.body.close()

    def test_inserts(self):
        self.body.set_content("x.txt", [hunk()], "unified")
        idx = self.body.row_index("new:2")
        self.assertEqual(idx, 4)
        label = QLabel("x")
        self.body.set_inserts({2: [label]})
        lay = self.body._layout
        widgets = [lay.itemAt(i).widget() for i in range(lay.count()) if lay.itemAt(i).widget()]
        self.assertIs(widgets[1], label)
        self.assertEqual((widgets[0].start, widgets[0].end), (0, 3))
        self.assertEqual(widgets[2].start, 3)

    def test_selection_new_and_old(self):
        self.body.set_content("x.txt", [hunk()], "unified")
        got = []
        self.body.rangeSelected.connect(lambda *a: got.append(a))
        blk = self.body._blocks[(0, len(self.body.rows()))]
        h = self.body.row_h
        y = lambda i: i * h + h // 2
        x = diffview.NUM_W + 10
        mouse(blk, QEvent.Type.MouseButtonPress, x, y(1))
        mouse(blk, QEvent.Type.MouseMove, x, y(4))
        mouse(blk, QEvent.Type.MouseButtonRelease, x, y(4))
        self.assertEqual(got[-1], ("new", 1, 2))
        mouse(blk, QEvent.Type.MouseButtonPress, x, y(2))
        mouse(blk, QEvent.Type.MouseButtonRelease, x, y(2))
        self.assertEqual(got[-1], ("old", 2, 2))

    def test_split_selection(self):
        self.body.set_content("x.txt", [hunk()], "split")
        got = []
        self.body.rangeSelected.connect(lambda *a: got.append(a))
        blk = self.body._blocks[(0, len(self.body.rows()))]
        h = self.body.row_h
        mouse(blk, QEvent.Type.MouseButtonPress, 10, 2 * h + 3)
        mouse(blk, QEvent.Type.MouseButtonRelease, 10, 2 * h + 3)
        self.assertEqual(got[-1], ("old", 2, 2))

    def test_render_5000_rows(self):
        lines = [L("+", None, i + 1, f"x = {i}  # c") for i in range(5000)]
        t = time.monotonic()
        self.body.set_content("a.py", [{"header": "@@", "lines": lines}], "unified")
        self.body.grab()
        self.assertLess(time.monotonic() - t, 1.5)


class SyntaxTest(unittest.TestCase):
    def test_python(self):
        spans = syntax.highlight_lines("x.py", ["def f():", "    return 'hi'"])
        self.assertEqual(spans[0][0][:2], (0, 3))
        self.assertTrue(any(s[2] == "#9ece6a" for s in spans[1]))

    def test_unknown(self):
        self.assertEqual(syntax.highlight_lines("x.zzzq", ["abc", "def"]), [[], []])


if __name__ == "__main__":
    unittest.main()
