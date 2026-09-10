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
| Ported by | `lib/drive_cycle.esm` (the VSP and op-mode shapes), `components/link_operating_mode_distribution.esm` |
| Java | `.../ghg/LinkOperatingModeDistributionGenerator.java` (1,184 lines), `.../ghg/SourceTypePhysics.java` for the model-year offset |
| Rust | `../moves.rs/crates/moves-calculators/src/generators/link_op_mode_distribution.rs` |

`scale-project` names this specification because it is the only snapshot that
carries `OpModeDistribution` non-empty. It has no fixture of its own — its
`MOVESOutput` is a separate, unresolved matter recorded in
`../moves.rs/docs/known-divergences.md` §6.1 — so this specification borrows
its snapshot for the coverage tool's fixture leg exactly as
`docs/meteorology-generator.md` borrows `process-pm-exhaust`
(`docs/esm-conventions.md` §35.1).

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

```python
#!/usr/bin/env python3
"""Independent reproduction of LinkOperatingModeDistributionGenerator.

Reads only: link, driveSchedule, driveScheduleAssoc, driveScheduleSecond,
operatingMode, physicsOperatingMode, sourceUseTypePhysicsMapping,
opModePolProcAssoc, runSpecHourDay, runSpecSourceType, linkSourceTypeHour.

Compares against: opModeDistribution and ratesOpModeDistribution, which are
read to be compared with and for the scheduling predicate, never as input.
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
    """calculateOpModeFractionsCore on one pseudo-link, then the physics offset.

    `seconds` is [(secondID, speed)] sorted. `grade` is the real link's
    linkAvgGrade, copied onto every second of every bracketing schedule.
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
    out = collections.defaultdict(Decimal)
    for om, n in counts.items():
        # `(secondCount*1.0/secondTotal)`. MariaDB: `int * 1.0` is DECIMAL with
        # scale 1, and DECIMAL/int adds div_precision_increment (default 4), so
        # the quotient is DECIMAL(_,5) rounded half-up -- not a double, and not
        # the four decimals the sibling generator's `COUNT(x)/starts` gives.
        frac = (Decimal(n) * Decimal("1.0") / Decimal(total)).quantize(
            Decimal("0.00001"), rounding=ROUND_HALF_UP)
        for pp in omppa.get(om, ()):
            mode = (501 if pp == 11609 else 1) if om == 501 else om
            for hd in hourdays:
                # `group by ... sum(opModeFraction)`: 501 folding into 1 can
                # collide with a real idle row, and the sum is what MOVES keeps.
                out[(pp, hd, mode)] += frac

    # SourceTypePhysics.updateOperatingModeDistribution: the temp source type
    # becomes the real one and the mode is lifted into the model-year-physics
    # band, for the generic and Running-Exhaust polProcessIDs only.
    offset = physics["offset"]
    shifted = {}
    for (pp, hd, mode), frac in out.items():
        lifted = mode + offset if (pp < 0 or pp % 100 == 1) and 0 <= mode < 100 else mode
        shifted[(pp, hd, lifted)] = f32(float(frac))
    return shifted


def link_distribution(root, snap):
    """The whole generator for one PROJECT snapshot: {linkID: {key: fraction}}."""
    links = tab(root, snap, "link")
    physics_rows = tab(root, snap, "sourceusetypephysicsmapping") or []
    if not links or not physics_rows:
        return None, None
    p = physics_rows[0]
    physics = {"A": num(p["rollingTermA"]), "B": num(p["rotatingTermB"]),
               "C": num(p["dragTermC"]), "mass": num(p["sourceMass"]),
               "fmf": num(p["fixedMassFactor"]), "offset": p["opModeIDOffset"],
               "real": p["realSourceTypeID"], "temp": p["tempSourceTypeID"]}

    schedule_speed = {r["driveScheduleID"]: num(r["averageSpeed"])
                      for r in tab(root, snap, "driveschedule")}
    assoc = tab(root, snap, "drivescheduleassoc")
    bands = op_mode_bands(tab(root, snap, "operatingmode"))

    seconds_of = collections.defaultdict(list)
    for r in tab(root, snap, "driveschedulesecond"):
        seconds_of[r["driveScheduleID"]].append((r["second"], num(r["speed"])))
    for k in seconds_of:
        seconds_of[k].sort()

    omppa = collections.defaultdict(list)
    for r in tab(root, snap, "opmodepolprocassoc"):
        omppa[r["opModeID"]].append(r["polProcessID"])
    hourdays = sorted({r["hourDayID"] for r in tab(root, snap, "runspechourday")})
    physics_modes = sorted({r["opModeID"] for r in tab(root, snap, "physicsoperatingmode")
                            if r["opModeID"] // 100 == physics["offset"] // 100})

    produced = {}
    detail = {}
    for link in links:
        link_id = link["linkID"]
        road_type = link["roadTypeID"]
        speed = num(link["linkAvgSpeed"])
        grade = num(link["linkAvgGrade"]) or 0.0
        source_types = sorted({r["sourceTypeID"] for r in
                               (tab(root, snap, "linksourcetypehour") or [])
                               if r["linkID"] == link_id})
        for source_type in source_types:
            cands = sorted((schedule_speed[r["driveScheduleID"]], r["driveScheduleID"])
                           for r in assoc
                           if r["sourceTypeID"] == source_type and r["roadTypeID"] == road_type)
            low, high, oob_lo, oob_hi = brackets(cands, speed)
            if low is None or high is None:
                continue
            factor = ((speed - low[0]) / (high[0] - low[0])) if low[0] < high[0] else 0.0
            lowd = core_distribution(seconds_of[low[1]], grade, physics, bands, omppa, hourdays)
            highd = core_distribution(seconds_of[high[1]], grade, physics, bands, omppa, hourdays)
            produced[-low[1]] = lowd
            produced[-high[1]] = highd

            # The interpolation runs over the FULL physics op-mode list, with
            # `coalesce(opModeFraction, 0)` for a mode one bracket never
            # entered, and drops non-positive results before the insert.
            interpolated = {}
            for pp, hd in sorted({(k[0], k[1]) for k in list(lowd) + list(highd)}):
                for mode in physics_modes:
                    lo = lowd.get((pp, hd, mode), 0.0)
                    hi = highd.get((pp, hd, mode), 0.0)
                    value = f32(lo + (hi - lo) * factor)
                    if value > 0:
                        interpolated[(pp, hd, mode)] = value
            produced[link_id] = interpolated
            detail[link_id] = {"low": low, "high": high, "factor": factor,
                               "oob_low": oob_lo, "oob_high": oob_hi,
                               "roadTypeID": road_type, "avgSpeed": speed,
                               "sourceTypeID": source_type}
    return produced, detail


def rates_copy(root, snap, produced, detail):
    """populateRatesOpModeDistribution: the real link's rows, at its own road type."""
    lsth = tab(root, snap, "linksourcetypehour") or []
    out = {}
    for link_id, d in detail.items():
        pairs = {(r["linkID"], r["sourceTypeID"]) for r in lsth}
        for (pp, hd, mode), frac in produced[link_id].items():
            if pp <= 0:                     # "don't copy the generic polprocess entries"
                continue
            if (link_id, d["sourceTypeID"]) not in pairs:
                continue
            out[(d["sourceTypeID"], d["roadTypeID"], 0, hd, pp, mode)] = (frac, d["avgSpeed"])
    return out


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
    missing = extra = 0
    worst = 0.0
    f64_would_miss = 0
    decimal_cells = decimal_exact = 0
    rates_cells = rates_exact = 0
    brackets_seen = []

    for snap in snaps:
        omd = tab(root, snap, "opmodedistribution", ["linkID"])
        if omd is None:
            continue                      # not an execution database this port models
        swept += 1
        project = is_project(fixtures, snap)
        # THE SCHEDULING PREDICATE. LinkOMDG is on the DO_RATES_FIRST whitelist
        # (MOVESInstantiator.java:1462) but only the PROJECT domain gives it a
        # link to run on, and `OpModeDistribution` is its only output table.
        non_empty = len(omd) > 0
        if non_empty != project:
            sched_bad.append((snap, non_empty, project))
        if not project:
            continue
        ran += 1

        produced, detail = link_distribution(root, snap)
        if produced is None:
            sched_bad.append((snap, non_empty, "no link table"))
            continue
        brackets_seen += [(snap, k, v["low"], v["high"], v["factor"],
                           v["oob_low"], v["oob_high"]) for k, v in detail.items()]

        reference = collections.defaultdict(dict)
        for r in tab(root, snap, "opmodedistribution"):
            reference[r["linkID"]][(r["polProcessID"], r["hourDayID"], r["opModeID"])] = \
                num(r["opModeFraction"])

        for link_id, pred in produced.items():
            ref = reference.get(link_id, {})
            missing += len(set(ref) - set(pred))
            extra += len(set(pred) - set(ref))
            for k in sorted(set(ref) & set(pred)):
                cells += 1
                if print6(pred[k]) == ref[k]:
                    exact += 1
                if ref[k]:
                    worst = max(worst, abs(pred[k] - ref[k]) / abs(ref[k]))

        # The two hypotheses this snapshot can separate, asserted apart.
        for link_id, d in detail.items():
            lowd = produced[-d["low"][1]]
            highd = produced[-d["high"][1]]
            ref = reference.get(link_id, {})
            for k in sorted(ref):
                lo = lowd.get(k, 0.0)
                hi = highd.get(k, 0.0)
                v = lo + (hi - lo) * d["factor"]
                if print6(v) != ref[k]:
                    f64_would_miss += 1
            for pseudo in (-d["low"][1], -d["high"][1]):
                for k, v in produced[pseudo].items():
                    if k in reference.get(pseudo, {}):
                        decimal_cells += 1
                        decimal_exact += print6(v) == reference[pseudo][k]

        rates_ref = {(r["sourceTypeID"], r["roadTypeID"], r["avgSpeedBinID"],
                      r["hourDayID"], r["polProcessID"], r["opModeID"]):
                     (num(r["opModeFraction"]), num(r["avgBinSpeed"]))
                     for r in (tab(root, snap, "ratesopmodedistribution") or [])
                     if r["avgSpeedBinID"] == 0 and r["roadTypeID"] != 1}
        pred_rates = rates_copy(root, snap, produced, detail)
        missing += len(set(rates_ref) - set(pred_rates))
        extra += len(set(pred_rates) - set(rates_ref))
        for k in sorted(set(rates_ref) & set(pred_rates)):
            rates_cells += 1
            rates_exact += (print6(pred_rates[k][0]) == rates_ref[k][0]
                            and print6(pred_rates[k][1]) == rates_ref[k][1])

    for snap, link_id, low, high, factor, oob_lo, oob_hi in brackets_seen:
        print("  brackets %-14s link %-4d low %s @ %g  high %s @ %g  factor %.16g%s"
              % (snap, link_id, low[1], low[0], high[1], high[0], factor,
                 "  OUT OF BOUNDS" if oob_lo or oob_hi else ""))
    print("  opModeDistribution   %4d cells, %d missing / %d extra"
          % (cells, missing, extra))
    print("  reproduced exactly   %4d of %d under FLOAT storage" % (exact, cells))
    print("  worst relative error %.4g" % worst)
    print("  DECIMAL(.,5) quotient bit-exact on %d of %d bracketing cells"
          % (decimal_exact, decimal_cells))
    print("  the f64 alternative  misses %d of %d interpolated cells" % (f64_would_miss, cells and 42))
    print("  ratesOpModeDistribution copy %d cells, %d exact" % (rates_cells, rates_exact))
    print("  scheduling predicate %d snapshots swept, %d run the generator, %d disagreeing"
          % (swept, ran, len(sched_bad)))

    bad = []
    if missing or extra:
        bad.append("key set: %d missing, %d extra" % (missing, extra))
    if exact != cells:
        bad.append("%d of %d cells do not reproduce exactly" % (cells - exact, cells))
    if cells < 122:
        bad.append("only %d cells compared, expected >= 122" % cells)
    if decimal_exact != decimal_cells:
        bad.append("the DECIMAL(.,5) quotient is not bit-exact on %d cells"
                   % (decimal_cells - decimal_exact))
    if decimal_cells < 80:
        bad.append("only %d bracketing cells compared, expected >= 80" % decimal_cells)
    # The FLOAT intermediate is DECIDED here and nowhere else. Keeping the
    # interpolation in double misses four cells; if it ever missed none, this
    # oracle would be asserting a distinction the corpus cannot see, and the
    # assertion has to fail rather than pass vacuously.
    if f64_would_miss < 1:
        bad.append("the double-precision alternative now reproduces every cell, "
                   "so the FLOAT round-trip is no longer distinguishable here")
    if rates_cells < 21:
        bad.append("only %d ratesOpModeDistribution cells compared, expected >= 21" % rates_cells)
    if rates_exact != rates_cells:
        bad.append("%d ratesOpModeDistribution cells differ" % (rates_cells - rates_exact))
    if sched_bad:
        bad.append("%d snapshots disagree with the scheduling predicate: %s"
                   % (len(sched_bad), sched_bad[:4]))
    if swept < 43:
        bad.append("only %d snapshots swept, expected >= 43" % swept)
    if ran < 1:
        bad.append("no snapshot ran the generator; the corpus lost its PROJECT capture")
    if bad:
        for b in bad:
            print("  FAIL: " + b, file=sys.stderr)
        sys.exit(1)


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

`./run-link-omd-oracle.sh`, over all 43 snapshots carrying an execution
database:

| | |
|---|---|
| `OpModeDistribution` | **122** cells, 0 missing / 0 extra |
| reproduced exactly | **122 of 122** under FLOAT storage |
| worst relative error | **2.396 × 10⁻⁶** |
| the five-decimal quotient | bit-exact on **80 of 80** bracketing cells |
| the double alternative | misses **4 of 42** interpolated cells |
| `RatesOpModeDistribution` copy | **21** cells, 21 exact including `avgBinSpeed` |
| scheduling predicate | **43** snapshots swept, **1** runs the generator, **0** disagreeing |

The 2.396 × 10⁻⁶ is not accumulated error and not a tolerance the port needs.
It is the reference's own storage: `opModeFraction` is a `FLOAT` column and
the capture records MariaDB's six-significant-digit rendering of it, so a
cell whose true value is 0.0900282487… is stored as `9.00282e-02` and nothing
downstream can recover the seventh digit. Compared as six-digit decimals —
which is all the reference has — every one of the 122 cells is **exact**.
`tolerance.toml`'s per-cell budget is 2 × 10⁻⁵ and this sits an order of
magnitude inside it, but the oracle does not use that budget: it asserts
equality of the rendered value, which is stricter and which the corpus
supports.

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

### 8.3 One link, one source type, one hour-day, one process

Every fan-out in §3 has cardinality 1 in this corpus:

| dimension | in the fixture | what is therefore unexercised |
|---|---|---|
| links | 1 | the per-link loop, and `previousRoadTypeID`'s delete-before-insert in L-6 |
| source types | 1 | `tempLinkBracket`'s `group by sourceTypeID`, and per-source-type brackets |
| hour-days | 1 | the `runSpecHourDay` cross join |
| pollutant-processes | `-1` and `9101` | the `mod(polProcessID,100) = 1` guard in L-4, and mode 501's survival at 11609 |
| physics mapping rows | 1 | model-year-banded coefficients; `beginModelYearID`/`endModelYearID` are 1950/2060 |

A multi-link project RunSpec would exercise the first two and the L-6 delete;
none exists. This is the single largest gap in the rung and it is a `moves.rs`
capture, not `.esm` work.

### 8.4 What the fixture's zeros hide

* **`linkAvgGrade` is 0**, so `sin(atan(g/100))` is 0 and both grade terms
  drop out of At0/At1/At2 and VSP. A non-zero grade is ported and unchecked.
* **`sourceMass == fixedMassFactor == 1.4788`**, so `/ F` is the identity. A
  port that dropped the division, or that divided by `sourceMass` instead,
  would reproduce this corpus exactly. §6.5 cannot separate them and does not
  claim to.
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
  operating modes that came from a **user-supplied** distribution, and with
  the input table empty there are none. Not ported.
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
