# Findings: conventions the format or the toolchain could not express

Twenty-nine things PLAN.md §3 Phase 1 through Phase 5 assumed, or that an author would
reasonably assume, that did not hold. **Fifteen are fixed upstream and retired**
from the tripwire, listed at the bottom with their sections kept above so the
workarounds they forced can be traced. The rest still hold at the pinned
toolchain (`esm-version.lock`: EarthSciAST `9e282da40`, EarthSciIO
`d109951d4`, `--features esio,parallel`).

F2, F3, F5, F13, F14, F20, F21, F22, F28 and F32 each have a minimal `.esm` repro in this
directory — F22 has two, one per construct; F8 is a CLI behaviour rather than a
document, and is checked by command against the ordinary files of the repo.
**F17, F31 and F33 deliberately have no repro file**: a repro
for any of them would assert the RIGHT answer and pass, and the tripwire stage
below reads a passing file in this directory as "the defect is fixed". F17 and
F31 were cost findings, where the right answer arrives too slowly rather than
wrong; F33 is about bindings this repository does not execute, so its repro
would pass on `./esm` for a reason that has nothing to do with the defect. Each
was reproduced inline in its own section instead, with the measurements that
made it a finding. F17 and F31 are now fixed upstream and retired — and F17 turned out not to be
a cost finding at all, which is why the rule that a performance repro cannot be
a tripwire is worth keeping even though both of its instances are gone: the
thing that had no repro was hiding a WRONG ANSWER, and only a document that
reordered its own join clauses would have found it. F23 has no repro at all, because the document that would carry it is `components/age_distribution.esm` itself and the finding is what that file does NOT declare. **Every repro is expected to fail**, and each one's inline test asserts the *intended* behaviour, so a repro
that starts passing means the defect is fixed. `run-tests.sh` runs them as a
**tripwire stage**: it fails if any repro goes green, with a message naming the
convention that then becomes available. That is the opposite of the usual
polarity and it is deliberate — a known limitation that quietly gets fixed is a
workaround left in the tree for no reason.

Three files are excluded from that loop by name. **`join_leaf.esm`** is a leaf
that two repros mount and that passes standalone, which is what makes their
failures attributable to the mount — F21 reuses it rather than adding a fourth
leaf, so that finding needed no change to `run-tests.sh`. **F18's control** is
meant to pass, and checks the guarantee the port depends on from both sides: the
key-collapse half of F18 is resolved by a per-variable `element_type` override
that is explicit by design, so the behaviour its old repro asserted will never
hold and "still fails, as recorded" would have been false reassurance.

**F24b's control** is the third, and it covers something nothing upstream could.
F24 was fixed in a build with **no parquet reader**, so the *ingestion* axis was
never verified there — the author said so rather than claiming it. F24b is that
verification: one ingested column wide, reading the real snapshot, 5/5. It
asserts the **clamped** column rather than the plain one, because an unresolved
self-read came back `NaN` and `max(NaN, 0.0)` returns `0.0`, so a check on the
plain column would go green the day the sentinel changed without the construct
working. Its twin F24a is gone — the cross-route agreement it checked is now
pinned upstream by ten tests that re-materialize every recurrence fixture
through the pipeline and compare on bits.

**F25's repro is the fourth file the tripwire loop does not run**, and F26's is
the fifth; both are excluded because their documents are *meant* to be invalid. `esm validate`
rejects it and always will; the defect is that `esm test` does not, on one
evaluation path. So "both stages pass" can never fire, and the loop would report
"still fails, as recorded" forever without noticing a fix. `run-tests.sh` checks
which of the two answers `esm test` gives instead — the dropped operand
(`actual=2 expected=10`) or the variable's name — and that check is
falsified in both directions. **F26 is watched the same way** and for the same
reason, on `esm validate` (where the refusal belongs) and `esm simulate` (where
the silence is).

There is a pattern in that pair worth naming, because a third instance would
make it a rule: both are **undefined names that only the SCALAR path notices**,
and every ingesting document takes the other one. F25 is an undeclared operand
dropped; F26 is an index symbol left free outside its aggregate, read as
position zero. Neither is refused at load, which is where both belong.

**F28's control is the fifth file the tripwire loop does not run**, and like F18's and F24b's it is meant to pass. F28 is a shape the format refuses; its control is the WORKAROUND that shape has to be rewritten into, and everything this repository can say about porting `TankTemperatureGenerator` TTG-4 rests on that workaround existing. It is checked rather than assumed, and it is two-sided by construction: with a constant lag of 1 in place of the contracted one, rows 4, 5 and 6 read 8, 16 and 32 where the chain says 4, 8 and 8, and three of its six assertions fail.

F12's control is **gone**. It was kept until `components/age_distribution.esm`
computed `agedist.f`'s fold and guarded it with its own assertions; it does, in
55 places, so the control had nothing left to notice.

There used to be another inverted check, F19's, whose repro *passed* and whose
passing was the defect. It is fixed, so that check is gone.

The repros are excluded from the ordinary `validate` and `test` stages, because
three of them do not load.

| | Finding | Fails at | Silent? |
|---|---|---|---|
| **F2** | A top-level `models` `{ref}` does not merge the referenced file's `index_sets` | validate | no |
| **F3** | An `enums` block does not cross an `expression_template_imports` edge | load | no |
| **F5** | `skolem` / `distinct` / `rank` value invention does not evaluate | — | **yes** |
| **F8** | A layered template library does not round-trip to a self-contained form | re-load | no |
| **F13** | `enums` merge first-wins across a mount; a colliding value is applied | — | **yes** |
| **F14** | A `ragged` index set ignores its member factor | evaluation | **yes** |
| **F16** | A SCALAR variable is not materialized in a document that ingests data — **fixed in Rust**; open because Julia and Python still resolve a pointwise assertion against state rows (`BEHAV-06-B-008`) | assertion | no |
| **F18** | An ingested value the declared `element_type` cannot represent is narrowed silently (the key-collapse half is **resolved**, by a per-variable override) | ingest | **yes** |
| **F23** | A leaf's `domain.element_type` does not survive a top-level `models` `{ref}` mount | — | **yes** |
| **F22** | A discrete event, and an implicit equation, do not evaluate on the ARRAY path (both work on the scalar path) | evaluation | no |
| **F20** | A constant-folded scalar right-hand side loses the left-hand side's array shape | assertion | no |
| **F21** | A scoped reference to a mounted model's variable resolves as an operand and a join key but not as an assertion `variable` | assertion | no |
| **F28** | A recurrence whose predecessor is named by a DATA COLUMN has no direct spelling; the lag must be an offset of the frame symbol | validate + test | no |
| **F32** | An `enums` member cannot be ZERO; the schema requires a positive integer, and MOVES's Braking operating mode is 0 | validate | no |
| **F33** | A `Float32` document's relational path is evaluated in binary64 by Julia and Python, with no diagnostic — §5.18 is normative and unimplemented | evaluation | no |

---

## F26 — an index symbol left free outside its `aggregate` is dropped

`F26_repro_a_free_index_symbol_is_dropped_on_the_array_path.esm`.

esm-spec §4.3.1 binds an index symbol **inside** the `aggregate` that declares
it — in that node's `output_idx`, its `ranges` keys and its `expr` — and says
that a bare string is a variable reference everywhere else. So

```jsonc
{ "op": "+", "args": [
    { "op": "aggregate", "output_idx": ["i"], "ranges": {"i": {"from": "rows"}},
      "expr": {"op": "index", "args": ["a", "i"]} },
    { "op": "index", "args": ["a", "i"] } ] }   // <- `i` is free here
```

names a variable `i` that does not exist and should be refused at load with an
undefined-name diagnostic. It is not:

```
$ ./esm validate docs/findings/F26_repro_a_free_index_symbol_is_dropped_on_the_array_path.esm
✓ Validation passed
$ ./esm test  …                 # tree walk
E_TREEWALK_CONSTARRAY_OOB: const array 'a' index 0 out of range 1..4 in dim 0
$ ./esm simulate … --observed b # array path
b[1] = 10   b[2] = 20   b[3] = 30   b[4] = 40
```

`b` is `a[i] + a[i]` and should be `[20, 40, 60, 80]`; the control `c`, the same
arithmetic with both terms inside the aggregate, is. On the array path the free
term contributes the additive identity and `b` comes back as `a`, with no
diagnostic. The tree walk's message is the useful one, and it says what
happened: the index was read as **zero**.

**Why this project cares, and it is not hypothetical.** The array path is the
one every ingesting document takes, for `esm test` as much as for `esm
simulate` — the same split F25 records. Hoisting `nrdeterioration`'s join off
the cohort axis in `fixtures/nr-logging-county.esm` was first written with the
missing-row default (`+ (1 - det_isPresent[q, cc])`) outside its aggregate.
`esm validate` passed, `esm test` passed **343 of 343** assertions, and 109 of
the 144 output cells were wrong: the deterioration exponent came out 2 where
the table says 1, because the correction term evaluated to 1 everywhere instead
of 0. Every wrong cell was a plausible number, and none of the 343 assertions
happened to cover a technology whose exponent had moved. What caught it was
diffing the emitted rows against the previous run — not a gate, and not
something anyone should have to rely on. The document now does the defaulting
inside the aggregate, where `q` and `cc` are bound.

**Fix shape.** The undefined-name walk of esm-spec §9.7.5 already exists; it is
the *binder set* that is wrong here. A node's loop symbols are node-local
(CONFORMANCE_SPEC §5.5.6 says so, normatively, for `join` key columns), so a
symbol that is not bound by the node it appears in, nor by any enclosing
`aggregate`, nor declared as a variable, resolves nowhere and should be
rejected — the same conclusion §9.7.5 reaches for every other reference.


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

## F6 — a scalar-only component has no assertable state — **fixed**

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

## F11 — a relation cannot be joined to itself — **fixed**

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

## F12 — a recurrence over an index axis has no spelling — **fixed**

Four repros, one missing feature: `F12_no_spelling_for_a_recurrence_over_an_index_axis.esm`
(an `aggregate`), `F12b_recurrence_via_a_makearray_region.esm`,
`F12c_recurrence_via_a_discrete_event.esm` and
`F12d_recurrence_as_an_implicit_equation.esm`. All four ask for `s[1] = 1`,
`s[k] = 2·s[k−1]`, answer `[1, 2, 4, 8]`. **The one that stops a Phase 2 stage
being computed rather than merely slowing it down.**

The `aggregate` spelling validates and then says so:

```
assertion evaluation failed: array state 's_value' has no cells in var_map
```

