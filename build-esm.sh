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
#   2. --config patch.crates-io.earthsciio.path=...
#      Cargo.toml pins `earthsciio = "0.1.2"` from crates.io. The sibling
#      EarthSciIO checkout is ALSO version 0.1.2, so cargo has no reason to
#      prefer it and silently keeps the registry copy -- which has no
#      parquet.rs. Since every MOVES snapshot table is parquet, that alone
#      makes every fixture read nothing. Measured: an aggregate over a real
#      1183-row column summed to 0, with no error.
#
#      We pass this on the command line rather than editing the crate's
#      checked-in .cargo/config.toml, because a committed relative path would
#      break the build for anyone without EarthSciIO as a sibling checkout.
#
#   3. parallel
#      Performance only; safe to drop.
#
# KNOWN BLOCKER (as of EarthSciAST b680f5301): even with 1 and 2, the `esm`
# binary never constructs an esio provider. `PrepareProvider` is supplied by
# the CALLER through `PrepareOptions`, and `src/bin/esm.rs` supplies none --
# `esio_provider` has no in-crate caller outside the library's own tests. So
# no CLI subcommand can load a `data_sources` entry yet, and a data-fed
# parameter stays at its default. Until that is wired upstream, the fixture
# stage of run-tests.sh cannot be trusted to have read anything.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

AST="${AST:-../EarthSciAST}"
IO_REL="../../../EarthSciIO/rust"   # relative to the crate dir, per its Cargo.toml comment

if [[ ! -d "$AST/pkg/earthsci-ast-rs" ]]; then
  echo "error: no EarthSciAST crate at '$AST/pkg/earthsci-ast-rs' (set AST=...)" >&2
  exit 2
fi

echo "building esm from $AST ..."
( cd "$AST/pkg/earthsci-ast-rs" \
  && cargo build --release --features esio,parallel --bin esm \
       --config "patch.crates-io.earthsciio.path=\"$IO_REL\"" )

cp "$AST/pkg/earthsci-ast-rs/target/release/esm" ./esm
echo "installed ./esm ($(./esm --version))"

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

# The EarthSciIO tree patched in over the crates.io 0.1.2 (same version
# number, different content -- the registry copy has no parquet reader).
esio_repo   = EarthSciIO
esio_commit = $(git -C ../EarthSciIO rev-parse HEAD 2>/dev/null || echo 'not a git checkout')
EOF

echo "wrote esm-version.lock"
