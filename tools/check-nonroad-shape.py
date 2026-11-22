#!/usr/bin/env python3
"""Check a `runspecs/nonroad/` document's emitted relation against the shape the
chain RECOMPUTES, rather than against the shape it was declared with.

Four numbers in `nonroad/model.esm` are declared and not discovered, because no
table in the database states them -- NONROAD works them out at run time:

  n_equipmentPoint   how many `nrsourceusetype` rows are equipment points of
                     this run (SCC in the /SOURCE CATEGORY/ packet, county
                     population positive), recomputed as
                     `run_equipmentPointsSelected` and checked the other way
                     round by `run_equipmentPointsDropped`
  n_outputCohort     how many (SCC, model year) cohorts reach MOVESOutput,
                     recomputed as `run_outputCohortCount`
  n_outputPolProcess how many of the selected pollutant-processes NONROAD
                     EMITS -- `nr-pleasure-craft-state` selects benzene at
                     three permeation processes and gets no row for any --
                     recomputed as `run_outputPolProcessCount`
  n_foldYear         how many years agedist.f's fold runs, checked by
                     `run_extraScopeRows` together with the one-row scope

Each fails differently when it is wrong, which is why all four are checked and
not just the row count. A SHORT `n_equipmentPoint` loses the points past it --
whole SCCs, or some of an SCC's hp bins, which is quietly LOW rather than
missing. A LONG one leaves point slots whose source type gathers as 0; those
slots are not inert, because a zero-population, zero-SCC point still fills age
slots, and they came back as owners of twenty spurious cohorts the first time it
happened (a probe run of `nr-lawn-garden-county` at 150 slots for its 97
points). A wrong `n_outputCohort` shows up in the emitted keys: too long and the
slots past the last owner carry SCC 0, too short and real cohorts are cut.

    rows == n_outputCohort x n_outputPolProcess, no key repeated
    distinct pollutants == run_outputPolProcessCount == n_outputPolProcess
    no emitted row has SCC 0 or a missing SCC
    distinct (SCC, modelYearID) == run_outputCohortCount == n_outputCohort
    run_equipmentPointsSelected == n_equipmentPoint
    run_equipmentPointsDropped == 0
    run_extraScopeRows == 0
    run_mixSetsOffOne == 0
    run_retrofitUnported == 0
    run_polProcessUnported == 0
    run_outputSettingUnported == 0

`run_mixSetsOffOne` is not a declared number but a guard the renormalization
would otherwise hide: NONROAD divides every technology set by its sum
(`rdtech_moves.f`), so a cohort that had read a second hp bin's set -- or none
-- would still come out as a mix summing to 1. It counts populated cohorts
whose LISTED mix misses 1 by more than the Fortran's own 0.002.

`run_retrofitUnported` is a refusal rather than a shape: the nrretrofitfactors
rows (NONROAD's /RETROFIT/ packet) the model does not apply as MOVES does
(PLAN.md §7.3.84). A run with one would otherwise emit a wrong inventory
without a sound.

`run_polProcessUnported` and `run_outputSettingUnported` are refusals too
(PLAN.md §7.3.86): selected pollutant-processes MOVES writes for NONROAD and
the model does not compute (crankcase, the evaporative and refueling
processes, CO2 and NH3 at running exhaust), and output settings -- breakdown,
geographic detail, mass unit -- the model does not emit.
`run_activityOutputRows` is REPORTED, not asserted: MOVES writes a
MOVESActivityOutput for every NONROAD run, and the model emits none.

usage: check-nonroad-shape.py <runspec.esm> <emitted.csv> <shape.csv>
"""
import csv
import json
import math
import sys


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main(doc_path, emitted_path, shape_path):
    doc = json.load(open(doc_path))
    bindings = next(iter(doc["models"].values())).get("bindings", {})
    try:
        points = int(bindings["n_equipmentPoint"])
        cohorts = int(bindings["n_outputCohort"])
        pps = int(bindings["n_outputPolProcess"])
    except KeyError as e:
        sys.exit("%s: binds no %s -- every nonroad RunSpec declares all three of its numbers" % (doc_path, e))
    rows = read(emitted_path)
    shape = read(shape_path)
    if len(shape) != 1:
        sys.exit("%s: expected one row of recomputed counts, got %d" % (shape_path, len(shape)))
    s = {k: float(v) for k, v in shape[0].items() if k != "i1"}
    errors = []

    def scc(r):
        v = float(r["out_SCC"])
        return None if math.isnan(v) or v == 0 else int(v)

    empty = [r for r in rows if scc(r) is None]
    if empty:
        errors.append("%d emitted row(s) carry no SCC -- output slots past the last owning cohort, so n_outputCohort=%d is "
                      "longer than the chain's %d" % (len(empty), cohorts, int(s["run_outputCohortCount"])))
    keys = [(scc(r), int(float(r["out_modelYearID"])), int(float(r["out_pollutantID"]))) for r in rows if scc(r)]
    if len(set(keys)) != len(keys):
        errors.append("%d emitted key(s) repeat" % (len(keys) - len(set(keys))))
    pollutants = {k[2] for k in keys}
    distinct_cohorts = {k[:2] for k in keys}
    if len(rows) != cohorts * pps:
        errors.append("rows %d != n_outputCohort %d x n_outputPolProcess %d" % (len(rows), cohorts, pps))
    if not (len(pollutants) == int(s["run_outputPolProcessCount"]) == pps):
        errors.append("pollutants: %d distinct emitted, %d recomputed, %d declared" %
                      (len(pollutants), int(s["run_outputPolProcessCount"]), pps))
    if not (len(distinct_cohorts) == int(s["run_outputCohortCount"]) == cohorts):
        errors.append("cohorts: %d distinct emitted, %d recomputed, %d declared" %
                      (len(distinct_cohorts), int(s["run_outputCohortCount"]), cohorts))
    if int(s["run_equipmentPointsSelected"]) != points:
        errors.append("equipment points: %d recomputed, %d declared" % (int(s["run_equipmentPointsSelected"]), points))
    for k in ("run_equipmentPointsDropped", "run_extraScopeRows", "run_mixSetsOffOne",
              "run_retrofitUnported", "run_polProcessUnported", "run_outputSettingUnported"):
        if s[k] != 0:
            errors.append("%s = %g, expected 0" % (k, s[k]))
    if errors:
        sys.exit("; ".join(errors))
    print("%d points, %d cohorts x %d pollutants = %d rows, all recomputed; MOVESActivityOutput rows not "
          "emitted (reported): %d" % (points, cohorts, len(pollutants), len(rows), int(s["run_activityOutputRows"])))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
