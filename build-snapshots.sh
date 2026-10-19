#!/usr/bin/env bash
# Regenerate the canonical-MOVES characterization snapshots that moves.esm's
# development documents read -- fixtures/, runs/, components/ tests, the
# run-*-oracle.sh scripts and tools/ -- by running each RunSpec through EPA
# MOVES inside the moves-fixture SIF.
#
#   ./build-snapshots.sh                 # every snapshot something here names
#   ./build-snapshots.sh nr-logging-county process-apu-single
#   ./build-snapshots.sh --missing       # only the ones not on disk
#   ./build-snapshots.sh --list          # print the names and stop
#   ./build-snapshots.sh --verify-only   # check every named file exists
#
# WHY THIS EXISTS. The snapshots are DEVELOPMENT scaffolding, not the test of
# record: a RunSpec's oracle in runspecs/ is computed from the default database
# (./movesdb, ./build-movesdb.sh), and the snapshot path is how a calculator was
# first reproduced against MOVES's own execution database before it was lifted
# onto that one. They are ~26-95 MB each and are not kept in this repository's
# git, so this script is the record of how to get them back.
#
# It drives moves.rs's own capture pipeline, unmodified:
# characterization/run-all-fixtures.sh, which runs a RunSpec through
# characterization/apptainer/run-fixture.sh and, for the runs that need a county
# or project input database (the four `-single` runs, scale-project), seeds it
# first through capture-county-snapshot.sh. The RunSpec XMLs and the county
# inputs are moves.rs's characterization/fixtures/ and county-inputs/.
#
# Environment (all optional):
#   MOVES_RS   the moves.rs checkout                      [../moves.rs]
#   OUT        where snapshots are written                [$MOVES_RS/characterization/snapshots]
#              (the documents here read ../moves.rs/characterization/snapshots/<name>/)
#   WORK       per-run MOVES/MariaDB scratch, deleted after [/scratch.local/$USER/snapshot-build]
#   SIF        moves-fixture.sif                          [$MOVES_RS/characterization/apptainer/moves-fixture.sif]
#   FAKEROOT   1 to pass --fakeroot to apptainer (needed where the user has no
#              /etc/subuid entry)                         [1]
#
# Each run takes 1-10 minutes and a few GB of scratch. The SIF must match
# characterization/fixture-image.lock: a snapshot captured with another image
# is not the same oracle, so a mismatch is refused unless FORCE_SIF=1.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MOVES_RS="${MOVES_RS:-../moves.rs}"
OUT="${OUT:-$MOVES_RS/characterization/snapshots}"
WORK="${WORK:-/scratch.local/${USER}/snapshot-build}"
SIF="${SIF:-$MOVES_RS/characterization/apptainer/moves-fixture.sif}"
FAKEROOT="${FAKEROOT:-1}"
RUN_ALL="$MOVES_RS/characterization/run-all-fixtures.sh"
LOCK="$MOVES_RS/characterization/fixture-image.lock"

# Every snapshot name and every snapshot FILE a checked-in document, script or
# tool here refers to. Read from the TRACKED files rather than listed, so a new
# document that starts reading a new snapshot is covered without editing this
# script -- and not from the working tree, where the suite's own scratch
# documents name snapshots that a stale capture once had.
referenced_paths() {
  git grep -hoE 'characterization/snapshots/[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]*' \
       -- '*.esm' '*.sh' '*.py' 2>/dev/null \
    | grep -v '^characterization/snapshots/[^/]*/$' | sort -u
}
referenced_names() {
  git grep -hoE 'characterization/snapshots/[A-Za-z0-9_.-]+/' \
       -- '*.esm' '*.sh' '*.py' 2>/dev/null \
    | sed -E 's#characterization/snapshots/([^/]+)/#\1#' | sort -u
}

verify() {  # <name>...: every file a document names under these snapshots exists
  local missing=0 n p rel
  for n in "$@"; do
    [[ -d "$OUT/$n" ]] || { echo "  missing snapshot: $n" >&2; missing=$((missing + 1)); continue; }
    while read -r p; do
      rel=${p#characterization/snapshots/}
      [[ $rel == "$n/"* ]] || continue
      # a glob or a template placeholder is not a file name
      [[ $rel == *'*'* || $rel == *'{'* ]] && continue
      [[ -e "$OUT/$rel" ]] || { echo "  missing: $OUT/$rel" >&2; missing=$((missing + 1)); }
    done < <(referenced_paths)
  done
  echo "$# snapshot(s) checked under $OUT, $missing named file(s) missing"
  [[ $missing -eq 0 ]]
}

MODE=all
declare -a NAMES=()
for a in "$@"; do
  case "$a" in
    --list) MODE=list ;;
    --missing) MODE=missing ;;
    --verify-only) MODE=verify ;;
    -h|--help) sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "unknown option: $a" >&2; exit 2 ;;
    *) NAMES+=("$a") ;;
  esac
