#!/usr/bin/env python3
"""Re-derive every corpus figure in `docs/omd-generator-reachability.md`.

That note is a MEASUREMENT of the snapshot corpus, and a measurement written
in prose rots the moment the corpus moves. It already said so about itself --
"§35.5's point about writing down the date a corpus-wide figure was true" --
and then proved the point: the `moves-snapshot/v2` recapture with the
`<day id=>` correction roughly halved most of its per-snapshot row counts,
and nothing in the suite noticed. Fourteen of the twenty-three counts in its
two per-snapshot tables were wrong, and both were still sitting there being
read as evidence.

Writing the date down is not enough. This makes the numbers CHECKED: the
document states them, this re-derives them from `$SNAPSHOTS`, and a
disagreement is a test failure. The next corpus change goes red here instead
of silently invalidating the prose.

WHAT IT CHECKS, and how it finds it. Everything is parsed out of the document
by structure, so the note stays the single source of truth and this file holds
no copy of the answers:

  1. the corpus size sentence --
     "**43 snapshot directories, 42 with an `execution-trace.json`**";
  2. the `java_classes[*].kind` histogram -- "`common` (2,451)", one per kind;
  3. the reachability table -- for each row, the generator, the count of
     snapshots that CLASS-LOADED it, the denominator, the execution-database
     table it writes, and the count of snapshots in which THAT GENERATOR both
     ran and left rows in that table -- `loaded AND non-empty`, not the row
     count of the table alone. See "ONE TABLE, SEVERAL GENERATORS" below;
  4. the two per-snapshot row-count tables under "Which snapshots, exactly",
     each a `| snapshot | rows | | snapshot | rows |` grid, keyed by the
     table named in the sentence that introduces it;
  5. the corroboration claim that the `StartOpModeDistribution` snapshots are
     SET-EQUAL to the snapshots carrying `SOMDGOpModes` and a populated
     `StartOpMode` -- the note calls this "three independent corroborations of
     one predicate", so it is checked as one.

ONE TABLE, SEVERAL GENERATORS -- why the with-rows column is an INTERSECTION.
An earlier version of this file derived that column from the table name alone:
"how many snapshots carry a non-empty `OpModeDistribution`". Three of the seven
generators in the table write `OpModeDistribution`, so the moment ONE of them
produced rows -- `LinkOperatingModeDistributionGenerator`, when `scale-project`
joined the corpus -- the table-keyed count read 1 for all three, and the
document would have had to claim that two generators no snapshot ever loaded
had nonetheless written something. `RatesOpModeDistribution` is worse: FOUR
generators write it.

The column now means "snapshots in which this generator was class-loaded AND
the table it writes is non-empty" -- the intersection of the two sets, not the
size of the second. That is the conjunction the document's `reachable?` verdict
actually rests on, and it is what makes the three OMD rows distinguishable:
`Link…` 1, the other two 0.

It is a NECESSARY condition, not a sufficient one: a generator that was loaded
alongside another generator's non-empty output still counts here. Attributing a
ROW to a generator needs the table's own partitioning key (for
`RatesOpModeDistribution` that is `(roadTypeID, avgSpeedBinID)` --
`docs/operating-mode-distribution.md` §6.5), which is a per-table argument this
generic checker cannot make. What the intersection buys is that a generator no
snapshot loaded can no longer be credited with output, which was the actual
failure.

The two per-snapshot grids under "Which snapshots, exactly" stay keyed on the
TABLE, because that is what their introducing sentence says they are: "`X` is
non-empty in N". Those are table measurements and are checked as such.

WHAT IT DELIBERATELY DOES NOT CHECK. The `reachable?` column, and every
sentence of interpretation around the tables. Those are verdicts, not
measurements; they are argued from the numbers and revised by hand. This file
guards the arithmetic underneath them, which is the part that goes stale on
its own.

Row counts come from the Parquet FOOTER (`ParquetFile.metadata.num_rows`),
never `read_table()` -- `StartOpMode` alone is 31,738 rows across nine
snapshots and materialising these has OOMed this machine before.

    tools/check-reachability-counts.py
    SNAPSHOTS=... tools/check-reachability-counts.py
"""

from __future__ import annotations

import glob
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
DOC = HERE / "docs" / "omd-generator-reachability.md"


