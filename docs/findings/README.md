# Findings: conventions the format or the toolchain could not express

Sixteen things PLAN.md §3 Phase 1 and Phase 2 assumed, or that an author would
reasonably assume, that did not hold. Four are now fixed upstream and are listed
at the bottom, with their sections kept above so the workarounds they forced can
be traced; the rest still hold at the pinned toolchain (`esm-version.lock`:
EarthSciAST `8a7810647`, EarthSciIO `d109951d4`, `--features esio,parallel`).

F2, F3, F5, F6 and F11–F14 each have a minimal `.esm` repro in this directory; F7 and F8 are
CLI behaviours rather than documents, and are checked by command against the
ordinary files of the repo. **Every repro is expected to fail**, and each one's inline test asserts the *intended* behaviour, so a repro
that starts passing means the defect is fixed. `run-tests.sh` runs them as a
**tripwire stage**: it fails if any repro goes green, with a message naming the
convention that then becomes available. That is the opposite of the usual
polarity and it is deliberate — a known limitation that quietly gets fixed is a
workaround left in the tree for no reason.

The repros are excluded from the ordinary `validate` and `test` stages, because
three of them do not load.

| | Finding | Fails at | Silent? |
|---|---|---|---|
| **F2** | A top-level `models` `{ref}` does not merge the referenced file's `index_sets` | validate | no |
| **F3** | An `enums` block does not cross an `expression_template_imports` edge | load | no |
| **F5** | `skolem` / `distinct` / `rank` value invention does not evaluate | — | **yes** |
| **F6** | A component with only scalar variables has no assertable state | assertion | no |
| **F7** | `esm round-trip` resolves a relative `ref` against the CWD | load | no |
| **F8** | A layered template library does not round-trip to a self-contained form | re-load | no |
| **F11** | A relation cannot be joined to itself: two ranges over one index set | build | no |
| **F12** | A recurrence over an index axis has no spelling | evaluation | no |
| **F13** | `enums` merge first-wins across a mount; a colliding value is applied | — | **yes** |
| **F14** | A `ragged` index set ignores its member factor | evaluation | **yes** |
| **F15** | A `url_template` is neither environment-expanded nor relative | ingest | no |

---

## F1 — a nested subsystem mount drops `join.on` key columns

`F1_subsystem_mount_drops_join_keys.esm` (with `join_leaf.esm`).

```
Compile failed: Unsupported feature 'value-equality join over data-derived
columns': join key column 'left_key' does not resolve to a loop index of this
aggregate ({"l", "r"})
```

The array runtime's mount renames each mounted variable to `<key>.<name>` and
rewrites `Expr::Variable` references to match, but a `join.on` key column is a
plain **string on the aggregate node**, not a child expression, so it is left
naming the old bare name. The scalar flatten path handles this
(`flatten.rs::namespace_join_names`, which exists precisely for it); the array
path — `simulate_array/compile.rs::mount_subsystems`, renaming through
`rename_free_symbol`, an `Expr::Variable` walker over `map_children` — has no
mirror of it.

`join_leaf.esm` on its own passes, which is what attributes the failure to the
mount.

**Impact.** Every relational leaf this project will write joins on data columns
(CONFORMANCE_SPEC §5.5.8 calls MOVES the motivating case), so under this defect
**no calculator can be mounted as a nested subsystem**. PLAN.md §3 Phase 1's
"mounted into a run-level assembly via §4.7 subsystem refs" is met by the
top-level `models` `{ref}` form instead — see docs/esm-conventions.md §5.

**Fix shape.** Mirror `namespace_join_names` in `mount_subsystems`: after
renaming a subsystem's variables, rewrite each `join.on` pair whose name is a
mounted sibling, leaving this node's own binders alone.

## F2 — a top-level `{ref}` does not merge `index_sets`

`F2_toplevel_ref_does_not_merge_index_sets.esm`.

```
Aggregate range references undeclared index set 'leaf_left'
```

