"""The premerge command line."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from premerge.core import prompt, publish
from premerge.core.gitrepo import GitError, Repo
from premerge.core.store import Store, StoreError


class CliError(Exception):
    """A user-facing failure that is not a git or store error."""


def cmd_comments(repo: Repo, args) -> int:
    data = Store(repo).load()
    if args.json:
        cs = [c for c in data["comments"] if args.all or c["status"] == "open"]
        for c in cs:
            if c["kind"] == "line":
                c["current"] = dict(zip(("state", "line"), prompt.locate(repo, c)))
        print(json.dumps(cs, indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(prompt.render_prompt(repo, data, args.all))
    return 0


def read_text_arg(v: str) -> str:
    return sys.stdin.read() if v == "-" else v


def cmd_reply(repo: Repo, args) -> int:
    text = read_text_arg(args.text) if args.text is not None else ""
    if not text.strip() and not args.resolve:
        raise CliError("reply text required (use - to read stdin)")
    c = Store(repo).reply(args.id, args.author, text, args.resolve)
    print(f"{c['id']}: {'resolved' if c['status'] == 'resolved' else 'replied'}")
    return 0


def cmd_status(repo: Repo, args, status: str) -> int:
    c = Store(repo).set_status(args.id, status)
    print(f"{c['id']}: {status}")
    return 0


def cmd_describe(repo: Repo, args) -> int:
    store = Store(repo)
    if args.reset:
        store.set_description(None, None)
    elif args.title is not None or args.body is not None or args.body_file is not None:
        body = args.body
        if args.body_file is not None:
            body = sys.stdin.read() if args.body_file == "-" else Path(args.body_file).read_text()
        with store.edit() as d:
            cur = store.description(d)
            d["title"] = args.title if args.title is not None else cur["title"]
            d["body"] = body if body is not None else cur["body"]
    desc = store.description()
    if args.json:
        print(json.dumps(desc, indent=2, ensure_ascii=False))
    else:
        print(f"# {desc['title']}\n\n{desc['body'].rstrip()}")
        if not desc["saved"]:
            print(f"<!-- not saved yet: prefilled from {desc['source']} -->", file=sys.stderr)
    return 0


def cmd_pr(repo: Repo, args) -> int:
    p = publish.plan(repo, Store(repo), draft=args.draft, push=not args.no_push)
    print(f"Title: {p.title}")
    print(f"Description: {len(p.body)} chars ({p.source})")
    if p.open_comments:
        print(f"warning: {p.open_comments} review comment(s) still open")
    for problem in p.problems:
        print(f"problem: {problem}")
    for line in p.display:
        print(f"  $ {line}")
    if p.problems:
        return 1
    if not args.yes and input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
        raise CliError("aborted")
    code, output = publish.execute(p, repo.root)
    print(output, end="" if output.endswith("\n") else "\n")
    return code


def cmd_gui(args) -> int:
    from premerge.ui.app import run_gui

    return run_gui(args)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="premerge", description="Local pull/merge request preview and review.")
    ap.add_argument("-C", dest="repo", default=".", help="run as if started in this directory")
    ap.add_argument("--base", help="base ref (default: git config premerge.base, <remote>/HEAD, then main/master)")
    ap.add_argument("--remote", help="remote to target (default: upstream's remote, else origin)")
    ap.add_argument("--forge", choices=["github", "gitlab"], help="override forge detection")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("gui", help="open the review app (default)")

    sc = sub.add_parser("comments", help="print review comments as an agent prompt")
    sc.add_argument("--all", action="store_true", help="include resolved comments")
    sc.add_argument("--json", action="store_true")

    sr = sub.add_parser("reply", help="reply to a comment")
    sr.add_argument("id")
    sr.add_argument("text", nargs="?", help="reply text, or - for stdin")
    sr.add_argument("--resolve", action="store_true", help="also mark the comment resolved")
    sr.add_argument("--as", dest="author", choices=["agent", "you"], default="agent")

    for name in ("resolve", "reopen"):
        x = sub.add_parser(name, help=f"{name} a comment")
        x.add_argument("id")

    sd = sub.add_parser("describe", help="read or update the PR title/description draft")
    sd.add_argument("--title")
    sd.add_argument("--body")
    sd.add_argument("--body-file", help="file with the description, or - for stdin")
    sd.add_argument("--reset", action="store_true", help="discard the draft (back to template/commits)")
    sd.add_argument("--json", action="store_true")

    spr = sub.add_parser("pr", help="push and create the PR/MR from the draft")
    spr.add_argument("--draft", action="store_true")
    spr.add_argument("--no-push", action="store_true")
    spr.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        repo = Repo(args.repo, args.base, args.remote, args.forge)
        match args.cmd:
            case None | "gui":
                return cmd_gui(args)
            case "comments":
                return cmd_comments(repo, args)
            case "reply":
                return cmd_reply(repo, args)
            case "resolve" | "reopen":
                return cmd_status(repo, args, "resolved" if args.cmd == "resolve" else "open")
            case "describe":
                return cmd_describe(repo, args)
            case "pr":
                return cmd_pr(repo, args)
    except (GitError, StoreError, CliError) as e:
        print(f"premerge: {e}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print(file=sys.stderr)
        return 1
    return 0