The other three do not say so. `makearray` fails identically, which is what
attributes the limitation to self-reference rather than to `aggregate`. The
event and implicit spellings **complete and return a wrong answer** — see their
own descriptions; both are recorded here because each is the next thing an
author reaches for and each fails silently on the array path.

**What exists.** The **prefix (cumulative) reduction** of esm-spec §4.3.1 — an
`aggregate` whose `filter` compares monotonically against the output index,
folded ascending, bit-identical across bindings (CONFORMANCE_SPEC §495). It
covers every fold whose *terms* are independent of the result. It does not cover
one whose next term is a function of the previous *answer*.

**Correction to an earlier version of this entry.** It said that "the closed
semiring registry has no product-as-addition entry, so even a cumulative
product — a survival curve — has no prefix-scan spelling". That is wrong, and it
mattered, because it wrote off the one piece of `agedist.f` that *is* spellable
today. The closed `semiring` registry indeed has no product-as-⊕ entry, but
`reduce` is a separate field whose enum is `["+", "*", "max", "min"]`
(esm-schema.json; CONFORMANCE_SPEC §5.6.2 fixes its empty-reduction identity at
`1`), and `reduce: "*"` under a `filter` of `j <= i` is a cumulative product.
Measured on the pinned CLI: `s = [2,3,4,5,6]` gives `[2, 6, 24, 120, 720]`, and
it is the **ascending left fold to the last bit** — `0.7015463661686019 ×
1.771150605405849 × 1.645661928464921` returns `2.0448078014798643`, the
left-associated value, not the `2.044807801479864` of any other association.
A **banded** product also works, `prod(S[j], a−y < j <= a)` as one aggregate
over two output indices, which is the windowed survival factor `agedist.f`
needs. §495's cross-binding bit-identity is stated in terms of the *filter*
shape rather than the semiring, so the plain `j <= i` product is covered by it;
the banded one, being a conjunction, is not, and is governed by the §5.9
simulation tolerance like any other contraction. Both evaluate, and both give
the right value here.

**Impact: `agedist.f`.** `docs/nonroad-logging-county.md` §2.2(e) grows a
51-slot age distribution from 1990 to 2020 by folding 30 years; each year's
vector is the previous year's shifted one slot and scrapped, **clamped at zero**,
with the newest slot written last as an unclamped residual. The clamp is inside
the fold, so the recurrence is not linear.

### The fold does reduce — and the reduction does not remove the recurrence

`tools/verify-agedist-reduction.py` tests, against §6.5's own script, a closed
form that rests on one property of the inputs: `1 − yy[ia] >= 0` at every slot
of every equipment point (measured: `max(yy)` is `1.0` exactly, and `0.99999994`
for SCC 2260007005). Because a non-negative cohort times a non-negative
survival stays non-negative, and slots 1..50 are themselves a `max(·, 0)`, a
negative can only ever ENTER at the initial vector or at the unclamped residual
`md[0]`. So the clamp bites **at most once** along any chain — at the step where
a negative first meets it — and the chain is identically zero thereafter.
Tracing slot `ia` back `ia` steps therefore lands on a residual, or on the
initial vector when `ia > y`:

```
md_y[ia] = max(r_{y−ia},  0) · Π(1−yy[k], k = 1..ia)         ia <= y
md_y[ia] = max(mf0[ia−y], 0) · Π(1−yy[k], k = ia−y+1..ia)    ia >  y
r_y      = tpf_y − Σ(md_y[ia], ia = 1..50)
```

**It holds.** All six equipment points (3 SCCs), all 31 years × 51 slots, in
float32: **0 of 1581 cells differ** per point. 73 cells differ only in the sign
of a zero, which no summation and no `<= 0` test can distinguish — the fold
produces `−0.0` there only because `max(−0.0, +0.0)` returns its first argument.
The clamp is load-bearing, so this is not a vacuous agreement: it alters 19, 19
and 35 values on the three `2265007010` points, at slot 1 and at slots 9–37, and
the residual goes negative in 8, 8 and 12 of the 30 years.

**And it does not help enough.** Substituting the residual equation into itself
gives a scalar recurrence on 31 numbers,

```
r_y = b_y − Σ(max(r_{y−a}, 0) · P[a],  a = 1..min(y,50)),   P[a] = Π(1−yy[k], k<=a)
```

where `b_y` is `tpf_y` less the initial vector's contribution and is computable
with no fold at all. Every ingredient except `r` is now spellable today: `P` is
a prefix product, the windowed factor is a banded product, `tpf` is a cumulative
product of `(1 + growth factor)`. What remains is still a recurrence — `r_y`
reads `r_{y−1}` because `P[1] = 1 − yy[1]` is not zero — and the prefix
reduction reaches a **convolution**, not the **deconvolution** that solving for
`r` is. Nor can the order be lowered: the per-lag weights `P[a]` differ, so no
scalar state summarises the history, and the minimal state genuinely is the age
distribution. The reduction re-expresses that state as a *scalar sequence* at
the cost of an order-50 dependence; it does not remove it.

The lags do fall away where `1 − yy` reaches exactly zero, which it does at
slot `nyrlif − 1`, so `P[a]` is non-zero only for `a < nyrlif − 1`: 19, 19, 37,
1 and 3 lags on five of this fixture's six equipment points. On the sixth, SCC
2260007005, the last survival is `5.96 × 10⁻⁸` rather than exactly zero, so all
50 lags carry weight. Either way `S[1]` is non-zero on every point — `0.265`,
`0.985`, `0.995`, `0.19999999`, `0.865` — so `r_y` always reads `r_{y−1}`. A
smaller order is not a different shape.

The unclamped system does have one closed form: it is `(I + L)·r = b` with `L`
strictly lower triangular, hence nilpotent, so the Neumann series
`r = Σ(−L)^k b` terminates at `k = 30`, term `k` being a `k`-fold contraction. Spelling it means up to thirty nested `aggregate`
nodes written out by hand — the generated, unfactored `.esm` CLAUDE.md forbids,
under a different name — and it is valid only where the clamp does not fire,
which on this fixture is not where it matters.

**Doors checked and closed.** `Pre` (§5.1): unavailable, not merely
inconvenient. F12 previously ruled it out because a MOVES calculator carries no
clock (PLAN.md §1.2); the binding reason is that the Rust **array** backend
drops `discrete_events` silently (F12c) and refuses a `parameter` with an
`expression` update loudly, and every relational component takes the array path
(docs/esm-conventions.md §2). Adopting a clock would not unblock this.
`makearray` regions: no (F12b). An implicit residual equation: not solved, and
would have been the wrong shape anyway (F12d). Template recursion: forbidden by
esm-spec, `MAX_TEMPLATE_EXPANSION_DEPTH = 32`. Thirty hand-written year blocks:
the mechanically generated, unfactored `.esm` CLAUDE.md forbids, and still wrong
for any run whose year span differs — the longest-lived equipment point of *this*
fixture spans 39 model years, more than the 30 years the fold runs for, so even
here the year count and the slot count are different numbers.

So `components/age_distribution.esm` still computes everything `scrptime.f`
produces and carries `agedist.f`'s **result** as a data column, with the same
status as a `data_sources` column — the verified §6.1 step 3 values, checked
against the cumulative growth ratio `components/growth_index.esm` derives
independently from the index series. That cross-check is what keeps the carried
column honest, and it is why the column carries one equipment point's three
values rather than every cohort of all six (3, 21, 21, 39, 3 and 5 of them, for
the 36 `(SCC, modelYearID)` pairs the output spans): the other cohorts' values
appear in no §6 table and in no snapshot table, so transcribing them would make
the comparison circular.

**Fix shape, sharpened.** A **causal self-reference along one index axis**: an
array-producing node whose body may read the array being defined at a *strictly
earlier* position on one declared axis, evaluated in ascending order on that
axis. Three notes on the shape, each of which the reduction above is what
settles:

1. `acc[i] = f(acc[i−1], body[i])` — the fix shape this entry used to propose —
   is **too narrow**. `agedist.f`'s residual needs `r` at `i − a` for `a` up to
   `nyrlif − 1`, so the body must be able to address any earlier position, not
   only the immediately preceding one.
2. It need not be array-valued. Without the reduction the accumulator is the
   51-slot vector, which is a larger addition; with it, a **scalar** self-
   reference over a 31-element axis suffices, which is exactly what F12's own
   repro asks for and what the existing forward-scan machinery's ascending
   accumulator already licenses (CONFORMANCE_SPEC §495: all three executing
   bindings maintain that accumulator internally — it is simply not addressable
   from the body).
3. The **order** of the arithmetic has to be the fold's, not the closed form's.
   Measured: spelling a cell as `max(r,0) × P[ia]` — the clamped base times a
   *precomputed* product — instead of applying the survivals one at a time to
   the running cohort moves values by up to **9.7 × 10⁻⁶** relative, which is
   the whole error budget of a fixture whose worst row is 4.9 × 10⁻⁶. No sign
   flips on this fixture, so no model year is gained or lost, but the margin is
   gone. A conforming spelling is available — one `reduce: "*"` aggregate whose
   lowest admitted term is the clamped base and whose remaining terms are the
   survivals, since the fold is ascending — and it is a constraint on the
   primitive, not an afterthought.

Until one of these lands, no NONROAD port can compute its own age distribution.

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

## F7 — `esm round-trip` resolves refs against the working directory — **fixed, and it was ~17 subcommands**

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

## F15 — a `url_template` has no portable form — **fixed**

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


## F16 — a scalar has no state in a document that ingests — **fixed (Rust)**

No repro file, for a reason given below; the measurement is a pair of documents
that differ in one thing.

```jsonc
// control: col = const [10, 20, 30];  total = Σ col[i]
{"lhs": "total", "rhs": {"op": "aggregate", "output_idx": [], "ranges": {"i": {"from": "rows"}},
                         "expr": {"op": "index", "args": ["col", "i"]}}}
```

```
$ ./esm test scalar_const.esm      # col from a const array
  TOTAL   1 pass

$ ./esm test scalar_data.esm       # col from `update.kind: data`, everything else identical
  assertion evaluation failed: scalar state 'total' not found
```

Both documents declare one array variable and one scalar; F6 says the array is
what puts the model on the runtime that materializes state-free observeds, and
in the `const` document it does. Bind that same column to a `data_sources`
entry and the scalar stops existing — the array reads correctly, and every
scalar derived from it is gone. It is loud (an ERROR naming the variable), and
it is not confined to assertions: an expression that READS such a scalar
evaluates to `NaN`, which is how it first surfaced here — four adjustment
factors came out NaN because the two scalars they multiply had no value, while
every array in the same document was right.

