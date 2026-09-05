#!/usr/bin/env bash
#
# Run the independent reproduction of `process-evap-fvv` that lives in
# `docs/evap-fvv.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-oracle.sh, ./run-onroad-oracle.sh, ./run-leaks-oracle.sh
# and ./run-permeation-oracle.sh do for their fixtures: one source of truth, and
# a spec whose code has quietly stopped running cannot mislead anyone for long.
#
#   ./run-fvv-oracle.sh
#
# What it proves. It computes the ACTIVITY chain (specification docs/evap-leaks.md
# 2.1, A1-A10), the cohort structure with this process's own source-bin key rule
# (0.1, C2'), the evaporative operating-mode distribution (E1-E3),
# TankTemperatureGenerator TTG-1 (2.4), the whole of TankFuelGenerator (2.5,
# TFG-1a..TFG-3b) and all nine steps of MultidayTankVaporVentingCalculator
# (2.6-2.14, TVV-1..TVV-9) including the TVG soak-day recurrence, from the
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
# to ~7.5e-6, which is the reference's own 6-significant-figure column storage
# (7.1), not accumulated error. Every comparison ASSERTS its tolerance
# (docs/esm-conventions.md 21); none of them merely prints it.
#
# What it takes from the reference: NOTHING. Every table it opens is an input of
# the execution database, and the seven tables named above are compared against
# and never read forward. Unlike ./run-permeation-oracle.sh -- which reads 192 of
# the 288 `AverageTankTemperature` cells because finding F28 blocks the generator
# step that produces them -- this chain needs no tank temperature on the path
# that carries the answer, and `AverageTankGasoline`, which would have been the
# analogous read, is captured EMPTY and is therefore computed here in full.
#
# Do not read that as "the venting chain is checked here". It is not. Section 0.3
# measures that this fixture's opModeFraction for the cold-soak mode is exactly
# 0, so perturbing ColdSoakTankTemperature by +50 degF, doubling TVV-5's venting
# equation, tripling the soak recurrence's carry or multiplying TTG-7's fraction
# by 7 each leave all 128 output cells BIT-IDENTICAL. The chain is computed here
# anyway, because that is what makes the zero a measurement rather than an
# assumption -- and the script asserts, on every run, both that the venting chain
# produced non-zero cold-soak base rates and that they contributed nothing.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/evap-fvv.md"
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
FIXTURE="process-evap-fvv"
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
echo "  NOTE: nothing above is read from the reference. Every table opened is an"
echo "        INPUT of the execution database; see $SPEC section 6.5 and 8.2."
