# `process-refueling` — computation specification

The port specification for the first fixture that does not compute a rate on the
running-exhaust spine at all, written to the method of `docs/process-brakewear.md`:
the input inventory determined from evidence, the chain with source lines into
`../moves.rs`, every join with its exact key pairs, and worked examples whose
numbers can be checked by hand.

`RefuelingLossCalculator` is a **chained** calculator, and it is chained onto
something no earlier fixture consumed: `BaseRateCalculator`'s **Total Energy
Consumption output**, which it uses as its *activity*. Its whole arithmetic is
one product and one quotient,

```
emissionQuant = lossRate x energy / (energyContent x fuelDensity)
```

— energy divided by kilojoules-per-gallon is **gallons delivered**, and both
loss rates are grams of Total Gaseous Hydrocarbons per gallon. So
`docs/mixed-onroad.md`'s activity chain, cohort structure, fuel-usage rebase and
drive-cycle operating-mode weights are this document's too, unchanged and not
restated; what is specified here is the five things that are new:

1. the activity is an **energy output**, in kilojoules, and the unit rebase that
   would turn it into Million BTU happens **after** every chained calculator has
   run (§2.2);
2. the run carries **seven** pollutant-processes in three roles — two the
   calculator produces, three it consumes, and two it must not touch (§2.1);
3. two of the three energy pollutant-processes contribute **exactly zero**, for
   a reason that is a road-type join in the reference and an operating-mode
   contraction in the port, and the two agree only because no off-network road
   type is selected (§2.2);
4. the two emitted blocks are **different sizes** — 64 cohorts and 104 — so the
   output relation has one rank across the whole rate relation and no per-block
   cohort ordinal (§0.2, §3.3);
5. two of the calculator's stages are **inert in this snapshot** and are checked
   in a component instead (§7.2).

---

## 0. The fixture at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/process-refueling.xml` |
| Model | ONROAD, `modelscale` `Inv` (inventory), `modeldomain` `DEFAULT` |
| Geography | county 26161 (Washtenaw, Michigan), zone 261610, link 2616104 |
| Time | year 2020, month **8**, hour **7**, day types **2 (weekend) and 5 (weekday)** |
| Vehicles | sourceTypeID 21 (passenger car); fuel types **1, 2, 5, 9** |
| Road | roadTypeID 4 (urban restricted access) |
| Pollutant/process emitted | **118** (THC x Refueling Displacement Vapor Loss) and **119** (THC x Refueling Spillage Loss) |
| Pollutant/process consumed | **9101**, **9102**, **9190** (Total Energy Consumption x running / start / extended-idle exhaust) |
| Model years | 1980–2020 (41) |
| Output | `db__out_process_refueling__movesoutput`, **336 rows** |
| Output units | **grams**; `outputtimestep` **Hour** |
| Calculator path | `TotalActivityGenerator` → `SourceBinDistributionGenerator` → `BaseRateGenerator` → `BaseRateCalculator` → **`RefuelingLossCalculator`** → output aggregation |
| Snapshot | 237 non-empty tables |

### 0.1 The RunSpec on disk does not describe the captured run

The same rule as `docs/mixed-onroad.md` §0.1 and `docs/process-brakewear.md`
§0.1, and for the same reason: the XML's `<month key>`, `<beginhour key>` and
`<day key>` are canonical `RunSpecXML` **0-based indices into sorted ID lists**,
not identifiers. The authority is the execution database's own `runspec*`
tables.

| dimension | `process-refueling.xml` says | the execution database says |
|---|---|---|
| month | 7 | **8** (`runspecmonth`) |
| hour | 6 | **7** (`runspechour`) |
| day types | 5 | **2 and 5** (`runspecday`, 2 rows) |
| fuel types | 1 | **1, 2, 5, 9** (`runspecsourcefueltype`, 4 rows) |
| pollutant/process | 8618, 8619, 118, 119 | **118, 119, 8618, 8619, 9101, 9102, 9190** |

The pollutant/process row is the one that is not a stale-capture correction and
is the most important line of the table. `ExecutionRunSpec.flagRequiredPollutantProcesses`
**adds** the inputs a chained calculator consumes: a refueling-only RunSpec
silently acquires Total Energy Consumption for running (1), start (2) and
extended-idle (90) exhaust, because without them `BaseRate` emits no energy and
the chained calculator sees no input at all. `moves.rs` records the consequence
of missing that as a measured gate failure — "`process-refueling`: 0 rows vs
canonical 336" (`crates/moves-cli/src/run.rs:1184-1199`).

**The scope is the same as `process-brakewear`'s**, which is worth stating
because it is what makes this fixture cheap to trust: month 8, hour 7, day types
2 and 5, county 26161, source type 21, road type 4. `baserate_1_2020` is
byte-identical between the two snapshots on all 250 of its 9101 rows, so the
energy spine here is `process-brakewear`'s energy block and, one rung further
back, `mixed-onroad`'s 250 rows at a different hour.

### 0.2 Why 336 rows, and why the two blocks are different sizes

```
336 = 64 displacement cohorts x 2 day types  +  104 spillage cohorts x 2 day types
```

Every earlier multi-block fixture in this repository emits the same cohort set
in every block. This one does not, and the two reasons are both inner joins:

| block | fuel types | model years | cohorts |
|---|---|---|---|
| 118 displacement | 1, 5 | 41 gasoline, 23 E85 | **64** |
| 119 spillage | 1, 2, 5 | 41 gasoline, 40 diesel, 23 E85 | **104** |

* **`refuelingcontroltechnology` carries fuel types 1 and 5 only** — 9,102 rows,
  all `processID` 18, `sourceTypeID` 21 and `regClassID` 20. REFEC-3 inner-joins
  it, so diesel has no displacement rate row at all and the 40 diesel cohorts the
  spillage block keeps are absent from the displacement block.
* **Electricity is dropped from BOTH by REFEC-7.** `fuelsubtype.energyContent`
  is NULL for subtype 90 and `fueltype.fuelDensity` is NULL for fuel type 9, and
  the `RefuelingFuelType` extract keeps only `energyContent > 0 AND fuelDensity > 0`
  — so all 21 electricity cohorts miss the join that converts energy to gallons.
  It is *not* the rate that drops them: `sourcetypetechadjustment` is keyed by
  source type and model year and knows nothing about fuel, so the spillage
  working table **does** have a row for every electricity cohort, with a rate of
  0 because `refuelingfactors.refuelingSpillRate` is 0 for electricity. A
  document that dropped them on the rate would agree with the snapshot on all 336
  rows and be wrong the first time a fuel had a non-zero spill rate and no energy
  content. `fixtures/process-refueling.esm` asserts
  `rt_spillageRowCount = 1` and `rt_hasFuelDivisor = 0` on exactly that cohort.

The 125 (modelYearID, fuelTypeID) cohorts the energy spine carries are
`mixed-onroad`'s own ragged 125, and the fixture asserts that all seven
pollutant-processes select the same 125 rather than assuming it
(`pp_selectedCohortCount`).

