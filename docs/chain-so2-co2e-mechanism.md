# `chain-so2-co2e-mechanism` — computation specification

The port specification for the **last three unported MOVES calculators**, written
to the method of `docs/nonroad-logging-county.md` and `docs/process-airtoxics.md`:
the input inventory determined from evidence, the chain with source lines into
`../moves.rs`, every join with its exact key pairs, the reusable shapes, and
worked examples whose numbers can be checked by hand.

`SO2Calculator`, `CO2AERunningStartExtendedIdleCalculator` and
`TOGSpeciationCalculator` are ported here and nowhere else. With them the
calculator track is **19 of 19**.

Three things about this rung are worth stating before the tables, because each
of them changed how the document is written rather than only what it computes.

* **The chain stops being multiplicative.** Every earlier fixture in this port
  computes an output row by SCALING one other row. Three of this run's
  twenty-six SUM several, and §2.6 is the second pass that costs.
* **`runspecchainedto` is not a complete statement of the chain.** It declares
  SO2's parent and says nothing about the other two calculators', which carry
  theirs as Java constants. §2.5, and `docs/esm-conventions.md` §40.2.
* **`TOGSpeciationCalculator` is much smaller than its registration count.**
  `calculator-dag.json` credits it with 184 registrations. Against the pinned
  default database it registers 24 pairs and writes exactly one pollutant.
  §0.3 has the measurement.

---

## 0. The fixture at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/chain-so2-co2e-mechanism.xml` |
| Model | ONROAD, `modelscale` `Inv` (inventory), `modeldomain` `DEFAULT` |
| Geography | county 26161 (Washtenaw, Michigan), zone 261610, link 2616104 |
| Time | year 2020, month **8**, hour **7**, day types **2 (weekend) and 5 (weekday)** |
| Vehicles | sourceTypeID 21 (passenger car); fuel types **1, 2, 5, 9** |
| Road | roadTypeID 4 (urban restricted access) |
| Pollutant/process | **twenty-seven selected, twenty-six emitting**, all on process 1 |
| Model years | 1980–2020 (41) |
| Output | `db__out_chain_so2_co2e_mechanism__movesoutput`, **5,534 rows** |
| Output units | **Million BTU** for pollutant 91, **grams** for the other twenty-five; `outputtimestep` **Hour** |
| Calculator path | rates-first: `TotalActivityGenerator` → `SourceBinDistributionGenerator` → `BaseRateGenerator` → `BaseRateCalculator` → `HCSpeciationCalculator`, `AirToxicsCalculator`, **`SO2Calculator`**, **`CO2AERunningStartExtendedIdleCalculator`**, **`TOGSpeciationCalculator`** → output aggregation |
| Control | `chain-so2-co2e-mechanism-control`, five `<pollutantprocessassociation>` lines apart |
| Fixture | `fixtures/chain-so2-co2e-mechanism.esm` |
| Oracle | `./run-so2-co2e-oracle.sh` |

### 0.1 The RunSpec on disk does not describe the captured run

The same rule as `docs/mixed-onroad.md` §0.1 and `docs/evap-leaks.md` §0.1, and
for the same reason: the XML's `<month key>`, `<beginhour key>` and `<day key>`
are canonical `RunSpecXML` **0-based indices into sorted ID lists**, not
identifiers. The execution database's `runspecmonth`, `runspechour` and
`runspecday` say month 8, hour 7, and day types 2 **and** 5. **The XML's
`<day key="5"/>` is an out-of-range index into the sorted `DayOfAnyWeek` list
`[2, 5]`, which `default_db_setup.rs:2504-2540` resolves as "no day selected"
and falls back to ALL day types.** So this run is not weekday-only, and every
row count in this document is over both day types. The execution database is
the authority.

### 0.2 Why 5,534 rows, and which cohorts each block drops

5,534 = 2,767 cohorts × 2 day types, and the 2,767 are not one block size:

| block | cohorts | pollutant-processes |
|---|---:|---|
| energy and the two greenhouse gases | **125** | 91, 90, 98 |
| the two with a rate and an age key | **124** | 1 (THC), 6 (N2O) |
| every HC species and every toxic but one | **104** | 5, 20, 24, 25, 26, 27, 40–46, 79, 80, 86, 87, 88, 185 |
| ethanol | **64** | 21 |

The three sizes are **nested**, and the oracle asserts the nesting rather than
the counts alone:

* **125 − 124 is one cohort, model year 2000 electricity**, and it is the one
  key pair that separates the two rate tables. `emissionratebyage` is keyed by
  age group and carries no fuel-type-9 row at age group 2099; `emissionrate` is
  not keyed by age group and so has no row to be missing. THC drops that
  cohort, Total Energy keeps it.
* **124 − 104 is every electricity cohort**, twenty of them, and the cause is
  one absence inherited transitively: `methanethcratio` has no fuel subtype 90
  row, so methane and NMHC are not produced, NMOG and VOC die with NMHC, and
  every toxic is chained off VOC.
* **64 is ethanol (21)**, whose two ratio paths between them cover gasoline and
  E85 and no diesel. It is the only pollutant that **both** `ATRatio` paths
  reach, on disjoint fuel types — see §7.3.

A twenty-seventh pollutant-process is selected and emits nothing: **300001**,
the mechanism pseudo-pollutant 3000. It has no rate, no ratio and no summand.
The document computes that rather than filtering it out, which is what makes
`pp_emittedCohortCount` a check instead of a restatement.

### 0.3 `TOGSpeciationCalculator` is a small rung wearing a large number

`calculator-dag.json` records `registrations_count: 184` for it — the sixteen
CB05 mechanism pseudo-pollutants 1000, 1001 … 1018 plus `NonHAPTOG` (88) across
twelve organic-gas processes. **Those pseudo-pollutants do not exist in the
pinned default database.** Measured over the corpus, by unioning all 42
snapshots' `pollutant` tables:

```
116 distinct pollutantIDs, maximum 3000, and not one of 1000–1018
```

so against this database the calculator registers 24 pairs, not 184. The
`Section Processing` algorithm only ever produces pollutant 88 in any case: the
individual mechanism species are computed upstream by `AirToxicsCalculator` and
the pseudo-pollutants are chain bookkeeping. **Quote 24, not 184, and say where
the 184 comes from** — a rung whose advertised size is 7.7× its real one is
exactly the sort of number that gets copied forward.

### 0.4 The class is loaded everywhere; the table is not

`TOGSpeciationCalculator` is class-loaded in **all 42 snapshots**, because
`ExecutionRunSpec` calls its static `needsFinalAggregation()` whether or not the
run selects a mechanism. So class-loading is no evidence at all that it ran, and
a snapshot picked on that signal would be the wrong one — including the
misleadingly named `chain-tog-speciation`, which does **not** exercise it.

The real discriminator is `integratedSpeciesSet`: **14 rows here and 0 in every
other snapshot of the corpus.** Its fourteen pollutants are exactly this run's
fourteen air toxics.

---

## 1. Input inventory

### 1.1 The tables the parent already reads

Geography, time, the activity chain, the cohort structure and the fuel-usage
rebase, the drive-cycle operating-mode weights, `emissionratebyage`,
`fuelsupply` / `fuelformulation` / `fuelsubtype`, `criteriaratio`,
`altcriteriaratio`, `methanethcratio`, `hcspeciation`, `atratio`,
`atrationongas`, `evsalesfraction`, `fleetavgadjustment`, `fullacadjustment`,
`monthgrouphour`, `zonemonthhour`, `sourcetypemodelyear`,
`temperatureadjustment`, `runspecchainedto`, `pollutantprocessmodelyear`,
`modelyeargroup` — all of `docs/process-airtoxics.md` §1, unchanged. §2.1
records how much of the answer that alone buys.

### 1.2 The seven tables this fixture adds

| table | rows | what it is |
|---|---:|---|
| `emissionrate` | 85,169 | the age-INDEPENDENT rate, for polProcessIDs 601 and 9101 |
| `evefficiency` | 7 | the battery × charging divisor, all polProcessID 9101 |
| `sulfateemissionrate` | 7 | `SO2Calculator`'s `SO2FuelCalculation2` |
| `pollutant` | 27 | `globalWarmingPotential`, the `CO2EqPollutant` extract |
| `integratedspeciesset` | 14 | the mechanism species `TOGSpeciationCalculator` subtracts |
| `minorhapratio` | 490 | `AirToxicsCalculator`'s third live path, pollutants 40–46 |
| `pahgasratio` | 8 | its fourth, naphthalene gas (185) |

and three columns of `fuelsubtype` the port had never needed —
`carbonContent`, `oxidationFraction` and `energyContent` — plus
`fuelformulation.sulfurLevel`.

