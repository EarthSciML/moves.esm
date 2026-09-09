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
column in the snapshot), so they are parsed with `Decimal` and compared as
floats. Parsing via float() directly would be fine for these magnitudes, but
Decimal makes the "the snapshot is text" fact visible at the one place it
matters, rather than a silent implicit conversion.

HOW MUCH of that text is meaningful depends on the capture, and the two
`moves-snapshot` format versions disagree: v1 wrote twelve decimal PLACES and
threw away every digit below them, v2 writes the shortest decimal that
round-trips the f64 and throws away nothing. `FloatEncoding` below reads which
one a table used off its `.meta.json` and answers the only question a
comparison has of it — how much absolute difference the reference is unable to
record. Both versions are read, because the corpus migrates one branch at a
time and a checkout that can only judge one of them can only test one of them.

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
# how the capture stores a float


class FloatEncoding:
    """What the snapshot's capture can and cannot resolve.

    `moves-snapshot` has had two float encodings and they differ in the one
    thing a comparison needs to know — how much of a difference the REFERENCE
    is incapable of recording:

      * `moves-snapshot/v1` wrote a fixed number of decimal PLACES (twelve).
        That is not twelve significant digits: a cell of 1e-12 keeps one, and
        below 5e-13 nothing survives at all. Half a stored quantum,
        `0.5 x 10^-decimals`, is the resolution the reference actually has.
      * `moves-snapshot/v2` writes the shortest correctly-rounded decimal that
        parses back to a bit-identical f64. Nothing is lost, so the quantum is
        ZERO and there is no storage floor to allow.

    The v2 sidecar does not restate `float_decimals` with some stand-in value;
    it OMITS the field, so a consumer that still reads it fails instead of
    silently deriving a 5e-13 floor that the data does not justify. This class
    is the other half of that contract: the encoding is read from the sidecar,
    every branch is named, and an unrecognised one raises.
    """

    def __init__(self, kind: str, decimals: int | None = None):
        self.kind = kind
        self.decimals = decimals

    @property
    def lossless(self) -> bool:
        return self.kind == "shortest_round_trip"

    @property
    def half_quantum(self) -> float:
        """Absolute slack the ENCODING accounts for. Zero when it loses nothing."""
        return 0.0 if self.lossless else 0.5 * 10.0 ** (-self.decimals)

    def __str__(self) -> str:
        if self.lossless:
            return "shortest_round_trip (moves-snapshot/v2, lossless)"
        return f"fixed_decimals, decimals = {self.decimals} (moves-snapshot/v1)"


def read_float_encoding(meta_path: pathlib.Path) -> FloatEncoding | None:
    """Read a table's float encoding off its `.meta.json`. `None` if there is none.

    `None` means "no sidecar at all", which is a different fact from either
    encoding and is kept distinguishable: a fixture whose comparison depends on
    the capture's resolution must not proceed on a guess.
    """
    if not meta_path.exists():
        return None
    import json as _json
    meta = _json.loads(meta_path.read_text())
    enc = meta.get("float_encoding")
    if enc is not None:
        kind = enc.get("kind")
        if kind == "shortest_round_trip":
            return FloatEncoding("shortest_round_trip")
        if kind == "fixed_decimals":
            d = enc.get("decimals")
            if not isinstance(d, int):
                raise Failure(
                    f"{meta_path.name} declares float_encoding kind "
                    f"'fixed_decimals' with no integer `decimals`: {enc!r}"
                )
            return FloatEncoding("fixed_decimals", d)
        raise Failure(
            f"{meta_path.name} declares an unknown float_encoding kind "
            f"{kind!r}. This comparator knows 'fixed_decimals' and "
            f"'shortest_round_trip'; refusing to guess a tolerance floor."
        )
    if "float_decimals" in meta:
        # moves-snapshot/v1, which had no `float_encoding` field at all.
        return FloatEncoding("fixed_decimals", int(meta["float_decimals"]))
    raise Failure(
        f"{meta_path.name} carries neither `float_encoding` nor "
        f"`float_decimals`, so how much precision the capture holds is "
        f"unknown. Refusing to guess."
    )


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