**No pollutant-91 output row.** The RunSpec selects THC and TOG on the two
refueling processes and nothing else; energy is a *prerequisite* the execution
run spec added, not a selection, so the 250 energy rows are computed and never
emitted. `baserateoutput` in the same snapshot carries all three sets — 250
energy rows plus the 128 and 208 refueling rows — which is the evidence that the
energy really was computed.

---

## 1. Input inventory

### 1.1 The tables `mixed-onroad` already reads

All 46 of them, unchanged, against this snapshot's copies.
`docs/mixed-onroad.md` §1.2–§1.4 is the inventory. One carries more here:

| table | in `mixed-onroad` | here |
|---|---|---|
| `emissionrate` | 69,200 rows, polProcessID 9101 only | **69,688 over three**: 57,040 for 9101 on 23 running modes, 12,160 for 9102 on the eight start modes 101–108, and 488 for 9190 at extended-idle mode 200 |

`pollutantprocessmodelyear` carries all seven pollutant-processes (111 model
years each), and the refueling ones resolve a model year to a **different**
`shortModYrGroupID` than the energy ones do — 1980 is short group 80 for 9101
and 52 for 118 — so the flat `(pollutant-process x cohort)` rate relation
`docs/process-brakewear.md` §2.2 introduced is needed here for the same reason.

### 1.2 The nine tables this fixture adds

| table | rows | what it carries |
|---|---:|---|
| `refuelingfactors` | 4 | the whole coefficient set of both rates, per fuel type |
| `refuelingcontroltechnology` | 9,102 | onboard-vapour-recovery penetration and controlled rate, by (process 18, modelYear, regClass, sourceType, fuelType, age) |
| `sourcetypetechadjustment` | 111 | spillage control penetration, by (process 19, sourceType, modelYear) |
| `countyyear` | 1 | the two Stage II program reductions for the run county and year |
| `regioncounty` | 2 | county → fuel region, for the fuel-supply scope |
| `fuelsupply` | 5 | the run region's formulations and their market shares |
| `fuelformulation` | 2,158 | `fuelSubtypeID` and `RVP` (nullable) |
| `fuelsubtype` | 13 | `fuelTypeID` and `energyContent` (nullable) |
| `fueltype` | 4 | `fuelDensity` (nullable) |

`refuelingfactors`, in full, because every branch in §2.3 turns on one of its
columns:

| fuel | A | B | C | D | E | F | low/high T | tank limit | min loss | spill rate |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 gasoline | −1.2798 | −0.0049 | 0.0203 | 0.1315 | 0.418 | −16.6 | 45 / 90 | 20 | **1.8** | 0.31 |
| 2 diesel | 0 | 0 | 0 | 0 | 0 | 0 | **0 / 0** | 0 | **−1** | 0.31 |
| 5 E85 | −1.2798 | −0.0049 | 0.0203 | 0.1315 | 0.418 | −16.6 | 45 / 90 | 20 | **1.8** | 0.31 |
| 9 electricity | 0 | 0 | 0 | 0 | 0 | 0 | **0 / 0** | 0 | **−1** | **0** |

Two of those columns are sentinels rather than numbers, and both are read wrong
by the obvious port. A `(0, 0)` temperature-limit pair **disables** the 2008
California study relation rather than clamping to zero; a
`minimumRefuelingVaporLoss` of `−1` means *this fuel displaces no vapour* rather
than *floor the rate at −1*. Diesel's and electricity's raw displaced-vapour
rate is `exp(0) = 1`, so reading the sentinel as an ordinary floor gives them a
rate of 1 g/gallon out of nothing.

### 1.3 What is NOT an input

`baserate_1_2020` (250 rows), `baserate_2_2020` (1,664, all road type 1),
`baserate_90_2020` (empty), `baserateoutput` (586), `sourcebindistribution`
(375), `sho` (82) and `MOVESOutput` (336) are all generator or expected output.
None is a `data_sources` entry that anything reads. Values out of
`baserate_1_2020`, `sho` and `MOVESOutput` appear as `expected` in the fixture's
inline tests, which is the opposite direction.

`emissionratebyage`, `baseratebyage_*`, `ratesopmodedistribution`,
`opmodedistribution` and `runspecchainedto` are all **captured empty**.

---

## 2. The computation chain

### 2.1 Three roles, and the one that must not be given a rate

`runspecpollutantprocess` carries seven rows, in file order:

| polProcessID | pollutant | process | role |
|---|---|---|---|
| 118 | 1 THC | 18 displacement | **produced** by this calculator |
| 119 | 1 THC | 19 spillage | **produced** by this calculator |
| 8618 | 86 TOG | 18 displacement | produced *downstream*, by speciation chaining off 118 |
| 8619 | 86 TOG | 19 spillage | produced *downstream*, by speciation chaining off 119 |
| 9101 | 91 energy | 1 running | **consumed** |
| 9102 | 91 energy | 2 start | **consumed** |
| 9190 | 91 energy | 90 extended idle | **consumed** |

The consumed set is `refueling_loss_calculator.rs`'s own
`ENERGY_SOURCE_PROCESS_IDS`, the SQL's `mwo.pollutantID = 91 AND mwo.processID
IN (1, 2, 90, 91)`. The produced set is **not** "the RunSpec's selections on
processes 18 and 19": the Java `pollutantIDs` array is `{1}` and `subscribeToMe`
**intersects** the RunSpec's selections with it
(`refueling_loss_calculator.rs:2505-2521`, with the reason spelled out
verbatim). A port that keyed the refueling rate on the process alone would give
8618 and 8619 a rate as well and emit 336 spurious rows. In the `.esm` the
intersection is a **key column**, `rspp_refuelingProcessID`, which is the
process on a THC row and `0` — no process — everywhere else, so it is what both
rate lookups join on and no branch is needed.

### 2.2 The energy spine, and the two pollutant-processes that contribute nothing

The energy each refueling row chains off is `BaseRateCalculator`'s
`MOVESWorkerOutput` quantity for the cohort: S13–S17 of `docs/mixed-onroad.md`,
unchanged.

**In kilojoules.** The kJ-to-MillionBTU rebase is applied by the output
processor **after** the calculator chain has run
(`moves-framework/src/execution/engine.rs:1078-1086`,
`EnergyUnit::factor_from_kilojoules`), so the refueling calculator sees raw
kilojoules. Dividing the energy by 1,055,055.9 before the refueling product
would make every emitted row that factor too small — and it would still pass a
per-pollutant *ratio* check between the two blocks, which is why the fixture
computes `rspp_unitDivisor` for all seven pollutant-processes and asserts both
the 1 the emitted rows get and the 1,055,055.9 the energy rows get.

**Two of the three energy pollutant-processes contribute exactly zero**, and the
reason is not the rate table:

| | rows in `emissionrate` | cohorts matching a source bin | contribution |
|---|---:|---:|---|
| 9101 running | 57,040 | 125 | 3.3254 × 10⁸ kJ |
| 9102 start | 12,160 | **104** | **0** |
| 9190 extended idle | 488 | 0 | **0** |

*In the reference* the mechanism is a road-type join. `BaseRateGenerator` emits
each process's rates on its natural road type — running exhaust on the selected
on-road types, start exhaust off-network at `roadTypeID` 1
(`generators/start_operating_mode_distribution.rs`), extended idle and auxiliary
power on `roadTypeID` 1 **and** source type 62 only
(`generators/rates_op_mode_distribution.rs:121`, `:700-735`) — and
`BaseRateCalculator` then joins its rate tables to `runSpecRoadType`, which for
this run is `{4}` (`baseratecalculator/mod.rs:762-781`). Every process-2 row is
discarded there; `baserate_2_2020`'s 1,664 rows are all road type 1 and
`baserate_90_2020` is empty because source type 62 is not in the run at all.

*In the port* the mechanism is one step later and is a contraction. Start rates
are on operating modes 101–108 and extended-idle rates on mode 200; `dc_W` is
the drive-cycle classification's distribution over the **23 running modes** of an
on-network road type and never produces either; so `Σ_om W[k, om] × rate[b, om]`
has no partner and is exactly 0.

**The two agree here, and only because no off-network road type is selected.**
That is a condition, not a coincidence, so the fixture measures it:
`run_offNetworkRoadTypeCount` is 0 beside `run_selectedRoadTypeCount` of 1, and
`pp_energyTotal` is the pair of exact zeros. On a RunSpec that selected road type
1 the reference would emit start rows and the port would not, and those two
assertions are what would fail.

The consequence for the `.esm`'s shape: because processes 2 and 90 contribute
nothing, the refueling row can **sum the chained energy over the run's energy
pollutant-processes** rather than carrying each energy row's own `roadTypeID`
into the output key. The reference emits one refueling row per energy row and
lets the output group-by add them; summing first is the same number because
neither refueling rate depends on the energy process, and the road types cannot
differ because only one process survives.

### 2.3 REFEC-1 and REFEC-2 — the displaced-vapour rate

Per fuel type, at the run's `(month, hour)` temperature of **59.5 °F**
(`zonemonthhour`):

```
refuelingTemperature  = (lowLimit != 0 and highLimit != 0)
                        ? 20.30 + 0.81 * clamp(t, lowLimit, highLimit)
                        : t
