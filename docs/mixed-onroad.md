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
  input. §7.3 uses it as the pivot that isolates the one uncomputed relation;
  a document that read it would be transcribing the answer.

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

**`W` is the one relation this port does not compute.** §7.3 measures it, §8.1
says what computing it takes.

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

### 4.4 `source_bin_components` (new)

Not an arithmetic template but a documented decomposition, because the packed
id must never be materialised (§2.2):

```
fuel_type_id_of(bin)         = floor(bin / 1e16) mod 100
eng_tech_id_of(bin)          = floor(bin / 1e14) mod 100
reg_class_id_of(bin)         = floor(bin / 1e12) mod 100
short_mod_yr_group_id_of(bin)= floor(bin / 1e10) mod 100
```

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

### 4.6 Reused unchanged

| library | shapes used |
|---|---|
| `lib/identifiers.esm` | `pol_process_id` (9101 = 100 × 91 + 1), `null_output_column` (the nine NULL `MOVESOutput` columns) |
| `lib/keys.esm` | `latest_at_or_before_key` — the same year-precedence shape J25/J32 need |
| `lib/population.esm` | `linear_series_interpolation` is *not* needed; nothing here interpolates |

### 4.7 Shapes deliberately not factored

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

`sourceusetypephysicsmapping` carries `opModeIDOffset = 1000`, which is how
`SourceTypePhysics` relabels the physics-remapped modes; the offset is relevant
only to §8.1's uncomputed `W`.

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
meanBaseRate[92, 1980, 1]                 = 3.871710e+05 kJ/hr    <== S14, not computed here
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
§1.2, computes S1–S12 and S16–S18, takes S13–S14 from `baserate_1_2020`, and
prints its worst relative error against `sho` and against `MOVESOutput`.

```python
#!/usr/bin/env python3
"""Independent reproduction of the mixed-onroad chain from the snapshot's own
input tables. The activity half (S1-S9), the cohort structure (S10-S12) and
the output stage (S16-S18) are computed here; the base rate (S13-S14) is read
from `baserate_1_2020`, because the operating-mode distribution it needs is
not derivable from any captured table (see the specification, section 8.1).

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
DAYS = [r["dayID"] for r in T("runspecday")]
HD = {r["dayID"]: r["hourDayID"] for r in T("hourday") if r["hourID"] == HOUR}
POLPROC = 100 * 91 + 1
KJ_PER_MMBTU = 1055.0559e6 / 1000.0

# ------------------------------------------------ S1: base year (section 1.5)
base = max(r["yearID"] for r in T("year")
           if r["yearID"] <= YEAR and str(r["isBaseYear"]).upper() == "Y")
assert base == YEAR, "the population and VMT folds do not collapse for %d" % base

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

# ----------------------------------------- S13, S14: read, not computed
base_rate = {(r["hourDayID"], r["modelYearID"], r["fuelTypeID"]):
             float(r["meanBaseRate"]) for r in T("baserate_1_2020")}

# ------------------------------ S15(f): the EV energy-efficiency divisor
agegroup = {r["ageID"]: r["ageGroupID"] for r in T("agecategory")}
eveff = {r["ageGroupID"]: float(r["batteryEfficiency"]) * float(r["chargingEfficiency"])
         for r in T("evefficiency")
         if r["polProcessID"] == POLPROC and r["sourceTypeID"] == ST}
ELECTRICITY = 9

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
print("key set:       %3d cohorts x %d day types = %d rows, exact"
      % (len(cohort), len(DAYS), len(rows)))
```

Result:

