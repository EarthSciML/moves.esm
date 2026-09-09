# `process-crankcase-running` — computation specification

The port specification for the first fixture that emits **two processes for the
same pollutants**, written to the method of `docs/mixed-onroad.md` and
`docs/process-brakewear.md`: the input inventory determined from evidence, the
chain with source lines into `../moves.rs`, every join with its exact key pairs,
and worked examples whose numbers can be checked by hand.

It is short where `docs/mixed-onroad.md` is long, and deliberately so. **The
activity chain, the cohort structure, the fuel-usage rebase and the drive-cycle
operating-mode weights are that document's, unchanged**, and are not restated
here — the resolved scope is byte-identical to `process-brakewear`'s and
`process-tirewear`'s (§0.1), so the whole activity half is already checked end
to end by two existing fixtures. What this document specifies is the two things
that are new, and they are independent of each other:

1. **The pollutants are criteria pollutants.** Every earlier onroad rung rated
   Total Energy Consumption or a particulate, and neither carries a fuel effect
   or a humidity correction. These do. The rate table becomes
   `emissionRateByAge` (§2.2), each base rate is expanded over the fuel
   **formulations** the county is supplied and re-collapsed by market share
   (§2.3), and NOx alone takes a humidity correction selected by a **free-text
   equation name** in a three-row table (§2.4).
2. **The two processes do not span the same key space** (§2.5).
   `CrankcaseEmissionCalculatorNonPM` is a chained calculator with no rate of
   its own; its ratio table has no electricity row and MOVES's join is an inner
   one, so process 1 emits 248 rows per pollutant and process 15 emits 208. That
   makes the output relation's blocks **ragged**, which is the first time in
   this port that they are, and §2.6 is the consequence for how a MOVESOutput
   row is addressed at all.

---

## 0. The fixture at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/process-crankcase-running.xml` |
| Model | ONROAD, `modelscale` `Inv` (inventory), `modeldomain` `DEFAULT` |
| Geography | county 26161 (Washtenaw, Michigan), zone 261610, link 2616104 |
| Time | year 2020, month **8**, hour **7**, day types **2 (weekend) and 5 (weekday)** |
| Vehicles | sourceTypeID 21 (passenger car); fuel types **1, 2, 5, 9** |
| Road | roadTypeID 4 (urban restricted access) |
| Pollutant/process | **101, 201, 301** (THC, CO, NOx × Running Exhaust) and **115, 215, 315** (the same three × Crankcase Running Exhaust, *chained*) |
| Model years | 1980–2020 (41) |
| Output | `db__out_process_crankcase_running__movesoutput`, **1,368 rows** |
| Output units | grams, `outputtimestep` **Hour** |
| Calculator path | `TotalActivityGenerator` → `SourceBinDistributionGenerator` → `BaseRateGenerator` → `BaseRateCalculator` → **`CrankcaseEmissionCalculatorNonPM`** → output aggregation |
| Snapshot | 370 tables, **247 non-empty** |

### 0.1 The scope is `process-brakewear`'s, exactly

The XML's `<month key>`, `<beginhour key>` and `<day key>` are canonical
`RunSpecXML` **0-based indices into sorted ID lists**, not identifiers, and the
authority is the execution database's own `runspec*` tables — the same rule as
`docs/mixed-onroad.md` §0.1.

| dimension | `process-crankcase-running.xml` says | the execution database says |
|---|---|---|
| month | 7 | **8** (`runspecmonth`) |
| hour | 6 | **7** (`runspechour`) |
| day types | 5 | **2 and 5** (`runspecday`, 2 rows) |
| fuel types | 1 | **1, 2, 5, 9** (`runspecsourcefueltype`, 4 rows) |
| pollutant/process | 3, 1, 2 × 15 and 1 | **101, 115, 201, 215, 301, 315** (`runspecpollutantprocess`, 6 rows) |

Measured: `sho`, `avgspeeddistribution`, `driveschedulesecond`,
`sourcetypeagedistribution` and `hourvmtfraction` are **byte-identical** to
`process-brakewear`'s and `process-tirewear`'s. Any disagreement can therefore
be attributed to the criteria-pollutant half or the crankcase half immediately.

### 0.2 Why 1,368 rows, and why the two processes differ

| | process 1 | process 15 |
|---|---|---|
| gasoline (1) | 41 model years | 41 |
| diesel (2) | 40 (1980–2019) | 40 |
| E85 (5) | 23 (1998–2020) | 23 |
| electricity (9) | 20 (2001–2020) | **none** |
| cohorts | **124** | **104** |
| × 3 pollutants × 2 day types | 744 | 624 |

`crankcaseEmissionRatio` carries rows for fuelTypeID 1, 2 and 5 and **not 9**,
and `CrankcaseEmissionCalculator.sql`'s join is an `INNER JOIN`
(`crankcase_emission.rs:75-85`), so an electricity cohort emits an exhaust row
and no crankcase row at all — not a zero, no row. That single absence is the
whole 248/208 split.

A separate and *smaller* fact, easy to confuse with it: diesel model years
2001–2019 have a ratio of **exactly 0**. Those rows do exist and are emitted
carrying zero, 114 of them. A row that is absent and a row that is zero are
different, and both are present in this fixture.

---

## 1. Input inventory

### 1.1 How the set was determined

Every table the chain reads is named in `fixtures/process-crankcase-running.esm`
as a `data_sources` entry, and each one is read by at least one binding. Nothing
below is inferred from the MOVES schema: a table is an input here because a
column of it reaches `emissionQuant`, or because §1.3 records the measurement
that says its effect is zero.

### 1.2 Tables that carry data into the calculation

The 40 tables of `docs/mixed-onroad.md` §1.2 carry the activity chain, the
cohort structure and the drive cycle, unchanged. Ten more are new here:

| table | rows | what it carries |
|---|---|---|
| `emissionratebyage` | 590,709 | The rate, for 101/201/301, keyed additionally by `ageGroupID` (§2.2). |
| `county` | 1 | `GPAFract` — 0, so both fuel-effect blends collapse to their normal arm. |
| `regioncounty` | 2 | Which fuel region the county is in. Two rows, one region, two region codes. |
| `fuelsupply` | 5 | Which formulations that region is supplied, and in what market share. |
| `fuelformulation` | 2,158 | Read for `fuelSubtypeID` alone. |
| `fuelsubtype` | 13 | Read for `fuelTypeID` alone; closes formulation → fuel type. |
| `criteriaratio` | 2,199 | The criteria-pollutant fuel effect (§2.3). |
| `generalfuelratio` | 39 | The general fuel effect — measurably inert here; see §1.3. |
| `noxhumidityadjust` | 3 | The NOx humidity correction, and its equation NAME (§2.4). |
| `crankcaseemissionratio` | 572 | The whole of `CrankcaseEmissionCalculatorNonPM` (§2.5). |

