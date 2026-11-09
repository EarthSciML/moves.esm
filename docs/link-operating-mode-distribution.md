# `LinkOperatingModeDistributionGenerator` — computation specification

The port specification for the last reachable operating-mode-distribution
generator, written to the method of `docs/meteorology-generator.md` and
`docs/operating-mode-distribution.md`: the input inventory determined from
evidence, the chain with source lines into the pinned MOVES tree, every join
with its exact key pairs, and worked examples whose numbers can be checked by
hand.

It exists because a capture was made for it. `docs/omd-generator-reachability.md`
measured five generators as unreachable and gave one reason for all five — no
RunSpec in the corpus selects the project or mesoscale-lookup domain.
`moves.rs` then captured `scale-project`, and exactly one of the five moved.
This is that one. The other four need no capture: three are discarded by
`MOVESInstantiator.java:1449` under `DO_RATES_FIRST` and the fourth is a SQL
section rather than a class.

**`scale-project` is the only snapshot in the corpus that runs this generator,
and it runs it once, on one link.** That is a narrow base and this document
says so wherever it matters — §8 is longer than usual for that reason. What
the one snapshot does buy is unusually sharp: the whole output is 122 cells,
every one of them reproduces to the last digit the reference stores, and two
of the arithmetic decisions are decided by the corpus rather than argued.

---

## 0. The generator at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/scale-project.xml` |
| Model | ONROAD, rates-first (`CompilationFlags.DO_RATES_FIRST`), `modeldomain` **`PROJECT`** |
| Reads | `link`, `linkSourceTypeHour`, `driveSchedule`, `driveScheduleAssoc`, `driveScheduleSecond`, `operatingMode`, `physicsOperatingMode`, `sourceUseTypePhysicsMapping`, `opModePolProcAssoc`, `runSpecHourDay`, `runSpecSourceType` |
| Writes | `OpModeDistribution` (122 rows) and 21 rows of `RatesOpModeDistribution` |
| Output | **no `MOVESOutput` rows at all** — it is a generator, and its product is an execution-database table |
| Calculator path | **`LinkOperatingModeDistributionGenerator`** — a generator with the project-scale `BaseRateCalculator` chain downstream of it, outside this slice |
| Rows | 122 `OpModeDistribution` + 21 `RatesOpModeDistribution`, in one snapshot (§7.1) |
| Ported by | `lib/drive_cycle.esm` (the VSP and op-mode shapes), `components/link_operating_mode_distribution.esm`; and since 2026-10-19 in the onroad chain itself, `onroad/model.esm`'s `lomd_*`, which `runspecs/scale-project.esm` exercises end to end (PLAN.md §7.3.40) |
| Java | `.../ghg/LinkOperatingModeDistributionGenerator.java` (1,184 lines), `.../ghg/SourceTypePhysics.java` for the model-year offset |
| Rust | `../moves.rs/crates/moves-calculators/src/generators/link_op_mode_distribution.rs` |

`scale-project` names this specification because it is the only snapshot that
carries `OpModeDistribution` non-empty. It has no execution-database
fixture, but since 2026-10-19 `runspecs/scale-project.esm` reproduces its
`MOVESOutput` end to end through this generator: 125 of 125 rows, key set
exact (PLAN.md §7.3.40). Since 2026-11-08 `tools/calculator-coverage.py`
accepts that RunSpec as the claim's fixture leg (PLAN.md §7.3.53), and the
claim counts. `docs/project-tag.md` claims `ProjectTAG` on the same snapshot.

### 0.1 Which runs it fires on, and how that was established

Both halves of a generator's claim are checked (§35.2): the rows, and *which
runs produce rows at all*. The predicate, asserted on all 43 snapshots
carrying an execution database — 43 as this is written, and the corpus grows —
including the 42 that fail it:

> `OpModeDistribution` populated ⇔ the RunSpec's `<modeldomain>` is `PROJECT`

The generator is on the `DO_RATES_FIRST` whitelist
(`MOVESInstantiator.java:1462`), so a DEFAULT-domain run can load the class;
what it cannot do is give it a link. `MasterLoop` drives the generator per
link, and outside PROJECT domain the `link` table holds the synthetic
road-type links rather than a project network. In the corpus the two
conditions coincide exactly: `scale-project` is the one PROJECT RunSpec, the
one snapshot that class-loads the generator, and the one snapshot with a
non-empty `OpModeDistribution`.

**The predicate is written on the RunSpec's domain and not on class-loading,
and that is deliberate.** Class-loading is the weaker signal — the corpus has
already been burned by a class that loaded and never emitted
(`nr-pleasure-craft-state` / `NRAirToxicsCalculator`), and in this very
snapshot `StartOperatingModeDistributionGenerator` is class-loaded and leaves
its own output table empty. Reading the domain out of the RunSpec XML is a
statement about the run, which is what the predicate is about.

## 1. Input inventory

### 1.1 The network, and what the generator asks of it

| table | columns used | why |
|---|---|---|
| `link` | `linkID`, `roadTypeID`, `linkAvgSpeed`, `linkAvgGrade` | the link being processed; `linkAvgSpeed` selects the brackets and `linkAvgGrade` is copied onto every second of both bracketing schedules |
| `linkSourceTypeHour` | `linkID`, `sourceTypeID` | which source types travel the link; also the join that gates the `RatesOpModeDistribution` copy |
| `driveScheduleAssoc` | `sourceTypeID`, `roadTypeID`, `driveScheduleID` | the candidate schedules for this (source type, road type) |
| `driveSchedule` | `driveScheduleID`, `averageSpeed` | the speed each candidate is ranked by |
| `driveScheduleSecond` | `driveScheduleID`, `second`, `speed` | the second-by-second trace the whole computation rests on |

### 1.2 The physics and binning tables

| table | columns used | why |
|---|---|---|
| `sourceUseTypePhysicsMapping` | `realSourceTypeID`, `tempSourceTypeID`, `opModeIDOffset`, `rollingTermA`, `rotatingTermB`, `dragTermC`, `sourceMass`, `fixedMassFactor` | the road-load coefficients in the VSP polynomial, and the model-year-physics renumbering applied afterwards |
| `operatingMode` | `opModeID`, `VSPLower`, `VSPUpper`, `speedLower`, `speedUpper` | the (speed, VSP) rectangles the `CASE` is built from |
| `physicsOperatingMode` | `opModeID` | the mode list the interpolation runs over, so a mode one bracket never entered still gets a zero |
| `opModePolProcAssoc` | `opModeID`, `polProcessID` | which pollutant-processes share a distribution |
| `runSpecHourDay` | `hourDayID` | the cross join that gives every row an hour-day |
| `runSpecSourceType` | `sourceTypeID` | joined to `sourceUseTypePhysicsMapping` in the per-second table |

### 1.3 What is NOT an input

* **`driveScheduleSecondLink` is not read as input, and in the snapshot it is
  empty.** The generator writes it (the bracketing schedules, under negative
  pseudo-link ids) and deletes what it wrote before finishing. The captured
  table is the aftermath, not the intermediate; this port does not read it,
  which is why the 0 rows there are not a problem.
* **`OpModeDistribution` is not read as input either**, though the generator
  checks it: an existing row for the link with `(polProcessID % 100) = 1` makes
  the generator stand down and use the user's distribution
  (`…java:330-334`). The fixture's input database creates the table **empty on
  purpose** so that branch is not taken. §8.2.
* `tempExistingOpMode` is present and empty, for the same reason.

## 2. The computation chain

| step | Java | what it does |
|---|---|---|
| **L-1** | `calculateOpModeFractions` @step 100 | decide the path: user distribution, drive schedule, or average speed |
| **L-2** | `interpolateOpModeFractions` @step 105 | find the two bracketing drive schedules; materialise each as a pseudo-link |
| **L-3** | `calculateOpModeFractionsCore` @step 110 | per-second acceleration and VSP; assign an operating mode; count; divide |
| **L-4** | `SourceTypePhysics.updateOperatingModeDistribution` | temp source type → real, `opModeID += opModeIDOffset` |
| **L-5** | `interpolateOpModeFractions` @step 105 (tail) | linear interpolation between the two brackets onto the real link |
| **L-6** | `populateRatesOpModeDistribution` @step 200 | copy the link's rows into `RatesOpModeDistribution` at the link's own road type |

### 2.1 L-1 — three paths, and which one the corpus exercises

`calculateOpModeFractions` (`…java:309-395`) counts two things before doing
anything: rows in `driveScheduleSecondLink` for the link, and rows in
`OpModeDistribution` for the link with `(polProcessID % 100) = 1`.

```
hasDriveSchedule && !hasRunningOpModeDistribution -> calculateOpModeFractionsCore   (L-3 directly)
!hasRunningOpModeDistribution && averageSpeed > 0 -> interpolateOpModeFractions     (L-2, the corpus)
!hasRunningOpModeDistribution                     -> ERROR, no schedule/speed/OMD
otherwise                                          -> use the user's distribution
```

There is a fourth arm hidden in the second: when `linkAvgSpeed <= 0` the
generator **writes itself a drive schedule** — thirty seconds of zero speed at
zero grade, commented in the Java as "with 0 speed, brakes are likely applied
rather than using the engine to counteract any grade" — and then takes the
first arm. The fixture's link has `linkAvgSpeed` 30, so the corpus exercises
the second arm only. §8.1.

