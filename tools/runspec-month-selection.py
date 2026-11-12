#!/usr/bin/env python3
"""Write a MOVES RunSpec's MONTH SELECTION out of its XML, as the one-column
parquet a `runspecs/` document reads for `db_aggregationmonth`.

WHY THIS EXISTS. It is `runspec-day-selection.py`'s twin, for the same reason
one level up. At `<aggregateBy key="Year"/>` MOVES runs PreAggYEAR.sql, which
collapses every month-keyed table over the months the RunSpec SELECTED into
MonthOfAnyYear 0 ("Whole Year"), and from then on the execution database's
month list (`MonthOfAnyYear`, and the months ExecutionRunSpec loads from it)
says month 0 (ExecutionRunSpec.java:424-445). The months the collapse was
weighted over are still in the RunSpec XML, which is the file MOVES was given,
so that is where this reads them (PLAN.md §7.3.65).

`<month key=>` is a 0-BASED index into the sorted month IDs (docs/mixed-onroad.md
§0.1; conventions §96): key 0 is January, and key 12 selects nothing.

usage: runspec-month-selection.py <runspec.xml> <out.parquet>
"""
import sys
import xml.etree.ElementTree as ET

import pandas as pd


def month_ids(xml_path):
    """The months `<month key=>` selects under `<timespan>`, sorted."""
    root = ET.parse(xml_path).getroot()
    span = root.find("timespan")
    if span is None:
        sys.exit("%s: no <timespan>" % xml_path)
    ids = sorted({int(m.attrib["key"]) + 1 for m in span.findall("month")
                  if 0 <= int(m.attrib["key"]) < 12})
    if not ids:
        sys.exit("%s: <timespan> selects no month" % xml_path)
    return ids


def main(xml_path, out_path):
    ids = month_ids(xml_path)
    pd.DataFrame({"monthID": pd.Series(ids, dtype="int64")}).to_parquet(
        out_path, index=False)
    print("%s: monthID %s -> %s" % (xml_path, ids, out_path))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: runspec-month-selection.py <runspec.xml> <out.parquet>")
    sys.exit(main(sys.argv[1], sys.argv[2]))