`emissionrate`, `evefficiency` and `pm10emissionratio` — inputs to the three
earlier onroad fixtures — are **empty or absent** in this snapshot and are not
declared.

### 1.3 Tables declared and read, whose effect on this fixture is measurably zero

| table | why it is inert | what measures it |
|---|---|---|
| `generalfuelratio` | All 39 rows name a **crankcase** pollutant-process (115/215/315) on diesel formulation 25003. `CrankcaseEmissionCalculatorNonPM` runs *downstream* of `BaseRateCalculator` and does not re-enter it, so no fuel block is ever scaled by one. The lookup reaches 81 (rate row, formulation) pairs — all on crankcase rate rows, none of which carries a rate. | `run_generalFuelRatioReach` = 81, `run_generalFuelRatioOnRatedRows` = **0** |
| `fullacadjustment` | 69 rows for exactly 101/201/301, and the A/C increment they define is multiplied by an activity term that clamps to 0 at this hour. Inert **by a clamp, not by absence.** | `run_acActivityRaw` = −0.2969815, `run_acActivity` = 0 |
| `temperatureadjustment` | 4 rows, all polProcessID 301 on regClassID 42/46/47/48 for model years 2027–2060. Neither the exact-class lookup nor the regClassID 0 wildcard finds anything, so every A and B term is 0 and the temperature half of the factor is exactly 1. The **humidity** half is not (§2.4). | `rt_tempAdjustTermA` = 0, `rt_hasTempAdjustExact` = 0 |
| `county.GPAFract` | 0, so `gpa_blend(normal, gpa, 0)` = `normal` at both call sites. | `run_gpaFraction` = 0 |

### 1.4 Non-empty tables that are not inputs to this chain

| table | rows | why not |
|---|---|---|
| `imcoverage` | **0** | Michigan has no I/M program in 2020. `adjust.rs:566-580` is an `if let Some` on this table, so the I/M blend never fires — and `imfactor`'s 22,608 rows and the `meanBaseRateIM` columns are read by nothing as a result. |
| `emissionrateadjustment` | **0** | `adjust.rs:585-604` never fires. |
| `altcriteriaratio` | 60 | `adjust.rs:620-680` builds an E85 duplicate block with the pollutant re-tagged **+10000**. Pollutant 10001 is not in the run's scope, the duplicate block is never merged into the original, and `MOVESOutput` carries no 10001 row. Not modelled; recorded here so a reader does not mistake the table's presence for a missing step. |
| `generalfuelratioexpression` | 174 | The fuel-effect *expressions*, which MOVES evaluates upstream of the snapshot into `generalfuelratio` and `criteriaratio`. Every physical fuel property in `fuelformulation` reaches this fixture only through those evaluated tables. |
| `m6sulfurcoeff`, `tempsulfur*`, `debugsulfuroutputtable` | various | Working tables of the sulfur model that produced `criteriaratio`, captured because the snapshot captures the whole execution database. |
| `nrcrankcaseemissionrate` | 126 | NONROAD's crankcase rates. This is an ONROAD run. |

---

## 2. The computation chain

### 2.1 What is inherited unchanged

S1–S12 (activity, cohorts, the fuel-usage rebase) and the drive-cycle
operating-mode weights `W` are `docs/mixed-onroad.md` §2.1–§2.3, unchanged. One
simplification relative to `process-tirewear`: **`W` is one relation again**.
That document had to key it by pollutant-process because tire wear's
`RatesOpModeDistribution` comes from a different generator; here every
pollutant-process is on process 1, so `BaseRateGenerator` drives the cycles
itself for all of them (`mod.rs:156-161`) and the axis is not needed. The three
crankcase pollutant-processes have no operating-mode distribution at all — they
are not rated.

### 2.2 The rate: `emissionRateByAge`, and a seventh key pair

A criteria-pollutant rate **deteriorates**, so MOVES stores it per age group:
`emissionRateByAge` carries an `ageGroupID` column and `agecategory` maps each
of the 41 ages onto one of seven groups (3, 405, 607, 809, 1014, 1519, 2099).
The cohort's model year fixes its age and its age fixes its group, so this is
one more key pair on the join J22 already made and **not** a new axis — the
document already carried `rt_ageGroupID` because `mixed-onroad` needed it for
the EV-efficiency lookup.

Dropping the key would not fail loudly. It would sum seven rates onto every
cohort, which is a factor of a few and passes any per-pollutant sum tolerance.

`sbweightedemissionratebyage` and `baseratebyage_1_2020` are the reference's own
intermediate tables for this stage; §6.2 pins nine cells of the second.

### 2.3 The fuel half of S15: formulations, market share and two ratios

`BaseRateCalculator` does not adjust a base rate once. It expands it into one
rate **per fuel formulation** the county's region is supplied for that fuel type
(`adjust.rs:206-262`), scales each one, and re-collapses them weighted by market
share (`aggregate.rs:28-45`):

```
emissionQuant = SUM over formulations f of  marketShare[f] x rate x G[f] x C[f]
```

`G` is the general fuel ratio and `C` the criteria ratio, each blended between
its normal and GPA arm by `county.GPAFract` (`adjust.rs:456-458`, `:480-482`).
The supply is resolved as
`fuelsupply → fuelformulation.fuelSubtypeID → fuelsubtype.fuelTypeID`, scoped by
region (through `regioncounty`), fuel year and month group.

In this county each fuel type is supplied in **exactly one** formulation at
market share 1 — gasoline in 9114, diesel in 25003, E85 in 27002, electricity in
90 — so the sum collapses and `rt_fuelFactor` is just that formulation's
`criteriaratio.ratio`. §7.2 records what that means for what is checked here.
The fifth supply row, formulation 28001, is fuel subtype 30, which `fuelsubtype`
does not carry; the inner join drops it.

`criteriaratio` is keyed `(fuelFormulationID, polProcessID, sourceTypeID,
modelYearID, ageID)` — an **exact** key with no range predicate anywhere in it,
which no other lookup in this chain is. A miss is a factor of **one**, not a
dropped row (`adjust.rs:481` is an `if let Some`), and electricity has no row at
all.

