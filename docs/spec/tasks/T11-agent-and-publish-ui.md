# T11 — Agent prompt, Create PR dialog, Open repository, polish

## Goal
Finish the toolbar actions and the remaining window features.

## Read
- `docs/spec/00-overview.md`
- `premerge/core/publish.py` (PrPlan, plan, execute), public API of `premerge/ui/session.py`, `premerge/ui/window.py`
  (whole file), `premerge/ui/jobs.py`, `tools/shot.py` (decorator usage), `tests/qt.py`

## Create / modify
`premerge/ui/prdialog.py`, `tests/test_prdialog.py`; modify `premerge/ui/window.py`, `premerge/ui/app.py` (only if
needed for Open Repository), `tools/shot.py`.

## Agent prompt button
- Text "Agent prompt · N" (N open comments; just "Agent prompt" when 0), tooltip "Copy the open review comments as
  a prompt for your coding agent". Click → copy `session.prompt_text()` to `QGuiApplication.clipboard()` and show a
  status message "Copied N comment(s) — paste into your agent, or run `premerge comments` there".
- A small dropdown arrow (`QToolButton.MenuButtonPopup`) with: "Copy prompt including resolved", "Show prompt…"
  (a dialog with a read-only monospace `QPlainTextEdit` of the prompt and a Copy button), and
  "Copy agent instructions" — copies a one-paragraph instruction: "Run `<cli_cmd> comments` in <root>, address each
  comment, then reply with `<cli_cmd> reply <id> --resolve "…"`." (use `core.prompt.cli_cmd()`).

## `class CreatePrDialog(QDialog)` — `CreatePrDialog(session, parent=None)`
- Title "Create pull request" / "Create merge request" by forge. Computes `publish.plan(repo, store, draft, push)`
  in a job (show "Checking…" first).
- Shows: title (bold), "into **target** from **branch** on **remote**", description source + length, a warn row if
  `open_comments` ("N review comments are still open"), every `problem` in a bad-coloured list, and the commands
  (`plan.display`) in a mono read-only box. Checkboxes "Draft" and "Push branch first" (default on) — changing them
  re-plans.
- Buttons: Cancel; "Create" (default) — disabled when there are problems. Create → `publish.execute` in a job; the
  dialog switches to a log view (mono, read-only) and a spinner label "Creating…"; the output is appended via
  `on_output` (marshal to the GUI thread — `on_output` runs in the worker; use a signal). On success, find the first
  `https://…` URL in the output and show "Created: <url>" with "Open" (QDesktopServices) and "Copy link"; on failure
  show "Failed (exit N)" in bad and keep the log. Close button after completion.
- This action pushes and publishes to a remote: never run it without the user clicking Create.

## Window polish
- "Create PR…" toolbar button enabled; label "Create MR…" when forge is gitlab. Ctrl+Shift+Enter opens the dialog.
- File → Open Repository… (Ctrl+O): directory dialog → build a new `Repo`; on success replace the session (stop the
  old one, `deleteLater` the old pages) — simplest correct approach: close this window and open a new `MainWindow`
  for the new session (keep a module-level list of windows so it isn't garbage-collected); on GitError show it.
  Also File → Open Recent (last 8 repo roots in QSettings).
- Window title "<title> — <repo> — premerge".
- When the session's branch changes (user did `git switch` in a terminal), show a status message "Switched to
  <branch>" (the session already reloads everything).
- macOS: menu roles — Quit uses `QAction.MenuRole.QuitRole`; About (Help menu, "About premerge", version from
  `importlib.metadata`) uses `AboutRole`.

## Tests
- Prompt button copies text containing "Local review of" (offscreen clipboard works within the process).
- `CreatePrDialog` on the fixture (forge None) shows a problem and Create is disabled.
- With `Repo(..., forge="github")` and a fake `gh` executable earlier on PATH (writes argv to a file, prints
  `https://github.com/o/r/pull/1`), with push unchecked: clicking Create runs it and the dialog shows the URL.

## Acceptance
Tests pass. Shots: `prdialog` (fixture with forge forced to github and the fake gh missing → problem shown) and
`prompt-dialog`. Look at them and describe.
