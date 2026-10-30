# Authoring conventions for MOVES `.esm` documents

The representation spine (PLAN.md §3, Phase 1), as amended by the first
vertical slice (Phase 2). Every later phase inherits these decisions, so this
document is the reference and `lib/`, `components/`, `runs/` and `gates/` are
the worked proof of each one. Phase 2 changed four of them and added three;
each is marked **[Phase 2]** where it appears. Where a rule can be
checked by a machine it is, in `tools/check-conventions.py`, run by
`./run-tests.sh` — the rules below that a review would otherwise have to
eyeball are marked **[checked]**.

Two companions: `docs/nonroad-logging-county.md` is the verified port
specification these conventions were fitted to, and `docs/findings/README.md`
records fifteen things the format or the toolchain will not do, each watched
by `run-tests.sh`.

---

## 1. One `.esm` per calculator or generator

A MOVES calculator becomes one document with one top-level model. It declares
the index sets it needs, so it validates and runs its own inline tests standing
alone — `./esm test components/deteriorated_emission_rate.esm` is a complete
check of that calculator, with no assembly and no data.

Components carry **no clock** (PLAN.md §1.2). Every MOVES quantity is
algebraic; nothing here is integrated. `esm test` evaluates observeds without an
ODE solve, so the `D(clock) ~ 0` crutch earlier probes needed is gone.

## 2. Tables stay tables

A MOVES table becomes **one column array per field over a row index set** — the
relation, not a reshaping of it. Column order follows the source table's, so a
reader can hold the `.esm` beside the SQL step table in the corresponding
`moves.rs` calculator and check it column by column.

```
"rate_SCC":           shape ["rate_rows"]     nremissionrate.SCC          column 1
"rate_engTechID":     shape ["rate_rows"]     nremissionrate.engTechID    column 2
"rate_polProcessID":  shape ["rate_rows"]     nremissionrate.polProcessID column 3
"rate_meanBaseRate":  shape ["rate_rows"]     nremissionrate.meanBaseRate column 4
```

Consequences worth stating, because each one is a decision that could have gone
the other way:

* **A row index set is anonymous.** `rate_rows` is `{kind: "interval", size: 5}`
  — a row count, not a meaning. The meaning is in the key *columns*. Encoding a
  key as a categorical index set whose members are the key values reaches the
  same equality classes and is valid (CONFORMANCE_SPEC §5.5.8 says so
  explicitly), but it transcribes data into the schema and the legible form
  needs the column.
* **Prefix every column with its relation.** `rate_polProcessID`,
  `det_polProcessID`. Two relations in one component regularly carry the same
  field name, and a join names both sides.
* **An output relation carries its key as COLUMNS, never as axes** **[Phase
  2]**. This is the same rule, and it is what makes a *ragged* key set
  expressible. `nr-logging-county`'s 144 rows are 36 `(SCC, modelYearID)` pairs
  × 4 pollutants, and the 36 are not a rectangle: the three SCCs span 3, 4 and
  29 model years, each set by that equipment point's `nyrlif`. A shared `[SCC ×
  modelYear × pollutant]` grid carries 348 keys against the snapshot's 144 — a
  `require_exact_key_set` failure, and the mirror of the binary64 `modfrc ≤ 0`
  case that emits four too few. `components/movesoutput_aggregation.esm` is one
  `output_rows` axis with `out_SCC`, `out_modelYearID` and `out_polProcessID`
  beside the value, so adding the other two SCCs is adding rows. The `ragged`
  index-set kind the schema advertises for exactly this WOULD serve, and this
  port does not use it: a ragged range binds the position and a body gathers the
  member explicitly (esm-spec §4.3.1, finding F14). A flat row relation with the
  parent as a key column needs neither the padded member array nor the axis
  machinery, so the rule above stands on its own merits rather than on a defect.
* **A component always has at least one array.** This falls out of the rule, and
  it is load-bearing for a reason unrelated to legibility: a component with only
  scalar variables has no assertable state under `esm test` (finding F6).

## 3. Every join is a `join.on`; a `filter` carries a genuine predicate **[checked]**

An equality between key columns is a `join.on` clause with a key-pair list.
A `filter` carries a range test, a null guard, a set membership — never an `ON`
clause in disguise.

```jsonc
"join":   [ { "on": [["time_monthID", "zmh_monthID"],
                     ["time_hourID",  "zmh_hourID"]] } ],   // the equality
"filter": { "op": "and", "args": [                          // the predicate
              { "op": ">=", "args": [ {"op":"index","args":["time_hourID","k"]},
                                      "daytimeHourFirst" ] },
              { "op": "<=", "args": [ {"op":"index","args":["time_hourID","k"]},
                                      "daytimeHourLast" ] } ] }
```

Both are on one node in `components/exhaust_adjustment.esm`, which is exactly
where confusing them would be easiest, so that file is the worked example of the
distinction.

Three reasons this is a rule and not a preference:

1. **Cost.** A `join.on` gate *drives enumeration* — cost `O(matches)`, not
   `O(∏ranges)` (CONFORMANCE_SPEC §5.5.8). The same equality in a `filter` is a
   full nested loop. Measured by `gates/` on the reference machine: 1.0×10¹⁰
   candidate pairs gated in ~0.27 s against 4.0×10⁶ ungated in ~3.5 s.
2. **Legibility.** The `.esm` should read like the SQL it ports. A reader
   looking for the joins finds them in one field.
3. **Checkability.** `tools/check-conventions.py` rejects an `==` anywhere
   inside an aggregate `filter`. The only exception in the tree is
   `gates/equijoin_undriven_control.esm`, which is that shape on purpose; it is
   allow-listed by name.

**Which clause you write FIRST decides what the node costs**, because only one
gate drives and the reference drives the first it can resolve. That is §25, and
it is worth a factor of 47 on this repository's largest aggregate.

**A composite key is one clause with several pairs**, not several clauses.
§5.5.8: a combination is admitted iff *every* listed pair agrees, and "the
canonical composite key is the §5.5.1 rule-4 `skolem` tuple of the per-pair
values, in the order the pairs are listed". The author writes the pair list; the
gate builds the skolem tuple. Several pairs over *different* symbol pairs are
several gates, which compose by conjunction.

**A semi-join is a clamped match count, `row_is_present`** **[Phase 2]**. *Does a
matching row exist* is the shape every precomputed key needs — the two SCC
ladders, state-default precedence, the `getind.f` year rule, the RunSpec sector
and fuel selections. Spell it as a `"semiring": "sum_product"` faq with
`"expr": 1.0` (or a 0/1 indicator), wrapped in lib/keys.esm's `row_is_present`,
which clamps the count to 1: 1 on a match and 0 on none, and bind it at the call
site as an explicit `> 0` comparison. The body carries no value. (It read `1.0`
for as long as `true` panicked at evaluation — F10, now fixed upstream in
EarthSciAST `a1a592ecf`, which also refused the other nine core-but-unevaluable
ops at build rather than letting them reach `unreachable!()`.)

It was spelled `"semiring": "bool_and_or"` until esm 0.3.1. CONFORMANCE_SPEC
§5.6.1 (EarthSciAST `1b6e7099f`) has the numeric evaluators REJECT an
array-valued `bool_and_or` reduction — a faq with an output index that
contracts another — and run only a scalar one, so under 0.3.1 every component
that spelled a semi-join that way errored at build under `esm test`, 353
assertions in twelve files. The clamped count is the same OR: a sum of terms
that are each 0 or 1 is at least 1 exactly when one of them is 1, and every
cell of the twelve files reproduces bit for bit. `onroad/model.esm` and
`nonroad/model.esm` still spell `bool_and_or`: `esm simulate`'s build pipeline
admits it (EarthSciAST `3c7a717bb`, "pipeline route only"), so the RunSpecs
evaluate, but the same faq would be refused on the compile path, and they
should move to `row_is_present` too.

**A relation cannot be joined to itself** **[Phase 2]**. Two `ranges` over one
index set leave every key column unresolvable, because resolution is by axis
(finding F11) — a build error, not a silent zero. Three joins here want a
self-join: `nrstatesurrogate`'s county row against its state row, the growth
series against its own previous year, the age walk against the previous age.
Each materializes a **second relation over a second index set** instead
(`surrogate_target_rows`, `growth_factor_rows` beside `growth_query_rows`), or
evaluates the same lookup twice at two arguments.

**An unmatched row contributes the additive identity, and is still emitted.**
The BSFC carrier row in `components/deteriorated_emission_rate.esm` has no
deterioration partner, reads 0, and stays in its relation. That is a rule about
what a JOIN does — a missing partner is a zero, not a deletion — and it holds
everywhere.

**It is not a rule about the output key set, and the two were conflated**
**[Phase 2]**. An earlier draft of this section said a document must never
reproduce the Fortran's `modfrc <= 0` row suppression. That is measured to be
wrong, and expensively so:

| skip predicate | float32 | binary64 |
|---|---|---|
| `modfrc <= 0` (the reference) | **144** | 140 |
| `modfrc < 0` | 188 | 188 |
| no skip at all | 188 | 188 |

Forty-four of the fixture's candidate cohorts have a grown fraction of
*exactly* zero, so dropping the skip over-emits by 44 in either precision.
**Reproduce the reference's control flow.** `components/movesoutput_aggregation.esm`
is the one file that decides membership, and it spells both suppressions as
columns: `out_pollutantIsSelected` (J25) and `out_cohortIsPopulated`
(`prccty.f`). Every other stage keeps its rows and lets an unselected key carry
a zero, because an intermediate's row set is nobody's answer.

The narrow claim that survives is about ONE cohort: SCC 2260007005 / MY2018,
whose fraction is 5.96 × 10⁻⁸ in float32 and exactly 0.0 in binary64. Nothing
written in a document distinguishes those; the evaluation precision does.

**What is *not* an equi-join** — three cases `docs/nonroad-logging-county.md` §3
names, and how each is spelled:

| Case | Spelling |
|---|---|
| HP containment, `hpMin ≤ hpAvg ≤ hpMax` | a `filter`. It is a genuine range predicate. |
| The two SCC fallback ladders | precompute an effective-key column with `lib/keys.esm`, then join on it |
| State-default precedence (26 beats 0) | same: precompute the effective key |

The last two keep the run-time relational step a plain equi-join and put the
precedence logic in one place.

## 4. `enums` for the literals, and where they can live

No magic integer appears in an expression. `pollutant.OxidesOfNitrogen → 3`,
`process.RunningExhaust → 1`, `month.August → 8`, `day_type.Weekday → 5`.

`polProcessID` is a *packed pair*, so it is built rather than written:

```jsonc
{ "op": "apply_expression_template", "name": "pol_process_id", "args": [],
  "bindings": { "pollutant_id": { "op": "enum", "args": ["pollutant", "OxidesOfNitrogen"] },
                "process_id":   { "op": "enum", "args": ["process", "RunningExhaust"] } } }
```

There is no bare `301` anywhere in the components' equations, at either end of
the join.

**An `enums` value must be a POSITIVE integer** **[Phase 2]**
(`esm-schema.json`: "symbol-to-positive-integer mappings"). Three identifiers in
this chain are zero — the national-default `stateID`, the default scrappage
curve's `NREquipTypeID`, and the `hourID` a NONROAD output row carries — and
none can be an enum. Each is a named `parameter` with the reason in its
description; `nationalDefaultStateID` is the one that appears most.

**An assembly restated the UNION of its leaves' enums, until EarthSciAST PR
#353** **[Phase 2] [retired]**. `enums` merge across a top-level `models`
`{ref}` mount into one registry, first declaration wins, and a colliding value
is applied **silently** — two leaves declaring `probe.Symbol` as 1 and 2 both
read 1 (finding F13). Where the winner merely lacks a symbol it is loud instead,
which is how it surfaces in practice: `geographic_allocation.esm` and
`fuel_properties.esm` both declare `nonroad_fuel_type` and only one has CNG.
That was finding F13, and PR #353 ended it: a mounted file's `enum` ops resolve
against that file's own block, so a leaf reads its own symbol whatever the
assembly says. The restatements are deleted — 16 enums in
`runs/mixed_onroad_run.esm`, 11 in `runs/evap_leaks_run.esm`, 6 in each 7c
document — and the two assemblies that keep a block keep only what their OWN
equations name. `tools/check-conventions.py`'s rule lost the comparison with
them and now checks only that a mounted `{ref}` resolves and parses.

**An `enums` block is file-local, and until EarthSciAST PR #341 it did not cross
a template import** (esm-spec §9.3; finding F3, retired). A library may now
declare its own enums and resolve its own `enum` ops against them. Each
component still declares the enums IT uses. Of the two routes the defect forced,
one is gone and one was never a workaround:

* a **library declares the codes it branches on** — `lib/conversion.esm`'s
  `activity_unit` (and `emission_unit` until §105). They were zero-parameter
  constant-fragment templates (§9.6.1) until PR #341; they are an `enums` block
  now, still READ through templates of the same names, because the call sites
  pass a code by name and never a literal. **A library's `enum` op resolves in
  the library** (§9.7.5), so an importer needs no copy: one that declares no
  enums at all still evaluates, and one that declares `activity_unit` at other
  values changes nothing the library computes. Only an op still spelled by a
  `param` when it reaches the importer resolves there;
* a **parameter the call site binds to an `enum` op** in its own file — every
  identifier `lib/identifiers.esm` touches. That is the second route, and it
  stays: those are the IMPORTER's identifiers, not the library's, so the
  library has nothing to declare.

Values come from `docs/nonroad-logging-county.md` §5, which is the inventory of
every literal the chain depends on.

## 5. Composition: mount leaves as top-level `{ref}` models

A run-level assembly (`runs/micro_exhaust_run.esm`) mounts each leaf as a
**top-level `models` entry that is a `{ref}`** and reaches into it by scoped
reference:

```jsonc
"models": {
  "Rates":  { "ref": "../components/deteriorated_emission_rate.esm" },
  "Adjust": { "ref": "../components/exhaust_adjustment.esm" },
  "Rollup": { ... "join": [ { "on": [["Rates.rate_polProcessID",
                                     "Adjust.adj_polProcessID"]] } ] ... }
}
```

A scoped name resolves as a `join.on` key column, so the roll-up joins two
mounted relations without either leaf knowing it was mounted.

**This is not the form PLAN.md §3 assumed, and the difference is forced.** A
nested `subsystems: {Rates: {ref}}` mount used to rename a leaf's variables while
leaving its `join.on` clause naming the old bare names, so any leaf with a
data-column join — every relational leaf — failed to build once mounted (finding
F1). **That is fixed** (EarthSciAST `a5e8a7d94`: the mount's rename now reaches
`join.on`, `overlap.src_env`/`tgt_env` and a resolved `on_gate`'s columns), so
the nested form §4.7 documents is available again, and it is the one that merges
index sets.

This port's assemblies still use the top-level `{ref}` form the defect forced.
That is deliberate: they work, they are tested, and rewriting them buys nothing
today. A *new* assembly may use either, and should prefer the nested form.

**An assembly declares only its OWN axes; a mounted leaf's merge across the
mount.** This is new, and it is the reversal of what this section said for two
phases. The cost of the working form *used* to be that index sets do not merge
across it (finding F2), so every assembly restated the axes of every file it
mounted. **F2 is fixed** (EarthSciAST `19f929981`, merged `859ef5e93`, PR #208):
a top-level `{ref}` now merges the leaf's `index_sets` into the mounting
document's registry and applies §4.7's conflict check at that edge. The
restatements are **gone** — 109 entries across the four assemblies, `evap_leaks`
23, `micro_exhaust` 5, `mixed_onroad` 18, `nr_logging_county` 63 — and every
one of the four `esm test` outputs is byte-identical to before the removal.

What is left in an assembly's `index_sets` is what the assembly itself declares
and no leaf does: `micro_exhaust_run`'s `micro_run_fuel_kind_rows`, and
`nr_logging_county_run`'s `run_scc_rows`, `run_model_year_rows` and
`run_engine_fuel_kind_rows` — the one-row key relations that pin the run's
scope. `evap_leaks_run` and `mixed_onroad_run` have no axis of their own and so
have **no `index_sets` block at all**, which is the honest shape: everything
they are indexed over belongs to a leaf.

An assembly's own equations shape freely over a mounted leaf's axes — the roll-up
in `mixed_onroad_run` is over `output_rows` and `svp_rows`, neither of which it
declares — and that is the merge doing the work, not an omission. **A redeclaration
is still legal when it is deep-equal**; it is simply noise, so do not write one.

`tools/check-conventions.py`'s `assembly-index-sets` rule is **deleted**, not
weakened. Its second half required the restatement it would have removed, so the
rule and the documents had to move in one change; and a rule whose subject no
longer exists cannot fail, which reads like coverage. Five rules remain. The
enum one is now an `assembly-ref` rule: PR #353 made a leaf resolve its own
symbols, so the union comparison went the way the index-set comparison went
before it — deleted rather than weakened.

What replaced it is a **falsifiable** check rather than a comparison of two
copies: `run-tests.sh` stage 6 writes `runs/.index_set_merge_probe.esm` — the
micro assembly with `rate_rows` restated one larger than its leaf declares it,
`tools/make-index-set-probe.py` reading the true size off the leaf — and requires
the loader to refuse it as `subsystem_index_set_conflict`. Stage 1 already covers
the positive half for free: the same assembly shapes a variable over `rate_rows`,
so a merge that stopped happening would stop that document validating. Measured
on all nineteen mount edges of the four assemblies, before the removal and again
after: every one raises the conflict, naming both definitions and suggesting
`index_set_rename`.

**A mounted leaf's own tests do NOT run under the mount.** They used to, and
this section used to call that a feature — the check that mounting preserved
their meaning. Upstream removed it deliberately (EarthSciAST `d2f2d328e`, now
normative as esm-spec §6.6): a mounting document may legitimately change the
conditions a leaf asserts under — a `variable_map` entry, a mount-edge
`bindings`, a mount-edge `expression_template_imports` — so re-running the
leaf's assertions inside the assembly reports failures the leaf never claimed
anything about. The loader now DROPS a mounted component's `tests` at the
top-level `{ref}` edge — a *subsystem* mount never ran them, since a test
targets a top-level component — and `esm test` names every mount edge it found,
so the components a run did not assert on are visible rather than silently
absent. F21's document measured the two forms disagreeing about this on the old
binary; they agree now, and F21 itself is retired (PR #345).

Measured here at the `3aa046d65` rebuild: `esm test ./components ./runs …` goes
**1444 assertions to 913**, and all 531 of the difference are leaves that were
being re-asserted under the four assemblies — `nr_logging_county_run` 296 → 9,
`mixed_onroad_run` 163 → 30, `evap_leaks_run` 107 → 26, `micro_exhaust_run` 39 →
9. **No assertion went unrun.** Each of the nineteen mounted leaves is its own
test target under `components/`, and every one of those files' own counts is
unchanged. What is gone is the *second*, under-the-mount evaluation of them. An
assertion an assembly wants to make about a mounted leaf is the assembly's own
to write, which §18 describes. Since PR #345 it may simply name the scoped
variable — `runs/evap_leaks_run.esm` asserts
`Emissions.emis_weightedMeanBaseRate` directly, and the variable that existed
only to make it assertable is gone (F21, retired).

## 6. Reused shapes are `expression_templates` in `lib/`, imported by reference

The eight shapes `docs/nonroad-logging-county.md` §4 names live once, in five
template-library files grouped by the stage of the chain that reaches for them:

| file | shapes |
|---|---|
| `lib/identifiers.esm` | `pol_process_id`, `scc_zero_tail` |
| `lib/keys.esm` | `scc_equipment_chain_key`, `scc_lookup_ladder_key`, `state_default_precedence` (§4.5, §4.6) |
| `lib/emission_factors.esm` | `deterioration_age`, `deterioration_factor` (§4.1), `carbon_balance_ef` (§4.8) |
| `lib/adjustments.esm` | `exhaust_temperature_adjustment` (§4.2), `oxygenate_adjustment` (§4.3), `im_blend` |
| `lib/conversion.esm` | `hp_hour_unit_conversion` and `gallon_unit_conversion` (§4.4, one template per `unitcf.f` arm, §105), `temporal_scale` (§4.7), `annual_activity_hours`, the activity-unit codes, `CVTTON` and its inverse |
| `lib/population.esm` **[Phase 2]** | `pop_file_rounding`, `truncate_toward_zero`, `linear_series_interpolation`, `annualized_growth_factor`, `median_life_years`, `year_over_year_scrap_fraction`, `scrappage_sales_growth`, `surviving_equipment` |

A component imports the two or three it uses, with `only` naming them, so the
import edge documents the dependency.

* **Libraries layer.** `lib/keys.esm` imports `lib/identifiers.esm` and invokes
  `scc_zero_tail` from inside two template *bodies* (§9.7.3), so the
  decimal-truncation arithmetic exists once for both SCC ladders.
* **Constants are zero-parameter templates**, not repeated literals:
  `grams_per_pound`, `co2_mass_per_carbon_mass`,
  `exhaust_temperature_reference`, `days_per_week`.
* **A template covers both arms of a branch.** `exhaust_temperature_adjustment`
  is `exp((T ≤ 75 ? a_cold : a_hot)·(T − 75))` — one instantiation, six uses,
  and the 2-stroke uses carry both coefficients 0 rather than needing a special
  case. It is an *exponential*, not the quadratic an early PLAN.md draft called
  it.
* **The cap goes on the argument.** `1 + A·min(age, cap)^B`. Capping the product
  instead is wrong wherever `B ≠ 1`, which is every 4-stroke tech.
* **`temporal_scale` carries both halves.** The `7×` and the `1/ndays` enter the
  engine's product at different places; combining them wrongly double-applies
  the monthly factor, a ≈2.6× error for a 31-day month.
* **The file-format rules are templates too** **[Phase 2]**. `pop_file_rounding`
  is the `.POP` file's `%17.1f` and `truncate_toward_zero` the `/GROWTH/`
  packet's `%20d`. Neither is a precision artefact to be tidied away: the first
  turns 0.463484 into 0.5, a 7.9% change the snapshot cannot be matched
  without, and the second decides the SIGN of a near-zero growth factor and
  with it whether a model year exists. They live in `lib/` under their own
  names so that a reader meets them as rules rather than as stray arithmetic.
* **Two namespaces that look alike get different prefixes** **[Phase 2]**. An
  EMISSION-rate unit is what `unitcf.f` selects on; an ACTIVITY unit
  (`activity_unit_hours_per_year`) is what `modyr.f` selects on; the `g/gallon`
  arm reads both. Phase 1 named the first pair `activity_unit_*`, which was
  wrong and was renamed `emission_unit_*`; since §105 the emission-rate code is
  not a value at all but the CHOICE of template at the call site.
* **`lib/` holds template-library files and nothing else** (§9.7.1) **[checked]**.

## 7. Discrete time is an index-set axis, and `t` is never a loop symbol

MOVES time is a discrete `(yearID, monthID, dayID, hourID)` key, **not** the
domain's continuous `t`. The run's temporal scope is a row set with four key
columns that joins to `zonemonthhour` like any other relation
(`components/exhaust_adjustment.esm`). Nothing differentiates with respect to
`t`; widening a run to three months adds rows and changes no expression.

**Never name a loop symbol `t`** (or `_var`) **[checked]**. `t` is the
independent variable, and a range symbol that shadows it makes the join gate
match nothing — silently, returning 0, with the document validating (finding
F4). This cost a real bug during Phase 1, in precisely the component whose axis
*is* a time axis. Use `k` for a time-key row symbol, `r`/`d`/`p`/`z` for other
relations.

**This is now enforced rather than merely advised — but only in Rust.**
EarthSciAST `ee067f5b6` rejects such a document at load with a named
`reserved_index_symbol` diagnostic. **Julia accepts it**, which I verified
directly: the same document loads under Julia and is refused under Rust.

That divergence makes the convention matter more, not less. Julia's binder
precedence is the opposite of Rust's, so the join is unaffected there — but the
binder then shadows the independent variable, and one measured document returns
**35.0 under binder `k` and 10.0 under binder `t`**, validating either way. A
document authored and checked against Rust alone is safe; one checked against
Julia alone is not. Since this port runs through the Rust CLI, the toolchain
catches it for us.
Rejecting rather than making the binder win is the right call — an index symbol
is the author's free choice (§4.3.1), while the alternative inverts name-first
precedence at nine sites and would still leave the node unable to name the
independent variable at all.

## 8. `coordinates` to label output rows back to their keys

`coordinates` marks an existing column array as a physical coordinate and
attaches CF metadata, so an emitted row can label back to `countyID` / `SCC`
rather than to a bare `0..N` integer axis (esm-spec §2.1):

```jsonc
"coordinates": {
  "rate_scc":          { "source": "rate_SCC",           "standard_name": "source_classification_code" },
  "rate_pol_process":  { "source": "rate_polProcessID",  "standard_name": "pollutant_process_identifier" }
}
```

It is purely additive and metadata-only — nothing in the current toolchain emits
it — so it is declared and not asserted. It costs nothing now and is the hook
the Phase 2 output stage will need.

## 9. `skolem`: use the composite `join.on`, not the value-invention ops

PLAN.md §3 asks for `skolem` for canonical composite keys. The supported
spelling is the multi-pair `join.on` of §3 above: §5.5.8 defines that clause's
canonical key *as* the skolem tuple of the per-pair values. The explicit
`skolem` / `distinct` / `rank` machinery — a derived index set whose members are
the distinct tuples — validated and materialized empty until EarthSciAST PR #342
(finding F5, retired). It evaluates now, so a composite-key axis is available
where one is genuinely wanted; the multi-pair `join.on` remains the spelling for
a canonical key, because it says the same thing with less machinery.

## 10. Precision, and what the document must not do about it

`moves.rs`'s NONROAD port is bit-exact `real*4`. `domain.element_type:
"Float32"` **is honoured**, per operation, and a variable may override it with
its own `element_type`. **§17 is the operative section; read it before
declaring a precision.** What follows is the rule that has not changed.

**Author for float32 semantics** **[Phase 2]**. Evaluating the whole document
in float32 reproduces all 144 rows at 4.9 × 10⁻⁶ — the independent oracle
confirms it — while binary64 loses four cells of `nr-logging-county` to an
exact zero, carrying 2.4 × 10⁻⁵ g out of 5,146 g, so per-pollutant sums still
agree to 2.6 × 10⁻⁶ and only the key set notices. So write the reference's
arithmetic and the reference's control flow. Do **not** design the document
around binary64's four missing rows, and do not add a per-key allow-list; that
was considered and rejected.

One correction to how that used to be stated, because it was acted on: those
four cells are *not* what the fixture's element type recovers. The fixture
carries the grown fractions as a `const` whose third value is positive in either
precision, and its twelve rows never depended on the precision at all. §17.5 has
the account. What the element type *does* now recover in the fixture is the
residue those four cells hang off — the age-3 survival, `5.9604645e-08` against
binary64's exact `0` — which the fixture computes from the real curve and
asserts. The step from that residue to the four rows is the fold, and the fold
is blocked by **F24**, not by the format: see §19.

**What this costs the inline tests — measured, and not what this section used
to predict.** It said the expected values must move to the float32 values of
the same expressions, mechanically. They must not, and doing it would have been
a mistake: the only float32 values available to write down are a
specification's seven-digit prints, so the assertion would end up pinned to a
rounded transcription rather than to the arithmetic. What moves instead is the
*tolerance*, to exactly 2⁻²³ — one binary32 epsilon, the tightest a binary32
evaluation can ever satisfy — **per test, never document-wide**, because a
blanket epsilon default would let a corrupted ten-digit key pass an assertion
of the right one, which is F18's own warning one level up. §17.4 has the
numbers.

## 11. Data comes from `data_sources`

`fixtures/nr-logging-county.esm` declares all twenty-six snapshot tables and
**consumes seventeen of them**. It is the only document in this repository whose
numbers come off disk; `components/` stay on `const` arrays, deliberately, and
§12 says why. The conversion, per column, is esm-spec §8.5's:

```jsonc
"emr_meanBaseRate": {
  "type": "parameter",            // not "unknown": a data-fed column is an input
  "units": "1", "default": 0.0,
  "shape": ["nremissionrate_rows"],
  "update": { "kind": "data",
              "source": "nr_logging_county_nremissionrate",
              "from": { "file_variable": "meanBaseRate" } }
}
```

Seven things about ingest that were paid for once and should not be re-derived.

* **The format is `metadata.esio_format`, not a `format` key in
  `reader_options`** — that is rejected as an unknown reader option (§8.9.1,
  working as specified). `tools/check-sources.py` flags the old spelling.
* **A `url_template` needs an absolute `file:///…`.** It is neither
  environment-expanded nor resolved relative to the referencing document, and
  the first path segment of a relative URL is eaten as the URL *host* (finding
  **F15**). So the checked-in fixture carries a `${MOVES_SNAPSHOTS}` placeholder
  it cannot itself ingest, and `run-tests.sh` materializes a resolved copy under
  `.fixtures-run/`. That copy is a path substitution and nothing else.
* **`float_columns` is mandatory, on almost every table** — the emission
  quantities are 12-place decimal TEXT despite the sidecar `.meta.json` calling
  them float64. It is also how a numeric KEY stored as utf8 becomes a key:
  `SCC` is listed in six tables' `float_columns`, and every SCC is below 2^53 so
  the decode is exact and a join on one is still exact.
* **An integer column with a NULL is refused,** by name, and listing it in
  `float_columns` is the fix — the nulls arrive as NaN and no join reaches them.
  `nrgrowthindex.growthIndex` is int64 with 43 null rows out of 50,955.
* **A row axis is sized by `extent` discovery, never by a literal.**
  `"metaparameters": {"n_nremissionrate": {"type": "integer", "default": 0}}`,
  `"index_sets": {"nremissionrate_rows": {"kind": "interval", "size":
  "n_nremissionrate"}}`, and `"extent": {"metaparameter": "n_nremissionrate"}`
  on the source. A fixture that wrote `55471` would be asserting the snapshot's
  shape rather than measuring it. The default is `0`, and a 0 that survives to
  evaluation is a build error rather than a small answer.
* **Every observable is a relation, including a one-row one.** In a document
  that ingests, a SCALAR variable is not materialized: the assertion errors and
  an expression that reads one evaluates to `NaN` (finding **F16**). So the
  fixture's run-level quantities — the ambient temperature, the oxygen weight
  percent, `adjtime` — are columns over a one-row `run_scope_rows`. That is the
  better shape anyway, and it survived the widening to six equipment points
  unchanged: what varies per point moved to a six-row `equipment_point_rows`
  and the run scope stayed one row, so no run-level equation was touched. §22
  is the rule that came out of doing it.
* **~~`hp` is not a unit the registry knows.~~ It is, and §58 is what replaced
  this bullet.** It was true when this section was written, and it stopped being
  true at EarthSciAST `c31ea106d` (2026-09-10), which added `mi`, `lb`, `hp` and
  `gal` *because* MOVES is written in them — `hp` is the mechanical horsepower,
  550 ft·lbf/s, and `short_ton` had arrived three weeks earlier. The rule it
  stated — an emission factor in g/hp-hr carries no `units` and names the unit in
  its `description`, so the whole roll-up product and `out_emissionQuant` with it
  are declared unitless — outlived its reason by a week and was still being cited
  in ten variable descriptions, two data-catalog notes and §57.6's table. **§58 is the correction:**
  the rate is `g/(hp*h)`, the product is a `short_ton`, and `out_emissionQuant`
  is a `g` that is checked.

### 11.1 Joining big tables to big tables

The one thing that does not follow from the per-column conversion. A `join.on`
whose key columns are large on BOTH sides is not driven: the fixture's roll-up
over `nrengtechfraction` × `nremissionrate` × `nrdeterioration` did not finish
in twenty-five minutes, and the same contraction with the technology given its
own axis takes four seconds (finding **F17**).

The rule that follows is a modelling one, and it is the same shape as
"tables stay tables": **give the thing the tables meet at an axis.** The mix,
the rates and the deterioration coefficients all key on `engTechID`, so
`engine_tech_rows` enumerates §5.5's exhaust code space and each table joins to
it separately. The check that keeps an enumerated window honest is a total:
`tech_fractionTotal` must be 1 for every cohort, so a code outside the window
shows up as a number rather than as a missing row.

### 11.2 What the fixture covers **[Phase 3, complete]**

All 144 rows of the snapshot's `MOVESOutput`, over the three SCCs the RunSpec
selects, at a worst cell of 4.561 × 10⁻⁶ relative and a worst per-pollutant sum
of 2.079 × 10⁻⁶. `tolerance.toml` carries no `[shortfall]` record for it any
more; `run-tests.sh` fails if one is left behind a comparison that passes.

It was twelve rows for a long time, and the two things that stood between it and
the other 132 are worth keeping written down, because only one of them was ever
about the format.

**The fold was a toolchain blocker, and it is fixed.** `agedist.f`'s thirty-year
fold has a spelling — esm-spec §4.3.1.1's causal self-reference — and the
fixture computes it, six times, once per equipment point, reproducing the
reference's real*4 grown fractions in all 306 cells. What had stopped it was
**F24**: a document that ingests `data_sources` is forced onto the build-pipeline
evaluation path, and that path left a causal self-read unresolved with
`max(NaN, 0)` laundering the sentinel. Fixed by EarthSciAST `de784f3f8`, and
verified here on the **ingestion** axis the upstream build could not reach.

**The equipment-point axis was ordinary authoring, and it was more work than
"widen the axis".** `prccty.f` loops over the `nrsourceusetype` rows the SCCs
select — six of them here, with three sharing one SCC — so the output row is a
SUM over points, the model-year set is the UNION of their `nyrlif`s, and the
union is ragged and gappy. Widening the axis is the easy half; §22 is the other
half.

## 12. Testing

Inline `tests` sections, small `const`-array inputs, hand-computable expected
values (CLAUDE.md; PLAN.md §4). Every number in `components/` comes from
`docs/nonroad-logging-county.md` §6, which read them out of the snapshot
parquet, and the assertions are that document's own worked longhand.

* **Array assertions select a scalar** via `coords` (a 1-based index-space
  position per axis) or `reduce` (`max`, `min`, `mean`, `integral`) — esm-spec
  §6.6.5. `coords` on a row axis is the row-by-row check that keeps a component
  test honest about *which* row is wrong.
* **Tolerance is per assertion, per test, then per model** (§6.6.4). Components
  here declare `rel: 1e-12` at model level, which is a real gate on hand-checked
  arithmetic; `tolerance.toml`'s much looser numbers are for the fixture
  comparison against a `real*4` oracle and are a different question.
* **An expected value is the binary64 value of the specification's own
  expression, and the description says how far it sits from the printed one**
  **[Phase 2]**. `docs/nonroad-logging-county.md` prints float32 figures;
  binary64 lands within ~4 × 10⁻⁶ of them, which is the snapshot's own
  six-significant-figure storage precision. Asserting the printed digits at
  `rel: 1e-12` would fail for the wrong reason, and rounding the assertion to
  the printed precision would stop catching real drift. Where the spec's prose
  and its cited code disagree, the code wins and the component says so: two
  instances so far, `nyrlif` 38 against the code's 39 for §6.3's 750-hour point,
  and two of §6.2's four printed deterioration factors, which are ~2 × 10⁻⁵ off
  the arithmetic in both precisions.
* **A quantity the toolchain cannot compute *here* enters as data, with an
  independent cross-check — and nothing in this repo does any more**
  **[Phase 2, retired]**. `agedist.f`'s thirty-year fold was the last one, and
  both `components/age_distribution.esm` and `fixtures/nr-logging-county.esm`
  now compute it (**F24** fixed upstream, and verified on the ingesting axis
  here). The cross-check that made carrying it safe outlived the carrying and is
  the better half of the convention: the grown fractions must sum to
  `G(2020)/G(1990)`, which the same document derives from `nrgrowthindex` by a
  completely different route, and that check is now made **once per equipment
  point** — six thirty-iteration recurrences landing within 5.3 × 10⁻⁷ of one
  externally derived constant.
* **A test names *what breaks if this is wrong*, not what it computes.** The
  composite-join test says a single-key join would give 131.86 instead of 60.74;
  the window test says the count would be 16 or 24 instead of 13. A description
  that only restates the expression is not worth the line.
* **Assert both arms of a branch.** `the_hot_branch_is_reachable` overrides the
  averaging window to cross the 75 °F branch point, so one temperature template
  is exercised on both sides.
* **`parameter_overrides` are keyed by bare local name** (§6.6.2 rule 3), which
  is what lets the same test text run against a leaf alone and against the same
  leaf mounted.
* **A test costs a whole evaluation of the document, so the number of TESTS is
  the runtime and the number of assertions is free** — and this is now a
  finding, **F31**, rather than a suspicion. `run_model_tests` builds a fresh
  problem, re-reads every `data_sources` table and re-evaluates the whole
  build-time observed graph once per test, and `--filter` selects rows from the
  results AFTER all of them have been evaluated. Measured on
  `fixtures/nr-logging-county.esm` at 144 rows: `simulate` is 16.3 / 16.5 /
  17.7 s over three runs, `esm test` is 532.7 / 545.7 s for all 29 tests and
  566.7 / 539.0 s filtered to ONE of them — not faster, and slower in one of the
  two samples. A 16-copies-of-one-test synthetic is linear
  at ~3.3 s per test and saves 8% when fifteen of the sixteen are filtered away.
  The consequence for authoring is not "write fewer tests" — each of the 29 is a
  distinct claim and merging them would make a failure less diagnosable — but
  it does mean a test added for a single extra assertion is an expensive way to
  buy it, and that profiling belongs on `simulate` rather than on `test`. The
  fix is upstream and has no document-level or harness-level form: read F31
  before spending time on one.

## 13. What `./run-tests.sh` guarantees

Nine stages, in order: the comparator's own falsification suite; schema
`validate`; the conventions above **[checked]**; every inline test;
`parse → emit → parse` fidelity; the join-gate scaling ratio; the
known-limitation tripwire; every `data_sources` declaration against the Parquet
files it names (`tools/check-sources.py`); the fixture run. It must stay green at every commit, and it must stay
*honest* — a fixture stage that says what it did not compare is worth more than
a green one that read nothing.

**Two stages run with the opposite polarity to everything else, and for the same
reason.** The tripwire fails when a `docs/findings/` repro starts **passing**,
because that means an upstream defect is fixed and a workaround in this tree is
now dead weight; read `docs/findings/README.md` when it fires. And the fixture
comparison is *expected to fail today*: `compare-output.py`'s verdict is
unconditional and nothing can tell it to pass, so `tools/shortfall.py` judges
its report against the `[shortfall]` record in `tolerance.toml` and the stage is
green only while the failure is exactly the one written down — a shortfall that
grows is a regression, one that shrinks is progress that has to be recorded, and
one that disappears means the record itself must go.

The fixture stage has four steps and each is load-bearing. It **materializes**
`.fixtures-run/<name>.esm` with the snapshot path substituted (F15), having
first checked that the CHECKED-IN document still cannot ingest; it runs the
fixture's **inline assertions** against the real tables, which is where a column
that arrived as its `default` fails somewhere it can be attributed; it
**emits** every `out_*` variable through `simulate --format csv`, reading the
field list out of the document so the output schema stays the document's
business; and it **compares**.

## 14. Reading a component back

`esm pretty` renders a document's equations, and it is the quickest way to check
that a component still reads like the relational step it ports. Run it from the
document's own directory (finding F7):

```
$ (cd components && ../esm pretty deteriorated_emission_rate.esm)

  Eq 3: rate_polProcessID = makearray([1:1] = 100·1 + 1, [2:2] = 100·2 + 1, …)
  Eq 4: rate_meanBaseRate = [47.98, 283.4, 0.91, 7.7, 0.608]
  …
  Eq 10: detAge = (ageIndex + 1)·hoursUsedPerYear·loadFactor/medianLifeFullLoad
  Eq 11: emissionRate =
           Σ[r] (rate_meanBaseRate[r]·(1 + det_coefficientA[d]
                  · min(detAge, det_ageCap[d])^det_ageExponentB[d]))
           where {d∈deterioration_rows, r∈rate_rows}
           join(rate_polProcessID=det_polProcessID, rate_engTechID=det_engTechID)
```

That last line is the whole convention in one place: a `SUM` over a `GROUP BY`
of a product, `FROM` two relations, `ON` two key columns. Compare it against
J14 in `docs/nonroad-logging-county.md` §3, and against the step table in the
`moves.rs` calculator. If the rendering does not read that way, the component
has drifted.

Note the templates are gone from the rendering — expanded, as §9.6.4 specifies.
That is the right trade: the *source* stays factored and the *rendering* stays
checkable against the arithmetic.

## 15. What Phase 2 could not compute, and how the document says so **[Phase 2]**

Four things in the chain are not in the documents, or are not in them the
obvious way, because the format or the toolchain cannot hold them. Each is a finding with a repro, and each has a
visible place in the `.esm` rather than a silent substitution.

| | What | Where it shows |
|---|---|---|
| **F24** | a causal self-reference is dropped once the document ingests | `fixtures/nr-logging-county.esm`'s `age_grownModelYearFraction` is still a data column, cross-checked against the growth stage's cumulative ratio; `components/age_distribution.esm`, which does not ingest, computes it. (This row was **F12** — the fold had no spelling at all — until EarthSciAST `a83cde55e`) |
| **F23** | a leaf's `domain.element_type` does not survive a top-level `{ref}` mount | `components/age_distribution.esm` stays in binary64 and pins BOTH precisions: its own answer exactly, the real\*4 value named beside it, and the invariant they share asserted |
| **F15** | a `url_template` has no relative or environment form | the checked-in fixture cannot ingest; `run-tests.sh` materializes `.fixtures-run/` and asserts that the checked-in one still cannot |
| **F16** | a scalar has no state in a document that ingests | every run-level quantity is a one-row relation over `run_scope_rows` |
| **F17** | a `join.on` between two large relations is not driven | `engine_tech_rows` gives the technology an axis, and `tech_fractionTotal` proves the window is a superset |

The rule the three share: **say it in the document, at the point where a reader
would otherwise assume the number was computed.** A carried column's
description names the finding, the assembly's description names both blockers,
and the source catalog says what it will prove once ingest lands. A workaround
that is not written down is indistinguishable from a bug.

The corresponding rule for the *fixture* is in §3 and §10, and it is the
opposite of what an earlier draft of this document said: **reproduce the
reference's row suppression**. The `modfrc <= 0` skip removes 44 exactly-zero
cohorts, and a chain without it emits 188 rows against the snapshot's 144 in
either precision.

---

## 16. What the onroad graph changed **[Phase 3]**

Phase 3 is the first slice that is not a self-contained Fortran chain: the
rates-first base-rate path, `mixed-onroad`, specified in
`docs/mixed-onroad.md`. The question it was authored to answer is whether the
conventions above survive a SQL-graph calculator, and the short answer is that
**every rule in §1–§15 held, and four of them are now forced for reasons the
NONROAD slice never met.** Nothing here is a reversal. What follows is the
list, because the reasons matter more than the rules.

### 16.1 Four rules that gained a second, independent reason

**A run-level quantity is a one-row relation — and now it has to be, in every
document.** §11 gives the reason as finding F16: a scalar is not materialized
in a document that *ingests*. Phase 3 found a second, which applies to `const`
components too. A `join.on` key column must be a 1-D data column over an index
set one of the aggregate's ranges draws from, so **a scalar cannot be a join
key at all** — the build refuses it by name:

```
join key column 'runPolProcessID' does not resolve to a loop index of this
aggregate ({"i", "m"}): it names neither a range symbol, nor an index set one
of those ranges draws from, nor a declared 1-D data column over such an index
set
```

`components/onroad_source_bin_distribution.esm`'s `runspec_polProcessID` is a
one-row relation over `runspec_pol_process_rows` for that reason and no other.
The convention is unchanged; its scope is wider than §11 says. It is also a
better failure than F16's: loud, at build, naming the column.

**Reproduce the reference's row suppression** (§3, §15). NONROAD's case is
`modfrc <= 0`. The onroad case is `samplevehiclepopulation.stmyFraction > 0.0`
(`source_bin_distribution_generator.rs:1341`), and it was found independently:
164 candidate rows for this fixture's source type, 39 with the value exactly
`0.000000000000`, and the surviving 125 are exactly the snapshot's cohorts.
Without it the fixture emits 328 rows against 250. Two chains with no shared
code reached the same rule, which is the strongest evidence available that it
is the rule and not an artefact.

**An output relation carries its key as COLUMNS** (§2). Ragged again, and for a
physical reason this time: the 125 cohorts are 41, 40, 23 and 21 model years
for gasoline, diesel, E85 and electricity — the years before E85 and electric
drive existed, and the year diesel passenger cars stopped. The flat-relation shape §22 built applies unchanged — and since PR #352 retired
F14 it is a choice rather than a workaround: a ragged axis does evaluate, it
simply wants a padded `[parent, max length]` member array that a flat relation
with the key as columns has no use for.

**A relation cannot be joined to itself** (§3, finding F11). Two more instances:
the travel fraction's numerator against its HPMS-group denominator, and the
fuel-usage rebase pairing a cohort with other cohorts of its own model year.
Phase 3 measured what the workaround actually costs, which §3 did not say: an
operand of an equation whose left-hand side is shaped over one index set must
itself be shaped over that set, so **the workaround duplicates the whole
relation and not only its key column**.
`onroad_source_bin_distribution.esm` carries `eq_stmyFraction`,
`eq_modelYearGroupIsPresent` and `eq_sourceBinActivityFraction` beside their
`svp_` twins for that reason.

### 16.2 Three things that are new

**A `makearray` region addresses one contiguous range PER DIMENSION, not a set
of disjoint spans.** `"regions": [[[1,1],[5,5]]]` is read as a two-dimensional
region and refused as rank-mismatched against a 1-D sibling. The consequence is
a *modelling* rule, not a syntax note: a relation whose identifier columns are
to be built from `enums` rather than written as bare integers must be **ordered
so that each identifier value occupies one run of rows**.
`onroad_source_bin_distribution.esm`'s twenty candidate rows are grouped by
fuel type and then by model year for exactly this reason — the natural order,
by model year, would need twenty single-cell regions.

**A key column above 2⁵³ is keyed on its components and never materialized.**
`sourceBinID` is `1e18 + fuel·1e16 + engTech·1e14 + regClass·1e12 +
shortModYrGroup·1e10`, about 1.01 × 10¹⁸, where binary64 spacing is 128. So
J22 joins on the four components and no document in this port builds a packed
id. The **inverse** is needed and is safe — `emissionrate`'s 69,200 rows arrive
already packed with no component columns, and `floor(bin/1e16)` has a small
exact quotient — which is what `lib/onroad_activity.esm`'s `source_bin_slot`
is. This is finding **F18** one binary exponent further out, and a second
independent reason this port cannot declare `Float32`.

**A residual assertion needs `abs` alongside `rel`.** `runs/mixed_onroad_run.esm`
recomputes each output row through the mount and asserts the difference against
the leaf's own column is zero. Nine of ten residuals are exactly `0.0`; one is
2.78 × 10⁻¹⁷, because the two expressions group the same product differently
and binary64 rounds them apart by one unit in the last place. A relative
tolerance is vacuous against an expected zero, so the test carries
`{"abs": 1e-15, "rel": 1e-12}` — either bound satisfies an assertion
(`esm-schema.json` `Tolerance`) — and its description says which residual is
not zero and why. Asserting exact zero would be claiming something about IEEE
association that the document does not intend.

### 16.3 One rule that did NOT need to fire, and why that is informative

**§11.1's "give the thing the tables meet at an axis"** — finding F17's remedy,
which turned a 25-minute contraction into 4 seconds by giving `engTechID` its
own axis over the 100–199 NONROAD exhaust code space. The onroad chain joins on
engine technology too, and it did not need the remedy: onroad `engTechID` takes
**two** values here (1, conventional internal combustion; 30, electric drive),
so it is a column.

That is worth writing down because it locates F17 precisely. The finding is
about the **size of both sides of a clause**, not about the semantics of the
key: NONROAD's technology axis was a performance fix because the mix table had
9,554 rows probing 55,471, and the same key over a two-valued column needs
nothing. An author reading §11.1 as "technology is always an axis" would be
generalising a measurement into a rule.

The same goes the other way. §3's table of "what is *not* an equi-join" lists
three NONROAD cases — the SCC fallback ladders, state-default precedence, and
hp containment. **The onroad chain has none of the first two.** What it has
instead is two joins on an inclusive model-year range
(`beginModelYearID <= MY <= endModelYearID`, in `fleetavgadjustment` and
`temperatureadjustment`), and those take the same spelling hp containment
takes: a `join.on` over the non-range keys plus an inclusive-range `filter`.
So the *list* is fixture-specific and the *spelling* generalises, which is the
distinction §3 should be read for.

### 16.4 A new finding, and what it cost

**F19: a constant-folded scalar right-hand side loses the left-hand side's
array shape.** An elementwise equation whose predicate is a compile-time false
folds to the scalar `0.0`, and the declared shape is discarded — the variable
has no cells rather than being an array of zeros. Loud, and it names the
variable.

What it removes is one testing technique: a component cannot exercise the FALSE
arm of a guard whose predicate is a run-level scalar by overriding that scalar,
which is the natural way to test a zero-denominator guard.
`docs/findings/README.md` F19 records both replacements, and both are better
tests — `onroad_travel_fraction.esm` exercises `share_of_group`'s guard with a
probe **row** whose group total is zero, which tests the join as well as the
arithmetic, and `onroad_energy_output.esm` exercises its two clamps by moving
the **temperature** both arms are reachable from, which is how the model will
actually meet them. So it cost two rewrites and no capability.

### 16.5 One rule that is about the fixture rather than the format

**The run scope comes from the execution database's `runspec*` tables, never
from the RunSpec XML.** `mixed-onroad.xml`'s sha256 matches
`provenance.json` and it nevertheless disagrees with the captured run on
month, hour, day type, fuel type and pollutant, because it was rewritten when
the mixed scenario was split in two and re-hashed without re-capturing the
tables (`docs/mixed-onroad.md` §0.1). A document scoped from the XML emits 250
rows with the wrong month and hour in every one, which the exact-key-set gate
rejects wholesale — the good failure. The dangerous one is a document that
reads the XML for a single dimension and quietly emits 62 rows.

`components/onroad_energy_output.esm`'s
`the_scope_columns_come_from_the_execution_database` asserts monthID 8 and
hourID 9 against the XML's 7 and 8 for that reason.

### 16.6 What Phase 3 deferred, and why the deferral is in the specification **[since resolved, §26]**

`mixed-onroad` had **no fixture** for a phase, and that was a decision rather
than an unfinished edge. `docs/mixed-onroad.md` §7.3 showed that everything in
the 250-row chain was computable from the snapshot's input tables except one
relation of 46 numbers — the speed-bin-weighted drive-cycle operating-mode
distribution, which canonical MOVES computes inside its worker and drops. §7.4
gave the reasoning: a document emitting 250 correctly-keyed rows carrying an
uncomputed rate fails the per-cell gate for a shape `[shortfall]`'s
`emitted_rows` / `missing_keys` / `extra_keys` record cannot express, and a
document reading the reference's own `baserate_1_2020` passes the gate by
transcribing the answer. Neither is a fidelity test, and §13's rule — a fixture
stage that says what it did not compare is worth more than a green one that
read nothing — applies to *whether to add the stage* as much as to what it
reports.

**The relation is computed now and the fixture is wired** — §26, and
`docs/mixed-onroad.md` §10 — so this subsection is history. It is kept for the
shape of the decision rather than for its verdict, because the next port will
meet the same fork: an uncomputed relation in an otherwise complete chain is a
choice between three things, and only one of them is honest. Emit the rows with
a placeholder and record a shortfall — but `[shortfall]` counts rows and this
failure has the right rows. Read the reference's intermediate — but then the
fixture measures nothing. Or **compute the relation**, which is what §7.3's
decomposition was for: it isolated exactly what was missing, proved everything
around it was right, and thereby made the third option a bounded piece of work
rather than an open-ended one.

What stood in for the fixture in the meantime, and still runs: the four
components check every stage that can be checked without the snapshot, against
numbers §6 read out of it; and `./run-onroad-oracle.sh` extracts §6.5 and
reproduces all 82 rows of `sho` and all 250 of `MOVESOutput` from the snapshot's
own input tables, now taking nothing at all from the reference.

## 17. Declaring the working precision **[float32]**

`fixtures/nr-logging-county.esm` now declares `domain.element_type: "Float32"`
and evaluates in it. This section is what that cost and what it did not. §10
states the authoring rule and points here; this section is the operative
detail.

### 17.1 Twenty variables, no rewritten expressions

The declaration is two kinds of edit to the model, and nothing else — no equation,
index set, data source or `expected` value changed (§17.4 is the third kind of
edit, to ten assertion tolerances):

```json
"domain": { "element_type": "Float32" }
```

```json
"point_SCC": { "type": "unknown", "element_type": "Float64", "shape": ["equipment_point_rows"], … }
```

— the second repeated on the twenty variables that hold an **SCC**, and on no
others. The reference is `real*4` in its floating-point quantities and `INTEGER`
in its keys (`docs/nonroad-logging-county.md` §7.1), and a per-variable
`element_type` is the only vocabulary the format has for that split. `Float64`
is not a rounding preference here: `2260007005` is 135× binary32's exact-integer
limit of 2²⁴ and rounds to `2260006912`, which is a **different equipment
category**, so every `join.on` over it matches nothing (finding F18).

Adding *only* the domain block, measured end to end on the real snapshot **at
the twelve-row version of the fixture**, where the variables were still named
`run_*`: **35 of 87 inline assertions pass**, `run_statePopulation` 83.3 → 0,
`run_allocationFraction` 0.0032383 → 0, `run_surrogateID` 8 → 0, and every one
of the twelve `emissionQuant` cells → exactly 0. Adding the overrides:
**48 of 87**, with no zeros left and every remaining failure a rounding
difference of at most 1.13 × 10⁻⁷. The measurement has not been repeated on the
144-row version (it would now be 343 assertions over six equipment points); what
keeps it live is `docs/findings/F18_control_float32_key_override.esm`, which
`run-tests.sh` runs every time and which asserts both halves — an overridden key
stays exact, and the domain is still `Float32`.

**Not one operator had to be split.** That is the surprising part and it is
worth knowing why, because the rule that makes it true is strict:

### 17.2 The rule: one operator, one precision

Mixing precisions inside a single operator is a **compile error**, not a silent
widening (`esm-spec` §11.3.1):

```
mixed_element_type: operator '*' mixes operands of different element types
— key is Float64 and q is Float32.
```

It is raised at compile time, which is `esm test` / `esm simulate`. **`esm
validate` does not see it** — a document that mixes precisions validates
cleanly, so the conventions checker and stage 1 of `./run-tests.sh` cannot be
the place this is caught. Only running it is.

The escape is not a cast — there is none. §11.3.1's exemption is that a
**comparison or logical operator returns an exact 0/1 flag**, representable in
every precision, so it is context-adopting *to its parent* while its own two
operands must still agree with each other. `sum(quant[i] * (key[i] == k))` is
therefore legal with `quant` binary32 and `key` binary64: the predicate is
evaluated in binary64 and hands the arithmetic a flag, not a key.

### 17.3 Why §3's rule already paid for this

Every place an SCC meets a quantity in this fixture — checked by compiling it,
which is the only thing that checks it — is one of three shapes, and all three
are the exempt one:

| shape | why it is exempt |
|---|---|
| `join.on: [["run_SCC", "mal_SCC"]]` | an equality comparison of two `Float64` keys; the aggregate's `expr` is a `Float32` quantity and never touches the key |
| `scc_zero_tail(scc, 1000)` — `floor(scc/k)*k` | every operand is the key or a literal, so the whole expression is `Float64` (a literal adopts its context) |
| `scc_lookup_ladder_key(scc, has_exact, …)` | the `has_*` parameters are **predicates**, and the call site converts its `Float32` presence column with `{"op": ">", "args": [presence, 0.0]}` — the flag is made outside the template |

The third one is the load-bearing accident. `lib/keys.esm`'s ladder templates
take booleans rather than presence columns because §3 requires the presence test
to be a `max`-semiring aggregate and the ladder to be a separate key column —
a *relational* rule, adopted for join cost and for nothing to do with precision.
Had the ladders been spelled the arithmetic way that a reader of `prccty.f`
would write first —

```json
{"op": "+", "args": [{"op": "*", "args": ["has_exact", "scc"]},
                     {"op": "*", "args": [{"op": "-", "args": [1, "has_exact"]}, "sccZero2"]}]}
```

— then every one of the five ladders would be a `mixed_element_type` error, and
the fix would be exactly what §11.3.1 prescribes: compute the mixed step into a
variable whose own `element_type` states the precision it lands in. **Prefer the
predicate form for any new ladder or select**: `ifelse(<comparison>, a, b)` with
the comparison built from operands that agree, never `flag*a + (1-flag)*b` with
a flag and a key on the two sides of a `*`.

`lib/identifiers.esm` is where the identifier arithmetic lives and therefore
where the precision concern belongs: **its templates evaluate at the precision
of the `scc` / `pol_process_id` argument the call site binds.** Bind a key and
the whole body is `Float64`; bind a quantity and it is the document's. Do not
bind one of each — `scc_zero_tail(scc, tail_scale)` with a `Float64` `scc` and a
`Float32` `tail_scale` variable is the error above, which is why `tail_scale` is
always a literal at every call site.

### 17.4 What it cost the assertions, and the one thing that must not be loosened

Under binary32 no computed value agrees with a decimal `expected` to twelve
digits, so a model tolerance of `rel: 1e-12` cannot be kept for quantities. The
39 assertions that binary64 satisfied exactly land between 1.2 × 10⁻⁹ and
1.13 × 10⁻⁷ relative — **every one inside one binary32 epsilon**,
2⁻²³ = 1.1920929 × 10⁻⁷.

The move is therefore: **the tolerance goes to exactly one epsilon, and not one
expected value changes.** One epsilon is the resolution of the declared element
type and the smallest tolerance a binary32 evaluation can ever satisfy; it is
not a fitted number, and anything looser has to be argued for separately. §10's
older plan — migrate the expected values to their float32 equivalents — was
rejected once it was measurable, because the float32 values available to write
down are the specification's 7-digit *prints*, and pinning those would replace a
number derived from seventeen tables with a transcription.

**The tolerance is per test, never document-wide, and this is the important
part.** At one epsilon, `2260006912` passes an assertion of `2260007005`: the
relative gap is 4.1 × 10⁻⁸. A blanket epsilon default would make every key
assertion in the fixture vacuous and hide the exact defect the element type was
declared to fix — F18's own warning, that a key set must never be compared
within a tolerance, one level up. So:

* the **model default stays `rel: 1e-12`**, exact for every identifier;
* the **nine tests whose every assertion is a quantity** carry a test-level
  one-epsilon tolerance;
* a test that pins **both** a key and a quantity puts the tolerance on the
  quantity **assertion** — `the_oxygen_content_survives_four_joins` does, because
  it also pins `run_fuelRegionID = 270000000`.

Check the loosening against what each test discriminates, not just against
whether it passes. The tightest in this fixture is `point_monthFraction`: the
table's `0.0833333` sits 4.0 × 10⁻⁷ from the `defmth = 1/12` that a missed
lookup would silently deliver, a factor of 3.3 outside one epsilon, so that
test still tells them apart. A tolerance of 1 × 10⁻⁶ would not have.

### 17.5 The element type is **not** what fixed the row set

`tolerance.toml`, `run-oracle.sh`, `docs/nonroad-logging-county.md` §7.3 and
README all said, in nearly the same words, that `nr-logging-county`'s four
MY2018 cells "are recovered by evaluating in f32". For **this document that is
false**, and it was false before this change too. `PLAN.md` §1.6.1a is the one
place that had it right — "§1.6.1's four-row binary64 question is NOT among
[the missing keys] … because MY2018's grown model-year fraction is carried
rather than computed" — and four files disagreed with it without noticing.

`age_grownModelYearFraction` is a `const` — `[3.7072685, 0.9905483,
5.8885583e-08]` — because the fixture cannot evaluate `agedist.f`'s thirty-year
fold: it ingests, and a document that ingests is forced onto an evaluation path
that leaves a causal self-read unresolved (**F24**; it was **F12**, the fold
having no spelling at all, until EarthSciAST `a83cde55e`). The third value **is
the float32 fold's output**, carried in as data, so `age_isPopulated` reads it as
positive in binary64 as well, and the fixture emitted all twelve rows under
binary64 and emits the same twelve under `Float32`. `run-oracle.sh --float64`,
which *executes* the fold, does drop those four cells and emit 140 of 144. Both
measurements are true; what separates them is the carried column, not precision.

**One half of it has since become computed, and the half that matters for this
section.** The fixture now derives the age-3 survival from the real 197-row
curve in the declared `Float32` and asserts it to be `5.9604645e-08` rather than
`0`. So the *input* whose precision decides those four rows is measured in this
document; what is still carried is the fold that turns it into them. A document
can get a row set right for the wrong reason — and it can also get half of the
reason right, which is worth writing down as precisely as the whole.

The general claim — that a chain which executes `scrptime`/`agedist` needs f32
to reach 144 rows — is unaffected and still correct. The narrower claim, that
*this fixture* demonstrates it, was wrong: the fixture gets the right row set for
a different reason, and a document can get a row set right for the wrong reason
without anything failing. Write down which one you have.

---

## 18. What the evaporative slice changed **[Phase 4]**

Phase 4's first slice is `process-evap-leaks`, specified in
`docs/evap-leaks.md`. It is the third of the three shapes MOVES has — after a
Fortran chain (§1–§15) and a rates-first SQL graph (§16), a SQL-graph
**inventory** calculator, whose base rate is a table rather than a computed
rate. Every rule in §1–§17 held. Four gained a reason, five things are new, one
finding came out of it, and one rule was deliberately not applied.

### 18.1 Four rules that gained a new reason

**§11.1's "give the thing the tables meet at an axis" — finding F17 — fired for
the first time as a measurement on a fixture-scale document, not on a
component.** §16.3 recorded that the onroad chain did not need the remedy and
located F17 as being about the *size of both sides* rather than the semantics of
the key. The evaporative chain needs it, and at a size worth writing down: L8
written as `docs/evap-leaks.md` §2.4 writes it is one aggregate over five
relations — `emissionratebyage` (6,564 rows) × `sourcebin` (80) × the source-bin
distribution (125) × `sourcetypemodelyear` (533) × `agecategory` (41) — and,
ingested and run, it **did not complete in 120 s**. Two two-relation joins at the
same scale, timed in the same probe, finish in **25 s for the pair including
ingest**. So the sharper statement of F17 is: **cost goes with the number of
LARGE relations meeting in one node, and two is affordable where five is not.**
`docs/evap-leaks.md` §7.5 has the decomposition that follows, which gives the
operating mode its own axis in the §11.1 way.

**§16.5's "the run scope comes from the execution database, never from the
RunSpec XML" now has a second instance and a different reason.** §16.5 explains
`mixed-onroad.xml`'s disagreement as a stale rewrite. Measured across all 27
onroad fixtures, *every one* shows the same three offsets, which a stale rewrite
would not reproduce: `<month key>` and `<beginhour key>` are canonical
`RunSpecXML` **0-based indices into sorted ID lists**, so the ID is `key + 1`
(`moves.rs`, `crates/moves-runspec/src/xml_format.rs:600-626`), and `<day key>`
is an index into the sorted `DayOfAnyWeek` list `[2, 5]`, where an out-of-range
key means "no day selected" and falls back to all day types
(`default_db_setup.rs:2504-2540`). The rule is unchanged and stronger: an author
who reads those attributes as identifiers is off by one in month and hour and
wrong wholesale in day, systematically, in every fixture.
`docs/evap-leaks.md` §0.1 has the derivation and `docs/mixed-onroad.md` §0.1
carries a correction note.

**§3's "an unmatched row contributes the additive identity, and is still
emitted" has three more instances, and one of them is the row-set rule.** The
(1980, diesel) and (2020, electricity) cohorts have real non-zero activity
fractions and no `emissionRateByAge` row, so they read 0 and stay in the rate
relation — which is what keeps the decision about *which* cohorts reach
`MOVESOutput` in the output stage, where §3 puts it. The I/M blend is the second:
`imcoverage` is empty, so `IMAdjustFract` is 0 on every row and `im_blend` is
the identity, which is exactly the SQL's "a row with no matching cell keeps its
value unchanged" — an `UPDATE`, not a join, spelled as a zero. The third is in
the assembly, where a probe row has no counterpart upstream.

**§12's "assert both arms of a branch" is again served by probe ROWS, not
parameter overrides** — §16.4's replacement technique, now used three times in
one component. `components/evap_operating_mode_distribution.esm` carries two
probe hour-days at constructed activity ratios (0.6 and 1.25) because the
fixture's own two rows make the `least(1, ·)` cap do nothing, and a ninth soak
row at an operating mode `opmodepolprocassoc` does not admit, so the semi-join
has a negative arm. `components/liquid_leaking_emissions.esm` carries two I/M
probe rows because `imcoverage` is empty. In all three the probe is *labelled* in
the description as not being MOVESOutput's value.

### 18.2 Five things that are new

**A PRODUCT relation can build at most one of its two key columns from
`enums`.** §16.2's rule is that a `makearray` region addresses one contiguous
range per dimension, so a value built from an enum must occupy one run of rows.
In a two-key rectangle — four hour-days × three operating modes, say — only one
of the two keys can be contiguous, whichever the row order favours; the other
recurs in disjoint runs and must be a `const` data column. That is not a
workaround, it is a consequence, and the choice of which key to build from enums
is an authoring decision worth making deliberately: **build the key whose values
are enumerated SYMBOLS, and carry the derived or ordinal key as data.**
`components/evap_operating_mode_distribution.esm` orders its soak relation by
operating mode (so `soak_opModeID` comes from `enums`) and its distribution
relation by hour-day (so `omd_hourDayID` comes from `hour` × `day_type`), and
each file says which and why.

**A zero IS assertable — under two conditions.** §10 and the README are right
that a plausible zero on a cleanly-validating document is this port's
characteristic failure, and the rule that every assertion pins a specific
non-zero value follows from it. Phase 4 met three places where the *reference's*
answer is zero and the assertion is worth having anyway, and the conditions that
keep it honest are: **(a) the zero is the additive identity of an unmatched
join, named as such in the description, and (b) a non-zero sibling in the SAME
test proves the join works when a partner exists, and a non-zero input column
proves the row reached it.** `a_fuel_with_no_rate_row_contributes_nothing_and_keeps_its_row`
pins 0 for the diesel cohort beside its own 0.0466707 activity fraction and the
gasoline cohort's 4.037348315 rate. A zero pinned alone is still worthless.

**An absent output column is assertable too, and the technique is not obvious.**
MOVESOutput leaves nine of 25 columns NULL and §11's `null_output_column`
computes NaN for them. That absence cannot be pinned directly: `Assertion.expected`
is a JSON number, so NaN cannot be written down, and every tolerance form is a
magnitude comparison a NaN actual fails — measured, `actual=NaN expected=0`
reports FAIL, which is the right verdict and the wrong polarity for a test that
should pass. The way through uses only ops the format already has: IEEE makes
both `x > 0` and `x <= 0` **false** for a NaN, so `1 − [x>0] − [x<=0]` is 1 for
an absent column and 0 for every real number. Measured on a three-row probe: 1
for `0/0`, 0 for `4.25`, 0 for `-1.5`. `lib/identifiers.esm`'s
`output_column_is_absent` is that expression, and the test that uses it carries a
**negative control** — the same template applied to a column that is present —
because an indicator stuck at 1 would otherwise satisfy it.

**A computed zero and an assumed zero are different documents, and this slice
turns on the difference.** `docs/evap-leaks.md` §0.3 chose evap fuel leaks over
permeation and FVV because the one recurrence-blocked quantity it touches —
`soakActivityFraction`, downstream of a quarter-hour recurrence — enters at a
weight of exactly zero. That weight is `1 − fractionOfOperating` where
`fractionOfOperating = least(1, ΣSHO / ΣsourceHours)`, and it is 1 because at an
**on-network** link `SourceHours = SHO` row for row. A document that wrote
`opModeFraction[300] = 1` would agree with the snapshot on every one of its six
rows and be wrong the first time it met an off-network link. So the component
computes the ratio and the residual, and it carries a probe row on which the
residual is `0.599999932` where `fractionOfOperating` is `0.6` — a 6.8 × 10⁻⁸
difference that is the only thing distinguishing the right expression from a
wrong one. Verified as a real gate: setting that assertion to `0.6` fails at the
model's `rel: 1e-12`. **Where a fixture's answer does not depend on a number,
compute the coefficient that makes it not depend on it, and assert the
coefficient.**

**A `CROSS JOIN` with no `ON` clause may be dropped from a key — stated, not
silently.** L8's `CROSS JOIN RunSpecMonth, RunSpecHourDay` replicates the
weighted base rate across the run's months and hour/days without changing it, so
`components/evap_weighted_base_rate.esm` carries the rate over
`(regClassID, fuelTypeID, modelYearID, opModeID)` and the emission component
attaches the two temporal keys at L9, where `sourceHours` and `opModeFraction`
first make them matter. That is a simplification of the reference's control flow,
which §3 and §15 otherwise forbid; what licenses it is that the clause has no
`ON` and therefore no information, and what keeps it honest is that the
specification says so in one place (§2.4 point 7) and says what would confirm it
on a multi-month fixture (§8.2).

### 18.3 One new finding, and what it costs an assembly

**F21: a scoped name was not an assertable variable, until EarthSciAST PR #345
[retired].** `esm-schema.json`'s `Assertion.variable` documents a scoped
reference (`"subsystem.X"`), and the assertion path cannot resolve one:
`variable 'Emissions.emis_weightedMeanBaseRate' is not declared in model
'Rollup'`. The same name works in the same document as a `join.on` key column,
as an operand of an ordinary equation, as an `expr` operand and as a `plots`
`variable`. Measured on **both** mount forms with an identical message, so no
spelling of the mount avoids it.

What it costs: **an assembly can only assert its own columns**, so a leaf value
it wants to pin has to be routed through one. Prefer an algebraic recovery over
an identity equation — `runs/evap_leaks_run.esm` wants the rate its emission
stage carries and gets it as `run_carriedRate = run_weightedMeanBaseRate −
run_rateResidual`, both of which it declares — because an identity equation adds
a variable that means nothing and a recovery adds one that means something.

**And a second measurement that bears on §5.** The two mount forms differ in
whether the leaf's *own* tests run under the mount. Same leaf, same host, one
host variable and two host assertions either way:

| mount form | assertions discovered | leaf's own test runs? |
|---|---|---|
| top-level `models` `{ref}` | 3 | **yes** |
| nested `subsystems` | 2 | **no** |

§5 states the leaves'-tests-run behaviour as a feature of mounting and then
recommends the nested form for new assemblies. On this toolchain those two
sentences pull against each other, and this port's assemblies get the leaves'
tests only because a now-fixed defect (F1) forced them onto the top-level form.
**Until that changes, prefer the top-level form when the leaves carry tests you
want run under the mount** — which, in this port, is all of them.
`runs/evap_leaks_run.esm` runs 107 assertions, of which 81 are its three
leaves'.

### 18.4 One rule that was deliberately not applied: §17's element type

`fixtures/nr-logging-county.esm` declares `domain.element_type: "Float32"`
because the NONROAD reference is `real*4`. **The evaporative chain declares no
element type, and that is a decision.** MOVES stores its SQL working tables in
`FLOAT` and evaluates the arithmetic in MariaDB's `DOUBLE`, so the reference for
this chain *is* binary64 arithmetic with binary32 storage between steps — a
sub-10⁻⁷ drift that is smaller than the six-significant-figure column storage
every residual in `docs/evap-leaks.md` §7.1 is attributed to. There is no
Fortran and no associativity contract to reproduce.

If a future document does declare it, §17.1's per-variable override is needed for
one column and the margin is much wider than the SCC's. `sourceBinID` is about
1.01 × 10¹⁸, which is **6.0 × 10¹⁰ times** binary32's exact-integer limit of
2²⁴ — where an SCC is 135 times it. Two bins differ by 10¹⁰, and binary32's
spacing at 10¹⁸ is about 6.9 × 10¹⁰, so every source bin in the run would
collapse onto the same value and `emissionRateByAge` would join to all of them
or none. It is exact in binary64 for a reason worth knowing: every id ends in
10¹⁰, which contains 2¹⁰, so each is a multiple of 1024 while the spacing at
10¹⁸ is 128. **A packed identifier is a `Float64` override, always, and its
margin should be computed and written down rather than assumed to resemble the
SCC's.**

§17.2's strict rule — one operator, one precision — did not fire here because no
document declares an element type, so no operator mixes. §17.3's route survives
unchanged for a future one: `lib/identifiers.esm`'s templates evaluate at the
precision of the identifier the call site binds, and the ladders take predicates
rather than presence columns.

### 18.5 The fixture, and the two rules that made its shape

`fixtures/process-evap-leaks.esm` computes all 128 rows of `MOVESOutput` from
the snapshot's input tables and the comparison **passes**: 128 of 128 rows, an
exact key set, worst cell 7.294 × 10⁻⁶ against `tolerance.toml`'s 2 × 10⁻⁵, worst
per-pollutant sum 5.161 × 10⁻⁷ against 10⁻³. No `[shortfall]`, no carried column,
nothing read from the reference. `./run-leaks-oracle.sh` reaches the same 128
numbers by a different route and reports the **same** worst cell to the digit,
which is what makes a future disagreement attributable.

It is the second fixture in the repository and the first that fully matches, so
two rules about a fixture's *shape* are worth stating separately from its
arithmetic.

**A derived relation's axis is a metaparameter EXPRESSION over discovered
extents, not a literal.** §11 says a row axis is sized by `extent` discovery;
this fixture needed two axes that are not any table's row count, and
`esm-spec` §9.7.6 admits a `MetaparameterExpression` in an interval `size`:

```json
"activity_rows": { "kind": "interval",
                   "size": { "op": "*", "args": ["n_agecategory", "n_runspecday"] } }
```

82 rows from a 41-row and a 2-row table, and the cohort relation's 164 the same
way. Two more mechanisms make the rows *addressable* without literals, and both
were probed before authoring: the aggregate's **loop symbol is usable as a value**
in `expr` — `floor((r − 1) / n_agecategory) + 1` is a block index with a
discovered block length — and a **two-axis variable can be filled by a join**,
which is what puts the operating mode on its own axis and keeps L8 to two large
relations. So the general rule is stronger than §11's: **derive the shape, not
just the contents.** A fixture that wrote 82 or 164 would be asserting the
snapshot's shape.

**The one axis that cannot be derived is the OUTPUT axis, and a declared axis
must be checked in-document.** Which cohorts reach `MOVESOutput` is a *result*
of the chain, so materialising them as an index set is F5's value invention,
which validated and materialised empty until PR #342 fixed it;
`fixtures/nr-logging-county.esm` declares `output_rows: 12` for the same reason.
What Phase 4 adds is the rest of the discipline, and it is three parts:

1. **Declare the count, not the keys.** `n_outputCohort` = 64 is the only
   literal shape in the document. The output row's `(fuelTypeID, modelYearID)`
   come from a join to the cohort relation on an ordinal decomposed from the
   loop symbol — never from a `const` list of keys, which would pass
   `require_exact_key_set` by transcription.
2. **Compute the same count from the chain and pin them together.**
   `cohortSurvivorCount` sums a membership column over the 164 candidates and a
   test asserts it equals 64. A chain that produced 63 fails in the document,
   before the comparator sees a row.
3. **Say which gate the declaration weakens.** `docs/evap-leaks.md` §7.2
   measured that `require_exact_key_set` catches **none** of this chain's six
   ablations and the per-cell gate catches all of them, so the declaration
   forfeits nothing that was measuring anything. A declaration without that
   measurement beside it is an excuse.

**One more thing the fixture measured that a component could not.** A data-fed
`parameter` has no assertable array state in a document that ingests — `array
state 'yr_yearID' has no cells in var_map` — so only computed `unknown`s can be
pinned, which is why every assertion in both fixtures is on a derived column.
F16's scalar case reproduces verbatim alongside it. And a `Y`/`N` text column
*is* ingestable, through a `codes` map on the `from` binding (`esm-spec`
§8.9.1): `year.isBaseYear` and `fueltype.subjectToEvapCalculations` both arrive
as 1/0, so A1 and K9 are computed rather than carried.

---

## 19. Authoring a recurrence, and the two paths it evaluates on **[F12 fixed]**

`agedist.f`'s thirty-year fold was the one calculation in this port that the
format could not hold. It can now, and §11.2's blocker moved from the format to
the toolchain. What follows is what authoring one cost.

### 19.1 Reduce the fold before you spell it

The construct is esm-spec §4.3.1.1's **causal self-reference**: an equation
whose LHS is an array-shaped unknown `V` and whose `faq` body reads
`index(V, k − c)` — `V` itself, strictly earlier along one of that node's own
output axes. Nothing is declared. The recurrence, its axis and its maximum lag
are all read off that one read.

That admits a *scalar* recurrence over one axis. `agedist.f`'s fold is not one:
it shifts, scrapps and tops up a **51-slot vector** thirty times. So the first
step is arithmetic, not authoring — reduce the vector fold to a scalar
recurrence on its 31 residuals. Every cell of the grown vector is a clamped base
times an ascending run of survival factors, so slot `a` of year `y` traces back
`a` years to the residual of year `y − a`, or to the base vector if the fold has
not run that long. The reduction rests on `1 − yryrfrcscrp ≥ 0`: a non-negative
cohort times a non-negative survival stays non-negative, so along any chain the
clamp bites at most once.

**Verify the reduction against the reference, cell by cell, before authoring
anything.** `tools/verify-agedist-reduction.py` extracts
`docs/nonroad-logging-county.md` §6.5's own script — so both sides of the
comparison see the same inputs from one source of truth — replays the fold and
the closed form in float32 and compares **every** cell of every year of every
equipment point: 0 of 1,581 differing, six points. A reduction argued and not
measured is a rewrite of the model.

### 19.2 The contracted index is the lag

The natural spelling of a bounded-lag fold is **one** aggregate whose contracted
index runs from 0, the `0` term carrying the non-recurrent part and the rest
carrying `f(V[k − a])` under a guard. The lag then *straddles* zero, and
§4.3.1.1 admits that deliberately: the `a = 0` cell is never evaluated because
the guard selects the other branch, and that is sound without a static proof
because a self-read of an unpublished cell cannot return a value at all.

This port does **not** use that shape, and the reason is arithmetic. The
residual is `minuend − Σ cohorts`, with the cohorts summed in ascending slot
order **first**; the one-aggregate form accumulates `minuend + (−term₁) +
(−term₂) + …` instead. Measured, that moves the answer by up to **1.1 × 10⁻⁵
relative**, because the residual is a catastrophic cancellation — `4.6978183 −
0.9905498` leaves `5.9e-08` in slot 3 thirty years later. So the sum is its own
recurrence variable and the difference is a separate equation. The base case
lives in the *minuend*, not in the recurrence, which is what lets
`residual = minuend − sum` hold at every row including the first and so lets the
body read a lag of any size with one expression and no second base case.

**The second order is inside the cell.** Each cohort's factors must multiply
left to right *starting from the base* — `((base · S[lo]) · S[lo+1]) · …` —
which is a `reduce: "*"` aggregate whose **first** factor is the clamped base,
selected by an `ifelse` on the run's start index. Precomputing the run product
and multiplying the base in afterwards is a different float32 number, measured
at up to **6.4 × 10⁻⁶**. Written as specified, all 306 cells of all six
equipment points reproduce the reference fold **bit-exactly, at `rel 0, abs 0`**.

Neither order is something the format chooses for you and neither is visible in
the answer's magnitude. Measure both alternatives and write the numbers into the
equation's `_comment`, because the next author will reach for the tidier one.

### 19.3 Give the recurrence the axis the domain has

`agedist.f` is called once **per equipment point**, and the fold's answer depends
on the point's own base population — two of this fixture's points differ in
nothing else and their grown fractions still differ in the last bits. So the
recurrence carries a second, **non-recurrence** output axis, and that axis must
be an **identity** index: §4.3.1.1 admits `index(V, p, Y − a)` and rejects
`index(V, p + 1, Y − a)` as `recurrence_not_wellfounded`. Pass the point index as
an `expression_templates` parameter rather than broadcasting, so one template
serves a one-point component and a six-point fixture instead of the library
carrying two copies of the same twenty lines.

A `ranges` endpoint is a **metaparameter** expression, not an expression, so
`max_equipment_ages` cannot be applied there and MXAGYR appears as a literal
`51` inside the template's product range. The `filter` is what actually bounds
the run; the literal only has to cover it.

### 19.4 There are TWO evaluation paths, and a construct verified on one is not verified

This is the finding, and it is the thing to carry into the next slice.

`esm test` on a document that does not ingest builds without the array
pipeline. `esm simulate`, and `esm test` on any document that **ingests
`data_sources`**, build with it. A causal self-reference is honoured on the
first path and silently dropped on the second: the self-read comes back
unresolved, and `max(NaN, 0)` returns `0`, so a body with a clamp — which is
exactly what `agedist.f` has — produces a finite, plausible, monotone, wrong
answer with nothing logged. That is finding **F24**; the repro is upstream's own
canonical valid example, and `docs/findings/F24b_…esm` is the same document with
**one ingested column the recurrence never reads**, which is enough to break it.

Two rules follow.

**Exercise a new construct on both paths before depending on it.** Every
conformance fixture for this construct was verified under `esm test`, which is
why a construct with two evaluation paths shipped correct on one of them. A
downstream check that runs only the command the repository happens to use is the
same mistake one level down: `run-tests.sh`'s F24 check runs `esm test` **and**
`esm simulate` on the same file and asserts that they still disagree — inverted
polarity, so the day they agree, the fixture can compute the fold.

**A construct blocked on one path can still earn its keep on the other.** The
fold lives in `components/age_distribution.esm`, which does not ingest, with 55
assertions on it; the fixture carries its three output values and computes
everything that *feeds* them. That split is worth more than either half: it is
what let §7.3's `5.9604645e-08` become a measured number in the fixture while
the fold that consumes it stayed carried.

**The two axes were one cause, and the fix says what to generalize.** F24 is
fixed upstream (EarthSciAST `de784f3f8`): `prepare::eval_observed` evaluated
every observed *wholesale* with no recurrence scope, and both routes reach it.
The sweep is now **one shared function both paths call** — two call sites with
two copies is exactly how one path came to work and the other to be dead — and
an unrecognized self-read now returns `recurrence_unsupported_form` instead of
falling through to the wholesale evaluation. Generalize the second half, not the
first: **a construct with more than one evaluation path needs one
implementation and a loud floor under the paths that miss it**, not two correct
implementations.

### 19.4a A NaN sentinel is not a defence in a model that clamps

The runtime *did* return the loud sentinel: an unresolved self-read was `NaN`.
`max(NaN, 0.0)` returns `0.0`, because IEEE-754 `max` returns the non-NaN
operand — so the clamp destroyed it, and `agedist.f`'s fold body **is**
`max(·, 0)`. This is the eighth instance of the plausible-wrong-value failure
this repository tracks (README's "A warning about zeros") and the **first where
the sentinel was manufactured by a clamp rather than returned by the runtime**.

MOVES clamps everywhere — the fold body, `prccty.f`'s `modfrc <= 0` skip, half
the scrappage arithmetic, `least`/`greatest` through the evaporative chain — so
in this port NaN propagation cannot be relied on to surface an unbound read at
all. Two consequences for authoring and for checking. Where a repro's evidence
is a sentinel, assert the value **downstream of the clamp** as well as at it:
`run-tests.sh`'s F24 check reads the *clamped* column, because a check on the
`NaN` column alone would pass the day the sentinel changed without the construct
working. And when a number is suspiciously round — a constant `1`, a sum of
`1.5e-06` where `4.697819` was expected — look for a clamp upstream of it before
looking for an arithmetic error.

### 19.5 A precision-sensitive leaf cannot declare its precision

`domain.element_type` does **not** survive a top-level `models` `{ref}` mount
(finding **F23**). Declaring `Float32` on
`components/age_distribution.esm` made `runs/nr_logging_county_run.esm` re-run
that leaf's inline tests in binary64 and read the third grown fraction as
exactly `0` against an expected `5.888558263222876e-08` — the silent precision
change producing the plausible zero. Declaring it on the *assembly* instead
breaks **119 of 295** assertions across ten leaves authored in binary64.

So a leaf whose answer depends on the precision **pins both**, in the two places
they are actually evaluated: its own arithmetic exactly, at the model default;
the reference's real\*4 value named beside it in the description with the
measured gap; and — this is what stops the first from being self-referential —
the **invariant the two precisions share**, asserted. Here that is
`Σ modfrc = G(2020)/G(1990) = 4.697819`, which the growth stage derives
independently, asserted at 2⁻²³ for all three equipment points.

Two further notes on tolerances, both learned by getting them wrong first. A
divergence that is **amplification** rather than rounding cannot be absorbed
into a tolerance: this leaf's binary64 fold is `5.3 × 10⁻⁷` from the real\*4
answer, four binary32 epsilons, so no tolerance makes the reference decimals
both assertable and discriminating. And where a reference *print* is coarser
than the arithmetic — §6.2 prints `0.0717785`, six significant figures because a
leading zero ate one — the assertion's tolerance is the **sum of two measured
quantities** written out in the test, one binary32 epsilon plus half an ulp of
the print, never a number chosen to make the test pass.

### 19.6 Isolate a known input difference; do not widen a gate to swallow it

`tools/cross-check-chain.py` holds the assembly and the fixture — two
independently authored routes to the same four numbers — at **one ulp** of
binary32, which was measured and not chosen. Once the leaf computed the fold,
the two routes differed by 5–8 ulps, for a reason that is *not* the one the gate
bounds: they now get one input, `modfrc[2020]`, from different places.

Raising the bound to 8 would absorb that and with it any future divergence of
the same size arising for a different reason, which is the one thing the gate
exists to catch. The fix is to **divide the known difference out** — normalise
each route's rows by its own `modfrc[2020]`, read from the document that owns it
— and hold the normalised rows to the original bound. It comes back to three
rows bit-exact and one at exactly one ulp, which is also the evidence that the
one input was the whole of the difference. The size of that input difference is
then asserted **two-sidedly**, with both edges naming what they mean, so it
cannot drift unnoticed; and if the fixture's equation stops being a `const`, the
script says the normalisation is now dead weight rather than silently dividing by
two equal numbers.

## 20. The recurrence's second shape, and what it did not need **[F12 verified twice]**

§19 records what authoring `agedist.f`'s fold cost. This section records what
authoring a *second, deliberately unlike* recurrence cost, because a construct
verified only against the case it was designed for is verified narrowly and
that is the whole reason `components/tank_temperature.esm` was written.

### 20.1 Four ways it is a different recurrence, and none of them cost anything

`TankTemperatureGenerator` TTG-1b differs from the fold on every axis that
looked like it might matter:

| | `agedist.f`'s fold | TTG-1b |
|---|---|---|
| self-reads per cell | one per contracted lag, `a ∈ [1, 50]` | exactly one |
| the lag | a contracted index symbol | the literal 1 |
| the axis | a declared 31-row year axis | a **derived** 96-cell quarter-hour grid whose hour and step columns are computed from the row number |
| the base case | the constant `0.0` under `Y <= 1` | **computed**: `quarterHourTemperature[1] − firstQHTankTemperature` |
| the terms | independent of the answer once the survival run is fixed | each term is a function of the answer so far |

The last row is the one that matters, and it is the sharpest available test that
§4.3.1.1 is doing work §4.3.1's prefix scan could not. TTG-1b carries
`sumTempDelta`, whose increment is `quarterHourTemperature − (1.4·sumTempDelta +
first)`: a linear feedback with ratio −0.4. There is no ordering of independent
terms that produces it.

**All four took the construct unchanged.** No new operator, no new schema field,
no declaration, and the file passed `esm validate` and `esm test` on its first
run. The one thing that had to be got right was §19.2's rule read backwards:
where the fold needed a *contracted* index as its lag, this one needs no
contraction at all, and an `faq` with an `output_idx` and no `reduce` is
the right node for it.

### 20.2 Prove the sweep is causal by perturbing an input, not by reading the code

§19.4a says a NaN sentinel is not a defence in a model that clamps. The positive
form of that rule is: **a recurrence is proved live by moving one of its inputs
and watching where the answer moves — and, just as importantly, where it does
not.** Measured on `components/tank_temperature.esm`, at the bit level, by
perturbing one hour's ambient temperature by +10 °F and dumping all 24
cold-soak outputs:

| perturbed | hours bit-identical | first hour that moves |
|---|---|---|
| hour 12 | 1 … 11 | 12 |
| hour 23 | 1 … 22 | 23 |

That is esm-spec §4.3.1.1 points 1–3 — axis outermost, ascending, published
before the sweep advances — observed rather than trusted. A vectorised or
reordered evaluation would leak the perturbation backwards; a dead recurrence
would confine it to the one cell. Neither happens.

The decay is worth naming too: the feedback ratio is −0.4, so a perturbation
falls below binary64's resolution about forty cells later. **A contracting
recurrence hides its own errors**, which is why this file asserts all 24 outputs
against the reference rather than sampling the ends — an error injected at hour
3 would be invisible by hour 15.

### 20.3 A guard is a template when two equations need the same one

§4.3.1.1 point 6 makes a self-read of an unpublished cell a **fault**, not a
zero ghost, so a base case is written as `ifelse(k <= 1, 0, index(V, k − 1))`
inside the body. Here two equations need that guarded prior — the recurrence
itself, and the equation that publishes the tank temperature one cell behind it
— so it is `lib/evaporative.esm`'s `prior_quarter_hour_delta_sum` and not two
copies. Factoring it is not tidiness. An `ifelse` in a recurrence body selects
its branch *before* evaluating it, which is the property that keeps the guarded
self-read from being evaluated at the first cell; one copy means one place where
that property has to hold.

And write the base case as the **computation** rather than as its value. Row 1's
carried delta here is zero, but it is zero because two computed quantities are
equal, not because a `0.0` was typed. Typing the `0.0` would have removed an
input the recurrence can be perturbed through, and §20.2 is what those are for.

### 20.4 A constant equality is still a `join.on`

§3 admits no exception for an equality against a constant, and
`tools/check-conventions.py` enforces that literally. TTG-1's two key selections
— the anchor at `(hour 1, step 1)` and TTG-1c's step-1 cells — were first
written as `==` inside a `filter` and were rejected. The spelling is a **one-row
relation** carrying the constant, joined to. It reads better, it is what §3
asks for, and it turns two full scans of a 96-cell axis into gates that drive
enumeration.

### 20.5 An absolute tolerance is sometimes the correct gate, not a widened one

`QuarterHourTankTemperature.tempDelta` is the difference of two numbers near
63.8 that MOVES holds in a Java 32-bit float. A 4e-06 absolute rounding on each
operand survives into a result of magnitude 0.2 as a 2e-05 *relative* one, so
the reference's stored −0.224998470000 and this document's −0.2249994278 agree
to 9.6e-07 absolutely and only 4.3e-06 relatively.

Asserting that column at `abs 2e-05` is not the tolerance-widening §7 of
`README.md` forbids; the relative gate is simply the wrong gate for a
cancellation. What makes it legitimate rather than convenient is that **both
operands are pinned tightly either side of it** — the quarter-hour temperature
at `rel 1e-12` and the tank temperature at `rel 1e-6` — so the loose gate covers
exactly the cancellation and nothing else.

---

## 21. An oracle must ASSERT its tolerance, not print it **[measured]**

`./run-tests.sh` reads each independent reproduction's **exit code**. Three of
the four computed a worst relative error, printed it, and returned 0 whatever it
was. Measured, not supposed: injecting a 2% error into
`docs/evap-leaks.md` §6.5's emission product left `./run-leaks-oracle.sh`
printing

```
emissionQuant:              128 rows, 0 missing, 0 extra, worst relative error 2.000e-02
```

and exiting **0**, so the suite reported `ok ./run-leaks-oracle.sh` with the
evidence sitting four lines above the green tick. The same held for
`./run-onroad-oracle.sh`. `./run-oracle.sh` was already right —
`assert n == 144 and missing == 0 and extra == 0 and worst < 1e-5`, in both its
arms — which is what makes this an omission rather than a design.

The rule: **every relation an oracle compares carries a numeric limit, and the
limit is asserted.** A key-set check is not a value check; a chain that emits
exactly the right 128 keys with every number 2% wrong is the failure an oracle
exists to catch, and it is also the failure a printed number cannot catch. The
limits are the recorded ones — `tolerance.toml`'s per-cell gate for an emission
quantity, the reference's own storage floor for a captured intermediate — and a
number that will not fit inside one belongs in `tolerance.toml` with a reason,
never in a widened literal.

This is `README.md`'s warning about zeros in a different costume. The value was
never wrong-and-silent; it was wrong-and-*printed*, which is worse, because a
log that contains the answer reads as a log that checked it.
## 22. A ragged key set on rectangular axes **[144 rows]**

The `nr-logging-county` output is 36 `(SCC, modelYearID)` cohorts over three
SCCs whose model-year counts are 3, 29 and 4 — and the 29 are not contiguous.
That is the shape a `ragged` index set advertises. This port does not use it,
and the reason is no longer that it fails: a ragged range binds the POSITION and
the body gathers the member explicitly (esm-spec §4.3.1, made normative by PR
#352; finding **F14**, retired), which needs a padded `[parent, max length]`
member array that the flat relation below does without. A rectangular `[SCC ×
modelYear]` output axis emits 348 keys where the snapshot has 144, and
`tolerance.toml`'s `require_exact_key_set` is not negotiable. This section is
the shape that works, because the next NONROAD sector will need it and the
reasoning does not survive being rediscovered.

**Three layers, and none of them ragged.**

1. **A rectangular grid, carried FLAT.** The cohorts live on
   `equipment_point_rows × age_slot_rows` — six points by `MXAGYR` = 51 age
   slots — and the relation is one 306-row axis with both coordinates as key
   COLUMNS, decoded by `lib/keys.esm`'s `flat_relation_major` /
   `flat_relation_minor`. Flat rather than two-dimensional for a hard reason: a
   `join.on` key column is resolved through its declared axis to one of the
   node's ranges, so it must be **1-D**. A `[point × slot]` array cannot be
   joined on, and every stage downstream of the grid needs to join on it.
   `block_size` is `max_equipment_ages`, applied by reference, so the layout
   follows the model's own age bound rather than a 51 typed into the fixture.

2. **A membership column, and it is usually more than one test.** The
   port's suppression rule is `prccty.f`'s, and it is TWO gates: the loop bound
   `idx < nyrlif` and the body's `modfrc <= 0` skip. Neither implies the other
   — `agedist.f` keeps shifting cohorts past `nyrlif` without scrapping them
   further, so a positive fraction can sit outside the bound, and a cohort
   inside the bound can be exactly zero. Write both, and assert a counterexample
   to each collapsing into the other; this fixture has one of each, in two
   different SCCs. What the mask must NOT be is a filter on the emitted rows:
   the row set has to be a consequence of the arithmetic, not a decision about
   the arithmetic's output.

3. **A rank, which is what makes the mask produce a row COUNT.** An inclusive
   prefix count of the mask over the flat relation, **zeroed on non-members**,
   gives every emitted cohort a dense 1…N and every suppressed one a 0 that no
   output ordinal can match. The output relation is then a flat `N × pollutants`
   axis whose rows join against that rank. Two properties follow and both are
   worth stating: the join is an ordinary equi-join, and **N is nowhere written
   down** — it is what the mask counts, so the test pins the count
   (`cohort_ownerRank` at the last position of the relation) rather than the
   number. A mask that admitted one cohort too many or too few would leave the
   output axis the same length and every row still carrying a number; pinning
   the count is what turns that into a failure.

**Where a key and its quantity are contracted differently.** The output row is
keyed by SCC and three equipment points share one, so exactly one cohort per
`(SCC, model year)` may own the row — a **self-join** of the flat relation
suppresses the rest — while the QUANTITY must sum every point that reaches that
cohort. So `out_emissionQuant` joins on `(SCC, age slot)` and `cohort_ordinal`
joins on the rank, and they are deliberately different joins on the same
relation. Getting that wrong in the obvious direction — summing the owner
alone — loses two thirds of one SCC's mass while keeping the key set exact,
which no structural check would see.

**And the axis a quantity is carried on is a claim about what it varies over.**
`run_scope_rows` has one row and holds the county, the month, the fuel region,
the ambient temperature and the gasoline oxygen; `equipment_point_rows` has six
and holds everything that differs per point, the two-stroke/four-stroke
distinction included. Both directions of getting it wrong were measured while
this landed: `tamb` on the point axis is six identical contractions over a
930,816-row table (14 s of a 31 s document), and `pp_adjustment` on the run axis
would hand five four-stroke points a two-stroke correction. The dangerous
mistake is neither of those but a third — an aggregate that RANGES over the
point axis without naming it in `output_idx` sums six points into one number and
returns a plausible answer. When an axis grows from one member to six, every
aggregate that mentions it has to be re-read for that.

## 23. Measure whether the fixture can SEE a stage before you check it there **[three slices]**

`process-evap-permeation` established that a stage multiplied by an
`opModeFraction` of exactly zero cannot be checked at the fixture, because the
check would pass with the stage deleted. `process-evap-fvv` is the second
instance, and the second instance is what makes it a rule rather than an
anecdote — the whole venting half of the largest calculator in MOVES, nine
steps and a soak-day recurrence, is zero-weighted there.

**The rule: before writing a fixture assertion on a stage, perturb one of that
stage's inputs and compare every output cell BIT FOR BIT against the
unperturbed run.** Not "within tolerance" — identical bytes. If the cells do not
move, the assertion you were about to write is decoration, and three things
follow:

1. **The check belongs in a component**, at probe values chosen so that each
   part of the expression is discriminating. A blend weight tested where both
   branches clamp to zero is as dead as the fixture assertion would have been;
   `components/tank_fuel_venting.esm` carries a canister load where both inner
   roots are positive and differ, *and* a second one where both are negative so
   the clamp is what returns the answer.
2. **The measurement belongs in the specification**, as a table of perturbations
   with their worst-cell effect, so the next reader does not re-derive it. See
   `docs/evap-fvv.md` §0.3.
3. **The fixture says what it does not contain, and why.** A fixture whose
   metadata is silent about an absent check reads exactly like one where the
   check passed.

The corollary is the one that saves the most time: **a zero WEIGHT and a zero
RATE are different failures, and only one of them is a bug.** So the oracle
asserts *both* that the zero-weighted chain produced non-zero numbers and that
they contributed nothing. Without the first assertion the second is vacuous —
a chain that computes nothing at all would also "contribute nothing", and would
look identical in the log.

## 24. Factor the FORM from the COEFFICIENTS when the reference packs them together **[2,188 rows → 2 forms]**

MOVES stores `MultidayTankVaporVentingCalculator`'s venting equations in a
`VARCHAR` column of `cumTVVCoeffs`, 2,188 rows of it. It is tempting to read
that as a special case — "an expression that arrived as data" — and to reach for
either a hand-translation or a finding. Both are wrong. Those strings are
equations that an engine evaluates, which is the same category of thing an
`.esm` expression is; that MOVES keeps them in a table rather than in source is
an implementation detail with no semantic weight, and they get ported like any
other model logic.

**What porting them means, though, is factoring.** MOVES packs the structural
form and the numeric coefficients into one string. The port must not:

* the **forms** become `expression_templates` in `lib/`, spelled once and
  imported by reference;
* the **coefficients** stay data.

Done that way, `cumTVVCoeffs`'s eighteen distinct equation labels are **two
forms** — a quadratic root, and a convex blend of two of them, of which the
unblended labels are the degenerate weight-1 case — plus one linear leak term,
and eighteen coefficient rows. 2,188 rows of table remain 2,188 rows of table.
The size of the set changes how many coefficient rows there are; it never
changes what the right answer is, and volume alone is not a finding.

**Say where the coefficient table came from when the snapshot does not contain
it.** This one does not: MOVES's Java rewrites the expressions into sequential
abbreviations (`T0`…`T5`, `L0`…`L11`) in the execution database before a
snapshot is taken, so what is captured is eighteen labels and no expression
anywhere. The expansion lives in the MOVES *default* database. Recording that in
the specification (`docs/evap-fvv.md` §2.10) rather than burying it in a
component is what lets a later reader check the numbers against a default
database instead of against us.
## 25. A multi-clause `join` no longer needs hand-ordering — and the reason it used to is worth keeping **[retired, F17 fixed]**

**The rule is RETIRED.** EarthSciAST `fe86d784b` chooses the driving gate by
selectivity rather than document position and then drives the **conjunction**,
intersecting the partner lists (CONFORMANCE_SPEC §5.24). Clause order in an `on`
list is now a reading order again. `mixed-onroad`'s `cohMode_rate` is the
measurement: its six key pairs hand-fused into one composite clause admit 3,772
leaves, and the same six written as six separate clauses now admit **3,772** —
where before they admitted 158,030,400 and cost 298 s against 6.6 s.

**But the fixture still spells it as one composite clause, and that is not an
oversight.** The retirement was written from the leaf counts and then the
unfusing was actually measured: six clauses emit a byte-identical relation, so
the fusion carries nothing for correctness — and `esm simulate` on the whole
fixture is **2.8 s fused against 5.1 s unfused**, three runs each, a consistent
**1.85×**. Equal leaves are not equal cost. Resolving six clauses builds six
equijoins where one composite builds one, which is the same effect that makes
selectivity ordering alone a wash on `nr-logging-county`. So the composite key
survives its own justification: it is now a measured authoring choice, not an
instance of this rule. **A workaround outliving the defect that forced it is
worth re-measuring rather than reflex-deleting** — the number that justified it
originally was not the number that justifies it now.

**Read the rest of this section anyway**, because the rule was load-bearing for
something nobody knew it was load-bearing for, and that is the transferable
part.

**What the rule used to say.** Write the most selective clause first, and say in
a `_comment` that the order is a cost decision rather than a reading order.
CONFORMANCE_SPEC §5.5.8 said every gate restricts the admitted set but only ONE
need DRIVE, and that "which one drives is a binding's choice" — the Rust
reference's choice being the first resolvable clause in document order
(`resolve_join_gate` returned on its first hit), the rest lowered into the
per-leaf equality `filter`, which is what keeps a non-driving clause exact.

**And the lowering was not exact.** `precision_infer` runs at `problem.rs` stage
(1c)/(3b); join resolution runs inside the array compile at stage (4). The
lowered `left == right` was therefore built *after* precision annotation, carried
no marker, and evaluated at the **document's** working precision. This
repository's NONROAD fixture works in binary32, where the spacing at SCC
magnitudes is 256 and `2265007010` and `2265007015` are the same number. So the
driving gate separated them on exact `i64` keys and the per-leaf filter did not:
**reordering three clauses on `out_emissionQuant` changed 32 of 144 emitted
rows**, summing two cohorts' emissions into the wrong output row. That is now
fixed, and §5.5.8 says normatively that a key comparison is exact rather than
the document's precision.

**The lesson that outlives the rule: a convention adopted for COST can be
holding up CORRECTNESS, and you will not know which.** This one was written
after measuring run time, with "the answer does not move a bit" stated as an
observation — and that observation was true only for the orders that had been
tried. A rule whose justification is performance still deserves a correctness
check on the thing it is silently choosing.

**Measured on `fixtures/nr-logging-county.esm`, J11 `tech_fraction`**, four
clauses permuted and nothing else changed, one `esm simulate --time 0` of the
whole document each, emitted rows byte-identical in all four:

| driving clause | leaves admitted | whole document |
|---|---:|---:|
| `tech_engTechID ↔ mix_engTechID` (as written now) | 2,320,704 | **11.5 s** |
| `cohort_mixEffectiveSCC ↔ mix_SCC` (as written before) | 5,977,200 | 20.4 s |
| `cohort_mixYearID ↔ mix_modelYearID` | 24,107,900 | 57.2 s |
| `mix_processGroupID ↔ epg_processGroupID` | 272,523,600 | 541.0 s |

~2 µs per admitted leaf, flat across four orders of magnitude — the driving
clause's selectivity *is* the run time. The load-bearing pair re-measured
interleaved, three passes each so both see the same machine: SCC-first 21.25 /
18.52 / 20.05 s against technology-first 10.99 / 11.48 / 11.24 s, emitted CSV
byte-identical. The four clauses together admit 2,601
tuples, so even the best order is ~900× above the relational cost; that gap is
upstream's (F17) and not the document's.

**How to pick without measuring.** The leaf count is
`Σ_output-cell |rows of the relation sharing that cell's key value|`, which for
J11 is (rows per key value) × (the product of the output axes the clause does
NOT bind). Per cohort, over the 100-wide technology axis:

| clause | rows per key value | × ungated tech axis | leaves per cohort |
|---|---:|---:|---:|
| `engTechID` | 7,584 across all 100 codes | binds it | **7,584** |
| `SCC` | 195 (weighted over the two SCCs the cohorts take) | × 100 | 19,533 |
| `modelYearID` | 788 (weighted; `1900` alone carries 1,135) | × 100 | 78,784 |
| `processGroupID` | 8,906 (the key has TWO values) | × 100 | 890,600 |

Two things fall out. A clause that binds an output axis pays that axis nothing,
which is why the technology clause wins by more than its key selectivity alone
suggests; and a 2-valued key is the worst driver there is while reading like the
most natural first clause, which is the trap.

**This is a workaround and it is written down as one.** The document should not
have to know which clause a binding drives on, and a binding that chose by
selectivity — or intersected the clauses instead of choosing — would make this
section obsolete. Until then, a `_comment` on the clause list is the only thing
standing between the next author and a nine-minute `tech_fraction`.

## 26. What the drive-cycle slice changed **[Phase 3 completed, 250 rows]**

`W[hourDayID, opModeID]` — 46 numbers, `docs/mixed-onroad.md` §10 — was the last
uncomputed relation in the onroad chain, and computing it landed
`fixtures/mixed-onroad.esm`: 250 of 250 `MOVESOutput` rows, key set exact, worst
cell 8.320 × 10⁻⁶ against a 2 × 10⁻⁵ gate. Four rules gained a reason, three
things are new, and one long-standing claim turned out to be false.

### 26.1 Four rules that gained a new reason

* **§2, tables stay tables.** The 63,602-row `driveschedulesecond` relation is a
  table and its neighbouring-second reads are joins on `(driveScheduleID,
  second − k)`, not array offsets. That is not a stylistic choice here: every
  schedule starts at second 0 and 19 of the 49 have **interior gaps**, so 185
  rows have no predecessor and a positional read would silently pair a row with
  a different schedule's second. The presence columns are what make the gap
  visible; §3's "a `filter` carries a genuine predicate" and this are the same
  rule seen from two sides.

* **§3, every equality is a `join.on`.** The drive-cycle bracketing is the
  counter-example that proves it: `speed <= binSpeed` really is a range
  predicate, so it is a `filter` under a `max_product` reduction, exactly as
  `latest_at_or_before_key` is. `docs/mixed-onroad.md` §8.1 had predicted this
  step would be F17's "big table meets big table" shape; it is not a join at
  all, and predicting a cost from a table's row count rather than from the
  gate's shape was the error.

* **§6, a reused shape is a template.** `lib/drive_cycle.esm` carries four, and
  one of them is a template for a reason worth repeating: the *faster* bracketing
  schedule's weight is `1 −` the slower's in **every one of the four branches**,
  so there is one `bracket_low_fraction` and no complement template that could
  drift from it.

* **§25, the first clause is the one that costs — and so is the NUMBER of
  clauses.** Two applications in one document. Each self-join writes the
  offset-second pair **first** (3.2 rows per value) rather than the schedule pair
  (1,298). And `cohMode_rate` puts all six key pairs in ONE clause rather than
  six, which is a stronger version of the same rule: a composite key of six pairs
  is one gate admitting **3,772** leaves, where six gates of one pair each is a
  gate whose selectivity is that of whichever single pair resolves first — 8.5 ×
  10⁶ at best and 5.6 × 10⁸ at worst, with the written order landing on
  1.58 × 10⁸. **Measured**, the same document with that one clause split into six
  and nothing else changed: 298.36 s and 287.08 s against 6.61 / 6.62 / 6.98 s, a
  factor of 43, emitted CSV byte-identical. ~1.8 µs per admitted leaf, which is
  §25's own ~2 µs. `docs/mixed-onroad.md` §10.3 has the full table.

### 26.2 Three things that are new

* **A self-join is now an ordinary join, and it needs `join.syms`.** Finding
  **F11** is fixed (EarthSciAST `107a15152`). Two `faq` ranges over one
  index set can carry an `on` clause; candidates are ordered by the node's
  canonical range order (output symbols first, then contracted symbols in
  ascending code-point order), the left key is read at the earlier and the right
  at the later, **three or more candidates is refused**, and an explicit
  `"syms": [left, right]` overrides and is required at three. Measured at this
  repository's largest scale — 63,602 rows, 4.045 × 10⁹ candidate pairs — the
  eight self-joins of `fixtures/mixed-onroad.esm` cost **~1.4 s together, about
  0.18 s each**, by bisection against the same document with them stubbed to
  constants (6.6 s against 5.2 s, three runs each).

  The convention: **write `syms` even when the default would pick the same
  pair.** A reader of `[["dss_priorSecond", "dss_second"], ["dss_driveScheduleID",
  "dss_driveScheduleID"]]` cannot otherwise tell which side is which, and the
  second pair's two sides are the same column name.

  What this makes RETIRABLE, and it is not yet retired:
  `fixtures/process-evap-leaks.esm`'s `cohort_equipped_rows` and
  `components/onroad_source_bin_distribution.esm`'s `eq_*` relation — in both
  cases a whole second copy of a relation over a second index set, carried only
  because the fuel-usage rebase pairs a row with another row of its own
  relation, and in both cases with a `_comment` citing F11 as the reason.
  `fixtures/mixed-onroad.esm` does the same rebase as a three-clause self-join
  and needs no second relation, so the workaround has a replacement that is known
  to work at this scale. Removing it from those two documents is a separate
  change with its own verification and has not been made here; this section is
  the record that it is now possible, which is exactly what the tripwire stage's
  polarity exists to surface.

* **A rank turns a mask into a row count, and now it needs no self-join
  either.** §22's mechanism, spelled with the cheaper of its two forms: the
  inclusive prefix count is an ungated `faq` over two ranges of one index
  set under a `filter` of `x <= c`, 164 × 164 leaves. It is a `filter` and not a
  join because `<=` is a genuine predicate — the same rule as §3, arrived at
  from the opposite direction.

* **A first-match-wins loop is a SUM when the cases are disjoint, and the
  disjointness is a computed check.** The reference walks 21 operating modes and
  `break`s on the first match; the port sums `opModeID × indicator`, which is the
  same number only because `readOperatingMode` excludes modes 26 and 36 and the
  survivors then partition `speed >= 1`. The document computes `SUM of indicator`
  as well and asserts it is 1, so a table change that broke the disjointness
  shows up as a 2 rather than as a plausible wrong mode. **Do not substitute a
  sum for an ordered search without carrying that second sum.**

### 26.3 One claim that measurement overturned, and how it survived so long

`docs/mixed-onroad.md` §8.2 recorded that "`sourceBinActivityFraction` equals
`stmyFraction` exactly on all 125 rows", and concluded the `fuelusagefraction`
remap was "effectively the identity for this county/year". It is not: the remap
is a factor of **55** on the E85 rows, end to end, and the conclusion had been
inferred from the table's shape (5 rows, four of them identity pairs) rather
than measured against the chain.

It survived because the observation it rested on was TRUE of a different table —
`sourcebindistribution`, the *equipped* distribution — and the base rate is
weighted by `sourcebindistributionfuelusage_1_26161_2020`, the *used* one.
`components/onroad_source_bin_distribution.esm` had the remap right and said so
at length; nothing compared the component with the specification, so the two
disagreed in writing for a phase.

**The rule:** an inference about what a table *does* is not a measurement, and a
specification is not exempt from the repository's own cross-check discipline
just because it is prose. §6.5's reproduction now computes the remap, so the
claim is exercised on every run rather than asserted once.

---

## 27. What the multi-pollutant slice changed **[Phase 5, 750 rows]**

`fixtures/process-brakewear.esm` is the first document in this port to emit more
than one pollutant-process: 750 `MOVESOutput` rows over 9101 (Total Energy ×
Running Exhaust), 11609 (PM2.5 Brakewear) and 10609 (PM10 Brakewear, chained),
key set exact, worst cell 8.250 × 10⁻⁶. Two rules gained a reason, two things are
new, and one existing fixture turned out to be wrong in a way only a second
snapshot could show.

### 27.1 Two rules that gained a new reason

* **§2, tables stay tables — now for a *derived* relation with two key
  factors.** Everything the base rate needs is keyed by the cohort AND the
  pollutant-process, and a `join.on` key column must be one-dimensional
  (`join.rs` resolves a key through a declared 1-D variable's single axis). So a
  two-dimensional `ppCoh_shortModYrGroupID[polProcess, cohort]` is not
  expressible as a key at all, and the rate stage rides a flat
  `rate_rows = n_polProcess × (n_agecategory × n_fuelType)` relation whose
  columns are read back from the two factor relations by ordinal joins.

  **The rule that follows: when a stage's keys acquire a second factor, cross
  the relations rather than widening the columns.** Widening is the reflex, and
  it stops at the first join. `docs/process-brakewear.md` §2.2 has the key that
  forced it — `pollutantprocessmodelyear` maps model year 2020 to
  `shortModYrGroupID` **40** for 9101 and **6** for 11609, so the same cohort
  meets a different `emissionrate.sourceBinID` on each path.

* **§3 / §20.4, a constant equality is still a `join.on`.** The
  temperature-adjustment lookup's wildcard arm is `ta_regClassID == 0`, and it is
  spelled as a join against a one-row relation carrying that 0
  (`run_regClassWildcardID`), not as an `==` in a filter — which
  `tools/check-conventions.py` would have rejected anyway.

### 27.2 Two things that are new

* **A chained pollutant is a self-join on the rate relation, and it needs no
  branch.** MOVES's chained calculators (`PM10BrakeTireCalculator`,
  `HCSpeciation`, the TOG/NonHAPTOG chains, air toxics) compute one pollutant by
  scaling another. `runspecchainedto` names the edge and a ratio table carries
  the factor, so the document reads both and writes neither. What makes it one
  expression over all blocks rather than a branch is that **three quantities are
  zero for three independent reasons**, each measured:

  ```
  chain key   = 0  on an unchained row   (the LEFT JOIN onto runspecchainedto misses)
  ratio       = 0  on an unchained row   (the ratio table carries only the chained id)
  direct rate = 0  on the CHAINED row    (emissionrate carries no row for it — J22 is inner)
  ```

  so `quant = direct + ratio × Σ(chained-from direct)` is a union everywhere. A
  document that instead tested "is this block chained?" would be writing down the
  answer `runspecchainedto` already gives.

* **A wildcard lookup is a precedence over two aggregates, and it is a
  template.** `lib/adjustments.esm`'s `exact_else_wildcard(has_exact,
  exact_value, wildcard_value)`. MOVES writes this shape repeatedly — the exact
  key, then a designated wildcard row, then the aggregate's own additive identity
  — and each arm is a separate aggregate over the same table with a different key
  pair, so the only thing a template can carry is the precedence between their
  results. That is enough: a document that computes only the exact arm now reads
  as obviously incomplete beside one that instantiates this.

### 27.3 Retargeting an existing fixture is an audit, and it found a defect

`fixtures/process-brakewear.esm` began as `fixtures/mixed-onroad.esm` with its
snapshot path, database name and hour changed and nothing else. That retarget
alone should have reproduced 250 of the 750 rows exactly, because the energy
block *is* `mixed-onroad`'s chain at hour 7. It reproduced them at a worst cell
of **1.539 × 10⁻²**, all of it on fuel 9, at exactly `1/1.015625`.

The cause was §27.2's wildcard: `temperatureadjustment`'s one row is keyed
`regClassID` 0, `mixed-onroad` implemented only the exact-class lookup, and at
66.9 °F its `adj < 0` clamp returned the correct factor of 1 **for the wrong
reason**. At 59.5 °F the adjustment is +0.015625 and does not clamp. Both
fixtures now instantiate the template, `mixed-onroad`'s 250 numbers are unchanged
to the last digit, and both carry an inline test that pins the exact-class
lookup's absence rather than the factor it happens to produce.

**The rule:** a fixture that agrees with its reference has been checked at one
point of its input space, and a clamped stage is checked at *no* point when the
clamp fires (§23 says the same about a stage multiplied by zero). **Moving one
scope dimension — an hour, a month, a county — onto a neighbouring snapshot is
the cheapest available audit of everything the first fixture could not see**, and
it should be the first move on a new rung rather than the last.

### 27.4 What the new slice still cannot check

Stated here because §23's discipline applies to this fixture too. Brake wear's
`emissionrate` covers **five** of `W`'s 23 operating modes (0, 1, 11, 21, 33),
carrying 12.84 % of the weekend weight and 19.89 % of the weekday weight. So a
perturbation of `W` confined to the other eighteen modes moves the 500
particulate rows not at all. The energy block remains the complete check on `W`;
the particulate blocks check something different — that the *same* weights,
contracted against a rate table five orders of magnitude smaller, still reproduce
`baserate_9_2020` to 2 × 10⁻⁶.

## 28. A shared spine does not imply a shared distribution **[Phase 5, 750 rows]**

`fixtures/process-tirewear.esm` is the second multi-pollutant fixture and, on
paper, `process-brakewear` with three identifiers changed: same 750 rows, same
three blocks, same `BaseRateCalculator` spine, same chained PM10 pollutant, and a
snapshot whose resolved scope is `process-brakewear`'s to the row. It is not.
Key set exact, worst cell 8.151 × 10⁻⁶. `docs/process-tirewear.md` is the
specification; two things are worth stating here.

* **A stage that every neighbouring fixture shares can still be
  process-specific, and the reference will say so with a hard-coded id.**
  `RatesOpModeDistribution` is written by *two* generators.
  `BaseRateGenerator` drives the drive cycles itself only for processes 1 and 9
  (`mod.rs:156-161`); process 10 is served by
  `AverageSpeedOperatingModeDistributionGenerator`, which binds
  `TIREWEAR_PROCESS = ProcessId(10)` and errors out for anything else. So tire
  wear's operating modes are 400–416, binned on average speed alone, and
  `avgspeedbin.opModeIDTirewear` — one nullable column of a sixteen-row table —
  is the entire model. `W` therefore acquires a pollutant-process axis, and the
  selector is a **process** test with both constants named as enum members,
  because that is what the reference is on both sides.

  **The rule:** when a fixture shares a spine with a landed one, check whether
  each stage's *inputs* are keyed by the new pollutant-process before assuming
  the stage is. `docs/process-brakewear.md` §3.2 asked exactly this question of
  brake wear and answered "no, `W` is unchanged" — correctly, and one process
  later the answer is "yes".

* **Do not exploit a disjointness the data happens to have.** Tire wear's rate
  modes (400–416) and the drive cycle's (0, 1, 11–40) do not overlap, so a single
  39-mode `W` carrying both families would reproduce all 750 rows. That would be
  writing down a coincidence rather than the rule, and — the part that is
  checkable — it would make the two structural assertions that distinguish the
  designs *unstatable*: `pp_WModeCount` is 23 on the energy block and 16 on both
  tire-wear blocks, and `pp_WTotal` is 1 on each family; a union's answers are 39
  and 2. §23's discipline applied to the document rather than to the fixture: a
  stage that is only right because another stage happens to be zero is checked at
  no point.

### 28.1 The retarget audit, when the neighbouring snapshot is not neighbouring

§27.3 made retargeting the first move on a new rung. Done here it was **clean**:
`mixed-onroad` and `process-brakewear`, pointed at the `process-tirewear`
snapshot with nothing changed but the paths, both reproduced all 250 energy rows
at 7.106 × 10⁻⁶, and `process-brakewear`'s retarget emitted the correct 750-row
key set with the correct SCCs.

**A clean audit is a result, and this one is a weaker result than §27.3's.** That
snapshot's scope *is* `process-brakewear`'s — same month, hour, day types,
county and fuels, with `sho`, `avgspeeddistribution`, `driveschedulesecond`,
`sourcetypeagedistribution` and `hourvmtfraction` byte-identical between the
two. No scope dimension moved, so no clamped stage could have been exposed; the
audit confirms the §27.3 fix rather than extending it. The refinement to the
rule: **a retarget audits what the two snapshots DISAGREE about.** Move an hour,
a month or a county and it audits the stages those dimensions drive; keep the
scope and change the pollutant set, as here, and it audits the pollutant
generalisation instead — which is a real check, and a different one.

What it did do immediately was name the work. The retargeted `process-brakewear`
returned **exactly 0** — the additive identity, not a wrong number — on all 500
particulate rows, because `dc_W` has no weight on modes 400–416. One run, and the
whole of §28's first bullet was visible before a line was written.

---

## 29. What the chained-off-energy slice changed **[Phase 5, 336 rows]**

`fixtures/process-refueling.esm` is the first document in this port whose
calculator computes no rate on the running-exhaust spine at all.
`RefuelingLossCalculator` chains off `BaseRateCalculator`'s **Total Energy
Consumption output** and uses it as *activity*, converting energy to fuel volume
through the fuel's energy content and density: 336 rows over 118 (THC ×
Refueling Displacement Vapor Loss) and 119 (THC × Refueling Spillage Loss), key
set exact, worst cell 7.434 × 10⁻⁶. Every rule in §1–§28 held. Three gained a
reason and four things are new.

### 29.1 Three rules that gained a new reason

* **§2, tables stay tables — a piece of DDL is a relation.** The spillage
  section of `RefuelingLossCalculator.sql` `ALTER`s a `fuelTypeID` column onto
  its county-year extract, duplicates the gasoline row as E85 and `INSERT`s
  zero-adjustment rows for three more fuels. That is five rows of model logic
  written as schema changes, and §24's rule — MOVES keeping something outside
  source is an implementation detail with no semantic weight — covers it: it is
  a five-row `const` relation with the key built from `enums`, joined to, not a
  branch. It is *inert* in this run and written anyway, because its two arms
  differ the moment a Stage II county is run.

* **§3's semi-join, for a right-hand side that is not unique.** `regioncounty`
  maps one county to one fuel region **twice**, once per `regionCodeID`. Reading
  the region as a value — `Σ regionID` over the matches — gives 540000000 and
  joins to nothing. The shape is `bool_and_or` with a numeric body, and the rule
  generalises: **before reading a lookup as a value, check that its right-hand
  side is unique on the key you are joining by**; a duplicate is silent and its
  wrong answer is plausible.

* **§27.1's flat `(pollutant-process × cohort)` rate relation, for a run whose
  pollutant-processes are in THREE roles.** Seven here: two the calculator
  produces, three it consumes, two it must not touch (Total Organic Gases on the
  same two processes, produced downstream by speciation). All seven ride the one
  relation and the roles are computed columns on it.

### 29.2 Four things that are new

**A chained calculator's INPUT is an output of another calculator, and the units
are the worker's, not the run's.** MOVES rebases kilojoules to the RunSpec's
energy unit in the *output processor*, after every chained calculator has run
(`moves-framework/src/execution/engine.rs:1078-1086`). So the refueling rows
consume raw kilojoules and the 1,055,055.9 divisor is applied only to the
emitted row — where, both refueling pollutants being mass, it is exactly 1. The
document computes that 1 through the same `rspp_isEnergy` test that gives the
three energy rows 1,055,055.9, so the 1 is a measurement. **The general rule:
when a stage consumes another stage's output, find where the unit conversion
happens relative to the two, and compute the factor rather than assuming it** —
a factor of 10⁶ applied one step early still passes every ratio check between
blocks that share it.

**A per-block ordinal is only available when the blocks are the same size.**
§22's rank is one layer of three, and `process-brakewear` could decompose an
output row number into (block, day, cohort-rank) because its three blocks were
125 cohorts each. Refueling's are **64 and 104** — `refuelingcontroltechnology`
carries two fuel types and `sourcetypetechadjustment` is keyed without fuel at
all — so there is no block length to divide by. The shape that works is **one
rank across the whole rate relation**, zeroed on non-members, with the
pollutant-process read *back* through the rank join like every other key. It is
strictly more general than the block decomposition and costs one aggregate; the
block form is worth keeping only where the reader gains from the block being
addressable.

**A NULL column must be guarded with a VALUE, not with an indicator.** A NULL
arrives from the parquet reader as NaN (§11), and `0 × NaN` is NaN — so
multiplying a presence flag into a sum does *not* remove a missing cell, it
poisons the whole aggregate. The SQL's own `WHERE energyContent > 0` written as
`ifelse(x > 0, x, 0)` does remove it, because `ifelse` selects its branch before
evaluating it (§20.3, arrived at there for a recurrence's base case). This is
the ninth instance of the plausible-wrong-value failure this repository tracks
and the second where a clamp-shaped construct is the defence rather than the
cause: §19.4a's `max(NaN, 0)` destroyed a sentinel, and here `ifelse` is what
stops one propagating. **Write the extract's `WHERE` as a value at the column
that can be NULL, not as a factor at the point of use.**

**Two independent chains can produce the same zero, and which one the document
models is a choice with a stated condition.** The run's start-exhaust and
extended-idle energy contribute exactly nothing. The reference discards them
with a **road-type join** — those rates are emitted off-network and the RunSpec
selects road type 4. The port discards them one step later, with an
**operating-mode contraction** — their rates are on modes 101–108 and 200 and
`dc_W` covers the 23 running modes. The two agree *only because no off-network
road type is selected*, so the document computes that condition
(`run_offNetworkRoadTypeCount` = 0, beside a `run_selectedRoadTypeCount` of 1)
and asserts the pair of exact zeros as a total rather than at a sample
(`pp_energyTotal`). The independent oracle deliberately models the **other**
mechanism, so a future snapshot that separated them fails in one of the two and
not in both. **Where a port reproduces an effect by a different route than the
reference, write down what makes the two routes equivalent and assert it.**

### 29.3 What the slice cannot check, and where it moved instead

§23 applied, and the answer is larger than in any earlier slice: **five** stages
of this calculator, and one whole branch of the spine it chains off, are
unobservable at this fixture's inputs. Both Stage II
program reductions are exactly 0 in the county and year, so the two `(1 − P)`
factors are 1; the refueling temperature never leaves gasoline's `[45, 90]`
window; the tank-temperature difference never leaves `[0, 20]`; and the vapour
floor that *binds* is never reached, because the one fuel whose raw rate is below
its floor takes the sentinel branch instead.

The branch is the one no earlier slice would have predicted, because it is a
stage that two earlier fixtures *do* see: the electricity cohorts' EV
temperature factor and EV efficiency divisor move real output cells in
`mixed-onroad` and `process-brakewear` — the missing wildcard step was a 1.56 %
error on 84 of brake wear's rows — and move **zero** here, measured by
perturbing each stage's own input and diffing all 336 emitted cells byte for
byte (`docs/process-refueling.md` §7.2, with two positive controls beside the
three zeros). A refueling row sums
the energy of its own `(modelYearID, fuelTypeID)` cohort and every electricity
cohort is dropped by REFEC-7's fuel-type join, so fuel-9 energy never reaches an
emitted cell. **A stage a neighbouring fixture checks is not thereby checked in
this one**, and the direction of that is not predictable from the two run
scopes: this fixture's hour is the one that makes the EV arm live, and it is
also the one where nothing depends on it.

All five moved to `components/refueling_loss_rate.esm`, on five probe
coefficient sets and three control cases at values chosen so both branches
differ — which is §23's point 1 applied without exception. What is worth
recording is the shape of the split that resulted: **the fixture keeps
everything relational and the component keeps everything arithmetic.** The
fixture checks the market-share-weighted RVP over a real fuel supply with two
inner-join misses in it, the reg-class wildcard's row count, the control-blend
at both endpoints and in between, and the two exact zeros of the energy spine —
none of which a `const` component could pose. The component checks four clamps
and a sentinel — none of which the fixture's own inputs reach. Neither half is a
weaker version of the other, and a slice that produced only one of them would
have been checked at half its surface.

---

## 30. What the NOx-speciation slice changed **[Phase 5, 872 rows]**

`process-nox-speciation` is the first fixture to compute a **criteria
pollutant**. The speciation it is named for turned out to be the cheap half —
three ratios and a self-join, `process-brakewear`'s chain with a different
table. The expensive half was the parent, and it is the parent that produced
these five conventions.

### 30.1 A row set can be decided by a key you added for a value

`emissionrate` is **empty** in this snapshot; running-exhaust NOx lives in
`emissionratebyage`, which is `emissionrate` plus an `ageGroupID` column. The
obvious reading of that is "one more join key on the rate lookup" and it is
incomplete. The seventh key also decides **which cohorts are emitted at all**:
fuel type 9 has rows for age groups 3 through 1519 and none for 2099, so the one
electricity cohort aged ≥ 20 finds no rate and does not appear, while model
years 2001–2020 appear at rate exactly zero. Adding the key as a value and
defaulting it on a miss reproduces every emitted number and emits 878 rows
instead of 872.

The general form: **a lookup that has gained a key has gained a way to miss, and
a miss is a row-set fact.** `require_exact_key_set` is what catches it; the
per-cell check cannot, because the extra rows are perfectly good numbers.

### 30.2 A chained row's existence is a property of its parent, not of its own tables

`process-brakewear`'s PM10 block emits exactly the cohorts its PM2.5 parent
emits, because the ratio table covers all of them. That made survival look like
a property of one relation. It is not. Here `nono2ratio` has no fuel type 9 row,
so the species drop the whole electricity column — 104 cohorts against the
parent's 124 — and the surviving condition is a **conjunction across two
relations one of which is the rate relation itself**:

```
rt_survives = rt_directSurvives
            + rt_hasChainRatio × rt_parentDirectSurvives
```

where `rt_parentDirectSurvives` is a self-join on
`(rt_chainInputPolProcessID ↔ rt_polProcessID, rt_cohortOrdinal ↔ rt_cohortOrdinal)`
— the same pair the *quantity* is already chained on, so no new join shape is
introduced. It is a **sum rather than a branch** because no row can satisfy both
arms: a chained pollutant-process has no rate row and an unchained one has no
ratio row, exactly as `rtDay_quant = direct + chained` already relies on.

Neither half alone gives the right answer, and the fixture asserts the row where
they differ: rate row 288 is NO on electricity model year 2020, whose parent
**does** survive (it is emitted, at zero) and which is still not emitted,
because there is no ratio. A document that took survival from the parent alone
emits 124 species cohorts; one that took it from the ratio alone emits 105.

Write the parent-survival arm even when the current ratio table happens to cover
everything. `process-brakewear` did not need it and would need it against a
snapshot whose ratio table had one gap.

### 30.3 Instantiate the flat-relation templates; three fixtures spell them out

`lib/keys.esm` has carried `flat_relation_major`, `flat_relation_minor` and
`flat_relation_block_index` since the NONROAD slice, and its own description
says why: the two coordinates of a flat product **share one floor division**, and
a hand-written pair can disagree about where a block ends. Three fixtures —
`mixed-onroad`, `process-brakewear`, `process-refueling` — write

```
floor((o - 1) / block) + 1        and        (o - 1) - block × floor((o - 1) / block) + 1
```

out by hand at every such site, six sites in the two Phase-5 documents alone.
This fixture instantiates the templates for its output decode. It is the same
miss §26 recorded for `model_year_in_range` — a template lands, and the next
document is authored from the *previous* document rather than from the library —
and the same remedy: **on merge, diff `lib/` against what the new document
hand-spells, not just against what it changed.** The remaining hand-spelled
sites are a follow-up, not a defect; they are correct, and converging them is a
change to three passing fixtures that has to be verified byte for byte.

### 30.4 An equation carried as a text column is two aggregates, not one expression

`noxhumidityadjust.humidityNOxEq` is `CFR 86` or `CFR 1065`, and the two name
genuinely different formulae — linear in bounded specific humidity, reciprocal
in bounded water mole fraction. Two consequences.

**The selection is a `join.on`, not a filter.** §20.4 admits no exception for an
equality against a constant; the text is decoded to 86 and 1065 by a `codes` map
and joined to two one-row relations. The first draft wrote both as `==` inside a
`filter` and `tools/check-conventions.py` rejected it, which is the rule working.

**The arms must be separate aggregates, for a NaN reason.** `humidityTermB` is
NULL — hence NaN — on the CFR 86 rows. Because the arms are separate aggregates
with different join keys, that NaN is never in a row the CFR 1065 aggregate
reads and never reaches an operator. Folding both forms into one expression
under an `ifelse` would not have helped: an `ifelse` selects a *result*, it does
not stop an operand being evaluated, so every gasoline cohort would return NaN.
This is the same shape as §29.2 — **write the branch at the relation, where the
row can be excluded, not at the expression, where the value has already been
read.**

### 30.5 A `regionCounty`-shaped table is a SET, and joining it doubles the answer

`fuelsupply` is keyed by `fuelRegionID` and a captured snapshot pools every
selected county's region into one table, so the port restricts it to the run
county's regions (`baseratecalculator/mod.rs:1110–1149`) — and it does so with a
`BTreeSet`. `regioncounty` has **two** rows for (26161, 270000000), differing
only in `regionCodeID`. Joined as a relation, each supply row matches twice and
every market share doubles: a silent 2× on the whole inventory, invisible to the
key set and to any structural check, and visible only as every cell being twice
what it should be.

Consumed as a `max`-semiring **presence flag** it is the set the port actually
uses. The tell is in the reference: **where the source collects into a set and
tests membership, the port needs a presence flag; where it collects into a map
and looks up, the port needs a join.** `lib/keys.esm`'s description already says
`presence` arguments are computed with a `max`-semiring aggregate; this is the
first fixture where getting it wrong would have been a factor-of-two error
rather than a missing row.

### 30.6 What the slice cannot see

§23 applied. `imcoverage`, `emissionrateadjustment` and `evefficiency` are all
**empty** in this snapshot, so three of `adjust.rs`'s stages are absent rather
than exercised, and `GPAFract` is 0 so every fuel-effect blend selects its
normal arm. The one worth naming separately is the **A/C arm, which is live in
its tables and dead in its result**: `fullacadjustment` has 23 real
`polProcessID` 301 rows, `rtDay_meanBaseRateACAdj` is a real number and is
asserted against the reference's own `baseratebyage_1_2020` — and
`run_acActivity` clamps to 0 at this heat index, so `rt_acFactor` is exactly 0
and none of it reaches an emitted cell.

That matters for one claim in particular. `adjust.rs` applies the criteria ratio
and the temperature factor to **both** the rate and its A/C companion before
adding the increment, and the fixture folds that into
`(rate + acFactor × acAdj) × temperature × criteria`. **The fold is correct and
untested**: with `acFactor` exactly 0 no ordering of those three factors changes
any emitted number. It is written in the source's order because that is the
port, and the document says so rather than letting a green comparison imply
otherwise. A fixture at an hour above about 68 °F on the heat index would test
it; this one cannot.

---

## 31. When the blocks are ragged, rank GLOBALLY **[Phase 5, 1,368 rows]**

§22 built a rank because a rectangular axis emits keys the snapshot does not
have, and because the ragged axis needs a padded member array the flat relation
does without (finding **F14**, retired: the axis does evaluate, in the spelling
esm-spec §4.3.1 now states). Three onroad fixtures then reused that shape at a
level up: the output relation is pollutant-process-major blocks of
`n_outputCohort × n_runspecday`, and an output row is addressed as *(block, day,
cohort rank)*.

**That layout carries a hidden precondition, and `process-crankcase-running` is
the first fixture to violate it: every block must span the same cohorts.** Its
six pollutant-processes do not. `crankcaseEmissionRatio` has no fuelTypeID 9
row and `CrankcaseEmissionCalculator.sql`'s join is an `INNER JOIN`, so the
twenty electricity cohorts emit a process-1 row and no process-15 row: three
blocks of 124 and three of 104.

**The fix is not a second rank, or a per-block offset table. It is to stop
letting the layout carry the pollutant-process at all.**

```
rt_emits[b]         -- does this rate row become an output row?
rt_prefixEmitted[b] = SUM over x <= b of rt_emits[x]     -- inclusive prefix count
rt_outputRank[b]    = rt_emits[b] x rt_prefixEmitted[b]  -- dense 1..N over ALL blocks
output row o        = (major(o, n_runspecday), minor(o, n_runspecday))
                    = (rank, day)
```

The rank runs over the whole rate relation rather than restarting per block, so
a short block simply contributes fewer ranks. The output relation is
`N × n_runspecday` — one flat product, two coordinates, no pollutant-process
factor — and every identity column of the output row, the pollutant-process
included, is read back through the rank join from the rate row it reaches. Which
rows emit is a consequence of the arithmetic; nothing about the shape of the
answer is written into the layout.

Three things follow, and each was worth the change on its own.

1. **The mask is where the two calculators meet.** `rt_emits` has exactly two
   arms and they are the two MOVES modules this fixture ports:

   ```
   rt_emits = isChained ? (chainSourceEmits AND hasChainRatio) : survives
   ```

   An exhaust row emits when `BaseRateCalculator` selects *and* rates its
   cohort; a crankcase row emits when its exhaust row did *and*
   `CrankcaseEmissionCalculatorNonPM`'s ratio table has a row for it. The
   `INNER JOIN` that drops a row and the `if let Some` that returns a factor of
   one are different things and they sit in the same expression, one in the
   mask and one in the value — which is the distinction §22's point 2 makes,
   restated for a chain.

2. **The per-block count becomes an assertion instead of a declaration.** With
   rectangular blocks, `n_outputCohort` is a metaparameter and a wrong block
   size is a length error somebody notices. With a global rank the only
   declared number is the TOTAL, so the split has to be measured separately:
   `pp_emittedCohortCount` counts the mask per pollutant-process and pins
   124/104/124/104/124/104. **1,368 rows is equally consistent with six blocks
   of 114**, and the comparator's exact-key-set check would not distinguish
   them either, because the union of six 114-cohort blocks over the same key
   space can be made to match. A slice whose blocks are ragged must assert the
   raggedness; the row count is not evidence of it, and neither is the key set.

3. **Fewer moving parts, not more.** The rectangular form needed a block
   offset, a within-block day ordinal, a within-block cohort ordinal and a
   repacked `(block, cohort)` key. The global form needs `flat_relation_major`
   and `flat_relation_minor` from `lib/keys.esm`, once. The ragged case is
   *simpler* than the rectangular one — which is the argument for using it even
   where the blocks happen to be equal, and the reason this section says
   **rank globally**, not "rank globally when you must".

**The rule.** Rank the rows that emit, over the whole relation they live on,
and let the output axis be that rank crossed with the axes that are genuinely
rectangular. Reserve a block layout for the case where a coordinate is
independently meaningful, and then assert its extent per block rather than
declaring it.

**And check the precondition before reusing a layout.** The rectangular form
worked in `process-brakewear` and `process-tirewear` and it worked for a reason
neither document stated, because in both of them it was true by accident: every
pollutant-process shared one cohort set. It took a fixture where that is false
to notice the assumption existed. When a later slice reuses a shape from an
earlier one, the question is not whether the shape fits the new numbers — it is
what the earlier slice was quietly relying on that nobody wrote down.

---

## 32. A chain deeper than one level **[Phase 5, 1,288 rows]**

`process-airtoxics` is the first fixture whose `runspecchainedto` is more than
one hop: 7901 ← 101, 8701 ← 7901, and 2001/2401/2501 ← 8701.
`docs/process-nox-speciation.md` §2.5 closed by saying that a fixture reaching
one "would have to resolve the parent's own survival first". It does, and
resolving it turned out to cost one thing repeated rather than one thing
generalised — which is the whole of §32.1. The other four sections are what the
two calculators either side of that chain forced.

### 32.1 Iterate the parent join; do not widen it

§30.2's rule is that a chained row exists where its ratio exists **and its
parent row does**, and its shape is a self-join on
`(rt_chainInputPolProcessID ↔ rt_polProcessID, rt_cohortOrdinal ↔ rt_cohortOrdinal)`.
At depth three the tempting move is a wider join — a two-hop or three-hop key,
or a `chainRootPolProcessID` column read from a hand-written map. Both are
worse, and the second is worse in a way that is easy to miss: a root written
down is no longer read from MOVES.

What works is the same clause, three times, over a different operand:

```
rt_survives        = rt_isSelected × rt_hasRate          -- depth 0, the only rated rows
rt_emitsAtDepth1   = rt_hasChainRatio × parent(rt_survives)
rt_emitsAtDepth2   = rt_hasChainRatio × parent(rt_emitsAtDepth1)
rt_emitsAtDepth3   = rt_hasChainRatio × parent(rt_emitsAtDepth2)
rt_emits           = rt_survives + rt_emitsAtDepth1 + rt_emitsAtDepth2 + rt_emitsAtDepth3
```

and the same three iterations on the six-row pollutant-process relation give
`rspp_rootPolProcessID` and, free with it, `rspp_chainDepth`. **A
pollutant-process sits at exactly one depth, so at most one term is non-zero on
any row and the sum is a union** — the argument §30.2 already made for two arms,
which does not weaken as arms are added. A fourth level costs one more pair of
equations and no new join; `TOGSpeciationCalculator` chains off
`HCSpeciationCalculator`'s TOG and would need exactly that.

**`rspp_chainDepth` is not used by the arithmetic and is worth computing
anyway.** It is the structural fact this rung adds, it is asserted (0, 3, 3, 3,
1, 2 in the table's own row order), and it is the only thing in the document
that would notice if `runspecchainedto` were read as a flat parent map rather
than as a chain.

### 32.2 Anchor a multi-stage chain at its ROOT, not at its parent

Every ratio downstream of `BaseRateCalculator` scales the same THC fuel block.
That is not a convenience: `criteriaratio` carries `polProcessID` 101 **only**,
`emissionratebyage` carries 101 only, and `fullacadjustment` carries 101 only.
So the lookups key on `rt_rootPolProcessID`, and the rate arrives through one
self-join on `(root, cohort)`:

```
rtDay_rootRate[b,k] = Σ over the root row of (meanBaseRate + acFactor × acAdj) × temperatureFactor
rtDay_quant[b,k]    = rtDay_rootRate[b,k] × rt_fuelFactor[b] × rtDay_activity[b,k]
```

`process-crankcase-running` chained the *quantity* instead — a crankcase row was
its parent's emitted quantity times a ratio — and that is right for a
one-level chain whose ratio applies at the fuel-type level. It does not survive
§32.3. Anchoring at the root also removes `rtDay_quantDirect` /
`rtDay_quantChained` / `rtDay_quant` as three separate variables: with the chain
inside the multiplier there is one quantity and no union to argue about.

**The tell for which anchor a slice needs is in the ratio tables' own
`polProcessID` column**, not in the calculator's prose. If the downstream
tables carry the *parent's* id, the chain is a property of the block and the
root is the anchor; if they carry the *chained* id, as `crankcaseemissionratio`
does, the parent is.

### 32.3 A per-formulation chain collapses ONCE, at the end

`criteriaratio` keys on the fuel **formulation**; `methaneTHCRatio`,
`HCSpeciation` and `ATRatioNonGas` key on the fuel **subtype**; `ATRatio` keys
on the formulation again. All of them therefore live on the (rate row ×
supplied formulation) relation, and the market-share collapse
(`aggregate.rs:28–45`) has to happen **after the whole chain has been formed**:

```
rt_fuelFactor[b] = Σ over supplied f of ( share_f × criteriaRatio_f × speciationChain_f[b] )
```

Collapsing earlier — computing a fuel-type-level criteria ratio and then a
fuel-type-level speciation factor and multiplying them — is the product of the
means where the arithmetic wants the mean of the products. **It is exactly
right whenever a fuel type has one formulation, which is every county in this
corpus**, so no fixture here can fail on it. Write the general form and record
that it is untested; the spec's §7.2.6 does.

The same applies to the *existence* half. `rt_hasChainRatio` is an OR over the
**supplied** formulations of the per-formulation test, not a test on the fuel
type: a ratio row for a formulation nobody sells keeps no row alive.

### 32.4 Two calculators, two shapes — write each one's own

Both stages of this rung scale a THC block, and it is tempting to write them
alike. The sources are not alike, and the difference is checkable rather than
stylistic: **`hcspeciation.rs` has no `RunSpecChainedTo` table at all** — it
takes one THC emission and returns up to five species in a single pass — while
`airtoxics.rs` reads it three times, once per `ATRatio*` path. So NMHC and VOC
are written as a direct multi-output stage and the toxics as a chained
self-join, and the document's shape is evidence about MOVES rather than about
its author's taste.

Forcing the HC stage into the chained shape would also have cost a division.
On the E85 `altTHC` path the VOC operand is `altNMHC`, **not** the NMHC the run
emits, so expressing VOC as `NMHC × ratio` requires dividing `(1 − CH4THCRatio)`
back out — a division by a table value, introduced by the re-expression and
present in neither source.

**Two more things fall out of writing each stage its own way.** The VOC lookup
keys on `hcspeciation.polProcessID`, which *is* the output pollutant-process, so
the join both finds the constants and identifies which rate rows are VOC rows —
pollutant 87 is named nowhere in the document. And NMHC has no such table, so 79
*is* named, from `hcspeciation.rs`'s own `NMHC_POLLUTANT_ID` constant. **Name a
pollutant exactly where the source names one**, and let a join do it everywhere
else.

### 32.5 What the slice cannot see

§23 applied, and this slice's list is long enough to be worth a rule of its
own. Four of `AirToxicsCalculator`'s six ratio paths have **empty tables**;
three of `HCSpeciationCalculator`'s five species are **not selected**;
`temperatureadjustment` and `generalfuelratio` are **empty**, so two adjustment
stages are absent rather than inert; `oxySpeciation` is 0 on all 136
`hcspeciation` rows, so the speciation factor's oxygenate term is live in its
inputs and dead in its coefficient; and `atRatioNonGas` is **identical on fuel
subtypes 20/21 and on 51/52**, so reading the supplied subtype rather than the
fuel type's default is correct and unfalsifiable here.

The last one is the one worth generalising. **When a lookup's key could
plausibly be either of two columns and the table gives both the same value, the
fixture cannot choose between them — and the oracle should assert the
identity**, so a later reader can see that the choice was made from the source
and not from the answer. `run-airtoxics-oracle.sh` does that for the two subtype
pairs; a comparison against `MOVESOutput` never could.

---

## 33. What the PM-exhaust slice changed **[Phase 5, 1,456 rows]**

`process-pm-exhaust` is the first fixture with **no unchained parent block**.
Every rung since `process-nox-speciation` was a 248-row parent computed off a
rate table plus *N* × 208 species blocks that fell out of it by ratio; this one
is seven 208-row blocks and nothing unchained. Two of the seven **are** the
parents, and they are 208 rather than 248 because the twenty electricity
cohorts reach `SulfatePMCalculator`'s working table and are dropped *there*, one
stage after the rate.

Five things follow, and the first is a limit on §32 rather than an addition to
it.

### 33.1 A chain declaration is not a computation graph — check that it is acyclic before iterating it

§32.1's rule is "iterate the parent join; do not widen it", and it works by
applying one self-join once per level of `runspecchainedto`. **That presumes the
chain table IS the computation order, and here it is not.** This snapshot's
eight rows contain two 2-cycles:

```
11801 (NonECPM) <- 11501 (sulfate)      and   11501 <- 11801
11801 (NonECPM) <- 11901 (H2O aerosol)  and   11901 <- 11801
```

because `SulfatePMCalculator` splits composite NonECPM into species and then
**re-sums NonECPM from them**. `pollutantprocessassoc`'s `chainedto1` /
`chainedto2` columns carry the same cycle. So a fixed-point iteration over that
table does not terminate, and a `rspp_rootPolProcessID` is not a well-defined
thing to compute.

The tell, stated generally: **MOVES's chain table records a calculator's
INPUTS, not an evaluation order.** `SulfatePMCalculator` genuinely takes 118 in
and puts 118 out, and the table records both facts with nothing to distinguish
them. So:

* **Write the calculator's stages.** `sulfate_pm_calculator.rs::calculate` is
  five stages and they are a DAG even though MOVES's declaration of them is
  not. The document has five stages.
* **Read the chain table for what it says unambiguously**, which is a row-set
  fact: which pollutant-processes are chained at all. `rspp_isChainOutput` is 1
  on six of the seven; only 11201 is never an output.
* **Measure the cycle rather than describing it.**
  `run_chainCycleCount` = |{p : p is both an input and an output}| = **4**, and
  `run_unchainedPolProcessCount` = **1** while **two** pollutant-processes are
  RATED. That gap is the finding: *MOVES's chain declaration cannot even
  identify the rated set here*, so `rt_hasRate` decides it and the chain table
  decides nothing. A one-line count in the document is worth more than a
  paragraph in a spec, because it fails if a later snapshot differs.

**This is not a `docs/findings/` entry.** That directory collects what the
FORMAT or the TOOLCHAIN could not express, each with a repro expected to fail.
Nothing was refused here and nothing was silently wrong; the format expresses
the fix without difficulty. What §32.1 was carrying implicitly was a
precondition, and this section is that precondition written down.

### 33.2 A parent can be a PAIR, and then the pull is per parent

`emissionratebyage` carries 11201 (unadjusted elemental carbon) and 11801
(composite NonECPM) and nothing else, and **five of the seven emitted pollutants
are functions of both** — PM2.5 total is elemental carbon plus NonECPM. A
single-parent chain cannot express that, however deep it iterates.

The shape is §32.2's anchor-at-the-root self-join, instantiated once per named
parent:

```
rtDay_ecQuant[b,k]    = Σ over b2 of rtDay_ratedQuant[b2,k]
                        join (rt_ecPolProcessID[b] ↔ rt_polProcessID[b2],
                              rt_cohortOrdinal ↔ rt_cohortOrdinal)
rtDay_nonECQuant[b,k] = the same with rt_nonECPMPolProcessID
```

On the parent's own row each selects that row's own quantity, exactly as
`rtDay_rootRate` did. **The generalisation is that "the block this row derives
from" is a set, not a value**, and a set of fixed known size is written as one
pull per member rather than as a wider join.

### 33.3 Composition by IDENTITY: carry it as shares, not as a branch per pollutant

`SulfatePMCalculator` composes its outputs out of four working species by
literal arrays of pollutant ids — `PM25_TOTAL_INPUTS`, `NON_EC_PM_INPUTS`,
`COPIED_SPECIES` in the Rust, `IN (…)` lists in the SQL. **There is no table to
look the composition up in**, so §32.4's "name a pollutant exactly where the
source names one" cuts the other way from how it cut in `process-airtoxics`:
five pollutant ids are named here, and every one is a named constant in
`sulfate_pm_calculator.rs`.

What is worth keeping is the SHAPE that follows. Seven emitted pollutants over
four species is a 7 × 4 matrix of coefficients, and writing it as seven branches
on the pollutant is unreadable. Written as one **share column per species** it is
four lines, each of which is a sum of MOVES's own arrays:

```
rt_totalShare   = rt_isPM25Total + rt_pm10Ratio          -- PM25_TOTAL_INPUTS, and PM10 rides on it
rt_ecShare      = rt_totalShare + rt_isElementalCarbon   -- + COPIED_SPECIES
rt_sulfateShare = rt_totalShare + rt_isNonECPM + rt_isSulfate
rt_waterShare   = rt_totalShare + rt_isNonECPM + rt_isWater
rt_residueShare = rt_totalShare + rt_isNonECPM + rt_pmSpeciationFraction
rtDay_quant     = Σ over the four species of share × speciesQuant
```

and `rtDay_quant` carries **no branch on the pollutant at all**. Two of the
seven pollutants then fall out as *factors* rather than as cases, because their
ratio table is keyed by the OUTPUT pollutant-process:
`pm10emissionratio.polProcessID` is 10001 and
`pmspeciation.outputPollutantID` is 111, so joining a rate row's own key to
either one both finds the coefficient and decides whether the row is that
pollutant. **Pollutants 100 and 111 appear nowhere in the document.** A share
column that is 0 on every row a lookup missed is the same construct as
`process-brakewear`'s "the same expression serves chained and unchained blocks
with no branch".

### 33.4 The selection test belongs to whichever relation the SOURCE keys it on

`pollutantprocessmodelyear` carries rows for **five** of the seven
pollutant-processes: MOVES builds a source bin only for something it can RATE,
and organic carbon and H2O aerosol are produced by a speciation fraction and by
a split. So `rt_isSelected` — S10's row rule, which requires a model-year group
— is 0 on two of the seven blocks, and rungs 4–6's habit of gating the emission
on it would have emptied them.

The fix is one line (`rt_cohortIsSelected` reads `coh_isSelected` back onto the
rate relation) and the rule is worth stating because the symptom is a *missing
block*, not a wrong number: **a per-pollutant-process test may only gate the
stage whose table is keyed per pollutant-process.** `rt_isSelected` still gates
the rate lookup, where it belongs, and `pp_selectedCohortCount` asserts
125, 125, 0, 125, 125, 125, 0 so the two zeros are in the document rather than
in a comment.

### 33.5 When two misses would each produce the row set, compute BOTH

`docs/process-airtoxics.md` §2.6 resolved three misses in **series** down a
chain, where any one sufficed because the later stages could not outlive the
earlier. This rung has two in **parallel** on the same cohort: the twenty
electricity cohorts have no `sulfatefractions` row (so the NonECPM split's inner
join drops them) *and* no `crankcaseemissionratio` row (so the copied
elemental-carbon rows are dropped one stage later). Either alone produces
exactly the observed 104-cohort key set.

So the row set is **not evidence for which one MOVES uses**, a document that
implemented one of them would be right for the wrong reason, and `rt_emits` is a
product of both existence flags because `sulfate_pm_calculator.rs` performs both
joins. The oracle asserts the two absences separately for the same reason. The
general rule: *an existence test justified only by the row count it produces is
justified by nothing when a sibling test produces the same one.*

### 33.6 One table, two stages, two keys — and the trap of merging them

`generalfuelratio` carries pollutant 112 and pollutant 120 here, and they enter
at **different stages**:

| | pollutant | applied by | keyed on | blended? |
|---|---|---|---|---|
| base rate | 112 (11201) | `BaseRateCalculator`, adjust.rs:452–472 | the SUPPLIED formulation | yes, by `GPAFract` |
| species split | 120 (12001) | `SulfatePMCalculator`, SulfatePMCalculator.sql §75 | the fuel TYPE | no, raw |

`SulfatePMCalculator.sql` restricts its own extract with
`gfr.pollutantID in (120)`. Applying the 112 rows there as well **squares** a
1.090910749585 on every gasoline and E85 cohort of model year 2001 or later;
`../moves.rs` records that trap in a comment at
`sulfate_pm_calculator.rs:2226`, having presumably hit it. The two stages differ
in their join key and in whether they blend, so they are written as two
lookups, and the document instantiates the same table twice under two names.

**A caution that came with it, reinforcing §29.** The sulfate adjustment
divides by a table value (`BaseFuelSulfurLevel`) that is 0 where the lookup
missed. `0 / 0` is NaN and `0 × NaN` is NaN, so a multiplicative existence gate
does not suppress it: the divisor has to be guarded with a **value**
(`rt_baseFuelSulfurLevelGuarded` substitutes 1). `process-refueling` met the
same shape on a NULL-bearing column; two instances make it a rule.

### 33.7 Re-derive the MECHANISM, not just the row

The one cohort this run selects and cannot rate is (model year 2000,
electricity) — **the same cohort `process-nox-speciation` and
`process-airtoxics` lose**, and the inherited explanation for it is wrong here.
Those fixtures lose it on the **age group**: pollutant 101's fuel-type-9 rows
stop at age group 1519 and model year 2000 is aged 20. In this snapshot
`emissionratebyage` carries **all seven age groups for fuel type 9** on both
rated pollutant-processes, and the miss is on the **short model-year group**:
the fuel-9 source bins run over short groups 8, 10–19, 21–50, 53, 55, 57–60 and
66–69, and 20 — the group `pollutantprocessmodelyear` assigns model year 2000 —
is absent.

Same row, different key, and every numeric gate in this repository passes either
way. This is the `tools/check-sources.py` lesson (a note travels with a copied
spine while the table under it changes) applied to a *specification*: **when a
new slice loses the same row as its predecessor, enumerate the miss rather than
citing the earlier reason.** `run-pm-exhaust-oracle.sh` asserts all three halves
— the age groups are complete, short group 20 is absent for fuel 9 and present
for fuel 1, and the miss list over both parents and all 125 candidates is
exactly those two rows — so the next fixture to copy this spine copies a checked
claim.

---

## 34. A key rule can be per PROCESS **[Phase 5, 128 rows]**

`process-evap-permeation` is the third evaporative slice and shares almost
everything with the first two: the run scope, the geography, the activity chain
A1–A10, the cohort structure C1–C4, the operating-mode distribution E1–E3, the
128-row output shape, even the two SCCs but for their process suffix. It is
therefore the slice where copying a sibling's spine is most tempting and most
dangerous, and the three sections below are the three ways it bites.

### 34.1 Read the key rule from the table that carries it, per process

`SourceBinDistributionGenerator` builds a source-bin key from the vehicle's
fuel, engine technology, regulatory class and model-year group — **except that
the regulatory class is replaced by 0 when
`SourceTypePolProcess.isRegClassReqd` is `'N'`**
(`source_bin_distribution_generator.rs:1355`). That flag is keyed on
`(sourceTypeID, polProcessID)`. It is not a property of the run:

| snapshot | `polProcessID` | `isRegClassReqd` | every `sourceBin.regClassID` |
|---|---|---|---|
| `process-evap-leaks` | 113 | `Y` | 20 |
| `process-evap-fvv` | 112 | `Y` | 20 |
| `process-evap-permeation` | 111 | **`N`** | **0** |

So the same 125 cohorts carry different `sourceBinID`s in three snapshots that
are otherwise the same run. **The rule: a join key whose SHAPE is decided by a
table gets that decision read from the table, in the document, once — never
folded into the key's definition.** Here that is one variable,
`coh_binRegClassID = isRegClassReqd ? svpRegClassID : 0`, and every key
downstream of it — the bin existence test, the fuel-usage rebase's
equipped-to-used match on both sides, and PC-1b's rate join — reads that column
and not the sample vehicle's own. `coh_svpRegClassID` is kept beside it and
asserted at 20, so what is discarded is visible rather than merely absent.

**Why this is worth a section rather than a comment: the failure is silent in
the only place a fixture usually looks.** Measured, by giving the bin key the
sibling's rule and rerunning:

| | with C2′ | with the sibling's rule |
|---|---|---|
| `coh_binExists` | 1 | 0 |
| `cohortSurvivorCount` | 64 | **0** |
| every one of the 128 `emissionQuant` cells | §6's values | **exactly 0** |
| rows emitted | 128 | **128** |
| `require_exact_key_set` | passes | **passes** |

The row count is `n_outputCohort × n_runspecday` and neither factor moves, so
the key set is perfect and the answer is zero everywhere. Only the per-cell gate
sees it, and it sees it at all 128 cells at once, which is the least
attributable shape a failure can have. **The cheap defence is a count on the
input side**, not a value on the output side: `sourceBinRegClassZeroCount`
asserts 80 of 80, and it fails the moment a snapshot with the other rule is
pointed at this document.

The same shape has one more instance in this slice, and it is the mirror image:
`EvaporativePermeationCalculator`'s 25 `INPUT_TABLES` list neither `IMCoverage`
nor `IMFactor`, so the I/M blend both sibling fixtures carry as an identity is
**absent from this calculator** rather than zero-weighted in it. Inheriting it
would have modelled a step MOVES does not run, and it would have been green.
**Check the calculator's declared inputs before carrying a stage across.**

### 34.2 When a stage is read rather than computed, read ALL of it and say which cells are inert

§23's rule is to measure whether a fixture can see a stage before asserting it
there. Its corollary, when the answer is no and the stage is therefore *read*
from a captured intermediate, is what to read.

This fixture reads `AverageTankTemperature`, all 288 cells; the oracle computes
96 of them (operating mode 151, through TTG-1's quarter-hour recurrence) and
reads 192. **The fixture deliberately reads more, and that is not laziness —
the 96 the oracle computes are exactly the 96 that cannot move an output digit.**
Both soak modes enter PC-2b at an `opModeFraction` this document computes to be
exactly 0, so recomputing mode 151 in the fixture would duplicate
`components/tank_temperature.esm`'s 64 assertions to buy a check that would
pass with the recurrence deleted — which is precisely the check §23 says not to
write.

What the fixture owes instead is three things, and all three are cheap:

1. **Assert the weight, not the value.** `tankTemperatureSoakWeight` sums the
   two soak modes' `opModeFraction` over both day types and asserts 0. A run in
   which the read cells could reach an output digit fails there, before the
   comparator sees a row.
2. **Assert that the zero-weighted arm is non-zero**, so a zero WEIGHT cannot be
   confused with an absent computation — §23's corollary. `cohDay_tempAdjustByMode`
   is asserted at all three modes: 0.9137 hot-soaking, 0.6194 cold-soaking,
   0.7585 operating.
3. **Say in the document that the read is a read**, which table, how many cells,
   and how that differs from what the oracle reads. A fixture whose metadata is
   silent about a read reads exactly like one that computed it.

### 34.3 The lag of a data-named predecessor is a property of the RELATION, not of the identifier

Finding F28 is that a recurrence whose predecessor is named by a data column has
no direct spelling: `index(V, k − index(lag, k))` is refused because the
coefficient of the frame symbol must be provable. That is correct behaviour and
it is unchanged. **What this rung changed is how to decide whether you are
actually in it**, because this repository spent two documents believing
`TankTemperatureGenerator` TTG-4a was and it is not.

TTG-4a enqueues the trip whose `priorTripID` is this trip's `tripID`. On the
captured `SampleVehicleTrip`, `tripID − priorTripID` is 1 on 24,610 of the
26,300 chained trips and 2…7 on the other 1,690 — from which F28 concluded
there was no constant lag to write. But `tripID` is an identifier, and the
recurrence runs over a *relation*:

| relation, in the order the generator walks it | rows | lag to the predecessor |
|---|---|---|
| `SampleVehicleTrip` as captured | 37,216 | 1 … 7 |
| after `flagMarkerTrips` deletes the 5,458 marker trips | 31,758 | **1, on all 26,193** |
| `SampleVehicleTripByHour`, ordered `(vehID, dayID, keyOnTime)` | 44,513 | **1, on all 26,193** |

The non-unit gaps are the marker trips, which MOVES's own first step removes
before the generator that recurs ever sees them. **The rule: compute the lag on
the relation the recurrence is written over, AFTER every row filter the
reference applies, and only then decide whether the offset is constant.** An
identifier gap is not a lag; a row gap is. Then measure it on more than one
capture, and be careful what counts as another capture. Thirty-nine snapshots
carry a populated `SampleVehicleTrip`, but by `(vehID, dayID, tripID)` key set
they are only **eight distinct tables**, and thirty-six of them omit
`tripType` — so the marker drop above is performable on three, all three of
which are the same evap capture. Checking "four snapshots" that share one table
is one measurement written down four times.

The eight distinct captures do corroborate it, and across more than one model:

| capture | rows | ties | positional lag 1 | exceptions |
| --- | ---: | ---: | ---: | ---: |
| `process-evap-fvv`, markers dropped | 37,216 → 31,758 | 0 | 26,193 | 107 |
| `chain-nonhaptog`, `expand-sourcetype`, `expand-fueltype-diesel`, `process-apu` | 37,216 | 0 | 30,007 | 107 |
| `expand-month` | 37,216 | 0 | 30,094 | 20 |
| `nr-agriculture-state` (NONROAD) | 26,958 | 0 | 21,915 | 90 |
| `sample-runspec` | 10,258 | 0 | 8,092 | 17 |

Two things in that table matter more than the pass. **The tie count is zero in
every one**, so the walk order is total on every capture and not just on this
one — which is the check to run, because a tie makes "the preceding row" a
sort-order question (12 of 44,513 `(vehID, dayID, keyOnTime)` triples do tie in
`SampleVehicleTripByHour`, broken by the emission order). And **the exception
count varies** — 17, 20, 90, 107 — so 107 is a property of this capture, not a
constant of the model, and a fixture that hard-codes it is fitting one snapshot.

Two things follow, and the second is the more useful:

* **The base case absorbs the exceptions.** 107 chained trips name a predecessor
  the relation does not contain. They take the same `coldSoakTankTemperature`
  arm a first-of-day trip takes, so a lag-1 self-read plus one `ifelse` covers
  every row — no contracted range, no metaparameter read off the data, none of
  the two costs F28's control records.
* **Attributing a blocker to the wrong finding is worse than not attributing
  it.** The remaining obstacle to TTG-2/3/4 is real and is a different shape
  entirely: a relation whose row count is a function of the data (1 to 22
  segments per trip), and, in TTG-4b, an output count that depends on the
  arithmetic itself — the soak stops at the first minute the temperature falls
  below its threshold, and that minute and all later ones are not emitted. That
  is F5 and F14 — both since retired, and neither was the reason the shape works
  — which §22 and §31 solve with a rectangular grid, a mask and a global rank.
  Priced: a 37,216 × 22 grid for TTG-2, and about 45 million cells to recover
  TTG-4b's 182,532 rows. **A cost, not a limitation** — and a document that had
  said so would have described a slice someone could schedule, where "blocked by
  F28" described one nobody could.

---

## 35. A generator that writes an INPUT column has no fixture **[Phase 5, 532 rows]**

`MeteorologyGenerator` is the first rung in this port whose product is not a
`MOVESOutput` row. It writes `ZoneMonthHour.heatIndex`,
`ZoneMonthHour.specificHumidity` and `ZoneMonthHour.molWaterFraction` back into
the execution database, before any calculator runs, and nine already-merged
fixtures read at least one of the three off disk. That one structural difference
decided everything about where the slice landed, and the five sections below are
what it taught.

**Where 532 comes from**, since the heading claims it: it is the number of
`ZoneMonthHour` rows in the whole snapshot corpus on which MOVES actually ran
this generator — 21 snapshots' worth, three written columns each, 1,596 cells.
Nineteen of the 21 carry the same 24-row (zone 261610, month 8) block, so the
distinct evidence is smaller than 532 suggests; §35.2 says what the other two
buy. It is not a `MOVESOutput` row count and is not comparable to the row counts
in §§29–34's headings, which is precisely the point of this section.

### 35.1 `fixtures/` is a `MOVESOutput` harness; do not put a generator in it

The default for a new slice is a new document under `fixtures/`, and for this
one that is not available. Two things in the harness say so, and both are worth
naming because neither is obvious from reading a fixture:

* `run-tests.sh`'s fixture stage requires `$SNAPSHOTS/<basename>` to be a
  snapshot directory, so a fixture's NAME is a snapshot's name. Every snapshot
  whose meteorology is populated either already has a fixture or would need a
  full `MOVESOutput` port to acquire one.
* `compare-output.py` reads `db__<output database>__movesoutput.parquet` and
  compares `value_columns = ["emissionQuant"]`. A document emitting
  `ZoneMonthHour` columns has nothing that comparator can look at, so it would
  fail, and passing the stage would then require a `[shortfall]` record —
  which is a promise to close a gap, not a way to describe a document that is
  complete.

**The rule: match the document's home to what it produces, not to how important
it is.** A generator whose product is an execution-database column belongs in
`components/`, checked by its own inline assertions against captured MOVES
intermediates, which is the shape `components/tank_temperature.esm` established
for `TankTemperatureGenerator` TTG-1 and which
`components/meteorology.esm` follows. The row-by-row half — the part
`compare-output.py` does for a fixture — moves into the specification's §6.5
reproduction and its oracle, where it can key on whatever the table's key
actually is.

### 35.2 A generator's claim has two halves, and the second is *when it runs*

A calculator's fixture is checked by comparing rows. A generator's port is
checked by comparing rows **and** by establishing which runs produce them at
all: `MeteorologyGenerator` subscribes to processes 1, 2, 9, 10, 90 and 91, and
a run selecting none of them leaves the three columns unwritten.

That second half is not decoration. Of the 40 snapshots carrying the columns,
**19 are unwritten** — the twelve NONROAD sectors, the three evaporative slices
and the four crankcase start/extended-idle ones. A port that verified only the
21 populated snapshots would have no way to tell "MOVES did not run the
generator here" from "MOVES ran it and got zero", and the second reading is how
a NONROAD run's zeroed humidity becomes a bug report.

So `run-meteorology-oracle.sh` is handed the snapshots **directory** rather than
one snapshot — the only oracle in the repository that is — and asserts the
predicate

> populated ⇔ ONROAD **and** the run's processes meet {1, 2, 9, 10, 90, 91}

on all 40. **The rule: when a stage's OUTPUT is conditional, assert the
condition on the snapshots that fail it as well as on the ones that pass.** The
negative cases are the evidence; without them the subscription list is a comment.

That sweep also paid for itself in a way a single-snapshot oracle could not.
Nineteen of the 21 populated snapshots carry a byte-identical 24-row block, so a
document checked against one of them is checked against nineteen. The two that
differ are where the coverage is: `expand-month` holds the corpus's only
sub-freezing row, which is the only place the Goff–Gratch reduced temperature is
exercised on the other side of the ice point, and `expand-counties` holds the
only populated multi-county geography, which is the only place the county join's
`on` clause can be wrong and be seen.

### 35.3 Decide a fidelity question by measuring both candidates, not by reading the source language

`moves.rs`'s port carries an explicit open question: MOVES writes the
Fahrenheit-to-Kelvin slope as the SQL literal `(5/9)`, and MariaDB evaluates `/`
between integers as DECIMAL division rounded to `div_precision_increment`
places — 0.5556 — so the executed slope might not be the exact ratio. The
upstream note chose the exact ratio, put the difference at "roughly 8e-6
relative", called it "far inside any generator tolerance budget", and said a
canonical-capture comparison was the place to revisit it.

Every part of that except the choice is wrong, and the way to find out was to
run both:

| slope | worst relative error over the corpus's 1,596 cells |
|---|---|
| exact `5.0/9.0` | **2.391e−08** |
| MariaDB decimal `0.5556` | **1.379e−04** |

The two differ by 8.0e−05 on the slope itself, which is 5.8e−03 on `TK`'s offset
from the ice point, and the saturation exponent multiplies that by 10.8 and
exponentiates it. The result is **seven times outside** `tolerance.toml`'s
per-cell 2e−5 — not inside any budget this repository applies — and four orders
away from the right answer. Substituting it turns **20 of
`components/meteorology.esm`'s 42 assertions** red.

**The rule: a fidelity question about a host language's evaluation semantics is
settled by evaluating both candidates against the reference, and the answer is
recorded as a measurement.** Reasoning about MariaDB's `div_precision_increment`
cannot distinguish the two; one sweep of the corpus does, in under two seconds,
and leaves a number a later reader can re-derive. The corollary is the part worth
carrying: the upstream estimate of the *size* of the difference was off by an
order of magnitude in the direction that made it look harmless, which is the
direction such estimates usually err.

### 35.4 Say which assertions face the reference and which face the port

`components/meteorology.esm` has 42 assertions and they are not all the same
kind of evidence. Thirty face the snapshot's own captured columns. Six pin
`TK` / `PH2O` / `PV`, which MOVES materialises as temporary tables and drops, so
the snapshot does not carry them and those six face **this port only**. Six more
pin the county default-fill branches, and no county in the corpus reaches them:
all 22,815 `County` rows in all 40 snapshots record a positive
`barometricPressure` and an altitude of `H` or `L`, so those six face **the SQL
as ported**.

Both groups are worth keeping — the intermediates are where the chain can be
perturbed one stage at a time, and the fill branches are where the two `UPDATE
County` statements' ORDER is written down. What is not acceptable is letting
them read as reference-checked. Each one's test `description` says which it is,
in the test rather than only in the specification, because a reader who reaches
the assertions first is the reader most likely to draw the wrong conclusion from
them. §23's rule is the neighbouring one: measure whether a document can SEE a
stage before claiming it checks it.

### 35.5 An oracle over a SHARED corpus asserts a floor, not a count

`run-meteorology-oracle.sh` is the first oracle here whose input is the whole
snapshot directory rather than one snapshot, and that made it the first to
notice that the directory is **shared mutable state**. It read 39 snapshots when
it was written and 40 the next time the suite ran, because a parallel rung
captured a new RunSpec into `../moves.rs/characterization/snapshots` while this
one was being verified.

The oracle asserted `cells == 1596` — the exact cell count — for a good reason:
without it, a snapshot whose tables stopped being readable would be silently
skipped and the run would pass on whatever was left. But an equality also makes
a sibling's capture into this oracle's failure, and a red suite whose cause is
another agent's correct work is worse than no assertion: the next person's fix
is to delete it.

**The rule: over shared, growing state, assert the invariant that only breaks in
the direction you care about.** Here that is `cells >= 1596`. Silent skipping can
only make the count go DOWN, so the floor keeps the whole of the property the
equality had; growth is allowed, and the per-cell error, the key-set equality and
the scheduling predicate are all per-snapshot invariants that a new snapshot has
to satisfy on its own terms anyway. The count that IS pinned exactly is the one
that is a property of the model rather than of the corpus: **0 missing, 0 extra
keys**, per snapshot.

The corollary for the prose is the same one §11 makes about shapes: a document
that writes a corpus-wide count writes down the date it was true. This
specification says "40 as this is written, and the corpus grows", which is a
claim that stays true; "the 39 snapshots" was a claim that was false within the
hour.

---

## 36. A fixed-decimal capture is part of the reference, and it is not always absorbable **[Phase 5, 14,036 rows]**

> **The instance in this section is HISTORY; the rule is not.** The corpus was
> recaptured to `moves-snapshot/v2`, which stores the shortest decimal that
> round-trips the f64, and every concession measured below was retired — see
> **§41**. Read §36 for how to attribute a residual to a capture, and §41 for
> what to do when the capture is then fixed. Numbers below describe
> `moves-snapshot/v1` and are kept because they are the measurement that
> justified the fix.

`nr-airtoxics-lawn-garden-county` is the last two NONROAD calculators —
`NRHCSpeciationCalculator` and `NRAirToxicsCalculator` — and the first slice in
this port whose limiting factor is neither the format, nor the toolchain, nor
the arithmetic, but **how the snapshot was written to disk**. Every rule in
§1–§35 held. What is new is a class of obstacle the previous ten rungs never
met, and a third thing to write in `tolerance.toml` beside a tolerance and a
shortfall.

### 36.1 Measure the capture's precision before attributing a residual

Under `moves-snapshot/v1`, `crates/moves-snapshot/src/format.rs:17` was
`pub const FLOAT_DECIMALS: u32 = 12;` and every table's `.meta.json` carried
`"float_decimals": 12`. So a captured float was a decimal string with twelve
places after the point, and it kept

```
12 + floor(log10|v|) + 1     significant digits
```

— six for a value of 10⁻¹, **one** for a value of 10⁻¹², none at all below
5 × 10⁻¹³. That was not a rounding preference: it was the resolution of the
only copy of the reference this repository had. **Read the encoding; never
assume it.** A v2 sidecar carries `float_encoding` and OMITS `float_decimals`
entirely, precisely so that a consumer still reading the old field fails
instead of deriving a floor the data no longer supports.

**Measured over the whole corpus**, every `MOVESOutput` table under
`characterization/snapshots`: **136,552 cells, of which 7,308 (5.35 %) are
stored as an exact zero and 1,326 (0.97 %) are non-zero with fewer than six
significant digits.** The distribution is the point. **1,324 of those 1,326
are in this one snapshot** — the only one in the corpus whose chain produces
trace species. The twelve fixtures before it met a capture that lost nothing
and could reasonably treat storage as ideal; this one produces mercury at
10⁻¹² g and dioxin at 10⁻¹³, and the capture is then the largest term in the
error budget.

The corollary for the next slice: **this will recur wherever a chain multiplies
a real inventory by a ratio of 10⁻⁶ or smaller**, which is every remaining
air-toxics, metal, dioxin and PAH rung, and it will not recur anywhere else.
One sweep answers it before a day is spent on the arithmetic.

### 36.2 An OUTPUT quantisation is absorbable; an INPUT one is not

They are two different failures and only the first can be answered by how the
comparison is read.

**Output.** The stored value is a rounding of the true one, so half a quantum —
5 × 10⁻¹³ absolute, a number read off the capture rather than fitted — is the
reference's own resolution. `compare-output.py` already concedes exactly this
for an expected zero ("when only the expectation is zero, fall back to
absolute, since there is no scale to be relative to"); the general form is the
same concession one step earlier. Measured on this fixture: 2,629 cells of the
27 compared pollutants are storage-limited, 283 of them exceed the 2 × 10⁻⁵
gate on their raw relative error, and allowing the half-quantum takes the worst
of all 2,629 to **8.655 × 10⁻⁶** — inside the unchanged gate, with the per-
pollutant worst excess running 5.683 × 10⁻⁶ to 7.712 × 10⁻⁶.

**Input.** Nothing about how the answer is read can recover a coefficient the
capture destroyed. Measured over the nine tables this slice reads:

| table | rows | rows stored with < 6 significant digits |
|---|---:|---:|
| `nrDioxinEmissionRate` | 316 | **316** |
| `nrMethaneTHCRatio`, `nrHCSpeciation`, `nrATRatio`, `nrPAHGasRatio`, `nrPAHParticleRatio`, `nrMetalEmissionRate`, `nrEmissionRate`, `nrEngTechFraction` | 66,875 | **0** |

One table of nine. Its two gasoline rates are `0.000000001105` and
`0.000000000019` — four significant figures and **two** — against the MySQL
`double` MOVES read.

**The way to prove it is the capture and not the port: fit the coefficient the
reference must have used, and show it is inside half a stored quantum.**
1.1045021 × 10⁻⁹ against a stored 1.105 × 10⁻⁹ is 0.996 half-quanta;
1.9434497 × 10⁻¹¹ against 1.9 × 10⁻¹¹ is 0.869. Both are inside, so the
captured value is a correct rounding of the fitted one and there is no
arithmetic left to find. Do the fit on the cells the output stores best, and
assert it in the oracle so the claim is re-checked every run rather than
asserted once.

**And the fits were later checked against the real numbers, which is the only
reason to trust the method.** `moves-snapshot/v2` records the two rates as
1.1045 × 10⁻⁹ and 1.94345 × 10⁻¹¹. The fits were off by 1.9 × 10⁻⁶ and
1.5 × 10⁻⁷ relative — two orders inside the `[cell] rel` they were used to
justify. A fitted coefficient is a hypothesis; this one turned out right, and
it is worth saying that it was checkable at all only because the capture was
fixed.

### 36.3 A declared SCOPE is a third thing, and it needs its own vocabulary

Three ways a fixture can fall short of "every cell inside the gate", and they
are not interchangeable:

| | what it says | where it lives | what it must carry |
|---|---|---|---|
| a **tolerance** | the port and the reference differ by this much | `[cell]`, `[default]` | a measurement of the drift |
| a **shortfall** | the fixture does not EMIT these rows yet | `[shortfall]` | the row and key counts, and it is a promise to close |
| a **scope** | the fixture emits these rows correctly and the SNAPSHOT cannot check them | `[fixtures."…".scope]` | the reason, mandatory, with the measurement |

Writing the third as one of the first two is what makes both of them
untrustworthy. A widened `[cell] rel` would have hidden every real error in the
27 other pollutants in order to admit two; a `[shortfall]` would have claimed
the rows were missing when they are emitted with the right keys and the right
arithmetic.

Three properties keep a scope honest, and all three are falsified in
`compare-output.py --self-test`: an error in a pollutant that is **not**
excluded still fails; the excluded pollutant is held out of **both** sides, so
it cannot reappear as a missing key; and a scope **with no `why` is refused**.

**And the exclusion is on the COMPARISON, never on the document.** The fixture
computes all 29 pollutant-processes and emits all 14,036 rows; the two dioxin
blocks are as correct as any implementation reading this capture can make them,
and the comparator says out loud that it is not looking at them. A fixture that
had instead stopped emitting them would have hidden the fact that they are
computable at all.

**Prefer the scope that checks MORE cells, and measure the alternative rather
than asserting it.** Two ways to make this fixture green were measured:
excluding pollutants 131 and 142 alone leaves 283 cells over the gate, so
making it green that way needs nine pollutants excluded — 4,356 of 14,036 rows
held out, 9,680 compared, worst cell 9.417 × 10⁻⁶. Excluding two and comparing
the rest at the capture's own resolution holds out 968 rows, compares 13,068,
and reaches the *same* worst cell of 9.417 × 10⁻⁶. Same gate, same worst error,
3,388 more cells checked. Both sets of numbers are in `tolerance.toml` so the
decision can be revisited without re-deriving them.

**Two numbers, and they must stay two numbers.** Folding the storage floor into
the reported worst cell makes a rung's headline figure an excess-over-quantum
ratio wearing the label "worst relative error", and a reader diffing oracle
output across rungs cannot see it. `compare-output.py` reports the true
relative error *and*, on its own line, the worst excess over the quantum, with
the second saying that it is the number the gate was applied to. On this
fixture they are 4.479 × 10⁻¹ and 9.417 × 10⁻⁶, and the first is worth seeing.

### 36.4 A lookup resolved once per PARENT is not the same as once per CHILD

The other thing this rung cost, and it has nothing to do with precision.

`nr-logging-county` resolves `nremissionrate`'s three-level SCC fallback chain
**once per equipment point** and then reads every technology's rate at that
level. `nonroad_loader.rs:436-451` resolves it **once per (technology,
pollutant slot)**: a specific SCC's rate rows need not cover every technology
its own tech mix names, and the ones it misses are served by the engine-family
root. Retargeted onto this sector, the point-level version emits **exactly the
right 14,036-row key set** and is wrong by up to a factor of **6.9** on five of
the 31 SCCs.

Two rules, and the second is the transferable one.

**When the reference resolves a fallback ladder inside a loop, the ladder's
result carries that loop's key.** A retarget cannot see this: the two spellings
agree on any fixture whose specific SCCs happen to cover their whole mix, which
`nr-logging-county`'s three do. §27.3 makes a retarget the first move on a new
rung; this is what a retarget audit looks like when it finds something, and the
tell was that the failure was **large, systematic and confined to five keys**
rather than distributed like a rounding error.

**A three-dimensional effective key cannot be a join key, so invert the
ladder.** §27.1's rule — a `join.on` key column must be 1-D — means
`techRate_effectiveSCC[point, pollutant-process, technology]` is not
expressible at all. The remedy is not to flatten it: it is to write the three
lookups and a **precedence between their results**, which is
`lib/adjustments.esm`'s `exact_else_wildcard` nested twice. Three aggregates
and one selection, none of them 2-D, and the ladder reads as what it is.

The same inversion has a limit, and this slice met it too: the horse-power
CATEGORY every speciation table keys on is a function of *both* the equipment
point and the technology, and it is a genuine join key rather than a value.
There the answer is §22's flat relation — one axis of (technology × category)
with the category as a 1-D column on it — and then a second level,
(technology × category × fuel subtype), because §32.3's per-formulation
collapse has to happen after the chain is formed and not before. **Flatten when
the thing is a key; invert when it is a value.**

**And keep the flat relation off the hot node.** The multiplier that all of
this produces is a VALUE at (point, technology, pollutant-process), not a key,
so it is read back onto those three axes once — 313,200 cells — rather than
joined inside the roll-up, which already contracts 16 million leaves. Measured:
joined inside the roll-up the document had not finished after eight minutes;
read back onto the roll-up's own axes first, the whole document runs in
**70 seconds**. That is §11.1's rule again, at the place where
a flat relation stops being useful.

### 36.5 Two smaller things, both measured

**"The first containing bin" is a strict lower bound when the bins tile.**
`nonroad_loader.rs` takes the first `(SCC, hpMin, hpMax)` bin containing
`hpAvg` under `lo <= hp <= hi`; an aggregate has no "first", and `hpMin <=
hpAvg` admits two bins wherever `hpAvg` sits on a boundary — 2260004071's 3.0
hp is in both (1, 3) and (3, 6) of 2260000000, and summing both makes
`tech_fractionTotal` 2 and that SCC's emissions 1.24 to 1.43× the reference's.
Because the bins tile contiguously from 0 and every `hpAvg` is positive,
`hpMin < hpAvg <= hpMax` selects exactly the reference's bin. Measured over all
108 points at all three chain levels: **0 differences**. Check the tiling
rather than assuming it, and apply the change to **every** aggregate that reads
the same bin — the presence tests and the model-year resolution as well as the
value, which is four sites here and where the first attempt got it wrong.

**The tenth instance of the plausible-wrong-value failure, and the third where
a clamp or a mask is the thing that fails.** Eleven of this run's 108 equipment
points carry a base-year population of exactly 0, and `prccty.f` skips them.
Here that skip is a DIVISION: `agedist.f`'s `totpop/baspop` is `0/0`, and
`cohort_isPopulated` cannot suppress the NaN because `0 × NaN` is NaN (§19.4a,
§29.2). It surfaced as seven SCCs emitting NaN on model year 2020 — the seven
whose SCC is shared between a populated point and an unpopulated one — while
every other cell was right. **Write the reference's `continue` as a guard on
the VALUE at the column that can be zero**, never as a factor at the point of
use, and expect the symptom to appear somewhere that looks unrelated to the
point that caused it.

**A `(pollutant-process, technology)` pair with no coefficient row takes the
IDENTITY, not zero.** `nrdeterioration` has no 9901 row anywhere, and the
inherited spelling multiplied the deterioration factor by a presence flag — so
fuel consumption, and with it every metal and dioxin derived from it, came out
as exactly 0 while THC and PM10 were right. The reference's `det.get(...)`
returns `None` and leaves the coefficient at 0, which makes the factor 1. This
is §3's "an unmatched row contributes the additive identity" meeting a case
where the identity of the operation is 1 rather than 0, and a fixture whose
selected pollutants all have coefficient rows cannot tell the two apart.

---

## 37. Retargeting a fixture from INGEST to COMPUTE is checked by that fixture only where the branch is not an identity **[Phase 5, 9 fixtures, 7 byte-identical]**

`docs/meteorology-generator.md` §8.2 rewired the nine fixtures that named
`ZoneMonthHour.heatIndex`, `.specificHumidity` or `.molWaterFraction` in a
`float_columns` list so that they DERIVE those columns from
`ZoneMonthHour.temperature`, `ZoneMonthHour.relHumidity` and
`County.barometricPressure` instead of reading MOVES's answers back off the
reference. Eight were retargeted, one turned out to have nothing to retarget,
and **seven of the nine emitted output that was byte-identical afterwards.**

**Where the heading's numbers come from**, since it claims them: nine fixtures
named at least one of the three columns; eight bound one to a variable and now
compute it; `nr-logging-county` bound none (§37.1). Comparing each fixture's
emitted relation before and after, `cmp` on the CSV: `mixed-onroad` (250 rows),
`process-airtoxics` (1,288), `process-brakewear` (750), `process-pm-exhaust`
(1,456), `process-refueling` (336), `process-tirewear` (750) and
`nr-logging-county` (144) are identical; `process-crankcase-running` (378 of
1,368 cells) and `process-nox-speciation` (832 of 872) moved.

### 37.1 Measure what a document BINDS, not what it DECLARES

`docs/meteorology-generator.md` opened by saying nine fixtures "read at least
one of those three columns off disk", and the list was assembled from the nine
`float_columns` lists. It was wrong in two directions at once, and both were
found only by opening the documents:

* **`nr-logging-county` named all three and read none.** Its
  `zonemonthhour` entry projected `heatIndex`, `specificHumidity` and
  `molWaterFraction`; its variables bind `zoneID`, `monthID`, `hourID` and
  `temperature` and nothing else off that table. All three columns are **NULL
  on all 930,816 rows** of that snapshot besides, because it is a NONROAD run
  and the generator never fired. Three dead entries, on a document nobody would
  suspect, in the file whose header already explains at length what it reads.
* **`process-airtoxics` and `process-pm-exhaust` were said to feed the humidity
  pair into the NOx correction.** Neither projects either column; each says so
  in its own source note. Only two fixtures consume them.

**The rule: a `float_columns` entry is a declaration of intent, not evidence of
use. A count of what a corpus "reads" must come from the `update.kind: "data"`
bindings, and a count of what it reads NON-TRIVIALLY must come from the
parquet.** The cheap version of both:

```
grep -o '"file_variable": "<column>"' fixtures/*.esm     # what is bound
python3 -c "...pq.read_table(f).column(c).null_count..."  # whether it is there
```

`tools/check-sources.py` will not catch this: its check 4 fails on a projected
column left OUT of `float_columns`, which is the dangerous direction, and
reports the reverse as a note. That asymmetry is correct — an unread declared
column costs nothing at runtime — but it means the declaration list cannot be
used as an inventory.

### 37.2 A magnitude bound says nothing about a threshold

The retarget's bound was known before it started: the computed columns differ
from the ingested ones by at most **2.391e−08** relative, 840× below
`tolerance.toml`'s per-cell gate. That number is worth exactly nothing where the
column feeds a **clamp**, and across the eight fixtures these three feed five of
them — the air-conditioning activity quadratic's `clamp(0, 1)`, the EV
heat-index suppression at 67.0 °F, the EV temperature quadratic's `max(·, 0)`,
and `bounded_low_then_high` once per humidity column. A clamp does not care how small the error is; it cares whether
the value is on the same side of the boundary.

**The rule: for every threshold the changed value feeds, state the boundary and
the margin, and state the CHANGE in the margin separately from the change in the
value.** `docs/meteorology-generator.md` §8.2.2 is that table. Two things in it
could not have been guessed from the 2.391e−08:

* The tightest margin in the corpus is `mixed-onroad`'s **0.0999985 °F** below
  the EV suppression — and it changes by an **exact zero**, not by 2.4e−08,
  because each of the eight retargeted fixtures' RunSpecs selects an hour below
  78 °F — seven at hour 7 and 59.5 °F, `mixed-onroad` at hour 9 and 66.9 — and
  the heat index below 78 °F IS the temperature. The relevant fact was never the
  size of the error; it was which branch the value lands on.
* The two humidity margins DO move, by 3.28e−08 and 2.59e−08 **of the margin**.
  That is the number a reader needs, and it is not the 2.3e−08 relative change
  in the value; the two agree here only because the margin happens to be the
  same order as the value.

### 37.3 Where the reference stores its own answer, computing it moves you AWAY from the reference

MOVES writes these three columns into the execution database and its own
calculators then read the **stored** value back. Two of the three are stored at
less precision than MOVES computed with — measured over `process-tirewear`'s 24
rows, 19 of 24 stored specific humidities and 21 of 24 stored mole fractions are
exactly the binary32 rounding of the value the formula gives. The third,
`heatIndex`, is stored at full double precision. So:

| column | computed vs stored | what retargeting costs |
|---|---|---|
| `heatIndex` | ≤ 7.93e−15 over 24 rows, 17 bit-identical | nothing |
| `specificHumidity` | 2.2985e−08 | the port moves 2.3e−08 further from MOVES |
| `molWaterFraction` | 2.2619e−08 | the same |

**The rule: when a port stops reading a reference column and starts computing
it, say which direction the comparison moves and why, before someone reads the
third decimal of a worst-cell figure as a regression.** Measured here:
`process-nox-speciation`'s worst cell went 9.482e−06 → 9.485e−06 against a
2e−05 gate, and its worst per-pollutant sum went 4.957e−07 → **4.883e−07**, so
one figure got worse and the other better. Neither is a signal.

The corollary for assertions: the fourteen inline assertions in the two moved
fixtures that had been transcribed from the stored column KEPT their `expected`
values and gained a per-assertion `rel: 1e-7` — four times the worse measured
gap, the gate `components/meteorology.esm` asserts the whole generator at, and
200× tighter than `tolerance.toml`. Retargeting them to the computed number
would have been easier and would have turned fourteen checks against MOVES into
fourteen checks against ourselves (§35.4). Widening `tolerance.toml` would have
been easier still and would have hidden the direction of §37.3 from every
fixture at once.

### 37.4 A retarget that changes no byte is not verified by the fixture, and the fixture must say so

This is §23 applied to a new shape, and the shape is worth naming because the
usual instinct is the opposite one: seven byte-identical outputs after a
nine-document change reads as *reassurance*. It is the reverse. **Every one of
those seven would pass with `heat_index`'s regression arm replaced by the
constant 0**, because no fixture's run hour reaches it.

So each retargeted document says, in the description of the variable that
changed, which of the two cases it is in — and the two that moved carry the
cell-by-cell account of what moved and why, because the other half of §23's rule
is that a change which DOES move bytes has to be explained rather than accepted.
For `process-crankcase-running` that account has to reach the level of "38 of
the 80 diesel crankcase rows are exactly 0, and a factor cannot move a zero"
before the 378 is a number and not a mystery.

**And the rule that follows for the next rung: retargeting is a change of
INPUTS, so verify it where the inputs vary.** The eight retargeted fixtures span
two heat indices between them, both below the branch. The 21 populated
snapshots `components/meteorology.esm` and `run-meteorology-oracle.sh` cover
span both arms and a sub-freezing temperature. The fixtures are where the
retarget is *integrated*; they are not where it is *checked*.


---

## 38. A fidelity question is settled by where the WRONG answer falls, and some cannot be settled at all **[Phase 5, 97 rows, 194 cells]**

§35.3 established that a fidelity question about a host language's evaluation
semantics is decided by evaluating both candidates against the reference rather
than by reasoning about the host. `FuelEffectsGenerator` is the second slice to
carry two such questions at once, and it answers one of them and — this is the
part that is new — establishes that the other **cannot be answered here**. The
five sections below are what the pair taught.

### 38.1 Measuring both candidates is necessary; saying WHERE the measurement can live is the other half

`FuelFormulation`'s seventeen property columns are MariaDB `FLOAT`, 32-bit, and
MOVES evaluates a `fuelEffectRatioExpression` against them in `DOUBLE`. So the
value that enters the arithmetic is a binary32 widened. The snapshot capture,
though, writes the **decimal** — `23.140000000000` where MOVES held
23.139999389648438 — which makes "what is a property value?" a real choice with
two plausible answers. Measured over the corpus's 194 compared cells:

| a property value is taken to be | worst relative error |
|---|---|
| the `FLOAT` widened | **0.000e+00** (bit-identical; **1.608e−14** under `moves-snapshot/v1`) |
| the capture's decimal read as a double | **7.059e−08** |

That looks like §35.3's table and it is not the same situation, because of where
the wrong answer lands. Meteorology's `0.5556` slope was 1.379e−04 — **seven
times outside** `tolerance.toml`'s per-cell `rel = 2e-5`, so any fixture would
have caught it. 7.059e−08 is **280 times inside** that gate. Every fixture in
this repository would have passed with the wrong promotion and reported nothing.

**The rule: after measuring both candidates, compare the loser against the
FIXTURE GATE, and if it falls inside, say so and put the assertion somewhere
that can see it.** Here that is `components/fuel_effects.esm` at `rel 1e-15` and
`run-fuel-effects-oracle.sh` at `1e-13`, and both say in words that they are the
only things in the port that decide it. A fidelity choice whose wrong answer is
inside the tolerance of every check you own is not a choice you have made; it is
a coin you have not looked at.

**And DO NOT STATE THE SEPARATION AS A RATIO.** The oracle's gate was
`worst[double] > 1e3 x worst[float]`, which was a real test while the winner
left a 1.608e−14 residual. The recapture made the winner EXACT, and `> 1e3 x 0`
is satisfied by any positive number at all: a gate that reads as a comparison
and tests nothing. Both ends are now asserted absolutely — the loser must miss
by more than 1e−9, the winner must land inside 1e−13. A separation expressed as
a ratio between two measurements silently dies the day one of them reaches
zero, which is the day the port gets it exactly right.

The corollary is the uncomfortable one. `tolerance.toml`'s 2e-5 is right for a
`real*4` oracle comparison and it is three to four orders too loose to
discriminate a `DOUBLE`-versus-`FLOAT` reading of an input column. Loosening a
gate to fit a residual is a recorded shortfall; **evaluating a question at a
gate that cannot resolve it is the same mistake with no record at all.**

### 38.2 A question the corpus cannot ask is answered by asserting the absence

`../moves.rs` left an explicit open question next to the `(5/9)` one: MariaDB
rounds an integer/integer division to `div_precision_increment` decimal places
before promoting to `DOUBLE`, so a `fuelEffectRatioExpression` that divides two
integer **literals** might not divide in IEEE. The upstream note put the corpus
at "58 such expressions, none compared".

The measurement: parsing all 118 distinct expression strings and counting every
`/` node whose two operands are both integer literals gives **0**. The 58 was
the `generalFuelRatio` row count of one snapshot, not a count of divisions. The
only integer denominator anywhere is the `100` in
`least(bioDieselEsterVolume, 20)/100`, whose numerator is a `FLOAT` column and
therefore a `DOUBLE` — which takes the expression out of MariaDB's exact-value
path entirely.

So the two hypotheses are not close on this corpus; they are **bit-identical**,
at 0.000e+00 each (1.608e−14 each under `moves-snapshot/v1`), because nothing
exercises the difference. Two ways to record
that, and only one of them survives contact with a growing corpus:

* *"Not resolvable; we chose IEEE."* — true on the day it is written, and
  indistinguishable a year later from a decision that was made and justified.
* **Assert the absence.** `run-fuel-effects-oracle.sh` asserts
  `int_divisions == 0` **and** that the two candidates' residuals are equal.
  Both are true today. The day a capture adds an expression with such a
  division, the oracle goes red, and the message points at the section that says
  the question is now answerable.

**The rule: when the corpus cannot distinguish two candidates, assert the reason
it cannot, not the conclusion you would draw if it could.** This is the same
polarity as `docs/findings/`'s tripwire (§13) and the same instinct as §35.5's
floor: write the assertion that breaks in the direction where something has
changed. An honest "not resolvable here" that goes red when it becomes
resolvable is worth more than a defensible guess.

### 38.3 An expression corpus's ROW count is not its FORM count, and its SKELETON count is the trap in between

§24 factored `cumTVVCoeffs`'s 2,188 rows into two forms and eighteen coefficient
rows. `generalFuelRatioExpression` is the second instance and it has a middle
term the first did not:

| | count |
|---|---:|
| rows, summed over the corpus | 2,078 |
| distinct rows (all nine columns) | 567 |
| distinct expression **strings** | 118 |
| distinct parse-tree **skeletons** (every literal replaced by `#`) | 72 |
| distinct algebraic **forms** | **6** |

The instinct on meeting 118 strings is to normalise them mechanically — replace
the literals, count the shapes — and 72 comes back. That number *looks* like a
form count and is not one: MOVES writes the same polynomial's terms in different
**orders** in different rows, `…+b·ETOH−c·RVP+d·T90…` here and
`…−c·aromatics−e·T50+b·ETOH…` there, with the same coefficients. Those are one
form. The criteria sulfur form alone accounts for **57 of the 72 skeletons**,
and it is one form.

**The rule: a mechanical normalisation gives an upper bound on the number of
forms, never the number.** The number comes from reading them, and the check
that the reading is a partition rather than a sample is that the per-form row
and string counts **sum to the totals** — 2,078 and 118 exactly, which
`docs/fuel-effects-generator.md` §2.1 prints for that reason.

The count that did NOT move when the corpus grew by two snapshots mid-rung is
the **6**. Rows went 1,744 → 2,078, strings 116 → 118, skeletons 70 → 72, and
the form count stayed where it was — which is the practical argument for
factoring in the first place, and `docs/fuel-effects-generator.md` §7.5 is the
before-and-after table.

The term-order fact is worth keeping for a second reason: it is a live fidelity
question of its own. MOVES sums left to right in the string's order and a
document that sums over an axis does not. The difference is under 1e−15 on the
exponent, inside the measured residual, and unseparable from it — which is the
honest thing to say about it rather than either claiming it is zero or writing
twelve coefficient orderings into a table.

### 38.4 A generator's EXTRA rows are evidence when another table claims them, and slack when it does not

`doGeneralFuelRatio` computes 1,112 rows over the 24 snapshots that ran it.
MOVES keeps **97**. The other 1,015 are not a bug in either direction: the
predictive/complex-model paths this port does not cover —
`copyGeneralFuelRatioToCriteriaRatio` and `doAirToxicsCalculations` — copy them
into `criteriaRatio` and `ATRatio` and delete them from `generalFuelRatio`
before the snapshot is taken.

A port in that position has three ways to write the key-set check and two of
them are worthless:

1. *Drop the extras and assert on the intersection.* Then a port that computed
   one correct row and 1,111 wrong ones passes.
2. *Hard-code the handed-off polProcessIDs.* Then the list is fitted to the
   corpus, and it is fitted by the same person who is checking it.
3. **Require every extra to be claimed, by key, by a table that is not the one
   under test.** For each extra row, `criteriaRatio`, `altCriteriaRatio` or
   `ATRatio` in the *same snapshot* must carry a row with the same
   `(fuelFormulationID, polProcessID)`. Measured: 1,015 of 1,015, and the
   assertion is `unaccounted == 0`.

**The rule: an extra row is evidence only if something outside the comparison
accounts for it.** The third form is falsifiable — a port that invented a row
would have to invent it into a table it does not write — and it costs one join
against tables that are read for their key columns and nothing else.

### 38.5 The execution trace answers the scheduling half directly; do not infer it from an output

§35.2 established that a generator's claim has two halves and the second is
*when it runs*, and `run-meteorology-oracle.sh` decided that half by asking
whether the written columns were populated. That works, and it has a weakness
this rung did not have to accept: a generator that ran and produced nothing
looks exactly like one that did not run.

Every snapshot carries an `execution-trace.json` listing the Java classes MOVES
actually **loaded**. So "did `FuelEffectsGenerator` run here?" has a direct
answer that does not pass through any output table, and using it made the
difference immediately: of the 42 snapshots carrying
`generalFuelRatioExpression`, 24 loaded the class and 18 did not, and **22 of
the 24 that loaded it wrote no `generalFuelRatio` row at all.** Fifteen of those
twenty-two had an empty expression table and so had nothing to compute; the
other **seven computed rows — 51, 51, 45, 99, 173, 173 and 282 of them — every
one of which was handed off** (§38.4). An oracle that read population as "it
ran" would have had twenty-two false negatives, seven of them on snapshots where
the generator did real work, and would then have derived a scheduling predicate
to fit them.

The predicate the trace supports is

> loaded ⇔ ONROAD **and** the run's processes meet {1, 2, 9, 10, 11, 12, 13, 90}

on all 42. And it contradicts the module inventory: `calculator-dag.json`
records **fourteen** `PROCESS` subscriptions for this generator, and the three
the corpus tests in isolation — 16, 17 and 91 — load it in none of the six
snapshots that select one of them alone. Processes 15, 18 and 19 never appear
alone, so they are **untested**, and the specification says that rather than
rounding eight up to eleven.

**The rule: when the reference records what it did, read that; derive it from an
output only when it does not.** And a subscription list is a declaration, not a
measurement — `docs/process-brakewear.md` §8 already said as much about a
*calculator*'s registrations, and this is the generator-side instance of the
same lesson.
## 39. A generator family shares a row, not a spine **[Phase 5, 201,665 + 84 + 168 rows]**

Section 38 is reserved for the `FuelEffectsGenerator` rung, which was in
progress in a sibling worktree while this was written; this section is 39 to
keep the two from colliding, not because 38 is missing.

`StartOperatingModeDistributionGenerator` and
`RatesOperatingModeDistributionGenerator` are the second and third generator
rungs, after `MeteorologyGenerator`, and the first pair to be ported together.
They were briefed as one family with a shared spine. They are not, and the four
subsections below are what came of measuring that instead of inheriting it.

**Where the row counts come from**, since the heading claims them: 201,665 is
every `StartOpMode` row in the corpus — the per-trip soak classification, the
generator's own captured intermediate; 84 is every `StartOpModeDistribution`
row; 168 is every `RatesOpModeDistribution` row at `avgSpeedBinID` 0, which is
the partition these two generators own. None is a `MOVESOutput` count and none
is comparable to §§29–34's. All three were 262,442 / 124 / 300 before the
`<day key=> -> <day id=>` correction halved every day-keyed table in 28 of the
42 snapshots (§42).

### 39.1 Test the family hypothesis before you factor for it

The brief for this rung proposed that the five operating-mode-distribution
generators "share one spine and differ only at the edges", and that the
compositional-authoring rule therefore called for one `lib/` spine plus thin
per-variant components. Measured against the pinned MOVES 5.0.1 source, the
proposition is false, and it is false in a way that would have produced a
plausible wrong file:

| generator | what it actually is |
|---|---|
| `RatesOperatingModeDistributionGenerator` | a cross product of hotelling op modes with `runSpecHourDay`, every fraction the literal 1 |
| `StartOperatingModeDistributionGenerator` | a soak-time histogram over `SampleVehicleTrip`, divided by a per-cell start count |
| `AverageSpeedOperatingModeDistributionGenerator` | drive-schedule bracketing over average speed bins |
| `Link...`, `MesoscaleLookup...` | project- and mesoscale-domain rewrites of the second-by-second VSP pipeline |

**Not one arithmetic expression is common to any two of them.** What is common
is the shape of the row they all write into `RatesOpModeDistribution`: road type
1, `avgSpeedBinID` 0, `avgBinSpeed` 0, and for the degenerate distributions a
fraction of exactly 1. So `lib/operating_mode.esm` holds six constants and four
small predicates and the two components share nothing else — which is the
correct amount of sharing, and is a quarter of what a spine would have been.

**The rule: a shared OUTPUT is evidence of a shared interface, not of shared
logic, and the two are factored differently.** The check that settles it is
cheap — read the live SQL of each variant and ask whether any expression
appears twice — and the cost of skipping it is a `lib/` file that forces two
unrelated computations through one abstraction, which is worse than either
written plainly. This is §6's rule with its converse attached: reused shapes go
in `lib/`, and shapes that are not reused do not, however similar the modules
around them look.

The sharing that IS real is worth naming precisely rather than by family
resemblance, because that is what distinguishes it from the hypothesis:
`off_network_road_type` is written by six separate `INSERT` statements across
the two modules, `off_network_avg_speed_bin` by the same six,
`degenerate_op_mode_fraction` by five, `hotelling_source_type` by four and
`extended_idle_op_mode` by three. A literal in six places is §6's problem
whatever the modules look like.

### 39.2 Evaluate BOTH candidates, because the answer is not a property of MariaDB

§35.3 established that a fidelity question about a host language's evaluation
semantics is settled by evaluating both candidates against the reference. That
section's example — MOVES's Fahrenheit slope `(5/9)` — came out on the side of
exact arithmetic, and the natural generalization is "MOVES computes exactly".

**This rung is the same question with the opposite answer, and that is why the
rule is stated as a procedure rather than as a fact.**

`StartOperatingModeDistributionGenerator` step 300 writes
`COUNT(opModeID)/starts`. Both operands are MariaDB `BIGINT`, so `/` is
exact-value division whose scale is the dividend's plus
`div_precision_increment` — 4 by default, which MOVES does not change.
`moves.rs`'s port returns the exact `f64` ratio and defers the question, sizing
the divergence at "up to 5 × 10⁻⁵ … still untested". Measured over the 124
`StartOpModeDistribution` rows in the corpus:

| quotient | bit-exact rows | worst relative error |
|---|---:|---|
| DECIMAL to 4 places | **124 of 124** | **0** |
| exact IEEE ratio | 15 of 124 | **5.767 × 10⁻³** |

The 15 the exact ratio gets right are those whose value terminates at four
decimals anyway. 107 of 124 fall outside `tolerance.toml`'s 2 × 10⁻⁵ gate.

Two data points now, opposite answers, both settled in seconds by a sweep of
the corpus. **The rule stands as §35.3 wrote it and the corollary is added:
neither answer generalizes to the next expression.** The property being
measured is not "does MOVES compute exactly" but "what are the SQL types of
this expression's operands" — `(5/9)` in the meteorology SQL is written inside
a `FLOAT` expression chain and `COUNT()/COUNT()` is not — and that is a
per-expression fact.

### 39.3 A generator's scheduling predicate can turn on something other than the process

§35.2 established that a generator's claim has two halves and the second is
*which runs produce rows*, asserted on the snapshots that fail it as well as
those that pass. `MeteorologyGenerator`'s predicate is a process list, and the
obvious generalization is that a generator's predicate is its subscription.

`RatesOperatingModeDistributionGenerator` is the counterexample, and the corpus
contains six snapshots that make the difference visible. It subscribes to
processes 1, 90 and 91, and it is class-loaded in **30 of the 42** snapshots.
All four of its live `INSERT` statements are pinned to **source type 62** — the
only hotelling source type — through `sourceTypePolProcess` for the first of
each pair and `runSpecSourceType` for the second. `expand-counties`,
`expand-day`, `expand-fueltype-diesel`, `expand-month`, `process-refueling` and
`sample-runspec` all select Extended Idle for source type 21 alone: MOVES loads
the generator, runs it, and it writes nothing. The predicate that holds on all
40 is

> a hotelling row exists ⇔ ONROAD ∧ (process 90 ∨ 91 selected) ∧ 62 ∈
> `runSpecSourceType`

and the one written on the subscription alone calls six correct snapshots
failures. The corpus grew from 40 snapshots to 42 while this rung was in
progress, and the predicate held on both newcomers unchanged -- both are ONROAD,
both class-load the generator for Running Exhaust, both emit nothing. That is
§35.5's floor-not-equality design paying for itself the first time it was
tested.

**The rule: derive the scheduling predicate from the WHERE clauses of the
statements that emit, not from `subscribeToMe`.** A subscription says when the
generator is invoked; the emitting statement says when the invocation produces
anything, and it is the second that a snapshot can disagree with. The same
distinction under a different name is the one the calculator track met at
`nr-pleasure-craft-state`, and it is the one `docs/omd-generator-reachability.md`
had to apply on the other side to decide which of this family were portable at
all: **class-loaded in 30 snapshots, emitting in 5.**

### 39.4 When two modules write one table, the port must name the partition

`RatesOpModeDistribution` is written by three generators — the two ported here
and `AverageSpeedOperatingModeDistributionGenerator`, which
`docs/process-tirewear.md` already covers. An oracle that compared the whole
table would fail on `process-tirewear`'s 32 rows and would have no honest way
to describe why.

The partition is `avgSpeedBinID`: both generators here write bin 0 and only bin
0, because hotelling and starts both happen at rest, and
`AverageSpeedOperatingModeDistributionGenerator` writes bins 1–16 because that
is what it is for. `run-omd-oracle.sh` restricts to bin 0 and says so; the
component asserts `avgSpeedBinID = 0` even though it is a literal in the SQL and
asserting a literal proves little, precisely because the oracle's correctness
rests on it.

**The rule: a restriction that makes an oracle's comparison meaningful is part
of the claim and is asserted, not merely applied.** The failure mode it guards
against is specific — a future MOVES that wrote a hotelling row in a non-zero
bin would be silently dropped by the restriction rather than reported — so the
oracle also asserts the row-count floor, which such a change would break. A
filter with no assertion behind it is a way of not looking.

---

## 40. A chain that SUMS is a second pass, and MOVES's own chain table does not declare it **[Phase 5 continued, 5,534 rows, calculators 19 of 19]**

`chain-so2-co2e-mechanism` is the last three unported calculators —
`SO2Calculator`, `CO2AERunningStartExtendedIdleCalculator` and
`TOGSpeciationCalculator` — and it is the first slice in this port where the
**shape of the chain** changed rather than its depth. §32 reached a chain three
levels deep; every level was a MULTIPLICATION. Three of this run's twenty-six
pollutant-processes are SUMS, and that is not a deeper chain, it is a different
one.

Everything in §1–§39 held. The six sections below are what this rung added.

### 40.1 A summed pollutant is not a chain step at any depth, so it needs its own pass

```
TOG       (86) = NMOG + methane                          hcspeciation.rs:767
CO2e      (98) = 1×CO2 + 28×CH4 + 265×N2O                co2ae step 2
NonHAPTOG (88) = max(NMOG − Σ 14 integrated species, 0)   togspeciation.rs
```

Each reads rows the same document has already emitted, and MOVES says so
literally: `CO2AE` step 2's SQL runs **after** step 1a's `INSERT` and selects
from `MOVESWorkerOutput`, so the Atmospheric CO2 rows it sums are ones the same
calculator has just written. A port that ran step 2 off the energy would use the
same three weights and get a different answer.

**The rule: split the emitted quantity into a DIRECT stage and a SUMMED stage,
and check that the summed one does not feed itself.** Here it does not — none of
86, 98 and 88 is a summand of another — so one extra pass suffices, and *that is
a property of this run to be asserted rather than a law*. The document computes
`rtDay_directQuant`, then three signed aggregates over the same relation joined
on the cohort, then their union.

Two consequences that are easy to get wrong:

* **A summed row must be held OUT of the chain-root resolution.** `8601` is the
  only pollutant-process in this run with **two** `runspecchainedto` rows, and
  the existing parent-join aggregate sums the matches — 8001 + 501 = **8501**, a
  pollutant-process that does not exist. `rspp_isSummed` is what prevents it,
  and the failure it prevents is silent: 8501 matches nothing, so the row would
  simply have emitted zero.
* **A summed row's emission mask is the UNION of its summands'**, because the
  SQL's `group by` makes a row of every group present. TOG's two summands are
  both 104 cohorts; CO2 Equivalent's are 125, 104 and 124 and union to 125.
  Taking the intersection, or the first summand's, gives 104 where the reference
  has 125.

### 40.2 A declaration table is not a complete declaration; check it against the calculator

`runspecchainedto` is MOVES's own statement of which pollutant-process is
computed by scaling which other one, and §32 taught reading the chain from it
rather than writing it down. **It is not complete, and nothing in the table says
so.** In this run it carries 21 rows, and:

| pollutant-process | chained? | declared in `runspecchainedto`? |
|---|---|---|
| 3101 (SO2) | yes, off 9101 | **yes** |
| 9001 (Atmospheric CO2) | yes, off 9101 | **no** |
| 9801 (CO2 Equivalent) | yes, off 9001/501/601 | **no** |
| 8801 (NonHAPTOG) | yes, off 8001 and the species | **no** |
| 8601 (TOG) | yes, off 8001 and 501 | **twice** |

The reason is a fact about MOVES rather than about the data: **only
`AirToxicsCalculator` reads that table.** `HCSpeciationCalculator` has no
`ChainedTo` table at all, and `CO2AE` and `TOGSpeciation` carry their input
pollutants as Java constants — `co2ae:161`'s `TOTAL_ENERGY_POLLUTANT_ID`,
`co2ae:168`'s `"90,5,6"`, `togspeciation.rs`'s NMOG.

**The rule: a table that declares structure is evidence about the calculators
that READ it, and which those are is a question with an answer in the source.**
Read the table where a calculator reads it, and write the constant where a
calculator carries one — then union the two and **assert they are disjoint**.
`run_chainDeclarationOverlap` is that assertion, and it is worth more than the
union it guards: MOVES writes a `runspecchainedto` row for a pollutant-process
exactly when no calculator carries its input as a constant, and if that ever
stops being true the document would silently double a factor.

The neighbouring temptation is to normalise: to write all four chains as table
rows, or all four as constants. Both lose the distinction, and the distinction
is the fact.

### 40.3 Measure the general alternative before preferring the specific one

The three summed stages are three aggregates, one per calculator, each with a
scalar predicate on the left and its own table on the right. The general
alternative is one aggregate against a weight relation indexed by
`(output pollutant-process, input pollutant-process)`, which needs a **two-sided
join**: the same column, `rt_polProcessID`, matching a different column of a
third relation on each side of one clause list.

**It works.** A per-clause `syms` pair resolves the ambiguity, and a probe on
this fixture drove it correctly — 8601 picked up 208 non-zero cells, the sum of
its two declared inputs, and every other chained pollutant-process picked up its
own. Recorded here because a reader of the three-aggregate form would reasonably
assume the general one had been refused.

**The rule: when a document chooses the specific spelling over the general one,
say whether the general one was unavailable or merely unwanted, and measure
which.** Here it is unwanted and the reason is §40.2's: a table-driven weight
would be half table and half constant, because `runspecchainedto` does not
declare two of the three. That is a fidelity argument, and it survives; "the
format could not express it" would have been a false one.

### 40.4 Two rate tables that differ by one key pair, and what the difference is worth

`emissionratebyage` and `emissionrate` are the same relation with and without an
`ageGroupID` key: a criteria pollutant's rate deteriorates and a source bin
carries seven of them, while energy and N2O do not and carry one. Three roots,
two tables, and the document writes **both lookups** rather than a widened one.

The measurable consequence is small and entirely structural. Model year 2000
electricity has no `emissionratebyage` row at age group 2099, so THC drops that
cohort; `emissionrate` has no age group to be missing, so Total Energy keeps it.
**That one cohort is the whole difference between this fixture's 125-row blocks
and its 124-row ones** — 8 of the 5,534 rows, and no numeric error anywhere.

**The rule: when two lookups differ by one key pair, the union of their results
is only a union while their key SETS are disjoint, and that is a thing to
assert.** `run_rateTableOverlap` counts the rate rows both tables serve and is
0. Without it, a snapshot that gained an `emissionrate` row for polProcessID 101
would double every THC rate and the fixture would fail somewhere that looks like
arithmetic.

### 40.5 A registration count is an upper bound against a database, not a size

`calculator-dag.json` credits `TOGSpeciationCalculator` with **184
registrations** — sixteen CB05 mechanism pseudo-pollutants 1000…1018 plus
NonHAPTOG across twelve organic-gas processes — and a plan that sized the rung
from that number would have budgeted for the largest calculator in the port.

Measured over the corpus, by unioning all 42 snapshots' `pollutant` tables:
**116 distinct pollutantIDs, maximum 3000, and not one of 1000–1018.** Against
the pinned default database the calculator registers **24** pairs, and its
`Section Processing` algorithm writes exactly **one** pollutant, 88 — the
individual mechanism species are computed upstream by `AirToxicsCalculator` and
the pseudo-pollutants are chain bookkeeping.

**The rule: a `registrations_count` is what a calculator would register against
a database that had every pollutant it names. Divide it by the database before
quoting it, and quote both numbers.** The corollary is the one that costs time:
`tools/calculator-coverage.py` prints the DAG figure, correctly, because the DAG
is the authoritative module inventory — so the correction belongs in the port
specification beside it and not in the tool.

The same rung supplies the matching rule for *scheduling*. §35.2 established
that a generator's port has a second half — which runs produce output at all.
For a calculator the analogue is which snapshot exercises it, and
**class-loading is not that signal**: `TOGSpeciationCalculator` is class-loaded
in all 42 snapshots because `ExecutionRunSpec` calls its static
`needsFinalAggregation()` whether or not a mechanism is selected. The
discriminator is a table — `integratedSpeciesSet`, 14 rows in one snapshot and 0
in the other 41, *including* the one named `chain-tog-speciation`. **Pick the
snapshot by the INPUT the calculator cannot run without, never by the class
list.**

### 40.6 Retargeting moves every ordinal, so re-address every assertion and not the failing ones

§27.3 makes a retarget the first move on a new rung, and this one paid: pointing
`fixtures/process-airtoxics.esm` at this snapshot, with a path substitution and
a model rename and no new equation, reproduced **2,538 of the 5,534 rows** with
an exact key set at a worst relative error of 8.207e-06.

What a retarget also does is move every ordinal. The pollutant-process relation
grew from 6 rows to 27, so every coordinate into it, into the rate relation
(pollutant-process-major over the cohorts) and into the output relation now
names something else. 288 inherited assertions, 77 failing.

**The rule: re-address EVERY affected coordinate, not the failing ones.** An
assertion that used to name pollutant-process 2 and still passes now names a
different pollutant-process and is checking something else while reading green —
the eleventh instance of this repository's plausible-wrong-value failure, and
the first where the wrong value is a *coordinate* rather than a number. Of the
135 rate-relation coordinates re-addressed here, 65 were passing beforehand.

Two things make the re-addressing checkable rather than a leap:

* **After a purely mechanical re-address, exactly one assertion should still
  fail** — the one whose claim genuinely changed. Here it was
  `run_outputRateRowCount`, 644 → 2,767. One failure is evidence the remap was
  an address change; a handful would have meant it was also a claim change.
* **An output-relation assertion is re-addressed by KEY, not by ordinal.** Emit
  the old fixture's `out_pollutantID` / `out_dayID` / `out_modelYearID` /
  `out_fuelTypeID`, look each old ordinal's key up in the new fixture's, and
  re-read its `expected` from the new snapshot's `MOVESOutput`. The document
  says WHERE and the reference says WHAT, which is §12's rule surviving a
  change of address.

---

## 41. A concession to the capture is retired by re-measuring it, and the retirement is worth as much as the concession **[Phase 5 continued, 14,036 cells, one exception deleted]**

§36 is this repository's record of a residual that belonged to the *capture*
rather than to the port, and of the vocabulary invented to say so: a declared
**scope**, holding 968 cells out of a comparison and allowing a 5 × 10⁻¹³
absolute floor beneath the relative gate on 2,629 more. `moves.rs` then fixed
the capture — `moves-snapshot/v2` writes the shortest decimal that round-trips
the f64 — and the whole concession came out. What that cost, and what it taught,
is different from what §36 taught.

### 41.1 Read the encoding. A replaced field must not be defaulted

`moves-snapshot/v1`'s sidecar carried `"float_decimals": 12`, from which a
consumer derived a storage quantum of `0.5 × 10⁻¹²`. v2 carries

```json
"float_encoding": { "kind": "shortest_round_trip", "max_significant_digits": 17 }
```

and **omits `float_decimals` entirely**. That omission is the design: there is
no fixed decimal count under the new rule, so any number written into the old
field would be a lie a consumer would silently turn into a wrong tolerance
floor. An un-updated consumer fails instead.

So the consumer's job is not to substitute a default; it is to **name every
branch and refuse the rest**. `compare-output.py`'s `FloatEncoding` answers one
question — how much absolute difference the reference is incapable of
recording — and answers it for `fixed_decimals` (`0.5 × 10⁻ᵈ`),
`shortest_round_trip` (**zero**), an absent sidecar (`None`, which is a third
fact and not a synonym for either), and nothing else. An unknown `kind`, or a
sidecar carrying neither field, raises.

**Derive the concession from the ENCODING, not from the flag.** The
`allow_storage_quantum` declaration is unchanged in the comparator, but against
a lossless capture the floor it computes is `0.0`, so the declaration allows
nothing and says so in the report. A flag whose obstacle has disappeared should
go inert on its own, before anyone remembers to delete it — otherwise the
window between "the corpus was fixed" and "someone edited the config" is a
window in which the gate is quietly weaker than it reads.

### 41.2 Both formats are read by the COMPARATOR; only one by the specifications

These are different lifetimes and conflating them costs a working test suite.

* The **comparator** reads v1 and v2, because a corpus migrates on a branch and
  a checkout that can judge only one format can be tested against only one
  branch.
* The **specifications and fixtures** pin exactly one corpus, because a spec
  quotes values and a fixture asserts ordinals, and those differ between the
  two captures for reasons that have nothing to do with tolerance.

Say which, in the document. `run-nr-airtoxics-oracle.sh` now READS the encoding
and **asserts it is lossless**: pointed at a v1 corpus it fails loudly rather
than reporting a clean comparison of a capture it is silently mismodelling.
That assertion is the honest form of "this specification describes v2".

**And measure what the pinning costs, rather than asserting it.** Run this tree
against the v1 corpus and `./run-tests.sh` exits 1 with **19 failures**: the
data-sources gate, all twelve day-halving fixtures' inline assertions,
`nr-airtoxics-lawn-garden-county`'s (its execution-database id differs between
the two captures), and five oracles. Against v2 it is 191 ok, 0 FAIL. So this
tree must land in the same window as the corpus it describes — which is what
`moves.rs/docs/snapshot-v2-migration.md` recommended, and the number is here so
that nobody has to rediscover it by running the suite against the wrong branch.

### 41.3 The retirement is a measurement, and the retired numbers stay

What was deleted, measured on the v2 corpus with `[cell] rel` untouched at
2 × 10⁻⁵ and the whole scope removed:

| | scope in place (v1) | scope deleted (v2) |
|---|---|---|
| rows compared | 13,068 of 14,036 | **14,036 of 14,036** |
| absolute floor | 5 × 10⁻¹³ | **none** |
| worst cell the gate saw | 9.417 × 10⁻⁶ in EXCESS of the floor | **9.417 × 10⁻⁶ raw** |
| pollutant 131 | not compared | 6.836 × 10⁻⁶ |
| pollutant 142 | not compared | 9.183 × 10⁻⁶ |
| worst of all 29 pollutants | — | 9.417 × 10⁻⁶, a factor of 2.1 inside |

The same worst cell over 968 more of them, with 2,629 fewer excused. The
independent float32 reproduction, which takes nothing from the reference but
the final comparison, reports 9.425 × 10⁻⁶ on the same 14,036 — so the
retirement is checked by two routes, which is §12's rule applied to the
*removal* of a concession rather than to its addition.

**Keep the retired numbers in the file that used to carry the exception.**
`tolerance.toml`'s `[fixtures]` section now has no scope and, in its place, the
measurement that removed one and the cost of the choice: on a v1 snapshot 1,012
of 14,036 cells exceed the gate, so the deleted scope would be needed again.
A deleted exception with no record is indistinguishable from an exception that
was never justified.

### 41.4 A fitted coefficient is a hypothesis, and a recapture is the only thing that can mark it

§36.2's method — fit the coefficient the reference must have used, show it is
inside half a stored quantum, assert it in the oracle every run — produced
1.1045021 × 10⁻⁹ and 1.9434497 × 10⁻¹¹ for the two dioxin rates. v2 records
**1.1045 × 10⁻⁹** and **1.94345 × 10⁻¹¹**: the fits were right to 1.9 × 10⁻⁶
and 1.5 × 10⁻⁷ relative, two orders inside the gate they were used to justify.

That is a vindication of the method and it must not be read as a licence. The
fit was never *evidence* that the arithmetic was right — it was evidence that
the arithmetic was *consistent with* a rate the capture could have rounded to
what it stored, which is a weaker claim, and the only reason it can now be
graded is that someone fixed the capture. When a fit is the best available
answer, say in the document that it is a hypothesis and name the recapture that
would settle it.

---

## 42. A RunSpec correction is not a tolerance question, and what it costs is coverage **[Phase 5 continued, 28 of 42 snapshots, 12 of 14 fixtures]**

The `moves-snapshot/v2` recapture carried a second change that has nothing to do
with floats. `<day key="5">` is a 0-based **INDEX** into the sorted
`DayOfAnyWeek` list `[2, 5]` (`RunSpecXML.java:517-532`), not a dayID: 5 is out
of range, it selected nothing, and MOVES fell back to **all** day types. So 28
of the 42 snapshots had been running BOTH days against a one-day intent.
Canonical `RunSpecXML.save` writes `<day id="…">` with the literal dayID
(`RunSpecXML.java:2040`); the fixtures were corrected and recaptured, and every
day-keyed table halved (moves.rs PR #55).

### 42.1 The model did not change, and that is the measurement worth keeping

Twelve of this repository's fourteen fixtures halve. **Not one equation was
edited**, in any of them. Every day axis is sized by a metaparameter whose value
the SOURCE's own `extent` supplies — `n_runspecday`, `default: 0` — so the
documents ingested a one-row `runspecday` and emitted 125, 375, 644, 684, 728,
2,767 rows and so on with no intervention at all, and every one of them matched
its snapshot's `MOVESOutput` key set exactly on the first run.

That is the strongest evidence available that the day axis was factored
correctly, and it is evidence that only a corpus-shape change could ever have
produced. **A dimension whose size is written down is a dimension nobody has
tested.** The rule is already in §12 for values; this is the same rule for
extents, and the way to check it is to change the corpus and see whether the
document notices by itself.

### 42.2 What DID have to change, and none of it is model logic

| | count |
|---|---|
| `metadata.note` row counts in `data_sources` | **65**, over 12 fixtures |
| inline assertion coordinates re-addressed or re-valued | **461** |
| inline assertions deleted as weekend-only claims | **110** (2,564 → 2,454) |
| oracle-fence hardcoded totals and `len(days) == 2` asserts | 7 |
| corpus-wide FLOORS in `run-omd-oracle.sh` | 3, and they went DOWN |

`tools/check-sources.py` caught all 65 notes one at a time, which is what it was
built for. Nothing caught the assertion prose; §42.5 is what to do about that.

### 42.3 Re-address by KEY, and MEASURE the layout rather than deriving it

§40's rule — an output assertion is re-addressed by the KEY it named, not by
arithmetic on its ordinal — is what this pass ran on, and the day correction
adds the reason it cannot be shortcut.

**The day is the outermost factor of `output_rows` in seven fixtures and the
innermost in five**:

| layout | fixtures |
|---|---|
| blocked, day outermost (`o -> o - N/2`) | mixed-onroad, process-brakewear, process-tirewear, process-evap-fvv, process-evap-leaks, process-evap-permeation, process-nox-speciation |
| interleaved, day innermost (`2r-1`/`2r`, `o -> o/2`) | process-airtoxics, process-crankcase-running, process-pm-exhaust, process-refueling, chain-so2-co2e-mechanism |

The index-set declaration is the **same product either way** —
`{"op": "*", "args": ["n_outputCohort", "n_runspecday"]}` — so the layout is a
property of the equations that fill the relation and cannot be read off the
size. Worse, the two can differ WITHIN one document: `activity_rows` is
day-outermost in all twelve, including the five whose `output_rows` is not.

So the layout is measured, per fixture and per axis, by emitting the old
document's key columns and reading `out_dayID` down the ordinals. A mapping
that had been assumed uniform would have silently re-pointed five fixtures'
assertions at the wrong rows — and they would still have PASSED, because an
interleaved fixture's `o/2` and a blocked fixture's `o - N/2` both land on
real rows with plausible values.

### 42.4 A weekend claim has three fates and they are not interchangeable

Of the 571 assertions this pass touched, each was one of:

* **an address change** — the same claim at a new ordinal, value untouched.
  The majority, and the safe kind.
* **a claim change** — a worked example that named a weekend row now names the
  SAME COHORT on the weekday. The value is re-read from the reference
  (`MOVESOutput`, `baserate_*_2020` or `baseratebyage_*_2020` at hourDayID 95),
  never rescaled from the weekend number and never rounded off the port's own
  answer. `mixed-onroad`'s example A goes 0.895519 → 1.99515 that way.
* **a deletion** — 110 of them, and every one is a loss. Where the weekend
  assertion was half of a two-day pair, the weekday half already carried the
  same number and nothing is lost but a duplicate. Where it was not, a claim
  goes: the weekend drive-cycle weight total 1.0000004, the weekend arithmetic
  mean speed 66.094076 and 67.0416879, `process-pm-exhaust`'s `act_dayID` 2 /
  `act_hourDayID` 72 / `day_noOfRealDays` 2, and
  `process-evap-permeation`'s whole `pc5_divides_by_the_day_types_real_days`
  premise.

### 42.5 Say what the correction cost, in the test that lost it

**Every two-valued day factor in this repository is now exercised at one
value.** `noOfRealDays` is 5 and never 2; `hourDayID` is 75 and never 72;
`dayVMTFraction` has four rows and not eight; the drive-cycle weight vector is
built once and not twice. A port that dropped the divisor entirely, or that
hardcoded 5, now passes every fixture here.

That is a real regression in what the suite can catch, it is the direct price
of running what the RunSpec meant, and the corpus already contains the cure:
**`expand-day` is the one snapshot that still carries both day types** and it
has no `.esm` fixture. Porting it is the cheapest coverage in the tree.

**It has been ported.** `fixtures/expand-day.esm` and `docs/expand-day.md`,
250 of 250 rows at 7.106 × 10⁻⁶, 109 assertions of which 69 are day-keyed. §43
is what that cost and what it bought.

The rule: when a corpus correction removes a case, write the loss into the test
that used to cover it, not only into a migration note. Each affected test's own
`description` now says which value it stopped checking, because the reader who
needs to know is the one adding the next assertion to that test.

---

## 43. Restoring a case a corpus correction removed **[Phase 5 continued, 250 rows, the corpus's only two-day snapshot]**

§42.5 named the loss and named the cure. `fixtures/expand-day.esm` is the cure
taken: `fixtures/mixed-onroad.esm`'s chain at hour 7 over both day types, 250
of 250 rows, key set exact, worst cell 7.106 × 10⁻⁶, no tolerance added or
widened. `docs/expand-day.md` is its specification. Four things are worth
keeping, and one of them is a limitation nobody had met before.

### 43.1 A retarget that changes no equation is the measurement, not the shortcut

The whole of the model work was 46 `url_template`s, a `data_sources` prefix and
a model name. **Not one equation was edited**, and the document emitted the
correct 250-row key set on its first run, because every day axis is sized by
`n_runspecday` out of the source's own `extent`.

§42.1 made that measurement in the shrinking direction — twelve fixtures halved
with no intervention. This is the same measurement in the growing direction,
and it is the stronger of the two: halving an axis to one can be survived by a
document that mishandles the axis, since a one-element loop and a scalar are
indistinguishable. Doubling it cannot. **A dimension that grows correctly with
no edit is a dimension that was factored; a dimension that only ever shrinks to
one has not been tested at all.**

The corollary is a scheduling one. Retargeting is already this repository's
first move on a new rung (§27.3), and it should be the first move on a *corpus
change* too: the cheapest question you can ask a new corpus is what the
existing documents do with it before anything is edited.

### 43.2 A two-valued factor is covered by the PAIR, not by either value

`dc_WTotal` is 1 on each day type and `dc_WModeCount` is 23 on each. Both are
real structural tests, both were restored to two rows here, and **neither can
tell a per-day `W` from one shared vector indexed twice**. The assertion that
can is `cohDay_meanBaseRate` at the same cohort on both days, where the two
values differ by 15 % to 28 % because 67.0 mph and 56.4 mph weight the
operating modes differently.

Same for the divisor. `outNoOfRealDays` = 2 and 5 says the right numbers
arrived; `out_emissionQuant` at the same cohort on both days says they were
applied, and it is the only one of the two that a port hardcoding 5 fails at
2.5×. **State the structural claim and the value claim separately, and expect
only the second to falsify a collapse.**

### 43.3 Prove the coverage by collapsing the axis, in the oracle, with an assert

A fixture that ingests a two-valued dimension and never distinguishes it is
decoration, and the difference is not visible by reading. So
`run-expand-day-oracle.sh` recomputes the whole answer three more times, with
the day axis collapsed three different ways, and **asserts** that each moves at
least half the output rows by more than the fixture's own cell gate:

| collapse | rows moved | worst relative move |
|---|---|---|
| `noOfRealDays` pinned at 5 | 125 of 250 | 0.600 |
| the divisor dropped | 250 of 250 | 4.00 |
| one shared `W` and one shared `sho` | 125 of 250 | 7.14 |

This is §21's rule — an oracle must assert its tolerance, not print it — applied
to a *coverage* claim rather than to an accuracy one. The script also refuses
outright if `runspecday` is not `[2, 5]`, because every claim in it is vacuous
on a one-day run and a vacuous pass is the failure mode the whole exercise is
about.

**And do it to the DOCUMENT too, beside a one-day sibling, because that is the
comparison that states the loss.** The same two edits — `outNoOfRealDays`
rewritten to the constant 5.0, and the `act_dayID` key pair deleted from the
two S7 shares' `join.on` — turn 6 and 18 of `expand-day`'s 109 assertions red
and **0 and 0** of `mixed-onroad`'s 59. The day-collapsed `mixed-onroad` also
passes the comparator, 125 of 125 rows at the same 8.319 × 10⁻⁶ worst cell as
the correct document. §42.5 said a port that hardcoded 5 would pass every test
here; that is now a measurement rather than an inference, and the fixture that
falsifies it is the evidence it was worth writing.

The specification carries the same argument in the other direction: §6.6 of
`docs/expand-day.md` lists, per collapse, **which named assertions go red**, and
then lists the 40 of 109 that a day-collapsed port would still pass. Saying
which assertions do *not* cover the thing is what keeps the claim honest.

### 43.4 A scope move audits the stage whose CLAMP it crosses, and says which one it did not

Hour 7 is 59.5 °F against `mixed-onroad`'s 66.9. Two clamped stages sit in the
chain and the colder hour moves them in opposite directions:

* the **EV temperature adjustment** crosses its quadratic's nearer zero at
  63.964 °F, so the raw adjustment is +0.015625 instead of −0.0041922, the
  `adj < 0` clamp does not fire, and `temperatureadjustment`'s `regClassID` 0
  WILDCARD row reaches `emissionQuant` on all 82 electricity rows. Removing the
  wildcard step moves the worst cell from 7.106 × 10⁻⁶ to 1.539 × 10⁻², which
  is the same figure §27.3 measured from the `.esm` side, reached independently.
* the **A/C activity term** goes from −0.0189 to −0.2969815, which is *further*
  inside its clamp. The colder hour bought nothing here, and the specification
  says so in §2.1 rather than letting a reader infer that a moved scope
  exercises more of everything.

**The rule, refining §27.3:** a scope move audits the stages whose *branch* it
changes, and a spec that reports only the branch it gained is reporting half a
measurement. Name the clamp you moved away from too.

It also found a defect in a neighbour, which is the other half of §27.3's
argument for retargeting: `docs/mixed-onroad.md` §6.5's reproduction script
implements no temperature adjustment at all. At 66.9 °F that is an exact
identity and the script is right; at 59.5 °F it is 1.54 % wrong on 82 rows. A
stage that is only correct because a clamp fires is not correct, in an oracle
exactly as in a document.

### 43.5 A claim about an INPUT has to be made one stage downstream

Finding **F43**: an inline assertion naming a `kind: data` parameter cannot be
evaluated — `array state '…' has no cells in var_map`, at run time, after the
document validates and after the source has been read correctly. Measured over
seven columns from seven tables; seven of seven.

It bit exactly where it would hurt most. The three columns that carry the day
axis into this chain — `runspecday.dayID`, `dayofanyweek.dayID`,
`dayofanyweek.noOfRealDays` — are all ingested parameters, and this is the
fixture whose subject is the day axis. Six assertions had to move.

Where they moved to is the part worth keeping: **pin the value where it is
USED, not where it is read.** `outNoOfRealDays` on both output blocks is a
strictly stronger claim than `dow_noOfRealDays` would have been, because a
divisor that arrives correctly and is then not applied fails the first and
passes the second. So no coverage was lost here — but that is a property of
this particular column and not a general reprieve, and the loss it *does* cost
is stated in the finding: an input that arrives wrong and an input that is
never used stopped being distinguishable.

Nothing in this repository had met F43 before, and the reason is worth writing
down as a rule of thumb rather than as an accident: of the 2,454 fixture
assertions that existed before this one landed, **zero** named an ingested
parameter. Every fixture pins its inputs one stage in, because that is where
the arithmetic starts. A document whose subject is an input is the only kind
that meets the wall.

## 44. One output table, several generators: a table-keyed count is not a generator-keyed one **[Phase 5 last rung, three generators sharing a table, four sharing another]**

§35.2 says a generator's claim has two halves — the rows, and *which runs
produce rows*. Both halves are usually measured by looking at the generator's
output table, and for a generator that owns its table that is right.

**Three of MOVES's five operating-mode generators write `OpModeDistribution`.
Four write `RatesOpModeDistribution`.** A count keyed on the table therefore
reports the same number for every generator that writes it, and that stayed
invisible for exactly as long as the table was empty.

`scale-project` joined the corpus and
`LinkOperatingModeDistributionGenerator` wrote 122 rows into
`OpModeDistribution`. Two things went red the same day and both were the
same mistake seen from different sides:

* `tools/check-reachability-counts.py` derived
  `docs/omd-generator-reachability.md`'s "snapshots with rows" column from
  the table name, so it demanded the document claim output from
  `OperatingModeDistributionGenerator` and
  `MesoscaleLookupOperatingModeDistributionGenerator` — two generators no
  snapshot has ever class-loaded.
* `./run-omd-oracle.sh` partitioned `RatesOpModeDistribution` on
  `avgSpeedBinID == 0`, with a comment saying that separates its two
  generators from `AverageSpeedOperatingModeDistributionGenerator`'s bins
  1-16. It does. It does not separate them from
  `LinkOperatingModeDistributionGenerator`, which also writes bin 0, and its
  21 rows were counted against the sibling specification as rows it had
  failed to predict.

### 44.1 The reachability count is an INTERSECTION, and it is necessary, not sufficient

The fix for the first is one line: "snapshots with rows" means
**class-loaded here AND the table non-empty here**, not the size of the second
set. That distinguishes the three — `Link…` 1, the other two 0 — and it is
also what the `reachable?` verdict beside it always meant.

Say what it does not buy. An intersection does not attribute a ROW to a
generator: a generator loaded alongside a sibling's non-empty output still
counts. It buys exactly one thing, which is the thing that broke — a generator
nothing loaded can no longer be credited with a sibling's rows.

### 44.2 Attribution needs the table's own partition key, and it must be NAMED

The second fix is not generic and cannot be. `RatesOpModeDistribution`'s
partition key is the PAIR `(roadTypeID, avgSpeedBinID)`:

| generator | roadTypeID | avgSpeedBinID |
|---|---|---|
| `RatesOperatingModeDistributionGenerator` | literal 1 | 0 |
| `StartOperatingModeDistributionGenerator` step 400 | literal 1 | 0 |
| `AverageSpeedOperatingModeDistributionGenerator` | — | 1-16 |
| `LinkOperatingModeDistributionGenerator` | **the link's own** | 0 |

The first two are not separated by it at all, and do not need to be: they are
specified together, in one document, for that reason. What matters is that the
key is written down in the reproduction beside the filter, with the Java line
that sets each column, so that the next generator to write the table is
noticed rather than absorbed.

**A shared output table is not a defect and should not be normalized away.**
MOVES writes one table because one table is what the downstream calculator
reads. What has to change is the counting.

### 44.3 The measurement that says a partition is still complete

`avgSpeedBinID == 0` was sufficient for two years of this corpus and became
insufficient without any code changing. The thing that made it insufficient
was a capture. So the guard is not a code review, it is the oracle's own key
set: `0 missing / 0 extra` over every snapshot, asserted exactly rather than
within a tolerance, fails the moment a new writer appears — which is what it
did, with `21 missing`, on the day `scale-project` landed.

## 45. "No fixture exercises it" and "the model never runs it" are different claims **[Phase 5 last rung, one of five moved]**

§35.5 and §39.3 both concern what a corpus can and cannot see. This is the
case where the corpus cannot tell two situations apart at all, and where
saying which one it is turned out to matter more than any number.

`docs/omd-generator-reachability.md` recorded five generators as unreachable
and gave **one reason for all five**: no RunSpec in the corpus selects the
project or mesoscale-lookup domain. Every one of the five had
`class-loaded in 0 / 42`, so the corpus gave no evidence that would separate
them.

`moves.rs` captured a project-domain RunSpec. **Exactly one of the five
moved.** The other four were never a capture problem:

* three are discarded by `MOVESInstantiator.java:1449`, which clears
  `neededClassNames` under `CompilationFlags.DO_RATES_FIRST` and re-adds a
  whitelist containing none of them. No RunSpec, in any domain, at any scale,
  instantiates them while that flag is `true`;
* the fourth is not a class. `NewTvvYearGenerator` is a named SQL section of
  `MultidayTankVaporVentingCalculator.sql`.

### 45.1 A zero has a reason, and the reason is not in the corpus

"0 of 42 snapshots" is a measurement. "…because no RunSpec selects that
domain" is an inference, and the corpus contains nothing that supports it over
"…because MOVES never instantiates it". The two look identical from the
snapshots and differ completely in what to do next: the first is a capture
away, the second is unreachable for as long as the pinned source stands.

So when a document records a zero, it must say which, and cite something
outside the corpus for it — the instantiator's control flow, the absence of a
class, the RunSpec element nothing sets. A reason drawn from the corpus alone
is the reason the corpus cannot have.

### 45.2 The cost of getting it wrong is a capture, and it was paid

This is not a stylistic point. Reaching `LinkOperatingModeDistributionGenerator`
took a new input database, a fixture correction, a capture and a 360-table
snapshot in `moves.rs`. Had the note been right about the other four, the same
work would have been proposed for each of them and none of it could have
succeeded. The single sentence "no RunSpec selects that domain", applied to
five modules on the strength of one shared zero, was a plan for four captures
that cannot exist.

### 45.3 Prove the negative where it can be proved, and prefer the oracle

Three of the four need a reading of Java and stay prose, cited to line
numbers. The fourth does not: `docs/new-tvv-year.md` rebuilds all three
tables the SQL section produces from an existing snapshot, 1,750 cells
bit-exact, and asserts **three negatives** alongside — no class named
`NewTvvYear*` is loaded anywhere in the corpus, every snapshot that has the
tables loads `TankVaporVentingCalculator` instead, and the DAG entry still
carries `java_path: ""` with zero registrations.

The negatives are the point. A document asserting only the table contents
would go on passing after someone found the class. These fail, and the day
they fail the document should be deleted rather than repaired.

## 46. A quotient's decimal scale is a property of the EXPRESSION, not of the table **[Phase 5 last rung, 80 cells at five places, 124 at four]**

§39.2 settled that MariaDB's exact-value division gives a DECIMAL whose scale
is the dividend's plus `div_precision_increment`, and measured
`COUNT(opModeID)/starts` at four places over 124 cells. The natural
generalization — the one this rung nearly made — is that MOVES's operating-mode
fractions are four-decimal DECIMALs.

They are not. `LinkOperatingModeDistributionGenerator` writes

```sql
(secondCount * 1.0 / secondTotal) as opModeFraction
```

into the same family of tables, and `* 1.0` makes the dividend a DECIMAL of
scale **1**, so the quotient has 1 + 4 = **five** places. Measured over the
80 bracketing cells the corpus carries:

| quotient | bit-exact cells |
|---|---:|
| DECIMAL to 5 places | **80 of 80** |
| DECIMAL to 4 places | 4 of 80 |

Two sibling generators, one `* 1.0` apart, one digit apart.

### 46.1 Parameterise the scale; do not copy the rounding

`lib/operating_mode.esm`'s `decimal_quotient` now takes `scale` as a
parameter, and `op_mode_fraction` and `link_op_mode_fraction` bind 10⁴ and
10⁵ to it. That is one rule with two bindings rather than two templates that
happen to round the same way — and it is the same argument that file already
makes for *not* reusing `lib/population.esm`'s `pop_file_rounding`, which
rounds identically for an unrelated reason.

The discriminator is worth keeping in the reproduction rather than only in
prose: the wrong scale must MISS, measurably, or the assertion is decoration.
118 of the LinkOMD oracle's 122 cells go red at four decimals.

### 46.2 Read the operand types, including the ones a literal introduces

The general form of both §39.2 and this section is: **the scale comes from
the operands, and a literal is an operand.** `COUNT(x)` is a `BIGINT` of scale
0. `x * 1.0` is a DECIMAL of scale 1. Neither is visible in the column
definition, in the table, or in the value — only in the expression that wrote
it. A port reading the schema, or the stored numbers, or the sibling
generator, gets it wrong in three different ways.

## 47. Writing down the date a figure was true is not a mechanism **[58 claims, 20 of them stale]**

§35.5's corollary asked prose that states a corpus-wide count to write down the
date it was true. `docs/omd-generator-reachability.md` did exactly that —
"43 snapshot directories, 42 with an `execution-trace.json` … at `moves.rs`
commit `3c07836`" — and then rotted anyway. The `moves-snapshot/v2` recapture
with the `<day id=>` correction halved most of the per-snapshot row counts in
its two grids, and fourteen of twenty-three went wrong in one merge. Nothing in
the suite noticed, because nothing in the suite was reading them. The note went
on being cited as the evidence for a porting decision, with the stale commit
hash sitting at the top of it like a receipt.

The date is doing something real — it tells a reader the figure is *as of* a
moment rather than *forever*. But it only helps a reader who already suspects
the number, and the whole reason to write a measurement down is so that later
readers do not have to re-derive it. **A date says a figure could be stale; it
never says that one is.**

### 47.1 Make the document state the numbers and the checker re-derive them

`tools/check-reachability-counts.py` parses the figures out of the document and
recomputes each from `$SNAPSHOTS`; `run-tests.sh` stage 2c fails on a
disagreement. The direction matters: the document holds the answers and the
tool holds only the code to derive them. Invert that — put the expected numbers
in the checker — and you have two copies to keep in step, and the document goes
back to being unverified prose next to a test that passes.

This is the same shape as the oracles (§35.5) and as `run-omd-oracle.sh`
extracting its reproduction from the specification rather than keeping a second
copy, and it generalises past this one note: **a figure in prose that is a
function of the corpus is a test that has not been written yet.**

### 47.2 Check the arithmetic, not the verdict

The checker deliberately skips the `reachable?` column and every sentence of
interpretation around the table. Those are conclusions — argued from the counts
by a person, revised when someone changes their mind — and a test asserting one
would only be asserting that nobody had. Splitting the file this way also let
this change and a parallel one revising those same verdicts land without
fighting over the same lines.

The line is worth stating generally, because it is where this kind of check
turns from useful to obstructive: **assert what the corpus determines; leave
what judgement determines to review.** A count of snapshots is the first; "and
therefore this generator is not worth porting" is the second.

### 47.3 Perturb the checker in both directions

Per §23, an assertion that cannot fail is decoration, and a document checker
has two independent ways to be vacuous: it can fail to read the document, and
it can fail to read the corpus. Both were measured before this was registered.
Changing one row count in the document (`mixed-onroad` 9 → 10) turns up exactly
one failure; hiding one snapshot from the corpus (`process-tirewear`) turns up
twenty, across the corpus-size sentence, the `kind` histogram, seven
denominators, two class-load counts and the grid membership. Unperturbed, 58
claims hold. A checker that only ever saw the document would have passed the
second test, and that is the failure that actually happens.

## 48. An identity is what a reproduction can omit without ever finding out **[four fuels, two reasons, one of them conditional]**

`docs/mixed-onroad.md` §6.5 reproduced 125 of 125 rows at a worst cell of
8.319 × 10⁻⁶ while implementing **no temperature adjustment at all**. It was
not wrong. At that fixture the temperature factor is exactly 1 on every one of
its four fuels, so the stage multiplies by one and omitting it is free — and
invisible, because a missing identity leaves no residue for a tolerance to
catch. It stayed invisible until the same chain was retargeted to hour 7 in
`fixtures/expand-day.esm`, where the worst cell went to 1.539 × 10⁻².

§23 is the rule for the fixture side of this: do not assert a stage the fixture
cannot see. This is the rule for the *reproduction* side, and it points the
other way — **an oracle should compute the identity and assert it, precisely
because it is an identity.** A stage that is absent and a stage that is present
and inert look the same in the output and completely different the next time
the corpus moves.

### 48.1 Name the reason, and say whether it survives a change of input

Establishing that a factor is 1 is not the finding. `mixed-onroad`'s
temperature factor is 1 on all four fuels for **two different reasons**:

* fuels 1, 2 and 5 — `temperatureadjustment` has no row for them at this
  polProcessID at all, both terms default to zero, and the quadratic is 1 at
  **every** temperature. Structural.
* fuel 9 — the terms are real, the raw EV adjustment is −0.0041922, and the
  `adj < 0` clamp returns 1. Conditional, and the condition is narrow: the
  quadratic's roots put the clamp's window at 63.964 °F to 72 °F, and this
  fixture sits at 66.9 °F.

The document had recorded both as "exactly zero, by a second clamp", which
merges a permanent fact with a temporary one. **A document that says a stage is
inert must say which of its inputs would make it live**, or the next reader
cannot tell whether retargeting is safe — and retargeting is this
repository's first move (§27.3, §43.1).

### 48.2 The scope belongs in the reproduction, not only in the prose

The script now prints its own clamp values and asserts them, so the claim
travels with the code that depends on it:

```
temperature:   heat index 66.9000 degF, A/C term -0.0188998 -> factor 0, EV term -0.0041922 -> clamped, factor 1
```

Every other number is unchanged to the last digit. That is the evidence the
stage is an identity, and it is also why nothing would have noticed its
absence.

### 48.3 Perturb an inert-stage assertion, and order the assertions by cause

Per §23 an assertion over a stage that evaluates to 1 is decoration until
something is shown to make it fail, so all three were perturbed against the
unmodified snapshot: heat index → 59.5 °F fires the EV clamp assertion
(`+0.0156250`), heat index → 80 °F fires the A/C clamp assertion
(`+0.3992600`), and removing the `regClassID 0` wildcard step fires the
wildcard assertion.

The last one carries a rule of its own. Without a dedicated assertion, deleting
the wildcard step surfaces as the *clamp* assertion failing with `-0.0000000`
— a message about temperature, for a lookup defect that has nothing to do with
temperature, and exactly the misdirection that let the defect survive until
`process-brakewear` found it. **When one assertion can fail as a side effect of
another's cause, assert the cause first.**

## 49. What crosses a `{ref}` mount into an INGESTING build, measured **[PLAN.md step 7a, four blocks, two of them do not]**

`runs/*.esm` mount components and evaluate; `fixtures/*.esm` read Parquet and
inline everything. The combination — a mounted component that reads Parquet —
was not exercised by anything in this tree until step 7a, and it does not
behave like either half. `spikes/7a/` is the measurement.

**The headline holds: a data BINDING crosses the mount.** A variable declared
inside a ref'd child may carry

```json
"update": { "kind": "data", "source": "spike_agecategory",
            "from": { "file_variable": "ageID" } }
```

where `data_sources.spike_agecategory` is declared **only in the mounting
document**. It is read, the join runs, and the numbers are the default
database's own. That is the assumption PLAN.md §7.1 rests on and it is now
measured rather than assumed.

**It also crosses the other way, which is the more useful half.** The child may
declare the `data_sources` entry itself and the parent supply nothing but the
metaparameter and the index set. So a shared domain document can carry the
whole default-database catalogue and a per-fixture document add only its own
runspec sources.

**Two blocks used NOT to cross, and `esm validate` did not say so. Both do
now.**

| block | may live in the child | must be restated by the mounting document |
|---|---|---|
| `variables`, `equations`, `update` bindings | yes | no |
| `data_sources` | yes | no |
| `index_sets` | yes | no — **since EarthSciAST PR #298** |
| `metaparameters` bound by an `extent` | yes, and should be | no — **since EarthSciAST PR #317** |

**The index-set row used to be the trap and is now settled.** Until #298 a
mounted child's `index_sets` reached the registry `esm validate` reads but not
the one the ingesting build reads, so the mounting document had to restate them
verbatim and a comment had to say the duplication was load-bearing. That was
finding F46, and it is retired: neither `spikes/7a` nor `spikes/7c` declares an
`index_sets` block in its mounting document any more.

**The metaparameter row replaced it, and is settled too.** For two days a name
an `extent` binds had to be declared by the document that owns the axis it sizes
*and* by the root document that is loaded, because #298 resolved a mounted leaf
in its own scope while the loader API still bound discovered extents only at the
root — and deleting the root's copy passed `esm validate` and failed the build
with `template_import_unknown_name`. That was finding F50. EarthSciAST PR #317
binds a discovered extent in whichever document of the assembly declares the
name, at either mount form and transitively, so the name is declared once, by
the document that owns the axis. Neither `spikes/7a` nor `spikes/7c` declares a
metaparameter in a mounting document any more.

**Which document should own the axes: the leaf.** `leaf-owns-shape` — the leaf
declares the metaparameters and the `index_sets`, the mount declares the
`data_sources` — is the only arrangement measured to load under **both** the
Rust and the Python bindings. The obvious alternative, a shape-open leaf sized
by the root's metaparameters, is accepted by Rust and refused by Python unless
the leaf happens to import an expression-template library, which is finding F51
— at `9dd36c7f6`. PR #317 made Rust accept it either way, and records the shape
as non-portable itself.

### 49.1 A `{ref}` mount edge is NOT a closed shape, and one of its four extra fields is the override mechanism

`{"ref": …, "metaparameters": …}` is refused and `{"ref": …, "tests": …}` is
refused, which is easy to read as "a `{ref}` takes nothing but a path". It is
not what the schema says. `SubsystemRef` accepts four more fields, and the one
that matters was looked for under the wrong name:

| field | what it does |
|---|---|
| `bindings` | **closes the referenced document's own metaparameters at the mount edge** (esm-spec §9.7.6 site 3). Each value is a metaparameter expression over the MOUNTING document's metaparameters — an integer literal, or a name, or `NX*NY` — folded at the mount. |
| `model` | selects one of several top-level models in the referenced file |
| `index_set_rename` | renames a mounted axis, so two mounts that both use `lev` at different lengths do not collide |
| `expression_template_imports` | registers a template library into the REFERENCED component's scope — assembler-chosen discretization without editing the leaf |

**So ref-with-overrides exists, spelled `bindings`.** Measured: a child that
declares `index_sets: {cat_rows: {size: "n_cat"}}` and a metaparameter `n_cat`
is closed by `{"ref": "./bind_child.esm", "bindings": {"n_cat":
"n_spike_agecategory"}}`, and the runtime-discovered `extent` of the parent's
source flows through the binding — the same 41 rows and the same
6/9/13/17/60/85/630.

**What `bindings` cannot do is introduce a name.** It closes a metaparameter the
referenced document **declares**; it is checked against the leaf's own
declarations, so a leaf that omits the block is refused at load — `loader API
binds metaparameter 'n_agecategory', which the document does not declare` — no
matter what the mount offers. Measured at 49 names. That is why F50 needed a
format change rather than an authoring one. PR #317 made the change by the other
route — binding the extent where the name is declared — so this limit no longer
costs anything, and `run-tests.sh`'s 7c stage keeps it as a check.

**`model` does not make a mounted document composable.** A referenced file with
two models is refused (`resolves to 2 models; add a "model" selector`), and
selecting the one that names its sibling then fails validation
(`Scoped reference 'Census.totalAge' cannot be resolved`). A mounted document
whose models reference each other cannot be mounted at all — which, with §50,
means a fixture mounts exactly one model and a shared domain document composes
through *expression templates*, not through nested mounts.

### 49.2 Per-fixture configuration: two channels, both already in the fixture

* **a `data_sources` key.** The shared document binds `source: "runspec_day"`
  and never declares it; each fixture declares that key against its own table.
  This is how a runspec's *selections* travel, and §7.3's monolithic conversion
  makes the default-database half of the catalogue identical for every fixture,
  so it can live in the shared document instead.
* **a metaparameter with a literal `default`, read as a number.** A
  metaparameter declared in the MOUNTING document is readable in a ref'd
  child's equation as an ordinary scalar. Measured twice: `metaEcho =
  n_spike_agegroup` gives 7 (an `extent`-discovered count) and `cfgEcho =
  cfg_year` gives 2020 (a literal the fixture wrote). That is the per-fixture
  numeric channel, and the fixture has to declare its metaparameters anyway.

One asymmetry worth knowing, because it is the trap between the two: a
metaparameter closed at the mount edge by `bindings` is **not** readable in an
equation — `Variable 'cfg_year' referenced in equation is not declared`, both
at validate and at build. `bindings` closes *sizes*. To pass a NUMBER into the
shared logic, declare the metaparameter in the mounting document and let the
child name it.

## 50. An ingesting document holds ONE model, so an assembly is verified by its relation and not by an assertion **[PLAN.md step 7a, three closed spellings]**

The moment any variable in a document carries `update: {kind: "data"}`, the
document may declare exactly one model. A second — a mounted `{ref}` beside an
asserting model, which is precisely PLAN.md §7.1's shape — makes **every**
assertion in the document error with `document holds several models; pass
model_name`, including assertions that touch no ingested value. Finding F45.

`runs/micro_exhaust_run.esm` is green today with three models and nine
assertions because it ingests nothing. Add one `kind: data` variable to a copy
of it and all nine error. **The four assemblies in `runs/` are one data source
away from that**, which is worth knowing before one of them is retargeted at
the default database.

And a mounted component's own inline tests do not run — `esm test` says so —
while a *data-open* component cannot be a test target either, because it does
not load alone. Finding F47. So all three ways to assert are closed:

| spelling | refused by |
|---|---|
| an asserting model beside the mount | `document holds several models` (F45) |
| `tests` beside the `{ref}` | the schema: `Additional properties are not allowed` |
| an assertion naming `Child.value` | nothing, since PR #345 (F21, retired) |

**So a ref'd, data-fed assembly is checked by emitting its relation and
comparing it** — `simulate --format csv` against a recorded CSV, which is what
the fixture stage already does and what `run-tests.sh`'s 7a stage now does.
Write the assertions in the child anyway, as `spikes/7a/age_group_census.esm`
does, and have the harness assert that they still do not run: the day they do,
the suite says so instead of the weaker check quietly remaining the only one.

## 51. A name crosses a mount downward only **[PLAN.md step 7a, two spellings, two different refusals]**

A mounting document can name what it mounted (`Rates.emissionRate`, and every
`join.on` in `runs/`). A mounted child cannot name what mounted it, and the
toolchain says so twice over rather than once:

* the **bare** name — the child's equation says `hostVal`, declared only in the
  parent — is refused by `esm validate` **on the child's own file**:
  `Variable 'hostVal' referenced in equation is not declared`. A child's
  equation is resolved in the child's scope, full stop;
* the **scoped** name — `Host.hostVal` — is refused at load as
  `circular reference (cycle) detected: Host -> Child -> Host`.

The mount graph is a DAG pointed downward, and the second message is the useful
one: reaching up is not an unimplemented feature, it is a cycle. **So the
shared document must be the leaf of the assembly, never the root.** Any
spelling that puts the per-fixture data above the shared logic and has the
logic reach up for it does not exist.

## 52. What a `data_source` costs per `esm` invocation, and where the cache lives **[PLAN.md step 7a, two tables, 106 MB and 2.0 M rows]**

`data_sources` load per invocation and `run-tests.sh` invokes the binary many
times, so PLAN.md §7.3 flags the parse as a cost that must be measured rather
than assumed. Measured, on the pinned toolchain, one table per throwaway
document, `esm test` wall clock:

| table | on disk | rows | cold | warm |
|---|---|---|---|---|
| `EmissionRateByAge` | 105.7 MiB | 1,590,830 | **4.94 s** | **0.33 s** |
| `IMCoverage`, consolidated | 0.8 MiB | 2,024,874 | **0.46 s** | **0.41 s** |

Two things in that table are worth more than the timings.

**A monolithic conversion is not merely convenient, it is 470× smaller for the
worst table.** `IMCoverage` is quoted as 378 MB, and it is — as 21,625
Parquet files of ~17 KB each, partitioned county × year. Concatenated it is
**0.8 MiB** over 2.02 M rows: essentially all of the 378 MB is per-file footer
and metadata. Consolidating it took 17.2 s once. The table PLAN.md §7.3 names
as one of the two that matter costs half a second.

**The ingested-source cache is in `$TMPDIR`, and on this machine `$TMPDIR` is
`/tmp`, which is a RAM-backed tmpfs.** `/tmp/earthsci-esm-cache` was already
379 MB during this work. CLAUDE.md's rule about not putting large things in
`/tmp` therefore applies to a tool nobody thinks of as writing there, and a run
that ingests the whole 1.1 GB default database would put roughly that much into
RAM. Set `TMPDIR` to a disk-backed directory before a whole-database run. (The
cache is also the F42 hazard: keyed by URL and never revalidated, so a table
edited in place is not re-read.)

## 53. The Phase 7 mount shape survives at fixture scale, and the numbers are bit-identical **[PLAN.md step 7c, 411 variables, 375 rows, same md5]**

§49–§52 measured the mount edge on 2 tables and 8 variables. `spikes/7c/` is the
same shape carrying a real fixture: `fixtures/process-tirewear.esm` split into
`onroad/model.esm` (49 → 0 `data_sources`, 411 variables, 245 equations, 49
metaparameters, 53 index sets, 6 enums, all eleven `tests` blocks) and
`tirewear_mount.esm` (51 `data_sources`, the same 6 enums, one `{ref}`, and —
until PR #317 — the same 49 metaparameters), itself mounted since 2026-09-15 by
the 43-line `tirewear_fixture.esm` (§53.2).

**The division of the blocks moved once, at EarthSciAST PR #298.** As first
written the mount owned the shape — 49 metaparameters, 53 index sets restated
verbatim from the leaf, 6 enums restated — and the leaf was open. #298 resolves
a mounted leaf in its own scope, which refuses that arrangement, so the leaf now
owns the metaparameters and the axes, and the mount owns the data. The 250
restated index sets are gone; so, since PR #317, is the second copy of the
metaparameters (F50); the enums are still restated, for collision safety rather
than for resolution (§54). Everything measured below survived the move unchanged
except the line counts in §53.1, which are the point of it.

**It works, first try, and the split is not an approximation.** The logic
half's `variables`, `equations`, `tolerance` and `tests` compare equal
key-by-key to the inlined fixture's; only the six
`expression_template_imports` paths and the 49 `url_template`s differ, by one
`../` each, because the two documents live one directory deeper. Emitted with
the fixture stage's own field list, the relation is **byte-identical** — 375
rows over 26 emitted `out_*` fields (27 CSV columns with the leading
ordinal), same md5 — so this is a regression test with an exact
oracle, not a demonstration. `run-tests.sh`'s 7c stage compares it against the
fixture stage's own output in the same run, so there is no recorded CSV to
drift.

**Falsified, not merely observed.** Scaling `emissionrate.meanBaseRate` by 1.5
in a scratch copy of the snapshot moves exactly the cells it should: 250 of
375 `meanBaseRate`, `adjustedMeanBaseRate` and `emissionQuantDirect` cells and
**all 375** `emissionQuant` cells, each by exactly 1.500000, with all 22 key
columns unchanged — and the split and the inlined fixture move *identically*,
byte for byte, under the same perturbation. So the data reaches the equations
through the mount, and the match is not a false positive from a document that
reads nothing.

**The mount costs no measurable time.** Alternating warm runs, `TMPDIR` on
disk: inlined 3.04 / 3.07 / 2.91 / 3.50 s, split 2.97 / 3.43 / 3.34 / 2.92 s.
Cold, cache wiped before each: inlined 4.24 / 4.29 s, split 4.30 / 4.21 s. The
difference is inside the run-to-run noise of either one.

### 53.1 The duplication, counted — and what PRs #298 and #317 removed from it

| block | mount lines | entries | also declared by the logic half |
|---|---|---|---|
| `data_sources` | 954 | 49 | no |

| `models` (the `{ref}`) | 6 | 1 | — |
| **total** | **977** | | **nothing duplicated** |

The mount has lost two blocks to upstream fixes. Before #298 it restated the
leaf's 53 `index_sets` verbatim — 250 lines, and a total of 1505 with 281
duplicated. After #298 it still declared all 49 metaparameters the leaf also
declares — 247 lines, a total of 1255 with 278 duplicated — until PR #317 fixed
F50. The enums went the same way at `8ac536bf0`: PR #353 resolves a mounted
file's `enum` ops against its own block, so restating them protected nothing
(F13, retired) and the 31 lines are gone. Nothing in the mount is now a copy of
anything in the leaf.

The split now costs **+23 lines over the inlined fixture** (17,400 against
17,377, +0.1%), down from +302 after #298 and +552 before it: no fix added
anything to the leaf, which already declared the axes, the names and the
symbols. The per-fixture document of §53.2 adds 12 more.

### 53.2 The per-fixture document, measured four ways

The number that matters is not the split's total but what **one fixture** has to
carry, because Phase 7 plans about thirty of them on one shared document.
Measured on `process-tirewear`, emitting the relation each time to confirm the
bytes do not move:

| the per-fixture document | lines | loads? |
|---|---|---|
| before #298, against the pinned `esm 0.2.0` | 551 | yes in Rust, **no** in Python |
| after #298 (`9dd36c7f6`) | 270 | yes in Rust **and** Python |
| after #298, with the metaparameter block deleted | 23 | **no** — F50 |
| after #317 (`58d21a1a1`): `spikes/7c/tirewear_fixture.esm`, checked in | 43 | yes in Rust; Python not re-run |
| **after #353 (`8ac536bf0`): the enum union deleted with F13** | **12** | **yes in Rust**; Python not re-run |

The first three rows moved the `data_sources` catalogue into the shared document
— the layout PLAN.md §7.1 wants, and the one §7.3's monolithic conversion makes
identical for every fixture. The fourth puts the catalogue in a middle document
instead, so the chain is fixture → `tirewear_mount.esm` (the data) →
`onroad/model.esm` (the logic and its shape). Both layouts were measured at
`58d21a1a1`, with and without the enum block, and all four variants emit the
same 375 rows byte for byte. The three-document one is committed because it
keeps the logic half data-open, which is the 7c stage's control.

**It is 12 lines, and the prediction of 23 was never the floor.** For two days
the document was 43: 31 of those were the enum union
`tools/check-conventions.py` required, because a colliding symbol was applied
silently across a mount (F13). EarthSciAST PR #353 made a leaf resolve its own
symbols, the rule lost its comparison, and the block went. What is left is
metadata and one `{ref}` — the whole of what a per-fixture document has to
carry, with nothing mechanical in it at all. PLAN.md §7.1's "one **thin** `.esm`
per fixture" is now literally true, and the two findings that stood between it
and the format, F50 and F13, are both retired.

## 54. The four override channels at the mount edge, measured at 49 names each **[PLAN.md step 7c, one of the four is unusable]**

§49.1 read `SubsystemRef`'s four extra fields off the schema and ran one of
them once. 7c ran them against a document with 49 metaparameters and 53 axes.

**`bindings` scales, and buys nothing.** 45 of the child's extent metaparameters
closed at one mount edge validate and emit the same 375 rows byte for byte, so
the mechanism is not toy-sized. It removes nothing: the mounting document
declares the 45 under its own names and gains a 45-line `bindings` block, which
is strictly more text than declaring nothing at all — the arrangement PR #317
allows (§49). For two days it was also the workaround F50 needed and could not
have, because `bindings` closes a name the leaf declares and cannot supply one
it lacks (§49.1).

**The 45 is not 49, and the four that are missing are the rule.** A
metaparameter closed by `bindings` is not readable in an equation (§49.2), and
this fixture *reads* four of its metaparameters as scalars —
`n_agecategory`, `n_outputCohort`, `n_runspecday`, `n_runspecsourcefueltype`.
Binding all 49 fails at validate AND at build with `Variable 'n_agecategory'
referenced in equation is not declared`. So the shape of the rule is: **a
size may be bound, a number must be declared**, and a document that mixes the
two has to know which of its metaparameters the logic reads.

**`index_set_rename` works, since #298, and it is the field Phase 7 needs.**
It was refused at this mount form until then —
`subsystem_index_set_rename_unsupported_mount_form`, finding F49, now retired.
Re-measured at `9dd36c7f6`: renaming **all 53** of the fixture's axes at the
mount edge validates *and* emits the same 375 rows byte for byte. `run-tests.sh`
checks it by evaluating rather than by validating, because a rename that
validated and quietly merged under the original names would pass the weaker
check.

This is what lets a per-fixture document namespace a shared domain document's
axes instead of adopting its names, which is the precondition for mounting two
domain documents that both spell an axis `rows` or `lev`. Nothing in this
repository needs it yet; it is checked because Phase 7 plans on it.

**`enums` cross the mount and reach the build, and are no longer restated** —
the fourth block, which 7a had no occasion to test. Change a value in the
mounted child and the emitted relation changes, so nothing about them needs
restating for the build's sake. They were restated anyway until `8ac536bf0`, and
`tools/check-conventions.py` required it: enums merged **first-wins** and a
same-name symbol at a different value was applied silently (F13). EarthSciAST PR
#353 resolves a mounted file's `enum` ops against that file's own block, so the
collision cannot happen, the restatements are deleted and the rule is now
`assembly-ref`. The distinction the old text drew — restated for collision
safety, not for resolution — is why deleting them was safe: nothing ever read
them.

**A metaparameter's `type` must be `"integer"`.** `"number"` is refused by the
schema — `/metaparameters/cfg_scale/type: "integer" was expected` — whether it
sizes an index set, is read in an equation, or is used by nothing at all.
§49.2's "read as a number" means read as a numeric operand, not declared with
a non-integer type; there is no non-integer metaparameter in `esm 0.2.0`. A
per-fixture *scalar* configuration value that is not a whole number has no
metaparameter spelling and has to arrive as data.

## 55. Do not trust `esm validate` to catch a missing declaration — the tool that reports it is not the one you ran **[PLAN.md step 7c, two findings, same shape]**

F46 recorded that a mounting document's missing `index_sets` restatement was
silent at `esm validate` and loud at the build, and F48 that whether you got the
silence depended on one thing nobody would look at: whether the child declared
any **literal**-sized axis. Both are retired — EarthSciAST PR #298 removed the
restatement entirely — and the habit they were teaching is not.

**The same shape came straight back, one block over, and has since gone too.**
Delete the `metaparameters` block a mount declared for its `extent`s and `esm
validate` passed; the refusal arrived at the build, as
`template_import_unknown_name`. That was F50, and it is why `run-tests.sh`'s 7a
and 7c stages ran `validate` **and** the build against their probes and required
the exact code, rather than reading a green `validate` as a verdict. PR #317
fixed it, and both watches went red on the first run against the new binary with
an instruction saying what to delete — which is what a two-sided watch is for.

Three consequences, and the last is the durable one.

* **A harness that watches a declaration by requiring `validate` to pass is
  measuring its own document, not the format.** This was true of the 7a stage's
  F46 watch for as long as it existed, correctly for the document it held.
* **Give a shared domain document at least one literal-sized axis on purpose.**
  A `run_rows` singleton, a 24-hour axis, a 12-month axis. F48's mechanism is
  gone but the reasoning holds for the next gap of its kind: a literal size is
  the cheapest way to convert a class of mistake from a build failure deep in an
  aggregate into a validate error that names the thing.
* **Prefer the arrangement that fails loudly in every binding.** F51 is this
  rule's third instance: at `9dd36c7f6` a shape-open leaf passed in Rust, failed
  in Python, and which you got depended on whether the leaf imported an
  expression-template library. PR #317 changed the Rust side and calls the shape
  non-portable itself. `leaf-owns-shape` fails loudly or passes in both, and
  that is the reason to write it that way rather than any measurement of lines.

## 56. A per-fixture document's size is set by the SHARED document, not by the fixture **[PLAN.md step 7c, 551 → 270 → 43 → 12 lines]**

The blocks a mounting document must carry are keyed to what the **mounted**
document declares, not to any choice the fixture makes. So as a shared domain
document grows, every document that mounts it grows with it, by the same lines,
and the per-fixture documents converge on being copies of each other.

**Two upstream fixes removed almost all of it.** This section read 551 lines per
fixture, 528 of them (96%) mechanical, against named ways out; then 270, of
which 247 (92%) were the single duplication F50 recorded. Measured at
`58d21a1a1` it is **43**, and it is checked in as
`spikes/7c/tirewear_fixture.esm` (§53.2).

1. ~~**Fix F46**~~ — **landed**, as EarthSciAST PR #298: 281 of the 551 lines,
   and a shape both bindings accept.
2. ~~**Fix F49**~~ — **landed in the same PR.** `index_set_rename` works at
   this mount form (§54).
3. **Factor the duplication into a mounted leaf of its own.** Not needed. The
   middle document of §53.2's chain is a mounted document of that kind for the
   *data*, and the shape needed no leaf of its own once F50 was fixed.
4. ~~**Fix F50**~~ — **landed**, as EarthSciAST PR #317: 247 of the remaining
   270.

**Nothing is left.** 31 of the 43 lines were the enum union, restated because
`tools/check-conventions.py`'s `assembly-enums` rule required every assembly to
carry it (F13). EarthSciAST PR #353 made a mounted file's `enum` ops resolve
against its own block, the rule became `assembly-ref`, and the block was deleted
from every assembly that carried it. The per-fixture document is **12 lines**:
metadata and one `{ref}`. This section's subject — that a per-fixture document's
size is set by the shared document rather than by the fixture — is now a
statement about a cost that has been paid down to nothing, and it is kept
because the next shared document will start the same way.

## 57. A unit on a constant is declared once, on the template that names it, and only where the unit is certain **[EarthSciAST PR #347, esm 1.2.0; 28 constants, 493 declarations corrected, 6 unit boundaries]**

A bare numeric literal has an undeterminable dimension, and a product containing
one is not checked (finding F44's units subsection, EarthSciAST #302). From esm
1.2.0 a `const` node may declare the unit its value is in (esm-spec §4.8.5), and
since PR #339 two units agree only in dimension **and** exact scale. This section
is how this repository uses the two.

**1. The unit goes on the `const` inside the zero-parameter template that already
names the constant.** §6 made every reused constant a template, so each value
already existed once, in the library of the stage that uses it, and its unit is
written once, beside it:

```json
"inches_hg_to_kilopascals": { "params": [], "body":
  { "op": "const", "args": [], "value": 3.38639, "units": "kPa/inHg" } }
```

A template call has the unit of its expansion (§4.8.5 rule 5), so one annotation
makes every call site checkable. There is deliberately **no separate conversions
library**: moving `inches_hg_to_kilopascals` out of `lib/meteorology.esm` would
put the number away from the MOVES source it is cited against and buy nothing an
import does not already give. Two constants that share a unit and not a value
stay two templates — NONROAD's `grams_per_pound` 453.6 in
`lib/emission_factors.esm` and the air-toxics 453.592 in
`lib/nonroad_speciation.esm`; the engine's 6.237 lb/gal and the calculator's
6.17 — because a declared unit never checks a value, and merging them would be a
fidelity change, not a units change.

| template | value | `units` |
|---|---|---|
| `lib/drive_cycle.esm` `gravity_m_per_s2` | 9.81 | `m/s^2` |
| `lib/drive_cycle.esm` `mph_to_meters_per_second` | 0.44704 | `m*h/(mi*s)` (rule 9) |
| `lib/drive_cycle.esm` `drive_schedule_time_step` | 1.0 | `s` (rule 9) |
| `lib/drive_cycle.esm` `full_scale_percent` | 100 | `percent` (rule 9) |
| `lib/emission_factors.esm` `grams_per_pound` | 453.6 | `g/lb` |
| `lib/nonroad_speciation.esm` `grams_per_pound` | 453.592 | `g/lb` |
| `lib/nonroad_speciation.esm` `nonroad_engine_gasoline_density`, `air_toxics_gasoline_density` | 6.237, 6.17 | `lb/gal` |
| `lib/meteorology.esm` `inches_hg_to_kilopascals` | 3.38639 | `kPa/inHg` |
| `lib/meteorology.esm` `water_ice_point_kelvin` | 273.15 | `K` |
| `lib/meteorology.esm` `fahrenheit_freezing_point` | 32 | `degF` |
| `lib/meteorology.esm` `percent_scale` | 100 | `percent` |
| `lib/meteorology.esm` `default_pressure_high_altitude`, `default_pressure_low_altitude`, `altitude_pressure_threshold` | 24.59, 28.94, 25.8403 | `inHg` |
| `lib/meteorology.esm` `fahrenheit_to_kelvin`, the slope | 5 over 9 | `K/degF` over `1` |
| `lib/adjustments.esm` `exhaust_temperature_reference`, `nox_diesel_temperature_ceiling`, `pm_temperature_ceiling` | 75, 77, 72 | `degF` |
| `lib/meteorology.esm` `heat_index_threshold`, `heat_index_ceiling` | 78, 120 | `degF` |
| `lib/meteorology.esm` `specific_humidity_constant` | 621.1 | `g/kg` |
| `lib/fuel_effects.esm` `sulfur_switch_ppm`, `sulfur_reference_ppm`, `sulfur_high_ppm` | 30, 30, 303 | `ppm` |
| `lib/fuel_effects.esm` `volume_percent_scale`, `biodiesel_volume_cap` | 100, 20 | `percent` |

**2. `"units": "1"` only where it is measured to make an equation checkable.** A
product or quotient with one bare literal in it is undeterminable, so a unit on
its sibling is wasted unless the literal gets one too. It mattered once:
`fahrenheit_to_kelvin` is `(5/9)·(T − 32) + 273.15`, and with `5` declared
`K/degF` over a bare `9`, a Kelvin result declared `kg` still validates; with the
nine declared `1` it is refused (a three-line probe). The repository-wide sweep
cannot show this, because the same wrong declaration is also caught one equation
later, in `saturation_vapor_pressure`'s `log10`. No other `"units": "1"` is
written: identifier packing (`100·pollutant + process`, `floor(county/1000)`),
code values and fractions stay bare, because nothing they multiply is declared
anything but `1`.

**3. Inline data stays bare.** `lomd_linkAvgGrade = const[0.0, …]` gets no unit on
the `const`: the variable's declaration is the one statement of what the numbers
are in, and a copy on the node would catch only a disagreement between two copies
of the same string. It costs five of the 61 declarations F44's sweep counts —
`act_medianLifeFullLoad`, `lomd_linkAvgGrade`, `met_relHumidity`,
`somd_bandMinSoakTime`, `somd_bandMaxSoakTime`, all data with no checked consumer.
Two more data declarations, `met_rawBarometricPressure` and `met_temperature`,
went from silent to caught with nothing written on them, through the annotated
constants their consumers use — which is the check this rule keeps.

**4. Empirical regression coefficients stay bare — and so the regression takes
pure numbers (rule 8).** The Rothfusz heat-index coefficients, the Goff-Gratch
exponent's, the evaporative RVP and TVV regressions (`0.026196`, `0.00076898`,
`46.321`, …), the EV temperature slopes (`0.00225`, `0.00028`), the scrappage fit
(`-1.4306`, `-0.24`): each has a unit only in the sense of whatever makes its
regression balance, this port has no source that states one, and a unit derived
from the equation is a check against itself.

**The test is whether the equation determines the units uniquely from a SOURCE or
only from itself.** Nine coefficients over two variables (Rothfusz) determine
nothing a source states: `-42.379` would be `degF`, `10.14333127` `degF/percent`,
`-0.00000199` `1/(degF*percent^2)`, and every one of those comes from reading the
formula backwards. One variable is different: a quadratic `A + h(B + Ch)` in a
heat index fixes `B` at `1/degF` and `C` at `1/degF^2`, and MOVES sources both
columns against a temperature in °F. Coefficients that arrive as table columns —
the A/C activity B and C, `tempAdjustTermA` and `tempAdjustTermB`, the VSP A/B/C —
are declarations, not constants, and are rule 6's business; a one-variable
polynomial in them is declared and CHECKED rather than divided out. A
multi-variable fit whose coefficients are literals in a template body is divided
out at its boundary instead (rule 8).

**5. A unit the registry cannot spell, or would misstate, stays bare.**
`days_per_week` (there is no `week`), `quarter_hours_per_hour`,
`kilojoules_per_million_btu` (there is no MMBTU, and `kJ/BTU` is a million out),
and `days_per_year`: the registry's `yr` is the Julian 365.25 days (esm-spec
§4.8.1), so `365 day/yr` would state NONROAD's calendar count as a conversion to
a different year.

**6. An annotation that makes a document refuse is a finding.** If what refuses is
`1` declared on a quantity whose own description or MOVES source names the unit,
correct the declaration — it is a unit error the old check could not see. The
annotations cost 210 such corrections — 51 for §57.1–7 and 159 more for §57.8 —
all in fixtures, components and the 7c spike: temperatures (`degF`), relative humidities (`percent`), heat indices
(`degF`), the temperature-adjustment A and B terms and the A/C activity B and C
terms (`1/degF`, `1/degF^2`, from `1 + d(A + dB)` with `d = temperature − 75` °F,
criteria_running_calculator.rs:3369, and from `A + h(B + Ch)` in a heat index,
setup.rs:409-411), the EV suppression threshold and reference temperature
(`degF`), vapour pressures (`kPa`), a specific humidity (`g/kg`), a sulfur level
(`ppm`) and an ester volume (`percent`). If the fix is not a declaration, or the
unit is not certain, the constant stays bare — or the chain gets a boundary
(rule 8) — and either way the reason is recorded. Measured on `8ac536bf0`
against the annotated tree, two constants were still bare. **Neither is now**,
and each was resolved by a different pass, three days apart. Both rows are kept
struck rather than deleted, because what each one claimed and why it stopped
being true is the part worth keeping — in both cases the blocker was somewhere
other than the constant:

| constant | would be | refuses | why it is neither a declaration fix nor a boundary here |
|---|---|---|---|
| ~~`mph_to_meters_per_second` 0.44704~~ **— RESOLVED by §57.9, which see** | `m*h/(mi*s)` — which the registry resolves to DIMENSIONLESS at scale 3125/1397, since `m·h/(mi·s)` cancels | 11 onroad fixtures, `components/link_operating_mode_distribution.esm`, and all three 7c spike documents | it is a scale factor rather than a dimension, so it does not merely want `mi/h` on one variable: every drive-schedule speed, prior speed, next speed, bin speed and operating-mode speed bound in those documents — about twenty declarations each — has to move together, and one of them cannot move without an expression change. `*_accelerationMs` is `(speed[t] − speed[t−1]) × 0.44704`, which is a `m/s` and is declared and used as a `m/s^2`; the drive schedule's one-second step is real, it is what makes the difference an acceleration, and it is not written down anywhere. Measured: with the annotation, `components/link_operating_mode_distribution.esm` equation 30 is refused `length*time^-2` against `length*time^-1`, which is the defect and not an artefact of the annotation. Writing `÷ 1 s` would be exact and would fix it, and it belongs with the twenty-declaration sweep rather than ahead of it. §57.9 wrote the one-second step down as `drive_schedule_time_step`, typed the chain, and found the `*_accelerationMs` error this row predicted plus two more |
| ~~`short_tons_per_gram` 1.102311e-06, and `grams_per_short_ton` with it~~ **— RESOLVED by §58, which see** | `short_ton/g`, now declared | — | the measurement in this row was right and its DIAGNOSIS was wrong twice. `unitConversionFactor` has a MOVES pin and it is in the function's own docstring (unitcf.f converts g/hp-hr to g/hr by multiplying by hpavg × faclod, exhaust.rs:228-236); `adjustmentTime` and `monthDayFactor` have one too, and it is that they are pure numbers — shares of an activity total over counts of days. What actually blocked the chain was §11's `hp` bullet, false since EarthSciAST `c31ea106d`. §58 declares the chain and `emissionShortTons` is a checked `short_ton` |


**The three the previous pass could not annotate, it now can**, because rule 8
gives their chains a boundary: `heat_index_threshold` and `heat_index_ceiling`
(`degF`), `specific_humidity_constant` (`g/kg`), and the four fuel-property
constants `sulfur_switch_ppm`, `sulfur_reference_ppm`, `sulfur_high_ppm` and
`volume_percent_scale` (`ppm`, `percent`) with `biodiesel_volume_cap` beside them.

**7. Version.** A unit-bearing `const` needs esm ≥ 1.2.0 on the document that
carries it **and on every root that mounts a document expanding to it**.
Measured: a 1.1.0 document that only *imports* a 1.2.0 library with a unit-bearing
constant is accepted, but a 1.1.0 root that *mounts* such a document is refused
(`const_units_version_too_old`), because the assembly is re-validated under the
root's version — the rule the `faq` rename met at `fdd32f1`. So every model
document declares 1.2.0. `spikes/7c` moved with them — all three of
`onroad/model.esm`, `tirewear_mount.esm` and `tirewear_fixture.esm` together,
because the logic half expands `heat_index`, which now carries three unit-bearing
`const`s, and a 1.1.0 root over it is refused. `docs/findings/` stays at 1.1.0;
nothing there expands a unit-bearing constant.

**8. A regression that rule 4 leaves bare takes PURE NUMBERS, and its boundary is
written once.** A typed quantity reaching a bare-coefficient regression is a
dimension error — `-42.379 + 2.049·T` with `T` in `degF` adds a dimensionless to a
temperature — and the honest fix is neither to untype the quantity nor to invent
units for the coefficients. It is to divide the unit out where the regression
begins, and, where the physics gives the RESULT a unit, to multiply it back on
where the regression ends. Both operations are `× 1.0` or `÷ 1.0` in binary64, so
a boundary NEVER moves a number; measured over the whole suite, the log is
identical but for two timing lines.

**Where the boundary goes: in the library template, if there is one.** Then call
sites are unchanged and the boundary is stated in exactly one place.
`lib/meteorology.esm`'s `heat_index` divides its temperature by one `degF` and its
humidity by one `percent`, hands `heat_index_regression` the magnitudes, and
multiplies the result by one `degF` because a heat index IS a temperature in °F.
Ten documents call it and not one of them changed. Where the regression has no
template of its own, the boundary goes at the VARIABLE where the typed chain hands
over, and that variable's `description` says so — `fixtures/process-refueling.esm`'s
`rff_temperature` is `run_temperature / 1 degF`, because NONROAD's three refueling
vapour regressions (`20.3 + 0.81T`, `E·T + F`, `exp(A + B·dT + C·T + D·RVP)`) are
fitted to the Fahrenheit number and MOVES states no unit for any of their
coefficients.

**A boundary also serves a COLUMN that cannot be declared**, which is the other
thing this repository keeps meeting. `noxhumidityadjust.humidityLowBound` is one
column holding 3.0 g/kg on a CFR 86 row and 0.002 mole fraction on a CFR 1065 row;
`fuelformulation`'s `fe_propValue` is one column holding seven properties in seven
units. Neither column can carry a unit, but what MEETS them can: `lib/adjustments.esm`'s
`bounded_specific_humidity` divides the `g/kg` out where the typed humidity reaches
the bound, and `components/fuel_effects.esm`'s two property gathers re-apply
`percent` and `ppm` at the select, because the join that selected property 4 or
property 7 knows which property it selected. The sixth is `lib/fuel_effects.esm`'s
`sulfur_power`, which divides the `ppm` out before the `log` in the high sulfur
arm — the SQL raises the ppm NUMBER to the power, and finding F52 is that the
checker would not have said otherwise. SEVEN boundaries exist in this repository
and each is listed here; an eighth would need a sentence here too. The seventh is
§58's: `nremissionrate.meanBaseRate` is one column holding `g/(hp*h)` on a
pollutant row and `lb/(hp*h)` on the BSFC carrier 9901, so the column carries
neither, and `fixtures/nr-logging-county.esm`'s J12 select and
`runs/nr_logging_county_run.esm`'s chain product each multiply by `1 g/(hp*h)`
where the join has already said which pollutant processes the rows are — the same
shape as `fe_propValue`'s two property gathers, and counted as one boundary with
two sites for the same reason.

**What a boundary costs.** It converts rather than checks, so a wrong unit on the
quantity entering one is not caught: `met_relHumidity` declared `cd` still
validates, because `cd / percent` is a legal quotient and the bare coefficients
downstream make the rest undeterminable. That is the price of rule 4 and it is
why a boundary is the SECOND choice — rule 6's declaration, where the equation
determines the unit from a source, is the first.

**What it bought**, on F44's sweep over every non-dimensionless declaration that
an equation writes (each wrong unit tried alone; "dimension" replaces the unit with
`cd`, "scale" multiplies it by `km/m`). The number of declarations under test is
itself a result, because an annotation is what lets a declaration be non-`1` at all:

| tree | binary | declarations swept | dimension-wrong, silent | scale-wrong, silent |
|---|---|---|---|---|
| before everything | `58d21a1a1` | 71 | 17 | 69 |
| before everything | PR #347 `7704f9621` | 71 | 17 | 16 |
| the const-units pass (§57.1–7) | PR #347 `7704f9621` | 107 | 13 | 12 |
| before this section | `8ac536bf0` | 71 | 14 | 13 |
| after this section | `8ac536bf0` | 189 | **11** | **10** |
| after the drive-cycle pass (§57.9) | `8ac536bf0` | 317 | **8** | **8** |
| both passes merged (§57.9 and §58 together) | `8ac536bf0` | **340** | **14** | **14** |

**The fixtures are the part to read.** They carried 10 swept declarations before
this section and carry 121 after, and not one of the 121 is silent in either arm:
every temperature, humidity, heat index, temperature-adjustment term and A/C
activity term in every fixture is now caught if it is declared wrong. The 11 and
10 that remained at THIS measurement — rule 9 re-measured them to 8 and 8 — are
all in `components/` and `runs/` (57 and 58 caught of 68), and
each is one of four things: `10^x` with a symbolic exponent, §4.8.3
(`met_saturationVaporPressure`); inline data with no checked consumer, rule 3
(`act_medianLifeFullLoad`, `lomd_linkAvgGrade`, `somd_bandMinSoakTime`,
`somd_bandMaxSoakTime`); a quantity ENTERING a boundary, rule 8's cost
(`met_relHumidity`); or a product `mph_to_meters_per_second` and
`short_tons_per_gram` have not been able to type, rule 6's table
(`lomd_speedMs`, `lomd_accelerationMs`, `lomd_vsp`, `out_emissionQuant`,
`chainEmissionGrams`).

A declared unit never checks the VALUE — `const(0.4470, "m*h/(mi*s)")` is accepted —
or an affine offset: the 273.15 and the 32 are checked as temperatures, not as the
right temperatures.

**9. A factor that CANCELS is typed by typing its chain, and the step a schedule
takes is a number somebody has to write down.** `mph_to_meters_per_second` was the
harder of rule 6's two bare constants, and the reason was not that its unit was
uncertain: `m*h/(mi*s)` is exactly what 0.44704 is. It is that the registry
resolves it to DIMENSIONLESS at scale 3125/1397, so the annotation checks nothing
on its own and refuses fourteen documents whose speeds are declared `1`. A scale
factor is typed by typing what it multiplies — 283 declarations across twelve
documents here — or it is not typed at all.

**The error rule 6 predicted, and its cause.** With the constant annotated and
nothing else moved, `components/link_operating_mode_distribution.esm` equation 30
is refused `length*time^-2` against `length*time^-1`: `lomd_accelerationMs` is
`(speed[t] − speed[t−1]) × 0.44704`, which is a `m/s`, and it is declared and used
as a `m/s^2`. The missing thing is not a unit, it is a NUMBER. `driveschedulesecond`
holds one row per second, so a backward difference of two consecutive rows is a
speed change over ONE SECOND, and it is that second — never written down anywhere
in this port, and not in the SQL either — that makes the difference an acceleration.

**So it is written down, once, as a constant with a unit.** `lib/drive_cycle.esm`
gains `drive_schedule_time_step`, a `const` 1.0 declared `s`, and
`per_schedule_second`, the one-parameter template that divides by it. Every
backward difference of two schedule seconds in the repository now goes through
that template: the three `At` differences and the VSP acceleration in the
component, and `*_acceleration`, `*_priorAcceleration`, `*_prior2Acceleration` and
`*_accelerationMs` in each of the ten onroad fixtures and in
`onroad/model.esm`. Dividing by exactly 1 is exact in binary64 for
every finite value, for an infinity, for a NaN and for a negative zero, so the
suite's log is identical but for two timing lines — the same cost rule 8 measured.

**A template and not a bare `÷ 1.0` at each site**, for the reason rule 1 gives:
the step is one fact about `driveschedulesecond`, its `description` is where that
fact is stated, and forty-odd call sites saying `per_schedule_second` cannot drift
from it where forty-odd naked `1.0`s could. **It is NOT a rule 8 boundary.** A
boundary divides a unit OUT so that bare coefficients can be reached, and pays for
it by not checking what enters; this multiplies a real physical interval IN and
makes MORE things checkable. The repository still has exactly six boundaries and
rule 8's list is still complete.

**A per-cent divisor is a conversion, not a hundred.** `grade_sine` was
`sin(atan(grade/100.0))` with a bare 100, and a bare divisor makes the quotient
undeterminable however the grade is declared. `full_scale_percent` is
`const(100.0, "percent")`, which the registry resolves to 1, so `grade / 100 percent`
is the dimensionless tangent `atan` wants and not a second hundredth —
the trap a literal `100` "in per cent" would have walked into. With it,
`grade_acceleration = gravity_m_per_s2 / mph_to_meters_per_second × grade_sine`
comes out `mi/(h*s)`, which is the unit
`docs/link-operating-mode-distribution.md` §2.3 states for `At0`; that is what
makes `lomd_at0`, `lomd_at1` and `lomd_at2` declarable at all, and all three are
caught in both arms.

**The road-load polynomial's coefficients ARE declared, and rule 4 is the reason
rather than an exception to it.** Once `speed_ms` is `m/s`, `vehicle_specific_power`'s
`(A·v + B·v² + C·v³ + M·v·a) / F` no longer type-checks with A, B, C, M and F all
declared `1`: four addends, four different dimensions, and no undeterminable
literal to hide behind. Rule 4's test settles which way to fix it, and it says
DECLARE. VSP's result unit is sourced — kW/tonne, in
`docs/link-operating-mode-distribution.md` §2.3 and
`link_op_mode_distribution.rs:320` — and the polynomial is in ONE variable, `v`,
since the acceleration is `v`'s own backward difference. That fixes all five
uniquely and from outside the equation: `sourceMass` and `fixedMassFactor` are the
same vehicle's mass in `tonne`, which makes `M·v·a/F` come out `m^2/s^3` — and
`m^2/s^3` IS `kW/tonne`, at scale 1, which is the check that the reading is right
rather than merely self-consistent. The other three then follow as `kW*s/m`,
`kW*s^2/m^2` and `kW*s^3/m^3`. This is the same shape as rule 4's `A + h(B + Ch)`:
one variable and a unit a source states, so the coefficients are declared and
CHECKED rather than divided out at a boundary. It is what moves `lomd_vsp` and the
fixtures' `dss_vsp` from silent to caught, and it brings `operatingmode`'s four
band bounds with it (`kW/tonne` on the VSP pair, `mi/h` on the speed pair), because
a half-open range test compares them against the typed quantity.

**Two more the typing found, both measured the same way — remove the fix, re-validate.**
Rule 6 named one defect (`*_accelerationMs`); there were three.

| what refuses | how it was measured | what it is |
|---|---|---|
| `lomd_at0`, `lomd_at1`, `lomd_at2`: `Incompatible dimensions in '+': length*time^-1 vs length*time^-2` at equations 26, 27 and 28 | the `per_schedule_second` wrap taken back off the three `At` differences, everything else left in place | the SAME missing one-second step, in the mi/h domain instead of the m/s one: the SQL adds `speed[t] − speed[t−1]` to `9.81/0.44704 · sin(atan(g/100))`, a speed to an acceleration, and this port copied it faithfully. It only becomes visible once `full_scale_percent` makes `grade_sine` dimensionless, so rule 6 could not have seen it |
| `dss_vsp` in a fixture: three `Incompatible dimensions in '+'`, `length^3*time^-3` against `length^2*time^-3` against `length^2*time^-2` against `length*time^-1`, at its equation and its variable | the five `sourceusetypephysicsmapping` declarations put back to `1` in `fixtures/process-tirewear.esm` | five wrong declarations, not one: `rollingTermA`, `rotatingTermB`, `dragTermC`, `sourceMass` and `fixedMassFactor` are not dimensionless, and with a typed `speed_ms` the road-load polynomial adds four different dimensions. This is rule 6's ordinary case — correct the declaration — and the units are the ones the paragraph above derives |

**Where this pass STOPS, and why the line is there.** The average-speed-bin chain —
`avgspeedbin.avgBinSpeed`, `driveschedule.averageSpeed`, the bracketing speeds and
`act_averageSpeed` — is still declared `1` although every one of their descriptions
says mph. Nothing in the 0.44704 chain touches them: they are compared only against
each other. Typing them would be a different pass, because `act_averageSpeed`'s one
consumer is S8, `SHO = VMT / averageSpeed`, and that types `act_vmt` as miles and
`act_sho` as hours and then walks into the emission chain behind them. A pass is
bounded by what the annotation it is FOR actually refuses, and a chain left
untyped is a smaller debt than a chain typed halfway.

**Re-measured**, same harness, same binary `8ac536bf0`, in a worktree:

| | swept | dimension-wrong, silent | scale-wrong, silent |
|---|---|---|---|
| before this rule | 189 | 11 | 10 |
| after this rule | **317** | **8** | **8** |

The fixtures go from 121 swept to 241 and stay at zero silent in both arms;
`components/` and `runs/` go from 68 to 76 and from 57/58 caught to 68 caught of
76 — every declaration those two directories write that is not one of the eight
below. The eight are the same four kinds rule 8 named, minus the two entries
`mph_to_meters_per_second` was responsible for: `met_saturationVaporPressure`
(`10^x`, §4.8.3); `act_medianLifeFullLoad`, `lomd_linkAvgGrade`,
`somd_bandMinSoakTime` and `somd_bandMaxSoakTime` (inline data with no checked
consumer, rule 3); `met_relHumidity` (entering a boundary, rule 8's cost); and
`out_emissionQuant` and `chainEmissionGrams`, which are `short_tons_per_gram`'s
row in rule 6's table and are all that is left of it. The sweep reads
`components`, `lib`, `runs` and `fixtures` and not `spikes`, so
`onroad/model.esm`'s 25 declarations are typed but not swept; they are
the same 25 the fixtures carry.

## 58. The NONROAD emission chain is a MASS, and what stopped it from being one was a sentence that had been false for a week **[EarthSciAST `c31ea106d`; 33 declarations, 5 annotated `const`s, one boundary, two upstream gaps]**

§57.6 left two constants bare, `short_tons_per_gram` (CVTTON, 1.102311e-06) and
its inverse, with a measurement: annotate them and `emissionShortTons` is refused
BOTH as `1` and as `short_ton`, because the ten-factor NONROAD product upstream is
dimensionless factor by factor. The measurement was right. Its diagnosis — that
`adjustmentTime`, `monthDayFactor` and `unitConversionFactor` "have no unit MOVES
pins" — was wrong on all three, and the thing that actually blocked the chain was
**§11's bullet, `hp is not a unit the registry knows`**, which stopped being true
at EarthSciAST `c31ea106d` on 2026-09-10 (`mi`, `lb`, `hp`, `gal` — added, its
commit message says, because they are "the units MOVES is written in"; `short_ton`
had landed on 2026-08-20). Both are in `8ac536bf0`, the binary §57 was measured
against. The stale bullet was still being cited by TEN variable descriptions, by
the two NONROAD fixtures' catalog notes and by §57.6's own table — twelve copies
of one fact about a registry — so nobody re-asked the question. **The rule this section is: when a declaration is blocked
by a missing unit, the blocker is a fact about a registry that changes, and it
belongs in ONE place with a date, not restated in every description that suffers
from it.**

### 58.1 The chain, factor by factor, with the source for each

`clcems.f`'s product for one (SCC, hp point, model year, technology, pollutant),
in the engine's own factorisation (`exhaust.rs:1079-1083` then `:1201-1208`,
`:1227`; docs/nonroad-logging-county.md §2.6):

| # | factor | unit | where the unit comes from |
|---|---|---|---|
| 1 | `emissionFactor` (nremissionrate.meanBaseRate) | `g/(hp*h)` | the rate's own unit code, `G/HP-HR`, which `unitcf.f` dispatches on and `unit_code_for` PANICS rather than defaults on (`nonroad_loader.rs:217-234`). **Not declared on the column** — see §58.4 |
| 2 | `unitConversionFactor` (cvttmp) | `hp` | `unitcf.f`'s own docstring: the `G/HP-HR` branch "converts g/hp-hr → g/hr by multiplying by `hpavg * faclod`" (`exhaust.rs:228-236`). `hpAvg` is `nrsourceusetype.hpAvg` in horsepower and `loadFactor` is a fraction |
| 3 | `deteriorationFactor` | `1` | `1 + A·min(detage, cap)^B`, and `detage` is the FRACTION of median life consumed — `(idxyr+1)·hours·LF / medianLifeFullLoad`, hours over hours. `emissionCap` is a cap on that fraction |
| 4 | `adjustment` (adjems) | `1` | `exp(a·(T−75))·(1 − c·oxy)`: a multiplicative correction |
| 5 | `adjustmentTime` (adjtime) | `1` | `1/ndays`, and `ndays` is a COUNT of calendar days summed out of `MONTH_DAYS` (`daymthf.rs:72-125`, `common.rs:987-1010`) |
| 6 | `hoursUsedPerYear` (acttmp) | `h` | `nrsourceusetype.hoursUsedPerYear`, a DURATION — see §58.2 |
| 7 | `monthDayFactor` (tpltmp) | `1` | `mthf × 7 × dayFraction`: `monthFraction` is the share of the year's activity in the month and `dayFraction` the share of a week's on one day of that type, and the 7 is a count of days |
| 8 | `countyPopulation` | `1` | a count of equipment units |
| 9 | `modelYearFraction` (modfrc) | `1` | a share of the population |
| 10 | `techFraction` (tchfrc) | `1` | a share of a model year's equipment |
| 11 | `short_tons_per_gram` (CVTTON) | `short_ton/g` | `consts.rs:350-355`, "grams-to-short-tons"; `nonrdprm.inc` |

`g/(hp*h) × hp × h × 1⁷ × short_ton/g = short_ton`, exactly, and the intermediate
the engine names is one too: `emstmp` is `g/h`, grams per hour of operation.

**What the registry makes of it.** `short_ton/g` is DIMENSIONLESS at scale
45359237/50, which is what §57.6 measured and read as a refusal. It is not one:
multiplied onto a mass in `g` it gives a mass at the short ton's scale, and since
PR #339 compares scale as well as dimension, `emissionShortTons` declared `g`,
`tonne`, `1` or `cd` is refused — all four measured.

### 58.2 `hoursUsedPerYear` is a DURATION, and that is the one judgement call here

The column's name says "per year" and the chain never divides by a year. Two
readings close:

* **`h`** — the hours this equipment ran in the accounting year. Then the product
  is grams, the annual-to-typical-day step is a dimensionless FRACTION (both sides
  are amounts of grams), and nothing is unwritten.
* **`h/yr`** — a rate. Then the product is `g/yr` and the chain needs an unwritten
  `× 1 yr` to become the daily mass it is, and that year would be the registry's
  Julian 365.25 days against NONROAD's calendar 365 (§57.5).

`h` is taken, and the source settles it rather than the convenience: `detage =
(idxyr+1)·hours·LF / medianLifeFullLoad` is the fraction of median life consumed
(`modyr.rs:308-317`, and `det_ageCap` is `emissionCap`, "a cap on the FRACTION OF
MEDIAN LIFE"), `medianLifeFullLoad` is in hours, and a fraction of it requires
hours over hours. `components/deteriorated_emission_rate.esm` had already declared
it `h` on exactly that reasoning.

**The same column is `h/yr` in `components/age_distribution.esm`, and that is not
an inconsistency to fix.** `scrptime.f` divides the lifetime hours by it to get a
number of YEARS, which is the one place in the chain where the year is real; the
fixtures spell the same quantity the other way, as a dimensionless
`point_medianLifeYears`, and both are right about their own equation. What is not
allowed is to read the column as a rate in the emission product, because then the
year never cancels.

### 58.3 An `ifelse` takes the units of its FIRST branch, and never looks at the rest

**Superseded by §105.** esm-spec §4.8.6 checks every branch, so the multi-unit
selector this section describes is a mismatch, and both templates it names were
rewritten.

Measured on `8ac536bf0` with a three-line probe: `ifelse(c, hp_avg·lf, dens)` with
`dens` declared `kg/m^3` validates with the left-hand side declared `hp` and is
refused declared `kg/m^3` or `m`. So a branch that disagrees is not a conflict; it
is invisible.

That is convenient here and it is also a trap, so the rule is: **the unit of a
code-dispatched conversion goes at the CALL SITE, where the code is fixed, and
never on the template.** `unit_conversion` genuinely returns `hp` on the g/hp-hr
branch, `gal/h` on the g/gallon branch and a dimensionless 1 on the pass-throughs;
`annual_activity_hours` returns `h`, then hours times a bare day count, then
`1/h`. Every call site in this repository binds `emission_unit_g_per_hp_hr` and
`activity_unit_hours_per_year`, and declares `hp` and `h`. The other branches are
stated in the library's `description` and are NOT checked — and would not be even
if they were wrong.

### 58.4 The seventh boundary: one rate column, two units

`nremissionrate.meanBaseRate` holds `g/(hp*h)` on a pollutant row and
`lb/(hp*h)` on the BSFC carrier, polProcessID 9901, which `clcems` reads for the
CO2 carbon balance and the SOx rewrite. Both are spellable now; the COLUMN still
is not, and this is §57.8's `fe_propValue` shape exactly. So the column stays `1`
and the unit is applied where a join has already selected which pollutant
processes the rows are: `fixtures/nr-logging-county.esm`'s J12 and
`runs/nr_logging_county_run.esm`'s chain product each multiply by
`const(1.0, "g/(hp*h)")`. One boundary, two sites, `× 1.0` in binary64, no number
moved. `components/exhaust_rollup.esm` needs no boundary: 9901 is absent from its
factor rows and its `emf_emissionFactor` is declared directly.

Two `"units": "1"` are written under §57.2's "only where it is measured to make an
equation checkable", and both were measured:

* the numerator of `grams_per_short_ton`. `1.0 / const(short_ton/g)` with a BARE
  one is undeterminable, and `out_emissionQuant` declared `short_ton` validates.
  With the one declared it is refused.
* the `+ 1` in `deterioration_age`. It matters only where the caller binds
  `age_index` to a BARE literal, and the one such call site is
  `runs/nr_logging_county_run.esm`'s `age_index: 0` — measured on a four-line
  probe, `((0 + 1)·h·1)/h` declared `cd` is silent with the one bare and refused
  with it declared. Where the caller passes a DECLARED index the quotient was
  already determinable: `components/deteriorated_emission_rate.esm`'s `detAge`
  refuses `cd` both before and after, because its `ageIndex` is declared `1` and
  a bare literal added to a declared operand takes that operand's unit. So this
  annotation is inert in this repository today — F54 makes the run unmeasurable —
  and it is written because it is the LIBRARY-level fix, one place instead of
  one per call site (§57.1).

### 58.5 What is still not checked, and it is not a missing unit

Two holes, both upstream and both measured; §58.6 counts what they cost.

**The mount edge.** `runs/nr_logging_county_run.esm` is declared throughout and
**none of it is checked**, because declared units do not cross a `{ref}` mount
edge: an expression
that reads `Activity.act_annualHours` or `Factors.zeroHourRate` is undeterminable
however the leaf declared it. Measured both ways in the same document — a product
of two LOCAL variables is caught declared `cd`, and the same declaration on a
product of mounted ones is silent. That is finding **F54**, and it is also the
real reason `chainEmissionGrams` is dim-silent; F44's list gives a different one
(`min(age, cap)^B`'s symbolic exponent), and that reason is wrong — a power with a
DIMENSIONLESS base is determinable, measured. The run's declarations are written
anyway: they are correct, they document the chain, and they begin checking the day
the mount edge carries units.

**A `faq` `filter`'s operands.** The hp bin test is `hpMin <= hpAvg <= hpMax`
written as a `filter` — §3's rule, the SCC and the tech are `join.on` clauses and
the horsepower is a predicate — and a filter is not unit-checked. Measured with a
nine-line probe: `filter: index(edge, i) <= val` with `edge` declared `cd` and
`val` declared `hp` validates, while the identical `<=` as an equation's
right-hand side is refused (`Incompatible dimensions in '<=': luminosity vs
length^2*mass*time^-3`). So the four bin-edge columns are declared `hp` because
they ARE horsepower, not because anything checks them, and their descriptions say
so. This is wider than the mount edge — every `filter` in the corpus is unchecked
— and it deserves a finding number, which this pass was not allocated one to
give.

### 58.6 The sweep, and why the silent count went UP

F44's sweep (every non-dimensionless declaration an equation writes, each wrong
unit tried alone; "dimension" replaces the unit with `cd`, "scale" multiplies it
by `km/m`), on `8ac536bf0`:

| tree | declarations swept | dimension-wrong, silent | scale-wrong, silent |
|---|---|---|---|
| §57 (before this section) | 189 | 11 | 10 |
| after this section | **212** | **17** | **16** |
| this section merged with §57.9's drive-cycle pass | **340** | **14** | **14** |

**Merged with §57.9, the tree sweeps 340 declarations and 14 are silent in each arm** — measured on the merged tree, not added up from the two rows above: §57.9's eight, less `out_emissionQuant` which this section catches, plus the seven this section writes. The fixtures are 249 swept and 0 silent. Each row above is what its own pass measured on its own tree, and neither is the number the repository has now.

**One declaration left the silent list and it is the one this section is about**:
`out_emissionQuant` in `components/movesoutput_aggregation.esm`, which was
declared `g` and checked against nothing, now refuses `short_ton`, `1`, `tonne`
and `cd`. In the fixtures the coverage is unchanged at 129 of 129 caught, and the
twelve that `fixtures/nr-logging-county.esm` contributes include the three this
section added.

**Seven arrived, and every one of them is a declaration that did not exist
before** — the sweep can only count a non-`1` declaration, so writing one is the
only way to be counted silent. They are two kinds and neither is a unit this
repository is unsure of:

* `chainAnnualHours`, `chainUnitConversion` and `chainEmissionGrams` in
  `runs/nr_logging_county_run.esm` — finding **F54**, units do not cross a
  `{ref}` mount edge. Three of the seventeen are one upstream gap.
* `act_hpAvg` and the four hp bin edges `mix_hpMin`, `mix_hpMax`, `emr_hpMin`,
  `emr_hpMax` — **a `faq` `filter`'s operands are not unit-checked.** Measured
  with a nine-line probe: `filter: index(edge, i) <= val` with `edge` declared
  `cd` and `val` declared `hp` validates, and the identical `<=` written as an
  equation's right-hand side is refused (`Incompatible dimensions in '<=':
  luminosity vs length^2*mass*time^-3`). The hp bin test is a `filter` in every
  aggregate that reads it — deliberately, §3's rule that the SCC and the tech are
  `join.on` clauses and the horsepower is a predicate — so the four edges are
  declared because they ARE horsepower and not because anything checks them.
  `act_hpAvg` is §57.3's case, inline data whose consumer is in another document.
  **This is finding F55.** It is a
  second silent hole of the same shape as F54 and it is wider: every `filter` in
  the corpus is unchecked, not only these.

So the honest reading of 11 → 17 is: one real gain, three upstream mount-edge
silences, one inline-data silence, and two upstream filter silences — and the
eleven that were silent before are still silent for the reasons §57.8 gives,
less `out_emissionQuant`.

## 59. An execution database is the default database already cut to the run, so a document written against one leaves its selections unsaid **[PLAN.md step 7c′; 38 tables, 36 drop-ins, 1 defect, 2 generators]**

Every fixture in this repository reads a `moves.rs` snapshot of a MOVES
EXECUTION database: the tables MOVES copied out of the default database for one
run, already filtered to that run's county, year, month, hour, day, source
types, road types and pollutant-processes. That is a convenience with a cost,
and 7c′ is what it cost.

**The cost is that a selection can be absent and nothing says so.** The document
still gets the right number, because the file has one row. Point the same
document at the national table and the sum it was writing becomes a sum.

`onroad/model.esm` had exactly one of these, and it took the shape
you would expect — the cheapest thing to write:

```json
{ "op": "faq", "semiring": "sum_product", "output_idx": ["k"],
  "ranges": { "k": { "from": "run_rows" }, "l": { "from": "link_rows" } },
  "expr": { "op": "index", "args": ["lnk_countyID", "l"] } }
```

Σ over `link`, which is correct precisely while `link` has one row. The default
database's `Link` has 22,610, and this reads county **710047702** and state
**710047** — Σ countyID over all 22,610 link rows, over 3,230 distinct
counties, divided by 1000 for the state. Nine digits where a county has five,
and no row of any table has ever held it. The
repair is a `join.on` against the runspec's county and road type, which is what
§3 has asked for all along; what was missing was any reason to notice.

### 59.1 The measurement that scopes the problem, and it is small

Repoint ONE `url_template` at the national file, re-emit the fixture's 375 rows,
compare bytes. Then all of them at once.

| | tables | verdict |
|---|---|---|
| in both databases, swapped one at a time | 37 | **36 byte-identical**, `link` the exception |
| in both, swapped together | 37 | byte-identical |
| plus `sourceUseTypePhysics` (see below) | 38 | byte-identical, 40 s |
| not in the default database at all | 11 | ten runspec selections and the expected output — the fixture's, not the domain's |

So the joins were already doing the narrowing in 36 places out of 37. **This is
the equi-join gate collecting its dividend** (PLAN.md §1.3 and §7.3): reading
nationally and joining is not a tolerated cost, it is the design, and the one
place it failed is the one place the document had not written a join.

### 59.2 A table MOVES synthesises is not a table to acquire

Two of the eleven absent tables were not runspec selections. Neither needed a
workaround, and the rule they share is worth stating: **when the default
database does not ship a table, find out what MOVES builds it FROM, because the
answer is usually a table it does ship and an equation this port can write.**

* `sourceUseTypePhysicsMapping` is `sourceUseTypePhysics` with `sourceTypeID`
  renamed and two columns added that this document never reads
  (`moves.rs default_db_setup.rs::populate_source_use_type_physics_mapping`).
  Cost of reading the real table instead: one `file_variable`.
* `evSalesFraction` is `evsales / sales` over the age-0 slice of four tables the
  document already ingests. Cost: three equations, and it reproduces the
  snapshot's 115 rows exactly from either database.

The alternative — generating those two tables into Parquet beside the database —
would have put model logic in a script, which is what CLAUDE.md forbids. It would also have been more work.

### 59.3 Write the join the SQL has, then factor it

`evSalesFraction`'s generator is one statement over four tables, and the first
translation was one `faq` over six ranges. **It did not finish in three
minutes.** Factoring the per-sample-vehicle weight into its own variable —

```
svp_salesWeight[v]   = Σ_{sty, stad}  population × age-0 fraction × stmyFraction
coh_salesAllFuels[c] = Σ_{svp, rc}    svp_salesWeight[v]
```

— replaces one six-range join with two four-range ones and costs **0.3 s**. The
factored form is also the better document: `svp_salesWeight` is a quantity with
a name and one definition, where the six-range form repeated the same product
three times (all fuels, electric, presence).

The rule is not "faq is slow at six ranges". It is that a join whose driving
relation is 6,068 rows and whose other four are 33,579, 819, 164 and 10 has a
plan, and an intermediate that pins the plan is worth one variable.

### 59.4 The runspec belongs to the fixture, and the format leaves no choice

`moves-onroad.esm` declares 38 tables and mounts the logic. It **does not load
alone**: it names ten runspec sources it does not declare, so `esm validate`
refuses it the way it refuses the 7c logic half, and `run-tests.sh` asserts that
refusal two-sided.

A domain document COULD have shipped a default runspec — except that it could
never then be replaced. `SubsystemRef` carries `bindings`, `model`,
`index_set_rename` and `expression_template_imports` and nothing else (§54), and
a child's `data_sources` merge UP (§49); **there is no channel for a mounting
document to override a mounted one's `data_sources`**. A default runspec would
be a permanent one. So the runspec is the per-fixture document's, which is where
§7.1 wanted the configuration anyway — the format and the plan agree here, and
it is worth recording that the agreement is not a coincidence of taste.

### 59.5 What is still snapshot-shaped, and why it is not a workaround

The ten runspec selections are read from the snapshot's own `runspec*` Parquet
rather than written in the document as numbers. The logic INGESTS them
(`update.kind: "data"`), which is what sizes the axes they are the extent of,
and an ingesting document holds exactly one model (F45) — so a per-fixture
document has nowhere to put an equation stating them inline. Stating a runspec
in the document means expressing those selections as metaparameters instead,
which changes how eleven variables are declared and is a separate pass.

Until then the honest description is: **the data comes from the default
database, and the RUNSPEC comes from the snapshot.** The first is what 7c′
claimed and measured; the second is what it did not.

## 60. A pollutant-process the RunSpec selects is not one MOVES emits, and the output relation is not a rectangle **[PLAN.md step 7d; 3 of 3, then 1 of 3; 250 rows, 25 fields, byte-identical by two routes]**

`process-tirewear` selects 9101, 10710 and 11710 and `MOVESOutput` has 375 rows:
3 × 125 × 1. Every other onroad RunSpec in the corpus selects 9101, 9102 and
9190 — Total Energy Consumption on running exhaust, start exhaust and extended
idle — and `MOVESOutput` has **250 rows, not 750**. The two are the same
document's output axis, and one of them is a rectangle by accident.

The mechanism is a join, and `moves.rs` states it in a comment before it does
it (`baseratecalculator/mod.rs:762-781`): `BaseRateGenerator` emits each
process's rates on that process's natural road type — running exhaust on the
selected on-road types, **start exhaust on off-network `roadTypeID` 1** — and
`BaseRateCalculator` then joins its rate rows to `runSpecRoadType`. A RunSpec
that selects road type 4 alone discards both off-network blocks entire, and
`baseRateOutput` comes back empty for them.

**The rule is a column, not a list of process ids.** `emissionProcess` has
`occursOnRealRoads`, which is `Y` for running exhaust, brake wear and tire wear
and `N` for start, extended idle, APU and every evaporative process. So the
model reads it, and the four equations that follow are the calculator's own
join written as one:

```
rspp_occursOnRealRoads   emissionprocess, joined on the process half of the id
rspp_rateRoadTypeID      the run's road type, or the OffNetwork enum's 1
rspp_isEmitted           join.on against runspecroadtype -- §20.4, not a filter
rspp_emittedPrefix       an inclusive prefix count (§22)
rspp_outputOrdinal       isEmitted × prefix: 1..n over the survivors, 0 otherwise
```

`rt_outputOrdinal` then reads the **emitted** block number rather than the
selected one, and `output_rows` is sized by `n_outputPolProcess` rather than by
`n_runspecpollutantprocess`.

### 60.1 The declared number is the one no table states, and it is recomputed rather than trusted

`n_outputCohort` was already this shape: 125 cohorts reach MOVESOutput, which
ones is a result of the chain, and `cohortSurvivorCount` recomputes it.
`n_outputPolProcess` is the second, and it needs a **relay**: `bindings` closes
a metaparameter the *referenced* document declares and a mounting document can
offer only an expression over its own (§49.1), so `moves-onroad.esm` declares
the name as well and passes it down. Measured: binding 2 at the outer edge
emits 250 rows from a chain that emits 375 at 3.

**What that buys is a check, not a shortcut.** `outputPolProcessCount`
recomputes the count from `rspp_isEmitted`, and `tools/check-runspec-shape.py`
requires three things of every `runspecs/` document at once:

```
rows == outputPolProcessCount × cohortSurvivorCount × day types
distinct (pollutantID, processID) == outputPolProcessCount
distinct (modelYearID, fuelTypeID) == cohortSurvivorCount
```

### 60.2 What `expand-day` discriminates, and — §23 — what it does not

**Discriminated.** The day axis at both of its values: `runspecday` is 2 rows
where every other run in the tree has 1, and **nothing in the model changed to
accept it** — `n_runspecday` is discovered from the source's own extent, so the
activity relation, the hour-day key and the output relation all doubled by
themselves. And the block count: without `n_outputPolProcess` the output
relation would be 750 rows and every comparison would fail.

**NOT discriminated, and this is the part worth writing down.** `expand-day`'s
one surviving pollutant-process is also its **first**, so the renumbering
`rspp_emittedPrefix` performs is the identity on it. Deleting the off-network
arm of `rspp_rateRoadTypeID` — the probe `no-road-type-filter` does exactly
that — leaves the emitted relation **byte for byte unchanged**: the two extra
blocks claim output ordinals 126–375, the relation has 250, and nothing
matches. Measured, not assumed; the probe was written expecting the numbers to
move and they did not.

So the probe is checked against the *recomputed shape* instead, where it does
bite: `outputPolProcessCount` goes 1 → 3 while 250 rows are emitted. A run whose
survivors are not a prefix of its selections would move the numbers as well —
`expand-criteria` selects 101, 102, 201, 202, 301, 302, 3101 and 3102 and emits
pollutants 1, 2 and 3 on process 1, which is positions 1, 3 and 5 of eight. It
is not ported, and until it is, this section is the record that the prefix
renumbering is exercised by construction and not by a fixture.

### 60.3 A second RunSpec costs eleven `url_template`s and one binding

That is the whole of `runspecs/expand-day.esm` against
`runspecs/process-tirewear.esm`: the eleven data-source keys are the same
strings, the notes differ because the runs differ, and the models block differs
by `"bindings": {"n_outputPolProcess": 1}`. 207 lines.

| | lines | data sources | equations |
|---|---|---|---|
| `fixtures/expand-day.esm` — the same run, inlined | 14,603 | 46 | 196 |
| `runspecs/expand-day.esm` — the same run, over the domain model | **207** | 11 | 0 |

The inlined document remains in the tree as a snapshot-fed module test
(PLAN.md §7.6) and it is what makes this a cross-check rather than a claim:
**the two emit the same 250 rows over all 25 shared fields, byte for byte** —
one from the run's own execution-database snapshot through 196 equations
written out in full, the other from the national default database through a
model written for a different process. 147 of those 196 equations were already
byte-identical to `fixtures/process-tirewear.esm`'s, which is what the
domain model is instead of.

## 61. One selected county made the county a SCALAR, and the fix is 30 variables out of 425 **[PLAN.md step 7d; 3 counties, 3 states, 375 rows, worst cell 1.140e-05]**

Every RunSpec in this repository selected one county, so the model wrote the
county as a property of the run: `run_countyID`, `run_zoneID`, `run_linkID` and
`run_stateID` were shaped over `run_rows`, the one-row carrier relation that
§20.4's joins use. That is the same mistake §59 records one level down —
a table that arrives with one row lets a document read where it meant to
index — and it hid for the same reason: nothing ever had two.

`expand-counties` selects Los Angeles, Cook and Washtenaw, and MOVES emits
**375 rows = 1 pollutant-process block × 3 counties × 1 day type × 125
cohorts**.

### 61.1 What varies with the county is 30 variables, and the list is the model

The measurement is the *denominator*. 30 of the model's 425 variables gained
the axis; three more were added to carry it; **395 did not**, and that is not an
accident of the port — it is where MOVES puts the county:

| gained the axis | why |
|---|---|
| `run_countyID`, `run_zoneID`, `run_linkID`, `run_stateID`, `run_linkRoadTypeID` | read back from `Link` through the county/road-type join |
| `run_heatIndex`, `run_temperature` | `ZoneMonthHour` is keyed by zone, and the zone is the county's |
| `run_acActivityTermA/B/C`, `run_acActivityRaw`, `run_acActivity`, `run_evTemperatureIsSuppressed` | the quadratic's coefficients do not vary with the county; they are ADDED to a heat index that does, so they are broadcast rather than left a shape the sum cannot take |
| `run_shoAllocFactor`, `act_sho` | VMT is NATIONAL; `zoneRoadType.SHOAllocFactor` is what makes it a county's |
| `coh_usedFraction`, `coh_acFactor` and the `rt_`/`rtMode_`/`rtDay_` stack above them | `fuelUsageFraction` is keyed by county — E85 is not available everywhere — so the same cohort grid is re-attributed differently in each |

| did NOT | why |
|---|---|
| the drive cycle and the operating-mode family, 60 variables between them | `driveSchedule` is national and speed-bin keyed, and not one of the 60 carries the county axis |
| `emissionrate`, `pollutantProcessModelYear`, `sourceTypeModelYear` | rates are national |
| `coh_isSelected`, `coh_rank`, `cohortSurvivorCount` | which cohorts SURVIVE is `stmyFraction > 0`, which is national — so all three counties emit the same 125 |
| `act_vmt`, `act_averageSpeed`, `act_travelFraction` | `HPMSVtypeYear` and `avgSpeedDistribution` are national; the county enters only at the allocation |

### 61.2 The output relation is four levels, and the county is the second

```
output_rows = n_outputPolProcess × n_runspeccounty × n_runspecday × n_outputCohort
```

decomposed from the aggregate's own loop symbol, county-major over day-major
over cohort. With `n_runspeccounty` at 1 the decomposition is arithmetically the
one it replaced, which is why `process-tirewear` and `expand-day` emit their
375 and 250 rows **byte for byte unchanged** — the check that the axis was added
and nothing else was.

`rsc_ordinal` is the county relation's own row ordinal, exactly as `day_ordinal`
is the day relation's, and the output row joins to it by POSITION. Every output
column that varies with the county gains one key pair, `outCountyOrdinal ↔
rsc_ordinal`, on the clause it already had.

### 61.3 What it discriminates: the join 7c′ added, at more than one value

7c′ put a county/road-type join on the four geography columns because the
national `Link` has 22,610 rows and summing them read county 710047702. Until
this run that join was only ever evaluated against a one-county runspec, where
a join returning the FIRST match rather than the MATCHING one would have passed
every check in the suite.

Here it has to return three different links, three different zones and three
different states, and the probe `no-county-join` deletes the output relation's
county key pair and requires the numbers to move. They move into exactly the
7c′ shape one axis up:

| | correct | probe |
|---|---|---|
| `out_countyID` | 6037, 17031, 26161 | **49229** on every row — their sum |
| `out_stateID` | 6, 17, 26 | **49** |
| `out_SHO` (MY 2020, fuel 1) | 8364.19, 2336.69, 260.06 | **10960.94** on every row |

`tools/check-runspec-shape.py` catches it a second way: with the counties summed
the output carries one distinct `countyID`, so 375 rows no longer equal
1 × 1 × 1 × 125.

### 61.4 The worst cell moved, and it is the new county

| run | rows | worst cell |
|---|---|---|
| `process-tirewear` | 375 | 8.128e-06 |
| `expand-day` | 250 | 7.106e-06 |
| `expand-counties` | 375 | **1.140e-05** |

Against a 2e-05 tolerance that is 1.75× headroom where the one-county runs have
2.5×, and the difference is not a new arithmetic — it is that Los Angeles and
Cook carry SHO an order of magnitude larger than Washtenaw's, so the reference's
six-significant-figure column storage lands further from the computed value.
§42.4's rule applies: the number is recorded, not rounded off, and the
tolerance has not been widened.


## 62. The source type is inside the cohort, and the cohort is not the source bin **[PLAN.md step 7d; 44 variables promoted, 125 of 248 rows exact, one root cause for the rest]**

Three of 7d's dimensions have now been widened, and all three found the same
kind of thing: a selection of width one had been hiding a structure. §60 was the
output relation not being a rectangle. §61 was the county being a scalar. This
is the third, and it is two findings deep — one about where the source type
lives, and one about where it does not go far enough.

### 62.1 A discovered axis is cheaper than a declared one, and the cohort grid already spanned it

`run_sourceTypeID` reached **125 of 262 equations** by forward closure, against
geography's 37, and the number was right: 44 variables gained a
`runspecsourcetype_rows` axis. But the expensive-looking half turned out to be
free. `cohort_rows` is `n_agecategory × n_runspecsourcefueltype`, and
`runspecsourcefueltype` carries **(sourceTypeID, fuelTypeID) PAIRS** — with one
source type selected, the distinction between "the fuel relation" and "the
source-fuel relation" is invisible, and `coh_fuelOrdinal` was named for the
invisible half. Renaming it `coh_sourceFuelOrdinal` and reading
`coh_sourceTypeID` off the same row moved no shape at all: the five cohort joins
that reached for the run's single source type read it off the candidate instead.

**So the output relation's shape contract survived.** PLAN.md §7.3.4 had written
down a decision about `output_rows` being sized by a PRODUCT of declared numbers
while a ragged cohort count makes the total a SUM. The sum over source types IS
the cohort survivor count: `coh_rank` densifies whatever survives by an inclusive
prefix count (§22), `cohortSurvivorCount` recomputes the total as one number, and
`output_rows` stays

    n_outputPolProcess × (n_outputCohort × n_runspecday) × n_runspeccounty

with the source type **inside** `n_outputCohort` rather than beside it — 248 at
two source types, 430 at five. The one thing that did change is that
`n_outputCohort` became a number a per-fixture document sets, through the same
`bindings` relay in `moves-onroad.esm` that `n_outputPolProcess` already used
(§49.1). A decision written down before it was made turned out not to be one,
which is an argument for writing them down.

### 62.2 What a source type is keyed by, and what it is not

Per source type: the drive cycle, from `sourceusetypephysics` down. Vehicle-specific
power is computed from that source type's rolling, rotating and drag terms and
its fixed mass factor, so the operating mode each drive-schedule second bins
into, the speed-bin brackets and the operating-mode distribution the rates are
weighted by are all per source type. Also per source type: the HPMS
normalisation group, the analysis-year VMT, the road-type and month VMT shares,
the population and the whole activity relation.

NOT per source type, and this is worth stating because it looks like it should
be: `run_travelGroupTotal`, S3's denominator, is over every (source type, age)
in **this source type's HPMS group** and not over this source type alone.
Normalising over source type 21 by itself is a 2.55× error on every row, and
HPMS 25 is shared with source types 31 and 32 — so a two-source-type run has two
denominators that are not two disjoint sums.

### 62.3 The cohort is (source type, fuel type, model year); the source bin is five columns

`runspecs/pending/expand-fueltype-diesel.esm` emits the right **shape** — 248
rows, 125 under source type 21 and 123 under source type 32, from a declaration
the chain recomputes — and **every one of source type 21's 125 rows reproduces
`MOVESOutput` at worst cell 7.106 × 10⁻⁶**, the same worst cell `expand-day`
reports. Source type 32's 123 are wrong, and there is one cause:

| source type | regulatory classes | (model year, fuel) triples carrying more than one |
|---|---|---|
| 11 | 10 | 0 of 111 |
| 21 | 20 | **0 of 444** |
| 32 | 30, 41 | 333 of 444 |
| 51 | 41, 42, 46, 47 | 333 of 444 |
| 62 | 46, 47, 49 | 222 of 333 |

A MOVES **source bin** is (sourceTypeID, fuelTypeID, modelYearID, regClassID,
engTechID). This model's cohort candidate stops at the first three, and
`coh_regClassID` is a `sum_product` over the matching `samplevehiclepopulation`
rows — so on a two-class triple it returns **71** rather than 30 or 41,
`emissionrate` matches nothing, and the rate is 0. The 23 rows of source type 32
that DO carry a single regulatory class are wrong too, at 0.735, one step back
for the same reason: their E85 activity is re-attributed from a gasoline cohort
whose `coh_regClassID` is the 71, so `coh_usedFraction` finds no partner.

**Source type 21 has one regulatory class for every triple it carries**, which is
why every run in this repository before this one was right by accident. That is
the same sentence §60 and §61 each earned, for the third time in one step, and
the rule it is worth stating once is: **a selection of width one cannot
distinguish a key from a constant, and the model will take the constant.**

### 62.4 `coh_usedFraction`'s self-join needed the source type, and it changed nothing here

The equipped-to-used fuel re-attribution pairs a cohort candidate with the
candidates sharing its source bin, on (model year, engine technology, regulatory
class). At two source types that pairing must also match the source type, or a
passenger car is re-attributed a light commercial truck's activity. The clause
was added and **the numbers did not move**, because source type 21's regulatory
class is 20 and source type 32's are 30 and 41, so the join never crossed. It is
kept because `expand-sourcetype` does cross it: source type 51 carries 41, 42,
46 and 47, source type 62 carries 46, 47 and 49, and source type 32 carries 41.
A guard whose effect is zero on the run that motivated it is worth the line when
the run that needs it is already written.

### 62.5 The join key that cannot be a key

The whole step took two attempts because of F57. A `faq` join key must be a 1-D
column over an axis the aggregate ranges; give it a 2-D one and the clause is
**dropped rather than refused**. `dsa_modeSeconds` joins `om_opModeID` to
`dss_opModeID`, and `dss_opModeID` gained the source-type axis here, so the
operating-mode distribution came back as 1.0 on all 60 modes instead of summing
to 1.0 over 23 — running-exhaust energy 22× to 24× high. The tire-wear
pollutants in the same run stayed exact to 1e-5, because they take the other arm
of an `ifelse` and never read that distribution.

The equality is spelled as a `filter` until EarthSciAST#417 lands, which §20.4
otherwise forbids. **`tools/check-conventions.py` exempts the unspellable CASE,
not the file** — an `==` one of whose operands indexes a variable of arity
greater than one — so the exemption disappears by itself when the key becomes
expressible. That is the shape an exemption should have: it names the reason,
and it expires when the reason does.

## 63. A cohort is what the answer has a row for; a source bin is what the rate table has a rate for **[PLAN.md step 7d; 330 bins exact, 3 of 4 factors right, one key left]**

§62 ended by saying the cohort had to become the MOVES source bin. It did not,
and the reason is worth more than the fix: they are **two relations**, and
collapsing them was the defect rather than the cure.

### 63.1 One is the output's identity, the other is the rate's

A **cohort** is (source type, fuel type, model year). It is what `MOVESOutput`
has a row for — the table has no regulatory-class or engine-technology column,
and `out_regClassID` and `out_engTechID` are two of this document's null
columns. A **source bin** is those three plus (regClassID, engTechID). It is
what `emissionrate` has a rate for, and MOVES packs the pair into the bin id it
keys by.

The relationship is one-to-many and ragged: a passenger car has exactly one bin
per cohort, a light commercial truck two, a refuse truck's diesel eight. So the
model grew a relation rather than a factor —

    cohort_rows      a candidate OUTPUT row
    sourcebin_rows   a candidate RATE lookup, cohort_rows x n_sourceBin
    rate_rows        a pollutant-process x a source bin

— and the eleven columns that were never the cohort's moved to where they
belong: `bin_regClassID`, `bin_engTechID`, `bin_stmyFraction`,
`bin_usedFraction` and the five EV-share columns that hang off the regulatory
class. A rate row now carries BOTH ordinals, `rt_binOrdinal` and
`rt_cohortOrdinal`, and each downstream join takes the one whose relation owns
the column it wants.

### 63.2 A key column must come from the relation that owns it

This is the part that does not survive the collapse. Several rate rows now share
an output row, and every output column was a `sum_product` over the rate rows
whose `rt_outputOrdinal` matched. For `out_emissionQuant` that sum is exactly
the point — an emission IS the sum over a cohort's bins. For `out_modelYearID`
it adds 2017 to 2017 and emits 4034.

So the six key columns read from the relation that owns them instead: the model
year, fuel type and source type from `cohort_rows` through `coh_rank`, the
pollutant and process from `runspecpollutantprocess_rows` through
`rspp_outputOrdinal`. The value columns keep the rate join. **The rule: when a
join becomes many-to-one, audit every aggregate over it for whether its `⊕` was
load-bearing or incidental** — a sum over one row looks the same either way, and
`sum_product` is the default.

### 63.3 A dense grid needs a dense slot, and MOVES has none

A candidate grid enumerates a product. `samplevehiclepopulation` gives a cohort
whatever rows it gives it. `svp_binOrdinal` bridges the two: §22's inclusive
prefix count, gated to the cohort by a JOIN on (source type, model year, fuel
type) rather than by an equality filter, which keeps it O(rows in a cohort)
instead of O(rows squared) over a 16,428-row table. The bin then reads its own
columns back through a four-column lookup on that slot.

`n_sourceBin` is the third declared number in a document that made a point of
having two, and it is checked differently from them. `cohortSurvivorCount` and
`outputPolProcessCount` recompute an EXTENT: too small and the emitted row count
disagrees, which the shape check catches. A slot count one short drops a whole
source bin, and a dropped bin is not a missing row — it is a row whose
emissionQuant is quietly low by that bin's share, which nothing about the shape
would notice. `run_sourceBinsDropped` counts them and is asserted at zero.

### 63.4 Three of four factors, and how you tell which one is left

`expand-fueltype-diesel` went from 123 of its 248 rows returning zero to being
wrong by a factor of between 1.48 and 3.06 on those rows. A ratio is not a
diagnosis, so each factor of an emission was checked against something the run
itself recorded:

| factor | checked against | result |
|---|---|---|
| source-hour activity | the execution database's `sho` | exact, both source types |
| source-bin distribution | `sourceBinDistributionFuelUsage_1_26161_2020` | exact, 330 bins |
| the rank and the shape | `cohortSurvivorCount`, the emitted keys | exact |
| the operating-mode distribution | — | **wrong** |

The execution database a characterization snapshot carries is not only the
run's INPUT — it holds MOVES's own intermediate tables, and an intermediate
relation the model builds can be compared to the one MOVES built. That turned "a
ratio between 1.48 and 3.06" into "everything but the drive cycle is right" in
two measurements.

### 63.5 The third key a width-one selection hid, and the model had already written the alarm

`sourceusetypephysics` is keyed by (sourceTypeID, regClassID, model-year range).
Source types 11 and 21 have one row; 31 and 32 have three; a heavy truck has 15
to 21, out of 178. The drive cycle is per SOURCE TYPE, so `phys_rollingTermA`
and the rest are a `sum_product` over the rows a source type selects, and a
source type with three rows computes vehicle-specific power for a vehicle that
does not exist.

**The model reported this itself.** `run_physicsRowsSelected` exists, and its
description says: *"ONE apiece, and a test pins it: the mapping is per
(sourceTypeID, regClassID, model-year range), so a source type with two rows
would make `dss_vsp` the sum of two vehicles' physics rather than one's."* It is
1 for source type 21 and 3 for source type 32. A guard written for a case that
had not happened yet, naming the consequence, is what turned the fourth factor
from a search into a lookup — and it is the argument for writing the
`run_*Count` recomputations even when they can only be right.

That is the fourth time in one step that a selection of width one could not
distinguish a key from a constant (§60's rectangle, §61's county, §62's source
bin, this). The pattern has stopped being a coincidence: **budget one hidden key
per dimension widened, and look for it in the columns of the MOVES table rather
than in the rules of its code.**

## 64. A drive cycle is per VEHICLE, and a vehicle is not a source type **[PLAN.md step 7d; 178 rows to 4, 248 of 248 rows exact]**

§63 ended by naming the fourth hidden key and the guard that found it. This is
the step that closed it, and it is the same promotion §62 did for the source
type — one key finer, over the model's largest relational step.

### 64.1 What MOVES keys the drive cycle by, and what the rate matches against

`sourceusetypephysics` has 178 rows over 13 source types, keyed by
(sourceTypeID, **regClassID**, **beginModelYearID**, **endModelYearID**). A
motorcycle and a passenger car have one row; a light commercial truck has three
— regulatory class 30, and regulatory class 41 split at model year 2010 because
its fixed mass factor changes from 2.05979 to 5.0 while its mass does not; a
refuse truck has 15 and a combination long-haul truck 20.

The Rust says so in its key types rather than in a comment
(`drivecycle.rs:34-59`):

    struct BracketedBinKey { physics_index, road_type_id, avg_speed_bin_id }
    struct ScheduleOpModeKey { physics_index, drive_schedule_id }

and the rate row reaches the block it built through
`aggregate.rs:351-358` — a regulatory-class **equality** and a model-year
**containment**:

    if romd.key.reg_class_id > 0 && romd.key.reg_class_id != rate.reg_class_id { continue }
    if rate.model_year_id < romd.key.begin_model_year_id
        || rate.model_year_id > romd.key.end_model_year_id { continue }

That is exactly one `join.on` pair and one `filter`, which is what
`rt_physicsOrdinal` is. **A containment is not a key**: the equality half goes
in the join so the engine can drive the enumeration from it, and the range half
stays a filter over what the join already narrowed.

### 64.2 The axis is the selected rows, not a padded product

§63.3 gave the source bin a candidate grid — the cohort grid crossed with
`n_sourceBin` slots — and paid for the padding, because a cohort relation is
small. The drive cycle cannot afford that. It reads 63,602 drive-schedule
seconds, bins each into an operating mode, and does it once per vehicle; a
padded product of 5 source types and a 20-slot width would compute 100 drive
cycles where the run has 40.

So `physicsrow_rows` is the **selected rows, densely ranked**: `phys_isSelected`
over the national table, `phys_prefixSelected` its §22 inclusive prefix count,
`phys_rank` the product that zeroes the rest, and a `phy_*` relation that reads
its nine columns back through `phys_rank ↔ phy_ordinal`. `n_physicsRow` is the
fourth declared number, checked the same way the third is —
`run_physicsRowsSelected` recomputes it and `run_physicsRowsDropped` counts what
falls past it.

**Which shape to use is a question about the source relation, not about taste.**
A padded grid is right when the candidate space is a genuine product and cheap
to enumerate; a ranked subset is right when the parent table is large, the
selection is sparse, and each row is expensive. The source bin is the first and
the physics row is the second, in the same document, and they read the same
because both end in §22's prefix count.

### 64.3 The drive cycle has two halves, and one join holds them together

Not everything below the physics row belongs on the new axis, and promoting what
does not is how an axis becomes expensive for nothing:

| per (source type, road type) | per vehicle |
|---|---|
| which drive schedules apply (`dsa_isSelected`) | vehicle-specific power (`dss_vsp`) |
| which two bracket a speed bin (`asb_slowerSpeed`, `asb_fasterSpeed`) | the operating mode each second bins into (`dss_opModeID`) |
| the weight each bracket carries (`asb_scheduleFraction`) | the schedule's mode distribution (`dsa_modeFraction`) |

`asb_modeFraction` is where they multiply, and `phy_sourceTypeOrdinal` — the
vehicle's source type, as a rank into `runspecsourcetype_rows` — is the join
that puts the two factors on one row. **A promotion is a question asked
separately of every variable below the key**: a schedule's average speed does
not know what it is driven by, and the axis it carries should say so.

### 64.4 The wider axis made the chain FASTER, because the gate came with it

`dsa_modeSeconds` is the model's largest aggregate: (614 associations × 60
operating modes × the schedule's ~1,300 seconds) per vehicle, with the mode
match a filter rather than a join because `dss_opModeID` is two-dimensional and
a 2-D join key is dropped (§57 / EarthSciAST#417).

Multiplying its axis by eight should have been an eight-fold slowdown. It was
not, because the same edit added the gate MOVES's own `ScheduleOpModeKey`
implies: the association is joined to the vehicle's OWN source type and the
run's road type, so 614 associations become the ~11 a source type drives on one
road. Measured on the same machine, before and after, with everything else
equal:

| run | axis | peak RSS | wall clock |
|---|---|---|---|
| `expand-fueltype-diesel` | 2 source types → 4 vehicles | 24.6 → 24.6 GB | 273 → 151 s |
| `expand-sourcetype` | 5 source types → 40 vehicles | 34.4 → 31.0 GB | 233 → 115 s |

**When an axis gets finer, look for the gate the finer key makes available** —
the old axis could not express it (an association belongs to a source type, and
the old range WAS the source types, so there was nothing to gate against), and
the restriction is usually written down in the reference's key type rather than
in its loops.

### 64.5 What it bought

| run | before | after |
|---|---|---|
| the three in `runspecs/` | 1.140e-05 / 7.106e-06 / 8.128e-06 | unchanged to the digit |
| `expand-fueltype-diesel` | 1.48–3.06× per cell, 1.157× per pollutant | **7.372e-06 over 248 cells** |

`n_physicsRow` defaults to 1, and at 1 the drive-cycle relation IS the one
vehicle a single-regulatory-class source type has — which is why the three
existing runs did not move. That is the same property `n_sourceBin` was given at
§63, and it is worth designing for deliberately: **a new axis whose default
width is 1 is a refactor the existing corpus cannot see, and the corpus is then
free to say so.**

What it did not buy is `expand-sourcetype`, and the distinction matters for how
a blocked run is described. That document waited on a KEY for two days and the
key is now closed; what stops it is 32.0 GB of resident memory against a 40 GB
limit, which is a different kind of obstacle and belongs in a different kind of
note. **A pending document should name the thing that actually stops it**, and
the three measurements above — it is not the drive cycle, not the source-bin
padding, and `expand-fueltype-diesel` at 24.6 GB runs — are worth more in that
note than the word "memory".

## 65. The month is an axis, and the calendar was the run's only scalar left **[PLAN.md step 7d; 26 variables promoted, five runs unchanged to the digit]**

Every RunSpec in this repository selected one month, so `run_monthID` was a
`run_rows` scalar — a faq that summed `rsm_monthID` over `runspecmonth_rows`
and landed the total on the one-row carrier relation. At one selected month a
sum of one is that month, which is §59's mistake for the fourth time and the
last dimension the corpus could still hide it in.

`expand-month` selects February, May, August and November and MOVES emits
**500 rows = 1 pollutant-process block × 1 county × 4 months × 1 day type ×
125 cohorts**.

### 65.1 What varies with the month is 26 variables out of 472

| gained the axis | why |
|---|---|
| `run_monthID`, `run_monthGroupID`, `run_daysInMonth`, `run_weeksPerMonth` | the month's own identity and calendar. These four were `run_rows` scalars, and the promotion REBINDS the range they were already summed over rather than adding one: the run axis they sat on IS the month axis |
| `run_temperature`, `run_heatIndex` | `ZoneMonthHour` is keyed by month |
| `run_acActivityTermA/B/C`, `run_acActivityRaw`, `run_acActivity`, `run_evTemperatureIsSuppressed` | `MonthGroupHour` is keyed by the month group, and the quadratic is evaluated at a heat index that is the month's |
| `coh_acFactor`, `rt_acFactor`, `rt_evTemperatureAdjustRaw`, `rt_evTemperatureFactor` | the A/C load and the EV temperature quadratic both ride that meteorology |
| `run_monthVMTFraction`, `act_dayVMTFraction`, `act_vmt`, `act_sho` | `MonthVMTFraction` is the month's share of the annual VMT, and `DayVMTFraction` is keyed by month as well as by day |
| `rtDay_sho`, `rtDay_activity`, `rtDay_adjustedMeanBaseRate`, `rtDay_quantDirect`, `rtDay_quantChained`, `rtDay_quant` | everything downstream of both halves |

| did NOT | why |
|---|---|
| `rtDay_meanBaseRate` and the whole rate stack under it | a base rate is not month-keyed. Only the ADJUSTED rate is, and only through the temperature and A/C steps |
| `act_hourVMTFraction` | `HourVMTFraction` is keyed by (source type, road type, day, hour) and by nothing else — which is the sharpest line in the table, because `act_dayVMTFraction` beside it IS month-keyed. **Both names are gone as of §66**, merged into one `act_timeVMTFraction` summed over the run's time cells; the asymmetry above is why the merged relation carries the month |
| the drive cycle and the operating-mode family | `driveSchedule` and `avgSpeedDistribution` carry no month |
| `coh_isSelected`, `coh_rank`, the source bins, the age distribution | which cohorts survive is national and annual |

### 65.2 The output relation is five levels, and the month is the third

```
output_rows = n_outputPolProcess × n_runspeccounty × n_runspecmonth × n_runspecday × n_outputCohort
```

county-major over month-major over day-major over cohort, one more level in the
same decomposition §61.2 built. `month_ordinal` is the month relation's own row
ordinal, exactly as `day_ordinal` and `rsc_ordinal` are, and every output column
that varies with the month gains one key pair, `outMonthOrdinal ↔
month_ordinal`, on the clause it already had. Four columns need it —
`out_SHO`, `out_adjustedMeanBaseRate`, `out_emissionQuantDirect` and
`out_emissionQuant` — plus `out_monthID` itself, which stops being a broadcast
scalar and becomes a lookup.

**`out_meanBaseRate` does NOT need it**, and that is worth stating because it
looks like an omission: the unadjusted rate does not vary with the month, so
each of the four month blocks joins to the same rate row and gets the same
value. A column that does not carry the axis is replicated by the join, not
dropped by it.

### 65.3 What it bought, and what it did not

| run | before | after |
|---|---|---|
| `process-tirewear` | 8.128e-06 | unchanged to the digit |
| `expand-day` | 7.106e-06 | unchanged |
| `expand-counties` | 1.140e-05 | unchanged |
| `expand-fueltype-diesel` | 7.372e-06 | unchanged |
| `expand-sourcetype` | 9.017e-06 | unchanged |

Five runs, `n_runspecmonth` at 1 in all five, and the decomposition
arithmetically the one it replaced — §64.5's rule again, that **a new axis whose
default width is 1 is a refactor the existing corpus cannot see.**

What it does NOT buy is `expand-month`, and the distinction is the whole reason
this section stops here. That run sets `aggregateBy = Month`, and the axis is
the cheaper half of what that costs: the other half is that MOVES rewrites six
input tables before the rate calculation runs, to a single `(hourDayID, dayID,
hourID) = (0, 0, 0)` cell the default database does not ship. The pre-aggregation was
measured first — the collapsed `AvgSpeedDistribution` reproduces from the
default database to 4.5e-06 over all 64 cells and the collapsed `ZoneMonthHour`
temperature and relative humidity to 2.7e-10 over all four months, both at the
snapshot column's own stored precision — and §66 is what those two measurements
turned out to be worth.

## 66. A second aggregation MODE is a per-run selection of time cells, and then it is not a mode **[PLAN.md step 7d; `expand-month` 500 of 500, worst cell 8.513e-06, five runs unchanged to the digit]**

`aggregateBy = Month` looks like a branch. Canonical MOVES answers it by
REWRITING six input tables before the rate calculation runs — `HourDay`,
`HourOfAnyDay` and `DayOfAnyWeek` to one row each, `HourVMTFraction` and
`DayVMTFraction` to the literal 1.0, and `AvgSpeedDistribution`, `ZoneMonthHour`
and `MonthGroupHour` to a weighted average over a single
`(hourDayID, dayID, hourID) = (0, 0, 0)` cell — and none of those rewritten rows
is in the default database, because every one of them is a RESULT (§59.2).

**Written as a branch it would be a second model. Written as a per-run
selection it is the case every other run was already the degenerate form of.**
A RunSpec declares three lists beside the ones it already declares:

| source | what it says | the five runs that do not aggregate | `expand-month` |
|---|---|---|---|
| `db_rateday` | day types the RATE tables are averaged over | its own `runspecday`, same file | `dayID 5` |
| `db_actday` | day types the output day's ACTIVITY covers | its own `runspecday`, same file | the whole week |
| `db_aggregationhour` | hours the run averages over | its own `runspechour`, same file | all 24 |

and the model reads `avgSpeedDistribution` and `zoneMonthHour` as WEIGHTED MEANS
over the resulting (day type, hour) cells instead of as lookups. **A mean over
one cell is that cell**, whatever the weight, so all five existing RunSpecs
reproduce unchanged to the digit — 8.128e-06, 7.106e-06, 1.140e-05, 7.372e-06
and 9.017e-06 — with nine new relations between them and the table.

### 66.1 The two weights, and the one that cancels

```
asd_cellWeight(day, hour, sourceType) = hourVMTFraction at the run's road type
met_cellWeight(day, hour)             = Σ_s HourWeighting2(s, day, hour),
   HourWeighting2 = Σ_rt hourVMTFraction × roadTypeVMTFraction
                  / Σ_rt roadTypeVMTFraction
```

Canonical multiplies the first by a `DayWeighting1` over the month —
`Σ_month dayVMTFraction·noOfRealDays·monthVMTFraction / Σ_month
monthVMTFraction`. **It cancels, and the reason is structural rather than
numerical**: every output day of every run in this corpus aggregates over ONE
day type, so a factor keyed on the day type is constant across the cells it is
averaged over. Reproducing the snapshot's collapsed `AvgSpeedDistribution` with
the factor and without it gives the same 4.5e-06, which is that column's storage
precision. Carrying it would have been four more relations that no measurement
could see.

`met_cellWeight` sums HourWeighting2 over the run's SELECTED source types where
canonical picks one out of a fixed ordering (`moves.rs` ports that ordering as a
13-element constant). **No run in this corpus can tell the two apart**, and the
reason is worth stating rather than the fact: a run that aggregates selects one
source type, and a run that does not average over one cell, where the weight
cancels entirely. The sum is the form that needs no unverifiable constant, and
this paragraph is the record that it is a choice.

### 66.2 The rate side and the activity side are scoped DIFFERENTLY

This is the part a reader gets wrong, and `db_rateday` against `db_actday` is
the whole of it:

* the rate-side collapse is scoped to the day type the RunSpec **selected** —
  `day id="5"`. Averaging over both day types instead moves the collapsed
  `ZoneMonthHour` temperature by 1.6e-02 and `AvgSpeedDistribution` by 6.3e-02.
  Measured at the output by pointing `db_rateday` at `db_actday`'s file: **all
  500 cells over the per-cell gate, worst 2.403e-02**, and the per-pollutant sum
  at 6.890e-03 against a 1e-3 gate.
* the activity covers the **whole week** whatever the RunSpec selected.
  Canonical writes `dayVMTFraction := 1`, `hourVMTFraction := 1` and
  `noOfRealDays := 7` — on a run that asked for weekdays.

Both literals are SUMS, and the model writes them as sums so that no literal
appears in it. `Σ_day dayVMTFraction` is exactly 1.0 in the default database,
`Σ_hour hourVMTFraction` is 1 to 2.2e-07, and `Σ_day noOfRealDays` over the two
day types is 7. `act_dayVMTFraction × act_hourVMTFraction` became one
`act_timeVMTFraction` for the same reason: the product of two per-cell fractions
is not the sum over cells of their product unless there is one cell, and writing
the sum makes the one-cell case fall out instead of being assumed.

### 66.3 What it retired

`zmh_heatIndex` is gone. The heat index was computed per `zoneMonthHour` row and
then looked up; it is now computed from the COLLAPSED temperature and relative
humidity, which is what canonical does and what the snapshot shows — all four
of `expand-month`'s months carry `heatIndex == temperature`, the below-threshold
branch, at the collapsed temperature. **The two orders differ whenever a run
aggregates across the 78 °F threshold**, and averaging the branch is the wrong
one. `act_dayID` went with it, unreferenced once the activity read its fractions
through the cells.

### 66.4 The one selection that is not in the snapshot

`db_rateday` is the only source in `runspecs/` that does not point at its own
snapshot or at the default database. MOVES overwrites `RunSpecDay` with the
synthesized output day AFTER the pre-aggregation has run, so the captured table
says `dayID 0` and the day the weights were scoped to is not in the execution
database at all. `tools/runspec-day-selection.py` reads it from the RunSpec XML
into `runspecs/selections/expand-month-rateday.parquet`.

**That is an interim and it is filed as one** (moves.rs#69): a snapshot should
be self-describing about what was ASKED for as well as about what MOVES
computed, and the capture already holds the XML. When it carries the parsed
selections the script and its output go away. The general rule this run adds to
§7.1's discipline is narrower than it looks: **a per-fixture document reads its
selections out of the snapshot, except where MOVES has overwritten one with a
result — and then the document says which one, and why, and where it went
instead.**

### 66.5 What it bought

| | |
|---|---|
| `expand-month` | **500 of 500 cells, worst cell 8.513e-06** against a 2e-05 gate, worst per-pollutant 6.386e-07 |
| cost | 8.6 s, 0.51 GB — the cheapest run in `runspecs/` after `process-tirewear` |
| the other five | unchanged to the digit |
| first run | it reproduced on it |

The last line is the one worth keeping. Both weights were reproduced in Python
against the snapshot's own collapsed tables **before the model changed**
(PLAN.md §7.3.11), which turned a second aggregation mode from a search into a
translation. Every other document in `runspecs/` went through `pending/` first;
this one never entered it.

---

## 67. A pollutant either deteriorates with age or it does not, and that decides which rate table it is in **[PLAN.md step 7d; residual reduced to `criteriaRatio` alone at 8e-06, six runs unchanged to the digit]**

`expand-criteria` is the first RunSpec in this tree to leave the energy and
particulate pollutants, and the first thing it found was that the chain had been
reading one of MOVES's **two** zero-hour rate tables and had no way to know it.

### 67.1 The two tables are disjoint in pollutant-process, so the chain selects, it does not sum

`emissionRate` is keyed on `(sourceBinID, polProcessID, opModeID)`.
`emissionRateByAge` adds **`ageGroupID`** and is fifteen times the size — 1,590,830
rows against 105,449. The temptation is to read the second as an age-resolved
refinement of the first. It is not. Their `polProcessID` sets do not intersect:

| table | pollutant-processes |
|---|---|
| `emissionRate` | 190, 191, 290, 291, 390, 391, 601, 602, 3090, 9101, 9102, 9190, 9191, 11290, 11291, 11609, 11710, 11890, 11891 |
| `emissionRateByAge` | 101, 102, 111, 112, 113, 201, 202, 301, 302, 3001, 3002, 11201, 11202, 11801, 11802 |

Running **energy** (9101) is in the first; running **THC, CO and NOx** (101, 201,
301) are in the second. Which table a pollutant-process lives in is a statement
about the pollutant — a 1980 passenger car emits far more hydrocarbon than a 2020
one and exactly as much energy per source-hour — and not a modelling choice.

So `rtMode_rate` is an `exact_else_wildcard` over `rt_hasRateByAge`, not a sum:

```
rt_hasRate    = exact_else_wildcard{ has_exact: rt_hasRateByAge, exact_value: 1,
                                     wildcard_value: rt_hasRateAgeless }
rtMode_rate   = exact_else_wildcard{ has_exact: rt_hasRateByAge,
                                     exact_value:    rtMode_rateByAge,
                                     wildcard_value: rtMode_rateAgeless }
```

A sum would give the same number on every run in this corpus, because the
disjointness holds. Writing the selection is what makes the disjointness a
**claim the document makes** rather than a property it silently depends on, and
one discriminant serves both lines so they cannot disagree about which table was
read.

### 67.2 The surviving cohort count is a property of the rate table's key set

Every RunSpec in `runspecs/` before this one emits 125 cohorts for source type
21. `expand-criteria` emits **124**, and the missing one is (fuel type 9,
model year 2000) — electricity. Model years 2001 to 2020 of the same fuel *are*
emitted, at zero. The difference is not a rule about electricity: it is that
`emissionRateByAge` has no row for that source bin at that model year's age
group, so the rate row is not rated, `rt_survives` is 0, and nothing is emitted.

That fell out of J58 with no extra rule written: adding the sixth key pair moved
`cohortSurvivorCount` from 125 to 124 on the first run. It is worth naming
because it is the first time in this port that the **rate** table decided the
**shape** of the answer. Until now the cohort grid decided it and the rate table
only supplied numbers.

### 67.3 A join key that names the wrong relation is silently dropped, and the tell is that one pollutant looks like another

This cost an hour and is the most transferable thing in this section.

The model already had an `emissionRateAdjustment` relation whose columns are
prefixed `era_`. The new `emissionRateByAge` relation was written with the same
prefix, so its `era_polProcessID` — intended over `emissionratebyage_rows` — lost
the name to the one already declared over `emissionrateadjustment_rows`. The
document **validated and simulated**. Six of the seven key pairs in J58 bound;
the `polProcessID` pair did not, because its right-hand side resolved to a column
over an index set the aggregate has no range for, and EarthSciAST's
`lower_node_joins` treats that as the degenerate positional no-op and `continue`s
(`join.rs:463-474`). The contraction then summed the rates of **every**
pollutant-process at each source bin.

Two things made it hard to see:

* **The answer was plausible.** Numbers came out, of the right order of
  magnitude, for every cell.
* **The left side has the error this needed and the right side does not.** A
  left key that resolves to nothing is an `UnsupportedFeatureError` naming the
  column. A right key that resolves to nothing is silence.

The tell, once looked for, was diagnostic: **THC and NOx returned identical
numbers**. Two pollutants agreeing to fifteen digits is not a modelling error, it
is a key that is not in the join. The confirmation was cheaper still — polProcess
3101 is absent from `emissionRateByAge` entirely, and `rt_hasRateByAge` returned
3 for it rather than 0.

Filed upstream as [EarthSciAST #437](https://github.com/EarthSciML/EarthSciAST/issues/437),
which asks for the three cases `resolve_side` currently folds into one `continue`
— undeclared name, column over a foreign axis, genuine positional no-op — to be
told apart, with the middle one refused.

**The local rule, which does not wait on the fix: one relation, one prefix, and
check the prefix is free before using it.** `era_` was taken; the ByAge relation
is `erba_`, which is what `fixtures/process-nox-speciation.esm` had already
called it.

There is a second instance of the same trap in this section's own work, caught
the other way round. `rt_humidityCFR86` ranges over `run_rows` and indexes
nothing with it. That range looks spare and deleting it is silent: it is what
lets the second key pair's right side — `run_humidityEqCFR86`, a one-row relation
over `run_rows` — resolve to a loop symbol at all. Without it both humidity arms
fire for every fuel type. The equation says so in its comment, because nothing
else would.

### 67.4 The NOx humidity correction multiplies the temperature factor, and it is two formulae in one table

`noxhumidityadjust` is three rows. Fuel types 1 and 5 carry `CFR 86`; fuel type 2
carries `CFR 1065`; fuel type 9 carries nothing and therefore takes factor 1.
The two names are two genuinely different formulae over two different measures of
the same air:

| equation | argument | form | on this run |
|---|---|---|---|
| CFR 86 | specific humidity, g H₂O / kg **dry** air, bounded to [3, 17.71] | `1 − A·(H − 10.71)` | 10.0536843 → **1.0215928** |
| CFR 1065 | water mole fraction, per mole **ambient** air, bounded to [0.002, 0.035] | `1 / (A·x + B)` | 0.0159291 → **1.0095484** |

Three things a reader would not guess from the table:

1. **It multiplies the temperature factor rather than adding to it**:
   `(1 + tempAdjust) × k`, inside the NOx branch of `general_temp_adjust`.
2. **`humidityTermA` means different things in the two rows** — 0.0329 as a
   slope in the first, 9.953 as a denominator coefficient in the second — and so
   do the bounds, which carry two different units in one column. The bound has to
   travel with the equation.
3. **`humidityTermB` is NULL on the CFR 86 rows**, so the arms have to be
   separate aggregates. §30.4 already argued this for the fixture; it holds here
   for the same reason, and an `ifelse` would not help because it selects a
   result and does not stop an operand being evaluated.

This chain computes both humidity measures rather than reading them, because it
has no execution database: `run_vaporPartialPressure` comes from the temperature
and relative humidity it already computes, through `lib/meteorology.esm`'s
MG-6/MG-7 templates. Measured against the columns MOVES stored, that is
2.298e-08 and 2.262e-08 relative — the storage limit of the reference columns,
and 870× below the per-cell gate.

### 67.5 What the measurement bought, again

§66's lesson held a second time. Before anything was written, the residual after
J58 was taken to the snapshot and asked what it was, rather than a list of
candidate adjustments being ported one at a time. The answer was exact and it was
short:

```
missing factor  =  criteriaRatio(fuelType, formulation, polProcess,
                                 sourceType, modelYear, ageID)
                 × noxHumidityAdjust(fuelType)
```

worst 7e-06 across all three pollutants, all three fuel types and all 124
cohorts. That is what says **`temperatureAdjustment` contributes exactly 1 here**
(its only rows for these pollutant-processes are model years 2027 and later),
**`IMCoverage` is empty** so the whole inspection-and-maintenance blend is
inactive, and **`emissionRateAdjustment` is empty** — three ports not needed,
established in twenty minutes of pandas rather than by writing them and watching
the number not move.

It also priced what IS needed. `criteriaRatio` is **empty in the default
database**: MOVES's `FuelEffectsGenerator` computes all 4,398 rows at run time,
from the EPA Complex Model for MY ≤ 2000 gasoline and from
`generalFuelRatioExpression` for the rest. That is the one thing
`runspecs/pending/expand-criteria.esm` waits on, and the pending document says so
in those terms rather than as a list of suspicions.

## 68. An equation carried as a string is a form and a table of coefficients, and the split is a measurement **[PLAN.md step 7d; `expand-criteria` 309 of 372 cells at 7.804e-06, six runs unchanged to the digit]**

§24 says what to do with a MOVES table whose column holds arithmetic: the FORM
becomes an expression template, spelled once, and the COEFFICIENTS stay data.
`criteriaRatio` is the first place in this port where that rule had to be applied
to a table the chain reads at scale, and it turned out to have four separate
lessons in it.

### 68.1 Split along the seam the generator already has, not along the table

`criteriaRatio` has 4,398 rows and three columns, and **MOVES fills them two
different ways without recording which**. Model years 2001 and later, and diesel
at every model year, come from evaluating a closed form the database ships as SQL
text. Gasoline model years 2000 and earlier come from running the EPA Complex
Model live over five more tables. Nothing in the output distinguishes them.

The seam is worth finding before any porting starts, because the two halves cost
very different amounts and one of them can be delivered on its own. Here the
closed form is 135 expression strings and five data sources; the Complex Model is
eight tables and a weighted polynomial sum. Porting the first alone took
`expand-criteria` from 372 wrong cells to **63**, and the 63 are exactly the rows
the second half owns — which is both a result and a check that the seam was read
correctly.

### 68.2 Parse the strings, then prove the parse against the strings

The coefficients cannot be read out of the database: searched across all 237
tables, not one of the intercepts, polynomial coefficients, base divisors, GPA
factors or low-sulfur slopes appears anywhere except inside the expression text.
(`sulfurModelCoeff.sulfurCoeff` and `m6SulfurCoeff.sulfurLongCoeff` do carry the
sulfur powers and multipliers — a corroboration, not a source, because the tables
are keyed by a model-year group the string does not record.) So they are
transcribed, and a transcription needs a check that is not "it reproduces the
answer".

The check that works is a **round trip through an independent evaluator**: parse
every string, reconstruct it from the extracted coefficients using the very
templates the document will use, and compare the two over every input the data
can supply. Here that is 135 strings × 2,158 fuel formulations = **165,297 cells
at a worst 1.4e-14**, run before a line of `.esm` was written. It is a stronger
statement than the fixture comparison that follows it, because it covers inputs
no RunSpec selects — and it is what says a coefficient was not silently dropped
on a row the corpus never reaches.

The census that comes out of the parse is the other half of the value: 102
distinct strings collapse to **two top-level forms and five term sets**, and both
forms were already in `lib/fuel_effects.esm`. What the chain had to add was one
template, `criteria_exponent`, and 135 rows of numbers.

### 68.3 The default database is not the execution database, and the difference is a generator

Every captured `fuelformulation` table in the snapshot corpus is the EXECUTION
copy — MOVES has already run its setup steps over it. Read the NATIONAL table
instead and two of those steps become the document's problem:

* **`changeFuelFormulationNulls`.** 2,118 of 2,158 rows have a NULL
  `BioDieselEsterVolume`; a parquet NULL reaches an `.esm` as a NaN, and a NaN
  multiplied by a market share of zero is still a NaN. `components/fuel_effects.esm`
  calls this sweep "a no-op against a relation whose columns are concrete" and it
  is, there — the component carries five formulations as literals, already filled.
  Against the table it is not a no-op at all.
* **`alterHighEthanolFuelProperties`** (`FuelEffectsGenerator.setup()` step 020).
  The default database ships the E85 formulations with **distillation sentinels**
  — `T50` 999, `T90` 999, `ETOHVolume` 74 — and the THC criteria polynomial
  carries `5.58e-05·T50²`. Read straight, the fuel-effect ratio is **1.0e+17**
  instead of 0.645. MOVES overwrites every combustion property of a subtype-51 or
  -52 formulation from `e10FuelProperties`, keeping only its own RVP, before any
  fuel-effect arithmetic runs.

A sentinel of 999 is the useful shape to remember: it is not a flag and not a
missing value, it is a number that will be squared. **A snapshot-fed document
cannot find either of these**, because both have already happened to the table it
reads. They are the price of §7.1's default-database rung and the reason it is
worth paying.

Where a canonical fallback chain exists and the data never exercises it, say so
rather than porting it: step 020 coalesces the regional row, then the national
row, then the formulation's own value, and not one of the 15,360 non-national
rows has a NULL in any column read here. The port stops at the first level and
the note records that the national row would have supplied a NULL `sulfurLevel`
in all 757 of its rows — which is what the fallback would have been falling back
to.

### 68.4 Both arms of a form selection are evaluated, so the unused one has to be finite

An `ifelse` over arrays computes both arms. A relation that carries several
algebraic forms and selects between them therefore has to carry filler values
that keep the unselected arm a number — and "a number" is a stronger requirement
than it looks:

* a diesel row carries base 1, GPA factor 1 and multiplier 0, so its sulfur arm
  is exactly 1;
* it carries sulfur power **1 and not 0**, because at power 0 the spelling
  `exp(power · log(sulfur))` is `exp(0 · −∞)` — a NaN — for the two formulations
  in the table whose sulfur level is 0. At any positive power it is `exp(−∞)`,
  which is 0, and the arm stays finite;
* a gasoline or ethanol row carries biodiesel coefficient 0, so its biodiesel arm
  is exactly 1.

The general rule: **look for the input that makes each filler degenerate, not
just the filler that makes the arm look tidy.** `components/fuel_effects.esm`'s
description already listed the finite-arm requirement and named `sulfurLevel = 0`
as the one case it could not satisfy; reading the national table is where that
case arrives.

### 68.5 What the coverage is, stated as a count rather than guarded

The relation covers the **135** rows of `generalFuelRatioExpression` whose
pollutant-process is 101, 201 or 301 — all 13 source types, all 3 fuel types,
both model-year ranges. It does not cover the other 135, which are processes 102,
202 and 302 and carry **cross terms** (`ETOHVolume·T50`, `ETOHVolume·T90`,
`ETOHVolume·RVP`, `ETOHVolume·aromaticContent`) that `standardized_term` cannot
spell. A miss is scaled by 1, which is what MOVES does when its own lookup misses
— so the failure mode for an uncovered key is silent.

That is stated in the document, in the domain document's own commentary and in
PLAN.md, and it is **not** guarded by a runtime check, because the guard would
need a data source read for nothing else and no RunSpec in this repository
selects process 2. §23's rule cuts both ways: a corpus that cannot discriminate
something is a reason to write the limit down, not a reason to build machinery
that watches for it.

One thing the coverage decision is NOT free about: `sourceTypeID` is a real key
in this table. The sulfur power is 0.168 at source types 11 and 21 and 0.125 at
the other eleven; the low-sulfur slope takes three values and is zero for a
motorcycle; the Tier 3 model-year boundary is 2016/2017 for most source types and
2017/2018 for two of them. Seven of this repository's eight RunSpecs select source
type 21 alone. Carrying only it would have been right on all seven and wrong on
`expand-sourcetype` — §62.3's width-one trap, in the dimension the corpus is
known to move.

### 68.6 A selection whose flag is not on the leading axis returns an EMPTY relation, silently

`exact_else_wildcard` is an `ifelse`, and an `ifelse` over arrays broadcasts.
Broadcasting here aligns operands by PREFIX: `X[b,g,m]` against `Y[b]` works, and
`X[h,c,g,m,f]` against `Y[c]` does not — the flag is on the second axis, not the
first. What the second one does is not an error and not a wrong number. It
produces an **array with no elements**, and every relation downstream of it is
then 0.

Measured, on the Complex Model's term factors: a 78-row relation came back with
zero rows, the polynomial that reads it came back 0, `exp(0)` is 1, and the
weighted ratio of ones is exactly 1 — so the model silently dropped the entire
complex model and kept only the sulfur half. The run still produced 372 plausible
cells and the residual moved from 16 % to 2 %, which reads like progress.

**The tell is an intermediate that is all zeros where the inputs are not.** The
fix is to spell the selection inside a `faq` with explicit `index`es, which names
the axes instead of aligning them:

```json
{"op": "faq", "output_idx": ["h","c","g","m","f"], "ranges": {...},
 "expr": {"op": "apply_expression_template", "name": "exact_else_wildcard",
          "bindings": {"has_exact":   {"op":"index","args":["flag","c"]},
                       "exact_value": {"op":"index","args":["value","h","c","g","m","f"]},
                       "wildcard_value": 1.0}}}
```

This is the same category as §67.3's dropped join key and it has the same
symptom: a wrong answer of the right order of magnitude. The difference is where
to look. A dropped key gives a number that is too WIDE — two pollutants agreeing
to fifteen digits. A failed broadcast gives a number that is too NARROW — a
relation that is empty, and a product that is 0. Check the intermediates for
emptiness before checking the physics.

## 69. A cohort or a pollutant-process with no rate is not emitted, and a chained one has no rate on purpose **[PLAN.md step 7d; `expand-criteria` 372 of 372, worst cell 7.805e-06, six runs unchanged to the digit]**

§67.2 measured this and left it as a binding. It is now a rule, and writing it
turned out to need one more distinction than the measurement showed.

### 69.1 Two counts, one predicate

The output relation is (pollutant-process block) × (cohort), and until
`expand-criteria` the chain computed both dimensions from the run's SELECTIONS:
a cohort was emitted if the grid selected a source bin of it, a pollutant-process
if it happened on a road type the RunSpec selected. Both are necessary and
neither is sufficient. MOVES emits what it has a NUMBER for:

* `expand-criteria` emits **124** cohorts where every other run of source type 21
  emits 125. The model year 2000 ELECTRICITY cohort has no `emissionRateByAge`
  row at its age group; model years 2001–2020 of the same fuel have rows whose
  rate is ZERO, and those are emitted. "No row" and "a row of zero" are different
  answers and only the first removes a cohort.
* It emits **3** blocks where 4 pass the road-type test. SO2 running exhaust is
  selected, happens on a road, and has no rate row anywhere.

So both counts multiply by the same predicate — does any rate row of this cohort,
or of this pollutant-process, produce a number? — and the rate row's own ordinals
(`rt_cohortOrdinal`, `rt_polProcOrdinal`) are already the keys into both
relations, so no new key had to be built.

### 69.2 The predicate is not `rt_survives`, because a chained pollutant-process has no rate by construction

The obvious spelling is the existing `rt_survives`, which is
`rt_isSelected × rt_hasRate`. It is wrong, and `process-tirewear` says so
immediately: it emits three blocks and only two of them carry a rate. PM2.5 tire
wear (10710) is `runspecchainedto`'s OUTPUT — its quantity is PM10's times a
`pm10emissionratio` — and it has `rt_isSelected` **0** on every one of its rate
rows, because `rt_isSelected` requires a `pollutantprocessmodelyear` row and not
having one is exactly what makes a pollutant-process chained.

The predicate is therefore a rate OR a chain:

```
rt_emits = max(rt_survives, (rt_chainRatio > 0) × bin_isSelectedAt)
```

which is `run_chainedRowCount`'s own spelling of the second arm. `rt_survives`
stays what it was — the rate selection — because the two questions are different
and the chain is the proof.

### 69.3 What this replaces, and why the replacement is worth more than the number

`runspecs/expand-criteria.esm` was pending with `n_outputCohort` bound to 124,
and the binding gave an EXACT key set — 372 of 372, none missing, none extra.
It was exact by luck: the relation is truncated to the declared length, so it
drops the LAST cohort, and the unrated one happened to rank last. A run whose
unrated cohort ranked in the middle would have emitted two wrong keys and the
binding would have hidden it.

That is the shape worth recognising. A declaration that makes the answer come out
right is not the same as a rule that makes it come out right, and the difference
only shows up in a run nobody has made yet. §11's "a checked declaration" is the
standard: `n_outputCohort` is still declared, but `cohortSurvivorCount`
recomputes it from the chain and run-tests.sh compares the two, so the number is
now evidence rather than an input.

Six RunSpecs could not tell the new rule from `true` (§23): every cohort they
select is rated and every pollutant-process they select has a rate. That is the
ordinary condition for a rule in this port — it is discovered by the first run
that violates it, and the runs that cannot see it are what say the change is
safe.

### 70 The output relation is not a rectangle, and two declared numbers could not say so

`onroad/model.esm` declared its output shape as a product —
`n_outputPolProcess × n_outputCohort × counties × months × day types` — and
every RunSpec in `runspecs/` satisfied it, because every one of them emitted
blocks of the same width. That is a property of the corpus and not of MOVES.
A **chained** pollutant-process is as wide as its ratio table's coverage, and
`NONO2Ratio` and `CrankcaseEmissionRatio` carry fuel types 1, 2, 3 and 5 and no
row for electricity, so NO, NO2, HONO and the three crankcase processes emit
**104** cohorts where their parents emit **124**.

#### 70.1 The shape of the fix: rank the PAIRS, once

The output relation's leading factor is now the (pollutant-process, cohort)
**pair**, ranked densely 1..`n_outputRate`, with the county, month and day-type
levels inside it. `ratecohort_rows` is the pollutant-process crossed with the
cohort candidate grid — the rate relation with the source bin divided out — and
it carries the rank. Two declared numbers became one, and the one that remains
is the one that can be ragged; `outputPolProcessCount` and `cohortSurvivorCount`
are still reported, and `rateSurvivorCount` is now what `n_outputRate` is checked
against. `tools/check-runspec-shape.py` prints which of the two a run is:

    436 rows = 436 (pollutant-process, cohort) pairs x 1 county x 1 month(s)
    x 1 day type(s); 4 block(s) and 124 cohort(s), RAGGED

**Do not rank the rate relation itself.** The rate relation is keyed by source
BIN, so several of its rows share a pair, and a prefix count over it would
number the bins rather than the output rows. The pair relation is also 1,722
rows where the rate relation is 13,776 on `expand-sourcetype`, and the rank is a
self-join with a `<=` filter, so it is the difference between three million
cell-pairs and a hundred and ninety million.

**Two conditions have to be spelled again.** The old packing carried them in an
`and`: a pair emits when a rate row of it emits AND the road-type test kept its
block. Dropping the second one is not visible as an error — `rateSurvivorCount`
came back 744 instead of 372 on `expand-criteria`, six blocks' worth where three
are emitted, and the extra rows appeared in the output as pollutant 68 process 9,
which is the SUM of the five pollutant-processes whose `rspp_outputOrdinal` is 0.
A key column read through a join that matched nothing is not blank; it is the
sum of everything the join did match.

#### 70.2 A ratio of exactly zero is a ratio

`CrankcaseEmissionRatio` carries `crankcaseRatio = 0.0` for diesel model years
2001 and later, and MOVES emits those cohorts — as zeros. A chain arm written as
`rt_chainRatio > 0` drops them: `process-crankcase-running` emitted 627 rows
instead of 684, 85 cohorts per crankcase block instead of 104. The test is
PRESENCE, and it has to be a separate flag from the value, because the value
cannot distinguish "no row" from "a row that says zero". This is §69's rule in a
second place: a cohort rated at zero is rated, and a ratio of zero is a ratio.

#### 70.3 Three chain tables, three ways of saying which model years

| table | chained | model years keyed by | other keys |
|---|---|---|---|
| `PM10EmissionRatio` | PM2.5 from PM10 | min/max RANGE | polProcess, fuel, source type |
| `NONO2Ratio` | NO, NO2, HONO from NOx | model-year GROUP, of the SPECIES | polProcess, fuel, source type |
| `CrankcaseEmissionRatio` | crankcase from running | min/max RANGE | polProcess, fuel, source type, **regClass** |

The arms are disjoint by pollutant-process, so the union is a **sum** and not a
precedence, and the presence flags union under `max`. The group in the middle
row is the SPECIES' own group, not its parent's, which is why the port needed
`rt_modelYearGroupID` as a value and not only J18/J19's presence test. The
regulatory class in the last row is a real key that no RunSpec here can see:
source type 21 has exactly one class, so dropping it would be right on every run
in this directory and wrong for a light commercial truck — §62.3's width-one
trap, named rather than closed.

### 71 The chain is a fixed point, and three is a measurement

`rtDay_quantChained` read the parent's **direct** quantity: the quantity a rate
row gets from its own rate table row, before any chain term is added. That is
correct for a species whose parent is rated — PM2.5 brake wear from PM10, NO
from total NOx, crankcase running from running — and it is every chain in
`runspecs/` up to this point. It is wrong the moment a chained pollutant-process
is itself a parent, and the hydrocarbon species are exactly that:

```
chain-tog-speciation   THC 101 → NMHC 7901 → NMOG 8001 → TOG 8601
process-airtoxics      THC 101 → NMHC 7901 → VOC  8701 → benzene 2001
```

Read one rung deep, TOG and benzene come out **zero** — not wrong by a factor,
absent. §69 makes that the same failure as a cohort with no rate: the row is not
emitted at all, and the shape checker reports missing rows with no hint of why.

#### 71.1 Three is the corpus, counted rather than assumed

The unroll depth is not a judgement call. Every `runspecchainedto` in
`../moves.rs/characterization/snapshots` was read and its graph's longest path
measured:

| chained snapshots | rows | longest chain | widest fan-in |
|---|---|---|---|
| `process-tirewear`, `process-brakewear` | 1 | 1 | 1 |
| `process-nox-speciation`, `process-crankcase-running` | 3 | 1 | 1 |
| `process-airtoxics` | 5 | 3 | 1 |
| `chain-tog-speciation`, `chain-nonhaptog` | 5 | 3 | **2** |
| `chain-so2-co2e-mechanism`(`-control`) | 21 (20) | 3 | **2** |
| `process-pm-exhaust` | 8 | — | 2 |
| the twelve `nr-*` | 651 | — | 2 |

Three rungs and two parents cover every onroad run. The two rows with no
longest chain are the reason this is a *measurement* and not a bound: their
graphs have **cycles**. `process-pm-exhaust` records 118 from 115 *and* 115 from
118, and 118 from 119 *and* 119 from 118. `runspecchainedto` says which
pollutant a calculator MAY derive an output from, not which one it does — the
calculator registration decides that — so the table is not a DAG and no
"compute the depth and unroll that far" rule is well defined on it. A fixed
number of rungs is, which is the other reason to spell the unroll out.

#### 71.2 The run checks the number it was given

Three being enough for the corpus is not three being enough for a run, so the
run says so itself. `rt_emitsGen4` is a **fourth presence pass** — a presence
pass carries no day, county or month, so it costs one more self-join of the rate
relation and nothing else — and `run_chainDepthExceeded` counts the rate rows a
fourth rung would newly emit. It is 0 on every RunSpec here, asserted by
`tools/check-runspec-shape.py` alongside the dropped source bins and the
vehicleless physics rows, and it is the same **kind** of check as those two: a
failure that costs rows rather than accuracy, which nothing else in the shape
identity would attribute correctly.

The value side needs no separate check. Presence and value walk the same graph,
so a chain that converges in three rungs for one converges for the other.

#### 71.3 What a template can carry and what it cannot

A `faq`'s `ranges` and `join` are equation-level: an expression template can
carry an expression, not a relational step, so the three passes are three
equations and not one applied three times. What *is* shared is the per-pass
predicate — a row emits if it has a rate of its own, or if its ratio exists and
its parent emitted — and that is `lib/chaining.esm`'s `chained_emits`, applied
at all four generations including the check. Before it, that `max` of a
`survives` and a gated product was spelled once; at four generations, spelling
it four times is how the check and the thing checked drift apart.

### 72 A ratio table keyed by the fuel SUBTYPE, and a species computed from a tally nobody reports

The hydrocarbon species — methane, NMHC, NMOG, TOG, VOC — are four ratio
lookups and one sum, and between them they broke three assumptions this port
had never had to question.

#### 72.1 A rate row has a fuel type; a ratio table can want a subtype

`methaneTHCRatio` and `HCSpeciation` are keyed by **(process or
pollutant-process, fuel SUBTYPE, regulatory class, model-year range)**. Gasoline
is not one subtype but six — 10 conventional, 11 reformulated, 12–15 the
gasohols — and their methane fractions differ. A rate row carries a fuel *type*.

The subtype is not a column to add; it is a **join through the county's fuel
supply**. `FuelSupply` gives the formulations a region carries in a month group,
`FuelFormulation` gives each one's subtype, and the ratio is the market-share
weighted mean over them — the same collapse `cfr_suppliedRatio` already makes
for the criteria ratio, and the reason `rt_chainRatio` gained a county and a
month. It had been a function of the rate row alone since PM10 brake wear, where
the ratio table is keyed by fuel *type* and the question never arose.

`rt_hasChainRatio` did **not** gain them: whether a table has a row for a cohort
does not depend on which county is asking.

Neither table carries an electricity subtype, so the four species blocks are 104
cohorts where THC is 124 — §70's ragged output reached from a third table.

#### 72.2 TOG has two parents, and a key column holds one

`rspp_chainInputPolProcessID` was a `sum_product` over `runspecchainedto` keyed
by the output pollutant-process. With one edge per output the sum *was* the
parent. TOG is methane **plus** NMOG, two edges, and that sum would have
returned `501 + 8001 = 8501` — a pollutant-process that does not exist. It is
§70.1's "pollutant 68, process 9" at a second site: an ID column holding the sum
of everything the join matched, and the tell is that it is an ID that is not one.

The fix is not a second slot. `runspecchainedto` **is** the edge list, so the
chain joins through it:

```
{ "syms": ["b",  "h"], "on": [["rt_polProcessID", "rct_outputPolProcessID"]] }
{ "syms": ["b2", "h"], "on": [["rt_polProcessID", "rct_inputPolProcessID" ]] }
{ "syms": ["b", "b2"], "on": [["rt_binOrdinal",   "rt_binOrdinal"         ]] }
```

One `faq` per rung whatever the fan-in, and two variables deleted rather than
one added. `syms` may pair a rate-row symbol with a chained-to symbol —
CONFORMANCE_SPEC §5.5.8 requires only that each entry name a range the node
binds and that the key's axis be the one that symbol draws.

TOG then needs no arithmetic of its own. The chain multiplies a row's ratio by
*each* parent and sums, so an arm that says **one** is the whole of
`TOG = methane + NMOG`. It is also the one arm whose presence flag is a pollutant
test alone, with no table behind it — which is why `run_chainedRowCount` reads
437 on this run and not 436: 104 each for the three table-backed arms and **125**
for TOG, the selected cohorts rather than the rated ones. What stops TOG being
emitted where its parents are not is `rt_parentEmitsHere`, not its ratio.

#### 72.3 `altTHC` is one property, and the quotient is an exponent difference

Ethanol E70/E85 vehicles of model year 2001 and later have their NMOG and VOC
speciated from `altTHC` (pollutant 10001) — the THC the fuel-effect machinery
would have produced under the E10 base fuel's RVP — while their **reported**
methane and NMHC still come from the ordinary THC. Get that backwards and the
E85 NMHC comes out at 0.662 of THC instead of 0.178.

`altTHC` is the base rate scaled by `altCriteriaRatio`, and the whole difference
between that and `criteriaRatio` is **one property**. The high-ethanol
substitution overwrites fifteen combustion properties of a 51/52 formulation
with the E10 row's and deliberately leaves RVP alone; `altRVP` is the value it
declined to use — 8.0 against formulation 27002's own 7.7. The model already
computed both sides of that and kept only one.

The two ratios therefore share their sulfur factor and their base divisor
exactly and differ only inside the exponential, so

```
altCriteriaRatio / criteriaRatio  =  exp(altExponent − exponent)
```

which is computed as written: no division by a ratio, and no second copy of the
sulfur arm. `cff_altExponent` is `cff_exponent` with one binding changed, which
is what a template library is for. The number is **0.9934070**, against 0.993396
read off the run.

The fuel half of the E10 test is not in the flag. `ff_speciationSubtypeID` is
the formulation's own subtype for everything that is not 50/51/52 and
`ffx_altRVP` is its own RVP for everything that is not 51/52, so the correction
is the identity on every fuel but ethanol and `rt_isE10Speciation` says only
what the formulation cannot: which model years and which processes.

#### 72.4 A term that is identically zero is still counted

`HCSpeciation`'s factor is
`speciationConstant + oxySpeciation × volToWtPercentOxy × totalOxygenate`, and
`oxySpeciation` is **exactly zero in all 2,562 rows** of the national table. So
the second summand contributes nothing anywhere and this document carries
neither `volToWtPercentOxy` nor the four oxygenate volumes it would need.

That is a fact about the DATA, not about MOVES, and §23's rule applies to an
omission as much as to a rule: `run_oxySpeciationReached` counts the rows a
run's joins reach whose coefficient is not zero, asserted at 0, so a county
database that shipped one would say so instead of quietly losing a term.
`lib/adjustments.esm`'s `speciation_factor` already spells the form it would
take.

#### 72.5 A working pattern has a price, and the price is a declared number

`cfr_suppliedRatio` reaches the county's formulations by ranging over
`fuelsupply` and `fuelformulation` and collapsing them by market share inside
the lookup. It is the obvious pattern, it is correct, and it was copied seven
times for the hydrocarbon species — once for each of the methane ratio and the
two speciation constants, at the row's own fuel subtype and again at the E10
one, plus the presence flags.

`expand-day` went from **60 seconds to 564**, on a run with no chained
pollutant at all. `FuelSupply` is **105,651** rows nationally against
`FuelFormulation`'s 2,158: one spine over that product is affordable, eight are
not.

The collapse is now `ffsup_marketShare[county, month, formulation]`, computed
once, and every lookup joins the small result. `cfr_suppliedRatio` was rewritten
onto it too, so a run that had one such spine now has none and `expand-day`
finishes in **34 seconds** — faster than before the species were added.

The lesson is not "hoist common subexpressions". It is that **the cost of a
pattern is a number the document already declares**: `n_fuelsupply` is a
metaparameter, it is discovered at load, and reading it before copying the
pattern an eighth time would have priced the copy in seconds. §62's rule — price a
promotion by forward closure before making it — applies to reusing a relational
step, not only to adding an axis.

### 73 A table the default database ships EMPTY, and one generator fills it two different ways

`ATRatio` is `AirToxicsCalculator`'s gasoline ratio table. In the default
database it has **0 rows**, and MOVES writes it at run time — as it writes
`criteriaRatio`, and for the same reason (§68): the rows depend on the county's
fuel, so they cannot be shipped. What is new here is that the two halves of the
table are produced by two *different* computations inside one generator, and
that a run needs both.

| model years | source | rows it produces here | what it is |
|---|---|---|---|
| 2001–2060 | `generalFuelRatioExpression` | 11 | the closed form, evaluated on each supplied formulation |
| ≤ 2000 | the Complex Model at the `airtoxicsA` engine | 4 toxics × 41 ages | `(atBaseEmissions_toxic × ratioNoSulfur_toxic) / (atBaseEmissions_VOC × ratioNoSulfur_VOC)` |
| ≤ 2000 | `generalFuelRatioExpression` again | 2 | for the two toxics that have no complex model at all (§73.5) |

`criteriaRatio` splits at exactly the same model year and in exactly the same
two ways (§68.2), which is the argument for having ported it first: the second
table needed one new engine, five new configurations and four new algebraic
forms, and no new *shape*.

**The split is NOT by model year.** That is how it reads with three toxics in
front of you, and it is wrong: it is by *which generator holds the
coefficients*. Benzene, 1,3-butadiene, formaldehyde and acetaldehyde have rows
in `ATBaseEmissions` and in `ComplexModelParameters`, so their early half comes
off the complex model and `generalFuelRatioExpression` carries no early string
for them. Ethanol and acrolein have neither, so `generalFuelRatioExpression`
carries a 1950–2000 string for them and there is no second half to look for.
The cheap check that tells the two apart is a row count in `ATBaseEmissions`,
not a model year.

#### 73.1 A constant that turns out to be a key, found by the second engine

The Complex Model read `meanFuelParameters` and `baseFuel` at the literal
model-year group **19502000**, written into three filters. That is right for all
three criteria configurations and wrong for all four air-toxics ones, which sit
at group **0** and whose base fuel is formulation 96 (`Base Gasoline Fuel`)
rather than 99 (`High Sulfur Gasoline`). This is §62.3's width-one trap at a fifth
site, and it has the property that makes that trap worth naming: **the three
configurations that existed could not see it**, because they agreed. The fix is
two columns on the configuration relation — `cmxcfg_meanModelYearGroupID` and
`cmxcfg_baseModelYearGroupID` — and the filters become join keys.

#### 73.2 Centring only shows up in a NONLINEAR term

`meanFuelParameters` gives every complex-model property a centring value, and
the polynomial subtracts it before multiplying. In `exp(S(target)) −
exp(S(base))` a centre **cancels** whenever the term is linear in the property:
`c·((x_t − m) − (x_b − m))` is `c·(x_t − x_b)`. Benzene, 1,3-butadiene and
formaldehyde use linear terms only. VOC — the shared denominator of all three
quotients — carries an E200 squared, an E300 squared and an E300 × aromatics
term, and there the centre does not cancel.

So a document with the centring silently missing reproduced **all three toxic
`ratioNoSulfur` values to every digit an `--observed` printed** and every one of
the three *ratios* was **7.4 % high**. Three of the four configurations could not see the bug and the
fourth moved all three answers by the same factor — which is what a shared
denominator does, and which reads exactly like a physics error in the numerators.

The rule: when an intermediate is shared by several answers, **check the
intermediate**. A common factor is invisible in the ratios between the answers
and obvious in the intermediate. Here `cmx_ratioNoSulfur` was observable with one
`--observed`, and comparing it against the same number computed in pandas found
in one step what comparing three answers could not find at all.

#### 73.3 Three forms the corpus said were not checkable

`docs/fuel-effects-generator.md` §8.1 recorded forms D, E and F as ported by
nobody and checkable by nobody: every `generalFuelRatioExpression` row that uses
them is moved into `ATRatio` and deleted from `generalFuelRatio` before a
snapshot is taken. That is true of the SNAPSHOT path. On the default-database
path the same rows are the only way to get a number, and `ATRatio`'s own 243
captured rows are the reference for them. The three are now
`centered_linear_ratio`, `quadratic_property_ratio` and `air_toxics_exponent` in
`lib/fuel_effects.esm`, and `runspecs/process-airtoxics.esm` checks all three.

Form F is worth one line of its own: `exp(A)/(exp(B) − exp(C))`, where A, B and C
are the same four standardised properties with different coefficients. The
denominator is a DIFFERENCE and a `sum_product` faq adds, so the subtraction is
carried as data: the three exponent rows have a `numeratorSign` and a
`denominatorSign` column, `+1` and `−1`, and one join gathers both halves of the
denominator. A sign column is how a difference is written relationally.

#### 73.4 Widening a shared relation is priced the same way as copying one

The complex-model relation now serves two generators. `complexconfig_rows` went
from 3 rows to 7 and `complexengine_rows` from 19 to 29, and every `cmx_*`
variable is dense over both: `cmx_modelSumTarget` is (configuration × engine row
× county × month × formulation) and `cmx_ratio` adds the source type and the
age. Measured on `expand-criteria`, which selects no air toxic and reads none of the
new work: **39.9 s of user CPU before and 49.8 s after, 25 % more**, with peak
RSS 1,277 MB against 1,315 MB and the emitted relation byte-identical.

**A second widening, priced the same way.** §73.5 added acetaldehyde:
`complexconfig_rows` 7 → 8, `complexproperty_rows` 13 → 15 and
`complexterm_rows` 29 → 31. Same document, same binary, same metric:
**49.8 s → 52.8 s of user CPU, 6 % more** over three interleaved passes,
peak RSS unmoved at 1,326 MB. The first widening was 33 % more configuration
rows for 25 % more CPU; this one is 14 % more for 6 %. The relation is not
linear in any one of its three sizes, and the useful reading is that each is
cheap on its own and the product is not — which is the §72.5 argument again,
against a different factor.

**Measure the CPU, not the clock.** This node is shared and its load average
moved between 43 and 112 while that was being measured; the same document took
**42 s of wall clock on one pass and 557 s on another**, which is a factor of 13
of somebody else's job. User CPU over three interleaved passes is steady to
0.2 s on each side. The first two attempts at this number were thrown away for
believing the clock: one of them reported the WIDENED document as twice as fast
as the narrow one.

**And the upstream fix for this does not exist yet, measured rather than
hoped.** EarthSciAST PR #440, "materialize an inline `const` array literal once,
not once per cell", merged the morning after the first widening, and the
widening is mostly inline `const` arrays — so it looked like the thing that
would pay for it. It does not. `esm` built from `3cf6f6f` and from `be1fafe6`
(which carries #436, #440 and #439) on the same document, three interleaved
passes each: **52.6 / 53.7 / 52.2 s against 52.4 / 52.2 / 54.2 s**, peak RSS
1,326 MB both, output byte-identical. The means differ by 0.2 %, and the single
slowest pass of the six is the *new* binary's. **This is a negative result and
it is worth the same as a positive one**: the cost above is the document's
shape, not the runtime's handling of `const`, so the saving named below is where
it has to come from.

§72.5 priced *copying* a relational pattern. This is the other case — the
pattern is not copied, it is **widened** — and the price is the widening factor
times whatever the relation already cost. It is read off the same kind of number:
there, a metaparameter discovered at load; here, two `interval` sizes written in
the document itself, which is cheaper still to look up.

The saving that is available and is not taken: the (configuration × engine row)
product is 8 × 29 = **232 pairs of which 69 are meaningful**, because an engine
row belongs to one engine and a configuration names one. Indexing the model sums
by fuel MODEL rather than by engine ROW would make it 152, and restricting each
configuration to its own engine's rows would make it 69 — which would pay for
both widenings over. Named, not closed.

#### 73.5 "That is data and not new machinery" is a claim, and it was wrong twice — and a census that sums correctly can still be wrong

`runspecs/pending/chain-so2-co2e-mechanism.esm` recorded, as a *measurement*,
that three of the toxics it half-emits — ethanol 21, acetaldehyde 26 and
acrolein 27 — were **"DATA in the two relations `process-airtoxics` already
added, and not new machinery."** Closing them took 183 rows and two pieces of
machinery. Both are worth naming, because both are the same mistake: **a form
census and a property set are sized to the rows you have read, and the next
pollutant-process is not obliged to stay inside them.**

**Ethanol's early ratio is a SEVENTH algebraic form.** It is

```
IF(E<0.1, 0.0, IF(E>=0.1 AND E<6.0, 0.01195, IF(E>=6.0 AND E<9.0, 0.01912, 0.0239)))
```

— a step function of one fuel property, which is neither a polynomial nor an
exponential and which none of `docs/fuel-effects-generator.md` §2.1's six forms
can spell.

**And the census was wrong, in a way worth more than the form is.** It counted
**"six forms plus a bare constant"** over 2,078 rows and reported form C, the
sulfur switch, at **1,013 rows and 100 strings**. Re-classified with this form
pulled out: form C is **974 rows and 99 strings**, and the step is **39 rows and
1 string in 3 snapshots**. `974 + 39 = 1,013`. The rows were never missing —
they were **absorbed**, by a classifier that asked whether a string contains
`if(` and got a case-insensitive yes on `IF(ETOHVolume<0.1, …)`. The partition
checks the census reported — rows summing to 2,078 and strings to 118 — all
still pass, because a misclassification moves rows between buckets without
changing either total. **A partition check proves the classifier is total, not
that it is right**; what would have caught this is printing one representative
string per bucket, which costs one line and is now in §2.1. (The bare constant,
meanwhile, really was data: acrolein is `centered_linear_ratio` with a zero
slope, which returns its scale exactly.)

**Acetaldehyde's complex model reads two properties the relation did not
carry.** `complexproperty_rows` held thirteen — the ones the three criteria
pollutant-processes, the three ported toxics and VOC need. Acetaldehyde's
`complexModelParameters` rows name cmpID 46 (`ETBE`) and 47 (`Ethanol`), which
are fuel parameters 11 and 12, and neither was there. Twelve of its thirteen
terms were right and the answer was **wrong by a flat 2.386 on all 21 model
years**.

That flatness is the whole diagnosis, and it is §73.2 read the other way round.
§73.2 said a centring is invisible in a linear term; this says **a missing
LINEAR term is invisible as anything but a constant factor** — the complex
model's answer is `exp(Σ coefficient × property)`, so dropping one term whose
property does not vary over the run multiplies every cell by one number. Here
that number is `exp(0.249326 × 0.3488 × 10) = 2.386`, and it agrees with the
observed 1/0.4191 before any code is read. **When every cell of a block is
wrong by the same factor, take the logarithm and look for a term, not a bug.**
The corollary for finding it: the 21 wrong cells were exactly the model years
the *complex* half covers, and every closed-form row was right — so the
residual named its own generator before anything was instrumented.

**What it cost, and what would have caught it.** One re-run of the chain (74 s
of CPU) to see the factor, one `grep` of `ComplexModelParameters` for the new
pollutant-process's `cmpID` set against `cmxprop_fuelParameterID`, and one
column. **That grep is the check worth keeping**: before adding a configuration
to a shared engine, list the parameter identifiers its coefficients name and
subtract the ones the relation carries. It is two lines of pandas and it is the
same check §62.3's width-one trap asks for, applied to a *set* rather than to a
column.

### 74 A bare variable in a `filter` is IGNORED once the aggregate has two output indices

This is a third member of the family §67.3 and §68.6 name — a shape error that
produces no error, no NaN and a plausible number — and it is the one that costs
the most, because the working spelling and the broken one differ by four
characters. §67.3 is a join key silently dropped, §68.6 is a selection that
returns an empty relation, and this one is a filter that is not applied at all.
Filed upstream as EarthSciML/EarthSciAST#441.

A faq's `filter` may reference a variable by BARE NAME, resolved from the
variable's shape exactly as `expr` resolves it, and that is how every filter in
`onroad/model.esm` was written:

```json
"filter": { "op": "apply_expression_template", "name": "in_half_open_range",
            "bindings": { "lower": 0.5, "upper": 1.5, "value": "rt_fuelTypeID" } }
```

That works while the aggregate has **one** output index. Give it a second — a
county and a month beside the rate row — and **the filter is ignored
entirely**. Every tuple passes. The gasoline test and the model-year test both
went inert together, every fuel type took the gasoline ratio, and model year
2020 took both halves of a table that is split at 2000: the answer was the
*sum* of two ratios that can never apply to one row, which reads as a modelling
mistake about appending versus choosing.

#### 74.1 The trigger is the output count and nothing else, measured

A three-variable probe settles it. `a_val` is `[1, 2, 3]`, the filter is
`a_val > 1.5` in all three, and row 1 should never survive:

| `output_idx` | the filter's `a_val` | result | correct? |
|---|---|---|---|
| `["i"]` | bare | `0, 2, 3` | yes |
| `["i","g"]` | bare | `10,20 / 20,40 / 30,60` | **no — row 1 survives** |
| `["i","g"]` | `index(a_val,"i")` | `0,0 / 20,40 / 30,60` | yes |

Everything else was varied and changed nothing: a second non-output range, a
`join` clause, the filter written inline as an `ifelse` versus through an
`apply_expression_template`, the bare variable drawing the first output index
or the second, and a second factor over another index set. Only the number of
output indices matters.

#### 74.2 The rule, and the lint that enforces it

**In a `filter`, index every variable explicitly.** The bare form is not
shorthand for the same thing once the aggregate has more than one output index,
and the spelling that is always right costs four characters:
`{"op": "index", "args": ["rt_fuelTypeID", "b"]}`.

`run-tests.sh` now checks this rather than trusting it: one pass over every
`.esm` document in the repository, reporting any `faq` with two or more output
indices whose `filter` names a declared variable of that model bare. The repo
had exactly one instance before this rung and it is the subject of §74.3; it has
none now.

#### 74.3 Two things that made it cost more than four characters

* **The `bool_and_or` twin of the same faq filtered correctly.**
  `rt_hasAtComplexRatio` is `rt_atComplexRatio` with the county and month ranges
  dropped and `expr: 1.0` — so it has ONE output index, and its identical filter
  applied. The presence relation said gasoline-only while the value relation
  said every fuel type, and the two disagreed silently. A presence relation is
  usually the narrower twin of its value relation, which puts it on the right
  side of this bug and makes the disagreement look like a modelling
  inconsistency.
* **`rt_complexRatioExact` had carried the same inert filter all along**, and
  nothing was wrong: `rt_criteriaRatio` is
  `ifelse(rt_hasComplexRatio > 0.5, rt_complexRatioExact, ...)`, and
  `rt_hasComplexRatio` is the single-output twin whose filter works. **A boolean
  gate in front of a value relation hides this class of bug completely.** Both
  filters are now explicit, and the lint is what says there is not a third.

### 75 A ratio-1 row can be a FILTER in one calculator and a chain in another

`crankcaseEmissionRatio` has rows for PM sulfate (11501) and PM water (11901)
on the **running** process, ratio 1. `process-crankcase-running` taught the
chain to read that table as "this child is its parent times this ratio", which
is what it means for the crankcase processes. Inside `SulfatePMCalculator` the
same rows mean something else: sulfate and water have *already* been split out
of NonECPM by the sulfate fraction, and the ratio-1 row only says the running
portion of each stays in the running process — a **row filter** on a species
that exists, not a recipe for making it.

Measured on `runspecs/pending/process-pm-exhaust.esm`: the generic crankcase
lift emits sulfate as **all of NonECPM** — 1.7× to 68× high — and water as
NonECPM where MOVES has exactly 0.0. Nothing fails loudly, the rows have the
right keys, and no RunSpec that reproduces today selects either pollutant, which
is why the suite has never seen it.

**The rule: a ratio table does not say which calculator owns its rows.** Before
a generic lift claims a (pollutant-process) for the chain, check whether another
calculator produces that pollutant-process first and reads the same table as a
modifier. The cheap check is `runspecchainedto`: a pollutant-process that appears
there as an OUTPUT whose inputs are not the table's parent is owned by something
else. The fix belongs where the lift decides what it claims, not in the data.

**Done that way.** `rt_isSulfatePMSpecies` is 1 on a rate row whose pollutant
`crankcaseEmissionRatio` also carries on a NON-crankcase process, and both
crankcase lifts multiply their filter by its complement. The exhaust-process
rows of the default table are exactly 112, 115, 119 and 120, which is
`SulfatePMCalculator`'s species set and nobody else's — `CalculatorInfo.txt`
agrees, registering `CrankcaseEmissionCalculatorNonPM` for gaseous pollutants
only. `runspecs/pending/process-pm-exhaust.esm` went from 456 emitted rows to
248, the difference being exactly the 208 wrong sulfate and water cells, and
`process-crankcase-running` is unchanged to the digit.

### 76 A cyclic chain declaration is a linear map with no direction

`runspecchainedto` for `process-pm-exhaust` has two 2-cycles: NonECPM → sulfate
→ NonECPM, and NonECPM → water → NonECPM. §33.1 and `docs/process-pm-exhaust.md`
§2.8 already said the table records a calculator's inputs rather than a
computation order. What porting it showed is the positive half: **the arithmetic
under that cycle is a matrix.**

`SulfatePMCalculator` makes four species per cohort — EC copied from its rated
block, and sulfate, water and an internal residue split out of the rated NonECPM
— and then every block it writes is a sum of species with a coefficient:

| block | EC | sulfate | water | residue |
|---|---|---|---|---|
| EC 112 | 1 | | | |
| sulfate 115 | | 1 | | |
| water 119 | | | 1 | |
| NonECPM 118 | | 1 | 1 | 1 |
| PM2.5 110 | 1 | 1 | 1 | 1 |
| organic carbon 111 | | | | `pmSpeciationFraction` |

NonECPM appears as an input (it is split) and as an output (it is re-summed),
and that is the whole of the "cycle". Written as species × shares, the inputs are
the two RATED blocks and the outputs are the six rows of the table; nothing
feeds back. In `onroad/model.esm` it is eleven entries of `spmsh_*` and one sum.

**The rule: when a chain declaration cycles, look for the species it is
conserving.** A calculator that takes X in and puts X out is almost always
splitting X into parts and adding some of them back, and the parts are the
state — not X. The fixed-point iteration §71 built is the wrong tool for that
and was never needed: the chain's rungs still run, and they see the six blocks
as having their OWN quantities, because the share matrix enters at
`rtDay_quantDirect` and not at the output. That is also what let PM10 chain off
PM2.5 through a path that already existed.

Measured: `runspecs/process-pm-exhaust.esm`, 728 of 728 at 7.516e-06, on the
first run of the port, all fourteen other documents in `runspecs/` unchanged.


### 77 A chain edge has a unit and a weight, and not every edge is in `runspecchainedto`

Until `chain-so2-co2e-mechanism`, every chained pollutant-process in this port
was one ratio times one parent, the parent was a mass, and every edge was a
row of `runspecchainedto`. That run broke all three, and the chain's shape
changed from "a child has a ratio" to "an edge has a weight".

**The unit.** MOVES chains in its internal units — kilojoules and grams — and
converts energy to Million BTU only when it writes `MOVESOutput` (S18). This
chain divides as it goes: `rtDay_quantRated` is already in the reported unit,
so a child reads its parent in Million BTU. For a mass child of a mass parent
the two agree. For SO2, the first child of an energy pollutant to be ported,
every cell came out low by exactly 1,055,055.9, and the pandas reproduction
had shown the same factor against the reported energy before the port began. The weight
`lnk_weight` carries the parent's S18 divisor over the child's: 1,055,055.9 on
the energy → SO2 and energy → CO2 edges, 1 on every other. It belongs on the
EDGE, not the child, because it depends on both ends.

**The edges MOVES keeps in code.** `CO2AERunningStartExtendedIdleCalculator`
chains CO2 off Total Energy, and CO2 equivalent off CO2, methane and N2O, in
its Java `subscribeToMe` — the step-2 input set is the literal `"90,5,6"`.
`pollutantprocessassoc.chainedTo1/2` are NULL on 9001 and 9801, so no
`runspecchainedto` carries those edges, while SO2's (9101 → 3101) is there.
The table is the ASSOCIATION graph pruned to the run; it is not every edge a
calculator follows. The port declares the four CO2AE edges as constants
(`cae_*`, crossed with the calculator's four processes) and unions them with
`runspecchainedto` into `chainlink_rows`, the one relation all seven rungs
join through. A calculator with code-declared edges is then one more block of
that relation, not a second copy of every rung.

The union is spelled `concat`, and it had to be. A positional join (`l` ↔ `h` by
an ordinal) is the first thing that comes to mind, but it needs an ordinal
COMPUTED over `runspecchainedto_rows`, and that table is empty in six of the
fifteen runs: a computed relation of length 0 panics (F56). The first version
did exactly that and took six RunSpecs down, and the version before it spelled the
position as an `==` in a filter, which the conventions lint rejects. `concat`
names what the relation is and computes nothing over the empty axis. The CO2AE
weight is then lifted onto the concatenated relation by its (output, input) pair
with `exact_else_wildcard`, wildcard 1.

**The weight that is physics.** CO2 equivalent is CO2 + 28 × methane + 265 × N2O:
three different parents, each with its own factor, and a SUM. A per-child
ratio cannot say that. With the weight on the edge (`cae_weight`, read from
`Pollutant.globalWarmingPotential`) the child's own arm is the number one, as
TOG's always was, and the rungs are unchanged.

**The rule: when a chained child needs a number that depends on which parent
it came from, the number is an edge attribute.** And before concluding that a
calculator is not chained because `runspecchainedto` is silent, read its Java
`subscribeToMe`.

### 78 A leaf past the last rung is computed after the chain, not as a fourth rung

NonHAPTOG (88) is NMOG minus the fourteen members of the national integrated
species set, clamped at zero. Its inputs include benzene, which is THC → NMHC →
VOC → benzene: three rungs. NonHAPTOG would be the fourth, one past what §71
measured and unrolls. It is also not linear, because of the clamp.

It needs neither a fourth rung nor a nonlinear chain, because it is a LEAF:
nothing in any calculator is computed from 88. So `rtDay_nonHapTogSum` reads the
FINISHED quantities (`rtDay_quantDirect + rtDay_quantChained`) of its fifteen
inputs through a signed self-join on source bin and process (`rt_nonHapTogSign`:
+1 for NMOG, −1 for a member, 0 otherwise), and the clamp is applied to that.
Presence is split the same way: `rt_emitsChained` is what the chain decides,
and `rt_emits` adds NonHAPTOG wherever its NMOG is emitted. The fourth-rung
check (`run_chainDepthExceeded`) compares against `rt_emitsChained`, so it still
measures the chain alone.

One place this is coarser than MOVES: the SQL clamps each worker-output cell,
which includes the regulatory class, and this clamps each source bin. The two
agree unless a bin's NMOG is below its own toxics. In this corpus the smallest
unclamped cell is 0.0015 g, so the corpus cannot tell the two apart.

**What switches it on is not pollutant 88.** `chain-nonhaptog` selects 8801,
and MOVES emits no NonHAPTOG for it. A run turns the calculator on by selecting a
MECHANISM pseudo-pollutant on a process — `chain-so2-co2e-mechanism` selects
300001, pollutant 3000, which `TOGSpeciationCalculator.java` decodes as mechanism
`1 + (3000 − 1000)/500` = 5 — and the execution database's `integratedSpeciesSet`
is filtered to the selected mechanisms, which is why it is empty in every other
snapshot. The first version of this port gated on 88 alone and put 104 phantom
rows into `chain-nonhaptog`. Its values still passed, because `n_outputRate`
truncated the phantom block, which came last. The shape check caught it; the
gate is `rt_mechanismSelected`. A declared size hides whatever it cuts off.

**The rule: before adding a rung for an operation the chain cannot express,
ask whether anything consumes its output.** If nothing does, the operation
runs after the fixed point.

## 79. A control run is a document, and what it checks is the gate rather than the arithmetic **[PLAN.md step 7d; `chain-so2-co2e-mechanism-control` 2,309 of 2,309, worst cell 8.201e-06, at no model cost]**

Most documents in `runspecs/` earn their place by making the model compute
something new. `chain-so2-co2e-mechanism-control` computes nothing new at all:
it is `chain-so2-co2e-mechanism` with five pollutants deselected, and MOVES's
own two answers are bit-identical on all 2,309 shared rows. It reproduced on its
first run and cost no model change, which is exactly the outcome that makes a
control worth keeping rather than deleting as redundant.

**What it checks is what a selection is ALLOWED to switch off.** Conventions §69
says a pollutant-process with no rate is not emitted; that rule is about the
data. This is the other half: a pollutant-process the RunSpec never selected
must not be emitted either, and the two places that can go wrong are the two
places where the model supplies machinery the run's own tables do not.

| mechanism | present in | switched off by |
|---|---|---|
| the four CO2AE chain edges (§77) | EVERY run — they are declared in the model, because `pollutantprocessassoc.chainedTo1/2` are NULL | nothing in the run's tables. Only the absence of a rate row for 9001/9801 |
| the NonHAPTOG leaf (§78) | every run | the mechanism pseudo-pollutant, not pollutant 88 |

A declared edge list is the dangerous kind of machinery, because a table-driven
edge disappears with its table and a declared one does not. The rule it needs is
that a declared edge must join to the run's selected rates like any other, never
to a set the model itself constructed — and the only way to see that it does is
a run where the edge exists and its endpoint is not selected.

**The rule: when a port replaces a data-driven mechanism with a declared one,
the run that does NOT want it is as much a test as the run that does.** Write
that run as its own document. The cheap way to know it is worth writing is to
check the two references against each other first: if the deselected run's rows
are bit-identical to the other's, the document can only fail by gating wrongly,
and every failure it reports is a real one.

## 80. Mount the empty table **[PLAN.md step 7d; `process-evap-leaks` 64 of 64, worst cell 7.294e-06, on its first run]**

§30 says absence and zero are different and that a value of 0 is a row, so a
`> 0` filter deletes it. This is the same distinction one level up, where the
whole relation is the thing that is absent, and it decides how a document spells
a multiplication by nothing.

`process-evap-leaks` needs MOVES's evaporative operating-mode distribution,
which is `soakActivityFraction × (1 − fractionOfOperating)` on the soaking modes
and `greatest(0, 1 − Σ soaking)` on All Running. `soakActivityFraction` has
**zero rows in the national default database** — `TankTemperatureGenerator`
writes it, and all four of that generator's outputs ship empty — and zero rows
in every execution-database snapshot this model is mounted against. So the two
soaking modes contribute nothing, and there are three ways to write that:

1. Leave the table out and give mode 300 the weight 1.
2. Leave the table out and give the soaking modes the weight 0.
3. **Mount the empty table, join it on all five of its keys, and sum over no
   rows.**

The first two are shorter, both are right on every run in the corpus, and both
are wrong. An aggregate over an empty relation is the additive identity, so (3)
produces the same three numbers — but it produces them from the data, and the
other two produce them from the author. The difference shows the day a county
database ships the table, or the day a run selects the off-network road type and
`fractionOfOperating` stops being 1.

**What makes this affordable is that an empty extent is legal — and finding F56
says the opposite, which is worth pinning down.** F56 is that an `interval`
index set of size 0 makes evaluation PANIC (`col_major_to_arrayd shape mismatch:
shape [0] (product 0) vs 1 elements`), and it is still open. It does not apply
here, and the difference is the data source:

| | axis size | what writes the relation | result |
|---|---|---|---|
| F56's repro | a metaparameter left at its DEFAULT of 0 | nothing — no `data_source` supplies it | panic: one element placed into shape [0] |
| an empty mount | an `extent` that DISCOVERED 0 | a parquet with no rows | a relation of length 0, and an aggregate over it is the identity |

Both were probed rather than reasoned about: a five-variable document over the
national `SoakActivityFraction` validates, simulates and passes an inline
assertion that the sum is 0, while `docs/findings/F56_*.esm` still panics beside
it. The rule F56 states from the other side — an axis sized 0 is fine as a `faq`
RANGE and fatal when a relation is MATERIALIZED at that length — is the same
rule: a source that supplies zero rows *is* the thing that materializes it, at
the right length. What stays unsafe is `--observed` on such a relation, which is
refused as not build-time-evaluable.

`spikes/7c/` had been mounting a zero-row `integratedSpeciesSet` all along
without anyone noticing it was the same question.

**The rule: if the calculation joins a table, mount it — even when you have
measured that it has no rows.** An empty mount costs one data source and says
where the number came from; a missing mount saves the line and moves the
statement from the database into the document, where nothing will ever check it
again. State the measured emptiness in the source's `note`, because the note is
what a later reader compares the next database against.

**The corollary is that a row set can diverge where the numbers do not.** MOVES's
own `opModeDistribution` for this run has three rows and this port emits one, and
the two absent rows carry exactly 0. Nothing in `MOVESOutput` can see that, and
a document is entitled to reproduce a run whose intermediates it cannot — but
only if it says so. This one does, in its description and in this section.

## 81. A prerequisite is not a selection, and the execution database does not say which is which **[PLAN.md step 7d; `process-refueling` 168 of 168, worst cell 6.981e-06]**

Every document in `runspecs/` takes its scope from the execution database's
`runspec*` tables and never from the RunSpec XML, because the XML's `@key`
attributes are 0-based indices into sorted ID lists and a document that reads
them as identifiers is off by one in month and hour and wrong wholesale in day
(`docs/mixed-onroad.md` §0.1). `process-refueling` is the one run where that
rule has a cost, and the cost is worth stating exactly, because it is the first
thing the execution database cannot answer.

`runspecpollutantprocess` carries **seven** rows and MOVES emits **two**. Three
of the seven are Total Energy Consumption at running, start and extended-idle
exhaust, and the RunSpec never asked for them:
`ExecutionRunSpec.flagRequiredPollutantProcesses` adds them because a refueling
loss is computed by scaling energy, and without them `BaseRate` emits none and
the chained calculator sees no input at all. The addition is flagged
`silentlyRequired` and the output processor strips it — so the run computes 250
energy rows and emits none of them. **The flag is not persisted.** The execution
database records the expanded set; `run_spec.pollutant_process_associations`,
which the engine filters on, is the raw XML selection.

**It is recoverable anyway, and only because the needs table is refueling-only.**
`REFUELING_NEEDS` is thirty rows: five pollutants — THC, NMHC, NMOG, TOG, VOC —
crossed with the two refueling processes, each requiring Total Energy
Consumption at three exhaust processes. No other calculator in MOVES adds a
prerequisite. So the rule

> a pollutant-process is stripped iff it is Total Energy Consumption at running,
> start or extended-idle exhaust **and** the run selects one of the ten
> refueling outputs

is a function of the selections and a declared table, which is what
`rspp_isSilentlyRequired` computes. Had the mechanism been general — had any
chained calculator been able to pull its parent in — the expanded set would not
determine the original one, because `X = S ∪ needs(S)` has more than one
solution and the maximal one is always `X` itself.

**State the blind spot rather than hiding it.** `require()` returns without
flagging when the pair is already selected, so a RunSpec asking for refueling
**and** for Total Energy Consumption keeps its energy block where this rule drops
it. Nothing in the corpus does that. The document says so, in its own
description, because a limitation a reader has to rediscover is worse than one
that is written down.

**The general rule this leaves: a runspec document supplies SELECTIONS, and a
selection is not the same thing as a scope.** Where the two differ and the
database records only the scope, derive the selection from a declared table and
name the case the derivation cannot reach. Do not reach for the XML — the reason
not to read it has not changed — and do not quietly emit the prerequisite either,
which is the failure this section exists to have caught: it put 125 energy rows
into a 168-row answer and the key columns went to nonsense, because
`n_outputRate` truncated the real blocks away.

## 82. `occursOnRealRoads` says where a process's RATES are written, not where its rows appear **[PLAN.md step 7d; `process-refueling`, and the corrected rule changes no earlier run]**

`emissionProcess.occursOnRealRoads` is `'N'` on both refueling processes, and
MOVES emits both at road type **4**, the run's. The flag is not a statement
about where the emission happens; it is `BaseRateGenerator`'s, and it says which
road types that generator writes a process's rate rows on — every selected road
type for a real-road process, road type 1 alone for an off-network one.

**A process the generator writes no rates for has no road type of its own.** Its
rows are a chained calculator's, stamped on the rows they were computed from, so
they carry the parent's road type. That is measurable rather than arguable:
neither `emissionRate` nor `emissionRateByAge` carries a single row at
`polProcessID` 118 or 119, while the off-network processes that DO keep road
type 1 — start exhaust 2, extended idle 90, auxiliary power 91 — carry 8, 7 and 6
pollutant-processes between them.

So the test is `occursOnRealRoads` **or** *the rate tables have no row for this
pollutant-process at all*, the second half asked of the TABLE and not of the
run's rate rows — a road type cannot depend on which vehicles a RunSpec happened
to select. Over the whole snapshot corpus the correction can only reach
processes 16, 17, 18, 19, 22, 23 and 24, and none of them is selected by a run
in `runspecs/` other than this one, so `expand-day`'s suppression of start and
extended-idle energy is untouched.

**The rule: when a flag is named for a physical fact, check which mechanism
actually reads it before porting it as one.** This one reads as "refueling does
not happen on a road", which is true and is not what the column is for.

## 83. Put a recurrence on an axis the mount discovers, and close its inner loops in algebra **[PLAN.md step 7d; `process-evap-permeation` 64 of 64, worst cell 5.630e-06; `TankTemperatureGenerator` TTG-1..5]**

`TankTemperatureGenerator` walks three nested loops: TTG-4a's work queue over a
vehicle's trips, each trip's hour segments, and TTG-4b's soak one MINUTE at a
time until the tank falls to the cold-soak temperature plus 3 °F, with the next
trip starting from wherever the soak ended. esm-spec §4.3.1.1 admits one
recurrence shape: ONE variable reading itself at a strictly earlier position
along ONE axis, the other axes identity. Two variables that read each other are a
cycle and are rejected, so there is no nesting to be had. What there is instead
is a choice of axis and a closure of everything inside it.

**The axis is the input table's rows, not MOVES's walk.** The obvious
transcription is one row per segment and per soak slice — 19,390 for this run —
with the state carried from row to row. Its length is a function of the data, so
every RunSpec would have to declare it, and a run that selects no evaporative
process would declare 0, which is finding F56: a computed relation of length 0
panics. `SampleVehicleTrip` is already sorted `(vehID, dayID, tripID)`, its
extent is discovered by the mount, and on it the predecessor of every chained
trip is the previous non-marker row (docs/evap-permeation.md §8.1). So
`ttg_tripState` recurs over the 37,216 national rows: a marker row carries the
state through, a real trip reads its predecessor at lag 1, and a run that does not
run the generator masks every row. Nothing is declared.

**Inside a trip, every loop has a closed form, and each was verified against
MOVES's own intermediates before it was written:**

* the operating rise is affine in the key-on temperature, so the trip's segments
  compose to `slope x keyOn + intercept` (`ttg_riseSlope`, `ttg_riseIntercept`),
  and the 140 °F cap is applied once because it is ABSORBING — the rise at 140
  °F is `termA + 15.84`, positive for every group;
* a hot-soak minute is geometric decay toward the hour's ambient, so every
  slice's entry temperature is affine in the trip's key-off temperature;
* the early stop is monotone within a slice, so whether it happens ANYWHERE is
  `keyOff <= K` for one threshold per trip (`trp_soakStopThreshold`), and WHERE
  is a `ceil` of a logarithm;
* the end-of-soak temperature is `U x keyOff + V`.

The state is then one number with two sentinels — MOVES's own −1000 for "the
soak ended cold" and −2000 for "the work queue never reaches this trip", which
has to be STATE and not a column because it is transitive: 17 national trips name
a predecessor that is not in the table, and 75 are unreachable. Reproduced from
the national tables in exactly this shape before any JSON: 10,370 operating
segments and 132,886 recorded hot-soak minutes, `OperatingTemperature`'s and
`HotSoakTemperature`'s row counts EXACTLY, and every `AverageTankTemperature`
cell below 1e-06.

**Keep the recurrence body small; compute what it does not need to carry
outside it.** The first version inlined the whole segment composition into the
body, with three copies of the key-on template each holding three guarded
self-reads. It was correct and did not finish: 595,456 cells in over 400 s at
46 MB, which is the signature of per-cell cost, not size. Moving the affine rise
into two ordinary variables took the same probe to 7.5 s, and the document then
matched an independent numpy reproduction on every cell — the same class
(temperature, ended cold, not walked) on all 595,456 and the temperatures to
8.7e-16. The rule of thumb: a recurrence body should hold the state transition
and nothing that is not a function of the state.

**Two format facts the port ran into.** A join key must be a 1-D column over one
index set: `tsk_hourID` is (trip, slot), so the slice's hour is a GATHER instead,
which is safe only because the hour-of-day axis is the document's own and
complete by construction — position h is hour h. And a NULL in an integer
column is a hard error at ingest, which is the right behaviour: `priorTripID` and
`keyontime` are read with `float_columns` so a NULL arrives as NaN and a marker
row can be told from a trip with key-on time 0.

**What it costs the runs that do not need it:** the soak grid and the recurrence
are built in every run, masked, because the axes are national. Measured on five
runspecs against HEAD: 10 to 28 s and 0.2 to 0.7 GB more each, and every output
byte-identical.

## 84. A column's meaning can belong to the calculator that reads it **[PLAN.md step 7d; `process-evap-permeation`, two keys and one factor]**

Permeation found two tables whose rows mean different things to different
calculators, and in both the symptom was the bad kind: every row present and
every value wrong.

**`temperatureAdjustment`.** It carries two rows for polProcess 111, and to
`BaseRateCalculator`'s `general_temp_adjust` a row is the coefficients of a
quadratic about 75 °F in the AMBIENT temperature. To `EvaporativePermeationCalculator`
the same two numbers are PC-2a's scale and exponent, `termA x exp(termB x T)` in
the TANK temperature. The first run of the permeation rate path multiplied every
one of its 64 rows by 9.281 — exactly `1 + 0.0625(59.5 − 75) + 0.0385(59.5 − 75)^2`
— because S15's fall-through read them. A factor that is the same on every cell
is a whole-row mechanism applied where it does not belong, and it is worth
evaluating the candidate before searching further. `rt_temperatureFactor` is now
the identity on a permeation row, `rtDay_permeationTemperatureAdjust` reads the
same terms, and the units are handed over where they are read, because the
column's units depend on the reader too.

**`sourceTypePolProcess.isRegClassReqd`.** The source bin's regulatory class
is a property of the (source type, pollutant-process), not of the vehicle:
`SourceBinDistributionGenerator` writes the bin with class 0 when the flag is
'N', and the rate tables are keyed by that bin. Before `rt_rateRegClassID`, every
permeation cohort found no rate and all 64 rows were exactly 0 with the key set
perfect. Only 111 and the chained SO2, NO and NO2 processes are 'N' nationally,
and the last three have no rate rows, so the rule changes nothing else.

**`fuelFormulation.ETOHVolume`, and this one was exact by luck.** PC-3 bins each
formulation by its ethanol volume, and MOVES reads the execution database's
`FuelFormulation`, which `FuelEffectsGenerator.setup()` has already rewritten:
E85 formulation 27002 ships 74 and is read as 10, E10's value. The first version
of `rt_etohBinShare` read the national 74 and put E85 in bin 6 where MOVES puts
it in bin 3 — and every cell still agreed, because `hcPermeationCoeff`'s bins 1
to 7 carry identical coefficients nationally. It reads `ffx_ETOHVolume`, the
model's substituted volume, now; `TankFuelGenerator`'s RVP does too, and there
the difference is not invisible — 7.61 psi against 7.7 for E85.

**The rule: before porting a lookup into a table that several calculators read,
ask which calculator the row is for.** The table name is the same; the
mechanism is not.

## 85. Port the insert the run reads, and make the other's absence loud **[PLAN.md step 7d; `process-evap-fvv` 64 of 64, worst cell 7.517e-06, on its first run]**

`MultidayTankVaporVentingCalculator` fills `WeightedMeanBaseRate` from two
disjoint inserts. The OPERATING one weights `emissionRateByAge` at modes 150 and
300 and multiplies mode 300 by TVV-8's `tempAdj x rvpAdj`. The COLD-SOAK one
writes mode 151 from TVV-2 to TVV-7 — the peak cold-soak hour, tank vapour at two
altitudes, the multi-day soak fold, two venting equation forms — and nothing else
reads that chain. On an on-network link mode 151's operating-mode fraction is 0,
and the zero is COMPUTED: E2 weights every soak mode by `1 − fractionOfOperating`,
and A10 makes `SourceHours` equal `SHO` there.

So the document ports the operating insert, whose inputs are real — including
`TankFuelGenerator`, which the default database ships empty and every snapshot
captures empty, and on which the answer turns — and does NOT port the cold-soak
insert. That is a decision about what a run can check, and it is only honest if
three things hold, all of which do here:

* the zero that stands in for the missing half is a computed weight, not an
  assumed one (§80, §18.2);
* the specification computes the missing half for this snapshot and measures it
  contributing exactly nothing (docs/evap-fvv.md §0.3), so "absent" and "zero"
  were compared rather than presumed equal;
* the one input that would give it weight — an off-network link — is asserted
  away by the shape check (`run_offNetworkLinkCount` is 0), so the day a RunSpec
  selects road type 1 this document fails instead of quietly dropping half a
  calculator.

**A linear interpolation over a knot table is a weight on every knot.** TVV-8
reads `evapRVPTemperatureAdjustment` at the fuel's RVP by finding the greatest
knot at or below it and the least one above, with sentinel rows at RVP −1 and
1000 that carry the end knots outward. Finding "the" knot either side and reading
its terms needs a key computed per (county, month, fuel), and a join key must be
a 1-D column. So the two brackets are found by VALUE — `max_sum` and `min_sum`
over the fuel's knots, each with a one-sided filter — and the interpolated term
is `SUM(bracketing_knot_weight x term)` over the knots, the weight asking whether
a knot IS one of the brackets (an equality in the expression, which is exact
because a bracket is one of the knots' own values). The one-sided arms are the
sentinels. At 7.7 psi E85's constant term is 1.263935, which is
`1.390541 + 0.7 x (1.209675 − 1.390541)`.

**The first version put the brackets on the knot rows and took the 7c spike
down.** Each knot carried its previous and next RVP — tidy, and a computed
relation over the knot axis. The tire-wear snapshot mounts that table with ZERO
rows, and a computed relation of length 0 is F56: the spike panicked, and with
it the thin per-fixture document and the index-set rename check, while every
national run passed. **Put nothing computed on an axis some catalogue can mount
empty**; contract over it instead, where a length of 0 is the additive identity
(§80).

## 86. A fixture's declarations are the second domain's first work, and "the first bin containing it" is a first-row gather **[PLAN.md step 7e; `nr-logging-county` byte-identical to its fixture, `nr-lawn-garden-county` 1,936 of 1,936, `nr-recreational-county` 1,010 of 1,010]**

**Lift a fixture by listing what it DECLARED, not what it read.** A fixture over
one execution database may write facts about its run into itself, and
`fixtures/nr-logging-county.esm` wrote five: the six equipment points as a
`const` array of source types, the county, state, year and day as parameters,
the base year, a technology window of IDs 100..199, and a block size of 4 in the
output relation. Every table it read was a drop-in from the default database --
19 of 21 copied whole into the execution database, the other two already joined
-- so the port was exactly those five turned into reads, and the fixture's own
output was the oracle for the refactor: 144 rows, byte-identical over every
emitted column. The equipment points are a SELECTION (§22's rank over a mask),
and the mask is the moves.rs loader's, rule for rule, including the quirk that
an empty `/SOURCE CATEGORY/` packet runs everything.

**A second run with no fixture finds the rules the first could not tell apart.**
Both of `nr-lawn-garden-county`'s were in a lookup that `nr-logging-county` exercises
at points where the two readings agree:

* NONROAD's SCC fallback chain (exact, equipment root, family root) is walked per
  (pollutant, technology), not once per point. Logging's SCCs rate every
  technology at one level, so "which level has a row for this point" and "which
  level has a row for this technology" never differed.
* A point whose hp sits ON a bin boundary takes the LOWER bin. An inclusive
  `hpMin <= hp <= hpMax` filter sums both, and no logging point sat on a boundary;
  37 national points do.

**"The first row satisfying P" is a `min_sum` over the row index, then a gather.**
`tech_rate<Level>Row = min over e of e` under the join and the containment filter
gives the first matching row, or +Inf; `index(emr_meanBaseRate, min(row, n))`
reads it, the `min` keeping the index in range on the branch the `ifelse`
discards. That is only "the lowest bin" because the file is ASCENDING in hpMin
within each (SCC, technology, pollutant) -- measured, with no two bins
overlapping -- so it is a claim about the table, and the description says so.
Where no row index is at hand the same rule is two passes, a `min_sum` of the
lower bound and a filter `hpMin <= that` (`point_mixBinLow`), which selects one
bin because bounds are distinct. Either way no key is 3-D: the level is chosen
by an `ifelse` over three 1-D-keyed aggregates, never by joining on a computed
per-(point, pollutant, technology) SCC (F57).

**A species a model WRITES moves its inputs onto the axis of what it always
has.** SO2 is not a rate NONROAD reads: `clcems.f` writes it from BSFC and the
un-adjusted THC product, both of which it loads whatever the run selects. Keyed
on the SELECTED pollutants, a run choosing SO2 without THC -- `nr-agriculture-state`
does -- would find no THC to subtract. So the rate and deterioration lookups
live on `rated_pp_rows`, the five pollutant-processes NONROAD rates, and the
selected axis reads them by join; SO2's branch is one `ifelse` in
`tech_hourlyEmission`, factored so the product associates exactly as it did
inline and `nr-logging-county` stayed byte-identical.

**The precision is the root's until F60 closes.** The model declares
`Float32` and a mounted leaf's `domain` is ignored, so each RunSpec declares it
again and `run-tests.sh` requires that deleting it costs `nr-logging-county` its
four binary64 rows. A run whose rows depend on a residual's sign (`agedist.f`)
is exactly where a silent precision change becomes a missing cohort.

## 87. A state is a county MOVES builds, and a one-ulp input can move a cohort a thousandfold **[PLAN.md step 7e; `nr-construction-state` 2,355 of 2,355, `nr-pleasure-craft-state` 440 of 440, the county runs unchanged]**

**Build the pseudo-geography in the model, as a generalization the real one
reduces to.** A state-level RunSpec runs at county stateID x 1000, zone
stateID x 10000 and fuel region stateID, and `PreAggSTATE.sql` and
`DefaultDataMaker` write all three into the execution database; the default
database has none of them. Each became a weight or a union that is exactly the
old formula at a real county -- `zone_runWeight` is 1 on the county's own zone,
`sup_isRunSupply` selects the rows the old join selected, and the default
supply rows carry share 0 wherever a fuel type has supply -- so the county runs
kept their bytes, and that is the check that the generalization did not move
them. `nr-logging-county` stayed byte-identical to its fixture through it.

**Aggregate the way the SQL aggregates, not the way the statistic reads.**
`PreAggSTATE.sql` writes a state's temperature as `Sum(temperature x actFract)`
with `actFract = ROUND(start, 6) / ROUND(state sum, 6)`; the rounded shares sum
to 0.9999322 for Michigan, and nothing renormalizes. Divided by its weights --
the natural spelling of a weighted mean -- the temperature is 0.0049 degF high;
divided by the thirteen hours NONROAD averages over, it is MOVES's. The tell
was the pattern, not the size: every 4-stroke gasoline THC, CO and NOx cell off
by exactly the ratio its temperature coefficient predicts, and every PM, SO2 and
2-stroke cell exact (§84's lesson from the other side).

**A default the database cannot satisfy falls through to another default.**
`DefaultDataMaker` gives the pseudo-region gasoline formulation 12, the default
database has no formulation 12, and the `.OPT` packet's func A then reads
formulation 10's sulfur, while its oxygen query, which has no fallback, reads 0.
SO2 was 0 until that rule was written; nothing else was wrong.

**When a few whole cohorts are off, replicate the fold before suspecting it.**
35 cells in six SCCs were off by up to 9.2e-04, every pollutant of a cohort by
one ratio, at model years whose `agedist.f` residual is a cancellation (a
fraction of 5.9e-05 between neighbours of 0.02), and a binary64 run moved exactly
those cells. A numpy binary32 replica fed the model's own inputs matched the
model bit for bit -- so the fold was right and an INPUT was one ulp off, and the
input was `linear_series_interpolation` associating `(dv x dy) / dx` where
`grwfac.f` computes `(dv / dx) x dy`. Algebra that is the same over the reals
is not the same in the declared precision (§11.3.1), and a shared template is
where one wrong association lives in every document at once.

**The output is what the calculator EMITS, not what the RunSpec selects.**
`nr-pleasure-craft-state` selects benzene at three permeation processes and
NONROAD has no slot for it, so MOVESOutput has no row; a width declared from the
selection emitted 330 rows of zeros. The width is its own declared and checked
number, `n_outputPolProcess`, the fourth.

## 88. A pre-aggregation is a fold the model computes, and a fold the oracle cannot see needs a probe that can **[PLAN.md step 7e; `nr-commercial-nation` 908 of 908 at 6.729e-06, the five earlier runs byte-identical]**

**Read the execution database before the Fortran.** NONROAD's `prc1st.f` reads
a population record per region, and the national tables have no state 0
anywhere, so a nation run reads like a sum of state runs. It is not:
`PreAggNATION.sql` rewrites every table NONROAD reads as one state 0 before the
run. The execution database a snapshot carries says which, in a query --
`nrbaseyearequippopulation` there has one stateID, 0 -- and the fold is then
the SQL, which fits on a page. Measure each fold against the execution database
in pandas before porting it, as §66 measured the month's pre-aggregation
weights; all five here were exact, and the run reproduced on its first
evaluation.

**Fold the way the SQL folds: before the rounding, not after.** The population
is summed across states and THEN rounded to the `.POP` file's tenth; a sum of
rounded state rows is a different number. The growth pattern is a `min` and
not a sum -- so `point_growthPatternID` is a `min_sum`, which is also the
single-row answer off the nation. And a fold that REPLACES a table is a union
with a relabelled key: `rma_stateID` is -1, which matches nothing, on the half
of `nrMonthAllocation` ∪ `nrUSMonthAllocation` the run does not have, so every
lookup against it is the lookup it was.

**An oracle that cannot distinguish a rule has not tested it.** Every SCC
`nr-commercial-nation` selects has one growth-finder row and a flat 1/12 month
fraction, so the minimum and the table swap could both have been wrong and the
run would have reproduced. Ask of each rule whether this run's data can tell it
from its absence (§23, and §86's first-bin rule). Where it cannot, a PROBE can:
another run's selections at the same scale, compared against a replica of the
SQL rather than against an oracle, until a run whose oracle discriminates it
arrives. Record which run that will be.

## 89. A clamp, a renormalization and a bin choice apply where the FILE puts them **[PLAN.md step 7e; the five 213-SCC runs]**

**Find the record before placing the operation.** NONROAD's arithmetic was ported
from `clcems.f` and was right; three of the four diesel rules were in the code
AROUND it -- the reader that renormalizes a technology set (`rdtech_moves.f`), the
loader that clamps an output record (`NonroadOutputDataLoader`), and the lookup
that chooses a rate row (`fndefc.f`). Each applies at the granularity of the
record a file carries: the output file has a technology column, so the clamp is
per (cohort, technology) and not per cohort. Before writing a `max(0, .)`, a
division by a sum or a tie-break, open the writer or reader of the file it
belongs to and list the record's key columns.

**NONROAD reads what MOVES printed, not what the table holds.** MOVES hands NONROAD
text files, and a writer's format is part of the arithmetic: the SEASON file's
`%10.3f` turns six-decimal month fractions into sets that sum to 0.996..1.002,
which `rdseas.f` then renormalizes. Wherever a file's format keeps fewer digits
than the table, the model reads the printed value (`printed_decimal`, like
`pop_file_rounding` before it for the POP file's `%17.1f`).

**A rule that was right at one boundary is a sample of the rule.** "On a boundary
the lower bin wins" reproduced two runs, because at 25 hp the lower bin IS the
nearest; at 11 hp it is not. When a rule is inferred from where it fired, read
the code that decides it before generalizing (§86's first-bin rule, §88's
probes).

**Attribute a residual to its contributors.** When a small share of a large
correction is off, run the model with the correction switched off, take the
difference per cohort, split it by each contributor's weight, and regress the
gap on the contributors. The technologies whose rate can go negative took all of
it, which named the clamp. Narrow the RunSpec for the loop -- one sector's
diesel, `runspecfueltype` 23 -- and an 11-minute run is a 3-minute one.

**A guard that normalization would hide becomes a number.** The listed mix
summing to 1 was the check that one hp bin's set had been read; dividing by the
sum makes every cohort's mix sum to 1 whatever was read. `run_mixSetsOffOne`
keeps the check, as a count held at zero, at the tolerance the Fortran itself
warns at.

## 90. A precision artifact is diagnosed before it is accepted, and then ported or excepted by its cost **[PLAN.md step 7e; `nr-railroad-support-nation` 23,108 of 23,108]**

**Diagnose first, every time.** A residual of 1e-4 looks like reference-precision noise, and most of 7e's were not noise. The Tier 4 PM clamp and the renormalized technology sets were logic, and both were found by refusing to accept a residual nobody had explained. A tolerance is loosened only for a cause that has been MEASURED, and against the reference itself where it can be run. moves.rs `generate-corpus.sh` runs a nonroad RunSpec through an instrumented NONROAD in about a minute.

**What a reference reader sees is part of the arithmetic.** §89 said NONROAD reads what MOVES printed. It also reads only what its parser's window holds: `rdnropt.f` reads each `/OPTIONS/` value from columns 21-30, so a weight-percent sulfur keeps seven decimals (`opt_option_value`). When a value enters a reference through a file, read the writer's format AND the reader's field width.

**Then port it or except it, by cost.** A precision artifact the format can replicate exactly and cheaply is ported, and the gate stays strict (the sulfur window, the SEASON file's `%10.3f`, the POP file's `%17.1f`). One the format cannot express gets a `cell_exception` in `tolerance.toml`. It names the cohort's key, carries the measurement in a comment and the cause in `why`, and is refused once it matches nothing. Never a per-fixture `rel`, which would loosen thousands of cells to cover four. The railroad's binary32 population sum is the first: it crosses a `.POP` rounding boundary, and the format has no binary64-to-binary32 conversion (EarthSciAST#536).

**A cancellation turns ulps into percent.** agedist.f's newest cohort is a residual, `totpop/baspop - frcsum`. Where sales fall, both terms are about 1.32 and their difference is about 0.001, so one ulp of the minuend is 1e-4 of the cohort. A cohort that is off alone, by one factor across all its pollutants, in a year when its equipment's growth turned negative, is that residual. Look at the fold's inputs (`baspop`, the growth factors), not at the fold (§87).

## 91. A derived pollutant is a root and a multiplier, and the multiplier is exactly 1 where it does not apply **[PLAN.md step 7e; `nr-airtoxics-lawn-garden-county` 14,036 of 14,036 on the port's first run, the other runs unchanged to the byte]**

**Redirect the lookup, not the pipeline.** NONROAD's two speciation calculators
scale three rated blocks -- THC, PM10, and fuel consumption -- into twenty-five
more pollutants. The dense layout already computes a rated block per (cohort,
selection, technology), clamped per technology record (§89). So a derived
selection does not get its own chain. It reads its ROOT's rate, deterioration,
adjustment and clamp (`rpp_ratedPolProcessID`), and its record is multiplied by
`pp_directMultiplier + tech_speciatedMultiplier`. Seven existing equations
changed one variable name, and nothing else in the rated chain moved.

**Make the identity exact, not approximate.** For every selection the chain
already emitted, the root is the selection itself, the direct part is a `1.0`
from a share column, and the speciated part is a sum of products with a `0.0`
coefficient. In binary32 `x × (1 + 0)` is `x` bit for bit, so a document serving
twelve runs takes the new chain without moving the eleven that don't use it.
Check that by the bytes of the emitted CSV, not by tolerance: a refactor that is
right within 2e-5 can still be wrong.

**A key that is per (point, technology) becomes an AXIS.** `nrHPCategory` is
looked up by (hp bin, technology), and every ratio table joins on it. A
`join.on` key has to be one column, and a 2-D value cannot be one. The category
is therefore a two-row axis (`hp_category_rows`). The tables are read per
(technology, category, subtype), the supply shares fold the subtype into a fuel
type, and the point gathers through a presence mask (`tech_isHPCategory`). A
pair with no category row then matches nothing. That is the Go's zero value,
written as a value and not as a branch.

**The needed set is the selection, so gate on it where the source does.**
`flagRequiredPollutantProcesses` returns early for NONROAD, and a block that is
not needed is never produced. TOG sums only the selected summands, NonHAPTOG
subtracts only the selected integrated species, and a toxic needs its input
block selected. Each gate is a selection flag on the term it governs
(`run_*IsSelected`), not a branch on the output pollutant. One consequence is
that the national `nrIntegratedSpecies` has 14 rows where the execution copy had
9: the five extras are unselected and subtract nothing.

## 92. A run's DOMAIN is a layer of its catalogue, and each table's merge rule is stated where it is declared **[PLAN.md step 7f; `scale-project` 125 of 125 at 9.123e-06 on its first run, the twenty DEFAULT-domain runs unchanged to the byte]**

**The input database is the domain's, so the domain is a document.** MOVES reads
a scale-input database only for a SINGLE-county or PROJECT run, and merges it
before the default database. A mounting document cannot override a mounted one's
`data_sources` (§59.4), so any table whose merged content depends on the domain
has to be declared ABOVE the default database. The chain is therefore four
documents, not three: the RunSpec, its domain (`moves-onroad.esm` for DEFAULT, one
per scale-input database in `inputs/`), `onroad/default-database.esm`, and the
model. The domain document also declares the RunSpec's `<modeldomain>`
(`db_runspecdomain`), because MOVES pairs the two. Twenty RunSpecs kept their
`ref` and their bytes.

**Two kinds of merge, two places to write them.** Where MOVES does not copy the
default table at all in a domain (`Link` in PROJECT; `FuelSupply`, `IMCoverage` in
SINGLE and PROJECT; `sourceTypeYear` and `sourceTypeAgeDistribution` in SINGLE),
the merge is a REPLACE, and the domain document declares the domain's file. That
is MOVES's rule written as a choice of file, not a shortcut. Where it copies both
and the input wins by primary key, the merge is a ROW MERGE. Then both sources are
read and the precedence is written in the model. Every computed variable goes on
the DEFAULT side's axis, because the input side's axis is mounted with zero rows
in every DEFAULT-domain catalogue, and a computed relation over it is F56.

**A row merge over identical rows needs no declaration, and that is measured.**
39 of `washtenaw-project`'s 45 tables are `INSERT ... SELECT` copies of default
rows at the run's keys. The model reads them from the default database through
the joins that already select them. That holds only while the copies ARE the
default's rows. The first scale-input database that changes one has to move the
table's declaration into its domain document. The measurement that licenses it is
a diff of the execution database against the default at nine significant digits.

**The domain switches the model in one variable, and a guard counts what it does
not switch.** `run_isProjectDomain` selects ProjectTAG's SHO, the link's own
operating-mode distribution, and link-level output columns. Each one is an
`ifelse` whose other arm is the old expression, so a DEFAULT run computes exactly
what it did. `run_domainUnported` counts every PROJECT-domain path the model does
not take: a second link or county, a non-running process, an out-of-bounds
bracket. The shape check asserts it 0. None of those would fail on its own: each
emits a plausible number.

**A probe that does not evaluate has measured nothing.** `no-link-join` had read
a compile failure as "the numbers moved" since 7c′. A probe is now required to
evaluate before its difference counts.

## 93. A county database is two kinds of row merge, and a merge that ADDS keys is read as a union **[PLAN.md step 7f; `process-extended-idle-single` 50 of 50 at 6.529e-06]**

§92 said a row merge is both sources read with the precedence written in the
model. A county database showed that there are two kinds, and they are read
differently.

**A merge whose input rows SHADOW default rows** -- Washtenaw's `zoneRoadType`,
whose four allocation factors are the default's truncated to twelve decimals -- is
computed on the default side's axis: per default row, does an input row share its
whole key, and if so take the input's value (`zrt_mergedSHOAllocFactor`). Every
DEFAULT-domain run mounts the input side empty, so every default value survives
bit for bit. An input row whose key the default lacks would be ADDED, which a
relation on the default axis cannot see, so it is counted (`run_zoneRoadTypeRowsAdded`,
into `run_domainUnported`).

**A merge whose input rows ADD keys** -- the county's `hotellingActivityDistribution`
at zone 261610 beside the default's at 990000 -- cannot be computed on either axis
alone. It is read as a UNION inside every aggregate that consumes it: one `faq` over
the input rows plus one over the default rows that survive (`had_isMerged`: not
shadowed, and not a PROJECT run, into which MOVES copies no default rows of this
table). No variable is shaped by the input axis, because it is mounted empty in
most catalogues (F56); only reductions range over it.

**Precedence is sometimes MOVES's own logic, not the merge's.** Which zone's
distribution a hotelling run reads is not the merge: it is
`findHotellingActivityDistributionZoneIDToUse`'s merit order over the MERGED table
(own zone, state, nation), and it picks ONE zone for every fuel type. Write the
merge and the choice as separate steps, because a county database that states
diesel alone leaves CNG unscaled rather than falling back to the national row --
and the oracle says so.

**Measure which kind a table is before declaring it.** Of `washtenaw_cdb`'s fifteen
tables, five are identical copies (read from the default, §92), three are
REPLACE-by-copy (identical at every key read), two shadow, one adds keys, and four
merge over an empty default side and are simply the domain's tables. The diff that
says which is the execution database against the default database at the run's
keys, at full precision: nine significant digits called the truncated allocation
factors identical.

## 94. A process the calculator writes is a block with its own pair relation **[PLAN.md step 7f; `process-apu-single` 91 of 91 at 5.848e-06, on its first run]**

The RunSpec selects auxiliary power (91); MOVES emits auxiliary power AND shore
power (93), because its calculator relabels the shore-power mode's block. The
selection is not the output's pollutant-process set, as §81's prerequisites showed
from the other side.

Three ways were priced. Adding 93 to the pollutant-process axis would re-key every
`rspp_*` relation on a data-bound extent. A second slot on `ratecohort_rows` would
quadruple its O(n²) prefix count and put every existing rank one rewrite away from
moving. The one taken is a SEPARATE pair relation for the calculator's blocks,
ranked after the selected blocks' pairs, with the output's key and value columns
reading each relation through its own rank. Every RunSpec that writes no such block
leaves that relation entirely non-emitting, which is what keeps the 21 others
byte-identical without having to argue it.

The split itself is at the operating mode, where the reference makes it, and not a
share of the total: the own block's contraction drops the retagged modes and a
parallel contraction keeps only them, through the same adjustment tail written once
as a template. A share computed after the fact would be the same number only while
every adjustment is multiplicative and mode-independent, which A/C is not.

## 95. A domain twin is a differential test of the merge, and a chained pollutant needs its parent selected **[PLAN.md step 7f; the four DEFAULT-domain `process-*` twins, 91, 100, 684 and 300 rows, on their first runs and with no model change]**

§92 and §93 say every merge is written with both sides read and the input side
mounted empty in a DEFAULT-domain catalogue. A RunSpec whose selections are a
`-single` run's, mounted on `moves-onroad.esm` instead of a county document, runs
every one of those merges at its DEFAULT arm, and its oracle against the county
twin's says where the county database matters. For the four twins the DEFAULT/`-single`
ratio is 1 (within the six-digit rendering) on every diesel cell, 0 on the 50
shore-power cells and 0.800 on the CNG extended-idle cells -- exactly the rows where
`washtenaw_cdb` states something the default does not (3% shore power from 2010, no
CNG row). Compute that ratio before diagnosing a twin: a residual where the ratio is 1
is not the merge's, and a ratio other than 1 where the two databases agree is a key
the merge drops.

**A selection the reference expects to be expanded is the RunSpec's to supply.**
Atmospheric CO2 at extended idle (9090) alone emitted nothing: CO2AE converts the
energy BaseRateCalculator writes, BaseRateGenerator builds rates only for selected
pollutant-processes, and the default database has no 9090 rate. Nothing in MOVES adds
9190 for it, so the fixture names 9190 beside 9090, and the model needs nothing new:
the edge is the CO2AE edge list's (§77), not a `runspecchainedto` row. Before
concluding that a process emits nothing, check that every calculator upstream of it
has a selected pollutant-process to run on (§81 is the converse: a prerequisite the
execution database carries that the RunSpec did not ask for).

## 96. An index is not an identifier, an out-of-range index selects nothing, and a road type is a location **[PLAN.md step 7d; `expand-fullyear` 1375 of 1375 at 1.056e-05 and `expand-counties-large` 875 of 875 at 1.140e-05, no model change; `expand-roadtypes` pending]**

§81 and §16.5 say a RunSpec XML's `<month key>` is a 0-based index into the sorted
`MonthOfAnyYear` IDs, so a document reads the execution database's `runspecmonth` and
never the XML. `expand-fullyear` is the run where that rule changes the COUNT and not
just the labels: its XML lists keys 1 to 12, which are monthIDs 2 to 12 and an index
past the twelve-row list. Canonical resolves that index to nothing and adds no month,
as it does for an out-of-range `<day key>`, so the run has eleven months, and key 0,
January, was never in the XML. Measure that before explaining it: every month-keyed
table MOVES cut to the run (`runspecmonth`, `zoneMonthHour`, `SHO`, `starts`,
`totalIdleFraction` and ten more) carries 2..12, and only the three not cut to it
(`monthOfAnyYear` and two nonroad month allocations) carry 1..12. A month missing
from the OUTPUT can be a dropped output row or a month never selected, and the
execution database tells the two apart; the oracle alone does not.

**A wider selection on an axis the model already has costs only its selections.**
Seven counties in seven fuel regions and eleven months reproduced on their first runs
with fourteen `url_template`s each, because `n_runspeccounty` and `n_runspecmonth` are
discovered extents and nothing in the model names three counties or four months. A
document that needed a binding change to go from three counties to seven would have
been carrying a width in the model.

**A road type is a location, not a selection of rates.** In MOVES the geography is the
LINK, a (county, road type) pair, and the model keys its location by county and reads
one on-network road type per run (`run_roadTypeID` over `run_rows`). Price the
promotion by forward closure (PLAN.md §7.3.43): 284 of 1517 variables reach
`run_roadTypeID`, and 119 of them only through the geography ids the county already
determines (`run_zoneID`, `run_stateID`, ...), so keying those by county and adding the
road type only where it varies -- the drive-cycle operating-mode stack, the activity
VMT and speed, the SHO allocation, the output blocks -- is 165 equations where a
link-keyed location would be 284 and would multiply the tank-temperature trip relation
by the road-type count. Off-network idle is then a sum ACROSS that axis, not a value
on it: road type 1's running-exhaust SHO is computed from the on-network road types'
SHO and driving-idle fractions, so it needs the axis before it can be written.

## 98. A year is folded into the relation that already varies with it, and appended to the ones that do not **[PLAN.md §7.3.44; `expand-multiyear` 241 of 241 at 8.277e-06 on the promotion's first run, the single-year runs unchanged]**

The forward closure from `run_yearID` reached 395 of 1,036 equations, three times the
source type's, and the edit was 160. The difference is a choice about WHERE a new
axis goes, and the rule is one line: **a relation whose rows already depend on the new
key takes it as a factor of its own row index; a relation that does not takes it as a
trailing axis.**

1. **Fold it where the rows already move.** A cohort is an age at a year, so the
   cohort grid's model year is year less age and every rate keyed by model year moves
   with the year. Making the year the grid's SLOWEST factor -- `n_agecategory x
   n_runspecsourcefueltype x n_runspecyear`, decoded by `coh_yearOrdinal` -- gives the
   199 cohort-shaped equations their year without a textual edit, and at one year the
   grid is the old one row for row, so no earlier run can see it (§64.5). The
   activity relation is folded the same way and for the same reason
   (`act_modelYearID`).
2. **Append it everywhere else, by name.** The fuel supply, the evaporative weights,
   the hotelling and start totals and the population are per year but not per cohort.
   They gain `runspecyear_rows` as their LAST axis, so an elementwise equation over
   them needs only its `shape` edited (operands align by index-set name), and a faq
   gains one output index, one range and one trailing argument on each promoted read.
   That part is regular enough to apply with a refactoring pass and to check with an
   axis checker -- every index read compared against the index set its symbol ranges
   over -- which found one pre-existing misread (`run_evTemperatureIsSuppressed` reads
   `rst_sourceTypeID` at the one-row `run_rows` symbol; harmless while no run's heat
   index reaches 67 degF, and left as found).
3. **A key that would become rank 2 gets a pair relation.** A join key is a rank-1
   column. `run_fuelRegionID` is keyed by county AND fuel year, so appending the year
   would make it a rank-2 key that fourteen fuel-supply joins read; it moves instead
   onto `runspeccountyyear_rows`, county-fastest, and the joins reach it through
   `rcy_countyOrdinal` and `rcy_yearOrdinal`. Folding the activity relation (item 1)
   is the same rule seen from the other side: `act_modelYearID` is a join key.
4. **Readers join at their row's year, and a self-join pairs by it.** Each of the 28
   rate-side readers of a per-year relation adds `rt_yearOrdinal <-> year_ordinal`;
   each per-year SUM over activity rows adds `act_yearOrdinal <-> year_ordinal`.
   Self-joins are where a forgotten year is silent: the fuel-usage join pairs a bin
   with the bins of the same vehicle by (source type, model year, engine technology,
   regulatory class), and model year 2012 is age 3 at 2015 and age 8 at 2020. Without
   `bin_yearOrdinal` in that key the two years' bins would pair with each other. Scan
   every join whose two sides are both cohort-derived on a non-ordinal key; this was
   the only one.

A check that counts DISTINCT output keys has to count by the new axis too: 241
cohorts are 135 (source type, fuel, model year) triples, and
`tools/check-runspec-shape.py`'s cohort key gained `out_yearID`.

## 100. A county database of the default's own rows is a differential test, and a RunSpec can select more than it names **[PLAN.md step 7f; `scale-county` pending, its oracle equal to `expand-roadtypes`' on all 729 rows]**

**Build a county database from the default's rows, and the SINGLE run becomes the
DEFAULT run's twin.** §95 made the twin from the RunSpec side, the same selections at
the other domain. `scale-county` makes it from the database side: every County Data
Manager table is a `LIKE` + `SELECT` copy of the default's rows at the run's keys, and
the oracle then equals the DEFAULT run's at every cell. That turns the county
database's document into something checkable without its own run: mount it under a
RunSpec that already reproduces (`process-crankcase-start`) and its relation must be
byte-identical. It was. The diff that says which tables a domain changes is still the
execution database against the default's (§93); against a twin's execution database it
is shorter, because the run's own selections cancel.

**Copy the alternative the default populates.** Several importers accept one of a set
of tables and refuse two: Starts, StartsPerDay or StartsPerDayPerVehicle;
totalIdleFraction or the idle adjustments; HPMSVtypeYear or the daily and source-type
VMT forms. The member the default database fills is the one whose branch MOVES takes at
DEFAULT scale, so copying any other changes the arithmetic, not just the input.

**A RunSpec can select more than it names, and the execution database says what.**
Road type 1 beside a running process makes MOVES select every road type, because
off-network idle is computed from all of them: `runspecroadtype` holds five rows for a
RunSpec that names two, and the output has running rows on all five. And it can name
less than it appears to: 92, 93 and 99 are not MOVES5 pollutant-processes, and
`runspecpollutantprocess` holds only 9101, 9102 and 9190. As §81 says of
prerequisites, read the run's scope from the execution database, never the XML.

**A validation error can be the harness's and not the run's.** The pinned SIF cannot
construct GenericImporter (its Swing parts need `libharfbuzz.so.0`), which logs an
`ERROR:` during domain-database validation and is then skipped; MOVES runs to
completion. Establish completeness with one validation-ON run, read for "Done
performing domain database validation.", and capture with validation skipped.

## 101. A road type folds into the rate relation's block and is appended to the activity, because a road type is where a process happens **[PLAN.md §7.3.46; `expand-roadtypes` 729 of 729 at 1.009e-05 on the promotion's first run, the 33 earlier runs unchanged to the byte]**

§98's rule decided it -- fold the new key into a relation whose rows already move
with it, append it to one whose rows do not -- and the road type is the first key
it splits down the middle.

1. **The rate relation already had a road type, one per pollutant-process.**
   `rspp_rateRoadTypeID` put every pollutant-process on exactly one road type, and
   the output's blocks were pollutant-processes. Running energy on five road types
   is one pollutant-process on five, so the BLOCK becomes a (pollutant-process,
   road type) pair, `polprocroad_rows`, and the rate relation's leading factor is
   the pair. It is road-type-FASTEST: at one selected road type the pair relation
   is the pollutant-process relation row for row, and on the eight runs that select
   road types 1 and 4, where each pollutant-process has one live block, every
   emitted block keeps its rank. The old per-pollutant-process ordinal becomes a
   gather through the block (`rt_polProcOrdinal`), so the twenty rate readers of
   `rspp_*` kept their joins; only what is per block -- the operating-mode weights,
   the activity, the emitted rank, the shore-power keep -- moved.
2. **A block is live where its pollutant-process lives.** `rspp_rateRoadTypeID`
   still classes a pollutant-process -- road type 1, or the run's on-network road
   types, which it names by a representative (`run_roadTypeID`, now the lowest
   selected one) -- and `ppr_occursOnRoad` expands the class onto the axis: an
   off-network process on road type 1, an on-network one on every selected
   on-network road type, running exhaust on road type 1 as well when that block is
   off-network idle. The three-rung chain closure needed no change, which is what a
   class buys over a value.
3. **The activity is not folded, because it is not the rate's to fold.** The
   activity relation carries SHO, starts and hotelling hours, and only SHO has a
   road type. Folding the axis into `activity_rows` would have made every per-day
   and per-year SUM over activity rows -- the start totals, the hotelling totals,
   the evaporative SHO totals -- count each road type once: the too-wide join of
   the memory rule, with nothing to see but a number four times too big on a run
   that selects four. So the VMT-to-SHO chain (`run_roadTypeVMTFraction`,
   `run_shoAllocFactor`, `act_*`) and the speed-bin stack under the operating-mode
   weights (`asd_*`, `asb_*`) take a trailing `runspecroadtype_rows` axis by name,
   and their readers index it at the block's road type.
4. **A row that already carries the key needs no axis.** A `driveScheduleAssoc` row
   HAS a road type, so `dsa_*` stayed two-dimensional and its selection became "a
   road type the run selects"; the bracketing above it (`asb_*`) reads the row's
   own road type through a key pair. The same is true of the zone: it is a
   county's, found in `Zone` by county, not through the county's link on one road
   type. That cut is what made the price 165 equations of a 284-equation closure,
   and the edit 69 changed and 30 added.
5. **Self-joins pair by the new key, again.** The chain generations, NonHAPTOG, the
   SPM splits and the four presence passes join rate rows to rate rows by bin or
   cohort; without `rt_roadTypeOrdinal` in each pair, road type 1's parent feeds
   road type 4's child. Eleven clauses, one rule (§98 item 4).
6. **A per-pollutant-process count over rate rows now counts blocks.**
   `pp_selectedBinCount` and `pp_rateBinCount` read the first road type, since the
   rate selection does not vary with it; the run-level presence tests became ORs
   over a pollutant-process's blocks. A label the comparator does not read can
   still move a byte-identical CSV: `out_SHO` on a start row read the run's one
   on-network SHO, and on the runs that select road types 1 and 4 it would have
   read road type 1's off-network idle instead. It keeps the label it had, and the
   description says why.

The shape check's block key gained the road type: `expand-roadtypes` emits six
blocks of two (pollutantID, processID) pairs.

## 102. Off-network idle is a sum across the road-type axis, and a run can select road types it does not name **[PLAN.md §7.3.46; `expand-roadtypes`' road type 1, 125 of 125 at 8e-06; `scale-county` 729 of 729]**

**ONI is TotalActivityGenerator step 190c**, written after the axis because it reads
the axis whole. Per activity row, county, source type and month,

    SHO(1) = max( S (tif - SD/S) / (1 - tif), 0 ),    tif < 1 and S > 0, else 0

with `S` the on-network SHO summed over the selected road types, `SD` the same
weighted by each road type's driving-idle fraction, and `tif` `totalIdleFraction`
at the county's state's idle region, the county type, the source type, month, day
type and model-year window (`lib/onroad_activity.esm` `off_network_idle_sho`).

* **The driving-idle fraction is a contraction of what the rate side already
  computes.** BaseRateGenerator's `drivingIdleFraction` is the idle share of a road
  type's speed-weighted operating-mode distribution (`drivecycle.rs:427-492`), so it
  is `asd_effectiveFraction x asb_modeFraction` summed over speed bins and the
  source type's vehicles, at mode 1 over all modes. The Java counts modes 1 and 501;
  no drive-cycle second is 501. A road type with no fraction drops out of both sums,
  as the SQL's inner join does.
* **Its rate is the idle mode alone.** BaseRateGenerator writes running exhaust's
  road-1 rates as opMode 1 at fraction 1 and avgSpeedFraction 1, for process 1 only
  (`drivecycle.rs:511-541`), so on an off-network idle block `pp_W` is 1 at Idling
  and the rest of the chain is unchanged -- the A/C adjustment included.
* **Selected or all, answered from the source.** The SQL sums `SHO` over the
  zone's links with `roadTypeID <> 1` in the EXECUTION database
  (`TotalActivityGenerator.java`, the step-190 insert into `SHO`, inventory and
  rates branches alike), and the execution `Link` is cut to the run's road types:
  the SELECTED ones. But `ExecutionRunSpec.getRoadTypes()` adds every road type
  whenever a non-project run selects road type 1 and running exhaust ("Off-Network
  Idle requires all roadtypes", `ExecutionRunSpec.java` ~980-1004), so the sum is
  over all four in every run that has ONI. The model sums the selected ones, which
  is the SQL, and reads the selection from the execution database (§81, §100).
* **What it does not port is counted.** AdjustTotalIdleFraction.sql replaces
  `totalIdleFraction` from `idleModelYearGrouping` and scales it by `idleMonthAdjust`
  and `idleDayAdjust`; all three are empty in the default database and in
  Washtenaw's county database, are mounted, and their rows are counted by
  `run_domainUnported` on a run that computes ONI. An evaporative process beside
  road type 1 (MOVES writes SHP rows there) and one on a second on-network road type
  stay in `run_selectionUnported`; `run_offNetworkLinkCount` now counts evaporative
  BLOCKS on road type 1, the only ones that would read SHP.

## 103. A second output table is a second relation over the first, and the scale that asks for it is a declaration whose default is the inventory **[PLAN.md §7.3.47; `scale-rates` and `rates-minimal` 2000 of 2000 at 1.163e-05 on the first run, the 35 earlier runs unchanged to the byte]**

MOVES's Rates scale (MESOSCALE_LOOKUP) writes no MOVESOutput a run keeps; it writes
`RatePerDistance`, a rate per mile per (cohort, speed bin). Three rules came out of
porting it.

1. **The scale is a RunSpec declaration, not a mode.** `<modelscale>` is stated in
   no table, so a Rates RunSpec binds `n_ratesScale` = 1 beside `n_outputRate`, and
   the default 0 is every other run. The rate relation is ADDED, never switched
   into: `out_*` is computed as before and is simply not the oracle at Rates
   scale. The memory rule "a second mode is a per-run selection" holds in its
   strongest form -- the inventory computes nothing differently, so the 35 runs
   that do not set it are the byte-for-byte check of the refactor that the new
   relation needed (`pp_WSpeedBins` now reads a factored `pp_WBin`).
2. **Size the new axis to ONE outside its mode, never to zero.** The speed-bin
   axis is `1 + n_ratesScale x (n_avgspeedbin - 1)`: the 16 discovered bins at
   Rates scale and a single bin otherwise, so an inventory run computes the rate
   relation over one bin it never emits instead of over an empty axis (F56). The
   cost at inventory scale is one more rate-row-sized relation; the wall clock and
   peak RSS of the 35 runs are in PLAN.md §7.3.47.
3. **A second output table reads its keys from the first.** `rateoutput_rows` is
   the output relation with the bin fastest; every column MOVES copies from
   BaseRateOutput is the output row's own and is read through one ordinal join
   (`lib/rates.esm`'s `rate_output_column`), so the rate table cannot disagree with
   the inventory about which cohorts, blocks, months and days exist. Only what is
   NEW is computed: the link MOVES synthesizes for the bin
   (`mesoscale_lookup_link_id`, `(zoneID*10 + roadTypeID)*100 + avgSpeedBinID`,
   `ExecutionRunSpec.createMesoscaleLookupLinks`), the bin, the hour's
   meteorology, BaseRateOutput's `regClassID` 0, and the rate.

**The harness names a run's oracle by its table.** A runspec's `oracle` source
points at the output-database table it is judged on; `run-tests.sh` reads the
table name off that url, emits `out_*` for `movesoutput` and `rpd_*` for
`rateperdistance`, and passes `--table` to `compare-output.py`, which takes the
table's column contract from `tolerance.toml` -- `[compare]` for MOVESOutput,
`[oracle_table.<table>]` otherwise, refusing a table with none. Every gate is the
same. The shape check reads the prefix off the emitted header and, for a rate
table, multiplies by the bins, takes the ZONE from the link (the table has no
county column) and asserts each link's last two digits are its bin.

**What Rates scale does not port is counted** (`run_ratesUnported`, inside
`run_selectionUnported`): any emitted block but a directly rated running-exhaust
block on an on-network road type -- starts, evaporative and hotelling processes,
brake and tire wear, chained pollutants and off-network idle write RatePerStart,
RatePerVehicle, RatePerProfile, RatePerHour or a chained BaseRateOutput, none of
which is built -- a PROJECT domain, and any time aggregation. Distance units other
than miles are a RunSpec setting no table records.

## 104. At Rates scale a rate is per vehicle of its own fuel, and the measurement that found it was a ratio that had to be constant **[PLAN.md §7.3.47]**

`BaseRateGenerator` step 008 divides the source-bin-weighted rate by
`SUM(sbd.SourceBinActivityFraction)` at Rates scale and by 1 at inventory scale,
and turns off `sumSBD` for running exhaust: an inventory rate is the cohort's SHARE
of the source type's fleet, a Rates rate is the rate of a vehicle OF THAT FUEL.

* **The normalizer is the SQL's group, over its inner join.**
  `rtMode_activityFractionSum` sums the used fractions of the rate row's siblings
  -- same block, cohort and regulatory class, the GROUP BY -- that have a rate at
  the operating mode (`rtMode_rateRows`), because a bin with no rate row at a mode
  is not in that mode's sum. On this corpus' passenger cars every cohort is one
  source bin, so the normalized rate is that bin's rate; the general form is what
  the SQL says and costs one self-join.
* **Found by a ratio, before porting.** Against `expand-day`'s weekday --
  same county, year, month, hour, source type and road type --
  `emissionQuant / (N x Sum_bin avgSpeedFraction x avgBinSpeed x ratePerDistance)`
  had to be the same for every fuel type of a model year if the rate were the
  inventory's rate normalized by `N`; it was, to 5e-06, and the port reproduced on
  its first run. A ratio that is constant along the axis a hypothesis says it
  should be is a cheaper test than a reimplementation, and it pins the units too
  (Million BTU, then per mile).
* **Two snapshots of one RunSpec disagree in one cell, and the model cannot be
  asked to pick.** `scale-rates` and `rates-minimal` agree in 1999 of 2000 cells;
  diesel, model year 2016, at link 261610412 (55 mph) is 0.00299941 in one and
  0.00299940 in the other, exactly one unit of the sixth significant digit a MySQL
  FLOAT is rendered to (3.3e-06 relative). It is MOVES's own run-to-run noise --
  most likely its float32 accumulations in a different order (the worker bundles and their GROUP BY sums are not ordered) landing on the other side of a
  display boundary -- and the model's 0.0029994027 sits between them, 9.1e-07 from
  one and 2.4e-06 from the other. Both runs are kept and both reproduce; a
  tolerance that could tell them apart would be testing MOVES's scheduling.

## 105. A bare literal is a pure number, so a selection's branches share one unit and a unit hidden in a number is written down **[EarthSciAST esm-spec §4.8.6; PR #1, the `units_dimensionless_literal_mismatch` warnings, 69 to 0]**

esm-spec §4.8.6 reads a bare nonzero literal as dimensionless. Today that is a
warning, `units_dimensionless_literal_mismatch`; at the next major esm version it
is an error. The repository carried 69 warning sites, nearly all of them one of
six `lib/` templates seen through the documents that mount them. Each was a
real statement the document had not made, and each fix is `× 1.0` or `/ 1.0`
in binary64, so no number moved.

* **A unit hidden in a fitted constant is written on a `const` of value 1.**
  The Goff-Gratch polynomial is log10(e / 1 kPa), so `saturation_vapor_pressure`
  multiplies its power of ten by `const(1.0, "kPa")`. Before §4.8.6 a symbolic
  power was undeterminable and `PH2O` validated declared `kPa`, `degF` or `K`
  alike; now it is checked.
* **A selection's branches share one unit, so a code-dispatched conversion is
  one template per arm.** §58.3's rule, the unit at the call site and never on
  the template, relied on an `ifelse` that only looked at its first branch.
  `unitcf.f` returns `hp`, `gal/h` or a pure 1 depending on the emission-rate
  code, and no single template can type all three. So `lib/conversion.esm` has
  `hp_hour_unit_conversion` and `gallon_unit_conversion`, the pass-throughs are
  the identity, and the call site, which already knew its code, picks one.
  Every call site in the repository was g/hp-hr and had bound placeholders, such
  as the median life as the fuel density, to the arm it never reached; those
  bindings are gone.
* **A source's own dimensional quirk is ported as the reading it makes.**
  NONROAD's gallons arm of `acttmp` is 1/(2*uselif), a reciprocal of hours
  that the Fortran then uses as hours. `annual_activity_hours` writes it
  `1 h / (2 × (uselif / 1 h))`, the number it computes in the unit it is used
  as, so all three arms are `h` and the selection is checked.
* **A pure number with a polymorphic consumer stays a number; a typed
  consumer gets a typed twin.** `kilojoules_per_million_btu` is divided into
  `rspp_unitDivisor`-style selections whose other arm is 1, so it stays
  unitless. `million_btu_energy` is the same number times one kJ, for the two
  callers whose numerator is declared `kJ`.
* **A column that holds two units gets its unit where the row kind is known**
  (§57.8). `NrAirToxics`' `run_gallonsFactor` is `gal/g`, as `nft_gallonsFactor`
  in nonroad/model.esm already was. `rat_multiplier` holds a g/gal rate on a rate
  row and a ratio on a ratio row, so `tox_unitFactor`'s rate arm multiplies by
  `const(1.0, "g/gal")`.
* **A threshold is named once.** The codemod's mechanical rewrite put
  `const(-1.0, "mi/(h*s)")` in three places and `const(72.0, "degF")` in two.
  Those values are now `brakeRate1Sec`, `brakeRate3Sec` and `idleCeilingMph`,
  the names onroad/model.esm reads them under, and lib/adjustments.esm's
  `ev_temperature_reference`. The EV temperature quadratic was the standard one
  about a different reference, so both are now `centred_quadratic_adjustment`.
