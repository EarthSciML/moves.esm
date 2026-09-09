# `process-nox-speciation` — computation specification

The port specification for the first fixture that computes a **criteria
pollutant**, written to the method of `docs/process-brakewear.md`: the input
inventory determined from evidence, the chain with source lines into
`../moves.rs`, every join with its exact key pairs, and worked examples whose
numbers can be checked by hand.

The speciation itself is three lines of arithmetic. `NOCalculator` and
`NO2Calculator` do not model NO, NO2 or HONO from first principles; each species
is its total-NOx parent scaled by a tabulated `NOxRatio`:

```
species emissionQuant = NOx emissionQuant x NOxRatio
```

Both classes are **chained** onto `BaseRateCalculator`
(`calculator-dag.json`: `subscribes_directly: false`, `depends_on:
["BaseRateCalculator"]`), and their SQL "Processing" sections are the same two
joins and the same multiply — `crates/moves-calculators/src/calculators/nitrogen_oxide.rs`
ports them once, as `compute_nitrogen_oxide`, and gives each Java class a thin
wrapper. The registration split is real and comes from the DAG, not from
prose: on process 1 **`NOCalculator` registers pollutants 32 (NO) and 34
(HONO)** and **`NO2Calculator` registers pollutant 33 (NO2)**.

So the chain is `docs/process-brakewear.md`'s, with a different ratio table.
**The work is in the parent.** No fixture before this one computed a criteria
pollutant, and total NOx on Running Exhaust needs five things the energy and
particulate rungs never touched:

1. the rate lives in **`emissionratebyage`**, not `emissionrate` — which is
   empty in this snapshot — and carries an **`ageGroupID`** key that decides a
   row SET as well as a value (§2.2);
2. the **criteria fuel effect** scales the rate per supplied fuel
   *formulation* and is market-share weighted back to the fuel type; it is
   worth a factor of two on the newest gasoline cohorts (§2.3);
3. the temperature adjustment takes its **NOx branch**, which is a temperature
   term *times* a **humidity correction** selected by a text column (§2.4);
4. the emitted blocks are **different sizes** — 124 and three of 104 — and a
   species survives only where its ratio exists **and its parent survived**,
   which is a self-join and not a property of any one table (§2.5, §3.3);
5. three of the calculator's stages are **empty in this snapshot** and one more
   is **clamped dead**, so they are named rather than claimed (§7.2).

---

## 0. The fixture at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/process-nox-speciation.xml` |
| Model | ONROAD, `modelscale` `Inv` (inventory), `modeldomain` `DEFAULT` |
| Geography | county 26161 (Washtenaw, Michigan), zone 261610, link 2616104 |
| Time | year 2020, month **8**, hour **7**, day types **2 (weekend) and 5 (weekday)** |
| Vehicles | sourceTypeID 21 (passenger car); fuel types **1, 2, 5, 9** |
| Road | roadTypeID 4 (urban restricted access) |
| Pollutant/process | **301** (Oxides of Nitrogen × Running Exhaust) and its three chained species **3201** (NO), **3301** (NO2) and **3401** (HONO) |
| Model years | 1980–2020 (41) |
| Output | `db__out_process_nox_speciation__movesoutput`, **872 rows** |
| Output units | **grams** for all four pollutants; `outputtimestep` **Hour** |
| Calculator path | `TotalActivityGenerator` → `SourceBinDistributionGenerator` → `BaseRateGenerator` → `BaseRateCalculator` → **`NOCalculator`**, **`NO2Calculator`** → output aggregation |
| Snapshot | 373 tables, **246 non-empty** |

### 0.1 The RunSpec on disk does not describe the captured run

The same rule as `docs/mixed-onroad.md` §0.1, and for the same reason: the XML's
`<month key>`, `<beginhour key>` and `<day key>` are canonical `RunSpecXML`
**0-based indices into sorted ID lists**, not identifiers. The XML says month 7,
hour 6, day 5; the execution database's `runspecmonth`, `runspechour` and
`runspecday` say month 8, hour 7, and day types 2 **and** 5. The execution
database is the authority.

### 0.2 Why 872 rows, and why the four blocks are not the same size

872 = (124 + 104 + 104 + 104) × 2 day types.

* **124** cohorts of total NOx. 125 of the 164 (model year, fuel type)
  candidates pass `stmyFraction > 0`; the one that is selected and still not
  emitted is **model year 2000, electricity**, whose age group at analysis year
  2020 is 2099 and for which `emissionratebyage` carries no fuel-type-9 row.
  Model years 2001–2020 electricity *are* emitted, at exactly zero. This is a
  row-set consequence of a rate KEY, which is the sort of thing a row count
  finds and a sum does not.
* **104** cohorts of each species — the 124 minus all 20 electricity ones,
  because `nono2ratio` has rows for fuel types 1, 2 and 5 and none for 9. The
  three species drop the *same* twenty, and each species' cohort set is a strict
  subset of the parent's; `run-nox-speciation-oracle.sh` asserts both, because
  "104" alone is compatible with dropping the wrong twenty.

`sbweightedemissionratebyage` is 2,852 rows = 23 operating modes × 124, which is
the same 124 arrived at by a route this document does not read.

---

## 1. Input inventory

### 1.1 The tables `mixed-onroad` and `process-brakewear` already read

The whole activity chain (S1–S9), cohort structure and fuel-usage rebase
(S10–S12), drive-cycle operating-mode weights, and the pollutant-process ×
cohort rate relation are unchanged and not restated here. Read
`docs/mixed-onroad.md` §§1–3 and `docs/process-brakewear.md` §2.2.

Two of those tables are read for **new columns**:

| table | new column | why |
|---|---|---|
| `zonemonthhour` | `specificHumidity`, `molWaterFraction` | the two humidity corrections' arguments (§2.4) |
| `agecategory` | `ageGroupID` *as a rate key* | it selected an EV efficiency before; it now keys the rate itself (§2.2) |

### 1.2 The ten tables this fixture adds

| table | rows | role |
|---|---:|---|
| `emissionratebyage` | 218,316 | the rate, keyed by source bin **and age group** (§2.2) |
| `nono2ratio` | 333 | the species-over-NOx ratio (§2.5) |
| `criteriaratio` | 733 | the criteria fuel effect, per fuel formulation (§2.3) |
| `county` | 1 | `GPAFract`, the fuel-effect blend weight (§2.3) |
| `regioncounty` | 2 | which fuel region the county is in (§3.2) |
| `fuelsupply` | 5 | which formulations that region supplies, and at what market share |
| `fuelformulation` | 2,158 | formulation → fuel subtype |
| `fuelsubtype` | 13 | fuel subtype → fuel type |
| `noxhumidityadjust` | 3 | the humidity correction, one row per combusting fuel type (§2.4) |
| `pollutantprocessmappedmodelyear` | 444 | *already read*, but now also resolves the ratio's model-year GROUP (§2.5) |

### 1.3 What is NOT an input

`emissionrate` (0 rows here), `baseratebyage_1_2020`, `baserateoutput`,
`sbweightedemissionratebyage`, `sourcebindistribution`, `sho` and `MOVESOutput`
are generator or expected output. None is a `data_sources` entry. Values out of
the first, third, fifth and sixth appear as `expected` in the inline tests,
which is the opposite direction.

