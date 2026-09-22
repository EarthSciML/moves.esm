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
gates, not numerical ones. **They are zero for one shared reason, measured:**
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
- **Eight snapshots emit no rows at all** — `process-extended-idle`,
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

**`runspecs/pending/` holds two documents**, both measurements.

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
| **7d** | Widen the runspec surface one selection dimension at a time — pollutant-process, source type, road type, timespan, geography | each dimension added only with a fixture that **discriminates** it (§23). **Begun 2026-09-17** (§7.3.4): **timespan** done at the day axis, the output relation is no longer a rectangle over the selected pollutant-processes (`runspecs/expand-day.esm`, 250 rows, byte-identical to the inlined fixture over 25 shared fields), and **geography** done at three counties in three states (`runspecs/expand-counties.esm`, 375 rows, worst cell 1.140e-05; conventions §61). **Source type is an axis as of 2026-09-18** (§7.3.5, conventions §62): 44 variables promoted, `run_sourceTypeID` gone, the three existing runs unchanged to the digit, and `runspecs/pending/expand-fueltype-diesel.esm` emitting the right 248-row shape with source type 21's 125 rows exact at 7.106e-06. **The source bin is its own relation as of 2026-09-18** (§7.3.6, conventions §63): `sourcebin_rows` beside `cohort_rows`, `n_sourceBin` a third declared and checked number relayed per fixture, the three existing runs still unchanged to the digit, and `expand-fueltype-diesel`'s activity AND source-bin distribution both exact for both source types — 330 bins against the run's own `sourceBinDistributionFuelUsage`. **The drive cycle is per VEHICLE as of 2026-09-18** (§7.3.7, conventions §64): `physicsrow_rows` is the run's selected `sourceusetypephysics` rows densely ranked, `n_physicsRow` a fourth declared and checked number, the three existing runs STILL unchanged to the digit, and **`runspecs/expand-fueltype-diesel.esm` promoted out of `pending/`** — all 248 rows, worst cell 7.372e-06, both regulatory classes of source type 32 and the split at model year 2010. **`runspecs/expand-sourcetype.esm` reproduces as of 2026-09-20** (§7.3.8, §7.3.9): the 40 GB kill was EarthSciAST#418 and was fixed upstream by PRs #420 and #423 — the run went from killed at 32 GB to 0.89 GB and 91 s — and the three cells left after that were `emissionRateAdjustment`, a table the model did not read, ported as J56. All 430 rows, worst cell 9.017e-06. **`runspecs/pending/` is empty.** **The month is an axis as of 2026-09-20** (§7.3.10, conventions §65): 26 variables promoted, `run_monthID` no longer a `run_rows` scalar, the output relation five levels, and all FIVE existing runs unchanged to the digit. **`runspecs/expand-month.esm` reproduces as of 2026-09-20** (§7.3.11, §7.3.12, conventions §66): `aggregateBy = Month` is three more lists a RunSpec declares and a model that reads its speed distribution and its meteorology as weighted means over TIME CELLS, not a second mode — 500 of 500 rows, worst cell 8.513e-06, reproduced on the first run because both pre-aggregation weights were measured before the port. **`runspecs/expand-criteria.esm` reproduces as of 2026-09-20** (§7.3.14, §7.3.15, conventions §68, §69): `criteriaRatio` is EMPTY in the default database and MOVES computes its 4,398 rows at run time TWO WAYS — a closed form the database ships as SQL text, and the live EPA Complex Model plus the sulfur model — 372 of 372 rows, worst cell 7.805e-06, and with it the rule that a cohort or a pollutant-process with no rate is not emitted. **`runspecs/process-brakewear.esm` reproduces as of 2026-09-20** (§7.3.16) and cost NO model change: 375 of 375 rows, worst cell 8.251e-06, and it is the first run here whose model-year group is not `Doesn't Matter`. **`runspecs/process-nox-speciation.esm` and `runspecs/process-crankcase-running.esm` reproduce as of 2026-09-20** (§7.3.17, conventions §70): the output relation stops being a RECTANGLE. A chained block is as wide as its ratio table's coverage and no ratio table has an electricity row, so the species and crankcase blocks are 104 cohorts where their parents are 124; `n_outputRate`, one declared number ranked over (pollutant-process, cohort) pairs, replaces the two that could only describe a product. 436 of 436 at 9.485e-06 and 684 of 684 at 7.805e-06, both reproduced in pandas before the port and both right on the document's first run, with all eight earlier RunSpecs unchanged to the digit. **The chain became a FIXED POINT as of 2026-09-20** (§7.3.18, conventions §71): `rtDay_quantChained` read the parent's DIRECT quantity, which is right for every chain in `runspecs/` and gives a grandchild ZERO — and the hydrocarbon species are nothing but grandchildren, THC to NMHC to NMOG to TOG. Three value passes and four presence passes, three being the longest chain in the whole snapshot corpus, counted; `run_chainDepthExceeded` is the run's own check that a fourth would add nothing, asserted at 0, and all ten RunSpecs unchanged to the digit. ****`runspecs/chain-tog-speciation.esm` and `runspecs/chain-nonhaptog.esm` reproduce as of 2026-09-20** (§7.3.20, conventions §72): the hydrocarbon species, 540 of 540 rows each at 7.564e-06, both right on the document's first run. A ratio table keyed by the fuel SUBTYPE, a chained pollutant-process with TWO parents, and a species computed from a tally MOVES never reports -- and one runtime mistake, seven copies of a lookup spine over a 105,651-row table, which took `expand-day` from 60 seconds to 564 and now leaves it at 34. **`runspecs/process-airtoxics.esm` reproduces as of 2026-09-21** (§7.3.21, conventions §73, §74): the first RunSpec here that needs a table the default database ships EMPTY -- `ATRatio`, which MOVES writes at run time from two different computations, three closed-form expressions `docs/fuel-effects-generator.md` §8.1 had recorded as checkable by nobody and a COMPLEX MODEL at a fourth calculation engine. 644 of 644 rows at 7.564e-06, measured in pandas from the default database first. It found a constant that was a key (the complex model's reference model-year group, invisible to all three criteria configurations because they agree), a centring that only shows up in a NONLINEAR term (three answers 7.4 % high through one shared denominator), and a `filter` that is silently IGNORED once its aggregate has two output indices (EarthSciML/EarthSciAST#441), which `run-tests.sh` now lints for. **Thirteen RunSpecs in `runspecs/`.** **`runspecs/pending/chain-so2-co2e-mechanism.esm` is the measurement of what is left** (§7.3.22, 2026-09-21): every one of the 1,294 rows this chain emits for that run is RIGHT at 8.201e-06 and the whole of the gap to its 2,767 is ABSENCE, in five pieces -- `SO2Calculator`, `CO2AE` and its addition of three different parents by global warming potential, `TOGSpeciation`'s clamped subtraction of a species set, two more air-toxics ratio paths, and three toxics thought to need only DATA in the two relations §7.3.21 built. The energy root it was thought to need is already here: Total Energy and N2O reproduce exactly, and eleven of the twenty-six pollutants are complete before that rung is written. **The fifth of those five pieces is closed as of 2026-09-21** (§7.3.23, conventions §73.5), and it was NOT data: ethanol's model-year-2000-and-earlier ratio is a SEVENTH algebraic form -- a step in the ethanol volume, which `docs/fuel-effects-generator.md` §2.1's census had silently absorbed into the sulfur switch because MariaDB does not care about case -- and acetaldehyde's complex model reads two fuel properties the shared relation did not carry, which showed up as a FLAT 2.386 on the 21 model years the complex half covers and on nothing else. 1,294 → **1,477 rows, worst cell 8.201e-06 unmoved**, thirteen RunSpecs unchanged to the digit, and fourteen of the twenty-six pollutants now complete. What is left after the remaining four pieces is `process-pm-exhaust`, **measured as of 2026-09-22** (§7.3.24): its cycle is MOVES's declaration and not its arithmetic, the machinery exists in `fixtures/process-pm-exhaust.esm`, and of the 456 rows the chain emits 37 are right -- EC lacks the base-rate `generalFuelRatio` by exactly its value, and the crankcase path wrongly claims sulfate and water |
| **7e** | `moves-nonroad.esm`, same shape | 12 `nr-*` fixtures |
| **7f** | The five fixtures needing a second input database (four `-single` on `washtenaw_cdb`, `scale-project` on the project DB) | last, because they are the only ones whose model input is not the default DB |

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
