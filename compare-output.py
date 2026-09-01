#!/usr/bin/env python3
"""Compare a fixture's MOVESOutput against a `moves.rs` characterization snapshot.

Inline `tests` sections in the `.esm` documents assert *reductions* — total mass
per pollutant, a max cell — because an assertion on an array-shaped variable has
to select a scalar (esm-spec §6.6.5). That is the right shape for a unit test and
the wrong shape for a fidelity gate: a reduction cannot see a row that moved.
This is the row-by-row half, run from `run-tests.sh`.

What it checks, in the order a failure is most diagnostic:

  1. row count            — exact, if `[structure] require_exact_row_count`
  2. key set              — exact, if `[structure] require_exact_key_set`
  3. per-cell relative    — `[cell] rel`
  4. per-pollutant sums   — `[default] onroad` / `nonroad`

Checks 2 and 3 are the two that bind, and they fail on opposite mistakes, which
is why both are here. Measured against this repo's own `nr-logging-county`
snapshot, by perturbing it and re-running:

  - drop the four (THC/CO/NOx/PM) x SCC 2260007005 x MY2018 rows -- the mistake
    a document copying Fortran's `modfrc <= 0` skip would make -- and the
    per-pollutant sums still agree to 1.2e-8, four orders inside the 1e-2 gate.
    Only the key set sees it.
  - emit those four rows as zero instead -- what evaluating in binary64 actually
    does -- and again sums agree to 1.2e-8. Only the per-cell check sees it.
  - move mass between two model years of one SCC and the sums agree to 2e-16, by
    construction. Only the per-cell check sees it.

So the loose per-pollutant gate would have waved through every realistic failure
this port can produce. It is kept because it is the gate `moves.rs` itself uses
across implementations, and because a per-fixture override can loosen `[cell]`
or omit it -- but it is not the gate doing the work.

Two of the four checks are SUBSUMED when all four are on: a row-count difference
implies a key-set difference (duplicate keys are rejected, so keys are unique),
and any sums violation implies a cell violation while `[cell] rel` stays ~500x
tighter. Disabling either changes no whole-suite outcome. They are still tested,
each alone, because subsumed-today is not the same as dead, and because the
isolation test is the only thing that can reach their logic at all.

The contract itself — which columns are identity, which are compared, which are
excused — lives in `tolerance.toml`, next to the prose explaining why.

Values arrive as decimal *text* on both sides (`emissionQuant` is a string
column in the snapshot, 12 decimal places), so they are parsed with `Decimal`
and compared as floats. Parsing via float() directly would be fine for these
magnitudes, but Decimal makes the "the snapshot is text" fact visible at the
one place it matters, rather than a silent implicit conversion.

Usage:
    compare-output.py --fixture nr-logging-county --actual out.csv
    compare-output.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import csv
import pathlib
import re
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_SNAPSHOTS = HERE.parent / "moves.rs" / "characterization" / "snapshots"

# NONROAD fixtures are named `nr-*` in the snapshot tree; everything else is
# onroad. This decides which `[default]` tolerance the sums gate uses, and it is
# the only place the distinction is drawn.
NONROAD_PREFIX = "nr-"


class Failure(Exception):
    """A comparison failed. The message is the report."""


# --------------------------------------------------------------------------
# loading


def parse_toml_subset(text: str) -> dict:
    """Read the small TOML subset `tolerance.toml` uses.

    Not a TOML implementation, and deliberately not trying to be. `tomllib` is
    3.11+, and on this machine the interpreter carrying `pyarrow` is 3.9 while
    the one carrying `tomllib` has no `pyarrow` — so a stdlib parse is not
    available to the process that has to read Parquet, and adding a dependency
    to run one comparison is a worse trade than 40 readable lines.

    The subset: `[table]` and `[table."quoted"]` headers, `key = value` where
    value is a number, a bare true/false, a double-quoted string, or a
    single-line or multi-line array of those. Comments and blank lines are
    skipped.

    Anything outside that subset raises. That is the whole point: a config
    parser that silently skips what it does not understand turns a typo'd
    tolerance into a missing gate, which is precisely the class of silent pass
    this file exists to prevent.
    """
    root: dict = {}
    table = root
    # Strip full-line comments and trailing comments outside strings. The file
    # has no `#` inside any string value, and this asserts that rather than
    # assuming it.
    lines = []
    for raw in text.splitlines():
        if '"' in raw and "#" in raw and raw.index("#") > raw.index('"'):
            raise ValueError(f"unsupported: `#` after a string on line: {raw!r}")
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)

    buf = ""
    for line in lines:
        buf = f"{buf} {line}".strip() if buf else line
        # An array may span lines; keep accumulating until brackets balance.
        if buf.count("[") != buf.count("]") and "=" in buf:
            continue

        if buf.startswith("[") and "=" not in buf:
            header = buf.strip("[]").strip()
            table = root
            for part in re.findall(r'"([^"]*)"|([^.]+)', header):
                name = (part[0] or part[1]).strip()
                table = table.setdefault(name, {})
            buf = ""
            continue

        if "=" not in buf:
            raise ValueError(f"unsupported TOML line: {buf!r}")
        key, _, value = buf.partition("=")
        table[key.strip()] = _toml_value(value.strip())
        buf = ""

    if buf:
        raise ValueError(f"unterminated TOML construct: {buf!r}")
    return root


def _toml_value(v: str):
    if v in ("true", "false"):
        return v == "true"
    if v.startswith("["):
        # Trailing commas are legal TOML and illegal Python only in odd spots;
        # `ast.literal_eval` accepts them in a list, so this is a direct read.
        try:
            out = ast.literal_eval(v)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(f"unsupported TOML array: {v!r}") from exc
        if not isinstance(out, list) or not all(isinstance(x, (str, int, float)) for x in out):
            raise ValueError(f"unsupported TOML array contents: {v!r}")
        return out
    if v.startswith('"') and v.endswith('"') and len(v) >= 2:
        return v[1:-1]
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError as exc:
        raise ValueError(f"unsupported TOML value: {v!r}") from exc


def load_tolerance(path: pathlib.Path) -> dict:
    return parse_toml_subset(path.read_text())


def snapshot_output_path(snapshots: pathlib.Path, fixture: str) -> pathlib.Path:
    """The expected-output table for a fixture.

    A snapshot's output database is named in its `provenance.json` as
    `output_database`; the table file is `db__<database>__movesoutput.parquet`.
    Reading the name rather than deriving it keeps this correct for a fixture
    whose database name is not just the fixture name with dashes swapped.
    """
    import json

    prov = snapshots / fixture / "provenance.json"
    if not prov.exists():
        raise Failure(f"no snapshot for fixture {fixture!r} at {prov.parent}")
    db = json.loads(prov.read_text())["output_database"]
    p = snapshots / fixture / "tables" / f"db__{db}__movesoutput.parquet"
    if not p.exists():
        raise Failure(f"snapshot {fixture!r} has no MOVESOutput at {p}")
    return p


def read_expected(path: pathlib.Path) -> list[dict]:
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    cols = table.to_pydict()
    n = table.num_rows
    return [{c: cols[c][i] for c in table.column_names} for i in range(n)]


def read_actual(path: pathlib.Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------
# comparison


def _norm(v):
    """Normalise one identity cell to a comparable token.

    The two sides arrive from different readers — Parquet types on one, CSV text
    on the other — so `26161` and `"26161"` must compare equal or every row is
    reported missing. NULL/None/"" all mean absent, and MOVESOutput leans on that
    heavily: for `nr-logging-county`, 9 of the 25 columns are NULL throughout.
    """
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.upper() in ("NULL", "NONE", "NAN"):
        return None
    # An integral value must compare equal whether it arrived as 26161, "26161"
    # or "26161.0"; anything else stays a trimmed string.
    try:
        d = Decimal(s)
    except InvalidOperation:
        return s
    return str(int(d)) if d == d.to_integral_value() else str(d)


def _num(v, where: str) -> float:
    if v is None or str(v).strip() == "":
        raise Failure(f"{where}: value is empty")
    try:
        return float(Decimal(str(v).strip()))
    except InvalidOperation as exc:
        raise Failure(f"{where}: {v!r} is not a number") from exc


def key_columns(columns, cfg) -> list[str]:
    ignored = set(cfg["ignored_columns"]) | set(cfg["value_columns"])
    return [c for c in columns if c not in ignored]


def relerr(actual: float, expected: float) -> float:
    """Relative error, with an exact-zero expectation handled explicitly.

    `abs(a-e)/abs(e)` is infinite when the expectation is zero, which would make
    a correct zero look like the worst cell in the table. When both are zero the
    error is zero; when only the expectation is, fall back to absolute, since
    there is no scale to be relative to.
    """
    if expected == actual:
        return 0.0
    if expected == 0.0:
        return abs(actual)
    return abs(actual - expected) / abs(expected)


def compare(expected: list[dict], actual: list[dict], tol: dict, fixture: str) -> list[str]:
    """Return a list of report lines. Raises `Failure` with the report on a diff."""
    cfg = tol["compare"]
    structure = tol.get("structure", {})
    value_cols = cfg["value_columns"]
    pol_col = cfg["pollutant_column"]

    if not expected:
        raise Failure("the snapshot's MOVESOutput is empty; nothing to compare")

    keys = key_columns(list(expected[0].keys()), cfg)
    report: list[str] = []
    problems: list[str] = []

    # Most identity columns are constant across a fixture -- for
    # nr-logging-county, 16 of 19, nine of them NULL throughout -- so printing
    # the full key makes a four-row difference unreadable. Report the columns
    # that actually vary, and say once which ones were held constant.
    varying = [c for c in keys if len({_norm(r.get(c)) for r in expected}) > 1]
    constant = [c for c in keys if c not in varying]

    def show(k: tuple) -> str:
        d = dict(zip(keys, k))
        shown = varying or keys
        return " ".join(f"{c}={d[c]}" for c in shown)

    # An actual row missing a compared or identity column is a schema mistake,
    # not a numeric one, and is worth saying before any number is looked at.
    missing_cols = [c for c in keys + value_cols if c not in actual[0]] if actual else []
    if missing_cols:
        raise Failure(
            f"actual output lacks column(s) {', '.join(missing_cols)}; "
            f"it has {', '.join(sorted(actual[0]))}"
        )

    # 1. row count
    if structure.get("require_exact_row_count") and len(actual) != len(expected):
        problems.append(f"row count: actual {len(actual)}, expected {len(expected)}")
    report.append(f"rows: {len(actual)} actual / {len(expected)} expected")
    if constant:
        report.append(
            f"identity: {len(keys)} columns, {len(varying)} varying "
            f"({', '.join(varying)}); {len(constant)} constant, not shown below"
        )

    def index(rows, side):
        out = {}
        for i, r in enumerate(rows):
            k = tuple(_norm(r.get(c)) for c in keys)
            if k in out:
                raise Failure(f"{side} row {i} duplicates key {show(k)}")
            out[k] = r
        return out

    exp_by_key = index(expected, "expected")
    act_by_key = index(actual, "actual")

    # 2. key set
    only_exp = sorted(exp_by_key.keys() - act_by_key.keys())
    only_act = sorted(act_by_key.keys() - exp_by_key.keys())
    if structure.get("require_exact_key_set") and (only_exp or only_act):
        if only_exp:
            problems.append(f"{len(only_exp)} key(s) in the snapshot but not emitted:")
            problems += [f"    {show(k)}" for k in only_exp[:5]]
            if len(only_exp) > 5:
                problems.append(f"    ... and {len(only_exp) - 5} more")
        if only_act:
            problems.append(f"{len(only_act)} key(s) emitted but not in the snapshot:")
            problems += [f"    {show(k)}" for k in only_act[:5]]
            if len(only_act) > 5:
                problems.append(f"    ... and {len(only_act) - 5} more")
    shared = exp_by_key.keys() & act_by_key.keys()
    report.append(
        f"key set: {len(shared)} shared, {len(only_exp)} missing, {len(only_act)} extra"
    )

    # 3. per-cell
    cell_rel = tol.get("cell", {}).get("rel")
    worst = (0.0, None)
    cells_checked = 0
    over = []
    if cell_rel is not None:
        for k in sorted(shared):
            for col in value_cols:
                e = _num(exp_by_key[k][col], f"expected {show(k)} {col}")
                a = _num(act_by_key[k][col], f"actual {show(k)} {col}")
                r = relerr(a, e)
                cells_checked += 1
                if r > worst[0]:
                    worst = (r, (k, col, a, e))
                if r > cell_rel:
                    over.append((r, k, col, a, e))
        if over:
            over.sort(reverse=True)
            problems.append(f"{len(over)} cell(s) over the {cell_rel:g} relative tolerance:")
            for r, k, col, a, e in over[:5]:
                problems.append(
                    f"    {show(k)} {col}: actual={a!r} expected={e!r} rel={r:.3e}"
                )
            if len(over) > 5:
                problems.append(f"    ... and {len(over) - 5} more")
        if cells_checked:
            report.append(
                f"worst cell: rel={worst[0]:.3e} over {cells_checked} cells "
                f"(tolerance {cell_rel:g})"
            )

    # 4. per-pollutant sums
    which = "nonroad" if fixture.startswith(NONROAD_PREFIX) else "onroad"
    sums_rel = tol["fixtures"][fixture]["rel"] if fixture in tol.get("fixtures", {}) else tol["default"][which]
    for col in value_cols:
        e_sums, a_sums = defaultdict(float), defaultdict(float)
        for r in expected:
            e_sums[_norm(r.get(pol_col))] += _num(r[col], f"expected .{col}")
        for r in actual:
            a_sums[_norm(r.get(pol_col))] += _num(r[col], f"actual .{col}")
        worst_sum = 0.0
        for p in sorted(e_sums.keys() | a_sums.keys(), key=str):
            r = relerr(a_sums.get(p, 0.0), e_sums.get(p, 0.0))
            worst_sum = max(worst_sum, r)
            if r > sums_rel:
                problems.append(
                    f"{col} sum for pollutant {p}: actual={a_sums.get(p, 0.0)!r} "
                    f"expected={e_sums.get(p, 0.0)!r} rel={r:.3e} > {sums_rel:g}"
                )
        report.append(f"worst per-pollutant {col} sum: rel={worst_sum:.3e} ({which} tolerance {sums_rel:g})")

    if problems:
        raise Failure("\n".join(report + [""] + problems))
    return report


# --------------------------------------------------------------------------
# self-test
#
# A comparator that has only ever been run on matching data is untested: every
# check below is written to be *falsified*, because the failure mode that
# matters here is a gate that passes everything.


def _self_test_toml() -> int:
    """The parser must read the real file correctly and refuse what it can't."""
    failed = 0

    def check(name, cond, detail=""):
        nonlocal failed
        if cond:
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name} {detail}")

    real = HERE / "tolerance.toml"
    if real.exists():
        t = load_tolerance(real)
        check("reads [default]", t["default"]["nonroad"] == 1e-2, t.get("default"))
        check("reads bools", t["structure"]["require_exact_key_set"] is True)
        check("reads [cell] rel", t["cell"]["rel"] == 2e-5)
        check("reads a multi-line array",
              t["compare"]["ignored_columns"][0] == "MOVESRunID"
              and "emissionQuantSigma" in t["compare"]["ignored_columns"],
              t["compare"].get("ignored_columns"))
        check("reads a string", t["compare"]["pollutant_column"] == "pollutantID")
        # Every key the comparator reads must actually be present, or a rename
        # in the file becomes a KeyError at fixture time rather than now.
        for sect, key in [("default", "onroad"), ("default", "nonroad"),
                          ("structure", "require_exact_row_count"),
                          ("compare", "value_columns")]:
            check(f"tolerance.toml has [{sect}] {key}", key in t.get(sect, {}))

    # A quoted sub-table header, as a per-fixture override would use.
    t2 = parse_toml_subset('[fixtures."nr-x"]\nrel = 2e-2\nwhy = "because"\n')
    check("quoted sub-table header", t2["fixtures"]["nr-x"]["rel"] == 2e-2, t2)

    # Refusals: each of these must raise rather than be skipped.
    for bad, why in [
        ("rel = @nope", "unparseable value"),
        ("[a]\nx = [1, 2", "unterminated array"),
        ("just_a_bare_word", "line with no ="),
    ]:
        try:
            parse_toml_subset(bad)
            check(f"refuses {why}", False, "it was accepted")
        except ValueError:
            check(f"refuses {why}", True)

    return failed


