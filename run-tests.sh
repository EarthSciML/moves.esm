#!/usr/bin/env bash
#
# Run every test in this repository.
#
# All model logic lives in .esm documents and all testing goes through the
# EarthSciAST CLI (CLAUDE.md), so this script is the whole test suite:
#
#   1. validate    — every .esm document loads and conforms to the schema
#   2. conventions — the authoring rules of docs/esm-conventions.md, checked
#                    structurally rather than by eye
#   3. test        — every .esm document's inline `tests` section passes
#   4. join gate   — a `join.on` contraction still costs O(matches), not O(N·M)
#   5. limitations — the known upstream defects in docs/findings/ still fail
#   6. fixtures    — end-to-end comparison against the moves.rs snapshots
#
# Stage 5 has the opposite polarity to the rest and that is deliberate: each
# file under docs/findings/ is a repro whose inline test asserts the behaviour
# we WANT, and which fails today. If one goes green, an upstream defect has been
# fixed and a workaround somewhere in this tree is now dead weight — so the
# suite says so, loudly, instead of letting the workaround rot in place.
#
# Exits non-zero if any stage fails.

set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

ESM="${ESM:-./esm}"
FAILED=0
declare -a FAILURES=()

say()  { printf '%s\n' "$*"; }
head2() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() { FAILED=1; FAILURES+=("$1"); printf '  \033[31mFAIL\033[0m %s\n' "$1"; }
pass() { printf '  \033[32mok\033[0m   %s\n' "$1"; }
skip() { printf '  \033[33mskip\033[0m %s — %s\n' "$1" "$2"; }

# --- the CLI --------------------------------------------------------------
#
# Kept untracked in the repo root per CLAUDE.md; built by ./build-esm.sh, which
# also writes esm-version.lock. Two of that script's three build decisions fail
# SILENTLY — read its header before building by hand.

if [[ ! -x "$ESM" ]]; then
  say "error: no EarthSciAST CLI at '$ESM'."
  say "       Build it with ./build-esm.sh, or set ESM=/path/to/esm."
  exit 2
fi

say "CLI:      $ESM ($("$ESM" --version 2>/dev/null || echo 'version unknown'))"
if [[ -f esm-version.lock ]]; then
  say "built at: $(sed -n 's/^commit *= *//p' esm-version.lock) \
($(sed -n 's/^subject *= *//p' esm-version.lock))"
else
  say "built at: unrecorded (no esm-version.lock)"
fi

# --- collect documents ----------------------------------------------------
#
# docs/findings/ is excluded from stages 1–3: those files are deliberate repros
# of upstream defects and three of them do not load at all. Stage 5 runs them.
# gates/ is excluded from stage 3 only, because stage 4 runs it and times it.

mapfile -t DOCS < <(find . -name '*.esm' \
  -not -path './.moves/*' -not -path './target/*' -not -path './docs/findings/*' \
  | sort)

