# `NewTvvYearGenerator` — the disproof

Every other document in `docs/` specifies a port. This one specifies that
there is nothing to port, and does it with an oracle rather than a paragraph,
because the claim it replaces was also a paragraph and was wrong.

`docs/omd-generator-reachability.md` listed `NewTvvYearGenerator` as the
fifth unreachable operating-mode-family generator and said of it:

> `CalculatorInfo.txt` names it against process 12, but the scan of the
> pinned MOVES source found no class by that name to attach it to.

**The first half of that is false.** `CalculatorInfo.txt` does not name it.
Grepped case-insensitively over the entire pinned MOVES tree (MOVES5.0.1 @
`25dc6c83`), the string `newtvvyear` occurs exactly three times:

```
database/MultidayTankVaporVentingCalculator.sql:335   -- Section NewTVVYear
database/MultidayTankVaporVentingCalculator.sql:432   -- End Section NewTVVYear
gov/.../ghg/TankVaporVentingCalculator.java:142       enabledSectionNames.add("NewTVVYear");
```

It is a **named SQL section** of the tank-vapour-venting calculator, switched
on by that calculator, in a file that calculator owns. There is no class, no
`Subscribe` line, no `Registration` line and no MasterLoop subscription. The
`"source": "CalculatorInfo"` on its `calculator-dag.json` subscription was
added by hand in `moves.rs` commit `f375a77c` to fix an unrelated
snapshot-table lookup, and the entry's own neighbouring fields contradict it:
`"java_path": ""` and `"registrations_count": 0`.

---

## 0. What is being disproved, and what would refute the disproof

| | |
|---|---|
| Snapshot | `../moves.rs/characterization/snapshots/process-evap-fvv` — **no new capture** |
| Claim | the three tables a `NewTvvYearGenerator` would produce are already in the corpus, produced by `TankVaporVentingCalculator` |
| Refuted by | any snapshot whose `execution-trace.json` names a class matching `NewTvvYear`; or the DAG entry acquiring a `java_path` or a registration |
| Oracle | `./run-new-tvv-year-oracle.sh`, §6.5 |
| Ported by | nothing, and that is the finding |

The oracle asserts the negative as well as the positive, which is the whole
point: it fails if a `NewTvvYear*` class is ever loaded, and it fails if the
DAG entry ever grows the `java_path` that would make it a real module. A
document that only asserted the tables' contents would go on passing after
someone found the class.

## 1. What the section computes

`-- Section NewTVVYear` (`MultidayTankVaporVentingCalculator.sql:335-432`) is
three `CREATE TABLE` / `INSERT ... SELECT` pairs, each suffixed with
`##context.year##` — which is why the corpus holds `stmyTVVCoeffs**2020**`
and `stmyTVVEquations**2020**` rather than unsuffixed names, and why the
`moves.rs` lookup that `f375a77c` was fixing failed in the first place.

| # | table | from | key |
|---|---|---|---|
| 1 | `regClassFractionOfSTMY<year>` | `SampleVehiclePopulation` | sourceType, modelYear, fuelType, regClass |
| 2 | `stmyTVVEquations<year>` | `cumTVVCoeffs` ⋈ `pollutantProcessMappedModelYear` ⋈ `ageCategory` ⋈ (1) | + polProcess, and the two equation STRINGS |
| 3 | `stmyTVVCoeffs<year>` | (2) | (2)'s key minus regClass and the equation strings |

Step 1 collapses `SampleVehiclePopulation`'s engine-technology detail into a
regulatory-class fraction, keeping only strictly positive sums. Step 2 weights
six coefficient columns by that fraction and sums them over the coefficient
rows an age group reaches — the join condition is
`ppmy.modelYearID = <year> - ageCategory.ageID`, so a coefficient row applies
to the model years its age group reaches back to from the run's year. Step 3
drops the regulatory class and the two equation strings out of the key and
sums again.

**The two equation strings staying in step 2's key and leaving it in step 3
is the substance of the section.** `tvvEquation` and `leakEquation` are form
selectors — `T0`, `L0`, `L9` and so on — and a coefficient set only means
anything paired with the form it parameterises. Step 2 keeps the pairing;
step 3 produces the fleet-average coefficients the calculator's arithmetic
actually consumes, where the form has already been resolved.

## 2. Why this is a disproof and not a port

Nothing in `components/` or `lib/` implements this section, and nothing
should. It is inside `MultidayTankVaporVentingCalculator.sql`, which
`docs/evap-fvv.md` specifies and `components/tank_fuel_venting.esm` ports; if
the fleet-average coefficients were ever needed by the `.esm` port they would
be a stage of that component, not a module of their own.

