import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from premerge.core import publish
from premerge.core.gitrepo import Repo
from premerge.core.store import Store
from tests.base import FixtureCase

FAKE_GH = """#!/bin/sh
{
  for a in "$@"; do printf 'ARG:%s\\n' "$a"; done
  printf 'STDIN:'; cat
} > "$FAKE_GH_OUT"
"""


class PublishTests(FixtureCase):
    def test_no_forge_is_a_problem(self):
        p = publish.plan(Repo(str(self.work)), Store(Repo(str(self.work))))
        self.assertIsNone(p.forge)
        self.assertTrue(p.problems)

    def test_missing_gh(self):
        repo = Repo(str(self.work), forge="github")
        with mock.patch("shutil.which", return_value=None):
            p = publish.plan(repo, Store(repo))
        self.assertIn("`gh` is not installed", " ".join(p.problems))

    def test_execute_with_fake_gh(self):
        repo = Repo(str(self.work), forge="github")
        store = Store(repo)
        store.set_description("Fancy title", "Line one\nLine two\n")
        with tempfile.TemporaryDirectory() as d:
            bindir = Path(d, "bin")
            bindir.mkdir()
            gh = bindir / "gh"
            gh.write_text(FAKE_GH)
            gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
            out = Path(d, "out.txt")
            path = f"{bindir}{os.pathsep}{os.environ['PATH']}"
            with mock.patch.dict(os.environ, {"PATH": path, "FAKE_GH_OUT": str(out)}):
                self.assertEqual(shutil.which("gh"), str(gh))
                plan = publish.plan(repo, store, push=False)
                self.assertEqual(plan.problems, [])
                self.assertIsNone(plan.push_cmd)
                seen = []
                code, text = publish.execute(plan, str(self.work), seen.append)
                self.assertEqual(code, 0, text)
                self.assertEqual(len(seen), 1)
                lines = out.read_text()
                self.assertIn("ARG:--title\nARG:Fancy title\n", lines)
                self.assertIn("ARG:--base\nARG:main\n", lines)
                self.assertIn("ARG:--head\nARG:feat/thing\n", lines)
                self.assertTrue(lines.endswith("STDIN:Line one\nLine two\n"))
                self.assertNotIn("--draft", lines)

                publish.execute(publish.plan(repo, store, draft=True, push=False), str(self.work))
                self.assertIn("ARG:--draft\n", out.read_text())

    def test_push_step_listed(self):
        repo = Repo(str(self.work), forge="github")
        with mock.patch("shutil.which", return_value="/fake/gh"):
            p = publish.plan(repo, Store(repo))
        self.assertEqual(p.push_cmd, ["git", "push", "-u", "origin", "feat/thing"])
        self.assertEqual(len(p.display), 2)
        self.assertEqual(p.problems, [])

    def test_glab_plan(self):
        repo = Repo(str(self.work), forge="gitlab")
        with mock.patch("shutil.which", return_value="/fake/glab"):
            p = publish.plan(repo, Store(repo), push=False)
        self.assertEqual(p.tool, "glab")
        self.assertIn("--target-branch", p.create_cmd)
        self.assertIsNone(p.stdin)


if __name__ == "__main__":
    unittest.main()
