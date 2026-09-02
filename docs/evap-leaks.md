# `process-evap-leaks` — computation specification

The third port specification in this repository, and the first of PLAN.md §3
Phase 4. Its two companions are `docs/nonroad-logging-county.md` (a Fortran
chain) and `docs/mixed-onroad.md` (a SQL-graph rates-first chain); this one is a
SQL-graph *inventory* chain, which is the third of the three shapes MOVES has.

What it specifies: how canonical MOVES turns the `process-evap-leaks` snapshot's
input tables into its 128 rows of `MOVESOutput`, in enough detail to author the
`.esm` from the document alone, and with an independent reproduction
(`./run-leaks-oracle.sh`, §6.5) whose numbers can be checked against the
snapshot without reading this file.

Sources, in the order they were trusted:

1. `../moves.rs/crates/moves-calculators/src/calculators/liquid_leaking_calculator.rs`
   — the port of `LiquidLeakingCalculator.java` + `.sql`, with `INPUT_TABLES`
   declared and the SQL step labels (LL-1, LL-8, LL-9) preserved.
2. `.../generators/evap_op_mode_distribution.rs`,
   `.../generators/totalactivitygenerator/`,
   `.../generators/source_bin_distribution_generator.rs` — the three generators
   that produce this calculator's non-default inputs.
3. `crates/moves-runspec/src/xml_format.rs` and
   `crates/moves-calculators/src/default_db_setup.rs` — for the run scope, and
   for §0.1, which corrects a claim in `docs/mixed-onroad.md`.
4. The snapshot itself: 375 declared tables, **234 non-empty**, plus the
   expected `MOVESOutput`.

---

## 0. The fixture at a glance

| | |
|---|---|
| snapshot | `../moves.rs/characterization/snapshots/process-evap-leaks` |
| aggregate sha256 | `e30be8210a7502636e5d1507a12477d1efe4022640c2afd16844ebaa00c0b556` |
| output database | `out_process_evap_leaks` |
| `MOVESOutput` rows | **128** |
| pollutant / process | THC (1) × Evap Fuel Leaks (13); `polProcessID` **113** |
| calculator | `LiquidLeakingCalculator`, a *direct* master-loop subscriber (process 13, `MONTH` granularity) |
| year / month / hour | 2020 / 8 / 7 |
| day types | 2 (weekend) and 5 (weekday) — `hourDayID` 72 and 75 |
| county / zone / link | 26161 (Washtenaw, MI) / 261610 / 2616104 |
| link road type | **4**, Urban Restricted Access — an *on-network* link, and §2.1 shows this is what makes the whole slice tractable |
| source type | 21, Passenger Car |
| fuel types in scope | 1, 2, 5, 9 — of which **1 and 5 reach the output** (§0.2) |
| emitted mass | 960.061201 g THC |

The chain is short: activity → cohorts → a base rate read from a table → one
multiplication. There is no temperature adjustment, no fuel adjustment, no
humidity term, no A/C term and no speciation. That is why it was chosen (§0.3).

### 0.1 The RunSpec XML and the execution database agree — and `mixed-onroad` §0.1 is wrong about why

`docs/mixed-onroad.md` §0.1 opens with a five-row table headed "`mixed-onroad.xml`
says / the execution database says" and explains the difference as a stale
capture: "the file was *rewritten* when the former `mixed-onroad-nonroad`
scenario was split … The tables were not re-captured."

**That explanation is wrong for three of the five rows, and this matters because
the rule it supports is stated for the wrong reason.** Measured over all 27
onroad fixtures in the corpus, *every single one* shows the same offsets:

| | XML | execution database | across all 27 onroad fixtures |
|---|---|---|---|
| month | `<month key="7">` | `runspecmonth` = 8 | XML key = DB id − 1, **27/27** |
| hour | `<beginhour key="6">` | `runspechour` = 7 | XML key = DB id − 1, **27/27** |
| day | `<day key="5">` | `runspecday` = {2, 5} | one key in, both day types out, **26/27** (`expand-day` selects keys 2 and 5 and also gets {2, 5}) |

A stale rewrite does not reproduce itself identically 27 times. The real reason
is in the canonical XML semantics, and both halves are in the `moves.rs` source:

* **`crates/moves-runspec/src/xml_format.rs:600-626`.** "In canonical
  `RunSpecXML`, a `@key` attribute is a **0-based index** into the sorted ID
  list (`TimeSpan.getMonthByIndex` / `getHourByIndex`), while `@id` (MOVES 5) is
  the literal ID. Month IDs (1..12) and hour IDs (1..24) are contiguous from 1,
  so the literal ID equals `key + 1`." So `<month key="7">` **is** monthID 8 and
  `<beginhour key="6">` **is** hourID 7. There is no disagreement to explain.
* **`crates/moves-calculators/src/default_db_setup.rs:2504-2540`.** `<day key>`
  is a 0-based index into the sorted `DayOfAnyWeek` list, which is `[2, 5]`. So
  key 0 → day 2, key 1 → day 5, and **key 5 is out of range**: "canonical adds
  no day and the execution time span falls back to ALL day types — the common
  `<day key="5"/>` fixtures". `{2, 5}` is not an expansion of a weekday
  selection; it is the fallback for a selection that selected nothing.

The remaining two rows of that table are genuine and were already right:
`runspecsourcefueltype` expands one `(21, 1)` selection over every fuel
`fuelengtechassoc` lists (`default_db_setup.rs:2666-2716`), and the pollutant /
process set is filtered. For **this** fixture the XML's three
`<pollutantprocessassociation>` entries (1×13, 86×13, 87×13) map exactly onto
the database's `{113, 8613, 8713}`, with no divergence at all.

**The authoring rule is unchanged and its reason is now stronger.** Take the run
scope from the execution database's `runspec*` tables. Not because the XML might
be stale, but because **the XML's `@key` attributes are 0-based indices into
sorted ID lists, and a document that reads them as identifiers is off by one in
month and hour and wrong wholesale in day** — a systematic error, present in
every fixture, which no amount of re-capturing would fix.
`components/onroad_energy_output.esm`'s
`the_scope_columns_come_from_the_execution_database` test is still the right
test; only its description's reasoning needs the correction.

### 0.2 Why 128 rows, and why only THC

```
128 = 64 (modelYearID, fuelTypeID) cohorts  x  2 day types
64  = 41 model years on gasoline (1980-2020) + 23 on E85 (1998-2020)
```

Two suppressions produce the 64, and both were measured rather than assumed.

**Diesel and electricity carry no leak rate.** `sourceBin` holds 22 gasoline,
21 diesel, 19 E85 and 18 electricity bins for this run; `emissionRateByAge`
carries rows for **all 22 gasoline and all 19 E85 bins and for none of the 39
diesel or electricity bins**. So the LL-8 inner join to `EmissionRateByAge`
already removes them. The SQL *also* joins `FuelType` on
`subjectToEvapCalculations = 'Y'`, which is `Y` for gasoline and E85 and `N` for
diesel and electricity — the same answer by a second route. §7.2 measures the
flag's effect on this fixture as **exactly zero**: removing it changes neither
the key set nor any cell. It is in §1.3, not §1.2, for that reason, and a
document that omits it is right here and wrong for a fixture whose base-rate
table happens to cover a fuel the flag excludes.

**The 41 and the 23 are ragged, and the raggedness comes from
`samplevehiclepopulation.stmyFraction > 0`.** This is `docs/mixed-onroad.md`
§2.2's row rule, unchanged, reached through the same generator: the surviving
125 `(modelYear, fuel)` cohorts are 41 gasoline, 40 diesel, 23 E85 and 21
electricity, and dropping the two fuels with no rate leaves 64. E85 starts at
model year 1998 because that is the first year with a non-zero `stmyFraction`.

**Only THC (pollutant 1) is emitted, although the run selects three
pollutants.** `runspecpollutantprocess` is `{113, 8613, 8713}` and
`pollutantprocessassoc` records `8613` (TOG) as `chainedto1 = 8013` and `8713`
(VOC) as `chainedto1 = 7913`. Neither `8013` (NMOG × 13) nor `7913` (NMHC × 13)
is in the run's pollutant-process set, so `HCSpeciationCalculator` has no input
to chain from and contributes nothing. `hcspeciation` has 81 rows and is read by
nothing. This is a *structural* explanation, checkable in one join, and it is
worth having because the alternative reading — "speciation ran and produced
zeros" — would make three quarters of the expected output silently absent.

### 0.3 Why this slice, and why not the others

Phase 3 closed by naming start exhaust as Phase 4's cheapest slice "because its
operating-mode distribution IS in the snapshot". That claim is wrong; PLAN.md
now records the correction, and this is the measurement behind it.

**There is no start-exhaust target anywhere in the corpus.** Over all 39
snapshots, `MOVESOutput` contains **zero rows with `processID` 2**. The
mechanism is `docs/mixed-onroad.md` §0.2's, and it is not specific to that
fixture: all 27 onroad fixtures select `runspecroadtype = {4}`, while
`BaseRateGenerator` emits start, extended-idle, APU and crankcase-start rates on
`roadTypeID` 1, so `BaseRateCalculator`'s join to `runSpecRoadType`
(`baseratecalculator/mod.rs:773-781`) discards all of them. The same join is why
the eight zero-output-row fixtures (`process-apu*`, `process-extended-idle*`,
`process-crankcase-extidle*`, `process-crankcase-start*`) are zero. A slice with
nothing to check against is not the cheapest available; it is the only kind that
cannot be checked at all.

So the candidates are the non-empty onroad fixtures, screened against the two
things that are blocked — the drive-cycle operating-mode distribution `W`
(`docs/mixed-onroad.md` §8.1) and finding **F12**, a recurrence over an index
axis:

| candidate | rows | verdict |
|---|---|---|
| `process-brakewear`, `process-tirewear`, `process-pm-exhaust`, `process-crankcase-running`, `chain-*`, `process-airtoxics`, `process-nox-speciation`, `expand-*` | 250–1,456 | **needs `W`.** Every one emits `processID` 1 rows, which are base-rate rows on road type 4 and therefore drive-cycle rows |
| `process-refueling` | 336 | **needs `W`.** `RefuelingLossCalculator` is *chained*, not a direct subscriber: it hangs off the calculators that produce Total Energy Consumption (pollutant 91) for processes 1, 2, 90 and 91 — in this runtime, `BaseRateCalculator`. Its snapshot carries `baserate_1_2020` (250 rows) and `baserate_2_2020` (1,664) for that reason |
| `process-evap-fvv` | 128 | **needs F12.** `MultidayTankVaporVentingCalculator` inserts a *soak-day recurrence* between TVV-4 and TVV-5 — `tvg_soak_recurrence` accumulates a running canister load `Xn` across soaking days, back-purged and capped each day |
| `process-evap-permeation` | 128 | **needs F12, one step removed.** PC-2a joins `AverageTankTemperature`, which is TTG-5's output, and TTG-1b is a *quarter-hour tank-temperature recurrence* (`tank_temperature_generator.rs:1-60`). The value is in the snapshot, so it could enter as data — but that is a carried column in the middle of a four-stage calculator, not at its edge |
| **`process-evap-leaks`** | **128** | **needs neither.** See below |

**Evap fuel leaks needs neither, and the reason is worth stating precisely
because it is the whole argument for the slice.**

1. *No `W`.* The emission is `weightedMeanBaseRate × sourceHours ×
   opModeFraction ÷ noOfRealDays`. The base rate is `EmissionRateByAge`, a
   **default-database input table** — so this chain replaces exactly the one
   relation Phase 3 could not compute, and replaces it with a table.
2. *No tank temperature.* Leaks has no temperature term at all. Compare
   permeation, whose `weightedTemperatureAdjust` is the reason its base rate is
   not enough.