What this document is for is the **coverage denominator**. A phantom entry in
`calculator-dag.json` makes `tools/calculator-coverage.py` report one more
live generator than MOVES has, permanently unported and permanently
unportable. §4 is the arithmetic that follows from removing it.

## 3. Worked example — one row, by hand

`process-evap-fvv` selects source type 21, fuel types 1/2/5/9 and model years
1980-2020, for polProcessID **112** (Total Gaseous Hydrocarbons × Evap Fuel
Vapor Venting). The three tables are **125 rows each**: 41 model years × the
fuel types present, after step 1's `having sum(stmyFraction) > 0` has removed
the combinations no sample vehicle has.

The row `(21, 1980, 1, 112)` in `stmyTVVCoeffs2020`:

| column | stored |
|---|---|
| `backPurgeFactor` | 0.22689237019496156 |
| `averageCanisterCapacity` | 69.4023720596353 |
| `leakFraction` | 0.6253840119659445 |
| `leakFractionIM` | 0.4623647039687242 |
| `tankSize` | 17.73192472952221 |
| `tankFillFraction` | 0.3813317146133808 |

In `stmyTVVEquations2020` the same key appears with `regClassID` **20** and
the form pair `(T0, L9)`, carrying
`regClassFractionOfSourceTypeModelYearFuel` 0.953329286533452.

**That 0.953 is worth reading carefully, because the column name misdescribes
it.** It is not a fraction *of the fuel*. `SampleVehiclePopulation`'s
`stmyFraction` for source type 21 and model year 1980 is
`(fuel 1, regClass 20) = 0.953329286533452`,
`(fuel 2, regClass 20) = 0.046670713467`, and zero for fuels 5 and 9 —
summing to exactly 1 across all four fuels. So the denominator is the
source-type-model-year, and 0.953 is the share of all 1980 passenger cars
that are gasoline in regulatory class 20. The 4.7 % that is missing from the
"fuel" fraction is diesel, not an unmodelled regulatory class.

The seventeen digits are the section's own: these are `double` columns and
the snapshot's `moves-snapshot/v2` encoding stores the shortest decimal that
round-trips, so what is written above is the value and not a rounding of it.
That is what makes a **bit-exact** comparison possible below rather than a
tolerance.

## 4. What removing the phantom does to the coverage denominator

`tools/calculator-coverage.py` counts a `Generator`-kind module as live when
it subscribes directly or is chained from something. `NewTvvYearGenerator`'s
DAG entry has `"subscribes_directly": true`, so it counts, and it can never be
ported because there is nothing to port. Excluding it is not shrinking a
number to look better; it is removing a row that was never a module.

The honest statement is in `PLAN.md` and in
`docs/omd-generator-reachability.md`. This document is the evidence for the
one line of it that says the module does not exist.

## 5. Literals

| literal | value | where it comes from |
|---|---|---|
| `2020` | the run year | `##context.year##`, substituted by the calculator; it is the table-name suffix and the `year - ageID` origin |
| `112` | polProcessID | Total Gaseous Hydrocarbons × Evap Fuel Vapor Venting, the one process this fixture selects |
| `> 0` | the `having` | step 1 keeps only strictly positive fractions |

## 6. The reproduction

### 6.5 The reproduction script

