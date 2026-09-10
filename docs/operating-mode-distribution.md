# The operating-mode-distribution generators — computation specification

Two of MOVES's five operating-mode-distribution generators are reachable from
the snapshot corpus. This specifies both, because they write the same table and
the only way to check either against that table is to know which rows belong to
the other.

`docs/omd-generator-reachability.md` is the measurement that chose them.
`LinkOperatingModeDistributionGenerator` has since been reached — `scale-project`
joined the corpus on 2026-09-10 — and has its own specification,
`docs/link-operating-mode-distribution.md`. The remaining three
(`OperatingModeDistributionGenerator` and the two `MesoscaleLookup` ones) are
not here because canonical MOVES never instantiates them under
`CompilationFlags.DO_RATES_FIRST`; that is a stronger claim than "no RunSpec
selects the domain" and it is argued in the reachability note.

**`scale-project` is why this document had to change, and the change is
instructive.** It contributes rows to `RatesOpModeDistribution` from a
generator this specification does not model, and it takes a branch of step 400
this specification did not know existed. Both are recorded below (§6.5's
partition comment, §7.1, §8.3); both went red in `./run-omd-oracle.sh` the day
the snapshot landed, which is what the oracle is for.

---

## 0. The generators at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/mixed-onroad.xml` |
| Model | ONROAD, rates-first (`CompilationFlags.DO_RATES_FIRST`), `modeldomain` `DEFAULT` |
| Reads | `SampleVehicleTrip`, `SampleVehicleDay`, `OperatingMode`, `HourDay`, `RunSpecHourDay`, `startsOpModeDistribution`, `pollutantProcessAssoc`, `sourceTypePolProcess`, `opModePolProcAssoc`, `runSpecSourceType`, `hotellingActivityDistribution` |
| Writes | `StartOpModeDistribution`, `SOMDGOpModes`, `StartsPerVehicleDay` and `RatesOpModeDistribution` |
| Output | **no `MOVESOutput` rows at all** — both are generators, and their product is an execution-database table |
| Calculator path | **`StartOperatingModeDistributionGenerator`**, **`RatesOperatingModeDistributionGenerator`** — two generators writing one table, with the rates-mode calculators downstream of it outside this slice |
| Rows | 201,665 `StartOpMode` + 84 `StartOpModeDistribution` + 168 `RatesOpModeDistribution` across the corpus (§7.1) |
| Ported by | `lib/operating_mode.esm` (the shapes), `components/start_operating_mode_distribution.esm` and `components/rates_operating_mode_distribution.esm` |
| Java | `.../ghg/StartOperatingModeDistributionGenerator.java` (479 lines), `.../ghg/RatesOperatingModeDistributionGenerator.java` (2,275 lines, of which two pages are live) |
| Rust | `../moves.rs/crates/moves-calculators/src/generators/start_operating_mode_distribution.rs`, `.../rates_op_mode_distribution.rs` |

`mixed-onroad` names this specification because it is the one snapshot that
carries **both** generators' tables non-empty and already has a fixture
(`fixtures/mixed-onroad.esm`) — the same arrangement
`docs/meteorology-generator.md` uses with `process-pm-exhaust`, and for the same
reason: a generator has no `MOVESOutput` row, so it borrows a fixture's snapshot
for the coverage tool's fixture leg (`docs/esm-conventions.md` §35.1).

### 0.1 Which runs they fire on, and how that was established

Both halves of a generator's claim are checked (§35.2): the rows, and *which
runs produce rows at all*. The predicates, asserted on all 43 snapshots
carrying an execution database — 43 as this is written, and the corpus grows —
including the 33 and 38 that fail them:

> `StartOpModeDistribution` populated ⇔ ONROAD **and** the run selects **Start
> Exhaust (2)**
>
> `RatesOpModeDistribution` carries a **hotelling** row ⇔ ONROAD **and** the run
> selects **Extended Idle (90) or Auxiliary Power (91)** **and** source type
> **62** is in `runSpecSourceType`

**The source type in the second predicate is not decoration, and leaving it out
is the mistake this rung nearly made.** `RatesOperatingModeDistributionGenerator`
subscribes to processes 1, 90 and 91 and is class-loaded in **31** of the 43
snapshots, but all four of its live `INSERT` statements are pinned to source
type 62 — through `sourceTypePolProcess` for the first of each pair and through
`runSpecSourceType` for the second. Six snapshots select Extended Idle for
source type 21 alone: MOVES loads the generator, runs it, and it emits nothing.
A predicate written on the process alone calls all six a failure. Class-loaded
and produced-output are different events, which is the same trap
`docs/omd-generator-reachability.md` measures on the other side and the
calculator track met at `nr-pleasure-craft-state`.

Counted with the source type: **9** snapshots run `StartOMDG`, **5** emit
`RatesOMDG` rows, and `process-tirewear`'s 32 rows in the same table belong to
`AverageSpeedOperatingModeDistributionGenerator` and to neither of these.

## 1. Input inventory

### 1.1 `StartOperatingModeDistributionGenerator`

| Table | Columns read | What it decides |
|---|---|---|
| `SampleVehicleTrip` | `vehID`, `tripID`, `priorTripID`, `hourID`, `dayID`, `keyOnTime`, `keyOffTime` | every start, and the soak before it |
| `SampleVehicleDay` | `vehID`, `sourceTypeID` | which source type a sampled vehicle is |
| `OperatingMode` | `opModeID`, `minSoakTime`, `maxSoakTime` | the soak-time bands |
| `HourDay`, `RunSpecHourDay` | `hourDayID`, `dayID`, `hourID` | which (hour, day) cells the run counts |
| `startsOpModeDistribution` | `dayID`, `hourID`, `sourceTypeID`, `ageID`, `opModeID`, `opModeFraction` | **step 400's actual input** — see §5 |
| `pollutantProcessAssoc` | `polProcessID`, `processID` | which start `polProcessID`s step 400 fans across |
| `runSpecSourceType` | `sourceTypeID` | the All Starts row's source types |

### 1.2 `RatesOperatingModeDistributionGenerator`

