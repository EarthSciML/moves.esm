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

### 1.3 The equi-join gate is a prerequisite, not an optimization

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

The performance envelope to aim at: a probe contracting 600,000 output cells —
the size of `emissionratebyage` — through gather-shaped access ran in 5.8 s in
a debug build. Cost proportional to matches, not to pairs, is what the gate
has to deliver.

### 1.4 Bulk data comes through `data_sources` — which needs a Parquet reader

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

### 1.5 CLI gaps

| Gap | Status |
|---|---|
| No `esm test` subcommand | **Being added by another agent**; will evaluate observed fields without an ODE solve. This plan depends on it and does not duplicate it. |
| `simulate` reports only *scalar* observeds | Open. Array observeds are absent from its JSON output, so an emission field cannot be compared row-by-row to a snapshot. `data_output.rs`'s `derive_output_plan` already builds the plan; the CLI never calls it. |
| Data sources off by default | `esio` is an opt-in Cargo feature — `esm simulate` silently loads no data unless built with it. |

Also: the checked-in `target/release/esm` in EarthSciAST is stale (Aug 11,
schema predating the `state`/`observed` → `unknown` rename). Build fresh.

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

**But it breaks the structural check, and that decides a modelling rule.** In
the binary64 run the four keys are *absent*, not zero — the Fortran skip
suppresses the row. Against `require_exact_key_set = true` that is a failure.
The resolution is not to loosen the check: it is that **the `.esm` must not
reproduce `modfrc <= 0` as row suppression.** A relational document emits every
key combination its joins produce and lets the value be whatever it computes;
the skip is Fortran control flow, not model semantics. Emit the row, emit the
zero, and the key set matches exactly while the sums gate passes at 2.6 × 10⁻⁶.

That is the happier answer — the legible form and the passing form are the same
form. Do not add a four-key allow-list.

---

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

1. **Build the equality-driven `join.on` gate** (§1.3.1) in
   `../EarthSciAST` — candidate set built once per node from the
   `relational.rs` kernel, gate drives enumeration, data-column keys admitted.
   Land it with conformance fixtures in the Julia and Python tracks so the
   determinism contract holds across bindings. **Everything numerical depends
   on this**; it is the critical path.
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

### Phase 1 — The representation spine

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

### Phase 3 — First onroad slice: `mixed-onroad` / `expand-day` (250 rows)

The rates-first base-rate path, which is what the pinned MOVES runtime actually
registers (`CriteriaRunningCalculator` is superseded and registers nothing):
`TotalActivityGenerator` → `SourceBinDistributionGenerator` →
`OperatingModeDistribution` → `BaseRateGenerator` → `BaseRateCalculator`
(`crates/moves-calculators/src/calculators/baseratecalculator/`), then output
aggregation. The adjustment sequence — temperature, humidity, fuel effects,
I/M, A/C, activity weighting — is where the Phase 1 templates pay off.

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

---

## 6. Immediate next steps

1. **Start the equi-join gate** (§1.3.1) in `../EarthSciAST` — the critical
   path. Candidate set from the `relational.rs` kernel, gate drives
   enumeration, data-column keys admitted, conformance fixtures in all three
   executing bindings.
2. Build `./esm` with `--features esio,parallel`; record the commit in
   `esm-version.lock`.
3. Write `run-tests.sh` with `validate` over `*.esm` — it passes trivially now
   and grows with the repo.
4. Add the EarthSciIO Parquet reader (§1.4), in parallel with step 1.
5. Author the Phase 1 spine and its scaling gate — the conventions can be
   written and unit-tested against `const` arrays before the gate lands.
