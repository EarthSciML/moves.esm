#!/usr/bin/env python3
"""Check every `data_sources` declaration against the Parquet file it names.

The CLI cannot load a `data_sources` entry yet (docs/findings/README.md, and
the KNOWN BLOCKER in build-esm.sh), so nothing today would notice a catalog
that names a file that does not exist or a column that is not in it. The
declarations would sit looking correct until ingest lands, and then fail all at
once, at the point where the failures are hardest to attribute.

This reads the files directly with pyarrow and checks four things:

  1. the file the `url_template` resolves to exists;
  2. every column named in `reader_options.float_columns` is really in it;
  3. every such column is really a STRING or integer column -- naming an
     already-float column costs nothing but means the author misread the
     schema, and the sidecar `.meta.json` files disagree with the actual
     Parquet types often enough that this is worth asserting;
  4. no column carrying decimal TEXT that the source PROJECTS is left out of
     `float_columns` -- the mistake that matters, since an unlisted text column
     arrives as a string and any arithmetic on it is wrong or refused. A
     decimal-text column outside the projection is reported as a note and does
     not fail: these tables are wide, and `nrsourceusetype` alone carries 23
     evaporative columns an exhaust chain never reads.

Check 4 is the reason this file exists. Every emission quantity in these
snapshots is a string of decimal text despite the sidecar metadata calling it
float64, so `float_columns` is mandatory rather than an optimization, and
forgetting one column is both easy and silent.

    tools/check-sources.py             # all sources/*.esm
    SNAPSHOTS=... tools/check-sources.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent


def _find_snapshots() -> pathlib.Path:
    """Locate the moves.rs snapshots by searching UPWARD, not by counting.

    `HERE.parent / "moves.rs"` is right from the canonical checkout and wrong
    from a git worktree under `.moves/`, where it resolves one level too deep.
    The failure was silent -- the stage reported "skip: no snapshots" and went
    green while checking nothing, which is the same shape as the bug this file
    exists to catch, and as one already fixed in EarthSciIO's test helpers.
    """
    env = os.environ.get("SNAPSHOTS")
    if env:
        return pathlib.Path(env)
    for parent in [HERE, *HERE.parents]:
        cand = parent / "moves.rs" / "characterization" / "snapshots"
        if cand.is_dir():
            return cand
    return HERE.parent / "moves.rs" / "characterization" / "snapshots"


SNAPSHOTS = _find_snapshots()

# A column whose values look like "12.340000000000" -- a decimal rendered as
# text. Integer-looking text (an ID column stored as a string) is deliberately
# NOT matched: it is a key, not a measurement, and coercing it to float would
# lose exactness on a join.
DECIMAL_TEXT = re.compile(r"^-?\d+\.\d+$")

problems: list[str] = []
notes: list[str] = []


def fail(doc: str, source: str, detail: str) -> None:
    problems.append(f"{doc}: {source}: {detail}")


def resolve(url: str) -> pathlib.Path | None:
    """Resolve a `url_template`. Only `${MOVES_SNAPSHOTS}` is substituted."""
    # The runtime requires an explicit scheme (a bare path fails with
    # "bad url ... missing scheme"); strip it to reach the file on disk.
    if url.startswith("file://"):
        url = url[len("file://"):]
    if "${MOVES_SNAPSHOTS}" in url:
        url = url.replace("${MOVES_SNAPSHOTS}", str(SNAPSHOTS))
    if "{" in url:  # a runtime substitution this checker cannot resolve
        return None
    return pathlib.Path(url)


def check_source(doc_name: str, name: str, entry: dict) -> None:
    import pyarrow.parquet as pq

    ro = entry.get("reader_options") or {}
    # The format is declared in `metadata.esio_format`, NOT in `reader_options`
    # -- the runtime rejects a `format` key there as an unknown reader option
    # (esm-spec §8.9.1), which is how this was found. Flag the old spelling
    # rather than silently skipping a source that would fail at load.
    if "format" in ro:
        fail(doc_name, name, "reader_options carries a 'format' key; the runtime rejects "
                             "that as an unknown reader option. Declare the format as "
                             "metadata.esio_format instead")
    if (entry.get("metadata") or {}).get("esio_format") != "parquet":
        return  # only parquet is checkable here

    url = (entry.get("source") or {}).get("url_template", "")
    path = resolve(url)
    if path is None:
        return  # carries a substitution only the runtime can fill
    if not path.exists():
        fail(doc_name, name, f"file does not exist: {path}")
        return

    schema = pq.ParquetFile(path).schema_arrow
    names = set(schema.names)
    declared = list(ro.get("float_columns") or [])

    for col in declared:
        if col not in names:
            fail(doc_name, name, f"float_columns names {col!r}, which is not a column "
                                 f"(has: {', '.join(sorted(names))})")
            continue
        t = str(schema.field(col).type)
        if t.startswith(("float", "double", "decimal")):
            fail(doc_name, name, f"float_columns names {col!r} but it is already {t} — "
                                 f"the declaration is a no-op and suggests a misread schema")

    # 4. a decimal-text column left out -- but only where leaving it out could
    #    actually hurt. A source with no projection is read whole, and these
    #    snapshots carry wide tables: nrsourceusetype has 23 evaporative columns
    #    (tank, hose, marine, e10) that an EXHAUST chain never reads, all of
    #    them decimal text. Failing on those would be a false alarm, and I got
    #    exactly that on the first run before checking the specification.
    #
    #    So: a column named in the source's projection MUST be declared, and is
    #    a failure; anything else is reported as a note and does not fail. When
    #    a consumer binds a `file_variable` the projection is what will name it,
    #    which is where this becomes load-bearing.
    projection = set(entry.get("select", {}).get("variables") or ro.get("variables") or [])
    missing = []
    for field in schema:
        if field.name in declared or not str(field.type).startswith(("string", "large_string")):
            continue
        try:
            sample = pq.read_table(path, columns=[field.name]).column(field.name).to_pylist()[:64]
        except Exception as exc:  # a column this reader cannot decode is not our business
            fail(doc_name, name, f"could not read column {field.name!r}: {exc}")
            continue
        vals = [v for v in sample if v not in (None, "")]
        if vals and all(DECIMAL_TEXT.match(str(v)) for v in vals):
            missing.append(field.name)
    if missing:
        hard = [c for c in missing if c in projection]
        soft = [c for c in missing if c not in projection]
        if hard:
            fail(doc_name, name,
                 "these columns are in the source's projection and hold decimal TEXT, but "
                 f"are not in float_columns, so they would arrive as strings: {', '.join(hard)}")
        if soft:
            notes.append(f"{doc_name}: {name}: {len(soft)} unprojected decimal-text column(s) "
                         f"not in float_columns — harmless while unread "
                         f"({', '.join(soft[:4])}{', …' if len(soft) > 4 else ''})")


def main() -> int:
    docs = sorted((HERE / "sources").glob("*.esm"))
    if not docs:
        print("  no data_sources catalogs to check")
        return 0
    if not SNAPSHOTS.exists():
        print(f"  skip — no snapshots at {SNAPSHOTS} (set SNAPSHOTS=...)")
        return 0
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        print("  skip — pyarrow is not available to this interpreter")
        return 0

    n = 0
    for doc in docs:
        d = json.loads(doc.read_text())
        for name, entry in (d.get("data_sources") or {}).items():
            n += 1
            check_source(doc.relative_to(HERE).as_posix(), name, entry)

    for line in notes:
        print(f"  note: {line}")
    if problems:
        for line in problems:
            print(f"  {line}")
        return 1
    print(f"  {len(docs)} catalog(s), {n} source(s), all files and columns present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