| Table | Columns read | What it decides |
|---|---|---|
| `pollutantProcessAssoc` | `polProcessID`, `processID` | the process-90 / 91 `polProcessID`s |
| `sourceTypePolProcess` | `sourceTypeID`, `polProcessID` | whether source type 62 is modelled for them |
| `opModePolProcAssoc` | `polProcessID`, `opModeID` | the associated operating modes |
| `hotellingActivityDistribution` | `opModeID` | the hotelling modes step 210 adds |
| `runSpecHourDay`, `runSpecSourceType` | `hourDayID`, `sourceTypeID` | the cross product every row is crossed with |

### 1.3 What is NOT an input

`RatesOperatingModeDistributionGenerator`'s drive-schedule tables —
`DriveSchedule`, `DriveScheduleSecond`, `DriveScheduleAssoc` — are read by the
dead half of the class (§4) and by no live statement. `SoakTime`,
`StartOpMode`, `StartsPerVehicleDay` and `existingStartOMD` are the first
generator's own temporary tables, not inputs; two of them are captured in the
snapshot and this port checks against them (§7.1).

## 2. The computation chain

| Step | Java | What it does |
|---|---|---|
| **S-1** | `calculateSoakTime` @step 100 | `soakTime = keyOnTime − keyOffTime[prior trip]`, over a `SampleVehicleTrip` self-join on `priorTripID` |
| **S-2** | `calculateStartOpMode` @step 200 | join each soak time against the `OperatingMode` soak bands, keep every match |
| **S-3** | `calculateOpModeFraction` @step 300 | `StartsPerVehicleDay.starts` per (sourceType, hourDay); `opModeFraction = COUNT(opModeID)/starts`; `SOMDGOpModes` = the distinct modes |
| **S-4** | `populateOperatingModeDistribution` @step 400 | copy into `RatesOpModeDistribution`, plus the All Starts row |
| **R-1** | `calculateExtendedIdleOpModeFractions` @step 200 | hotelling modes for process 90 × `runSpecHourDay`, fraction 1 |
| **R-2** | `calculateAuxiliaryPowerOpModeFractions` @step 210 | the same for process 91, excluding operating mode 200 |

### 2.1 S-1 — the soak, unfloored

```sql
CREATE TABLE SoakTime
SELECT svt2.vehID, svt2.tripID, svt2.keyOnTime - svt1.keyOffTime AS soakTime
FROM SampleVehicleTrip svt1
INNER JOIN SampleVehicleTrip svt2
  ON (svt2.vehID = svt1.vehID AND svt2.priorTripID = svt1.tripID)
```

An INNER JOIN, so the first trip of a vehicle's day — which has no
`priorTripID` — produces no soak-time row and is never classified. The join is
on `vehID` and `tripID` only, not on `dayID`; `(vehID, tripID)` is unique in all
nine populated snapshots (37,216 of 37,216 in `process-refueling`), so the
narrower key would select the same rows and the wider one is what MOVES writes.
The difference is not floored at zero: the sample records key-off times before
the day begins as negatives, and a soak of 2,608 minutes measured from −2,202 is
a real row of the reference.

### 2.2 S-2 — the band join is SQL three-valued logic

```sql
WHERE (minSoakTime <= soakTime OR (minSoakTime IS NULL AND maxSoakTime IS NOT NULL))
  AND (maxSoakTime >  soakTime OR (maxSoakTime IS NULL AND minSoakTime IS NOT NULL))
```

Four cases: both bounds present is the half-open interval `[min, max)`; only a
maximum is `soak < max`; only a minimum is `soak >= min`; **neither bound
matches nothing**, because each clause is then `NULL OR FALSE` = UNKNOWN and
`UNKNOWN AND UNKNOWN` is not TRUE.

That fourth case is the whole of the risk in this step. `OperatingMode` has 60
rows and **52 carry no soak band** — every VSP mode, braking, idling, the four
hotelling modes, and operating mode 100, "Starting (Used for all starts)".
Read an absent bound as an unbounded one and all 201,665 classified starts fall
into all 52. `lib/drive_cycle.esm`'s `in_half_open_range` reads it exactly that
way, which is why this port does not reuse it; `lib/operating_mode.esm`'s
`soak_band_contains` factors the two mirror-image clauses into one
`sql_bound_clause` applied twice.

### 2.3 S-3 — the quotient is a four-decimal DECIMAL

```sql
CREATE TABLE StartOpModeDistribution
SELECT sv.sourceTypeID, svd.hourDayID, opModeID, COUNT(opModeID)/starts AS opModeFraction
...
GROUP BY sv.sourceTypeID, svd.hourDayID, opModeID
```

`COUNT()` is a MariaDB `BIGINT` and `starts` is another; `/` between exact-value
operands is DECIMAL division whose scale is the dividend's plus
`div_precision_increment`, which MOVES leaves at its default of 4. So the stored
fraction is the rational quotient rounded to **four decimal places**, and the
`CREATE TABLE ... SELECT` gives the column that type. §7.2 is the measurement.

A `GROUP BY` emits no row for an empty group, so a (sourceType, hourDay) cell's
row count is the number of *non-empty* bands, not nine.

### 2.4 R-1 and R-2 — two statements each, unioned by `INSERT IGNORE`

Step 200 emits, for source type 62, road type 1, `avgSpeedBinID` 0,
`avgBinSpeed` 0 and `opModeFraction` 1: (a) the `opModePolProcAssoc` modes of
each process-90 `polProcessID` for which `sourceTypePolProcess` holds a
source-type-62 row, crossed with `runSpecHourDay`; and (b) operating mode 200
for every process-90 `polProcessID`, crossed with `runSpecHourDay`, whenever
source type 62 is in `runSpecSourceType`. Step 210 is the same for process 91
with `opModeID <> 200` on both statements, and draws (b)'s modes from
`hotellingActivityDistribution` instead of fixing them at 200.

`INSERT IGNORE` makes the second statement lose to the first on a primary-key
collision. That is a union rather than a sum only because every row either
statement emits carries the same constant non-key columns, so a collision is
always between value-identical rows — the argument
`lib/operating_mode.esm`'s `insert_ignore_union` carries with the operator.

## 3. Join structure

