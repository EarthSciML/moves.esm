#!/usr/bin/env python3
"""Check a `runspecs/` document's emitted relation against the shape the chain
RECOMPUTES, rather than against the shape it was declared with.

Two numbers in `onroad/model.esm` are declared and not discovered, because no
table in the database states them -- MOVES works both out:

  n_outputCohort      how many (modelYearID, fuelTypeID) cohorts reach
                      MOVESOutput, recomputed as `cohortSurvivorCount`
  n_outputPolProcess  how many of the run's selected pollutant-processes reach
                      it at all, recomputed as `outputPolProcessCount` from
                      `rspp_isEmitted` -- MOVES's join to `runSpecRoadType`

A declaration that disagrees with its recomputation is how a run would silently
emit the wrong number of rows, and for `runspecs/expand-day.esm` it is the ONLY
check that notices: its one surviving pollutant-process block is also its first,
so deleting the rule that discards the other two leaves every emitted number
where it was.

So this asserts the identity three ways at once -- the declared row count, the
chain's recomputation, and the KEYS actually present in the output:

    rows == outputPolProcessCount x cohortSurvivorCount x day types
    distinct (pollutantID, processID) == outputPolProcessCount
    distinct (modelYearID, fuelTypeID) == cohortSurvivorCount

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

    def distinct(*cols):
        return {tuple(r[c] for c in cols) for r in rows}

    days = distinct("out_dayID")
    pairs = distinct("out_pollutantID", "out_processID")
    cohort_keys = distinct("out_modelYearID", "out_fuelTypeID")

    problems = []
    if len(rows) != blocks * cohorts * len(days):
        problems.append("%d rows, but the chain recomputes %d x %d x %d = %d"
                        % (len(rows), blocks, cohorts, len(days),
                           blocks * cohorts * len(days)))
    if len(pairs) != blocks:
        problems.append("%d (pollutantID, processID) pairs emitted, but "
                        "outputPolProcessCount is %d" % (len(pairs), blocks))
    if len(cohort_keys) != cohorts:
        problems.append("%d (modelYearID, fuelTypeID) cohorts emitted, but "
                        "cohortSurvivorCount is %d" % (len(cohort_keys), cohorts))
    if problems:
        for p in problems:
            print(p)
        return 1

    print("%d rows = %d pollutant-process block(s) x %d cohorts x %d day type(s)"
          % (len(rows), blocks, cohorts, len(days)))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: check-runspec-shape.py <emitted.csv> <shape.csv>")
    sys.exit(main(sys.argv[1], sys.argv[2]))
