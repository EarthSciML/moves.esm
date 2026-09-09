#!/usr/bin/env bash
#
# Run the independent reproduction of `nr-airtoxics-lawn-garden-county` that
# lives in
# `docs/nr-airtoxics-lawn-garden-county.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-oracle.sh does for `nr-logging-county`: one source of
# truth, and a spec whose code has quietly stopped running cannot mislead
# anyone for long.
#
#   ./run-nr-airtoxics-oracle.sh
#
# What it proves. It computes the WHOLE NONROAD chain from the snapshot's own
# INPUT tables -- growth, scrappage, the thirty-year age-distribution fold, the
# geographic allocation, the monthly/daily temporal split, the emission factors
# with deterioration and the emsadj.f adjustments -- for all 108 Lawn/Garden
# equipment points, and then both previously unported NONROAD calculators:
# `NRHCSpeciationCalculator`'s five species and `NRAirToxicsCalculator`'s
# twenty toxics plus the NonHAPTOG pass. It reproduces all 14,036 MOVESOutput
# rows over 29 pollutant-process pairs, key set exact.
#
# WHY THE REPORT IS ONE POPULATION, AND USED TO BE THREE. `moves-snapshot/v2`
# stores a float as the shortest decimal that round-trips the f64, so the
# capture destroys nothing and every one of the 14,036 cells is judged on its
# raw relative error against tolerance.toml's UNMODIFIED [cell] rel = 2e-5.
# Worst 9.425e-06; 6.874e-06 on pollutant 131 and 9.217e-06 on 142.
#
# The script READS the encoding off a `.meta.json` and ASSERTS it is lossless.
# That is deliberate: pointed at a `moves-snapshot/v1` corpus it fails loudly
# rather than reporting a clean comparison it is silently misreading.
#
# Under v1 this report had three lines, because twelve DECIMAL places left a
# value of 1e-12 with ONE significant digit: 10,439 cells stored in full,
# 2,629 that needed a 5e-13 absolute floor, and 968 cells of pollutants 131
# and 142 whose INPUT rate (`nrdioxinemissionrate.meanBaseRate`) was captured
# as 0.000000001105 and 0.000000000019 -- four significant figures and TWO --
# which no tolerance reading can fix, so the script had to FIT the rate the
# reference must have used. v2 records 1.1045e-09 and 1.94345e-11 and the
# script now reads them; the old fits, 1.1045021e-09 and 1.9434497e-11, were
# right to 1.9e-06 and 1.5e-07 relative.
#
# That is why `fixtures/nr-airtoxics-lawn-garden-county.esm` emits 14,036 rows
# and now COMPARES all 14,036 where it used to compare 13,068, and why
# tolerance.toml no longer carries a scope for it at all.
# `docs/nr-airtoxics-lawn-garden-county.md` §7.2 and §8 have the before-and-after.
#
# THIS SCRIPT IS THE ATTRIBUTION TOOL FOR THAT: it computes the same 14,036
# rows by a completely different route -- float32 NumPy straight from the
# Parquet, no .esm anywhere -- so when the fixture and the snapshot disagree,
# a third implementation says whether the document or the specification is
# wrong. It also fits and asserts the two dioxin rates every run, which no
# comparison against MOVESOutput could do.
#
# IT TAKES NOTHING FROM THE REFERENCE. `movesworkeroutput`, `baserateoutput`,
# the `temporaryoutputimport` tables and `MOVESOutput` are read by nothing here
# except the final comparison.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/nr-airtoxics-lawn-garden-county.md"
# Locate the snapshots by searching UPWARD rather than by a fixed `../`, which
# is right from the canonical checkout and one level too deep from a git
# worktree under `.moves/`.
if [[ -z "${SNAPSHOTS:-}" ]]; then
  d="$PWD"
  while [[ "$d" != / ]]; do
    if [[ -d "$d/moves.rs/characterization/snapshots" ]]; then
      SNAPSHOTS="$d/moves.rs/characterization/snapshots"; break
    fi
    d="$(dirname "$d")"
  done
  SNAPSHOTS="${SNAPSHOTS:-../moves.rs/characterization/snapshots}"
fi
FIXTURE="nr-airtoxics-lawn-garden-county"
PYTHON="${PYTHON:-python3}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)  sed -n '2,/^set -uo/p' "$0" | sed 's/^# \?//;$d'; exit 0 ;;
    *)          echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ ! -f "$SPEC" ]]; then
  echo "error: no port specification at $SPEC" >&2
  exit 2
fi
if [[ ! -d "$SNAPSHOTS/$FIXTURE" ]]; then
  echo "error: no snapshot at $SNAPSHOTS/$FIXTURE (set SNAPSHOTS=...)" >&2
  exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Pull the one ```python fence out of §6.5.
"$PYTHON" - "$SPEC" "$WORK/repro.py" <<'PY' || exit 2
import sys, pathlib
lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
try:
    start = next(i for i, l in enumerate(lines) if l.startswith("### 6.5"))
    end = next(i for i, l in enumerate(lines) if i > start and l.startswith("### 6.6"))
except StopIteration:
    sys.exit("could not find §6.5 .. §6.6 in the specification")
block = lines[start:end]
try:
    b = next(i for i, l in enumerate(block) if l.strip() == "```python")
    e = next(i for i, l in enumerate(block) if i > b and l.strip() == "```")
except StopIteration:
    sys.exit("§6.5 has no ```python fence")
pathlib.Path(sys.argv[2]).write_text("\n".join(block[b + 1:e]) + "\n")
print(f"  extracted {e - b - 1} lines from {sys.argv[1]} §6.5")
PY

SNAP_ABS="$(cd "$SNAPSHOTS/$FIXTURE" && pwd)"

if ! out=$("$PYTHON" "$WORK/repro.py" "$SNAP_ABS" 2>&1); then
  echo "  FAILED" >&2
  sed 's/^/  /' <<<"$out" >&2
  exit 1
fi
sed 's/^/  /' <<<"$out"
