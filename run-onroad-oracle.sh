#!/usr/bin/env bash
#
# Run the independent reproduction of `mixed-onroad` that lives in
# `docs/mixed-onroad.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-oracle.sh does for `nr-logging-county`: one source of
# truth, and a spec whose code has quietly stopped running cannot mislead
# anyone for long.
#
#   ./run-onroad-oracle.sh
#
# What it proves, and what it does not. It computes the activity chain
# (specification §2.1, steps S1-S9), the cohort structure and its row-set rule
# (§2.2, S10-S12) and the output stage (§2.4, S16-S18) from the snapshot's own
# INPUT tables, and reproduces all 82 rows of `sho` and all 250 rows of
# `MOVESOutput` to ~1e-5 -- which is the reference's own 6-significant-figure
# column storage (§7.1), not accumulated error.
#
# It takes ONE quantity from the reference: `baserate_1_2020.meanBaseRate`.
# That is deliberate and it is the whole point of §8.1 -- the operating-mode
# distribution the base rate needs is computed inside the MOVES worker and
# dropped, so no captured table carries it. So this oracle is an attribution
# tool for the two thirds of the chain the `.esm` components cover, and it is
# NOT a substitute for the fixture comparison, which cannot run until §8.1
# lands. The output says so.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/mixed-onroad.md"
# Locate the snapshots by searching UPWARD rather than by a fixed `../`, which
# is right from the canonical checkout and one level too deep from a git
# worktree under `.moves/`. Same fix as tools/check-sources.py and run-oracle.sh.
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
FIXTURE="mixed-onroad"
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
echo "  NOTE: the base rate is read from baserate_1_2020; see $SPEC §8.1."
