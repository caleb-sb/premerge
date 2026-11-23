"""Git access: running git, parsing patches, and the Repo model (base, remote, forge, diffs)."""
from __future__ import annotations

import contextlib
import hashlib
import os
import re
import subprocess
from functools import cached_property
from pathlib import Path

MAX_UNTRACKED = 200
FULL_CONTEXT = 1_000_000
MODES = ("committed", "worktree")


class GitError(Exception):
    """A git command failed or the repository is unusable."""

def run_git(cwd, *args, check=True, ok=(0,), stdin=None) -> str:
    """Run `git args` in cwd and return stdout; raise GitError on a return code not in `ok`."""
    p = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=cwd, capture_output=True, input=stdin.encode() if stdin is not None else None,
    )
    if check and p.returncode not in ok:
        msg = p.stderr.decode("utf-8", "replace").strip()
        raise GitError(msg or f"git {args[0]} exited with {p.returncode}")
    return p.stdout.decode("utf-8", "replace")


def literal(paths) -> list[str]:
    """Wrap paths as literal git pathspecs."""
    return [f":(literal){p}" for p in paths]


# --------------------------------------------------------------------------- patch parsing

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")
_ESC = {"n": 10, "t": 9, '"': 34, "\\": 92, "a": 7, "b": 8, "f": 12, "r": 13, "v": 11}


def unquote_path(p: str) -> str:
    """Undo git's C-style path quoting."""
    if not (len(p) >= 2 and p[0] == '"' and p[-1] == '"'):
        return p
    s, out, i = p[1:-1], bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt in _ESC:
                out.append(_ESC[nxt]); i += 2; continue
            if re.fullmatch(r"[0-7]{3}", s[i + 1:i + 4]):
                out.append(int(s[i + 1:i + 4], 8)); i += 4; continue
        out += c.encode(); i += 1
    return out.decode("utf-8", "replace")


def _side_path(raw: str):
    raw = raw.rstrip("\t\r")
    if raw == "/dev/null":
        return None
    p = unquote_path(raw)
    return p[2:] if p[:2] in ("a/", "b/") else p


def _git_header_paths(rest: str):
    if rest.startswith('"'):
        m = re.match(r'^("(?:[^"\\]|\\.)*")\s+(.*)$', rest)
        if m:
            return _side_path(m[1]), _side_path(m[2])
    half = (len(rest) - 1) // 2
    a, b = rest[:half], rest[half + 1:]
    if a[2:] == b[2:]:
        return _side_path(a), _side_path(b)
    m = re.match(r"^(a/.*?) (b/.*)$", rest)
    return (_side_path(m[1]), _side_path(m[2])) if m else (None, None)


def parse_patch(text: str) -> list[dict]:
    """Parse unified `git diff` output into FileDiff dicts."""
    files: list[dict] = []
    f = hk = None
    rem_o = rem_n = o = n = 0

    def finish():
        if f is None:
            return
        f["hash"] = hashlib.sha1("\n".join(f.pop("_hdr")).encode()).hexdigest()[:12]
        if f["status"] == "added":
            f["oldPath"] = None
        elif f["status"] == "deleted":
            f["newPath"] = None
        f["path"] = f["newPath"] or f["oldPath"]

    for line in text.split("\n"):
        if hk is not None and (rem_o > 0 or rem_n > 0) and line[:1] in (" ", "-", "+", "\\", ""):
            tag, s = line[:1], line[1:]
            if tag == "\\":
                if hk["lines"]:
                    hk["lines"][-1]["noeol"] = True
            elif tag == "-":
                hk["lines"].append({"t": "-", "o": o, "n": None, "s": s})
                o += 1; rem_o -= 1; f["deletions"] += 1
            elif tag == "+":
                hk["lines"].append({"t": "+", "o": None, "n": n, "s": s})
                n += 1; rem_n -= 1; f["additions"] += 1
            else:
                hk["lines"].append({"t": " ", "o": o, "n": n, "s": s})
                o += 1; n += 1; rem_o -= 1; rem_n -= 1
            continue
        if line.startswith("\\") and hk is not None:
            if hk["lines"]:
                hk["lines"][-1]["noeol"] = True
            continue
        if line.startswith("diff --git "):
            finish()
            f = {"path": None, "oldPath": None, "newPath": None, "status": "modified", "binary": False,
                 "additions": 0, "deletions": 0, "hunks": [], "_hdr": [line]}
            f["oldPath"], f["newPath"] = _git_header_paths(line[11:])
            files.append(f)
            hk = None
            continue
        if f is None:
            continue
        if line.startswith("@@"):
            m = HUNK_RE.match(line)
            if not m:
                continue
            o, n = int(m[1]), int(m[3])
            rem_o = int(m[2]) if m[2] is not None else 1
            rem_n = int(m[4]) if m[4] is not None else 1
            hk = {"header": line, "lines": []}
            f["hunks"].append(hk)
            continue
        if hk is not None:
            continue
        f["_hdr"].append(line)
        if line.startswith("new file mode"):
            f["status"] = "added"
        elif line.startswith("deleted file mode"):
            f["status"] = "deleted"
        elif line.startswith("rename from "):
            f["oldPath"] = unquote_path(line[12:]); f["status"] = "renamed"
        elif line.startswith("rename to "):
            f["newPath"] = unquote_path(line[10:])
        elif line.startswith("copy from "):
            f["oldPath"] = unquote_path(line[10:]); f["status"] = "copied"
        elif line.startswith("copy to "):
            f["newPath"] = unquote_path(line[8:])
        elif line.startswith("similarity index "):
            with contextlib.suppress(ValueError):
                f["similarity"] = int(line[17:].rstrip("%"))
        elif line.startswith("old mode "):
            f["oldMode"] = line[9:]
        elif line.startswith("new mode "):
            f["newMode"] = line[9:]
        elif line.startswith("Binary files ") or line == "GIT binary patch":
            f["binary"] = True
        elif line.startswith("--- "):
            f["oldPath"] = _side_path(line[4:])
        elif line.startswith("+++ "):
            f["newPath"] = _side_path(line[4:])
    finish()
    return files


