#!/usr/bin/env bash
#
# Run the DISPROOF of `NewTvvYearGenerator` that lives in
# `docs/new-tvv-year.md` §6.5.
#
# The script is EXTRACTED from the document rather than kept as a second copy,
# exactly as the other oracles here do.
#
#   ./run-new-tvv-year-oracle.sh
#
# WHY THERE IS AN ORACLE FOR A MODULE THAT DOES NOT EXIST. The claim "this is
# a SQL section and not a generator" was previously a sentence in
# `docs/omd-generator-reachability.md`, and that sentence was WRONG about
# where the name comes from -- it said `CalculatorInfo.txt` names it, and
# `CalculatorInfo.txt` does not. A sentence cannot be re-checked when the
# corpus or the pinned source moves. This can.
#
# IT NEEDS NO CAPTURE. Everything it reads is already in
# `process-evap-fvv`, which has been in the corpus since Phase 0.
#
# What it proves. From `sampleVehiclePopulation`, `cumTVVCoeffs`,
# `pollutantProcessMappedModelYear`, `ageCategory`, `runSpecSourceType`,
# `runSpecModelYear` and `runSpecPollutantProcess` -- and nothing else -- it
# rebuilds all three tables `-- Section NewTVVYear` creates
# (`MultidayTankVaporVentingCalculator.sql:335-432`):
#
#     regClassFractionOfSTMY2020   125 rows
#     stmyTVVEquations2020         125 rows
#     stmyTVVCoeffs2020            125 rows
#
# and asserts:
#
#     the key sets            0 missing / 0 extra, per table, EXACTLY
#     the values              1,750 cells, BIT-EXACT -- `==` on the double,
#                             not a tolerance, because the columns are
#                             doubles and moves-snapshot/v2 stores the
#                             shortest round-tripping decimal of each
#     the cell count          >= 1750, a FLOOR (docs/esm-conventions.md §35.5)
#
# and THREE NEGATIVES, which are what make it a disproof rather than a port
# check:
#
#     no snapshot in the corpus class-loads any class whose name contains
#     `NewTvvYear` -- 0 of 43 traced
#
#     every snapshot that HAS the tables class-loads
#     `TankVaporVentingCalculator` -- 1 of 1, which is the positive
#     attribution to go with the negative one
#
#     `calculator-dag.json`'s hand-added `NewTvvYearGenerator` module still
#     carries `java_path: ""` and `registrations_count: 0`, so its
#     `"source": "CalculatorInfo"` is still contradicted by its own
#     neighbouring fields
#
# The negatives fail LOUDLY if the module turns out to be real after all --
# a class appears, or the DAG entry is corrected into a genuine one. At that
# point `docs/new-tvv-year.md` is wrong and should be deleted, which is the
# outcome this is built to detect rather than to survive.
#
# IT TAKES NOTHING FROM THE REFERENCE. The three tables are read only to
# compare against.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/new-tvv-year.md"
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
PYTHON="${PYTHON:-python3}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)  sed -n '2,/^set -uo/p' "$0" | sed 's/^# \?//;$d'; exit 0 ;;
    *)          echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ ! -f "$SPEC" ]]; then
  echo "error: no document at $SPEC" >&2
  exit 2
fi
if [[ ! -d "$SNAPSHOTS" ]]; then
  echo "error: no snapshots at $SNAPSHOTS (set SNAPSHOTS=...)" >&2
  exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

"$PYTHON" - "$SPEC" "$WORK/repro.py" <<'PY' || exit 2
import sys, pathlib
lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
try:
    start = next(i for i, l in enumerate(lines) if l.startswith("### 6.5"))
    end = next(i for i, l in enumerate(lines) if i > start and l.startswith("### 6.6"))
except StopIteration:
    sys.exit("could not find §6.5 .. §6.6 in the document")
block = lines[start:end]
try:
    b = next(i for i, l in enumerate(block) if l.strip() == "```python")
    e = next(i for i, l in enumerate(block) if i > b and l.strip() == "```")
except StopIteration:
    sys.exit("§6.5 has no ```python fence")
pathlib.Path(sys.argv[2]).write_text("\n".join(block[b + 1:e]) + "\n")
print(f"  extracted {e - b - 1} lines from {sys.argv[1]} §6.5")
PY

SNAP_ABS="$(cd "$SNAPSHOTS" && pwd)"

if ! out=$("$PYTHON" "$WORK/repro.py" "$SNAP_ABS" 2>&1); then
  echo "  FAILED" >&2
  sed 's/^/  /' <<<"$out" >&2
  exit 1
fi
sed 's/^/  /' <<<"$out"
echo "  NOTE: one snapshot, one year and one process -- process-evap-fvv is"
echo "        the only run in the corpus that selects process 12. See"
echo "        $SPEC section 7."