| Id | Join | Where |
|---|---|---|
| **J-OMD-1** | `SampleVehicleTrip.(vehID, tripID)` = the later trip's `(vehID, priorTripID)` | S-1 |
| **J-OMD-2** | `SampleVehicleDay.vehID` = `SampleVehicleTrip.vehID` | S-3 |
| **J-OMD-3** | `HourDay.(dayID, hourID)` = `SampleVehicleTrip.(dayID, hourID)`, then `RunSpecHourDay.hourDayID` | S-3 |
| **J-OMD-4** | `StartsPerVehicleDay.(sourceTypeID, dayID, hourID)` = the grouped trip's | S-3 |
| **J-OMD-5** | `sourceTypePolProcess.polProcessID` = `pollutantProcessAssoc.polProcessID`, then `opModePolProcAssoc.polProcessID` | R-1, R-2 |

The soak-band containment of S-2 is deliberately **not** in this table: it is a
range predicate, not an equality, so it is a `filter` and not a `join.on`
(`docs/esm-conventions.md` §3).

## 4. What is dead, and how that was established

`RatesOperatingModeDistributionGenerator.java` is 2,275 lines and two
`static final` flags in the pinned MOVES 5.0.1 source gate most of it:
`USE_EXTERNAL_GENERATOR_FOR_DRIVE_CYCLES` retires the second-by-second
bracketing / VSP / op-mode pipeline, and `USE_EXTERNAL_GENERATOR` retires the
Running-Exhaust branch of `calculateOpModeFractions` in favour of
`SourceTypePhysics.updateOperatingModeDistribution`. What executes is the
subscription, step 200 and step 210.

The corpus corroborates it rather than taking the flags' word: Running Exhaust
is selected in 32 of the 43 snapshots and **not one row** of any snapshot's
`RatesOpModeDistribution` is attributable to this module on process 1.

## 5. The fact about `StartOperatingModeDistributionGenerator` most likely to be missed

**Its two outputs come from two different inputs, and only one of them is the
soak-time histogram.**

`StartOpModeDistribution` — steps 100–300 — is computed from `SampleVehicleTrip`
soak times. `RatesOpModeDistribution` — step 400, in a non-project rates run —
does not read it at all:

```sql
insert ignore into ratesOpModeDistribution (...)
 select distinct 0 as avgSpeedBinID, 1 as roadTypeID, somd.sourceTypeID,
        (somd.hourID*10+somd.dayID) as hourDayID, ppa.polProcessID,
        somd.opModeID, somd.opModeFraction, null as opModeFractionCV
   from startsOpModeDistribution somd
   cross join pollutantprocessassoc ppa
  where ppa.processID in (2,16)
```

`startsOpModeDistribution` is the MOVES 3+ Starts-tool **input** table, keyed on
`(dayID, hourID, sourceTypeID, ageID, opModeID)`; the `SELECT DISTINCT` collapses
its age dimension, and the cross join fans it across the run's start and
crankcase-start `polProcessID`s. `process-refueling` makes the divergence plain:
its `StartOpModeDistribution` says mode 101 is 0.4444 of hourDay 72's starts and
its `RatesOpModeDistribution` says 0.124754, and both are right, because they
are different tables answering different questions from different sources.

`moves.rs`'s port models step 400 as a copy of the soak fractions and carries no
`polProcessID` on its rates row at all, so it would produce the first number
where MOVES produces the second. That is recorded here rather than fixed: this
repository ports MOVES, and `moves.rs` is a reference it is allowed to disagree
with when the snapshot says so.

The second statement of step 400 is a bare cross product with a hard-coded key:

```sql
select distinct sourceTypeID, 1, 0, hourDayID, 602 as polProcessID,
       100 as opModeID, 1 as opModeFraction
  from runSpecHourDay, runSpecSourceType
```

`602` is a literal in the Java — `@algorithm Add information for All Starts
using operating mode 100 and polProcessID 602` — and not a `polProcessID` the
run selects. It appears in no other table of any snapshot. A port that derived
it from `pollutantProcessAssoc` would emit nothing here.

## 6. Hand-checkable worked examples

### 6.0 The cell every example uses

`process-refueling`, source type 21, hourDay 72 (hour 7, day 2). Eighteen
starts survive the `priorTripID` inner join and the `SampleVehicleDay` join;
their soak times, in the order `components/start_operating_mode_distribution.esm`
carries them, are

```
492  494  848    3    5  748    3    4  848    3    5  748    3    4   15  377  828  2608
```

### 6.1 Worked example A — the bands

| mode | band | soaks it takes | count |
|---|---|---|---:|
| 100 | *neither bound* | — | **0** |
| 101 | `soak < 6` | 3, 5, 3, 4, 3, 5, 3, 4 | 8 |
| 102 | `6 ≤ soak < 30` | 15 | 1 |
| 103–106 | `30 ≤ soak < 360` | — | 0 |
| 107 | `360 ≤ soak < 720` | 492, 494, 377 | 3 |
| 108 | `720 ≤ soak` | 848, 748, 848, 748, 828, 2608 | 6 |

8 + 1 + 3 + 6 = 18, the cell's own `StartsPerVehicleDay.starts`.

### 6.2 Worked example B — the quotient, both ways

| mode | count/starts | exact | ×10⁴ + ½ | **stored** |
|---|---|---|---|---|
| 101 | 8/18 | 0.4444444444… | 4444.94 → 4444 | **0.4444** |
| 102 | 1/18 | 0.0555555555… | 556.06 → 556 | **0.0556** |
| 107 | 3/18 | 0.1666666666… | 1667.17 → 1667 | **0.1667** |
| 108 | 6/18 | 0.3333333333… | 3333.83 → 3333 | **0.3333** |

Two round down and two round up, which distinguishes rounding from truncation as
well as from the exact ratio. All four are what
`../moves.rs/characterization/snapshots/process-refueling`'s
`StartOpModeDistribution` stores. It stores them EXACTLY, in four decimals:
`moves-snapshot/v1` padded every float to twelve decimal places and this
sentence used to read "to twelve decimals", which described the capture format
and not the column.

### 6.3 Worked example C — the two hotelling snapshots

`process-extended-idle` selects process 90; `sourceTypePolProcess` is **empty**,
so R-1's first statement has no driver, and `runSpecSourceType` = {62}, so its
second emits operating mode 200 for `polProcessID` 9090. One mode × two hourDays
= the snapshot's **2** rows.

