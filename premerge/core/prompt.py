"""The Markdown prompt that hands open review comments to a coding agent."""
from __future__ import annotations

import shlex
import shutil
import sys
from pathlib import Path

from premerge.core import anchors
from premerge.core.gitrepo import GitError, Repo


def cli_cmd() -> str:
    """How the agent should invoke premerge: `premerge` if on PATH and this install, else an absolute command."""
    found = shutil.which("premerge")
    if found:
        mine = {Path(sys.argv[0]).resolve(), Path(sys.executable).parent.joinpath("premerge").resolve()}
        if Path(found).resolve() in mine:
            return "premerge"
    return f"{shlex.quote(sys.executable)} -m premerge"


def locate(repo: Repo, c: dict) -> tuple[str, int | None]:
    """Where a line comment's anchor is now: ('ok'|'moved'|'outdated', line)."""
    try:
        if c["side"] == "new":
            text = Path(repo.root, c["path"]).read_text(errors="replace")
        else:
            text = repo.git("show", f"{repo.merge_base()}:{c.get('oldPath') or c['path']}")
    except (OSError, GitError):
        return "outdated", None
    ln, state = anchors.locate_in_text(text.split("\n"), c)
    return ("outdated", None) if state == "missing" else (state, ln)


def fence(lines: list[str], lang: str = "") -> list[str]:
    """A Markdown code fence around `lines`, long enough not to be closed by their content."""
    tick = "````" if any("```" in s for s in lines) else "```"
    return [tick + lang, *lines, tick]


def quote(who: str, body: str) -> str:
    """A blockquote attributed to `who`."""
    return f"**{who}:**\n" + "\n".join("> " + s if s else ">" for s in body.split("\n"))


def render_prompt(repo: Repo, data: dict, include_all: bool = False) -> str:
    """Markdown listing the review comments for the agent."""
    cmd = cli_cmd()
    cs = [c for c in data["comments"] if include_all or c["status"] == "open"]
    out = [f"# Local review of `{data['branch']}` → `{repo.target_branch}`", ""]
    if not cs:
        out.append("No open review comments.")
        return "\n".join(out) + "\n"
    out += [
        f"Repository: `{repo.root}`",
        "",
        f"The reviewer left {len(cs)} comment(s) on this branch's diff against `{repo.base}` "
        "(the diff a pull request would show). For each one, make the requested change in the working "
        "tree — or, if no change is warranted, explain why. Then record the outcome:",
        "",
        f"    {cmd} reply <id> --resolve \"what you changed\"   # addressed",
        f"    {cmd} reply <id> \"question or pushback\"         # needs the reviewer",
        "",
        "Line numbers refer to the current working tree. The PR title/description draft can be read with "
        f"`{cmd} describe` and updated with `{cmd} describe --title \"…\" --body-file FILE`. "
        "Do not commit unless asked.",
        "",
        "---",
    ]
    for i, c in enumerate(cs, 1):
        out.append("")
        if c["kind"] == "line":
            st, ln = locate(repo, c)
            rng = f"{c['startLine']}–{c['line']}" if c.get("startLine") and c["startLine"] != c["line"] else str(c["line"])
            where = f"line {rng}" if c["side"] == "new" else f"removed line {rng} (base version)"
            out.append(f"## {i}. `{c['path']}` {where} · id `{c['id']}`")
            if c["side"] == "new" and st == "moved":
                out.append(f"_The code has moved since this comment; the anchor line is now line {ln}._")
            elif c["side"] == "new" and st == "outdated":
                out.append("_Outdated: the commented line no longer exists in the working tree — it may already be addressed._")
            if c.get("context"):
                out += fence(c["context"], "diff")
        elif c["kind"] == "file":
            out.append(f"## {i}. `{c['path']}` (whole file) · id `{c['id']}`")
        else:
            out.append(f"## {i}. General comment · id `{c['id']}`")
        if c["status"] != "open":
            out.append(f"_status: {c['status']}_")
        out += ["", quote("Reviewer", c["body"])]
        for r in c.get("replies", []):
            out += ["", quote("Agent" if r["author"] == "agent" else "Reviewer", r["body"])]
    return "\n".join(out) + "\n"
