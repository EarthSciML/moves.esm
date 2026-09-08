# `nr-airtoxics-lawn-garden-county` — computation specification

The port specification for the **last two unported NONROAD calculators**,
`NRHCSpeciationCalculator` and `NRAirToxicsCalculator`. They chain, so one
snapshot reaches both: `NonroadEmissionCalculator` emits THC, PM10 and fuel
consumption; HC speciation splits THC into five species; air toxics scales VOC,
PM2.5 and fuel consumption into twenty more; and a second pass forms NonHAPTOG
out of NMOG minus the integrated species.

Neither calculator subscribes to the master loop
(`calculator-dag.json`: `subscribes_directly: false` on both). What makes them
run is the **pollutant set**, and because
`ExecutionRunSpec.flagRequiredPollutantProcesses()` returns early for NONROAD,
every link in the chain has to be named explicitly in the RunSpec — which is
why the fixture XML lists all 29 associations rather than the four a user would
type.

The geography, vehicle and time selections are byte-identical to
`nr-lawn-garden-county`, so the pair is a controlled A/B on the pollutant set
alone. Measured: pollutant 1 (THC) and pollutant 100 (PM10) agree between the
two snapshots' `MOVESOutput` **to the last digit on all 484 cohorts**
(0.0 relative difference, both pollutants), so everything below the speciation
line is the `nr-lawn-garden-county` run unchanged.

---

## 0. The fixture at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/nr-airtoxics-lawn-garden-county.xml` |
| Calculator path | **`NonroadEmissionCalculator`** → **`NRHCSpeciationCalculator`** → **`NRAirToxicsCalculator`** → output aggregation |
| Model | NONROAD, `modelscale` `Inv` (inventory), `modeldomain` `DEFAULT` |
| Geography | county 26161 (Washtenaw, Michigan) |
| Time | year 2020, month **8**, day type **5 (weekday)**, hour **0** in the output |
| Equipment | sector 4 (Lawn/Garden), fuel type 1 (gasoline) — **31 SCCs**, **108 `nrsourceusetype` equipment points** |
| Road | roadTypeID 100 (Nonroad) |
| Pollutant/process | **29 pairs, all process 1**: 101, 501, 2001, 2101, 2301, 2401, 2501, 2601, 2701, 4501, 4601, 6001, 6301, 6501, 6601, 6701, 6901, 7901, 8001, 8601, 8701, 8801, 9901, 10001, 11001, 13101, 14201, 16901, 18501 |
| Model years | 1971–2020 (50), ragged per SCC — 3 to 50 each |
| Output | `db__out_nr_airtoxics_lawn_garden_county__movesoutput`, **14,036 rows** = 29 × **484** `(SCC, modelYearID)` cohorts |
| Fixture | `fixtures/nr-airtoxics-lawn-garden-county.esm` — 14,036 rows emitted, **13,068 compared**, key set exact, worst compared cell **9.417 × 10⁻⁶** against an unchanged `[cell] rel = 2e-5` (§7.2, §8) |
| Output units | grams; `outputtimestep` **Hour** |

### 0.1 Why 484 cohorts, and why every block is the same size

The 484 cohorts are the `(SCC, modelYearID)` pairs `prccty.f` emits for the 108
equipment points, after the `modfrc <= 0` skip and the `idx < nyrlif` loop
bound (`docs/nonroad-logging-county.md` §7.3). Their model-year counts are
ragged — 3, 5, 6, 7, 9, 10, 12, 15, 16, 23, 43 and 50 — and unlike every
onroad rung since `process-crankcase-running` (`docs/esm-conventions.md` §31)
**all 29 pollutant blocks carry the identical 484**, because every downstream
pollutant is a fixed multiple of a block that exists for every cohort. Verified
directly: `groupby(pollutantID, processID).size()` is 484 on all 29 pairs, and
`groupby(SCC, modelYearID).ngroups` is 484.

That is a fact about this snapshot's data, not a licence to lay the output out
as `484 × 29`: `nrMethaneTHCRatio` returning no row makes the Go `continue`
past an emission and would drop five species for that cohort (§2.4). The
global rank of §31 is still the right shape.

### 0.2 The chain, read from `runspecnonroadchainedto`

The snapshot's own `runspecnonroadchainedto`, restricted to the 29 selected
pairs, is 28 edges. Read as a graph it is **not** the evaluation order — the
same caution `docs/esm-conventions.md` §33.1 records for the onroad chain
table. Two rows say so here:

* `10001 ← 11001` — PM10 chained *from* PM2.5. In NONROAD it is the other way
  round: `nremissionrate` carries polProcessID 10001 and no 11001, and
  `NonroadOutputDataLoader.java:454-481` writes pollutant 110 as
  `record.pmExhaust * 0.92`. Measured, `110/100` is 0.92 on all 484 cohorts to
  within the capture's storage noise (mean 0.920000, sd 2 × 10⁻⁶ over the 242
  cohorts above 1 g).
* `8601 ← 501` **and** `8601 ← 8001` — a two-input edge, which is right
  (TOG = methane + NMOG) but which a single-parent iteration cannot express.

So the document writes the **calculators' stages**, and reads the chain table
only for what it says unambiguously.

---

## 1. Input inventory

### 1.1 The base chain

Every table `docs/nonroad-logging-county.md` §1.2 lists is read here for the
same reason and with the same meaning, against this snapshot's own copies
(`db__movesexecution1ccc0236_…`). Three of them behave differently at this
sector's scale and are re-specified in §2.1.

### 1.2 The nine tables this rung adds

| table | rows (this snapshot) | key | what it carries |
|---|---:|---|---|
| `nrhpcategory` | 2,268 | `(nrhprangebinid, engtechid)` | the `'L'`/`'S'` horse-power category that every speciation lookup keys on |
| `nrmethanethcratio` | 948 | `(processID, engTechID, fuelSubtypeID, nrHPCategory)` | `CH4THCRatio` |
| `nrhcspeciation` | 1,896 | `(pollutantID ∈ {80, 87}, processID, engTechID, fuelSubtypeID, nrHPCategory)` | `speciationConstant` |
| `nratratio` | 7,584 | `(processID, engTechID, fuelSubtypeID, nrHPCategory)` | `atRatio` for pollutants 20, 21, 24, 25, 26, 27, 45, 46 |
| `nrpahgasratio` | 316 | `(processid, fuelTypeID, engTechID, nrHPCategory)` | `atratio` for 169, 185 |
| `nrpahparticleratio` | 316 | `(processid, fuelTypeID, engTechID, nrHPCategory)` | `atratio` for 23, 69 |
| `nrdioxinemissionrate` | 316 | `(processID, fuelTypeID, engtechID, nrHPCategory)` | `meanBaseRate`, `units` `g/gal`, for 131, 142 |
| `nrmetalemissionrate` | 790 | `(processID, fuelTypeID, engTechID, nrHPCategory)` | `meanBaseRate`, `units` `g/gal`, for 60, 63, 65, 66, 67 |
| `nrintegratedspecies` | 9 | `pollutantID` | 20, 21, 24, 25, 26, 27, 45, 46, 185 — the species subtracted from NMOG |

Note the column-name casing genuinely differs table to table
(`processid`/`processID`, `engtechID`/`engTechID`, `atratio`/`atRatio`); the
Rust port normalises it in `ProcFuelEngHpRow::polars_schema` and a document
must read the name the file actually has.

### 1.3 What is NOT an input

`atRatio`, `atRatioGas2`, `atRatioNonGas`, `dioxinEmissionRate`,
`metalEmissionRate`, `pahGasRatio`, `pahParticleRatio` — the **un-prefixed**
tables — belong to the *onroad* `AirToxicsCalculator` and are read by nothing
here. `nrrocspeciation`, `integratedspeciesset` and `integratedspeciessetname`
are **empty** in this snapshot. `minorhapratio` has 84 rows, all for
polProcessID 4501 and 4601, and is an onroad table: neither NONROAD calculator
reads it.