```
sho:            82 rows, worst relative error 4.138e-06
emissionQuant: 250 rows, worst relative error 8.231e-06 at (day 5, MY 2002, fuel 5)
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
| `the_ev_temperature_branch_is_reachable` | override `temperature` to 40 °F → factor 1.0219 | same reason: assert both arms |
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

### 7.3 The measured decomposition that isolates the uncomputed relation

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
reason. `W` has to be computed, and §8.1 says how.

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
computable — §2.2's `stmyFraction > 0` rule reproduces all 125 cohorts exactly,
and the oracle asserts it. What is not computable is the *value* in each cell.
That is a failure shape the `[shortfall]` mechanism cannot express: its record
is `emitted_rows` / `missing_keys` / `extra_keys`, and this would be 250 rows
with the right keys and wrong numbers.

**So this specification does not wire a `fixtures/mixed-onroad.esm`.** A
document that emitted 250 correctly-keyed rows carrying an uncomputed rate
would fail the per-cell gate for a reason no exact record could pin, and one
that read `baserate_1_2020` would pass the gate by transcribing the reference.
Neither is a fidelity test. §9 says what the components deliver instead, and
§8.1 says what has to land before the comparison is worth running.

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

### 8.1 `W[hourDayID, opModeID]` — the one relation this port does not compute

**What it is.** The speed-bin-weighted, drive-cycle operating-mode
distribution for running exhaust. `crates/moves-calculators/src/generators/baserategenerator/drivecycle.rs:354-622`,
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
is computed inside the worker and dropped.

**What computing it requires.** Five things, all present in the snapshot:

1. `drivescheduleassoc` (11 rows) → the drive schedules for
   `(sourceTypeID 21, roadTypeID 4)`, and the bracketing of each `avgSpeedBin`
   between two schedules with a `schedule_fraction`
   (`drivecycle.rs:359`).
2. `driveschedulesecond` (63,602 rows) → the second-by-second speed trace.
3. Acceleration, `a[s] = v[s] − v[s−1]` — a **neighbouring-row read**, which
   finding F11 says needs a second relation over a second index set. The
   braking modes additionally need a 3-second lookback
   (`operatingmode.brakeRate3Sec`), i.e. three more.
4. `sourceusetypephysicsmapping` (1 row: rollingTermA 0.156461,
   rotatingTermB 0.00200193, dragTermC 0.000492646, sourceMass 1.4788,
   fixedMassFactor 1.4788, opModeIDOffset 1000) → VSP per second. The mapping
   is per `(sourceTypeID, regClassID, model-year range)`, so the distribution is
   **model-year dependent** in general; this fixture's single row spans
   1950–2060, so here it is not.
5. `operatingmode` (60 rows) → the classification. `VSPLower`/`VSPUpper` and
   `speedLower`/`speedUpper` are a genuine range predicate — a `filter`, not a
   `join.on` — and then a count per mode over total seconds.

**Is it expressible?** Every piece has a spelling: the VSP polynomial is
arithmetic, the neighbouring-row reads are F11's documented workaround, the
mode classification is a `filter` over inclusive/exclusive bounds, and the
per-schedule normalisation is `share_of_group` (§4.2). What it is *not* is
small: a 63,602-row relation joined to a 60-row one under a range predicate,
which is precisely the "big table meets big table" shape finding **F17**
measures as undriven. The `engine_tech_rows` remedy F17 records — give the
thing the tables meet at an axis — applies directly: `operating_mode_rows` is
23 members and each side joins to it separately.

**Why it is not in this phase.** No captured intermediate to verify it
against. The 46 numbers of §7.3 were fitted to the reference's own base rates,
so checking a computed `W` against them is not independent evidence; it is
checking the port against a rearrangement of the port's target. Landing `W`
without an independent check would put a 63,602-row VSP computation into the
tree with nothing to catch a wrong sign — and this project's characteristic
failure is a plausible wrong number on a document that validates.

The honest sequence is: compute `W`, check it against `MOVESOutput` end to end
(which §7.3 shows is a sufficient check, because the factorisation is exact and
everything else is verified), and only then wire the fixture. That is one
coherent piece of work and it is Phase 4's.

### 8.2 Things verified empirically but not in canonical code

* **The `1 055 055.85` in the snapshot** versus `moves.rs`'s
  `1055.0559e6/1000 = 1 055 055.9`. The snapshot stores 6 significant figures
  so the eighth-figure difference is unobservable (§5.6). Canonical MOVES's own
  `EnergyMeasurementSystem` was not read.
* **The absence of `weeksPerMonth` on the output.** Inferred from
  `plan.rs:455-478` (`Hour` timestep → `PortionOfWeekPerDay`) *and* confirmed
  numerically: including it would multiply every row by 4.43.
* **`sourceBinActivityFraction` equalling `stmyFraction` exactly** on all 125
  rows. This means the `fuelusagefraction` remap is effectively the identity
  for this county/year, which follows from its 5 rows but was not traced
  through `county_year_distribution` line by line.

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

1. **`onroad_travel_fraction`** — S1–S3. The population product and the
   HPMS-normalised travel fraction. The one thing to get right is J5's
   denominator group (§6.6 test 1).
2. **`onroad_vmt_allocation`** — S4–S5, S7. The VMT chain, including
   `weeksPerMonth` as a divisor.
3. **`onroad_average_speed`** — S6. Arithmetic mean, not harmonic.
4. **`onroad_source_hours`** — S8–S9. The divide and the spatial allocation.
   `sho` is the stage with an independent reference (§6.1–§6.4 all print it).
5. **`onroad_source_bin_distribution`** — S10–S12. The `stmyFraction > 0` row
   rule is the whole point of this component; it decides the key set.
6. **`onroad_energy_output`** — S15(f), S16–S18. The EV divisor, the
   `noOfRealDays` divide, the energy conversion, the arithmetic SCC, and the
   output relation's key columns.

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
* **One relation that is not computed** (§8.1). It has a name, a shape, a
  source line, an exact size (46 numbers), and a measured proof that everything
  around it is right (§7.3). Say so in the document, at the point where a
  reader would otherwise assume the number was computed —
  `docs/esm-conventions.md` §15.
