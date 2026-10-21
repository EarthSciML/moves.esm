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
chain's recomputation, and the KEYS actually present in the output -- and then
asserts the four counts the chain keeps of what it could not reach:

    rows == rateSurvivorCount x counties x months x day types
    distinct (pollutantID, processID, roadTypeID) == outputPolProcessCount
    distinct (yearID, sourceTypeID, fuelTypeID, modelYearID) == cohortSurvivorCount
    rateSurvivorCount <= outputPolProcessCount x cohortSurvivorCount
    run_sourceBinsDropped == 0
    run_physicsRowsDropped == 0
    run_rateRowsWithoutPhysics == 0
    run_chainDepthExceeded == 0
    run_offNetworkLinkCount == 0
    run_domainUnported == 0
    run_selectionUnported == 0

The last four lines are a different KIND of check from the four above them.
The first two declared numbers are extents: too small and the document emits
fewer rows than it computes, which the row count catches. The other two are
WIDTHS of a relation the output has no column for, and a width one short does
not lose a row -- it loses a term of one. A short `n_sourceBin` drops a source
bin out of the candidate grid and the cohort's emissionQuant is quietly LOW by
that bin's share; a short `n_physicsRow` drops a vehicle off the drive-cycle
axis and every rate row of its regulatory class collapses against no weights at
all, which is quietly ZERO. Nothing about the shape would notice either, so the
chain counts what it could not reach and this asserts the counts are zero.

`run_chainDepthExceeded` is a third kind again, and the one this file exists to
make cheap. A chained pollutant-process can itself be a parent -- THC to NMHC to
NMOG to TOG -- so the chain is a fixed point, and `onroad/model.esm` unrolls it
THREE times because three is the longest chain in the whole snapshot corpus
(lib/chaining.esm). A run needing a fourth would not be wrong: its deepest
species would be ZERO, which the row count above would report as missing rows
with no hint of why. So the model runs one extra PRESENCE pass -- a presence
pass carries no day, county or month, so it is nearly free -- and counts the
rows a fourth rung would newly emit. Zero means the unroll converged on THIS
run, which is a measurement and not the corpus-wide claim.

`run_offNetworkLinkCount` is a FOURTH kind, and it guards an identity rather
than a width. `TotalActivityGenerator` copies `SHO` into `SourceHours` row for
row at an on-network link and takes it from `SHP` -- a table this model does not
have -- at the off-network road type 1. The evaporative operating-mode
distribution divides the first by the second, so on every run here that ratio is
exactly 1 and the soaking modes are weighted exactly 0. An evaporative block on
road type 1 would not lose a row or emit a zero: it would divide `SHO` by a copy
of itself where MOVES divided it by something else, and every evaporative number
would be wrong by whatever the two differ by. Nothing downstream could see it,
so the model counts the evaporative blocks on road type 1 and this asserts there
are none. (Until PLAN.md §7.3.46 it counted counties whose one link was
off-network; with the road type an axis, road type 1 is a block of its own, and
running exhaust's off-network idle lives there legitimately.)

`run_rateRowsWithoutPhysics` is the same failure reached from the other side: a
rate row whose (source type, regulatory class, model year) matches no
`sourceusetypephysics` row at all, which is a gap in the table rather than a
short declaration. It is zero for every (source type, regulatory class) pair the
default database's `samplevehiclepopulation` carries, and a county database that
added a regulatory class would find out here rather than in a low number.

`run_domainUnported` is a FIFTH kind, and it guards the run's DOMAIN (PLAN.md
§7.3.40). A PROJECT-domain run takes its SHO from its links and its running
operating modes from the link's own drive-schedule blend, and the model does
that for one link in one county, for running exhaust, inside the drive
schedules' speed range. Every way past those limits -- two links on one road
type, a second county, brake wear or tire wear or a start or evaporative process
on a project, an out-of-bounds bracket MOVES itself refuses -- would emit a
plausible number rather than none, so the model counts them, together with a
DEFAULT-domain run that carries a linkSourceTypeHour row only ProjectTAG reads,
and this asserts the count is 0.

