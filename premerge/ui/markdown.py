"""A read-only Markdown view that sizes itself to its content."""

import html

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFontDatabase, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat
from PySide6.QtWidgets import QFrame, QTextBrowser, QWidget

from .theme import NIGHT


class MarkdownView(QTextBrowser):
    """Renders GitHub-flavoured Markdown; its height follows the content."""

    def __init__(self, parent: QWidget | None = None, placeholder: str = "") -> None:
        super().__init__(parent)
        self._placeholder = placeholder
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)
        self.setStyleSheet("QTextBrowser { background: transparent; border: none; padding: 0; }")
        self.document().contentsChanged.connect(self._fit)
        self.set_markdown("")

    def set_markdown(self, text: str) -> None:
        """Show `text` rendered as Markdown (or the placeholder when empty)."""
        code_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
        doc = self.document()
        doc.setDefaultStyleSheet(
            f"code, pre {{ background-color: {NIGHT.bg_highlight}; color: {NIGHT.fg};"
            f" font-family: '{code_font}'; }}"
            f" a {{ color: {NIGHT.accent}; }}"
            f" h1, h2, h3 {{ color: {NIGHT.fg}; }}"
        )
        if text.strip():
            doc.setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
            self._style_code()
        elif self._placeholder:
            doc.setHtml(f'<p style="color: {NIGHT.muted}">{html.escape(self._placeholder)}</p>')
        else:
            doc.clear()
        self._fit()

    def _style_code(self) -> None:
        """Give code spans and fenced blocks the code font and background (setMarkdown ignores the stylesheet)."""
        doc = self.document()
        code_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        bg = QColor(NIGHT.bg_highlight)
        block = doc.begin()
        while block.isValid():
            fmt = block.blockFormat()
            is_fence = fmt.hasProperty(QTextFormat.Property.BlockCodeFence) or fmt.nonBreakableLines()
            if is_fence:
                cur = QTextCursor(block)
                fmt.setBackground(bg)
                cur.setBlockFormat(fmt)
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and (is_fence or frag.charFormat().fontFixedPitch()):
                    cur = QTextCursor(doc)
                    cur.setPosition(frag.position())
                    cur.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
                    cf = QTextCharFormat()
                    cf.setFont(code_font)
                    cf.setForeground(QColor(NIGHT.fg))
                    if not is_fence:
                        cf.setBackground(bg)
                    cur.mergeCharFormat(cf)
                it += 1
            block = block.next()

    def _content_height(self) -> int:
        doc = self.document()
        doc.setTextWidth(max(self.viewport().width(), 1))
        return int(doc.size().height()) + 2

    def _fit(self) -> None:
        height = self._content_height()
        if height != self.height():
            self.setFixedHeight(height)

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), self._content_height())

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self._content_height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()