---

## 2. The computation chain

### 2.1 Three things the logging-county base chain gets wrong at this scale

`docs/nonroad-logging-county.md` §6.5's reproduction, pointed at this snapshot
with nothing changed but the paths, emits **exactly the right 1,936-row key
set** for the four `nr-lawn-garden-county` pollutants and reproduces **22** of
the 31 SCCs to 1 × 10⁻⁵ — and is wrong on **five**, by up to a factor of
**6.9**. (The remaining four
— the 2260/2265 snowblowers, SCCs `2260004035`, `2260004036`,
`2265004035` and `2265004036` — are exactly zero on both sides, because
`nrmonthallocation` carries `monthFraction` 0.000000000000 for month 8 on all
53 states for those SCCs; they are right, and trivially so.) That measurement is what this section is: the logging fixture's
three SCCs could not tell these rules apart.

**(a) The `.EMF` SCC fallback is walked PER ENGINE TECHNOLOGY, not per SCC.**
`nonroad_loader.rs:436-451` looks up each tech's rate with
`chain.iter().find_map(|s| rates.get(&((*s).clone(), tid))…)`, where `chain` is
`[SCC, xxxxxxx000, xxxx000000]`. A specific SCC's rate rows need not cover
every technology its mix names: `2265004076` has `nremissionrate` rows only for
hp bin 0–6, so its 8-, 15-, 36-, 66-, 86- and 113-hp points take the
`2265000000` root — and within one point, techs present at the specific SCC and
techs present only at the root are both live. Resolving the chain once per SCC
and taking that level's whole tech set is what produced the **0.254 to 0.314**
ratios on `2265004076`'s 2015–2020 THC cohorts.

**(b) The `.TECH` lookup takes ONE hp bin, the first in ascending
`(SCC, hpMin, hpMax)` order that contains `hpAvg`**
(`nonroad_loader.rs:415-422`). The bins are half-open in intent and closed in
code (`lo <= hp && hp <= hi`), so an `hpAvg` on a boundary — `2260004071`'s
3.0 hp sits in both `(1, 3)` and `(3, 6)` of `2260000000` — matches two, and
only the first counts. Collecting every matching bin over-counts that SCC's five
emitted model years by **1.242 to 1.433**.

**(c) The tech list is truncated to `MXTECH = 32`** (`common/consts.rs:51`,
applied at `nonroad_loader.rs:424`). `2260000000` names 34 exhaust
technologies.

### 2.2 Fuel consumption (pollutant 99) is grams, and the densities cancel

`nremissionrate` carries polProcessID 9901 with an **empty** `units` column and
a rate in **lb/hp-hr**. The engine converts to gallons by dividing by
`CMFGAS = 6.237` lb/gal (`emissions/exhaust.rs:265`), and
`NonroadOutputDataLoader.java:1052` converts back with
`lbs = gallons * 6.237` then `grams = lbs * 453.592`. The two densities cancel
exactly, so

```
emissionQuant(99) = bsfc[lb/hp-hr] x hpAvg x loadFactor x … x 453.592
```

Measured: the ratio of the snapshot's pollutant-99 rows to the chain's
`lb`-valued product is **453.5909 to 453.5951 over all 484 cohorts**, which is
453.592 inside the capture's storage noise. `nrdeterioration` carries no 9901
row, so BSFC takes no deterioration factor and no `emsadj.f` adjustment.

Write the two divisions rather than the cancelled constant: they do not cancel
in the *toxics* path (§2.6), which uses a different density.

### 2.3 PM2.5 (pollutant 110)

`NonroadOutputDataLoader.java:454-481`, a hard-coded per-fuel factor on the
NONROAD engine's single PM tally:

| fuelTypeID | 1 | 2 | 23 | 24 | 3 | 4 |
|---|---|---|---|---|---|---|
| factor | **0.92** | 0.97 | 0.97 | 0.97 | 1 | 1 |

Gasoline only here, so `PM2.5 = PM10 × 0.92`. This is a *loader* constant: it
is in neither `nremissionrate` nor any ratio table, and `../moves.rs` does not
carry it (grepped: no `0.92` anywhere in `crates/`). §8 records that as a gap.

### 2.4 `NRHCSpeciationCalculator`

Ported at `crates/moves-calculators/src/calculators/nrhcspeciation.rs`
(`speciate_emission`, lines 510-606), itself a port of
`calc/nrhcspeciation/nrhcspeciation.go`. For one THC emission of a fuel block
keyed `(pollutantID, processID, engTechID, fuelTypeID, hpID)`:

```
hpCategory = nrHPCategory[(hpID, engTechID)]                    -- 0 when absent
r          = nrMethaneTHCRatio[(processID, engTechID, ff.fuelSubTypeID, hpCategory)]
             -- no row  =>  the emission is SKIPPED ENTIRELY
methane(5) = THC x r
NMHC(79)   = THC x (1 - r)
NMOG(80)   = NMHC x nrHCSpeciation[(80, processID, engTechID, e.fuelSubTypeID, hpCategory)]
             -- no row  =>  an explicit ZERO emission, not an omitted row
VOC(87)    = NMHC x nrHCSpeciation[(87, …)]                     -- same fallback
TOG(86)    = NMOG + methane
```

Three things are load-bearing and none is visible in the arithmetic:

* **The speciation happens inside the engine-technology contraction.** The
  block key carries `engTechID`, and `nrMethaneTHCRatio` for fuel subtype 12 on
  the 40 exhaust technologies this sector uses takes **two** values, 0.02 and
  0.149. The emitted `CH4/THC` ratio per cohort takes **404 distinct values
  over 484 cohorts**, spanning 0.023141 to 0.149001 — a blend, not a lookup.
  A document that speciated the *aggregated* THC would have to pick one.
* **Two different fuel-subtype ids.** `nrMethaneTHCRatio` keys on the *fuel
  formulation's* subtype, `nrHCSpeciation` on the *emission's*. §8 says why
  this snapshot cannot tell them apart.
* **TOG sums the GATED species.** An un-needed summand contributes nothing and
  TOG is omitted when both are absent.

### 2.5 The nonroad fuel-supply fan-out

`calc/mwo/mworeader.go` `parseLines` turns one nonroad worker row into **one
emission per `nrFuelSupply` entry** for `(county, year, month, fuelType)`, each
carrying that entry's `fuelSubTypeID` and `fuelFormulationID` and each scaled
by its `marketShare`. Region 270000000 in month group 8 supplies gasoline as
formulation **9114** (subtype 12, E10) at market share **1.0** and formulation
**9414** (subtype 10) at market share **0.0**. The zero-share entry is still
an emission and still runs the whole chain; it contributes nothing.

### 2.6 `NRAirToxicsCalculator`

Ported at `crates/moves-calculators/src/calculators/nrairtoxics.rs`
(`air_toxics_for_emission`, lines 611-682). Three input pollutants, five ratio
tables, one form:

```
VOC  (87)  x nrATRatio[(processID, engTechID, ff.fuelSubTypeID, hpCategory)]      -> 20,21,24,25,26,27,45,46
VOC  (87)  x nrPAHGasRatio[(processID, fuelTypeID, engTechID, hpCategory)]        -> 169,185
PM2.5(110) x nrPAHParticleRatio[(processID, fuelTypeID, engTechID, hpCategory)]   -> 23,69
fuel (99)  x (meanBaseRate x gallonsFactor)   nrDioxinEmissionRate                -> 131,142
fuel (99)  x (meanBaseRate x gallonsFactor)   nrMetalEmissionRate                 -> 60,63,65,66,67
```

with, verbatim from the Go and reproduced in that operation order,

```
gallonsFactor = (1.0 / 453.592) / density        -- TWO sequential divisions
density(gasoline) = 6.17                          -- NOT the engine's 6.237
```

