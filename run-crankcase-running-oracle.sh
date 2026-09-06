#!/usr/bin/env bash
#
# Run the independent reproduction of `process-crankcase-running` that
# lives in
# `docs/process-crankcase-running.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-onroad-oracle.sh does for `mixed-onroad`: one source of
# truth, and a spec whose code has quietly stopped running cannot mislead
# anyone for long.
#
#   ./run-crankcase-running-oracle.sh
#
# What it proves. It computes the WHOLE chain from the snapshot's own INPUT
# tables -- the activity half, the cohort structure, the drive-cycle
# operating-mode weights W, the age-group-keyed criteria rate, the fuel-supply
# expansion with its criteria and general fuel ratios, the NOx humidity
# correction, and the whole of CrankcaseEmissionCalculatorNonPM -- and
# reproduces all 82 rows of `sho` and all 1368 rows of `MOVESOutput` to ~9e-6,
# which is the reference's own six-significant-figure FLOAT column storage
# (specification §7.1) and not accumulated error. It reports the same worst
# cell, at the same key, as the .esm fixture does by a different route.
#
# It also asserts THE KEY SET WITH THE PROCESS SPLIT MADE EXPLICIT, which is
# the one thing a row count cannot see here: 1368 rows is equally consistent
# with six blocks of 114, and the subject of this rung is that the two
# processes do NOT span the same cohorts. Process 1 spans 124 cohorts over four
# fuel types; process 15 spans 104 over three, is a strict subset of the first,
# and is short by exactly the twenty electricity cohorts that
# `crankcaseemissionratio` has no row for.
#
# And three structural facts no comparison against MOVESOutput could catch:
# that the crankcase ratio's model-year band is live in both directions (two
# diesel bands inside the run's window, one reachable gasoline band with an
# unreachable one 25x larger); that 114 crankcase rows are EXACTLY zero rather
# than absent; and that `generalfuelratio` -- 39 rows, all on crankcase
# pollutant-processes -- contributes a factor of exactly 1.
#
# IT TAKES NOTHING FROM THE REFERENCE. `baseratebyage_1_2020`,
# `sbweightedemissionratebyage`, `sourcebindistribution`, `baserateoutput`,
# `sho` and `MOVESOutput` are read by nothing here except the final comparison.
#
# It remains an ATTRIBUTION tool and not a substitute for the fixture
# comparison: when a `.esm` disagrees with the snapshot, a third implementation
# says whether the document or the specification is wrong.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/process-crankcase-running.md"
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
FIXTURE="process-crankcase-running"
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
