# `process-airtoxics` — computation specification

The port specification for the first fixture that reaches **two speciation
calculators in series**, written to the method of `docs/process-brakewear.md`:
the input inventory determined from evidence, the chain with source lines into
`../moves.rs`, every join with its exact key pairs, and worked examples whose
numbers can be checked by hand.

**The parent is not new, and that is measurable rather than argued.** The THC ×
Running Exhaust block of this snapshot's `MOVESOutput` is **byte-identical** to
`process-crankcase-running`'s `(pollutantID 1, processID 1)` block — all 248
rows, all 248 values, character for character in the reference's own decimal
text. So the whole criteria-pollutant parent — `emissionratebyage` and its
`ageGroupID` row-set key, the per-formulation `criteriaratio` fuel effect, the
fuel-supply resolution — is `docs/process-crankcase-running.md` §§2.2–2.3 and
`docs/process-nox-speciation.md` §§2.2–2.3 unchanged, and is not re-derived
here.

What is new is the five chained blocks, and they are new in four ways no earlier
rung has:

1. **The chain is three levels deep.** `runspecchainedto` says 7901 ← 101,
   8701 ← 7901 and 2001/2401/2501 ← 8701. `docs/process-nox-speciation.md` §2.5
   closes with "a fixture that reached [a deeper chain] would have to resolve
   the parent's own survival first"; this is that fixture, and §2.6 is how it
   resolves it.
2. **Two calculators, and only one of them is chained.**
   `HCSpeciationCalculator` reads no `RunSpecChainedTo` at all — it takes a THC
   block and returns up to five species from it in one pass
   (`hcspeciation.rs::speciate_emission`). `AirToxicsCalculator` does read it,
   twice, and is chained in the ordinary sense. The document writes each the way
   its source is written (§2.4, §2.5), and the difference is visible in the
   shape of the two stages.
3. **The ratios key on the fuel SUBTYPE and the fuel FORMULATION**, not on the
   fuel type, so every factor lives on the (cohort × supplied formulation)
   relation that `criteriaratio` already introduced and is re-collapsed by
   market share exactly once (§2.3).
4. **An E85 model year 2001-and-later burns a different fuel for speciation
   purposes than for combustion.** `adjust.rs::build_e85_block` emits a parallel
   `altTHC` tally (pollutant 10001) scaled by `altCriteriaRatio / criteriaRatio`,
   and `hcspeciation.rs` speciates *that* into VOC using the E10 subtype's
   ratios while NMHC still comes from the ordinary THC. It multiplies the
   emitted VOC by **3.8528** on 20 of the run's 23 ethanol cohorts (§2.4.1) —
   this fixture would be wrong by that factor on 40 of its 1,288 rows without
   it, which is not a rounding difference.

---

## 0. The fixture at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/process-airtoxics.xml` |
| Model | ONROAD, `modelscale` `Inv` (inventory), `modeldomain` `DEFAULT` |
| Geography | county 26161 (Washtenaw, Michigan), zone 261610, link 2616104 |
| Time | year 2020, month **8**, hour **7**, day types **2 (weekend) and 5 (weekday)** |
| Vehicles | sourceTypeID 21 (passenger car); fuel types **1, 2, 5, 9** |
| Road | roadTypeID 4 (urban restricted access) |
| Pollutant/process | **101** (THC × Running Exhaust) and its five chained species **7901** (NMHC), **8701** (VOC), **2001** (benzene), **2401** (1,3-butadiene) and **2501** (formaldehyde) |
| Model years | 1980–2020 (41) |
| Output | `db__out_process_airtoxics__movesoutput`, **1,288 rows** |
| Output units | **grams** for all six pollutants; `outputtimestep` **Hour** |
| Calculator path | `TotalActivityGenerator` → `SourceBinDistributionGenerator` → `BaseRateGenerator` → `BaseRateCalculator` → **`HCSpeciationCalculator`**, **`AirToxicsCalculator`** → output aggregation |
| Snapshot | 368 tables, **251 non-empty** |

### 0.1 The RunSpec on disk does not describe the captured run

The same rule as `docs/mixed-onroad.md` §0.1, and for the same reason: the XML's
`<month key>`, `<beginhour key>` and `<day key>` are canonical `RunSpecXML`
**0-based indices into sorted ID lists**, not identifiers. The execution
database's `runspecmonth`, `runspechour` and `runspecday` say month 8, hour 7,
and day types 2 **and** 5, and `runspecpollutantprocess` says 101, 2001, 2401,
2501, 7901 and 8701. The execution database is the authority.

### 0.2 Why 1,288 rows, and which cohorts each block drops

1,288 = (124 + 104 × 5) × 2 day types.

| | THC (101) | each of the five species |
|---|---|---|
| gasoline (1) | 41 model years, 1980–2020 | 41 |
| diesel (2) | 40, 1980–2019 | 40 |
| E85 (5) | 23, 1998–2020 | 23 |
| electricity (9) | 20, 2001–2020 | **none** |
| cohorts | **124** | **104** |

* **124** cohorts of THC. 125 of the 164 (model year, fuel type) candidates pass
  `stmyFraction > 0`; the one that is selected and still not emitted is **model
  year 2000, electricity**, whose age group at analysis year 2020 is 2099 and
  for which `emissionratebyage` carries no fuel-type-9 row. Model years
  2001–2020 electricity *are* emitted, at exactly zero. This is a row-set
  consequence of a rate KEY, which is the sort of thing a row count finds and a
  sum does not (`docs/esm-conventions.md` §30.1).
* **104** cohorts of every species, and it is the **same** 104 in all five
  blocks — the 124 minus every electricity cohort. The cause is a *chain* of
  three misses on the electricity column, not one: `methaneTHCRatio` has no fuel
  subtype 90 row, so NMHC is not produced; VOC is produced by the same
  `speciate_emission` call and dies with it; and the three toxics are chained
  off VOC and cannot outlive it. Any one of the three would have sufficed, which
  is why §2.6 resolves survival transitively rather than testing the three
  tables independently.

`sbweightedemissionratebyage` is 2,852 rows = 23 operating modes × 124, the same
124 arrived at by a route this document does not read. `baseratebyage_1_2020` is
248 = 124 × 2 hour-day ids, of which **208 are non-zero** — the 40 electricity
rows carry a real rate of exactly zero.

---

## 1. Input inventory

### 1.1 The tables the parent already reads

The activity chain (S1–S9), the cohort structure and the fuel-usage rebase
(S10–S12), the drive-cycle operating-mode weights, the age-group-keyed rate out
of `emissionratebyage`, the fuel-supply resolution and `criteriaratio` are all
`docs/process-crankcase-running.md` §§1.2, 2.2–2.3 and are not restated. Read
`docs/mixed-onroad.md` §§1–3 for the activity half and
`docs/process-nox-speciation.md` §2.2–2.3 for the criteria-pollutant half.

### 1.2 The eight tables this fixture adds

| table | rows | role |
|---|---:|---|
| `methanethcratio` | 140 | `CH4THCRatio`, keyed by process, fuel **subtype**, regClass and a model-year range (§2.4) |
| `hcspeciation` | 136 | the NMOG/VOC `(speciationConstant, oxySpeciation)` pair, keyed by pol-process, fuel **subtype**, regClass and a model-year range (§2.4) |
| `altcriteriaratio` | 60 | the E85 `altTHC` numerator (§2.4.1) |
| `atratio` | 243 | `ATRatioGas1`: the toxic-over-VOC ratio per fuel **formulation** (§2.5) |
| `atrationongas` | 372 | `ATRatioNonGas`: the same per fuel **subtype** and model-year group (§2.5) |
| `atbaseemissions` | 4 | *present and NOT read* — see §1.3 |
| `runspecchainedto` | 5 | the three-level chain declaration, read rather than written down (§2.6) |
| `fuelformulation` | 2,158 | *already read* for `fuelSubtypeID`; now also for the four oxygenate volumes and `volToWtPercentOxy` (§2.4) |

