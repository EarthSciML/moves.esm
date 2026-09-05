#!/usr/bin/env bash
#
# Run the independent reproduction of `process-refueling` that lives in
# `docs/process-refueling.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-onroad-oracle.sh does for `mixed-onroad`: one source of
# truth, and a spec whose code has quietly stopped running cannot mislead
# anyone for long.
#
#   ./run-refueling-oracle.sh
#
# What it proves. It computes the WHOLE chain from the snapshot's own INPUT
# tables -- the activity half, the cohort structure, the drive-cycle
# operating-mode weights W, the Total Energy Consumption spine the refueling
# formulae chain off, and REFEC-1 through REFEC-8 of RefuelingLossCalculator.sql
# -- and reproduces all 82 rows of `sho` and all 336 rows of `MOVESOutput` to
# ~7e-6, which is the reference's own 6-significant-figure column storage
# (specification §7.1) and not accumulated error.
#
# It also asserts the two things a row count cannot see (§7.2): that the two
# energy pollutant-processes the road-type join discards contribute exactly
# nothing WHILE the surviving one contributes something, and that both Stage II
# program reductions are 0 -- so a reader cannot mistake a passing comparison for
# a check of the (1 - P) factors.
#
# IT TAKES NOTHING FROM THE REFERENCE. `baserate_1_2020`, `baserateoutput`,
# `sourcebindistribution`, `sho` and `MOVESOutput` are read by nothing here
# except the final comparison.
#
# It remains an ATTRIBUTION tool and not a substitute for the fixture
# comparison: when a `.esm` disagrees with the snapshot, a third implementation
# says whether the document or the specification is wrong.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/process-refueling.md"
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
FIXTURE="process-refueling"
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
