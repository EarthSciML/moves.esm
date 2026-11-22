# ONROAD (and general MOVES-run) functionality MOVES 5 has that moves.esm lacks

Audit date 2026-11-21. Read-only. moves.esm checkout `/projects/illinois/eng/cee/ctessum/ctessum/code/moves.esm-docs` (branch docs-status, HEAD `cc2897c`). MOVES 5.0.1 source copied out of `canonical-moves.sif:/opt/moves` to `/scratch.local/ctessum/gaps/moves/` (paths below are relative to that tree; `gov/.../master` = `gov/epa/otaq/moves/master`). Default DB = `movesdb-parquet/movesdb20241112`. The verified onroad corpus is 115 runspecs in `runspecs/*.esm` (+1 in `runspecs/pending/`); their recipes are `moves.rs/characterization/fixtures/<name>.xml`.

Status vocabulary: **NOT PORTED-silent** (MOVES does it, moves.esm neither computes nor counts it; a run asking for it gets a plausible wrong or default number), **NOT PORTED-absent** (output simply not produced; loud only in the sense that a table is missing), **COUNTED via `<var>`** (refused through `run_selectionUnported`/`run_domainUnported`, asserted 0 by `tools/check-runspec-shape.py`), **PARTIAL**, **PORTED-unverified** (equations exist, no capture checks them), **PORTED** (a capture checks it cell by cell), **GUARDED** (a tooling check fails a RunSpec document that would leave it silent).

---

## Ranked summary (silent first)

