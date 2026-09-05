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
Parquet, the fixture run — materialize, assert, emit, compare — a cross-check
that the two independently authored chains agree, and the independent oracles.

Three stages are worth explaining because their polarity is unusual.

**The known-limitations tripwire fails when a test starts passing.** Each file
in `docs/findings/` reproduces an upstream defect and asserts the behaviour we
want, so it fails today. A repro going green is good news that has to be acted
on — a limitation quietly fixed leaves a workaround in the tree for no reason.

**A fixture comparison that falls short fails at a RECORDED size, and there are
no such records left.** `nr-logging-county` computed twelve of its 144 rows for
a long time, and `tolerance.toml` carried the shortfall with its reason while it
did; `compare-output.py` failed on it, as it should — a comparator that can be
told to pass is not a comparator — and `tools/shortfall.py` checked that the
failure was still exactly the recorded one, firing if it grew, if it shrank, or
if an emitted row drifted. It shrank to nothing: both fixtures now match their
snapshots completely. The machinery stays, and `run-tests.sh` fails if a
`[shortfall]` record is ever left behind a comparison that has started
passing.

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
82 rows of `sho` to 4.1 × 10⁻⁶ and all 250 of `MOVESOutput` to 8.3 × 10⁻⁶, and
it takes **nothing** from the reference: it used to read `baserate_1_2020`,
because the drive-cycle operating-mode distribution the base rate needs is
computed inside the MOVES worker and dropped, and it computes that instead
(§10). It reproduces all 144 rows of
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
this repo used to say it was.** `agedist.f`'s fold was a recurrence the format
could not then spell (F12), so the fixture *carries* the grown fractions as a
`const` whose third value is 5.89 × 10⁻⁸ — positive in either precision. Its twelve
rows never depended on the element type; the document had the right row set for
a reason none of those four files stated, and no gate noticed. What the element
type is needed for is the *other two* SCCs, once the fixture computes their
folds rather than carrying them. `docs/esm-conventions.md` §17.5 records this.

## A warning about zeros

This toolchain's characteristic failure is returning a plausible wrong value
rather than raising. **This list is the authoritative count** — other documents
in this repo cite an instance by its number here, and should not number one
themselves. Ten independent instances so far, each on a document that runs
clean, with no error and no warning:

1. a `data_sources` entry read by no provider;
2. the same when the published `earthsciio` shadows the local checkout;
3. an `aggregate` range symbol named `t`, which makes `join.on` match nothing;
4. `skolem`/`distinct` materializing empty;
5. an index set sized by `extent` discovery, which stayed at its placeholder;
6. `element_type: "Float32"`, which returned the binary64 answer;
7. a CWD-anchored `url_template`, which resolves, succeeds, and reads a
   *different file* — the same document converted from three directories gave
   three different paths (F7/F15);
8. a causal self-reference dropped on the ingesting path (F24);
9. an undeclared operand dropped rather than named, again only when the
   document ingests — `max(known, undeclared)` quietly becomes `max(known)`
   (F25);
10. an index symbol used outside the `aggregate` that binds it, read as index
    zero and contributing the additive identity, again only on the path an
    ingesting document takes (F26). It reached 109 of `nr-logging-county`'s 144
    output cells past 343 of 343 green assertions, and was caught by diffing
    against a previous run — not by any gate.

The fixed ones stay listed, because the *class* of failure is the point rather
than the individual bug.

**Eight, nine and ten were one defect, and one fix closed all three** — which is
the strongest evidence this list has that it tracks a *class* rather than a run
of unrelated bugs. A name unbound at evaluation returned `NaN`, and IEEE-754
`max`/`min` return the **non-NaN** operand: a clamp does not propagate that
sentinel, it absorbs it, and the operand disappears with every downstream digit
finite. Eight arrived through an array not yet built, nine through a name
declared nowhere, ten through a symbol used out of scope — three doors, one arm.
It is now `E_TREEWALK_UNBOUND_NAME` on every route (EarthSciAST `a1dc9bb30`).
Instrumented before the fix, that arm was read **zero times across 119 suites
and 1,399 tests**: on every valid document in the corpus it was dead code
returning a sentinel, which is why it survived three findings.

Six of the ten returned `0`. One returned `NaN` — the same defect in a
different shape, because an unbound *array* forcing reads as NaN where a scalar
reads as zero. One returns a number right to fifteen digits and wrong in the
sixteenth, which is the hardest of all to see and changes how many rows exist.
And the eighth is the one to reason from: the runtime **did** return the loud
`NaN`, and a `max(·, 0)` clamp destroyed it, because IEEE-754 `max` returns the
non-NaN operand. That was the first sentinel manufactured by a clamp rather
than returned by the runtime, and MOVES clamps everywhere — `agedist.f`'s fold
body is `max(·, 0)`, and so is `prccty.f`'s skip test and half the scrappage
arithmetic. In this port a NaN sentinel is not a defence.

