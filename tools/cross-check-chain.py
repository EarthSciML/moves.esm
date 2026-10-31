#!/usr/bin/env python3
"""Check that the two independently authored NONROAD chains agree.

`runs/nr_logging_county_run.esm` mounts the components and recomputes
docs/nonroad-logging-county.md §6.1's four model-year-2020 rows from leaves.
`fixtures/nr-logging-county.esm` computes the same four rows from the snapshot
Parquet. They are separate documents with separate equations, and until this
check nothing compared them -- each passed its own gate against its own
transcribed numbers, at tolerances far tighter than the gap between them.

TWO THINGS NOW SEPARATE THE ROUTES, AND THEY ARE NOT THE SAME KIND OF THING.
This script used to bound the pair at ONE ULP of binary32, measured: three rows
agreed bit-exactly and one differed by exactly one ulp, which is per-operation
rounding versus a single final cast. That was right while both routes used the
SAME grown model-year fraction -- the fixture carried `agedist.f`'s real*4
result as a `const` and so did the assembly's stage-2c leaf.

BOTH ROUTES NOW COMPUTE IT, and they still do not agree, for the reason set out
below: the fixture computes it in the `Float32` it declares, the assembly in
binary64. The fixture's answer is bit-identical to the real*4 constant it used
to carry, which is the evidence that changing where the number comes from
changed nothing else.

The leaf now COMPUTES the fold (esm-spec §4.3.1.1), in the binary64 the assembly
evaluates in, and for this equipment point the fold's answer depends on the
precision: `age_percentScrapped` reaches exactly 100 at age 3, so the age-3
survival is exactly 0 in binary64 and 5.96e-08 in real*4, and thirty iterations
of an unclamped residual amplify that into a 5.3e-07 disagreement on
`modfrc[2020]`. So the routes differ by

  (a) per-operation rounding versus a final cast   -- <= 1 ulp of binary32; and
  (b) ONE INPUT: the grown model-year fraction, 3.707270451304289 computed in
      binary64 against 3.707268476486206 computed in binary32 -- about 8 ulps,
      and NOT rounding. It is a cancellation residue amplified thirty times.

RAISING THE BOUND TO 8 ULPS WOULD BE THE WRONG FIX, and it was considered. It
would absorb (b) into the tolerance and with it any future divergence of the
same size arising for a completely different reason, which is the one thing this
gate exists to catch. So (b) is DIVIDED OUT instead: each route's four rows are
normalised by ITS OWN `modfrc[2020]`, read out of the document that owns it, and
the normalised rows are then held to the original one-ulp bound. Measured after
normalising: three rows bit-exact and one at exactly one ulp -- the same picture
as before the leaf started computing the fold, which is the evidence that (b) is
the whole of the difference.

A THIRD DIFFERENCE APPEARED ON 2026-10-30, when the fixture stopped carrying its
own copy of the chain and became a catalogue mounting nonroad/model.esm
(conventions §106). The domain model ports NONROAD's printed-decimal month
allocation -- each month fraction rounded to three places and renormalised by
the printed sum, f32(1/12) exactly -- and the components the assembly mounts
read the table's raw 0.0833333. That is (c), one INPUT again, 3.58e-07
relative, so it is divided out the same way as (b) and its size held
two-sidedly; the extra binary32 product it leaves inside the fixture's rows is
why the row bound is 2 ulps rather than 1. The components could take the
printed-decimal rule too; until they do, this is the recorded account.

The size of (b) is asserted separately, two-sidedly, so it cannot drift
unnoticed: it must be LARGER than one binary32 ulp (below that the two routes
would be using the same fold again and the normalisation would be dead weight
hiding nothing) and no larger than sixteen (twice the measured 8.18; beyond that
it is not the recorded amplification any more). Both edges name what they mean
rather than being fitted.

What this catches that nothing else does: an arithmetic divergence between the
two chains. What it deliberately accounts for: the precision difference, and the
one grown fraction the two routes get from different places. What it does NOT
catch: both chains being wrong in the same way -- that is what run-oracle.sh's
third implementation is for.
"""
import csv, json, math, os, struct, subprocess, sys, tempfile

