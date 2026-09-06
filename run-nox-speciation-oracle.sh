#!/usr/bin/env bash
#
# Run the independent reproduction of `process-nox-speciation` that lives in
# `docs/process-nox-speciation.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-onroad-oracle.sh does for `mixed-onroad`: one source of
# truth, and a spec whose code has quietly stopped running cannot mislead
# anyone for long.
#
#   ./run-nox-speciation-oracle.sh
#
# What it proves. It computes the WHOLE chain from the snapshot's own INPUT
# tables -- the activity half, the cohort structure, the drive-cycle
# operating-mode weights W, the AGE-GROUP-keyed base rate out of
# `emissionratebyage`, the criteria fuel effect, the NOx temperature-and-humidity
# factor, and the NOCalculator / NO2Calculator chain -- and reproduces all 82
# rows of `sho`, all 208 non-zero rows of `baseratebyage_1_2020` and all 872 rows
# of `MOVESOutput` to ~9.5e-6, which is the reference's own
# six-significant-figure column storage (specification 7.1) and not accumulated
# error. It reports the same worst cell, at the same key, as the .esm fixture
# does by a different route.
#
# It also ASSERTS the key set, and per pollutant-process rather than in total,
# because the blocks are ragged: 124 total-NOx cohorts and 104 for each of the
# three species, over 2 day types. 124 + 104 x 3 and 109 x 4 are both 436, so a
# row count cannot see a block set that has gone wrong. It asserts further that
# the twenty cohorts each species drops are exactly the ELECTRICITY ones and
# that every species set is a strict subset of the parent's.
#
# And it asserts the two things no comparison against MOVESOutput could catch:
# that NO + NO2 + HONO is exactly 1.0 in all 37 model-year groups of each fuel
# type -- so the three species partition their parent and a per-pollutant SUM
# gate cannot tell them apart -- and that the A/C activity term clamps to 0, so
# a reader cannot mistake a passing comparison for a check of the 23 live
# fullacadjustment rows.
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

SPEC="docs/process-nox-speciation.md"
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
FIXTURE="process-nox-speciation"
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
