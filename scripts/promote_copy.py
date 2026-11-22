"""Bake live copy overrides into the catalogs, so they become the default copy.

    python3 scripts/promote_copy.py            # from prod
    python3 scripts/promote_copy.py --dev      # from dev.worldzero.org

Writes each public ``GET /copy-overrides`` value into
``frontend/src/locales/en/<ns>.json`` at its dotted key; commit as a PR.

An all-asterisks override means "nothing belongs here": never written, listed as
``DELETE ns:key`` for you to remove by hand. A key not already in the catalog is
``REFUSE``d (exit non-zero); plurals bake at their ``_one``/``_other`` keys.

Keep the rows after the bake: they are the list of copy the owner wrote, and
``--guard <base-ref>`` (CI, every PR) fails a PR that changes or removes one.
Revert a row in the copy-edit page to release its key. Stdlib only.
"""

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CATALOGS = Path(__file__).resolve().parent.parent / "frontend/src/locales/en"
API = {"prod": "https://api.worldzero.org", "dev": "https://api.dev.worldzero.org"}


def _slot(data, key: str):
    """(container, index) holding a string at dotted ``key``; lists take numeric parts."""
    *parents, leaf = key.split(".")
    node = data
    for part in parents:
        node = _child(node, part)
    if isinstance(node, list) and leaf.isdigit() and int(leaf) < len(node):
        leaf = int(leaf)
    elif not isinstance(node, dict) or leaf not in node:
        return None
    return (node, leaf) if isinstance(node[leaf], str) else None


def _child(node, part: str):
    if isinstance(node, dict):
        return node.get(part)
    if isinstance(node, list) and part.isdigit() and int(part) < len(node):
        return node[int(part)]
    return None


def _is_marker(v) -> bool:
    return isinstance(v, str) and bool(v.strip()) and not v.strip().strip("*")


def promote(overrides: list[dict], catalogs: Path) -> list[str]:
    """Returns one line per changed key, then one DELETE line per marker."""
    changed, markers, files = [], [], {}
    for o in overrides:
        if _is_marker(o["value"]):
            markers.append(
                f"DELETE {o['ns']}:{o['key']} — marked as no copy; delete this key and its element"
            )
            continue
        path = catalogs / f"{o['ns']}.json"
        if not path.exists():
            changed.append(f"SKIP {o['ns']}:{o['key']} — no {path.name}")
            continue
        data = files.setdefault(path, json.loads(path.read_text()))
        slot = _slot(data, o["key"])
        if slot is None:
            changed.append(f"REFUSE {o['ns']}:{o['key']} — not a string in the catalog; nothing written")
            continue
        node, leaf = slot
        if node[leaf] != o["value"]:
            node[leaf] = o["value"]
            changed.append(f"{o['ns']}:{o['key']} = {o['value']!r}")
    for path, data in files.items():
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return changed + markers


def guard(overrides: list[dict], read_base, read_head) -> list[str]:
    """Owner-written keys this diff changes or removes. ``read_*(ns)`` -> catalog or None.

    A key absent at the base is not this diff's; a head value equal to the override
    is the bake itself.
    """
    out, cache = [], {}
    for o in overrides:
        if _is_marker(o["value"]):
            continue
        ns, key = o["ns"], o["key"]
        for side, read in (("b", read_base), ("h", read_head)):
            if (side, ns) not in cache:
                cache[side, ns] = read(ns)
        base, head = cache["b", ns], cache["h", ns]
        b = _slot(base, key) if base is not None else None
        if b is None:
            continue
        h = _slot(head, key) if head is not None else None
        was, now = b[0][b[1]], (h[0][h[1]] if h else None)
        if now == was or now == o["value"]:
            continue
        what = "removes" if now is None else "rewrites"
        out.append(f"{ns}:{key} — this PR {what} copy the owner wrote. Keep it as: {o['value']!r}")
    return out


def _fetch(env: str) -> list[dict]:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"{API[env]}/copy-overrides", timeout=20) as r:
                return json.load(r)
        except OSError as e:
            err = e
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
    sys.exit(f"Couldn't read {API[env]}/copy-overrides after 3 tries ({err}); rerun the job.")


def _git_catalog(ref: str):
    def read(ns: str):
        r = subprocess.run(
            ["git", "show", f"{ref}:frontend/src/locales/en/{ns}.json"], capture_output=True, text=True
        )
        return json.loads(r.stdout) if r.returncode == 0 else None

    return read


def _disk_catalog(ns: str):
    path = CATALOGS / f"{ns}.json"
    return json.loads(path.read_text()) if path.exists() else None


