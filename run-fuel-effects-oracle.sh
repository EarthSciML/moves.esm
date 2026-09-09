#!/usr/bin/env bash
#
# Run the independent reproduction of `FuelEffectsGenerator.doGeneralFuelRatio`
# that lives in docs/fuel-effects-generator.md §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-meteorology-oracle.sh does: one source of truth, and a
# spec whose code has quietly stopped running cannot mislead anyone for long.
#
#   ./run-fuel-effects-oracle.sh
#
# IT IS HANDED THE SNAPSHOTS DIRECTORY, NOT ONE SNAPSHOT, which it shares with
# exactly one sibling and for the same reason.  `FuelEffectsGenerator` is a
# GENERATOR: it writes the `generalFuelRatio` table of the execution database
# and emits no `MOVESOutput` row, so there is no single fixture whose output it
# reproduces.  What there is instead is a scheduling rule -- MOVES loads the
# class on an ONROAD run that selects any of processes 1, 2, 9, 10, 11, 12, 13
# or 90 -- and 40 snapshots that carry the input table, 22 of which ran it and
# 18 of which did not.  Both halves are the claim, so both halves are checked,
# and checking them needs the whole corpus.
#
# What it proves.  From `generalFuelRatioExpression`, `FuelFormulation`,
# `FuelSubtype` and `FuelSupply` -- and nothing else -- it re-evaluates every
# expression string the corpus holds against every fuel formulation the fuel
# supply selects, and asserts:
#
#     the cell count                     >= 194, a FLOOR rather than an
#                                        equality: silent skipping can only make
#                                        it go down, and the corpus is shared
#                                        with the other rungs and grows
#                                        (docs/esm-conventions.md 35.5)
#     missing keys                       0, exactly
#     unaccounted extra keys             0, exactly -- MOVES computes 766 rows
#                                        and keeps 97; the other 669 are the
#                                        ones `copyGeneralFuelRatioToCriteriaRatio`
#                                        and `doAirToxicsCalculations` move to
#                                        `criteriaRatio` / `ATRatio`, and each
#                                        one is checked against those tables by
#                                        its own (fuelFormulationID, polProcessID)
#                                        rather than waved through
#     the worst relative error           < 1e-13  (measured: 0.0, bit-identical
#                                          on all 194 cells; it was 1.608e-14
#                                          under moves-snapshot/v1, and that
#                                          residual was the CAPTURE's)
#     the scheduling predicate           every snapshot agrees (40 of 40 today)
#     the two FLOAT promotions           distinguishable by > 1000x
#     the integer-literal division       count is ZERO, and the two candidate
#                                        semantics give BIT-IDENTICAL residuals
#
# The last one is asserted with the opposite polarity to everything else here,
# and section 7.3 of the specification is why.  moves.rs left open whether a
# `fuelEffectRatioExpression` that divides two integer literals gets MariaDB's
# DECIMAL rounding.  The measurement is that the corpus contains no such
# expression, so the question cannot be asked of it -- and the honest way to
# record that is to assert the absence, so that the day a capture adds one the
# oracle goes red and the question becomes answerable, instead of the
# specification quietly continuing to say "not decidable" after it has become
# decidable.
#
# IT TAKES NOTHING FROM THE REFERENCE.  `generalFuelRatio` is read only to
# compare against; `criteriaRatio`, `altCriteriaRatio` and `ATRatio` are read
# only for their key columns, to establish which rows MOVES moved rather than
# never computed.
#
# It remains an ATTRIBUTION tool and not a substitute for
# components/fuel_effects.esm's inline assertions: when the component disagrees
# with the snapshot, a third implementation says whether the document or the
# specification is wrong.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/fuel-effects-generator.md"
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
echo "  NOTE: forms C, D, E and F are NOT checked against MOVES anywhere. Every"
echo "        row that uses one is moved to criteriaRatio or ATRatio before a"
echo "        snapshot is taken; see $SPEC section 8.1."