esm-spec §4.7 "Index-set merge" requires it: *"A referenced subsystem file's
top-level `index_sets` merge into the importing document's document-scoped
registry at resolution time … This is what makes the mounted-mesh pattern
sound: the importing model's variables may be shaped over the mesh file's axes
without redeclaring them."* A **nested** `subsystems: {X: {ref}}` edge does
merge them; a **top-level** `models: {X: {ref}}` edge does not.

**Impact.** F1 and F2 are complementary, and together they mean an assembly
cannot both mount a relational leaf and inherit its axes. The assembly takes
the top-level form (the one that works) and restates the axes, and
`run-tests.sh` compares an assembly's `index_sets` against every file it refs —
the merge's conflict check, performed by the harness because the loader does
not perform it here.

## F3 — `enums` do not cross a template import

`F3_enums_do_not_cross_a_template_import.esm` (with `F3_lib_with_enum.esm`).

```
[unknown_enum] enum `activity_unit` is not declared in the file's `enums` block
```

esm-spec §9.3 says enums are file-local and "never merged across files", and
names one inheritance path — a §4.7 subsystem ref, which inherits the
*referenced* file's enums. A template import is not that path, and §9.7.5
merges only `index_sets` across it. So this is arguably conforming; what it
costs is not obvious from either section read alone.

**Impact.** A template library cannot name its own constants symbolically. Both
routes around it are in use here: `lib/conversion.esm` carries its activity-unit
codes as zero-parameter constant-fragment templates (§9.6.1), and
`lib/identifiers.esm`'s `pol_process_id` takes the identifier *values* as
parameters that a component binds to `enum` ops in its own scope. The library
half validates on its own, so the failure surfaces at the importer, naming an
enum the importer never mentioned.

## F4 — a loop symbol named `t` silently empties a join

`F4_loop_symbol_named_t_breaks_the_join.esm`. **The dangerous one.**

Two aggregates over the same data with the same join, differing only in the
name of the first loop symbol. `k` gives 2. `t` gives **0** — no error, no
warning, document validates.

`t` is the independent variable and the scoping walkers special-case it by name
(`flatten.rs::namespace_expr_scoped`, `scope_template_body`:
`if name == "t" || name == VAR_PLACEHOLDER || bound.contains(name)`), so a range
symbol that shadows it is not treated as a binder consistently and the key
column stops resolving to a loop index. With a `const`-array key column the same
collision surfaces as a misleading build error instead:

```
E_TREEWALK_CONSTARRAY_OOB: const array 'left_key' index 0 out of range 1..3
```

**Impact, and it was real.** The first draft of
`components/exhaust_adjustment.esm` named its time-key loop symbol `t` — the
natural choice for a time axis, in a project whose whole point is that MOVES
time is a *discrete key* rather than the continuous `t` — and the daytime hour
count came out 0 with everything else passing. This is exactly the failure mode
PLAN.md §1.3.2 records upstream having just fixed for build-time observeds
("an unfiltered full product, silently wrong"), reappearing through a different
door.

**Fix shape.** §5.5.8 already requires an unresolvable key column to be a
*build error* rather than a silent no-op. Extend that: reject a `ranges` key
named `t` (or `_var`) at load with a named diagnostic. Convention meanwhile:
docs/esm-conventions.md §7 — `t` is never a loop symbol.

## F5 — `skolem` / `distinct` / `rank` do not evaluate

`F5_skolem_distinct_does_not_materialize.esm`.

A `distinct` aggregate under `bool_and_or` with a `skolem` `key`, exposed as a
`kind: "derived"` index set via `from_faq`, validates — and materializes
**empty**. A contraction over the derived axis returns 0 instead of the 3
distinct pairs the input carries. Silent.

This is consistent with how EarthSciAST frames its own fixture:
`tests/valid/aggregate/skolem_distinct_rank.esm` says it *"validates against the
schema with no evaluator"* and carries no inline tests. The construct is
schema-level today.

