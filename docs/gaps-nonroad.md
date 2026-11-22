# NONROAD gaps: MOVES 5 (Java driver + NONROAD Fortran) vs moves.esm

Audited 2026-11-21, read-only, against `/projects/illinois/eng/cee/ctessum/ctessum/code/moves.esm-docs` (branch `docs-status`, HEAD `cc2897c`, which includes the NONROAD retrofit port).
Ground truth: `canonical-moves.sif:/opt/moves` (MOVES 5.0.1). Short path prefixes used below:
`NR/` = `/opt/moves/NONROAD/NR08a/SOURCE/`, `NRJ/` = `/opt/moves/gov/epa/otaq/moves/master/nonroad/`,
`LOADER` = `/opt/moves/gov/epa/otaq/moves/worker/framework/NonroadOutputDataLoader.java`,
`AGG` = `/opt/moves/gov/epa/otaq/moves/master/framework/AggregationSQLGenerator.java`,
`IDM` = `/opt/moves/gov/epa/otaq/moves/master/framework/InputDataManager.java`,
`MODEL` = `nonroad/model.esm` (510 variables), `CAT` = `moves-nonroad.esm`.

Status labels: **NOT PORTED-silent** (MOVES produces it, moves.esm produces nothing and has no counter: a run that asks for it returns an incomplete or wrong answer with no signal) / **NOT PORTED-documented** (absent, acknowledged in a doc, no counter) / **COUNTED via `<var>`** (refused by a scalar that `tools/check-nonroad-shape.py` asserts is 0) / **PARTIAL** / **PORTED-unverified** (computed, but no capture checks that path) / **PORTED-verified** / **N/A** (MOVES never exposes it).

---

## 0. Ranked summary (silent gaps first)

