#!/usr/bin/env bash
#
# Run the independent reproduction of the two reachable operating-mode-
# distribution generators that lives in
# `docs/operating-mode-distribution.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-meteorology-oracle.sh does: one source of truth, and a
# spec whose code has quietly stopped running cannot mislead anyone for long.
#
#   ./run-omd-oracle.sh
#
# IT IS HANDED THE SNAPSHOTS DIRECTORY, NOT ONE SNAPSHOT. Both modules are
# GENERATORS: they write execution-database tables and emit no `MOVESOutput`
# row, so there is no single fixture whose output they reproduce. What there is
# instead is a scheduling rule with two halves, and 40 snapshots of which 9 run
# `StartOperatingModeDistributionGenerator` and 5 emit rows from
# `RatesOperatingModeDistributionGenerator`. The 31 and 35 that do not are the
# evidence; without them the subscription list is a comment.
#
# What it proves. From `SampleVehicleTrip`, `SampleVehicleDay`, `OperatingMode`,
# `HourDay`, `RunSpecHourDay`, `startsOpModeDistribution`,
# `pollutantProcessAssoc`, `sourceTypePolProcess`, `opModePolProcAssoc`,
# `runSpecSourceType` and `hotellingActivityDistribution` -- and nothing else --
# it recomputes:
#
#     StartOpMode              262,442 rows, 0 missing / 0 extra
#     StartOpModeDistribution      124 rows, 0 missing / 0 extra, BIT-EXACT
#     SOMDGOpModes             the distinct set, in all 9 snapshots
#     RatesOpModeDistribution      300 rows, 0 missing / 0 extra
#
# and asserts:
#
#     the row counts                     >= the figures above, FLOORS rather
#                                        than equalities: silent skipping can
#                                        only make them go down, and the corpus
#                                        is shared with the other rungs and
#                                        grows (docs/esm-conventions.md 35.5)
#     the key sets                       0 missing / 0 extra, per snapshot,
#                                        EXACTLY -- a property of the model
#     the worst relative error           < 2e-5  (measured: 4.388e-06)
#     the four-decimal quotient          bit-exact on every row
#     the exact IEEE ratio               still distinguishable at > 2e-5, so the
#                                        assertion above is doing work
#     the scheduling predicate           every snapshot agrees (40 of 40 today)
#
# 4.388e-06 is the reference's own single-precision FLOAT storage of
# `RatesOpModeDistribution.opModeFraction` against the DOUBLE it is copied from,
# not accumulated error. The `StartOpModeDistribution` fractions are reproduced
# to the last bit, because MOVES stores them as a four-decimal DECIMAL and this
# port computes the same four-decimal DECIMAL.
#
# IT TAKES NOTHING FROM THE REFERENCE. `StartOpMode`, `StartOpModeDistribution`,
# `SOMDGOpModes` and `RatesOpModeDistribution` are read only to compare against
# and, for the scheduling predicate, to decide which runs produced rows.
#
# It remains an ATTRIBUTION tool and not a substitute for the components'
# inline assertions: when `components/start_operating_mode_distribution.esm` or
# `components/rates_operating_mode_distribution.esm` disagrees with the
# snapshot, a third implementation says whether the document or the
# specification is wrong.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/operating-mode-distribution.md"
# Locate the snapshots by searching UPWARD rather than by a fixed `../`, which
# is right from the canonical checkout and one level too deep from a git
# worktree.
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
  echo "error: no port specification at $SPEC" >&2
  exit 2
fi
if [[ ! -d "$SNAPSHOTS" ]]; then
  echo "error: no snapshots at $SNAPSHOTS (set SNAPSHOTS=...)" >&2
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

SNAP_ABS="$(cd "$SNAPSHOTS" && pwd)"

if ! out=$("$PYTHON" "$WORK/repro.py" "$SNAP_ABS" 2>&1); then
  echo "  FAILED" >&2
  sed 's/^/  /' <<<"$out" >&2
  exit 1
fi
sed 's/^/  /' <<<"$out"
echo "  NOTE: the inventory branch of step 400 and the existingStartOMD"
echo "        bookkeeping are NOT checked here -- every snapshot runs"
echo "        DO_RATES_FIRST; see $SPEC section 8.2."
