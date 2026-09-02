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
ESM evaluates in `binary64`; `domain.element_type: "Float32"` is document-wide
and does not reproduce per-expression single-precision rounding. Set a relative
tolerance and record it — do not promise bit equality.

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

### 1.6.1a Measured against the .esm, not the oracle **[Phase 2, done]**

The first end-to-end comparison has run. `fixtures/nr-logging-county.esm` reads
seventeen snapshot tables through `data_sources` and emits twelve MOVESOutput
rows -- SCC `2260007005`, §6.1's worked example -- through
`simulate --format csv`. Against the snapshot:

```
rows: 12 actual / 144 expected
key set: 12 shared, 132 missing, 0 extra
worst cell: rel=4.025e-06 over 12 cells (tolerance 2e-05)
```

So the per-cell gate this plan sets is met by every row the port produces, at
one fifth of its tolerance. The 132 missing keys are the other two SCCs and are
recorded in `tolerance.toml` under `[shortfall."nr-logging-county"]`; §1.6.1's
four-row binary64 question is NOT among them and has not yet been reached,
because MY2018's grown model-year fraction is carried rather than computed
(finding F12) and therefore keeps its float32 value of 5.9e-08. When the
remaining SCCs land the four rows become live and §1.6.2 becomes the blocker it
is described as being.

### 1.6.2 `element_type: "Float32"` was declared, documented, and ignored — **now honoured**

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
silent mixed precision would be the seventh instance of §5's failure mode.

## 2. Target ladder

Snapshot `MOVESOutput` row counts, the honest measure of fixture size:

| rows | fixture | path |
|---|---|---|
| 128 | `process-evap-permeation`, `-leaks`, `-fvv` | onroad evap |
| 144 | **`nr-logging-county`** | NONROAD |
| 250 | **`mixed-onroad`**, `expand-day` | onroad base-rate |
| 336 | `process-refueling` | onroad evap |
| 744–750 | `expand-criteria`, `process-brakewear`, `process-tirewear` | onroad |
| 1,080 | `chain-tog-speciation`, `chain-nonhaptog` | speciation chains |
| 1,936–2,355 | `nr-lawn-garden-county`, `nr-construction-state` | NONROAD |
| 15,801–23,108 | `nr-industrial-county`, `nr-agriculture-state`, `nr-railroad-support-nation`, … | NONROAD, large |

Eight fixtures have 0 output rows (`process-apu*`, `process-extended-idle*`,
`process-crankcase-extidle*`, `process-crankcase-start*`) — cheap structural
gates, not numerical ones.

Each snapshot carries **both sides** of the comparison: ~200 non-empty
`MOVESExecution` input tables *and* the expected `MOVESOutput`. No canonical
MOVES, MariaDB, or JVM is needed to develop against them.

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

**Status: specified and four of six stages built.** The port specification is
`docs/mixed-onroad.md`, written to the method of its NONROAD companion: the
input inventory from four cross-checked sources, the eighteen-step chain with
source lines, thirty-five joins with their exact key pairs, four worked
examples and an executable oracle (`./run-onroad-oracle.sh`). Four components
and an assembly cover S1–S12 and S15–S18, with 296 assertions.
`docs/esm-conventions.md` §16 records what the onroad graph changed: every
Phase 1/2 rule held, four gained a second reason, three things are new.

**One relation is not computed, and this changes the phase's exit criterion.**
`W[hourDayID, opModeID]` — the speed-bin-weighted drive-cycle operating-mode
distribution, 46 numbers — is computed inside the MOVES worker and dropped, so
no captured table carries it, and `ratesopmodedistribution` covers only the
off-network road type and start exhaust. §7.3 isolates it by solving for it
(125 equations, 23 unknowns, residual 7.1 × 10⁻⁶ at the reference's own
six-significant-figure storage floor), which proves the base rate factorises
exactly around it and everything either side is right. §8.1 says what computing
it takes: second-by-second VSP over `driveschedulesecond`'s 63,602 rows with
`sourceusetypephysicsmapping`'s road-load coefficients, three F11
neighbouring-row relations for acceleration and the 3-second brake lookback,
and a range-predicate classification against `operatingmode`. Every piece has a
spelling; it is F17's "big table meets big table" shape and needs
`operating_mode_rows` as an axis.

**No fixture yet, and §7.4 argues that rather than recording a shortfall.** A
document emitting 250 correctly-keyed rows with an uncomputed rate fails the
per-cell gate for a shape `[shortfall]`'s exact counts cannot express; one
reading the reference's own `baserate_1_2020` passes by transcribing the
answer. So the exit criterion becomes: land `W`, check it end to end against
`MOVESOutput` (§7.3 shows that is a sufficient check), then wire the fixture.
That is one coherent piece of work and it opens Phase 4 — whose cheapest slice
is start exhaust, because its operating-mode distribution IS in the snapshot.

### Phase 4 — Broaden by process

One new leaf component per process, each reusing the spine: evap (permeation /
leaks / FVV, 128 rows each), refueling (336), brake and tire wear (750 each),
crankcase (1,368), PM exhaust (1,456), the TOG/NonHAPTOG speciation chains
(1,080), air toxics (1,288). The zero-row idle/APU fixtures come along as
structural gates.

### Phase 5 — Scale out

Remaining NONROAD sectors (mostly the Phase 2 components against different
sector data) and the `expand-*` dimension fixtures (multi-county, multi-month,
multi-year, road types, fuel types). This is where the §1.3 gate gets
stress-tested — the first place where a join's match count, not its index-set
product, becomes the number that matters.

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

Phases 0 and 1 are done and merged. What follows is ordered by what blocks what.

1. **Wire a `PrepareProvider` into the `esm` binary** (§1.5) — the one hard
   blocker. Until it lands, no `.esm` can read a `data_sources` entry, so the
   144-row comparison cannot run at all. In flight upstream.
2. **Fix F1 and F4** (`docs/findings/README.md`). F4 is a silent wrong answer —
   an `aggregate` range symbol named `t` makes `join.on` match nothing and the
   reduction returns 0, with no error and a document that validates. F1 blocks
   the nested subsystem mount that CLAUDE.md's compositional rule assumes, so
   every relational leaf currently mounts as a top-level `{ref}` instead. Both
   in flight upstream.
3. **Author the Phase 2 chain** — unblocked *except* for the fixture
   comparison, because each stage's inline tests take their numbers from the
   specification's worked examples (§6.1–§6.3) and run today against `const`
   arrays. In flight.
4. **Finish the parquet work in EarthSciIO** — the cross-language conformance
   corpus case. In flight.
5. **Julia's `join.on` gate** — `BEHAV-10-B-001` and `-004`. In flight. Python
   needs only `-004`.

Then Phase 3 (`mixed-onroad`, 250 rows), which is the first onroad slice and
the first test of whether the conventions survive contact with the rates-first
base-rate path rather than a self-contained NONROAD chain.

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

The layered gates are not belt-and-braces. Measured by perturbing the real
snapshot: dropping the four rows a Fortran-faithful `modfrc <= 0` skip would
suppress leaves per-pollutant sums agreeing to **1.2e-8**, four orders inside
the 1e-2 gate; zeroing those same four cells does too; and moving mass between
model years leaves them agreeing to **2e-16** by construction. The loose
per-pollutant gate `moves.rs` uses across implementations would pass every
realistic failure this port can produce. Only the exact key set and the
per-cell check see them.
