#!/usr/bin/env python3
"""Emit a `runspecs/` document's oracle tables, from ONE evaluation, as the CSVs the comparator reads.

A run's oracle is the output-database table its `oracle` source names (PLAN.md
§7.3.47), and since §7.3.48 a Rates-scale run names several. Each table is a
relation of `onroad/model.esm` under a prefix:

  movesoutput       out_   the output relation itself
  rateperdistance   rpd_   the output relation times the speed bins
  rateperstart      rps_   \\
  rateperhour       rph_    > the output relation, each a SUBSET of it
  ratepervehicle    rpv_   /
  startspervehicle  spv_   cohorts x counties x months x day types
  movesoutput_step  mos_   MOVESOutput at a Month or Year output time step:
                           the output relation's cells summed (PLAN.md §7.3.63)

A table over the output relation computes only what is NEW to it -- its value
and its membership -- and reads every other column it carries from the
relation's Rates-scale view `rto_*` or from `out_*` itself, in that order, so a
key the two tables share is computed once (conventions §107). Which columns a
table carries is the oracle's own header, read here off the capture's
`<table>.meta.json` schema.

A table that is a subset declares `<prefix>inTable`: RatePostProcessorRatesFirst.sql
assigns a row to a table by process and road type, and that predicate is model
logic, so it is in the model; this keeps the rows where it is 1 and drops the
column. A relation with no such variable is emitted whole.

ONE `esm simulate` per run. `esm simulate` evaluates every observed in the
document whatever `--observed` names (PLAN §7.3.52), so a call per table paid
for the whole model once per table -- seven times for a Rates run, with the
output relation and the shape scalars. `--format csv` needs every field it
writes to share a shape, and these do not; `--format grid` writes each field
with its own dimensions, so one call fetches everything and the CSVs are cut
from it here. Two more files can be asked for in the same call:

  --relation PATH   the output relation's `out_*` fields, written exactly as
                    `esm simulate --format csv` writes them (the shape check
                    and the probe's `cmp` read this file)
  --shape PATH      the scalar fields named by --shape-field, the same way

Floats are rendered as Rust's `{}` renders an f64 -- the shortest round-trip
digits, positional, never an exponent -- so a file is byte-identical to the
one a `--format csv` call writes.

    emit-oracle-table.py --esm ./esm --runspec runspecs/rates-start.esm \\
        --table rateperstart --table rateperhour --outdir runs/ \\
        --snapshots ../moves.rs/characterization/snapshots --model onroad/model.esm \\
        --relation runs/rates-start.runspec.csv \\
        --shape runs/rates-start.runspec.shape.csv --shape-field rateSurvivorCount

A table's file is `<outdir>/<run>.<table>.actual.csv`, its header the oracle's
column names, unprefixed. `--output` names the file when one table is asked
for, as before.
"""
from __future__ import annotations

import argparse
import csv
import decimal
import glob
import json
import math
import pathlib
import subprocess
import sys
import tempfile

PREFIX = {
    "movesoutput": "out_",
    "rateperdistance": "rpd_",
    "rateperstart": "rps_",
    "rateperhour": "rph_",
    "ratepervehicle": "rpv_",
    "rateperprofile": "rpp_",
    "startspervehicle": "spv_",
    "movesoutput_step": "mos_",
}
# A table name that is not the snapshot's: the oracle it is compared against.
# `movesoutput_step` is MOVESOutput at a coarser `<outputtimestep>` than the
# output relation's cells (PLAN.md §7.3.63) -- the run's oracle source carries
# the `output-time-step` tag -- emitted from `mos_*` into the movesoutput file.
ORACLE_FILE = {"movesoutput_step": "movesoutput"}
# A table over the output relation may read a column it does not compute from
# these, in order. Only `out_` itself and the tables laid over `output_rows` do.
SHARED = {"rps_": ["rto_", "out_"], "rph_": ["rto_", "out_"], "rpv_": ["rto_", "out_"],
          "rpp_": ["rto_", "out_"]}


