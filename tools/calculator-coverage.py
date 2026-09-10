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
import glob
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

# The three live calculators that belong to the NONROAD side.
#
# This has to be written down rather than derived, and it is worth saying why,
# because three plausible automatic signals were tried and all three fail:
#
#   * `calculator-dag.json`'s registrations are keyed on (pollutant, process)
#     alone and say nothing about the model, so a NONROAD calculator appears
#     as a candidate on any ONROAD RunSpec that happens to select a pair it
#     shares -- which is most of them.
#   * `java_path` does not separate them: only `NonroadEmissionCalculator`
#     lives under `master/nonroad/`; both `NR*` classes sit in the same
#     `implementation/ghg/` package as the onroad calculators.
#   * The snapshot's own tables do not either. `nr*`-prefixed tables ship
#     populated in the default database regardless of model -- `mixed-onroad`,
#     an ONROAD snapshot, carries 89 of them holding 381,789 rows.
#
# What IS authoritative is the RunSpec's own `<model>` element, which is what
# MOVES reads to decide which model runs. That covers the snapshot side; this
# list covers the calculator side. The evidence for each name:
# `NonroadEmissionCalculator` is the onroad DAG's hook into the NONROAD
# simulation (its module doc, and the only `master/nonroad/` java_path), and
# both `NR*` calculators read exclusively `nr*`-prefixed input tables that no
# onroad calculator reads (`nrATRatio`, `nrHCSpeciation`, `nrMethaneTHCRatio`
# and their siblings, from the `INPUT_TABLES` each declares).
#
# Three names is small enough to check by hand and stable enough to keep. If a
# fourth appears, `--ladder` will silently credit it to onroad snapshots.
NONROAD_CALCULATORS = {
    "NonroadEmissionCalculator",
    "NRAirToxicsCalculator",
    "NRHCSpeciationCalculator",
}

# A `| Calculator path | ... |` table row, and the `| RunSpec | ... |` row that
# says which snapshot the spec is about. Both are existing conventions in
# docs/; this reads them, it does not invent a new place to record things.
# A module whose class name ends in neither `Generator` nor `Calculator`, so
# the DAG builder filed it as `Unknown`, but whose ROLE is a generator. See
# `is_live`'s docstring: TAG is Total Activity Generator.
GENERATORS_BY_ROLE = {"ProjectTAG"}

