#!/usr/bin/env bash
# Build the canonical-moves SIF that ./build-movesdb.sh dumps the MOVES default
# database from: EPA MOVES at a pinned commit, MariaDB seeded with
# movesdb20241112, the NONROAD build. It drives moves.rs's own
# characterization/apptainer/build-sif.sh, whose pins (files/versions.env:
# MOVES_COMMIT, MOVESDB_SHA256, MariaDB, JDK and Go versions) are the source of
# truth, and adds only what running it from here needs:
#
#   ./build-sif.sh            # verify the pinned SIF; build it only if it is missing
#   ./build-sif.sh --force    # rebuild even though a SIF is present
#
# Environment (all optional):
#   MOVES_RS            the moves.rs checkout                         [../moves.rs]
#   SCRATCH             build context, apptainer temp and cache       [/scratch.local/$USER/sif-build]
#   MOVESDB_LOCAL_PATH  a local movesdb20241112.zip or directory to seed from
#                       (passed through; SHA-verified against the pin)
#
# WHY THE TEMP DIRECTORIES ARE SET: upstream's script makes its build context
# with a bare `mktemp -d`, and apptainer unpacks into APPTAINER_TMPDIR and
# caches layers in APPTAINER_CACHEDIR -- by default /tmp and ~. On this cluster
# /tmp is RAM, and the image is over 1 GB before its MariaDB seed is unpacked.
#
# WHY IT REFUSES BY DEFAULT: moves.rs's characterization/canonical-image.lock
# pins the SIF by SHA-256, and says a rebuild that changes the hash is "a
# deliberate cutover" that invalidates its characterization snapshots. A
# rebuild is not bit-reproducible (timestamps, package mirrors), so this does
# not overwrite a SIF that verifies against the lock unless asked to; when it
# does rebuild, upstream's script rewrites that lock, and the diff in moves.rs
# is the record that it happened.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MOVES_RS="${MOVES_RS:-../moves.rs}"
SCRATCH="${SCRATCH:-/scratch.local/${USER}/sif-build}"
BUILD="$MOVES_RS/characterization/apptainer/build-sif.sh"
SIF="$MOVES_RS/characterization/apptainer/canonical-moves.sif"
LOCK="$MOVES_RS/characterization/canonical-image.lock"
FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

[[ -f "$BUILD" ]] || { echo "error: no $BUILD (set MOVES_RS=...)" >&2; exit 2; }
command -v apptainer >/dev/null || { echo "error: apptainer is not on this host" >&2; exit 2; }

pinned=$(sed -n 's/^sif_sha256 *= *"\(.*\)"/\1/p' "$LOCK" 2>/dev/null || true)
if [[ -f "$SIF" && $FORCE -eq 0 ]]; then
  echo "checking $SIF against $LOCK ..."
  actual=$(sha256sum "$SIF" | awk '{print $1}')
  if [[ -n "$pinned" && "$actual" == "$pinned" ]]; then
    echo "ok: the pinned SIF is present ($actual); nothing to build"
    exit 0
  fi
  echo "error: $SIF does not match the lock (sif $actual, lock ${pinned:-none})." >&2
  echo "       Rebuild with --force, which replaces it and rewrites the lock." >&2
  exit 3
fi

mkdir -p "$SCRATCH/tmp" "$SCRATCH/apptainer-tmp" "$SCRATCH/apptainer-cache"
echo "building $SIF (temp and cache under $SCRATCH) ..."
TMPDIR="$SCRATCH/tmp" \
APPTAINER_TMPDIR="$SCRATCH/apptainer-tmp" \
APPTAINER_CACHEDIR="$SCRATCH/apptainer-cache" \
OUTPUT="$(cd "$(dirname "$SIF")" && pwd)/$(basename "$SIF")" \
  bash "$BUILD"
echo "built $SIF ($(sha256sum "$SIF" | awk '{print $1}')); $LOCK now records it"
rm -rf "$SCRATCH/tmp" "$SCRATCH/apptainer-tmp"
