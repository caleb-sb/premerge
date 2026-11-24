# premerge build progress

Orchestrator log. One section per task: status, commit, deviations accepted, fixes, open issues.

## Setup
- `git init -b main`; spec committed as 98ee433 "Add premerge spec".
- Venv created by the orchestrator before T01 (system Python 3.15.2): `pip -U pip`, `pip install PySide6 Pygments`
  → PySide6 6.12.0 (meta-package also pulls PySide6_Essentials/Addons/Pdf/WebEngine wheels; WebEngine is never
  imported), Pygments 2.21.0. T01 therefore only runs `pip install -e .`.
- Schedule: tasks dispatched sequentially with a 45-minute wait between tasks (user request).

## T01 — Package skeleton, venv, and core port — DONE
- Commit: see `git log` ("T01: Package skeleton, venv, and core port").
- Verified by orchestrator: imports, no Qt in core, §6 core signatures, end-to-end CLI in a throwaway repo
  (describe / --title/--body / --reset / --json, comments / --json, add_comment via Store, reply with prefix id,
  reply `-` from stdin `--as you` reopens, resolve/reopen, pr problem + exit 1, unknown id and non-repo errors exit 1).
- Deviations accepted: `PrPlan` gained a trailing `source: str = ""` field (description source for the CLI plan).
- Spec bug: acceptance `grep -rn "evie"` matches the word "review"; the word-boundary grep (`grep -rniw evie`) is clean.
- Not verified: `publish.execute` (would need a real remote; never run).

## T02 — Fixture repo and core tests — DONE
- Verified: 48 tests pass (~1.5 s) on rerun; publish tests assert the fake `gh` resolves first before `execute`
  (real /usr/bin/gh is never run).
- Core fix by subagent: `premerge describe` no longer prints an extra trailing blank line.
- Deviations accepted: extra `tests/base.py` (`FixtureCase`, sets git-config isolation env for in-process calls);
  fixture's app.py ends up with 3 hunks (test asserts ≥2); empty global gitconfig is `$TMPDIR/premerge-empty-gitconfig`.

## T03 — Theme, icons, background jobs, Markdown view — DONE
- Verified: 54 tests pass; every §5 colour and syntax mapping checked programmatically; icon strip + widgets rendered
  and inspected (all 30 shapes crisp).
- Orchestrator fix: `MarkdownView` — `QTextDocument.setMarkdown` ignores the default stylesheet, so code spans/fences
  had no code font/background. Added `_style_code()` post-processing (fixed-pitch fragments and code-fence blocks get
  the system fixed font + `bg_highlight`); placeholder text is now HTML-escaped.
- Deviations accepted: `Theme` has no `dark` field; `palette(t)` kept public; jobs bridge created lazily on first
  `run` (must be first called from the GUI thread). Tests import the helper as `from tests import qt`.

## T04 — Tree ordering and the Session model — DONE
- Verified: 65 tests pass; `tree_order`/`build_tree` checked by hand (dirs first, casefold, chain compression,
  root never merged); Session signals/queries/mutations/start/stop names match the task; load/pending/generation and
  poll logic read and judged correct.
- Deviations accepted: `set_mode` reloads the whole "code" kind (meta+files+commits), so meta/commits signals also
  fire; initial `review["description"]` is None until the first load.
- Known issue (spec-level): polling watches branch/HEAD/worktree/store only — a `git fetch` that moves the base ref
  isn't picked up until the next manual refresh.

## T05 — App entry, main window shell, commits tab, screenshot tool — DONE
- Verified: 68 tests pass; `tools/shot.py shots` writes overview/commits/files; inspected commits.png and overview.png
  (toolbar, header with warn-coloured "main is 1 commit ahead", tabs with counts, +A −D, status bar — matches §5);
  rendered a commit with a body and expanded it; `timeout 5 premerge -C <repo>` exits by timeout, no traceback.
- Deviations accepted: `MainWindow(session, settings=None)` / `create_window(repo, settings=None)` take an optional
  `QSettings` (tests and shots pass a temp INI so the user's config is never touched); errors use a bad-coloured
  status-bar QLabel cleared after 8 s; "Agent prompt" without " · 0" when no open comments; chevron icon doesn't flip.

## T06 — File tree widget — DONE
- Verified: 74 tests pass; filetree shot inspected; also rendered a nested tree (compressed `docs/x/y`, nested dirs,
  long-name elision, badges, renamed/deleted styling) and a collapsed directory.
- Orchestrator fix: `setRootIsDecorated(True)` — with it off, only nested directories showed an expand arrow.
- Deviations accepted: `FileTree(parent=None, t=NIGHT)`; filter via `setRowHidden` (no proxy model); copied files use
  `st_renamed`; `tools/shot.py` runner grabs the returned widget if a shot function returns one.
- Known cosmetic issue: the comment badge (bg_highlight) is barely visible on the selected row.

## T07 — Syntax highlighting and the diff body widget — DONE
- Verified: 82 tests pass (incl. 5 000-row render < 1.5 s); inspected diffview-unified/split shots (gutters, tints,
  syntax colours, selection, insert slot, split pairing and empty cells) and a noeol render (⊘ in bad).
- Deviations accepted: split halves also have a 16 px sign column; selected rows draw numbers in fg (readability);
  spans kept when bold/italic even if fg; `scroll_target` is a 1×row_h transparent child at the row's y.
- Not verified visually: gutter hover "+" box / pointing-hand cursor (no hover offscreen); Shift+click extend untested.
