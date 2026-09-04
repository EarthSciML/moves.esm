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

**The cost of the working form: index sets do not merge across it** (finding
F2), so an assembly restates the axes of every file it mounts. That redundancy
is exactly what the merge exists to prevent, so
`tools/check-conventions.py` compares the two definitions and fails on
disagreement **[checked]** — the loader's conflict detection, performed by the
harness.

Running `esm test` on an assembly runs the mounted leaves' own tests too, under
the mount. That is a feature: it is the check that mounting preserved their
meaning.

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
  the runtime and the number of assertions is free.** Measured on
  `fixtures/nr-logging-county.esm` at 144 rows: one `simulate` is 17 s, and
  `esm test` is 29 × that — `--filter` narrows what is REPORTED, not what is
  evaluated (8 m 11 s filtered to one test, against 8 m 32 s for all of them).
  The whole suite is 12 m 22 s, up from 4 m 47 s at twelve output rows. The
  consequence for authoring is not "write fewer tests" — each of the 29 is a
  distinct claim and merging them would make a failure less diagnosable — but
  it does mean a test added for a single extra assertion is an expensive way to
  buy it, and that profiling belongs on `simulate` rather than on `test`.

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

### 16.6 What Phase 3 did not do, and why it is in the specification

`mixed-onroad` has **no fixture**, and that is a decision rather than an
unfinished edge. `docs/mixed-onroad.md` §7.3 shows that everything in the
250-row chain is computable from the snapshot's input tables except one
relation of 46 numbers — the speed-bin-weighted drive-cycle operating-mode
distribution, which canonical MOVES computes inside its worker and drops. §7.4
gives the reasoning: a document emitting 250 correctly-keyed rows carrying an
uncomputed rate fails the per-cell gate for a shape `[shortfall]`'s
`emitted_rows` / `missing_keys` / `extra_keys` record cannot express, and a
document reading the reference's own `baserate_1_2020` passes the gate by
transcribing the answer. Neither is a fidelity test, and §13's rule — a fixture
stage that says what it did not compare is worth more than a green one that
read nothing — applies to *whether to add the stage* as much as to what it
reports.

What replaces it: the four components check every stage that can be checked
without the snapshot, against numbers §6 read out of it; and
`./run-onroad-oracle.sh` extracts §6.5 and reproduces all 82 rows of `sho` and
all 250 of `MOVESOutput` from the snapshot to 4.1 × 10⁻⁶ and 8.2 × 10⁻⁶, with
the base rate read from the reference and the output saying so on every run.

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