tankTemperatureDif    = clamp(E * refuelingTemperature + F, 0, tankTDiffLimit)
averageRVP            = sum(RVP * marketShare) over the fuel supply, by (month, fuelType)
displacedVaporRate    = exp(A + B*dif + C*refuelingTemperature + D*averageRVP)
                        floored at minimumRefuelingVaporLoss, or 0 if that is <= -1
```

Worked, for gasoline:

```
refuelingTemperature = 20.30 + 0.81 x 59.5        = 68.495
tankTemperatureDif   = 0.418 x 68.495 - 16.6      = 12.03091   (inside [0, 20])
averageRVP           = 8.0 x 1.0                  = 8.0
exponent = -1.2798 - 0.0049 x 12.03091 + 0.0203 x 68.495 + 0.1315 x 8.0
         = -1.2798 - 0.05895146 + 1.39044850 + 1.052   = 1.10369704
displacedVaporRate   = exp(1.10369704)            = 3.0152931
```

and for E85 the same arithmetic with `averageRVP` 7.7 gives **2.8986556**. For
diesel and electricity both temperature limits are 0, so the California relation
is disabled and the ambient 59.5 is used unchanged; every vapour term is 0, the
raw rate is `exp(0) = 1`, and the `−1` sentinel floors it to **0**.

`averageRVP` is a market-share-weighted sum over four joined relations —
`fuelsupply → fuelformulation → fuelsubtype`, fanned across the months of each
supply row's `monthGroupID` — and two of the five supply rows are inner-join
misses that have to stay misses:

* formulation **28001** has `fuelSubtypeID` 30 and `fuelsubtype` has no such row,
  so it contributes to no fuel type at all;
* formulation **90** is present but its subtype's `energyContent` is NULL.

A NULL arrives from the parquet reader as **NaN**
(`docs/esm-conventions.md` §11), and `0 × NaN` is NaN — so a presence
*indicator* multiplied into the sum does not remove it and would poison every
other fuel's `energyContent`. `lib/refueling.esm`'s `positive_else_zero` is the
SQL's own `WHERE energyContent > 0` written as a **value**: `ifelse` selects its
branch before evaluating it, which is what makes it the fix.

### 2.4 REFEC-3..6 — the two adjusted rates

```
adjustedVaporRate = displacedVaporRate x (1-P) x (1-T)
                  + controlledRefuelingRate x (1-P) x T          (REFEC-3, 4)
adjustedSpillRate = (1-Pspill) x ((1-Tspill) x refuelingSpillRate) (REFEC-5, 6)
```

`P` and `Pspill` are `countyyear`'s two Stage II program reductions and are
**both exactly 0** here — see §7.2. `T` and `Tspill` are not:

| model year | `T` (rct, fuels 1 and 5) | `Tspill` (stta) | vapour rate | spill rate |
|---|---:|---:|---:|---:|
| 1980–1995 | 0 | 0 | 3.0152931 | 0.31 |
| 1996–1997 | 0 | 0.5 | 3.0152931 | 0.155 |
| 1998 | 0.348 | 0.5 | **1.9785339** | 0.155 |
| 1999 | 0.696 | 0.5 | 0.9410847 | 0.155 |
| 2000–2019 | 0.87 … 0.993 | 0.5 | 0.4275 … 0.0572 | 0.155 |
| 2020 | **1.0** | 0.5 | **0.0361** | 0.155 |

so the convex blend is exercised at both endpoints and everywhere between, and
`controlledRefuelingRate` (0.0361 g/gallon wherever `T` is non-zero) is the
whole of the 2020 rate. `3.0152931 × 0.652 + 0.0361 × 0.348 = 1.9785339` at 1998
is the assertion that separates a blend from a two-case lookup.

**The spillage county-year fan-out is SQL that is model logic.** The spillage
section `ALTER`s a `fuelTypeID` column onto `RefuelingCountyYear` (existing rows
default to gasoline), duplicates the gasoline row as E85 — most Stage II
programs cover E85 too, so it keeps the reduction — and `INSERT`s
zero-adjustment rows for fuel types 2, 3 and 9
(`refueling_loss_calculator.rs:214-222`,
`SPILLAGE_COUNTY_YEAR_FUEL_TYPES = [(1,true),(5,true),(2,false),(3,false),(9,false)]`).
That is a five-row relation, so the `.esm` ports it as one — `spcy_fuelTypeID`
built from `enums` and `spcy_retainsProgramAdjust` as its data column — rather
than as a branch (`docs/esm-conventions.md` §24: equations that arrive as data
get ported as code, and the coefficients stay data). Fuel type 3 is in the
fan-out and not in `refuelingfactors`, so the INNER JOIN between them is what
keeps CNG out of the spillage block; the fixture computes both existence flags
rather than relying on either alone.

### 2.5 REFEC-7 and REFEC-8 — energy to gallons to grams

```
RefuelingFuelType(fuelType, month) = ( sum(marketShare x subtype energyContent),
                                       fueltype.fuelDensity )
                                     WHERE energyContent > 0 AND fuelDensity > 0