**Impact on the brief.** PLAN.md §3 Phase 1 asks for "`skolem` for canonical
composite keys where a join is on a tuple". The convention is still met, in the
spelling CONFORMANCE_SPEC §5.5.8 actually mandates: a `join.on` clause listing
several key pairs over the same two loop symbols is **one composite key**, and
§5.5.8 states that *"the canonical composite key is the §5.5.1 rule-4 `skolem`
tuple of the per-pair values, in the order the pairs are listed"*. The skolem
tuple is what the gate builds; the author writes the pair list.
`components/deteriorated_emission_rate.esm`'s J14 is exactly that.

What is **not** available is an author-visible composite-key *axis* — a derived
index set whose members are the distinct tuples, which a rollup grouped by a
composite key would want. Phase 2 does not need one (its groupings are over
declared axes), but Phase 5's larger NONROAD sectors may.

## F6 — a scalar-only component has no assertable state

`F6_scalar_only_component_has_no_testable_state.esm`.

```
assertion evaluation failed: scalar state 'answer' not found
```

A component whose variables are all scalars and whose equations are all
algebraic has no state vector, so `esm test` cannot find its observeds.
Declaring one array-shaped variable anywhere in the same component makes the
identical scalar assertion pass — the model then takes the array runtime, which
materializes state-free observeds.

**Impact.** None on this repo: tables-stay-tables gives every MOVES component at
least one column array, so every component is already on the array path, and
PLAN.md §1.2's "components carry no clock" holds. It is recorded because it makes
the `D(clock) ~ 0` crutch PLAN.md §1.2 describes look necessary for the wrong
reason, and because it is a trap for anyone factoring a small pure-arithmetic
helper out of a calculator.

## F10 — the evaluable-core op `true` panics at evaluation

`F10_true_op_panics_at_eval.esm`. Found while authoring Phase 2's first stage.

```
$ ./esm validate docs/findings/F10_true_op_panics_at_eval.esm
✓ Validation passed
$ ./esm test docs/findings/F10_true_op_panics_at_eval.esm
thread 'main' panicked at src/simulate_array/eval.rs:340:18:
internal error: entered unreachable code: operator 'true' reached eval_op
without an evaluation rule; every entry point must gate with
check_evaluable() first
```

`true` is in the **closed** evaluable-core operator set — `esm-schema.json`'s
`op` description names it in the same breath as `ifelse` and `Pre`, and
esm-spec §4.2 says every binding's evaluator implements each member of that set
directly. The panic message is addressed to the implementor rather than the
author: it says an entry point failed to gate, which means `check_evaluable()`
does not list `true` even though the schema does. Exit code 101, no diagnostic.

**Impact: small, because the workaround is one character.** The natural body of
a semi-join under the `bool_and_or` semiring is `true` — *does a matching row
exist* — and the MOVES port needs semi-joins everywhere a most-specific-match
key is precomputed (the two SCC fallback ladders, state-default precedence, the
`getind.f` year rule, the RunSpec sector and fuel selections). Spelled with a
**numeric** body instead, `"semiring": "bool_and_or"` with `"expr": 1.0`, the
same aggregate evaluates correctly and yields 1 on a match and 0 on none. That
is the form every Phase 2 component uses. When this goes green they can say
`true` and read as what they are.

**Fix shape.** Add `true` to `check_evaluable()`'s accepted set and give
`eval_op` the one-line rule, or — if the intent is that `true` is structural
and never evaluated — remove it from the schema's evaluable-core enumeration so
`validate` rejects it. Either is fine; the present state, where the schema
promises an evaluator and the evaluator calls `unreachable!()`, is not.

## F11 — a relation cannot be joined to itself

`F11_a_relation_cannot_be_joined_to_itself.esm`. Found authoring Phase 2's
population stage.

```
Compile failed: Unsupported feature 'value-equality join over data-derived
columns': join key column 'r_priorID' does not resolve to a loop index of this
aggregate ({"b", "a"}): it names neither a range symbol, nor an index set one
of those ranges draws from, nor a declared 1-D data column over such an index
set (RFC semiring-faq-unified-ir §5.3)
```

