# premerge build progress

Orchestrator log. One section per task: status, commit, deviations accepted, fixes, open issues.

## Setup
- `git init -b main`; spec committed as 98ee433 "Add premerge spec".
- Venv created by the orchestrator before T01 (system Python 3.15.2): `pip -U pip`, `pip install PySide6 Pygments`
  → PySide6 6.12.0 (meta-package also pulls PySide6_Essentials/Addons/Pdf/WebEngine wheels; WebEngine is never
  imported), Pygments 2.21.0. T01 therefore only runs `pip install -e .`.
- Schedule: tasks dispatched sequentially with a 45-minute wait between tasks (user request).

## T01 — Package skeleton, venv, and core port — DONE
- Commit: see `git log` ("T01: Package skeleton, venv, and core port").
- Verified by orchestrator: imports, no Qt in core, §6 core signatures, end-to-end CLI in a throwaway repo
  (describe / --title/--body / --reset / --json, comments / --json, add_comment via Store, reply with prefix id,
  reply `-` from stdin `--as you` reopens, resolve/reopen, pr problem + exit 1, unknown id and non-repo errors exit 1).
- Deviations accepted: `PrPlan` gained a trailing `source: str = ""` field (description source for the CLI plan).
- Spec bug: acceptance `grep -rn "evie"` matches the word "review"; the word-boundary grep (`grep -rniw evie`) is clean.
- Not verified: `publish.execute` (would need a real remote; never run).

## T02 — Fixture repo and core tests — DONE
- Verified: 48 tests pass (~1.5 s) on rerun; publish tests assert the fake `gh` resolves first before `execute`
  (real /usr/bin/gh is never run).
- Core fix by subagent: `premerge describe` no longer prints an extra trailing blank line.
- Deviations accepted: extra `tests/base.py` (`FixtureCase`, sets git-config isolation env for in-process calls);
  fixture's app.py ends up with 3 hunks (test asserts ≥2); empty global gitconfig is `$TMPDIR/premerge-empty-gitconfig`.
