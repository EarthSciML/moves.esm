#!/usr/bin/env bash
#
# Run the independent reproduction of `process-airtoxics` that lives in
# `docs/process-airtoxics.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-nox-speciation-oracle.sh does for
# `process-nox-speciation`: one source of truth, and a spec whose code has
# quietly stopped running cannot mislead anyone for long.
#
#   ./run-airtoxics-oracle.sh
#
# What it proves. It computes the WHOLE chain from the snapshot's own INPUT
# tables -- the activity half, the cohort structure, the drive-cycle
# operating-mode weights W, the AGE-GROUP-keyed base rate out of
# `emissionratebyage`, the criteria fuel effect, then BOTH speciation stages:
# `HCSpeciationCalculator`'s NMHC and VOC (including the E85 `altTHC` branch)
# and `AirToxicsCalculator`'s two live ratio paths -- and reproduces all 82
# rows of `sho`, all 208 non-zero rows of `baseratebyage_1_2020` and all 1,288
# rows of `MOVESOutput` to ~8.1e-6, which is the reference's own
# six-significant-figure column storage (specification §7.1) and not accumulated
# error. It reports the same worst cell, at the same key, as the .esm fixture
# does by a different route.
#
# It also ASSERTS the key set, and per pollutant-process rather than in total,
# because the blocks are ragged: 124 cohorts of THC and 104 for each of the five
# species. 124 + 104 x 5 and 129 + 103 x 5 are both 644, so a row count cannot
# see a block set that has gone wrong. It asserts further that the twenty
# cohorts every species drops are exactly the ELECTRICITY ones and that every
# species set is a strict subset of the parent's.
#
# And it asserts six things no comparison against MOVESOutput could catch:
#
#   * that the E85 `altTHC` branch multiplies the emitted VOC by 3.8528 on every
#     ethanol 2001+ cohort, so a document that skipped it would be wrong by that
#     factor on 23 of the 104 species cohorts rather than subtly off;
#   * that the two live ATRatio paths are DISJOINT on every emitted cohort, so
#     the Go's append-both-ratios semantics is a sum of one term and untested;
#   * that `atRatioNonGas` is identical on fuel subtypes 20/21 and on 51/52, so
#     reading the SUPPLIED subtype rather than the fuel type's default cannot be
#     distinguished in this snapshot;
#   * that `oxySpeciation` is 0 on all 136 `hcspeciation` rows while the
#     formulations' oxygenate volumes are not, so that term of the speciation
#     factor is live in its inputs and dead in its coefficient;
#   * that the A/C activity term clamps to 0, so a reader cannot mistake a
#     passing comparison for a check of the 23 live fullacadjustment rows;
#   * that each fuel type is supplied by exactly ONE formulation at market share
#     1.0, so the per-formulation product's ORDER against the market-share sum is
#     untested.
#
# IT TAKES NOTHING FROM THE REFERENCE. `baseratebyage_1_2020`, `baserateoutput`,
# `sbweightedemissionratebyage`, `sourcebindistribution`, `sho` and
# `MOVESOutput` are read by nothing here except the final comparison.
#
# It remains an ATTRIBUTION tool and not a substitute for the fixture
# comparison: when a `.esm` disagrees with the snapshot, a third implementation
# says whether the document or the specification is wrong.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/process-airtoxics.md"
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
FIXTURE="process-airtoxics"
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
