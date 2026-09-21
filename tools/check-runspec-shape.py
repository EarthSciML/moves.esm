#!/usr/bin/env python3
"""Check a `runspecs/` document's emitted relation against the shape the chain
RECOMPUTES, rather than against the shape it was declared with.

Four numbers in `onroad/model.esm` are declared and not discovered, because no
table in the database states them -- MOVES works them all out at run time:

  n_outputRate        how many (pollutant-process, cohort) PAIRS reach
                      MOVESOutput, recomputed as `rateSurvivorCount`. It is ONE
                      number where there used to be two, because two could only
                      describe a rectangle: a chained block is narrower than its
                      parent wherever its ratio table is (PLAN.md 7.3.16). The
                      two factors are still reported separately, as
                      `outputPolProcessCount` and `cohortSurvivorCount`, and
                      this says whether their product is the answer
  n_sourceBin         how many source bins the widest cohort holds, checked the
                      other way round by `run_sourceBinsDropped`
  n_physicsRow        how many `sourceusetypephysics` rows the run's source
                      types select -- the width of the drive-cycle axis --
                      recomputed as `run_physicsRowsSelected` and checked the
                      other way round by `run_physicsRowsDropped`

A declaration that disagrees with its recomputation is how a run would silently
emit the wrong number of rows, and for `runspecs/expand-day.esm` it is the ONLY
check that notices: its one surviving pollutant-process block is also its first,
so deleting the rule that discards the other two leaves every emitted number
where it was.

So this asserts the identity three ways at once -- the declared row count, the
chain's recomputation, and the KEYS actually present in the output:

    rows == rateSurvivorCount x counties x months x day types
    distinct (pollutantID, processID) == outputPolProcessCount
    distinct (sourceTypeID, fuelTypeID, modelYearID) == cohortSurvivorCount
    rateSurvivorCount <= outputPolProcessCount x cohortSurvivorCount
    run_sourceBinsDropped == 0
    run_physicsRowsDropped == 0
    run_rateRowsWithoutPhysics == 0

The last three lines are a different KIND of check from the three above them.
The first two declared numbers are extents: too small and the document emits
fewer rows than it computes, which the row count catches. The other two are
WIDTHS of a relation the output has no column for, and a width one short does
not lose a row -- it loses a term of one. A short `n_sourceBin` drops a source
bin out of the candidate grid and the cohort's emissionQuant is quietly LOW by
that bin's share; a short `n_physicsRow` drops a vehicle off the drive-cycle
axis and every rate row of its regulatory class collapses against no weights at
all, which is quietly ZERO. Nothing about the shape would notice either, so the
chain counts what it could not reach and this asserts the counts are zero.

`run_rateRowsWithoutPhysics` is the same failure reached from the other side: a
rate row whose (source type, regulatory class, model year) matches no
`sourceusetypephysics` row at all, which is a gap in the table rather than a
short declaration. It is zero for every (source type, regulatory class) pair the
default database's `samplevehiclepopulation` carries, and a county database that
added a regulatory class would find out here rather than in a low number.

The cohort key gained its source type at 7d, and the third line is what says so:
`runspecs/expand-fueltype-diesel.esm` emits 125 cohorts under source type 21 and
123 under 32, and (modelYearID, fuelTypeID) alone counts 164 of them -- the union
of two overlapping sets, which would match no declaration and hide the fact that
a per-source-type count is a SUM.

The county, month and day-type factors are counted from the output's own key
columns rather than recomputed, because all three are runtime-discovered extents
of a runspec source and no declaration stands behind them to check. What they DO
catch is a level that collapsed: `runspecs/expand-counties.esm` emits three
counties, and a chain that summed them instead of selecting them emits one --
the 7c' defect one axis up. The month joined them at 7d, and it is the level
most likely to collapse silently, because `run_monthID` was a `run_rows` scalar
until then and a sum over one month is that month (conventions 65).

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
    pairs_emitted = int(float(shape[0]["rateSurvivorCount"]))
    dropped = int(float(shape[0]["run_sourceBinsDropped"]))
    vehicleless = int(float(shape[0]["run_physicsRowsDropped"]))
    unphysical = int(float(shape[0]["run_rateRowsWithoutPhysics"]))

    def distinct(*cols):
        return {tuple(r[c] for c in cols) for r in rows}

    days = distinct("out_dayID")
    months = distinct("out_monthID")
    counties = distinct("out_countyID")
    pairs = distinct("out_pollutantID", "out_processID")
    cohort_keys = distinct("out_sourceTypeID", "out_fuelTypeID", "out_modelYearID")

    problems = []
    expected = pairs_emitted * len(counties) * len(months) * len(days)
    if len(rows) != expected:
        problems.append("%d rows, but the chain recomputes %d x %d x %d x %d = %d"
                        % (len(rows), pairs_emitted, len(counties), len(months),
                           len(days), expected))
    if pairs_emitted > blocks * cohorts:
        problems.append("%d (pollutant-process, cohort) pairs emit, which is MORE "
                        "than the %d blocks x %d cohorts they can be drawn from"
                        % (pairs_emitted, blocks, cohorts))
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
    if vehicleless:
        problems.append("%d selected physics row(s) fall past n_physicsRow and "
                        "are not on the drive-cycle axis: every rate row of "
                        "their regulatory class weights its operating modes "
                        "against nothing and emits 0" % vehicleless)
    if unphysical:
        problems.append("%d selected rate row(s) match no sourceusetypephysics "
                        "row at all, so they have no drive cycle and emit 0"
                        % unphysical)
    if problems:
        for p in problems:
            print(p)
        return 1

    ragged = pairs_emitted != blocks * cohorts
    print("%d rows = %d (pollutant-process, cohort) pair%s x %d count%s x %d "
          "month(s) x %d day type(s); %d block(s) and %d cohort(s), %s; no source "
          "bin and no vehicle dropped"
          % (len(rows), pairs_emitted, "" if pairs_emitted == 1 else "s",
             len(counties), "y" if len(counties) == 1 else "ies",
             len(months), len(days), blocks, cohorts,
             "RAGGED -- a block is narrower than the widest" if ragged
             else "a rectangle"))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: check-runspec-shape.py <emitted.csv> <shape.csv>")
    sys.exit(main(sys.argv[1], sys.argv[2]))
