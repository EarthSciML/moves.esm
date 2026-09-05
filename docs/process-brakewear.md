# `process-brakewear` — computation specification

The port specification for the first fixture that emits **more than one
pollutant-process**, written to the method of `docs/mixed-onroad.md`: the input
inventory determined from evidence, the chain with source lines into
`../moves.rs`, every join with its exact key pairs, and worked examples whose
numbers can be checked by hand.

It is short where `docs/mixed-onroad.md` is long, and deliberately so. **Brake
wear is a rate on the `BaseRateCalculator` spine, not a different model.** The
activity chain, the cohort structure, the fuel-usage rebase and the drive-cycle
operating-mode weights are that document's, unchanged, and are not restated
here. What this document specifies is the four things that are new:

1. the run emits three pollutant-processes instead of one, and one cohort key
   — the source bin's `shortModYrGroupID` — **differs between them** (§2.2);
2. PM10 brake wear is **chained** off PM2.5 brake wear by a tabulated ratio and
   has no rate of its own (§2.4);
3. the same `W` serves both rate paths, and the operating mode that would make
   that false is measured to be inert (§3.2);
4. the EV temperature adjustment's **non-zero arm is live** at this hour, and
   reaching it needed a lookup precedence `mixed-onroad` did not implement
   (§2.5) — which is how a latent defect in that fixture was found.

---

## 0. The fixture at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/process-brakewear.xml` |
| Model | ONROAD, `modelscale` `Inv` (inventory), `modeldomain` `DEFAULT` |
| Geography | county 26161 (Washtenaw, Michigan), zone 261610, link 2616104 |
| Time | year 2020, month **8**, hour **7**, day types **2 (weekend) and 5 (weekday)** |
| Vehicles | sourceTypeID 21 (passenger car); fuel types **1, 2, 5, 9** |
| Road | roadTypeID 4 (urban restricted access) |
| Pollutant/process | **9101** (Total Energy × Running Exhaust), **11609** (PM2.5 Brakewear × Brakewear) and **10609** (PM10 Brakewear × Brakewear, *chained*) |
| Model years | 1980–2020 (41) |
| Output | `db__out_process_brakewear__movesoutput`, **750 rows** |
| Output units | energy in Million BTU, particulate in **grams**, `outputtimestep` **Hour** |
| Calculator path | `TotalActivityGenerator` → `SourceBinDistributionGenerator` → `BaseRateGenerator` → `BaseRateCalculator` → **`PM10BrakeTireCalculator`** → output aggregation |
| Snapshot | 372 tables, **237 non-empty** |

### 0.1 The RunSpec on disk does not describe the captured run

The same rule as `docs/mixed-onroad.md` §0.1, and for the same reason: the XML's
`<month key>`, `<beginhour key>` and `<day key>` are canonical `RunSpecXML`
**0-based indices into sorted ID lists**, not identifiers. The authority is the
execution database's own `runspec*` tables.

| dimension | `process-brakewear.xml` says | the execution database says |
|---|---|---|
| month | 7 | **8** (`runspecmonth`) |
| hour | 6 | **7** (`runspechour`) |
| day types | 5 | **2 and 5** (`runspecday`, 2 rows) |
| fuel types | 1 | **1, 2, 5, 9** (`runspecsourcefueltype`, 4 rows) |
| pollutant/process | 10609, 11609, 9101 | **9101, 10609, 11609** (`runspecpollutantprocess`) |

The pollutant/process row is the one line of that table that is *not* a
correction: the XML and the execution database agree on the set, and only the
order differs. `runspecpollutantprocess` is read in file order and that order —
9101, 10609, 11609 — is the order of the output relation's three blocks.

The fuel expansion is genuine MOVES behaviour rather than a stale capture: a
single `(21, 1)` `onroadvehicleselection` becomes all four `(21, f)` pairs
because `ExecutionRunSpec` expands each selected source type over every fuel
type `fuelengtechassoc` lists for it.

### 0.2 Why 750 rows, and what the three blocks are

```
750 = 3 pollutant-processes  x  125 (modelYearID, fuelTypeID) cohorts  x  2 day types
```

The 125 is the same ragged set as `mixed-onroad`'s — 41 gasoline model years, 40
diesel, 23 E85 and 21 electricity — and it is **the same 125 for both computed
pollutant-processes**, which the fixture asserts rather than assumes
(`pp_selectedCohortCount` = 125, 0, 125). The middle zero is PM10 brake wear:
`pollutantprocessmodelyear` carries no 10609 rows, so it has no source-bin
distribution of its own, and its 250 output rows arrive through the chain.

**Why the run carries an energy pollutant at all.** The RunSpec's own
`<description>` says: brake wear alone makes the Go `BaseRateGenerator` panic on
the missing `sourceUseTypePhysicsMapping` table, which MOVES only builds when a
running-exhaust process is selected. So 9101 is a carrier, and its 250 rows are
`mixed-onroad`'s 250 rows at a different hour. That is a gift for this port: one
third of the answer is already checked end to end by an existing fixture, and a
disagreement can be attributed to the brake-wear half immediately.

**No start exhaust, again.** `BaseRateGenerator` emits start-exhaust rates on
road type 1 and `BaseRateCalculator` joins its rate tables to `runSpecRoadType`,
which is `{4}` — see `docs/mixed-onroad.md` §0.2. Brake wear is *not* road-type
gated (`GenericCalculatorBase.doExecute` gates only start and extended-idle),
which is why it survives where the eight zero-row fixtures do not.

