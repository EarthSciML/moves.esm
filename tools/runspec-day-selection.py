#!/usr/bin/env python3
"""Write a MOVES RunSpec's DAY SELECTION out of its XML, as the one-column
parquet a `runspecs/` document reads for `db_rateday`.

WHY THIS EXISTS, AND WHY ONLY FOR ONE FIXTURE. A per-fixture document reads its
selections out of its own snapshot's `runspec*` tables -- that is the discipline
PLAN.md §7.1 set, and every one of those tables is MOVES's own record of what
the RunSpec asked for. `aggregateBy` breaks it for exactly one column. When a
RunSpec sets `aggregateBy = Month`, MOVES pre-aggregates the rate-side tables
over the day types the RunSpec SELECTED and then overwrites `RunSpecDay` with
the single synthesized output day, so the execution database records `dayID 0`
and the selection the weights were scoped to is gone. It is still in the RunSpec
XML, which is the file MOVES was given, so that is where this reads it.

The scoping is not a detail: averaging `ZoneMonthHour` over both day types
instead of over the one the RunSpec selected moves `expand-month`'s February
temperature from 26.041854 degF to 26.465902 degF, four thousand times that
column's storage precision, and moves the collapsed `AvgSpeedDistribution` by
6.3e-02 (PLAN.md §7.3.11).

THIS IS AN INTERIM. The right home for the parsed selections is the snapshot,
beside the tables MOVES wrote -- `moves.rs` already has the XML at capture time
and records its sha256 in `provenance.json`. Filed upstream; when the capture
carries it, `runspecs/expand-month.esm` points `db_rateday` at the snapshot like
every other selection and this script and its output go away.

usage: runspec-day-selection.py <runspec.xml> <out.parquet>
"""
import sys
import xml.etree.ElementTree as ET

import pandas as pd


def day_ids(xml_path):
    """The `<day id=>` values under `<timespan>`, sorted.

    MOVES writes the day type ID directly in this attribute (2 weekend,
    5 weekdays) -- unlike `<month key=>` and `<beginhour key=>`, which are
    0-based indices into sorted ID lists (docs/mixed-onroad.md §0.1). The
    `moves.rs` corpus was recaptured for exactly that distinction; see
    docs/esm-conventions.md §42.5.
    """
    root = ET.parse(xml_path).getroot()
    span = root.find("timespan")
    if span is None:
        sys.exit("%s: no <timespan>" % xml_path)
    ids = sorted({int(d.attrib["id"]) for d in span.findall("day")})
    if not ids:
        sys.exit("%s: <timespan> selects no day" % xml_path)
    return ids


def main(xml_path, out_path):
    ids = day_ids(xml_path)
    pd.DataFrame({"dayID": pd.Series(ids, dtype="int64")}).to_parquet(
        out_path, index=False)
    print("%s: dayID %s -> %s" % (xml_path, ids, out_path))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: runspec-day-selection.py <runspec.xml> <out.parquet>")
    sys.exit(main(sys.argv[1], sys.argv[2]))