### 2.4 The temperature adjustment, which at this hour is entirely humidity

`generalTempAdjust` (`adjust.rs:87-141`) has four arms. Two are reachable here:

* **standard quadratic** — `1 + (T − 75)(A + (T − 75)B)`, for THC and CO;
* **NOx** — a fuel-specific temperature term times a humidity factor `k`:

  ```
  diesel : t = (T > 77) ? 0 : (77 − T) x A          factor = (1 + t) x k
  other  : t = (T − 75)(A + (T − 75)B)              factor = (1 + t) x k
  ```

Every `A` and `B` is 0 here (§1.3), so `t` = 0 and the whole temperature half is
1. **`k` is not.** `calculateNOxK` (`adjust.rs:160-188`) selects its formula by
a **free-text column**, `noxhumidityadjust.humidityNOxEq`:

| fuel | equation | argument | bounds | k |
|---|---|---|---|---|
| 1 gasoline | `CFR 86` | `specificHumidity` = 10.0537 g/kg | [3, 17.71] | `1 − 0.0329(h − 10.71)` = **1.0215928** |
| 5 E85 | `CFR 86` | same | same | **1.0215928** |
| 2 diesel | `CFR 1065` | `molWaterFraction` = 0.0159291 | [0.002, 0.035] | `1/(9.953x + 0.832)` = **1.0095484** |
| 9 electricity | *(no row)* | — | — | **1** |

The two equations read **different columns in different units**. Dropping `k`
moves every NOx row by more than 2 %, which the 1e-3 per-pollutant sum tolerance
in `tolerance.toml` would catch but no structural check would.

A text column that selects a formula is *code*, and it is ported as code: the
column is decoded to the `humidity_equation` enum by a `codes` map on the
binding — the same device `year.isBaseYear` uses for Y/N — and the branch is
arithmetic in the document. A third equation name falls through to 1, which is
the Go's `_` arm and not a silent default of ours.

The bound is **not** a clamp: the Go writes `if v < low { v = low }; if v > up {
v = up }`, which yields `up` when the bounds are crossed rather than trapping.
`bounded_humidity` is `min(max(v, low), up)`, which reproduces that.

### 2.5 `CrankcaseEmissionCalculatorNonPM`

The DAG records it as `subscribes_directly: false`, `subscriptions: []`,
`registrations_count: 180`, `depends_on: [AirToxicsCalculator,
BaseRateCalculator, HCSpeciationCalculator, NO2Calculator, NOCalculator,
SO2Calculator]`. It is chained off **six** calculators rather than one, and only
one of them — `BaseRateCalculator` — is live in this run. Its 180 registrations
are 60 pollutants × processes **15, 16 and 17**; process 1 belongs to
`BaseRateCalculator`. So the six pollutant-process pairs of this RunSpec are
split between two calculators, and the split is read from the DAG rather than
assumed. (A bare `CrankcaseEmissionCalculator` also exists in the DAG with zero
registrations and no subscription: it is the never-instantiated Java base class,
and it is dead.)

Its whole arithmetic (`crankcase_emission.rs:44-56`) is:

```
crankcaseEmission = exhaustEmission x crankcaseRatio
```

with the crankcase process in place of the exhaust one, the pollutant, the
dimension cell and the model year unchanged. `crankcaseRatio` is looked up per
`(polProcessID, sourceTypeID, regClassID, fuelTypeID)` under an inclusive
model-year band. Both halves of that lookup are load-bearing:

| pollutant-process | fuel | 1950–1968 | 1969–2060 | 1950–2000 | 2001–2060 |
|---|---|---|---|---|---|
| 115 (THC) | 1, 5 | 0.33 | **0.0132** | | |
| 115 | 2 | | | **0.037** | **0** |
| 215 (CO) | 1 | 0.13 | **0.00052** | | |
| 215 | 5 | 0.00052 | **0.00052** | | |
| 215 | 2 | | | **0.013** | **0** |
| 315 (NOx) | 1 | 0.001 | **0.00004** | | |
| 315 | 5 | 0.00004 | **0.00004** | | |
| 315 | 2 | | | **0.001** | **0** |

* **The band.** For gasoline only the 1969+ band is reachable from model year
  1980, and the unreachable one is 25 times larger — a document that took the
  first matching row would be wrong on every gasoline cell. For diesel *both*
  bands are live inside 1980–2020, and the second is zero.
* **The key.** `regClassID` is 20 on every row and the cohorts are regClass 20
  too, so the pair matches — but it is a real key and not a formality:
  `MOVESOutput` reports `regClassID` as **NULL**, so a document that read the
  output column instead of the cohort would join 0 against 20 and emit no
  process-15 row at all. And `fuelTypeID` has no 9, which is §0.2.
* **The pollutant.** The three ratios differ by four orders of magnitude on the
  same fuel, so a lookup that lost the pollutant-process key could not pass.

The document reads the chain itself — which pollutant-process is computed from
which — from `runspecchainedto`, MOVES's own declaration, rather than writing
`115 = ratio × 101`.

### 2.6 The output relation, and the first ragged blocks in this port

`process-brakewear` and `process-tirewear` laid MOVESOutput out as
pollutant-process-major blocks of `n_outputCohort × n_runspecday`, with a cohort
rank shared by every block. That works only while every block spans the same
cohorts. Here three blocks are 124 cohorts long and three are 104.

The fix is to stop addressing an output row by *(block, cohort)* and address it
by a **global rank over the rate relation**:

```
rt_emits[b]        = isChained[b] ? chainSourceEmits[b] x hasChainRatio[b] : survives[b]
rt_prefixEmitted[b]= SUM over x <= b of rt_emits[x]
rt_outputRank[b]   = rt_emits[b] x rt_prefixEmitted[b]        -- dense 1..684
output row o       = (rank, day) with rank = major(o, n_runspecday)
```

Nothing in that needs a block to be rectangular, and the pollutant-process is
carried by the rate row the rank reaches rather than by the layout. It is the
same prefix-count device `docs/esm-conventions.md` §22 describes, applied one
level up; §31 records the rule.

The two arms of `rt_emits` are the two calculators, stated as arithmetic: an
exhaust row emits when `BaseRateCalculator` selects **and rates** its cohort; a
crankcase row emits when its exhaust row did **and** the ratio table has a row
for it.