`generalfuelratioexpression` (45 rows) is **not read**, and that is a decision
with a reason. It carries the criteria fuel effects as closed-form expression
STRINGS over fuel properties — `if(sulfurLevel>30, ((exp(-4.7644... ))...)` —
which `FuelEffectsGenerator` evaluates into `criteriaratio`, together with a
live Complex Model and sulfur model for model years ≤ 2000. `moves.rs` gates
that whole reconstruction on `criteriaRatio` being empty and records that "the
snapshot/onroad path ships it captured"
(`crates/moves-calculators/src/generators/fueleffectsgenerator/criteria.rs`).
This fixture is on the snapshot path, so `criteriaratio` is an input here
exactly as it is there. Porting `FuelEffectsGenerator` is a separate rung and
is **not** claimed in the calculator path above.

---

## 2. The computation chain

### 2.1 What is unchanged

S1–S14 of `docs/mixed-onroad.md`, and `docs/process-brakewear.md`'s rate
relation: `rate_rows` is the four pollutant-processes crossed with the 41 × 4
cohort candidate grid, 656 rows, every factor a discovered extent. Every rate
column is read back through `rt_polProcOrdinal` / `rt_cohortOrdinal`, so nothing
about the pollutant-process or the cohort is restated on it.

### 2.2 The rate is age-dependent, and `emissionrate` is empty

`emissionrate` has **0 rows** in this snapshot and `emissionratebyage` has
218,316, all `polProcessID` 301. MOVES keeps age-dependent rates in the second
table, and running-exhaust NOx is one; energy consumption and brake/tire wear
are not, which is why every earlier fixture read the first.

The rate join therefore gains a seventh key column:

```
rt_polProcessID       = erba_polProcessID
om_opModeID           = erba_opModeID
rt_shortModYrGroupID  = erba_shortModYrGroupID
rt_regClassID         = erba_regClassID
rt_engTechID          = erba_engTechID
rt_fuelTypeID         = erba_fuelTypeID
rt_ageGroupID         = erba_ageGroupID          <-- new
```

Seven age groups (3, 405, 607, 809, 1014, 1519, 2099) partition the 41 age
categories. **The key decides a row set.** `sbweightedemissionratebyage` carries
groups 3 through 1519 for fuel type 9 and no 2099 rows at all, so the single
electricity cohort whose age is ≥ 20 — model year 2000 — finds no rate and is
not emitted, while 2001–2020 find one and are emitted at rate zero. A document
that kept `emissionrate`'s six-key join and defaulted the age would emit 125
NOx cohorts and 872 would become 878.

### 2.3 The criteria fuel effect

`adjust.rs:475–493`. For process 1 and 2, each per-formulation base rate is
scaled by

```
r = criteriaRatio.ratio + GPAFract x (criteriaRatio.ratioGPA - criteriaRatio.ratio)
```

keyed by `(fuelFormulationID, polProcessID, sourceTypeID, modelYearID, ageID)`,
and `aggregate.rs:38` then sums `rate x marketShare` over the formulations. Both
factors are per-formulation and the base rate is not, so the factor a *shared*
base rate can be multiplied by is the **share-weighted mean of the ratios**:

```
rt_criteriaFactor = SUM over supplied formulations f of ( marketShare_f x r_f )
```

with `r_f = 1` wherever `criteriaratio` has no row — a missing effect, not a
zero one. Washtenaw's `GPAFract` is 0, so the blend selects `ratio`; the blend
is written anyway, because a document that read only `ratio` would pass here and
be wrong in an Alaskan county.

**Which formulations.** `fuelsupply` is keyed by `fuelRegionID`, not by county.
The county's regions come from `regioncounty` — see §3.2 for why that is a
presence flag and not a join — and the formulation is resolved to a fuel type
through `fuelformulation.fuelSubtypeID` and `fuelsubtype.fuelTypeID`. Four of
the five supplied formulations resolve (90 → electricity, 9114 → gasoline,
25003 → diesel, 27002 → E85, each at market share 1.0); the fifth carries fuel
subtype 30, which `fuelsubtype` does not have, and resolves to fuel type 0,
matching no cohort. That is the port's `filter_map` on a missing subtype,
expressed as an inner join that finds nothing.

The effect is not decorative. For source type 21: gasoline model year 2020 is
**0.927694995111**, gasoline 1980 **0.962413415319**, diesel 1980
**1.00385**, and the gasoline series bottoms out at 0.50102. Diesel model years
after 2006 and E85 before 2001 have no row and take 1.

### 2.4 The temperature adjustment takes its NOx branch

`general_temp_adjust` (`adjust.rs:88–143`) is a five-way branch on
`(process, pollutant, fuel type)`. `mixed-onroad` and `process-brakewear` reach
its **EV-energy** arm and its fall-through; this fixture reaches the **NOx** arm,
which no earlier one could:

```
process in {1, 90, 91} and pollutant == 3:
    tempAdjust = fuelType == 2 ? (T > 77 ? 0 : (77 - T) x A)
                               : (T - 75) x (A + (T - 75) x B)
    factor     = (1 + tempAdjust) x k
```

Two things a reader would not guess. The diesel arm is centred on **77 °F** and
switched off above it while every other fuel is the ordinary quadratic about
**75 °F** — two reference temperatures in one branch. And `k`, the humidity
correction, **multiplies** rather than adds.

`k` is `calculate_nox_k` (`adjust.rs:168–188`), and the equation it uses is a
**text column**:

| fuel type | `humidityNOxEq` | `k` |
|---|---|---|
| 1, 5 | `CFR 86` | `1 - A x (clamp(specificHumidity, 3, 17.71) - 10.71)` |
| 2 | `CFR 1065` | `1 / (A x clamp(molWaterFraction, 0.002, 0.035) + B)` |
| 9 | *no row* | `1` |

Both arms fire here. At the run's hour, specific humidity is
10.053684293477 g/kg and the water mole fraction 0.015929059029, so

```
k(gasoline, E85) = 1 - 0.0329 x (10.053684293477 - 10.71) = 1.0215927867446069
k(diesel)        = 1 / (9.953 x 0.015929059029 + 0.832)   = 1.0095483848288278
k(electricity)   = 1
```

**And the temperature term is 0 on every emitted row.** `temperatureadjustment`
carries four rows, all `polProcessID` 301, fuel type 2, **model years
2027–2060** — outside this run's 1980–2020 entirely — so both the exact-regClass
and the regClassID-0 wildcard lookups find nothing and the additive identity
gives A = B = 0. The NOx factor *is* the humidity correction. The two-step
wildcard precedence is still written (`lib/adjustments.esm`'s
`exact_else_wildcard`), because `mixed-onroad` §7 demonstrably needed the second
step and a document that computed only the exact arm reads as incomplete.

The three species are pollutants 32, 33 and 34, so they miss the NOx branch and
take the fall-through quadratic, whose coefficients are also 0: exactly 1.

`humidityTermB` is **NULL on the two CFR 86 rows**, hence NaN. It is read only
inside an aggregate whose join has already restricted the rows to CFR 1065, so
the NaN never reaches an operator. A document that folded both forms into one
expression with a coefficient switch would return NaN for every gasoline cohort
— `ifelse` does not shield an operand from being evaluated.

### 2.5 The chain

`runspecchainedto` carries three rows — 3201 ← 301, 3301 ← 301, 3401 ← 301 —
and the quantity is `process-brakewear`'s expression unchanged: a self-join of
the rate relation on (chained-from pollutant-process, cohort), times the ratio.
On the parent the chain key is 0, `nono2ratio` matches nothing, and the term
vanishes with no branch.

