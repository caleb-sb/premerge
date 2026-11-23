Implement premerge, a native PySide6 desktop app (Linux + Apple Silicon macOS) that previews the current git branch as a GitHub PR / GitLab MR against remote main, with a file tree, inline review comments that a coding agent works through via a CLI, and a PR description draft.

The full spec is in /home/caleb/dev/premerge/docs/spec/. You are the orchestrator: read docs/spec/ORCHESTRATOR.md first and follow it exactly, then docs/spec/00-overview.md.

In short:
- Do tasks T01–T12 in order, each by a single Sonnet subagent (Agent tool, model "sonnet"), strictly one at a time, never in parallel. Subagents don't have your context; use the dispatch template in ORCHESTRATOR.md and keep each subagent's context under ~80k tokens.
- After each task, verify it yourself against the spec (rerun acceptance checks, check contracts, look at the screenshots for UI tasks), fix deviations or dispatch a focused follow-up, log it in docs/spec/PROGRESS.md, and commit locally ("T0N: …"). Run `git init -b main` and commit the spec before T01.
- Approved installs: a ./.venv with PySide6 and Pygments (and a pip upgrade) only. Ask me before anything else, including a different Python if PySide6 won't install for Python 3.15.
- Never push or create real PRs/MRs. Ask before symlinking anything into ~/.local/bin or ~/.claude/skills.
- When done, report what was built, how to run it, deviations from the spec, known issues, and what couldn't be verified (macOS).
