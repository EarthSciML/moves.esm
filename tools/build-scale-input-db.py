#!/usr/bin/env python3
"""Write a scale-input database's own rows as Parquet, from the SQL that defines it.

A MOVES county or project database is a MariaDB database a RunSpec names in
`<scaleinputdatabase>`. The corpus does not ship one as Parquet: moves.rs builds
each one from a `setup-*.sql` under `characterization/county-inputs/` and then
captures only the EXECUTION database MOVES merged it into. This tool turns the
SQL back into the tables a document can mount, and it writes exactly two kinds
of thing:

  * every `INSERT INTO <table> (<columns>) VALUES (...)` -- the rows the SQL
    STATES -- one Parquet file per table, typed by the default database's
    own file for that table (the SQL's `CREATE TABLE ... LIKE` says the schema
    is the default's, and the cast enforces it);
  * `runspecdomain.parquet`, one row: the RunSpec's `<modeldomain value=...>`,
    which is the run's selection that a scale-input database exists to serve
    (MOVES reads the database only for a SINGLE-county or PROJECT domain).

It writes NOTHING for an `INSERT ... SELECT ... FROM movesdb20241112.<t>`: those
rows are the default database's, and a document reads them from `./movesdb`
with the same keys. Whether that is an identity for a given run is a
measurement, not this tool's business -- PLAN.md §7.3.40 records it table by
table for `washtenaw-project`.

A DEFAULT-domain run has no scale-input database, and its document still has
to say which domain it is, so `--default-domain <outdir>` writes the one-row
`runspecdomain.parquet` alone, with MOVES's own name for that domain (`DEFAULT`,
ModelDomain.java's NATIONAL_ALLOCATION).

usage: build-scale-input-db.py <setup.sql> <runspec.xml> <movesdb-dir> <outdir>
       build-scale-input-db.py --default-domain <outdir>
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

import pyarrow as pa
import pyarrow.parquet as pq


def default_schema(movesdb, table):
    """The default database's schema for `table`, matched case-insensitively."""
    for name in os.listdir(movesdb):
        if name.lower() == table.lower() + ".parquet":
            return name[:-len(".parquet")], pq.read_schema(os.path.join(movesdb, name))
    sys.exit("no default-database table matches %r" % table)


def literal(text):
    text = text.strip()
    if text.upper() == "NULL":
        return None
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1]
    return float(text) if re.search(r"[.eE]", text) else int(text)


def stated_rows(sql):
    """{table: (columns, [row, ...])} for every INSERT ... VALUES the SQL states."""
    sql = re.sub(r"--[^\n]*", "", sql)
    out = {}
    pattern = re.compile(r"INSERT\s+INTO\s+(\w+)\s*\(([^)]*)\)\s*VALUES\s*(.*?);", re.S | re.I)
    for m in pattern.finditer(sql):
        table, cols = m.group(1), [c.strip() for c in m.group(2).split(",")]
        for tup in re.findall(r"\(((?:[^()']|'[^']*')*)\)", m.group(3)):
            values = [literal(v) for v in re.findall(r"'[^']*'|[^,]+", tup)]
            if len(values) != len(cols):
                sys.exit("%s: %d values for %d columns" % (table, len(values), len(cols)))
            out.setdefault(table, (cols, []))[1].append(values)
    return out


def write_domain(outdir, domain):
    pq.write_table(pa.table({"modelDomain": [domain]}), os.path.join(outdir, "runspecdomain.parquet"))
    print("%-24s %s" % ("runspecdomain", domain))


def main(sql_path, xml_path, movesdb, outdir):
    os.makedirs(outdir, exist_ok=True)
    for table, (cols, rows) in stated_rows(open(sql_path).read()).items():
        name, schema = default_schema(movesdb, table)
        data = {f.name: [] for f in schema}
        for row in rows:
            given = {c.lower(): v for c, v in zip(cols, row)}
            for f in schema:
                data[f.name].append(given.get(f.name.lower()))
        pq.write_table(pa.table(data, schema=schema), os.path.join(outdir, name + ".parquet"))
        print("%-24s %d row(s)" % (name, len(rows)))
    write_domain(outdir, ET.parse(xml_path).getroot().find("modeldomain").get("value"))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--default-domain":
        os.makedirs(sys.argv[2], exist_ok=True)
        write_domain(sys.argv[2], "DEFAULT")
        sys.exit(0)
    if len(sys.argv) != 5:
        sys.exit("usage: build-scale-input-db.py <setup.sql> <runspec.xml> <movesdb-dir> <outdir>")
    main(*sys.argv[1:])