### 2.2 L-2 — the brackets

Four `INSERT`s, the second and fourth `INSERT IGNORE` so they only fire when
the first of their pair found nothing:

| | rule | flag when it fires |
|---|---|---|
| low | greatest `averageSpeed` **≤** the link's | — |
| low (fallback) | least `averageSpeed` **>** the link's | `isOutOfBoundsLow` |
| high | least `averageSpeed` **≥** the link's | — |
| high (fallback) | greatest `averageSpeed` **<** the link's | `isOutOfBoundsHigh` |

Ties on `averageSpeed` are broken by `max(driveScheduleID)`. Either flag makes
MOVES emit a message, and — unless `CompilationFlags.ALLOW_DRIVE_CYCLE_EXTRAPOLATION`
— call `MOVESEngine.terminalErrorFound()`. Neither fires in the corpus, and
this port implements the flags but cannot check them (§8.1).

The interpolation factor is

```
factor = (linkAvgSpeed - lowAverageSpeed) / (highAverageSpeed - lowAverageSpeed)
```

and is **0.0** when `lowAverageSpeed >= highAverageSpeed`, which is the case
where a single schedule brackets the link on both sides.

### 2.3 L-3 — accelerations, VSP, and the operating mode

For each second `t` of a bracketing schedule, with `g` the **link's** average
grade in per cent copied onto every second:

```
At0 = coalesce( (speed[t]   - speed[t-1]) + 9.81/0.44704 * sin(atan(g/100)), 0.0 )
At1 = coalesce( (speed[t-1] - speed[t-2]) + 9.81/0.44704 * sin(atan(g/100)), 0.0 )
At2 = coalesce( (speed[t-2] - speed[t-3]) + 9.81/0.44704 * sin(atan(g/100)), 0.0 )

VSP = (  (v*0.44704) * (A + (v*0.44704) * (B + C*(v*0.44704)))
       + M * (v*0.44704) * coalesce(speed[t]-speed[t-1], 0.0) * 0.44704
       + M * 9.81 * sin(atan(g/100)) * (v*0.44704) ) / F
```

with `v = speed[t]`, `A`/`B`/`C` the rolling, rotating and drag terms,
`M = sourceMass` and `F = fixedMassFactor`. Speeds are mi/h, accelerations
mi/(h·s), VSP kW/tonne, and `0.44704` is (m·h)/(mi·s).

> **The Java's own `@algorithm` comment is wrong about `At0`, and the SQL is
> what runs.** The comment says
> `at0 = coalesce((speed[t]-speed[t-1])+grade, (speed[t+1]-speed[t])+grade, 0.0)`
> — a forward difference for the first second. The SQL two lines below it
> (`…java:1006-1009`) has **two** arguments, not three: the backward
> difference and `0.0`. Likewise the `VSP` comment lists a
> `speed[t+1]-speed[t]` fallback the SQL does not have. So the first second of
> every schedule is treated as having zero acceleration, and this port does
> the same. Forcing the comment's version instead is one of the perturbations
> in §6.5.

The mode is then assigned by a `CASE` whose arms are evaluated in order:

```
speed = 0                                      -> 501   (stopped)
speed < 1                                      -> 1     (idle)
At0 <= -2 or (At0 < -1 and At1 < -1 and At2 < -1) -> 0  (braking)
<the operatingMode rectangles, in opModeID order>
otherwise                                      -> -1
```

`buildOpModeClause` (`…java:241-300`) builds those rectangles from
`operatingMode` where `opModeID` is 1..99 **excluding 26 and 36**, which the
Java comments as "redundant with others". Each non-null bound contributes one
term, lower bounds inclusive and upper bounds exclusive:

| `opModeID` | `VSPLower` ≤ VSP | VSP < `VSPUpper` | `speedLower` ≤ speed | speed < `speedUpper` |
|---:|---:|---:|---:|---:|
| 1 | — | — | -1 | 1 |
| 11 | — | 0 | 1 | 25 |
| 12 | 0 | 3 | 1 | 25 |
| 13 | 3 | 6 | 1 | 25 |
| 14 | 6 | 9 | 1 | 25 |
| 15 | 9 | 12 | 1 | 25 |
| 16 | 12 | — | 1 | 25 |
| 21 | — | 0 | 25 | 50 |
| 22 | 0 | 3 | 25 | 50 |
| 23 | 3 | 6 | 25 | 50 |
| 24 | 6 | 9 | 25 | 50 |
| 25 | 9 | 12 | 25 | 50 |
| 27 | 12 | 18 | 25 | 50 |
| 28 | 18 | 24 | 25 | 50 |
| 29 | 24 | 30 | 25 | 50 |
| 30 | 30 | — | 25 | 50 |
| 33 | — | 6 | 50 | — |
| 35 | 6 | 12 | 50 | — |
| 37 | 12 | 18 | 50 | — |
| 38 | 18 | 24 | 50 | — |
| 39 | 24 | 30 | 50 | — |
| 40 | 30 | — | 50 | — |

Mode 1's row has no VSP bounds and `-1 <= speed < 1`, so it is unreachable
through the rectangles — the `speed < 1` arm above has already claimed every
second that could match it. It is in the list because `buildOpModeClause`
selects on `opModeID >= 1` and does not special-case it.

### 2.4 L-3 (tail) — counts, the quotient, and the pollutant-process fan-out

```
secondTotal = count(*)                       -- every second of the schedule
secondCount = count(*) group by opModeID
opModeFraction = secondCount * 1.0 / secondTotal
```

**`secondCount * 1.0 / secondTotal` is a five-decimal DECIMAL, not a double,
and the five is derivable rather than observed.** MariaDB's `int * 1.0` is
`DECIMAL` with scale 1; `DECIMAL / int` produces scale = dividend scale +
`div_precision_increment`, whose default is 4; 1 + 4 = 5, rounded half-up.
This is the same rule that makes
`docs/operating-mode-distribution.md`'s `COUNT(opModeID)/starts` a **four**-decimal
DECIMAL — there the dividend is `COUNT(…)`, an integer of scale 0, so 0 + 4 = 4.
Two neighbouring generators, one `* 1.0` apart, one digit apart. §6.3 checks
it against every bracketing cell in the corpus.

The distribution is then joined to `opModePolProcAssoc` `using (opModeID)` and
cross joined to `runSpecHourDay`. Mode 501 becomes mode **1** for every
pollutant-process except **11609** (brakewear PM), which keeps 501. Because
501 folds into 1, and 1 can already be present from the `speed < 1` arm, the
insert is `group by … sum(opModeFraction)` — the two contributions add.

### 2.5 L-4 — the model-year physics renumbering

The per-second table is built with `sut.tempSourceTypeID` as its source type,
so everything above is written under source type **100**, not 21. Then
`SourceTypePhysics.updateOperatingModeDistribution` (`SourceTypePhysics.java:236-241`)
runs for the link:

```
update OpModeDistribution
   set sourceTypeID = realSourceTypeID,
       opModeID     = opModeID + opModeIDOffset
 where sourceTypeID = tempSourceTypeID
   and opModeID >= 0 and opModeID < 100
   and (polProcessID < 0 or mod(polProcessID,100) = 1)
```

`sourceUseTypePhysicsMapping` in this snapshot is a single row: real 21, temp
100, offset **1000**. So modes 0…40 become 1000…1040 and the source type
becomes 21 — which is exactly what the snapshot holds, and why a reader
looking for op mode 23 in `OpModeDistribution` will not find it.

The `polProcessID < 0 or mod(polProcessID,100) = 1` guard is why only the
generic `-1` rows and the Running-Exhaust `9101` rows are lifted. The
generator's output carries no other pollutant-process, so in this corpus the
guard is satisfied by everything present; a snapshot selecting a second
process would test it, and none does (§8.4).

### 2.6 L-5 — the interpolation

For each `(polProcessID, hourDayID)` the two brackets have in common, and for
**every** mode in `physicsOperatingMode` within the offset band (here
1000…1099), not merely the modes that occurred:

```
opModeFraction = low + (high - low) * factor      -- coalesce(missing, 0)
```

then `delete from tempOpModeDistribution where opModeFraction <= 0` before the
insert. Running the full mode list and then dropping non-positives is not the
same as running the union of the two brackets' modes: a mode present in one
bracket only still interpolates to a positive value and must appear. Two of
the fixture's 42 interpolated cells (modes 1030 and 1040, absent from the
low bracket) exist for exactly that reason.

### 2.7 L-6 — the copy into `RatesOpModeDistribution`

`populateRatesOpModeDistribution` (`…java:448-458`) deletes the road type's
existing rows and re-inserts from `OpModeDistribution`:

```
select sourceTypeID, hourDayID, polProcessID, opModeID, opModeFraction,
       <the link's roadTypeID>, 0 as avgSpeedBinID, <linkAvgSpeed> as avgBinSpeed
  from opModeDistribution
 inner join linkSourceTypeHour using (sourceTypeID, linkID)
 where polProcessID > 0 and linkID = <the link>
```

`polProcessID > 0` drops the generic `-1` rows, commented as "these are just
to speed up OMD population itself". So 42 `OpModeDistribution` rows for the
link become **21** `RatesOpModeDistribution` rows.