# The three generators canonical MOVES discards under DO_RATES_FIRST.
# `MOVESInstantiator.java:1449` and the whitelist at :1457-1491.
RATES_FIRST_DISCARDED = {
    "OperatingModeDistributionGenerator",
    "MesoscaleLookupOperatingModeDistributionGenerator",
    "MesoscaleLookupTotalActivityGenerator",
}

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
    """A module the pinned MOVES build actually computes with.

    The test differs by kind, because the evidence differs by kind.

    A CALCULATOR is live iff it registers at least one (pollutant, process)
    pair. Registration is what MOVES consults to decide whether a calculator
    contributes to a run; a calculator that registers none contributes nothing,
    whatever else it declares.

    Subscription is NOT sufficient, and reading it as sufficient is the trap.
    Twelve calculators subscribe to the master loop, register zero pairs, are
    named in nobody's `chained_downstream`, and have no dependents: they are
    the classes `BaseRateCalculator`'s rates-first approach superseded, left in
    the tree with their `Subscribe` directive intact.
    `docs/process-brakewear.md` says exactly this of one of them --
    "`CalculatorInfo.txt` registers (116, 9) to `BaseRateCalculator`, and
    `calculator-dag.json` records `registrations_count: 0` for the legacy
    class" -- and `moves.rs` says it in the module docs of
    `criteria_running_calculator`, `criteria_start_calculator` and
    `basicstartpm`. Counting them would put twelve modules in the denominator
    that no fixture can ever exercise, because MOVES itself never calls them.

    `DummyCalculator` is one of those twelve rather than a special case, so
    this rule needs no by-name exclusion. An earlier version of this function
    had one, which is what a wrong rule looks like from the inside: the
    exception that had to be carved out was the rule disagreeing with reality.

    A GENERATOR registers nothing by nature -- it is pulled in by whatever
    depends on it -- so for generators subscription and being chained from
    something are the evidence.

    `PROJECTTAG IS A GENERATOR AND THIS FUNCTION USED TO SAY IT WAS NOT.` The
    docstring here read "`ProjectTAG` is project-scale tagging, and neither is
    model arithmetic a fixture could reproduce". **TAG is Total Activity
    Generator.** `ProjectTAG.java` is the PROJECT-domain counterpart of
    `TotalActivityGenerator`: it computes SHO, SHP, Starts and extended-idle
    activity from link volumes and `offNetworkLink` (`:388-476`), it is on
    canonical MOVES's `DO_RATES_FIRST` whitelist
    (`MOVESInstantiator.java:1465`), `moves.rs` ports it as a generator, and
    `scale-project` class-loads it. It is model arithmetic and a fixture CAN
    reproduce it. Its `kind: "Unknown"` is an artifact of the DAG builder
    classifying by class-name suffix -- `ProjectTAG` ends in neither
    `Generator` nor `Calculator` -- and not a statement about the module.
    So it is named here as a generator by role. `MasterLoopTest` really is a
    test harness and the other eight `Unknown`s are control strategies, which
    are RunSpec-driven and not master-loop modules.

    TWO FURTHER EXCLUSIONS, both of them things MOVES does not run:

    A PHANTOM is a DAG entry with no Java class behind it: empty `java_path`,
    zero registrations, and named in nobody's `chained_downstream`. Exactly
    one module answers that description -- `NewTvvYearGenerator`, which is a
    named SQL section of `MultidayTankVaporVentingCalculator.sql` (335-432)
    and not a class at all; `docs/new-tvv-year.md` proves it against the
    corpus. The test is derived rather than a by-name list, and it is three
    conditions rather than one because `CrankcaseEmissionCalculatorNonPM` also
    has an empty `java_path` and is entirely real (180 registrations).

    RATES-FIRST DISCARDS are the three generators
    `MOVESInstantiator.generateExecutionGraph` throws away. Under
    `CompilationFlags.DO_RATES_FIRST`, which is `true` in the pinned source,
    `:1449` clears `neededClassNames`, `:1450-1456` re-adds three classes and
    `:1457-1491` intersects a whitelist containing neither
    `OperatingModeDistributionGenerator` nor either `MesoscaleLookup` one. The
    swap that would restore `MesoscaleLookupTotalActivityGenerator` is
    commented out; the one that would restore
    `MesoscaleLookupOperatingModeDistributionGenerator` runs BEFORE the clear;
    and `alsoInstantiate` -- the late escape hatch -- has zero call sites.
    They are named rather than derived because the evidence is a control-flow
    reading of Java the DAG does not encode, and `docs/omd-generator-reachability.md`
    is where that reading is written down. This is a by-name list of the kind
    the `DummyCalculator` note above warns about, and the difference is that
    it is not an exception to a rule that disagrees with reality -- the DAG
    simply has no field for "discarded by the instantiator", so there is no
    rule to derive it from.
    """
    if is_phantom(mod, dag) or mod["name"] in RATES_FIRST_DISCARDED:
        return False
    if mod["kind"] == "Calculator":
        return mod["registrations_count"] > 0
    if mod["kind"] == "Generator" or mod["name"] in GENERATORS_BY_ROLE:
        return (mod["subscribes_directly"]
                or any(mod["name"] in o.get("chained_downstream", [])
                       for o in dag.values()))
    return False


def is_phantom(mod, dag):
    """A DAG entry with no Java class behind it. See `is_live`'s docstring."""
    return (not mod.get("java_path")
            and mod["registrations_count"] == 0
            and not any(mod["name"] in o.get("chained_downstream", [])
                        for o in dag.values()))


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