def oracle_columns(snapshots: pathlib.Path, run: str, table: str) -> list[str]:
    """The oracle table's column names, from the capture's schema record."""
    hits = glob.glob(str(snapshots / run / "tables" / f"db__out_*__{table}.parquet"))
    if len(hits) != 1:
        sys.exit(f"emit-oracle-table: {len(hits)} `{table}` tables for {run} under {snapshots}")
    meta = pathlib.Path(hits[0][: -len(".parquet")] + ".meta.json")
    return [c["name"] for c in json.loads(meta.read_text())["schema"]]


def model_variables(model: pathlib.Path) -> list[str]:
    names: list[str] = []
    for m in json.loads(model.read_text()).get("models", {}).values():
        names.extend(m.get("variables") or {})
    return names


def table_fields(names: set[str], snapshots, run, table):
    """(variable, oracle column) pairs for one table; the membership flag, if
    the table has one, last with column None."""
    prefix = PREFIX[table]
    own = sorted(n for n in names if n.startswith(prefix))
    if not own:
        sys.exit(f"emit-oracle-table: the model declares no {prefix}* relation for `{table}`")
    member = f"{prefix}inTable"
    fields = [(n, n[len(prefix):]) for n in own if n != member]
    have = {col for _, col in fields}
    for col in oracle_columns(snapshots, run, ORACLE_FILE.get(table, table)):
        if col in have:
            continue
        for p in SHARED.get(prefix, []):
            if p + col in names:
                fields.append((p + col, col))
                have.add(col)
                break
    if member in names:
        fields.append((member, None))
    return fields