**This is the row set that made `./run-omd-oracle.sh` go red.** Four
generators write `RatesOpModeDistribution`; the sibling specification
partitioned it on `avgSpeedBinID == 0` alone, which does not separate this
generator's rows because it writes bin 0 too. The distinguishing column is
`roadTypeID`: `RatesOperatingModeDistributionGenerator` and
`StartOperatingModeDistributionGenerator` both write the literal 1, and this
one writes the link's own road type — 4 in the fixture.

## 3. Join structure

| # | left | right | `on` | cardinality |
|---|---|---|---|---|
| J1 | `driveScheduleAssoc` | `driveSchedule` | `driveScheduleID` | 11 candidates for (21, road type 4) |
| J2 | `driveScheduleSecondLink` a | same b, c, d | `linkID` and `secondID = secondID − 1, −2, −3` | three self-joins, all `LEFT` |
| J3 | the per-second table | `sourceUseTypePhysicsMapping` | cross product, then `runSpecSourceType.sourceTypeID = realSourceTypeID` | 1 physics row here |
| J4 | `tempDriveScheduleSecondLinkCount` | `…Total` | `sourceTypeID`, `linkID` | the divisor |
| J5 | the fraction table | `opModePolProcAssoc` | `opModeID` | 1 → {−1, 9101} for every mode present |
| J6 | J5 | `runSpecHourDay` | cross product | ×1 here |
| J7 | `physicsOperatingMode` | `sourceUseTypePhysicsMapping` | `opModeID DIV 100 = opModeIDOffset DIV 100` | the mode list for the offset band |
| J8 | low bracket | high bracket | `sourceTypeID`, `hourDayID`, `polProcessID`, `opModeID` | the interpolation |
| J9 | `OpModeDistribution` | `linkSourceTypeHour` | `sourceTypeID`, `linkID` | the rates copy |

J2 is the only one whose `LEFT` matters: it is what makes the first three
seconds of a schedule fall back to `0.0`.

## 4. Reusable shapes

* `lib/drive_cycle.esm` already carries the second-by-second drive-cycle
  shapes the tirewear rung needed. The VSP polynomial and the
  rectangle-assignment `CASE` are the two pieces this rung adds, and both are
  written there rather than in the component, because
  `AverageSpeedOperatingModeDistributionGenerator` and
  `OperatingModeDistributionGenerator` use the same two.
* The five-decimal DECIMAL quotient is the same shape as
  `lib/operating_mode.esm`'s four-decimal one with a different scale, so it
  is parameterised rather than copied.

## 5. Literals and enums

| literal | value | where it comes from |
|---|---|---|
| `0.44704` | (m·h)/(mi·s) | the unit conversion, written into the SQL |
| `9.81` | m/s² | gravity, written into the SQL |
| `-2`, `-1` | mi/(h·s) | the braking thresholds, written into the SQL |
| `26`, `36` | op modes | excluded by `buildOpModeClause` as "redundant with others" |
| `501` | op mode | the stopped bin, folded to 1 except for polProcess 11609 |
| `11609` | polProcessID | brakewear PM, the one process that keeps mode 501 |
| `100` | mode band width | `opModeID >= 0 and opModeID < 100` gates the physics offset |
| `4` | `div_precision_increment` | MariaDB's default, and the reason the quotient has five decimals |

Everything else — the coefficients, the band edges, the offset — is read from
the execution database.

## 6. Hand-checkable worked examples

### 6.0 Run-level values used by every example

From `scale-project`'s execution database:

| | |
|---|---|
| `link` | `linkID` 1, `roadTypeID` 4, `linkAvgSpeed` **30**, `linkAvgGrade` **0** |
| `linkSourceTypeHour` | (1, 21) — passenger cars only |
| `runSpecHourDay` | `hourDayID` **95** (hour 9, day 5) |
| `sourceUseTypePhysicsMapping` | real 21 → temp 100, offset **1000**, `A` 0.156461, `B` 0.00200193, `C` 0.000492646, `sourceMass` **1.4788**, `fixedMassFactor` **1.4788** |
| candidate schedules for (21, 4) | 11, from 2.5 to 76 mi/h |

Because `linkAvgGrade` is 0, `sin(atan(0/100))` is 0 and both grade terms
vanish; because `sourceMass == fixedMassFactor`, the division by `F` is a
no-op. Neither is a property of the model and both are recorded in §8.4 as
unexercised.

### 6.1 Worked example A — the brackets and the factor

The eleven candidates, by `averageSpeed`:

| schedule | 101 | 1033 | 1043 | **1021** | **153** | 1020 | 1019 | 1018 | 1017 | 1009 | 158 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| mi/h | 2.5 | 8.71909 | 15.733 | **20.6006** | **30.5** | 46.132 | 58.7949 | 64.3993 | 66.3632 | 73.7991 | 76 |

`linkAvgSpeed` is 30, so the greatest at or below is **1021** at 20.6006 and
the least at or above is **153** at 30.5. Neither out-of-bounds fallback
fires.

```
factor = (30 − 20.6006) / (30.5 − 20.6006) = 9.3994 / 9.8994 = 0.9494918883972766
```

The two schedules become pseudo-links **−1021** and **−153**, which is why
`OpModeDistribution` in the snapshot carries three link ids for a
one-link project.

### 6.2 Worked example B — three seconds of schedule 153, assigned by hand

Schedule 153 ("LD LOS E Freeway") opens `33.8, 33.4, 33.0, 31.9, 32.3, …`
mi/h. With `g = 0`:

| t | speed | `speed[t]−speed[t−1]` | At0 | VSP | mode |
|---:|---:|---:|---:|---:|---:|
| 0 | 33.8 | — (no t−1) | **0.0** | 3.0570003101339895 | **23** |
| 3 | 31.9 | −1.1 | −1.1 | −4.262308318302009 | **21** |
| 11 | 32.6 | −2.0 | **−2.0** | −10.169303518659751 | **0** |

* **t = 0** is the first second, so the `LEFT JOIN` to t−1 gives NULL, the
  whole `(a.speed−b.speed)+grade` is NULL, and `coalesce(…, 0.0)` makes At0
  zero. The VSP acceleration term uses `coalesce(a.speed−b.speed, 0.0)` and is
  likewise zero, leaving only the road-load polynomial:
  `15.109952 × (0.156461 + 15.109952 × (0.00200193 + 0.000492646 × 15.109952)) / 1.4788`
  = 3.0570003101339895. Speed 33.8 is in [25, 50) and VSP is in [3, 6), so
  mode **23**.
* **t = 3** has At0 = −1.1, which is greater than −2, so the first braking
  test fails; the second needs At1 and At2 below −1 as well and At1 is
  33.0 − 33.4 = −0.4, so it fails too. Speed 31.9 is in [25, 50) and VSP is
  negative, so mode **21** — coasting, not braking.
* **t = 11** has At0 = exactly −2.0, and the test is `At0 <= -2`, so it is
  **braking**, mode 0, regardless of its VSP. The boundary is inclusive.

### 6.3 Worked example C — the five-decimal quotient

Schedule 1021 has **905** seconds, of which **76** are assigned mode 0
(braking). Schedule 153 has **456**, of which **52** are.

```
76 / 905  = 0.08397790055248619…   ->  DECIMAL(_,5) half-up  ->  0.08398
52 / 456  = 0.11403508771929824…   ->  DECIMAL(_,5) half-up  ->  0.11404
```

and the snapshot stores exactly `8.398e-02` and `1.1404e-01`. Under a double
the stored values would carry the full mantissa; under a **four**-decimal
DECIMAL they would be `0.0840` and `0.1140`. §6.5 asserts the five-decimal
answer on all 80 bracketing cells and both alternatives are perturbations.

After the physics offset, mode 0 is stored as mode **1000**.

### 6.4 Worked example D — the interpolation, and where FLOAT decides it

For mode 1000 the two brackets give 0.08398 and 0.11404:

```
0.08398 + (0.11404 − 0.08398) × 0.9494918883972766 = 0.11252172835580503
```

which the snapshot stores as `1.12522e-01` — six significant digits, because
`OpModeDistribution.opModeFraction` is a `FLOAT` column and MariaDB renders a
FLOAT with six. Rounded either as a double or through a single, this cell
gives 0.112522. It does not decide anything.

**Two cells do.** Mode 1011 and mode 1015:

| mode | low | high | in double | in single | snapshot |
|---:|---:|---:|---|---|---|
| 1011 | 0.17459 | 0.08553 | 0.09002825241933854 → `0.0900283` | 0.09002824872732162 → `0.0900282` | **`9.00282e-02`** |
| 1015 | 0.00884 | 0.03728 | 0.035843549306018546 → `0.0358435` | 0.03584355115890503 → `0.0358436` | **`3.58436e-02`** |

The single-precision round-trip moves the sixth digit **down** on one and
**up** on the other, so this is not a systematic bias that some other rounding
rule would also produce. Keeping the interpolation in double reproduces 38 of
the 42 interpolated cells; storing the result through a single reproduces
**42 of 42**. Both are asserted in §6.5, in opposite directions, so that the
right answer must land exactly and the wrong one must miss.

### 6.5 The reproduction script

