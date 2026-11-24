"""Custom-painted unified/split diff body with line selection and insert slots for other widgets."""

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPainter
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from . import syntax
from .theme import NIGHT

NUM_W = 52
SIGN_W = 16
PAD = 8
TAB = " " * 4


@dataclass
class Row:
    kind: str  # "hunk" | "line" (unified) | "pair" (split)
    header: str = ""
    line: dict | None = None
    left: dict | None = None
    right: dict | None = None


def build_rows(hunks: list[dict], view: str) -> list[Row]:
    """Rows for a list of hunks, unified (`line` rows) or split (`pair` rows)."""
    rows: list[Row] = []
    for hunk in hunks:
        rows.append(Row("hunk", header=hunk["header"]))
        if view != "split":
            rows.extend(Row("line", line=ln) for ln in hunk["lines"])
            continue
        dels: list[dict] = []
        adds: list[dict] = []

        def flush() -> None:
            for i in range(max(len(dels), len(adds))):
                rows.append(Row("pair", left=dels[i] if i < len(dels) else None,
                                right=adds[i] if i < len(adds) else None))
            dels.clear()
            adds.clear()

        for ln in hunk["lines"]:
            if ln["t"] == "-":
                if adds:
                    flush()
                dels.append(ln)
            elif ln["t"] == "+":
                adds.append(ln)
            else:
                flush()
                rows.append(Row("pair", left=ln, right=ln))
        flush()
    return rows


def row_keys(row: Row) -> list[str]:
    """Selection/anchor keys ("old:N" / "new:N") hosted by a row."""
    if row.kind == "hunk":
        return []
    if row.kind == "line":
        left, right = row.line, row.line
    else:
        left, right = row.left, row.right
    keys: list[str] = []
    if right is not None and right["t"] != "-":
        keys.append(f"new:{right['n']}")
    if left is not None and left["t"] != "+":
        keys.append(f"old:{left['o']}")
    return keys


def _num(line: dict | None, side: str) -> int | None:
    """Line number of `line` on `side`, or None if it has no such side."""
    if line is None:
        return None
    if side == "old":
        return line["o"] if line["t"] != "+" else None
    return line["n"] if line["t"] != "-" else None


def _row_num(row: Row, side: str) -> int | None:
    if row.kind == "line":
        return _num(row.line, side)
    if row.kind == "pair":
        return _num(row.left if side == "old" else row.right, side)
    return None


