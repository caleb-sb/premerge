import unittest

from premerge.core.gitrepo import FULL_CONTEXT, Repo, parse_patch
from tests.base import FixtureCase
from tests.fixture import FIXTURE_FILES_COMMITTED


class RepoTests(FixtureCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo = Repo(str(cls.work))
        cls.committed = {f["path"]: f for f in cls.repo.files("committed")}

    def test_resolution(self):
        self.assertEqual(self.repo.base, "origin/main")
        self.assertEqual(self.repo.target_branch, "main")
        self.assertEqual(self.repo.remote, "origin")
        self.assertEqual(self.repo.branch(), "feat/thing")

    def test_committed_files(self):
        self.assertEqual(set(self.committed), FIXTURE_FILES_COMMITTED)
        self.assertNotIn("main_only.txt", self.committed)
        c = self.committed
        self.assertEqual(c["bin.dat"]["status"], "added")
        self.assertTrue(c["bin.dat"]["binary"])
        self.assertEqual(c["gone.txt"]["status"], "deleted")
        self.assertIsNone(c["gone.txt"]["newPath"])
        self.assertEqual(c["with space.txt"]["status"], "added")
        self.assertIsNone(c["with space.txt"]["oldPath"])
        self.assertEqual(c["moved.txt"]["status"], "renamed")
        self.assertEqual(c["moved.txt"]["oldPath"], "move_me.txt")
        self.assertEqual(c["moved.txt"]["hunks"], [])
        self.assertGreaterEqual(len(c["app.py"]["hunks"]), 2)
        lines = [ln for h in c["eol.txt"]["hunks"] for ln in h["lines"]]
        self.assertEqual([ln["t"] for ln in lines if ln.get("noeol")], ["-", "+"])

    def test_worktree_mode(self):
        wt = {f["path"]: f for f in self.repo.files("worktree")}
        self.assertEqual(set(wt), FIXTURE_FILES_COMMITTED | {"u.txt"})
        self.assertEqual(wt["u.txt"]["status"], "added")
        for p, f in self.committed.items():
            if p == "keep.txt":
                self.assertNotEqual(f["hash"], wt[p]["hash"])
            else:
                self.assertEqual(f["hash"], wt[p]["hash"], p)

    def test_file_full(self):
        hunks = self.repo.file_full("committed", "app.py")
        self.assertEqual(len(hunks), 1)
        with open(self.work / "app.py") as fh:
            nlines = len(fh.read().split("\n")) - 1
        self.assertEqual(sum(1 for ln in hunks[0]["lines"] if ln["t"] != "-"), nlines)

    def test_line_numbers_consistent(self):
        for f in self.committed.values():
            for h in f["hunks"]:
                o = n = None
                for ln in h["lines"]:
                    if ln["t"] != "+":
                        self.assertTrue(o is None or ln["o"] == o + 1)
                        o = ln["o"]
                    if ln["t"] != "-":
                        self.assertTrue(n is None or ln["n"] == n + 1)
                        n = ln["n"]
                    if ln["t"] == " ":
                        self.assertIsNotNone(ln["o"])
                        self.assertIsNotNone(ln["n"])

    def test_commits_and_meta(self):
        self.assertEqual([c["subject"] for c in self.repo.commits()], ["Tweak app", "Change things"])
        m = self.repo.meta()
        self.assertEqual((m["ahead"], m["behind"]), (2, 1))
        self.assertTrue(m["dirty"])
        self.assertEqual(m["user"], "Tester")

    def test_default_description(self):
        title, body, source = self.repo.default_description("github")
        self.assertEqual(title, "Thing")
        self.assertEqual(body, "## Summary\n\n## Testing\n")
        self.assertIn("pull_request_template", source)

    def test_worktree_sig_changes(self):
        before = self.repo.worktree_sig()
        (self.work / "u.txt").write_text("untracked, edited\n")
        try:
            self.assertNotEqual(before, self.repo.worktree_sig())
        finally:
            (self.work / "u.txt").write_text("untracked\n")


class ParsePatchTests(unittest.TestCase):
    def test_quoted_path_with_tab(self):
        text = ('diff --git "a/we\\tird.txt" "b/we\\tird.txt"\nindex 1..2 100644\n'
                '--- "a/we\\tird.txt"\n+++ "b/we\\tird.txt"\n@@ -1 +1 @@\n-a\n+b\n')
        (f,) = parse_patch(text)
        self.assertEqual(f["path"], "we\tird.txt")
        self.assertEqual((f["additions"], f["deletions"]), (1, 1))

    def test_no_newline_marker(self):
        text = ("diff --git a/x b/x\nindex 1..2 100644\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n"
                "-a\n\\ No newline at end of file\n+b\n\\ No newline at end of file\n")
        (f,) = parse_patch(text)
        lines = f["hunks"][0]["lines"]
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(ln.get("noeol") for ln in lines))

    def test_dashes_content_is_not_a_header(self):
        text = ("diff --git a/x b/x\nindex 1..2 100644\n--- a/x\n+++ b/x\n@@ -1,2 +1,1 @@\n"
                "--- foo\n keep\n")
        (f,) = parse_patch(text)
        self.assertEqual(f["path"], "x")
        self.assertEqual(f["deletions"], 1)
        self.assertEqual(f["hunks"][0]["lines"][0], {"t": "-", "o": 1, "n": None, "s": "-- foo"})

    def test_mode_only_change(self):
        text = "diff --git a/run.sh b/run.sh\nold mode 100644\nnew mode 100755\n"
        (f,) = parse_patch(text)
        self.assertEqual((f["oldMode"], f["newMode"]), ("100644", "100755"))
        self.assertEqual(f["hunks"], [])
        self.assertEqual(f["path"], "run.sh")
        self.assertEqual(f["status"], "modified")

    def test_full_context_constant(self):
        self.assertGreater(FULL_CONTEXT, 100000)


if __name__ == "__main__":
    unittest.main()
