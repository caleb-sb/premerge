# premerge — shared spec (read this first, every task)

premerge is a **desktop app** (Python + PySide6 Qt **widgets**) that previews the current git branch as if a
pull request (GitHub) / merge request (GitLab) had been opened against the remote main branch. The user reviews the
diff in a file tree + diff view, leaves inline comments, and a coding agent (Claude Code) reads those comments
through a CLI, fixes the code, and replies. The user also drafts the PR title/description here; `premerge pr`
then creates the real PR/MR with `gh` / `glab`.

Every task file in `docs/spec/tasks/` relies on this document. Where a task and this document disagree, the task
wins for that task's scope; never change a contract in §6 unless your task says so.

## 1. Platforms, stack, rules

- Must run on **Linux** (Fedora, Wayland/Hyprland and X11) and **macOS on Apple Silicon**. No platform-only APIs
  except where guarded (`sys.platform`). `fcntl` is fine (both are POSIX).
- Python ≥ 3.11. Dependencies: **PySide6 ≥ 6.6** and **Pygments ≥ 2.17**. Nothing else. Do **not** use QtWebEngine,
  QML, or any web view. Do not install anything else (the user requires approval for installs).
- `premerge/core/` must **never import Qt** (the CLI must work without a display).
- Git is driven only through the `git` CLI via `core.gitrepo.run_git`.
- The venv is `./.venv`; run things with `.venv/bin/python`. Tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v`.
- Style: type hints on public functions, short docstrings, no dead code, no commented-out code. PySide6 enums fully
  qualified (`Qt.AlignmentFlag.AlignLeft`). Use `Ctrl` in shortcuts (Qt maps it to ⌘ on macOS); prefer
  `QKeySequence.StandardKey` where one exists.
- Long-running work (anything that runs git) in the UI goes through `ui.jobs.run` — never block the UI thread on
  git except trivially fast store writes.
- The reference desktop app for look & feel is pdfile at `~/dev/pdfile/pdfile/` (PySide6). Only task T03 reads it.

## 2. Repository layout (final)

```
pyproject.toml            # name "premerge", script premerge = "premerge.cli:main"
README.md
premerge/
  __init__.py  __main__.py (calls cli.main)  cli.py
  core/  __init__.py gitrepo.py store.py anchors.py prompt.py publish.py paths.py
  ui/    __init__.py app.py theme.py icons.py jobs.py markdown.py session.py window.py
         commits.py filetree.py syntax.py diffview.py comments.py filepage.py overview.py prdialog.py
tests/   qt.py fixture.py test_*.py
tools/   shot.py                  # offscreen screenshots for visual review
skills/premerge-review/SKILL.md   # Claude Code skill for the agent side
docs/spec/                        # this spec
```

## 3. Concepts

- **Base**: the ref the PR targets, e.g. `origin/main`. Resolution order: `--base` flag → `git config premerge.base`
  → `refs/remotes/<remote>/HEAD` → `<remote>/main` → `<remote>/master` → `main` → `master`.
  **Target branch** = base without the `<remote>/` prefix (`main`).
- **Remote**: `--remote` → remote of the branch's upstream → `origin` → first remote.
- **Forge**: `--forge` → `git config premerge.forge` → `github` if the remote host contains "github", `gitlab` if it
  contains "gitlab", else `None`.
- **The diff** is always `merge-base(base, HEAD)` → X (what a PR shows; commits only on main are excluded):
  - mode `committed`: X = `HEAD`.
  - mode `worktree`: X = the working tree, including untracked (not ignored) files (max 200).
- **Store**: review state for one branch lives in `<git-common-dir>/premerge/<branch-slug>.json` (slug: every run of
  chars outside `[A-Za-z0-9._-]` becomes `__`). It is inside `.git`, so it is never committed. Writes are
  `fcntl.flock`ed on `<dir>/.lock` and atomic (write tmp + `os.replace`). The CLI and the app write it concurrently.
- **Viewed**: `viewed[path] = file.hash`. A file counts as viewed only when the stored hash equals its current hash;
  if it differs the UI says "Changed since viewed".
- **Agent loop**: the user comments in the app → the agent runs `premerge comments` (a Markdown prompt) → changes code
  → `premerge reply <id> --resolve "what changed"` → the app picks up the change within ~2 s and shows the reply.
  A reply written by the user (author `you`) re-opens a resolved thread.

## 4. Data shapes (plain dicts; JSON-compatible)

```text
FileDiff  {path, oldPath, newPath, status: "added"|"modified"|"deleted"|"renamed"|"copied",
           binary: bool, additions: int, deletions: int, hunks: [Hunk], hash: str (12 hex),
           similarity?: int, oldMode?: str, newMode?: str}
           path = newPath or oldPath. added → oldPath None. deleted → newPath None. modified → oldPath == path.
