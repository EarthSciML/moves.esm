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

# The one repro the tripwire loop cannot judge; see the F25 block below.
F25="${F25:-docs/findings/F25_repro_an_undeclared_operand_is_dropped_when_ingesting.esm}"

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

# `-not -name '.*'` is load-bearing, not tidiness. This list is collected ONCE,
# at the top of the run, and a hidden .esm is by convention transient -- a
# probe, a materialized copy, a half-written scratch file. One that exists now
# and is gone by stage 2 fails the round-trip with "No such file or directory",
# which is the harness reporting on its own bookkeeping rather than on the
# repo. Observed: a concurrent `fixtures/.abs.esm` / `.rel.esm` pair did exactly
# that. Hidden files are not part of the document set.
mapfile -t DOCS < <(find . -name '*.esm' -not -name '.*' \
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

# fixtures/ is excluded here and run by the fixture stage instead -- not
# because it cannot ingest (it can, since F15 landed and a `url_template`
# resolves against its own document), but because that stage does three things
# with it in order: assert, emit, compare. Running its assertions here too
# would just run them twice.
mapfile -t TEST_TARGETS < <(find . -maxdepth 1 -mindepth 1 -type d \
  -not -name '.*' -not -name 'target' -not -name 'gates' -not -name 'docs' \
  -not -name 'tools' -not -name 'fixtures' | sort)

head2 "test (${TEST_TARGETS[*]})"
if "$ESM" test "${TEST_TARGETS[@]}" 2>&1 | sed 's/^/  /'; then
  :
else
  fail "inline tests (see the table above for which)"
fi

# The assertions this stage just ran are audited for whether they CAN fail, by
# `tools/perturbation-audit.py`, which is deliberately NOT part of this suite.
# It perturbs the documents in place and restores them from git, and a hard kill
# mid-run -- which happens -- would leave a perturbed tree behind. That is a bad
# trade to make on every routine run for a property that changes only when
# assertions are added. Run it when they are:
#
#   ./tools/perturbation-audit.py                # components/ and runs/
#   ./tools/perturbation-audit.py fixtures gates # the rest
#
# All 785 currently go red under a 10^-3 nudge, the 102 zero-valued ones
# additively. It refuses to start on a dirty tree.

# --- 4. round-trip --------------------------------------------------------
#
# parse → emit → parse must be faithful, which is the check that this repo is
# using the format rather than a dialect of it that happens to load.
#
# Each document is round-tripped WHERE IT LIVES. It used to be run from its own
# directory, because `esm round-trip` resolved a relative `ref` against the
# process working directory instead of the referencing file's (finding F7) —
# which turned out to be ~17 subcommands rather than one, and to be the
# prerequisite for F15: a CWD-anchored `ref` fails loudly, but a CWD-anchored
# `url_template` resolves, succeeds, and reads a different file. Both are fixed.
# lib/keys.esm is still excluded: a layered template library does not round-trip
# to a self-contained form (finding F8), watched by the tripwire stage.

head2 "round-trip"
for doc in "${DOCS[@]}"; do
  rel="${doc#./}"
  [[ "$rel" == "lib/keys.esm" ]] && continue
  if out=$("$ESM" round-trip "$doc" 2>&1); then
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
# F12's control is gone: components/age_distribution.esm now computes agedist.f's
# fold and guards it with 55 assertions, which is what that control was waiting
# for. What replaced it is F24b, and F24b is a CONTROL rather than a repro,
# because F24 is fixed.
#
# WHAT IT GUARDS, AND WHY IT IS THIS DOCUMENT. F24 was that a causal
# self-reference evaluated under `esm test` and was DEAD whenever the pipeline
# build was taken -- which `esm simulate` takes unconditionally and which any
# ingesting document takes. Fixed upstream at EarthSciAST de784f3f8 by one
# shared sweep both routes call, with a `recurrence_unsupported_form` floor
# under any path that misses it. The upstream author could not verify the
# INGESTION axis, because that build has no parquet reader, and said so instead
# of claiming it. This control is that verification, and it is kept because it
# is the only thing here that covers the axis nothing upstream could.
#
# It is one ingested column wide, and the column is one the recurrence never
# reads -- that is the point: ingesting AT ALL was enough, because providers
# existing set the pipeline flag.
#
# THE CLAMPED COLUMN IS WHAT IT ASSERTS, not the plain one. An unresolved
# self-read came back NaN, which would have been loud -- but `max(NaN, 0.0)`
# returns 0.0, and agedist.f's body IS `max(..., 0)`, so s_clamped read a
# plausible [1, 1, 1, 1] where the document says [1, 3, 7, 15]. That is the
# eighth instance of this repository's characteristic failure and the first
# where the sentinel was MANUFACTURED BY A CLAMP rather than returned by the
# runtime. A check on the NaN column alone would go green the day the sentinel
# changed without the construct working.
F24B_CONTROL=docs/findings/F24b_repro_one_ingested_column_breaks_the_recurrence.esm
if [[ ! -d "$SNAPSHOTS" ]]; then
  skip "F24b recurrence-on-ingest control" "needs the snapshots; none at $SNAPSHOTS"
else
  if "$ESM" validate "$F24B_CONTROL" >/dev/null 2>&1 && "$ESM" test "$F24B_CONTROL" >/dev/null 2>&1; then
    pass "F24b control passes: a recurrence still evaluates in a document that INGESTS"
  else
    fail "F24b control — a causal self-reference no longer evaluates in an ingesting document. components/age_distribution.esm's fold runs on that construct, and this is the axis upstream could not verify"
  fi
fi

F18_CONTROL=docs/findings/F18_control_float32_key_override.esm
if [[ ! -d "$SNAPSHOTS" ]]; then
  skip "F18 key-override control" "needs the snapshots; none at $SNAPSHOTS"
else
  if "$ESM" validate "$F18_CONTROL" >/dev/null 2>&1 && "$ESM" test "$F18_CONTROL" >/dev/null 2>&1; then
    pass "F18 key-override control passes: an overridden key stays exact, and Float32 is still live"
  else
    fail "F18 key-override control — either a per-variable element_type override no longer keeps an ingested ten-digit key exact, or the document is no longer evaluating in Float32. Both are load-bearing for fixtures/nr-logging-county.esm"
  fi
fi

mapfile -t REPROS < <(find docs/findings -name '*.esm' -not -name '.*' -not -name 'join_leaf.esm' \
  -not -name 'F3_lib_with_enum.esm' \
  -not -name 'F13_enum_leaf_*.esm' \
  -not -name 'F18_control_float32_key_override.esm' \
  -not -name 'F24b_repro_one_ingested_column_breaks_the_recurrence.esm' \
  -not -name 'F25_repro_an_undeclared_operand_is_dropped_when_ingesting.esm' \
  2>/dev/null | sort)

if [[ ${#REPROS[@]} -eq 0 ]]; then
  say "  none recorded"
else
  for repro in "${REPROS[@]}"; do
    name=$(basename "$repro" .esm)
    # A repro that reads real data used to need its ${MOVES_SNAPSHOTS} placeholder
    # substituted before it could load, or the tripwire read the load failure as
    # "still fails, as recorded" -- the right verdict for the wrong reason. F15
    # landed, so a repro names its own inputs with a relative path and runs as
    # checked in. It still needs the snapshots to be PRESENT.
    if grep -q 'characterization/snapshots' "$repro" 2>/dev/null \
       && [[ ! -d "$SNAPSHOTS" ]]; then
      skip "$name" "needs the snapshots; none at $SNAPSHOTS"
      continue
    fi
    repro_run="$repro"
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

# F25 is the fourth file the loop above does not run, and for a reason none of
# the other three have: its document is INTENDED to be invalid. The defect is
# that `esm validate` rejects it and `esm test`, on the ingesting path, does
# not -- so `validate` will never start passing, the loop's "both pass" test can
# never fire, and it would report "still fails, as recorded" forever without
# ever noticing the fix. What has to be watched is which of the two answers
# `esm test` gives.
if [[ -f "$F25" ]]; then
  if grep -q 'characterization/snapshots' "$F25" && [[ ! -d "$SNAPSHOTS" ]]; then
    skip "F25 undeclared-operand tripwire" "needs the snapshots; none at $SNAPSHOTS"
  else
    f25_out=$("$ESM" test "$F25" 2>&1 || true)
    if grep -qi "undeclaredFloor" <<<"$f25_out"; then
      # The name is only ever mentioned when the toolchain REFUSES the document,
      # which is the intended behaviour and the thing this finding asks for.
      fail "F25 IS FIXED — the ingesting path now names 'undeclaredFloor' instead of
       dropping it. Remove the repro, retire F25 in docs/findings/README.md, and
       delete this block. The undeclared-name check no longer depends on which
       evaluation path a document takes."
    elif grep -q 'actual=2 expected=10' <<<"$f25_out"; then
      pass "F25 still fails, as recorded — an undeclared operand is dropped when ingesting"
    else
      fail "F25's repro gives neither recorded answer. It should either drop the
       operand (actual=2 expected=10, the defect) or name 'undeclaredFloor' (the
       fix). Something else changed underneath it:"
      sed 's/^/         /' <<<"$f25_out"
    fi
  fi
fi

# One limitation that is a CLI behaviour rather than a document, so it is
# checked by command rather than by a repro file. (F7 was the other, and is
# fixed -- which is why the round-trip stage above no longer has to `cd`.)

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
# THERE IS NO LONGER A MATERIALIZATION STEP. This stage used to rewrite each
# fixture's snapshot path into an untracked copy under .fixtures-run/, because a
# `url_template` was neither environment-expanded nor resolved relative to its
# own document (F15), so a checked-in fixture could not name its own inputs.
# F15 landed: a relative template resolves against the declaring file, so the
# document that runs IS the document that is checked in -- which is what makes
# `esm validate` on it mean anything.
#
# That also removed the reason this stage ran `simulate` from inside
# .fixtures-run/. It did so because `simulate` resolved a relative `ref` against
# the process working directory rather than the referencing file's (F7). F7 is
# fixed too -- and it was the more dangerous of the pair, because a CWD-anchored
# `ref` fails loudly while a CWD-anchored `url_template` resolves, succeeds, and
# reads a different file. .fixtures-run/ now holds only emitted CSV.

# Untracked, and now holding only emitted CSV rather than rewritten documents.
RUNDIR=".fixtures-run"

head2 "fixtures"
mapfile -t FIXTURES < <(find fixtures -name '*.esm' 2>/dev/null | sort)

if [[ ${#FIXTURES[@]} -eq 0 ]]; then
  say "  none"
elif [[ ! -d "$SNAPSHOTS" ]]; then
  for f in "${FIXTURES[@]}"; do
    skip "$f" "no snapshots at $SNAPSHOTS (set SNAPSHOTS=...)"
  done
else
  mkdir -p "$RUNDIR"
  for f in "${FIXTURES[@]}"; do
    name=$(basename "$f" .esm)
    if [[ ! -d "$SNAPSHOTS/$name" ]]; then
      fail "fixture $name — no snapshot at $SNAPSHOTS/$name"
      continue
    fi

    run="$f"

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
    # It runs from the repo root. It used to run from $RUNDIR because `simulate`
    # resolved a relative `ref` against the process working directory (F7); that
    # is fixed, so the document is run where it lives.
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
    if ! out=$("$ESM" simulate "$run" --time 0 \
                  --format csv "${obs[@]}" --output "$raw" 2>&1 ); then
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

# --- the two chains agree ---------------------------------------------------

# runs/nr_logging_county_run.esm and fixtures/nr-logging-county.esm are separate
# documents with separate equations that compute the same four model-year-2020
# rows -- one from mounted component leaves, one from the snapshot Parquet.
# Until this stage nothing compared them: each passed its own gate against its
# own transcribed numbers, at tolerances far tighter than the gap between the
# two. Agreement between independent routes is the check this repo relies on
# most (it is why run-oracle.sh exists), so leaving this pair unchecked was a
# hole.
#
# They evaluate in different precisions on purpose -- the fixture per-operation
# binary32, the assembly binary64 -- so the bound is in ULPS of binary32 rather
# than a relative fraction. Measured: three rows agree bit-exactly and one
# differs by exactly one ulp, which is per-operation rounding versus a single
# final cast. A relative bound loose enough to pass that row would be 1e-7,
# four orders looser than what either document asserts internally.
head2 "the two chains agree"
CHAIN_CSV="${ACTUAL_DIR:-$RUNDIR}/nr-logging-county.actual.csv"
if [[ ! -f "$CHAIN_CSV" ]]; then
  skip "chain cross-check" "the fixture stage produced no $CHAIN_CSV"
else
  if out=$("$PYTHON" tools/cross-check-chain.py "$CHAIN_CSV" 2>&1); then
    pass "runs/ assembly and fixtures/ agree within 1 ulp of binary32"
    sed 's/^/     /' <<<"$out"
  else
    fail "the mounted assembly and the fixture disagree by more than their precision difference explains"
    sed 's/^/       /' <<<"$out"
  fi
fi

# --- independent oracles ----------------------------------------------------

# The four reproductions that live inside the port specifications. Each is
# EXTRACTED from its §6.5 fence at run time and run against the snapshot, so a
# specification whose code has quietly stopped working cannot keep looking
# authoritative -- and each one ASSERTS, so a drift in the snapshot or in a
# spec's arithmetic fails here rather than being discovered the next time
# someone reads the document.
#
# None of them was in this suite until now: four scripts that assert, run by
# nobody, while README quoted their numbers as facts. CLAUDE.md asks this
# script to run all of the tests.
#
# `run-oracle.sh --float64` re-runs the NONROAD reproduction in binary64 rather
# than f32. It is expected to SUCCEED as a script -- the row difference is its
# output, not its exit code -- and it asserts what the whole "binary64 costs
# exactly four rows" argument rests on (docs/nonroad-logging-county.md §7.3,
# PLAN.md §1.6.1a): 140 compared, exactly 4 missing, 0 extra. Printing that is
# not the same as asserting it, and until today it was only printed.
head2 "independent oracles"
if [[ ! -d "$SNAPSHOTS" ]]; then
  skip "oracles" "no snapshots at $SNAPSHOTS (set SNAPSHOTS=...)"
else
  ORACLES=("./run-oracle.sh" "./run-oracle.sh --float64"
           "./run-onroad-oracle.sh" "./run-leaks-oracle.sh")
  for oracle in "${ORACLES[@]}"; do
    if [[ ! -x "${oracle%% *}" ]]; then
      fail "oracle ${oracle} — not executable"
      continue
    fi
    if out=$(SNAPSHOTS="$SNAPSHOTS" $oracle 2>&1); then
      pass "${oracle}"
      # Report the counts each oracle asserts, not its last few lines: the
      # row-set numbers are the point and a tail can scroll them away.
      grep -E "rows compared|worst relative error|key set:|rows,|NOTE:" <<<"$out" \
        | sed 's/^/       /'
    else
      fail "oracle ${oracle} — the independent reproduction no longer agrees with the snapshot"
      sed 's/^/       /' <<<"$out" | tail -12
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