**Two of the new columns are nullable and both matter.**
`fuelsubtype.energyContent` is NULL on subtype 90 (Electricity) and
`pollutant.globalWarmingPotential` is NULL on 24 of the 27 rows. Both are listed
in `float_columns` and arrive as NaN (`docs/esm-conventions.md` §11), and both
are stopped before they can become a factor: the first by the SO2 division's own
guard, the second inside `lib/co2_equivalent.esm`'s
`global_warming_potential_is_selected`. A flag-times-value spelling of either
would have produced `0 × NaN = NaN` (§19.4a, §29.2).

### 1.3 What is NOT an input

`carbonoxidationbyfueltype` (4 rows) is in the snapshot and this document does
**not** read it. It is `CO2AERunningStartExtendedIdleCalculator`'s own working
table, recomputed here from `fuelsupply` and `fuelsubtype`, and its four rows
are then used as an independent check — §6.2. Reading it would have made the
CO2 stage a transcription of MOVES's answer instead of a port of its arithmetic.

`generalfuelratio`, `emissionrateadjustment`, `imcoverage`, `starttempadjustment`,
`atratiogas2` and `pahparticleratio` are all **empty**. `noxhumidityadjust` is
populated and read by nothing: pollutant 3 is not selected, so the NOx arm of
the temperature branch is unreachable.

---

## 2. The computation chain

### 2.1 What is unchanged, measured rather than assumed

This snapshot's geography, year, month, hour, day types, source type, fuel types
and road type are `process-airtoxics`'s exactly. **Retargeting that fixture at
this snapshot — a path substitution and a model rename, no new equation —
reproduced 2,538 of the 5,534 rows with an exact key set and a worst relative
error of 8.207e-06.** That is what says the whole activity spine S1–S9, the
cohort structure, the fuel-usage rebase S10–S12, the drive-cycle weights, the
age-group-keyed rate, the fuel-supply resolution, `criteriaratio` and the E85
`altTHC` branch are that document's unchanged. §27.3's "retarget first" rule,
and the retarget audit found nothing this time.

### 2.2 Three roots, off two rate tables

`emissionratebyage` carries polProcessID **101 alone**. Total Energy
Consumption (9101) and N2O (601) take their rates from `emissionrate`, which is
the same relation minus the age-group key:

| | `emissionratebyage` | `emissionrate` |
|---|---|---|
| key pairs on the rate lookup | 7 | 6 |
| the seventh | `ageGroupID` | — |
| polProcessIDs here | 101 | 601, 9101 |

The two are disjoint on polProcessID, so `rt_hasRate` and `rtMode_rate` are
unions and not double counts; `run_rateTableOverlap` asserts that rather than
assuming it. The missing seventh key pair is not a simplification — it is the
whole of §0.2's 125-versus-124.

### 2.3 The temperature branch takes two of its four arms in one document

`adjust.rs:87-142` has four arms. Two are live here, and this is the first
fixture in the port where both are:

* **Electricity Total Energy on running exhaust** (process 1, fuel 9,
  pollutant 91) takes the EV quadratic about **72 °F**, clamped at
  `max(·, 0)`, and suppressed for light duty above a heat index of 67 °F.
* **Everything else** takes the fall-through quadratic about **75 °F**.

The PM arm needs pollutant 112 or 118 and the NOx arm pollutant 3; neither is
selected. The snapshot's **one** `temperatureadjustment` row is
`(9101, fuel 9, regClass 0)`, so the EV arm is the only one with coefficients
and every other row's factor is exactly 1.

At this hour's 59.5 °F the EV raw adjustment is
`(59.5 − 72) × (0.00225 + 0.00028 × (59.5 − 72)) = +0.015625`, so it is **above**
the clamp and reaches an emitted number — 1.5625 % on 42 rows. The heat-index
suppression is **reachable** (source type 21 is light duty) and does not fire,
at 7.5 °F of margin. Contrast `mixed-onroad`, where the same code is a no-op at
hour 9 with a margin of 0.0999985 °F (`docs/esm-conventions.md` §37.2).

The `evefficiency` divisor is the last step of the sequence and is worth
**0.779 to 0.893** — 12 % to 22 % — on the same 42 rows. It is applied to the
ROOT row's rate, so Atmospheric CO2 and CO2 Equivalent inherit it, which is
what MOVES does by reading the already-divided value back out of
`MOVESWorkerOutput`.

### 2.4 `HCSpeciationCalculator`, now producing four species and a sum

`hcspeciation.rs:640-767` returns up to five pollutants from one THC block.
This run selects all five where `process-airtoxics` selected two:

```
methane (5)  = THC × r                      r = methanethcratio.CH4THCRatio
NMHC   (79)  = THC × (1 − r)
NMOG   (80)  = NMHC × speciationFactor(8001)
VOC    (87)  = NMHC × speciationFactor(8701)
TOG    (86)  = NMOG + methane                          ← A SUM, see §2.6
```

**NMOG needed no new equation.** `hcspeciation` is keyed by the OUTPUT
pollutant-process, so the existing join on a rate row's own `polProcessID`
found its 8001 rows the moment the table had them. `process-airtoxics`'s own
source note predicted exactly this.

Methane is the one species that is the ratio itself rather than its complement,
out of the same `methanethcratio` row, so it is a fourth arm of the same
`rtSup_hcSpeciesFactor` union.

### 2.5 `SO2Calculator` and `CO2AE` step 1a: two stages off the energy root

Both are one multiplication applied to the Total Energy Consumption the root
produced, in **kilojoules** — the Million BTU divisor is applied at the output
row and nowhere earlier, because both calculators read `MOVESWorkerOutput` and
`engine.rs:1286-1310` converts on the way out.

```
SO2 (31) = energy × meanBaseRate × WsulfurLevel / energyContent     so2_calculator.rs:2079
CO2 (90) = energy × sumCarbonContent × sumOxidationFraction × 44/12  co2ae:1090-1094
```

`WsulfurLevel`, `energyContent`, `sumCarbonContent` and `sumOxidationFraction`
are market-share-weighted means over the county's fuel supply — fuel-**type**
quantities entering a per-**formulation** product. That is exact rather than an
approximation, and the reason is worth writing down once: a factor constant
across the supply factors out of a sum whose weights are the same market shares,
so `Σ_s share_s × energy_s × F` and `(Σ_s share_s × energy_s) × F` are the same
number. MOVES computes the second because its energy row is already collapsed;
this document computes the first because its energy is still per formulation.

**`runspecchainedto` declares SO2's parent and not CO2's.** The table carries
`3101 ← 9101` and no 9001 row at all, because only `AirToxicsCalculator` reads
it; `CO2AERunningStartExtendedIdleCalculator` carries `TOTAL_ENERGY_POLLUTANT_ID`
as a Java constant (co2ae:161). The document unions MOVES's declaration with the
one calculator constant it needs and asserts the two never overlap
(`run_chainDeclarationOverlap`). `docs/esm-conventions.md` §40.2.

**Electricity fails SO2 twice and CO2 never**, and the difference is the whole
of §0.2's 104-versus-125:

| | SO2 (31) | Atmospheric CO2 (90) |
|---|---|---|
| the rate table | no fuelTypeID 9 row in `sulfateemissionrate` | — |
| the fuel chemistry | subtype 90's `energyContent` is **NULL** | `carbonContent` and `oxidationFraction` are **real zeros** |
| the outcome | no row: 104 cohorts | a row of exactly 0: 125 cohorts |

Either SO2 reason alone would give the same block, so this snapshot cannot say
which one MOVES used; §7.4 records that.

### 2.6 The additive stage, and why there has to be one

Three of the twenty-six are sums:

```
TOG       (86) = NMOG + methane                                hcspeciation.rs:767
CO2e      (98) = 1×CO2 + 28×CH4 + 265×N2O                      co2ae step 2
NonHAPTOG (88) = max(NMOG − Σ 14 integrated species, 0)        togspeciation.rs
```

A summed row is not a multiplicative chain step at any depth, so the document
gains a **second pass** over the same relation: `rtDay_directQuant` for the
scaled pollutants, three signed aggregates over the same relation joined on the
cohort, and `rtDay_quant` their union. **One pass is enough, because none of the
three feeds another** — and that is a property of this run to be checked, not a
general law.

`rspp_isSummed` holds all three out of the chain-root resolution, and that is
not cosmetic: **8601 is the only pollutant-process in this run with two
`runspecchainedto` rows**, and the parent-join aggregate would have summed 8001
and 501 into the nonsense id 8501.

All three input sets are the **calculators'** constants. MOVES's table records
TOG's two inputs and says nothing about the other two, which is the same
asymmetry §2.5 met.

**Step 2 of `CO2AE` reads step 1a's own output back.** The SQL inserts the
Atmospheric CO2 rows into `MOVESWorkerOutput` and then selects from it, so the
document forms CO2 Equivalent from `rtDay_directQuant` and not from the energy.
A port that ran step 2 off the energy would use the same three weights and get
a different answer.