def _find_snapshots() -> pathlib.Path:
    """Locate the moves.rs snapshots by searching UPWARD, not by counting.

    Same reasoning as tools/check-sources.py: a fixed `../` is right from the
    canonical checkout and one level too deep from a worktree, and the failure
    mode is a green "skip" that checked nothing.
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

problems: list[str] = []
checked = 0


def claim(what: str, stated, measured) -> None:
    """Record one document claim against its re-derived value."""
    global checked
    checked += 1
    if stated != measured:
        problems.append(f"{what}: document says {stated!r}, corpus says {measured!r}")


# ---------------------------------------------------------------- the corpus

def measure_corpus() -> tuple[list[str], list[str]]:
    dirs = sorted(
        d.name for d in SNAPSHOTS.iterdir() if d.is_dir()
    )
    traced = [d for d in dirs if (SNAPSHOTS / d / "execution-trace.json").is_file()]
    return dirs, traced


def measure_loaded(traced: list[str]) -> tuple[dict[str, set[str]], dict[str, int]]:
    """Which snapshots class-loaded each `*Generator`, and the kind histogram."""
    loaded: dict[str, set[str]] = {}
    kinds: dict[str, int] = {}
    for d in traced:
        trace = json.loads((SNAPSHOTS / d / "execution-trace.json").read_text())
        for entry in trace.get("java_classes", []):
            kind = entry.get("kind")
            kinds[kind] = kinds.get(kind, 0) + 1
            short = entry["name"].rsplit(".", 1)[-1]
            if short.endswith("Generator"):
                loaded.setdefault(short, set()).add(d)
    return loaded, kinds


def table_rows(snapshot: str, table: str) -> int | None:
    """Row count of an execution-database table, from the Parquet footer.

    Returns None when the snapshot does not carry the table at all, which is a
    different fact from carrying it empty and is reported as such.
    """
    import pyarrow.parquet as pq

    pattern = f"{SNAPSHOTS}/{snapshot}/tables/db__movesexecution*__{table.lower()}.parquet"
    hits = sorted(glob.glob(pattern))
    if not hits:
        return None
    return sum(pq.ParquetFile(f).metadata.num_rows for f in hits)


def measure_table(dirs: list[str], table: str) -> dict[str, int]:
    """{snapshot: rows} for every snapshot carrying `table` NON-EMPTY."""
    out = {}
    for d in dirs:
        n = table_rows(d, table)
        if n:
            out[d] = n
    return out


# -------------------------------------------------------------- the document

CORPUS_RE = re.compile(
    r"\*\*(\d+) snapshot directories, (\d+) with an\s+`execution-trace\.json`\*\*"
)
# "`common` (2,451)" -- one per kind, inside the Signal 1 paragraph.
KIND_RE = re.compile(r"`(common|framework|master|utils|worker)`\s+\((\d{1,3}(?:,\d{3})*)\)")
# A reachability-table row. Only the leading cells are parsed; the trailing
# `reachable?` verdict is deliberately left alone (see the module docstring).
TABLE_RE = re.compile(
    r"^\|\s*`(\w+Generator)`\s*\|\s*\**(\d+)\**\s*/\s*(\d+)\s*\|"
    r"\s*(.*?)\s*\|\s*(\**\d+\**|—)[^|]*\|"
)
# "`FuelEffectsGenerator` (24 / 42)" -- the eighth generator, named in prose
# below the table rather than in it. Same kind of claim, same check.
PROSE_LOADED_RE = re.compile(r"`(\w+Generator)`\s+\((\d+)\s*/\s*(\d+)\)")
# "| `expand-counties` | 18 | | `process-apu` | 6 |" -- and the ragged last
# row, "| `expand-fueltype-diesel` | 20 | | |".
PAIR_RE = re.compile(r"`([\w-]+)`\s*\|\s*(\d[\d,]*)\s*\|")
# The sentence introducing each per-snapshot grid names its table and its size.
INTRO_RE = re.compile(r"`(\w+)` is non-empty in (\d+)")


def parse_int(s: str) -> int:
    return int(s.replace(",", ""))


def parse_grid(lines: list[str], start: int) -> dict[str, int]:
    """Read the `| snap | rows | | snap | rows |` grid following line `start`."""
    out: dict[str, int] = {}
    seen_table = False
    for line in lines[start:]:
        if line.lstrip().startswith("|"):
            seen_table = True
            if set(line) <= set("|-: \t"):
                continue
            for name, n in PAIR_RE.findall(line):
                out[name] = parse_int(n)
        elif seen_table and line.strip():
            break
    return out


def main() -> int:
    if not DOC.is_file():
        print(f"  error: no document at {DOC}")
        return 2
    if not SNAPSHOTS.is_dir():
        print(f"  skip — no snapshots at {SNAPSHOTS} (set SNAPSHOTS=...)")
        return 0
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        print("  skip — pyarrow is not available to this interpreter")
        return 0

    text = DOC.read_text()
    lines = text.splitlines()

    dirs, traced = measure_corpus()
    loaded, kinds = measure_loaded(traced)

    # 1. the corpus size sentence
    m = CORPUS_RE.search(text)
    if not m:
        problems.append(
            "the corpus-size sentence is gone — expected "
            "'**N snapshot directories, M with an `execution-trace.json`**'"
        )
    else:
        claim("snapshot directories", int(m.group(1)), len(dirs))
        claim("snapshots with an execution-trace.json", int(m.group(2)), len(traced))

    # 2. the java_classes kind histogram
    stated_kinds = {k: parse_int(v) for k, v in KIND_RE.findall(text)}
    if not stated_kinds:
        problems.append("the `java_classes[*].kind` histogram is gone from the document")
    else:
        claim("kinds named in the histogram", sorted(stated_kinds), sorted(kinds))
        for kind in sorted(set(stated_kinds) & set(kinds)):
            claim(f"java_classes kind {kind!r}", stated_kinds[kind], kinds[kind])

    # 3. the reachability table
    seen_generators = 0
    for line in lines:
        m = TABLE_RE.match(line)
        if not m:
            continue
        seen_generators += 1
        gen, n_loaded, denom, writes, n_rows = m.groups()
        claim(f"{gen} class-loaded in", int(n_loaded), len(loaded.get(gen, ())))
        claim(f"{gen} denominator", int(denom), len(traced))
        # `writes` may name several tables ("`SourceHours`, `SHO`") or none
        # ("—"). The stated with-rows count covers the FIRST named table,
        # which is the one the per-snapshot grid below expands.
        named = re.findall(r"`(\w+)`", writes)
        # An em-dash in the with-rows cell means "no table to count", which is
        # a statement about the DAG, not about the corpus — nothing to derive.
        if named and n_rows != "—":
            # INTERSECTED with the class-loaded set, not the bare table count:
            # three of these generators share `OpModeDistribution` and four
            # share `RatesOpModeDistribution`, so a table-keyed count credits
            # every one of them with a sibling's rows. See the module
            # docstring, "ONE TABLE, SEVERAL GENERATORS".
            with_rows = set(measure_table(dirs, named[0])) & loaded.get(gen, set())
            claim(
                f"{gen} snapshots where it ran and `{named[0]}` is non-empty",
                int(n_rows.strip("*")),
                len(with_rows),
            )
    if seen_generators < 7:
        problems.append(
            f"the reachability table lists {seen_generators} generators, expected at least 7"
        )

    # 3b. the eighth generator, counted in prose instead of in the table
    for gen, n_loaded, denom in PROSE_LOADED_RE.findall(text):
        claim(f"{gen} class-loaded in (prose)", int(n_loaded), len(loaded.get(gen, ())))
        claim(f"{gen} denominator (prose)", int(denom), len(traced))

    # 4. the two per-snapshot grids
    grids = 0
    for i, line in enumerate(lines):
        m = INTRO_RE.search(line)
        if not m:
            continue
        table, stated_n = m.group(1), int(m.group(2))
        grids += 1
        measured = measure_table(dirs, table)
        claim(f"`{table}` non-empty in", stated_n, len(measured))
        stated = parse_grid(lines, i)
        claim(f"`{table}` grid: which snapshots", sorted(stated), sorted(measured))
        for snap in sorted(set(stated) & set(measured)):
            claim(f"`{table}` rows in {snap}", stated[snap], measured[snap])
    if grids != 2:
        problems.append(f"found {grids} per-snapshot grids under 'Which snapshots, exactly', expected 2")

    # 5. the three-way set equality the note calls its corroboration
    start_dist = set(measure_table(dirs, "StartOpModeDistribution"))
    for corroborator in ("SOMDGOpModes", "StartOpMode"):
        claim(
            f"snapshots with `{corroborator}` are set-equal to those with "
            "`StartOpModeDistribution`",
            sorted(start_dist),
            sorted(measure_table(dirs, corroborator)),
        )

    if problems:
        for line in problems:
            print(f"  {line}")
        print(f"  {len(problems)} of {checked} document claims no longer hold")
        return 1
    print(
        f"  {checked} claims re-derived from {len(dirs)} snapshot directories "
        f"({len(traced)} traced) — all hold"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
