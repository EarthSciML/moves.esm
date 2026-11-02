#!/usr/bin/env python3
"""Emit one oracle table of a `runspecs/` document as the CSV the comparator reads.

A run's oracle is the output-database table its `oracle` source names (PLAN.md
§7.3.47), and since §7.3.48 a Rates-scale run names several. Each table is a
relation of `onroad/model.esm` under a prefix:

  movesoutput       out_   the output relation itself
  rateperdistance   rpd_   the output relation times the speed bins
  rateperstart      rps_   \
  rateperhour       rph_    > the output relation, each a SUBSET of it
  ratepervehicle    rpv_   /
  startspervehicle  spv_   cohorts x counties x months x day types

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

    emit-oracle-table.py --esm ./esm --runspec runspecs/rates-start.esm \\
        --table rateperstart --snapshots ../moves.rs/characterization/snapshots \\
        --model onroad/model.esm --output rps.csv

The output's header is the oracle's column names, unprefixed.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
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
}
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


def model_variables(model: pathlib.Path) -> set[str]:
    names: set[str] = set()
    for m in json.loads(model.read_text()).get("models", {}).values():
        names.update(m.get("variables") or {})
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--esm", required=True)
    ap.add_argument("--runspec", required=True)
    ap.add_argument("--table", required=True, choices=sorted(PREFIX))
    ap.add_argument("--snapshots", required=True, type=pathlib.Path)
    ap.add_argument("--model", required=True, type=pathlib.Path)
    ap.add_argument("--run", help="the snapshot's name (default: the runspec's basename)")
    ap.add_argument("--output", required=True)
    a = ap.parse_args()

    run = a.run or pathlib.Path(a.runspec).stem
    prefix = PREFIX[a.table]
    names = model_variables(a.model)
    own = sorted(n for n in names if n.startswith(prefix))
    if not own:
        sys.exit(f"emit-oracle-table: the model declares no {prefix}* relation for `{a.table}`")

    member = f"{prefix}inTable"
    # Each emitted variable, and the oracle column it becomes.
    fields: list[tuple[str, str]] = [(n, n[len(prefix):]) for n in own if n != member]
    have = {col for _, col in fields}
    for col in oracle_columns(a.snapshots, run, a.table):
        if col in have:
            continue
        for p in SHARED.get(prefix, []):
            if p + col in names:
                fields.append((p + col, col))
                have.add(col)
                break
    if member in names:
        fields.append((member, None))

    with tempfile.TemporaryDirectory() as tmp:
        raw = pathlib.Path(tmp) / "raw.csv"
        cmd = [a.esm, "simulate", a.runspec, "--time", "0", "--format", "csv", "--output", str(raw)]
        for n, _ in fields:
            cmd += ["--observed", n]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(r.stdout[-2000:] + r.stderr[-2000:])
            return r.returncode
        with open(raw, newline="") as f, open(a.output, "w", newline="") as g:
            rd = csv.DictReader(f)
            w = csv.writer(g, lineterminator="\n")
            keep = [(n, col) for n, col in fields if col is not None]
            w.writerow([col for _, col in keep])
            kept = total = 0
            for row in rd:
                total += 1
                if member in names and float(row[member]) < 0.5:
                    continue
                kept += 1
                w.writerow([row[n] for n, _ in keep])
    print(f"{a.table}: {kept} of {total} {prefix}* rows", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
