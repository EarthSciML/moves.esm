#!/usr/bin/env python3
"""How much of MOVES is ported, measured rather than remembered.

The number this prints has been asked for in prose more than once, and each
time it was assembled by hand from memory of which fixture landed when. That
answer rots the day after it is given: a fixture lands, the figure in PLAN.md
does not move, and nobody can tell whether the stale number is stale or wrong.

So the coverage is derived, every time, from three things that already exist
and that a contributor cannot forget to update without the suite noticing:

  1. THE DENOMINATOR -- `calculator-dag.json` in `../moves.rs`, built by
     `moves-calculator-info` from the pinned MOVES `CalculatorInfo.txt` plus a
     scan of 62 Java files. It is the authoritative module inventory: 65
     modules, each with a `kind`, a `registrations_count`, and its chaining.
     Not a list maintained here, and so not a list that can quietly disagree
     with MOVES.

  2. THE NUMERATOR -- the `| Calculator path |` row of each port
     specification in `docs/`. Every spec already carries one; it is the
     document's own claim about which MOVES modules its fixture reproduces,
     stated where a reader of the spec will see it, and it moves in the same
     commit as the work. Nothing is duplicated into a coverage table that
     could drift from the spec it summarizes.

  3. THE EVIDENCE -- the oracle. A spec's claim only counts when an oracle
     script says it `lives in docs/<name>.md`, that oracle is registered in
     `run-tests.sh`'s ORACLES array, and a fixture in `fixtures/` names the
     same snapshot. A claim with no oracle behind it is reported as a claim,
     never as coverage.

`--check` turns the whole thing into a gate: it exits non-zero if a spec names
a module MOVES does not have, if it claims a module the DAG records as dead,
or if a doc declares a calculator path with no RunSpec (or the reverse). Those
are the three ways this measurement could start lying without anyone noticing.

Usage:
    tools/calculator-coverage.py            # the table
    tools/calculator-coverage.py --check    # gate; non-zero on rot
    tools/calculator-coverage.py --markdown # the PLAN.md §2 table body
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAG = os.environ.get(
    "CALCULATOR_DAG",
    os.path.join(ROOT, "..", "moves.rs", "characterization",
                 "calculator-chains", "calculator-dag.json"),
)

# A `| Calculator path | ... |` table row, and the `| RunSpec | ... |` row that
# says which snapshot the spec is about. Both are existing conventions in
# docs/; this reads them, it does not invent a new place to record things.
PATH_ROW = re.compile(r"^\|\s*Calculator path\s*\|(.+)\|\s*$", re.M)
# Which snapshot the spec is about. The Phase 5 specs say it with a `RunSpec`
# row naming the XML; the four older ones say it with a `snapshot` row naming
# the directory. Both are read, because the point of this tool is to measure
# the documents that exist rather than to make every document alike first.
RUNSPEC_ROW = re.compile(
    r"^\|\s*(?:RunSpec|snapshot)\s*\|\s*`[^`]*"
    r"(?:fixtures/([a-z0-9-]+)\.xml|snapshots/([a-z0-9-]+))`", re.M)
IDENT = re.compile(r"`([A-Z][A-Za-z0-9]*)`")
# Oracles say, in their header comment, which spec they run.
ORACLE_DOC = re.compile(r"lives in\s*\n?#?\s*`?docs/([a-z0-9-]+)\.md`?")


def load_dag():
    with open(DAG) as fh:
        return {m["name"]: m for m in json.load(fh)["modules"]}


def is_live(mod, dag):
    """A module MOVES actually runs.

    Registrations are the direct evidence. A generator has none -- it is pulled
    in by whatever depends on it -- so `subscribes_directly` and being named in
    someone's `chained_downstream` both count. `DummyCalculator` satisfies that
    test and is still a test stub, so it is excluded by name; it is the only
    such case in the file.
    """
    if mod["name"] == "DummyCalculator":
        return False
    if mod["registrations_count"] > 0 or mod["subscribes_directly"]:
        return True
    return any(mod["name"] in o.get("chained_downstream", []) for o in dag.values())


def specs():
    """Every port specification, with what it claims and what backs the claim."""
    docs = os.path.join(ROOT, "docs")
    out = {}
    for name in sorted(os.listdir(docs)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(docs, name)) as fh:
            text = fh.read()
        path = PATH_ROW.search(text)
        runspec = RUNSPEC_ROW.search(text)
        if not path and not runspec:
            continue
        out[name[:-3]] = {
            "modules": IDENT.findall(path.group(1)) if path else None,
            "snapshot": (runspec.group(1) or runspec.group(2)) if runspec else None,
        }
    return out


def oracles():
    """oracle script -> the spec it runs, for those the suite actually runs."""
    with open(os.path.join(ROOT, "run-tests.sh")) as fh:
        suite = fh.read()
    registered = set(re.findall(r'"\./(run-[a-z0-9-]*oracle\.sh)', suite))
    out = {}
    for script in sorted(registered):
        p = os.path.join(ROOT, script)
        if not os.path.exists(p):
            continue
        with open(p) as fh:
            head = fh.read(2000)
        m = ORACLE_DOC.search(head)
        if m:
            out.setdefault(m.group(1), []).append(script)
    return out


def fixtures():
    """snapshot name -> the .esm that reproduces it."""
    d = os.path.join(ROOT, "fixtures")
    out = {}
    for name in sorted(os.listdir(d)):
        if not name.endswith(".esm") or name.startswith("."):
            continue
        with open(os.path.join(d, name)) as fh:
            for snap in set(re.findall(r"snapshots/([a-z0-9-]+)", fh.read())):
                out[snap] = "fixtures/" + name
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if any spec's claim has rotted")
    ap.add_argument("--markdown", action="store_true",
                    help="emit the table body for PLAN.md")
    args = ap.parse_args()

    dag = load_dag()
    live = {n: m for n, m in dag.items() if is_live(m, dag)}
    spec = specs()
    oracle = oracles()
    fixture = fixtures()

    errors, covered, claimed = [], {}, {}
    rows = []
    for name, s in sorted(spec.items()):
        if (s["modules"] is None) != (s["snapshot"] is None):
            errors.append(
                "docs/%s.md declares a %s but no %s -- a coverage claim and "
                "the snapshot it is about have to travel together, or the "
                "claim cannot be checked against anything."
                % (name, "calculator path" if s["modules"] else "RunSpec",
                   "RunSpec" if s["modules"] else "calculator path"))
            continue

        for mod in s["modules"]:
            if mod not in dag:
                errors.append(
                    "docs/%s.md names `%s`, which is not a module in "
                    "calculator-dag.json. Either MOVES renamed it or the spec "
                    "invented it; both matter." % (name, mod))
            elif mod not in live:
                errors.append(
                    "docs/%s.md claims `%s`, which the DAG records as dead "
                    "(no registrations, no subscription, chained from "
                    "nothing). Porting it would not be coverage."
                    % (name, mod))

        backed = name in oracle and s["snapshot"] in fixture
        for mod in s["modules"]:
            (covered if backed else claimed).setdefault(mod, []).append(name)
        rows.append((name, s["snapshot"], len(s["modules"]), backed,
                     fixture.get(s["snapshot"]),
                     ", ".join(oracle.get(name, [])) or "-"))

    if args.check:
        for e in errors:
            print("error: " + e, file=sys.stderr)
        print("checked %d specifications against %d MOVES modules (%d live)"
              % (len(spec), len(dag), len(live)))
        return 1 if errors else 0

    def tally(kind):
        n = sum(1 for m in live.values() if m["kind"] == kind)
        c = sum(1 for x in covered if dag[x]["kind"] == kind)
        return c, n

    if args.markdown:
        print("| Fixture | Snapshot | Modules | Verified |")
        print("|---|---|---:|---|")
        for name, snap, n, backed, fx, _ in rows:
            print("| `%s` | `%s` | %d | %s |"
                  % (name, snap or "-", n, "yes" if backed else "**no**"))
        return 0

    print("MOVES port coverage")
    print("  denominator: %s" % os.path.relpath(DAG, ROOT))
    print("  %d modules, %d live (%d calculators, %d generators)"
          % (len(dag), len(live), tally("Calculator")[1], tally("Generator")[1]))
    print()
    print("  %-26s %-26s %3s  %s" % ("spec", "snapshot", "mod", "evidence"))
    for name, snap, n, backed, fx, orc in rows:
        print("  %-26s %-26s %3d  %s"
              % (name, snap or "-", n,
                 orc if backed else "NOT COUNTED (%s)"
                 % ("no fixture" if snap not in fixture else "no oracle")))
    print()
    for kind in ("Calculator", "Generator"):
        c, n = tally(kind)
        print("  %-11s %2d of %2d live  (%4.1f %%)"
              % (kind.lower() + "s", c, n, 100.0 * c / n))
    c = len(covered)
    print("  %-11s %2d of %2d live  (%4.1f %%)"
          % ("all", c, len(live), 100.0 * c / len(live)))
    if claimed:
        print()
        print("  claimed but not counted, for want of a fixture or an oracle:")
        for mod, where in sorted(claimed.items()):
            if mod not in covered:
                print("    %-42s %s" % (mod, ", ".join(where)))
    print()
    print("  not yet ported:")
    for kind in ("Calculator", "Generator"):
        rest = sorted(n for n, m in live.items()
                      if m["kind"] == kind and n not in covered)
        for n in rest:
            print("    %-9s %-42s %d registrations"
                  % (kind.lower(), n, dag[n]["registrations_count"]))
    if errors:
        print()
        print("  %d claim(s) have rotted; run --check for detail" % len(errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