**The emission mask of a summed row is the UNION of its summands'.** TOG's two
summands are both 104 cohorts; CO2 Equivalent's are 125, 104 and 124 and union
to 125; NonHAPTOG's are 104 and 104/64 and union to 104. That is the SQL's own
`group by`: every group present becomes a row.

### 2.7 `AirToxicsCalculator`, now with four of its six paths

| path | keys on | outputs | rows |
|---|---|---|---:|
| `ATRatioGas1` | fuel FORMULATION, month, model year | 20, 21, 24, 25, 26, 27 | 446 |
| `ATRatioNonGas` | source type, fuel SUBTYPE, model-year group | 20, 21, 24, 25, 26, 27 | 650 |
| `minorHAPRatio` | fuel SUBTYPE, model-year group | 40–46 | 490 |
| `pahGasRatio` | the BLOCK's fuel TYPE, model-year group | 185 | 8 |

The two this snapshot adds are **direct** paths — they take a VOC (87) block
rather than reading `runspecchainedto` — and they differ from each other in
exactly one thing, which decides where each lives in the document.
`minorHAPRatio` keys on the emission's fuel subtype, so it is a per-formulation
quantity on the `(rate row × supplied formulation)` relation; `pahGasRatio`
builds its key **once per fuel block** (airtoxics.rs:725-729), so its ratio is a
rate-row quantity that reaches the answer through the per-formulation VOC
factor. **Where a lookup is KEYED and where its result is USED are different
questions**, and only the first decides the shape.

The four are summed because `airtoxics.rs:657-682` APPENDS every path's
emissions to the output block rather than choosing between them. The two dead
paths need an Organic Carbon (111) block (`pahParticleRatio`) and a non-empty
`atratiogas2`.

---

## 3. Join structure

The joins this fixture adds to `docs/process-airtoxics.md` §3:

| id | left | right | key pairs | filter |
|---|---|---|---|---|
| J46 | rate × supply | `minorhapratio` | `polProcessID`, `fuelSubtypeID` | `model_year_in_group` |
| J47 | rate | `pahgasratio` | `polProcessID`, `fuelTypeID` | `model_year_in_group` |
| J48 | rate | `sulfateemissionrate` | `polProcessID`, `fuelTypeID` | `model_year_in_group` |
| J49 | rate × mode | `emissionrate` | `polProcessID`, `opModeID`, `shortModYrGroupID`, `regClassID`, `engTechID`, `fuelTypeID` | — |
| J50 | rate | `evefficiency` | `ageGroupID`, `regClassID`, `sourceTypeID`, `polProcessID` | — |
| J51 | rate × day × rate | — | `cohortOrdinal` | the summed-pollutant gate, and the summand's pollutant |
| J52 | rate × day × rate × `pollutant` | — | `cohortOrdinal`; `pollutantID` | the CO2 Equivalent gate |
| J53 | rate × day × rate × `integratedspeciesset` | — | `cohortOrdinal`; `pollutantID` | the NonHAPTOG gate |

**J51–J53 are the new shape**, and the thing to notice is that the *left* side
of each contributes only a scalar predicate.

**The general alternative works, and was measured rather than assumed.** A
single weight relation indexed by `(output pollutant-process, input
pollutant-process)` needs a **two-sided** join: `rt_polProcessID` on the left
matching `rct_outputPolProcessID` and `rt_polProcessID` on the right matching
`rct_inputPolProcessID`, which is the same column on both sides of one clause
list. A per-clause `syms` pair resolves it, and a probe on this fixture confirms
it drives correctly — 8601 picks up 208 non-zero cells, the sum of its two
declared inputs, and every other chained pollutant-process picks up its own.

So the choice between the two is a **fidelity** question, not a capability one,
and it goes the other way: `runspecchainedto` does not declare CO2 Equivalent's
or NonHAPTOG's summands at all (§2.5), so a table-driven form would have to be
half table and half constant. Writing each calculator's summand set the way its
own source writes it keeps all three the same shape and keeps every join
one-sided. §27.1's "a `join.on` key column must be 1-D" is the neighbouring
rule, and it is not the obstacle here.

Three of the new lookups (J46, J47, J48) decode a **self-described model-year
band** — `beginYYYYendYYYY` in one column — with `lib/keys.esm`'s
`model_year_in_group`, so the divisor 10000 is a literal in exactly one place in
the repository.

---

## 4. Reusable shapes

Imported by reference, not restated:

* `lib/onroad_activity.esm` — `source_bin_slot` (the packed `sourceBinID`),
  `ev_energy_divisor`, `is_energy_pollutant`, `energy_unit_divisor`,
  `kilojoules_per_million_btu`. The last four were written for
  `fixtures/process-brakewear.esm` and are used here unchanged; this fixture is
  the second consumer of each, which is what makes them library shapes rather
  than one document's inline arithmetic.
* `lib/adjustments.esm` — `exact_else_wildcard`, `gpa_blend`,
  `quadratic_temperature_adjustment`, `speciation_factor`.
* `lib/keys.esm` — `model_year_in_range`, `model_year_in_group`,
  `flat_relation_major` / `flat_relation_minor`.
* `lib/identifiers.esm` — `pol_process_id`, used to build 9101 from the
  pollutant constant and the row's own process, so the CO2 chain constant is a
  pollutant id and not a hard-coded pollutant-process id.

**One new library file**, `lib/co2_equivalent.esm`, with two templates:

* `carbon_to_carbon_dioxide_mass_ratio` — 44/12, with §7.1's measurement in its
  description. It is here rather than inline for the reason
  `kilojoules_per_million_btu` is: a conversion whose value is a *fidelity
  decision* belongs somewhere the decision can be written beside it.
* `global_warming_potential_is_selected` — the `CO2EqPollutant` extract
  predicate, returning the WEIGHT rather than a flag so a NaN can never leave it.

---

## 5. Literals and enums

Eleven pollutant ids are named in `enums`, and each is a constant a *calculator*
carries rather than a value a table supplies:

| enum | id | whose constant |
|---|---:|---|
| `TotalGaseousHydrocarbons` | 1 | `hcspeciation.rs` |
| `Methane` | 5 | `hcspeciation.rs:670`, `co2ae:168` |
| `NitrousOxide` | 6 | `co2ae:168` |
| `SulfurDioxide` | 31 | `so2_calculator.rs:155` |
| `NonMethaneHydrocarbons` | 79 | `hcspeciation.rs:679` |
| `NonMethaneOrganicGases` | 80 | `togspeciation.rs`, `hcspeciation.rs:767` |
| `TotalOrganicGases` | 86 | `hcspeciation.rs:767` |
| `NonHapTog` | 88 | `togspeciation.rs:40` |
| `AtmosphericCO2` | 90 | `co2ae:150`, `co2ae:168` |
| `TotalEnergyConsumption` | 91 | `so2_calculator.rs:161`, `co2ae:161`, `engine.rs:1286` |
| `CO2Equivalent` | 98 | `co2ae` |
| `PetroleumEnergyConsumption` / `FossilFuelEnergyConsumption` | 92 / 93 | `engine.rs:1286-1310` |

The last two are named although this run selects neither, **because the rule is
the port and not the run**: the unit conversion applies to 91, 92 and 93 and to
nothing else, and a membership rule written with one member is a different rule.

Three EV constants are parameters rather than enums, matching
`fixtures/process-brakewear.esm`: `evTemperatureSourceTypeCeiling` 40,
`evTemperatureSuppressionHeatIndex` 67.0, `evTemperatureReferenceDegF` 72.0.

Nothing else is a literal. Every ratio, rate, weight, band and membership set
comes off a table.

---

## 6. Hand-checkable worked examples

All four use **model year 2010, gasoline (fuel type 1), day type 5 (weekday)**,
so one activity number carries the whole set. Reference figures are
`MOVESOutput`'s own, stored at six significant digits.

### 6.0 The number every example starts from

```
Total Energy Consumption (91) = 10.7536 Million BTU
                              = 10.7536 × 1,055,055.9 = 1.134663e+07 kJ
```

The kilojoule figure is what all three new calculators consume; the Million BTU
figure is what `MOVESOutput` stores, and the conversion happens between them and
nowhere else.

### 6.1 Worked example A — SO2

```
meanBaseRate  = 1.99378e-06      sulfateemissionrate, fuel 1, band 19502050
WsulfurLevel  = 7.15             fuelformulation 9114, market share 1.0
energyContent = 41.696           fuelsubtype 12

factor = 1.99378e-06 × 7.15 / 41.696 = 3.418920e-07
SO2    = 1.134663e+07 × 3.418920e-07 = 3.879 g
```

Reference: **3.879000000000**.