`pp_emittedCohortCount` then recomputes 124/104/124/104/124/104 per
pollutant-process. **That is the assertion a row count cannot make**: 1,368 is
equally consistent with six blocks of 114.

---

## 3. Join structure

J1–J37 are `docs/mixed-onroad.md`'s and `docs/process-tirewear.md`'s. Four are
new, and one is changed.

| id | left | right | key pairs | residual predicate |
|---|---|---|---|---|
| J22′ | rate × operating mode | `emissionratebyage` | polProcessID, opModeID, **ageGroupID**, shortModYrGroupID, regClassID, engTechID, fuelTypeID | — |
| J38 | rate row | `crankcaseemissionratio` | polProcessID, sourceTypeID, regClassID, fuelTypeID | `model_year_in_range` |
| J39 | rate row × supply row | `criteriaratio` | fuelFormulationID, polProcessID, sourceTypeID, modelYearID, ageID | — |
| J40 | rate row × supply row | `generalfuelratio` | fuelFormulationID, polProcessID, sourceTypeID | `in_inclusive_range` on model year **and** on age |
| J41 | rate row | `noxhumidityadjust` | fuelTypeID | — |

J22′ is a **cost** decision as well as a reading order: 590,709 rate rows
against 984 × 41 rate-mode cells is affordable only as one equi-join
(`docs/esm-conventions.md` §3).

J38, J39, J40 and J41 are all LEFT joins in effect — a miss is a factor of one
for J39/J40/J41 and a **dropped row** for J38 — so each carries a separate
`bool_and_or` presence aggregate beside its value aggregate. The difference
between "factor of one" and "dropped row" is the whole of §0.2, and it is the
one place in this chain where reading the presence wrongly changes the row set
rather than a number.

J40's two bands are why `lib/keys.esm` now carries `in_inclusive_range` under
the shape's own name, with `model_year_in_range` delegating to it: MOVES bands
ages exactly as it bands model years, and `generalfuelratio` carries both bands
on one row.

---

## 4. Reusable shapes (`expression_templates`)

**One template is new here. The other eight this rung needs already existed**
— `docs/process-nox-speciation.md` landed them, because that rung reaches the
same `BaseRateCalculator` arm this one does. They were written independently on
the two branches under the same names and with the same bodies, and the
reconciliation on merge was to delete this branch's copy and instantiate the
library's: one shape, one implementation.

| template | file | provenance | what it is |
|---|---|---|---|
| `in_inclusive_range(value, first, last)` | `lib/keys.esm` | **new here** | The inclusive band, under the name of the shape rather than of the column family it was first used on. |
| `gpa_blend(ratio, ratio_gpa, gpa_fraction)` | `lib/adjustments.esm` | `process-nox-speciation` | The geographic-phase-in interpolation, used at J39 and J40. |
| `bounded_low_then_high(v, low, up)` | `lib/adjustments.esm` | `process-nox-speciation` | The Go's two sequential assignments, which yield `up` when the bounds cross. |
| `nox_humidity_reference()` | `lib/adjustments.esm` | `process-nox-speciation` | 10.71 g/kg. |
| `nox_humidity_cfr86(A, h)` | `lib/adjustments.esm` | `process-nox-speciation` | `1 − A(h − 10.71)`. |
| `nox_humidity_cfr1065(A, B, x)` | `lib/adjustments.esm` | `process-nox-speciation` | `1/(Ax + B)`. |
| `nox_diesel_temperature_ceiling()` | `lib/adjustments.esm` | `process-nox-speciation` | 77 °F. |
| `quadratic_temperature_adjustment(A, B, T)` | `lib/adjustments.esm` | `process-nox-speciation` | `generalTempAdjust`'s standard arm, `adjust.rs:141` — the **additive** term. |
| `nox_temperature_adjustment(A, B, T, is_diesel)` | `lib/adjustments.esm` | `process-nox-speciation` | Its NOx arm, `adjust.rs:126-141`, with the diesel ceiling inside. Also additive. |

Both temperature templates return the **additive** term and the caller writes
`1 + t` once, so the diesel ceiling is not remembered anywhere else and no call
site has to know which arm returns a factor. Every one of them carries a FORM
and no coefficients: the two humidity terms, the two temperature terms and the
GPA fraction are all columns of the snapshot, read at the fixture.

### 4.0 Why `in_inclusive_range` is not `model_year_in_range` under a new name

`model_year_in_range` was already in `lib/keys.esm` and is instantiated 34
times across the port. J40 needs the same shape on an **age** band —
`generalfuelratio` carries `minModelYearID`/`maxModelYearID` *and*
`minAgeID`/`maxAgeID` on one row — and the two alternatives were to instantiate
`model_year_in_range` with an age, which makes its three parameter names read
falsely at the call site, or to write the two comparisons out a thirty-fifth
time, which is exactly what the template exists to prevent.

So the shape got its own name and `model_year_in_range` now **delegates** to it
in one line. There is one implementation of the comparison pair in the
repository, not two; the caller-facing name and its parameter names are
unchanged, because they read correctly at all 34 existing call sites; and the
change is byte-neutral, verified by re-emitting all eight pre-existing fixtures
against the pre-change library and diffing.

`flat_relation_major` / `flat_relation_minor` (`lib/keys.esm`) are not new but
are used here for all four flat product relations — the activity relation, the
cohort grid, the rate relation and the output relation — where the three earlier
onroad fixtures spelled each floor division out. They share one
`flat_relation_block_index`, so a boundary cannot be computed two ways.

### 4.1 Shapes deliberately not factored

`crankcaseEmission = exhaust × ratio` is a multiplication. A template for it
would add a name and hide nothing.

---

## 5. Literals and enums

| enum | members |
|---|---|
| `pollutant` | `TotalGaseousHydrocarbons` 1, `CarbonMonoxide` 2, `OxidesOfNitrogen` 3 |
| `process` | `RunningExhaust` 1, `CrankcaseRunningExhaust` 15 |
| `fuel_type` | `Gasoline` 1, `Diesel` 2, `Ethanol` 5, `Electricity` 9 |
| `humidity_equation` | `CFR86` 1, `CFR1065` 2 |
| `operating_mode` | `Braking` 0, `Idling` 1, `HighestBinnedMode` 40, `CoarseModerateSpeedHighVSP` 26, `CoarseHighSpeedHighVSP` 36 |
| `source_bin_slot` | the four decimal slot exponents, 10/12/14/16 |