---

## 1. Input inventory

### 1.1 The tables `mixed-onroad` already reads

All 46 of them, unchanged, against this snapshot's copies. `docs/mixed-onroad.md`
§1.2–§1.4 is the inventory; nothing was added to or removed from the activity,
cohort or drive-cycle stages.

Two of those tables carry **more** here than they do there, and both differences
are load-bearing:

| table | in `mixed-onroad` | here |
|---|---|---|
| `emissionrate` | 69,200 rows, polProcessID 9101 only | **60,388 rows over two**: 57,040 for 9101 across 23 operating modes and 3,348 for 11609 across six |
| `pollutantprocessmodelyear` | 222 rows, two pollutant-processes' worth, one of them consulted | 222 rows, **both** consulted, and they disagree — §2.2 |

### 1.2 The three tables this fixture adds

| table | rows | what it carries |
|---|---:|---|
| `runspecpollutantprocess` | 3 | 9101, 10609, 11609 — the run's whole pollutant scope, and the output relation's block axis |
| `runspecchainedto` | 1 | `10609 ← 11609`: MOVES's own statement that PM10 brake wear is derived, not rated |
| `pm10emissionratio` | 8 | `PM10PM25Ratio` by (polProcessID, sourceTypeID, fuelTypeID, model-year range) |

`pm10emissionratio`'s eight rows are two model-year ranges (1940–2010 and
2011–2060) over the four fuel types:

| fuel | 1940–2010 | 2011–2060 |
|---|---|---|
| 1 gasoline | 8.0 | 2.60985 |
| 2 diesel | 8.0 | 2.60985 |
| 5 E85 | 8.0 | 2.60985 |
| 9 electricity | 8.0 | **1.42475** |

A port that dropped the range predicate would be a factor of three out on half
the rows; one that dropped the fuel key would be 83 % out on the electricity
rows of the newer range.

### 1.3 What is NOT an input

`baserate_1_2020` (250 rows), `baserate_9_2020` (250 rows),
`sourcebindistribution` (250 rows), `sho` (82 rows) and `MOVESOutput` (750 rows)
are all generator or expected output. None is a `data_sources` entry that
anything reads. Values out of the first four appear as `expected` in the
fixture's inline tests, which is the opposite direction.

`baseratebyage_1_2020`, `baseratebyage_9_2020`, `emissionratebyage`,
`ratesopmodedistribution` and `opmodedistribution` are all **captured empty**,
which is what says the age-resolved and the pre-computed-op-mode paths are not
taken.

---

## 2. The computation chain

### 2.1 What is unchanged

S1–S9 (activity), S10–S12 (cohorts and the fuel-usage rebase), the drive-cycle
classification and `W` (S13a), and the output stage's group-by and SCC (S16–S18)
are `docs/mixed-onroad.md` §2.1–§2.4 verbatim. The activity half is *shared*:
brake wear is weighted by the same source-hours-operating as running-exhaust
energy, so an error in it moves all 750 rows and not 250 of them.

### 2.2 The rate relation, and why it has to exist

`mixed-onroad` emits one pollutant-process, so `run_polProcessID` is a run-level
scalar and every rate column is keyed by the cohort alone. Three
pollutant-processes make that impossible, because **one cohort key differs
between them**:

```
pollutantprocessmodelyear     modelYearGroupID       modelyeargroup.shortModYrGroupID
  (9101,  2020)                     2020                       40
  (11609, 2020)                 20112020                        6
  (9101,  1980)                     1980                       80
  (11609, 1980)                 19501980                        1
```

9101 resolves a model year to a two-digit **year** code; 11609 resolves it to one
of six **decade bands**. `shortModYrGroupID` is one of the six components packed
into `emissionrate.sourceBinID`, so the same cohort meets a different source bin
on each rate path. A document that computed one short group per cohort would read
3,348 of `emissionrate`'s rows with the wrong bin and produce a brake-wear rate
of exactly zero.

