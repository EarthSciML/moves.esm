#!/usr/bin/env bash
#
# Run the independent reproduction of `expand-day` that lives in
# `docs/expand-day.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-onroad-oracle.sh does for `mixed-onroad`: one source of
# truth, and a spec whose code has quietly stopped running cannot mislead
# anyone for long.
#
#   ./run-expand-day-oracle.sh
#
# What it proves, and it is two things rather than one.
#
# THE CHAIN. It computes S1-S18 from the snapshot's own INPUT tables -- the
# activity half, the cohort structure, the drive-cycle operating-mode weights
# W, S15's adjustments and the output stage -- over BOTH day types, and
# reproduces all 82 rows of `sho` and all 250 rows of `MOVESOutput` to 7.1e-6,
# which is the reference's own 6-significant-figure column storage
# (docs/expand-day.md §7.1) and not accumulated error. It reaches the same
# worst cell, at the same key, as fixtures/expand-day.esm by a completely
# different route.
#
# THE DAY AXIS. `expand-day` is the one snapshot in the corpus that still
# carries both day types (docs/esm-conventions.md §42.5), so it is the only
# place a day-keyed factor can be exercised at more than one value. The last
# section recomputes the answer under three COLLAPSES of that axis --
# noOfRealDays pinned at 5, the divisor dropped, one shared W and one shared
# sho -- and ASSERTS that each moves at least half the output rows by more than
# the fixture's own 2e-5 cell gate. A collapse that changed nothing would mean
# the fixture buys no coverage; the script refuses rather than reporting a pass
# it did not earn, and it refuses outright if `runspecday` is not [2, 5].
#
# IT TAKES NOTHING FROM THE REFERENCE. `baserate_1_2020`, `sho`, `averagespeed`
# and `MOVESOutput` are read by nothing here except the final comparison.
#
# It remains an ATTRIBUTION tool and not a substitute for the fixture
# comparison: when a `.esm` disagrees with the snapshot, a third implementation
# says whether the document or the specification is wrong. It already has --
# docs/mixed-onroad.md §6.5's script omits S15's temperature adjustment, which
# is an exact identity at hour 9 and a 1.54% error on 82 rows at hour 7.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/expand-day.md"
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
FIXTURE="expand-day"
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