Three reference constants carry the numbers that decide a branch, and all three
are `lib/adjustments.esm` templates rather than literals in this document:
`exhaust_temperature_reference` 75 °F (shared with the NONROAD adjustment,
which is referenced to the same temperature), `nox_diesel_temperature_ceiling`
77 °F and `nox_humidity_reference` 10.71 g/kg. **Three different reference
temperatures appear in one function of `adjust.rs` — 72 for the EV arm, 75 for
the standard one and 77 for diesel NOx — and none of them is a typo.**

---

## 6. Hand-checkable worked examples

### 6.0 Run-level values used by every example

```
temperature      59.5 degF        heatIndex           59.5 degF
specificHumidity 10.053684293477  molWaterFraction    0.015929059029
GPAFract         0                acActivity          0 (raw -0.2969815, clamped)
k(gasoline,E85)  1.0215928        k(diesel)           1.0095484
sho[day 2, age 40] 2.43728        sho[day 2, age 30]  1.1036
sho[day 2, age 1]  32.6255        sho[day 5, age 22]  46.8299
noOfRealDays: day 2 -> 2, day 5 -> 5
```

### 6.1 Worked example A — THC, gasoline, MY 1980, weekend

```
baseRateByAge(101, hourDay 72, 1980, fuel 1) = 84.6858
criteriaratio(9114, 101, 21, 1980, age 40)   = 0.915810241181
temperature factor (not NOx, terms 0)        = 1
activity = sho/noOfRealDays = 2.43728/2      = 1.21864

process 1  : 84.6858 x 0.915810241181 x 1 x 1.21864 = 94.5127   (reference 94.513)
process 15 : 94.513 x 0.0132                        = 1.24757   (reference 1.24757)
```

The gasoline ratio is the **1969–2060** band's 0.0132. Taking the table's first
row would give 0.33 and 31.2.

### 6.2 Worked example B — NOx, gasoline, MY 2019, weekend

```
baseRateByAge(301, 72, 2019, 1) = 1.1234
criteriaratio                   = 0.927694995111
temperature factor              = (1 + 0) x k = 1.0215927867446069
activity = 32.6255/2            = 16.31275

process 1  : 1.1234 x 0.927694995111 x 1.0215928 x 16.31275 = 17.3677  (reference 17.3678)
process 15 : 17.3678 x 0.00004                              = 6.9471e-4 (reference 6.94712e-4)
```

Without `k` the process-1 value would be 17.000 — a 2.1 % error, and the same
2.1 % on the crankcase row that is computed from it.

### 6.3 Worked example C — THC, diesel, MY 1990, weekend, and MY 2010

```
MY 1990: baseRateByAge(101, 72, 1990, 2) = 0.0585755
         criteriaratio(25003, 101, 21, 1990, age 30) = 0.975325
         activity = 1.1036/2 = 0.5518
         process 1  : 0.0585755 x 0.975325 x 0.5518 = 0.0315243  (reference 0.0315244)
         process 15 : 0.0315244 x 0.037             = 0.00116640 (reference 0.0011664)

MY 2010: process 1 (CO)  = 31.4358
         process 15 (CO) = 31.4358 x 0            = 0            (reference 0.0)
```

The MY 2010 crankcase row **exists and is zero**. 114 of the 624 crankcase rows
are — three pollutants × 19 diesel model years × 2 day types.

### 6.4 Worked example D — electricity, and the row that is not there

```
MY 2020, electricity, weekend, THC:
  baseRateByAge(101, 72, 2020, 9) = 0.0     -- an electric car emits no hydrocarbons
  process 1  : 0.0                          (reference 0.0)
  process 15 : NO ROW -- crankcaseEmissionRatio has no fuelTypeID 9 row at all
```

Compare with 6.3's MY 2010 diesel: a zero and an absence, side by side, and the
document has to produce a different *shape* for each.

### 6.5 The reproduction script

An independent reproduction of the whole fixture from the snapshot's own input
tables, in plain Python. It **takes nothing from the reference**:
`baseratebyage_1_2020`, `sbweightedemissionratebyage`, `sourcebindistribution`
and `baserateoutput` are read by nothing here, and `sho` and `MOVESOutput` only
by the final comparison. `./run-crankcase-running-oracle.sh` extracts and runs
it.