Every clause of that message is in fact satisfied — `r_priorID` is a declared
1-D data column over `row_ax`, and `row_ax` is the index set both ranges draw
from. What fails is the resolution *strategy*: a key column is matched to a
loop symbol by its **axis**, so two symbols over one axis are ambiguous and
neither is chosen. A build error, not a silent zero, which is the right failure
mode.

**Impact.** Three joins in `docs/nonroad-logging-county.md` §3 are naturally
self-joins: J6 pairs `nrstatesurrogate`'s county row with the *state* row of
the same table; the growth series needs its own indicator at the previous year;
`scrptime`'s age walk needs the previous age's cumulative scrappage percent.
Each is worked around by materializing a **second relation over a second index
set** — `surrogate_target_rows` in `components/geographic_allocation.esm`,
`growth_factor_rows` beside `growth_query_rows` in
`components/growth_index.esm`, and in `components/age_distribution.esm` a
second contraction over the 197-point scrappage curve rather than a read of the
neighbouring row. The workarounds are legible enough that this is a cost, not a
blocker.

**Fix shape.** Resolve a key column to the range symbol whose body indexes it,
falling back to the axis rule only where that is unambiguous; or admit an
explicit `[symbol, column]` spelling in the pair, since the pair list is already
where the author says what joins to what.

## F12 — a recurrence over an index axis has no spelling

`F12_no_spelling_for_a_recurrence_over_an_index_axis.esm`. **The one that
stops a Phase 2 stage being computed rather than merely slowing it down.**

`s[1] = 1`, `s[k] = 2·s[k−1]`. Validates; then:

```
assertion evaluation failed: array state 's_value' has no cells in var_map
```

What exists is the **prefix (cumulative) reduction** of esm-spec §4.3.1 — an
`aggregate` whose `filter` compares monotonically against the output index,
folded ascending, bit-identical across bindings (CONFORMANCE_SPEC §495). That
covers every fold whose *terms* are independent of the result. It does not
cover one whose next term is a function of the previous *answer*. And the
closed semiring registry has no product-as-⊕ entry, so even a cumulative
**product** — a survival curve — has no prefix spelling. `Pre` (§5.1) is
defined against events on the time axis and needs a clock, which a MOVES
calculator does not have.

**Impact: `agedist.f`.** `docs/nonroad-logging-county.md` §2.2(e) grows a
51-slot age distribution from 1990 to 2020 by folding 30 years; each year's
vector is the previous year's shifted one slot and scrapped, **clamped at
zero**, with the newest slot written last as an unclamped residual. The clamp
is inside the fold, so the recurrence is not linear and there is no closed form
to substitute: `m0[y] = tpf(y) − Σₐ max(m0[y−a], 0)·R[a]`.

`components/age_distribution.esm` therefore computes everything `scrptime.f`
produces and carries `agedist.f`'s **result** as a data column, with the same
status as a `data_sources` column — the verified §6.1 step 3 values, checked
against the cumulative growth ratio `components/growth_index.esm` derives
independently from the index series. That cross-check is what keeps the carried
column honest.

Not used, deliberately: thirty near-identical equations, one per projected
year. It would run, and it would be the mechanically generated, unfactored
`.esm` CLAUDE.md forbids — and still wrong for any run with a different year
span.

**Fix shape.** Extend §4.3.1's prefix reduction to a fold whose body may read
the accumulator (`acc[i] = f(acc[i−1], body[i])`), which the ascending
left-fold order already licenses and which all three executing bindings already
maintain internally; or admit `Pre` on an index axis. Until then, no NONROAD
port can compute its own age distribution.

## F13 — `enums` merge first-wins across a mount, silently

`F13_enums_collide_across_a_mount.esm`, with `F13_enum_leaf_one.esm` and
`F13_enum_leaf_two.esm`. **The silent one of Phase 2.**

Two leaves each declare `probe.Symbol` — one says 1, the other 2 — and each
reads it back. Both pass alone. Mounted together, leaf two reads **1**: the
first declaration wins and the second file's reading of its own symbol changes
underneath it. `esm validate` is clean, and the only thing that notices is leaf
two's own inline test, which runs under the mount and fails.