Run by `./run-link-omd-oracle.sh` over every snapshot. Since 2026-11-09 the
corpus has four PROJECT runs — `scale-project` and `rates-project` (one link,
source type 21, one physics row), `project-links` (links 1, 2 and an
off-network link 3; source types 21 and 32, the latter with three physics
rows; pollutant-processes −1, 201, 9101 and brake 11609) and
`project-offnetwork` (link 1 and an off-network link 2; source types 21 and 62,
the latter with eleven physics rows) — and the script reproduces every row the
generator leaves in them. What it models, each established by measurement on
those snapshots:

* **per link, in `linkID` order**, skipping road type 1 (`executeLoop` never
  calls the generator for an off-network link);
* **brackets per REAL source type** — `driveScheduleAssoc` is keyed by it —
  for each RunSpec source type; the bracket lines print one per (link, source
  type);
* **one core run per bracketing schedule per physics row**: each
  `sourceUseTypePhysicsMapping` row (one temp source type each) gets its own
  VSP from its own coefficients, and `SourceTypePhysics` renames it to the
  real source type at `mode + opModeIDOffset`, so a real source type with
  three physics rows holds three disjoint bands (1100…, 1200…, 1300…) on the
  same pseudo-link, each summing to one;
* **the pseudo-link is replaced, not merged**: `delete … where linkID=-S`
  precedes each core run, so the final table holds the last link's use of
  schedule S (not exercised: no two links in the corpus share a schedule);
* **brake 11609's stopped mode**: 501 is kept for 11609 and folded into 1 for
  everything else, but `SourceTypePhysics`' `physics_` path lifts 11609 only
  `where opModeID <> 501`, so the 501 row stays under the **temp** source type
  (100, 101, …), unoffset, one per physics row; and because the interpolation
  selects only the real source type's rows and only the physics band's modes,
  **no 11609 mode-501 row reaches a real link**;
* **the 501→1 fold** is a `sum()` over a FLOAT column: each DECIMAL(.,5)
  quotient is narrowed to single, summed in double, narrowed again (the
  corpus has 60 such collisions and cannot tell this from summing the
  DECIMALs first — both reproduce);
* **the interpolation per real source type** over the union of its physics
  rows' `physicsOperatingMode` bands, narrowed to single;
* **user input is not output.** Rows with `isUserInput='Y'` — in the corpus,
  `project-links`' start distribution (202 and 9102, modes 101…108) on
  off-network link 3 — are the generator's `tempExistingOpMode` input: they
  are read for the exclusion and the stand-down test and excluded from the
  comparison and from the scheduling predicate;
* **tire wear 11710 is another generator's**
  (`AverageSpeedOperatingModeDistributionGenerator`) and is excluded by name;
  a separate small check reproduces what the final `RatesOpModeDistribution`
  holds of it (§7.1).

It asserts: the key set 0 missing / 0 extra and every cell equal under the
six-digit FLOAT rendering, on real links and pseudo-links alike; the
DECIMAL(.,5) quotient on every pseudo-link cell; the brake mode-501 cells; the
double alternative to the interpolation's FLOAT narrowing still missing at
least one cell; the `RatesOpModeDistribution` copy and the tire-wear rows key
for key; the scheduling predicate on every snapshot; and FLOORS (lower
bounds, the corpus grows) on every count.