```python
#!/usr/bin/env python3
"""process-crankcase-running reproduction from the snapshot's own input tables."""
import sys, collections
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
COUNTY, ELECTRICITY = 26161, 9
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
sel={r["hourDayID"] for r in T("runspechourday")}
sho={}
for d in DAYS:
    assert HD[d] in sel
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
# ---- drive cycle W (polprocess-independent at national scale) ----
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
# ---------------------------------------------------------------------------
# S13(a'): the RATE, which is `emissionratebyage` and not `emissionrate`.
# Criteria pollutants deteriorate, so their rates carry an ageGroupID; the
# cohort's model year fixes its age and therefore its group, so this is one
# more key pair on the same join and not a new axis.
def slot(b,scale): return (b//scale)%100
agegroup={r["ageID"]:r["ageGroupID"] for r in T("agecategory")}
ERBA=T("emissionratebyage")
def rates(pp):
    d={}
    for r in ERBA:
        if r["polProcessID"]!=pp: continue
        b=r["sourceBinID"]
        d[(slot(b,10**16),slot(b,10**14),slot(b,10**12),slot(b,10**10),
           r["opModeID"],r["ageGroupID"])]=float(r["meanBaseRate"])
    return d
fleetgroup={r["regClassID"]:r["fleetAvgGroupID"] for r in T("regulatoryclass")}
evfrac={(r["modelYearID"],r["fleetAvgGroupID"]):float(r["evFraction"]) for r in T("evsalesfraction")}
FA=T("fleetavgadjustment")
def evsf(pp,my,fuel,rc):
    if fuel==ELECTRICITY: return 1.0
    g=fleetgroup[rc]; e=evfrac.get((my,g))
    row=next((r for r in FA if r["polProcessID"]==pp and r["fleetAvgGroupID"]==g
              and r["beginModelYearID"]<=my<=r["endModelYearID"]),None)
    if e is None or row is None: return 1.0
    m=float(row["evMultiplier"]); den=(1.0-e)+e*m; v=1.0/(1.0-e*m/den)
    cap=row["adjustmentCap"]
    return min(v,float(cap)) if cap is not None and float(cap)>0.0 else v
PPA={r["polProcessID"]:(r["pollutantID"],r["processID"]) for r in T("pollutantprocessassoc")}
DIRECT=[p for p in POLPROCS if PPA[p][1]==1]
CHAINED=[p for p in POLPROCS if p not in DIRECT]

# S13(b), S14: the source-bin weighted rate and the operating-mode collapse.
sbw_all={}; br_all={}; regclass_of={}
for pp in DIRECT:
    coh=cohorts(pp); sbaf=rebase(coh); rate=rates(pp)
    sbw=collections.defaultdict(float)
    oms={k[4] for k in rate}
    for (my,fuel,et,rc),frac in sbaf.items():
        smy=shortgroup[mygroup[(pp,my)]]; ag=agegroup[YEAR-my]
        ev=evsf(pp,my,fuel,rc)
        for om in oms:
            r=rate.get((fuel,et,rc,smy,om,ag))
            if r is not None: sbw[(my,fuel,rc,om)]+=frac*r*ev
    sbw_all[pp]=sbw
    br=collections.defaultdict(float)
    for (my,fuel,rc,om),v in sbw.items():
        for d in DAYS: br[(HD[d],my,fuel,rc)]+=v*W[(HD[d],om)]
    br_all[pp]=br
    for (hd,my,fuel,rc) in br: regclass_of[(pp,hd%10,my,fuel)]=rc

# ------------------------------------------------- the calculator's fuel half
# BaseRateCalculator expands each base rate over the FORMULATIONS the county's
# fuel supply carries for that fuel type (adjust.rs:206-262), scales each by the
# general-fuel-ratio and the criteria ratio, and re-collapses them weighted by
# marketShare (aggregate.rs:28-45).
MONTHGROUP={r["monthID"]:r["monthGroupID"] for r in T("monthofanyyear")}[MONTH]
REGIONS={r["regionID"] for r in T("regioncounty")
         if r["countyID"]==COUNTY and r["fuelYearID"]==FUELYEAR}
SUBFUEL={r["fuelSubtypeID"]:r["fuelTypeID"] for r in T("fuelsubtype")}
FORM={r["fuelFormulationID"]:r["fuelSubtypeID"] for r in T("fuelformulation")}
supply=collections.defaultdict(list)
for r in T("fuelsupply"):
    if (r["fuelRegionID"] not in REGIONS or r["fuelYearID"]!=FUELYEAR
        or r["monthGroupID"]!=MONTHGROUP): continue
    sub=FORM[r["fuelFormulationID"]]
    if sub not in SUBFUEL: continue
    supply[SUBFUEL[sub]].append((r["fuelFormulationID"],float(r["marketShare"])))
GPA=float([r for r in T("county") if r["countyID"]==COUNTY][0]["GPAFract"])
GFR=T("generalfuelratio")
CR={(r["fuelFormulationID"],r["polProcessID"],r["sourceTypeID"],r["modelYearID"],r["ageID"]):
    (float(r["ratio"]),float(r["ratioGPA"])) for r in T("criteriaratio")}
def gpa_blend(v,vgpa): return v+GPA*(vgpa-v)
def gfr_factor(ff,pp,my,age):
    f=1.0
    for r in GFR:
        if (r["fuelFormulationID"]==ff and r["polProcessID"]==pp and r["sourceTypeID"]==ST
            and r["minModelYearID"]<=my<=r["maxModelYearID"]
            and r["minAgeID"]<=age<=r["maxAgeID"]):
            f*=gpa_blend(float(r["fuelEffectRatio"]),float(r["fuelEffectRatioGPA"]))
    return f
def cr_factor(ff,pp,my,age):
    v=CR.get((ff,pp,ST,my,age))
    return 1.0 if v is None else gpa_blend(*v)
def fuel_factor(pp,my,fuel,age):
    return sum(share*gfr_factor(ff,pp,my,age)*cr_factor(ff,pp,my,age)
               for ff,share in supply[fuel])

# --------------------------------------- the temperature + humidity adjustment
ZMH=[r for r in T("zonemonthhour")
     if r["monthID"]==MONTH and r["zoneID"]==ZONE and r["hourID"]==HOUR][0]
TEMP,HEAT=float(ZMH["temperature"]),float(ZMH["heatIndex"])
SPECHUM,MOLFRAC=float(ZMH["specificHumidity"]),float(ZMH["molWaterFraction"])
TA=T("temperatureadjustment")
NHA={r["fuelTypeID"]:r for r in T("noxhumidityadjust")}
NOX, DIESEL = 3, 2
def hbound(v,lo,up):
    if v<lo: v=lo
    return up if v>up else v
def nox_k(fuel):
    """adjust.rs:170-188 `calculateNOxK`."""
    n=NHA.get(fuel)
    if n is None: return 1.0
    lo,up=float(n["humidityLowBound"]),float(n["humidityUpBound"])
    if n["humidityNOxEq"]=="CFR 86":
        return 1.0-float(n["humidityTermA"])*(hbound(SPECHUM,lo,up)-10.71)
    if n["humidityNOxEq"]=="CFR 1065":
        return 1.0/(float(n["humidityTermA"])*hbound(MOLFRAC,lo,up)+float(n["humidityTermB"]))
    return 1.0
def temp_terms(pp,fuel,regclass,my):
    """adjust.rs:495-520 -- the exact regulatory class, then the regClassID 0
    WILDCARD, then a zero-valued default. NEITHER exists for 101/201/301 here."""
    for rc in (regclass,0):
        for r in TA:
            if (r["polProcessID"]==pp and r["fuelTypeID"]==fuel and r["regClassID"]==rc
                    and r["minModelYearID"]<=my<=r["maxModelYearID"]):
                return float(r["tempAdjustTermA"]),float(r["tempAdjustTermB"])
    return 0.0,0.0
def temp_factor(pp,pol,fuel,regclass,my):
    """adjust.rs:87-141 `generalTempAdjust`, the two arms this run reaches."""
    a,b=temp_terms(pp,fuel,regclass,my)
    if pol==NOX:
        if fuel==DIESEL: t=0.0 if TEMP>77.0 else (77.0-TEMP)*a
        else:            t=(TEMP-75.0)*(a+(TEMP-75.0)*b)
        return (1.0+t)*nox_k(fuel)
    return 1.0+(TEMP-75.0)*(a+(TEMP-75.0)*b)

# ------------------------------------------------------------ S16, S17, S18
realdays={r["dayID"]:float(r["noOfRealDays"]) for r in T("dayofanyweek")}
def scc(fuel,proc): return "%d"%(22*10**8+fuel*10**6+ST*10**4+ROAD*10**2+proc)
rows={}
for pp in DIRECT:
    pol,proc=PPA[pp]
    for (hd,my,fuel,rc),base in br_all[pp].items():
        age=YEAR-my; d=hd%10
        q=base*fuel_factor(pp,my,fuel,age)*temp_factor(pp,pol,fuel,rc,my)
        rows[(pol,proc,d,my,fuel)]=q*sho[(hd,age)]/realdays[d]
direct_rows=len(rows)

# ------------------------------- CrankcaseEmissionCalculatorNonPM, the whole of
# it: crankcase_emission.rs:44-56. The exhaust row's quantity times a tabulated
# ratio, the crankcase process in place of the exhaust one, everything else
# unchanged -- and an INNER JOIN, so a cohort with no ratio row emits NOTHING.
CCR=T("crankcaseemissionratio")
for c in T("runspecchainedto"):
    outpp,outpol,outproc=c["outputPolProcessID"],c["outputPollutantID"],c["outputProcessID"]
    inpp,inpol,inproc=c["inputPolProcessID"],c["inputPollutantID"],c["inputProcessID"]
    for (pol,proc,d,my,fuel),q in list(rows.items()):
        if (pol,proc)!=(inpol,inproc): continue
        rc=regclass_of[(inpp,d,my,fuel)]
        for r in CCR:
            if (r["polProcessID"]==outpp and r["sourceTypeID"]==ST
                    and r["regClassID"]==rc and r["fuelTypeID"]==fuel
                    and r["minModelYearID"]<=my<=r["maxModelYearID"]):
                rows[(outpol,outproc,d,my,fuel)]=q*float(r["crankcaseRatio"])
crank_rows=len(rows)-direct_rows

# ------------------------------------------------------------------- compare
ref_sho={(r["hourDayID"],r["ageID"]):float(r["SHO"]) for r in T("sho")}
worst_sho=max(abs(sho[k]-v)/v for k,v in ref_sho.items())
print("sho:           %3d rows, worst relative error %.3e"%(len(ref_sho),worst_sho))
assert worst_sho<1e-5, "sho: worst relative error %.3e exceeds 1e-5"%worst_sho

out=pq.read_table(SNAP+"/tables/db__out_process_crankcase_running__movesoutput.parquet").to_pylist()
def key(o): return (o["pollutantID"],o["processID"],o["dayID"],o["modelYearID"],o["fuelTypeID"])
worst,worst_key=0.0,None
for o in out:
    k=key(o); q=rows[k]
    assert scc(k[4],k[1])==o["SCC"], (k,scc(k[4],k[1]),o["SCC"])
    e=float(o["emissionQuant"])
    rel=abs(q-e)/abs(e) if e else abs(q)
    if rel>worst: worst,worst_key=rel,k
print("emissionQuant: %d rows, worst relative error %.3e at "
      "(pollutant %d, process %d, day %d, MY %d, fuel %d)"%(len(out),worst,*worst_key))
# ASSERTED, not merely printed (docs/esm-conventions.md 21): ./run-tests.sh reads
# this script's EXIT CODE, so a regression that leaves the key set intact and
# moves every value would otherwise be reported green with the evidence in a log.
assert len(rows)==len(out), (len(rows),len(out))
assert set(rows)=={key(o) for o in out}
assert worst<2e-5, "emissionQuant: worst relative error %.3e exceeds 2e-5"%worst

# The key set, WITH THE PROCESS SPLIT MADE EXPLICIT: a row count alone cannot
# tell 248+208 from 228+228, and the whole point of this rung is that the two
# processes do NOT span the same cohorts.
exhaust=sorted({(k[3],k[4]) for k in rows if k[1]==1})
crank=sorted({(k[3],k[4]) for k in rows if k[1]==15})
assert len(exhaust)==124 and len(crank)==104, (len(exhaust),len(crank))
assert {f for _,f in exhaust}=={1,2,5,9} and {f for _,f in crank}=={1,2,5}
assert set(crank)<set(exhaust)
assert crank_rows==3*len(crank)*len(DAYS) and direct_rows==3*len(exhaust)*len(DAYS)
print("key set:       process  1 -- 3 pollutants x %d cohorts x %d day types = %d rows"
      %(len(exhaust),len(DAYS),direct_rows))
print("key set:       process 15 -- 3 pollutants x %d cohorts x %d day types = %d rows"
      %(len(crank),len(DAYS),crank_rows))
print("key set:       %d rows, exact, and process 15 is a STRICT SUBSET of "
      "process 1: the 20 electricity cohorts carry no crankcaseEmissionRatio "
      "row and are dropped by its inner join" % len(rows))

# Three structural facts no comparison against MOVESOutput could catch.
# (1) The ratio is BANDED on model year, and the band test is load-bearing in
#     both directions. Diesel has two bands INSIDE this run's 1980-2020 window
#     -- 0.037 to model year 2000 and exactly 0 from 2001 -- so a document that
#     took the first matching row would be wrong on half the diesel cells.
#     Gasoline has two bands of which only ONE is reachable, and the unreachable
#     one is 25 times larger, so ignoring the band would be wrong on all of them.
def bands(pp,fuel):
    return sorted((r["minModelYearID"],r["maxModelYearID"],float(r["crankcaseRatio"]))
                  for r in CCR if r["polProcessID"]==pp and r["fuelTypeID"]==fuel)
assert bands(115,DIESEL)==[(1950,2000,0.037),(2001,2060,0.0)], bands(115,DIESEL)
assert bands(115,1)==[(1950,1968,0.33),(1969,2060,0.0132)], bands(115,1)
reachable=[b for b in bands(115,1) if b[0]<=YEAR and b[1]>=YEAR-40]
assert len(reachable)==1 and reachable[0][2]==0.0132
zero=[k for k in rows if k[1]==15 and k[4]==DIESEL and rows[k]==0.0]
assert len(zero)==3*19*len(DAYS), len(zero)
print("               %d of the crankcase rows are EXACTLY zero -- diesel model "
      "years 2001-2019, whose ratio is 0 and whose rows exist anyway"%len(zero))
# (2) `generalfuelratio` carries 39 rows and NONE of them can be reached: every
#     one names a CRANKCASE pollutant-process, and no fuel block ever carries
#     one, because CrankcaseEmissionCalculatorNonPM runs after BaseRateCalculator
#     and does not re-enter it. Its effect on this fixture is exactly 1.
assert {r["polProcessID"] for r in GFR}=={115,215,315}, "generalfuelratio moved"
assert all(gfr_factor(ff,pp,my,YEAR-my)==1.0
           for pp in DIRECT for ff,_ in supply[1] for my in (1980,2000,2020))
# (3) The A/C term is inert at this hour, and it is inert by a CLAMP rather than
#     by absence: fullacadjustment carries 69 rows for exactly these three
#     pollutant-processes.
mgh=[r for r in T("monthgrouphour")
     if r["monthGroupID"]==MONTHGROUP and r["hourID"]==HOUR][0]
ac=(float(mgh["ACActivityTermA"])+HEAT*(float(mgh["ACActivityTermB"])
    +HEAT*float(mgh["ACActivityTermC"])))
assert ac<0.0 and {r["polProcessID"] for r in T("fullacadjustment")}=={101,201,301}
print("NOTE:          the A/C activity term is %.4f before setup.rs:411's "
      "clamp(0,1), so the A/C increment is inert -- by a clamp, not by absence"%ac)
```