```python
#!/usr/bin/env python3
"""Show that `NewTvvYearGenerator` is a SQL section, not a generator.

Reads, per snapshot: execution-trace.json, and — where the tables exist —
sampleVehiclePopulation, cumTVVCoeffs, pollutantProcessMappedModelYear,
ageCategory, runSpecSourceType and runSpecModelYear.

Compares against: regClassFractionOfSTMY<year>, stmyTVVEquations<year> and
stmyTVVCoeffs<year>, which are read only to be compared with.
"""
import collections
import glob
import json
import os
import re
import sys

import pyarrow.parquet as pq

# The columns the section carries through each of its two aggregations. Split
# because `regClassFractionOfSourceTypeModelYearFuel` is summed in the
# equations table and is NOT a column of the coefficients table.
WEIGHTED = ("backPurgeFactor", "averageCanisterCapacity",
            "leakFraction", "leakFractionIM", "tankSize", "tankFillFraction")


def tab(root, snap, name, columns=None):
    hits = sorted(glob.glob(
        f"{root}/{snap}/tables/db__movesexecution*__{name.lower()}.parquet"))
    if not hits:
        return None
    rows = []
    for h in hits:
        t = pq.ParquetFile(h).read(columns=columns).to_pydict()
        n = len(next(iter(t.values()))) if t else 0
        rows += [{k: t[k][i] for k in t} for i in range(n)]
    return rows


def num(x):
    return None if x is None else float(x)


def loaded_classes(root, snap):
    path = f"{root}/{snap}/execution-trace.json"
    if not os.path.isfile(path):
        return None
    trace = json.load(open(path))
    return {c["name"].rsplit(".", 1)[-1] for c in trace.get("java_classes", [])}


def new_tvv_year(root, snap, year):
    """The three tables `-- Section NewTVVYear` builds, from its four inputs."""
    svp = tab(root, snap, "samplevehiclepopulation")
    cum = tab(root, snap, "cumtvvcoeffs")
    ppmy = tab(root, snap, "pollutantprocessmappedmodelyear")
    age = tab(root, snap, "agecategory")
    if None in (svp, cum, ppmy, age):
        return None

    # `##macro.csv.all.sourceTypeID##` and `##macro.csv.all.modelYearID##` are
    # the RunSpec's own scope, which the execution database carries as tables.
    source_types = {r["sourceTypeID"] for r in tab(root, snap, "runspecsourcetype")}
    model_years = {r["modelYearID"] for r in tab(root, snap, "runspecmodelyear")}
    # `##pollutantProcessIDs##` is the calculator's own list. Taking it from
    # the reference would make the comparison circular, so it comes from the
    # RunSpec: TankVaporVentingCalculator owns process 12.
    pol_procs = {r["polProcessID"] for r in tab(root, snap, "runspecpollutantprocess")
                 if r["polProcessID"] % 100 == 12}

    # ---- regClassFractionOfSTMY<year> ------------------------------------
    # `group by sourceTypeModelYearID, fuelTypeID, regClassID having sum > 0`.
    # sourceTypeModelYearID is (sourceTypeID, modelYearID) composed, so the
    # group is the four-column key the primary key declares.
    fractions = collections.defaultdict(float)
    for r in svp:
        if r["sourceTypeID"] in source_types and r["modelYearID"] in model_years:
            fractions[(r["sourceTypeID"], r["modelYearID"],
                       r["fuelTypeID"], r["regClassID"])] += num(r["stmyFraction"])
    fractions = {k: v for k, v in fractions.items() if v > 0}

    # ---- stmyTVVEquations<year> ------------------------------------------
    ages_of_group = collections.defaultdict(list)
    for a in age:
        ages_of_group[a["ageGroupID"]].append(a["ageID"])
    years_of = collections.defaultdict(list)
    for p in ppmy:
        years_of[(p["polProcessID"], p["modelYearGroupID"])].append(p["modelYearID"])
    by_model_year = collections.defaultdict(list)
    for (st, my, ft, rc), frac in fractions.items():
        by_model_year[(my, rc)].append((st, ft, frac))

    equations = collections.defaultdict(lambda: collections.defaultdict(float))
    for c in cum:
        if c["polProcessID"] not in pol_procs:
            continue
        # `where ppmy.modelYearID = <year> - a.ageID`, with ageCategory joined
        # on the coefficient row's ageGroupID. A coefficient row therefore
        # applies to the model years its age group reaches back to.
        reachable = {year - aid for aid in ages_of_group.get(c["ageGroupID"], ())}
        for my in years_of.get((c["polProcessID"], c["modelYearGroupID"]), ()):
            if my not in reachable:
                continue
            for st, ft, frac in by_model_year.get((my, c["regClassID"]), ()):
                key = (st, my, ft, c["polProcessID"], c["regClassID"],
                       c["tvvEquation"], c["leakEquation"])
                row = equations[key]
                for col in WEIGHTED:
                    v = num(c.get(col))
                    if v is not None:
                        row[col] += v * frac
                row["regClassFractionOfSourceTypeModelYearFuel"] += frac

    # ---- stmyTVVCoeffs<year> ---------------------------------------------
    # The same rows again, with regClass and the two equation strings dropped
    # out of the key and summed over. That is the whole of the third statement.
    coeffs = collections.defaultdict(lambda: collections.defaultdict(float))
    for key, row in equations.items():
        for col in WEIGHTED:
            coeffs[key[:4]][col] += row.get(col, 0.0)
    return fractions, equations, coeffs