Where the winner merely *lacks* a symbol, it is at least loud. Measured on two
real components — `geographic_allocation.esm` declares `nonroad_fuel_type`
without CNG or LPG, `fuel_properties.esm` declares the same name with them:

```
[unknown_enum_symbol] symbol `CompressedNaturalGas` is not declared under enum
`nonroad_fuel_type`
```

esm-spec §9.3 says an `enums` block is file-local and "never merged across
files", and names one inheritance path — a §4.7 subsystem ref, inheriting the
*referenced* file's block. This edge does neither: it merges, and the wrong
way. Third of a family with F2 (index sets do not merge here) and F3 (enums do
not cross a template import).

**Impact.** `runs/nr_logging_county_run.esm` restates twenty enums and
sixty-two symbols for ten leaves; `runs/micro_exhaust_run.esm` restates seven
for two. None are used by the assemblies' own equations. Because a value
collision is silent, `tools/check-conventions.py` now compares an assembly's
enums against every leaf it mounts, symbol by symbol **[checked]** — a missing
symbol or a disagreeing value is a violation.

**Fix shape.** Resolve each leaf's `enum` ops against its own block, per §9.3;
or, if a merged registry is intended, make a conflicting redeclaration a load
error the way §4.7 already treats a conflicting index set.

## F14 — a `ragged` index set ignores its member factor

`F14_ragged_index_set_ignores_its_member_factor.esm`.

A `kind: "ragged"` set declares `offsets` (per-parent length) and `values` (the
flattened CSR member array). It evaluates — and reads only `offsets`,
enumerating positions `1..offsets[i]` instead of parent *i*'s members. With
lengths `[1, 2, 3]` over the flat layout `[1 | 2, 3 | 4, 5, 6]`, the per-parent
sums come out `10, 30, 60` where the members give `10, 50, 150`. Three probes
pin it: changing `offsets` to `[1, 3, 6]` gives `10, 60, 210`; `[0, 1, 3]`
gives `0, 10, 60`; and **reversing `values` changes nothing**.

**Why this project cares.** The `nr-logging-county` key set is *ragged*: 36
`(SCC, modelYearID)` pairs over three SCCs whose model-year counts are 3, 4 and
29, each set by that equipment point's `nyrlif`. A rectangular
`[SCC × modelYear]` axis would emit 3 × 29 × 4 = **348** keys where the
snapshot has 144, and `tolerance.toml`'s `require_exact_key_set` is not
negotiable. A ragged inner axis is exactly the shape the schema advertises.

**Workaround, and a good one.** Keep the output a **flat row relation** whose
parent is a key *column* — `(SCC, modelYearID, polProcessID)` over one row axis
— and join on it. Raggedness then needs no axis machinery, because a relation's
key set is data (conventions §2). `components/movesoutput_aggregation.esm` is
written that way, so this costs the port only the axis it cannot use.

**Fix shape.** Read `values`: `member(i, k) = values[offset(i) + k]` with
`offset` the exclusive prefix sum of `offsets`. The RFC's own MPAS example has
the same requirement — cell *i*'s edges are not the first `nEdgesOnCell[i]`
entries of `edgesOnCell`.

## F7 — `esm round-trip` resolves refs against the working directory

No repro file; the whole repo is the repro.

```
$ ./esm validate components/deteriorated_emission_rate.esm
✓ Validation passed
$ ./esm round-trip components/deteriorated_emission_rate.esm
Round 1: Load failed: [template_import_unresolved] template-library file not
found or unreadable: .../.moves/lib/emission_factors.esm
                             ^^^^^^ — the CWD's parent, not the file's
$ (cd components && ../esm round-trip deteriorated_emission_rate.esm)
✓ Round-trip fidelity maintained
```

esm-spec §4.7 fixes the rule for both mechanisms: *"Relative path … Resolved
relative to the directory of the referencing file"*, and §9.7.2 says
`expression_template_imports` reuses "§4.7's reference formats and
resolution-timing rule, verbatim". `validate` and `test` implement it;
`round-trip` resolves against the process working directory instead. It affects
every document here with a relative `ref` — both components, the assembly, and
`lib/keys.esm`.

