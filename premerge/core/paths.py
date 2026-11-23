"""Pure path helpers for the file tree."""


def _key(name: str) -> tuple[str, str]:
    return (name.casefold(), name)


def _split(paths: list[str]) -> dict:
    root: dict = {"name": "", "path": "", "dirs": {}, "files": []}
    for p in paths:
        *parents, _ = p.split("/")
        node = root
        for i, part in enumerate(parents):
            node = node["dirs"].setdefault(part, {"name": part, "path": "/".join(parents[:i + 1]),
                                                  "dirs": {}, "files": []})
        node["files"].append(p)
    return root


def _finish(node: dict, merge: bool) -> dict:
    dirs = [_finish(node["dirs"][k], True) for k in sorted(node["dirs"], key=_key)]
    files = sorted(node["files"], key=lambda p: _key(p.rsplit("/", 1)[-1]))
    out = {"name": node["name"], "path": node["path"], "dirs": dirs, "files": files}
    while merge and not out["files"] and len(out["dirs"]) == 1:
        child = out["dirs"][0]
        out = {"name": f"{out['name']}/{child['name']}", "path": child["path"],
               "dirs": child["dirs"], "files": child["files"]}
    return out


def build_tree(paths: list[str]) -> dict:
    """Nested `{name, path, dirs, files}` tree with single-child directory chains compressed."""
    return _finish(_split(paths), False)


def tree_order(paths: list[str]) -> list[str]:
    """Paths in depth-first tree order: directories before files, case-insensitive names."""
    out: list[str] = []

    def walk(node: dict) -> None:
        for d in node["dirs"]:
            walk(d)
        out.extend(node["files"])

    walk(build_tree(paths))
    return out
