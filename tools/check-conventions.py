#!/usr/bin/env python3
"""Check the authoring conventions of docs/esm-conventions.md mechanically.

Every rule here exists because a reviewer was asked to check it by eye and a
machine can check it instead. Run from the repository root; exits non-zero and
names the offending file, JSON path and rule on any violation.

The checks are deliberately structural, over the parsed JSON, rather than
textual: an equality `filter` is a shape in the AST, not a string, and a grep
for `"=="` cannot tell a join standing in for an ON clause from an honest
predicate that happens to compare two things.

Nothing here generates or rewrites a .esm file (CLAUDE.md). It only reads.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# docs/findings/ holds deliberate repros of upstream defects; three of them do
# not even load. They are exercised by run-tests.sh's tripwire stage instead.
EXCLUDED_DIRS = {".moves", "target", "docs/findings"}

# The one file allowed to spell a join as an equality `filter`: the ungated
# calibration half of the scaling gate, which exists precisely to be the thing
# the convention forbids. See its own description.
UNGATED_CONTROL = "gates/equijoin_undriven_control.esm"

# `t` is the independent variable. A `ranges` key or `output_idx` entry that
# shadows it makes a `join.on` match nothing, silently -- docs/findings F4.
RESERVED_SYMBOLS = {"t", "_var"}

problems: list[str] = []


def fail(path: pathlib.Path, where: str, rule: str, detail: str) -> None:
    problems.append(f"{path.relative_to(ROOT)}: {where}: [{rule}] {detail}")


def documents() -> list[pathlib.Path]:
    out = []
    for p in sorted(ROOT.rglob("*.esm")):
        rel = p.relative_to(ROOT).as_posix()
        if any(rel == d or rel.startswith(d + "/") for d in EXCLUDED_DIRS):
            continue
        out.append(p)
    return out


def walk(node, path: str):
    """Yield (json_pointer, dict) for every object in the tree."""
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}/{i}")


def contains_op(node, op: str) -> bool:
    for _, obj in walk(node, ""):
        if obj.get("op") == op:
            return True
    return False


def check_no_equality_filter(p: pathlib.Path, doc) -> None:
    """RULE: every join is a `join.on`; a `filter` carries a genuine predicate.

    An `==` inside an aggregate `filter` is an ON clause in disguise. Range
    tests, null guards and set membership are what a filter is for.
    """
    if p.relative_to(ROOT).as_posix() == UNGATED_CONTROL:
        return
    for ptr, obj in walk(doc, ""):
        if obj.get("op") != "aggregate" or "filter" not in obj:
            continue
        if contains_op(obj["filter"], "=="):
            fail(p, ptr + "/filter", "equality-filter",
                 "an `==` inside an aggregate `filter` is a join spelled as a "
                 "predicate; use join.on with a key-pair list")


def check_reserved_loop_symbols(p: pathlib.Path, doc) -> None:
    """RULE: `t` is never a loop symbol (docs/findings F4)."""
    for ptr, obj in walk(doc, ""):
        if obj.get("op") != "aggregate":
            continue
        for key in (obj.get("ranges") or {}):
            if key in RESERVED_SYMBOLS:
                fail(p, ptr + "/ranges", "reserved-loop-symbol",
                     f"range symbol {key!r} shadows the independent variable; "
                     "the join gate then matches nothing, silently")
        for entry in (obj.get("output_idx") or []):
            if entry in RESERVED_SYMBOLS:
                fail(p, ptr + "/output_idx", "reserved-loop-symbol",
                     f"output index {entry!r} shadows the independent variable")


def check_join_clauses_are_on(p: pathlib.Path, doc) -> None:
    """RULE: a join clause names its key columns.

    `overlap` is legitimate for spatial work and simply does not arise in
    MOVES; flag it so that its first appearance is a deliberate decision.
    """
    for ptr, obj in walk(doc, ""):
        if obj.get("op") != "aggregate":
            continue
        for i, clause in enumerate(obj.get("join") or []):
            if "on" not in clause:
                fail(p, f"{ptr}/join/{i}", "join-not-on",
                     "join clause is not an `on` clause; MOVES has no spatial "
                     "joins, so this needs a written reason")
            elif not clause["on"]:
                fail(p, f"{ptr}/join/{i}/on", "join-not-on",
                     "empty key-pair list")


def check_library_purity(p: pathlib.Path, doc) -> None:
    """RULE: lib/ holds template-library files and nothing else (esm-spec §9.7.1)."""
    rel = p.relative_to(ROOT).as_posix()
    if not rel.startswith("lib/"):
        return
    if not doc.get("expression_templates"):
        fail(p, "/", "library-purity",
             "a file in lib/ must declare top-level expression_templates")
    for forbidden in ("models", "reaction_systems", "data_sources", "coupling", "domain"):
        if forbidden in doc:
            fail(p, "/" + forbidden, "library-purity",
                 f"a template-library file must not declare {forbidden}")


def check_assembly_index_sets(p: pathlib.Path, doc) -> None:
    """RULE: an assembly's index sets agree with those of every file it mounts.

    esm-spec §4.7 says a subsystem ref merges the referenced file's index sets
    into the mounting document's registry, and that a non-equal collision is a
    load error. At a top-level `models` {ref} edge the merge does not happen
    (docs/findings F2), so the assembly restates the axes and this check stands
    in for the conflict detection the loader would have done.
    """
    for name, entry in (doc.get("models") or {}).items():
        if not isinstance(entry, dict) or "ref" not in entry:
            continue
        target = (p.parent / entry["ref"]).resolve()
        if not target.is_file():
            fail(p, f"/models/{name}/ref", "assembly-index-sets",
                 f"referenced file not found: {entry['ref']}")
            continue
        try:
            ref_doc = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(p, f"/models/{name}/ref", "assembly-index-sets",
                 f"referenced file is not valid JSON: {exc}")
            continue
        mine = doc.get("index_sets") or {}
        for set_name, definition in (ref_doc.get("index_sets") or {}).items():
            if set_name not in mine:
                fail(p, "/index_sets", "assembly-index-sets",
                     f"{entry['ref']} declares index set {set_name!r} and this "
                     "document does not restate it (the §4.7 merge does not run "
                     "on a top-level {ref} edge)")
            elif mine[set_name] != definition:
                fail(p, f"/index_sets/{set_name}", "assembly-index-sets",
                     f"disagrees with {entry['ref']}: "
                     f"{json.dumps(mine[set_name], sort_keys=True)} vs "
                     f"{json.dumps(definition, sort_keys=True)}")


CHECKS = (
    check_no_equality_filter,
    check_reserved_loop_symbols,
    check_join_clauses_are_on,
    check_library_purity,
    check_assembly_index_sets,
)


def main() -> int:
    docs = documents()
    if not docs:
        print("  no .esm documents to check")
        return 0
    for p in docs:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(p, "/", "parse", str(exc))
            continue
        for check in CHECKS:
            check(p, doc)
    if problems:
        for line in problems:
            print(f"  {line}")
        return 1
    print(f"  {len(docs)} documents, {len(CHECKS)} rules, no violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