The ratio lookup differs from `pm10emissionratio` in one structural way.
`pm10emissionratio` carries an inclusive model-year **band**;
`nono2ratio` carries a model-year **GROUP**, which
`pollutantprocessmappedmodelyear` must expand — and it must be expanded **for
the species' own `polProcessID`**, not the parent's. Model year 2020 is group
**2020** for 301 and group **20112020** for 3201. `NOCalculation1`'s
`INNER JOIN NOCopyOfPPMY ON modelYearGroupID AND polProcessID` is exactly this;
read in the other direction it is a lookup on the year, giving the join key
`nono2ratio` wants.

**The survival rule is the part that is new.** `NOMOVESOutputTemp1` inner-joins
the ratio to the parent's `MOVESWorkerOutput` rows, so a species row exists where
a ratio exists **and** the parent row does:

```
rt_directSurvives       = rt_isSelected x rt_hasRate
rt_parentDirectSurvives = self-join on (rt_chainInputPolProcessID = rt_polProcessID,
                                        rt_cohortOrdinal = rt_cohortOrdinal)
rt_survives             = rt_directSurvives + rt_hasChainRatio x rt_parentDirectSurvives
```

A sum, not a branch, because no row can satisfy both arms: a chained
pollutant-process has no `emissionratebyage` row and an unchained one has no
`nono2ratio` row. Neither half alone gives 104 — rate row 288 (NO, electricity,
model year 2020) has a surviving parent and no ratio, and rate row 164 (NOx,
electricity, model year 1980) has neither. `process-brakewear` needed none of
this because its PM10 ratio covered every cohort its PM2.5 parent had.

This is a **one-level** chain, which is all these two calculators ask for. MOVES
does have deeper ones (`TOGSpeciationCalculator` chains off the same
`BaseRateCalculator` and downstream of `NOCalculator`), and a fixture that
reached one would have to resolve the parent's own survival first.

---

## 3. Join structure

### 3.1 The joins this fixture adds

| # | left | right | key pairs | semiring |
|---|---|---|---|---|
| J22 | `rate_rows` × `operating_mode_rows` | `emissionratebyage_rows` | polProcess, opMode, shortModYrGroup, regClass, engTech, fuelType, **ageGroup** | sum-product |
| J22a | `rate_rows` | `emissionratebyage_rows` | the same six, without opMode | max |
| J28b | `run_rows` | `zonemonthhour_rows` | zone, month, hour | sum-product |
| J30 | `run_rows` | `county_rows` | county | sum-product |
| J31 | `fuelsupply_rows` | `fuelformulation_rows`, then `fuelsubtype_rows` | formulation; subtype | sum-product |
| J32 | `fuelsupply_rows` | `regioncounty_rows` × `run_rows` | region, county | **max** |
| J33 | `rate_rows` × `fuelsupply_rows` | `criteriaratio_rows` | formulation; polProcess, modelYear, ageID; sourceType | sum-product / max |
| J34 | `rate_rows` | `noxhumidityadjust_rows` | fuelType; **equation code** | sum-product |
| J36 | `rate_rows` | `nono2ratio_rows` | polProcess, fuelType, sourceType, **modelYearGroup** | sum-product / max |
| J37 | `rate_rows` | `rate_rows` (self) | chainInputPolProcess ↔ polProcess, cohortOrdinal ↔ cohortOrdinal | sum-product |
| J38 | `rate_rows` | `pollutantprocessmodelyear_rows` | polProcess, modelYear | sum-product |

### 3.2 Two joins that are not what they look like

**`regioncounty` is a SET, not a relation.** `baseratecalculator/mod.rs:1120–1149`
collects the county's region ids into a `BTreeSet` and tests membership. The
table has **two** rows for (26161, 270000000), differing only in `regionCodeID`,
so joining it as a relation would match every supply row twice and double every
market share — a silent 2× on the whole inventory. It is consumed as a
`max`-semiring presence flag, which is what `docs/esm-conventions.md` §3 asks
for and what the set semantics actually are.

**The humidity equation is selected by a `join.on`, not an `==` filter.**
`noxhumidityadjust.humidityNOxEq` is decoded by a `codes` map to 86 and 1065,
and the two arms join to one-row relations `run_humidityEqCFR86` and
`run_humidityEqCFR1065` carrying those constants. `docs/esm-conventions.md`
§20.4 admits no exception for an equality against a constant and
`tools/check-conventions.py` enforces it; the first draft of this fixture wrote
both as filters and was rejected.

### 3.3 One rank, over the whole rate relation

`docs/esm-conventions.md` §22's three layers, exactly as
`docs/process-refueling.md` §3.3 uses them, and for the same reason: the blocks
are different sizes, so there is no block length to divide by. `rt_survives` is
the mask (§2.5), `rt_prefixSurvives` an inclusive prefix count over all 656
candidates giving a dense 1..436, and the output relation is 436 × 2 with the
pollutant-process read *back* through the rank join like every other key.
`n_outputRate` = 436 is the one declared number; `rateSurvivorCount` recomputes
it and `pp_rateCohortCount` recomputes the 124 and the three 104s separately —
which matters, because 124 + 104 × 3 and 109 × 4 are the same 436.

**One thing this fixture does differently.** The flat (day type, survivor)
product is decoded with `lib/keys.esm`'s `flat_relation_major` and
`flat_relation_minor` rather than two hand-written floor divisions.
`mixed-onroad`, `process-brakewear` and `process-refueling` all spell the
arithmetic out; the templates existed before any of them and are documented for
exactly this. See `docs/esm-conventions.md` §30.

---

## 4. Reusable shapes

Seven new expression templates in `lib/adjustments.esm`, all forms and no
coefficients (`docs/esm-conventions.md` §24):

| template | source | why it is shared |
|---|---|---|
| `gpa_blend` | `adjust.rs:465`, `:486` | the general-fuel-ratio and criteria-ratio steps perform the *same* blend; written twice they can disagree about which arm is the base |
| `bounded_low_then_high` | `adjust.rs:152–159` | the Go's two sequential assignments, which agree with `min(max(v, lo), up)` everywhere including `lo > up` where a three-argument clamp would panic |
| `nox_humidity_reference` | `adjust.rs:176` | 10.71, once |
| `nox_humidity_cfr86` | `adjust.rs:170–177` | one arm of `calculate_nox_k` |
| `nox_humidity_cfr1065` | `adjust.rs:178–185` | the other |
| `nox_diesel_temperature_ceiling` | `adjust.rs:130` | 77.0, once, and visibly not the 75.0 beside it |
| `quadratic_temperature_adjustment` | `adjust.rs:142` | `general_temp_adjust`'s fall-through, centred on the existing `exhaust_temperature_reference` |
| `nox_temperature_adjustment` | `adjust.rs:127–139` | the NOx branch, delegating its non-diesel arm to the fall-through so the two cannot drift |

`lib/keys.esm`'s `model_year_in_range`, `flat_relation_major` and
`flat_relation_minor`, and `lib/adjustments.esm`'s `exact_else_wildcard`, are
instantiated rather than re-spelled.

---

## 5. Literals and enums

