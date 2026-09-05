# `process-evap-permeation` — computation specification

The fourth port specification in this repository, and the second of PLAN.md §3
Phase 4. Its siblings are `docs/nonroad-logging-county.md` (a Fortran chain),
`docs/mixed-onroad.md` (a rates-first SQL chain) and `docs/evap-leaks.md` (the
SQL *inventory* chain this one is a variant of).

What it specifies: how canonical MOVES turns the `process-evap-permeation`
snapshot's input tables into its 128 rows of `MOVESOutput`; which parts of that
this port computes and which one it does not; and an independent reproduction
(`./run-permeation-oracle.sh`, §6.5) whose numbers can be checked against the
snapshot without reading this file.

**Read §0.3 and §8.1 first if you are here because PLAN.md said this slice was
unblocked.** It is unblocked in the part that PLAN.md named and blocked in a
part PLAN.md did not — the two are different steps of the same generator, and
the difference is measured below rather than argued.

Sources, in the order they were trusted:

1. `../moves.rs/crates/moves-calculators/src/calculators/evaporative_permeation_calculator.rs`
   — the port of `EvaporativePermeationCalculator.java` + `.sql`, with
   `INPUT_TABLES` declared and the SQL step labels PC-1 … PC-6 preserved.
2. `.../generators/tank_temperature_generator.rs` — TTG-1 … TTG-7, which
   produce `AverageTankTemperature`.
3. `.../generators/evap_op_mode_distribution.rs`,
   `.../generators/totalactivitygenerator/`,
   `.../generators/source_bin_distribution_generator.rs` — the same three
   generators `docs/evap-leaks.md` specifies, which this slice reuses in full.
4. The snapshot itself: 370 declared tables, **235 non-empty**, plus the
   expected `MOVESOutput`.

---

## 0. The fixture at a glance

| | |
|---|---|
| snapshot | `../moves.rs/characterization/snapshots/process-evap-permeation` |
| output database | `out_process_evap_permeation` |
| `MOVESOutput` rows | **128** |
| pollutant / process | THC (1) × Evap Permeation (11); `polProcessID` **111** |
| calculator | `EvaporativePermeationCalculator`, a direct master-loop subscriber (process 11, `MONTH` granularity) |
| year / month / hour | 2020 / 8 / 7 |
| day types | 2 (weekend) and 5 (weekday) — `hourDayID` 72 and 75 |
| county / zone / link | 26161 (Washtenaw, MI) / 261610 / 2616104 |
| link road type | 4, Urban Restricted Access — an on-network link |
| source type | 21, Passenger Car |
| emitted mass | 32.256746 g THC |

The run scope, the geography, the activity chain, the cohort structure and the
operating-mode distribution are **identical** to `process-evap-leaks`. Only the
calculator differs, and it differs by adding two adjustments the leaks chain has
none of: a tank-temperature adjustment (PC-2) and a fuel adjustment (PC-3).

### 0.1 What is the same as the leaks slice, and what is not

Same, and specified in `docs/evap-leaks.md` rather than repeated here: the run
scope rule (§0.1 there — take it from the execution database's `runspec*`
tables, because the XML's `@key` attributes are 0-based indices into sorted ID
lists), the whole activity chain A1–A10, the cohort construction C1–C4, and the
evaporative operating-mode distribution E1–E3. `./run-permeation-oracle.sh`
recomputes all of them from this snapshot's own tables and checks them against
this snapshot's own `SHO`, `SourceHours`, `sourceBinDistributionFuelUsage` and
`OpModeDistribution`, so the reuse is verified here and not assumed.

**One thing in the shared part is NOT the same, and it changes every key.** The
source bin's *dimensions* are per `(sourceTypeID, polProcessID)`, not per run:

| snapshot | `polProcessID` | `isRegClassReqd` | a gasoline bin |
|---|---|---|---|
| `process-evap-leaks` | 113 | **Y** | `1010120240000000000` |
| `process-evap-fvv` | 112 | **Y** | — |
| `process-evap-permeation` | 111 | **N** | `1010100240000000000` |

`SourceBinDistributionGenerator` collapses `regClassID` to 0 in the bin id when
`SourceTypePolProcess.isRegClassReqd` is `N`
(`source_bin_distribution_generator.rs:1355`). So the same 125 cohorts carry
different `sourceBinID`s in the three evaporative snapshots, and a chain that
takes the leaks bin rule as a run-wide constant produces 125 keys that match
nothing and an output of exactly zero rows. Call this **C2′**: the bin key's
fields are read from `SourceTypePolProcess`, per process.

The regulatory class does not disappear — PC-1b puts it back, weighted by
`RegClassSourceTypeFraction.regClassFraction`, which for source type 21 is a
single row per `(fuel, model year)` at fraction 1.0.

### 0.2 Why 128 rows

```
128 = 64 (modelYearID, fuelTypeID) cohorts  x  2 day types
64  = 41 model years on gasoline (1980-2020) + 23 on E85 (1998-2020)
```

Exactly the leaks slice's key set, for exactly the reasons `docs/evap-leaks.md`
§0.2 gives: `emissionRateByAge` carries rows for the 22 gasoline and 19 E85
source bins and for none of the 39 diesel or electricity bins, so the PC-1b
inner join removes them. The SCCs differ only in their process suffix —
`2201210411` and `2205210411` against the leaks slice's `…13`.

### 0.3 What this slice was chosen to establish, and what it actually established

