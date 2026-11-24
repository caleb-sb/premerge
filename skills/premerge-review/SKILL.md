---
name: premerge-review
description: Address the local review comments the user left in premerge (local PR preview) for the current git branch. Use when the user asks to address/handle/fix their premerge or review comments, or says /premerge-review.
---

# Address premerge review comments

premerge is a local pull-request preview. The user leaves review comments in its app; you read them through the CLI,
change the code, and reply so the user sees the answer in the app within a couple of seconds.

## Steps

1. Run `premerge comments` in the repository (current branch). If `premerge` is not on PATH, run
   `python -m premerge comments` using the Python from the premerge virtualenv.
2. If there are no open comments, say so and stop.
3. For each comment:
   - Read the code around the location it gives (file, side, line range). The prompt shows the diff context and tells
     you when the line has moved or is outdated; trust the code you read over the quoted snippet.
   - Make the smallest change that addresses the comment. Keep to the comment's scope; do not refactor unrelated code.
   - Reply and resolve it with a one-line summary of what you changed:
     `premerge reply <id> --resolve "<one-line summary of the change>"`
   - If you disagree, or need a decision from the user, reply without resolving and ask the question:
     `premerge reply <id> "<question>"`
4. General comments about the PR description or title: edit the draft with
   `premerge describe --title "…" --body-file -` (body on stdin). `premerge describe` alone prints the current draft.
5. Never commit, push, or run `premerge pr` unless the user asks you to.
6. Finish with a short summary list: `id -> what changed` (or `id -> question asked`).
