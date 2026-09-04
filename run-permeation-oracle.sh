#!/usr/bin/env bash
#
# Run the independent reproduction of `process-evap-permeation` that lives in
# `docs/evap-permeation.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-oracle.sh and ./run-onroad-oracle.sh do for their
# fixtures: one source of truth, and a spec whose code has quietly stopped
# running cannot mislead anyone for long.
#
#   ./run-permeation-oracle.sh
#
# What it proves. It computes the ACTIVITY chain (specification docs/evap-leaks.md
# 2.1, A1-A10), the cohort structure with this process's own source-bin key rule
# (0.1, C2'), the evaporative operating-mode distribution (E1-E3), TankTemperature-
# Generator TTG-1 (2.6) and the calculator itself (2.7, PC-1..PC-6) from the
# snapshot's own INPUT tables, and reproduces
#
#     all  82 rows of `SHO`
#     all  82 rows of `SourceHours`
#     all 125 rows of `sourceBinDistributionFuelUsage`
#     all   6 rows of the evap `OpModeDistribution` (exactly)
#     all  96 rows of `QuarterHourTemperature`
#     all  24 rows of `ColdSoakTankTemperature`
#     all 128 rows of `MOVESOutput.emissionQuant`
#
# to ~6e-6, which is the reference's own 6-significant-figure column storage
# (7), not accumulated error.
#
# What it takes from the reference: 192 of the 288 `AverageTankTemperature`
# cells -- operating modes 150 and 300, which are TankTemperatureGenerator TTG-4's
# and which finding F28 blocks. Mode 151's 96 cells are COMPUTED here, through
# TTG-1's quarter-hour recurrence. The read is printed on every run.
#
# Do not read that as "the recurrence is checked here". It is not: 0.3 measures
# that this fixture's opModeFraction for mode 151 is exactly 0, so perturbing the
# computed cells by +50 degF changes nothing at all. The recurrence is checked in
# components/tank_temperature.esm, against three captured MOVES intermediates.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/evap-permeation.md"
# Locate the snapshots by searching UPWARD rather than by a fixed `../`, which
# is right from the canonical checkout and one level too deep from a git
# worktree under `.moves/`. Same fix as tools/check-sources.py, run-oracle.sh
# and run-onroad-oracle.sh; counting directories has caused three separate bugs
# in this repository, one of which silently skipped and went green.
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
FIXTURE="process-evap-permeation"
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
echo "  NOTE: 192 of 288 AverageTankTemperature cells ARE read from the reference"
echo "        (opModes 150 and 300); see $SPEC section 8.1. Everything else is derived."