1. **NOT PORTED-silent: every nonroad process except running exhaust.** Crankcase THC (process 15) and the seven evaporative and refueling processes NONROAD computes (diurnal 30, hot soak 31, running loss 32, tank permeation 20, hose permeation 21, refueling displacement 18, spillage 19), with all their NRHCSpeciation and NRAirToxics species, are missing. MOVES writes them from the `.BMV` file (`LOADER:720-768`) and from `.BMX` column 13 (`LOADER:442-447`). MODEL: `run_processID` is "Running exhaust, the one process this model computes"; the 13-row `epp_polProcessID` is all process 1; `nrevapemissionrate` and `nrcrankcaseemissionrate` are not mounted. A selected evap or crankcase pollutant-process gets `rpp_isEmitted` = 0 and no row, and no counter fires (the only refusal scalars are `run_extraScopeRows`, `run_equipmentPointsDropped`, `run_mixSetsOffOne`, `run_retrofitUnported`). For gasoline lawn & garden and recreational equipment, evaporative HC is a large share of total HC, so this gap is the most consequential.
2. **NOT PORTED-silent: Atmospheric CO2 (9001) and NH3 (3001) at running exhaust.** MOVES emits both (`LOADER:424-429` CO2 from the NONROAD CO2 column; `LOADER:485-503` NH3 = fuel gallons x 0.116 g/gal gasoline, 0.0833 diesel). MODEL's `epp_polProcessID` description admits CO2 "is not carried: a RunSpec selecting it misses those rows, and the comparator's key check says so". That check runs only where a capture exists. NH3 is not mentioned anywhere. Neither has an in-model counter.
3. **NOT PORTED-silent: every nonroad user or domain input database table except `nrRetrofitFactors`.** `IDM:3805ff` `mergeNonRoad` copies all 38 tables listed in `/opt/moves/NonroadTableFilter.csv` from each user input database and the domain database: population, surrogates, growth, month/day/hour allocation, nrFuelSupply (a user `nrFuelSupply` REPLACES the default, `IDM` ~3820), tech fractions, emission rates, deterioration, source-use type, scrappage, sulfur adjustment, and the speciation and toxics tables. MOVES also uses `ZoneMonthHour`, `FuelFormulation` and `County` from the run. Every `runspecs/nonroad/*.esm` mounts only the `runspec*` tables plus `movesoutput` (and `nrretrofitfactors` in one), so the model reads national defaults. `tools/check-sources.py` check 8 (`:419-438`) guards only the retrofit table. A county-data-manager nonroad run (local population, fuel, meteorology) would emit default-database numbers with no signal.
4. **NOT PORTED-silent: output breakdown and geographic detail are not read.** MOVES's aggregation (`AGG:1423-1500`) groups nonroad output by the RunSpec's `outputemissionsbreakdownselection`: SCC, model year, fuel type and fuel subtype, and engTechID, sectorID and hpID when hpClass, sector or engine tech is selected. MODEL never reads it (0 hits for "breakdown"). It always emits (SCC, modelYear) rows with engTechID, sectorID and hpID NULL (`out_engTechID`, `out_sectorID`, `out_hpID`). A RunSpec that turns off model year or SCC, or turns on hpClass, sector or engine tech, gets the wrong row shape. Every capture uses the same breakdown (modelyear, fueltype, emissionprocess, onroadscc).
5. **NOT PORTED-documented: `MOVESActivityOutput` for nonroad.** MOVES writes six activity types per (SCC, hp, model year, tech) record (`LOADER:507-534`): hours (2), population (6), load factor (12), average hp (9), retrofit fraction (10) and retrofit units (11). The LF and hp are activity-weighted at aggregation (`AGG:1500ff`, `:1787ff`). moves.esm emits no activity relation (`grep activityoutput` in the repo: 0 hits). It is acknowledged as out of scope in `docs/nonroad-logging-county.md:2220` and has no counter. MOVES's own nonroad post-processing scripts (`/opt/moves/database/NonroadProcessingScripts/*.sql`: 19 per-hp, per-SCC, per-vehicle and per-operating-hour EF and inventory scripts) depend on it and are not ported.
6. **PORTED-unverified: weekend day type, any month but August, and any year but 2020.** Every nonroad capture is month 8, day 5, year 2020 (table in §3). Weekend reads `nrdayallocation` dayID 2 through the same join (`point_dayFraction`) but is never checked. Another year needs `n_foldYear` rebound; that is COUNTED by `run_extraScopeRows`, so it is not silent.
7. **PARTIAL: speciation and toxics coverage.** NMOG, TOG, NonHAPTOG and fuel consumption (99) are verified for gasoline only. CH4, NMHC, VOC and PM2.5 are verified for gasoline and nonroad diesel. CNG, LPG and marine-diesel species are not checked. 19 of the ~70 nonroad running-exhaust toxics are verified; the rest use the same ratio machinery but different rows. PLAN §7.3.39 lists as not ported but unexercised: last-write-wins between ratio tables, `MXTECH = 32`, and a TOG row when neither summand is selected.
8. **COUNTED:**
   - More than one county, state, year, month or day in a run, or a fold-length mismatch (`run_extraScopeRows`).
   - Retrofit at state or nation scale, N-unit retrofit records, and every retrofit table NONROAD rejects (`run_retrofitUnported` / `run_retrofitTableOff`).
   - Declared-shape mismatches (`run_equipmentPointsDropped`, `run_outputCohortCount`, `run_outputPolProcessCount`, `run_mixSetsOffOne`).