done
[[ ${#NAMES[@]} -gt 0 ]] || mapfile -t NAMES < <(referenced_names)

case "$MODE" in
  list) printf '%s\n' "${NAMES[@]}"; exit 0 ;;
  verify) verify "${NAMES[@]}"; exit $? ;;
  missing)
    declare -a todo=()
    for n in "${NAMES[@]}"; do [[ -d "$OUT/$n" ]] || todo+=("$n"); done
    NAMES=("${todo[@]+"${todo[@]}"}")
    [[ ${#NAMES[@]} -gt 0 ]] || { echo "every snapshot is on disk"; verify $(referenced_names); exit $?; } ;;
esac

[[ -x "$RUN_ALL" ]] || { echo "error: no $RUN_ALL (set MOVES_RS=...)" >&2; exit 2; }
[[ -f "$SIF" ]] || { echo "error: no SIF at $SIF -- build it with moves.rs characterization/apptainer/build-fixture-sif.sh" >&2; exit 2; }
command -v apptainer >/dev/null || { echo "error: apptainer is not on this host" >&2; exit 2; }
for n in "${NAMES[@]}"; do
  [[ -f "$MOVES_RS/characterization/fixtures/$n.xml" ]] \
    || { echo "error: no RunSpec $MOVES_RS/characterization/fixtures/$n.xml" >&2; exit 2; }
done

pinned=$(sed -n 's/^sif_sha256 *= *"\(.*\)"/\1/p' "$LOCK" 2>/dev/null || true)
actual=$(sha256sum "$SIF" | awk '{print $1}')
if [[ "$actual" != "$pinned" && "${FORCE_SIF:-0}" != 1 ]]; then
  echo "error: $SIF ($actual) does not match $LOCK (${pinned:-none}); FORCE_SIF=1 to capture anyway" >&2
  exit 3
fi

mkdir -p "$WORK/tmp" "$OUT"
OUT_ABS="$(cd "$OUT" && pwd)"
WORK_ABS="$(cd "$WORK" && pwd)"
SIF_ABS="$(cd "$(dirname "$SIF")" && pwd)/$(basename "$SIF")"
args=(--sif "$SIF_ABS" --workdir-root "$WORK_ABS" --output-root "$OUT_ABS" --keep-going)
[[ "$FAKEROOT" == 1 ]] && args+=(-f)
for n in "${NAMES[@]}"; do args+=(--include "$n"); done

echo "capturing ${#NAMES[@]} snapshot(s) into $OUT_ABS (scratch $WORK_ABS) ..."
# The host's temp goes to scratch, never /tmp (RAM); the container's stays its
# own /tmp, because apptainer forwards TMPDIR and a host path is not mounted
# inside it (see build-movesdb.sh).
rc=0
( cd "$MOVES_RS/characterization" && TMPDIR="$WORK_ABS/tmp" APPTAINERENV_TMPDIR=/tmp \
    bash ./run-all-fixtures.sh "${args[@]}" ) || rc=$?

# MOVES names its execution and worker databases after the HOST
# (movesexecution1ccc0235_campuscluster_illinois_edu), and the snapshot's table
# files carry that name, so a capture on another node writes files no document
# here names. Rename each new snapshot's host token to the one the tracked
# documents read for that snapshot. The content is unaffected: a table's bytes
# do not depend on the database it was dumped from.
for n in "${NAMES[@]}"; do
  d="$OUT_ABS/$n/tables"; [[ -d $d ]] || continue
  # the token is everything between `db__movesexecution` and the next `__`
  want=$(referenced_paths | grep "^characterization/snapshots/$n/tables/db__movesexecution" \
           | sed -E 's#.*/db__movesexecution##; s#__.*##' | sort -u | head -1)
  have=$(ls "$d" | grep '^db__movesexecution' | sed -E 's#^db__movesexecution##; s#__.*##' | sort -u | head -1)
  [[ -n $want && -n $have && $want != "$have" ]] || continue
  echo "  $n: renaming host token $have -> $want"
  for f in "$d"/db__movesexecution"$have"__* "$d"/db__movesworker"$have"__*; do
    [[ -e $f ]] && mv "$f" "${f/$have/$want}"
  done
done
verify "${NAMES[@]}" || rc=1
[[ $rc -eq 0 ]] && rm -rf "$WORK_ABS"
exit $rc