### 6.6 Suggested inline `.esm` tests

`fixtures/process-crankcase-running.esm` carries 169 assertions in 11 groups,
against the real snapshot Parquet. The four that a reviewer should look at first
are the ones no comparison against `MOVESOutput` could make:

* `125_cohorts_are_selected_124_are_rated_and_104_carry_a_crankcase_ratio` —
  the process split, per pollutant-process, and the one selected-but-unrated
  cohort (electricity MY 2000) named rather than absorbed;
* `the_crankcase_ratio_is_banded_by_model_year_and_its_absence_drops_the_row` —
  a zero ratio and an absent row asserted separately;
* `the_temperature_adjustment_is_all_humidity_at_this_hour` — every temperature
  term 0 **and** `k` non-trivial on three of four fuels;
* `the_fuel_half_of_S15_...` — `run_generalFuelRatioOnRatedRows` = 0.

---

## 7. Fidelity notes and tolerance

### 7.1 Everything agrees to ~9e-6, and that number is the reference's

The worst cell over all 1,368 rows is **8.702e-06**, at (pollutant 2, process
15, day 2, MY 2014, fuel 5) — and the independent Python reproduction reports
the same figure at the same key, by a different route, which is what makes it a
storage limit rather than an error.

It is a **chained** cell, and that is the pattern `tolerance.toml` records: four
of the port's five worst cells are chained, because a chained pollutant is its
parent times a stored ratio and so carries the parent's residual *plus* the
ratio's quantisation. Here the parent — (CO, process 1, same cell) — is
reproduced to 7.2e-07, the ratio is an exact 0.00052, and the reference stores
the product as 0.001039700000, six significant figures whose half-ulp is
~5e-06 on its own.

