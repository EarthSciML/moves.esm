#!/usr/bin/env bash
#
# Run the independent reproduction of `process-pm-exhaust` that lives in
# `docs/process-pm-exhaust.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-airtoxics-oracle.sh does for `process-airtoxics`: one
# source of truth, and a spec whose code has quietly stopped running cannot
# mislead anyone for long.
#
#   ./run-pm-exhaust-oracle.sh
#
# What it proves. It computes the WHOLE chain from the snapshot's own INPUT
# tables -- the activity half, the cohort structure, the drive-cycle
# operating-mode weights W, the AGE-GROUP-keyed base rates of BOTH rated
# pollutant-processes (11201 elemental carbon and 11801 composite NonECPM), the
# base-rate general fuel effect, then both calculators: `SulfatePMCalculator`'s
# fuel-sulfur sulfate fractions, its three-way split of NonECPM, its
# residue-only fuel ratio, its crankcase split and its four sums, and
# `PM10EmissionCalculator`'s single multiply -- and reproduces all 82 rows of
# `sho`, all 4,784 non-zero rows of `sbweightedemissionratebyage`, all 208
# non-zero rows of each of the two `baseratebyage_1_2020` blocks and all 1,456
# rows of `MOVESOutput` to ~9.9e-6, which is the reference's own
# six-significant-figure column storage (specification §7.1) and not
# accumulated error.
#
# THIS RUNG HAS NO UNCHAINED PARENT BLOCK, so there is no cheap cross-check to
# lean on. `process-airtoxics`' THC parent came back byte-identical to
# `process-crankcase-running`'s (1,1) block; measured across all 31 snapshots
# that carry a non-empty MOVESOutput, NO block of this one is byte-identical to
# or a constant multiple of any block of any other (§ the specification's
# opening). What is shared is one level down -- `sho` is byte-identical across
# this snapshot and thirteen others -- so the three INTERMEDIATE checkpoints
# below are doing the attribution work a shared parent block would otherwise
# have done. `sbweightedemissionratebyage` in particular is a table
# `process-airtoxics` named and did not read; reading it separates a wrong
# `emissionratebyage` key from a wrong drive-cycle weight, which matters here
# because the rate half runs twice.
#
# It also ASSERTS the key set, per pollutant-process against ONE shared cohort
# set rather than as seven counts. 1,456 = 7 x 208 but also 4 x 364 and
# 8 x 182, so a row count cannot see a mis-shaped block set; and the assertion
# that all seven blocks carry the SAME 104 cohorts is stronger than seven
# separate counts would be. It asserts further that the 124-cohort rate
# relation loses exactly the twenty ELECTRICITY cohorts, and that it loses them
# TWICE -- `sulfatefractions` has no fuel-type-9 row and
# `crankcaseemissionratio` has none either -- because either miss alone would
# produce this row set and the row set is therefore not evidence for which one
# MOVES uses.
#
# And it asserts eleven things no comparison against MOVESOutput could catch,
# every one of them found by SABOTAGING this script and watching it stay green
# (specification §7.2 tabulates all twenty-one sabotages):
#
#   * that every `crankcaseRatio` this run reaches is exactly 1.0, so the
#     crankcase MULTIPLY is inert while its INNER JOIN decides 20 cohorts;
#   * that `H2OnonECPMFraction` is 0 on all six `sulfatefractions` rows, so
#     pollutant 119 is 208 rows of exactly zero and the water term never leaves
#     the residue fraction;
#   * that the split does NOT conserve mass -- sulfate takes the
#     sulfur-ADJUSTED fraction and the residue the UNADJUSTED one, so the three
#     species sum to 0.8385..0.9865 of the NonECPM they came from;
#   * that the `greatest(1 - H - S, 0)` clamp never binds;
#   * that the PM temperature arm exp(A x (72 - T)) is the LIVE branch at
#     59.5 degF and is 1 only because `temperatureadjustment` is EMPTY -- the
#     72 degF ceiling is not what neutralises it;
#   * that the A/C arm is dead TWICE, the activity term clamping to 0 and
#     `fullacadjustment` having no rows for either parent;
#   * that `criteriaratio` is empty, so `generalfuelratio` is the only live fuel
#     effect, and that its two pollutants enter at DIFFERENT stages -- applying
#     both in one place would square the 1.0909 on gasoline and E85;
#   * that each fuel type is supplied by exactly ONE formulation at market share
#     1.0, so the share-weighted sulfate fraction is a sum of one term and
#     `generalfuelratio`'s fuelFormulationID column cannot be distinguished from
#     ignoring it;
#   * that `pm10emissionratio` ships a fuel-type-9 row nothing can reach, and
#     one model-year band per (source, fuel), so its band predicate is untested;
#   * that `runspecchainedto` contains the 2-CYCLE 11801 <-> 11501, so the
#     chain-root iteration of `docs/esm-conventions.md` §32.1 does not
#     terminate on this snapshot;
#   * that `pmspeciation` is 4 rows, all 120 -> 111, so NCOM, Total Organic
#     Matter, NonECNonSO4NonOM and the whole ratio124 step are dead.
#
# IT TAKES NOTHING FROM THE REFERENCE. `baseratebyage_1_2020`,
# `sbweightedemissionratebyage`, `baserateoutput`, `sourcebindistribution`,
# `sho` and `MOVESOutput` are read by nothing here except the final
# comparisons.
#
# It remains an ATTRIBUTION tool and not a substitute for the fixture
# comparison: when a `.esm` disagrees with the snapshot, a third implementation
# says whether the document or the specification is wrong.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/process-pm-exhaust.md"
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
FIXTURE="process-pm-exhaust"
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
