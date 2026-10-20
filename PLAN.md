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
gates, not numerical ones. **The four `-single` variants are no longer among them as of 2026-10-19**: moves.rs recaptured them (`a75791bb`, local) with the hour, road types 1 and 4, the crankcase parents, and a county database that carries an age distribution, VMT and fuel supply, and they emit 91, 50, 300 and 684 rows (step 7f). The four default-scale twins are still empty, for the reason below. **They are zero for one shared reason, measured:**
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
- **Eight snapshots emitted no rows at all** (four of them, the `-single` variants, were recaptured non-empty on 2026-10-19; see step 7f) — `process-extended-idle`,
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
                └────────────── not modelled in .esm ─────────────────┘                   └──── §2's ladder, 30/32 ────┘
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
fixture stage already does — not by an assertion. And because a mounted
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

The faithful fix is a binary64 sum narrowed once to binary32, and the format cannot express it. esm-spec §11.3.1 refuses an equation whose right-hand side's precision differs from its left-hand side's, and offers no conversion (EarthSciML/EarthSciAST#536). The cohort is held instead to 2e-4 by a `cell_exception` in `tolerance.toml`. That is a new, narrow mechanism in `compare-output.py`, keyed by (SCC, model year), with a mandatory reason. It is refused if it matches no cell, and reported as dead weight once the cells are inside the full gate. Every other cell of every run keeps 2e-5. Both residuals were precision artifacts. The difference between them was cost: the sulfur window is one exact template, while the population would need binary64 islands and a new operator.


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
| `hotellingHourFraction`, `-AgeFraction`, `-MonthAdjust` | created empty | empty both sides | declared; a row at the run's zone is counted by `run_domainUnported` |
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

**Unchanged runs.** All 21 DEFAULT- and PROJECT-domain RunSpecs were emitted at
aa077b6 and again on the branch: every out_* relation is byte-identical and every
recomputed shape number identical, `run_selectionUnported` 0 on each
(`expand-sourcetype` with the memory-fixed binary, `esm.fix9`). The 7c spike is
byte-identical, and the Python binding loads the new RunSpec.

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

**Filed by the units passes, both open:**

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
| **7d** | Widen the runspec surface one selection dimension at a time — pollutant-process, source type, road type, timespan, geography | each dimension added only with a fixture that **discriminates** it (§23). **Begun 2026-09-17** (§7.3.4): **timespan** done at the day axis, the output relation is no longer a rectangle over the selected pollutant-processes (`runspecs/expand-day.esm`, 250 rows, byte-identical to the inlined fixture over 25 shared fields), and **geography** done at three counties in three states (`runspecs/expand-counties.esm`, 375 rows, worst cell 1.140e-05; conventions §61). **Source type is an axis as of 2026-09-18** (§7.3.5, conventions §62): 44 variables promoted, `run_sourceTypeID` gone, the three existing runs unchanged to the digit, and `runspecs/pending/expand-fueltype-diesel.esm` emitting the right 248-row shape with source type 21's 125 rows exact at 7.106e-06. **The source bin is its own relation as of 2026-09-18** (§7.3.6, conventions §63): `sourcebin_rows` beside `cohort_rows`, `n_sourceBin` a third declared and checked number relayed per fixture, the three existing runs still unchanged to the digit, and `expand-fueltype-diesel`'s activity AND source-bin distribution both exact for both source types — 330 bins against the run's own `sourceBinDistributionFuelUsage`. **The drive cycle is per VEHICLE as of 2026-09-18** (§7.3.7, conventions §64): `physicsrow_rows` is the run's selected `sourceusetypephysics` rows densely ranked, `n_physicsRow` a fourth declared and checked number, the three existing runs STILL unchanged to the digit, and **`runspecs/expand-fueltype-diesel.esm` promoted out of `pending/`** — all 248 rows, worst cell 7.372e-06, both regulatory classes of source type 32 and the split at model year 2010. **`runspecs/expand-sourcetype.esm` reproduces as of 2026-09-20** (§7.3.8, §7.3.9): the 40 GB kill was EarthSciAST#418 and was fixed upstream by PRs #420 and #423 — the run went from killed at 32 GB to 0.89 GB and 91 s — and the three cells left after that were `emissionRateAdjustment`, a table the model did not read, ported as J56. All 430 rows, worst cell 9.017e-06. **`runspecs/pending/` is empty.** **The month is an axis as of 2026-09-20** (§7.3.10, conventions §65): 26 variables promoted, `run_monthID` no longer a `run_rows` scalar, the output relation five levels, and all FIVE existing runs unchanged to the digit. **`runspecs/expand-month.esm` reproduces as of 2026-09-20** (§7.3.11, §7.3.12, conventions §66): `aggregateBy = Month` is three more lists a RunSpec declares and a model that reads its speed distribution and its meteorology as weighted means over TIME CELLS, not a second mode — 500 of 500 rows, worst cell 8.513e-06, reproduced on the first run because both pre-aggregation weights were measured before the port. **`runspecs/expand-criteria.esm` reproduces as of 2026-09-20** (§7.3.14, §7.3.15, conventions §68, §69): `criteriaRatio` is EMPTY in the default database and MOVES computes its 4,398 rows at run time TWO WAYS — a closed form the database ships as SQL text, and the live EPA Complex Model plus the sulfur model — 372 of 372 rows, worst cell 7.805e-06, and with it the rule that a cohort or a pollutant-process with no rate is not emitted. **`runspecs/process-brakewear.esm` reproduces as of 2026-09-20** (§7.3.16) and cost NO model change: 375 of 375 rows, worst cell 8.251e-06, and it is the first run here whose model-year group is not `Doesn't Matter`. **`runspecs/process-nox-speciation.esm` and `runspecs/process-crankcase-running.esm` reproduce as of 2026-09-20** (§7.3.17, conventions §70): the output relation stops being a RECTANGLE. A chained block is as wide as its ratio table's coverage and no ratio table has an electricity row, so the species and crankcase blocks are 104 cohorts where their parents are 124; `n_outputRate`, one declared number ranked over (pollutant-process, cohort) pairs, replaces the two that could only describe a product. 436 of 436 at 9.485e-06 and 684 of 684 at 7.805e-06, both reproduced in pandas before the port and both right on the document's first run, with all eight earlier RunSpecs unchanged to the digit. **The chain became a FIXED POINT as of 2026-09-20** (§7.3.18, conventions §71): `rtDay_quantChained` read the parent's DIRECT quantity, which is right for every chain in `runspecs/` and gives a grandchild ZERO — and the hydrocarbon species are nothing but grandchildren, THC to NMHC to NMOG to TOG. Three value passes and four presence passes, three being the longest chain in the whole snapshot corpus, counted; `run_chainDepthExceeded` is the run's own check that a fourth would add nothing, asserted at 0, and all ten RunSpecs unchanged to the digit. ****`runspecs/chain-tog-speciation.esm` and `runspecs/chain-nonhaptog.esm` reproduce as of 2026-09-20** (§7.3.20, conventions §72): the hydrocarbon species, 540 of 540 rows each at 7.564e-06, both right on the document's first run. A ratio table keyed by the fuel SUBTYPE, a chained pollutant-process with TWO parents, and a species computed from a tally MOVES never reports -- and one runtime mistake, seven copies of a lookup spine over a 105,651-row table, which took `expand-day` from 60 seconds to 564 and now leaves it at 34. **`runspecs/process-airtoxics.esm` reproduces as of 2026-09-21** (§7.3.21, conventions §73, §74): the first RunSpec here that needs a table the default database ships EMPTY -- `ATRatio`, which MOVES writes at run time from two different computations, three closed-form expressions `docs/fuel-effects-generator.md` §8.1 had recorded as checkable by nobody and a COMPLEX MODEL at a fourth calculation engine. 644 of 644 rows at 7.564e-06, measured in pandas from the default database first. It found a constant that was a key (the complex model's reference model-year group, invisible to all three criteria configurations because they agree), a centring that only shows up in a NONLINEAR term (three answers 7.4 % high through one shared denominator), and a `filter` that is silently IGNORED once its aggregate has two output indices (EarthSciML/EarthSciAST#441), which `run-tests.sh` now lints for. **Thirteen RunSpecs in `runspecs/`.** **`runspecs/pending/chain-so2-co2e-mechanism.esm` is the measurement of what is left** (§7.3.22, 2026-09-21): every one of the 1,294 rows this chain emits for that run is RIGHT at 8.201e-06 and the whole of the gap to its 2,767 is ABSENCE, in five pieces -- `SO2Calculator`, `CO2AE` and its addition of three different parents by global warming potential, `TOGSpeciation`'s clamped subtraction of a species set, two more air-toxics ratio paths, and three toxics thought to need only DATA in the two relations §7.3.21 built. The energy root it was thought to need is already here: Total Energy and N2O reproduce exactly, and eleven of the twenty-six pollutants are complete before that rung is written. **The fifth of those five pieces is closed as of 2026-09-21** (§7.3.23, conventions §73.5), and it was NOT data: ethanol's model-year-2000-and-earlier ratio is a SEVENTH algebraic form -- a step in the ethanol volume, which `docs/fuel-effects-generator.md` §2.1's census had silently absorbed into the sulfur switch because MariaDB does not care about case -- and acetaldehyde's complex model reads two fuel properties the shared relation did not carry, which showed up as a FLAT 2.386 on the 21 model years the complex half covers and on nothing else. 1,294 → **1,477 rows, worst cell 8.201e-06 unmoved**, thirteen RunSpecs unchanged to the digit, and fourteen of the twenty-six pollutants now complete. What is left after the remaining four pieces is `process-pm-exhaust`, **measured as of 2026-09-22** (§7.3.24): its cycle is MOVES's declaration and not its arithmetic, the machinery exists in `fixtures/process-pm-exhaust.esm`, and of the 456 rows the chain emits 37 are right -- EC lacked the base-rate `generalFuelRatio` by exactly its value, and the crankcase path wrongly claimed sulfate and water. **All three causes fixed the same day, and `runspecs/process-pm-exhaust.esm` reproduces: 728 of 728 at 7.516e-06, on the port's first run** -- `SulfatePMCalculator` as a four-species share matrix, which needs no cycle (conventions §76). **Fourteen RunSpecs in `runspecs/`.** **`runspecs/chain-so2-co2e-mechanism.esm` reproduces as of 2026-09-22** (§7.3.25, conventions §77, §78): all 2,767 rows at 8.201e-06, the four remaining pieces each reproduced in pandas first. SO2 found that MOVES chains in kilojoules and this chain in reported units, and CO2AE found that not every chain edge is in `runspecchainedto`; both became a weight on one unioned edge relation. **Fifteen RunSpecs in `runspecs/`, `pending/` empty.** **`runspecs/chain-so2-co2e-mechanism-control.esm` reproduces as of 2026-09-22** (§7.3.26): all 2,309 rows at 8.201e-06 on its first run, at no model cost. It is the twin with five pollutants DESELECTED, MOVES's own two answers are bit-identical on every shared row, and so it tests GATING and not arithmetic -- the declared CO2AE edge list, which is present in every run, and the mechanism switch, which `chain-nonhaptog` exercises from the other side. **Sixteen RunSpecs in `runspecs/`.** What is left of the onroad corpus is the four evaporative and refueling runs (`process-evap-permeation`, `-leaks`, `-fvv`, `process-refueling`, all with snapshot-path fixtures), `mixed-onroad` and `scale-project` -- and the evaporative four are **measured as of 2026-09-22** (§7.3.27). `onroad/model.esm` has no evaporative machinery at all, and all four outputs of `TankTemperatureGenerator` are EMPTY nationally -- 2,645 lines of Java in seven steps, and the largest thing left in the onroad corpus. **`process-evap-leaks` needs none of it**, which is why `docs/evap-leaks.md` §0.3 chose that run: MOVES's own `opModeDistributionTemp` for it is 150→0, 151→0, 300→1, so the soak modes enter at weight exactly zero and an empty `soakActivityFraction` costs the run nothing -- provided the document COMPUTES that weight rather than assuming it (conventions §18.2). What it needs instead is relational and familiar: the evap op-mode distribution, the `IMCoverage` lift, the op-mode-weighted base rate and `SourceHours`. Permeation and FVV cannot dodge the thermal chain, and it is priced: two of `soakActivityFraction`'s three terms come off the national tables exactly (49,260 and 1,446 minutes) and the third, 1,058 hot-soak minutes, is a minute-by-minute recurrence -- 4,913 without its cutoff. The format already holds a recurrence (conventions §19, `agedist.f`), so this is not an upstream ask; it would be the first one on the ONROAD side. **`runspecs/process-evap-leaks.esm` reproduces as of 2026-09-22** (§7.3.28, conventions §80): all 64 rows at 7.294e-06 on the document's first run, the same worst cell an independent pandas reproduction from the national tables had reached before the model changed. It is the first EVAPORATIVE run here and it cost 21 variables and 13 equations, because `pp_W` gained an ALTERNATIVE and not a term: the evaporative operating-mode distribution comes from a different generator, over soaking and running rather than over speed bins, and `SHO / noOfRealDays` was already the inventory calculator's activity. The I/M lift turned out not to be work at all -- `IMCoverage` is 2,024,874 national rows that narrow to ZERO for county 26161 -- and `soakActivityFraction` is mounted although it has no rows, because an aggregate over an empty relation is the additive identity and the alternative is moving the statement out of the database and into the document. It is also the first run whose INTERMEDIATE row set diverges where its numbers do not: MOVES's `opModeDistribution` has three rows to this chain's one, and the two missing ones carry exactly 0. **Seventeen RunSpecs in `runspecs/`.** `process-refueling` is **measured as of 2026-09-22** (§7.3.29) and the measurement came back empty-handed in the best way: the national default database reproduces all 168 of its rows at 6.981e-06 already, identical to the execution-database reproduction at every cell. Five tables need mounting -- `refuelingControlTechnology` (189,379 national rows narrowing to exactly the 9,102 the execution copy held), `countyYear`, `sourceTypeTechAdjustment`, `refuelingFactors` and `fuelType` -- and the model work is `components/refueling_loss_rate.esm`'s 32 variables over REFEC-1..8, with all eight of its shapes already factored in `lib/refueling.esm`. It needs nothing from `TankTemperatureGenerator`, which the evaporative pair cannot say. **`runspecs/process-refueling.esm` reproduces as of 2026-09-22** (§7.3.30, conventions §81, §82): all 168 rows at 6.981e-06, the same worst cell the pandas reproduction had reached. The calculator went in as priced -- REFEC-1 and REFEC-2 checked against the specification's own 3.0152931048711182 and 2.8986555933440346 before anything downstream was written, and the 189,379-row control-technology lookup put on the BIN rather than the rate row for a spine seven times smaller. What was NOT priced was that two gates had been right by coincidence for seventeen runs. `occursOnRealRoads` says where `BaseRateGenerator` WRITES a process's rates, not where its rows appear, and refueling has no rate rows at all, so its rows take their parent's road type. And a chain PREREQUISITE is not a selection: `runspecpollutantprocess` carries seven pollutant-processes and MOVES emits two, because `flagRequiredPollutantProcesses` added three energy ones and the output processor strips what it added -- the first time the execution database is not enough, recoverable only because the needs table is refueling-only. The failure before it was understood was 125 energy rows and 43 with summed key columns, caught by the comparator's key check and by nothing else. **Eighteen RunSpecs in `runspecs/`.** `process-evap-permeation` is **measured as of 2026-09-22** (§7.3.31): the national default database reproduces all 64 rows at 5.630e-06 with every tank temperature COMPUTED, and `TankTemperatureGenerator`'s TTG-2 to TTG-5 are one lag-1 recurrence over `SampleVehicleTrip`'s rows with closed forms inside each trip -- the soak's early stop is a single threshold on the trip's key-off temperature. Probed on the ingest path at 1.7 s, bit-identical. **`runspecs/process-evap-permeation.esm` reproduces as of 2026-09-22** (§7.3.32, conventions §83, §84): all 64 rows at 5.630e-06, the tank temperature COMPUTED by `TankTemperatureGenerator` TTG-1 to TTG-5 in the model -- one recurrence over the national trips, 595,456 cells matching an independent walk -- and two keys fixed on the way: the source bin's regulatory class is 0 for a process whose `isRegClassReqd` is 'N', and `temperatureAdjustment`'s permeation rows are not S15's quadratic. Five other runspecs byte-identical. **Nineteen RunSpecs in `runspecs/`.** **`runspecs/process-evap-fvv.esm` reproduces as of 2026-09-22** (§7.3.33, conventions §85): all 64 rows at 7.517e-06 on the model's first run. The operating insert of TVV-8 went in -- `TankFuelGenerator`'s tank RVP, which the default database ships empty, and `evapRVPTemperatureAdjustment` interpolated at it as a weight per knot -- and the cold-soak insert did not: it is weighted by a computed exactly-zero on an on-network link, and the shape check's `run_offNetworkLinkCount` makes its absence fail loudly the day a RunSpec could weight it. **Twenty RunSpecs in `runspecs/`, and the onroad corpus is ported except `scale-project` (step 7f).** |
| **7e** | `moves-nonroad.esm`, same shape | 12 `nr-*` fixtures. **Begun 2026-09-23** (§7.3.34): `nonroad/model.esm` lifted out of `fixtures/nr-logging-county.esm`, `moves-nonroad.esm` over 21 national tables, and three county runs reproduce in `runspecs/nonroad/` -- `nr-logging-county` (144, byte-identical to the fixture), `nr-lawn-garden-county` (1,936, which found NONROAD's per-technology SCC chain and its lower-bin rule) and `nr-recreational-county` (1,010, SO2 written from BSFC). F60 on the way: a mounted leaf's precision is ignored. **State scale as of 2026-09-23** (§7.3.35): `nr-construction-state` (2,355) and `nr-pleasure-craft-state` (440) reproduce -- a state run is a county run at a pseudo-county MOVES builds, whose temperature, fuel supply and allocation the model now builds too -- and `grwfac.f`'s interpolation association is fixed in `lib/population.esm`. **Five of twelve.** **Nation scale as of 2026-09-23** (§7.3.36): `nr-commercial-nation` (908) reproduces on the model's first run. It is NOT a sum of state runs, as the state rung had read it: `PreAggNATION.sql` folds every table into one state 0 first, and the model computes each of the five folds, measured in pandas beforehand. **Six of twelve.** **Diesel and the whole inventory as of 2026-09-23** (§7.3.37): `nr-industrial-county`, `nr-airport-support-county`, `nr-agriculture-state` and `nr-mixed-nonroad` reproduce -- 213 SCCs each, gasoline, diesel, LPG, CNG and marine, in the dense layout at ~9 minutes and ~5 GB -- after five rules about where NONROAD applies an operation or what MOVES prints for it: per-technology sulfur alternates and the diesel PM correction, renormalized technology sets, a per-technology zero clamp, the nearest rate hp bin, and three-decimal month fractions. **Ten of twelve.** **`nr-railroad-support-nation` reproduces as of 2026-10-19** (§7.3.38): 23,108 rows, the gasoline SO2 residual closed by reading the `.OPT` sulfur through NONROAD's 10-column window, and one diesel cohort held by a declared `cell_exception` because the binary32 population sum crosses a `.POP` rounding boundary the format cannot narrow across (EarthSciAST#536). **Eleven of twelve.** **Speciation and air toxics as of 2026-10-19** (§7.3.39): `nr-airtoxics-lawn-garden-county` (14,036) reproduces on the port's first run -- NRHCSpeciation and NRAirToxics as a rated root and a per-(point, technology) multiplier that is exactly 1 off the chain, over nine national tables -- and the runs re-checked are byte-identical. **Twelve of twelve; step 7e is done.** |
| **7f** | The five fixtures needing a second input database (four `-single` on `washtenaw_cdb`, `scale-project` on the project DB) | last, because they are the only ones whose model input is not the default DB. **Begun 2026-10-19** (§7.3.40, conventions §92): `scale-project` reproduces from the default database plus its PROJECT database -- 125 of 125, key set exact, worst cell 9.123e-06, on the first run -- after the catalogue gained a DOMAIN layer: `moves-onroad.esm` is now the DEFAULT domain's (`link`, `linkSourceTypeHour`, `runspecdomain`) over `onroad/default-database.esm`, and `inputs/washtenaw-project.esm` is the project's over the same. The model switches ProjectTAG's SHO, `LinkOperatingModeDistributionGenerator` (`lomd_*`) and link-level output on `run_isProjectDomain`, and `run_domainUnported` counts what a domain asks that it does not do. The twenty DEFAULT-domain RunSpecs are byte-identical. **One of five; the four `-single` runs need the row-merge half of §92.** **`process-extended-idle-single` reproduces as of 2026-10-19** (§7.3.41, conventions §93): 50 of 50 at 6.529e-06 from the default database plus Washtenaw's COUNTY database -- a row merge that shadows (`zoneRoadType`), one that adds keys (`hotellingActivityDistribution`), hotelling hours as the activity, the degenerate hotelling operating-mode distribution times `hourFractionAdjust`, and road type 1 for an off-network process; the 21 earlier RunSpecs byte-identical. **Two of five.** **`process-apu-single` reproduces as of 2026-10-19** (§7.3.41, conventions §94): 91 of 91 at 5.848e-06 on its first run -- one selected pollutant-process, two output processes, because the calculator retags shore power (mode 203) to process 93; the process-93 pairs have their own pair relation. **Three of five.** **`process-crankcase-extidle-single` reproduces as of 2026-10-19** (§7.3.41): 300 of 300 at 5.275e-06 on its first run -- extended idle's THC, CO and NOx with K and the diesel biodiesel ratio, and crankcase extended idle on its PARENT's road type, which a chained pollutant-process now takes in three rungs. **Four of five.** |

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
that is at 30 of 32.
