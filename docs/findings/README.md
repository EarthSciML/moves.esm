# Findings: conventions the format or the toolchain could not express

Ten things PLAN.md §3 Phase 1 and Phase 2 assumed, or that an author would
reasonably assume, that do not hold at the pinned toolchain (`esm-version.lock`:
EarthSciAST `b680f5301`, EarthSciIO `8e1df2280`, `--features esio,parallel`).

F1–F6, F9 and F10 each have a minimal `.esm` repro in this directory; F7 and F8 are
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
| **F1** | A nested §4.7 `subsystems` mount drops a leaf's `join.on` key columns | build | no |
| **F2** | A top-level `models` `{ref}` does not merge the referenced file's `index_sets` | validate | no |
| **F3** | An `enums` block does not cross an `expression_template_imports` edge | load | no |
| **F4** | An `aggregate` range symbol named `t` makes `join.on` match nothing | — | **yes** |
| **F5** | `skolem` / `distinct` / `rank` value invention does not evaluate | — | **yes** |
| **F6** | A component with only scalar variables has no assertable state | assertion | no |
| **F7** | `esm round-trip` resolves a relative `ref` against the CWD | load | no |
| **F8** | A layered template library does not round-trip to a self-contained form | re-load | no |
| **F9** | A relational document evaluates but cannot be written to a file | emit | no |
| **F10** | The evaluable-core op `true` panics at evaluation | evaluation (panic) | no |

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

`F9_no_emit_path_for_a_relational_document.esm`.

**Blocks the Phase 2 exit criterion, independently of the data provider.**

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

**Polarity.** Unlike F1–F6, this repro's assertion passes. Its tripwire in
`run-tests.sh` is therefore the `simulate` command, checked in both directions:
the document must still evaluate, and must still fail to emit.
