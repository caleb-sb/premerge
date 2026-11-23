# T12 — README, agent skill, end-to-end QA

## Goal
Document the tool, ship the Claude Code skill for the agent side, and run a full end-to-end check of the agent loop.

## Read
- `docs/spec/00-overview.md`
- `premerge/cli.py` (argparse definitions), `premerge/core/prompt.py` (`render_prompt` instructions text),
  `premerge/ui/window.py` (menus/shortcuts), `premerge/ui/filepage.py` (shortcut definitions only)

## Create / modify
`README.md`, `skills/premerge-review/SKILL.md`, `tests/test_e2e.py`; small fixes anywhere if QA finds bugs (list each
fix in the report).

## README.md
Sections: what it is (1 paragraph); Install (Linux and macOS: `python3 -m venv .venv && .venv/bin/pip install -e .`,
then symlink `.venv/bin/premerge` into `~/.local/bin`; mention `pipx install -e .` as an alternative; Python ≥ 3.11;
`gh` for GitHub and `glab` for GitLab only needed for creating PRs/MRs); Use (run `premerge` in a repo; the base
branch rules; Committed vs Working tree; Viewed; comments; description drafts; PR templates); The agent loop (the
commands, the skill, where state is stored, that it's never committed); Keyboard shortcuts (table generated from
the actual shortcuts in the code); CLI reference (from argparse); Configuration (`premerge.base`, `premerge.forge`);
Development (tests, `tools/shot.py`).

## skills/premerge-review/SKILL.md
Claude Code skill (YAML front matter `name: premerge-review`, `description:` "Address the local review comments the
user left in premerge (local PR preview) for the current git branch. Use when the user asks to address/handle/fix
their premerge or review comments, or says /premerge-review."). Body: steps — run `premerge comments` (if not on
PATH, `python -m premerge comments` from the premerge venv); if none, say so and stop; for each comment read the
code around the given location, make the smallest change that addresses it, keep to the comment's scope; then
`premerge reply <id> --resolve "<one-line summary of the change>"`; if you disagree or need a decision,
`premerge reply <id> "<question>"` without `--resolve`; general comments about the description → edit with
`premerge describe --title … --body-file -`; never commit, push or run `premerge pr` unless asked; finish with a
short summary list (id → what changed). README explains installing it with
`ln -s "$PWD/skills/premerge-review" ~/.claude/skills/premerge-review`.

## tests/test_e2e.py
Offscreen, fixture: open `MainWindow`, start the session; add a line comment through the Files page API on
`keep.txt` line 2; run `python -m premerge -C work comments` as a subprocess and assert the id and a ```diff block
appear; edit `keep.txt` in the working tree as an agent would, run `premerge reply ID --resolve "Fixed"`; within
5 s the thread in the Files page shows the agent reply and is collapsed as resolved, the toolbar count drops to 0,
and in worktree mode the diff shows the edit.

## QA checklist (do each; report pass/fail and fixes)
1. Full test suite passes; `tools/shot.py shots` produces every registered shot without warnings on stderr. Look at
   every image.
2. `grep -rn "PySide6\|from premerge.ui" premerge/core` is empty.
3. No hard-coded colours outside `ui/theme.py` (`grep -rnE "#[0-9a-fA-F]{6}" premerge | grep -v theme.py`).
4. Every shortcut listed in README exists in code and vice versa.
5. `premerge --help` and each subcommand's `--help` read well.
6. macOS readiness review (can't run it here): no Linux-only calls outside `sys.platform` guards, shortcuts use Ctrl
   (→ ⌘), QSettings via org/app names, no hard-coded paths; note anything risky in the report.

## Acceptance
All tests pass; README and SKILL.md exist; QA checklist reported item by item.
