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
filtering the default database's own Parquet with the same predicates; and
`INSERT INTO [db.]T (cols) SELECT cols FROM movesdb20241112.S WHERE ...`, the
form MOVES 5's LEV and NLEV builder scripts take (`emissionratebyage` from
`emissionratebyagelev`, with `in (...)` lists and MySQL's `mid()` on the packed
sourceBinID; PLAN.md §7.3.82). It is
how a domain document gets the INPUT side of a row merge whose input rows are
default-row copies (`washtenaw-project`'s `ZoneRoadType`, filtered to its zone):
the merge has to read both sides even when one is a subset of the other, or
the precedence the model writes has nothing to choose between.

`--default-domain <outdir> [<movesdb-dir> T1,T2,...]` also writes the named
tables with ZERO rows, typed by the default database: a DEFAULT-domain run has
no input database, so the input side of every row merge is empty there.

`--empty <outdir> <movesdb-dir> T1,T2,...` writes each named table with ZERO rows,
typed by the default database, and nothing else -- never over a file that is
already there. It is how a scale-input database's document declares a table the
database holds only as `INSERT ... SELECT` copies of the default's rows, or does
not hold at all: the INPUT side of the merge states nothing the default does not
(PLAN.md §7.3.85), and the model counts any row a domain database states there
that differs from the default's.

`--runspec-output <runspec.xml> <out.parquet>` writes the RunSpec's OUTPUT settings,
which MOVES writes nowhere in the execution database either (PLAN.md §7.3.85): one
row per setting, a single string column `option` spelled `<setting>=<value>` --
each `<outputemissionsbreakdownselection>` flag (`breakdown.<tag>=<selected>`), the
three `<outputfactors>` (`timefactors=<selected>:<units>`, `distancefactors=...`,
`massfactors=<selected>:<units>:<energyunits>`), `geographicoutputdetail`, one
`geographicselection=<type>` per selection, the seven activity-output flags
(`outputvmtdata`, `outputsho`, `outputsh`, `outputshp`, `outputshidling`,
`outputstarts`, `outputpopulation`), whether a `<genericcounty>` is given, how many
calculators `<donotexecute>` names and `<doNotPerformFinalAggregation>`.
The model decodes each against the one configuration it computes and counts the
rest (`run_outputOptionsUnported`, `run_geoSelectionUnported`,
`run_activityOutputUnported`).

`--internal-control-strategies <runspec.xml> <outdir>` writes the one table a
RunSpec's `<internalcontrolstrategies>` element stands for,
`runspecinternalcontrolstrategy.parquet`: a row per strategy, its class name and
its `useParameters` value. Rate-of-Progress is the one strategy MOVES 5 takes from
the RunSpec rather than from a table (PLAN.md §7.3.81); a RunSpec with an empty
element writes the table with no rows.

usage: build-scale-input-db.py <setup.sql> <runspec.xml> <movesdb-dir> <outdir> [--copy T1,T2,...]
       build-scale-input-db.py --default-domain <outdir> [<movesdb-dir> T1,T2,...]
       build-scale-input-db.py --empty <outdir> <movesdb-dir> T1,T2,...
       build-scale-input-db.py --internal-control-strategies <runspec.xml> <outdir>
       build-scale-input-db.py --runspec-output <runspec.xml> <out.parquet>
"""
import json
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


def schema_only(movesdb, table):
    """True when the default database has `table` only as `<t>.schema.json`."""
    names = {n.lower() for n in os.listdir(movesdb)}
    return (table.lower() + ".schema.json" in names
            and table.lower() + ".parquet" not in names)


# Tables a scale-input database may hold that are not model inputs at all:
# MOVES's importers read them during domain-database validation and the merge
# never copies them into the execution database (InputDataManager copies only
# default-schema tables). `auditLog` carries the County Data Manager's
# "No data needed" flags (setup-county.sql's "No I/M Program"). They are
# skipped by name, so any OTHER table without a default-database counterpart
# still stops the tool.
BOOKKEEPING_TABLES = {"auditlog"}


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
            # A quoted value is matched whole, after any leading blank, so a
            # comma inside it does not split it (project-useromd's link name).
            values = [literal(v) for v in re.findall(r"\s*'[^']*'|[^,]+", tup)]
            if len(values) != len(cols):
                sys.exit("%s: %d values for %d columns" % (table, len(values), len(cols)))
            out.setdefault(table, (cols, []))[1].append(values)
    return out


def never_filled(sql):
    """The tables the SQL creates and fills by no INSERT at all."""
    sql = re.sub(r"--[^\n]*", "", sql)
    filled = {m.group(1).lower() for m in re.finditer(r"INSERT\s+INTO\s+(\w+)", sql, re.I)}
    return [t for t in created_columns(sql) if t.lower() not in filled]


def sql_number(value):
    """MySQL's numeric reading of a value compared with a number: a string is
    read as its leading number, '' as 0 (`mid(sourcebinid,8,2) in ('', 94, ...)`)."""
    if isinstance(value, str):
        m = re.match(r"\s*[-+]?\d+(\.\d*)?([eE][-+]?\d+)?", value)
        return float(m.group(0)) if m else 0.0
    return float(value)


def row_filter(data, clause):
    """The boolean mask of one WHERE conjunct over `data`: `col = literal`,
    `col in (literal, ...)` or `mid(col, start, length) in (literal, ...)`, the
    last as MySQL evaluates it -- MID of the column's decimal text (1-based), the
    comparison numeric, because the list holds numbers."""
    m = re.match(r"(?:mid\(\s*(\w+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)|(\w+))\s*(=|in)\s*(.*)$",
                 clause.strip(), re.S | re.I)
    if not m:
        sys.exit("unsupported WHERE clause: %r" % clause)
    col = m.group(1) or m.group(4)
    field = next(f.name for f in data.schema if f.name.lower() == col.lower())
    values = data.column(field).to_pylist()
    if m.group(1):
        start, length = int(m.group(2)) - 1, int(m.group(3))
        values = [str(v)[start:start + length] for v in values]
    if m.group(5) == "=":
        wanted = {sql_number(literal(m.group(6)))}
    else:
        items = re.findall(r"'[^']*'|[^,()\s]+", m.group(6).strip()[1:-1])
        wanted = {sql_number(literal(v)) for v in items}
    return [sql_number(v) in wanted for v in values]


def copied_rows(sql, movesdb, tables):
    """{table: pyarrow.Table} for the named tables, copied from the default
    database by `INSERT INTO T SELECT * FROM movesdb20241112.T [WHERE ...]` or by
    `INSERT INTO [db.]T (cols) SELECT cols FROM movesdb20241112.S [WHERE ...]` --
    the second is how MOVES 5's LEV/NLEV builder scripts write their database
    (database/LEV_NLEVScripts/, `emissionratebyage` from `emissionratebyagelev`).
    The WHERE is a conjunction of `col = v`, `col in (...)` and
    `mid(col, a, b) in (...)` (`row_filter`); the copy is typed by the TARGET
    table's default schema."""
    sql = re.sub(r"--[^\n]*", "", sql)
    wanted = {t.lower() for t in tables}
    out = {}
    pattern = re.compile(r"INSERT\s+INTO\s+(?:\w+\.)?(\w+)\s*(?:\(([^)]*)\))?\s*SELECT\s+(\*|[\w\s,]+?)\s+"
                         r"FROM\s+\w+\.(\w+)\s*(?:WHERE\s+(.*?))?;", re.S | re.I)
    for m in pattern.finditer(sql):
        table = m.group(1)
        if table.lower() not in wanted:
            continue
        name, schema = default_schema(movesdb, table)
        source, _ = default_schema(movesdb, m.group(4))
        data = pq.read_table(os.path.join(movesdb, source + ".parquet"))
        if m.group(3).strip() != "*":
            into = [c.strip().lower() for c in m.group(2).split(",")]
            picked = [c.strip().lower() for c in m.group(3).split(",")]
            if into != picked:
                sys.exit("%s: a column list that renames is not supported" % table)
        for clause in re.split(r"\s+AND\s+", m.group(5) or "", flags=re.I):
            if clause.strip():
                data = data.filter(pa.array(row_filter(data, clause), type=pa.bool_()))
        by_name = {f.name.lower(): f.name for f in data.schema}
        data = pa.table({f.name: data.column(by_name[f.name.lower()]).cast(f.type) for f in schema},
                        schema=schema)
        out[table] = (name, data)
    missing = wanted - {t.lower() for t in out}
    if missing:
        sys.exit("no INSERT ... SELECT copy of %s" % sorted(missing))
    return out


def write_domain(outdir, domain):
    pq.write_table(pa.table({"modelDomain": [domain]}), os.path.join(outdir, "runspecdomain.parquet"))
    print("%-24s %s" % ("runspecdomain", domain))


def write_strategies(outdir, xml_path):
    """`runspecinternalcontrolstrategy.parquet`: one row per `<internalcontrolstrategy>`
    of the RunSpec -- its `classname` and the value of the `useParameters` line of its
    TSV text, as RateOfProgressStrategy.acceptTSV reads it (the first four lines,
    tab-separated, name matched case-insensitively; no line is "" and means No).
    MOVES writes neither anywhere in the execution database (PLAN.md §7.3.81)."""
    names, values = [], []
    root = ET.parse(xml_path).getroot().find("internalcontrolstrategies")
    for node in (root if root is not None else []):
        if node.tag.lower() != "internalcontrolstrategy":
            continue
        value = ""
        for line in (node.text or "").strip("\r\n").splitlines()[:4]:
            parts = line.split("\t")
            if not line or not parts:
                break
            if parts[0].strip().lower() == "useparameters":
                value = parts[1].strip() if len(parts) > 1 else ""
                break
        names.append(node.get("classname") or "")
        values.append(value)
    pq.write_table(pa.table({"className": pa.array(names, pa.string()),
                             "useParameters": pa.array(values, pa.string())}),
                   os.path.join(outdir, "runspecinternalcontrolstrategy.parquet"))
    print("%-30s %d row(s)" % ("runspecinternalcontrolstrategy", len(names)))


ACTIVITY_FLAGS = ("outputvmtdata", "outputsho", "outputsh", "outputshp", "outputshidling",
                  "outputstarts", "outputpopulation")


def runspec_output_options(xml_path):
    """The RunSpec's output settings as `<setting>=<value>` strings, in document order."""
    root = ET.parse(xml_path).getroot()
    out = []
    node = root.find("outputemissionsbreakdownselection")
    for flag in (node if node is not None else []):
        out.append("breakdown.%s=%s" % (flag.tag.lower(), (flag.get("selected") or "false").lower()))
    node = root.find("outputfactors")
    for f in (node if node is not None else []):
        parts = [(f.get("selected") or "false").lower(), f.get("units") or ""]
        if f.tag.lower() == "massfactors":
            parts.append(f.get("energyunits") or "")
        out.append("%s=%s" % (f.tag.lower(), ":".join(parts)))
    node = root.find("geographicoutputdetail")
    out.append("geographicoutputdetail=%s" % (node.get("description") if node is not None else ""))
    node = root.find("geographicselections")
    for g in (node if node is not None else []):
        out.append("geographicselection=%s" % g.get("type"))
    for tag in ACTIVITY_FLAGS:
        node = root.find(tag)
        out.append("%s=%s" % (tag, (node.get("value") if node is not None else "false").lower()))
    node = root.find("genericcounty")
    out.append("genericcounty=%s" % ("true" if node is not None else "false"))
    # RunSpecXML.java:225-231: calculators the RunSpec tells MOVES not to run, and
    # the switch that skips MOVES's final aggregation; both change MOVESOutput.
    node = root.find("donotexecute")
    out.append("donotexecute=%d" % (len(node) if node is not None else 0))
    node = next((n for n in root if n.tag.lower() == "donotperformfinalaggregation"), None)
    out.append("donotperformfinalaggregation=%s" % ((node.get("selected") or "false").lower() if node is not None else "false"))
    return out


def write_runspec_output(xml_path, out_path):
    options = runspec_output_options(xml_path)
    pq.write_table(pa.table({"option": pa.array(options, pa.string())}), out_path)
    print("%-30s %d row(s)" % (os.path.basename(out_path), len(options)))


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
        if table.lower() in BOOKKEEPING_TABLES:
            print("%-30s %d row(s), not a model input: skipped" % (table, len(rows)))
            continue
        write_rows(movesdb, outdir, table, cols, rows)
    for table in never_filled(sql):
        if schema_only(movesdb, table):
            # The default database ships this table with no rows and no Parquet
            # (only `<t>.schema.json`), so a created-empty copy is empty on both
            # sides and there is no schema file to type it by: nothing to mount.
            print("%-30s 0 row(s), schema-only in the default: skipped" % table)
            continue
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
    if len(sys.argv) == 5 and sys.argv[1] == "--empty":
        os.makedirs(sys.argv[2], exist_ok=True)
        for table in sys.argv[4].split(","):
            if schema_only(sys.argv[3], table):
                # Shipped as `<t>.schema.json` alone (Starts): typed by that.
                spec = json.load(open(os.path.join(sys.argv[3], table + ".schema.json")))
                types = {"Int64": pa.int64(), "Float64": pa.float64(), "Utf8": pa.string()}
                schema = pa.schema([(c["name"], types[c["arrow_type"]]) for c in spec["columns"]])
                path = os.path.join(sys.argv[2], spec["name"] + ".parquet")
                if os.path.exists(path):
                    print("%-30s exists: kept" % spec["name"])
                    continue
                pq.write_table(schema.empty_table(), path)
                print("%-30s 0 row(s), typed by its schema.json" % spec["name"])
                continue
            name, _ = default_schema(sys.argv[3], table)
            if os.path.exists(os.path.join(sys.argv[2], name + ".parquet")):
                print("%-30s exists: kept" % name)
                continue
            write_rows(sys.argv[3], sys.argv[2], table, [], [])
        sys.exit(0)
    if len(sys.argv) == 4 and sys.argv[1] == "--runspec-output":
        os.makedirs(os.path.dirname(sys.argv[3]) or ".", exist_ok=True)
        write_runspec_output(sys.argv[2], sys.argv[3])
        sys.exit(0)
    if len(sys.argv) == 4 and sys.argv[1] == "--internal-control-strategies":
        os.makedirs(sys.argv[3], exist_ok=True)
        write_strategies(sys.argv[3], sys.argv[2])
        sys.exit(0)
    args = sys.argv[1:]
    copy = ()
    if len(args) == 6 and args[4] == "--copy":
        copy, args = args[5].split(","), args[:4]
    if len(args) != 4:
        sys.exit("usage: build-scale-input-db.py <setup.sql> <runspec.xml> <movesdb-dir> <outdir> [--copy T1,T2,...]")
    main(*args, copy=copy)