# --------------------------------------------------------------------------- repository

DIFF_OPTS = ["diff", "--no-color", "--no-ext-diff", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/"]

TEMPLATES = {
    "github": [".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md",
               "pull_request_template.md", "PULL_REQUEST_TEMPLATE.md",
               "docs/pull_request_template.md", "docs/PULL_REQUEST_TEMPLATE.md"],
    "gitlab": [".gitlab/merge_request_templates/Default.md", ".gitlab/merge_request_templates/default.md"],
}


class Repo:
    """A git work tree plus the PR context (base, remote, forge) used to preview a pull request."""

    def __init__(self, path=".", base=None, remote=None, forge=None):
        try:
            self.root = run_git(path, "rev-parse", "--show-toplevel").strip()
        except (GitError, OSError):
            raise GitError(f"{os.path.abspath(path)} is not inside a git work tree") from None
        self.common_dir = Path(run_git(self.root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
        self._remote, self._base, self._forge = remote, base, forge

    def git(self, *a, **k):
        return run_git(self.root, *a, **k)

    def _verify(self, ref):
        return bool(self.git("rev-parse", "--verify", "--quiet", ref + "^{commit}", check=False).strip())

    @cached_property
    def remote(self):
        if self._remote:
            return self._remote
        remotes = self.git("remote").split()
        if not remotes:
            return None
        up = self.git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False).strip()
        r = up.split("/", 1)[0] if "/" in up else ""
        if r in remotes:
            return r
        return "origin" if "origin" in remotes else remotes[0]

    @cached_property
    def base(self):
        if self._base:
            if not self._verify(self._base):
                raise GitError(f"base ref {self._base!r} not found")
            return self._base
        cands = []
        cfg = self.git("config", "--get", "premerge.base", check=False).strip()
        if cfg:
            cands.append(cfg)
        if self.remote:
            sym = self.git("symbolic-ref", "--quiet", "--short", f"refs/remotes/{self.remote}/HEAD", check=False).strip()
            if sym:
                cands.append(sym)
            cands += [f"{self.remote}/main", f"{self.remote}/master"]
        cands += ["main", "master"]
        for c in cands:
            if self._verify(c):
                return c
        raise GitError(f"could not find a base branch (tried {', '.join(cands)}); pass --base")

    @property
    def target_branch(self):
        b = self.base
        if self.remote and b.startswith(self.remote + "/"):
            return b[len(self.remote) + 1:]
        return b

    def head(self):
        return self.git("rev-parse", "HEAD").strip()

    def branch(self):
        b = self.git("rev-parse", "--abbrev-ref", "HEAD").strip()
        return b if b != "HEAD" else "detached-" + self.head()[:8]

    def merge_base(self):
        mb = self.git("merge-base", self.base, "HEAD", check=False).strip()
        if not mb:
            raise GitError(f"{self.base} and HEAD have no common ancestor")
        return mb

    def untracked(self, paths=None):
        args = ["ls-files", "--others", "--exclude-standard", "-z"]
        if paths:
            args += ["--", *literal(paths)]
        return [p for p in self.git(*args).split("\0") if p][:MAX_UNTRACKED]

    def patch(self, mode, ctx=3, paths=None):
        args = [*DIFF_OPTS, "-M", f"-U{ctx}", self.merge_base()]
        if mode == "committed":
            args.append("HEAD")
        if paths:
            args += ["--", *literal(paths)]
        text = self.git(*args)
        if mode == "worktree":
            for p in self.untracked(paths):
                if text and not text.endswith("\n"):
                    text += "\n"
                text += self.git(*DIFF_OPTS, "--no-index", f"-U{ctx}", "--", "/dev/null", p, ok=(0, 1))
        return text

    def files(self, mode, ctx=3, paths=None):
        return parse_patch(self.patch(mode, ctx, paths))

    def file_full(self, mode: str, path: str, old_path: str | None = None) -> list[dict]:
        """Hunks for one file with the whole file as context."""
        paths = [old_path, path] if old_path and old_path != path else [path]
        fs = self.files(mode, FULL_CONTEXT, paths)
        f = next((x for x in fs if x["path"] == path), fs[0] if fs else None)
        return f["hunks"] if f else []

    def commits(self):
        out = self.git("log", "--format=%H%x1f%h%x1f%an%x1f%aI%x1f%s%x1f%b%x1e", f"{self.merge_base()}..HEAD")
        res = []
        for rec in out.split("\x1e"):
            rec = rec.strip("\n")
            if not rec:
                continue
            sha, short, author, date, subject, body = (rec.split("\x1f") + [""] * 6)[:6]
            res.append({"sha": sha, "short": short, "author": author, "date": date,
                        "subject": subject, "body": body.strip()})
        return res

    def status_text(self):
        return self.git("status", "--porcelain=v1", "-z", "--untracked-files=all")

    def worktree_sig(self):
        out = self.status_text()
        sig = hashlib.sha1(out.encode())
        for ent in out.split("\0"):
            if len(ent) > 3:
                with contextlib.suppress(OSError):
                    st = os.stat(os.path.join(self.root, ent[3:]))
                    sig.update(f"{st.st_mtime_ns}:{st.st_size}".encode())
        return sig.hexdigest()[:16]

    def is_dirty(self) -> bool:
        """True if there are uncommitted or untracked changes."""
        return bool(self.status_text())

    def ahead_behind(self) -> tuple[int, int]:
        """(commits on HEAD not in base, commits in base not on HEAD), relative to the merge base."""
        mb = self.merge_base()
        ahead = int(self.git("rev-list", "--count", f"{mb}..HEAD").strip() or 0)
        behind = int(self.git("rev-list", "--count", f"HEAD..{self.base}").strip() or 0)
        return ahead, behind

    def user_name(self) -> str:
        """git user.name, or an empty string."""
        return self.git("config", "--get", "user.name", check=False).strip()

    def meta(self) -> dict:
        """The Meta dict (see the spec) describing this review."""
        mb = self.merge_base()
        ahead, behind = self.ahead_behind()
        return {
            "repo": os.path.basename(self.root), "root": self.root, "branch": self.branch(),
            "base": self.base, "target": self.target_branch, "remote": self.remote, **self.remote_info(),
            "head": self.head()[:10], "mergeBase": mb[:10], "ahead": ahead, "behind": behind,
            "user": self.user_name(), "dirty": self.is_dirty(),
        }

    def remote_info(self):
        url = self.git("remote", "get-url", self.remote, check=False).strip() if self.remote else ""
        host = path = ""
        m = re.match(r"^(?:[a-z+]+://)?(?:[^@/]+@)?([^/:]+)(?::\d+)?[:/](.+?)(?:\.git)?/?$", url)
        if m:
            host, path = m[1], m[2]
        forge = self._forge or self.git("config", "--get", "premerge.forge", check=False).strip() or None
        if not forge:
            forge = "github" if "github" in host else "gitlab" if "gitlab" in host else None
        return {"forge": forge, "host": host, "project": path, "webUrl": f"https://{host}/{path}" if host else None}

    def find_template(self, forge):
        order = TEMPLATES.get(forge, []) + [x for k, v in TEMPLATES.items() if k != forge for x in v]
        for rel in order:
            p = Path(self.root, rel)
            if p.is_file():
                return rel, p.read_text(errors="replace")
        d = Path(self.root, ".gitlab/merge_request_templates")
        if d.is_dir():
            for p in sorted(d.glob("*.md")):
                return str(p.relative_to(self.root)), p.read_text(errors="replace")
        return None, None

    def default_description(self, forge):
        commits = self.commits()
        if len(commits) == 1:
            title = commits[0]["subject"]
        else:
            b = re.sub(r"^[^/]+/", "", self.branch())
            b = re.sub(r"[-_]+", " ", b).strip()
            title = b[:1].upper() + b[1:]
        rel, tpl = self.find_template(forge)
        if tpl:
            return title, tpl, f"template {rel}"
        if len(commits) == 1:
            return title, commits[0]["body"], "the commit message"
        if commits:
            return title, "\n".join(f"- {c['subject']}" for c in reversed(commits)), "the commit list"
        return title, "", "nothing"


