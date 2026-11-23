# T09 — Files changed page (integration)

## Goal
The full Files tab: tree on the left, the selected file's header + diff + inline threads + composers on the right,
wired to the Session. Replace the placeholder in `MainWindow._make_files()`.

## Read
- `docs/spec/00-overview.md` (§3 Viewed, §4 sides/anchors, §5 layout)
- Public APIs only (read class/def lines and docstrings, skip bodies unless needed): `premerge/ui/session.py`,
  `premerge/ui/filetree.py`, `premerge/ui/diffview.py`, `premerge/ui/comments.py`, `premerge/core/anchors.py`;
  `premerge/ui/window.py` (`_make_files` and how pages are stored); `tools/shot.py` (decorator usage); `tests/qt.py`

## Create / modify
`premerge/ui/filepage.py`, `tests/test_filepage.py`; modify `premerge/ui/window.py` (`_make_files`, Go menu
actions, `show_file(path, comment_id=None)`), `tools/shot.py` (replace the `files` shot, add more).

## `class FilesPage(QWidget)` — `FilesPage(session, parent=None)`
- `QSplitter`: `FileTree` (initial 300 px, min 200) | right pane. Splitter sizes persisted in QSettings
  (`files/splitter`).
- `show_file(path, comment_id=None)`: select in tree, render that file, and if `comment_id` scroll to and briefly
  highlight that thread (flash the frame border accent for 1.2 s). On first load show the first file in tree order;
  keep the current path across reloads if it still exists, else the next one in order.
- **File header** (bg_dark bar, sticky above the scroll area): status letter (coloured), path in mono bold (for
  renames: muted old path + `arrow_right` icon + new path), "+A −D" (ok/bad), open comment count (message icon),
  stretch, prev/next file buttons (`chevron_left`/`chevron_right`, tooltips with shortcuts), "Full file" checkable
  (`unfold` icon; disabled for binary/added/deleted files), "Comment on file" (`message` icon), and a "Viewed"
  `QCheckBox`; when `session.viewed_changed(f)` show a warn label "Changed since viewed" before it.
- **Body** = `QScrollArea` (widget resizable, both scrollbars as needed) containing a vertical layout:
  1. a "file comments" area: a file-level Composer when requested, threads of `kind == "file"`, then outdated line
     comments (those whose `anchors.locate_in_rows` state is `missing`), each preceded by a muted label
     "Outdated · line N" and a read-only mini diff of its stored `context` (mono, add/del backgrounds);
  2. notes instead of a diff for: binary ("Binary file not shown"), no hunks ("File renamed without changes" /
     "Mode changed 100644 → 100755" / "No content changes"), and large diffs (> 3 000 lines: "Large diff — N lines"
     + "Load diff" button);
  3. the `DiffBody`.
- **Content**: hunks = `session.full_hunks(...)` result when "Full file" is checked, else the file's hunks. Rebuild
  the DiffBody on `filesChanged` (for the current file), `viewChanged`, and Full-file toggles. Preserve the vertical
  scroll position across rebuilds of the same file.
- **Threads**: for line comments of this file, `locate_in_rows(flat_lines, c)` → row index via
  `DiffBody.row_index(f"{side}:{n}")` of the located line → group threads per row → `set_inserts`. Keep
  `CommentThread` widgets in a dict by comment id; on `reviewChanged` call `update_comment` on existing ones, create
  new, delete removed, then recompute inserts. Connect thread signals to `session.reply/set_status/edit_body/
  delete_comment`.
- **Composing**: `DiffBody.rangeSelected(side, start, end)` → open a `Composer` labelled "Commenting on line N" /
  "lines A–B (old)" inserted after the row of `end`. Composers are kept in a dict keyed by
  `(path, side, start, end)`; re-opening the same range focuses the existing one. Several composers may exist.
  Submit → build fields: `kind "line"`, `path`, `oldPath`, `side`, `startLine=start`, `line=end`,
  `anchorText` = text of the `end` line, `context` = up to 3 diff lines before `start` plus the range, each as
  prefix+text, taken from the flat line list → `session.add_comment(fields)`; on success remove the composer and
  clear the selection; Cancel removes it and clears the selection. A composer with text whose range disappears after a
  reload moves to the file comments area with label "Draft for a line that changed".
  Composers belonging to other files are kept (hidden) and restored when you come back to that file.
- **Viewed**: toggling the checkbox → `session.set_viewed(f, checked)`; when checked, jump to the next file in tree
  order that isn't viewed (if any).
- **Keyboard** (page-level `QShortcut`s, context `WidgetWithChildrenShortcut`, inactive while a text editor has
  focus where they'd collide): `J` / `Alt+Down` next file, `K` / `Alt+Up` previous file, `V` toggle viewed, `F`
  focus tree filter (`Ctrl+P` too), `C` comment on file, `N` / `Shift+N` next/previous comment thread in this file.
- Tree data: on `filesChanged`/`reviewChanged` call `tree.set_files(files, viewed, changed, open counts)`.

## MainWindow changes
`_make_files()` returns `FilesPage(session)`; `show_file(path, comment_id=None)` switches to the files tab and
delegates. Go menu: Next File, Previous File (same shortcuts as above, but as menu items showing them).

## Tests (offscreen, fixture)
- After load, the page shows the first file in tree order; activating `app.py` in the tree renders its DiffBody
  with 2+ hunk rows.
- Simulate `rangeSelected("new", 2, 3)` on app.py → a Composer appears; set text + submit → the store has a line
  comment with `startLine 2`, `line 3`, correct `anchorText` and a context ending with the line-3 text; a
  `CommentThread` appears after the session reloads.
- A comment whose anchor text matches nothing appears in the outdated area.
- Checking Viewed moves to the next unviewed file and the tree progress updates.
- Switching view to split keeps the thread visible.
- A reply written via a separate `Store` shows up within 5 s with `session.start()` running.

## Acceptance
Tests pass. Shots: `files` (app.py, unified, one open thread with an agent reply, one open composer),
`files-split`, `files-outdated`, `files-binary`. Look at every image; check the header, tree, threads and diff
colours against §5 and fix what looks wrong before reporting. Describe them.