`process-apu` selects process 91; `sourceTypePolProcess` = {(62, 9191)} and
`opModePolProcAssoc` gives 9191 mode 201 alone, so R-2's first statement emits
{201}; `hotellingActivityDistribution` carries modes 200, 201, 203 and 204 and
R-2's second emits {201, 203, 204} after dropping 200. The union is
{201, 203, 204} — three modes × two hourDays = the snapshot's **6** rows. Mode
201 is emitted by both statements and appears once, which is `INSERT IGNORE`.

### 6.4 Worked example D — why `expand-counties` produces no hotelling row

`expand-counties` selects Extended Idle (90) and MOVES class-loads
`RatesOperatingModeDistributionGenerator` for it. Its `runSpecSourceType` is
{21}. Both of R-1's statements require source type 62 — one through
`sourceTypePolProcess`, one through `runSpecSourceType` — so both emit nothing,
and the snapshot's 18 `RatesOpModeDistribution` rows are all
`StartOperatingModeDistributionGenerator`'s. Five other snapshots are the same
shape. This is the example that fixes §0.1's predicate.

### 6.5 The reproduction script

```python
#!/usr/bin/env python3
"""Independent reproduction of the two reachable operating-mode-distribution
generators, from the snapshot corpus's INPUT tables only.

  StartOperatingModeDistributionGenerator  steps 100, 200, 300 and 400
  RatesOperatingModeDistributionGenerator  steps 200 and 210

It takes nothing from the generators' own outputs except to compare against,
and it is handed the snapshots DIRECTORY rather than one snapshot, because
half of each generator's claim is WHICH runs produce rows at all
(docs/esm-conventions.md section 35.2).

Usage:  repro.py <snapshots directory>
"""
import glob, os, re, sys

import pyarrow.parquet as pq

# --- reading -----------------------------------------------------------------

def tab(root, snap, name, cols=None):
    """One execution-database table, or None when the snapshot lacks it.

    Streamed in batches rather than read whole: the corpus holds tables of
    ~10^6 rows and a previous sweep OOMed this machine by materialising one as
    a Python dict.
    """
    f = glob.glob(os.path.join(root, snap, "tables", "*__%s.parquet" % name))
    if not f:
        return None
    rows = []
    for b in pq.ParquetFile(f[0]).iter_batches(batch_size=65536, columns=cols):
        rows.extend(b.to_pylist())
    return rows

def missing(v):
    """A NULL, as the parquet capture spells it (None, or a float NaN)."""
    return v is None or (isinstance(v, float) and v != v)

# --- the model ---------------------------------------------------------------

def soak_time(key_on_time, prior_key_off_time):
    """@step 100. MOVES does not floor the difference and neither does this."""
    return key_on_time - prior_key_off_time

def soak_band_contains(soak, lo, hi):
    """@step 200's band condition, in SQL three-valued logic.

        (minSoakTime <= soakTime OR (minSoakTime IS NULL AND maxSoakTime IS NOT NULL))
    AND (maxSoakTime > soakTime OR (maxSoakTime IS NULL AND minSoakTime IS NOT NULL))

    With BOTH bounds NULL each clause is `NULL OR FALSE` = UNKNOWN and the
    conjunction is not TRUE, so a bandless operating mode -- 52 of the
    OperatingMode table's 60 rows, mode 100 among them -- matches nothing.
    """
    has_lo, has_hi = not missing(lo), not missing(hi)
    lower = (lo <= soak) if has_lo else has_hi
    upper = (hi > soak) if has_hi else has_lo
    return lower and upper

def decimal_quotient(numerator, denominator):
    """`COUNT(opModeID)/starts` as MariaDB computes it.

    Both operands are BIGINT; `/` between exact-value operands yields DECIMAL
    at the dividend's scale plus `div_precision_increment`, which MOVES leaves
    at its default of 4, rounded half away from zero. Counts are non-negative,
    so half-away-from-zero is half-up. Done in integers so the rounding is the
    rational one and not a float's.
    """
    return ((numerator * 10**4 * 2 + denominator) // (2 * denominator)) / 10.0**4

def hour_day_id(hour_id, day_id):
    return hour_id * 10 + day_id

def classify_starts(trips, operating_modes):
    """@step 100 + 200 -> StartOpMode(vehID, tripID, opModeID)."""
    key_off = {(t["vehID"], t["tripID"]): t["keyOffTime"] for t in trips}
    bands = [(m["opModeID"], m["minSoakTime"], m["maxSoakTime"]) for m in operating_modes]
    out = []
    for t in trips:
        if missing(t["priorTripID"]):
            continue
        prior = key_off.get((t["vehID"], int(t["priorTripID"])))
        if prior is None:
            continue
        soak = soak_time(t["keyontime"], prior)
        for om, lo, hi in bands:
            if soak_band_contains(soak, lo, hi):
                out.append((t["vehID"], t["tripID"], int(om)))
    return out

def start_op_mode_distribution(root, snap, classified):
    """@step 300 -> StartsPerVehicleDay and StartOpModeDistribution.

    StartsPerVehicleDay counts the classified starts per (sourceTypeID,
    hourDayID) after the HourDay / RunSpecHourDay join; StartOpModeDistribution
    divides the per-band count by it.
    """
    trips = {(t["vehID"], t["tripID"]): t for t in tab(root, snap, "samplevehicletrip")}
    source_type = {d["vehID"]: d["sourceTypeID"] for d in tab(root, snap, "samplevehicleday")}
    hour_day = {(h["dayID"], h["hourID"]): h["hourDayID"] for h in tab(root, snap, "hourday")}
    selected = {r["hourDayID"] for r in tab(root, snap, "runspechourday")}
    starts, counts = {}, {}
    for veh, trip, om in classified:
        t = trips[(veh, trip)]
        st = source_type.get(veh)
        hd = hour_day.get((t["dayID"], t["hourID"]))
        if st is None or hd is None or hd not in selected:
            continue
        starts[(st, hd)] = starts.get((st, hd), 0) + 1
        counts[(st, hd, om)] = counts.get((st, hd, om), 0) + 1
    return starts, counts

def rates_op_mode_distribution(root, snap, onroad, processes, project=False):
    """RatesOMDG steps 200 and 210 plus StartOMDG step 400, under INSERT IGNORE.

    Returns {primary key -> opModeFraction}. The primary key is
    (sourceTypeID, roadTypeID, avgSpeedBinID, hourDayID, polProcessID, opModeID).

    `project` selects step 400's PROJECT branch; see the comment on it below.
    """
    if not onroad:
        return {}
    ppa = tab(root, snap, "pollutantprocessassoc", ["polProcessID", "processID"]) or []
    stpp = tab(root, snap, "sourcetypepolprocess", ["sourceTypeID", "polProcessID"]) or []
    omppa = tab(root, snap, "opmodepolprocassoc", ["polProcessID", "opModeID"]) or []
    hours = [r["hourDayID"] for r in (tab(root, snap, "runspechourday") or [])]
    src_types = [r["sourceTypeID"] for r in (tab(root, snap, "runspecsourcetype") or [])]
    hotelling = sorted({r["opModeID"] for r in
                        (tab(root, snap, "hotellingactivitydistribution", ["opModeID"]) or [])})
    starts_omd = tab(root, snap, "startsopmodedistribution",
                     ["dayID", "hourID", "sourceTypeID", "opModeID", "opModeFraction"]) or []

    rows = []                                  # (key, fraction), in statement order
    def emit(st, hd, pp, om, frac):
        rows.append(((st, 1, 0, hd, pp, om), frac))

    modes_of = {}
    for o in omppa:
        modes_of.setdefault(o["polProcessID"], []).append(o["opModeID"])

    # ---- RatesOperatingModeDistributionGenerator, when 90 or 91 is selected
    if 90 in processes or 91 in processes:
        for process, exclude_200, extra in ((90, False, None), (91, True, hotelling)):
            polprocs = {p["polProcessID"] for p in ppa if p["processID"] == process}
            # SQL 1: opModePolProcAssoc modes for (source type 62, polProcess)
            for r in stpp:
                if r["sourceTypeID"] != 62 or r["polProcessID"] not in polprocs:
                    continue
                for om in modes_of.get(r["polProcessID"], []):
                    if exclude_200 and om == 200:
                        continue
                    for hd in hours:
                        emit(62, hd, r["polProcessID"], om, 1.0)
            # SQL 2: mode 200 (process 90), or the hotelling modes (process 91)
            if 62 in src_types:
                for pp in sorted(polprocs):
                    for om in ([200] if extra is None else [m for m in extra if m != 200]):
                        for hd in hours:
                            emit(62, hd, pp, om, 1.0)

    # ---- StartOperatingModeDistributionGenerator step 400, when 2 is selected
    #
    # Step 400 HAS TWO BRANCHES and they read different tables
    # (StartOperatingModeDistributionGenerator.java:381-431). The condition is
    # the model domain, spelled `@condition Project domain` in the Java's own
    # annotation:
    #
    #   PROJECT      insert from OpModeDistribution, joined through
    #                sourceTypePolProcess and opModePolProcAssoc
    #   non-PROJECT  insert from startsOpModeDistribution, cross joined to
    #                pollutantProcessAssoc where processID in (2,16)
    #
    # The All-Starts row (602 / 100, from runSpecHourDay x runSpecSourceType)
    # is written AFTER the branch, on both paths.
    #
    # Every snapshot was non-PROJECT until `scale-project`, so only the second
    # branch was modelled and nothing could see the omission. On scale-project
    # the unbranched code predicted eight (21, 1, 0, 95, 9102, 101..108) rows
    # canonical never wrote: MOVES took the PROJECT branch, whose join needs
    # `omppa.opModeID = somd.opModeID`, and OpModeDistribution there holds only
    # project VSP modes 1000-1040, which no START polProcess has in
    # opModePolProcAssoc. The branch yields nothing, correctly.
    if 2 in processes:
        start_polprocs = sorted({p["polProcessID"] for p in ppa if p["processID"] in (2, 16)})
        if project:
            omd = tab(root, snap, "opmodedistribution",
                      ["sourceTypeID", "hourDayID", "opModeID", "opModeFraction"]) or []
            pp_of_st = {}
            for r in stpp:
                pp_of_st.setdefault(r["sourceTypeID"], []).append(r["polProcessID"])
            for r in omd:
                for pp in pp_of_st.get(r["sourceTypeID"], []):
                    if pp not in start_polprocs:
                        continue
                    if r["opModeID"] not in modes_of.get(pp, []):
                        continue
                    emit(r["sourceTypeID"], r["hourDayID"], pp,
                         r["opModeID"], float(r["opModeFraction"]))
        else:
            seen = set()
            for r in starts_omd:                  # `select distinct ... cross join`
                k = (r["sourceTypeID"], hour_day_id(r["hourID"], r["dayID"]),
                     r["opModeID"], float(r["opModeFraction"]))
                if k in seen:
                    continue
                seen.add(k)
                for pp in start_polprocs:
                    emit(k[0], k[1], pp, k[2], k[3])
        for hd in hours:                          # the All Starts row, 602 / 100
            for st in src_types:
                emit(st, hd, 602, 100, 1.0)

    out = {}
    for k, v in rows:                             # INSERT IGNORE: first wins
        out.setdefault(k, v)
    return out

# --- the sweep ---------------------------------------------------------------

def run_scope(root, fixtures, snap):
    """(is ONROAD, the processIDs the RunSpec selects, is PROJECT) for one snapshot.

    The model comes from the RunSpec's `<model>` element, which is what MOVES
    reads; a RunSpec with no such element is ONROAD, which MOVES's own default
    is and which `sample-runspec` relies on. The processes come from
    `RunSpecPollutantProcess`, whose polProcessID is pollutantID*100 + processID.

    The DOMAIN comes from `<modeldomain>`, absent meaning DEFAULT. It selects
    step 400's branch, which reads a different table on each side.
    """
    xml = os.path.join(fixtures, snap + ".xml")
    text = open(xml).read() if os.path.exists(xml) else ""
    models = set(re.findall(r'<model value="(\w+)"', text))
    domain = (re.findall(r'<modeldomain value="(\w+)"', text) or ["DEFAULT"])[0]
    procs = {r["polProcessID"] % 100 for r in (tab(root, snap, "runspecpollutantprocess") or [])}
    return models != {"NONROAD"}, procs, domain == "PROJECT"

def main(root):
    fixtures = os.path.join(os.path.dirname(root.rstrip("/")), "fixtures")
    snaps = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))

    som_rows = som_bad = 0
    somd_rows = somd_decimal_exact = somd_ratio_exact = 0
    somd_worst_ratio = 0.0
    rates_rows = rates_missing = rates_extra = 0
    rates_worst = 0.0
    sched_checked = sched_bad = 0
    populated_start = populated_rates = 0
    somdg_bad = 0

    for snap in snaps:
        reference_rates = tab(root, snap, "ratesopmodedistribution")
        if reference_rates is None:
            continue                     # not an execution database this port models
        onroad, procs, project = run_scope(root, fixtures, snap)

        # --- StartOMDG steps 100-300, where the run selected Start Exhaust ----
        reference_som = tab(root, snap, "startopmode")
        if reference_som is not None:
            classified = classify_starts(
                tab(root, snap, "samplevehicletrip"),
                tab(root, snap, "operatingmode", ["opModeID", "minSoakTime", "maxSoakTime"]))
            got = {(r["vehID"], r["tripID"], r["opModeID"]) for r in reference_som}
            pred = set(classified)
            som_rows += len(got)
            som_bad += len(got ^ pred)

            starts, counts = start_op_mode_distribution(root, snap, classified)
            reference_somd = {(r["sourceTypeID"], r["hourDayID"], r["opModeID"]):
                              float(r["opModeFraction"])
                              for r in tab(root, snap, "startopmodedistribution")}
            predicted_somd = {k: decimal_quotient(c, starts[(k[0], k[1])])
                              for k, c in counts.items()}
            if set(reference_somd) != set(predicted_somd):
                raise SystemExit("%s: StartOpModeDistribution key set differs: "
                                 "%d missing, %d extra"
                                 % (snap, len(set(reference_somd) - set(predicted_somd)),
                                    len(set(predicted_somd) - set(reference_somd))))
            for k, v in reference_somd.items():
                somd_rows += 1
                if predicted_somd[k] == v:
                    somd_decimal_exact += 1
                exact = counts[k] / starts[(k[0], k[1])]
                if exact == v:
                    somd_ratio_exact += 1
                somd_worst_ratio = max(somd_worst_ratio, abs(exact - v) / abs(v))

            # SOMDGOpModes is `select distinct opModeID from StartOpModeDistribution`
            reference_modes = {r["opModeID"] for r in (tab(root, snap, "somdgopmodes") or [])}
            if reference_modes != {k[2] for k in reference_somd}:
                somdg_bad += 1

        # --- the RatesOpModeDistribution rows these two generators own --------
        # FOUR generators write this table and the partition key is the PAIR
        # (roadTypeID, avgSpeedBinID), not avgSpeedBinID alone:
        #   RatesOMDG           roadTypeID 1, bin 0   (`1 as roadTypeID`)
        #   StartOMDG step 400  roadTypeID 1, bin 0   (`1 as roadTypeID`)
        #   AverageSpeedOMDG    bins 1-16
        #   LinkOMDG            the LINK's own roadTypeID, bin 0
        # `avgSpeedBinID == 0` alone was sufficient until a PROJECT snapshot
        # existed. `scale-project` has 22 rows here: one is StartOMDG's
        # All-Starts row at roadTypeID 1, and twenty-one are LinkOMDG copying
        # its freshly-computed OpModeDistribution across at the project link's
        # roadTypeID 4 with avgBinSpeed = linkAvgSpeed
        # (LinkOperatingModeDistributionGenerator.java:448-458). Without the
        # roadTypeID term those 21 read as 21 rows this specification failed to
        # predict, which is a different generator's output counted against it.
        reference = {(r["sourceTypeID"], r["roadTypeID"], r["avgSpeedBinID"], r["hourDayID"],
                      r["polProcessID"], r["opModeID"]): float(r["opModeFraction"])
                     for r in reference_rates
                     if r["avgSpeedBinID"] == 0 and r["roadTypeID"] == 1}
        predicted = rates_op_mode_distribution(root, snap, onroad, procs, project)
        rates_missing += len(set(reference) - set(predicted))
        rates_extra += len(set(predicted) - set(reference))
        for k, v in reference.items():
            if k not in predicted:
                continue
            rates_rows += 1
            err = abs(predicted[k] - v) / abs(v) if v else abs(predicted[k] - v)
            rates_worst = max(rates_worst, err)

        # --- the scheduling predicate, on the negatives as well ---------------
        sched_checked += 1
        # Both halves of a generator's claim: subscription AND the run scope
        # its statements need. RatesOMDG subscribes to 90/91 but every one of
        # its four statements is pinned to source type 62 -- through
        # `sourceTypePolProcess` for the first of each pair and through
        # `runSpecSourceType` for the second -- so a run selecting Extended
        # Idle for a source type that does not hotel loads the generator and
        # emits nothing. Six snapshots in the corpus are exactly that case,
        # which is why this predicate names the source type and not only the
        # process (docs/esm-conventions.md 35.2, and the class-loaded-is-not-
        # emitting trap docs/omd-generator-reachability.md measures).
        hotelling_selected = 62 in {r["sourceTypeID"] for r in
                                    (tab(root, snap, "runspecsourcetype") or [])}
        start_expected = onroad and 2 in procs
        rates_expected = onroad and (90 in procs or 91 in procs) and hotelling_selected
        start_seen = any(k[4] == 602 or k[5] in range(101, 109) for k in reference)
        rates_seen = any(k[5] >= 200 for k in reference)
        if start_seen != start_expected or rates_seen != rates_expected:
            sched_bad += 1
            print("  SCHEDULING MISMATCH %-30s start seen/expected %s/%s "
                  "rates seen/expected %s/%s"
                  % (snap, start_seen, start_expected, rates_seen, rates_expected))
        populated_start += 1 if start_expected else 0
        populated_rates += 1 if rates_expected else 0

    print("  StartOpMode           %6d rows, %d missing / %d extra" % (som_rows, som_bad, 0))
    print("  StartOpModeDistribution %4d rows, key set: 0 missing / 0 extra" % somd_rows)
    print("  SOMDGOpModes          %6d snapshots disagreeing on the distinct set" % somdg_bad)
    print("  RatesOpModeDistribution %4d rows compared, %d missing / %d extra"
          % (rates_rows, rates_missing, rates_extra))
    print("  worst relative error  %.4g   (RatesOpModeDistribution, FLOAT storage)" % rates_worst)
    print("  the four-decimal quotient is bit-exact on %d of %d StartOpModeDistribution rows"
          % (somd_decimal_exact, somd_rows))
    print("  the exact IEEE ratio  is bit-exact on %d of %d, worst relative %.4g"
          % (somd_ratio_exact, somd_rows, somd_worst_ratio))
    print("  scheduling predicate  %d snapshots, %d disagreeing; %d run StartOMDG, "
          "%d run RatesOMDG" % (sched_checked, sched_bad, populated_start, populated_rates))

    # ASSERTED, not merely printed (docs/esm-conventions.md 21): run-tests.sh
    # reads this script's EXIT CODE, so a regression that left the key set
    # intact and moved every value would otherwise be reported green.
    # FLOORS, not equalities, on the corpus-wide counts (35.5): the snapshot
    # directory is shared with the other rungs and it grows. Silent skipping
    # can only make a count go DOWN, so a floor keeps the whole of the
    # property. The counts pinned EXACTLY are the per-snapshot ones -- zero
    # missing, zero extra, zero scheduling disagreements -- which are
    # properties of the model rather than of the corpus.
    #
    # THESE FLOORS WENT DOWN ONCE, LEGITIMATELY, AND THAT IS THE ONLY WAY THEY
    # MAY. `<day key="5">` was an out-of-range 0-based INDEX into the sorted
    # DayOfAnyWeek list [2, 5]: it selected nothing and MOVES fell back to BOTH
    # day types, so 28 of the 42 snapshots ran two days against a one-day
    # intent. With `<day id="5">` honoured (moves.rs PR #55) every day-keyed
    # table halves, and these three counts fell from 262,442 / 124 / 300 to
    # 201,665 / 84 / 168 -- not by 2, because only 28 of the 42 were affected.
    # A floor over a shared corpus assumes the corpus's SHAPE is monotone as
    # well as its size. It is not: a correction to the RunSpec can shrink it.
    # Lowering a floor is therefore a claim about the corpus that has to be
    # justified by the correction, and this comment is that justification.
    bad = []
    if som_bad:                      bad.append("StartOpMode differs on %d rows" % som_bad)
    if som_rows < 201665:            bad.append("StartOpMode rows %d < 201665" % som_rows)
    if somd_rows < 84:               bad.append("StartOpModeDistribution rows %d < 84" % somd_rows)
    if somd_decimal_exact != somd_rows:
        bad.append("the four-decimal quotient is not bit-exact on %d rows"
                   % (somd_rows - somd_decimal_exact))
    if somd_worst_ratio <= 2e-5:
        bad.append("the exact ratio is no longer distinguishable from the reference "
                   "at tolerance.toml's 2e-5 (worst %.4g)" % somd_worst_ratio)
    if somdg_bad:                    bad.append("SOMDGOpModes differs in %d snapshots" % somdg_bad)
    if rates_missing or rates_extra:
        bad.append("RatesOpModeDistribution key set: %d missing, %d extra"
                   % (rates_missing, rates_extra))
    if rates_rows < 169:             bad.append("RatesOpModeDistribution rows %d < 169" % rates_rows)
    if rates_worst >= 2e-5:          bad.append("worst relative error %.4g >= 2e-5" % rates_worst)
    if sched_bad:                    bad.append("%d snapshots disagree with the "
                                                "scheduling predicate" % sched_bad)
    if sched_checked < 43:           bad.append("only %d snapshots swept, expected >= 43"
                                                % sched_checked)
    if bad:
        for b in bad:
            print("  FAIL: " + b, file=sys.stderr)
        sys.exit(1)

main(sys.argv[1])
```

