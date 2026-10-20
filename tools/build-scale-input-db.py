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

A SINGLE-county database (step 7f's `washtenaw-county/setup-*.sql`) states its
rows the other way, `INSERT INTO <table> VALUES (...)` with no column list, so
the columns are the `CREATE TABLE <table> (...)` list above it, in order; and it
CREATES tables it never fills (`hotellingHourFraction` and its two siblings),
which MOVES then merges as tables with no rows. Both are written: a stated table
with its rows, a created-and-never-filled one with none. A table the SQL
TRUNCATEs and refills is the refill.

`--copy T1,T2,...` additionally materialises `INSERT INTO T SELECT * FROM
movesdb20241112.T [WHERE a=1 AND b=2 ...]` for the NAMED tables only, by
filtering the default database's own Parquet with the same equalities. It is
how a domain document gets the INPUT side of a row merge whose input rows are
default-row copies (`washtenaw-project`'s `ZoneRoadType`, filtered to its zone):
the merge has to read both sides even when one is a subset of the other, or
the precedence the model writes has nothing to choose between.

`--default-domain <outdir> [<movesdb-dir> T1,T2,...]` also writes the named
tables with ZERO rows, typed by the default database: a DEFAULT-domain run has
no input database, so the input side of every row merge is empty there.

usage: build-scale-input-db.py <setup.sql> <runspec.xml> <movesdb-dir> <outdir> [--copy T1,T2,...]
       build-scale-input-db.py --default-domain <outdir> [<movesdb-dir> T1,T2,...]
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


def created_columns(sql):
    """{table: [column, ...]} for every `CREATE TABLE <t> (...)` with a column list,
    and {table: None} for every `CREATE TABLE <t> LIKE ...`."""
    out = {}
    for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*(\(|LIKE)", sql, re.I):
        table = m.group(1)
        if m.group(2).upper() == "LIKE":
            out.setdefault(table, None)
            continue
        depth, i = 1, m.end()
        while depth:
            depth += {"(": 1, ")": -1}.get(sql[i], 0)
            i += 1
        body = sql[m.end():i - 1]
        cols = [line.strip().split()[0] for line in body.split("\n")
                if line.strip() and not re.match(r"(PRIMARY|UNIQUE|KEY|INDEX)\b", line.strip(), re.I)]
        out[table] = cols
    return out


def stated_rows(sql):
    """{table: (columns, [row, ...])} for every INSERT ... VALUES the SQL states,
    with or without a column list (without one, the CREATE TABLE's columns)."""
    sql = re.sub(r"--[^\n]*", "", sql)
    created = created_columns(sql)
    out = {}
    pattern = re.compile(r"INSERT\s+INTO\s+(\w+)\s*(?:\(([^)]*)\))?\s*VALUES\s*((?:[^;']|'[^']*')*);",
                         re.S | re.I)
    for m in pattern.finditer(sql):
        table = m.group(1)
        if m.group(2) is not None:
            cols = [c.strip() for c in m.group(2).split(",")]
        elif created.get(table):
            cols = created[table]
        else:
            sys.exit("%s: INSERT without a column list and no CREATE TABLE column list" % table)
        for tup in re.findall(r"\(((?:[^()']|'[^']*')*)\)", m.group(3)):
            values = [literal(v) for v in re.findall(r"'[^']*'|[^,]+", tup)]
            if len(values) != len(cols):
                sys.exit("%s: %d values for %d columns" % (table, len(values), len(cols)))
            out.setdefault(table, (cols, []))[1].append(values)
    return out


def never_filled(sql):
    """The tables the SQL creates and fills by no INSERT at all."""
    sql = re.sub(r"--[^\n]*", "", sql)
    filled = {m.group(1).lower() for m in re.finditer(r"INSERT\s+INTO\s+(\w+)", sql, re.I)}
    return [t for t in created_columns(sql) if t.lower() not in filled]


def copied_rows(sql, movesdb, tables):
    """{table: pyarrow.Table} for `INSERT INTO T SELECT * FROM movesdb20241112.T
    [WHERE a=1 AND b=2]`, for the named tables: the default's rows, filtered."""
    sql = re.sub(r"--[^\n]*", "", sql)
    wanted = {t.lower() for t in tables}
    out = {}
    pattern = re.compile(r"INSERT\s+INTO\s+(\w+)\s+SELECT\s+\*\s+FROM\s+\w+\.(\w+)\s*(?:WHERE\s+(.*?))?;",
                         re.S | re.I)
    for m in pattern.finditer(sql):
        table = m.group(1)
        if table.lower() not in wanted:
            continue
        name, _ = default_schema(movesdb, m.group(2))
        data = pq.read_table(os.path.join(movesdb, name + ".parquet"))
        for clause in re.split(r"\s+AND\s+", m.group(3) or "", flags=re.I):
            if not clause.strip():
                continue
            col, val = (x.strip() for x in clause.split("="))
            field = next(f.name for f in data.schema if f.name.lower() == col.lower())
            keep = [v == literal(val) for v in data.column(field).to_pylist()]
            data = data.filter(pa.array(keep, type=pa.bool_()))
        out[table] = (name, data)
    missing = wanted - {t.lower() for t in out}
    if missing:
        sys.exit("no INSERT ... SELECT * copy of %s" % sorted(missing))
    return out


def write_domain(outdir, domain):
    pq.write_table(pa.table({"modelDomain": [domain]}), os.path.join(outdir, "runspecdomain.parquet"))
    print("%-24s %s" % ("runspecdomain", domain))


def write_rows(movesdb, outdir, table, cols, rows):
    name, schema = default_schema(movesdb, table)
    data = {f.name: [] for f in schema}
    for row in rows:
        given = {c.lower(): v for c, v in zip(cols, row)}
        for f in schema:
            data[f.name].append(given.get(f.name.lower()))
    pq.write_table(pa.table(data, schema=schema), os.path.join(outdir, name + ".parquet"))
    print("%-30s %d row(s)" % (name, len(rows)))


def main(sql_path, xml_path, movesdb, outdir, copy=()):
    os.makedirs(outdir, exist_ok=True)
    sql = open(sql_path).read()
    for table, (cols, rows) in stated_rows(sql).items():
        write_rows(movesdb, outdir, table, cols, rows)
    for table in never_filled(sql):
        write_rows(movesdb, outdir, table, [], [])
    for table, (name, data) in copied_rows(sql, movesdb, copy).items():
        pq.write_table(data, os.path.join(outdir, name + ".parquet"))
        print("%-30s %d row(s), copied" % (name, data.num_rows))
    write_domain(outdir, ET.parse(xml_path).getroot().find("modeldomain").get("value"))


if __name__ == "__main__":
    if len(sys.argv) in (3, 5) and sys.argv[1] == "--default-domain":
        os.makedirs(sys.argv[2], exist_ok=True)
        write_domain(sys.argv[2], "DEFAULT")
        if len(sys.argv) == 5:
            for table in sys.argv[4].split(","):
                write_rows(sys.argv[3], sys.argv[2], table, [], [])
        sys.exit(0)
    args = sys.argv[1:]
    copy = ()
    if len(args) == 6 and args[4] == "--copy":
        copy, args = args[5].split(","), args[:4]
    if len(args) != 4:
        sys.exit("usage: build-scale-input-db.py <setup.sql> <runspec.xml> <movesdb-dir> <outdir> [--copy T1,T2,...]")
    main(*args, copy=copy)
