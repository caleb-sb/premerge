# T02 — Fixture repo and core tests

## Goal
A reusable fixture repository and a `unittest` suite that pins down the core behaviour. Fix core bugs the tests
reveal (keep the §6 contracts).

## Read
- `docs/spec/00-overview.md`
- `premerge/core/gitrepo.py`, `store.py`, `anchors.py`, `prompt.py`, `publish.py`, `premerge/cli.py`
  (read signatures first; read bodies only where a test fails)

## Create
- `tests/__init__.py` (empty), `tests/fixture.py`, `tests/test_gitrepo.py`, `tests/test_store.py`,
  `tests/test_anchors.py`, `tests/test_prompt.py`, `tests/test_cli.py`, `tests/test_publish.py`
- Modify core files only to fix bugs.

## fixture.py
`make_fixture(root: Path) -> Path` — all git commands with `-c user.name=Tester -c user.email=t@example.com`
(or repo-local config) and `GIT_CONFIG_GLOBAL=/dev/null`-style isolation so the user's git config can't interfere
(set env `GIT_CONFIG_GLOBAL` to an empty temp file and `GIT_CONFIG_NOSYSTEM=1` in a helper `git(cwd, *args)`).
1. `root/origin.git` bare; `root/work` with `git init -b main`.
2. On main, commit: `keep.txt` (`a\nb\nc\n`), `gone.txt` (`x\n`), `move_me.txt` (`1..30`, one number per line),
   `eol.txt` (`no eol`, no trailing newline), `app.py` (40 lines of plausible Python: imports, a class with three
   methods, a `main()`), `.github/pull_request_template.md` (`## Summary\n\n## Testing\n`). Push, `remote set-head origin main`.
3. Branch `feat/thing`: `keep.txt` → `a\nB\nc\nd\n`; delete `gone.txt`; `git mv move_me.txt moved.txt`; add
   `with space.txt` (`new\n`); `eol.txt` → `no eol2` (no newline); add `bin.dat` (bytes `\x00\x01\x02`); edit
   `app.py` near the top (add an import) and near the bottom (change `main()`), so it has **two hunks**. Commit
   "Change things". Then a second commit "Tweak app" changing one more line in `app.py`.
4. Back on main: add `main_only.txt`, commit, push; switch back to `feat/thing` (so `origin/main` is ahead).
5. Working tree: untracked `u.txt` (`untracked\n`); append `wt\n` to `keep.txt` (uncommitted).
Return `root/work`. Also export `FIXTURE_FILES_COMMITTED` = the set of paths expected in committed mode.

## Tests (use `tempfile.TemporaryDirectory`; build the fixture once per class in `setUpClass`)
- gitrepo: base `origin/main`, target `main`, remote `origin`; committed mode lists exactly the expected paths with
  statuses (bin.dat added+binary, eol.txt modified with `noeol` on both lines, gone.txt deleted, moved.txt renamed
  from move_me.txt with no hunks, `with space.txt` added, app.py 2+ hunks); `main_only.txt` never appears;
  worktree mode adds `u.txt` and keep.txt's hash differs from committed mode while other hashes are equal;
  `file_full` for app.py returns one hunk containing every line; line numbers `o`/`n` are consistent (walk a hunk:
  context increments both); `commits()` returns 2 newest-first; `meta()` has ahead 2, behind 1;
  `default_description("github")` uses the template and a branch-derived title ("Thing"); `parse_patch` unit cases:
  quoted path with `\t`, `\ No newline at end of file`, a deleted line starting with `-- ` inside a hunk
  (`--- foo` content must not be read as a header), mode-only change (`old mode`/`new mode`, no hunks).
- store: add line/file/general comments; validation errors raise `StoreError` (empty body, bad side, bad kind);
  `find` by unique prefix and ambiguous prefix; reply by `you` reopens a resolved comment, reply by `agent` doesn't;
  `set_viewed`; `set_description` + reset; two `Store` objects on the same repo don't lose each other's writes
  (interleave edits); branch switch uses a different file; JSON file lives under `.git/premerge/`.
- anchors: ok / moved (line shifted by inserted lines) / missing; blank anchor text never "moves"; side old.
- prompt: render with 0 comments, with each kind; resolved hidden unless `include_all`; context fenced with ```` when
  it contains ```; `locate` reports moved after inserting lines above in the working tree, outdated after deleting.
- cli (subprocess `[sys.executable, "-m", "premerge", "-C", work, ...]`): `comments`, `comments --json`,
  `reply ID --resolve TEXT`, `reply ID -` with stdin, `resolve`, `reopen`, `describe --title T --body-file -`,
  `describe --reset`, unknown id → exit 1 and `premerge:` on stderr, not-a-repo dir → exit 1.
- publish: `plan()` on the fixture (remote is a local path → forge None) has a problem; with `forge="github"` and
  a PATH lacking `gh` (monkeypatch `shutil.which`) lists "gh is not installed"; with a fake `gh` script on PATH
  (writes its argv and stdin to a file) `execute` with `push=False` passes `--title`, `--base main`, `--head feat/thing`
  and the body on stdin; `--draft` appended when draft=True.

## Acceptance
`.venv/bin/python -m unittest discover -s tests -v` — all pass, total runtime < 60 s. Paste the summary.