def compare(predicted, reference, key_of, columns):
    """(cells, exact, missing, extra) for one table, comparing bit-for-bit."""
    ref = {key_of(r): r for r in reference}
    missing = len(set(ref) - set(predicted))
    extra = len(set(predicted) - set(ref))
    cells = exact = 0
    for k in sorted(set(ref) & set(predicted), key=repr):
        for col in columns:
            stored = ref[k].get(col)
            if stored is None:
                continue
            cells += 1
            exact += predicted[k].get(col, 0.0) == float(stored) \
                if isinstance(predicted[k], dict) else predicted[k] == float(stored)
    return cells, exact, missing, extra


def main(root):
    snaps = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))

    traced = 0
    generator_loaded = []
    with_tables = []
    calculator_loaded = []
    cells = exact = missing = extra = 0
    tables_checked = 0

    for snap in snaps:
        classes = loaded_classes(root, snap)
        if classes is not None:
            traced += 1
            # THE CLAIM. If `NewTvvYearGenerator` were a generator, MOVES would
            # have to load a class by that name to run it.
            if any("NewTvvYear" in c or "NewTVVYear" in c for c in classes):
                generator_loaded.append(snap)

        years = sorted({int(m.group(1)) for m in
                        (re.search(r"__stmytvvcoeffs(\d{4})\.parquet$", p)
                         for p in glob.glob(f"{root}/{snap}/tables/"
                                            f"db__movesexecution*__stmytvvcoeffs*.parquet"))
                        if m})
        if not years:
            continue
        with_tables.append(snap)
        if classes and "TankVaporVentingCalculator" in classes:
            calculator_loaded.append(snap)

        for year in years:
            built = new_tvv_year(root, snap, year)
            if built is None:
                print(f"  {snap}: the section's inputs are not all present", file=sys.stderr)
                continue
            fractions, equations, coeffs = built
            tables_checked += 3

            c, e, m, x = compare(
                {k: {"regClassFractionOfSourceTypeModelYearFuel": v}
                 for k, v in fractions.items()},
                tab(root, snap, f"regclassfractionofstmy{year}"),
                lambda r: (r["sourceTypeID"], r["modelYearID"], r["fuelTypeID"], r["regClassID"]),
                ("regClassFractionOfSourceTypeModelYearFuel",))
            cells += c; exact += e; missing += m; extra += x
            print(f"  regClassFractionOfSTMY{year}  {len(fractions):4d} rows, "
                  f"{m} missing / {x} extra, {e} of {c} cells bit-exact")

            c, e, m, x = compare(
                equations, tab(root, snap, f"stmytvvequations{year}"),
                lambda r: (r["sourceTypeID"], r["modelYearID"], r["fuelTypeID"],
                           r["polProcessID"], r["regClassID"],
                           r["tvvEquation"], r["leakEquation"]),
                WEIGHTED + ("regClassFractionOfSourceTypeModelYearFuel",))
            cells += c; exact += e; missing += m; extra += x
            print(f"  stmyTVVEquations{year}       {len(equations):4d} rows, "
                  f"{m} missing / {x} extra, {e} of {c} cells bit-exact")

            c, e, m, x = compare(
                coeffs, tab(root, snap, f"stmytvvcoeffs{year}"),
                lambda r: (r["sourceTypeID"], r["modelYearID"],
                           r["fuelTypeID"], r["polProcessID"]),
                WEIGHTED)
            cells += c; exact += e; missing += m; extra += x
            print(f"  stmyTVVCoeffs{year}          {len(coeffs):4d} rows, "
                  f"{m} missing / {x} extra, {e} of {c} cells bit-exact")

    # ---- the DAG entry's own provenance ----------------------------------
    dag_path = os.path.join(os.path.dirname(root.rstrip("/")),
                            "calculator-chains", "calculator-dag.json")
    dag_entry = None
    if os.path.isfile(dag_path):
        for module in json.load(open(dag_path))["modules"]:
            if module["name"] == "NewTvvYearGenerator":
                dag_entry = module
                break

    print(f"  class-loaded as a generator  {len(generator_loaded)} of {traced} traced snapshots")
    print(f"  snapshots with the tables    {len(with_tables)} ({', '.join(with_tables) or 'none'})")
    print(f"  ...class-loading TankVaporVentingCalculator  {len(calculator_loaded)}")
    if dag_entry is not None:
        srcs = sorted({s.get("source") for s in dag_entry.get("subscriptions", [])})
        print(f"  calculator-dag.json entry    kind={dag_entry['kind']!r} "
              f"java_path={dag_entry['java_path']!r} "
              f"registrations={dag_entry['registrations_count']} source={srcs}")

    bad = []
    if generator_loaded:
        bad.append("a class named NewTvvYear* IS loaded in %s -- it is a generator after all"
                   % generator_loaded)
    if not with_tables:
        bad.append("no snapshot carries stmyTVVCoeffs<year>; the claim cannot be tested")
    if len(calculator_loaded) != len(with_tables):
        bad.append("%d of %d snapshots with the tables do not load TankVaporVentingCalculator"
                   % (len(with_tables) - len(calculator_loaded), len(with_tables)))
    if tables_checked < 3:
        bad.append("only %d of the section's 3 tables were checked" % tables_checked)
    if missing or extra:
        bad.append("key sets: %d missing, %d extra" % (missing, extra))
    if cells < 1750:
        bad.append("only %d value cells compared, expected >= 1750" % cells)
    if exact != cells:
        bad.append("%d of %d value cells are not bit-exact" % (cells - exact, cells))
    if dag_entry is None:
        bad.append("calculator-dag.json no longer carries a NewTvvYearGenerator module; "
                   "if it was removed, this oracle and the note it serves are done")
    else:
        if dag_entry["java_path"] != "":
            bad.append("the DAG entry now has a java_path (%r) -- a class was found for it"
                       % dag_entry["java_path"])
        if dag_entry["registrations_count"] != 0:
            bad.append("the DAG entry now registers %d pollutant-process pairs"
                       % dag_entry["registrations_count"])
    if bad:
        for b in bad:
            print("  FAIL: " + b, file=sys.stderr)
        sys.exit(1)