`enums` gains `pollutant.OxidesOfNitrogen` (3), `process.ExtendedIdleExhaust`
(90) and `process.AuxiliaryPowerExhaust` (91) — both named although this run
selects neither, because `adjust.rs:127` gates the NOx branch on all three
processes and the rule is the port, not the run — `fuel_type.Diesel` (2), and
`humidity_equation.CFR86` / `.CFR1065`, the codes the text column decodes to.
`process.Brakewear` and `source_type.HeavyDutyThreshold` are gone with the
branches that used them.

The only bare numeric literals in the document are the ones a template already
owns (75, 77, 10.71) and the flat-relation block size, which is a metaparameter.

---

## 6. Hand-checkable worked examples

### 6.0 Run-level values used by every example

```
temperature          59.5 degF          heatIndex           59.5 degF
specificHumidity     10.053684293477    molWaterFraction    0.015929059029
GPAFract             0.0                acActivity          0.0 (raw -0.2969815, clamped)
k(gasoline, E85)     1.0215927867446069 k(diesel)           1.0095483848288278
```

### 6.1 Worked example A — MY 1980, gasoline, weekend, total NOx

```
rtDay_meanBaseRate        135.734        (= baseratebyage_1_2020, hourDayID 72)
rt_acFactor                 0            -> the A/C companion 51.9912 contributes nothing
rt_temperatureFactor        1.0215927867 (humidity only; A = B = 0)
rt_criteriaFactor           0.962413415319
activity (SHO / noOfRealDays) 27.33 / 2 = 13.665     [hourDayID 72, ageID 40]
emissionQuant = 135.734 x 1.0215927867 x 0.962413415319 x ... = 162.631
```

MOVESOutput stores **162.631000000000**.

### 6.2 Worked example B — the same row, speciated

`nono2ratio` for source type 21, fuel type 1, model-year group 19501980:
NO 0.975, NO2 0.017, HONO 0.008 — summing to exactly 1.

```
NO   = 162.631 x 0.975 = 158.565      MOVESOutput: 158.565000000000
```

### 6.3 Worked example C — MY 2020, gasoline, weekend, all four

Model-year group 20112020 for the species (2020 for the parent): NO 0.836,
NO2 0.156, HONO 0.008.

```
NOx  = 12.4026                        MOVESOutput: 12.402600000000
NO   = 12.4026 x 0.836   = 10.3686    MOVESOutput: 10.368600000000
NO2  = 12.4026 x 0.156   =  1.93481   MOVESOutput:  1.934810000000
HONO = 12.4026 x 0.008   =  0.0992211 MOVESOutput:  0.099221100000
```

The three sum to the parent by construction, which is why **no per-pollutant
sum gate can distinguish NO from NO2**; only the per-cell check can.

### 6.4 Worked example D — MY 2020, electricity, weekend

```
rtDay_meanBaseRate    0     (emissionratebyage carries a fuel-9 ageGroup-1519 row, rate 0)
NOx emissionQuant     0     MOVESOutput: 0.000000000000, row PRESENT
NO / NO2 / HONO       -     rows ABSENT: nono2ratio has no fuel type 9
```

and one model year older:

```
MY 2000, electricity  -     row ABSENT in every block: no ageGroup 2099 row for fuel 9
```

Those two rows are the whole of §2.2 and §2.5 in four lines: a zero that is
emitted, and two absences with two different causes.

### 6.5 The reproduction script

Extracted and run by `./run-nox-speciation-oracle.sh`. It reads only the input
tables of §1, computes S1–S18 for the parent and the chain for the three
species, and **asserts** its worst relative error against `sho`, against
`baseratebyage_1_2020` and against `MOVESOutput`, plus the key set per
pollutant-process.

