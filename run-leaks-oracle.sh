#!/usr/bin/env bash
#
# Run the independent reproduction of `process-evap-leaks` that lives in
# `docs/evap-leaks.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-oracle.sh and ./run-onroad-oracle.sh do for their
# fixtures: one source of truth, and a spec whose code has quietly stopped
# running cannot mislead anyone for long.
#
#   ./run-leaks-oracle.sh
#
# What it proves. It computes the ACTIVITY chain (specification §2.1, A1-A10),
# the cohort structure and its row rule (§2.2, C1-C4), the evaporative
# operating-mode distribution (§2.3, E1-E3) and the calculator itself (§2.4-§2.5,
# L1/L8/L9 and the output row) from the snapshot's own INPUT tables, and
# reproduces
#
#     all  82 rows of `SHO`
#     all  82 rows of `SourceHours`
#     all 125 rows of `sourceBinDistributionFuelUsage`
#     all   2 rows of `FractionOfOperating`      (exactly)
#     all   6 rows of the evap `OpModeDistribution` (exactly)
#     all 128 rows of `MOVESOutput.emissionQuant`
#
# to ~1e-5, which is the reference's own 6-significant-figure column storage
# (§7.1), not accumulated error.
#
# What it takes from the reference: NOTHING. Unlike ./run-onroad-oracle.sh --
# which has to read `baserate_1_2020` because the operating-mode distribution
# that rate needs is computed inside the MOVES worker and dropped -- every
# quantity here is derived, and the six tables named above are compared against
# and never read forward. That is the reason this slice was chosen; see §0.3.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/evap-leaks.md"
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
FIXTURE="process-evap-leaks"
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
echo "  NOTE: nothing above is read from the reference; see $SPEC §6.5."
