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
* **An output relation carries its key as COLUMNS, never as axes** **[Phase 2]**.
  This is the same rule, and it is what makes a *ragged* key set expressible.
  `nr-logging-county`'s 144 rows are 36 `(SCC, modelYearID)` pairs × 4
  pollutants, and the 36 are not a rectangle: the three SCCs span 3, 4 and 29
  model years, each set by that equipment point's `nyrlif`. A shared
  `[SCC × modelYear × pollutant]` grid carries 348 keys against the snapshot's
  144 — a `require_exact_key_set` failure, and the mirror of the binary64
  `modfrc ≤ 0` case that emits four too few. `components/movesoutput_aggregation.esm`
  is one `output_rows` axis with `out_SCC`, `out_modelYearID` and
  `out_polProcessID` beside the value, so adding the other two SCCs is adding
  rows. The `ragged` index-set kind the schema advertises for exactly this
  ignores its own member factor and cannot address a parent's members
  (finding F14).
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

**A semi-join is `bool_and_or` with a numeric body** **[Phase 2]**. *Does a
matching row exist* is the shape every precomputed key needs — the two SCC
ladders, state-default precedence, the `getind.f` year rule, the RunSpec sector
and fuel selections. Spell it `"semiring": "bool_and_or"` with `"expr": 1.0`,
giving 1 on a match and 0 on none, and bind it at the call site as an explicit
`> 0` comparison. The body is `true`: a presence test carries no value. (It read
`1.0` for as long as `true` panicked at evaluation — F10, now fixed upstream in
EarthSciAST `a1a592ecf`, which also refused the other nine core-but-unevaluable
ops at build rather than letting them reach `unreachable!()`.)

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

**An assembly restates the UNION of its leaves' enums** **[Phase 2] [checked]**.
`enums` merge across a top-level `models` `{ref}` mount into one registry, first
declaration wins, and a colliding value is applied **silently** — two leaves
declaring `probe.Symbol` as 1 and 2 both read 1 (finding F13). Where the winner
merely lacks a symbol it is loud instead, which is how it surfaces in practice:
`geographic_allocation.esm` and `fuel_properties.esm` both declare
`nonroad_fuel_type` and only one has CNG. So an assembly declares every symbol
every leaf it mounts declares, and `tools/check-conventions.py` compares them
symbol by symbol — the same conflict check it performs for index sets, for the
same reason and with more at stake, since a wrong pollutant identifier relabels
data rather than failing.

**An `enums` block is file-local and does not cross a template import**
(esm-spec §9.3; finding F3). So each component declares the enums it uses, and a
*library* cannot name its own constants symbolically. Two routes, both in use:

* a **zero-parameter constant-fragment template** (§9.6.1) for a code the
  library itself branches on — `lib/conversion.esm`'s
  `activity_unit_g_per_hp_hr`;
* a **parameter the call site binds to an `enum` op** in its own file — every
  identifier `lib/identifiers.esm` touches.

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
longer exists cannot fail, which reads like coverage. Five rules remain, and the
enum one stays, because `enums` still do not conflict-check (F13, open).

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
binary; they agree now, and that paragraph of it is stale.

Measured here at the `3aa046d65` rebuild: `esm test ./components ./runs …` goes
**1444 assertions to 913**, and all 531 of the difference are leaves that were
being re-asserted under the four assemblies — `nr_logging_county_run` 296 → 9,
`mixed_onroad_run` 163 → 30, `evap_leaks_run` 107 → 26, `micro_exhaust_run`
39 → 9. **No assertion went unrun.** Each of the nineteen mounted leaves is its
own test target under `components/`, and every one of those files' own counts is
unchanged. What is gone is the *second*, under-the-mount evaluation of them. An
assertion an assembly wants to make about a mounted leaf is now the assembly's
own to write, which §18 already describes how to do — and which is what F21
makes awkward, since a scoped name still cannot be an assertion `variable`.

## 6. Reused shapes are `expression_templates` in `lib/`, imported by reference

The eight shapes `docs/nonroad-logging-county.md` §4 names live once, in five
template-library files grouped by the stage of the chain that reaches for them:

| file | shapes |
|---|---|
| `lib/identifiers.esm` | `pol_process_id`, `scc_zero_tail` |
| `lib/keys.esm` | `scc_equipment_chain_key`, `scc_lookup_ladder_key`, `state_default_precedence` (§4.5, §4.6) |
| `lib/emission_factors.esm` | `deterioration_age`, `deterioration_factor` (§4.1), `carbon_balance_ef` (§4.8) |
| `lib/adjustments.esm` | `exhaust_temperature_adjustment` (§4.2), `oxygenate_adjustment` (§4.3), `im_blend` |
| `lib/conversion.esm` | `unit_conversion` (§4.4), `temporal_scale` (§4.7), `annual_activity_hours`, the unit codes, `CVTTON` and its inverse |
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
  EMISSION-rate unit (`emission_unit_g_per_hp_hr`) is what `unitcf.f` selects
  on; an ACTIVITY unit (`activity_unit_hours_per_year`) is what `modyr.f`
  selects on; the `g/gallon` branch reads both. Phase 1 named the first pair
  `activity_unit_*`, which was wrong and is renamed.
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
the distinct tuples — validates but materializes empty (finding F5), and
EarthSciAST's own fixture for it says it "validates against the schema with no
evaluator". Do not reach for it until F5's repro goes green.

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
* **`hp` is not a unit the registry knows.** `W`, `kW`, `degF`, `g`, `h`, `yr`
  and `1` are. So an emission factor in g/hp-hr carries no `units` and names the
  unit in its `description` — and because no factor in the roll-up product
  carries a unit, neither can the product: `out_emissionQuant` is grams,
  declared unitless, and says so.

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
drive existed, and the year diesel passenger cars stopped. Finding F14's flat-
relation workaround applies unchanged.

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