3. *The one F12-derived quantity it does touch enters at a **computed** weight of
   zero.* The evap operating-mode distribution (§2.3) splits activity as
   `soakActivityFraction × (1 − fractionOfOperating)` for the soak modes and
   `1 − Σ(those)` for operating mode 300, where
   `fractionOfOperating = least(1, ΣSHO / ΣsourceHours)`. `soakActivityFraction`
   is TTG-6's output and is F12-blocked. But at an **on-network** link
   `SourceHours = SHO` **row for row** (`allocation.rs:631-682`), so the ratio
   is exactly 1, the soak weight is exactly 0, and mode 300 takes the whole
   share. This fixture's link is road type 4. Measured: `fractionOfOperating` is
   `1.000000000000` for both `hourDayID`s in the snapshot's own
   `fractionofoperating` table, and the six-row `opmodedistributiontemp` is
   `{150: 0, 151: 0, 300: 1}` for `polProcessID` 113.

Point 3 is the difference between "the number does not matter" and "the number
is multiplied by a zero this document computes". The `.esm` computes the ratio
and the residual; it does not assume them. §7.2 shows what happens when the
residual is not a residual.

**And the slice pays a Phase 3 debt.** `./run-onroad-oracle.sh` has to read
`baserate_1_2020` from the reference. `./run-leaks-oracle.sh` reads nothing from
the reference: it reproduces all 82 rows of `SHO`, all 82 of `SourceHours`, all
125 of the fuel-usage source-bin distribution, all 6 of the evap operating-mode
distribution and all 128 of `MOVESOutput` from input tables alone. So it is the
first end-to-end independent check of Phase 3's activity and cohort spine.

---

## 1. Input inventory

### 1.1 How the set was determined

Four sources, cross-checked, as its two companions do. The cross-checking is
what keeps a table out of §1.2 that is declared and unread, and what keeps one
in that is read and looks inert.

1. **`INPUT_TABLES`, declared per calculator/generator in `../moves.rs`:**
   `liquid_leaking_calculator.rs` (13 entries),
   `evap_op_mode_distribution.rs`, `totalactivitygenerator/mod.rs:2919-2957`
   (36), `source_bin_distribution_generator.rs:1678-1692` (12).
2. **`execution-trace.json`.** For this fixture the trace is **thin and says
   so**: `sources.worker_sql_files` is 0 and `java_classes` contains 177 entries
   of which none is a `calculator` or `generator` kind — the class-load log
   captured the master and framework classes only. The two completed
   specifications faced the same (`nr-logging-county`: 0 SQL files;
   `mixed-onroad`: 0 SQL files, though its class-load log did catch the
   generators). **So there is no SQL-level evidence for this fixture and the
   Rust port is the only executable reference.** That is worth writing down
   rather than implying: source 2 contributed nothing here.
3. **Row counts.** A declared table with zero rows carries nothing, and three
   of them are what make three steps provable no-ops rather than assumed ones:
   `imcoverage` (0), `imfactor` (0) and `opmodedistribution` (0 — §1.4 explains
   where the operating-mode distribution actually is).
4. **Numerical verification.** Every table in §1.2 appears in the §6.5 oracle,
   which reproduces all 128 output rows to 7.29 × 10⁻⁶. A table that could be
   removed from the oracle without changing its answer is in §1.3, not §1.2,
   and §7.2 gives the measured effect of removing each one.

### 1.2 Tables that carry data into the calculation

**Run scope (8).** Pure filters; each is a one- or two-row relation here.

| table | rows | what is read |
|---|---|---|
| `runspecyear` | 1 | `yearID` = 2020 |
| `runspecmonth` | 1 | `monthID` = 8 |
| `runspechour` | 1 | `hourID` = 7 |
| `runspecday` | 2 | `dayID` ∈ {2, 5} |
| `runspechourday` | 2 | `hourDayID` ∈ {72, 75} |
| `runspecsourcetype` | 1 | `sourceTypeID` = 21 |
| `runspecroadtype` | 1 | `roadTypeID` = 4 |
| `runspecsourcefueltype` | 4 | `fuelTypeID` ∈ {1, 2, 5, 9} — the cohort scope filter of C2 |

**Activity — VMT to `SourceHours` (15).** This is `docs/mixed-onroad.md` §1.2's
activity block with `monthofanyyear` and `link` added, and it is identical table
for table, which is the point: the spine is shared.

| table | rows | columns read |
|---|---|---|
| `year` | 63 | `yearID`, `isBaseYear`, `fuelYearID` |
| `sourcetypeyear` | 819 | `sourceTypePopulation` |
| `sourcetypeagedistribution` | 33,579 | `ageFraction` |
| `sourcetypeage` | 533 | `relativeMAR` |
| `sourceusetype` | 13 | `HPMSVtypeID` |
| `hpmsvtypeyear` | 315 | `HPMSBaseYearVMT` |
| `roadtypedistribution` | 5 | `roadTypeVMTFraction` |
| `roadtype` | 6 | `isAffectedByOnroad` (the onroad road-type gate) |
| `monthvmtfraction` | 1 | `monthVMTFraction` |
| `dayvmtfraction` | 8 | `dayVMTFraction` |
| `hourvmtfraction` | 192 | `hourVMTFraction` |
| `monthofanyyear` | 12 | `noOfDays` |
| `avgspeedbin` | 16 | `avgBinSpeed` |
| `avgspeeddistribution` | 3,072 | `avgSpeedFraction` |
| `zoneroadtype` | 4 | `SHOAllocFactor` |

**Cohort structure (5).**

| table | rows | columns read |
|---|---|---|
| `samplevehiclepopulation` | 6,068 | `stmyFraction` — the sole numeric input to the source-bin distribution |
| `pollutantprocessmodelyear` | 333 | `modelYearGroupID` for `polProcessID` 113 |
| `modelyeargroup` | 192 | `shortModYrGroupID` |
| `sourcebin` | 80 | `fuelTypeID`, `engTechID`, `regClassID`, `modelYearGroupID` — the bin definition, and the join partner of `emissionRateByAge` |
| `fuelusagefraction` | 5 | `usageFraction` — the equipped→used fuel rebase, and §7.2 measures it as the largest per-cell factor in the whole chain |

**The rate and the emission (6).**

| table | rows | columns read |
|---|---|---|
| `emissionratebyage` | 6,564 | `meanBaseRate`, keyed `(sourceBinID, opModeID, ageGroupID)` — all rows are `polProcessID` 113 |
| `agecategory` | 41 | `ageGroupID` — the age → age-group map, and §7.2 measures this join as the largest single-factor error available (9.44×) |
| `soakactivityfraction` | 4 | `soakActivityFraction` — at a computed weight of zero here (§0.3, §2.3) |
| `opmodepolprocassoc` | 27 | which operating modes `polProcessID` 113 admits |
| `pollutantprocessassoc` | 3 | `processID`, `pollutantID` for the output row; `chainedto1` for §0.2 |
| `sourcetypemodelyear` | 533 | `sourceTypeModelYearID` ↔ `(sourceTypeID, modelYearID)` |

**Output stage (3).**

| table | rows | columns read |
|---|---|---|
| `hourday` | 48 | `hourDayID` ↔ (`dayID`, `hourID`) |
| `dayofanyweek` | 2 | `noOfRealDays` = 2 and 5 |
| `link` | 1 | `roadTypeID` = 4, `zoneID`, `countyID` |

**Total: 37 tables carry data.**

### 1.3 Tables joined whose effect on this fixture is measurably zero

Not "unread". Each is joined, each produces a factor or a filter, and each one's
effect here is exactly nothing. §7.2 is the measurement.

