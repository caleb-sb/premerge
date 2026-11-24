import json
import unittest
from pathlib import Path

from premerge.core.gitrepo import Repo
from premerge.core.store import Store, StoreError
from tests.base import FixtureCase
from tests.fixture import git

LINE = {"kind": "line", "body": "why?", "path": "keep.txt", "oldPath": "keep.txt", "side": "new",
        "line": 2, "startLine": 2, "anchorText": "B", "context": [" a", "+B"]}


class StoreTests(FixtureCase):
    def setUp(self):
        self.repo = Repo(str(self.work))
        self.store = Store(self.repo)
        self.store.path().unlink(missing_ok=True)

    def test_add_kinds(self):
        a = self.store.add_comment(LINE)
        b = self.store.add_comment({"kind": "file", "body": "file note", "path": "keep.txt"})
        c = self.store.add_comment({"kind": "general", "body": "hello"})
        self.assertEqual([a["kind"], b["kind"], c["kind"]], ["line", "file", "general"])
        self.assertEqual(len(a["id"]), 6)
        self.assertEqual(a["status"], "open")
        self.assertEqual(a["head"], self.repo.head())
        self.assertEqual(len(self.store.load()["comments"]), 3)

    def test_validation(self):
        for bad in ({"kind": "general", "body": "  "}, {**LINE, "side": "middle"}, {"kind": "bogus", "body": "x"},
                    {"kind": "file", "body": "x"}, {"kind": "line", "body": "x", "side": "new"}):
            with self.assertRaises(StoreError, msg=bad):
                self.store.add_comment(bad)
        self.assertEqual(self.store.load()["comments"], [])

    def test_find(self):
        a = self.store.add_comment({"kind": "general", "body": "a"})
        self.assertEqual(self.store.find(self.store.load(), a["id"][:3])["id"], a["id"])
        data = {"comments": [{"id": "abc123"}, {"id": "abc456"}]}
        with self.assertRaises(StoreError):
            Store.find(data, "abc")
        with self.assertRaises(StoreError):
            Store.find(data, "zzz")
        with self.assertRaises(StoreError):
            Store.find(data, "ab")
        self.assertEqual(Store.find(data, "abc4")["id"], "abc456")

    def test_reply_reopens(self):
        a = self.store.add_comment({"kind": "general", "body": "a"})
        c = self.store.reply(a["id"], "agent", "done", resolve=True)
        self.assertEqual(c["status"], "resolved")
        self.assertEqual(self.store.reply(a["id"], "agent", "fyi")["status"], "resolved")
        c = self.store.reply(a["id"], "you", "not really")
        self.assertEqual(c["status"], "open")
        self.assertEqual([r["author"] for r in c["replies"]], ["agent", "agent", "you"])

    def test_status_edit_delete(self):
        a = self.store.add_comment({"kind": "general", "body": "a"})
        self.assertEqual(self.store.set_status(a["id"], "resolved")["status"], "resolved")
        with self.assertRaises(StoreError):
            self.store.set_status(a["id"], "closed")
        self.assertEqual(self.store.edit_body(a["id"], " new ")["body"], "new")
        self.store.delete(a["id"])
        self.assertEqual(self.store.load()["comments"], [])

    def test_viewed_and_description(self):
        self.store.set_viewed("keep.txt", "abc")
        self.assertEqual(self.store.load()["viewed"], {"keep.txt": "abc"})
        self.store.set_viewed("keep.txt", None)
        self.assertEqual(self.store.load()["viewed"], {})
        self.assertFalse(self.store.description()["saved"])
        self.store.set_description("My title", "My body")
        d = self.store.description()
        self.assertEqual((d["title"], d["body"], d["saved"]), ("My title", "My body", True))
        self.store.set_description(None, None)
        d = self.store.description()
        self.assertEqual((d["title"], d["saved"]), ("Thing", False))

    def test_two_stores_do_not_lose_writes(self):
        other = Store(Repo(str(self.work)))
        for i in range(5):
            self.store.add_comment({"kind": "general", "body": f"a{i}"})
            other.add_comment({"kind": "general", "body": f"b{i}"})
        self.assertEqual(len(self.store.load()["comments"]), 10)
        with self.store.edit() as d1:
            d1["viewed"]["x"] = "1"
        other.set_viewed("y", "2")
        self.assertEqual(self.store.load()["viewed"], {"x": "1", "y": "2"})

    def test_location_and_rev(self):
        self.assertEqual(self.store.rev(), 0)
        self.store.add_comment({"kind": "general", "body": "a"})
        self.assertGreater(self.store.rev(), 0)
        p = self.store.path()
        self.assertEqual(p.parent, self.repo.common_dir / "premerge")
        self.assertEqual(p.name, "feat__thing.json")
        self.assertEqual(json.loads(p.read_text())["branch"], "feat/thing")
        self.assertTrue(str(Path(p).resolve()).startswith(str((self.work / ".git").resolve())))

    def test_branch_switch_uses_other_file(self):
        self.store.add_comment({"kind": "general", "body": "on feat"})
        feat_path = self.store.path()
        git(self.work, "stash", "-u", "-q")
        git(self.work, "checkout", "-q", "-b", "other")
        try:
            s2 = Store(Repo(str(self.work)))
            self.assertEqual(s2.load()["comments"], [])
            self.assertNotEqual(s2.path(), feat_path)
        finally:
            git(self.work, "checkout", "-q", "feat/thing")
            git(self.work, "branch", "-q", "-D", "other")
            git(self.work, "stash", "pop", "-q")


if __name__ == "__main__":
    unittest.main()
