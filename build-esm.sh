#!/usr/bin/env bash
#
# Build the EarthSciAST CLI this repo tests through, and record what it was
# built from.
#
# CLAUDE.md keeps ./esm untracked in the repo root. That makes *how* it was
# built the thing worth checking in, because two of the three build decisions
# below fail SILENTLY -- they produce a working binary that reads no data and
# a test suite that passes having compared nothing.
#
#   1. --features esio
#      `esio` is opt-in. Without it `data_sources` load nothing at all.
#
#   2. an earthsciio WITH A PARQUET READER
#      Every MOVES snapshot table is parquet, so an earthsciio without
#      `src/format/parquet.rs` makes every fixture read nothing. Measured: an
#      aggregate over a real 1183-row column summed to 0, with no error.
#
#      Until 2026-11-01 the crates.io release (0.1.2) had no reader, so this
#      script ALWAYS patched in a sibling EarthSciIO checkout and refused any
#      build that did not use it. EarthSciAST now pins `earthsciio = "0.2.0"`,
#      whose registry copy HAS the reader -- and the always-patch rule then
#      broke the build, because the sibling checkout sat at 0.1.4 on a
#      dependabot branch and a version-mismatched patch is simply not used.
#      The rule had encoded "the registry copy has no parquet" as a fact; the
#      requirement was only ever "whatever gets linked has a parquet reader".
#      So that is what is checked now: after the build, `cargo metadata` names
#      the earthsciio actually resolved, and its source tree must contain the
#      reader. The registry copy is the default; IO=<EarthSciIO checkout>
#      patches a local tree in instead (to test an unreleased EarthSciIO), and
#      then the patch must actually be used.
#
#      The patch is passed on the command line rather than in the crate's
#      checked-in .cargo/config.toml, because a committed relative path would
#      break the build for anyone without EarthSciIO as a sibling checkout.
#
#   3. parallel
#      Performance only; safe to drop.
#
# THE BLOCKER THIS HEADER USED TO CARRY IS GONE (EarthSciAST 72568e8bc,
# 8dd7789ef, 8274f0918). `src/bin/esm.rs` now builds a provider per consumed
# `data_sources` entry, samples a source's `extent` BEFORE closing the
# document's metaparameters, and `simulate --format csv` writes a relational
# document's rows. So 1 and 2 above are no longer merely prudent: with either
# of them wrong the binary reads NOTHING and says so only by returning each
# data-fed parameter's `default`, which is a plausible number. That is why
# run-tests.sh's fixture stage asserts a row COUNT and a key SET and not only a
# tolerance -- see docs/esm-conventions.md §11 and §13.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

AST="${AST:-../EarthSciAST}"

# OPTIONAL: an EarthSciIO checkout to patch in over the registry release. Unset
# (the default), the crate builds against the earthsciio its Cargo.lock names.
# There is deliberately no default path: a default relative to $AST was right
# for a sibling checkout and wrong for a nested git worktree, and patching
# whatever happens to be checked out beside EarthSciAST is how a dependabot
# branch ended up deciding what got linked.
IO="${IO:-}"

# Where the built binary lands. Default is the canonical ./esm that CLAUDE.md
# keeps untracked in the repo root and that run-tests.sh runs. Override it to
# build a comparison binary without disturbing the one the suite uses:
#
#   OUT=./esm.mybranch AST=../EarthSciAST/.moves/mybranch ./build-esm.sh
OUT="${OUT:-./esm}"

if [[ ! -d "$AST/pkg/earthsci-ast-rs" ]]; then
  echo "error: no EarthSciAST crate at '$AST/pkg/earthsci-ast-rs' (set AST=...)" >&2
  exit 2
fi
CFG=()
if [[ -n "$IO" ]]; then
  if [[ ! -d "$IO/rust" ]]; then
    echo "error: IO='$IO' has no EarthSciIO crate at '$IO/rust'" >&2
    exit 2
  fi
  IO_ABS="$(cd "$IO/rust" && pwd)"
  CFG=(--config "patch.crates-io.earthsciio.path=\"$IO_ABS\"")
fi

