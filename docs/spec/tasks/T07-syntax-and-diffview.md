# T07 — Syntax highlighting and the diff body widget

## Goal
Fast, custom-painted diff rendering (unified and split) with syntax colours, line selection for commenting, and
slots where other widgets (comment threads, composers) are inserted between rows. No comment logic here.

## Read
- `docs/spec/00-overview.md` (§4 Line shape, side rules; §5 colours)
- `premerge/ui/theme.py` (fields + `syntax_color`), `tests/qt.py`

## Create
`premerge/ui/syntax.py`, `premerge/ui/diffview.py`, `tests/test_diffview.py`

## syntax.py
`highlight_lines(path: str, lines: list[str]) -> list[list[tuple[int, int, str, bool, bool]]]` — for each input line,
spans `(start, length, hex, bold, italic)`. Lexer: `pygments.lexers.get_lexer_for_filename(path, stripnl=False,
ensurenl=False)`; on `ClassNotFound` try `guess_lexer_for_filename` only if the text is < 50 KB, else no spans. Lex
`"\n".join(lines)`, split token values on `\n` to assign spans to lines; skip spans whose colour equals `fg`.
Return empty span lists if there are > 20 000 lines or any line > 5 000 chars. LRU-cache by `(path, hash of text)`
(max 64 entries).

`annotate(path, hunks)`: builds two texts — the old side (lines with `t != "+"`) and new side (`t != "-"`) in hunk
order — highlights each, and stores spans on each Line dict as `line["_hl"]` (context lines take new-side spans).
Lexing a whole side (not line by line) keeps multi-line strings/comments correct within a hunk.

## diffview.py
```python
@dataclass
class Row:
    kind: str                 # "hunk" | "line" (unified) | "pair" (split)
    header: str = ""          # hunk header text
    line: dict | None = None  # unified
    left: dict | None = None  # split: "-" or " " line, or None
    right: dict | None = None # split: "+" or " " line, or None

def build_rows(hunks: list[dict], view: str) -> list[Row]
def row_keys(row: Row) -> list[str]   # selection/anchor keys hosted by the row: "old:N" / "new:N" (see below)

class DiffBody(QWidget):
    rangeSelected = Signal(str, int, int)          # side, start, end (inclusive line numbers on that side)
    def __init__(self, parent=None)
    def set_content(self, path: str, hunks: list[dict], view: str) -> None
    def rows(self) -> list[Row]
    def row_index(self, key: str) -> int | None    # e.g. "new:12"
    def set_inserts(self, inserts: dict[int, list[QWidget]]) -> None  # widgets placed after row index i
    def set_selection(self, side: str, start: int, end: int) -> None
    def clear_selection(self) -> None
    def scroll_target(self, row: int) -> QWidget   # a child whose y lets a QScrollArea ensure the row is visible
```
- `build_rows`: for each hunk a `"hunk"` row, then lines. Split: context lines → pair(left=line, right=line); a run of
  `-` lines followed by a run of `+` lines is zipped into pairs (missing side None); `+` with no preceding `-` →
  pair(None, line).
- `row_keys`: unified `-` → `old:o`; `+` → `new:n`; context → `new:n` **and** `old:o`. Split pair: left `-` →
  `old:o`, right → `new:n`, context pair → `new:n` and `old:o`. Hunk rows: none.
- Layout: `DiffBody` is a `QWidget` with a `QVBoxLayout` (spacing 0, no margins) of alternating `_Block` widgets
  (custom-painted, each covering a contiguous row range) and inserted widgets. `set_inserts` rebuilds the layout
  (reusing blocks where possible; inserted widgets are reparented, never deleted by DiffBody — callers own them).
- `_Block.paintEvent` paints only rows intersecting `event.rect()`. Row height = code-font `height() + 4`. Code font
  per §5. No wrapping; the body's minimum width = gutters + widest line (`horizontalAdvance`, tabs expanded to 4) so a
  surrounding QScrollArea scrolls horizontally.
- Unified columns: old number (52 px), new number (52 px), sign (16 px), code. Split: old number, old code, new number,
  new code (two halves of equal width; each half's code clipped to its column; the body min width = 2×(52+16+widest)).
- Colours: `-` lines `diff_del_bg` (numbers on `diff_del_gutter`), `+` lines `diff_add_bg` / `diff_add_gutter`,
  context `bg` (numbers on `bg_dark`, muted), hunk rows `hunk_bg` with `hunk_fg` text, empty split cells `bg_dark`,
  selected rows `sel_bg` / `sel_gutter`. Signs `-`/`+` in muted; code drawn span by span from `line["_hl"]` (call
  `syntax.annotate` inside `set_content`), default fg. `noeol` lines end with a small `⊘` in `bad`.
- Hovering a number gutter shows a 16 px rounded accent "+" box at the gutter's left and a pointing-hand cursor.
- Selection: mouse press on a number gutter (or anywhere on a line row with Shift held) starts at that line on the
  side given by §4 rules (in split, the column clicked decides: left `-` → old, everything else → new); dragging
  extends on the same side (rows without that side are skipped); release emits `rangeSelected(side, start, end)`.
  Shift+click extends the current selection. The selection stays highlighted until `clear_selection()`.

## Tests
- `build_rows` unified/split on a hand-made hunk (`" a"`, `"-b"`, `"-c"`, `"+B"`, `" d"`, `"+e"`): split gives
  pairs (a,a), (b,B), (c,None), (d,d), (None,e); keys as specified.
- `DiffBody.set_content` + `row_index("new:2")` finds the `+B` row; `set_inserts({2: [QLabel("x")]})` puts the label
  in the layout right after the block containing row 2 (check layout order and the next block's first row is 3).
- Simulated press/drag/release on the new-number gutter from row of new line 1 to new line 2 emits
  `("new", 1, 2)`; on a `-` row emits side `"old"`.
- `highlight_lines("x.py", ["def f():", "    return 'hi'"])` gives a keyword span at 0 and a string span on line 2;
  unknown extension → no spans.
- Rendering 5 000 rows: `set_content` + `grab()` under 1.5 s.

## Acceptance
Tests pass. Add `@shot("diffview-unified")` and `@shot("diffview-split")` to `tools/shot.py`: a standalone
`QScrollArea` (1100×700) holding a `DiffBody` for the fixture's `app.py` (from `session.files`), with a selection on
two new lines and a `QLabel` insert; look at both images and describe them.