`MOVESOutput.emissionQuant` is a `DOUBLE`, but it is computed from a chain of
MariaDB `FLOAT` intermediate tables (`sbweightedemissionratebyage`,
`baseratebyage_*`) whose captured values carry six significant figures. That is
the size of the disagreement.

**No entry in `tolerance.toml` was needed and nothing was widened**: 8.702e-06
is inside the existing `[cell] rel = 2e-5`, and the eight pre-existing fixtures'
worst cells are unmoved at 4.561e-06, 7.294e-06, 7.434e-06, 7.495e-06,
8.151e-06, 8.250e-06, 8.320e-06 and 9.482e-06.

### 7.2 What this fixture does **not** check

* **The market-share sum.** Every fuel type in Washtenaw County is supplied in
  exactly one formulation at share 1, so `SUM over f of marketShare[f] x ...`
  is exercised with one term. The expansion and the re-collapse are both
  written, and both are joins rather than a shortcut, but a county with a mixed
  supply would be the first real test of them.
* **The GPA blend.** `GPAFract` is 0, so `gpa_blend` returns its normal arm at
  both call sites. The `ratioGPA` columns are read and the blend is written; a
  GPA county would be the first to distinguish it from `normal_value`.
* **`generalfuelratio`'s value arm.** It reaches 81 (rate row, formulation)
  pairs and none of them carries a rate, so only the *presence* half is
  exercised on a live path. The measurement is asserted rather than the effect.
* **The multi-row general-fuel-ratio case.** `adjust.rs:459-470` loops and
  *multiplies* every matching detail row; the document sums matches, which
  agrees whenever at most one row matches. Here zero match on any rated row.
* **`crankcaseRatioCV`.** Read by nothing. Uncertainty is not modelled anywhere
  in this port.

### 7.3 Precision-sensitive operations, ranked

1. The NOx humidity factor `k` — a 2.1 % effect on a third of the rows, and it
   comes from a text-column branch.
2. The criteria ratio — up to 14 % on the oldest gasoline model years.
3. The crankcase ratio band boundary at diesel model year 2001 — a factor of
   ∞ (0.037 → 0) on 114 rows.
4. The `emissionRateByAge` age-group key — a factor of a few if dropped.

---

## 8. Gaps, uncertainties and things not verified

* The **E85 THC duplication** (`adjust.rs:620-680`, `altcriteriaratio`) is not
  modelled. Its output is pollutant 10001, which is outside the run's scope and
  absent from `MOVESOutput`; the argument that it cannot affect the six emitted
  pollutant-processes is read from `build_e85_block`, which returns a *new*
  block and leaves the original untouched. Not verified against canonical Java.
* The claim that `MOVESWorkerOutput` still carries `regClassID` = 20 when the
  crankcase join runs — while `BaseRateOutput` reports 0 and `MOVESOutput`
  reports NULL — is inferred from the fact that process-15 rows exist at all
  (§2.5). It is not traced through `moves.rs`'s output wiring.
* `imcoverage` is empty in this snapshot, so the I/M blend, `imfactor`'s 22,608
  rows and the whole `meanBaseRateIM` half of `emissionRateByAge` are
  **untested** by this fixture. `lib/adjustments.esm`'s `im_blend` exists and is
  used by the evaporative fixtures; the exhaust I/M path has no coverage in this
  port yet.
* Processes **16** (Crankcase Start) and **17** (Crankcase Extended Idle) are
  the other 120 of `CrankcaseEmissionCalculatorNonPM`'s 180 registrations.
  `process-crankcase-start` and `process-crankcase-extidle` snapshots exist and
  are not ported; the arithmetic is the same and the *exhaust* side is not.