**F21: a scoped name is not an assertable variable.** `esm-schema.json`'s
`Assertion.variable` documents a scoped reference (`"subsystem.X"`), and the
assertion path cannot resolve one: `variable 'Emissions.emis_weightedMeanBaseRate'
is not declared in model 'Rollup'`. The same name works in the same document as a
`join.on` key column, as an operand of an ordinary equation, as an `expr`
operand and as a `plots` `variable`. Measured on **both** mount forms with an
identical message, so no spelling of the mount avoids it.

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
which validates and materialises empty; `fixtures/nr-logging-county.esm`
declares `output_rows: 12` for the same reason. What Phase 4 adds is the rest of
the discipline, and it is three parts:

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
whose LHS is an array-shaped unknown `V` and whose `aggregate` body reads
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
contraction at all, and an `aggregate` with an `output_idx` and no `reduce` is
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
That is the shape a `ragged` index set advertises, and a `ragged` set does not
evaluate (finding **F14**). A rectangular `[SCC × modelYear]` output axis emits
348 keys where the snapshot has 144, and `tolerance.toml`'s
`require_exact_key_set` is not negotiable. This section is the shape that works,
because the next NONROAD sector will need it and the reasoning does not survive
being rediscovered.

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
  **F11** is fixed (EarthSciAST `107a15152`). Two `aggregate` ranges over one
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
  inclusive prefix count is an ungated `aggregate` over two ranges of one index
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

§22 built a rank because a `ragged` index set does not evaluate (finding
**F14**) and a rectangular axis emits keys the snapshot does not have. Three
onroad fixtures then reused that shape at a level up: the output relation is
pollutant-process-major blocks of `n_outputCohort × n_runspecday`, and an output
row is addressed as *(block, day, cohort rank)*.

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
  is F5 and F14, which §22 and §31 already solve with a rectangular grid, a mask
  and a global rank. Priced: a 37,216 × 22 grid for TTG-2, and about 45 million
  cells to recover TTG-4b's 182,532 rows. **A cost, not a limitation** — and a
  document that had said so would have described a slice someone could schedule,
  where "blocked by F28" described one nobody could.

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

**Two blocks do NOT cross, and `esm validate` does not say so.**

| block | may live in the child | must be restated by the mounting document |
|---|---|---|
| `variables`, `equations`, `update` bindings | yes | no |
| `data_sources` | yes | no |
| `metaparameters` | **no** | **yes** |
| `index_sets` | yes, and ignored | **yes, verbatim** |

The index-set half is the one that will catch an author out, because the
document validates. F2 merges a top-level `{ref}`'s index sets into the
registry `esm validate` reads; the ingesting build reads a different registry —
`file.index_sets`, the mounting document's own — and reports

```
aggregate range 'g' references index set 'spike_agegroup_rows', which is not
declared in the document `index_sets` registry
```

Finding F46. **Restate the child's `index_sets` in the mounting document, and
say in a comment that it is load-bearing**, or the next reader will delete
them as duplication.

### 49.1 Per-fixture configuration needs no override mechanism, and here is what it does need

`{"ref": …, "metaparameters": …}` is refused by the schema, and so is
`{"ref": …, "tests": …}`: a `{ref}` entry is a closed shape that takes nothing
else. Two channels remain, and between them they are enough:

* **a `data_sources` key.** The shared document binds `source: "runspec_day"`
  and never declares it; each fixture declares that key against its own table.
  This is how a runspec's *selections* travel.
* **a metaparameter, read as a number.** A metaparameter declared in the
  mounting document is readable in a ref'd child's equation as an ordinary
  scalar — measured: `metaEcho = n_spike_agegroup` evaluates to 7. The fixture
  has to declare its metaparameters anyway (§49's table), so this channel costs
  nothing. Verified for `type: "integer"`; a `number` metaparameter validates
  and was not evaluated.

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
while a *parent-shaped* component cannot be a test target either, because it
does not load alone. Finding F47. So all three ways to assert are closed:

| spelling | refused by |
|---|---|
| an asserting model beside the mount | `document holds several models` (F45) |
| `tests` beside the `{ref}` | the schema: `Additional properties are not allowed` |
| an assertion naming `Child.value` | F21 |

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