```python
#!/usr/bin/env python3
"""Independent reproduction of LinkOperatingModeDistributionGenerator.

Reads only: link, driveSchedule, driveScheduleAssoc, driveScheduleSecond,
operatingMode, physicsOperatingMode, sourceUseTypePhysicsMapping,
opModePolProcAssoc, runSpecHourDay, runSpecSourceType, linkSourceTypeHour,
and the USER-INPUT rows of opModeDistribution (isUserInput='Y'), which are
the generator's `tempExistingOpMode` input and not its output.

Compares against: the generator's rows of opModeDistribution
(isUserInput='N') and ratesOpModeDistribution, which are read to be
compared with and for the scheduling predicate, never as input.
"""
import collections
import glob
import math
import os
import re
import struct
import sys
from decimal import Decimal, ROUND_HALF_UP

import pyarrow.parquet as pq


# --------------------------------------------------------------- table access
def tab(root, snap, name, columns=None):
    """One execution-database table as a list of dicts, or None if absent."""
    hits = sorted(glob.glob(
        f"{root}/{snap}/tables/db__movesexecution*__{name.lower()}.parquet"))
    if not hits:
        return None
    rows = []
    for h in hits:
        t = pq.ParquetFile(h).read(columns=columns).to_pydict()
        n = len(next(iter(t.values()))) if t else 0
        rows += [{k: t[k][i] for k in t} for i in range(n)]
    return rows


def num(x):
    """A snapshot cell to float. moves-snapshot/v2 stores floats as text."""
    return None if x is None else float(x)


def f32(x):
    """Round a double to the nearest IEEE single, as a FLOAT column store does."""
    return struct.unpack("f", struct.pack("f", x))[0]


def print6(x):
    """MariaDB's FLOAT-column rendering: six significant digits."""
    return float("%.6g" % x)


# Tire wear's 11710 rows come from AverageSpeedOperatingModeDistributionGenerator,
# not from this generator; they are checked separately (tirewear_rows) and kept
# out of every comparison of this generator's output.
TIREWEAR = 11710
BRAKE = 11609


# ------------------------------------------------------- the generator, step 105
def brackets(cands, average_speed):
    """The low and high bracketing drive schedules for one (sourceType, roadType).

    Four INSERTs in the Java, in this order, the 2nd and 4th `insert ignore`:
      low  = the schedule with the greatest averageSpeed <= link speed;
             failing that, the least averageSpeed > link speed (out of bounds low)
      high = the schedule with the least averageSpeed >= link speed;
             failing that, the greatest averageSpeed < link speed (out of bounds high)
    `max(driveScheduleID)` breaks a tie on averageSpeed, which is why the pools
    are compared on the (speed, id) pair.
    """
    below = [c for c in cands if c[0] <= average_speed]
    above = [c for c in cands if c[0] > average_speed]
    at_or_above = [c for c in cands if c[0] >= average_speed]
    strictly_below = [c for c in cands if c[0] < average_speed]

    low, oob_low = (max(below), 0) if below else ((min(above), 1) if above else (None, 0))
    high, oob_high = ((min(at_or_above), 0) if at_or_above
                      else ((max(strictly_below), 1) if strictly_below else (None, 0)))
    return low, high, oob_low, oob_high


def op_mode_bands(operating_mode):
    """The CASE arms `buildOpModeClause` emits, in opModeID order.

    `where opModeID >= 1 and opModeID <= 99 and opModeID not in (26,36)` --
    26 and 36 are commented in the Java as redundant with others.
    """
    rows = sorted((r for r in operating_mode
                   if 1 <= r["opModeID"] <= 99 and r["opModeID"] not in (26, 36)),
                  key=lambda r: r["opModeID"])
    return [(r["opModeID"], num(r["VSPLower"]), num(r["VSPUpper"]),
             num(r["speedLower"]), num(r["speedUpper"])) for r in rows]


def assign_op_mode(bands, speed, vsp, at0, at1, at2):
    """@step 110's `update ... set opModeID = case ... end`, in its own order."""
    if speed == 0:
        return 501                       # stopped; becomes 1 below unless 11609
    if speed < 1:
        return 1                         # idle
    if at0 <= -2 or (at0 < -1 and at1 < -1 and at2 < -1):
        return 0                         # braking
    for om, vsp_lo, vsp_hi, spd_lo, spd_hi in bands:
        if vsp_lo is not None and not vsp_lo <= vsp:
            continue
        if vsp_hi is not None and not vsp < vsp_hi:
            continue
        if spd_lo is not None and not spd_lo <= speed:
            continue
        if spd_hi is not None and not speed < spd_hi:
            continue
        return om
    return -1


def core_distribution(seconds, grade, physics, bands, omppa, hourdays):
    """calculateOpModeFractionsCore on one pseudo-link for ONE physics row
    (one temp source type), then SourceTypePhysics' renumbering.

    `seconds` is [(secondID, speed)] sorted. `grade` is the real link's
    linkAvgGrade, copied onto every second of every bracketing schedule.
    Returns {(sourceTypeID, polProcessID, hourDayID, opModeID): fraction}.
    """
    a_term, b_term, c_term = physics["A"], physics["B"], physics["C"]
    mass, fmf = physics["mass"], physics["fmf"]
    grade_rad = math.atan(grade / 100.0)
    grade_accel = 9.81 / 0.44704 * math.sin(grade_rad)
    grade_force = 9.81 * math.sin(grade_rad)

    speed_at = dict(seconds)
    counts = collections.Counter()
    for sec, speed in seconds:
        p1 = speed_at.get(sec - 1)
        p2 = speed_at.get(sec - 2)
        p3 = speed_at.get(sec - 3)
        # `coalesce((a.speed-b.speed)+grade, 0.0)`: a missing neighbour makes the
        # whole sum NULL, so the fallback is 0.0 and NOT a forward difference.
        # The Java's @algorithm comment claims a `speed[t+1]-speed[t]` second
        # argument; the SQL it documents has no such argument. The SQL wins.
        at0 = (speed - p1) + grade_accel if p1 is not None else 0.0
        at1 = (p1 - p2) + grade_accel if None not in (p1, p2) else 0.0
        at2 = (p2 - p3) + grade_accel if None not in (p2, p3) else 0.0

        ms = speed * 0.44704                      # mi/h -> m/s
        dv = (speed - p1) if p1 is not None else 0.0
        vsp = (ms * (a_term + ms * (b_term + c_term * ms))
               + mass * ms * dv * 0.44704
               + mass * grade_force * ms) / fmf
        counts[assign_op_mode(bands, speed, vsp, at0, at1, at2)] += 1

    total = len(seconds)
    parts = collections.defaultdict(list)
    for om, n in counts.items():
        # `(secondCount*1.0/secondTotal)`. MariaDB: `int * 1.0` is DECIMAL with
        # scale 1, and DECIMAL/int adds div_precision_increment (default 4), so
        # the quotient is DECIMAL(_,5) rounded half-up -- not a double, and not
        # the four decimals the sibling generator's `COUNT(x)/starts` gives.
        frac = (Decimal(n) * Decimal("1.0") / Decimal(total)).quantize(
            Decimal("0.00001"), rounding=ROUND_HALF_UP)
        for pp in omppa.get(om, ()):
            mode = (501 if pp == BRAKE else 1) if om == 501 else om
            for hd in hourdays:
                # Into opModeDistributionTemp, whose opModeFraction is FLOAT.
                parts[(pp, hd, mode)].append(f32(float(frac)))

    # `insert ignore ... select ..., sum(opModeFraction) ... group by`: the
    # stopped seconds (501) folding into idle (1) can collide with real idle
    # seconds (0 < speed < 1); the sum is a DOUBLE sum of the two FLOATs,
    # stored back into a FLOAT.
    temp, real, offset = physics["temp"], physics["real"], physics["offset"]
    out = {}
    for (pp, hd, mode), xs in parts.items():
        frac = f32(sum(xs))
        # SourceTypePhysics.updateOperatingModeDistribution, per physics row:
        #  * generic (pp < 0) and running-exhaust (pp % 100 == 1) rows in
        #    0..99 move to the real source type at mode + opModeIDOffset;
        #  * brake 11609 goes through `physics_opModeDistribution`, whose
        #    update is `where opModeID <> 501`: every 0..99 mode is lifted to
        #    the real source type, and mode 501 is NOT -- it is re-inserted
        #    unchanged, still under the TEMP source type;
        #  * any other polProcessID would stay under the temp source type.
        if pp == BRAKE:
            key = (temp, pp, hd, 501) if mode == 501 else (real, pp, hd, mode + offset)
        elif (pp < 0 or pp % 100 == 1) and 0 <= mode < 100:
            key = (real, pp, hd, mode + offset)
        else:
            key = (temp, pp, hd, mode)
        out[key] = frac
    return out


def load(root, snap):
    """Every input the generator reads, once per snapshot."""
    links = tab(root, snap, "link")
    physics_rows = tab(root, snap, "sourceusetypephysicsmapping") or []
    if not links or not physics_rows:
        return None
    physics_of = collections.defaultdict(list)          # real -> [physics row]
    for p in sorted(physics_rows, key=lambda p: p["opModeIDOffset"]):
        physics_of[p["realSourceTypeID"]].append(
            {"A": num(p["rollingTermA"]), "B": num(p["rotatingTermB"]),
             "C": num(p["dragTermC"]), "mass": num(p["sourceMass"]),
             "fmf": num(p["fixedMassFactor"]), "offset": p["opModeIDOffset"],
             "real": p["realSourceTypeID"], "temp": p["tempSourceTypeID"]})

    seconds_of = collections.defaultdict(list)
    for r in tab(root, snap, "driveschedulesecond"):
        seconds_of[r["driveScheduleID"]].append((r["second"], num(r["speed"])))
    for k in seconds_of:
        seconds_of[k].sort()

    omppa = collections.defaultdict(list)
    for r in tab(root, snap, "opmodepolprocassoc"):
        omppa[r["opModeID"]].append(r["polProcessID"])

    pom = [r["opModeID"] for r in tab(root, snap, "physicsoperatingmode")]
    # The interpolation's mode list for a REAL source type is the union of
    # the physicsOperatingMode bands of ALL its physics rows
    # (`pom.opModeID DIV 100 = sutpm.opModeIDOffset DIV 100`).
    modes_of = {st: sorted({m for m in pom for p in ps if m // 100 == p["offset"] // 100})
                for st, ps in physics_of.items()}

    # tempExistingOpMode: the (sourceType, link, polProcess) triples that were
    # in opModeDistribution before the generator first ran. In a snapshot
    # those are exactly the isUserInput='Y' rows.
    user = [r for r in tab(root, snap, "opmodedistribution") if r["isUserInput"] == "Y"]
    return {
        "links": sorted(links, key=lambda r: r["linkID"]),
        "physics_of": physics_of,
        "schedule_speed": {r["driveScheduleID"]: num(r["averageSpeed"])
                           for r in tab(root, snap, "driveschedule")},
        "assoc": tab(root, snap, "drivescheduleassoc"),
        "bands": op_mode_bands(tab(root, snap, "operatingmode")),
        "operating_mode": tab(root, snap, "operatingmode"),
        "seconds_of": seconds_of,
        "omppa": omppa,
        "hourdays": sorted({r["hourDayID"] for r in tab(root, snap, "runspechourday")}),
        "run_source_types": sorted({r["sourceTypeID"] for r in tab(root, snap, "runspecsourcetype")}),
        "modes_of": modes_of,
        "lsth": {(r["linkID"], r["sourceTypeID"])
                 for r in (tab(root, snap, "linksourcetypehour") or [])},
        "user_rows": user,
        "existing": {(r["sourceTypeID"], r["linkID"], r["polProcessID"]) for r in user},
    }


def interpolate(lowd, highd, st, modes, factor, as_float=True):
    """Step 105's interpolation for one real source type.

    `tempOpModeDistribution2` is the FULL physics op-mode list of the real
    source type crossed with every (hourDay, polProcess) either bracket holds
    for it, `coalesce(opModeFraction, 0)` for a mode a bracket never entered;
    the low and high copies are then INNER-joined, so a (polProcess, hourDay)
    must be on both brackets. Non-positive results are dropped. The 11609
    mode-501 rows sit under the TEMP source types and so are never selected.
    """
    def pairs(d):
        return {(k[1], k[2]) for k in d if k[0] == st}
    out = {}
    for pp, hd in sorted(pairs(lowd) & pairs(highd)):
        for mode in modes:
            lo = lowd.get((st, pp, hd, mode), 0.0)
            hi = highd.get((st, pp, hd, mode), 0.0)
            v = lo + (hi - lo) * factor
            if as_float:
                v = f32(v)
            if v > 0:
                out[(st, pp, hd, mode)] = v
    return out


def link_distribution(ctx):
    """The whole generator for one PROJECT snapshot.

    Returns ({linkID: {(st, pp, hd, mode): fraction}}, [bracket detail]),
    `linkID` negative for a pseudo-link (-driveScheduleID).
    """
    produced = {}
    detail = []
    for link in ctx["links"]:
        link_id = link["linkID"]
        road_type = link["roadTypeID"]
        speed = num(link["linkAvgSpeed"])
        grade = num(link["linkAvgGrade"]) or 0.0
        # executeLoop: `if(roadTypeRecordID != 1)` -- off-network links never
        # reach the generator.
        if road_type == 1:
            continue
        # calculateOpModeFractions: a link with its own running-type
        # (pp % 100 == 1) user distribution is left alone; only the
        # linkAvgSpeed > 0, no-drive-schedule path (step 105) is reproduced.
        if any(l == link_id and pp % 100 == 1 for (_, l, pp) in ctx["existing"]):
            continue
        if not speed or speed <= 0:
            continue

        # Brackets are chosen per REAL source type (driveScheduleAssoc is
        # keyed by it); the RunSpec's source types are the ones the core
        # computes (`inner join RunSpecSourceType`).
        chosen = {}
        for st in ctx["run_source_types"]:
            if st not in ctx["physics_of"]:
                continue
            cands = sorted((ctx["schedule_speed"][r["driveScheduleID"]], r["driveScheduleID"])
                           for r in ctx["assoc"]
                           if r["sourceTypeID"] == st and r["roadTypeID"] == road_type)
            low, high, oob_lo, oob_hi = brackets(cands, speed)
            if low is None or high is None:
                continue
            chosen[st] = (low, high, oob_lo, oob_hi)

        # One core run per bracketing schedule, for the source types it
        # brackets on THIS link. `delete from opModeDistribution where
        # linkID=-S` first: a later link that reuses schedule S replaces
        # every row of pseudo-link -S, so the final table holds the LAST
        # link's source types for it.
        schedule_types = collections.defaultdict(set)
        for st, (low, high, _, _) in chosen.items():
            schedule_types[low[1]].add(st)
            schedule_types[high[1]].add(st)
        for sched, sts in sorted(schedule_types.items()):
            rows = {}
            for st in sorted(sts):
                for physics in ctx["physics_of"][st]:
                    rows.update(core_distribution(ctx["seconds_of"][sched], grade, physics,
                                                  ctx["bands"], ctx["omppa"], ctx["hourdays"]))
            produced[-sched] = rows

        rows = {}
        for st, (low, high, oob_lo, oob_hi) in sorted(chosen.items()):
            factor = ((speed - low[0]) / (high[0] - low[0])) if low[0] < high[0] else 0.0
            for k, v in interpolate(produced[-low[1]], produced[-high[1]], st,
                                    ctx["modes_of"][st], factor).items():
                # `left join tempExistingOpMode ... where eom.* is null`
                if (k[0], link_id, k[1]) not in ctx["existing"]:
                    rows[k] = v
            detail.append({"link": link_id, "sourceTypeID": st, "low": low, "high": high,
                           "factor": factor, "oob_low": oob_lo, "oob_high": oob_hi,
                           "roadTypeID": road_type, "avgSpeed": speed})
        produced[link_id] = rows
        # offsetUserInputOpModeIDs rewrites only linkID > 0 rows with
        # opModeID < 100; every generated real-link row is >= 1000 and the
        # corpus's user rows are start modes 101..108, so it is a no-op here.
    return produced, detail