def compare(expected: list[dict], actual: list[dict], tol: dict, fixture: str,
            encoding: FloatEncoding | None = None) -> list[str]:
    """Return a list of report lines. Raises `Failure` with the report on a diff."""
    cfg = tol["compare"]
    structure = tol.get("structure", {})
    value_cols = cfg["value_columns"]
    pol_col = cfg["pollutant_column"]

    if not expected:
        raise Failure("the snapshot's MOVESOutput is empty; nothing to compare")

    report: list[str] = []
    problems: list[str] = []

    # --- declared scope -----------------------------------------------------
    #
    # A fixture may declare, in tolerance.toml, pollutants whose cells this
    # snapshot cannot support a comparison for. This is NOT a tolerance and it
    # is not a shortfall: the rows are still emitted, with the right keys and
    # the right arithmetic, and every check below still runs at full strength
    # on everything else. What it says is that the snapshot's own capture
    # destroyed the evidence -- see tolerance.toml, where the reason is
    # mandatory and the measurement is written out.
    #
    # It is applied to BOTH sides, so a scoped-out pollutant cannot show up as
    # a missing key either, and it is reported before anything else so that a
    # reader cannot mistake the row count for the whole table.
    scope = tol.get("fixtures", {}).get(fixture, {}).get("scope", {})
    excluded = [int(p) for p in scope.get("excluded_pollutants", [])]
    if (excluded or scope.get("allow_storage_quantum")) \
            and not str(scope.get("why", "")).strip():
        raise Failure(
            f"tolerance.toml declares a scope for {fixture} with no `why`. "
            f"A scope without a reason is a bug being hidden."
        )
    if excluded:
        drop = {_norm(p) for p in excluded}
        keep = lambda rows: [r for r in rows if _norm(r.get(pol_col)) not in drop]
        n_exp, n_act = len(expected), len(actual)
        expected, actual = keep(expected), keep(actual)
        if not expected:
            raise Failure("the declared scope excludes every row of the snapshot")
        report.append(
            f"scope: pollutant(s) {', '.join(str(p) for p in excluded)} are NOT "
            f"compared -- {n_exp - len(expected)} of {n_exp} snapshot rows and "
            f"{n_act - len(actual)} of {n_act} emitted rows held out"
        )
        report.append(f"       why: {scope['why']}")

    # A capture that writes floats with a fixed number of DECIMAL places stores
    # a small value to very few significant digits: at float_decimals = 12, a
    # cell of 1e-12 keeps one. Where a fixture declares it, the comparison is
    # made at the resolution the reference is actually stored in -- half a
    # stored quantum of absolute slack, read off the snapshot's own
    # `.meta.json` and not fitted here -- which is the same concession relerr()
    # already makes for an expected zero, one step earlier. It is OPT-IN so
    # that no other fixture's gate moves, and it is an ABSOLUTE floor: the
    # relative gate is unchanged above it and every cell the capture stores in
    # full is held to it exactly as before.
    #
    # The floor is DERIVED FROM THE ENCODING and not from the flag. Against a
    # `moves-snapshot/v2` capture the encoding loses nothing, the floor is 0.0,
    # and the declaration therefore allows NOTHING -- the flag goes inert on
    # its own when the obstacle it names disappears, rather than quietly
    # keeping a 5e-13 concession the data no longer needs. That is said out
    # loud in the report, because "the same flag, now allowing nothing" is a
    # change of gate a reader must be able to see.
    half_quantum = 0.0
    if scope.get("allow_storage_quantum"):
        if encoding is None:
            raise Failure(
                f"{fixture} declares allow_storage_quantum but there is no "
                f"MOVESOutput `.meta.json` beside the snapshot parquet, so the "
                f"capture's resolution is unknown"
            )
        half_quantum = encoding.half_quantum
        if half_quantum:
            report.append(
                f"       storage: comparing at the capture's own resolution, "
                f"{encoding}, so {half_quantum:g} absolute "
                f"is allowed beneath the relative gate"
            )
        else:
            report.append(
                f"       storage: the capture is {encoding}, so the declared "
                f"storage floor allows NOTHING and every cell is held to the "
                f"relative gate. The declaration is now dead weight."
            )

    keys = key_columns(list(expected[0].keys()), cfg)

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
    worst_gated = (0.0, None)
    cells_checked = 0
    over = []
    if cell_rel is not None:
        for k in sorted(shared):
            for col in value_cols:
                e = _num(exp_by_key[k][col], f"expected {show(k)} {col}")
                a = _num(act_by_key[k][col], f"actual {show(k)} {col}")
                # TWO numbers, and they are not the same quantity. `r` is the
                # relative error and stays comparable with every other
                # fixture's headline figure; `gated` is the same difference
                # with the capture's own half-quantum taken off first, and it
                # decides pass/fail only where a fixture declared the floor.
                # Conflating them would silently change what "worst relative
                # error" means in one rung's oracle output.
                r = relerr(a, e)
                gated = r
                if half_quantum:
                    excess = max(0.0, abs(a - e) - half_quantum)
                    gated = excess / abs(e) if e else excess
                    if gated > worst_gated[0]:
                        worst_gated = (gated, (k, col, a, e))
                cells_checked += 1
                if r > worst[0]:
                    worst = (r, (k, col, a, e))
                if gated > cell_rel:
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
            if half_quantum:
                # Said separately and labelled differently, because it is a
                # different quantity: the worst error IN EXCESS of the
                # capture's half-quantum, which is what the gate above was
                # applied to. The line above stays the figure that is
                # comparable across rungs.
                report.append(
                    f"worst cell, excess over the {half_quantum:g} storage "
                    f"quantum: rel={worst_gated[0]:.3e} (this is the number the "
                    f"{cell_rel:g} gate was applied to)"
                )

    # 4. per-pollutant sums
    which = "nonroad" if fixture.startswith(NONROAD_PREFIX) else "onroad"
    sums_rel = tol.get("fixtures", {}).get(fixture, {}).get("rel", tol["default"][which])
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

    def alone(name, exp, act, cfg_tol, should_pass, encoding=None):
        nonlocal extra_failures
        try:
            compare(exp, act, cfg_tol, "nr-self-test", encoding=encoding)
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

    # --- the declared scope ------------------------------------------------
    #
    # Three falsifications, because an exclusion is the one mechanism here that
    # makes a check do LESS and it has to be shown to do exactly that much.
    scoped = {**tol, "fixtures": {"nr-self-test": {"scope": {
        "excluded_pollutants": [2], "why": "a self-test reason"}}}}
    # (a) a pollutant that is wrong is still caught when it is NOT excluded.
    alone("scope: an error in a pollutant that is not excluded still fails", base,
          rows((1, "A", 2020, "150.0"), (1, "A", 2021, "200.0"), (2, "A", 2020, "300.0")),
          scoped, False)
    # (b) the excluded pollutant's cells are genuinely not compared -- and the
    #     key set does not report them as missing either.
    alone("scope: the excluded pollutant is not compared", base,
          rows((1, "A", 2020, "100.0"), (1, "A", 2021, "200.0"), (2, "A", 2020, "999.0")),
          scoped, True)
    # (c) an exclusion with no reason is refused.
    no_why = {**tol, "fixtures": {"nr-self-test": {"scope": {"excluded_pollutants": [2]}}}}
    try:
        compare(base, base, no_why, "nr-self-test")
        print("  FAIL an exclusion with no `why` was accepted")
        extra_failures += 1
    except Failure as exc:
        got = "no\n`why`" in str(exc).replace(" ", "\n") or "why" in str(exc)
        print(f"  {'ok  ' if got else 'FAIL'} an exclusion with no `why` is refused")
        extra_failures += 0 if got else 1

    # --- the storage floor ---------------------------------------------------
    #
    # It must absorb a difference the CAPTURE explains and nothing larger, and
    # it must be derived from the encoding the sidecar declares rather than from
    # the flag -- so the SAME declaration against a lossless capture absorbs
    # nothing. All three directions are falsified here, because the middle one
    # is the whole content of the v1 -> v2 consumer change and a floor that
    # silently survived the migration would be indistinguishable from one that
    # correctly went to zero.
    V1_12 = FloatEncoding("fixed_decimals", 12)
    V2 = FloatEncoding("shortest_round_trip")
    q = {**tol, "fixtures": {"nr-self-test": {"scope": {
        "allow_storage_quantum": True, "excluded_pollutants": [], "why": "x"}}}}
    tiny = rows((1, "A", 2020, "0.000000000001"), (1, "A", 2021, "200.0"),
                (2, "A", 2020, "300.0"))
    tiny_off = rows((1, "A", 2020, "0.0000000000014"), (1, "A", 2021, "200.0"),
                    (2, "A", 2020, "300.0"))
    # 4e-13 out on a cell stored as 1e-12 is inside half a v1 quantum: absorbed.
    alone("storage floor: a difference inside half a stored quantum is absorbed",
          tiny, tiny_off, q, True, encoding=V1_12)
    # The same difference against a LOSSLESS capture is a 40% error and fails:
    # v2 leaves no storage slack for the flag to spend.
    alone("storage floor: under moves-snapshot/v2 the same difference FAILS",
          tiny, tiny_off, q, False, encoding=V2)
    # 5% on a cell the capture stores in full is NOT absorbed under either.
    alone("storage floor: a real error on a well-stored cell still fails",
          tiny, rows((1, "A", 2020, "0.000000000001"), (1, "A", 2021, "210.0"),
                     (2, "A", 2020, "300.0")), q, False, encoding=V1_12)
    # And the flag with no sidecar at all is refused rather than defaulted.
    alone("storage floor: declared with no sidecar encoding, refused",
          tiny, tiny, q, False, encoding=None)

    # --- reading the encoding off a sidecar ----------------------------------
    #
    # `float_decimals` was REPLACED by `float_encoding` and not restated, so
    # that an un-updated consumer fails loudly instead of deriving a floor the
    # data does not support. These four cases pin both spellings, the
    # deliberate loudness, and the refusal to guess.
    import json as _json
    import tempfile as _tempfile
    with _tempfile.TemporaryDirectory() as _td:
        def enc_of(name, payload):
            p = pathlib.Path(_td) / f"{name}.meta.json"
            p.write_text(_json.dumps(payload))
            return read_float_encoding(p)

        def enc_case(name, payload, want):
            nonlocal extra_failures
            try:
                got = str(enc_of(name.replace(" ", "_"), payload))
            except Failure as exc:
                got = f"refused: {exc}"
            ok = want in got
            print(f"  {'ok  ' if ok else 'FAIL'} encoding: {name}")
            if not ok:
                extra_failures += 1
                print(f"       wanted {want!r} in {got!r}")

        enc_case("v1 float_decimals is read", {"float_decimals": 12},
                 "decimals = 12")
        enc_case("v2 float_encoding is read",
                 {"float_encoding": {"kind": "shortest_round_trip",
                                     "max_significant_digits": 17}}, "lossless")
        enc_case("an explicit fixed_decimals encoding is read",
                 {"float_encoding": {"kind": "fixed_decimals", "decimals": 6}},
                 "decimals = 6")
        enc_case("an unknown kind is refused, not guessed",
                 {"float_encoding": {"kind": "posits"}}, "refused")
        enc_case("a sidecar declaring neither is refused",
                 {"schema": []}, "refused")
        missing = read_float_encoding(pathlib.Path(_td) / "absent.meta.json")
        ok = missing is None
        print(f"  {'ok  ' if ok else 'FAIL'} encoding: an absent sidecar is None, "
              f"not an encoding")
        if not ok:
            extra_failures += 1

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
        meta = exp_path.with_suffix("").with_suffix(".meta.json")
        report = compare(
            read_expected(exp_path), read_actual(args.actual), tol, args.fixture,
            encoding=read_float_encoding(meta),
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
