#!/usr/bin/env python3
"""Check that the two independently authored NONROAD chains agree.

`runs/nr_logging_county_run.esm` mounts the fifteen components and recomputes
docs/nonroad-logging-county.md §6.1's four model-year-2020 rows from leaves.
`fixtures/nr-logging-county.esm` computes the same four rows from the snapshot
Parquet. They are separate documents with separate equations, and until this
check nothing compared them -- each passed its own gate against its own
transcribed numbers, at tolerances far tighter than the gap between them.

They evaluate in DIFFERENT PRECISIONS, deliberately, and that is the whole
subtlety. The fixture declares Float32 and rounds per operation. The assembly
does not declare an element type, so it evaluates in binary64 and asserts
binary64 values. Comparing them therefore means casting the assembly's values
to binary32 and allowing the difference between per-operation rounding and a
single final cast -- which is bounded by one ulp per operation but is, measured
on these four rows, exactly one ulp on one row and zero on the other three.

So the tolerance here is ULPS, not a relative fraction: a relative bound would
have to be loosened to 1e-7 to pass row 2, and 1e-7 is four orders looser than
what either document asserts internally. An ulp bound stays tight in the units
that the divergence is actually measured in.

What this catches that nothing else does: an arithmetic divergence between the
two chains. What it deliberately tolerates: the precision difference. What it
does NOT catch: both chains being wrong in the same way -- that is what
run-oracle.sh's third implementation is for.
"""
import csv, json, math, struct, sys

ASSEMBLY = "runs/nr_logging_county_run.esm"
TEST_ID = "the_chain_reproduces_the_worked_examples_2020_rows"
MODEL_YEAR = "2020"
MAX_ULPS = 1.0

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

def fixture_values(csv_path):
    rows = [r for r in csv.DictReader(open(csv_path)) if r["modelYearID"] == MODEL_YEAR]
    if not rows:
        sys.exit(f"{csv_path}: no rows for model year {MODEL_YEAR}")
    return [float(r["emissionQuant"]) for r in rows]

def main():
    if len(sys.argv) != 2:
        sys.exit("usage: cross-check-chain.py <fixture actual .csv>")
    a = sorted(f32(v) for v in assembly_values())
    b = sorted(fixture_values(sys.argv[1]))

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
            print(f"FAIL: values {a[i]!r} and {a[i+1]!r} are closer than the "
                  f"tolerance, so a sorted comparison cannot pair them safely")
            return 1

    bad = 0
    print(f"  {'assembly f64->f32':>22} {'fixture per-op f32':>22} {'ulps':>7}")
    for x, y in zip(a, b):
        n = abs(y - x) / ulp32(x)
        flag = "" if n <= MAX_ULPS else "  <-- EXCEEDS"
        if n > MAX_ULPS:
            bad += 1
        print(f"  {x!r:>22} {y!r:>22} {n:7.2f}{flag}")
    if bad:
        print(f"FAIL: {bad} of {len(a)} rows differ by more than {MAX_ULPS} ulp of "
              f"binary32. The two chains disagree by more than the precision "
              f"difference between them can explain.")
        return 1
    print(f"  all {len(a)} rows agree within {MAX_ULPS} ulp of binary32")
    return 0

if __name__ == "__main__":
    sys.exit(main())
