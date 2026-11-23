import subprocess
import unittest
from unittest import mock

from premerge.core.gitrepo import GitError, Repo
from premerge.core.paths import tree_order
from premerge.core.store import Store
from premerge.ui.session import Session
from tests import qt
from tests.base import FixtureCase


class SessionTest(FixtureCase):
    def setUp(self):
        qt.app()
        self.s = Session(Repo(str(self.work)))

    def tearDown(self):
        self.s.stop()
        qt.wait_until(lambda: not self.s.busy)

    def loaded(self):
        self.s.reload_all()
        self.assertTrue(qt.wait_until(lambda: self.s.meta and self.s.review["description"] and not self.s.busy))

    def test_reload_all(self):
        counts = {n: 0 for n in ("meta", "files", "commits", "review")}
        for n, sig in (("meta", self.s.metaChanged), ("files", self.s.filesChanged),
                       ("commits", self.s.commitsChanged), ("review", self.s.reviewChanged)):
            sig.connect(lambda n=n: counts.__setitem__(n, counts[n] + 1))
        self.loaded()
        self.assertEqual(counts, {"meta": 1, "files": 1, "commits": 1, "review": 1})
        paths = [f["path"] for f in self.s.files]
        self.assertEqual(paths, tree_order(paths))
        self.assertTrue(self.s.commits)
        self.assertIsNotNone(self.s.last_refresh)

    def test_worktree_mode(self):
        self.loaded()
        self.assertIsNone(self.s.file("u.txt"))
        self.s.set_mode("worktree")
        self.assertTrue(qt.wait_until(lambda: self.s.file("u.txt") is not None))

    def test_comments_and_viewed(self):
        self.loaded()
        c = self.s.add_comment({"kind": "general", "body": "hello"})
        self.assertTrue(qt.wait_until(lambda: any(x["id"] == c["id"] for x in self.s.review["comments"])))
        self.assertEqual(self.s.open_count(), 1)
        self.assertEqual(len(self.s.general_comments()), 1)
        self.s.reply(c["id"], "done", resolve=True)
        self.assertTrue(qt.wait_until(lambda: self.s.review["comments"][0]["status"] == "resolved"))
        self.assertEqual(self.s.open_count(), 0)
        f = self.s.file("app.py")
        self.assertFalse(self.s.is_viewed(f))
        self.s.set_viewed(f, True)
        self.assertTrue(self.s.is_viewed(f))
        self.assertFalse(self.s.viewed_changed(f))
        self.s.set_viewed(f, False)
        self.assertFalse(self.s.is_viewed(f))
        qt.wait_until(lambda: not self.s.busy)
        self.s.delete_comment(c["id"])
        self.assertTrue(qt.wait_until(lambda: not self.s.review["comments"]))

    def test_polling_picks_up_cli_writes(self):
        self.loaded()
        c = self.s.add_comment({"kind": "general", "body": "poll me"})
        qt.wait_until(lambda: self.s.review["comments"])
        hits = []
        self.s.reviewChanged.connect(lambda: hits.append(1))
        self.s.start()
        self.assertTrue(qt.wait_until(lambda: self.s._poll_prev is not None, 5))
        hits.clear()
        Store(Repo(str(self.work))).reply(c["id"], "agent", "fixed")
        self.assertTrue(qt.wait_until(
            lambda: hits and self.s.review["comments"][0]["replies"], timeout=6))

    def test_polling_detects_commit(self):
        self.loaded()
        self.s.start()
        self.assertTrue(qt.wait_until(lambda: self.s._poll_prev is not None, 5))
        hits = []
        self.s.filesChanged.connect(lambda: hits.append(1))
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t"}
        import os
        subprocess.run(["git", "commit", "--allow-empty", "-q", "-m", "poll"], cwd=self.work,
                       check=True, env={**os.environ, **env})
        try:
            self.assertTrue(qt.wait_until(lambda: hits, timeout=6))
        finally:
            subprocess.run(["git", "reset", "-q", "--hard", "HEAD~1"], cwd=self.work, check=True)

    def test_full_hunks(self):
        self.loaded()
        got = []
        self.s.full_hunks("app.py", got.append)
        self.assertTrue(qt.wait_until(lambda: got))
        self.assertEqual(len(got[0]), 1)
        self.assertTrue(len(got[0][0]["lines"]) > 10)

    def test_error_signal(self):
        errors = []
        self.s.error.connect(errors.append)
        with mock.patch.object(Repo, "files", side_effect=GitError("boom")):
            self.s.reload_code()
            self.assertTrue(qt.wait_until(lambda: errors))
        self.assertEqual(errors[0], "boom")
        self.assertIsNone(self.s.meta)


if __name__ == "__main__":
    unittest.main()