### 6.6 What the components' inline tests check

`components/start_operating_mode_distribution.esm` carries 27 assertions over
one **complete** cell of the reference — all 18 starts of (source type 21,
hourDay 72), not a sample of them, because a fraction computed over part of a
group is a different number rather than a smaller one. Six tests: the bandless
mode 100 takes nothing; the two open-ended bands take 8 and 6; the closed bands
take 1 and 3 with four empty between them; the counts sum to the cell's
`starts`; the four stored fractions are the four-decimal DECIMAL and not the
IEEE ratio; and the soak times and the composed `hourDayID`.

`components/rates_operating_mode_distribution.esm` carries 21 assertions over
the four hotelling operating modes. Four tests: extended idle is {200} and comes
from step 200's *second* statement; auxiliary power is {201, 203, 204} with mode
200 excluded from *both* of step 210's statements; the two statements of step
210 overlap on mode 201 and the union is not a sum; and the shared row shape.

Both files' headers say which assertions face MOVES and which face the port
only (§35.4). The soak times face the port — MOVES drops the `SoakTime`
temporary table — and everything downstream of them faces the reference.

## 7. Fidelity notes and tolerance

### 7.1 The measured result

`./run-omd-oracle.sh`, over all 43 snapshots carrying an execution database:

| | |
|---|---|
| `StartOpMode` (steps 100 + 200) | **201,665** rows, 0 missing / 0 extra |
| `StartOpModeDistribution` (step 300) | **84** rows, key set 0 missing / 0 extra |
| `SOMDGOpModes` | 0 snapshots disagreeing on the distinct set |
| `RatesOpModeDistribution` (step 400, R-1, R-2) | **169** rows, 0 missing / 0 extra |
| worst relative error | **4.026 × 10⁻⁶** |
| four-decimal quotient | bit-exact on **84 of 84** |
| exact IEEE ratio | bit-exact on **7 of 84**, worst relative **5.767 × 10⁻³** |
| scheduling predicate | **43** snapshots, **0** disagreeing |

