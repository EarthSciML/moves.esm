# Authoring conventions for MOVES `.esm` documents

The representation spine (PLAN.md §3, Phase 1). Every later phase inherits
these decisions, so this document is the reference and `lib/`, `components/`,
`runs/` and `gates/` are the worked proof of each one. Where a rule can be
checked by a machine it is, in `tools/check-conventions.py`, run by
`./run-tests.sh` — the rules below that a review would otherwise have to
eyeball are marked **[checked]**.

Two companions: `docs/nonroad-logging-county.md` is the verified port
specification these conventions were fitted to, and `docs/findings/README.md`
records six things the format or the toolchain will not do, each with a repro
that `run-tests.sh` watches.

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
   full nested loop. Measured in `gates/`: 1.0×10¹⁰ candidate pairs gated in
   365 ms against 4.0×10⁶ ungated in 4,571 ms.
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
| `lib/conversion.esm` | `unit_conversion` (§4.4), `temporal_scale` (§4.7) |

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

Six stages, in order: schema `validate`; the conventions above **[checked]**;
every inline test; the join-gate scaling ratio; the known-limitation tripwire;
the fixture comparison. It must stay green at every commit, and it must stay
*honest* — an empty fixture stage that says why it is empty is worth more than a
green one that read nothing.

The tripwire runs with the opposite polarity to everything else: it fails when a
`docs/findings/` repro starts **passing**, because that means an upstream defect
is fixed and a workaround in this tree is now dead weight. Read
`docs/findings/README.md` when it fires.
