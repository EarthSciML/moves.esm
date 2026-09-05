# `process-tirewear` — computation specification

The port specification for Phase 5's second rung, written to the method of
`docs/mixed-onroad.md` and `docs/process-brakewear.md`: the input inventory
determined from evidence, the chain with source lines into `../moves.rs`, every
join with its exact key pairs, and worked examples whose numbers can be checked
by hand.

It is short in the same places `docs/process-brakewear.md` is short, and for the
same reason: **tire wear is a rate on the `BaseRateCalculator` spine, not a
different model.** The activity chain, the cohort structure, the fuel-usage
rebase and the three-block output relation are those documents', unchanged.

But it is **not** brake wear with the identifiers changed, and the one place it
differs is the place a reader would least expect a difference:

1. tire wear's operating modes are **400–416, binned on average speed alone**,
   and they are produced by a **different generator** — the drive-cycle physics
   that carries every other running process contributes nothing to a tire-wear
   rate (§2.3);
2. so `W` acquires a pollutant-process axis, and this is the first fixture in
   the port whose weight vector is not one relation (§2.4);
3. tire wear's `shortModYrGroupID` is **0 on every model year** — a third
   encoding, neither running exhaust's two-digit years nor brake wear's decade
   bands (§2.2);
4. the PM10 chain is structurally brake wear's and **numerically far weaker as a
   check**, which §7.2 states rather than leaves to be discovered.

---

## 0. The fixture at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/process-tirewear.xml` |
| Model | ONROAD, `modelscale` `Inv` (inventory), `modeldomain` `DEFAULT` |
| Geography | county 26161 (Washtenaw, Michigan), zone 261610, link 2616104 |
| Time | year 2020, month **8**, hour **7**, day types **2 (weekend) and 5 (weekday)** |
| Vehicles | sourceTypeID 21 (passenger car); fuel types **1, 2, 5, 9** |
| Road | roadTypeID 4 (urban restricted access) |
| Pollutant/process | **9101** (Total Energy × Running Exhaust), **10710** (PM10 Tirewear, *chained*) and **11710** (PM2.5 Tirewear) |
| Model years | 1980–2020 (41) |
| Output | `db__out_process_tirewear__movesoutput`, **750 rows** |
| Output units | energy in Million BTU, particulate in **grams**, `outputtimestep` **Hour** |
| Calculator path | `TotalActivityGenerator` → `SourceBinDistributionGenerator` → **`AverageSpeedOperatingModeDistributionGenerator`** → `BaseRateGenerator` → `BaseRateCalculator` → `PM10BrakeTireCalculator` → output aggregation |
| Snapshot | 372 tables, **237 non-empty** |

### 0.1 The scope is `process-brakewear`'s, exactly

The XML's `<month key>`, `<beginhour key>` and `<day key>` are canonical
`RunSpecXML` **0-based indices into sorted ID lists**, not identifiers, and the
authority is the execution database's own `runspec*` tables — the same rule as
`docs/mixed-onroad.md` §0.1.

| dimension | `process-tirewear.xml` says | the execution database says |
|---|---|---|
| month | 7 | **8** (`runspecmonth`) |
| hour | 6 | **7** (`runspechour`) |
| day types | 5 | **2 and 5** (`runspecday`, 2 rows) |
| fuel types | 1 | **1, 2, 5, 9** (`runspecsourcefueltype`, 4 rows) |
| pollutant/process | 107, 117, 91 | **9101, 10710, 11710** (`runspecpollutantprocess`) |

**That resolved scope is `process-brakewear`'s to the row.** Measured: `sho`,
`avgspeeddistribution`, `driveschedulesecond`, `sourcetypeagedistribution` and
`hourvmtfraction` are **byte-identical** between the two snapshots, and the
`(91, 1)` block of `MOVESOutput` is identical too. So the whole activity half of
this fixture is already checked end to end by an existing one, and any
disagreement can be attributed to the tire-wear half immediately. §6.4 is the
consequence for what the retarget audit could and could not find.

`runspecpollutantprocess` is read in file order and that order — 9101, 10710,
11710 — is the order of the output relation's three blocks. It is the same
*shape* as brake wear's (energy, chained, direct) and therefore the same block
ordinals, which is worth knowing when reading either fixture's `coords`.

### 0.2 Why 750 rows, and what the three blocks are

```
750 = 3 pollutant-processes  x  125 (modelYearID, fuelTypeID) cohorts  x  2 day types
```

The 125 is `mixed-onroad`'s ragged set — 41 gasoline model years, 40 diesel, 23
E85 and 21 electricity — and it is **the same 125 for both computed
pollutant-processes**, which the fixture asserts rather than assumes
(`pp_selectedCohortCount` = 125, 0, 125). The middle zero is PM10 tire wear:
`pollutantprocessmodelyear` carries no 10710 rows, so it has no source-bin
distribution of its own and its 250 output rows arrive through the chain.

**Why the run carries an energy pollutant at all.** The RunSpec's own
`<description>` says: tire wear alone makes the Go `BaseRateGenerator` panic on
the missing `sourceUseTypePhysicsMapping` table, which MOVES only builds when a
running-exhaust process is selected. So 9101 is a carrier.

