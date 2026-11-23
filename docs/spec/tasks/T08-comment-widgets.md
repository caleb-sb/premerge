# T08 — Comment thread and composer widgets

## Goal
Reusable widgets to show one comment thread (root comment + replies + actions) and to write a new comment/reply.
They only emit signals; the pages connect them to the Session (T09/T10).

## Read
- `docs/spec/00-overview.md` (§4 Comment/Reply shapes, §5 colours)
- `premerge/ui/markdown.py`, `premerge/ui/theme.py` (fields, stylesheet object names), `premerge/ui/icons.py`
  (names), `tests/qt.py`

## Create
`premerge/ui/comments.py`, `tests/test_comments.py`

## API
```python
def ago(iso: str, now: datetime | None = None) -> str   # "just now", "5m ago", "3h ago", "2d ago", else "23 Nov"

class Composer(QFrame):                      # objectName "thread"
    submitted = Signal(str)                  # stripped non-empty text
    cancelled = Signal()
    def __init__(self, label: str = "", placeholder: str = "Leave a comment…", submit_text: str = "Comment",
                 cancellable: bool = True, compact: bool = False, parent=None)
    def text(self) -> str; def set_text(self, s: str); def clear(self); def focus_editor(self)
    def set_label(self, s: str)

class CommentThread(QFrame):                 # objectName "thread"
    replyRequested = Signal(str, str)        # cid, text
    statusRequested = Signal(str, str)       # cid, "open" | "resolved"
    editRequested = Signal(str, str)         # cid, new body
    deleteRequested = Signal(str)            # cid
    def __init__(self, comment: dict, user_name: str = "", show_location: bool = False, parent=None)
    def comment_id(self) -> str
    def update_comment(self, comment: dict) -> None   # refresh in place, keeping any reply draft and focus
    def reply_draft(self) -> str
```
`EXPANDED: set[str]` module-level — ids of resolved threads the user expanded (survives widget rebuilds).

## Composer
- Optional muted label line (e.g. "Commenting on lines 12–14"). A `QPlainTextEdit` (min 3 lines, grows with
  content up to 12 lines, placeholder). Buttons right-aligned: Cancel (if cancellable) and a default button
  (`submit_text`, disabled while empty). Ctrl+Enter submits, Esc cancels (if cancellable), hint "Ctrl+Enter to
  submit" muted 11 px at the left (show "⌘↩" on macOS).
- `compact=True` (reply box): a single-line-looking editor with placeholder "Reply…", buttons hidden until focused
  or non-empty.
- After `submitted`, the composer does **not** clear itself (the owner clears it once the store write succeeded).

## CommentThread
- Max width 920 px (`setMaximumWidth`), `QFrame#thread`.
- Each entry (root, then replies): header row = avatar (20 px circle: `you` colour with the user's initial, or
  `agent` colour with the `bot` icon), name in bold ("You"/user name for `you`, "Agent" for `agent`), muted
  `ago(created)`; for the root also, when `show_location` and kind is line: muted "path:line" (or lines a–b);
  pills "Resolved" (ok colour) when resolved. Body = `MarkdownView`. Agent entries get a faint `agent`-tinted
  background (agent colour at ~8% alpha over bg).
- Root actions (small flat tool buttons on the header's right): edit (`pencil`; only for author `you`) swaps the
  body for an inline Composer prefilled with the body (Save/Cancel) → `editRequested`; delete (`trash`) asks a
  `QMessageBox.question` "Delete this comment and its replies?" → `deleteRequested`.
- Footer `QFrame#threadFoot`: compact Composer (reply) → `replyRequested(cid, text)`; a button "Resolve"
  (→ `statusRequested(cid, "resolved")`) or "Reopen" when resolved.
- Resolved threads render collapsed unless `cid in EXPANDED`: one clickable row — `valid` icon (ok), "Resolved",
  first line of the root body (elided), "· N replies", latest author — clicking expands (adds to `EXPANDED`);
  expanded resolved threads get a "Collapse" link in the footer that removes it.
- `update_comment` rebuilds entries but keeps the reply composer instance (and its text/focus).

## Tests
- `ago` boundaries (30 s, 5 min, 3 h, 2 d, 40 d).
- Composer: typing + Ctrl+Enter emits `submitted` with stripped text; empty text keeps the button disabled; Esc
  emits `cancelled`.
- Thread for an open comment with one agent reply shows 2 entries and a Resolve button; clicking Resolve emits
  `statusRequested(id, "resolved")`; typing a reply and submitting emits `replyRequested`.
- Resolved thread is collapsed; clicking expands it and adds the id to `EXPANDED`.
- `update_comment` with an extra reply keeps a typed reply draft.

## Acceptance
Tests pass. Add `@shot("threads")`: a 960×700 widget stacking a Composer with a label, an open thread (you + agent
reply, markdown with inline code and a list), and a collapsed resolved thread. Look at it and describe it.