if [[ ${#DOCS[@]} -eq 0 ]]; then
  head2 "No .esm documents yet"
  say "  Nothing to run. This is expected before the first component lands."
  exit 0
fi

# --- 1. validate ----------------------------------------------------------

head2 "validate (${#DOCS[@]} documents)"
for doc in "${DOCS[@]}"; do
  if out=$("$ESM" validate "$doc" 2>&1); then
    pass "$doc"
  else
    fail "validate $doc"
    sed 's/^/       /' <<<"$out"
  fi
done

# --- 2. conventions -------------------------------------------------------
#
# The rules in docs/esm-conventions.md that a machine can check: no equality
# `filter` standing in for a join, no loop symbol shadowing the independent
# variable, every join clause an `on` clause, lib/ files are template libraries,
# and an assembly's index sets agree with those of every file it mounts. The
# last one stands in for the §4.7 merge the loader does not perform on a
# top-level {ref} edge (docs/findings F2).

head2 "conventions"
if out=$(python3 tools/check-conventions.py 2>&1); then
  printf '%s\n' "$out"
else
  fail "conventions"
  printf '%s\n' "$out"
fi

# --- 3. inline tests ------------------------------------------------------
#
# `esm test` searches a directory recursively and prints its own per-test
# table naming the model and the assertion, so one invocation over the repo
# reports more precisely than a per-file loop could, and the table is the
# report. The solver tolerances are left at their defaults: they govern how
# accurately each test is integrated, not the tolerance its assertions are
# judged against, which each test declares for itself (§6.6.4).

mapfile -t TEST_TARGETS < <(find . -maxdepth 1 -mindepth 1 -type d \
  -not -name '.*' -not -name 'target' -not -name 'gates' -not -name 'docs' \
  -not -name 'tools' | sort)

head2 "test (${TEST_TARGETS[*]})"
if "$ESM" test "${TEST_TARGETS[@]}" 2>&1 | sed 's/^/  /'; then
  :
else
  fail "inline tests (see the table above for which)"
fi

# --- 4. the join.on scaling gate ------------------------------------------
#
# PLAN.md §3 Phase 1: a checked-in assertion that a `join.on` contraction costs
# O(matches) and not O(N·M), so a regression in the equi-join gate — or a join
# that silently falls back to the unfiltered filter path — is caught the day it
# appears.
#
# The gate is a RATIO between two runs on this machine, not an absolute time, so
# it needs no calibration: gates/equijoin_driven.esm contracts 1.0e10 candidate
# pairs under a `join.on`, gates/equijoin_undriven_control.esm contracts 4.0e6
# under an equality `filter` — 2,500x FEWER — and the driven one must still be
# several times faster. Ungated cost is quadratic in N (measured: 0.47 s at
# 1.0e6 pairs, 4.09 s at 9.0e6), so a fallback at 1.0e10 would need minutes.
# Both documents also assert the admitted pair SET, not merely its size.

GATE_MARGIN="${GATE_MARGIN:-4}"

time_ms() {  # time_ms <esm file> -> milliseconds, or "" if its tests failed
  local start end
  start=$(date +%s%N)
  if ! "$ESM" test "$1" >/dev/null 2>&1; then
    return 1
  fi
  end=$(date +%s%N)
  echo $(( (end - start) / 1000000 ))
}

head2 "join.on scaling gate"
if driven_ms=$(time_ms gates/equijoin_driven.esm); then
  if control_ms=$(time_ms gates/equijoin_undriven_control.esm); then
    say "  driven   (1.0e10 candidate pairs, join.on): ${driven_ms} ms"
    say "  ungated  (4.0e6 candidate pairs, filter)  : ${control_ms} ms"
    if (( driven_ms * GATE_MARGIN < control_ms )); then
      pass "driven join is >${GATE_MARGIN}x faster on 2500x the pairs"
    else
      fail "join.on scaling gate — driven ${driven_ms} ms vs ungated ${control_ms} ms"
      say "       The gate is no longer driving enumeration: a contraction over"
      say "       2,500x fewer pairs should not be competitive. See"
      say "       CONFORMANCE_SPEC §5.5.8 and gates/equijoin_driven.esm."
    fi
  else
    fail "join.on scaling gate — the ungated control's own assertions failed"
  fi
else
  fail "join.on scaling gate — the driven document's own assertions failed"
fi

# --- 5. known limitations (tripwire) --------------------------------------
#
# Each file here reproduces an upstream defect and asserts the behaviour we
# want, so it FAILS today. A repro that starts passing is good news that has to
# be acted on — see docs/findings/README.md for what each one unblocks.

head2 "known limitations (expected to fail)"

# The positive control for F1/F2. join_leaf.esm is the relational leaf both of
# those repros mount; on its own it must LOAD, VALIDATE and PASS. Without this,
# a typo in the leaf would make both repros fail for the wrong reason and the
# tripwire would report "still fails, as recorded" about nothing.
if "$ESM" validate docs/findings/join_leaf.esm >/dev/null 2>&1 \
   && "$ESM" test docs/findings/join_leaf.esm >/dev/null 2>&1; then
  pass "join_leaf (control) passes standalone, so F1/F2 are about the mount"
else
  fail "join_leaf (control) — the shared leaf fixture is itself broken"
fi

mapfile -t REPROS < <(find docs/findings -name '*.esm' -not -name 'join_leaf.esm' \
  -not -name 'F3_lib_with_enum.esm' 2>/dev/null | sort)

if [[ ${#REPROS[@]} -eq 0 ]]; then
  say "  none recorded"
else
  for repro in "${REPROS[@]}"; do
    name=$(basename "$repro" .esm)
    if "$ESM" validate "$repro" >/dev/null 2>&1 && "$ESM" test "$repro" >/dev/null 2>&1; then
      fail "$name NOW PASSES — the defect it records is fixed"
      say "       Read docs/findings/README.md: this unblocks a convention, and"
      say "       the workaround it forced is now dead weight. Remove both."
    else
      pass "$name still fails, as recorded"
    fi
  done
fi

# --- 6. fixtures ----------------------------------------------------------
#
# Each fixture assembly under fixtures/ reads a moves.rs snapshot through
# `data_sources` and is compared against that snapshot's expected MOVESOutput
# at the tolerances in tolerance.toml.
#
# NOTE (PLAN.md §1.5, build-esm.sh KNOWN BLOCKER): no CLI subcommand wires a
# PrepareProvider yet, so a `data_sources` entry loads nothing and a comparison
# built on one would pass having read nothing. Until that is fixed upstream,
# this stage must stay empty rather than green — sources/nr_logging_county.esm
# declares the ingest configuration and is deliberately consumed by no component.

SNAPSHOTS="${SNAPSHOTS:-../moves.rs/characterization/snapshots}"

head2 "fixtures"
mapfile -t FIXTURES < <(find fixtures -name '*.esm' 2>/dev/null | sort)

if [[ ${#FIXTURES[@]} -eq 0 ]]; then
  say "  none yet — data_sources ingest is not wired (build-esm.sh, KNOWN BLOCKER)"
elif [[ ! -d "$SNAPSHOTS" ]]; then
  for f in "${FIXTURES[@]}"; do
    skip "$f" "no snapshots at $SNAPSHOTS (set SNAPSHOTS=...)"
  done
else
  for f in "${FIXTURES[@]}"; do
    name=$(basename "$f" .esm)
    if [[ ! -d "$SNAPSHOTS/$name" ]]; then
      fail "fixture $name — no snapshot at $SNAPSHOTS/$name"
      continue
    fi
    if out=$(./compare-fixture.sh "$name" 2>&1); then
      pass "$name"
    else
      fail "fixture $name"
      sed 's/^/       /' <<<"$out"
    fi
  done
fi

# --- summary --------------------------------------------------------------

head2 "summary"
if [[ $FAILED -eq 0 ]]; then
  say "  all green"
else
  say "  ${#FAILURES[@]} failure(s):"
  printf '    %s\n' "${FAILURES[@]}"
fi
exit $FAILED