The diesel step is the other half of the claim. `sulfateemissionrate`'s bands
are `19502006` and `20072050`, so model year 2000 diesel takes 1.89735e-06 and
model year 2010 diesel takes 1.76298e-06 — a 7.6 % difference that a document
which read the first matching row without decoding the band would get wrong on
half the diesel cohorts. Reference for model year 2000 diesel, weekday:
**0.003815150000**.

### 6.2 Worked example B — Atmospheric CO2, checked against MOVES's own intermediate

```
sumCarbonContent     = 0.01982   recomputed; carbonoxidationbyfueltype says 0.019820000000
sumOxidationFraction = 1.0       recomputed; the same table says 1.000000000000
44/12                = 3.666667

factor = 0.01982 × 1 × 3.666667 = 0.0726733
CO2    = 1.134663e+07 × 0.0726733 = 824,553 g
```

Reference: **824529.000000000000**, which is 2.9e-05 relative — the float32
storage of the energy the reference actually used, and the document reproduces
the cell at **5.743e-06** because it carries the un-rounded energy through.

All four of `carbonoxidationbyfueltype`'s rows are reproduced: 0.01982 / 1 on
gasoline, 0.02022 / 1 on diesel, 0.0194 / 1 on ethanol, **0 / 0** on
electricity. That last row is why CO2 emits 125 cohorts of which 42 are exactly
zero, where SO2 emits 104 and drops them.

### 6.3 Worked example C — CO2 Equivalent

```
CO2  824529    × 1   = 824529
CH4     20.5384 × 28 =    575.08
N2O      1.43409 × 265 =   380.03
                       ----------
                         825484.1
```

Reference: **825484.000000000000**.

The two greenhouse terms are 0.07 % and 0.05 % of the total, which is the point
of asserting each summand separately: a CO2 Equivalent that had dropped **both**
would still be within 0.12 % of the right answer and would sail through any
tolerance in this repository.

### 6.4 Worked example D — NonHAPTOG, and the sum that does not fire

```
NMOG (80)                      = 41.7547 g
Σ of the 14 integrated species = 10.853 g
NonHAPTOG (88) = max(41.7547 − 10.853, 0) = 30.9017 g
```

Reference: **30.901700000000**. And the same cell's TOG:

```
TOG (86) = NMOG 41.7547 + methane 20.5384 = 62.2931 g
```

Reference: **62.293200000000**.

The clamp does not fire — not here and not anywhere in this run. §7.5.

### 6.5 The reproduction script

Extracted and run by `./run-so2-co2e-oracle.sh`. It reads only the input tables
of §1, computes the activity chain, all three roots, the multiplicative chain
and the additive stage, and **asserts** its worst relative error against `sho`,
against both `baseRate` tables and against `MOVESOutput`, plus the key set per
pollutant-process, the nesting of the three block sizes, and five things a
comparison against `MOVESOutput` could not see.