9. **Precision:** one permanent `cell_exception` (nr-railroad-support-nation, SCC 2270002066 / model year 2010, held to 2e-4: the binary32 population sum crosses a `.POP` rounding boundary; the conversion op was declined in EarthSciAST #674). Every other nonroad cell is within 2e-5. moves.rs's tolerance.toml has no nonroad cell exception; its suite gates nonroad on per-pollutant sums at 1e-2.
10. **N/A (MOVES never exposes):** subcounty, state and 50-state NONROAD region levels, PERIOD TOTAL or annual/seasonal summation, RFG, high altitude (all factors 1.0), alternate scrappage, `/DAYTEMPRVP/`, `/AGE ADJUSTMENT/`, SI report, EPS2 AMS, legacy per-start exhaust, hourly allocation, commercial marine SCCs.

---

## 1. Equipment sectors, SCCs and fuels

Default DB: `nrSCC` 214 SCCs (fuel 1: 103, CNG 3: 14, LPG 4: 32, nonroad diesel 23: 63, marine diesel 24: 2); `nrEquipmentType` 88; `Sector` 1-12; `nrSourceUseType` 1,183 equipment points.

- **All 12 sectors and all 5 fuels: PORTED-verified (exhaust only).** The five whole-inventory runs selected onroad diesel (fuel 2), which matches no `nrscc` row, so the `/SOURCE CATEGORY/` packet was empty and NONROAD ran everything (`scc_isSelected`; `NRJ/NonroadOptFileSqlHelper.java:488`). Those runs are nr-agriculture-state, nr-airport-support-county, nr-industrial-county, nr-mixed-nonroad and nr-railroad-support-nation. Measured over every capture's MOVESOutput: **213 of 214 SCCs appear**, including:
  - underground mining 2270009010
  - oil field 2265010010, 2268010010 and 2270010010
  - snowmobiles 2260001020
  - rec-marine diesel 2282020005 and 2282020010 (fuel 24)
  - every 2-stroke, 4-stroke, LPG and CNG family

  The only SCC never emitted is **2270007010** (diesel shredders >6 hp, sector 7), presumably zero population in the captured geographies.
- **Per-sector selections actually captured:** recreational (1), construction (2), industrial (3), lawn & garden (4), agriculture (5), commercial (6), logging (7), airport support (8), pleasure craft (11) and railroad support (12). Underground mining (9) and oil field (10) were never selected by name, only reached through the empty packet. They take the same code path, so this is a low risk.
- **Fuel selection by nonroad fuel ID: PARTIAL.** Fuels 1, 1+2 and 23 are captured. Selecting 3, 4 or 24 alone is unverified, although their numbers are checked in the whole-inventory runs. MOVES selects SCCs as the cross product of the selected fuels and the selected sectors' equipment types (`NRJ/NonroadInputCreator.java:179`, `NonroadOptFileSqlHelper.java:486-488`).
- **Commercial marine (2280002xxx): N/A.** It is not in MOVES's `nrscc`. The marine-diesel sulfur branch for 2280002 (`NR/emsadj.f:264-266`) is ported (`point_isMarineDiesel`) and reached only through 2282020.

## 2. Processes and pollutants

MOVES nonroad registrations (`/opt/moves/CalculatorInfo.txt`):
- NonroadEmissionCalculator, 18 registrations: running-exhaust THC, CO, NOx, CO2, SO2, PM10, PM2.5, NH3, BSFC (99) and Total Energy (91); crankcase THC; and THC at 18, 19, 20, 21, 30, 31 and 32.
- NRHCSpeciationCalculator: CH4, NMHC, NMOG, TOG and VOC at 1, 15, 18, 19, 20, 21, 30, 31 and 32.
- NRAirToxicsCalculator: 205 registrations over processes 1, 15, 18-24 and 30-32.
- Chains: NRAirToxics -> NRHCSpeciation -> NonroadEmissionCalculator.

The MOVES output mapping is in `LOADER:405-503` (`.BMX`) and `LOADER:720-768` (`.BMV`).

| Process | MOVES source | moves.esm status | Evidence |
|---|---|---|---|
| Running exhaust (1): THC, CO, NOx, SO2, PM10 | `NR/clcems.f`; `LOADER:406-441` | PORTED-verified | all 14 runs |
| Running exhaust: PM2.5 (110) = PM10 x 0.92 (gasoline), 0.97 (diesel), 1 (CNG/LPG) | `LOADER:454-483` | PORTED; verified for gasoline and diesel 23 only | `nft_pm25Fraction`; nr-airtoxics, nr-retrofit |
| Running exhaust: fuel/BSFC (99), grams from gallons x density | `LOADER:448-452` | PORTED; verified for gasoline only | nr-airtoxics selects 9901 |
| Running exhaust: **CO2 (90)** | `NR/clcems.f:250` carbon balance; `LOADER:424-429` | **NOT PORTED-silent** | `epp_polProcessID` description (MODEL line ~3772); not in the 13-row `epp` list |
| Running exhaust: **NH3 (30)** = gallons x 0.116 or 0.0833 | `LOADER:485-503` | **NOT PORTED-silent** | not in `epp`; no hit for NH3 or ammonia in MODEL |
| Running exhaust: Total Energy (91) | registered in CalculatorInfo, but no need-flag in `LOADER:111-127` | N/A (probably empty in MOVES too; unverified) | - |
| Running exhaust: CH4, NMHC, NMOG, TOG, VOC, NonHAPTOG (NRHCSpeciation) | `/opt/moves/calc/nrhcspeciation` | PORTED. CH4, NMHC and VOC verified for gasoline and diesel; NMOG, TOG and NonHAPTOG for gasoline only | `run_methaneIsSelected` etc.; nr-airtoxics (fuel 1), nr-retrofit (fuel 23) |
| Running exhaust: air toxics (VOC ratios, PAH gas/particle, dioxins, metals) | `/opt/moves/calc/nrairtoxics`, `NRAirToxicsCalculator.sql` | PORTED; 19 toxics verified for gasoline (2001, 2101, 2301, 2401, 2501, 2601, 2701, 4501, 4601, 6001, 6301, 6501, 6601, 6701, 6901, 13101, 14201, 16901, 18501) | nr-airtoxics-lawn-garden-county. Unverified: MTBE 22, 40-46, 61-62, other PAH (68-84, 168-184), other dioxins (130-146), every non-gasoline toxic |
| **Crankcase (15) THC**, plus its CH4…VOC and 47 crankcase toxics | `NR/clcems.f:239-245` (IDXCRA from `nrcrankcaseemissionrate`, units MULT); `LOADER:442-447` | **NOT PORTED-silent** | `nrcrankcaseemissionrate` not in CAT's 34 sources; `run_processID` = running only |
| **Diurnal (30)** | `NR/clcevems.f:603ff` (Wade equation, tmin/tmax, RVP) | **NOT PORTED-silent** | `nrevapemissionrate` not mounted; `mix_processGroupID` filtered to 1 ("the evap rows…") |
| **Tank permeation (20)**, with the ethanol blend effect | `NR/clcevems.f:335-383` | **NOT PORTED-silent** | as above |
| **Hose permeation (21)**, non-rec-marine plus rec-marine neck/supply/vent folded in | `NR/clcevems.f:385-541`; `.BMV` HosePerm column `LOADER:763` | **NOT PORTED-silent** | as above |
| **Hot soak (31)** (g/start x starts per hour) | `NR/clcevems.f:543-566` | **NOT PORTED-silent** | as above |
| **Running loss (32)** | `NR/clcevems.f:568ff` | **NOT PORTED-silent** | as above |
| **Refueling displacement (18)** (temperature, RVP, Stage II from `countyyear.refuelingvaporprogramadjust`) | `NR/clcevems.f:295-333`; `NRJ/NonroadOptFileSqlHelper.java:600`; `NonroadOptFileHelper.java:645` | **NOT PORTED-silent** | `countyyear` not mounted in CAT |
| **Spillage (19)**, including diesel/LPG/CNG equipment (non-gasoline fuels run IDXSPL only) | `NR/clcevems.f:236-237`, `:264-293` | **NOT PORTED-silent** | as above |
| Rec-marine hose permeation 22, 23, 24 (toxics only) | NRAirToxics registrations | N/A in practice: MOVES emits no row (nr-pleasure-craft-state selects benzene at 2022-2024 and gets none) | `rpp_isEmitted` description |
| Evap tech fractions (`nrengtechfraction` processGroupID 2) | `NRJ/NonroadDataFileHelper.java:2184` (`/MOVES EVAP TECH FRAC/`, `NR/rdevtech_moves.f`) | NOT PORTED (part of the evap gap) | `mix_processGroupID` = 1 only |

Why the evaporative and crankcase gap is silent: `rpp_isEmitted` is 0 for any selected pollutant-process outside `epp` (or outside the toxic roots), and `n_outputPolProcess` / `run_outputPolProcessCount` count only what the model emits. `tools/check-nonroad-shape.py` compares the model with itself, so it cannot see the gap. MOVES would write THC (and species) rows at 15, 18-21 and 30-32 for every gasoline cohort.

## 3. Geography and time

Captured scope (snapshots' `runspec*` tables):

| run | county | state | year | month | day | pollutant-processes |
|---|---|---|---|---|---|---|
| nr-agriculture-state | 19000 | 19 | 2020 | 8 | 5 | 201, 301, 3101, 10001 |
| nr-airport-support-county | 17031 | 17 | 2020 | 8 | 5 | 201, 301, 3101, 10001 |
| nr-airtoxics-lawn-garden-county | 26161 | 26 | 2020 | 8 | 5 | 29 running-exhaust |
| nr-commercial-nation | 0 | 0 | 2020 | 8 | 5 | 101, 201, 301, 10001 |
| nr-construction-state | 26000 | 26 | 2020 | 8 | 5 | 101, 201, 301, 3101, 10001 |
| nr-industrial-county | 17031 | 17 | 2020 | 8 | 5 | 201, 301, 10001 |
| nr-lawn-garden-county | 26161 | 26 | 2020 | 8 | 5 | 101, 201, 301, 10001 |
| nr-logging-county | 26161 | 26 | 2020 | 8 | 5 | 101, 201, 301, 10001 |
| nr-mixed-nonroad | 26161 | 26 | 2020 | 8 | 5 | 101, 201, 301, 10001 |
| nr-pleasure-craft-state | 12000 | 12 | 2020 | 8 | 5 | 101, 201, 301, 2022-2024, 10001 |
| nr-railroad-support-nation | 0 | 0 | 2020 | 8 | 5 | 201, 301, 3101, 10001 |
| nr-recreational-county | 26161 | 26 | 2020 | 8 | 5 | 101, 201, 301, 3101, 10001 |
| nr-retrofit-county(-base) | 26161 | 26 | 2020 | 8 | 5 | 101, 201, 301, 501, 3101, 7901, 8701, 10001, 11001 |

- **County, state (pseudo-county from `PreAggSTATE.sql`) and nation (`PreAggNATION.sql`) scale: PORTED-verified** (PLAN §7.3.34-7.3.36). MOVES writes only `Region Level: COUNTY` or `US TOTAL` (`NRJ/NonroadOptFileHelper.java:212-262`, lines 35-39 of the method).
- **State-to-county allocation through surrogates** (`nrstatesurrogate`, `NR/alocty.f`, `getind.f` year rule): PORTED-verified (`eqt_allocationFraction`).
- **Multiple counties, states, years, months or day types in one RunSpec: COUNTED via `run_extraScopeRows`.** It counts rows beyond one in runspeccounty, state, year, month and day, plus `n_foldYear` != runYear - baseYear + 1. MOVES loops NONROAD once per (county, year, month, day) (`NRJ/NonroadEmissionCalculator.java:120`, DAY granularity).
- **Weekend (dayID 2): PORTED-unverified.** `nrdayallocation` has dayIDs 2 and 5. The model keys on `runDayID`, and no capture uses 2.
- **Months other than 8: PORTED-unverified.** The month fraction ladder and printed `%10.3f` renormalization are ported (PLAN §7.3.37 rule 5), and the national month fractions were probed in pandas. The temperature-branch question is settled by the captured daytime means: Washtenaw 73.6 F (the cold branch), Cook 76.4 F, Florida 85.0 F and nation 79.2 F (the hot branch), so both `emsadj.f` branches are exercised.
- **Years other than 2020: COUNTED** (`n_foldYear` default 31 is checked by `run_extraScopeRows`). It is ported in principle; no capture.
- **Time aggregation: N/A.** NONROAD is always run as `Period type: Monthly / Summation type: TYPICAL DAY` (`NRJ/NonroadOptFileHelper.java:64-73`). `AGG:1496-1498` does no time aggregation for nonroad, and every row carries hourID 0. MODEL does the same (`out_hourID` = 0, `out_dayID` from runspecday). `nrHourAllocation`, `nrHourAllocPattern` and `nrHourPatternFinder` are merged by MOVES but read by no nonroad Java or Fortran (grep shows only the table filter, CreateDefault and NEIQA checks): N/A.
- **NONROAD subcounty (`NR/prcsub.f`, `alosub.f`), state and 50-state region levels (`prcsta.f` as a region option), and period, annual or seasonal totals: N/A** (MOVES writes none of them).
- **Retrofit at state or nation scale: COUNTED** (`run_retrofitUnported` via `run_isCountyScale`).
- **Mixed ONROAD+NONROAD RunSpec** (`snapshots/mixed-onroad-nonroad`): unverified; that capture ships no MOVESOutput (PLAN:3892).

## 4. Physical adjustments

| Adjustment | MOVES/NONROAD | moves.esm |
|---|---|---|
| Growth (`nrgrowthpatternfinder`, `nrgrowthindex`, `NR/grwfac.f`, `getgrw.f`) | `NRJ/NonroadDataFileHelper.java:1519-1600` | PORTED-verified (`gpf_*`, `gi_*`; state rows outrank the national 0 row; nation fold = min growthPatternID) |
| Scrappage (`nrscrappagecurve` NREquipTypeID 0, `NR/scrptime.f`) | `:1608` | PORTED-verified (`dc_NREquipTypeID` = 0) |
| Alternate scrappage per equipment type (`/ALTERNATE SCRAPPAGE/`, `NR/rdalt.f`; `nrequipmenttype.useDefaultScrappage`) | `NRJ/NonroadDataFileHelper.java:1633` "implement later" | N/A (MOVES never writes it) |
| Age distribution fold (`NR/agedist.f`, `modyr.f`) | - | PORTED-verified, Float32 recurrence (`fold_*`) |
| Deterioration `1 + A*min(age,cap)^B`, missing pair -> 1 | `NR/emfclc.f`, `fnddet.f` | PORTED-verified (`det_*`, `tech_ratedDeterioration`) |
| Technology fractions, per-set renormalization (`NR/rdtech_moves.f`), half-open hp lookup | `:2184` | PORTED-verified (`run_mixSetsOffOne` guard) |
| Emission factor lookup: SCC fallback chain, nearest hp bin (`NR/fndefc.f`) | - | PORTED-verified (`tech_rate*`) |
| Sulfur: SOx rewrite, diesel PM sulfur correction, `/PM BASE SULFUR/` (`nrsulfuradjustment`) | `NR/clcems.f:290-305`, `emsadj.f:258-271`; `NonroadOptFileSqlHelper.java:653` | PORTED-verified (`point_soxCorrection`, `tech_hasSulfurAlternate`, the 7-digit `F10.0` read window) |
| Temperature correction (exhaust, 75 F branch) | `NR/emsadj.f` | PORTED-verified (both branches exercised) |
| Oxygenate correction (exhaust; oxygen weight % from nrfuelsupply x fuelformulation) | `NR/emsadj.f`; `NonroadOptFileSqlHelper.java:147` | PORTED-verified (`run_oxygenWeightPercent`) |
| RVP, minimum/maximum temperature, EtOH market share and volume | `NRJ/NonroadOptFileHelper.java:166-189` | NOT PORTED. NONROAD uses them only in `clcevems.f` (evaporative), so this is part of gap #1 and has no exhaust effect |
| Altitude (`County.altitude` L/H -> `lhigh`) | `NR/emsadj.f:274-279`; ALT* factors = 1.0 (`NR/nonrdprm.inc:261-265`) | N/A (a multiply by 1.0). MODEL has no altitude variable (grep: 0 hits); the result is identical |
| RFG (`lrfg`) | `NR/rdnropt.f:213-219`: commented out, forced .FALSE. | N/A |
| Stage II refueling control | `NonroadOptFileSqlHelper.java:600` (countyyear) | NOT PORTED (evap gap #1) |
| Retrofit (`nrretrofitfactors`, `/RETROFIT/`) | `NR/rdrtrft.f`, `vldrtrftrecs.f`, `clcrtrft.f`; `NonroadDataFileHelper.java:1888` | PORTED-verified at county scale for diesel HC/CO/NOx (nr-retrofit-county, 1,881 cells). COUNTED (`run_retrofitUnported`): state/nation runs, N-unit records (fraction > 1), and every record NONROAD rejects including any PM record (F100), via `run_retrofitTableOff`. Not emitted: the FracRetro and UnitsRetro activity rows (gap #5) |
| Clamp at zero per (SCC, hp, MY, tech) record | `LOADER` `Math.max(0, …)` | PORTED-verified (per technology, PLAN §7.3.37 rule 3) |
| Legacy per-start exhaust (`clcems.f:309-313`, IDSTHC+) | `nremissionrate` has only 101, 201, 301, 9901 and 10001 | N/A |
| `/AGE ADJUSTMENT/` activity (`NR/rdact.f:226`), `/DAYTEMPRVP/` daily files (`rdday.f`) | not written by MOVES | N/A |

## 5. Output

- **MOVESOutput columns:** MODEL emits yearID, monthID, dayID, hourID 0, stateID, countyID (NULL at state and nation scale), pollutantID, processID 1, fuelTypeID (unmapped nonroad IDs 1, 3, 4, 23, 24), modelYearID, SCC and emissionQuant (grams), with zoneID, linkID, sourceTypeID, regClassID, fuelSubTypeID, engTechID, sectorID and hpID NULL. `out_*` variables. MOVES also writes roadTypeID 100 on every nonroad row; MODEL emits no roadTypeID column (`grep -c roadType nonroad/model.esm` = 0), which is a cosmetic gap. Otherwise this matches the captures' breakdown exactly.
- **Output breakdown options: NOT PORTED-silent** (gap #4). MOVES groups by engTechID, sectorID and hpID when those breakdowns are selected (`AGG:1423-1470`), and sums SCC or model year away when they are deselected. The loader fills engTechID (from `engineTech.engTechName`), sectorID and hpID on every record (`LOADER:395-403`, `:720-725`). MODEL reads no breakdown selection.
- **Fuel subtype breakdown** (`CompilationFlags.ALLOW_FUELSUBTYPE_OUTPUT`, `AGG` ~1520): NOT PORTED (`out_fuelSubTypeID` is NULL); probably off in the shipped build.
- **Geographic output detail:** derived from scale (county, or NULL county at state or nation), not read from `<geographicoutputdetail>`. A county-scale multi-county run reported at STATE (`AGG:1787ff`) is COUNTED (multiple counties).
- **Activity output (`MOVESActivityOutput`): NOT PORTED-documented** (gap #5). MOVES writes hours, population, load factor (activity-weighted), average hp (weighted), FracRetro and UnitsRetro per record (`LOADER:507-534`). Every capture has it (for example, nr-lawn-garden-county has 1,936 rows, 484 each of activityTypeID 2, 6, 9 and 12), and none is compared.
- **Mass units:** MODEL emits grams only. MOVES converts to the RunSpec's `massfactors` units (a general output option, covered by the other audit). All nonroad captures use Grams.
- **Post-processing scripts** (`/opt/moves/database/NonroadProcessingScripts/`: 19 scripts, including EmissionFactors_per_hphr/OperatingHour/Vehicle by SCC/Equipment/HP/MY, Inventory_by_*, Population_by_Sector_and_SCC and DecodedNonroadOutput) and `ProfileWeightScripts/profileWeights_nonroad_{cb6,roc}.sql` (`nrrocspeciation`): NOT PORTED (user-run; grep in moves.esm-docs: 0 hits).

## 6. Input databases (the silent-gap area)

MOVES merges every table in `/opt/moves/NonroadTableFilter.csv` (38 tables: nragecategory, nratratio, nrbaseyearequippopulation, nrcrankcaseemissionrate, nrdayallocation, nrdeterioration, nrdioxinemissionrate, nremissionrate, nrengtechfraction, nrequipmenttype, nrevapemissionrate, nrfuelsupply, nrfueltype, nrfuelsubtype, nrgrowthindex, nrgrowthpattern, nrgrowthpatternfinder, nrhcspeciation, nrhourallocation, nrhourallocpattern, nrhourpatternfinder, nrhpcategory, nrhprangebin, nrintegratedspecies, nrmetalemissionrate, nrmethanethcratio, nrmonthallocation, nrpahgasratio, nrpahparticleratio, nrretrofitfactors, nrscc, nrscrappagecurve, nrsourceusetype, nrstatesurrogate, nrsurrogate, nrusmonthallocation, processgroupid, nrsulfuradjustment).

It merges them from the default database, the domain database and each RunSpec `<inputdatabase>` (`IDM:1470-1490`, `:1561-1580`, `:3805ff`), with no row filters. `GenericImporter.java:180-225` imports any NR table, and `FuelImporter` imports `nrFuelSupply`. NONROAD also reads `ZoneMonthHour` (the temperature in /OPTIONS/), `FuelFormulation`, `County` (altitude) and `CountyYear` (Stage II) from the execution database.

moves.esm: `CAT` mounts 34 national tables (listed by `data_sources`). Each `runspecs/nonroad/*.esm` shadows only `db_runspec{county,state,year,month,day,sector,fueltype,pollutantprocess}` and `db_movesoutput`; `nr-retrofit-county` also shadows `db_nrretrofitfactors`.

| User/domain table a nonroad run can carry | moves.esm status |
|---|---|
| nrretrofitfactors | PORTED, guarded by `tools/check-sources.py` check 8 (`:419-438`) |
| nrbaseyearequippopulation (state population), nrstatesurrogate (county allocation), nrgrowthindex, nrgrowthpatternfinder, nrmonthallocation, nrusmonthallocation, nrdayallocation, nrsourceusetype (hp, hours/yr, LF, life), nrequipmenttype (surrogate), nrscrappagecurve, nrengtechfraction, nremissionrate, nrdeterioration, nrsulfuradjustment, nrscc | **NOT PORTED-silent.** The tables are read, but only from the default database; no guard compares a run's execution database with them (unlike retrofit). Shadowing is possible document by document, but nothing forces it |
| nrfuelsupply + fuelformulation (user fuel; a user nrFuelSupply replaces the default) | **NOT PORTED-silent** (same mechanism) |
| zonemonthhour (user meteorology) | **NOT PORTED-silent** (same mechanism) |
| nrhcspeciation, nrmethanethcratio, nratratio, nrpah*, nrdioxin*, nrmetal*, nrintegratedspecies, nrhpcategory | **NOT PORTED-silent** (same mechanism) |
| nrevapemissionrate, nrcrankcaseemissionrate, countyyear (Stage II) | not read at all (gap #1) |
| nrhourallocation, nrhourallocpattern, nrhourpatternfinder, nrhprangebin, nragecategory, nrsurrogate, nrgrowthpattern, processgroupid, nrrocspeciation | N/A: not read by the nonroad path, or descriptive only |

Note: all 14 verified captures have empty `<inputdatabase>` and `<scaleinputdatabase>` (fixture XMLs), and PLAN §7.3.34 measured that the default-database runs' execution tables equal the national ones. The model has never been checked against a nonroad run with user data except retrofit.

## 7. Options standalone NONROAD has that MOVES never exposes (N/A)

- `/REGION/` levels SUBCOUNTY, STATE and 50STATE (`NR/rdnrreg.f`, `prcsub.f`, `alosub.f`). MOVES writes COUNTY or US TOTAL only.
- `/PERIOD/` Annual or Seasonal period, and PERIOD TOTAL summation (`NR/rdnrper.f:85-87`). MOVES hard-codes Monthly / TYPICAL DAY.
- RFG flag (commented out, `NR/rdnropt.f:213-219`). High altitude: factors are all 1.0.
- `/ALTERNATE SCRAPPAGE/` (MOVES: "implement later").
- `/DAILY FILES/` and `/DAYTEMPRVP/`.
- `/AGE ADJUSTMENT/`.
- `/SI REPORT/` (commented out in `NonroadOptFileHelper.java:701ff`).
- EPS2 AMS output (written blank).
- `/INDICATORS/` and `/ALLOC FILES/` from user files. MOVES generates the `.ALO` files from `nrstatesurrogate`, which is ported.
- Legacy EMSFAC, TECH and SEASON file reuse (`useOld*Files`).
- Commercial marine SCCs (2280xxx) are not in `nrscc`.

## 8. Precision (known small divergences)

- `moves.esm-docs/tolerance.toml`:
  - Per-cell gate `[cell] rel = 2e-5` on every nonroad run; per-pollutant sum gate `nonroad = 1e-2`.
  - One nonroad `cell_exception`: `[fixtures."nr-railroad-support-nation".cell_exception]`, columns (SCC, modelYearID) = (2270002066, 2010), `rel = 2e-4`. The cause is a binary32 nation population sum (137670.547 -> `.POP` 137670.6, where MOVES has binary64 137670.538 -> .5), amplified by `agedist.f`'s 2010 cancellation. It is permanent (EarthSciAST #536; conversion op PR #674 declined).
  - The former airtoxics `scope` (pollutants 131 and 142) is retired under moves-snapshot/v2.
  - Worst cells per run (PLAN): 4.6e-6 to 9.4e-6, railroad 1.865e-05 outside the exception.
- `moves.rs/characterization/tolerance.toml`: no nonroad cell exception. Nonroad is gated by per-pollutant sums at `NONROAD_REL_TOL = 1e-2` in `crates/moves-cli/tests/full_suite_regression.rs` (comment at `:44`).
- Structural precision dependence: F60 (each nonroad RunSpec must declare `Float32`; binary64 drops whole cohorts, e.g. nr-logging-county's four rows) and F101 (retrofit fractions read through the packet's half-up `%.2f`).
- Operational: every new nonroad run needs three per-run declared numbers (`n_equipmentPoint`, `n_outputCohort`, `n_outputPolProcess`). They are checked against recomputed values, not discovered, so a new RunSpec needs a probe evaluation before it can be bound. The output relation is assumed to be a RECTANGLE of cohorts x emitted pollutant-processes (`n_outputCohort` description). A toxic whose ratio table lacks some fuels' rows, in a mixed-fuel run, would break that assumption. This is untested (the airtoxics run is gasoline-only), so it is a potential shape mismatch, not a confirmed one.