ASSEMBLY = "runs/nr_logging_county_run.esm"
LEAF = "components/age_distribution.esm"
FIXTURE = "fixtures/nr-logging-county.esm"
TEST_ID = "the_chain_reproduces_the_worked_examples_2020_rows"
LEAF_TEST_ID = "the_grown_fractions_sum_to_the_cumulative_growth_ratio"
ACTIVITY_TEST_ID = "the_activity_stage_supplies_what_the_rollup_multiplies"
MODEL_YEAR = "2020"
# The fixture computes six equipment points over three SCCs; the assembly
# computes one. This names the one they share.
FIXTURE_SCC = "2260007005"
# The binary run-tests.sh is testing, so the fixture's number is its own.
ESM = os.environ.get("ESM", "./esm")
# One ulp of per-operation rounding against a final cast, plus one for the
# month-day factor: since difference (c) is divided out, it is one more binary32
# product inside the fixture's rows than inside the normalisation. Measured with
# both divided out: two rows bit-exact, one at 1 ulp, one at 2.
MAX_ULPS = 2.0
# The recorded size of difference (b), in ulps of binary32, two-sided. Measured
# 8.18; see the module docstring for what each edge means.
FOLD_GAP_ULPS_MIN = 1.0
FOLD_GAP_ULPS_MAX = 16.0
# The recorded size of difference (c), the month-day factor, in ulps of
# binary32, two-sided: measured 4.34 (the month fraction alone is 3.58e-07
# relative); the upper edge is twice that, as for (b). See main().
MONTH_GAP_ULPS_MIN = 1.0
MONTH_GAP_ULPS_MAX = 9.0


def f32(x):
    return struct.unpack("f", struct.pack("f", x))[0]


def ulp32(x):
    """The spacing of binary32 at x. Normal magnitudes only, which these are."""
    if x == 0.0:
        return 2.0 ** -149
    return 2.0 ** (math.frexp(abs(x))[1] - 1 - 23)


def assembly_values():
    doc = json.load(open(ASSEMBLY))
    tests = doc["models"]["Chain"]["tests"]
    hit = [t for t in tests if t["id"] == TEST_ID]
    if len(hit) != 1:
        sys.exit(f"{ASSEMBLY}: expected exactly one test '{TEST_ID}', found {len(hit)}")
    return [a["expected"] for a in hit[0]["assertions"]]


def assembly_grown_fraction():
    """`modfrc[2020]` as the assembly's stage-2c leaf computes it, in binary64.

    Read from the leaf's own assertion rather than hardcoded, for the same
    reason the four row values above are: a number this script restated would
    stop tracking the document the day the document moved.
    """
    doc = json.load(open(LEAF))
    tests = doc["models"]["AgeDistribution"]["tests"]
    hit = [t for t in tests if t["id"] == LEAF_TEST_ID]
    if len(hit) != 1:
        sys.exit(f"{LEAF}: expected exactly one test '{LEAF_TEST_ID}', found {len(hit)}")
    got = [a["expected"] for a in hit[0]["assertions"]
           if a["variable"] == "age_grownModelYearFraction"
           and a.get("coords", {}).get("age_rows") == 1]
    if len(got) != 1:
        sys.exit(f"{LEAF}: expected one age_grownModelYearFraction[1] assertion in "
                 f"'{LEAF_TEST_ID}', found {len(got)}")
    return got[0]


def assembly_month_day_factor():
    """The assembly's month-day factor, read from its own assertion."""
    doc = json.load(open(ASSEMBLY))
    hit = [t for t in doc["models"]["Chain"]["tests"] if t["id"] == ACTIVITY_TEST_ID]
    got = [a["expected"] for t in hit for a in t["assertions"] if a["variable"] == "chainMonthDayFactor"]
    if len(got) != 1:
        sys.exit(f"{ASSEMBLY}: expected one chainMonthDayFactor assertion in '{ACTIVITY_TEST_ID}', found {len(got)}")
    return got[0]


def emit(variable):
    """One variable of the fixture, as the binary under test computes it."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        out = tmp.name
    try:
        subprocess.run([ESM, "simulate", FIXTURE, "--time", "0", "--format", "csv",
                        "--observed", variable, "--output", out],
                       check=True, capture_output=True)
        return list(csv.DictReader(open(out)))
    finally:
        os.unlink(out)


def fixture_point():
    """The fixture's equipment point for FIXTURE_SCC, chosen by SCC, not position."""
    points = [r["i1"] for r in emit("point_SCC") if r["point_SCC"] == FIXTURE_SCC]
    if len(points) != 1:
        sys.exit(f"{FIXTURE}: expected one equipment point with SCC {FIXTURE_SCC}, found {len(points)}")
    return points[0]


