# `mixed-onroad` — computation specification

The port specification for the first **onroad** fixture, written to the method
of `docs/nonroad-logging-county.md`: the input inventory determined from
evidence, the chain with source lines into `../moves.rs`, every join with its
exact key pairs, the reusable shapes, and worked examples whose numbers can be
checked by hand.

It differs from its NONROAD companion in one important way, and the difference
is stated here rather than buried in §8. **One relation in the chain is not
computed by this port**: the speed-bin-weighted, drive-cycle operating-mode
distribution `W[hourDayID, opModeID]`, 46 numbers. Everything on either side of
it is specified, verified against the snapshot, and reproduced by the §6.5
oracle. §7.3 gives the measured decomposition that isolates it, §8.1 says what
computing it would take, and §7.4 says what that costs the fixture comparison.
The reason this document exists in this shape is that a specification which
says exactly where it stops is worth more than one that implies it goes all
the way.

---

## 0. The fixture at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/mixed-onroad.xml` |
| Model | ONROAD, `modelscale` `Inv` (inventory), `modeldomain` `DEFAULT` |
| Geography | county 26161 (Washtenaw, Michigan), zone 261610, link 2616104 |
| Time | year 2020, month **8**, hour **9**, day types **2 (weekend) and 5 (weekday)** |
| Vehicles | sourceTypeID 21 (passenger car); fuel types **1, 2, 5, 9** |
| Road | roadTypeID 4 (urban restricted access) |
| Pollutant/process | **polProcessID 9101 only** — pollutant 91 (Total Energy Consumption) × process 1 (Running Exhaust) |
| Model years | 1980–2020 (41) |
| Output | `db__out_mixed_onroad__movesoutput`, **250 rows** |
| Output units | energy in **Million BTU**, `outputtimestep` **Hour** |
| Calculator path | rates-first: `TotalActivityGenerator` → `SourceBinDistributionGenerator` → `BaseRateGenerator` → `BaseRateCalculator` → output aggregation |

### 0.1 The RunSpec on disk does not describe the captured run

> **CORRECTION (Phase 4).** The *rule* this section reaches is right and is
> unchanged — scope a document from the execution database's `runspec*` tables.
> The *explanation* below, that the XML is a stale rewrite, is wrong for three of
> the five rows. `<month key>`, `<beginhour key>` and `<day key>` are canonical
> `RunSpecXML` **0-based indices into sorted ID lists**, not identifiers:
> `xml_format.rs:600-626` resolves month and hour as `key + 1`, and
> `default_db_setup.rs:2504-2540` resolves `<day key>` against the sorted
> `DayOfAnyWeek` list `[2, 5]`, where an out-of-range key means "no day
> selected" and falls back to all day types. All 27 onroad fixtures in the
> corpus show the identical offsets, which a stale rewrite would not reproduce.
> `docs/evap-leaks.md` §0.1 has the measurement and the citations; §8.3 there
> records the one row of the table below that was not re-derived (the
> pollutant/process row). Read the rule, not the diagnosis.

This has to be said first, because taking `mixed-onroad.xml` at face value
produces the wrong scope in five separate dimensions.

`provenance.json`'s `runspec_sha256` matches the checked-in
`fixtures/mixed-onroad.xml` byte for byte, and the XML's own `<description>`
explains why it nevertheless does not describe the snapshot: the file was
*rewritten* when the former `mixed-onroad-nonroad` scenario was split into an
onroad half and `nr-mixed-nonroad`, and the hash in `provenance.json` was
recomputed from the rewritten file. The tables were not re-captured.

| dimension | `mixed-onroad.xml` says | the execution database says |
|---|---|---|
| month | 7 | **8** (`runspecmonth`) |
| hour | 8 | **9** (`runspechour`) |
| day types | 5 | **2 and 5** (`runspecday`, 2 rows) |
| fuel types | 1 | **1, 2, 5, 9** (`runspecfueltype`, 4 rows) |
| pollutant/process | 9101, 9102, 9301, 9302 | **9101, 9102** (`runspecpollutantprocess`) |

**The authority is the execution database's own `runspec*` tables**, and every
number in this document is taken from them. A `.esm` that scoped itself from
the XML would emit a key set with the wrong month and hour in every row and
fail `require_exact_key_set` on all 250 — which is the good outcome; the
dangerous version is a fixture that reads the XML for the *fuel types* alone
and quietly emits 62 rows instead of 250.