`run_selectionUnported` is a SIXTH kind, and it guards the run's SELECTION
rather than its domain (PLAN.md §7.3.41). Since PLAN.md §7.3.46 the road type is
an axis and running exhaust's off-network idle is computed, so what is left is
an evaporative process on a second on-network road type (its SourceHours are
per link in MOVES and summed here), an on-road pollutant-process other than
running exhaust beside road type 1 (evaporative SHP rows, which this model does
not write), a hotelling, start or off-network idle block in a run that
pre-aggregates time, and at Rates scale everything the RatePerDistance relation
does not compute (`run_ratesUnported`, PLAN.md 7.3.47); this asserts the count
is 0.

The pollutant-process key gained the road type at PLAN.md §7.3.46. An output
BLOCK is a (pollutant-process, road type) pair: `expand-roadtypes` emits running
energy on five road types and start energy on one, six blocks of two
(pollutantID, processID) pairs, ragged across the road type because a start
happens on road type 1 alone. `out_roadTypeID` is a key here even though the
comparator ignores it, because the SCC that carries it is compared.

The cohort key gained its source type at 7d, and the third line is what says so:
`runspecs/expand-fueltype-diesel.esm` emits 125 cohorts under source type 21 and
123 under 32, and (modelYearID, fuelTypeID) alone counts 164 of them -- the union
of two overlapping sets, which would match no declaration and hide the fact that
a per-source-type count is a SUM.

It gained the calendar year at PLAN.md §7.3.44 for the same reason. A cohort is
an AGE at a YEAR, so `runspecs/expand-multiyear.esm`'s 241 cohorts -- 116 at
2015 and 125 at 2020 -- share most of their model years, and (sourceTypeID,
fuelTypeID, modelYearID) alone counts 135 of them. The year is not a factor of
the row count: it is already in the pairs, because the cohort grid carries it.

The county, month and day-type factors are counted from the output's own key
columns rather than recomputed, because all three are runtime-discovered extents
of a runspec source and no declaration stands behind them to check. What they DO
catch is a level that collapsed: `runspecs/expand-counties.esm` emits three
counties, and a chain that summed them instead of selecting them emits one --
the 7c' defect one axis up. The month joined them at 7d, and it is the level
most likely to collapse silently, because `run_monthID` was a `run_rows` scalar
until then and a sum over one month is that month (conventions 65).

A RATES-scale run (PLAN.md 7.3.47) emits a different relation, RatePerDistance,
as `rpd_*` columns, and the prefix of the emitted header says which one this
is. The checks are the same with one more factor: every (pollutant-process,
cohort) pair is written at every speed bin, so

    rows == rateSurvivorCount x zones x months x day types x speed bins