def fixture_month_day_factor(point):
    got = [float(r["point_monthDayFactor"]) for r in emit("point_monthDayFactor") if r["i1"] == point]
    if len(got) != 1:
        sys.exit(f"{FIXTURE}: expected one point_monthDayFactor[{point}], found {len(got)}")
    return got[0]


def fixture_grown_fraction(point):
    """`modfrc[2020]` as the fixture COMPUTES it, in the binary32 it declares.

    This used to read a `const`, and to exit telling its reader to delete the
    normalisation the day the fixture stopped carrying the fold. That day came,
    and the instruction was WRONG -- kept here because the reasoning is the
    useful part. It assumed "not carried any more" meant "both routes agree on
    the fold again". They do not. The fixture computes it in `Float32` and the
    assembly in binary64, and this script's own docstring says why those cannot
    agree: the age-3 survival is exactly 0 in binary64 and 5.96e-08 in real*4,
    and thirty unclamped iterations amplify the difference. So difference (b)
    survives at the size it always had; what changed is its NAME. It was
    "computed against transcribed", and it is now "computed against computed at
    another precision" -- the mechanism the docstring already predicted rather
    than a new one, so the normalisation is still exactly the right treatment.

    SINCE 2026-10-30 THE FIXTURE CARRIES NO ASSERTIONS -- it is a catalogue
    mounting nonroad/model.esm, and a mounted model's tests do not run (F47) --
    so the number is EMITTED from it rather than read from a test. That is the
    stronger reading: it is what the fixture computes today, not what someone
    transcribed. The equipment point is chosen by its SCC, not by position.
    """
    got = [float(r["slot_grownModelYearFraction"]) for r in emit("slot_grownModelYearFraction")
           if r["i1"] == point and r["i2"] == "1"]
    if len(got) != 1:
        sys.exit(f"{FIXTURE}: expected one slot_grownModelYearFraction[{point}, 1], found {len(got)}")
    return got[0]