**Impact.** Cosmetic but load-bearing for the harness: `run-tests.sh`'s
round-trip stage `cd`s into each document's directory. Remove that when this is
fixed.

## F8 — a layered template library does not round-trip

No repro file; `lib/keys.esm` is the repro.

```
$ (cd lib && ../esm round-trip keys.esm)
Error: [apply_expression_template_unknown_template]
  document.expression_templates.scc_equipment_chain_key: body references
  undeclared template 'scc_zero_tail' (esm-spec §9.7.3)
```

`lib/keys.esm` imports `scc_zero_tail` from `lib/identifiers.esm` and invokes it
from inside two template bodies. On emit, the import EDGE is consumed —
correctly, §9.7.6 says `expression_template_imports` "is a call site … and does
**not** survive `parse → emit`" — but the imported DECLARATION is dropped too,
so the emitted document references a template it does not declare and cannot be
re-loaded.

§9.7.6 states the intended split in the same paragraph: *"The import EDGE is
expanded away; the DECLARATIONS survive"*, and §9.6.4 rule 5 is explicit about
this exact case: *"a library that imports round-trips to its self-contained
form, which is import-free and round-trips to itself."* The emitted form is
import-free but not self-contained.

```
$ (cd lib && ../esm convert keys.esm --to compact-json) | jq '.expression_templates | keys'
["scc_equipment_chain_key", "scc_lookup_ladder_key", "state_default_precedence"]   # scc_zero_tail is gone
```

**Impact.** Nothing at authoring time — `validate` and `test` both handle
`lib/keys.esm` correctly, and cross-file layering is the convention
(docs/esm-conventions.md §6). It matters for any tool that reads an emitted
document rather than the source, which is what §9.6.4's Option B round-trip
model exists to make safe. `run-tests.sh` excludes `lib/keys.esm` from its
round-trip stage and watches this by command instead.


---

## F9 — a relational document evaluates, but cannot be written to a file

**Fixed upstream — see the list at the bottom. Kept for the record.**

`F9_no_emit_path_for_a_relational_document.esm`, now removed.

**Blocked the Phase 2 exit criterion, independently of the data provider.**

A MOVES calculator is a *relational* document: it computes rows from rows and
integrates nothing. Both `components/*.esm` already have this shape — 0 of 11
and 0 of 15 equations carry a `D()` — and every Phase 2 stage will too.

`esm test` evaluates such a document correctly; this repro's own inline
assertion **passes**. But `esm test` only asserts, and prints an actual value
only on failure. The only subcommand that writes computed values to a file is
`esm simulate --output`, and on a document with no ODE it fails:

```
Error: "solve failed: diffsol error: ODE solver error:
        Exceeded maximum number of nonlinear solver failures (51) at time = 0"
```

Reproduced on both real components at `--time 0` and `--time 1` alike.
`analyze` and `info` report structure, not values.

So there is no route from a computed row set to `compare-output.py`, and the
144-row comparison cannot run whatever happens with ingest.

**On PLAN.md §1.5.** That table records the array-output gap as closed by
`simulate --observed` plus `--format grid` (EarthSciAST `a784c5444`). The
closure is real, and it was verified — but on a document that *simulates*. It
does not reach one that has nothing to integrate. The gap was closed for
gridded PDE output and the relational case was never on the other side of it.

**Fix shape.** Either let `simulate` treat an ODE-free document as a single
evaluation at `t = 0` rather than a solve, or give `esm test` (or a new
subcommand) an `--output` writing the same `derive_output_plan` shape
`--format grid` already produces. The second looks cleaner: evaluation without
a solve is exactly what `esm test` already does, so it is a new sink on an
existing path rather than a new mode on the solver.

**Polarity.** Unlike F1–F6, this repro's assertion passed. Its tripwire in
`run-tests.sh` was therefore the `simulate` command, checked in both directions:
the document had to still evaluate, and to still fail to emit. It is the
direction that fired — `simulate` began writing the file — which is how the
fixture stage came to exist.

