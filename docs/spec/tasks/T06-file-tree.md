# T06 — File tree widget

## Goal
`FileTree`: the left pane of the Files tab — filter box, viewed progress, collapsible directory tree of changed
files with status letters, comment badges and viewed checks. Standalone widget (wired into the Files tab in T09).

## Read
- `docs/spec/00-overview.md`
- `premerge/core/paths.py`, `premerge/ui/theme.py` (fields), `premerge/ui/icons.py` (names), `tests/qt.py`

## Create
`premerge/ui/filetree.py`, `tests/test_filetree.py`

## API
```python
class FileTree(QWidget):
    fileActivated = Signal(str)          # path; emitted on click / Enter
    def set_files(self, files: list[dict], viewed: set[str], changed: set[str], comments: dict[str, int]) -> None
    def select_path(self, path: str) -> None          # highlight + expand parents + scroll to it; no signal
    def ordered_paths(self) -> list[str]              # all file paths in display order (ignores the filter)
    def focus_filter(self) -> None
```
`viewed` = paths currently viewed; `changed` = viewed-but-changed paths; `comments` = path → open comment count.

## Behaviour
- Layout (vertical, margins 8): `QLineEdit` filter (placeholder "Filter changed files…", `search` icon as a leading
  action, clear button); a progress row: label "3 of 7 viewed" (muted, 12 px) and a thin 6 px bar (custom painted:
  gutter track, ok fill); then a `QTreeView` (header hidden, no root decoration lines, uniform row heights,
  `setIndentation(14)`, animated expand, no edit triggers).
- Model: `QStandardItemModel` built from `core.paths.build_tree`. Directory items: `folder` icon (muted), name
  (compressed chains shown as "src/main/java"), expanded by default; collapse state is remembered per directory path
  across `set_files` calls. File items: data roles for path, status, viewed, changed, comment count.
- Painting: a `QStyledItemDelegate` for file rows draws: the status letter (A/M/D/R/C, bold mono, colour
  `st_added`/`st_modified`/`st_deleted`/`st_renamed`), the file **base name** (fg; muted + `check` icon at the right
  when viewed; `warn`-coloured dot when changed since viewed; struck-through muted for deleted files), and a comment
  badge (rounded rect `bg_highlight`, `message` icon 12 px + count) right-aligned before the check. Tooltip = full
  path (+ "renamed from X" when renamed — pass oldPath through `set_files` data).
- Filter: case-insensitive substring on the full path; non-matching files hidden, directories with no visible
  files hidden, all visible directories expanded while a filter is active. Esc in the filter clears it.
- Activation: single click or Enter on a file row emits `fileActivated(path)`. Clicking a directory toggles it.
- `select_path` keeps the selection visible (`scrollTo`, `PositionAtCenter` only if it's out of view).
- Keyboard: Up/Down move the current file (skipping directories is not required), Enter activates.

## Tests
- Given files `["README.md", "src/a.py", "src/util/b.py", "docs/x/y/z.md"]`: `ordered_paths()` ==
  `["docs/x/y/z.md", "src/util/b.py", "src/a.py", "README.md"]`; the docs directory shows as one row "docs/x/y".
- Filter "util" leaves exactly one visible file row.
- Clicking (simulate via `QTest.mouseClick` on `visualRect`) a file emits `fileActivated` with its path.
- Progress label reads "1 of 4 viewed" when one path is viewed.
- Collapse "src", call `set_files` again → still collapsed.

## Acceptance
Tests pass. Add a `@shot("filetree")` to `tools/shot.py` that shows a standalone `FileTree` (320×600) for the fixture
files with one viewed file and a comment count, saves it, and describe the image in your report.
