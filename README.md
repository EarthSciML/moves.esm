# moves.esm

An implementation of the EPA [MOVES/NONROAD](https://github.com/USEPA/EPA_MOVES_Model)
model as [EarthSciAST](https://earthsciml.github.io/EarthSciAST/) `.esm`
documents.

All model logic lives in `.esm` files. There is no Python or Rust in this repo
that computes an emission — the scripts here build the toolchain, run the tests,
and compare results against a reference. That constraint is the point: a MOVES
calculator written as a declarative relational document can be read against the
SQL step table it ports, in a way a reimplementation in a general-purpose
language cannot.

## Getting started

```sh
./build-esm.sh     # build ./esm from the sibling EarthSciAST checkout
./run-tests.sh     # the whole suite
```

`build-esm.sh` expects `../EarthSciAST` and `../EarthSciIO` as sibling
checkouts. It writes `esm-version.lock`, recording which commit of **each** it
built from — both, because the binary's behaviour depends on both trees and
their version numbers are identical, so the version number alone identifies
nothing.

The binary itself, `./esm`, is deliberately untracked.

## Layout

| path | what it is |
|---|---|
| `lib/` | Expression-template libraries. The reusable shapes — the deterioration curve, the exhaust temperature adjustment, unit conversion — each defined exactly once and imported by reference. |
| `components/` | One `.esm` per calculator. Tables stay tables; joins are `join.on`; literals come from `enums`. |
| `runs/` | Run-level assemblies that mount components. |
| `fixtures/` | The documents that read the snapshot Parquet and are compared against its `MOVESOutput`. One per snapshot; each declares the tables it reads as `data_sources`. |
| `gates/` | Performance gates, currently the `join.on` scaling assertion. |
| `docs/` | The port specification, the conventions doc, and the findings. |
| `tools/` | `check-conventions.py`, which enforces mechanically what a review would otherwise have to eyeball; `check-sources.py`, which opens every declared Parquet file and checks the columns; `shortfall.py`, which judges a fixture's failure against what `tolerance.toml` says to expect. |

## Testing

`./run-tests.sh` runs everything and is the only thing you need. In order: a
self-test of the comparator, `esm validate` on every document, the conventions
check, `esm test` (the inline §6.6 tests), a round-trip check, the scaling gate,
the known-limitations tripwire, the `data_sources` declarations against the
Parquet, and the fixture run — materialize, assert, emit, compare.

Three stages are worth explaining because their polarity is unusual.

**The known-limitations tripwire fails when a test starts passing.** Each file
in `docs/findings/` reproduces an upstream defect and asserts the behaviour we
want, so it fails today. A repro going green is good news that has to be acted
on — a limitation quietly fixed leaves a workaround in the tree for no reason.

**The fixture comparison is expected to fail, at a recorded size.** The port
computes twelve of `nr-logging-county`'s 144 rows today, and those twelve agree
with the snapshot to 4.0 × 10⁻⁶. `compare-output.py` fails on that, as it
should — a comparator that can be told to pass is not a comparator — so
`tolerance.toml` records the shortfall with its reason and `tools/shortfall.py`
checks that the failure is still exactly that one. It fires if the shortfall
grows, if it shrinks, or if a row this port does emit drifts. See §11.2 of the
conventions for what the other 132 rows need, which is not more `.esm`.

**The comparator is tested before it is trusted.** `compare-output.py` judges
whether output matches the reference, so a bug in it that passes everything
would be invisible. Its falsification suite runs first, and was itself verified
by disabling each gate in turn and confirming the suite goes red. That found
two real problems, including a hardcoded `exit 0` in this script that discarded
a failure recorded moments earlier.

## Fidelity

The reference is the set of characterization snapshots in `../moves.rs`, each
carrying both the ~200 input tables and the expected `MOVESOutput`. No canonical
MOVES, MariaDB or JVM is needed to develop against them.

Tolerances live in `tolerance.toml`, with the reasoning next to the numbers.
They are not a copy of the reference implementation's own tolerance file, which
encodes a byte-identity contract appropriate to diffing two runs of one binary
and not to comparing two implementations.

`./run-oracle.sh` extracts and runs the independent float32 reproduction
embedded in `docs/nonroad-logging-county.md` §6.5. It reproduces all 144 rows of
`nr-logging-county` to 4.9 × 10⁻⁶. Its purpose is attribution: when a document
disagrees with the snapshot, a third implementation is what tells you whether
the document is wrong or the specification is. `--float64` runs the same chain
in binary64, which drops four rows — see below.

### Why the comparison is layered

`compare-output.py` checks row count, an exact key set, a per-cell relative
tolerance, and per-pollutant sums. That is more than one gate because the
failures this port can actually produce are invisible to the loose one.
Measured, by perturbing the real `nr-logging-county` snapshot:

| perturbation | per-pollutant sums | caught by |
|---|---|---|
| the four rows a Fortran-faithful `modfrc <= 0` skip suppresses, dropped | agree to 1.2 × 10⁻⁸ | key set only |
| those same four cells emitted as zero | agree to 1.2 × 10⁻⁸ | per-cell only |
| mass moved between two model years of one SCC | agree to 2 × 10⁻¹⁶ | per-cell only |

The per-pollutant tolerance is 10⁻². It would have passed all three.

### The binary64 rule

MOVES NONROAD is `real*4` Fortran and the reference port is bit-exact `f32`
throughout. EarthSciAST evaluates in binary64. Running the oracle in both
precisions: the age-loop bound is *identical*, but the `modfrc <= 0` skip fires
exactly one more time (31 → 32), dropping model year 2018 of SCC 2260007005
across all four pollutants — 144 rows becomes 140. The surviving cells still
agree to 6.9 × 10⁻⁶.

So the divergence is structural, not a magnitude a looser tolerance could
absorb — and the fix is *not* to drop the skip. Measured on the same oracle:

| skip predicate | float32 | binary64 |
|---|---|---|
| `modfrc <= 0` (the reference) | **144** | 140 |
| `modfrc < 0` | 188 | 188 |
| no skip at all | 188 | 188 |

Forty-four candidate cohorts have a grown fraction of *exactly* zero, so a
document without the skip over-emits by 44 in either precision. **Reproduce the
reference's control flow, and author for float32 semantics**: the remaining
difference is one cohort — SCC 2260007005 / MY2018, 5.96 × 10⁻⁸ in float32 and
exactly 0.0 in binary64 — which no expression can distinguish and which
evaluating the document in float32 settles. `domain.element_type: "Float32"` is
ignored at the pinned toolchain and is being fixed upstream.

## A warning about zeros

This toolchain's characteristic failure is returning `0` rather than raising.
Four independent instances turned up in a single day, each on a document that
validates cleanly, with no error and no warning: a `data_sources` entry read by
no provider; the same when the published `earthsciio` shadows the local
checkout; an `aggregate` range symbol named `t`, which makes `join.on` match
nothing; and `skolem`/`distinct` materializing empty.

Zero is the worst possible sentinel here. It is a *legal* emission quantity, it
flows through a sum without leaving a NaN to trace, and a per-pollutant
tolerance absorbs it.

The defence is structural rather than vigilance, and is why the repo is shaped
as it is: every inline test asserts a specific non-zero expected value rather
than a bound, `run-oracle.sh` provides an independent implementation to
attribute a disagreement to, and the exact key set catches the row-shaped
version. Assume the next instance exists and has not been found.

## Status

Phases 0 and 1 are complete, and the first end-to-end fidelity comparison runs:
both blockers that stood in front of it are fixed upstream — the CLI now builds
a data provider per consumed `data_sources` entry and samples a source's extent
before closing metaparameters, and `simulate --format csv` writes the rows of a
document that has nothing to integrate. `fixtures/nr-logging-county.esm` reads
seventeen snapshot tables and reproduces the twelve `MOVESOutput` rows of SCC
2260007005 to 4.0 × 10⁻⁶.

The remaining 132 rows are two more SCCs, and the blocker is not authoring
effort: each equipment point needs its own `agedist.f` result, and that
thirty-year fold is a recurrence with no spelling in the format
(`docs/findings/README.md` F12). See `PLAN.md` for the plan of record and the
findings file for what else the toolchain cannot yet do.