def rates_copy(ctx, produced):
    """populateRatesOpModeDistribution, as the FINAL table shows it.

    Step 200 deletes the previous link's road type and the current one before
    copying, so the table ends up holding the rows of the LAST on-network link
    processed only (links are visited in linkID order): every
    opModeDistribution row on that link -- generated or user input -- with
    polProcessID > 0 and a linkSourceTypeHour row, at the link's road type,
    avgSpeedBinID 0 and avgBinSpeed = linkAvgSpeed.
    """
    on_network = [l for l in ctx["links"] if l["roadTypeID"] != 1 and l["linkID"] in produced]
    if not on_network:
        return {}, None
    last = on_network[-1]
    link_id, road_type, speed = last["linkID"], last["roadTypeID"], num(last["linkAvgSpeed"])
    rows = dict(produced[link_id])
    for r in ctx["user_rows"]:
        if r["linkID"] == link_id:
            rows[(r["sourceTypeID"], r["polProcessID"], r["hourDayID"], r["opModeID"])] = \
                num(r["opModeFraction"])
    out = {}
    for (st, pp, hd, mode), frac in rows.items():
        if pp <= 0:                     # "don't copy the generic polprocess entries"
            continue
        if (link_id, st) not in ctx["lsth"]:
            continue
        out[(st, road_type, 0, hd, pp, mode)] = (frac, speed)
    return out, last


def tirewear_rows(ctx):
    """AverageSpeedOperatingModeDistributionGenerator's PROJECT tire wear rows,
    as the FINAL ratesOpModeDistribution shows them.

    One mode per link from linkAvgSpeed (`when linkAvgSpeed<0.1 then 400`,
    else the 'tirewear%' row in 401..499 with speedLower <= speed <
    speedUpper), fraction 1, for every RunSpec source type and hour-day. Each
    link starts with `delete ... where polProcessID=11710`, so only the LAST
    link visited -- on- OR off-network -- survives.
    """
    bands = sorted(((num(r["speedLower"]), num(r["speedUpper"]), r["opModeID"])
                    for r in ctx["operating_mode"]
                    if 401 <= r["opModeID"] <= 499 and r["opModeName"].startswith("tirewear")),
                   key=lambda b: (b[0] is not None, b[0]))
    out = {}
    for link in ctx["links"]:
        speed = num(link["linkAvgSpeed"])
        mode = -1
        if speed < 0.1:
            mode = 400
        else:
            for lo, hi, om in bands:
                if (lo is None or lo <= speed) and (hi is None or speed < hi):
                    mode = om
                    break
        out[link["linkID"]] = {(st, link["roadTypeID"], 0, hd, TIREWEAR, mode): (1.0, speed)
                               for st in ctx["run_source_types"] for hd in ctx["hourdays"]}
    last = ctx["links"][-1]["linkID"]
    return out[last], {k: next(iter(v))[5] for k, v in out.items()}


# ------------------------------------------------------------------- the sweep
def is_project(fixtures, snap):
    path = os.path.join(fixtures, snap + ".xml")
    if not os.path.exists(path):
        return False
    return bool(re.search(r'<modeldomain value="PROJECT"', open(path).read()))


def main(root):
    fixtures = os.path.join(os.path.dirname(root.rstrip("/")), "fixtures")
    snaps = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))

    swept = ran = 0
    sched_bad = []
    cells = exact = 0
    real_cells = 0
    missing = extra = 0
    worst = 0.0
    f64_would_miss = 0
    decimal_cells = decimal_exact = 0
    brake501_cells = brake501_exact = 0
    user_rows = 0
    rates_cells = rates_exact = 0
    rates_missing = rates_extra = 0
    tire_cells = tire_exact = 0
    tire_missing = tire_extra = 0
    brackets_seen = []
    rates_seen = []
    tire_seen = []

    for snap in snaps:
        omd = tab(root, snap, "opmodedistribution", ["linkID", "isUserInput"])
        if omd is None:
            continue                      # not an execution database this port models
        swept += 1
        project = is_project(fixtures, snap)
        # THE SCHEDULING PREDICATE. LinkOMDG is on the DO_RATES_FIRST whitelist
        # (MOVESInstantiator.java:1462) but only the PROJECT domain gives it a
        # link to run on, and `OpModeDistribution` is its only output table.
        # User-input rows are not its output, so they do not count.
        non_empty = any(r["isUserInput"] != "Y" for r in omd)
        if non_empty != project:
            sched_bad.append((snap, non_empty, project))
        if not project:
            continue
        ran += 1

        ctx = load(root, snap)
        if ctx is None:
            sched_bad.append((snap, non_empty, "no link table"))
            continue
        produced, detail = link_distribution(ctx)
        brackets_seen += [(snap, d) for d in detail]

        # The reference: this generator's rows only. isUserInput='Y' rows
        # (the start-mode 101..108 distribution a user supplied for an
        # off-network link) are INPUT; tire wear never lands here under
        # DO_RATES_FIRST but is excluded by name all the same.
        reference = collections.defaultdict(dict)
        for r in tab(root, snap, "opmodedistribution"):
            if r["isUserInput"] == "Y":
                user_rows += 1
                continue
            if r["polProcessID"] == TIREWEAR:
                continue
            reference[r["linkID"]][(r["sourceTypeID"], r["polProcessID"], r["hourDayID"],
                                    r["opModeID"])] = num(r["opModeFraction"])

        for link_id in sorted(set(produced) | set(reference)):
            pred = produced.get(link_id, {})
            ref = reference.get(link_id, {})
            missing += len(set(ref) - set(pred))
            extra += len(set(pred) - set(ref))
            for k in sorted(set(ref) & set(pred)):
                cells += 1
                real_cells += link_id > 0
                ok = print6(pred[k]) == ref[k]
                exact += ok
                if ref[k]:
                    worst = max(worst, abs(pred[k] - ref[k]) / abs(ref[k]))
                if link_id < 0:
                    # Every pseudo-link cell is a DECIMAL(.,5) quotient (or a
                    # FLOAT sum of two of them) narrowed once to FLOAT.
                    decimal_cells += 1
                    decimal_exact += ok
                    if k[1] == BRAKE and k[3] == 501:
                        brake501_cells += 1
                        brake501_exact += ok

        # The FLOAT-vs-double hypothesis for the interpolation, asserted apart.
        for d in detail:
            lowd, highd = produced[-d["low"][1]], produced[-d["high"][1]]
            alt = interpolate(lowd, highd, d["sourceTypeID"],
                              ctx["modes_of"][d["sourceTypeID"]], d["factor"], as_float=False)
            for k, v in reference.get(d["link"], {}).items():
                if k[0] == d["sourceTypeID"] and print6(alt.get(k, 0.0)) != v:
                    f64_would_miss += 1

        # ratesOpModeDistribution: only the last on-network link survives.
        # Rows at road type 1 (off-network: start, extended idle, hotelling,
        # and tire wear's off-network row) are other generators' and are not
        # compared here.
        rates_all = tab(root, snap, "ratesopmodedistribution") or []
        rates_ref = {(r["sourceTypeID"], r["roadTypeID"], r["avgSpeedBinID"],
                      r["hourDayID"], r["polProcessID"], r["opModeID"]):
                     (num(r["opModeFraction"]), num(r["avgBinSpeed"]))
                     for r in rates_all
                     if r["avgSpeedBinID"] == 0 and r["roadTypeID"] != 1
                     and r["polProcessID"] != TIREWEAR}
        pred_rates, last = rates_copy(ctx, produced)
        if last is not None:
            rates_seen.append((snap, last["linkID"], last["roadTypeID"], len(pred_rates)))
        rates_missing += len(set(rates_ref) - set(pred_rates))
        rates_extra += len(set(pred_rates) - set(rates_ref))
        for k in sorted(set(rates_ref) & set(pred_rates)):
            rates_cells += 1
            rates_exact += (print6(pred_rates[k][0]) == rates_ref[k][0]
                            and print6(pred_rates[k][1]) == rates_ref[k][1])

        # Tire wear (another generator), checked only where the run has it.
        tire_ref = {(r["sourceTypeID"], r["roadTypeID"], r["avgSpeedBinID"],
                     r["hourDayID"], r["polProcessID"], r["opModeID"]):
                    (num(r["opModeFraction"]), num(r["avgBinSpeed"]))
                    for r in rates_all if r["polProcessID"] == TIREWEAR}
        if tire_ref:
            pred_tire, per_link = tirewear_rows(ctx)
            tire_seen.append((snap, per_link))
            tire_missing += len(set(tire_ref) - set(pred_tire))
            tire_extra += len(set(pred_tire) - set(tire_ref))
            for k in sorted(set(tire_ref) & set(pred_tire)):
                tire_cells += 1
                tire_exact += (print6(pred_tire[k][0]) == tire_ref[k][0]
                               and print6(pred_tire[k][1]) == tire_ref[k][1])

    for snap, d in brackets_seen:
        print("  brackets %-18s link %-2d st %-3d low %s @ %g  high %s @ %g  factor %.16g%s"
              % (snap, d["link"], d["sourceTypeID"], d["low"][1], d["low"][0],
                 d["high"][1], d["high"][0], d["factor"],
                 "  OUT OF BOUNDS" if d["oob_low"] or d["oob_high"] else ""))
    for snap, link_id, road_type, n in rates_seen:
        print("  rates    %-18s last on-network link %d, road type %d: %d rows"
              % (snap, link_id, road_type, n))
    for snap, per_link in tire_seen:
        print("  tirewear %-18s mode per link %s (final table: last link only)"
              % (snap, per_link))
    print("  opModeDistribution   %4d cells (%d on real links), %d missing / %d extra"
          % (cells, real_cells, missing, extra))
    print("  reproduced exactly   %4d of %d under FLOAT storage" % (exact, cells))
    print("  worst relative error %.4g" % worst)
    print("  user-input rows      %4d excluded (isUserInput='Y', not this generator's)"
          % user_rows)
    print("  DECIMAL(.,5) quotient bit-exact on %d of %d bracketing cells"
          % (decimal_exact, decimal_cells))
    print("  brake 11609 mode 501 %d of %d pseudo-link cells (temp source types)"
          % (brake501_exact, brake501_cells))
    print("  the f64 alternative  misses %d of %d interpolated cells"
          % (f64_would_miss, real_cells))
    print("  ratesOpModeDistribution copy %d cells, %d exact, %d missing / %d extra"
          % (rates_cells, rates_exact, rates_missing, rates_extra))
    print("  tire wear 11710      %d cells, %d exact, %d missing / %d extra"
          % (tire_cells, tire_exact, tire_missing, tire_extra))
    print("  scheduling predicate %d snapshots swept, %d run the generator, %d disagreeing"
          % (swept, ran, len(sched_bad)))

    bad = []
    if missing or extra:
        bad.append("key set: %d missing, %d extra" % (missing, extra))
    if exact != cells:
        bad.append("%d of %d cells do not reproduce exactly" % (cells - exact, cells))
    if cells < FLOOR_CELLS:
        bad.append("only %d cells compared, expected >= %d" % (cells, FLOOR_CELLS))
    if decimal_exact != decimal_cells:
        bad.append("the DECIMAL(.,5) quotient is not bit-exact on %d cells"
                   % (decimal_cells - decimal_exact))
    if decimal_cells < FLOOR_DECIMAL:
        bad.append("only %d bracketing cells compared, expected >= %d"
                   % (decimal_cells, FLOOR_DECIMAL))
    if brake501_cells < FLOOR_BRAKE501:
        bad.append("only %d brake mode-501 cells compared, expected >= %d"
                   % (brake501_cells, FLOOR_BRAKE501))
    # The FLOAT intermediate is DECIDED here and nowhere else. Keeping the
    # interpolation in double misses cells; if it ever missed none, this
    # oracle would be asserting a distinction the corpus cannot see, and the
    # assertion has to fail rather than pass vacuously.
    if f64_would_miss < 1:
        bad.append("the double-precision alternative now reproduces every cell, "
                   "so the FLOAT round-trip is no longer distinguishable here")
    if rates_missing or rates_extra:
        bad.append("ratesOpModeDistribution key set: %d missing, %d extra"
                   % (rates_missing, rates_extra))
    if rates_cells < FLOOR_RATES:
        bad.append("only %d ratesOpModeDistribution cells compared, expected >= %d"
                   % (rates_cells, FLOOR_RATES))
    if rates_exact != rates_cells:
        bad.append("%d ratesOpModeDistribution cells differ" % (rates_cells - rates_exact))
    if tire_missing or tire_extra or tire_exact != tire_cells:
        bad.append("tire wear: %d missing, %d extra, %d differ"
                   % (tire_missing, tire_extra, tire_cells - tire_exact))
    if tire_cells < FLOOR_TIRE:
        bad.append("only %d tire wear cells compared, expected >= %d" % (tire_cells, FLOOR_TIRE))
    if sched_bad:
        bad.append("%d snapshots disagree with the scheduling predicate: %s"
                   % (len(sched_bad), sched_bad[:4]))
    if swept < FLOOR_SWEPT:
        bad.append("only %d snapshots swept, expected >= %d" % (swept, FLOOR_SWEPT))
    if ran < FLOOR_RAN:
        bad.append("only %d snapshots ran the generator, expected >= %d" % (ran, FLOOR_RAN))
    if bad:
        for b in bad:
            print("  FAIL: " + b, file=sys.stderr)
        sys.exit(1)