**No start exhaust, again.** `BaseRateGenerator` emits start-exhaust rates on
road type 1 and `BaseRateCalculator` joins its rate tables to `runSpecRoadType`,
which is `{4}` — `docs/mixed-onroad.md` §0.2. Tire wear is not road-type gated.

---

## 1. Input inventory

### 1.1 The tables `process-brakewear` already reads

All 49 of its `data_sources`, against this snapshot's copies, with **one table
read for one more column** and **no table added or removed**. That is the whole
inventory difference, and it is the measure of how close these two fixtures are:

| table | in `process-brakewear` | here |
|---|---|---|
| `avgspeedbin` | `avgSpeedBinID`, `avgBinSpeed` | **plus `opModeIDTirewear`** — 401 for bin 1 up to 416 for bin 16 |
| `emissionrate` | 60,388 rows: 57,040 for 9101 over 23 modes, 3,348 for 11609 over six | **57,567**: 57,040 for 9101 over the same 23, **527 for 11710 over seventeen (400–416)** |
| `pollutantprocessmodelyear` | 222 rows, two pollutant-processes, short groups 40/80 vs 6/1 | 222 rows, and 11710's are **all modelYearGroupID 0** — §2.2 |
| `pm10emissionratio` | 8 rows, two model-year ranges × four fuels, three distinct values | **4 rows**, one range, four fuels, **one** value |
| `runspecchainedto` | `10609 ← 11609` | `10710 ← 11710` |

`opModeIDTirewear` is one nullable column of a sixteen-row table, and it is the
entire tire-wear operating-mode model. §2.3.

### 1.2 What is NOT an input

`baserate_1_2020` (250 rows), `baserate_10_2020` (250 rows),
`sourcebindistribution` (250 rows), `sho` (82 rows) and `MOVESOutput` (750 rows)
are generator or expected output. None is a `data_sources` entry that anything
reads. Values out of the first four appear as `expected` in the fixture's inline
tests, which is the opposite direction.

**`ratesopmodedistribution` is captured NON-EMPTY here — 32 rows — and is still
not an input.** This is the one place the inventory rule needed a decision rather
than a look-up. Those 32 rows are `AverageSpeedOperatingModeDistributionGenerator`'s
output: 16 speed bins × 2 hour-days, `opModeFraction` 1, `avgSpeedFraction` 0.
They are a *generator* table, they are what §2.3 computes, and reading them would
transcribe the answer to the one question this fixture exists to ask. The fixture
therefore computes them from `avgspeedbin` and `avgspeeddistribution` and reads
the table nowhere; its 16-wide mode count is the independent statement of what
those 32 rows say.

`baseratebyage_1_2020`, `baseratebyage_10_2020`, `emissionratebyage` and
`opmodedistribution` are all **captured empty**, which is what says the
age-resolved and the pre-computed-op-mode paths are not taken.

---

## 2. The computation chain

### 2.1 What is unchanged

S1–S9 (activity), S10–S12 (cohorts and the fuel-usage rebase), the output
stage's group-by and SCC (S16–S18), and the whole of S15's adjustments are
`docs/mixed-onroad.md` §2.1–§2.4 and `docs/process-brakewear.md` §2.3 and §2.5
verbatim. In particular:

* every adjustment table `BaseRateCalculator` consults is keyed by
  `polProcessID` and **none of them carries an 11710 row** — `fullacadjustment`
  23 rows for 9101 and 0, `fleetavgadjustment` 11 and 0, `temperatureadjustment`
  1 and 0, `evefficiency` 7 and 0 — so the A/C increment is exactly 0, the
  EV-sales back-scaling exactly 1, the temperature factor exactly 1 and there is
  no EV divisor on the tire-wear electricity rows. Each of those zeros and ones
  is **computed**, through the existence aggregate beside each value aggregate,
  and not written down;
* the EV temperature arm is live on the 84 energy × electricity rows at 1.015625
  and reaching it needs `lib/adjustments.esm`'s `exact_else_wildcard`
  (`docs/process-brakewear.md` §2.5). Same hour, same 59.5 °F, same wildcard row.

### 2.2 The rate relation, and a third model-year encoding

`rate_rows = n_runspecpollutantprocess × (n_agecategory × n_runspecsourcefueltype)`
= 3 × 164 = 492, pollutant-process major, every factor a discovered extent. It
exists for the reason `docs/process-brakewear.md` §2.2 gives — a `join.on` key
column must be one-dimensional, and `shortModYrGroupID` depends on the
pollutant-process as well as on the cohort — and this fixture supplies the third
independent value that rule has now produced:

```
pollutantprocessmodelyear     modelYearGroupID       modelyeargroup.shortModYrGroupID
  (9101,  2020)                     2020                       40      two-digit year
  (11609, 2020)                 20112020                        6      decade band
  (11710, 2020)                        0                        0      "Doesn't Matter"
  (9101,  1980)                     1980                       80
  (11609, 1980)                 19501980                        1
  (11710, 1980)                        0                        0
```

All 31 of `emissionrate`'s 11710 source bins carry `00` in that slot, so the 0 is
not a miss — it is the encoding. **A document that computed one short group per
cohort would meet the 527 tire-wear rate rows with a source bin of 40 or 80 and
produce a tire-wear rate of exactly zero**, which is brake wear's failure mode
reached by a different route. That two encodings out of three are *degenerate*
in opposite directions is the argument for keeping the fix structural.