```python
#!/usr/bin/env python3
"""process-nox-speciation reproduction from the snapshot's own input tables."""
import sys, collections, math
import glob
import pyarrow.parquet as pq

SNAP = sys.argv[1]
# The execution database's name carries a per-run id, so the prefix is
# DISCOVERED and not written down: a recapture renames every table in the
# snapshot and a hardcoded id fails as a missing FILE, which reads like a
# missing table rather than like a stale name.
P = glob.glob(SNAP + "/tables/db__movesexecution*__year.parquet")[0][:-len("year.parquet")]
def T(n): return pq.read_table(P+n+".parquet").to_pylist()

YEAR, MONTH, HOUR, ZONE, ROAD, ST = 2020, 8, 7, 261610, 4, 21
COUNTY, ELECTRICITY, NOX = 26161, 9, 3
DAYS=[r["dayID"] for r in T("runspecday")]
HD={r["dayID"]:r["hourDayID"] for r in T("hourday") if r["hourID"]==HOUR}
POLPROCS=[r["polProcessID"] for r in T("runspecpollutantprocess")]
base=max(r["yearID"] for r in T("year") if r["yearID"]<=YEAR and str(r["isBaseYear"]).upper()=="Y")
FUELYEAR={r["yearID"]:r["fuelYearID"] for r in T("year")}[YEAR]
stpop={r["sourceTypeID"]:float(r["sourceTypePopulation"]) for r in T("sourcetypeyear") if r["yearID"]==base}
agefrac={(r["sourceTypeID"],r["ageID"]):float(r["ageFraction"]) for r in T("sourcetypeagedistribution") if r["yearID"]==base}
pop={k:stpop[k[0]]*v for k,v in agefrac.items() if k[0] in stpop}
mar={(r["sourceTypeID"],r["ageID"]):float(r["relativeMAR"]) for r in T("sourcetypeage")}
hpms={r["sourceTypeID"]:r["HPMSVtypeID"] for r in T("sourceusetype")}
gt=collections.defaultdict(float)
for k in pop: gt[hpms[k[0]]]+=pop[k]*mar[k]
travelfrac={k:pop[k]*mar[k]/gt[hpms[k[0]]] for k in pop}
ayv={r["HPMSVtypeID"]:float(r["HPMSBaseYearVMT"]) for r in T("hpmsvtypeyear") if r["yearID"]==base}
onroad={r["roadTypeID"] for r in T("roadtype")}
rtd={r["roadTypeID"]:float(r["roadTypeVMTFraction"]) for r in T("roadtypedistribution") if r["sourceTypeID"]==ST and r["roadTypeID"] in onroad}
ages=sorted({k[1] for k in travelfrac if k[0]==ST})
annual={a:ayv[hpms[ST]]*rtd[ROAD]*travelfrac[(ST,a)] for a in ages}
binspeed={r["avgSpeedBinID"]:float(r["avgBinSpeed"]) for r in T("avgspeedbin")}
speed=collections.defaultdict(float)
for r in T("avgspeeddistribution"):
    if r["sourceTypeID"]!=ST or r["roadTypeID"]!=ROAD: continue
    for d in DAYS:
        if r["hourDayID"]==HD[d]: speed[d]+=float(r["avgSpeedFraction"])*binspeed[r["avgSpeedBinID"]]
weeks={r["monthID"]:r["noOfDays"]/7.0 for r in T("monthofanyyear")}[MONTH]
mvf={r["monthID"]:float(r["monthVMTFraction"]) for r in T("monthvmtfraction") if r["sourceTypeID"]==ST}[MONTH]
dvf={r["dayID"]:float(r["dayVMTFraction"]) for r in T("dayvmtfraction") if r["sourceTypeID"]==ST and r["monthID"]==MONTH and r["roadTypeID"]==ROAD}
hvf={r["dayID"]:float(r["hourVMTFraction"]) for r in T("hourvmtfraction") if r["sourceTypeID"]==ST and r["roadTypeID"]==ROAD and r["hourID"]==HOUR}
alloc={r["roadTypeID"]:float(r["SHOAllocFactor"]) for r in T("zoneroadtype") if r["zoneID"]==ZONE}[ROAD]
sho={}
for d in DAYS:
    for a in ages:
        vmt=annual[a]*mvf*dvf[d]*hvf[d]/weeks
        sho[(HD[d],a)]=(vmt/speed[d] if speed[d] else 0.0)*alloc
maxage=max(r["ageID"] for r in T("agecategory"))
my_lo,my_hi=YEAR-maxage,YEAR
fuels={r["fuelTypeID"] for r in T("runspecsourcefueltype") if r["sourceTypeID"]==ST}
mygroup={(r["polProcessID"],r["modelYearID"]):r["modelYearGroupID"] for r in T("pollutantprocessmodelyear")}
shortgroup={r["modelYearGroupID"]:r["shortModYrGroupID"] for r in T("modelyeargroup")}
svp=[r for r in T("samplevehiclepopulation")]
def cohorts(pp):
    c={}
    for r in svp:
        frac=float(r["stmyFraction"])
        if (r["sourceTypeID"]!=ST or not my_lo<=r["modelYearID"]<=my_hi
            or r["fuelTypeID"] not in fuels or frac<=0.0): continue
        g=mygroup.get((pp,r["modelYearID"]))
        if g is None or g not in shortgroup: continue
        key=(r["modelYearID"],r["fuelTypeID"],r["engTechID"],r["regClassID"])
        c[key]=c.get(key,0.0)+frac
    return c
# ---- drive cycle W ----
seconds=collections.defaultdict(dict)
for r in T("driveschedulesecond"): seconds[r["driveScheduleID"]][r["second"]]=float(r["speed"])
physics=[r for r in T("sourceusetypephysicsmapping") if r["realSourceTypeID"]==ST and float(r["sourceMass"])>0.0 and float(r["fixedMassFactor"])>0.0]
assert len(physics)==1
PH=physics[0]
opmode={r["opModeID"]:r for r in T("operatingmode")}
BRAKE1=float(opmode[0]["brakeRate1Sec"]); BRAKE3=float(opmode[0]["brakeRate3Sec"])
binned=sorted(m for m in opmode if 1<m<100 and m not in (26,36))
MS=0.44704
def bound(m,c):
    v=opmode[m][c]; return None if v is None else float(v)
def dcd(sid):
    sp=seconds[sid]; lo,hi=min(sp),max(sp); mode,acc={},{}
    for s,v in sp.items():
        if v<1.0: mode[s]=1
    for s in range(lo+1,hi+1):
        if s in sp and s-1 in sp: acc[s]=sp[s]-sp[s-1]
    if lo+1 in acc: acc[lo]=acc[lo+1]
    total=collections.Counter()
    for s in range(lo,hi+1):
        if s not in sp: continue
        m=mode.get(s)
        if m is None:
            a=acc.get(s,0.0)
            three=(s-1 in sp and s-2 in sp and a<BRAKE3 and acc.get(s-1,0.0)<BRAKE3 and acc.get(s-2,0.0)<BRAKE3)
            if a<=BRAKE1 or three: m=0
            else:
                v=sp[s]*MS
                a_ms=(v-sp[s-1]*MS) if s-1 in sp else ((sp[s+1]*MS-v) if s==lo and s+1 in sp else 0.0)
                vsp=(float(PH["rollingTermA"])*v+float(PH["rotatingTermB"])*v*v
                     +float(PH["dragTermC"])*v*(v*v)+float(PH["sourceMass"])*v*a_ms)/float(PH["fixedMassFactor"])
                for k in binned:
                    lov,hiv=bound(k,"VSPLower"),bound(k,"VSPUpper")
                    los,his=bound(k,"speedLower"),bound(k,"speedUpper")
                    if lov is not None and vsp<lov: continue
                    if hiv is not None and vsp>=hiv: continue
                    if los is not None and sp[s]<los: continue
                    if his is not None and sp[s]>=his: continue
                    m=k; break
        if m is not None and s>0: total[m]+=1
    n=sum(total.values())
    return {k:v/n for k,v in total.items()}
cycles=sorted(r["driveScheduleID"] for r in T("drivescheduleassoc") if r["sourceTypeID"]==ST and r["roadTypeID"]==ROAD)
cspeed={r["driveScheduleID"]:float(r["averageSpeed"]) for r in T("driveschedule")}
cdist={c:dcd(c) for c in cycles}
bin_modes={}
for b,bs in binspeed.items():
    low=max((cspeed[c] for c in cycles if cspeed[c]<=bs),default=None)
    high=min((cspeed[c] for c in cycles if cspeed[c]>=bs),default=None)
    span=(high if high is not None else 100000.0)-(low if low is not None else -100.0)
    if span<=0.0: lf=1.0
    elif low is None: lf=0.0
    elif high is None: lf=1.0
    else: lf=(high-bs)/span
    d=collections.defaultdict(float)
    for c,f in ((low,lf),(high,1.0-lf)):
        if c is None or f==0.0: continue
        sid=next(s for s in cycles if cspeed[s]==c)
        for m,v in cdist[sid].items(): d[m]+=f*v
    bin_modes[b]=d
W=collections.defaultdict(float)
for r in T("avgspeeddistribution"):
    if r["sourceTypeID"]!=ST or r["roadTypeID"]!=ROAD: continue
    for m,v in bin_modes[r["avgSpeedBinID"]].items():
        W[(r["hourDayID"],m)]+=v*float(r["avgSpeedFraction"])
for d in DAYS:
    t=sum(v for (h,_),v in W.items() if h==HD[d])
    assert abs(t-1.0)<1e-5, t
usage=[r for r in T("fuelusagefraction") if r["countyID"]==COUNTY and r["fuelYearID"]==FUELYEAR]
def rebase(cohort):
    s=collections.defaultdict(float)
    for (my,fuel,et,rc),frac in cohort.items():
        for u in usage:
            if u["sourceBinFuelTypeID"]!=fuel: continue
            if u["modelYearGroupID"]!=0 and u["modelYearGroupID"]!=my: continue
            used=(my,u["fuelSupplyFuelTypeID"],et,rc)
            if used not in cohort: continue
            s[used]+=float(u["usageFraction"])*frac
    return s
def slot(b,scale): return (b//scale)%100
agegroup={r["ageID"]:r["ageGroupID"] for r in T("agecategory")}
ERBA=T("emissionratebyage")
def rates_by_age(pp):
    d={}
    for r in ERBA:
        if r["polProcessID"]!=pp: continue
        b=r["sourceBinID"]
        d[(slot(b,10**16),slot(b,10**14),slot(b,10**12),slot(b,10**10),r["opModeID"],r["ageGroupID"])]=float(r["meanBaseRate"])
    return d
fleetgroup={r["regClassID"]:r["fleetAvgGroupID"] for r in T("regulatoryclass")}
evfrac={(r["modelYearID"],r["fleetAvgGroupID"]):float(r["evFraction"]) for r in T("evsalesfraction")}
FA=T("fleetavgadjustment")
def evsf(pp,my,fuel,rc):
    if fuel==ELECTRICITY: return 1.0
    g=fleetgroup[rc]; e=evfrac.get((my,g))
    row=next((r for r in FA if r["polProcessID"]==pp and r["fleetAvgGroupID"]==g and r["beginModelYearID"]<=my<=r["endModelYearID"]),None)
    if e is None or row is None: return 1.0
    m=float(row["evMultiplier"]); den=(1.0-e)+e*m; v=1.0/(1.0-e*m/den)
    cap=row["adjustmentCap"]
    return min(v,float(cap)) if cap is not None and float(cap)>0.0 else v
realdays={r["dayID"]:float(r["noOfRealDays"]) for r in T("dayofanyweek")}
ZMH=[r for r in T("zonemonthhour") if r["monthID"]==MONTH and r["zoneID"]==ZONE and r["hourID"]==HOUR][0]
TEMP=float(ZMH["temperature"]); HEAT=float(ZMH["heatIndex"])
SPECHUM=float(ZMH["specificHumidity"]); MOLFRAC=float(ZMH["molWaterFraction"])
TA=T("temperatureadjustment")
def temp_terms(pp,fuel,regclass,my):
    for rc in (regclass,0):
        for r in TA:
            if (r["polProcessID"]==pp and r["fuelTypeID"]==fuel and r["regClassID"]==rc
                    and r["minModelYearID"]<=my<=r["maxModelYearID"]):
                a=r["tempAdjustTermA"]; b=r["tempAdjustTermB"]
                return (float(a) if a is not None else 0.0, float(b) if b is not None else 0.0)
    return 0.0,0.0
NHA={r["fuelTypeID"]:r for r in T("noxhumidityadjust")}
def nox_k(fuel):
    r=NHA.get(fuel)
    if r is None: return 1.0
    lo=float(r["humidityLowBound"]); up=float(r["humidityUpBound"]); a=float(r["humidityTermA"])
    eq=r["humidityNOxEq"]
    def bnd(v):
        if v<lo: v=lo
        return up if v>up else v
    if eq=="CFR 86": return 1.0-a*(bnd(SPECHUM)-10.71)
    if eq=="CFR 1065": return 1.0/(a*bnd(MOLFRAC)+float(r["humidityTermB"]))
    return 1.0
def nox_temp_factor(pp,pol,proc,fuel,regclass,my):
    a,b=temp_terms(pp,fuel,regclass,my)
    if fuel==2:
        adj=0.0 if TEMP>77.0 else (77.0-TEMP)*a
    else:
        adj=(TEMP-75.0)*(a+b*(TEMP-75.0))
    return (1.0+adj)*nox_k(fuel)
# A/C
GRP={r["monthID"]:r["monthGroupID"] for r in T("monthofanyyear")}[MONTH]
MGH=[r for r in T("monthgrouphour") if r["monthGroupID"]==GRP and r["hourID"]==HOUR][0]
acraw=float(MGH["ACActivityTermA"])+HEAT*(float(MGH["ACActivityTermB"])+float(MGH["ACActivityTermC"])*HEAT)
ACACT=min(max(acraw,0.0),1.0)
ACPEN={r["modelYearID"]:float(r["ACPenetrationFraction"]) for r in T("sourcetypemodelyear") if r["sourceTypeID"]==ST}
ACFUNC={r["ageID"]:float(r["functioningACFraction"]) for r in T("sourcetypeage") if r["sourceTypeID"]==ST}
FAC={r["opModeID"]:float(r["fullACAdjustment"]) for r in T("fullacadjustment") if r["sourceTypeID"]==ST and r["polProcessID"]==301}
# criteria ratio
GPA=float([r for r in T("county") if r["countyID"]==COUNTY][0]["GPAFract"])
FSUB={r["fuelSubtypeID"]:r["fuelTypeID"] for r in T("fuelsubtype")}
FFORM={r["fuelFormulationID"]:r["fuelSubtypeID"] for r in T("fuelformulation")}
supply=collections.defaultdict(list)
for r in T("fuelsupply"):
    if r["fuelYearID"]!=FUELYEAR or r["monthGroupID"]!=GRP: continue
    st=FFORM[r["fuelFormulationID"]]
    if st not in FSUB: continue
    supply[FSUB[st]].append((r["fuelFormulationID"],float(r["marketShare"])))
CR={}
for r in T("criteriaratio"):
    CR[(r["fuelFormulationID"],r["polProcessID"],r["sourceTypeID"],r["modelYearID"],r["ageID"])]=(
        float(r["ratio"]),float(r["ratioGPA"]))
def crit(pp,ff,my,age):
    v=CR.get((ff,pp,ST,my,age))
    if v is None: return 1.0
    return v[0]+GPA*(v[1]-v[0])
def scc(fuel,proc): return "%d"%(22*10**8+fuel*10**6+ST*10**4+ROAD*10**2+proc)
PPA={r["polProcessID"]:(r["pollutantID"],r["processID"]) for r in T("pollutantprocessassoc")}
rows={}
for pp in POLPROCS:
    pol,proc=PPA[pp]
    if pol!=NOX: continue
    coh=cohorts(pp)
    sbaf=rebase(coh)
    rate=rates_by_age(pp)
    modes=sorted({k[4] for k in rate})
    sbw=collections.defaultdict(float); sbwac=collections.defaultdict(float)
    for (my,fuel,et,rc),frac in sbaf.items():
        smy=shortgroup[mygroup[(pp,my)]]
        ag=agegroup[YEAR-my]
        ev=evsf(pp,my,fuel,rc)
        for om in modes:
            r=rate.get((fuel,et,rc,smy,om,ag))
            if r is None: continue
            sbw[(my,fuel,om)]+=frac*r*ev
            sbwac[(my,fuel,om)]+=frac*r*ev*(FAC.get(om,1.0)-1.0)
    br=collections.defaultdict(float); brac=collections.defaultdict(float)
    for (my,fuel,om),v in sbw.items():
        for d in DAYS: br[(HD[d],my,fuel)]+=v*W[(HD[d],om)]
    for (my,fuel,om),v in sbwac.items():
        for d in DAYS: brac[(HD[d],my,fuel)]+=v*W[(HD[d],om)]
    have={(k[0],k[1],k[2],k[3],k[5]) for k in rate}
    for (my,fuel,et,rc),frac in coh.items():
        age=YEAR-my
        smy=shortgroup[mygroup[(pp,my)]]
        if (fuel,et,rc,smy,agegroup[age]) not in have: continue
        acf=ACACT*ACPEN[my]*ACFUNC[age]
        tf=nox_temp_factor(pp,pol,proc,fuel,rc,my)
        for d in DAYS:
            base_r=br[(HD[d],my,fuel)]+acf*brac[(HD[d],my,fuel)]
            q=0.0
            for ff,share in supply.get(fuel,[]):
                q+=share*base_r*crit(pp,ff,my,age)
            q*=tf
            act=sho[(HD[d],age)]/realdays[d]
            rows[(pol,proc,d,my,fuel)]=(q*act,scc(fuel,proc))
# chained species
NNR=T("nono2ratio")
for c in T("runspecchainedto"):
    outpp,outpol,outproc=c["outputPolProcessID"],c["outputPollutantID"],c["outputProcessID"]
    inpol,inproc=c["inputPollutantID"],c["inputProcessID"]
    for (pol,proc,d,my,fuel),(q,s) in list(rows.items()):
        if (pol,proc)!=(inpol,inproc): continue
        g=mygroup.get((outpp,my))
        rr=[r for r in NNR if r["polProcessID"]==outpp and r["sourceTypeID"]==ST
            and r["fuelTypeID"]==fuel and r["modelYearGroupID"]==g]
        for r in rr:
            rows[(outpol,outproc,d,my,fuel)]=(q*float(r["NOxRatio"]),scc(fuel,outproc))
# ------------------------------------------------------------------- compare
ref_sho = {(r["hourDayID"], r["ageID"]): float(r["SHO"]) for r in T("sho")}
worst_sho = max(abs(sho[k] - v) / v for k, v in ref_sho.items())
print("sho:            %3d rows, worst relative error %.3e" % (len(ref_sho), worst_sho))
assert worst_sho < 1e-5, "sho: worst relative error %.3e exceeds 1e-5" % worst_sho

ref_br = {(r["hourDayID"], r["modelYearID"], r["fuelTypeID"]): float(r["meanBaseRate"])
          for r in T("baseratebyage_1_2020")}
worst_br, n_br = 0.0, 0
for k, v in ref_br.items():
    if v == 0.0:
        assert br[k] + brac[k] == 0.0, k
        continue
    n_br += 1
    worst_br = max(worst_br, abs(br[k] - v) / v)
print("baseRateByAge:  %3d non-zero rows, worst relative error %.3e" % (n_br, worst_br))
assert worst_br < 2e-5, "baseRateByAge: worst relative error %.3e exceeds 2e-5" % worst_br

out = pq.read_table(SNAP + "/tables/db__out_process_nox_speciation__movesoutput.parquet").to_pylist()
key = lambda o: (o["pollutantID"], o["processID"], o["dayID"], o["modelYearID"], o["fuelTypeID"])
worst, worst_key = 0.0, None
missing = [key(o) for o in out if key(o) not in rows]
extra = sorted(set(rows) - {key(o) for o in out})
for o in out:
    if key(o) not in rows:
        continue
    q, s = rows[key(o)]
    assert s == o["SCC"], (key(o), s, o["SCC"])
    e = float(o["emissionQuant"])
    rel = abs(q - e) / e if e != 0.0 else abs(q - e)
    if rel > worst:
        worst, worst_key = rel, key(o)
print("emissionQuant: %4d rows, %d missing, %d extra, worst relative error %.3e at "
      "(pollutant %d, process %d, day %d, MY %d, fuel %d)"
      % (len(out), len(missing), len(extra), worst, *worst_key))
# ASSERTED, not merely printed (docs/esm-conventions.md 21): ./run-tests.sh reads
# this script's EXIT CODE, so a regression that leaves the key set intact and
# moves every value would otherwise be reported green with the evidence in a log.
assert not missing, missing[:8]
assert not extra, extra[:8]
assert len(rows) == len(out), (len(rows), len(out))
assert worst < 2e-5, "emissionQuant: worst relative error %.3e exceeds 2e-5" % worst

# --- the KEY SET, exactly, and not merely its size -------------------------
# A row count cannot see a ragged block set: 124 + 104 + 104 + 104 and
# 109 + 109 + 109 + 109 are both 436. So the cohort set is asserted PER
# pollutant-process, and the day-type axis separately, and their product is
# checked against the row count.
cohorts_by_pp = collections.defaultdict(set)
days = set()
for (pol, proc, day, my, fuel) in rows:
    cohorts_by_pp[(pol, proc)].add((my, fuel))
    days.add(day)
expected_cohorts = {(3, 1): 124, (32, 1): 104, (33, 1): 104, (34, 1): 104}
got = {k: len(v) for k, v in cohorts_by_pp.items()}
assert got == expected_cohorts, (got, expected_cohorts)
assert days == set(DAYS) and len(days) == 2, days
parent = cohorts_by_pp[(3, 1)]
for species in (32, 33, 34):
    assert cohorts_by_pp[(species, 1)] < parent, species
    assert {c for c in parent - cohorts_by_pp[(species, 1)]} == \
        {c for c in parent if c[1] == ELECTRICITY}, species
assert sum(expected_cohorts.values()) * len(days) == len(out) == 872
print("key set:       124 NOx + 3 x 104 species cohorts x %d day types = %d rows, exact;"
      % (len(days), len(out)))
print("               the 20 cohorts each species drops are exactly the ELECTRICITY ones,"
      " and every species set is a strict subset of the parent's")
chained = sum(1 for (pol, _, _, _, _) in rows if pol != NOX)
assert chained == 3 * 104 * len(days), chained
print("               %3d of the %d rows are CHAINED -- computed from the 301 rows by "
      "NOxRatio, from no rate of their own" % (chained, len(out)))

# --- what a comparison against MOVESOutput alone could not see -------------
# The three ratios partition the parent exactly, so a document that swapped NO
# for NO2 would conserve mass and move only per-cell values. Checked here on the
# ratio table itself, where it is a property of the input and not of the answer.
for fuel in (1, 2, 5):
    for group in {r["modelYearGroupID"] for r in NNR
                  if r["sourceTypeID"] == ST and r["fuelTypeID"] == fuel}:
        total = sum(float(r["NOxRatio"]) for r in NNR
                    if r["sourceTypeID"] == ST and r["fuelTypeID"] == fuel
                    and r["modelYearGroupID"] == group
                    and r["polProcessID"] in (3201, 3301, 3401))
        assert abs(total - 1.0) < 1e-9, (fuel, group, total)
print("NOTE:          NO + NO2 + HONO is exactly 1.0 in all 37 model-year groups of each of"
      " the three fuel types, so the")
print("               three species partition the parent and no per-pollutant SUM can tell"
      " them apart -- only the per-cell check can.")
# The A/C arm is dead at this hour and the fixture says so; assert it here too,
# so a reader cannot mistake a passing comparison for a check of fullACAdjustment.
assert ACACT == 0.0, ACACT
assert acraw < 0.0, acraw
print("NOTE:          the A/C activity term is %.6f and clamps to 0, so the 23 live"
      " fullacadjustment rows" % acraw)
print("               (6.26 at idle, 1.38077 elsewhere) reach no emitted number and the"
      " order of S15's factors is untested.")
```