# FLOORS, not equalities: silent skipping can only make them go down, and the
# corpus is shared with the other rungs and grows (docs/esm-conventions.md
# §35.5). Measured 2026-11-09 over 4 PROJECT runs.
FLOOR_CELLS = 3650
FLOOR_DECIMAL = 2378
FLOOR_BRAKE501 = 16
FLOOR_RATES = 549
FLOOR_TIRE = 2
FLOOR_SWEPT = 66
FLOOR_RAN = 4

main(sys.argv[1])
```

### 6.6 What the component's inline tests check

`components/link_operating_mode_distribution.esm` carries its assertions over
one **complete** bracketing schedule rather than a sample of it — a fraction
computed over part of a schedule is a different number, not a smaller one.
The tests are: the eleven candidate schedules and which two bracket 30; the
factor; the three hand-assigned seconds of §6.2 including the inclusive `−2`
boundary; the five-decimal quotient on both brackets' mode-0 cells; the
+1000 offset; and the 42 → 21 drop of the generic `polProcessID` in the rates
copy.

## 7. Fidelity notes and tolerance

### 7.1 The measured result

`./run-link-omd-oracle.sh`, over all 66 snapshots carrying an execution
database (2026-11-09):

| | |
|---|---|
| `OpModeDistribution` | **3,650** cells (1,272 on real links, 2,378 on pseudo-links), 0 missing / 0 extra |
| reproduced exactly | **3,650 of 3,650** under FLOAT storage |
| worst relative error | **4.613 × 10⁻⁶** |
| user-input rows excluded | **32** (`project-links`, link 3, `isUserInput='Y'`) |
| the five-decimal quotient | bit-exact on **2,378 of 2,378** bracketing cells |
| brake 11609 mode 501 | **16 of 16** pseudo-link cells (4 schedules × temp source types 100…103) |
| the double alternative | misses **32 of 1,272** interpolated cells |
| `RatesOpModeDistribution` copy | **549** cells, 549 exact including `avgBinSpeed`, 0 missing / 0 extra |
| tire wear 11710 | **2** cells, 2 exact, 0 missing / 0 extra |
| scheduling predicate | **66** snapshots swept, **4** run the generator, **0** disagreeing |

Per (link, source type), the brackets and factors:

| snapshot | link | road type | speed | source type | low | high | factor |
|---|---|---|---|---|---|---|---|
| `scale-project`, `rates-project` | 1 | 4 | 30 | 21 | 1021 @ 20.6006 | 153 @ 30.5 | 0.9494918883972766 |
| `project-links` | 1 | 4 | 30 | 21, 32 | 1021 @ 20.6006 | 153 @ 30.5 | 0.9494918883972766 |
| `project-links` | 2 | 5 | 25 | 21, 32 | 1041 @ 18.5781 | 1030 @ 25.379 | 0.9442720816362539 |
| `project-offnetwork` | 1 | 4 | 30 | 21 | 1021 @ 20.6006 | 153 @ 30.5 | 0.9494918883972766 |
| `project-offnetwork` | 1 | 4 | 30 | 62 | 305 @ 25.6 | 306 @ 32.5 | 0.6376811594202898 |

Source types 21 and 32 share their candidate schedules in this corpus, so
they bracket identically; 62 does not. None is out of bounds.

**`RatesOpModeDistribution` is the state after the LAST link.** Step 200
deletes the previous link's road type and the current one before each copy,
so the final table holds only the last on-network link visited: link 2 at
road type 5 in `project-links` (237 rows: 20 per process for source type 21,
59 for 32, processes 201, 9101, 11609 — no 501), link 1 at road type 4 in the
other three (270, 21, 21 rows). Link 1's road-type-4 rows in `project-links`
were written and deleted and cannot be checked against the snapshot; the
oracle compares exactly the last link's copy and asserts no other on-network
road type survives. Rows at road type 1 (start, extended idle, hotelling,
user-input copies) belong to other generators and are not compared.

**Tire wear's final rows are likewise only the last link's.**
`AverageSpeedOperatingModeDistributionGenerator`'s project path deletes every
11710 row before writing each link, so of its per-link modes in
`project-links` — 407 for link 1 (30 mi/h), 406 for link 2 (25 mi/h), 400 for
link 3 (speed 0 < 0.1) — only link 3's survives: one row per source type at
road type 1, fraction 1, `avgBinSpeed` 0. The check reproduces those 2 rows;
the other two links' modes are computed and printed but not observable.

The 4.6 × 10⁻⁶ is not accumulated error and not a tolerance the port needs.
It is the reference's own storage: `opModeFraction` is a `FLOAT` column and
the capture records MariaDB's six-significant-digit rendering of it, so a
cell whose true value is 0.0900282487… is stored as `9.00282e-02` and nothing
downstream can recover the seventh digit. Compared as six-digit decimals —
which is all the reference has — every one of the 3,650 cells is **exact**.
`tolerance.toml`'s per-cell budget is 2 × 10⁻⁵ and this sits inside it, but
the oracle does not use that budget: it asserts equality of the rendered
value, which is stricter and which the corpus supports.

### 7.2 The FLOAT intermediate, decided by measurement

The interpolation reads two `FLOAT` columns, computes in double (MariaDB
promotes), and stores into a `FLOAT` column. Whether the port models that
final narrowing is decidable here, and the answer is yes — 42/42 with it,
38/42 without. §6.4 has the two cells.

This is worth stating plainly because the margin is small in absolute terms
(a seventh-digit difference) and it would have been easy to call it noise and
widen a tolerance. It is not noise: it is a storage step in the reference
implementation, it moves the answer in both directions, and the corpus can
see it. §6.5 asserts both ends separately and absolutely — the right
narrowing must reproduce every cell, and the wrong one must miss at least one
— so that if a future corpus ever stopped separating them the oracle would
fail rather than pass vacuously.

### 7.3 Precision-sensitive operations, ranked

1. **`secondCount * 1.0 / secondTotal`** — a five-decimal DECIMAL, half-up.
   Every downstream number descends from it. Getting the scale wrong by one
   moves every cell by up to 5 × 10⁻⁶ relative, which the six-digit reference
   can see.
2. **The interpolation's FLOAT round-trip** — §7.2. Four cells.
3. **The VSP polynomial** — evaluated in double throughout, Horner form as
   the SQL writes it. It only ever feeds a rectangle comparison, so an error
   matters only when it moves a second across a band edge; none of the 1,361
   seconds in the two schedules sits within 10⁻⁹ of an edge, so the binning
   is not precision-sensitive **in this corpus** (§8.4).
4. **`atan`/`sin` of the grade** — exercised only at grade 0, where both are
   exactly 0. Not precision-sensitive here, and not checked (§8.4).

## 8. Gaps and things not verified

### 8.1 Three of the four paths through L-1 are ported and unreachable

The corpus takes the average-speed path. Ported from the SQL and **not
checked** by anything:

* the **drive-schedule path** (`hasDriveSchedule`), which runs L-3 directly on
  a user-supplied `driveScheduleSecondLink`;
* the **zero-speed path**, which synthesises thirty seconds of idle when
  `linkAvgSpeed <= 0` and then takes the drive-schedule path;
* the **user-distribution path**, which stands down entirely when
  `OpModeDistribution` already holds a Running-Exhaust row for the link.

Also unreachable: both **out-of-bounds bracket flags** and the
`ALLOW_DRIVE_CYCLE_EXTRAPOLATION` behaviour behind them. The fixture's link
speed of 30 mi/h sits inside the candidate range 2.5…76, and reaching either
flag needs a link outside it — a one-line change to
`../moves.rs/characterization/county-inputs/washtenaw-project/setup-project.sql`
and a new capture, not `.esm` work.

### 8.2 The empty `OpModeDistribution` is an input-database choice, not a fact

`setup-project.sql` creates `OpModeDistribution` and `driveScheduleSecondLink`
empty on purpose, with a comment saying why: a seeded `OpModeDistribution`
would send the generator down the user-distribution path and the snapshot
would pin its own input. So the corpus's ability to see this generator at all
rests on a decision in a `moves.rs` fixture, and a future edit there could
silently remove it. The scheduling predicate in §6.5 is the guard: if
`scale-project` ever stops producing rows it fails, rather than the
comparison quietly having nothing to compare.

### 8.3 Links, source types, physics rows and processes — now reproduced

Until 2026-11-09 every fan-out in §3 had cardinality 1. `project-links` and
`project-offnetwork` changed that, and §6.5 reproduces them exactly:

| dimension | in the corpus | status |
|---|---|---|
| links | up to 2 on-network + 1 off-network per run | reproduced; the off-network skip and the per-link loop are exercised |
| source types | 21, 32, 62; two per run | reproduced; brackets per real source type |
| physics mapping rows | 1, 3 (st 32: two regulatory classes, a model-year break at 2010) and 11 (st 62) | reproduced; per-row coefficients, `sourceMass ≠ fixedMassFactor`, offsets 1000…2100 |
| pollutant-processes | −1, 201, 9101, 11609 | reproduced, including the `mod(polProcessID,100) = 1` guard's complement through the 11609 `physics_` path and mode 501 under the temp source types |
| user-input rows | 32 start rows on an off-network link | excluded as input; they do not touch the generator's path |
| hour-days | 1 | **unexercised**: the `runSpecHourDay` cross join |

Still not exercised: **two links sharing a bracketing schedule** (the
replace-not-merge of the pseudo-link, modelled in §6.5 but with no snapshot
that could tell it from a merge); **two on-network links of the same road
type** (L-6's delete of the current road type); and every link's
`RatesOpModeDistribution` copy except the last's, which the final table
cannot show (§7.1). A pollutant-process other than −1, x01 and 11609 in the
generator's fan-out (which would stay under the temp source type) does not
occur.

### 8.4 What the fixture's zeros hide

* **`linkAvgGrade` is 0**, so `sin(atan(g/100))` is 0 and both grade terms
  drop out of At0/At1/At2 and VSP. A non-zero grade is ported and unchecked.
* **`sourceMass == fixedMassFactor == 1.4788`** for source type 21, so `/ F`
  is the identity there. Since 2026-11-09 it is not for every row: source
  type 32's model-year-banded rows (3.40194 / 2.05979 and 3.40194 / 5) and
  most of source type 62's do separate them, and dividing by `sourceMass`
  instead breaks 1,620 of 3,476 compared cells and the key set.
* **No second in either schedule lies within 10⁻⁹ of a band edge**, so the
  rectangle comparisons are not precision-sensitive here and a port using `<=`
  where MOVES uses `<` on an upper bound would still pass. The one boundary
  that *is* exercised is the braking test's `At0 <= -2`, which second 11 of
  schedule 153 hits exactly (§6.2) — flipping that comparison to `<` is a
  perturbation in §6.5 and it goes red.
* **The stale `@algorithm` comment is not falsifiable here, and this is the
  one probe of the eleven in §6.5 that does not go red.** §2.3 records that
  the Java's comment claims a forward-difference fallback for `At0` on the
  first second and the SQL it documents has none. Implementing the comment
  instead — `At0 = speed[t+1] − speed[t]` where there is no `t−1` — changes
  the assigned operating mode of **0 of the 1,361** seconds in the two
  schedules. Both schedules open with a small deceleration (33.8 → 33.4 and
  its counterpart), so the forward difference lands in the same rectangle the
  zero does, and neither reaches a braking threshold. The port follows the
  SQL because the SQL is what runs, not because the corpus said so. A
  schedule whose first second is a hard brake would decide it; neither of
  these is.

### 8.5 What the generator does that this port does not

* `modelYearPhysics.offsetUserInputOpModeIDs` runs after L-5. It renumbers
  `linkID > 0` rows with `opModeID < 100`, meant for a **user-supplied**
  running distribution. The corpus's only user rows are start modes 101…108,
  above its range, and every generated real-link row is ≥ 1000, so it is a
  no-op on every snapshot. Not ported.
* `createExpandedOperatingModesTable` materialises `physicsOperatingMode`.
  This port reads that table from the snapshot rather than building it,
  because `sourceUseTypePhysicsMapping` here has one row and the construction
  would be unverifiable — see `docs/esm-conventions.md` §35.3.
* The generator writes and then deletes `driveScheduleSecondLink`. This port
  never materialises it; the intermediate is not in the snapshot to compare
  against (§1.3).

## 9. Summary for the `.esm` author

Read one link's `linkAvgSpeed` and `linkAvgGrade`. Rank the drive schedules
that `driveScheduleAssoc` associates with the link's (source type, road type)
by `driveSchedule.averageSpeed`, take the nearest at-or-below and the nearest
at-or-above, and form `factor` from the three speeds. For each of the two
schedules, walk `driveScheduleSecond` in order: back-difference the speed
three times with `0.0` where a predecessor is missing, evaluate the VSP
polynomial in Horner form, and assign an operating mode by the ordered `CASE`
— stopped, idle, braking, then the (speed, VSP) rectangles from
`operatingMode` minus modes 26 and 36. Count the modes, divide by the number
of seconds **as a five-decimal half-up DECIMAL**, fan out over
`opModePolProcAssoc` and `runSpecHourDay` folding 501 into 1, add 1000 to
every mode and rename the source type. Then interpolate the two schedules
mode by mode over the full `physicsOperatingMode` band, **narrow the result to
a single**, drop the non-positives, and copy the positive-polProcess rows into
`RatesOpModeDistribution` at the link's own road type with `avgBinSpeed` set
to the link's speed.
