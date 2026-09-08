#!/usr/bin/env bash
#
# Run the independent reproduction of `chain-so2-co2e-mechanism` that
# lives in
# `docs/chain-so2-co2e-mechanism.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-oracle.sh does for `nr-logging-county`: one source of
# truth, and a spec whose code has quietly stopped running cannot mislead
# anyone for long.
#
#   ./run-so2-co2e-oracle.sh
#
# What it proves. It computes the whole ONROAD rates-first chain from the
# snapshot's own INPUT tables -- the activity spine, the cohort structure and
# fuel-usage rebase, the drive-cycle operating-mode weights, THREE base-rate
# roots off TWO different rate tables, the temperature and A/C adjustments
# including both arms of adjust.rs's temperature branch, and the EV efficiency
# divisor -- and then the five calculators chained off it:
# `HCSpeciationCalculator`'s five species, `AirToxicsCalculator`'s four live
# ratio paths, and the three this rung ports, `SO2Calculator`,
# `CO2AERunningStartExtendedIdleCalculator` and `TOGSpeciationCalculator`.
# It reproduces all 5,534 MOVESOutput rows over 26 pollutant-processes, key
# set exact, worst relative error 8.331e-06 against tolerance.toml's
# UNMODIFIED [cell] rel = 2e-5.
#
# WHY IT PRINTS FIVE NOTES. Each is something a comparison against MOVESOutput
# cannot say, and each is ASSERTED rather than printed
# (docs/esm-conventions.md 21) -- ./run-tests.sh reads this script's EXIT CODE.
#
#   * THE 44/12 MASS RATIO IS MEASURED. MOVES writes the SQL literal `(44/12)`
#     and MariaDB rounds exact-operand division to DECIMAL, giving 3.6667. The
#     script runs BOTH candidates over the 500 Atmospheric CO2 and CO2
#     Equivalent cells: the exact ratio lands at 5.743e-06 and the decimal one
#     at 1.483e-05, a systematic 9.09e-06 offset. The decimal candidate WOULD
#     STILL HAVE PASSED the 2e-5 gate, at 0.74 of it, which is why the two are
#     measured against each other and not each against the gate.
#
#   * THE NonHAPTOG CLAMP NEVER FIRES. `greatest(sum(...), 0)` is
#     `TOGSpeciationCalculator`'s whole protection against an over-subtracting
#     speciation, and 0 of this run's 208 cells are negative -- the fourteen
#     integrated species take 16.1 % to 48.6 % of NMOG and the smallest
#     residual is 4.567e-04 g. The census is recounted every run, so a snapshot
#     that started clamping would be noticed rather than absorbed.
#
#   * THE MECHANISM TABLE IS THE DISCRIMINATOR, NOT THE CLASS LOADING.
#     `TOGSpeciationCalculator` is class-loaded in ALL 42 snapshots because
#     `ExecutionRunSpec` calls its static `needsFinalAggregation()`.
#     `integratedspeciesset` is 14 rows here and 0 in every other snapshot,
#     including the misleadingly named `chain-tog-speciation`. One mechanism,
#     so the per-(mechanism, set) fan-out has one member and is untested.
#
#   * ELECTRICITY FAILS SO2 TWICE. There is no fuelTypeID 9 row in
#     `sulfateemissionrate` AND fuel subtype 90's `energyContent` is NULL.
#     Either alone gives the same 104-cohort block, so this snapshot cannot say
#     which one MOVES reached; both are asserted so a snapshot that fixed one
#     would fail loudly rather than pass on the other.
#
#   * THE CONTROL SNAPSHOT ATTRIBUTES THE ROWS. If
#     `chain-so2-co2e-mechanism-control` is beside this snapshot, the script
#     asserts that the two differ by exactly the four pollutant-processes the
#     three calculators own -- (31,1) (88,1) (90,1) (98,1) -- and that all 22
#     shared pairs' totals are bit-identical in the reference's own decimal
#     text. That is what says the chain BELOW the three calculators does not
#     move when they are switched on. The check is skipped, not failed, when
#     the control is absent (docs/esm-conventions.md 35.5's floor rule).
#
# THIS SCRIPT IS THE ATTRIBUTION TOOL: it computes the same 5,534 rows by a
# completely different route -- float64 Python straight from the Parquet, no
# .esm anywhere -- so when the fixture and the snapshot disagree, a third
# implementation says whether the document or the specification is wrong.
#
# IT TAKES NOTHING FROM THE REFERENCE except at the comparison.
# `movesworkeroutput`, `baserateoutput`, the `temporaryoutputimport` tables and
# `carbonoxidationbyfueltype` are read by nothing here; `sho`,
# `baseratebyage_1_2020`, `baserate_1_2020` and `MOVESOutput` are read by the
# comparison alone.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/chain-so2-co2e-mechanism.md"
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
FIXTURE="chain-so2-co2e-mechanism"
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