One table the parent read is **gone**: `temperatureadjustment` has **0 rows** in
this snapshot (it had 4 in `process-nox-speciation`), and `generalfuelratio` has
0 as well (it had 39 in `process-crankcase-running`). §2.2 says what that costs.

### 1.3 What is NOT an input

`emissionrate` (0 rows here), `baseratebyage_1_2020`, `baserateoutput`,
`sbweightedemissionratebyage`, `sourcebindistribution`, `sho` and `MOVESOutput`
are generator or expected output. None is a `data_sources` entry. Values out of
the first, third, fifth and sixth appear as `expected` in the inline tests,
which is the opposite direction.

**Four of `AirToxicsCalculator`'s six ratio paths are dead here, and they are
dead by measurement.** `minorhapratio`, `pahgasratio`, `pahparticleratio` and
`atratiogas2` all have **0 rows**, and `airtoxics.rs::air_toxics_block` runs a
path only when `flag && !table.is_empty()`. They are named in §7.2 rather than
claimed.

**`atbaseemissions` (4 rows) is not read.** It is an input to
`FuelEffectsGenerator`, which turns it and `generalfuelratioexpression`'s
`atDifferenceFraction` expressions into the `atratio` table this document reads
(the snapshot's `tempairtoxicsa`, `tempairtoxicsavoc` and `tempairtoxicsanonvoc`
are that generator's own scratch, 41 + 82 + 123 rows). As in
`docs/process-nox-speciation.md` §1.3, this fixture is on the snapshot path,
where `atratio` and `criteriaratio` ship captured; porting
`FuelEffectsGenerator` is a separate rung and is **not** claimed in the
calculator path above.

**Both HC speciation tables ship populated in snapshots that do not read
them.** `methanethcratio` is non-empty in all nine already-ported snapshots
(81 to 500 rows) and `hcspeciation` in two of them, `process-evap-fvv` and
`process-evap-leaks` at 81 rows each — and none of those nine reads either,
correctly, because no calculator they port consults them. A populated table is
not an input; a column reaching `emissionQuant` is.

---

## 2. The computation chain

### 2.1 What is unchanged

S1–S18 of `docs/process-crankcase-running.md` for the THC parent, whose
resulting 248 rows are byte-identical to that fixture's process-1 block. The
rate relation is the run's **six** pollutant-processes crossed with the 41 × 4
cohort candidate grid, 984 rows, every factor a discovered extent; every rate
column is read back through `rt_polProcOrdinal` / `rt_cohortOrdinal`.

### 2.2 Two adjustment stages are absent, not zero

`temperatureadjustment` has **0 rows**, so the exact-regClass and
regClassID-0 wildcard lookups both miss and the additive identity gives
A = B = 0. Pollutant 1 is not 118/112 (PM), not the fuel-9 energy pollutant 91,
and not 3 (NOx), so `general_temp_adjust` (`adjust.rs:132–142`) reaches its
**fall-through quadratic**:

```
factor = 1 + (T - 75) x (A + (T - 75) x B)       = 1 exactly, for every row
```

The two-step wildcard precedence and the quadratic are still written —
`lib/adjustments.esm`'s `exact_else_wildcard` and
`quadratic_temperature_adjustment`, both already in the library — because
`mixed-onroad` §7 demonstrably needed the first and `adjust.rs` writes the
second. `noxhumidityadjust` is populated (3 rows) and is **not read**: the
humidity correction multiplies only inside the NOx arm, which pollutant 1 does
not enter.

`generalfuelratio` is empty too, so `adjust.rs:449–473` is absent. That leaves
`criteriaratio` as the only live fuel effect on the parent, applied exactly
once.

### 2.3 Everything downstream lives on (cohort × supplied formulation)

`adjust.rs:206–262` expands one base rate into one rate **per formulation** the
county is supplied for that fuel type, and `aggregate.rs:28–45` re-collapses by
market share. Every ratio in §§2.4–2.5 keys on the formulation or on its fuel
subtype, so all of them belong inside that expansion, and the collapse happens
**once, at the end**:

```
rt_fuelFactor[pp] = SUM over supplied formulations f of
                        ( marketShare_f x criteriaRatio_f x speciationChain_f[pp] )
```

with `speciationChain[101] = 1`, so the parent's `rt_fuelFactor` is exactly the
`rt_criteriaFactor` of `docs/process-nox-speciation.md` §2.3. Writing the
collapse anywhere earlier would be wrong in general — `criteriaRatio_f` and the
speciation ratios both vary by formulation, and the product of the means is not
the mean of the products — and would be *indistinguishable* here, because each
of this county's four fuel types is supplied by exactly one formulation at
market share 1.0 (§7.2).

**Which formulations.** As `docs/process-nox-speciation.md` §2.3: `fuelsupply`
is keyed by `fuelRegionID`, `regioncounty` is consumed as a **presence flag and
not a join** (`docs/esm-conventions.md` §30.5), and the formulation resolves to
a fuel type through `fuelformulation.fuelSubtypeID` and `fuelsubtype.fuelTypeID`.
Four of the five supplied formulations resolve:

| formulation | subtype | fuel type | market share |
|---|---|---|---|
| 90 | 90 Electricity | 9 | 1.0 |
| 9114 | **12 Gasohol (E10)** | 1 | 1.0 |
| 25003 | **21 Biodiesel Blend** | 2 | 1.0 |
| 27002 | **51 Ethanol (E85)** | 5 | 1.0 |
| 28001 | 30 — absent from `fuelsubtype` | 0 | — |

The subtypes in bold are the ones §2.4 and §2.5 key on, and none of them is the
fuel type's *default* formulation (`neededfuelsupply` names 10, 20, 50 and 90).
A document that keyed on the default would get the same answer here and be wrong
elsewhere; §7.2 records that it cannot be distinguished.

### 2.4 `HCSpeciationCalculator`, which is not a chained calculator

`hcspeciation.rs::speciate_emission` takes **one THC emission** and returns up to
five species from it in a single pass. It reads no `RunSpecChainedTo`; the
module has no such table. For the two species this run selects:

```
r      = methaneTHCRatio.CH4THCRatio          key (processID, fuelSubtypeID, regClassID, modelYear in [begin, end])
factor = speciationConstant + oxySpeciation x volToWtPercentOxy x totalOxygenate
                                              key (polProcessID 8701, fuelSubtypeID, regClassID, modelYear in [begin, end])
NMHC (79) = THC  x (1 - r)
VOC  (87) = NMHC x factor
```

`totalOxygenate` is the formulation's `MTBEVolume + ETBEVolume + TAMEVolume +
ETOHVolume`. Both lookups are **inner**: a key with no row produces no output
row, which is `hcspeciation.rs:602–615`'s documented divergence from the Go
reference (the Go emits a zero; canonical's `INNER JOIN` emits nothing, and the
port follows canonical because the Go form regressed `process-refueling`).

The two tables' values for this county's three combusting subtypes:

| fuel type | subtype | model years | `CH4THCRatio` | `speciationConstant` |
|---|---|---|---|---|
| 1 | 12 | ≤ 2000 | 0.146 | 1.008 |
| 1 | 12 | ≥ 2001 | 0.338 | 0.974 |
| 2 | 21 | ≤ 2006 | 0.000 | 1.145 |
| 2 | 21 | 2007–2009 | 0.589 | 1.285 |
| 2 | 21 | ≥ 2010 | 0.380 | 0.965 |
| 5 | 51 | all | 0.822 | 0.934 |
| 9 | 90 | — | *no row* | *no row* |

`oxySpeciation` is 0 on every one of the 136 `hcspeciation` rows, so the
oxygenate term never leaves the speciation constant here — it is written because
the source writes it, and §7.2 records that it is untested even though the
formulations' oxygenate volumes are non-zero (formulation 9114 is 10 % ethanol).

#### 2.4.1 The E85 `altTHC` branch, which is worth a factor of 3.85

`adjust.rs::build_e85_block` (`:625–692`): for process 1 or 2, model year ≥ 2001
and a formulation whose subtype is 51 or 52, MOVES emits a **second fuel block**
carrying the already-criteria-adjusted rate scaled by

```
altRatio / ratio        both blended by GPAFract, from altCriteriaRatio and criteriaRatio
```

and re-tagged pollutant `1 + 10000 = 10001`. `hcspeciation.rs:715-760` then
speciates that block with the **E10 subtype (12)** rather than the emission's
own, because such vehicles burn E10-like blends in practice — while the ordinary
THC block still yields the NMHC that is *output*. The two paths are mutually
exclusive per emission (`is_ethanol_alt_case` suppresses the ordinary VOC), so
nothing is double counted. For this county:

```
altRatio / ratio = 0.640730021747 / 0.644982407884 = 0.99340697...   (MY 2001-2016)
                 = 1.037215919005 / 1.044099696019 = 0.99340697...   (MY 2017-2020)
VOC = THC x (altRatio/ratio) x (1 - 0.338) x 0.974
    = THC x 0.640536                        vs. the ordinary THC x 0.178 x 0.934 = THC x 0.166252
```

a ratio of **3.8528**, identical on all **20** of the run's ethanol cohorts
that are model year 2001 or later — the two criteria ratios move together, so
the quotient is the same on both of its bands. The other three ethanol cohorts,
model years 1998–2000, take the ordinary path. It is asserted in §6.5 on the
tables rather than on the answer, so the branch cannot be mistaken for a no-op.

If either `criteriaratio` or `altcriteriaratio` lacked a row the block would not
be built (`adjust.rs:651` needs both), the ordinary VOC would already have been
suppressed, and the cohort would emit **no VOC row at all** — a third way for a
species cohort to disappear, and one this snapshot does not exercise.

### 2.5 `AirToxicsCalculator`, which is

`airtoxics.rs::air_toxics_block` runs six independent paths and gates each on
`flag && !table.is_empty()`. **Two are live here**, and both are `ATRatio*`
chained-to paths: a `runspecchainedto` row maps the input block's `polProcessID`
to the toxic `(polProcessID, pollutantID, processID)` it produces, and the ratio
table supplies the multiplier.

| path | source | ratio key | which cohorts it reaches here |
|---|---|---|---|
| `ATRatioGas1` | `:784–800` | emission's **fuelFormulationID**, block month, block model year, output pol-process | gasoline, all 41 model years; E85 2001–2020 |
| `ATRatioNonGas` | `:833–856` | output pol-process, block **sourceTypeID**, emission's **fuelSubtypeID**, block model year | diesel, all 40; E85 1998–2000 |

Both extracts resolve their raw table to a single model year before the
calculator sees it, and the two resolutions are different:

* `atratio` carries `(minModelYearID, maxModelYearID, ageID, monthGroupID)` and
  `synthesize_at_ratio` (`:2154–2245`) sets **`modelYearID = year - ageID`**,
  keeps the row only when that year is inside `[min, max]`, and joins
  `FuelSupply → MonthOfAnyYear` to give the row its `monthID`. So the 41 rows of
  the 1980–2000 window are ages 40 down to 0 and only ages 20–40 survive, while
  the 2001–2060 window's 20 rows are ages 19–0 and all survive. The two windows
  partition the run's model years exactly.
* `atrationongas` carries a self-describing `modelYearGroupID` and
  `synthesize_at_ratio_non_gas` (`:2077–2116`) decodes it as
  `(g / 10000, g % 10000)` and expands to every model year in
  `[max(start, year-40), min(end, year)]`. **No `pollutantprocessmappedmodelyear`
  join** — unlike `nono2ratio` in `docs/process-nox-speciation.md` §2.5, this
  group is read, not looked up.

The three ratios that result, by fuel type:

| model years | path | benzene (2001) | 1,3-butadiene (2401) | formaldehyde (2501) |
|---|---|---|---|---|
| gasoline 1980–1995 (ages 25–40) | gas1 | 0.037092331652 | 0.005724373282 | 0.014317289786 |
| gasoline 1996–2000 (ages 24–20) | gas1 | 0.037226809842 … 0.037784194104 | 0.005745721828 … 0.005834207398 | 0.014321218453 … 0.014337505463 |
| gasoline ≥ 2001 (ages 19–0) | gas1 | 0.047131980205 | **0.0** | 0.015083067732 |
| diesel ≤ 2006 | non-gas | 0.007835437544 | 0.002917763079 | 0.078225277364 |
| diesel 2007–2009 | non-gas | 0.012900000438 | 0.000799999980 | 0.217399999499 |
| diesel ≥ 2010 | non-gas | **0.0** | **0.0** | 0.026600000000 |
| E85 1998–2000 | non-gas | 0.017000000924 | 0.001099999994 | 0.029100000858 |
| E85 ≥ 2001 | gas1 | 0.031446464484 | **0.0** | 0.023712512447 |

The gasoline 1996–2000 band is where §3.2's `ageID` key earns its place: those
five model years take five *different* ratios out of one `(min, max)` window
whose other sixteen ages are identical, so a document that matched the window and
not the age would be right on 36 of the 41 gasoline cohorts.

A zero ratio emits a row carrying zero; only a *missing* ratio drops one. **160**
of the 1,288 emitted cells are exactly 0.000000000000 — 40 electricity THC, 40
gasoline and 40 E85 butadiene, and 20 diesel benzene and 20 diesel butadiene —
and every one of them is a row the comparison checks.

The Go's `add_chained_emission` **appends**: when two ratio rows name the same
output pollutant, both scaled emissions are kept and the output aggregation sums
them. This document therefore writes the two paths as a **sum**, not as an
either/or. Here they are disjoint on every emitted cohort (§6.5 asserts it), so
the sum has exactly one live term — but a fixture is not a licence to write the
narrower form.

### 2.6 Survival down a three-level chain

`docs/esm-conventions.md` §30.2's rule — a chained row exists where its ratio
exists **and its parent row does** — generalises to depth 3 by iterating the
same self-join rather than by widening it. With
`rt_hasChainRatio` the per-pollutant-process existence half:

```
rt_survives      = rt_isSelected x rt_hasRate                   -- depth 0, 101 only
rt_emitsAtDepthN = rt_hasChainRatio x parent(previous arm)      -- N = 1, 2, 3
rt_emits         = rt_survives + rt_emitsAtDepth1 + rt_emitsAtDepth2 + rt_emitsAtDepth3
```

where `parent(x)` is the self-join on
`(rt_chainInputPolProcessID ↔ rt_polProcessID, rt_cohortOrdinal ↔ rt_cohortOrdinal)`
— the same pair `docs/process-crankcase-running.md` uses at depth 1, applied
three times. The sum is safe because each pollutant-process sits at exactly one
depth, so at most one term is non-zero on any row; the fixture asserts that by
counting each `rt_emitsAtDepthN` separately, and `rspp_chainDepth` -- 0, 3, 3,
3, 1, 2 in the table's own row order -- pins which depth each one sits at.

`rt_hasChainRatio` is where the two calculators differ again:

| pol-process | depth | existence test |
|---|---|---|
| 7901 NMHC | 1 | some supplied formulation has a `methanethcratio` row |
| 8701 VOC | 2 | some supplied formulation has an `hcspeciation` row **and** the methane ratio of whichever subtype its path uses — its own on the ordinary path, subtype 12 on the `altTHC` one |
| 2001 / 2401 / 2501 | 3 | some supplied formulation has an `atratio` **or** an `atrationongas` row |

Electricity fails the first test and everything downstream inherits the failure,
which is why all five species blocks drop exactly the same twenty cohorts.
`run-airtoxics-oracle.sh` asserts both that fact and that each species set is a
**strict subset** of the parent's, because "104" alone is compatible with
dropping the wrong twenty.

**The chain does two different jobs here and only one of them is the
quantity.** The SURVIVAL rule above iterates over all three levels, because a
toxic row's existence depends on the VOC row's, which depends on the NMHC row's.
The QUANTITY does not: §2.4 computes NMHC and VOC from the THC block in one
stage, as `hcspeciation.rs` does, so only the toxics' multiplier reaches back
through `parent(...)` — for the VOC factor it scales. Writing the quantity
through all three levels instead would force VOC to be `NMHC × ratio`, and on
the `altTHC` path the operand is `altNMHC` and not the emitted NMHC, so it would
need `(1 − CH4THCRatio)` divided back out: a division by a table value that
neither source performs (`docs/esm-conventions.md` §32.4).

---

## 3. Join structure

### 3.1 The joins this fixture adds

| # | left | right | key pairs | semiring |
|---|---|---|---|---|
| J41 | `rate_rows` × `fuelsupply_rows` | `methanethcratio_rows` | process; fuel subtype; regClass; **model-year range** | sum-product / max |
| J42 | `rate_rows` × `fuelsupply_rows` | `hcspeciation_rows` | polProcess (8701); fuel subtype; regClass; **model-year range** | sum-product / max |
| J43 | `rate_rows` × `fuelsupply_rows` | `altcriteriaratio_rows` | formulation; polProcess, modelYear, ageID; sourceType | sum-product / max |
| J44 | `rate_rows` × `fuelsupply_rows` | `atratio_rows` | formulation; polProcess; **ageID**; the resolved model year in range | sum-product / max |
| J45 | `rate_rows` × `fuelsupply_rows` | `atrationongas_rows` | polProcess; sourceType; fuel subtype; **decoded model-year group** | sum-product / max |
| J46 | `fuelsupply_rows` | `fuelformulation_rows` | formulation → the four oxygenate volumes and `volToWtPercentOxy` | sum-product |
| J47 | `rate_rows` | `rate_rows` (self) | chainInputPolProcess ↔ polProcess, cohortOrdinal ↔ cohortOrdinal | sum-product, **three times** |

J47 is `docs/process-crankcase-running.md`'s J38 applied at three depths; J41–J45
all live on the (rate row × supplied formulation) relation `rtSup_*` that
`criteriaratio` already established, so no new relation shape is introduced
either.

### 3.2 The model-year predicates are three different things

Worth separating, because all three read as "the model year matches":

* **an inclusive band on the row** — `methanethcratio`, `hcspeciation`:
  `lib/keys.esm`'s `model_year_in_range`, which delegates to
  `in_inclusive_range`;
* **an age identity plus a band** — `atratio`: the row's `ageID` must equal the
  cohort's `YEAR − modelYearID` *and* the resulting year must be in the band. The
  age is a join key, the band is the range predicate, and a document that read
  the band alone would match 41 rows where MOVES matches one;
* **a decoded group** — `atrationongas`: `floor(g / 10000)` and `g mod 10000` are
  the band's endpoints, so the same `in_inclusive_range` applies to a pair of
  values computed from the key column rather than read from two columns.

Only the second is new; the third is `lib/keys.esm`'s
`model_year_in_group` (§4).

### 3.3 One rank, over the whole rate relation

`docs/esm-conventions.md` §31, unchanged: `rt_emits` is the mask,
`rt_prefixEmitted` an inclusive prefix count over all 984 candidates giving a
dense 1..644, and the output relation is 644 × 2 with the pollutant-process read
*back* through the rank join like every other key. `n_outputRateRow` = 644 is the
one declared number; `run_outputRateRowCount` recomputes it and
`pp_emittedCohortCount` recomputes the 124 and the five 104s separately — which
matters, because 124 + 104 × 5 and 129 + 103 × 5 are both 644. The flat
(rate row, day type) product is decoded with `lib/keys.esm`'s
`flat_relation_major` and `flat_relation_minor`.

---

## 4. Reusable shapes

Two new expression templates, both forms and no coefficients
(`docs/esm-conventions.md` §24):

| template | file | source | why it is shared |
|---|---|---|---|
| `model_year_in_group` | `lib/keys.esm` | `airtoxics.rs::decode_model_year_group` | a self-describing `beginYYYYendYYYY` group appears in `atrationongas`, `pahgasratio` and `minorhapratio`, and the two endpoints must be decoded from one shared floor division or they can disagree about where a group ends. Layered as `flat_relation_minor` is on `flat_relation_block_index`: `model_year_group_last` is written in terms of `model_year_group_first`, and the comparison delegates to `in_inclusive_range` |
| `speciation_factor` | `lib/adjustments.esm` | `hcspeciation.rs:616–617` | `speciationConstant + oxySpeciation × volToWtPercentOxy × totalOxygenate` is the NMOG and the VOC factor both; written twice they can disagree about which term the oxygenate multiplies |

Everything else is instantiated rather than re-spelled: `lib/keys.esm`'s
`in_inclusive_range`, `model_year_in_range`, `flat_relation_major` and
`flat_relation_minor`; `lib/adjustments.esm`'s `exact_else_wildcard`,
`gpa_blend` and `quadratic_temperature_adjustment`;
`lib/identifiers.esm`'s `pol_process_id`, `pollutant_id_of`, `process_id_of` and
`null_output_column`; `lib/onroad_activity.esm`'s `onroad_scc`,
`weeks_per_month`, `share_of_group` and `source_bin_slot`; and the whole of
`lib/drive_cycle.esm`.

---

## 5. Literals and enums

`enums` gains four members and loses three. Added: `pollutant.NonMethaneHydrocarbons`
(79), because `hcspeciation.rs` names it as a constant (`NMHC_POLLUTANT_ID`) and
the methane complement is keyed by no table that could identify the row;
`fuel_subtype.Gasohol10` (12), `.EthanolE85` (51) and `.EthanolE70` (52), which
are `hcspeciation.rs`'s `E10_FUEL_SUBTYPE_ID` and `E70_E85_FUEL_SUBTYPE_IDS` and
`adjust.rs:640`'s subtype test; `model_year.AltThcFirst` (2001), which is
`adjust.rs`'s `ALT_THC_MIN_MODEL_YEAR`; and `process.StartExhaust` (2), named
although this run selects only running exhaust because `adjust.rs:626` gates the
altTHC block on both. Removed with the branches that used them:
`humidity_equation.CFR86` / `.CFR1065`, `pollutant.OxidesOfNitrogen`,
`pollutant.CarbonMonoxide` and `process.CrankcaseRunningExhaust`.

**No pollutant is named where a join can find it.** VOC (87) appears nowhere in
the document: `hcspeciation` is keyed by the *output* pollutant-process, so
joining a rate row's own `polProcessID` to it identifies the VOC rows and finds
their constants in one clause. Benzene, 1,3-butadiene and formaldehyde likewise
appear nowhere — `atratio` and `atrationongas` carry their pol-processes and
`runspecchainedto` carries the chain. Only NMHC needs a name, and only because
its table has no pollutant-process column to give it one.

**The bare numeric literals are the same seven values as
`process-crankcase-running`'s and `process-nox-speciation`'s**, measured over
every equation of all three: 0, 0.5 and 1 (masks, comparisons and the
multiplicative identity); 2 and 3 (the drive cycle's second offsets, and the
chain-depth labels of `rspp_chainDepth`); 10 (the decimal-slot exponent
`source_bin_slot` raises); and 1000 (`countyID / 1000`, the state id). The 75 of
the temperature quadratic, the 10.71 of the humidity reference and the 10000 of
a self-described model-year group all live inside the templates that own them.

---

## 6. Hand-checkable worked examples

### 6.0 Run-level values used by every example

```
temperature       59.5 degF         heatIndex     59.5 degF
GPAFract          0.0               acActivity    0.0 (raw -0.296982, clamped)
temperatureFactor 1.0 exactly on every row (temperatureadjustment is EMPTY)
```

### 6.1 Worked example A — MY 1980, gasoline, weekend

`baseratebyage_1_2020` hourDayID 72 carries meanBaseRate 84.6858 and
meanBaseRateACAdj 19.3359; `rt_acFactor` is 0, so the A/C companion contributes
nothing. `criteriaratio` for formulation 9114, polProcess 101, source type 21,
model year 1980, age 40 supplies the fuel effect, and the temperature factor is
1.

```
THC   =                                                          94.513
NMHC  = 94.513 x (1 - 0.146)          = 80.7141      MOVESOutput: 80.714100000000
VOC   = 80.7141 x 1.008               = 81.3598      MOVESOutput: 81.359800000000
C6H6  = 81.3598 x 0.037092            =  3.01780     MOVESOutput:  3.017830000000
C4H6  = 81.3598 x 0.005724            =  0.465704    MOVESOutput:  0.465734000000
HCHO  = 81.3598 x 0.014317            =  1.16483     MOVESOutput:  1.164850000000
```

The three toxic ratios are read at ageID 40 out of `atratio`'s 1980–2000 window;
this is the row that pins §3.2's second predicate, because age 40 and age 0 of
that window are 0.037092 and 0.042119 respectively.

### 6.2 Worked example B — MY 2020, gasoline, weekday, and a zero that is emitted

```
THC   = 26.2569
NMHC  = 26.2569 x (1 - 0.338)         = 17.3821      MOVESOutput: 17.382100000000
VOC   = 17.3821 x 0.974               = 16.9302      MOVESOutput: 16.930200000000
C6H6  = 16.9302 x 0.047132            =  0.797952    MOVESOutput:  0.797952000000
C4H6  = 16.9302 x 0.000000            =  0           MOVESOutput:  0.000000000000  <- row PRESENT
HCHO  = 16.9302 x 0.015083            =  0.255359    MOVESOutput:  0.255359000000
```

### 6.3 Worked example C — MY 2020, E85, weekday, the `altTHC` branch

```
THC       = 0.00881415
NMHC      = 0.00881415 x (1 - 0.822)                       = 0.00156892
altTHC    = 0.00881415 x (1.037215919005 / 1.044099696019) = 0.00875604
VOC       = 0.00875604 x (1 - 0.338) x 0.974               = 0.00564579
                                              MOVESOutput: 0.005645790000
```

The ordinary path would have given `0.00156892 x 0.934 = 0.00146537`, low by the
3.8528 of §2.4.1. **NMHC is larger than nothing and smaller than VOC on this
row** — `VOC / NMHC = 3.5985` — which cannot happen on the ordinary path, where
`speciationConstant` is 0.934, and is the visible signature of the branch.

### 6.4 Worked example D — the three absences

```
MY 2020, electricity   THC 0.000000000000 emitted; five species rows ABSENT
                       (no methaneTHCRatio row for fuel subtype 90)
MY 2000, electricity   ABSENT in every block
                       (no emissionratebyage ageGroup-2099 row for fuel type 9)
MY 2020, diesel        ABSENT in every block
                       (not a selected cohort: no 2020 diesel stmyFraction)
```

Three absences with three different causes, and a zero that is emitted. Between
them they are the whole of §0.2.

### 6.5 The reproduction script

Extracted and run by `./run-airtoxics-oracle.sh`. It reads only the input tables
of §1, computes S1–S18 for the THC parent, then the two speciation stages, and
**asserts** its worst relative error against `sho`, against
`baseratebyage_1_2020` and against `MOVESOutput`, plus the key set per
pollutant-process and six things a comparison against `MOVESOutput` could not
see.

```python
#!/usr/bin/env python3
"""process-airtoxics reproduction from the snapshot's own input tables."""
import sys, collections, math
import pyarrow.parquet as pq

SNAP = sys.argv[1]
P = SNAP + "/tables/db__movesexecution1ccc0232_campuscluster_illinois_edu__"
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
# ---- the THC parent, kept per fuel FORMULATION ---------------------------
# Every downstream ratio keys on the formulation or on its fuel subtype, and
# the E85 altTHC branch divides the criteria ratio back out, so the parent is
# carried as a per-formulation slice and summed only where a row is emitted.
pol,proc=PPA[THCPP]
coh=cohorts(THCPP)
sbaf=rebase(coh)
rate=rates_by_age(THCPP)
modes=sorted({k[4] for k in rate})
sbw=collections.defaultdict(float); sbwac=collections.defaultdict(float)
for (my,fuel,et,rc),frac in sbaf.items():
    smy=shortgroup[mygroup[(THCPP,my)]]
    ag=agegroup[YEAR-my]
    ev=evsf(THCPP,my,fuel,rc)
    for om in modes:
        r=rate.get((fuel,et,rc,smy,om,ag))
        if r is None: continue
        sbw[(my,fuel,om)]+=frac*r*ev
        sbwac[(my,fuel,om)]+=frac*r*ev*(FAC.get(om,1.0)-1.0)
br=collections.defaultdict(float); brac=collections.defaultdict(float)
for (my,fuel,om),v in sbw.items():
    for d in DAYS: br[(HD[d],my,fuel)]+=v*W[(HD[d],om)]
for (my,fuel,om),v in sbwac.items():
    for d in DAYS: brac[(HD[d],my,fuel)]+=v*W[(HD[d],om)]
have={(k[0],k[1],k[2],k[3],k[5]) for k in rate}
thc=collections.defaultdict(dict)      # (day, my, fuel) -> {formulation: quantity}
REGCLASS={}
for (my,fuel,et,rc),frac in coh.items():
    age=YEAR-my
    smy=shortgroup[mygroup[(THCPP,my)]]
    if (fuel,et,rc,smy,agegroup[age]) not in have: continue
    acf=ACACT*ACPEN[my]*ACFUNC[age]
    tf=temp_factor(THCPP,fuel,rc,my)
    REGCLASS[(my,fuel)]=rc
    for d in DAYS:
        base_r=br[(HD[d],my,fuel)]+acf*brac[(HD[d],my,fuel)]
        act=sho[(HD[d],age)]/realdays[d]
        for ff,share in supply.get(fuel,[]):
            thc[(d,my,fuel)][ff]=share*base_r*crit(THCPP,ff,my,age)*tf*act
assert len({(k[0],k[1]) for k in coh})==len(coh), "one (modelYear, fuelType) per cohort"
# ---- HCSpeciationCalculator: NMHC (79) and VOC (87) from THC --------------
# hcspeciation.rs::speciate_emission. Methane (5), NMOG (80) and TOG (86) are
# not selected by this RunSpec and are not computed.
E10_SUBTYPE, E85_SUBTYPES, ALT_MIN_MY = 12, (50,51,52), 2001
MTHC=[r for r in T("methanethcratio")]
HCS=[r for r in T("hcspeciation")]
FFROW={r["fuelFormulationID"]:r for r in T("fuelformulation")}
def ch4(sub,rc,my):
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
NMHC_PP, VOC_PP = 7901, 8701
nmhc=collections.defaultdict(dict); voc=collections.defaultdict(dict)
for (d,my,fuel),per in thc.items():
    rc=REGCLASS[(my,fuel)]; age=YEAR-my
    for ff,q in per.items():
        sub=FFORM[ff]
        alt=(sub in E85_SUBTYPES and fuel==5 and my>=ALT_MIN_MY)
        r=ch4(sub,rc,my)
        if r is None: continue
        nmhc[(d,my,fuel)][ff]=q*(1.0-r)
        if not alt:
            f=hcfactor(VOC_PP,sub,rc,my,ff)
            if f is not None: voc[(d,my,fuel)][ff]=q*(1.0-r)*f
            continue
        # The E85 altTHC block: adjust.rs::build_e85_block scales the already
        # criteria-adjusted rate by altRatio/ratio and re-tags it pollutant
        # 10001; hcspeciation then speciates it with the E10 subtype's ratios.
        cr=blend(CR,THCPP,ff,my,age,None); ar=blend(ACR,THCPP,ff,my,age,None)
        if cr is None or ar is None: continue
        alt_q=q*(ar/cr if cr>0.0 else 0.0)
        e10=ch4(E10_SUBTYPE,rc,my)
        if e10 is None: continue
        f=hcfactor(VOC_PP,E10_SUBTYPE,rc,my,ff)
        if f is not None: voc[(d,my,fuel)][ff]=alt_q*(1.0-e10)*f
# ---- AirToxicsCalculator: the two live ratio paths off the VOC block ------
# airtoxics.rs::apply_at_ratio_gas1 and ::apply_at_ratio_non_gas. The other
# four paths are dead here: minorHAPRatio, pahGasRatio, pahParticleRatio and
# ATRatioGas2 are all empty (0 rows).
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
ATN={}
for r in T("atrationongas"):
    g=r["modelYearGroupID"]; lo,hi=g//10000,g%10000
    for my in range(max(lo,YEAR-40),min(hi,YEAR)+1):
        ATN[(r["polProcessID"],r["sourceTypeID"],r["fuelSubtypeID"],my)]=float(r["ATRatio"])
CHAINED=collections.defaultdict(list)
for c in T("runspecchainedto"):
    CHAINED[c["inputPolProcessID"]].append(
        (c["outputPolProcessID"],c["outputPollutantID"],c["outputProcessID"]))
toxic=collections.defaultdict(dict)
for (d,my,fuel),per in voc.items():
    for outpp,outpol,outproc in CHAINED[VOC_PP]:
        for ff,q in per.items():
            for r in (ATG.get((ff,MONTH,my,outpp)), ATN.get((outpp,ST,FFORM[ff],my))):
                if r is None: continue
                acc=toxic[(outpol,outproc,d,my,fuel)]
                acc[ff]=acc.get(ff,0.0)+q*r
# ---- the emitted rows ----------------------------------------------------
rows={}
def emit(pol,proc,per_cohort):
    for (d,my,fuel),per in per_cohort.items():
        if not per: continue
        rows[(pol,proc,d,my,fuel)]=(sum(per.values()),scc(fuel,proc))
emit(THC,1,thc); emit(PPA[NMHC_PP][0],1,nmhc); emit(PPA[VOC_PP][0],1,voc)
for (outpol,outproc,d,my,fuel),per in toxic.items():
    if not per: continue
    rows[(outpol,outproc,d,my,fuel)]=(sum(per.values()),scc(fuel,outproc))
# ------------------------------------------------------------------- compare
ref_sho = {(r["hourDayID"], r["ageID"]): float(r["SHO"]) for r in T("sho")}
worst_sho = max(abs(sho[k] - v) / v for k, v in ref_sho.items())
print("sho:            %3d rows, worst relative error %.3e" % (len(ref_sho), worst_sho))
assert worst_sho < 1e-5, "sho: worst relative error %.3e exceeds 1e-5" % worst_sho

ref_br = {(r["hourDayID"], r["modelYearID"], r["fuelTypeID"]): float(r["meanBaseRate"])
          for r in T("baseratebyage_1_2020")}
worst_br, n_br = 0.0, 0
for k, v in ref_br.items():
    if v == 0.0:
        assert br[k] + brac[k] == 0.0, k
        continue
    n_br += 1
    worst_br = max(worst_br, abs(br[k] - v) / v)
print("baseRateByAge:  %3d non-zero rows of %d, worst relative error %.3e"
      % (n_br, len(ref_br), worst_br))
assert worst_br < 2e-5, "baseRateByAge: worst relative error %.3e exceeds 2e-5" % worst_br

out = pq.read_table(SNAP + "/tables/db__out_process_airtoxics__movesoutput.parquet").to_pylist()
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
# ASSERTED, not merely printed (docs/esm-conventions.md 21): ./run-tests.sh reads
# this script's EXIT CODE, so a regression that leaves the key set intact and
# moves every value would otherwise be reported green with the evidence in a log.
assert not missing, missing[:8]
assert not extra, extra[:8]
assert len(rows) == len(out), (len(rows), len(out))
assert worst < 2e-5, "emissionQuant: worst relative error %.3e exceeds 2e-5" % worst

# --- the KEY SET, exactly, and not merely its size -------------------------
# A row count cannot see a ragged block set: 124 + 5 x 104 and 6 x 107.33 are
# both 644 (and 129 + 103 x 5 is 644 too). So the cohort set is asserted PER
# pollutant-process, the day-type axis separately, and their product against
# the row count.
cohorts_by_pp = collections.defaultdict(set)
days = set()
for (pol, proc, day, my, fuel) in rows:
    cohorts_by_pp[(pol, proc)].add((my, fuel))
    days.add(day)
expected_cohorts = {(1, 1): 124, (20, 1): 104, (24, 1): 104,
                    (25, 1): 104, (79, 1): 104, (87, 1): 104}
got = {k: len(v) for k, v in cohorts_by_pp.items()}
assert got == expected_cohorts, (got, expected_cohorts)
assert days == set(DAYS) and len(days) == 2, days
parent = cohorts_by_pp[(THC, 1)]
for species in (20, 24, 25, 79, 87):
    assert cohorts_by_pp[(species, 1)] < parent, species
    assert (parent - cohorts_by_pp[(species, 1)]) == \
        {c for c in parent if c[1] == ELECTRICITY}, species
assert sum(expected_cohorts.values()) * len(days) == len(out) == 1288
print("key set:       124 THC + 5 x 104 species cohorts x %d day types = %d rows, exact;"
      % (len(days), len(out)))
print("               the 20 cohorts every species drops are exactly the ELECTRICITY ones,"
      " and every species set is a strict subset of the parent's")
chained = sum(1 for (pol, _, _, _, _) in rows if pol != THC)
assert chained == 5 * 104 * len(days), chained
print("               %4d of the %d rows are SPECIATED -- computed from the 101 rows, from"
      " no rate of their own" % (chained, len(out)))

# --- what a comparison against MOVESOutput alone could not see -------------
# 1. The E85 altTHC branch is LOAD-BEARING, not a no-op. On ethanol 2001+ the
#    emitted VOC is the E10-speciated altTHC, and the ordinary path would have
#    produced a number 3.85x smaller. Checked on the tables, not on the answer.
alt_gain, alt_cohorts = None, set()
for (d, my, fuel), per in voc.items():
    if fuel != 5 or my < ALT_MIN_MY:
        continue
    for ff, q in per.items():
        rc = REGCLASS[(my, fuel)]; sub = FFORM[ff]
        ordinary = thc[(d, my, fuel)][ff] * (1.0 - ch4(sub, rc, my)) * hcfactor(VOC_PP, sub, rc, my, ff)
        g = q / ordinary
        assert alt_gain is None or abs(g - alt_gain) < 1e-9, (g, alt_gain)
        alt_gain = g
        alt_cohorts.add((my, fuel))
assert alt_gain is not None and abs(alt_gain - 1.0) > 2.0, alt_gain
assert len(alt_cohorts) == 20, len(alt_cohorts)
print("NOTE:          the E85 altTHC branch multiplies the ordinary VOC by %.4f on every"
      " ethanol 2001+ cohort," % alt_gain)
print("               so a document that skipped it would be wrong by that factor on %d of"
      " the 104 species cohorts" % len(alt_cohorts))
print("               -- the 20 of this run's 23 ethanol cohorts that are model year 2001 or"
      " later.")
# 2. The two live ATRatio paths are DISJOINT on every emitted cohort, so the
#    Go's append-both semantics (two ratio rows -> two kept emissions) is a sum
#    of exactly one term here and is not exercised.
both = [(ff, my, pp) for pp in (2001, 2401, 2501)
        for (d, my, fuel), per in voc.items() for ff in per
        if (ff, MONTH, my, pp) in ATG and (pp, ST, FFORM[ff], my) in ATN]
assert not both, both[:4]
print("NOTE:          no (formulation, model year, output) reaches BOTH ATRatioGas1 and"
      " ATRatioNonGas, so the")
print("               append-both-ratios semantics is a sum of one term and is untested.")
# 3. Diesel's two subtypes carry identical ratios, so reading the SUPPLIED
#    subtype (21, biodiesel blend) rather than the fuel type's default (20) is
#    unfalsifiable in this snapshot.
pairs = {(r["polProcessID"], r["modelYearGroupID"]): {} for r in T("atrationongas")}
for r in T("atrationongas"):
    pairs[(r["polProcessID"], r["modelYearGroupID"])][r["fuelSubtypeID"]] = float(r["ATRatio"])
assert all(v[20] == v[21] for v in pairs.values() if 20 in v and 21 in v)
assert all(v[51] == v[52] for v in pairs.values() if 51 in v and 52 in v)
print("NOTE:          atRatioNonGas is identical on fuel subtypes 20/21 and on 51/52, so"
      " reading the SUPPLIED subtype")
print("               rather than the fuel type's default cannot be distinguished here.")
# 4. oxySpeciation is 0 on every hcspeciation row, so the oxygenate term of the
#    NMOG/VOC factor never leaves the speciation constant.
assert all(float(r["oxySpeciation"]) == 0.0 for r in HCS)
assert any(float(FFROW[ff]["ETOHVolume"]) > 0.0 for ff in FORM_MONTHS)
print("NOTE:          oxySpeciation is 0 on all %d hcspeciation rows, so the"
      " volToWtPercentOxy x totalOxygenate term" % len(HCS))
print("               is written and never leaves the speciation constant, though the"
      " oxygenate volumes themselves are non-zero.")
# 5. The A/C arm is dead at this hour; assert it, so a reader cannot mistake a
#    passing comparison for a check of the 23 live fullacadjustment rows.
assert ACACT == 0.0, ACACT
assert acraw < 0.0, acraw
print("NOTE:          the A/C activity term is %.6f and clamps to 0, so the 23 live"
      " fullacadjustment rows" % acraw)
print("               (1.07956 at idle, 1.23161 elsewhere) reach no emitted number.")
# 6. Every supplied fuel type has exactly one formulation at market share 1.0.
assert {f: len(v) for f, v in supply.items()} == {1: 1, 2: 1, 5: 1, 9: 1}, supply
assert all(share == 1.0 for v in supply.values() for _, share in v), supply
print("NOTE:          each of the four fuel types is supplied by exactly one formulation at"
      " market share 1.0, so the")
print("               share weighting is a sum of one term and the ORDER of the"
      " per-formulation product is untested.")
```

Result:

```
sho:             82 rows, worst relative error 3.610e-06
baseRateByAge:  208 non-zero rows of 248, worst relative error 4.468e-06
emissionQuant: 1288 rows, 0 missing, 0 extra, worst relative error 8.100e-06 at (pollutant 20, process 1, day 2, MY 1991, fuel 2)
key set:       124 THC + 5 x 104 species cohorts x 2 day types = 1288 rows, exact;
               the 20 cohorts every species drops are exactly the ELECTRICITY ones, and every species set is a strict subset of the parent's
               1040 of the 1288 rows are SPECIATED -- computed from the 101 rows, from no rate of their own
```

### 6.6 What the fixture's inline tests check

Twelve tests and 288 assertions, none of which reads `MOVESOutput` through the
document:

| test | what it pins |
|---|---|
| run scope | year/month/hour/geography, `GPAFract`, and that `temperatureadjustment` and `generalfuelratio` are both EMPTY |
| six pollutant-processes | the scope and the five chain declarations, read from the execution database, including that 8701's input is 7901 and not 101 |
| drive-cycle scaffolding | braking thresholds read not written, one physics row, bracket weights sum to 1 |
| **selection vs survival** | 125 selected in five of the six blocks and 0 in NMHC's, 124/104/104/104/104/104 emitted, 644 total, and each depth's emission arm counted separately |
| `W` | a distribution over exactly 23 modes, at an *absolute* 1e-5 (§20.5) |
| activity | `act_sho` against the snapshot's own `sho`, which nothing here reads |
| base rate | `rtDay_meanBaseRate` and `rtDay_meanBaseRateACAdj` against `baseratebyage_1_2020` |
| criteria fuel effect | the five supplied formulations' fuel types and subtypes, and `rt_fuelFactor` on the parent |
| **temperature** | the factor is 1 on every row, and the A/C arm is asserted **dead** |
| **HC speciation** | the six `(subtype, model-year band)` pairs of `methanethcratio` and `hcspeciation`, and that fuel subtype 90 has neither |
| **the `altTHC` branch** | its five conditions, `altcriteriaratio / criteriaratio` = 0.99340697, and that the VOC multiplier on the E85 2020 cohort is 0.6405369 and not the ordinary path's 0.1662520 -- with the model year 2000 ethanol cohort asserted beside it, which takes the ordinary path |
| **the toxic ratios and output** | the `ageID` key on `atratio`, the decoded group on `atrationongas`, and cells across all six blocks |

---

## 7. Fidelity notes and tolerance

### 7.1 The measured result

1,288 of 1,288 rows, key set exact, **worst cell 8.100e-06** relative. No
tolerance override; the repository-wide `[cell] rel = 2e-5` carries about 2.5×
headroom, and this is *below* the port's previous worst (9.482e-06 in
`process-nox-speciation`) despite being three chain levels deeper.

The worst cell is **(benzene, day 2, MY 1991, diesel)**, value 0.000741552000.
That is a *chained* cell three levels from its rate, as the worst cell is in
`process-brakewear`, `process-tirewear` and `process-nox-speciation`, and for the
same arithmetic reason: it carries its parent's residual plus each ratio's own
quantisation. Measured on the four cells of that one cohort, the residual is
almost entirely inherited and barely grows:

| pollutant | reference value | relative error |
|---|---|---:|
| THC (1) | 0.082655700000 | 7.956e-06 |
| NMHC (79) | 0.082655700000 | 7.956e-06 |
| VOC (87) | 0.094640700000 | 7.148e-06 |
| benzene (20) | 0.000741552000 | **8.100e-06** |

so **the parent contributes 7.96e-06 of the 8.10e-06** and the three ratios
together contribute the remaining 1.4e-07 — NMHC's is exactly the parent's
because diesel's `CH4THCRatio` is 0 below model year 2007, and VOC's is smaller
than the parent's rather than larger. Six significant figures on 0.000741552 is
a half-ulp of 6.7e-07 relative on its own. The independent reproduction in §6.5
reports **the same 8.100e-06 at the same key** by a different route, which is
what distinguishes a storage limit from an error.

### 7.2 What this fixture cannot see, measured

Ten things are named here rather than claimed, because a passing comparison
would otherwise look like evidence for them. `docs/esm-conventions.md` §23.

1. **Four of `AirToxicsCalculator`'s six paths are dead.** `minorhapratio`,
   `pahgasratio`, `pahparticleratio` and `atratiogas2` all have 0 rows, so
   `apply_minor_hap_ratio`, `apply_pah_gas_ratio`, `apply_pah_particle_ratio` and
   `apply_at_ratio_gas2` are absent rather than exercised. Two of them
   (`pahParticleRatio`, and `SulfatePMCalculator` as the calculator's other
   upstream) need an Organic Carbon input this RunSpec does not select at all.
2. **Three of `HCSpeciationCalculator`'s five species are not selected.** Methane
   (5), NMOG (80) and TOG (86) are not in `runspecpollutantprocess`, and
   `hcspeciation` carries rows for polProcessID **8701 only** — so the NMOG
   lookup and the `TOG = NMOG + methane` sum have no rows to read. The
   `methaneTHCRatio` lookup *is* read, but only through `1 - r`; the methane
   product `THC × r` reaches nothing.
3. **The two live `ATRatio` paths are disjoint on every emitted cohort.** No
   (formulation, model year, output pol-process) matches both `atratio` and
   `atrationongas`, so the Go's append-both semantics — two ratio rows for one
   output pollutant produce two kept emissions that the output aggregation sums —
   is a sum of exactly one term here. §6.5 asserts the disjointness so the sum
   cannot be mistaken for a measured requirement.
4. **`atRatioNonGas` is identical on fuel subtypes 20/21 and on 51/52.** This
   county is supplied biodiesel blend (21) and E85 (51), not conventional diesel
   (20) or E70 (52). Reading the *supplied* subtype rather than the fuel type's
   default is therefore correct and **unfalsifiable in this snapshot**; §6.5
   asserts the identity that makes it so.
5. **`oxySpeciation` is 0 on all 136 `hcspeciation` rows**, so the
   `volToWtPercentOxy × totalOxygenate` term of the speciation factor never
   leaves the constant. The oxygenate volumes themselves are non-zero
   (formulation 9114 is 10 % ethanol, `volToWtPercentOxy` 0.3653), so the term is
   live in its inputs and dead in its coefficient — the same shape as §7.2.9.
6. **Each fuel type is supplied by exactly ONE formulation at market share 1.0**,
   so §2.3's re-collapse is a sum of one term and the **order** of the
   per-formulation product against the market-share sum is untested. The document
   writes the source's order.
7. **The A/C arm is live in its tables and dead in its result.**
   `fullacadjustment` has 23 real `polProcessID` 101 rows (1.07956 at idle,
   1.23161 elsewhere) and `rtDay_meanBaseRateACAdj` is a real number pinned
   against `baseratebyage_1_2020` — but the A/C *activity* quadratic is −0.296982
   at this heat index and clamps to 0, so `rt_acFactor` is exactly 0 and none of
   it reaches an emitted number.
8. **The temperature stage is absent, not merely inert.**
   `temperatureadjustment` has 0 rows, so unlike `process-nox-speciation` — where
   the term was 0 but the humidity factor was live — the whole factor is exactly
   1 on every row. The fall-through quadratic and the `exact_else_wildcard`
   precedence are written and reach no number.
9. **`imcoverage`, `emissionrateadjustment`, `evefficiency`, `generalfuelratio`
   and `generalfuelratioexpression`'s evaluation** are all absent for the reasons
   `docs/process-nox-speciation.md` §7.2 gives, and `GPAFract` is 0 so every
   fuel-effect blend selects its normal arm.
10. **The `altTHC` branch's own miss is not exercised.** `adjust.rs:651` needs
    *both* an `altcriteriaratio` and a `criteriaratio` row; when either is
    missing, the E85 block is not built, the ordinary VOC has already been
    suppressed by `is_ethanol_alt_case`, and the cohort emits **no VOC row** — a
    third way for a species cohort to disappear. All 20 E85 model years 2001–2020
    have both rows, so this fixture cannot distinguish that arm from one that
    falls back to the ordinary path.

### 7.3 Precision-sensitive operations, ranked

1. **The three-multiply chain.** A benzene cell is
   `THC × (1−r) × factor × atRatio`, four stored decimals in series. Each
   contributes its own quantisation, and §7.1's worst cell is where the parent's
   own 7.96e-06 lands on the smallest of the three toxics.
2. **`altRatio / ratio`** — a quotient of two twelve-decimal stored values whose
   result is 0.99340697. It is a well-conditioned ratio (both operands near 1,
   and near each other), which is why the E85 block does not dominate §7.1
   despite carrying one more operation than any other cell.
3. **`rt_fuelFactor`** — twelve stored decimal places, applied multiplicatively,
   as in every criteria-pollutant rung.
4. **The A/C clamp** — inert at −0.296982, and 0.3 further up the heat index it
   would not be.

---

## 8. Gaps and things not verified

* **`FuelEffectsGenerator` is not ported.** `criteriaratio`, `altcriteriaratio`
  and `atratio` are read as the captured inputs they are on this path (§1.3).
  Porting it means an expression evaluator over `generalfuelratioexpression`'s
  93 strings *and* the Complex + sulfur model, and the calculator path in §0 does
  not claim it. The snapshot's `tempairtoxicsa` / `tempairtoxicsavoc` /
  `tempairtoxicsanonvoc` are that generator's scratch and are named here only so
  a reader does not mistake them for `AirToxicsCalculator`'s.
* **One process, one source type, one road type.** `HCSpeciationCalculator`
  registers 40 pairs across nine processes and `AirToxicsCalculator` 195; this
  fixture exercises five of them, all on running exhaust.
* **The chain is three levels and MOVES has four.**
  `TOGSpeciationCalculator` chains off `HCSpeciationCalculator`'s TOG, which
  this run does not select; §2.6's iteration would extend to it by adding one
  term, which is untested.
* **`ATRatioCV`, `ATRatioNonGas.ATRatioCV`, `dataSourceId` and
  `ratioNoSulfur`** are uncertainty/provenance columns and are not modelled,
  matching `airtoxics.rs` and `adjust.rs`.
* **A fuel type with no supply row** would be zeroed here and dropped there, the
  same divergence `docs/process-nox-speciation.md` §8 records. All four of this
  run's fuel types are supplied.
* **`monthofanyyear` is assumed one month per month GROUP**, as
  `synthesize_at_ratio`'s `months_of_group` map and
  `baseratecalculator/mod.rs:1163` both assume. It holds in this snapshot
  (group 8 → month 8).
* **The two calculators' output ORDER is not modelled and could not be.** Both
  Go workers grouped their outputs in a `map`, and both ports sort by pollutant
  id to be deterministic; a fuel-block set is unordered, so nothing downstream of
  either could see the difference and neither can this fixture.
* **`atbaseemissions`, `tempairtoxicsa`, `tempairtoxicsavoc` and
  `tempairtoxicsanonvoc` are read by nothing**, which is a claim about
  `FuelEffectsGenerator`'s boundary rather than a measurement of this chain. It
  rests on `airtoxics.rs` naming none of them among its inputs.

---

## 9. Summary for the `.esm` author

Start from `fixtures/process-crankcase-running.esm`. Keep everything through
`rt_fuelFactor` and the global rank; the THC parent's 248 rows are byte-identical
to that fixture's process-1 block, so any disagreement there is a regression in
shared logic and not a new-fixture problem. Then:

1. drop the NOx branch, the humidity arms and `noxhumidityadjust`; the
   temperature factor is the fall-through quadratic over an EMPTY
   `temperatureadjustment` and is 1 everywhere (§2.2);
2. keep `generalfuelratio` as a source even though it has 0 rows here, and
   assert `run_generalFuelRatioReach` is 0 — an empty table and an unwritten
   step look the same from the answer, and an index set of extent 0 evaluates
   (a sum over it is the semiring identity), so the step can be written;
3. put the two HC-speciation ratios and the two air-toxic ratios on the
   **(rate row × supplied formulation)** relation `criteriaratio` already lives
   on, and collapse by market share exactly once, at the end (§2.3);
4. write `HCSpeciationCalculator` as a direct multi-output stage — it reads no
   `RunSpecChainedTo` — and `AirToxicsCalculator` as a chained self-join off the
   VOC block, which does (§2.4, §2.5);
5. add the E85 `altTHC` branch between them, keyed on fuel subtype 51/52,
   process 1/2 and model year ≥ 2001, and speciating with the **E10** subtype
   (§2.4.1);
6. iterate `docs/esm-conventions.md` §30.2's parent-survival self-join three
   times rather than widening it, and count each depth separately (§2.6);
7. key `atratio` on `ageID` as well as on the model-year window (§3.2), and
   decode `atrationongas`'s group with `lib/keys.esm`'s new
   `model_year_in_group`.