One consequence worth stating, because it makes the worked examples in §6 read
oddly at first: with a constant short group, **the tire-wear rate table does not
vary with model year at all**. §6.1 and §6.3 compute the same 0.0625957 g per
source-hour for a 2020 car and a 1980 one, and the two output rows differ only by
the fuel-usage rebase and the activity.

### 2.3 Tire wear's operating modes, and the generator that produces them

This is the section brake wear has no counterpart for.

`emissionrate` carries 11710 rates on operating modes **400 to 416** and on
nothing else. `operatingmode` names them:

```
400  tirewear;idle
401  tirewear;speed < 2.5mph
402  tirewear;2.5mph <= speed < 7.5mph
...
416  tirewear;72.5mph <= speed
```

with `speedLower`/`speedUpper` set and `VSPLower`/`VSPUpper` **null**. They are
binned on speed alone; there is no vehicle-specific-power physics on this path.

**The drive-cycle classification never produces one.** `drivecycle.rs` assigns a
second to mode 0, 1, 501 or one of the 21 VSP-binned modes, and to nothing in the
400 family. So a port that simply added a pollutant-process to
`process-brakewear` gets a tire-wear rate of exactly zero on all 500 particulate
rows — which is what the retarget audit of §6.4 measured, before any of this was
implemented.

What produces them is a **second generator**:
`AverageSpeedOperatingModeDistributionGenerator`
(`crates/moves-calculators/src/generators/avg_speed_op_mode_distribution.rs`),
whose module documentation states the case plainly: *"Tire wear is the one
running-emission process whose operating mode depends only on average speed —
there is no VSP / drive-cycle physics."* It handles process 10 and errors out for
anything else (`TIREWEAR_PROCESS = ProcessId(10)`, and `executeLoop` logs
`"AvgSpeedOMDG called for unknown process"`). Its live, non-project computation
is one cross join:

> every speed bin already carries its tire-wear operating mode in
> `avgSpeedBin.opModeIDTirewear`. The generator cross-joins the speed bins with
> the RunSpec's selected source types, road types and hour/days and emits one
> `opModeFraction = 1` row each.

And `BaseRateGenerator` reads what that generator wrote rather than driving the
cycles itself, because its fast path is gated on the process id
(`mod.rs:156-161`):

```rust
let should_process_drive_cycles = !inputs.is_project
    && (flags.process_id == 1 || flags.process_id == 9)   // Running, Brakewear
    && !ALWAYS_USE_ROMD_TABLE;
```

Process 10 fails that test and takes `core_base_rate_generator_from_romd`, which
reads `RatesOpModeDistribution` and resolves each row's missing
`avgSpeedFraction` out of `avgSpeedDistribution` (`aggregate.rs:93-106`).

**So the two paths differ in exactly one factor and agree in every other.**
`aggregate.rs:365-417` collapses both the same way —
`meanBaseRate += rate × opModeFraction × avgSpeedFraction` — so:

```
W[p, k, m]  =  Σ over speed bins b of  avgSpeedFraction[k, b] x opModeFraction_p[b, m]

  opModeFraction_p[b, m]  =  the drive-cycle distribution of bin b   if p is process 1 or 9
                          =  1 if m = avgspeedbin[b].opModeIDTirewear, else 0   if p is process 10
```

which is one aggregate with a per-pollutant-process selection of the mode
fraction, not two relations and a branch downstream. The document spells the
tire-wear arm as a `join.on` between `asb_opModeIDTirewear` and `om_opModeID`
with `expr: 1.0`, so its 1 is the additive identity of a matched row and its 0
that of an unmatched one — never an `==` inside a filter
(`docs/esm-conventions.md` §3).

The selector `rspp_usesAvgSpeedModes` is a **process** test because the reference
makes it one on both sides, and both constants are named as enum members rather
than written as digits.

**Why not simply union the two families?** The mode families are disjoint and
each pollutant-process's `emissionrate` selects only its own, so a single
`W[k, m]` carrying both would reproduce all 750 rows. It would also be writing
down a coincidence of the data instead of the rule, and it would make the two
structural assertions of §6.6 — `pp_WModeCount` 23 and 16, `pp_WTotal` 1 on each
— unstatable, since a union's counts are 39 and 2. §7.2's discipline applies to
the document as much as to the fixture: a stage that is only right because
another stage happens to be zero is checked at no point.

### 2.4 The base rate

Structurally `docs/process-brakewear.md` §2.3, with the weight now read for the
rate row's own pollutant-process through J37's key pair:

```
rtMode_rate[b, om]         = emissionrate.meanBaseRate  ⋈ (polProcessID, opModeID,
                                 shortModYrGroupID, regClassID, engTechID, fuelTypeID)
rtMode_weightedRate[b, om] = usedFraction[b] x evSalesFactor[b] x rtMode_rate[b, om]
rtDay_meanBaseRate[b, k]   = Σ over om of  pp_W[p(b), k, om] x rtMode_weightedRate[b, om]
```

J22 remains **one clause carrying six key pairs** — a cost decision, not a
reading order (`docs/esm-conventions.md` §25). Here it gates 492 × 60 output
cells against 57,567 rate rows.

### 2.5 The PM10 chain