def fixture_values(csv_path):
    """The fixture's four rows for the SCC the assembly computes.

    THE SCC FILTER IS NOT DECORATION. The assembly recomputes SS6.1's SCC and
    nothing else; the fixture now emits all three, so model year 2020 alone is
    twelve rows and an unfiltered read would hand four of another SCC's rows to
    a comparison that pairs by sorted position. It would not pass -- the row
    count check below catches it -- but it would fail for the wrong reason, and
    a gate that fails for the wrong reason teaches its reader the wrong thing.
    """
    rows = [r for r in csv.DictReader(open(csv_path))
            if r["modelYearID"] == MODEL_YEAR and r["SCC"] == FIXTURE_SCC]
    if not rows:
        sys.exit(f"{csv_path}: no rows for SCC {FIXTURE_SCC} model year {MODEL_YEAR}")
    return [float(r["emissionQuant"]) for r in rows]


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: cross-check-chain.py <fixture actual .csv>")

    point = fixture_point()
    a_mod, f_mod = assembly_grown_fraction(), fixture_grown_fraction(point)
    a_mdf, f_mdf = assembly_month_day_factor(), fixture_month_day_factor(point)
    gap_ulps = abs(a_mod - f_mod) / ulp32(f_mod)
    gap_rel = abs(a_mod - f_mod) / abs(f_mod)
    print(f"  modfrc[2020]: assembly (binary64 fold) {a_mod!r}")
    print(f"                fixture  (binary32 fold)  {f_mod!r}")
    print(f"                differ by {gap_rel:.3e} relative = {gap_ulps:.2f} ulps of binary32")
    if gap_ulps < FOLD_GAP_ULPS_MIN:
        print(f"FAIL: the two routes' grown fractions now differ by {gap_ulps:.2f} ulps, less "
              f"than one. That is rounding, not the recorded 5.3e-07 amplification, so the two "
              f"routes are using the same fold and the normalisation below divides by two equal "
              f"numbers -- it would hide a real divergence rather than isolate a known one. "
              f"Delete it and restore the plain comparison.")
        return 1
    if gap_ulps > FOLD_GAP_ULPS_MAX:
        print(f"FAIL: the two routes' grown fractions differ by {gap_ulps:.2f} ulps, more than "
              f"the {FOLD_GAP_ULPS_MAX:.0f} recorded. One of the two folds -- the assembly's in "
              f"binary64 or the fixture's in binary32 -- has moved by more than the age-3 "
              f"cancellation residue explains, and this "
              f"script's account of WHY the routes differ is no longer true.")
        return 1

    # Difference (c): the month-day factor. The fixture mounts nonroad/model.esm,
    # which ports NONROAD's PRINTED-DECIMAL month allocation -- each fraction
    # rounded to three places and renormalised by their printed sum, which gives
    # f32(1/12) = 0.0833333283662796 -- where the components the assembly mounts
    # read the table's raw 0.0833333. Measured 3.58e-07 relative, 3 ulps of
    # binary32. It is one input, not arithmetic, so like (b) it is divided out
    # and its size is held two-sidedly.
    mdf_ulps = abs(a_mdf - f_mdf) / ulp32(f_mdf)
    print(f"  month-day factor: assembly {a_mdf!r}, fixture {f_mdf!r}: {mdf_ulps:.2f} ulps of binary32")
    if not (MONTH_GAP_ULPS_MIN <= mdf_ulps <= MONTH_GAP_ULPS_MAX):
        print(f"FAIL: the month-day factors differ by {mdf_ulps:.2f} ulps, outside the recorded "
              f"[{MONTH_GAP_ULPS_MIN:.0f}, {MONTH_GAP_ULPS_MAX:.0f}]. Below it the two routes read "
              f"the month allocation the same way again and this normalisation hides nothing; "
              f"above it the printed-decimal account is no longer the whole difference.")
        return 1

    # Difference (b) divided out: each route by its own grown fraction. Division
    # by a positive number preserves order, so the sorted pairing below is the
    # same pairing it would have been on the raw values.
    a = sorted(f32(v / (a_mod * a_mdf)) for v in assembly_values())
    b = sorted(f32(v / (f_mod * f_mdf)) for v in fixture_values(sys.argv[1]))

    if len(a) != len(b):
        print(f"FAIL: assembly asserts {len(a)} rows for {MODEL_YEAR}, fixture emitted {len(b)}")
        return 1

    # The comparison is by sorted position, so it is only meaningful if the
    # values are far enough apart that sorting cannot pair the wrong two. Assert
    # that rather than assume it: a future fixture whose rows crowd together
    # must fail here loudly instead of comparing mismatched pairs quietly.
    for i in range(len(a) - 1):
        gap = a[i + 1] - a[i]
        if gap <= MAX_ULPS * ulp32(a[i + 1]) * 2:
            print(f"FAIL: normalised values {a[i]!r} and {a[i+1]!r} are closer than the "
                  f"tolerance, so a sorted comparison cannot pair them safely")
            return 1

    bad = 0
    print()
    print(f"  each row divided by its own route's modfrc[2020] x month-day factor:")
    print(f"  {'assembly / 3.7072705':>22} {'fixture / 3.7072685':>22} {'ulps':>7}")
    for x, y in zip(a, b):
        n = abs(y - x) / ulp32(x)
        flag = "" if n <= MAX_ULPS else "  <-- EXCEEDS"
        if n > MAX_ULPS:
            bad += 1
        print(f"  {x!r:>22} {y!r:>22} {n:7.2f}{flag}")
    if bad:
        print(f"FAIL: {bad} of {len(a)} normalised rows differ by more than {MAX_ULPS} ulp of "
              f"binary32. With the one grown fraction the two routes get from different places "
              f"divided out, what is left is per-operation rounding against a final cast, and "
              f"that is bounded by {MAX_ULPS:.0f} ulps -- measured, two rows bit-exact, one at 1 ulp "
              f"and one at 2. A divergence here is arithmetic, not precision.")
        return 1
    print(f"  all {len(a)} normalised rows agree within {MAX_ULPS} ulp of binary32")
    return 0


if __name__ == "__main__":
    sys.exit(main())
