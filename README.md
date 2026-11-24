# premerge

premerge is a desktop app (Python + PySide6) that previews the current git branch as if a pull request (GitHub) or
merge request (GitLab) had been opened against the remote main branch. You review the diff in a file tree and diff
view, leave inline comments, and draft the PR title and description. A coding agent such as Claude Code reads your
comments through a small CLI, fixes the code and replies, and you see the answer in the app within a couple of
seconds. When you are happy, `premerge pr` creates the real PR/MR. It runs on Linux and on Apple Silicon macOS.

## Install

Requires Python 3.11 or newer. `gh` (GitHub) and `glab` (GitLab) are only needed to create PRs/MRs.

```sh
git clone <this repository> premerge && cd premerge
python3 -m venv .venv && .venv/bin/pip install -e .
mkdir -p ~/.local/bin && ln -s "$PWD/.venv/bin/premerge" ~/.local/bin/premerge
```

Make sure `~/.local/bin` is on your `PATH`. As an alternative to the venv and symlink: `pipx install -e .`.

## Use

Run `premerge` inside a repository (or `premerge -C path/to/repo`). The window shows what a PR from the current
branch would contain: the diff from the merge base of the base branch and `HEAD`, so commits that exist only on main
are never shown.

- **Base branch.** The first of: `--base`, `git config premerge.base`, the remote's `HEAD` (`refs/remotes/<remote>/HEAD`),
  `<remote>/main`, `<remote>/master`, `main`, `master`. The remote is `--remote`, the branch's upstream remote,
  `origin`, or the first remote.
- **Committed / Working tree.** Committed shows `HEAD` (what a PR would contain today). Working tree also includes
  uncommitted changes and untracked files (up to 200).
- **Unified / Split** diff layouts, and a full-file toggle per file.
- **Viewed.** Tick a file as viewed; if it changes afterwards it is flagged "Changed since viewed".
- **Comments.** Select lines in the diff (click or drag the gutter) to comment on a line or a range, comment on a whole
  file, or add general comments on the Overview tab. Reply, resolve and reopen threads; resolved threads collapse.
  Comments whose line moved are re-anchored; ones that no longer match are shown as outdated.
- **Description.** Edit the PR title and description on the Overview tab. Until you save a draft, it is prefilled from
  the PR/MR template (`.github/pull_request_template.md`, `.gitlab/merge_request_templates/Default.md`, ...) if there is
  one, else from the commit messages.
- **Create PR.** File → Create Pull Request… (Ctrl+Shift+Enter) or `premerge pr` shows the plan (push, `gh pr create` / `glab mr create`) and only
  runs it when you confirm.

## The agent loop

1. You comment in the app.
2. The agent runs `premerge comments` and gets a Markdown prompt with each open comment, its location and diff context.
3. It changes the code and runs `premerge reply <id> --resolve "what changed"` (or replies without `--resolve` to ask
   a question).
4. The app notices within about 2 seconds and shows the agent's reply. A reply from you re-opens a resolved thread.

The toolbar's "Agent prompt" button copies the same prompt to the clipboard for pasting into any agent.

For Claude Code, install the skill so that "address my premerge comments" (or `/premerge-review`) does all of this:

```sh
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/premerge-review" ~/.claude/skills/premerge-review
```

**Where state is stored.** Review state (comments, viewed marks, the description draft) lives in
`<git-common-dir>/premerge/<branch>.json`, inside `.git`, so it is never committed and is shared by all worktrees of the
repository. Writes are locked and atomic because the app and the CLI write it concurrently.

## Keyboard shortcuts

`Ctrl` is `Cmd` on macOS.

| Keys | Action | Where |
| --- | --- | --- |
| `Ctrl+O` | Open repository | anywhere |
| `Ctrl+Q` | Quit | anywhere |
| `Ctrl+Shift+Return` | Create pull request | anywhere |
| `F5`, `Ctrl+R` | Reload | anywhere |
| `Ctrl+1` / `Ctrl+2` / `Ctrl+3` | Overview / Commits / Files changed | anywhere |
| `Alt+Down` / `Alt+Up` | Next / previous file | anywhere |
| `J` / `K` | Next / previous file | Files tab |
| `V` | Toggle viewed on the current file | Files tab |
| `F`, `Ctrl+P` | Focus the file filter | Files tab |
| `C` | Comment on the current file | Files tab |
| `N` / `Shift+N` | Next / previous comment thread | Files tab |
| `Esc` | Leave the file filter | file filter |
| `Ctrl+Enter` | Submit the comment or reply | comment editor |
| `Esc` | Cancel the comment editor | comment editor |
| `Ctrl+S` | Save the description | description editor |
| `Esc` | Cancel editing the description | description editor |

## CLI reference

```
premerge [-C DIR] [--base REF] [--remote NAME] [--forge github|gitlab] [COMMAND]

  (no command), gui        open the review app for the repository at DIR (default .)
  comments [--all] [--json]
                           print open comments as an agent prompt (Markdown); --all includes resolved ones
  reply ID [TEXT|-] [--resolve] [--as agent|you]
                           reply to a comment (default author: agent; - reads stdin); --resolve also resolves it
  resolve ID | reopen ID   change a comment's status
  describe [--title T] [--body B | --body-file F|-] [--reset] [--json]
                           read or update the PR title/description draft; --reset discards the draft
  pr [--draft] [--no-push] [-y]
                           show the plan, ask for confirmation, push and create the PR/MR
```

IDs may be abbreviated to a unique prefix of at least 3 characters. Errors print `premerge: <message>` to stderr and
exit with status 1.

## Configuration

Set per repository with `git config`:

- `premerge.base`: the base ref, for example `origin/develop`.
- `premerge.forge`: `github` or `gitlab`, for hosts whose name does not contain either word.

The `--base`, `--remote` and `--forge` flags override these.

## Development

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests
QT_QPA_PLATFORM=offscreen .venv/bin/python tools/shot.py shots   # offscreen screenshots for visual review
```

`premerge/core` (git, store, anchors, prompt, publish) never imports Qt, so the CLI works without a display.
