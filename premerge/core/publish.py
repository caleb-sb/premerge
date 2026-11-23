"""Planning and running `git push` + `gh pr create` / `glab mr create` from the review draft."""
from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable

from premerge.core.gitrepo import Repo
from premerge.core.store import Store


@dataclass
class PrPlan:
    """Everything needed to show and run a PR/MR creation."""

    forge: str | None
    tool: str | None
    branch: str
    target: str
    remote: str | None
    title: str
    body: str
    open_comments: int
    push_cmd: list[str] | None
    create_cmd: list[str]
    stdin: str | None
    display: list[str]
    problems: list[str] = field(default_factory=list)
    source: str = ""


def plan(repo: Repo, store: Store, draft: bool = False, push: bool = True) -> PrPlan:
    """Build the PR plan; user-fixable problems are listed in `problems`, not raised."""
    data = store.load()
    desc = store.description(data)
    branch, target, remote = repo.branch(), repo.target_branch, repo.remote
    forge = repo.remote_info()["forge"]
    problems: list[str] = []
    if not remote:
        problems.append("no git remote configured")
    tool = {"github": "gh", "gitlab": "glab"}.get(forge)
    if forge not in ("github", "gitlab"):
        problems.append("can't tell if the remote is GitHub or GitLab; pass --forge or "
                        "`git config premerge.forge gitlab`")
    elif not shutil.which(tool):
        problems.append(f"`{tool}` is not installed — it's needed to create the "
                        f"{'PR' if tool == 'gh' else 'MR'}")
    if tool == "glab":
        create = ["glab", "mr", "create", "--source-branch", branch, "--target-branch", target,
                  "--title", desc["title"], "--description", desc["body"], "--yes"]
    else:
        create = ["gh", "pr", "create", "--base", target, "--head", branch,
                  "--title", desc["title"], "--body-file", "-"]
    if draft:
        create.append("--draft")
    push_cmd = ["git", "push", "-u", remote, branch] if push and remote else None
    shown = ["<description>" if tool == "glab" and i > 0 and create[i - 1] == "--description" else x
             for i, x in enumerate(create)]
    display = ([shlex.join(push_cmd)] if push_cmd else []) + [shlex.join(shown)]
    return PrPlan(forge, tool, branch, target, remote, desc["title"], desc["body"],
                  sum(c["status"] == "open" for c in data["comments"]), push_cmd, create,
                  desc["body"] if tool == "gh" else None, display, problems, desc["source"])


def execute(plan: PrPlan, cwd: str, on_output: Callable[[str], None] | None = None) -> tuple[int, str]:
    """Run push then create; stop at the first failure. Returns (returncode, combined output)."""
    outputs: list[str] = []
    steps = ([(plan.push_cmd, None)] if plan.push_cmd else []) + [(plan.create_cmd, plan.stdin)]
    for (cmd, stdin), shown in zip(steps, plan.display):
        p = subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, text=True)
        text = f"$ {shown}\n{p.stdout}{p.stderr}"
        outputs.append(text)
        if on_output:
            on_output(text)
        if p.returncode != 0:
            return p.returncode, "".join(outputs)
    return 0, "".join(outputs)
