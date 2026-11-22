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

  5. a row count stated at the START of the entry's `note` matches the file.
     Fixtures are authored by copying a sibling's spine, so a note travels
     with the structure while the table under it changes; four notes were
     wrong this way when the check was added, two of them still naming
     `brakewear` inside the NOx fixture. Numerics passing says nothing about
     whether the prose describes this snapshot.

  6. a polProcessID the note names is really in the table. Check 5 catches a
     copied note whose count is wrong; this catches one whose count is right
     by coincidence, which is how a note claiming brakewear's polProcessID
     survived in the NOx fixture -- both tables have 23 rows.

  7. a `runspecs/` document's Rate-of-Progress setting is its RunSpec's. MOVES
     writes the RunSpec's `<internalcontrolstrategies>` nowhere in the execution
     database, so the model reads it from `db_runspecinternalcontrolstrategy`,
     which a RunSpec turning the strategy on declares itself and every other
     inherits empty (PLAN.md §7.3.81). A document that forgot the declaration
     would be read as strategy-off, silently; this compares it with the fixture
     XML under `../moves.rs/characterization/fixtures/`, where one exists.

  8. a `runspecs/nonroad/` document reads its execution database's NONROAD
     retrofit programs. The catalogue declares `db_nrretrofitfactors` from the
     default database, empty; a run whose input database states programs must
     shadow it with its snapshot's `nrretrofitfactors`, or the model reads the
     run as un-retrofitted (PLAN.md §7.3.84). This compares the row count the
     document reads with the snapshot's.

  9. a `runspecs/nonroad/` document reads, table by table, what its run's
     execution database holds (PLAN.md §7.3.86). InputDataManager.mergeNonRoad
     copies every NonroadTableFilter.csv table from each user and domain input
     database ahead of the default (a user nrFuelSupply REPLACES the default),
     so the snapshot's execution copy is what MOVES read; the model reads the
     default database unless the document shadows a source. Every row of the
     execution copy must be a row of the source the document reads (exactly:
     decimal text parsed to the source's double, measured equal on all 14
     captures), and for nrFuelSupply every default row at the run's keys must
     be in the copy. MOVES's own rewrites are not input: fuelFormulation is
     compared as DefaultDataMaker leaves it, nrFuelSupply without
     DefaultDataMaker's default-formulation fills, and the tables PreAggSTATE /
     PreAggNATION rewrite at state and nation scale are skipped -- and REFUSED
     when the run names a user or domain database, which their rewrite hides.
     A run whose supply reaches a formulation DefaultDataMaker re-files to
     another subtype is refused too (F108).

 10. a `runspecs/nonroad/` document declares its RunSpec's output settings
     (`db_runspecoutputsettings`, written by tools/nonroad-output-settings.py)
     whenever they are not the ones the model emits: the breakdown, the
     geographic detail and the mass unit are in the RunSpec XML only, and the
     model counts what it is told (`run_outputSettingUnported`).

    tools/check-sources.py             # every .esm that declares data_sources
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
# A row-count claim opening a `data_sources` note: "222 rows.", "1 row,".
ROW_CLAIM = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)\s+rows?\b")
# polProcessIDs a note names: "all polProcessID 9101", "polProcessID 118, 119".
POLPROCESS = re.compile(r"polProcessID[s]?\s+((?:\d+)(?:\s*(?:,|and|/)\s*\d+)*)")

problems: list[str] = []
notes: list[str] = []


def fail(doc: str, source: str, detail: str) -> None:
    problems.append(f"{doc}: {source}: {detail}")


def resolve(url: str, doc_dir: pathlib.Path) -> pathlib.Path | None:
    """Resolve a `url_template` the way the RUNTIME does, against `doc_dir`.

    `doc_dir` is the directory of the document that DECLARED the template, not
    the process working directory and not the repo root. That is esm-spec
    §4.7's rule for a `ref`, extended to `url_template` when finding F15
    landed, and this function used to get it wrong: it returned a bare relative
    `Path`, which Python then resolves against the CWD.

    The consequence was 64 false "file does not exist" reports against two
    fixtures whose paths are correct and which ingest those very files
    successfully on every suite run. It went unnoticed because this checker is
    not wired into `run-tests.sh` -- it now is.

    That is the same defect as findings F7 and F15, in the tool this repository
    wrote to catch data-source mistakes. Worth stating plainly: a CWD-anchored
    path is the failure this repo has now met four times, and the fourth was
    its own checker.
    """
    # The runtime requires an explicit scheme (a bare path fails with
    # "bad url ... missing scheme"); strip it to reach the file on disk.
    if url.startswith("file://"):
        url = url[len("file://"):]
    if "${MOVES_SNAPSHOTS}" in url:
        url = url.replace("${MOVES_SNAPSHOTS}", str(SNAPSHOTS))
    if "{" in url:  # a runtime substitution this checker cannot resolve
        return None
    path = pathlib.Path(url)
    # Lexical, against the declaring document's directory (RFC 3986 §5.2.4 dot
    # segments, never `realpath`), which is what F15 made normative.
    return path if path.is_absolute() else (doc_dir / path).resolve()


