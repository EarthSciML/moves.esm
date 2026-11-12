#!/usr/bin/env bash
#
# Run the independent reproduction of `ProjectTAG`'s outputs that lives in
# `docs/project-tag.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, as ./run-link-omd-oracle.sh does: one source of truth.
#
#   ./run-project-tag-oracle.sh
#
# It is handed the snapshots directory and moves.rs's RunSpec XMLs, not one
# snapshot. From each PROJECT-domain run's link, linkSourceTypeHour,
# offNetworkLink, avft, sourceTypeAgeDistribution, dayOfAnyWeek, hourDay and
# runSpec* tables -- and nothing else -- it recomputes SHO and distance, Starts,
# SHP, SourceHours and hotelling hours (ProjectTAG.java:354-519) and asserts
# each key set exact and every FLOAT cell equal to the reference's binary32,
# six-digit rendering (the DOUBLE hotellingHours within 1e-6). It also asserts the scheduling: linkSourceTypeHour is
# populated on exactly the PROJECT-domain runs.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/project-tag.md"
# Locate the snapshots by searching UPWARD rather than by a fixed `../`, which
# is right from the canonical checkout and one level too deep from a git
# worktree.
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

XMLS="$(cd "$SNAP_ABS/../fixtures" && pwd)"
if ! out=$("$PYTHON" "$WORK/repro.py" "$SNAP_ABS" "$XMLS" 2>&1); then
  echo "  FAILED" >&2
  sed 's/^/  /' <<<"$out" >&2
  exit 1
fi
sed 's/^/  /' <<<"$out"
echo "  NOTE: a missing age distribution is unexercised; the non-positive-speed"
echo "        arm (project-zerospeed) and a walked schedule's speed (project-"
echo "        driveschedule) are reached -- see $SPEC section 6.6. All five outputs are"
echo "        ported (act_projectSho, st_projectStarts, act_projectShp,"
echo "        act_projectSourceHours, hot_projectHours)."