**Impact, and the convention it forces.** `fixtures/nr-logging-county.esm`
carries **every** run-level quantity as a one-row relation over `run_rows`
rather than as a scalar: the ambient temperature, the oxygen weight percent,
the fuel year, the days in the month, `adjtime`. That is a better shape anyway
— tables stay tables (conventions §2), and a second SCC turns `run_rows` into a
two-row relation with no equation change — but it is not a free choice here,
and a component moved from the `const` level to the fixture level has to be
rewritten for it. Note the asymmetry with F6: F6 says a scalar needs an array
in the document to be assertable, and this says an *ingested* array is not
enough.

**Why no repro file.** A repro needs a real data source, a data source needs an
absolute path (F15), and an absolute path checked into `docs/findings/` would
make the repro fail on any other machine — for the wrong reason, which is
exactly what the tripwire's positive controls exist to prevent. It is recorded
here with its measurement instead, and the fixture is the standing evidence:
every one-row relation in it would be a scalar if this were fixed.

**Fix shape.** Whatever `prepare` does for a data-fed document, it drops the
scalar observeds that the `const` path keeps. The two paths should agree, and
the `const` one is right.


## F17 — a `join.on` between two large relations is not driven — **fixed**

No repro file; `fixtures/nr-logging-county.esm` is the repro, and its history is
the measurement. **Silent, in the way that matters least often and costs most:
the answer is right and the run does not end.**

The first form of the fixture's roll-up was one contraction over three data
relations — `nrengtechfraction` (9,554 rows), `nremissionrate` (55,471) and
`nrdeterioration` (424) — under `join.on` clauses that reduce it to about 72
surviving tuples: the mix rows the equipment chain and the cohort's mix year
select, then one rate row and one deterioration row per (pollutant process,
technology). It did not finish in twenty-five minutes of wall clock. That
number is on a shared machine and is not the measurement; the measurement is a
bisection run back to back, one clause apart, on the same document, the same
data and the same load:

| contraction | time |
|---|---|
| mix only (`age_rows` × `pol` × mix, joined to two small relations) | **3 s** |
| … plus the join to `nremissionrate` on (SCC, polProcessID, engTechID) | **> 120 s**, killed |

Splitting the composite `on` list into one clause per relation *pair* — which
is the right spelling anyway, since its three key pairs related three different
relations and not one composite key — changed nothing. What the two cases
differ in is the SIZE OF BOTH SIDES: in the fast one every key column on the
left of a clause lives on a 1-, 3- or 4-row relation, and in the slow one
`mix_engTechID` is a column of a 9,554-row table probing a 55,471-row one.

**The fix is in the document and it is a better document.** Give the technology
its own axis — `engine_tech_rows`, the exhaust code space 100–199 that §5.5
enumerates — and each of the three tables joins to it separately: the mix
becomes `tech_fraction[cohort, tech]`, the rates `tech_meanBaseRate[pollutant,
tech]`, the coefficients `tech_deteriorationFactor[cohort, pollutant, tech]`,
and the roll-up contracts over 100 technologies instead of over a product of
three tables. **4 seconds**, same answer. `tech_fractionTotal` is the assertion
that keeps the window honest: the mix must sum to 1 for every cohort, so a code
outside 100–199 would show up as a number less than 1 rather than as a missing
row.

**Why this is worth recording rather than filing under "we wrote it better".**
The scaling gate in `gates/` asserts that a `join.on` contraction costs
O(matches) and not O(N·M), and it passes — because its driven side is small.
The gate's claim is therefore narrower than it reads, and this is the case it
does not cover. Every larger NONROAD fixture joins big tables to big tables.

**Fix shape.** Build the hash index on whichever side of a clause is smaller
rather than on a fixed one, and choose a join ORDER over the clause set instead
of taking them as written. A second gate document, contracting two large
relations, would pin it.

### The remainder, measured: only the FIRST clause drives, and which one it is costs 47×

The "gate selection" half above is no longer a suspicion. `docs/esm-conventions.md`
§12 recorded one, honestly hedged — that `tech_fraction`'s `tech_engTechID ↔
mix_engTechID` join "does not appear to drive over the 100-wide technology
axis". It does not, and here is why and by how much.

**Cause, read off the reference.** `resolve_join_gate`
(`pkg/earthsci-ast-rs/src/simulate_array/eval.rs`) walks the node's `join` list
and `return`s on the **first** clause it can resolve. That is conforming —
CONFORMANCE_SPEC §5.5.8 says only one gate need drive and "which one drives is a
binding's choice" — and every other clause is then lowered into the per-leaf
equality `filter`, which is what keeps the answer right. So an aggregate's cost
is fixed by *one* clause: the number of leaves that clause's match set admits.

`tech_fraction` (J11) has four clauses and two output axes. Written as it was,
`cohort_mixEffectiveSCC ↔ mix_SCC` was first and drove; the technology axis was
therefore an ordinary 100-wide output loop, re-walking the SCC's mix rows once
per technology code.

**The measurement.** One `esm simulate --time 0` of the whole fixture, the four
clauses of J11 permuted and nothing else changed. Emitted rows byte-identical in
every row (`diff` against the unpermuted run's CSV). "Leaves it admits" is
computed from the parquet, not fitted: for the driving clause, the number of
`nrengtechfraction` rows sharing each bound output cell's key value, summed over
those cells and multiplied by the size of the output axis the clause does NOT
bind (the 100-wide technology axis for three of the four; the 306-wide cohort
axis for the technology clause):

| clause driving J11 | leaves it admits | whole-document `simulate` | per leaf |
|---|---:|---:|---:|
| `tech_engTechID ↔ mix_engTechID` | 2,320,704 | **11.52 s** | 2.03 µs |
| `cohort_mixEffectiveSCC ↔ mix_SCC` (as written) | 5,977,200 | **20.41 s** | 2.27 µs |
| `cohort_mixYearID ↔ mix_modelYearID` | 24,107,900 | **57.16 s** | 2.09 µs |
| `mix_processGroupID ↔ epg_processGroupID` | 272,523,600 | **541.00 s** | 1.96 µs |

Subtracting the 6.81 s the rest of the document costs (the same run with J11
stubbed to a constant), the cost per admitted leaf is ~2 µs and **flat across
four orders of magnitude of leaf count**. Nothing else explains the 47× spread:
the driving clause's selectivity *is* the runtime, and document order picks it.

**And the best order is still ~900× off the relational cost.** The four
clauses together admit **2,601** (cohort, mix-row) tuples over all 306 cohorts.
Driving on the technology clause walks 2,320,704 leaves to find them. A driver
that intersected the clauses instead of picking one would run J11 in
milliseconds.

**What this repository did about it, and what it did not.** The clause list of
J11 is now written technology-first, which is worth ~9 s on every one of the 30
evaluations `run-tests.sh` makes of this fixture. That is a workaround written
against a binding's free choice, and it is recorded as one:
`docs/esm-conventions.md` §25 and a `_comment` on the clause list itself. It is
not a fix — the next author to reorder those clauses for legibility will make
the suite take an hour, and nothing will tell them.

**Fix shape, sharpened.** Two things, in this order of value:
1. **Choose the driving clause by selectivity, not by document position.** Every
   input needed is already in hand at `resolve_join_gate` — each candidate
   clause's match set is built from data the evaluator has, and its size is the
   cost. Building all of them and driving on the smallest would have picked
   technology-first here without the document saying anything.
2. **Drive conjunctively.** Restrict the contracted axis to the *intersection* of
   the partner sets of every clause that binds it, rather than to one clause's.
   That is the 2,601-vs-2,320,704 gap, and it is what makes a MOVES roll-up cost
   what the SQL costs.

**The second gate document this finding asks for, in a form small enough to
carry upstream.** Two `on` clauses on one aggregate, one per output axis, over a
relation keyed `(cohort, technology)` — `tech_fraction` with the data taken out.
`c_key[c] = c` over 300 cohorts, `t_key[cc] = 99 + cc` over a technology axis of
width `T`, and a 9,300-row relation laid out as 31 consecutive rows per cohort
carrying technology codes 100…130, so the ANSWER (every row lands in exactly one
cell; the grand total is `M(M+1)/2`) is invariant to `T` and to clause order:

```jsonc
{ "lhs": "result",
  "rhs": { "op": "aggregate", "args": [], "semiring": "sum_product",
    "output_idx": ["c", "cc"],
    "ranges": { "c": {"from": "outc"}, "cc": {"from": "tech"}, "m": {"from": "rel"} },
    "join": [ { "on": [["c_key",  "rel_ckey"]] },     // written first ⇒ drives
              { "on": [["t_key",  "rel_tkey"]] } ],   // never drives; `tech` is scanned
    "expr": { "op": "index", "args": ["rel_val", "m"] } } }
