#!/usr/bin/env bash
#
# Run the independent reproduction of `nr-logging-county` that lives in
# `docs/nonroad-logging-county.md` §6.5, and optionally emit its rows in
# MOVESOutput shape for `compare-output.py`.
#
# The script is EXTRACTED from the document rather than kept as a second copy.
# There is one source of truth, the spec stays executable, and a spec whose
# code has quietly stopped running cannot mislead anyone for long.
#
# Why an oracle at all: when an `.esm` eventually disagrees with the snapshot,
# the useful question is whether the `.esm` is wrong or the port specification
# is. A third implementation -- float32 NumPy, straight from the same Parquet
# tables, written independently of both -- answers that. It reproduces all 144
# rows to 4.897e-6.
#
#   ./run-oracle.sh              # run it, assert 144 rows
#   ./run-oracle.sh --emit DIR   # also write DIR/nr-logging-county.actual.csv
#   ./run-oracle.sh --float64    # run it in binary64 (see below)
#
# --float64 exists because the answer changes, and the way it changes is the
# single most important constraint on how the `.esm` must be written. In
# binary64 the chain emits 140 rows, not 144: the `modfrc <= 0` skip inherited
# from `prccty.f` fires exactly once more (31 -> 32), which drops model year
# 2018 of SCC 2260007005 across all four pollutants. The age-loop bound `ny` is
# IDENTICAL in both precisions, so this is not a different iteration count --
# it is one age-distribution cell that is a tiny positive number in binary32 and
# is not in binary64.
#
# The surviving 140 cells still agree to 6.9e-6 and per-pollutant sums to
# 2.6e-6. So the divergence is not a magnitude problem that a looser tolerance
# could absorb; it is a STRUCTURAL one, and only the exact-key-set check sees it.
#
# The rule that follows is NOT "stop reproducing the skip" -- an earlier version
# of this comment said that and it was wrong. Measured: `modfrc < 0` and no skip
# at all both give 188 rows, in BOTH precisions, because 44 age cohorts have
# modfrc exactly zero. The skip is load-bearing. Only ONE cohort is borderline,
# and it is indistinguishable in-document from those 44. The four rows are
# recovered by evaluating in f32, which is why `domain.element_type: "Float32"`
# has to be honoured (PLAN.md 1.6.2). Keep the `modfrc <= 0` skip as written.
#
# ONE CAVEAT ON READING ACROSS TO THE .esm, because this comment used to invite
# the wrong inference. `fixtures/nr-logging-county.esm` declares `Float32` and
# emits twelve rows -- but it emitted the same twelve in binary64. It does not
# execute agedist's fold at all: the recurrence has no spelling in the format
# (finding F12), so the fixture carries the f32 fold's OUTPUT as a `const`,
# `5.8885583e-08` included, and the skip never fires on it in either precision.
# The 144-vs-140 difference below is this script's, not the document's. It
# becomes the document's when the other two SCCs land and their folds have to be
# computed rather than carried (PLAN.md 1.6.1a, docs/esm-conventions.md 17.5).

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/nonroad-logging-county.md"
# Locate the snapshots by searching UPWARD rather than by a fixed `../`, which
# is right from the canonical checkout and one level too deep from a git
# worktree under `.moves/`. Same fix as tools/check-sources.py.
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
FIXTURE="nr-logging-county"
PYTHON="${PYTHON:-python3}"

EMIT=""
FLOAT64=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --emit)     EMIT="${2:?--emit needs a directory}"; shift 2 ;;
    --float64)  FLOAT64=1; shift ;;
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

if [[ $FLOAT64 -eq 1 ]]; then
  # The script's own assertion is a float32 claim; in binary64 it is expected to
  # fail, and the failure is the point.
  sed -i 's/^f = np\.float32$/f = np.float64/' "$WORK/repro.py"
  sed -i 's/^assert n == 144 and worst < 1e-5$//' "$WORK/repro.py"
  echo "  running in binary64 (expect 140 rows, not 144)"
fi

SNAP_ABS="$(cd "$SNAPSHOTS/$FIXTURE" && pwd)"

if [[ -n "$EMIT" ]]; then
  mkdir -p "$EMIT"
  EMIT_ABS="$(cd "$EMIT" && pwd)"
  cat > "$WORK/emit.py" <<'PY'
import csv, pathlib, runpy, sys
repro, snap, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
sys.argv = ["repro.py", snap]
g = runpy.run_path(repro, run_name="__oracle__")

# The chain accumulates in short tons; MOVESOutput is grams. 1.102311e-06 is the
# grams->tons factor the spec's `unitcf.f` port applies, so dividing recovers
# the units the snapshot is in rather than introducing a new constant.
GRAMS_PER_TON = 1.102311e-06
cols = ["MOVESRunID","iterationID","yearID","monthID","dayID","hourID","stateID","countyID",
        "zoneID","linkID","pollutantID","processID","sourceTypeID","regClassID","fuelTypeID",
        "fuelSubTypeID","modelYearID","roadTypeID","SCC","engTechID","sectorID","hpID",
        "emissionQuant","emissionQuantMean","emissionQuantSigma"]
# Constant across this fixture; see compare-output.py, which reports which
# identity columns vary and holds the rest aside.
const = {"MOVESRunID":1,"iterationID":1,"yearID":2020,"monthID":8,"dayID":5,"hourID":0,
         "stateID":26,"countyID":26161,"zoneID":"","linkID":"","processID":1,
         "sourceTypeID":"","regClassID":"","fuelTypeID":1,"fuelSubTypeID":"",
         "roadTypeID":100,"engTechID":"","sectorID":"","hpID":"",
         "emissionQuantMean":"","emissionQuantSigma":""}
out = pathlib.Path(outdir) / "nr-logging-county.actual.csv"
with out.open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
    for (pol, scc, my), v in sorted(g["totals"].items()):
        w.writerow({**const, "pollutantID": pol, "SCC": scc, "modelYearID": my,
                    "emissionQuant": repr(float(v) / GRAMS_PER_TON)})
print(f"  wrote {out} ({len(g['totals'])} rows)")
PY
  ( cd "$SNAP_ABS/../.." && "$PYTHON" "$WORK/emit.py" "$WORK/repro.py" "$SNAP_ABS" "$EMIT_ABS" )
  exit $?
fi

( cd "$SNAP_ABS/../.." && "$PYTHON" "$WORK/repro.py" "$SNAP_ABS" )