1. **County/Project input databases are read only for ~20 tables; the core CDM tables come from the DEFAULT database. COUNTED via `run_domainTablesUnread` (in `run_domainUnported`) (PLAN.md §7.3.85).** Every domain document declares each table's input side (`db_input_<table>`, the rows its database states); a row the default does not carry identically at the columns the model reads (`run_input*Differs`), or, for a table MOVES REPLACES in that domain, a selected default key the stated table lacks (`run_input*Missing`), is refused. *Audit text follows.* In SINGLE (county) and PROJECT domain MOVES replaces `sourceTypeYear`, `sourceTypeAgeDistribution`, `HPMSVtypeYear`, `fuelSupply`, `IMCoverage` with the county database's (`InputDataManager.java:1433-1435, 2816, 2834-2846`), and row-merges every other table it states (VMT fractions, `avgSpeedDistribution`, `roadTypeDistribution`, `zoneMonthHour` meteorology, `fuelFormulation`, `fuelUsageFraction`, `totalIdleFraction`, the starts tables). moves.esm reads all of those from `../movesdb/*.parquet` (`onroad/default-database.esm`); the domain documents (`moves-onroad.esm`, `inputs/*.esm`) declare only 17 tables (link, linkSourceTypeHour, offNetworkLink, opModeDistribution, driveScheduleSecondLink, runspecdomain, zone, zoneRoadType, the five hotelling tables, three idle-adjust tables, startsPerDay) plus avft, onRoadRetrofit, soakActivityFraction and emissionRateByAge overrides. Every captured county database is by construction a copy of the default at the run's keys ("SINGLE should equal DEFAULT", PLAN.md:4712-4721; table at PLAN.md:4283-4296), so no capture can see this. Only added Zone/ZoneRoadType keys are counted (`run_zoneRowsAdded`, `run_zoneRoadTypeRowsAdded`). A real county database (local population, age distribution, VMT, speeds, fuels, meteorology) silently produces the default-database inventory.
2. **Alternate VMT forms are not read at all. COUNTED via `run_domainTablesUnread` (`run_inputHPMSVtypeDayRows`, `run_inputSourceTypeYearVMTRows`, `run_inputSourceTypeDayVMTRows`: any row) (PLAN.md §7.3.85).** `SourceTypeYearVMT`, `SourceTypeDayVMT`, `HPMSVtypeDay` (VehicleTypeVMTImporter; TotalActivityGenerator.java:1170-1200, 1436-1460, 1547-1600) have 0 references in `onroad/model.esm`. PLAN.md:7091 admits "not read: no county database here states daily VMT". These are the forms most CDM users supply.
3. **User `starts` table, `startsPerDayPerVehicle`/`startsHourFraction`/`startsMonthAdjust`/`startsAgeAdjustment`/`startsOpModeDistribution` and `totalIdleFraction` from a county DB. COUNTED via `run_domainTablesUnread` (`run_inputStartsRows` -- isUserInput 'Y' rows -- `run_inputImportStartsOpModeDistributionRows`, and the Differs counters of the five starts tables and totalIdleFraction) (PLAN.md §7.3.85).** AdjustStarts.sql:22-35 uses an imported `starts` table (`isUserInput='Y'`) in place of the computed one; the model has no `db_starts` and reads the other five from the default only.
4. **I/M in SINGLE/PROJECT domain: the refusal reads the wrong table. FIXED and COUNTED via `run_imUnported` (PLAN.md §7.3.85): the domain database's IMCoverage (`db_input_imcoverage`, `run_inputIMProgramRows`) is counted in every domain, the default's only in DEFAULT domain. *Audit text (the bug as found) follows.* `run_imProgramRows` joins `imcoverage_rows` = default `../movesdb/IMCoverage.parquet` (equation in `onroad/model.esm`). In SINGLE/PROJECT MOVES uses the domain DB's IMCoverage only. So a county DB stating a program for a county the default has none for (e.g. Washtenaw) gives `run_imUnported` 0 and un-inspected rates, silently; a county the default does cover is refused even if the user's DB has no program.
5. **The output shape options of a RunSpec are not read. COUNTED via `run_outputOptionsUnported` (in `run_selectionUnported`), read from the per-run declared `db_runspecoutput` and checked against each XML by tools/check-sources.py (PLAN.md §7.3.85).** Geographic output detail (NATION/STATE/COUNTY/ZONE/ROADTYPE/LINK, AggregationSQLGenerator.java:956-1191), the 13 output-breakdown flags (common/OutputEmissionsBreakdownSelection.java:17-53: model year, fuel type, fuel subtype, process, road type, source type, MOVES vehicle type, SCC, sector, engine tech, hp class, reg class), and output units (mass g/kg/lb/ton, energy J/kJ/MMBTU, distance mi/km; runspec/MassMeasurementSystem.java etc.) have 0 references in the model (`grep -ic breakdown|geographicoutputdetail onroad/model.esm` = 0). All 115 verified XMLs use the same breakdown (modelyear, fueltype, emissionprocess, roadtype, onroadscc), COUNTY or LINK detail, and grams/MMBTU/miles. Any other choice gets the fixed shape and units.
6. **NATION/STATE geographic selection (PreAggNATION.sql / PreAggSTATE.sql) for onroad. COUNTED via `run_geoSelectionUnported` (in `run_selectionUnported`) (PLAN.md §7.3.85).** Triggered by the selection type in InputDataManager.java:2582-2640; `PreAggSTATE|PreAggNATION` occur 0 times in `onroad/model.esm` (16 in `nonroad/model.esm`). Every verified onroad run is COUNTY-type.
7. **MOVESActivityOutput is never emitted. NOT PORTED-absent, COUNTED apart via `run_activityOutputUnported`: a reported known-unported output, NOT a refusal (MOVESOutput is unaffected; the 4 VMT-output runs read 1 and pass) (PLAN.md §7.3.85).** MOVES instantiates DistanceCalculator/ActivityCalculator when outputvmtdata/SHO/SH/SHP/SHIdling/starts/population is on (MOVESInstantiator.java:1366-1377). The model computes distance and population internally (`rto_distance`, `coh_population`) but no runspec emits or checks the table, including the 4 verified runs with `outputvmtdata=true` (`scale-county-minor-running`, `-minor-offnet`, `-timeagg-year-minor-*`). `tools/calculator-coverage.py` excludes both calculators from its denominator as "superseded/unwired" -- wrong for this output path.
8. **Any other table in a user input database (`<databaseselections>`) or the Generic importer. GUARDED in tooling: tools/check-sources.py check 11 fails a run whose input-database SQL states a table no document of its mount chain reads (PLAN.md §7.3.85).** MasterLoop merges every table of a user DB ahead of the default; the model merges only emissionRateByAge (counted beyond the LEV tool's 10 pairs), onRoadRetrofit, the hotelling/idle/starts-per-day tables, avft and soakActivityFraction.
9. **The RunSpec front end is MOVES's, not the model's. NOT PORTED (loud-ish).** All 115 runspecs read `runspecyear/month/day/hour/county/roadtype/sourcetype/sourcefueltype/pollutantprocess/chainedto` and most `actday/rateday/aggregationhour` from the MOVES capture's execution database (`../../moves.rs/characterization/snapshots/<run>/tables/db__movesexecution...`). The XML is not parsed; prerequisite expansion (`flagRequiredPollutantProcesses`), chaining, road-type forcing and STATE->county expansion are taken from MOVES. Scale, output step and aggregation are hand bindings (`n_ratesScale`, `n_outputSums*`, `n_aggregatesMonths`, ...), and `n_outputRate`/`n_sourceBin`/`n_physicsRow` are bound from a previous evaluation of the same run (mismatch is caught by `check-runspec-shape.py`, so this is loud). moves.esm cannot run a RunSpec MOVES has not already run.
10. Counted gaps still open: I/M at unchecked pollutant-processes and in SINGLE/PROJECT (`run_imUnported`); retrofit outside running/start, under aggregation, PROJECT, summed output steps, table-off cases (`run_retrofitUnported`, `run_retrofitTableOff`); LEV rows outside the 10 tool pairs / added keys / PROJECT (`run_levUnported`); Rate-of-Progress (permanent, `run_ropUnported`, MOVES 5.0.1 itself fails); third+ calendar year with hotelling adjustments (`hot_adjustmentRowsUnported`, pending `userdb-hotelling-threeyear`); project-domain residue (`run_projectShortfall`, `run_projectScheduleUnported`, `run_userLinkModeRows`, `run_userLinkGaps`, `run_unportedProjectProcesses`); Year-aggregated pairs no Year capture checks (`run_yearUnportedSelected`); `run_soakActivityGapsEmitted`; `run_startModeAgeVariation`.
11. Unverified generality (secondary): PAH gas-phase species 168-184 at 1/2/15/16/17/90/91 never selected by a verified run; crankcase running/start gaseous species (CH4, NMHC, TOG, VOC, NO, NO2, HONO, SO2, NH3, CO2e at 15/16) only ever selected without parents (MOVES wrote no rows); source types 41, 43, 53, 54, 61 never in a checked output; calendar years only 2015/2020/2025; county inputs only Washtenaw (26161), I/M only Cook (17031); performance limits (single county-hour runs at 36-62 GB RSS).

---

## 1. Emission processes and pollutants

Source: `PollutantProcessAssoc.parquet` joined to `EmissionProcess` (onroad processes 1, 2, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19, 90, 91, 93; 99 well-to-pump has no MOVES 5 pair). "Selected" = in some verified runspec's `runspecpollutantprocess`; "checked" = (pollutant, process) has rows in some verified run's MOVESOutput or rate table (compared cell by cell, exact key set). Script output in `/scratch.local/ctessum/gaps/tmp/ppcov.csv`.

| process | MOVES pairs | selected by a verified run | checked with output rows | selected, MOVES writes none (checked absent) | never selected by any verified run |
|---|---:|---:|---:|---|---|
| 1 Running Exhaust | 111 | 95 | 70 | 60, 61, 62, 63, 65, 66, 67, 130-146 (metals, dioxins), 3000 | 99 (BSFC, nonroad-only registration), 168-178, 181-184 (PAH gas) |
| 2 Start Exhaust | 85 | 70 | 69 | 3000 | 168-178, 181-184 |
| 9 Brakewear | 2 | 2 | 2 | - | - |
| 10 Tirewear | 2 | 2 | 2 | - | - |
| 11 Evap Permeation | 14 | 14 | 12 | 185, 3000 | - |
| 12 Evap Fuel Vapor Venting | 14 | 14 | 12 | 185, 3000 | - |
| 13 Evap Fuel Leaks | 14 | 14 | 12 | 185, 3000 | - |
| 15 Crankcase Running Exhaust | 83 | 68 | 57 | 5, 30, 31, 32, 33, 34, 79, 86, 87, 98, 3000 | 168-178, 181-184 |
| 16 Crankcase Start Exhaust | 82 | 67 | 56 | 5, 30, 31, 32, 33, 34, 79, 86, 87, 98, 3000 | 168-178, 181-184 |
| 17 Crankcase Extended Idle | 81 | 66 | 63 | 30, 31, 3000 | 168-178, 181-184 |
| 18 Refueling Displacement | 16 | 16 | 14 | 185, 3000 | - |
| 19 Refueling Spillage | 16 | 16 | 15 | 3000 | - |
| 90 Extended Idle Exhaust | 83 | 68 | 67 | 3000 | 168-178, 181-184 |
| 91 Auxiliary Power Exhaust | 83 | 68 | 66 | 30, 3000 | 168-178, 181-184 |
| 93 Hotelling Shore Power | 1 | 0 | 1 (via APU retag) | - | - |

Notes per gap:
- **PAH gas-phase 168-178, 181-184 at 1, 2, 15, 16, 17, 90, 91 -- PORTED-unverified.** Registered to AirToxicsCalculator (MOVESInstantiator.java:926-975); `pahGasRatio` has 10 rows per pair at 1/2. The model mounts `db_pahgasratio` (28 references) and the path is checked only for naphthalene (185). No verified run selects any of the 15 others; at Hour output nothing counts them (`run_yearUnportedSelected` only fires at `aggregateBy` Year).
- **Crankcase running/start gaseous species (CH4 5, NH3 30, SO2 31, NO 32, NO2 33, HONO 34, NMHC 79, TOG 86, VOC 87, CO2e 98 at 15 and 16) -- PORTED-unverified.** Only `scale-county-idle-species` and `scale-county-timeagg-year-toxics-idle` select them, and there "crankcase running and start are selected without their parents and MOVES writes no row" (that runspec's description). The absence is checked; the arithmetic with parents present is not.
- **Metals (60-67) and dioxins (130-146) at running exhaust -- PORTED as absent.** MOVES 5 does not instantiate AirToxicsDistanceCalculator under DO_RATES_FIRST (MOVESInstantiator.java:1449-1490 whitelist) and SourceBinDistributionGenerator writes no distribution without `sourceTypePolProcess` rows (PLAN.md:8285-8296, F81; capture `scale-county-metals-novmt`, 0 rows). A user DB adding `sourceTypePolProcess` rows would change that in MOVES; GUARDED by tools/check-sources.py check 11 (PLAN.md §7.3.85).
- **NonHAPTOG mechanism (3000)** is a selection switch whose output is the 1000-series species; those are checked (`rates-mechanism`, `chain-so2-co2e-mechanism`, `scale-county-idle-nonhaptog`, `scale-county-timeagg-year-nonhaptog`). At 11/12/13/18/19 it is ported (§7.3.75).
- **SO2's `generalFuelRatio` factor -- PARTIAL.** `rt_so2ChainRatio`: "SO2Calculator.sql's last step multiplies by generalFuelRatio for pollutant 31; no national expression names it, so that factor is 1 on every cohort MOVES ships and is not ported." A user fuel/GFRE that sets it would be ignored silently -- now GUARDED: a user or domain database stating `generalFuelRatioExpression` fails tools/check-sources.py check 11 (PLAN.md §7.3.85).
- Well-to-pump (99): `pollutantProcessAssoc` has no 99 pair in MOVES 5 (WellToPumpProcessor not live); N/A.

## 2. Calculators and generators

Denominator from `moves.rs/characterization/calculator-chains/calculator-dag.json` and `tools/calculator-coverage.py` (run read-only): 32 live modules (19 calculators, 13 generators), all claimed with an oracle and a fixture.

| module | status | evidence |
|---|---|---|
| BaseRateCalculator, BaseRateGenerator, RatesOperatingModeDistributionGenerator, SourceBinDistributionGenerator, TotalActivityGenerator, MeteorologyGenerator, FuelEffectsGenerator, AverageSpeedOMDG, StartOMDG, EvaporativeEmissionsOMDG, TankFuelGenerator, TankTemperatureGenerator, LinkOMDG, ProjectTAG | PORTED | coverage tool; runspecs across scales |
| AirToxicsCalculator, HCSpeciationCalculator, TOGSpeciationCalculator, SulfatePMCalculator, NOCalculator, NO2Calculator, SO2Calculator, CO2AERunningStartExtendedIdleCalculator, CrankcaseEmissionCalculatorNonPM, PM10EmissionCalculator, PM10BrakeTireCalculator, RefuelingLossCalculator, EvaporativePermeationCalculator, TankVaporVentingCalculator (multiday), LiquidLeakingCalculator | PORTED (see §1 for unverified pollutant subsets) | coverage tool; `process-*`, `chain-*`, `scale-county-*species*` runs |
| **ActivityCalculator, DistanceCalculator** | **NOT PORTED-absent** as output producers (internals computed) | live when activity output flags are set (MOVESInstantiator.java:1366-1377, both on the DO_RATES_FIRST whitelist :1474-1477); coverage tool lists them as "unwired"/"superseded" |
| AVFTControlStrategy | PORTED | §7.3.78, `scale-county-avft`, `project-avft` |
| OnRoadRetrofitStrategy | PARTIAL, COUNTED via `run_retrofitUnported` | §7.3.79 |
| RateOfProgressStrategy | COUNTED via `run_ropUnported` (permanent; MOVES 5.0.1 fails, F92) | §7.3.81 |
| NewTvvYearGenerator (SQL section) | PORTED | `docs/new-tvv-year.md`, oracle |
| Superseded/unwired by MOVES 5 (AirToxicsDistanceCalculator, Basic*PM*, CH4N2O*, Criteria*, NH3*, Dummy, WTP calculators, CrankcaseEmissionCalculator(PM), PMTotalExhaust, MesoscaleLookup*, OperatingModeDistributionGenerator), FuelControlStrategy/SourceMaintenance/SourceManufacturing/SourceUsage control strategies (`implementation/general`) | N/A in MOVES 5 | MOVESInstantiator DO_RATES_FIRST whitelist |

## 3. Scale, domain, selection, output options

- **Model scale Inventory / Rates (MACROSCALE / MESOSCALE_LOOKUP) -- PORTED.** 94 Inventory, 21 Rates verified runs. Rates + time aggregation: MOVES refuses; counted (`run_ratesUnported`).
- **Domain DEFAULT / SINGLE / PROJECT -- PORTED for the tables in the domain documents; see §4 for what is read from the default instead.** 56 / 40 / 19 verified runs. `run_domainUnported` counts project-shape residue (multi-county project, missing link per road type, Rates + walked schedules, evaporative beside walked schedule, user OMD rows at unread families, partial-hour user OMD).
- **Geographic selection NATION / STATE -- COUNTED via `run_geoSelectionUnported` (PLAN.md §7.3.85).** All 115 verified XMLs use `geographicselection type="COUNTY"`; no `PreAggNATION`/`PreAggSTATE` in `onroad/model.esm` (InputDataManager.java:2582-2640 runs them for MACROSCALE/MESOSCALE_LOOKUP). ZONE/LINK selection exists only as PROJECT links.
- **Multiple counties -- PORTED** (DEFAULT domain, up to 7: `expand-counties-large`). SINGLE/PROJECT allow one by MOVES rule.
- **Generic (custom) county (`<genericcounty>`, runspec/GenericCounty.java, RunSpecXML.java:169, 361-410: altitude, GPA fraction, barometric pressure, refuel vapor adjust) -- COUNTED via `run_outputOptionsUnported` (`genericcounty=true`) (PLAN.md §7.3.85).** Model reads `db_county`/`db_state` from the default; nothing references a generic county.
- **Time span -- PORTED.** Years 2015/2020/2025 only (1, 2 or 3 per run); months 1-12 (`expand-fullyear`); both day types; hours single, ranges and 0-23.
- **Non-base-year growth (TAG growPopulation/growVMT, TotalActivityGenerator.java:600-760, 1212-1260) -- NOT PORTED, unreachable with the default DB.** `run_baseYearIsAnalysisYear` is computed but read by no equation (grep of equations: only its own definition). Every default year 1990, 1999-2060 has `isBaseYear='Y'`, so harmless unless a user DB changes `year` -- which is now COUNTED (`run_inputYearDiffers` compares `isBaseYear` and `fuelYearID`, PLAN.md §7.3.85).
- **Pre-aggregation `aggregateBy` Hour/Day/Month/Year and output time step Hour / 24-Hour Day / Portion of Week / Month / Year -- PORTED,** with counted residue (`run_aggregationUnported`, `run_yearUnportedSelected`, `hot_adjustmentRowsUnported`, `run_soakActivityGapsEmitted`). Retrofit under aggregation or summed output steps counted.
- **Geographic output detail (NATION/STATE/ZONE/ROADTYPE) -- COUNTED via `run_outputOptionsUnported` (COUNTY outside PROJECT, LINK in it; Rates exempt, MOVES forces LINK) (PLAN.md §7.3.85).** Only COUNTY (96) and LINK (19) verified; AggregationSQLGenerator.java:956-1191 final aggregation not ported; option not read.
- **Output breakdown flags -- COUNTED via `run_outputOptionsUnported` (any other configuration) (PLAN.md §7.3.85).** Every verified XML: modelyear, fueltype, emissionprocess, distinguishparticulates, onroadoffroad, roadtype, onroadscc = true; sourceusetype, movesvehicletype, offroadscc, segment, hpclass = false. MOVES also has fuelSubType, sector, engTechID, regClassID flags (OutputEmissionsBreakdownSelection.java:17-53). Model: `out_regClassID`, `out_fuelSubTypeID`, `out_engTechID` are "NULL on this run"; `out_SCC` always computed. Comparator additionally ignores `roadTypeID` (tolerance.toml `[compare] ignored_columns`), so road type is checked only through the SCC.
- **Output units -- COUNTED via `run_outputOptionsUnported` (any other units) (PLAN.md §7.3.85).** Fixed grams, Million BTU (`out_emissionQuant` "Million BTU for pollutant 91 and grams"), miles, seconds. MOVES offers kg/lb/ton, J/kJ, km and time factors (runspec/*MeasurementSystem.java). No verified XML sets non-default units.
- **Activity output (VMT, SHO, SH, SHP, SHIdling, starts, population; MOVESActivityOutput) -- NOT PORTED-absent, COUNTED apart via `run_activityOutputUnported`** (see summary 7). Hotelling hours and source hours likewise.
- **MOVESRun, MOVESError, MOVESEventLog, MOVESTablesUsed, MOVESWorkersUsed, bundleTracking, translate_* tables (database/CreateOutput.sql) -- NOT PORTED-absent.** Output is a CSV relation emitted by `tools/emit-oracle-table.py`; no MOVES output database.
- **BaseRateOutput / BaseRateUnits (CreateOutputRates.sql; `lookuptableflags truncatebaserates`, RunSpecXML.java:1466-1480) -- NOT PORTED-absent.**
- **Estimate uncertainty -- N/A.** Forced off in MOVES 5 (RunSpecXML.java:141-142 "Uncertainty is disabled in this version").
- **pmsize, savedata, donotexecute, generatordatabase, doNotPerformFinalAggregation, scenarioID** (RunSpecXML.java:219-235) -- debugging/legacy; NOT PORTED. `donotexecute` (any calculator named) and `doNotPerformFinalAggregation` change MOVESOutput and are COUNTED via `run_outputOptionsUnported` (PLAN.md §7.3.85); `pmsize`, `savedata`, `generatordatabase` and `lookuptableflags` do not change MOVESOutput.

## 4. Input data (County / Project Data Manager, Additional Input DBs)

Importers enumerated from `gov/.../master/implementation/importers/*.java`. Status of moves.esm read path from `onroad/default-database.esm` (default parquet), the 17-table domain documents (`moves-onroad.esm`, `inputs/*.esm`) and the input overrides found (`db_avft`, `db_onroadretrofit`, `db_soakactivityfraction`, `db_input_emissionratebyage`).

| importer -> table | MOVES SINGLE/PROJECT behaviour | moves.esm | evidence |
|---|---|---|---|
| SourceTypePopulationImporter -> sourceTypeYear | REPLACE (InputDataManager.java:2834-2835) | **COUNTED via `run_domainTablesUnread`** (PLAN.md §7.3.85) (default) | `db_sourcetypeyear ../movesdb/SourceTypeYear.parquet`; washtenaw copies equal default (PLAN.md:4293) |
| AgeDistributionImporter -> sourceTypeAgeDistribution | REPLACE | **COUNTED via `run_domainTablesUnread`** (PLAN.md §7.3.85) | `db_sourcetypeagedistribution` default only |
| VehicleTypeVMTImporter -> HPMSVtypeYear | REPLACE | **COUNTED via `run_domainTablesUnread`** (PLAN.md §7.3.85) | default only |
| VehicleTypeVMTImporter -> HPMSVtypeDay, SourceTypeYearVMT, SourceTypeDayVMT | used by TAG (TotalActivityGenerator.java:1170-1200, 1436-1600); suppress default HPMSVtypeYear (InputDataManager.java:2837-2846) | **COUNTED via `run_domainTablesUnread`** (any row) (PLAN.md §7.3.85) | 0 references in model; parquet files present in `inputs/washtenaw-county/` (0 rows) but mounted by nothing |
| VehicleTypeVMTImporter -> monthVMTFraction, dayVMTFraction, hourVMTFraction | row merge | **COUNTED via `run_domainTablesUnread`** (PLAN.md §7.3.85) | default only |
| AverageSpeedDistributionImporter -> avgSpeedDistribution | row merge | **COUNTED via `run_domainTablesUnread`** (PLAN.md §7.3.85) | default only |
| RoadTypeDistributionImporter -> roadTypeDistribution | row merge | **COUNTED via `run_domainTablesUnread`** (PLAN.md §7.3.85) | default only (`inputs/washtenaw-county-hotelling/RoadTypeDistribution.parquet` mounted by nothing) |
| RampFractionImporter -> roadType.rampFraction | stored only | N/A | `rampFraction` read nowhere in MOVES 5 outside the importer (grep of gov, calc, generators, database) |
| FuelImporter / FuelSupplyImporter / FuelFormulationImporter -> fuelSupply, fuelFormulation, fuelUsageFraction | fuelSupply REPLACE; others merge; user fuelUsageFraction suppresses default (InputDataManager.java:2824-2830) | **COUNTED via `run_domainTablesUnread`** (PLAN.md §7.3.85) | default only |
| AVFTImporter / FuelImporter -> avft | AVFTControlStrategy | PORTED | `scale-county-avft`, `project-avft`; NATION geography and empty project avft unreached (PLAN Phase 6) |
| MeteorologyImporter -> zoneMonthHour | row merge | **COUNTED via `run_domainTablesUnread`** (PLAN.md §7.3.85) | `db_zonemonthhour` default only; Rates "temperature-bin" lookup runs depend on this |
| IMImporter -> IMCoverage | REPLACE (domain DB only) | **COUNTED via `run_imUnported` from the domain database's table** (PLAN.md §7.3.85) | `run_imProgramRows` joins default IMCoverage (summary 4) |
| StartsImporter -> startsPerDay | merge | PORTED | domain-declared `db_startsperday` |
| StartsImporter -> starts (user) | replaces computed starts (AdjustStarts.sql:22-35) | **COUNTED via `run_inputStartsRows`** (PLAN.md §7.3.85) | no `db_starts`; `isUserInput` 1 unrelated reference |
| StartsImporter -> startsPerDayPerVehicle, startsHourFraction, startsMonthAdjust, startsAgeAdjustment, startsOpModeDistribution | merge | **COUNTED via `run_domainTablesUnread`** (PLAN.md §7.3.85) (default) | default-database.esm only; `run_startModeAgeVariation` counts only default age variation |
| IdleImporter -> totalIdleFraction | merge | **COUNTED via `run_domainTablesUnread`** (PLAN.md §7.3.85) (default) | not in domain documents |
| IdleImporter -> idleModelYearGrouping, idleMonthAdjust, idleDayAdjust | AdjustTotalIdleFraction.sql | PORTED | `scale-county-idle-adjust*` |
| HotellingImporter -> 5 hotelling tables | AdjustHotelling.sql | PORTED; 3+ years COUNTED (`hot_adjustmentRowsUnported`) | `userdb-hotelling-multiyear*`, pending `userdb-hotelling-threeyear` |
| ZoneImporter / ZoneRoadTypeImporter -> zone, zoneRoadType | merge | PORTED; added keys COUNTED (`run_zoneRowsAdded`, `run_zoneRoadTypeRowsAdded`) | domain documents |
| OnRoadRetrofitImporter -> onRoadRetrofit | strategy | PARTIAL, COUNTED (`run_retrofitUnported`, `run_retrofitTableOff`) | §7.3.79 |
| LEV/NLEV tool DB -> emissionRateByAge | user DB merge | PORTED for the tool's 10 pairs; rest COUNTED (`run_levUnported`) | §7.3.82 |
| (user) soakActivityFraction | user rows replace TTG-6 per zone | PORTED; Hour-step gap cells COUNTED (`run_soakActivityGapsEmitted`) | §7.3.67, §7.3.75 |
| LinkImporter, LinkSourceTypeHourImporter, OffNetworkLinkImporter, DriveScheduleSecondLinkImporter, LinkOpmodeDistributionImporter (Project) | project inputs | PORTED with COUNTED residue (`run_projectShortfall`, `run_userLinkModeRows`, `run_userLinkGaps`, `run_projectScheduleUnported`) | `project-*`, `rates-project*` |
| Project DB's age distribution, fuel, meteorology, I/M | REPLACE/merge from project DB | **COUNTED via `run_domainTablesUnread`** (PLAN.md §7.3.85) (default) | same as rows above; `washtenaw-project` copies defaults |
| GenericImporter (any table), any other table in a `<databaseselections>` user DB | MasterLoop merge ahead of default | **GUARDED: tools/check-sources.py check 11** (PLAN.md §7.3.85) | only the overrides listed above exist |
| Domain-database validation (`*Importer.sql` checks, NEIQA `onroadCDBchecks.sql`) | refuses incomplete CDMs | NOT PORTED | every SINGLE/PROJECT capture runs with `skipdomaindatabasevalidation` (PLAN.md:4727-4740) |

## 5. Control strategies

- **AVFT -- PORTED** (F86-F88). Unreached: NATION geography, empty project avft.
- **On-Road Retrofit -- PARTIAL, COUNTED** (`run_retrofitUnported`): checked only at running and start exhaust, SINGLE/DEFAULT, Inventory and Rates, 1-2 years, Hour step without aggregateBy. Counted: other processes, aggregation, PROJECT, summed output steps, MOVES-switched-off tables (`run_retrofitTableOff`, never captured).
- **LEV / NLEV -- PORTED** (user DB emissionRateByAge merge, F93-F95). Counted: other pairs, added keys, PROJECT.
- **I/M -- PARTIAL.** DEFAULT domain blend ported for THC/CO/NOx running+start and venting THC (Cook County only). COUNTED: SINGLE/PROJECT programs and unchecked pairs (leaks). Fixed: the refusal reads the domain database's IMCoverage (summary 4, §7.3.85). The GUI I/M tool (IMGUI) is not relevant to output.
- **Rate-of-Progress -- COUNTED, permanent** (`run_ropUnported`; MOVES 5.0.1 aborts in spDoRateOfProgress, F92).

## 6. Rates mode

- RatePerDistance (16 runs with rows; processes 1, 9, 10, 11, 12, 13, 15, 18, 19), RatePerVehicle (12; 2, 11, 13, 16, 17, 18, 19, 90, 91, 93), RatePerStart (6; 2, 16), StartsPerVehicle (6), RatePerProfile (5; 12 only), RatePerHour (3; 17, 90, 91, 93) -- **PORTED**, all six tables compared, empty ones included, `temperature` and `relHumidity` compared as values.
- **Rates + time aggregation -- COUNTED** (`run_ratesUnported`; invalid in MOVES).
- **PROJECT Rates: user drive schedule or zero-speed link -- COUNTED** (`run_projectScheduleUnported`); two links on one road type at Rates -- COUNTED.
- **Temperature/humidity-bin lookup tables (user meteorology as bins) -- COUNTED via `run_inputZoneMonthHourDiffers`** (§4, PLAN.md §7.3.85): a county `zoneMonthHour` that differs from the default is refused. Every Rates run uses the default meteorology of Washtenaw or Cook.
- Of 21 Rates runs, 14 mount the DEFAULT domain document, 5 a PROJECT database, and 2 a user DB (retrofit, LEV); none mounts a county database with non-default activity or meteorology.

## 7. Outside the core run

| MOVES feature | status |
|---|---|
| GUI RunSpec editor, Pre-aggregation options panel, Scale panel | NOT PORTED (runspecs are hand-written JSON over captured runspec tables) |
| County/Project Data Manager GUI, templates, "Create Input Database", input DB conversion MOVES3/4 -> 5 (`database/ConversionScripts`, Convert3To5Action/Convert4To5Action, `commandline/DatabaseConverter.java`) | NOT PORTED |
| AVFT Tool (`master/avfttool`, AVFTToolRunner) | NOT PORTED (consumes its output table) |
| Fuel Wizard (importers/FuelWizard.java) | NOT PORTED |
| LEV/NLEV builder (BuildLEVAction, `database/LEV_NLEVScripts`) | NOT PORTED as a tool; its output table is read |
| ONI Tool (`database/ONITool`, ONIToolRunner) | NOT PORTED |
| Output post-processing scripts (`database/OutputProcessingScripts`: EmissionRates, CO/PM CAL3QHC and grams-per-mile/hour, DecodedMovesOutput, TabbedOutput) | NOT PORTED |
| Profile weight scripts (`database/ProfileWeightScripts`, SMOKE cb6/roc) | NOT PORTED |
| Summary Reporter, custom reports, Export to NIF/Pechan, GREET hooks, Update Future Emission Rates / Manufacture-Disposal / WTP rates actions | NOT PORTED |
| NEI QA scripts (`database/NEIQA`) | NOT PORTED |
| Batch / multi-run: command-line MOVES, LoopingTool, MultipleRunSpecCreator, MOVESOutputGrouper (`tools/`), OpModeDistCalc (`tools/`) | NOT PORTED (one `esm simulate` per runspec document) |
| Master/worker distribution, bundles | N/A by design (one evaluation) |
| MOVES-Matrix (external) | N/A |

## 8. Precision exceptions (known small divergences)

moves.esm `tolerance.toml`: per-cell 2e-5 relative, exact key set and row count; per-pollutant sums 1e-3. Onroad `cell_exception`s (all measured, all from MOVES's FLOAT storage or cancellation):
- `rates-venting`, `process-evap-fvv-day`: 1 cell each at 5e-5 (stored FLOAT soakActivityFraction leaves mode 300 a 2.1e-7 weight; permanent, EarthSciAST #536 declined).
- `project-grades`: 1 cell at 5e-5 (six-digit text rendering between worker and external calculator; electric Total Energy on a -3% link cancels 25.6x).
- `scale-county-timeagg-processes-day`: 1 cell at 5e-5 (Year sum cancels 12x). `-processes-month`: 4 cells at 1e-4 (FLOAT SHO/population; 1315x cancellation).
- `scale-county-timeagg-soak-day`: 2 cells at 1e-4 (44x cancellation).
- `im-cook-venting`: 121 cells at 5e-5 (FLOAT soakActivityFraction at motorcycle early hours; FLOAT tankVaporVented differencing at two old 52 cohorts).
- Comparator ignores `MOVESRunID`, `iterationID`, `roadTypeID`, `emissionQuantMean/Sigma`.
`moves.rs/characterization/tolerance.toml` has no cell exceptions (byte-identity contract, not used for cross-implementation comparison).

## 9. Narrowly verified (secondary)

- County inputs: Washtenaw (26161) only, and only copies of the default. I/M: Cook (17031) only, DEFAULT domain only. DEFAULT-domain geography: 7 counties max.
- Calendar years 2015, 2020, 2025; no run before 2015 or after 2025.
- Source types never in a checked output: 41, 43, 53, 54, 61 (checked: 11, 21, 31, 32, 42, 51, 52, 62). Fuels checked: 1, 2, 3, 5, 9 (all MOVES 5 onroad fuels in sampleVehiclePopulation).
- Cost: `expand-sourcetype` peaks at 62 GB RSS (PLAN.md §7.3.40 "Unchanged runs"); `scale-county-idle-nonhaptog` 1,575 s user CPU at 35.9 GB peak RSS for one county (§7.3.73); an all-pollutant 7-process capture passed 57 GB in ten minutes and was split (§7.3.74). A full-year, all-hour, all-source-type county inventory (the usual SIP/conformity run) has not been attempted.