def rust_float(v) -> str:
    """An f64 as Rust's `format!("{}", v)` writes it: what `--format csv` emits."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "NaN"
    v = float(v)
    if math.isinf(v):
        return "inf" if v > 0 else "-inf"
    if v == 0:
        return "-0" if math.copysign(1, v) < 0 else "0"
    # repr() gives the shortest digit count that round-trips, and so does
    # Rust; they differ only on an exact tie between two such strings, which
    # Python breaks to even and Rust rounds UP -- common in a Float32 model,
    # whose values are short binary fractions (71.911651611328125: Rust
    # writes ...813, repr ...812).
    short = decimal.Decimal(repr(v))
    n = len(short.as_tuple().digits)
    exact = decimal.Decimal(v)
    q = exact.quantize(decimal.Decimal(1).scaleb(exact.adjusted() - n + 1),
                       rounding=decimal.ROUND_HALF_UP)
    if float(q) != v or len(q.normalize().as_tuple().digits) > n:
        q = short
    s = format(q, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def flatten(data) -> list:
    """Row-major values, whether the grid wrote them flat or nested."""
    while data and isinstance(data[0], list):
        data = [x for sub in data for x in sub]
    return data


def load_grid(path: pathlib.Path) -> dict[str, tuple[list[int], list]]:
    """name -> (shape without the time axis, row-major flat values)."""
    doc = json.loads(path.read_text())
    out = {}
    for g in doc["grids"]:
        dims = dict(g["dims"])
        for v in g["vars"]:
            shape = [dims[d] for d in v["dims"] if d != g.get("time_dim")]
            if g.get("time_dim") in v["dims"] and dims[g["time_dim"]] != 1:
                sys.exit(f"emit-oracle-table: {v['name']} has {dims[g['time_dim']]} "
                         "time points; a relational run is evaluated once")
            data = v["data"]
            data = flatten(data) if isinstance(data, list) else [data]
            if len(data) != math.prod(shape):
                sys.exit(f"emit-oracle-table: {v['name']}: {len(data)} values for shape {shape}")
            out[v["name"]] = (shape, data)
    return out


def write_esm_csv(grid, names: list[str], path) -> None:
    """`esm simulate --format csv` of `names`: i1..in (1-based, last axis
    fastest), then one column per field, in the order named."""
    shapes = {tuple(grid[n][0]) for n in names}
    if len(shapes) != 1:
        sys.exit(f"emit-oracle-table: {path}: the fields do not share a shape: "
                 + ", ".join(f"{n}={grid[n][0]}" for n in names))
    shape = list(shapes.pop())
    if not shape:
        sys.exit(f"emit-oracle-table: {path}: {names[0]} is a single value, not a column")
    cols = [grid[n][1] for n in names]
    with open(path, "w", newline="") as f:
        f.write(",".join([f"i{d}" for d in range(1, len(shape) + 1)] + names) + "\n")
        idx = [0] * len(shape)
        for k in range(math.prod(shape)):
            f.write(",".join([str(i + 1) for i in idx] + [rust_float(c[k]) for c in cols]) + "\n")
            for d in range(len(shape) - 1, -1, -1):
                idx[d] += 1
                if idx[d] < shape[d]:
                    break
                idx[d] = 0


def write_table(grid, fields, path) -> tuple[int, int]:
    member = next((n for n, col in fields if col is None), None)
    keep = [(n, col) for n, col in fields if col is not None]
    n_rows = len(grid[fields[0][0]][1])
    for n, _ in fields:
        if len(grid[n][1]) != n_rows:
            sys.exit(f"emit-oracle-table: {path}: {n} has {len(grid[n][1])} cells, "
                     f"{fields[0][0]} {n_rows}")
    kept = 0
    with open(path, "w", newline="") as g:
        w = csv.writer(g, lineterminator="\n")
        w.writerow([col for _, col in keep])
        for k in range(n_rows):
            if member is not None and float(rust_float(grid[member][1][k])) < 0.5:
                continue
            kept += 1
            w.writerow([rust_float(grid[n][1][k]) for n, _ in keep])
    return kept, n_rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--esm", required=True)
    ap.add_argument("--runspec", required=True)
    ap.add_argument("--table", action="append", default=[], choices=sorted(PREFIX))
    ap.add_argument("--snapshots", required=True, type=pathlib.Path)
    ap.add_argument("--model", required=True, type=pathlib.Path)
    ap.add_argument("--run", help="the snapshot's name (default: the runspec's basename)")
    ap.add_argument("--output", help="the file, when exactly one --table is asked for")
    ap.add_argument("--outdir", type=pathlib.Path, help="<outdir>/<run>.<table>.actual.csv")
    ap.add_argument("--relation", help="also write the out_* relation, as --format csv would")
    ap.add_argument("--shape", help="also write the --shape-field scalars, as --format csv would")
    ap.add_argument("--shape-field", action="append", default=[])
    a = ap.parse_args()
    if a.output and len(a.table) != 1:
        ap.error("--output names one table's file; use --outdir for several")
    if a.table and not (a.output or a.outdir):
        ap.error("--output or --outdir is needed for a --table")
    if bool(a.shape) != bool(a.shape_field):
        ap.error("--shape and --shape-field go together")

    run = a.run or pathlib.Path(a.runspec).stem
    ordered = model_variables(a.model)
    names = set(ordered)
    relation = [n for n in ordered if n.startswith("out_")]
    plan = {t: table_fields(names, a.snapshots, run, t) for t in a.table}

    wanted: list[str] = []
    for n in (relation if a.relation else []) + a.shape_field + [
            n for fs in plan.values() for n, _ in fs]:
        if n not in wanted:
            wanted.append(n)

    with tempfile.TemporaryDirectory() as tmp:
        raw = pathlib.Path(tmp) / "grid.json"
        cmd = [a.esm, "simulate", a.runspec, "--time", "0", "--format", "grid",
               "--output", str(raw)]
        for n in wanted:
            cmd += ["--observed", n]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(r.stdout[-2000:] + r.stderr[-2000:])
            return r.returncode
        grid = load_grid(raw)
    missing = [n for n in wanted if n not in grid]
    if missing:
        sys.exit(f"emit-oracle-table: the evaluation wrote no {', '.join(missing)}")

    if a.relation:
        write_esm_csv(grid, relation, a.relation)
    if a.shape:
        write_esm_csv(grid, a.shape_field, a.shape)
    for t, fields in plan.items():
        path = a.output or a.outdir / f"{run}.{ORACLE_FILE.get(t, t)}.actual.csv"
        kept, total = write_table(grid, fields, path)
        print(f"{t}: {kept} of {total} {PREFIX[t]}* rows", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