`PM10BrakeTireCalculator` again, and the `.esm` spells it exactly as
`docs/process-brakewear.md` §2.4 does — a `syms`-named self-join of the rate
relation, with the same three measured zeros making one expression serve all
three blocks with no branch:

```
chain key   = 0  on an unchained row   (the LEFT JOIN onto runspecchainedto misses)
ratio       = 0  on an unchained row   (pm10emissionratio carries only 10710)
direct rate = 0  on the CHAINED row    (emissionrate has no 10710 row — J22 is inner)
```

The ratio table is smaller and blunter here: four rows, `polProcessID` 10710 ×
sourceTypeID 21 × the four fuel types, model years 1940–2060, and **`6.6667` in
all four**. §7.2 records what that costs the check.

---

## 3. Join structure

### 3.1 The joins this fixture adds

`docs/mixed-onroad.md` §3's J1–J34 and `docs/process-brakewear.md` §3.1's
J35–J39 all survive with their key pairs unchanged. Two are new:

| id | left | right | key pairs |
|---|---|---|---|
| **J40** | `asb_opModeIDTirewear` | `om_opModeID` | 1 — the tire-wear mode of a speed bin, `expr: 1.0`, so a match is the fraction and a miss is 0 |
| **J41** | `rt_polProcOrdinal` | `rspp_ordinal` | 1 — J37's pair again, now on the base-rate collapse, which is what gives `rtDay_meanBaseRate` the right weight vector |

and one one-row relation is added beside `run_regClassWildcardID`:
`run_tirewearIdleOpModeID`, carrying the enum's 400 so that `pp_tireIdleWeight`
selects mode 400 with a `join.on` rather than with an `==` in a filter
(`docs/esm-conventions.md` §20.4).

### 3.2 Operating mode 400, which is tire wear's mode 501

`docs/process-brakewear.md` §3.2 had to show that brake wear's mode 501,
`brakewear;stopped`, never carries a weight. Tire wear has the same question one
family over, and the answer has the same shape and one extra reason.

`operatingmode` carries **400**, `tirewear;idle`. `opmodepolprocassoc` associates
it with 11710 along with 401–416 — seventeen modes, not sixteen. `emissionrate`
carries 31 rows for it. So a reader may reasonably expect a 17-wide weight
vector.

**It is never non-zero, and there are two independent measurements to that
effect.**

1. **No speed bin names it.** `avgspeedbin.opModeIDTirewear` runs 401 to 416 over
   the sixteen bins, and 400 is reachable only through `buildOpModeClause`'s
   `when linkAvgSpeed < 0.1 then 400` — the **project-domain** branch
   (`avg_speed_op_mode_distribution.rs:118-125`). This RunSpec is `modelscale
   Inv`, `modeldomain DEFAULT`. The fixture's `pp_WModeCount` is **16 for both
   day types on both tire-wear pollutant-processes**, not 17, which is the
   document's own statement of that, and `pp_tireIdleWeight` is asserted at
   exactly 0 beside it.
2. **The rate is zero even if it did.** All 31 of `emissionrate`'s 11710 mode-400
   rows carry `meanBaseRate` **exactly 0.0** — measured, `min = max = 0.0`.

The parallel with brake wear is close enough to be worth naming: in both cases
the idle-like special mode exists in the schema, is associated with the
pollutant-process, is emitted only at project scale, and carries a zero rate. It
is the same design decision made twice by EPA, and neither of the 39 snapshots
exercises either half of it.

---

## 4. Reusable shapes

**Three templates were factored out of the existing documents for this rung**,
and the test of whether that was the right call is that two of them are now
instantiated in fixtures that predate this one.