Result:

```
sho:             82 rows, worst relative error 3.610e-06
baseRateByAge:  208 non-zero rows, worst relative error 5.945e-06
emissionQuant:  872 rows, 0 missing, 0 extra, worst relative error 9.482e-06 at (pollutant 33, process 1, day 5, MY 1990, fuel 2)
key set:       124 NOx + 3 x 104 species cohorts x 2 day types = 872 rows, exact;
               the 20 cohorts each species drops are exactly the ELECTRICITY ones, and every species set is a strict subset of the parent's
               624 of the 872 rows are CHAINED -- computed from the 301 rows by NOxRatio, from no rate of their own
```

### 6.6 What the fixture's inline tests check

Eleven tests, 165 assertions, none of which reads `MOVESOutput` through the
document:

| test | what it pins |
|---|---|
| run scope | year/month/hour/geography, and the four new run-level numbers: both humidity columns and `GPAFract` |
| four pollutant-processes | the scope and the three chain declarations, read from the execution database |
| drive-cycle scaffolding | braking thresholds read not written, one physics row, bracket weights sum to 1 |
| **selection vs survival** | 125 selected in **all four** blocks, 124/104/104/104 emitted, 436 total, 312 chained per day |
| `W` | a distribution over exactly 23 modes, at an *absolute* 1e-5 (§20.5) |
| activity | `act_sho` against the snapshot's own `sho`, which nothing here reads |
| base rate | `rtDay_meanBaseRate` and `rtDay_meanBaseRateACAdj` against `baseratebyage_1_2020` |
| model-year group | 2020 → group 2020 for 301 and group 20112020 for 3201 |
| **criteria fuel effect** | the five supplied formulations' fuel types, and eight `rt_criteriaFactor` values including the two that are 1 for want of a row |
| **temperature and humidity** | both `k` arms, the zero temperature term, and the A/C arm asserted **dead** |
| **chain and output** | the four ratios, the electricity distinction at rate row 288, and twelve `MOVESOutput` cells across all four blocks |