The fuel path runs for **process 1 only**. An unknown fuel formulation skips
the whole emission before any branch, including the two branches that never
read a fuel subtype. Where two tables would produce the same output pollutant
the later one wins (`produced.insert`); in this data the five sets are
disjoint, so that is written and untested.

### 2.7 The NonHAPTOG pass

A second, independent pass (`non_hap_tog_block`, lines 791-830). Each input
block contributes a **partial** row for pollutant 88:

```
NMOG (80) block                     ->  +emission
nrIntegratedSpecies block            ->  -emission
```

and the total is formed by the output aggregation, not inside the calculator.
Measured against the snapshot two ways, both to storage precision:
`NMOG − Σ(20,21,24,25,26,27,45,46,185)` agrees to **8.393 × 10⁻⁶** and
`TOG − Σ − CH4` to **7.923 × 10⁻⁶**; they are the same expression because
TOG = NMOG + CH4. The Java says which one MOVES writes —
`NRAirToxicsCalculator.getIntegratedSpecies`: *"NMOG (80) is always required.
It is already TOG - Methane so we avoid chaining to TOG and Methane."*

---

## 3. Join structure

Every lookup in §2 is an equi-join on a composite key and is spelled as one
`join.on` clause with a pair list (`docs/esm-conventions.md` §3). The two key
shapes are:

| clause | pairs |
|---|---|
| subtype-keyed (`nrMethaneTHCRatio`, `nrHCSpeciation`, `nrATRatio`) | `processID`, `engTechID`, `fuelSubtypeID`, `nrHPCategory` |
| fuel-type-keyed (`nrPAHGasRatio`, `nrPAHParticleRatio`, `nrDioxinEmissionRate`, `nrMetalEmissionRate`) | `processID`, `fuelTypeID`, `engTechID`, `nrHPCategory` |

`nrHPCategory` is a one-character text column and enters through a `codes` map
on the `from` binding (`esm-spec` §8.9.1), the same route
`year.isBaseYear` takes in `fixtures/nr-logging-county.esm`. A missing
`nrhpcategory` row yields the Go map's zero value, which is carried into the
lookup key verbatim and therefore matches nothing — a *value*, not a branch.

The base chain's joins are `docs/nonroad-logging-county.md` §3's, with J12 and
J13 re-keyed per §2.1(a): the `.EMF` lookup joins
`(effective SCC per technology, engTechID, polProcessID)` with the hp
containment as a `filter`, and the effective SCC is a per-technology
precomputed column rather than a per-point one.

---

## 4. Reusable shapes

The five ratio tables are five sets of **coefficients** over **two forms**
(`docs/esm-conventions.md` §24), and the forms live in
`lib/nonroad_speciation.esm`:

| template | body | used by |
|---|---|---|
| `ratio_scaled(input, ratio)` | `input × ratio` | `nrATRatio`, `nrPAHGasRatio`, `nrPAHParticleRatio`, and both `nrHCSpeciation` species |
| `rate_scaled(input, rate, unit_factor)` | `input × (rate × unit_factor)` | `nrDioxinEmissionRate`, `nrMetalEmissionRate` |
| `grams_to_gallons_factor(density)` | `(1 ÷ 453.592) ÷ density` | the fuel path's `unit_factor` |
| `grams_per_pound()` | `453.592` | both of the above, and §2.2's BSFC conversion |
| `methane_share(r)` / `nmhc_share(r)` | `r` / `1 − r` | HC speciation |
| `total_organic_gases(nmog, methane)` | `nmog + methane` | HC speciation |
| `non_hap_tog(nmog, integrated_sum)` | `nmog − integrated_sum` | the NonHAPTOG pass |

`rate_scaled` is **not** `ratio_scaled` with a pre-multiplied ratio: the Go
computes `atRatio*gallonsFactor` as one product and then scales, so the two
associations differ in the last bits and the template records which one the
reference uses.

---

## 5. Literals and enums

| symbol | value | source |
|---|---|---|
| `pollutant.TotalGaseousHydrocarbons` | 1 | `nrhcspeciation.rs:122` |
| `pollutant.Methane` | 5 | `nrhcspeciation.rs:124` |
| `pollutant.NonMethaneHydrocarbons` | 79 | `nrhcspeciation.rs:126` |
| `pollutant.NonMethaneOrganicGases` | 80 | `nrhcspeciation.rs:128` |
| `pollutant.TotalOrganicGases` | 86 | `nrhcspeciation.rs:130` |
| `pollutant.VolatileOrganicCompounds` | 87 | `nrhcspeciation.rs:132`, `nrairtoxics.rs` |
| `pollutant.NonHAPTOG` | 88 | `nrairtoxics.rs` |
| `pollutant.BrakeSpecificFuelConsumption` | 99 | `nrairtoxics.rs` |
| `pollutant.PrimaryExhaustPM10Total` | 100 | `nremissionrate.polProcessID` 10001 |
| `pollutant.PrimaryExhaustPM25Total` | 110 | `nrairtoxics.rs` |
| `process.RunningExhaust` | 1 | `nrairtoxics.rs` |
| `grams_per_pound` | 453.592 | `nrairtoxics.rs` `GRAMS_PER_POUND` |
| gasoline density, toxics path | 6.17 | `nrairtoxics.rs` `gallons_factor` |
| gasoline density, engine path | 6.237 | `emissions/exhaust.rs`, `CMFGAS` |
| PM2.5 fraction of PM10, gasoline | 0.92 | `NonroadOutputDataLoader.java:458` |
| `MXTECH` | 32 | `common/consts.rs:51` |
| `MXAGYR` | 51 | `common/consts.rs` |