# Facts that depend only on the FILE, not on the entry that names it. Two
# documents may legitimately name the same table -- a fixture and a mount that
# configures the same component do exactly that -- and re-deriving these for
# the second one reads the file again to reach the same answer. Keyed by
# resolved path, so the saving is automatic rather than a special case.
_file_facts: dict[pathlib.Path, dict] = {}


def file_facts(path: pathlib.Path) -> dict:
    import pyarrow.parquet as pq

    hit = _file_facts.get(path)
    if hit is None:
        pf = pq.ParquetFile(path)
        hit = {"schema": pf.schema_arrow, "num_rows": pf.metadata.num_rows, "polprocess": None}
        _file_facts[path] = hit
    return hit


def polprocess_values(path: pathlib.Path) -> set:
    import pyarrow.parquet as pq

    facts = file_facts(path)
    if facts["polprocess"] is None:
        facts["polprocess"] = set(
            pq.read_table(path, columns=["polProcessID"]).column("polProcessID").to_pylist()
        )
    return facts["polprocess"]


_decimal_text: dict[tuple, object] = {}


def is_decimal_text(path: pathlib.Path, column: str):
    """Whether a column's leading values are all decimal TEXT.

    Depends only on the file and the column, never on which entry is asking,
    so it is cached: the same wide table named by two documents samples each
    of its string columns once. Returns None if the column could not be read,
    and the caller reports that.
    """
    import pyarrow.parquet as pq

    key = (path, column)
    if key in _decimal_text:
        return _decimal_text[key]
    try:
        # Only the first 64 values are ever inspected, so read only those.
        # This used to be `read_table(...).to_pylist()[:64]`, which pulled the
        # WHOLE column into Python and threw all but 64 away -- once per
        # undeclared string column, so a wide table was read end to end a
        # dozen times over to look at its first few rows.
        batch = next(iter(pq.ParquetFile(path).iter_batches(batch_size=64, columns=[column])), None)
        sample = batch.column(column).to_pylist() if batch is not None else []
    except Exception as exc:  # a column this reader cannot decode is not our business
        _decimal_text[key] = exc
        return exc
    vals = [v for v in sample if v not in (None, "")]
    verdict = bool(vals) and all(DECIMAL_TEXT.match(str(v)) for v in vals)
    _decimal_text[key] = verdict
    return verdict