```

`esm simulate --time 0`, one document per cell, the cohort clause written first
against the technology clause written first:

| `T` (width of the second output axis) | cohort clause first | technology clause first |
|---:|---:|---:|
| 31 | 0.17 s | 1.56 s |
| 100 | 0.53 s | 1.71 s |
| 300 | 1.59 s | 1.56 s |
| 1000 | **5.58 s** | **1.62 s** |

Linear in `T` in the first column and flat in the second, for one answer. The
axis is scanned when its own clause is not the one that drives, and driven when
it is; at `T` = 300 the two orders admit the same leaf count and the two columns
meet, which is the control that the difference is the driver and not the shape.


---

## F31 — `esm test` evaluates the whole document once per test, and `--filter` narrows only the report — **fixed**

No repro file, for F17's reason: a performance repro asserts the RIGHT answer,
so it passes, and the tripwire stage reads a passing file in `docs/findings/` as
"the defect is fixed". `fixtures/nr-logging-county.esm` is the repro — 29 tests,
343 assertions — and a synthetic confirms the shape.

**A document's `tests` section costs one full build and evaluation PER TEST,
whether or not the tests differ in anything the build depends on.** Read off the
reference: `run_model_tests` (`pkg/earthsci-ast-rs/src/pde_inline_tests.rs`) is
`for t in tests { … esm_problem(run_file, span, popts) … }` — a fresh
`ProblemOptions`, a fresh call to the `build_providers` factory (so every
`data_sources` table is re-read from parquet), a fresh build of the whole
build-time observed graph, once around the loop. Nothing is memoised across
iterations. And `--filter` is applied in `run_test`
(`pkg/earthsci-ast-rs/src/bin/esm.rs`) to the `Vec<PdeAssertionResult>` that
`run_pde_tests_with_providers` has ALREADY returned: it selects rows to print,
after every test has been evaluated.

**Measured, synthetic.** N copies of one identical test on a document whose
single evaluation costs ~1.6 s — same `time_span`, same assertion times, no
`parameter_overrides`, no `initial_conditions`, no per-test template imports, so
every build in the loop is the same build:

| tests in the document | `esm test` wall clock |
|---:|---:|
| 1 | 3.47 s |
| 2 | 5.66 s |
| 4 | 12.21 s |
| 8 | 24.64 s |
| 16 | 53.24 s |
| 16, `--filter` to one of them | **49.17 s** |

Linear, ~3.3 s per additional test, and filtering fifteen of the sixteen away
saves 8%.

**Measured, on this repository.** `fixtures/nr-logging-county.esm`,
`/usr/bin/time` around each invocation, two samples of each interleaved so they
see the same machine:

| invocation | run 1 | run 2 |
|---|---:|---:|
| `esm test fixtures/nr-logging-county.esm` (all 29 tests) | 532.74 s | 545.72 s |
| … `--filter the_surrogate_is_read_and_not_declared` (one test) | 566.71 s | 539.03 s |

The filtered run is not faster; in one of the two samples it is *slower*, which
is the spread and not an effect. `esm simulate --time 0` on the same document is
16.30 / 16.52 / 17.70 s, and 29 × 16.8 s = 487 s. The suite's dominant cost is
therefore not the fixture — it is the fixture, twenty-nine times.

**Why it is worth a finding rather than an authoring rule.** The document cannot
avoid it without giving something up. Merging the 29 tests into one would buy a
28× speedup and cost 29 statements of *what breaks if this is wrong* — the thing
`docs/esm-conventions.md` §12 says a test is for. Splitting `esm test`
invocations buys nothing, because each invocation still evaluates everything.
There is no document-level or harness-level form of this fix; it is upstream or
it is paid.

**Fix shape.** Memoise the built problem across consecutive tests of one model,
keyed on everything the build actually depends on — `parameter_overrides`,
`initial_conditions`, `expression_template_imports`, `time_span`, and the
provider set — and reuse it when the key is unchanged, rebuilding when it is
not. The key is cheap and the check is exact; no test would share a build it
should not. Every test of BOTH fixtures in this repository (29 and 10) has an
empty key, as do 39 of the 45 component and run tests, so the memo would hit on
the first try in the only place where it matters. A second, smaller win sits
behind the same seam: `build_providers` is a factory called inside the loop, so
the parquet tables are re-read per test as well.

**What it would be worth here, and where the suite's time actually goes.**
Every component of `./run-tests.sh`, timed separately at the same commit on the
same machine, against a 609.70 s whole-suite wall clock. **The machine was
shared with another agent throughout and the whole-suite number moves with it**
— three runs of `./run-tests.sh` on the same afternoon gave 821 s (before the
J11 reorder), 610 s and 508 s (after), at 1-minute load averages of 9.3, 10.5
and 6.8 — so read the shares below rather than the absolute seconds, and read
the interleaved per-document A/B in `docs/esm-conventions.md` §25 for anything
load-bearing:

| component | tests | wall clock |
|---|---:|---:|
| `esm test fixtures/nr-logging-county.esm` | 29 | 322.15 s |
| `esm test ./components ./lib ./runs` (34 documents) | 140 | 176.18 s |
| `esm test fixtures/process-evap-leaks.esm` | 10 | 45.36 s |
| the `join.on` scaling gate (both documents) | 2 | 3.75 s |
| `esm validate`, all 42 documents | — | 1.56 s |
| `esm round-trip`, all 41 | — | 1.43 s |
| everything else (tripwire, comparator self-test, fixture emit + compare, four oracles, chain cross-check) | — | ~59 s |

**90% of the suite is `esm test`, and every one of its 181 tests is a separate
build and evaluation.** Counting how many DISTINCT builds those tests actually
need — one per (`parameter_overrides`, `initial_conditions`,
`expression_template_imports`, `time_span`) group, per model, computed over the
tree — gives **42**: 1 for `nr-logging-county`, 1 for `process-evap-leaks`, 2
for the gates, and 38 across `components/`, `lib/` and `runs/`, where the tests
that carry a `parameter_overrides` block rightly keep their own. A memo keyed on
exactly that would remove **139 of the 181 evaluations**. **Inferred, not
measured**, by scaling each row above by its own ratio: 322 s → ~11 s,
176 s → ~48 s, 45 s → ~5 s, so `./run-tests.sh` in a little over two minutes,
without touching a single assertion. Nothing else in the table is worth
optimising: the whole non-`test` half of the suite is under a minute.

---

## F19 — an assertion whose actual value is `+inf` passes, whatever the `expected` — **fixed**

`F19_an_infinite_actual_passes_any_assertion.esm`. **The one that can invalidate
every other gate in this repository.**

The repro asserts three mutually contradictory values — `42`, `−5` and `0` — for
one cell, and `esm test` reports `3 passed, 0 failed`. The cell's value is
`+inf`: it sums `1e200 * 1e200` over an axis. An assertion is judged by
`|actual − expected| <= rtol·|expected| + atol`, and with `actual = inf` that
comparison is satisfied whatever `expected` is, so `expected` stops mattering.

**NaN is handled correctly**, which is what makes this attributable rather than
a general looseness: a NaN actual reports `actual=NaN … FAIL`. The hole is
specific to an infinity, which is the value an overflow, a division by a zero
denominator, or a `log(0)` produces — and the last two are ordinary hazards in
this port (a growth factor over a zero base indicator, an emission rate over a
zero `medianLifeFullLoad`).

**Why it lands harder here than it would elsewhere.** CLAUDE.md puts all model
logic in `.esm` and all testing through `esm test`, so an inline assertion is
this repository's *only* gate below the fixture comparison, and
docs/esm-conventions.md §13 leans on it deliberately: every fixture assertion
names a value out of `docs/nonroad-logging-county.md` §6 so that a source which
silently delivered its `default` fails at the assertion rather than at the
comparison. That discipline assumes an assertion cannot pass for a reason
unrelated to its expected value. Six defects in this port have already returned
a *plausible wrong value* from a document that validates; this one returns a
*pass* from a document that computes nothing meaningful.

The fixture comparison is not exposed — `compare-output.py` has its own
falsification suite and its own key-set check — so what is at risk is every
`.esm`-level assertion, which is most of what `run-tests.sh` reports.

**Polarity.** This repro passes today, so it is excluded from the tripwire loop
by name and watched by its own inverted check in `run-tests.sh`: green while
`esm test` still succeeds on it, red when it starts failing. That is the third
polarity in this file and it is unavoidable — a defect that makes tests pass
cannot be watched by a test that fails.

**Fix shape.** Judge finiteness before tolerance: an assertion whose actual
value is not finite fails unless `expected` is the same infinity. One guard,
beside the NaN guard that is already there and already right.

## F22 — a discrete event, and an implicit equation, do not evaluate on the array path

`F22a_a_discrete_event_on_the_array_path.esm`,
`F22b_an_implicit_equation_on_the_array_path.esm`.

**Found while looking for something else, and it outlived it.** Both documents
began as candidate spellings for F12's recurrence — an author reaching for a
fold naturally tries a discrete event that mutates an accumulator, and an
implicit equation that states the fold as a residual. F12 is now fixed by a
causal self-reference, so neither is a recurrence question any more.

They still fail, and what they fail at is real and separate: both constructs
work on the **scalar** path and neither evaluates on the **array** path. That is
worth keeping as its own finding rather than retiring with F12, because
retiring it would have deleted a live limitation along with the solved one —
the two documents were only ever *filed* under F12, they were never *about* it.

**Nothing in this port needs either today**, which is why this sits at the
bottom of the list rather than blocking anything. It is recorded so the next
author who reaches for one finds a measurement instead of a surprise.

---

## F23 — a leaf's `domain.element_type` does not survive a `{ref}` mount

No repro file: the document that would carry it is
`components/age_distribution.esm`, and the finding is about what that file
cannot declare.

`agedist.f`'s fold is the first calculation in this port whose **answer** depends
on the working precision, and only for one equipment point. SCC `2260007005`'s
cumulative scrappage reaches exactly 100 % at age 3, so `yryrfrcscrp` is
`100 × 0.265 / 26.5` — exactly `1` in binary64 and `0.99999994` in `real*4` —
and the surviving `5.96e-08` is amplified by thirty iterations of an unclamped
residual into a `5.3e-07` disagreement on the grown fractions and an **exact
zero** where the reference leaves `5.8885583e-08`. Four `MOVESOutput` rows hang
off that (§7.3).

So the leaf wants `domain.element_type: "Float32"`. Declaring it does not work,
and the way it fails is the shape this repository fears:

* `runs/nr_logging_county_run.esm` mounts the leaf through a top-level `models`
  `{ref}` and **re-runs the leaf's own inline tests**. With `Float32` on the
  leaf, those tests ran in **binary64** under the mount and the third grown
  fraction came back as exactly `0` against an expected
  `5.888558263222876e-08`. Nothing was rejected and nothing was logged: the
  leaf's declared precision is simply not part of what the mount carries.
* Declaring it on the **assembly** instead is not a workaround. Measured: **119
  of 295** assertions fail, across ten leaves that were authored and checked in
  binary64.

This is F2's family — a top-level `{ref}` does not merge the referenced file's
`index_sets` either — but with a worse failure mode: F2 fails at `validate`,
this one changes an answer.

**What the port does instead.** The leaf stays in binary64 and **pins both
precisions**, in the two places they are actually evaluated. Its own arithmetic
is asserted exactly, at the model's `rel 1e-12`: `3.707270451304289`,
`0.9905488043395176`, and the exact `0`. §6.1 step 3's `real*4` values are named
beside them in the test's description with the measured `5.3e-07` gap and the
reason it is amplification rather than rounding. And the **invariant both
precisions share** is asserted, which is what stops the first from being
self-referential: `Σ modfrc = G(2020)/G(1990) = 4.697819`, which
`components/growth_index.esm` derives from the index series by a different
route, asserted at 2⁻²³ for all three equipment points.
`fixtures/nr-logging-county.esm`, which declares `Float32`, is where the
`real*4` residue is asserted. `docs/esm-conventions.md` §19.5 has the rule.

The two other `2265007015` equipment points §6.2 tabulates need none of this: in
binary64 their grown fractions land within `1.8e-07` of the specification's own
decimals, because neither has a survival factor that is a cancellation residue.
Precision sensitivity here is a property of **one equipment point's scrappage
curve landing exactly on 100 %**, not of the fold.

---

## F25 — an undeclared operand is dropped rather than named, on the ingesting path

An equation references a name declared nowhere in the document. `esm validate`
refuses it with a structural error naming the equation. `esm test` refuses it
too — **on the ordinary path**. On the ingesting path it evaluates instead,
drops the operand, and returns a plausible number.

The repro is two-sided, and that is what makes this a finding rather than a
wish. The check already exists and already says the right thing; one evaluation
path does not reach it. Measured at the pinned toolchain, on the same equation,
the same undeclared name and the same assertion:

| document | `esm test` |
|---|---|
| with `data_sources` removed | **ERROR** — `Unknown variable 'undeclaredFloor' referenced in expression` |
| ingesting one column the equation never reads | **`actual=2`** — a clean run, and `max(known, undeclaredFloor)` evaluated as `known` |

So `max` did not fault on a missing operand and did not treat it as zero, either
of which would have been visible. The operand simply was not there, and its
absence is the only evidence that anything happened.

**How it was found, which is the argument for the order `run-tests.sh` runs its
stages in.** `fixtures/nr-logging-county.esm` gained `agedist.f`'s fold, whose
running-total recurrence applies NONROAD's MINGRWIND floor as
`max(running_total, minimumGrowthPopulation)`. The declaration did not come
across with the equations. The fixture then reported **120 of 120 assertions
passing** — including twelve end-to-end emission rows agreeing with the
reference snapshot to 4 × 10⁻⁶ — while `esm validate` rejected the same bytes.

The floor cannot bind on this data: the smallest base population on any of the
fixture's equipment points is 0.5, against a floor of 10⁻⁴. So losing it changed
no digit *here*, and would change the answer for a state with almost no
equipment — which is exactly what that parameter's own description had said it
was carried to prevent. Agreeing by accident on the data in front of you is the
thing this repository is built to refuse, and only `validate` running **before**
`test` caught it.

**It is the ninth instance of the failure class README's "A warning about zeros"
enumerates, and the second found on the ingesting path after F24.** That is an
argument for looking there first rather than a coincidence: the ingesting route
re-resolves names against a map built for the pipeline, and a name that map does
not hold has now twice become an absence rather than an error. F24 was the same
sentence about a self-read.

The repro asserts **10**, not the 2 the toolchain returns. Pinning 2 would pin
the buggy answer and go green, which is the mistake the repro exists not to
make. It fails today as `actual=2 expected=10`, and on the day the ingesting
path reaches the check it fails as an ERROR naming `undeclaredFloor` — red
either way until fixed, with the message saying which stage caught it. It also
asserts the ingested column itself, so a failure can never be read as the ingest
not having happened.

---

## F24 — a causal self-reference is dropped once the document ingests — **fixed upstream, pinned, and verified on the ingesting axis**

Two repros, and the second one is the finding.

`F24_repro_a_recurrence_is_dropped_on_the_ingesting_path.esm` is esm-spec
§4.3.1.1's canonical spelling over `const` inputs. **Its inline test passes**,
and that is half the finding: the defect is a disagreement between two
evaluation paths.

```
esm test <that file>      ->  s_value [1, 2, 4, 8]        s_clamped [1, 3, 7, 15]   correct
esm simulate <that file>  ->  s_value [1, NaN, NaN, NaN]  s_clamped [1, 1, 1, 1]
```

`F24b_repro_one_ingested_column_breaks_the_recurrence.esm` is that same document
plus **one ingested column that the recurrence never reads** —
`runspecmonth.monthID`, one row. At `rel 0, abs 0`:

```
same document, no data_sources    esm test -> 4/4 pass
same document, one column read    esm test -> 1/5 pass (the month is right; both recurrences are not)
```

The `m_month = 8` assertion passes in the ingesting case, so the **data path
works** and it is the recurrence that the build changes. The trigger is not that
the recurrence reads ingested data; it is that **the document ingests at all**.
`run_simulate` sets `build_pipeline = true` whenever providers exist, and
`esm simulate` takes that path even for a document that does not ingest.

**Silent, and the clamp is why.** An unresolved self-read comes back `NaN`,
which would at least be loud. `max(NaN, 0)` returns `0`, so a body with a clamp
— which is exactly what `agedist.f` has — reads `[1, 1, 1, 1]` where the
document says `[1, 3, 7, 15]`: finite, plausible, monotone, wrong, nothing
logged at any level. `CONFORMANCE_SPEC` §5.19.4 requires a raised fault rather
than a sentinel and names this laundering as the reason.

**Confirmed upstream, not a spelling problem here.** The repro is EarthSciAST's
own canonical valid example, `tests/valid/recurrence_causal_self_reference.esm`:
6/6 under `esm test`, and under `esm simulate --observed r` it returns that
file's non-recurrent `b[y]` `const` verbatim,
`[1e-16, 1, 1e-16, 1e8, 3, -1e16]`, meaning the self-read term contributed
nothing at all. Four spellings were tried before filing — the bare-variable LHS,
the §4.3 indexed-aggregate LHS (`aggregate{expr: s[k]} ~ …`, the other form
§4.3.1.1's *Recognition* paragraph admits), a one-axis fold, and a two-axis fold
with the second axis an identity index — and all four are correct under
`esm test` and unresolved under `esm simulate`.

**What it costs this port, and what it does not.**
`fixtures/nr-logging-county.esm` reads twenty-six snapshot tables, so it is on
the pipeline path unconditionally, and a fixture's emitted answer goes through
`esm simulate` regardless. The fold was authored into that fixture and taken
back out: measured, `fold_totalPopulation` at 1991 read `1e-4 × (1 + grwfac)`
instead of `83.3 × (1 + grwfac)` — the signature of
`max(self_read, MINGRWIND)` with an unresolved self-read — and the grown
fractions summed to `1.5e-06` instead of `4.697819`. So the fixture still
carries three numbers.

It costs `components/age_distribution.esm` nothing: that document does not
ingest, so it computes the fold on the path that honours it, verified
**bit-exactly against the reference fold on all six equipment points — 306 of
306 cells at `rel 0, abs 0`** — with 55 assertions on it.

**The gap that let it through is worth more than the defect.** The construct's
conformance tier and every fixture for it were verified under `esm test` only: a
construct with two evaluation paths, checked on one. `run-tests.sh`'s F24 check
therefore runs **both** commands on F24a and asserts that they still disagree,
and it checks the *clamped* column rather than the `NaN` one — a check on `NaN`
alone would pass the day the sentinel changed without the construct working.
`docs/esm-conventions.md` §19.4 makes "exercise a new construct on both paths"
a rule rather than an anecdote.

### The fix, and one cause rather than two

EarthSciAST `de784f3f8` (`9dafce9a0` is the fix, `ed939f48b` the both-paths
test, `1c05b569a` the spec text). The two axes this section describes — "any
document that ingests" and "every document under `esm simulate`" — turned out to
be **one cause**: `prepare::eval_observed` evaluated every observed
**wholesale** through the shared expression evaluator with no recurrence scope,
so `index(r, y − a)` resolved against a map that does not yet hold the array
being built and fell through to an unbound-name `NaN`. Both routes reach that
function.

The fix is structural rather than a second implementation. The sweep is factored
out of `materialize_observeds_pass` into `rhs::sweep_recurrence` and **both
paths call it** — two call sites with two copies is precisely how one path came
to work and the other to be dead, so one function is the fix and not a cleanup.
And the part that matters beyond this bug: a self-read the lowering does not
recognize now returns **`recurrence_unsupported_form`** instead of falling
through to the wholesale evaluation, so a future path that misses the sweep
fails loudly rather than quietly.

**It is the eighth instance of this repository's characteristic failure, and the
first where the sentinel was MANUFACTURED BY A CLAMP rather than returned by the
runtime.** The runtime did return `NaN`, which is the loud sentinel and would
have propagated; `max(NaN, 0.0) == 0.0` destroyed it, because IEEE-754 `max`
returns the non-NaN operand. MOVES clamps everywhere — `agedist.f`'s own fold
body is `max(·, 0)`, and so is `prccty.f`'s skip test and half the scrappage
arithmetic — so in this port a NaN sentinel is not a defence at all. That is why
`run-tests.sh` checks the clamped column: the loud half of the evidence was
already there and the clamp is what removed it.

**Not in the pinned toolchain, and one axis still unproven.** `esm-version.lock`
pins `6d0ec3b13`, which predates the fix, so both repros still reproduce here
and stay in the tripwire. The upstream author verified the **build-pipeline
path** — which both axes reduce to — and said plainly that they could not verify
the **ingestion** axis, because that build has no parquet reader. So
`fixtures/nr-logging-county.esm` keeps its carried `const` until the ingestion
axis is confirmed against a reader-enabled binary on the real snapshot.
`run-tests.sh`'s F24 check is already the tripwire for that: it fails, with
instructions, the moment `esm simulate` agrees with `esm test` on F24a.

---

## F33 — a `Float32` document is evaluated in binary64 by Julia and Python, silently

**No repro file, for the reason F17 and F31 had none:** the repro's natural
polarity is backwards here. This repository runs the Rust binding, which
*honours* `element_type` — so a document asserting binary32 behaviour PASSES on
`./esm`, and the tripwire loop would report it as a fixed defect on the first
run. The finding is about the other bindings, and nothing in this tree executes
them.

**Not a new contract. An unimplemented one.** CONFORMANCE_SPEC §5.18 is
normative, and §5.18.2 closes by naming exactly this failure:

> A binding that cannot honour a clause MUST refuse it. Evaluating part of a
> document in a precision it did not ask for, and saying nothing, is the defect
> this section exists to prevent.

Julia implements the refusal §5.18.2(3) requires for time integration
(`E_TREEWALK_FLOAT32_STATE`, `tree_walk/compile.jl:1417`, whose message says
why: "the compiled RHS's literals and const data are Float64"). But §5.18.2(3)
is explicit that the rest still runs — "Algebraic, observed and relational
evaluation — which is what an inline `tests` block and `observed_field` read —
is unaffected and runs in binary32." That path is binary64 in both bindings,
and neither says so.

How far from honoured, measured by where `element_type` is READ:

| binding | sites reading it during evaluation |
|---|---|
| Julia | **none** — parsed and round-tripped (`types.jl`), read nowhere else |
| Python | **one** — `simulation_array.py:686`, feeding `rounding_for_element_type` into the recurrence sweep. Aggregates and joins are float64. |
| Rust | honours it per operation |
| Go, TypeScript | N/A — no evaluator at all |

**The measurement.** A `Float32` document with two join clauses over integer
keys straddling a binary32 collision (`2265007010` / `2265007015`; binary32
spacing at that magnitude is 256), key columns left at the document default:
Rust answers **8**, Julia **4**, Python **4**. Three executing bindings, two
answers, no diagnostic on any of them.

**Why this is not F18.** F18 is Rust's, and is about INGEST — it already records
this exact collision and measures 214 equipment categories collapsing to 48.
Rust's 8 above *is* F18, with the per-variable `Float64` override as its
resolution. F33 is the other bindings' side: not narrowing when the document
said to, and not refusing either.

**Why this is not F17.** F17 was Rust lowering a join's `on` pair into a filter
that inherited the working precision. Julia and Python never build a comparison
expression from a join at all — each pair is a gate of integer bucket codes
compared with integer `==` — so they are structurally immune. Rust was alone in
lowering the comparison, which is why it was alone in getting it wrong.

**What it costs this port.** Nothing directly: Rust is the binding this
repository runs, and its answers are the ones every fixture is checked against.
What it costs is a claim — no cross-binding fidelity statement can be made for
any float32 document here, which is the whole NONROAD side. Julia and Python
are right on the collision probe by *not* implementing the declaration, and
that is the least durable way to be right: the same non-implementation makes
them wrong wherever binary32 rounding is what the reference actually does, and
§5.18.1 opens by measuring precisely that case.

Recorded upstream in `ESM_COMPLIANCE_VALIDATION_MATRIX.md` under BEHAV-11-007's
binding-status note.

---

## Fixed upstream

Retired from the tripwire; the repros are gone because the fixing commits carry
their own regression tests. Kept here so the workarounds they forced can be
traced.

- **F17** — EarthSciAST `fe86d784b` — a multi-clause `join` now chooses its driving gate by **selectivity** rather than by document position, and then drives the **conjunction** by intersecting partner lists. Normative as CONFORMANCE_SPEC §5.24 and `BEHAV-11-001..008`. J11 in its worst clause order goes 272,523,600 leaves to **4,455** (floor 2,601; the 1.71× gap is a second contracted axis the floor does not count) and the whole document 515.88 s to **3.71 s**; `mixed-onroad`'s `cohMode_rate` spelled as six clauses goes 158,030,400 leaves to **3,772**, which is exactly what the hand-fused composite key costs — so **that workaround is retirable**. Part 1 alone is a *wash* on `nr-logging-county` as written: resolving every clause costs equijoins that first-clause-wins skipped, and 13.9% fewer leaves does not pay for them. Essentially all of the win is the intersection.

  **But the finding was not what it said it was, and the correction is the important part.** F17 was filed as a COST finding — the answer is right, the run does not end. Reordering three `join` clauses on `out_emissionQuant` changes **32 of 144 emitted rows on the merge-base binary**, which makes it a silent WRONG ANSWER finding that had been sitting under a performance headline. Root cause: every resolved `on` pair is also lowered into the node's `filter` so a non-driving clause is still tested per leaf — that is the whole of §5.5.8's "which clause drives cannot change the result" — but `precision_infer::annotate_models` runs at `problem.rs` stage (1c)/(3b) while `join::resolve_aggregate_joins` runs inside the array compile at stage (4). The lowered `left == right` is built *after* annotation, carries no marker, and evaluated at the document's **working precision**. This document works in binary32, where the spacing at SCC magnitudes is **256** and `2265007010` and `2265007015` are the same number. The gate compared exact `i64` keys and separated them; the filter did not, so two cohorts' emissions were summed into the wrong output row (1.784 + 0.480 = 2.264). Fixed by marking the comparison binary64 where it is built (`8bb234629`), and now normative in §5.5.8: **a key comparison is exact, not the document's precision.** Every fidelity number this repository has published for `nr-logging-county` was correct only because the SCC clause happened to be written first.

- **F31** — EarthSciAST `9e282da40` — `run_model_tests` reuses the built problem across consecutive tests that share it, keyed on `expression_template_imports`, `time_span`, `parameter_overrides` and `initial_conditions` (floats by bit pattern), and `--filter` now selects **work** rather than rows. Normative as CONFORMANCE_SPEC §5.25 and `BEHAV-12-001..007`. Measured with both binaries built from `a1dc9bb30`, so this is the change in isolation: `esm test fixtures/nr-logging-county.esm` **301.9 / 306.6 s → 11.0 / 16.2 s**; `run-tests.sh` user time **712.5 / 707.0 s → 251.6 / 235.5 s** (wall clock is not usable — `real ≫ user` at loadavg 9→21, starved by concurrent agents); `esm test ./runs --filter <one of fifteen>` **153.2 s → 0.98 s**, 156×. Over the tree, 200 tests need 44 distinct builds.

  **Combined with F17, measured on the pinned binary `9e282da40`**: the whole
  suite is **58.34 s wall / 68.23 s user**, against 712.5 s user before either
  landed — and all four fixtures report the same worst cells to the digit
  (4.561e-06, 8.320e-06, 7.495e-06, 7.294e-06), which is what makes the speedup
  a speedup rather than a change of answer.

  Two things in it that a naive memo would have got wrong. `assertions` and `tolerance` are **deliberately not in the key** — they feed the *solve*, not the build, so keying on them would be correct and would collapse the hit rate to nearly zero; only the build is memoised and every test still solves. And `take_inspection` uses `std::mem::take`, so it **drains**: without re-arming, the second test of a state-free document — which is every MOVES fixture, where `solve` returns `NotDynamic` and never refills the record — reads what the first test left behind. That is the silent class F5/F13/F14/F24 belong to, and it is covered by a test that fails on a wrong **number** rather than merely on a wrong build count.

- **F11** — EarthSciAST `107a15152` — a relation can be joined to itself, and driven. The root cause was neither the validator nor the join kernel: resolving an `on` key column to a loop symbol goes through the column's *axis*, and that map is one-to-many the moment two ranges draw `{from}` one index set, so both reference bindings declined to pick. The kernel could always have done it — `equijoin` addresses range symbols by *name* and never consults an axis. It was a genuine underdetermination in the format: `["a","b"]` and `["b","a"]` are both consistent and compute transposed results. Resolved with no new syntax in the common case (candidates in the node's canonical range order, left key earlier and right later), **refused** at three or more, with an explicit `join.syms` overriding — and narrowed to the data-column step, so a key naming an index set still errors rather than becoming a tautology and an ungated product. Measured at the downstream scale: 63,602 rows, 4.045e9 candidate pairs, **0.31 s driven**. **F17 is separate and its headline is already gone** — its exact bisected shape runs 0.06 s driven on the *merge-base* binary, so earlier driver work fixed it; what remains is gate selection and ordering, measured identical on both binaries.
- **F24** — EarthSciAST `de784f3f8` — a causal self-reference was dropped on the build-pipeline path, and **silently**. One root cause, not two axes: `prepare::eval_observed` evaluated every observed wholesale with no recurrence scope, and both `esm simulate` (which turns the pipeline on to materialize array observeds) and any ingesting document reach that one function. The self-read resolved against a map that does not yet hold the array being built, fell through to an unbound-name `NaN`, and **`max(NaN, 0.0)` returned `0.0`** — the shape `agedist.f`'s own body has. Measured downstream, the grown fractions summed to **1.5e-06 instead of 4.697819**. Fixed by making the sweep **one function both routes call** — two copies is precisely how one route came to work and the other to be dead — with `recurrence_unsupported_form` under any path that misses it, so a future miss fails loudly. The correction to the *verification* matters more: the conformance tier and all nine fixtures had been exercised under `esm test` only, so ten new tests re-materialize each fixture through the pipeline and re-check every assertion **on bits against the same pin**, because "both routes produced something plausible" is the state that persisted here. Normative as `CONFORMANCE_SPEC` §5.19.3b and `BEHAV-04-G-009`. The ingestion axis could not be verified upstream — no parquet reader in that build — and is verified here instead: `F24b` goes 5/5 against the real snapshot, and is kept as a **control** for exactly that reason.
- **F15 and F7** — EarthSciAST `35f8d9e87` — a scheme-less `url_template` is a filesystem path, and a relative one resolves against the directory of the file that declared it, which is §4.7's rule for a `ref` verbatim. Dot-segment removal is lexical (RFC 3986 §5.2.4) and never `realpath`, because a `{date:…}` template names a file per timestep and none of them exists at load time. **Environment expansion is refused, not granted**: a `${` anywhere in a template is a load-time `data_source_url_unresolved`, because a document reading `${…}` does not say what it reads, and the value is spliced into a URL that is then *fetched* — a `://`, `@`, `?`, `#` or `..` from the environment redirects it without changing a byte of the document. **The workaround is gone**: `run-tests.sh` no longer rewrites any document before running it, so the document that runs is the document that is checked in, which is what makes `esm validate` on a fixture mean anything.
  F7 came along because it had to. It was recorded here as a `round-trip` bug and is in fact **~17 subcommands** — only `validate` and `test` used `load_path`. On its own that is a loud failure. Combined with F15's fix it would have become a **silent** one: a CWD-anchored `ref` fails, but a CWD-anchored `url_template` resolves, succeeds, and reads a *different file*. Measured before the fix, one document converted from three directories gave `file:///tmp/tables/probe.parquet`, `file:///tables/probe.parquet` and `file:///u/ctessum/tables/probe.parquet`. That is the **seventh** instance of this toolchain's characteristic failure (README's "A warning about zeros" holds the numbering), and it was found by an author noticing that their own change would create it.
- **F6 and F16** — EarthSciAST `d421d3541` — they were **one cause, not two**. The §6.6.3 pointwise assertion path read the solve trajectory and nothing else, and a 0-D observed lives in one of three carriers: the array runtime exposes every 0-D observed unasked (which is why the array-shaped twin always worked), the scalar backend exposes one only when the caller names it (F6), and a document that cannot integrate has no trajectory at all (F16). `esm simulate` printed the right value for both repros the whole time; only `esm test` could not reach it. The fix requests the pointwise-asserted observeds and falls back to the state-free scalar observed, with the same guards the array branch has — so an unbound name is still an ERROR naming it, never a zero. **Fixed in Rust only**; Julia and Python still resolve a pointwise assertion against state rows, recorded upstream as `BEHAV-06-B-008` rather than papered over.
- **F19** — EarthSciAST `31b46188c` — an assertion whose actual was `±inf` passed whatever `expected` said, because `check_assertion` had been reduced to the tolerance bound alone and `|inf − expected| ≤ inf` holds for every `expected`. **Julia was always right**: its `_check_assertion` delegates to `isapprox`, which carries the finiteness clause. The Rust and Python re-implementations both documented themselves as "Julia `isapprox` semantics" and both dropped it — a re-implementation drifting from the binding it names, invisible to every other conformance category because every other fixture's actuals are finite. Now normative in esm-spec §6.6.3 and pinned by CONFORMANCE_SPEC §5.20, a tier that compares **verdicts** rather than actuals, since `±Inf` and `NaN` are not JSON-representable.
- **F25 and F26** — EarthSciAST `a1dc9bb30` — they were **one defect wearing two sets of clothes**, and one fix closed both. A name unbound at evaluation returned `Value::Scalar(f64::NAN)`, and IEEE-754 `max`/`min` return the **non-NaN** operand — so a clamp does not propagate that sentinel, it **absorbs** it: the operand vanishes from the expression and every downstream digit stays finite and plausible. F25 reached that arm through a name declared nowhere in the document; F26 through an index symbol used outside the `aggregate` that binds it. Same arm, same silence, different doors. It is also the same arm **F24** rode, and F24's fix did not generalise: it gave one construct a fail-closed path at the *top* of `lookup_variable` while the general arm forty lines below still returned `NaN`. The gate that catches this already existed and already said the right thing (`check_free_variables`); only the compile path reached it, and `prepare::run_prepare` — taken by **any ingesting document** — evaluates the observed graph wholesale upstream of it. Fixed by making it one function both routes call, plus an `E_TREEWALK_UNBOUND_NAME` backstop on the existing fail-closed channel so a future route cannot silently reacquire it. No operator was special-cased. Cost measured rather than assumed: the arm was instrumented and read **zero times across 119 suites and 1,399 tests** — on every valid document in the corpus it was dead code returning a sentinel. Rust was the sole outlier of the five bindings; Julia, Python and TypeScript each already raise a named unbound-variable error and Go has no runner by design, surveyed by reading each resolver rather than assumed. Normative as `CONFORMANCE_SPEC` §5.23 and `BEHAV-04-H`, a new family. **Both repros are kept as controls**, for F24b's reason: the upstream crate has no parquet feature, so the fix was verified there against `build_pipeline` directly and never against a live `data_sources` block — F25's control reads the real snapshot and is the only place that axis is exercised at all. Note where the fix landed for F26: at **evaluation**, not at `esm validate`, which still accepts that document and is right to — `i` *is* declared, it is merely used out of scope.
- **F12** — EarthSciAST `a83cde55e` — a recurrence over an index axis now has a spelling, and it adds **no new op and no new schema field**: an equation defining an array-shaped unknown `V` whose `aggregate` body reads `index(V, k − c)` — `V` itself, strictly earlier along one of that node's output axes — is a causal self-reference, materialized cell by cell, that axis outermost and ascending, each cell published before the axis advances. The LHS already names the accumulator, so an annotation would carry no information the read does not. The proof obligation **splits**: the coefficient of the frame symbol must be provably 1, or the axis and direction are undecidable, but the lag's *sign* need not be provable at all, because a self-read resolves only against published cells and so faults rather than returning a number. Arithmetic order is normative (CONFORMANCE_SPEC §5.19), and the carried value is rounded to the variable's `element_type` at **every** cell, not once at the end — which matters here, since the consumer is a `Float32` document. Its control is now **deleted**: it was kept only until `components/age_distribution.esm` computed the fold and guarded it with its own assertions, which it does, in 55 places, verified bit-exactly against the reference fold on all six equipment points (306 of 306 cells at `rel 0, abs 0`). **The port's blocker did not disappear with F12, it moved and shrank**: `fixtures/nr-logging-county.esm` still carries the fold's three output values, because a document that ingests is forced onto an evaluation path that leaves a causal self-read unresolved — **F24**, which is about the toolchain rather than the format, and which the construct's own conformance tier could not have caught because it was verified under `esm test` only. Of the four spellings tried, the `makearray`-region one is now refused *loudly* with `recurrence_unsupported_form` naming the fix, where it used to fail silently — region order fixes which write wins, not which cell is evaluated when — and the other two turned out to record a different gap, re-filed as **F22**.
- **F24** — EarthSciAST `de784f3f8` — a causal self-reference was **dead on the build-pipeline path, and silent**: `prepare::eval_observed` evaluated every observed wholesale with no recurrence scope, so the self-read fell through to an unbound-name `NaN` and `max(NaN, 0.0)` returned `0.0`. One cause, not the two axes the section above describes — `esm simulate` and the ingesting path both reach that function. The sweep is now one shared `rhs::sweep_recurrence` both routes call, and an unrecognized self-read returns `recurrence_unsupported_form` rather than falling through. **Listed here for the record but NOT retired**: `6d0ec3b13` is pinned, so it still reproduces, and the ingestion axis has not been confirmed against a reader-enabled build. Its two repros stay.
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


---

## F18 — an ingested value the declared `element_type` cannot represent is narrowed silently

`F18_control_float32_key_override.esm`. **Resolved as a design question, still
open as a silence.** The original defect — a document-wide
`element_type: "Float32"` collapsing ingested ten-digit keys — is fixed by a
per-variable override. What remains is that *omitting* the override still
narrows silently, with no diagnostic.

Reading one real snapshot column under each precision, same document, one line
different:

| precision | rows | distinct `SCC` | first value |
|---|---|---|---|
| Float64 | 1,183 | **214** | `2260001010` |
| Float32 | 1,183 | **48** | `2260001024` |

214 equipment categories collapse to 48. MOVES SCC codes are ten digits, ~2.26 ×
10⁹, and binary32 represents every integer only to 2²⁴ = 16,777,216 — 135 times
smaller. `2265007010` and `2265007015` both become `2265007104`, so a `join.on`
over them merges two different equipment categories.

End to end on `fixtures/nr-logging-county.esm`, adding nothing but the `domain`
block:

```
binary64: SCC 2260007005, emissionQuant 1.0997e-07 .. 1205.1395
Float32 : SCC 2260006912, emissionQuant ALL EXACTLY ZERO
```

The document validates and the run completes.

**A relative tolerance cannot see this.** The repro asserts at *zero* tolerance
deliberately. `|2260001024 − 2260001010| / 2.26 × 10⁹` is 6.2 × 10⁻⁹ — four
orders of magnitude inside the default 1 × 10⁻⁶ — so the first version of this
repro passed while the key was wrong. The corruption is relatively tiny and
semantically total. That is exactly why `require_exact_key_set` exists and why a
key set must never be compared within a tolerance.

Row by row against the same column read in binary64: **all 1,183 rows differ**,
and rows 0 and 1 (`2260001010` and `2260001020`) both become `2260001024`.

**It is not the `const` path.** A `const` array of the same three codes
round-trips exactly under Float32 — I wrote that repro first and it passed. The
corruption is on the **ingested** path, which is where a relational model's keys
actually live. EarthSciAST `973ee7360` already refuses a declared index-set
*extent* above 2²⁴, for exactly this reason; the gate does not reach data
columns.

**Why this was a design question rather than a patch.** Honouring Float32 was
meant to reproduce the reference's `real*4` arithmetic (PLAN.md §1.6.2). But the
reference is `real*4` in its *floating-point quantities* while its keys stay
Fortran `INTEGER` and `CHARACTER` — never `REAL*4`. A document-wide float
precision cannot express that split: it reproduces the arithmetic and destroys
the keys. Either key and integer columns are exempt from the document precision
— a typed-column notion the format did not have — or precision becomes
per-expression rather than document-wide.

### Resolved: a per-variable `element_type`

Upstream took the first branch and gave the format the typed-column notion it
lacked: a `ModelVariable` may declare its own `element_type`, overriding the
document's. `fixtures/nr-logging-county.esm` now declares `Float32` with 19
SCC-valued variables at `Float64`, passes 87 of 87 assertions, and emits twelve
values that are *exactly binary32-representable* with the SCC intact — so both
halves are live in one run.

Two things about the resolution are worth knowing before you use it. It is
**strict**: mixing precisions inside one operator is a compile error, not a
coercion. And it is **explicit** — there is no automatic exemption for integers
or keys — which is why the repro for this finding could not survive as a repro
and is now a two-sided control instead: the behaviour it asserted, that a
Float32 document keeps an ingested ten-digit key exact by itself, is
deliberately not provided. Left in the failure loop, its "still fails, as
recorded" would have been false reassurance about a fixed defect.

### Still open: the narrowing is silent

Declare `Float32`, ingest a ten-digit key, omit the override, and the document
validates, runs, and returns a corrupted key. That is the same
silent-plausible-wrong-value class as everything else in this file, and it is
now *inconsistent* with the resolution: upstream refuses to widen or narrow
silently between the operands of one operator, but ingress narrows a value the
declared type cannot represent without a word. The gate that already exists for
a declared index-set extent above 2²⁴ is the precedent; it does not reach data
columns.

**This finding has no repro, and cannot have one.** The wanted behaviour is a
*refusal*, and "should refuse" has no assertion form in this harness — an error
and a wrong answer are the same verdict to it. F19 is the same shape of hole in
the same harness. So the check is the control described above, which catches a
regression in either direction but cannot catch the silence itself.


---

## F20 — a constant-folded scalar right-hand side loses the array shape

`F20_constant_folded_rhs_loses_the_array_shape.esm`. Found authoring Phase 3's
first component.

```
$ (cd docs/findings && ../../esm test F20_constant_folded_rhs_loses_the_array_shape.esm)
  a_scalar_folded_rhs_broadcasts_over_the_declared_shape[1] (unguarded)  PASS
  a_scalar_folded_rhs_broadcasts_over_the_declared_shape[2] (guarded)    ERROR
      assertion evaluation failed: array state 'guarded' has no cells in var_map
```

Two variables, both declared `shape: ["row_ax"]`, both assigned
`ifelse(guard > 0, col, 0.0)`. They differ in one thing: the guard's default.
With the guard at 1.0 the fold keeps the array branch and `unguarded`
materializes. With it at 0.0 the predicate is a compile-time false, the whole
`ifelse` folds to the scalar literal `0.0`, and the left-hand side's declared
shape is discarded — the variable is absent from the state map rather than
being a three-cell array of zeros.

An array assigned a scalar broadcasts everywhere else in the format; the
control in the same document proves the runtime knows the shape. It is the
*folder* that drops it.

**Loud, not silent**, which is what keeps this a cost rather than a hazard. It
names the variable, and the message is F12's — which is a small trap of its
own, since F12's cause (a recurrence) and this one's (a fold) have nothing in
common.

**Impact: it removes one testing technique.** A component cannot exercise the
FALSE arm of a guard whose predicate is a run-level scalar by overriding that
scalar, which is the natural way to test a zero-denominator guard or a
switched-off adjustment. Both places Phase 3 reached for it, the technique had
to be replaced:

* `components/onroad_travel_fraction.esm`'s `share_of_group` zero guard is
  exercised by a probe **row** whose group total is zero, not by overriding the
  carried denominator to zero;
* `components/onroad_energy_output.esm`'s two clamps are exercised by moving
  the **temperature** both arms are reachable from, not by forcing either
  factor to zero.

Both replacements are better tests — per-row data exercises the join as well
as the arithmetic, and moving a physical input exercises the branch the way
the model will actually meet it — so this cost the port two rewrites and no
capability. It is recorded because the first form of each test was the obvious
one, and because the error message points at the wrong finding.

**Fix shape.** Broadcast a scalar-folded right-hand side over the left-hand
side's declared shape, which is what the same document already does when the
fold does not collapse the branch.

---

## F21 — a scoped name is not an assertable variable

`F21_a_scoped_name_is_not_assertable.esm` (with `join_leaf.esm`). Found
authoring Phase 4's assembly, `runs/evap_leaks_run.esm`.

`esm-schema.json`'s `Assertion.variable` says, verbatim:

> Name of the variable or species to check. Use the local name (e.g., `"O3"`)
> or a scoped reference relative to this component (e.g., `"subsystem.X"`).

Do that and the assertion errors:

```
$ (cd docs/findings && ../../esm test F21_a_scoped_name_is_not_assertable.esm)
  TOTAL                                        3      0      1

  - Host/a_scoped_name_resolves_as_an_operand_but_not_as_an_assertion[3]
      (Leaf.left_key@t=0.0) — ERROR
      assertion evaluation failed: variable 'Leaf.left_key' is not declared in
      model 'Host'
```

**The same name resolves everywhere else in the same document.** That is what
the repro's first two assertions establish, and it is what makes this a gap in
one code path rather than a mount that does not work: `host_doubled` is
`2 × Leaf.left_key` in an ordinary equation and evaluates to 14 and 8 from the
leaf's `[7, 9, 4]`. Across this repository's four assemblies the scoped form is
also used, and works, as

* a `join.on` key column — every `run_*` equation in `runs/mixed_onroad_run.esm`
  and `runs/evap_leaks_run.esm`;
* an `expr` operand inside an aggregate;
* a `plots` `variable` — `runs/nr_logging_county_run.esm` plots
  `Rollup.pp_polProcessID`, `runs/mixed_onroad_run.esm` plots `Output.out_SCC`.

**Measured on both mount forms, with a byte-identical message.** The repro uses
the top-level `models` `{ref}` form (`docs/esm-conventions.md` §5's). A
`subsystems` mount of the same leaf asserting the same scoped name fails the
same way, so there is no spelling of the mount that makes the assertion work and
the finding is not about which form §5 recommends.

**Loud, and at assertion time.** `esm validate` passes; the failure is reported
as an `ERROR` (not a `FAIL`) with the name in it, so nothing is silent and
nothing is mistaken for a wrong number.

**Impact: an assembly can only assert its own columns.** A leaf value it wants
to pin has to be routed through a variable the asserting model declares. Two
shapes for that, and the second is better:

* an identity equation, `run_x = Leaf.x`, which adds a variable that means
  nothing;
* an algebraic recovery from columns the model already has.
  `runs/evap_leaks_run.esm` wants the base rate its emission stage *carries*, to
  assert it beside the residual of the rate join, and gets it as
  `run_carriedRate = run_weightedMeanBaseRate − run_rateResidual` — both its
  own. One expression more than the schema implies is needed, and no loss of
  coverage.

**A second measurement, taken at the same time, that is not this finding.** The
two mount forms differ in whether the *leaf's own* tests run under the mount.
Same leaf, same host, one host variable and two host assertions either way:

| mount form | assertions discovered | leaf's own test runs? |
|---|---|---|
| top-level `models` `{ref}` | 3 | **yes** |
| nested `subsystems` | 2 | **no** |

`docs/esm-conventions.md` §5 states the leaf's-tests-run behaviour as a feature
of mounting and then recommends the nested form for new assemblies. On this
toolchain those two sentences pull against each other, and this port's
assemblies get the leaves' tests only because a now-fixed defect (F1) forced
them onto the top-level form. Recorded here because it is a reason to keep that
form that §5 does not know about; `docs/esm-conventions.md` §18 carries the
authoring consequence.

**Fix shape.** Resolve an assertion's `variable` through the same scope chain
the equation binder already uses, which is the behaviour the schema's own
description promises.

## F28 — a recurrence whose predecessor is named by a data column

`F28_a_data_named_predecessor_is_not_a_recurrence.esm`, with
`F28_control_the_contracted_lag_workaround.esm` beside it.

```
index 0 of a causal self-read of 'f28_value' is not affine in its frame symbol
'k'. A self-read names a position RELATIVE to the cell being written (`k - 1`,
`k - a`, `k - a - 2`), which is what makes the recurrence axis and its
direction decidable (esm-spec §4.3.1.1).
```

esm-spec §4.3.1.1 admits a self-read whose index argument is affine in the
frame symbol with **coefficient 1** and an offset built from integer literals
and index symbols. `index(V, k − index(lag, k))` looks like that and is not:
`lag[k]` is a *value*, and the checker cannot resolve a range for it. Both
`esm validate` and `esm test` refuse it, with the same diagnostic — the one
place in this file where the two paths agree without having to be checked
separately, which is worth noting next to F25.

**This is correct behaviour, not a defect.** §4.3.1.1 splits its proof
obligation deliberately: the *sign* of the lag need not be provable (that is
what admits `agedist.f`'s straddling fold), but the *coefficient* must be,
because without it neither the axis nor the direction of the recurrence is
decidable. A data-column offset defeats exactly that half. It is recorded here
because an author porting MOVES writes this expression, and because knowing the
cost of the alternative before paying it is the point.

**Where MOVES needs it.** `TankTemperatureGenerator` TTG-4a
(`calculateHotSoakAndOperatingTankTemperatures`) walks a work queue: each trip,
as its last segment is reached, enqueues the trip whose `priorTripID` is its own
`tripID`, carrying the hot-soak end temperature forward as the next trip's
starting `keyOnTemp`. The predecessor is named by a column. Measured on the
`process-evap-permeation` snapshot: 26,300 of `SampleVehicleTrip`'s 37,216 rows
carry a `priorTripID`, and `tripID − priorTripID` is 1 for 24,610 of them and
2, 3, 4, 5, 6 or 7 for the other 1,690 — so a constant lag of 1 is wrong on
1,690 rows and there is no other constant to write.

**Impact, and it is the Phase 4 screening.** PLAN.md screened
`process-evap-fvv` and `process-evap-permeation` as blocked by F12 and
unblocked by its fix. F12's fix does unblock TTG-1, the quarter-hour
recurrence, which `components/tank_temperature.esm` now computes. It does not
unblock TTG-2/3/4 or TTG-7, and those are what the two fixtures actually stand
on — `docs/evap-permeation.md` §8.1 measures which. The screening was not wrong
about F12; it was incomplete about what was behind it.

**The workaround, and its two costs.** Contract the lag over its bounded range
and select the matching term with an equality guard against the data column:

```jsonc
"ranges": { "k": { "from": "rows" }, "a": [1, 7] },
"reduce": "+",
"expr": { "op": "ifelse", "args": [
    { "op": "==", "args": [ {"op":"index","args":["lag","k"]}, "a" ] },
    <a term reading index(V, k − a)>,
    0.0 ] }
```

That is §4.3.1.1's straddling idiom and docs/esm-conventions.md §19.2's rule
that the contracted index *is* the lag — the same shape `agedist.f`'s fold
uses, pointed at a predecessor a column names rather than at the slot number.
The control reproduces `[1, 2, 4, 4, 8, 8]` with it. It costs `max lag`
evaluations per cell where the direct spelling would cost one, and the range's
upper bound is a **metaparameter expression read off the data** rather than off
the model: 7 is a property of this capture, and a lag beyond the declared range
contributes the additive identity rather than raising. That second cost is this
repository's characteristic failure in miniature, so an author using this
spelling owes an assertion that the observed maximum lag is the one declared.


## F32 — an `enums` member cannot be zero

`F32_an_enum_member_cannot_be_zero.esm`. Found authoring Phase 3's drive-cycle
operating-mode distribution.

```
Schema errors:
  ✗ /enums/operating_mode/Braking: 0 is less than the minimum of 1
```

`esm-schema.json`'s `EnumDeclaration.additionalProperties` is
`{"type": "integer", "minimum": 1}`, so an identifier whose value is 0 cannot be
named. The refusal is at `validate`, loud, and names the member — the right
failure mode.

**Impact.** MOVES has several zero-valued identifiers and one of them is not a
sentinel. `operatingmode.opModeID = 0` is **Braking**: a decelerating second is
classified into it, it carries its own `emissionrate` row, and it is 2.0 % of
`mixed-onroad`'s weekend and 5.6 % of its weekday operating-mode distribution.
`regulatoryclass.regClassID = 0` ("Doesn't Matter"), `modelyeargroup.
modelYearGroupID = 0` and `fuelusagefraction.modelYearGroupID = 0` (a wildcard
the fuel-usage rebase tests for) are three more, in three other tables.

So `docs/esm-conventions.md` §4's rule — an identifier value is written once, in
an `enums` block, and referenced by name — has an exception it cannot state.
`fixtures/mixed-onroad.esm` carries `run_brakingOpModeID` as a bare `0.0`
literal with a comment, and three equations key on it: the two braking-rate
lookups into `operatingmode` and the classification's braking arm. A reader who
renumbers operating modes has to find a literal rather than an enum member.

**Falsified, so the failure is attributable.** The same document with
`"Braking": 99` validates. The zero is the whole of it, not the `makearray`, not
the document-level `enums` block and not the `enum` op.

**One secondary observation**, recorded because it would mislead a reader of the
error output: once the schema rejects the `enums` block, the structural pass
reports four further errors of the form `Variable 'operating_mode' referenced in
equation is not declared`. Those are downstream of the first and disappear with
it; they are not a second defect.

**Fix shape.** Drop the `minimum` from `EnumDeclaration.additionalProperties`,
or widen it to the whole integer range. Negative values matter for the same
reason: `opmodepolprocassoc.polProcessID = -1` marks the unassociated
drive-cycle operating modes — 24 of that table's 27 rows in the
`process-evap-leaks` snapshot — and a MOVES table that uses −1 as a real code is
not unusual. An `enums` member is not an index: it resolves to a NUMBER used in
arithmetic and in `join.on` key comparisons, and the two 1-based constructs in
the format (index-set coordinates and `makearray` regions) are validated
separately.