def _self_test() -> int:
    tol = {
        "default": {"onroad": 1e-3, "nonroad": 1e-2},
        "structure": {"require_exact_key_set": True, "require_exact_row_count": True},
        "cell": {"rel": 2e-5},
        "compare": {
            "value_columns": ["emissionQuant"],
            "ignored_columns": ["MOVESRunID", "iterationID", "roadTypeID"],
            "pollutant_column": "pollutantID",
        },
    }

    def rows(*specs):
        return [
            {"MOVESRunID": 1, "iterationID": 1, "roadTypeID": 100,
             "pollutantID": p, "SCC": s, "modelYearID": m, "emissionQuant": q}
            for p, s, m, q in specs
        ]

    base = rows((1, "A", 2020, "100.0"), (1, "A", 2021, "200.0"), (2, "A", 2020, "300.0"))

    cases: list[tuple[str, list, list, bool]] = []

    # identical inputs must pass
    cases.append(("identical", base, base, True))

    # types differing across the reader boundary must still match
    stringy = [{k: str(v) for k, v in r.items()} for r in base]
    cases.append(("int vs text identity columns", base, stringy, True))

    # ignored columns may disagree freely
    diff_ignored = [dict(r, MOVESRunID=99, iterationID=7, roadTypeID=1) for r in base]
    cases.append(("ignored columns differ", base, diff_ignored, True))

    # a value inside the cell tolerance passes; outside it fails
    cases.append(("cell within tolerance", base,
                  rows((1, "A", 2020, "100.000001"), (1, "A", 2021, "200.0"), (2, "A", 2020, "300.0")), True))
    cases.append(("cell outside tolerance", base,
                  rows((1, "A", 2020, "100.5"), (1, "A", 2021, "200.0"), (2, "A", 2020, "300.0")), False))

    # a dropped row -- the mistake the plan predicts from copying Fortran's
    # `modfrc <= 0` skip -- must fail on the key set, not slip through
    cases.append(("row dropped", base, base[:-1], False))
    # an extra row must fail too
    cases.append(("row added", base, base + rows((3, "A", 2020, "1.0")), False))

    # redistribution: mass moved between model years leaves per-pollutant sums
    # untouched. Only the per-cell check can see it.
    cases.append(("mass redistributed, sums identical", base,
                  rows((1, "A", 2020, "150.0"), (1, "A", 2021, "150.0"), (2, "A", 2020, "300.0")), False))

    # scaling: every row wrong by 5%, key set perfect. Only the sums check and
    # the cell check see it -- and for a *nonroad* fixture the 1e-2 sums gate
    # alone would still catch 5%, so use a magnitude the sums gate misses.
    cases.append(("all cells off by 0.5%, nonroad sums gate alone would pass", base,
                  rows((1, "A", 2020, "100.5"), (1, "A", 2021, "201.0"), (2, "A", 2020, "301.5")), False))

    # A substituted key: right row COUNT, wrong row identity -- an off-by-one in
    # a fallback ladder emits exactly this. It is the only case that isolates the
    # key-set gate, because every other key difference above also changes the row
    # count and would be caught by that check instead. Without this case,
    # disabling `require_exact_key_set` entirely still passed the suite; I
    # checked, which is the only reason it is here.
    cases.append(("key substituted, row count unchanged", base,
                  rows((1, "A", 2020, "100.0"), (1, "A", 2099, "200.0"), (2, "A", 2020, "300.0")), False))

    # --- each gate, alone ---------------------------------------------------
    #
    # Two of the four gates are SUBSUMED by the others when all are on, which a
    # whole-suite sabotage check reports as "disabling it changes nothing":
    #
    #   - row count is implied by the key set. Duplicate keys are rejected, so
    #     with unique keys a differing row count entails a differing key set.
    #   - per-pollutant sums are implied by the per-cell check whenever `[cell]
    #     rel` is tighter than the sums tolerance, which it is by ~500x
    #     (2e-5 vs 1e-2 for nonroad).
    #
    # They are kept because they are not always subsumed -- a per-fixture
    # override can loosen `[cell]`, and `[cell]` may be absent entirely, leaving
    # sums as the only numeric gate; and the sums gate is the one `moves.rs`
    # itself uses across implementations, so it is the documented contract even
    # when it is not the binding one. Each is therefore tested ALONE, which is
    # the only way to test logic that nothing else can reach.
    extra_failures = 0

    def alone(name, exp, act, cfg_tol, should_pass):
        nonlocal extra_failures
        try:
            compare(exp, act, cfg_tol, "nr-self-test")
            ok = True
        except Failure:
            ok = False
        if ok == should_pass:
            print(f"  ok   {name}")
        else:
            extra_failures += 1
            print(f"  FAIL {name}: expected to {'pass' if should_pass else 'FAIL'}, did not")

    # Duplicate detection is subsumed too: a double-emit with a correct row
    # count necessarily leaves some other key missing, which the key set sees.
    # Its value is the DIAGNOSTIC -- "row 3 duplicates key ..." instead of a
    # confusing "1 key missing, 1 extra" -- so it is tested with every
    # structural check off, where nothing else can reach it.
    alone_dup = {**tol, "structure": {}, "cell": {}}
    try:
        compare(base, base[:-1] + [dict(base[0])], alone_dup, "nr-self-test")
        print("  FAIL duplicate detection alone does not catch a double-emit")
        extra_failures_pre = 1
    except Failure as exc:
        got = "duplicates key" in str(exc)
        print(f"  {'ok  ' if got else 'FAIL'} duplicate detection alone names the duplicate")
        extra_failures_pre = 0 if got else 1

    extra_failures += extra_failures_pre
    key_only = dict(tol, structure={"require_exact_key_set": True,
                                    "require_exact_row_count": False})
    alone("key-set gate alone catches a dropped row", base, base[:-1], key_only, False)

    count_only = dict(tol, structure={"require_exact_key_set": False,
                                      "require_exact_row_count": True})
    alone("row-count gate alone catches a dropped row", base, base[:-1], count_only, False)

    # The sums gate with no per-cell check and no structural checks: a 5% error
    # on one pollutant is over the 1e-2 nonroad tolerance, a 0.5% error is not.
    sums_only = {**tol, "structure": {}, "cell": {}}
    alone("sums gate alone catches a 5% pollutant error", base,
          rows((1, "A", 2020, "105.0"), (1, "A", 2021, "210.0"), (2, "A", 2020, "300.0")),
          sums_only, False)
    alone("sums gate alone tolerates 0.5% for a nonroad fixture", base,
          rows((1, "A", 2020, "100.5"), (1, "A", 2021, "201.0"), (2, "A", 2020, "301.5")),
          sums_only, True)
    # ...and the same 0.5% is NOT tolerated for an onroad fixture (1e-3).
    try:
        compare(base, rows((1, "A", 2020, "100.5"), (1, "A", 2021, "201.0"),
                           (2, "A", 2020, "301.5")), sums_only, "mixed-onroad")
        print("  FAIL onroad sums tolerance is not tighter than nonroad")
        extra_failures += 1
    except Failure:
        print("  ok   onroad sums tolerance (1e-3) is tighter than nonroad (1e-2)")

    # a duplicate key is a bug, not a tie
    cases.append(("duplicate key", base, base + [dict(base[0])], False))

    # exact zeros on both sides are equal, not infinitely wrong
    zeros = rows((1, "A", 2020, "0.0"), (1, "A", 2021, "200.0"), (2, "A", 2020, "300.0"))
    cases.append(("expected zero, actual zero", zeros, zeros, True))
    # a zero that should not be -- the binary64 failure mode -- must fail
    cases.append(("expected nonzero, actual zero", base,
                  rows((1, "A", 2020, "0.0"), (1, "A", 2021, "200.0"), (2, "A", 2020, "300.0")), False))

    failed = _self_test_toml() + extra_failures
    for name, exp, act, should_pass in cases:
        try:
            compare(exp, act, tol, "nr-self-test")
            ok = True
            detail = ""
        except Failure as exc:
            ok = False
            detail = str(exc).splitlines()[-1] if str(exc) else ""
        if ok == should_pass:
            print(f"  ok   {name}")
        else:
            failed += 1
            want = "pass" if should_pass else "FAIL"
            print(f"  FAIL {name}: expected to {want}, did not. {detail}")

    print(f"\n  {failed} self-test failure(s)" if failed else "\n  all self-tests ok")
    return 1 if failed else 0


# --------------------------------------------------------------------------


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fixture", help="snapshot fixture name, e.g. nr-logging-county")
    ap.add_argument("--actual", type=pathlib.Path, help="CSV of the rows this repo produced")
    ap.add_argument("--expected", type=pathlib.Path, help="override the snapshot parquet path")
    ap.add_argument("--snapshots", type=pathlib.Path, default=DEFAULT_SNAPSHOTS)
    ap.add_argument("--tolerance", type=pathlib.Path, default=HERE / "tolerance.toml")
    ap.add_argument("--self-test", action="store_true", help="falsify every check and exit")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.fixture or not args.actual:
        ap.error("--fixture and --actual are required unless --self-test")

    try:
        tol = load_tolerance(args.tolerance)
        exp_path = args.expected or snapshot_output_path(args.snapshots, args.fixture)
        report = compare(
            read_expected(exp_path), read_actual(args.actual), tol, args.fixture
        )
    except Failure as exc:
        print(f"FAIL {args.fixture}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    print(f"ok {args.fixture}")
    for line in report:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
