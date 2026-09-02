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
#   4. round-trip  — parse → emit → parse is faithful
#   5. join gate   — a `join.on` contraction still costs O(matches), not O(N·M)
#   6. limitations — the known upstream defects in docs/findings/ still fail
#   7. fixtures    — end-to-end comparison against the moves.rs snapshots
#
# Stage 6 has the opposite polarity to the rest and that is deliberate: each
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
# Fixtures whose comparison FAILED but failed in exactly the way tolerance.toml
# records. They pass the gate; they must not be summarised as if they matched.
declare -a SHORTFALLS=()

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

PYTHON="${PYTHON:-python3}"

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

# The comparator is checked by its own falsification suite before it is trusted
# to judge anything. This is not ceremony: two of its three gates are ones a
# passing-by-default bug would hide completely -- measured on this very
# snapshot, dropping four rows leaves the per-pollutant sums agreeing to
# 1.2e-8, well inside the 1e-2 gate, so only the key-set check sees it.

head2 "comparator self-test"
if out=$("$PYTHON" compare-output.py --self-test 2>&1); then
  pass "compare-output.py"
else
  fail "compare-output.py self-test"
  sed 's/^/       /' <<<"$out"
fi

# --- collect documents ----------------------------------------------------
#
# docs/findings/ is excluded from stages 1–3: those files are deliberate repros
# of upstream defects and three of them do not load at all. Stage 5 runs them.
# gates/ is excluded from stage 3 only, because stage 4 runs it and times it.

mapfile -t DOCS < <(find . -name '*.esm' \
  -not -path './.moves/*' -not -path './target/*' -not -path './docs/findings/*' \
  -not -path './.fixtures-run/*' \
  | sort)