PLAN.md chose it — with `process-evap-fvv` — as "the first chance to exercise
[F12's recurrence construct] on a *different* recurrence than the one it was
designed against", on the ground that permeation "needs `AverageTankTemperature`,
which is the output of `TankTemperatureGenerator`'s quarter-hour recurrence".

The premise is true and the conclusion does not follow, and the difference is
worth stating precisely because it decides what the next slice should be.

`AverageTankTemperature` has three operating modes (TTG-5):

| `opModeID` | what it is | where it comes from |
|---|---|---|
| 151 cold soaking | the parked tank temperature | **TTG-1**, the quarter-hour recurrence |
| 300 all running | duration-weighted mean over trip segments | TTG-4a, via TTG-2 and TTG-3 |
| 150 hot soaking | mean over the post-trip minute trajectory | TTG-4b, via TTG-3 |

PC-2b weights the three by `OpModeDistribution.opModeFraction`, and this
fixture's distribution — computed, not assumed; E1–E3 of `docs/evap-leaks.md`
§2.3 derive it, and the oracle reproduces all six rows exactly — is

```
opMode 150: 0.0     opMode 151: 0.0     opMode 300: 1.0
```

for both hour-days, because `fractionOfOperating` is exactly 1 at an on-network
link. **So the quarter-hour recurrence's output is multiplied by an
`opModeFraction` of exactly zero, and this fixture cannot see it.** Measured on
the oracle, by perturbing each mode's tank temperature by +50 °F and rerunning:

| perturbation | worst cell | total THC |
|---|---|---|
| none | 6.174e-06 | 32.256748 g |
| `AverageTankTemperature` opMode **151** +50 °F | 6.174e-06 | 32.256748 g |
| `AverageTankTemperature` opMode **150** +50 °F | 6.174e-06 | 32.256748 g |
| `AverageTankTemperature` opMode **300** +50 °F | **5.855e+00** | **221.124805 g** |

Not "changes by less than the tolerance" — *unchanged*, at every one of the 128
cells. Every number this fixture emits flows through mode 300, which is
TTG-4a's walk over `SampleVehicleTrip`, which is finding **F28**: a recurrence
whose predecessor is named by a data column.

Three consequences, and they are the useful output of this slice:

1. **The recurrence had to be verified somewhere else, and was.**
   `components/tank_temperature.esm` checks TTG-1 against three captured MOVES
   intermediates — 96 `QuarterHourTemperature` rows, 96
   `QuarterHourTankTemperature` rows and all 24 `ColdSoakTankTemperature` rows —
   with 64 assertions, and none of them is downstream of an `opModeFraction`. A
   fixture-level check would have been worthless here: it would have passed
   with the recurrence deleted. That is finding F24's lesson arriving from the
   other direction — there the clamp laundered the sentinel, here a zero weight
   would have.
2. **`process-evap-fvv` is the better next slice, not the equal one — and
   this was WRONG, corrected here after measurement.**
   `MultidayTankVaporVentingCalculator` TVV-2 and TVV-3 read
   `ColdSoakTankTemperature` *directly* — TVV-3's tank vapour generated is
   `tankSize·(1 − fill)·tvgTermA·exp(tvgTermB·RVP)·(exp(tvgTermC·t2) −
   exp(tvgTermC·t1))` with `t1`, `t2` the cold-soak tank temperatures of two
   hours — so TTG-1 is numerically load-bearing there in a way it is not here.
   **The conclusion does not follow.** TVV-8 fills `WeightedMeanBaseRate` from
   two disjoint inserts, and everything downstream of `ColdSoakTankTemperature`
   lands in the cold-soak one, which writes operating mode **151** — carrying
   the same `opModeFraction` of exactly zero as here, and for the same reason.
   `docs/evap-fvv.md` §0.3 computes the whole venting chain and measures it:
   2,688 non-zero cold-soak base rates, the largest 0.42 g/h, and all 128
   output cells **bit-identical** under a +50 °F perturbation of
   `ColdSoakTankTemperature`, a doubling of TVV-5's equation, a tripling of the
   soak recurrence's carry and a ×7 of TTG-7's fraction.

   The mechanism is structural, not particular to a process: E2 weights every
   soak mode by `1 − fractionOfOperating`, and `fractionOfOperating` is
   identically 1 at an **on-network** link because A10 sets `SourceHours = SHO`
   there. All three evaporative snapshots have one link, on road type 4. So no
   evaporative process would have answered the recurrence question; a run
   selecting road type 1 would. `docs/evap-fvv.md` §8.3 states that.
3. **PLAN.md's screening is corrected in place**, not footnoted.

---

## 1. Inputs

The calculator declares 25 `INPUT_TABLES`. Beyond the ones
`docs/evap-leaks.md` §1 already inventories for the shared activity, cohort and
operating-mode chain, permeation adds:

| table | rows | what it carries |
|---|---|---|
| `averageTankTemperature` | 288 | TTG-5's per-`opModeID` tank temperature, 2 tank-temperature groups × 48 hour-days × 3 modes |
| `temperatureAdjustment` | 2 | `tempAdjustTermA`, `tempAdjustTermB` for `polProcessID` 111, fuel types 1 and 5 |
| `hcPermeationCoeff` | 120 | `fuelAdjustment` / `fuelAdjustmentGPA` per `(etohThreshID, fuelMYGroupID)` |
| `etohBin` | 8 | the ethanol-volume brackets `hcPermeationCoeff` is keyed through |
| `fuelSupply` | 5 | the market shares of the region's fuel formulations |
| `fuelFormulation` | 2158 | `ETOHVolume` and `fuelSubtypeID` |
| `fuelSubtype` | 13 | subtype → fuel type |
| `regClassSourceTypeFraction` | 125 | PC-1b's regulatory-class split |
| `sourceTypeModelYearGroup` | 37 | source type × model-year group → tank-temperature group |
| `pollutantProcessMappedModelYear` | 333 | `fuelMYGroupID` → the model years it covers |
| `zoneMonthHour` | 24 | the ambient temperatures TTG-1 starts from |
| `sourceTypePolProcess` | 1 | §0.1's `isRegClassReqd` |

`imCoverage` and `imFactor` are empty, so this fixture has no I/M program —
same as the leaks slice.

---

## 2. The chain

A1–A10 (activity), C1–C4 (cohorts, with C2′ from §0.1) and E1–E3 (the
operating-mode distribution) are `docs/evap-leaks.md` §2.1–§2.3 unchanged.
What follows is TTG-1 and then the calculator.

### 2.6 TTG-1 — the quarter-hour cold-soak tank temperature

`tank_temperature_generator.rs:1483-1537`, ported in
`components/tank_temperature.esm`. Three parts:

* **TTG-1a.** Interpolate the 24 hourly `ZoneMonthHour.temperature` values to
  quarter-hour resolution. For hour `h` and step `ts ∈ 1…4`,

  ```
  quarterHourTemperature = t[h] + (ts − 1) · 0.25 · (t[next h] − t[h])
  ```

  with `next(24) = 1`. An hour produces output only when both it and its
  successor have a temperature — the Java's self-join is inner.

* **TTG-1b.** A **recurrence** over the 96-cell `(hour, timeStep)` grid, swept
  in that order, with `sumTempDelta` starting at 0 and
  `firstQHTankTemperature = quarterHourTemperature[1, 1]`:

  ```
  quarterHourTankTemperature = 1.4 · sumTempDelta + firstQHTankTemperature
  tempDelta                  = quarterHourTemperature − quarterHourTankTemperature
  sumTempDelta              += tempDelta
  ```

  The tank lags the air, and 1.4 is the lag coefficient. Note what the carried
  value is: `sumTempDelta`, whose increment is a function of the answer so far.
  Substituting gives the two-term closed form
  `T[k+1] = 1.4·Q[k] − 0.4·T[k]`, which is algebraically identical, shorter, and
  the wrong thing to write — esm-spec §4.3.1.1 rounds a carried value to the
  variable's `element_type` at **every** cell, so the two forms are the same
  computation only in exact arithmetic. In binary64 they agree to 2.8e-14 over
  all 96 cells; in the `real*4` MOVES runs they do not. Carry what the Java
  carries.

* **TTG-1c.** `coldSoakTankTemperature[h]` is the `ts = 1` cell of hour `h`.

The feedback ratio is −0.4, so the recurrence **contracts** error rather than
amplifying it: hour 24 is 93 cells downstream of the anchor and still agrees
with the reference to 7.550e-07, which is that column's six-significant-figure
storage floor. A perturbation of one hour's ambient temperature is confined to
that hour and later ones, exactly (measured: perturbing hour 12 by +10 °F leaves
hours 1–11 bit-identical; perturbing hour 23 leaves hours 1–22 bit-identical),
which is the causal-sweep property esm-spec §4.3.1.1 points 1–3 promise, checked
rather than assumed.

### 2.7 The calculator, PC-1 … PC-6

`emissionQuant = weightedTemperatureAdjust · meanBaseRate ·
weightedFuelAdjustment · sourceHours / noOfRealDays`, assembled in six steps.

* **PC-1a** tags each `sourceBinDistributionFuelUsage` row with the age group
  of `yearID − modelYearID`.
* **PC-1b** `meanBaseRate = Σ sourceBinActivityFraction · meanBaseRate ·
  regClassFraction`, over source bins, grouped by
  `(polProcessID, sourceTypeID, regClassID, modelYearID, fuelTypeID)`.
  `EmissionRateByAge` carries one row per operating mode and the join does not
  constrain `opModeID`, so every matching row contributes.
* **PC-2a** `temperatureAdjustByOpMode = tempAdjustTermA ·
  exp(tempAdjustTermB · averageTankTemperature)`, over the cross product of
  `AverageTankTemperature` and `TemperatureAdjustment` (the SQL join carries no
  `ON` clause), expanded across the adjustment's model-year range.
* **PC-2b** `weightedTemperatureAdjust = Σ temperatureAdjustByOpMode ·
  opModeFraction`, joined to `OpModeDistribution` on
  `(hourDayID, polProcessID, opModeID)` and to `Link` on `(linkID, zoneID)`.
  **This is where §0.3's zero lives.**
* **PC-3** `weightedFuelAdjustment = Σ marketShare · (fuelAdjustment +
  GPAFract · (fuelAdjustmentGPA − fuelAdjustment))`, over the fuel supply,
  narrowed through the ethanol bin (`etohThreshLow ≤ ETOHVolume <
  etohThreshHigh`) and the mapped model years. `GPAFract` is 0 for Washtenaw
  County, so the GPA term contributes nothing here and the adjustment is the
  market-share-weighted `fuelAdjustment`. The Processing section opens with
  `update FuelFormulation set ETOHVolume = 0 where ETOHVolume is null`, and that
  coercion is part of the step.
* **PC-4** `fuelAdjustedEmissionRate = meanBaseRate · weightedFuelAdjustment`,
  on `(polProcessID, modelYearID, fuelTypeID)` and `Year (yearID, fuelYearID)`.
* **PC-5** `fuelAdjustedEmissionQuant = fuelAdjustedEmissionRate · sourceHours
  / noOfRealDays`, joining `SourceHours` on
  `(yearID, modelYearID = yearID − ageID, sourceTypeID)`.
* **PC-6** `emissionQuant = weightedTemperatureAdjust ·
  fuelAdjustedEmissionQuant`, gated by `SourceTypeModelYearGroup`: the
  temperature adjustment's `tankTemperatureGroupID` must equal the one the
  row's `(sourceTypeID, modelYearGroupID)` maps to. That gate is what keeps
  source type 21's pre-1996 model years (tank-temperature group 5) apart from
  its 1996-and-later ones (group 3) — 288 `AverageTankTemperature` rows are 2
  groups × 48 hour-days × 3 modes, and picking the wrong group is a wrong
  answer rather than a missing row.

---

## 6. Reproductions

### 6.5 An independent reproduction

Extracted and run by `./run-permeation-oracle.sh`. It computes the activity
chain, the cohorts, the operating-mode distribution, TTG-1 and PC-1 … PC-6 from
the snapshot's own input tables and compares six relations against the
snapshot's own captured intermediates and its `MOVESOutput`.

**What it takes from the reference: 192 of the 288 `AverageTankTemperature`
cells** — operating modes 150 and 300, which are TTG-4's and which §8.1 says
why. Mode 151's 96 cells are computed from `ZoneMonthHour` through TTG-1. That
one read is stated in the script's output on every run, in the same posture
`./run-onroad-oracle.sh` states its `baserate_1_2020` read.

```python
#!/usr/bin/env python3
"""Independent reproduction of the process-evap-leaks chain from the snapshot's
own INPUT tables: the activity chain (specification 2.1, A1-A10), the cohort
structure and its row rule (2.2, C1-C4), the evap operating-mode distribution
(2.3, E1-E3) and the calculator (2.4-2.5, L1/L8/L9/O1-O3).

Purpose: attribution. When a `.esm` disagrees with the snapshot, a third
implementation says whether the document or the specification is wrong."""
import sys
import glob
import collections
import pyarrow.parquet as pq

SNAP = sys.argv[1]
_PREFIX = glob.glob(SNAP + "/tables/db__movesexecution*__year.parquet")[0][:-len("year.parquet")]


def T(name):
    """One MOVESExecution table, as a list of dicts."""
    return pq.read_table(_PREFIX + name + ".parquet").to_pylist()


def OUT(name):
    """One table of the run's OUTPUT database."""
    return pq.read_table(glob.glob(SNAP + "/tables/db__out_*__" + name + ".parquet")[0]).to_pylist()


f = float

# ----------------------------------------------------------------- run scope
# Section 0.1: from the execution database's runspec* tables, never from the
# RunSpec XML, whose @key attributes are 0-based indices into sorted ID lists.
YEAR = T("runspecyear")[0]["yearID"]
MONTH = T("runspecmonth")[0]["monthID"]
HOUR = T("runspechour")[0]["hourID"]
DAYS = sorted(r["dayID"] for r in T("runspecday"))
ROADS = sorted(r["roadTypeID"] for r in T("runspecroadtype"))
ST = T("runspecsourcetype")[0]["sourceTypeID"]
LINK = T("link")[0]
LINK_ID, ZONE, COUNTY, LINK_ROAD = LINK["linkID"], LINK["zoneID"], LINK["countyID"], LINK["roadTypeID"]
PP = 100 * 1 + 11                                   # section 5.1: THC x Evap Permeation
HD = {r["dayID"]: r["hourDayID"] for r in T("hourday") if r["hourID"] == HOUR}
print("scope: year %d, month %d, hour %d, days %s, road types %s, source type %d,"
      % (YEAR, MONTH, HOUR, DAYS, ROADS, ST))
print("       link %d on road type %d, zone %d, county %d, polProcessID %d"
      % (LINK_ID, LINK_ROAD, ZONE, COUNTY, PP))

# ------------------------------------------------------- A1: the base year
base = max(r["yearID"] for r in T("year")
           if r["yearID"] <= YEAR and str(r["isBaseYear"]).upper() == "Y")
assert base == YEAR, "the population and VMT folds do not collapse (section 1.5)"
FUELYEAR = {r["yearID"]: r["fuelYearID"] for r in T("year")}[YEAR]

# --------------------------------------------- A2: sourceTypeAgePopulation
stpop = {r["sourceTypeID"]: f(r["sourceTypePopulation"])
         for r in T("sourcetypeyear") if r["yearID"] == base}
agefrac = {(r["sourceTypeID"], r["ageID"]): f(r["ageFraction"])
           for r in T("sourcetypeagedistribution") if r["yearID"] == base}
pop = {k: stpop[k[0]] * v for k, v in agefrac.items() if k[0] in stpop}

# -------------------------------------------------------- A3: travelFraction
mar = {(r["sourceTypeID"], r["ageID"]): f(r["relativeMAR"]) for r in T("sourcetypeage")}
hpms = {r["sourceTypeID"]: r["HPMSVtypeID"] for r in T("sourceusetype")}
group_total = collections.defaultdict(float)
for k in pop:
    group_total[hpms[k[0]]] += pop[k] * mar[k]
travelfrac = {k: pop[k] * mar[k] / group_total[hpms[k[0]]] for k in pop}

# ------------------------------------------------ A4, A5: annual VMT by age
ayv = {r["HPMSVtypeID"]: f(r["HPMSBaseYearVMT"])
       for r in T("hpmsvtypeyear") if r["yearID"] == base}
onroad = {r["roadTypeID"] for r in T("roadtype") if r["isAffectedByOnroad"]}
rtd = {r["roadTypeID"]: f(r["roadTypeVMTFraction"]) for r in T("roadtypedistribution")
       if r["sourceTypeID"] == ST and r["roadTypeID"] in onroad}
ages = sorted({k[1] for k in travelfrac if k[0] == ST})

# ------------------------------------- A6: averageSpeed, the ARITHMETIC mean
binspeed = {r["avgSpeedBinID"]: f(r["avgBinSpeed"]) for r in T("avgspeedbin")}
speed = collections.defaultdict(float)
for r in T("avgspeeddistribution"):
    if r["sourceTypeID"] != ST or r["roadTypeID"] not in ROADS:
        continue
    for d in DAYS:
        if r["hourDayID"] == HD[d]:
            speed[(r["roadTypeID"], d)] += f(r["avgSpeedFraction"]) * binspeed[r["avgSpeedBinID"]]

# --------------------------------------------- A7, A8, A9: SHO for the zone
weeks = {r["monthID"]: r["noOfDays"] / 7.0 for r in T("monthofanyyear")}[MONTH]
mvf = {r["monthID"]: f(r["monthVMTFraction"])
       for r in T("monthvmtfraction") if r["sourceTypeID"] == ST}[MONTH]
dvf = {(r["roadTypeID"], r["dayID"]): f(r["dayVMTFraction"]) for r in T("dayvmtfraction")
       if r["sourceTypeID"] == ST and r["monthID"] == MONTH}
hvf = {(r["roadTypeID"], r["dayID"]): f(r["hourVMTFraction"]) for r in T("hourvmtfraction")
       if r["sourceTypeID"] == ST and r["hourID"] == HOUR}
alloc = {r["roadTypeID"]: f(r["SHOAllocFactor"])
         for r in T("zoneroadtype") if r["zoneID"] == ZONE}
sho = {}
for rt in ROADS:
    for d in DAYS:
        for a in ages:
            vmt = (ayv[hpms[ST]] * rtd[rt] * travelfrac[(ST, a)]
                   * mvf * dvf[(rt, d)] * hvf[(rt, d)] / weeks)
            s = speed[(rt, d)]
            sho[(rt, HD[d], a)] = (vmt / s if s else 0.0) * alloc[rt]

# ---------------------- A10: SourceHours = SHO at an on-network link, = SHP at 1
assert LINK_ROAD != 1, "an off-network link needs SHP (allocation.rs:631-682)"
source_hours = {(HD[d], a): sho[(LINK_ROAD, HD[d], a)] for d in DAYS for a in ages}

# -------------------------------------------- C1, C2, C3: the cohorts and bins
maxage = max(r["ageID"] for r in T("agecategory"))
my_lo, my_hi = YEAR - maxage, YEAR
fuels = {r["fuelTypeID"] for r in T("runspecsourcefueltype") if r["sourceTypeID"] == ST}
mygroup = {(r["polProcessID"], r["modelYearID"]): r["modelYearGroupID"]
           for r in T("pollutantprocessmodelyear")}
shortgroup = {r["modelYearGroupID"]: r["shortModYrGroupID"] for r in T("modelyeargroup")}
sb = {r["sourceBinID"]: r for r in T("sourcebin")}
# C2': the bin's DIMENSIONS are per (sourceType, polProcess), not per run. Evap
# permeation sets isRegClassReqd = 'N' and its bins collapse regClassID to 0,
# where evap fuel leaks and fuel vapour venting set 'Y' and keep it -- so the
# same 125 cohorts carry DIFFERENT sourceBinIDs in the three snapshots.
REGCLASS_REQD = any(str(r["isRegClassReqd"]).upper() == "Y" for r in T("sourcetypepolprocess")
                    if r["sourceTypeID"] == ST and r["polProcessID"] == PP)


def bin_id(fuel, engtech, regclass, shortmy):
    """Section 2.2: 1e18 + fuel*1e16 + engTech*1e14 + regClass*1e12 + shortMY*1e10."""
    return 10**18 + fuel * 10**16 + engtech * 10**14 + regclass * 10**12 + shortmy * 10**10


sbaf = collections.defaultdict(float)
for r in T("samplevehiclepopulation"):
    frac = f(r["stmyFraction"])
    if (r["sourceTypeID"] != ST or not my_lo <= r["modelYearID"] <= my_hi
            or r["fuelTypeID"] not in fuels or frac <= 0.0):
        continue                          # C2's row rule: stmyFraction > 0
    g = mygroup.get((PP, r["modelYearID"]))
    if g is None or g not in shortgroup:
        continue                          # two inner joins
    rc = r["regClassID"] if REGCLASS_REQD else 0        # C2': isRegClassReqd
    b = bin_id(r["fuelTypeID"], r["engTechID"], rc, shortgroup[g])
    sbaf[(ST * 10000 + r["modelYearID"], b)] += frac

# --------------------------------------- C4: the equipped -> used fuel rebase
used_by_equipped = collections.defaultdict(list)
for u in T("fuelusagefraction"):
    if u["countyID"] != COUNTY or u["fuelYearID"] != FUELYEAR:
        continue
    for e in sb.values():
        if e["fuelTypeID"] != u["sourceBinFuelTypeID"]:
            continue
        if u["modelYearGroupID"] != 0 and e["modelYearGroupID"] != u["modelYearGroupID"]:
            continue
        for w in sb.values():
            if (w["fuelTypeID"] == u["fuelSupplyFuelTypeID"]
                    and w["engTechID"] == e["engTechID"]
                    and w["regClassID"] == e["regClassID"]
                    and w["modelYearGroupID"] == e["modelYearGroupID"]
                    and w["engSizeID"] == e["engSizeID"]
                    and w["weightClassID"] == e["weightClassID"]):
                used_by_equipped[e["sourceBinID"]].append((w["sourceBinID"], f(u["usageFraction"])))
sbdfu = collections.defaultdict(float)
for (stmy, b), v in sbaf.items():
    for used, usage in used_by_equipped.get(b, []):
        sbdfu[(stmy, used)] += usage * v

# -------------------------- E1, E2, E3: the evap operating-mode distribution
sho_sum, sh_sum = collections.defaultdict(float), collections.defaultdict(float)
for (rt, h, a), v in sho.items():
    sho_sum[h] += v
for (h, a), v in source_hours.items():
    sh_sum[h] += v
frac_op = {h: min(1.0, sho_sum[h] / sh_sum[h]) if sh_sum[h] else 0.0 for h in sh_sum}
soak = {(r["hourDayID"], r["opModeID"]): f(r["soakActivityFraction"])
        for r in T("soakactivityfraction")
        if r["sourceTypeID"] == ST and r["monthID"] == MONTH and r["zoneID"] == ZONE}
evap_modes = {r["opModeID"] for r in T("opmodepolprocassoc") if r["polProcessID"] == PP}
OPERATING = 300
omd = {}
for d in DAYS:
    h, total = HD[d], 0.0
    for om in sorted(evap_modes):
        if (h, om) in soak:
            omd[(h, om)] = soak[(h, om)] * (1.0 - frac_op[h])
            total += omd[(h, om)]
    omd[(h, OPERATING)] = max(0.0, 1.0 - total)     # E3: a RESIDUAL, not frac_op


# ============================================================================
# TTG-1 -- the quarter-hour cold-soak tank temperature (section 2.6).
#
# The one part of TankTemperatureGenerator this reproduction computes. It is a
# RECURRENCE over a 96-cell quarter-hour axis, and it is the shape
# components/tank_temperature.esm spells with esm-spec 4.3.1.1's causal
# self-reference. Its output is `AverageTankTemperature`'s operating mode 151.
# ============================================================================
amb = {r["hourID"]: f(r["temperature"]) for r in T("zonemonthhour")
       if r["zoneID"] == ZONE and r["monthID"] == MONTH}
qh_temp = {}
for hr in range(1, 25):                      # TTG-1a
    nxt = 1 if hr == 24 else hr + 1
    if hr not in amb or nxt not in amb:
        continue
    for ts in range(1, 5):
        qh_temp[(hr, ts)] = amb[hr] + (ts - 1) * 0.25 * (amb[nxt] - amb[hr])
first_tank = qh_temp[(1, 1)]
delta_sum, cold_soak = 0.0, {}
for (hr, ts) in sorted(qh_temp):             # TTG-1b, in (hour, step) order
    tank = 1.4 * delta_sum + first_tank
    delta_sum += qh_temp[(hr, ts)] - tank
    if ts == 1:                              # TTG-1c
        cold_soak[hr] = tank

# ============================================================================
# AverageTankTemperature -- TTG-5, of which only mode 151 is computed here.
#
# Modes 150 and 300 are the mean over `HotSoakTemperature`'s minutes and the
# duration-weighted mean over `OperatingTemperature`'s trip segments, both of
# which are downstream of TTG-2/3/4's walk over the 37,216 rows of
# `SampleVehicleTrip`. That walk is NOT this shape and is not reproduced here;
# see section 8.1 and docs/findings/README.md F28. The two modes are READ from
# the reference, and this is the only thing this script takes from it.
# ============================================================================
hour_of = {r["hourDayID"]: r["hourID"] for r in T("hourday")}
att, att_read, att_computed = {}, 0, 0
for r in T("averagetanktemperature"):
    if r["zoneID"] != ZONE or r["monthID"] != MONTH:
        continue
    k = (r["tankTemperatureGroupID"], r["hourDayID"], r["opModeID"])
    if r["opModeID"] == 151:
        att[k] = cold_soak[hour_of[r["hourDayID"]]]      # computed, section 2.6
        att_computed += 1
    else:
        att[k] = f(r["averageTankTemperature"])          # READ -- section 8.1
        att_read += 1

# ------------------------------------------- PC-1a, PC-1b: SBWeightedPermeationRate
import math
stmy_of = {r["sourceTypeModelYearID"]: r for r in T("sourcetypemodelyear")}
age_group_of = {r["ageID"]: r["ageGroupID"] for r in T("agecategory")}
fuel_of_bin = {r["sourceBinID"]: r["fuelTypeID"] for r in T("sourcebin")}
rcstf = collections.defaultdict(list)
for r in T("regclasssourcetypefraction"):
    rcstf[(r["sourceTypeID"], r["fuelTypeID"], r["modelYearID"])].append(
        (r["regClassID"], f(r["regClassFraction"])))
rates = collections.defaultdict(list)
for e in T("emissionratebyage"):
    rates[(e["sourceBinID"], e["polProcessID"], e["ageGroupID"])].append(f(e["meanBaseRate"]))

sbwpr = collections.defaultdict(float)
for (stmy, b), frac in sbdfu.items():
    s = stmy_of.get(stmy)
    if s is None or s["sourceTypeID"] != ST:
        continue
    ag = age_group_of.get(YEAR - s["modelYearID"])
    if ag is None:
        continue
    ft = fuel_of_bin.get(b)
    if ft is None:
        continue
    for rate in rates.get((b, PP, ag), []):
        for rc, rcf in rcstf.get((ST, ft, s["modelYearID"]), []):
            sbwpr[(PP, ST, rc, s["modelYearID"], ft)] += frac * rate * rcf

# ------------------------------- PC-2a, PC-2b: WeightedTemperatureAdjust
model_years = [r["modelYearID"] for r in T("modelyear")]
tadj = []
for (ttg, hd, om), temp in att.items():
    for ta in T("temperatureadjustment"):
        if ta["polProcessID"] != PP:
            continue
        adjust = f(ta["tempAdjustTermA"]) * math.exp(f(ta["tempAdjustTermB"]) * temp)
        for my in model_years:
            if ta["minModelYearID"] <= my <= ta["maxModelYearID"]:
                tadj.append((ttg, hd, om, ta["fuelTypeID"], my, adjust))
wta = collections.defaultdict(float)
for (ttg, hd, om, ft, my, adjust) in tadj:
    frac = omd.get((hd, om))
    if frac is None:
        continue
    wta[(hd, ttg, ft, my)] += adjust * frac

# ------------------------------------------ PC-3: WeightedFuelAdjustment
mapped_my = collections.defaultdict(list)
for r in T("pollutantprocessmappedmodelyear"):
    mapped_my[(r["polProcessID"], r["fuelMYGroupID"])].append(r["modelYearID"])
ff_of = {r["fuelFormulationID"]: r for r in T("fuelformulation")}
ft_of_subtype = {r["fuelSubtypeID"]: r["fuelTypeID"] for r in T("fuelsubtype")}
fuelyear_of = {r["yearID"]: r["fuelYearID"] for r in T("year")}
GPA = f(T("county")[0]["GPAFract"])
wfa = collections.defaultdict(float)
for fs in T("fuelsupply"):
    if fuelyear_of.get(YEAR) != fs["fuelYearID"]:
        continue
    ff = ff_of.get(fs["fuelFormulationID"])
    if ff is None:
        continue
    etoh = 0.0 if ff["ETOHVolume"] is None else f(ff["ETOHVolume"])
    ft = ft_of_subtype.get(ff["fuelSubtypeID"])
    if ft is None:
        continue
    for fa in T("hcpermeationcoeff"):
        if fa["polProcessID"] != PP:
            continue
        mys = mapped_my.get((fa["polProcessID"], fa["fuelMYGroupID"]))
        if not mys:
            continue
        contribution = f(fs["marketShare"]) * (
            f(fa["fuelAdjustment"]) + GPA * (f(fa["fuelAdjustmentGPA"]) - f(fa["fuelAdjustment"])))
        for eb in T("etohbin"):
            if (eb["etohThreshID"] != fa["etohThreshID"]
                    or etoh < f(eb["etohThreshLow"]) or etoh >= f(eb["etohThreshHigh"])):
                continue
            for my in mys:
                wfa[(fs["monthGroupID"], PP, my, ft)] += contribution

# ------------------------- PC-4, PC-5: the fuel-adjusted rate and quantity
faer = {}
for (pp, st, rc, my, ft), rate in sbwpr.items():
    for (mg, pp2, my2, ft2), adj in wfa.items():
        if (pp2, my2, ft2) == (pp, my, ft):
            faer[(st, rc, my, ft)] = rate * adj
real_days = {r["dayID"]: f(r["noOfRealDays"]) for r in T("dayofanyweek")}
day_of = {r["hourDayID"]: r["dayID"] for r in T("hourday")}
faeq = {}
for (hd, age), hours in source_hours.items():
    my = YEAR - age
    for (st, rc, my2, ft), rate in faer.items():
        if my2 != my:
            continue
        faeq[(hd, st, rc, my, ft)] = rate * hours / real_days[day_of[hd]]

# --------------------------------------- PC-6: the output rows (O1-O3)
ttg_of = {(r["sourceTypeID"], r["modelYearGroupID"]): r["tankTemperatureGroupID"]
          for r in T("sourcetypemodelyeargroup")}
mygroups = collections.defaultdict(list)
for r in T("pollutantprocessmodelyear"):
    mygroups[(r["polProcessID"], r["modelYearID"])].append(r["modelYearGroupID"])
ppa = {r["polProcessID"]: (r["processID"], r["pollutantID"]) for r in T("pollutantprocessassoc")}
process_id, pollutant_id = ppa[PP]


def onroad_scc(fuel, source, road, process):
    return "%d" % (22 * 10**8 + fuel * 10**6 + source * 10**4 + road * 10**2 + process)


rows, sccs = collections.defaultdict(float), {}
for (hd, st, rc, my, ft), quant in faeq.items():
    for mg in mygroups.get((PP, my), []):
        ttg = ttg_of.get((st, mg))
        if ttg is None:
            continue
        adj = wta.get((hd, ttg, ft, my))
        if adj is None:
            continue
        d = day_of[hd]
        rows[(d, ft, my)] += adj * quant
        sccs[(d, ft, my)] = onroad_scc(ft, st, LINK_ROAD, process_id)

# --------------------------------------------------------------------- compare
def worst(computed, reference, label, limit, absolute=False):
    """Compare two keyed relations: the ROW SET first, then every value.

    Missing and extra keys are counted SEPARATELY and either one fails -- a key
    the chain does not reach and a key it invents are different defects, and a
    comparison that folds a missing row into a relative error (by reading its
    value as 0) cannot fail on an over-emitting chain at all.

    `limit` is asserted, not merely printed. Printing a worst error and letting
    the script exit 0 makes a gate that cannot go red: this reproduction is run
    by ./run-tests.sh, which reads the EXIT CODE, so a regression that leaves
    the key set intact and moves every value would otherwise be reported green
    with the evidence sitting in the log."""
    missing = sorted(set(reference) - set(computed))
    extra = sorted(set(computed) - set(reference))
    assert not missing, "%s: %d key(s) in the reference and not computed, e.g. %s" % (
        label, len(missing), missing[:3])
    assert not extra, "%s: %d key(s) computed and not in the reference, e.g. %s" % (
        label, len(extra), extra[:3])
    if absolute:
        w = max(abs(computed[k] - v) for k, v in reference.items())
        kind = "ABSOLUTE"
    else:
        w = max(abs(computed[k] - v) / abs(v) for k, v in reference.items() if v)
        kind = "relative"
    print("%-28s %4d rows, 0 missing, 0 extra, worst %s error %.3e"
          % (label + ":", len(reference), kind, w))
    assert w <= limit, "%s: worst %s error %.3e exceeds the recorded %.1e" % (
        label, kind, w, limit)
    return w


worst({(k[1], k[2]): v for k, v in sho.items()},
      {(r["hourDayID"], r["ageID"]): f(r["SHO"]) for r in T("sho")}, "SHO", 1e-5)
worst(source_hours,
      {(r["hourDayID"], r["ageID"]): f(r["sourceHours"]) for r in T("sourcehours")}, "SourceHours", 1e-5)
worst(dict(sbdfu),
      {(r["sourceTypeModelYearID"], r["sourceBinID"]): f(r["sourceBinActivityFraction"])
       for r in T("sourcebindistributionfuelusage_%d_%d_%d" % (PP % 100, COUNTY, YEAR))},
      "sourceBinDistribution", 1e-5)
worst(omd,
      {(r["hourDayID"], r["opModeID"]): f(r["opModeFraction"]) for r in T("opmodedistributiontemp")},
      "OpModeDistribution", 1e-12, absolute=True)
worst(cold_soak,
      {r["hourID"]: f(r["coldSoakTankTemperature"]) for r in T("coldsoaktanktemperature")
       if r["zoneID"] == ZONE and r["monthID"] == MONTH}, "ColdSoakTankTemperature", 1e-6)
worst({(r["hourID"], r["timeStepID"]): qh_temp[(r["hourID"], r["timeStepID"])]
       for r in T("quarterhourtemperature")},
      {(r["hourID"], r["timeStepID"]): f(r["quarterHourTemperature"])
       for r in T("quarterhourtemperature")}, "QuarterHourTemperature", 1e-12)

out = OUT("movesoutput")
expected = {(o["dayID"], o["fuelTypeID"], o["modelYearID"]): f(o["emissionQuant"]) for o in out}
assert len(expected) == len(out), "the reference's own key is not unique"
for o in out:
    k = (o["dayID"], o["fuelTypeID"], o["modelYearID"])
    assert sccs[k] == o["SCC"], (sccs[k], o["SCC"])
    assert o["processID"] == process_id and o["pollutantID"] == pollutant_id
w = worst(dict(rows), expected, "emissionQuant", 2e-5)   # tolerance.toml's per-cell gate
print("%-28s %d cohorts x %d day types = %d rows, exact; SCCs %s"
      % ("key set:", len(rows) // len(DAYS), len(DAYS), len(rows), sorted(set(sccs.values()))))
print("%-28s %.6f g computed / %.6f g in MOVESOutput"
      % ("total THC:", sum(rows.values()), sum(expected.values())))
print("%-28s %d of %d AverageTankTemperature cells computed (mode 151, TTG-1),"
      % ("read from the reference:", att_computed, att_computed + att_read))
print("%-28s %d read (modes 150 and 300); section 8.1"
      % ("", att_read))
```

### 6.6 What the reproduction is for

Attribution. When an `.esm` disagrees with the snapshot, a third implementation
says whether the document or the specification is wrong. It is also the only
executable statement of §8.1's measurement: perturb the `att[k] = f(...)` read
by operating mode and rerun, and the table in §0.3 falls out.

---

## 7. Tolerance

`emissionQuant` reproduces to **6.174e-06** worst relative error over all 128
rows, with an exact key set. That is the reference's own six-significant-figure
column storage propagated through the chain, the same figure and the same cause
as the leaks slice's 7.294e-06 — `MOVESOutput.emissionQuant` is stored as
decimal text and the inputs it is built from are `FLOAT`.

`ColdSoakTankTemperature` reproduces to 7.550e-07 and
`QuarterHourTemperature` to 1.175e-14; the difference between those two is the
storage width of the columns, not the accuracy of the step.

### 7.1 What the fixture does not exercise, found by sabotaging the oracle

Every gate in §6.5 was checked by breaking what it guards. Four went red as
intended — the TTG-1b smoothing coefficient 1.4 → 1.0 (`ColdSoakTankTemperature`
4.978e-03 against its 1e-06 limit), TTG-1a's hour-24 wrap removed, §0.1's C2′
bin rule ignored (125 keys computed that match nothing), PC-5's `noOfRealDays`
division dropped (`emissionQuant` 4.000e+00), and the read of
`AverageTankTemperature` nudged by 1% (`emissionQuant` 2.716e-02, which is also
what makes the read demonstrably load-bearing).

**One did not, and it is worth recording.** Deleting `marketShare` from PC-3
entirely changes nothing, because all five `FuelSupply` rows in this snapshot
carry `marketShare = 1.0`. So this fixture does not test the fuel-supply
weighting at all; it tests that the *sum over the supply* is taken. An
`expand-fueltype-*` fixture would. The same is true of `GPAFract`, which is 0
for Washtenaw County and makes PC-3's `fuelAdjustment + GPAFract ·
(fuelAdjustmentGPA − fuelAdjustment)` collapse to `fuelAdjustment`.

Recording a gate that cannot fail is the point of running the sabotage rather
than assuming it: two of PC-3's three factors are inert on this fixture, and a
port that got either wrong would be green here and wrong on the next slice.

---

## 8. What is not computed

### 8.1 `AverageTankTemperature` operating modes 150 and 300

TTG-5 builds them from `OperatingTemperature` (14,462 rows) and
`HotSoakTemperature` (182,532 rows), which TTG-4 builds from
`SampleVehicleTripByHour`, which TTG-2 builds by splitting
`SampleVehicleTrip`'s 37,216 rows across the hours they span.

TTG-4a is a **work queue**: the seed processes every first-of-day trip, and each
trip, as its last segment is reached, enqueues the trip whose `priorTripID` is
its own `tripID`, carrying forward the temperature its hot soak ended at (or a
`−1000` sentinel meaning "started cold", in which case the next trip starts from
`coldSoakTankTemperature` instead). Within a trip, segments split across an hour
boundary carry `keyOffTemp` forward. TTG-4b then walks the following minutes
one at a time.

That is three nested recurrences, and the outermost of them is **finding F28**:
its predecessor is named by a data column, and esm-spec §4.3.1.1's causal
self-read requires an offset of the frame symbol. Measured on this snapshot,
26,300 of the 37,216 trips carry a `priorTripID` and `tripID − priorTripID` is
1 for 24,610 of them and 2…7 for the other 1,690, so there is no constant lag to
write. F28's control shows the workaround — contract the lag over `[1, 7]` and
select with an equality guard — and shows what it costs.

**This is a scope decision, not a blocker.** The chain is expressible; it is
about the size of the whole leaks slice again, it has no bearing on the
recurrence question this phase was opened to answer, and §0.3 shows the two
modes it produces are the ONLY thing this fixture is sensitive to. Recording the
read and moving on buys more than half-building it would.

### 8.2 What `process-evap-fvv` would need on top of this

Listed here because §0.3 argues FVV is the better next slice and that argument
should carry its bill with it:

* **TTG-1** — done (`components/tank_temperature.esm`), and load-bearing there.
* **TTG-7** `ColdSoakInitialHourFraction` (534 rows) — TVV-7 Part A weights
  every unweighted hourly TVV by it, before any operating-mode split, so it
  cannot be reached past. It is downstream of TTG-2/TTG-3, i.e. F28 again.
* **`TankFuelGenerator`'s `AverageTankGasoline`** — TVV-3 needs its `RVP`, and
  the table is captured **empty** in all three evaporative snapshots, so it must
  be computed rather than read.
* **The nine `TVV-*` steps plus the TVG soak-day recurrence**, whose TVV-5
  evaluates `tvvEquation` / `leakEquation` strings that MOVES stores as *data*
  in `cumTVVCoeffs` (2,188 rows, present in the snapshot). The soak-day
  recurrence itself is an ordinary index-axis fold over soaking days 1, 2, 3…
  and needs nothing F12 did not deliver.

**§8.2 is corrected by `docs/evap-fvv.md`, which did the work.** Three
statements above did not survive contact with the snapshot:

* **`TankFuelGenerator`'s `AverageTankGasoline` is needed, but not by TVV-3.**
  Its RVP does reach TVV-3, and TVV-3 is zero-weighted. The place it is
  load-bearing is TVV-8's temperature / RVP adjustment on operating mode 300,
  which is on the *other* side of the calculator; omitting it is a 2.79 %
  error. See `docs/evap-fvv.md` §2.5 and §2.13.
* **TTG-7 "cannot be reached past" is true and does not matter.** It is
  computed forward through TVV-7 from the captured 534-row table, and
  multiplying it by 7 changes nothing at all.
* **TVV-5 does not evaluate strings.** The MOVES *default* database stores SQL
  expressions there, but `alterReplacementsAndSections` rewrites them in the
  *execution* database as sequential abbreviations before the snapshot is
  taken, so `cumTVVCoeffs` here holds exactly six `tvvEquation` labels
  (`T0`…`T5`) and twelve `leakEquation` labels (`L0`…`L11`) and no expression
  anywhere. Factored, those eighteen are **two forms and eighteen coefficient
  rows**; `docs/evap-fvv.md` §2.10 carries both tables and
  `lib/evaporative.esm` carries the forms.

So FVV is one further generator (`TankFuelGenerator`), one F28-shaped step
(TTG-7) and the largest calculator SQL file in MOVES. It is the next slice; it
is not a small one.