Number 7 is the only one caught before it shipped, and it is worth saying how:
an author noticed that their own fix would *create* it. The CWD anchoring was
already there and already wrong, but loud — a CWD-anchored `ref` fails. Making
`url_template` resolve the same way would have converted a loud failure into a
silent one.

Zero is the worst possible sentinel here. It is a *legal* emission quantity, it
flows through a sum without leaving a NaN to trace, and a per-pollutant
tolerance absorbs it.

The defence is structural rather than vigilance, and is why the repo is shaped
as it is: every inline test asserts a specific expected value rather than a
bound, `run-oracle.sh` provides an independent implementation to attribute a
disagreement to, and the exact key set catches the row-shaped version. Eight of
the ten were found by running something real and checking the number against an
independent source, not by reading code — and number ten was found by neither,
but by diffing one run against the previous one, which is the method this list
did not have before.

**Three of the ten were on the ingesting path, which is why it is now the first
place to look, and all three are now fixed upstream.** F24 lost a self-read there, F25 loses an
undeclared operand there, and F26 loses an unbound index symbol there; all
three are the same sentence: that route re-resolves names against a map built
for the pipeline, and a name the map does not hold becomes an absence instead
of an error. Every fixture in this repo ingests. The prediction under the
previous version of this paragraph — assume the next instance exists and has
not been found — was written before F26 and was right within the week; it still
stands.

**That defence is audited, not asserted.** A gate that cannot fail is worse
than no gate, so every assertion in the repo has been perturbed and checked to
go red:

| what | result |
|---|---|
| all 585 declared assertions in `components/` and `runs/`, perturbed by 10⁻³ | **1,116 of 1,116 evaluations fail, 0 pass** |
| the 416 in `fixtures/`, same perturbation | **416 of 416 fail, 0 pass** |
| the 4 in `gates/`, same perturbation | **4 of 4 fail, 0 pass** |
| `nr-logging-county`'s 84 perturbable assertions **as it stood at twelve output rows**, at ×(1+10⁻⁵) | **84 of 84 fail** |
| the same, at ×(1+4 × 10⁻⁷) | 80 fail; the 4 survivors are the one test whose `rel: 1e-6` is older than the float32 work |
| the F18 control, override dropped / domain forced to Float64 | 2 of 3 fail / 1 of 3 fails |

That is all 1,005 of them, which it had never been: the audit used to stop at
`components/` and `runs/`, so the fixtures — the documents that actually ingest,
and where all three silent findings on that path were eventually found — had no
evidence any of their assertions could fail. They can; 32 of the 416 in
`fixtures/` assert exactly zero and all 32 go red.

The two fine-grained rows above are marked with the version they were measured
on and have not been re-run since `nr-logging-county` went from 12 output rows
to 144: its assertion count went 196 → 416 and its tolerances gained two
entries. `tools/perturbation-audit.py` covers the whole of it at 10⁻³ and is
what run-tests.sh and every commit rely on; the ×(1+4 × 10⁻⁷) sweep is a
sharper instrument that is worth re-running by hand rather than quietly
restating.

The zero-valued ones are the case that matters most and the easiest to get
wrong. 91 of the 585 in `components/` and `runs/` assert *exactly* zero — an earlier version of this
paragraph claimed none did — and a zero assertion whose tolerance hides a
non-zero is decoration. They are nudged *additively*, because `x × (1 + ε)`
leaves a zero exactly where it was: a purely multiplicative audit skips every
one of them and still reports a clean sweep. Nudged to 10⁻³, all 91 go red.

**That audit is now a checked-in tool rather than a claim about the past.**
`tools/perturbation-audit.py` re-derives the whole table in one command, which
matters because the earlier hand-run version had gone stale without saying so:
it covered 457 assertions and 128 more were added after it, so for a while the
sentence above was true only of the assertions that happened to predate it. The
documents are perturbed **in place** and restored from git — not copied to a
scratch directory — because two of them ingest, and a `url_template` resolves
against its own document's directory (F15), so a copy elsewhere reads a
different file or nothing. The tool is itself checked the same way it checks
everything else: at a 10⁻¹³ nudge it must name survivors and exit non-zero, and
it does.

## Status

