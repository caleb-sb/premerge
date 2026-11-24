"""Tokyo Night *Night* colours, palette and stylesheet for premerge (no light theme)."""

from dataclasses import dataclass, field
from functools import lru_cache

from PySide6.QtGui import QColor, QPalette
from pygments.token import Token, _TokenType

_SYNTAX = {
    "keyword": "#bb9af7",
    "constant": "#ff9e64",
    "type": "#2ac3de",
    "function": "#7aa2f7",
    "decorator": "#e0af68",
    "tag": "#f7768e",
    "attribute": "#73daca",
    "string": "#9ece6a",
    "escape": "#b4f9f8",
    "number": "#ff9e64",
    "comment": "#565f89",
    "operator": "#89ddff",
    "heading": "#7aa2f7",
    "error": "#db4b4b",
}


@dataclass(frozen=True)
class Theme:
    bg: str  # main surfaces
    bg_dark: str  # toolbar, status bar, menus, inputs
    bg_highlight: str  # hover
    canvas: str
    border: str
    fg: str
    fg_dark: str
    muted: str  # disabled text, hints
    gutter: str  # scrollbar handles
    accent: str
    accent_soft: str  # checked buttons
    on_accent: str  # text on accent
    shadow: str
    ok: str
    warn: str
    bad: str
    diff_add_bg: str
    diff_add_gutter: str
    diff_del_bg: str
    diff_del_gutter: str
    hunk_bg: str
    hunk_fg: str
    sel_bg: str
    sel_gutter: str
    st_added: str
    st_modified: str
    st_deleted: str
    st_renamed: str
    you: str
    agent: str
    syntax: dict[str, str] = field(default_factory=lambda: dict(_SYNTAX))


NIGHT = Theme(
    bg="#1a1b26",
    bg_dark="#16161e",
    bg_highlight="#292e42",
    canvas="#101014",
    border="#2a2c3c",
    fg="#c0caf5",
    fg_dark="#a9b1d6",
    muted="#565f89",
    gutter="#3b4261",
    accent="#7aa2f7",
    accent_soft="#2c3a5e",
    on_accent="#16161e",
    shadow="#000000",
    ok="#9ece6a",
    warn="#e0af68",
    bad="#f7768e",
    diff_add_bg="#20303b",
    diff_add_gutter="#1f3d3e",
    diff_del_bg="#37222c",
    diff_del_gutter="#4b2632",
    hunk_bg="#1f2335",
    hunk_fg="#7aa2f7",
    sel_bg="#283457",
    sel_gutter="#3d59a1",
    st_added="#9ece6a",
    st_modified="#e0af68",
    st_deleted="#f7768e",
    st_renamed="#7dcfff",
    you="#7aa2f7",
    agent="#bb9af7",
)

# Token types checked against the token's ancestry, most specific first.
_RULES: tuple[tuple[_TokenType, str, bool, bool], ...] = (
    (Token.Keyword.Constant, "constant", False, False),
    (Token.Keyword.Type, "type", False, False),
    (Token.Keyword, "keyword", False, False),
    (Token.Name.Function, "function", False, False),
    (Token.Name.Class, "type", False, False),
    (Token.Name.Builtin, "type", False, False),
    (Token.Name.Namespace, "fg_dark", False, False),
    (Token.Name.Exception, "type", False, False),
    (Token.Name.Decorator, "decorator", False, False),
    (Token.Name.Tag, "tag", False, False),
    (Token.Name.Attribute, "attribute", False, False),
    (Token.String.Escape, "escape", False, False),
    (Token.String.Regex, "escape", False, False),
    (Token.String, "string", False, False),
    (Token.Number, "number", False, False),
    (Token.Comment, "comment", False, True),
    (Token.Operator, "operator", False, False),
    (Token.Punctuation, "operator", False, False),
    (Token.Generic.Heading, "heading", True, False),
    (Token.Generic.Subheading, "heading", True, False),
    (Token.Error, "error", False, False),
)


@lru_cache(maxsize=None)
def syntax_color(ttype: _TokenType) -> tuple[str, bool, bool]:
    """Map a Pygments token type to (hex colour, bold, italic)."""
    for rule, key, bold, italic in _RULES:
        if ttype in rule:
            color = getattr(NIGHT, key) if key == "fg_dark" else NIGHT.syntax[key]
            return color, bold, italic
    return NIGHT.fg, False, False