echo "building esm from $AST ..."
(
  cd "$AST/pkg/earthsci-ast-rs" || exit 2

  # `--config patch...` is SILENTLY IGNORED when Cargo.lock already pins the
  # registry copy: cargo prints "warning: patch ... was not used in the crate
  # graph" and builds the crates.io crate. `cargo update` re-resolves so the
  # patch wins -- or, if the checkout's version does not match the one
  # Cargo.toml asks for, still does not, which the checks below catch.
  if [[ -n "$IO" ]]; then
    cargo update -p earthsciio "${CFG[@]}" >/dev/null 2>&1 || true
  fi

  # A cargo build killed mid-write -- by an OOM, or by a wrapper timeout --
  # leaves a half-written rlib, and the NEXT build fails at link with
  # "undefined hidden symbol: hashbrown::..." or "...serde_json..Value...".
  # The message points at a dependency and has nothing to do with the code, and
  # it has cost real time three times on this project. Detect it and self-heal
  # once rather than making the next person diagnose it again.
  build() { cargo build --release --features esio,parallel --bin esm "${CFG[@]}" 2>&1; }
  out="$(build)"; rc=$?
  if [[ $rc -ne 0 ]] && grep -q "undefined hidden symbol" <<<"$out"; then
    echo "note: stale build artifacts from an interrupted compile; cleaning and retrying" >&2
    rm -rf target/release/incremental target/debug/incremental
    cargo clean -p earthsci-ast >/dev/null 2>&1
    out="$(build)"; rc=$?
  fi
  printf '%s\n' "$out"
  [[ $rc -eq 0 ]] || exit $rc

  # WHICH earthsciio got linked, from cargo itself rather than from a guess
  # about the lock file: its version, its source (registry or path) and the
  # directory its sources are in.
  ESIO="$(cargo metadata --format-version 1 --features esio "${CFG[@]}" 2>/dev/null \
    | python3 -c 'import json, os, sys
p = [p for p in json.load(sys.stdin)["packages"] if p["name"] == "earthsciio"]
if len(p) != 1:
    sys.exit("expected one earthsciio package, found %d" % len(p))
p = p[0]
print(p["version"], p["source"] or "path", os.path.dirname(p["manifest_path"]), sep="\t")')" || {
    echo "error: could not determine which earthsciio the build resolved" >&2
    exit 3
  }
  IFS=$'\t' read -r ESIO_VERSION ESIO_SOURCE ESIO_DIR <<<"$ESIO"

  if [[ -n "$IO" && "$ESIO_DIR" != "$IO_ABS" ]]; then
    echo "error: IO='$IO' was asked for, but earthsciio $ESIO_VERSION resolved to" >&2
    echo "       '$ESIO_DIR' -- the patch was not used (is the checkout's version" >&2
    echo "       the one Cargo.toml asks for?)" >&2
    exit 3
  fi
  # The requirement itself. Without the reader every parquet source reads as
  # nothing, and each data-fed parameter returns its plausible `default`.
  if [[ ! -f "$ESIO_DIR/src/format/parquet.rs" ]]; then
    echo "error: the linked earthsciio ($ESIO_VERSION, $ESIO_SOURCE) has no parquet" >&2
    echo "       reader at '$ESIO_DIR/src/format/parquet.rs'; the binary would read" >&2
    echo "       no MOVES table. Set IO=<an EarthSciIO checkout that has one>." >&2
    exit 3
  fi
  echo "earthsciio $ESIO_VERSION from $ESIO_SOURCE ($ESIO_DIR): parquet reader present"
  printf '%s\t%s\t%s\n' "$ESIO_VERSION" "$ESIO_SOURCE" "$ESIO_DIR" > "${TMPDIR:-/tmp}/build-esm.esio.$$"
) || exit $?
IFS=$'\t' read -r ESIO_VERSION ESIO_SOURCE ESIO_DIR < "${TMPDIR:-/tmp}/build-esm.esio.$$"
rm -f "${TMPDIR:-/tmp}/build-esm.esio.$$"