One expansion in that table is genuine MOVES behaviour rather than a stale
capture: a single `(sourceTypeID 21, fuelTypeID 1)` `onroadvehicleselection`
becomes all four `(21, f)` pairs in `runspecsourcefueltype`, because
`ExecutionRunSpec` expands each selected source type over every fuel type
`fuelengtechassoc` lists for it (`crates/moves-calculators/src/default_db_setup.rs:2666-2716`,
whose comment records exactly this case: *"the captured execution
`RunSpecSourceFuelType` holds e.g. (21,{1,2,5,9}) for a single (21,1)
selection"*). The month, hour, day and pollutant differences are not
expansions and have no such explanation.

### 0.2 Why only 250 rows, and why no start exhaust

`runspecpollutantprocess` carries 9101 *and* 9102 (start exhaust energy), and
`baserate_2_2020` has 1,664 rows — yet `MOVESOutput` contains **no processID 2
rows at all**.

The mechanism is a join, not a bug. `BaseRateGenerator` emits start-exhaust
rates on the off-network road type (`roadTypeID` 1), because that is where
starts happen; `BaseRateCalculator` then joins its rate tables to
`runSpecRoadType`, which for this run is `{4}`
(`crates/moves-calculators/src/calculators/baseratecalculator/mod.rs:773-781`,
with the reasoning spelled out verbatim at `mod.rs:762-772`). Every
process-2 row is on road type 1, so every process-2 row is discarded, the
calculator's block list comes out empty, and nothing reaches the aggregator.

So the 250 rows are polProcessID 9101 alone:

```
250 = 125 (modelYearID, fuelTypeID) cohorts  x  2 day types
```

and the 125 is **ragged** — 41 model years for fuel 1, 40 for fuel 2, 23 for
fuel 5 and 21 for fuel 9, not a rectangle. §2.4 gives the rule that decides
membership. This is the same shape as `nr-logging-county`'s 36 ragged
`(SCC, modelYearID)` pairs, and it is handled the same way: a flat row
relation with the key as columns (`docs/esm-conventions.md` §2, finding F14).

---

## 1. Input inventory

### 1.1 How the set was determined

Four independent sources, cross-checked. This matters because the snapshot ships
**369 tables, 235 of them non-empty**, and 21 of those non-empty tables are
NONROAD tables left over from the un-split scenario and are read by nothing in
this chain.

1. **`execution-trace.json`** lists the 182 Java classes the run actually
   loaded. The generator/calculator set is exactly:
   `MeteorologyGenerator`, `SourceBinDistributionGenerator`,
   `TotalActivityGenerator`, `SourceTypePhysics`, `FuelEffectsGenerator`,
   `RatesOperatingModeDistributionGenerator`,
   `StartOperatingModeDistributionGenerator`, `BaseRateGenerator`,
   `BaseRateByAgeHelper`, `BaseRateCalculator`, `TOGSpeciationCalculator`.
   Note what is *absent*: `CriteriaRunningCalculator` and
   `OperatingModeDistributionGenerator`. The trace's `sql_files` and
   `go_calculators` arrays are empty, so there is no SQL-level evidence for
   this fixture and the Rust port is the only executable reference.
2. **`INPUT_TABLES`**, declared per generator/calculator in `../moves.rs`:
   `totalactivitygenerator/mod.rs:2919-2957` (36 entries),
   `source_bin_distribution_generator.rs:1678-1692` (12),
   `baserategenerator/mod.rs:84-115` (22),
   `baseratecalculator/mod.rs:78-123` (35).
3. **Row counts.** A declared table with zero rows carries nothing.
   `generalfuelratio` and `criteriaratio` are both **empty**, which is what
   makes the two fuel-effect steps of §2.3(e) provable no-ops rather than
   assumed ones.
4. **Numerical verification.** Every table in §1.2 appears in the §6.5 oracle,
   which reproduces all 82 rows of `sho` to 4.14 × 10⁻⁶ and all 250 rows of
   `emissionQuant` to 8.23 × 10⁻⁶. A table that could be dropped from the
   oracle without changing its answer is not in §1.2.

### 1.2 Tables that carry data into the calculation

**Run scope (8).** Pure filters; each is a one- or two-row relation here.

| table | rows | what is read |
|---|---|---|
| `runspecyear` | 1 | `yearID` = 2020 |
| `runspecmonth` | 1 | `monthID` = 8 |
| `runspechour` | 1 | `hourID` = 9 |
| `runspecday` | 2 | `dayID` ∈ {2, 5} |
| `runspechourday` | 2 | `hourDayID` ∈ {92, 95} |
| `runspecsourcetype` | 1 | `sourceTypeID` = 21 |
| `runspecroadtype` | 1 | `roadTypeID` = 4 |
| `runspecpollutantprocess` | 2 | `polProcessID` ∈ {9101, 9102} |

**Activity — VMT to source-hours-operating (14).**

| table | rows | columns read |
|---|---|---|
| `year` | 63 | `yearID`, `isBaseYear` |
| `sourcetypeyear` | 819 | `sourceTypePopulation` |
| `sourcetypeagedistribution` | 33,579 | `ageFraction` |
| `sourcetypeage` | 533 | `relativeMAR` |
| `sourceusetype` | 13 | `HPMSVtypeID` |
| `hpmsvtypeyear` | 315 | `HPMSBaseYearVMT` |
| `roadtypedistribution` | 5 | `roadTypeVMTFraction` |
| `monthvmtfraction` | 1 | `monthVMTFraction` |
| `dayvmtfraction` | 8 | `dayVMTFraction` |
| `hourvmtfraction` | 192 | `hourVMTFraction` |
| `monthofanyyear` | 12 | `noOfDays` |
| `avgspeedbin` | 16 | `avgBinSpeed` |
| `avgspeeddistribution` | 3,072 | `avgSpeedFraction` |
| `zoneroadtype` | 4 | `SHOAllocFactor` |

**Cohort structure and rates (9).**

| table | rows | columns read |
|---|---|---|
| `samplevehiclepopulation` | 6,068 | `stmyFraction` (the sole numeric input to the source-bin distribution) |
| `pollutantprocessmodelyear` | 222 | `modelYearGroupID` |
| `modelyeargroup` | 192 | `shortModYrGroupID` |
| `emissionrate` | 69,200 | `meanBaseRate` |
| `evsalesfraction` | 115 | `evFraction` |
| `fleetavgadjustment` | 11 | `evMultiplier`, `adjustmentCap` |
| `regulatoryclass` | 10 | `fleetAvgGroupID` |
| `fuelusagefraction` | 5 | `usageFraction` |
| `sourcebin` | 125 | the packed-id components (see §2.2) |

**Output stage (4).**

| table | rows | columns read |
|---|---|---|
| `hourday` | 48 | `hourDayID` ↔ (`dayID`, `hourID`) |
| `dayofanyweek` | 2 | `noOfRealDays` |
| `agecategory` | 41 | `ageGroupID` |
| `evefficiency` | 7 | `batteryEfficiency`, `chargingEfficiency` |

**Total: 35 tables carry data.**

### 1.3 Tables declared and read, whose effect on this fixture is measurably zero

These are not "unread". Each is joined, each produces a factor, and each factor
is **exactly 1 or exactly 0** here. They are listed separately because a `.esm`
that omits them is right for this fixture and wrong for the next, and because
each one is a branch worth a test on both arms (§6.6).

| table | rows | why the effect is zero |
|---|---|---|
| `generalfuelratio` | **0** | empty; the general-fuel-ratio step is a passthrough (`adjust.rs:451-474` requires a row) |
| `criteriaratio` | **0** | empty; likewise (`adjust.rs:475-494`) |
| `monthgrouphour` | 1 | `A + h(B + Ch)` at `heatIndex` 66.9 °F evaluates to **−0.0189**, and `clamp(·, 0, 1)` makes the A/C factor exactly 0 (§2.3(d)) |
| `fullacadjustment` | 23 | its contribution is scaled by that zero A/C factor |
| `sourcetypemodelyear` | 533 | `ACPenetrationFraction`, multiplied by the same zero |
| `temperatureadjustment` | 7 | the one 9101 row is fuel 9; its adjustment evaluates to **−0.00419** and is clamped to 0 (§2.3(e)) |
| `zonemonthhour` | 24 | supplies the 66.9 °F `heatIndex`/`temperature` that both clamps above depend on — read, and load-bearing for the *reasoning*, not for the answer |
| `noxhumidityadjust` | 3 | the humidity factor is computed but used only in the pollutant-3 branch (`adjust.rs:127-139`) |
| `imcoverage`, `imfactor` | 0 | `pollutantprocessassoc` says 9101 is `isAffectedByExhaustIM = 'N'` |

Two of these sit **on a clamp boundary**, which is the most fragile place a
number can sit. At `heatIndex` 66.9 the A/C activity term is −0.019; at 67.2 °F
it turns positive and the A/C adjustment — a 14.6 % addition to the base rate
for MY1980 — switches on. Likewise the EV temperature term is negative at
66.9 °F and positive below about 62 °F. A run one hour later or one month over
exercises both. §6.6 asserts both arms.

### 1.4 Non-empty tables that are not inputs to this chain

* **21 NONROAD tables** (`nrbaseyearequippopulation` 62,699 rows,
  `nremissionrate` 55,471, `nrgrowthindex` 50,955, …) — residue of the
  un-split scenario. No onroad generator declares any of them.
* **Evaporative, start, PM, crankcase and speciation tables** —
  `soaktime` (31,738), `startopmode` (31,738), `samplevehicletrip` (37,216),
  `crankcaseemissionratio` (572), `methanethcratio` (280) and so on. Reached by
  processes this RunSpec does not select, or by process 2, which §0.2 shows
  emits nothing.
* **`sbweightedemissionrate` (832 rows) covers polProcessID 9102 only.** This
  is worth stating because it looks exactly like the intermediate the running
  chain would want. It is not: for process 1 the source-bin-weighted rate is
  computed in-process and never persisted (`baserategenerator/mod.rs:291-314`).
* **`ratesopmodedistribution` (18 rows) is roadTypeID 1 / polProcessID 602 and
  9102 only.** Also worth stating for the same reason. For process 1 the
  operating-mode distribution comes from drive cycles instead
  (`baserategenerator/mod.rs:158-160`), and `ratesopmodedistribution` is
  declared, loaded and never consulted.
* **`baserate_1_2020` (250 rows)** is the reference's own intermediate, not an
  input. §7.3 uses it as the pivot that isolated the one uncomputed relation,
  and no document reads it as one — but `fixtures/mixed-onroad.esm` does assert
  eight of its cells as an EXPECTED value (§10.4), which is the opposite
  direction: delete the assertion and no number changes.

### 1.5 The two recurrences that collapse, and why that is luck

`TotalActivityGenerator` contains two year-by-year folds:

* population aging from the base year to the analysis year
  (`totalactivitygenerator/population.rs:115-168`), and
* `HPMSBaseYearVMT × Π VMTGrowthFactor`
  (`totalactivitygenerator/travel.rs:325`).

Both are recurrences of exactly the shape finding **F12** says has no spelling
in this format. Neither has to be evaluated here, because `year` marks **2020
itself as a base year** (`isBaseYear = 'Y'` for every year from 1999 on), so
`determine_base_year` returns 2020, `base_year == analysis_year`, and both
folds are the empty product.

Measured, so this is a fact and not an argument:

```
analysisyearvmt.VMT                    = 2 572 990 000 000
hpmsvtypeyear[25, 2020].HPMSBaseYearVMT = 2 572 988 371 051     ratio 1.000 000 63
sourcetypeagepopulation[2020, 21, a]    = sourcetypeyear[2020, 21].sourceTypePopulation
                                          x sourcetypeagedistribution[21, 2020, a].ageFraction
                                                                  worst ratio 1.000 004
```

(Both ratios are the reference's own 6-significant-figure column storage; see
§7.1.)

**This is a property of the fixture, not of the port.** A run whose analysis
year is not a base year needs both folds and hits F12. The `.esm` must
therefore *say* that it is taking the collapsed form and why, at the point
where a reader would otherwise assume the fold was computed — the rule of
`docs/esm-conventions.md` §15. It must not silently spell the fold as a
one-step product and leave the next fixture to discover it.

---

## 2. The computation chain

```
                        year.isBaseYear -> baseYear = 2020  (S1)
                                  |
  sourcetypeyear x sourcetypeagedistribution ------------> sourceTypeAgePopulation  (S2)
                                  |  x sourcetypeage.relativeMAR, normalised over HPMSVtype
                                  v
                            travelFraction  (S3)
                                  |
  hpmsvtypeyear.HPMSBaseYearVMT -----> analysisYearVMT  (S4)
                                  |  x roadtypedistribution x travelFraction
                                  v
                         annualVMTByAgeRoadway  (S5)
                                  |  x monthVMTFraction x dayVMTFraction x hourVMTFraction
                                  |  / weeksPerMonth
                                  v
                          vmtByAgeRoadwayHour  (S7)
                                  |  / averageSpeed  (S6 = sum avgSpeedFraction x avgBinSpeed)
                                  v
                          shoByAgeRoadwayHour  (S8)
                                  |  x zoneroadtype.SHOAllocFactor
                                  v
                                sho  (S9)  ------------------------------+
                                                                         |
  samplevehiclepopulation.stmyFraction (stmyFraction > 0)                |
        x pollutantprocessmodelyear x modelyeargroup                     |
                                  v                                      |
                sourceBinActivityFraction, sourceBinID  (S10, S11)       |
                                  |  x fuelusagefraction                 |
                                  v                                      |
              sourceBinDistributionFuelUsage  (S12)                      |
                                  |  x emissionrate.meanBaseRate         |
                                  |  x evSalesFactor                     |
                                  v                                      |
                     sbWeightedMeanBaseRate[opModeID]  (S13)             |
                                  |  x W[hourDayID, opModeID]   <== NOT COMPUTED (§8.1)
                                  v                                      |
                     baseRate.meanBaseRate  (S14)                        |
                                  |  x 1 (fuel ratios, temperature, A/C, I/M -- §2.3)
                                  v                                      |
                          meanBaseRate'  (S15)                           |
                                  |                                      |
                                  +---------- x (sho / noOfRealDays) <---+  (S16)
                                  v
                    emissionQuant [kJ]  (S17)
                                  |  / 1 055 055.9
                                  v
                    emissionQuant [Million BTU]  (S18)
```

Steps S1–S9 are `TotalActivityGenerator`; S10–S12 are
`SourceBinDistributionGenerator`; S13–S14 are `BaseRateGenerator`; S15–S17 are
`BaseRateCalculator`; S18 is the engine's output stage.

### 2.1 Activity — VMT to source-hours-operating

Source: `crates/moves-calculators/src/generators/totalactivitygenerator/`.
There is no SQL in the port; the canonical SQL survives as doc comments, and
the arithmetic below is the Rust.

**S1 — base year.** `population.rs:30-35`:
`max(yearID) from year where yearID <= 2020 and isBaseYear in ('Y','y')` = 2020.

**S2 — `sourceTypeAgePopulation`.** `population.rs:73`:

```
population[st, a] = sourcetypeyear[baseYear, st].sourceTypePopulation
                    x sourcetypeagedistribution[st, baseYear, a].ageFraction
```

**S3 — `travelFraction`.** `travel.rs:200-204`, over the four working tables
`travel.rs:40-234` collapses to:

```
travelFraction[st, a] =        population[st, a]  x  relativeMAR[st, a]
                        ------------------------------------------------------
                        SUM over (st', a') with HPMSVtypeID[st'] = HPMSVtypeID[st]
                              of population[st', a'] x relativeMAR[st', a']
```

The denominator runs over **every source type in the HPMS vehicle type**, which
for HPMSVtypeID 25 is source types 21, 31 and 32 — not source type 21 alone.
Getting that wrong scales every row by 1/0.392 = 2.55. `travelFraction`
consequently sums to 0.3923, not to 1.

The renormalisation at `travel.rs:213-231` fires only when VMT is supplied by
source type (`mod.rs:3047-3048`); this run is HPMS-driven, so it does not.

**S4 — `analysisYearVMT`.** `travel.rs:311-325`. With base year = analysis year
this is `hpmsvtypeyear[25, 2020].HPMSBaseYearVMT` (§1.5).

**S5 — `annualVMTByAgeRoadway`.** `vmt.rs:88-96`:

```
annualVMT[rt, a] = analysisYearVMT[HPMSVtypeID[st]] x roadTypeVMTFraction[st, rt]
                   x travelFraction[st, a]
```

This is **national** VMT allocated over road type and age; the county
allocation happens at S9. `roadtypedistribution` is gated to `roadtype`
membership (`vmt.rs:67`).

**S6 — `averageSpeed`.** `activity.rs:147-150`. The **arithmetic** mean, not the
harmonic mean:

```
averageSpeed[rt, st, d, h] = SUM over avgSpeedBinID b of
                               avgSpeedFraction[st, rt, hourDayID(d,h), b] x avgBinSpeed[b]
```

Verified: 66.094076 against the reference's 66.0941 for (4, 21, 2, 9). The
harmonic mean of the same distribution is 49.44, which is 34 % low — and since
SHO is `VMT / averageSpeed`, choosing it would over-emit by the same factor.
`avgspeeddistribution` is keyed by `hourDayID` and carries no month, so one
speed serves every month.

**S7 — `vmtByAgeRoadwayHour`.** `vmt.rs:170-194`:

```
weeksPerMonth[m] = monthofanyyear[m].noOfDays / 7            (vmt.rs:115)

vmt[rt, a, d, h] = annualVMT[rt, a] x monthVMTFraction[st, m]
                   x dayVMTFraction[st, m, rt, d] x hourVMTFraction[st, rt, d, h]
                   / weeksPerMonth[m]
```

`weeksPerMonth` is a **divisor** and it is the only place `monthofanyyear` is
read in the whole generator. For August, 31/7 = 4.428571. A missing month row
silently substitutes 1.0 (`vmt.rs:116`) and SHO comes out 4.43× too large.

The division is what fixes SHO's *basis*: `dayVMTFraction` is a share of the
**month's** VMT, so after `× dayVMTFraction` the quantity covers every real day
of that day type in the month; dividing by weeks-in-month brings it to one
average week — i.e. to the day type's `noOfRealDays` days. S16 divides that out
again. Applying `noOfRealDays` here **and** at S16 is the double-count
`baseratecalculator/mod.rs:1536-1542` records as a ~4.3× over-emit.

**S8 — `shoByAgeRoadwayHour`.** `activity.rs:186-205`:

```
sho[rt, a, d, h] = averageSpeed != 0 ? vmt[rt, a, d, h] / averageSpeed[rt, st, d, h] : 0
```

A `LEFT JOIN`: a missing speed row gives `SHO = 0` with `VMT` intact, which is
the diagnostic signature to look for.

**S9 — `sho`.** `allocation.rs:201`, gated by `runspechourday` at
`allocation.rs:187`:

```
sho[hourDayID, a] = shoByAgeRoadwayHour[4, a, d, h] x zoneroadtype[261610, 4].SHOAllocFactor
```

purely spatial, 0.001645627794 here. The `sho` relation carries **no
`roadTypeID` and no `dayID`** column (`allocation.rs:806-823`) — the road type
is implicit in `linkID` and the day type is packed into `hourDayID`.

The whole of S1–S9 in one line:

```
sho = HPMSBaseYearVMT x roadTypeVMTFraction x travelFraction
      x monthVMTFraction x dayVMTFraction x hourVMTFraction
      / (noOfDays/7) / averageSpeed x SHOAllocFactor
```

### 2.2 Cohort structure — the source-bin distribution

Source: `crates/moves-calculators/src/generators/source_bin_distribution_generator.rs`.

**S10 — model-year window.** `:1219-1227`:
`[min(runspecyear) − max(agecategory.ageID), max(runspecyear)]` = [1980, 2020].
Note the port derives this from the `Year` table where canonical derives it from
`ExecutionRunSpec.years` (`:1808-1815`); for this run the two agree.

**S11 — `sbdgsvp`, and the row-set rule.** `:1336-1394`. The scope filter,
verbatim from `:1337-1341`:

```rust
let in_scope = row.source_type_id == source_type_id
    && row.model_year_id >= year_range.first_model_year_needed
    && row.model_year_id <= year_range.last_model_year_needed
    && fuel_type_ids.contains(&row.fuel_type_id)
    && row.stmy_fraction > 0.0;
```

**`stmyFraction > 0.0` is what makes the output key set ragged**, and it is the
onroad analogue of NONROAD's `modfrc <= 0` skip. Measured on this snapshot:
`samplevehiclepopulation` has **164** rows for source type 21 in the window;
**39** of them carry `stmyFraction` exactly `0.000000000000`; the surviving
**125** are precisely the 125 cohorts of `MOVESOutput`. The 39 are
`(fuel 9, engTech 30)` for model years 1980–1999, `(fuel 5, engTech 1)` for
1980–1997, and `(fuel 2, engTech 1)` for 2020 — i.e. exactly the years before
E85 and electric drive existed, and the year diesel passenger cars stopped.

Dropping the predicate emits 328 rows against the snapshot's 250, and
`require_exact_key_set` is not negotiable. **Reproduce the row suppression** —
the same conclusion `docs/esm-conventions.md` §3 reaches for NONROAD, arrived
at independently on the onroad side.

Two inner joins follow (`:1346-1353`), each of which drops a row on a miss:
`pollutantprocessmodelyear` on `(polProcessID, modelYearID) → modelYearGroupID`,
then `modelyeargroup` on `modelYearGroupID → shortModYrGroupID`.

The `sourceBinID` packing, `:1196-1207`:

```
sourceBinID = 1e18
            + fuelTypeID        x 1e16
            + engTechID         x 1e14
            + regClassID        x 1e12
            + shortModYrGroupID x 1e10
```

`engSizeID` and `weightClassID` own the two remaining decimal slots and are
identically 0 for onroad bins, so their terms are dropped. It is
`shortModYrGroupID` that is packed, not `modelYearGroupID`.

**Note for the `.esm`: this identifier is ~1.01 × 10¹⁸ and exceeds 2⁵³.** A
document must not carry it as a float64 key column — 1.01e18 is representable
only to a multiple of 128, and two bins differing in `shortModYrGroupID`
differ by 1e10, so the *join* is still exact, but any arithmetic on the id is
not. The `.esm` keys on the four components instead and never materialises the
packed id. This is the same hazard finding **F18** records for ten-digit SCCs
under `Float32`, one binary exponent further out.

**S12 — `sourceBinActivityFraction`.** `:1424-1445`. There is **no
normalisation anywhere in the generator** (grepped: zero hits for `normali` in
2,766 lines). The fraction is a bare sum of `stmyFraction` over the group:

```
sourceBinActivityFraction[stmy, polProcessID, sourceBinID]
    = SUM of samplevehiclepopulation.stmyFraction over that group
```

Its sum-to-1 property is *inherited* from the input, and only holds insofar as
every surviving SVP row's fuel type is in `runspecsourcefueltype` and both
inner joins hit. Verified on this snapshot: all 125 values equal their
`samplevehiclepopulation.stmyFraction` exactly, and the per-model-year sums are
1 to 6 significant figures.

Then the fuel-usage rebase (`:1590-1637`):

```
sourceBinDistributionFuelUsage[stmy, pp, usedBin]
    = SUM over equippedBin of usageFraction[equipped -> used] x sourceBinActivityFraction[stmy, pp, equippedBin]
```

Chain B consumes **this** table, not the raw distribution
(`baserategenerator/sbweighted.rs:148-165`, whose comment records that using
the raw one over-weights E85 energy ~50×). On this snapshot the two differ:
`sourcebindistribution` has 250 rows (both polProcessIDs),
`sourcebindistributionfuelusage_1_26161_2020` has 125 (process 1 only), and the
values are not bit-identical.

### 2.3 The base rate

Source: `crates/moves-calculators/src/generators/baserategenerator/` and
`crates/moves-calculators/src/calculators/baseratecalculator/`.

**Flags.** For process 1, Inventory scale, non-Project
(`baserategenerator/mod.rs:239-264`):
`applyAvgSpeedDistribution = true`, `keepOpModeID = false`,
`useAvgSpeedBin = false`, `useAvgSpeedFraction = true`, `useSumSBD = true`,
`useSumSBDRaw = false`.

**(a) S13 — the source-bin-weighted rate.**
`baserategenerator/sbweighted.rs:457-465`:

```rust
fn accumulate(acc: &mut Acc, sbaf: f64, r: &RateRow, ac_factor: f64) {
    acc.mean_base_rate += sbaf * r.mean_base_rate;
    acc.mean_base_rate_ac_adj += sbaf * r.mean_base_rate * (ac_factor - 1.0);
    acc.sum_sbd += sbaf;
}
```

grouped by `(sourceTypeID, polProcessID, modelYearID, fuelTypeID, opModeID,
regClassID)`. Note `meanBaseRateACAdj` is the **incremental** A/C load,
`(fullACAdjustment − 1)`, not the adjusted rate: a missing `fullacadjustment`
row gives factor 1 and contributes exactly 0.

Then the EV-sales ICE back-scaling, `sbweighted.rs:369-405`, applied to the
emitted rate but not to `sumSBD`:

```
evSalesFactor(MY, fuel, regClass) =
    fuel == 9                    ->  1
    otherwise, with g = regulatoryclass[regClass].fleetAvgGroupID,
               e = evsalesfraction[MY, g].evFraction,
               m = fleetavgadjustment[9101, MY in range, g].evMultiplier,
               den = (1 - e) + e*m:
      min( 1 / (1 - e*m/den),  adjustmentCap )        (cap applied only if > 0)
```

This compensates for EV sales removing vehicles from the ICE fleet, and it is
**model-year dependent** — which is why no single operating-mode weight vector
fits the base rates until it is divided out (§7.3).

**(b) S14 — the base rate.** `baserategenerator/aggregate.rs:365-417`.
Substituting this run's flags (`sumSBDRaw → 1`, `useAvgSpeedBin` false):

```
baseRate.meanBaseRate[hourDayID, MY, fuel]
  = SUM over opModeID om and avgSpeedBinID b of
        sbWeightedMeanBaseRate[om] x opModeFraction[om, b] x avgSpeedFraction[b]

baseRate.opModeFraction = SUM of opModeFraction x avgSpeedFraction x sumSBD
```

Only `opModeFraction` carries `sumSBD`; `meanBaseRate` does not. So
`meanBaseRate / opModeFraction` is *not* an activity-weighted mean rate.

The two collapsed key columns: `opModeID = 0` and `avgSpeedBinID = 0` in
`baserate_1_2020` are **not** operating mode zero (which is Braking) and speed
bin zero. They are the `Default` values left when `keepOpModeID` and
`useAvgSpeedBin` are both false and neither `if` fires
(`aggregate.rs:246-261`, `:305-313`). Every operating mode and all sixteen
speed bins have been weighted into `meanBaseRate` and the key collapsed. By
contrast `baserate_2_2020` keeps real `opModeID`s 101–108, because
`keepOpModeID` is `process_id == 2`.

Write the collapsed weight as one relation:

```
W[hourDayID, opModeID] = SUM over avgSpeedBinID b of opModeFraction[om, b] x avgSpeedFraction[b]
```

**`W` was the one relation this port did not compute.** §7.3 measures it, §8.1
records what it took, and §10 is the port. It is computed in
`fixtures/mixed-onroad.esm` and in §6.5's reproduction, and `cohDay_meanBaseRate`
above is asserted against `baserate_1_2020`'s own cells.

**(c) S15 — the calculator's adjustments, in order.**
`baseratecalculator/adjust.rs:317-623`. For polProcessID 9101:

| step | line | effect here |
|---|---|---|
| general fuel ratio, GPA-blended | `:451-474` | `generalfuelratio` is **empty** → passthrough |
| criteria ratio, GPA-blended | `:475-494` | `criteriaratio` is **empty** → passthrough |
| temperature (+ NOx humidity) | `:495-535` | **1.0**, see (e) |
| air conditioning, `+= ACFactor × meanBaseRateACAdj` | `:536-568` | **ACFactor = 0**, see (d) |
| I/M blend | `:569-583` | 9101 is `isAffectedByExhaustIM = 'N'` → no coverage row |
| `emissionRateAdjustment` | `:584-603` | flag false in production |
| EV efficiency divisor | `:611-616` | see (f) — and see the divergence note |

So for this fixture `meanBaseRate' = baseRate.meanBaseRate`, except for the EV
divisor of (f). That is an empirical result, verified to 8.23 × 10⁻⁶ over all
250 rows, and (d) and (e) are why.

**(d) The A/C factor is exactly zero, by a clamp.**
`baseratecalculator/setup.rs:409-411`, porting the canonical cache query:

```
ACFactor[hour, sourceType, MY]
  = clamp( ACActivityTermA + heatIndex x (ACActivityTermB + ACActivityTermC x heatIndex), 0, 1 )
    x sourcetypemodelyear.ACPenetrationFraction
    x sourcetypeage[sourceType, year - MY].functioningACFraction
```

With `monthgrouphour[monthGroupID 8, hourID 9]` = (A −3.63154, B 0.072465,
C −0.000276) and `zonemonthhour[8, 261610, 9].heatIndex` = 66.900001525879:

```
-3.63154 + 66.9 x (0.072465 - 0.000276 x 66.9)
  = -3.63154 + 66.9 x 0.0540006
  = -3.63154 + 3.61264
  = -0.01890        ->  clamp to 0  ->  ACFactor = 0
```

`meanBaseRateACAdj` is genuinely large — 56,676.3 against a `meanBaseRate` of
387,171 for MY1980/fuel 1, a 14.6 % addition — so this is a clamp doing real
work, not an absent table. Nineteen hundredths of one unit the other way and
every one of the 250 rows changes.

**(e) The temperature adjustment is exactly zero, by a second clamp.**
`temperatureadjustment` has exactly one 9101 row and it is `fuelTypeID 9`
(termA 0.00225, termB 0.00028). For fuels 1, 2 and 5 there is no row, the
lookup `unwrap_or_default()`s to all-zero terms (`adjust.rs:515`), and the
standard quadratic `1 + (T−75)(a + b(T−75))` is exactly 1.

For fuel 9 the dedicated EV branch runs (`adjust.rs:107-124`):

```
adj = (T - 72) x (termA + termB x (T - 72));   if adj < 0 { adj = 0 }
if sourceTypeID < 40 && heatIndex > 67.0 { adj = 0 }
factor = 1 + adj
```

At T = 66.900001525879: `(−5.1)(0.00225 + 0.00028 × (−5.1)) = (−5.1)(0.000822)
= −0.004192` → clamped to 0 → factor 1.

**Both clamps, and the `heatIndex > 67.0` suppression, are within 0.1 °F of
their boundary at 66.9 °F.** The suppression does *not* fire (66.9 < 67.0), so
the EV branch is live and returns 1 only because of its own `adj < 0` clamp.
This is the most precision-sensitive fact in the fixture and §7.2 quantifies it.

**(f) The EV efficiency divisor.**
`baseratecalculator/adjust.rs:689-708`:

```
divisor = evefficiency.batteryEfficiency x evefficiency.chargingEfficiency
meanBaseRate' = meanBaseRate / divisor
```

keyed `(polProcessID, sourceTypeID, regClassID, fuelTypeID = 9, modelYearID)`,
where the `evefficiency` row is selected by
`agecategory[2020 − modelYearID].ageGroupID` (`setup.rs:3229-3235`) — the table
has no `fuelTypeID` column and 9 is forced (`setup.rs:3221`).

Measured, and this is how the divisor was identified: `emissionQuant` for the
42 fuel-9 rows is short by exactly the seven age-group products.

| ageGroupID | ages | batteryEff | × chargingEff 0.94 | model years | measured ratio |
|---|---|---|---|---|---|
| 3 | 0–3 | 0.95 | **0.893000** | 2017–2020 | 0.893000 |
| 405 | 4–5 | 0.903153432 | **0.848964226** | 2015–2016 | 0.848964 |
| 607 | 6–7 | 0.874407474 | **0.821943026** | 2013–2014 | 0.821941 |
| 809 | 8–9 | 0.847434948 | **0.796588851** | 2011–2012 | 0.796589 |
| 1014 | 10–14 | 0.828272877 | **0.778576504** | 2006–2010 | 0.778576 |
| 1519 | 15–19 | 0.828272877 | 0.778576504 | 2001–2005 | 0.778576 |
| 2099 | 20+ | 0.828272877 | 0.778576504 | 2000 | 0.778578 |

> **A divergence in `moves.rs`, recorded because the `.esm` must not copy it.**
> `ModuleFlags::ev_efficiency` is `false` on `moves.rs`'s production path
> (`baseratecalculator/mod.rs:798-802` sets only `apply_activity`; `true`
> appears solely in `tests/baseratecalculator.rs:467`), so `moves.rs` loads and
> expands `evefficiency` and never applies it. Canonical MOVES *did* apply it —
> the table above is measured off the snapshot's own `MOVESOutput` — and without
> it the 42 fuel-9 rows are 10.7 % to 22.1 % low. `model.rs:55-56` records that
> the Java "always run[s] evefficiency section". **The `.esm` follows canonical,
> not `moves.rs`.** This is why §1.1 cross-checks the Rust against the snapshot
> instead of trusting it.

### 2.4 Activity weighting, and the output row

**S16 — the activity multiply.** `baseratecalculator/aggregate.rs:223-231` and
`mod.rs:1602-1608`:

```
universalActivity[hourDayID, MY, sourceTypeID] = sho.SHO / dayofanyweek[dayID].noOfRealDays

emissionQuant [kJ] = meanBaseRate' x universalActivity
```

with `dayID` reached through `hourday[hourDayID].dayID`, and `noOfRealDays` = 2
for the weekend type and 5 for the weekday type. A missing divisor is a **hard
error** in the port, not a 1.0 (`mod.rs:1584-1590`), for the reason §2.1(S7)
gives.

`outputtimestep` is `Hour`, so the aggregator's temporal scaling is
`PortionOfWeekPerDay`, which is deliberately the identity
(`crates/moves-framework/src/aggregation/output_aggregate.rs:213-217`: the
`1/noOfRealDays` already happened inside the calculator). **There is no
weeks-in-month factor on the output for an `Hour` timestep** — that multiplier
(`output_aggregate.rs:203`) applies to `Month` and `Portion` timesteps only.

**S18 — energy units.** The only unit conversion in the chain.
`crates/moves-runspec/src/model.rs:546-565`:

```
joules_per_unit(MillionBtu) = 1055.0559 x 1e6
factor_from_kilojoules      = 1000 / joules_per_unit  =  9.478171e-7
```

applied to pollutants 91, 92 and 93 only
(`crates/moves-framework/src/execution/engine.rs:1286-1310`), *after* the
group-by sum. Equivalently, divide kilojoules by **1 055 055.9**.

Checked against the snapshot's own intermediates, which capture both sides of
this step: `unitconvertafter` = `movesoutput` = 0.895519 and
`finalaggbefore` = `temporaryoutputimport` = `output_tbl` = 944823 for
MY1980 / fuel 1 / day 2. 944823 / 0.895519 = 1 055 055.85. (`MassUnit` is
parsed and recorded but never applied anywhere in the tree.)

**The SCC is computed, not looked up.**
`crates/moves-framework/src/execution/engine.rs:1450-1477`:

```
roadTypeID != 100:  SCC = "22" ++ fuel:02 ++ src:02 ++ road:02 ++ proc:02
roadTypeID == 100:  SCC = "22" ++ fuel:02 ++ (src+1):02 ++ "00" ++ proc:02
```

As arithmetic, for the on-road branch:

```
SCC = 22 x 1e8 + fuelTypeID x 1e6 + sourceTypeID x 1e4 + roadTypeID x 1e2 + processID
```

Check: `22e8 + 1e6 + 21e4 + 4e2 + 1 = 2201210401`. The four SCCs in this
fixture are 2201210401 (gasoline), 2202210401 (diesel), 2205210401 (E85) and
2209210401 (electricity). The `scc` table (14,976 rows) agrees with the
formula on all four and is not read by the chain.

**The output group-by.** `crates/moves-framework/src/aggregation/plan.rs:258-286`.
For this RunSpec — `Hour` timestep, `COUNTY` detail, and a breakdown selecting
`modelyear`, `fueltype`, `emissionprocess`, `roadtype`, `onroadscc` but *not*
`sourceusetype` — the key columns are:

```
MOVESRunID, iterationID, yearID, monthID, dayID, hourID, stateID, countyID,
pollutantID, roadTypeID, processID, sourceTypeID, fuelTypeID, modelYearID, SCC
```

and `zoneID`, `linkID`, `regClassID`, `fuelSubTypeID`, `engTechID`, `sectorID`,
`hpID`, `emissionQuantMean`, `emissionQuantSigma` are NULL in every row.
`sourceTypeID` appears with a single value because the run has one source type,
even though the breakdown flag is off. `avgSpeedBinID`, `fuelFormulationID`,
`hourDayID`, `polProcessID` and `ageID` are not `MOVESOutput` columns at all
and are summed away here.

A group with no non-NULL metric emits `emissionQuant = None`, never `0.0`
(`output_aggregate.rs:471`).

---

## 3. Join structure

Every equality below is a `join.on` clause with the listed key pairs
(`docs/esm-conventions.md` §3). Where a step is not an equi-join it is marked,
with the spelling that replaces it.

| | step | left | right | key pairs |
|---|---|---|---|---|
| J1 | S1 | `year` | `runspecyear` | *not an equi-join*: `yearID <= runYearID`, then a `max`. A `filter` plus a reduction |
| J2 | S2 | `sourcetypeyear` | `sourcetypeagedistribution` | `(sourceTypeID, sourceTypeID)`, `(yearID, yearID)` — one clause, two pairs |
| J3 | S3 | `sourceTypeAgePopulation` | `sourcetypeage` | `(sourceTypeID, sourceTypeID)`, `(ageID, ageID)` |
| J4 | S3 | `sourceTypeAgePopulation` | `sourceusetype` | `(sourceTypeID, sourceTypeID)` — supplies `HPMSVtypeID` for the normalisation group |
| J5 | S3 | the numerator relation | the denominator relation | `(HPMSVtypeID, HPMSVtypeID)`. **A second relation over a second index set**, not a self-join (finding F11) |
| J6 | S4 | `hpmsvtypeyear` | `sourceusetype` ⋈ `runspecsourcetype` | `(HPMSVtypeID, HPMSVtypeID)`, `(yearID, baseYearID)` |
| J7 | S5 | `analysisYearVMT` | `roadtypedistribution` | `(HPMSVtypeID via sourceusetype, —)`, `(—, sourceTypeID)`; then `roadtypedistribution` ⋈ `roadtype` on `(roadTypeID, roadTypeID)` |
| J8 | S5 | that product | `travelFraction` | `(sourceTypeID, sourceTypeID)`, `(yearID, yearID)` |
| J9 | S6 | `avgspeeddistribution` | `avgspeedbin` | `(avgSpeedBinID, avgSpeedBinID)` |
| J10 | S6 | `avgspeeddistribution` | `hourday` | `(hourDayID, hourDayID)`; then ⋈ `runspecday` on `(dayID, dayID)` and ⋈ `runspechour` on `(hourID, hourID)` |
| J11 | S7 | `annualVMTByAgeRoadway` | `monthvmtfraction` | `(sourceTypeID, sourceTypeID)` |
| J12 | S7 | ″ | `dayvmtfraction` | `(sourceTypeID, sourceTypeID)`, `(monthID, monthID)`, `(roadTypeID, roadTypeID)` |
| J13 | S7 | ″ | `hourvmtfraction` | `(sourceTypeID, sourceTypeID)`, `(roadTypeID, roadTypeID)`, `(dayID, dayID)`, `(hourID, hourID)` — four pairs, one clause |
| J14 | S7 | ″ | `monthofanyyear` | `(monthID, monthID)` |
| J15 | S8 | `vmtByAgeRoadwayHour` | `averageSpeed` | `(roadTypeID, roadTypeID)`, `(sourceTypeID, sourceTypeID)`, `(dayID, dayID)`, `(hourID, hourID)`. Note: **no `monthID`, no `ageID`** |
| J16 | S9 | `shoByAgeRoadwayHour` | `zoneroadtype` ⋈ `link` | `(roadTypeID, roadTypeID)`; `link`/`zoneroadtype` filtered to `zoneID` |
| J17 | S9 | ″ | `runspechourday` | `(hourDayID, hourDayID)` |
| J18 | S11 | `samplevehiclepopulation` | `pollutantprocessmodelyear` | `(modelYearID, modelYearID)`, `(runPolProcessID, polProcessID)` |
| J19 | S11 | ″ | `modelyeargroup` | `(modelYearGroupID, modelYearGroupID)` |
| J20 | S11 | ″ | `runspecsourcefueltype` | `(sourceTypeID, sourceTypeID)`, `(fuelTypeID, fuelTypeID)` |
| J21 | S12 | `sourceBinActivityFraction` | `fuelusagefraction` | `(fuelTypeID, sourceBinFuelTypeID)`, `(modelYearGroupID, modelYearGroupID)`, `(countyID, countyID)`, `(fuelYearID, fuelYearID)` |
| J22 | S13 | `sourceBinDistributionFuelUsage` | `emissionrate` | `(fuelTypeID, —)`, `(engTechID, —)`, `(regClassID, —)`, `(shortModYrGroupID, —)` against the same four components of `emissionrate.sourceBinID`, plus `(polProcessID, polProcessID)`. **Keyed on the components, never on the packed id** (§2.2) |
| J23 | S13 | ″ | `fullacadjustment` | `(sourceTypeID, sourceTypeID)`, `(polProcessID, polProcessID)`, `(opModeID, opModeID)`. A `LEFT JOIN`: a miss is factor 1, contribution 0 |
| J24 | S13 | ″ | `evsalesfraction` ⋈ `regulatoryclass` | `(modelYearID, modelYearID)`, `(fleetAvgGroupID, fleetAvgGroupID)` |
| J25 | S13 | ″ | `fleetavgadjustment` | *not an equi-join*: `beginModelYearID <= MY <= endModelYearID` on `(polProcessID, fleetAvgGroupID)`. A two-pair `join.on` plus a range `filter` |
| J26 | S14 | `sbWeightedMeanBaseRate` | `W` | `(opModeID, opModeID)`, `(hourDayID, hourDayID)` |
| J27 | S15 | `baseRate` | `runspecroadtype` | `(roadTypeID, roadTypeID)`. **This is the join that suppresses every process-2 row** (§0.2) |
| J28 | S15 | ″ | `zonemonthhour` | `(zoneID, zoneID)`, `(monthID, monthID)`, `(hourID, hourID)` |
| J29 | S15 | ″ | `monthgrouphour` | `(monthGroupID via monthofanyyear, monthGroupID)`, `(hourID, hourID)` |
| J30 | S15 | ″ | `sourcetypemodelyear` | `(sourceTypeModelYearID, sourceTypeModelYearID)` |
| J31 | S15 | ″ | `sourcetypeage` | `(sourceTypeID, sourceTypeID)`, `(ageID, ageID)` with `ageID = yearID − modelYearID` |
| J32 | S15 | ″ | `temperatureadjustment` | *not an equi-join*: `minModelYearID <= MY <= maxModelYearID` on `(polProcessID, fuelTypeID, regClassID)`. Three pairs plus a range `filter` |
| J33 | S15 | ″ | `evefficiency` ⋈ `agecategory` | `(polProcessID, polProcessID)`, `(sourceTypeID, sourceTypeID)`, `(regClassID, regClassID)`, `(ageGroupID, ageGroupID)` with `ageID = yearID − modelYearID`; `fuelTypeID` is forced to 9 |
| J34 | S16 | `meanBaseRate'` | `sho` | `(hourDayID, hourDayID)`, `(ageID, ageID)` with `ageID = yearID − modelYearID` |
| J35 | S16 | ″ | `hourday` ⋈ `dayofanyweek` | `(hourDayID, hourDayID)`, then `(dayID, dayID)` |

**Three steps are not equi-joins**, and each gets the §3 treatment:

| case | spelling |
|---|---|
| J1's `yearID <= runYearID` then `max` | a `filter` plus a reduction — a genuine range predicate |
| J25 / J32's `beginModelYearID <= MY <= endModelYearID` | a `join.on` over the non-range keys plus an inclusive-range `filter`. Structurally identical to NONROAD's `hpMin <= hpAvg <= hpMax` |
| J5's numerator-against-denominator | two relations over two index sets, per finding F11 |

**Note what is absent from this list:** there is no SCC fallback ladder, no
state-default precedence and no rounded join key. All three of those were the
awkward parts of NONROAD, and the onroad chain has none of them. What it has
instead is one join on a **packed identifier above 2⁵³** (J22) and two joins on
an **inclusive model-year range** (J25, J32).

---

## 4. Reusable shapes (`expression_templates`)

Five shapes are used more than once and belong in `lib/`. Three of the six
existing libraries are reused unchanged.

### 4.1 `weeks_per_month` (new)

```
weeks_per_month(days_in_month) = days_in_month / 7
```

`vmt.rs:115`. One use, but it is a named MOVES concept
(`WeeksInMonthHelper`) whose absence silently multiplies the answer by 4.43,
so it is named rather than written inline. Compare `lib/conversion.esm`'s
`temporal_scale`, which carries the same `7 /ndays` pair for NONROAD — the two
are *not* the same shape and must not be merged: NONROAD's is
`mthf × 7 × dayf / ndays` and this one is a bare divisor.

### 4.2 `share_of_group` (new)

```
share_of_group(numerator, group_total) = group_total != 0 ? numerator / group_total : 0
```

Three uses: `travelFraction` (S3), `fractionWithinHPMSVType`, and the
`sourceBinActivityFraction` sum-to-1 check. The zero guard is
`travel.rs:99-103` and `travel.rs:200-204`, and it is the difference between a
missing group and a NaN.

### 4.3 `onroad_scc` (new)

```
onroad_scc(fuel_type_id, source_type_id, road_type_id, process_id)
  = 22 x 1e8 + fuel x 1e6 + source x 1e4 + road x 1e2 + process
```

`engine.rs:1450-1477`, the non-off-network branch. Sits beside
`lib/identifiers.esm`'s `pol_process_id` and `scc_zero_tail`: the third
identifier in this port that is built rather than written. The `roadTypeID 100`
branch is a separate template because it is a different formula, not a
parameterisation of this one.

### 4.4 `source_bin_slot` (new)

Not an arithmetic template but a documented decomposition, because the packed
id must never be materialised (§2.2):

```
source_bin_slot(bin, slot_scale) = floor(bin / slot_scale) mod 100

  with slot_scale 1e16 for fuelTypeID, 1e14 for engTechID,
                  1e12 for regClassID, 1e10 for shortModYrGroupID
```

One parameterised template rather than four, with the four slot exponents in
the calling component's `enums` under `source_bin_slot` — which is what keeps
the decimal layout in one place and readable against `:1196-1207`.

These are the **inverse** direction, for reading `emissionrate.sourceBinID`,
whose 69,200 rows arrive with the id already packed and no component columns.
`floor(bin/1e16)` on a float64 whose value is 1.01e18 is exact — the quotient
is small — which is what makes the inverse safe where the forward packing is
not.

### 4.5 `ev_energy_divisor` (new)

```
ev_energy_divisor(battery_efficiency, charging_efficiency, is_electric)
  = is_electric > 0 ? battery_efficiency x charging_efficiency : 1
```

`adjust.rs:689-708`, with the zero-divisor guard. One use, named because §2.3(f)
shows it is the single largest correction in the fixture (up to 22 %) and the
one `moves.rs` omits.

### 4.6 Two constants that are templates

`days_per_week` (7.0, which `weeks_per_month` divides by) and
`kilojoules_per_million_btu` (`1055.0559e6 / 1000`, §5.6). Zero-parameter
constant fragments, per `docs/esm-conventions.md` §6: the second is imported by
both the output component and the assembly's roll-up, and a port with two
copies of an eight-figure conversion constant has two chances to disagree with
itself.

### 4.7 Reused unchanged

| library | shapes used |
|---|---|
| `lib/identifiers.esm` | `pol_process_id` (9101 = 100 × 91 + 1), `null_output_column` (the nine NULL `MOVESOutput` columns) |
| `lib/keys.esm` | `latest_at_or_before_key` — the same year-precedence shape J25/J32 need |
| `lib/population.esm` | `linear_series_interpolation` is *not* needed; nothing here interpolates |

### 4.8 Shapes deliberately not factored

`clamp(x, 0, 1)` appears twice (§2.3(d), §2.3(e)) but with different bodies
either side of it, and `min`/`max` are core operators; a `clamp01` template
would hide which clamp is which. The two are written out, each next to the
constants it clamps, because §2.3 shows the *value* of each clamp is the
load-bearing fact.

---

## 5. Literals and enums

Values here are the inventory of every literal the chain depends on. Per
`docs/esm-conventions.md` §4, no magic integer appears in an expression.

### 5.1 Pollutants and processes

| symbol | value | source |
|---|---|---|
| `pollutant.TotalEnergyConsumption` | 91 | `runspecpollutantprocess`, `pollutantprocessassoc` |
| `pollutant.FossilFuelEnergyConsumption` | 93 | in the XML, **not** in the captured run (§0.1) |
| `process.RunningExhaust` | 1 | `pollutantprocessassoc` |
| `process.StartExhaust` | 2 | ″ |
| `polProcessID` 9101 | `100 × 91 + 1` | built with `pol_process_id` |

`ENERGY_POLLUTANT_IDS` = {91, 92, 93} is the set the unit conversion touches
(`engine.rs:1286`).

### 5.2 Geography, time and vehicles

| symbol | value | note |
|---|---|---|
| `county.WashtenawMI` | 26161 | |
| `state.Michigan` | 26 | `county.stateID` |
| `zone.WashtenawMI` | 261610 | `county × 10` |
| `link.WashtenawUrbanRestricted` | 2616104 | `county × 100 + roadTypeID` |
| `month.August` | 8 | `runspecmonth` |
| `hour.NineAM` | 9 | `runspechour`; MOVES `hourID` is 1-based |
| `day_type.Weekend` | 2 | `dayofanyweek`, `noOfRealDays` 2 |
| `day_type.Weekday` | 5 | `dayofanyweek`, `noOfRealDays` 5 |
| `hourDayID` 92, 95 | `hourID × 10 + dayID` | `hourday` |
| `source_type.PassengerCar` | 21 | |
| `hpms_vtype.LightDutyVehicles` | 25 | `sourceusetype[21].HPMSVtypeID` |
| `road_type.UrbanRestrictedAccess` | 4 | |
| `road_type.OffNetwork` | 1 | where process 2's rates live (§0.2) |
| `road_type.Total` | 100 | the `onroad_scc` alternate branch |
| `reg_class.LightDutyVehicles` | 20 | |
| `fleet_avg_group.LightDuty` | 1 | `regulatoryclass[20].fleetAvgGroupID` |
| `base_year.NineteenNinety` | 1990 | the `year` table's first base year; not used here |

### 5.3 Fuel types and engine technologies

| symbol | value | SCC | cohorts |
|---|---|---|---|
| `fuel_type.Gasoline` | 1 | 2201210401 | 41 (MY 1980–2020) |
| `fuel_type.DieselFuel` | 2 | 2202210401 | 40 (MY 1980–2019) |
| `fuel_type.EthanolE85` | 5 | 2205210401 | 23 (MY 1998–2020) |
| `fuel_type.Electricity` | 9 | 2209210401 | 21 (MY 2000–2020) |

| symbol | value | note |
|---|---|---|
| `engine_tech.ConventionalInternalCombustion` | 1 | fuels 1, 2, 5 |
| `engine_tech.ElectricDrive` | 30 | fuel 9 |

Note the asymmetry with NONROAD: there, engine technology needed its own axis
over the 100–199 code space for performance (finding F17). Here it takes two
values and is a column.

### 5.4 Age groups

`agecategory` maps `ageID` → `ageGroupID`, and `evefficiency` is keyed on the
group:

| `ageGroupID` | ages | symbol |
|---|---|---|
| 3 | 0–3 | `age_group.ZeroToThree` |
| 405 | 4–5 | `age_group.FourToFive` |
| 607 | 6–7 | `age_group.SixToSeven` |
| 809 | 8–9 | `age_group.EightToNine` |
| 1014 | 10–14 | `age_group.TenToFourteen` |
| 1519 | 15–19 | `age_group.FifteenToNineteen` |
| 2099 | 20+ | `age_group.TwentyPlus` |

### 5.5 Operating modes

23 modes carry a 9101 rate (`opmodepolprocassoc`, `emissionrate`):
0 (Braking), 1 (Idling), 11–16, 21–25, 27–30, 33, 35, 37–40. Mode 501 exists in
`opmodepolprocassoc` but is brakewear and carries no 9101 rate.

`opModeID 0` in `baserate_1_2020` is **not** mode 0. See §2.3(b).

Mode 0 is also the one identifier in this port that cannot be an `enums` member:
the schema requires a positive integer, so `fixtures/mixed-onroad.esm` carries
the Braking mode as a literal `0.0` with a comment. `docs/findings/README.md`
F32.

`sourceusetypephysicsmapping` carries `opModeIDOffset = 1000`, which is how
`SourceTypePhysics`'s row-correction pass (`sourcetypephysics.rs:320-390`)
relabels a temporary source type's normal operating modes. **It does not reach
this chain**, and the evidence is the answer rather than an argument: that pass
rewrites tables keyed by `(sourceTypeID, opModeID)`, `emissionrate` is keyed by
a packed source bin and carries no source type, and
`fixtures/mixed-onroad.esm` reproduces all 250 rows to 8.320 × 10⁻⁶ applying no
offset anywhere. `fixtures/mixed-onroad.esm` therefore does not read the
column at all — it projects six of `sourceusetypephysicsmapping`'s eleven,
and this is the one whose absence is worth naming. A run with a temporary source
type in play would need both it and the correction pass;
`run_physicsRowsSelected` is the assertion that says this run has one mapping row
and no remapping to do.

### 5.6 Physical and dimensioning constants

| constant | value | source |
|---|---|---|
| kilojoules per Million BTU | **1 055 055.9** = `1055.0559 × 1e6 / 1000` | `moves-runspec/src/model.rs:553` |
| ″, measured off the snapshot | 1 055 055.85 | `944823 / 0.895519` |
| days per week | 7 | `weeks_per_month` |
| `monthofanyyear[8].noOfDays` | 31 | → `weeksPerMonth` 4.428571 |
| `zoneroadtype[261610, 4].SHOAllocFactor` | 0.001645627794 | |
| `zonemonthhour[8, 261610, 9].heatIndex` | 66.900001525879 | = `temperature` |
| max `agecategory.ageID` | 40 | sets the 41-year model-year window |
| `sourceBinID` marker | 1 × 10¹⁸ | §2.2 |

The two conversion constants differ in the eighth significant figure. The
snapshot cannot distinguish them (6 significant figures stored), and the
difference is 4.7 × 10⁻⁸ relative — five orders inside the 10⁻³ gate. The
`.esm` uses `1055.0559e6 / 1000`, the port's own value, so that a disagreement
with `moves.rs` is never this.

---

## 6. Hand-checkable worked examples

Every number below is computed by the §6.5 oracle from the snapshot's own
tables, at full binary64 precision, and printed against the reference value.

### 6.0 Run-level values used by every example

```
baseYear                                = 2020            (= analysis year; §1.5)
analysisYearVMT[25]                     = 2 572 988 371 051
roadTypeVMTFraction[21, 4]              = 0.259544
monthVMTFraction[21, 8]                 = 0.0934297
weeksPerMonth[8]                        = 4.428571428571   (31/7)
SHOAllocFactor[261610, 4]               = 0.001645627794
heatIndex[8, 261610, 9]                 = 66.900001525879
ACFactor                                = 0               (clamped; §2.3(d))
kJ per Million BTU                      = 1 055 055.9

                                          dayID 2          dayID 5
dayVMTFraction[21, 8, 4, d]               0.237635         0.762365
hourVMTFraction[21, 4, d, 9]              0.0363852        0.0608279
averageSpeed[4, 21, d, 9]                 66.094075550     48.185058000
noOfRealDays[d]                           2                5
hourDayID                                 92               95
```

### 6.1 Worked example A — MY 1980, gasoline, weekend

The oldest cohort, the largest single `emissionQuant`, and the row that shows
every factor at once.

```
travelFraction[21, 40]  = pop[21,40] x relativeMAR[21,40] / SUM over (21,31,32) x ages
                        = 1.609174853309e-03
annualVMT[4, 21, 40]    = 2 572 988 371 051 x 0.259544 x 1.609174853309e-03
                        = 1.074612910971e+09        (reference 1.074610000e+09, 2.7e-6)

vmtByAgeRoadwayHour     = 1.074612910971e+09 x 0.0934297 x 0.237635 x 0.0363852 / 4.428571429
                        = 1.960236750361e+05        (reference 1.960236717e+05, 1.7e-8)

shoByAgeRoadwayHour     = 1.960236750361e+05 / 66.094075550
                        = 2.965828229003e+03        (reference 2.965828066e+03, 5.5e-8)

sho[92, 40]             = 2.965828229003e+03 x 0.001645627794
                        = 4.880649365878            (reference 4.880650000,     1.3e-7)

sourceBinActivityFraction[211980, fuel 1] = 0.953329
evSalesFactor(1980, 1, 20)                = 1                (evFraction 0 in 1980)
meanBaseRate[92, 1980, 1]                 = 3.871710e+05 kJ/hr    <== S14; §10
ACFactor x meanBaseRateACAdj              = 0 x 56 676.3 = 0
temperature factor                        = 1
evEfficiency divisor                      = 1                (fuel != 9)

universalActivity       = 4.880649365878 / 2 = 2.440324682939 h

emissionQuant [kJ]      = 3.871710e+05 x 2.440324682939
                        = 9.448229478e+05           (reference 944 823,          4.1e-7)

emissionQuant [MMBTU]   = 9.448229478e+05 / 1 055 055.9
                        = 0.895519367831            (MOVESOutput 0.895519,       4.1e-7)

SCC = 22e8 + 1e6 + 21e4 + 4e2 + 1 = 2201210401
```

Every intermediate is checkable against a snapshot table: `annualvmtbyageroadway`,
`vmtbyageroadwayhour`, `shobyageroadwayhour`, `sho`, `output_tbl` and
`movesoutput` respectively. This is the row to put in a `.esm` test first,
because a wrong factor anywhere shows up at a named stage.

### 6.2 Worked example B — MY 2020, gasoline, weekday

The newest cohort and the other day type; the largest `sho`.

```
travelFraction[21, 0]   = 1.804420293236e-02
annualVMT[4, 21, 0]     = 1.204998536947e+10
vmtByAgeRoadwayHour     = 1.178890839798e+07     (x 0.762365 x 0.0608279 / 4.428571429)
shoByAgeRoadwayHour     = 2.446590060757e+05     (/ 48.185058)
sho[95, 0]              = 402.617660450525       (reference 402.618000,  8.4e-7)

sourceBinActivityFraction[212020, fuel 1] = 0.940774
meanBaseRate[95, 2020, 1]                 = 1.552680e+05
universalActivity                         = 402.617660450525 / 5 = 80.523532090105

emissionQuant [MMBTU]   = 1.552680e+05 x 80.523532090105 / 1 055 055.9
                        = 11.850299470465        (MOVESOutput 11.850300, 4.5e-8)
```

Note `sourceBinActivityFraction` is 0.9408 rather than 1 even in 2020: the
remaining 0.0592 is spread over diesel is 0 (no MY2020 diesel car), E85 and
electric — which is what makes MY2020 a **three**-cohort model year while 1980
is a two-cohort one.

### 6.3 Worked example C — MY 2000, electricity, weekday

The row that exercises the EV efficiency divisor at its largest, and the
smallest `sourceBinActivityFraction` in the fixture.

```
sho[95, 20]                               = 129.467988377611  (reference 129.468000, 9.0e-8)
sourceBinActivityFraction[212000, fuel 9] = 3.15303e-04
meanBaseRate[95, 2000, 9]                 = 15.75310
agecategory[20].ageGroupID                = 2099
evefficiency[9101, 21, 20, 2099]          = 0.828272877 x 0.94 = 0.778576504380

universalActivity       = 129.467988377611 / 5 = 25.893597675522
meanBaseRate'           = 15.75310 / 0.778576504380 = 20.233795...

emissionQuant [MMBTU]   = 20.233795 x 25.893597675522 / 1 055 055.9
                        = 4.965713765e-04        (MOVESOutput 4.96572e-04, 1.3e-6)
```

Without the divisor this is 3.866e-04, **22.1 % low**. This single row is the
reason §2.3(f) records the `moves.rs` divergence.

### 6.4 Worked example D — MY 2020, electricity, weekend

The other end of the `evefficiency` age-group ladder, so that both the youngest
and the oldest group are exercised.

```
sho[92, 0]                                = 54.728314588378  (reference 54.728300, 2.7e-7)
sourceBinActivityFraction[212020, fuel 9] = 0.0413386
meanBaseRate[92, 2020, 9]                 = 3 144.90
agecategory[0].ageGroupID                 = 3
evefficiency[9101, 21, 20, 3]             = 0.95 x 0.94 = 0.893

emissionQuant [MMBTU]   = (3 144.90 / 0.893) x (54.728314588378 / 2) / 1 055 055.9
                        = 0.091340210875         (MOVESOutput 0.0913402, 1.2e-7)
```

### 6.5 The reproduction script

Extracted and run by `./run-onroad-oracle.sh`. It reads only the tables of
§1.2 and §10.1, computes S1–S18 — including `W` and the base rate, which it used
to read from `baserate_1_2020` — and **asserts** its worst relative error against
`sho` and against `MOVESOutput`.

```python
#!/usr/bin/env python3
"""Independent reproduction of the mixed-onroad chain from the snapshot's own
input tables, and from NOTHING else. Every stage is computed here: the activity
half (S1-S9), the cohort structure and the fuel-usage rebase (S10-S12), the
drive-cycle operating-mode weights and the base rate (S13-S14), and the output
stage (S16-S18).

It used to read `baserate_1_2020.meanBaseRate`, because the operating-mode
distribution the base rate needs is computed inside the MOVES worker and dropped
(section 8.1). Section 10 says how it is computed instead.

Purpose: attribution. When a `.esm` disagrees with the snapshot, a third
implementation says whether the document or the specification is wrong."""
import sys
import collections
import pyarrow.parquet as pq

SNAP = sys.argv[1]
P = SNAP + "/tables/db__movesexecution1ccc0233_campuscluster_illinois_edu__"


def T(n):
    return pq.read_table(P + n + ".parquet").to_pylist()


# ---------------------------------------------------------------- run scope
YEAR, MONTH, HOUR, ZONE, ROAD, ST = 2020, 8, 9, 261610, 4, 21
COUNTY, ELECTRICITY = 26161, 9
DAYS = [r["dayID"] for r in T("runspecday")]
HD = {r["dayID"]: r["hourDayID"] for r in T("hourday") if r["hourID"] == HOUR}
POLPROC = 100 * 91 + 1
KJ_PER_MMBTU = 1055.0559e6 / 1000.0

# ------------------------------------------------ S1: base year (section 1.5)
base = max(r["yearID"] for r in T("year")
           if r["yearID"] <= YEAR and str(r["isBaseYear"]).upper() == "Y")
assert base == YEAR, "the population and VMT folds do not collapse for %d" % base
FUELYEAR = {r["yearID"]: r["fuelYearID"] for r in T("year")}[YEAR]

# ------------------------------------------------- S2: sourceTypeAgePopulation
stpop = {r["sourceTypeID"]: float(r["sourceTypePopulation"])
         for r in T("sourcetypeyear") if r["yearID"] == base}
agefrac = {(r["sourceTypeID"], r["ageID"]): float(r["ageFraction"])
           for r in T("sourcetypeagedistribution") if r["yearID"] == base}
pop = {k: stpop[k[0]] * v for k, v in agefrac.items() if k[0] in stpop}

# --------------------------------------------------------- S3: travelFraction
mar = {(r["sourceTypeID"], r["ageID"]): float(r["relativeMAR"])
       for r in T("sourcetypeage")}
hpms = {r["sourceTypeID"]: r["HPMSVtypeID"] for r in T("sourceusetype")}
group_total = collections.defaultdict(float)
for k in pop:
    group_total[hpms[k[0]]] += pop[k] * mar[k]
travelfrac = {k: pop[k] * mar[k] / group_total[hpms[k[0]]] for k in pop}

# -------------------------------------------------------- S4: analysisYearVMT
ayv = {r["HPMSVtypeID"]: float(r["HPMSBaseYearVMT"])
       for r in T("hpmsvtypeyear") if r["yearID"] == base}

# ------------------------------------------------- S5: annualVMTByAgeRoadway
onroad = {r["roadTypeID"] for r in T("roadtype")}
rtd = {r["roadTypeID"]: float(r["roadTypeVMTFraction"])
       for r in T("roadtypedistribution")
       if r["sourceTypeID"] == ST and r["roadTypeID"] in onroad}
ages = sorted({k[1] for k in travelfrac if k[0] == ST})
annual = {a: ayv[hpms[ST]] * rtd[ROAD] * travelfrac[(ST, a)] for a in ages}

# ------------------------------------------------------------ S6: averageSpeed
binspeed = {r["avgSpeedBinID"]: float(r["avgBinSpeed"]) for r in T("avgspeedbin")}
speed = collections.defaultdict(float)
for r in T("avgspeeddistribution"):
    if r["sourceTypeID"] != ST or r["roadTypeID"] != ROAD:
        continue
    for d in DAYS:
        if r["hourDayID"] == HD[d]:
            speed[d] += float(r["avgSpeedFraction"]) * binspeed[r["avgSpeedBinID"]]

# ------------------------------------------------- S7: vmtByAgeRoadwayHour
weeks = {r["monthID"]: r["noOfDays"] / 7.0 for r in T("monthofanyyear")}[MONTH]
mvf = {r["monthID"]: float(r["monthVMTFraction"])
       for r in T("monthvmtfraction") if r["sourceTypeID"] == ST}[MONTH]
dvf = {r["dayID"]: float(r["dayVMTFraction"]) for r in T("dayvmtfraction")
       if r["sourceTypeID"] == ST and r["monthID"] == MONTH and r["roadTypeID"] == ROAD}
hvf = {r["dayID"]: float(r["hourVMTFraction"]) for r in T("hourvmtfraction")
       if r["sourceTypeID"] == ST and r["roadTypeID"] == ROAD and r["hourID"] == HOUR}

# ------------------------------------------------------------- S8, S9: sho
alloc = {r["roadTypeID"]: float(r["SHOAllocFactor"])
         for r in T("zoneroadtype") if r["zoneID"] == ZONE}[ROAD]
selected_hd = {r["hourDayID"] for r in T("runspechourday")}
sho = {}
for d in DAYS:
    assert HD[d] in selected_hd
    for a in ages:
        vmt = annual[a] * mvf * dvf[d] * hvf[d] / weeks
        sho[(HD[d], a)] = (vmt / speed[d] if speed[d] else 0.0) * alloc

# ----------------------------------- S10, S11, S12: the cohorts and their bins
maxage = max(r["ageID"] for r in T("agecategory"))
my_lo, my_hi = YEAR - maxage, YEAR
fuels = {r["fuelTypeID"] for r in T("runspecsourcefueltype")
         if r["sourceTypeID"] == ST}
mygroup = {(r["polProcessID"], r["modelYearID"]): r["modelYearGroupID"]
           for r in T("pollutantprocessmodelyear")}
shortgroup = {r["modelYearGroupID"]: r["shortModYrGroupID"]
              for r in T("modelyeargroup")}
cohort = {}
for r in T("samplevehiclepopulation"):
    frac = float(r["stmyFraction"])
    if (r["sourceTypeID"] != ST or not my_lo <= r["modelYearID"] <= my_hi
            or r["fuelTypeID"] not in fuels or frac <= 0.0):
        continue                      # `stmyFraction > 0` -- section 2.2
    g = mygroup.get((POLPROC, r["modelYearID"]))
    if g is None or g not in shortgroup:
        continue                      # two inner joins
    key = (r["modelYearID"], r["fuelTypeID"], r["engTechID"], r["regClassID"])
    cohort[key] = cohort.get(key, 0.0) + frac

# ------------------------------- S13(a): the drive-cycle operating-mode weights
# `W[hourDayID, opModeID]`, the one relation no captured table carries: MOVES 5
# computes it inside the worker and drops it (section 8.1). Ported from
# crates/moves-calculators/src/generators/baserategenerator/drivecycle.rs.
seconds = collections.defaultdict(dict)
for r in T("driveschedulesecond"):
    seconds[r["driveScheduleID"]][r["second"]] = float(r["speed"])
physics = [r for r in T("sourceusetypephysicsmapping")
           if r["realSourceTypeID"] == ST and float(r["sourceMass"]) > 0.0
           and float(r["fixedMassFactor"]) > 0.0]
assert len(physics) == 1, "the physics mapping is not a single row for source type %d" % ST
PH = physics[0]
opmode = {r["opModeID"]: r for r in T("operatingmode")}
BRAKE1 = float(opmode[0]["brakeRate1Sec"])
BRAKE3 = float(opmode[0]["brakeRate3Sec"])
# readOperatingMode (inputs.rs:408-419). Dropping 26 and 36 leaves 21 modes that
# are disjoint AND exhaustive over speed >= 1, which is why the classification
# below can be a single match rather than an ordered first-match.
binned = sorted((m for m in opmode if 1 < m < 100 and m not in (26, 36)))
MS = 0.44704


def bound(mode, column):
    v = opmode[mode][column]
    return None if v is None else float(v)


def drive_cycle_distribution(sid):
    """calculateDriveCycleOpModeDistribution at national scale (is_project False)."""
    sp = seconds[sid]
    lo, hi = min(sp), max(sp)
    mode, acc = {}, {}
    for s, v in sp.items():
        if v < 1.0:                       # 0 mph and 0 < v < 1 mph are both Idling
            mode[s] = 1
    for s in range(lo + 1, hi + 1):
        if s in sp and s - 1 in sp:
            acc[s] = sp[s] - sp[s - 1]
    if lo + 1 in acc:
        acc[lo] = acc[lo + 1]             # the first second copies the second's
    total = collections.Counter()
    for s in range(lo, hi + 1):
        if s not in sp:
            continue
        m = mode.get(s)
        if m is None:
            a = acc.get(s, 0.0)
            three = (s - 1 in sp and s - 2 in sp and a < BRAKE3
                     and acc.get(s - 1, 0.0) < BRAKE3 and acc.get(s - 2, 0.0) < BRAKE3)
            if a <= BRAKE1 or three:
                m = 0
            else:
                v = sp[s] * MS
                a_ms = (v - sp[s - 1] * MS) if s - 1 in sp else (
                    (sp[s + 1] * MS - v) if s == lo and s + 1 in sp else 0.0)
                vsp = (float(PH["rollingTermA"]) * v
                       + float(PH["rotatingTermB"]) * v * v
                       + float(PH["dragTermC"]) * v * (v * v)
                       + float(PH["sourceMass"]) * v * a_ms) / float(PH["fixedMassFactor"])
                for k in binned:
                    lov, hiv = bound(k, "VSPLower"), bound(k, "VSPUpper")
                    los, his = bound(k, "speedLower"), bound(k, "speedUpper")
                    if lov is not None and vsp < lov: continue
                    if hiv is not None and vsp >= hiv: continue
                    if los is not None and sp[s] < los: continue
                    if his is not None and sp[s] >= his: continue
                    m = k
                    break
        if m is not None and s > 0:        # the `second > 0` guard, drivecycle.rs:327
            total[m] += 1
    n = sum(total.values())
    return {k: v / n for k, v in total.items()}


cycles = sorted(r["driveScheduleID"] for r in T("drivescheduleassoc")
                if r["sourceTypeID"] == ST and r["roadTypeID"] == ROAD)
cycle_speed = {r["driveScheduleID"]: float(r["averageSpeed"]) for r in T("driveschedule")}
assert len({cycle_speed[c] for c in cycles}) == len(cycles), "two cycles share a speed"
cycle_dist = {c: drive_cycle_distribution(c) for c in cycles}

bin_modes = {}                             # findDriveCycles, drivecycle.rs:110-176
for b, bs in binspeed.items():
    low = max((cycle_speed[c] for c in cycles if cycle_speed[c] <= bs), default=None)
    high = min((cycle_speed[c] for c in cycles if cycle_speed[c] >= bs), default=None)
    span = (high if high is not None else 100000.0) - (low if low is not None else -100.0)
    if span <= 0.0:      lf = 1.0
    elif low is None:    lf = 0.0
    elif high is None:   lf = 1.0
    else:                lf = (high - bs) / span
    d = collections.defaultdict(float)
    for c, f in ((low, lf), (high, 1.0 - lf)):
        if c is None or f == 0.0:
            continue
        sid = next(s for s in cycles if cycle_speed[s] == c)
        for m, v in cycle_dist[sid].items():
            d[m] += f * v
    bin_modes[b] = d

W = collections.defaultdict(float)
for r in T("avgspeeddistribution"):
    if r["sourceTypeID"] != ST or r["roadTypeID"] != ROAD:
        continue
    for m, v in bin_modes[r["avgSpeedBinID"]].items():
        W[(r["hourDayID"], m)] += v * float(r["avgSpeedFraction"])
for d in DAYS:
    t = sum(v for (h, _), v in W.items() if h == HD[d])
    assert abs(t - 1.0) < 1e-5, "W does not sum to 1 for hourDayID %d: %.9f" % (HD[d], t)

# ---------------------- S12(b): the fuel-usage rebase, source_bin_..._generator.rs:1534
# NOT the identity: `fuelusagefraction` sends 98.2134% of an E85 bin's activity
# to the gasoline supply, and the base rate is weighted by the rebased
# distribution (sbweighted.rs:148-165). Omitting it is a 55x error on E85.
usage = [r for r in T("fuelusagefraction")
         if r["countyID"] == COUNTY and r["fuelYearID"] == FUELYEAR]
sbaf = collections.defaultdict(float)
for (my, fuel, engtech, regclass), frac in cohort.items():
    for u in usage:
        if u["sourceBinFuelTypeID"] != fuel:
            continue
        if u["modelYearGroupID"] != 0 and u["modelYearGroupID"] != my:
            continue
        used = (my, u["fuelSupplyFuelTypeID"], engtech, regclass)
        if used not in cohort:            # the used bin must exist, :1551-1557
            continue
        sbaf[used] += float(u["usageFraction"]) * frac

# ------------------------------------------ S13(b): the source-bin-weighted rate
def slot(bin_id, scale):                  # section 4.4; never pack, only unpack
    return (bin_id // scale) % 100


rate = {}
for r in T("emissionrate"):
    if r["polProcessID"] != POLPROC:
        continue
    b = r["sourceBinID"]
    rate[(slot(b, 10**16), slot(b, 10**14), slot(b, 10**12), slot(b, 10**10),
          r["opModeID"])] = float(r["meanBaseRate"])

fleetgroup = {r["regClassID"]: r["fleetAvgGroupID"] for r in T("regulatoryclass")}
evfrac = {(r["modelYearID"], r["fleetAvgGroupID"]): float(r["evFraction"])
          for r in T("evsalesfraction")}
fleetadj = [r for r in T("fleetavgadjustment") if r["polProcessID"] == POLPROC]


def ev_sales_factor(my, fuel, regclass):
    """sbweighted.rs:369-405 -- back-scale the ICE fleet for EV sales."""
    if fuel == ELECTRICITY:
        return 1.0
    g = fleetgroup[regclass]
    e = evfrac.get((my, g))
    row = next((r for r in fleetadj if r["fleetAvgGroupID"] == g
                and r["beginModelYearID"] <= my <= r["endModelYearID"]), None)
    if e is None or row is None:
        return 1.0
    m = float(row["evMultiplier"])
    den = (1.0 - e) + e * m
    v = 1.0 / (1.0 - e * m / den)
    cap = row["adjustmentCap"]
    return min(v, float(cap)) if cap is not None and float(cap) > 0.0 else v


# ------------------------------------------------- S14: the collapsed base rate
sbweighted = collections.defaultdict(float)
for (my, fuel, engtech, regclass), frac in sbaf.items():
    smy = shortgroup[mygroup[(POLPROC, my)]]
    ev = ev_sales_factor(my, fuel, regclass)
    for om in {k[4] for k in rate}:
        r = rate.get((fuel, engtech, regclass, smy, om))
        if r is not None:
            sbweighted[(my, fuel, om)] += frac * r * ev
base_rate = collections.defaultdict(float)
for (my, fuel, om), v in sbweighted.items():
    for d in DAYS:
        base_rate[(HD[d], my, fuel)] += v * W[(HD[d], om)]

# ------------------------------ S15(f): the EV energy-efficiency divisor
agegroup = {r["ageID"]: r["ageGroupID"] for r in T("agecategory")}
eveff = {r["ageGroupID"]: float(r["batteryEfficiency"]) * float(r["chargingEfficiency"])
         for r in T("evefficiency")
         if r["polProcessID"] == POLPROC and r["sourceTypeID"] == ST}

# ------------------------------------------------------- S16, S17, S18
realdays = {r["dayID"]: float(r["noOfRealDays"]) for r in T("dayofanyweek")}


def onroad_scc(fuel, source, road, process):
    return "%d" % (22 * 10**8 + fuel * 10**6 + source * 10**4 + road * 10**2 + process)


rows = {}
for (my, fuel, engtech, regclass), frac in cohort.items():
    for d in DAYS:
        rate = base_rate[(HD[d], my, fuel)]
        if fuel == ELECTRICITY:
            rate /= eveff[agegroup[YEAR - my]]
        activity = sho[(HD[d], YEAR - my)] / realdays[d]
        rows[(d, my, fuel)] = (rate * activity / KJ_PER_MMBTU,
                               onroad_scc(fuel, ST, ROAD, POLPROC % 100))

# ------------------------------------------------------------------- compare
ref_sho = {(r["hourDayID"], r["ageID"]): float(r["SHO"]) for r in T("sho")}
worst_sho = max(abs(sho[k] - v) / v for k, v in ref_sho.items())
print("sho:           %3d rows, worst relative error %.3e" % (len(ref_sho), worst_sho))
# ASSERTED, not merely printed. ./run-tests.sh reads this script's EXIT CODE, so
# a regression that leaves the key set intact and moves every value would
# otherwise be reported green with the evidence sitting in the log. Measured:
# injecting a 2% error here used to leave the whole suite green.
assert worst_sho < 1e-5, "sho: worst relative error %.3e exceeds 1e-5" % worst_sho

out = pq.read_table(SNAP + "/tables/db__out_mixed_onroad__movesoutput.parquet").to_pylist()
worst, worst_key = 0.0, None
for o in out:
    q, scc = rows[(o["dayID"], o["modelYearID"], o["fuelTypeID"])]
    assert scc == o["SCC"], (scc, o["SCC"])
    rel = abs(q - float(o["emissionQuant"])) / float(o["emissionQuant"])
    if rel > worst:
        worst, worst_key = rel, (o["dayID"], o["modelYearID"], o["fuelTypeID"])
print("emissionQuant: %3d rows, worst relative error %.3e at (day %d, MY %d, fuel %d)"
      % (len(out), worst, *worst_key))
assert len(rows) == len(out), (len(rows), len(out))
assert set(rows) == {(o["dayID"], o["modelYearID"], o["fuelTypeID"]) for o in out}
assert worst < 2e-5, "emissionQuant: worst relative error %.3e exceeds 2e-5" % worst
print("key set:       %3d cohorts x %d day types = %d rows, exact"
      % (len(cohort), len(DAYS), len(rows)))
```

Result:

```
sho:            82 rows, worst relative error 4.138e-06
emissionQuant: 250 rows, worst relative error 8.320e-06 at (day 5, MY 2015, fuel 5)
key set:       125 cohorts x 2 day types = 250 rows, exact
```

### 6.6 Suggested inline `.esm` tests

| test | asserts | what breaks if it is wrong |
|---|---|---|
| `travel_fraction_normalises_over_the_hpms_vtype` | `travelFraction[21, 40]` = 1.609174853309e-03 | normalising over source type 21 alone gives 4.10e-03, and every row is 2.55× high |
| `average_speed_is_the_arithmetic_mean` | `averageSpeed[4, 21, 2, 9]` = 66.094076 | the harmonic mean gives 49.44 and SHO is 34 % high |
| `weeks_per_month_divides` | `sho[92, 40]` = 4.880649 | omitting the divisor gives 21.61 and a 4.43× over-emit |
| `sho_is_a_week_of_the_day_type` | `emissionQuant` = 0.895519 for §6.1 | leaving out `/noOfRealDays` gives 1.79 for the weekend and 4.48 for the weekday |
| `the_zero_share_cohorts_are_suppressed` | 125 cohorts, and `(1980, 5)` absent | dropping `stmyFraction > 0` emits 328 rows |
| `ev_efficiency_divides_by_age_group` | §6.3 = 4.965714e-04 and §6.4 = 0.09134021 | omitting it is 22.1 % low at MY2000 and 10.7 % at MY2020 |
| `the_ac_factor_is_clamped_to_zero_here` | `ACFactor` = 0 at `heatIndex` 66.9 | the unclamped −0.0189 *subtracts* 1 070 kJ from §6.1 |
| `the_ac_factor_is_reachable` | override `heatIndex` to 75 → `ACFactor` > 0 and §6.1 grows by 14.6 % | a document that hardcodes 0 passes the previous test and is wrong for every other hour |
| `the_ev_temperature_branch_is_reachable` | at 40 °F the EV term is +0.214720, so the factor is 1.21472 and §6.4 goes from 0.0913402 to 0.1109528 | same reason. And at 40 °F the A/C term is −1.174540 and still clamps, so the two clamps are not redundant: there is a temperature where one is active and the other is not. At 75 °F they move in OPPOSITE directions, because the `heatIndex > 67` suppression fires and holds the EV factor at 1 |
| `the_onroad_scc_is_arithmetic` | 2201210401, 2209210401 | an SCC off by a digit relabels the whole relation and passes a per-pollutant tolerance |
| `the_energy_conversion_is_million_btu` | 944823 kJ → 0.895519 | leaving it in kJ passes nothing, but leaving it in *BTU* is a 10⁶ error a sum check would catch and a per-cell check attributes |

---

## 7. Fidelity notes and tolerance

### 7.1 Everything agrees to ~10⁻⁶, and that number is the reference's, not ours

The oracle's worst relative error is 4.14 × 10⁻⁶ on `sho` and 8.23 × 10⁻⁶ on
`emissionQuant`. That is not accumulated arithmetic error; it is the
**storage precision of the reference**. Canonical MOVES holds these columns as
MySQL `FLOAT` (binary32) and the snapshot writes them out with 12 decimal
places, so a value like `annualvmtbyageroadway.VMT` arrives as
`1074610000.000000000000` where the exact product is `1074612910.971`. Six
significant figures.

Every ratio measured in this document lands in `[1 − 9e-6, 1 + 9e-6]`, which is
what a 6-significant-figure round trip predicts. There is no step in this chain
where the two implementations disagree by more than the reference can express.

**This is why onroad's tolerance is 10⁻³ and NONROAD's is 10⁻².** NONROAD is
`real*4` Fortran throughout and its port is bit-exact `f32`; the onroad chain
is binary64 arithmetic over binary32-*stored* inputs, which is a much weaker
constraint. 10⁻³ gives two orders of headroom over the worst observed 8.3 × 10⁻⁶
and still catches a 0.1 % modelling error.

### 7.2 The one place precision changes the answer

Not arithmetic — a **clamp**.

```
A/C activity term at heatIndex 66.900001525879 = -0.018900...
```

The clamp `max(·, 0)` turns that into an A/C factor of exactly 0, which removes
a 14.6 % addition from all 250 rows. The margin is 0.0189 in a term whose
inputs are ±3.6, i.e. the clamp decision is made on the **third significant
figure** of a cancelling difference:

```
-3.63154 + 3.612640...   ->  the two terms agree to 3 figures and the
                             difference is what decides the branch
```

`heatIndex` is stored as binary32 (66.900001525879 is `66.9f` widened), so a
port that read `66.9` exactly would get `-0.01890013...` and a port reading the
binary32 value gets `-0.01890011...`. Both clamp to zero, comfortably — the
distance to the boundary is 0.0189, and binary32's spacing at 66.9 is 3.8e-6.
So this is *safe* here, and would not be at a `heatIndex` of 67.15.

The same is true of the EV temperature term, at −0.004192 with binary32
spacing 3.8e-6 in its input.

**Conclusion, and it is the opposite of NONROAD's.** `nr-logging-county` has a
cohort whose `modfrc` is 5.96e-8 in float32 and exactly 0 in binary64, so the
answer *depends on the evaluation precision* and the port needs
`element_type: "Float32"` (blocked by finding F18). `mixed-onroad` has no such
cell: both of its clamp decisions have margins ~5 000× the input precision.
**This fixture is precision-insensitive and must be evaluated in binary64** —
which is fortunate, because F18 says a document carrying ten-digit identifier
columns cannot declare `Float32` at all, and this one carries an 18-digit one.

### 7.3 The measured decomposition that isolated the uncomputed relation

§2.3(b) claims the base rate factorises as

```
baseRate.meanBaseRate[hd, MY, fuel]
  = SUM over opModeID om of
      W[hd, om]
      x sourceBinActivityFraction[MY, fuel]
      x emissionrate[bin(MY, fuel), 9101, om].meanBaseRate
      x evSalesFactor(MY, fuel, 20)
```

with `W[hd, om] = SUM over b of opModeFraction[om, b] × avgSpeedFraction[b]`
depending on `hourDayID` alone. That is a strong claim — it says the operating
mode structure is *separable* from the cohort structure — and it is testable
without computing `W`: solve for the 23 unknowns from the 125 known base rates
per `hourDayID`, and see whether the residual is at the reference's storage
precision.

Non-negative least squares over the snapshot:

| `hourDayID` | equations | unknowns | `SUM W` | worst residual | median residual |
|---|---|---|---|---|---|
| 92 (weekend) | 125 | 23 | 0.999447 | **7.06 × 10⁻⁶** | 1.15 × 10⁻⁶ |
| 95 (weekday) | 125 | 23 | 0.999176 | **1.38 × 10⁻⁵** | 1.83 × 10⁻⁶ |

Both residuals are at the 6-significant-figure floor of §7.1, and both weight
vectors sum to 1 to within the same. **The factorisation is exact.** Two
controls confirm the two factors that had to be right for it to hold:

* using the raw `sourcebindistribution` instead of
  `sourcebindistributionfuelusage_1_26161_2020` — as
  `sbweighted.rs:148-158` warns — the fit degrades;
* omitting `evSalesFactor`, which is model-year dependent, the best single
  weight vector leaves a **5.5 × 10⁻²** residual and `SUM W` = 1.371 — a
  37 % error, and the reason a naive fit fails.

So the whole of S13–S14 reduces to **46 numbers**: `W[92, ·]` and `W[95, ·]`.
Everything else in the base rate is specified above and computable from §1.2.

Those 46 numbers are *not* reproduced in this document, deliberately. They were
obtained by fitting to the reference's own intermediate, so they are not an
independent derivation, and a `.esm` that carried them would be transcribing
the answer — the thing `docs/esm-conventions.md` §12 forbids for exactly this
reason.

**`W` is now computed**, twice and independently: by §6.5's reproduction script
and by `fixtures/mixed-onroad.esm`, both from `driveschedulesecond`,
`driveschedule`, `drivescheduleassoc`, `operatingmode`,
`sourceusetypephysicsmapping`, `avgspeedbin` and `avgspeeddistribution`. §10 is
the port. The measurement that closes this section is the one that says the
factorisation was not an artefact of the fit: **computing `W` moved the worst
`MOVESOutput` cell from 8.231 × 10⁻⁶ to 8.320 × 10⁻⁶**, which is nowhere, and
the residual is still §7.1's six-significant-figure column storage.

Two things about the fitted numbers are worth keeping now that the computed ones
exist. The fit's `SUM W` came out 0.999447 and 0.999176; the computed weights
sum to **1.0000004** and **0.9999999**, which is `avgspeedFraction`'s own total
to its stored precision. So the fit was about 6 × 10⁻⁴ low on the total — an
ill-conditioning of a 23-unknown non-negative fit over 125 highly collinear rate
vectors, not a property of `W` — and a document that had transcribed the fitted
vector would have been wrong by that much with every residual still inside the
gate. That is the second reason not to transcribe a fitted answer, and it is a
better one than the first.

### 7.4 Recommended tolerance, and the honest state of the comparison

```toml
[default]
onroad = 1e-3        # per-pollutant sums

[cell]
rel = 2e-5           # per-cell; worst observed 8.3e-6, ~2.4x headroom

[structure]
require_exact_key_set = true
require_exact_row_count = true
```

The per-cell 2 × 10⁻⁵ is the same number NONROAD uses, arrived at
independently: 2.4× headroom over the worst observed 8.3 × 10⁻⁶ here, 5×
over NONROAD's 4.0 × 10⁻⁶ there, and in both cases the constraint is the
reference's 6-significant-figure storage rather than either implementation.

**What the key set gate means for this fixture.** The 250-row key set *is*
computable — §2.2's `stmyFraction > 0` rule reproduces all 125 cohorts exactly.
So is the value in each cell, now that §10's `W` is computed.

**Measured, `fixtures/mixed-onroad.esm` against the snapshot's `MOVESOutput`:**

```
rows: 250 actual / 250 expected
identity: 19 columns, 4 varying (dayID, fuelTypeID, modelYearID, SCC); 15 constant
key set: 250 shared, 0 missing, 0 extra
worst cell: rel=8.320e-06 over 250 cells        (tolerance 2e-05)
worst per-pollutant emissionQuant sum: rel=9.675e-08 (onroad tolerance 1e-03)
```

`tolerance.toml` carries **no `[shortfall]` record** for this fixture and must
not acquire one: `run-tests.sh` fails if a record is left behind a comparison
that passes.

This section used to argue that the fixture should not be wired at all, and the
argument is kept because it is the right one for the state it described. A
document that emitted 250 correctly-keyed rows carrying an *uncomputed* rate
would fail the per-cell gate for a reason no exact record could pin — the
`[shortfall]` mechanism records `emitted_rows` / `missing_keys` /
`extra_keys`, and that failure is 250 rows with the right keys and wrong
numbers — and a document that read `baserate_1_2020` would pass the gate by
transcribing the reference. Neither is a fidelity test. The way out was to
compute the missing relation, not to widen anything.

### 7.5 Precision-sensitive operations, ranked

| | operation | why |
|---|---|---|
| 1 | the A/C activity clamp (§7.2) | a cancelling difference decides a branch worth 14.6 % |
| 2 | the EV temperature clamp | same shape, worth up to 2 % |
| 3 | `travelFraction`'s denominator | a sum over 123 terms spanning 4 orders of magnitude; summation order matters at ~10⁻¹⁵, far inside the gate |
| 4 | `sourceBinID` arithmetic | 1.01 × 10¹⁸ is past 2⁵³; never do arithmetic on it (§2.2) |
| 5 | `averageSpeed` | a 16-term sum of positive terms; benign |
| 6 | the energy conversion | one multiply by a constant known to 8 figures (§5.6) |

---

## 8. Gaps, uncertainties and things I could not verify

### 8.1 `W[hourDayID, opModeID]` — **computed; see §10**

This section recorded `W` as the one relation this port did not compute, and
listed the five things computing it would take. All five are now in
`fixtures/mixed-onroad.esm` and in §6.5's reproduction, and §10 is the port.
The list was right about all five inputs and it is kept here, corrected, because
three of the things it said about the *toolchain* have stopped being true.

**What it is.** The speed-bin-weighted, drive-cycle operating-mode distribution
for running exhaust. `crates/moves-calculators/src/generators/baserategenerator/drivecycle.rs:354-622`,
with the weighting at `:388-401`:

```rust
for (&op_mode_id, &op_mode_fraction) in distribution {
    *detail.op_mode_fractions.entry(op_mode_id).or_insert(0.0) +=
        schedule_fraction * op_mode_fraction;
}
```

**Why the snapshot cannot supply it.** MOVES 5 sets
`USE_EXTERNAL_GENERATOR = true`, so canonical's Java
`RatesOperatingModeDistributionGenerator` delegates Running Exhaust entirely to
the external generator and contributes no rows
(`rates_op_mode_distribution.rs:1-58`). The `ratesopmodedistribution` table in
the snapshot therefore covers roadTypeID 1 / polProcessIDs 602 and 9102 only
(18 rows, §1.4), and no captured table carries the process-1 distribution. It
is computed inside the worker and dropped. **That part is unchanged, and it is
why `W` had to be computed rather than read.**

**The five inputs, all present in the snapshot:**

1. `drivescheduleassoc` (11 rows) → the drive schedules for
   `(sourceTypeID 21, roadTypeID 4)`, and the bracketing of each `avgSpeedBin`
   between two schedules with a `schedule_fraction` (`drivecycle.rs:359`).
2. `driveschedulesecond` (63,602 rows) → the second-by-second speed trace.
3. Acceleration, and the three-second brake lookback. §10.2 is what this costs.
4. `sourceusetypephysicsmapping` (1 row: rollingTermA 0.156461,
   rotatingTermB 0.00200193, dragTermC 0.000492646, sourceMass 1.4788,
   fixedMassFactor 1.4788, opModeIDOffset 1000) → VSP per second. The mapping is
   per `(sourceTypeID, regClassID, model-year range)`, so the distribution is
   **model-year dependent** in general; this fixture's single row spans
   1950–2060, so here it is not, and `run_physicsRowsSelected` asserts that the
   collapse is a fact about the data rather than an assumption.
5. `operatingmode` (60 rows) → the classification. `VSPLower`/`VSPUpper` and
   `speedLower`/`speedUpper` are a genuine range predicate — a `filter`, not a
   `join.on`.

**Three things this section said that are no longer true.**

* *"the neighbouring-row reads are F11's documented workaround"* — **F11 is
  fixed** (EarthSciAST `107a15152`), so they are not a workaround at all. They
  are four ordinary self-joins with an explicit `join.syms`; §10.2 measures
  them.
* *"a 63,602-row relation joined to a 60-row one under a range predicate, which
  is precisely the shape finding F17 measures as undriven"* — the range
  predicate is **not a join** and never was. The classification is a per-second
  contraction over the 60-row mode relation with no gate at all, 3.8 × 10⁶
  leaves; the F17 shape appears one stage later, at the emission-rate lookup,
  and §10.3 says what was done about it.
* *"the per-schedule normalisation is `share_of_group` (§4.2)"* — correct, and
  it is the one prediction in the list that needed no change.

**And one thing it said that was right, and that the sequence honoured.** "No
captured intermediate to verify it against… landing `W` without an independent
check would put a 63,602-row VSP computation into the tree with nothing to catch
a wrong sign." The check is the one this section prescribed: compute `W`, check
it against `MOVESOutput` end to end, and only then wire the fixture. §7.3 has
the number that closes it and §7.4 has the comparison.

### 8.2 Things verified empirically but not in canonical code

* **The `1 055 055.85` in the snapshot** versus `moves.rs`'s
  `1055.0559e6/1000 = 1 055 055.9`. The snapshot stores 6 significant figures
  so the eighth-figure difference is unobservable (§5.6). Canonical MOVES's own
  `EnergyMeasurementSystem` was not read.
* **The absence of `weeksPerMonth` on the output.** Inferred from
  `plan.rs:455-478` (`Hour` timestep → `PortionOfWeekPerDay`) *and* confirmed
  numerically: including it would multiply every row by 4.43.
* ~~**`sourceBinActivityFraction` equalling `stmyFraction` exactly** on all 125
  rows. This means the `fuelusagefraction` remap is effectively the identity
  for this county/year, which follows from its 5 rows but was not traced
  through `county_year_distribution` line by line.~~ **This was WRONG, and it is
  the one claim in this document that measurement has overturned.** It was true
  of `sourcebindistribution` (the *equipped* distribution, which does equal
  `stmyFraction` on all 125 rows) and asserted of
  `sourcebindistributionfuelusage_1_26161_2020` (the *used* one, which the base
  rate is actually weighted by, `sbweighted.rs:148-165`). Measured against that
  table, the raw `stmyFraction` is wrong by **5.497 × 10¹** on the E85 rows:
  `fuelusagefraction` sends 0.982134 of every E85 bin's activity to the gasoline
  supply, so MY 1998's E85 fraction is 1.611 × 10⁻⁴ and not 9.019 × 10⁻³. End to
  end the error is the same 5.497 × 10¹ on the worst `MOVESOutput` cell. The
  remap is computed in §6.5 and in `fixtures/mixed-onroad.esm`, and
  `components/onroad_source_bin_distribution.esm` had it right all along and
  says so at length — this section was the stale half. The lesson is the one
  §1.1 already states: cross-check the Rust *and this document* against the
  snapshot, because an inference from a table's shape ("5 rows, four of them
  identity pairs") is not a measurement of what the chain does with it.

### 8.3 An inconsistency in `moves.rs` worth reporting upstream

`ModuleFlags::ev_efficiency` is never enabled outside tests
(`baseratecalculator/mod.rs:798-802`), so `moves.rs` cannot reproduce this
fixture's 42 electricity rows — they come out 10.7 % to 22.1 % low (§2.3(f)).
The `EVEfficiency` table is declared in `INPUT_TABLES`, read, and expanded
through its model-year ranges, and then the only code that consumes it is
gated off. `model.rs:55-56` records that the Java always runs the section.
`emissionRateAdjustment` (`adjust.rs:586`) is gated off the same way.

Also recorded in that report and not chased here: `sum_sbd_raw` is assigned
`sum_sbd` (`sbweighted.rs:420`, `:444`), collapsing a distinction canonical
keeps — inert for this run because `useSumSBDRaw` is false, live at Rates
scale.

### 8.4 Paths this fixture does not exercise

Described from code only, and each would need its own verification:

* **Start exhaust (process 2)** — the rates exist (`baserate_2_2020`, 1,664
  rows) with real `opModeID`s 101–108, `sbweightedemissionrate` covers it, and
  `ratesopmodedistribution` and `startopmodedistribution` are both captured. A
  run selecting roadTypeID 1 would emit it. This is the *cheapest* next onroad
  slice, because its operating-mode distribution is in the snapshot and §8.1's
  blocker does not apply.
* **Pollutant 93 (Fossil Fuel Energy)** — in the XML, not in the run (§0.1).
* **I/M, criteria ratios, general fuel ratios** — all empty or not applicable
  to energy.
* **`Month`/`Portion` output timesteps** — where `weeksPerMonth` becomes live.
* **A non-base analysis year** — where §1.5's two folds stop collapsing and
  finding F12 bites.
* **Multiple counties, road types or source types** — where J5's normalisation
  denominator and J13's four-pair join start to matter.

### 8.5 Things deliberately not modelled

* The `roadTypeID 100` SCC branch (§4.3). One line, no data here.
* `MassUnit`. Parsed, recorded in `MOVESRun.massUnits`, and never applied
  anywhere in `moves.rs`; there is no `factor_from_grams`.
* `emissionRate` as an output column. `frame_to_emission_records` hard-codes
  `emission_rate: None` (`engine.rs:1503`) and `build_emission_output`
  re-nulls it, so it never reaches `MOVESOutput`.
* The E85 alternate-THC duplicate block (`adjust.rs:604-609`), which creates
  synthetic pollutant IDs ≥ 10000 that the aggregator drops
  (`output_aggregate.rs:87`). Energy is not chained to it.

---

## 9. Summary for the `.esm` author

**What to build, in order.** Each stage's numbers come from §6.

1. **`components/onroad_travel_fraction.esm`** — S1–S3. The population product
   and the HPMS-normalised travel fraction. The one thing to get right is J5's
   denominator group (§6.6 test 1). *Built: 19 assertions.*
2. **`components/onroad_source_hours.esm`** — S4–S9. The VMT chain with
   `weeksPerMonth` as a divisor, the arithmetic-mean speed, the divide and the
   spatial allocation. One component rather than three because `sho` is the
   stage with an independent reference and all four of its intermediate steps
   have stored values to check against. *Built: 23 assertions.*
3. **`components/onroad_source_bin_distribution.esm`** — S10–S12. The
   `stmyFraction > 0` row rule is the whole point of this component; it decides
   the key set. *Built: 36 assertions.*
4. **`components/onroad_energy_output.esm`** — S15, S16–S18. The two clamps and
   both their arms, the EV divisor, the `noOfRealDays` divide, the energy
   conversion, the arithmetic SCC, and the output relation's key columns.
   *Built: 55 assertions.*
5. **`runs/mixed_onroad_run.esm`** — the assembly. Performs the three joins the
   components replace with carried columns, plus the output-row-to-cohort join
   that has no counterpart in a leaf, and asserts the residuals.
   *Built: 163 assertions under the mount.*
6. **`lib/drive_cycle.esm` and `fixtures/mixed-onroad.esm`** — `W` (§10) and
   then the whole chain against the snapshot's own tables. *Built: 48
   assertions, and 250 of 250 `MOVESOutput` rows at a worst cell of
   8.320 × 10⁻⁶ (§7.4).*

**Six rules carried over from Phase 2 that still apply.**

* Tables stay tables; the output relation carries its key as **columns**, because
  the 125 cohorts are ragged (§0.2, finding F14).
* Every equality is a `join.on`; the two model-year ranges (J25, J32) are a
  `join.on` plus a range `filter`, exactly as NONROAD's hp containment was.
* J5 is not a self-join — second relation, second index set (finding F11).
* Every run-level quantity is a **one-row relation**, not a scalar (finding F16).
* `float_columns` on every ingested decimal-text column, and `extent` discovery
  for every row axis.
* The reference's row suppression is reproduced, not smoothed over.

**Three things that are new, and where they are written down.**

* An identifier **above 2⁵³** (`sourceBinID`, §2.2). Key on the components.
  Never materialise the packed id, and never declare `Float32` (finding F18).
* **Two clamps that both evaluate to zero here** (§2.3(d), §2.3(e)) and are
  both reachable one hour away. Assert both arms.
* **One relation that was not computed** (§8.1). It had a name, a shape, a
  source line, an exact size (46 numbers), and a measured proof that everything
  around it was right (§7.3) — which is what made it safe to leave out and what
  made it possible to put back. It is computed now; §10 is the port and §7.3 is
  the measurement that says computing it changed the answer by nothing.

---

## 10. `W[hourDayID, opModeID]`, computed

`W[hd, om] = SUM over avgSpeedBinID b of opModeFraction[om, b] x
avgSpeedFraction[hd, b]` — 46 non-zero numbers over two day types and the 23
operating modes §5.5 lists. Ported from
`crates/moves-calculators/src/generators/baserategenerator/drivecycle.rs`, whose
three functions map onto three stages.

### 10.1 The shape, stage by stage

| stage | Rust | `.esm` |
|---|---|---|
| the per-second classification | `calculate_drive_cycle_op_mode_distribution`, `:190-337` | `dss_opModeID` over `drive_second_rows` |
| the per-schedule distribution | `:330-337` | `dsa_modeFraction[schedule, mode]` |
| the bracketing of a speed bin | `find_drive_cycles`, `:110-176` | `asb_scheduleFraction[bin, schedule]` |
| the combination | `:388-401` | `asb_modeFraction[bin, mode]` |
| the speed-bin weighting | `aggregate.rs:365-417` | `dc_W[day, mode]` |

Two decisions in that table are not transcription and are worth stating.

**The classification is a SUM, not a first match.** `drivecycle.rs:305-322`
walks the operating modes in ascending id and `break`s on the first whose four
bounds admit the second, so the answer depends on iteration order — unless the
modes are disjoint, which they are. `readOperatingMode` (`inputs.rs:408-419`)
keeps `1 < opModeID < 100` **excluding 26 and 36**, and those two exclusions are
exactly what makes the survivors disjoint: 26 spans `12 <= VSP` over
`25 <= speed < 50` and 27–30 partition the same interval finely, and likewise 36
against 37–40. With them out, the 21 survivors partition `speed >= 1`
completely, so `SUM over modes of opModeID x indicator` is the matching mode's
id and `SUM of indicator` is 1. The document computes both:
`dss_binnedModeMatches` is the second, and a table change that broke the
disjointness shows up there as a 2 rather than as a plausible wrong mode.

**The bracketing schedules are identified by SPEED, not by an argmax over ids.**
`asb_slowerSpeed` is a `max_product` reduction under a `<=` filter and
`asb_fasterSpeed` a `min_sum` under `>=`; the weight is then attached to
whichever schedule carries that speed. The format has no argmax, and the
substitution is safe only while no two selected schedules share a speed — so
`asb_scheduleFractionTotal` sums the weights per bin and must be 1. A duplicated
bracket speed makes it 2 and a bin with no bracket makes it 0. That is finding
F17's `tech_fractionTotal` discipline applied to a different kind of window.

### 10.2 The four neighbouring-second reads, and what they cost

`a[s] = v[s] − v[s−1]` needs the previous second, the three-second brake test
needs `a[s−1]` and `a[s−2]` (so `v[s−2]` and `v[s−3]`), and a schedule's *first*
second copies its successor's acceleration (so `v[s+1]`). Each is
`driveschedulesecond` joined to **itself** — two `aggregate` ranges over one
index set — which finding **F11** refused until EarthSciAST `107a15152`. Each
value column has a companion presence column carrying `1` through the same join,
because an inner join fills an unmatched row with the semiring identity and a
`sum_product` 0 is indistinguishable from a genuine speed of 0.

That distinction is not academic here. **185 of the 63,602 rows have no
predecessor**: 49 because their schedule starts at that second, and 136 because
19 of the 49 schedules have interior gaps. The Rust indexes a dense `Vec` and
returns `None` for a gap; the port has to test presence for the same reason.

**Measured**, on the pinned toolchain, `esm simulate fixtures/mixed-onroad.esm
--time 0` with every `out_*` observed, three runs each:

| | wall clock |
|---|---|
| the fixture as written | 6.61 s, 6.62 s, 6.98 s |
| the same document with the eight self-join aggregates replaced by constants | 5.18 s, 5.23 s, 5.26 s |

So the four self-joins and their four presence companions cost about **1.4 s
together, ~0.18 s each**, at 63,602 × 63,602 = **4.045 × 10⁹ candidate pairs**
per join. They are driven. F11's own report measured 0.31 s for one join at this
exact size and inferred ~3.6 × 10³ s undriven; this is the same shape reached
from the other side, inside a document that does something with the answer.

The clause order matters and is deliberate: the offset-second pair is written
**first** in each `on` list, so it is the clause the evaluator resolves and
drives on (`docs/esm-conventions.md` §25). It admits about 3.2 rows per value
where the `driveScheduleID` pair admits 1,298.

### 10.3 Where the F17 shape actually is

§8.1 predicted that the 63,602-row relation meeting the 60-row `operatingmode`
relation would be F17's "big table meets big table". It is not: that step is a
per-second contraction over 60 modes with **no join gate at all** — 3.8 × 10⁶
leaves of pure arithmetic — and it does not dominate anything.

The F17 shape is one stage later, at `cohMode_rate`: the 164-row cohort grid
meeting `emissionrate`'s 69,200 rows over 164 × 60 = 9,840 output cells. The
remedy is the one F17 records, applied to a composite key rather than to an
axis: **all six key pairs go in ONE `on` clause**, so the gate is a single
composite key.

Leaf counts, computed from the parquet exactly as
`docs/esm-conventions.md` §25 computes J11's — for a clause that binds only the
cohort axis the mode axis is scanned, and vice versa:

| `cohMode_rate`'s gate | leaves admitted |
|---|---:|
| **one clause, all six pairs** (as written) | **3,772** |
| six clauses, `shortModYrGroupID` first | 8,511,600 |
| six clauses, `opModeID` first | 11,348,800 |
| six clauses, `regClassID` first | 91,315,200 |
| six clauses, `fuelTypeID` first (the order the pairs are written in) | 158,030,400 |
| six clauses, `engTechID` first | 379,430,400 |
| six clauses, `polProcessID` first | 561,273,600 |

**Measured**, the same document with that one clause split into six and nothing
else changed, `esm simulate --time 0` with every `out_*` observed: **298.36 s and
287.08 s**, against 6.61 / 6.62 / 6.98 s — a factor of **43**, for an emitted CSV
that is byte-identical. Subtracting the baseline gives ~1.8 µs per admitted leaf
over 1.58 × 10⁸ of them, which is F17's own ~2 µs and is the strongest evidence
available that the leaf count is the whole model of the cost.

So §25's rule generalises: it is not only *which* clause is first, it is *how
many clauses there are*. A composite key of six pairs is one gate; six gates of
one pair each is a gate whose selectivity is the least selective of the six.

The 60-wide `operating_mode_rows` axis *is* F17's remedy in one other place:
`dsa_modeSeconds` gives the mode axis its own `on` clause rather than leaving it
a scanned output loop.

### 10.4 What the fixture checks about `W`, and what it cannot

`W` has no captured intermediate. `baserate_1_2020` is the next thing
downstream that does, and it is `SUM over om of W[hd, om] x
sbWeightedMeanBaseRate[MY, fuel, om]` — so the fixture asserts **eight of its
cells directly**, over four cohorts spanning four orders of magnitude and both
day types, plus five of its `meanBaseRateACAdj` cells. §7.3 is what makes that a
check on `W`: the base rate factorises exactly around it, so a wrong `W` is a
wrong number in every one of those cells and nothing else in the chain can
absorb it.

Two structural properties are asserted as well, and neither needs a reference:
the weights sum to `avgSpeedFraction`'s own total (1 to its six stored
significant figures, hence an **absolute** 10⁻⁵ gate and not a relative one,
`docs/esm-conventions.md` §20.5), and they cover exactly 23 operating modes.

**Which of the two kinds of check actually catches a wrong `W`, measured.**
Perturb the classification in a sum-preserving way — `dss_vsp` × 1.001, so a
handful of seconds cross a VSP boundary into a neighbouring mode:

| | value |
|---|---|
| `dc_WTotal` | 1.0000004 and 0.9999999 — **unchanged** |
| `dc_WModeCount` | 23 and 23 — **unchanged** |
| inline assertions | **17 fail**: nine base-rate cells and all four worked examples |
| the comparator | 250 of 250 cells over tolerance |

So the structural tests check that `W` is a *distribution*; only a value checks
that it is the *right* distribution. A second sabotage — 1 % taken off every
binned mode's weight, which is not sum-preserving — is caught by both, at a
worst cell of 1.054 × 10⁻². Both were run before this section was written.

Three independent routes now agree on those 46 numbers: §6.5's Python, the
`.esm` fixture, and the snapshot's `MOVESOutput`. The first two agree to
**2.4 × 10⁻¹⁶** cell by cell — one ulp — which is what says the two ports are
the same arithmetic and not two arithmetics that happen to land inside a 10⁻⁵
gate.