**A join key column has to be one-dimensional** (`join.rs`: a key resolves
through a declared 1-D variable's single axis). So a two-dimensional
`ppCoh_shortModYrGroupID[polProcess, cohort]` cannot be a key, and the rate stage
is instead carried on a **flat relation whose rows are the cross product**:

```
rate_rows  =  n_runspecpollutantprocess  x  (n_agecategory x n_runspecsourcefueltype)
           =  3 x 164  =  492 rows
```

every factor a discovered extent, pollutant-process major. Its columns are read
back from the pollutant-process relation and from the cohort relation by two
ordinal joins, so nothing about either is restated. This is
`docs/esm-conventions.md` §2 — *tables stay tables* — applied to a derived
relation, and it is the whole structural difference between this fixture and
`mixed-onroad`.

The model-year *sets* the two pollutant-processes admit are identical (41 each),
which is what lets one cohort rank serve all three output blocks. That is a
property of the data, not an assumption: `pp_selectedCohortCount` computes it per
pollutant-process and a test pins it at 125, 0, 125.

### 2.3 The brake-wear base rate

Structurally identical to `docs/mixed-onroad.md` §2.3, with every
pollutant-process-keyed lookup now reading `rt_polProcessID`:

```
rtMode_rate[b, om]        = emissionrate.meanBaseRate  ⋈ (polProcessID, opModeID,
                                shortModYrGroupID, regClassID, engTechID, fuelTypeID)
rtMode_weightedRate[b, om]= usedFraction[b] x evSalesFactor[b] x rtMode_rate[b, om]
rtDay_meanBaseRate[b, k]  = Σ over om of  W[k, om] x rtMode_weightedRate[b, om]
```

Every one of the adjustment tables `BaseRateCalculator` consults is keyed by
`polProcessID`, and **none of them carries an 11609 row**:

| table | 9101 rows | 11609 rows | effect on brake wear |
|---|---:|---:|---|
| `fullacadjustment` | 23 | 0 | A/C increment exactly 0, by the LEFT-JOIN treatment of J23 |
| `fleetavgadjustment` | 11 | 0 | EV-sales back-scaling factor exactly 1 |
| `temperatureadjustment` | 1 | 0 | temperature factor exactly 1 (standard quadratic, zero terms) |
| `evefficiency` | 7 | 0 | no divisor on its electricity rows |

Every one of those zeros and ones is **computed**, through the existence
aggregate that sits beside each value aggregate, and not written down. The last
row of that table is the one with teeth: `lib/onroad_activity.esm`'s
`ev_energy_divisor` floors its product at `1e-300`, so an electricity cohort with
no `evefficiency` row would divide by that floor and return an infinity. The
document therefore passes `rt_appliesEvDivisor` — *electric* **and** *has a row*
— rather than `rt_isElectric`, which is the LEFT-JOIN reading of
`adjust.rs:611-616` and the argument the template actually wants.

### 2.4 The PM10 chain

`PM10BrakeTireCalculator` is a *chained* calculator: it subscribes to no
MasterLoop stage and hangs off `BaseRateCalculator`'s output
(`crates/moves-calculators/src/calculators/pm10.rs`, `calculator-dag.json`
records `subscribes_directly: false`, `depends_on: ["BaseRateCalculator"]`). Its
whole processing section is one multiply:

```
PM10 emissionQuant = PM2.5 emissionQuant  x  PM10PM25Ratio
```

with the ratio resolved by an inner join on `(polProcessID, sourceTypeID,
fuelTypeID)` and a model-year range that brackets the row's `modelYearID`.

The `.esm` spells that as a **self-join of the rate relation**, because the
chained row and the row it is chained from are two rows of one relation:

```
rtDay_quantChained[b, k] = rt_chainRatio[b]
                           x  Σ over b2 of rtDay_quantDirect[b2, k]
                              gated on  rt_chainInputPolProcessID[b] = rt_polProcessID[b2]
                                   and  rt_cohortOrdinal[b]          = rt_cohortOrdinal[b2]
rtDay_quant[b, k]        = rtDay_quantDirect[b, k] + rtDay_quantChained[b, k]
```

The clause names its two sides with `syms` (CONFORMANCE_SPEC §5.5.8), as
`coh_usedFraction` already does for the fuel-usage rebase.

**Three things make this one expression serve all three blocks with no branch,
and all three are measured rather than assumed.**

* On an unchained rate row `rt_chainInputPolProcessID` is **0** — the additive
  identity of the LEFT JOIN onto `runspecchainedto`, and no pollutant-process —
  so the gate matches nothing.
* On an unchained rate row `rt_chainRatio` is **0**, because `pm10emissionratio`
  carries polProcessID 10609 and nothing else.
* On the chained rate row `rtDay_quantDirect` is **exactly 0**, because
  `emissionrate` has no 10609 row and J22's inner join leaves its rate at the
  additive identity. The fixture asserts that zero directly.

So the sum is a union, never a double count, and `run_chainedRowCount` (125)
counts the rate rows that arrive through it.

**The unit divisor moves with the pollutant.** `engine.rs:1286-1310` applies the
kilojoule-to-Million-BTU conversion to pollutants 91, 92 and 93 and to nothing
else, so `rspp_unitDivisor` is 1,055,055.9 on the energy block and exactly 1 on
both particulate blocks. `mixed-onroad` divides unconditionally because it emits
one pollutant; this is the first fixture that has to test.

### 2.5 The adjustment that is live here, and the defect it found

At hour 7 the zone temperature is **59.5 °F** (`zonemonthhour`), against
`mixed-onroad`'s 66.9 °F at hour 9. Two clamps sit on that number and they go
opposite ways.

**(a) The A/C factor is still exactly zero.** With
`monthgrouphour[8, 7]` = (A −3.63154, B 0.072465, C −0.000276):

```
-3.63154 + 59.5 x (0.072465 - 0.000276 x 59.5)
  = -3.63154 + 59.5 x 0.056043
  = -3.63154 + 3.3345585
  = -0.2969815        ->  clamp to 0  ->  ACFactor = 0
```

Further from its boundary than `mixed-onroad`'s −0.0189, not closer.

**(b) The EV temperature factor is 1.015625, and does NOT clamp.**
`adjust.rs:107-124`, for pollutant 91 × process 1 × fuel 9:

```
adj = (T - 72)(a + b(T - 72));  if adj < 0 { adj = 0 }
if sourceTypeID < 40 && heatIndex > 67.0 { adj = 0 }
factor = 1 + adj
```

With `a = 0.00225`, `b = 0.00028` and `T = 59.5`:

```
(59.5 - 72) x (0.00225 + 0.00028 x (59.5 - 72))
  = (-12.5) x (0.00225 - 0.0035)
  = (-12.5) x (-0.00125)
  = +0.015625          ->  positive, no clamp  ->  factor 1.015625
```

and the heat-index suppression does not fire because 59.5 < 67.0. All 84
energy × electricity rows carry that factor.

**Getting those coefficients needed a lookup step `mixed-onroad` does not have,
and that is a defect in `mixed-onroad` this fixture found.**
`temperatureadjustment` has exactly one row, keyed `polProcessID 9101,
fuelTypeID 9, regClassID **0**, model years 1950–2060`. `regClassID 0` is a
**wildcard**: `adjust.rs:495-520` looks the row up by the exact `regClassID`
first — 20 for a light-duty passenger car — and by the `regClassID 0` row second,
defaulting to zero-valued terms only if neither exists.

`fixtures/mixed-onroad.esm` implemented only the first step. Its terms therefore
came out 0, its raw adjustment 0 instead of the −0.00419 its own
`docs/mixed-onroad.md` §2.3(e) writes out, and the `adj < 0` clamp returned the
same factor of 1 **for the wrong reason**. At 66.9 °F that is invisible; at
59.5 °F it is a 1.56 % error on 84 rows, and it is how the missing step was
found — the retargeted fixture reproduced its 250 energy rows at a worst cell of
**1.539 × 10⁻²**, all of it on fuel 9, at exactly `1/1.015625`.

The precedence is now `lib/adjustments.esm`'s **`exact_else_wildcard`**, a
three-parameter template over the two lookups' results, and **both fixtures
instantiate it**. `mixed-onroad`'s numbers are unchanged to the last digit
(250/250, worst cell 8.320 × 10⁻⁶), which is what says the fix is a completion
and not a correction there.

The wildcard's second lookup is spelled as a `join.on` against a one-row relation
carrying the constant 0 (`run_regClassWildcardID`), not as an `==` inside a
`filter` — `docs/esm-conventions.md` §20.4.

---

## 3. Join structure

### 3.1 The joins this fixture adds

`docs/mixed-onroad.md` §3's J1–J34 all survive. Five are new, and two of the old
ones acquire a key pair.

| id | left | right | key pairs |
|---|---|---|---|
| **J35** | `rspp_polProcessID` | `rct_outputPolProcessID` | 1 — the chain declaration, a LEFT JOIN whose miss is 0 |
| **J36** | `rt_polProcessID`, `rt_fuelTypeID`, `run_sourceTypeID` | `pmr_*` | 3, plus the inclusive model-year range predicate |
| **J37** | `rt_polProcOrdinal` | `rspp_ordinal` | 1 — the rate relation's pollutant-process factor |
| **J38** | `rt_cohortOrdinal` | `coh_ordinal` | 1 — its cohort factor |
| **J39** | `rt_chainInputPolProcessID`, `rt_cohortOrdinal` | `rt_polProcessID`, `rt_cohortOrdinal` | 2, `syms: [b, b2]` — the chain self-join |
| J20′ | `ppmy_modelYearGroupID` | `myg_modelYearGroupID` | resolved **at the `pollutantprocessmodelyear` row** rather than at the cohort, so the short group is a one-dimensional column |
| J22′ | as J22 | | `run_polProcessID` → `rt_polProcessID`: the composite gate is unchanged, its first pair is now a column of the rate relation |

J22 remains **one clause carrying six key pairs**, which is a cost decision and
not a reading order — `docs/esm-conventions.md` §25 and `docs/mixed-onroad.md`
§10.3, where splitting it was measured at 43× on the 164 × 60 version. Here it
gates 492 × 60 output cells against 60,388 rate rows.

### 3.2 Operating mode 501, and why `W` is the same for both rate paths

This is the one place where a reader would reasonably expect brake wear to need
its own drive-cycle weights, and it does not.

`emissionrate` carries 11609 rates for six operating modes — 0, 1, 11, 21, 33 and
**501** — and `opmodepolprocassoc` associates all 24 running modes with 11609,
including 501, `brakewear;stopped`. `BaseRateGenerator` has an explicit
brake-wear branch for it
(`generators/baserategenerator/drivecycle.rs:545`, `:581-590`):

```rust
for &op_mode_id in &op_modes_to_iterate {
    if pol_process_id != 11609 && op_mode_id == 501 { continue; }
    ...
    if pol_process_id != 11609 {
        if op_mode_id == 501 { continue; }
        else if op_mode_id == 1 {
            op_mode_fraction += detail.op_mode_fractions.get(&501)...;  // fold into idle
        }
    }
```

So for every pollutant-process **except** 11609, mode 501's share is folded into
idle; for 11609 it is kept separate. If mode 501 ever carried a share, brake wear
and energy would need different weight vectors.

**It never does, and there are two independent measurements to that effect.**

1. **The classification never produces it at this scale.**
   `drivecycle.rs:235-237` assigns a zero-speed second to mode 501 only when
   `is_project`, and to mode 1 otherwise:
   `detail.op_mode_id = if is_project { 501 } else { 1 }`. This RunSpec is
   `modelscale Inv`, `modeldomain DEFAULT`. The fixture's `dc_WModeCount` is
   **23 for both day types**, not 24, which is the document's own statement of
   that: 24 would mean the classification had taken the project-scale branch.
2. **The rate is zero even if it did.** All 558 of `emissionrate`'s 11609
   mode-501 rows carry `meanBaseRate` **exactly 0.0** — measured, `min = max =
   0.0` — so the fold and the split give the same answer whichever branch runs.

The consequence for what the fixture checks is stated in §7.2 rather than hidden:
brake wear's rate table covers **five** of `W`'s 23 modes (0, 1, 11, 21 and 33),
carrying 12.84 % of the weekend weight and 19.89 % of the weekday weight, so the
brake-wear rows are a *partial* independent check on `W` and the energy rows
remain the complete one.

---

## 4. Reusable shapes

One new `expression_template`, in `lib/adjustments.esm`:

**`exact_else_wildcard(has_exact, exact_value, wildcard_value)`** — the two-step
lookup precedence MOVES writes over and over: the exact key first, a designated
wildcard row second, and the aggregate's own additive identity third. Both arms
are separate aggregates over the same table with different key pairs; the
template is the precedence between their results. Instantiated four times here
(A and B terms, exact and wildcard) and twice in `fixtures/mixed-onroad.esm`.

Everything else is imported unchanged: `pol_process_id`, `pollutant_id_of`,
`process_id_of`, `null_output_column` from `lib/identifiers.esm`;
`weeks_per_month`, `share_of_group`, `onroad_scc`, `source_bin_slot`,
`ev_energy_divisor`, `kilojoules_per_million_btu` from `lib/onroad_activity.esm`;
all four drive-cycle shapes from `lib/drive_cycle.esm`.

`ev_energy_divisor` is used with a **different argument** than in `mixed-onroad`
— `rt_appliesEvDivisor` rather than `rt_isElectric` — for the reason §2.3 gives.
The template is unchanged: what the third parameter means is "the divisor
applies", and `mixed-onroad` could pass `isElectric` for it only because there
every electricity cohort had a row.

---

## 5. Literals and enums

`docs/mixed-onroad.md` §5 carries the fixture's enums. Two groups grow:

```
pollutant:  TotalEnergyConsumption 91, PetroleumEnergyConsumption 92,
            FossilFuelEnergyConsumption 93
process:    RunningExhaust 1, Brakewear 9
```

The three energy pollutants are named because `rspp_isEnergy` tests membership of
exactly that set (`engine.rs:1286-1310`), and writing the rule out is the point:
92 and 93 are not in this run and the test still has to admit them.

The two brake-wear pollutant ids, 106 and 116, are **not** enum members and are
never written down. They are unpacked from `runspecpollutantprocess`'s
`polProcessID` by `pollutant_id_of`, which is also how the SCC's process digit
and the output's `processID` column are reached.

---

## 6. Hand-checkable worked examples

### 6.0 Run-level values used by every example

| | |
|---|---|
| temperature, heat index | 59.5 °F (equal in every row of this snapshot) |
| A/C activity raw / clamped | −0.2969815 / **0** |
| EV temperature raw / factor | **+0.015625** / **1.015625** (energy × electricity only) |
| EV suppression | not fired (59.5 < 67.0) |
| days in month, weeks per month | 31, 31/7 |
| `noOfRealDays` | 2 (weekend), 5 (weekday) |
| average speed | 67.0416879 mph (weekend), 56.361205525 mph (weekday) |

### 6.1 Worked example A — MY 2020, gasoline, weekday, PM2.5 brake wear

```
rtDay_meanBaseRate[11609, MY2020/fuel1, day 5]  =  0.0432849892   g / source-hour
    (baserate_9_2020 stores 0.043285)
sho[hourDayID 75, ageID 0] = 260.0573039        (the sho table stores 260.057)
activity = 260.0573039 / 5 = 52.01146078        source-hours
emissionQuant = 0.0432849892 x 52.01146078 = 2.25131552 g
```

MOVESOutput stores **2.251310**. No unit conversion: pollutant 116 is mass.

### 6.2 Worked example B — the same row, PM10

```
PM10PM25Ratio(10609, sourceType 21, fuel 1, MY 2020 in 2011-2060) = 2.60985
emissionQuant = 2.25131552 x 2.60985 = 5.8755958 g
```

MOVESOutput stores **5.875590**, and 5.875590 / 2.251310 = 2.60984, so the two
particulate blocks check the chain against each other as well as against the
reference.

### 6.3 Worked example C — MY 1980, gasoline, weekend, both particulates

```
rtDay_meanBaseRate[11609, MY1980/fuel1, day 2] = 0.0322580879     (stored 0.0322581)
sho[hourDayID 72, ageID 40] = 2.4372787          (stored 2.43728)
activity = 2.4372787 / 2 = 1.21863936
PM2.5 = 0.0322580879 x 1.21863936 = 0.0393109755 g   (stored 0.039311)
PM10  = 0.0393109755 x 8.0        = 0.314487804  g   (stored 0.314488)
```

The ratio is 8.0 here and 2.60985 in §6.2 — the same cohort key, a different
model-year range — which is the assertion that the range predicate is doing
work.

### 6.4 Worked example D — MY 2000, electricity, weekday, Total Energy

The smallest cell in the fixture, and the one that exercises every remaining
factor at once: the live EV temperature arm, the EV efficiency divisor at its
largest, and the kilojoule conversion.

```
rtDay_meanBaseRate[9101, MY2000/fuel9, day 5] = 19.1614528  kJ / source-hour  (stored 19.1615)
EV temperature factor                          = 1.015625
EV energy divisor = batteryEfficiency x chargingEfficiency
                  = 0.828272877 x 0.94 = 0.7785765044        (ageGroupID 2099)
adjusted = 19.1614528 x 1.015625 / 0.7785765044 = 24.9954248
activity = 83.6254822 / 5 = 16.7250964
kilojoules = 24.9954248 x 16.7250964 = 418.0491
emissionQuant = 418.0491 / 1055055.9 = 3.96235774e-04  Million BTU
```

MOVESOutput stores **0.000396237**. Drop the 1.015625 and it is
3.90140 × 10⁻⁴ — a 1.54 % error, and the one this fixture's retarget produced
before §2.5's wildcard step was added.

### 6.5 The reproduction script

Extracted and run by `./run-brakewear-oracle.sh`. It reads only the input tables
of §1, computes S1–S18 for all three pollutant-processes — including `W`, the
base rate and the chain — and **asserts** its worst relative error against `sho`
and against `MOVESOutput`.

```python
#!/usr/bin/env python3
"""process-brakewear reproduction from the snapshot's own input tables."""
import sys, collections
import pyarrow.parquet as pq

SNAP = sys.argv[1]
P = SNAP + "/tables/db__movesexecution1ccc0232_campuscluster_illinois_edu__"
def T(n): return pq.read_table(P+n+".parquet").to_pylist()

YEAR, MONTH, HOUR, ZONE, ROAD, ST = 2020, 8, 7, 261610, 4, 21
COUNTY, ELECTRICITY = 26161, 9
DAYS=[r["dayID"] for r in T("runspecday")]
HD={r["dayID"]:r["hourDayID"] for r in T("hourday") if r["hourID"]==HOUR}
POLPROCS=[r["polProcessID"] for r in T("runspecpollutantprocess")]
KJ=1055.0559e6/1000.0
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
sel={r["hourDayID"] for r in T("runspechourday")}
sho={}
for d in DAYS:
    assert HD[d] in sel
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
# ---- drive cycle W (polprocess-independent at national scale) ----
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
ER=T("emissionrate")
def rates(pp):
    d={}
    for r in ER:
        if r["polProcessID"]!=pp: continue
        b=r["sourceBinID"]
        d[(slot(b,10**16),slot(b,10**14),slot(b,10**12),slot(b,10**10),r["opModeID"])]=float(r["meanBaseRate"])
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
agegroup={r["ageID"]:r["ageGroupID"] for r in T("agecategory")}
EVE=T("evefficiency")
def eveff(pp):
    return {r["ageGroupID"]:float(r["batteryEfficiency"])*float(r["chargingEfficiency"])
            for r in EVE if r["polProcessID"]==pp and r["sourceTypeID"]==ST}
realdays={r["dayID"]:float(r["noOfRealDays"]) for r in T("dayofanyweek")}
ZMH = [r for r in T("zonemonthhour")
       if r["monthID"] == MONTH and r["zoneID"] == ZONE and r["hourID"] == HOUR][0]
TEMP, HEAT = float(ZMH["temperature"]), float(ZMH["heatIndex"])
TA = T("temperatureadjustment")


def temp_terms(pp, fuel, regclass, my):
    """adjust.rs:495-520 -- the exact regulatory class first, then the
    regClassID 0 WILDCARD, then a zero-valued default. Only the wildcard row
    exists in this snapshot, and reaching it is the whole difference between
    a factor of 1.015625 and a factor of 1."""
    for rc in (regclass, 0):
        for r in TA:
            if (r["polProcessID"] == pp and r["fuelTypeID"] == fuel
                    and r["regClassID"] == rc
                    and r["minModelYearID"] <= my <= r["maxModelYearID"]):
                return float(r["tempAdjustTermA"]), float(r["tempAdjustTermB"])
    return 0.0, 0.0


def ev_temp_factor(pp, pol, proc, fuel, regclass, my):
    """adjust.rs:107-124. The dedicated EV branch is gated on process 1, fuel 9
    AND pollutant 91 together, so brakewear's electricity rows take the standard
    quadratic (zero terms, exactly 1) instead."""
    if not (proc == 1 and fuel == ELECTRICITY and pol == 91):
        return 1.0
    a, b = temp_terms(pp, fuel, regclass, my)
    adj = (TEMP - 72.0) * (a + b * (TEMP - 72.0))
    if adj < 0.0:
        adj = 0.0
    if ST < 40 and HEAT > 67.0:      # light-duty heat-index suppression
        adj = 0.0
    return 1.0 + adj
def scc(fuel,proc): return "%d"%(22*10**8+fuel*10**6+ST*10**4+ROAD*10**2+proc)
PPA={r["polProcessID"]:(r["pollutantID"],r["processID"]) for r in T("pollutantprocessassoc")}
ENERGY={91,92,93}
rows={}
for pp in POLPROCS:
    pol,proc=PPA[pp]
    if pp not in (9101,11609): continue   # 10609 is chained, below
    coh=cohorts(pp)
    sbaf=rebase(coh)
    rate=rates(pp)
    sbw=collections.defaultdict(float)
    for (my,fuel,et,rc),frac in sbaf.items():
        smy=shortgroup[mygroup[(pp,my)]]
        ev=evsf(pp,my,fuel,rc)
        for om in {k[4] for k in rate}:
            r=rate.get((fuel,et,rc,smy,om))
            if r is not None: sbw[(my,fuel,om)]+=frac*r*ev
    br=collections.defaultdict(float)
    for (my,fuel,om),v in sbw.items():
        for d in DAYS: br[(HD[d],my,fuel)]+=v*W[(HD[d],om)]
    ee=eveff(pp)
    for (my,fuel,et,rc),frac in coh.items():
        for d in DAYS:
            r=br[(HD[d],my,fuel)]*ev_temp_factor(pp,pol,proc,fuel,rc,my)
            if fuel==ELECTRICITY and ee: r/=ee[agegroup[YEAR-my]]
            act=sho[(HD[d],YEAR-my)]/realdays[d]
            q=r*act
            if pol in ENERGY: q/=KJ
            rows[(pol,proc,d,my,fuel)]=(q,scc(fuel,proc))
# chained: 10609 = 11609 x PM10PM25Ratio
chain=[r for r in T("runspecchainedto")]
pm10=T("pm10emissionratio")
for c in chain:
    outpp,outpol,outproc=c["outputPolProcessID"],c["outputPollutantID"],c["outputProcessID"]
    inpol,inproc=c["inputPollutantID"],c["inputProcessID"]
    for (pol,proc,d,my,fuel),(q,s) in list(rows.items()):
        if (pol,proc)!=(inpol,inproc): continue
        rr=[r for r in pm10 if r["polProcessID"]==outpp and r["sourceTypeID"]==ST
            and r["fuelTypeID"]==fuel and r["minModelYearID"]<=my<=r["maxModelYearID"]]
        for r in rr:
            rows[(outpol,outproc,d,my,fuel)]=(q*float(r["PM10PM25Ratio"]),scc(fuel,outproc))
# ------------------------------------------------------------------- compare
ref_sho = {(r["hourDayID"], r["ageID"]): float(r["SHO"]) for r in T("sho")}
worst_sho = max(abs(sho[k] - v) / v for k, v in ref_sho.items())
print("sho:           %3d rows, worst relative error %.3e" % (len(ref_sho), worst_sho))
assert worst_sho < 1e-5, "sho: worst relative error %.3e exceeds 1e-5" % worst_sho

out = pq.read_table(SNAP + "/tables/db__out_process_brakewear__movesoutput.parquet").to_pylist()
worst, worst_key = 0.0, None
for o in out:
    key = (o["pollutantID"], o["processID"], o["dayID"], o["modelYearID"], o["fuelTypeID"])
    q, scc = rows[key]
    assert scc == o["SCC"], (key, scc, o["SCC"])
    rel = abs(q - float(o["emissionQuant"])) / float(o["emissionQuant"])
    if rel > worst:
        worst, worst_key = rel, key
print("emissionQuant: %3d rows, worst relative error %.3e at "
      "(pollutant %d, process %d, day %d, MY %d, fuel %d)" % (len(out), worst, *worst_key))
# ASSERTED, not merely printed (docs/esm-conventions.md 21): ./run-tests.sh reads
# this script's EXIT CODE, so a regression that leaves the key set intact and
# moves every value would otherwise be reported green with the evidence in a log.
assert len(rows) == len(out), (len(rows), len(out))
assert set(rows) == {(o["pollutantID"], o["processID"], o["dayID"], o["modelYearID"],
                      o["fuelTypeID"]) for o in out}
assert worst < 2e-5, "emissionQuant: worst relative error %.3e exceeds 2e-5" % worst
chained = sum(1 for k in rows if (k[0], k[1]) == (106, 9))
print("key set:       %3d pollutant-processes x %d cohorts x %d day types = %d rows, exact"
      % (len(POLPROCS), len(cohorts(9101)), len(DAYS), len(rows)))
print("               %3d of them are CHAINED -- computed from the 11609 rows by "
      "PM10PM25Ratio, from no rate of their own" % chained)
```

Result:

```
sho:            82 rows, worst relative error 3.610e-06
emissionQuant: 750 rows, worst relative error 8.250e-06 at (pollutant 106, process 9, day 5, MY 2016, fuel 9)
key set:         3 pollutant-processes x 125 cohorts x 2 day types = 750 rows, exact
               250 of them are CHAINED -- computed from the 11609 rows by PM10PM25Ratio, from no rate of their own
```

### 6.6 What the fixture's inline tests check

Eleven tests, 130 assertions, and five of them are about things `mixed-onroad`
cannot check:

| test | what fails if it is wrong |
|---|---|
| the three pollutant-processes and the chain between them | the chain declaration, the energy-pollutant membership test, the unit divisor |
| the cohort row set is the same 125 for both rate paths | the union claim that lets one rank serve three blocks |
| the short model-year group is a property of the pollutant-process | §2.2, at four cohorts spanning both encodings |
| the EV temperature arm is live at this hour | §2.5, including `rt_hasTempAdjustExact` = 0, which pins the wildcard step |
| the PM10 chain is a ratio lookup with a model-year range | the ratio at five rows, and the exact zeros either side of the chain |

plus the base rate against **both** generator tables (16 cells over both day
types and five orders of magnitude), `W`'s two structural properties, the
activity chain against `sho`, and twelve `MOVESOutput` cells with their SCCs.

---

## 7. Fidelity notes and tolerance

### 7.1 The measured result

| | |
|---|---|
| rows | **750 of 750**, key set exact |
| worst cell | **8.250 × 10⁻⁶** relative, at (pollutant 106, process 9, day 5, MY 2016, fuel 9) |
| worst per pollutant | 91: 7.106 × 10⁻⁶, 106: 8.250 × 10⁻⁶, 116: 7.380 × 10⁻⁶ |
| gate | `tolerance.toml` `[cell] rel = 2e-5`, unchanged, and `[default] onroad = 1e-3` |
| `[shortfall]` | none |

The residual is the reference's own six-significant-figure column storage, the
same as every other fixture in this repository: `MOVESOutput` holds
`emissionQuant` as decimal text with six significant figures, and 8 × 10⁻⁶ is
what that costs. The independent Python reproduction of §6.5 reports the same
worst cell to the digit, at the same key, by a different route.

The PM10 block is the worst of the three for an arithmetically boring reason: it
is the PM2.5 block times a stored ratio, so it carries the PM2.5 residual plus
the ratio's own quantisation.

### 7.2 What the brake-wear rows do and do not check about `W`

Stated here rather than left to be discovered. Brake wear's rate table covers
five of `W`'s 23 operating modes:

| day type | modes 0, 1, 11, 21, 33 | total |
|---|---:|---:|
| 2 (weekend) | 0.1284438 | 1.0000003 |
| 5 (weekday) | 0.1988770 | 0.9999990 |

So a perturbation of `W` confined to the other eighteen modes would move the 500
particulate rows not at all and the 250 energy rows fully. The energy block is
the complete check on `W`; the particulate blocks are a 13–20 % one, and they add
something different instead — they check that the *same* weights, contracted
against a rate table five orders of magnitude smaller, still reproduce
`baserate_9_2020` to 2 × 10⁻⁶.

### 7.3 Precision-sensitive operations, ranked

1. **The EV temperature clamp**, and it is now on the live side. At 59.5 °F the
   raw adjustment is +0.015625; the clamp boundary is at T = 72 − a/b =
   72 − 0.00225/0.00028 = 63.96 °F. The fixture sits 4.5 °F below it, which is
   comfortable — but the *sign* of that margin is what changed from
   `mixed-onroad`, and it is what makes the wildcard lookup load-bearing.
2. **The heat-index suppression** at 67.0 °F. 59.5 is 7.5 °F below, so this one
   is further from its boundary here than at `mixed-onroad`'s 66.9.
3. **The A/C activity clamp.** −0.29698, against `mixed-onroad`'s −0.0189.
4. The model-year range boundary at 2010/2011 in `pm10emissionratio` — integer,
   so not a precision question, but a factor of 3.07 either side of it.

---

## 8. Gaps and things not verified

* **The `evefficiency` divergence in `moves.rs` still applies.**
  `ModuleFlags::ev_efficiency` is false on `moves.rs`'s production path, so it
  loads the table and never applies it; canonical MOVES does, and the `.esm`
  follows canonical. `docs/mixed-onroad.md` §2.3(f) has the measurement. This
  fixture inherits it unchanged, and the 42 fuel-9 energy rows are 10.7–22.1 %
  low without it.
* **Mode 501 is never exercised as a live weight.** §3.2 shows it cannot be at
  Inventory scale and that its rate is zero anyway. A project-scale snapshot
  would be needed to exercise the fold, and none of the 39 fixtures is one.
* **Tire wear is not covered.** `process-tirewear` is the same chain with
  polProcessID 11710 → 10710 and, from `operatingmode`, a completely different
  operating-mode family (400–416, binned on speed alone). Whether the drive-cycle
  classification produces those modes at all is the open question there; this
  fixture says nothing about it.
* **No age-resolved rate.** `emissionratebyage` and both `baseratebyage_*` tables
  are captured empty, so the `EmissionRateByAgeRates` path is untouched.
* **The legacy `BasicBrakeWearPMEmissionCalculator` is not ported and is not
  needed.** `CalculatorInfo.txt` registers (116, 9) to `BaseRateCalculator`, and
  `calculator-dag.json` records `registrations_count: 0` for the legacy class.

---

## 9. Summary for the `.esm` author

* Start from `fixtures/mixed-onroad.esm`. Retarget it and 250 of the 750 rows are
  already right — that retarget is a genuine, checkable milestone and it is where
  §2.5's defect surfaces.
* The only structural addition is `rate_rows`, the pollutant-process crossed with
  the cohort candidate grid, and it exists for one reason: a join key column must
  be one-dimensional and `shortModYrGroupID` is no longer a property of the
  cohort alone.
* Read the chain from `runspecchainedto` and `pm10emissionratio`. Do not write
  `106 = ratio × 116`. The chained block's own rate path is exactly zero and its
  quantity arrives through a `syms`-named self-join of the rate relation.
* Every pollutant-process-keyed adjustment table has an existence aggregate
  beside its value aggregate. The four zeros and ones brake wear gets from them
  are computed; the `evefficiency` one is not optional, because the divisor
  template floors at 1e-300.
* `W` is unchanged, and §3.2 is why. Assert `dc_WModeCount = 23`: 24 would mean
  the drive-cycle classification had taken the project-scale branch.