Hunk      {header: "@@ -a,b +c,d @@ section", lines: [Line]}
Line      {t: " "|"+"|"-", o: int|None (old line no.), n: int|None (new line no.), s: str (text, no newline),
           noeol?: True}
Comment   {id: 6 hex, kind: "line"|"file"|"general", body: str, author: "you", status: "open"|"resolved",
           created: ISO-8601 UTC, updated: ISO, head: sha at creation, replies: [Reply],
           # kind "line" only:
           path, oldPath, side: "old"|"new", line: int (last line of range, 1-based), startLine: int,
           anchorText: str (text of `line`), context: [str]  (diff lines with prefix " ", "+", "-"; ≤ 60)
           # kind "file": path}
Reply     {id: 6 hex, author: "you"|"agent", body, created}
StoreFile {version: 1, branch, title: str|None, body: str|None, comments: [Comment], viewed: {path: hash}}
Description {title, body, saved: bool, source: str}   # title/body fall back to defaults when not saved:
           # 1 commit → its subject/body; otherwise title from branch name ("feat/add-login" → "Add login");
           # body: PR/MR template file if present (.github/pull_request_template.md, .gitlab/merge_request_templates/
           # Default.md, …) else bullet list of commit subjects. source says where it came from.
Meta      {repo, root, branch, base, target, remote, forge, host, project, webUrl, head (10 chars),
           mergeBase (10 chars), ahead: int, behind: int, user: str (git user.name), dirty: bool}
```

**Line comment sides.** `side == "new"` → `line` is a new-file line number (`Line.n`); `"old"` → old-file number
(`Line.o`). Selection rule in the UI: a `-` line is side old; `+` and context lines are side new. A range is always on
one side (the side of where the selection started).

**Anchors** (`core/anchors.py`, used by both UI and prompt): a comment is placed on the row whose line number on its
side equals `line` *and* whose text equals `anchorText` (state `ok`); otherwise on the nearest row (by line-number
distance) with that side defined and the same text, if `anchorText.strip()` is non-empty (state `moved`); otherwise
it's `missing` ("outdated").

## 5. Look & feel — Tokyo Night **Night** only

The app always uses pdfile's Tokyo Night *Night* palette (no light theme). `ui/theme.py` (task T03) holds every
colour; no other module hard-codes a colour — they read `theme.NIGHT` fields. Base palette (from pdfile):

```
bg #1a1b26  bg_dark #16161e  bg_highlight #292e42  canvas #101014  border #2a2c3c
fg #c0caf5  fg_dark #a9b1d6  muted #565f89  gutter #3b4261  accent #7aa2f7  accent_soft #2c3a5e
on_accent #16161e  shadow #000000  ok #9ece6a  warn #e0af68  bad #f7768e
```
Added for premerge:
```
diff_add_bg #20303b   diff_add_gutter #1f3d3e   diff_del_bg #37222c   diff_del_gutter #4b2632
hunk_bg #1f2335       hunk_fg #7aa2f7           sel_bg #283457        sel_gutter #3d59a1
st_added #9ece6a  st_modified #e0af68  st_deleted #f7768e  st_renamed #7dcfff     # file status letters A M D R
you #7aa2f7  agent #bb9af7                                                         # comment authors
syntax: keyword #bb9af7, constant (Keyword.Constant) #ff9e64, type/class/builtin #2ac3de, function #7aa2f7,
  decorator #e0af68, tag #f7768e, attribute #73daca, string #9ece6a, escape/regex #b4f9f8, number #ff9e64,
  comment #565f89 (italic), operator/punctuation #89ddff, heading #7aa2f7 (bold), error #db4b4b, default fg
```
Code font: `QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)` at 13 px. UI font: system default.
Icons: Lucide-style line icons drawn by `ui/icons.py` (copied from pdfile and extended), tinted per theme.

### Window layout

```
┌ toolbar ──────────────────────────────────────────────────────────────────────────────────────────┐
│ ⎇ repo  feat/x → main │ [Committed|+ Working tree] [Unified|Split] ⟳          [⧉ Agent prompt · 3 | ⌄] │
├───────────────────────────────────────────────────────────────────────────────────────────────────┤
│  Add login flow                                                            (PR title, large)      │
│  ● Local preview   Caleb wants to merge 3 commits into main from feat/x  ·  main is 2 ahead        │
│  Overview │ Commits 3 │ Files changed 7                                         +120 −30          │
├───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Files tab:                                                                                        │
│ ┌ tree ─────────────┐ ┌ file header: M src/app.py  +12 −3  💬2   ‹ ›  [⇕ Full file] [💬] [☐ Viewed] ┐ │
│ │ [filter…]         │ │ file comments / outdated comments                                       │ │
│ │ 3/7 viewed ▓▓░░   │ │ @@ -10,6 +10,8 @@ def main                                               │ │
│ │ ▾ src/            │ │  10  10   import os                                                     │ │
│ │   M app.py  💬2   │ │      11 + import sys                                                     │ │
│ │   A util.py ✓     │ │ ┌ thread ───────────────────────────────────────────┐                  │ │
│ │ D old.txt         │ │ │ You · 5m ago: why sys?                            │                  │ │
│ └───────────────────┘ │ │ 🤖 Agent · 1m ago: removed it                      │                  │ │
│                       │ └ [Reply…]  [Resolve] ────────────────────────────────┘                  │ │
│                       └───────────────────────────────────────────────────────────────────────────┘ │
├ status bar: origin/main @ 1a2b3c4 · HEAD 5d6e7f8 · last refreshed 12:01:03 ───────────────────────┤
```
The Files tab shows **one file at a time** (selected in the tree), like desktop diff tools. Overview = description
card + conversation (general comments) + review-comment summary + details sidebar. Commits = commit list.

## 6. Module contracts (public API — later tasks rely on these exact names)

### core/gitrepo.py
`class GitError(Exception)` · `run_git(cwd, *args, check=True, ok=(0,), stdin=None) -> str` ·
`parse_patch(text) -> list[FileDiff]` · `MODES = ("committed", "worktree")` · `FULL_CONTEXT = 1_000_000`

`class Repo(path=".", base=None, remote=None, forge=None)` — raises `GitError` if `path` is not in a work tree.
Attributes `root: str`, `common_dir: Path`. Cached properties `remote: str|None`, `base: str` (raises GitError),
property `target_branch: str`. Methods: `git(*args, **kw)`, `head()`, `branch()` (detached → `detached-<sha8>`),
`merge_base()`, `files(mode, ctx=3, paths=None) -> list[FileDiff]`,
`file_full(mode, path, old_path=None) -> list[Hunk]` (whole file as context), `commits() -> list[dict]`
(`{sha, short, author, date (ISO), subject, body}`, newest first), `status_text()`, `worktree_sig() -> str`
(changes whenever any changed/untracked file changes), `is_dirty() -> bool`, `ahead_behind() -> (int, int)`,
`user_name() -> str`, `remote_info() -> {forge, host, project, webUrl}`, `find_template(forge) -> (rel|None, text|None)`,
`default_description(forge) -> (title, body, source)`, `meta() -> Meta`.

### core/store.py
`class StoreError(Exception)` (bad input / unknown id) ·
`class Store(repo)`: `path(branch=None) -> Path`, `load() -> StoreFile`, `edit()` (context manager yielding the
StoreFile dict, saved on exit), `rev() -> int` (mtime_ns of the file, 0 if none), `description(data=None) -> Description`,
`find(data, cid) -> Comment` (static; exact id or unique prefix ≥ 3 chars),
`add_comment(fields: dict) -> Comment` (fields as in §4 minus id/author/status/created/updated/head/replies;
validated), `reply(cid, author, text, resolve=False) -> Comment`, `set_status(cid, status) -> Comment`,
`edit_body(cid, text) -> Comment`, `delete(cid) -> None`, `set_viewed(path, hash_or_None) -> None`,
`set_description(title, body) -> None` (both `None` = reset to defaults).

### core/anchors.py
`line_no(line, side) -> int|None` · `locate_in_rows(lines: list[Line], comment) -> (index|None, "ok"|"moved"|"missing")`
· `locate_in_text(text_lines: list[str], comment) -> (lineno|None, state)`.

### core/prompt.py
`cli_cmd() -> str` ("premerge" if that's on PATH and is this install, else an absolute invocation) ·
`locate(repo, comment) -> (state, line|None)` (line comments, against the working tree for side new, the merge base
for side old) · `render_prompt(repo, data, include_all=False) -> str` (Markdown for the agent).

### core/publish.py
`@dataclass PrPlan(forge, tool, branch, target, remote, title, body, open_comments, push_cmd: list|None,
create_cmd: list, stdin: str|None, display: list[str], problems: list[str])` ·
`plan(repo, store, draft=False, push=True) -> PrPlan` (never raises for user-fixable problems; lists them in
`problems`, e.g. "gh is not installed") · `execute(plan, cwd, on_output=None) -> (returncode, output_text)`.

### core/paths.py
`tree_order(paths) -> list[str]` (directories before files at each level, case-insensitive name order) ·
`build_tree(paths) -> Node` where `Node = {name, path, dirs: [Node], files: [str]}`, with single-child directory
chains compressed (`src/main/java` as one node).

### ui (Qt) — summarised; full detail in each task
- `ui.theme`: `Theme` dataclass, `NIGHT`, `stylesheet(t)`, `apply(app)`, `syntax_color(ttype) -> (hex, bold, italic)`.
- `ui.icons`: `icon(name, t=NIGHT, color=None) -> QIcon`, `pixmap(name, color, px) -> QPixmap`.
- `ui.jobs`: `run(fn, *args, on_done=None, on_error=None, **kw)` — runs in `QThreadPool.globalInstance()`,
  callbacks on the GUI thread.
- `ui.markdown`: `MarkdownView(QTextBrowser)` auto-height, read-only, links open externally; `set_markdown(text)`.
- `ui.session`: `Session(QObject)` — the only owner of repo/store state; see T04.
- `ui.filetree.FileTree`, `ui.syntax.highlight_lines`, `ui.diffview.DiffBody`, `ui.comments.{CommentThread, Composer}`,
  `ui.filepage.FilesPage`, `ui.overview.OverviewPage`, `ui.commits.CommitsPage`, `ui.prdialog.CreatePrDialog`,
  `ui.window.MainWindow`, `ui.app.run_gui(args) -> int`.

## 7. CLI (final)

```
premerge [-C DIR] [--base REF] [--remote NAME] [--forge github|gitlab] [COMMAND]
  (no command) | gui        open the app for the repo at DIR (default .)
  comments [--all] [--json] print open comments as an agent prompt (Markdown) / JSON
  reply ID [TEXT|-] [--resolve] [--as agent|you]   default author agent; - reads stdin
  resolve ID | reopen ID
  describe [--title T] [--body B | --body-file F|-] [--reset] [--json]   prints "# title\n\nbody"
  pr [--draft] [--no-push] [-y]   shows the plan, asks y/N, pushes, runs gh/glab
```
Errors print `premerge: <message>` to stderr and exit 1.

## 8. Testing & screenshots

- `tests/fixture.py: make_fixture(root: Path) -> Path` builds a bare `origin.git` + a `work` clone with branch
  `feat/thing` covering: modified, added, deleted, renamed, binary, file with a space, missing final newline, a
  Python file with two hunks, a commit only on main, an untracked file, an uncommitted edit, a PR template. Returns
  the work dir. (T02)
- `tests/qt.py`: `app()` singleton QApplication (offscreen), `wait_until(pred, timeout=5.0)` pumping events. (T03)
- `tools/shot.py OUT_DIR`: builds a fixture in a temp dir, opens `MainWindow` at 1440×900 offscreen, drives it and
  saves PNGs (`QWidget.grab()`). Each UI task adds its shots. The orchestrator **looks at these images**. (T05+)

## 9. Rules for implementing a task

1. Read this file and your task file. Read only the other files your task lists — your context is limited.
2. Touch only the files your task lists. Keep every contract in §6.
3. If something is ambiguous, pick the simplest option consistent with this spec and say so in your report.
4. Finish only when the task's acceptance checks pass. Run them; paste the real output.
5. End with a report: files changed, decisions/deviations, acceptance output, anything left undone.