* **`lib/keys.esm`'s `model_year_in_range(model_year, first_model_year,
  last_model_year)`** — the inclusive model-year band that MOVES puts on
  `temperatureadjustment`, `evefficiency`, `fleetavgadjustment` and
  `pm10emissionratio`. It is the residual predicate left over after the equi-join
  keys, so it is a `filter` and not a `join.on`. It was written out **twenty-six
  times** across three fixtures — nine here, nine in `process-brakewear`, eight in
  `mixed-onroad` — with the inclusivity of each end decided twenty-six times. All
  twenty-six now instantiate the template. The column names differ between the
  tables (`minModelYearID`/`maxModelYearID` against
  `beginModelYearID`/`endModelYearID`), which is exactly why the shape and not the
  columns is what a template can carry.
* **`lib/onroad_activity.esm`'s `is_energy_pollutant(pollutant_id, ...)`** —
  `engine.rs:1286-1310`'s membership rule, three ids of which a typical run
  selects one. Instantiated here and in `process-brakewear`, and it is the shape
  every later multi-pollutant fixture needs on its first line.
* **`lib/onroad_activity.esm`'s `energy_unit_divisor(is_energy,
  energy_divisor)`** — the other half of the same lines. The divisor arrives as a
  parameter rather than being applied inside the predicate, so that
  `rspp_isEnergy` stays assertable in its own right.

Everything else is imported unchanged: `pol_process_id`, `pollutant_id_of`,
`process_id_of`, `null_output_column` from `lib/identifiers.esm`;
`weeks_per_month`, `share_of_group`, `onroad_scc`, `source_bin_slot`,
`ev_energy_divisor`, `kilojoules_per_million_btu` from `lib/onroad_activity.esm`;
`exact_else_wildcard` from `lib/adjustments.esm`; all four drive-cycle shapes
from `lib/drive_cycle.esm` — which the energy block still needs in full, and the
tire-wear blocks do not touch at all.

**No template was added for the tire-wear mode fraction**, and that is
deliberate: it is an `aggregate` with a `join.on`, not an expression, and
`docs/esm-conventions.md` §6 is about expression shapes. What a template could
carry — the precedence, the arithmetic — is not where the content is.

---

## 5. Literals and enums

`docs/mixed-onroad.md` §5 carries the fixture's enums. Two groups change:

```
process:         RunningExhaust 1, Tirewear 10
operating_mode:  ... TirewearIdle 400
```

`Tirewear` is named because `rspp_usesAvgSpeedModes` tests it (§2.3) and because
`AverageSpeedOperatingModeDistributionGenerator` hard-codes the same 10.
`TirewearIdle` is named because `pp_tireIdleWeight` joins against it (§3.2).

The three energy pollutants stay named for `is_energy_pollutant`'s sake: 92 and
93 are not in this run and the rule still has to admit them.

The two tire-wear pollutant ids, 107 and 117, are **not** enum members and are
never written down. They are unpacked from `runspecpollutantprocess`'s
`polProcessID` by `pollutant_id_of`, which is also how the SCC's process digits
and the output's `processID` column are reached — `2201210410`, one digit from
brake wear's `2201210409`.

---

## 6. Hand-checkable worked examples

### 6.0 Run-level values used by every example

| | |
|---|---|
| temperature, heat index (hour 7, month 8, zone 261610) | **59.5 °F** |
| A/C activity `-3.63154 + 59.5(0.072465 - 0.000276 × 59.5)` | −0.29698 → clamps to **0** |
| EV temperature adjustment (pollutant 91 × process 1 × fuel 9) | +0.015625 → factor **1.015625** |
| `noOfRealDays` | day 2 → **2**, day 5 → **5** |
| unit divisor | 9101 → **1,055,055.9**, 10710 and 11710 → **1** |

The tire-wear speed distribution, `avgspeeddistribution` summed to the bin for
source type 21 on road type 4 — this is `W`'s whole tire-wear arm, one number per
operating mode:

| bin | mode | weekend (hourDay 72) | weekday (hourDay 75) |
|---:|---:|---:|---:|
| 1 | 401 | 0.0049413 | 0.0073012 |
| 2 | 402 | 0.0063848 | 0.0191584 |
| 3 | 403 | 0.0026317 | 0.0245037 |
| 4 | 404 | 0.0020342 | 0.0276453 |
| 5 | 405 | 0.0019203 | 0.0289574 |
| 6 | 406 | 0.0019185 | 0.0279777 |
| 7 | 407 | 0.0024934 | 0.0266481 |
| 8 | 408 | 0.0033444 | 0.0264458 |
| 9 | 409 | 0.0054434 | 0.0273040 |
| 10 | 410 | 0.0100339 | 0.0319103 |
| 11 | 411 | 0.0208781 | 0.0429263 |
| 12 | 412 | 0.0454058 | 0.0642978 |
| 13 | 413 | 0.0981945 | 0.1059380 |
| 14 | 414 | 0.1821360 | 0.1550490 |
| 15 | 415 | 0.2393280 | 0.1713350 |
| 16 | 416 | 0.3729120 | 0.2126010 |
| **400** | *tirewear;idle* | **0** | **0** |
| | total | 1.0000003 | 0.9999990 |

The two columns are the same activity binned two ways as the day type changes,
not two different activities: the weekend hour is 37 % in the top speed bin and
the weekday hour 21 %, which is the whole reason the weekend tire-wear rate comes
out **higher** than the weekday one while every energy rate goes the other way.

### 6.1 Worked example A — MY 2020, gasoline, weekday and weekend, PM2.5 tire wear

The cohort is one source bin after the fuel-usage rebase: engTech 1, regClass 20,
`usedFraction` **0.9583418**. Its `shortModYrGroupID` is 0 (§2.2), so its rate
row is `sourceBinID` **1010120000000000000** — fuel 1, engTech 1, regClass 20,
short model-year group **00** — and its seventeen mode rates are

```
mode 400  0.000000      mode 406  0.044600      mode 412  0.062755
mode 401  0.006355      mode 407  0.049680      mode 413  0.063540
mode 402  0.012020      mode 408  0.053795      mode 414  0.063895
mode 403  0.022310      mode 409  0.057080      mode 415  0.063910
mode 404  0.031065      mode 410  0.059580      mode 416  0.063525
mode 405  0.038440      mode 411  0.061450
```

(g per source-hour; the rate rises with speed, flattens above 60 mph and turns
over slightly in the top bin, which is the shape of a tire-wear curve — and mode
400's exact 0 is §3.2's second measurement).

Contract with the weekend column:

```
Σ_bin  frac x rate  =  0.0049413(0.006355) + 0.0063848(0.012020) + ... + 0.3729120(0.063525)
                    =  0.0625957
