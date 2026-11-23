# T05 — App entry, main window shell, commits tab, screenshot tool

## Goal
Launchable app: `premerge` opens a themed main window with toolbar, PR header, tab bar (Overview / Commits / Files
changed), status bar and menus. Commits tab is complete; Overview and Files are placeholders that later tasks
replace. Plus `tools/shot.py`.

## Read
- `docs/spec/00-overview.md` (§5 window layout)
- `premerge/ui/session.py` (public API part), `premerge/ui/theme.py` (field names + stylesheet object names),
  `premerge/ui/icons.py` (names only), `premerge/cli.py` (the gui branch), `tests/qt.py`, `tests/fixture.py` (signature)

## Create / modify
`premerge/ui/app.py`, `premerge/ui/window.py`, `premerge/ui/commits.py`, `tools/shot.py`, `tests/test_ui_window.py`;
modify `premerge/cli.py` only to remove the "isn't built yet" fallback.

## app.py — `run_gui(args) -> int`
- On Linux, pdfile's platform-theme fallback: if `QT_QPA_PLATFORMTHEME` names a theme plugin missing from PySide6's
  `platformthemes` plugin dir, set it to `xdgdesktopportal`; pop `QT_STYLE_OVERRIDE`.
- `QApplication`, `setApplicationName("premerge")`, `setOrganizationName("premerge")`, window icon = `git_pr` icon
  in accent; `theme.apply(app)`.
- Build `Repo(args.repo, args.base, args.remote, args.forge)`; on `GitError` show a `QMessageBox.critical` with the
  message and a "Choose repository…" button (QFileDialog directory) that retries; Cancel → return 1.
- `Session(repo)`, `MainWindow(session)`, `show()`, `session.reload_all()`, `session.start()`, `app.exec()`.

## window.py — `class MainWindow(QMainWindow)`
- **Toolbar** (not movable, icon size 18): `git_branch` icon + label "**repo** feat/x → main" (branch and target in
  accent); separator; a `QFrame#segment` with two checkable exclusive `QToolButton`s "Committed" / "+ Working tree"
  (→ `session.set_mode`); a second segment "Unified" (`rows` icon) / "Split" (`columns` icon) (→ `session.set_view`);
  refresh button (`refresh` icon, Ctrl+R and F5 → `reload_all`); stretch spacer; "Agent prompt" button
  (`copy` icon, text "Agent prompt · N" with N = open comments; placeholder action for T11: copies
  `session.prompt_text()` to the clipboard and shows a status-bar message); `QToolButton#primary` "Create PR…"
  (`git_pr` icon; placeholder slot for T11 — disabled with tooltip "Coming soon").
- **PR header** (a `QWidget` above the tabs, margins 24/16/24/0): `QLabel#h1` = description title; below, a row:
  chip "Local preview", then muted text "<user> wants to merge <ahead> commit(s) into <target> from <branch>",
  plus, if `behind > 0`, warn-coloured " · <target> is <behind> commit(s) ahead — consider rebasing"; and if
  mode is committed and `meta.dirty`, muted " · uncommitted changes not shown".
- **Tabs**: `QTabBar` (document mode, not expanding) + `QStackedWidget`. Tab labels "Overview", "Commits  N",
  "Files changed  N"; on the right of the tab bar row a label "+A −D" (green/red via rich text using theme ok/bad).
  Pages: `self.overview_page`, `self.commits_page`, `self.files_page` attributes. For now Overview and Files are
  `QLabel("Overview — T10")` / `QLabel("Files — T09")` placeholders; construct them in methods
  `_make_overview()` / `_make_files()` so later tasks swap the body of those methods only.
  `show_tab(name)` with names `"overview" | "commits" | "files"`.
- **Status bar**: left "base origin/main @ <mergeBase> · HEAD <head>"; right "Refreshing…" while busy else
  "Refreshed HH:MM:SS"; `session.error` → `statusBar().showMessage(msg, 8000)` in bad colour (use a QLabel).
- **Menus**: File (Open Repository… Ctrl+O — stub that T11 completes, Quit `StandardKey.Quit`), View (Committed,
  Working tree, Unified, Split as checkable actions mirroring the toolbar; Reload), Go (Overview Ctrl+1, Commits
  Ctrl+2, Files Ctrl+3).
- Window title "<title> — premerge". Default size 1440×900. Persist geometry, current tab, mode and view in
  `QSettings` (restore in constructor, save in `closeEvent`; mode/view applied to the session on start).
- Connect session signals to `refresh_*` methods that update only what changed.

## commits.py — `class CommitsPage(QWidget)`
Scrollable list, max content width 1000 px, centered-left with 24 px margins. Groups by local date heading
("Commits on 23 Nov 2026", muted). Each commit is a row card: subject (bold, fg), "author committed 2h ago" (muted),
short sha on the right as a flat button that copies the full sha (status message "Copied"); if the commit has a body,
a chevron toggles a monospace muted body below. Empty state: "No commits on this branch yet." `set_commits(list)`.

## tools/shot.py
`python tools/shot.py OUT_DIR [--only NAME…]`: sets `QT_QPA_PLATFORM=offscreen`, builds `make_fixture` in a temp
dir, creates the app the same way as `run_gui` (factor a helper in app.py: `create_window(repo) -> (app, window,
session)` used by both), resizes to 1440×900, `reload_all()`, waits until not busy, then for each registered shot
calls a function that drives the UI and saves `window.grab()` to `OUT_DIR/<name>.png`. Shots are registered with a
decorator `@shot("name")` so later tasks append functions. This task registers `overview`, `commits`, `files`.
Print each written path.

## tests/test_ui_window.py
Window builds on the fixture; after load, the title label shows "Thing" (fixture title); tab labels contain counts
("Commits  2", "Files changed  7"); toggling the Working tree button sets `session.mode` and the files count becomes
8 (adds `u.txt`); `show_tab("commits")` shows 2 commit rows.

## Acceptance
- Tests pass (`QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v`).
- `.venv/bin/python tools/shot.py shots` writes three PNGs; look at `shots/commits.png` and describe it in the report.
- `.venv/bin/premerge -C <fixture work dir>` starts (run with `QT_QPA_PLATFORM=offscreen` and `timeout 5`; exit by
  timeout without a traceback is a pass).
