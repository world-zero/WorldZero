#!/usr/bin/env python3
"""Fail when a comment, docstring or doc names a repo path that doesn't exist (#4101).

Usage: check_comment_paths.py [--write-allowlist]
Known violations live in scripts/comment_paths_allowlist.txt as `file:token` lines.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = Path(__file__).with_name("comment_paths_allowlist.txt")
SCAN = ("backend/", "frontend/src/", "scripts/", "docs/")
TOKEN = re.compile(
    r"(?<![\w/.:@-])(?:backend|frontend|scripts|docs|deploy|e2e)/[\w./@-]*\.[A-Za-z]\w*"
)
# ponytail: `//` and `/*` match naively, even inside strings; a false hit is
# allowlistable, and URLs are skipped by the token lookbehind.
BLOCK = re.compile(r"/\*.*?\*/", re.S)
LINE = re.compile(r"(?<![:\w])//.*")


def py_comment_lines(text):
    out = {}
    for i, line in enumerate(text.splitlines(), 1):
        if "#" in line:
            out[i] = line[line.index("#"):]
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        d = node.body[0] if node.body else None
        if isinstance(d, ast.Expr) and isinstance(d.value, ast.Constant) and isinstance(d.value.value, str):
            for n, s in enumerate(d.value.value.splitlines()):
                out[d.value.lineno + n] = out.get(d.value.lineno + n, "") + s
    return out


def c_comment_lines(text):
    out = {}
    for m in BLOCK.finditer(text):
        start = text.count("\n", 0, m.start()) + 1
        for n, s in enumerate(m.group().splitlines()):
            out[start + n] = s
    blanked = BLOCK.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), text)
    for i, line in enumerate(blanked.splitlines(), 1):
        m = LINE.search(line)
        if m:
            out[i] = out.get(i, "") + m.group()
    return out


def comment_lines(rel, text):
    if rel.endswith(".py"):
        return py_comment_lines(text)
    if rel.endswith((".ts", ".tsx", ".css")):
        return c_comment_lines(text)
    if rel.endswith(".md"):
        return dict(enumerate(text.splitlines(), 1))
    return {}


def exists(token, root):
    return (root / token).exists() or (
        token.startswith("e2e/") and (root / "frontend" / token).exists()
    )


def find(root):
    files = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    for rel in files:
        if not rel.startswith(SCAN):
            continue
        try:
            text = (root / rel).read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for ln, s in sorted(comment_lines(rel, text).items()):
            for m in TOKEN.finditer(s):
                tok = m.group()
                if s[m.end():m.end() + 1] and s[m.end()] in "*<{":
                    continue
                if not exists(tok, root):
                    yield rel, ln, tok


def main(root=ROOT, allowlist=ALLOWLIST, argv=()):
    bad = list(find(root))
    if "--write-allowlist" in argv:
        allowlist.write_text("".join(sorted({f"{f}:{t}\n" for f, _, t in bad})))
        return 0
    allowed = set(allowlist.read_text().split()) if allowlist.exists() else set()
    new = [(f, ln, t) for f, ln, t in bad if f"{f}:{t}" not in allowed]
    for f, ln, t in new:
        print(f"{f}:{ln}: names {t}, which does not exist", file=sys.stderr)
    if new:
        print(
            "check_comment_paths: fix the path, or add `file:path` to "
            "scripts/comment_paths_allowlist.txt",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(argv=sys.argv[1:]))
