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
| `docs/` | The two port specifications, the conventions doc, and the findings. |
| `tools/` | `check-conventions.py`, which enforces mechanically what a review would otherwise have to eyeball; `check-sources.py`, which opens every declared Parquet file and checks the columns; `shortfall.py`, which judges a fixture's failure against what `tolerance.toml` says to expect; `cross-check-chain.py`, which compares the mounted assembly's rows against the fixture's in ulps. |

## Testing

`./run-tests.sh` runs everything and is the only thing you need. In order: a
self-test of the comparator, `esm validate` on every document, the conventions
check, `esm test` (the inline §6.6 tests), a round-trip check, the scaling gate,
the known-limitations tripwire, the `data_sources` declarations against the
Parquet, the fixture run — materialize, assert, emit, compare — and a
cross-check that the two independently authored chains agree.

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

**The two chains are compared to each other, in ulps.**
`runs/nr_logging_county_run.esm` and `fixtures/nr-logging-county.esm` are
separate documents with separate equations that compute the same four
model-year-2020 rows — one from mounted component leaves, one from the snapshot
Parquet. Each passed its own gate against its own transcribed numbers, at
tolerances far tighter than the gap between the two, and nothing compared them.
Agreement between independent routes is the check this repo leans on hardest,
so that was a hole. They evaluate in different precisions on purpose — the
fixture per-operation binary32, the assembly binary64 — so the bound is **ulps
of binary32**, not a relative fraction: three rows agree bit-exactly and one
differs by exactly one ulp, which is per-operation rounding versus a single
final cast. A relative bound loose enough to pass that row would be 10⁻⁷, four
orders looser than what either document asserts internally.

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
embedded in `docs/nonroad-logging-county.md` §6.5, and
`./run-onroad-oracle.sh` does the same for `docs/mixed-onroad.md` §6.5 — all
82 rows of `sho` to 4.1 × 10⁻⁶ and all 250 of `MOVESOutput` to 8.2 × 10⁻⁶, with
the base rate read from the reference and the output saying so. It reproduces all 144 rows of
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
exactly 0.0 in binary64 — which no expression can distinguish.

`domain.element_type: "Float32"` is honoured, per operation, and a
**per-variable** `element_type` overrides it — necessary because a
document-wide float precision destroys ten-digit join keys (`docs/findings`
F18). The override is **strict**: mixing precisions inside one operator is a
compile error, not a silent coercion. The fixture declares `Float32` with 19
SCC-valued variables at `Float64`, and both halves are verifiably live in one
run: all 12 emitted values are exactly binary32-representable where none of the
binary64 values was, and the SCC stays `2260007005` rather than collapsing to
`2260006912`.

**But that cohort is not what the element type settles here, and four files in
this repo used to say it was.** `agedist.f`'s fold is a recurrence the format
cannot spell (F12), so the fixture *carries* the grown fractions as a `const`
whose third value is 5.89 × 10⁻⁸ — positive in either precision. Its twelve
rows never depended on the element type; the document had the right row set for
a reason none of those four files stated, and no gate noticed. What the element
type is needed for is the *other two* SCCs, once F12 lands and their folds are
computed rather than carried. `docs/esm-conventions.md` §17.5 records this.

## A warning about zeros

This toolchain's characteristic failure is returning a plausible wrong value
rather than raising. Six independent instances so far, each on a document that
validates cleanly, with no error and no warning: a `data_sources` entry read by
no provider; the same when the published `earthsciio` shadows the local
checkout; an `aggregate` range symbol named `t`, which makes `join.on` match
nothing; `skolem`/`distinct` materializing empty; an index set sized by `extent`
discovery, which stayed at its placeholder; and `element_type: "Float32"`, which
returned the binary64 answer — since fixed, and the entry stays because the
*class* of failure is the point, not the individual bug.

Four of the six returned `0`. One returned `NaN` — the same defect in a
different shape, because an unbound *array* forcing reads as NaN where a scalar
reads as zero. The last returns a number that is right to fifteen digits and
wrong in the sixteenth, which is the hardest of all to see and changes how many
rows exist.

Zero is the worst possible sentinel here. It is a *legal* emission quantity, it
flows through a sum without leaving a NaN to trace, and a per-pollutant
tolerance absorbs it.

The defence is structural rather than vigilance, and is why the repo is shaped
as it is: every inline test asserts a specific expected value rather than a
bound, `run-oracle.sh` provides an independent implementation to attribute a
disagreement to, and the exact key set catches the row-shaped version. Five of
the six were found by running something real and checking the number against an
independent source, not by reading code. Assume the next instance exists and
has not been found.