def _check() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.json"
        p.write_text('{"a": {"b": "old", "c": "same"}}')
        out = promote(
            [
                {"ns": "x", "key": "a.b", "value": "new"},
                {"ns": "x", "key": "a.c", "value": "same"},
                {"ns": "nope", "key": "k", "value": "v"},
            ],
            Path(d),
        )
        assert json.loads(p.read_text()) == {"a": {"b": "new", "c": "same"}}
        assert len(out) == 2 and out[1].startswith("SKIP"), out

        # Markers (#3114).
        p.write_text('{"a": {"b": "keep"}}')
        out = promote(
            [
                {"ns": "x", "key": "a.b", "value": " *** "},
                {"ns": "x", "key": "gone.leaf", "value": "*"},
                {"ns": "x", "key": "a.d", "value": "* five stars *"},
            ],
            Path(d),
        )
        assert json.loads(p.read_text()) == {"a": {"b": "keep"}}
        assert out == [
            "REFUSE x:a.d — not a string in the catalog; nothing written",
            "DELETE x:a.b — marked as no copy; delete this key and its element",
            "DELETE x:gone.leaf — marked as no copy; delete this key and its element",
        ], out

        # Stale unsuffixed plural refused, its real form still bakes (#3165).
        p.write_text('{"m": {"n_one": "Member", "n_other": "Members"}}')
        out = promote(
            [
                {"ns": "x", "key": "m.n", "value": "dead leaf"},
                {"ns": "x", "key": "m.n_other", "value": "Folk"},
                {"ns": "x", "key": "q.r.s", "value": "dead branch"},
            ],
            Path(d),
        )
        assert json.loads(p.read_text()) == {"m": {"n_one": "Member", "n_other": "Folk"}}
        assert out[0].startswith("REFUSE x:m.n ") and out[2].startswith("REFUSE x:q.r.s "), out

        # Array slots bake (perks, taunts); out of range refuses.
        p.write_text('{"t": ["a", "b"], "perks": [{"desc": "old"}]}')
        out = promote(
            [
                {"ns": "x", "key": "t.1", "value": "B"},
                {"ns": "x", "key": "perks.0.desc", "value": "new"},
                {"ns": "x", "key": "t.5", "value": "no"},
            ],
            Path(d),
        )
        assert json.loads(p.read_text()) == {"t": ["a", "B"], "perks": [{"desc": "new"}]}, out
        assert out[2].startswith("REFUSE x:t.5 "), out

        # Guard: rewrite and removal of owner copy fail; untouched, bake, new key and marker pass.
        ov = [
            {"ns": "x", "key": "kept", "value": "mine"},
            {"ns": "x", "key": "rewritten", "value": "mine"},
            {"ns": "x", "key": "removed", "value": "mine"},
            {"ns": "x", "key": "baked", "value": "mine"},
            {"ns": "x", "key": "brand.new", "value": "mine"},
            {"ns": "x", "key": "marked", "value": "***"},
            {"ns": "x", "key": "l.0", "value": "mine"},
        ]
        base = {"kept": "old", "rewritten": "mine", "removed": "mine", "baked": "old", "marked": "a", "l": ["mine"]}
        head = {"kept": "old", "rewritten": "agent", "baked": "mine", "brand": {"new": "x"}, "l": ["agent"]}
        hits = guard(ov, lambda ns: base, lambda ns: head)
        assert [h.split(" ")[0] for h in hits] == ["x:rewritten", "x:removed", "x:l.0"], hits
        assert "removes" in hits[1] and "rewrites" in hits[0], hits
        assert guard(ov, lambda ns: None, lambda ns: head) == []

        # Marker-only catalogs are not rewritten (#3084's feed.json rows).
        feed = Path(d) / "feed.json"
        before = (CATALOGS / "feed.json").read_bytes()
        feed.write_bytes(before)
        baked = {
            "factionSelect.ua.banner": "******************",
            "factionSelect.ua.masthead": "*******************",
            "factionSelect.ua.subtitle": "***************",
            "factionSelect.ua.status.locked": "*******************",
            "factionSelect.wow.banner": "********************",
        }
        out = promote([{"ns": "feed", "key": k, "value": v} for k, v in baked.items()], Path(d))
        assert feed.read_bytes() == before
        assert len(out) == 5 and all(line.startswith("DELETE feed:") for line in out), out


if __name__ == "__main__":
    if "--check" in sys.argv:
        _check()
        sys.exit(print("ok"))
    if "--guard" in sys.argv:
        args = sys.argv[sys.argv.index("--guard") + 1 :]
        if not args:
            sys.exit("usage: promote_copy.py --guard <base-ref>")
        ref = args[0]
        # An unresolved ref would read as "no key at base" and pass everything.
        if subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], capture_output=True).returncode:
            sys.exit(f"--guard: {ref!r} is not a commit here; fetch it (fetch-depth: 0) and rerun.")
        hits = guard(_fetch("dev"), _git_catalog(ref), _disk_catalog)
        for line in hits:
            print(f"::error::{line}")
        if hits:
            print("Live copy on dev.worldzero.org is owner-written. Restore those values; to")
            print("release a key, the owner Reverts its row on the copy-edit page.")
        sys.exit(bool(hits) or print("ok: no owner-written copy changed"))
    lines = promote(_fetch("dev" if "--dev" in sys.argv else "prod"), CATALOGS)
    print("\n".join(lines) or "Nothing to promote — catalogs already match.")
    sys.exit(any(line.startswith("REFUSE") for line in lines))