def check_source(doc_name: str, doc_dir: pathlib.Path, name: str, entry: dict) -> None:
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
    path = resolve(url, doc_dir)
    if path is None:
        return  # carries a substitution only the runtime can fill
    if not path.exists():
        fail(doc_name, name, f"file does not exist: {path}")
        return

    schema = file_facts(path)["schema"]
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
        verdict = is_decimal_text(path, field.name)
        if isinstance(verdict, Exception):
            fail(doc_name, name, f"could not read column {field.name!r}: {verdict}")
            continue
        if verdict:
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


    # 5. a leading row-count claim in the note must match the Parquet.
    #
    #    By convention nearly every note here opens by stating the table's
    #    size -- "222 rows. Model year to model-year GROUP..." -- and 409 of
    #    them across nine fixtures did so when this check was written. That
    #    convention is what makes the check possible AND what makes it
    #    necessary, because a fixture is authored by copying a sibling's spine
    #    and the note travels with the structure while the table underneath it
    #    changes.
    #
    #    It found four wrong ones the day it was added, all inherited:
    #    process-nox-speciation carried brakewear's counts for
    #    pollutantprocessmodelyear (222 where its own table has 444),
    #    fleetavgadjustment (11 where it has 9) and temperatureadjustment (1
    #    where it has 4) -- two of them still saying the word "brakewear"
    #    inside the NOx fixture -- and process-refueling carried the same 222
    #    against a 777-row table. Every one of those fixtures matched its
    #    snapshot to the row and to 1e-6, which is the point: numbers passing
    #    says nothing about whether the prose describes THIS snapshot, and
    #    nothing else in this suite reads the prose at all.
    #
    #    Only a claim that OPENS the note is checked. Numbers later in a note
    #    are about subsets, other tables, or other fixtures ("222 in the
    #    brakewear and tirewear slices"), and checking those would be a
    #    guessing game with false alarms. A note that opens with a count is
    #    making a claim about the file this entry names, and nothing else.
    m = ROW_CLAIM.match((entry.get("metadata") or {}).get("note", "").strip())
    if m:
        claimed = int(m.group(1).replace(",", ""))
        actual = file_facts(path)["num_rows"]
        if claimed != actual:
            fail(doc_name, name,
                 f"the note opens by claiming {m.group(1)} row(s), but "
                 f"{path.name} has {actual}. A note that travels with copied "
                 f"structure describes the snapshot it was written for, not "
                 f"this one")

    # 6. a polProcessID the note names must actually be in the table.
    #
    #    Check 5 catches a copied note whose COUNT is wrong. It cannot catch
    #    one whose count happens to be right, and that is not hypothetical:
    #    process-nox-speciation's fullacadjustment note said "23 rows, all
    #    polProcessID 9101. Brakewear has none, so its A/C increment is exactly
    #    0" -- and both snapshots' tables have exactly 23 rows, so check 5 
    #    passed it. The NOx table holds polProcessID 301, not 9101.
    #
    #    That one mattered more than a wrong count, because it gave the wrong
    #    REASON for a right number. Brakewear's A/C increment is 0 because the
    #    table has no row for its pollutant-process; NOx's is 0 because the
    #    rows ARE there and the activity term clamps. A reader who trusted the
    #    note would believe the LEFT JOIN was load-bearing where it is not.
    #
    #    So: if a note names polProcessIDs and the file has that column, at
    #    least one named ID must be present. "At least one" rather than "all",
    #    because notes legitimately contrast their own table with a sibling's
    #    ("222 in the brakewear and tirewear slices"), and demanding every
    #    mentioned ID be present would punish exactly the cross-references
    #    that make these documents readable.
    note_text = (entry.get("metadata") or {}).get("note", "")
    mentions = list(POLPROCESS.finditer(note_text))
    if mentions and "polProcessID" in names:
        claimed = set()
        for m in mentions:
            claimed |= {int(x) for x in re.findall(r"\d+", m.group(1))}
        actual = polprocess_values(path)
        # Every mention, not just the first, and every bare integer besides.
        # `search()` read only the leading `polProcessID` phrase, so a note
        # whose first such phrase belongs to a CONTRAST failed even when it
        # named its own rows perfectly well elsewhere -- which is the opposite
        # of what the comment above promises. process-pm-exhaust's
        # sourcetypepolprocess note opens "2 rows, one for each RATED
        # pollutant-process -- 11201 and 11801 --" and later contrasts "the
        # mirror image of process-evap-permeation, whose polProcessID 111 says
        # `N`". Its own IDs are named without the `polProcessID` token in front
        # of them, and the sibling's is named with it, so the check read the
        # note as being about 111 alone and failed a note that is entirely
        # right. Hence `named_anywhere`: a note that writes any of this table's
        # own IDs, tagged or not, is talking about this table.
        named_anywhere = {int(x) for x in re.findall(r"\d+", note_text)}
        # An EMPTY table cannot contain any ID, so "at least one present" is
        # unsatisfiable and this check must not fire. The emptiness is itself
        # what such a note is about, and naming the polProcessID whose rows are
        # missing is the useful part of it -- process-airtoxics' generalfuelratio
        # note says "ZERO rows in this snapshot ... FuelEffectsGenerator
        # evaluated none of them into generalfuelratio for polProcessID 101",
        # which is precisely right and which the first version of this check
        # reported as a failure. Found by running the check against a fixture
        # written after it, which is the only way that class of false positive
        # surfaces.
        if actual and claimed and not (claimed & actual) \
                and not (named_anywhere & actual):
            fail(doc_name, name,
                 f"the note names polProcessID {sorted(claimed)}, none of "
                 f"which is in {path.name} (it has "
                 f"{sorted(actual)[:8]}). A right row count does not make a "
                 f"copied note right about whose rows they are")

