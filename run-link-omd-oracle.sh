#!/usr/bin/env bash
#
# Run the independent reproduction of `LinkOperatingModeDistributionGenerator`
# that lives in `docs/link-operating-mode-distribution.md` §6.5.
#
# The script is EXTRACTED from the specification rather than kept as a second
# copy, exactly as ./run-omd-oracle.sh and ./run-meteorology-oracle.sh do: one
# source of truth, and a spec whose code has quietly stopped running cannot
# mislead anyone for long.
#
#   ./run-link-omd-oracle.sh
#
# IT IS HANDED THE SNAPSHOTS DIRECTORY, NOT ONE SNAPSHOT. The module is a
# GENERATOR: it writes execution-database tables and emits no `MOVESOutput`
# row, so there is no fixture whose output it reproduces. What there is
# instead is a scheduling rule and 43 snapshots of which exactly ONE — the
# PROJECT-domain `scale-project` — runs it. The 42 that do not are half the
# evidence; without them "this generator needs PROJECT domain" is a comment.
#
# What it proves. From `link`, `linkSourceTypeHour`, `driveSchedule`,
# `driveScheduleAssoc`, `driveScheduleSecond`, `operatingMode`,
# `physicsOperatingMode`, `sourceUseTypePhysicsMapping`, `opModePolProcAssoc`,
# `runSpecHourDay` and `runSpecSourceType` -- and nothing else -- it
# recomputes:
#
#     OpModeDistribution        122 cells over three link ids (the real link
#                               and the two negative pseudo-links the
#                               generator writes for its bracketing schedules)
#     RatesOpModeDistribution    21 cells, at the LINK's road type
#
# and asserts:
#
#     the key sets              0 missing / 0 extra, EXACTLY -- a property of
#                               the model, not a tolerance
#     every cell                equal to the reference's own six-significant-
#                               digit FLOAT rendering, which is stricter than
#                               tolerance.toml's 2e-5 per-cell budget and is
#                               what the corpus can actually support
#     the row counts            >= 122 and >= 80 and >= 21, FLOORS rather than
#                               equalities: silent skipping can only make them
#                               go down, and the corpus is shared with the
#                               other rungs and grows (docs/esm-conventions.md
#                               §35.5)
#     the five-decimal quotient bit-exact on all 80 bracketing cells --
#                               MariaDB's `int * 1.0 / int` with the default
#                               div_precision_increment, NOT a double and NOT
#                               the four decimals its sibling generator gets
#     the FLOAT narrowing       asserted at BOTH ends: the single-precision
#                               round-trip must reproduce every cell, and the
#                               double alternative must still miss at least
#                               one. If the corpus ever stopped separating
#                               them this fails rather than passing vacuously.
#     the scheduling predicate  `OpModeDistribution` populated <=> the RunSpec
#                               is PROJECT domain, on every snapshot (43 of 43
#                               today, one positive and 42 negative)
#
# IT TAKES NOTHING FROM THE REFERENCE. `OpModeDistribution` and
# `RatesOpModeDistribution` are read only to compare against and, for the
# scheduling predicate, to decide which runs produced rows.
#
# It remains an ATTRIBUTION tool and not a substitute for the component's
# inline assertions: when `components/link_operating_mode_distribution.esm`
# disagrees with the snapshot, a third implementation says whether the
# document or the specification is wrong.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEC="docs/link-operating-mode-distribution.md"
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

if ! out=$("$PYTHON" "$WORK/repro.py" "$SNAP_ABS" 2>&1); then
  echo "  FAILED" >&2
  sed 's/^/  /' <<<"$out" >&2
  exit 1
fi
sed 's/^/  /' <<<"$out"
echo "  NOTE: three of the four paths through step 100, both out-of-bounds"
echo "        bracket flags, a non-zero link grade and a source mass that"
echo "        differs from the fixed mass factor are all unexercised --"
echo "        see $SPEC sections 8.1 and 8.4."