## F15 — a `url_template` has no portable form

No repro file; `fixtures/nr-logging-county.esm` is the repro, and
`run-tests.sh`'s fixture stage checks it by command in the direction that
matters — the checked-in document must **fail** to ingest.

A `data_sources` entry names its input with `source.url_template`. The runtime
requires an explicit scheme (a bare path is `bad url … missing scheme`), and
then takes the URL literally: nothing expands an environment variable, and
nothing resolves the path against the referencing document's directory the way
esm-spec §4.7 does for a `ref`. All three portable spellings fail, and the
error message shows why — the first path segment is consumed as the URL
**host**:

```
file://${MOVES_SNAPSHOTS}/…/nrscc.parquet   io error at /…/nrscc.parquet
file://../../../moves.rs/…/nrscc.parquet    io error at /../../moves.rs/…/nrscc.parquet
file://./probe.parquet                      io error at /probe.parquet
```

Only `file:///absolute/path` reads. So a document whose data lives outside its
own repository — which is every fixture here, since the snapshots are a sibling
checkout — **cannot name its own inputs**.

**Impact.** `run-tests.sh` materializes each fixture into an untracked
`.fixtures-run/` copy with one `sed` over the snapshot path. That is a
substitution of a *path*, not a generation of model logic, and it is the reason
`fixtures/` is excluded from the ordinary `esm test` stage: the checked-in
document deliberately does not ingest, so its inline assertions mean nothing
until it is materialized. The cost is that the file the repository reviews and
the file the toolchain runs are not byte-identical, which is exactly what the
round-trip stage exists to avoid elsewhere.

**Fix shape.** Expand `${VAR}` from the process environment — `url_template` is
already called a template and already carries `{date:…}`-style substitutions —
or resolve a relative path against the referencing document's directory, per
§4.7's rule for every other reference in the format. Either removes the
materialization step; the first also lets one catalog serve several machines.


---

## Fixed upstream

Retired from the tripwire; the repros are gone because the fixing commits carry
their own regression tests. Kept here so the workarounds they forced can be
traced.

- **F1** — EarthSciAST `a5e8a7d94` — `rename_free_symbol` now rewrites `join.on`, `overlap.src_env`/`tgt_env` and a resolved `on_gate`'s columns after `map_children`, so a nested §4.7 mount carries a leaf's key columns. **The nested mount is available again**; this port's assemblies still use the top-level `{ref}` form the workaround forced, which works and is not worth churning, but a new assembly may use either.
- **F4** — EarthSciAST `ee067f5b6` — rejected at load with a named diagnostic, `reserved_index_symbol`, rather than made to work: an index symbol is the author's free choice (§4.3.1), while making the binder win would invert name-first precedence at nine sites and still leave the node unable to name the independent variable at all. The convention in `docs/esm-conventions.md` §7 stands, now enforced by the toolchain.
- **F9** — EarthSciAST `8274f0918` — `simulate` treats a document with nothing to
  integrate as a single evaluation at `t = 0` (`Compile::Always` became
  `Compile::Auto`) instead of handing it to the ODE solver, and `--format csv`
  writes the row set itself: a leading `i1` ordinal column, then one column per
  `--observed` field, with a request whose fields do not share one shape REFUSED
  rather than padded or truncated. **This is the commit that opened the fixture
  stage** — together with EarthSciAST `72568e8bc`/`8dd7789ef`, which wire the
  `data_sources` ingest bridge into the binary and sample a source's `extent`
  before the document closes its metaparameters. `fixtures/` uses all three.
  The `.esm` repro is gone; its tripwire in `run-tests.sh` was the `simulate`
  command and is gone with it.
- **F10** — EarthSciAST `a1a592ecf` — `true` evaluates to 1.0, matching Python, Julia and Rust's own value-invention path; Rust's dense path was the outlier. The other nine core-but-unevaluable ops are now refused at build instead of reaching `unreachable!()`. Confirmed a class, not a case: `rank` panicked the same way.