if [[ ${#DOCS[@]} -eq 0 ]]; then
  head2 "No .esm documents yet"
  say "  Nothing to run. This is expected before the first component lands."
  # NOT `exit 0`: the comparator self-test above has already run and may have
  # failed. A hardcoded success here discarded that -- the harness reported
  # green with a sabotaged gate, which is the exact failure mode the self-test
  # exists to prevent, reproduced one level up.
  exit $FAILED
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

# fixtures/ is excluded here and run by stage 7 instead: a fixture's
# `url_template` carries a ${MOVES_SNAPSHOTS} placeholder the RUNTIME does not
# substitute, so the checked-in file deliberately cannot ingest and its inline
# tests only mean anything against the materialized copy.
mapfile -t TEST_TARGETS < <(find . -maxdepth 1 -mindepth 1 -type d \
  -not -name '.*' -not -name 'target' -not -name 'gates' -not -name 'docs' \
  -not -name 'tools' -not -name 'fixtures' | sort)

head2 "test (${TEST_TARGETS[*]})"
if "$ESM" test "${TEST_TARGETS[@]}" 2>&1 | sed 's/^/  /'; then
  :
else
  fail "inline tests (see the table above for which)"
fi

# --- 4. round-trip --------------------------------------------------------
#
# parse → emit → parse must be faithful, which is the check that this repo is
# using the format rather than a dialect of it that happens to load.
#
# Each document is round-tripped FROM ITS OWN DIRECTORY, because `esm
# round-trip` resolves a relative `ref` against the process working directory
# instead of the referencing file's directory (finding F7) — unlike `validate`
# and `test`, which get it right. lib/keys.esm is excluded: a layered template
# library does not currently round-trip to a self-contained form (finding F8).
# Both are watched by the tripwire stage.

head2 "round-trip"
for doc in "${DOCS[@]}"; do
  rel="${doc#./}"
  [[ "$rel" == "lib/keys.esm" ]] && continue
  if out=$( cd "$(dirname "$doc")" && "$OLDPWD/$ESM" round-trip "$(basename "$doc")" 2>&1 ); then
    pass "$rel"
  else
    fail "round-trip $rel"
    sed 's/^/       /' <<<"$out"
  fi
done

# --- 5. the join.on scaling gate ------------------------------------------
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

# --- 6. known limitations (tripwire) --------------------------------------
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

# The same positive control for F13, whose two leaves declare the SAME enum
# name with different values. Each must pass on its own, or the collision the
# repro records would be indistinguishable from a broken fixture.
if "$ESM" test docs/findings/F13_enum_leaf_one.esm docs/findings/F13_enum_leaf_two.esm \
     >/dev/null 2>&1; then
  pass "F13 enum leaves (control) pass standalone, so F13 is about the mount"
else
  fail "F13 enum leaves (control) — a leaf fixture is itself broken"
fi

# F18's control, and the reason it is a control and not a repro. F18 was that a
# document-wide element_type narrows INGESTED values, so a ten-digit SCC
# collapses. Upstream resolved it with a PER-VARIABLE element_type -- an
# explicit override, deliberately not an automatic exemption -- so the thing the
# old repro asserted will never be true, and "still fails, as recorded" would be
# false reassurance about a defect that is in fact resolved.
#
# It is two-sided on purpose. Asserting only the overridden key would still pass
# if element_type were ignored altogether, which is the original defect; so the
# same document also asserts an UN-overridden column at the exact binary32 value
# of 0.34. Sabotage-checked both ways: dropping the override collapses both keys
# to 2260001024 (2 fail), and setting the domain to Float64 reads 0.34 instead
# of 0.3400000035762787 (1 fail).
F18_CONTROL=docs/findings/F18_control_float32_key_override.esm
if [[ ! -d "$SNAPSHOTS" ]]; then
  skip "F18 key-override control" "needs the snapshots; none at $SNAPSHOTS"
else
  f18_run="$(mktemp --suffix=.esm)"
  sed "s|\${MOVES_SNAPSHOTS}|$(cd "$SNAPSHOTS" && pwd)|g" "$F18_CONTROL" > "$f18_run"
  if "$ESM" validate "$f18_run" >/dev/null 2>&1 && "$ESM" test "$f18_run" >/dev/null 2>&1; then
    pass "F18 key-override control passes: an overridden key stays exact, and Float32 is still live"
  else
    fail "F18 key-override control — either a per-variable element_type override no longer keeps an ingested ten-digit key exact, or the document is no longer evaluating in Float32. Both are load-bearing for fixtures/nr-logging-county.esm"
  fi
  rm -f "$f18_run"
fi

mapfile -t REPROS < <(find docs/findings -name '*.esm' -not -name 'join_leaf.esm' \
  -not -name 'F3_lib_with_enum.esm' \
  -not -name 'F13_enum_leaf_*.esm' \
  -not -name 'F18_control_float32_key_override.esm' \
  -not -name 'F19_an_infinite_actual_passes_any_assertion.esm' 2>/dev/null | sort)

if [[ ${#REPROS[@]} -eq 0 ]]; then
  say "  none recorded"
else
  for repro in "${REPROS[@]}"; do
    name=$(basename "$repro" .esm)
    # A repro that reads real data carries the same ${MOVES_SNAPSHOTS} placeholder
    # the fixtures do (F15: the runtime resolves neither a variable nor a relative
    # path). Substitute it, or the repro fails to LOAD and the tripwire reads that
    # as "still fails, as recorded" -- the right verdict for the wrong reason,
    # which would hide the defect being fixed.
    if grep -q 'MOVES_SNAPSHOTS' "$repro" 2>/dev/null; then
      if [[ ! -d "$SNAPSHOTS" ]]; then
        skip "$name" "needs the snapshots; none at $SNAPSHOTS"
        continue
      fi
      repro_run="$(mktemp --suffix=.esm)"
      sed "s|\${MOVES_SNAPSHOTS}|$(cd "$SNAPSHOTS" && pwd)|g" "$repro" > "$repro_run"
    else
      repro_run="$repro"
    fi
    if "$ESM" validate "$repro_run" >/dev/null 2>&1 && "$ESM" test "$repro_run" >/dev/null 2>&1; then
      fail "$name NOW PASSES — the defect it records is fixed"
      say "       Read docs/findings/README.md: this unblocks a convention, and"
      say "       the workaround it forced is now dead weight. Remove both."
    else
      pass "$name still fails, as recorded"
    fi
    [[ "$repro_run" != "$repro" ]] && rm -f "$repro_run"
  done
fi

# F19 has the OPPOSITE polarity to every other repro and so cannot go through the
# loop above: it asserts three contradictory values for one cell and PASSES,
# because an assertion whose actual value is +inf is judged vacuously true. The
# tripwire is therefore "still passes" = defect still present. It is excluded
# from REPROS by name so the loop does not read its pass as good news.
#
# This one is watched from here rather than merely written down because it can
# invalidate every OTHER assertion in the repository, including the fixture
# assertions docs/esm-conventions.md §13 relies on to catch a source that
# silently delivered its default.
F19="docs/findings/F19_an_infinite_actual_passes_any_assertion.esm"
if "$ESM" test "$F19" >/dev/null 2>&1; then
  pass "F19_an_infinite_actual_passes_any_assertion still passes WRONGLY, as recorded"
else
  fail "F19_an_infinite_actual_passes_any_assertion NOW FAILS — the defect it records is fixed"
  say "       An infinite actual is now judged against \`expected\`. Read"
  say "       docs/findings/README.md F19: assertions across this tree can now be"
  say "       trusted not to pass on an overflow, and this inverted check can go."
fi

# Two limitations that are CLI behaviours rather than documents, so they are
# checked by command rather than by a repro file.

# F7: `esm round-trip` resolves a relative ref against the process working
# directory, not the referencing file's directory (esm-spec §4.7, §9.7.2).
if "$ESM" round-trip components/deteriorated_emission_rate.esm >/dev/null 2>&1; then
  fail "F7_round_trip_ref_resolution NOW PASSES — the defect it records is fixed"
  say "       Simplify the round-trip stage above: it no longer needs to cd."
else
  pass "F7_round_trip_ref_resolution still fails, as recorded"
fi

# F8: a layered template library does not round-trip to a self-contained form —
# the import edge is consumed but the imported DECLARATION does not survive.
if ( cd lib && "$OLDPWD/$ESM" round-trip keys.esm ) >/dev/null 2>&1; then
  fail "F8_layered_library_round_trip NOW PASSES — the defect it records is fixed"
  say "       Remove the lib/keys.esm exclusion from the round-trip stage."
else
  pass "F8_layered_library_round_trip still fails, as recorded"
fi

# --- 7. fixtures ----------------------------------------------------------
#
# Each fixture under fixtures/ declares the moves.rs snapshot tables it reads as
# `data_sources` and computes MOVESOutput rows from them. It is the only place
# in this repository where a number comes off disk rather than out of a `const`
# array, and it is the level at which this port is compared against the
# reference at all.
#
# THE MATERIALIZATION STEP, AND WHY IT IS NOT A GENERATED DOCUMENT. A
# `url_template` is neither environment-expanded nor resolved relative to the
# referencing file: `file://${MOVES_SNAPSHOTS}/...` is looked up literally and
# `file://../x` eats `..` as the URL host (both measured; see
# docs/findings/README.md F15). So a checked-in fixture cannot name its own
# inputs, and this stage rewrites ONLY the snapshot path into an untracked copy
# under .fixtures-run/. No model logic is generated -- CLAUDE.md's rule is about
# expressions, and the copy differs from the source by one absolute path per
# data source. .fixtures-run/ sits at the repository root so that each fixture's
# relative `../lib/...` template imports resolve exactly as they do from
# fixtures/.

# Located by searching UPWARD, not by a fixed `../`, which is right from the
# canonical checkout and one level too deep from a git worktree under .moves/.
# The failure was silent and had already been fixed twice elsewhere in this
# repository (run-oracle.sh, tools/check-sources.py) before it was noticed here:
# the stage reported "skip -- no snapshots" and the suite went green having
# compared nothing, which is the same shape as the bug the fixture exists to
# catch, one level up.
RUNDIR=".fixtures-run"

# --- data_sources catalogs ------------------------------------------------
#
# Checked against the Parquet directly, with pyarrow, because the runtime's own
# report of a wrong column name is a `default` -- a plausible number with no
# diagnostic attached. This stage is what makes a misspelled `fractionLifeused`
# or a forgotten `float_columns` entry fail where it can be attributed.

head2 "data_sources catalogs"
if out=$("$PYTHON" tools/check-sources.py 2>&1); then
  sed 's/^/  /' <<<"$out"
else
  fail "data_sources catalogs"
  sed 's/^/       /' <<<"$out"
fi

head2 "fixtures"
mapfile -t FIXTURES < <(find fixtures -name '*.esm' 2>/dev/null | sort)

if [[ ${#FIXTURES[@]} -eq 0 ]]; then
  say "  none"
elif [[ ! -d "$SNAPSHOTS" ]]; then
  for f in "${FIXTURES[@]}"; do
    skip "$f" "no snapshots at $SNAPSHOTS (set SNAPSHOTS=...)"
  done
else
  SNAP_ABS="$(cd "$SNAPSHOTS" && pwd)"
  mkdir -p "$RUNDIR"
  for f in "${FIXTURES[@]}"; do
    name=$(basename "$f" .esm)
    if [[ ! -d "$SNAPSHOTS/$name" ]]; then
      fail "fixture $name — no snapshot at $SNAPSHOTS/$name"
      continue
    fi

    # F15 tripwire, in the direction that matters: the CHECKED-IN document must
    # NOT be able to ingest. If it can, `url_template` has grown a portable
    # form and the substitution below is dead weight.
    if "$ESM" test "$f" >/dev/null 2>&1; then
      fail "$name — the checked-in fixture INGESTED without substitution"
      say "       url_template now resolves \${MOVES_SNAPSHOTS} or a relative path"
      say "       (docs/findings/README.md F15). Drop the materialization step."
      continue
    fi

    run="$RUNDIR/$name.esm"
    sed "s|\${MOVES_SNAPSHOTS}|$SNAP_ABS|g" "$f" > "$run"

    # The fixture's own inline assertions, against the real tables. Every one
    # names a value out of docs/nonroad-logging-county.md §6, so a source that
    # silently delivered its `default` fails here rather than at the comparison.
    if out=$("$ESM" test "$run" 2>&1); then
      pass "$name — inline assertions against the snapshot parquet"
      sed -n 's/^ *TOTAL */       assertions: /p' <<<"$out"
    else
      fail "fixture $name — inline assertions"
      sed 's/^/       /' <<<"$out"
      continue
    fi

    # --- emit -------------------------------------------------------------
    #
    # The emitted fields are EVERY variable whose name begins `out_`, read from
    # the document itself rather than listed here, so the output schema is the
    # document's business and adding a column to it does not need a change to
    # this script. `simulate --format csv` writes one row per index tuple with a
    # leading `i1` ordinal, which compare-output.py ignores; every named field
    # must share one shape, which is exactly the constraint that keeps the
    # output a single relation.
    #
    # It runs from $RUNDIR, because `simulate` resolves a relative `ref` against
    # the process working directory rather than the referencing file's (finding
    # F7, the same defect the round-trip stage works around).
    mapfile -t FIELDS < <("$PYTHON" - "$run" <<'PYEOF'
import json, sys
doc = json.load(open(sys.argv[1]))
for model in doc.get("models", {}).values():
    for name in (model.get("variables") or {}):
        if name.startswith("out_"):
            print(name)
PYEOF
)
    if [[ ${#FIELDS[@]} -eq 0 ]]; then
      fail "fixture $name — the document declares no out_* fields to emit"
      continue
    fi
    obs=()
    for f in "${FIELDS[@]}"; do obs+=(--observed "$f"); done

    raw="$RUNDIR/$name.emitted.csv"
    actual="${ACTUAL_DIR:-$RUNDIR}/$name.actual.csv"
    if ! out=$( cd "$RUNDIR" && "$OLDPWD/$ESM" simulate "$name.esm" --time 0 \
                  --format csv "${obs[@]}" --output "$name.emitted.csv" 2>&1 ); then
      fail "fixture $name — emit"
      sed 's/^/       /' <<<"$out" | tail -5
      continue
    fi

    # The document names its output relation's columns `out_<MOVESOutput
    # column>`, per the relation-prefix convention (docs/esm-conventions.md §2);
    # the comparator keys on MOVESOutput's own names. Rewrite the HEADER LINE
    # only -- a column that is not `out_`-prefixed keeps its name and will be
    # reported by the comparator as unrecognised rather than silently matched.
    sed '1s/out_//g' "$raw" > "$actual"

    # --- compare ----------------------------------------------------------
    #
    # The comparator's verdict is unconditional: it fails on a partial key set
    # and nothing here can tell it not to. What tolerance.toml records is what
    # that failure is EXPECTED to be today -- how many rows this fixture emits
    # and how many keys it therefore does not -- and this stage is green only
    # while the failure matches the record exactly, in both directions. A
    # shortfall that grows is a regression; a shortfall that shrinks is progress
    # that has to be written down. Same polarity as the tripwire stage above,
    # and for the same reason: a fixture that quietly compares 12 rows out of
    # 144 and reports "ok" is the failure this repository already hit once.
    if out=$("$PYTHON" compare-output.py --fixture "$name" --actual "$actual" \
               --snapshots "$SNAPSHOTS" 2>&1); then
      pass "$name — compared against the snapshot MOVESOutput, complete"
      sed 's/^/       /' <<<"$out"
      if "$PYTHON" tools/shortfall.py --fixture "$name" --has-record; then
        fail "$name — the comparison now PASSES; delete its [shortfall] record"
        say "       tolerance.toml records an expected shortfall that no longer"
        say "       exists. Remove the record: an unexplained one is an excuse."
      fi
    elif verdict=$("$PYTHON" tools/shortfall.py --fixture "$name" \
                     --tolerance tolerance.toml --report <<<"$out"); then
      pass "$name — $verdict"
      SHORTFALLS+=("$name: $verdict")
      sed 's/^/       /' <<<"$out"
    else
      fail "fixture $name — comparison against the snapshot MOVESOutput"
      sed 's/^/       /' <<<"$out"
      say "       This is NOT the shortfall tolerance.toml records:"
      "$PYTHON" tools/shortfall.py --fixture "$name" --tolerance tolerance.toml \
        --report --explain <<<"$out" | sed 's/^/       /'
    fi
  done
fi

# --- summary --------------------------------------------------------------

head2 "summary"
if [[ $FAILED -eq 0 ]]; then
  if [[ ${#SHORTFALLS[@]} -eq 0 ]]; then
    say "  all green"
  else
    # NOT "all green". A reader who scrolls straight here would otherwise take
    # it to mean the port reproduces the fixture, when a comparison in fact
    # FAILED and was accepted only because it failed exactly as recorded. The
    # gate is honest; the one-line summary has to be too.
    say "  green, with ${#SHORTFALLS[@]} recorded shortfall(s) — NOT a full match:"
    printf '    %s\n' "${SHORTFALLS[@]}"
    say ""
    say "  Each is a comparison that FAILED and was accepted because it failed in"
    say "  exactly the way tolerance.toml [shortfall] records, with a reason. Any"
    say "  other failure, in either direction, is red."
  fi
else
  say "  ${#FAILURES[@]} failure(s):"
  printf '    %s\n' "${FAILURES[@]}"
fi
exit $FAILED
