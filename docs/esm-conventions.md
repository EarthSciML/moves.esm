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
records fourteen things the format or the toolchain will not do, each watched
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
`> 0` comparison. The honest body, `true`, is in the schema's evaluable-core set
and panics at evaluation (finding F10).

**A relation cannot be joined to itself** **[Phase 2]**. Two `ranges` over one
index set leave every key column unresolvable, because resolution is by axis
(finding F11) — a build error, not a silent zero. Three joins here want a
self-join: `nrstatesurrogate`'s county row against its state row, the growth
series against its own previous year, the age walk against the previous age.
Each materializes a **second relation over a second index set** instead
(`surrogate_target_rows`, `growth_factor_rows` beside `growth_query_rows`), or
evaluates the same lookup twice at two arguments.

**An unmatched row contributes the additive identity, and is still emitted.**
This is not merely a semantic footnote — it is the modelling rule PLAN.md §1.6.1
settles. The BSFC carrier row in `components/deteriorated_emission_rate.esm` has
no deterioration partner, reads 0, and stays in the output. A document that
reproduced the Fortran's `modfrc <= 0` row suppression would emit 140 keys
against the snapshot's 144 and fail `require_exact_key_set`. Emit every key the
joins produce; emit the zero.

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
nested `subsystems: {Rates: {ref}}` mount renames a leaf's variables but leaves
its `join.on` clause naming the old bare names, so any leaf with a data-column
join — every relational leaf — fails to build once mounted (finding F1). Revisit
this section when F1 is fixed: the nested form is the one §4.7 documents, and it
is the one that merges index sets.

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

ESM evaluates in binary64; `moves.rs`'s NONROAD port is bit-exact `real*4`, and
`domain.element_type` is document-wide, so per-expression single-precision
rounding is not reproducible. This is measured, not projected (PLAN.md §1.6.1):
in binary64 four cells of `nr-logging-county` compute to exactly zero, carrying
2.4×10⁻⁵ g out of 5,146 g, so per-pollutant sums still agree to 2.6×10⁻⁶.

**The rule that follows is a modelling rule, not a tolerance one.** Do not
reproduce Fortran control flow that suppresses rows. Emit every key the joins
produce and let the value be whatever it computes. Then the emitted key set
matches the snapshot exactly and `require_exact_key_set = true` stays. Do not
add a per-key allow-list; that was considered and rejected.

## 11. Data comes from `data_sources` — but not yet

`sources/nr_logging_county.esm` is a source-catalog file (esm-spec §2:
`data_sources` only, no component, not mountable) declaring the snapshot tables
with their `reader_options`. **Nothing consumes it**, because no CLI subcommand
wires a `PrepareProvider` at this toolchain: a data-fed parameter silently keeps
its default and an aggregate over it silently sums to zero (`build-esm.sh`,
KNOWN BLOCKER). A component wired to it today would produce a green test that
compared nothing.

Two things that hold regardless, and that Phase 2 should not re-derive:

* **`float_columns` is mandatory, on every table.** Verified against the
  snapshot parquet: `zonemonthhour.temperature`, `nrsourceusetype.hpAvg`,
  `nremissionrate.meanBaseRate`, `nrdeterioration.DFCoefficient` and
  `MOVESOutput.emissionQuant` are all physically `string` — 12-place decimal
  text for byte-reproducibility — even though the sidecar `.meta.json` calls
  them `float64`.
* **`hp` is not a unit the registry knows.** `W`, `kW`, `degF`, `g`, `h`, `yr`
  and `1` are. Horsepower-based quantities carry no `units` and record the
  native unit in their `description`; an emission factor in g/hp-hr is
  unspellable and does the same.

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
* **A quantity the format cannot compute enters as data, with an independent
  cross-check** **[Phase 2]**. `agedist.f`'s thirty-year fold is a recurrence
  and has no spelling (finding F12), so
  `components/age_distribution.esm` carries its result as a column — and
  asserts that the column sums to `G(2020)/G(1990)`, which
  `components/growth_index.esm` derives from the index series by a different
  route. A carried column without such a check is a number nobody is testing.
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

## 13. What `./run-tests.sh` guarantees

Nine stages, in order: the comparator's own falsification suite; schema
`validate`; the conventions above **[checked]**; every inline test;
`parse → emit → parse` fidelity; the join-gate scaling ratio; the
known-limitation tripwire; every `data_sources` catalog against the Parquet
files it names (`tools/check-sources.py`); the fixture comparison. It must stay green at every commit, and it must stay
*honest* — an empty fixture stage that says why it is empty is worth more than a
green one that read nothing.

The tripwire runs with the opposite polarity to everything else: it fails when a
`docs/findings/` repro starts **passing**, because that means an upstream defect
is fixed and a workaround in this tree is now dead weight. Read
`docs/findings/README.md` when it fires.

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

Three things in the chain are not in the documents because the format or the
toolchain cannot hold them. Each is a finding with a repro, and each has a
visible place in the `.esm` rather than a silent substitution.

| | What | Where it shows |
|---|---|---|
| **F12** | `agedist.f`'s 30-year fold is a recurrence — no spelling | `components/age_distribution.esm`'s `age_grownModelYearFraction` is a data column, cross-checked against the growth stage's cumulative ratio |
| **F9** | a relational document cannot be written to a file | nothing emits rows; the chain is proved by inline assertions only |
| **—** | no `PrepareProvider` in the CLI | every relation is a transcription of the snapshot; `sources/` declares the real tables and is checked against them |

The rule the three share: **say it in the document, at the point where a reader
would otherwise assume the number was computed.** A carried column's
description names the finding, the assembly's description names both blockers,
and the source catalog says what it will prove once ingest lands. A workaround
that is not written down is indistinguishable from a bug.

The corresponding rule for the *fixture* is PLAN.md §1.6.1's and it has not
changed: emit every key the joins produce, emit the zero, and do not reproduce
Fortran control flow that suppresses rows.