meanBaseRate        =  0.9583418 x 0.0625957  =  0.0599881
```

which is `baserate_10_2020.meanBaseRate` at (11710, MY 2020, fuel 1, hourDay 72)
to the last stored digit. No adjustment applies (§2.1), so

```
activity      =  sho[hourDay 72, age 0] / noOfRealDays[2]  =  27.33 / 2  =  13.665
emissionQuant =  0.0599881 x 13.665  =  0.819737   (MOVESOutput: 0.819737)
```

The weekday column gives 0.0580158 × 0.9583418 = **0.0555990**, and with
`sho[hourDay 75, age 0] = 260.057` over five real days, 0.0555990 × 52.0114 =
**2.89178** (MOVESOutput: 2.89178).

### 6.2 Worked example B — the same two rows, PM10

`runspecchainedto` says 10710 ← 11710 and `pm10emissionratio` gives 6.6667 for
(10710, sourceType 21, fuel 1, model years 1940–2060):

```
weekend  0.819737 x 6.6667  =  5.46494    (MOVESOutput: 5.46494)
weekday  2.891780 x 6.6667  =  19.27860   (MOVESOutput: 19.27860)
```

The chained block has no rate of its own: `rtDay_quantDirect` on a 10710 rate row
is exactly 0, and the fixture asserts that directly.

### 6.3 Worked example C — MY 1980, gasoline, weekend, and why the rate did not move

The 1980 cohort is also one source bin — engTech 1, regClass 20 — with
`usedFraction` **0.9533293**, and **the same seventeen mode rates as MY 2020**,
because 11710's `shortModYrGroupID` is 0 for every model year (§2.2). So

```
meanBaseRate  =  0.9533293 x 0.0625957  =  0.0596743   (baserate_10_2020: 0.0596743)
activity      =  sho[hourDay 72, age 40] / 2  =  2.43728 / 2  =  1.21864
PM2.5         =  0.0596743 x 1.21864  =  0.0727215     (MOVESOutput: 0.0727215)
PM10          =  0.0727215 x 6.6667   =  0.484812      (MOVESOutput: 0.484812)
```

The 0.53 % gap between the 1980 and 2020 base rates is the fuel-usage rebase and
nothing else. Compare the energy block, where the same two model years are
392,141 and 207,997 — a factor of 1.9. **A tire-wear rate is essentially
model-year-blind and an energy rate is not**, and that is a property of the rate
table's own model-year encoding rather than of anything this port does.

### 6.4 What the retarget audit found, before any of this existed

`docs/process-brakewear.md` §6.5 records that retargeting an existing fixture
onto a neighbouring snapshot is the cheapest available audit, and it is the first
move on this rung. Both existing onroad fixtures were pointed at this snapshot's
input tables, with nothing changed but the paths and the execution-database name.

| retargeted fixture | rows it emits | key set | worst cell on its own block |
|---|---|---|---|
| `fixtures/mixed-onroad.esm` | 250 | exact on (91, 1) | **7.106 × 10⁻⁶** |
| `fixtures/process-brakewear.esm` | 750 | exact, all 750 keys | **7.106 × 10⁻⁶** on (91, 1) |

**The audit is clean: it found no defect.** Both reproduce every energy row of
the `process-tirewear` snapshot at the same worst cell, at the same key, and
`process-brakewear`'s retarget even emits the correct 750-row key set with the
correct SCCs, because its output relation is built from
`runspecpollutantprocess` and unpacks the process digits from the data.

**And the reason it is clean is worth recording, because it makes this audit
weaker than the one that earned the rule.** This snapshot's resolved scope is
`process-brakewear`'s exactly (§0.1) — same month, same hour, same day types,
same county, same fuels, byte-identical activity tables. So the retarget moved
*no* scope dimension and could not have found a clamped stage; it confirms the
`exact_else_wildcard` fix rather than extending it. A retarget that moves an hour
or a month is the audit `docs/esm-conventions.md` §27.3 describes; a retarget onto
a snapshot with the same scope and a different pollutant set is a check that the
*pollutant* generalisation holds, which is a different and smaller thing.

What it did establish, immediately and cheaply, is the shape of the work: the
retargeted `process-brakewear` produced **exactly 0.0 in both particulate
blocks**, on all 500 rows. Not a small number, not a wrong number — the additive
identity, because `dc_W` has no weight on operating modes 400–416 and J22's inner
join therefore matches no 11710 rate. That zero is what pointed at §2.3 before a
line was written, and it is the reason this document's §2.3 is its longest
section.

### 6.5 The reproduction script

Extracted and run by `./run-tirewear-oracle.sh`. It reads only the input tables
of §1, computes S1–S18 for all three pollutant-processes — including **both**
operating-mode families, the base rate and the chain — and **asserts** its worst
relative error against `sho` and against `MOVESOutput`.

```python
#!/usr/bin/env python3
"""process-tirewear reproduction from the snapshot's own input tables."""
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
# ---- tire-wear W: the SAME speed-bin weights, binned by speed alone --------
# AverageSpeedOperatingModeDistributionGenerator (avg_speed_op_mode_distribution.rs
# :386-420). A speed bin already carries its tire-wear operating mode in
# avgSpeedBin.opModeIDTirewear and the emitted opModeFraction is 1, so the weight
# of mode 400+i IS the fraction of bin i. Mode 400 (`tirewear;idle`) is reachable
# only from buildOpModeClause's project-domain `linkAvgSpeed < 0.1`, so it is
# absent here and the vector is 16 modes wide, not 17.
TIREWEAR_PROCESS=10
tire_mode={r["avgSpeedBinID"]:(r["opModeIDTirewear"] if r["opModeIDTirewear"] is not None else 0)
           for r in T("avgspeedbin")}