**Phases 0–3 are complete, and Phase 4 has two slices — both wired, and both
complete.** Twenty components cover all seven NONROAD stages of
`nr-logging-county`, S1–S12 and S15–S18 of `mixed-onroad`, and all of
`process-evap-leaks` and `process-evap-fvv`; `fixtures/mixed-onroad.esm` covers
the whole onroad chain, including the drive-cycle operating-mode distribution no
component can carry, against the snapshot's own tables.

**`process-evap-leaks` was the first fixture with no shortfall at all**: 128 of
128 rows against the snapshot `MOVESOutput`, key set exact — 128 shared, 0
missing, 0 extra, verified against the Parquet directly on all 20 identity
columns — worst cell 7.294 × 10⁻⁶ against a 2 × 10⁻⁵ gate that was not
widened, and 0 cells over it. Its oracle reads *nothing* from the reference.

**`process-evap-fvv` is the second, and it corrected the choice of the third.**
128 of 128 rows, key set exact, worst cell 7.495 × 10⁻⁶ against the same
un-widened 2 × 10⁻⁵ gate, and its oracle also reads *nothing* from the
reference — where `./run-permeation-oracle.sh` has to read 192
`AverageTankTemperature` cells. It adds `TankFuelGenerator`, whose
`AverageTankGasoline` is captured **empty** in all three evaporative snapshots
and therefore has to be computed rather than read.

What it establishes is mostly negative and is the more useful half.
`docs/evap-permeation.md` §0.3 had argued FVV would be the slice that finally
exercised a recurrence on the fixture path, because
`MultidayTankVaporVentingCalculator` reads `ColdSoakTankTemperature` directly.
It does — and the whole venting half of that calculator lands in operating mode
151, whose `opModeFraction` is exactly 0 here as it was there. Measured by
computing the venting chain in full and then perturbing it: 2,688 non-zero
cold-soak base rates, and **all 128 output cells bit-identical** under a +50 °F
perturbation of `ColdSoakTankTemperature`, a doubling of the venting equation,
a tripling of the soak recurrence's carry and a ×7 of the cold-soak fraction.
The mechanism is structural — `fractionOfOperating` is identically 1 at an
on-network link, so `1 − fractionOfOperating` zeroes every soak mode — so **no
evaporative process would have answered the recurrence question**; a run
selecting road type 1 would. `docs/evap-fvv.md` §8.3 says so, and
`docs/esm-conventions.md` §23 is the rule that came out of it.

Choosing the leaks slice corrected this plan. `PLAN.md` had said Phase 4's cheapest
slice was start exhaust, because its operating-mode distribution is in the
snapshot. Measured across all 39 snapshots, `MOVESOutput` contains **zero rows
with `processID` 2** — every onroad fixture selects road type 4 and
`BaseRateCalculator` discards the road-type-1 start rates — so a start-exhaust
slice has nothing to validate against, which is also why eight fixtures have no
output rows at all. Leaks was chosen instead because it needs neither the
uncomputable drive-cycle distribution nor the thirty-year fold.

Running the component and assembly directories reports 1,116 against 585
declared there, and the difference is worth knowing rather than quoting:
mounting a component into an assembly **re-runs that component's own tests in
the assembly's context**, so 531 of those 1,116 are re-executions. The
nonroad assembly declares 9 assertions of its own and runs 296 — its ten
mounted components' 287, plus its 9. That is not redundancy: a mount is
precisely where this toolchain has been caught changing behaviour — dropped
`join.on` key columns (F1), unmerged `index_sets` (F2), `enums` colliding
first-wins and applying the wrong value (F13) — so re-running a component's
assertions under the mount is the only check that would catch it, and it is
free. But a run count overstates how much independent checking exists, so the
headline number is what the documents declare.

Both blockers on the first end-to-end fixture comparison are closed: the CLI
now wires a data provider and `simulate --format csv` emits a relational
document's rows. Verified against the real snapshot — 1,183 rows of a column
sized by `extent` discovery, summing to 181564.4520000001, matching pyarrow
exactly.

**The nonroad fixture evaluates in Float32, and its row COUNT depends on it.**
It declares `domain.element_type: "Float32"` with 20 SCC-valued variables
overridden to `Float64` — the override exists because honouring a float
precision document-wide destroys ingested integer keys above 2²⁴
(`docs/findings/README.md` F18). When that landed, 87 of 87 inline assertions
passed, the 12 rows of the day were unchanged and the worst cell moved from
4.025 × 10⁻⁶ to 4.046 × 10⁻⁶ — but the row set did not yet depend on the
precision, because the fixture still carried `agedist.f`'s answer as data. It
computes the fold now, six times, once per equipment point: model year 2018 of
SCC `2260007005` survives on a grown fraction of 5.888558263222876 × 10⁻⁸,
which is exactly binary32's `5.8885583e-08` and is exactly `0.0` in binary64.
Four of the 144 rows exist because the declared element type is honoured.

