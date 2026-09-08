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
# WHY THE REPORT HAS THREE LINES INSTEAD OF ONE. Every table in this corpus is
# captured with `float_decimals: 12` (`moves.rs/crates/moves-snapshot/
# src/format.rs:17`), which stores a float as twelve DECIMAL places -- so a
# value of 1e-12 keeps ONE significant digit. That splits the comparison into
# three populations, and conflating them would hide the one that matters:
#
#   * 10,439 cells the capture stores in full (>= 8 significant digits). Worst
#     9.425e-06, asserted against tolerance.toml's UNMODIFIED [cell] rel = 2e-5.
#   * 2,629 cells stored with fewer digits. Their error is asserted in EXCESS of
#     the capture's own half-quantum (5e-13 absolute) -- the same concession
#     compare-output.py already makes for an exactly-zero expectation, and not a
#     tolerance chosen here. Worst 8.655e-06.
#   * 968 cells of pollutants 131 and 142, whose INPUT rate
#     (`nrdioxinemissionrate.meanBaseRate`) is captured as 0.000000001105 and
#     0.000000000019 -- four and TWO significant figures. No tolerance reading
#     can fix an input. Instead the script FITS the rate the reference must have
#     used and asserts it lies within half a stored quantum of the captured one:
#     1.1045021e-09 against 1.105e-09 (0.996 half-quanta) and 1.9434497e-11
#     against 1.9e-11 (0.869). That is the whole of the difference, and it is
#     the capture's rather than the port's.
#
# That third population is why this snapshot has NO .esm fixture: a per-cell
# comparison against its MOVESOutput fails on 1,013 of 14,036 cells for ANY
# correct implementation. `docs/nr-airtoxics-lawn-garden-county.md` §7.2 and §8
# have the measurement and what it costs.
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