WT=collections.defaultdict(float)
for r in T("avgspeeddistribution"):
    if r["sourceTypeID"]!=ST or r["roadTypeID"]!=ROAD: continue
    WT[(r["hourDayID"],tire_mode[r["avgSpeedBinID"]])]+=float(r["avgSpeedFraction"])
for d in DAYS:
    t=sum(v for (h,_),v in WT.items() if h==HD[d])
    assert abs(t-1.0)<1e-5, t
    assert len({m for (h,m),v in W.items() if h==HD[d] and v>0.0})==23
    assert len({m for (h,m),v in WT.items() if h==HD[d] and v>0.0})==16
    assert WT[(HD[d],400)]==0.0
def weights(proc): return WT if proc==TIREWEAR_PROCESS else W
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
    AND pollutant 91 together, so tire wear's electricity rows take the standard
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
    if pp not in (9101,11710): continue   # 10710 is chained, below
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
    Wpp=weights(proc)
    for (my,fuel,om),v in sbw.items():
        for d in DAYS: br[(HD[d],my,fuel)]+=v*Wpp[(HD[d],om)]
    ee=eveff(pp)
    for (my,fuel,et,rc),frac in coh.items():
        for d in DAYS:
            r=br[(HD[d],my,fuel)]*ev_temp_factor(pp,pol,proc,fuel,rc,my)
            if fuel==ELECTRICITY and ee: r/=ee[agegroup[YEAR-my]]
            act=sho[(HD[d],YEAR-my)]/realdays[d]
            q=r*act
            if pol in ENERGY: q/=KJ
            rows[(pol,proc,d,my,fuel)]=(q,scc(fuel,proc))
# chained: 10710 = 11710 x PM10PM25Ratio
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

out = pq.read_table(SNAP + "/tables/db__out_process_tirewear__movesoutput.parquet").to_pylist()
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
chained = sum(1 for k in rows if (k[0], k[1]) == (107, 10))
print("key set:       %3d pollutant-processes x %d cohorts x %d day types = %d rows, exact"
      % (len(POLPROCS), len(cohorts(9101)), len(DAYS), len(rows)))
print("               %3d of them are CHAINED -- computed from the 11710 rows by "
      "PM10PM25Ratio, from no rate of their own" % chained)