**That defence is audited, not asserted.** A gate that cannot fail is worse
than no gate, so every assertion in the repo has been perturbed and checked to
go red:

| what | result |
|---|---|
| all 457 distinct assertions in `components/` and `runs/`, perturbed by 10⁻³ | **886 of 886 evaluations fail, 0 pass** |
| the fixture's 84 perturbable assertions, at ×(1+10⁻⁵) | **84 of 84 fail** |
| the same, at ×(1+4 × 10⁻⁷) | 80 fail; the 4 survivors are the one test whose `rel: 1e-6` is older than the float32 work |
| the F18 control, override dropped / domain forced to Float64 | 2 of 3 fail / 1 of 3 fails |

The zero-valued ones are the case that matters most and the easiest to get
wrong. 68 of the 457 assert *exactly* zero — an earlier version of this
paragraph claimed none did — and a zero assertion whose tolerance hides a
non-zero is decoration. Nudged to 10⁻³, all 68 go red.

## Status

**Phases 0, 1 and 2 are complete, and Phase 3 has its specification and its
first four components.** Fifteen components cover all seven NONROAD stages of
`nr-logging-county` and four of the six onroad stages of `mixed-onroad`, with
**457 distinct inline assertions** whose numbers each trace to a named section
of a port specification.

`esm test` reports 886, and the difference is worth knowing rather than
quoting: mounting a component into an assembly **re-runs that component's own
tests in the assembly's context**, so 429 of the 886 are re-executions. The
nonroad assembly declares 9 assertions of its own and runs 275 — its ten
mounted components' 266, plus its 9. That is not redundancy: a mount is
precisely where this toolchain has been caught changing behaviour — dropped
`join.on` key columns (F1), unmerged `index_sets` (F2), `enums` colliding
first-wins and applying the wrong value (F13) — so re-running a component's
assertions under the mount is the only check that would catch it, and it is
free. But 886 overstates how much independent checking exists, so the headline
number is 457.

Both blockers on the first end-to-end fixture comparison are closed: the CLI
now wires a data provider and `simulate --format csv` emits a relational
document's rows. Verified against the real snapshot — 1,183 rows of a column
sized by `extent` discovery, summing to 181564.4520000001, matching pyarrow
exactly.

**The fixture evaluates in Float32.** It declares
`domain.element_type: "Float32"` with 19 SCC-valued variables overridden to
`Float64` — the override exists because honouring a float precision
document-wide destroys ingested integer keys above 2²⁴
(`docs/findings/README.md` F18). 87 of 87 inline assertions pass, the 12 rows
and their key set are unchanged, and the worst cell moved from 4.025 × 10⁻⁶ to
4.046 × 10⁻⁶ against a 2 × 10⁻⁵ gate. Not one expected value changed; ten
assertion tolerances moved to exactly 2⁻²³, one binary32 epsilon, which is the
tightest a binary32 evaluation can ever satisfy and still fails a perturbation
of 3.4 epsilons.

Nothing needed splitting to get there, and that was luck with a cause worth
knowing: `lib/keys.esm`'s SCC ladders take their presence tests as
*predicates*, because §3 of the conventions wanted the test to be a separate
`max`-semiring aggregate for join cost. Written the way a reader of `prccty.f`
reaches for first — `has_exact*scc + (1-has_exact)*sccZero2` — all five ladders
would be `mixed_element_type` errors.

**What stands between the NONROAD chain and the 144th row is F12 alone** —
`agedist.f`'s thirty-year fold is a recurrence over an index axis that the
format cannot spell, and the fixture's other two SCCs each need their own
result from it. A closed form over the residual sequence is
verified exact — 0 of 1,581 cells differ per equipment point, float32, six
equipment points — but substituting it leaves a deconvolution, so the recurrence
survives every reduction and the fix is a format addition.

`mixed-onroad` has no fixture yet, and `docs/mixed-onroad.md` §7.4 says why
rather than recording a shortfall: everything in that 250-row chain is
computable from the snapshot's input tables except one relation of 46 numbers,
the drive-cycle operating-mode distribution, which canonical MOVES computes
inside its worker and drops. §7.3 isolates it by solving for it and shows the
base rate factorises exactly around it. A document emitting 250
correctly-keyed rows with an uncomputed rate would fail the per-cell gate for
a reason no `[shortfall]` record can express; one reading the reference's own
`baserate_1_2020` would pass by transcribing the answer. Neither is a fidelity
test, so the four components check what can be checked without the snapshot
and `run-onroad-oracle.sh` checks the rest against it.

See `PLAN.md` for the plan of record and `docs/findings/README.md` for what the
toolchain still cannot do — sixteen open findings, and four retired because
they were fixed.