```python
#!/usr/bin/env python3
"""process-airtoxics reproduction from the snapshot's own input tables."""
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
COUNTY, ELECTRICITY, THC, THCPP = 26161, 9, 1, 101
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
TA=T("temperatureadjustment")
def temp_terms(pp,fuel,regclass,my):
    for rc in (regclass,0):
        for r in TA:
            if (r["polProcessID"]==pp and r["fuelTypeID"]==fuel and r["regClassID"]==rc
                    and r["minModelYearID"]<=my<=r["maxModelYearID"]):
                a=r["tempAdjustTermA"]; b=r["tempAdjustTermB"]
                return (float(a) if a is not None else 0.0, float(b) if b is not None else 0.0)
    return 0.0,0.0
def temp_factor(pp,fuel,regclass,my):
    # THC on running exhaust reaches general_temp_adjust's fall-through
    # quadratic (adjust.rs:141-142): not PM, not EV energy, not NOx.
    a,b=temp_terms(pp,fuel,regclass,my)
    return 1.0+(TEMP-75.0)*(a+b*(TEMP-75.0))
# A/C
GRP={r["monthID"]:r["monthGroupID"] for r in T("monthofanyyear")}[MONTH]
MGH=[r for r in T("monthgrouphour") if r["monthGroupID"]==GRP and r["hourID"]==HOUR][0]
acraw=float(MGH["ACActivityTermA"])+HEAT*(float(MGH["ACActivityTermB"])+float(MGH["ACActivityTermC"])*HEAT)
ACACT=min(max(acraw,0.0),1.0)
ACPEN={r["modelYearID"]:float(r["ACPenetrationFraction"]) for r in T("sourcetypemodelyear") if r["sourceTypeID"]==ST}
ACFUNC={r["ageID"]:float(r["functioningACFraction"]) for r in T("sourcetypeage") if r["sourceTypeID"]==ST}
FAC={r["opModeID"]:float(r["fullACAdjustment"]) for r in T("fullacadjustment") if r["sourceTypeID"]==ST and r["polProcessID"]==THCPP}
# fuel supply, criteria ratio and its E85 alternate
GPA=float([r for r in T("county") if r["countyID"]==COUNTY][0]["GPAFract"])
FSUB={r["fuelSubtypeID"]:r["fuelTypeID"] for r in T("fuelsubtype")}
FFORM={r["fuelFormulationID"]:r["fuelSubtypeID"] for r in T("fuelformulation")}
supply=collections.defaultdict(list)
for r in T("fuelsupply"):
    if r["fuelYearID"]!=FUELYEAR or r["monthGroupID"]!=GRP: continue
    st=FFORM[r["fuelFormulationID"]]
    if st not in FSUB: continue
    supply[FSUB[st]].append((r["fuelFormulationID"],float(r["marketShare"])))
def ratio_table(name):
    d={}
    for r in T(name):
        d[(r["fuelFormulationID"],r["polProcessID"],r["sourceTypeID"],r["modelYearID"],r["ageID"])]=(
            float(r["ratio"]),float(r["ratioGPA"]))
    return d
CR=ratio_table("criteriaratio"); ACR=ratio_table("altcriteriaratio")
def blend(tbl,pp,ff,my,age,default):
    v=tbl.get((ff,pp,ST,my,age))
    if v is None: return default
    return v[0]+GPA*(v[1]-v[0])
def crit(pp,ff,my,age): return blend(CR,pp,ff,my,age,1.0)
def scc(fuel,proc): return "%d"%(22*10**8+fuel*10**6+ST*10**4+ROAD*10**2+proc)
PPA={r["polProcessID"]:(r["pollutantID"],r["processID"]) for r in T("pollutantprocessassoc")}
# ---- the base-rate parents, kept per fuel FORMULATION ---------------------
# Three pollutant-processes carry a rate of their own here: THC (101) off the
# age-keyed `emissionratebyage`, and Total Energy (9101) and N2O (601) off the
# age-INDEPENDENT `emissionrate`.  Everything else in this run is chained.
# Each parent is carried per fuel FORMULATION because every downstream ratio
# keys on the formulation or on its subtype; the market-share collapse happens
# once, where a row is emitted.
ER=T("emissionrate")
def rates_flat(pp):
    d={}
    for r in ER:
        if r["polProcessID"]!=pp: continue
        b=r["sourceBinID"]
        d[(slot(b,10**16),slot(b,10**14),slot(b,10**12),slot(b,10**10),r["opModeID"])]=float(r["meanBaseRate"])
    return d
EVEFF={}
for r in T("evefficiency"):
    for my in range(max(r["beginModelYearID"],YEAR-maxage),min(r["endModelYearID"],YEAR)+1):
        if agegroup.get(YEAR-my)!=r["ageGroupID"]: continue
        EVEFF[(r["polProcessID"],ST,r["regClassID"],9,my)]=(
            float(r["batteryEfficiency"])*float(r["chargingEfficiency"]))
def temp_factor_for(pp,pol,fuel,regclass,my):
    # adjust.rs::general_temp_adjust.  Two of its four branches are reachable
    # here: the EV running-energy quadratic (process 1, fuel 9, pollutant 91)
    # and the fall-through quadratic.  The PM branch needs pollutant 112/118
    # and the NOx branch pollutant 3; neither is selected.
    a,b=temp_terms(pp,fuel,regclass,my)
    if fuel==ELECTRICITY and pol==91:
        adj=(TEMP-72.0)*(a+b*(TEMP-72.0))
        if adj<0.0: adj=0.0
        if ST<40 and HEAT>67.0: adj=0.0
        return 1.0+adj
    return 1.0+(TEMP-75.0)*(a+b*(TEMP-75.0))
BASE_RATE={}
def parent_block(pp,age_keyed):
    """One pollutant-process's emitted quantity, per (day, modelYear, fuelType)
    and per fuel formulation.  Returns (quantity dict, regClass dict)."""
    pol,proc=PPA[pp]
    coh=cohorts(pp)
    sbaf=rebase(coh)
    rate=rates_by_age(pp) if age_keyed else rates_flat(pp)
    modes=sorted({k[4] for k in rate})
    fac={r["opModeID"]:float(r["fullACAdjustment"])
         for r in T("fullacadjustment") if r["sourceTypeID"]==ST and r["polProcessID"]==pp}
    sbw=collections.defaultdict(float); sbwac=collections.defaultdict(float)
    for (my,fuel,et,rc),frac in sbaf.items():
        smy=shortgroup[mygroup[(pp,my)]]
        ev=evsf(pp,my,fuel,rc)
        for om in modes:
            k=(fuel,et,rc,smy,om,agegroup[YEAR-my]) if age_keyed else (fuel,et,rc,smy,om)
            r=rate.get(k)
            if r is None: continue
            sbw[(my,fuel,om)]+=frac*r*ev
            sbwac[(my,fuel,om)]+=frac*r*ev*(fac.get(om,1.0)-1.0)
    br=collections.defaultdict(float); brac=collections.defaultdict(float)
    for (my,fuel,om),v in sbw.items():
        for d in DAYS: br[(HD[d],my,fuel)]+=v*W[(HD[d],om)]
    for (my,fuel,om),v in sbwac.items():
        for d in DAYS: brac[(HD[d],my,fuel)]+=v*W[(HD[d],om)]
    BASE_RATE[pp]=(br,brac)
    have={(k[0],k[1],k[2],k[3],k[5]) for k in rate} if age_keyed else {k[:4] for k in rate}
    out=collections.defaultdict(dict); regclass={}
    for (my,fuel,et,rc),frac in coh.items():
        age=YEAR-my
        smy=shortgroup[mygroup[(pp,my)]]
        probe=(fuel,et,rc,smy,agegroup[age]) if age_keyed else (fuel,et,rc,smy)
        if probe not in have: continue
        acf=ACACT*ACPEN[my]*ACFUNC[age]
        tf=temp_factor_for(pp,pol,fuel,rc,my)
        eve=EVEFF.get((pp,ST,rc,fuel,my),1.0)
        regclass[(my,fuel)]=rc
        for d in DAYS:
            base_r=br[(HD[d],my,fuel)]+acf*brac[(HD[d],my,fuel)]
            act=sho[(HD[d],age)]/realdays[d]
            for ff,share in supply.get(fuel,[]):
                out[(d,my,fuel)][ff]=share*base_r*crit(pp,ff,my,age)*tf*act/eve
    return out,regclass
ENERGY_PP, N2O_PP = 9101, 601
thc,REGCLASS=parent_block(THCPP,True)
energy,_=parent_block(ENERGY_PP,False)
n2o,_=parent_block(N2O_PP,False)
coh=cohorts(THCPP)
assert len({(k[0],k[1]) for k in coh})==len(coh), "one (modelYear, fuelType) per cohort"
# ---- HCSpeciationCalculator: CH4 (5), NMHC (79), NMOG (80), VOC (87), TOG (86)
# hcspeciation.rs::speciate_emission.  Five species, where `process-airtoxics`
# selected two: NMOG and TOG are the two this run adds, and NMOG is the positive
# term of the NonHAPTOG residual below.
E10_SUBTYPE, E85_SUBTYPES, ALT_MIN_MY = 12, (50,51,52), 2001
MTHC=[r for r in T("methanethcratio")]
HCS=[r for r in T("hcspeciation")]
FFROW={r["fuelFormulationID"]:r for r in T("fuelformulation")}
def ch4ratio(sub,rc,my):
    for r in MTHC:
        if (r["processID"]==1 and r["fuelSubtypeID"]==sub and r["regClassID"]==rc
                and r["beginModelYearID"]<=my<=r["endModelYearID"]): return float(r["CH4THCRatio"])
    return None
def hcfactor(outpp,sub,rc,my,ff):
    for r in HCS:
        if (r["polProcessID"]==outpp and r["fuelSubtypeID"]==sub and r["regClassID"]==rc
                and r["beginModelYearID"]<=my<=r["endModelYearID"]):
            f=FFROW[ff]
            def g(c): return 0.0 if f[c] is None else float(f[c])
            oxy=g("MTBEVolume")+g("ETBEVolume")+g("TAMEVolume")+g("ETOHVolume")
            return float(r["speciationConstant"])+float(r["oxySpeciation"])*g("volToWtPercentOxy")*oxy
    return None
NMHC_PP, NMOG_PP, VOC_PP, TOG_PP, CH4_PP = 7901, 8001, 8701, 8601, 501
ch4=collections.defaultdict(dict); nmhc=collections.defaultdict(dict)
nmog=collections.defaultdict(dict); voc=collections.defaultdict(dict); tog=collections.defaultdict(dict)
for (d,my,fuel),per in thc.items():
    rc=REGCLASS[(my,fuel)]; age=YEAR-my
    for ff,q in per.items():
        sub=FFORM[ff]
        alt=(sub in E85_SUBTYPES and fuel==5 and my>=ALT_MIN_MY)
        r=ch4ratio(sub,rc,my)
        if r is None: continue
        ch4[(d,my,fuel)][ff]=q*r
        nmhc[(d,my,fuel)][ff]=q*(1.0-r)
        if not alt:
            for outpp,acc in ((NMOG_PP,nmog),(VOC_PP,voc)):
                f=hcfactor(outpp,sub,rc,my,ff)
                if f is not None: acc[(d,my,fuel)][ff]=q*(1.0-r)*f
        else:
            # adjust.rs::build_e85_block: the altTHC copy is the criteria-adjusted
            # rate rescaled by altRatio/ratio, and hcspeciation speciates THAT with
            # the E10 subtype's ratios.  Methane and NMHC stay on the ordinary block.
            cr=blend(CR,THCPP,ff,my,age,None); ar=blend(ACR,THCPP,ff,my,age,None)
            if cr is None or ar is None: continue
            alt_q=q*(ar/cr if cr>0.0 else 0.0)
            e10=ch4ratio(E10_SUBTYPE,rc,my)
            if e10 is None: continue
            for outpp,acc in ((NMOG_PP,nmog),(VOC_PP,voc)):
                f=hcfactor(outpp,E10_SUBTYPE,rc,my,ff)
                if f is not None: acc[(d,my,fuel)][ff]=alt_q*(1.0-e10)*f
        # TOG (86) = NMOG (80) + methane (5), summing the GATED species.  On the
        # altTHC path methane is absent from the speciated result, but the
        # ordinary block still produced one for the same cell, and both are
        # emitted, so the sum is taken on the emitted pair.
for (d,my,fuel),per in nmog.items():
    for ff,q in per.items(): tog[(d,my,fuel)][ff]=q+ch4[(d,my,fuel)].get(ff,0.0)
# ---- AirToxicsCalculator: FOUR live ratio paths off the VOC block ----------
# airtoxics.rs::air_toxics_block.  `process-airtoxics` reached two of the six;
# this run adds `minorHAPRatio` (the seven BTEX-family toxics 40-46) and
# `pahGasRatio` (naphthalene gas, 185).  `pahParticleRatio` needs an organic
# carbon (111) block and `ATRatioGas2` is empty, so those two stay dead.
MONTHS_OF_GROUP=collections.defaultdict(list)
for r in T("monthofanyyear"): MONTHS_OF_GROUP[r["monthGroupID"]].append(r["monthID"])
FORM_MONTHS=collections.defaultdict(set)
for r in T("fuelsupply"): FORM_MONTHS[r["fuelFormulationID"]].update(MONTHS_OF_GROUP[r["monthGroupID"]])
ATG={}
for r in T("atratio"):
    my=YEAR-r["ageID"]
    if not r["minModelYearID"]<=my<=r["maxModelYearID"]: continue
    for mo in FORM_MONTHS.get(r["fuelFormulationID"],()):
        ATG[(r["fuelFormulationID"],mo,my,r["polProcessID"])]=float(r["atRatio"])
def expand_group(g): 
    lo,hi=g//10000,g%10000
    return range(max(lo,YEAR-maxage),min(hi,YEAR)+1)
ATN={}
for r in T("atrationongas"):
    for my in expand_group(r["modelYearGroupID"]):
        ATN[(r["polProcessID"],r["sourceTypeID"],r["fuelSubtypeID"],my)]=float(r["ATRatio"])
MHR=collections.defaultdict(list)
for r in T("minorhapratio"):
    for my in expand_group(r["modelYearGroupID"]):
        MHR[(1,r["fuelSubtypeID"],my)].append((r["polProcessID"],float(r["atRatio"])))
PGR=collections.defaultdict(list)
for r in T("pahgasratio"):
    for my in expand_group(r["modelYearGroupID"]):
        PGR[(1,r["fuelTypeID"],my)].append((r["polProcessID"],float(r["atRatio"])))
CHAINED=collections.defaultdict(list)
for c in T("runspecchainedto"):
    CHAINED[c["inputPolProcessID"]].append(
        (c["outputPolProcessID"],c["outputPollutantID"],c["outputProcessID"]))
toxic=collections.defaultdict(dict)
def add_toxic(outpol,outproc,d,my,fuel,ff,v):
    acc=toxic[(outpol,outproc,d,my,fuel)]
    acc[ff]=acc.get(ff,0.0)+v
for (d,my,fuel),per in voc.items():
    for ff,q in per.items():
        sub=FFORM[ff]
        for outpp,ratio in MHR.get((1,sub,my),()):     # minorHAPRatio, VOC block
            add_toxic(PPA[outpp][0],1,d,my,fuel,ff,q*ratio)
        for outpp,ratio in PGR.get((1,fuel,my),()):    # pahGasRatio, VOC block
            add_toxic(PPA[outpp][0],1,d,my,fuel,ff,q*ratio)
        for outpp,outpol,outproc in CHAINED[VOC_PP]:   # ATRatioGas1 / ATRatioNonGas
            for r in (ATG.get((ff,MONTH,my,outpp)), ATN.get((outpp,ST,sub,my))):
                if r is None: continue
                add_toxic(outpol,outproc,d,my,fuel,ff,q*r)
# ---- SO2Calculator: SO2 (31) from Total Energy Consumption -----------------
# so2_calculator.rs::calculate.  SO2FuelCalculation1 is the market-share-weighted
# mean sulfur level and energy content of the (year, monthGroup, fuelType) fuel
# supply; SO2FuelCalculation2 expands SulfateEmissionRate's modelYearGroupID.
FST={r["fuelSubtypeID"]:r for r in T("fuelsubtype")}
def num(v): return 0.0 if v is None else float(v)
fc1={}
for f,forms in supply.items():
    ec=sum(share*num(FST[FFORM[ff]]["energyContent"]) for ff,share in forms)
    ws=sum(share*num(FFROW[ff]["sulfurLevel"]) for ff,share in forms)
    fc1[f]=(ec,ws)
fc2=collections.defaultdict(list)
for r in T("sulfateemissionrate"):
    if r["polProcessID"] not in POLPROCS: continue
    lo,hi=r["modelYearGroupID"]//10000,r["modelYearGroupID"]%10000
    for my in range(my_lo,my_hi+1):
        if lo<=my<=hi: fc2[(r["fuelTypeID"],my)].append((r["polProcessID"],float(r["meanBaseRate"])))
SO2_POL=31
so2=collections.defaultdict(dict)
for (d,my,fuel),per in energy.items():
    ec,ws=fc1.get(fuel,(0.0,0.0))
    if ec==0.0: continue                      # MariaDB x/0 is NULL: the row is dropped
    for outpp,mbr in fc2.get((fuel,my),()):
        for ff,q in per.items():
            acc=so2[(d,my,fuel)]
            acc[ff]=acc.get(ff,0.0)+mbr*ws*q/ec
# ---- CO2AERunningStartExtendedIdleCalculator: CO2 (90) then CO2e (98) ------
# co2ae_running_start_extended_idle.rs.  Step 1a is energy x carbon x oxidation
# x 44/12; step 2 reads step 1a's rows BACK and sums them with methane and N2O,
# each weighted by its Pollutant.globalWarmingPotential.
CARBON_TO_CO2 = 44.0/12.0
cox={}
for f,forms in supply.items():
    cox[f]=(sum(share*num(FST[FFORM[ff]]["carbonContent"]) for ff,share in forms),
            sum(share*num(FST[FFORM[ff]]["oxidationFraction"]) for ff,share in forms))
CO2_POL, CO2E_POL = 90, 98
co2=collections.defaultdict(dict)
for (d,my,fuel),per in energy.items():
    cc,ox=cox.get(fuel,(0.0,0.0))
    for ff,q in per.items(): co2[(d,my,fuel)][ff]=q*cc*ox*CARBON_TO_CO2
GWP={r["pollutantID"]:r["globalWarmingPotential"] for r in T("pollutant")
     if r["globalWarmingPotential"] is not None and float(r["globalWarmingPotential"])>0.0}
co2e=collections.defaultdict(dict)
for pol,blk in ((CO2_POL,co2),(5,ch4),(6,n2o)):
    g=float(GWP[pol])
    for (d,my,fuel),per in blk.items():
        for ff,q in per.items():
            acc=co2e[(d,my,fuel)]; acc[ff]=acc.get(ff,0.0)+q*g
# ---- TOGSpeciationCalculator: NonHAPTOG (88) ------------------------------
# togspeciation.rs::calculate.  NonHAPTOG = NMOG - sum(integrated species),
# clamped at zero, per (mechanism, integratedSpeciesSet) and output cell.  The
# run selects mechanism 5 / set 4, whose 14 members are the toxics above.
ISS=collections.defaultdict(set)
for r in T("integratedspeciesset"): ISS[(r["mechanismID"],r["integratedSpeciesSetID"])].add(r["pollutantID"])
NONHAPTOG_POL=88
nonhaptog=collections.defaultdict(dict)
for (mech,setid),members in ISS.items():
    for (d,my,fuel),per in nmog.items():
        # greatest(sum(...), 0): the clamp is on the GROUPED sum, so it is taken
        # after the market-share collapse and not per fuel formulation.
        s=sum(per.values())
        for pol in members: s-=sum(toxic.get((pol,1,d,my,fuel),{}).values())
        nonhaptog[(d,my,fuel)][(mech,setid)]=max(s,0.0)
# ---- the emitted rows ------------------------------------------------------
# S18: sum the per-formulation slice, label the row with its SCC, and divide an
# ENERGY pollutant by the kilojoules-per-Million-BTU divisor.  The three new
# calculators all consume the energy block in KILOJOULES, before that divisor.
KJ_PER_MMBTU = 1055.0559*1e6/1000.0
rows={}
def emit(pol,per_cohort,divisor=1.0):
    for (d,my,fuel),per in per_cohort.items():
        if not per: continue
        rows[(pol,1,d,my,fuel)]=(sum(per.values())/divisor,scc(fuel,1))
emit(THC,thc); emit(5,ch4); emit(6,n2o); emit(79,nmhc); emit(80,nmog)
emit(86,tog); emit(87,voc); emit(SO2_POL,so2); emit(CO2_POL,co2)
emit(CO2E_POL,co2e); emit(NONHAPTOG_POL,nonhaptog); emit(91,energy,KJ_PER_MMBTU)
for (outpol,outproc,d,my,fuel),per in toxic.items():
    if not per: continue
    rows[(outpol,outproc,d,my,fuel)]=(sum(per.values()),scc(fuel,outproc))
# ------------------------------------------------------------------- compare
ref_sho = {(r["hourDayID"], r["ageID"]): float(r["SHO"]) for r in T("sho")}
worst_sho = max(abs(sho[k] - v) / v for k, v in ref_sho.items())
print("sho:            %3d rows, worst relative error %.3e" % (len(ref_sho), worst_sho))
assert worst_sho < 1e-5, "sho: worst relative error %.3e exceeds 1e-5" % worst_sho

# The two rate tables produce two different reference tables, and both are checked.
ref_ba = {(r["hourDayID"], r["modelYearID"], r["fuelTypeID"]): float(r["meanBaseRate"])
          for r in T("baseratebyage_1_2020")}
thc_br, thc_brac = BASE_RATE[THCPP]
worst_ba, n_ba = 0.0, 0
for k, v in ref_ba.items():
    if v == 0.0:
        assert thc_br[k] + thc_brac[k] == 0.0, k
        continue
    n_ba += 1
    worst_ba = max(worst_ba, abs(thc_br[k] - v) / v)
print("baseRateByAge:  %3d non-zero rows of %d, worst relative error %.3e"
      % (n_ba, len(ref_ba), worst_ba))
assert worst_ba < 2e-5, "baseRateByAge: worst relative error %.3e exceeds 2e-5" % worst_ba

ref_fl = collections.defaultdict(dict)
for r in T("baserate_1_2020"):
    ref_fl[r["polProcessID"]][(r["hourDayID"], r["modelYearID"], r["fuelTypeID"])] = \
        float(r["meanBaseRate"])
worst_fl, n_fl, tot_fl = 0.0, 0, 0
for pp, ref_rows in sorted(ref_fl.items()):
    br, brac = BASE_RATE[pp]
    for k, v in ref_rows.items():
        tot_fl += 1
        if v == 0.0:
            assert br[k] + brac[k] == 0.0, (pp, k)
            continue
        n_fl += 1
        worst_fl = max(worst_fl, abs(br[k] - v) / v)
print("baseRate:       %3d non-zero rows of %d over polProcessIDs %s, worst relative error %.3e"
      % (n_fl, tot_fl, sorted(ref_fl), worst_fl))
assert sorted(ref_fl) == [N2O_PP, ENERGY_PP], sorted(ref_fl)
assert worst_fl < 2e-5, "baseRate: worst relative error %.3e exceeds 2e-5" % worst_fl

out = pq.read_table(SNAP + "/tables/db__out_chain_so2_co2e_mechanism__movesoutput.parquet").to_pylist()
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
# ASSERTED, not merely printed (docs/esm-conventions.md 21).
assert not missing, missing[:8]
assert not extra, extra[:8]
assert len(rows) == len(out) == 2767, (len(rows), len(out))
assert worst < 2e-5, "emissionQuant: worst relative error %.3e exceeds 2e-5" % worst

# --- the KEY SET, exactly, and not merely its size -------------------------
# 5,534 rows is consistent with many block splits, so the cohort set is asserted
# PER pollutant-process, the day-type axis separately, and their product against
# the row count.
cohorts_by_pp = collections.defaultdict(set)
days = set()
for (pol, proc, day, my, fuel) in rows:
    cohorts_by_pp[(pol, proc)].add((my, fuel))
    days.add(day)
expected_cohorts = {(1, 1): 124, (5, 1): 104, (6, 1): 124, (21, 1): 64,
                    (31, 1): 104, (90, 1): 125, (91, 1): 125, (98, 1): 125}
for pol in (20, 24, 25, 26, 27, 40, 41, 42, 43, 44, 45, 46, 79, 80, 86, 87, 88, 185):
    expected_cohorts[(pol, 1)] = 104
got = {k: len(v) for k, v in cohorts_by_pp.items()}
assert got == expected_cohorts, (got, expected_cohorts)
# The run selects ONE day type. `<day id="5">` is a literal dayID and is honoured;
# the earlier `<day key="5">` was an out-of-range 0-based INDEX into the sorted
# DayOfAnyWeek list [2, 5], selected nothing and fell back to BOTH (moves.rs PR #55).
assert days == set(DAYS) == {5}, days
assert sum(expected_cohorts.values()) * len(days) == len(out) == 2767
print("key set:       124 THC + 124 N2O + 3 x 125 energy/CO2/CO2e + 64 ethanol + 18 x 104")
print("               = 2,767 cohorts x %d day type%s = %d rows, exact."
      % (len(days), "" if len(days) == 1 else "s", len(out)))
# The 125-blocks are a strict superset of the 124-block, which is a strict
# superset of the 104s, and the one cohort between 125 and 124 is the model
# year 2000 electricity one `emissionratebyage` has no age-group row for.
e125, e124, e104 = (cohorts_by_pp[(91, 1)], cohorts_by_pp[(1, 1)], cohorts_by_pp[(80, 1)])
assert e104 < e124 < e125, "the three block sizes are not nested"
assert (e125 - e124) == {(2000, ELECTRICITY)}, sorted(e125 - e124)
assert (e124 - e104) == {c for c in e124 if c[1] == ELECTRICITY}, "the 20 dropped are not the electricity ones"
print("               nested: the one cohort energy has and THC has not is MY2000 electricity,")
print("               and the twenty THC has and every species has not are the electricity ones.")

# --- what a comparison against MOVESOutput alone could not see -------------
# 1. THE 44/12 MASS RATIO IS MEASURED, not assumed. MOVES writes the SQL literal
#    `(44/12)`; MariaDB rounds exact-operand division to DECIMAL, giving 3.6667.
#    Both are run against the 500 CO2 and CO2 Equivalent cells here.
def co2_worst(ratio):
    w = 0.0
    for o in out:
        if o["pollutantID"] not in (CO2_POL, CO2E_POL):
            continue
        d, my, fuel = o["dayID"], o["modelYearID"], o["fuelTypeID"]
        cc, ox = cox.get(fuel, (0.0, 0.0))
        q = sum(v * cc * ox * ratio for v in energy[(d, my, fuel)].values())
        if o["pollutantID"] == CO2E_POL:
            q = q * float(GWP[CO2_POL]) \
                + sum(ch4[(d, my, fuel)].values()) * float(GWP[5]) \
                + sum(n2o[(d, my, fuel)].values()) * float(GWP[6])
        e = float(o["emissionQuant"])
        if e:
            w = max(w, abs(q - e) / e)
    return w
w_exact, w_decimal = co2_worst(44.0 / 12.0), co2_worst(3.6667)
print("NOTE:          the 44/12 mass ratio -- exact %.3e, MariaDB decimal 3.6667 %.3e over"
      % (w_exact, w_decimal))
print("               the 500 CO2 and CO2 Equivalent cells. The exact ratio sits on the same")
print("               noise floor as every other pollutant; the decimal one is a systematic")
print("               %.2e above it, and WOULD STILL HAVE PASSED the 2e-5 gate."
      % ((3.6667 - 44.0 / 12.0) / (44.0 / 12.0)))
assert w_exact < w_decimal / 2.0, (w_exact, w_decimal)
assert w_decimal < 2e-5, w_decimal

# 2. THE NonHAPTOG CLAMP IS A NO-OP HERE, and a passing comparison cannot say so.
negatives, min_residual, shares = 0, None, []
for (mech, setid), members in ISS.items():
    for k, per in nmog.items():
        total = sum(per.values())
        s = total
        for pol in members:
            s -= sum(toxic.get((pol, 1) + k, {}).values())
        negatives += (s < 0.0)
        min_residual = s if min_residual is None else min(min_residual, s)
        if total > 0.0:
            shares.append((total - s) / total)
assert negatives == 0, negatives
print("NOTE:          `greatest(sum(...), 0)` never fires: 0 of %d cells are negative, the"
      % len(nonhaptog))
print("               smallest residual is %.3e g and the fourteen species take %.1f%% to %.1f%%"
      % (min_residual, 100 * min(shares), 100 * max(shares)))
print("               of NMOG. The clamp is written because the source writes it and is"
      " untested here.")

# 3. THE MECHANISM IS THE DISCRIMINATOR, and the calculator's class-loading is not.
mechs = {(r["mechanismID"], r["integratedSpeciesSetID"]) for r in T("integratedspeciesset")}
species = {r["pollutantID"] for r in T("integratedspeciesset")}
assert len(mechs) == 1 and len(species) == 14, (mechs, species)
assert species == {20, 21, 24, 25, 26, 27, 40, 41, 42, 43, 44, 45, 46, 185}, sorted(species)
print("NOTE:          `integratedspeciesset` is 14 rows, all mechanism %d / set %d, and its"
      % mechs.copy().pop())
print("               pollutants are exactly this run's fourteen air toxics. ONE mechanism,"
      " so the")
print("               per-(mechanism, set) fan-out has one member and the multi-mechanism"
      " case is untested.")

# 4. ELECTRICITY FAILS SO2 TWICE, and either failure alone gives the same block.
assert 9 not in {r["fuelTypeID"] for r in T("sulfateemissionrate")}
assert fc1[ELECTRICITY][0] == 0.0, fc1[ELECTRICITY]
assert cox[ELECTRICITY] == (0.0, 0.0), cox[ELECTRICITY]
print("NOTE:          electricity is dropped from SO2 for TWO independent reasons -- no"
      " fuelTypeID 9")
print("               sulfate rate AND a NULL energyContent -- so this snapshot cannot say"
      " which MOVES")
print("               used. Its CO2 factors are REAL zeros, so the 42 CO2 and CO2 Equivalent"
      " rows are")
print("               emitted at exactly 0 rather than dropped, which is why those blocks"
      " are 125.")

# 5. THE CONTROL SNAPSHOT, if it is beside this one. Five `<pollutantprocess-
#    association>` lines apart, and the difference is exactly the four
#    pollutant-processes the three calculators own.
import os
control = os.path.join(os.path.dirname(SNAP.rstrip("/")), "chain-so2-co2e-mechanism-control")
cpath = control + "/tables/db__out_chain_so2_co2e_mechanism_control__movesoutput.parquet"
if os.path.exists(cpath):
    from decimal import Decimal
    def totals(path):
        acc, cnt = collections.defaultdict(Decimal), collections.Counter()
        for b in pq.ParquetFile(path).iter_batches(
                batch_size=65536, columns=["pollutantID", "processID", "emissionQuant"]):
            dd = b.to_pydict()
            for p, pr, v in zip(dd["pollutantID"], dd["processID"], dd["emissionQuant"]):
                acc[(p, pr)] += Decimal(v); cnt[(p, pr)] += 1
        return acc, cnt
    ta, ca = totals(SNAP + "/tables/db__out_chain_so2_co2e_mechanism__movesoutput.parquet")
    tb, cb = totals(cpath)
    owned = sorted(set(ta) - set(tb))
    assert owned == [(31, 1), (88, 1), (90, 1), (98, 1)], owned
    assert not set(tb) - set(ta)
    moved = [k for k in set(ta) & set(tb) if ta[k] != tb[k]]
    assert not moved, moved[:4]
    print("NOTE:          the control snapshot emits %d rows over %d pairs against this one's"
          " %d over %d;" % (sum(cb.values()), len(cb), sum(ca.values()), len(ca)))
    print("               the four it is missing are exactly (31,1) (88,1) (90,1) (98,1) --"
          " the three")
    print("               calculators' whole output -- and all %d shared pairs' totals are"
          " bit-identical" % len(set(ta) & set(tb)))
    print("               in the reference's own decimal text. The chain below them does not"
          " move.")
