# T01 — Package skeleton, venv, and core port

## Goal
Turn the working single-file prototype `legacy/evie_core.py` into the `premerge` package's Qt-free core plus CLI,
following the contracts in overview §6–§7. Remove everything web/HTTP related. Set up the venv.

## Read
- `docs/spec/00-overview.md`
- `legacy/evie_core.py` (≈850 lines; the logic is tested and correct — port it, don't redesign it)

## Create / modify
- `pyproject.toml`, `premerge/__init__.py`, `premerge/__main__.py`, `premerge/cli.py`
- `premerge/core/__init__.py`, `gitrepo.py`, `store.py`, `anchors.py`, `prompt.py`, `publish.py`
- `premerge/ui/__init__.py` (empty), `.gitignore` (`.venv/`, `__pycache__/`, `*.egg-info/`, `/shots/`)
- Delete `legacy/` at the end.

## Steps
1. **Venv.** `python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -e .` with
   `pyproject.toml`: name `premerge`, version `0.1.0`, `requires-python = ">=3.11"`, dependencies
   `["PySide6>=6.6", "Pygments>=2.17"]`, `[project.scripts] premerge = "premerge.cli:main"`, setuptools build backend,
   packages `premerge`, `premerge.core`, `premerge.ui`. If PySide6 can't be installed for this Python (no wheel for
   the interpreter version), **stop and report** the exact pip error — do not install another Python or any other
   package.
2. **gitrepo.py**: move `GitError`, `run_git`, `now`→ keep `now()` in store.py instead, `literal`, patch parsing
   (`HUNK_RE`, `unquote_path`, `_side_path`, `_git_header_paths`, `parse_patch`), `DIFF_OPTS`, `TEMPLATES`, `Repo`.
   Changes vs. legacy:
   - Config keys `premerge.base` / `premerge.forge` (were `evie.*`).
   - Constructor raises `GitError("… is not inside a git work tree")` instead of `SystemExit`.
   - Add `file_full(mode, path, old_path=None)` (legacy did this inline in `App.route` for `/api/file`:
     `files(mode, FULL_CONTEXT, [old, path] if old and old != path else [path])`, pick the entry whose `path`
     matches, return its hunks or `[]`).
   - Add `is_dirty()`, `ahead_behind()`, `user_name()`, `meta()` — `meta()` returns the Meta dict of overview §4
     (port `App.meta` without the `evie` key).
3. **store.py**: `Store`, `now()`, `new_comment`, `add_reply` from legacy. Rename `ApiError` → `StoreError(Exception)`
   (no HTTP codes). Storage dir `<common_dir>/premerge`. `description(data=None)` loads if `data` is None. Add the
   high-level methods of §6 (`add_comment`, `reply`, `set_status`, `edit_body`, `delete`, `set_viewed`,
   `set_description`), each a single `with self.edit()` transaction, mirroring what legacy `App.route` did for the
   corresponding endpoint. `add_comment` takes the head sha from `self.repo.head()`.
4. **anchors.py** (new): implement overview §4 "Anchors". `line_no(line, side)`: side old → `line["o"]` unless
   `t == "+"`; side new → `line["n"]` unless `t == "-"`. `locate_in_text(text_lines, c)` is the logic of legacy
   `locate()` after the file has been read (returns `(lineno|None, state)` with state `ok|moved|missing`).
5. **prompt.py**: `cli_cmd()` (legacy `evie_cmd`, checking for `premerge` on PATH resolving to an executable of
   this install — compare `shutil.which("premerge")` against `Path(sys.argv[0]).resolve()` and the venv's
   `bin/premerge`; fall back to `"<sys.executable> -m premerge"` quoted), `locate(repo, c)` (reads the file, calls
   `anchors.locate_in_text`; returns `(state, line)` with state `ok|moved|outdated` — `missing` is reported as
   `outdated`), `render_prompt` (legacy, with `premerge` wording; title line `# Local review of \`branch\` → \`target\``).
6. **publish.py**: split legacy `cmd_pr` into `plan()` (no I/O except git reads and `shutil.which`; fills
   `problems` instead of exiting: no remote, unknown forge, tool missing; `display` is the list of shell-quoted
   commands with a glab description shown as `<description>`) and `execute()` (runs push then create with
   `subprocess.run(..., capture_output=True, text=True)`, streams nothing, calls `on_output(text)` after each step,
   returns `(returncode, combined_output)`; stops at the first failure).
7. **cli.py**: argparse as overview §7 (prog `premerge`). No command or `gui` → `from premerge.ui.app import run_gui;
   return run_gui(args)` (import lazily; until T05 exists, an `ImportError` there should print
   `premerge: the app isn't built yet` and exit 1). `pr` prints the plan (title, description length/source, open
   comment warning, problems, `$ command` lines), exits 1 if there are problems, asks `Proceed? [y/N]` unless `-y`,
   then `execute` and print output. Catch `GitError`/`StoreError` → `premerge: msg`, exit 1. `main(argv=None) -> int`
   and `sys.exit(main())` in `__main__.py`.
8. Remove: `App`, `make_handler`, `STATIC_TYPES`, `cmd_serve`, `webbrowser`, `threading`, `traceback`, every
   reference to "evie". Delete `legacy/`.

## Acceptance
```sh
.venv/bin/python -c "import PySide6, pygments; print(PySide6.__version__)"
.venv/bin/python -c "import premerge.core.gitrepo, premerge.core.store, premerge.core.prompt, premerge.core.publish, premerge.core.anchors"
grep -rn "evie" premerge pyproject.toml && echo FAIL || echo ok
grep -rn "PySide6" premerge/core && echo FAIL || echo ok
```
Then, in a throwaway repo you create under `$TMPDIR` (a `main` with one commit pushed to a bare `origin`, then a
`feat/x` branch with a modified and an added file): `.venv/bin/premerge -C <work> describe`,
`premerge comments` (prints "No open review comments."), add a line comment via
`Store(Repo(work)).add_comment({...})` in a python one-liner, `premerge comments` shows it with a ```diff block,
`premerge reply <id> --resolve "done"` prints `<id>: resolved`, `premerge pr` without `gh` on a non-github remote
prints a problem and exits 1. Paste the outputs.