ROP_CLASS = ("gov.epa.otaq.moves.master.implementation.ghg.internalcontrolstrategies."
             "rateofprogress.RateOfProgressStrategy")


def xml_rate_of_progress(xml: pathlib.Path) -> bool:
    """RateOfProgressStrategy.acceptTSV over the RunSpec's strategy entries."""
    import xml.etree.ElementTree as ET
    root = ET.parse(xml).getroot().find("internalcontrolstrategies")
    for node in (root if root is not None else []):
        if node.get("classname") != ROP_CLASS:
            continue
        for line in (node.text or "").strip("\r\n").splitlines()[:4]:
            parts = line.split("\t")
            if not line:
                break
            if parts[0].strip().lower() == "useparameters":
                if len(parts) > 1 and parts[1].strip().lower() == "yes":
                    return True
                break
    return False


def check_rate_of_progress(rel: str, doc: pathlib.Path, d: dict) -> None:
    xml = SNAPSHOTS.parent / "fixtures" / (doc.stem + ".xml")
    if not rel.startswith("runspecs/") or rel.startswith("runspecs/nonroad/") or not xml.exists():
        return
    want = xml_rate_of_progress(xml)
    entry = (d.get("data_sources") or {}).get("db_runspecinternalcontrolstrategy")
    have = False
    if entry is not None:
        import pyarrow.parquet as pq
        path = resolve((entry.get("source") or {}).get("url_template", ""), doc.parent)
        if path is not None and path.exists():
            t = pq.read_table(path).to_pydict()
            have = any(c == ROP_CLASS and str(u).strip().lower() == "yes"
                       for c, u in zip(t.get("className", []), t.get("useParameters", [])))
    if want != have:
        fail(rel, "db_runspecinternalcontrolstrategy",
             f"{xml.name} turns the Rate-of-Progress strategy {'ON' if want else 'off'}, "
             f"but the document {'does not declare it' if want else 'declares it on'}: "
             f"the model would read the run as strategy-{'off' if want else 'on'}")


def check_nonroad_retrofit(rel: str, doc: pathlib.Path, d: dict) -> None:
    if not rel.startswith("runspecs/nonroad/"):
        return
    snap = sorted((SNAPSHOTS / doc.stem / "tables").glob("db__movesexecution*__nrretrofitfactors.parquet"))
    if not snap:
        return
    import pyarrow.parquet as pq
    want = pq.ParquetFile(snap[0]).metadata.num_rows
    entry = (d.get("data_sources") or {}).get("db_nrretrofitfactors")
    if entry is None:
        catalogue = json.loads((HERE / "moves-nonroad.esm").read_text())
        entry, base = catalogue["data_sources"]["db_nrretrofitfactors"], HERE
    else:
        base = doc.parent
    path = resolve((entry.get("source") or {}).get("url_template", ""), base)
    have = pq.ParquetFile(path).metadata.num_rows if path is not None and path.exists() else None
    if have != want:
        fail(rel, "db_nrretrofitfactors",
             f"the run's execution database holds {want} nrretrofitfactors row(s) and the "
             f"document reads {have}: the model would apply the wrong retrofit programs")


# Check 9. Tables the execution database holds REWRITTEN rather than merged,
# so its copy is not what an input database stated: PreAggSTATE.sql and
# PreAggNATION.sql aggregate them into the state's pseudo-county or the nation
# before NONROAD reads them, which the model does itself from the default
# tables (PLAN.md §7.3.34-7.3.36). Keyed by the run's level: 1 state, 0 nation.
NR_PREAGG = {
    1: {"zonemonthhour", "zone", "regioncounty"},
    0: {"zonemonthhour", "zone", "regioncounty", "nrbaseyearequippopulation", "nrfuelsupply",
        "nrgrowthpatternfinder", "nrmonthallocation", "nrstatesurrogate"},
}
_nr_tables: dict = {}


