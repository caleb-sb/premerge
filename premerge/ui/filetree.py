"""Left pane of the Files tab: filter box, viewed progress and the changed-files tree."""
from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QFontDatabase, QFontMetrics, QPainter, QStandardItem,
                           QStandardItemModel)
from PySide6.QtWidgets import (QAbstractItemView, QLabel, QLineEdit, QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QTreeView, QVBoxLayout, QWidget)

from premerge.core.paths import build_tree
from premerge.ui import icons
from premerge.ui.theme import NIGHT, Theme

PATH, KIND, STATUS, VIEWED, CHANGED, COUNT, TIP = (Qt.ItemDataRole.UserRole + i for i in range(1, 8))
LETTERS = {"added": "A", "modified": "M", "deleted": "D", "renamed": "R", "copied": "C"}


class ProgressBar(QWidget):
    """A thin 6 px bar: gutter track with an ok-coloured fill."""

    def __init__(self, t: Theme = NIGHT, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t = t
        self._frac = 0.0
        self.setFixedHeight(6)

    def set_fraction(self, frac: float) -> None:
        """Set the filled share (0..1) and repaint."""
        self._frac = max(0.0, min(1.0, frac))
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        r = QRectF(self.rect())
        p.setBrush(QColor(self._t.gutter))
        p.drawRoundedRect(r, 3, 3)
        if self._frac > 0:
            p.setBrush(QColor(self._t.ok))
            p.drawRoundedRect(QRectF(r.x(), r.y(), max(6.0, r.width() * self._frac), r.height()), 3, 3)


class FileDelegate(QStyledItemDelegate):
    """Paints file rows: status letter, base name, comment badge and viewed check."""

    def __init__(self, t: Theme = NIGHT, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t = t
        self._mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self._mono.setBold(True)
        self._mono.setPixelSize(12)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(0, 26)

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        if index.data(KIND) != "file":
            super().paint(p, option, index)
            return
        t = self._t
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        opt.icon = type(opt.icon)()
        style = opt.widget.style() if opt.widget else None
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, p, opt.widget)
        r: QRect = option.rect
        viewed, changed = bool(index.data(VIEWED)), bool(index.data(CHANGED))
        status = index.data(STATUS)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cy = r.center().y()
        right = r.right() - 8
        if viewed and not changed:
            p.drawPixmap(QPoint(right - 13, cy - 7), icons.pixmap("check", t.ok, 14))
            right -= 22
        elif changed:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.warn))
            p.drawEllipse(QPoint(right - 4, cy), 4, 4)
            right -= 18
        count = index.data(COUNT) or 0
        if count:
            font = QFont(option.font)
            font.setPixelSize(11)
            fm = QFontMetrics(font)
            w = 6 + 12 + 3 + fm.horizontalAdvance(str(count)) + 6
            box = QRect(right - w + 1, cy - 9, w, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.bg_highlight))
            p.drawRoundedRect(box, 9, 9)
            p.drawPixmap(QPoint(box.x() + 6, cy - 6), icons.pixmap("message", t.fg_dark, 12))
            p.setFont(font)
            p.setPen(QColor(t.fg_dark))
            p.drawText(QRect(box.x() + 21, box.y(), w - 21, box.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, str(count))
            right = box.left() - 6
        p.setFont(self._mono)
        p.setPen(QColor(getattr(t, f"st_{status}", t.muted) if status != "copied" else t.st_renamed))
        letter = LETTERS.get(status, "?")
        p.drawText(QRect(r.x() + 6, r.y(), 14, r.height()), Qt.AlignmentFlag.AlignCenter, letter)
        name_font = QFont(option.font)
        name_font.setStrikeOut(status == "deleted")
        p.setFont(name_font)
        dim = viewed and not changed or status == "deleted"
        p.setPen(QColor(t.muted if dim else t.fg))
        name = index.data(PATH).rsplit("/", 1)[-1]
        avail = max(0, right - (r.x() + 26))
        text = QFontMetrics(name_font).elidedText(name, Qt.TextElideMode.ElideMiddle, avail)
        p.drawText(QRect(r.x() + 26, r.y(), avail, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        p.restore()


class FileTree(QWidget):
    """Filterable tree of changed files with status, comment and viewed markers."""

    fileActivated = Signal(str)

    def __init__(self, parent: QWidget | None = None, t: Theme = NIGHT) -> None:
        super().__init__(parent)
        self._t = t
        self._collapsed: set[str] = set()
        self._items: dict[str, QStandardItem] = {}
        self._dirs: dict[str, QStandardItem] = {}
        self._filtering = False
        self._syncing = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter changed files…")
        self._filter.setClearButtonEnabled(True)
        self._filter.addAction(QAction(icons.icon("search", t, t.muted), "", self._filter),
                               QLineEdit.ActionPosition.LeadingPosition)
        self._filter.textChanged.connect(self._apply_filter)
        self._filter.installEventFilter(self)
        lay.addWidget(self._filter)

        self._label = QLabel()
        self._label.setStyleSheet(f"color: {t.muted}; font-size: 12px;")
        lay.addWidget(self._label)
        self._bar = ProgressBar(t)
        lay.addWidget(self._bar)

        self._model = QStandardItemModel(self)
        self._view = QTreeView()
        self._view.setModel(self._model)
        self._view.setHeaderHidden(True)
        self._view.setRootIsDecorated(True)
        self._view.setUniformRowHeights(True)
        self._view.setIndentation(14)
        self._view.setAnimated(True)
        self._view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._view.setItemDelegate(FileDelegate(t, self._view))
        self._view.setFrameShape(QTreeView.Shape.NoFrame)
        self._view.clicked.connect(self._clicked)
        self._view.activated.connect(self._activated)
        self._view.expanded.connect(lambda i: self._remember(i, True))
        self._view.collapsed.connect(lambda i: self._remember(i, False))
        lay.addWidget(self._view, 1)
        self._update_progress(0, 0)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._filter and event.type() == event.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self._filter.clear()
            return True
        return super().eventFilter(obj, event)

    def focus_filter(self) -> None:
        """Put keyboard focus in the filter box."""
        self._filter.setFocus()
        self._filter.selectAll()

    def set_files(self, files: list[dict], viewed: set[str], changed: set[str], comments: dict[str, int]) -> None:
        """Rebuild the tree; directory collapse state and the current file survive."""
        current = self._current_path()
        by_path = {f["path"]: f for f in files}
        self._syncing = True
        self._model.clear()
        self._items.clear()
        self._dirs.clear()
        folder = icons.icon("folder", self._t, self._t.muted)

        def add(node: dict, parent: QStandardItem) -> None:
            for d in node["dirs"]:
                item = QStandardItem(folder, d["name"])
                item.setData("dir", KIND)
                item.setData(d["path"], PATH)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                parent.appendRow(item)
                self._dirs[d["path"]] = item
                add(d, item)
            for path in node["files"]:
                f = by_path[path]
                item = QStandardItem(path.rsplit("/", 1)[-1])
                item.setData("file", KIND)
                item.setData(path, PATH)
                item.setData(f.get("status"), STATUS)
                item.setData(path in viewed, VIEWED)
                item.setData(path in changed, CHANGED)
                item.setData(comments.get(path, 0), COUNT)
                tip = path
                if f.get("status") == "renamed" and f.get("oldPath"):
                    tip += f"\nrenamed from {f['oldPath']}"
                item.setToolTip(tip)
                parent.appendRow(item)
                self._items[path] = item

        add(build_tree(list(by_path)), self._model.invisibleRootItem())
        self._order = self._walk_order()
        self._view.expandAll()
        for path, item in self._dirs.items():
            if path in self._collapsed:
                self._view.collapse(item.index())
        self._syncing = False
        self._update_progress(sum(1 for p in by_path if p in viewed), len(by_path))
        self._apply_filter()
        if current in self._items:
            self._view.setCurrentIndex(self._items[current].index())

    def ordered_paths(self) -> list[str]:
        """All file paths in display order, ignoring the filter."""
        return list(self._order)

    def select_path(self, path: str) -> None:
        """Highlight `path`, expanding its parents and scrolling it into view; emits nothing."""
        item = self._items.get(path)
        if item is None:
            return
        self._view.blockSignals(True)
        self._view.setCurrentIndex(item.index())
        self._view.blockSignals(False)
        parent = item.parent()
        while parent is not None:
            self._view.expand(parent.index())
            parent = parent.parent()
        idx = item.index()
        if not self._view.viewport().rect().contains(self._view.visualRect(idx)):
            self._view.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _walk_order(self) -> list[str]:
        out: list[str] = []

        def walk(item: QStandardItem) -> None:
            for r in range(item.rowCount()):
                child = item.child(r)
                if child.data(KIND) == "file":
                    out.append(child.data(PATH))
                else:
                    walk(child)

        walk(self._model.invisibleRootItem())
        return out

    def _current_path(self) -> str | None:
        idx = self._view.currentIndex()
        return idx.data(PATH) if idx.isValid() and idx.data(KIND) == "file" else None

    def _update_progress(self, done: int, total: int) -> None:
        self._label.setText(f"{done} of {total} viewed")
        self._bar.set_fraction(done / total if total else 0.0)

    def _remember(self, index: QModelIndex, expanded: bool) -> None:
        if self._filtering or self._syncing:
            return
        path = index.data(PATH)
        (self._collapsed.discard if expanded else self._collapsed.add)(path)

    def _apply_filter(self) -> None:
        needle = self._filter.text().strip().casefold()
        self._filtering = bool(needle)
        self._syncing = True

        def visit(item: QStandardItem) -> bool:
            any_visible = False
            index = item.index() if item is not self._model.invisibleRootItem() else QModelIndex()
            for r in range(item.rowCount()):
                child = item.child(r)
                if child.data(KIND) == "file":
                    show = not needle or needle in child.data(PATH).casefold()
                else:
                    show = visit(child)
                self._view.setRowHidden(r, index, not show)
                any_visible = any_visible or show
            return any_visible

        visit(self._model.invisibleRootItem())
        for path, item in self._dirs.items():
            self._view.setExpanded(item.index(), bool(needle) or path not in self._collapsed)
        self._syncing = False

    def _clicked(self, index: QModelIndex) -> None:
        if index.data(KIND) == "dir":
            self._view.setExpanded(index, not self._view.isExpanded(index))
        else:
            self.fileActivated.emit(index.data(PATH))

    def _activated(self, index: QModelIndex) -> None:
        if index.data(KIND) == "file":
            self.fileActivated.emit(index.data(PATH))
