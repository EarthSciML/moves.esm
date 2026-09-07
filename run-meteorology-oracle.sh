#!/usr/bin/env bash
#
# Run the independent reproduction of `MeteorologyGenerator` that lives in
# `docs/meteorology-generator.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-brakewear-oracle.sh does for its fixture: one source of
# truth, and a spec whose code has quietly stopped running cannot mislead anyone
# for long.
#
#   ./run-meteorology-oracle.sh
#
# IT IS HANDED THE SNAPSHOTS DIRECTORY, NOT ONE SNAPSHOT, and that is the one
# way it differs from its nine siblings. `MeteorologyGenerator` is a GENERATOR:
# it writes three columns of the `ZoneMonthHour` INPUT table and emits no
# `MOVESOutput` row, so there is no single fixture whose output it reproduces.
# What there is instead is a scheduling rule -- it subscribes to processes 1, 2,
# 9, 10, 90 and 91 -- and 40 snapshots that carry the three columns, 21 of which
# ran it and 19 of which did not. Both halves are the claim, so both halves are
# checked, and checking them needs the whole corpus.
#
# What it proves. From `ZoneMonthHour.temperature`, `ZoneMonthHour.relHumidity`,
# `Zone` and `County` -- and nothing else -- it recomputes all 532 populated
# rows' `heatIndex`, `specificHumidity` and `molWaterFraction`, 1,596 cells, and
# asserts:
#
#     the cell count                     >= 1,596, a FLOOR rather than an
#                                        equality: silent skipping can only make
#                                        it go down, and the corpus is shared
#                                        with the other rungs and grows
#                                        (docs/esm-conventions.md 35.5)
#     the key set                        0 missing / 0 extra
#     the worst relative error           < 1e-7  (measured: 2.391e-08)
#     the scheduling predicate           every snapshot agrees (40 of 40 today)
#     the two candidate slopes           distinguishable at > 2e-5
#
# 2.391e-08 is the reference's own twelve-decimal column storage, not
# accumulated error -- two orders tighter than any `MOVESOutput` fixture in this
# repository, because `ZoneMonthHour` stores twelve decimals where
# `emissionQuant` stores six significant figures and there is no chain of
# multiplications in between.
#
# IT TAKES NOTHING FROM THE REFERENCE. `heatIndex`, `specificHumidity` and
# `molWaterFraction` are read only to decide which rows the generator ran on and
# then to compare against.
#
# It remains an ATTRIBUTION tool and not a substitute for the component's inline
# assertions: when `components/meteorology.esm` disagrees with the snapshot, a
# third implementation says whether the document or the specification is wrong.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/meteorology-generator.md"
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
echo "  NOTE: the county default-fill branches are NOT checked here. No county in"
echo "        the corpus has a missing barometricPressure; see $SPEC section 8.1."