else:
    print("NOTE:          no control snapshot beside this one; the attribution check is"
          " skipped.")
```

### 6.6 What the oracle proves that the fixture does not

The fixture and the oracle are two implementations of the same specification —
one an `.esm` document evaluated by EarthSciAST, the other float64 Python
straight from the Parquet — so when they disagree with the snapshot, a third
opinion says whether the document or the specification is wrong. Four of the
oracle's assertions have no fixture counterpart at all:

* the **44/12 measurement**, which runs both candidates and asserts the exact
  ratio is at least twice as good;
* the **clamp census**, which asserts 0 of 208 cells are negative;
* the **control snapshot** comparison, which asserts the four pollutant-processes
  the three calculators own and that every shared pair's total is bit-identical;
* the **two independent reasons** electricity is dropped from SO2.

---

## 7. What this document measures, and what it cannot

### 7.1 The 44/12 mass ratio, settled by measurement

MOVES writes the SQL literal `(44/12)`. MariaDB evaluates `/` between exact
operands as DECIMAL rounded to `div_precision_increment` extra places, giving
**3.6667** — 9.0909e-06 above the exact ratio. `moves.rs`'s port left the
question open, chose the exact ratio, and called the difference "far inside any
generator tolerance budget".

Both candidates were run against this snapshot's 500 Atmospheric CO2 and CO2
Equivalent cells:

| slope | worst relative error, CO2 | worst relative error, CO2e |
|---|---|---|
| exact `44.0/12.0` | **5.743e-06** | **5.408e-06** |
| MariaDB decimal `3.6667` | 1.483e-05 | 1.436e-05 |

The exact ratio sits on the same 5e-06 – 8e-06 float32 noise floor as every
other pollutant in the fixture; the decimal one sits a systematic 9.1e-06 above
it. So **MOVES did not round the literal**, and the exact ratio is the port.

The part worth keeping is the near miss: the decimal candidate would still have
**passed** `tolerance.toml`'s per-cell 2e-5 gate, at 0.74 of it. A tolerance
that a wrong answer passes is not evidence, which is why the two were measured
against each other rather than each against the gate
(`docs/esm-conventions.md` §35.3).

### 7.2 The float32 storage of `MOVESWorkerOutput`, and where it shows

`MOVESWorkerOutput.emissionQuant` is a `FLOAT` column, so every intermediate the
three new calculators consume was rounded to binary32 before MOVES read it back,
while this document carries the un-rounded value through. The measured effect is
the 5e-06 – 8e-06 floor every pollutant in this fixture sits on, and §6.2 is
where it is visible as a number: the hand calculation from the STORED energy
lands 2.9e-05 from the reference CO2, and the document lands 5.7e-06, because it
never rounds.

None of this fixture's inputs is storage-limited. Unlike
`nr-airtoxics-lawn-garden-county` (§36.1, §36.2), no cell here is produced by a
chain that multiplies a real inventory by a ratio of 1e-06 or smaller: the
smallest emitted non-zero value is of order 1e-04 g and `float_decimals: 12`
keeps eight significant digits of it. `tolerance.toml` needs no scope record and
no shortfall for this fixture.

### 7.3 Ethanol is where both `ATRatio` paths are live

Pollutant 21 is the only output **both** `ATRatioGas1` and `ATRatioNonGas`
produce: gasoline through the first (formulations 9114 and 27002) and E85
through the second (subtypes 51 and 52). No single cohort reaches both, so the
Go's append-both semantics is still a sum of one term per cell — but the two
paths between them cover no diesel at all, which is why 21's block is 64
cohorts rather than 104. Measured: the ATRatioGas1 arm contributes 64.756 g of
the 64.762 g total and ATRatioNonGas the remaining 0.006 g.

### 7.4 Electricity is dropped from SO2 for two reasons and this fixture cannot separate them

`sulfateemissionrate` has no fuelTypeID 9 row **and** fuel subtype 90's
`energyContent` is NULL. Either alone would produce the same 104-cohort block,
so the snapshot cannot say which one MOVES's `INNER JOIN` chain reached first.
The document asserts **both** — `rt_hasSulfateRate` is 0 and
`rt_supplyEnergyContent` is 0 — so a future snapshot that fixed one would fail
loudly rather than pass on the other.

### 7.5 The `greatest(sum(...), 0)` clamp is a no-op here, and that is asserted

`TOGSpeciationCalculator`'s clamp is its whole protection against a speciation
that over-subtracts. On **all 208 emitted cells** of this run the residual is
positive: the fourteen species take between **16.1 % and 48.6 %** of NMOG and
the smallest residual is **4.567e-04 g**.

So §23's rule applies: **the check belongs in a component, at probe values
chosen so the clamp is discriminating, and the fixture says out loud that it
does not contain one.** It does — `rtDay_nonHapTogRaw` and
`rtDay_nonHapTogQuant` are asserted EQUAL at the smallest residual in the run,
which is the honest statement that the clamp is not exercised, and the oracle
recounts the census every run so a snapshot that started clamping would be
noticed.

### 7.6 One mechanism, so the fan-out is untested

`togspeciation.rs`'s step 2 fans each emitted species out to **every**
`(mechanismID, integratedSpeciesSetID)` that lists it. This run has one such
pair, so the fan-out has one member and a join that dropped the mechanism key
entirely would give the same answer. `run_integratedSpeciesMechanismSpread` is
asserted 0, which turns the limitation into a number rather than a sentence.

### 7.7 The temperature quadratic reads the temperature, not the heat index

`adjust.rs:108` uses `temperature` in the EV quadratic and `heat_index` only in
the suppression test. This document follows that.
`fixtures/mixed-onroad.esm`'s `coh_evTemperatureAdjustRaw` uses `heat_index` in
**both**. The two agree at every hour in the corpus, because the heat index below
78 °F IS the temperature (`docs/esm-conventions.md` §37.2), so no fixture can
falsify either spelling — this one included. It is recorded here rather than
changed, because changing a merged document on an unfalsifiable difference is
how a port acquires churn it cannot justify.

---

## 8. Results

| | |
|---|---|
| rows compared | **5,534 of 5,534** |
| pollutant-processes | **26 of 26** |
| missing keys | **0** |
| extra keys | **0** |
| worst relative cell error | **8.331e-06** at (43, 1, day 2, MY 1991, diesel) |
| gate | `tolerance.toml` `[cell] rel = 2e-5`, **unmodified** |
| `[shortfall]` record | **none** |
| `[scope]` record | **none** |
| inline assertions | **333**, all passing |
| `esm simulate` | 6.4 s |
| `esm test` | 6.7 s |

Per pollutant, worst relative error:

| pollutant | rows | worst | pollutant | rows | worst |
|---|---:|---|---|---:|---|
| 1 THC | 248 | 7.956e-06 | 44 styrene | 208 | 7.594e-06 |
| 5 CH4 | 208 | 7.428e-06 | 45 toluene | 208 | 6.584e-06 |
| 6 N2O | 248 | 8.201e-06 | 46 xylene | 208 | 7.934e-06 |
| 20 benzene | 208 | 8.100e-06 | 79 NMHC | 208 | 7.956e-06 |
| 21 ethanol | 128 | 6.316e-06 | 80 NMOG | 208 | 7.148e-06 |
| 24 butadiene | 208 | 7.558e-06 | 86 TOG | 208 | 7.148e-06 |
| 25 formaldehyde | 208 | 7.822e-06 | 87 VOC | 208 | 7.148e-06 |
| 26 acetaldehyde | 208 | 7.198e-06 | **88 NonHAPTOG** | 208 | **7.394e-06** |
| 27 acrolein | 208 | 8.207e-06 | **90 CO2** | 250 | **5.743e-06** |
| **31 SO2** | 208 | **6.974e-06** | 91 energy | 250 | 7.106e-06 |
| 40 trimethylpentane | 208 | 7.613e-06 | **98 CO2e** | 250 | **5.408e-06** |
| 41 ethylbenzene | 208 | 8.124e-06 | 185 naphthalene | 208 | 7.414e-06 |
| 42 hexane | 208 | 7.513e-06 | | | |
| 43 propionaldehyde | 208 | 8.331e-06 | | | |

The four blocks in bold are the ones the three new calculators own. They sit on
the same noise floor as the twenty-two the retarget already reproduced, which is
what says the new arithmetic is right rather than merely tolerable.
