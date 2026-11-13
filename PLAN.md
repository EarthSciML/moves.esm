# Implementation plan — MOVES/NONROAD as EarthSciAST `.esm`

Goal: reproduce the end-to-end example simulations in `../moves.rs` — its 39
green characterization fixtures (`characterization/fixtures/*.xml` →
`characterization/snapshots/<fixture>/`) — with all model logic expressed in
`.esm` documents, tests in their `tests` sections, analyses in their `analyses`
sections, and everything driven by the EarthSciAST Rust CLI.

This plan is grounded in probes run against the current EarthSciAST tree
(`esm 0.2.0`, built from `EarthSciAST@8936d81be`). Findings that shaped it are
in [§1](#1-what-the-probes-established) with their evidence, because two of them
overturn the obvious design.

**§2 and §3 cover the second half of the pipeline only** — execution database to
`MOVESOutput`, which is where all 734 of the fixtures' `data_sources` read. The
front half, RunSpec XML and the default database, is
[Phase 7](#phase-7--runspec-to-output-in-esm-planned-2026-09-10), and it is not
started. Module coverage is a real number that measures a different thing than
the goal does.

---

## 1. What the probes established

### 1.1 MOVES maps onto the ESM array model cleanly

MOVES is not an ODE system — it is a relational pipeline of joins and
sum-products (see the step tables in
`moves.rs/crates/moves-calculators/src/calculators/criteria_running_calculator.rs`,
which name each SQL working table and its port). The ESM `aggregate` op is the
Functional Aggregate Query `sum_product` (esm-spec §4.3.1): `output_idx` is the
`GROUP BY`, `reduce: "+"` is the `SUM`, `join.on` / `filter` is the `ON` clause.
A probe computing `emis[p] = Σ_s act[s]·rate[s,p]` and a key-matched join both
returned exactly the hand-computed answers.

### 1.2 Component tests need no ODE solve; `simulate` still does

`esm simulate` drives a BDF integrator, and a document whose equations are all
algebraic — as every MOVES quantity is — fails with
`Exceeded maximum number of nonlinear solver failures at time = 0`. Adding one
trivial state, `D(clock) ~ 0`, makes the run succeed and evaluates every
observed correctly.

The `esm test` subcommand now being added evaluates observed fields **without**
an ODE simulation, so component-level inline tests need no such crutch.
Convention: **components carry no `clock`.** Only a runnable assembly driven
through `simulate` adds one, and that need disappears once array-observed
output lands (§1.5).

### 1.3 The equi-join gate is a prerequisite, not an optimization — **built**

> **Status: landed** in EarthSciAST `28bda86ac`. Measured on the merged tree:
> at 10⁸ combinations with 10⁴ matches the driven contraction runs in
> **0.032 s**; the undriven arm needs 0.184 s at 10⁷, an order of magnitude
> *smaller*. Cost now tracks matches, not the product. The rest of this section
> is the reasoning that got there, kept because §1.3.1 is now the record of what
> was built. See §1.3.2 for what shipped.

MOVES is a join pipeline, and the `.esm` must read like one — a reader should
see the same relational steps `moves.rs` names in its SQL step tables. That
makes `aggregate`'s `join.on` the spelling for every join in this
implementation. It does not currently perform, and making it perform is the
first thing this project builds.

An `aggregate` contracting two row axes under an equality gate is today a
genuine O(N×M) nested loop:

| combinations | `filter` | `join.on` |
|---|---|---|
| 5 × 10⁵ | 2.4 s | — |
| 1 × 10⁷ | 95 s | **> 120 s (timed out)** |
| 1 × 10⁸ | > 120 s (timed out) | — |

(debug build; a release build shifts the constant, not the exponent)

`join.on` is the *semantically* correct spelling — an inner equi-join, RFC
`semiring-faq-unified-ir` §5.3, with many-to-many defined and unmatched rows
contributing the additive identity. But `pkg/earthsci-ast-rs/src/join.rs` says
plainly what it does with it: the key pair "is lowered into a
member-value-equality predicate ANDed into the node's `filter` … so the
evaluator reuses its existing `filter` gate with no new value-equality path on
the hot loop." Measured, it is slightly *slower* than the hand-written filter —
the extra coding step showing up.

Surveying the three index mechanisms:

| Mechanism | What it indexes | On the numeric path? |
|---|---|---|
| `join.overlap` | Spatial: AABB envelope broad phase, R*-tree / STRtree | **Yes** — the gate *drives enumeration* from a candidate set built once per node, so cost is `O(\|candidates\|·∏ungated)`, not `O(∏ranges)` (CONFORMANCE_SPEC §5.5.6) |
| `join.on` | Value equality on key columns | No — lowered to `filter` |
| `skolem` / `rank` / `distinct` | Value invention: canonical keys and dense IDs | No — `relational.rs` is a build-time engine, run once at setup |

**Both halves of the fix already exist.** `join.overlap` proves the pattern:
its candidate set is "built ONCE per node," and it drives enumeration rather
than testing every tuple. And `relational.rs` already contains a deterministic
hash-bucketed `equijoin` / `group_aggregate` kernel, written to the same §5.5
cross-binding determinism contract. They are simply not connected.

#### 1.3.1 What has to be built

An equality-driven gate for `join.on`, structurally the mirror of
`join.overlap`:

1. **Candidate set once per node.** Build the match set with the hash-bucketed
   kernel in `relational.rs`, emitted sorted by canonical key per §5.7 rule 5,
   so the result stays byte-identical across bindings.
2. **The gate drives enumeration.** Bind the two gated symbols from the
   candidate set rather than testing every tuple of the full product — cost
   `O(|matches|·∏ungated)`. The three binding cases `overlap` already
   specifies (both contracted, one bound, both bound) carry over unchanged.
3. **Admit data-column keys.** Today `join.rs` rejects a key that "resolves to
   no loop symbol (a join keyed on a genuine data column, not an iterated
   index)." MOVES joins are overwhelmingly on data columns — one table's
   `sourceTypeID` against another's. Encoding every key column as a
   categorical index set whose members *are* the key values is a workable
   fallback (a probe confirms it loads and evaluates), but it is a
   transcription of the data into the schema, and the legible form wants the
   column itself.

Item 3 is what decides whether the `.esm` reads like the SQL it ports, so it
belongs in the same piece of work as items 1 and 2, not after them.

#### 1.3.2 What shipped, and one thing we did not expect

All three items landed. `join.rs` resolves each `on` pair to a `(loop symbol,
key column)` where the column may be a genuine declared 1-D variable — **the
data-column rejection is gone**, so a MOVES join spells as one table's
`sourceTypeID` against another's. `relational.rs` gained the `equijoin`
primitive its own docs had promised but never had. `OverlapGate` generalized to
`JoinGate`, so the two gate kinds differ only in how the pair set is computed
and `overlap`'s three binding cases carry over verbatim.

Two things worth knowing beyond the plan:

**A latent correctness bug, not just a performance one.** `prepare.rs`
evaluates observeds directly and had a resolution hook for `overlap` symbols
but none for `on`. So a `join.on` on a build-time observed reached the
evaluator with neither the predicate nor the gate attached — **an unfiltered
full product, silently wrong**. That is precisely the path a relational `.esm`
takes. It is fixed, and an unresolvable key column is now a build error rather
than an ignored clause.

**A fourth drive shape.** Where both gated symbols are contracted *alongside*
other contracted axes, the later gated axis walks only the earlier one's
partner list, removing the whole `N_later` factor. A MOVES rollup hits this the
moment it also sums over months — which every fixture does.

The equality still lowers into `filter` *as well as* attaching the gate. That
is a deliberate asymmetry with `overlap`: an overlap gate is a conservative
broad phase with the author's filter behind it, so declining to drive is free,
whereas an `on` gate is exact with nothing behind it. Keeping the predicate
makes every non-consulting path correct for free, and makes driven-vs-undriven
directly comparable — which is what the kill-switch differential tests exploit.

Not yet done: Julia does not implement the gate (`BEHAV-10-B-001`/`-004`, with
a written handoff); Python admits data columns but is one item behind. Neither
blocks us — Rust is the binding that executes here.

The performance envelope to aim at: a probe contracting 600,000 output cells —
the size of `emissionratebyage` — through gather-shaped access ran in 5.8 s in
a debug build. Cost proportional to matches, not to pairs, is what the gate
has to deliver.

### 1.4 Bulk data comes through `data_sources` — which needed a Parquet reader — **done**

A variable's `default` must be a scalar number; array literals are rejected at
load. Array data reaches a document three ways: an inline `const`-op array (fine
for hand-checkable unit tests, and what the probes used), a `function_tables`
entry (capped at **2 axes** in v0.4.0, so useless for MOVES' 4–6 key
dimensions), or a `data_sources` entry. So: `const` for inline tests,
`data_sources` for fixtures.

EarthSciIO's Rust readers are `ff10`, `geotiff`, `netcdf`, `shapefile`, `zarr` —
**there is no Parquet reader**, and the `moves.rs` snapshots are Parquet
throughout. Rather than convert every fixture's ~200 input tables into
Zarr/NetCDF, add the reader (§3, Phase 0). Its format registry is explicitly
built for this: "a second reader … registers under a new name **without
touching the `Provider`** — exactly the extensibility invariant the three
registries exist to guarantee." The `netcdf` reader is 222 lines, and Parquet's
Arrow-typed columns map onto the `NativeDataset` contract more directly than
CF-decoded NetCDF does. This deletes a whole conversion stage from every
fixture and lets the `.esm` documents read the oracle data in place.

**Landed** (EarthSciIO `c2c603d`): `parquet` is a registered format name in the
Rust reader, decoding a file as a flat table — one rank-1 field per column over
`index` — with column selection pushed down as a real projection, verified at
the byte level. Registered without touching `Provider`. Rust track only; the
Python and Julia registries deliberately do not claim `parquet`, so those
tracks give a clean registration gap rather than a wrong decode
(`spec/parquet-bindings-handoff.md` is the work order). Note `rust-version`
moved 1.74 → 1.85, arrow-rs's MSRV.

**One snapshot detail with teeth.** MOVES snapshot floats are stored as
*decimal text*, not floats. In `nr-logging-county`'s `MOVESOutput`, every ID
column is `int64` and `SCC` is a string — but so are `emissionQuant`,
`emissionQuantMean`, and `emissionQuantSigma`, held as strings like
`"261.000000000000"` for byte-reproducibility. So the reader's `float_columns`
option is not an edge case for us; **every fixture must declare its float
columns**, or the emission quantities arrive as strings. The reader parses
decimal text under that option and refuses the unparseable.

**Landed in all three bindings**, with a cross-language conformance corpus case
(EarthSciIO `7a4ce2a`). Writing the second and third implementations is what
found the first one's bugs, which is the argument for having done it that way:

- Rust refused a `uint64` past `int64::MAX` under `float_columns` — the range
  check sat in the decode rather than the integer coercion, the same shape as an
  earlier `Binary` bug.
- **Parquet2.jl reads a narrow fixed-length decimal as UNSIGNED.** A
  `decimal128(9,2)` cell holding `-2.50` decoded as `42949670.46` — silently, no
  error. Verified independently by arithmetic: the unscaled value is −250, and
  read unsigned over 4 bytes that is 2³²−250 = 4294967046, ÷100 = 42949670.46
  exactly. Compensated for in the Julia track rather than tolerated.
- Julia's `Provider` applied the `variables` projection *after* the decode, so a
  column the document never named could still fail the read; and an empty
  `variables` read no columns instead of every column, against the spec and both
  other tracks.

`spec/conformance.md` now draws the distinction that makes this reviewable: a
backend *gap* is a permitted divergence, recorded so a corpus case does not
encode a difference it cannot fix; a backend defect producing a *wrong number*
is never one, and gets compensated for in the track.

### 1.5 CLI gaps

| Gap | Status |
|---|---|
| No `esm test` subcommand | **Closed** (EarthSciAST `fb0544b8a`). Takes files *or directories searched recursively*, and prints a per-file table naming the model and the failing assertion. `--reltol`/`--abstol` are the *solver* tolerances — how accurately a test is integrated — not the §6.6.4 tolerance its assertions are judged against, which each test declares for itself. |
| `simulate` reports only *scalar* observeds | **Closed** (EarthSciAST `a784c5444`). Confirmed real first: an array observed was absent from `simulate --output` entirely, while a scalar one in the same model appeared. Now `SolveOptions::output_observed` names the subset to emit, `simulate --observed <NAME>` selects it, and `--format grid` renders `derive_output_plan` — which the CLI had never called. Array observeds flatten to one row per cell under the same cell-key scheme an array *state* gets, so both land on one grid. |
| Data sources off by default | `esio` is an opt-in Cargo feature — `esm simulate` silently loads no data unless built with it. |
| **The CLI wires no provider at all** | **OPEN, and a blocker for the Phase 2 exit criterion.** Worse than the row above, and independent of it: `PrepareProvider` is supplied by the *caller* through `PrepareOptions`, and `src/bin/esm.rs` supplies none — `esio_provider` has no in-crate caller outside the library's own tests. So no CLI subcommand can load a `data_sources` entry, with or without the feature. |
| **`earthsciio` resolves to the registry, not the sibling checkout** | **Closed here** by `build-esm.sh`. `Cargo.toml` pins `earthsciio = "0.1.2"` from crates.io; the local EarthSciIO tree is *also* 0.1.2, so cargo has no reason to prefer it and silently keeps the registry copy — which has no `parquet.rs`. Every MOVES snapshot table is parquet. |

Also: the checked-in `target/release/esm` in EarthSciAST is stale (Aug 11,
schema predating the `state`/`observed` → `unknown` rename). Build fresh — and
build through `./build-esm.sh`, which encodes the feature and the patch and
records both in `esm-version.lock`.

**All three of these gaps fail the same way: silently.** Measured, on a
document that validates cleanly and reads a real 1,183-row column of the
`nr-logging-county` snapshot: the aggregate over it evaluates to `0`, no error,
no warning. A fixture comparison written against that binary would report
agreement having compared nothing. That is why `build-esm.sh` exists and why
the fixture stage cannot be trusted until the provider is wired.

Two smaller facts the same probe established, both of which Phase 2 inherits:
`nrsourceusetype`'s `hpAvg`, `loadFactor`, and `hoursUsedPerYear` are **`string`
columns of decimal text** (12 decimal places), so `float_columns` is mandatory
rather than an optimization; and `hp` is **not a recognised unit** — `W` and
`kW` are, so horsepower must be carried as one of those or as dimensionless.

The rename itself has already landed on `main`: a variable's `type` now accepts
only `unknown` or `parameter`, and a document written with `observed` is
rejected at validation. "Observed" survives as the *concept* this plan uses
throughout — a quantity the model computes rather than integrates — but it is
not a schema value. Every hand-authored document must say `unknown`.

### 1.6 Fidelity will be tolerance-based, not bit-exact

`moves.rs`'s NONROAD port is deliberately `f32` throughout to stay
bit-identical to the Fortran `real*4` reference, and preserves Fortran
associativity operation by operation
(`crates/moves-nonroad/src/emissions/exhaust.rs`, "Numerical-fidelity policy").
ESM evaluated in `binary64` when this was written. It no longer does:
`domain.element_type: "Float32"` is honoured **per operation**, and a
per-variable override carries the identifier columns a float precision would
destroy (§1.6.2, `docs/findings` F18). Set a relative tolerance and record it
anyway — the per-operation rounding matches, but associativity is not promised,
so do not promise bit equality.

**Which tolerance, though, is not the obvious one.** An earlier draft of this
plan said to mirror `moves.rs/characterization/tolerance.toml`. That is wrong:
that file sets `default_float_tolerance = 0.0` — byte identity — and exists to
diff two runs of the *same* binary against the same container image. `moves.rs`
says so in the file itself, and its own full-suite regression gate
(`crates/moves-cli/tests/full_suite_regression.rs`, `canonical_snapshot_diff`)
deliberately bypasses it, because a cell-level `MOVESOutput` diff is unusable
for canonical-vs-port comparison: the two tables disagree on metadata and
labeling columns that carry no emitted mass (`iterationID`, `roadTypeID`, the
SCC road-type subfield) and on which uncertainty columns are even present.

The gate that actually runs there compares per-pollutant `emissionQuant` sums
with relative tolerances defined in-test — `ONROAD_REL_TOL = 1e-3`,
`NONROAD_REL_TOL = 1e-2`, justified per fixture in
`moves.rs/docs/known-divergences.md` §1b/§4.2. Our `tolerance.toml` mirrors
*that*, and keeps the structural checks exact: the emitted key set and the row
count must match the snapshot exactly regardless of the float tolerance. A
per-fixture override requires a written reason — an override without one is a
bug being hidden.

#### 1.6.1 Measured: binary64 costs four rows, and the fix is a modelling rule

No longer a projection. Running the `nr-logging-county` reproduction in both
precisions:

| precision | result |
|---|---|
| `float32` | 144/144 rows, max relative error **4.9 × 10⁻⁶** |
| `float64` | 140/144 — four cells compute **exactly zero** |

The four are `(THC, CO, NOx, PM) × SCC 2260007005 × modelYear 2018`. The cause
is one operation in `moves.rs/crates/moves-nonroad/src/driver/scrptime.rs`:
`100 × ((100 − 73.5)/100) / (100 − 73.5)` is `0.99999994` in binary32 and
exactly `1.0` in binary64, so `1 − yryrfrcscrp` is one ulp versus zero. The age
distribution carries that 5.96 × 10⁻⁸ through 30 iterations, and a
`modfrc <= 0` skip then does or does not fire.

**Under the gate we actually apply this costs nothing.** Those four cells carry
2.4 × 10⁻⁵ g out of 5,146 g, so per-pollutant `emissionQuant` sums in binary64
come out at worst **2.6 × 10⁻⁶** relative — three orders inside the 1 × 10⁻²
NONROAD tolerance, and inside a per-cell 2 × 10⁻⁵ as well.

**But it breaks the structural check.** In the binary64 run the four keys are
*absent*, not zero — the Fortran skip suppresses the row. Against
`require_exact_key_set = true` that is a failure.

**An earlier version of this section prescribed the wrong fix**, and it is
recorded here rather than quietly deleted because it was acted on: it said the
`.esm` should not reproduce `modfrc <= 0` as row suppression, and should emit
every key its joins produce. Measured, that is false:

| skip predicate | float32 | float64 |
|---|---|---|
| `modfrc <= 0` (the reference) | **144** | 140 |
| `modfrc < 0` | 188 | 188 |
| no skip at all | 188 | 188 |

The skip is load-bearing — it removes 44 keys, because 44 age cohorts have
`modfrc` **exactly** zero. Dropping it, or relaxing it to `< 0`, over-emits by
44. `docs/nonroad-logging-county.md` §7.3 already said both and rejected both.

Only **one** cohort is borderline, and nothing written in-document can identify
it: in f32 its `modfrc` is 5.96 × 10⁻⁸ and in binary64 exactly `0.0`, which is
indistinguishable from the 44 legitimate zeros.

### 1.6.1a Measured against the .esm, not the oracle **[Phase 2, complete]**

The end-to-end comparison is complete. `fixtures/nr-logging-county.esm` reads
the snapshot tables through `data_sources` and emits **all 144** MOVESOutput
rows -- the run's three SCCs over its six `nrsourceusetype` equipment points --
through `simulate --format csv`. Against the snapshot:

```
rows: 144 actual / 144 expected
key set: 144 shared, 0 missing, 0 extra
worst cell: rel=4.561e-06 over 144 cells (tolerance 2e-05)
worst per-pollutant emissionQuant sum: rel=2.079e-06 (nonroad tolerance 0.01)
```

So the per-cell gate this plan sets is met by every row the port produces, at
under a quarter of its tolerance, and `tolerance.toml` carries no `[shortfall]`
record for this fixture any more.

**§1.6.1's four-row binary64 question is now LIVE, and the answer holds.** It
was not, for as long as the fixture carried `agedist.f`'s grown fractions as
data (finding F12, then F24): MY2018's 5.9e-08 arrived already positive in
either precision. The fixture now COMPUTES the fold, six times, once per
equipment point, and reproduces the reference's real*4 fractions in all 306
cells of the (point, age slot) grid -- including the one that decides those four
rows. So the row count is produced by the declared element type, which is
exactly what §1.6.2 said it would take.

The rest of what had to be true is not about precision at all: the emitted key
set is ragged, and the shape that works -- a rectangular grid, a membership
mask, and a rank that compacts it onto a flat output relation -- is written up
as `docs/esm-conventions.md` §22. F14 said a `ragged` index set does not
evaluate; that was a spelling error in this port's repro rather than a defect,
and it is retired.

### 1.6.2 `element_type: "Float32"` was declared, documented, and ignored — **now honoured**

*(Historical, and now landed — see the end of this subsection. One correction
to its premise: the four rows are recoverable by evaluating the FOLD in f32,
which the fixture does not do — it carries the fold's output as data because of
F12, so its own twelve rows never depended on the element type. §1.6.1a has
this right; `docs/esm-conventions.md` §17.5 records where four other files did
not.)*

So the four rows are recoverable only by evaluating in f32 — and the one
mechanism the format offers for that does not work. A document declaring
`domain.element_type: "Float32"` still computes in binary64. Verified twice:
once with literals, and once with **every operand a runtime parameter**, so a
build-time constant fold cannot explain it. `100 × ((100 − 73.5)/100) /
(100 − 73.5)` returns `1`, not `0.99999994`. There is no cast or round-to-f32
operator in the schema either.

That is the same silent-wrong-behaviour class as the four zero-returning
defects in §5 — a schema field that is accepted, documented, and does nothing.

**Decision: fix it upstream.** The field is already specified, so honouring it
is a bug fix rather than new surface; it keeps all model logic inside the
`.esm` as CLAUDE.md requires; it fixes every NONROAD fixture at once rather
than this one; and the independent oracle confirms a full-f32 evaluation
reproduces all 144 rows at 4.897 × 10⁻⁶. The `.esm` therefore keeps the
`modfrc <= 0` skip exactly as the reference writes it.

Two routes considered and not taken: precomputing `yryrfrcscrp` in f32 outside
the document and feeding it in as data (§7.3's suggestion — correct, but moves
a computation out of the `.esm`), and recording 140/144 as a known divergence
(cheapest, but weakens `require_exact_key_set`, which this plan says elsewhere
not to weaken). Do not add a four-key allow-list.

**Landed** (EarthSciAST `973ee7360`). The fix is larger than "round the two
kernels" because the evaluator turned out to have **seven** definitions of
`x + y`, only one of them the nominal kernel table: the shared tables, the
vectorized `vec_combine` arms, two fused-tape paths, the sum-of-products
fusion, the relational engine's `vi_eval_op`, and the semiring `⊕`. Each was
documented as bit-identical to the shared kernel, and each was — *in binary64*.
The witness kept returning `1.0` with four Float32 resolutions already in
place, because the arm it actually executed was `vec_combine`.

That is worth recording beyond this fix: "audited for a silent f64 fallback"
had to mean enumerating every monomorphized arm, not trusting a comment that
says two functions are the chokepoint.

Rounding also had to reach *ingress* — document `const` literals, parameters,
`u0`, host and provider arrays — so that every live value is
binary32-representable and array reads need no per-element rounding. Three
constructs are refused rather than silently widened: binary64-only ops
(`intersect_polygon`, `interp.*`, `datetime.julian_day`), a declared extent
above 2²⁴ (index arithmetic shares the value kernels), and **time integration**,
since diffsol is instantiated at f64. That last is a judgement call the
implementer flagged for disagreement; it is right. Integrating in binary64
while the document declares binary32 would be precisely the silently-wrong-
answer class this project keeps hitting, and MOVES needs algebraic and
relational evaluation, not integration.

---

### 1.6.3 …and honouring it document-wide turned out to be the wrong shape

Declaring `Float32` on the real fixture produced `SCC 2260006912` and emission
quantities of **exactly zero**, on a document that validates and runs. Isolated
to one ingested column: 214 distinct SCC codes collapse to **48**, and all 1,183
rows differ. Binary32 is exact for integers only to 2²⁴ = 16,777,216; an SCC is
2.26 × 10⁹, 135× beyond. `2265007010` and `2265007015` both become
`2265007104`, so a join over them merges two equipment categories.
`docs/findings/README.md` F18 carries the full measurement.

Two mistakes in reaching that, both instructive. A `const`-array repro passed —
the corruption is on the **ingested** path, where a relational model's keys
live. And the next repro passed too, because
`|2260001024 − 2260001010| / 2.26 × 10⁹` is 6.2 × 10⁻⁹, four orders **inside**
the default 1 × 10⁻⁶ relative tolerance. **A relative tolerance cannot see key
corruption**: it is relatively tiny and semantically total. That is the sharpest
argument this project has produced for `require_exact_key_set`.

**Decision: a per-variable `element_type` overriding the document's.** The
reference is `real*4` in its floating-point *quantities* while its keys stay
Fortran `INTEGER` and `CHARACTER` — one document-wide float precision cannot
express that split, so it reproduces the arithmetic and destroys the keys.

Three pieces, and the third is the one that matters. Schema: an optional field
on `ModelVariable`, separate from its semantic `type`. Ingress: skip rounding
for an exempt variable — cheap, the rounding sites already know which variable
they fill. **Arithmetic**: exempting ingress alone is not enough, measured — the
SCC fallback ladder computes `floor(scc/1000)*1000`, which is `2260007000` in
f64 and `2260006912` in f32, so the first expression node undoes it. Values must
carry their precision, with an operation taking the wider of its operands.

No integer arithmetic is needed: f64 is exact for every integer below
9.0 × 10¹⁵, and every key here is at most 2.26 × 10⁹. And an exempt value
flowing into an f32 quantity must be an explicit narrowing or a hard error —
silent mixed precision would be a fresh instance of §5's failure mode
(the count lives in README's "A warning about zeros"; this one has not
happened, because the mixing is a compile error).

## 2. Target ladder

Snapshot `MOVESOutput` row counts, the honest measure of fixture size:

| rows | fixture | path |
|---|---|---|
| 128 | **`process-evap-permeation`**, **`-leaks`**, **`-fvv`** | onroad evap |
| 144 | **`nr-logging-county`** | NONROAD |
| 250 | **`mixed-onroad`**, `expand-day` | onroad base-rate |
| 336 | **`process-refueling`** | onroad evap |
| 744–750 | **`process-brakewear`** (750), **`process-tirewear`** (750), `expand-criteria` | onroad |
| 872 | **`process-nox-speciation`** | onroad speciation |
| 1,080 | `chain-tog-speciation`, `chain-nonhaptog` | speciation chains |
| 1,936–2,355 | `nr-lawn-garden-county`, `nr-construction-state` | NONROAD |
| 15,801–23,108 | `nr-industrial-county`, `nr-agriculture-state`, `nr-railroad-support-nation`, … | NONROAD, large |

`process-brakewear` is the first rung of Phase 5 and the first fixture that
emits **more than one pollutant-process**: 250 rows of running-exhaust Total
Energy (`mixed-onroad`'s chain at a different hour), 250 of PM2.5 brake wear on
the same `BaseRateCalculator` spine, and 250 of PM10 brake wear *chained* off
the PM2.5 rows by a tabulated ratio. `docs/process-brakewear.md` is the
specification and `./run-brakewear-oracle.sh` the independent reproduction.

Eight fixtures have 0 output rows (`process-apu*`, `process-extended-idle*`,
`process-crankcase-extidle*`, `process-crankcase-start*`) — cheap structural
gates, not numerical ones. **The four `-single` variants are no longer among them as of 2026-10-19**: moves.rs recaptured them (`a75791bb`, local) with the hour, road types 1 and 4, the crankcase parents, and a county database that carries an age distribution, VMT and fuel supply, and they emit 91, 50, 300 and 684 rows (step 7f). The four default-scale twins followed on 2026-10-20 (moves.rs `dbda2695`, local): road type 1, the crankcase parents, source type 62 for crankcase extended idle and Total Energy beside `process-extended-idle`'s CO2, and they emit 91, 100, 300 and 684 rows (§7.3.42). Before that they were empty, for the reason below. **They are zero for one shared reason, measured:**
every onroad fixture selects `runspecroadtype = {4}`, and those four processes'
rates are emitted on road type 1, so `BaseRateCalculator`'s road-type join
discards them all (`docs/mixed-onroad.md` §0.2, `docs/evap-leaks.md` §0.3). The
same measurement rules out any start-exhaust (processID 2) target: not one of
the 39 snapshots contains a single process-2 output row.

Each snapshot carries **both sides** of the comparison: ~200 non-empty
`MOVESExecution` input tables *and* the expected `MOVESOutput`. No canonical
MOVES, MariaDB, or JVM is needed to develop against them.

**`chain-so2-co2e-mechanism` (5,534 rows) is not on the ladder above because it
did not exist when the ladder was written.** It was captured to reach the last
three unported calculators in one run — `SO2Calculator`,
`CO2AERunningStartExtendedIdleCalculator` and `TOGSpeciationCalculator` — and
landing it takes the calculator track to **19 of 19**; `docs/esm-conventions.md`
§40 is what it changed. It also retires two entries above it: `chain-nonhaptog`
and `chain-tog-speciation` were on the ladder as speciation-chain targets, and
the second of them does **not** exercise `TOGSpeciationCalculator` at all — its
`integratedSpeciesSet` is empty, and §40.5 says how that was found. Run
`tools/calculator-coverage.py --ladder` rather than reading this table for what
to do next; the generators are what is left.

---

## 3. Phases

### Phase 0 — Harness and the equi-join gate

Phase 0 is longer than a harness phase usually is, because the gate (§1.3) is
in it. That is deliberate: it is what lets every later phase be written in
relational form from the first line.

1. ~~**Build the equality-driven `join.on` gate**~~ — **done** (§1.3.2),
   EarthSciAST `28bda86ac`, specified as CONFORMANCE_SPEC §5.5.8. The critical
   path is clear.
2. **Build the CLI.** `cargo build --release --features esio,parallel` in
   `../EarthSciAST/pkg/earthsci-ast-rs`; copy to `./esm` (untracked, per
   CLAUDE.md). Record the EarthSciAST commit in a checked-in `esm-version.lock`
   so a fidelity result is attributable to a toolchain.
3. **Add a Parquet reader to EarthSciIO** (§1.4). Register `parquet` in
   `rust/src/format/`, following `netcdf.rs`, mapping Arrow columns to
   `NativeDataset`. Match it in the Python and Julia tracks so the decode
   contract stays cross-binding. It makes the `moves.rs` snapshots directly
   readable, deleting a conversion stage from every fixture.
4. **Close the array-output gap** (§1.5) — a CLI shim over
   `derive_output_plan`, so an emission field can be written and diffed.
   *Done.* Note for the fixture stage: `--format flat` is the old output
   byte-for-byte, so `grid` must be passed explicitly, and the emitted shape is
   field-for-field `earthsciio::format::OutputSchema` — pointing it at a Zarr
   sink later is a serializer swap, not a re-derivation.
5. **Take the `esm test` dependency**, don't duplicate it. Once it lands,
   component tests drop the `clock` state (§1.2).
6. **`run-tests.sh`** (checked in, kept current): `esm validate` every `.esm`,
   then `esm test` every `.esm`, then per-fixture end-to-end comparisons.
   Non-zero exit on any failure. *Done* — it degrades honestly meanwhile: a CLI
   build without a `test` subcommand reports skip with the reason, and an empty
   repo exits 0.
7. **`tolerance.toml`** — per-pollutant relative tolerance on `emissionQuant`
   sums with exact structural checks, mirroring the gate `moves.rs` actually
   runs rather than its byte-identity file (§1.6). *Done.*

Items 2–7 are independent of item 1 and proceed in parallel with it. Component
authoring (Phase 1, and the arithmetic of Phase 2) can also start against small
`const`-array inline tests before the gate lands — what waits on it is running
anything at fixture scale.

### Phase 1 — The representation spine — **done**

> **Status: landed.** The conventions below are written up, with their worked
> proof, in [`docs/esm-conventions.md`](docs/esm-conventions.md); `run-tests.sh`
> now checks the checkable ones mechanically
> (`tools/check-conventions.py`). Delivered: five template libraries in `lib/`,
> two micro-components in `components/`, a run-level assembly in `runs/`, the
> scaling gate in `gates/`, a source catalog in `sources/`, and six recorded
> upstream limitations with repros in
> [`docs/findings/`](docs/findings/README.md).
>
> **Three of the bullets below did not survive contact and are amended in the
> conventions doc, not here.** (1) The `subsystems` mount form breaks a leaf's
> `join.on`, so leaves mount as top-level `models` `{ref}` entries and index
> sets do *not* merge across the edge — finding F1/F2. (2) The explicit
> `skolem` value-invention ops do not evaluate; the canonical composite key is
> the multi-pair `join.on`, which §5.5.8 defines as that skolem tuple — finding
> F5. (3) A new rule the plan could not have known to ask for: an `aggregate`
> loop symbol named `t` makes a `join.on` match nothing, silently — finding F4.

Deliverable: `lib/` template libraries plus a written convention doc, proven on
one micro-component. No MOVES science yet. This phase exists because every
later phase inherits its decisions.

- **Tables stay tables.** A MOVES table becomes one column array per field over
  a row index set — the relation, not a reshaping of it. A reader comparing an
  `.esm` component against the SQL step table in the corresponding `moves.rs`
  calculator should see the same relations in the same order.
- **Every join is a `join.on`.** One key-pair list per join clause, naming the
  key columns. No hand-written equality `filter` standing in for a join: a
  `filter` carries a genuine predicate (a range test, a null guard), never an
  `ON` clause. This is the rule that keeps the documents legible, and it is
  checkable — a review can grep for equality filters between key columns.
- **`enums` for the literals** (`pollutant.NOx → 3`,
  `process.RunningExhaust → 1`), so no magic integers appear in expressions.
- **`skolem` for canonical composite keys** where a join is on a tuple rather
  than a column, and `coordinates` to record the original key so output rows
  label back to `countyID` / `SCC`.
- **Reused shapes as `expression_templates`** in library files imported by
  reference — the exhaust temperature adjustment
  `exp((T ≤ 75 ? a_cold : a_hot)·(T − 75))` (an *exponential*, not the quadratic
  an earlier draft of this plan called it), the I/M blend
  `max(rIM·f + r·(1−f), 0)`, unit conversion, the deterioration curve
  `1 + A·min(detage, cap)^B`. Each appears exactly once;
  `docs/nonroad-logging-county.md` §4 names eight with their exact forms.
- **One `.esm` per calculator/generator**, mounted into a run-level assembly via
  §4.7 subsystem refs. Index sets merge across the mount, so leaf components
  never redeclare shared axes.
- **Discrete time is an index-set axis.** MOVES time is a discrete
  `(year, month, day, hour)` key, *not* the domain's continuous `t`.
- **Scaling gate.** A checked-in test asserting a `join.on` contraction costs
  `O(matches)`, not `O(N·M)`, at fixture scale — so a regression in the gate,
  or a join that silently falls back to the filter path, is caught the day it
  appears.

### Phase 2 — First vertical slice: `nr-logging-county` (144 rows)

NONROAD first: self-contained (no 70-calculator chain), the smallest fixture,
and `moves.rs` documents its arithmetic as four named Fortran subroutines
rather than a SQL graph — `unitcf.f`, `emsadj.f`, `emfclc.f`, `clcems.f` →
`crates/moves-nonroad/src/emissions/exhaust.rs`.

Components, one `.esm` each, composed in order:

1. Geography and allocation (`geography/`, `allocation.rs`)
2. Population — base-year equipment population × growth × age distribution ×
   scrappage (`population/`)
3. Activity — annual hours, load factor, horsepower
4. Emission factors with deterioration (`emfclc.f`)
5. Adjustments — temperature, fuel, sulfur (`emsadj.f`)
6. Unit conversion (`unitcf.f`) and the exhaust roll-up (`clcems.f`)
7. Output aggregation to the `MOVESOutput` schema

The port specification for this fixture is written and verified:
`docs/nonroad-logging-county.md`. It carries the input inventory (21 of the
snapshot's 324 tables carry data; 11 more are declared by
`NonroadEmissionCalculator` and never read), the chain with source lines, 25
joins with exact key pairs, and a standalone script reproducing all 144 rows in
`float32` at 4.9 × 10⁻⁶.

**Three joins are not plain equi-joins** and need a precomputed key rather than
a `join.on` — the exceptions to the Phase 1 rule, worth knowing before
authoring: HP containment (`hpMin ≤ hpAvg ≤ hpMax`, both inclusive); the two
*different* SCC fallback ladders (rates/mixes/growth walk one, month/day
allocation another, and rates and mixes must walk theirs independently); and
state-default precedence (`stateID = 26` beats `stateID = 0`). Two further
joins are on *rounded* values — population quantized to 1 dp, `growthIndex`
truncated to integer — and the truncation decides the sign of near-zero growth
factors, so both must be modelled explicitly.

**Exit criterion:** all 144 rows match the snapshot within the recorded
tolerance, driven by `./run-tests.sh`. This phase proves the whole approach;
treat a slip here as a signal to revisit Phase 1, not to push on.

### Phase 3 — First onroad slice: `mixed-onroad` (250 rows)

The rates-first base-rate path, which is what the pinned MOVES runtime actually
registers (`CriteriaRunningCalculator` is superseded and registers nothing):
`TotalActivityGenerator` → `SourceBinDistributionGenerator` →
`OperatingModeDistribution` → `BaseRateGenerator` → `BaseRateCalculator`
(`crates/moves-calculators/src/calculators/baseratecalculator/`), then output
aggregation. The adjustment sequence — temperature, humidity, fuel effects,
I/M, A/C, activity weighting — is where the Phase 1 templates pay off.

**Status: complete.** The port specification is `docs/mixed-onroad.md`, written
to the method of its NONROAD companion: the input inventory from four
cross-checked sources, the eighteen-step chain with source lines, thirty-five
joins with their exact key pairs, four worked examples and an executable oracle
(`./run-onroad-oracle.sh`). Four components and an assembly cover S1–S12 and
S15–S18 with 296 assertions; `fixtures/mixed-onroad.esm` covers the whole chain
against the snapshot's own tables with 48 more.

**Measured, `fixtures/mixed-onroad.esm` against the snapshot's `MOVESOutput`:**
250 of 250 rows, key set exact (0 missing, 0 extra), worst cell **8.320 × 10⁻⁶**
against a 2 × 10⁻⁵ gate, worst per-pollutant sum 9.675 × 10⁻⁸ against 10⁻³.
`tolerance.toml` carries no `[shortfall]` record for it. `docs/esm-conventions.md`
§16 records what the onroad graph changed and §26 what the drive-cycle slice
changed.

**The relation that was not computed, and how the exit criterion was met.**
`W[hourDayID, opModeID]` — the speed-bin-weighted drive-cycle operating-mode
distribution, 46 numbers — is computed inside the MOVES worker and dropped, so
no captured table carries it, and `ratesopmodedistribution` covers only the
off-network road type and start exhaust. §7.3 isolated it by solving for it
(125 equations, 23 unknowns, residual 7.1 × 10⁻⁶ at the reference's own
six-significant-figure storage floor), which proved the base rate factorises
exactly around it and everything either side was right. It is computed now, from
`driveschedulesecond`'s 63,602 second-by-second speeds and
`sourceusetypephysicsmapping`'s road-load coefficients, in both the Python
oracle and the `.esm` fixture; `docs/mixed-onroad.md` §10 is the port.

**Three numbers from doing it.** Computing `W` instead of reading
`baserate_1_2020` moved the oracle's worst cell from 8.231 × 10⁻⁶ to
8.320 × 10⁻⁶ — nowhere — which is what §7.3's "the factorisation is exact"
looks like from the outside. The two independent routes agree cell by cell to
2.4 × 10⁻¹⁶, one ulp. And the four neighbouring-second self-joins that finding
**F11** used to refuse cost ~1.4 s together at 4.045 × 10⁹ candidate pairs each,
measured by bisection against the same document with them stubbed.

**Two things §8.1 predicted about the toolchain were wrong, and are corrected in
place.** The neighbouring-row reads are not F11's workaround — F11 is fixed
(EarthSciAST `107a15152`) and they are ordinary self-joins with `join.syms`. And
the mode classification is not F17's "big table meets big table" shape: it is an
ungated per-second contraction over 60 modes, and the F17 shape is one stage
later at the `emissionrate` lookup, where the remedy is one composite `on`
clause rather than six.

**§7.4's argument for not wiring a fixture is kept rather than deleted**, because
it was right for the state it described. A document emitting 250 correctly-keyed
rows with an uncomputed rate fails the per-cell gate for a shape `[shortfall]`'s
exact counts cannot express; one reading the reference's own `baserate_1_2020`
passes by transcribing the answer. The way out was to compute the missing
relation, not to widen anything.

That is one coherent piece of work, and it is not the only route into Phase 4.
An earlier version of this paragraph said Phase 4's cheapest slice is start
exhaust, "because its operating-mode distribution IS in the snapshot". **That
claim is wrong, and Phase 4 corrected it in place.** The premise is half true —
`ratesopmodedistribution` does carry polProcessID 9102 — but the conclusion does
not follow, because *no fixture in the suite has any start-exhaust output to
check against*. Measured over all 39 snapshots: `MOVESOutput` carries
**processID 2 rows in none of them**, and all 27 onroad fixtures select
`runspecroadtype = {4}` while `BaseRateGenerator` emits start, extended-idle,
APU and crankcase-start rates on road type 1, so `BaseRateCalculator`'s join to
`runSpecRoadType` discards every one of them — which §0.2 of
`docs/mixed-onroad.md` derives for `mixed-onroad`, and which holds suite-wide.
It is also why the eight zero-output-row fixtures are zero. A start-exhaust
slice would therefore be the *most* expensive kind available: unvalidatable.
See `docs/evap-leaks.md` §0.3 for the measurement, and Phase 4 below for the
slice that was taken instead.

### Phase 4 — Broaden by process

One new leaf component per process, each reusing the spine: evap (permeation /
leaks / FVV, 128 rows each), refueling (336), brake and tire wear (750 each),
crankcase (1,368), PM exhaust (1,456), the TOG/NonHAPTOG speciation chains
(1,080), air toxics (1,288). The zero-row idle/APU fixtures come along as
structural gates — see the note in §2 for the one join that makes all eight of
them zero.

**The first slice is `process-evap-leaks` (128 rows), and it was chosen by
measurement rather than by size.** `docs/evap-leaks.md` §0.3 records the
selection. Of the candidate onroad processes, most need the drive-cycle
operating-mode distribution `W` that Phase 3 §8.1 blocks — every fixture that
emits processID 1 rows (brake wear, tire wear, PM exhaust, crankcase running,
the speciation chains, air toxics), plus refueling, which chains off
`BaseRateCalculator`'s total-energy output. Of the three 128-row evap fixtures,
FVV (process 12) needs the multi-day tank-vapour soak-day recurrence that
finding F12 blocked, and permeation (process 11) needs
`AverageTankTemperature`, which is the output of `TankTemperatureGenerator`'s
quarter-hour recurrence — F12 again.

**F12 is now fixed (EarthSciAST `a83cde55e`).** A recurrence over an index axis
has a spelling — an `aggregate` body reading `index(V, k − c)` where `V` is the
equation's own left-hand side — with an arbitrary bounded lag, a normative
arithmetic order, and per-cell rounding to the variable's `element_type`.

**An earlier version of this paragraph then said FVV and permeation were
therefore unblocked. That is half right, and the half that is wrong was
measured rather than argued.** F12's fix does unblock the recurrence PLAN.md
named: `TankTemperatureGenerator` TTG-1b, the quarter-hour cold-soak tank
temperature, is computed in `components/tank_temperature.esm` and checked
against three captured MOVES intermediates — 96 `QuarterHourTemperature` rows,
96 `QuarterHourTankTemperature` rows and all 24 `ColdSoakTankTemperature` rows,
64 assertions, worst 7.550e-07 against the reference's own six-significant-figure
storage. It took the construct unchanged on a recurrence unlike the fold in four
ways at once (`docs/esm-conventions.md` §20.1), which is exactly the
verification-breadth argument below and it succeeded.

What F12's fix does **not** unblock is what the two fixtures actually stand on.

* **`process-evap-permeation` cannot see the recurrence at all.** Its
  `opModeFraction` for the cold-soaking mode is exactly 0, so
  `AverageTankTemperature` mode 151 — the quarter-hour recurrence's output — is
  multiplied by zero: perturbing it by +50 °F leaves all 128 cells *unchanged*,
  while the same perturbation of mode 300 moves the total from 32.26 g to 221.12
  g (`docs/evap-permeation.md` §0.3, measured on the oracle). Mode 300 is
  TTG-4a's walk over `SampleVehicleTrip`, whose predecessor is named by
  `priorTripID`, a data column — **and this bullet used to attribute that to
  finding F28, which is wrong.** On the relation TTG-4a walks, after
  `flagMarkerTrips` deletes the 5,458 marker trips, the predecessor is one row
  back on all 26,193 chained rows; the gaps of 2…7 are gaps in the *identifier*.
  What TTG-2/3/4 actually need is a relation whose row count is a function of
  the data (F5 and F14, both now retired) — priced in `docs/evap-permeation.md`
  §8.1 and generalised in `docs/esm-conventions.md` §34.3. **The fixture is
  landed** and reads `AverageTankTemperature` as a scope decision, not as a
  blocked step.
* **`process-evap-fvv` can**, and is therefore the better next slice rather than
  the equal one: `MultidayTankVaporVentingCalculator` TVV-3 reads
  `ColdSoakTankTemperature` directly. It needs, in addition, TTG-7's
  `ColdSoakInitialHourFraction` (F28 again), `TankFuelGenerator`'s
  `AverageTankGasoline` (captured *empty* in all three evaporative snapshots, so
  it must be computed), and the largest calculator SQL file in MOVES.
  `docs/evap-permeation.md` §8.2 carries the bill.

The screening was not wrong about F12; it was incomplete about what was behind
it. `docs/evap-permeation.md` is the specification, `./run-permeation-oracle.sh`
reproduces all 128 rows at 6.174e-06 with an exact key set — reading 192 of 288
`AverageTankTemperature` cells and nothing else — and the recurrence-breadth
question this pair was opened to answer is **answered**, by
`components/tank_temperature.esm` rather than by either fixture.

**Evap fuel leaks (process 13) needs neither.** Its base rate is
`emissionRateByAge`, a default-database input table, so it replaces exactly the
one relation Phase 3 could not compute; and its operating-mode distribution
comes out of the evap generator as `{opMode 300: 1}` because
`fractionOfOperating = least(1, ΣSHO / ΣsourceHours)` is exactly 1 at an
on-network link, which multiplies the F12-blocked soak activity fractions by a
*computed* zero rather than an assumed one.

So the leaks slice is also the slice that makes Phase 3's activity and cohort
spine checkable end to end: `./run-leaks-oracle.sh` reproduces all 82 rows of
`SHO`, all 82 of `SourceHours`, all 125 of the fuel-usage source-bin
distribution, all 6 of the evap operating-mode distribution and all 128 of
`MOVESOutput` from the snapshot's own input tables, reading **nothing** from the
reference — which `./run-onroad-oracle.sh` cannot do.

**Status: specified, built and WIRED.** `docs/evap-leaks.md` is the port
specification — 37 input tables from cross-checked sources, nineteen numbered
steps, twenty-two joins with their exact key pairs, four worked examples and the
oracle. `lib/evaporative.esm` and three components cover E1–E3, L8 and
L1/L9/O1–O3 with 81 inline assertions; `runs/evap_leaks_run.esm` mounts them and
adds the joins that exist only between them, running 107 assertions in total.
`docs/esm-conventions.md` §18 records what the evaporative graph changed: every
rule in §1–§17 held, four gained a reason, five things are new, and one new
finding (**F21**, a scoped name is not an assertable variable — fixed upstream
2026-09-16 and retired) came out of the assembly.

And `fixtures/process-evap-leaks.esm` **matches completely** — 128 of 128 rows,
an exact key set, worst cell 7.294 × 10⁻⁶ against `tolerance.toml`'s 2 × 10⁻⁵,
worst per-pollutant sum 5.161 × 10⁻⁷ against 10⁻³, with no `[shortfall]` and
nothing read from the reference. It is the first full match in this repository.
The oracle reports the same worst cell to the digit from the same tables by a
different route. Two things had to be got right that are not about inputs and
that Phase 5 will meet again: L8 is a **two**-relation contraction with the
operating mode on its own axis, because the five-relation form does not finish
(F17 at fixture scale, measured at >120 s against 25 s for two two-relation
joins at the same scale); and a derived relation's axis is a *metaparameter
expression over discovered extents*, so only the output axis's 64 surviving
cohorts is declared — checked in-document against a count the chain computes.

### Phase 5 — Scale out

Remaining NONROAD sectors (mostly the Phase 2 components against different
sector data) and the `expand-*` dimension fixtures (multi-county, multi-month,
multi-year, road types, fuel types). This is where the §1.3 gate gets
stress-tested — the first place where a join's match count, not its index-set
product, becomes the number that matters.

**Two of Phase 5's rungs have no row in §2's ladder, and that is not an
oversight.** `MeteorologyGenerator` (rung 9) and `FuelEffectsGenerator` (rung
11) are GENERATORS: their product is an execution-database column or table, not
a `MOVESOutput` row, so a snapshot row count says nothing about them and
`fixtures/` is the wrong home (`docs/esm-conventions.md` §35.1). Their sizes are
532 `ZoneMonthHour` rows / 1,596 cells and 97 `generalFuelRatio` rows / 194
cells, over the whole corpus rather than over one snapshot, and each is verified
by an oracle handed the snapshots *directory*. §35.2 and §38 are the rules that
came out of the pair.

### Phase 6 — Control strategies

AVFT, Rate-of-Progress, OnRoad/NonRoad retrofit, LEV
(`moves.rs/docs/control-strategies.md`). Deferred deliberately: none of the 39
fixtures exercises them, so this is scope beyond reproducing the examples.

---

## 4. Testing and analyses

- **Unit level — inline `tests`.** Each component `.esm` carries tests with
  small `const`-array inputs and hand-computable expected values, exactly like
  the probes in §1. Fast, portable across all five bindings, no data
  dependency, and — with the new `esm test` — no ODE solve. Note the
  constraint: on a component with array-shaped variables, every assertion
  selects a scalar via `coords` or `reduce` (esm-spec §6.6.5), so these are
  reductions and point samples, not row dumps.
- **Fixture level.** A per-fixture assembly `.esm` whose `data_sources` read
  the snapshot Parquet directly (§1.4). Its inline tests assert reductions —
  total mass per pollutant, max cell — against the snapshot. The full
  row-by-row diff runs in `run-tests.sh`, which needs the array-output gap
  closed.
- **Analyses.** `analyses` sections with `plots` for illustrative runs —
  emissions by hour, a sweep over temperature or fuel sulfur — mirroring what
  `moves.rs`'s `docs/downstream-tools.md` walks through.

Which tables a fixture needs is not guesswork: each `moves.rs` calculator
declares its `INPUT_TABLES`, and each snapshot ships an `execution-trace.json`
listing the SQL files and Java classes that fixture actually touched.

Every `.esm` in this repo is hand-authored — no `.esm` is generated by script,
per CLAUDE.md.

---

## 5. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **The equi-join gate (§1.3) is now the critical path.** Nothing runs at fixture scale until it lands | High | Both halves exist (`overlap`'s enumeration-driving gate, `relational.rs`'s hash-bucketed kernel), so this is connection work, not invention. Phase 1 and the Phase 2 arithmetic proceed against small `const`-array tests meanwhile. If it stalls, a local EarthSciAST branch unblocks; do **not** fall back to dense reshaping — that is the legibility this plan is buying |
| Cross-binding determinism on the new gate | Medium | §5.7 rule 5 already fixes the answer: hashing buckets only, results emitted sorted by canonical key. Land Julia and Python conformance fixtures with the Rust implementation, not after |
| f32/associativity fidelity on NONROAD (§1.6) | Medium | Tolerance gates recorded per column; document the divergence class rather than chase bits |
| Memory — a 600k-cell probe used ~236 MB across 95 output points | Medium | Limit output points; MOVES needs one evaluation, not a trajectory |
| Other upstream dependencies: Parquet reader, array output, `esm test` | Medium | All three are thin additions over existing structure and run in parallel with the gate |
| Scope: 39 fixtures over ~70 onroad calculators and a 29k-line Fortran rewrite | High | The ladder delivers a working, tested end-to-end path at Phase 2 and stays green after every later phase |
| **This toolchain's characteristic failure is returning `0`, not raising** | High | Four independent instances found in one day, all silent, all a plausible zero on a document that validates: (a) a `data_sources` entry read by no provider; (b) the same when the registry `earthsciio` shadows the local checkout; (c) F4, an `aggregate` range symbol named `t`; (d) F5, `skolem`/`distinct`/`rank` validating but materializing empty. Zero is the worst possible sentinel here — it is a *legal* emission quantity, it flows through sums without a NaN to trace, and a per-pollutant tolerance absorbs it. Mitigation is structural, not vigilance: every inline test asserts a specific non-zero expected value rather than a bound; `run-oracle.sh` gives an independent third implementation to attribute a disagreement to; and `compare-output.py`'s exact key set catches the row-shaped version. Assume the next one exists and has not been found yet |

---

## 6. Immediate next steps

Phases 0, 1, 2 and 3 are done and merged, and Phase 4 has two of its slices
wired, and Phase 5's rungs are landing. **All fifteen** fixtures match the
reference completely, with an exact key set and no `[shortfall]`.

The table below is read off one `./run-tests.sh` run rather than accumulated
commit by commit, and it had to be, because the `moves-snapshot/v2` day
correction halved twelve of these row counts and the accumulated version still
carried the pre-correction ones (`mixed-onroad` 250, `process-brakewear` 750,
`process-refueling` 336, `process-pm-exhaust` 1,456 — all of them the two-day
figures for one-day runs). A count assembled from memory cannot be told from a
stale one; `tools/calculator-coverage.py` exists for that reason and this table
now follows the same rule.

| fixture | rows | worst cell | phase |
|---|---:|---|---|
| `nr-logging-county` | 144 / 144 | 4.561e-06 | 2 |
| `mixed-onroad` | 125 / 125 | 8.319e-06 | 3 |
| `process-evap-leaks` | 64 / 64 | 7.294e-06 | 4 |
| `process-evap-fvv` | 64 / 64 | 7.517e-06 | 4 |
| `process-evap-permeation` | 64 / 64 | 6.174e-06 | 4 |
| `process-brakewear` | 375 / 375 | 8.251e-06 | 5 |
| `process-tirewear` | 375 / 375 | 8.128e-06 | 5 |
| `process-refueling` | 168 / 168 | 6.981e-06 | 5 |
| `process-airtoxics` | 644 / 644 | 7.564e-06 | 5 |
| `process-crankcase-running` | 684 / 684 | 7.805e-06 | 5 |
| `process-nox-speciation` | 436 / 436 | 9.485e-06 | 5 |
| `process-pm-exhaust` | 728 / 728 | 7.516e-06 | 5 |
| `chain-so2-co2e-mechanism` | 2,767 / 2,767 | 8.201e-06 | 5 |
| `nr-airtoxics-lawn-garden-county` | 14,036 / 14,036 | 9.417e-06 | 5 |
| **`expand-day`** | **250 / 250** | **7.106e-06** | 5 |

all against `tolerance.toml`'s 2e-05, which has never been widened for any of
them.

`expand-day` is the last of the fifteen and is the only one that is not about a
new calculator: it is `mixed-onroad`'s chain at hour 7 over BOTH day types, and
it exists to restore the two-day coverage the RunSpec correction removed from
the other fourteen (`docs/esm-conventions.md` §42.5, §43). Measured: the two
day-collapsing perturbations that turn 6 and 18 of its 109 assertions red turn
**none** of `mixed-onroad`'s 59 red, and the day-collapsed `mixed-onroad` still
passes the comparator at its usual worst cell. What follows is ordered by what
blocks what.

1. **Scale out (Phase 5).** This is now the main line, and three rungs are
   landed. The first: `fixtures/process-brakewear.esm` matches all 750 rows with an
   exact key set, worst cell 8.250e-06, no `[shortfall]` and nothing read from
   the reference. Three things came out of it that the remaining rungs inherit.

   * **A rate relation, not a wider cohort relation.** A run emitting several
     pollutant-processes cannot key its rate columns on the cohort alone,
     because `shortModYrGroupID` — one of the six components packed into
     `emissionrate.sourceBinID` — differs between them: 9101 resolves model year
     2020 to short group 40 and 11609 to 6. A `join.on` key column must be
     one-dimensional, so the rate stage rides a flat
     `rate_rows = polProcess x cohort` relation (`docs/esm-conventions.md` §2).
     Every later multi-pollutant fixture — the speciation chains, air toxics,
     PM exhaust — meets this on its first line.
   * **A chained pollutant is a self-join, not a second rate.** `runspecchainedto`
     and `pm10emissionratio` carry the whole of `PM10BrakeTireCalculator`; the
     chained block's own rate path evaluates to exactly 0 because
     `emissionrate` has no 10609 row. The same expression serves chained and
     unchained blocks with no branch, because the chain key and the ratio are
     both 0 on an unchained row.
   * **A latent defect in `mixed-onroad`, found by moving one hour.** The
     temperature-adjustment lookup has a `regClassID 0` wildcard step that
     `fixtures/mixed-onroad.esm` did not implement; at 66.9 °F the clamp hid it,
     at 59.5 °F it is a 1.56 % error on 84 rows. Fixed in both fixtures via a
     new `lib/adjustments.esm` template, with `mixed-onroad`'s 250 numbers
     unchanged to the last digit. **Retargeting an existing fixture onto a
     neighbouring snapshot is a cheap and effective audit** and should be the
     first move on every later rung.

   **`process-tirewear` is the second rung and is landed**: 750 / 750, exact key
   set, worst cell 8.151e-06, no `[shortfall]`, nothing read from the reference,
   and the same worst cell at the same key from the independent reproduction in
   `docs/process-tirewear.md` §6.5. It inherits all three of the above and adds
   one. **The `BaseRateCalculator` spine is shared but the operating-mode
   distribution is not.** Tire wear's rates live on modes 400–416, binned on
   average speed alone and written by a second generator
   (`AverageSpeedOperatingModeDistributionGenerator`, process 10) rather than by
   the drive cycles, so `W` acquires a pollutant-process axis. Retargeting
   `process-brakewear` onto that snapshot reproduced its 250 energy rows at
   7.106e-06 and returned *exactly 0* on all 500 particulate rows: the audit
   found no defect — this snapshot's scope is `process-brakewear`'s to the row,
   so it could not — but it named the work in one measurement.
   `docs/esm-conventions.md` §28 and `docs/process-tirewear.md` §2.3.

   The rest of the phase is unblocked for the same reason it was:
   `W` was the last uncomputed relation, so every fixture that emits processID 1
   — brake wear, tire wear, PM exhaust, crankcase running, both speciation
   chains, air toxics — can be attempted against a spine that is checked end to
   end. §2's ladder is the order; the 744–1,456-row band is the next rung and
   the 15,801–23,108-row NONROAD fixtures are where §1.3's gate stops being
   theoretical.

   **`process-refueling` is the third rung and it is landed**: 336 of 336 rows,
   key set exact, worst cell 7.434e-06. It is the first fixture whose calculator
   does not compute a rate on the running-exhaust spine at all —
   `RefuelingLossCalculator` chains off `BaseRateCalculator`'s **total-energy
   output** and uses it as ACTIVITY, converting energy to fuel volume through the
   fuel's energy content and density. Three things it adds are in
   `docs/esm-conventions.md` §29: an energy output consumed in kilojoules
   *before* the output processor's unit rebase; a rank that runs across the whole
   rate relation because the two emitted blocks are different sizes (64 cohorts
   and 104); and a NULL-bearing input column that has to be guarded with a VALUE
   rather than an indicator, because `0 × NaN` is NaN.
   `docs/process-refueling.md` is the specification and
   `./run-refueling-oracle.sh` the independent reproduction.
2. **F33 — a `Float32` document is evaluated in binary64 by Julia and Python,
   silently.** Not a new contract and not a new observation: `CONFORMANCE_SPEC`
   §5.18 is normative, §5.18.2 closes by naming this exact failure ("a binding
   that cannot honour a clause MUST refuse it"), and upstream's PREC-11-A
   binding status already records the gap and what closing it would take. Julia implements the refusal for time integration
   and not for the algebraic and relational path §5.18.2(3) explicitly says
   still runs in binary32; `element_type` is read nowhere in its evaluator, and
   Python reads it at one site. Measured on a two-clause `Float32` document with
   integer keys straddling a binary32 collision: Rust answers 8, Julia and
   Python answer 4. Three executing bindings, two answers, no diagnostic. It
   does not block this port — Rust is the binding this repository runs — but it
   means a cross-binding fidelity claim cannot be made for any float32 document
   here, which is all of the NONROAD side.
3. **F28 — a data-named predecessor is not a recurrence.** Real, correct
   behaviour, with a repro and a passing workaround control — but **no
   confirmed call site in MOVES**, and this item used to name
   `process-evap-permeation` as one. Measured: TTG-4a's predecessor is one row
   back on the relation the recurrence walks (`docs/findings/README.md` F28,
   `docs/esm-conventions.md` §34.3). `process-evap-permeation` is landed —
   fixture, oracle and specification — at 128 rows and 6.174e-06.
4. **An off-network snapshot**, without which the evaporative soak chain cannot
   be checked anywhere. Three consecutive slices failed to reach it for one
   structural reason — `fractionOfOperating` is identically 1 at an on-network
   link, and all 39 snapshots select road type 4 — so this needs a RunSpec on
   road type 1 generated in `moves.rs`, not another slice here. See
   `docs/evap-fvv.md` §8.3 and `docs/esm-conventions.md` §23.

Phase 6 (control strategies) stays deferred: none of the 39 fixtures exercises
them, so it is scope beyond reproducing the examples.

### 6.1 What the fidelity gate now consists of

Three checked-in pieces, all green:

- `compare-output.py` — the row-by-row diff, with a falsification suite the
  harness runs *before* trusting it. Verified by sabotaging each gate in turn
  and confirming the suite goes red.
- `run-oracle.sh` — extracts and runs the independent float32 reproduction that
  lives in `docs/nonroad-logging-county.md` §6.5, so the specification stays
  executable and there is a third implementation to attribute disagreements to.
  Reproduces all 144 rows at 4.897e-6.
- `tolerance.toml` — the contract, with the reasoning next to the numbers.

Two further audits are checked in but deliberately **outside** `run-tests.sh`,
because they perturb the working tree in place and a hard kill would leave it
perturbed. They have to be run by hand, so the record of when they last ran
names the commit — a claim of "the audit is green" with no revision attached
rots exactly the way the coverage figure did:

| audit | last run | result |
|---|---|---|
| `tools/perturbation-audit.py fixtures` | `d866a8d` (rung 6) | 1,721 assertions perturbed, **1,721 red, 0 pass** — 1,459 non-zero nudged multiplicatively, 262 exactly-zero nudged additively. None is decoration. |
| `tools/clause-order-audit.py` | `d866a8d` (rung 6) | 45 documents, 10 runnable; **191 clause lists and 589 `on` lists reordered** under five modes (reverse, rotate, three shuffles), every relation byte-identical and no test row moved. |

The clause-order figures are the ones to watch: they were 162 clause lists and
363 `on` lists at seven fixtures, so rungs 4–6 added 29 clause lists and 226
`on` pairs and every one of them is order-independent. That gate is proven
two-sided — run against the pre-F17 binary it fails at exactly 32 of 144 rows,
first cell 1.7840874195098877 → 2.2641310691833496.

The layered gates are not belt-and-braces. Measured by perturbing the real
snapshot: dropping the four rows a Fortran-faithful `modfrc <= 0` skip would
suppress leaves per-pollutant sums agreeing to **1.2e-8**, four orders inside
the 1e-2 gate; zeroing those same four cells does too; and moving mass between
model years leaves them agreeing to **2e-16** by construction. The loose
per-pollutant gate `moves.rs` uses across implementations would pass every
realistic failure this port can produce. Only the exact key set and the
per-cell check see them.

### 6.2 How much of MOVES this is

Run `tools/calculator-coverage.py`. The number is not recorded here, because a
number recorded here is a number that stops being true the next time a rung
lands and gives no sign of it. What is recorded is where it comes from:

- **The denominator** is `../moves.rs/characterization/calculator-chains/calculator-dag.json`,
  built by `moves-calculator-info` from the pinned MOVES `CalculatorInfo.txt`
  and a scan of 62 Java files. 65 modules, of which **32 are live** — 19
  calculators and 13 generators.

  The liveness rule differs by kind, because the evidence does. A calculator
  is live iff it registers at least one `(pollutant, process)` pair;
  registration is what MOVES consults to decide whether a calculator
  contributes at all. Subscription is *not* sufficient, and reading it as
  sufficient is the trap: **twelve** calculators subscribe to the master loop,
  register nothing, are chained from nothing and have no dependents — the
  classes `BaseRateCalculator`'s rates-first approach superseded, left in the
  tree with their `Subscribe` directive intact. `docs/process-brakewear.md`
  §8 already says this of `BasicBrakeWearPMEmissionCalculator`. Counting them
  would put twelve modules in the denominator that no fixture can ever
  exercise, because MOVES never calls them. A further seven neither subscribe
  nor register — an abstract base, the well-to-pump pair, and the PM crankcase
  variant `SulfatePMCalculator` displaced. The tool prints both lists, split
  by reason, so the exclusion is auditable rather than buried in a predicate.

  A generator registers nothing by nature, so for generators subscription and
  being chained from something are the evidence. Most modules of kind
  `Unknown` are excluded — `MasterLoopTest` is a test harness and the eight
  control strategies are RunSpec-driven rather than master-loop modules — but
  **`ProjectTAG` is not one of them, and this section used to say it was.**
  It read "`ProjectTAG` is project-scale tagging". **TAG is Total Activity
  Generator**: `ProjectTAG.java` is the PROJECT-domain counterpart of
  `TotalActivityGenerator`, computing SHO, SHP, Starts and extended-idle
  activity from link volumes and `offNetworkLink` (`:388-476`); it is on
  canonical MOVES's `DO_RATES_FIRST` whitelist (`MOVESInstantiator.java:1465`);
  and `scale-project` class-loads it. Its `kind: "Unknown"` is an artifact of
  the DAG builder classifying by class-name suffix. It is a live generator and
  is now counted as one.

  **Two further exclusions**, both of them modules MOVES does not run and
  neither of which existed as a category before Phase 5's last rung. The three
  generators `MOVESInstantiator.java:1449` discards under `DO_RATES_FIRST`
  (`OperatingModeDistributionGenerator` and both `MesoscaleLookup` ones) are
  out, because no RunSpec in any domain can instantiate them while that flag
  is `true`. `NewTvvYearGenerator` is out because there is no such class: it
  is a named SQL section of `MultidayTankVaporVentingCalculator.sql`, and the
  tool detects it derivably as "empty `java_path`, zero registrations, chained
  from nothing" rather than by name. `docs/omd-generator-reachability.md` and
  `docs/new-tvv-year.md` are the evidence for both, and the second is an
  oracle rather than a paragraph.
- **The numerator** is the `| Calculator path |` row each specification in
  `docs/` already carries. The spec's own claim, in the spec, moving in the
  same commit as the work.
- **The evidence** is the oracle. A claim counts only when an oracle names that
  spec, `run-tests.sh` runs that oracle, and a fixture in `fixtures/` names the
  same snapshot. `docs/evap-permeation.md` was the case that made this worth
  enforcing: the specification and `./run-permeation-oracle.sh` were complete
  for months while the fixture was not, so the tool reported
  `EvaporativePermeationCalculator` as **claimed and not counted**. A
  specification is not a port — and the row is what got the fixture written.
  It now counts, and `NOT COUNTED (no fixture)` appears nowhere in the table.

`run-tests.sh` gates this: a spec may not name a module MOVES does not have,
nor claim one the DAG records as dead, nor declare a calculator path without
the snapshot row that says what the claim is about. Those are the three ways
the figure could quietly start lying.

`--ladder` answers the other recurring question — which snapshot to port next —
from the same data. Rung order had been chosen from memory, and it went wrong
twice in one afternoon: once naming a superseded class as the prize, once
crediting NONROAD calculators to ONROAD snapshots because registration is
model-blind. Two rules make it measured instead:

- **The pairs come from the OUTPUT, not the RunSpec.** A RunSpec selects
  pollutant-process pairs; it does not promise MOVES emitted rows for them.
  `process-refueling`, `process-evap-leaks` and `process-evap-fvv` all select
  pollutant 86, for which `HCSpeciationCalculator` is registered, and **not one
  of them has a single output row for it**. Read from the RunSpec, all three
  look like they would unlock that calculator; read from the output, it
  contributed nothing — which is also why those three fixtures match every row
  without implementing it.
- **Eight snapshots emitted no rows at all** (all eight were recaptured non-empty, the `-single` variants on 2026-10-19 and the default-scale four on 2026-10-20; see step 7f and §7.3.42) — `process-extended-idle`,
  `process-apu`, `process-crankcase-start`, `process-crankcase-extidle` and
  each one's `-single` variant — with `MOVESOutput` *and* `MOVESWorkerOutput`
  both empty. They are structural gates over the run scope, not verification
  rungs: a fixture cannot be checked against no rows. Reading the output
  disposes of them without a special case.

**The next four rungs inherit a proven key set.** Measured against
`MOVESOutput` after rung 4 landed: `process-airtoxics`,
`chain-tog-speciation`, `chain-nonhaptog` and `process-pm-exhaust` all use
**exactly** the cohort sets `process-nox-speciation` established — the same 124
parent cohorts × 2 day types (248 rows) and the same 104 species cohorts × 2
(208 rows), set-equal, not merely equinumerous. So the expensive half of rung 4
is done for all of them, and what is left per rung is that snapshot's own ratio
table and its parent's chemistry.

**But the KEY the row set turns on is not inherited with it, and rung 7 found
that out the hard way.** This paragraph used to add that
"`emissionratebyage`'s `ageGroupID` row-set behaviour, including model year 2000
electricity being absent from the parent while 2001–2020 are present at exactly
zero, is the same in each". The row set is the same; the *mechanism* is not.
`process-nox-speciation` and `process-airtoxics` lose (model year 2000,
electricity) on the **age group** — pollutant 101's fuel-type-9 rows stop at
group 1519 and that cohort is aged 20. `process-pm-exhaust` carries **all seven
age groups for fuel type 9** and loses the same cohort on the **short
model-year group**: its fuel-9 source bins have no shortModYrGroupID 20, which
is the group model year 2000 maps to. Every numeric gate passes either way, so
the wrong reason for a right number survives indefinitely — which is
`tools/check-sources.py`'s lesson applied to a plan rather than to a note.
`docs/esm-conventions.md` §33.7 is the rule that came out of it and
`run-pm-exhaust-oracle.sh` asserts all three halves of the measurement.

Two consequences for ordering. `process-airtoxics` (1,288 rows = 248 + 5 × 208)
is *structurally the rung just landed* with a THC parent instead of NOx, which
makes it cheaper than its row count suggests. And `chain-tog-speciation` and
`chain-nonhaptog` have **identical** pollutant-process composition — 1,080 rows
each over pollutants 1, 5, 79, 80 and 86 on process 1 — so they are one piece of
work that cross-checks itself, not two rungs — though the paragraph below
records the further fact, measured after rung 6 landed, that neither of them
unlocks a calculator at all. `process-pm-exhaust` is the odd
one: seven 208-row blocks and **no** 248-row parent, so nothing in it is
unchained.

**Five live calculators no snapshot in the corpus exercises**, measured by
`tools/calculator-coverage.py --ladder` at rung 6:

| calculator | registrations | what it owns |
| --- | --- | --- |
| `NRAirToxicsCalculator` | 205 | NONROAD air toxics |
| `TOGSpeciationCalculator` | 184 | pollutant 88 and the 1000-series species |
| `NRHCSpeciationCalculator` | 45 | NONROAD HC speciation |
| `CO2AERunningStartExtendedIdleCalculator` | 8 | off-network CO2 |
| `SO2Calculator` | 4 | SO2 |

Each is the same shape of gap as the missing off-network snapshot in item 4
above: it needs a RunSpec generated in `moves.rs`, not a fixture here. Two of
them are the NONROAD pair, so a single nonroad RunSpec selecting air toxics
pays +2.

`TOGSpeciationCalculator` is worth naming separately, because the corpus has
two snapshots that *sound* like they reach it and do not.
`chain-tog-speciation` and `chain-nonhaptog` emit 1,080 rows each over
pollutants 1, 5, 79, 80 and 86 — and `TOGSpeciationCalculator` registers
none of those. It owns pollutant 88 and the 1000-series. Both snapshots unlock
**+0**: every calculator they touch is already covered by rung 6. They are axis
tests, not rungs, and the ladder classifies them that way on the output rows
rather than on their names.

---

### Phase 5, continued — the operating-mode-distribution generators, and what the family measurement found

**Two of seven generators in this family were reachable from the corpus when
this rung was planned, and the reason given for the other five turned out to
be wrong for four of them.** The table below is as it stood then, over the 42
snapshots that carried an `execution-trace.json`:

| generator | class-loaded in | emits rows in | reachable? |
|---|---:|---:|---|
| `RatesOperatingModeDistributionGenerator` | 30 / 42 | 5 | **yes** |
| `StartOperatingModeDistributionGenerator` | 9 / 42 | 9 | **yes** |
| `OperatingModeDistributionGenerator` | 0 / 42 | 0 | no |
| `LinkOperatingModeDistributionGenerator` | 0 / 42 | 0 | no |
| `MesoscaleLookupOperatingModeDistributionGenerator` | 0 / 42 | 0 | no |
| `MesoscaleLookupTotalActivityGenerator` | 0 / 42 | 0 | no |
| `NewTvvYearGenerator` | 0 / 42 | 0 | no |

The reason recorded for all five was "these need a RunSpec that selects a
different **domain** — project scale or mesoscale lookup". `moves.rs` then
captured `scale-project`, and **exactly one of the five moved**. The other
four never will: three are discarded by `MOVESInstantiator.java:1449` under
`DO_RATES_FIRST` and the fourth is not a class. Both are argued in
`docs/omd-generator-reachability.md`, and the fourth is proved by
`./run-new-tvv-year-oracle.sh` over a snapshot that has been in the corpus
since Phase 0.

That is the correction worth carrying forward: **"no RunSpec selects that
domain" and "MOVES never instantiates it" look identical from the corpus and
are not the same claim**, and only the first is fixable by capturing more.

**The 30-versus-5 line in that table is the point.** `RatesOMDG` is loaded in
30 snapshots and emits in five, because all four of its live statements are
pinned to source type 62. Class-loaded and produced-output are different
events, and a rung planned on the first number would be planned on a number
five times too large. `docs/esm-conventions.md` §39.3 is the rule.

**What landed.** `docs/operating-mode-distribution.md`, `run-omd-oracle.sh`,
`lib/operating_mode.esm`, `components/start_operating_mode_distribution.esm`
(27 assertions) and `components/rates_operating_mode_distribution.esm` (21).
Coverage moved from 24 of 35 live modules to **26 of 35**; generators from 8
of 16 to **10 of 16**. *(Those are the denominators as they stood at that
rung. The last rung of Phase 5 changed them — see below — so re-run
`tools/calculator-coverage.py` rather than reading either figure forward.)*

**What it left for the next rung.** The specification's §5 records that
`moves.rs`'s `StartOperatingModeDistributionGenerator` models step 400 as a
copy of the soak-time fractions, when MOVES's non-project rates branch reads
`startsOpModeDistribution` instead and carries a `polProcessID` that port's row
struct does not have. That is a defect in the reference, not in this port, and
it is upstream work.

---

### Phase 5, last rung — the generators nothing could reach, and the one a capture reached

**Five generators were carried as "unreachable, needs a domain the corpus does
not have". A capture reached one, and dissolved the reason given for the other
four.** `docs/omd-generator-reachability.md` is the measurement and
`docs/esm-conventions.md` §45 is the rule.

**What `moves.rs` had to do first.** `scale-project` — a PROJECT-domain RunSpec
over one 1-mile urban-restricted-access link in Washtenaw County — needed a
scale-input database that did not exist. It is
`../moves.rs/characterization/county-inputs/washtenaw-project/setup-project.sql`,
built entirely with `CREATE TABLE ... LIKE` and `INSERT ... SELECT` against the
default database, with exactly **three invented rows** (`link`,
`linkSourceTypeHour`, `offNetworkLink`), each carrying an inline note on why the
default database cannot supply it. `OpModeDistribution` and
`driveScheduleSecondLink` are created **empty on purpose**, which is what makes
the generator compute a distribution instead of echoing a user-supplied one.
The capture is 360 tables, `moves-snapshot/v2`.

**What that bought, measured.** `OpModeDistribution` is present in all 43 of the
older snapshots and **empty in all 43**. `scale-project` carries **122 rows,
`isUserInput='N'` on every one** — the first and only evidence in the corpus
for `LinkOperatingModeDistributionGenerator`, and for `ProjectTAG`, which the
same snapshot class-loads and nothing else does.

| generator | was | is | why |
|---|---|---|---|
| `LinkOperatingModeDistributionGenerator` | unreachable | **reached, specified, oracled** | `scale-project` |
| `OperatingModeDistributionGenerator` | unreachable | **dead code** | `MOVESInstantiator.java:1449` |
| `MesoscaleLookupOperatingModeDistributionGenerator` | unreachable | **dead code** | same, and its swap runs before the clear |
| `MesoscaleLookupTotalActivityGenerator` | unreachable | **dead code** | same, and its swap is commented out |
| `NewTvvYearGenerator` | unreachable | **not a class** | a named SQL section, proved by oracle |

**What landed.** `docs/link-operating-mode-distribution.md` and
`./run-link-omd-oracle.sh` (122 of 122 cells exact, 21 `RatesOpModeDistribution`
cells, 43 snapshots swept);
`components/link_operating_mode_distribution.esm` (39 assertions);
`docs/new-tvv-year.md` and `./run-new-tvv-year-oracle.sh` (1,750 cells
bit-exact, three negatives, **no capture**); additions to
`lib/drive_cycle.esm` and a scale parameter on `lib/operating_mode.esm`'s
`decimal_quotient`; F44; conventions §44-§46.

Two arithmetic questions the corpus decided rather than the documents arguing:
the quotient is a **five**-decimal DECIMAL where its sibling's is four (§46),
and the interpolation is narrowed to a **single** before storage — 42/42 cells
with, 38/42 without.

**Two things this rung broke and fixed.** The reachability checker credited
two never-loaded generators with a third's rows, because three generators
share `OpModeDistribution`. `./run-omd-oracle.sh` counted 21 of this
generator's `RatesOpModeDistribution` rows against itself, because four
generators share that one and it was partitioned on `avgSpeedBinID` alone.
Both are §44.

**What it left.** `LinkOperatingModeDistributionGenerator` is **claimed and not
counted** by `tools/calculator-coverage.py`, for want of a fixture:
`scale-project` has no `.esm` fixture and cannot borrow one, being the only
snapshot whose `OpModeDistribution` is non-empty. A fixture for it means the
project-domain `BaseRate` chain, and `moves.rs`'s own port of that chain is
currently **50.69× high** against this snapshot
(`../moves.rs/docs/known-divergences.md` §6.1) — so the reference for such a
fixture is itself unsettled. `ProjectTAG` is the other unported live module,
and the same snapshot is its evidence.

**The denominator, honestly.** 65 modules, **32 live** (19 calculators, 13
generators), **30 of 32 ported**. It was 35 live and 30 of 35. The three
that left are the `DO_RATES_FIRST` discards; the fourth,
`NewTvvYearGenerator`, was never a module; and `ProjectTAG` **joined**,
because the exclusion that kept it out read "project-scale tagging" and TAG
is Total Activity Generator. The number went up because the denominator got
smaller and more honest, not because more was ported — nothing in this rung
added a counted module, and saying so is the point of §6.2's rule that the
figure is derived rather than recorded.

---

## Phase 7 — runspec to output, in `.esm` (planned 2026-09-10)

Everything above stops at the same place, and the goal does not. **Every one of
the 734 `data_sources` entries across `fixtures/*.esm` reads a canonical MOVES
*execution database* snapshot.** MOVES has already parsed the RunSpec XML and
materialised `RunSpecDay`, `RunSpecMonth`, `RunSpecHour` and the rest into that
database before the capture is taken. So the ladder in §2 measures the second
half of the pipeline:

```
RunSpec XML ──► [MOVES master: parse, importers, build execution DB] ──► execution DB ──► [calculators, generators] ──► MOVESOutput
                └────────────── not modelled in .esm ─────────────────┘                   └──── §2's ladder, 32/32 ────┘
```

Zero `.esm` documents read a RunSpec XML; zero read the default database. The
`runspec*` tables they consume are that phase's **output**, not its input.
Module coverage is a real number and it measures a different thing than the
goal does. Phase 7 is the front half.

### 7.1 The shape of the target

One top-level document per domain — **`moves-onroad.esm`** and
**`moves-nonroad.esm`** (they are separate executables in MOVES with separate
tables and separate arithmetic; one document covering both was considered and
rejected as the largest and riskiest option). Each reads the default database
and computes `MOVESOutput`. Then one thin `.esm` per fixture that imports the
domain document **by reference**, configures it, and checks it against
canonical output.

**"Thin" is 12 lines, measured and checked in.** 7c split a real fixture this
way and counted what the per-fixture document has to carry (conventions §53.2):
551 lines before EarthSciAST PR #298, 270 after it, 43 after PR #317 fixed F50,
and **12** after PR #353 fixed F13 and the enum union went. That is
`spikes/7c/tirewear_fixture.esm` — metadata and one `{ref}` — which mounts a
catalogue document that mounts the logic, and emits the fixture's 375 rows byte
for byte. It configures nothing, because it mounts a snapshot of one run and there
is nothing left to configure.

**7c′ is what a per-fixture document looks like when there IS.**
`runspecs/process-tirewear.esm` mounts `moves-onroad.esm` — 39
default-database tables and the same logic — and carries the ten runspec
selections and the expected output, which is every line of the difference.
Thin is not a line count; it is the rule that a per-fixture document holds
selections and nothing mechanical. §7.3.3 has what it measured.

**Where the three live, since 2026-09-17.** The split was made in `spikes/7c/`
and named for tire wear, which stopped being true the moment 7d asked the same
model for a second RunSpec. It is now:

| | |
|---|---|
| `onroad/model.esm` | the domain MODEL — one model, no `data_sources`, and the metaparameters and index sets that size it. Data-open; does not validate alone. |
| `moves-onroad.esm` | the domain CATALOGUE — the default database's 39 tables, mounting the model. Still data-open: it declares no runspec. |
| `runspecs/<run>.esm` | one thin document per RunSpec, mounting the catalogue. These validate alone, which is the point. |

**Since step 7f the catalogue is two documents** (§7.3.40, conventions §92): `onroad/default-database.esm` holds the default database's tables and mounts the model, and the run's DOMAIN document mounts it and declares the tables MOVES merges differently by domain, with the RunSpec's `<modeldomain>`. `moves-onroad.esm` is the DEFAULT domain's and is what every RunSpec but one still mounts; a scale-input database's is in `inputs/`.

**Since 2026-10-30 `fixtures/` has the same shape** (conventions §106): each of
the fourteen fixtures is its snapshot's execution database under the `db_*`
names, mounting `onroad/model.esm` or `nonroad/model.esm` with the run's
declared counts as `bindings`. The inlined copies of the spine they used to
carry -- 236k lines -- are gone, and all fourteen reproduce their snapshots at
the same worst cells as before.
Since 2026-11-01 the execution database itself is written twice, not per
fixture: `fixtures/catalogues/{onroad,nonroad}-execution-db.esm` hold the tables
behind a `{snapshot}` placeholder and mount the model, and each fixture mounts
its catalogue as a subsystem with `url_substitutions: {snapshot}`, its counts
and its tests (EarthSciAST #616/#617/#618; conventions §106).

The input source keys moved with the file — `tw_link` is `db_link` — because
the tables are the database's and not one process's. `spikes/7c/` keeps the
snapshot catalogue and the 12-line fixture that mount the same model, which is
what makes the two databases a cross-check rather than a migration.

**Two shape constraints, both measured in 7a and neither of them optional.**
An ingesting document holds exactly **one** model (F45), and that model is the
mount — so the fixture has nowhere to put an inline `tests` block beside
it, and `"tests"` as a sibling of the `ref` is refused outright. A mounted
child's own inline tests never run either (F47). So a fixture is verified by
**emitting its relation and comparing** — exactly what `run-tests.sh`'s
fixture stage already does — not by an assertion. *(Superseded 2026-10-31:
since EarthSciAST PR #612 the one model can mount the domain model as a
`subsystems` `{ref}` and carry `tests` naming `Onroad.*`, so every fixture
now does both — asserts its intermediate values and compares its relation.
Conventions §106 point 3.)* And because a mounted
document whose models reference each other cannot itself be mounted,
**`moves-onroad.esm` must be a single model**, composed internally through
expression templates rather than nested mounts.

**No intermediate checkpoint.** The 44 captured execution databases are *not*
reproduced as an intermediate target; the documents go straight to
`MOVESOutput`. The cost of that choice is localisation — a wrong number does
not say which of ~30 modules produced it — and the mitigation is free: the 15
existing snapshot-fed fixtures **stay** as module-level tests. They already
localise a failure to a generator and cost nothing to retain. Phase 7 adds no
intermediate assertions; it does not remove the ones we have.

### 7.2 What the format already does, measured

Three probes, first run against the pinned `esm 0.2.0` / EarthSciAST
`3aa046d65` and re-run at `9dd36c7f6` after PRs #297 and #298 merged. Two of the
four bullets below changed at that rebuild and say so:

- **Shape is already data-driven.** Every fixture's `index_sets` are sized by
  metaparameters, and those are bound at load time from a `data_sources` entry's
  `extent`. Nothing about that needs to change.
- **Components carry no data.** `components/onroad_travel_fraction.esm` and
  `onroad_source_hours.esm` declare `enums`, `index_sets`, `coordinates`,
  `models` — logic and shape only, no `data_sources`. That is already the split
  Phase 7 wants.
- **A child can leave its shape open and the parent closes it.** A child
  declaring `index_sets: {rows: {size: "n_rows"}}` and no `n_rows` fails alone —
  `invalid type: string "n_rows", expected i64` — and **validates through a
  parent** that declares `n_rows` and refs it. So the shared document is open at
  the top and the fixture closes it.
- **A child could leave its shape open — and should not.** The third bullet is
  how this worked against the pinned `0.2.0`, and EarthSciAST PR #298 ended it:
  a mounted leaf is now resolved in its own scope, so a leaf sized by names only
  the root declares is refused `metaparameter_unbound`. Python had been refusing
  that arrangement all along, as `subsystem_index_set_conflict`, and nothing
  here measured it (F51). **The portable shape is `leaf-owns-shape`**: the leaf
  declares its metaparameters and its `index_sets`, the mount declares the
  `data_sources`. Both bindings accept it; `spikes/7a` and `spikes/7c` are both
  written that way.
- **What #298 and #317 fixed (F46, F50).** The mounting document used to have to
  **restate the child's `index_sets` verbatim** — F46, worth 250 lines in the 7c
  mount — and #298 ended that. The metaparameter half it left was F50: a name a
  `data_source`'s `extent` binds had to be declared by the document owning the
  axis **and** by the root, because the loader API closed discovered extents
  only at the root, and `bindings` could not carry it (measured at 49 names).
  That was 247 more lines, and PR #317 ended it too: a discovered extent now
  binds where the name is declared. Measured both ways at the mount edge, a
  child's `data_sources` **merge up**, and that is load-bearing — it is what
  lets the shared document carry the whole default-DB catalogue.

**`ref` with overrides EXISTS, and this plan previously said it did not.** That
conclusion came from `{"ref": …, "metaparameters": …}` being refused
(`Additional properties are not allowed`) — but the key was wrong, not the
feature. `SubsystemRef` takes **`bindings`**, **`model`**,
**`index_set_rename`** and **`expression_template_imports`** (`esm-schema.json`,
`additionalProperties: false`). Measured: `{"ref": "./child.esm", "bindings":
{"n_cat": "n_spike_agecategory"}}` closes a child's *own* open metaparameters
from the parent, with a runtime-discovered `extent` flowing through. Two limits:
a metaparameter closed by `bindings` is **not readable in an equation**
(—`bindings` closes sizes only), and it can only *close* a name the referenced
document already declares, never *supply* one — which is why it was not F50's
way out (#317 was).

So configuration has three working channels, not none: a per-fixture
`data_sources` key the shared document binds by name; a metaparameter declared
in the mounting document with a literal `default` and read as a scalar in a
child equation; and `bindings` at the mount edge for sizes.

### 7.3 The default database: convert the whole of it, monolithically

The release asset (`default-db-movesdb20241112.tar.gz`, 64.5 MB) unpacks to
**781 MB of Parquet over 240 tables** — 220 monolithic, 17 partitioned by
county / year / modelYear, 3 schema-only. The partitioned ones are what make a
fixture want to address a *file*:

| table | size | partitions | one county needs |
|---|---|---|---|
| `IMCoverage` | 378 MB | 21,625 (county × year) | ~8 KB |
| `fuelUsageFraction` | 89 MB | 3,230 | ~21 KB |
| `regionCounty` | 39 MB | 3,233 | ~7 KB |
| `nrStateSurrogate` | 26 MB | 3,285 | ~4 KB |

**7a measured this table, got the right number for the wrong reason, and 7b
corrected it.** `IMCoverage`'s 378 MB is mostly not data — it is 21,625
files of ~17 KB dominated by Parquet footer. But 7a's headline "791,123 bytes,
a 478× reduction" was produced by **pyarrow with Snappy and dictionary
encoding**, while the converter writes uncompressed, no dictionary, no
statistics, under a deliberate byte-determinism contract. That was a
*compression* result labelled as a *de-partitioning* one.

De-partitioning alone, like for like: **262,910,040 → 204,574,768 bytes**,
i.e. **1.29×**, over the same 2,024,874 rows. The compression win is real,
unclaimed and larger than the layout win — the whole database re-encodes
from 515.8 MiB to **15.8 MiB** (Snappy+dict) or 12.0 MiB (Zstd+dict), and
reads get *faster* with it. It is deliberately not taken here: it trades the
byte-determinism contract for a compressor's version stability, and it needs a
check that the EarthSciAST reader decompresses Snappy. **That is a 7c
decision, not a layout one.**

**Convert the entire database, one monolithic Parquet per table.** Not a
corpus-scoped cut: a database that only holds the geographies today's fixtures
name is not "the MOVES database", it silently limits what can ever be run, and
it would have to be re-cut every time a fixture is added.

**This removes the only upstream ask, and §1.3 is why it costs nothing.** The
naive objection to a monolithic national table is that selecting one county out
of 3,232 means paying for all of them. That was true before the equi-join gate,
and it is exactly what the gate was built to fix: `join.on` in EarthSciAST
`28bda86ac` **drives enumeration from the match set**, so cost tracks matches
rather than the product — 10⁸ combinations with 10⁴ matches in 0.032 s, against
a timeout at 10⁷ before. A national `IMCoverage` joined against the run's
county selection is enumerated by the join, not scanned per row. This project
built that gate as its first deliverable; Phase 7 is the first thing that
collects the dividend.

So: no partitions to address, no `url_template` parameterisation, no document-
level row filtering, and the *output* shapes stay match-sized because the join
drives them.

**The load cost is now measured, in 7a rather than 7b.** `esm test`, one table
per throwaway document, wall clock, `TMPDIR` on disk:

| table | on disk | rows | cold | warm |
|---|---|---|---|---|
| `EmissionRateByAge` | 105.7 MiB | 1,590,830 | **4.94 s** | **0.33 s** |
| `IMCoverage`, consolidated | 0.8 MiB (Snappy+dict) | 2,024,874 | **0.46 s** | **0.41 s** |

The `IMCoverage` row is the Snappy+dictionary file, not what the converter
ships; as shipped it is 195.1 MiB and reads in 0.102 s.

So `EmissionRateByAge` is the only one of the two that was ever a real cost,
and warm it is a third of a second. This does not dictate the layout.

**Two things 7b must not trip over.** First, the ingested-source cache lives in
`$TMPDIR`, which is `/tmp`, which is **`tmpfs` on this host** — it had
reached 758 MB before anyone looked. Converting a whole database with the
default `TMPDIR` will put the lot in RAM and OOM the machine; **set `TMPDIR` to
disk first.** Second, the converted database at
`/scratch/$USER/movesdb/movesdb20241112` was **220 monolithic tables plus 11
still-partitioned directories** (the twelfth directory is `_tsv`, not a
table). **7b has since converted it**: see below.

**The original statement of the cost, retained because it is what was
assumed:**
`data_sources` are loaded per `esm` invocation, so a run pays the parse of
whatever tables it declares — `IMCoverage` at 378 MB and
`EmissionRateByAge` at 106 MB being the two that matter. `run-tests.sh` invokes
the binary many times. If that parse dominates, the answer is a reader-level
concern (projection or predicate pushdown, or a per-table lazy read), not a
reason to re-partition the data — but it needs a number before 7c commits to
the layout.

### 7.3.1 7b, done 2026-09-10: the conversion, and what it measured

**The database is monolithic.** 237 monolithic Parquet tables plus 3
schema-only sidecars, **zero partition directories**, **517 MB** against
781 MB, converted in **15.6 s**, byte-identical across two runs. Output at
`/scratch/$USER/agent-7b/movesdb20241112-monolithic/`; the old tree is left
in place because a `moves.esm` test stage skips against it.

**The policy moved, not the capability.** `audit-schema.py::_classify_partition`
is now one rule; `partition.rs` and `plan.rs` still implement and unit-test all
five strategies, so the layout stays expressible. A test pins the shipped audit
at 237+3 so a strategy cannot reappear unnoticed.

**The equi-join premise, verified on the real table rather than assumed.** On
the national 2,024,874-row `IMCoverage` joined on `countyID`: 1 county →
3,884 matches in 0.17 s; 405 counties → 2,024,874 matches in 2.23 s. **40.5×
the cartesian pairs for 8.6× the wall clock**, about a microsecond per match.
And the single-county join at 0.17 s **beats the same selection written as a
filter over all 2 M rows at 0.39 s** — reading nationally and joining is
the faster spelling, not a tolerated one. Peak RSS tracks the materialised
match set, which is worth remembering before joining two multi-million-row
tables on a low-cardinality key.

**Two incidental findings.** Five of the eleven populated "partitioned" tables
had been sharded into exactly **one** file, on an estimated upper bound the
real data never approached. Six more had zero rows and so produced **no
artifact at all**; monolithic writes an empty Parquet carrying the schema.

**The validator had a hole, and closing it is the durable part.** `Utf8` and
`Boolean` columns were only counted for non-nulls and the float sum quantises
at 1e-9, so a changed string cell in a 2 M-row table, a changed county name,
and a 1e-12 float change all passed **clean**. A per-column exact content
digest over every cell of every type including nulls, plus an order-independent
row-multiset digest, closes it. All seven planted corruptions are now red;
three were green before.

**Not released.** The tarball is a public asset on the EarthSciML org and
replacing it is a separate decision. Note the asset is 1.1 GB unpacked, not
781 MB: `_tsv/` is 337 MB of it, 59% of the compressed tarball. The
recommendation on record is to ship it as a sibling asset, which also removes
an exclusion three CI workflows each re-implement.

### 7.3.2 7c, done 2026-09-10 and re-shaped 2026-09-12: the mount at fixture scale

`fixtures/process-tirewear.esm` — 49 `data_sources`, 411 variables, 245
equations, 53 axes — split into `onroad/model.esm` and
`spikes/7c/tirewear_mount.esm` and compared against the inlined fixture's own
output in the same run: **byte-identical, 375 rows over 26 fields**, and
falsified by perturbing `emissionrate.meanBaseRate` and watching both halves
move identically. It costs about 7 seconds of the suite. Conventions §53.

**It was committed knowingly non-conforming and is not any more.** The first
split declared the 53 axes in both halves, which the pinned `0.2.0` accepted and
the spec did not; `run-tests.sh`'s stage header said so and said what to do when
PR #298 landed. #298 merged on 2026-09-12 and the stage went red exactly as
written. The instruction was followed: the mount's 250-line `index_sets` block
is gone, the leaf owns the shape, and **both the Rust and the Python bindings
now load the result** — which neither `spikes/7a` nor `spikes/7c` had ever done
before.

Three findings retired with it (F46, F48, F49) and two opened (F50, F51). The
line counts are in conventions §53.1 and §53.2; the short version is 1505 → 1255
for the mount, and 551 → 270 for what a per-fixture document would carry.

**Re-shaped again 2026-09-15, and now thin.** EarthSciAST PR #317 fixed F50, and
the 7c stage's two-sided watch went red on it with an instruction saying what to
delete. The mount's 247-line `metaparameters` copy is gone (1255 → 1008 lines),
and `spikes/7c/tirewear_fixture.esm` — then 43 lines, now 12 — is the
per-fixture document §7.1 describes, emitting the same 375 rows byte for byte
through two mount edges. It carried the enum union until PR #353 retired F13 two
days later; what is left is metadata and one `{ref}` to the mount. The stage
checks that, and that the document stays thin. F50 is retired; F51 changed
upstream and is left open, unmeasured on the Python side.

**The same rebuild moved every document to `esm 1.1.0`.** PR #299 renamed the
query node `aggregate` → `faq` and kept the old spelling as a deprecated alias.
The alias loads standalone, but the build re-validates a `{ref}` assembly's
resolved document under the ROOT's declared version, so a 1.0.0 root mounting
anything that used `aggregate` was refused with `faq_version_too_old` — five
suite checks at once. All 89 documents now declare 1.1.0 and spell the node
`faq` (3382 nodes, a rename and nothing else), and `tools/check-conventions.py`
refuses the alias.

### 7.3.3 7c′, done 2026-09-17: the same 375 rows out of the default database

`runspecs/process-tirewear.esm` → `moves-onroad.esm` →
`onroad/model.esm`. **Byte-identical to the inlined fixture's 375
rows over 26 fields**, from the monolithic conversion of §7.3.1 rather than from
the run's execution-database snapshot. 40 s, against 3 s for the snapshot-fed
chain, and the difference is almost entirely one table: `fuelUsageFraction` is
1,424,430 uncompressed rows of which the run keeps 5.

**The premise held, and it is the one §7.3 bet the layout on.** Every table is
read NATIONALLY and narrowed by the joins. Measured one table at a time —
repoint one `url_template` at the national file, re-emit, compare — **36 of the
37 that exist in both databases are byte-identical drop-ins**, and all 38
together (the 37 plus `sourceUseTypePhysics`) give the same bytes.

**One table was not, and it is the interesting one.** An execution database is
the default database already cut to the run, so a document written against one
can leave its selections unsaid. `link` did: the execution copy has ONE row, so
the four run-level geography columns *summed* it, and summing a one-row table is
the same as reading it. The national `Link` has 22,610 rows and the sum reads
county 710047702 — Σ countyID over every link row — with the state column at a
thousandth of it. Nine digits where a county has five. The fix is to say the selection — county × road type, both
already in the runspec — and it cost one data source (`runspeccounty`), one
variable and four `join.on` clauses. `run-tests.sh`'s 7c′ stage deletes that
join and requires the numbers to move.

**Two tables the default database does not ship, because MOVES builds them at
execution time. Both are gone rather than worked around.**

* `sourceUseTypePhysicsMapping` is `sourceUseTypePhysics` with `sourceTypeID`
  renamed to `realSourceTypeID` and two columns added that this document never
  reads. It reads the real table now: one `file_variable`, and the snapshot
  ships that table too, so both configurations read the same thing.
* `evSalesFraction` is a real computation — `evFraction[modelYear,
  fleetAvgGroup] = evsales / sales` over the age-0 slice of `SourceTypeYear ⋈
  SourceTypeAgeDistribution ⋈ SampleVehiclePopulation ⋈ RegulatoryClass`, the
  numerator restricted to fuelType 9. All four tables were already ingested, so
  the table became three equations: `svp_salesWeight` (one row's age-0 sales),
  `coh_salesAllFuels`, `coh_salesElectric`, plus a presence flag. It reproduces
  the snapshot's 115 rows exactly from either database.

  **Written first as the single six-range join the SQL is, and that did not
  finish in three minutes.** Factoring the per-sample-vehicle weight out —
  two four-range joins instead of one six-range one — costs 0.3 s. The
  intermediate is also the better document: a named quantity computed once
  rather than a subexpression repeated three times.

**What the split says.** `moves-onroad.esm` holds the domain (tables + logic)
and **does not load alone**: it names ten runspec sources it does not declare.
That is not an oversight and cannot be fixed by shipping a default runspec,
because a `SubsystemRef` carries `bindings`, `model`, `index_set_rename` and
`expression_template_imports` and nothing else — **there is no channel for a
mounting document to override a mounted one's `data_sources`**, so a default
would be unreplaceable. The runspec is therefore the fixture's. The suite
asserts the refusal two-sided, the way it does for the 7c logic half.

**`./movesdb/` is an untracked symlink** to the §7.3.1 conversion, gitignored
beside `./esm` for the same reason: 517 MB of derived data is not source. The
stage skips when it is absent.

**What it does not yet do.** It is one process and one runspec. The runspec is
read from the snapshot's own `runspec*` tables rather than written in the
document, because the logic INGESTS those selections — which is what sizes the
axes they are the extent of — and an ingesting document holds one model (F45),
so there is nowhere in a per-fixture document to state them inline. A runspec
expressed as metaparameters instead would remove the last snapshot dependency;
that is a 7d question and it is not a blocker for 7d.

### 7.3.4 7d, begun 2026-09-17: two more RunSpecs, and what the first one was hiding

`runspecs/expand-day.esm` → `moves-onroad.esm` → `onroad/model.esm`. **250 rows
against the snapshot's own `MOVESOutput`, 0 missing and 0 extra, worst cell
7.106 × 10⁻⁶** — the same worst cell the inlined `fixtures/expand-day.esm`
reports, and the two agree **byte for byte over all 25 shared fields**. One
comes from that run's execution-database snapshot through 196 equations written
out in full; the other from the national default database through a model
written for tire wear.

**The document is 207 lines and differs from `runspecs/process-tirewear.esm` in
eleven `url_template`s and one binding.** That is PLAN.md §7.1's per-fixture
document measured a second time, and it is the answer to the question 7c left
open: `fixtures/expand-day.esm` is 14,603 lines of which 147 equations are
*byte-identical* to `fixtures/process-tirewear.esm`'s, so a corpus of inlined
fixtures is a corpus of near-copies.

**What was in the way was not a dimension.** The output relation was a
RECTANGLE over the run's selected pollutant-processes, which is true of
`process-tirewear` by accident: all three of 9101, 10710 and 11710 happen on a
road. `expand-day` selects 9101, 9102 and 9190 and MOVES writes the
running-exhaust block alone, because start exhaust and extended idle write
their rates on the off-network road type 1 and `BaseRateCalculator` joins to
`runSpecRoadType`. The model reads that rule out of
`emissionProcess.occursOnRealRoads` now; conventions §60 has the five
equations, the relay that lets a per-fixture document set the block count, and
the honest limit — `expand-day` cannot discriminate the block *renumbering*,
because its one survivor is also its first.

**What the day axis cost: nothing.** `n_runspecday` is discovered from the
source's own extent, so at 2 rows the activity relation, the hour-day key and
the output relation doubled with no edit to the model. That is §42.1's
measurement run in the other direction, and it is the strongest evidence
available that the day axis is factored rather than written down.

**GEOGRAPHY, done the same day.** `runspecs/expand-counties.esm` selects Los
Angeles, Cook and Washtenaw and emits **375 rows, 0 missing and 0 extra, worst
cell 1.140 × 10⁻⁵** against a 2 × 10⁻⁵ tolerance. The county stopped being a
property of the run and became an axis of it: **30 of the model's 425 variables
gained it, three more were added to carry it, and 395 did not** — the drive
cycle, the emission rates and which cohorts survive are national, and the county
enters only at `zoneRoadType`'s allocation, `ZoneMonthHour`'s meteorology and
`fuelUsageFraction`'s county key. Conventions §61 has the whole list and the
reason for each side of it.

That is also the first evaluation of the join 7c′ added. It had narrowed a
22,610-row national `Link` against a one-county runspec, where a join returning
the FIRST match rather than the MATCHING one would have passed every check in
the suite; here it has to return three different links, three zones and three
states. The probe `no-county-join` deletes the output relation's county key pair
and the numbers move into exactly the 7c′ shape one axis up — `out_countyID`
comes back 49229, `out_stateID` 49, and SHO 10960.9 in place of 8364.2, 2336.7
and 260.1.

**`process-tirewear` and `expand-day` emit their 375 and 250 rows BYTE FOR BYTE
unchanged** through the widened model, which is the check that an axis was added
and nothing else was.

**The three dimensions left, and what each actually costs.** Every remaining
`expand-*` snapshot needs something the model does not have, and none of them
is a re-pointing.

**How the cost was priced.** The same forward closure that found geography's 37
equations, run from each remaining scalar: **`run_sourceTypeID` reaches 125 of
the model's 262 equations, `run_hourID` 39 and `run_monthID` 32**, against
geography's 37. Source type is the expensive one because it reaches the DRIVE
CYCLE — `sourceUseTypePhysics` is keyed by source type, so the VSP, the
operating modes and `pp_W` all become per source type, and that is where the
`join.on` scaling gate lives.

| fixture | rows | what it needs |
|---|---|---|
| `expand-month` | 500 = 125 × 4 months | 32 equations, the cheapest of the three — but `dayID`, `hourID` and `hourDayID` all come back **0** in its output, and the snapshot's `DayOfAnyWeek` has been rewritten to one row, `dayID` 0, "Whole Week", `noOfRealDays` 7. MOVES SYNTHESISES those aggregate rows at execution time, so this is §59.2 again: a table the default database does not ship because it is a result. Not a wider selection — a second time-aggregation mode. |
| `expand-sourcetype` | **430**, not 5 × 125 | 125 equations, and the cohort count is RAGGED across the five: 41 / 125 / 125 / 89 / 50 for source types 11, 21, 31, 51 and 62, with different fuel sets (11 gasoline only; 62 diesel and CNG). The cohort GRID already spans source type — `runspecsourcefueltype` carries the pair and `coh_rank`'s prefix count already handles raggedness — but `n_outputCohort` stops being one declared number and `output_rows` stops being a PRODUCT of declared numbers, because 430 is a sum. |
| `expand-fueltype-diesel` | **248** = 125 + 123 | the same axis at width 2, with the ragged count visible in the smaller number. It comes free with the one above. |
| `expand-criteria` | 372 = 3 × 124 | pollutants 1, 2 and 3 on process 1, from 8 selected pollutant-processes at positions 1, 3 and 5. New physics (criteria pollutants), and the one run in the corpus whose survivors are not a prefix — so it is also what would discriminate §60's renumbering. |

**So the order is month, then source type, then the criteria pollutants**, and
it is by cost rather than by the §7.5 list's order. Geography cost 30 variables
of 425 and one level in the output decomposition and left every cohort count at
125; source type is four times the equation count and takes the output
relation's shape contract with it.

**That contract is the decision the next step opens.** `output_rows` is an
interval sized by a PRODUCT of declared numbers, and every output column finds
its place by dividing that product back down. A ragged cohort count makes the
total a SUM, so either `output_rows` is sized by one declared total that the
chain recomputes — the `n_outputCohort` discipline applied once instead of
twice, and the floor/mod decomposition replaced by the dense rank
`rt_outputOrdinal` already computes — or the axis becomes `ragged` (§22 argues
against, F14 measured the spelling). The first is the smaller change and the
better document; it is also a change to the one thing §7.1 says a per-fixture
document may declare, so it is written down here before it is made rather than
after.

### 7.3.5 7d, 2026-09-18: the source type is an axis, and the cohort is not the source bin

**The decision above turned out not to be one.** The sum over source types IS
the cohort survivor count: `runspecsourcefueltype` was already the cohort grid's
second factor and it carries (sourceTypeID, fuelTypeID) PAIRS, `coh_rank`
already densifies whatever survives, and `cohortSurvivorCount` already recomputes
the total as one number. `output_rows` stays a product of four declared or
discovered numbers with the source type INSIDE `n_outputCohort` rather than
beside it: 1 × 1 × 1 × 248 for `expand-fueltype-diesel`, 1 × 1 × 1 × 430 for
`expand-sourcetype`. What did change is that `n_outputCohort` is now a number a
per-fixture document sets, through the same `bindings` relay in
`moves-onroad.esm` that `n_outputPolProcess` uses (§49.1), rather than one value
for the whole corpus.

**The promotion itself was the county's, three and a half times over.** 44
variables gained a `runspecsourcetype_rows` axis — the drive cycle (VSP is
computed from the source type's own `sourceusetypephysics` row, so the operating
modes it bins into, the speed-bin brackets and the operating-mode distribution
all follow), the activity relation, and the run's VMT, population and HPMS
normalisation group. `run_sourceTypeID` is gone: it summed the source-type
relation into a scalar, right for one row and garbage for five. **The three
existing runs are unchanged to the digit** — 375, 250 and 375 rows at worst
cells 8.128e-06, 7.106e-06 and 1.140e-05 — which is what an axis at width one
should cost.

**F57 cost the step a second attempt** and is the sharpest toolchain finding
since F45. A `faq` join key must be a 1-D column; give it a 2-D one and the
clause is **dropped, not refused**. `dsa_modeSeconds` joins `om_opModeID` to
`dss_opModeID`, which gained an axis here, and the operating-mode distribution
came back as 1.0 on all 60 modes instead of summing to 1.0 over 23 —
running-exhaust energy 22× to 24× high while the tire-wear pollutants in the same
run stayed exact to 1e-5, because they take the other arm of an `ifelse`. Repro,
control and EarthSciAST#417.

**What stops `runspecs/pending/expand-fueltype-diesel.esm` is not the axis.** It
emits the right shape — 248 rows, 125 under source type 21 and 123 under 32 —
and **every one of source type 21's 125 rows reproduces `MOVESOutput` at worst
cell 7.106 × 10⁻⁶**, the same worst cell `expand-day` reports. Source type 32's
123 are wrong, for one reason:

| source type | regulatory classes | triples carrying more than one |
|---|---|---|
| 11 | 10 | 0 of 111 |
| 21 | 20 | **0 of 444** |
| 32 | 30, 41 | 333 of 444 |
| 51 | 41, 42, 46, 47 | 333 of 444 |
| 62 | 46, 47, 49 | 222 of 333 |

A MOVES **source bin** is (sourceTypeID, fuelTypeID, modelYearID, regClassID,
engTechID); this model's cohort candidate stops at the first three.
`coh_regClassID` is a `sum_product` over the matching `samplevehiclepopulation`
rows, so on a two-class triple it returns **71** rather than 30 or 41,
`emissionrate` matches nothing and the rate is 0. Source type 21 has one
regulatory class for every triple it carries, which is why every run before this
one was right by accident — the third time in 7d that a selection of width one
hid a structure (§60's rectangle, §61's county, this).

**The fix is bounded and is the next step.** `cohort_rows` gains
`regulatoryclass_rows` as a third factor — 328 candidates become 4,264 and
`rate_rows` 984 become 12,792 — `coh_rank` ranks distinct (source type, fuel
type, model year) TRIPLES rather than candidates, and the output relation's
ordinal join sums the bins of a triple, which the `faq` already does. 330
selected bins carry the 248 output rows of `expand-fueltype-diesel`; the 82
difference is exactly its two-class triples. Only `emissionQuant` is compared,
so the per-bin `meanBaseRate` and `SHO` columns summing is not a constraint.

**Both documents are checked in under `runspecs/pending/`** rather than deleted:
they validate, they round-trip, they pass the conventions, and the suite holds
them to saying what they wait on. A measurement that cost a session is worth
more in the tree than in a commit message.

### 7.3.6 7d, 2026-09-18: the cohort is not the source bin, and the source bin is not the vehicle

§7.3.5 named the next step and it was the right one. `cohort_rows` did **not**
gain a factor; a separate `sourcebin_rows` relation did, and that is the better
shape. A cohort is (source type, fuel type, model year) — the thing MOVESOutput
has a row for, which has no regulatory-class or engine-technology column. A
MOVES **source bin** is those three plus (regClassID, engTechID) — the thing
`emissionrate` has a rate for. They are two relations, they are one-to-many, and
the model now says so:

| relation | rows, `process-tirewear` | rows, `expand-fueltype-diesel` | what a row is |
|---|---|---|---|
| `cohort_rows` | 164 | 328 | a candidate output row |
| `sourcebin_rows` | 164 | 656 | a candidate rate lookup |
| `rate_rows` | 492 | 1,968 | a pollutant-process × a source bin |

**The slot count is the third declared number and it is checked.** No table
states how many bins a cohort holds, so `n_sourceBin` is declared and relayed
through `moves-onroad.esm`'s `bindings` like the other two (§49.1) — 1 for every
run that selects a single-binned source type, 2 for `expand-fueltype-diesel`, 8
for `expand-sourcetype`. At 1 the bin relation IS the cohort relation, row for
row, so **the three runs in `runspecs/` are unchanged to the digit** — 375, 250
and 375 rows at worst cells 8.128e-06, 7.106e-06 and 1.140e-05, the same three
numbers 7d's other two dimensions left. `run_sourceBinsDropped` counts the bins
a slot short would lose and is asserted at 0, because a short slot count is not
a missing row — it is a row whose emissionQuant is quietly low.

**`svp_binOrdinal` is the dense slot MOVES does not have.** A source bin is
named by its packed id; the rows of one cohort are whatever
`samplevehiclepopulation` holds. A candidate grid cannot enumerate "whatever
they are", so the model ranks them: §22's inclusive prefix count, gated to the
cohort by a join rather than an equality filter, and the four-column lookup
(source type, model year, fuel type, slot) reads the bin's regulatory class,
engine technology and fraction back off the row.

**A key column now comes from the relation that owns it.** Several rate rows
share an output row, so `out_modelYearID` and the other five key columns would
have SUMMED their keys through `rt_outputOrdinal`. They read from the cohort
relation through `coh_rank` and from the pollutant-process relation through
`rspp_outputOrdinal` instead. The value columns keep the rate join, where the
sum over bins is exactly the point.

#### What this bought, measured

`expand-fueltype-diesel` went from **123 of 248 rows returning 0** to three of
the four factors of an emission being exactly right:

* **Source-hour activity: exact for both source types**, every row, against the
  execution database's own `sho` table.
* **Source-bin distribution: exact for both.** 330 selected bins — 125 under
  source type 21, 205 under 32 — and every `bin_usedFraction` equals the run's
  own `sourceBinDistributionFuelUsage_1_26161_2020.sourceBinActivityFraction`,
  including the fuel-usage re-attribution that moves 98.2% of equipped E85 into
  gasoline. Every per-(source type, model year) total is 1.
* **Source type 21: still 125 of 125 exact** at 7.106e-06.
* The per-pollutant total went from **21.6× to 1.157×**.

#### What stops it now, and it is the third key a width-one selection hid

`sourceusetypephysics` is keyed by **(sourceTypeID, regClassID, model-year
range)** and the drive cycle is per SOURCE TYPE. `phys_rollingTermA` and the
rest are a `sum_product` over the rows a source type selects, so a source type
with more than one row computes vehicle-specific power for a vehicle that does
not exist.

| source type | physics rows |
|---|---|
| 11, 21 | 1 |
| 31, 32 | 3 |
| 51 | 15 |
| 41, 43, 52, 53 | 21 |
| 62 | 20 |

Source type 32's three are regulatory class 30, and regulatory class 41 split at
model year 2010 because its fixed mass factor goes from 2.05979 to 5.0. **The
model's own guard reports it**: `run_physicsRowsSelected` is 1 for source type
21 and 3 for source type 32, and that variable's description was written to say
that the day it is not 1, `dss_vsp` is the sum of two vehicles' physics rather
than one's. The operating-mode distribution it feeds still sums to 1 over 23
modes, which is why the error is not a scale factor but a reweighting: 1.7316 on
E85, 2.1633 on electricity, 1.48 to 3.06 where two regulatory classes blend.

**The next step is the same promotion 7d did for the source type, one key
finer.** Everything from `phys_isSelected` down to `pp_W` carries a
`runspecsourcetype_rows` axis and would carry the run's selected PHYSICS ROWS
instead — 4 for `expand-fueltype-diesel`, 40 for `expand-sourcetype`, out of the
178 the table holds. It is not free the way the source bin was: the drive-cycle
chain is the model's largest relational step (63,602 drive-schedule seconds with
four self-joins), so the axis has to be the selected rows and not a padded
product of source types and a slot count.

### 7.3.7 7d, 2026-09-18: the drive cycle is per VEHICLE, and `expand-fueltype-diesel` reproduces

§7.3.6 named the fourth hidden key and the guard that found it. This is the step
that closed it. `sourceusetypephysics` is keyed by **(sourceTypeID, regClassID,
beginModelYearID, endModelYearID)**, and everything from `phys_isSelected` down
to `pp_W` now carries that row rather than a source type.

**The axis is the run's selected rows, densely ranked — not a padded product.**
`n_sourceBin` could afford padding because a cohort grid is small; the drive
cycle reads 63,602 drive-schedule seconds once per vehicle, and a product of 5
source types and a 20-slot width would compute 100 drive cycles where
`expand-sourcetype` has 40. So the promotion reuses §22 rather than §63.3's
grid: `phys_isSelected` over the 178-row national table, `phys_prefixSelected`
its inclusive prefix count, `phys_rank` the product that zeroes the rest, and a
`phy_*` relation that reads its nine columns back through
`phys_rank ↔ phy_ordinal`.

`n_physicsRow` is the **fourth declared number**, relayed through
`moves-onroad.esm`'s `bindings` like the other three (§49.1) and checked both
ways: `run_physicsRowsSelected` recomputes it, and `run_physicsRowsDropped`
counts the vehicles that fall past it. A third guard,
`run_rateRowsWithoutPhysics`, catches the same failure from the other side — a
rate row whose regulatory class the physics table never had. All three are
asserted at their values by `tools/check-runspec-shape.py`.

**The rate row finds its vehicle the way `aggregate.rs:351-358` does.**
`rt_physicsOrdinal` joins on (source type, regulatory class) and FILTERS on the
model year lying inside the row's range, because a containment is not a key.

**Only half the drive cycle moved.** Which schedules apply, which two bracket an
average-speed bin and what weight each carries are properties of the SCHEDULES
and stay per (source type, road type); vehicle-specific power, the operating
mode a second bins into and the schedule's mode distribution are properties of
the PHYSICS and became per vehicle. `asb_modeFraction` is where the two
multiply, and `phy_sourceTypeOrdinal` is the join that puts them on one row.

#### What it cost, which was less than nothing

The same edit added the gate the finer key makes available — MOVES's
`ScheduleOpModeKey` is (physics row, drive schedule), so `dsa_totalSeconds` and
`dsa_modeSeconds` now join the association to the vehicle's OWN source type and
the run's road type, and 614 associations become the ~11 a source type drives on
one road. Measured on the two pending runs, before and after, same machine:

| run | axis | peak RSS | wall clock |
|---|---|---|---|
| `expand-fueltype-diesel` | 2 source types → 4 vehicles | 24.6 GB → 24.6 GB | 273 s → 151 s |
| `expand-sourcetype` | 5 source types → 40 vehicles | 34.4 GB → 31.0 GB | 233 s → 115 s |

A ten-fold finer axis that runs in half the time is the gate, not the axis.

#### What it bought

**`runspecs/pending/expand-fueltype-diesel.esm` reproduces and is no longer
pending**: 248 of 248 cells, worst cell **7.372e-06** against a 2e-05 tolerance,
worst per-pollutant sum 2.000e-08. It was 123 rows of zero before 7.3.6, then
1.48–3.06× per cell and 1.157× per pollutant after it. Both source types, both
regulatory classes, the split at model year 2010 and all four fuels.

**`n_physicsRow` defaults to 1, and at 1 the drive-cycle relation is the one
vehicle a single-regulatory-class source type has**, so the three runs already
in `runspecs/` are unchanged to the digit: 375, 250 and 375 rows at 8.128e-06,
7.106e-06 and 1.140e-05 — the same three numbers 7d has left alone through four
promotions now.

#### What it did NOT unblock, and where the ceiling is

`runspecs/pending/expand-sourcetype.esm` — the same axis at width five, 40
vehicles — still does not run, and for a reason that is no longer about a key.
It is KILLED at **32.0 GB** of resident memory against this job's 40 GB cgroup
limit, which counts page cache as well. *Killed at* and not *peaks at*: the run
never completes, so 32.0 GB is where it died and not what it needs — a
distinction that only became measurable once the cost came down (see the
2026-09-19 note below, where the same run reaches 38.67 GB before dying). Three
measurements say where not to look:

* **Not the drive cycle.** This step LOWERED that run's peak from 34.4 GB and
  halved its wall clock, 233 s to 115 s.
* **Not the source-bin padding.** Peak is flat as `n_sourceBin` goes 8 → 4 → 2
  (32.0, 32.0, 33.2 GB) and drops only at 1 (24.3 GB), which is a smaller
  relation and not a smaller pad.
* **Not width per se.** `expand-fueltype-diesel` peaks at 24.6 GB and runs.

So the ceiling sits above 24.6 GB, which `expand-fueltype-diesel` reaches and
survives, and nothing in either document can move it. **The cause is upstream and is now measured**, F58 /
[EarthSciAST#418](https://github.com/EarthSciML/EarthSciAST/issues/418).

Two observations found it without a profiler, `esm performance-profile` having
turned out to report parse time only. First, summing every variable's declared
shape over this run's resolved extents gives **0.31 GiB** of arrays across all
462 variables — so ~32 GB is transient join machinery and not stored results.
Second, an RSS timeline of the run that DOES fit (`expand-fueltype-diesel`,
23.56 GB, sampling `/proc/<pid>/status` every second) is three steps of ~4.2 GB,
each followed by a plateau of exactly 21 s at a bit-flat value, and nothing
released between them:

```
t=19   +4.7 GB →  5.8     t=52  +4.3 GB → 13.43  ── 21 s flat
t=75   +4.0 GB → 15.94    t=111 +4.2 GB → 23.56  ── 21 s flat
```

A peak that is the SUM of three retained intermediates, each live for 21
seconds and resident for the remaining two minutes, is a cache with no
eviction — and `EQ_GATE_CACHE` is exactly that. A join-gated `faq` retains
~80 bytes per candidate pair and ~78 per fact-table row, because
`OverlapIndex` stores the match set four times over. `n_sourceBin` moving the
peak barely at all now makes sense: it changes `sourcebin_rows`, and what the
gate charges for is the number of MATCHES, which the four-column self-join
narrows either way.

`docs/findings/F58_a_join_gate_retains_its_match_set.esm` is the minimal case,
four metaparameters that separate the two terms, and
`tools/check-join-gate-memory.py` gates it so the finding retires itself when
the fix lands.

#### 2026-09-19: PR #420 is a 3x win and still does not unblock this run

[EarthSciAST#420](https://github.com/EarthSciML/EarthSciAST/pull/420) fixes
#418 — the index holds its pairs in two columns instead of four copies, and
both gate caches get a resident-pair budget. Built at its head `e70af2590` and
measured against the pinned `8ac536bf0`, on this model and not on the MWE:

| run | peak, pinned | peak, #420 | wall, pinned | wall, #420 |
|---|---|---|---|---|
| `process-tirewear` | 6.56 GB | **2.26 GB** | 33.1 s | **11.5 s** |
| `expand-fueltype-diesel` | 23.58 GB | **7.91 GB** | 129.2 s | **31.8 s** |

**Three times the memory and three to four times the wall clock, with the
emitted relation BYTE-IDENTICAL on both runs.** That is much better than the
MWE predicted (80 → 32 bytes a pair, a 2.4x cut), because the model's gates
are large enough that the eviction budget matters as well as the layout.

**`expand-sourcetype` still does not run.** An RSS timeline shows the budget
working — two build-and-evict cycles, the second releasing 13 GB at t=171 s —
and then a plateau at **38.67 GB held flat for 70 seconds** before the kernel
kills it. Flat, not climbing: the run needs about 38.7 GB of anonymous memory
plus page cache, against a 40 GB cap. It is now *just* over rather than three
times over, and the honest reading is that **the 32.0 GB recorded above was
never its peak** — it was where the old binary happened to die, and a cheaper
gate simply got further before hitting the same wall.

So: #420 is worth taking on its own merits and is not what unblocks this run.
What would is a larger allocation, which now needs only ~48 GB, or the term
#420 deliberately leaves standing plus one model change — `sourcebin_rows` as a
densely ranked subset rather than a padded `cohort × n_sourceBin` grid
(conventions §64.2), since the padded bins all agree with each other on
`bin_usedFraction`'s four-column self-join and so pair up quadratically. That
hypothesis was dropped when the `n_sourceBin` sweep did not move the peak; at
32 bytes a pair it is worth re-measuring.

### 7.3.8 7d, 2026-09-19: the toolchain fix lands, and the corpus runs in under a gigabyte

§7.3.7 left `expand-sourcetype` unrunnable and named the cause as upstream.
Both halves are now merged and the pin has moved to them
(`esm-version.lock`: `f22139eb1`).

* **[#420](https://github.com/EarthSciML/EarthSciAST/pull/420)** — the gate
  index holds its pairs once instead of four times, and both gate caches get a
  resident-pair budget. 80 bytes a candidate pair to 32.
* **[#423](https://github.com/EarthSciML/EarthSciAST/pull/423)** — a gate is
  PRICED before it is built, and one that would materialise more pairs than the
  tuples it could prune is declined. `resolve_join_gates` used to build an index
  for every clause and consult §5.24's selectivity estimate only afterwards, so
  `bin_usedFraction`'s two fuel-type clauses — **166,861,800 pairs each**, a
  six-valued key against the 1,424,430-row national `fuelusagefraction` table —
  were materialised even though a sibling clause cuts that table to single
  digits. They are now declined, and the model's own `filter` applies the
  equality over a space the county clause has already made small.

**Every RunSpec in this tree now evaluates in under 1 GB**, against 6.6 to 38.7
before, and the four that reproduced still reproduce to the digit:

| run | peak, `8ac536bf0` | peak, `f22139eb1` | worst cell |
|---|---|---|---|
| `process-tirewear` | 6.56 GB / 36.9 s | **0.48 GB / 7.3 s** | 8.128e-06 |
| `expand-day` | — | **0.48 GB / 7.3 s** | 7.106e-06 |
| `expand-counties` | — | **0.48 GB / 7.8 s** | 1.140e-05 |
| `expand-fueltype-diesel` | 23.62 GB / 124 s | **0.53 GB / 11.2 s** | 7.372e-06 |
| `expand-sourcetype` | killed at 32 GB | **0.89 GB / 91 s** | see below |

That is the order `../moves.rs` runs the same simulations in, which is the
standard this port should have been held to: a 40 GB allocation was never the
answer, and asking for one would have hidden a 39x defect.

#### `expand-sourcetype` runs, and is 427 of 430

Its per-pollutant total is exact at **3.890e-07** and 427 cells are inside the
2e-05 tolerance. Three are not, and they are one thing: **source type 51
(refuse truck), fuel type 9 (electricity), model years 2017-2019, all high by
exactly 2.623x.**

What that is NOT, each checked rather than assumed:

* **Not the physics-row match.** No (sourceTypeID, regClassID, modelYearID)
  triple in `sourceusetypephysics` is covered by more than one row, anywhere in
  the table, so `rt_physicsOrdinal` is picking a unique vehicle and its
  `sum_product` is not summing two ordinals the way §63.2's key columns did.
  `run_rateRowsWithoutPhysics` is 0.
* **Not the EV efficiency.** `evefficiency`'s battery and charging factors are
  identical across all four of source type 51's regulatory classes, so they
  cannot produce a per-regClass ratio.
* **Not a bin-selection error.** The cohort has exactly ONE bin with a non-zero
  `stmyFraction` — regClass 47, engTech 30 — of the 17 the model year carries,
  and `run_sourceBinsDropped` is 0.

A constant ratio on one (source type, fuel type) pair, identical across three
model years, is the signature this step has met four times already
(§60, §61, §62, §63): a key that is plural in the data and singular in the
model. **It was read as the fifth, and it was not** — it was a whole table the
model did not read. §7.3.9 has it, and the three bullets above kept their value
anyway: each one that was ruled out is a factor this run now certifies.

#### What the pin move cost: F59, and one red test

Moving to `f22139eb1` turned the suite red, and what it found was filed as
[#431](https://github.com/EarthSciML/EarthSciAST/issues/431) / finding F59:
**a variable with no `shape` reads as NaN inside a `faq`.** The scalar itself is
right when observed directly; every aggregate that reads it is NaN, with no
refusal and no warning.

**It was reported here as a regression and it is not one — that was my error,
and the correction is the useful part.** The claim rested on this suite being
green at `8ac536bf0`, and this suite runs `esm test`. Building `8ac536bf0` and
running `esm simulate` on the same document answers NaN there too, as does
every commit tested. #412 gave the inline-test runner a retry that builds a
state-free document through the build pipeline, so `esm test` began reaching a
path it had never taken; it exposed the defect rather than causing it. **A green
suite is evidence about the paths the suite takes**, and `esm simulate` on a
scalar-in-`faq` was not one of them. The distinction decided the fix: restoring
`8ac536bf0`'s behaviour would have patched the test runner and left `simulate`
broken.

`components/tank_temperature.esm` takes a scalar as a bare template operand, so
its quarter-hourly recurrence is NaN throughout and **41 assertions fail**. That
is the suite's only red, and the honest reading is that it understates the
problem: this repository has **65 unshaped `unknown`s across 12 components**, and
the reason only one went red is F47 — a mounted component's inline tests are not
run, so a component that is only ever mounted cannot fail this way however many
of its aggregates are NaN. Every fixture and oracle is still green, which says
the mounted paths are fine; it is not evidence, because the tests that would say
so do not run.

**A length-1 axis would have worked around it and was deliberately not spent**,
because [#433](https://github.com/EarthSciML/EarthSciAST/pull/433) fixes it
upstream instead: a build-time field's rank now comes from its declaration, so an
unshaped variable materializes at `IxDyn(&[])`. **Merged 2026-09-19**, along with
[#434](https://github.com/EarthSciML/EarthSciAST/pull/434), and the pin moves
again to `3cf6f6f92`. F59 is retired.

**The inline-test stage is now 878 pass / 0 fail**, over `components`, `lib` and
`runspecs`. It was 723 / 155 on the pin that found this, 831 / 47 with #433
alone, and #434 closed the rest. So the scalar defect was costing this
repository **155 assertions across eight documents**, silently, for longer than
anyone had looked — and the reason nobody had looked is the one worth keeping:
the suite's own inline-test stage was green at the pin before, because a
state-free document never reached the path that was broken.

### 7.3.9 7d, 2026-09-20: the last three cells were a table the model did not read

`expand-sourcetype` reproduces. **430 of 430 cells, worst cell 9.017e-06 against
a 2e-05 tolerance**, worst per-pollutant `emissionQuant` sum 1.074e-07, in 91
seconds and 0.89 GB — unchanged from §7.3.8, because the fix is one factor and
not a shape. The document moved out of `runspecs/pending/`, which is now empty,
and `runspecs/` holds five RunSpecs that all reproduce their runs.

**What the 3.622713 was.** `emissionRateAdjustment`, applied at
`baseratecalculator/adjust.rs:586-603`, multiplies the rate by a factor keyed on
(pollutant-process, source type, **regulatory class**, fuel type, model-year
range), after the temperature and A/C steps and before the EV efficiency
divisor. The national
table has 1131 rows. Row `9101 / 51 / 47 / 9 / 1950-2020` holds **0.276035**,
and `1 / 0.276035 = 3.622713`, which is the ratio all three cells carried to six
digits. Ported as **J56** (`rt_emissionRateAdjustment`, conventions' J-numbering;
docs/mixed-onroad.md §2.3(g) and the join catalogue), with the existence half
spelled the way J25's is: a `bool_and_or` companion, so a rate row the table does
not name is multiplied by 1 rather than by the `sum_product` identity of 0.

**Why four RunSpecs passed over a table nobody read.** Of the 1131 rows, 26 carry
a factor that is not 1 at a model year this corpus runs, and **every one of the
26 is heavy-duty electric running energy** — source types 41, 42, 43, 51, 52, 53,
54, 61, 62 at fuel type 9. `process-tirewear`, `expand-day` and `expand-counties`
are source type 21; `expand-fueltype-diesel` is 21 and 32. Not one of their
cohorts could reach a row. The execution databases say the same thing more
sharply: the `expand-day` and `process-tirewear` snapshots carry **0 rows** of
`emissionrateadjustment`, and the `expand-sourcetype` snapshot carries **241**.

**The wrong inference this corrects, and it was written down.**
docs/mixed-onroad.md §2.3(c) listed the step as *flag false in production*. That
came from `moves.rs`, where `ModuleFlags::emission_rate_adjustment` is never set
outside tests — the same gating that left `ev_efficiency` off until `moves.rs`
`30dc3d28` fixed that one on 2026-09-10 — and it was never a measurement of
canonical MOVES. Canonical applies the section, and the oracle says so in three
cells. The .esm already followed canonical rather than `moves.rs` on the EV
divisor, for exactly this reason, and did not on this one because no run had yet
been able to tell.

**`moves.rs` cannot see it either, and its own gate cannot.**
`full_suite_regression.rs` scores `expand-sourcetype` per POLLUTANT, at a
recorded residual of ~1.3e-4. The three cells sum to 2.25e-04 of excess against
a pollutant total of 799.5 — **2.8e-07 relative**, three orders of magnitude under
that fixture's own noise. A per-cell comparison against the run's own
`MOVESOutput` is the only thing in either repository that could have found this,
and `compare-output.py` is it. Filed as [moves.rs#68](https://github.com/EarthSciML/moves.rs/issues/68).

**What the three rejected explanations bought.** §7.3.8's list — not the
physics-row match, not the EV efficiency, not a bin selection — read at the time
as three dead ends. They are three certifications: `run_rateRowsWithoutPhysics`
is 0 and no `(sourceTypeID, regClassID, modelYearID)` triple is double-covered,
the EV factors are per-regClass-identical, and the cohort's one non-zero
`stmyFraction` bin is the one the rates come from. Every one of those had to be
true for a *factor* to be the remaining explanation, which is what made a
single constant the thing to look for.

### 7.3.10 7d, 2026-09-20: the month is an axis, and it was the run's last scalar

`run_monthID` was a `run_rows` scalar — a `faq` that summed `rsm_monthID` over
`runspecmonth_rows` and landed the total on the one-row carrier relation. At one
selected month a sum of one IS that month, and every RunSpec in the tree selects
one, so nothing had ever told the model otherwise. That is §59's shape for the
fourth time (conventions §65), after the day, the county and the source type.

**26 of 472 variables gained the axis, three were added to carry it, and 446 did
not.** Four of the 26 are a rebind rather than a promotion: `run_monthID`,
`run_monthGroupID`, `run_daysInMonth` and `run_weeksPerMonth` were already faqs
over `runspecmonth_rows` collapsed onto `run_rows`, so the change is to stop
collapsing. The rest divide cleanly in two — the meteorology half
(`ZoneMonthHour` is month-keyed, so `run_temperature`, `run_heatIndex`, the A/C
quadratic and the EV temperature factor follow it) and the activity half
(`MonthVMTFraction`, and `DayVMTFraction` which is keyed by month AND day).
`act_hourVMTFraction` is the line worth reading: `HourVMTFraction` carries no
month, so it did not move, while `act_dayVMTFraction` immediately beside it did.

The output relation is five levels now —
`n_outputPolProcess × n_runspeccounty × n_runspecmonth × n_runspecday ×
n_outputCohort` — and four columns plus `out_monthID` gained the
`outMonthOrdinal ↔ month_ordinal` key pair. `out_meanBaseRate` did NOT, because
an unadjusted base rate does not vary with the month; the join replicates it
across the four blocks.

**All five RunSpecs in `runspecs/` reproduce unchanged to the digit** — 8.128e-06,
7.106e-06, 1.140e-05, 7.372e-06 and 9.017e-06 — which is §64.5's rule a second
time: an axis whose default width is 1 is a refactor the existing corpus cannot
see.

### 7.3.11 What `aggregateBy = Month` actually costs, measured before it is built

The axis is the cheap half. `expand-month` sets `aggregateBy = Month`, and
canonical MOVES answers that by REWRITING six input tables before the rate
calculation runs, to a single `(hourDayID, dayID, hourID) = (0, 0, 0)` cell that
the default database does not ship. `HourDay`, `HourOfAnyDay` and `DayOfAnyWeek`
become one row each — the last of them `(0, "Whole Week", 7.0)`;
`HourVMTFraction` and `DayVMTFraction` become 1.0; and `AvgSpeedDistribution`,
`ZoneMonthHour` and `MonthGroupHour` are collapsed by weighted average. That is a
GENERATOR in the sense conventions §35.1 fixed for `MeteorologyGenerator` and
`FuelEffectsGenerator` — a table the default database does not ship because it
is a result. §7.3.12 is what it turned out to cost once both weights were in
hand, and it is less than this section expected: not a component beside the
model but a per-run SELECTION inside it.

**Both weights were reproduced from the default database before any of it was
written**, which is what makes the next step a translation rather than a search.

| collapsed table | weight | worst relative error over the snapshot's own cells |
|---|---|---|
| `AvgSpeedDistribution`, 64 cells | `hourVMTFraction(st,rt,day,hour) × DayWeighting1(st,rt,day)`, where `DayWeighting1 = Σ_month dayVMTFraction·noOfRealDays·monthVMTFraction / Σ_month monthVMTFraction` | **4.5e-06** |
| `ZoneMonthHour` temperature and relative humidity, 4 months | `HW2(st,day,hour) = Σ_rt hourVMTFraction·roadTypeVMTFraction / Σ_rt roadTypeVMTFraction` | **2.7e-10** |

Both numbers are the snapshot column's own stored precision, so both are exact.

**THE WEIGHT IS SCOPED TO THE RUN'S SELECTED DAY, AND THAT IS THE ONE THING THE
EXECUTION DATABASE NO LONGER SAYS.** Averaging the met columns over both day
types instead of over day 5 alone gives 1.6e-02, four thousand times the storage
precision; the same substitution in `AvgSpeedDistribution` gives 6.3e-02. The
RunSpec XML selects `day id="5"`, `moves.rs` never has to look it up because
`InputDataManager` filters `HourVMTFraction` and `DayOfAnyWeek` by `dayID`
during extraction (`input_data_manager.rs:1283-1291`) — and the captured
`runspecday` says `0`, because MOVES collapsed it after the pre-aggregation ran.
**A per-fixture document reads its selections out of the snapshot's own
`runspec*` tables, and for this one fixture one of those selections has been
overwritten by a result.** That is a question about provenance rather than about
arithmetic, and §7.3.12 answers it the only way that keeps the measurement:
`tools/runspec-day-selection.py` reads the day out of the RunSpec XML, and
moves.rs#69 asks the capture to carry the parsed selections so the script can go
away.

Three smaller findings from the same measurement:

* **`MonthGroupHour`'s collapse is a no-op.** `ACActivityTermA/B/C` are constant
  across the 24 hours for every month group in the default database, so the
  HW3-weighted average returns them unchanged — which the snapshot confirms
  (−3.63154, 0.072465, −0.000276 at hour 0, the same triple every hour carries).
  The collapse still has to happen, because the A/C factor joins
  `ZoneMonthHour.hourID` to `MonthGroupHour.hourID` and both sides must land on
  hour 0 together.
* **`heatIndex`, `specificHumidity` and `molWaterFraction` are NULL in the
  default database** and computed by `MeteorologyGenerator`, which this
  repository already ports. So they are computed AFTER the collapse, from the
  collapsed temperature and humidity — and the snapshot's `heatIndex` equals its
  `temperature` exactly in all four months, which is what that port already gives
  below the heat-index threshold.
* **The activity side is not a collapse but a literal**, and the literal is a
  sum: `dayVMTFraction := 1` is `Σ_day dayVMTFraction`, which is exactly 1.0 in
  the default database; `noOfRealDays := 7` is `Σ_day noOfRealDays` over the two
  day types; and `hourVMTFraction := 1` is `Σ_hour hourVMTFraction`, which is 1
  to 2.2e-07. So the whole-month activity is the full week at full hours, and the
  run's day selection — which scopes the RATE side — does not scope it.

### 7.3.12 7d, 2026-09-20: `expand-month` reproduces, and the second mode was a selection

**500 of 500 cells, worst cell 8.513e-06 against a 2e-05 tolerance**, worst
per-pollutant `emissionQuant` sum 6.386e-07, in 8.6 seconds and 0.51 GB — the
cheapest run in `runspecs/` after `process-tirewear`. **It reproduced on its
first run**, and every other document in that directory went through `pending/`
first. §7.3.11's measurements are why: both weights were reproduced from the
default database against the snapshot's own collapsed tables before a line of
the model changed, so the port was a translation instead of a search.

**§7.3.11 predicted a component and was wrong, and the correction is the
result.** `aggregateBy = Month` is not a generator beside the model and not a
second mode inside it. It is three more lists a RunSpec declares — which day
types its RATE tables are averaged over, which its ACTIVITY covers, and which
hours — and a model that reads `avgSpeedDistribution` and `zoneMonthHour` as
weighted means over the resulting time cells instead of as lookups. **A mean
over one cell is that cell**, so the five runs that do not aggregate are the
degenerate case and reproduce unchanged to the digit with nine new relations
between them and the table. Conventions §66 has the whole shape; three things
from it are worth having here:

* **`DayWeighting1` cancels.** Canonical's speed-distribution weight is
  `hourVMTFraction × DayWeighting1(sourceType, roadType, day)`, and every output
  day of every run in this corpus aggregates over ONE day type — so a factor
  keyed on the day type is constant across the cells it is averaged over. With
  it and without it the collapsed `AvgSpeedDistribution` reproduces at the same
  4.5e-06. Four relations that no measurement in the tree could have seen.
* **The literals are sums.** `dayVMTFraction := 1`, `hourVMTFraction := 1` and
  `noOfRealDays := 7` are what canonical writes; `Σ_day dayVMTFraction` is exactly
  1.0, `Σ_hour hourVMTFraction` is 1 to 2.2e-07, and `Σ_day noOfRealDays` over the
  week's two day types is 7. Writing the sums is what makes the one-cell case
  fall out rather than be assumed, and it is why `noOfRealDays` comes out 7 on a
  run that selected weekdays without 7 appearing anywhere the model reads.
* **`zmh_heatIndex` is retired.** The heat index was computed per
  `zoneMonthHour` row and looked up; it is now computed from the COLLAPSED
  temperature and humidity, which is what canonical does. The two orders differ
  whenever a run aggregates across the 78 °F threshold, and averaging a branch is
  the wrong one. `act_dayID` went with it, unreferenced.

**What is declared rather than derived, and what was filed for it.**
`db_rateday` is the only source in `runspecs/` that points neither at its own
snapshot nor at the default database, because MOVES overwrote `RunSpecDay` after
the pre-aggregation ran. `tools/runspec-day-selection.py` reads `day id="5"` out
of `characterization/fixtures/expand-month.xml`. It is not a formality: the
probe that points `db_rateday` at `db_actday`'s file instead puts **all 500
cells over the per-cell gate at a worst 2.403e-02**, and the per-pollutant sum
at 6.890e-03 against a 1e-3 gate. Filed as
[moves.rs#69](https://github.com/EarthSciML/moves.rs/issues/69) — the capture
already holds the XML and records its sha256, so a snapshot can be
self-describing about what was ASKED for as well as about what MOVES computed.

`runspecs/` now holds **six** RunSpecs, all reproducing, and `runspecs/pending/`
is still empty. What is left of 7d is the criteria pollutants.

### 7.3.13 7d, 2026-09-20: the criteria pollutants are in the OTHER rate table, and what is left is one factor

`expand-criteria` — THC, CO and NOx running exhaust, otherwise
`process-tirewear`'s geometry exactly — is back in `runspecs/pending/`, and this
section is the measurement that says what it waits on. The chain now computes
every part of the run **except one multiplicative factor**, and that factor is
identified rather than guessed at.

**The first finding is that the chain had been reading one of two rate tables.**
MOVES has `emissionRate` and `emissionRateByAge`, and they are **disjoint in
`polProcessID`**: running energy, tire wear and brake wear are in the first,
THC/CO/NOx running exhaust in the second, which carries an `ageGroupID` key and
1,590,830 rows against 105,449. Every RunSpec in this tree until now read the
first and nothing else, so the criteria run returned zero for all 375 cells
before a line changed. `rtMode_rate` now SELECTS between the two arms on
`rt_hasRateByAge` rather than summing them (conventions §67.1), and the
selection is what makes the disjointness a claim the document makes.

**The cohort count fell out of it.** `expand-criteria` emits **124** cohorts,
not the 125 every other run in `runspecs/` emits: the model year 2000
ELECTRICITY cohort has no `emissionRateByAge` row at its age group, so it is not
rated and not emitted, while 2001–2020 of the same fuel are rated at zero and
are. No rule was written for that; adding the sixth key pair moved
`cohortSurvivorCount` from 125 to 124 on the first run. It is the first time in
this port that the RATE table decided the SHAPE of the answer.

**Then the residual was measured before anything else was ported**, which is
§7.3.11's method applied a second time. With J58 read and nothing else changed,
the ratio of emitted to expected `emissionQuant` was piecewise-constant in model
year and nearly equal across pollutants — the signature of a fuel-effect factor,
not of a missing physical term. Taking it to the snapshot's own tables:

```
missing factor  =  criteriaRatio(fuelType, formulation, polProcess,
                                 sourceType, modelYear, ageID)
                 × noxHumidityAdjust(fuelType)
```

**worst 7e-06 across all three pollutants, all three fuel types and all 124
cohorts.** That single line is what says three other ports are NOT needed:
`temperatureAdjustment` contributes exactly 1 here (its only rows for these
pollutant-processes are model years 2027 and later), `IMCoverage` is **empty**
so the entire inspection-and-maintenance blend is inactive, and
`emissionRateAdjustment` is empty too. Twenty minutes of pandas, against writing
three adjustments and watching the number not move.

**The humidity half is built and the residual is now exactly `criteriaRatio`.**
`noxhumidityadjust` carries two different formulae in one table — CFR 86, linear
in bounded specific humidity, for gasoline and E85; CFR 1065, reciprocal in
bounded water mole fraction, for diesel — and this run exercises both, at
1.0215928 and 1.0095484. The chain computes both humidity measures from the
temperature and relative humidity it already computes, rather than reading
`ZoneMonthHour` as the fixtures do, and lands them at 2.298e-08 and 2.262e-08
against the columns MOVES stored. With that applied, the leftover is
`criteriaRatio` and nothing else, at a worst of **8e-06** (conventions §67.4,
§67.5). The general temperature factor arrived with it — the NOx branch and the
fall-through quadratic beside the EV branch that was all this chain had — and
**all six existing RunSpecs are unchanged to the digit**, because the only
`temperatureadjustment` rows in the national table are for pollutant-processes
none of them reach.

**What is left is `criteriaRatio`, and it is a generator.** The table is
**empty in the default database**: MOVES's `FuelEffectsGenerator` computes all
4,398 rows at run time, from the EPA Complex Model
(`complexModelParameters` polynomials over fuel properties, then the sulfur
model) for MY ≤ 2000 gasoline, and from `generalFuelRatioExpression` for
everything else. `components/fuel_effects.esm` already evaluates the second half
— including the sulfur form — so the port is the Complex Model plus the sulfur
model, `moves.rs`'s `fueleffectsgenerator/criteria.rs`, verified there as
`ratio = ratioNoSulfur × sulfEff`. On this run the factor ranges from **0.501 to
1.044**, so it is not optional: NOx gasoline MY 2001–2016 is a factor of two.

**An upstream footgun, filed.** The `emissionRateByAge` relation was first
written with the prefix `era_`, which an existing `emissionRateAdjustment`
relation already owned. The document validated and simulated; six of J58's seven
key pairs bound and the `polProcessID` pair was **silently dropped**, because
its right-hand side resolved to a column over an index set the aggregate has no
range for and EarthSciAST treats that as a positional no-op. The contraction
summed every pollutant-process at each source bin and returned plausible
numbers. The tell was that THC and NOx came back identical to fifteen digits.
Filed as
[EarthSciAST #437](https://github.com/EarthSciML/EarthSciAST/issues/437) —
the left side of a key pair already refuses this, the right side does not.
Conventions §67.3 has the local rule that does not wait on the fix.

### 7.3.14 7d, 2026-09-20: the criteria ratio is two generators in one table, and one of them is a parse

`criteriaRatio` is the single factor §7.3.13 left, and the first thing worth
recording about it is that **MOVES computes it two different ways and the table
does not say which**. All 4,398 rows carry the same three columns. For model
years 2001 and later, and for diesel at every model year, the number comes from
evaluating a closed-form expression the default database ships as SQL text in
`generalFuelRatioExpression`. For gasoline model years 2000 and earlier it comes
from running the **EPA Complex Model** live — `complexModelParameters`
polynomials over centred fuel properties, weighted across fuel models, then the
sulfur model out of `sulfurModelCoeff`. Splitting the work along that seam is
what made the first half a day's work instead of a week's.

**The first half is ported and the measurement is exact about what it bought.**
`expand-criteria` goes from 372 wrong cells to **63**, and those 63 are precisely
the gasoline cohorts of model years 1980–2000 on all three pollutants — the
Complex Model's half, to the row. The other **309 land at a worst 7.804e-06**,
which is the residual every other RunSpec in `runspecs/` already carries. All six
RunSpecs that reproduce are **unchanged to the digit** (8.128e-06 for
`process-tirewear`, 7.372e-06 for `expand-fueltype-diesel`, and so on): the
criteria rows are keyed on pollutant-processes 101, 201 and 301, and no other run
in the tree emits one.

**The form/coefficient split is conventions §24's rule, and it was measured
rather than assumed.** The 135 rows of `generalFuelRatioExpression` whose
`polProcessID` is 101, 201 or 301 hold 102 distinct expression strings. Parsed,
they collapse to **two top-level forms and five term sets**: `sulfur_switch_ratio`
over a six-term polynomial for gasoline and ethanol, `biodiesel_ester_ratio` for
diesel, and the only difference between the gasoline and ethanol term sets is the
`least(10, ETOHVolume)` clamp `standardized_term` already carries. Both forms were
already in `lib/fuel_effects.esm`, written for `components/fuel_effects.esm` and
never before reached from the chain; what this rung added there is
`criteria_exponent`, which spells the six terms once.

**What the coefficients could not be read from.** Every one of the intercepts,
the six polynomial coefficients, the base divisors, the GPA factors and the
low-sulfur slopes was searched for across all 237 tables of the default database.
Not one appears. `sulfurModelCoeff.sulfurCoeff` does carry the sulfur powers
(0.168, 0.236, 0.351 at source type 21) and `m6SulfurCoeff.sulfurLongCoeff` the
multipliers (2.5, 2.36, 1.47), which is a corroboration and not a source: the
table is also keyed by a model-year group the string does not record, so the
string stays the authority. The 135 coefficient rows are therefore data in
`onroad/model.esm`, and the extraction is checked twice — against an independent
parse and evaluation of all 135 strings over all 2,158 formulations (**165,297
cells, worst 1.4e-14**), and against the snapshot's own captured `criteriaRatio`
for all **2,013** of its rows the closed form covers (**worst 4.4e-08**, which is
the binary32 column question of docs/fuel-effects-generator.md §7.2 and not a
modelling residual).

**`sourceTypeID` is a real key here, and that is the reason the relation is 135
rows and not 15.** The sulfur power is 0.168 for source types 11 and 21 and 0.125
for the other eleven; the low-sulfur slope takes three values across them and is
zero for a motorcycle; the Tier 3 model-year boundary is 2016/2017 for most source
types and 2017/2018 for 31 and 32. Six of this repository's seven RunSpecs select
source type 21 alone — a relation that carried only it would have been right on
all six and wrong on `expand-sourcetype`, which is the shape
`width-one-hides-a-key` warns about.

**The finding that could only be made from the default database.** The default
`FuelFormulation` ships the E85 formulation 27002 with **distillation sentinels**
— `T50` 999, `T90` 999, `ETOHVolume` 74 — and the THC criteria polynomial carries
`5.58244506624426e-05 * T50 * T50`. Read straight, that returns a fuel-effect
ratio of **1.0e+17** instead of 0.645. `FuelEffectsGenerator.setup()` step 020,
`alterHighEthanolFuelProperties`, overwrites every combustion property of a
subtype-51 or -52 formulation from `e10FuelProperties` at the formulation's own
(fuel region, fuel year, month group) — keeping only its RVP — before any
fuel-effect arithmetic runs. **The snapshot corpus cannot show this at all**:
every captured `fuelformulation` table in it is the EXECUTION copy, with the
substitution already applied, which is why `components/fuel_effects.esm` could
carry five formulations as literals and never meet it. It is visible only from
the default database, which is what this rung of the plan exists to read. The
port reaches 7.15 ppm, 10 % ethanol, 23.14 % aromatics, T50 222.95 and T90 327.77
for 27002 in region 270000000 in August 2020 — the execution copy's numbers
exactly — and the E85 cells then land inside tolerance.

**Nulls became real for the first time.** `components/fuel_effects.esm` calls
`changeFuelFormulationNulls` "a no-op against a relation whose columns are
concrete", and it is, there. Against the national table it is not: 2,118 of 2,158
rows have a NULL `BioDieselEsterVolume`, and a NULL reaches an `.esm` as a NaN
that no market-share weight can multiply away. `fuel_property_or_zero` is that
sweep, spelled with the `value == value` NaN test `in_half_open_range` already
uses. The same care decides the filler values on the unused arm of every form
selection: a diesel row carries sulfur power **1 and not 0**, because at power 0
a formulation whose sulfur level is 0 would make `exp(0 * log(0))` a NaN rather
than a 1 — and two of the 2,158 formulations have sulfur level 0.

**What is left, which is one generator and 63 cells.** The EPA Complex Model plus
the sulfur model, `moves.rs`'s `fueleffectsgenerator/criteria.rs`, reproduced in
pandas from the default database at **≤2.1e-09 for all six criteria
pollutant-processes** before any of this was written (§7.3.13). Two things about
it are already known and neither is in the shipped table text: the coefficient is
`coeff1 + coeff2 + coeff3`, and the `complexModelParameterName.cmpExpression`
strings omit the `stdDev` division MOVES actually applies. It is eight more
tables and no new algebra that is not already in `lib/fuel_effects.esm`.

**And a gap that is named rather than guarded.** The other 135 rows of
`generalFuelRatioExpression` — pollutant-processes 102, 202 and 302, START
exhaust — carry **cross terms** (`ETOHVolume*T50`, `ETOHVolume*T90`,
`ETOHVolume*RVP`, `ETOHVolume*aromaticContent`) that `standardized_term` cannot
spell, because it raises one property to a power. A start-exhaust rung needs a
`standardized_cross_term` beside it. No RunSpec in this repository selects process
2, so no rate row can reach a missing coefficient set; the day one does,
`rt_hasCriteriaRatio` returns 0 and the cohort is scaled by 1. That is the one
silent failure in the block, and it is written down in three places rather than
guarded, because the guard would need a data source read for nothing else.

### 7.3.15 7d, 2026-09-20: the other half of the criteria ratio, and the shape rule that was hiding behind a binding

`runspecs/expand-criteria.esm` reproduces: **372 of 372 cells, worst 7.805e-06**,
key set exact, and it has moved out of `runspecs/pending/`, which is empty again.
All six RunSpecs that already reproduced are **unchanged to the digit**. This
section is the second half of §7.3.14 and the rule that came with it.

**The EPA Complex Model, ported relationally.** Six new national tables
(`complexModelParameters`, `meanFuelParameters`, `fuelModelWtFactor`, `baseFuel`,
`sulfurModelCoeff`, `sulfurModelName`), four small constant relations and
J66–J76. The algebra is `ratio = ratioNoSulfur × sulfEff`, and the pieces that
mattered:

* **`coeff1 + coeff2 + coeff3`.** Three columns summed, not three alternatives.
* **The standardising divisor is applied and the table's own expression does not
  mention it.** `meanFuelParameters.stdDevValue` is genuinely ≠ 1 for THC and NOx,
  and the `complexModelParameterName.cmpExpression` text omits the division.
  `criteria.rs` applies it; so does this document; the table is incomplete
  relative to what MOVES computes, and that is now written down where a reader of
  the table will meet it.
* **Two nulls in one row that mean different things.** A NULL `centeringValue` is
  *no centring*, which is 0; a NULL `stdDevValue` is *no standardising*, which is
  1. Every CO row is NULL in the second and not in the first.
* **The fuel-model membership is not derivable, and that is measured.**
  `fuelModelName.calculationEngines` is a pipe-delimited SET (`|airtoxicsA|co||`)
  and no `codes` map decodes a set, so the 19 (engine, fuel model) pairs are data.
  Taking them from `complexModelParameters` instead looks equivalent and is not:
  fuel model 11, `All Tier2`, has non-zero CO coefficients and belongs to NO
  engine, so CO would be averaged over eleven models instead of ten.
* **The weight fallback is the ordinary path.** `fuelModelWtFactor` carries 410
  rows at model-year group 19502000 for the ten CO fuel models and **none** for
  the nine predictive ones, which take the uniform group 0.
* **The sulfur model's group range is encoded in its own identifier** —
  `19972000` is 1997 to 2000 — so the two bounds are decoded arithmetically, and
  the 50/50 blend of the Normal and High emitter classes is the *contraction* over
  `M6emitterID` rather than a second expression.

**One wrong turn, and it is the reusable part of this section.** The first run
with the Complex Model in place moved the 63 cells from 16 % wrong to 2 % wrong,
which reads like progress and was not: the polynomial was returning **zero
everywhere**, `exp(0)` is 1, and a weighted ratio of ones is exactly 1, so the
sulfur half was doing all the work alone. The cause was an
`exact_else_wildcard` whose flag is over the term axis and whose value is over
five axes — **broadcasting aligns by PREFIX, and this is not a prefix**. It
returned an array with **no elements**, silently. Conventions §68.6 has the shape
and the fix. The tell is an intermediate that is all zeros where its inputs are
not, and it is the opposite symptom to §67.3's dropped join key: a dropped key
gives an answer that is too WIDE, a failed broadcast one that is too NARROW.

**Then the shape rule, which the binding had been hiding.** With the numbers
right, `expand-criteria` still could not be promoted: run-tests.sh compares the
emitted shape against what the chain RECOMPUTES, and the chain said 4
pollutant-process blocks and 125 cohorts where MOVES emits 3 and 124. The
`n_outputCohort: 124` binding had made the key set exact — 372 of 372, none
missing, none extra — **by luck**: the relation is truncated to the declared
length, so it drops the LAST cohort, and the unrated one happened to rank last.

Both counts now multiply by one predicate: does any rate row of this cohort, or
of this pollutant-process, produce a number? The rate row's own ordinals are
already the keys into both relations, so J77 needed no new key. What it did need
was a distinction the measurement had not shown: the predicate is **not**
`rt_survives`. `process-tirewear` emits three blocks and two of them carry a rate
— PM2.5 tire wear is `runspecchainedto`'s output and has `rt_isSelected` 0 on
every one of its rows, because not having a `pollutantprocessmodelyear` row is
exactly what makes a pollutant-process chained. The predicate is a rate OR a
chain (conventions §69).

**What it cost.** Six more tables and a 6-D contraction over
(configuration × source type × age × county × month × formulation): the suite's
slowest run, `expand-sourcetype`, goes from 94 s and 1.53 GB to 170 s and
1.61 GB, and `process-tirewear` from 10 s to 30 s. The formulation axis is 2,158
rows wide and five of them are ever supplied, which is where most of that goes;
narrowing it needs a dynamic extent and is not worth a document change today.

**What is left in this dimension.** The other 135 rows of
`generalFuelRatioExpression` — pollutant-processes 102, 202 and 302, START
exhaust — still need a `standardized_cross_term`, and no RunSpec here selects
process 2. `altCriteriaRatio`, the E85 alternate-RVP path, is likewise unreached:
it needs the `altRVP` column that step 020 writes and only NMOG and VOC read it.

### 7.3.16 7d, 2026-09-20: brake wear was free, and a measurement pass prices the rest

`runspecs/process-brakewear.esm` reproduces — **375 of 375 cells, worst
8.251e-06**, key set exact — and it required **no change to the model at all**.
It was written by copying `runspecs/process-tirewear.esm`, swapping fourteen
`url_template`s, and running it. That is the first RunSpec in this directory
that cost nothing, and the thing worth recording is what it would have caught
anyway.

**The model-year group is 0 in every other run in this directory, and it is not
0 here.** `rt_modelYearGroupIsPresent` (J18, J19) is S10's two inner joins as
one semi-join: `pollutantprocessmodelyear` must carry the run's (polProcessID,
modelYearID) pair, and that pair's `modelYearGroupID` must itself be a
`modelyeargroup` row. For PM10 **tire** wear the group is `0` at all 41 model
years — and `0` is a `modelyeargroup` row, named *Doesn't Matter*, which is the
only reason the tire-wear path passes the test at all. For PM10 **brake** wear
it is six real groups, 19501980 through 20112020, short groups 1 to 6, chosen by
the model year. This is the first run in the corpus where that join has to find
something, and the first where a chained block's model-year group moves.

Brake wear is also a second process on the `emissionRate` arm J58 added (process
9, a disjoint set of rate rows from tire wear's process 10), and a second
chained pair — `runspecchainedto` says 10609 ← 11609 where tire wear says 10710
← 11710 — so J77's rule that a chained block carries no rate of its own and is
emitted anyway is exercised by a pair it was not written against.

#### What the rest costs, measured rather than guessed

Seven more onroad snapshots were then run the same way: build a throwaway probe
RunSpec from `process-tirewear.esm` with the `url_template`s swapped, let the
**chain** recompute the four declared shape numbers rather than reading them off
the answer, bind those, and compare against that run's own `MOVESOutput`. The
probes are deleted after; nothing here is checked in. (Not measured: the four
`chain-*` snapshots, which are the same question at twenty times the width; the
two other `process-evap-*`; the eight whose recorded `MOVESOutput` is EMPTY —
every APU, extended-idle, crankcase-start and crankcase-extended-idle run —
and `sample-runspec`, which ships no `MOVESOutput` at all; and `scale-project`,
which is step 7f because its input is a second database.)

| run | its rows | emitted | shared | worst on the shared cells | what is missing |
|---|---|---|---|---|---|
| `mixed-onroad` | 125 | 125 | 125 | 8.319e-06 | nothing |
| `process-brakewear` | 375 | 375 | 375 | 8.251e-06 | nothing — **promoted** |
| `process-nox-speciation` | 436 | 124 | 124 | 7.805e-06 | 3 x 104: NO, NO2, HONO |
| `process-crankcase-running` | 684 | 372 | 372 | 7.805e-06 | 3 x 104: the crankcase ratio |
| `process-airtoxics` | 644 | 124 | 124 | 7.564e-06 | 5 x 104: the air toxics |
| `process-pm-exhaust` | 728 | 375 | 312 | **1.000e+00** | 4 of its 7 blocks absent; the 3 it emits are 125 cohorts wide instead of 104 and their values are wrong |
| `process-refueling` | 168 | 125 | 0 | — | everything; the two runs have no block in common |
| `process-evap-permeation` | 64 | — | 0 | — | everything; the chain recomputes **no surviving block at all** |

The shape of that table is the finding. **Where a block is shared, it is exact
to the same 8e-06 the corpus already carries; what is missing is always the
CHAINED blocks, and they are 104 cohorts where the parent is 124.** Three
different calculators — `NOCalculator`/`NO2Calculator`, the crankcase ratio and
the air-toxics ratios — run into the same structural wall: `output_rows` is
declared as a strict product, `n_outputPolProcess × n_outputCohort ×
n_runspecday × n_runspecmonth × n_runspeccounty`, a rectangle over the blocks,
and a chained species survives only where its ratio exists **and its parent
survived**, which is 104 and not 124. One structural change is what
`process-nox-speciation` and `process-crankcase-running` are waiting on and
nothing else — 1,120 rows of MOVESOutput between them.

**And 104 is not a coincidence; it is a join.** The 20 cohorts a species block
drops, against its parent's 124, are **fuel type 9, model years 2001 to 2020** —
electricity, every one of them. `NONO2Ratio` and `CrankcaseEmissionRatio` each
carry fuel types 1, 2, 3 and 5 and no row for 9. So the chained block is the
parent's cohorts INTERSECTED with the ratio table's coverage, which is a join and
not a property of the parent, and it is the same 20 cohorts that `expand-criteria`
found are *rated at zero and emitted anyway* on the parent. The fixtures already
have the shape this needs: `docs/process-nox-speciation.md` §3.3 ranks the WHOLE
rate relation once and declares a single `n_outputRate`, because "124 + 104 x 3
and 109 x 4 are the same 436". `onroad/model.esm` still declares the rectangle.

**Two of them need more than the shape change, and saying so is the point of
measuring.** `process-airtoxics` reads `ATRatio`, which is **empty in the default
database** and carries 243 rows in that run's execution copy — another table
MOVES computes at run time, exactly like `criteriaRatio` (§7.3.14), so it is the
shape change *plus* a generator. And `process-pm-exhaust` is not the same gap at
all: four of its seven blocks are absent, the three it does emit (pollutants 100,
112 and 118) come out 125 cohorts wide instead of 104, and their values are
wrong — worst cell 1.000e+00, with 208 of 375 nonzero. It is a separate piece of
work and not a free ride behind the others.

`mixed-onroad` reproduces its 125 rows exactly and is **not** added to
`runspecs/`: its selections are a strict subset of `runspecs/expand-day.esm`'s,
so a document for it would discriminate nothing (§23) and cost the suite another
80 seconds.

### 7.3.17 7d, 2026-09-20: the output relation stops being a rectangle

`runspecs/process-nox-speciation.esm` and `runspecs/process-crankcase-running.esm`
reproduce — **436 of 436 at 9.485e-06** and **684 of 684 at 7.805e-06** — and
they are the first two runs in this directory whose output is **ragged**: 124 +
104 × 3, and 124 × 3 + 104 × 3. All eight RunSpecs that already reproduced are
**unchanged to the digit**, and `process-tirewear` is still byte-for-byte
identical to the inlined fixture. Ten RunSpecs, `runspecs/pending/` still empty.

**Both were reproduced in pandas first, and both landed on the first run of the
document.** §7.3.16's measurement said what was missing; before a line of the
model changed, the species blocks were recomputed from the default database
against this chain's own parent values (312 cells, worst 9.485e-06) and so were
the crankcase blocks (312 cells, worst 6.265e-06). The figures the documents
then produced are those figures. That is the third time in this phase that
measuring the intermediate turned a port into a translation (§7.3.11).

**What the model had assumed.** `output_rows` was a product —
`n_outputPolProcess × n_outputCohort × counties × months × day types` — and
every RunSpec satisfied it because every one emitted blocks of equal width. That
is a property of the corpus, not of MOVES. A chained pollutant-process is as
wide as its ratio table's coverage, and `NONO2Ratio` and
`CrankcaseEmissionRatio` carry fuel types 1, 2, 3 and 5 and **no electricity
row**, so the species and crankcase blocks are 104 cohorts where their parents
are 124. The 20 that drop are fuel type 9, model years 2001 to 2020 — the same
cohorts `expand-criteria` found are *rated at zero and emitted anyway* on the
parent.

**Two declared numbers became one.** `ratecohort_rows` is the pollutant-process
crossed with the cohort candidate grid — the rate relation with the source bin
divided out — and its dense rank is the output relation's leading key, with
county, month and day type inside it. `n_outputRate` replaces `n_outputCohort`
and `n_outputPolProcess`; `rateSurvivorCount` recomputes it, and
`outputPolProcessCount` and `cohortSurvivorCount` are still reported so that
`tools/check-runspec-shape.py` can say which runs are a rectangle and which are
ragged. Conventions §70 has the shape, including why the rank is over the PAIR
relation and not the rate relation: the rate relation is keyed by source bin, so
a prefix count over it would number the bins, and on `expand-sourcetype` it is
13,776 rows against the pair relation's 1,722 — a self-join with a `<=` filter,
so 190 million cell-pairs against three million.

**Two wrong turns, both worth keeping.**

*The block test that the old arithmetic carried in an `and`.* A pair emits when
a rate row of it emits **and** the road-type test kept its block. Written with
only the first, `rateSurvivorCount` came back 744 on `expand-criteria` where the
run emits 372 — six blocks' worth, because six of its eight selected
pollutant-processes have rate rows that emit and three happen on a road. The
symptom in the output was a block of 124 rows carrying **pollutant 68, process
9**, which is not a pollutant: it is the SUM of the five pollutant-processes
whose `rspp_outputOrdinal` is 0, gathered by a key column whose join matched all
of them at once. A key read through a join that found nothing is not blank.

*A ratio of exactly zero is a ratio.* `CrankcaseEmissionRatio` carries
`crankcaseRatio = 0.0` for diesel model years 2001 and later and MOVES emits
those 19 cohorts as zeros. The chain arm written as `rt_chainRatio > 0` emitted
627 rows instead of 684 — 85 cohorts per crankcase block instead of 104. The
test has to be PRESENCE, on its own flag, because a value cannot distinguish *no
row* from *a row that says zero*. It is §69's rule in a second place, and
`process-crankcase-running` is the only run in the corpus that can tell the two
apart.

**Two more national tables**, 56 in all: `NONO2Ratio` (10,767 rows) and
`CrankcaseEmissionRatio` (20,915). With `PM10EmissionRatio` that is three chain
tables and three ways of saying which model years a ratio covers — a min/max
range, a model-year group, and a range with a regulatory class in the key. The
regulatory class is a real key no RunSpec here can see: source type 21 has
exactly one, so dropping it would be right on every run in this directory and
wrong for a light commercial truck. Named, not closed (conventions §70.3).

**What this leaves.** `process-airtoxics` is now the shape change plus a
generator — its `ATRatio` is empty in the default database, 243 rows in the
execution copy, another table MOVES computes at run time. `process-pm-exhaust`
is a different gap again (§7.3.16).

#### 7.3.18 The chain is a fixed point, and the depth is a measurement

`rtDay_quantChained` read the parent's **direct** quantity — the number a rate
row gets from its own row of `emissionrate`. That is right for every chain in
`runspecs/`: PM2.5 brake wear's parent is PM10, NO's parent is total NOx,
crankcase running's parent is running, and all three parents are rated. It is
wrong the moment a chained pollutant-process is itself a parent, and the
hydrocarbon species are nothing else — `chain-tog-speciation` runs THC 101 to
NMHC 7901 to NMOG 8001 to TOG 8601, and `process-airtoxics` runs THC to NMHC to
VOC 8701 to benzene 2001. Read one rung deep, TOG and benzene are not wrong;
they are **absent**, which §69 has already established is the same failure as a
cohort with no rate.

So the chain is unrolled as the fixed point it is: three value passes and four
presence passes, the last of which exists only to check the first three.

**Three is counted, not chosen.** Every `runspecchainedto` in
`../moves.rs/characterization/snapshots` was read and its graph measured: the
longest onroad chain is three rungs and the widest fan-in is two parents (TOG is
the SUM of methane and NMOG). Two snapshots have no longest chain at all,
because their graphs have **cycles** — `process-pm-exhaust` records 118 from 115
*and* 115 from 118 — which is the second reason a fixed rung count is the right
reading: `runspecchainedto` says which pollutant a calculator MAY derive an
output from, and the registration decides which it does. Conventions §71.1 has
the table.

**And the run checks it.** `run_chainDepthExceeded` is a fourth presence pass
compared with the third, counting the rate rows a fourth rung would newly emit.
A presence pass carries no day, county or month, so it costs one self-join and
nothing else; it is 0 on all ten RunSpecs and `tools/check-runspec-shape.py`
asserts it beside the dropped source bins and the vehicleless physics rows —
the same kind of failure as those two, one that costs rows rather than accuracy.

**All ten RunSpecs unchanged to the digit**, which is the whole evidence that a
fixed point unrolled three times is idempotent at depth one.

#### 7.3.19 What `chain-tog-speciation` costs, measured before porting

The hydrocarbon species were reproduced in pandas from the default database
against this chain's own THC, before any `.esm` edit, and all four land inside
the corpus's own band:

| pollutant | rows | worst cell |
|---|---|---|
| methane (5) | 104 | 5.770e-06 |
| NMHC (79) | 104 | 7.892e-06 |
| NMOG (80) | 104 | 5.380e-06 |
| TOG (86) | 104 | 8.135e-06 |

What it needs, exactly: `methaneTHCRatio` and `HCSpeciation`, both keyed by
(pollutant-process, **fuel subtype**, **regulatory class**, model-year range) —
the fuel subtype is a key this document has never carried, and the regulatory
class is §70.3's width-one trap arriving a second time; the oxygenate term
`speciationConstant + oxySpeciation × volToWtPercentOxy × totalOxygenate`, which
`lib/adjustments.esm` already spells as `speciation_factor` and whose last two
factors collapse to a weighted sum of the four oxygenate volumes; a **second
parent slot**, because TOG is methane plus NMOG and a sum over
`runspecchainedto` would hand it the phantom pollutant-process 8501; and
`altRVP`.

`altRVP` is the one piece that was already half-present. Ethanol E70/E85
vehicles of model year 2001 and later are speciated from a parallel THC tally,
`altTHC` (10001), which is the base rate scaled by `altCriteriaRatio` instead of
`criteriaRatio` — and the two differ in exactly one property. The high-ethanol
substitution overwrites fifteen combustion properties of formulation 27002 with
the E10 row's and deliberately leaves RVP alone at 7.7; `altRVP` is the value it
declined to use, 8.0. With the THC exponent's RVP coefficient at
−0.0220495078142151 the whole of `altTHC/THC` is
`exp(−0.0220495078142151 × 0.3)` = **0.9934070**, against 0.993396 read off the
run. One property, one number, and the model already computes both sides of it.

#### 7.3.20 The hydrocarbon species reproduce, and a working pattern had a price

`runspecs/chain-tog-speciation.esm` and `runspecs/chain-nonhaptog.esm`: 540 rows
each, worst cell 7.564e-06, both right on the document's first run. The second
is byte-identical to the first — the two snapshots agree at a relative 0.0 over
all 540 cells — so it cost nothing and is kept for the one thing it
discriminates: it selects a sixth pollutant-process, 8801, that has neither a
rate nor a chain edge, and emits five blocks.

**Three assumptions broke, all recorded in conventions §72.**

*A ratio table can be keyed by the fuel SUBTYPE.* `methaneTHCRatio` and
`HCSpeciation` key on (process or pollutant-process, fuel **subtype**,
regulatory class, model-year range). A rate row carries a fuel *type*, so the
subtype is a join through the county's fuel supply — and that is why
`rt_chainRatio` gained a county and a month, having been a function of the rate
row alone since PM10 brake wear. Neither table has an electricity subtype, so
the four species blocks are 104 cohorts where THC is 124.

*TOG has two parents, and a key column holds one.*
`rspp_chainInputPolProcessID` summed `runspecchainedto` per output, which was
the parent while every output had one edge. TOG is methane **plus** NMOG and
that sum returns 501 + 8001 = 8501 — §70.1's "pollutant 68, process 9" at a
second site. The chain now joins through `runspecchainedto` itself, which is the
edge list: one `faq` per rung whatever the fan-in, and two variables deleted
rather than one added. TOG then needs no arithmetic — an arm that says *one*
applied to each parent is the whole of it.

*A species can be computed from a tally nobody reports.* Ethanol E70/E85 of
model year 2001 and later speciate their NMOG and VOC from `altTHC` (10001)
while their reported methane and NMHC still come from the ordinary THC; get it
backwards and E85's NMHC is 0.662 of THC instead of 0.178. The whole difference
is `altRVP` — the E10 row's 8.0 against formulation 27002's own 7.7, the one
property the high-ethanol substitution leaves alone. The two criteria ratios
share every other factor, so their quotient is `exp` of the exponent difference:
**0.9934070**, against 0.993396 read off the run, and no division by a ratio.

**And a term that is identically zero is still counted.** `oxySpeciation` is
exactly 0 in all 2,562 rows of `HCSpeciation`, so the oxygenate summand
contributes nothing and this document carries neither `volToWtPercentOxy` nor
the four oxygenate volumes. That is a reading of the DATA, so
`run_oxySpeciationReached` counts the non-zero rows a run's joins reach and is
asserted at 0.

**The one real mistake, and it was a runtime one.** `cfr_suppliedRatio` reaches
the county's formulations by ranging over `fuelsupply` and `fuelformulation`
inside the lookup. Correct, obvious, and copied seven times for the species —
and `expand-day` went from **60 seconds to 564**, on a run with no chained
pollutant at all. `FuelSupply` is **105,651** national rows: one spine over that
product is affordable and eight are not. The collapse is now
`ffsup_marketShare[county, month, formulation]`, computed once, with
`cfr_suppliedRatio` rewritten onto it as well — so a run that had one spine now
has none, and `expand-day` finishes in **34 seconds**, faster than before the
species existed. The cost of that pattern was a number the document already
declares, and reading `n_fuelsupply` before the eighth copy would have priced it
(§72.5).

**Two more national tables**, 58 in all.

#### 7.3.21 `process-airtoxics` reproduces, and the table it needs is empty

**644 of 644 rows, worst cell 7.564e-06** (`runspecs/process-airtoxics.esm`,
2026-09-21). THC running exhaust, the two hydrocarbon species on the way to it —
NMHC and VOC — and the three gaseous air toxics chained off VOC: benzene,
1,3-butadiene and formaldehyde. The thirteenth RunSpec, and the first that needs
a table the default database ships **empty**.

**`ATRatio` has 0 national rows and MOVES writes it at run time from two
different computations.** For model years 2001 and later the rows are
`generalFuelRatioExpression` evaluated on the county's supplied formulations —
three algebraic forms (D, E and F in `docs/fuel-effects-generator.md` §2.1) that
that document had recorded as ported by nobody and checkable by nobody, because
every snapshot moves them out of `generalFuelRatio` before capture. For model
years 2000 and earlier they are a quotient of two COMPLEX MODEL ratios against
the `airtoxicsA` base fuel, weighted by what that base fuel emits. It is the
same split at the same model year that `criteriaRatio` has (§7.3.14), which is
why the second table needed one new calculation engine, four new configurations
and three new forms and no new *shape*.

**Measured before porting, and it decided the whole rung.** The eight distinct
ratios `docs/process-airtoxics.md` §2.5 reads off the snapshot's captured
`atratio` were reproduced from the DEFAULT database in pandas first — the six
closed-form values to 9.6e-08 and the complex-model band, age by age, to 5.3e-08
— and then the whole 644-row chain to 7.9e-06, before a line of `.esm` changed.

| what | worst relative error |
|---|---|
| the six model-year-2001 closed-form ratios | 1.0e-10 to 9.6e-08 |
| the model-year-2000 complex-model ratios, ages 20 to 40 | 2.7e-08 to 5.3e-08 |
| the 644-cell chain, in pandas | 7.892e-06 |
| the 644-cell chain, from the document | **7.564e-06** |

**Two findings, and the second is the expensive one.**

*A constant that turned out to be a key* (§73.1). The Complex Model read
`meanFuelParameters` and `baseFuel` at the literal model-year group 19502000,
written into three filters. The air-toxics configurations sit at group 0 and
their base fuel is formulation 96 and not 99 — and the three criteria
configurations could not see it, because all three agree. That is conventions
§62.3's width-one trap at a fifth site, and this one was invisible in the
criteria answer.

*A bare variable in a filter is IGNORED once the aggregate has two output
indices* (§74, filed upstream as EarthSciML/EarthSciAST#441). `"value":
"rt_fuelTypeID"` resolves from the variable's shape and works while the faq has
one output index; give it a county and a month beside the rate row and the
WHOLE filter stops applying. Every fuel type took the gasoline ratio and model
year 2020 took both halves of a table split at 2000, so the answer was the sum
of two ratios that can never apply to one row — which reads exactly like a
modelling error about appending versus choosing. A three-variable probe says
the output count is the only trigger: a second non-output range, a join, a
template, which output index the variable draws and a second factor over
another index set all change nothing. Two things made it cost more than the
four characters the fix takes: the `bool_and_or` twin of the same faq filtered
CORRECTLY — it has one output index, because a presence relation drops the
county and the month — so the presence relation said gasoline-only and the
value relation said every fuel type; and `rt_complexRatioExact` had carried the
same inert filter all along, hidden completely because `rt_criteriaRatio` gates
it behind that single-output twin. `run-tests.sh` now LINTS for it: no faq with
two or more output indices may name a variable bare in its filter, and the repo
had exactly one instance before this rung.

**And one that is worth more than either**: *centring only shows up in a
nonlinear term* (§73.2). With the centring silently missing, all three toxic
`ratioNoSulfur` values were right to 3e-08 and all three *ratios* were 7.4 %
high — because a centre cancels in `exp(target) − exp(base)` for a linear term,
the three toxics use linear terms only, and their shared denominator VOC does
not. A common factor is invisible in the ratios between the answers. The fix
was to observe the INTERMEDIATE, `cmx_ratioNoSulfur`, against the same number in
pandas.

**What it cost, measured in CPU and not in clock** (§73.4). The complex-model
relation now serves two generators: `complexconfig_rows` went from 3 rows to 7
and `complexengine_rows` from 19 to 29, and every `cmx_*` variable is dense over
both. On `expand-criteria`, which selects no air toxic and reads none of the new
work, **user CPU goes from 39.9 s to 49.8 s — 25 % more** — with peak RSS 1,277
MB against 1,315 MB and the emitted relation byte-identical. §72.5 priced
*copying* a relational pattern; this is the other case, where it is **widened**,
and the price is the widening factor times whatever the relation already cost.
The saving that exists and is not taken: the (configuration × engine row)
product is 203 pairs of which 59 are meaningful.

**The clock on this machine is worthless and it took two wasted measurements to
act on it.** The node is shared; its load average moved between 43 and 112
during this rung, and the SAME document took 42 seconds of wall clock on one
pass and 557 on another. The first pair of numbers reported the widened document
as twice as fast as the narrow one. User CPU over three interleaved passes is
steady to 0.2 s a side, and that is the number above.

**Two more national tables**, 60 in all: `ATBaseEmissions` and `ATRatioNonGas`.
**Thirteen RunSpecs in `runspecs/`.**

#### 7.3.22 What `chain-so2-co2e-mechanism` is missing, measured

`runspecs/pending/chain-so2-co2e-mechanism.esm`, 2026-09-21. The measurement
pass §7.3.16 ran for the shape, run against the last unported onroad RunSpec
that is not the cyclic one.

**Every one of the 1,294 rows this chain emits is right** — 1,294 shared, 0
extra, worst cell 8.201e-06 against the 2e-05 gate. The reference has 2,767, so
the entire gap is **absence**, and it is five pieces:

| missing | rows | what it needs |
|---|---:|---|
| SO2 (31) | 104 | `SO2Calculator`: energy × a market-share-weighted sulfur level over the fuel's energy content, then `sulfateemissionrate` |
| CO2 (90) and CO2e (98) | 125 each | `CO2AE`: energy × carbon × oxidation × 44/12, then a stage that reads its own rows BACK and adds methane and N2O by global warming potential |
| NonHAPTOG (88) | 104 | `TOGSpeciation`: NMOG minus the sum of one mechanism's integrated species, clamped |
| the seven BTEX toxics (40–46) and naphthalene (185) | 832 | two more `AirToxicsCalculator` ratio paths, `minorHAPRatio` and `pahGasRatio` — a fourth and a fifth keying of the same idea |
| ethanol (21), acetaldehyde (26), acrolein (27) | 183 | thought to be **data, not machinery** — and it was not. **Done 2026-09-21** (§7.3.23) |

**And the useful half of the measurement is what it does NOT wait on.** The
second rate root is already here — Total Energy (91) and N2O (6) come off the
age-independent `emissionrate` where THC comes off `emissionratebyage`, and both
reproduce exactly, as do THC, methane, NMHC, NMOG, TOG, VOC and the three toxics
of §7.3.21. **Eleven of the twenty-six pollutants are complete before a line of
that rung is written**, and the energy the two carbon calculators need is a
number this chain already has right.

**`runspecs/pending/` holds one document again**, and it holds the measurement
above rather than a plan.

#### 7.3.23 The fifth piece was not data, and a census that summed correctly was wrong

2026-09-21. The cheapest row of §7.3.22's table, closed. The three toxics that
chain half-emitted — ethanol 21, acetaldehyde 26, acrolein 27 — are complete:
**1,294 → 1,477 rows, 1,477 shared, 0 extra, worst cell 8.201e-06, unmoved**,
and all thirteen RunSpecs in `runspecs/` unchanged to the digit.

§7.3.22 called this row "**data, not machinery**". It was wrong twice, and both
ways are recorded in conventions §73.5 because both are the same error — **a
census and a property set are sized to the rows already read**:

| what it said | what it was |
|---|---|
| ethanol's early ratio is a `generalFuelRatioExpression` row | it is a **seventh algebraic form**, a step function of the ethanol volume, and `lib/fuel_effects.esm` gained `stepwise_property_ratio` for it |
| acetaldehyde needs a complex-model **configuration** | it needs a configuration **and two properties the relation did not carry** — `ETBE` and `Ethanol`, complex-model parameters 46 and 47 |
| acrolein needs a form | it does not: a bare constant is the centred linear form with a **zero slope** |

**The acetaldehyde residual named its own generator.** Twelve of its thirteen
terms were right, and the answer was wrong by a **flat 2.386 on all 21 model
years and on nothing else** — exactly the 21 model years the complex half
covers, with every closed-form row right. A missing LINEAR term in an exponent
is one constant factor, and `exp(0.249326 × 0.3488 × 10) = 2.386` identified it
before any code was read. That is §73.2 read backwards, and it is the second
time on this rung that "several answers wrong by the same factor" was solved by
looking at what they share rather than at any of them.

**And the form census was an undercount that passed its own check.**
`docs/fuel-effects-generator.md` §2.1 reported six forms over 2,078 expression
rows, with form C at 1,013 rows and 100 strings. Re-classified: form C is **974
and 99**, the step is **39 and 1**, and `974 + 39 = 1,013`. The rows were
absorbed by a classifier that tested for `if(` and got a case-insensitive yes on
`IF(ETOHVolume<0.1, …)`. Both of the census's partition checks — rows summing to
2,078, strings to 118 — still passed, because a misclassification moves rows
between buckets without moving either total. **A partition check proves a
classifier is total, not that it is right.** §2.1 now prints one representative
string per bucket, which is what would have caught it, and the table is seven
forms plus the bare constant.

**Four pieces left in §7.3.22's table**, and fourteen of the twenty-six
pollutants are now complete.

**The upstream rebuild was measured and NOT promoted.** §7.3.21 paid 25 % of
`expand-criteria`'s CPU to widen the complex-model relation rather than copy it,
and EarthSciAST PR #440 — "materialize an inline `const` array literal once, not
once per cell" — merged the next morning, which looked like the thing that would
pay it back. It does not. `esm` built from `3cf6f6f` (what `esm-version.lock`
records) and from `be1fafe6` (which carries #436, #440 and #439), three
interleaved passes each on the same document: **52.6 / 53.7 / 52.2 s of user CPU
against 52.4 / 52.2 / 54.2 s**, peak RSS 1,326 MB both, output byte-identical.
The means differ by 0.2 % and the slowest single pass of the six is the new
binary's. So `./esm` and `esm-version.lock` are left where they are — a rebuild
re-attributes every fidelity number in this repository to a different revision,
and that is worth doing for a reason and not for a hope. The comparison binary
is `./esm.be1fafe6`, untracked beside `./esm` (conventions §73.4).

This rung's own widening — acetaldehyde's configuration and the two properties —
cost **49.8 s → 52.8 s, 6 % more**, measured the same way.

#### 7.3.24 What `process-pm-exhaust` is missing, measured — and what it gets wrong

`runspecs/pending/process-pm-exhaust.esm`, 2026-09-22. The last unported onroad
RunSpec, the one this plan has been calling "cyclic". **The cycle is not the
gap** — `docs/process-pm-exhaust.md` §2.8 settled that `runspecchainedto`
records `SulfatePMCalculator`'s inputs and the arithmetic is a DAG, and
`fixtures/process-pm-exhaust.esm` already computes all of it on the snapshot
path, 728 of 728 at 7.516e-06. This rung moves machinery; it does not invent it.

Unlike §7.3.22, the measurement is not only absence. The chain emits **456 rows
and 37 of them are right**:

| block | emitted / expected | right | what is wrong |
|---|---:|---:|---|
| EC 112 | 124 / 104 | 37 | every wrong cell is exactly `1/generalFuelRatio` on 11201 (1/1.0909107, 1/0.9727): the PM **base** rate never gets its general fuel ratio. Plus 20 electricity rows MOVES drops |
| NonECPM 118 | 124 / 104 | 0 | MOVES emits the **re-summed** 118; the chain emits the rated one |
| sulfate 115, water 119 | 104 / 104 each | 0 | **claimed by the crankcase path** — ratio-1 `crankcaseEmissionRatio` rows that are a row filter inside `SulfatePMCalculator` read as "sulfate = all of NonECPM" |
| PM2.5 110, OC 111, PM10 100 | 0 / 104 each | — | absent; `rt_pm10ChainRatio` is already 1.13043, its parent is what is missing |

The arithmetic was confirmed from the reference before any port: PM10 = PM2.5 ×
ratio, 118-out = 115 + 119 + residue to 1e-5, OC = residue × speciation
fraction, and the sulfate fraction by hand equals the fixture's
`rt_sulfateFraction` (0.027248, 0.066530, 0.014773).

**The ordering this suggests**: (1) `generalFuelRatio` on the PM base rate —
the forms are already in `lib/fuel_effects.esm`, and it fixes 67 EC cells;
(2) take 115 and 119 away from the crankcase path, which is a correctness fix
for any future run whether or not PM is finished (conventions §75); (3) the
split / re-sum, which is the new operation.

**(1) and (2) are done, same day.** The chain now emits 248 rows, **every EC
cell right — 104 of 104 at 5.272e-06** — and nothing spuriously claimed:

* `rt_baseFuelRatio` is BaseRateCalculator's `generalFuelRatio` factor, a
  separate multiplier beside `rt_criteriaRatio` because MOVES keeps the two in
  separate tables and applies both. Its three rows (EC on gasoline, E85, diesel)
  are forms A and B; form A's exponent is two more rows of the shared exponent
  table `atxexp_*`, evaluated by the same `air_toxics_exponent` template as
  formaldehyde's, so the only new code is the relation's collapse and lift.
  Source type is not a key, measured: the E85 string covers exactly the three
  source types `sampleVehiclePopulation` has an E85 vehicle on.
* `rt_isSulfatePMSpecies` keeps the crankcase lift off any pollutant that
  `crankcaseEmissionRatio` also carries on an exhaust process — derived from the
  table, not listed. `process-crankcase-running` is unchanged to the digit.

**(3) is done too, the same day, and `process-pm-exhaust` reproduces: 728 of
728 cells, worst 7.516e-06, on the port's first run.** `SulfatePMCalculator` is
four species per cohort — EC, sulfate, water and the internal residue 120 — and
every emitted block is a linear combination of them: NonECPM is sulfate + water +
residue, PM2.5 is all four, organic carbon is the residue × `pmSpeciation`'s
fraction. That share matrix (`spmsh_*`, eleven entries) is the split AND the
re-sum, which is why MOVES's cyclic chain declaration never had to be resolved:
the cycle records that the calculator takes NonECPM in and puts NonECPM out, and
a linear map from species to blocks has no direction to cycle in (conventions
§76). The design was checked in pandas against all 728 reference cells from the
default tables before the model changed, including the one detail that looked
like an error — the residue takes the UNADJUSTED sulfate and water fractions.

Where it enters the model is the part worth recording. The SPM quantity replaces
`rtDay_quantDirect` on the six blocks the calculator writes, and the old rate ×
activity becomes `rtDay_quantRated`, which the species read. So the chain's
fixed point sees a PM2.5 block with an OWN quantity, and PM10 chains off it by
the `PM10EmissionRatio` path that was already there. Survival works the same way:
`rt_survives` becomes "covered by `sulfateFractions` and made of a surviving
parent" on those blocks, which is also what drops electricity.

**Fourteen RunSpecs in `runspecs/`; `runspecs/pending/` holds one.**

#### 7.3.25 `chain-so2-co2e-mechanism` reproduces, and the chain's edges got weights

2026-09-22. The four pieces §7.3.22 named, in order of cost, each reproduced in
pandas from the default tables before the model changed:

| piece | rows | what it took |
|---|---|---|
| `minorHAPRatio`, `pahGasRatio` | 832 | two more summed arms of the air-toxics ratio (J102, J103): the `ATRatioNonGas` lift without the source type, and one keyed on the fuel type. Right on the first run |
| `SO2Calculator` | 104 | base rate × the supply's sulfur ÷ its energy content (J104). The sulfur is AFTER the high-ethanol substitution — the pandas pass showed a flat 7.15/8 on every E85 cell against the national value — and the energy is in KILOJOULES: the first run was low by exactly 1,055,055.9, because this chain carries reported units and MOVES chains internal ones. Fixed as an edge weight (J105) |
| `CO2AERunningStartExtendedIdleCalculator` | 250 | CO2 = energy × carbon × oxidation × 44/12 (J106), CO2 equivalent = CO2 + 28 CH4 + 265 N2O (J107). Neither edge is in `runspecchainedto` — `chainedTo1/2` are NULL on 9001 and 9801; the calculator chains in Java — so every rung now joins through `chainlink_rows`, that table UNION a declared four-edge list, and the GWP is the edge's weight. Right on the first run |
| `TOGSpeciationCalculator` NonHAPTOG | 104 | NMOG minus the one national integrated species set, clamped (J108). Four rungs from THC, one past the chain, and a leaf, so it reads the finished quantities after the chain. Right on the first run here, and WRONG in `chain-nonhaptog`, which selects 88 but no mechanism: the switch is the mechanism pseudo-pollutant 300001, not 88. The suite's shape check caught the 104 phantom rows that `n_outputRate` had truncated out of the value comparison |

**All 2,767 rows, worst cell 8.201e-06** — the worst cell the 1,294 rows had on
the day this was measured. The document moved out of `pending/`. User CPU on the run went
110 → 115 s. Conventions §77 (a chain edge has a unit and a weight, and not every
edge is in `runspecchainedto`) and §78 (a leaf past the last rung runs after the
chain).

**Fifteen RunSpecs in `runspecs/`; `runspecs/pending/` is empty.**

What that does NOT mean is that the onroad corpus is done. Seven onroad snapshots
still have no document in `runspecs/` — which is a statement about which documents
exist, not about which database anything reads: everything in `runspecs/` computes
from the default database, and what these seven have instead is a `fixtures/*.esm`
reading that run's own pre-filtered execution-database snapshot (stage 7c), which
is the weaker check because MOVES has already done the selection. They are the
three evaporative runs and refueling (64, 64, 64 and 168 rows), `mixed-onroad`
(125), `scale-project` (125) and `chain-so2-co2e-mechanism-control` (2,309) — the
last is this run's control twin and is the obvious next document (§7.3.26).

#### 7.3.26 The control twin reproduces, and it tests gating rather than arithmetic

2026-09-22. `runspecs/chain-so2-co2e-mechanism-control.esm`: **all 2,309 rows,
worst cell 8.201e-06, on its first run, and it cost no model change.**

It is the same MOVES run as `chain-so2-co2e-mechanism` with five pollutants
DESELECTED -- SO2 (31), NonHAPTOG (88), Atmospheric CO2 (90), CO2 Equivalent (98)
and the NonHAPTOG Mechanism pseudo-pollutant (3000). Every other selection is
identical, and MOVES's own two answers were checked to be BIT-identical on all
2,309 shared rows before the document was written, which is what makes it a
control: the reference is the twin's numbers with five pollutants removed, so
every way it can fail is this port emitting something the RunSpec did not ask
for, or dropping something it did.

Three of the five are exactly the pollutants whose machinery does NOT come from
the run's own tables, which is why the twin was worth a document:

| what it gates | why only this run can see it |
|---|---|
| the four CO2AE chain edges | they are DECLARED in the model, not read from `runspecchainedto` (conventions §77), so they are present in EVERY run. Here 9001 and 9801 are unselected and all sixteen edge-process pairs must stay silent -- against 250 rows in the twin |
| the NonHAPTOG leaf | it is switched by the mechanism pseudo-pollutant and not by selecting 88 (conventions §78). `chain-nonhaptog` selects 88 with no mechanism; this run selects NEITHER, so the leaf must be off from both sides |
| SO2's one `runspecchainedto` row | 20 edges here against the twin's 21. Dropping one table row must drop exactly one pollutant's block and leave the other twenty-one untouched |

It also leaves 9101 Total Energy selected with NOTHING chained off it -- the only
run in this corpus where an energy root has no children -- so the kilojoule
divisor the edge weight carries has to be invisible here, where in the twin it is
a factor of 1,055,055.9 on two pollutants.

**Sixteen RunSpecs in `runspecs/`, `pending/` still empty.**

#### 7.3.27 What the EVAPORATIVE family costs, measured -- and `process-evap-leaks` needs none of the expensive half

2026-09-22, measured before any model change. What is left of the onroad corpus
after §7.3.26 is the four evaporative and refueling runs, `mixed-onroad` and
`scale-project`. The four are small -- 64, 64, 64 and 168 rows, one pollutant
(THC) and one process each -- and their selections are trivial:
`runspecchainedto` is EMPTY in all four, and the TOG and VOC pollutant-processes
they select emit nothing.

**The model has none of it.** `onroad/model.esm` has no evaporative machinery at
all: no soak, no IM coverage, no `SourceHours`, 0 of 1,003 variables matching any
of them. The table delta is where the price is:

| run | fixture tables absent from the national mount | of those, EMPTY in the default DB |
|---|---|---|
| `process-evap-leaks` | 6 | `sourceBin` (this port already generates it), `soakActivityFraction` |
| `process-evap-fvv` | 8 | the same two, and it reads `coldSoakInitialHourFraction` |
| `process-evap-permeation` | 12 | the same two, plus `averageTankTemperature`, and `pollutantProcessMappedModelYear` and `regClassSourceTypeFraction` are absent outright |
| `process-refueling` | 7 | `evSalesFraction` and `sourceUseTypePhysicsMapping` are absent outright |

All four outputs of `TankTemperatureGenerator` -- `soakActivityFraction`,
`averageTankTemperature`, `coldSoakInitialHourFraction`,
`coldSoakTankTemperature` -- are empty nationally, at 0 rows against the
snapshots' 2, 144, 254 and 144. That generator is 2,645 lines of Java in seven
steps and is by a distance the largest thing left in the onroad corpus.

**`process-evap-leaks` does not need any of it, and that is why
`docs/evap-leaks.md` §0.3 chose that run.** The soak modes enter at a weight of
exactly zero. MOVES's own intermediate for the run says so directly:
`opModeDistributionTemp` is `150 -> 0`, `151 -> 0`, `300 -> 1`, and
`fractionOfOperating` is 1, because at an **on-network** link `SourceHours = SHO`
row for row and the soak weight is `1 - fractionOfOperating`. So an empty
`soakActivityFraction` costs this run nothing -- but only if the document
COMPUTES that weight rather than assuming it, which is the distinction
conventions §18.2 already records with a probe row at `0.599999932`. An assumed
1 agrees on all 64 rows here and is wrong at the first off-network link.

What `process-evap-leaks` actually needs is therefore all relational and all of a
kind this port has done before: the evap operating-mode distribution (E1-E3), the
`IMCoverage` lift (L1, and `imCoverage` is national at 2,024,874 rows), the
op-mode-weighted base rate (L8), and `SourceHours` activity. It is the cheap
entry to the family and should be taken first.

**What the thermal chain costs, priced now because permeation and FVV cannot
dodge it.** On the one cell `process-evap-leaks` would use (source type 21, zone
261610, month 8, hourDay 75), `soakActivityFraction`'s three terms are:

| term | value | where it comes from |
|---|---|---|
| eMinutes `= 60 x vehicles` | 49,260 | `SampleVehicleDay`, national, exact |
| oMinutes `= SUM(keyOff - keyOn)` | 1,446 | `SampleVehicleTrip` split across hours (TTG-2), national, exact |
| `eMinutes - oMinutes` | 47,814 | the denominator of both soak fractions |
| hot-soak minutes | **1,058** | TTG-1 and TTG-4: a minute-by-minute tank-temperature recurrence |

The first three reproduce from the national tables alone, and the fourth is
implied by MOVES's own stored answer -- 2.21274e-02 x 47,814 = 1057.9995 and
9.77873e-01 x 47,814 = 46,756.02, an integer and its complement to 5e-4. That
confirms the whole structure of the generator before a line of it is ported, and
it is worth having written down even though the run that motivated the
measurement turns out not to need it.

**The fourth term cannot be got at relationally.** TTG-3 builds the hot-soak
events from the trips alone, and counting their minutes UNCLAMPED gives 4,913 --
4.6x the right answer. The cutoff is TTG-4's: the tank temperature is walked one
minute at a time from the trip's end, each minute depending on the running sum of
the previous minutes' deltas against the ambient, and the soak is recorded only
while it stays above the cold-soak temperature plus 3 °F. 78.5 % of the minutes
are cut, so nothing here can be approximated away.

That is a recurrence, and **the format already holds one**: conventions §19
records `agedist.f`'s thirty-year fold authored as esm-spec §4.3.1.1 causal
self-reference, so this is not a new kind of work and not an upstream ask. It
would be the first recurrence on the ONROAD side, and §19.1's lesson applies
before any of it is spelled -- reduce the fold to a scalar recurrence over one
axis first, because what TTG-4 walks is a per-trip minute sequence and not a
vector.

#### 7.3.28 `process-evap-leaks` reproduces, and the table it needs has no rows

2026-09-22, the same day §7.3.27 priced the family. All 64 rows, worst cell
**7.294e-06**, on the document's first run — and the number matters twice,
because an independent pandas reproduction from the national tables had reached
the same 7.294e-06 before the model changed. **Seventeen RunSpecs in
`runspecs/`.**

**The measurement came first, and it went further than §7.3.27's table delta.**
`docs/evap-leaks.md`'s own oracle reproduces the run from the snapshot's input
tables; the pass here was to re-point it at `./movesdb` and see what broke. Six
tables the execution database carried are absent or empty nationally, and each
turned out to be a different kind of thing:

| table | national | what it turned out to be |
|---|---|---|
| `sourceBin` | 0 rows | `SourceBinDistributionGenerator` writes it. The port already derives the grid; the 80 bins reproduce exactly from `sampleVehiclePopulation` |
| `sourceBinDistribution` | 0 rows | the same generator. 125 distribution rows, exact |
| `opModePolProcAssoc` | 407 rows | a national table that was simply not mounted. Now it is |
| `pollutantProcessAssoc` | 786 rows | not needed twice over: `polProcessID = pollutantID × 100 + processID` is arithmetic the port already does, and its `isAffectedByEvapIM` flag gates only a blend that is inert |
| `fuelType` | 6 rows | not needed: `subjectToEvapCalculations` is measurably inert, because `emissionRateByAge` carries 113 for gasoline and E85 bins and for no diesel or electricity one |
| `soakActivityFraction` | **0 rows** | `TankTemperatureGenerator`, and the one that is interesting |

`IMCoverage` was the surprise in the other direction. §7.3.27 called the I/M
lift work to do; it is **2,024,874 national rows that narrow to zero for county
26161 in any year at all**, so L1 produces nothing and the blend is the identity
— as a RESULT of the county selection rather than as an inheritance from the
execution copy's emptiness. Nothing was ported, and the document says why.

**What the model gained is one alternative, not one family.** MOVES weights a
rated pollutant-process's operating modes with a `RatesOpModeDistribution` over
speed bins. An evaporative one is not in either of the two generators that write
that table: `EvaporativeEmissionsOperatingModeDistributionGenerator` writes a
distribution over SOAKING and RUNNING instead. So `pp_W` acquired an alternative
rather than a term — `evap_W`, with E1's `fractionOfOperating`, E2's soak
weights and E3's residual — reached through one `ifelse` on the process, and
`rtDay_meanBaseRate` gained the month axis that distribution is keyed on. 21
variables and 13 equations; everything else was already here, including
`SHO / noOfRealDays`, which IS the inventory calculator's activity. The four
adjustment tables an exhaust rate row passes through were each measured to carry
no row at `polProcessID` 113, so the factors the chain already applies are their
identities and nothing had to be bypassed.

**The axis promotion was free, measured back to back.** `rtDay_meanBaseRate`
gained the month, which is the widest thing this change touches:
`runspecs/expand-month.esm` is four months over the same rate relation. Running
it on the pre-change model and the changed one in the same session gives
**161.31 s / 1,472,328 KB before and 151.20 s / 1,473,036 KB after** — 708 KB of
peak RSS, 0.05 %, and a wall clock that moved the wrong way — wall clock on this
corpus tracks page-cache warmth rather than work, so the honest reading of the
pair is "no measurable time". The
two emitted relations are **byte-identical**, which is a stronger statement than
the worst cell being unchanged: the promotion added an axis of width four and
changed no number anywhere in the corpus.

**The empty table is mounted, and that is the finding (conventions §80).**
`soakActivityFraction` has no rows in either database this model is mounted
against, so the soaking modes contribute nothing and mode 300's residual is 1.
Three spellings give those numbers and only one of them gets them from the data:
mount the empty table, join it on all five of its keys, and sum over no rows. An
aggregate over an empty relation is the additive identity — probed before the
port, and `spikes/7c/` had been mounting a zero-row `integratedSpeciesSet` all
along without anyone noticing it was the same question. The other two spellings
— give mode 300 the weight 1, or give the soak modes the weight 0 — are right on
every run in the corpus and move the statement out of the database and into the
document.

**The zero is load-bearing, and that is measurable.** The soaking modes are not
weighted out because their rates are small: `emissionRateByAge` carries 2,188
rows at each of the three modes for `polProcessID` 113, and their mean
`meanBaseRate` is 0.0989 g/h at Hot Soaking and 0.0514 at Cold Soaking against
0.9267 at All Running. Only the weight suppresses them, and the weight is
`1 − fractionOfOperating`. A document that gave the soak modes any weight at all
would be wrong by roughly a sixth; one that gave mode 300 its weight without
computing the residual would be right here and blind to the difference.

**A row set diverges where the numbers do not, and it is the first time.**
MOVES's own `opModeDistribution` for this run has three rows; this chain emits
one. The two missing rows are modes 150 and 151 at value exactly 0, because at
an on-network link `SourceHours` is `SHO` row for row, E1's ratio is exactly 1,
and the soak weight `1 − fractionOfOperating` is exactly 0. `MOVESOutput` cannot
see the difference and this document reproduces it to 7.294e-06 — but the
intermediate is not reproducible without `TankTemperatureGenerator`, and both
the document and conventions §80 say so rather than leaving it to be discovered.

**`run_offNetworkLinkCount` is new, and it guards an identity rather than a
width.** The zero that makes all of this free comes from `SourceHours = SHO`,
which `TotalActivityGenerator` does only at an on-network link; at road type 1
it uses `SHP`, a table this model does not have. A run selecting road type 1
would not drop a row or emit a zero — it would divide `SHO` by a copy of itself
where MOVES divided it by something else. So the model counts the counties whose
link is off-network and `tools/check-runspec-shape.py` asserts none is, beside
the three counts of what the chain could not reach.

**What is left of the onroad corpus** is `process-evap-permeation`,
`process-evap-fvv`, `process-refueling`, `mixed-onroad` and `scale-project`. The
first two cannot dodge the thermal chain and §7.3.27 prices it; refueling is the
next thing to measure.

#### 7.3.29 What `process-refueling` costs, measured — and the whole of it reproduces already

2026-09-22, the same measure-first pass §7.3.28 used, applied to the next run
before any model change. **The national default database reproduces
`process-refueling` completely: all 168 rows, worst cell 6.981e-06, identical to
the execution-database reproduction at every cell.** Nothing about the data is
missing. What is left is the model, and this section prices it.

**Seven tables the fixture reads are not in the national mount, and five of them
are real.**

| table | national | narrowed to | note |
|---|---|---|---|
| `refuelingControlTechnology` | 189,379 | **9,102** | exactly the execution copy's count, at source type 21 and processes 18/19. It carries fuel types 1 and 5 only, which is why the two output blocks are different sizes |
| `countyYear` | 203,616 | **1** | both Stage II adjustments 0.0 for county 26161 |
| `sourceTypeTechAdjustment` | 1,443 | **111** | exactly the execution copy's count |
| `refuelingFactors` | 5 | 4 | electricity dropped by the join, not by a filter |
| `fuelType` | 6 | 4 | still not mounted; `process-evap-leaks` measured it inert there and it is a real input here |
| `evSalesFraction` | — | — | not a table: MOVES computes it at execution time and `onroad/model.esm` already computes it, reproducing the snapshot's 115 rows |
| `sourceUseTypePhysicsMapping` | — | — | not a table either: it is `sourceUseTypePhysics` with one column renamed, which the model already reads |

**One column is NULL where the execution copy had a value**, and it is already
solved for the same reason: the national `zoneMonthHour.heatIndex` is empty
because `MeteorologyGenerator` fills it, and `lib/meteorology.esm`'s
`heat_index` computes it — 59.5 °F at 59.5 °F and 90.4 % RH, below the 78 °F
threshold, which is the arm where the heat index IS the temperature. The
reproduction above mirrors that rather than reading the column, and asserts it
is on that arm rather than assuming it.

**The Stage II arm is still untested, and the national table says how untested.**
`docs/process-refueling.md`'s oracle notes that both program reductions are 0.0,
so the fixture cannot distinguish `(1 − P)` from `1`. The national `countyYear`
turns that from a gap into a measurement: **7,375 of its 203,616 rows carry a
nonzero vapour adjustment and 7,154 a nonzero spill adjustment**. The arm is
real data that no run in this corpus reaches, and
`components/refueling_loss_rate.esm` already carries probes at 0.2 and 0.3.

**The model work, sized.** `components/refueling_loss_rate.esm` is 32 variables
and 32 equations over REFEC-1..8, and `lib/refueling.esm` already factors the
eight shapes it needs — `refueling_temperature`, `tank_temperature_dif`,
`displaced_vapor_rate`, `floored_vapor_rate`, `adjusted_vapor_rate`,
`adjusted_spill_rate`, `refueling_emission_quantity` and `positive_else_zero` —
so the port imports them by reference rather than restating them. Five data
sources, the five tables' columns, and that chain. It is the next rung, and
unlike the evaporative pair it needs nothing from `TankTemperatureGenerator`.

#### 7.3.30 `process-refueling` reproduces, and two gates had been right by coincidence

2026-09-22. All 168 rows, worst cell **6.981e-06**, the same number §7.3.29's
pandas reproduction had reached from the national tables before the model
changed. **Eighteen RunSpecs in `runspecs/`.**

**The calculator itself went in as priced** (§7.3.29): five mounts, the thirty
columns they carry, and REFEC-1..8 with all eight of its shapes imported by
reference from `lib/refueling.esm` rather than restated. It is `rt_so2ChainRatio`'s
shape — a mass child of energy is a quotient, and `lnk_weight` already carried
the kilojoule rebase — so the chain arm itself was eleven variables. REFEC-1 and
REFEC-2 were checked against the specification's own numbers before anything
downstream was written: 8.0 and 7.7 average RVP, 68.495 °F refueling
temperature, 12.03091 °F tank-temperature difference, and displaced-vapour rates
of 3.0152931048711182 and 2.8986555933440346 against the spec's 3.0152931 and
2.8986556.

**The control-technology lookup went on the BIN and not on the rate row**, which
is where the one cost decision was. `refuelingControlTechnology` is 189,379
national rows and the displacement side needs three lookups into it on six keys;
`sourcebin_rows` is 164 where `rate_rows` is 1,148, so the spine is seven times
smaller for exactly the same answer (conventions §72.5, and the memory of
`expand-day` going to 564 seconds on seven copies of a spine over 105,651 rows).

**What was not priced was that two gates in the model had been right by
coincidence for seventeen runs.**

**The road type (conventions §82).** `emissionProcess.occursOnRealRoads` is `'N'`
on both refueling processes, and MOVES emits both at road type 4. The flag is
`BaseRateGenerator`'s and says where that generator WRITES a process's rates;
neither rate table carries a single row at `polProcessID` 118 or 119, so there
is nothing for it to say, and a chained calculator's rows take the road type of
the rows they were stamped from. The corrected test is `occursOnRealRoads` OR
*the rate tables have no row for this pollutant-process*, asked of the table
rather than of the run's rate rows. It can reach only processes 16, 17, 18, 19,
22, 23 and 24 across the whole snapshot corpus, and no other run in `runspecs/`
selects one — `expand-day`'s suppression of start and extended-idle energy is
untouched, which was verified before the change and again by the suite.

**The prerequisite (conventions §81), and it is the first time the execution
database is not enough.** `runspecpollutantprocess` carries seven rows and MOVES
emits two. Three are Total Energy Consumption, which
`ExecutionRunSpec.flagRequiredPollutantProcesses` ADDED because a refueling loss
is computed by scaling energy; the addition is flagged `silentlyRequired`, the
output processor strips it, and the flag is not persisted. The database records
the expanded set and the XML records the user's — and the XML is the file this
repository has a rule against reading.

It is recoverable anyway, and only for a reason worth writing down: the needs
table is **refueling-only**. Thirty rows, five pollutants crossed with the two
refueling processes, each requiring energy at three exhaust processes, and no
other calculator in MOVES adds a prerequisite at all. So the strip is a function
of the selections and a declared table. Had the mechanism been general the
expanded set would not determine the original one — `X = S ∪ needs(S)` has more
than one solution and the maximal one is always `X`.

**What that failure looked like before it was understood** is the reason both
corrections are recorded rather than just made. The first run emitted 168 rows:
125 of them the energy block, and 43 with `processID` 166, `pollutantID` 356 and
`modelYearID` 77603 — summed key columns, because `n_outputRate` of 168 had
truncated two real blocks into the space one prerequisite block was occupying.
The row COUNT was right. Only the comparator's key check saw it, which is
conventions §22's rule earning its keep for the third time.

**One count changed meaning with it.** `cohortSurvivorCount` read
`coh_hasRatedRow`, which asks whether any rate row of a cohort emits; until this
run that was the same question as whether any emits in a block the output keeps.
The 21 electricity cohorts break it — they reach an emitting rate row only in the
stripped energy block — so the count now reads the block as well and is 104 here
against the energy spine's 125. `coh_isSelected` deliberately does not: the
source-bin grid is built for every cohort the chain needs, emitted or not.

**What is left of the onroad corpus** is `process-evap-permeation`,
`process-evap-fvv`, `mixed-onroad` and `scale-project`. The two evaporative runs
are the ones that cannot dodge `TankTemperatureGenerator`, and §7.3.27 prices
it.

#### 7.3.31 `process-evap-permeation` measured: the thermal chain is one recurrence over trips

2026-09-22, measured before any model change. §7.3.27 priced
`TankTemperatureGenerator` as the largest thing left in the onroad corpus and
said permeation and FVV cannot dodge it. That is still true, and it is now also
measured to be SMALL in the shape the format admits.

**The national default database reproduces all 64 of `process-evap-permeation`'s
rows at 5.630e-06 with every `AverageTankTemperature` cell COMPUTED**, none read
-- better than the fixture's 6.174e-06, because the fixture read 96 of those
cells at the snapshot's six significant figures. The reproduction is
`docs/evap-permeation.md` §6.5's own script with the national catalogue swapped in,
exactly as §7.3.29 did for refueling.

**TTG-2 to TTG-5 reproduce exactly from the national tables.** 5,272 hour
segments and 14,118 soak slices (TTG-2, TTG-3, key sets exact), then per tank
temperature group 5,185 operating segments and 46,470 + 86,416 = 132,886
recorded hot-soak minutes -- `OperatingTemperature`'s and `HotSoakTemperature`'s
row counts exactly, not approximately -- and all 144 `AverageTankTemperature`
cells at <1e-06, the column's own storage floor.

**The shape is ONE recurrence over `SampleVehicleTrip`'s rows, in file order.**
§8.1 of the specification measured that the predecessor of a chained trip is the
immediately preceding non-marker row; the national file is sorted
`(vehID, dayID, tripID)`, so a marker row carries the state through and every
trip reads its predecessor at lag 1. Inside a trip nothing is sequential that
cannot be closed:

* the hour segments' rise composes to `min(140, A·keyOn + B)` -- the cap is
  ABSORBING, because the rise at 140 °F is `a + 15.84 > 0` for every group;
* the hot soak is `T ← T + (1.4/60)(ambient − T)` per minute, geometric within
  an hour slice, so each slice's entry temperature is affine in the trip's
  key-off temperature (`P·keyOff + Q`, with `P` a power of `1 − 1.4/60`);
* the soak's data-dependent early stop -- the minute the tank falls to the
  cold-soak temperature plus 3 °F -- is monotone within a slice, so whether it
  happens ANYWHERE is `keyOff ≤ K` for one threshold `K` per trip; where it
  happens is a `ceil` of a logarithm;
* the end-of-soak temperature the next trip starts from is `U·keyOff + V`.

So the recurrence carries one scalar per `(group, trip)` with two sentinels
(soak ended cold, trip never walked), which is what §4.3.1.1 admits: one
variable, one axis, lag 1. A timing probe on the ingest path -- a lag-1 fold over
all 37,216 national trips for two groups -- evaluates **bit-identically** to
Python in 1.7 s and 20 MB, and 2.2 s with sixteen groups of which fourteen are
masked.

**Why not the flattened timeline MOVES actually walks.** One row per segment and
per soak slice would transcribe the Java directly, but its length is a
data-determined number that every RunSpec would have to declare, and a run that
selects no evaporative process would declare 0 -- which is finding F56, still
open: a computed relation of length 0 panics. Over the trip table the axis is an
extent the mount discovers, and a non-evaporative run masks every trip.

**Five edge cases the reproduction had to get right before it matched**, each
now a rule the document must carry: a soak slice whose next trip starts exactly
on the hour has length −1 and runs zero minutes; 195 national trips end after
midnight and their soak runs from hour 1 back up to 24; 75 trips are never
walked because their chain is broken somewhere upstream (17 directly), which is
TRANSITIVE and is exactly what the "never walked" sentinel propagates; the 140 °F
cap binds on 28 segments; and a soak's first slice can have zero minutes and
still be followed by others.

**The two tables §7.3.27 found absent outright are not work.**
`PollutantProcessMappedModelYear` is an identity copy of
`PollutantProcessModelYear` when `modelYearMapping` is empty, which it is
nationally. `RegClassSourceTypeFraction` is derived at run time from
`fuelUsageFraction ⋈ SampleVehiclePopulation`, and PC-6 sums it away again, so
all that reaches the output is its per-cohort total -- 1 wherever the cohort has
a fuel-usage-weighted sample vehicle.

**One key the model gets wrong today (C2′).** The rate joins decode the
regulatory class from the packed source bin, and permeation's bins carry class 0
because `SourceTypePolProcess.isRegClassReqd` is 'N' for polProcess 111. Only 111
and the chained SO2/NO/NO2 processes are 'N' nationally, and those three have no
rate rows, so collapsing the class for an 'N' process changes nothing already in
`runspecs/`.

#### 7.3.32 `process-evap-permeation` reproduces, and the tank temperature is computed

2026-09-22. All 64 rows, worst cell **5.630e-06**, the number §7.3.31's pandas
reproduction from the national tables reached before the model changed.
**Nineteen RunSpecs in `runspecs/`.**

**`TankTemperatureGenerator` TTG-1 to TTG-5 is in `onroad/model.esm`**, in the
shape §7.3.31 measured: TTG-1's quarter-hour recurrence per county-zone and
month, the trips' flags and bounds as columns over the national
`SampleVehicleTrip`, the soak as a (trip x hour-of-day) grid of entry decays,
offsets and stop thresholds, `ttg_tripState` as the one recurrence over trips,
and TTG-5 at the run's hour. Its six `AverageTankTemperature` cells here agree
with the snapshot's to 7.4e-07, the column's storage floor, and the recurrence
matches an independent numpy walk on all 595,456 cells. The shapes are in
`lib/evaporative.esm` — twenty-one templates, from `segment_rise` to
`soak_recorded_minutes` (conventions §83).

**It was right on its first evaluation and too slow to finish.** The first body
inlined the trip's whole segment composition into the recurrence with three
copies of the key-on template: correct, and over 400 s for 595,456 cells.
Precomputing the rise as `slope x keyOn + intercept` outside the recurrence
took the same chain to 7.5 s. The rule is in conventions §83: a recurrence body
should hold the state transition and nothing else.

**Then the calculator, and two keys the rate path had right by coincidence**
(conventions §84). The rate joins now read the regulatory class the SOURCE BIN
carries for the process — class 0 for polProcess 111, because
`sourceTypePolProcess.isRegClassReqd` is 'N' — and before that every permeation
row was exactly 0 with a perfect key set. And S15's temperature factor is the
identity on a permeation row: `temperatureAdjustment`'s two 111 rows are PC-2a's
exponential in the TANK temperature, not a quadratic in the ambient one, and the
first run that emitted numbers had all 64 rows high by exactly 9.281. PC-2a and
PC-2b are `rtDay_permeationTemperatureAdjust`, PC-3 is
`rt_permeationFuelAdjustment` through three 1-D keys, and the weight replaces
the operating-mode fraction in S14 because PC-1b sums the rate over modes and
weights the temperature adjustment instead. A third correction was an exact answer by luck: PC-3 bins the ethanol volume AFTER `FuelEffectsGenerator`'s high-ethanol substitution, so E85 reads 10 and not the 74 the table ships, and bins 1 to 7 carry identical coefficients nationally, so the first version agreed while binning E85 wrongly.

**Nothing else moved.** Five runspecs run against HEAD — `expand-counties`,
`expand-sourcetype`, `expand-month`, `chain-so2-co2e-mechanism` and
`process-evap-leaks` — are byte-identical, and the price of building the
thermal chain in every run is 10 to 28 s and 0.2 to 0.7 GB each, measured. The
two `RegClassSourceTypeFraction` and `PollutantProcessMappedModelYear` tables
§7.3.27 found absent are not mounted: the first is the identity wherever it
multiplies anything, and the second is the table it would be copied from.

**What is left of the onroad corpus** is `process-evap-fvv` and
`scale-project`. FVV needs, on top of this, TTG-6 and TTG-7 (the soak activity
fraction and the cold-soak initial-hour fraction, both downstream of the same
walk), `TankFuelGenerator` and the tank vapour venting calculator
(docs/evap-fvv.md), and on its on-network link all of the cold-soak side is
multiplied by zero, as it is here.

#### 7.3.33 `process-evap-fvv` reproduces, and the onroad corpus is ported

2026-09-22. All 64 rows, worst cell **7.517e-06**, on the model's first run —
the number the spec's own reproduction reached from the national tables before
the model changed (`docs/evap-fvv.md` §6.5 with the national catalogue, the high-
ethanol substitution applied, and the venting-only inputs from the snapshot,
which is where they are multiplied by zero). **Twenty RunSpecs in `runspecs/`.**

**What went in is the operating insert of TVV-8** (conventions §85):
`TankFuelGenerator`'s `averageTankGasoline` per county, month and fuel type —
TFG-1's market-share means with the NULL rule and the year multiplicity, TFG-2's
zone evaporative temperature and weathering, TFG-3's commingling step as a table
— the interpolation of `evapRVPTemperatureAdjustment` at that RVP as a weight per
knot, the two cubics, and the mode-300 factor on the rate path. 8.0 psi for
gasoline and 7.7 for E85, read at the ethanol volume after `FuelEffectsGenerator`'s
substitution; without it E85 weathers to 7.61 and the E85 cells move.

**What did not go in is the cold-soak insert**, TVV-2 to TVV-7, and the document
says so: it is weighted by a computed exactly-zero on an on-network link, the
spec measures it contributing nothing, and `run_offNetworkLinkCount` is asserted
0, so the first RunSpec that could weight it will fail here instead of silently
dropping it.

**That closes the onroad corpus except `scale-project`**, which is step 7f
because its input is a second database. Every other onroad snapshot with a
`MOVESOutput` either reproduces from the default database in `runspecs/` or is
deliberately not a RunSpec (`mixed-onroad`, a strict subset of `expand-day`),
the eight that emit no rows at all are structural gates, not rungs (§7.3.16), and `mixed-onroad-nonroad` and `sample-runspec` ship no `MOVESOutput` to reproduce. Counted against the snapshot directory, not remembered: 20 of the 32 non-nonroad snapshots are RunSpecs here.

#### 7.3.34 Step 7e begins: three county runs reproduce from the default database

2026-09-23. `nonroad/model.esm` is `fixtures/nr-logging-county.esm`'s model
lifted into a data-open document, `moves-nonroad.esm` mounts it over 21 national
tables, and `runspecs/nonroad/` holds one document per run. **Three nonroad
RunSpecs reproduce**, with the shape each emits recomputed by the chain and
checked by `tools/check-nonroad-shape.py`:

| run | rows | worst cell | points | cohorts |
|---|---:|---|---:|---:|
| `nr-logging-county` | 144 / 144 | 4.561e-06 | 6 | 36 |
| `nr-lawn-garden-county` | 1,936 / 1,936 | 6.718e-06 | 97 | 484 |
| `nr-recreational-county` | 1,010 / 1,010 | 6.354e-06 | 17 | 202 |

**The national tables needed nothing.** Measured against `nr-logging-county`'s
execution database first: 19 of the 21 tables are copied whole, the other two
(`nrfuelsupply`, `regioncounty`) are narrowed there and the fixture already
joined both on the run's fuel region, year and month group. What the fixture
had written into itself instead were five DECLARATIONS a document serving more
than one run cannot make -- the six equipment points, the county, state, year and
day, the base year, a technology window of 100..199 and four pollutants per
cohort -- and each now comes from a table. The equipment points are the
`nrsourceusetype` rows in the RunSpec's `/SOURCE CATEGORY/` packet with a
positive county population, and the packet carries NONROAD's rule that an
EMPTY query runs everything, which is how the four diesel-only snapshots came to
emit every sector. `nr-logging-county`'s 144 rows are **byte-identical to the
fixture's** over every emitted column, through every change that followed.

**`nr-lawn-garden-county` found two lookup rules, with every key right.** Five
of its 31 SCCs were off by 0.002 % to 86 %. NONROAD walks the SCC fallback chain
(exact, `xxxxxxx000`, `xxxx000000`) per (pollutant, technology), not once per
point, and 2265004076's exact rows rate only hp 0 to 6; and a point ON a bin
boundary -- 37 national points sit on one, 2260004071 at 3.0 hp among them --
takes the LOWER bin, where the fixture's inclusive filter read both. Both became
a first-row gather: the lowest `nremissionrate` row whose bin contains the point,
per chain level, which is the lowest hpMin because the file is ascending in it
(measured, and no two bins overlap). **`nr-recreational-county` found SO2**, which
`clcems.f` WRITES from BSFC and the un-adjusted THC rather than reading, so the
rate and deterioration lookups moved onto the axis of what NONROAD always rates.

**F60, found on the way.** The pinned toolchain ignores a MOUNTED leaf's
`domain.element_type` and evaluates it in the root's precision, silently: the
first run of `nr-logging-county` emitted 140 of 144 rows, missing exactly the
cohort binary64 costs (docs/nonroad-logging-county.md §7.3). Each RunSpec
declares `Float32` itself; the 7e stage deletes it from one and requires the
four rows to vanish; and the fix is being worked upstream (docs/findings F60).

**What is left of step 7e**, in the order it will be taken: STATE and NATION
scale (MOVES pre-aggregates zone, temperature and fuel supply to a pseudo-county
-- `PreAggSTATE.sql`, `PreAggNATION.sql` -- and a state run's nonroad fuel supply
is a one-row default), then the non-gasoline fuels (diesel's PM sulfur
correction and `nrSulfurAdjustment`, and the temperature and oxygenate factor of 1
for every kind the table has no row for), then reformulated gasoline if Cook
County needs it, then the air-toxics chain `fixtures/nr-airtoxics-lawn-garden-county.esm`
already computes. **Three of the twelve nonroad snapshots are RunSpecs here.**

#### 7.3.35 State scale: two runs, and three rules a state's pseudo-county carries

2026-09-23. `nr-construction-state` (2,355 of 2,355, worst cell 6.615e-06) and
`nr-pleasure-craft-state` (440 of 440, 6.923e-06) reproduce from the default
database, and the three county runs are unchanged -- `nr-logging-county` still
byte-identical to its fixture. **Five of the twelve nonroad snapshots are
RunSpecs here.**

**A state run is a county run at a county MOVES builds.** `PreAggSTATE.sql`
writes Michigan as county 26000, zone 260000 and fuel region 26, and none of
them is in a national table. So the model builds them: the temperature is a
weighted sum over the state's zones (`zone_runWeight`), the nonroad fuel supply
is one UNION relation of the national rows and `DefaultDataMaker`'s one default
row per `nrFuelType` (`rsu_*`), and nothing is allocated. At a real county each
reduces to the formula it replaced.

**Three rules came out of it, each a number off by a mechanism rather than by
noise.** (1) SO2 was 0: the state's default gasoline is formulation 12, the
default database has no formulation 12, and the `.OPT` packet's func A then
falls back to formulation 10's sulfur while its oxygen query finds nothing.
(2) Every 4-stroke gasoline THC, CO and NOx cell was off by the ratio its
temperature coefficient gives for +0.0049 degF, and PM, SO2 and 2-stroke were
exact: the state's zone weights are rounded to six decimals BEFORE they are
divided and sum to 0.9999322, and MOVES does not renormalize, so the
temperature is `Sum(w x T) / 13` and not a weighted mean. (3) 35 cells in six
SCCs were off by up to 9.2e-4, whole cohorts at a time, at model years whose
`agedist.f` residual is a cancellation -- 5.9e-05 of a fraction whose
neighbours are 0.02. A numpy binary32 replica of the fold matched the model bit
for bit, so the inputs were wrong, and `lib/population.esm`'s
`linear_series_interpolation` associated `(dv x dy) / dx` where `grwfac.f`
computes `(dv / dx) x dy`. One ulp, a thousandfold. It is fixed in the library,
and so in every document that imports it.

**And the output's pollutant axis is what NONROAD EMITS.** `nr-pleasure-craft-state`
selects benzene at three permeation processes, and MOVES writes no row for any:
only pollutants with an output slot do (moves.rs `SLOT_POLLUTANT`). The output
relation is now `n_outputPolProcess` wide, a fourth declared and checked
number, and every record is clamped at zero before it is summed, as
`NonroadOutputDataLoader` does.

**One rule came from the fixture that had found it first.**
`fixtures/nr-airtoxics-lawn-garden-county.esm` had already found the per-technology
chain and the first-bin rule, and a third this model lacked: a (pollutant,
technology) pair `nrdeterioration` has no row for deteriorates by 1, not 0 --
moves.rs's arrays default A to 0.0. No run here has such a pair yet; the diesel
technologies will.

#### 7.3.36 Nation scale: one run at a state MOVES folds

2026-09-23. `nr-commercial-nation` (908 of 908, worst cell 6.729e-06)
reproduces from the default database on the model's first run, and the five
earlier runs are byte-identical -- `nr-logging-county` still to its fixture.
**Six of the twelve nonroad snapshots are RunSpecs here.**

**A nation run is not a sum of state runs.** §7.3.35 said it would be, reading
NONROAD's `prc1st.f` and the national tables, which have no state 0 row
anywhere. The execution database says otherwise: `PreAggNATION.sql` rewrites
every table NONROAD reads as a single state 0 before the run, and NONROAD then
runs once. The model computes each fold from the national rows, with Puerto
Rico and the Virgin Islands left out as the SQL leaves them out
(`state_is_in_nation`, `lib/identifiers.esm`), and each was measured against
this run's execution database first:

| fold | the SQL | measured |
|---|---|---|
| population | `sum(population)` per source type; the `.POP` file rounds the SUM | 1,183 rows, 7e-16 |
| growth pattern | `min(growthPatternID)` per SCC over the states | 246 of 246 |
| month allocation | `nrUSMonthAllocation`'s state 0, a different table | 840 of 840 |
| temperature | `sum(T x startAllocFactor) / sum(startAllocFactor)`, renormalized -- a state's is not (§7.3.35) | 24 hours, 4e-13 |
| fuel supply | `sum(marketShare x actFract)` over regions, `actFract` a region's share of the start activity | 45 shares, 3.6e-7 (the f32 column) |

Each is a weight, a relabelled key or a union that is exactly the old formula
off the nation, the same shape as the state rung's (conventions §87, §88). The
catalogue gains its twenty-third table.

**The first cut of the fuel fold cost every run 890 MB.** It summed each supply
row's region over `regioncounty`, and a join group's candidate pairs are
materialized whatever else narrows them (F58's cost model, ~34 bytes a pair):
94,560 supply rows times their regions' counties is ~14M pairs, and
`nr-logging-county` went from 269 MB to 1.16 GB for a weight that is 1 off the
nation. The SQL itself aggregates per REGION first (`SurrogateRegionActivity`),
and so does the model now: each zone's region, the region's activity by a
self-join over zones (1.8M pairs), and one key per region on its first zone,
which each supply row gathers through once. Logging is back to 304 MB; the
nation run is 468 MB; the five earlier runs kept their bytes.

**Two folds this run cannot see.** Each of its ten SCCs has ONE growth-finder
row, so the minimum over states is that row; and its August fraction is 1/12,
which is also the model's fallback when no month row matches. A probe --
`nr-lawn-garden-county`'s selections at county 0 -- checked both against a
pandas replica of `PreAggNATION.sql` instead: 97 points, every one on an SCC
whose growth pattern differs by state, month fractions from 0 to 0.137, no
mismatch. `nr-railroad-support-nation` carries 31 of those SCCs, so its oracle
will hold both folds to MOVES's numbers.

**What is left is the five 213-SCC runs and the air-toxics run.**
`nr-railroad-support-nation`, `nr-agriculture-state`,
`nr-airport-support-county`, `nr-industrial-county` and `nr-mixed-nonroad`
select diesel, which `nrscc` spells as a nonroad fuel ID the RunSpec does not
use, so each packet is EMPTY and NONROAD runs its whole inventory. They need
diesel, LPG and CNG (the PM sulfur correction, `nrSulfurAdjustment`), and a
technology axis sparser than the cohort x 130 grid, which at that size will
not fit.

#### 7.3.37 Diesel, LPG, CNG and the whole inventory: five runs of 213 SCCs

2026-09-23. `nr-industrial-county` (15,801 of 15,801, worst cell 7.207e-06), `nr-airport-support-county`
(21,068, 7.207e-06), `nr-agriculture-state` (21,120, 6.897e-06) and `nr-mixed-nonroad` (21,328,
6.993e-06) reproduce from the default database, each with its shape recomputed, and the seven
earlier runs still reproduce -- their bytes moved with the printed month fractions (rule 5), their
worst cells did not leave noise. **Ten of the twelve nonroad snapshots are RunSpecs here.** The
eleventh, `nr-railroad-support-nation`, is `runspecs/nonroad/pending/`: every key and the shape are
right, 21,013 of 23,108 cells reproduce, and two residuals are measured and not explained -- every
gasoline SO2 cell 1.38e-4 high by one ratio, though the model's nation gasoline sulfur agrees with
the `.OPT` query on the run's own execution database to 8e-7, and one diesel cohort (2270002066,
model year 2010) off by 0.7 to 1.3e-4 in each pollutant differently. `run-tests.sh` now evaluates
the nonroad RunSpecs four at a time, because five of them take ~9 minutes and ~5 GB each.

**Each of them is NONROAD's whole inventory.** Their RunSpecs select onroad diesel
(2), which `nrscc` spells 23 and 24, so the `/SOURCE CATEGORY/` packet is empty
and NONROAD runs every SCC it has: gasoline, diesel, LPG, CNG and marine, 1,056
to 1,119 equipment points and 5,267 to 5,777 cohorts per run. **The dense layout
fits.** §7.3.36 expected the cohort x 130-technology grid not to; measured, the
model's multi-axis arrays are 0.52 GB at 1,084 points, a run peaks at 4.2 GB and
takes 11 minutes, and a probe RunSpec narrowed to one sector's diesel (a
`runspecfueltype` of 23) reproduces the same cells in three.

**The fuel type is `nrscc`'s, unmapped.** The fixture mapped the nonroad fuel ID
into the onroad namespace through a one-row table that only knew gasoline, whose
ID the namespaces share; MOVESOutput carries 23, 24, 3 and 4 as they are. Every
non-gasoline row had fuelTypeID 0 until that went.

**Five NONROAD rules, each measured before it was written, and each a question of
WHERE an operation applies, or of WHAT NONROAD is handed, rather than of its
arithmetic:**

1. *The `/PM BASE SULFUR/` packet* (`NonroadOptFileSqlHelper.getPMBasedSulfur`):
   `nrSulfurAdjustment`'s diesel rows give each diesel technology an alternate
   base sulfur and sulfate conversion -- T4's conversion is 0.30, not 0.02247 --
   which `clcems.f` uses in the SOx rewrite and in the diesel PM correction
   (`bsfc x 453.6 x hp x load x 7 x soxcnv x 0.01 x (sulbas x adjPM - soxbas x adjSOx)`,
   skipped where the base is 1). The catalogue's twenty-fourth table.
2. *Every technology set is renormalized.* `rdtech_moves.f` divides each (SCC,
   hp range, year) set by its sum, unconditionally; 33 national sets sum to 0.999
   or 1.001, 13 of them the diesel mix in 2011, 2013, 2014 and 2016 -- where
   every diesel CO, NOx and PM cell was off by up to 6e-4 in unequal ratios. The
   listed sum keeps its old job as a guard: `run_mixSetsOffOne` counts populated
   cohorts whose listed mix misses 1 by more than the Fortran's 0.002, and
   `tools/check-nonroad-shape.py` holds it at 0. It earned its place on its first
   run: a probe bound to 17 points too many showed 340.
3. *The clamp is per TECHNOLOGY.* `NonroadOutputDataLoader`'s `Math.max(0, value)`
   is per record, and NONROAD's output record is (SCC, hp, model year,
   technology) -- the file has a technology column. A Tier 4 final diesel whose
   PM rate is 0 or 0.001 g/hp-hr goes negative once its 0.0007 base sulfur is
   corrected to 0.0006 in-use, and MOVES zeroes that record while the cohort's
   other technologies keep theirs. Clamping the cohort sum left 2017-2020 PM up
   to 0.1% low. Found by attributing the residual: a variant with the correction
   switched off gives each cohort's correction as a difference, split by each
   technology's weight, and the gap regressed onto the technologies that can go
   negative. `nr-pleasure-craft-state` moved with it, 6.923e-06 to 5.993e-06.
4. *The rate row's hp bin is the NEAREST one.* `fndefc.f` takes the closed
   interval and keeps the smallest `max(INT(hp - hpMin), INT(hpMax - hp))`
   (`hp_bin_distance`, `lib/keys.esm`). §7.3.34's "lower bin wins" was this rule
   at 25 hp, where [16, 25] is nearer than [25, 50]; `2270003030`'s point at 11 hp
   takes [11, 16] over [0, 11]. The technology mix's lookup (`fndtch.f`) is
   half-open, `(hpMin, hpMax]`, and there the lower bin does win.
5. *The month fraction is the one MOVES printed.* `generateSeasonFile` writes each
   month with `%10.3f` and `rdseas.f` divides the twelve by their sum. The US
   table's six-decimal fractions print to sets summing 0.996 to 1.002, which moved
   every cohort of `nr-railroad-support-nation` by one ratio per SCC -- 0.99361
   for industrial equipment, 1.00317 for construction -- and nothing else
   (`printed_decimal`, `lib/conversion.esm`). Every state row the county and state
   runs read happens to print to a set whose ratio is 1.000000, so those five
   runs could not see it; `nr-commercial-nation`'s fractions are a flat 1/12.

What is left of step 7e is the two railroad residuals and `nr-airtoxics-lawn-garden-county`,
whose chain `fixtures/nr-airtoxics-lawn-garden-county.esm` already computes.

#### 7.3.38 Railroad leaves `pending/`: the reader's window, and one cohort a format cannot narrow

`nr-railroad-support-nation` reproduces: 23,108 of 23,108 rows, key set exact, 23,104 cells at a worst of 1.865e-05 and the four cells of one cohort under a declared exception at 1.342e-04. **Eleven of twelve.**

Both residuals the rung was left with were measured against NONROAD itself. `generate-corpus.sh` (moves.rs `characterization/nonroad-fidelity/`) runs the RunSpec through an instrumented NONROAD in `moves-fixture.sif` in about a minute, and its worker folder holds what no snapshot does: the `.OPT` file MOVES wrote, NONROAD's own `Output.tbl` (equal to MOVESOutput in every cell, so the residuals were inside NONROAD), `NONROAD.BMY` per (SCC, hp, technology, model year), and the `AGEDIST`, `GRWFAC` and `CLCEMS` traces.

1. *Gasoline SO2 was the sulfur NONROAD READS.* MOVES writes `Gas sulfur %` with `DecimalFormat("0.00000000")` and `rdnropt.f` reads `line(21:30)` with `F10.0`: the separating space and nine characters. `0.00066419` arrives as `0.0006641`, 1.374e-4 low, and every gasoline SO2 cell was 1.381e-4 high. The model now reads the in-use sulfur through `opt_option_value` (`lib/conversion.esm`): rounded to eight decimals, then cut to seven. The county and state runs' sulfur levels have no digits past the seventh, which is why they could not see it.
2. *Diesel 2270002066 model year 2010 is the base population's rounding.* `NONROAD.BMY` put the residual on one record, the 87-hp point's T3B, roughly uniform across the four pollutants. The `AGEDIST` trace matched the model's grown fractions to 1e-6 everywhere but that slot, where both sides are tiny: 2010's newest cohort is `totpop/baspop - frcsum`, 1.32300 - 1.32201. And `baspop` differs. MOVES sums the states in binary64 (`PreAggNATION.sql`: 137670.538) and the `.POP` file prints 137670.5. This model sums in binary32 (137670.547) and prints .6. The cancellation turns 7e-7 into 2.4e-4. Forcing the rounding to .5 closes the cohort to 1.6e-5.

The faithful fix is a binary64 sum narrowed once to binary32, and the format cannot express it. esm-spec §11.3.1 refuses an equation whose right-hand side's precision differs from its left-hand side's, and offers no conversion (EarthSciML/EarthSciAST#536). **2026-11-09: a conversion op (PR #674) was declined, as not worth a new AST operation, so this exception is permanent.** The cohort is held instead to 2e-4 by a `cell_exception` in `tolerance.toml`. That is a new, narrow mechanism in `compare-output.py`, keyed by (SCC, model year), with a mandatory reason. It is refused if it matches no cell, and reported as dead weight once the cells are inside the full gate. Every other cell of every run keeps 2e-5. Both residuals were precision artifacts. The difference between them was cost: the sulfur window is one exact template, while the population would need binary64 islands and a new operator.


#### 7.3.39 Speciation and air toxics: the twelfth RunSpec is a root and a multiplier

2026-10-19. `nr-airtoxics-lawn-garden-county` (14,036 of 14,036, key set exact, worst cell
8.537e-06) reproduces from the default database on the port's first run. It is
`nr-lawn-garden-county`'s selections with 29 running-exhaust pollutant-processes: NONROAD's
four, `NRHCSpeciationCalculator`'s five hydrocarbon species, NonHAPTOG, fuel consumption,
PM2.5, and nineteen toxics from five ratio tables. `nr-logging-county`,
`nr-lawn-garden-county`, `nr-pleasure-craft-state` and the 213-SCC `nr-industrial-county`
are **byte-identical** to the pre-change model, in both the emitted relation and the
recomputed shape, at unchanged memory and time. **Twelve of twelve: every nonroad snapshot is a
RunSpec that reproduces from the default database, and step 7e is done.**

**The tables needed nothing, measured first.** The nine tables of
`docs/nr-airtoxics-lawn-garden-county.md` §1.2 are mounted nationally (the catalogue's
twenty-fifth to thirty-third). Every row the execution copies held is in the national
tables at an identical value. The copies were narrowed to the selected pollutants,
running exhaust and the gasoline subtypes, all of them join keys. Washtenaw's nonroad
gasoline supply is the snapshot's 9114 at 1.0 and 9414 at 0.0.
`nrIntegratedSpecies` has fourteen national rows to the copy's nine, and the five extras
are unselected, so they subtract nothing (rule 3).

**The chain is a root and a multiplier, not a second pipeline** (conventions §91). A
selection reads its RATED root's rate, deterioration, adjustment and per-technology clamp
(`rpp_ratedPolProcessID`): THC for the species and the VOC toxics, PM10 for PM2.5 and its
PAH, and the BSFC carrier 9901 for fuel and the dioxins and metals. Each technology record
is then multiplied by `pp_directMultiplier + tech_speciatedMultiplier`. The multiplier is
computed where the tables key it: per (technology, `nrHPCategory`, fuel subtype), folded
by the run's supply shares to a fuel type, and gathered onto the point through its hp
bin's category. That puts the species inside the technology contraction, as the
fixture's 404 distinct CH4/THC ratios require. Off this run the root is the selection
and the multiplier is exactly `1 + 0`, which is why nothing else moved.

**Three rules came from the source and not from this run**, which selects every link and
so cannot see them:

1. *A 2-D key is an axis.* `nrHPCategory` is per (hp bin, technology), and a join key is
   one column, so the category is a two-row axis with a presence mask. A missing row
   matches nothing, which is the Go's zero value.
2. *The supply fan-out is a share-weighted mean over subtypes* (`mworeader.go`), because
   `nrMethaneTHCRatio` and `nrATRatio` key on the formulation's subtype.
3. *The needed set is the selection.* TOG sums only the selected summands, NonHAPTOG
   subtracts only the selected integrated species, and a toxic needs its input block
   selected (`nrhcspeciation.rs` :580, `non_hap_tog_block`, `apply_ratio_details`). Each
   is a selection flag on the term it governs.

**Not ported, all unexercised:** the Go's last-write-wins between tables that share an
output pollutant (the five sets are disjoint nationally), `MXTECH = 32` (as before), and
an emitted TOG row when neither summand is selected. The per-fuel densities and PM2.5
fractions are written and only their gasoline arms are evaluated.

#### 7.3.40 Step 7f begins: `scale-project` reproduces, and a run's catalogue has a domain layer

2026-10-19. `runspecs/scale-project.esm` reproduces its MOVES oracle from the
default database plus the run's PROJECT input database: **125 of 125 rows, key set
exact, worst cell 9.123e-06, per-pollutant sum 1.373e-06**, on the port's first run,
`run_domainUnported` = 0. It is the first RunSpec whose input is not the default
database alone, so it decided the shape the four `-single` runs inherit.

**The measurement came first, and most of the project database is the default
database.** `setup-project.sql` builds 45 tables in `washtenaw_cdb`. 39 are
`INSERT ... SELECT` copies of default rows at the run's keys; `avft` is the
default `sampleVehiclePopulation` summed over regulatory class (AVFTTool's own
query); `opModeDistribution` and `driveScheduleSecondLink` are created EMPTY on
purpose, so `LinkOperatingModeDistributionGenerator` computes the link's
distribution from its average speed; and three tables hold the only rows the SQL
states -- `link` (one 1-mile road-type-4 link, 1,000 veh/h, 30 mph, grade 0),
`linkSourceTypeHour` (all passenger cars) and `offNetworkLink`. MOVES merges the
input database first and the default after it, by primary key
(`MasterLoop.java:203-250`), and in PROJECT domain does not copy the default's
`Link`, `FuelSupply`, `IMCoverage` or `hotellingActivityDistribution` at all
(`InputDataManager.java:1432-1435`, `:2799-2846`). Every execution-database table
was then diffed against the default database at nine significant digits and
against `process-tirewear`'s (same county, year and month): **the only
project-specific differences are the three stated tables, the generator's 122
`OpModeDistribution` rows, the 444 `avft` rows -- after which `sampleVehiclePopulation`
is still the default's -- and `SourceTypePhysics`' renumbering of the physics
vehicles' modes to 1000+** (2,875 `emissionRate`, 23 `fullACAdjustment` and 23
`opModePolProcAssoc` rows), which the model already handles by keying rate and
weight on the base mode and the physics row. Two numbers were reproduced in pandas
from the default database plus the stated rows before anything was ported: `SHO` =
linkVolume x sourceTypeHourFraction x noOfRealDays x ageFraction x
least(length/speed, 1) (`ProjectTAG.java:354-385`), 41 of 41 rows at the snapshot's
six-digit rendering; and the link's operating-mode distribution, already oracled by
`./run-link-omd-oracle.sh` (122 cells). `BaseRateGenerator` in PROJECT domain
takes its core path over that distribution with no average-speed weighting
(`baserategenerator/mod.rs:158, :242`), so nothing else in the rate chain moves.

**The catalogue shape: a DOMAIN layer above the default database** (conventions
§92). A mounting document cannot override a mounted one's `data_sources` (§59.4),
so a table whose merged content depends on the domain cannot live in the default
database's catalogue. `moves-onroad.esm` was split:

| | |
|---|---|
| `onroad/default-database.esm` | the old catalogue less the domain-owned tables: 82 default tables, mounting `onroad/model.esm` |
| `moves-onroad.esm` | the DEFAULT domain: `db_link` (the national `Link`), `db_linksourcetypehour` (the default's, 0 rows), `db_runspecdomain` (`DEFAULT`), mounting the above. The 20 earlier RunSpecs still mount it, unedited. |
| `inputs/washtenaw-project.esm` | the PROJECT database: the same three sources pointed at `inputs/washtenaw-project/` (the stated rows, typed by the default's schemas, and `PROJECT` from the RunSpec XML, all written by `tools/build-scale-input-db.py`), mounting the same `onroad/default-database.esm` |

Each table's merge rule is stated where it is declared. `link` is a REPLACE in
PROJECT domain, which is MOVES's rule and not a shortcut; `linkSourceTypeHour` is a
row merge whose default side is empty, so it is the project's table; and the 39
copies are row merges over identical rows, so they are read from the default
database by the joins that already select them. The `-single` runs will need the
other kind of merge -- input rows overriding default rows of the same key, in
`zoneRoadType`, `roadTypeDistribution` and the like, and a whole-table replace of
`sourceTypeYear` and `sourceTypeAgeDistribution` in SINGLE domain -- and the rule for
those is the same: a replace is a table the domain document declares, and a row
merge is both sources read and a per-key precedence written in the model, with
every computed variable shaped over the DEFAULT axis because the input axis is
mounted empty in every DEFAULT-domain catalogue (F56).

**What the model computes from the domain**, all of it behind `run_isProjectDomain`
and nothing written in the RunSpec document:

1. `act_projectSho` -- ProjectTAG's SHO, in the SQL's association, with
   `link_travel_hours_share` in `lib/onroad_activity.esm`. `act_sho` selects it.
2. `lomd_*`, 33 variables -- `LinkOperatingModeDistributionGenerator` over the
   national `driveScheduleSecond`: backward-difference accelerations with the
   link's grade and no forward fallback for a schedule's first second, the CASE in
   its own order (stopped, idle, braking, the rectangles via a new
   `op_mode_rectangle_contains`), totals over EVERY second, five-decimal quotients
   (`link_op_mode_fraction`), mode 501 folded into mode 1 after rounding, the four
   bracketing INSERTs with the `max(driveScheduleID)` tie-break, and the
   interpolation with non-positives dropped. The link's 21 modes agree with the
   snapshot's `RatesOpModeDistribution` to 2.4e-06, the FLOAT column's rendering.
   `pp_W` selects `lomd_W` for running exhaust and the old expression, now
   `pp_WSpeedBins`, otherwise.
3. `out_zoneID` and `out_linkID` carry the selected zone and link; a PROJECT run's
   output is at LINK detail.

**`run_domainUnported` is the licence**, asserted 0 by `tools/check-runspec-shape.py`
for every RunSpec: a domain table that is not one row; in PROJECT domain a county
whose join selects other than one link, a second county, an emitted process other
than running exhaust, or an out-of-bounds bracket (a MOVES terminal error); and
outside it any `linkSourceTypeHour` row. Each of those would emit a plausible number.
**Not ported, all unexercised and all counted:** brake wear's mode-501 arm, the
project generators of tire wear, start exhaust and the evaporative processes, the
first and third arms of step 100 (a user `driveScheduleSecondLink` or
`opModeDistribution`), multi-link projects, and a grade other than 0 (written, not
exercised). `offNetworkLink` is written and read by nothing, because only processes
on the off-network road type read it. The FLOAT storage of the distribution is not
modelled: it moves a fraction by at most 6e-08 of itself.

**One harness defect turned up on the way.** The `no-link-join` probe has been
vacuous since 7c′: it deleted the county range and `rsc_countyID`, which the
barometric pressure's join still named, so the probe document did not compile and
the harness read the refusal as the numbers moving. It now deletes only the four
joins and emits county 710047702 as its comment always said, the harness fails a
probe that does not evaluate, and `tools/make-runspec-probe.py` walks the mount
chain instead of naming `moves-onroad.esm`.

**Unchanged runs, all twenty.** Every DEFAULT-domain RunSpec in `runspecs/` was emitted at the pre-change commit and again on the branch: the out_* relation is byte-identical on all 20, the eight recomputed shape numbers are identical, and `run_domainUnported` is 0 on each. The 7c spike is byte-identical too, and peak memory moved by under 0.3% (`expand-sourcetype` peaks at 62 GB before and after, which is the pre-existing high-water mark of the corpus and not this change's). All three runspec probes evaluate and move their run: `no-link-join` emits county 710047702, `no-county-join` county 49229 at SHO 10960.9 (it now drops 10 county key pairs, `out_zoneID` and `out_linkID` being two more), and `no-road-type-filter` moves the shape. The Python binding loads `scale-project` and `process-tirewear` too.

#### 7.3.41 The SINGLE-county runs: a county database is two kinds of row merge, and a hotelling run lives on road type 1

2026-10-19. The four `-single` RunSpecs read the default database plus Washtenaw's
COUNTY input database, `washtenaw_cdb`, built by moves.rs from
`county-inputs/washtenaw-county/setup-hotelling.sql` (three runs) and
`setup-starts.sql` (one). Each was measured in pandas from the default database plus
the SQL before the model changed, and each run's merge diff was redone against the
recaptured execution databases (hour 7, road types 1 and 4, the age distribution,
VMT and fuel supply now in the county database).

**The merge, table by table.** MOVES merges the input database first and the
default after it by primary key, and at SINGLE scale does not copy the default's
`SourceTypeAgeDistribution`, `SourceTypeYear`, `HPMSVtypeYear`, `FuelSupply` or
`IMCoverage` at all (InputDataManager.java:1435, :2834-2846). Measured against the
default at the run's keys:

| table | county database | merge | how the port reads it |
|---|---|---|---|
| `zoneRoadType` | 4 rows, the default's values TRUNCATED to 12 decimals (up to 5.75e-10) | row merge, input wins | both sides; `zrt_mergedSHOAllocFactor` writes the precedence |
| `hotellingActivityDistribution` | 12 rows at zone 261610, diesel only, not the default's distribution (3% shore power from 2010) | row merge that ADDS keys (the default's 36 are at 990000) | both sides; `had_isMerged` and MOVES's best-zone choice `hot_activityZoneID` |
| `hotellingHoursPerDay`, `startsPerDay` | 2 rows each | row merge over an EMPTY default side | the domain's table, declared whole |
| `hotellingHourFraction`, `-AgeFraction`, `-MonthAdjust` | created empty | empty both sides | declared; a row at the run's zone was counted by `run_domainUnported` (ported since §7.3.57) |
| `state`, `county`, `roadTypeDistribution`, `year`, `sourceTypeYear` | literal copies | row merge over identical rows (0 relative) | the default's, by the joins that select them |
| `zone` | truncated like `zoneRoadType` | row merge | read by no hotelling path |
| `sourceTypeAgeDistribution`, `HPMSVtypeYear`, `fuelSupply` | `INSERT ... SELECT` of the default's rows at 2020 / fuel region 270000000 | REPLACE | identical at every key read, so the default's (as `washtenaw-project` reads its `fuelSupply`) |
| `IMCoverage`, `link`, `linkSourceTypeHour` | none | REPLACE by nothing; default copied | empty for county 26161 either way; the national `Link` |

`inputs/washtenaw-county-hotelling.esm` carries this over `onroad/default-database.esm`
(the starts database's document arrives with its run), with
their rows written by `tools/build-scale-input-db.py` (which now reads `INSERT INTO t
VALUES` without a column list, writes created-and-never-filled tables with no rows,
and materialises named `INSERT ... SELECT` copies with `--copy`). The DEFAULT and
PROJECT domain documents declare the same input sides, empty or as their databases
state them, so every catalogue mounts every table (conventions §80) and every
computed variable sits on the default side's axis (F56, §92).

**`process-extended-idle-single` reproduces: 50 of 50 rows, key set exact, worst cell
6.529e-06, per-pollutant sum 5.1e-07, on the port's first run once its widths were
declared.** What it needed, all switched by the pollutant-process and nothing
written in the RunSpec:

1. **Hotelling hours as the activity** (`hot_*`): TotalActivityGenerator step 180's
   daily VMT on the restricted-access road types 2 and 4 -- whatever the RunSpec
   selects, which is why `hot_roadDayVMT` has its own road-type factor -- times the
   ROW-MERGED `SHOAllocFactor` and `hotellingRate`, spread over the day by
   `sourceTypeHour.hotellingdist`, and rescaled by AdjustHotelling.sql to the
   domain's `hotellingHoursPerDay` (`hot_dayAdjustment`: 0.99999999995561 for the
   weekday, because the county states the default's own daily total). Reproduced in
   pandas against the execution database's `hotellingHours`, 123 of 123 at 8.2e-08.
   `rtDay_sho` became `rtDay_activityBasis`: SHO, or hotelling hours.
2. **The degenerate operating-mode distribution** of
   RatesOperatingModeDistributionGenerator steps 200 and 210 (`hot_modeWeight`),
   times BaseRateCalculator's `hourFractionAdjust` (`cohMode_hotellingWeight`): the
   merged `hotellingActivityDistribution`'s opModeFraction at the best zone the table
   holds -- the run's own, its state's, or 990000 -- and **1 where that zone has no
   row for the cohort's fuel**, because the Go multiplies only by what it finds.
   Washtenaw's CNG trucks therefore keep their whole extended-idle rate, which the
   oracle confirms on all nine CNG rows.
3. **Road type 1.** The RunSpec selects 1 and 4. `run_roadTypeID` is now the run's
   ON-network road type (the link, zone and VMT shares are read at it), the
   off-network processes live on 1 through `rspp_rateRoadTypeID`, and the output's
   road type -- and so its SCC, `...0190` -- is the pollutant-process's.
   `run_selectionUnported`, a new guard asserted 0 by `tools/check-runspec-shape.py`,
   counts a second on-network road type, an on-road process beside road type 1
   (MOVES would add off-network idle rows), and a hotelling process in a run that
   pre-aggregates time.

**`process-apu-single` reproduces: 91 of 91 rows, key set exact, worst cell 5.848e-06,
per-pollutant sum 4.7e-07, on the port's first run.** It selects one
pollutant-process, 9191, and MOVES emits two processes: the Go BaseRateCalculator
rewrites a process-91 block at operating mode 203, shore power, to process 93
(baseratecalculator.go:1021-1037) and leaves its polProcessID at 91's, so the 93
rows carry every adjustment the APU's do. Reproduced in pandas first (91 of 91 at
5e-06). The model splits the rate at the mode -- `rtDay_meanBaseRate` keeps the
modes a retagging pollutant-process keeps, `rtDay_meanBaseRateShorePower` the
retagged one, and both go through the same S15 tail, now the template
`adjusted_mean_base_rate` -- and gives the process-93 pairs their OWN pair relation
(`shorepowercohort_rows`, `spc_*`), ranked after every own-block pair, rather than a
second slot of `ratecohort_rows`: no rank an existing RunSpec emits can move. A
block emits only where it has a rate at a mode it keeps (`rt_ownBlockEmits`), which
is why Washtenaw's CNG trucks, whose APU rates are all shore power, have a process-93
row and no process-91 one. hourFractionAdjust is per mode: 201's fraction on the APU
rows, 203's on the shore-power rows -- 0.03 from 2010 in the county database, where
the default states none.

**`process-crankcase-extidle-single` reproduces: 300 of 300 rows, key set exact, worst
cell 5.275e-06, per-pollutant sum 6.6e-07, on the port's first run.** Its six blocks
are extended idle's THC, CO and NOx (190, 290, 390) and the crankcase three chained
to them by `runspecchainedto` (117, 217, 317). Measured in pandas first against the
execution database: the parents are extended idle's arithmetic with two factors
energy did not need -- NOx's humidity factor K (1.0095 diesel, 1.0216 CNG), which
`rt_isNoxTotal` already applied to processes 90 and 91, and diesel's biodiesel fuel
ratio for model years 1950-2006 (0.97533, 0.97585, 1.00385 at 3.5% ester), which is
three more rows of the base-rate general fuel ratio `gfb_*` -- and every crankcase
row is its parent times `crankcaseEmissionRatio` alone, 0.037000 exactly on the
pre-2007 diesel cohorts. The one structural change is the ROAD TYPE of a chained
pollutant-process: it used to be the run's, which put 117 on road type 4 and its SCC
on `...0417`. It is now its PARENTS' (`rspp_chainRoadTypeID1..3`, closed over the
chain in the three rungs the model unrolls): on-network if a parent on a selected
road is, road type 1 if only off-network ones are -- so 117 is on 1 with 190, and a
refueling loss stays on 4 with its running-energy parent, because its start and
extended-idle parents are on no road the refueling RunSpec selects.
`run_mixedRoadChains` counts a chained process with parents on both kinds of road.

**`process-crankcase-start-single` reproduces: 684 of 684 rows, key set exact, worst
cell 8.250e-06, per-pollutant sum 3.2e-07.** It is the first RunSpec here to emit
START exhaust, and every piece was reproduced in pandas before the model changed:
starts from the default tables plus the county's `startsPerDay` (41 of 41 at
3.7e-06, the execution database's six-digit rendering), the start arithmetic from the
execution database's base rates (exact to the 0.2 that is `1/noOfRealDays`), and the
135 start fuel-effect strings evaluated directly. What the model gained:

1. **Starts** (`st_*`), AdjustStarts.sql: the stated `startsPerDay` where the domain
   states the day type -- for every source type at once -- else population x
   `startsPerDayPerVehicle`; x the normalised age effect, the month and hour shares,
   the zone's ROW-MERGED `startAllocFactor` (`zn_mergedStartAllocFactor`, the county's
   truncated value, a third shadowing merge) and `noOfRealDays`.
2. **The start operating-mode weights** (`sod_weight`): `startsOpModeDistribution` at
   the day, hour and source type, at age 0 -- MOVES copies it with `select distinct` and
   `INSERT IGNORE`, and its fractions do not vary with age (`run_startModeAgeVariation`
   counts one that would).
3. **StartTempAdjustment**, ADDITIVE per mode (baseratecalculator.go:1339-1350): the LOG
   or POLY increment in `min(T,75) - 75` times the mode's weight fraction, added to the
   weighted rate before the criteria ratio. The weight fraction is BaseRate's
   `opModeFraction`, which carries the source-bin share and NOT the EV-sales back-scaling
   the rate does; with it in, the 2017-2020 THC and NOx cells were 0.84% high, and that
   was the run's only failure.
4. **criteriaRatio at process 2.** Model years 2001 and later: the 135 start strings
   split as conventions §68 split the running ones -- 9 coefficient sets and 135 sulfur
   rows, checked against a direct evaluation of every string on all 2,158 formulations
   (worst 2.9e-14 over 165,297 cells) -- and the five ETHANOL CROSS TERMS (E², E·T50,
   E·T90, E·RVP, E·aromatics) that conventions §68 named as the reason the start strings
   were left out are one more template, `criteria_ethanol_cross_terms`, exactly 0 on a
   running set. Model years 2000 and earlier: the Complex Model's start configurations,
   three more `cmxcfg_*` rows, whose coefficients `complexModelParameters` and
   `sulfurModelCoeff` already carry at process 2.
5. **Crankcase start** (116, 216, 316): the parent times `crankcaseEmissionRatio`, on the
   parent's road type 1, through the chain road-type closure.

Start weights and hotelling weights are both zero on a pollutant-process whose road
type the run does not select, which is what MOVES computes for it: `expand-month`,
`process-refueling` and `scale-project` carry start or extended-idle energy as a
selection or a prerequisite on road type 4 alone, and their bytes did not move.

The start port has a price on every RunSpec, and it is the Complex Model's three
start configurations, which it evaluates over all 2,158 formulations for every county,
month and age before the fuel supply collapses them: on the pinned `esm 0.3.1` peak
memory rose from 3.2 to 4.3 GB on a one-month run, from 6.0 to 11.3 GB on
`expand-counties` and from 7.8 to 15.0 GB on `expand-month` (bisected: the closed-form
rows cost nothing measurable, the three `cmxcfg_*` rows all of it). On the memory-fixed
binary `expand-month` goes from 3.2 to 3.5 GB, so most of the growth is 0.3.1's
match-set retention (EarthSciAST PR #537), but its wall clock goes from 79 s to 184 s.
Narrowing the Complex Model to the formulations the county's supply carries is the
follow-up that would buy it back.

**Unchanged runs.** All 21 DEFAULT- and PROJECT-domain RunSpecs were emitted at
aa077b6 and again after each of the four ports, and each earlier `-single` run again after each later one: every out_* relation is byte-identical and every
recomputed shape number identical, `run_selectionUnported` 0 on each
(`expand-sourcetype` with the memory-fixed binary, `esm.fix9`). The 7c spike is
byte-identical, and the Python binding loads the new RunSpec.

#### 7.3.42 The DEFAULT-domain twins: four runs, no model change, and a selection that was a prerequisite

2026-10-20. `process-apu`, `process-extended-idle`, `process-crankcase-start` and
`process-crankcase-extidle` are the four `-single` runs at the DEFAULT domain: the
same county, year, month, hour and vehicles, no input database. Their snapshots had
0 output rows for the reasons the `-single` ones did, less the county database's:
road type 4 alone (the 90/91/start rates are written on road type 1), crankcase 16
and 17 with no parent, and `process-crankcase-extidle` selecting the gasoline
passenger car, which never extended-idles. moves.rs `7c0f11cd` selects road type 1
beside 4, THC/CO/NOx at processes 2 and 90 as the crankcase parents, and source type
62; `dbda2695` recaptures them with the pinned SIF (`4f92c593`); `f22146a1` quarantines
them in moves.rs's own gate, where the port is off as on the `-single` twins (crankcase
start x2.000, APU x26.6 without shore power, extended idle +59%).

**`process-extended-idle` still emitted nothing, and the reason is a prerequisite.**
It selects Atmospheric CO2 at extended idle (9090), the one RunSpec that runs
CO2AERunningStartExtendedIdleCalculator on an off-network process. MOVES computed
the hotelling hours (123 rows in the execution database) and wrote no `baseRate`, no
`MOVESWorkerOutput` and no output: BaseRateGenerator builds rates only for the
selected pollutant-processes, the default `emissionRate` has 0 rows at 9090 (488 at
9190), and CO2AE is chained onto the energy BaseRateCalculator writes. Nothing
expands the selection: `runspecpollutantprocess` held 9090 alone. moves.rs `4f7098e7` selects 9190
beside 9090, as `chain-so2-co2e-mechanism` selects 9101 beside 9001, and keeps the
CO2. The edge 9090<-9190 is in no `runspecchainedto` row; the model's CO2AE edge
list carries it (`co2aelink_rows`, conventions §77).

| run | MOVESOutput rows | reproduced | worst cell | per-pollutant sum |
|---|---:|---:|---:|---:|
| `process-apu` | 91 (91/91 x41, 91/93 x50) | 91 | 2.505e-06 | 4.3e-07 |
| `process-extended-idle` | 100 (90/90 x50, 91/90 x50) | 100 | 5.422e-06 | 5.2e-07 |
| `process-crankcase-start` | 684 (1,2,3 x 2: 124; x 16: 104) | 684 | 8.250e-06 | 3.2e-07 |
| `process-crankcase-extidle` | 300 (1,2,3 x {90,17}: 50) | 300 | 5.395e-06 | 6.7e-07 |

**All four reproduce on their first run, key sets exact, with no model change.** Each
`runspecs/` document is its `-single` twin's selections over `moves-onroad.esm`
instead of a county document; `run_domainUnported` and `run_selectionUnported` are 0
and the shape checks pass. The DEFAULT arms of every merge were written with the
`-single` runs and are what these exercise: `hotellingHoursPerDay` and `startsPerDay`
empty, so no AdjustHotelling rescale and AdjustStarts' population x
`startsPerDayPerVehicle` arm; the input sides of `zoneRoadType`, `zone` and
`hotellingActivityDistribution` mounted empty, so the default's values and zone
990000.

**The twin pair is a differential test of the merge, and it differs exactly where the
county database does** (conventions §95). Cell by cell, DEFAULT over `-single`, from
the two oracles:

* diesel, every pollutant-process of all four runs: 1 within 6e-06, the oracles'
  six-digit rendering (the county states the default's daily hotelling total, its 990000 mode-200 and
  mode-201 fractions through model year 2020, and the startsPerDay the default arm
  computes);
* shore power (91/93), all 50 cohorts: 0, where the county's 3% from 2010 made them
  non-zero. MOVES still writes the retagged block for every cohort with a mode-203
  rate, at the default's 0.00 fraction; the model's `spc_*` pairs emit the same 50
  zeros;
* CNG extended idle and its crankcase rows: 0.800, the default's mode-200 fraction
  for CNG, where the county states no CNG row and BaseRateCalculator leaves the rate
  unscaled (§7.3.41, item 2);
* starts: equal at every one of the 684 cells (the electric start cohorts are 0 on
  both sides).

**Corpus gates the recapture moved.** `docs/omd-generator-reachability.md`'s counts
(`tools/check-reachability-counts.py`, 13 of 61 claims broken by the recapture, all
61 holding after: two more snapshots with `RatesOpModeDistribution` rows, one more
loading `StartOperatingModeDistributionGenerator`, two more loading
`FuelEffectsGenerator`, and the `kind` histogram) and a `calculator-coverage.py`
docstring that called the eight runs empty. `./run-fuel-effects-oracle.sh`'s
scheduling predicate holds on all 43 snapshots. `build-snapshots.sh` exited 1 under
`pipefail` after a capture whose snapshot no tracked document named yet; it no longer
does.

**Unchanged runs.** Nothing under `onroad/`, `lib/`, `components/` or `inputs/`
changed, so no earlier RunSpec's numbers can move. The four `-single` runs were re-run
against their own snapshots, which the recapture did not touch: 50, 91, 684 and 300
rows at 6.529e-06, 5.848e-06, 8.250e-06 and 5.275e-06, the worst cells §7.3.41 records.

#### 7.3.43 Three wider selections: two axes the model had, and one it does not

2026-10-20. moves.rs captured three RunSpecs that widen a selection the corpus had held
narrow: `expand-fullyear` (every month, `aggregateBy = Month`), `expand-counties-large`
(seven counties in seven states) and `expand-roadtypes` (all five road types). The
first two are wider on axes `expand-month` and `expand-counties` built; the third is
the first on an axis the model does not have.

| run | MOVESOutput rows | reproduced | worst cell | per-pollutant sum | wall / peak RSS |
|---|---:|---:|---:|---:|---:|
| `expand-fullyear` | 1375 = 125 x 11 months | 1375 | 1.056e-05 | 3.4e-07 | 284 s / 7.0 GiB |
| `expand-counties-large` | 875 = 125 x 7 counties | 875 | 1.140e-05 | 2.9e-07 | 184 s / 4.9 GiB |
| `expand-roadtypes` | 729 = 125 x 5 road types + 104 starts | pending | -- | -- | -- |

**`expand-fullyear` and `expand-counties-large` reproduce on their first runs, key sets
exact, with no model change.** Each document is its precedent's with fourteen
`url_template`s moved (`expand-fullyear` also names its own
`selections/expand-fullyear-rateday.parquet`, byte-identical to `expand-month`'s since
both XMLs say `<day id="5"/>`); `n_runspecmonth` and `n_runspeccounty` are discovered
extents, and the 243 month-shaped and 270 county-shaped variables took eleven and seven
without an edit. The overlap is exact rather than close: the model's three
`expand-counties` counties inside `expand-counties-large`, and `expand-month`'s four
months inside `expand-fullyear`, are bit-identical in the emitted CSV, all 125 cells
each -- widening an axis did not move a cell already on it. The seven counties sit in seven fuel regions (`regionCounty` gives each
its own) with seven `zoneMonthHour` profiles; the worst cell per county lies between
6.6e-06 and 1.14e-05, so no county is the outlier. I/M discriminates nothing here: Total
Energy has no I/M adjustment and `IMCoverage` is empty. The eleven months span 26.04 to
76.29 degF collapsed, with the A/C quadratic above its clamp at June to September where
`expand-month` had August alone.

**Eleven months, not twelve, and the execution database is the evidence.** The XML
lists `<month key="1"/>` to `<month key="12"/>`. A month key is a 0-based index into the
sorted `MonthOfAnyYear` IDs (moves.rs `xml_format.rs` `XmlIndexedId`, the reading the
whole corpus was recaptured under), so keys 1 to 11 are monthIDs 2 to 12, key 12
indexes past the twelve-row list and selects nothing, and January would have been key
0, which the XML does not carry. The snapshot's `runspecmonth` and `runspecmonthgroup`
are 11 rows, 2..12, and so is every month-keyed table MOVES cut to the run (`SHO`,
`starts`, `zoneMonthHour`, `totalIdleFraction`, `vmtByAgeRoadwayHour` and eight more);
only `monthOfAnyYear` and the two nonroad month allocations, which are not cut to the
run, carry twelve. January was never selected, rather than computed and dropped, which
is the distinction the oracle alone cannot make (conventions §96). The document reads
the 11 rows and names no month. The fixture presumably meant all twelve; if moves.rs
rewrites it as keys 0 to 11 the document follows without an edit.

**`expand-roadtypes` is pending, priced** (`runspecs/pending/expand-roadtypes.esm`,
WHAT IT WAITS ON). With five road types selected `run_roadTypeID` sums the on-network
four to 14, joins no `Link` row, and the chain emits 104 start rows at county 0 and 0 g;
`run_selectionUnported` is 4. Two pieces:

* *The road type as an axis.* The forward closure of `run_roadTypeID` is 284 of the
  model's 1517 variables, one equation each: 153 already county-shaped, 68 not -- the
  drive-cycle operating-mode stack (`lomd_*` 31, `asb_*` 8, `asd_*` 4, `dsa_*` 4,
  `pp_W*` 5, over `drive_second_rows` x `physicsrow_rows`), the activity VMT and speed,
  the output ordinals -- and 63 per-run, per-pollutant-process and output variables
  whose road type becomes per block. 119 of the 284 reach the road type only through
  the geography ids (`run_linkID`, `run_zoneID`, `run_countyID`, `run_stateID`,
  `run_linkRoadTypeID`), the tank-temperature (`ttg_` 23), tank-fuel (`tfg_` 15) and
  hotelling (`hot_` 12) stacks among them, so with the zone and state found by county
  the promotion is 165 equations. For scale, source type's closure was 125 of 262
  equations and geography's 37, and source type's promotion came to 44 variables
  (conventions §62.1): a closure is an upper bound. The road-type-independent part is already right: this run's
  road-4 block equals `expand-counties`' Washtenaw block on all 125 cells.
* *Off-network idle*, a mechanism the model does not have. Running exhaust on road
  type 1 is 125 rows summing to 31.31 against 240.73 on road type 4, and is
  `TotalActivityGenerator` step 190c: SHO(1) = max(S (TIF - sum_r SHO_r DIF_r / S) / (1
  - TIF), 0) per age, S the on-network SHO of the zone, DIF_r `BaseRateGenerator`'s
  driving-idle fraction per road type (0.00505, 0.05721, 0.03030, 0.12842 here) and TIF
  `totalIdleFraction` at Michigan's idle region 103, county type 1, August, weekday:
  0.245044679. It reproduces the snapshot's age-0 SHO on link 2616101, 188.612, from the
  four on-network values. Its rate is opMode 1 at fraction 1 and a 1 mph bin speed
  (`baserategenerator/drivecycle.rs`). `totalIdleFraction`, `State.idleRegionID` and
  `County.countyTypeID` are in the default database and not yet ingested. ONI is a sum
  across the road-type axis, so it is written after the axis, not before.

The shape check moves with them: the output relation gains a road-type level and is
ragged on it (start on one road type, running on five), and `run_offNetworkLinkCount`
must stop counting a road-type-1 link that carries no evaporative process.
Track B's `expand-multiyear` and `expand-multifuel` are editing `onroad/model.esm` at
the same time, and a 165-equation promotion would collide with an axis promotion of
their own; it was not started here.

**Unchanged runs.** Nothing under `onroad/`, `lib/`, `components/`, `inputs/` or
`moves-onroad.esm` changed (`git diff --stat` on the branch is four new files), so no
earlier RunSpec's numbers can move. As a check on the binary, `expand-counties`
re-run with the memory-fix `esm` is byte-identical to its output from the 2026-10-20
suite run. The suite's runspecs stage picks the two new documents up by `find` and the
pending one by `runspecs/pending/`, so `run-tests.sh` needed only its commentary.

#### 7.3.44 The calendar year is an axis, and `expand-multifuel` discriminates one empty candidate

2026-10-20. Two new snapshots, `expand-multiyear` (241 rows) and `expand-multifuel`
(125 rows), both `expand-day`'s weekday run with one selection widened.

**`expand-multifuel` changes one row of one table and none of the numbers.** Its
RunSpec selects gasoline, diesel, CNG and electricity for the passenger car; MOVES
expands that to five `runspecsourcefueltype` rows, the four every gasoline-only run
here already carries (1, 2, 5, 9) and CNG. The default `sampleVehiclePopulation` has
no (21, CNG) row at any model year, so the fifth candidate of the cohort grid finds
no vehicle. `MOVESOutput` holds fuels 1, 2, 5 and 9, and compared from the oracles
as floats it equals `expand-day`'s weekday block and `process-tirewear`'s 91/1 block
at all 125 cells (maximum relative difference 0). What it discriminates is that
candidate: it is the first run of the 31 whose `runspecsourcefueltype` names a pair
with no population, so a grid that ranked by selection rather than by surviving
cohort, or emitted a zero row per selected fuel, passed the suite until now. It is a
regression, not a fuel test; a CNG cohort needs a source type that has one (42) or an
input database. 125 of 125 on its first run with no model change, worst cell
7.106e-06.

**`expand-multiyear` needed the year, and the year was the run's last scalar.**
`run_yearID` was a `run_rows` faq SUMMING `rsy_yearID` -- 2020 at one year, 4035 at
two -- and the run emitted 241 rows keyed yearID 4035 and model year 658460. Conventions
§65 called the month the last scalar; it was the last one any RunSpec had widened.

**The price, measured before it was paid.** The forward closure from `run_yearID`
reaches **395 of the model's 1,036 equations**, against the month's 32 and the source
type's 125 of 262 when those were priced (§7.3.4). It is that large because the cohort
is an AGE at a YEAR: `coh_modelYearID` is year less age, so every rate keyed by model
year, and the fuel year, the age distribution, the population and the VMT, all move
with it. The closure over-counts by the 199 cohort-shaped equations that inherit an
axis the cohort grid carries without a textual edit, and by the run-level presence
counts (`cohortSurvivorCount`, `rspp_isEmitted`, ...) that are ORs over rates of any
year. What was edited is **160 equations changed and 9 added, 119 variables
reshaped** (conventions §98):

* the cohort grid and the activity relation take the year as their SLOWEST factor
  (`cohort_rows`, `sourcebin_rows`, `rate_rows`, `ratecohort_rows`,
  `shorepowercohort_rows`, `activity_rows`), so at one year each is the relation it
  was row for row; `coh_yearOrdinal`, `act_yearOrdinal` and their gathers carry it;
* 114 per-year relations that are neither -- the fuel supply and every fuel-effects
  term built on it, the tank-fuel and venting chain, the evaporative weights, the
  hotelling and start totals, the population, the VMT and the age distribution --
  gain a trailing `runspecyear_rows` axis, and the four run-level carriers
  (`run_yearID`, `run_fuelYearID`, `run_baseYearIsAnalysisYear`,
  `run_fuelYearMultiplicity`) move from `run_rows` onto it;
* `run_fuelRegionID` lives on a (county, year) pair relation, because `regionCounty`
  is keyed by FUEL year and 528 of the default database's 3,232 counties change region
  between fuel years; on the county relation at two years it would be a rank-2 join
  key, and the fuel-supply joins read only rank-1 keys;
* the 28 rate-side readers of a per-year relation join it at `rt_yearOrdinal`; the
  fuel-usage self-join pairs bins by year as well, because model year 2012 is age 3 at
  2015 and age 8 at 2020 and the two bins are not the same vehicle.

`tools/check-runspec-shape.py`'s cohort key gains `out_yearID`: 135 distinct
(sourceTypeID, fuelTypeID, modelYearID) triples hold the 241 cohorts.

| run | rows | reproduced | key set | worst cell | per-pollutant sum |
|---|---:|---:|---|---:|---:|
| `expand-multifuel` | 125 | 125 | exact | 7.106e-06 | 1.3e-07 |
| `expand-multiyear` | 241 (2015: 116, 2020: 125) | 241 | exact | 8.277e-06 | 2.6e-09 |

**`expand-multiyear` reproduced on the promotion's first run.** Its 2020 block equals
`expand-day`'s weekday block at every cell in the oracles, so the 116 rows at 2015 are
what it adds. It does not discriminate the growth folds (2015 is a base year, §15), and
it selects energy on running exhaust alone, so most of the 114 per-year relations --
the evaporative, hotelling, start and fuel-effects ones -- are computed at two years
and checked only by the single-year runs staying put.

**Unchanged runs, byte for byte.** Every runspec in `runspecs/` -- the 29 that
reproduced before and `expand-multifuel` -- was emitted against the commit before the
promotion and again after it, the out_* relation and the recomputed shape both: all 60
CSVs are identical (`cmp`). `spikes/7c/tirewear_mount.esm`'s relation equals
`process-tirewear`'s, the three selection probes still move their runs, the four
domain documents are still data-open, and the Python binding still loads
`expand-day`. `expand-multiyear` runs in 65 s at 1.98 GB peak RSS against
`expand-day`'s 49 s and 1.87 GB; `expand-multifuel` in 49 s at 1.87 GB.

**Left open.** `run_evTemperatureIsSuppressed` reads `rst_sourceTypeID` at the
one-row `run_rows` symbol rather than at the source type, so under several source
types it tests the first one's; it cannot fire while no run's heat index exceeds 67
degF, and it is left as found (conventions §98 item 2). **Fixed 2026-11-02**
(§7.3.50), by the first capture whose heat index does.

#### 7.3.45 `scale-county`: a complete county database, and a run that waits on the road type

2026-10-20. `scale-county` is the corpus's county-scale INVENTORY: Washtenaw
(26161), 2020, August (`<month key="7"/>` is an index), weekday, hour 7, the
gasoline passenger car, road types 1 and 4, and energy at running, start and
extended idle exhaust plus well-to-pump. Its first capture failed domain-database
validation, because `washtenaw_cdb` as `setup-starts.sql` builds it holds only
what the off-network `-single` runs read, and they skip that validation.

**The county database, moves.rs `c567c808`.** `setup-county.sql` provides every
County Data Manager table, each `CREATE TABLE ... LIKE` + `INSERT ... SELECT` of the
default database's own rows at the run's county, zone, year and fuel region (whole
tables where there is no such key). That is `setup-project.sql`'s rule rather than
`setup-starts.sql`'s twelve-decimal literals, chosen because nothing here is frozen by
an older snapshot, so the bit-exact copy costs nothing and SINGLE should equal
DEFAULT. Where an importer allows one of several alternatives (Starts / StartsPerDay /
StartsPerDayPerVehicle; totalIdleFraction / the idle adjustments; HPMSVtypeYear / the
daily and source-type VMT forms) the one the default populates is the one copied.
Two rows are not copies: `avft`, which MOVES3+ requires non-empty and which is
AVFTTool's default projection of `sampleVehiclePopulation`, and `auditLog`'s "No I/M
Program" flag, without which the county I/M check refuses the empty `IMCoverage` that
Michigan has.

**The GenericImporter error is real, harmless to MOVES, and fatal to the capture.**
With validation ON, MOVES logged "Done performing domain database validation." and
ran to completion with 729 rows. Its one `ERROR:` line is `ImporterInstantiator is
unable to instantiate ...GenericImporter`: GenericImporter's constructor builds a
Swing `TableFileLinkagePart`, `JComboBox.addItem` asks for font metrics, and
`libfontmanager.so` needs `libharfbuzz.so.0`, which the pinned SIF lacks. The
instantiator returns null and the manager skips that importer. It is raised at
construction, before any table is read, so it appears whenever validation runs, with
or without the missing tables; moves-log-scan.sh treats every `ERROR:` line as
terminal. `scale-county.xml` therefore skips validation like the other five
SINGLE/PROJECT fixtures, and the capture (moves.rs `cadac923`) is clean.

**The oracle is the DEFAULT run's.** MOVESOutput is 729 rows of Total Energy:
running exhaust on road types **1 through 5**, 125 each, and start exhaust on road
type 1, 104. Petroleum and fossil energy (92, 93) and well-to-pump (99) are not
MOVES5 pollutant-processes, and the passenger car never extended-idles. Selecting
road type 1 beside a running process makes MOVES select every road type ("Off-Network
Idle requires all roadtypes"), so the run is `expand-roadtypes` at SINGLE scale.
**All 729 rows equal `expand-roadtypes`' at the same key**, at the six-digit
rendering. Diffing the two execution databases table by table: every table the model
reads is identical but `sourceTypeYear`, `sourceTypeAgeDistribution` and
`HPMSVtypeYear`, which hold the 2020 rows alone (MOVES's SINGLE-scale REPLACE), plus
`avft` (with `sampleVehiclePopulation` unchanged), the 9190 selection's rows, and two
tables the output does not depend on, since all 729 rows agree: `starts` (41 rows at
DEFAULT scale, 0 at SINGLE) and `sbWeightedEmissionRate` (832 and 0).

**The domain document, `inputs/washtenaw-county.esm`**, declares the input sides the
`-single` documents do, written by `tools/build-scale-input-db.py --copy`: `zone` and
`zoneRoadType` bit-exact copies (shadowing merges that return the default's values),
the hotelling tables and `startsPerDay` empty. The tool now skips `auditLog` and the
three tables the default ships schema-only. Checked on its own, with the selections of
a run that reproduces: `process-crankcase-start` mounted on it emits a relation
**byte-identical** to its DEFAULT run's, and reproduces `process-crankcase-start-single`'s
oracle at its worst cell, 8.250e-06 (1.3e-10 to 2.1e-10 from the starts county
database, whose zone factor is truncated).

**What it waits on: the road type as an axis** (`runspecs/pending/scale-county.esm`,
conventions §100). The model's on-network road type is one scalar,
`run_roadTypeID`; over four rows it sums to 14, the zone and county joins find
nothing, and every row comes out at county 0. `run_selectionUnported` says so: 4 (three
extra on-network road types, one running process beside road type 1). Three pieces,
all shared with `expand-roadtypes`:

1. **Running exhaust on each on-network road type**: SHO per road type (VMT x
   `roadTypeVMTFraction` over the road's speed) and the average-speed operating-mode
   distribution `pp_W` per road type. The forward closure of `run_roadTypeID` is
   **283 of 1,036** equations, against county's 37 and source type's 125.
2. **Off-network idle**, running exhaust on road type 1 (TotalActivityGenerator step
   190c): per age, `max(S x (tif - SD/S) / (1 - tif), 0)`, S the on-network SHO summed
   over road types 2-5 and SD the same weighted by each road's `drivingIdleFraction`;
   `tif` is `totalIdleFraction` at the state's idle region (103), the county type (1),
   the month, day and model-year window. Reproduced in pandas from the execution
   database: **41 of 41 ages at 3.9e-06**. `drivingIdleFraction` is operating mode 1's
   share of the road's speed-weighted distribution (moves.rs
   `baserategenerator/drivecycle.rs:427-492`), so it is a contraction of item 1's
   `pp_W`. The rate on road type 1 is not yet measured.
3. **A pollutant-process on several road types**: the output's blocks become
   (pollutant-process, road type) pairs; `rspp_rateRoadTypeID` is one road type each.

Not attempted here, deliberately: the promotion is not a localized edit, two other
tracks are editing `onroad/model.esm` concurrently, and `expand-roadtypes` is its
natural first carrier. Once it reproduces, `scale-county` should follow as the §95
twins did, with no model change: its county database changes nothing the model reads.

**Corpus gates.** `docs/omd-generator-reachability.md`'s counts move with the new
snapshot (45 directories, 44 traced; 63 of 63 claims hold on the TRACKED corpus), and
the four corpus-sweeping oracles (`run-omd-oracle.sh`, `run-link-omd-oracle.sh`,
`run-fuel-effects-oracle.sh`, `run-new-tvv-year-oracle.sh`) pass on it. The seven
untracked snapshots in the shared moves.rs checkout move the counts again when
committed.

**Unchanged runs.** Nothing under `onroad/`, `lib/` or `components/` changed. The
three existing domain documents' input files regenerate byte-identically under the
edited tool.

#### 7.3.46 The road type is an axis, and off-network idle is a sum across it

2026-10-20. `expand-roadtypes` and `scale-county` (§7.3.43, §7.3.45) wait on the
same two things: the road type as an axis of the onroad model, and MOVES's
off-network idle (ONI). This section is written in two passes: the price and the
design, committed before `onroad/model.esm` was touched, and then what was done.

**The price, by forward closure (conventions §96).** `run_roadTypeID` reaches 284 of
the model's 1,526 variables (1,045 equations). With the zone and the state found by
COUNTY rather than through the county's link on the run's road type -- the closure
cut at `run_linkID`, `run_zoneID`, `run_countyID`, `run_stateID` and
`run_linkRoadTypeID` -- it is **165**: `lomd_` 31, `rtDay_` 21, `rspp_` 20, `run_`
19, `out*` 20, `evap_` 9, `asb_` 8, `act_` 7, `pp_` 5, `asd_`/`dsa_`/`spc_`/`pcoh_`
4 each, and the rate/output ordinals and survivor counts. A closure is an upper
bound; the design below decides which of the 165 carry the road type as data and
which only inherit it.

**The design: the rate side FOLDS the road type, the activity side APPENDS it**
(the §98 rule, "fold where the rows already move, append elsewhere").

* *Rate side: a (pollutant-process, road type) block.* `rspp_rateRoadTypeID`
  already gives every pollutant-process a road type, so the rate relation already
  varies with it; it varies with ONE value. The rate relation's leading factor
  becomes the pair relation `polprocroad_rows` = `n_runspecpollutantprocess x
  n_runspecroadtype`, road-type-FASTEST, so at one road type it is the
  pollutant-process relation row for row, and on the eight runs that select road
  types 1 and 4 each pollutant-process's one live block keeps its rank among the
  emitted ones (the output order is unchanged). `rate_rows`, `ratecohort_rows` and
  `shorepowercohort_rows` take it; `rt_polProcOrdinal` becomes a gather through the
  block (`rt_blockOrdinal`, `rt_roadTypeOrdinal`), so the ~20 per-pollutant-process
  readers keep their joins. A block is LIVE when its road type is where the
  pollutant-process lives: road type 1 for an off-network one (start, extended
  idle, APU and what they chain to), every selected on-network road type for an
  on-network one, and road type 1 as well for running exhaust (process 1) in a
  non-project run that selects an on-network road type -- ONI. The emitted-block
  rank (`rspp_outputOrdinal`) and the shore-power keep move to the block; the
  per-pollutant-process presence tests become ORs over its blocks. Rate rows that
  join rate rows -- the chain generations, the NonHAPTOG and SPM self-joins and
  the four presence passes -- pair by road type as well as by bin or cohort: a
  forgotten key there sums road 1's parent into road 4's child (conventions §98
  item 4).
* *The operating-mode weights are per block.* `pp_W` and its `pp_WSpeedBins`
  move from the pollutant-process to the block, and the speed-bin stack under them
  gains a trailing road-type axis: `asd_*` (the speed distribution and its time
  pre-aggregation) and `asb_*` (the bracketing schedules and their mode
  fractions). `dsa_*` need no axis: a `driveScheduleAssoc` row already HAS a road
  type, so its selection becomes "a selected road type" instead of "the run's".
  Road type 1's running exhaust is the idle mode at fraction 1
  (`baserategenerator/drivecycle.rs`: opMode 1, avgSpeedFraction 1, and only
  process 1 is written there).
* *Activity side: a trailing road-type axis* on the VMT-to-SHO chain:
  `run_roadTypeVMTFraction`, `run_shoAllocFactor`, `act_annualVMT`,
  `act_timeVMTFraction`, `act_averageSpeed`, `act_vmt`, `act_projectSho`, `act_sho`,
  `act_sourceHours`. The activity relation itself is NOT folded: it also carries
  starts and hotelling hours, which have no road type, and a fold would make every
  per-day and per-year SUM over activity rows count each road type once (the
  too-wide join of the memory rule). `rtDay_activityBasis` and `out_SHO` read
  `act_sho` at their block's road type.
* *ONI is a sum across that axis*, written after it: per activity row, county,
  source type and month, `SHO(1) = max(S (tif - SD/S) / (1 - tif), 0)` with `S` the
  on-network SHO summed over the selected road types and `SD` the same weighted by
  each road's driving-idle fraction, which is operating modes 1 and 501's share of
  that road's speed-weighted distribution (`drivecycle.rs:427-492`) -- a contraction
  of the per-road-type `asb_modeFraction` x `asd_effectiveFraction` the rate side
  already needs. `tif` is `totalIdleFraction` at the county's state's idle region
  (`State.idleRegionID`), `County.countyTypeID`, the source type, month, day type and
  model-year window: three columns and one table the model mounts new.
* *Geography by county.* `run_zoneID` and `run_countyID` come from `Zone` by its
  `countyID` (a new column of a mounted table), not from the county's link on the
  run's road type; `run_stateID` is arithmetic on the county as before. The
  project-link quantities (`run_link*`, `lomd_*`, `act_projectSho`'s link join)
  keep one road type: a PROJECT run is one link, and `run_roadTypeID` is redefined
  as the run's lowest selected on-network road type -- that link's road type at
  project scale, and the representative the three-rung chain closure classes an
  on-network pollutant-process by. `lomd_*` therefore needs no axis.
* *What is counted rather than ported.* An evaporative process on more than one
  on-network road type (its SourceHours and soak weights are per link in MOVES and
  summed here), an on-road process other than running exhaust beside road type 1
  (brake wear has no road-1 rate rows, `drivecycle.rs:513`; tire wear's road-1
  arm and the evaporative SHP arm are not ported), and any `idleModelYearGrouping`, `idleMonthAdjust` or
  `idleDayAdjust` row (AdjustTotalIdleFraction.sql's override and multipliers;
  empty in the default database and in Washtenaw's county database) stay in
  `run_selectionUnported` / `run_domainUnported`. (The idle tables are ported
  since §7.3.57 and no longer counted.)

ONI's open question has an answer in the source: the SQL sums `SHO` over the links
of the zone's execution database with `roadTypeID <> 1`
(`TotalActivityGenerator.java`, the step-190 `insertSelect` into `SHO`, both the
inventory and rates branches), and the execution `link` is cut to the run's road
types, so it is the SELECTED on-network road types. But a run that selects road
type 1 and running exhaust outside project scale never has fewer than all four:
`ExecutionRunSpec.getRoadTypes()` adds every road type ("Off-Network Idle requires
all roadtypes", `ExecutionRunSpec.java:994-1004`). The model sums over the selected
ones, which is the SQL, and the selection is the snapshot's.

**What was done** (conventions §101, §102). The design went in as priced; the
edit is **69 equations changed, 30 added, 4 removed and 2 renamed, 26 variables
reshaped**, against the 165-equation closure:

* the pair relation `polprocroad_rows` (`ppr_*`: ordinals, road type, liveness,
  emitted rank, shore-power keep), the rate, rate-cohort and shore-power
  relations' leading factor, and `rt_blockOrdinal` / `rt_roadTypeOrdinal` /
  `pcoh_blockOrdinal` / `spc_blockOrdinal`; `rspp_outputOrdinal` and its prefix,
  `rspp_shorePowerKept` and `rspp_shorePowerPairs` are gone, their block forms
  replacing them;
* a trailing `runspecroadtype_rows` axis on 22 variables -- `asd_*` 4, `asb_*` 8,
  `run_roadTypeVMTFraction`, `run_shoAllocFactor`, `act_*` 7 and `act_networkSho`
  -- and the block on `pp_W`, `pp_WSpeedBins` and the three diagnostics under them;
* the 11 rate-row self-join clauses pair by `rt_roadTypeOrdinal`;
* `run_zoneID` and `run_countyID` from `Zone` by `zn_countyID`; `run_roadTypeID`
  the lowest selected on-network road type, read by the project link and the chain
  closure only;
* off-network idle: `dif_*` (the driving-idle fraction, 3), `oni_*` (4),
  `run_idleRegionID`, `run_countyTypeID`, the `off_network_idle_sho` template, and
  16 mounted columns of `Zone.countyID`, `County.countyTypeID`, `State`,
  `totalIdleFraction` and the three idle-adjustment tables -- five new sources in
  `onroad/default-database.esm` and in the 7c spike's catalogue;
* the shape check keys a block by (pollutantID, processID, roadTypeID);
  `run_offNetworkLinkCount` counts evaporative blocks on road type 1;
  `run_selectionUnported` counts an evaporative process on a second on-network
  road type and an on-road process other than running exhaust beside road type 1.

All of it was hand-written. The edits were applied to `onroad/model.esm` by a
scratch script that splices hand-written equations into the JSON and reserializes
it in the file's own format (it round-trips the unedited file byte for byte); two
mechanical parts of it are loops -- appending the trailing axis to a listed set of
equations (output index, range, and reads of the listed names) and appending the
road-type pair to every `["b", "b2"]` self-join clause -- each checked afterwards by
track B's axis checker (every index read against its symbol's set; no new
findings) and by a scan that every referenced name exists.

| run | rows | reproduced | key set | worst cell | per-pollutant sum | wall / peak RSS |
|---|---:|---:|---|---:|---:|---:|
| `expand-roadtypes` | 729 | 729 | exact | 1.009e-05 | 6.3e-07 | 59 s / 1.89 GB |
| `scale-county` | 729 | 729 | exact | 1.009e-05 | 6.3e-07 | 69 s / 1.91 GB |

By block, `expand-roadtypes`' worst cell is 8e-06 on road type 1's off-network
idle, 1.0e-05, 9e-06, 7e-06 and 8e-06 on road types 2 to 5, and 8e-06 on start
exhaust; the five running blocks sum to 31.311628, 51.089656, 62.824040,
240.727522 and 303.729604 against MOVES's 31.311621, 51.089675, 62.824012,
240.727491 and 303.729216. Off-network idle reproduced on the first run, rate and
SHO both: the rate is the idle mode at weight 1 and needed nothing the rate side
did not already compute.

**Unchanged runs, byte for byte.** Every RunSpec in `runspecs/` -- all 33 -- was
emitted from a frozen clone of the starting commit (`e91c62c`) and again from the
branch, the out_* relation and the recomputed shape both: **66 of 66 CSVs
identical** (`cmp`), including the eight that select road types 1 and 4, where the
rate relation is now twice as wide and each pollutant-process has one live block
of two. `scale-county`'s relation is byte-identical to `expand-roadtypes'` in all
27 emitted columns: the county database changes nothing the model reads, as
§7.3.45 measured on the execution databases. Wall clock moved by under 5% on 31
runs (`expand-month` 122 -> 124 s at 3.5 GB, `expand-counties-large` 201 -> 202 s
at 5.1 GB, peak RSS unchanged to 0.5%); the two `process-crankcase-start` runs went
57 -> 70 s, the doubled rate relation of six pollutant-processes on two road
types.

**Probes and bindings.** The three selection probes evaluate and move their
runs: `no-link-join` (now dropping the county join from `Zone` as well as `Link`)
emits county 101483769, the national `Zone`'s sum, at SHO 0; `no-county-join`
still drops 13 county pairs; `no-road-type-filter` puts start exhaust on road type 4,
and the chain recomputes two blocks and 229 pairs where the run emits one block. The 7c
spike, its data-open control, rename and bindings probes are unchanged, the five
domain documents are still data-open, `tools/check-sources.py` finds every new
file and column, and the Python binding loads `expand-day`, `expand-roadtypes`,
`scale-county` and `process-crankcase-start`.

**Left open.** Off-network idle is checked on one run pair, one source type and an
unaggregated day: under `aggregateBy` its `totalIdleFraction` day would be the
synthesized output day, so an ONI block in an aggregating run is counted by
`run_selectionUnported` (it joins the hotelling and start blocks there). Brake
wear, tire wear and crankcase running on several on-network road types run
through the same block machinery but no snapshot discriminates them; the
evaporative processes on several road types, and every on-road process but running
exhaust beside road type 1, stay counted. The model sums ONI over the SELECTED
on-network road types, which no run here can tell from all four.

#### 7.3.47 Rates scale: a rate per mile at each speed bin, and the output is a different table

2026-10-21. `scale-rates` and `rates-minimal` are the corpus' two Rates-scale
RunSpecs (`<modelscale value="Rates"/>`, MOVES's MESOSCALE_LOOKUP, DEFAULT
domain) -- one RunSpec under two names. Their `MOVESOutput` is EMPTY; the oracle is
the output database's `RatePerDistance`, 2000 rows: running Total Energy (91/1)
for the 125 (model year, fuel type) cohorts of passenger cars on road type 4,
at each of the 16 average-speed bins. This section is written in two passes: the
measurement, the design and the price, committed before `onroad/model.esm` was
touched, and then what was done.

**What MOVES does, from its source** (the pinned SIF's `/opt/moves`):

* *A speed bin is a link.* `ExecutionRunSpec.createMesoscaleLookupLinks`
  (`ExecutionRunSpec.java`, called for MESOSCALE_LOOKUP outside PROJECT) deletes
  `Link` and writes one link per (zone, road type, speed bin), `linkID =
  (zoneID*10 + roadTypeID)*100 + avgSpeedBinID`, and one per (zone, road type 1)
  without the bin. The snapshot's execution `link` is exactly those 16 rows,
  261610401..261610416, with `linkAverageSpeed` the bin's `avgBinSpeed`.
* *The rate is the bin's, not the road type's.* `BaseRateGenerator.generateBaseRates`
  sets `applyAvgSpeedDistribution` only at MACROSCALE, so at Rates scale running
  exhaust keeps `avgSpeedBinID` (`useAvgSpeedBin`) and divides by `avgBinSpeed`
  (`emissionRate = sum(MeanBaseRate)/avgBinSpeed`); `BaseRateCalculator.sql`'s
  `Rates`/`NotProject` section selects `avgSpeedBinID = mod(linkID,100)`.
* *The source-bin weighting is NORMALIZED* (step 008): at Rates scale
  `SBWeightedEmissionRate` divides by `SUM(sbd.SourceBinActivityFraction)` over
  the (source type, pollutant-process, model year, fuel type, operating mode, age
  group, regulatory class) group the inner join on the rate table leaves, and
  `applySourceBinDistribution` (`sumSBD`) is off for running exhaust. A rate is per
  vehicle OF THAT FUEL, not a share of the fleet.
* *The output table.* `MesoscaleLookupPostProcessor` runs
  `RatePostProcessorRatesFirst.sql` after unit conversion: `RatePerDistance` is
  `BaseRateOutput.emissionRate` for processes 1, 9, 10, 15 (and 11-13, 18, 19 off
  road type 1), with `dayID`/`hourID` unpacked from `hourDayID`, and
  `temperature`/`relHumidity` from `ZoneMonthHour` at the zone, month and hour.
  `regClassID` is BaseRateOutput's 0. `MOVESOutput` is then deleted by the
  "truncate MOVESOutput" performance setting (`OutputProcessor.java`).

**Measured before porting, in pandas against the snapshots.** (1) The snapshot's
own `baserate_1_2020` (rates, per bin and mode) and `expand-day`'s (inventory,
collapsed) agree as `inventory = sumSBD x Sum_bin avgSpeedFraction x Sum_mode
rates`, 125 of 125 cohorts within 5e-06. (2) End to end, `expand-day`'s day-5
`MOVESOutput` against this run's `RatePerDistance` -- same county, year, month,
hour, source type and road type -- satisfies `emissionQuant(c) / (N(c) x
Sum_bin avgSpeedFraction x avgBinSpeed x ratePerDistance(bin, c))` constant across
each model year's fuel types to 5e-06, with `N(c)` the sum of the run's
`sourceBinDistributionFuelUsage` fractions over the cohort. The units are the
inventory's (Million BTU, then per mile), the meteorology is the inventory's,
and every adjustment the inventory applies is linear in the rate and applies
unchanged (`baseratecalculator/adjust.rs` treats `emissionRate` and `meanBaseRate`
alike). So the rate is what the model already computes, at a one-bin speed
distribution, divided by `N` and by the bin speed.

**The design: the scale is a selection, and the rate relation is a second output
relation.** Rates scale switches nothing the inventory computes; it ADDS a
relation, and the corpus' 35 runs are its degenerate case.

* *The datum.* `<modelscale>` is stated in no table, so it is a RunSpec
  declaration, `n_ratesScale` (0 at inventory scale, the default; a Rates RunSpec
  binds 1), beside `n_outputRate`. It sizes `ratespeedbin_rows`, `1 + n_ratesScale
  x (n_avgspeedbin - 1)`: the 16 discovered bins at Rates scale and ONE bin
  otherwise, so an inventory run computes the new relation over a single bin it
  never emits rather than over an empty axis (F56).
* *The weights per bin.* `pp_WSpeedBins` is `Sum_bin asd_effectiveFraction x
  modeFraction(bin)`; the per-bin factor becomes `pp_WBin` and `pp_WSpeedBins`
  reads it -- the same products in the same order, so the inventory's bytes do
  not move.
* *The normalization.* `rtMode_activityFractionSum` is the SQL's denominator: the
  used fractions of the rate row's siblings -- same block, cohort and regulatory
  class -- that have a rate at the mode (`rtMode_rateRows`); `rtMode_normalizedRate`
  divides `rtMode_weightedRate` by it.
* *The rate, per bin.* `rtBin_meanBaseRate` and `rtBin_meanBaseRateACAdj` contract
  the mode against `pp_WBin` at the bin; `rtBin_adjustedMeanBaseRate` is the same
  `adjusted_mean_base_rate` template the inventory uses.
* *The relation.* `rateoutput_rows` is the output relation times the bins
  (bin fastest), so every key column is read from `out_*` through one ordinal
  join (`lib/rates.esm`'s `rate_output_column`), and the new columns are
  `rpd_linkID` (the link formula, also in `lib/rates.esm`), `rpd_avgSpeedBinID`,
  `rpd_temperature`, `rpd_relHumidity`, `rpd_regClassID` (0) and
  `rpd_ratePerDistance` (the per-bin rate over the bin speed and the unit
  divisor, summed over the output row's rate rows). `out_*` keeps its meaning and
  is not compared at Rates scale.
* *What is counted, not ported* (`run_ratesUnported`, inside
  `run_selectionUnported`): at Rates scale, any emitted block other than a
  directly rated running-exhaust block on an on-network road type (a start, an
  evaporative or hotelling process, brake or tire wear, a chained pollutant, or
  off-network idle: `RatePerStart`, `RatePerVehicle`, `RatePerProfile` and
  `RatePerHour` are not built), PROJECT domain (its rate is per link speed), and a
  run that aggregates hours or day types. Distance units other than miles are a
  RunSpec setting no table records; the model writes per mile.

**The harness.** A runspec names its oracle by the table its `oracle` source
points at; `run-tests.sh` reads it, emits `rpd_*` for `rateperdistance` and
`out_*` otherwise, and `compare-output.py --table` takes the table's column contract
from `tolerance.toml` (`[oracle_table.rateperdistance]`; `[compare]` stays
MOVESOutput's). The shape check reads the prefix off the emitted header and, for
a rate table, adds the bin factor.

**The price.** No axis is promoted: 1 equation changed (`pp_WSpeedBins`, to read
`pp_WBin`) plus `run_selectionUnported`'s new term, about 30 added (`pp_WBin`, 2
normalization, 3 per-bin rate, 5 ordinals, 17 `rpd_*` columns,
`run_ratesUnported`), 1 metaparameter, 2 index sets and one template file. The
forward closure of the change into the existing 35 runs' emitted relations is
`pp_WSpeedBins` alone.

**What was done** (conventions §103, §104). The design went in as priced: **2
equations changed (`pp_WSpeedBins`, `run_selectionUnported`) and 29 added**
(1,071 -> 1,100 equations, 1,567 -> 1,596 variables), `n_ratesScale` and the two
index sets, `lib/rates.esm` (`rate_output_column`, `mesoscale_lookup_link_id`) and
`flat_relation_major`/`_minor` imported from `lib/keys.esm` for the ordinals. One
thing the price missed: a binding reaches the model only through the relay of
every catalogue between it and the runspec (§49.1), so `n_ratesScale` is declared
and passed on in `moves-onroad.esm`, `onroad/default-database.esm` and the four
`inputs/` domain documents, as `n_outputRate` is. All of it was hand-written and
applied to `onroad/model.esm` by a scratch script that splices the equations into
the JSON and reserializes it in the file's own format (it round-trips the unedited
file byte for byte); nothing in it is a loop over equations. `tools/make-runspec-probe.py`'s
`no-county-join` now drops 17 county key pairs, the four new ones being the rate
relation's.

| run | rows | reproduced | key set | worst cell | ratePerDistance sum | wall / peak RSS |
|---|---:|---:|---|---:|---:|---:|
| `scale-rates` | 2000 | 2000 | exact | 1.163e-05 | 6.8e-08 | 50 s / 1.87 GB |
| `rates-minimal` | 2000 | 2000 | exact | 1.163e-05 | 6.7e-08 | 48 s / 1.87 GB |

Both reproduced on the model's first run. The worst cell is electricity at bin 1
(2.5 mph), a rate of 2.56e-04 MMBtu/mile; `temperature` and `relHumidity` match to
1.7e-08 (binary32 90.4 against its six-digit rendering). The model's two emitted
relations are byte-identical to each other, as the runs' selections are. **The two
snapshots differ in one cell**: diesel, model year 2016, link 261610412 (55 mph),
0.00299941 in `scale-rates` and 0.00299940 in `rates-minimal`, exactly one unit of
the sixth significant digit a MySQL FLOAT is rendered to (3.3e-06). It is MOVES's
own run-to-run noise -- most likely float32 sums accumulated in a different order,
landing either side of a rounding boundary -- and the model's 0.0029994027 lies
between them, 2.4e-06 from one and 9.1e-07 from the other. The shape check
recomputes 2000 = 125 pairs x 1 zone x 1 month x 1 day x 16 bins, every link's
last two digits its bin, and every unported count 0; at Rates scale
`run_ratesUnported` is live (a probe binding `process-crankcase-start` to Rates
scale counts its 6 start and chained blocks).

**Unchanged runs, byte for byte.** Every RunSpec in `runspecs/` -- all 35 --
was emitted from a frozen clone of the starting commit (`16734e5`) and again from
the branch, the out_* relation and the recomputed shape both: **70 of 70 CSVs
identical** (`cmp`). Wall clock moved by a median -0.6% (worst +5.9%,
`process-brakewear` 46.9 -> 49.7 s) and peak RSS by a median 0.1% (worst +0.9%; the
corpus high-water mark is `expand-fullyear` at 7.36 GB before and after). The 7c
spike and its thin fixture document are byte-identical (375 rows); the three
selection probes evaluate and move their runs (`no-county-join` again emits
county 49229 at SHO 10960.9); `compare-output.py --self-test` covers the table
switch; the conventions, sources, filter-lint, reachability and coverage checks
pass; and the Python binding loads `scale-rates`, `rates-minimal`, `expand-day`
and `scale-project`.

**Left open.** RatePerStart, RatePerVehicle, RatePerProfile and RatePerHour, the
other processes' RatePerDistance (brake and tire wear, crankcase running, the
evaporative on-road rows), chained pollutants at Rates scale, off-network idle,
PROJECT-domain rates and time aggregation are counted by `run_ratesUnported`, not
ported; no snapshot exercises any of them. The model's `out_*` relation is computed
at Rates scale but means nothing there (MOVES's pre-truncation MOVESOutput is
`meanBaseRate x` a link activity this model does not build). Distance units other
than miles are not read.

#### 7.3.48 The rest of Rates scale: five captured runs, one per table family, measured before porting

2026-11-01. §7.3.47 left every Rates table but running exhaust's RatePerDistance
counted and unported, because no snapshot exercised them. Six RunSpecs were written
for that (moves.rs `characterization/fixtures/rates-*.xml`, moves.rs `6c11d458`),
each the Rates-scale twin of inventory runs this model already reproduces, so that
what a run discriminates is the Rates arithmetic and nothing else. Five ran:

| run | twin of | tables MOVES writes (rows) |
|---|---|---|
| `rates-running` | `process-crankcase-running` + `chain-tog-speciation`, road types 1 and 4 | RatePerDistance 79,625 |
| `rates-wear` | `process-brakewear` + `process-tirewear` | RatePerDistance 10,000 |
| `rates-start` | `process-crankcase-start` | RatePerStart 684, RatePerVehicle 684, StartsPerVehicle 125 |
| `rates-hotelling` | `process-crankcase-extidle` + `process-extended-idle` + `process-apu` | RatePerHour 491, RatePerVehicle 491 |
| `rates-evap` | the four evaporative and refueling runs, road types 1 and 4 | RatePerDistance 31,165, RatePerVehicle 296, RatePerProfile 64, RatePerStart 104, StartsPerVehicle 125 |

**Two of §7.3.47's open items are not MOVES configurations.** *Time aggregation*:
`TimeSpans.java` forces `aggregateBy = HOUR` at Rates scale and refuses anything
else, so a Rates run that aggregates is not a RunSpec MOVES runs; it stays counted.
*PROJECT-domain rates*: MOVES failed `rates-project`'s first capture --
`RatePostProcessorRatesFirst.sql`'s PROJECT branch hardcodes `MOVESExecution.link`,
and the capture's `executionDatabaseName = *` names the execution database per
host, so the post-processor stopped and left every rate table empty. It is
recaptured with the name literal (moves.rs `5cc407df`: `run-moves.sh` takes
`EXECUTION_DB_NAME`, `*` for every other fixture) and ported as part D below.

**What MOVES does, from its source.** `RatePostProcessorRatesFirst.sql` assigns a
row to a table by its process and road type alone:

| table | rows | value |
|---|---|---|
| RatePerDistance | processes 1, 9, 10, 15 on any road type; 11, 12, 13, 18, 19 off road type 1 | `BaseRateOutput.emissionRate`; for 11-13, `MOVESOutput / distance` |
| RatePerStart | 2, 16 (not PROJECT) | `emissionRate` |
| RatePerHour | 17, 90, 91, 93 | `emissionRate` |
| RatePerVehicle | 2, 16, 17, 90, 91, 93; 11, 13, 18, 19 on road type 1 | `MOVESOutput / population` |
| RatePerProfile | 12 on road type 1 | `MOVESOutput / population`, by temperature profile |
| StartsPerVehicle | every cohort with population, when starts are computed | `starts / population` |

`baseratecalculator.go`'s `aggregateAndApplyActivity` scales `meanBaseRate` by the
activity and leaves `emissionRate` alone, so at Rates scale `MOVESOutput` is the
inventory's quantity and `emissionRate` is a rate per unit of activity.

**Measured in pandas against the snapshots and their inventory twins.**

1. *Every directly rated on-network row already reproduces.* Running THC, CO, NOx
   and energy on road types 2-5 (the run's execution `runspecroadtype` holds all
   five although the XML names 1 and 4 -- conventions §102) and brake and tire
   PM2.5, within 1.2e-05, with no change.
2. *A chained pollutant is the inventory's chain applied to the per-bin rate.* Brake
   and tire PM10 are zero in the model today; MOVES's PM10/PM2.5 is constant across
   the 16 bins within each cohort (8.0 for brake wear's older model years, 6.67 for
   tire wear) -- `PM10EmissionRatio`, the same per-rate-row ratio the inventory
   chain reads. Crankcase running and the hydrocarbon species are the same case.
3. *Off-network idle is a rate per idle HOUR of a vehicle of that fuel*, in
   RatePerDistance at `avgSpeedBinID` 0 and link `(zoneID*10 + 1)*100`, one row per
   cohort rather than sixteen. The worker's Rates-mode `MOVESOutput` for it equals
   `expand-roadtypes`' inventory at every cohort (the factor is 1.0551e6, kJ per
   MMBtu), and `inventory / ratePerDistance` divided by the road-type-1 SHO of the
   cohort's age is the fuel's share of the source type (0.179-0.200 for gasoline):
   §104's normalization, without the bin speed.
4. *Starts.* `rates-start` against `process-crankcase-start`: RatePerVehicle =
   inventory / population, and RatePerStart = inventory / (starts x population per
   vehicle), both within 1.1e-05 for every fuel; StartsPerVehicle is the AGE's
   starts per vehicle, identical across fuels, with a row only where the cohort has
   population (no diesel model year 2020).
5. *Hotelling.* `rates-hotelling` against its three twins: RatePerVehicle =
   inventory / population and RatePerHour = inventory / hotelling hours for 17, 90
   and 91, within 1e-05 -- and shore power (93) has a RatePerHour of 0.0115 where
   its hours and its inventory are zero. RatePerHour is the rate, not a quotient.
6. *The evaporative on-road rows are an hourly rate over the bin speed.*
   `ratePerDistance x avgBinSpeed` for 11, 12 and 13 is the same at every bin and
   road type to 1.6e-05. Refueling (18, 19) varies by bin as running energy does:
   it is chained from it, and MOVES keeps the energy prerequisites (91/1, 91/2) in
   the Rates tables where the inventory output processor strips them (§7.3.30).
7. *Off-network evaporative is new physics.* Permeation, leaks, vapor venting and
   refueling on road type 1 need the soak operating modes, the cold-soak tank
   temperatures (TTG-6/7) and refueling's off-network energy parent, none of which
   the model computes (§7.3.33). RatePerProfile has one profile per zone and month,
   `zoneID*10000 + monthID*100`.

**The design.** Every Rates table but StartsPerVehicle is a SUBSET of the output
relation -- of `rateoutput_rows` for RatePerDistance -- chosen by process and road
type, so each table is a relation over the rows the model already has plus a
membership flag `<prefix>_inTable`, and the harness drops the rows whose flag is 0.
A declared and checked row count per table (as `n_outputRate` is) would cost five
bindings in every RunSpec and a rank per table for no information the predicate
does not already carry. The value columns:

* *One per-activity rate, and its chain.* `rt_sourceBinShare` is §104's normalizer
  without the operating mode -- the used fractions of a rate row's siblings in the
  same block, cohort and regulatory class. `rtDay_ratePerActivity` is the
  inventory's `rtDay_adjustedMeanBaseRate` over the unit divisor and that share:
  per start, per hotelling hour, per idle hour. It goes through the inventory's
  three chain rungs unchanged (the chain is linear and its ratio per rate row), and
  `rto_ratePerActivity` sums it, direct plus chained, onto the output row --
  with shore power's own rate on its own output row. RatePerStart and RatePerHour
  are that value; RatePerDistance reads it for off-network idle.
* *The per-bin rate gets its own chain.* `rtBin_rateDirect` is the existing
  normalized per-bin rate over the unit divisor, and three rungs over `[b,j,g,n]`
  give the chained species, crankcase, PM10 and refueling per bin.
  `rpd_ratePerDistance` divides it by the bin speed, or reads `rto_ratePerActivity`
  at road type 1 (one row: the first bin is a member, at bin id 0).
* *Per vehicle.* `rto_population` is the age's population times the cohort's
  share (the same `rt_usedFraction` sum); RatePerVehicle is `out_emissionQuant`
  over it. StartsPerVehicle is a relation of its own over cohorts, county, month
  and day, a member where the run computes starts and the cohort has population.
* *Off-network idle covers crankcase running too.* MOVES applies the crankcase
  ratio to every running row, so `ppr_isOffNetworkIdle` takes process 15 beside 1;
  no inventory RunSpec here selects crankcase running with road type 1.
* *Shared columns are read, not copied.* The output-row tables emit their key
  columns from `out_*` (the harness names them from each table's column contract),
  so only what is new is computed: the value, the membership, RatePerHour's road-
  type-1 link, and the hour's meteorology once, as `rto_temperature` and
  `rto_relHumidity`, which `rpd_*` now reads too.

**The harness.** A runspec may carry one `oracle` source per table. Each table has
a prefix (`rpd_`, `rps_`, `rph_`, `rpv_`, `rpp_`, `spv_`) and a column contract in
`tolerance.toml`; `run-tests.sh` emits the prefix's variables and, for an output-
row table, the `out_*` key columns its contract names, keeps the member rows, and
compares each table. A Rates RunSpec names every table MOVES writes, including the
empty ones, so a row the model emits that MOVES does not is a failure.

**Sequenced in three parts, each closing runs.**

* **A** -- the chains, off-network idle, starts and hotelling: `rates-wear`,
  `rates-running`, `rates-start`, `rates-hotelling`, with `scale-rates` and
  `rates-minimal` naming their empty tables. Priced: 1 equation changed in
  `ppr_isOffNetworkIdle`, 5 in `rpd_*`; about 40 added (the share, the
  per-activity rate and 5 chain equations, the per-bin direct rate and 5 more, the
  output-row rate, population, meteorology, the RatePerStart, RatePerHour and
  RatePerVehicle columns and memberships, and about 12 for StartsPerVehicle) and one
  index set. Two chain copies are computed at inventory scale too, over a single
  speed bin; their cost is measured on the 35 inventory runs, which must stay
  byte-identical.
* **B** -- the on-road evaporative rows and the kept energy prerequisites:
  `rates-evap`'s RatePerDistance (the hourly evaporative rate over the bin speed,
  refueling through the per-bin chain) and RatePerStart.
* **C** -- off-network evaporative: the soak modes, TTG-6/7, refueling's off-network
  parent, RatePerVehicle's road-type-1 rows and RatePerProfile. The largest part,
  and measured separately before it is priced.

**What was done: parts A and B** (2026-11-01, conventions §107).

| run | table | rows | worst cell |
|---|---|---:|---:|
| `rates-wear` | RatePerDistance | 10,000 | 1.163e-05 |
| `rates-running` | RatePerDistance | 79,625 | 1.163e-05 |
| `rates-start` | RatePerStart / RatePerVehicle / StartsPerVehicle | 684 / 684 / 125 | 4.5e-06 / 1.09e-05 / 1.0e-05 |
| `rates-hotelling` | RatePerHour / RatePerVehicle | 491 / 491 | 4.6e-06 / 8.3e-06 |
| `scale-rates`, `rates-minimal` | RatePerDistance | 2,000 each | 1.163e-05 |

Every table key-exact, every empty table empty in the model too. `rates-evap` is
in `runspecs/pending/`: its RatePerDistance (31,165 at 1.163e-05), RatePerStart
(104) and StartsPerVehicle (125) reproduce, and its 296 RatePerVehicle rows are
part C. 1,100 -> 1,156 equations, 1,596 -> 1,652 variables, one index set, four
`process` enum names; 5 equations changed in `rpd_*`, 3 emission gates and
`run_onRoadPollutantProcessCount`. The design held, and the measurement corrected
it four times, each now a rule of conventions §107:

* *One chain, not two.* The per-bin rate and the per-activity rate are one
  relation, `rtRate_*` over `[rate row, day, speed bin, county, month]`, so the
  inventory's three rungs are copied once.
* *The cohort's share, not the class's.* §104's per-regulatory-class normalizer,
  reused for the per-activity rate, overstated `rates-hotelling`'s RatePerHour by
  15-69 % (three bins in two classes); a cohort's starts, idle and hotelling hours
  are the age's times its WHOLE share, `rt_cohortShare`.
* *The mode's hour, not the hotelling hour.* RatePerHour is then 1/0.8, 1/0.73 and
  1/0.07 of the quotient: MOVES scales meanBaseRate by `hourFractionAdjust` and not
  emissionRate, so the rate is per hour of extended idling, of the APU, of shore
  power -- computed directly (six equations, the hotelling branch without the
  cohort's mode fraction), because shore power's fraction is 0 and its rate is
  0.0115.
* *The zone's population.* RatePerVehicle and StartsPerVehicle were 877x low:
  `act_population` is the source type's, and `ActivityCalculator.sql` allocates it
  by `sutFraction` -- the zone's SHO allocation weighted by VMT over every road type
  it has -- not by `startAllocFactor` (0.0011408 against 0.0011225).
* *Prerequisites are half-kept.* Part B's `rspp_isStripped` keeps refueling's
  energy prerequisites at Rates scale, because RatePerDistance and RatePerStart
  read BaseRateOutput; RatePerVehicle reads MOVESOutput, which has been stripped,
  so `rpv_inTable` drops them (`rto_isPrerequisite`) -- 104 start-energy rows that
  MOVES does not write.

The evaporative hourly rate needed no new physics: `ratePerDistance x avgBinSpeed`
is the inventory twins' quantity over the cohort's SHO per real day (0.2 = 1/5,
exactly), which is `rtDay_adjustedMeanBaseRate` over the cohort's share.

The harness: `tools/emit-oracle-table.py` emits one table (its prefix relation,
the `rto_*`/`out_*` key columns its contract names, the member rows), a runspec
may carry one `oracle` source per table, `compare-output.py` passes an empty Rates
table only against nothing emitted (an empty MOVESOutput is still refused), and
the shape check is the output relation's, with RatePerDistance's links checked
against their road type and bin.

**Unchanged runs, byte for byte.** All 37 RunSpecs in `runspecs/` at `47c8bde`
were emitted from a frozen clone and again with part A: the 35 inventory `out_*`
relations and all 37 recomputed shapes, **72 of 72 CSVs identical** (`cmp`);
`process-refueling`, the one run with prerequisites, identical again with part B.
CPU time moved by a median +0.9 % (worst +2.3 %, `scale-rates`) and peak RSS by
-0.4 % (worst +1.0 %); the corpus high-water mark is `expand-fullyear` at 7.32 GB.

**Part D: PROJECT domain** (2026-11-01). `rates-project`, the Rates twin of
`scale-project`, writes 125 RatePerDistance rows of running energy on the
project's link 1 at `avgSpeedBinID` 0. Measured before porting: `scale-project`'s
inventory over the cohort's SHO per real day, over the link's 30 mph, is the rate
for all 125 cohorts within 2e-06 -- the per-activity rate again, with the LINK's
speed where the bin's would be. So the port is four edits: `rt_isBinRated` is off in
PROJECT domain (BaseRateGenerator turns `useAvgSpeedBin` off there),
`rt_isLinkSpeedRated` divides running, brake and tire wear by `run_linkAvgSpeed`
(the chained 15, 18 and 19 follow their parents), and RatePerDistance keeps one row
per output row, at bin 0, on `run_linkID`. **125 of 125 at 5.2e-06 on the first
run**, the four empty tables empty, `scale-project` byte-identical. PROJECT domain
leaves `run_ratesUnported`; what a project selects beyond running exhaust is
`run_domainUnported`'s to refuse, as it was.

**Part C measured** (2026-11-01, `rates-evap` against MOVES's own intermediates in
its snapshot and the worker's road-type-1 `MOVESWorkerOutput`). It splits in two.

*C1 -- RatePerVehicle's road-type-1 rows (permeation, leaks, both refueling
losses; 296 rows) need no new physics, only the off-network arm of four things
the model already has.*

1. *SourceHours is SHP.* `TotalActivityGenerator` step 190 writes the off-network
   link's `SourceHours` as `SHP = SHPByAgeHour x SHPAllocFactor`, and step 180's
   `SHPByAgeHour` is the age's national population x `noOfRealDays` minus its
   national SHO summed over the road types with VMT. The snapshot's road-type-1
   `sourceHours` sums to 570,208.44 against `SHP`'s 570,208.455 (decimal storage).
   `SHPAllocFactor` is already a mounted `zone` column.
2. *The operating fraction is per road type.* E1 at the off-network link is the
   off-network-idle SHO over SHP: 0.007197, against exactly 1 on every on-network
   link. `evap_fractionOfOperating` and the soak weights take the road type as an
   axis, and `evap_W` is read at the rate row's road type.
3. *soakActivityFraction is computed, TTG-6.* `hotSoakOpModeCount / (eMinutes -
   oMinutes)` for mode 150 and the remainder for 151, with `eMinutes = 60 x` the
   source type's sample vehicles on the day and `oMinutes` the operating minutes
   in the hour: 1,058 / (49,260 - 1,446) = 0.0221274, the snapshot's value.
4. *Then each process is the inventory calculator at weights it already reads.*
   Leaks: `Sum_m W_m x weightedMeanBaseRate_m x SHP / noOfRealDays` with
   `W = (1-f) x saf` on 150 and 151 and `f` on 300 -- E85 to 5.2e-06 and gasoline
   to 2e-06 at every model year once E85 vehicles' gasoline use
   (`fuelUsageFraction`) is added to the gasoline row, as on-network. Permeation:
   the on-network rate x `Sum_m W_m A exp(B T_m) / A exp(B T_300)` with TTG-5's
   150, 151 and 300 tank temperatures (`ttg_averageTankTemperature` already has
   all three): 0.849367 for tank group 5 and 0.922963 for group 3, every cohort.
   Refueling: `meanBaseRate / noOfRealDays` of the BaseRateOutput rows chained from
   the road-type-1 energy -- off-network idle (91/1) and starts (91/2) -- every
   cohort to 1e-06, so a chained process occurs on every road type a parent
   occurs on, and `run_mixedRoadChains` stops being a limit.

*C2 -- vapor venting's cold soak (RatePerProfile, 64 rows).* Mode 151's venting
rate is `MultidayTankVaporVentingCalculator.sql`'s TVV-1..7 (2,066 lines: the
sample-vehicle soaking days, cumulative tank vapor generated by ethanol level)
-- `emissionRateByAge` carries 150 and 300 alone. It is the cold-soak insert
§7.3.33 left out, and it feeds RatePerProfile only.

*C2 measured* (2026-11-01, /scratch.local/ctessum/rates2/c2/repro.py): all 64
RatePerProfile rows reproduce in pandas at 7.4e-06, and the cold-soak insert
contributes EXACTLY ZERO to every one. The worker extracts `HourDay` as the
selected hours of the selected days, and TVV-3 pairs a cold-soak hour with an
earlier one of the same day (`TankTemperatureGenerator` resets the initial hour
at hour 1 of each day); with one hour selected, and that hour not 1, there is no
pair, TVV-3 is empty, and so is every step to TVV-7. (Independently, hour 7's
cold-soak tank temperature, 59.57 °F, is below hour 6's, so TVV-6 would zero it
even with all 24 hours.) Every capture in the corpus selects one hour, so no
capture can validate the TVG recurrence; RatePerProfile is
`MOVESOutput / population`, the same quotient as RatePerVehicle
(RatePostProcessor.sql), keyed by `zoneID*10000 + monthID*100`. On the way the
pandas reproduction rebuilt `sampleVehicleSoaking*` from the trips (all eight
tables exact) and the NewTVVYear coefficients, priced for the day a multi-hour
capture exists.

**What was done: part C1** (2026-11-01). Fourteen equations and two mounted
parameters added, sixteen equations changed, two retired; 1,157 -> 1,169
equations. `act_shp` and `act_nationalSho` give the
off-network link's SourceHours from the zone's `SHPAllocFactor` (now mounted
beside `startAllocFactor`, row-merged the same way); E1 to E3 and `evap_W` take
the road type as an axis, read at the rate row's; TTG-6 is
`ttg_soakActivityFraction`, from the hot-soak minutes' union across tank groups
(`max_product` per trip), the source type's operating minutes and its sample
vehicles, with a mounted row taking precedence as `SoakActivityFractionKeys`
does; an evaporative rate row's activity is SourceHours; permeation and leaks
occur on road type 1, and a chained process with an off-network parent occurs
there beside its on-network one. `run_evapRoadTypeExcess` and
`run_mixedRoadChains` are retired -- both are ported -- and vapor venting on road
type 1 is what `run_offNetworkLinkCount` now counts, on the selection, at both
scales. **`rates-evap`'s RatePerVehicle 296 of 296 at 9.068e-06 on the first
run**, its other four tables unchanged, `run_selectionUnported` 0. It stays in
`runspecs/pending/` on RatePerProfile alone (C2). Every other RunSpec is
byte-identical: 82 CSVs against the part-A/B/D emits and 24 against the frozen
baseline, all equal; peak RSS 7.34 GB against 7.32.

One thing the compiler taught: `evap_soakWeight` stopped compiling once it no
longer read a mounted relation -- `native` declines a join-gated `faq` in a
build-time constant -- so the op-mode association is its own flag,
`evap_hasMode[p, o]`.

**What was done: part C2** (2026-11-01). Three equations added, two changed, one
renamed; 1,169 -> 1,172. Vapor venting occurs on road type 1 beside the other
evaporative processes; its mode-151 rate is the absent rate row's 0, which is
MOVES's own answer whenever `run_coldSoakPairable` is 0, and
`run_offNetworkLinkCount` now counts selected venting on road type 1 only in a
run where it is 1 -- more than one hour, or hour 1 -- so a run whose cold soak
MOVES would compute still fails loudly. `rpp_inTable` is process 12 on road type
1; `rpp_temperatureProfileID` the profile key; and `rpv_ratePerVehicle` became
`rto_ratePerVehicle`, read by both tables. **`rates-evap` reproduces: RatePerProfile
64 of 64 at 8.999e-06 on the first run**, its other five tables unchanged, and
it leaves `runspecs/pending/`. Every Rates run now names RatePerProfile as an
oracle, empty in the other seven. Every other RunSpec is byte-identical.

The suite on the part-C1 commit found one thing the per-table comparisons had
not: `rates-project`'s shape check asserted every RatePerDistance row sits on a
bin link, and a PROJECT run's sits on the project link itself, at bin 0.
tools/check-runspec-shape.py now reads the project link from `out_linkID` --
NULL at county detail -- and asserts that instead.

**What was done: part E** (2026-11-02): SulfatePMCalculator's species and the
non-HAP TOG residual per speed bin, the last rows `run_ratesUnported` counted
besides time aggregation. Three more captures (`moves.rs` `46cff1e6`), Rates twins
on road types 1 and 4: `rates-pm` of `process-pm-exhaust` (RatePerDistance 47,320
rows), `rates-nonhaptog` of `chain-nonhaptog` (35,100, and no 88 row -- it selects
88 without its mechanism 3000, so it tests the switch and not the subtraction) and
`rates-mechanism` of `chain-so2-co2e-mechanism` (179,855, 88 with its mechanism).
Measured from the SQL first: both calculators are linear in
`MOVESWorkerOutput.emissionRate` exactly as in `emissionQuant` --
SulfatePMCalculator.sql carries both columns through every step, and
TOGSpeciationCalculator.sql signs and sums both and clamps each with `greatest(...,
0)` per GROUP BY cell, which carries `linkID`, the bin. So the per-bin rate takes
the inventory's two constructions over `rtRate_*`: the old `rtRate_direct` is
`rtRate_rated`, and `rtRate_direct` is the share matrix on the SPM blocks
(`rtRate_spmParent`, `rtRate_spmSpecies`, `rtRate_spmRate`), before the chain so
PM10 chains off PM2.5; `rtRate_nonHapTogSum` and its clamp `rtRate_nonHapTog` read
the finished rate, after it, and join `rtRate_total`. Six equations added; 1,172
-> 1,178. `run_ratesUnported` is time aggregation alone. **All three reproduce on
the first run, every table**: 47,320 at 6.248e-06, 35,100 at 5.296e-06 and 179,855
at 1.163e-05, the other five tables empty as in MOVES, and the shape check holds
for each (3,640, 2,700 and 13,835 rows). Every other RunSpec is byte-identical
(119 CSVs against the C2 emits; `rates-evap`'s six tables unchanged at their
worst cells). `rates-mechanism` is the costliest run in the suite: 49 minutes for
its six tables at 2.4 GB peak, measured beside a running suite, because each
table is a separate `simulate`.

**What was done: part F, hotelling for other source types** (2026-11-02).
`rates-hotelling-sourcetypes` (moves.rs `5389ead6`) is `rates-hotelling` with the
single-unit and combination short-haul trucks (52, 61) selected beside the
long-haul truck (62), and MOVES writes the same 491 rows, every one 62's.
BaseRateGenerator's steps 200 and 210 write RatesOpModeDistribution for 62 alone,
so another source type's hotelling bin has no rate row at all. The model had it
as a row with a ZERO weight (`cohMode_hotellingWeight`), which emits 779 rows MOVES
does not: `rateSurvivorCount` 1,270 against 491. One equation,
`rt_hasHotellingModes`, makes it an absence, read by `rt_survivesRated`; 1,178 ->
1,179. **RatePerHour 491 of 491 at 4.566e-06, RatePerVehicle 491 of 491 at
8.345e-06, the other four tables empty as in MOVES, and the shape check holds.**
The document's first try failed RatePerVehicle with every value 0: it had copied
`rates-hotelling`'s `n_physicsRow` = 20, three source types need 58, and the
declared size cut 62's physics rows off -- a binding, caught by the shape check's
38 dropped rows.

**Left open.** Time aggregation, which is not left open but INVALID -- MOVES
refuses it at Rates scale, and `run_ratesUnported` counts it as a RunSpec MOVES
would not run. Vapor venting's cold soak in a run of more than one hour is ported
in §7.3.49.

#### 7.3.49 The hour is part of the output cell, and the multiday cold-soak insert is ported

**Measured first** (2026-11-02). Every RunSpec so far selected ONE hour, and the
model read the hour as a run scalar (`run_hourID`, and the meteorology and
TankTemperatureGenerator's "run hour" with it). Two captures (moves.rs `5389ead6`)
select every hour of both day types: `rates-venting`, Rates-scale vapor venting
THC on road types 1 and 4 (3,072 RatePerProfile rows, every other table empty),
and its inventory twin `process-evap-fvv-day` (6,144 MOVESOutput rows, THC only).
A pandas reproduction of `rates-venting` from the capture (TVV-2 to TVV-9 as
moves.rs ports them, `HourDay` restricted to the SELECTED hours) matched all 3,072
rows at 1.97e-05 once the stored soak fractions were renormalized; with every hour
of the day in `HourDay` instead it does not. The cold soak is up to 46 % of an
afternoon hour and exactly 0 at night, when the tank cools.

**The hour joins the output day** (conventions §108). Priced as an axis it is 175
of 1,178 equations; 72 of those already carry the output day `k`, so `k` became
the output (day type, hour) CELL: `db_runspecday` mounts `runspechourday`, which
on all 59 earlier RunSpecs is their `runspecday` row for row, `rsd_dayID` and
`rsd_hourID` are looked up through `hourday`, about 52 run-level variables gained
the cell, and a rate-side day or aggregation hour belongs to a cell by its day and
hour or, for a synthesized aggregate cell, to all of them (`tcell_*`).
`run_dayCount` counts the rate-side day types rather than cells.

**The cold-soak insert** (operating mode 151), every input from the default
database: TTG-7's `coldSoakInitialHourFraction` as algebra over the national
trips (`tvh_*`, `csi_*`); FillSampleVehicleSoaking's five soaking days
(`svs_*`) from `sampleVehicleSoakingDayBasisUsed`; NewTVVYear's coefficients per
rate row from `CumTVVCoeffs`, whose equation STRINGS are decoded into the two
forms of lib/evaporative.esm at the binding by a `codes` map from both the SQL
text and the execution database's labels; and TVV-2 to TVV-8 over pairs of the
run's cells (`tvv_*`), with the canister load the one recurrence, over soaking
days. Four templates name the SQL's literals (`soaking_days`,
`barometric_altitude_fraction`, `ethanol_level_weight`, `post_peak_decay`) and
one TTG-7's `keyOnTime mod 60` (`minute_of_hour`). Checked against the capture
stage by stage: TTG-7 534 of 534 pairs at 4.9e-07 after the TIE rule (a
zero-minute last segment whose soak starts on the same minute is a hot-soak
first record: 124 vehicle-hours), the soaking fractions 240 of 240 at 3.0e-08,
the peak hour 17.

**Three defects a one-hour corpus hid**, found by comparing one intermediate per
cell at the worst hour: marker trips counted as driving in hour 1
(`ttg_operatingMinutes` now over walked trips); off-network idle SHO computed in a
run with no process that needs it (`run_needsOffNetworkSho`: running exhaust,
brake or tire wear); and the parked hours subtracting the SHO of the SELECTED road
types where MOVES subtracts every road type's (the VMT-to-speed chain now runs over
`roadtype_rows`, its five readers selecting by ID). 1,179 -> 1,272 equations.

**Both reproduce**: `rates-venting` RatePerProfile 3,072 of 3,072, the other five
tables empty as in MOVES, and `process-evap-fvv-day` 6,144 of 6,144, key sets
exact. One cell each is over 2e-5 -- day 5, hour 4, gasoline model year 1982, at
2.24e-05 and 2.06e-05 -- and it is MOVES's own FLOAT storage of
`soakActivityFraction`, whose two stored shares sum to 0.99999979 and leave
operating mode 300 a 2.1e-7 weight; tolerance.toml holds that one cell to 5e-5
(EarthSciAST#536, declined 2026-11-09: the exception is permanent). The gate narrows to venting on road type 1 in a run that
AGGREGATES hours (`run_aggregatesHours`), which no capture measures.

#### 7.3.50 `expand-ev-heat`: the heat-index suppression is per source type

2026-11-02. A capture made to test one known defect. `run_evTemperatureIsSuppressed`
zeroes the EV running-energy temperature adjustment for light duty (source type
below 40) above a 67 degF heat index (`adjust.rs`), and it read `rst_sourceTypeID`
at the one-row `run_rows` symbol -- the run's FIRST source type -- rather than at
the source type it is computed for (§7.3.44, conventions §98 item 2). Every earlier
EV run selects source type 21 alone, where the two readings agree.

`expand-ev-heat` selects battery-electric passenger cars (21) and transit buses (42),
Washtenaw, 2020, August weekday, hour 16 -- heat index 83.16 degF -- on road types
2 to 5, running Total Energy: 996 rows, MOVES's own expansion adding the gasoline,
diesel, E85 and CNG cohorts. The fix is one index (`s` for `n`) and one range
dropped. **996 of 996 at 1.008e-05, key set exact**; the unfixed model fails 69
cells, every electric transit-bus cell, all at the same 4.737e-02 -- the bus's
adjustment, suppressed because the car comes first. `expand-multifuel`, the one
earlier EV run, is byte-identical with the fix. The first binding copied
`expand-multifuel`'s width and declared `n_sourceBin` 4; the shape check's 28
dropped source bins named it, and 12 holds them.

The RunSpec also selects PM10 brake and tire wear, to put wear on several
on-network road types for the first time. MOVES writes no rows for either, so
that surface stays unmeasured (§7.3.46).

**The capture binary was stale.** `run-fixture.sh` takes
`target/release/moves-fixture-capture` as it finds it, and that build dated from
2026-05-30, before `moves-snapshot/v2`: every capture from 2026-10-20 on -- 25
snapshots, this week's included -- is v1, twelve fixed decimals, although the corpus
was migrated to v2 on 2026-09-09 and `tolerance.toml` judges v2. A v1 capture of this
run stored its 1986 transit-bus cells as `0.000000000014` and failed 13 of them at up
to 2 %; rebuilt, the v2 recapture passes them all. The 24 other v1 snapshots pass
because their cells are large, and are not yet recaptured.

#### 7.3.51 The cold-soak chain is per group slot, and the soak's hour is gathered

2026-11-02 to 2026-11-08. No new RunSpec: a cost fix to the chain §7.3.49 added,
and three shape and capture defects found on the way.

**The cold-soak chain over every tank-temperature group.** At 763ffca the eight
`tvh_*` vehicle-hour variables were computed over all 16 tank-temperature groups,
when no source type uses more than two. `expand-counties-large`'s shape step went
from 5.1 GB and 3 min (8bd56e8) to 16.7 GB and 2 h 22 min. Those variables are now
over `tankgroupslot_rows`: a (vehicle-day, group slot) row, `w`, with
`n_tankGroupSlot` = 2 slots, where `tvh_groupOrdinal` gives each group its place
among its source type's groups. `run_tankGroupsDropped` counts the groups past
the last slot. The shape check asserts it is 0, as it does `run_sourceBinsDropped`,
and both observed lists in `run-tests.sh` carry it.

**Two joins that walked the full product.** The slot rewrite made the vehicle-day a
contracted dim, and that exposed an EarthSciAST limit. Only one gate between two
contracted dims restricted a walk; the others were per-leaf filters (EarthSciAST CONFORMANCE_SPEC
§5.24.2 at the time). `tvh_soakTies` (slot → vehicle-day → trip) ran about 10^10
tuples, and the run looked hung. `run_startModeAgeVariation`, a star join, counted
235M leaves for one scalar. Both are fixed in the document as well as upstream:

* `tgs_firstTripKeyOn[w,h]` gathers the first trip's key-on onto the slot, so
  `tvh_soakTies` joins its trips to `w` directly;
* `sod_ageVariation[k,m,s]` counts with the key bound, and the run's number is
  its sum.

EarthSciAST PR #659 (9c0c941, esm 0.9.0) then made every such gate restrict the
walk, in both directions and to a fixpoint. `rates-venting` dropped from over 60
minutes to about 6.

**The soak's hour is a gather, not a match.** `tvh_hotMinutes`, `tvh_soakCarries`
and `tvh_soakTies` walked all 24 soak slices `s` of each trip and kept the one
where `tsk_hourID[i,s]` matched the hour. A join key must be a 1-D column, so that
test is a per-leaf filter, not a join. The slice is computable instead:
`trp_hourSlice[i,h]` is `hour_of_day_wrap(h - trp_lastHourID[i] + 1)`.
`ttg_hourHotSoakMinutes[g,n,u,i,h]` re-keys `ttg_sliceHotSoakMinutes` by the
hour, and the three joins drop `s`.

On `expand-fullyear`, each of the three soak folds went from about 12 min to
about 42 s. The run went from 43 min to 11 min, and its peak from 21.2 GB to
22.4 GB. The output is byte-identical to the model before the change, and so are
`rates-venting`'s outputs. With the older non-slot form, main's 9c0c941 took
5 h 56 min on this run.

EarthSciAST PR #668 (c88d0dc) removed the per-chunk input copy that made tuple
folds cost (#chunks × input size). On the same model, `expand-month` went from
1 h 08 min to 16 min.

**Defects found on the way:**

* **The shape check lacked the hour.** Rows are pairs × counties × months × day
  types × *hours* since §7.3.49. A one-hour run hid this, and the first 24-hour
  runs (`process-evap-fvv-day`, `rates-venting`) failed at 6,144 rows against
  256.
* **The distance activity is per run.** `run_writesDistance` gates evaporative
  RatePerDistance. MOVES divides by the distance activity, and only
  DistanceCalculator writes it, for running exhaust alone. A venting-only run
  (`rates-venting`) therefore has no RatePerDistance rows.
* **The capture tool rewrote host tokens incompletely.** The 24 v1 snapshots of
  §7.3.50 were recaptured as `moves-snapshot/v2`. `build-snapshots.sh` now
  rebuilds the capture binary first. `tools/rehost-snapshot.py` renames a host
  token in the files, the `.meta.json` names and the manifest together, and
  `--check` re-derives every manifest. A rename of the files alone left
  snapshots that moves-snapshot refuses.

The whole suite with these changes ran green on esm 9c0c941 in 8 h 28 min,
621 ok, with a peak of 22.4 GB. The same suite on main had not finished after
25 h.

#### 7.3.52 One evaluation per run

2026-11-08. A harness change, no model change. `esm simulate` evaluates every
observed in the document; `--observed` only picks the columns written. The
RunSpec stage nevertheless called it once per oracle table, then twice more for
the output relation and the shape scalars. That was eight full evaluations for a
Rates run, two for an inventory run, and two for each nonroad RunSpec and probe.
The suite took 8 h 05 min, most of it in these repeats.

`tools/emit-oracle-table.py` now makes ONE call per run, with `--format grid`.
`--format csv` refuses fields of different shapes, and a run's tables do have
different shapes; the grid writes each field with its own dimensions. The tool
writes, from that one evaluation:

* every oracle table;
* the `out_*` relation;
* the shape scalars.

The relation and the scalars are written exactly as `--format csv` writes them.
Floats are rendered as Rust's `{}` does: the shortest round-trip digits,
positional, and on an exact tie between two shortest strings, rounded up where
Python's `repr` rounds to even. A Float32 model hits such ties often:
71.911651611328125 is written `…813`, and `repr` gives `…812`. All 5,483,003
numbers in the previous suite's esm-written CSVs re-render byte-identically,
and so do the files of four runs re-emitted through the new path. The probes'
`cmp` against `<run>.runspec.csv` therefore still compares like with like.

The suite went from 8 h 05 min to 2 h 48 min (peak 19.9 GB), and `rates-venting` from about
35 min to 5 min 15 s. Every comparison and shape check passed. The one failure was
the wall-clock `join.on` gate: 1052 ms driven against 3080 ms ungated, under a load spike
on a shared node. Re-timed five times on its own, it ran 128–373 ms against
2846–2925 ms.

#### 7.3.53 32 of 32: the two PROJECT-domain generators are counted

2026-11-08. No model change. `tools/calculator-coverage.py` had reported 30 of
32 live modules ported. The two it missed were both ported in step 7f
(§7.3.40), and `scale-project` and `rates-project` have reproduced through
them since. They went uncounted for two bookkeeping reasons:

* **`LinkOperatingModeDistributionGenerator`** had a spec and a registered
  oracle, `run-link-omd-oracle.sh`. But the tool's fixture leg accepted only a
  `fixtures/` document, and `scale-project` reproduces as a RunSpec. A Phase 7
  RunSpec reproduces its snapshot's oracle tables end to end, from the default
  database, in the 7c'/7d stage. The tool now accepts one.
* **`ProjectTAG`** had no spec at all. `docs/project-tag.md` is it: the SHO
  product (`ProjectTAG.java:354-385`), a hand-checked example, and an
  independent reproduction run by `run-project-tag-oracle.sh` and registered
  in ORACLES. Over both PROJECT-domain snapshots the reproduction gives 82 of
  82 `SHO` and 82 of 82 `distance` cells, each equal to the reference's
  binary32 six-digit rendering. It also asserts the scheduling:
  linkSourceTypeHour is populated on exactly the 2 PROJECT-domain runs and
  empty on the other 62.

  Only ProjectTAG's SHO path is ported. Its SHP, Starts, hotelling and
  SourceHours outputs are refused through `run_domainUnported`, and the spec
  says so at the top.

The result is **32 of 32: 19 calculators and 13 generators.**

#### 7.3.54 The trip chain is per slot too

2026-11-08. A cost fix; every output is byte-identical. §7.3.51 moved the
vehicle-hour chain onto two group slots. The trip chain one step upstream
(TTG-2..5: `ttg_tripState`, the key-on and key-off temperatures, the soak
slices, the run-hour readings, twelve variables) still ran for all sixteen
`TankTemperatureRise` groups x every trip. A trip's source type carries at
most `n_tankGroupSlot`, which is two.

**Two axes, not one.** The first attempt flattened (trip, slot) into one
trip-major axis, and it was slower: 444 s of CPU on `rates-venting` against
329 s. A recurrence is evaluated step by step along its axis and vectorised
across the others. Flattening doubled the steps, narrowed each step's vector,
and turned every trip-indexed read into a gather; the chain's step went from
133 s to 252 s. What went in instead:

* **`tankslot_rows`** (`q`, `n_tankGroupSlot`) carries the chain:
  `ttg_X[g,n,q,i]`. The recurrence stays over the trip, vectorised over the
  slot. `ttq_groupRow[q,i]` is the trip's q-th group in group-ID order, and
  `ttq_applies` marks an empty slot, which is never walked.
* **`tripgroupslot_rows`** (`zq`, trip-major) carries only the READERS: the
  four per-group totals (TTG-6), `ttg_tripHotSoakMinutes`, and the three
  vehicle-hour joins. Each reads the chain by a gather at
  (`tts_slot`, `tts_trip`), so its join keys stay one-dimensional. Being
  trip-major, a group's trips are summed in trip order, which keeps every sum
  bit-identical. An empty slot's `tts_groupID` is -1, which matches neither a
  group nor the vehicle-day side's empty slot, which is 0.
* **The vehicle-hour joins use one composite key**: (vehicle, day, group).
  As two clauses, the group clause paired every trip with every vehicle-day
  slot of its group, 1.0e8 candidate pairs on `process-evap-permeation` and
  10-20 s per fold.

`ttg_hotSoakMinutes` and `ttg_hotSoakTemperatureSum` also walked all 24 soak
slices to keep the one equal to `trp_runHourSlice[i,k]`. That slice is
computable, so it is gathered (§7.3.51's pattern).

**Measured** (CPU, so load-independent, on the same binary):

| run | CPU before | CPU after | peak before | peak after |
|---|---|---|---|---|
| `rates-venting` | 329 s | 177 s | 8.0 GB | 3.7 GB |
| `process-evap-permeation` | about 76 s | about 65 s | 2.9 GB | 1.9 GB |

The trip chain's own step on `rates-venting` went from 133 s to 16 s. Six
runs were re-emitted through the full harness and `cmp`'d against the
previous suite's files, every one byte-identical: `rates-minimal`,
`rates-venting`, `rates-evap`, `process-evap-fvv-day`,
`process-evap-permeation` and `expand-fullyear`.

#### 7.3.55 PROJECT domain beyond running exhaust: several links, start, brake and tire wear, hotelling

2026-11-09. Until today a PROJECT run reproduced only running exhaust on one
link. `run_domainUnported` refused any other emitted process, a second county
and a county whose join selected other than one link. **`project-links`
reproduces: 3412 of 3412 rows, key set exact, worst cell 1.324e-05, per-pollutant
sum 1.17e-06**, through running, start, brake and tire wear on three links.
**`project-hotelling` reproduces: 266 of 266, key set exact, worst cell
8.316e-06**, through extended idle and APU on an off-network link.
`project-offnetwork` is captured and pending on the evaporative processes. (It reproduces since §7.3.56.)

**Two new captures** (moves.rs `characterization/fixtures/` and
`county-inputs/`, routed in `run-all-fixtures.sh`; snapshots captured on host
token `1ccc0236`):

| run | selects | network |
|---|---|---|
| `project-links` | source types 21 and 32; road types 1, 4, 5; CO and Total Energy for running and start, PM10/PM2.5 brake and tire wear | link 1 (road type 4, 1 mi, 1,000 veh/h, 30 mph), link 2 (road type 5, 0.5 mi, 600 veh/h, 25 mph), off-network link 3; per-link source-type shares 0.8/0.2 and 0.6/0.4; an off-network fleet per source type; the user's start modes on link 3 |
| `project-offnetwork` | source types 21 and 62; road types 1, 4; Total Energy for running, extended idle and APU, THC for permeation, venting and leaks | link 1 (road type 4, 90% source type 21) and off-network link 2; 50 long-haul trucks idling 30% |
| `project-hotelling` | the same without the evaporative processes | the same database (`setup-project-offnetwork.sql`) |

The first `project-links` capture had no start-exhaust output at all. MOVES had
computed Starts, but in PROJECT domain StartOperatingModeDistributionGenerator
takes start modes ONLY from the user's `opModeDistribution`
(java:379-410). So the database now states them, as round fractions that differ
from the default `startsOpModeDistribution`. A port that read the default would
move the numbers.

**Measured before porting.** Each intermediate was reproduced in pandas from the
execution database's inputs:

* ProjectTAG's five outputs (`docs/project-tag.md` §6.5): SHO 328 rows,
  Starts 164, SHP 82, SourceHours 164, hotelling hours 123. Each key set is
  exact. Every FLOAT cell matches at six digits once the FLOAT input columns
  are narrowed to binary32: `project-links`' share of 0.6 decides one
  `distance` cell. `rates-project` confirms the Rates arm of Starts, which has
  no `startFraction`.
* The link operating-mode distribution (`docs/link-operating-mode-distribution.md`
  §6.5, generalised by a subagent): 3650 of 3650 cells across several links,
  real source types and physics rows. It also settled the brake question. The
  generator keeps brake wear's stopped seconds as mode 501, but under a TEMP
  source type that SourceTypePhysics' `physics_` update skips
  (`where opModeID <> 501`). So no real link ever reads them, and brake wear's
  distribution on a link is the UNFOLDED one, which sums to under 1. Tire wear
  gets one mode per link from its speed: 407 at 30 mph, 406 at 25 mph, 400
  off-network.
* The start modes (`docs/operating-mode-distribution.md` §8.3): step 400's
  PROJECT arm reproduces 32 rows. The road-type-1 partition also holds
  AverageSpeedOMDG's project tire rows, which the spec now leaves to their
  generator.

**First, the refusal guarded.** The pre-port model (dac96ab) evaluated on
`project-links` gives `run_domainUnported` = 6: the six emitted start, brake and
tire pollutant-processes. **It did not count the second and third links.**
`run_linkCount` selected only `run_roadTypeID`'s link, so a link on another road
type was never seen. The processes refused the run; the links would not have.
On `project-hotelling` the pre-port model gives 2: extended idle and APU.

**What the model now does**, all behind `run_isProjectDomain`:

1. **The link is per (county, road type).** `run_linkID`, `run_linkAvgSpeed`
   and `run_linkCount` carry the road type, and `out_linkID`, `rpd_linkID` and
   `rtRate_rated` read the row's road type. `run_linkCount` refuses a
   (county, road type) with other than one link. `act_projectSho` was already
   per road type.
2. **The link distribution is per road type.** The brackets, factor and
   interpolation (`lomd_*`) are keyed by road type. A bracket schedule is
   matched by FILTER: a two-index key such as `lomd_lowSpeed[s,rd]` cannot be
   a join's right side. The first attempt joined on it, and every schedule
   matched, giving a W summing to 11 and rates 15 times too large. The stopped
   seconds' quotient is its own variable (`lomd_stoppedFraction`). The fold
   adds it to mode 1 in the bracket fractions, with the same operands and order
   as before, so running exhaust is bit-identical.
3. **Brake wear** reads `lomd_WBrake`, the unfolded distribution. **Tire wear**
   reads `lomd_tireW`, one mode per road type's link (the new template
   `tirewear_link_op_mode`). `lib/operating_mode.esm` adds
   `link_bracket_interpolation`, which is shared by `lomd_W` and `lomd_WBrake`.
4. **Starts** are ProjectTAG's (`st_projectStarts`): the zone's
   `offNetworkLink` fleet x startFraction (inventory only) x ageFraction x days.
   **Start modes** are the user's: `sod_weight` reads the domain's
   `opModeDistribution`, matched by neither link nor polProcess, as the SQL is.
   The old expression is `sod_defaultWeight`.
5. **Two domain tables are mounted in every catalogue**: `offNetworkLink` and
   the input `opModeDistribution`. They are empty in the default database, the
   county databases, the execution-database fixture catalogue and the 7c spike.
6. **Hotelling hours** are ProjectTAG's (`hot_projectHours`): the off-network
   fleet of source type 62 x extendedIdleFraction x ageFraction x days, summed
   over the fuel split as the DEFAULT path's `hot_hours` is. The project
   database's `avft` is AVFTTool's sum of the sample vehicle population, so its
   fractions sum to `hot_stmyTotal`. And **a process-93 block needs a
   shore-power mode** (`rspp_hasShorePowerMode`). MOVES copies no default
   `hotellingActivityDistribution` into a PROJECT run, so APU's distribution is
   mode 201 alone, and MOVES writes no shore-power row. The first evaluation
   found the model computing a 50-row process-93 block, hidden because
   `n_outputRate` truncated it. The shape check caught it (316 recomputed
   against 266 emitted).
7. **The DEFAULT domain's refusal of brake and tire wear beside road type 1**
   (`run_onRoadPollutantProcessCount`) does not apply in PROJECT domain. There,
   road type 1 is the off-network link, and MOVES writes no brake or tire row
   on it.

**What `run_domainUnported` still refuses in PROJECT domain**:

* any emitted pollutant-process without a project generator here
  (`rspp_hasProjectGenerator`):
  * the evaporative processes (SHP, SourceHours, and the project branches of
    their operating-mode and tank-temperature generators);
  * the crankcase processes;
* a (county, road type) without exactly one link, and a second county;
* an out-of-bounds bracket;
* on-network links of different grades (`run_linkGradeMismatches`). The
  per-second chain reads one grade, because keying it by road type would
  multiply 63,602 seconds x physics rows by the road types of every run;
* user start modes that disagree across links or polProcesses
  (`sod_projectConflicts`), which INSERT IGNORE would settle by scan order;
* a user link distribution (`run_userLinkModeRows`);
* a second link at Rates scale (`run_ratesProjectLinks`). The per-road-type
  rate keys are written but not exercised there.

`runspecs/pending/project-offnetwork.esm` evaluates to `run_domainUnported` = 3.
That is its three evaporative pollutant-processes. §7.3.56 ports them.

**Unchanged runs.** Before the suite, `scale-project`, `rates-project` (all
eight tables), `process-brakewear`, `process-tirewear`,
`process-crankcase-start-single`, `process-crankcase-start` and
`expand-roadtypes`, and after the hotelling change `process-apu`,
`process-apu-single` and `rates-hotelling`, were re-emitted with `tools/emit-oracle-table.py` and
`cmp`'d against the main tree's `.fixtures-run/`: all byte-identical.
`project-links` evaluates in 151 s at 2.3 GB peak.

#### 7.3.56 PROJECT domain, the evaporative processes: SHP, SourceHours, and a soaking on-network link

2026-11-09. **`project-offnetwork` reproduces: 650 of 650 rows, key set exact,
worst cell 8.316e-06, per-pollutant sum 1.39e-06**, on the port's first run.
Permeation, fuel vapor venting and fuel leaks (THC, source type 21) on both
links: link 1 on road type 4 and the off-network link 2. It has moved out of
`runspecs/pending/`, which is empty again, and `run-tests.sh` routes it through
its `runspecs/` glob like `project-hotelling`.

**The brief was larger than the work.** §7.3.55 listed four things the
evaporative path waited on: SHP, SourceHours, and the PROJECT branches of
EvaporativeEmissionsOperatingModeDistributionGenerator and
TankTemperatureGenerator. The last two do not exist. Neither Java file has a
domain test (`grep -i 'project\|domain'` finds nothing in either). The
operating-mode generator runs once per link, and TTG once per zone, the same in
every domain. So the only PROJECT-specific inputs are ProjectTAG's two outputs.

**Measured before porting**, from the capture's execution database:

* SHP and SourceHours: `docs/project-tag.md` §6.5 already reproduced them on
  this run. 82 SHP and 164 SourceHours keys, exact, every cell at the FLOAT's
  six digits after binary32 narrowing. Re-run today, unchanged.
* The soak activity fractions: the model's `ttg_soakActivityFraction`, probed
  on the unchanged model, gives 0.0741377/0.925862 (source type 21) and
  0.215774/0.784226 (62) for modes 150/151. Those are the snapshot's four
  `soakActivityFraction` rows at six digits. TTG has nothing domain-specific to
  port.
* The fraction of operating, per link: `least(1, SUM(SHO)/SUM(sourceHours))`
  over the snapshot's own SHO and SourceHours. On link 1 it is 0.0333333 for
  both source types: ProjectTAG's on-network SourceHours is the link-volume
  product WITHOUT `least(linkLength/linkAvgSpeed, 1)`, and its SHO is that
  product times the share. So the fraction is the share, 1 mile / 30 mph. On
  link 2 it is 0, as the snapshot's last-written `FractionOfOperating` (link 2)
  says. The op-mode weights follow: 150/151 carry `saf x 29/30` on link 1 and
  `saf` on link 2. Mode 300 is the FLOAT residual: 0.0333337 on link 1, and 0 or 1.5e-08 on
link 2.

**The run is the first where soaking modes carry weight on an ON-network
link.** In DEFAULT domain A10 makes SourceHours equal SHO there, so the
fraction of operating is exactly 1 and the soak weight is a computed 0 on every
on-network road type of every earlier evaporative run. Nothing had read the
soak modes' rates or tank temperatures at road type 4 with a non-zero weight.
They were right: the worst evaporative cell on link 1 is 8.125e-06 (leaks),
against 5.801e-06 on link 2. The run's worst cell, 8.316e-06, is running
exhaust, the same cell `project-hotelling` records.

**What the model now does**, behind `run_isProjectDomain` like §7.3.55:

1. **`act_projectShp`**: the zone's off-network fleet x parkedVehicleFraction
   x ageFraction x noOfRealDays (ProjectTAG.java:387-405). `act_shp` takes it
   in PROJECT domain. It is the off-network link's SourceHours too
   (java:465-485), so `act_sourceHours` needed no change on road type 1.
   `onl_parkedVehicleFraction` is the new parameter; every catalogue already
   mounts `offNetworkLink` with that column (§7.3.55 item 5).
2. **`act_projectSourceHours`**: linkVolume x sourceTypeHourFraction x
   noOfRealDays x ageFraction (java:487-517), what `act_projectSho` was before
   its share. `act_projectSho` is now that times `link_travel_hours_share`, in
   the SQL's association, so SHO is bit-identical. `act_sourceHours` reads it
   on an on-network road type in PROJECT domain, and `act_sho` in DEFAULT.
3. **`off_network_fleet_hours`** (`lib/onroad_activity.esm`): `((population x
   fraction) x ageFraction) x days`. It is the one product behind
   `st_projectStarts` (startFraction, 1 at Rates scale), `hot_projectHours`
   (extendedIdleFraction) and `act_projectShp` (parkedVehicleFraction). The
   first two now call it; their outputs are byte-identical.
4. **`rspp_hasProjectGenerator`** admits the processes `rspp_usesEvapModes`
   names, at INVENTORY scale only. No PROJECT Rates capture selects an
   evaporative process. Probed: `project-offnetwork` with `n_ratesScale` bound
   to 1 gives `run_domainUnported` = 3.

Nothing else changed. The evaporative op-mode distribution (`evap_*`), TTG, the
three calculators and the per-road-type output were all already keyed by road
type, and a PROJECT link is a (county, road type) (§7.3.55 item 1).

**The refusal, before and after.** The pre-port model (2cf1c71) gives
`run_domainUnported` = 3 on `project-offnetwork`. It emits 650 rows, the key
set already exact, with 384 cells wrong by up to 233x: DEFAULT-domain SHP on
link 2, and all-running weights on link 1. The ported model gives 0.

**What `run_domainUnported` still refuses in PROJECT domain**:

* any emitted pollutant-process without a project generator here
  (`rspp_hasProjectGenerator`):
  * the evaporative processes at Rates scale;
  * the refueling processes;
  * the crankcase processes;
* a (county, road type) without exactly one link, and a second county;
* an out-of-bounds bracket;
* on-network links of different grades (`run_linkGradeMismatches`);
* user start modes that disagree across links or polProcesses
  (`sod_projectConflicts`);
* a user link distribution (`run_userLinkModeRows`). That count includes user
  rows at the evaporative modes 150, 151 and 300, which INSERT IGNORE would
  keep over the generator's;
* a second link at Rates scale (`run_ratesProjectLinks`).

§7.3.58 ports the crankcase and refueling processes at inventory scale, the
evaporative processes at Rates scale and the user's link distribution of
running exhaust and the evaporative modes; its list supersedes this one.

**Unchanged runs.** `project-hotelling`, `project-links`, `scale-project`,
`rates-project` (all eight tables), `process-evap-permeation`,
`process-evap-fvv`, `process-evap-fvv-day`, `process-evap-leaks`,
`rates-venting`, `rates-evap` and `process-refueling` were re-emitted with
`tools/emit-oracle-table.py` and `cmp`'d against the main tree's
`.fixtures-run/`: every relation, shape and table file byte-identical. The
Python binding loads `project-offnetwork`, `project-hotelling` and
`process-evap-leaks`. `project-offnetwork` evaluates in 118 s at 2.2 GB peak,
the same as before the port (134 s, 2.2 GB).

#### 7.3.57 The idle and hotelling adjustment tables: AdjustTotalIdleFraction.sql and the rest of AdjustHotelling.sql

2026-11-10. Until today the model COUNTED, rather than ported, any row of the six
tables through which a county database rewrites an activity input in place:
`idleModelYearGrouping`, `idleMonthAdjust` and `idleDayAdjust`
(AdjustTotalIdleFraction.sql, off-network idle's `totalIdleFraction`;
`run_idleAdjustmentRows`), and `hotellingHourFraction`, `hotellingAgeFraction` and
`hotellingMonthAdjust` (AdjustHotelling.sql's three blocks after
`hotellingHoursPerDay`; `hot_adjustmentRowsUnported`). All six are empty in the
default database and in every county and project database the corpus had, so no
capture exercised them. **`scale-county-idle-adjust` reproduces: 8128 of 8128 rows,
key set exact, worst cell 1.245e-05 (an on-network road type 3 cell the port does
not touch; off-network idle 1.0e-05, extended idle 1.1e-05, APU 6e-06), per-pollutant
sum 7.4e-08, on the port's first run** (after one binding fix, `n_physicsRow` 21).

**The capture** (moves.rs branch `capture-idle-adjust`; host token `1ccc0236`).
`county-inputs/washtenaw-county-idle-adjust/setup-idle-adjust.sql` is
`setup-county.sql` with its Idle and Hotelling sections replaced, routed by
`run-all-fixtures.sh`. Every table varies along every key it carries and leaves some
key of the run without a row: the grouping has three model-year groups for the car
and two for the truck (and a row at the unselected source type 32); `idleMonthAdjust`
states the car's months and not the truck's; `idleDayAdjust` the car's two day types
and the truck's weekday; `hotellingHourFraction` the weekday's 24 hours and the
weekend's 23 (no hour 8), summing to 0.935 and 0.953; `hotellingAgeFraction` ages 0-29
(sum 0.697); `hotellingMonthAdjust` a different value each month; and
`hotellingHoursPerDay` neither default daily total. The RunSpec selects April and
August, both day types and hours 7-8, the gasoline car and the diesel long-haul truck,
road types 1 and 4, and Total Energy at running exhaust, extended idle and APU. MOVES
adds every fuel of both source types and every road type, so MOVESOutput is 8 cells
x 1016 rows.

**Measured before porting**, in pandas from the execution database:

* `totalIdleFraction` as AdjustTotalIdleFraction.sql leaves it: the grouping crossed
  with the run's months and days, times the two multipliers where stated -- **20 of 20
  at 2.2e-16**. The execution database had already dropped source type 32's grouping
  and multipliers, and holds no default row at all.
* `hotellingHours`, by replaying all four blocks of AdjustHotelling.sql on TAG's
  `IdleHoursByAgeHour` x `sampleVehiclePopulation` (24 hours of both day types, before
  the cut to the run's hours) -- **984 of 984 rows, key set exact, at 9.6e-15**.
* The model's factorised form of the same (below) -- 328 fuel-summed rows at 1.0e-14,
  once the age default is taken over full days. Over the run's two hours alone it was
  2.0e-10: TAG's hours are an age factor times a time factor only to that precision.

**What the model does** (conventions §109; all hand-written, spliced into
`onroad/model.esm` by a scratch script, as §7.3.46's were):

1. **Off-network idle's `oni_totalIdleFraction`** is the grouping's fraction at the
   source type and model-year window (`oni_groupedIdleFraction`) when the execution
   database holds any grouping row at a selected source type (`run_idleGroupingRows`),
   else the default's (`oni_defaultIdleFraction`, the old expression), times
   `idleMonthAdjust` and then `idleDayAdjust` where each states the key. The override
   replaces the fraction for EVERY source type, so a selected one the grouping does not
   state has none -- the test database states both.
2. **Hotelling hours.** The hour block replaces the hour's share: `hotellingdist` where
   the zone states no fraction, `hourFraction x sum(hotellingdist)` where it does
   (`hot_hourShare`; the same sum over all 24 hours is `hot_dayShare`). The age block
   rescales by `ageFraction / defaultAgeFraction`, the default being the age's share of
   the full-day hours (`hot_ageAdjustment`). The month block rescales by
   `monthAdjustment / (numMonths x the month's share)` (`hot_monthAdjustment`; MOVES's
   ratio of averages over equal row counts -- 0.9530 and 1.0470 here). `hot_hours` is
   `hot_hourAdjustedHours x hot_ageAdjustment x hot_monthAdjustment` outside PROJECT
   domain; ProjectTAG never calls AdjustHotelling, so PROJECT domain is unchanged.
3. **Two templates** in `lib/onroad_activity.esm`: `stated_adjustment_or_identity` (the
   value where a row matches, 1 where none does, tested on the match count) and
   `stated_hour_share`. The guarded ratios reuse `share_of_group`.
4. **The three idle tables are domain tables.** Their default side is empty, so they
   moved from `onroad/default-database.esm` to `moves-onroad.esm` and every
   `inputs/*.esm`, as the hotelling tables already had; `inputs/washtenaw-county-idle-adjust.esm`
   states the new database's rows (built by `tools/build-scale-input-db.py --copy
   Zone,ZoneRoadType,hotellingActivityDistribution`).

**The port discriminates.** The pre-port model on the same RunSpec refuses it
(`run_domainUnported` 122, the rows it counted) and, read anyway, misses every
off-network idle cell (median 31% for the car, 38% for the truck, worst 49%), every
extended-idle cell (worst x5.3) and every APU cell (worst x4.5); the on-network road
types are within 1.2e-05 either way.

**What is refused now.** `run_idleAdjustmentRows` is gone: AdjustTotalIdleFraction.sql
is ported whole. `hot_adjustmentRowsUnported` counts a hotelling adjustment row only in
a run outside PROJECT domain that selects more than one calendar year: the three
defaults sum over every year `hotellingHours` holds, and TAG adjusts one year at a time
over a table that still holds the earlier years' cut rows. Off-network idle and
hotelling under `aggregateBy` stay counted by `run_selectionUnported` as before. One
caveat is documented rather than counted: the fixture catalogue reads the execution
database, whose `totalIdleFraction` is AdjustTotalIdleFraction's output, so a fixture
whose snapshot stated the multipliers would apply them twice (none does).

**Unchanged runs.** `expand-roadtypes`, `scale-county`, `process-extended-idle[-single]`,
`process-apu[-single]`, `process-crankcase-extidle[-single]`, `project-hotelling`,
`project-links`, `project-offnetwork`, `rates-hotelling`, `rates-hotelling-sourcetypes`,
`rates-evap`, `rates-mechanism`, `rates-nonhaptog`, `rates-pm` and `rates-running` --
every RunSpec that computes off-network idle or hotelling -- were re-emitted with
`tools/emit-oracle-table.py` and `cmp`'d against the main tree's `.fixtures-run/`:
every relation, shape and table file byte-identical. The catalogue move alone was
checked the same way on `process-extended-idle-single` first. `scale-county-idle-adjust`
evaluates in 212 s at 3.8 GB peak. The Python binding loads it.

#### 7.3.58 PROJECT domain, the chained processes, Rates-scale evaporation and the user's link distribution

2026-11-10. Four things `run_domainUnported` refused in PROJECT domain
(§7.3.56's list) each have a capture now, and each reproduces:

| run | selects | network | rows | worst cell |
|---|---|---|---|---|
| `project-crankcase` | THC, CO, NOx for running, start, extended idle and crankcase running, start, extended idle; source types 21 and 62; road types 1, 4, 5 | links 1 (road type 4) and 2 (road type 5), off-network link 3 with the user's start modes | 3252 of 3252 | 8.404e-06 |
| `project-refueling` | THC, TOG refueling displacement and spillage; road types 4, 5 | the same database | 418 of 418 | 9.406e-06 |
| `rates-project-evap` | THC permeation, venting, leaks at Rates scale; source type 21; road types 1, 4 | `project-offnetwork`'s database | RatePerVehicle 128 of 128, RatePerProfile 64 of 64, four tables empty as captured | 8.919e-06 |
| `project-useromd` | CO and Total Energy running, THC permeation, venting, leaks | links 1-3 as above; the user states link 1's running distribution and its evaporative modes | 1274 of 1274 | 1.324e-05 (the generator's link 2; link 1 1.0e-05) |

Every key set is exact and no `cell_exception` was added. moves.rs branch
`capture-project-more` holds the captures (host token `1ccc0236`; the two
new project databases are `county-inputs/washtenaw-project-crankcase/` and
`washtenaw-project-useromd/`). `rates-project-evap` is captured with the
execution database named `MOVESExecution`, as `rates-project` is: the rate
post-processor's PROJECT branch hardcodes it, and the first capture under
the per-host name lost every rate table to a `RUN_ERROR`.

**What turned out PROJECT-specific.** As in §7.3.56, very little, and each
piece was found by evaluating the unchanged model against the capture
before anything was written:

1. **Crankcase: nothing.** CrankcaseEmissionCalculator copies each parent
   row at its own link and road type times `crankcaseEmissionRatio`, and
   neither its Java nor its SQL tests the domain. The pre-port model emitted
   all 3252 rows within tolerance and refused them only for the nine
   crankcase pollutant-processes. `rspp_copiesParentRows` names the
   processes written from their parents' rows alone, and
   `rspp_hasProjectGenerator` admits them: they have their parents'
   generators.
2. **Refueling: one latent defect, not domain logic.** RefuelingLossCalculator
   is the same kind of copy (`rspp_copiesParentRows`), over the Total Energy
   rows of processes 1, 2, 90 and 91. The pre-port model was 25-63% high on
   the long-haul trucks' spillage and right on everything else: ProjectTAG's
   hotelling hours are per zone, so an extended-idle energy block on road
   types 4 and 5 -- where extended idle does not occur and MOVES writes no
   row -- carried a quantity, and refueling's chain read it at the same road
   type. A hotelling block's weight now carries `ppr_occursOnRoad`, as a
   start block's already did; no earlier run reads a hotelling block off its
   road. In DEFAULT domain the same block would have read the DEFAULT
   hotelling hours, so a DEFAULT refueling run with long-haul trucks would
   have had the same error; none is captured.
3. **Rates-scale evaporation: the population.** EvaporativeEmissionsOperatingModeDistributionGenerator's
   `isMesoscaleLookup` is set and never read, TankTemperatureGenerator's is
   commented out, MultidayTankVaporVentingCalculator.sql has no Mesoscale
   section, and ProjectTAG's SHP and SourceHours have no Rates arm. What
   differs is the divisor: RatePerVehicle and RatePerProfile divide by
   MOVESActivityOutput's population, which ActivityCalculator.sql's
   ProjectDomain section writes on the off-network link alone as the zone's
   `offNetworkLink` fleet x ageFraction x the fuel share, summed by the post-processor
   over road type 1. The pre-port model divided by the county's DEFAULT
   population and was 120 times low on every rate (1000 cars against
   Washtenaw's fleet). `act_projectPopulation` is the fleet x ageFraction,
   and `coh_population` takes it in PROJECT domain. RatePerDistance is empty
   in the capture because the run selects no running exhaust, so there is
   no distance activity (`run_writesDistance`). With running exhaust
   selected the on-network evaporative rows would reach it as the
   inventory over the link's distance -- the rate times SourceHours over SHO
   over the speed, not the speed-bin quotient `rtRate_rated` writes in
   DEFAULT domain -- and that arm is unmeasured, so `run_ratesProjectEvapDistance`
   refuses it.
4. **The user's link distribution: two precedences.** LinkOperatingModeDistributionGenerator
   skips a link with ANY opModeDistribution row for a running
   pollutant-process (java:330, selected or not; `omd_linkRunningRows`), and
   BaseRateGenerator then weights that link's running exhaust by the user's
   rows, which SourceTypePhysics copies to each physics row's offset mode
   (the capture's 13 rows for a long-haul truck become 143, eleven physics
   rows of the same fractions). `omd_userFraction` is the user's fraction at
   (pollutant-process, hour-day, mode, source type, link), the input
   table's `linkID` and `polProcessID` read for the first time, and `pp_W`
   takes it on such a link. The evaporative generator writes with INSERT
   IGNORE, so a user row stands mode by mode: `evap_W` is now the user's
   fraction where `omd_userRows` finds one and `evap_WGenerated`, the old
   expression, elsewhere. The pre-port model was wrong on every link-1 cell,
   by up to 7 times on venting.

**Refusals.** Removed: the crankcase and refueling processes at inventory
scale, the evaporative processes at Rates scale, and user link rows of the
two families ported. Still refused, each counted by `run_domainUnported`
and each unmeasured:

* the crankcase and refueling processes at Rates scale (the post-processor
  divides processes 15, 18 and 19 by the link's average speed, and 16 and
  17 go to RatePerVehicle and RatePerHour; no capture);
* evaporative rows a PROJECT Rates run would write to RatePerDistance
  (`run_ratesProjectEvapDistance`);
* user link rows outside the two families, and every user link row at Rates
  scale (`run_userLinkModeRows`); on a link the user states, a running
  pollutant-process with no user row at a selected hour-day and source type,
  and brake or tire wear (`run_userLinkGaps`);
* and, unchanged from §7.3.56: a (county, road type) without exactly one
  link, a second county, an out-of-bounds bracket, on-network links of
  different grades, conflicting user start modes, and a second link at
  Rates scale.

§7.3.60 ports two links on one road type, link grades, out-of-bounds brackets,
conflicting user start modes and the user's running and brake-wear rows that
leave gaps at inventory scale; its list supersedes this one there.

Before the port the four runs gave `run_domainUnported` = 9, 2, 3 and 55.

§7.3.59 ports the Rates-scale items of this list -- the crankcase and refueling
processes, evaporative RatePerDistance, a second link and the user's link rows
of the two families -- and its list supersedes this one.

**Unchanged runs.** After each item, `scale-project`, `rates-project` (relation,
shape and all six tables), `project-links`, `project-hotelling`, `project-offnetwork`,
`process-crankcase-running`, `-start`, `-extidle`, `-start-single`,
`-extidle-single`, `process-refueling`, `rates-evap`, `rates-venting` (all
tables each), `process-evap-permeation`, `-fvv`, `-fvv-day` and `-leaks` were
re-emitted with `tools/emit-oracle-table.py` and `cmp`'d against the main
tree's `.fixtures-run/`: every relation, shape and table file
byte-identical. The Python binding loads the four new runspecs and
`project-offnetwork`. `docs/project-tag.md` §6.5's oracle, run over the new
snapshots, reproduces all five ProjectTAG outputs on them too (SHO 943,
Starts 328, SHP 205, SourceHours 492, hotelling hours 492 rows across the
corpus). `project-crankcase` evaluates in 4 min at 4.3 GB peak, the others
in 1.5-2.5 min at 2.2 GB.

`tools/build-scale-input-db.py` gained one fix on the way: a quoted value
after a blank was split at a comma inside it (`project-useromd`'s link
name); `washtenaw-project-crankcase`'s files rebuild byte-identical.

#### 7.3.59 PROJECT domain at Rates scale: the chained processes, a second link, evaporative RatePerDistance and the user's link distribution

2026-11-11. §7.3.58 left four PROJECT refusals at Rates scale, each unmeasured:
the crankcase and refueling processes, the evaporative rows a Rates run writes
to RatePerDistance (`run_ratesProjectEvapDistance`), a second link
(`run_ratesProjectLinks`), and every user link row (`run_userLinkModeRows`'s
Rates arm). Three new captures exercise all four, and each reproduces every
Rates table:

| run | selects | network | tables | worst cell |
|---|---|---|---|---|
| `rates-project-chained` | THC, CO for running, start, extended idle and crankcase running, start, extended idle; THC refueling displacement and spillage; source types 21 and 62; road types 1, 4, 5 | `project-crankcase`'s: links 1 (road type 4, 30 mph) and 2 (road type 5, 25 mph), off-network link 3 | RatePerDistance 2080 of 2080, RatePerHour 250 of 250, RatePerVehicle 1065 of 1065; RatePerStart, RatePerProfile, StartsPerVehicle empty as captured | 1.008e-05 |
| `rates-project-evap-links` | THC running, permeation, venting, leaks; source type 21; road types 1, 4, 5 | the same database | RatePerDistance 632 of 632 (384 evaporative), RatePerVehicle 128 of 128, RatePerProfile 64 of 64 | 8.919e-06 |
| `rates-project-useromd` | `project-useromd` at Rates scale | `project-useromd`'s: the user states link 1's running and evaporative modes | RatePerDistance 1082 of 1082, RatePerVehicle 128 of 128, RatePerProfile 64 of 64 | 8.919e-06 |

Every key set is exact and no `cell_exception` was added. moves.rs branch
`capture-rates-project-more` holds the captures (`aff4c13f`, host token
`1ccc0236`, moves-snapshot/v2, execution database named `MOVESExecution` for
every `rates-project-*` fixture). No new project database: the first two run
on `washtenaw-project-crankcase`, the third on `washtenaw-project-useromd`.
`docs/project-tag.md` §6.5's oracle reproduces all five ProjectTAG outputs on
the three new snapshots too (SHO 1353, Starts 410, SHP 328, SourceHours 861,
hotelling hours 615 rows across the corpus).

**What MOVES does, from RatePostProcessorRatesFirst.sql's PROJECT branch.**
It divides BaseRateOutput's emissionRate by `MOVESExecution.link.linkAvgSpeed`
for processes 1, 9, 10, 15, 18 and 19 on every link, then writes
RatePerDistance from BaseRateOutput for 1, 9, 10, 15 everywhere and 18, 19 off
road type 1 (prerequisite Total Energy rows included: BaseRateOutput is not
stripped), and a SECOND RatePerDistance insert for 11, 12, 13 off road type 1
as MOVESOutput over MOVESActivityOutput's distance; it skips RatePerStart and
StartsPerVehicle, writes RatePerHour from BaseRateOutput for 17, 90, 91, 93,
and RatePerVehicle as MOVESOutput over the zone's population summed over road
type 1's links.

**What turned out PROJECT- or Rates-specific.** Again little, and each piece
was found by evaluating the unchanged model against a capture first:

1. **The copy processes: nothing of their own.** With
   `rspp_hasProjectGenerator` admitting `rspp_copiesParentRows` at both
   scales, crankcase running, crankcase start, crankcase extended idle and
   refueling's off-network rows reproduced at once: 15, 18 and 19 inherit the
   link-speed division through their parents' rates (`rt_isLinkSpeedRated`),
   16 and 17 go to RatePerVehicle and RatePerHour. RatePerVehicle was 1065 of
   1065 on the pre-port model.
2. **Three latent defects the copies exposed, none domain logic:**
   * *Refueling's RatePerDistance rows were written once per speed bin.*
     `rpd_inTable` kept one bin on road type 1 and on a PROJECT link only for
     the running family. The gate is now its own flag, `rpdKeptBin`, read by
     every process RatePerDistance takes.
   * *RatePerHour's link.* `rto_linkID` was the synthesized
     `(zoneID*10 + roadTypeID)*100` in every domain; in PROJECT domain
     BaseRateOutput carries the project's link (3 here), now `run_linkID`.
   * *The hotelling RATE on a road it does not occur on.* §7.3.58 gave a
     hotelling block's QUANTITY weight `ppr_occursOnRoad`; its rate
     (`rtRate_hotellingMeanBaseRate`, which RatePerHour reads) did not have
     it, and refueling's chain on road types 4 and 5 read extended idle's
     energy rate there: the long-haul trucks' spillage per mile was 4.3-6.2
     times MOVES's, a constant 0.313 g/mi added to every model year. Both the
     rate and its A/C term now carry the flag, a factor of exactly 1 where
     the process occurs. A DEFAULT Rates run with refueling and long-haul
     trucks would have shown it too; none is captured.
3. **A second link: nothing.** Both runs put two on-network links at Rates
   scale; the per-road-type keys `rtRate_rated`, `rpd_linkID` and
   `run_linkAvgSpeed` read were right as written in §7.3.55.
4. **Evaporative RatePerDistance: the divisor.** Measured in pandas first:
   the model's own evaporative inventory over the capture's running-exhaust
   distance (inventory over RatePerDistance, per cohort) reproduces all 384
   evaporative RatePerDistance cells of `rates-project-evap-links` within
   1.0e-05. In DEFAULT domain that quotient is the per-SourceHour rate over
   the bin's speed, because SourceHours is SHO on the network, and the model
   writes it so (`rt_isHourlyPerMile`). In PROJECT domain ProjectTAG's
   SourceHours on a link lacks the travel-time share, so the quotient is the
   rate over the link's LENGTH, not its speed -- the pre-port model's
   bin-speed quotient is wrong by a factor that differs per link. So
   `rpd_ratePerDistance` is now the post-processor's two inserts:
   `rpdEmissionRate` (the old expression, BaseRateOutput's rate), except an
   evaporative row on a PROJECT link, which is `out_emissionQuant /
   rto_distance`; `rto_distance` is DistanceCalculator.sql's `SHO.distance x
   fuelTypeActivityFraction`, the output row's activity (SHO per real day,
   the basis its quantity is on -- the first attempt used SHO over all the
   day type's days and came out 5 times low) x `coh_usedShare` x the link's
   speed.
5. **The user's link distribution at Rates scale: nothing.** The pre-port
   model reproduced all three tables of `rates-project-useromd`; only the
   refusal counted (`run_domainUnported` 55, the run's user running and
   evaporative rows). `run_userLinkModeRows` no longer has a Rates arm.

**Refusals.** Before the port the three runs gave `run_domainUnported` = 9,
4 and 55; after it 0. Removed: the crankcase and refueling processes at Rates
scale, `run_ratesProjectEvapDistance`, `run_ratesProjectLinks` (and
`run_onNetworkLinkCount`, which only they read), and user link rows of the
two ported families at Rates scale. Still refused in PROJECT domain, each
counted by `run_domainUnported`:

* user link rows outside the two families (`run_userLinkModeRows`), and on a
  link the user states, a running pollutant-process with no user row at a
  selected hour-day and source type, or brake or tire wear (`run_userLinkGaps`);
* a (county, road type) without exactly one link, a second county, an
  out-of-bounds bracket, on-network links of different grades, and
  conflicting user start modes (§7.3.56's list; the inventory-scale
  structural refusals, ported in a parallel branch).

**Unchanged runs.** After the port, every PROJECT run (`scale-project`,
`rates-project`, `rates-project-evap`, `project-links`, `project-hotelling`,
`project-offnetwork`, `project-crankcase`, `project-refueling`,
`project-useromd`), every DEFAULT Rates run (`rates-evap`, `rates-venting`,
`rates-hotelling`, `rates-hotelling-sourcetypes`, `rates-start`,
`rates-running`, `rates-wear`, `rates-pm`, `rates-nonhaptog`,
`rates-mechanism`, `rates-minimal`) and the inventory crankcase and
refueling runs (`process-crankcase-running`, `-start`, `-start-single`,
`-extidle`, `-extidle-single`, `process-refueling`) were re-emitted with
`tools/emit-oracle-table.py` and `cmp`'d against the main tree's
`.fixtures-run/`: every relation, shape and table file byte-identical (26 runs, 130 files), after renaming the two RatePerDistance helpers out of the `rpd_` prefix -- `tools/emit-oracle-table.py` emits every `rpd_*` variable as a column, and the first names made every RatePerDistance file two columns wider. The Python binding loads the three new
runspecs. `rates-project-chained` evaluates in 4.3 min at 4.1 GB peak,
`rates-project-evap-links` in 1.7 min and `rates-project-useromd` in 2.6 min at
2.2-2.3 GB.

**The suite.** `./run-tests.sh` in the worktree: 703 ok and 1 FAIL against main's
668 ok. That is +36 for the three runspecs (each has seven table and shape checks,
three fixture-stage table lines, and a validate and round-trip line), and the one
FAIL was the `no-county-join` probe. It counts the county key pairs it deletes,
and `rto_linkID` and `rto_distance` add two (21 to 23), so
`tools/make-runspec-probe.py` now expects 23. Run directly, the probe document
writes, evaluates and moves `expand-counties`. So the expected total is 704 ok /
0 FAIL. Wall time was 2 h 43 min (8,764 s user CPU) and peak RSS 7.1 GB.

#### 7.3.60 PROJECT domain, the structural refusals: a link is a location, link grades, user distributions with gaps, start-mode conflicts

2026-11-11. Five structural cases `run_domainUnported` refused at inventory
scale in PROJECT domain (§7.3.58's list) each have a capture now. Four are
ported and reproduce; the fifth, a second county, stays refused, because MOVES
itself refuses it.

| run | network | selects | rows | worst cell |
|---|---|---|---|---|
| `project-multilink` | links 1 and 4 on road type 5, 2 and 5 on road type 4, off-network link 3; IDs out of road-type order | source types 21, 32; running, start, brake, tire, THC permeation and leaks | 7654 of 7654 | 1.324e-05 |
| `project-grades` | five on-network links of grades 0, 4, -3, 0 and 1.5 %, one at 80 mph (above every schedule of road type 4) and one at 2 mph (below source type 21's on road type 5) | source types 21, 62; running, brake, tire | 5245 of 5245 | 8.770e-06; 21 cells to 2.430e-05 under one scoped exception |
| `project-useromd-gaps` | link 1: user running CO only, brake wear for source type 21 only, a tire-wear row; link 2: user brake wear alone | source types 21, 32; running CO and Total Energy, brake, tire | 2468 of 2468 | 1.324e-05 |
| `project-startconflict` | user start modes A (CO) and B (Total Energy) on the off-network link, C (CO) on the on-network link | source types 21, 32; running and start CO and Total Energy | 939 of 939 | 7.763e-06 |

Every key set is exact. moves.rs branch `capture-project-structural` holds the
captures (host token `1ccc0236`) and the four project databases,
`county-inputs/washtenaw-project-{multilink,grades,useromd-gaps,startconflict}/`.
Before the port the four runs gave `run_domainUnported` = 4, 8, 27 and 8.

**What MOVES actually does, measured before porting:**

1. **Two links on one road type are two locations.** ExecutionLocationProducer
   iterates the Link table; ProjectTAG, LinkOperatingModeDistributionGenerator
   and BaseRateGenerator (`isNewLink`) each run per link, and
   RatesOpModeDistribution is rebuilt per link for its road type. docs/project-tag.md
   §6.5 reproduces ProjectTAG's five outputs on `project-multilink` once the
   Link table's FLOAT columns are narrowed (its 0.3 mi decided three SHO cells'
   sixth digit), and docs/link-operating-mode-distribution.md §6.5 reproduces
   the generator on all four links.
2. **Each link's distribution is at its own grade.** The generator copies each
   bracketing schedule into driveScheduleSecondLink at the LINK's average grade
   (java:685-695) and deletes a bracket's rows before recomputing them
   (java:1158), so two links sharing a schedule at different grades walk it
   twice. The link-distribution oracle reproduces all 24,999 cells of
   `project-grades` under FLOAT storage.
3. **An out-of-bounds speed is extrapolated, not refused.** CompilationFlags'
   ALLOW_DRIVE_CYCLE_EXTRAPOLATION is TRUE: the generator logs a WARNING (a
   run promotes it to RUN_ERROR in its log) and brackets the link with the
   nearest schedule on both sides, factor 0. The run completes, all 15 bundles.
   The model's bracket fallback (`latest_at_or_before_key`) already did this;
   only the refusal (`run_bracketsOutOfBounds`) is retired.
4. **A user-governed distribution is the user's alone, and an empty one writes
   no row.** A link with any user running row is skipped by the generator
   (java:330); on any other link tempExistingOpMode keeps the generator off
   every (source type, polProcess) the user states (java:836-860). So on
   `project-useromd-gaps`' link 1 running Total Energy, which the user does not
   state, has no RatesOpModeDistribution row and MOVES writes NO output row for
   it, nor for the trucks' brake wear; the cars' brake wear is the user's four
   modes, mode 501 among them at its own rate (BaseRateGenerator's `OR
   er.OpModeID = 501`). Link 2's brake wear is the user's over the generator's.
   Tire wear's project generator writes RatesOpModeDistribution from the link's
   speed and never reads opModeDistribution, so the user's tire row changes
   nothing.
5. **Conflicting start modes: the first row written wins.** Step 400's INSERT
   IGNORE keys the user's rows by neither link nor polProcess. MOVES's road-type-1
   RatesOpModeDistribution carries distribution A for both start polProcesses:
   the rows written first, where a primary-key scan would have put link 1's C
   first. A MyISAM scan returns rows of one key in the order they were written.
6. **A second county is refused by MOVES.** MacroscaleGeographicBounds rejects a
   PROJECT RunSpec with more than one county ("Only one county may be selected
   at Project Scale", and the section status requires exactly one), and a
   project database is one county's. No realistic project selects two; the
   refusal (`run_countyCount`) is the faithful behaviour and stays.

**The model, priced first.** A link axis would have touched every
per-road-type variable. Instead the road-type relation became the LOCATION
relation by appending rows: `runspecroadtype_rows` is the run's selected road
types followed by the project links that share a (county, road type) with an
earlier one -- `n_projectExtraLinks`, declared and checked like `n_outputRate`
-- and every project-link lookup joins on `lnk_locationOrdinal` instead of the
road type (six equations). The questions about the SELECTED road types (the
drive-schedule selection, `run_roadTypeID`, the chain's road-type test, twelve
equations) moved to the file relation `rsrf_roadTypeID`, where a duplicated
road type would have double-counted. Nothing per location changed shape. The
grade promotion's forward closure was twelve variables, the per-second link
chain and nothing else, so it gained a grade-slot axis, `projectgrade_rows` of
the declared `n_projectGrade` (default 1), each location reading its grade's
slot: a DEFAULT run walks the chain once, as before. Items 4 and 5 are
`omd_userGoverned` and `omd_userGap` in `pp_W` and in rate-row survival
(`rt_hasLinkModes`, beside `rt_hasHotellingModes`), a block emitted per
location only where a rate row in it emits (`ppr_hasEmittingRow`), and
`sod_projectFirst`, the first matching row in the input table's order.
Conventions §112.

**The one exception.** On `project-grades`' -3 % link, electric cars' Total
Energy cancels regenerative (negative) mode rates against positive ones 25.6x
per mode; MOVES carries FLOAT intermediates as six-digit text between its
worker and external calculator and sums them after, so its 21 cells there are
off by up to 2.4e-5, random in sign by model year, while the model's
`lomd_W` matches the captured opModeDistribution and every other link stays
inside 8e-06. `tolerance.toml` holds those cells to 5e-5.

**Refusals.** Removed: two links on one road type, links of different grades,
an out-of-bounds bracket, conflicting user start modes, and user running and
brake-wear rows that leave a gap, at inventory scale. Still refused, each
counted by `run_domainUnported`:

* a second county -- MOVES's own RunSpec validation refuses it;
* a selected road type with no project link (`run_linkCountMismatches`);
* user link operating-mode rows outside running exhaust, brake wear, tire
  wear and the evaporative modes on a link (an off-network link's running or
  hotelling rows), and every user link row at Rates scale (`run_userLinkModeRows`);
  user running or brake-wear rows covering some but not all selected hour-days
  (`run_userLinkGaps`): the anti-join is keyed without the hour-day and the
  model's rate rows carry none -- unmeasured;
* the Rates-scale cases §7.3.58 lists (crankcase and refueling, evaporative
  RatePerDistance, a second link), which the Rates-scale work owns;

* and, NEW, an on-network link of zero speed (`run_projectZeroSpeedLinks`):
  the generator walks thirty seconds of idling as a drive schedule
  (java:340-375) and ProjectTAG's SHO takes its `else` arm, neither ported nor
  captured. The out-of-bounds refusal used to catch it; without that, the
  ported extrapolation would bracket it at the slowest schedule.

Still neither ported nor refused, as before: a user drive schedule
(`driveScheduleSecondLink`), the first arm of step 100. No catalogue mounts
the table, so a project database stating one is silently read as an
average-speed link.

§7.3.62 refuses the user drive schedule first and then ports it, with the
zero-speed link, at inventory scale; its list supersedes this one there.

#### 7.3.61 AdjustHotelling at a second calendar year: the table still holds the first

2026-11-11. `hot_adjustmentRowsUnported` counted a hotellingHourFraction,
hotellingAgeFraction or hotellingMonthAdjust row in any run of more than one
calendar year (§7.3.57). **`userdb-hotelling-multiyear` reproduces: 15616 of
15616 rows, key set exact, worst cell 1.245e-05 (an on-network running cell the
port does not touch; extended idle 1.0e-05, APU 7e-06), per-pollutant sum
1.3e-07, no `cell_exception`.** The refusal now counts a THIRD year only.

**Where such a run comes from.** Not from a county database: MOVES refuses a
county or project domain database with more than one calendar year, even with
domain validation skipped (`A domain database can contain only one calendar
year`, ImporterManager.java:2311 -- the first capture attempt, as a SINGLE run,
stopped there). A DEFAULT-domain run may select several years and merges every
user input database its `<databaseselections>` names, input rows first, exactly
as it merges a scale input database. So the fixture is a DEFAULT-domain run
naming `washtenaw_cdb` as a user database: moves.rs branch
`capture-hotelling-multiyear`, `county-inputs/washtenaw-userdb-hotelling-multiyear/setup-userdb-hotelling-multiyear.sql`
(`setup-idle-adjust.sql` with every year-keyed table at 2015 and 2020, and
`hotellingHoursPerDay` different at each), `fixtures/userdb-hotelling-multiyear.xml`
(`scale-county-idle-adjust`'s selections at 2015 and 2020), host token `1ccc0236`.
In the model a user database is a domain document like any other
(`inputs/washtenaw-userdb-hotelling-multiyear.esm`, `runspecdomain` DEFAULT): the
model distinguishes PROJECT domain from the rest and nothing else, and every
merge it ports is the same merge.

**What changes with several years**, read from TotalActivityGenerator.java and
AdjustHotelling.sql and then measured:

1. **The table is cleared per process, not per year.** TAG runs once per (zone,
   year) inside the master loop's process > location > year order;
   `clearActivityTables` deletes `hotellingHours` only when the PROCESS changes,
   and after adjusting a year TAG deletes that year's rows outside the RunSpec's
   hours. So when it adjusts 2020 the table holds 2015's adjusted rows at hours
   7 and 8 beside 2020's 24 hours. (The execution database confirms it: the
   final `hotellingHours` holds 984 rows of each year.)
2. **The hotellingHoursPerDay block is per year**, the one block that is: its
   defaults and its join carry `yearID`, and only the target year's rows get a
   day type. Unchanged.
3. **The hour, age and month blocks are not.** Their defaults
   (`defaultHourFraction` by zone, day and hour; `defaultAgeFraction` by zone and
   ageID; `defaultMonthAdjust` by zone and month) are taken over EVERY row the
   table holds, both years, and the rewrite multiplies every row too. The age
   block joins on ageID, so 2015's age 5 pools with 2020's age 5 -- different
   model years. The 2015 rows' rewrite does not reach the output (2015 was
   computed and consumed before 2020's TAG ran), but they weigh in every 2020
   default.
4. **And one thing that was true at one year too: the input merge cuts
   `hotellingHourFraction` to the RunSpec's hours.** The execution database holds
   3 of the 47 rows (both days' hour 7, the weekday's hour 8). At one year this
   cannot be seen -- every default is a ratio over one year's hours, which carry
   the same day shares -- and the §7.3.57 model rescaled all 24 hours of its full
   day. Pooled with an earlier year's per-cell rows it moves the age default by
   1e-4. `hot_hourFractionRows` now counts a row only at a selected hour.

**Measured before porting** (pandas, the execution database): replaying the four
blocks over 2015's rows and 2020's TAG hours (`IdleHoursByAgeHour`, which TAG
truncates per year and so holds 2020's) reproduces 2020's 984 `hotellingHours`
rows at 4.2e-15, and the age block's own leftover table `newHotellingHours_had`
(the SQL never drops it; it holds both years after 2020's age block) on all
9360 rows at 4.3e-15. 2015's rows were recovered from the final table, where
2020's blocks rescaled them, by a fixed point of `final = R1 x G(R1)`. Adjusting
2020 alone misses by up to 52% (median 38%). The pooled 2020 month defaults are
0.9590 and 1.0410.

**What the model does** (conventions §113; hand-written, spliced into
`onroad/model.esm` by a scratch script, as §7.3.57's were):

1. **The one-year chain takes its defaults per calendar year**: `hot_totalHours`,
   `hot_monthHours`, `hot_allMonthHours` and `hot_monthAdjustment` gain the year
   axis, `hot_ageHours` joins on it, and its product is `hot_ownHours`. Before,
   they summed over every year of the activity relation -- right at one year,
   wrong at two even without an earlier-year pool.
2. **The pooled chain** for a year whose table holds an earlier year's rows
   (`hot_earlierHours > 0`): the earlier rows at each output cell
   (`hot_earlierCellHours`, the earlier year's `hot_ownHours`), by day and by
   hour-day; the year's own full-day TAG hours per unit of `hotellingdist`
   (`hot_dayUnit`); the hour factor `hourFraction / defaultHourFraction` with the
   default `(earlier + own) at the hour / (earlier + own) over the day`
   (`hot_pooledHourFactor`, and the shares `hot_pooledHourShare` /
   `hot_pooledDayShare`); the age default over own full-day hours plus the
   earlier rows times their cell's hour factor (`hot_earlierAgeHours`,
   `hot_pooledAgeAdjustment`); the month default likewise, with the age
   adjustment too (`hot_earlierMonthHours`, `hot_pooledMonthAdjustment`).
   `hot_hours` takes the pooled product where the pool is non-empty and
   `hot_ownHours` elsewhere, so every run of one year computes exactly what it
   did.
3. **Each day once.** Every activity row of a day's output cell carries that
   day's full-day hours, so the one-year defaults counted each day once per
   selected hour and the counts cancelled in the ratio. Pooled with per-cell
   earlier rows they do not cancel: `hot_dayCellCount` divides the own part (the
   first pooled run was 1.0% low on the own part, every 2020 cell off by up to
   11%).
4. **One template**, `stated_over_default(match_count, stated, part, total)` in
   `lib/onroad_activity.esm`: `stated / (part / total)` where the key is stated,
   the identity where not, built from `stated_adjustment_or_identity` and
   `share_of_group`. The hour, age and month blocks all use it.

**The port discriminates.** The pre-port model on the same RunSpec refuses it
(`run_domainUnported` 89, the adjustment rows it counted) and, read anyway,
misses every extended-idle and APU cell of both years: 2015 extended idle by up
to 59% (median 13%) -- its defaults summed both years' full days -- and 2020 by
up to x2.7 (median 49%), APU x2.4. Running exhaust is within 1.2e-05 either way.

**What is refused now.** `hot_adjustmentRowsUnported` counts the three tables'
rows only in a run of THREE or more years: a third year's table holds the first
year's rows rescaled again by the second's blocks and the second's as the pooled
chain leaves them, which the model does not carry (it would be a recurrence over
the year axis with a table-valued state). No capture exercises it. Hotelling
under `aggregateBy` (`hot_aggregationUnported`, in `run_selectionUnported`)
stays refused: it needs a capture of its own -- the pre-aggregation rewrites the
hour and day tables AdjustHotelling and AdjustStarts read -- and covers start
exhaust as well, so it was not taken on here.

**Unchanged runs.** `scale-county-idle-adjust`, `process-extended-idle[-single]`,
`process-apu[-single]`, `process-crankcase-extidle[-single]`, `project-hotelling`,
`scale-county`, `rates-hotelling`, `rates-hotelling-sourcetypes` and
`expand-multiyear` (the corpus's one other multi-year run) were re-emitted with
`tools/emit-oracle-table.py` and `cmp`'d against the main tree's `.fixtures-run/`:
every relation, shape and Rates table byte-identical but one: `scale-county-idle-adjust`'s relation moves in 222 extended-idle and APU cells by at most 4.0e-14 relative (item 4 of the list above, a ratio that was already right reassociated; still 8128 of 8128 at 1.245e-05). `userdb-hotelling-multiyear` evaluates in 6-7 min at 5.1 GB peak, `run_domainUnported` and `run_selectionUnported` 0. The Python binding loads it.

**Merging §7.3.59-§7.3.61 (2026-11-11).** The three were developed in parallel, each measured on its own captures, and two of their ports meet where neither was measured. §7.3.59 reproduces Rates scale with one link per road type, and §7.3.60 several links on a road type at inventory scale, so `run_projectShortfall` counts `n_ratesScale` x `run_projectExtraLinks`: two links on one road type at Rates scale stay refused. Likewise §7.3.60 measured user brake- and tire-wear link rows at inventory scale only, and §7.3.59 the running and evaporative families at Rates scale, so `run_userLinkModeRows` admits brake and tire wear at inventory scale only. Both are refusals of an unmeasured combination, not a known defect; each needs one capture.

#### 7.3.62 PROJECT domain, step 100's drive-schedule arm: a user drive schedule and a zero-speed link

2026-11-11. Two PROJECT link-activity inputs real hot-spot analyses state were
the last arm of LinkOperatingModeDistributionGenerator's step 100 not ported:
a USER DRIVE SCHEDULE (`driveScheduleSecondLink`, second-by-second speed and
grade on a link) and an on-network link of ZERO average speed (an idling
queue). The first was neither ported nor refused -- no catalogue mounted the
table, so a project database stating one was read as an average-speed link
(§7.3.60's last paragraph); the second was refused (`run_projectZeroSpeedLinks`).
Both now reproduce:

| run | network | selects | rows | worst cell |
|---|---|---|---|---|
| `project-driveschedule` | link 1 (road type 5, stated 30 mph): a 110-second signal approach -- deceleration to a stop, 22 s stopped, a creep below 1 mph, acceleration, a 35 mph cruise; link 2 (road type 4, stated 45 mph): a 67-second on-ramp merge at grades of 4, 3, 2 and 0.5 %, a hard brake on the uphill in its second second, seconds 41-43 missing; link 3 (road type 4, 55 mph): no schedule | source types 21, 62; running CO, Total Energy, atmospheric CO2; brake and tire wear PM10/PM2.5 | 3672 of 3672 | 1.090e-05 |
| `project-zerospeed` | link 1 (road type 5, 25 mph): the approach; link 2 (road type 5, 0 mph): the queue | source types 21, 62; running THC, CO, NOx, Total Energy; brake and tire wear | 2444 of 2444 | 1.324e-05 (the queue's 1.0e-05) |

Every key set is exact and no `cell_exception` was added. moves.rs branch
`capture-project-driveschedule` holds the fixtures and captures (host token
`1ccc0236`, moves-snapshot/v2) and the two project databases,
`county-inputs/washtenaw-project-{driveschedule,zerospeed}/`. **The refusal
came first** (commit c72f5bc): `driveScheduleSecondLink` mounted in every onroad
catalogue, and `run_userLinkSchedules` counting its rows on a selected
on-network link into `run_projectShortfall`. On the pre-refusal model (main,
5d44014) `project-driveschedule` evaluates to `run_domainUnported` = 1, and only
because link 2's stated 3 % takes a grade slot there that `n_projectGrade` 1 does
not declare; declared (2), it evaluates to **0 and emits all 3672 rows, key-exact,
with 2554 cells wrong by up to 81 %** (links 1 and 2; brake wear's sum 4 % low) --
the hole. On the refusal commit it gives 178: the schedules' 177 rows and that
grade. `project-zerospeed` gives 1 on both (`run_projectZeroSpeedLinks`).

**What MOVES does, measured before porting** (LinkOperatingModeDistributionGenerator.java,
the capture SIF's `/opt/moves` copy; docs/link-operating-mode-distribution.md §2.1, §6.5):

1. **Step 100 walks the link instead of bracketing it** (java:309-393) when it
   has `driveScheduleSecondLink` rows and no user running opModeDistribution
   row, or when its `linkAvgSpeed <= 0`, for which it first INSERTs thirty
   seconds of speed 0 at grade 0 (java:343-367, "with 0 speed, brakes are
   likely applied"). `calculateOpModeFractionsCore` (java:922-1183) then runs
   on the real link for every RunSpec source type and physics row: no
   brackets, no interpolation, the same CASE, five-decimal quotients and 501
   fold as the bracketing walk.
2. **It writes the schedule's average back into Link** before anything reads
   it (java:937-948), at loop priority `GENERATOR+1`, "because this generator
   fills Link.linkAvgSpeed ... needed by ProjectTAG to do SHO calculations"
   (java:71-79). So SHO, its distance, tire wear's project mode and the rates
   copy's `avgBinSpeed` all read 21.1055 mph on link 1 (stated 30; tire mode
   405, not 407) and 50.8433 on link 2 (stated 45; mode 411, not 410). The
   snapshot's Link carries both. The first second's acceleration is 0 (the
   SQL's coalesce has no forward difference); each second's grade is its own
   -- At0 reads `a.grade`, At1 `b.grade`, At2 `c.grade`, VSP `a.grade`
   (java:996-1006); and `c`, `d` are LEFT JOINed through `b`, `c`
   (java:1009-1011), so a gap zeroes the next three seconds' history. Link 2's
   second-second brake (-2.4 mph/s) is At0 = -1.52 on its 4 % ramp and does
   not brake.
3. **A zero-speed link is all mode 501**: running exhaust's distribution is
   mode 1 at fraction 1 (every physics row's 1+offset), and brake wear's
   stays mode 501 under the TEMP source types (SourceTypePhysics' `opModeID <>
   501`), which the copy to RatesOpModeDistribution drops -- so the queue has
   NO brake-wear output row, 350 rows MOVES does not write. Tire wear's
   project generator gives it mode 400. ProjectTAG's SHO takes its `else` arm
   (ProjectTAG.java:355-365): the link-volume product with no travel-time
   share, distance 0 -- `link_travel_hours_share` already said so, and §6.5 of
   docs/project-tag.md now reaches it.
4. **The national schedules are FLOAT.** Link 3's long-haul trucks bracket at
   schedules 353 and 354, the first capture to reach 354, whose second 56
   (64.9 -> 63.9 mph) is -1.000000000000007 in double and exactly -1.0 as the
   FLOAT column stores it; `At0 < -1` makes it braking in double only, and the
   model's brake wear on that link came out up to 5.2e-04 high. The link
   oracle reproduces all 41,224 cells of the corpus with binary32 speeds and
   moves 88 bracketing cells with double ones.

Each was reproduced in pandas before it was ported: the extended link oracle
(docs/link-operating-mode-distribution.md §6.5: 1,452 walked cells on three
links, every one exact, and the Link row's speed asserted as the schedule's
average) and the ProjectTAG oracle (docs/project-tag.md §6.5: 246 and 164 SHO
keys, every cell at the FLOAT's six digits once the walked speed is derived
from the schedule rather than read from the snapshot's six-digit rendering).

**The model** (conventions §114), all behind `lsl_walksSchedule`, the
generator's own condition: PROJECT domain, an on-network link, a selected
running or brake-wear pollutant-process (the generator's two subscriptions),
no user running row on the link, and user rows or a stated speed <= 0.

* **The walk**, `lsec_*`, over `linksecond_rows` -- the input's rows plus one
  padding slot (`n_driveschedulesecondlink + 1`), so no catalogue computes over
  an empty relation (F56): each column is `concat(input column, one padding
  row)`, the chain edge list's shape (an equality-filtered gather is refused by
  tools/check-conventions.py, which caught the first version); the
  prior second is a join on (link, second - 1); At1 and At2 are the previous
  second's At0 and At1; the braking test, VSP, rectangles and CASE are the
  bracketing walk's templates with the grade read per second.
* **Per location**, `lsl_*`: the seconds, stopped seconds and per-mode counts
  over the location's slots (`lsec_locationOrdinal` = the link's
  `lnk_locationOrdinal`), the idle schedule closed to thirty stopped seconds
  (`zero_speed_link_idle_seconds`), the five-decimal quotients
  (`link_op_mode_fraction`) and the fold (`stopped_folded_into_idle`, a new
  template the bracket fractions now use too). `lomd_W` and `lomd_WBrake`
  take the walk's distribution at a walked location.
* **The write-back**: `run_linkAvgSpeed` is the walk's average at a walked
  location, and `act_projectSho` reads it instead of the stated column; a
  walked location takes no grade slot (`run_projectLinkGrade`).
* **The absence**: `lsl_brakeGap` beside `omd_userGap` in `rt_hasLinkModes`
  drops brake wear where the walk leaves it no mode.
* **The FLOAT columns**: `float_column_value` (lib/drive_cycle.esm, with
  `binary32_spacing`) rounds to binary32 with the format's own ops -- floor,
  log, `^`, sign, abs -- exactly, against numpy on every one-decimal value in
  [-200, 2000]; the bracketing walk reads `lomd_storedSpeed` and its link
  grade through it, and the user walk its speeds and grades.

**Refusals.** Removed: a user drive schedule and an on-network link of zero
speed at inventory scale. Still refused, by `run_projectScheduleUnported` into
`run_projectShortfall`, each unmeasured:

* a walked schedule (a user's or a zero-speed link's) at Rates scale -- the
  post-processor divides by `linkAvgSpeed`, 0 on the queue;
* an emitted evaporative pollutant-process beside a walked location: its
  fraction of operating is SHO, which the walk's speed moves, over
  SourceHours, which it does not;
* user brake-wear opModeDistribution rows on a walked link: the walk's
  `tempExistingOpMode` anti-join joins on the TEMP source type
  (java:1114-1121) and never matches.

A schedule on a link the generator does not walk -- no running or brake-wear
process, a user running distribution, the off-network road type -- is ignored
by MOVES and read as stated by the model, so it is not counted. §7.3.60's
other refusals stand.

**Unchanged runs.** After the port, all sixteen PROJECT runs -- `scale-project`, `project-links`, `project-hotelling`, `project-offnetwork`, `project-crankcase`, `project-refueling`, `project-useromd`, `project-multilink`, `project-grades`, `project-useromd-gaps`, `project-startconflict`, `rates-project`, `rates-project-evap`, `rates-project-chained`, `rates-project-evap-links` and `rates-project-useromd` -- were re-emitted with
`tools/emit-oracle-table.py` and `cmp`'d against the main tree's
`.fixtures-run/`: every relation, shape and Rates table byte-identical (62 files), the FLOAT reading included. The Python binding loads both new runspecs.
`project-driveschedule` evaluates in 153 s at 2.5 GB peak, `project-zerospeed`
in 117 s at 2.3 GB.

**The suite.** `./run-tests.sh` in the worktree, SNAPSHOTS on a corpus equal to
moves.rs main plus the two captures: **739 ok / 0 FAIL against main's 729 / 0**.
The +10 are the two runspecs' validate, round-trip, MOVESOutput and shape checks
(8) and the two input documents' data-open controls (2); the bindings and
index-set-rename counts each moved by the new table and axes (117 -> 118, 171 ->
173). Wall 3 h 16 min (11,058 s user CPU), peak RSS 7.2 GB.
#### 7.3.63 Time aggregation: the pre-aggregation runs BEFORE the generators, and the output time step is a sum

2026-11-11. Until today `hot_aggregationUnported` refused every run that selects a
start or hotelling process, or off-network idle, AND aggregates hours or day types,
and no capture of the corpus's 83 aggregated anything but running-exhaust energy at
one day type and one source type (`expand-month`, `expand-fullyear`; both output at
Hour). Real county inventories nearly always carry start exhaust, and users set
`aggregateBy` and a coarser `<outputtimestep>` to cut run time.
**`scale-county-timeagg-day` reproduces: 12576 of 12576 rows, key set exact, worst
cell 8.833e-06, per-pollutant sum 5.9e-07; `scale-county-timeagg-month` 6288 of
6288, key set exact, worst cell 8.000e-06, per-pollutant sum 5.1e-07. No
`cell_exception`.**

**The survey** (what the model refused or could not express, and after):

| configuration | before | after |
|---|---|---|
| `aggregateBy` Hour (every run but two) | ported | unchanged |
| `aggregateBy` 24-Hour Day (PreAggDAY.sql), running exhaust | not refused, WRONG: the cell's hour-day `dayID` (2, 5 at hour 0) is not in the default `hourday`, so `rsd_dayID` looked up 0 and every cell read as a whole-week aggregate | ported, captured |
| `aggregateBy` Day, start / crankcase start / extended idle / APU / off-network idle | refused (`hot_aggregationUnported`) | ported, captured |
| `aggregateBy` Month (PreAggDAY.sql then PreAggMONTH.sql), running, one day type and one source type | ported (`expand-month`) | unchanged, byte-identical |
| `aggregateBy` Month, TWO day types | not refused, wrong: DayWeighting1 assumed to cancel (0.36 on the collapsed AvgSpeedDistribution) | ported, captured |
| `aggregateBy` Day or Month, several source types | not refused, wrong: HourWeighting3 summed over the source types (5e-04 on the collapsed temperature) | ported: ONE source type by `SourceTypeOrdering` |
| `aggregateBy` Month, start / hotelling / off-network idle | refused | ported, captured |
| `aggregateBy` Year (PreAggYEAR.sql) | not expressible: it collapses the MONTHS (MonthOfAnyYear 0, month-group-weighted fuel supply, ATRatio, MonthGroupHour, monthVMTFraction) | unchanged; priced below |
| `<outputtimestep>` Hour | ported | unchanged |
| `<outputtimestep>` Month, Year | not expressible: the oracle's dayID/hourID (and monthID) are NULL and each row a sum | ported (`mos_*`), captured |
| `<outputtimestep>` 24-Hour Day, Portion of Week | not expressible | unchanged; priced below |
| hotelling under aggregation at two or more calendar years | refused | still refused (`run_aggregationUnported`) |
| off-network idle under aggregation with AdjustTotalIdleFraction inputs | refused | still refused |
| start / hotelling / off-network idle in a whole-week cell of a RunSpec selecting one day type | refused | still refused (unmeasured: starts tables are cut to the selected days, travel is not) |
| evaporative processes under aggregation | NOT refused, not captured | refused (TankTemperatureGenerator reads SampleVehicleTrip with every hour collapsed to 0) |
| refueling, crankcase, brake and tire wear under aggregation | not refused | not refused: copies of their parents and rate-side means the captures exercise; uncaptured |
| Rates scale under aggregation | refused (`run_ratesUnported`: MOVES refuses it) | unchanged |

**What MOVES does, and in which order.** MasterLoop runs
`InputDataManager.preAggregateExecutionDB()` ("Preaggregate data") after the input
merge and BEFORE `MOVESInstantiator.performInstantiation`, i.e. before any
generator: PreAggDAY.sql whenever `aggregateBy` is not Hour, then PreAggMONTH.sql at
Month or coarser, then PreAggYEAR.sql at Year (InputDataManager.java:2646-2730).
So TotalActivityGenerator, AdjustStarts.sql and AdjustHotelling.sql, the operating
mode generators and BaseRateCalculator all read the COLLAPSED tables:

* PreAggDAY.sql, per day type: `HourDay` becomes `(hourDayID = dayID, hourID 0)`;
  HourVMTFraction 1.0; AvgSpeedDistribution the HourWeighting1 (`hourVMTFraction`)
  mean; ZoneMonthHour and MonthGroupHour the HourWeighting3 mean -- `avg` over the
  day types of HourWeighting2 at ONE source type, the first selected one in
  `SourceTypeOrdering` (21, 31, 32, 52, 61, 54, 62, 43, 53, 41, 42, 51, 11) -- with
  no day type, so every day type reads the same weather; sourceTypeHour's
  `hotellingDist` and startsHourFraction SUMMED over the hours; startsOpModeDistribution
  `sum(opModeFraction x allocationFraction)` (not divided); hotellingHourFraction
  summed.
* PreAggMONTH.sql, over the RunSpec's day types: `HourDay` `(0,0,0)`, DayVMTFraction
  1.0, DayOfAnyWeek `(0, Whole Week, 7)`; AvgSpeedDistribution the DayWeighting1
  mean (`sum(dayVMTFraction x noOfRealDays x monthVMTFraction)/sum(monthVMTFraction)`
  over the RunSpec's months); sourceTypeHour by DayWeighting2 (road-type weighted);
  startsPerDay and startsPerDayPerVehicle `sum(x * dayID / 7)` -- the dayID, which is
  the day's number of real days only by MOVES's numbering; startsOpModeDistribution
  weighted by `dayID x startsPerDayPerVehicle` and normalised over the modes;
  startsHourFraction and hotellingHourFraction renormalised to 1;
  hotellingHoursPerDay `sum(hours x noOfRealDays / 7)`; totalIdleFraction
  `sum(tif x DayWeighting2Normalized)`; idleDayAdjust `sum(adj x noOfRealDays / 7)`.
  The tables were cut to the RunSpec's SELECTED day types before this ran: the
  `expand-month` execution database holds `startsPerDayPerVehicle` 2.6313 =
  `3.6839 x 5/7`, the weekday's alone.
* Then TAG runs AdjustStarts.sql per day type (`spAdjustStarts(0/2/5)`: starts =
  startsPerDay x combined age effect x monthAdjustment x the collapsed
  allocationFraction x startAllocFactor x noOfRealDays) and AdjustHotelling.sql over
  hotelling hours computed from the collapsed `hotellingDist`, each block's default
  now a share of ONE collapsed hour (`defaultHourFraction` 1, so the hour block
  rescales by the collapsed `hourFraction` itself).
* The output: AggregationSQLGenerator converts each row to the output time step on
  the worker. At Hour (and 24-Hour Day) `convertDays`, `x 1/noOfRealDays` -- the
  division this model already makes in `rtDay_activity`, so the output relation's
  cells are classical days. At Month and Year `convertWeeks` instead:
  `SUM(emissionQuant x noOfDays/7)` over the cells of the slot, on the cell's portion
  of a WEEK, with dayID and hourID (and at Year monthID) NULL.

**Measured before porting**, in pandas from the default database against each
execution database's collapsed tables: DAY -- startsHourFraction 6 of 6 at
2.2e-16, startsOpModeDistribution 1968 of 1968 at 3.8e-16, sourceTypeHour 2 of 2
at 2.2e-16, AvgSpeedDistribution 384 of 384 at 4.5e-06 (its storage), ZoneMonthHour
temperature 6.8e-10 (5.0e-04 summing over the source types); MONTH --
startsOpModeDistribution 984 of 984 at 3.9e-16, startsPerDayPerVehicle exact,
startsPerDay `375571428.57` = `(312e6 x 2 + 401e6 x 5)/7`, sourceTypeHour 2.2e-16,
AvgSpeedDistribution 192 of 192 at 4.5e-06 (0.36 with the day types unweighted),
totalIdleFraction 120 of 120 at 2.3e-08 (DayWeighting2Normalized is a FLOAT
column), ZoneMonthHour 6.8e-10. The collapsed Starts table is not in the
execution database (TAG truncates it per process); SHO is, 2460 of 2460 at 5e-06
against the model's.

**The captures** (moves.rs branch `capture-time-aggregation`, host token
`1ccc0236`, moves-snapshot/v2): `county-inputs/washtenaw-county-timeagg/setup-timeagg.sql`
is `setup-county.sql` with stated `startsPerDay` (all three source types on both
day types, each a different multiple of the default) and `setup-idle-adjust.sql`'s
four hotelling tables (the weekend without hour 8, day sums 0.953 and 0.935).
`scale-county-timeagg-day`: SINGLE domain, January and July 2020, both day types,
all 24 hours, the gasoline car and light commercial truck and the diesel long-haul
truck, road types 1 and 4 (MOVES adds 2, 3, 5 for off-network idle), THC, CO, NOx
at running, start, crankcase start, extended idle and APU, `aggregateBy` 24-Hour
Day, output Month. `scale-county-timeagg-month`: the same at January, April, July
and October, `aggregateBy` Month, output Year. 232 MB and 129 MB, most of it
`emissionRateByAge` (67 MB), which every criteria-pollutant capture carries.

**What the model does** (conventions §115; hand-written, spliced into
`onroad/model.esm` by scratch scripts, as §7.3.57's were):

1. **The cell unpacks its own hour-day** (`rsd_dayID`, `rsd_hourID`:
   `mod(hourDayID,10)`, `floor(hourDayID/10)`, the templates `hour_day_day` and
   `hour_day_hour` in the new `lib/time_aggregation.esm`), so a day-aggregated cell is
   its day type at the synthesized hour, and `tcell_collectsHours` /
   `tcell_collectsDays` say which collapse the cell is.
2. **Each collapsed table the generators read is a variable at the cell** that is
   the table's own row on a run that does not aggregate: `st_hourFraction`,
   `st_perDayStated`, `st_perDayDefault` (`st_dayWeekWeight`, `dayID/7`),
   `sod_defaultWeight` (`sod_hourWeight`, `sod_dayWeight`, `sod_weekWeight`),
   `hot_hourDistribution` (`hot_cellDayDistribution`, `hot_weekDayWeight`),
   `hot_dayDistribution`, `hot_hourShare` / `hot_dayShare` (the collapsed hour
   fraction `hot_cellHourFractionStated`), `hot_hoursPerDayInput`
   (`tcell_dayWeekShare`, `noOfRealDays/7`), `oni_defaultIdleFraction`
   (`oni_dayWeight`, DayWeighting2Normalized), and the DayWeighting family
   (`dw_*`). The generator equations downstream are unchanged: AdjustStarts and
   AdjustHotelling over a collapsed table are the same scripts.
3. **The weather is weighted by one source type** (`met_isWeightingSourceType`,
   `preaggregation_source_type_order`) and carries no day type (`met_cellWeight`
   over the hours only); **the speed distribution is a two-stage mean**, hours by
   HourWeighting1 within the day and days by DayWeighting1 in a whole-week cell
   (`asd_cellShare`).
4. **The output time step is a relation of its own**, `outputstep_rows` and
   `mos_*`: the output relation with its month and cell levels narrowed to the slots
   the step keeps, `mos_emissionQuant` the slot's rows summed times
   `noOfRealDays x weeksPerMonth` (`outStepWeeks`), every other column read from the
   slot's first row (`output_step_column`). Two declared metaparameters say which
   step (`n_outputSumsDays` 1 at Month and Year, `n_outputSumsMonths` 1 at Year),
   relayed like `n_ratesScale`. A run's oracle source tagged `output-time-step` is
   emitted from `mos_*` (`tools/emit-oracle-table.py --table movesoutput_step`); every
   other run is still emitted from `out_*`.
5. **A pre-existing gap found on the way**: APU's THC, CO and NOx biodiesel fuel
   ratios (`generalFuelRatioExpression` 191, 291, 391, model years 1950-2060) were
   not among the base fuel ratio rows, so every 2010-2020 diesel APU cell -- the only
   ones with an APU fraction -- was 2.5% high on THC and CO and 0.4% low on NOx. No
   earlier capture selected APU criteria pollutants. Three more `gfb_*` rows.

**The port discriminates.** The pre-port model refuses `scale-county-timeagg-day`
(`run_selectionUnported` 1) and, read anyway, misses 10739 of its 12576 cells:
start, crankcase start and extended idle zero, running about twice the oracle.
Each pre-port shortcut measured alone: HourWeighting3 summed over the source
types moves the collapsed temperature by 5e-04, DayWeighting1 dropped moves the
collapsed speed distribution by 0.36.

**What is refused now.** `hot_aggregationUnported` is gone; `run_aggregationUnported`
(in `run_selectionUnported`) counts, on a run that aggregates: hotelling at more
than one calendar year (the pooled AdjustHotelling chain is written per hour of the
clock); off-network idle with any AdjustTotalIdleFraction input (PreAggMONTH.sql
collapses idleDayAdjust before that script runs); start, hotelling or off-network
idle in a whole-week cell whose RunSpec selects fewer day types than the week; and
any evaporative process. Not expressible and not refused, because nothing in a
snapshot says so (the RunSpec XML does): `aggregateBy` Year (declared and ported since §7.3.65), and the 24-Hour Day
and Portion of Week output steps. **Their cost:** Year pre-aggregation collapses
the month axis the whole fuel chain is keyed by (MonthGroupHour, month-group
fuel supply weighting, ATRatio, monthVMTFraction by MonthWeighting) -- a
month-collapse analogue of this section's day collapse over perhaps twice the
variables, and a capture; the two day output steps are one more slot level
(sum a day type's hour cells, and `x 1/noOfRealDays` undone at Portion of Week),
about six variables and a capture each.

**Unchanged runs.** `expand-month`, `expand-fullyear` (the two that aggregate),
`scale-county`, `scale-county-idle-adjust`, `userdb-hotelling-multiyear`,
`process-extended-idle[-single]`, `process-apu[-single]`,
`process-crankcase-start[-single]`, `rates-start`, `rates-hotelling`,
`project-crankcase`, `project-startconflict`, `expand-day` and
`process-evap-fvv-day` (every hour of two day types, which reads the unpacked
hour-day) were re-emitted with `tools/emit-oracle-table.py` and `cmp`'d against
the main tree's `.fixtures-run/`: every relation, shape and Rates table
byte-identical. `scale-county-timeagg-day` evaluates in 9 min 19 s (470 s user CPU)
at 7.5 GB, `-month` in 14 min 44 s (667 s) at 7.8 GB, `run_domainUnported` and
`run_selectionUnported` 0 on both. The Python binding loads both. `./run-tests.sh` in the branch's sibling worktree: 738 ok / 2 FAIL against main's 729 / 0 -- eleven new `ok` (the two runs' validate, test, number and shape lines, the data-open domain document, and `lib/time_aggregation.esm` twice), and the two FAILs are `run-link-omd-oracle.sh` and `run-project-tag-oracle.sh` sweeping two PROJECT snapshots (`project-zerospeed`, `project-driveschedule`) a parallel branch added to the shared moves.rs corpus mid-run; both oracles pass over the corpus without them. 3 h 01 min wall, 10,309 s user CPU (main 2 h 50 min, 9,200 s), 7.8 GB peak.

#### 7.3.64 Every on-road process under time aggregation: the tank-temperature chain has no neighbour hour

2026-11-12. §7.3.63 ported start exhaust, hotelling and off-network idle under
`aggregateBy` 24-Hour Day and Month, and left `run_aggregationUnported` refusing
every evaporative process (TankTemperatureGenerator reads SampleVehicleTrip with
every hour collapsed to 0); refueling, crankcase, brake and tire wear were not
refused and had never met a capture. A real county inventory selects all of them.
**`scale-county-timeagg-processes-day` reproduces: 19628 of 19628 rows, key set exact, worst cell 1.802e-05, per-pollutant sum 6.5e-07; `scale-county-timeagg-processes-month`
78512 of 78512, key set exact, worst cell 1.256e-05, per-pollutant sum 4.1e-07. Five cells are held by two scoped precision `cell_exception`s (below): a Year sum that cancels 12x, and one cohort whose whole-week SHP cancels 1,315x in MOVES's FLOAT columns.**

**The survey** (MOVESOutput's processes at each level, what PreAggDAY.sql /
PreAggMONTH.sql do to what each calculator reads, and what MOVES then writes;
InputDataManager.preAggregateExecutionDB runs both BEFORE any generator, so
every table a generator WRITES -- AverageTankTemperature, SoakActivityFraction,
ColdSoakTankTemperature, SHO, SourceHours, OpModeDistribution -- is empty when
the scripts run, and their sections act only on user-stated rows):

| process (calculator) | reads | 24-Hour Day (PreAggDAY.sql) | Month (then PreAggMONTH.sql) | what MOVES writes |
|---|---|---|---|---|
| TankTemperatureGenerator TTG-1 (ColdSoakTankTemperature) | ZoneMonthHour, hours h and h+1 (TankTemperatureGenerator.java:361-368, `zmh1.hourID = zmh2.hourID-1 OR 24/1`) | ZoneMonthHour ONE row per month at hourID 0 (HourWeighting3 mean) | the same | **nothing**: an hour-0 row pairs with no other, so QuarterHourTemperature, QuarterHourTankTemperature and ColdSoakTankTemperature are empty |
| TTG-2 (SampleVehicleTripByHour) | SampleVehicleTrip, HourDay | every trip at hourID 0 of its day type; HourDay `(dayID, dayID, 0)` | every trip at day 0, hour 0; HourDay `(0,0,0)`; SampleVehicleDay folded to day 0 (cut to the RunSpec's day types and source types first) | each trip's FIRST segment only, one row per real trip of the run's vehicles (13,129): the walk's next hour `hourID+1` has no HourDay row |
| TTG-3..5 (HotSoakTemperature, OperatingTemperature, AverageTankTemperature) | the walk and TempColdSoakTankTemperature | -- | -- | **nothing**: every step joins the empty cold-soak temperature |
| TTG-6 (SoakActivityFraction) | HotSoakTemperature, eMinutes `60 x vehicles`, oMinutes | -- | eMinutes over the folded day 0 | mode 151 `(e - o - 0)/(e - o)` = **exactly 1** per source type, cell and month (12 rows each level); mode 150 none, its count joins the empty HotSoakTemperature |
| TTG-7 (ColdSoakInitialHourFraction) | the walk's records per hour-day | -- | -- | rows pairing day 2 with day 5 as if they were hours (fractions 1.98, 4.51); read ONLY by TVV-3, which joins it to the empty ColdSoakTankTemperature |
| TankFuelGenerator | fuel supply by month group | untouched | untouched | unchanged |
| Permeation (EvaporativePermeationCalculator.sql) | AverageTankTemperature x OpModeDistribution x SourceHours | -- | -- | **no rows**: AverageTankTemperature is empty |
| Vapor venting (MultidayTankVaporVentingCalculator.sql) | 151: ColdSoakTankTemperature, ColdSoakInitialHourFraction, sampleVehicleSoaking; 150/300: ZoneMonthHour temperature and tank RVP (TVV-8); OpModeDistribution, SourceHours | ZoneMonthHour collapsed; SourceHours/SHO computed by TAG over the collapsed tables | the same over the whole week | 151 **none** (TVV-3 joins the empty cold-soak temperature); 150 weight 0 (no SAF row); 300 the operating insert at the collapsed temperature, weighted by fractionOfOperating |
| Liquid leaks (LiquidLeakingCalculator.sql) | OpModeDistribution (EvapOMDG: SAF x (1 - fOp), 300 the residual), SourceHours, SHO | as above | as above | 151 at `1 - fOp`, 300 at `fOp`; fOp `least(1, SHO/SourceHours)` per link over the collapsed sums -- the off-network link's SHO is off-network idle's, 0.27 to 1 |
| Refueling displacement, spillage (RefuelingLossCalculator.sql) | ZoneMonthHour at RunSpecHour (REFEC-1), parent Total Energy | hourID 0 temperature | the same | the chain over its collapsed parent |
| Crankcase running, start, extended idle | parent's rows x `crankcaseEmissionRatio` | parents collapsed (§7.3.63) | the same | copies of the collapsed parents |
| Brake and tire wear | running OMD from AvgSpeedDistribution (HourWeighting1 mean), SHO; PM10 chained from PM2.5 | AvgSpeedDistribution collapsed | DayWeighting1 mean | as running exhaust's activity |


**The captures** (moves.rs branch `capture-timeagg-processes`, host token `1ccc0236`,
moves-snapshot/v2, capture binary rebuilt first): the county database is §7.3.63's
`setup-timeagg.sql` unchanged. `scale-county-timeagg-processes-day`: SINGLE domain,
January and July 2020, both day types, all 24 hours, the gasoline car and light
commercial truck and the diesel long-haul truck, road types 1 and 4 (MOVES adds 2, 3,
5), THC, CO and NOx at running, start, extended idle and crankcase running, start and
extended idle; Total Energy at running exhaust; THC at permeation, venting, leaks,
refueling displacement and spillage; PM10 and PM2.5 brake and tire wear --
`aggregateBy` 24-Hour Day, output YEAR (the earlier day capture took Month).
`scale-county-timeagg-processes-month`: the same at January, April, July and October,
`aggregateBy` Month, output MONTH (the earlier took Year). 278 MB and 313 MB, 66 MB of
each `emissionRateByAge`. MOVES ran 1.5 minutes each.

**What MOVES does, and in which order** (the survey's consequences; InputDataManager.java:2646-2730
for the order, MasterLoop's "Preaggregate data" before `performInstantiation`):

1. PreAggDAY.sql (then PreAggMONTH.sql) collapse ZoneMonthHour to one hour-0 row per
   month, SampleVehicleTrip to hour 0 (and day 0), and fold SampleVehicleDay -- already
   cut to the RunSpec's day types and source types -- into day 0 at Month. Their
   AverageTankTemperature and SoakActivityFraction sections find empty tables: the
   generators that fill them have not run.
2. TankTemperatureGenerator TTG-1 pairs each ZoneMonthHour hour with the next
   (TankTemperatureGenerator.java:361-368). An hour-0 row has none, so ColdSoakTankTemperature
   is EMPTY, and so is everything joined to it: TTG-3/4's hot soaks, TTG-5's
   AverageTankTemperature, TVV-3's cold-soak vapor. TTG-6 then writes mode 151 at
   `(e - o - 0)/(e - o)`, exactly 1, and no mode 150 (12 rows, every one 1, at both levels).
3. TankFuelGenerator (TankFuelGenerator.java:421) takes the zone's min and max over the
   collapsed ZoneMonthHour: one row, so `zoneMax - zoneMin <= 0` and its evaporative
   temperature is the collapsed mean. July's tank RVP is 8.0 for gasoline and 7.7 for E85
   (the clamp), where the 24 hours give 7.979 and 7.694.
4. EvaporativeEmissionsOperatingModeDistributionGenerator weights mode 151 by
   `SAF x (1 - fOp)` and puts the rest on 300; its fOp sums SHO and SourceHours over the
   ages whose SourceHours is POSITIVE (`WHERE sourceHours>0`, :204). The collapsed
   off-network SHP -- `population x noOfRealDays - SUM(SHO)` over the whole day -- is
   negative at the newest model years in July weekdays, so the filter binds there: the
   passenger car's fOp is 0.477 with it, 0.859 without.
5. The calculators: permeation joins AverageTankTemperature and writes NO row; venting
   writes 300 (TVV-8 at the collapsed temperature and RVP) and nothing at 151; leaks
   write 151 and 300 at their rates; refueling, crankcase, brake and tire wear run over
   their collapsed parents and activity exactly as §7.3.63's processes do. Every output
   cell, the negative evaporative cells of the newest model years included (MOVESOutput
   holds -20.6 g for a 2019 light truck's venting), is then summed to the output step (§7.3.63's `mos_*`).

**Measured before porting.** In pandas against each execution database: SAF 12 of 12 rows
mode 151 at exactly 1, AverageTankTemperature and ColdSoakTankTemperature 0 rows,
SampleVehicleTripByHour one hour-0 row per real trip of the run's vehicles (13,129),
TTGeMinutes `60 x` SampleVehicleCount (Month: 1,168 / 1,118 / 171 vehicles), the collapsed
oMinutes ABOVE eMinutes for source types 32 and 62 on weekdays (51,034 > 46,380) --
where the ratio is still 1 -- and fOp per (source type, month, day type) with and without
the positive-age filter. Then, observed from the model with `esm simulate --observed`
(87 s, 1.5 GB -- the observed set is pruned now, unlike §7.3.52's): fOp, SourceHours per
age on road type 1 (492 of 492 at 6.5e-06, the column's storage), the collapsed
temperature, SAF, eMinutes and the tank RVP, each against the snapshot's value.

**The non-evaporative processes needed no aggregation change.** The first evaluation
of the day run, before any edit, reproduced running (including off-network idle),
start, extended idle, crankcase running, start and extended idle, refueling displacement
and spillage, and PM10 and PM2.5 brake and tire wear at worst cell 9e-06 -- 23 of the
27 (pollutant, process) pairs. What it missed was evaporative (permeation 640 rows MOVES
does not write, venting +13 %, leaks +7.5 %) and one pre-existing gap with no
aggregation in it:

**Total Energy at running exhaust, selected beside refueling, was dropped (1,490 rows).**
`flagRequiredPollutantProcesses` adds Total Energy at running, start and extended idle
for a refueling loss, flags the additions `silentlyRequired`, and the output processor
strips them; `require()` does not flag a pair the user selected, so 9101 is kept and
9102, 9190 are not. The execution database records the expanded set either way, and
`rspp_isSilentlyRequired` -- which documented exactly this blind spot -- stripped all
three. The datum is the RunSpec's, so it is declared as `<modelscale>` and
`<outputtimestep>` are: `n_statedEnergyProcesses` (bits over the needs table's three
exhaust processes; 1 here), relayed by `onroad/default-database.esm`, `moves-onroad.esm`
and `inputs/washtenaw-county-timeagg.esm`. A real inventory selecting CO2 or energy
beside refueling hits it at any `aggregateBy`.

**What the model does** (conventions §116; hand-written, spliced into
`onroad/model.esm` by scratch scripts):

1. `ttg_hasColdSoakTankTemperature` (run): 1 - `run_aggregatesHours`. It gates the
   three consumers of the cold-soak temperature -- `ttg_hotSoakOpModeCount`,
   `ttg_hasAverageTankTemperature`, `tvv_pairExists` -- and `rt_hasTankTemperature`
   makes a permeation rate row ABSENT (`rt_survivesRated`), so `n_outputRate` drops by
   the 640 pairs MOVES does not write. The model's TTG reads the national hourly table,
   which is why the run, not the table, has to say it.
2. `ttg_existenceMinutes` counts the vehicles of every selected day type a cell collects
   (`tcell_dayMatch` over `db_rateday`), as PreAggMONTH.sql's fold does. Before, a
   whole-week cell (day 0) matched no vehicle, eMinutes was 0, SAF 0 and every soak
   share went to mode 300.
3. `tfg_minimumTemperature` / `tfg_maximumTemperature` read the one collapsed row
   (`tfg_collapsedTemperature`, the cell's `run_temperature`) on a run that aggregates
   its hours, the 24 hours otherwise (`tfg_hourly*`).
4. `evap_shoTotal` and `evap_sourceHoursTotal` sum the positive-SourceHours ages only.
5. `n_statedEnergyProcesses` and `rfn_isStated` above.

**The port discriminates.** Each piece measured alone on the day run: the cold-soak gate
is the whole permeation key set (640 rows) and off-network venting and leaks (SAF 150 of
1-8 % where MOVES has none); the TankFuelGenerator range is on-network venting's
uniform 0.99945 (gasoline) and 0.99985 (E85); the positive-age filter is off-network
venting +27 % and leaks +23 % in July; the eMinutes fold is every Month-level soak share.

**What is refused now.** `run_aggregationUnported` no longer counts evaporative
processes; `run_evapSelected` is deleted, and `run_offNetworkLinkCount` -- the shape
check's guard on venting at road type 1 in a run that aggregates hours -- is retired with
its column (tools/check-runspec-shape.py, run-tests.sh). Still counted, on a run that
aggregates: (1) hotelling at more than one calendar year; (2) off-network idle with an
AdjustTotalIdleFraction input; (3) start, hotelling or off-network idle in a whole-week
cell whose RunSpec selects fewer day types than the week -- all three unchanged from
§7.3.63 -- and NEW (4): an evaporative process over a STATED soakActivityFraction
(`run_soakActivityInputRows`), which PreAggDAY.sql collapses to
`sum(soakActivityFraction x HourWeighting2)` (PreAggMONTH.sql then by DayWeighting2)
before TTG-6 keeps it, and which the model reads at the cell's own hour-day. Its price:
about four variables over weightings the model already has (`met_hourWeight`,
`dw_roadDayWeight`) and a capture whose county database states the table. Not counted,
because nothing in a snapshot or a runspec can see it: a RunSpec whose SourceHours at an
on-network cell is non-positive at EVERY age (MOVES writes no FractionOfOperating row and
so no evaporative row there; the model would). Neither capture comes near it -- the
on-network SourceHours is SHO.

**Tolerance.** Two scoped `cell_exception`s, each naming only the cells over the gate.
Day: venting of the 2019 light truck on road type 1, -20.639 g at Year, the sum of
three positive cells and a July-weekday cell of -138.9 g (negative SHP) -- a 12x
cancellation that puts the port's ordinary 2e-06 per-cell residual at 2.6e-05; held
to 5e-05. Month: the 2015 light truck's July venting and leaks on road type 1 (four
cells, -0.0026 to -1.36 g), whose whole-week SHP is -4.47 h, `population x 7`
(5.232e6) less the national SHO (5.236e6): a 1,315x cancellation in two FLOAT columns,
where one float32 ulp of the national SHO, 0.5 h, is up to 1.3e-04 of the difference;
measured 3.5e-05 to 4.0e-05 and held to 1e-04. Every other cell is inside 2e-05.

**Also found and fixed, with no aggregation in it.** `run_onRoadPollutantProcessCount`
counted brake and tire wear in a run that also selects road type 1 ("tire wear's are
not ported"), so both new runs reported `run_selectionUnported` 4. No capture had
selected road type 1 beside brake or tire wear in the default or single-county domain;
these two are the first, MOVES writes no wear row on road type 1 in either (with
off-network idle's SHO on that link), and the model emits none. Wear is no longer
counted.

**Unchanged runs.** Re-emitted with `tools/emit-oracle-table.py` on the final model and
`cmp`'d against the main tree's `.fixtures-run/`: `expand-month`, `expand-fullyear`, `scale-county`, `scale-county-timeagg-day` and `-month` (relation and `movesoutput_step`), `scale-county-idle-adjust`, `process-evap-permeation`, `-leaks`, `-fvv`, `-fvv-day`, `process-refueling`, `process-crankcase-running`, `-start`, `-start-single`, `-extidle`, `-extidle-single`, `process-brakewear`, `process-tirewear`, `rates-evap` and `rates-venting` (and their six Rates tables), and -- because the eMinutes join, the positive-age filter and the stated-energy rule reach them -- `project-offnetwork`, `project-useromd`, `project-refueling`, `project-crankcase`, `rates-project-evap`, `rates-project-evap-links`, `rates-project-useromd` and `rates-project-chained` (and their Rates tables): 28 runs. Every relation and every
oracle table is byte-identical; each shape file differs only by the retired
`run_offNetworkLinkCount` column (0 in all of them). The Python binding (EarthSciAST
`main` 0519b012e) loads both new runspecs. `scale-county-timeagg-processes-day`
evaluates in 18 min 20 s (890 s user CPU) at 13.6 GB and `-month` in 26 min 30 s (1,250 s) at 14.0 GB, both on a node shared with two other lanes' evaluations, `run_domainUnported` and
`run_selectionUnported` 0 on both. `./run-tests.sh` in this lane's sibling worktree: 758 ok / 1 FAIL against main's 749 / 1. The `ok` set is main's plus eight -- each new run's round-trip, validate, reproduction and shape lines -- plus the `join.on` scaling gate, main's one FAIL, the cold-cache flake, which passed this time. The FAIL is `document figures vs the corpus`: `docs/omd-generator-reachability.md` counts the shared snapshot corpus, which three lanes grew from 85 directories to 97 today (two of them this section's), so its figures are right only once every lane is merged and the document is re-derived (`tools/check-reachability-counts.py`). 4 h 20 min wall, 14,616 s user CPU, 14.0 GB peak, on the same shared node.

#### 7.3.65 Time aggregation by year: PreAggYEAR.sql collapses the months, and its fuel supply is a sum

2026-11-12. §7.3.63 left `aggregateBy` Year neither expressible nor refused:
nothing in an execution database says PreAggYEAR.sql ran, the RunSpec XML does.
It is now a declared run property, `n_aggregatesMonths` (relayed like
`n_outputSumsMonths` through every catalogue), and it is ported for what one
capture checks. **`scale-county-timeagg-year` reproduces: 18071 of 18071 rows,
key set exact, worst cell 1.134e-05, per-pollutant sum 9.2e-07, no `cell_exception`.**

**What MOVES does, and in which order.** `InputDataManager.preAggregateExecutionDB`
(InputDataManager.java:2646-2730) runs PreAggDAY.sql, then PreAggMONTH.sql, then,
at `aggregateBy` Year (`compareTo(OutputTimeStep.YEAR) >= 0`), PreAggYEAR.sql --
all after the input merge and before `MOVESInstantiator.performInstantiation`, so
before every generator. ExecutionRunSpec then loads its months from the collapsed
`MonthOfAnyYear` instead of the RunSpec (ExecutionRunSpec.java:424-445): the run
has ONE month, 0, and the execution database's `runspecmonth`, `runspecmonthgroup`,
`monthofanyyear` and `monthgroupofanyyear` say so. AdjustHotelling.sql's
`numMonths` is then 1 and its `monthID = 0` arm skips the multiplication
(AdjustHotelling.sql:46-67). The output step is unchanged from §7.3.63's Year
step: one cell times `noOfRealDays x 365/7`.

**The survey of PreAggYEAR.sql** (500 lines; every table it rewrites):

| table | collapse at MonthOfAnyYear 0 / monthGroup 0 | weight | in the model |
|---|---|---|---|
| MonthOfAnyYear, MonthGroupOfAnyYear | one row, `Whole Year`, 365 days | -- | `whole_year_days` |
| DayVMTFraction, MonthVMTFraction | 1.0 per (source type, road type) / source type | -- | `year_value_or_own`; the day-VMT sums averaged by `mag_meanShare` |
| SourceTypeDayVMT, HPMSVTypeDay | `sum(VMT x actFract)` | MonthWeightingBySourceType / MonthWeighting | not read: no county database here states daily VMT |
| SHO, SourceHours, Starts | summed over months | -- | empty at that point (TAG writes them later) |
| StartsMonthAdjust, HotellingMonthAdjust | 1 | -- | `year_value_or_own` |
| ZoneMonthHour | MEAN, molWaterFraction/heatIndex/specificHumidity zeroed (MeteorologyGenerator recomputes them) | MonthWeighting: `monthVMTFraction` of the HIGHEST selected sourceTypeID with travel | `mag_meanShare` |
| MonthGroupHour (FLOAT intermediate) | MEAN | MonthGroupWeighting: `SourceTypeOrdering`'s first | `mag_groupShare` |
| ATRatio, ATBaseEmissions | MEAN | MonthGroupWeighting | ATBaseEmissions `mag_groupShare`; ATRatio refused (air toxics) |
| FuelSupply | `(1 - fractDontHave) x haveFract` = `sum(marketShare x actFract)`: a SUM | MonthGroupWeighting | `mag_groupSum`, `ffsup_normalizer`, `rt_fuelSupplyScale` |
| e10FuelProperties | MEAN, `INSERT IGNORE` at group 0 | MonthGroupWeighting | `mag_groupShare` |
| AverageTankTemperature, SoakActivityFraction | `sum(x * actFract)`, not divided | MonthWeighting | refused (evaporative) |
| TotalIdleFraction | `sum(tif x actFract)`, not divided | MonthWeightingBySourceType | `mag_sourceSum` |
| IdleMonthAdjust | unweighted `avg` | -- | refused under any aggregation (§7.3.63) |

Nothing else in the Java branches on Year beyond those two sites; the fuel and
meteorology generators read the collapsed tables like every other generator.

**Measured before porting** (pandas; pre-YEAR state = `scale-county-timeagg-month`'s
execution database, the same county database, months, day types and source
types after PreAggDAY + PreAggMONTH; post = the Year capture's): MonthWeighting's
source type 62 and MonthGroupWeighting's 21 (the two orderings differ, and the
default `monthVMTFraction` is identical for every source type but 11, so only a
motorcycle run could tell); ZoneMonthHour temperature and humidity exact;
MonthGroupHour 1.2e-16 in double (3.5e-08 with the FLOAT intermediate, so it is
not modelled); e10FuelProperties 1.4e-16; TotalIdleFraction 30 of 30 at 1.4e-08;
FuelSupply exact against the DEFAULT database's rows -- `27001` is January +
April + October, 0.241904 -- and NOT against the Month run's execution database,
whose April and October gasoline is `29002`/`29003`, a later writer's
formulations (§ a-snapshot-table-is-its-last-writer).

**The capture** (moves.rs branch `capture-timeagg-year`, `fd3fd738`; host token
`1ccc0236`, moves-snapshot/v2; 145 MB):
`characterization/fixtures/scale-county-timeagg-year.xml` over the unchanged
`county-inputs/washtenaw-county-timeagg/setup-timeagg.sql`: SINGLE domain,
January, April, July and October 2020, both day types, all 24 hours, source
types 21, 32, 62, road types 1 and 4 (MOVES adds 2, 3, 5), THC, CO and NOx at
running, start, crankcase running/start/extended idle, extended idle and APU,
Total Energy and Atmospheric CO2 at running, and brake and tire wear PM10 and
PM2.5; `aggregateBy` Year, output Year. No evaporative or refueling process
(the parallel lane, §7.3.64). 18,071 output rows.

**What the model does** (conventions §117; hand-written, spliced into
`onroad/model.esm` by scratch scripts):

1. **The months a cell aggregates over are a relation**, `aggregationmonth_rows`
   (`db_aggregationmonth`). Its default lives in `onroad/default-database.esm` --
   every month of `MonthOfAnyYear` -- and a Year RunSpec overrides it with its
   XML's months (`tools/runspec-month-selection.py`; `<month key>` is 0-based),
   since the execution database has overwritten them with month 0. No existing
   RunSpec changed.
2. **Each month-keyed read joins the aggregation month** with a weight that is
   1 at the cell's own month and 0 elsewhere on every other run (`mag_isOwnMonth`,
   `mag_collects`): `run_temperature`, `run_relHumidity`, `act_timeVMTFraction`,
   `hot_roadDayVMT` (`mag_meanShare`); `run_acActivityTerm*`, eleven `ffx_*`,
   `atr_baseEmissions` (`mag_groupShare`); `ffsup_suppliedShare` and
   `cmx_suppliedRatio` (`mag_groupSum`); `oni_defaultIdleFraction` (`mag_sourceSum`).
   PreAggMONTH.sql's DayWeighting1 (`dw_*`) sums the collected months, because it
   ran over the RunSpec's months before PreAggYEAR.sql. The constant rows are
   `year_value_or_own` over the old lookups, renamed `*own*`.
3. **FuelSupply's sum scales every process.** At four months a fuel type's
   formulations sum to 0.334229, and BaseRateCalculator sums every rate over the
   formulations by `marketShare`. The first evaluation found every cell no
   share-weighted fuel ratio covers -- brake and tire wear, energy, diesel model
   years without a biodiesel ratio -- exactly 2.992 = 1/0.334229 high, and every
   covered one exact (finding **F63**). So at Year `ffsup_marketShare` is the share
   of its fuel type (`ffsup_normalizer`) and the total multiplies
   `rtDay_quantRated` once (`rt_fuelSupplyScale`). CarbonOxidationByFuelType
   multiplies two SUMS over the raw shares (`ffsup_suppliedShare`), so
   Atmospheric CO2 carries the total CUBED -- 8.952 = 0.334229^-2 high with both
   normalised (finding **F64**). A twelve-month Year run has a total of 1 and
   none of this shows.
4. **Brake and tire wear beside road type 1 are no longer refused** in the
   DEFAULT domain (`run_onRoadPollutantProcessCount`): this is the first capture
   to select them there, MOVES writes no road-type-1 row for either, the model
   writes none, and their 4,768 rows reproduce.

**What is refused now.** `run_aggregationUnported` counts, at `aggregateBy` Year,
every pollutant-process on a selected road that the capture does not check
(`run_yearUnportedSelected`: processes 1, 2, 9, 10, 15, 16, 17, 90, 91 and
pollutants 1, 2, 3, 90, 91, 106, 107, 116, 117; `year_captured_process`,
`year_captured_pollutant`). So Year + evaporative stays refused (twice: (4)
TankTemperatureGenerator under any aggregation, and AverageTankTemperature and
SoakActivityFraction are SUMMED, not averaged, by MonthWeighting), Year +
refueling is refused (its month-keyed fuel RVP and weather are uncaptured), and
Year + air toxics is refused (ATRatio's MonthGroupWeighting mean of per-group
ratios is not the ratio at the mean fuel). §7.3.63's refusals are unchanged.

**Unchanged runs.** The full suite in this worktree re-emitted every run, and all 365 CSVs `.fixtures-run/` shares with main's are byte-identical under `cmp` -- among them `expand-month`, `expand-fullyear`, `scale-county`, `scale-county-timeagg-day`, `scale-county-timeagg-month`, `scale-county-idle-adjust`, `userdb-hotelling-multiyear`, `process-brakewear`, `process-tirewear`, `process-apu`, `process-extended-idle`, `process-crankcase-start`, `process-crankcase-extidle`, `chain-so2-co2e-mechanism`, `rates-start` and `rates-hotelling`. Byte-identical by construction: on a run that does not aggregate by year every new weight is exactly 1 or 0, `ffsup_normalizer` and `rt_fuelSupplyScale` exactly 1. The Python binding loads the Year and Month runspecs. `./run-tests.sh`: 754 ok / 1 FAIL against main's 749 / 1; the FAIL is `document figures no longer match the corpus` (the shared moves.rs corpus has grown to 96 snapshot directories with the parallel lanes' captures and this one), and main's join.on timing flake passed this time. 3 h 58 min wall, 13,369 s user CPU, 12.1 GB peak, on a node running two other suites.

**Runtime.** `scale-county-timeagg-year` evaluates in 11 min (515 s user CPU) at 12.1 GB. The twelve-row
default aggregation-month axis is not free: re-evaluated alone, `scale-county-timeagg-day` took 531 s user CPU against §7.3.63's 470 and `-month` 767 against 667 (both under concurrent load, so an upper bound). Declaring `db_aggregationmonth` per RunSpec as its own `runspecmonth` would make the axis one row wide on every run, at the price of 75 edited documents.

#### 7.3.66 The 24-Hour Day and Portion of Week output steps, and the last three aggregation refusals

2026-11-12. §7.3.63 left the 24-Hour Day and Portion of Week `<outputtimestep>`s
unexpressed and unrefused, and `run_aggregationUnported` refusing hotelling at two
calendar years, off-network idle with the AdjustTotalIdleFraction.sql inputs, and
start, hotelling or off-network idle in a whole-week cell of a RunSpec selecting
fewer day types than the week. **All five now reproduce, eight captures, every key
set exact, no `cell_exception`:**

| run | `aggregateBy` / output | rows | worst cell | model change |
|---|---|---|---|---|
| `scale-county-outstep-hourday` | Hour / 24-Hour Day | 2188 of 2188 | 6.846e-06 | the slot level |
| `scale-county-outstep-week` | 24-Hour Day / Portion of Week | 8752 of 8752 | 1.049e-05 | the slot level, `x noOfRealDays` |
| `scale-county-outstep-dayagg` | 24-Hour Day / 24-Hour Day | 8752 of 8752 | 9.379e-06 | the slot level |
| `scale-county-idle-adjust-day` | 24-Hour Day / Month | 2032 of 2032 | 1.026e-05 | none |
| `scale-county-idle-adjust-month` | Month / Month | 2032 of 2032 | 1.287e-05 | idleDayAdjust's collapse |
| `scale-county-timeagg-weekday` | Month / Year, weekday only | 6288 of 6288 | 8.671e-06 | none |
| `userdb-hotelling-multiyear-day` | 24-Hour Day / Month, 2015 and 2020 | 3904 of 3904 | 1.067e-05 | the pooled chain over the collapsed tables |
| `userdb-hotelling-multiyear-month` | Month / Month, 2015 and 2020 | 3904 of 3904 | 1.287e-05 | that, and the earlier year's second rescale |

**The captures** (moves.rs branch `capture-timeagg-outputsteps`, host token
`1ccc0236`, moves-snapshot/v2; snapshots are not versioned and were copied into the
main checkout's `characterization/snapshots/`): the three `scale-county-outstep-*`
over `setup-timeagg.sql` -- January and July 2020, both day types, all 24 hours,
the gasoline car and diesel long-haul truck on road types 1 and 4, running, start
and extended idle; CO and NOx at `-week` and `-dayagg` (98 MB, 157 MB), and at
`-hourday` CO alone in July alone (65 MB): its 48 hour cells evaluate in 42 min at
33.5 GB, and the first two shapes captured for it -- the same 48 cells in two
months, with and without NOx -- were killed by the memory cgroup past 58 and 61 GB
(memory grows with the cells times the months, not with the pollutants; not
diagnosed further); `scale-county-idle-adjust-day/-month` over `setup-idle-adjust.sql` at
all 24 hours (65 MB, 64 MB); `scale-county-timeagg-weekday`, `scale-county-timeagg-month`
at the weekday alone (230 MB); `userdb-hotelling-multiyear-day/-month`,
`userdb-hotelling-multiyear` at all 24 hours under each aggregation (72 MB, 17 MB).

**What MOVES does.**

1. **The output step** (AggregationSQLGenerator.java:857-923, 1560-1602;
   OutputTimeStep.java:23-36). Each step is four flags. 24-Hour Day
   (`requiresAllHours`, `usesClassicalDay`) groups by `yearID, monthID, dayID` with
   `null as hourID` and converts each row to a classical day, `x 1/noOfRealDays`
   (convertDays, WeeksInMonthHelper.getPortionOfWeekPerDayClause) -- the division
   the output relation's cells already carry, so the slot is a plain sum. Portion
   of Week (`requiresAllHours`, not `usesClassicalDay`) groups the same way and
   converts NOTHING: each row is the day type's portion of a week. Measured in
   pandas between `-week` and `-dayagg`, the same RunSpec at the two steps: the
   ratio is 2.000000 on every weekend row and 5.000000 on every weekday row (7636
   nonzero rows, within the v2 storage). When `aggregateBy` equals the output step
   ExecutionRunSpec.doFinalAggregation (java:1893) skips the master's final
   aggregation, but the worker SQL still groups and converts (`-dayagg`). The GUI
   raises an output step finer than the aggregation to it (TimeSpans.java:746), so
   24-Hour Day under `aggregateBy` Month does not occur.
2. **Off-network idle's adjustments under aggregation.** PreAggDAY.sql does not
   touch the idle tables, and `scale-county-idle-adjust-day` reproduced with no
   change. PreAggMONTH.sql (lines 537-560) collapses totalIdleFraction by
   DayWeighting2Normalized and idleDayAdjust to `sum(idleDayAdjust x noOfRealDays/7)`
   over the rows PRESENT, before TAG runs AdjustTotalIdleFraction.sql, whose
   override is crossed with `runspecday` -- by then day 0 alone. A source type that
   states only the weekday gets `1.12 x 5/7 = 0.8` for the whole week, not 1.12 and
   not the identity on the weekend. Measured: the collapsed idleDayAdjust 1.02 and
   0.8 exactly, and the execution database's 10 totalIdleFraction rows at 1.1e-16.
3. **A partial week.** The input merge cuts startsPerDay, startsHourFraction,
   startsOpModeDistribution and the hotelling tables to the selected day type
   before PreAggMONTH.sql (`startsPerDay` 2.864e8 = `401e6 x 5/7`, hotellingHoursPerDay
   1857.1 = `2600 x 5/7`), and the model already scopes every collapse to the
   RunSpec's day types through `db_rateday` (`tools/runspec-day-selection.py`). It
   reproduced with no change.
4. **Hotelling at two years.** Under PreAggDAY.sql TAG's table holds one hour per
   day type and year (hour 0, the RunSpec's only hour after the pre-aggregation),
   so the pooled hour block of §7.3.61 is taken over the collapsed tables -- its
   default is 1 and the cell's collapsed hourFraction rescales by itself. Under
   PreAggMONTH.sql one more thing happens: AdjustHotelling.sql's
   hotellingHoursPerDay block adds a `dayID` column and fills it only `where yearID
   = targetYearID`, so 2015's rows keep the default `dayID 0` -- which is now the
   collapsed day, present in hotellingHoursPerDay -- and are rescaled a second time
   by 2015's own `hhpd / (sum(hours)/7) x numMonths` before 2020's hour, age and
   month blocks pool them. Without that, every 2020 extended-idle and APU cell was
   off by up to 20% (a month factor 1.015 / 0.984 and an age pattern).

**What the model does** (conventions §118; hand-edited, spliced by scratch scripts):

1. **The output step is four declared flags**, MOVES's own: `n_outputSumsHours`
   and `n_outputClassicalDay` beside §7.3.63's `n_outputSumsDays` and
   `n_outputSumsMonths`, relayed through every domain document. One coded property
   was tried first and does not compose: an index-set size is `+ - * /` over
   metaparameters, and "sums hours" over the codes Hour, Day, Portion of Week has
   no integer polynomial. `outputstep_rows`' cell level is the cells, the day types
   (`n_rateday`) or one (`output_step_cell_slots`, with `output_step_month_slots`
   in `lib/time_aggregation.esm`); `tcell_dayTypeSlot`, `tcell_outputSlot` and
   `tcell_slotFirstCell` say which slot a cell falls in and which cell stands for
   the slot -- the slot's FIRST cell, since `runspechourday` is hour-major;
   `outStepWeeks` is `noOfRealDays` at Portion of Week; `outStepHourID` is NULL once
   the hours are summed.
2. **idleDayAdjust in a whole-week cell** is the collapse over the RunSpec's day
   types (`oni_dayAdjustRows`, `oni_dayAdjustStated` through `tcell_dayMatch` and
   `tcell_dayWeekShare`); in a cell of its own day it is its own row, as before.
3. **The pooled hotelling chain over the collapsed tables**:
   `hot_pooledHourFactor`, `hot_pooledHourShare` and `hot_pooledDayShare` take the
   collapsed arm in a cell that collects hours and keep the hourly one as
   `*ByHour`; `hot_earlierRescale` (with `hot_yearCellHours`) is the earlier year's
   second hotellingHoursPerDay block in a whole-week cell, 1 everywhere else, and
   `hot_earlierRowHours` is what the three earlier-year sums read.
4. **`run_aggregationUnported` counts evaporative processes alone** (the
   timeagg-processes lane's). `run_offNetworkActivitySelected` and
   `run_idleAdjustmentRows`, read by nothing else, are deleted.

**The port discriminates.** Before it, the output steps could not be emitted at
all (the oracle has hourID NULL and one row per day type), the four refused runs
counted 20 or 22 in `run_selectionUnported`, and, read anyway:
`scale-county-idle-adjust-month` reproduced only once idleDayAdjust was collapsed
(the earlier join on the cell's day, 0, finds no row and applies the identity: 1.02
and 1.25 off by construction; not separately evaluated); `userdb-hotelling-multiyear-day` missed 122 2020 cells by up to
x1.9 (the hourly pooled chain finds no hour-0 rows); `-month` emitted ZERO for
every 2020 hotelling cell, and with the collapsed chain but without the second
rescale was off by up to 20%.

**Still refused** under aggregation: evaporative processes (the timeagg-processes
lane), and, through `hot_adjustmentRowsUnported`, a third calendar year. Not
captured, and expected right by construction: the idle adjustment tables over a
partial week (idleDayAdjust's collapse is scoped to `db_rateday`, as starts are),
and Portion of Week under `aggregateBy` Hour (the hour sum of `-hourday` times the
factor of `-week`).

**Unchanged runs.** Re-emitted with `tools/emit-oracle-table.py` on the final model and `cmp`'d
against the main tree's `.fixtures-run/`, every relation, shape and table
byte-identical: `scale-county-timeagg-day`, `scale-county-timeagg-month`,
`expand-month`, `expand-fullyear`, `expand-multiyear`, `expand-roadtypes`,
`expand-day`, `scale-county`, `scale-county-idle-adjust`,
`userdb-hotelling-multiyear`, `process-extended-idle[-single]`,
`process-apu[-single]`, `process-crankcase-start[-single]`,
`process-crankcase-extidle[-single]`, `process-evap-fvv-day`, `project-hotelling`,
`rates-start`, `rates-hotelling` and `rates-hotelling-sourcetypes` (all eight Rates
tables each). The Python binding loads all eight new runspecs.

**Cost.** Seven of the eight new runs evaluate in 3.5-5 min at 3.2-4.3 GB,
`scale-county-timeagg-weekday` in 14.5 min at 7.8 GB, and `scale-county-outstep-hourday`
in 41 min 50 s (2396 s user CPU) at 33.5 GB, the heaviest run in the suite: an
hourly inventory of every hour is 48 cells a month, and the two-month shape did not
fit in memory beside the other lanes' runs. `./run-tests.sh` in this worktree: 782 ok / 1 FAIL against main's 749 / 1 -- 32
new `ok` (the eight runs' validate, test, number and shape lines), main's join.on
timing flake passed this time, and the one FAIL is `document figures vs the
corpus`: `tools/check-reachability-counts.py` counts the SHARED snapshot corpus,
which now holds this lane's eight new snapshots and the other two lanes' three (96
directories against the 85 docs/omd-generator-reachability.md states), so the note
is refreshed once, after the lanes merge. 4 h 51 min wall, 16,593 s user CPU, 33.5 GB
peak (`scale-county-outstep-hourday`), with the two other lanes' suites on the node.

#### 7.3.68 Year + the evaporative processes and refueling: what PreAggYEAR.sql sums, and who reads the sum

2026-11-12. §7.3.65 refused every evaporative and refueling process at `aggregateBy`
Year, for two stated reasons: PreAggYEAR.sql SUMS AverageTankTemperature and
SoakActivityFraction over the months instead of averaging them, and refueling's
month-keyed fuel RVP and weather were uncaptured. One capture now checks both.
**`scale-county-timeagg-processes-year` reproduces: 19628 of 19628 rows, key set
exact, worst cell 1.134e-05, per-pollutant sum 9.2e-07, no `cell_exception`,
`run_selectionUnported` 0.**

**What MOVES does, and in which order.** InputDataManager.preAggregateExecutionDB
(InputDataManager.java:2646-2730) runs PreAggDAY.sql, PreAggMONTH.sql and
PreAggYEAR.sql after the input merge and BEFORE `performInstantiation`, so before
TankTemperatureGenerator and every other generator (§7.3.64, §7.3.65):

1. **PreAggYEAR.sql's AverageTankTemperature and SoakActivityFraction sections sum
   empty tables.** It does write `sum(x * actFract)` over MonthWeighting, undivided
   (PreAggYEAR.sql, the `OldAverageTankTemperature` / `OldSoakActivityFraction`
   blocks) -- but both tables are filled by TankTemperatureGenerator, which has not
   run. They hold rows only when the USER states them, which is refusal (1) of
   `run_aggregationUnported` (`run_soakActivityInputRows`, the agg-soak lane).
   TTG then runs over the month-0 ZoneMonthHour exactly as at Month: no cold-soak
   tank temperature (one hour-0 row has no neighbour hour), so no
   AverageTankTemperature and no permeation row, and SoakActivityFraction mode 151
   at exactly 1 -- the execution database holds three rows, one per source type, at
   month 0, every one 1.
2. **What the month collapse DOES reach is FuelSupply**, whose `(1 - fractDontHave)
   x haveFract` is a SUM of the four months' shares (0.334229 per fuel type;
   §7.3.65). Three readers on the evaporative and refueling path read that sum
   as a sum:
   - TankFuelGenerator TFG-1c's `gasoholMarketShare = sum(marketShare)` over the
     formulations with 4 <= ETOHVolume <= 20 (TankFuelGenerator.java:334-355) --
     0.334229 for gasoline AND E85 (this region's E85 formulations, 27001/27002, carry
     ETOHVolume 10) -- puts TFG-3a's commingling factor in its `>= 0.3` bin, 1.035,
     where any run whose shares sum to one has 1.000. Its means (`linearAverageRVP`,
     `tankAverageETOHVolume`, `averageGasPortionRVP`) divide by `sum(marketShare)`
     and see no difference.
   - RefuelingLossCalculator.sql's REFEC-2 `averageRVP = sum(rvp x marketShare)`
     (:345-347): 3.447 for gasoline, not the mean 10.31 -- a lower displaced-vapor
     exponent.
   - Its `RefuelingFuelType` extract's `energyContent = sum(marketShare x
     energyContent)` (:176-195): 0.334 of the mean, dividing the loss.
3. **Venting and leaks read no market share at all.** MultidayTankVaporVentingCalculator.sql
   reads the fuel only through AverageTankGasoline (the TFG output, by fuel type),
   and LiquidLeakingCalculator.sql not at all; neither is BaseRateCalculator. So the
   0.334 that §7.3.65 found multiplying every BaseRateCalculator process does NOT
   multiply them. (EvaporativePermeationCalculator.sql does sum,
   `SUM(marketShare x fuelAdjustment)` (:535), but writes no row here.)
4. Weather, SourceHours, SHO and the soak shares are §7.3.64's chain over the
   month-0 cell, with ZoneMonthHour the MonthWeighting mean (§7.3.65); the output
   step is §7.3.65's Year sum.

**Measured before porting** (pandas, the Year execution database against the
`-processes-month` one): FuelSupply's month-group-0 rows sum to 0.334229 per fuel
type; the gasohol share is 0.334229 for fuel types 1 and 5 and 0 for the others;
`sum(rvp x marketShare)` is 3.446685 (gasoline) and 3.250895 (E85), means 10.312 and
9.727; AverageTankTemperature and ColdSoakTankTemperature 0 rows, SoakActivityFraction
3 rows of 1 at month 0. The venting RVP adjustment (`evapRVPTemperatureAdjustment`,
process 12) has knots at RVP 7, 8, 9 and 10 and is clamped above 10: gasoline's tank
RVP is above 10 under either commingling factor, E85's crosses it (9.727 x 1.035).
Then the first evaluation, before any edit, against the capture: key set exact, every
non-evaporative cell exact, and

| process | fuel | model / MOVES | cause |
|---|---|---|---|
| venting; leaks | gasoline; gasoline and E85 | 0.334229, uniform | `rt_fuelSupplyScale` applied where the calculator reads no share (finding **F67**) |
| venting | E85 | 0.330158 = 0.334229 x 0.98782 | the commingling factor 1.000 instead of 1.035 (finding **F68**) |
| refueling spillage | all | 0.334229 | `energyContent` a mean, not the sum (F68) |
| refueling displacement | gasoline, E85 | 0.334 to 0.691 | the same, times `exp(vaporTermD x (RVP mean - sum))` above the minimum-loss floor (F68) |

**What the model does** (conventions §120; hand-written edits to existing equations):

1. `tfg_weight`, `rff_averageRVP` and `rff_energyContent` read `ffsup_suppliedShare`,
   the share as the execution database holds it, instead of `ffsup_marketShare`, the
   share of its fuel type. On a run that does not aggregate by year the two are the
   same number (`ffsup_normalizer` is exactly 1).
2. `rt_fuelSupplyScale` is 1 at Year for a process whose calculator reads no market
   share (`fuel_supply_summing_process` in lib/time_aggregation.esm: venting 12 and
   leaks 13).
3. `year_captured_process` adds 11, 12, 13, 18 and 19; permeation is checked as the
   empty output MOVES writes.

The second evaluation, with all three, reproduces every cell. The fixes do not mask one
another: the scale is the only cause on gasoline venting and on leaks, the gasohol
share the only further one on E85 venting (gasoline's RVP is clamped either way),
and the two refueling sums act only on processes 18 and 19.

**What is refused now.** `run_aggregationUnported` no longer counts the evaporative
processes or refueling at Year. Still counted: (1) a STATED soakActivityFraction
under any aggregation -- at Year PreAggYEAR.sql's undivided MonthWeighting sum would
act on it, and on a stated AverageTankTemperature too; (2) Year + air toxics and the
other uncaptured pollutants (the year-toxics lane); (3) §7.3.66's three
configurations at Year (the year-configs lane). Not counted and not reachable from
any capture: Year + permeation with a stated AverageTankTemperature, where
EvaporativePermeationCalculator.sql's `SUM(marketShare x fuelAdjustment)` would carry
the 0.334 as BaseRateCalculator's does (`fuel_supply_summing_process` keeps 11
scaled for that reason).

**The capture** (moves.rs branch `capture-year-evap`; host token `1ccc0236`,
moves-snapshot/v2, capture binary rebuilt first; 257 MB):
`characterization/fixtures/scale-county-timeagg-processes-year.xml` --
`-processes-month`'s selections (THC, CO, NOx at running, start, extended idle and the
three crankcase processes; Total Energy at running; THC at permeation, venting, leaks,
refueling displacement and spillage; brake and tire wear PM10 and PM2.5), gasoline
car and light truck and diesel long-haul truck, road types 1 and 4, January, April,
July and October 2020, both day types, all hours -- at `aggregateBy` Year, output
Year, over the unchanged `washtenaw-county-timeagg/setup-timeagg.sql`. MOVES ran in
about two minutes; 19,628 output rows.

**Runtime.** `scale-county-timeagg-processes-year` evaluates in 10 min 24 s
(547 s user CPU) at 13.3 GB peak RSS.

**Unchanged runs.** Re-emitted on the final model with `tools/emit-oracle-table.py`
and `cmp`'d against the main tree's `.fixtures-run/` (refreshed by main's suite the
same evening): `process-evap-permeation`, `-leaks`, `-fvv`, `-fvv-day`,
`process-refueling`, `rates-evap`, `rates-venting` (and their six Rates tables),
`project-refueling`, `rates-project-evap`, `expand-month`, `expand-fullyear`,
`scale-county`, `scale-county-timeagg-day`, `-month`, `-year`, `-processes-day` and
`-processes-month`: 17 runs, 66 files -- every relation, oracle table and shape file
byte-identical. By construction: off Year `ffsup_suppliedShare` and
`ffsup_marketShare` are the same number, and `rt_fuelSupplyScale`'s Year arm is not
taken; `scale-county-timeagg-year` selects neither venting nor leaks. The Python
binding (EarthSciAST `main` 0ea122b7d) loads the new runspec; all 97 runspecs and
fixtures validate; `tools/check-sources.py` passes. `tools/check-reachability-counts.py`
reports the shared corpus's figures moved (24 of 129 claims), as every lane's new
snapshots move them; the document is re-derived once the lanes merge.

### 7.4 Upstream asks

**None is blocking.** This section has said "still none", "already exists,
spelled `bindings`" and "F50" in turn, each right when written. F50 — bind a
discovered `extent` in the scope that declares it — was filed as EarthSciAST
#301 on 2026-09-12 and fixed by PR #317, merged 2026-09-14, and it bought what
it was priced at: a per-fixture document of 43 lines instead of 270 — and 12
once PR #353 took the enum union with F13 (§7.1, conventions §53.2).

**Landed since Phase 7 began:** PR #297 (`mi`, `lb`, `hp`, `gal`; retired F44),
PR #298 (the §4.7 edge pipeline at a top-level `{ref}`; retired F46, F48, F49),
PR #317 (retired F50), and PR #299 (`aggregate` → `faq` at `esm 1.1.0`), which
was not an ask and cost one mechanical commit (§7.3.2). The #299 behaviour that
forced it — the deprecated alias refused inside a 1.0.0-rooted assembly — is
recorded there and was not filed.

**In flight, and what each changes here when it lands:**

* ~~#339 + #347~~ — **merged 2026-09-15** and adopted here: exact unit scales,
  and a declared unit on a `const` at `esm 1.2.0`. Between them they fix **#302**
  — a multiplicative literal disabled an equation's dimensional check, so 37 of
  61 wrong declarations validated clean. Four annotation passes followed (§57,
  §58): 340 declarations are swept now against 71 before, and every fixture
  declaration is caught if it is wrong. **#303** (`esm units` is a stub) has no
  PR yet, and it is the instrument the passes were read with. Over the 69
  model documents it reports 367 equations consistent at a non-dimensionless
  unit, and 2556 of 5691 still NOT CHECKED — 1006 because the left-hand side
  declares no units (the typing pass that has not been done), 1272 because the
  right-hand side node is undeterminable (903 `faq`, 311 `const`, 58
  `makearray`), and 276 for an indeterminate operand. The `faq` share is where
  #414 bites: an aggregate is undeterminable when its operands are, which is
  what a mount edge and an unchecked `filter` produce.
* ~~#341 + #353~~ — **merged 2026-09-15**, retiring F3 and F13. The enum
  restatements are deleted — 16 enums in `runs/mixed_onroad_run.esm`, 11 in
  `runs/evap_leaks_run.esm`, 6 in each 7c document — and the per-fixture
  document is 12 lines.
* ~~#352, #342, #343, #345~~ — **all merged**, retiring F14, F5, F20 and F21.
  #338 and #346 landed too, and F28 and F22 stay open: each was answered with a
  better diagnostic or an explicit refusal rather than with the capability. F14
  turned out not to be a defect at all — PR #352 settled the ragged SPELLING and
  this port's repro had it wrong.

**Status re-checked 2026-11-02: every ask below but #441 and #536 is closed.** #536 was closed as not planned on 2026-11-09: its fix, a `cast` op (PR #674), was declined, and the three `cell_exception`s it would have retired stay.
#303 closed 2026-09-16; #409 by PR #413 and #418 by PR #420, both 2026-09-19;
#414 by PR #508 on 2026-10-17, which checks units across a mount edge, through
array operators and at constant exponents -- and `./esm` (`esm-version.lock`,
EarthSciAST `040952d1`) contains it. The sweep re-run over the 52 model
documents in `components/`, `lib/`, `onroad/`, `nonroad/` and `runs/` reports
**0 mismatched**, 2,058 consistent and 1,977 not checked: 712 because the
left-hand side declares no units (the typing pass not done), 1,071 because a
right-hand node is undeterminable (517 `const`, 500 `faq`, 54 `makearray`), and
194 for an indeterminate operand. The paragraphs below are the record as filed.

**Filed by the units passes, both open when filed:**

* **#409** — transcendentals and trig ignore a unit's SCALE (`sin(90 deg)`
  evaluates `sin(90 rad)`; `log(x ppm)` is accepted unchecked). Finding F52.
  **PR #413** proposes the fix: convert for angles, refuse for
  dimensionless-but-scaled.
* **#414** — unit checking is silently skipped across a `{ref}` mount edge
  (F54), inside a `faq`'s `filter` (F55), and on a bare `var` operand (F53).
  All three are "undeterminable", which is reported as nothing. **#414 is what
  the `runs/` declarations are waiting on**: they are written and correct and
  check nothing until it lands, which is why the sweep reports them silent.
* **#418** — a join-gated `faq` retains ~80 bytes per candidate pair and ~78
  per fact-table row, in a thread-local cache with no eviction, so peak memory
  tracks the join's MATCH SET rather than the arrays a document declares or the
  answer it produces. Finding F58, filed 2026-09-18 with a four-metaparameter
  MWE (`docs/findings/F58_a_join_gate_retains_its_match_set.esm`). **This is
  the one ask that currently blocks a RunSpec**: `expand-sourcetype` declares
  0.31 GiB of arrays and is killed at 32 GB. **PR #420 fixes it** and was
  measured downstream on 2026-09-19: 3x the memory and 3-4x the wall clock on
  this model, answers byte-identical — and `expand-sourcetype` still does not
  fit, reaching 38.67 GB and holding flat there before the kill. §7.3.7 has
  both measurements and the RSS timelines.

**Recorded but not filed: F51**, a Rust/Python disagreement about a shape-open
leaf. #317 changed the Rust side; the Python side is not being measured now.
This repository writes `leaf-owns-shape`, which does not depend on the answer.

### 7.5 Sequence

| step | deliverable | gate |
|---|---|---|
| **7a** ✅ | The spike: one ref'd, data-fed model evaluating end to end against a real table — **GO, 2026-09-10**; re-shaped to `leaf-owns-shape` 2026-09-12 with §7.3.2 | met; three corrections folded into §7.1–§7.3 |
| **7b** ✅ | Full-database monolithic conversion — **done 2026-09-10**: 237 monolithic + 3 schema-only, 0 partition directories, 517 MB, 15.6 s, validator extended and all 7 planted corruptions red (§7.3.1) | met; the load cost is measured and does not dictate the layout |
| **7c** ✅ | The mount shape at fixture scale — **done 2026-09-10, re-shaped to conform 2026-09-12, thin 2026-09-15** (§7.3.2): `fixtures/process-tirewear.esm` split into a logic half, a catalogue document that mounts it, and a 43-line per-fixture document that mounts the catalogue, byte-identical over 375 rows × 26 fields. Four findings retired (F46, F48, F49, F50), one open (F51) | met; the per-fixture document is 12 lines — metadata and one `{ref}`, nothing mechanical (conventions §53.2) |
| **7c′** ✅ | `moves-onroad.esm`: default DB → `MOVESOutput` for `process-tirewear` — **done 2026-09-17** (§7.3.3): 38 national tables and the same logic, behind a per-fixture document carrying ten runspec selections, emitting the inlined fixture's 375 rows byte for byte in 40 s | met; the first end-to-end number comes off the default database |
| **7d** | Widen the runspec surface one selection dimension at a time — pollutant-process, source type, road type, timespan, geography | each dimension added only with a fixture that **discriminates** it (§23). **Begun 2026-09-17** (§7.3.4): **timespan** done at the day axis, the output relation is no longer a rectangle over the selected pollutant-processes (`runspecs/expand-day.esm`, 250 rows, byte-identical to the inlined fixture over 25 shared fields), and **geography** done at three counties in three states (`runspecs/expand-counties.esm`, 375 rows, worst cell 1.140e-05; conventions §61). **Source type is an axis as of 2026-09-18** (§7.3.5, conventions §62): 44 variables promoted, `run_sourceTypeID` gone, the three existing runs unchanged to the digit, and `runspecs/pending/expand-fueltype-diesel.esm` emitting the right 248-row shape with source type 21's 125 rows exact at 7.106e-06. **The source bin is its own relation as of 2026-09-18** (§7.3.6, conventions §63): `sourcebin_rows` beside `cohort_rows`, `n_sourceBin` a third declared and checked number relayed per fixture, the three existing runs still unchanged to the digit, and `expand-fueltype-diesel`'s activity AND source-bin distribution both exact for both source types — 330 bins against the run's own `sourceBinDistributionFuelUsage`. **The drive cycle is per VEHICLE as of 2026-09-18** (§7.3.7, conventions §64): `physicsrow_rows` is the run's selected `sourceusetypephysics` rows densely ranked, `n_physicsRow` a fourth declared and checked number, the three existing runs STILL unchanged to the digit, and **`runspecs/expand-fueltype-diesel.esm` promoted out of `pending/`** — all 248 rows, worst cell 7.372e-06, both regulatory classes of source type 32 and the split at model year 2010. **`runspecs/expand-sourcetype.esm` reproduces as of 2026-09-20** (§7.3.8, §7.3.9): the 40 GB kill was EarthSciAST#418 and was fixed upstream by PRs #420 and #423 — the run went from killed at 32 GB to 0.89 GB and 91 s — and the three cells left after that were `emissionRateAdjustment`, a table the model did not read, ported as J56. All 430 rows, worst cell 9.017e-06. **`runspecs/pending/` is empty.** **The month is an axis as of 2026-09-20** (§7.3.10, conventions §65): 26 variables promoted, `run_monthID` no longer a `run_rows` scalar, the output relation five levels, and all FIVE existing runs unchanged to the digit. **`runspecs/expand-month.esm` reproduces as of 2026-09-20** (§7.3.11, §7.3.12, conventions §66): `aggregateBy = Month` is three more lists a RunSpec declares and a model that reads its speed distribution and its meteorology as weighted means over TIME CELLS, not a second mode — 500 of 500 rows, worst cell 8.513e-06, reproduced on the first run because both pre-aggregation weights were measured before the port. **`runspecs/expand-criteria.esm` reproduces as of 2026-09-20** (§7.3.14, §7.3.15, conventions §68, §69): `criteriaRatio` is EMPTY in the default database and MOVES computes its 4,398 rows at run time TWO WAYS — a closed form the database ships as SQL text, and the live EPA Complex Model plus the sulfur model — 372 of 372 rows, worst cell 7.805e-06, and with it the rule that a cohort or a pollutant-process with no rate is not emitted. **`runspecs/process-brakewear.esm` reproduces as of 2026-09-20** (§7.3.16) and cost NO model change: 375 of 375 rows, worst cell 8.251e-06, and it is the first run here whose model-year group is not `Doesn't Matter`. **`runspecs/process-nox-speciation.esm` and `runspecs/process-crankcase-running.esm` reproduce as of 2026-09-20** (§7.3.17, conventions §70): the output relation stops being a RECTANGLE. A chained block is as wide as its ratio table's coverage and no ratio table has an electricity row, so the species and crankcase blocks are 104 cohorts where their parents are 124; `n_outputRate`, one declared number ranked over (pollutant-process, cohort) pairs, replaces the two that could only describe a product. 436 of 436 at 9.485e-06 and 684 of 684 at 7.805e-06, both reproduced in pandas before the port and both right on the document's first run, with all eight earlier RunSpecs unchanged to the digit. **The chain became a FIXED POINT as of 2026-09-20** (§7.3.18, conventions §71): `rtDay_quantChained` read the parent's DIRECT quantity, which is right for every chain in `runspecs/` and gives a grandchild ZERO — and the hydrocarbon species are nothing but grandchildren, THC to NMHC to NMOG to TOG. Three value passes and four presence passes, three being the longest chain in the whole snapshot corpus, counted; `run_chainDepthExceeded` is the run's own check that a fourth would add nothing, asserted at 0, and all ten RunSpecs unchanged to the digit. ****`runspecs/chain-tog-speciation.esm` and `runspecs/chain-nonhaptog.esm` reproduce as of 2026-09-20** (§7.3.20, conventions §72): the hydrocarbon species, 540 of 540 rows each at 7.564e-06, both right on the document's first run. A ratio table keyed by the fuel SUBTYPE, a chained pollutant-process with TWO parents, and a species computed from a tally MOVES never reports -- and one runtime mistake, seven copies of a lookup spine over a 105,651-row table, which took `expand-day` from 60 seconds to 564 and now leaves it at 34. **`runspecs/process-airtoxics.esm` reproduces as of 2026-09-21** (§7.3.21, conventions §73, §74): the first RunSpec here that needs a table the default database ships EMPTY -- `ATRatio`, which MOVES writes at run time from two different computations, three closed-form expressions `docs/fuel-effects-generator.md` §8.1 had recorded as checkable by nobody and a COMPLEX MODEL at a fourth calculation engine. 644 of 644 rows at 7.564e-06, measured in pandas from the default database first. It found a constant that was a key (the complex model's reference model-year group, invisible to all three criteria configurations because they agree), a centring that only shows up in a NONLINEAR term (three answers 7.4 % high through one shared denominator), and a `filter` that is silently IGNORED once its aggregate has two output indices (EarthSciML/EarthSciAST#441), which `run-tests.sh` now lints for. **Thirteen RunSpecs in `runspecs/`.** **`runspecs/pending/chain-so2-co2e-mechanism.esm` is the measurement of what is left** (§7.3.22, 2026-09-21): every one of the 1,294 rows this chain emits for that run is RIGHT at 8.201e-06 and the whole of the gap to its 2,767 is ABSENCE, in five pieces -- `SO2Calculator`, `CO2AE` and its addition of three different parents by global warming potential, `TOGSpeciation`'s clamped subtraction of a species set, two more air-toxics ratio paths, and three toxics thought to need only DATA in the two relations §7.3.21 built. The energy root it was thought to need is already here: Total Energy and N2O reproduce exactly, and eleven of the twenty-six pollutants are complete before that rung is written. **The fifth of those five pieces is closed as of 2026-09-21** (§7.3.23, conventions §73.5), and it was NOT data: ethanol's model-year-2000-and-earlier ratio is a SEVENTH algebraic form -- a step in the ethanol volume, which `docs/fuel-effects-generator.md` §2.1's census had silently absorbed into the sulfur switch because MariaDB does not care about case -- and acetaldehyde's complex model reads two fuel properties the shared relation did not carry, which showed up as a FLAT 2.386 on the 21 model years the complex half covers and on nothing else. 1,294 → **1,477 rows, worst cell 8.201e-06 unmoved**, thirteen RunSpecs unchanged to the digit, and fourteen of the twenty-six pollutants now complete. What is left after the remaining four pieces is `process-pm-exhaust`, **measured as of 2026-09-22** (§7.3.24): its cycle is MOVES's declaration and not its arithmetic, the machinery exists in `fixtures/process-pm-exhaust.esm`, and of the 456 rows the chain emits 37 are right -- EC lacked the base-rate `generalFuelRatio` by exactly its value, and the crankcase path wrongly claimed sulfate and water. **All three causes fixed the same day, and `runspecs/process-pm-exhaust.esm` reproduces: 728 of 728 at 7.516e-06, on the port's first run** -- `SulfatePMCalculator` as a four-species share matrix, which needs no cycle (conventions §76). **Fourteen RunSpecs in `runspecs/`.** **`runspecs/chain-so2-co2e-mechanism.esm` reproduces as of 2026-09-22** (§7.3.25, conventions §77, §78): all 2,767 rows at 8.201e-06, the four remaining pieces each reproduced in pandas first. SO2 found that MOVES chains in kilojoules and this chain in reported units, and CO2AE found that not every chain edge is in `runspecchainedto`; both became a weight on one unioned edge relation. **Fifteen RunSpecs in `runspecs/`, `pending/` empty.** **`runspecs/chain-so2-co2e-mechanism-control.esm` reproduces as of 2026-09-22** (§7.3.26): all 2,309 rows at 8.201e-06 on its first run, at no model cost. It is the twin with five pollutants DESELECTED, MOVES's own two answers are bit-identical on every shared row, and so it tests GATING and not arithmetic -- the declared CO2AE edge list, which is present in every run, and the mechanism switch, which `chain-nonhaptog` exercises from the other side. **Sixteen RunSpecs in `runspecs/`.** What is left of the onroad corpus is the four evaporative and refueling runs (`process-evap-permeation`, `-leaks`, `-fvv`, `process-refueling`, all with snapshot-path fixtures), `mixed-onroad` and `scale-project` -- and the evaporative four are **measured as of 2026-09-22** (§7.3.27). `onroad/model.esm` has no evaporative machinery at all, and all four outputs of `TankTemperatureGenerator` are EMPTY nationally -- 2,645 lines of Java in seven steps, and the largest thing left in the onroad corpus. **`process-evap-leaks` needs none of it**, which is why `docs/evap-leaks.md` §0.3 chose that run: MOVES's own `opModeDistributionTemp` for it is 150→0, 151→0, 300→1, so the soak modes enter at weight exactly zero and an empty `soakActivityFraction` costs the run nothing -- provided the document COMPUTES that weight rather than assuming it (conventions §18.2). What it needs instead is relational and familiar: the evap op-mode distribution, the `IMCoverage` lift, the op-mode-weighted base rate and `SourceHours`. Permeation and FVV cannot dodge the thermal chain, and it is priced: two of `soakActivityFraction`'s three terms come off the national tables exactly (49,260 and 1,446 minutes) and the third, 1,058 hot-soak minutes, is a minute-by-minute recurrence -- 4,913 without its cutoff. The format already holds a recurrence (conventions §19, `agedist.f`), so this is not an upstream ask; it would be the first one on the ONROAD side. **`runspecs/process-evap-leaks.esm` reproduces as of 2026-09-22** (§7.3.28, conventions §80): all 64 rows at 7.294e-06 on the document's first run, the same worst cell an independent pandas reproduction from the national tables had reached before the model changed. It is the first EVAPORATIVE run here and it cost 21 variables and 13 equations, because `pp_W` gained an ALTERNATIVE and not a term: the evaporative operating-mode distribution comes from a different generator, over soaking and running rather than over speed bins, and `SHO / noOfRealDays` was already the inventory calculator's activity. The I/M lift turned out not to be work at all -- `IMCoverage` is 2,024,874 national rows that narrow to ZERO for county 26161 -- and `soakActivityFraction` is mounted although it has no rows, because an aggregate over an empty relation is the additive identity and the alternative is moving the statement out of the database and into the document. It is also the first run whose INTERMEDIATE row set diverges where its numbers do not: MOVES's `opModeDistribution` has three rows to this chain's one, and the two missing ones carry exactly 0. **Seventeen RunSpecs in `runspecs/`.** `process-refueling` is **measured as of 2026-09-22** (§7.3.29) and the measurement came back empty-handed in the best way: the national default database reproduces all 168 of its rows at 6.981e-06 already, identical to the execution-database reproduction at every cell. Five tables need mounting -- `refuelingControlTechnology` (189,379 national rows narrowing to exactly the 9,102 the execution copy held), `countyYear`, `sourceTypeTechAdjustment`, `refuelingFactors` and `fuelType` -- and the model work is `components/refueling_loss_rate.esm`'s 32 variables over REFEC-1..8, with all eight of its shapes already factored in `lib/refueling.esm`. It needs nothing from `TankTemperatureGenerator`, which the evaporative pair cannot say. **`runspecs/process-refueling.esm` reproduces as of 2026-09-22** (§7.3.30, conventions §81, §82): all 168 rows at 6.981e-06, the same worst cell the pandas reproduction had reached. The calculator went in as priced -- REFEC-1 and REFEC-2 checked against the specification's own 3.0152931048711182 and 2.8986555933440346 before anything downstream was written, and the 189,379-row control-technology lookup put on the BIN rather than the rate row for a spine seven times smaller. What was NOT priced was that two gates had been right by coincidence for seventeen runs. `occursOnRealRoads` says where `BaseRateGenerator` WRITES a process's rates, not where its rows appear, and refueling has no rate rows at all, so its rows take their parent's road type. And a chain PREREQUISITE is not a selection: `runspecpollutantprocess` carries seven pollutant-processes and MOVES emits two, because `flagRequiredPollutantProcesses` added three energy ones and the output processor strips what it added -- the first time the execution database is not enough, recoverable only because the needs table is refueling-only. The failure before it was understood was 125 energy rows and 43 with summed key columns, caught by the comparator's key check and by nothing else. **Eighteen RunSpecs in `runspecs/`.** `process-evap-permeation` is **measured as of 2026-09-22** (§7.3.31): the national default database reproduces all 64 rows at 5.630e-06 with every tank temperature COMPUTED, and `TankTemperatureGenerator`'s TTG-2 to TTG-5 are one lag-1 recurrence over `SampleVehicleTrip`'s rows with closed forms inside each trip -- the soak's early stop is a single threshold on the trip's key-off temperature. Probed on the ingest path at 1.7 s, bit-identical. **`runspecs/process-evap-permeation.esm` reproduces as of 2026-09-22** (§7.3.32, conventions §83, §84): all 64 rows at 5.630e-06, the tank temperature COMPUTED by `TankTemperatureGenerator` TTG-1 to TTG-5 in the model -- one recurrence over the national trips, 595,456 cells matching an independent walk -- and two keys fixed on the way: the source bin's regulatory class is 0 for a process whose `isRegClassReqd` is 'N', and `temperatureAdjustment`'s permeation rows are not S15's quadratic. Five other runspecs byte-identical. **Nineteen RunSpecs in `runspecs/`.** **`runspecs/process-evap-fvv.esm` reproduces as of 2026-09-22** (§7.3.33, conventions §85): all 64 rows at 7.517e-06 on the model's first run. The operating insert of TVV-8 went in -- `TankFuelGenerator`'s tank RVP, which the default database ships empty, and `evapRVPTemperatureAdjustment` interpolated at it as a weight per knot -- and the cold-soak insert did not: it is weighted by a computed exactly-zero on an on-network link, and the shape check's `run_offNetworkLinkCount` makes its absence fail loudly the day a RunSpec could weight it. **Twenty RunSpecs in `runspecs/`, and the onroad corpus is ported except `scale-project` (step 7f).** **`expand-fullyear` and `expand-counties-large` reproduce as of 2026-10-20** (§7.3.43, conventions §96): 1375 and 875 rows at 1.056e-05 and 1.140e-05, first runs, no model change -- eleven months because `<month key>` 12 indexes past the list, seven counties in seven fuel regions. **`expand-roadtypes` is pending and priced**: a road-type axis (284 of 1517 variables in the forward closure, 165 genuinely) and off-network idle, whose SHO formula reproduces the snapshot. **The road type is an axis as of 2026-10-21** (§7.3.46, conventions §101, §102): the rate relation's block is a (pollutant-process, road type) pair, the VMT-to-SHO chain carries the road type as a trailing axis, and off-network idle is a sum across it -- **`expand-roadtypes` 729 of 729 at 1.009e-05 on the first run**, the 33 earlier RunSpecs byte-identical. **Rates scale as of 2026-10-21** (§7.3.47, conventions §103, §104): `<modelscale>` is a RunSpec declaration (`n_ratesScale`) and its oracle is RatePerDistance, a second output relation over the first with the 16 speed bins as links -- **`scale-rates` and `rates-minimal` 2000 of 2000 at 1.163e-05 on the first run**, the 35 earlier RunSpecs byte-identical. **`runspecs/pending/` is empty.** **The rest of Rates scale as of 2026-11-01** (§7.3.48, conventions §107): five new captures, each a Rates twin of runs above, and every table MOVES writes but RatePerProfile is a membership-flagged relation of the model -- chained pollutants per bin, off-network idle per idle hour, RatePerStart, RatePerHour per hour of the hotelling mode, RatePerVehicle over the zone's population, StartsPerVehicle -- **`rates-wear`, `rates-running`, `rates-start` and `rates-hotelling` reproduce every table, key-exact**, the 37 earlier RunSpecs byte-identical. **`rates-evap` reproduces** (part C): its off-network RatePerVehicle 296 of 296 and its vapor-venting RatePerProfile 64 of 64, the cold soak a computed zero in a one-hour run; **`rates-project` reproduces** (part D, PROJECT domain, recaptured with a literal execution-database name). **`runspecs/pending/` is empty.** **Sulfate PM and the non-HAP TOG residual per speed bin as of 2026-11-02** (part E): `rates-pm`, `rates-nonhaptog` and `rates-mechanism` reproduce every table on the first run, and `run_ratesUnported` counts time aggregation alone. **Hotelling for other source types as of 2026-11-02** (part F): `rates-hotelling-sourcetypes` reproduces every table once a hotelling bin of a source type other than 62 is ABSENT rather than zero-weighted. **The hour is part of the output cell as of 2026-11-02** (§7.3.49, conventions §108): `runspecday_rows` is the (day type, hour) cell, and MultidayTankVaporVentingCalculator's cold-soak insert is ported -- **`rates-venting` and `process-evap-fvv-day`, every hour of both day types, reproduce**, one stored-FLOAT cell each held to 5e-5. **The heat-index suppression is per source type as of 2026-11-02** (§7.3.50): `expand-ev-heat`, an electric car and transit bus at a heat index of 83 degF, 996 of 996 at 1.008e-05, where the unfixed model fails every electric-bus cell. **The cold-soak chain is per group slot as of 2026-11-08** (§7.3.51): the eight vehicle-hour variables over two group slots rather than sixteen groups, the soak's hour gathered rather than matched, and `expand-fullyear` from 5 h 56 min to 11 min, byte-identical. **Two day types and several source types under aggregation as of 2026-11-11** (§7.3.63): DayWeighting1 does not cancel and HourWeighting3 is ONE source type's, `aggregateBy` 24-Hour Day's cells unpack their own hour-day, and `<outputtimestep>` Month and Year are emitted -- `aggregateBy` Year and the 24-Hour Day and Portion of Week output steps stay unexpressed, priced there. **`aggregateBy` Year as of 2026-11-12** (§7.3.65, conventions §117): `scale-county-timeagg-year` 18071 of 18071 at 1.134e-05, key-exact -- PreAggYEAR.sql's month collapse read through the aggregation months (`db_aggregationmonth`, `n_aggregatesMonths`), its FuelSupply a SUM that scales every process by the months' share of the year (F63) and Atmospheric CO2 by its cube (F64); Year + evaporative, refueling and air toxics refused. |
| **7e** | `moves-nonroad.esm`, same shape | 12 `nr-*` fixtures. **Begun 2026-09-23** (§7.3.34): `nonroad/model.esm` lifted out of `fixtures/nr-logging-county.esm`, `moves-nonroad.esm` over 21 national tables, and three county runs reproduce in `runspecs/nonroad/` -- `nr-logging-county` (144, byte-identical to the fixture), `nr-lawn-garden-county` (1,936, which found NONROAD's per-technology SCC chain and its lower-bin rule) and `nr-recreational-county` (1,010, SO2 written from BSFC). F60 on the way: a mounted leaf's precision is ignored. **State scale as of 2026-09-23** (§7.3.35): `nr-construction-state` (2,355) and `nr-pleasure-craft-state` (440) reproduce -- a state run is a county run at a pseudo-county MOVES builds, whose temperature, fuel supply and allocation the model now builds too -- and `grwfac.f`'s interpolation association is fixed in `lib/population.esm`. **Five of twelve.** **Nation scale as of 2026-09-23** (§7.3.36): `nr-commercial-nation` (908) reproduces on the model's first run. It is NOT a sum of state runs, as the state rung had read it: `PreAggNATION.sql` folds every table into one state 0 first, and the model computes each of the five folds, measured in pandas beforehand. **Six of twelve.** **Diesel and the whole inventory as of 2026-09-23** (§7.3.37): `nr-industrial-county`, `nr-airport-support-county`, `nr-agriculture-state` and `nr-mixed-nonroad` reproduce -- 213 SCCs each, gasoline, diesel, LPG, CNG and marine, in the dense layout at ~9 minutes and ~5 GB -- after five rules about where NONROAD applies an operation or what MOVES prints for it: per-technology sulfur alternates and the diesel PM correction, renormalized technology sets, a per-technology zero clamp, the nearest rate hp bin, and three-decimal month fractions. **Ten of twelve.** **`nr-railroad-support-nation` reproduces as of 2026-10-19** (§7.3.38): 23,108 rows, the gasoline SO2 residual closed by reading the `.OPT` sulfur through NONROAD's 10-column window, and one diesel cohort held by a declared `cell_exception` because the binary32 population sum crosses a `.POP` rounding boundary the format cannot narrow across (EarthSciAST#536, declined; the exception is permanent). **Eleven of twelve.** **Speciation and air toxics as of 2026-10-19** (§7.3.39): `nr-airtoxics-lawn-garden-county` (14,036) reproduces on the port's first run -- NRHCSpeciation and NRAirToxics as a rated root and a per-(point, technology) multiplier that is exactly 1 off the chain, over nine national tables -- and the runs re-checked are byte-identical. **Twelve of twelve; step 7e is done.** |
| **7f** | The five fixtures needing a second input database (four `-single` on `washtenaw_cdb`, `scale-project` on the project DB) | last, because they are the only ones whose model input is not the default DB. **Begun 2026-10-19** (§7.3.40, conventions §92): `scale-project` reproduces from the default database plus its PROJECT database -- 125 of 125, key set exact, worst cell 9.123e-06, on the first run -- after the catalogue gained a DOMAIN layer: `moves-onroad.esm` is now the DEFAULT domain's (`link`, `linkSourceTypeHour`, `runspecdomain`) over `onroad/default-database.esm`, and `inputs/washtenaw-project.esm` is the project's over the same. The model switches ProjectTAG's SHO, `LinkOperatingModeDistributionGenerator` (`lomd_*`) and link-level output on `run_isProjectDomain`, and `run_domainUnported` counts what a domain asks that it does not do. The twenty DEFAULT-domain RunSpecs are byte-identical. **One of five; the four `-single` runs need the row-merge half of §92.** **`process-extended-idle-single` reproduces as of 2026-10-19** (§7.3.41, conventions §93): 50 of 50 at 6.529e-06 from the default database plus Washtenaw's COUNTY database -- a row merge that shadows (`zoneRoadType`), one that adds keys (`hotellingActivityDistribution`), hotelling hours as the activity, the degenerate hotelling operating-mode distribution times `hourFractionAdjust`, and road type 1 for an off-network process; the 21 earlier RunSpecs byte-identical. **Two of five.** **`process-apu-single` reproduces as of 2026-10-19** (§7.3.41, conventions §94): 91 of 91 at 5.848e-06 on its first run -- one selected pollutant-process, two output processes, because the calculator retags shore power (mode 203) to process 93; the process-93 pairs have their own pair relation. **Three of five.** **`process-crankcase-extidle-single` reproduces as of 2026-10-19** (§7.3.41): 300 of 300 at 5.275e-06 on its first run -- extended idle's THC, CO and NOx with K and the diesel biodiesel ratio, and crankcase extended idle on its PARENT's road type, which a chained pollutant-process now takes in three rungs. **Four of five.** **`process-crankcase-start-single` reproduces as of 2026-10-20** (§7.3.41): 684 of 684 at 8.250e-06 -- the first start-exhaust RunSpec: AdjustStarts' starts, startsOpModeDistribution's weights, StartTempAdjustment's additive term, the 135 start fuel-effect strings with their ethanol cross terms and the Complex Model's start configurations, and crankcase start on its parent's road type. **Five of five; step 7f is done.** **The four DEFAULT-domain twins reproduce as of 2026-10-20** (§7.3.42): `process-apu` 91, `process-extended-idle` 100, `process-crankcase-start` 684 and `process-crankcase-extidle` 300 of their rows, on their first runs and with no model change, once moves.rs selected road type 1, the crankcase parents and source type 62, and Total Energy beside extended idle's CO2. **`scale-county` is captured and pending as of 2026-10-20** (§7.3.45, conventions §100): a complete county database of the default's own rows, an oracle equal to `expand-roadtypes`' on all 729 rows, and a wait on the road type as an axis that `expand-roadtypes` shares. **`scale-county` reproduces as of 2026-10-21** (§7.3.46): 729 of 729, its relation byte-identical to `expand-roadtypes'` in every column, with no change beyond the road-type axis. **PROJECT domain beyond running exhaust as of 2026-11-09** (§7.3.55, §7.3.56): `project-links` 3412 of 3412 (running, start, brake and tire wear on three links), `project-hotelling` 266 of 266 (extended idle and APU off-network) and `project-offnetwork` 650 of 650 at 8.316e-06 (permeation, venting and leaks on an on-network and an off-network link, ProjectTAG's SHP and SourceHours), each key set exact. **`runspecs/pending/` is empty.** **The idle and hotelling adjustment tables are ported as of 2026-11-10** (§7.3.57, conventions §109): `scale-county-idle-adjust`, a county database stating all six, 8128 of 8128 at 1.245e-05, key-exact -- AdjustTotalIdleFraction.sql's override and multipliers and AdjustHotelling.sql's hour, age and month blocks; `run_idleAdjustmentRows` retired, `hot_adjustmentRowsUnported` now multi-year only. **The chained processes, Rates-scale evaporation and the user's link distribution in PROJECT domain as of 2026-11-10** (§7.3.58): `project-crankcase` 3252 of 3252 (crankcase running, start and extended idle on their parents' links), `project-refueling` 418 of 418, `rates-project-evap` RatePerVehicle 128 and RatePerProfile 64 of theirs (the PROJECT population is the off-network fleet's), and `project-useromd` 1274 of 1274 (a user-stated running and evaporative distribution on one link), each key set exact, worst cell 1.324e-05. **PROJECT domain at Rates scale as of 2026-11-11** (§7.3.59, conventions §111): `rates-project-chained` (the crankcase and refueling processes on two links and an off-network one; RatePerDistance 2080, RatePerHour 250, RatePerVehicle 1065), `rates-project-evap-links` (evaporative RatePerDistance on two links, MOVESOutput over the link's distance; 632, 128, 64) and `rates-project-useromd` (the user's link distribution at Rates scale; 1082, 128, 64) reproduce every table, key-exact, worst cell 1.008e-05; `run_ratesProjectLinks` and `run_ratesProjectEvapDistance` retired. **AdjustHotelling at a second calendar year as of 2026-11-11** (§7.3.61, conventions §113): `userdb-hotelling-multiyear`, a DEFAULT-domain run at 2015 and 2020 with the adjustment tables in a USER database (MOVES refuses a county database with two years), 15616 of 15616 at 1.245e-05, key-exact -- TAG's table still holds the first year's rows when it adjusts the second, and every hour, age and month default pools both; `hot_adjustmentRowsUnported` now counts a third year only. **The structural PROJECT refusals as of 2026-11-11** (§7.3.60, conventions §112): `project-multilink` 7654 of 7654 (two links per road type: a link is a LOCATION, appended to the road-type relation), `project-grades` 5245 of 5245 (link grades as a declared slot axis of the per-second chain; out-of-bounds speeds extrapolated as MOVES does), `project-useromd-gaps` 2468 of 2468 (a user-governed distribution, and the rows MOVES does not write where it is empty) and `project-startconflict` 939 of 939 (the first user start row wins), each key set exact; a second county stays refused, as MOVES refuses it. **A walked drive schedule as of 2026-11-11** (§7.3.62, conventions §114): `project-driveschedule` 3672 of 3672 (two links with a user `driveScheduleSecondLink`, whose average speed MOVES writes into Link before SHO) and `project-zerospeed` 2444 of 2444 (an idling queue: thirty idle seconds, SHO's `else` arm, no brake-wear row), each key set exact, worst cell 1.324e-05, no exception; the link walks read schedule speeds as the FLOAT columns store them (`float_column_value`). **Time aggregation as of 2026-11-11** (§7.3.63, conventions §115): `scale-county-timeagg-day` (`aggregateBy` 24-Hour Day, output Month) 12576 of 12576 at 8.833e-06 and `scale-county-timeagg-month` (`aggregateBy` Month, output Year) 6288 of 6288 at 8.000e-06, key-exact -- start exhaust, crankcase start, extended idle, APU and off-network idle over a county database stating startsPerDay and the hotelling tables, the pre-aggregation run BEFORE AdjustStarts and AdjustHotelling as MOVES runs it, and the Month and Year output steps as a sum over cells (`mos_*`); `hot_aggregationUnported` retired for `run_aggregationUnported` (multi-year hotelling, idle adjustment tables, a partial week and evaporative processes under aggregation). **Every on-road process under aggregation as of 2026-11-12** (§7.3.64, conventions §116): `scale-county-timeagg-processes-day` (24-Hour Day, output Year) 19628 of 19628 at 1.802e-05 and `scale-county-timeagg-processes-month` (Month, output Month) 78512 of 78512 at 1.256e-05, key-exact, five cells under two scoped precision exceptions -- evaporative permeation, venting and leaks, refueling, crankcase running, start and extended idle, and brake and tire wear beside the exhaust processes. TankTemperatureGenerator over the collapsed ZoneMonthHour writes no cold-soak tank temperature (no permeation row, the soak all cold, no cold-soak vapor; `ttg_hasColdSoakTankTemperature`), TankFuelGenerator's temperature range is one point, EvapOMDG's fractionOfOperating sums the positive-SourceHours ages only, and a RunSpec's own Total Energy selection beside refueling is kept (`n_statedEnergyProcesses`); `run_aggregationUnported` no longer counts evaporative processes (a stated soakActivityFraction is counted instead), and `run_offNetworkLinkCount` is retired. **The 24-Hour Day and Portion of Week output steps and the last three aggregation refusals as of 2026-11-12** (§7.3.66, conventions §118): `scale-county-outstep-hourday` 2188, `-week` 8752 and `-dayagg` 8752 (the output step as MOVES's four OutputTimeStep flags, Portion of Week `x noOfRealDays`), `scale-county-idle-adjust-day` and `-month` 2032 each (idleDayAdjust's whole-week collapse), `scale-county-timeagg-weekday` 6288 (a partial week, no model change) and `userdb-hotelling-multiyear-day` and `-month` 3904 each (the pooled hotelling chain over the collapsed tables, and an earlier year's rows rescaled again at the whole-week day 0), every key set exact, worst cell 1.287e-05; `run_aggregationUnported` counts evaporative processes alone. **Year + the evaporative processes and refueling as of 2026-11-12** (§7.3.68, conventions §120): `scale-county-timeagg-processes-year` 19628 of 19628 at 1.134e-05, key-exact, no exception -- PreAggYEAR.sql's AverageTankTemperature and SoakActivityFraction sums act on tables no generator has written yet, and the summed FuelSupply share is read as a sum by TankFuelGenerator's gasohol share and RefuelingLossCalculator's RVP and energy content (`ffsup_suppliedShare`) and not at all by venting and leaks (`fuel_supply_summing_process`); `run_yearUnportedSelected` no longer counts processes 11, 12, 13, 18, 19. |

**7a is a GO, run 2026-09-10.** A ref'd, parent-fed model evaluates end to end
against the real default database: `spikes/7a/` reads `AgeCategory` (41 rows)
and `AgeGroup` (7), joins on `ageGroupID`, and reports 4/2/2/2/5/5/21 categories
and 6/9/13/17/60/85/630 age totals — verified against the raw Parquet
independently of the document, and falsified by perturbing the table and
watching exactly the predicted cells move. It is `run-tests.sh` stage 8, which
is two-sided: it fails if the child ever starts validating *alone*, so the
control cannot rot. The corrections it forced are folded into §7.1, §7.2 and
§7.3 above.

**The word "parent-shaped" is retired, and the change is not cosmetic.** The
spike was written with the child's axes sized by metaparameters only the parent
declared. EarthSciAST PR #298 refuses that, and Python always had; the same
relation is now produced by a child that declares its own shape and is merely
**data-open** — it reads two sources the parent holds. The numbers are the
recorded ones, unchanged. See §7.3.2 and findings F50 and F51. What follows is
the original framing, kept because it is what the gate was for.

**The original framing.** What is proven is *scoping and
validation*: a parent-fed ref **validates**. What is not proven
is that it **evaluates** — and the existing evidence is split in exactly the
wrong way. `runs/*.esm` ref components and do evaluate under the suite, but
supply **no data** (no `data_sources`, no `metaparameters`, no `index_sets`).
`fixtures/*.esm` supply data but **inline everything** rather than ref'ing. The
combination Phase 7 rests on is the one combination nothing in the tree
currently exercises. Do 7a before committing to 7b–7f.

Note also that the components' index sets are hardcoded probe sizes (5, 7, 3,
4) for self-contained unit tests. Making them parent-sized is real work across
~27 files, not a rename.

### 7.6 What this does not change

`docs/findings/*.esm` keep their inverted polarity, `run-tests.sh` keeps its
stages, and the snapshot-fed fixtures keep asserting. Phase 7 is additive: it
builds the half of the pipeline that has never been modelled, beside the half
that is at 32 of 32.