def output_path(snap):
    """The MOVESOutput parquet inside a snapshot directory.

    The capture tool lowercases the output database when it builds the file
    name; `provenance.json` preserves the case MOVES used. Thirty-eight of the
    thirty-nine snapshots have an all-lowercase database name, so building the
    path from the field verbatim worked everywhere except `sample-runspec`
    (`JUnitTestOutput`) -- where it raised FileNotFoundError, which the ladder
    swallowed into a one-line note that read as "this snapshot emits nothing".
    It emits 84 rows. Lowercase first, then glob, so that a future naming
    change fails loudly instead of quietly subtracting a snapshot.
    """
    with open(os.path.join(snap, "provenance.json")) as fh:
        db = json.load(fh)["output_database"]
    path = os.path.join(snap, "tables",
                        "db__%s__movesoutput.parquet" % db.lower())
    if os.path.exists(path):
        return path
    hits = glob.glob(os.path.join(snap, "tables",
                                  "db__*__movesoutput.parquet"))
    if len(hits) != 1:
        raise IOError("%d MOVESOutput tables under %s, expected exactly 1"
                      % (len(hits), snap))
    return hits[0]


def read_output(snap):
    """(row count, set of pollutant-process pairs) for one snapshot."""
    import pyarrow.parquet as pq
    path = output_path(snap)
    n = pq.read_metadata(path).num_rows
    if not n:
        return 0, set()
    t = pq.read_table(path, columns=["pollutantID", "processID"])
    d = t.to_pydict()
    return n, {(d["pollutantID"][i], d["processID"][i])
               for i in range(t.num_rows)}


def unreadable_outputs():
    """Snapshots holding a MOVESOutput this tool cannot read.

    The fourth rot mode, and the only one about the tool rather than the
    documents. A snapshot that emits rows and reads as unreadable is
    indistinguishable, in the ladder's output, from one that emits nothing --
    and "emits nothing" is a conclusion the port acts on, by striking the
    snapshot off the board. So an unreadable output is a hard error, not a
    note.
    """
    ch = os.path.join(ROOT, "..", "moves.rs", "characterization")
    out = []
    for xml in sorted(glob.glob(os.path.join(ch, "fixtures", "*.xml"))):
        snap = os.path.join(ch, "snapshots", os.path.basename(xml)[:-4])
        if not os.path.isdir(snap):
            continue
        if not glob.glob(os.path.join(snap, "tables",
                                      "db__*__movesoutput.parquet")):
            continue                      # genuinely absent, not unreadable
        try:
            read_output(snap)
        except Exception as exc:
            out.append("%s holds a MOVESOutput parquet this tool could not "
                       "read (%s: %s). The ladder would report it as emitting "
                       "nothing, which is how a real rung gets struck off the "
                       "board." % (os.path.basename(snap),
                                   type(exc).__name__, exc))
    return out