emissionQuant = rate x energy / (energyContent x fuelDensity)
```

| fuel | energyContent (kJ/g) | fuelDensity (g/gallon) | divisor (kJ/gallon) |
|---|---:|---:|---:|
| 1 gasoline | 41.696 | 2829 | **117,957.984** |
| 2 diesel | 42.7 | 3203 | **136,768.1** |
| 5 E85 | 29.12 | 2944 | **85,729.28** |
| 9 electricity | — | — | (no row) |

The divisor guard is REFEC-7's inner join and not a defensive zero check:
electricity's divisor would be `0`, and `0.0 × energy / 0` is a **NaN** that no
key-set check would catch. `lib/refueling.esm`'s `refueling_emission_quantity`
carries the join as its fourth parameter for that reason.

---

## 3. Join structure

### 3.1 The joins this fixture adds

`docs/mixed-onroad.md` §3's J1–J34 all survive, minus the PM10 chain
`process-brakewear` added. Twelve are new.

| id | left | right | key pairs |
|---|---|---|---|
| **R1** | `fsp_fuelRegionID`, `fsp_fuelYearID`, `run_countyID`, `run_fuelYearID` | `rgc_*` | 4, a SEMI-JOIN — see §3.2 |
| **R2** | `fsp_monthGroupID`, `run_monthID` | `moy_*` | 2, a semi-join: does the supply row's month group contain the run's month |
| **R3** | `fsp_fuelFormulationID` | `ffm_fuelFormulationID` | 1, twice (subtype and RVP) |
| **R4** | `fsp_fuelSubtypeID` | `fst_fuelSubtypeID` | 1, twice (fuel type and energy content) |
| **R5** | `rff_fuelTypeID` | `fsp_fuelTypeID` | 1 — the market-share sum, REFEC-2 |
| **R6** | `rff_fuelTypeID` | `ftp_fuelTypeID` | 1 — the fuel density |
| **R7** | `run_countyID`, `run_yearID` | `cty_*` | 2 — the Stage II reductions |
| **R8** | `run_offNetworkRoadTypeID` | `rsr_roadTypeID` | 1 — a constant equality spelled as a join against a one-row relation (`docs/esm-conventions.md` §20.4) |
| **R9** | `rt_fuelTypeID` | `rff_fuelTypeID` | 1 — the fuel's rates and divisor at the rate row |
| **R10** | `rt_fuelTypeID` | `spcy_fuelTypeID` | 1 — the spillage county-year fan-out |
| **R11** | `rt_refuelingProcessID`, `rt_modelYearID`, `rt_fuelTypeID`, `rt_ageID`, `run_sourceTypeID` | `rct_*` | **5**, and `regClassID` deliberately absent — §3.2 |
| **R12** | `rt_refuelingProcessID`, `rt_modelYearID`, `run_sourceTypeID` | `stta_*` | 3 |
| **R13** | `rt_cohortOrdinal` | `rt_cohortOrdinal` | 1, `syms: [b, b2]` — the energy self-join, REFEC-7 |

### 3.2 Two joins that are not what they look like

**The fuel-supply scope is a SEMI-JOIN because `regioncounty` has two rows.**
County 26161 maps to fuel region 270000000 twice, once per `regionCodeID`.
Reading the region as a *value* — `Σ regionID` over the matching rows — gives
540000000 and matches nothing; the shape that works is §3's presence test,
`bool_and_or` with a numeric body, and it is the third instance in this
repository of a lookup whose right-hand side is not unique.

**The displacement join drops `regClassID`, and the reference is why.** The SQL
matches `rd.regClassID = mwo.regClassID`, but `BaseRate`'s `MOVESWorkerOutput`
**collapses `regClassID` to 0** — faithfully matching canonical's
`baseRateOutput`, which is `regClassID = 0` when the RunSpec does not break
emissions down by reg class — while `RefuelingControlTechnology` carries
concrete per-class rows. `moves.rs` reconciles that by keying the working table
without `regClassID` and treating a collapsed 0 as a **wildcard**
(`refueling_loss_calculator.rs:1973-1993, 2363-2371`), which makes the rate the
**sum** over whatever reg classes match. The `.esm` spells it as exactly that
sum and then measures the count: `rt_displacementRowCount` is 1 on every
displacement rate row, because this snapshot's table carries `regClassID` 20
alone. On a snapshot with two reg classes it would be 2 and the output row would
be their sum, which is what the reference does — so the count is the claim, not
the assumption.

### 3.3 One rank, because the blocks are different sizes

`docs/esm-conventions.md` §22's three layers, with the middle one carrying three
independent tests rather than one:

1. **A rectangular grid, carried flat.** `rate_rows` is the seven
   pollutant-processes crossed with the 41 × 4 cohort candidate grid — 1,148 rows,
   every factor a discovered extent, all key columns one-dimensional.
2. **A membership column that is three inner joins.** `rt_refuelIsSelected` is
   *the cohort survives `stmyFraction > 0`* **and** *the refueling working table
   has a row* **and** *REFEC-7 finds a fuel divisor*. None of the three is a
   decision about the output; each is a join that the reference also makes.
3. **A rank over the WHOLE rate relation.** `process-brakewear` could decompose
   an output row number into (block, day, cohort-rank) because its three blocks
   were 125 cohorts each. Here they are 64 and 104, so there is no block length
   to divide by: `rt_refuelRank` is an inclusive prefix count over all 1,148
   candidates, zeroed on non-members, giving a dense 1..168, and the output
   relation is `168 × 2` with the pollutant-process read *back* through the rank
   join like every other key.

`n_outputRefuelRow` = 168 is the one declared number, and `run_refuelRowCount`
recomputes it while `pp_refuelRowCount` recomputes the 64 and the 104 separately.

---

## 4. Reusable shapes

One new template library, `lib/refueling.esm`, eight templates. Every
coefficient stays in its table; the library carries only forms
(`docs/esm-conventions.md` §24).

| template | what it is |
|---|---|
| `positive_else_zero` | the SQL's `WHERE x > 0` as a VALUE — the NaN guard §2.3 explains |
| `refueling_temperature` | REFEC-1's California relation with its clamp and its disabling arm |
| `tank_temperature_dif` | REFEC-1's `[0, limit]` clamp, in the reference's own branch order |
| `displaced_vapor_rate` | REFEC-2's four-term exponential |
| `floored_vapor_rate` | REFEC-2's floor, with the `<= -1` sentinel |
| `adjusted_vapor_rate` | REFEC-3/4's convex blend |
| `adjusted_spill_rate` | REFEC-5/6 |
| `refueling_emission_quantity` | REFEC-8's product, with REFEC-7's inner join as its guard |

Everything else is imported unchanged: `pol_process_id`, `pollutant_id_of`,
`process_id_of`, `null_output_column` from `lib/identifiers.esm`;
`weeks_per_month`, `share_of_group`, `onroad_scc`, `source_bin_slot`,
`ev_energy_divisor`, `kilojoules_per_million_btu` from `lib/onroad_activity.esm`;
all four drive-cycle shapes from `lib/drive_cycle.esm`; `exact_else_wildcard`
from `lib/adjustments.esm`.

`components/refueling_loss_rate.esm` instantiates seven of the eight on five
probe coefficient sets and three control cases, at values this fixture's own
inputs never reach — §7.2.

---

## 5. Literals and enums

`docs/mixed-onroad.md` §5 carries the fixture's enums. Four groups change:

```
pollutant:  TotalGaseousHydrocarbons 1, TotalEnergyConsumption 91,
            PetroleumEnergyConsumption 92, FossilFuelEnergyConsumption 93
