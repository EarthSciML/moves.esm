#!/usr/bin/env python3
"""Refuse a `faq` whose `filter` names a variable by BARE NAME when the
aggregate has two or more output indices.

EarthSciML/EarthSciAST#441: a filter may reference a variable by bare name,
resolved from the variable's shape exactly as `expr` resolves it -- and that
works while the aggregate has ONE output index. With two, the filter is
IGNORED. Not the bare factor: the whole filter. No error, no NaN, and an answer
that is a sum over rows the filter names.

docs/esm-conventions.md 74 has the three-variable probe that pins the trigger to
the output count alone: a second non-output range, a `join`, an
`apply_expression_template`, which output index the variable draws and a second
factor over another index set all change nothing.

The rule this enforces is one spelling: `{"op": "index", "args": [name, sym]}`.
It is four characters longer than the bare form and it is never wrong.

WHY A LINT AND NOT A CONVENTION. The two spellings differ by four characters,
the broken one reads more naturally, and the failure is invisible in three
ordinary situations: behind a boolean gate (the value relation is never asked),
in a presence relation (those have one output index and filter correctly), and
on any run whose selections happen not to reach the excluded rows. This
repository carried one instance for some time and nothing was wrong until a
second configuration was added to the relation it reads.

    ./tools/faq-filter-lint.py [path ...]     # default: the repo root
    ./tools/faq-filter-lint.py --selftest     # the walk is checked, not trusted

Exit 0 and one summary line if clean; exit 1 and one line per site if not.

`--selftest` is what makes a clean sweep mean something. It builds the smallest
document that HAS the defect -- the three-variable probe of conventions 74.1 --
and requires the walk to reject it, so a lint that quietly stopped finding
anything (a renamed key, a structure it no longer recognises) reports that
instead of a clean tree. The suite runs both.
"""
import json
import pathlib
import sys
import tempfile

SKIP_KEYS = {"name"}  # an apply_expression_template's template name is not a variable


def leaf_names(node, out):
    """Every string leaf of `node` that is NOT an index symbol of an `index` op."""
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        if node.get("op") == "index":
            # args[0] is the variable and it is INDEXED -- the spelling we want.
            return
        for key, value in node.items():
            if key in SKIP_KEYS:
                continue
            leaf_names(value, out)
    elif isinstance(node, list):
        for value in node:
            leaf_names(value, out)


def sites(path):
    try:
        doc = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    for model_name, model in (doc.get("models") or {}).items():
        if not isinstance(model, dict):
            continue
        declared = set(model.get("variables") or {})
        for equation in model.get("equations") or []:
            rhs = equation.get("rhs")
            if not isinstance(rhs, dict) or rhs.get("op") != "faq":
                continue
            outputs = rhs.get("output_idx") or []
            filt = rhs.get("filter")
            if filt is None or len(outputs) < 2:
                continue
            names = []
            leaf_names(filt, names)
            bare = sorted({n for n in names if n in declared})
            if bare:
                yield path, model_name, equation.get("lhs"), outputs, bare


DEFECTIVE = {
    "esm": "1.2.0",
    "metadata": {"name": "faq-filter-lint-selftest", "description": "one faq, two output indices, a bare name in the filter", "authors": ["selftest"], "tags": ["selftest"]},
    "index_sets": {"a_rows": {"kind": "interval", "size": 3}, "c_rows": {"kind": "interval", "size": 2}},
    "models": {"Probe": {
        "variables": {
            "a_val": {"type": "unknown", "units": "1", "shape": ["a_rows"], "description": "1, 2, 3"},
            "c_val": {"type": "unknown", "units": "1", "shape": ["c_rows"], "description": "10, 20"},
            "y": {"type": "unknown", "units": "1", "shape": ["a_rows", "c_rows"], "description": "the filter does not apply"},
        },
        "equations": [
            {"lhs": "a_val", "rhs": {"op": "const", "args": [], "value": [1.0, 2.0, 3.0]}},
            {"lhs": "c_val", "rhs": {"op": "const", "args": [], "value": [10.0, 20.0]}},
            {"lhs": "y", "rhs": {"op": "faq", "args": [], "semiring": "sum_product",
                "output_idx": ["i", "g"],
                "ranges": {"i": {"from": "a_rows"}, "g": {"from": "c_rows"}},
                "filter": {"op": "ifelse", "args": [{"op": ">", "args": ["a_val", 1.5]}, 1.0, 0.0]},
                "expr": {"op": "*", "args": [{"op": "index", "args": ["a_val", "i"]},
                                             {"op": "index", "args": ["c_val", "g"]}]}}},
        ],
    }},
}


def selftest():
    with tempfile.TemporaryDirectory() as d:
        probe = pathlib.Path(d) / "defective.esm"
        probe.write_text(json.dumps(DEFECTIVE, indent=2) + "\n")
        found = list(sites(probe))
    if len(found) != 1 or found[0][4] != ["a_val"]:
        print(f"selftest FAILED: the walk reports {found} on a document that has exactly one bare filter name")
        return 1
    print("selftest: the walk rejects the smallest document that has the defect")
    return 0


def main(argv):
    if "--selftest" in argv[1:]:
        return selftest()
    roots = [pathlib.Path(a) for a in argv[1:]] or [pathlib.Path(__file__).resolve().parent.parent]
    files = []
    for root in roots:
        files.extend(sorted(root.rglob("*.esm")) if root.is_dir() else [root])
    found = [s for f in files for s in sites(f)]
    for path, model, lhs, outputs, bare in found:
        print(
            f"{path}: {model}.{lhs} aggregates to {len(outputs)} output indices "
            f"{outputs} and its filter names {', '.join(bare)} BARE -- index them "
            f"explicitly (EarthSciML/EarthSciAST#441, docs/esm-conventions.md 74)"
        )
    if found:
        print(f"{len(found)} faq filter(s) that do not apply, over {len(files)} document(s)")
        return 1
    print(f"no faq filter names a variable bare at two or more output indices, over {len(files)} documents")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
