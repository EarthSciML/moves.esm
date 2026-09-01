#!/usr/bin/env bash
#
# Run every test in this repository.
#
# All model logic lives in .esm documents and all testing goes through the
# EarthSciAST CLI (CLAUDE.md), so this script is the whole test suite:
#
#   1. validate  — every .esm document loads and conforms to the schema
#   2. test      — every .esm document's inline `tests` section passes
#   3. fixtures  — end-to-end comparison against the moves.rs snapshots
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
# Kept untracked in the repo root per CLAUDE.md. Build it with:
#   cargo build --release --features esio,parallel \
#     --manifest-path ../EarthSciAST/pkg/earthsci-ast-rs/Cargo.toml
#   cp ../EarthSciAST/pkg/earthsci-ast-rs/target/release/esm ./esm
#
# `esio` is opt-in; without it `data_sources` load nothing, silently, so the
# fixture stage would pass vacuously. `esm-version.lock` records which
# EarthSciAST commit produced the binary, so a fidelity result is attributable
# to a toolchain.

if [[ ! -x "$ESM" ]]; then
  say "error: no EarthSciAST CLI at '$ESM'."
  say "       See the build command in the comment at the top of this script,"
  say "       or set ESM=/path/to/esm."
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

mapfile -t DOCS < <(find . -name '*.esm' -not -path './.moves/*' -not -path './target/*' | sort)

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

# --- 2. inline tests ------------------------------------------------------

# `esm test` searches a directory recursively and prints its own per-test
# table naming the model and the assertion, so one invocation over the repo
# reports more precisely than a per-file loop could, and the table is the
# report. The solver tolerances are left at their defaults: they govern how
# accurately each test is integrated, not the tolerance its assertions are
# judged against, which each test declares for itself (§6.6.4).

head2 "test (${#DOCS[@]} documents)"
if "$ESM" test . 2>&1 | sed 's/^/  /'; then
  :
else
  fail "inline tests (see the table above for which)"
fi

# --- 3. fixtures ----------------------------------------------------------
#
# Each fixture assembly under fixtures/ reads a moves.rs snapshot through
# `data_sources` and is compared against that snapshot's expected MOVESOutput
# at the tolerances in tolerance.toml.

SNAPSHOTS="${SNAPSHOTS:-../moves.rs/characterization/snapshots}"

head2 "fixtures"
mapfile -t FIXTURES < <(find fixtures -name '*.esm' 2>/dev/null | sort)

if [[ ${#FIXTURES[@]} -eq 0 ]]; then
  say "  none yet"
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