---

## 7. Fidelity notes and tolerance

### 7.1 The measured result

872 of 872 rows, key set exact, **worst cell 9.482e-06** relative, worst
per-pollutant `emissionQuant` sum 4.957e-07. No tolerance override; the
repository-wide `[cell] rel = 2e-5` carries about 2.1× headroom.

The worst cell is **(NO2, day 5, MY 1990, diesel)**, value 0.011031500000. That
is a *chained* cell, as it is in `process-brakewear` and `process-tirewear`,
and for the same arithmetic reason: it carries its parent's residual plus the
ratio's own quantisation. Six significant figures on 0.0110315 is a half-ulp of
4.5e-06 relative before anything else is counted; the parent
(0.370684000000) contributes another 1.3e-06, and `NOxRatio` is a MOVES
`FLOAT`. 9.482e-06 is slightly above the port's previous worst (8.320e-06) and
is the reference's column storage, not either implementation — the independent
reproduction in §6.5 reports **the same 9.482e-06 at the same key** by a
different route, which is what distinguishes a storage limit from an error.

### 7.2 What this fixture cannot see, measured

Five things are named here rather than claimed, because a passing comparison
would otherwise look like evidence for them:

1. **The A/C arm is dead.** `fullacadjustment` has 23 live `polProcessID` 301
   rows (6.26 at idle, 1.38077 elsewhere) and `rtDay_meanBaseRateACAdj` is a
   real number — the inline tests pin it against `baseratebyage_1_2020`. But
   the A/C *activity* quadratic is −0.2969815 at this heat index and clamps to
   0, so `rt_acFactor` is exactly 0 and none of it reaches an emitted number.
   **The order in which the criteria ratio and the temperature factor reach the
   A/C increment is therefore untested.** It is written in `adjust.rs`'s order;
   nothing here can tell that order from any other.
