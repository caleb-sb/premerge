# Orchestrating the premerge build

You coordinate the implementation of premerge: you dispatch each task to a **Sonnet subagent, one at a time**,
verify its work against the spec, fix deviations, and commit. You don't have the context of the session that wrote
this spec — everything you need is in `docs/spec/`.

## Files
- `docs/spec/00-overview.md` — shared spec (architecture, data shapes, contracts, colours). Read it fully first.
- `docs/spec/tasks/T01…T12-*.md` — one self-contained task each, in order. Read each before dispatching it.
- `docs/spec/PROGRESS.md` — you create and maintain it: one section per task with status, commit sha, deviations
  accepted, fixes you made, open issues. Update it after every task so work can resume after a context reset.
- `legacy/evie_core.py` — the tested prototype T01 ports (T01 deletes it).

## Ground rules from the user
- Run subagents **sequentially, never in parallel**. Use the Agent tool with `model: "sonnet"` and
  `subagent_type: "general-purpose"`. One subagent per task; if a task fails badly, you may dispatch a follow-up
  subagent for the same task with a focused fix list.
- **Installs:** the user has approved creating `./.venv` and installing exactly `PySide6` and `Pygments` (plus
  upgrading pip) into it. Ask the user before installing anything else, or a different Python. If PySide6 can't
  be installed for the system Python (only 3.15 is present on this machine), stop and ask the user.
- Never push, open PRs/MRs, or touch remotes. Never run `premerge pr` against a real remote.
- Commits: the directory is not a git repo yet. Before T01, run `git init -b main` and commit the spec
  ("Add premerge spec"). After each verified task commit locally with message `T0N: <task title>`. Don't push.
- Each subagent has a limited context (keep it under ~80k tokens): the dispatch prompt must stay short and point at
  files rather than paste them.

## Dispatch prompt template
```
You are implementing one task of the premerge project in /home/caleb/dev/premerge.
Read docs/spec/00-overview.md, then docs/spec/tasks/<TASK FILE>. Implement exactly that task, following §9 of the
overview ("Rules for implementing a task"). Read only the files the task lists; read just signatures/docstrings
where the task says "public API". Don't install anything (the venv already has PySide6 and Pygments — T01 is the
only task that creates it). Don't commit. Use .venv/bin/python for everything; GUI tests run with
QT_QPA_PLATFORM=offscreen.
<if this is a follow-up: "A previous attempt left these problems; fix them: …">
Finish with the report described in §9 (files changed, decisions/deviations, real acceptance output, anything left
undone).
```

## Verifying each task (do all of this yourself before committing)
1. Read the subagent's report, then `git status` / `git diff --stat` to see what actually changed. Flag files
   touched outside the task's list.
2. Re-run the task's acceptance commands yourself; don't trust the pasted output.
3. Check the §6 contracts the task owns: names, signatures, return shapes (read the code, at least the public parts).
   Later tasks depend on them; a renamed method breaks the next subagent.
4. Check the overview's global rules: no Qt in `premerge/core`, no colours outside `ui/theme.py`, no extra
   dependencies, `ui.jobs` for git work in the UI, Ctrl shortcuts.
5. For UI tasks, run `QT_QPA_PLATFORM=offscreen .venv/bin/python tools/shot.py shots` and **look at the PNGs** with
   the Read tool. Compare with overview §5 (Tokyo Night Night colours, layout). Ugly or broken rendering is a
   deviation.
6. Fix small deviations yourself. For larger ones, dispatch a follow-up Sonnet subagent for that task with a
   precise list. Record everything in PROGRESS.md, then commit.
7. If the spec itself turns out wrong or contradictory, choose the fix that best serves the goal (a native
   PR/MR preview with an agent comment loop), update the spec file so later tasks see the change, and note it in
   PROGRESS.md.

## Finish
After T12: run the full test suite and all shots once more, then report to the user: what was built, how to run it
(`.venv/bin/premerge` in a repo; optional symlink to `~/.local/bin`; installing the skill with
`ln -s "$PWD/skills/premerge-review" ~/.claude/skills/premerge-review` — ask the user before creating either link),
the deviations from the spec, known issues, and what couldn't be checked here (macOS behaviour).
