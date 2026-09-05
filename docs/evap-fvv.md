# `process-evap-fvv` — computation specification

The fifth port specification in this repository, and the third of PLAN.md §3
Phase 4. Its siblings are `docs/nonroad-logging-county.md` (a Fortran chain),
`docs/mixed-onroad.md` (a rates-first SQL chain), `docs/evap-leaks.md` (the SQL
*inventory* chain this one is a variant of) and `docs/evap-permeation.md`.

What it specifies: how canonical MOVES turns the `process-evap-fvv` snapshot's
input tables into its 128 rows of `MOVESOutput`; which parts of that this port
computes; and an independent reproduction (`./run-fvv-oracle.sh`, §6.5) whose
numbers can be checked against the snapshot without reading this file.

**Read §0.3 first if you are here because `docs/evap-permeation.md` §0.3 said
this slice would exercise `TankTemperatureGenerator`'s quarter-hour
recurrence.** It does not. That claim was an inference from the *structure* of
`MultidayTankVaporVentingCalculator` and it is wrong on *this snapshot*, for
the same reason permeation was: the soak operating modes carry an
`opModeFraction` of exactly zero. §0.3 measures it, and unlike permeation's §0.3
the measurement here is made against a reproduction that computes the whole
venting chain rather than one that skips it.

Sources, in the order they were trusted:

1. `../moves.rs/crates/moves-calculators/src/calculators/multiday_tank_vapor_venting_calculator.rs`
   — the port of `MultidayTankVaporVentingCalculator.sql`, with `INPUT_TABLES`
   declared and the SQL step labels TVV-1 … TVV-9 preserved.
2. `.../generators/tank_fuel_generator.rs` — TFG-1a … TFG-3b, which produce
   `AverageTankGasoline`.
3. `.../generators/tank_temperature_generator.rs` — TTG-1, whose
   `ColdSoakTankTemperature` TVV-2 and TVV-3 read; and TTG-6/TTG-7, which
   produce `SoakActivityFraction` and `ColdSoakInitialHourFraction`.
4. `.../generators/evap_op_mode_distribution.rs`,
   `.../generators/totalactivitygenerator/`,
   `.../generators/source_bin_distribution_generator.rs` — the same three
   generators `docs/evap-leaks.md` specifies, which this slice reuses in full.
5. The snapshot itself: 384 declared tables, **252 non-empty**, plus the
   expected `MOVESOutput`.

---

## 0. The fixture at a glance

| | |
|---|---|
| snapshot | `../moves.rs/characterization/snapshots/process-evap-fvv` |
| output database | `out_process_evap_fvv` |
| `MOVESOutput` rows | **128** |
| pollutant / process | THC (1) × Evap Fuel Vapor Venting (12); `polProcessID` **112** |
| calculator | `TankVaporVentingCalculator`, running its **multi-day** SQL script |
| year / month / hour | 2020 / 8 / 7 |
| day types | 2 (weekend) and 5 (weekday) — `hourDayID` 72 and 75 |
| county / zone / link | 26161 (Washtenaw, MI) / 261610 / 2616104 |
| link road type | 4, Urban Restricted Access — an on-network link |
| source type | 21, Passenger Car |
| emitted mass | **558.971807 g THC** |

The run scope, the geography, the activity chain, the cohort structure and the
operating-mode distribution are **identical** to `process-evap-leaks` and
`process-evap-permeation`. The calculator is much larger than either: nine
numbered steps, a soak-day recurrence, and two generators (`TankFuelGenerator`,
`TankTemperatureGenerator`) upstream of it.

This slice emits **17× the mass of the leaks slice and permeation combined**
(559 g against 32 g and 128 g), because fuel vapour venting is the dominant
evaporative process for a running vehicle.

### 0.1 What is the same as the other two evaporative slices, and what is not

Same: §0.1 of `docs/evap-permeation.md` (the RunSpec-versus-execution-database
rule), A1–A10, C1–C4 and E1–E3, and the 128-row key set — 41 gasoline model
years × 2 day types plus 23 E85 model years × 2 day types.

Different, and each of these is a section below:

| | |
|---|---|
| `isRegClassReqd` | **`'Y'`** — like leaks, unlike permeation, so the source bins keep `regClassID` (§2.2 C2′) |
| the SCC process suffix | `…12`, so `2201210412` and `2205210412` |
| `TankFuelGenerator` | new; §2.5. `averageTankGasoline` is captured **empty** and must be computed |
| `TankTemperatureGenerator` TTG-1 | reused from `components/tank_temperature.esm`; §2.4 |
| the calculator | `MultidayTankVaporVentingCalculator`, §2.6–§2.14 — the largest calculator SQL file in MOVES |
| the temperature / RVP adjustment | new; TVV-8, §2.13. **The only place `AverageTankGasoline` is load-bearing here** |

### 0.2 Why 128 rows

Exactly the leaks slice's key set, for exactly the reasons `docs/evap-leaks.md`
§0.2 gives: `emissionRateByAge` carries rows for the 22 gasoline and 19 E85
source bins and for none of the 39 diesel or electricity bins, so TVV-8's
`SourceBin` join removes them. 41 gasoline model years and 23 E85 model years,
each on two day types.

### 0.3 What this slice was chosen to establish, and what it actually established

`docs/evap-permeation.md` §0.3 argued that `process-evap-fvv` was "the better
next slice, not the equal one", on the ground that

> `MultidayTankVaporVentingCalculator` TVV-2 and TVV-3 read
> `ColdSoakTankTemperature` *directly* … so TTG-1 is numerically load-bearing
> there and is not here.

The premise is true. TVV-3 does read `ColdSoakTankTemperature` directly, at
both ends of its exponential difference. **The conclusion is false on this
snapshot, and the reason is the one permeation already found.**

`MOVESOutput` is TVV-9, and TVV-9 is

```
emissionQuant = weightedMeanBaseRate × sourceHours × opModeFraction / noOfRealDays
```

summed over operating mode. TVV-8 fills `weightedMeanBaseRate` from **two
disjoint inserts**: the cold-soak insert writes operating mode **151** and is
the only consumer of everything TVV-2 … TVV-7 and the soak recurrence compute;
the operating / hot-soak insert writes modes **150** and **300** from
`EmissionRateByAge` and never touches the venting chain at all. And this
fixture's operating-mode distribution — computed, not assumed; E1–E3 of
`docs/evap-leaks.md` §2.3 derive it and the oracle reproduces all six rows
exactly — is

```
opMode 150: 0.0     opMode 151: 0.0     opMode 300: 1.0
```

for both hour-days, because `fractionOfOperating` is exactly 1 at an on-network
link. **So the entire venting half of the calculator is multiplied by an
`opModeFraction` of exactly zero.**

This is not an inference from the zero. The oracle in §6.5 computes the venting
half in full — TVV-2, TVV-3 over both altitudes, TVV-4's ethanol interpolation
and hourly difference, the TVG soak-day recurrence over soaking days 1…5,
TVV-5's venting equations, TVV-6's warming-gated increment, TVV-7's two parts
and TVV-8's cold-soak insert — and it *arrives at 2,688 non-zero cold-soak base
rates, the largest of them 0.421632 g/h*. The chain is live, produces real
numbers, and contributes nothing:

```
contribution by operating mode: {150: 0.0, 151: 0.0, 300: 558.971771}
```

Measured by perturbing one input at a time and comparing all 128 output cells
**bit for bit** against the unperturbed run (`§7.2` gives the command):

