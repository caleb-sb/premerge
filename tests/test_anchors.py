import unittest

from premerge.core import anchors


def ctx(n, s):
    return {"t": " ", "o": n, "n": n, "s": s}


class AnchorTests(unittest.TestCase):
    def comment(self, **kw):
        return {"side": "new", "line": 3, "anchorText": "target", **kw}

    def test_line_no(self):
        self.assertIsNone(anchors.line_no({"t": "+", "o": None, "n": 4, "s": ""}, "old"))
        self.assertEqual(anchors.line_no({"t": "+", "o": None, "n": 4, "s": ""}, "new"), 4)
        self.assertIsNone(anchors.line_no({"t": "-", "o": 2, "n": None, "s": ""}, "new"))

    def test_ok_moved_missing_rows(self):
        rows = [ctx(1, "a"), ctx(2, "b"), ctx(3, "target")]
        self.assertEqual(anchors.locate_in_rows(rows, self.comment()), (2, "ok"))
        shifted = [ctx(1, "a"), ctx(2, "b"), ctx(3, "new"), ctx(4, "target")]
        self.assertEqual(anchors.locate_in_rows(shifted, self.comment()), (3, "moved"))
        self.assertEqual(anchors.locate_in_rows([ctx(1, "a")], self.comment()), (None, "missing"))

    def test_text(self):
        self.assertEqual(anchors.locate_in_text(["a", "b", "target"], self.comment()), (3, "ok"))
        self.assertEqual(anchors.locate_in_text(["x", "a", "b", "target"], self.comment()), (4, "moved"))
        self.assertEqual(anchors.locate_in_text(["a", "b"], self.comment()), (None, "missing"))

    def test_nearest_wins(self):
        text = ["target", "x", "x", "x", "x", "x", "target", "x"]
        self.assertEqual(anchors.locate_in_text(text, self.comment(line=5)), (7, "moved"))

    def test_blank_anchor_never_moves(self):
        c = self.comment(anchorText="  ")
        self.assertEqual(anchors.locate_in_text(["", "", "  "], c), (3, "ok"))
        self.assertEqual(anchors.locate_in_text(["", "  ", "", ""], c), (None, "missing"))

    def test_old_side(self):
        rows = [{"t": "-", "o": 3, "n": None, "s": "target"}, {"t": "+", "o": None, "n": 3, "s": "target"}]
        self.assertEqual(anchors.locate_in_rows(rows, self.comment(side="old")), (0, "ok"))
        self.assertEqual(anchors.locate_in_rows(rows[1:], self.comment(side="old")), (None, "missing"))


if __name__ == "__main__":
    unittest.main()