The twenty output pollutant ids of the toxics stage are **not** named in the
document: each one arrives as `nrATRatio.pollutantID`,
`nrPAHGasRatio.pollutantID` and so on, so the join both finds the coefficient
and says which pollutant it is (`docs/esm-conventions.md` §32.4, "name a
pollutant exactly where the source names one"). The seven named above are the
seven the *source* names as constants.

---

## 6. Hand-checkable worked examples

### 6.0 Run-level values

| | |
|---|---|
| daytime mean temperature (hours 6–18, zone 261610, month 8) | 73.57693 °F |
| oxygen weight percent | 3.653 |
| days in month | 31, so `adjtime` = 1/31 |
| supplied gasoline formulation | 9114, fuel subtype 12, market share 1.0 |
| `nrIntegratedSpecies` | {20, 21, 24, 25, 26, 27, 45, 46, 185} |

### 6.1 The species multipliers on one block

SCC 2265004010 (4-stroke residential lawn mowers) at `hpAvg` 2.55 takes
`nrHPRangeBinID` 3, whose `nrHPCategory` is `S` on every technology, and its
`.TECH` bin names nine of them: **136, and 137–144**. For fuel subtype 12 they
carry exactly two coefficient sets:

| | tech 136 | techs 137–144 |
|---|---|---|
| `CH4THCRatio` | 0.02 | 0.149 |
| `speciationConstant` (80) | 1.06 | 1.051 |
| `speciationConstant` (87) | 1.057 | 1.035 |
| methane / THC | 0.02 | 0.149 |
| NMHC / THC | 0.98 | 0.851 |
| NMOG / THC | 1.0388 | 0.894401 |
| VOC / THC | 1.03586 | 0.880785 |
| TOG / THC | 1.0588 | 1.0434 |

Every emitted cohort is a population-weighted blend of the technologies its
model year admits, which is why the snapshot's own `CH4/THC` runs from
0.023141 to 0.149001 over the 484 cohorts (404 distinct values) and its
`TOG/THC` from 1.04339 to 1.05843 — inside the [1.0434, 1.0588] the two
coefficient sets bracket, and matching neither endpoint.

### 6.2 The fuel path on one block

`nrMetalEmissionRate` for gasoline, process 1, is constant over this sector's
technologies and both hp categories:

| pollutant | 60 | 63 | 65 | 66 | 67 |
|---|---|---|---|---|---|
| `meanBaseRate` (g/gal) | 1.8 × 10⁻⁶ | 6.33 × 10⁻⁵ | 2.2 × 10⁻⁷ | 2.72 × 10⁻⁵ | 3.06 × 10⁻⁵ |

so, with `gallonsFactor = (1/453.592)/6.17 = 3.5731352 × 10⁻⁴`,

```
pollutant 66 = fuel[g] x (2.72e-05 x 3.5731352e-04) = fuel x 9.7189278e-09
```

Checked against the snapshot at (66, SCC 2265004071, MY 2020), where
`MOVESOutput` carries fuel consumption 4170270 g and manganese
0.040530500000 g: `4170270 x 9.7189278e-09 = 0.040530553`, **1.30 × 10⁻⁶**
relative. The full chain, which applies the ratio per technology and per
equipment point rather than to the aggregate, lands at 0.040530465 —
8.6 × 10⁻⁷ relative — and that gap between the two hand routes is itself the
capture's six-significant-figure storage of the fuel-consumption row.

### 6.3 The PM2.5 path

At (23, SCC 2260004021, MY 2020) the snapshot carries 0.860500000000 g of
naphthalene particle against a PM2.5 of 13,487.4 g, and the chain computes
0.860498659 — 1.6 × 10⁻⁶ relative.

### 6.4 NonHAPTOG

At (88, SCC 2265004010, MY 1981) the snapshot carries 0.102524000000 g and the
chain computes 0.10252303372 — 9.4 × 10⁻⁶ relative, which is the **worst cell
in the whole 14,036-row comparison** among the cells the capture stores in
full. NonHAPTOG being the worst is the §32/§33 pattern: it is a difference of
ten quantities, each of which carries its own quantisation.

### 6.5 The reproduction script

Run against the snapshot directory; it takes nothing from the reference except
`MOVESOutput` in the final comparison.

```python
#!/usr/bin/env python3
"""Independent reproduction of every nr-airtoxics-lawn-garden-county
MOVESOutput row: the NONROAD exhaust chain, NRHCSpeciationCalculator and
NRAirToxicsCalculator, in float32 straight from the snapshot Parquet.

Run as:  repro.py <snapshot directory>
"""
import math
import sys

import numpy as np
import pyarrow.parquet as pq

f = np.float32
MXAGYR = 51                      # common/consts.rs
MXTECH = 32                      # common/consts.rs
GRMLB = 453.592                  # grams per pound
CVTTON = 1.102311e-06            # grams -> short tons (unitcf.f)
GAS_DENSITY_NONROAD = 6.237      # lb/gal, CMFGAS in the NONROAD engine
GAS_DENSITY_TOXICS = 6.17        # lb/gal, the nrairtoxics.go literal
PM25_OF_PM10 = 0.92              # NonroadOutputDataLoader.java:458, gasoline

SNAP = sys.argv[1]
D = SNAP + "/tables/"
PRE = "db__movesexecution1ccc0236_campuscluster_illinois_edu__"
rd = lambda t: pq.read_table(D + PRE + t + ".parquet").to_pandas()

COUNTY, STATE, YEAR, MONTH, DAYID, NDAYS = 26161, 26, 2020, 8, 5, 31
PP = {"THC": 101, "CO": 201, "NOx": 301, "PM": 10001, "BSFC": 9901}
POLID = {"THC": 1, "CO": 2, "NOx": 3, "PM": 100, "BSFC": 99}

# ---------------------------------------------------------------- growth
gi, gp = rd("nrgrowthindex"), rd("nrgrowthpatternfinder")


def growth_series(pattern):
    g = gi[gi.growthPatternID == pattern].sort_values("yearID")
    return ([int(r.yearID) for r in g.itertuples()],
            [f(int(r.growthIndex)) for r in g.itertuples()])


def indicator(ys, vs, y):
    ib, ie = 0, len(ys) - 1
    if y < ys[ib]:
        s = (vs[ib + 1] - vs[ib]) / f(ys[ib + 1] - ys[ib])
        return max(f(vs[ib] + s * f(y - ys[ib])), f(0))
    if y > ys[ie]:
        s = (vs[ie] - vs[ie - 1]) / f(ys[ie] - ys[ie - 1])
        return max(f(vs[ie] + s * f(y - ys[ie])), f(0))
    if y == ys[ie]:
        return vs[ie]
    for i in range(ib, ie):
        if y == ys[i]:
            return vs[i]
        if y < ys[i + 1]:
            s = (vs[i + 1] - vs[i]) / f(ys[i + 1] - ys[i])
            return f(vs[i] + s * f(y - ys[i]))
    return vs[ie]


def growth_factor(ys, vs, y1, y2):
    if y1 == y2:
        return f(0)
    b, g = indicator(ys, vs, y1), indicator(ys, vs, y2)
    if b == 0 and g == 0:
        return f(0)
    return f((g - b) / (b * f(y2 - y1)))


# ------------------------------------------------------------ scrappage
sc = rd("nrscrappagecurve")
sc = sc[sc.NREquipTypeID == 0]
CURVE = [(f(k / 1e6), f(v)) for k, v in sorted(
    {round(float(r.fractionLifeused) * 1e6): float(r.percentageScrapped)
     for r in sc.itertuples()}.items())]


def find_scrappage_percent(x):
    if x < CURVE[0][0]:
        return CURVE[0][1]
    for i in range(len(CURVE) - 1):
        if CURVE[i + 1][0] > x:
            return CURVE[i][1]
    return CURVE[-1][1]


def scrptime(mdlfhrs, ldfctr, acthpy, pgf):
    mly = min(f(MXAGYR // 2), f(f(mdlfhrs / ldfctr) / acthpy))
    mlpy = f(1.0) / mly
    yy, pct, nyrlif = [f(0)] * MXAGYR, [f(0)] * MXAGYR, 0
    for iage in range(2, MXAGYR + 1):
        cur, prev = iage - 1, iage - 2
        pct[cur] = find_scrappage_percent(f(f(iage - 1) * mlpy))
        yfs = f((pct[cur] - pct[prev]) / f(100))
        if pct[prev] >= 100:
            if nyrlif == 0:
                nyrlif = iage - 1
            yy[cur] = f(0)
        else:
            yy[cur] = f(f(100) * yfs / (f(100) - pct[prev]))
    if pct[MXAGYR - 1] >= 100 and nyrlif == 0:
        nyrlif = MXAGYR
    sg = f(pgf / (f(f(-1.4306) * pgf) * mly + f(-0.24) * pgf + f(1.0)))
    sales = [f(f(1000.0) + f(f(1000.0) * sg * f(i))) for i in range(MXAGYR)]
    surv, tot = [f(0)] * MXAGYR, f(0)
    for iage in range(1, MXAGYR + 1):
        i0 = iage - 1
        if iage <= nyrlif:
            surv[i0] = f(sales[nyrlif - iage] * (f(1.0) - f(pct[i0] / f(100))))
        tot = f(tot + surv[i0])
    return yy, [f(s / tot) for s in surv], nyrlif


def agedist(baspop, modfrc, base_year, growth_year, yy, ys, vs):
    md, totpop = list(modfrc), f(baspop)
    for iyear in range(base_year + 1, growth_year + 1):
        tmp = list(md)
        gf = growth_factor(ys, vs, iyear - 1, iyear)
        if gf != 0:
            totpop = max(totpop, f(0.0001))
        totpop = max(f(totpop * (f(1.0) + gf)), f(0))
        tpf = f(totpop / f(baspop))
        s = f(0)
        for ia in range(1, MXAGYR):
            u = max(f(tmp[ia - 1] * (f(1.0) - yy[ia])), f(0))
            md[ia] = u
            s = f(s + u)
        md[0] = f(tpf - s)
    return md


# ------------------------------------------------------------------ geography
ss = rd("nrstatesurrogate")


def alloc_frac(sur):
    def pick(fips):
        rows = ss[(ss.surrogateID == sur) & (ss.countyID == fips)]
        low = rows[rows.surrogateYearID <= YEAR]
        if len(low):
            return f(float(low.sort_values("surrogateYearID").iloc[-1].surrogatequant))
        hi = rows[rows.surrogateYearID > YEAR]
        if len(hi):
            return f(float(hi.sort_values("surrogateYearID").iloc[0].surrogatequant))
        return None

    qs, qc = pick(STATE * 1000), pick(COUNTY)
    return f(qc / qs) if (qs is not None and qs > 0 and qc is not None) else f(0)


# ------------------------------------------------------------------- temporal
ma, da = rd("nrmonthallocation"), rd("nrdayallocation")


def scc_ladder(s):
    return [s] + [s[:10 - k] + "0" * k for k in (2, 4, 6)]


def equip_chain(s):
    return [s, s[:7] + "000", s[:4] + "000000"]


def month_fraction(scc):
    for k in scc_ladder(scc):
        for st in (STATE, 0):
            r = ma[(ma.SCC == k) & (ma.stateID == st) & (ma.monthID == MONTH)]
            if len(r):
                return f(float(r.iloc[0].monthFraction))
    return f(1.0 / 12.0)


def day_fraction(scc):
    for k in scc_ladder(scc):
        r = da[(da.scc == k) & (da.dayID == DAYID)]
        if len(r):
            return f(float(r.iloc[0].dayFraction))
    return f(1.0 / 7.0)


# ---------------------------------------------------------------- temperature
z, zmh = rd("zone"), rd("zonemonthhour")
zids = set(z[z.countyID == COUNTY].zoneID)
_t = zmh[(zmh.zoneID.isin(zids)) & (zmh.monthID == MONTH)
         & (zmh.hourID >= 6) & (zmh.hourID <= 18)].temperature.astype(float)
TAMB = f(_t.mean())

# ------------------------------------------------------------------ fuel props
yr = rd("year")
fuel_year = int(yr[yr.yearID == YEAR].fuelYearID.iloc[0])
rc = rd("regioncounty")
regions = set(rc[(rc.regionCodeID == 2) & (rc.countyID == COUNTY)
                 & (rc.fuelYearID == fuel_year)].regionID)
sup, form, fst = rd("nrfuelsupply"), rd("fuelformulation"), rd("nrfuelsubtype")
sup["marketShare"] = sup.marketShare.astype(float)
for c in ("ETOHVolume", "MTBEVolume", "ETBEVolume", "TAMEVolume", "volToWtPercentOxy"):
    form[c] = form[c].astype(float)
m = sup[sup.fuelRegionID.isin(regions) & (sup.monthGroupID == MONTH)
        & (sup.fuelYearID == fuel_year)].merge(form, on="fuelFormulationID") \
                                        .merge(fst[["fuelSubtypeID", "fuelTypeID"]], on="fuelSubtypeID")
gas = m[m.fuelTypeID == 1]
OXY = f((gas.marketShare * ((gas.ETOHVolume + gas.MTBEVolume + gas.ETBEVolume
                            + gas.TAMEVolume) * gas.volToWtPercentOxy)).sum())
# mworeader.go parseLines: a nonroad worker row fans out into one emission per
# nrFuelSupply entry, mass scaled by the entry's market share.
SUPPLY = [(int(r.fuelSubtypeID), float(r.marketShare)) for r in gas.itertuples()]


def adjustments(scc):
    two = scc[:4] == "2260"
    dt = f(TAMB - f(75.0))
    if two:
        a = (f(0.0), f(0.0), f(0.0))
        c = (f(0.006), f(0.065), f(-0.186))
    else:
        a = (f(-0.00240), f(0.0015784), f(-0.00892)) if TAMB <= 75 \
            else (f(0.00132), f(0.00375), f(-0.00873))
        c = (f(0.045), f(0.062), f(-0.115))
    out = {}
    for i, p in enumerate(("THC", "CO", "NOx")):
        out[p] = f(f(np.exp(f(a[i] * dt))) * f(f(1.0) - c[i] * OXY))
    out["PM"] = f(1.0)
    out["BSFC"] = f(1.0)          # nrdeterioration carries no 9901 row either
    return out


# ------------------------------------------- emission factors and the tech mix
er, tf, det = rd("nremissionrate"), rd("nrengtechfraction"), rd("nrdeterioration")
DET = {(k, int(r.engTechID)): (f(float(r.DFCoefficient)), f(float(r.DFAgeExponent)),
                               f(float(r.emissionCap)))
       for k, pp in PP.items() for r in det[det.polProcessID == pp].itertuples()}

SLOT = {v: k for k, v in PP.items()}
RATES = {}                        # (SCC, engTechID) -> slot -> [(hpMin,hpMax,rate)]
for r in er.itertuples():
    s = SLOT.get(int(r.polProcessID))
    if s is None:
        continue
    RATES.setdefault((r.SCC, int(r.engTechID)), {}).setdefault(s, []).append(
        (int(r.hpMin), int(r.hpMax), f(float(r.meanBaseRate))))

MIXES = {}                        # (SCC,hpMin,hpMax) -> engTechID -> MY -> fraction
for r in tf[tf.processGroupID == 1].itertuples():
    MIXES.setdefault((r.SCC, int(r.hpMin), int(r.hpMax)), {}) \
         .setdefault(int(r.engTechID), {})[int(r.modelYearID)] = f(float(r.NREngTechFraction))
MIX_KEYS = sorted(MIXES)


def tech_mix(scc, hp):
    """`.TECH`: the first bin, in ascending (SCC, hpMin, hpMax) order, of the
    most specific SCC in the equipment chain that has one containing hp
    (nonroad_loader.rs build_entries_from_mix)."""
    for s in equip_chain(scc):
        for key in MIX_KEYS:
            if key[0] == s and f(key[1]) <= hp <= f(key[2]):
                return MIXES[key]
    return {}


def rate_for(scc, hp, tid, slot):
    """`.EMF`: the SCC chain is walked PER ENGINE TECHNOLOGY, and within a
    level the first hp bin containing hp in file order wins."""
    for s in equip_chain(scc):
        for lo, hi, v in RATES.get((s, tid), {}).get(slot, ()):
            if f(lo) <= hp <= f(hi):
                return v
    return None


# ------------------------------------------------- the speciation lookup tables
hpcat = {(int(r.nrhprangebinid), int(r.engtechid)): r.nrhpcategory
         for r in rd("nrhpcategory").itertuples()}
CH4 = {(int(r.processID), int(r.engTechID), int(r.fuelSubtypeID), r.nrHPCategory):
       float(r.CH4THCRatio) for r in rd("nrmethanethcratio").itertuples()}
HCS = {(int(r.pollutantID), int(r.processID), int(r.engTechID),
        int(r.fuelSubtypeID), r.nrHPCategory): float(r.speciationConstant)
       for r in rd("nrhcspeciation").itertuples()}


def by_subtype(df, col):
    d = {}
    for r in df.itertuples():
        d.setdefault((int(r.processID), int(r.engTechID), int(r.fuelSubtypeID),
                      r.nrHPCategory), []).append((int(r.pollutantID), float(getattr(r, col))))
    return d


def by_fueltype(df, proc, eng, col):
    d = {}
    for r in df.itertuples():
        d.setdefault((int(getattr(r, proc)), int(r.fuelTypeID), int(getattr(r, eng)),
                      r.nrHPCategory), []).append((int(r.pollutantID), float(getattr(r, col))))
    return d


ATR = by_subtype(rd("nratratio"), "atRatio")
PAHG = by_fueltype(rd("nrpahgasratio"), "processid", "engTechID", "atratio")
PAHP = by_fueltype(rd("nrpahparticleratio"), "processid", "engTechID", "atratio")
DIOX = by_fueltype(rd("nrdioxinemissionrate"), "processID", "engtechID", "meanBaseRate")
METAL = by_fueltype(rd("nrmetalemissionrate"), "processID", "engTechID", "meanBaseRate")
INTEGRATED = {int(x) for x in rd("nrintegratedspecies").pollutantID}
NEEDED = {int(x) for x in rd("runspecpollutantprocess").polProcessID}
# nrairtoxics.go gallonsFactor: TWO sequential divisions, not 1/(453.592*rho).
GALLONS = (1.0 / GRMLB) / GAS_DENSITY_TOXICS

# --------------------------------------------------------------- the run
sut, pop = rd("nrsourceusetype"), rd("nrbaseyearequippopulation")
scct, eqt = rd("nrscc"), rd("nrequipmenttype")
sectors = set(rd("runspecsector").sectorID)
fuels = set(rd("runspecfueltype").fuelTypeID)
eq_sector = dict(zip(eqt.NREquipTypeID, eqt.sectorID))
eq_surr = dict(zip(eqt.NREquipTypeID, eqt.surrogateID))
allowed = {r.SCC for r in scct.itertuples()
           if eq_sector.get(r.NREquipTypeID) in sectors and r.fuelTypeID in fuels}
scc_surr = {r.SCC: eq_surr[r.NREquipTypeID] for r in scct.itertuples()
            if r.NREquipTypeID in eq_surr}

pop_by_src = {}
for r in pop[pop.stateID == STATE].itertuples():   # .POP is written %17.1f
    pop_by_src[r.sourceTypeID] = pop_by_src.get(r.sourceTypeID, 0.0) \
        + round(float(r.population) * 10) / 10

# The worker's own granularity: one MOVESWorkerOutput row per
# (SCC, model year, engTechID, hpID, pollutant), which is where the speciation
# ratios key. `cells` is that relation.
cells = {}
for r in sut.itertuples():
    if r.SCC not in allowed:
        continue
    sp = pop_by_src.get(r.sourceTypeID)
    if not sp:
        continue
    scc = r.SCC
    hp, hrs = f(float(r.hpAvg)), f(float(r.hoursUsedPerYear))
    ldf, mdl = f(float(r.loadFactor)), f(float(r.medianLifeFullLoad))
    hpid = int(r.NRHPRangeBinID)
    ys, vs = growth_series(int(gp[(gp.SCC.isin(equip_chain(scc)))
                                 & (gp.stateID.isin([STATE, 0]))].iloc[0].growthPatternID))
    yy, mf0, ny = scrptime(mdl, ldf, hrs, growth_factor(ys, vs, 1990, 1991))
    md = agedist(f(sp), mf0, 1990, YEAR, yy, ys, vs)
    cp = f(f(sp) * alloc_frac(scc_surr[scc]))
    tpl = f(month_fraction(scc) * f(f(7.0) * day_fraction(scc)))
    adjtime, cvt = f(f(1.0) / f(NDAYS)), f(hp * ldf)
    adj = adjustments(scc)
    MIX = tech_mix(scc, hp)
    tech_ids = sorted(MIX)[:MXTECH]
    EF = {(p, tid): rate_for(scc, hp, tid, p) for p in PP for tid in tech_ids}
    for idx in range(ny):
        if md[idx] <= 0:                          # prccty.f skips modfrc <= 0
            continue
        my = YEAR - idx
        detage = f(f(idx + 1) * hrs * ldf / mdl)
        for tid in tech_ids:
            byyear = MIX[tid]
            yrs = [y for y in sorted(byyear) if y <= min(my, YEAR)]
            frac = byyear[yrs[-1]] if yrs else byyear[sorted(byyear)[0]]
            if frac <= 0:
                continue
            for p in PP:
                rate = EF.get((p, tid))
                if rate is None:
                    continue
                A, B, cap = DET.get((p, tid), (f(0), f(1), f(0)))
                DF = f(f(1.0) + A * f((detage if detage <= cap else cap) ** B))
                emstmp = f(f(f(f(rate * cvt) * DF) * adj[p]) * adjtime)
                emiss = f(f(f(f(f(emstmp * hrs) * tpl) * cp) * md[idx]) * frac)
                k = (scc, my, tid, hpid)
                cells.setdefault(k, {})
                cells[k][p] = f(cells[k].get(p, f(0)) + f(emiss * f(CVTTON)))

# ---------------------------------- NRHCSpeciation and NRAirToxics, both in f64
totals = {}


def emit(pol, scc, my, q):
    if pol * 100 + 1 in NEEDED:
        totals[(pol, scc, my)] = totals.get((pol, scc, my), 0.0) + q


for (scc, my, tid, hpid), d in cells.items():
    thc0 = float(d.get("THC", f(0))) / CVTTON
    pm10 = float(d.get("PM", f(0))) / CVTTON
    # BSFC: the engine divides by CMFGAS to get gallons, the loader multiplies
    # by 6.237 lb/gal and 453.592 g/lb to get grams; the densities cancel.
    fuel0 = (float(d.get("BSFC", f(0))) / CVTTON) / GAS_DENSITY_NONROAD \
        * GAS_DENSITY_NONROAD * GRMLB
    pm25_0 = pm10 * PM25_OF_PM10
    cat = hpcat.get((hpid, tid), 0)
    emit(1, scc, my, thc0)
    emit(100, scc, my, pm10)
    emit(99, scc, my, fuel0)
    emit(110, scc, my, pm25_0)
    for sub, share in SUPPLY:
        thc, pm25, fuel = thc0 * share, pm25_0 * share, fuel0 * share
        r = CH4.get((1, tid, sub, cat))
        if r is None:                    # the Go `continue`s past the emission
            continue
        methane, nmhc = thc * r, thc * (1.0 - r)
        nmog = nmhc * HCS.get((80, 1, tid, sub, cat), 0.0)
        voc = nmhc * HCS.get((87, 1, tid, sub, cat), 0.0)
        emit(5, scc, my, methane)
        emit(79, scc, my, nmhc)
        emit(80, scc, my, nmog)
        emit(87, scc, my, voc)
        emit(86, scc, my, nmog + methane)
        produced = {}
        for pol, ratio in ATR.get((1, tid, sub, cat), ()):
            produced[pol] = voc * ratio
        for pol, ratio in PAHG.get((1, 1, tid, cat), ()):
            produced[pol] = voc * ratio
        for pol, ratio in PAHP.get((1, 1, tid, cat), ()):
            produced[pol] = pm25 * ratio
        for pol, ratio in DIOX.get((1, 1, tid, cat), ()):
            produced[pol] = fuel * (ratio * GALLONS)
        for pol, ratio in METAL.get((1, 1, tid, cat), ()):
            produced[pol] = fuel * (ratio * GALLONS)
        nonhap = nmog
        for pol, q in produced.items():
            emit(pol, scc, my, q)
            if pol in INTEGRATED:
                nonhap -= q
        emit(88, scc, my, nonhap)

# ------------------------------------------------------------------- compare
exp = pq.read_table(D + "db__out_nr_airtoxics_lawn_garden_county__movesoutput.parquet") \
        .to_pandas()
obs = {(int(r.pollutantID), r.SCC, int(r.modelYearID)): float(r.emissionQuant)
       for r in exp.itertuples()}

# `float_decimals: 12` in every table's .meta.json: the capture writes floats
# with twelve DECIMAL places, so a stored value keeps
# 12 + floor(log10|v|) + 1 significant digits and no more.
QUANTUM = 1e-12


def sig_digits(v):
    return 0 if v == 0 else max(0, 12 + int(math.floor(math.log10(abs(v)))) + 1)


DIOXIN_STORED = {131: 1.105e-09, 142: 1.9e-11}   # nrdioxinemissionrate, gasoline

missing = sorted(set(obs) - set(totals))
extra = sorted(set(totals) - set(obs))
full = storage_limited = 0
worst_full = worst_limited = 0.0
worst_full_at = worst_limited_at = None
for k, want in obs.items():
    got = totals[k] if k in totals else None
    if got is None:
        continue
    rel = abs(got - want) / abs(want) if want else abs(got)
    if k[0] in DIOXIN_STORED:
        continue                       # accounted for separately, below
    if sig_digits(want) >= 8:
        full += 1
        if rel > worst_full:
            worst_full, worst_full_at = rel, k
    else:
        storage_limited += 1
        # The stored value is a rounding of the true one to twelve decimals, so
        # half a quantum of absolute slack is the reference's own resolution --
        # not a tolerance chosen here.
        excess = max(0.0, abs(got - want) - 0.5 * QUANTUM)
        r = excess / abs(want) if want else excess
        if r > worst_limited:
            worst_limited, worst_limited_at = r, k

print("%d rows compared, %d missing, %d extra"
      % (len(obs) - len(missing), len(missing), len(extra)))
print("  fully stored cells   %5d  worst relative error %.3e  at %s"
      % (full, worst_full, worst_full_at))
print("  storage-limited      %5d  worst relative error %.3e in excess of the"
      % (storage_limited, worst_limited))
print("                              12-decimal capture quantum, at %s"
      % (worst_limited_at,))

# The two dioxin congeners are a different failure and get their own account:
# their `nrdioxinemissionrate.meanBaseRate` is 1.105e-09 and 1.9e-11, which
# twelve decimals store to four and TWO significant figures. Fit the rate the
# reference must have used and show it is inside half a quantum of the stored
# one -- that is the whole of the difference, and it is the capture's.
implied = {}
for pol, stored in DIOXIN_STORED.items():
    minsig = 5 if pol == 131 else 4
    num = den = 0.0
    for k, want in obs.items():
        if k[0] != pol or want == 0 or sig_digits(want) < minsig:
            continue
        num += want * totals[k]
        den += totals[k] * totals[k]
    scale = num / den
    implied[pol] = stored * scale
    worst = max(abs(totals[k] * scale - want) / abs(want)
                for k, want in obs.items()
                if k[0] == pol and sig_digits(want) >= minsig)
    print("  pollutant %-3d rate stored %.6g, implied %.8g "
          "(%.3f half-quanta); rescaled worst %.3e"
          % (pol, stored, implied[pol], abs(implied[pol] - stored) / (0.5 * QUANTUM),
             worst))

assert len(obs) == 14036, len(obs)
assert not missing and not extra, (len(missing), len(extra))
assert full == 10439, full
# tolerance.toml [cell] rel, unmodified, on every cell the capture stores in full
assert worst_full < 2e-5, worst_full
# and on the rest, once the capture's own quantum is allowed for
assert worst_limited < 2e-5, worst_limited
# both dioxin rates are inside half a stored quantum of the value MOVES used
for pol, stored in DIOXIN_STORED.items():
    assert abs(implied[pol] - stored) < 0.5 * QUANTUM, (pol, implied[pol])
```

### 6.6 What the fixture's and the components' inline tests check

`fixtures/nr-airtoxics-lawn-garden-county.esm` carries four inline tests, kept
few because each one costs a whole evaluation of a 263-equation document that
ingests 35 tables (finding **F31**). Each is a claim the row-by-row comparison
cannot make: that all 29 output rows reach one of the three rated blocks
(`rpp_rootOrdinal` between 1 and 3, both ends pinned); that
`tech_fractionTotal` is 1 and the horse-power category takes both its values;
that the share-weighted CH₄ multiplier reaches 0.149 exactly, which is only
possible if the speciation is inside the technology contraction; and that the
largest emitted cell is the snapshot's own largest, 4,170,270 g of fuel
consumption at SCC 2265004071 model year 2020.



`components/nr_hc_speciation.esm` and `components/nr_air_toxics.esm` carry the
arithmetic on `const` relations at the coefficient values §6.1 and §6.2 read
out of the snapshot, so each stage is checked where the fixture-scale
comparison cannot attribute a failure. Between them they pin:

* both technology coefficient sets of §6.1, so the CH₄/NMHC split, both
  speciation constants and the TOG sum are each exercised at two values rather
  than at one;
* the **missing-row arms** of both calculators, which this snapshot never
  reaches: a probe technology with no `nrMethaneTHCRatio` row (the emission is
  skipped entirely and produces no species at all) and one with no
  `nrHCSpeciation` row (NMOG and VOC are an explicit **zero**, not an absent
  row). §7.2 measures that neither fires on any of the run's 2,063 worker
  cells, which is exactly why they belong in a component;
* the `gallons_factor` operation order — `(1 ÷ 453.592) ÷ 6.17` against
  `1 ÷ (453.592 × 6.17)` — and the `rate × unit_factor` association, both of
  which are bit-level choices the reference makes and no comparison against a
  six-significant-figure column could see;
* the NonHAPTOG residual over the nine integrated species, with a probe
  species outside the set to prove the membership test is doing work.

## 7. Fidelity notes and tolerance

### 7.1 The measured result

`./run-nr-airtoxics-oracle.sh`, computing the whole chain from the snapshot's
input tables and taking nothing from the reference but the final comparison:

```
14036 rows compared, 0 missing, 0 extra
  fully stored cells   10439  worst relative error 9.425e-06  at (88, '2265004010', 1981)
  storage-limited       2629  worst relative error 8.655e-06 in excess of the
                              12-decimal capture quantum, at (60, '2265004015', 2010)
  pollutant 131 rate stored 1.105e-09, implied 1.1045021e-09 (0.996 half-quanta); rescaled worst 4.239e-05
  pollutant 142 rate stored 1.9e-11,   implied 1.9434497e-11 (0.869 half-quanta); rescaled worst 3.300e-04
```

10,439 + 2,629 + 968 = 14,036, the 968 being pollutants 131 and 142.

### 7.2 The snapshot capture stores twelve DECIMAL places, and that is the gate

Every table's `.meta.json` in this corpus carries `"float_decimals": 12`. The
capture therefore writes a float as a decimal string with twelve places after
the point, so a stored value keeps `12 + floor(log10|v|) + 1` **significant**
digits — six for a value of 10⁻¹, but **one** for a value of 10⁻¹². Two
consequences, and they are different failures:

**(a) On the output side.** 3,597 of the 14,036 `MOVESOutput` cells are stored
with fewer than eight significant digits, and 1,208 of them are stored as
`0.000000000000` outright. `compare-output.py` already concedes the second case
— "when only the expectation is zero, fall back to absolute, since there is no
scale to be relative to" — and the general form of that concession is what §7.1
reports separately: allow the capture's own half-quantum, 5 × 10⁻¹³ absolute,
and the worst of those 2,629 cells is **8.655 × 10⁻⁶**, inside the unmodified
`[cell] rel = 2e-5`. Without that allowance, **283** of them exceed
2 × 10⁻⁵ under the comparator's own rule, which falls back to an absolute
error where the expectation is an exact zero.

**(b) On the INPUT side, which no gate reading can fix.**
`nrdioxinemissionrate.meanBaseRate` for gasoline running exhaust is
`0.000000001105` and `0.000000000019` — **four** and **two** significant
figures. MOVES read those from a MySQL `double`; the port can only read the
capture. Fit the rate the reference must have used, from the pollutant's own
output cells:

| pollutant | stored | implied by the output | distance | uniform bias it causes |
|---|---|---|---|---|
| 131 (OCDD) | 1.105 × 10⁻⁹ | 1.1045021 × 10⁻⁹ | 0.996 half-quanta | 4.5 × 10⁻⁴ |
| 142 (2,3,7,8-TCDD) | 1.9 × 10⁻¹¹ | 1.9434497 × 10⁻¹¹ | 0.869 half-quanta | 2.24 × 10⁻² |

Both implied rates are **inside half a stored quantum** of the captured value,
which is the whole of the difference and is decisive: rescale by the fitted
factor and the worst residual over each pollutant's better-stored cells falls
to 4.239 × 10⁻⁵ and 3.300 × 10⁻⁴, which is those cells' own output
quantisation. There is no arithmetic here to correct.

**What that costs, stated plainly.** A per-cell comparison of this snapshot's
`MOVESOutput` against any correct implementation fails on **1,013 of 14,036
cells** at `[cell] rel = 2e-5`: **729** of pollutants 131 and 142 (cause (b);
the other 239 of their cells are stored as an outright zero, which the
comparator's own absolute fallback lets through) and **283** more from cause
(a). §8 records what follows for the fixture.

### 7.3 Precision-sensitive operations, ranked

1. **The `.EMF` per-technology SCC chain** (§2.1a) — wrong by up to 6.9× on
   five SCCs, not a rounding question at all.
2. **The `.TECH` single-bin rule** (§2.1b) — 1.24 to 1.43× on one SCC.
3. **`gallonsFactor`'s two divisions and `rate × gallons` as one product** —
   sub-ulp, and untestable against this snapshot.
4. **The NONROAD engine is `real*4` and both calculators are `f64`**, with an
   f32 round-trip at `MOVESWorkerOutput` between them (`CreateWorker.sql:79`
   declares the column `FLOAT`). The oracle reproduces that split: the base
   chain in `np.float32`, the speciation in Python floats.
5. **Where the f32 round-trip happens.** MOVES writes one worker row per
   equipment point; the oracle sums the points sharing a
   `(SCC, modelYear, engTechID, hpID)` cell **before** the round-trip. 108
   points collapse to 2,063 such cells, so some cells round once where MOVES
   rounds two or three times. It is below the storage floor everywhere here and
   is written down rather than claimed away.

## 8. Gaps and things not verified

**`fixtures/nr-airtoxics-lawn-garden-county.esm` emits all 14,036 rows and
compares 13,068 of them.** The 968 it does not compare are pollutants 131 and
142, for §7.2(b)'s reason: they are emitted, with the right keys and the right
arithmetic, and the rate they are computed from was captured to two and four
significant figures, so no implementation reading this capture can be closer.
`tolerance.toml` records that as a **scope** — a third thing beside a tolerance
and a shortfall (`docs/esm-conventions.md` §36.3) — with the fitted rates and
the half-quantum distances in a mandatory `why`, and `compare-output.py` prints
what it held out on every run. The gate itself is untouched: `[cell] rel` is
still 2 × 10⁻⁵ and the fixture's worst compared cell is **9.417 × 10⁻⁶** over
13,068 cells, with the key set exact and the worst per-pollutant sum
1.442 × 10⁻⁶.

The 283 cells of cause (a) are compared and pass, because the same `scope`
declares `allow_storage_quantum`: the comparison is made at the resolution the
snapshot is stored in, half a quantum — 5 × 10⁻¹³, **read off the snapshot's
own `.meta.json`** rather than chosen — as an absolute floor beneath the
unchanged relative gate. It is the concession `relerr` already makes for an
expected zero, one step earlier, and it is opt-in so that no other fixture's
gate moves.

The correct fix for the dioxins is upstream: re-capture with more significant
digits — `FLOAT_DECIMALS` is a single constant,
`moves.rs/crates/moves-snapshot/src/format.rs:17`.

**Everything below is a stage that runs but is not discriminated by this
snapshot**, measured rather than assumed:

* **Both missing-row arms are dead.** Over all 2,063 worker cells there are
  **0** cells with no `nrhpcategory` row, **0** with no `nrMethaneTHCRatio`
  row, and **0** with no `nrHCSpeciation` row for either 80 or 87. So the Go's
  skip-the-emission and its zero-emission fallback are written from the source
  and exercised only in `components/nr_hc_speciation.esm`.
* **Every ratio lookup hits, and always with the same arity**: 8 details from
  `nrATRatio`, 2 from `nrPAHGasRatio`, 2 from `nrPAHParticleRatio`, 2 from
  `nrDioxinEmissionRate` and 5 from `nrMetalEmissionRate`, on **every** cell.
  The five output-pollutant sets are disjoint, so the Go's last-write-wins
  overwrite is written and untested.
* **`MXTECH = 32` never bites.** The largest `.TECH` tech list any of the 108
  points draws is **9** (sizes 3, 6, 7 and 9). The truncation is in the port
  because it is in the reference, not because this run needs it.
* **One process, one fuel type.** Everything here is process 1 and fuel type 1.
  `NRHCSpeciationCalculator` registers 45 pollutant-process pairs and
  `NRAirToxicsCalculator` 205 (`calculator-dag.json`); this snapshot's output
  exercises 5 and 21 of them. The fuel path's process-1-only guard is therefore satisfied trivially,
  and the diesel/CNG/LPG densities (7.1, 0.0061, 4.507) and the diesel PM2.5
  factor (0.97) are written from the source and never evaluated.
* **The two fuel-subtype ids cannot be told apart.** `nrMethaneTHCRatio` and
  `nrATRatio` key on the *formulation's* subtype and `nrHCSpeciation` on the
  *emission's*; here both are 12 on the only supplied formulation, so the
  distinction is preserved from the source and is unfalsifiable
  (`docs/esm-conventions.md` §32.5's rule, and the oracle asserts the identity).
* **The market-share fan-out is 1.0 and 0.0.** Two formulations are supplied
  and one has market share 0, so the weighting is exercised only at its two
  endpoints; a county with two real shares would test the sum.
* **`nrHPCategory` is discriminating, and that is worth saying because so
  little else is**: 1,908 of the 2,063 cells are `S` and 155 are `L`, so a
  document that dropped the category from the key would join to the wrong rows
  on 155 cells rather than to none.
* **The 0.92 PM2.5 factor is not in `../moves.rs`.** It is read from canonical
  MOVES (`NonroadOutputDataLoader.java:454-481`); grepping `crates/` for `0.92`
  returns nothing. So the port's authority for it is the Java, and the
  agreement of the ratio to 2 × 10⁻⁶ on all 484 cohorts is the only check.
* **`nrsulfuradjustment` is read by nothing here.** Its PM sulfur correction is
  a diesel path (`emissions/exhaust.rs:1156`) and this run is gasoline.
* **The 2-stroke/4-stroke `emsadj.f` split is exercised**, 11 SCCs against 20,
  which is worth recording as a *positive*: `docs/nonroad-logging-county.md`
  §2.5's two coefficient sets both fire here, where the logging fixture only
  ever took one of them.

## 9. Summary for the `.esm` author

1. The base chain is `docs/nonroad-logging-county.md`'s, with §2.1's three
   corrections. Two of them change a **key**, not a number: the `.EMF`
   effective SCC is per `(SCC, engTechID)` and the `.TECH` bin is the first
   containing bin, not every containing bin.
2. Fuel consumption is `lb/hp-hr × 453.592`, with no deterioration and no
   `emsadj.f` adjustment; write the engine's ÷6.237 and the loader's ×6.237
   rather than the cancelled constant, because the toxics path uses 6.17.
3. The speciation lives **inside** the engine-technology contraction. Every
   ratio keys on `(engTechID, nrHPCategory)` and most on the fuel subtype too.
4. Five ratio tables, two forms, `lib/nonroad_speciation.esm` (§4). Twenty of
   the twenty-nine output pollutant ids come out of the tables' own
   `pollutantID` column and are named nowhere.
5. NonHAPTOG is `NMOG − Σ(nrIntegratedSpecies)`, formed by the output
   aggregation out of signed partial rows.
6. The output row set is 484 cohorts × 29 blocks, and the 484 are ragged over
   SCC. §31's global rank is the shape; the blocks being equal here is a
   property of the data, not of the layout.
