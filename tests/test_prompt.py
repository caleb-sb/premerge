import unittest

from premerge.core import prompt
from premerge.core.gitrepo import Repo
from premerge.core.store import Store
from tests.base import FixtureCase

APP_LINE = "import json"


class PromptTests(FixtureCase):
    def setUp(self):
        self.repo = Repo(str(self.work))
        self.store = Store(self.repo)
        self.store.path().unlink(missing_ok=True)
        self.app = self.work / "app.py"
        self.orig = self.app.read_text()

    def tearDown(self):
        self.app.write_text(self.orig)

    def line_comment(self, **kw):
        fields = {"kind": "line", "body": "check this", "path": "app.py", "side": "new", "line": 3,
                  "startLine": 3, "anchorText": APP_LINE, "context": [" import os", "+import json"]}
        return self.store.add_comment({**fields, **kw})

    def render(self, **kw):
        return prompt.render_prompt(self.repo, self.store.load(), **kw)

    def test_empty(self):
        self.assertIn("No open review comments.", self.render())

    def test_each_kind(self):
        a = self.line_comment()
        b = self.store.add_comment({"kind": "file", "body": "whole file", "path": "keep.txt"})
        c = self.store.add_comment({"kind": "general", "body": "overall"})
        text = self.render()
        for needle in (a["id"], b["id"], c["id"], "`app.py` line 3", "(whole file)", "General comment",
                       "> check this", "```diff", "reply <id> --resolve"):
            self.assertIn(needle, text)

    def test_resolved_hidden_unless_all(self):
        a = self.store.add_comment({"kind": "general", "body": "done one"})
        self.store.set_status(a["id"], "resolved")
        self.assertNotIn(a["id"], self.render())
        text = self.render(include_all=True)
        self.assertIn(a["id"], text)
        self.assertIn("_status: resolved_", text)

    def test_replies_rendered(self):
        a = self.store.add_comment({"kind": "general", "body": "q"})
        self.store.reply(a["id"], "agent", "answer")
        self.assertIn("**Agent:**\n> answer", self.render(include_all=True))

    def test_fence_grows_for_backticks(self):
        self.line_comment(context=[" ```", "+code"])
        self.assertIn("````diff", self.render())
        self.assertEqual(prompt.fence(["a"]), ["```", "a", "```"])

    def test_locate_moved_and_outdated(self):
        c = self.line_comment()
        self.assertEqual(prompt.locate(self.repo, c), ("ok", 3))
        self.app.write_text("# one\n# two\n" + self.orig)
        self.assertEqual(prompt.locate(self.repo, c), ("moved", 5))
        self.assertIn("anchor line is now line 5", self.render())
        self.app.write_text(self.orig.replace(APP_LINE + "\n", ""))
        self.assertEqual(prompt.locate(self.repo, c), ("outdated", None))
        self.assertIn("Outdated", self.render())

    def test_locate_missing_file_and_old_side(self):
        c = self.line_comment(path="nope.py")
        self.assertEqual(prompt.locate(self.repo, c), ("outdated", None))
        old = self.line_comment(path="gone.txt", side="old", line=1, anchorText="x")
        self.assertEqual(prompt.locate(self.repo, old), ("ok", 1))
        self.assertIn("removed line 1 (base version)", self.render())

    def test_cli_cmd(self):
        self.assertIn("premerge", prompt.cli_cmd())


if __name__ == "__main__":
    unittest.main()