# WHERE CARGO PUT IT, not where it usually puts it. `CARGO_TARGET_DIR` in the
# environment redirects the build and this copy does not follow, so the `cp`
# below reads whatever the crate's default target/ happens to hold -- which on
# a checkout that has ever been built is a stale binary, copied without
# complaint, and then described by a freshly written esm-version.lock as the
# commit that is checked out. That is this script's own headline failure mode
# reached by a route it did not guard: a working binary that is not the one
# the lock claims. Observed 2026-09-19, installing a ten-hour-old esm over a
# just-merged toolchain.
TARGET_DIR="${CARGO_TARGET_DIR:-$AST/pkg/earthsci-ast-rs/target}"
BIN="$TARGET_DIR/release/esm"
if [[ ! -x "$BIN" ]]; then
  echo "error: cargo reported success but there is no binary at '$BIN'" >&2
  echo "       (CARGO_TARGET_DIR=${CARGO_TARGET_DIR:-unset})" >&2
  exit 3
fi
# And it must not PREDATE the sources it claims to be built from. A binary
# newer than every source is the correct outcome of a no-op rebuild, so the
# test is staleness and not "did this run write it": cargo rightly leaves an
# up-to-date artifact alone.
STALE="$(find "$AST/pkg/earthsci-ast-rs/src" "$AST/pkg/earthsci-ast-rs/Cargo.toml" \
           -newer "$BIN" -print -quit 2>/dev/null)"
if [[ -n "$STALE" ]]; then
  echo "error: '$BIN' is OLDER than the source it would be recorded against" >&2
  echo "       (e.g. $STALE)." >&2
  echo "       cargo wrote somewhere else, and this would install a stale" >&2
  echo "       binary under a freshly written esm-version.lock." >&2
  echo "       (CARGO_TARGET_DIR=${CARGO_TARGET_DIR:-unset})" >&2
  exit 3
fi
cp "$BIN" "$OUT"
echo "installed $OUT ($("$OUT" --version)) from $BIN"

# The lock documents THE canonical binary, so a build to any other path leaves
# it alone. Without this, three concurrent upstream branches building for
# comparison each rewrote ./esm and esm-version.lock in turn -- and the lock's
# whole job is to make a fidelity result attributable to a revision. Observed:
# agents worked around it by hand, leaving esm.base, esm.f31 and esm.f32 beside
# the real binary, which is the same race with worse names.
if [[ "$OUT" != "./esm" ]]; then
  echo "note: not the canonical ./esm, so esm-version.lock is left unchanged"
  exit 0
fi

# The earthsciio record is what cargo resolved, not what IO= asked for: a
# registry release by version, or a patched-in checkout by commit. (It used to
# read "$AST/../EarthSciIO", which for a nested worktree recorded 'not a git
# checkout' about a tree that IS one -- a quiet wrong answer in the record.)
if [[ "$ESIO_SOURCE" == path ]]; then
  ESIO_RECORD="$(git -C "$ESIO_DIR" rev-parse HEAD 2>/dev/null || echo 'not a git checkout')"
else
  ESIO_RECORD="$ESIO_SOURCE"
fi
#
# Note that the heredoc below is UNQUOTED, so it interpolates: a shell
# variable written into a comment inside it lands in the lock file expanded.
cat > esm-version.lock <<EOF
# The EarthSciAST commit that ./esm was built from. Written by build-esm.sh.
#
# ./esm itself is untracked (CLAUDE.md); this file is the checked-in record of
# which upstream tree produced it, so a fidelity result is attributable to a
# revision rather than to "whatever was on main that day". See build-esm.sh for
# why the feature and patch lines below matter -- both fail silently.

repo      = EarthSciAST
commit    = $(git -C "$AST" rev-parse HEAD)
subject   = $(git -C "$AST" log -1 --format=%s)
date      = $(git -C "$AST" log -1 --format=%cI)
version   = $(./esm --version)
features  = esio,parallel

# The earthsciio cargo linked: a crates.io release, or a patched-in EarthSciIO
# checkout (IO=) by commit. build-esm.sh refuses one without a parquet reader.
esio_version = $ESIO_VERSION
esio_source  = $ESIO_RECORD
EOF

echo "wrote esm-version.lock"