All four row counts came DOWN at the `<day key=> -> <day id=>` correction
(moves.rs PR #55), which is the only legitimate way a floor over this corpus
may fall: 28 of the 42 snapshots had been running BOTH day types against a
one-day intent, so every day-keyed table halves. They were 262,442 / 124 / 300
with a worst of 4.388 × 10⁻⁶ and the exact ratio bit-exact on 15 of 124. The
ratio is not 2 because only 28 of the 42 were affected. §6.5's floors carry the
same note.

The 4.388 × 10⁻⁶ is not accumulated error. It is the single-precision `FLOAT`
column `RatesOpModeDistribution.opModeFraction` against the `DOUBLE` input
`startsOpModeDistribution.opModeFraction` it is copied from: 0.104152542938
stored back as 0.104153. Every other comparison in the table is exact — the
`StartOpModeDistribution` fractions to the last bit, and the whole of
`StartOpMode` and the hotelling rows as key sets with no value to compare.

Row counts are asserted as **floors** and per-snapshot key sets as
**equalities**, per §35.5: the snapshot directory is shared with the other rungs
and grows, silent skipping can only make a count go down, and 0-missing /
0-extra is a property of the model rather than of the corpus.

### 7.2 The quotient, decided by measurement

`moves.rs`'s port returns the exact `f64` ratio and its module documentation
calls the four-place rounding "a divergence of up to 5 × 10⁻⁵ … still
untested". The corpus tests it:

| quotient | bit-exact rows | worst relative error |
|---|---:|---|
| MariaDB DECIMAL to `div_precision_increment` = 4 | **124 of 124** | **0** |
| exact IEEE ratio | 15 of 124 | **5.767 × 10⁻³** |

The 15 the exact ratio gets right are the ones whose value terminates at four
decimals anyway (0.9, 0.5, 0.1, 0.02 …). 107 of the 124 land outside
`tolerance.toml`'s 2 × 10⁻⁵ per-cell gate, so the wrong candidate fails loudly.

This is the mirror image of §35.3's meteorology result, where the same class of
question — *does MariaDB's decimal arithmetic reach the stored value?* — came
out the other way. Two data points, opposite answers, one rule:
`docs/esm-conventions.md` §39.2. It is deliberately not a `docs/findings/`
entry: that directory holds EarthSciAST format defects with executable repros,
and this is a fact about MOVES.

### 7.3 Precision-sensitive operations, ranked

1. **`COUNT(opModeID)/starts`** — the only division in either generator, and the
   only place a fidelity choice changes a stored value. §7.2.
2. **`hourID*10 + dayID`** — exact in every representation; listed because it is
   written in two places in the Java (step 300's `HourDay` join and step 400's
   inline rebuild) and a document that spelled them differently would be wrong
   in a way no tolerance would see.
3. **The soak-time subtraction** — two `INT` columns; exact.
4. Everything else is a literal `1` or `0`.

## 8. Gaps and things not verified

### 8.1 Four generators of the family are not reachable, and never will be

`OperatingModeDistributionGenerator`,
`MesoscaleLookupOperatingModeDistributionGenerator`,
`MesoscaleLookupTotalActivityGenerator` and `NewTvvYearGenerator` are
class-loaded in **0** of the 43 snapshots.

This used to read "five", with `LinkOperatingModeDistributionGenerator` among
them and "needs a project-scale RunSpec captured in `moves.rs`" as the reason
for all of them. The project-scale RunSpec was captured and exactly one of the
five moved. The other four do not need a capture: three are discarded by
`MOVESInstantiator.java:1449` under `DO_RATES_FIRST` and the fourth is not a
Java class at all. `docs/omd-generator-reachability.md` has the evidence.

### 8.3 Step 400's PROJECT arm is branched on but its INSERT emits nothing

Step 400 has two arms and the model domain chooses between them
(`StartOperatingModeDistributionGenerator.java:381-431`). §6.5 now takes the
PROJECT arm on a PROJECT RunSpec, and that change is load-bearing: forcing the
non-PROJECT arm on `scale-project` predicts eight
`(21, 1, 0, 95, 9102, 101..108)` rows canonical never wrote, and the oracle
goes red with `0 missing, 8 extra`.

**What is NOT established is the arm's own arithmetic.** On the one PROJECT
snapshot in the corpus it iterates 122 `OpModeDistribution` rows and emits
**zero**, because its `omppa.opModeID = somd.opModeID` join has no match: the
project link's operating modes are the VSP bins 1000–1040 and the only start
polProcess in scope is 9102, which `opModePolProcAssoc` never pairs with them.
So the corpus decides the branch CONDITION and not the branch BODY. The join is
still doing work and can still fail — deleting it emits 21 rows and the oracle
reports `0 missing, 21 extra` — but a snapshot in which the arm produces a row
does not exist, and until one does the emitted values are ported from the SQL
and unverified.

### 8.2 The inventory branch of step 400 is ported from the SQL and not checked

`populateOperatingModeDistribution`'s `else` arm — the non-rates-first path that
writes `OpModeDistribution` with a `cross join link` — is unreachable in this
corpus, because every snapshot runs with `DO_RATES_FIRST`. The `existingStartOMD`
bookkeeping in step 300 is likewise never observed: it is a `create table … like`
plus one `insert … select` whose result no live statement reads.

### 8.3 `AverageSpeedOperatingModeDistributionGenerator` shares the table

`process-tirewear` writes 32 `RatesOpModeDistribution` rows at `avgSpeedBinID`
1–16 that belong to a third generator, already covered by
`docs/process-tirewear.md`. This port partitions the table on `avgSpeedBinID`:
both generators here write bin 0 and only bin 0, and the oracle compares only
bin-0 rows. If a future MOVES version wrote a hotelling row in a non-zero bin
the partition would silently drop it, so the oracle also asserts the row-count
floor, which such a change would break.

### 8.4 What the generators do that this port does not

Neither generator's master-loop bookkeeping is modelled — the `DELETE FROM
OpModeDistribution WHERE isUserInput='N'` that
`StartOperatingModeDistributionGenerator.executeLoop` runs on each zone change,
the index creation, the `ANALYZE TABLE` calls. None of them changes a value.

## 9. Summary for the `.esm` author

* Two generators, one output table, partitioned by `avgSpeedBinID`.
* The only arithmetic is `COUNT(opModeID)/starts`, and it is a **four-decimal
  DECIMAL**, not the IEEE ratio.
* A soak band with **both** bounds NULL matches **nothing**; 52 of 60
  `OperatingMode` rows are that case.
* Step 400 reads `startsOpModeDistribution`, **not** the soak histogram it just
  computed, and stamps the All Starts row with the literal `polProcessID` 602.
* `INSERT IGNORE` is a set union, and it is one only because the colliding rows
  are value-identical.
* A generator's claim has two halves; the second is *which runs produce rows*,
  and for `RatesOMDG` that turns on the **source type**, not only the process.
