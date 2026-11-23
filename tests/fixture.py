"""Builds a throwaway git repository (origin + work clone) that exercises every diff case."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

FIXTURE_FILES_COMMITTED = {
    "keep.txt", "gone.txt", "moved.txt", "with space.txt", "eol.txt", "bin.dat", "app.py",
}

APP_PY = '''"""Sample application."""
import os
import json


class Service:
    """A tiny service."""

    def __init__(self, name):
        self.name = name
        self.items = []

    def add(self, item):
        self.items.append(item)
        return len(self.items)

    def dump(self):
        return json.dumps({"name": self.name, "items": self.items})


def helper(a, b):
    return a + b


def other(x):
    return x * 2


def more(x):
    return x - 1


def main():
    svc = Service("demo")
    svc.add(1)
    print(svc.dump())
    print(os.getcwd())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def isolated_env() -> dict[str, str]:
    """Environment for git that ignores the user's and the system's git config."""
    empty = Path(os.environ.get("TMPDIR", "/tmp")) / "premerge-empty-gitconfig"
    empty.touch()
    return {**os.environ, "GIT_CONFIG_GLOBAL": str(empty), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Tester", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "Tester", "GIT_COMMITTER_EMAIL": "t@example.com"}


def git(cwd: Path, *args: str) -> str:
    """Run git in `cwd` with isolated config; raise on failure."""
    p = subprocess.run(["git", "-c", "user.name=Tester", "-c", "user.email=t@example.com", *args],
                       cwd=cwd, env=isolated_env(), capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr}")
    return p.stdout


def write(path: Path, text: str | bytes) -> None:
    """Write text or bytes, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_bytes(text.encode())


def make_fixture(root: Path) -> Path:
    """Create root/origin.git and root/work on branch feat/thing; return the work dir."""
    root = Path(root)
    origin, work = root / "origin.git", root / "work"
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "--bare", "-b", "main", str(origin))
    work.mkdir()
    git(work, "init", "-b", "main")
    git(work, "config", "user.name", "Tester")
    git(work, "config", "user.email", "t@example.com")
    git(work, "remote", "add", "origin", str(origin))
    write(work / "keep.txt", "a\nb\nc\n")
    write(work / "gone.txt", "x\n")
    write(work / "move_me.txt", "".join(f"{i}\n" for i in range(1, 31)))
    write(work / "eol.txt", "no eol")
    write(work / "app.py", APP_PY)
    write(work / ".github" / "pull_request_template.md", "## Summary\n\n## Testing\n")
    git(work, "add", "-A")
    git(work, "commit", "-m", "Initial")
    git(work, "push", "-u", "origin", "main")
    git(work, "remote", "set-head", "origin", "main")

    git(work, "checkout", "-b", "feat/thing")
    write(work / "keep.txt", "a\nB\nc\nd\n")
    git(work, "rm", "-q", "gone.txt")
    git(work, "mv", "move_me.txt", "moved.txt")
    write(work / "with space.txt", "new\n")
    write(work / "eol.txt", "no eol2")
    write(work / "bin.dat", b"\x00\x01\x02")
    app = APP_PY.replace("import json\n", "import json\nimport sys\n")
    app = app.replace("    print(os.getcwd())\n    return 0\n", "    print(os.getcwd(), file=sys.stderr)\n    return 1\n")
    write(work / "app.py", app)
    git(work, "add", "-A")
    git(work, "commit", "-m", "Change things")
    write(work / "app.py", app.replace("return a + b", "return b + a"))
    git(work, "commit", "-am", "Tweak app")

    git(work, "checkout", "main")
    write(work / "main_only.txt", "main\n")
    git(work, "add", "-A")
    git(work, "commit", "-m", "Main only")
    git(work, "push", "origin", "main")
    git(work, "checkout", "feat/thing")

    write(work / "u.txt", "untracked\n")
    with open(work / "keep.txt", "a") as f:
        f.write("wt\n")
    return work