| perturbation | worst cell change | total THC |
|---|---|---|
| none | — | 558.971771 g |
| `ColdSoakTankTemperature` (TTG-1's output) **+50 °F** | **0.0000e+00** | 558.971771 g |
| TVV-5's `tvvEquation` result **× 2** | **0.0000e+00** | 558.971771 g |
| the TVG soak recurrence's day-*n* `Xn` **× 3** | **0.0000e+00** | 558.971771 g |
| `coldSoakInitialHourFraction` (TTG-7) **× 7** | **0.0000e+00** | 558.971771 g |
| `AverageTankGasoline.RVP` **+2** | 9.5871e-02 | **612.559522 g** |

Not "changes by less than the tolerance" — *bit-identical*, at every one of the
128 cells, for four separate perturbations covering the recurrence, the venting
equations, the soak fold and the cold-soak weighting. The one input in that
table that moves the answer is the RVP, and it moves it through TVV-8's
temperature / RVP adjustment (§2.13), which is on the **operating**-mode side.

Four consequences, and they are the useful output of this slice:

1. **A fixture-level check of the venting chain would be worthless here**, in
   exactly the sense `docs/evap-permeation.md` §0.3 established for TTG-1: it
   would pass with the chain deleted. `fixtures/process-evap-fvv.esm` therefore
   does not contain one, and §8.1 says what it does contain instead.
2. **The recurrence question this phase was opened to answer cannot be answered
   by an on-network evaporative slice at all.** This is the third consecutive
   one, and the mechanism is structural rather than incidental: E2 weights every
   soak mode by `1 − fractionOfOperating`, `fractionOfOperating` is
   `min(1, SHO/SourceHours)`, and `SourceHours = SHO` identically at an
   on-network link (A10). So `1 − fractionOfOperating` is **exactly** 0 on any
   fixture whose only link is on-network, for any evaporative process. §8.3
   states what a slice would have to change to see the soak chain.
3. **`docs/evap-permeation.md` §0.3 and §8.2 are corrected in place**, not
   footnoted, in the posture permeation's own §0.3 used on PLAN.md.
4. **The oracle still earns its keep**, and more than the permeation one does:
   it reads *nothing* from the reference (§6.5), it computes `AverageTankGasoline`
   which the snapshot does not contain at all, and computing the venting half is
   what makes claim 1 a measurement rather than an assumption.

---

## 1. Inputs

The calculator declares 30 `INPUT_TABLES`. Beyond the ones `docs/evap-leaks.md`
§1 already inventories for the shared activity, cohort and operating-mode chain,
fuel vapour venting adds:

| table | rows | what it carries |
|---|---|---|
| `coldSoakTankTemperature` | 24 | TTG-1's parked-tank temperature; TVV-2 and TVV-3 read it |
| `coldSoakInitialHourFraction` | 534 | TTG-7's (current hour, soak-start hour) split; TVV-3 and TVV-7 |
| `sampleVehicleSoaking` | 288 | the multi-day soak fractions, soaking days 0…5 |
| `stmyTVVCoeffs2020` | 125 | `tankSize`, `tankFillFraction`, `backPurgeFactor`, `averageCanisterCapacity`, `leakFraction`, `leakFractionIM` per (sourceType, modelYear, fuelType) |
| `stmyTVVEquations2020` | 125 | the same, plus `regClassID`, `regClassFractionOfSourceTypeModelYearFuel`, `tvvEquation`, `leakEquation` |
| `cumTVVCoeffs` | 2188 | `NewTVVYear`'s input, from which the two `stmyTVV*` tables are aggregated; §2.10 |
| `tankVaporGenCoeffs` | 4 | `tvgTermA/B/C` per (ethanolLevelID ∈ {0, 10}) × (altitude ∈ {H, L}) |
| `evapTemperatureAdjustment` | 1 | TVV-8's cubic in temperature, `processID` 12 |
| `evapRVPTemperatureAdjustment` | 8 | TVV-8's cubic in temperature, per fuel type, at RVP knots 7, 8, 9, 10 |
| `averageTankGasoline` | **0** | TFG's output. **Empty**; §2.5 computes it |
| `fuelSupply` | 5 | the market shares of the region's fuel formulations |
| `fuelFormulation` | 2158 | `RVP`, `ETOHVolume`, `fuelSubtypeID` |
| `fuelSubtype` | 13 | subtype → fuel type |
| `regionCounty` | 2 | county → fuel region, per `regionCodeID` |
| `county` | 1 | `barometricPressure` 29.095 inHg, for TVV-3's altitude interpolation |
| `zoneMonthHour` | 24 | the ambient temperatures TTG-1 and TFG-2a start from, and TVV-8's operating temperature |
| `emissionRateByAge` | 4840 | TVV-8's operating / hot-soak rates; opModes 150 and 300, seven age groups |
| `sourceTypePolProcess` | 1 | §0.1's `isRegClassReqd` |

`imCoverage` is empty, so this fixture has no I/M program — same as the other
two evaporative slices, and TVV-1's merge and TVV-9's blend are both inert. The
oracle asserts that emptiness rather than assuming it.

### 1.1 The three tables that are captured empty, and what each means

| table | why empty | consequence |
|---|---|---|
| `averageTankGasoline` | `TankFuelGenerator` is a **master-side** year-level generator; its output is never transferred to a SQL worker, and this snapshot captures the worker's view | must be **computed** (§2.5); it is load-bearing (§0.3) |
| `opModeDistribution` | the evaporative distribution is built into `opModeDistributionTemp` and consumed from there | E1–E3 compute it; the snapshot's 6-row `opModeDistributionTemp` is the check |
| `imCoverage` | no I/M program in Washtenaw County | TVV-1 and TVV-9's blend are inert |

`sampleVehicleSoakingDayUsed` and its siblings are also empty; they are
`FillSampleVehicleSoaking`'s *scratch*, and `sampleVehicleSoaking` — the table
that section fills — is present with 288 rows, so the section had already run.

### 1.2 The recurrences in this chain, and what happens to each

| | recurrence | where | in this fixture |
|---|---|---|---|
| R1 | TTG-1's 96-cell quarter-hour tank-temperature walk | §2.4 | **computed**, checked in `components/tank_temperature.esm` against three captured intermediates; contributes 0 to the output (§0.3) |
| R2 | the TVG soak-day fold over soaking days 1, 2, 3… | §2.9 | **computed in the oracle**; an ordinary index-axis fold, nothing F12 did not deliver; contributes 0 (§0.3) |
| R3 | TTG-4a's work queue over `SampleVehicleTrip` | not computed | finding **F28**; `coldSoakInitialHourFraction` and `soakActivityFraction` are read as inputs. §8.2 |

---

## 2. The chain

A1–A10 (activity), C1–C4 (cohorts, with C2′ from §0.1) and E1–E3 (the
operating-mode distribution) are `docs/evap-leaks.md` §2.1–§2.3 unchanged. What
follows is the two generators and then the nine calculator steps.

### 2.4 TTG-1 — the quarter-hour cold-soak tank temperature

`tank_temperature_generator.rs:1483-1537`, and identical to
`docs/evap-permeation.md` §2.6 — the same recurrence, the same 96-cell axis,
the same `components/tank_temperature.esm`. Restated only for its output:

* **TTG-1a** `quarterHourTemperature[h, s] = ambient[h] + (s−1)·0.25·(ambient[h+1] − ambient[h])`, `s ∈ 1…4`, `h+1` wrapping 24 → 1.
* **TTG-1b** the recurrence, walked in `(h, s)` order with
  `tank[0] = quarterHourTemperature[1, 1]`:
  `tank[n] = 1.4 · Σ_{k<n} (quarterHourTemperature[k] − tank[k]) + tank[0]`.
* **TTG-1c** `coldSoakTankTemperature[h] = tank` at `s = 1`.

Reproduced to **7.550e-07** on all 24 hours; the peak (TVV-2's `peakHourID`) is
**hour 17**.

### 2.5 `TankFuelGenerator` — `AverageTankGasoline` (TFG-1a … TFG-3b)

`tank_fuel_generator.rs:405-755`. The table is captured empty (§1.1) so every
column of it is computed here. Constants: `ethanolRVP = 2.3`,
`weatheringConstant = 0.049`, `regionCodeID = 1`.

**TFG-0 — resolve the fuel region.** The first `regionCounty` row with
`regionCodeID = 1` and `countyID = 26161` for which some `Year` row has
`fuelYearID = regionCounty.fuelYearID` and `yearID = 2020`. Here: region
`270000000`, fuel year `2020`. The **year multiplicity** is the count of `Year`
rows with that `fuelYearID` whose `yearID` is in `RunSpecYear` — here **1**. It
multiplies every market share, so it cancels out of the three ratios below but
*not* out of `gasoholMarketShare`, which is an absolute sum.

**TFG-1a — the used formulations.** `FuelSupply` filtered to the region, the
fuel year, `marketShare > 0` and `monthGroupID ∈ RunSpecMonthGroup`, then inner
joined `FuelSupply.fuelFormulationID = FuelFormulation.fuelFormulationID`,
`FuelFormulation.fuelSubtypeID = FuelSubtype.fuelSubtypeID`,
`FuelSubtype.fuelTypeID = FuelType.fuelTypeID` with
`subjectToEvapCalculations = 'Y'`. Of the snapshot's five supplied formulations
this keeps **two**: 9114 (subtype 12 → fuel type 1) and 27002 (subtype 51 →
fuel type 5). Formulation 90 is electricity and 25003 is diesel, both
`subjectToEvapCalculations = 'N'`; formulation 28001 names `fuelSubtypeID` 30,
which **has no `FuelSubtype` row at all**, so the inner join drops it.

For each kept formulation, with `e = ETOHVolume`:

```
kGasoline(e)  = −7e-7·e³ + 0.0002·e² + 0.0024·e + 1
kEthanol(e)   = 46.321 · e^(−0.8422)      (e > 0), else 1000
gasPortionRVP = (RVP − kEthanol(e)·e/100·2.3) / (kGasoline(e)·(100−e)/100)
```

`gasPortionRVP` is **NULL when either `RVP` or `ETOHVolume` is NULL** — MySQL
NULL propagation, and coercing it to 0 was a recorded defect in `moves.rs`
(`AUDIT-canonical-fidelity.md:78`).

**TFG-1b, TFG-1c — the market-share means**, grouped by
`(fuelTypeID, fuelYearID, monthGroupID)`, with `weight = marketShare ×
yearMultiplicity`:

```
linearAverageRVP      = Σ RVP·w           / Σ w
tankAverageETOHVolume = Σ ETOHVolume·w    / Σ w
averageGasPortionRVP  = Σ gasPortionRVP·w / Σ w
gasoholMarketShare    = Σ w over rows with 4 ≤ ETOHVolume ≤ 20   (NULL if none)
```

**The denominator is `Σ w` over every surviving row, including rows whose
numerator operand is NULL.** There is no renormalisation to 1 and no
per-column denominator.

**TFG-1d, TFG-1e — the unweathered Reddy RVP**, evaluated at the *average*
ethanol volume `E = tankAverageETOHVolume`:

```
reddy(E, g) = kGasoline(E)·(100−E)/100·g + kEthanol(E)·E/100·2.3
noWeatheringReddyRVP = reddy(E, averageGasPortionRVP)
```

**TFG-3a — commingling.** `commingledRVP = linearAverageRVP × factor`, where
`factor` is a step function of `gasoholMarketShare`, evaluated top-down:

| share ≥ | 1.0 | 0.9 | 0.8 | 0.7 | 0.6 | 0.5 | 0.4 | 0.3 | 0.2 | 0.1 | else / NULL |
|---|---|---|---|---|---|---|---|---|---|---|---|
| factor | 1.000 | 1.018 | 1.027 | 1.034 | 1.038 | **1.040** | 1.039 | 1.035 | 1.028 | 1.016 | 1.000 |

It is **not monotonic** — the peak is 1.040 at the 0.5 band — so it is a table,
not a curve, and must be spelled as one.

**TFG-2a — the zone's evaporative temperature**, from the month's ambient
extremes `zLo`, `zHi` over `ZoneMonthHour` for the county's zones:

```
zoneEvapTemp = (zLo + zHi)/2                        if zHi < 40 or zHi − zLo ≤ 0
             = −1.7474 + 1.029·zLo + 0.99202·(zHi − zLo)
                       − 0.0025173·zLo·(zHi − zLo)  otherwise
```

Here `[59.5, 81.900002]` → **78.344292 °F**.

**TFG-2b, TFG-2c, TFG-2d, TFG-3b — weather and rescale**, per
`(zone, fuelType)` pair joined on `monthGroupID`, with `t = zoneEvapTemp` and
`g = averageGasPortionRVP`:

```
ratioGasolineRVPLoss   = max(0, (−2.4908 + 0.026196·t + 0.00076898·t·g)
                                / (−0.0860 + 0.070592·g))
weatheredGasPortionRVP = g · (1 − ratioGasolineRVPLoss · 0.049)
RVP        = reddy(E, weatheredGasPortionRVP) · commingledRVP / noWeatheringReddyRVP
ETOHVolume = tankAverageETOHVolume
```

**On this fixture all three of the interesting mechanisms collapse to the
identity**, and this is worth stating because it bounds what the fixture can
check:

* one formulation per fuel type at `marketShare` 1, so the weighted means are
  that formulation's own values and the fixture cannot discriminate the
  weighting scheme or its denominator;
* `gasoholMarketShare = 1.0` → factor **1.000**, so commingling is inert;
* `ratioGasolineRVPLoss` evaluates to **−0.0589** and clamps to **0**, so
  weathering is inert.

The computed result is therefore `RVP = 8.0` (fuel type 1) and `7.7` (fuel type
5), `ETOHVolume = 10.0` for both — exactly the supplied formulations' own
values. §8.1 records the three untested mechanisms; the `max(0, …)` clamp
itself *is* exercised, because it is what makes the answer 8.0 rather than
7.98.

### 2.6 TVV-1 — `IMCoverageMergedUngrouped`

Identical in structure to `docs/evap-leaks.md` §2.4's L1. `imCoverage` is empty,
so TVV-1 produces nothing and TVV-9's blend is inert.

### 2.7 TVV-2 — the peak cold-soak hour

For each month, `peakHourID` is the hour whose `coldSoakTankTemperature`,
rounded to two decimals, is highest, ties broken to the **earliest** hour. The
SQL packs the ranking into `max(round(T,2)·100000 + (999 − hourID))` and
unpacks with `mod(…,1000)`; the port ranks on the exact integer tuple
`(round(T·100), −hourID)`, which is the same order without the float exposure.

Here: **hour 17**, at 88.99 °F.

### 2.8 TVV-3 — `TankVaporGenerated`

Driven by `ColdSoakInitialHourFraction`, which pairs a current hour `H` with the
hour `I` in which the vehicle's current cold soak began. For each such row with
a positive fraction, keeping only `hourDayID ≠ initialHourDayID` (or both at
hour 1 of the same day) and `hour(H) ≤ peakHourID`, and with `t2 =
coldSoakTankTemperature[hour(H)]`, `t1 = coldSoakTankTemperature[hour(I)]`:

```
TVG = tankSize · (1 − tankFillFraction)
    · tvgTermA · exp(tvgTermB · RVP)
    · (exp(tvgTermC · t2) − exp(tvgTermC · t1))            when t1 < t2
    = 0                                                     when t1 ≥ t2
```

computed **once per altitude** (`tankVaporGenCoeffs.altitude ∈ {H, L}`) and
once per `ethanolLevelID ∈ {0, 10}`, then interpolated by the county's
barometric pressure:

```
TVG = max(0, ((baroP − 29.069) / (24.087 − 29.069)) · (TVG_high − TVG_low) + TVG_low)
```

`29.069` is Wayne County, MI; `24.087` is Denver County, CO; both are literals
of the SQL. Here `baroP = 29.095`, so the interpolation factor is
**−0.005219**: a slight extrapolation *below* the low-altitude endpoint.

`tankSize` and `tankFillFraction` come from `stmyTVVCoeffs` joined on
`(sourceTypeID, fuelTypeID)`, so the result carries `(modelYearID,
polProcessID)`. The `(hour 1, initial hour 1, same day)` self-pair is admitted
deliberately — it yields `TVG = 0` since `t1 = t2` — so the soak recurrence has
an hour-1 row to start from. **This is where `AverageTankGasoline.RVP` enters
the venting half**, and it is why `docs/evap-permeation.md` §8.2 listed
`TankFuelGenerator` as a prerequisite; §0.3 measures that this particular use of
it is multiplied by zero, and §2.13 is the use that is not.

The oracle builds **34,048** `TankVaporGenerated` rows.

### 2.9 TVV-4 and the TVG soak recurrence

**TVV-4** pairs each ethanol-level-0 row with its level-10 sibling and
interpolates by the fuel's ethanol volume, then differences the (cumulative)
result into an hourly increment:

```
cumulativeTVG = TVG₁₀ · φ + TVG₀ · (1 − φ),     φ = min(10, ETOHVolume) / 10
hourlyTVG     = max(0, cumulativeTVG[H] − cumulativeTVG[H−1])
```

pairing each row with the same dimensions one hour earlier **on the same day**;
a missing prior hour contributes 0. `hourDayID` decodes as
`hourID = ⌊hourDayID/10⌋`, `dayID = hourDayID mod 10`.

**The soak recurrence** (`tvg_soak_recurrence`) is R2. It first builds four
day-window partial sums of `hourlyTVG`, each keyed on the seven-column identity
`(hourDayID, initialHourDayID, monthID, sourceTypeID, fuelTypeID, modelYearID,
polProcessID)`:

* `tvgSumIH` — hours `[I, H]`, or 0 when `H` precedes `I`;
* `tvgSumI24` — hours `[I, 24]`;
* `tvgSum1H` — hours `[1, H]` over the rows whose *initial* hour is hour 1;
* `tvgSumH24` — hours `(H, 24]`, a left join coalesced to 0.

`tvgSum1H` and `tvgSumI24` are **inner** joins: a row with an empty window is
dropped, not zeroed. Then, soaking day by soaking day:

```
day 1:  TVGdaily = Xn = tvgSumIH
day 2:  Xn = (1 − backPurgeFactor)·min(tvgSumI24, canisterCap) + tvgSum1H
day n:  Xn = (1 − backPurgeFactor)·min(Xn[n−1] + tvgSumH24, canisterCap) + tvgSum1H
```

with `TVGdaily` carried forward unchanged from day 1. The days iterated beyond
day 2 are the distinct `soakDayID > 2` values in `sampleVehicleSoaking` — here
**3, 4 and 5** — so a gap in those values truncates the recurrence exactly as
the SQL `loop` would. This is an ordinary index-axis fold and needs nothing F12
did not deliver.

The oracle builds **85,120** `TVG` rows across the five soaking days.

### 2.10 TVV-5 — cumulative tank vapour vented, and its two equation forms

Each `stmyTVVEquations` row is joined to the soak recurrence on
`(sourceTypeID, modelYearID, fuelTypeID, polProcessID)`, to `AgeCategory` with
the model year pinned to `year − ageID`, and to `HourDay`:

```
TVV    = regClassFraction · max(0, (1 − leakFraction)·tvvEq + leakFraction·leakEq)
TVV_IM = regClassFraction · max(0, (1 − leakFracIM)·tvvEq + leakFracIM·leakEq)
```

with `leakFracIM = coalesce(leakFractionIM, leakFraction)`. `priorHourID` is the
cyclic predecessor `((hourID − 2) mod 24) + 1`, pre-computed for TVV-6.

**`tvvEq` and `leakEq` are the part of this calculator that MOVES stores as
data, and this is what that actually is.**

`cumTVVCoeffs.tvvEquation` and `.leakEquation` are `VARCHAR` columns. In the
MOVES *default* database they hold full SQL expressions.
`TankVaporVentingCalculator.alterReplacementsAndSections` reads the distinct
strings, rewrites them in the **execution** database as sequential abbreviations
in primary-key scan order, and pastes the expressions themselves into the SQL's
`##tvvEquations##` / `##leakEquations##` placeholders as a `CASE`. So:

* what the **snapshot** carries is the post-rewrite execution database, whose
  2,188 `cumTVVCoeffs` rows hold exactly **six** distinct `tvvEquation` values
  (`T0`…`T5`) and **twelve** distinct `leakEquation` values (`L0`…`L11`) — 18
  short labels, and no expression anywhere;
* the expressions are recoverable only from the default database.
  `moves.rs` hard-codes them against the MOVES 2024-11-12 default DB
  (`multiday_tank_vapor_venting_calculator.rs:5196-5271`), and that is where the
  forms below come from.

Once the coefficients are factored out of the strings there are **two forms**,
not eighteen:

**Form 1 — `tvv_quadratic_root`.** The positive root of `a·y² + b·y + c = 0`
with `b` linear and `c` quadratic in the canister load `Xn`:

```
inner(Xn; a, b₁, b₀, c₂, c₁, c₀)
    = (−b + sqrt(max(0, b² − 4·a·c))) / (2a)
      where  b = b₁·Xn + b₀,   c = c₂·Xn² + c₁·Xn + c₀
```

**Form 2 — `tvv_blend`.** A convex blend of two Form-1 evaluations, clamped:

```
tvvEq(Xn; p, q, w) = max(0, w·inner(Xn; θ_p) + (1 − w)·inner(Xn; θ_q))
```

`T0`, `T1` and `T2` are the degenerate `w = 1` case, so **Form 2 subsumes Form
1 and all six T-labels are one expression** with a coefficient row each:

| label | a | b₁ | b₀ | c₂ | c₁ | c₀ | blend |
|---|---|---|---|---|---|---|---|
| T0 | 1.25 | −1.00 | 85 | −0.250 | 0.20 | 70 | — |
| T1 | 1.15 | −1.21 | 187 | −0.071 | 3.12 | 20 | — |
| T2 | 1.90 | −1.34 | 115 | −0.125 | 2.70 | 23 | — |
| T3 | | | | | | | 0.8·T0 + 0.2·T2 |
| T4 | | | | | | | 0.6·T0 + 0.4·T2 |
| T5 | | | | | | | 0.1·T0 + 0.9·T2 |

**Form 3 — `leak_linear`.** All twelve leak labels are one expression,
`leakEq = k · TVGdaily`, with `k` a coefficient:

| L0 | L1 | L2 | L3 | L4 | L5 | L6 | L7 | L8 | L9 | L10 | L11 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.814 | 0.79 | 0.796 | 0.524 | 0.408 | 0.388 | 0.376 | 0.365 | 0.357 | 0.351 | 0.952 | 0.782 |

So the port is **three expression templates and eighteen coefficient rows**, and
the coefficients stay data. The label is already an ordinary ingested column;
what has to be authored is the 18-row label → coefficient table, because it is
the one thing the snapshot does not contain. That is the same standing as any
other MOVES default-database table this repository reproduces, and it is
recorded here rather than buried in a component so a later reader can check it
against a default database rather than against this document.

The `sqrt` argument is clamped with `max(0, …)` before the root: the SQL would
yield `NULL` for a negative discriminant and MariaDB would propagate it,
`moves.rs` clamps, and this port follows `moves.rs`. Nothing in this fixture
reaches a negative discriminant, so the two are indistinguishable here and this
is flagged in §8.1 rather than claimed as verified.

`stmyTVVEquations` on this snapshot uses only `T0`–`T5` and `L3`, `L9` — six of
the six TVV forms and two of the twelve leak coefficients.

### 2.11 TVV-6 — the unweighted hourly increment

A self-join of `CummulativeTankVaporVented` on the full primary key with
`hourID = priorHourID`:

```
unweightedHourlyTVV = max(0, TVV[H] − TVV[priorHour])   if the tank warmed
                    = 0                                  otherwise
```

"the tank warmed" is `coldSoakTankTemperature[H] > coldSoakTankTemperature[prior]`.
A missing prior row contributes `coalesce(…, 0) = 0`; a **missing temperature**
makes the SQL `≤` comparison `NULL` and the `CASE` falls through to the
difference, so absence and non-warming are not the same thing. This gate is the
multi-day script's addition over the single-day TVV-6.

### 2.12 TVV-7 — the cold-soak-weighted hourly TVV

**Part A.** Every `unweightedHourlyTVV` row is weighted by its matching
`coldSoakInitialHourFraction` and summed over the `soakDayID` and
`initialHourDayID` dimensions, on the six-column key
`(soakDayID, sourceTypeID, zoneID, monthID, hourDayID, initialHourDayID)`,
producing one row per `(regClassID, ageID, polProcessID, hourDayID, monthID,
sourceTypeID, fuelTypeID)`.

The fraction set is built in two halves: the extracted
`coldSoakInitialHourFraction` rows **are** soaking day 1, and every
`sampleVehicleSoaking` row with `soakDayID > 1` becomes a fraction at
`(hour, day)` with the initial hour pinned to **hour 1 of that day**. This is
the weighting `docs/evap-permeation.md` §8.2 said "cannot be reached past", and
that is true — it multiplies every unweighted hourly TVV before any
operating-mode split. It is also, on this fixture, multiplied by zero one step
later (§0.3, perturbation ×7).

**Part B — the four post-peak decay hours.** Each part-A row sitting *at* its
month's peak hour seeds rows for hours `peak+1 … peak+4` on the same day,
scaled by the fixed schedule **0.0200, 0.0100, 0.0040, 0.0005**. The SQL reads
these from a `CopyOfHourlyTVV` snapshot taken before part B's insert, so the
decay rows derive from part A alone and do not compound.

The oracle builds **2,688** `HourlyTVV` rows, **1,792** of them non-zero.

### 2.13 TVV-8 — `WeightedMeanBaseRate`, in two disjoint inserts

**The cold-soak insert — operating mode 151.** Carries `HourlyTVV` forward,
weighting by `sourceBinActivityFraction` and summing per
`(polProcessID, sourceTypeID, regClassID, fuelTypeID, monthID, hourDayID,
modelYearID)`. The bin must match the `HourlyTVV` row's `fuelTypeID` **and**
`regClassID`, the fuel type must be `subjectToEvapCalculations = 'Y'`, and a
`PollutantProcessModelYear` row must link the bin's model-year group.

**The operating / hot-soak insert — operating modes 150 and 300.** Weights
`EmissionRateByAge.meanBaseRate` by `sourceBinActivityFraction` over the same
group key, then multiplies mode 300 (fuel types 1 and 5 only) by

```
tempAdj = Σₖ evapTemperatureAdjustment.tempAdjustTermₖ · max(T, 40)ᵏ
rvpAdj  = Σₖ averageTankGasoline.adjustTermₖ · Tᵏ          (T ≥ 40, else 1)
adjustment = tempAdj · rvpAdj
```

both cubic, with `T` the **ambient** `ZoneMonthHour.temperature` — 59.5 °F at
hour 7 — not a tank temperature.

`averageTankGasoline.adjustTerm₃₂₁` and `adjustConstant` do not exist in the
snapshot's schema; they are built by a block that runs immediately before this
insert and **linearly interpolates `evapRVPTemperatureAdjustment`'s four RVP
knots at the fuel's own RVP**. The knot set is first extended with sentinels at
`RVP = −1` (carrying the lowest real knot's terms) and `RVP = 1000` (the
highest's), so every RVP falls strictly inside; then, with `lo` the greatest
knot `≤ RVP` and `hi` the least knot `> RVP`,

```
term = lo.term + (hi.term − lo.term) / (hi.RVP − lo.RVP) · (RVP − lo.RVP)
```

**This is the one place `AverageTankGasoline` is load-bearing on this fixture**
(§0.3): the RVP moves the answer by 2.7 % on gasoline and 3.5 % on E85, and
getting it wrong is a 15.6 g error on a 559 g total. The block *truncates and
refills* `averageTankGasoline` from this join, so a fuel type with no
`evapRVPTemperatureAdjustment` knots leaves the table entirely — which is why
only fuel types 1 and 5 can ever reach this insert.

Both inserts filter `subjectToEvapCalculations = 'Y'` and require the
`PollutantProcessModelYear` link; neither is discriminating here.

### 2.14 TVV-9 — the emission and the output row

Identical in shape to `docs/evap-leaks.md` §2.5's L9:

```
emissionQuant = weightedMeanBaseRate × sourceHours × opModeFraction / noOfRealDays
```

joined to `SourceHours` on `(hourDayID, monthID, ageID = year − modelYearID,
sourceTypeID)`, to `OpModeDistribution` on `(sourceTypeID, hourDayID,
polProcessID, opModeID)`, and through `PollutantProcessAssoc` and `HourDay` →
`DayOfAnyWeek.noOfRealDays`. The I/M blend is `lib/adjustments.esm`'s
`im_blend` and is inert. `÷ noOfRealDays` undoes A7's `× 1/weeksPerMonth`, as
`docs/evap-leaks.md` §2.5 explains.

**The SCC** is `22·10⁸ + fuelTypeID·10⁶ + sourceTypeID·10⁴ + roadTypeID·10² +
processID` = `2201210412` / `2205210412`, checked against `MOVESOutput` on all
128 rows.

**Aggregation to the output key** sums over `opModeID` and `regClassID`. That
sum over operating mode is where §0.3's zero lands: two of the three modes
contribute exactly 0.

---

## 3. Join structure

The A-stage, C-stage and E-stage joins are `docs/evap-leaks.md` §3's, unchanged.
`docs/esm-conventions.md` §3 is the spelling rule: an equality between key
columns is a `join.on` clause with a key-pair list, a composite key is **one**
clause with several pairs, and a range test, a null guard or a set membership is
a `filter`.

| | step | left | right | key pairs | note |
|---|---|---|---|---|---|
| V1 | TFG-0 | `regionCounty` | `Year` | `fuelYearID = fuelYearID` | filter `regionCodeID = 1`, `countyID`, `yearID` |
| V2 | TFG-1a | `fuelSupply` | `fuelFormulation` | `fuelFormulationID = fuelFormulationID` | inner |
| V3 | TFG-1a | `fuelFormulation` | `fuelSubtype` | `fuelSubtypeID = fuelSubtypeID` | inner; drops subtype 30 |
| V4 | TFG-1a | `fuelSubtype` | `fuelType` | `fuelTypeID = fuelTypeID` | filter `subjectToEvapCalculations = 'Y'` |
| V5 | TFG-2a | `zone` | `zoneMonthHour` | `zoneID = zoneID` | filter `countyID`, `monthID ∈ RunSpecMonth` |
| V6 | TFG-2b | TFG zone | TFG fuel average | `monthGroupID = monthGroupID` | inner; the only zone↔fuel key |
| V7 | TVV-2 | `coldSoakTankTemperature` | — | — | group by `monthID`, arg-max on `(round(T·100), −hourID)` |
| V8 | TVV-3 | `coldSoakInitialHourFraction` | `hourDay` | `hourDayID = hourDayID` | and again on `initialHourDayID = hourDayID` |
| V9 | TVV-3 | ⟶ | `coldSoakTankTemperature` | `monthID = monthID`, `hourID = hourID` | twice: `t2` at `H`, `t1` at `I` |
| V10 | TVV-3 | ⟶ | `monthOfAnyYear` | `monthID = monthID` | → `monthGroupID` |
| V11 | TVV-3 | ⟶ | `averageTankGasoline` | `monthGroupID = monthGroupID` | → `RVP`, `fuelTypeID` |
| V12 | TVV-3 | ⟶ | `stmyTVVCoeffs` | `sourceTypeID = sourceTypeID`, `fuelTypeID = fuelTypeID` | fans out over model year |
| V13 | TVV-3 | ⟶ | `tankVaporGenCoeffs` | — | cross join; 2 ethanol levels × 2 altitudes |
| V14 | TVV-3 | high | low | the 8-column identity | pairs the altitudes for the interpolation |
| V15 | TVV-4 | level 0 | level 10 | `hourDayID` + the 6-column identity | pairs the ethanol levels |
| V16 | TVV-4 | ⟶ | prior hour | `hourID − 1`, same day, same 6-column identity | left join, coalesce 0 |
| V17 | TVG | row | window | the 7-column identity, `hourID ∈ window` | 4 windows; `IH`/`I24`/`1H` inner, `H24` left |
| V18 | TVV-5 | `stmyTVVEquations` | TVG | `sourceTypeID`, `modelYearID`, `fuelTypeID`, `polProcessID` | inner |
| V19 | TVV-5 | ⟶ | `ageCategory` | `ageID = year − modelYearID` | inner; an existence filter |
| V20 | TVV-6 | row | prior hour | the 10-column key with `hourID = priorHourID` | left join |
| V21 | TVV-6 | ⟶ | `coldSoakTankTemperature` | `monthID`, `hourID` and `priorHourID` | the warming gate |
| V22 | TVV-7A | `unweightedHourlyTVV` | fraction set | `soakDayID`, `sourceTypeID`, `zoneID`, `monthID`, `hourDayID`, `initialHourDayID` | inner |
| V23 | TVV-7B | part A | `hourDay` | `dayID`, `hourID = peak + k` | k = 1…4 |
| V24 | TVV-8c | `hourlyTVV` | `sourceTypeModelYear` | `modelYearID = year − ageID`, `sourceTypeID` | inner |
| V25 | TVV-8c | ⟶ | `sourceBinDistribution` | `sourceTypeModelYearID`, `polProcessID` | inner |
| V26 | TVV-8c | ⟶ | `sourceBin` | `sourceBinID`, and `fuelTypeID`, `regClassID` must match the TVV row | inner |
| V27 | TVV-8o | `emissionRateByAge` | `sourceBin` | `sourceBinID = sourceBinID` | inner |
| V28 | TVV-8o | ⟶ | `ageCategory` | `ageGroupID = ageGroupID` | **the load-bearing join**; see `docs/evap-leaks.md` §2.4 |
| V29 | TVV-8o | ⟶ | `zoneMonthHour` | `hourID = hourID` | → the operating temperature |
| V30 | TVV-8o | `averageTankGasoline` | `evapRVPTemperatureAdjustment` | `fuelTypeID = fuelTypeID`, RVP bracket | filter `lo.RVP ≤ RVP < hi.RVP` |
| V31 | TVV-9 | `weightedMeanBaseRate` | `sourceHours` | `hourDayID`, `monthID`, `ageID = year − modelYearID`, `sourceTypeID` | inner |
| V32 | TVV-9 | ⟶ | `opModeDistribution` | `sourceTypeID`, `hourDayID`, `polProcessID`, `opModeID` | inner; **carries the zero** |
| V33 | TVV-9 | ⟶ | `pollutantProcessAssoc` | `polProcessID = polProcessID` | → `(processID, pollutantID)` |
| V34 | TVV-9 | ⟶ | `hourDay` → `dayOfAnyWeek` | `hourDayID`, then `dayID` | → `noOfRealDays` |

---

## 4. Reusable shapes (`expression_templates`)

### 4.1 Reused unchanged

`lib/onroad_activity.esm`'s `onroad_scc`; `lib/adjustments.esm`'s `im_blend`;
`lib/keys.esm`'s hour-day decode; `lib/evaporative.esm`'s `soak_share` and
`operating_share_of_activity` (`docs/evap-leaks.md` §4.2, §4.3);
`components/tank_temperature.esm`'s TTG-1.

### 4.2 New, and why each is a template rather than an inline expression

| template | shape | used by |
|---|---|---|
| `cubic_in` | `t₃·x³ + t₂·x² + t₁·x + c` | TVV-8's `tempAdj` **and** `rvpAdj`; two call sites with different arguments, which is the whole reason it is a template |
| `knot_interpolate` | `lo + (hi − lo)/(x_hi − x_lo)·(x − x_lo)` | TVV-8's four RVP-knot terms; four call sites |
| `reddy_rvp` | `kGas(E)·(100−E)/100·g + kEth(E)·E/100·2.3` | TFG-1e and TFG-3b; two call sites on the *same* `E` with different `g`, which is what makes the ratio at TFG-3b meaningful |
| `tvv_quadratic_root` | Form 1 of §2.10 | `tvv_blend`, twice |
| `tvv_blend` | Form 2 of §2.10 | TVV-5's `tvvEq`, all six labels |
| `leak_linear` | `k · TVGdaily` | TVV-5's `leakEq`, all twelve labels |

### 4.3 Deliberately not factored

TVV-3's exponential product and TFG-2a's `zoneEvapTemp` are each used once and
have no sibling; naming them would add an indirection without removing a
repetition. TFG-3a's commingling step function is a **table**, not an
expression (§2.5 — it is not monotonic), so it is data, not a template.

---

## 5. Literals and enums

### 5.1 Pollutants and processes

`polProcessID` **112** = pollutant 1 (THC) × process 12 (Evap Fuel Vapor
Venting). `pollutantProcessAssoc` marks it `isAffectedByEvapIM = 'Y'`, which is
why TVV-1 is in the chain at all.

### 5.2 Operating modes

150 hot soaking, 151 cold soaking, 300 all running — the same three as the other
two evaporative slices. `opModePolProcAssoc` associates 150 and 151 with
`polProcessID` 112; 300 is E3's residual.

### 5.3 The constants that are not run data

| where | value | what |
|---|---|---|
| TTG-1b | 1.4 | the tank-temperature rise coefficient |
| TVV-3 | 29.069 / 24.087 | the low / high altitude barometric endpoints, inHg |
| TVV-4 | 10 | the ethanol interpolation's upper level |
| TVV-7B | 0.0200, 0.0100, 0.0040, 0.0005 | the four post-peak decay hours |
| TVV-8 | 40 | the temperature floor of both adjustment polynomials |
| TVV-8 | −1, 1000 | the RVP knot sentinels |
| TFG | 2.3 | `ethanolRVP` |
| TFG | 0.049 | `weatheringConstant` |
| TFG-1a | −7e-7, 0.0002, 0.0024, 1 | `kGasoline` |
| TFG-1a | 46.321, −0.8422, 1000 | `kEthanol` |
| TFG-2a | 40, −1.7474, 1.029, 0.99202, 0.0025173 | `zoneEvapTemp` |
| TFG-2c | −2.4908, 0.026196, 0.00076898, −0.0860, 0.070592 | `ratioGasolineRVPLoss` |
| TFG-1c | 4, 20 | the gasohol `ETOHVolume` band |
| TVV-5 | §2.10's two tables | the 18 equation coefficient rows |

---

## 6. Hand-checkable worked examples

### 6.0 Run-level values used by every example

```
ambient temperature at hour 7        59.5           °F
evapTemperatureAdjustment cubic      0.711154735391  at max(59.5, 40)
AverageTankGasoline RVP              8.0 (fuel 1), 7.7 (fuel 5)
rvpAdjustment cubic                  0.972883340310 (fuel 1), 0.965379044111 (fuel 5)
TVV-8 adjustment = product           0.691870594444 (fuel 1), 0.686533878667 (fuel 5)
opModeFraction, mode 300             1.0            (modes 150 and 151: 0.0)
noOfRealDays                         2 (weekend), 5 (weekday)
```

### 6.1 Worked example A — model year 1980, gasoline, weekend

```
Σ sourceBinActivityFraction × meanBaseRate (mode 300)   11.058619723783  g/h
× adjustment (fuel 1)                                    0.691870594444
× sourceHours (hourDay 72, age 40)                       2.437278713     h
× opModeFraction                                         1.0
÷ noOfRealDays                                           2
                                                       = 9.323972773     g
MOVESOutput                                              9.323970000     g
```

relative error 2.97e-07 — the reference's own six-significant-figure column
storage.

### 6.2 Worked example B — model year 2020, gasoline, weekday

```
0.032023662781 × 0.691870594444 × 260.057303892 × 1.0 ÷ 5 = 1.152377919 g
MOVESOutput                                                 1.152380000 g
```

Note that the base rate is 345× smaller than 1980's while `sourceHours` is 107×
larger — the age relation V28 picks a different `emissionRateByAge` age group
for each, and this is the join `docs/evap-leaks.md` §2.4 measures at 9.44× the
total when removed.

### 6.3 Worked example C — model year 2002, E85, weekend

```
0.000101812689 × 0.686533878667 × 12.456122692 × 1.0 ÷ 2 = 0.000435328 g
MOVESOutput                                                 0.000435329 g
```

The adjustment differs from A and B in the fourth significant figure only,
because fuel 5's RVP of 7.7 lands between the same pair of knots as fuel 1's
8.0 — knots 7 and 8, and 8 and 9, respectively. This is the *only* cell class
that distinguishes the two RVP interpolations, so it is the one that would catch
a per-fuel-type mix-up in V30.

### 6.4 Worked example D — the venting half, and where it goes

The oracle's cold-soak insert produces 2,688 base rates for operating mode 151,
the largest **0.421632 g/h**. For a cell to reach the output it must survive V32,
which joins `opModeDistribution` on `opModeID`; the row is found, and its
`opModeFraction` is `0.0`. So

```
0.421632 × sourceHours × 0.0 ÷ noOfRealDays = 0.0
```

exactly, at every one of the 2,688. That is §0.3's measurement stated as
arithmetic. It is *not* a missing join — the row is present and matched — which
is why deleting the venting chain would leave the fixture green.

### 6.5 The reproduction script

Extracted and run by `./run-fvv-oracle.sh`, which is wired into `run-tests.sh`.
It reads **nothing** from the reference: every table it opens is an input of the
execution database, and the seven tables it compares against are compared and
never read forward. `./run-permeation-oracle.sh` reads 192
`AverageTankTemperature` cells and says so on every run; this one has none to
read, because the calculator's operating-mode half needs no tank temperature at
all and `AverageTankGasoline` — the table that would have been the analogous
read — is captured empty and is therefore computed.

```python
#!/usr/bin/env python3
"""Independent reproduction of the process-evap-fvv chain from the snapshot's own
INPUT tables: the activity chain (2.1, A1-A10), the cohort structure (2.2,
C1-C4), the evap operating-mode distribution (2.3, E1-E3), TankTemperature-
Generator TTG-1 (2.4), TankFuelGenerator (2.5, TFG-1..TFG-3) and the nine
steps of MultidayTankVaporVentingCalculator (2.6-2.14, TVV-1..TVV-9)
including the TVG soak-day recurrence.

Nothing is read from the reference. Purpose: attribution. When a `.esm`
disagrees with the snapshot, a third implementation says whether the document
or the specification is wrong."""
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
PP = 100 * 1 + 12                       # section 5.1: THC x Evap Fuel Vapor Venting
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
# TankFuelGenerator -- TFG-1a..TFG-3b (section 2.5). `averageTankGasoline` is
# captured EMPTY in all three evaporative snapshots because TankFuelGenerator
# runs master-side and its output is never transferred to a worker, so its RVP
# and ETOHVolume must be COMPUTED. TVV-3 needs the RVP, and so does TVV-8's
# operating-mode adjustment -- where, on this fixture, it is the only place it
# is load-bearing (section 0.3).
# ============================================================================
import math
ETHANOL_RVP, WEATHERING = 2.3, 0.049
REGION = [r for r in T("regioncounty")
          if r["regionCodeID"] == 1 and r["countyID"] == COUNTY
          and any(y["yearID"] == YEAR and y["fuelYearID"] == r["fuelYearID"] for y in T("year"))][0]
YEAR_MULT = float(sum(1 for y in T("year") if y["fuelYearID"] == REGION["fuelYearID"]
                      and y["yearID"] in {r["yearID"] for r in T("runspecyear")}))
assert YEAR_MULT > 0, "TFG: no run-selected year shares the fuel year"
MONTHGROUPS = {r["monthGroupID"] for r in T("runspecmonthgroup")}


def k_gasoline(e):
    return -7e-7 * e**3 + 0.0002 * e**2 + 0.0024 * e + 1.0


def k_ethanol(e):
    return 46.321 * e**-0.8422 if e > 0 else 1000.0


def reddy(e, gas_portion):
    """TFG-1e: recombine the gasoline and ethanol portions into a Reddy RVP."""
    return (k_gasoline(e) * (100.0 - e) / 100.0 * gas_portion
            + k_ethanol(e) * e / 100.0 * ETHANOL_RVP)


# TFG-1a: the formulations this region actually supplies, for evap fuel types.
ft_of_subtype = {r["fuelSubtypeID"]: r["fuelTypeID"] for r in T("fuelsubtype")}
evap_ft = {r["fuelTypeID"] for r in T("fueltype")
           if str(r["subjectToEvapCalculations"]).upper() == "Y"}
ff_of = {r["fuelFormulationID"]: r for r in T("fuelformulation")}
supply = [r for r in T("fuelsupply")
          if r["fuelRegionID"] == REGION["regionID"]
          and r["fuelYearID"] == REGION["fuelYearID"]
          and r["monthGroupID"] in MONTHGROUPS and f(r["marketShare"]) > 0.0]
used = {}
for r in supply:
    ff = ff_of.get(r["fuelFormulationID"])
    if ff is None:
        continue
    ft = ft_of_subtype.get(ff["fuelSubtypeID"])          # inner: subtype 30 has no row
    if ft is None or ft not in evap_ft:
        continue
    e = None if ff["ETOHVolume"] is None else f(ff["ETOHVolume"])
    rvp = None if ff["RVP"] is None else f(ff["RVP"])
    gp = None if (e is None or rvp is None) else \
        (rvp - k_ethanol(e) * e / 100.0 * ETHANOL_RVP) / (k_gasoline(e) * (100.0 - e) / 100.0)
    used[r["fuelFormulationID"]] = (ft, gp)

# TFG-1b, TFG-1c: market-share means. The denominator is the share sum over
# EVERY surviving row, including rows whose numerator operand is NULL.
acc = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, None])
for r in supply:
    if r["fuelFormulationID"] not in used:
        continue
    ft, gp = used[r["fuelFormulationID"]]
    ff = ff_of[r["fuelFormulationID"]]
    w = f(r["marketShare"]) * YEAR_MULT
    a = acc[(ft, r["fuelYearID"], r["monthGroupID"])]
    if ff["RVP"] is not None:
        a[0] += f(ff["RVP"]) * w
    if ff["ETOHVolume"] is not None:
        a[1] += f(ff["ETOHVolume"]) * w
    if gp is not None:
        a[2] += gp * w
    a[3] += w
    if ff["ETOHVolume"] is not None and 4.0 <= f(ff["ETOHVolume"]) <= 20.0:
        a[4] = (a[4] or 0.0) + w

COMMINGLE = [(1.0, 1.000), (0.9, 1.018), (0.8, 1.027), (0.7, 1.034), (0.6, 1.038),
             (0.5, 1.040), (0.4, 1.039), (0.3, 1.035), (0.2, 1.028), (0.1, 1.016)]
fuel_avg = {}
for (ft, fy, mg), (srvp, setoh, sgp, sms, gasohol) in acc.items():
    lin, etoh, gas = srvp / sms, setoh / sms, sgp / sms
    factor = next((v for lo, v in COMMINGLE if gasohol is not None and gasohol >= lo), 1.000)
    fuel_avg[(ft, mg)] = (lin * factor, etoh, gas, reddy(etoh, gas))   # TFG-3a, TFG-1e

# TFG-2a: the zone's evaporative temperature, from the month's extremes.
zone_t = [f(r["temperature"]) for r in T("zonemonthhour")
          if r["zoneID"] == ZONE and r["monthID"] == MONTH]
zlo, zhi = min(zone_t), max(zone_t)
zone_evap_t = ((zlo + zhi) / 2.0 if (zhi < 40.0 or zhi - zlo <= 0.0) else
               -1.7474 + 1.029 * zlo + 0.99202 * (zhi - zlo) - 0.0025173 * zlo * (zhi - zlo))

# TFG-2b, TFG-2c, TFG-2d, TFG-3b: weather the gasoline portion and rescale.
MG = {r["monthID"]: r["monthGroupID"] for r in T("monthofanyyear")}[MONTH]
ATG_RVP, ATG_ETOH = {}, {}
for (ft, mg), (commingled, etoh, gas, no_weather) in fuel_avg.items():
    if mg != MG:
        continue
    loss = max(0.0, (-2.4908 + 0.026196 * zone_evap_t + 0.00076898 * zone_evap_t * gas)
               / (-0.0860 + 0.070592 * gas))
    ATG_RVP[ft] = reddy(etoh, gas * (1.0 - loss * WEATHERING)) * commingled / no_weather
    ATG_ETOH[ft] = etoh
print("%-28s zoneEvapTemp %.6f degF from [%.4f, %.4f]; ratioGasolineRVPLoss %.6f"
      % ("TankFuelGenerator:", zone_evap_t, zlo, zhi, loss))
print("%-28s RVP %s, ETOHVolume %s"
      % ("", {k: round(v, 6) for k, v in sorted(ATG_RVP.items())},
         {k: round(v, 6) for k, v in sorted(ATG_ETOH.items())}))
# ============================================================================
# The venting half: TVV-2, TVV-3, TVV-4, the TVG soak recurrence, TVV-5, TVV-6,
# TVV-7 and TVV-8's cold-soak insert. Every step writes operating mode 151.
# ============================================================================
hourday_of = {r["hourDayID"]: (r["dayID"], r["hourID"]) for r in T("hourday")}
hourday_id = {(r["dayID"], r["hourID"]): r["hourDayID"] for r in T("hourday")}

# TVV-2: the hour of peak cold-soak tank temperature, ties to the earliest hour.
peak_hour = max(range(1, 25), key=lambda h: (round(cold_soak[h] * 100), -h))

# TVV-3: tank vapour generated, per altitude, then interpolated by pressure.
BARO = f(T("county")[0]["barometricPressure"])
P_LOW, P_HIGH = 29.069, 24.087
tvg_factor = (BARO - P_LOW) / (P_HIGH - P_LOW)
tvgc = [(r["ethanolLevelID"], r["altitude"], f(r["tvgTermA"]), f(r["tvgTermB"]),
         f(r["tvgTermC"])) for r in T("tankvaporgencoeffs")]
mg_of_month = {r["monthID"]: r["monthGroupID"] for r in T("monthofanyyear")}
stmy_tvv = collections.defaultdict(list)
for r in T("stmytvvcoeffs2020"):
    stmy_tvv[(r["sourceTypeID"], r["fuelTypeID"])].append(r)
csihf = [r for r in T("coldsoakinitialhourfraction")
         if r["zoneID"] == ZONE and r["monthID"] == MONTH]

tvg_lo, tvg_hi = {}, {}
for r in csihf:
    if f(r["coldSoakInitialHourFraction"]) <= 0.0:
        continue
    d, h = hourday_of[r["hourDayID"]]
    di, hi_ = hourday_of[r["initialHourDayID"]]
    if not (r["hourDayID"] != r["initialHourDayID"] or (h == 1 and hi_ == 1 and d == di)):
        continue
    if h > peak_hour:
        continue
    t2, t1 = cold_soak[h], cold_soak[hi_]
    for ft, RVP in ATG_RVP.items():
        for sc in stmy_tvv.get((r["sourceTypeID"], ft), []):
            pre = f(sc["tankSize"]) * (1.0 - f(sc["tankFillFraction"]))
            for (eth, alt, a, b, cc) in tvgc:
                v = 0.0 if t1 >= t2 else (
                    pre * a * math.exp(b * RVP) * (math.exp(cc * t2) - math.exp(cc * t1)))
                k = (r["hourDayID"], r["initialHourDayID"], eth, r["sourceTypeID"], ft,
                     sc["modelYearID"], sc["polProcessID"])
                (tvg_lo if alt == "L" else tvg_hi)[k] = (v, sc)
tvg = {}
for k, (lo, sc) in tvg_lo.items():
    if k not in tvg_hi:
        continue
    tvg[k] = (max(tvg_factor * (tvg_hi[k][0] - lo) + lo, 0.0), sc)

# TVV-4: interpolate ethanol level 0/10 by ETOHVolume, then difference to hourly.
cum = {}
for (hd, ihd, eth, st, ft, my, pp), (v0, sc) in tvg.items():
    if eth != 0:
        continue
    hi_k = (hd, ihd, 10, st, ft, my, pp)
    if hi_k not in tvg:
        continue
    u = min(10.0, ATG_ETOH[ft]) / 10.0
    cum[(hd, ihd, st, ft, my, pp)] = (tvg[hi_k][0] * u + v0 * (1.0 - u), sc)
ewtvg = {}
for (hd, ihd, st, ft, my, pp), (v, sc) in cum.items():
    d, h = hourday_of[hd]
    prior_hd = hourday_id.get((d, h - 1))
    p = cum.get((prior_hd, ihd, st, ft, my, pp), (0.0, None))[0] if prior_hd else 0.0
    ewtvg[(hd, ihd, st, ft, my, pp)] = (max(v - p, 0.0), sc)

# The TVG soak recurrence -- an index-axis fold over soaking days 1, 2, 3...
def window(d, lo, hi, ihd, st, ft, my, pp):
    s, seen = 0.0, False
    for h in range(lo, hi + 1):
        hd = hourday_id.get((d, h))
        if hd is None:
            continue
        if (hd, ihd, st, ft, my, pp) in ewtvg:
            s += ewtvg[(hd, ihd, st, ft, my, pp)][0]
            seen = True
    return s if seen else None

TVG = {}                              # (soakDay, key6) -> (tvgDaily, Xn, sc, s1h, sh24)
day1 = {}
for (hd, ihd, st, ft, my, pp), (_, sc) in ewtvg.items():
    d, h = hourday_of[hd]
    hi_ = hourday_of[ihd][1]
    s_ih = window(d, hi_, h, ihd, st, ft, my, pp) or 0.0 if h >= hi_ else 0.0
    hd1 = hourday_id.get((d, 1))
    s_1h = window(d, 1, h, hd1, st, ft, my, pp) if hd1 else None
    if s_1h is None:
        continue                      # inner join tvgSum1H
    s_h24 = window(d, h + 1, 24, ihd, st, ft, my, pp) or 0.0
    day1[(hd, ihd, st, ft, my, pp)] = (s_ih, s_ih, sc, s_1h, s_h24)
for k, v in day1.items():
    TVG[(1,) + k] = v
day2 = {}
for k, (td, xn, sc, s1h, sh24) in day1.items():
    hd, ihd, st, ft, my, pp = k
    d = hourday_of[hd][0]
    hi_ = hourday_of[ihd][1]
    s_i24 = window(d, hi_, 24, ihd, st, ft, my, pp)
    if s_i24 is None:
        continue                      # inner join tvgSumI24
    cap, bp = f(sc["averageCanisterCapacity"]), f(sc["backPurgeFactor"])
    day2[k] = (td, (1.0 - bp) * min(s_i24, cap) + s1h, sc, s1h, sh24)
for k, v in day2.items():
    TVG[(2,) + k] = v
prev = day2
for sd in sorted({r["soakDayID"] for r in T("samplevehiclesoaking")} - {0, 1, 2}):
    cur = {}
    for k, (td, xn, sc, s1h, sh24) in prev.items():
        cap, bp = f(sc["averageCanisterCapacity"]), f(sc["backPurgeFactor"])
        cur[k] = (td, (1.0 - bp) * min(xn + sh24, cap) + s1h, sc, s1h, sh24)
    for k, v in cur.items():
        TVG[(sd,) + k] = v
    prev = cur

# TVV-5: the venting equations. Section 2.10 -- two forms, eighteen coefficient
# rows, and NOT a string evaluated out of a table cell.
TVV_INNER = {"T0": (1.25, -1.00, 85.0, -0.250, 0.20, 70.0),
             "T1": (1.15, -1.21, 187.0, -0.071, 3.12, 20.0),
             "T2": (1.90, -1.34, 115.0, -0.125, 2.70, 23.0)}
TVV_BLEND = {"T0": ("T0", "T0", 1.0), "T1": ("T1", "T1", 1.0), "T2": ("T2", "T2", 1.0),
             "T3": ("T0", "T2", 0.8), "T4": ("T0", "T2", 0.6), "T5": ("T0", "T2", 0.1)}
LEAK_K = {"L0": 0.814, "L1": 0.79, "L2": 0.796, "L3": 0.524, "L4": 0.408, "L5": 0.388,
          "L6": 0.376, "L7": 0.365, "L8": 0.357, "L9": 0.351, "L10": 0.952, "L11": 0.782}


def tvv_inner(name, xn):
    a, b1, b0, c2, c1, c0 = TVV_INNER[name]
    b = b1 * xn + b0
    return (-b + math.sqrt(max(0.0, b * b - 4.0 * a * (c2 * xn * xn + c1 * xn + c0)))) / (2.0 * a)


def tvv_equation(name, xn):
    p, q, w = TVV_BLEND[name]
    return max(0.0, w * tvv_inner(p, xn) + (1.0 - w) * tvv_inner(q, xn))


ages = {r["ageID"] for r in T("agecategory")}
ctvv = {}
for co in T("stmytvvequations2020"):
    age = YEAR - co["modelYearID"]
    if age not in ages:
        continue
    lf = f(co["leakFraction"])
    lfim = f(co["leakFractionIM"]) if co["leakFractionIM"] is not None else lf
    rcf = f(co["regClassFractionOfSourceTypeModelYearFuel"])
    for (sd, hd, ihd, st, ft, my, pp), (td, xn, sc, _, _) in TVG.items():
        if (st, my, ft, pp) != (co["sourceTypeID"], co["modelYearID"],
                                co["fuelTypeID"], co["polProcessID"]):
            continue
        te = tvv_equation(co["tvvEquation"], xn)
        le = LEAK_K[co["leakEquation"]] * td
        d, h = hourday_of[hd]
        ctvv[(sd, co["regClassID"], age, pp, ihd, MONTH, st, ft, d, h)] = (
            rcf * max(0.0, (1 - lf) * te + lf * le),
            rcf * max(0.0, (1 - lfim) * te + lfim * le), hd)

# TVV-6: the hour-over-hour increment, zeroed unless the tank warmed.
uh = {}
for k, (v, vim, hd) in ctvv.items():
    sd, rc, age, pp, ihd, mo, st, ft, d, h = k
    ph = (h - 2) % 24 + 1
    pr = ctvv.get((sd, rc, age, pp, ihd, mo, st, ft, d, ph))
    pv, pvim = (pr[0], pr[1]) if pr else (0.0, 0.0)
    warming = cold_soak[h] > cold_soak[ph]
    uh[(sd, rc, age, pp, hd, ihd, mo, st, ft)] = (
        (max(v - pv, 0.0), max(vim - pvim, 0.0)) if warming else (0.0, 0.0))

# TVV-7 Part A: weight by coldSoakInitialHourFraction over soakDayID, initial hour.
csihf_of = {}
for r in csihf:
    csihf_of[(1, r["sourceTypeID"], r["hourDayID"], r["initialHourDayID"])] = \
        f(r["coldSoakInitialHourFraction"])
for s in T("samplevehiclesoaking"):
    if s["soakDayID"] <= 1:
        continue
    hd, ihd = hourday_id.get((s["dayID"], s["hourID"])), hourday_id.get((s["dayID"], 1))
    if hd is None or ihd is None:
        continue
    csihf_of[(s["soakDayID"], s["sourceTypeID"], hd, ihd)] = f(s["soakFraction"])
htvv = collections.defaultdict(lambda: [0.0, 0.0])
for (sd, rc, age, pp, hd, ihd, mo, st, ft), (v, vim) in uh.items():
    fr = csihf_of.get((sd, st, hd, ihd))
    if fr is None:
        continue
    htvv[(rc, age, pp, hd, mo, st, ft)][0] += v * fr
    htvv[(rc, age, pp, hd, mo, st, ft)][1] += vim * fr
# TVV-7 Part B: the four post-peak decay hours.
for (rc, age, pp, hd, mo, st, ft), (v, vim) in list(htvv.items()):
    d, h = hourday_of[hd]
    if h != peak_hour:
        continue
    for off, sc_ in ((1, 0.0200), (2, 0.0100), (3, 0.0040), (4, 0.0005)):
        nhd = hourday_id.get((d, peak_hour + off))
        if nhd is None:
            continue
        htvv[(rc, age, pp, nhd, mo, st, ft)][0] += v * sc_
        htvv[(rc, age, pp, nhd, mo, st, ft)][1] += vim * sc_
print("%-28s peak cold-soak hour %d; %d TankVaporGenerated, %d soak-day TVG rows,"
      % ("venting chain:", peak_hour, len(tvg), len(TVG)))
print("%-28s %d HourlyTVV rows, of which %d are non-zero"
      % ("", len(htvv), sum(1 for v in htvv.values() if v[0] != 0.0)))

# ============================================================================
# TVV-8 -- WeightedMeanBaseRate. Two inserts writing disjoint operating modes:
# the cold-soak insert (151) carries the venting chain forward; the operating /
# hot-soak insert (150, 300) is EmissionRateByAge-driven.
# ============================================================================
sb_of = {r["sourceBinID"]: r for r in T("sourcebin")}
ppmy_links = {(r["polProcessID"], r["modelYearID"], r["modelYearGroupID"])
              for r in T("pollutantprocessmodelyear")}
age_of_group = collections.defaultdict(list)
for r in T("agecategory"):
    age_of_group[r["ageGroupID"]].append(r["ageID"])
stmy_of = {r["sourceTypeModelYearID"]: r for r in T("sourcetypemodelyear")}
RS_HOURDAY = sorted(HD[d] for d in DAYS)

sbdfu_by_stmy = collections.defaultdict(list)
for (stmy_id, b), v in sbdfu.items():
    sbdfu_by_stmy[stmy_id].append((b, v))

wmbr = collections.defaultdict(lambda: [0.0, 0.0, 1.0])

# The cold-soak insert -- opModeID 151.
COLD_SOAK, HOT_SOAK, OPERATING = 151, 150, 300
for (rc, age, pp, hd, mo, st, ft), (v, vim) in htvv.items():
    my = YEAR - age
    for b, sbaf_v in sbdfu_by_stmy.get(st * 10000 + my, ()):
        bin_ = sb_of.get(b)
        if bin_ is None or bin_["fuelTypeID"] != ft or bin_["regClassID"] != rc:
            continue
        if bin_["fuelTypeID"] not in evap_ft:
            continue
        if (pp, my, bin_["modelYearGroupID"]) not in ppmy_links:
            continue
        k = (pp, st, rc, ft, mo, hd, my, COLD_SOAK)
        wmbr[k][0] += sbaf_v * v
        wmbr[k][1] += sbaf_v * vim

# The operating / hot-soak insert -- opModeID 150 and 300, with TVV-8's
# temperature / RVP adjustment on mode 300 for fuel types 1 and 5.
knots = collections.defaultdict(list)
for r in T("evaprvptemperatureadjustment"):
    knots[r["fuelTypeID"]].append((f(r["RVP"]), (f(r["adjustTerm3"]), f(r["adjustTerm2"]),
                                                 f(r["adjustTerm1"]), f(r["adjustConstant"]))))
RVP_TERMS = {}
for ft, ks in knots.items():
    if ft not in ATG_RVP:
        continue                     # the SQL refills averageTankGasoline from this join
    allk = ks + [(-1.0, min(ks)[1]), (1000.0, max(ks)[1])]
    v = ATG_RVP[ft]
    lo = max((k for k in allk if k[0] <= v), key=lambda k: k[0])
    hi = min((k for k in allk if k[0] > v), key=lambda k: k[0])
    RVP_TERMS[ft] = tuple(lo[1][i] + (hi[1][i] - lo[1][i]) / (hi[0] - lo[0]) * (v - lo[0])
                          for i in range(4))
eta = T("evaptemperatureadjustment")[0]


def operating_adjustment(temp, ft):
    """TVV-8: the cubic evapTemperatureAdjustment in max(T, 40) times the cubic
    RVP-interpolated averageTankGasoline polynomial in T (unity below 40 degF)."""
    tf = max(temp, 40.0)
    ta = (f(eta["tempAdjustTerm3"]) * tf**3 + f(eta["tempAdjustTerm2"]) * tf**2
          + f(eta["tempAdjustTerm1"]) * tf + f(eta["tempAdjustConstant"]))
    t3, t2, t1, c = RVP_TERMS.get(ft, (0.0, 0.0, 0.0, 1.0))
    ra = (t3 * temp**3 + t2 * temp**2 + t1 * temp + c) if temp >= 40.0 else 1.0
    return ta * ra


for e in T("emissionratebyage"):
    if e["polProcessID"] != PP:
        continue
    bin_ = sb_of.get(e["sourceBinID"])
    if bin_ is None or bin_["fuelTypeID"] not in evap_ft:
        continue
    for age in age_of_group.get(e["ageGroupID"], []):
        my = YEAR - age
        sbaf_v = sbdfu.get((ST * 10000 + my, e["sourceBinID"]))
        if sbaf_v is None:
            continue
        s = stmy_of.get(ST * 10000 + my)
        if s is None or s["sourceTypeID"] != ST:
            continue
        if (PP, my, bin_["modelYearGroupID"]) not in ppmy_links:
            continue
        for hd in RS_HOURDAY:
            hr = hourday_of[hd][1]
            adj = (operating_adjustment(amb[hr], bin_["fuelTypeID"])
                   if e["opModeID"] == OPERATING and bin_["fuelTypeID"] in (1, 5) else 1.0)
            k = (PP, ST, bin_["regClassID"], bin_["fuelTypeID"], MONTH, hd, my, e["opModeID"])
            wmbr[k][0] += sbaf_v * f(e["meanBaseRate"])
            wmbr[k][1] += sbaf_v * f(e["meanBaseRateIM"])
            wmbr[k][2] = adj

# ============================================================================
# TVV-1 and TVV-9 -- the I/M merge and the output row.
# ============================================================================
im_adjust = collections.defaultdict(float)          # TVV-1; imCoverage is empty
assert not T("imcoverage"), "imCoverage is non-empty: TVV-1's blend is no longer inert"
real_days = {r["dayID"]: f(r["noOfRealDays"]) for r in T("dayofanyweek")}
assoc = {r["polProcessID"]: r for r in T("pollutantprocessassoc")}[PP]
process_id, pollutant_id = assoc["processID"], assoc["pollutantID"]

rows, by_mode, sccs = collections.defaultdict(float), collections.defaultdict(float), {}
for k, (rate, rate_im, adj) in wmbr.items():
    _, st, rc, ft, mo, hd, my, om = k
    frac = omd.get((hd, om))
    if frac is None:
        continue                                    # inner join OpModeDistribution
    sh = source_hours.get((hd, YEAR - my))
    if sh is None:
        continue                                    # inner join SourceHours
    d = hourday_of[hd][0]
    q = rate * adj * sh * frac / real_days[d]
    a = im_adjust.get((process_id, pollutant_id, my, ft, st), 0.0)
    q = max(rate_im * adj * sh * frac / real_days[d] * a + q * (1.0 - a), 0.0) if a else q
    rows[(d, ft, my)] += q
    by_mode[om] += q
    sccs[(d, ft, my)] = "%d" % (22 * 10**8 + ft * 10**6 + st * 10**4
                                + LINK_ROAD * 10**2 + process_id)


def worst(computed, expected, label, tol, absolute=False):
    """Compare two dicts on identical key sets and ASSERT the tolerance."""
    assert set(computed) == set(expected), (
        "%s: key sets differ (%d computed, %d expected, %d only in one)"
        % (label, len(computed), len(expected), len(set(computed) ^ set(expected))))
    w, wk = 0.0, None
    for k in expected:
        a, b = computed[k], expected[k]
        e = abs(a - b) if absolute else abs(a - b) / max(abs(b), 1e-30)
        if e > w:
            w, wk = e, k
    assert w <= tol, "%s: worst error %.4e at %s exceeds %.1e" % (label, w, wk, tol)
    print("%-28s %5d cells, worst %s error %.3e (tolerance %.0e)"
          % (label + ":", len(expected), "absolute" if absolute else "relative", w, tol))
    return w


# ------------------------------------------------------------------- compare
worst({(hd, a): v for (rt, hd, a), v in sho.items() if rt == LINK_ROAD},
      {(r["hourDayID"], r["ageID"]): f(r["SHO"]) for r in T("sho")}, "SHO", 1e-5)
worst(source_hours,
      {(r["hourDayID"], r["ageID"]): f(r["sourceHours"]) for r in T("sourcehours")},
      "SourceHours", 1e-5)
worst(sbdfu,
      {(r["sourceTypeModelYearID"], r["sourceBinID"]): f(r["sourceBinActivityFraction"])
       for r in T("sourcebindistributionfuelusage_12_26161_2020")},
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
worst(dict(rows), expected, "emissionQuant", 2e-5)

print("%-28s %d cohorts x %d day types = %d rows, exact; SCCs %s"
      % ("key set:", len(rows) // len(DAYS), len(DAYS), len(rows), sorted(set(sccs.values()))))
print("%-28s %.6f g computed / %.6f g in MOVESOutput"
      % ("total THC:", sum(rows.values()), sum(expected.values())))

# ---------------------------------------- section 0.3: where the zero enters
cold_rates = [v[0] for k, v in wmbr.items() if k[7] == COLD_SOAK]
assert any(r != 0.0 for r in cold_rates), \
    "the venting chain produced no cold-soak base rate at all -- section 0.3's " \
    "measurement is about a zero WEIGHT, and would be vacuous if it were a zero RATE"
print("%-28s %d cold-soak (151) base rates, max %.6f g/h, opModeFraction %.1f"
      % ("zero-weighted:", len(cold_rates), max(cold_rates), omd[(RS_HOURDAY[0], COLD_SOAK)]))
print("%-28s contribution by operating mode: %s"
      % ("", {m: round(v, 6) for m, v in sorted(by_mode.items())}))
assert by_mode[COLD_SOAK] == 0.0 and by_mode[HOT_SOAK] == 0.0, \
    "a soak mode contributed to the output; section 0.3 needs remeasuring"
print("%-28s nothing; every table above is an INPUT of the execution database"
      % "read from the reference:")
```

### 6.6 What the reproduction is for

Attribution. When `fixtures/process-evap-fvv.esm` disagrees with the snapshot, a
third implementation says whether the document or the specification is wrong.
It is also the only place the venting half of the calculator is executed at all,
so it is what makes §0.3's zero a measurement.

---

## 7. Fidelity notes and tolerance

### 7.1 Everything agrees to 7.5 × 10⁻⁶, and that number is the reference's storage

```
SHO                        82 cells, worst relative error 3.610e-06
SourceHours                82 cells, worst relative error 3.610e-06
sourceBinDistribution     125 cells, worst relative error 3.449e-06
OpModeDistribution          6 cells, worst absolute error 0.000e+00
ColdSoakTankTemperature    24 cells, worst relative error 7.550e-07
QuarterHourTemperature     96 cells, worst relative error 1.175e-14
emissionQuant             128 cells, worst relative error 7.495e-06
```

`MOVESOutput.emissionQuant` is a `DECIMAL(20,12)` fed from a `FLOAT` working
column, i.e. six significant figures; `7.495e-06` is that storage, not
accumulated error. `OpModeDistribution` matching to **0.000e+00 absolute** on
all six rows is the strongest single check in this document — it is the
quantity §0.3 turns on.

The recommended tolerance is `2e-5` per cell, the same gate
`docs/evap-leaks.md` §7.4 recommends and `tolerance.toml` already applies to the
evaporative slices. **No per-fixture override is needed and none was added.**

### 7.2 Which inputs are load-bearing — measured, one at a time

The perturbation sweep of §0.3 is reproducible from the extracted oracle:
copy it, apply one edit, and compare all 128 cells against the unperturbed run
bit for bit. The four zero-effect results in §0.3's table are not "below
tolerance"; they are byte-identical output.

The complementary measurement is that the operating-mode half **alone**
reproduces all 128 cells: deleting TVV-2 … TVV-7, the soak recurrence and
TVV-8's cold-soak insert entirely, and keeping only `EmissionRateByAge ×
sourceBinActivityFraction × adjustment × sourceHours ÷ noOfRealDays`, gives the
same worst-cell error of 7.495e-06 and the same 558.971771 g total.

`AverageTankGasoline.RVP` is the one new input that moves the answer:
setting `rvpAdjustment = 1` (which is what a port that skipped
`TankFuelGenerator` would get) gives **574.552554 g** against the reference's
558.971807 g — a 2.79 % total error and 3.59 % on the worst cell, uniform within
each fuel type at exactly 0.972879747…0.972888089 (fuel 1) and
0.965375393…0.965386279 (fuel 5). A constant per-fuel-type ratio is what
identified the missing factor as the RVP adjustment and nothing else.

### 7.3 Fidelity notes carried from `moves.rs`

* The SQL stores every working-table measure in a 32-bit `FLOAT` while MariaDB
  evaluates in `DOUBLE`. Both `moves.rs` and this port compute in `f64` end to
  end and do not reproduce the inter-step truncation — a sub-1e-7 relative
  drift, and below the reference's own storage.
* TVV-2's pack/unpack ranking idiom is computed in exact integer arithmetic
  rather than through the SQL's `mod` on a float.
* The barometric interpolation uses the SQL's literal endpoints verbatim; there
  are no integer/integer literal divisions, so MariaDB's
  `div_precision_increment` rounding does not arise.
* The `WithRegClassID` / `NoRegClassID` toggle resolves to `WithRegClassID`
  (`BundleUtilities` force-enables it); only that variant is ported, per the
  established scripted-calculator precedent.

---

## 8. What is not computed, and what is not exercised

### 8.1 What this fixture cannot check, even with the whole chain computed

Everything in §0.3's zero-effect table, and in addition:

| | why |
|---|---|
| TFG's market-share weighting and its denominator | one formulation per fuel type at share 1 (§2.5) |
| TFG's commingling step function | `gasoholMarketShare = 1.0` → factor 1.000 |
| TFG's weathering | `ratioGasolineRVPLoss` clamps to 0 |
| TFG's year multiplicity | exactly 1 |
| TFG's NULL propagation through `gasPortionRVP` | both kept formulations have non-NULL `RVP` and `ETOHVolume` |
| TVV-5's `sqrt` clamp on a negative discriminant | never reached |
| TVV-1's I/M merge and TVV-9's blend | `imCoverage` empty |
| the `subjectToEvapCalculations` and `PollutantProcessModelYear` filters | neither removes a row |
| TVV-6's "missing temperature falls through" arm | all 24 hours have a temperature |
| TVV-2's peak-hour ranking, including its tie-break | only the venting half reads `peakHourID` |

Every one of these was confirmed by sabotage rather than by reading: forcing
`peakHourID` to 24, for instance, leaves `./run-fvv-oracle.sh` at exit 0 with
every number unchanged, which is §0.3 arriving from a fourth direction.

The three TFG mechanisms are the ones most worth a probe test rather than a
fixture check, because unlike the venting chain they are *upstream of a
load-bearing quantity* — a fixture cannot see them, but a wrong one would move
the RVP and therefore the answer.

### 8.2 `ColdSoakInitialHourFraction` and `SoakActivityFraction` are read, not computed

Both are `TankTemperatureGenerator` outputs captured in the execution database,
and both are downstream of TTG-2/TTG-3/TTG-4 — the walk over
`SampleVehicleTrip`'s 37,216 rows whose outermost recurrence is finding **F28**
(a predecessor named by a data column). `docs/evap-permeation.md` §8.1 sizes
that walk and the reasoning is unchanged.

Reading them is consistent with `docs/evap-leaks.md`'s "reads nothing from the
reference": they are **input tables of the execution database**, in the same
standing as `emissionRateByAge` or `sourceTypeAgeDistribution`, not rows of the
output database. `soakActivityFraction` is read by the leaks and permeation
oracles on the same footing. The distinction the phrase draws is
input-database versus output-database, and this document keeps it.

`docs/evap-permeation.md` §8.2 called TTG-7 a prerequisite that "cannot be
reached past". It is reached past here in exactly the sense that matters: it
*is* computed forward through TVV-7 from the captured table, and §0.3's ×7
perturbation shows the whole path it feeds contributes nothing.

### 8.3 What a slice would have to change to exercise the soak chain

Stated because three consecutive evaporative slices have now failed to, for one
structural reason (§0.3, consequence 2).

`fractionOfOperating = min(1, Σ SHO / Σ SourceHours)`, and A10 sets
`SourceHours = SHO` at an **on-network** link, so the ratio is identically 1 and
E2's `1 − fractionOfOperating` is identically 0. The soak modes can carry weight
only when `SourceHours > SHO`, which happens when the run has an **off-network
link** — `roadTypeID` 1, where `SourceHours` comes from `SHP` (source hours
parked) instead. Every one of these three snapshots has exactly one link, on
road type 4.

So the next slice that would answer the recurrence question is one whose RunSpec
selects road type 1, not one that picks a different evaporative process. That is
a snapshot that does not currently exist in
`../moves.rs/characterization/snapshots`, and generating it is upstream work.

### 8.4 Things deliberately not modelled

`NewTVVYear` (which aggregates `cumTVVCoeffs` into the two `stmyTVV*` tables by
the sample-vehicle regulatory-class fractions) and `FillSampleVehicleSoaking`
(which derives the five-soak-day fractions from the trip tables) are
conditionally-enabled setup sections, not the per-bundle venting algorithm.
Both had already run when the snapshot was taken — `stmyTVVCoeffs2020`,
`stmyTVVEquations2020` and `sampleVehicleSoaking` are all present and non-empty
— and `moves.rs` takes all three as inputs for the same reason. The
`-- Section Debug` blocks build debug-only tables that feed no output.

---

## 9. Summary for the `.esm` author

1. The activity, cohort and operating-mode stages are `docs/evap-leaks.md`'s,
   unchanged, with `isRegClassReqd = 'Y'` (leaks', not permeation's).
2. `TankFuelGenerator` must be computed — the table is empty — and its RVP is
   load-bearing through TVV-8, not through TVV-3.
3. TVV-8's operating-mode half plus TVV-9 reproduces all 128 cells to
   7.495e-06. That is the whole of what the fixture can check.
4. The venting half is real, computable, and multiplied by exactly zero.
   Do not put an unverifiable transcription of it in a component; §0.3's
   perturbations show what a fixture-level check of it would be worth.
5. TVV-5's equations are two forms and eighteen coefficient rows (§2.10), not
   2,188 strings and not an expression evaluated out of a table cell.
