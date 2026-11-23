import unittest

from premerge.core.paths import build_tree, tree_order


class PathsTest(unittest.TestCase):
    def test_order(self):
        paths = ["b.txt", "A.txt", "src/z.py", "src/a/x.py", "Docs/r.md", "a.txt"]
        self.assertEqual(tree_order(paths),
                         ["Docs/r.md", "src/a/x.py", "src/z.py", "A.txt", "a.txt", "b.txt"])

    def test_compress(self):
        t = build_tree(["src/main/java/A.java", "src/main/java/B.java", "README.md"])
        self.assertEqual(t["name"], "")
        self.assertEqual(t["files"], ["README.md"])
        (d,) = t["dirs"]
        self.assertEqual((d["name"], d["path"]), ("src/main/java", "src/main/java"))
        self.assertEqual(d["files"], ["src/main/java/A.java", "src/main/java/B.java"])

    def test_no_merge_with_files_or_root(self):
        t = build_tree(["only/a/f.txt", "x/g.txt", "x/y/h.txt"])
        self.assertEqual([d["name"] for d in t["dirs"]], ["only/a", "x"])
        self.assertEqual([d["name"] for d in t["dirs"][1]["dirs"]], ["y"])

    def test_empty(self):
        self.assertEqual(build_tree([]), {"name": "", "path": "", "dirs": [], "files": []})


if __name__ == "__main__":
    unittest.main()
