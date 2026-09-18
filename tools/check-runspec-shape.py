#!/usr/bin/env python3
"""Check a `runspecs/` document's emitted relation against the shape the chain
RECOMPUTES, rather than against the shape it was declared with.

Two numbers in `onroad/model.esm` are declared and not discovered, because no
table in the database states them -- MOVES works both out:

  n_outputCohort      how many (sourceTypeID, fuelTypeID, modelYearID) cohorts
                      reach MOVESOutput, recomputed as `cohortSurvivorCount`
  n_outputPolProcess  how many of the run's selected pollutant-processes reach
                      it at all, recomputed as `outputPolProcessCount` from
                      `rspp_isEmitted` -- MOVES's join to `runSpecRoadType`
  n_sourceBin         how many source bins the widest cohort holds, checked the
                      other way round by `run_sourceBinsDropped`

A declaration that disagrees with its recomputation is how a run would silently
emit the wrong number of rows, and for `runspecs/expand-day.esm` it is the ONLY
check that notices: its one surviving pollutant-process block is also its first,
so deleting the rule that discards the other two leaves every emitted number
where it was.

So this asserts the identity three ways at once -- the declared row count, the
chain's recomputation, and the KEYS actually present in the output:

    rows == outputPolProcessCount x counties x day types x cohortSurvivorCount
    distinct (pollutantID, processID) == outputPolProcessCount
    distinct (sourceTypeID, fuelTypeID, modelYearID) == cohortSurvivorCount
    run_sourceBinsDropped == 0

The last line is a different KIND of check from the three above it, and it is
the one 7e added. The other two declared numbers are extents: too small and the
document emits fewer rows than it computes, which the row count catches. A
`n_sourceBin` one short drops a whole source bin out of the candidate grid, and
a dropped bin is not a missing row -- it is a row whose emissionQuant is quietly
LOW by that bin's share. Nothing about the shape would notice, so the chain
counts the bins it could not reach and this asserts the count is zero.

The cohort key gained its source type at 7d, and the third line is what says so:
`runspecs/expand-fueltype-diesel.esm` emits 125 cohorts under source type 21 and
123 under 32, and (modelYearID, fuelTypeID) alone counts 164 of them -- the union
of two overlapping sets, which would match no declaration and hide the fact that
a per-source-type count is a SUM.

The county and day-type factors are counted from the output's own key columns
rather than recomputed, because both are runtime-discovered extents of a runspec
source and no declaration stands behind them to check. What they DO catch is a
county level that collapsed: `runspecs/expand-counties.esm` emits three counties,
and a chain that summed them instead of selecting them emits one -- the 7c'
defect one axis up.

usage: check-runspec-shape.py <emitted.csv> <shape.csv>
"""
import csv
import sys


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main(emitted_path, shape_path):
    rows = read(emitted_path)
    shape = read(shape_path)
    if len(shape) != 1:
        sys.exit("%s: expected one row of recomputed counts, got %d"
                 % (shape_path, len(shape)))
    blocks = int(float(shape[0]["outputPolProcessCount"]))
    cohorts = int(float(shape[0]["cohortSurvivorCount"]))
    dropped = int(float(shape[0]["run_sourceBinsDropped"]))

    def distinct(*cols):
        return {tuple(r[c] for c in cols) for r in rows}

    days = distinct("out_dayID")
    counties = distinct("out_countyID")
    pairs = distinct("out_pollutantID", "out_processID")
    cohort_keys = distinct("out_sourceTypeID", "out_fuelTypeID", "out_modelYearID")

    problems = []
    expected = blocks * len(counties) * len(days) * cohorts
    if len(rows) != expected:
        problems.append("%d rows, but the chain recomputes %d x %d x %d x %d = %d"
                        % (len(rows), blocks, len(counties), len(days), cohorts,
                           expected))
    if len(pairs) != blocks:
        problems.append("%d (pollutantID, processID) pairs emitted, but "
                        "outputPolProcessCount is %d" % (len(pairs), blocks))
    if len(cohort_keys) != cohorts:
        problems.append("%d (sourceTypeID, fuelTypeID, modelYearID) cohorts "
                        "emitted, but cohortSurvivorCount is %d"
                        % (len(cohort_keys), cohorts))
    if dropped:
        problems.append("%d source bin(s) of a selected cohort fall past slot "
                        "n_sourceBin and are not in the candidate grid: this "
                        "run's emissionQuant is low by their share, and "
                        "nothing else here would say so" % dropped)
    if problems:
        for p in problems:
            print(p)
        return 1

    print("%d rows = %d pollutant-process block(s) x %d count%s x %d day type(s) "
          "x %d cohorts, no source bin dropped"
          % (len(rows), blocks, len(counties), "y" if len(counties) == 1 else "ies",
             len(days), cohorts))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: check-runspec-shape.py <emitted.csv> <shape.csv>")
    sys.exit(main(sys.argv[1], sys.argv[2]))
