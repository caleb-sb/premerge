# T10 — Overview page (PR description, conversation, summary)

## Goal
The Overview tab: what the PR page will look like, with the title/description draft editable in place, general
comments for the agent, a summary of all review comments, and a details sidebar. Replace the placeholder in
`MainWindow._make_overview()`.

## Read
- `docs/spec/00-overview.md` (§3, §4 Description/Meta)
- Public APIs only: `premerge/ui/session.py`, `premerge/ui/comments.py`, `premerge/ui/markdown.py`,
  `premerge/ui/theme.py` (fields/object names); `premerge/ui/window.py` (`_make_overview`, `show_file`);
  `tools/shot.py` (decorator usage); `tests/qt.py`

## Create / modify
`premerge/ui/overview.py`, `tests/test_overview.py`; modify `premerge/ui/window.py` (`_make_overview`),
`tools/shot.py` (replace `overview`, add `overview-edit`).

## `class OverviewPage(QWidget)` — `OverviewPage(session, parent=None)`
- Signal `openComment(str, str)` (path, comment id) — MainWindow connects it to `show_file`.
- `QScrollArea` with a two-column layout: main column (stretch, max 900 px) and a 260 px sidebar; below 1000 px
  window width the sidebar moves under the main column.

### Description card (`QFrame#card`)
- Header (`QFrame#cardHeader`): avatar initial + bold user name + muted "· description draft" if
  `description.saved`, else muted "· not saved yet — prefilled from <source>"; stretch; "Edit" button (`pencil`).
- Body: `MarkdownView` of the body, or muted "No description provided."
- **Edit mode** (replaces the card body; the PR header title in MainWindow keeps showing the saved title):
  title `QLineEdit` (18 px); "Write" / "Preview" toggle (two checkable flat buttons); Write = `QPlainTextEdit` in the
  code font, min height 280, tab inserts 2 spaces; Preview = `MarkdownView` of the current text; buttons: Save
  (default; Ctrl+S) → `session.save_description(title, body)` then leave edit mode; Cancel (Esc, confirm if
  modified); "Reset to default" (only when saved; confirm) → `session.reset_description()`.
- While editing, `reviewChanged` must not replace the editor contents. If the stored description changes on disk
  while editing (e.g. the agent ran `premerge describe`), show a warn bar in the card: "The description was changed
  outside the editor." with "Load it" (replace editor text) and "Keep mine" (dismiss).

### Conversation
- Heading "Conversation" (bold 15 px). General comments (`session.general_comments()`) as `CommentThread`s
  (kept by id and updated in place, like the files page), oldest first, connected to the session mutations.
- An always-present `Composer(placeholder="Leave a general comment for the agent — about the approach, the
  description, anything…", cancellable=False)` → `session.add_comment({"kind": "general", "body": text})`;
  cleared on success.

### Review comments summary
- Heading "Review comments" with muted "N open · M resolved"; hidden when there are none.
- A list (one row per line/file comment, grouped by file in tree order, open first): status dot (warn open / ok
  resolved), mono "path:line" (or "path" for file comments), elided first line of the body (muted), and on the
  right "🤖" (bot icon) when the latest reply is by the agent. Clicking a row emits `openComment(path, id)`.

### Sidebar (labels muted 12 px bold, values fg)
Target: `remote/target`; Forge: "GitHub" / "GitLab" / "Unknown — set `git config premerge.forge`"; when `webUrl`,
a link "Open repository ↗" (opens with `QDesktopServices`); Base: `base @ mergeBase`; Head: `head`; Commits, Files,
Changes "+A −D"; Comments "N open, M resolved"; a muted hint at the bottom: "When you're ready: Create PR… (toolbar)
or `premerge pr`".

## Tests (offscreen, fixture)
- Card shows the template body (contains "Summary") and "prefilled from template .github/pull_request_template.md".
- Edit → change title and body → Save → store has them, card shows "description draft", PR header title updates.
- While in edit mode, `Store(...).set_description("X", "Y")` from outside → warn bar appears; "Load it" puts "Y" in
  the editor.
- General composer submit → a general comment exists and a thread is shown.
- Summary row click emits `openComment` with the right path/id.

## Acceptance
Tests pass. Shots `overview` (with one general comment thread + agent reply and two review comments) and
`overview-edit` (edit mode, Preview selected). Look at both and fix anything that looks off before reporting.