def palette(t: Theme) -> QPalette:
    """The Qt palette for the theme."""
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: t.bg,
        QPalette.ColorRole.WindowText: t.fg,
        QPalette.ColorRole.Base: t.bg_dark,
        QPalette.ColorRole.AlternateBase: t.bg_highlight,
        QPalette.ColorRole.Text: t.fg,
        QPalette.ColorRole.Button: t.bg_highlight,
        QPalette.ColorRole.ButtonText: t.fg,
        QPalette.ColorRole.BrightText: t.fg,
        QPalette.ColorRole.Highlight: t.accent,
        QPalette.ColorRole.HighlightedText: t.on_accent,
        QPalette.ColorRole.ToolTipBase: t.bg_dark,
        QPalette.ColorRole.ToolTipText: t.fg,
        QPalette.ColorRole.PlaceholderText: t.muted,
        QPalette.ColorRole.Link: t.accent,
        QPalette.ColorRole.Light: t.bg_highlight,
        QPalette.ColorRole.Midlight: t.bg_highlight,
        QPalette.ColorRole.Mid: t.border,
        QPalette.ColorRole.Dark: t.bg_dark,
        QPalette.ColorRole.Shadow: t.shadow,
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.muted))
    return p


def stylesheet(t: Theme) -> str:
    """The application stylesheet."""
    accent_hover = QColor(t.accent).lighter(112).name()
    return f"""
    QMainWindow, QDialog, QMessageBox {{ background: {t.bg}; }}

    QToolBar {{
        background: {t.bg_dark};
        border: none;
        border-bottom: 1px solid {t.border};
        padding: 6px 10px;
        spacing: 4px;
    }}
    QToolBar::separator {{ background: {t.border}; width: 1px; margin: 6px 8px; }}

    QToolButton {{
        background: transparent;
        color: {t.fg};
        border: none;
        border-radius: 7px;
        padding: 6px;
    }}
    QToolButton:hover {{ background: {t.bg_highlight}; }}
    QToolButton:pressed {{ background: {t.gutter}; }}
    QToolButton:checked {{ background: {t.accent_soft}; color: {t.accent}; }}
    QToolButton:disabled {{ color: {t.muted}; }}

    QFrame#segment {{
        background: {t.bg};
        border: 1px solid {t.border};
        border-radius: 9px;
    }}
    QFrame#segment QToolButton {{ border-radius: 6px; padding: 5px; }}

    QFrame#splitButton {{
        border: 1px solid {t.border};
        border-radius: 8px;
    }}
    QFrame#splitButton QToolButton#splitMain {{
        border-top-right-radius: 0; border-bottom-right-radius: 0; padding: 5px 10px 5px 8px;
    }}
    QFrame#splitButton QToolButton#splitArrow {{
        border-left: 1px solid {t.border};
        border-top-left-radius: 0; border-bottom-left-radius: 0; padding: 5px 7px;
    }}
    QToolButton#splitArrow::menu-indicator {{ image: none; width: 0; }}

    QToolButton#primary {{
        background: {t.accent};
        color: {t.on_accent};
        font-weight: 600;
        padding: 6px 14px 6px 10px;
    }}
    QToolButton#primary:hover {{ background: {accent_hover}; }}
    QToolButton#primary:disabled {{ background: {t.bg_highlight}; color: {t.muted}; }}

    QStatusBar {{
        background: {t.bg_dark};
        color: {t.fg_dark};
        border-top: 1px solid {t.border};
    }}
    QStatusBar QLabel {{ color: {t.fg_dark}; padding: 2px 8px; }}
    QStatusBar::item {{ border: none; }}

    QMenu {{
        background: {t.bg_dark};
        color: {t.fg};
        border: 1px solid {t.border};
        border-radius: 10px;
        padding: 6px;
    }}
    QMenu::item {{ padding: 7px 28px 7px 10px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {t.bg_highlight}; }}
    QMenu::icon {{ padding-left: 10px; }}
    QMenu::separator {{ height: 1px; background: {t.border}; margin: 5px 8px; }}

    QToolTip {{
        background: {t.bg_dark};
        color: {t.fg};
        border: 1px solid {t.border};
        border-radius: 6px;
        padding: 5px 8px;
    }}

    QPushButton {{
        background: {t.bg_highlight};
        color: {t.fg};
        border: 1px solid {t.border};
        border-radius: 7px;
        padding: 6px 16px;
        min-width: 64px;
    }}
    QPushButton:hover {{ border-color: {t.accent}; }}
    QPushButton:default {{ background: {t.accent}; color: {t.on_accent}; border-color: {t.accent}; }}

    QLineEdit {{
        background: {t.bg_dark};
        color: {t.fg};
        border: 1px solid {t.border};
        border-radius: 7px;
        padding: 5px 8px;
        selection-background-color: {t.accent};
        selection-color: {t.on_accent};
    }}
    QLineEdit:focus {{ border-color: {t.accent}; }}
    QLineEdit:read-only {{ color: {t.fg_dark}; background: transparent; }}
    QLineEdit[invalid="true"] {{ border-color: {t.bad}; }}

    QPlainTextEdit, QTextEdit {{
        background: {t.bg_dark};
        color: {t.fg};
        border: 1px solid {t.border};
        border-radius: 7px;
        padding: 6px;
        selection-background-color: {t.accent};
        selection-color: {t.on_accent};
    }}
    QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {t.accent}; }}

    QComboBox {{
        background: {t.bg_dark};
        color: {t.fg};
        border: 1px solid {t.border};
        border-radius: 7px;
        padding: 5px 8px;
    }}
    QComboBox:hover, QComboBox:focus {{ border-color: {t.accent}; }}
    QComboBox:disabled {{ color: {t.fg_dark}; background: transparent; }}
    QComboBox::drop-down {{ border: none; background: transparent; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: {t.bg_dark};
        color: {t.fg};
        border: 1px solid {t.border};
        selection-background-color: {t.bg_highlight};
        selection-color: {t.fg};
        outline: none;
    }}

    QTabBar::tab {{
        background: transparent;
        color: {t.fg_dark};
        padding: 8px 14px;
        border: none;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{ color: {t.fg}; border-bottom: 2px solid {t.accent}; }}
    QTabBar::tab:hover {{ color: {t.fg}; }}

    QTreeView {{ background: {t.bg_dark}; border: none; outline: none; }}
    QTreeView::item {{ padding: 3px; }}
    QTreeView::item:selected {{ background: {t.bg_highlight}; color: {t.fg}; }}
    QTreeView::item:hover {{ background: {t.bg_highlight}; }}

    QSplitter::handle {{ background: {t.border}; }}
    QSplitter::handle:horizontal {{ width: 1px; }}
    QSplitter::handle:vertical {{ height: 1px; }}

    QCheckBox {{ color: {t.fg}; }}
    QCheckBox::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {t.border};
        border-radius: 4px;
    }}
    QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}

    QLabel#h1 {{ font-size: 22px; color: {t.fg}; }}
    QLabel#muted {{ color: {t.muted}; }}
    QLabel#chip {{
        background: {t.bg_highlight};
        border-radius: 9px;
        padding: 2px 8px;
        color: {t.fg_dark};
    }}
    QFrame#card {{ background: {t.bg}; border: 1px solid {t.border}; border-radius: 9px; }}
    QFrame#card QLabel {{ background: transparent; }}
    QFrame#cardHeader {{
        background: {t.bg_dark};
        border: none;
        border-bottom: 1px solid {t.border};
        border-top-left-radius: 9px;
        border-top-right-radius: 9px;
    }}
    QFrame#thread {{ background: {t.bg}; border: 1px solid {t.border}; border-radius: 8px; }}
    QFrame#threadFoot {{ background: {t.bg_dark}; border: none; border-top: 1px solid {t.border}; }}

    QScrollArea {{ background: transparent; border: none; }}
    QAbstractScrollArea::corner {{ background: {t.canvas}; }}
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
    QScrollBar::handle {{ background: {t.gutter}; border-radius: 4px; }}
    QScrollBar::handle:vertical {{ min-height: 40px; margin: 0 2px; }}
    QScrollBar::handle:horizontal {{ min-width: 40px; margin: 2px 0; }}
    QScrollBar::handle:hover {{ background: {t.muted}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
    """


def apply(app) -> None:
    """Apply the Fusion style, palette and stylesheet to the application."""
    app.setStyle("Fusion")
    app.setPalette(palette(NIGHT))
    app.setStyleSheet(stylesheet(NIGHT))