def _ethanol_subtype(subtype, etoh):
    """DefaultDataMaker.java:54-61: a gasoline-family formulation's subtype by its
    ethanol volume, applied to the execution database before any calculator."""
    if subtype not in (10, 11, 12, 13, 14, 15, 51, 52, 18) or etoh is None:
        return subtype
    for new, lo, hi in ((10, None, 0.10), (12, 9, 12.5), (13, 6, 9), (14, 0.10, 6), (15, 12.5, 17.5),
                        (51, 70.5, 100.0000001), (52, 50.5, 70.5), (18, 17.5, 50.5)):
        if new == 10 and subtype == 11:
            continue  # "and fuelSubtypeID <> 11"
        if (lo is None or etoh >= lo) and etoh < hi:
            return new
    return subtype


def _nr_table(path: pathlib.Path, like=None):
    """A table with lower-cased column names, cast to `like`'s schema (the
    execution database stores FLOAT columns as decimal text, the default
    database's parquet as doubles), a NULL formulation property read as 0."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    key = (path, None if like is None else str(like.schema))
    hit = _nr_tables.get(key)
    if hit is None:
        t = pq.read_table(path)
        t = t.rename_columns([c.lower() for c in t.column_names])
        if "fuelformulation" in path.name.lower():
            # DefaultDataMaker.java:66-80 rewrites the execution copy before any
            # calculator reads it: NULL properties become 0, which is how the model
            # reads a NULL (`fuel_property_or_zero`); volToWtPercentOxy is
            # recalculated, and is 0 there for every formulation without
            # oxygenates, where the model multiplies it by a zero volume; T50, T90,
            # e200 and e300 are filled in, which the model does not read. So the
            # formulation is compared on the columns the model reads, as it reads them.
            import pyarrow.compute as pc
            t = t.select(["fuelformulationid", "fuelsubtypeid", "etohvolume", "mtbevolume", "etbevolume",
                          "tamevolume", "voltowtpercentoxy", "sulfurlevel", "rvp"])
            if like is not None:
                t = t.cast(like.schema)
            t = pa.table({c: (t[c].fill_null(0) if pa.types.is_floating(t[c].type) else t[c])
                          for c in t.column_names})
            oxy = pc.add(pc.add(t["etohvolume"], t["mtbevolume"]), pc.add(t["etbevolume"], t["tamevolume"]))
            t = t.set_column(t.column_names.index("voltowtpercentoxy"), "voltowtpercentoxy",
                             pc.if_else(pc.equal(oxy, 0), pa.scalar(0.0, t["voltowtpercentoxy"].type),
                                        t["voltowtpercentoxy"]))
            # DefaultDataMaker.java:54-61 also re-files a gasoline formulation's
            # subtype by its ethanol volume. The model does not (F108); the
            # formulations it re-files are checked against the run's supply in
            # check_nonroad_inputs, and compared here as MOVES files them.
            sub = [_ethanol_subtype(s, e) for s, e in
                   zip(t["fuelsubtypeid"].to_pylist(), t["etohvolume"].to_pylist())]
            t = t.set_column(t.column_names.index("fuelsubtypeid"), "fuelsubtypeid",
                             pa.array(sub, t["fuelsubtypeid"].type))
        else:
            if "zonemonthhour" in path.name.lower():
                # NONROAD reads the hourly temperature and nothing else of it (the
                # .OPT's daytime mean, and tmin/tmax for evaporation); the humidity
                # columns are 930,816 rows of decimal text it never parses.
                t = t.select(["monthid", "zoneid", "hourid", "temperature"])
            if like is not None:
                t = t.select(like.column_names).cast(like.schema)
        hit = t
        if like is None:  # a model source, which several runs compare against
            _nr_tables[key] = t
    return hit


_nr_rows: dict = {}


def _rows(t):
    import collections
    hit = _nr_rows.get(id(t))
    if hit is not None and hit[0] is t:
        return hit[1]
    rows = collections.Counter(zip(*[t[c].to_pylist() for c in t.column_names]))
    if any(t is v for v in _nr_tables.values()):  # a model source: kept for the next run
        _nr_rows[id(t)] = (t, rows)
    return rows


def check_nonroad_inputs(rel: str, doc: pathlib.Path, d: dict) -> int:
    """Check 9: every table the model reads holds, in the run's execution
    database, nothing the model does not read. Returns the rows found wrong."""
    if not rel.startswith("runspecs/nonroad/"):
        return 0
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    tables = SNAPSHOTS / doc.stem / "tables"
    exec_of = {p.name.split("__")[-1][:-len(".parquet")]: p
               for p in tables.glob("db__movesexecution*__*.parquet")}
    if "runspeccounty" not in exec_of:
        return 0
    catalogue = json.loads((HERE / "moves-nonroad.esm").read_text())
    county = pq.read_table(exec_of["runspeccounty"]).column("countyID").to_pylist()
    level = 0 if county == [0] else (1 if len(county) == 1 and county[0] % 1000 == 0 else 2)
    xml = SNAPSHOTS.parent / "fixtures" / (doc.stem + ".xml")
    has_user_db = False
    if xml.exists():
        import xml.etree.ElementTree as ET
        root = ET.parse(xml).getroot()
        names = [e.get("databasename") or "" for tag in ("databaseselections/databaseselection",
                 "scaleinputdatabase", "inputdatabase") for e in root.findall(tag)]
        has_user_db = any(n.strip() for n in names)
    bad = 0
    for name, entry in catalogue["data_sources"].items():
        table = name[len("db_"):]
        if table.startswith("runspec") or table not in exec_of:
            continue
        own = (d.get("data_sources") or {}).get(name)
        src, base = (own, doc.parent) if own is not None else (entry, HERE)
        path = resolve((src.get("source") or {}).get("url_template", ""), base)
        if path is None or not path.exists():
            continue  # check 1 reports it
        if table in NR_PREAGG.get(level, ()):
            if has_user_db:
                fail(rel, name, f"the run names a user or domain input database, and at "
                     f"{'state' if level == 1 else 'nation'} scale the execution database holds "
                     f"`{table}` as PreAgg{'STATE' if level == 1 else 'NATION'}.sql's rewrite, which "
                     f"cannot show what the input database stated: refused")
                bad += 1
            continue
        model = _nr_table(path)
        try:
            run = _nr_table(exec_of[table], like=model)
        except Exception as e:  # a column the source lacks, or text that is not a number
            fail(rel, name, f"the execution database's `{table}` does not read as the model's source: {e}")
            bad += 1
            continue
        if run.num_rows == model.num_rows and run.equals(model):
            continue
        extra = _rows(run) - _rows(model)
        if table == "nrfuelsupply":
            # DefaultDataMaker.java:166-172 fills a needed-but-missing fuel type with
            # its default formulation at share 1; the model makes the same rows itself
            # (`run_supply_rows`).
            defaults = set(_nr_table(exec_of["nrfueltype"]).column("defaultformulationid").to_pylist()) \
                if "nrfueltype" in exec_of else set()
            cols = run.column_names
            for row in list(extra):
                r = dict(zip(cols, row))
                if r["fuelformulationid"] in defaults and r["marketshare"] == 1.0 and r["marketsharecv"] == 0.0:
                    del extra[row]
            # A user nrFuelSupply REPLACES the default (InputDataManager.java:3822-3826):
            # every default row at the run's fuel region, fuel year and month group
            # must still be there.
            mask = None
            for c, t, c2 in (("fuelregionid", "runspecfuelregion", "fuelRegionID"),
                             ("fuelyearid", "runspecfuelyear", "fuelYearID"),
                             ("monthgroupid", "runspecmonthgroup", "monthGroupID")):
                if t not in exec_of:
                    continue
                vals = pq.read_table(exec_of[t]).column(c2).cast(model[c].type)
                m = pc.is_in(model[c], value_set=vals)
                mask = m if mask is None else pc.and_(mask, m)
            if mask is not None:
                lack = _rows(model.filter(mask)) - _rows(run)
                if lack:
                    fail(rel, name, f"{sum(lack.values())} default nrFuelSupply row(s) at the run's keys are not in "
                         f"its execution database -- a user nrFuelSupply replaced the default, and the model "
                         f"reads the default: e.g. {next(iter(lack))}")
                    bad += sum(lack.values())
        if extra:
            fail(rel, name, f"the run's execution database holds {sum(extra.values())} `{table}` row(s) the model's "
                 f"source does not -- an input database stated them (InputDataManager.mergeNonRoad), and the model "
                 f"would read {path.name} instead: e.g. {next(iter(extra))}")
            bad += sum(extra.values())
    # F108: the model reads a formulation's subtype as the default database states
    # it, MOVES as DefaultDataMaker re-files it. A run whose supply reaches one it
    # re-files (formulations 2675 and 2676, fuel years 2010-2013, one region) is
    # refused until the model re-files too.
    if "nrfuelsupply" in exec_of and "runspecfuelyear" in exec_of:
        ff = pq.read_table(HERE / "movesdb" / "FuelFormulation.parquet",
                           columns=["fuelFormulationID", "fuelSubtypeID", "ETOHVolume"]).to_pylist()
        refiled = {r["fuelFormulationID"] for r in ff
                   if _ethanol_subtype(r["fuelSubtypeID"], r["ETOHVolume"]) != r["fuelSubtypeID"]}
        years = set(pq.read_table(exec_of["runspecfuelyear"]).column("fuelYearID").to_pylist())
        supply = pq.read_table(exec_of["nrfuelsupply"]).to_pylist()
        hit = sorted({int(r["fuelFormulationID"]) for r in supply
                      if int(r["fuelFormulationID"]) in refiled and int(r["fuelYearID"]) in years
                      and float(r["marketShare"] or 0) > 0})
        if hit:
            fail(rel, "db_fuelformulation", f"the run's fuel supply reaches formulation(s) {hit}, whose subtype "
                 f"DefaultDataMaker.java:54-61 re-files by ethanol volume and the model reads as stated (F108)")
            bad += len(hit)
    return bad


def check_nonroad_output_settings(rel: str, doc: pathlib.Path, d: dict) -> None:
    """Check 10: a `runspecs/nonroad/` document declares its RunSpec's output
    settings when they are not the ones the model emits."""
    if not rel.startswith("runspecs/nonroad/"):
        return
    xml = SNAPSHOTS.parent / "fixtures" / (doc.stem + ".xml")
    if not xml.exists():
        return
    import importlib.util
    spec = importlib.util.spec_from_file_location("nos", HERE / "tools" / "nonroad-output-settings.py")
    nos = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nos)
    want = nos.settings(xml)
    departs = nos.departures(xml)
    entry = (d.get("data_sources") or {}).get("db_runspecoutputsettings")
    if entry is None:
        if departs:
            fail(rel, "db_runspecoutputsettings",
                 f"{xml.name} asks for output settings the model does not emit ({', '.join(departs)}), and the "
                 f"document does not declare them: the model would emit its own shape without a count")
        return
    import pyarrow.parquet as pq
    path = resolve((entry.get("source") or {}).get("url_template", ""), doc.parent)
    have = pq.read_table(path).to_pylist() if path is not None and path.exists() else []
    if len(have) != 1 or any(abs(float(have[0].get(c, float("nan"))) - float(v)) > 1e-12 for c, v in want.items()):
        fail(rel, "db_runspecoutputsettings",
             f"the document declares {have} and {xml.name} says {want}")


def main() -> int:
    # Every document that declares `data_sources`, wherever it lives. The
    # catalog used to be a file of its own with no model attached, because
    # nothing could consume it; it is now the fixture's own declaration block,
    # and the checks below are what stop a wrong column name from reaching the
    # runtime as a silent default.
    docs = [p for p in sorted(HERE.rglob("*.esm"))
            if not any(part in {"target"} or part.startswith(".")
                       for part in p.relative_to(HERE).parts[:-1])
            and p.is_file() and '"data_sources"' in p.read_text(encoding="utf-8")]
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
        rel = doc.relative_to(HERE).as_posix()

        # spikes/ reads the DEFAULT MOVES DATABASE, which is 1.1 GB, is not in
        # this repository, and is therefore named by an absolute machine-local
        # path. `run-tests.sh`'s 7a stage skips when it is absent; this checker
        # has to agree, or a checkout without the database fails stage 2 for a
        # missing input rather than for a mistake. Only spikes/ is treated this
        # way: a fixture's snapshot path is repository-relative and its absence
        # IS a mistake.
        if rel.startswith("spikes/"):
            absent = [
                p for p in (resolve((e.get("source") or {}).get("url_template", ""), doc.parent)
                            for e in (d.get("data_sources") or {}).values())
                if p is not None and not p.exists()
            ]
            if absent:
                notes.append(f"{rel} — skipped, the default MOVES database is not at {absent[0]}")
                continue

        for name, entry in (d.get("data_sources") or {}).items():
            n += 1
            check_source(rel, doc.parent, name, entry)
        check_rate_of_progress(rel, doc, d)
        check_nonroad_retrofit(rel, doc, d)
        check_nonroad_inputs(rel, doc, d)
        check_nonroad_output_settings(rel, doc, d)

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
