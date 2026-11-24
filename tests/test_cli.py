import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from premerge.core.gitrepo import Repo
from premerge.core.store import Store
from tests.base import FixtureCase
from tests.fixture import isolated_env

ROOT = Path(__file__).resolve().parent.parent


class CliTests(FixtureCase):
    def setUp(self):
        self.store = Store(Repo(str(self.work)))
        self.store.path().unlink(missing_ok=True)
        self.cid = self.store.add_comment({"kind": "general", "body": "please fix"})["id"]

    def run_cli(self, *args, cwd=None, stdin=None):
        return subprocess.run([sys.executable, "-m", "premerge", "-C", str(cwd or self.work), *args],
                              input=stdin, capture_output=True, text=True, env=isolated_env(), cwd=ROOT)

    def status(self):
        return self.store.load()["comments"][0]["status"]

    def test_comments(self):
        p = self.run_cli("comments")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(self.cid, p.stdout)
        self.assertIn("please fix", p.stdout)

    def test_comments_json(self):
        p = self.run_cli("comments", "--json")
        self.assertEqual([c["id"] for c in json.loads(p.stdout)], [self.cid])

    def test_reply_resolve_and_stdin(self):
        p = self.run_cli("reply", self.cid, "--resolve", "fixed it")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.status(), "resolved")
        self.assertEqual(json.loads(self.run_cli("comments", "--json").stdout), [])
        self.assertEqual(len(json.loads(self.run_cli("comments", "--json", "--all").stdout)), 1)
        p = self.run_cli("reply", self.cid, "-", stdin="from stdin\nsecond line\n")
        self.assertEqual(p.returncode, 0, p.stderr)
        replies = self.store.load()["comments"][0]["replies"]
        self.assertEqual([r["author"] for r in replies], ["agent", "agent"])
        self.assertEqual(replies[1]["body"], "from stdin\nsecond line")

    def test_resolve_reopen(self):
        self.assertEqual(self.run_cli("resolve", self.cid).returncode, 0)
        self.assertEqual(self.status(), "resolved")
        self.assertEqual(self.run_cli("reopen", self.cid[:3]).returncode, 0)
        self.assertEqual(self.status(), "open")

    def test_describe(self):
        p = self.run_cli("describe", "--title", "My PR", "--body-file", "-", stdin="Body text\n")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, "# My PR\n\nBody text\n")
        j = json.loads(self.run_cli("describe", "--json").stdout)
        self.assertEqual((j["title"], j["saved"]), ("My PR", True))
        p = self.run_cli("describe", "--reset")
        self.assertTrue(p.stdout.startswith("# Thing\n"))
        self.assertFalse(json.loads(self.run_cli("describe", "--json").stdout)["saved"])

    def test_unknown_id(self):
        p = self.run_cli("resolve", "ffffff")
        self.assertEqual(p.returncode, 1)
        self.assertTrue(p.stderr.startswith("premerge:"))

    def test_not_a_repo(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.run_cli("comments", cwd=d)
        self.assertEqual(p.returncode, 1)
        self.assertTrue(p.stderr.startswith("premerge:"))


if __name__ == "__main__":
    unittest.main()


class GuiDispatchTests(unittest.TestCase):
    def test_gui_starts_outside_a_repo(self):
        """Finder/Spotlight start apps in /: the GUI must get to choose its repository itself."""
        from unittest import mock

        from premerge import cli

        with tempfile.TemporaryDirectory() as d, mock.patch.object(cli, "cmd_gui", return_value=0) as gui:
            self.assertEqual(cli.main(["-C", d]), 0)
            self.assertEqual(cli.main(["-C", d, "gui"]), 0)
        self.assertEqual(gui.call_count, 2)