main(sys.argv[1])
```

### 6.6 What is asserted, and what would break it

The oracle asserts, over every snapshot in the corpus:

| assertion | measured |
|---|---|
| no snapshot class-loads a `NewTvvYear*` class | **0** of 43 traced |
| the tables exist somewhere | 1 snapshot, `process-evap-fvv` |
| every snapshot with the tables loads `TankVaporVentingCalculator` | 1 of 1 |
| the three tables' key sets | 0 missing / 0 extra |
| the three tables' values | **1,750 of 1,750 cells bit-exact** |
| the DAG entry still has no `java_path` and no registration | `''`, 0 |

The value comparison is `==` on the double, not a tolerance, and the row
counts are floors rather than equalities because the corpus is shared and it
grows (`docs/esm-conventions.md` §35.5).

**Three of those six are negatives, and they are the ones that make this a
disproof.** A document asserting only the table contents would keep passing
if someone found a `NewTvvYearGenerator.java` tomorrow; these fail. The DAG
assertions in particular fail if the hand-added entry is ever *corrected* into
a real one — at which point this note is wrong and should be deleted, which is
the outcome it is built to detect rather than survive.

## 7. Gaps

* **One snapshot, one year, one process.** `process-evap-fvv` is the only
  snapshot in the corpus that selects process 12, so it is the only one that
  runs the section. A second year would exercise the `<year> - ageID` join at
  a different origin; none exists.
* **`##pollutantProcessIDs##` is taken from the RunSpec, not from the
  calculator.** The Java hands the section its own pollutant-process list;
  §6.5 derives the same set from `runSpecPollutantProcess` filtered to process
  12. The two coincide here because the fixture selects one process. A run
  selecting several evaporative processes would tell them apart.
* **The section's `drop table if exists` and the table DDL are not modelled.**
  Only the three `INSERT ... SELECT` statements are, because only their output
  is in the snapshot.
* **BOTH AGGREGATIONS ARE OVER SINGLETON GROUPS, so neither `sum` is
  exercised, and the perturbation battery says so rather than the tally being
  reported as eight of eight.** Measured on `process-evap-fvv`: every one of
  the 125 step-3 groups has exactly **one** row, `stmyTVVEquations2020`
  carries a single `regClassID` (20) throughout, and
  `regClassFractionOfSTMY2020` has exactly one regulatory class per
  (sourceType, modelYear, fuelType). That is a consequence of the fixture
  selecting only passenger cars, which map to one regulatory class. Two of
  the eight probes in §6.5's battery therefore do NOT go red — replacing step
  2's `+=` with `=`, and replacing step 3's `+=` with `=` — because on
  singleton groups the two are the same function. The other six do. A RunSpec
  selecting a source type that spans regulatory classes, or several
  evaporative processes, would separate them; none exists.
* **This says nothing about whether the coefficients are *right*.** It says
  they are what the section computes from the inputs the snapshot carries. The
  arithmetic downstream of them is `docs/evap-fvv.md`'s.
