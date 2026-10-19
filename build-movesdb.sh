#!/usr/bin/env bash
# Rebuild ./movesdb -- the Parquet conversion of the MOVES default database that
# every default-database document here reads (moves-onroad.esm,
# moves-nonroad.esm, runspecs/) -- and point the ./movesdb symlink at it.
#
#   ./build-movesdb.sh                  # convert, verify, link
#   ./build-movesdb.sh --verify-only    # check the current ./movesdb, change nothing
#
# It drives moves.rs's own pipeline (PLAN.md §7.3.1), unmodified:
#   1. characterization/default-db-conversion/convert-default-db.sh stage 1 --
#      MariaDB inside the canonical-moves SIF dumps every table of
#      movesdb20241112 to TSV;
#   2. its stage 2 -- the moves-default-db-convert crate writes one monolithic
#      Parquet file per table under the byte-determinism contract, from
#      characterization/default-db-schema/tables.json.
#
# Environment (all optional):
#   MOVES_RS   the moves.rs checkout                 [../moves.rs]
#   WORK       scratch for the TSV dump and the MariaDB runtime, deleted after
#              [/scratch.local/$USER/movesdb-build]
#   DEST       where the Parquet tree is kept         [../movesdb-parquet]
#   DB         the default-DB release                 [movesdb20241112]
#
# WHY DEST IS NOT SCRATCH: the previous ./movesdb pointed into
# /scratch/$USER/agent-7b/, which the cluster purged, and every 7c'/7d/7e
# stage failed with "No such file" until this script existed. Scratch is right
# for the multi-GB TSV dump (never /tmp, which is RAM); the ~520 MB result
# belongs somewhere that is kept.
#
# WHY IT VERIFIES: a conversion that silently skips a table yields a document
# that fails far from the cause. Every `./movesdb/<file>` a checked-in .esm
# names must exist before the link is moved, and the table count must be the
# shipped audit's 237 monolithic files.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MOVES_RS="${MOVES_RS:-../moves.rs}"
WORK="${WORK:-/scratch.local/${USER}/movesdb-build}"
DEST="${DEST:-../movesdb-parquet}"
DB="${DB:-movesdb20241112}"
EXPECTED_TABLES=237

verify() {  # <dir>: every file a document names exists, and the count is the audit's
  local dir=$1 missing=0 n
  n=$(find "$dir" -maxdepth 1 -name '*.parquet' | wc -l)
  while read -r f; do
    if [[ ! -e "$dir/$f" ]]; then echo "  missing: $f" >&2; missing=$((missing + 1)); fi
  done < <(grep -rhoE '"\./movesdb/[^"]+"' --include='*.esm' . 2>/dev/null \
             | sed -E 's#^"\./movesdb/##; s#"$##' | sort -u)
  echo "$dir: $n parquet tables (audit: $EXPECTED_TABLES), $missing named by a document and missing"
  [[ $missing -eq 0 && $n -eq $EXPECTED_TABLES ]]
}

if [[ "${1:-}" == "--verify-only" ]]; then
  [[ -e movesdb ]] || { echo "error: ./movesdb does not resolve ($(readlink movesdb 2>/dev/null || echo 'no link'))" >&2; exit 1; }
  verify movesdb/
  exit $?
fi

CONVERT="$MOVES_RS/characterization/default-db-conversion/convert-default-db.sh"
SIF="$MOVES_RS/characterization/apptainer/canonical-moves.sif"
[[ -x "$CONVERT" ]] || { echo "error: no $CONVERT (set MOVES_RS=...)" >&2; exit 2; }
[[ -f "$SIF" ]] || { echo "error: no SIF at $SIF -- build it with moves.rs characterization/apptainer/build-sif.sh" >&2; exit 2; }
command -v apptainer >/dev/null || { echo "error: apptainer is not on this host" >&2; exit 2; }

mkdir -p "$WORK"
WORK_ABS="$(cd "$WORK" && pwd)"
SIF_ABS="$(cd "$(dirname "$SIF")" && pwd)/$(basename "$SIF")"
SRC="$WORK_ABS/out/$DB"
# A dump that finished (it writes dump-manifest.json last) is reused, so a
# failure in the Parquet stage does not cost the ~10-minute MariaDB dump again.
RESUME=()
if [[ -f "$SRC/_tsv/dump-manifest.json" ]]; then
  echo "reusing the finished TSV dump in $SRC/_tsv"
  RESUME=(--tsv-dir "$SRC/_tsv")
fi
echo "converting $DB in $WORK_ABS (TSV dump + MariaDB runtime) ..."
# The host's temp goes to scratch; the CONTAINER's must be its own /tmp (the
# --writable-tmpfs overlay), because apptainer forwards TMPDIR and a host path
# is not mounted inside it -- MariaDB's InnoDB then aborts with "Unable to
# create temporary file; errno: 2". The script's Parquet stage is a bare
# `cargo run -p moves-default-db-convert`, so it runs from inside moves.rs.
( cd "$MOVES_RS" && TMPDIR="$WORK_ABS" APPTAINERENV_TMPDIR=/tmp bash "$(pwd)/characterization/default-db-conversion/convert-default-db.sh" \
    --sif "$SIF_ABS" --db "$DB" --output "$WORK_ABS/out" "${RESUME[@]}" )
verify "$SRC" || { echo "error: the conversion in $SRC is incomplete; ./movesdb left as it was" >&2; exit 3; }

mkdir -p "$DEST"
DEST_ABS="$(cd "$DEST" && pwd)/$DB"
rm -rf "$DEST_ABS.new"
mkdir -p "$DEST_ABS.new"
# the Parquet tree and its manifest; not the TSV dump
find "$SRC" -mindepth 1 -maxdepth 1 ! -name '_tsv' -exec cp -r {} "$DEST_ABS.new/" \;
verify "$DEST_ABS.new"
rm -rf "$DEST_ABS.old"
[[ -e "$DEST_ABS" ]] && mv "$DEST_ABS" "$DEST_ABS.old"
mv "$DEST_ABS.new" "$DEST_ABS"
rm -rf "$DEST_ABS.old"
ln -sfn "$DEST_ABS" movesdb
rm -rf "$WORK_ABS"
echo "linked ./movesdb -> $DEST_ABS"
