#!/usr/bin/env python3
"""Judge a `compare-output.py` failure against the shortfall tolerance.toml records.

The comparator itself is unconditional and stays that way: it fails whenever the
emitted key set is not the snapshot's, and nothing can tell it to pass. That is
deliberate — a comparator that can be silenced is not a comparator, and this
repository has already been bitten once by a stage that reported success while
comparing nothing.

But a fixture can be legitimately incomplete for a written reason, and the
useful question is then not "did it pass" but "is the failure still exactly the
one we wrote down". This script answers that, from the comparator's own report:

    rows: 12 actual / 144 expected
    key set: 12 shared, 132 missing, 0 extra
    worst cell: rel=4.025e-06 over 12 cells (tolerance 2e-05)

against a `[shortfall."<fixture>"]` table giving `emitted_rows`,
`missing_keys`, `extra_keys` and `why`. It agrees ONLY if all three counts
match and every shared cell is within the per-cell tolerance the comparator
applied — so a wrong NUMBER in a row this fixture does emit is still a failure,
and so is one more or one fewer row than recorded. The per-pollutant sums are
not consulted: they cannot agree while whole SCCs are missing, and they are
already reported.

Exit 0 with a one-line verdict on agreement; exit 1 otherwise. `--explain`
prints what differed. `--has-record` exits 0 iff a record exists at all, which
is what lets run-tests.sh fail a fixture whose shortfall has been fixed but
whose record is still in the file.
"""

from __future__ import annotations

import argparse
import re
import sys

ROWS = re.compile(r"^rows:\s*(\d+) actual / (\d+) expected\s*$", re.M)
KEYS = re.compile(r"^key set:\s*(\d+) shared, (\d+) missing, (\d+) extra\s*$", re.M)
CELL = re.compile(r"^worst cell: rel=([0-9.eE+-]+) over (\d+) cells \(tolerance ([0-9.eE+-]+)\)\s*$", re.M)


def record(path: str, fixture: str) -> dict | None:
    """The `[shortfall."<fixture>"]` table, or None.

    Deliberately a small hand parser rather than a TOML library: this repository
    targets a bare python3 and compare-output.py already carries its own subset
    reader for the same file and the same reason.
    """
    want = f'[shortfall."{fixture}"]'
    out: dict = {}
    inside = False
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("["):
            inside = line == want
            continue
        if not inside or not line or line.startswith("#") or "=" not in line:
            continue
        k, v = (x.strip() for x in line.split("=", 1))
        out[k] = int(v) if v.lstrip("-").isdigit() else v.strip('"')
    return out or None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--tolerance", default="tolerance.toml")
    ap.add_argument("--report", action="store_true", help="read the comparator report on stdin")
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--has-record", action="store_true")
    a = ap.parse_args(argv)

    rec = record(a.tolerance, a.fixture)
    if a.has_record:
        return 0 if rec else 1
    if rec is None:
        if a.explain:
            print(f"no [shortfall.\"{a.fixture}\"] record in {a.tolerance}")
        return 1

    text = sys.stdin.read()
    rows, keys, cell = ROWS.search(text), KEYS.search(text), CELL.search(text)
    if not (rows and keys):
        if a.explain:
            print("the comparator report is not in the expected shape; it may have "
                  "failed before comparing (a missing column, an empty snapshot)")
        return 1

    emitted, expected = int(rows.group(1)), int(rows.group(2))
    _shared, missing, extra = (int(g) for g in keys.groups())
    bad = []
    for what, got, want in (("emitted rows", emitted, rec.get("emitted_rows")),
                            ("missing keys", missing, rec.get("missing_keys")),
                            ("extra keys", extra, rec.get("extra_keys"))):
        if want is None:
            bad.append(f"{what}: {got}, and the record does not say")
        elif got != want:
            bad.append(f"{what}: {got}, recorded {want}")
    if cell:
        worst, _n, tol = (float(cell.group(1)), int(cell.group(2)), float(cell.group(3)))
        if worst > tol:
            bad.append(f"a shared cell is out of tolerance: rel={worst:.3e} > {tol:g}")
    elif emitted:
        bad.append("no per-cell comparison was reported")

    if bad:
        if a.explain:
            for line in bad:
                print(line)
        return 1
    print(f"comparison fails with exactly the recorded shortfall: {emitted}/{expected} "
          f"rows, {missing} keys not emitted, every emitted cell within tolerance")
    return 0


if __name__ == "__main__":
    sys.exit(main())
