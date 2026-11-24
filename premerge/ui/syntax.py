"""Pygments-based syntax highlighting producing per-line colour spans."""

from collections import OrderedDict

from pygments.lexers import get_lexer_for_filename, guess_lexer_for_filename
from pygments.util import ClassNotFound

from . import theme

Span = tuple[int, int, str, bool, bool]  # start, length, hex colour, bold, italic

MAX_LINES = 20_000
MAX_LINE_LEN = 5_000
GUESS_LIMIT = 50_000
_CACHE: OrderedDict[tuple[str, int], list[list[Span]]] = OrderedDict()
_CACHE_SIZE = 64


def _lexer(path: str, text: str):
    try:
        return get_lexer_for_filename(path, stripnl=False, ensurenl=False)
    except ClassNotFound:
        pass
    if len(text) >= GUESS_LIMIT:
        return None
    try:
        return guess_lexer_for_filename(path, text, stripnl=False, ensurenl=False)
    except ClassNotFound:
        return None


def _lex(path: str, lines: list[str]) -> list[list[Span]]:
    result: list[list[Span]] = [[] for _ in lines]
    if not lines or len(lines) > MAX_LINES or any(len(s) > MAX_LINE_LEN for s in lines):
        return result
    text = "\n".join(lines)
    lexer = _lexer(path, text)
    if lexer is None:
        return result
    row = col = 0
    for ttype, value in lexer.get_tokens(text):
        color, bold, italic = theme.syntax_color(ttype)
        for k, part in enumerate(value.split("\n")):
            if k:
                row += 1
                col = 0
            if not part:
                continue
            if row < len(result) and (color != theme.NIGHT.fg or bold or italic):
                result[row].append((col, len(part), color, bold, italic))
            col += len(part)
    return result


def highlight_lines(path: str, lines: list[str]) -> list[list[Span]]:
    """Colour spans for each line: (start, length, hex, bold, italic)."""
    key = (path, hash("\n".join(lines)))
    hit = _CACHE.get(key)
    if hit is not None:
        _CACHE.move_to_end(key)
        return hit
    result = _lex(path, lines)
    _CACHE[key] = result
    if len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return result


def annotate(path: str, hunks: list[dict]) -> None:
    """Store spans on each hunk line as `line["_hl"]` (context lines take new-side spans)."""
    old = [ln for h in hunks for ln in h["lines"] if ln["t"] != "+"]
    new = [ln for h in hunks for ln in h["lines"] if ln["t"] != "-"]
    for lines in (old, new):
        for ln, spans in zip(lines, highlight_lines(path, [ln["s"] for ln in lines])):
            ln["_hl"] = spans
