# T03 — Theme, icons, background jobs, Markdown view

## Goal
The UI foundation modules every later UI task uses. No windows yet.

## Read
- `docs/spec/00-overview.md` (§5 colours are authoritative)
- `~/dev/pdfile/pdfile/theme.py` and `~/dev/pdfile/pdfile/icons.py` (copy and adapt; pdfile is the user's app)

## Create
`premerge/ui/theme.py`, `premerge/ui/icons.py`, `premerge/ui/jobs.py`, `premerge/ui/markdown.py`, `tests/qt.py`,
`tests/test_ui_foundation.py`

## theme.py
- Copy pdfile's `Theme` dataclass and `NIGHT`; drop `DAY`, every light/dark detection function, and the
  pdfile-only stylesheet rules (datePicker, signature, zoom, QGraphicsView). Add the §5 premerge fields to `Theme`
  (`diff_add_bg`, `diff_add_gutter`, `diff_del_bg`, `diff_del_gutter`, `hunk_bg`, `hunk_fg`, `sel_bg`, `sel_gutter`,
  `st_added`, `st_modified`, `st_deleted`, `st_renamed`, `you`, `agent`) and a `syntax: dict[str, str]` field
  (keys: keyword, constant, type, function, decorator, tag, attribute, string, escape, number, comment, operator,
  heading, error) with the §5 values — use `field(default_factory=...)` or a module-level dict, keep the dataclass frozen.
- `syntax_color(ttype) -> tuple[str, bool, bool]`: map a Pygments token type to (hex, bold, italic) by walking
  `ttype` up its parents: `Keyword.Constant`→constant; `Keyword.Type`→type; `Keyword`→keyword; `Name.Function`,
  `Name.Function.Magic`→function; `Name.Class`, `Name.Builtin`, `Name.Namespace`(fg_dark), `Name.Exception`→type;
  `Name.Decorator`→decorator; `Name.Tag`→tag; `Name.Attribute`→attribute; `String.Escape`, `String.Regex`→escape;
  `String`→string; `Number`→number; `Comment`→comment (italic); `Operator`, `Punctuation`→operator;
  `Generic.Heading`, `Generic.Subheading`→heading (bold); `Error`→error; else `fg`. Cache results.
- `stylesheet(t)`: keep pdfile's rules for QMainWindow/QDialog/QToolBar/QToolButton (incl. `#primary`, `#segment`
  frame)/QStatusBar/QMenu/QToolTip/QPushButton/QLineEdit/QComboBox/scrollbars, and add:
  `QPlainTextEdit, QTextEdit` (like QLineEdit, radius 7, padding 6); `QTabBar::tab` (transparent, fg_dark, padding
  8px 14px, bottom border 2px transparent; `:selected` fg + bottom border accent; `:hover` fg);
  `QTreeView` (background bg_dark, no border, item padding 3px, `::item:selected` bg_highlight with fg,
  `::item:hover` bg_highlight); `QSplitter::handle` (border colour, 1px); `QCheckBox` (fg; indicator 14px, border
  1px border colour, radius 4, checked = accent background); `QLabel#h1` (22px, fg), `QLabel#muted` (muted),
  `QLabel#chip` (bg_highlight, radius 9, padding 2px 8px, fg_dark), `QFrame#card` (bg, 1px border, radius 9),
  `QFrame#cardHeader` (bg_dark, bottom border, top radius 9), `QFrame#thread` (bg, 1px border, radius 8),
  `QFrame#threadFoot` (bg_dark, top border), `QScrollArea` transparent/no border.
- `apply(app)`: Fusion style, palette, stylesheet — as pdfile.

## icons.py
Copy pdfile's `_SHAPES`, `SIZES`, `_pixmap`, `icon` (keep the ISC/Lucide attribution docstring). Make `t` default to
`NIGHT`. Expose `pixmap(name, color, px)` (public alias of `_pixmap`). Keep only shapes premerge uses from pdfile:
open, chevron_left, chevron_right, chevron_down, close, external, plus, minus, trash, warning, valid, pending,
reset. Add (Lucide paths, 24×24 grid):
```
git_branch   <line x1="6" x2="6" y1="3" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>
git_pr       <circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><line x1="6" x2="6" y1="9" y2="21"/>
message      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
copy         <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
refresh      <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>
folder       <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>
file         <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>
check        <path d="M20 6 9 17l-5-5"/>
columns      <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M12 3v18"/>
rows         <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 12h18"/>
unfold       <path d="M12 22v-6"/><path d="M12 8V2"/><path d="M4 12H2"/><path d="M10 12H8"/><path d="M16 12h-2"/><path d="M22 12h-2"/><path d="m15 19-3 3-3-3"/><path d="m15 5-3-3-3 3"/>
bot          <path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>
pencil       <path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/>
send         <path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>
arrow_right  <path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>
eye          <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>
search       <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
```

## jobs.py
`run(fn, *args, on_done=None, on_error=None, **kwargs) -> None`: wraps the call in a `QRunnable` submitted to
`QThreadPool.globalInstance()`. Results are delivered on the GUI thread through a QObject bridge living in the GUI
thread (`Signal(object, object, object)` carrying callback, value, error; queued connection). `on_error(exc)`
receives the exception; with no `on_error`, print the traceback to stderr. Keep strong references to in-flight
runnables/bridges until delivered.

## markdown.py
`class MarkdownView(QTextBrowser)`: read-only, no frame, transparent background, no scrollbars,
`setOpenExternalLinks(True)`, word wrap; `set_markdown(text)` uses
`document().setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)`; a default stylesheet on the
document (`setDefaultStyleSheet` before setting content) colouring `code`/`pre` with `bg_highlight` background and
`fg` text in the code font, `a` in accent, `h1,h2,h3` in fg; height follows content: `sizeHint`/`minimumSizeHint`
from `document().size()` after `document().setTextWidth(viewport width)`, recomputed in `resizeEvent` and on
`contentsChanged` (use `setFixedHeight`). Empty text shows `placeholder` (constructor kwarg) in muted colour.

## tests/qt.py
`app() -> QApplication` (creates once; sets `QT_QPA_PLATFORM=offscreen` if unset before creation; applies theme),
`wait_until(pred, timeout=5.0) -> bool` (loop `QApplication.processEvents()` + `time.sleep(0.01)`).

## test_ui_foundation.py
- every `_SHAPES` name renders a non-empty pixmap; `icon()` returns non-null.
- `syntax_color` for `Token.Keyword` → keyword hex, `Token.Comment.Single` → italic, `Token.Text` → fg.
- `stylesheet(NIGHT)` is non-empty and `apply()` doesn't raise.
- `jobs.run(lambda: 42, on_done=...)` delivers 42 on the GUI thread (check `QThread.currentThread()` is the app's
  thread); an exception reaches `on_error`.
- `MarkdownView.set_markdown("# Hi\n\n- a\n- [x] b\n\n```py\nx=1\n```")` grows taller than with `"one line"` at
  width 400.

## Acceptance
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v` — all tests (old and new) pass.