| table | rows | why the effect is zero |
|---|---|---|
| `fueltype` | 4 | `subjectToEvapCalculations` excludes diesel and electricity — which `emissionRateByAge` already excludes by carrying no rows for their 39 bins (§0.2). Removing the flag changes nothing: 128 rows, worst cell 4.38 × 10⁻⁶ either way |
| `pollutantprocessmodelyear` (as LL-8's *existence* filter) | 333 | every `(113, modelYearID, modelYearGroupID)` triple the chain reaches is present. The table is still in §1.2 — C3 *reads* `modelYearGroupID` from it — but its LL-8 re-check admits everything |
| `imcoverage`, `imfactor` | **0** | both empty, so LL-1 produces no `IMAdjustFract` cell and LL-9's I/M blend leaves every row untouched. `pollutantprocessassoc` says 113 is `isAffectedByEvapIM = 'Y'`, so this is an empty *program* table and not a structural exclusion — a county with an evap I/M program would exercise it |
| `emissionratebyage.meanBaseRateIM` | — | present and non-null on some rows, and multiplied by an `IMAdjustFract` that does not exist |
| `soakactivityfraction` | 4 | multiplied by `1 − fractionOfOperating` = 0 (§0.3 point 3). The values are 0.00668717 / 0.993313 at `hourDayID` 72 and 0.0221274 / 0.977873 at 75; they reach the answer at weight zero |

Two of these are worth a test on both arms, and §6.6 says which: the I/M blend
(`lib/adjustments.esm`'s `im_blend`, authored in Phase 1 for exactly this and
unexercised until now) and the soak split.

### 1.4 Non-empty tables that are not inputs to this chain

* **`opmodedistribution` is EMPTY, and the operating-mode distribution this
  calculator reads is in `opmodedistributiontemp` (6 rows).** This is the one
  place a reader can go wrong by looking at the obvious table.
  `EvaporativeEmissionsOperatingModeDistributionGenerator` writes
  `OpModeDistribution` with an `INSERT IGNORE` and MOVES's execution-database
  lifecycle then clears it (`evap_op_mode_distribution.rs`'s "Out of scope"
  note describes the `cleanDataLoop` / `DELETE FROM OpModeDistribution` that
  does it). `opmodedistributiontemp` is the surviving capture and it carries
  exactly the 6 rows §2.3 computes. **The `.esm` computes them; the table is a
  check, not an input.**
* **`sourcehours` (82 rows) and `sho` (82 rows) are generator output, not
  input.** They are numerically identical row for row (measured; §2.1 A10 gives
  the reason), and both are checks. A fixture that read either would be
  transcribing the reference's own intermediate.
* **The tank-temperature chain — `averagetanktemperature` (288),
  `hotsoaktemperature` (182,532), `operatingtemperature` (14,462),
  `quarterhourtanktemperature` (96), `coldsoaktanktemperature` (24),
  `hotsoakeventbyhour` (19,573), `samplevehicletripbyhour` (7,329),
  `tempvehandttg` (2,336), `ttgeminutes`/`ttgominutes`.** All of it is
  `TankTemperatureGenerator`'s output or working set. Leaks reads exactly one
  thing out of it, `soakactivityfraction`, at weight zero. Permeation and FVV
  read much more, which is §0.3's point.
* **`hcspeciation` (81 rows)** — the speciation chain has no input (§0.2).
* **The NONROAD residue** — 29 non-empty `nr*` tables
  (`nrbaseyearequippopulation` 62,699 rows, `nremissionrate` 55,471,
  `nrgrowthindex` 50,955, …), left over from the un-split scenario exactly as
  `docs/mixed-onroad.md` §1.4 records. No onroad generator declares any of them.
* **`emissionrate` (0 rows), `baserate*` (0 rows), `sbweightedemissionrate`
  (0 rows), `ratesopmodedistribution` (0 rows).** The rates-first path did not
  run at all for this fixture. That is the cleanest possible confirmation of
  §0.3: this chain does not touch the machinery `W` is missing from.
* **`startsopmodedistribution` (656 rows)** is non-empty in *every* fixture in
  the corpus, including the eight with no output. It is a default-database
  table, not evidence that starts were computed.

### 1.5 The recurrences in this chain, and what happens to each

`docs/mixed-onroad.md` §1.5 records two folds in `TotalActivityGenerator` that
collapse because the base year equals the analysis year (`year.isBaseYear = 'Y'`
at 2020, so the population and VMT growth folds are empty products). Both
collapse here for the same reason and the oracle asserts it.

The third recurrence is the one §0.3 is about, and it does **not** collapse: the
quarter-hour tank-temperature fold behind `soakActivityFraction`. It is F12, it
is not computable, and it enters this chain multiplied by zero. There is no
fourth.

---

## 2. The computation chain

Nineteen steps in five stages. `A*` is `TotalActivityGenerator`, `C*` is
`SourceBinDistributionGenerator`, `E*` is
`EvaporativeEmissionsOperatingModeDistributionGenerator`, `L*` is
`LiquidLeakingCalculator` (keeping the SQL's own LL-n labels), and `O*` is
output aggregation.

| step | quantity | source | new to this slice? |
|---|---|---|---|
| A1 | base year | `year.isBaseYear` | no — `mixed-onroad` S1 |
| A2 | `sourceTypeAgePopulation` | `population.rs` | no — S2 |
| A3 | `travelFraction` | `travel.rs:99-103, :200-204` | no — S3 |
| A4 | `analysisYearVMT` | `vmt.rs` | no — S4 |
| A5 | `annualVMTByAgeRoadway` | `vmt.rs:88-96` | no — S5 |
| A6 | `averageSpeed` | `activity.rs:147-150` | no — S6 |
| A7 | `vmtByAgeRoadwayHour` | `vmt.rs:170-194` | no — S7 |
| A8 | `SHOByAgeRoadwayHour` | `activity.rs:186-205` | no — S8 |
| A9 | `SHO` | `allocation.rs:201` | no — S9 |
| **A10** | **`SourceHours`** | `allocation.rs:631-682` | **yes** |
| C1 | model-year window | `source_bin_distribution_generator.rs:1219-1227` | no — S10 |
| C2 | `sbdgsvp`, the row rule | `:1336-1394` | no — S11 |
| C3 | `sourceBinActivityFraction` | `:1424-1445` | no — S12 |
| C4 | the fuel-usage rebase | `:1534-1637` | no — S12 |
| **E1** | **`fractionOfOperating`** | `evap_op_mode_distribution.rs:350` | **yes** |
| **E2** | **the soak modes** | `:443` stage 2 | **yes** |
| **E3** | **operating mode 300** | `:443` stage 3 | **yes** |
| **L1** | **`IMCoverageMergedUngrouped`** | `liquid_leaking_calculator.rs:606` | **yes** |
| **L8** | **`WeightedMeanBaseRate`** | `:694-806` | **yes** |
| **L9** | **the emission and the I/M blend** | `:859-1020` | **yes** |
| O1–O3 | the output row | `engine.rs:1450-1477` (SCC) | mostly no |

Nine of nineteen are new. The other ten are `docs/mixed-onroad.md` §2.1–§2.2
unchanged, and §7.1 measures how unchanged: the fuel-usage source-bin
distribution this fixture's snapshot carries for `polProcessID` 113 is
**bit-identical**, on all 125 keys, to the one the `mixed-onroad` snapshot
carries for `polProcessID` 1.

### 2.1 Activity — VMT to `SourceHours` (A1–A10)

A1–A9 are `docs/mixed-onroad.md` §2.1 steps S1–S9 with `hourID` 7 in place of
9. Read that document for them; three things it says are worth repeating because
getting any of them wrong changes every one of the 128 rows:

* `averageSpeed` is the **arithmetic** mean `Σ avgSpeedFraction × avgBinSpeed`,
  not the harmonic mean (`activity.rs:147-150`). At hour 7 the arithmetic means
  are 67.0416879 and 56.361205525 mph and the harmonic means of the same two
  distributions are 54.2427 and 35.5758 — 24 % and 58 % low. (At `mixed-onroad`'s
  hour 9 the gaps are 34 % and 95 %, so this fixture is a *weaker* test of that
  choice, not a stronger one; the component test that pins it lives in
  `components/onroad_source_hours.esm` and stays keyed to hour 9.) Since A8
  divides by this number the error goes straight to the output.
* `weeksPerMonth = noOfDays / 7` is a **divisor** (`vmt.rs:194`), 31/7 =
  4.428571 for August. Omitting it multiplies every row by 4.43.
* `SHOAllocFactor` is **purely spatial** (`allocation.rs:201`), 0.001645627794
  for zone 261610 road type 4.

**A10 — `SourceHours`, and the one line the whole slice rests on.**
`allocation.rs:631-682`, canonical `TotalActivityGenerator.java` step 190:

```
the zone's off-network link (roadTypeID 1, where soak/parked activity lives)
    gets  SourceHours = SHP
on-network links
    get   SourceHours = SHO
```

`link` has one row and its `roadTypeID` is **4**. So

```
SourceHours[hourDayID, ageID] = SHO[roadTypeID 4, hourDayID, ageID]
```

row for row, and `SHP` — which is
`population × noOfRealDays − Σ_roadType SHO` (`activity.rs:498-563`, step
180i) — is never materialised for this run. Measured on the snapshot: all 82
rows of `sourcehours` equal all 82 rows of `sho` **exactly**, and both sums are
594.229522 h at `hourDayID` 72 and 5654.364 h at 75.

That row-wise identity is what §0.3 point 3 turns into a computed zero, and it
is why the identity is stated as a row-wise one rather than as an equality of
sums: the sums being equal is a consequence, and a document that computed only
the sums would be right for the wrong reason.

### 2.2 Cohort structure — the source-bin distribution (C1–C4)

`docs/mixed-onroad.md` §2.2, with `polProcessID` 113 in place of 9101. All four
steps and both suppressions are unchanged, and
`components/onroad_source_bin_distribution.esm` already implements them. Recap
of what the `.esm` must not lose:

* **C2's row rule is `stmyFraction > 0.0`** (`:1337-1341`), and it is what makes
  the key set ragged. 164 candidate rows for source type 21 in the window
  [1980, 2020]; 39 carry exactly `0.000000000000`; the surviving **125** are the
  cohorts.
* **C1's window** is `[min(runspecyear) − max(agecategory.ageID),
  max(runspecyear)]` = [1980, 2020].
* **C3 does no normalisation.** `sourceBinActivityFraction` is a bare sum of
  `stmyFraction` over the `(sourceTypeModelYearID, sourceBinID)` group; its
  sum-to-1 property is inherited from the input.
* **`sourceBinID` is ≈1.01 × 10¹⁸ and past 2⁵³.** Key on the four components.
  The *join* on the packed id is still exact (two bins differ by ≥ 10¹⁰ and
  binary64 spacing there is 128), which matters because `emissionRateByAge`
  arrives with the id already packed and carries no component columns —
  `lib/onroad_activity.esm`'s `source_bin_slot` is the inverse.
* **C4, the equipped→used fuel rebase, is load-bearing and a per-pollutant total
  cannot see it.** `sourceBinDistributionFuelUsage[stmy, pp, used] =
  Σ_equipped usageFraction[equipped→used] × sourceBinActivityFraction[stmy, pp,
  equipped]` (`:1590-1637`), where the equipped→used pairing keeps
  `(engTechID, regClassID, modelYearGroupID, engSizeID, weightClassID)` and
  changes only the fuel (`:1534-1570`). For county 26161 / fuel year 2020 the
  only non-identity row is E85: `usageFraction` 0.982134 to gasoline and
  0.017866 to E85. Measured: using the raw distribution instead makes the worst
  cell wrong by a factor of **55.0** and the median cell by 3.2 %, while the
  total THC changes from 960.0610 g to 960.0610 g — **the same number to seven
  significant figures.** §7.3 is about that.

**One spelling note the `.esm` needs and `mixed-onroad` did not.** C4's
`equipped → used` pairing is written in the Rust as a nested loop over
`source_bins` twice, which is a **relation joined to itself** (finding F11).
`components/onroad_source_bin_distribution.esm` already carries the F11
workaround — a second relation over `svp_equipped_rows` — and it is the same
workaround here. But there is a cheaper spelling available in this chain and it
is worth naming: the used bin differs from the equipped bin **only** in
`fuelTypeID`, so the used bin's component tuple is
`(fuelSupplyFuelTypeID, engTechID, regClassID, modelYearGroupID)` — available
from the equipped row and the `fuelusagefraction` row without consulting
`sourceBin` a second time. What the second consultation adds is an *existence*
condition (the used bin must be in `sourceBin`), and that is a **semi-join**,
which `docs/esm-conventions.md` §3 spells `bool_and_or` with a numeric body. So
the self-join is avoidable here where it was not in Phase 3, and §7.2 records
that on this fixture the existence condition admits every pair, so the two
spellings agree.

### 2.3 The evap operating-mode distribution (E1–E3)

Source: `crates/moves-calculators/src/generators/evap_op_mode_distribution.rs`,
port of `EvaporativeEmissionsOperatingModeDistributionGenerator.java`. Three SQL
steps, all tagged `@step 010`. The generator subscribes to processes 11, 12 and
13 at `MONTH` granularity; a fourth name in the Java's `subscribeToMe`, "Evap
Non-Fuel Vapors", resolves to no process in the MOVES5 default database and the
null guard drops it.

**E1 — `FractionOfOperating`** (`:350`). Per `(hourDayID, sourceTypeID)`:

```
fractionOfOperating = least(1, COALESCE(SUM(SHO), 0) / SUM(sourceHours))
```

both sums over the age dimension. On this fixture, by A10's row-wise identity,
numerator and denominator are the same 41 numbers, so

```
fractionOfOperating[72] = 594.229522 / 594.229522 = 1
fractionOfOperating[75] = 5654.364    / 5654.364    = 1
```

and the snapshot's own `fractionofoperating` table stores
`1.000000000000` twice. **The `least(1, ·)` clamp sits exactly on its
boundary here**, which is the most fragile place a number can sit (the same
observation `docs/mixed-onroad.md` §1.3 makes about its two clamps), so §6.6
asserts both arms with probe rows rather than only the value this fixture takes.

**E2 — the soak modes** (`:443`, stage 2). `SoakActivityFraction ⋈
FractionOfOperating` on `(sourceTypeID, hourDayID)`, `⋈ OpModePolProcAssoc` on
`opModeID`, `⋈ PollutantProcessAssoc` on `polProcessID` filtered to the loop's
process, with `SoakActivityFraction` keyed at the context's `monthID` and
`zoneID`:

```
opModeFraction[opMode] = soakActivityFraction[opMode] × (1 − fractionOfOperating)
```

Here `1 − 1 = 0`, so both soak modes are 0. `opmodepolprocassoc` admits exactly
three modes for `polProcessID` 113 — **150** (hot soaking), **151** (cold
soaking) and **300** (operating) — and `soakActivityFraction` carries only 150
and 151, so stage 2 emits four rows and stage 3 emits the two mode-300 rows.

The generator's own source comment records a defect that was fixed upstream and
that §0.1 is the other half of: "The former `month+1` join was an artifact of
the unconverted RunSpec key — a `<month key="7">` run was processed as monthID 7
while SAF correctly carried monthID 8." That is the same 0-based-index semantics
§0.1 derives, seen from the other end.

**E3 — operating mode 300** (`:443`, stage 3). Per
`(sourceTypeID, hourDayID, linkID, polProcessID)`:

```
opModeFraction[300] = greatest(0, 1 − SUM(opModeFraction over the soak modes))
```

**It is a residual, not `fractionOfOperating`.** On this fixture the two are
numerically indistinguishable (both 1), which is exactly why the distinction has
to be tested rather than trusted: §6.6's probe row at
`fractionOfOperating = 0.6` gives

```
1 − fractionOfOperating = 0.4
opModeFraction[150]     = 0.00668717 × 0.4 = 0.002674868
opModeFraction[151]     = 0.993313   × 0.4 = 0.3973252
Σ(soak)                 = 0.400000068
opModeFraction[300]     = 1 − 0.400000068  = 0.599999932
```

The residual is **0.599999932**, and `fractionOfOperating` is **0.6**. They
differ by 6.8 × 10⁻⁸, because the snapshot's soak pair sums to 1.00000017 rather
than to 1 — six-significant-figure storage. That difference is small, real, and
the signature of the right expression: a document that wrote
`opModeFraction[300] = fractionOfOperating` is right to seven digits on a probe
and exactly right on this fixture, and wrong in general.

### 2.4 The weighted mean base rate (L1, L8)

**L1 — `IMCoverageMergedUngrouped`** (`liquid_leaking_calculator.rs:606`).
Disaggregates each `IMCoverage` program record across the individual model years
its `[begModelYearID, endModelYearID]` range covers and sums
`IMFactor × complianceFactor × 0.01`, grouped by
`(processID, pollutantID, modelYearID, fuelTypeID, sourceTypeID)`.
`imcoverage` and `imfactor` are **both empty here**, so L1 produces nothing and
L9's blend is inert. It is in the chain because `pollutantprocessassoc` marks
113 `isAffectedByEvapIM = 'Y'`: this is an absent *program*, not a structural
exclusion.

**L8 — `WeightedMeanBaseRate`** (`:694-806`), `WithRegClassID` variant.
`BundleUtilities.prepareCountyDataWithRunSpec` unconditionally enables
`WithRegClassID`, so the `NoRegClassID` variant (which writes `regClassID` 0) is
dead in current MOVES and is not ported.

```
weightedMeanBaseRate[polProcessID, sourceTypeID, regClassID, fuelTypeID,
                     monthID, hourDayID, modelYearID, opModeID]
    = SUM over source bins of
        sourceBinActivityFraction × meanBaseRate
```

with five inner joins and two cross joins. Every join is an `INNER JOIN`, so a
row with no partner is dropped:

1. `EmissionRateByAge ⋈ SourceBin` on `sourceBinID`.
2. `⋈ FuelType` on `fuelTypeID` **and** `subjectToEvapCalculations = 'Y'` — an
   existence filter, measurably inert here (§1.3).
3. `⋈ SourceBinDistribution` on `(sourceBinID, polProcessID)`.
4. `⋈ SourceTypeModelYear` on `sourceTypeModelYearID`, **and**
   `stmy.modelYearID = year − AgeCategory.ageID` where `AgeCategory` is joined
   to `EmissionRateByAge.ageGroupID`. **This is the load-bearing join of the
   whole calculator.** `emissionRateByAge` carries seven age groups per
   `(bin, opMode)` — for the 2020 gasoline bin at mode 300 they are 0.1304,
   0.1304, 0.1304, 0.1304, 0.3626, 1.1174 and 3.4536 — and this join picks the
   one whose group contains `2020 − modelYearID`. Removing it sums all seven:
   measured, **9.44× the total** (9,066 g against 960 g) and 41× on the worst
   cell. §7.2.
5. `⋈ PollutantProcessModelYear` on
   `(polProcessID, modelYearID, modelYearGroupID)` — an existence filter, also
   measurably inert here.
6. `⋈ RunSpecSourceType` on `sourceTypeID`.
7. `CROSS JOIN RunSpecMonth, RunSpecHourDay`. **This adds no information.** The
   month and the hour/day come from the run spec, not from any joined data row,
   so the value is replicated across the two `hourDayID`s unchanged. The `.esm`
   therefore carries `weightedMeanBaseRate` over
   `(regClassID, fuelTypeID, modelYearID, opModeID)` and attaches `monthID` and
   `hourDayID` at L9, where they first carry information (`sourceHours` and
   `opModeFraction` are both keyed on `hourDayID`). That is a *stated*
   simplification of the reference's control flow rather than a silent one, and
   it is safe precisely because the cross join has no `ON` clause.

`meanBaseRateIM` is summed the same way into `weightedMeanBaseRateIM`, and is
used only by L9's blend.

### 2.5 The emission and the output row (L9, O1–O3)

**L9** (`:859-1020`). Five more inner joins, then one product:

```
emissionQuant   = weightedMeanBaseRate   × sourceHours × opModeFraction / noOfRealDays
emissionQuantIM = weightedMeanBaseRateIM × sourceHours × opModeFraction / noOfRealDays
```

* `⋈ SourceHours` on `(hourDayID, monthID, yearID, ageID, linkID,
  sourceTypeID)` with **`ageID = year − modelYearID`** and `linkID` the
  iteration link. This is the second place the age relation appears and it must
  agree with L8's.
* `⋈ OpModeDistribution` on
  `(sourceTypeID, hourDayID, linkID, polProcessID, opModeID)`.
* `⋈ PollutantProcessAssoc` on `polProcessID` → `(processID, pollutantID)`.
* `⋈ Link` on the iteration link → `roadTypeID`.
* `⋈ HourDay` on `hourDayID` → `(dayID, hourID)`, then `⋈ DayOfAnyWeek` on
  `dayID` → `noOfRealDays`.

**`÷ noOfRealDays` undoes A7's `× 1/weeksPerMonth` basis change.** A7 divides
the month's VMT by the number of weeks so that `SHO` covers one average week —
that is, `noOfRealDays` days of the day type. L9 divides that back out to one
day. Applying `noOfRealDays` in both places, or in neither, is a factor of 2 on
the weekend rows and 5 on the weekday rows;
`baseratecalculator/mod.rs:1536-1542` records the rates-first analogue.

**The I/M blend**, applied where an `IMCoverageMergedUngrouped` cell matches
`(processID, pollutantID, modelYearID, fuelTypeID, sourceTypeID)`:

```
emissionQuant = GREATEST(emissionQuantIM × IMAdjustFract
                       + emissionQuant   × (1 − IMAdjustFract), 0)
```

This is `lib/adjustments.esm`'s `im_blend` exactly — `max(rate_im × fraction_im
+ rate_base × (1 − fraction_im), 0)` — which Phase 1 authored for "the onroad
inspection/maintenance blend PLAN.md §3 names; it is not exercised by the
NONROAD slice". This slice is the first place it appears in a real chain, and it
is inert here (§1.3), so §6.6 exercises it with a probe `IMAdjustFract`.

The SQL's `UPDATE` is a multi-table update, not a join: a row with **no**
matching cell keeps its value unchanged. `IMCoverageMergedUngrouped` carries at
most one cell per key (it is L1's `GROUP BY` result), so folding the update into
the row loop is equivalent, and the `.esm` spells the absence as
`IMAdjustFract = 0`, for which `im_blend` is the identity.

**O1 — aggregate to the output key.** L9's rows carry `opModeID`; the output row
does not. Two L9 rows can therefore share an output key and their quantities
add. Here that sum is over the three operating modes, of which two contribute
exactly 0.

**O2 — the SCC.** `engine.rs:1450-1477`, and it is *computed*, not looked up:

```
SCC = 22×10⁸ + fuelTypeID×10⁶ + sourceTypeID×10⁴ + roadTypeID×10² + processID
```

= `2201210413` for gasoline and `2205210413` for E85, which is what
`MOVESOutput` carries. `lib/onroad_activity.esm`'s `onroad_scc` is this
template, unchanged from Phase 3.

**O3 — the NULL columns.** `MOVESOutput` has 25 columns; on this fixture **9
are NULL throughout**, measured: `zoneID`, `linkID`, `regClassID`,
`fuelSubTypeID`, `engTechID`, `sectorID`, `hpID`, and the two uncertainty
columns `emissionQuantMean` / `emissionQuantSigma`, which are NULL on any
deterministic run. `regClassID` is NULL even though L8 and L9 carry
it, because the run's `outputemissionsbreakdownselection` does not select
`movesvehicletype`; so O1 aggregates `regClassID` away. On this fixture that
aggregation is a no-op — `sourcebin` carries one regulatory class, 20 — but the
column must still be emitted absent, and `lib/identifiers.esm`'s
`null_output_column` (`0/0`, i.e. NaN) is how a numeric column says absent.
Emitting `0` there would claim regulatory class zero.

---

## 3. Join structure

The A-stage and C-stage joins are `docs/mixed-onroad.md` §3's, unchanged; this
section numbers only the twenty-two that are new (`K1`–`K22`), so that a reader
holding both documents never sees the same join twice under two names.

`docs/esm-conventions.md` §3 is the spelling rule: an equality between key
columns is a `join.on` clause with a key-pair list; a composite key is **one**
clause with several pairs; a range test, a null guard or a set membership is a
`filter`.

| | step | left | right | key pairs | note |
|---|---|---|---|---|---|
| K1 | A10 | `sho` | `link` | `sho_linkID` = `link_linkID` | plus `filter link_roadTypeID ≠ 1`; on a match `SourceHours = SHO`, otherwise `= SHP` |
| K2 | E1 | `sho` | the `(hourDay, sourceType)` group | `sho_hourDayID` = `oper_hourDayID`, `sho_sourceTypeID` = `oper_sourceTypeID` | the numerator's `GROUP BY`, summing over `ageID` |
| K3 | E1 | `sourceHours` | same group | `sh_hourDayID` = `oper_hourDayID`, `sh_sourceTypeID` = `oper_sourceTypeID` | the denominator. A **separate** contraction, because the result is a divisor and needs the zero guard — the same reason `mixed-onroad` J15 is separate |
| K4 | E2 | `soakActivityFraction` | `fractionOfOperating` | `saf_sourceTypeID` = `frac_sourceTypeID`, `saf_hourDayID` = `frac_hourDayID` | one clause, two pairs |
| K5 | E2 | `soakActivityFraction` | `opModePolProcAssoc` | `saf_opModeID` = `omppa_opModeID` | this is what admits 150 and 151 and no other soak mode |
| K6 | E2 | `opModePolProcAssoc` | `pollutantProcessAssoc` | `omppa_polProcessID` = `ppa_polProcessID` | plus `filter ppa_processID = 13`; a **semi-join** — presence, no value — so `bool_and_or` with body `1.0`, bound at the call site as `> 0` |
| K7 | E3 | the E2 rows | the `(sourceType, hourDay, link, polProcess)` group | four pairs, one clause | the residual's `GROUP BY`; `greatest(0, 1 − Σ)` |
| K8 | L8 | `emissionRateByAge` | `sourceBin` | `era_sourceBinID` = `sb_sourceBinID` | on the **packed** id, which is exact (§2.2); no document builds the id |
| K9 | L8 | `sourceBin` | `fuelType` | `sb_fuelTypeID` = `ft_fuelTypeID` | plus `filter ft_subjectToEvapCalculations = 'Y'`, a set membership. Semi-join, measurably inert (§1.3) |
| K10 | L8 | `emissionRateByAge` | `sourceBinDistributionFuelUsage` | `era_sourceBinID` = `sbd_sourceBinID`, `era_polProcessID` = `sbd_polProcessID` | **one clause, two pairs.** A single-key version on `sourceBinID` alone would be right here only because the table holds one `polProcessID` |
| K11 | L8 | `sourceBinDistribution` | `sourceTypeModelYear` | `sbd_sourceTypeModelYearID` = `stmy_sourceTypeModelYearID` | |
| K12 | L8 | `emissionRateByAge` × `sourceTypeModelYear` | `ageCategory` | `era_ageGroupID` = `ac_ageGroupID`, **`ac_ageID` = `stmy_effectiveAgeID`** | the load-bearing one. The right-hand key is **derived**: `stmy_effectiveAgeID = runYearID − stmy_modelYearID`, precomputed as a column and then joined on, per §3's rule. Removing it: 9.44× (§7.2) |
| K13 | L8 | `sourceBinDistribution` × `sourceTypeModelYear` × `sourceBin` | `pollutantProcessModelYear` | `sbd_polProcessID` = `ppmy_polProcessID`, `stmy_modelYearID` = `ppmy_modelYearID`, `sb_modelYearGroupID` = `ppmy_modelYearGroupID` | **one clause, three pairs.** Semi-join; inert here |
| K14 | L8 | `sourceTypeModelYear` | `runSpecSourceType` | `stmy_sourceTypeID` = `rsst_sourceTypeID` | semi-join |
| — | L8 | — | `runSpecMonth`, `runSpecHourDay` | *none* | `CROSS JOIN`, no `ON` clause, no information (§2.4 point 7) |
| K15 | L9 | `weightedMeanBaseRate` | `sourceHours` | `wmbr_hourDayID` = `sh_hourDayID`, `wmbr_monthID` = `sh_monthID`, `wmbr_effectiveAgeID` = `sh_ageID`, `wmbr_sourceTypeID` = `sh_sourceTypeID` | **one clause, four pairs**, plus `yearID` and `linkID` from the iteration context. `wmbr_effectiveAgeID` is the same derived column K12 uses, and the two **must** agree |
| K16 | L9 | `weightedMeanBaseRate` | `opModeDistribution` | `wmbr_sourceTypeID` = `omd_sourceTypeID`, `wmbr_hourDayID` = `omd_hourDayID`, `wmbr_polProcessID` = `omd_polProcessID`, `wmbr_opModeID` = `omd_opModeID` | one clause, four pairs, plus `linkID` from context |
| K17 | L9 | `weightedMeanBaseRate` | `pollutantProcessAssoc` | `wmbr_polProcessID` = `ppa_polProcessID` | carries `(processID, pollutantID)` to the output row |
| K18 | L9 | `weightedMeanBaseRate` | `hourDay` | `wmbr_hourDayID` = `hd_hourDayID` | carries `(dayID, hourID)` |
| K19 | L9 | `hourDay` | `dayOfAnyWeek` | `hd_dayID` = `dow_dayID` | carries `noOfRealDays`, the divisor |
| K20 | L1 | `imCoverage` | `pollutantProcessMappedModelYear` | `im_polProcessID` = `ppmmy_polProcessID` | plus `filter im_begModelYearID ≤ modelYearID ≤ im_endModelYearID` — an **inclusive model-year range**, the shape `docs/esm-conventions.md` §16.3 names: `join.on` over the non-range keys plus a range `filter` |
| K21 | L9 | the L9 rows | `IMCoverageMergedUngrouped` | `ppa_processID` = `im_processID`, `ppa_pollutantID` = `im_pollutantID`, `wmbr_modelYearID` = `im_modelYearID`, `wmbr_fuelTypeID` = `im_fuelTypeID`, `wmbr_sourceTypeID` = `im_sourceTypeID` | one clause, five pairs. An **unmatched row keeps its value**: the SQL is an `UPDATE`, not a join, and the `.esm` spells the miss as `IMAdjustFract = 0`, for which `im_blend` is the identity |
| K22 | O1 | the L9 rows | the output key | `(yearID, monthID, dayID, hourID, stateID, countyID, pollutantID, processID, sourceTypeID, fuelTypeID, modelYearID, roadTypeID)` | the `GROUP BY` that drops `opModeID` and `regClassID`; two rows sharing a key add |

**Three things about this list that are worth stating as rules rather than as
entries.**

1. **Two joins share one derived key column and must not compute it twice.**
   K12 and K15 both key on `runYearID − modelYearID`. `moves.rs` writes the
   subtraction at both sites (`:767` in `weighted_mean_base_rate`, `:935` in
   `calculate`) and they agree; a port that wrote it twice has two chances to
   disagree with itself, exactly as `lib/identifiers.esm`'s description says
   about packing and unpacking `polProcessID`. One column,
   `wmbr_effectiveAgeID`, used by both.
2. **Five of the twenty-two are semi-joins** — K6, K9, K13, K14, and K20's
   existence half. All five are presence tests with no value, so all five are
   `bool_and_or` with body `1.0` and an explicit `> 0` at the call site
   (§3, `docs/esm-conventions.md`).
3. **Nothing here needs a self-join.** §2.2 explains why C4's is avoidable in
   this chain; K1–K22 introduce no new instance of finding F11. That is the
   first stage of this port for which that is true.

---

## 4. Reusable shapes (`expression_templates`)

Five shapes, and **four of the five already exist**. That is the strongest
evidence available that the Phase 1–3 factoring was right, so it is worth
recording which ones and why they fit.

### 4.1 Reused unchanged

| shape | file | what it does here |
|---|---|---|
| `im_blend` | `lib/adjustments.esm` | L9's I/M blend, `max(rate_im·f + rate_base·(1−f), 0)`, **exactly**. Authored in Phase 1 as "the onroad inspection/maintenance blend PLAN.md §3 names; it is not exercised by the NONROAD slice"; this is the first chain that reaches it |
| `pol_process_id` | `lib/identifiers.esm` | `100 × 1 + 13 = 113`. No bare `113` appears in an equation |
| `pollutant_id_of`, `process_id_of` | `lib/identifiers.esm` | O1 splits `113` back into the output's two columns |
| `onroad_scc` | `lib/onroad_activity.esm` | O2, unchanged from Phase 3 |
| `null_output_column` | `lib/identifiers.esm` | O3's nine absent columns |
| `source_bin_slot` | `lib/onroad_activity.esm` | unpacks `emissionRateByAge.sourceBinID`, needed for the same reason `emissionrate` needed it |
| `weeks_per_month`, `share_of_group` | `lib/onroad_activity.esm` | A7 and A3, unchanged |

### 4.2 `soak_share` (new)

E2, `evap_op_mode_distribution.rs:443` stage 2:

```
soak_share(soak_activity_fraction, fraction_of_operating)
    = soak_activity_fraction × (1 − fraction_of_operating)
```

Two parameters, one product. It is a template rather than inline arithmetic for
one reason: **the `(1 − f)` and E3's `(1 − Σ)` are different subtractions and
look alike.** Writing both inline invites a reader — or an author — to treat
`opModeFraction[300]` as `fraction_of_operating`, which §2.3 measures as a
6.8 × 10⁻⁸ error on a probe and an exact agreement on this fixture. Naming the
soak half makes the residual half conspicuous by not having a name.

### 4.3 `operating_share_of_activity` (new)

E1, `:350`:

```
operating_share_of_activity(sho_total, source_hours_total)
    = source_hours_total > 0 ? min(1, sho_total / source_hours_total) : 0
```

The `least(1, ·)` is the reference's; the zero guard is
`COALESCE(SUM(SHO), 0)`'s other half and is the same shape
`lib/onroad_activity.esm`'s `share_of_group` carries. It is **not**
`share_of_group`, and merging them would be wrong: `share_of_group` has no cap,
and a cap on a normalisation would silently change A3.

### 4.4 Deliberately not factored

* **`÷ noOfRealDays`.** It appears once, at L9. `lib/conversion.esm`'s
  `temporal_scale` is NONROAD's `mthf × 7 × dayf / ndays` and
  `lib/onroad_activity.esm`'s `weeks_per_month` is A7's `noOfDays / 7`; this is a
  third thing that carries the same 7-day week and combines it differently. Three
  templates for three combinations, none merged — the mistake
  `docs/esm-conventions.md` §6 already warns about for the first two.
* **`greatest(0, ·)` and `least(1, ·)`.** Two clamps, at E1 and E3, with
  different bodies and different constants, and in both cases the *value the
  clamp takes* is the load-bearing fact. A `clamp01` template would hide which
  clamp is which — the same reasoning `lib/onroad_activity.esm` records for the
  two clamps it declined to factor.
* **The `sourceBinID` packing.** Absent on purpose (§2.2); only the inverse
  exists.

---

## 5. Literals and enums

Every value here is from the snapshot's own tables. No magic integer appears in
an equation (`docs/esm-conventions.md` §4).

### 5.1 Pollutants and processes

| symbol | value | table |
|---|---|---|
| `pollutant.TotalGaseousHydrocarbons` | 1 | `pollutant` |
| `pollutant.TotalOrganicGases` | 86 | `pollutant`; selected, emits nothing (§0.2) |
| `pollutant.VolatileOrganicCompounds` | 87 | `pollutant`; same |
| `process.EvapFuelLeaks` | 13 | `emissionprocess` (1 row: "Evap Fuel Leaks", `occursOnRealRoads = 'Y'`) |
| `polProcessID` | **113** | built by `pol_process_id`, never written |
| chained, absent | 8013, 7913 | `pollutantprocessassoc.chainedto1`; not in `runspecpollutantprocess`, which is why §0.2 holds |

### 5.2 Operating modes

| symbol | value | meaning |
|---|---|---|
| `operating_mode.HotSoaking` | 150 | a vehicle soaking after a recent trip |
| `operating_mode.ColdSoaking` | 151 | a vehicle parked long enough to have cooled |
| `operating_mode.Operating` | 300 | in use; **the only mode with a non-zero fraction here** |

`opmodepolprocassoc` admits exactly these three for `polProcessID` 113, and its
other 24 rows carry `polProcessID` −1 (the drive-cycle modes, unassociated).
**−1 cannot be an `enums` value** — `esm-schema.json` requires a positive
integer, the constraint `docs/esm-conventions.md` §4 records for three NONROAD
identifiers — so the sentinel is a named `parameter`,
`unassociatedPolProcessID`, with the reason in its description. It is the fourth
such value in this port.

### 5.3 Geography, time and vehicles

| symbol | value |
|---|---|
| `state.Michigan` | 26 |
| county | 26161 (`county`, 1 row) |
| zone | 261610 (`zone`) |
| link | 2616104 (`link`, 1 row, `roadTypeID` 4) |
| `road_type.UrbanRestrictedAccess` | 4 |
| `road_type.OffNetwork` | 1 — appears only in A10's `≠` test |
| `month.August` | 8 |
| `hour.SevenAM` | 7 — `hourofanyday[7].hourname` is "Hour beginning at 6:00 AM"; the table has 24 rows. The symbol is named for the ID, not the wall clock |
| `day_type.Weekend` / `.Weekday` | 2 / 5 |
| `hourDayID` | 72, 75 — built as `hourID × 10 + dayID` |
| `source_type.PassengerCar` | 21 |
| `hpms_vtype.LightDutyVehicles` | 25 |
| `reg_class.LightDutyVehicles` | 20 — the only regulatory class in `sourcebin` |

### 5.4 Fuel types, engine technologies and age groups

| symbol | value | `subjectToEvapCalculations` | leak rates in `emissionRateByAge`? |
|---|---|---|---|
| `fuel_type.Gasoline` | 1 | Y | yes, all 22 bins |
| `fuel_type.DieselFuel` | 2 | N | **no**, none of its 21 bins |
| `fuel_type.EthanolE85` | 5 | Y | yes, all 19 bins |
| `fuel_type.Electricity` | 9 | N | **no**, none of its 18 bins |

`engine_tech.ConventionalInternalCombustion` = 1 and `.ElectricDrive` = 30, the
two values `sourcebin` carries — the same two Phase 3 met, which is why
§11.1's "give the thing the tables meet at an axis" does not fire here either
(`docs/esm-conventions.md` §16.3).

`agecategory` maps 41 `ageID`s onto **7** `ageGroupID`s: `3` (ages 0–3), `405`
(4–5), `607` (6–7), `809` (8–9), `1014` (10–14), `1519` (15–19), `2099`
(20–40). The group id is the concatenated range, so `405` is not a number to do
arithmetic on. K12 is the join that uses them and §7.2 is what it costs to get
it wrong.

### 5.5 Physical and dimensioning constants

| constant | value | where |
|---|---|---|
| days per week | 7 | A7's divisor |
| `noOfDays` for August | 31 | `monthofanyyear` |
| `noOfRealDays` | 2 (weekend), 5 (weekday) | `dayofanyweek`; A7 multiplies them in, L9 divides them out |
| `SHOAllocFactor` | 0.001645627794 | `zoneroadtype[261610, 4]` |
| `HPMSBaseYearVMT` | 2 572 988 371 051 | `hpmsvtypeyear[25, 2020]` |
| `roadTypeVMTFraction` | 0.259544 | `roadtypedistribution[21, 4]` |
| `monthVMTFraction` | 0.0934297 | `monthvmtfraction[21, 8]` |
| `usageFraction`, E85 → gasoline | 0.982134 | `fuelusagefraction`; the other 0.017866 stays on E85 |

There is no unit conversion anywhere in this chain: `meanBaseRate` is grams per
hour, `sourceHours` is hours, and the product is grams. `emissionQuant` is
therefore grams and is declared unitless with the unit named in its
description, for the reason `docs/esm-conventions.md` §11 gives — the registry
knows `g` and `h`, but a factor that carries no unit forces the product to carry
none either.

---

## 6. Hand-checkable worked examples

Every number below is either read from the snapshot's input tables or computed
from numbers that are, and each example ends at a cell of `MOVESOutput`. The
`.esm` components' inline assertions are these values (§6.6), so a component
that drifts fails against a number a reader can re-derive with a calculator.

### 6.0 Run-level values used by every example

| quantity | value | source |
|---|---|---|
| `HPMSBaseYearVMT[25, 2020]` | 2 572 988 371 051 | `hpmsvtypeyear`; base year = analysis year, so the growth fold is the empty product (§1.5) |
| `roadTypeVMTFraction[21, 4]` | 0.259544 | `roadtypedistribution` |
| `monthVMTFraction[21, 8]` | 0.0934297 | `monthvmtfraction` |
| `weeksPerMonth` | 31 / 7 = 4.428571428571429 | `monthofanyyear[8].noOfDays` |
| `dayVMTFraction[21, 8, 4, ·]` | 0.237635 (day 2), 0.762365 (day 5) | `dayvmtfraction` |
| `hourVMTFraction[21, 4, ·, 7]` | 0.0184304 (day 2), 0.0459565 (day 5) | `hourvmtfraction` |
| `averageSpeed[21, 4, 72]` | 67.0416879 mph | A6 over all 16 bins; the fractions sum to 1.0000003 |
| `averageSpeed[21, 4, 75]` | 56.361205525 mph | same; the fractions sum to 0.99999901 |
| `SHOAllocFactor[261610, 4]` | 0.001645627794 | `zoneroadtype` |
| `noOfRealDays` | 2 (day 2), 5 (day 5) | `dayofanyweek` |
| HPMS-25 group total, `Σ pop × relativeMAR` | 182 397 687.37007642 | A3's denominator, over source types 21, 31 and 32 |
| `fractionOfOperating[72]`, `[75]` | 1, 1 | E1; the snapshot's `fractionofoperating` stores `1.000000000000` twice |
| `opModeFraction[·, 300]` | 1 | E3; `[·, 150]` and `[·, 151]` are 0 |
| `IMAdjustFract` | absent everywhere | `imcoverage` and `imfactor` are empty |

Activity, for the three ages the examples use (A2 → A9; every figure binary64
from the inputs above):

| `ageID` | `travelFraction` | `annualVMT` | `SHO[72]` | `SHO[75]` | snapshot `sho` |
|---|---|---|---|---|---|
| 0 | 0.018044202932359497 | 12 049 985 369.4745 | 27.330001837636907 | 260.0573038920831 | 27.33 / 260.057 |
| 18 | 0.00822395867146252 | 5 491 989 978.264336 | 12.456122691939292 | 118.52562994539538 | 12.4561 / 118.526 |
| 40 | 0.0016091748533087504 | 1 074 612 910.9711342 | 2.437278712884465 | 23.191807108971084 | 2.43728 / 23.1918 |

and `SourceHours` equals `SHO` at every one of the 82 keys (A10).

### 6.1 Worked example A — model year 1980, gasoline

The oldest cohort in the output, and the one with the largest base rate.

**Cohort (C1–C4).** `samplevehiclepopulation[21, 1980]` has two rows with
`stmyFraction > 0`: gasoline 0.953329 and diesel 0.0466707.
`pollutantprocessmodelyear[113, 1980].modelYearGroupID` = **19781995**, and
`modelyeargroup[19781995].shortModYrGroupID` = 52, so the gasoline bin is

```
1e18 + 1×1e16 + 1×1e14 + 20×1e12 + 52×1e10 = 1010120520000000000
```

which is in `sourcebin` with `modelYearGroupID` 19781995. The fuel-usage rebase
(C4) leaves gasoline unchanged — `usageFraction[1 → 1]` = 1 and no other
equipped fuel maps onto gasoline for this model-year group — so
`sourceBinActivityFraction = 0.953329`.

**The diesel row disappears here and nowhere else.** `emissionRateByAge` has no
row for bin `1020120520000000000`, so K8's inner join drops it; `fuelType`'s
`subjectToEvapCalculations = 'N'` would have dropped it too (K9). Both, so §7.2
measures the second as inert.

**Rate (L8).** `ageID = 2020 − 1980 = 40`, `agecategory[40].ageGroupID` = 2099.
`emissionratebyage[1010120520000000000, 300, 2099].meanBaseRate` = **4.235** g/h.
The mode-150 and mode-151 rates for the same bin and age group are 0.452 and
0.235; both are multiplied by an `opModeFraction` of 0.

```
weightedMeanBaseRate = 0.953329 × 4.235 = 4.037348315
```

**Emission (L9), weekend.**

```
emissionQuant = 4.037348315 × 2.437278712884465 × 1 / 2
              = 4.9200741505916 g
```

`MOVESOutput` stores **4.92007**; relative difference 8.4 × 10⁻⁷.

**Emission (L9), weekday.**

```
emissionQuant = 4.037348315 × 23.191807108971084 × 1 / 5
              = 18.7266749303634 g
```

`MOVESOutput` stores **18.7267**; relative difference 1.3 × 10⁻⁶.

**SCC** = 22×10⁸ + 1×10⁶ + 21×10⁴ + 4×10² + 13 = **2201210413**, which is what
both rows carry.

### 6.2 Worked example B — model year 2020, gasoline

The newest cohort, `ageID` 0, `ageGroupID` 3, and the one where the age-group
join is easiest to get wrong: `emissionratebyage[1010120400000000000, 300, ·]`
is `0.1304` for age groups 3, 405, 607 and 809 and then `0.3626`, `1.1174`,
`3.4536` — so a document that dropped K12 would pick up **41.83×** the right
rate for this cohort alone: the seven values sum to 5.4552 against 0.1304, and
`weightedMeanBaseRate` would be 5.227947278399999 instead of
0.12496779679999999.

`samplevehiclepopulation[21, 2020]`: gasoline 0.958342 (after the rebase), E85
0.000319583, electricity 0.0413386, and **no diesel** — 2020 is the model year
`stmyFraction` goes to zero for diesel passenger cars
(`docs/mixed-onroad.md` §2.2 measures the same thing).
`pollutantprocessmodelyear[113, 2020].modelYearGroupID` = 2020,
`shortModYrGroupID` = 40.

```
weightedMeanBaseRate = 0.958342 × 0.1304 = 0.12496779679999999

weekday: 0.12496779679999999 × 260.0573038920831 / 5 = 6.49975006648352 g
weekend: 0.12496779679999999 ×  27.330001837636907 / 2 = 1.7076849432719998 g
```

`MOVESOutput` stores **6.49975** and **1.70768** — relative differences
1.0 × 10⁻⁸ and 8.5 × 10⁻⁷. The electricity row is absent (no rate rows for
`1093020400000000000`), and the E85 row is present with
`weightedMeanBaseRate = 0.000319583 × 0.1304`.

### 6.3 Worked example C — model year 2002, E85, and the 56× the fuel rebase is worth

`ageID` 18, `ageGroupID` 1519, `modelYearGroupID` 19992003,
`shortModYrGroupID` 56. Four cohorts survive C2 for this model year, and the
rebase changes three of the four fractions:

| fuel | `sourceBinActivityFraction`, raw (C3) | after the rebase (C4) | ratio |
|---|---|---|---|
| 1, gasoline | 0.985306 | **0.993079** | 1.0079 |
| 2, diesel | 0.0046339 | 0.0046339 | 1 |
| 5, E85 | 0.00791484 | **0.000141407** | **0.01786** |
| 9, electricity | 0.00214529 | 0.00214529 | 1 |

E85's 0.982134 usage share moves onto gasoline; 0.017866 stays. Both
`emissionratebyage[1010120560000000000, 300, 1519]` and
`emissionratebyage[1050120560000000000, 300, 1519]` are **1.363**, so the E85
and gasoline rows differ only in that fraction.

```
E85,      weekday: 0.000141407 × 1.363 × 118.52562994539538 / 5 = 0.0045688866979532 g
E85,      weekend: 0.000141407 × 1.363 ×  12.456122691939292 / 2 = 0.0012003802878350499 g
gasoline, weekday: 0.993079    × 1.363 × 118.52562994539538 / 5 = 32.0865687916204 g
```

`MOVESOutput` stores **0.00456889**, **0.00120038** and **32.0866**.

**With the raw C3 fraction instead**, the E85 weekday cell is
`0.00791484 × 1.363 × 118.52562994539538 / 5 =` **0.255729965223984 g** — high
by a factor of 55.97, a relative error of 54.97. §7.3 is about why no total in
this document notices.

### 6.4 Worked example D — the rows that are absent, and the two reasons

`MOVESOutput`'s 128 rows are 64 cohorts × 2 day types. The 125 cohorts C2
produces become 64 by two separate mechanisms, and it is worth being able to
point at one row of each:

| cohort | present? | why |
|---|---|---|
| (1980, fuel 1) | yes | §6.1 |
| (1980, fuel 2) | **no** | no `emissionRateByAge` row for its bin; and `subjectToEvapCalculations = 'N'` |
| (2020, fuel 9) | **no** | same, both reasons |
| (1997, fuel 5) | **no** | `stmyFraction = 0` — E85 passenger cars start at model year 1998, so C2 never produces the cohort |
| (1998, fuel 5) | yes | first E85 model year |
| (2020, fuel 2) | **no** | `stmyFraction = 0` — the year diesel passenger cars stop |

The first three are a *rate* absence and the last three a *cohort* absence, and
they need different spellings: the rate absence is an inner join (K8) and the
cohort absence is the `stmyFraction > 0` row rule in C2. A document that spelled
either as the other would emit the right count on this fixture and the wrong one
on the next.

Aggregate checks, all against `MOVESOutput`:

| | value |
|---|---|
| total THC | 960.061201 g |
| weekend total | 199.755384 g |
| weekday total | 760.305817 g |
| gasoline total | 959.778075 g |
| E85 total | 0.283126 g |
| rows | 41 + 23 gasoline/E85 cohorts × 2 day types = 128 |

The weekday/weekend ratio is 3.806, not 2.5: the day-type split carries
`dayVMTFraction` (0.762365 / 0.237635 = 3.208) and `hourVMTFraction`
(0.0459565 / 0.0184304 = 2.493) and divides `noOfRealDays` (5 / 2 = 2.5), and
3.208 × 2.493 / 2.5 = 3.1996 — times the speed ratio (A8 *divides* by speed, so
the factor is 67.0416879 / 56.361205525 = 1.18950), giving **3.80618**, which is
18.7266749303634 / 4.9200741505916 to six digits. Every factor in that product
is one a wrong join could drop, and none of them is 1.

### 6.5 The reproduction script

An independent reproduction, in Python, of the whole chain from the snapshot's
own **input** tables. `./run-leaks-oracle.sh` extracts this fence and runs it —
extracted rather than kept as a second copy, so a specification whose code has
quietly stopped running cannot mislead anyone for long. It is the same
arrangement `./run-oracle.sh` and `./run-onroad-oracle.sh` use.

**It reads nothing from the reference.** `sho`, `sourcehours`,
`sourcebindistributionfuelusage_13_26161_2020`, `opmodedistributiontemp`,
`fractionofoperating` and `MOVESOutput` are all *compared against*, never read
forward. That is the difference from `./run-onroad-oracle.sh`, which has to take
`baserate_1_2020` from the reference (§0.3).

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
PP = 100 * 1 + 13                                   # section 5.1
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
    b = bin_id(r["fuelTypeID"], r["engTechID"], r["regClassID"], shortgroup[g])
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

# --------------------------------------------- L1: IMCoverageMergedUngrouped
assert not T("imcoverage") and not T("imfactor"), \
    "this fixture has no I/M program; L9's blend is the identity (section 1.3)"
im_adjust = {}

# ------------------------------------------------- L8: WeightedMeanBaseRate
evap_fuels = {r["fuelTypeID"] for r in T("fueltype")
              if str(r["subjectToEvapCalculations"]).upper() == "Y"}
stmy_of = {r["sourceTypeModelYearID"]: r for r in T("sourcetypemodelyear")}
age_groups = {(r["ageID"], r["ageGroupID"]) for r in T("agecategory")}
ppmy = {(r["polProcessID"], r["modelYearID"], r["modelYearGroupID"])
        for r in T("pollutantprocessmodelyear")}
run_source_types = {r["sourceTypeID"] for r in T("runspecsourcetype")}
sbd_by_bin = collections.defaultdict(list)
for (stmy, b), v in sbdfu.items():
    sbd_by_bin[b].append((stmy, v))

wmbr = collections.defaultdict(float)
for e in T("emissionratebyage"):
    if e["polProcessID"] != PP:
        continue
    b = sb.get(e["sourceBinID"])                        # K8
    if b is None or b["fuelTypeID"] not in evap_fuels:  # K9
        continue
    for stmy, frac in sbd_by_bin.get(e["sourceBinID"], []):   # K10
        s = stmy_of.get(stmy)                                 # K11
        if s is None:
            continue
        age = YEAR - s["modelYearID"]                         # the derived key
        if (age, e["ageGroupID"]) not in age_groups:          # K12
            continue
        if (PP, s["modelYearID"], b["modelYearGroupID"]) not in ppmy:   # K13
            continue
        if s["sourceTypeID"] not in run_source_types:                   # K14
            continue
        # No CROSS JOIN over months and hour/days: it carries no information.
        key = (b["regClassID"], b["fuelTypeID"], s["modelYearID"], e["opModeID"])
        wmbr[key] += frac * f(e["meanBaseRate"])

# ------------------------------------------ L9, O1-O3: the emission and the row
real_days = {r["dayID"]: f(r["noOfRealDays"]) for r in T("dayofanyweek")}
day_of = {r["hourDayID"]: r["dayID"] for r in T("hourday")}
ppa = {r["polProcessID"]: (r["processID"], r["pollutantID"]) for r in T("pollutantprocessassoc")}
process_id, pollutant_id = ppa[PP]


def onroad_scc(fuel, source, road, process):
    return "%d" % (22 * 10**8 + fuel * 10**6 + source * 10**4 + road * 10**2 + process)


rows, sccs = collections.defaultdict(float), {}
for (regclass, fuel, my, opmode), rate in wmbr.items():
    for d in DAYS:
        h = HD[d]
        if (h, YEAR - my) not in source_hours or (h, opmode) not in omd:   # K15, K16
            continue
        quant = rate * source_hours[(h, YEAR - my)] * omd[(h, opmode)] / real_days[day_of[h]]
        if (process_id, pollutant_id, my, fuel, ST) in im_adjust:          # K21
            raise SystemExit("unreachable: L1 produced no cell")
        rows[(d, fuel, my)] += quant                                       # K22
        sccs[(d, fuel, my)] = onroad_scc(fuel, ST, LINK_ROAD, process_id)

# --------------------------------------------------------------------- compare
def worst(computed, reference, label, absolute=False):
    assert set(computed) >= set(reference), \
        "%s: %d reference key(s) not computed" % (label, len(set(reference) - set(computed)))
    if absolute:
        w = max(abs(computed[k] - v) for k, v in reference.items())
        print("%-26s %4d rows, worst ABSOLUTE error %.3e" % (label + ":", len(reference), w))
    else:
        w = max(abs(computed[k] - v) / abs(v) for k, v in reference.items() if v)
        print("%-26s %4d rows, worst relative error %.3e" % (label + ":", len(reference), w))
    return w


worst({(k[1], k[2]): v for k, v in sho.items()},
      {(r["hourDayID"], r["ageID"]): f(r["SHO"]) for r in T("sho")}, "SHO")
worst(source_hours,
      {(r["hourDayID"], r["ageID"]): f(r["sourceHours"]) for r in T("sourcehours")}, "SourceHours")
worst(dict(sbdfu),
      {(r["sourceTypeModelYearID"], r["sourceBinID"]): f(r["sourceBinActivityFraction"])
       for r in T("sourcebindistributionfuelusage_%d_%d_%d" % (PP % 100, COUNTY, YEAR))},
      "sourceBinDistribution")
worst(dict(frac_op),
      {r["hourDayID"]: f(r["fractionOfOperating"]) for r in T("fractionofoperating")},
      "fractionOfOperating", absolute=True)
worst(omd,
      {(r["hourDayID"], r["opModeID"]): f(r["opModeFraction"]) for r in T("opmodedistributiontemp")},
      "OpModeDistribution", absolute=True)

out = OUT("movesoutput")
expected = {(o["dayID"], o["fuelTypeID"], o["modelYearID"]): f(o["emissionQuant"]) for o in out}
assert len(rows) == len(out), (len(rows), len(out))
assert set(rows) == set(expected), "key set differs"
for o in out:
    k = (o["dayID"], o["fuelTypeID"], o["modelYearID"])
    assert sccs[k] == o["SCC"], (sccs[k], o["SCC"])
    assert o["processID"] == process_id and o["pollutantID"] == pollutant_id
w = worst(dict(rows), expected, "emissionQuant")
print("%-26s %d cohorts x %d day types = %d rows, exact; SCCs %s"
      % ("key set:", len(rows) // len(DAYS), len(DAYS), len(rows), sorted(set(sccs.values()))))
print("%-26s %.6f g computed / %.6f g in MOVESOutput"
      % ("total THC:", sum(rows.values()), sum(expected.values())))
```

### 6.6 Suggested inline `.esm` tests

Each one pins a specific non-zero value from the sections above, and each
description says **what breaks if it is wrong** rather than restating the
expression (`docs/esm-conventions.md` §12).

`components/evap_operating_mode_distribution.esm` (E1–E3):

| test | pins | what it catches |
|---|---|---|
| `the_operating_share_is_one_at_an_on_network_link` | `fractionOfOperating` = 1 at both hour-days, from the §6.0 sums | an A10 that took the off-network `SHP` branch; the ratio would be ≈9.6 × 10⁻⁵ and every soak weight would come alive |
| `mode_300_is_a_residual_and_not_the_operating_share` | 0.599999932 on a probe row at `fractionOfOperating` = 0.6 | writing `opModeFraction[300] = fractionOfOperating`, which is exact on this fixture and wrong by 6.8 × 10⁻⁸ on the probe |
| `the_soak_modes_carry_the_complement` | 0.002674868 and 0.3973252 on the same probe row | a `(1 − f)` written as `f`, and the sign of the complement |
| `the_operating_share_is_capped_at_one` | 1 on a probe row whose ratio is 1.25 | dropping `least(1, ·)`, which would drive the mode-300 residual negative and then to 0 through `greatest` |

`components/evap_weighted_base_rate.esm` (L8):

| test | pins | what it catches |
|---|---|---|
| `the_age_group_join_selects_one_rate_of_seven` | 0.12496779679999999 for (2020, gasoline) | dropping K12 sums all seven age groups: 5.227947278399999 instead, **41.83×** on this cohort and 9.44× on the fixture total |
| `the_oldest_cohort_uses_the_grouped_model_year_rate` | 4.037348315 for (1980, gasoline) | a `modelYearGroupID` → `shortModYrGroupID` step that used 19781995 in the bin instead of 52 |
| `a_fuel_with_no_rate_row_contributes_nothing_and_keeps_its_row` | 0 for (1980, diesel) **and** 4.037348315 for (1980, gasoline) in the same test | an inner join spelled as a deletion — the diesel row must be present carrying zero (`docs/esm-conventions.md` §3) |
| `the_evap_fuel_flag_is_inert_on_this_fixture` | the same two values with the flag overridden to admit every fuel | asserting a filter that does nothing, which §7.2 measures; the test's job is to record that the flag is *redundant here*, not that it is unnecessary |
| `the_rebased_fraction_is_the_one_that_reaches_the_rate` | 0.000192737741 for (2002, E85) | using C3's raw fraction: 0.01078792692, **56×** |

`components/liquid_leaking_emissions.esm` (L9, O1–O3):

| test | pins | what it catches |
|---|---|---|
| `the_worked_examples_reach_movesoutput` | 4.9200741505916, 18.7266749303634, 6.49975006648352, 32.0865687916204 | any factor in the L9 product |
| `real_days_divides_and_does_not_multiply` | the weekend/weekday pair for one cohort, ratio 3.806 | applying `noOfRealDays` twice or not at all — a factor of 2 and 5 respectively (§2.5) |
| `the_zero_op_mode_fractions_contribute_nothing` | the mode-300 contribution for (1980, gasoline), beside an exactly zero contribution from each soak mode | summing the three modes' rates without their fractions: 4.037348315 + 0.430904708 + 0.224032315 = 4.692285338, a 16.2 % over-emit |
| `the_im_blend_is_the_identity_at_zero_and_moves_the_rate_at_one` | the unblended value at `IMAdjustFract` = 0 and the `…IM` value at 1, on a probe row | an `im_blend` wired with its arguments swapped, which is invisible while `IMAdjustFract` is absent everywhere in this fixture |
| `the_scc_is_computed_from_four_columns` | 2201210413 and 2205210413 | a hard-coded SCC, or the fuel and source-type slots exchanged |
| `the_absent_output_columns_are_absent_and_not_zero` | NaN for `regClassID`, and a non-zero `emissionQuant` beside it | emitting 0 for a NULL column, which claims regulatory class zero |

---

## 7. Fidelity notes and tolerance

### 7.1 Everything agrees to 7.3 × 10⁻⁶, and that number is the reference's storage, not our error

`./run-leaks-oracle.sh`, measured:

| relation | rows | worst error |
|---|---|---|
| `SHO` | 82 | 3.610 × 10⁻⁶ relative |
| `SourceHours` | 82 | 3.610 × 10⁻⁶ relative |
| `sourceBinDistributionFuelUsage` | 125 | 3.449 × 10⁻⁶ relative |
| `FractionOfOperating` | 2 | **0** absolute |
| `OpModeDistribution` | 6 | **0** absolute |
| `MOVESOutput.emissionQuant` | 128 | 7.294 × 10⁻⁶ relative |
| total THC | — | 960.060705 g against 960.061201 g, 5.2 × 10⁻⁷ |

**Every one of those residuals is the width of a stored column, and it can be
attributed cell by cell.** Two demonstrations:

* `samplevehiclepopulation.stmyFraction` for (21, 2002) is stored as
  `0.985305968751`, `0.004633902802`, `0.007914838927`, `0.002145289519` —
  **twelve decimals**. The rebased result MOVES stored is
  `0.993079000000`, `0.004633900000`, `0.000141407000`, `0.002145290000` —
  **six significant figures**. Recomputing E85's from the twelve-decimal input
  gives `0.000141406512269782`, and `|·− 0.000141407| / 0.000141407 =
  3.449 × 10⁻⁶`, which is the worst cell of the whole C-stage. The input is
  precise; the reference's *intermediate* is not.
* `sourcehours` stores `27.33`, `260.057`, `12.4561`, `118.526`, `2.43728`,
  `23.1918` against computed `27.330001837636907`, `260.0573038920831`,
  `12.456122691939292`, `118.52562994539538`, `2.437278712884465`,
  `23.191807108971084` — relative differences 6.7 × 10⁻⁸ to 3.1 × 10⁻⁶, again
  six significant figures.

The output's worst cell is at (day 5, fuel 5, MY 2002), which is the product of
the worst C-stage cell (3.4 × 10⁻⁶) and a 3.1 × 10⁻⁶ activity cell. **7.3 × 10⁻⁶
is what those two add up to.** This is the same conclusion both companions
reached — `docs/nonroad-logging-county.md` §7.1's 4.0 × 10⁻⁶ and
`docs/mixed-onroad.md` §7.1's 8.2 × 10⁻⁶ — and the number is comparable because
the cause is the same.

**Two relations agree exactly, and that is informative.** `FractionOfOperating`
and the six-row `OpModeDistribution` are 0 and 1 to the last bit, because A10's
row-wise identity makes the ratio an exact 1 (a quotient of identical binary64
values) and the residual an exact `1 − 0`. So the one part of this chain that
depends on a blocked recurrence is also the one part with no numerical
uncertainty at all.

**There is no `float32` question in this chain.** The SQL stores its working
tables in `FLOAT` while MariaDB evaluates in `DOUBLE`
(`liquid_leaking_calculator.rs`'s fidelity note), which is a sub-10⁻⁷ drift
between steps and is smaller than the 6-significant-figure storage above. The
NONROAD slice's `real*4` associativity problem (`docs/esm-conventions.md` §10)
does not arise: nothing here is Fortran.

### 7.2 Which joins are load-bearing — measured, one at a time

Each row removes exactly one filter or substitutes one input in the §6.5 oracle
and reports what happens. This is the table §1.3 rests on, and it is also where
each component test's "what breaks if this is wrong" comes from.

| ablation | rows emitted | key set | worst cell (relative) | total THC |
|---|---|---|---|---|
| *(none — the specification as written)* | 128 | exact | 7.294 × 10⁻⁶ | 960.06070527028 g |
| drop `fuelType.subjectToEvapCalculations = 'Y'` (K9) | 128 | exact | 7.294 × 10⁻⁶ | 960.06070527028 g |
| drop the `pollutantProcessModelYear` existence filter (K13) | 128 | exact | 7.294 × 10⁻⁶ | 960.06070527028 g |
| drop the `runSpecSourceType` filter (K14) | 128 | exact | 7.294 × 10⁻⁶ | 960.06070527028 g |
| **drop the `AgeCategory` join (K12)** | 128 | exact | **41.27** | **9 066.422472 g — 9.44×** |
| **use C3's raw distribution instead of C4's rebased one** | 128 | exact | **54.97** | **960.0607052702798 g** |

(`MOVESOutput`'s own total is 960.061201 g; the 5.2 × 10⁻⁷ gap to the baseline is
§7.1's storage width. Each row is one edit to the §6.5 script, re-run.)

Two of the six do nothing, and they are the two `.esm` authors are most likely
to skip *because* they do nothing — so §1.3 lists them and §6.6 asserts them
with the filter overridden, which records that they are redundant **here**
rather than unnecessary.

The two that matter are the point of the table. **The `AgeCategory` join is the
largest single-factor error available in this chain** — larger than
`weeksPerMonth`'s 4.43× in the activity stage, because `emissionRateByAge`
carries seven age groups and an unfiltered join sums all seven. And the
fuel-usage rebase is the largest *per-cell* error while being invisible in every
total, which is §7.3.

Nothing in the key set moves under any of the six. That is worth stating: on
this fixture, `require_exact_key_set` catches **none** of these errors. The
key set is decided upstream, by C2's `stmyFraction > 0` and by which bins have
rate rows at all (§6.4), and both of those are structural. So the per-cell gate
is doing all of the work here, unlike `nr-logging-county`, where the key set was
the sensitive thing.

### 7.3 Why no total in this document can see the largest per-cell error

Substituting C3's raw source-bin distribution for C4's rebased one makes the
worst cell high by a factor of **55.97** (relative error 54.97) and the median
cell wrong by **3.2 %** — and changes the total THC from

```
960.06070527028     (as specified)
960.0607052702798   (with the raw distribution)
```

**The same number to thirteen significant figures.** The two differ only in the
last bits, from summation order.

The reason is that the rebase *moves* activity between fuels within a model
year rather than creating or destroying it: E85's 0.982134 share goes onto
gasoline, and for these model-year groups the gasoline and E85 rates are
**equal** (both 1.363 at age group 1519, both 0.158 at 3, and so on down the
table in §6.1 and §6.3). So the sum over the two fuels is invariant and only the
split is wrong. It is wrong by 56× on the small side of the split.

**This is the repository's characteristic failure mode with the numbers filled
in.** `README.md` and `docs/esm-conventions.md` warn that a plausible wrong
value on a document that validates cleanly is what this port has to defend
against, and that a per-pollutant tolerance absorbs it. Here is a specific,
reproducible instance:

* the per-pollutant sums gate (`tolerance.toml` `[default] onroad = 1e-3`) would
  pass at a relative error of **5.2 × 10⁻⁷**;
* `require_exact_key_set` and `require_exact_row_count` would pass — the key set
  is identical;
* the **only** gate that fails is `[cell] rel = 2e-5`, and it fails by a factor
  of 2.7 million.

So the per-cell gate is not belt-and-braces on this fixture; it is the gate. Do
not loosen it, and do not accept a per-fixture override for this slice — §7.4
shows none is needed.

A second consequence, for the `.esm` author: a fixture assertion on a total is
worth very little here. §6.6's component tests pin **cells** — 4.037348315,
0.12496779679999999, 0.000192737741 — and the two aggregate figures in §6.4 are
there to catch a gross structural error, not a modelling one.

### 7.4 Recommended tolerance: no change, and no per-fixture override

`tolerance.toml` as it stands is the right gate for this fixture, unchanged:

| gate | current value | measured | headroom |
|---|---|---|---|
| `[cell] rel` | 2 × 10⁻⁵ | 7.294 × 10⁻⁶ | 2.7× |
| `[default] onroad` (per-pollutant sums) | 1 × 10⁻³ | 5.2 × 10⁻⁷ | 1900× |
| `[structure] require_exact_key_set` | true | 128 / 128 | exact |
| `[structure] require_exact_row_count` | true | 128 / 128 | exact |

**No `[fixtures."process-evap-leaks"]` override is needed**, and that is a
result rather than an omission: the same 2 × 10⁻⁵ that `nr-logging-county` needs
no override for covers this fixture with 2.7× to spare, on a chain with no
`float32` question at all (§7.1). A per-fixture override here would be hiding
something.

**And there is no `[shortfall]` to record.** Every input this fixture needs is
computable from the snapshot — that is the §0.3 argument and §6.5 is the proof —
so the comparison is expected to *pass*, not to fail in a recorded way. §8.1
says what remains.

---

## 8. Gaps, uncertainties and things I could not verify

### 8.1 What this fixture does not exercise

Each of these is a branch the `.esm` should carry and this fixture cannot check.
§6.6 exercises the first three with probe rows, which is the technique
`docs/esm-conventions.md` §16.4 established after finding F19 removed the
parameter-override one.

* **The I/M blend (L1, K20, K21).** `imcoverage` and `imfactor` are empty.
  Unexercised: the model-year-range disaggregation, the `× 0.01`, the blend
  itself and its `GREATEST(·, 0)` clamp. No fixture in the corpus has a
  non-empty `imcoverage`, so this stays unexercised until one is added.
* **The soak operating modes (E2).** Weight exactly 0 here. Unexercised: the
  `soakActivityFraction` join and the mode-150/151 rates, which are 0.452 and
  0.235 for the (1980, gasoline) bin — a document that used them where it should
  use 4.235 would be low by 89 %.
* **`SHP`, the off-network branch of A10.** This run has one link and it is
  on-network. Unexercised: `population × noOfRealDays − Σ_roadType SHO`, and
  with it the whole reason `fractionOfOperating` can be less than 1. This is
  the single largest untested surface in the slice and §8.3 says what it would
  take.
* **More than one of anything temporal or spatial.** One county, one zone, one
  link, one month, one hour, one source type, one road type, one regulatory
  class. `expand-*` is Phase 5.
* **`regClassID` aggregation with more than one class (O1).** `sourcebin`
  carries only class 20, so O1's `regClassID` group-by is a no-op that must
  still emit the column as absent.
* **The speciation chain.** §0.2: it has no input. `chain-tog-speciation` and
  `chain-nonhaptog` are the fixtures for it, and both need `W`.

### 8.2 Verified empirically but not against canonical code

The `execution-trace.json` for this fixture lists no SQL files and no calculator
or generator classes (§1.1), so **`LiquidLeakingCalculator.sql` itself was not
read** — every step label (LL-1, LL-8, LL-9), every join key pair and every
literal in this document comes from the `moves.rs` port's transcription of it,
cross-checked against the snapshot's numbers. The §6.5 oracle is what makes that
defensible: an independent third implementation agreeing to 7.3 × 10⁻⁶ on 128
cells and exactly on the key set is strong evidence that the transcription is
faithful, but it is not the same as having read the SQL. Two specific places
where reading it would add something:

* **§2.4 point 7's claim that L8's `CROSS JOIN RunSpecMonth, RunSpecHourDay`
  carries no information.** The Rust has no `ON` clause there and the port's
  module comment says so, and the `.esm` relies on it to drop a whole key
  dimension from `weightedMeanBaseRate`. It is measured (the two `hourDayID`s
  get identical values) but on a fixture with one month.
* **The `NoRegClassID` variant of L8.** Asserted dead because
  `BundleUtilities.prepareCountyDataWithRunSpec` unconditionally enables
  `WithRegClassID`; that is the port's claim, and this fixture cannot
  distinguish the variants because it has one regulatory class.

### 8.3 A correction to `docs/mixed-onroad.md` §0.1

§0.1 above replaces the "stale capture" explanation with the canonical
`RunSpecXML` key semantics, and the change is not cosmetic: it converts a
one-fixture accident into a corpus-wide rule with a named mechanism in two
`moves.rs` files. `docs/mixed-onroad.md` §0.1 now carries a pointer to it.

One row of that document's five-row table was **not** re-derived here: the
pollutant/process row (`9101, 9102, 9301, 9302` in the XML against `9101, 9102`
in the database). For *this* fixture the XML's three associations map exactly
onto the database's three `polProcessID`s with no divergence, so there is
nothing to compare against. That row may still be a genuine filter, an
expansion, or a stale edit; I did not chase it.

### 8.4 An anomaly I noticed and did not chase

`expand-month`'s execution database has `runspecday = {0}` and
`runspechour = {0}`, where every other onroad fixture has real day and hour
sets. `dayID` 0 and `hourID` 0 are not members of `dayofanyweek` or
`hourofanyday`. The fixture nevertheless produces 500 output rows. That is
either a different scope mechanism for a multi-month run or a capture defect,
and it is Phase 5's problem, not this slice's. It is recorded because a Phase 5
author scoping from `runspecday` will meet it.

### 8.5 Things deliberately not modelled

* **`meanBaseRateIM`.** Summed into `weightedMeanBaseRateIM` by L8 and consumed
  only by the blend, which is inert. The `.esm` carries the column so that the
  blend has both arguments and §6.6 can exercise it, and the fixture's value for
  it reaches nothing.
* **The 24 `polProcessID = −1` rows of `opmodepolprocassoc`.** They are the
  drive-cycle operating modes, unassociated with any pollutant-process. K5 and
  K6 never admit them. §5.2 records why −1 cannot be an `enums` value.
* **`sourceBinID` as a value.** Only as a join key and only unpacked (§2.2).
* **`hcspeciation`'s 81 rows** (§0.2), and the whole tank-temperature working
  set except `soakActivityFraction` (§1.4).

---

## 9. Summary for the `.esm` author

1. **Reuse, do not rewrite, A1–A9 and C1–C4.**
   `components/onroad_travel_fraction.esm`,
   `components/onroad_source_hours.esm` and
   `components/onroad_source_bin_distribution.esm` are these stages, and the
   fuel-usage source-bin distribution for `polProcessID` 113 is **bit-identical
   on all 125 keys** to the one Phase 3 built for `polProcessID` 1 — measured
   across two snapshots. Rebind the pollutant-process and nothing else.
2. **A10 is one line and it decides the slice.** `SourceHours = SHO` at an
   on-network link, `= SHP` at road type 1. Get it wrong and every soak weight
   comes alive and you need a recurrence the format cannot express.
3. **E3's mode-300 fraction is a residual `1 − Σ(soak)`, not
   `fractionOfOperating`.** On this fixture the two are equal. Assert the probe.
4. **K12 — the `(ageID = year − modelYearID, ageGroupID)` join — is the one to
   get right.** 9.44× on the total if it is dropped, 41.83× on a single cohort.
   One derived column, `effectiveAgeID`, shared by K12 and K15, computed once.
5. **The rebased source-bin fraction is the one that reaches the rate**, and no
   total will tell you if you used the raw one. 56× on a cell, 0 on the sum.
6. **Five joins are semi-joins** (K6, K9, K13, K14, K20): `bool_and_or` with
   body `1.0`, bound as `> 0`. Two of them are measurably inert and must still
   be there.
7. **No self-join anywhere in K1–K22** — a first for this port. C4's is
   avoidable via the used-bin existence semi-join (§2.2), and the existence
   condition admits all 99 equipped × usage pairs on this fixture.
8. **`÷ noOfRealDays` at L9 undoes `÷ weeksPerMonth` at A7.** Both or neither is
   a factor of 2 and 5.
9. **Every assertion pins a cell, not a total** (§7.3). The cells are in §6.
10. **Nothing is uncomputable.** No `[shortfall]`, no carried column, no data
    read from the reference. If the fixture does not match, the document is
    wrong.