2. **`imcoverage` is empty**, so the I/M blend (`adjust.rs:576–586`) is absent.
   `imfactor` has 7,536 rows and reaches nothing without coverage.
3. **`emissionrateadjustment` is empty**, so that stage is absent.
4. **`evefficiency` is empty** — it is an energy-pollutant table — so there is
   no EV divisor and the fixture does not carry one. `mixed-onroad` and
   `process-brakewear` do.
5. **`GPAFract` is 0**, so every fuel-effect blend selects its normal arm. The
   blend is written; the GPA arm is never taken.
6. **`generalfuelratio` is empty** (0 rows; only `generalfuelratioexpression`
   is populated), so `adjust.rs:449–473`'s general-fuel-ratio stage is absent
   too. For a criteria pollutant `FuelEffectsGenerator` drops the model-year-
   overlapping rows from it anyway, so the effect arrives through
   `criteriaratio` and applies exactly once — but that is read from the source,
   not measured here.

Two more, weaker: the temperature TERM is 0 on every emitted row (§2.4), so only
the humidity half of the NOx factor is exercised; and every supplied fuel type
has exactly one formulation at market share 1.0, so the share weighting in
`rt_criteriaFactor` is a sum of one term.

### 7.3 Precision-sensitive operations, ranked

1. **`NOxRatio`** — a MOVES `FLOAT`, so ~7 significant figures on a multiplier
   applied to the whole quantity. The largest single contributor to §7.1.
2. **The humidity correction** — `1 - 0.0329 x (h - 10.71)` is a cancellation:
   `h` is 10.0537 and the reference is 10.71, so the difference is −0.656 out of
   operands near 10. It is computed from a stored `specificHumidity` with 12
   decimal places, so the cancellation costs nothing here, but a document that
   recomputed specific humidity from relative humidity would lose two digits.
3. **`rt_criteriaFactor`** — twelve stored decimal places, applied
   multiplicatively.
4. **The A/C clamp** — inert at −0.2969815, and 0.3 further up the heat index it
   would not be. `mixed-onroad` sits at −0.0189 and is the fixture that would
   notice first.

---

## 8. Gaps and things not verified

* **`FuelEffectsGenerator` is not ported.** `criteriaratio` is read as the
  captured input it is on this path (§1.3). Porting it means an expression
  evaluator over `generalfuelratioexpression`'s strings *and* the Complex +
  sulfur model for model years ≤ 2000 — two rungs, not one, and the calculator
  path in §0 does not claim it.
* **One process, one source type, one road type.** The NOx branch of
  `general_temp_adjust` also covers processes 90 and 91; the enums name them and
  nothing exercises them.
* **The diesel temperature arm's 77 °F ceiling is not crossed.** At 59.5 °F the
  `T > 77` test is false; with A = 0 both sides are 0 anyway, so this fixture
  cannot distinguish the diesel arm from the quadratic at all. It is written
  because `adjust.rs` writes it.
* **One-level chaining only** (§2.5).
* **`NOxRatioCV` and `dataSourceId`** are uncertainty/provenance columns and are
  not modelled, matching `nitrogen_oxide.rs`.
* **A fuel type with no supply row would be zeroed here and dropped there.**
  `rt_criteriaFactor` is a sum over the supplied formulations, so a fuel type
  absent from `fuelsupply` gives 0 and its rows would be emitted at zero;
  `build_fuel_blocks` (`adjust.rs:215–228`) `continue`s past such a row on the
  age path and emits nothing. All four of this run's fuel types are supplied, so
  the two agree. A run whose supply were missing a selected fuel type would
  differ by a row count, and the difference would show in the key set rather
  than in a cell.
* **`monthofanyyear` is assumed one month per month GROUP**, as
  `baseratecalculator/mod.rs:1163`'s `group_to_month` map assumes. It holds in
  this snapshot (group 8 → month 8) and a group covering two months would sum
  their ids here and last-write-wins there — neither is right, and neither is
  exercised.

---

## 9. Summary for the `.esm` author

Start from `fixtures/process-brakewear.esm`. Keep the activity chain, the cohort
structure, the fuel-usage rebase, `dc_W`, and the pollutant-process × cohort
rate relation. Then:

1. read `emissionratebyage` instead of `emissionrate`, and add `ageGroupID` to
   the rate join and to the has-a-rate test;
2. add the fuel-supply resolution (`regioncounty` as a presence flag,
   `fuelformulation` and `fuelsubtype` as two hops) and `rt_criteriaFactor`;
3. replace the EV temperature branch with the NOx one, and add the two humidity
   arms, joining the equation code rather than filtering on it;
4. replace `pm10emissionratio` with `nono2ratio`, keyed on the model-year GROUP
   resolved for the species' own `polProcessID`;
5. make `rt_survives` a union of the direct arm and `has a ratio AND its parent
   survives`, rank over the whole rate relation, and decode the output's flat
   (day, survivor) product with `lib/keys.esm`'s two templates;
6. drop the EV-efficiency divisor — the table is empty.
