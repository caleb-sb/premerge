# T04 — Tree ordering and the Session model

## Goal
`core/paths.py` (pure helpers) and `ui/session.py`: the single QObject that owns repo/store state, loads data off the
UI thread, polls for changes, and performs mutations. All widgets talk to the Session, never to Repo/Store directly.

## Read
- `docs/spec/00-overview.md`
- Signatures only (not bodies) of `premerge/core/gitrepo.py` and `premerge/core/store.py`; `premerge/ui/jobs.py`;
  `tests/qt.py`; `tests/fixture.py` (just `make_fixture`'s docstring/signature)

## Create
`premerge/core/paths.py`, `premerge/ui/session.py`, `tests/test_paths.py`, `tests/test_session.py`

## core/paths.py
- `tree_order(paths: list[str]) -> list[str]`: depth-first order where, at each directory level, subdirectories
  come before files, each group sorted case-insensitively (`str.casefold`, then the raw string to break ties).
- `build_tree(paths) -> dict`: root `{"name": "", "path": "", "dirs": [...], "files": [...]}`; `files` holds full
  paths; dirs/files sorted as in `tree_order`; compress chains: a dir whose only content is one subdir merges with it
  (`name` "src/main/java", `path` the deepest full path). The root is never merged.

## ui/session.py — `class Session(QObject)`

Constructor `Session(repo: Repo, parent=None)`; creates `Store(repo)`.

**Signals:** `metaChanged()`, `filesChanged()`, `commitsChanged()`, `reviewChanged()`, `busyChanged(bool)`,
`error(str)`, `modeChanged(str)`, `viewChanged(str)`.

**State (read-only attributes for widgets):** `repo`, `store`, `mode` (`"committed"` | `"worktree"`),
`view` (`"unified"` | `"split"`), `meta: dict|None`, `files: list[FileDiff]` (in `tree_order` of their paths),
`commits: list[dict]`, `review: dict` = `{"comments": [...], "viewed": {...}, "description": Description}`,
`busy: bool`, `last_refresh: datetime|None`.

**Loading** (all via `jobs.run`; each kind has a generation counter so stale results are dropped; if a load of the
same kind is already running, set a "pending" flag and rerun once it finishes):
- `reload_all()` → meta, files, commits, review.
- `reload_code()` → meta, files, commits.  `reload_review()` → review.
- Errors (`GitError`, etc.) → `error.emit(str(exc))`, state unchanged.
- `busy` is true while any load runs.

**Setters:** `set_mode(mode)` (emit `modeChanged`, reload files), `set_view(view)` (emit `viewChanged`, no reload).

**Queries:** `file(path) -> FileDiff|None`; `comments_for(path) -> list` (line + file comments with that path);
`general_comments()`; `open_count() -> int`; `is_viewed(f) -> bool` (stored hash == f["hash"]);
`viewed_changed(f) -> bool` (stored but different); `prompt_text() -> str` (`core.prompt.render_prompt`, synchronous);
`full_hunks(path, callback)`: async `repo.file_full(mode, path, oldPath)`, cached per `(mode, path, file hash)`,
cache cleared when files reload; callback receives the hunks.

**Mutations** (synchronous Store calls on the UI thread — they're small file writes — then `reload_review()`; on
`StoreError` emit `error`): `add_comment(fields) -> dict|None`, `reply(cid, text, resolve=False)` (author `you`),
`set_status(cid, status)`, `edit_body(cid, text)`, `delete_comment(cid)`, `set_viewed(f, viewed: bool)` (stores
`f["hash"]` or None; update `self.review["viewed"]` immediately and emit `reviewChanged` before the reload so the UI
is instant), `save_description(title, body)`, `reset_description()`.

**Polling:** a `QTimer` every 2000 ms (start in `start()`, stop in `stop()`; not started by the constructor). Each
tick, if no poll is in flight, run a job computing `(branch, head, worktree_sig if mode == "worktree" else None,
store.rev())`, then compare with the previous tick: branch or head changed → `reload_all()`; worktree sig changed →
`reload_code()`; store rev changed → `reload_review()`. The first tick only records values. Swallow poll errors
silently (emit `error` only if the error message changed since the last poll error).

## tests/test_session.py (offscreen, fixture repo)
- `reload_all()` populates meta/files/commits/review and emits each signal once; files are in tree order.
- `set_mode("worktree")` adds `u.txt`.
- `add_comment` (line) → `review["comments"]` has it after `wait_until`; `reply` with resolve marks it resolved;
  `set_viewed` → `is_viewed` true immediately.
- Polling: `start()`, then write a reply through a *separate* `Store(Repo(work))` (simulating the CLI) → within 5 s
  `reviewChanged` fires and the reply is present. Commit a change in the fixture → `filesChanged` fires.
- `full_hunks` returns one hunk with all lines of `app.py`.
- A GitError in a load reaches `error`.

## Acceptance
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v` — all pass.