process:    RunningExhaust 1, StartExhaust 2,
            RefuelingDisplacementVaporLoss 18, RefuelingSpillageLoss 19,
            ExtendedIdleExhaust 90, AuxiliaryPowerExhaust 91
fuel_type:  Gasoline 1, Diesel 2, CompressedNaturalGas 3, EthanolE85 5, Electricity 9
road_type:  OffNetwork 1
```

Processes 2, 90 and 91 are named because `rspp_isEnergySource` tests membership
of exactly that set and 91 is not in this run — writing the rule out is the
point. The four fuel types are named because the spillage county-year fan-out is
a five-row relation whose key column is built from them, CNG included, and CNG
is not in this run either. Pollutant 86 (Total Organic Gases) is **not** an enum
member and is never written down: it is unpacked from
`runspecpollutantprocess`'s `polProcessID` by `pollutant_id_of`, and the whole
point of §2.1's key column is that the document never has to name it.

---

## 6. Hand-checkable worked examples

### 6.0 Run-level values used by every example

| | |
|---|---|
| temperature, heat index | 59.5 °F |
| A/C activity raw / clamped | −0.2969815 / **0** |
| EV temperature raw / factor | **+0.015625** / **1.015625** (energy × electricity only) |
| Stage II reductions `P`, `Pspill` | **0**, **0** |
| refueling temperature (fuels 1 and 5) | **68.495 °F** |
| tank temperature difference | **12.03091 °F** |
| displaced vapour rate | **3.0152931** (gasoline), **2.8986556** (E85), **0** (diesel, electricity) |
| fuel-volume divisor | 117,957.984 / 136,768.1 / 85,729.28 kJ per gallon |
| `noOfRealDays` | 2 (weekend), 5 (weekday) |

### 6.1 Worked example A — MY 1980, gasoline, weekday, displacement

The uncontrolled end of the blend, and the largest cell in the fixture.

```
rtDay_meanBaseRate[9101, MY1980/fuel1, day 5] = 333651 kJ / source-hour  (baserate_1_2020)
sho[hourDayID 75, ageID 40]      = 23.191807109
activity  = 23.191807109 / 5     = 4.6383614218   source-hours
energy    = 333651 x 4.6383614218 = 1,547,592.933  kJ
T(1980)   = 0  ->  adjustedVaporRate = 3.0152931 x 1 x 1 + 0.0361 x 1 x 0 = 3.0152931
emissionQuant = 3.0152931 x 1547592.933 / 117957.984 = 39.5602412 g
```

MOVESOutput stores **39.560300**.

### 6.2 Worked example B — the same row, spillage

```
Tspill(1980) = 0  ->  adjustedSpillRate = 1 x (1 x 0.31) = 0.31
emissionQuant = 0.31 x 1547592.933 / 117957.984 = 4.0671584 g
```

MOVESOutput stores **4.067160**, and 4.067160 / 39.560300 = 0.10281, which is
0.31 / 3.0152931 — so the two blocks check each other's energy as well as the
reference.

### 6.3 Worked example C — MY 1998, gasoline, weekday, displacement

The only worked example where the control blend is neither endpoint.

```
T(1998)   = 0.348
adjustedVaporRate = 3.0152931 x 0.652 + 0.0361 x 0.348 = 1.9785339
energy    = 2,279,798.270 kJ
emissionQuant = 1.9785339 x 2279798.270 / 117957.984 = 38.2395326 g
```

MOVESOutput stores **38.239600**. Take the uncontrolled rate instead and it is
58.27 g — 52 % high; take the controlled rate and it is 0.698 g.

### 6.4 Worked example D — MY 2020, E85, weekend, displacement

The second fuel's own vapour rate and divisor, at the fully controlled end.

```
T(2020)   = 1.0  ->  adjustedVaporRate = 2.8986556 x 0 + 0.0361 x 1 = 0.0361
energy    = 947.8283340 kJ
emissionQuant = 0.0361 x 947.828334 / 85729.28 = 3.99123880e-04 g
```

MOVESOutput stores **0.000399124**. Use gasoline's divisor and it is
2.9006e-04 — 27 % low.

### 6.5 The reproduction script

Extracted and run by `./run-refueling-oracle.sh`. It reads only the input tables
of §1, computes the whole chain — the activity half, the cohort structure, `W`,
the energy spine, REFEC-1 through REFEC-8 — and **asserts** its worst relative
error against `sho` and against `MOVESOutput`, the exactness of the key set, and
the two things §7.2 says the fixture cannot see.

```python
#!/usr/bin/env python3
"""process-refueling reproduction from the snapshot's own input tables."""
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
KJ=1055.0559e6/1000.0
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
def slot(b,scale): return (b//scale)%100
ER=T("emissionrate")
def rates(pp):
    d={}
    for r in ER:
        if r["polProcessID"]!=pp: continue
        b=r["sourceBinID"]
        d[(slot(b,10**16),slot(b,10**14),slot(b,10**12),slot(b,10**10),r["opModeID"])]=float(r["meanBaseRate"])
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
agegroup={r["ageID"]:r["ageGroupID"] for r in T("agecategory")}
EVE=T("evefficiency")
def eveff(pp):
    return {r["ageGroupID"]:float(r["batteryEfficiency"])*float(r["chargingEfficiency"])
            for r in EVE if r["polProcessID"]==pp and r["sourceTypeID"]==ST}
realdays={r["dayID"]:float(r["noOfRealDays"]) for r in T("dayofanyweek")}
ZMH = [r for r in T("zonemonthhour")
       if r["monthID"] == MONTH and r["zoneID"] == ZONE and r["hourID"] == HOUR][0]
TEMP, HEAT = float(ZMH["temperature"]), float(ZMH["heatIndex"])
TA = T("temperatureadjustment")
def temp_terms(pp, fuel, regclass, my):
    for rc in (regclass, 0):
        for r in TA:
            if (r["polProcessID"] == pp and r["fuelTypeID"] == fuel
                    and r["regClassID"] == rc
                    and r["minModelYearID"] <= my <= r["maxModelYearID"]):
                return float(r["tempAdjustTermA"]), float(r["tempAdjustTermB"])
    return 0.0, 0.0
def ev_temp_factor(pp, pol, proc, fuel, regclass, my):
    if not (proc == 1 and fuel == ELECTRICITY and pol == 91):
        return 1.0
    a, b = temp_terms(pp, fuel, regclass, my)
    adj = (TEMP - 72.0) * (a + b * (TEMP - 72.0))
    if adj < 0.0: adj = 0.0
    if ST < 40 and HEAT > 67.0: adj = 0.0
    return 1.0 + adj
# ---- S15: the Total Energy Consumption spine, in KILOJOULES -----------------
ENERGY_PROCESSES={1,2,90,91}
OFFNET_ROAD=1
OFFNET_PROCESSES={2,90,91}
RUNSPEC_ROADS={r["roadTypeID"] for r in T("runspecroadtype")}
PPA={r["polProcessID"]:(r["pollutantID"],r["processID"]) for r in T("pollutantprocessassoc")}
energy={}
dropped_energy_processes=set()
for pp in POLPROCS:
    pol,proc=PPA[pp]
    if pol!=91 or proc not in ENERGY_PROCESSES: continue
    road=OFFNET_ROAD if proc in OFFNET_PROCESSES else ROAD
    if road not in RUNSPEC_ROADS:
        dropped_energy_processes.add(proc); continue
    coh=cohorts(pp); sbaf=rebase(coh); rate=rates(pp)
    sbw=collections.defaultdict(float)
    for (my,fuel,et,rc),frac in sbaf.items():
        smy=shortgroup[mygroup[(pp,my)]]
        ev=evsf(pp,my,fuel,rc)
        for om in {k[4] for k in rate}:
            r=rate.get((fuel,et,rc,smy,om))
            if r is not None: sbw[(my,fuel,om)]+=frac*r*ev
    br=collections.defaultdict(float)
    for (my,fuel,om),v in sbw.items():
        for d in DAYS: br[(HD[d],my,fuel)]+=v*W[(HD[d],om)]
    ee=eveff(pp)
    for (my,fuel,et,rc),frac in coh.items():
        for d in DAYS:
            r=br[(HD[d],my,fuel)]*ev_temp_factor(pp,pol,proc,fuel,rc,my)
            if fuel==ELECTRICITY and ee: r/=ee[agegroup[YEAR-my]]
            act=sho[(HD[d],YEAR-my)]/realdays[d]
            assert (proc,d,my,fuel) not in energy
            energy[(proc,d,my,fuel)]=r*act
# ---- REFEC-2: RefuelingAverageRVP ------------------------------------------
REGIONS={r["regionID"] for r in T("regioncounty") if r["countyID"]==COUNTY and r["fuelYearID"]==FUELYEAR}
SUPPLY=[r for r in T("fuelsupply") if r["fuelRegionID"] in REGIONS and r["fuelYearID"]==FUELYEAR]
FORM={r["fuelFormulationID"]:r for r in T("fuelformulation")}
SUBTYPE={r["fuelSubtypeID"]:r for r in T("fuelsubtype")}
MONTHS_OF_GROUP=collections.defaultdict(list)
for r in T("monthofanyyear"): MONTHS_OF_GROUP[r["monthGroupID"]].append(r["monthID"])
RF={r["fuelTypeID"]:r for r in T("refuelingfactors")}
avgrvp=collections.defaultdict(float)
for fs in SUPPLY:
    ff=FORM.get(fs["fuelFormulationID"])
    if ff is None: continue
    st=SUBTYPE.get(ff["fuelSubtypeID"])
    if st is None: continue
    rvp=0.0 if ff["RVP"] is None else float(ff["RVP"])
    for m in MONTHS_OF_GROUP[fs["monthGroupID"]]:
        avgrvp[(m,st["fuelTypeID"])]+=rvp*float(fs["marketShare"])
for m in {r["monthID"] for r in T("monthofanyyear")}:
    for f in RF: avgrvp.setdefault((m,f),0.0)
# ---- REFEC-1, 2: RefuelingTemp ---------------------------------------------
def f_(r,c): return 0.0 if r[c] is None else float(r[c])
disp_rate={}
for f,r in RF.items():
    lo,hi=f_(r,"vaporLowTLimit"),f_(r,"vaporHighTLimit")
    rtemp=20.30+0.81*min(max(lo,TEMP),hi) if (lo!=0.0 and hi!=0.0) else TEMP
    raw=f_(r,"vaporTermE")*rtemp+f_(r,"vaporTermF"); lim=f_(r,"tankTDiffLimit")
    dif=lim if raw>=lim else (0.0 if raw<=0.0 else raw)
    import math
    v=math.exp(f_(r,"vaporTermA")+f_(r,"vaporTermB")*dif
               +f_(r,"vaporTermC")*rtemp+f_(r,"vaporTermD")*avgrvp[(MONTH,f)])
    mn=f_(r,"minimumRefuelingVaporLoss")
    disp_rate[f]=0.0 if mn<=-1.0 else (mn if v<mn else v)
# ---- REFEC-3..6: the two adjusted-rate tables ------------------------------
CY=[r for r in T("countyyear") if r["countyID"]==COUNTY and r["yearID"]==YEAR]
assert len(CY)==1
P_VAPOR=float(CY[0]["refuelingVaporProgramAdjust"]); P_SPILL=float(CY[0]["refuelingSpillProgramAdjust"])
DISPLACEMENT_PROCESS, SPILLAGE_PROCESS = 18, 19
displacement={}
for r in T("refuelingcontroltechnology"):
    if r["processID"]!=DISPLACEMENT_PROCESS or r["fuelTypeID"] not in disp_rate: continue
    Tadj=float(r["refuelingTechAdjustment"]); ctrl=float(r["controlledRefuelingRate"])
    key=(r["modelYearID"],r["sourceTypeID"],r["fuelTypeID"],r["ageID"],MONTH,HOUR)
    displacement.setdefault(key,[]).append(
        (r["regClassID"], disp_rate[r["fuelTypeID"]]*(1.0-P_VAPOR)*(1.0-Tadj)+ctrl*(1.0-P_VAPOR)*Tadj))
SPILL_FUELS=[(1,True),(5,True),(2,False),(3,False),(9,False)]
spillage={}
for fuel,keeps in SPILL_FUELS:
    if fuel not in RF: continue
    rate=f_(RF[fuel],"refuelingSpillRate"); pr=P_SPILL if keeps else 0.0
    for r in T("sourcetypetechadjustment"):
        if r["processID"]!=SPILLAGE_PROCESS: continue
        spillage[(fuel,r["sourceTypeID"],r["modelYearID"])]=(
            (1.0-pr)*((1.0-float(r["refuelingTechAdjustment"]))*rate))
# ---- the RefuelingFuelType computed extract --------------------------------
DENSITY={r["fuelTypeID"]:float(r["fuelDensity"]) for r in T("fueltype")
         if r["fuelDensity"] is not None and float(r["fuelDensity"])>0.0}
econtent=collections.defaultdict(float)
for fs in SUPPLY:
    ff=FORM.get(fs["fuelFormulationID"])
    if ff is None: continue
    st=SUBTYPE.get(ff["fuelSubtypeID"])
    if st is None or st["energyContent"] is None or float(st["energyContent"])<=0.0: continue
    for m in MONTHS_OF_GROUP[fs["monthGroupID"]]:
        econtent[(st["fuelTypeID"],m)]+=float(fs["marketShare"])*float(st["energyContent"])
divisor={k:v*DENSITY[k[0]] for k,v in econtent.items() if v>0.0 and k[0] in DENSITY}
# ---- REFEC-7, 8: one output row per (energy row x rate) --------------------
def scc(fuel,proc): return "%d"%(22*10**8+fuel*10**6+ST*10**4+ROAD*10**2+proc)
THC=1
rows={}
for (proc,d,my,fuel),kj in energy.items():
    div=divisor.get((fuel,MONTH))
    if div is None: continue
    for r in displacement.get((my,ST,fuel,YEAR-my,MONTH,HOUR),[]):
        k=(THC,DISPLACEMENT_PROCESS,d,my,fuel)
        rows[k]=(rows.get(k,(0.0,None))[0]+r[1]*kj/div, scc(fuel,DISPLACEMENT_PROCESS))
    s=spillage.get((fuel,ST,my))
    if s is not None:
        k=(THC,SPILLAGE_PROCESS,d,my,fuel)
        rows[k]=(rows.get(k,(0.0,None))[0]+s*kj/div, scc(fuel,SPILLAGE_PROCESS))
# ------------------------------------------------------------------- compare
ref_sho = {(r["hourDayID"], r["ageID"]): float(r["SHO"]) for r in T("sho")}
worst_sho = max(abs(sho[k] - v) / v for k, v in ref_sho.items())
print("sho:           %3d rows, worst relative error %.3e" % (len(ref_sho), worst_sho))
assert worst_sho < 1e-5, "sho: worst relative error %.3e exceeds 1e-5" % worst_sho

out = pq.read_table(SNAP + "/tables/db__out_process_refueling__movesoutput.parquet").to_pylist()
worst, worst_key = 0.0, None
for o in out:
    key = (o["pollutantID"], o["processID"], o["dayID"], o["modelYearID"], o["fuelTypeID"])
    q, s = rows[key]
    assert s == o["SCC"], (key, s, o["SCC"])
    rel = abs(q - float(o["emissionQuant"])) / float(o["emissionQuant"])
    if rel > worst:
        worst, worst_key = rel, key
print("emissionQuant: %3d rows, worst relative error %.3e at "
      "(pollutant %d, process %d, day %d, MY %d, fuel %d)" % (len(out), worst, *worst_key))
# ASSERTED, not merely printed (docs/esm-conventions.md 21): ./run-tests.sh reads
# this script's EXIT CODE, so a regression that leaves the key set intact and
# moves every value would otherwise be reported green with the evidence in a log.
assert len(rows) == len(out), (len(rows), len(out))
assert set(rows) == {(o["pollutantID"], o["processID"], o["dayID"], o["modelYearID"],
                      o["fuelTypeID"]) for o in out}
assert worst < 2e-5, "emissionQuant: worst relative error %.3e exceeds 2e-5" % worst
disp = sum(1 for k in rows if k[1] == DISPLACEMENT_PROCESS)
spill = sum(1 for k in rows if k[1] == SPILLAGE_PROCESS)
print("key set:       %3d displacement + %3d spillage = %d rows, exact"
      % (disp, spill, len(rows)))
print("               the two blocks are DIFFERENT sizes: refuelingcontroltechnology carries "
      "fuel types %s only" % sorted({r["fuelTypeID"] for r in T("refuelingcontroltechnology")}))

# --- the two things a row count cannot see (docs/esm-conventions.md 23) -----
# The energy spine: assert BOTH that the surviving process produced non-zero
# kilojoules and that the discarded ones contribute exactly nothing. Without the
# first the second is vacuous -- a chain computing nothing would also
# "contribute nothing" and would look identical in this log.
total = {p: sum(v for k, v in energy.items() if k[0] == p) for p in {k[0] for k in energy}}
print("energy spine:  %d kJ from process 1, %s discarded on the road-type join, "
      "off-network road types selected: %d"
      % (round(sum(total.values())), sorted(dropped_energy_processes),
         len([r for r in T("runspecroadtype") if r["roadTypeID"] == OFFNET_ROAD])))
assert total[1] > 0.0 and set(total) == {1}
assert dropped_energy_processes, "no energy process was discarded: the road-type gate is untested"
assert not [r for r in T("runspecroadtype") if r["roadTypeID"] == OFFNET_ROAD]
# The two Stage II program reductions are exactly zero in this county and year,
# so nothing here can tell a correct (1 - P) from an omitted one. Said out loud
# rather than left for a reader to discover from a passing comparison.
assert P_VAPOR == 0.0 and P_SPILL == 0.0
print("NOTE:          both Stage II program reductions are 0.0, so this fixture cannot "
      "distinguish (1 - P) from 1; components/refueling_loss_rate.esm carries them at 0.2 and 0.3")
```

Result:

```
sho:            82 rows, worst relative error 3.610e-06
emissionQuant: 336 rows, worst relative error 7.434e-06 at (pollutant 1, process 19, day 2, MY 2002, fuel 2)
key set:       128 displacement + 208 spillage = 336 rows, exact
               the two blocks are DIFFERENT sizes: refuelingcontroltechnology carries fuel types [1, 5] only
energy spine:  332539532 kJ from process 1, [2, 90] discarded on the road-type join, off-network road types selected: 0
NOTE:          both Stage II program reductions are 0.0, so this fixture cannot distinguish (1 - P) from 1; components/refueling_loss_rate.esm carries them at 0.2 and 0.3
```

The script models §2.2's zero the **reference's** way — a road-type gate on the
energy process — while `fixtures/process-refueling.esm` models it the port's way,
as an operating-mode contraction that finds no partner. Two independent routes
to the same pair of zeros is the point; §2.2 says what would make them disagree.

### 6.6 What the fixture's inline tests check

Twelve tests, 220 assertions. Six are about things no earlier fixture could
check:

| test | what fails if it is wrong |
|---|---|
| the seven pollutant-processes and the two roles they play | §2.1's intersection with THC, the energy-source set, the unit divisor |
| the energy spine is running exhaust alone and reproduces the generator table | §2.2, in both directions: `baserate_1_2020` on 9101 and exact zeros on 9102 and 9190 |
| the short model-year group is a property of the pollutant-process | the flat rate relation's reason for existing, at three model years |
| the fuel supply sets the average RVP, the divisor and the displaced vapour rate | §2.3 end to end, including both inner-join misses and the `−1` sentinel |
| the two refueling rates are disjoint and the Stage II reductions are inert | §2.4 at both blend endpoints and the 1998 blend, the three zeros of §0.2, and the 64 / 104 / 168 counts |
| the worked examples reach MOVESOutput in both blocks | §6.1–§6.4 with their SCCs |

plus the run scope, the drive-cycle scaffolding, `W`'s two structural
properties, the activity chain against `sho`, the cohort row set, and the EV
temperature arm.

---

## 7. Fidelity notes and tolerance

### 7.1 The measured result

| | |
|---|---|
| rows | **336 of 336**, key set exact |
| worst cell | **7.434 × 10⁻⁶** relative, at (pollutant 1, process 19, day 2, MY 2002, fuel 2) |
| worst per-pollutant sum | 2.769 × 10⁻⁷ |
| gate | `tolerance.toml` `[cell] rel = 2e-5`, unchanged, and `[default] onroad = 1e-3` |
| `[shortfall]` | none |

The residual is the reference's own six-significant-figure column storage, the
same as every other fixture here. The independent Python reproduction of §6.5
reports the same worst cell **to the digit, at the same key**, by a different
route.

### 7.2 What this fixture cannot see, measured

`docs/esm-conventions.md` §23. Two of `RefuelingLossCalculator`'s stages are
multiplied by a value that makes them unobservable here, and both are checked in
`components/refueling_loss_rate.esm` instead, on probe rows whose two branches
differ:

| stage | why it is inert | where it is checked |
|---|---|---|
| the Stage II vapour reduction `(1 − P)` | `countyyear.refuelingVaporProgramAdjust` = 0 | probe at `P` = 0.2 |
| the Stage II spillage reduction `(1 − Pspill)` and the fuel-type fan-out it rides | `countyyear.refuelingSpillProgramAdjust` = 0, so both arms of `retainsProgramAdjust` give 0 | probe at `Pspill` = 0.3 |

**And the whole ELECTRICITY branch of the energy spine is invisible here**,
which is the one entry on this list that no earlier fixture would have predicted.
`mixed-onroad` and `process-brakewear` both emit electricity rows, so for them
the EV temperature factor and the EV efficiency divisor move real output cells —
`docs/process-brakewear.md` §2.5 measures the missing wildcard step as a 1.56 %
error on 84 of that fixture's rows. This fixture emits **no** electricity row at
all: a refueling row sums
the energy of its own `(modelYearID, fuelTypeID)` cohort, and every electricity
cohort is dropped by REFEC-7's fuel-type join, so fuel-9 energy never reaches an
emitted cell at all. Perturbing either the EV temperature terms or
`evefficiency` moves no row of this fixture's 336. The fixture asserts both at
the rate-relation column — where they are still computed and still worth pinning
— and says so in the test's own description; the checks that BITE are
`components/onroad_energy_output.esm`'s and `fixtures/process-brakewear.esm`'s.
The same is true of the A/C increment, for a different reason: its factor is
exactly 0 at this heat index, as it is at `mixed-onroad`'s.

Measured, §23's way — perturb one input of the stage and compare **every**
emitted cell byte for byte against the unperturbed run:

| perturbation | rows that move, of 336 |
|---|---:|
| `rt_evTemperatureAdjustRaw` := 1.0 (the EV arm's own value) | **0** |
| `rt_batteryEfficiency` := 0.5 (the EV divisor's own input) | **0** |
| `rtMode_acIncrement` := 1.0 (the A/C increment) | **0** |
| `rt_refuelingSpillRate` := 2.0 — *positive control* | 208 |
| `rt_evTemperatureFactor` := 2.0 — *positive control*, and it is one because this variable is the WHOLE temperature factor, not the EV arm | 336 |

The two controls are what make the three zeros mean something: the harness does
see a change when there is one, and the second control is the trap — perturbing
the *factor* rather than the EV arm's own input moves everything, because the
same variable carries the standard quadratic's 1 for the other three fuels.

Three more are inert for a *structural* reason rather than a zero weight, and
they are checked in the same component:

* **both arms of the refueling-temperature clamp.** 59.5 °F is inside
  gasoline's `[45, 90]` window, so neither bound is reached; the component
  probes 95 °F and 20 °F.
* **both arms of the tank-temperature-difference clamp.** 12.03091 is inside
  `[0, 20]`; the component probes a raw 22.3576 and a raw −4.06.
* **the vapour floor that BINDS.** Gasoline's 3.0152931 is above its 1.8 floor
  and diesel's sentinel takes the other branch, so the `rate < minimum` arm is
  never taken here; the component probes a raw 1.0 against a floor of 1.8.

What the fixture *can* see, and what a component could not: the control-technology
blend at both endpoints and in between (§2.4), the market-share-weighted RVP over
a real fuel supply with two inner-join misses in it, the reg-class wildcard's row
count, and the energy spine's two exact zeros.

### 7.3 Precision-sensitive operations, ranked

1. **The `exp` in REFEC-2.** The exponent is 1.10369704 for gasoline, so a
   relative error `e` in the exponent's terms becomes `e × 1.1036` in the rate.
   The largest term is `D × averageRVP` = 1.052; drop the RVP and the rate is
   1.0530 instead of 3.0152931, a factor of 2.86.
2. **The `minimumRefuelingVaporLoss` sentinel at exactly −1.** An integer
   comparison, so not a precision question, but the two readings differ by the
   whole rate.
3. **The temperature window at 45 and 90 °F.** 59.5 is 14.5 °F inside the lower
   bound.
4. **The tank-difference limit at 20 °F.** 12.03091 is 7.97 °F inside it.
5. **The A/C activity clamp** at −0.29698 and the **EV temperature clamp** at
   +0.015625, both inherited from the energy spine and both further from their
   boundaries than at `mixed-onroad`'s hour.

---

## 8. Gaps and things not verified

* **The `evefficiency` divergence in `moves.rs` still applies**, inherited from
  `docs/mixed-onroad.md` §2.3(f) through the energy spine. It reaches the
  emitted rows only through the electricity cohorts' energy, and those cohorts
  are dropped by REFEC-7 — so unlike in `mixed-onroad` and `process-brakewear`
  it moves **no** row of this fixture's output. That is a narrowing, not a
  resolution, and it cuts both ways: the EV temperature arm this snapshot's
  59.5 °F makes live is equally invisible here (§7.2).
* **The auxiliary-power energy process (91) is in the consumed set and not in
  the run.** `rspp_isEnergySource` admits it and nothing exercises it. A
  hotelling RunSpec on source type 62 would be needed, and none of the 39
  fixtures is one.
* **No off-network road type is selected anywhere in the 39 fixtures**, so
  §2.2's two mechanisms cannot be told apart by any snapshot in this repository.
  The same gap blocks the evaporative soak chain (`docs/evap-fvv.md` §8.3) and
  needs a RunSpec generated in `moves.rs`, not another slice here.
* **`controlledRefuelingRate` takes one value, 0.0361**, on every row where it
  is weighted at all, so the fixture cannot distinguish it from a constant. The
  component probes it at 0.5.
* **Total Organic Gases is selected and not emitted.** 8618 and 8619 are in
  `runspecpollutantprocess` and produce no `MOVESOutput` row, because the
  speciation calculator that would chain off this one's THC is not wired in the
  captured run. This fixture's §2.1 key column is what keeps them out of the
  refueling rate; whether the speciation chain reproduces is `chain-tog-speciation`'s
  question.

---

## 9. Summary for the `.esm` author

* Start from `fixtures/process-brakewear.esm`. Its scope is this one's, and its
  energy block is byte-identical in the generator table, so a retarget that
  changes the snapshot path and nothing else already computes the activity this
  fixture chains off.
* Delete the PM10 chain and keep its **shape**: the energy spine is the same
  `syms`-named self-join of the rate relation, on the cohort ordinal instead of
  on a chained pollutant-process.
* Do **not** divide the energy by 1,055,055.9. The rebase is the output
  processor's and happens after the chain.
* Key both refueling rate lookups on a column that is the process for a THC row
  and 0 otherwise. Keying on the process alone gives Total Organic Gases a rate.
* Read `minimumRefuelingVaporLoss <= -1` as a sentinel and a `(0, 0)` temperature
  limit pair as *disabled*. Both fuels that carry them have `exp(0) = 1` as their
  raw rate, so both mistakes produce a plausible number.
* Guard the NULL fuel columns with a value, not an indicator: `0 × NaN` is NaN.
* One rank across the whole rate relation, not a per-block cohort ordinal — the
  two blocks are 64 and 104.