```

### 6.6 What the fixture's inline tests check

Eleven tests, 141 assertions. Five of them are about things no earlier fixture
can check:

| test | what fails if it is wrong |
|---|---|
| the two operating-mode families are two binnings of one activity | §2.3 and §3.2 — the mode counts 23 and 16, both totals 1, mode 400 at exactly 0, and the generator selector on all three pollutant-processes |
| the collapsed base rate reproduces both generator tables | that the two blocks are contracted against *different* weight vectors, over seven orders of magnitude |
| the short model-year group is a property of the pollutant-process | §2.2, at six rate rows spanning both encodings |
| the PM10 chain is a ratio lookup, and here it is a single constant | the chain edge and the exact zeros either side of it — and §7.2's admission of what it cannot see |
| the three pollutant-processes and the chain between them | the chain declaration, the energy-pollutant membership test, the unit divisor, and the process ids the SCC is built from |

plus the run scope, the drive-cycle scaffolding, `W`'s structural properties, the
activity chain against `sho`, and twelve `MOVESOutput` cells with their SCCs.

---

## 7. Fidelity notes and tolerance

### 7.1 The measured result

| | |
|---|---|
| rows | **750 of 750**, key set exact |
| worst cell | **8.151 × 10⁻⁶** relative, at (pollutant 107, process 10, day 5, MY 2004, fuel 9) |
| worst per pollutant | 91: 7.106 × 10⁻⁶, 107: 8.151 × 10⁻⁶, 117: 6.888 × 10⁻⁶ |
| gate | `tolerance.toml` `[cell] rel = 2e-5`, unchanged, and `[default] onroad = 1e-3` |
| `[shortfall]` | none |

The residual is the reference's own six-significant-figure column storage, the
same as every other fixture here. The independent Python reproduction of §6.5
reports **the same worst cell to the digit, at the same key**, by a different
route.

The PM10 block is again the worst of the three for the arithmetically boring
reason: it is the PM2.5 block times a stored ratio, so it carries the PM2.5
residual plus the ratio's own quantisation — and 6.6667 is a five-figure store of
20/3, which is a coarser quantisation than brake wear's 2.60985.

### 7.2 What the tire-wear rows do and do not check

Stated here rather than left to be discovered, and the answer is close to the
mirror image of `docs/process-brakewear.md` §7.2.

**On the weights, the tire-wear rows are the COMPLETE check and the energy rows
are not.** Brake wear's rate table covered five of `W`'s 23 modes, 12.8 % of the
weekend weight; tire wear's covers all sixteen live speed-bin modes, **100 %** of
it. A perturbation of any speed bin's `avgSpeedFraction` moves the 500
particulate rows. What the tire-wear rows check is `avgspeeddistribution` and its
re-binning; what they do **not** touch at all is the drive-cycle physics —
`driveschedulesecond`'s 63,602 speeds, the VSP polynomial, the braking
thresholds, the bracketing weights. That whole apparatus is still exercised, but
only by the 250 energy rows, exactly as in `mixed-onroad`.

**On the PM10 lookup, this fixture is materially weaker than
`process-brakewear`.** `pm10emissionratio` here is four rows, one model-year
range, one value:

| | brake wear | tire wear |
|---|---|---|
| rows | 8 | 4 |
| model-year ranges | 1940–2010 and 2011–2060 | 1940–2060 only |
| distinct ratios | 8.0, 2.60985, 1.42475 | **6.6667** |
| dropping the range predicate | factor of 3 wrong on half the rows | **no effect** |
| dropping the fuel key | 83 % wrong on the newer electricity rows | **no effect** |

So J36's range predicate and its `fuelTypeID` pair are carried here and checked
nowhere here. They are checked by `process-brakewear`, which is the argument for
the two fixtures being in the same suite rather than one superseding the other.

**On the model-year encoding, likewise.** 11710's `shortModYrGroupID` is 0
everywhere, so the tire-wear path never distinguishes two source bins by model
year and J20′ is exercised on the energy block alone.

### 7.3 Precision-sensitive operations, ranked

1. **The EV temperature clamp**, live at +0.015625 with its boundary at
   T = 72 − 0.00225/0.00028 = 63.96 °F; the fixture sits 4.5 °F below it. Same as
   `process-brakewear`, and it is the energy block that carries it.
2. **The heat-index suppression** at 67.0 °F; 59.5 is 7.5 °F below.
3. **The A/C activity clamp** at −0.29698.
4. **The tire-wear weight sum.** `pp_WTotal` is 1.0000003 and 0.9999990 rather
   than 1, because `avgSpeedFraction` is stored to six significant figures — which
   is why its assertion is ABSOLUTE at 1e-5 and not relative
   (`docs/esm-conventions.md` §20.5). The tire-wear arm inherits exactly the same
   two numbers as the drive-cycle arm, since both are re-weightings of the same
   sixteen fractions; that they agree is asserted.
5. The 6.6667 ratio, a five-figure store of 20/3. Not a boundary, but it is the
   largest single contributor to the PM10 block's residual.

---

## 8. Gaps and things not verified

* **The `evefficiency` divergence in `moves.rs` still applies**, unchanged from
  `docs/mixed-onroad.md` §2.3(f) and inherited here. It touches the 42 fuel-9
  energy rows and no tire-wear row, because `evefficiency` has no 11710 entry.
* **Operating mode 400 is never exercised as a live weight**, and neither is
  brake wear's 501. §3.2 shows it cannot be at Inventory scale and that its rate
  is zero anyway. Both need a project-scale snapshot and none of the 39 is one.
* **`AverageSpeedOperatingModeDistributionGenerator`'s project branch is not
  ported.** `project_op_mode_fractions` / `assign_tirewear_op_mode` — the
  `linkAvgSpeed` `CASE` clause that produces mode 400 — is unreachable from any
  available RunSpec, so the document implements the non-project arm only and says
  so here rather than implementing an untestable branch.
* **The NULL `opModeIDTirewear` edge case is not exercised.** The Java's
  `INSERT IGNORE` would store a NULL as operating mode 0; every bin in the
  default database carries a mode, so this is schema-permitted and unobserved.
  The `.esm` reads the column as it stands, and a NULL would arrive as the
  reader's own missing-value and match no `operatingmode` row — a zero weight
  rather than a weight on mode 0. That is a divergence from
  `NULL_OP_MODE_DEFAULT` which nothing here can reach and nothing here checks.
* **No age-resolved rate.** `emissionratebyage` and both `baseratebyage_*` tables
  are captured empty.
* **No upstream defect was found on this rung.** The reserved finding number F34
  is unused: the fixture needed no workaround, `esm validate`, `esm test` and
  `esm simulate` behaved as documented throughout, and nothing about F17, F31 or
  F32 had to be worked around. `tools/clause-order-audit.py` is green on the new
  document, so nothing in it depends on the order of a join.

---

## 9. Summary for the `.esm` author

* Start from `fixtures/process-brakewear.esm`. Retarget it and 250 of the 750
  rows are already right — and the other 500 come out **exactly 0**, which is the
  measurement that tells you what the rung is actually about (§6.4).
* **The whole of it is §2.3.** Tire wear's operating modes are speed bins, they
  come from a different generator, and `avgspeedbin.opModeIDTirewear` is the one
  column that carries the model. Give `W` a pollutant-process axis and select the
  mode fraction on it; do not union the two families, even though the union
  reproduces every number.
* The rate relation is `process-brakewear`'s, and `shortModYrGroupID` = 0 is the
  third value the rule that created it has now produced. Do not special-case it.
* Read the chain from `runspecchainedto` and `pm10emissionratio`. The lookup is
  degenerate here — one value, one range — so write the join that
  `process-brakewear` needs, not the one this snapshot would accept, and record
  in §7.2 which half of it this fixture cannot see.
* Assert `pp_WModeCount` = 16, not 17, and `pp_tireIdleWeight` = 0. Seventeen
  would mean the classification had taken the project-scale branch.