class _Block(QWidget):
    """A contiguous range of rows, painted directly."""

    def __init__(self, body: "DiffBody", start: int, end: int) -> None:
        super().__init__(body)
        self.body, self.start, self.end = body, start, end  # end exclusive
        self.hover: tuple[int, int] | None = None  # (row, column)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight((end - start) * body.row_h)

    def sizeHint(self):
        return self.minimumSize().expandedTo(super().sizeHint())

    def _locate(self, pos: QPoint) -> tuple[int, int, bool]:
        """(row index, column 0/1, over a number gutter) for a block-local point."""
        body = self.body
        row = min(max(self.start + pos.y() // body.row_h, self.start), self.end - 1)
        if body.view == "split":
            half = self.width() // 2
            col = 0 if pos.x() < half else 1
            x = pos.x() - col * half
        else:
            col, x = 0, pos.x()
        span = NUM_W if body.view == "split" else 2 * NUM_W
        return row, col, x < span

    def leaveEvent(self, event) -> None:
        self._set_hover(None)

    def _set_hover(self, hover: tuple[int, int] | None) -> None:
        if hover != self.hover:
            self.hover = hover
            self.update()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.body._drag(self.mapTo(self.body, pos))
            return
        row, col, over = self._locate(pos)
        ok = over and self.body._side_at(row, col) is not None
        self._set_hover((row, col) if ok else None)
        self.setCursor(Qt.CursorShape.PointingHandCursor if ok else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        row, col, over = self._locate(event.position().toPoint())
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if over or shift:
            self.body._press(row, col, shift)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.body._release()

    def paintEvent(self, event) -> None:
        body = self.body
        h = body.row_h
        first = max(self.start, self.start + event.rect().top() // h)
        last = min(self.end, self.start + event.rect().bottom() // h + 1)
        p = QPainter(self)
        p.setFont(body.font_for(False, False))
        for i in range(first, last):
            y = (i - self.start) * h
            row = body.rows_[i]
            if row.kind == "hunk":
                self._paint_hunk(p, row, y)
            elif row.kind == "line":
                self._paint_cells(p, i, 0, self.width(), y, row.line, True)
            else:
                half = self.width() // 2
                self._paint_cells(p, i, 0, half, y, row.left, False)
                self._paint_cells(p, i, half, self.width() - half, y, row.right, False)
        p.end()

    def _text_y(self, y: int) -> int:
        fm = self.body.fm
        return y + (self.body.row_h - fm.height()) // 2 + fm.ascent()

    def _paint_hunk(self, p: QPainter, row: Row, y: int) -> None:
        p.fillRect(0, y, self.width(), self.body.row_h, QColor(NIGHT.hunk_bg))
        p.setPen(QColor(NIGHT.hunk_fg))
        p.drawText(NUM_W + PAD, self._text_y(y), row.header)

    def _paint_cells(self, p: QPainter, index: int, x0: int, w: int, y: int, line: dict | None,
                     unified: bool) -> None:
        """Paint one cell: number gutter(s), sign and code. Unified has two number columns."""
        body, h = self.body, self.body.row_h
        if line is None:
            p.fillRect(x0, y, w, h, QColor(NIGHT.bg_dark))
            return
        kind = line["t"]
        selected = body._is_selected(line)
        if selected:
            bg, gut = NIGHT.sel_bg, NIGHT.sel_gutter
        elif kind == "+":
            bg, gut = NIGHT.diff_add_bg, NIGHT.diff_add_gutter
        elif kind == "-":
            bg, gut = NIGHT.diff_del_bg, NIGHT.diff_del_gutter
        else:
            bg, gut = NIGHT.bg, NIGHT.bg_dark
        ncols = 2 if unified else 1
        gw = NUM_W * ncols
        p.fillRect(x0, y, w, h, QColor(bg))
        p.fillRect(x0, y, gw, h, QColor(gut))
        p.setPen(QColor(NIGHT.fg if selected else NIGHT.muted))
        ty = self._text_y(y)
        if unified:
            nums = [line["o"], line["n"]]
        else:
            nums = [line["o"] if x0 == 0 else line["n"]]
        for c, num in enumerate(nums):
            if num is not None:
                rect = QRect(x0 + c * NUM_W, y, NUM_W - PAD, h)
                p.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(num))
        if self.hover is not None and self.hover[0] == index and (unified or self.hover[1] == (0 if x0 == 0 else 1)):
            box = QRectF(x0 + 3, y + (h - 16) / 2, 16, 16)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(NIGHT.accent))
            p.drawRoundedRect(box, 3, 3)
            p.setPen(QColor(NIGHT.on_accent))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, "+")
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(QColor(NIGHT.muted))
        if kind in "+-":
            p.drawText(x0 + gw + 4, ty, kind)
        cx = x0 + gw + SIGN_W
        p.save()
        p.setClipRect(QRect(cx, y, x0 + w - cx, h))
        end = self._paint_code(p, cx + 2, ty, line)
        if line.get("noeol"):
            p.setPen(QColor(NIGHT.bad))
            p.setFont(body.font_for(False, False))
            p.drawText(end + 4, ty, "⊘")
        p.restore()

    def _paint_code(self, p: QPainter, x: int, ty: int, line: dict) -> int:
        """Draw the line text span by span; returns the x after the last character."""
        body = self.body
        text = line["s"]
        pos = 0
        for start, length, color, bold, italic in line.get("_hl", ()):
            if start > pos:
                x = self._draw(p, x, ty, text[pos:start], NIGHT.fg, False, False)
            x = self._draw(p, x, ty, text[start:start + length], color, bold, italic)
            pos = start + length
        if pos < len(text):
            x = self._draw(p, x, ty, text[pos:], NIGHT.fg, False, False)
        return x

    def _draw(self, p: QPainter, x: int, ty: int, text: str, color: str, bold: bool, italic: bool) -> int:
        text = text.replace("\t", TAB)
        font = self.body.font_for(bold, italic)
        p.setFont(font)
        p.setPen(QColor(color))
        p.drawText(x, ty, text)
        return x + self.body.advance(text, font)


class DiffBody(QWidget):
    """Diff rows (unified or split) with line-range selection and slots between rows."""

    rangeSelected = Signal(str, int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.view = "unified"
        self.path = ""
        self.rows_: list[Row] = []
        self._fonts: dict[tuple[bool, bool], QFont] = {}
        base = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        base.setPixelSize(13)
        self._base = base
        self.fm = QFontMetrics(base)
        self.row_h = self.fm.height() + 4
        self._inserts: dict[int, list[QWidget]] = {}
        self._blocks: dict[tuple[int, int], _Block] = {}
        self._sel: tuple[str, int, int] | None = None
        self._anchor: tuple[str, int] | None = None
        self._dragging = False
        self._marker = QWidget(self)
        self._marker.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._marker.hide()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAutoFillBackground(True)

    def font_for(self, bold: bool, italic: bool) -> QFont:
        """The code font variant for the given style."""
        key = (bold, italic)
        font = self._fonts.get(key)
        if font is None:
            font = QFont(self._base)
            font.setBold(bold)
            font.setItalic(italic)
            self._fonts[key] = font
        return font

    def advance(self, text: str, font: QFont) -> int:
        """Pixel width of `text` in `font`."""
        return QFontMetrics(font).horizontalAdvance(text)

    def set_content(self, path: str, hunks: list[dict], view: str) -> None:
        """Show `hunks` of `path` in `view` ("unified" or "split")."""
        self.path, self.view = path, view
        syntax.annotate(path, hunks)
        self.rows_ = build_rows(hunks, view)
        self._sel = self._anchor = None
        self._inserts = {}
        widest = 0
        advance = self.fm.horizontalAdvance(" ")
        for hunk in hunks:
            for ln in hunk["lines"]:
                widest = max(widest, len(ln["s"].replace("\t", TAB)))
        widest = widest * advance + advance * 2
        cols = 2 if view == "split" else 1
        gutters = NUM_W if view == "split" else 2 * NUM_W
        self.setMinimumWidth(cols * (gutters + SIGN_W + widest + PAD))
        for b in self._blocks.values():
            b.hide()
            b.deleteLater()
        self._blocks = {}
        self._rebuild()

    def rows(self) -> list[Row]:
        """The current rows."""
        return self.rows_

    def row_index(self, key: str) -> int | None:
        """Index of the row hosting selection key `key` (e.g. "new:12")."""
        for i, row in enumerate(self.rows_):
            if key in row_keys(row):
                return i
        return None

    def set_inserts(self, inserts: dict[int, list[QWidget]]) -> None:
        """Place widgets after row index i (callers own the widgets)."""
        self._inserts = {i: list(ws) for i, ws in inserts.items() if ws and 0 <= i < len(self.rows_)}
        self._rebuild()

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None and not isinstance(w, _Block):
                w.hide()
                w.setParent(None)
        spans: list[tuple[int, int]] = []
        start = 0
        for i in sorted(self._inserts):
            spans.append((start, i + 1))
            start = i + 1
        if start < len(self.rows_):
            spans.append((start, len(self.rows_)))
        old, self._blocks = self._blocks, {}
        for span in spans:
            block = old.pop(span, None) or _Block(self, *span)
            self._blocks[span] = block
        for b in old.values():
            b.hide()
            b.deleteLater()
        for s, e in spans:
            block = self._blocks[(s, e)]
            self._layout.addWidget(block)
            block.show()
            for w in self._inserts.get(e - 1, ()):
                self._layout.addWidget(w)
                w.show()
        self._layout.addStretch(0)
        self.updateGeometry()
        self.update()

    def set_selection(self, side: str, start: int, end: int) -> None:
        """Highlight lines start..end (inclusive) on `side`."""
        self._sel = (side, min(start, end), max(start, end))
        self._anchor = (side, start)
        self._repaint()

    def clear_selection(self) -> None:
        """Remove the highlight."""
        self._sel = self._anchor = None
        self._repaint()

    def scroll_target(self, row: int) -> QWidget:
        """A child positioned at `row`, for `QScrollArea.ensureWidgetVisible`."""
        for (s, e), block in self._blocks.items():
            if s <= row < e:
                self._marker.setGeometry(0, block.y() + (row - s) * self.row_h, 1, self.row_h)
                break
        self._marker.show()
        return self._marker

    def _repaint(self) -> None:
        for block in self._blocks.values():
            block.update()

    def _is_selected(self, line: dict) -> bool:
        if self._sel is None:
            return False
        side, a, b = self._sel
        n = _num(line, side)
        return n is not None and a <= n <= b

    def _side_at(self, row_index: int, col: int) -> str | None:
        """Selection side for a press on the gutter of `row_index` (column in split), or None."""
        row = self.rows_[row_index]
        if row.kind == "line":
            return "old" if row.line["t"] == "-" else "new"
        if row.kind == "pair":
            if col == 0:
                if row.left is None:
                    return None
                return "old" if row.left["t"] == "-" else "new"
            return "new" if row.right is not None else None
        return None

    def _press(self, row_index: int, col: int, shift: bool) -> None:
        if shift and self._sel is not None:
            side = self._sel[0]
            num = _row_num(self.rows_[row_index], side)
            if num is None:
                return
            if self._anchor is None or self._anchor[0] != side:
                self._anchor = (side, self._sel[1])
        else:
            side = self._side_at(row_index, col)
            if side is None:
                return
            num = _row_num(self.rows_[row_index], side)
            if num is None:
                return
            self._anchor = (side, num)
        self._dragging = True
        self._extend(num)

    def _extend(self, num: int) -> None:
        side, anchor = self._anchor
        self._sel = (side, min(anchor, num), max(anchor, num))
        self._repaint()

    def _drag(self, pos: QPoint) -> None:
        if not self._dragging or self._anchor is None or not self._blocks:
            return
        blocks = sorted(self._blocks.values(), key=lambda b: b.y())
        target = blocks[0]
        for b in blocks:
            if b.y() <= pos.y():
                target = b
        index = target.start + (pos.y() - target.y()) // self.row_h
        index = min(max(index, target.start), target.end - 1)
        num = _row_num(self.rows_[index], self._anchor[0])
        if num is not None:
            self._extend(num)

    def _release(self) -> None:
        if self._dragging and self._sel is not None:
            self.rangeSelected.emit(*self._sel)
        self._dragging = False