def ladder(dag, live, covered):
    """What each snapshot would newly unlock, measured from its OUTPUT.

    Rung order is the recurring decision on this port, and answering it from
    memory has gone wrong twice: once recommending a snapshot for a calculator
    that is one of the superseded twelve, and once crediting NONROAD
    calculators to ONROAD snapshots because registration is model-blind. Both
    were plausible and both were wrong, so the answer is derived here.

    THE PAIRS COME FROM THE OUTPUT, NOT THE RUNSPEC. A RunSpec selects
    pollutant-process pairs; it does not promise MOVES emitted rows for them.
    Three already-ported snapshots make the difference concrete: process-
    refueling, process-evap-leaks and process-evap-fvv each select pollutant 86
    (and two of them 87), for which `HCSpeciationCalculator` is registered --
    and their MOVESOutput contains no row for any of those pairs. Reading the
    RunSpec would report all three as unlocking HCSpeciationCalculator; reading
    the output shows it contributed nothing there, which is also why those
    fixtures match 100 % of their rows without implementing it.

    Reading the output also disposes of the zero-row snapshots without a
    special case: process-extended-idle, both process-apu and all four
    process-crankcase-{start,extidle}* have an empty MOVESOutput AND an empty
    MOVESWorkerOutput, so they emit no pairs and unlock nothing. They are
    structural gates over the run scope, not verification rungs -- a fixture
    cannot be checked against no rows.

    Row counts and pairs come from the output parquet: the count from the
    footer via `read_metadata`, the pairs from the two key columns only.
    """
    ch = os.path.join(ROOT, "..", "moves.rs", "characterization")
    reg = {}
    with open(DAG) as fh:
        for r in json.load(fh)["registrations"]:
            reg.setdefault((r["pollutant_id"], r["process_id"]),
                           set()).add(r["calculator"])

    ported = set()
    for name in os.listdir(os.path.join(ROOT, "fixtures")):
        if name.endswith(".esm") and not name.startswith("."):
            with open(os.path.join(ROOT, "fixtures", name)) as fh:
                ported |= set(re.findall(r"snapshots/([a-z0-9-]+)", fh.read()))

    rows = []
    for xml in sorted(glob.glob(os.path.join(ch, "fixtures", "*.xml"))):
        name = os.path.basename(xml)[:-4]
        snap = os.path.join(ch, "snapshots", name)
        if not os.path.isdir(snap):
            continue
        with open(xml) as fh:
            models = set(re.findall(r'<model value="(\w+)"', fh.read()))
        model = "/".join(sorted(models)) or "?"

        n, pairs, note = None, set(), ""
        try:
            n, pairs = read_output(snap)
        except Exception as exc:
            note = type(exc).__name__

        cands = set()
        for pr in pairs:
            cands |= reg.get(pr, set())
        if models == {"ONROAD"}:
            cands -= NONROAD_CALCULATORS
        elif models == {"NONROAD"}:
            cands &= NONROAD_CALCULATORS
        rows.append({
            "name": name, "model": model, "rows": n, "pairs": sorted(pairs),
            "cands": {c for c in cands if c in live},
            "ported": name in ported, "note": note,
        })

    todo = [r for r in rows if not r["ported"]]
    print("ladder -- what each unported snapshot would newly unlock")
    print("  pairs and rows read from MOVESOutput, not from the RunSpec")
    print()
    print("  %-30s %-8s %6s %5s  %s"
          % ("snapshot", "model", "rows", "pairs", "unlocks"))
    ranked = sorted(todo, key=lambda r: (-len(r["cands"] - covered),
                                         r["rows"] if r["rows"] else 1 << 30))
    for r in ranked:
        new = sorted(r["cands"] - covered)
        if not new:
            continue
        print("  %-30s %-8s %6s %5d  +%d %s"
              % (r["name"], r["model"],
                 r["rows"] if r["rows"] is not None else "?",
                 len(r["pairs"]), len(new), ", ".join(new)))

    empty = [r for r in todo if r["rows"] == 0]
    if empty:
        print()
        print("  emit NO rows -- structural gates over the run scope, not")
        print("  verification rungs; a fixture cannot be checked against none:")
        for r in empty:
            print("    %s" % r["name"])

    rest = [r for r in ranked if r["rows"] and not (r["cands"] - covered)]
    if rest:
        print()
        print("  emit rows, but unlock no calculator not already covered --")
        print("  these test axis generalization rather than new arithmetic:")
        for r in rest:
            print("    %-28s %-8s %6s %5d" % (r["name"], r["model"],
                                              r["rows"], len(r["pairs"])))

    reachable = set()
    for r in rows:
        reachable |= r["cands"]
    missing = sorted(n for n, m in live.items()
                     if m["kind"] == "Calculator" and n not in reachable)
    if missing:
        print()
        print("  live, but NO snapshot in the corpus emits a row it owns --")
        print("  porting it needs a new RunSpec generated in moves.rs:")
        for n in missing:
            print("    %-42s %d registrations"
                  % (n, dag[n]["registrations_count"]))
    bad = [r for r in rows if r["note"]]
    if bad:
        print()
        print("  no MOVESOutput read: %s"
              % ", ".join("%s (%s)" % (r["name"], r["note"]) for r in bad))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if any spec's claim has rotted")
    ap.add_argument("--markdown", action="store_true",
                    help="emit the table body for PLAN.md")
    ap.add_argument("--ladder", action="store_true",
                    help="what each unported snapshot would newly unlock")
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

    if args.ladder:
        return ladder(dag, live, set(covered))

    if args.check:
        errors.extend(unreadable_outputs())
        for e in errors:
            print("error: " + e, file=sys.stderr)
        print("checked %d specifications against %d MOVES modules (%d live)"
              % (len(spec), len(dag), len(live)))
        return 1 if errors else 0

    def bucket(name):
        """The reporting bucket a live module belongs to.

        `kind` alone would leave `ProjectTAG` in neither, because the DAG
        files it as `Unknown` on its class-name suffix. It is a generator by
        role (see `is_live`), so the two buckets have to sum to `len(live)`
        and this is where that is enforced rather than assumed.
        """
        if name in GENERATORS_BY_ROLE:
            return "Generator"
        return dag[name]["kind"]

    def tally(kind):
        n = sum(1 for name in live if bucket(name) == kind)
        c = sum(1 for x in covered if bucket(x) == kind)
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
    n_calc, n_gen = tally("Calculator")[1], tally("Generator")[1]
    assert n_calc + n_gen == len(live), (
        "the two buckets do not sum to the live set: %d + %d != %d"
        % (n_calc, n_gen, len(live)))
    print("  %d modules, %d live (%d calculators, %d generators)"
          % (len(dag), len(live), n_calc, n_gen))
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
    # The exclusion is the largest single judgement this tool makes -- it
    # removes twelve calculators from the denominator -- so it is printed
    # rather than left implicit in is_live().
    dead = [(n, m) for n, m in sorted(dag.items())
            if m["kind"] == "Calculator" and n not in live]
    # Two different reasons, and saying "superseded" for both would be wrong:
    # a class that still subscribes has been displaced by BaseRateCalculator,
    # whereas one that subscribes to nothing was never wired in at all
    # (GenericCalculatorBase is the abstract base; the WTP pair is well-to-pump).
    print("  not in the denominator, because MOVES never calls them:")
    for label, which in (
            ("superseded -- subscribes, registers no pollutant-process pair",
             [n for n, m in dead if m["subscribes_directly"]]),
            ("unwired -- no subscription and no registration",
             [n for n, m in dead if not m["subscribes_directly"]])):
        print("    %s:" % label)
        for n in which:
            print("      %s" % n)
    print()
    # The three exclusions this tool makes on top of the calculator rule, each
    # printed with the evidence rather than left implicit in is_live().
    print("  not in the denominator, because canonical MOVES never "
          "INSTANTIATES them (DO_RATES_FIRST):")
    for n in sorted(RATES_FIRST_DISCARDED):
        if n in dag:
            print("      %-46s MOVESInstantiator.java:1449 clears it" % n)
    phantoms = sorted(n for n, m in dag.items() if is_phantom(m, dag))
    if phantoms:
        print("  not in the denominator, because there is no such class:")
        for n in phantoms:
            print("      %-46s java_path '', 0 registrations, chained from "
                  "nothing" % n)
    print()
    print("  not yet ported:")
    for kind in ("Calculator", "Generator"):
        rest = sorted(n for n, m in live.items()
                      if (m["kind"] == kind
                          or (kind == "Generator" and n in GENERATORS_BY_ROLE))
                      and n not in covered)
        for n in rest:
            print("    %-9s %-42s %d registrations"
                  % (kind.lower(), n, dag[n]["registrations_count"]))
    if errors:
        print()
        print("  %d claim(s) have rotted; run --check for detail" % len(errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