and the table has no county column, so the geography level is the ZONE its
links are synthesized in, `floor(linkID / 1000)`. A link carries its bin in its
last two digits (`(zoneID*10 + roadTypeID)*100 + avgSpeedBinID`), and that is
asserted too: a rate at the right bin on the wrong link would pass every count.

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
    undeep = int(float(shape[0]["run_chainDepthExceeded"]))
    offnet = int(float(shape[0]["run_offNetworkLinkCount"]))
    unported = int(float(shape[0]["run_domainUnported"]))
    unselected = int(float(shape[0]["run_selectionUnported"]))

    header = list(rows[0]) if rows else []
    rate = any(c.startswith("rpd_") for c in header)
    pre = "rpd_" if rate else "out_"

    def distinct(*cols):
        return {tuple(r[pre + c] for c in cols) for r in rows}

    days = distinct("dayID")
    months = distinct("monthID")
    pairs = distinct("pollutantID", "processID", "roadTypeID")
    cohort_keys = distinct("yearID", "sourceTypeID", "fuelTypeID", "modelYearID")

    problems = []
    if rate:
        counties = {int(float(r["rpd_linkID"])) // 1000 for r in rows}
        bins = distinct("avgSpeedBinID")
        mislinked = [r for r in rows
                     if int(float(r["rpd_linkID"])) % 100 != int(float(r["rpd_avgSpeedBinID"]))]
        if mislinked:
            problems.append("%d rate row(s) sit on a link whose last two digits are not "
                            "their speed bin" % len(mislinked))
    else:
        counties = distinct("countyID")
        bins = {None}
    expected = pairs_emitted * len(counties) * len(months) * len(days) * len(bins)
    if len(rows) != expected:
        problems.append("%d rows, but the chain recomputes %d x %d x %d x %d%s = %d"
                        % (len(rows), pairs_emitted, len(counties), len(months),
                           len(days), " x %d speed bins" % len(bins) if rate else "",
                           expected))
    if pairs_emitted > blocks * cohorts:
        problems.append("%d (pollutant-process, cohort) pairs emit, which is MORE "
                        "than the %d blocks x %d cohorts they can be drawn from"
                        % (pairs_emitted, blocks, cohorts))
    if len(pairs) != blocks:
        problems.append("%d (pollutantID, processID, roadTypeID) blocks emitted, but "
                        "outputPolProcessCount is %d" % (len(pairs), blocks))
    if len(cohort_keys) != cohorts:
        problems.append("%d (yearID, sourceTypeID, fuelTypeID, modelYearID) cohorts "
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
    if undeep:
        problems.append("a fourth rung of the chain would newly emit %d rate "
                        "row(s): this run's chain is deeper than the three the "
                        "model unrolls, and its deepest species are emitting 0 "
                        "or not emitting at all" % undeep)
    if offnet:
        problems.append("%d evaporative block(s) of this run lie on the "
                        "OFF-NETWORK road type, where SourceHours is SHP and "
                        "not SHO: the evaporative fractionOfOperating is "
                        "dividing SHO by a copy of itself" % offnet)
    if unported:
        problems.append("%d thing(s) this run asks of its DOMAIN that the model "
                        "does not do (run_domainUnported): a runspecdomain that "
                        "is not one row, or in PROJECT domain a county without "
                        "exactly one link, a second county, an emitted process "
                        "other than running exhaust or an out-of-bounds bracket, "
                        "or outside it a linkSourceTypeHour row" % unported)
    if unselected:
        problems.append("%d thing(s) this run SELECTS that the model does not "
                        "compute (run_selectionUnported): an evaporative "
                        "process on a second on-network road type, an on-road "
                        "pollutant-process other than running exhaust beside the "
                        "off-network road type 1, or a hotelling, start or "
                        "off-network idle block in a run that aggregates hours "
                        "or day types, or at Rates scale anything but a directly "
                        "rated running-exhaust block on an on-network road type, "
                        "a PROJECT domain or any time aggregation "
                        "(run_ratesUnported)" % unselected)
    if problems:
        for p in problems:
            print(p)
        return 1

    ragged = pairs_emitted != blocks * cohorts
    print("%d rows = %d (pollutant-process, cohort) pair%s x %d %s x %d "
          "month(s) x %d day type(s)%s; %d block(s) and %d cohort(s), %s; no source "
          "bin and no vehicle dropped, and the chain converged in three rungs"
          % (len(rows), pairs_emitted, "" if pairs_emitted == 1 else "s",
             len(counties),
             ("zone" if len(counties) == 1 else "zones") if rate
             else ("county" if len(counties) == 1 else "counties"),
             len(months), len(days),
             " x %d speed bins, each on its own link" % len(bins) if rate else "",
             blocks, cohorts,
             "RAGGED -- a block is narrower than the widest" if ragged
             else "a rectangle"))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: check-runspec-shape.py <emitted.csv> <shape.csv>")
    sys.exit(main(sys.argv[1], sys.argv[2]))