Nothing needed splitting to get there, and that was luck with a cause worth
knowing: `lib/keys.esm`'s SCC ladders take their presence tests as
*predicates*, because §3 of the conventions wanted the test to be a separate
`max`-semiring aggregate for join cost. Written the way a reader of `prccty.f`
reaches for first — `has_exact*scc + (1-has_exact)*sccZero2` — all five ladders
would be `mixed_element_type` errors.

**`agedist.f`'s thirty-year fold is computed**, in
`components/age_distribution.esm`, guarded by 55 of that file's assertions and
verified against the reference fold at *zero* tolerance — 306 of 306 cells
bit-exact across all six equipment points. The format gained a spelling for it
(F12): an `aggregate` body that reads its own array-shaped left-hand side at a
strictly earlier index is a causal self-reference, which needed no new operator
and no new schema field.

**The fixture computes it too, and carries nothing.** F24 — the reason it could
not — is fixed upstream, pinned, and verified here on the ingestion axis that
build could not reach. `fixtures/nr-logging-county.esm` now derives
`age_grownModelYearFraction` from the snapshot rather than transcribing it, and
reproduces the reference's three `real*4` values **to the last bit**:
3.707268476486206 *is* binary32's 3.7072685, and 5.888558263222876 × 10⁻⁸ *is*
binary32's 5.8885583 × 10⁻⁸. That third number is the whole of §7.3 — it is
positive only because the age-3 survival is 5.96 × 10⁻⁸ in `real*4` where
binary64 makes it exactly zero, and it decides whether this SCC has three model
years or two. **The document's row set is now produced by its declared element
type instead of resting on a constant that was typed in.**

That left the equipment-point axis as the only thing between the fixture and 144
rows, and it was ordinary authoring rather than a missing capability — but more
of it than "widen the axis". `prccty.f` loops over the `nrsourceusetype` rows
the RunSpec's SCCs select, six here, three of them sharing one SCC, so an output
row is a SUM over points and its model-year set is the UNION of their `nyrlif`s.
That union is ragged (3, 29 and 4 model years) and gappy (`2265007010` is
missing 1991, 2000–2002 and 2006–2010 out of a 1983–2020 span), and a `ragged`
index set does not evaluate (**F14**). The shape that works is a rectangular
6 × 51 grid of (equipment point, age slot), a membership mask that is
`prccty.f`'s skip written as TWO gates, and a prefix-count rank that compacts the
survivors onto a flat 144-row output relation — `docs/esm-conventions.md` §22.
It lands at 144 rows, key set exact, worst cell 4.561 × 10⁻⁶.

Restoring the fold is also what turned up **F25**: the fixture passed 120 of 120
with `minimumGrowthPopulation` undeclared, because on the ingesting path the
operand was dropped rather than named, and the floor could not bind on this
data anyway. `esm validate` rejected the same bytes. That is the second silent
failure found on that path, after F24.

`mixed-onroad` is the fourth fixture with no shortfall: **250 of 250 rows, key
set exact, worst cell 8.320 × 10⁻⁶ against the same 2 × 10⁻⁵ gate, worst
per-pollutant sum 9.675 × 10⁻⁸.** It was the last chain in the port with an
uncomputed relation, and the shape of that gap is worth keeping: everything in
those 250 rows was computable from the snapshot's input tables *except* 46
numbers — the drive-cycle operating-mode distribution, which canonical MOVES
computes inside its worker and drops. `docs/mixed-onroad.md` §7.3 isolated it by
solving for it and showed the base rate factorises exactly around it, and §7.4
argued that a document emitting 250 correctly-keyed rows with an uncomputed rate
would fail the per-cell gate for a reason no `[shortfall]` record can express,
while one reading the reference's own `baserate_1_2020` would pass by
transcribing the answer. So neither was wired, and the relation was computed
instead — from 63,602 second-by-second drive-schedule speeds, in the fixture and
in the oracle independently, agreeing cell by cell to one ulp. Computing it moved
the worst cell from 8.231 × 10⁻⁶ to 8.320 × 10⁻⁶. §10 is the port.

See `PLAN.md` for the plan of record and `docs/findings/README.md` for what the
toolchain still cannot do — thirteen open findings, and twelve retired
because they were fixed.
