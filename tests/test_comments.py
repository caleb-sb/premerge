import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFrame, QMessageBox, QPushButton

from premerge.ui import comments
from premerge.ui.comments import CommentThread, Composer, ago
from tests import qt


def make_comment(status="open", replies=1, cid="abc123"):
    c = {
        "id": cid, "kind": "line", "body": "why `sys`?\n\n- one\n- two", "author": "you", "status": status,
        "created": "2026-01-01T00:00:00Z", "updated": "2026-01-01T00:00:00Z", "head": "x",
        "path": "a.py", "oldPath": "a.py", "side": "new", "line": 12, "startLine": 10,
        "anchorText": "", "context": [], "replies": [],
    }
    for i in range(replies):
        c["replies"].append({"id": f"r{i}", "author": "agent", "body": "removed it", "created": "2026-01-01T00:01:00Z"})
    return c


def button(widget, text):
    return next(b for b in widget.findChildren(QPushButton) if b.text() == text)


class AgoTest(unittest.TestCase):
    def test_boundaries(self):
        now = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)

        def at(**kw):
            return ago((now - timedelta(**kw)).isoformat(), now)

        self.assertEqual(at(seconds=30), "just now")
        self.assertEqual(at(minutes=5), "5m ago")
        self.assertEqual(at(hours=3), "3h ago")
        self.assertEqual(at(days=2), "2d ago")
        self.assertEqual(at(days=40), "15 Oct")


class ComposerTest(unittest.TestCase):
    def setUp(self):
        qt.app()
        self.box = Composer()
        self.box.show()

    def tearDown(self):
        self.box.close()

    def test_submit_with_ctrl_enter(self):
        got = []
        self.box.submitted.connect(got.append)
        self.assertFalse(button(self.box, "Comment").isEnabled())
        QTest.keyClicks(self.box._edit, "  hello  ")
        self.assertTrue(button(self.box, "Comment").isEnabled())
        QTest.keyClick(self.box._edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(got, ["hello"])
        self.assertEqual(self.box.text(), "  hello  ")

    def test_empty_does_not_submit(self):
        got = []
        self.box.submitted.connect(got.append)
        QTest.keyClicks(self.box._edit, "   ")
        QTest.keyClick(self.box._edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(got, [])
        self.assertFalse(button(self.box, "Comment").isEnabled())

    def test_escape_cancels(self):
        got = []
        self.box.cancelled.connect(lambda: got.append(1))
        QTest.keyClick(self.box._edit, Qt.Key.Key_Escape)
        self.assertEqual(got, [1])

    def test_compact_hides_buttons_until_text(self):
        box = Composer(compact=True)
        box.show()
        self.assertTrue(box._buttons.isHidden())
        box.set_text("x")
        self.assertFalse(box._buttons.isHidden())
        box.clear()
        self.assertTrue(box._buttons.isHidden())
        box.close()

    def test_grows_with_content(self):
        before = self.box._edit.height()
        self.box.set_text("\n".join("line" for _ in range(8)))
        self.assertGreater(self.box._edit.height(), before)


class ThreadTest(unittest.TestCase):
    def setUp(self):
        qt.app()
        comments.EXPANDED.clear()

    def test_open_thread(self):
        t = CommentThread(make_comment(), "Caleb")
        t.show()
        self.assertEqual(len(t.findChildren(QFrame, "entry")), 2)
        resolve = button(t, "Resolve")
        got = []
        t.statusRequested.connect(lambda *a: got.append(a))
        resolve.click()
        self.assertEqual(got, [("abc123", "resolved")])
        replies = []
        t.replyRequested.connect(lambda *a: replies.append(a))
        QTest.keyClicks(t._reply._edit, "thanks")
        QTest.keyClick(t._reply._edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(replies, [("abc123", "thanks")])
        t.close()

    def test_delete_asks(self):
        t = CommentThread(make_comment(), "Caleb")
        t.show()
        got = []
        t.deleteRequested.connect(got.append)
        tool = next(b for b in t.findChildren(type(t._collapse_btn)) if b.toolTip() == "Delete")
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            tool.click()
        self.assertEqual(got, [])
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            tool.click()
        self.assertEqual(got, ["abc123"])
        t.close()

    def test_edit(self):
        t = CommentThread(make_comment(), "Caleb")
        t.show()
        got = []
        t.editRequested.connect(lambda *a: got.append(a))
        next(b for b in t.findChildren(type(t._collapse_btn)) if b.toolTip() == "Edit").click()
        self.assertIsNotNone(t._edit_box)
        t._edit_box.set_text("new body")
        button(t, "Save").click()
        self.assertEqual(got, [("abc123", "new body")])
        self.assertIsNone(t._edit_box)
        t.close()

    def test_resolved_collapsed_then_expands(self):
        t = CommentThread(make_comment("resolved"), "Caleb")
        t.show()
        self.assertFalse(t._collapsed.isHidden())
        self.assertTrue(t._entries.isHidden())
        QTest.mouseClick(t._collapsed, Qt.MouseButton.LeftButton)
        self.assertIn("abc123", comments.EXPANDED)
        self.assertTrue(t._collapsed.isHidden())
        self.assertFalse(t._entries.isHidden())
        self.assertEqual(button(t, "Reopen").text(), "Reopen")
        t._collapse_btn.click()
        self.assertNotIn("abc123", comments.EXPANDED)
        self.assertFalse(t._collapsed.isHidden())
        t.close()

    def test_update_keeps_draft(self):
        t = CommentThread(make_comment(replies=1), "Caleb")
        t.show()
        QTest.keyClicks(t._reply._edit, "draft")
        t.update_comment(make_comment(replies=2))
        self.assertEqual(len(t.findChildren(QFrame, "entry")), 3)
        self.assertEqual(t.reply_draft(), "draft")
        t.close()


if __name__ == "__main__":
    unittest.main()
