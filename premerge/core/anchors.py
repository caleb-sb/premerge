"""Placing a line comment on current code: exact line, moved line, or missing."""
from __future__ import annotations


def line_no(line: dict, side: str) -> int | None:
    """The line number of a diff Line on the given side ('old' or 'new'), or None if it has none."""
    if side == "old":
        return None if line["t"] == "+" else line["o"]
    return None if line["t"] == "-" else line["n"]


def _pick(numbers: list[tuple[int, str]], comment: dict):
    """Choose among (number, text) candidates: exact line first, else nearest with the same text."""
    want, ln = comment.get("anchorText", ""), comment["line"]
    for i, (num, text) in enumerate(numbers):
        if num == ln and text == want:
            return i, num, "ok"
    if want.strip():
        hits = [(i, num) for i, (num, text) in enumerate(numbers) if text == want]
        if hits:
            i, num = min(hits, key=lambda h: abs(h[1] - ln))
            return i, num, "moved"
    return None, None, "missing"


def locate_in_rows(lines: list[dict], comment: dict) -> tuple[int | None, str]:
    """Row index in a hunk's lines where the comment belongs, with state 'ok'|'moved'|'missing'."""
    side = comment["side"]
    cands = [(i, n, ln["s"]) for i, ln in enumerate(lines) if (n := line_no(ln, side)) is not None]
    k, _, state = _pick([(n, s) for _, n, s in cands], comment)
    return (cands[k][0] if k is not None else None), state


def locate_in_text(text_lines: list[str], comment: dict) -> tuple[int | None, str]:
    """1-based line number in a file's lines where the comment's anchor is now, with its state."""
    _, num, state = _pick([(i + 1, s) for i, s in enumerate(text_lines)], comment)
    return num, state
