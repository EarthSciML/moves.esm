# `expand-day` — computation specification

The port specification for the **two-day** onroad fixture. It is written as a
*delta* against `docs/mixed-onroad.md` rather than as a second copy of it: the
chain, the joins, the reusable shapes and the enums are that document's, and
repeating them here would create two specifications that can disagree. What is
here is what is different, what that difference buys, and the worked examples
and reproduction that can only be written at this snapshot.

**Why it exists is not the 250 rows.** It is the day axis. Read §0.2 first.

---

## 0. The fixture at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/expand-day.xml` |
| Model | ONROAD, `modelscale` `Inv` (inventory), `modeldomain` `DEFAULT` |
| Geography | county 26161 (Washtenaw, Michigan), zone 261610, link 2616104 |
| Time | year 2020, month **8**, hour **7**, day types **2 (weekend) and 5 (weekday)** |
| Vehicles | sourceTypeID 21 (passenger car); fuel types **1, 2, 5, 9** |
| Road | roadTypeID 4 (urban restricted access) |
| Pollutant/process | `runspecpollutantprocess` holds **9101, 9102, 9190**; only 9101 emits (§0.3) |
| Model years | 1980–2020 (41) |
| Output | `db__out_expand_day__movesoutput`, **250 rows** = 125 cohorts × 2 day types |
| Output units | energy in **Million BTU**, `outputtimestep` **Hour** |
| Calculator path | rates-first: `TotalActivityGenerator` → `SourceBinDistributionGenerator` → `BaseRateGenerator` → `BaseRateCalculator` → output aggregation |
| Fixture | `fixtures/expand-day.esm`, 109 inline assertions |
| Result | 250 of 250 rows, key set exact, worst cell **7.106 × 10⁻⁶** |

### 0.1 The RunSpec on disk and the execution database, and where they agree

`docs/mixed-onroad.md` §0.1 states the rule and this fixture does not restate
it: **scope a document from the execution database's `runspec*` tables**, never
from the XML, because `<month key>` and `<beginhour key>` are 0-based indices
into sorted ID lists and not identifiers.

What is worth recording here is the one row where the two now **agree**, and
why that is the whole subject of this document:

| dimension | `expand-day.xml` says | the execution database says |
|---|---|---|
| month | `key="7"` → 8 | **8** (`runspecmonth`) |
| hour | `beginhour key="6"` → 7 | **7** (`runspechour`) |
| day types | `<day id="2"/><day id="5"/>` | **2 and 5** (`runspecday`, 2 rows) — **agrees** |
| fuel types | one selection, fuel 1 | **1, 2, 5, 9** (`runspecsourcefueltype`) — a genuine expansion |
| pollutants | 91, 92, 93 | **91** (`runspecpollutant`, 1 row) |

`<day id="…">` with a literal dayID is what canonical `RunSpecXML.save` writes
(`RunSpecXML.java:2040`), and it is what the correction that produced
`moves-snapshot/v2` put into all 42 RunSpecs. In 28 of them that *narrowed* the
run, because `<day key="5">` had been an out-of-range index that selected
nothing and fell back to every day type. In this one it did not: the intent was
always both days, the XML now says both days, and the execution database has
said both days throughout. **`expand-day` is the snapshot the correction did
not change** — `MOVESOutput` is 250 rows before and after, and the table count
moved 378 → 372 only because the recapture renamed the per-worker temporary
tables.

### 0.2 Why this fixture exists

`docs/esm-conventions.md` §42.5, in full because it is the requirement this
document is answering:

> **Every two-valued day factor in this repository is now exercised at one
> value.** `noOfRealDays` is 5 and never 2; `hourDayID` is 75 and never 72;
> `dayVMTFraction` has four rows and not eight; the drive-cycle weight vector is
> built once and not twice. A port that dropped the divisor entirely, or that
> hardcoded 5, now passes every fixture here.

That is a real hole and it is the direct price of running what the RunSpecs
meant. `expand-day` is the only snapshot in the 42-snapshot corpus that still
carries both day types, so it is the only place the hole can be closed without
a new MOVES capture.

**The fixture is only worth its weight if the assertions can tell the two days
apart**, and §6.6 and §7.3 are where that is established rather than asserted:
three separate collapses of the day axis are recomputed by the §6.5
reproduction and each is required to move at least half the output rows by more
than the fixture's own cell tolerance. They move them by 60 %, 400 % and 714 %.

### 0.3 Three pollutant-processes in scope, one in the output

`runspecpollutantprocess` carries 9101, 9102 **and 9190** — running, start and
extended-idle Total Energy Consumption — and `MOVESOutput` holds processID 1
alone. The mechanism is `docs/mixed-onroad.md` §0.2's, once for each of the two
extra processes: `BaseRateGenerator` emits start-exhaust and extended-idle
rates on the **off-network road type 1**, and `BaseRateCalculator` joins its
rate tables to `runSpecRoadType`, which for this run is `{4}`
(`baseratecalculator/mod.rs:773-781`). Every process-2 and process-90 row is
discarded before the calculator's block list is built.

The extra process is visible in two input tables and in neither answer:
`pollutantprocessmodelyear` is 333 rows here against `mixed-onroad`'s 222, and
`emissionrate` is 69,688 against 69,200. The 488 extra rate rows reach nothing.

So the 250 rows are polProcessID 9101 alone:

```
250 = 125 (modelYearID, fuelTypeID) cohorts  x  2 day types
```

and the 125 is **ragged** — 41 model years for fuel 1, 40 for fuel 2, 23 for
fuel 5 and 21 for fuel 9. `docs/mixed-onroad.md` §2.2 gives the rule that
decides membership; it is unchanged, and so is the count, because a cohort is
not a day.

---

## 1. What differs from `mixed-onroad`, and nothing else does

The two snapshots are the same run at a different hour over a different day
set. Every table in `docs/mixed-onroad.md` §1.2 is read here, with the same
columns, and §1.3's zero-effect list holds with **one deletion** (§2.2 below).
Measured over the 46 `data_sources` entries of the two fixtures, seven tables
differ in row count and no table differs in schema:

| table | `mixed-onroad` | `expand-day` | why |
|---|---|---|---|
| `runspecday` | 1 | **2** | the day set |
| `runspechourday` | 1 | 2 | ″ |
| `hourday` | 24 | **48** | ″ — the execution database trims `hourday` to the selected days |
| `dayofanyweek` | 1 | **2** | ″ |
| `dayvmtfraction` | 4 | **8** | ″ |
| `hourvmtfraction` | 96 | **192** | ″ |
| `pollutantprocessmodelyear` | 222 | 333 | polProcessID 9190 (§0.3) |
| `emissionrate` | 69,200 | 69,688 | ″ |

`avgspeeddistribution` is **3,072 rows in both** and that is not a coincidence
worth passing over: it is keyed by `hourDayID` over all 48 hour-days regardless
of what the run selects, so it is the table that makes the day axis reach `W`
and `averageSpeed` whether or not the run has two days. The one-day fixtures
read the same 3,072 rows and use 16 of them.

---

## 2. The chain, and the two stages the hour moves

The chain is `docs/mixed-onroad.md` §2 — S1 through S18, joins J1 through J35 —
and this document does not restate it. Two stages produce different numbers at
hour 7 than at hour 9, and one of them changes **arm** rather than value.

### 2.1 The A/C activity clamp is further inside its clamp

`setup.rs:409-411`, with `monthgrouphour[8, 7]` = (A −3.63154, B 0.072465,
C −0.000276) and `zonemonthhour[8, 261610, 7].heatIndex` = 59.5:

```
-3.63154 + 59.5 x (0.072465 - 0.000276 x 59.5)
  = -3.63154 + 59.5 x 0.056043
  = -3.63154 + 3.3345585
  = -0.2969815        ->  clamp to 0  ->  ACFactor = 0
```

At hour 9 the same quadratic gives −0.0189. **Both clamp, and this one clamps
harder**, so the colder hour buys nothing on this branch and
`docs/esm-conventions.md` §23 says to write that down rather than let a reader
infer that a different hour exercises more of everything. The non-zero A/C arm
still has no fixture; `components/onroad_energy_output.esm` moves the heat
index and asserts both arms.

`meanBaseRateACAdj` is 57,185 against a base rate of 392,141 for MY1980
gasoline — a 14.6 % addition — so this is a clamp holding back a real number,
and the fixture asserts the **incremental load** directly against
`baserate_1_2020`'s own column rather than through an output the zero erases.

### 2.2 The EV temperature adjustment does **not** clamp, and that is new

`temperatureadjustment`'s only polProcessID 9101 row is `fuelTypeID` 9 at
`regClassID` **0** — a WILDCARD — and this run's passenger car is regulatory
class 20. `adjust.rs:495-520` looks the row up by the exact class first and by
the wildcard second, and `adjust.rs:107-124` then runs the EV branch:

```
adj = (T - 72) x (termA + termB x (T - 72));   if adj < 0 { adj = 0 }
if sourceTypeID < 40 && heatIndex > 67.0 { adj = 0 }
factor = 1 + adj
```

At 59.5 °F:

```
d = 59.5 - 72 = -12.5
adj = -12.5 x (0.00225 + 0.00028 x -12.5) = -12.5 x -0.00125 = +0.015625
```

`adj > 0`, so the clamp does not fire; 59.5 < 67.0, so the suppression does not
fire either; **the factor is 1.015625 and it multiplies all 82 electricity rows
of the output.** At `mixed-onroad`'s 66.9 °F the same lookup gives −0.0041922
and is clamped to 1.

This is the row that `docs/esm-conventions.md` §27.3 records as having been
implemented as an exact-class lookup only, which returned the correct factor of
1 at 66.9 °F **for the wrong reason** and was found at 59.5 °F. So this fixture
is where the wildcard precedence is load-bearing rather than inert, and
`the_temperature_lookup_reaches_the_regClassID_zero_wildcard` pins it from both
sides: the exact lookup finds nothing, the wildcard's two coefficients are the
ones that arrive, and the raw adjustment is the positive number the clamp does
not touch.

Measured with the wildcard step removed, by the §6.5 reproduction: worst cell
goes from 7.106 × 10⁻⁶ to **1.539 × 10⁻²**, on (day 5, MY 2002, fuel 9) — the
same 1/1.015625 that §27.3 measured from the `.esm` side, arrived at
independently.

**`temperatureadjustment` therefore leaves §1.3's zero-effect list at this
fixture.** That is the one structural difference between the two documents'
input inventories, and it is what a scope move is for.

### 2.3 Everything else the hour moves, it moves by value only

`averageSpeed`, `hourVMTFraction`, `sho`, `W` and every base rate differ from
`mixed-onroad`'s because they are keyed by hour or hour-day. None changes shape
and none changes branch. §6 has the numbers.

---

## 3. The day axis, stage by stage

This section has no counterpart in `docs/mixed-onroad.md`, because at one day
type there is nothing to say. Six quantities are keyed by the day, and they
enter at four places:

| # | quantity | day 2 | day 5 | where |
|---|---|---|---|---|
| 1 | `hourDayID` | 72 | 75 | looked up from (`dayID`, `hourID`) in `hourday`; the key `sho`, `avgspeeddistribution` and `runspechourday` are all keyed on |
| 2 | `dayVMTFraction` | 0.237635 | 0.762365 | S7, from `dayvmtfraction[21, 8, 4, d]` |
| 3 | `hourVMTFraction` | 0.0184304 | 0.0459565 | S7, from `hourvmtfraction[21, 4, d, 7]` |
| 4 | `averageSpeed` | 67.0416879 | 56.3611908 | S6, the arithmetic mean of `avgspeeddistribution[·, hourDayID]` |
| 5 | `W[·, opModeID]` | 23 modes | 23 modes | S13(a), weighted by the same `avgSpeedFraction` column |
| 6 | `noOfRealDays` | 2 | 5 | S16's divisor, `dayofanyweek[d]` |

**S6–S9's day axis is exactly three of those and the identity is checkable by
hand.** From the snapshot's own `sho` table at age 0:

```
sho[72, 0] / sho[75, 0] = 27.33 / 260.057 = 0.105092

                        = (0.237635 / 0.762365)      dayVMTFraction
                        x (0.0184304 / 0.0459565)    hourVMTFraction
                        x (56.3611908 / 67.0416879)  1 / averageSpeed
                        = 0.311708 x 0.401039 x 0.840685
                        = 0.105092
```

`monthVMTFraction`, `weeksPerMonth`, `annualVMT` and `SHOAllocFactor` are all
day-free and cancel. The §6.5 reproduction asserts this identity to 10⁻¹².

**S14 adds the fourth, and S16 the fifth.** For MY1980 gasoline:

```
emissionQuant[day 2] / emissionQuant[day 5]
  = 0.452942 / 1.46683 = 0.308788

  = (392141 / 333651)      meanBaseRate, through W
  x (2.43728 / 23.1918)    sho at age 40
  x (5 / 2)                the RECIPROCAL of noOfRealDays
  = 1.175305 x 0.105092 x 2.5
```

The divisor appears **inverted** in that product, which is the trap worth
naming: a bigger `noOfRealDays` makes a *smaller* output row, because S7 has
already multiplied the day type's whole share of the month's VMT in and S16 is
bringing it back to one average day (`docs/mixed-onroad.md` §2.1 S7). A port
that applied `noOfRealDays` in both places over-emits by ~4.3×, which is what
`baseratecalculator/mod.rs:1536-1542` records; a port that applies it in
neither is 2.5× high on the weekend and 1× right on the weekday, which is
exactly why a one-day corpus cannot see it.

---

## 4. Reusable shapes

**None are new.** The fixture imports the same six `lib/` templates
`fixtures/mixed-onroad.esm` does — `pol_process_id`, `pollutant_id_of`,
`process_id_of` and `null_output_column` from `lib/identifiers.esm`;
`weeks_per_month`, `share_of_group`, `onroad_scc`, `source_bin_slot`,
`ev_energy_divisor` and `kilojoules_per_million_btu` from
`lib/onroad_activity.esm`; `mph_to_meters_per_second`,
`vehicle_specific_power`, `in_half_open_range` and `bracket_low_fraction` from
`lib/drive_cycle.esm`; `exact_else_wildcard` from `lib/adjustments.esm`;
`model_year_in_range` from `lib/keys.esm`; and `heat_index` from
`lib/meteorology.esm`.

That is a claim and not an omission: a second day type is a second value on an
axis the templates already carry, so if any of the six had needed a variant the
factorisation would have been wrong. `exact_else_wildcard` is the one that
earns its place here rather than elsewhere (§2.2).

---

## 5. Enums, joins, precision

`docs/mixed-onroad.md` §3 (joins J1–J35), §5 (enums) and §7.5
(precision-sensitive operations) apply verbatim. The document declares no
`element_type`, for §2.2's reason there: the packed `sourceBinID` is 1.01 × 10¹⁸
and is unpacked, never built.

---

## 6. Hand-checkable worked examples

### 6.0 Run-level values used by every example

| | |
|---|---|
| `weeksPerMonth` | 31 / 7 = 4.428571 |
| `monthVMTFraction[21, 8]` | 0.0934297 |
| `analysisYearVMT[25]` | 2 572 988 371 051 |
| `roadTypeVMTFraction[21, 4]` | 0.259544 |
| `SHOAllocFactor[261610, 4]` | 0.001645627794 |
| `heatIndex` | 59.5 °F → A/C factor **0**, EV temperature factor **1.015625** |
| kJ per Million BTU | 1 055 055.9 |

and the six day-keyed values of §3.

### 6.1 Worked example A — MY 1980, gasoline, on both days

The largest single row, and the pair that shows every day factor at once.

```
                                day 2 (weekend)       day 5 (weekday)
meanBaseRate  [baserate_1_2020]        392 141               333 651
sho           [sho, ageID 40]          2.43728               23.1918
noOfRealDays                                 2                     5
activity = sho / noOfRealDays          1.21864               4.63836
kJ = rate x activity                   477 879             1 547 593
MMBTU = kJ / 1 055 055.9              0.452942               1.46683
MOVESOutput                           0.452942               1.46683
```

### 6.2 Worked example B — MY 2020, gasoline, on both days

The largest activity.

```
meanBaseRate                           207 997               176 680
sho           [ageID 0]                  27.33               260.057
activity                                13.665               52.0114
MMBTU                                  2.69396               8.70984
MOVESOutput                            2.69396               8.70984
```

### 6.3 Worked example C — MY 2000, electricity, on both days

The smallest rows in the fixture, and the two adjustments that only electricity
sees: the EV efficiency divisor at its largest (age group 2099, 0.778576504 —
a 22.1 % increase) and the EV temperature factor of §2.2.

```
meanBaseRate                            24.421               19.1615
x EV temperature factor 1.015625       24.8025               19.4609
/ EV energy divisor 0.778576504         31.856               24.9955
sho           [ageID 20]               8.78839               83.6255
activity                               4.39420               16.7251
MMBTU                                1.32678e-4            3.96237e-4
MOVESOutput                          1.32678e-4            3.96237e-4
```

Drop the wildcard step of §2.2 and both numbers fall by 1/1.015625 = 1.54 %,
which is 60 times this fixture's cell tolerance.

### 6.4 Worked example D — MY 2020, electricity, on both days

The other end of the age-group ladder: age group 3, divisor 0.893.

```
MMBTU                                0.0471637              0.140851
MOVESOutput                          0.0471637              0.140851
```

### 6.5 The reproduction script

Extracted and run by `./run-expand-day-oracle.sh`. It reads only the input
tables, computes S1–S18 over both day types, and **asserts** its worst relative
error against `sho` and against `MOVESOutput`.

It differs from `docs/mixed-onroad.md` §6.5's script in three ways and each is
load-bearing here. It runs at hour 7; it implements **S15's temperature
adjustment**, which that script omits and which is invisible at hour 9 (§2.2);
and its last section recomputes the answer under three **collapses of the day
axis** and requires each to move it. The last of those is what makes this
fixture's coverage claim a measurement rather than an assertion.

```python
#!/usr/bin/env python3
"""Independent reproduction of the `expand-day` chain from the snapshot's own
input tables, and from NOTHING else -- the activity half (S1-S9), the cohort
structure and the fuel-usage rebase (S10-S12), the drive-cycle operating-mode
weights and the base rate (S13-S14), S15's adjustments and the output stage
(S16-S18), over BOTH day types.

It is docs/mixed-onroad.md 6.5's reproduction at hour 7 over two days, plus one
stage that document's script does not have: S15's TEMPERATURE ADJUSTMENT. That
omission is invisible at hour 9, where the EV branch's `adj < 0` clamp returns 1
anyway, and is a 1.56% error on every electricity row at 59.5 degF. Finding it
is what a retarget audit is for (docs/esm-conventions.md 27.3), and this script
is the third implementation that says so.

The last section is the point of the fixture: three COLLAPSES of the day axis,
each recomputed here and each required to move the answer. A day dimension that
no test can falsify is a day dimension nobody has checked, and after the
`<day key=>` correction this is the only snapshot in the corpus that can ask.

Purpose: attribution. When a `.esm` disagrees with the snapshot, a third
implementation says whether the document or the specification is wrong."""
import sys
import collections
import glob
import pyarrow.parquet as pq

# "1 day types" is not English and this line is quoted in section 7.
_s = lambda n: "" if n == 1 else "s"

SNAP = sys.argv[1]
# The execution database's name carries a per-run id, so the prefix is
# DISCOVERED and not written down: a recapture renames every table in the
# snapshot and a hardcoded id fails as a missing FILE, which reads like a
# missing table rather than like a stale name.
P = glob.glob(SNAP + "/tables/db__movesexecution*__year.parquet")[0][:-len("year.parquet")]


def T(n):
    return pq.read_table(P + n + ".parquet").to_pylist()


# ---------------------------------------------------------------- run scope
YEAR, MONTH, HOUR, ZONE, ROAD, ST = 2020, 8, 7, 261610, 4, 21
COUNTY, ELECTRICITY = 26161, 9
DAYS = [r["dayID"] for r in T("runspecday")]
assert DAYS == [2, 5], (
    "expand-day is the corpus's only two-day snapshot and this one has %r. "
    "Every claim below about the day axis is vacuous on a one-day run, so the\n"
    "    script refuses rather than reporting a pass it did not earn." % (DAYS,))
HD = {r["dayID"]: r["hourDayID"] for r in T("hourday") if r["hourID"] == HOUR}
POLPROC = 100 * 91 + 1
KJ_PER_MMBTU = 1055.0559e6 / 1000.0

# ------------------------------------------------ S1: base year (section 1.5)
base = max(r["yearID"] for r in T("year")
           if r["yearID"] <= YEAR and str(r["isBaseYear"]).upper() == "Y")
assert base == YEAR, "the population and VMT folds do not collapse for %d" % base
FUELYEAR = {r["yearID"]: r["fuelYearID"] for r in T("year")}[YEAR]

# ------------------------------------------------- S2: sourceTypeAgePopulation
stpop = {r["sourceTypeID"]: float(r["sourceTypePopulation"])
         for r in T("sourcetypeyear") if r["yearID"] == base}
agefrac = {(r["sourceTypeID"], r["ageID"]): float(r["ageFraction"])
           for r in T("sourcetypeagedistribution") if r["yearID"] == base}
pop = {k: stpop[k[0]] * v for k, v in agefrac.items() if k[0] in stpop}

# --------------------------------------------------------- S3: travelFraction
mar = {(r["sourceTypeID"], r["ageID"]): float(r["relativeMAR"])
       for r in T("sourcetypeage")}
hpms = {r["sourceTypeID"]: r["HPMSVtypeID"] for r in T("sourceusetype")}
group_total = collections.defaultdict(float)
for k in pop:
    group_total[hpms[k[0]]] += pop[k] * mar[k]
travelfrac = {k: pop[k] * mar[k] / group_total[hpms[k[0]]] for k in pop}

# -------------------------------------------------------- S4: analysisYearVMT
ayv = {r["HPMSVtypeID"]: float(r["HPMSBaseYearVMT"])
       for r in T("hpmsvtypeyear") if r["yearID"] == base}

# ------------------------------------------------- S5: annualVMTByAgeRoadway
onroad = {r["roadTypeID"] for r in T("roadtype")}
rtd = {r["roadTypeID"]: float(r["roadTypeVMTFraction"])
       for r in T("roadtypedistribution")
       if r["sourceTypeID"] == ST and r["roadTypeID"] in onroad}
ages = sorted({k[1] for k in travelfrac if k[0] == ST})
annual = {a: ayv[hpms[ST]] * rtd[ROAD] * travelfrac[(ST, a)] for a in ages}

# ------------------------------------------------------------ S6: averageSpeed
binspeed = {r["avgSpeedBinID"]: float(r["avgBinSpeed"]) for r in T("avgspeedbin")}
speed = collections.defaultdict(float)
for r in T("avgspeeddistribution"):
    if r["sourceTypeID"] != ST or r["roadTypeID"] != ROAD:
        continue
    for d in DAYS:
        if r["hourDayID"] == HD[d]:
            speed[d] += float(r["avgSpeedFraction"]) * binspeed[r["avgSpeedBinID"]]

# ------------------------------------------------- S7: vmtByAgeRoadwayHour
weeks = {r["monthID"]: r["noOfDays"] / 7.0 for r in T("monthofanyyear")}[MONTH]
mvf = {r["monthID"]: float(r["monthVMTFraction"])
       for r in T("monthvmtfraction") if r["sourceTypeID"] == ST}[MONTH]
dvf = {r["dayID"]: float(r["dayVMTFraction"]) for r in T("dayvmtfraction")
       if r["sourceTypeID"] == ST and r["monthID"] == MONTH and r["roadTypeID"] == ROAD}
hvf = {r["dayID"]: float(r["hourVMTFraction"]) for r in T("hourvmtfraction")
       if r["sourceTypeID"] == ST and r["roadTypeID"] == ROAD and r["hourID"] == HOUR}

# ------------------------------------------------------------- S8, S9: sho
alloc = {r["roadTypeID"]: float(r["SHOAllocFactor"])
         for r in T("zoneroadtype") if r["zoneID"] == ZONE}[ROAD]
selected_hd = {r["hourDayID"] for r in T("runspechourday")}
sho = {}
for d in DAYS:
    assert HD[d] in selected_hd
    for a in ages:
        vmt = annual[a] * mvf * dvf[d] * hvf[d] / weeks
        sho[(HD[d], a)] = (vmt / speed[d] if speed[d] else 0.0) * alloc

# ----------------------------------- S10, S11, S12: the cohorts and their bins
maxage = max(r["ageID"] for r in T("agecategory"))
my_lo, my_hi = YEAR - maxage, YEAR
fuels = {r["fuelTypeID"] for r in T("runspecsourcefueltype")
         if r["sourceTypeID"] == ST}
mygroup = {(r["polProcessID"], r["modelYearID"]): r["modelYearGroupID"]
           for r in T("pollutantprocessmodelyear")}
shortgroup = {r["modelYearGroupID"]: r["shortModYrGroupID"]
              for r in T("modelyeargroup")}
cohort = {}
for r in T("samplevehiclepopulation"):
    frac = float(r["stmyFraction"])
    if (r["sourceTypeID"] != ST or not my_lo <= r["modelYearID"] <= my_hi
            or r["fuelTypeID"] not in fuels or frac <= 0.0):
        continue                      # `stmyFraction > 0` -- section 2.2
    g = mygroup.get((POLPROC, r["modelYearID"]))
    if g is None or g not in shortgroup:
        continue                      # two inner joins
    key = (r["modelYearID"], r["fuelTypeID"], r["engTechID"], r["regClassID"])
    cohort[key] = cohort.get(key, 0.0) + frac

# ------------------------------- S13(a): the drive-cycle operating-mode weights
# `W[hourDayID, opModeID]`, the one relation no captured table carries: MOVES 5
# computes it inside the worker and drops it (section 8.1). Ported from
# crates/moves-calculators/src/generators/baserategenerator/drivecycle.rs.
seconds = collections.defaultdict(dict)
for r in T("driveschedulesecond"):
    seconds[r["driveScheduleID"]][r["second"]] = float(r["speed"])
physics = [r for r in T("sourceusetypephysicsmapping")
           if r["realSourceTypeID"] == ST and float(r["sourceMass"]) > 0.0
           and float(r["fixedMassFactor"]) > 0.0]
assert len(physics) == 1, "the physics mapping is not a single row for source type %d" % ST
PH = physics[0]
opmode = {r["opModeID"]: r for r in T("operatingmode")}
BRAKE1 = float(opmode[0]["brakeRate1Sec"])
BRAKE3 = float(opmode[0]["brakeRate3Sec"])
# readOperatingMode (inputs.rs:408-419). Dropping 26 and 36 leaves 21 modes that
# are disjoint AND exhaustive over speed >= 1, which is why the classification
# below can be a single match rather than an ordered first-match.
binned = sorted((m for m in opmode if 1 < m < 100 and m not in (26, 36)))
MS = 0.44704


def bound(mode, column):
    v = opmode[mode][column]
    return None if v is None else float(v)


def drive_cycle_distribution(sid):
    """calculateDriveCycleOpModeDistribution at national scale (is_project False)."""
    sp = seconds[sid]
    lo, hi = min(sp), max(sp)
    mode, acc = {}, {}
    for s, v in sp.items():
        if v < 1.0:                       # 0 mph and 0 < v < 1 mph are both Idling
            mode[s] = 1
    for s in range(lo + 1, hi + 1):
        if s in sp and s - 1 in sp:
            acc[s] = sp[s] - sp[s - 1]
    if lo + 1 in acc:
        acc[lo] = acc[lo + 1]             # the first second copies the second's
    total = collections.Counter()
    for s in range(lo, hi + 1):
        if s not in sp:
            continue
        m = mode.get(s)
        if m is None:
            a = acc.get(s, 0.0)
            three = (s - 1 in sp and s - 2 in sp and a < BRAKE3
                     and acc.get(s - 1, 0.0) < BRAKE3 and acc.get(s - 2, 0.0) < BRAKE3)
            if a <= BRAKE1 or three:
                m = 0
            else:
                v = sp[s] * MS
                a_ms = (v - sp[s - 1] * MS) if s - 1 in sp else (
                    (sp[s + 1] * MS - v) if s == lo and s + 1 in sp else 0.0)
                vsp = (float(PH["rollingTermA"]) * v
                       + float(PH["rotatingTermB"]) * v * v
                       + float(PH["dragTermC"]) * v * (v * v)
                       + float(PH["sourceMass"]) * v * a_ms) / float(PH["fixedMassFactor"])
                for k in binned:
                    lov, hiv = bound(k, "VSPLower"), bound(k, "VSPUpper")
                    los, his = bound(k, "speedLower"), bound(k, "speedUpper")
                    if lov is not None and vsp < lov: continue
                    if hiv is not None and vsp >= hiv: continue
                    if los is not None and sp[s] < los: continue
                    if his is not None and sp[s] >= his: continue
                    m = k
                    break
        if m is not None and s > 0:        # the `second > 0` guard, drivecycle.rs:327
            total[m] += 1
    n = sum(total.values())
    return {k: v / n for k, v in total.items()}


cycles = sorted(r["driveScheduleID"] for r in T("drivescheduleassoc")
                if r["sourceTypeID"] == ST and r["roadTypeID"] == ROAD)
cycle_speed = {r["driveScheduleID"]: float(r["averageSpeed"]) for r in T("driveschedule")}
assert len({cycle_speed[c] for c in cycles}) == len(cycles), "two cycles share a speed"
cycle_dist = {c: drive_cycle_distribution(c) for c in cycles}

bin_modes = {}                             # findDriveCycles, drivecycle.rs:110-176
for b, bs in binspeed.items():
    low = max((cycle_speed[c] for c in cycles if cycle_speed[c] <= bs), default=None)
    high = min((cycle_speed[c] for c in cycles if cycle_speed[c] >= bs), default=None)
    span = (high if high is not None else 100000.0) - (low if low is not None else -100.0)
    if span <= 0.0:      lf = 1.0
    elif low is None:    lf = 0.0
    elif high is None:   lf = 1.0
    else:                lf = (high - bs) / span
    d = collections.defaultdict(float)
    for c, f in ((low, lf), (high, 1.0 - lf)):
        if c is None or f == 0.0:
            continue
        sid = next(s for s in cycles if cycle_speed[s] == c)
        for m, v in cycle_dist[sid].items():
            d[m] += f * v
    bin_modes[b] = d

W = collections.defaultdict(float)
for r in T("avgspeeddistribution"):
    if r["sourceTypeID"] != ST or r["roadTypeID"] != ROAD:
        continue
    for m, v in bin_modes[r["avgSpeedBinID"]].items():
        W[(r["hourDayID"], m)] += v * float(r["avgSpeedFraction"])
for d in DAYS:
    t = sum(v for (h, _), v in W.items() if h == HD[d])
    assert abs(t - 1.0) < 1e-5, "W does not sum to 1 for hourDayID %d: %.9f" % (HD[d], t)

# ---------------------- S12(b): the fuel-usage rebase, source_bin_..._generator.rs:1534
# NOT the identity: `fuelusagefraction` sends 98.2134% of an E85 bin's activity
# to the gasoline supply, and the base rate is weighted by the rebased
# distribution (sbweighted.rs:148-165). Omitting it is a 55x error on E85.
usage = [r for r in T("fuelusagefraction")
         if r["countyID"] == COUNTY and r["fuelYearID"] == FUELYEAR]
sbaf = collections.defaultdict(float)
for (my, fuel, engtech, regclass), frac in cohort.items():
    for u in usage:
        if u["sourceBinFuelTypeID"] != fuel:
            continue
        if u["modelYearGroupID"] != 0 and u["modelYearGroupID"] != my:
            continue
        used = (my, u["fuelSupplyFuelTypeID"], engtech, regclass)
        if used not in cohort:            # the used bin must exist, :1551-1557
            continue
        sbaf[used] += float(u["usageFraction"]) * frac

# ------------------------------------------ S13(b): the source-bin-weighted rate
def slot(bin_id, scale):                  # section 4.4; never pack, only unpack
    return (bin_id // scale) % 100


rate = {}
for r in T("emissionrate"):
    if r["polProcessID"] != POLPROC:
        continue
    b = r["sourceBinID"]
    rate[(slot(b, 10**16), slot(b, 10**14), slot(b, 10**12), slot(b, 10**10),
          r["opModeID"])] = float(r["meanBaseRate"])

fleetgroup = {r["regClassID"]: r["fleetAvgGroupID"] for r in T("regulatoryclass")}
evfrac = {(r["modelYearID"], r["fleetAvgGroupID"]): float(r["evFraction"])
          for r in T("evsalesfraction")}
fleetadj = [r for r in T("fleetavgadjustment") if r["polProcessID"] == POLPROC]


def ev_sales_factor(my, fuel, regclass):
    """sbweighted.rs:369-405 -- back-scale the ICE fleet for EV sales."""
    if fuel == ELECTRICITY:
        return 1.0
    g = fleetgroup[regclass]
    e = evfrac.get((my, g))
    row = next((r for r in fleetadj if r["fleetAvgGroupID"] == g
                and r["beginModelYearID"] <= my <= r["endModelYearID"]), None)
    if e is None or row is None:
        return 1.0
    m = float(row["evMultiplier"])
    den = (1.0 - e) + e * m
    v = 1.0 / (1.0 - e * m / den)
    cap = row["adjustmentCap"]
    return min(v, float(cap)) if cap is not None and float(cap) > 0.0 else v


# ------------------------------------------------- S14: the collapsed base rate
sbweighted = collections.defaultdict(float)
for (my, fuel, engtech, regclass), frac in sbaf.items():
    smy = shortgroup[mygroup[(POLPROC, my)]]
    ev = ev_sales_factor(my, fuel, regclass)
    for om in {k[4] for k in rate}:
        r = rate.get((fuel, engtech, regclass, smy, om))
        if r is not None:
            sbweighted[(my, fuel, om)] += frac * r * ev
base_rate = collections.defaultdict(float)
for (my, fuel, om), v in sbweighted.items():
    for d in DAYS:
        base_rate[(HD[d], my, fuel)] += v * W[(HD[d], om)]

# ---------------- S15(d), S15(e): the two temperature-driven adjustments
#
# NEITHER IS IN docs/mixed-onroad.md 6.5's script, because at 66.9 degF both
# return an exact identity and a script that omits them is right by accident.
# At 59.5 degF only one of them still does.
zmh = next(r for r in T("zonemonthhour")
           if r["zoneID"] == ZONE and r["monthID"] == MONTH and r["hourID"] == HOUR)
HEATINDEX = float(zmh["heatIndex"])

# (d) The A/C activity quadratic, setup.rs:409-411, clamped to [0, 1]. Computed
# and asserted rather than assumed: `meanBaseRateACAdj` is 14.6% of the MY1980
# gasoline rate, so "the A/C term is inert here" is a claim about a large number.
mgh = next(r for r in T("monthgrouphour")
           if r["hourID"] == HOUR and r["monthGroupID"] == MONTH)
ac_raw = (float(mgh["ACActivityTermA"])
          + HEATINDEX * (float(mgh["ACActivityTermB"])
                         + float(mgh["ACActivityTermC"]) * HEATINDEX))
AC_FACTOR = min(max(ac_raw, 0.0), 1.0)
assert AC_FACTOR == 0.0, "the A/C activity term is %+.7f and no longer clamps" % ac_raw

# (e) The temperature adjustment, adjust.rs:495-535, with the regClassID
# PRECEDENCE of :495-520: the exact regulatory class first, the regClassID 0
# WILDCARD second. The table's one 9101 row is the wildcard, so a lookup that
# stops at the exact class finds nothing, defaults its terms to zero, and
# returns 1 -- which is the right answer at 66.9 degF and 1.56% low here.
tadj = [r for r in T("temperatureadjustment") if r["polProcessID"] == POLPROC]


def temp_terms(fuel, regclass, my):
    for want in (regclass, 0):                 # exact, then wildcard
        for r in tadj:
            if (r["fuelTypeID"] == fuel and r["regClassID"] == want
                    and r["minModelYearID"] <= my <= r["maxModelYearID"]):
                return float(r["tempAdjustTermA"]), float(r["tempAdjustTermB"])
    return 0.0, 0.0


def temperature_factor(fuel, regclass, my):
    """adjust.rs:107-124 for electricity, the standard quadratic otherwise."""
    a, b = temp_terms(fuel, regclass, my)
    if fuel == ELECTRICITY:
        if ST < 40 and HEATINDEX > 67.0:       # the suppression, :119-121
            return 1.0
        d = HEATINDEX - 72.0
        return 1.0 + max(d * (a + b * d), 0.0)
    d = HEATINDEX - 75.0
    return 1.0 + d * (a + b * d)


EV_TEMP = temperature_factor(ELECTRICITY, 20, 2000)
print("temperature:   heat index %.1f degF, A/C term %+.7f -> factor %.0f, "
      "EV factor %.6f" % (HEATINDEX, ac_raw, AC_FACTOR, EV_TEMP))
assert abs(EV_TEMP - 1.015625) < 1e-12, EV_TEMP
assert temperature_factor(1, 20, 2000) == 1.0

# ------------------------------ S15(f): the EV energy-efficiency divisor
agegroup = {r["ageID"]: r["ageGroupID"] for r in T("agecategory")}
eveff = {r["ageGroupID"]: float(r["batteryEfficiency"]) * float(r["chargingEfficiency"])
         for r in T("evefficiency")
         if r["polProcessID"] == POLPROC and r["sourceTypeID"] == ST}

# ------------------------------------------------------- S16, S17, S18
realdays = {r["dayID"]: float(r["noOfRealDays"]) for r in T("dayofanyweek")}


def onroad_scc(fuel, source, road, process):
    return "%d" % (22 * 10**8 + fuel * 10**6 + source * 10**4 + road * 10**2 + process)


def emit(realdays_of, sho_of, base_rate_of):
    """S15-S18 for one set of day-keyed inputs, so a COLLAPSE can reuse it."""
    out = {}
    for (my, fuel, engtech, regclass), frac in cohort.items():
        for d in DAYS:
            rate = base_rate_of(d, my, fuel)
            rate = (rate + AC_FACTOR * 0.0) * temperature_factor(fuel, regclass, my)
            if fuel == ELECTRICITY:
                rate /= eveff[agegroup[YEAR - my]]
            activity = sho_of(d, YEAR - my) / realdays_of(d)
            out[(d, my, fuel)] = (rate * activity / KJ_PER_MMBTU,
                                  onroad_scc(fuel, ST, ROAD, POLPROC % 100))
    return out


rows = emit(lambda d: realdays[d],
            lambda d, a: sho[(HD[d], a)],
            lambda d, my, f: base_rate[(HD[d], my, f)])

# ------------------------------------------------------------------- compare
ref_sho = {(r["hourDayID"], r["ageID"]): float(r["SHO"]) for r in T("sho")}
worst_sho = max(abs(sho[k] - v) / v for k, v in ref_sho.items())
print("sho:           %3d rows, worst relative error %.3e" % (len(ref_sho), worst_sho))
# ASSERTED, not merely printed. ./run-tests.sh reads this script's EXIT CODE, so
# a regression that leaves the key set intact and moves every value would
# otherwise be reported green with the evidence sitting in the log. Measured:
# injecting a 2% error here used to leave the whole suite green.
assert worst_sho < 1e-5, "sho: worst relative error %.3e exceeds 1e-5" % worst_sho

out = pq.read_table(SNAP + "/tables/db__out_expand_day__movesoutput.parquet").to_pylist()
worst, worst_key = 0.0, None
for o in out:
    q, scc = rows[(o["dayID"], o["modelYearID"], o["fuelTypeID"])]
    assert scc == o["SCC"], (scc, o["SCC"])
    rel = abs(q - float(o["emissionQuant"])) / float(o["emissionQuant"])
    if rel > worst:
        worst, worst_key = rel, (o["dayID"], o["modelYearID"], o["fuelTypeID"])
print("emissionQuant: %3d rows, worst relative error %.3e at (day %d, MY %d, fuel %d)"
      % (len(out), worst, *worst_key))
assert len(rows) == len(out), (len(rows), len(out))
assert set(rows) == {(o["dayID"], o["modelYearID"], o["fuelTypeID"]) for o in out}
assert worst < 2e-5, "emissionQuant: worst relative error %.3e exceeds 2e-5" % worst
print("key set:       %3d cohorts x %d day type%s = %d rows, exact"
      % (len(cohort), len(DAYS), _s(len(DAYS)), len(rows)))

# ------------------------------------------------- the day axis, and what it costs
#
# docs/esm-conventions.md 42.5. This is the only snapshot in the corpus that
# carries both day types, so it is the only place these numbers can be measured
# at all -- and measuring them is the whole reason the fixture exists.
print("day axis:      dayVMTFraction %s, hourVMTFraction %s, averageSpeed %s, "
      "noOfRealDays %s"
      % ("/".join("%.6g" % dvf[d] for d in DAYS),
         "/".join("%.6g" % hvf[d] for d in DAYS),
         "/".join("%.6g" % speed[d] for d in DAYS),
         "/".join("%.0f" % realdays[d] for d in DAYS)))
for d in DAYS:
    assert len({dvf[d], hvf[d], speed[d], realdays[d]}) == 4
assert dvf[2] != dvf[5] and hvf[2] != hvf[5] and speed[2] != speed[5]
assert realdays[2] == 2.0 and realdays[5] == 5.0
assert abs(sum(dvf.values()) - 1.0) < 1e-9, sum(dvf.values())

# S6-S9's day axis is exactly three factors and this identity says so.
lhs = sho[(HD[2], 0)] / sho[(HD[5], 0)]
rhs = (dvf[2] / dvf[5]) * (hvf[2] / hvf[5]) * (speed[5] / speed[2])
print("               sho ratio %.6f = dayVMT x hourVMT x 1/speed = %.6f"
      % (lhs, rhs))
assert abs(lhs - rhs) < 1e-12, (lhs, rhs)

# THE THREE COLLAPSES. Each is a port that would pass every other fixture in
# this repository, and each is required to move a number here. A collapse that
# changed nothing would mean this fixture buys no coverage and should say so.
COLLAPSES = [
    ("noOfRealDays pinned at 5",
     lambda: emit(lambda d: 5.0,
                  lambda d, a: sho[(HD[d], a)],
                  lambda d, my, f: base_rate[(HD[d], my, f)])),
    ("the divisor dropped altogether",
     lambda: emit(lambda d: 1.0,
                  lambda d, a: sho[(HD[d], a)],
                  lambda d, my, f: base_rate[(HD[d], my, f)])),
    ("one shared W and one shared sho, both the weekday's",
     lambda: emit(lambda d: realdays[d],
                  lambda d, a: sho[(HD[5], a)],
                  lambda d, my, f: base_rate[(HD[5], my, f)])),
]
for name, build in COLLAPSES:
    bad = build()
    hit = [(k, abs(v[0] - rows[k][0]) / rows[k][0]) for k, v in bad.items()
           if v[0] != rows[k][0]]
    worst_bad = max(r for _, r in hit)
    print("collapse:      %-46s %3d of %d rows move, worst %.4g"
          % (name, len(hit), len(rows), worst_bad))
    assert len(hit) >= len(rows) // 2, (
        "%s moves only %d of %d rows -- the day axis is not being exercised"
        % (name, len(hit), len(rows)))
    assert worst_bad > 1e-2, (
        "%s moves the answer by only %.3e, which is inside this fixture's own "
        "2e-5 cell gate: the collapse is not detectable and the coverage claim "
        "is false" % (name, worst_bad))
```

Result:

```
temperature:   heat index 59.5 degF, A/C term -0.2969815 -> factor 0, EV factor 1.015625
sho:            82 rows, worst relative error 3.610e-06
emissionQuant: 250 rows, worst relative error 7.106e-06 at (day 5, MY 2002, fuel 9)
key set:       125 cohorts x 2 day types = 250 rows, exact
day axis:      dayVMTFraction 0.237635/0.762365, hourVMTFraction 0.0184304/0.0459565, averageSpeed 67.0417/56.3612, noOfRealDays 2/5
               sho ratio 0.105092 = dayVMT x hourVMT x 1/speed = 0.105092
collapse:      noOfRealDays pinned at 5                       125 of 250 rows move, worst 0.6
collapse:      the divisor dropped altogether                 250 of 250 rows move, worst 4
collapse:      one shared W and one shared sho, both the weekday's 125 of 250 rows move, worst 7.136
```

### 6.6 The inline `.esm` tests, and which claim each one is

`fixtures/expand-day.esm` carries **109** assertions in nine tests. Seven of
the nine are `fixtures/mixed-onroad.esm`'s, re-addressed by key and re-valued
from this snapshot's own reference tables (§7.2). Two are this fixture's own.

| test | assertions | what it is for |
|---|---|---|
| `the_run_scope_comes_from_the_execution_database` | 16 | the scope, and hour 7 rather than 9 |
| `the_drive_cycle_scaffolding_is_a_single_physics_row_and_two_data_thresholds` | 7 | day-free; identical to `mixed-onroad`'s |
| `the_cohort_row_rule_admits_exactly_the_snapshots_cohorts` | 2 | 125 cohorts, unchanged by the second day |
| `the_drive_cycle_weights_are_a_distribution_over_the_twenty_three_running_modes` | 4 | **W at both day types** |
| `the_activity_chain_reproduces_the_worked_examples` | 10 | S3, S6, S9 — averageSpeed and `sho` **at both day types** |
| `the_four_worked_examples_reach_MOVESOutput` | 19 | four cohorts **× two days**, plus the SCCs |
| `the_collapsed_base_rate_reproduces_the_references_own_intermediate` | 16 | `baserate_1_2020` **at both hourDayIDs** |
| `the_temperature_lookup_reaches_the_regClassID_zero_wildcard` | 11 | §2.2's live arm, and both temperature clamps |
| `the_day_axis_is_exercised_at_both_of_its_values` | 24 | §3, end to end |

**Which assertions a day-collapsed port fails.** This is the list §0.2 promises,
and it is what the fixture is for:

| a port that … | fails |
|---|---|
| hardcodes `noOfRealDays = 5` | the 4 day-2 cells of `the_four_worked_examples_reach_MOVESOutput`, at 2.5×, and the 2 day-2 cells of `outNoOfRealDays` in `the_day_axis_…`. 125 of 250 output rows; the comparator's per-cell gate at 0.6 |
| drops the divisor entirely | all 8 output cells of the worked examples and all 4 `outNoOfRealDays` cells; 250 of 250 rows |
| builds one `W` and indexes it twice | all 8 `cohDay_meanBaseRate` cells and all 8 `cohDay_meanBaseRateACAdj` cells of `the_collapsed_base_rate_…`; **not** `dc_WTotal` or `dc_WModeCount`, which is why those two are not the test |
| reads `dayvmtfraction`/`hourvmtfraction` by first match rather than by day | the 4 share assertions of `the_day_axis_…`, and `act_sho` on 3 of its 6 cells |
| resolves `hourday` without the day | `day_hourDayID[1]`, `act_hourDayID[1]`, `outHourDayID` at 2 of its 4 ordinals, and every value downstream |
| interleaves the two output blocks instead of blocking them | the interior ordinals of `out_dayID`, `outHourDayID` and `outNoOfRealDays` — which is why each is asserted at **both ends** of each block and not only at the first row |

**Which it does not.** `travelFraction`, the cohort grid, the drive-cycle
scaffolding, the SCC arithmetic and both temperature lookups are day-free, and
their 40 assertions are unchanged from the one-day fixture. A day-collapsed
port passes every one of them, which is the point of listing them separately:
this fixture's day coverage is 69 of its 109 assertions, not all of them.

---

## 7. Fidelity

### 7.1 Everything agrees to 7.1 × 10⁻⁶, and that number is the reference's

| route | rows | worst relative error |
|---|---|---|
| `fixtures/expand-day.esm` vs `MOVESOutput` | 250 | **7.106 × 10⁻⁶** |
| §6.5 reproduction vs `MOVESOutput` | 250 | **7.106 × 10⁻⁶** |
| §6.5 reproduction vs `sho` | 82 | 3.610 × 10⁻⁶ |
| worst per-pollutant `emissionQuant` sum | 1 | 2.326 × 10⁻⁷ |

The two routes are independent — one is a `.esm` evaluated by EarthSciAST, the
other is NumPy-free Python over pyarrow — and they agree on the worst cell to
four figures, at (day 5, MY 2002, fuel 9). `docs/mixed-onroad.md` §7.1's
argument applies unchanged: the residual is the reference's own
six-significant-figure column storage, not accumulated error. No tolerance in
`tolerance.toml` was added or widened for this fixture, and the 2 × 10⁻⁵ cell
gate carries 2.8× headroom over the worst cell.

### 7.2 The re-addressing, and how each value was obtained

`docs/esm-conventions.md` §42.4 divides a moved assertion into an address
change, a claim change and a deletion. This fixture is the inverse operation —
a one-day document gaining a day — and the same three apply:

* **Address changes.** `output_rows` is (day, cohort) with the day
  **outermost**, so `mixed-onroad`'s ordinal *o* is this document's *o + 125*.
  That layout was **measured** and not derived: `out_dayID` was emitted down
  the 250 ordinals and read off. §42.3 records that five of twelve fixtures
  interleave instead, and that a wrong assumption would have re-pointed the
  assertions at real rows with plausible values.
* **Claim changes.** Every value was re-read at its key from the snapshot's own
  tables — `averagespeed`, `sho`, `baserate_1_2020`, `MOVESOutput` — and never
  rescaled from `mixed-onroad`'s number and never rounded off this port's own
  answer. The one exception is `act_travelFraction`, which is day- and
  hour-free: its two assertions keep both their ordinals and their values, and
  that is the control on the re-addressing.
* **Restorations.** Three of the claims `docs/esm-conventions.md` §42.4 records
  as *deleted* by the correction are restored here at their own hour: the
  weekend drive-cycle weight total, the weekend arithmetic mean speed
  (67.0416879, which that section names), and the weekend `noOfRealDays` of 2.

### 7.3 The coverage claim, measured

A fixture that ingests both day types and never distinguishes them would be
decoration. Three collapses, each recomputed by §6.5 against the same 250-row
key set:

| collapse | rows moved | worst relative move |
|---|---|---|
| `noOfRealDays` pinned at 5 | 125 of 250 | 0.600 |
| the divisor dropped | 250 of 250 | 4.00 |
| one shared `W` and one shared `sho`, both the weekday's | 125 of 250 | 7.14 |

Every one is four to five orders of magnitude outside the 2 × 10⁻⁵ cell gate,
so each is caught by the comparator as well as by the inline assertions. The
script **asserts** all three rather than printing them, for
`docs/esm-conventions.md` §21's reason: a coverage claim that is only printed
is a coverage claim nobody is checking.

**The same collapses were applied to the `.esm` itself**, which is the half the
oracle cannot speak for, and to `fixtures/mixed-onroad.esm` beside it — the
same two edits, the same equations, the sibling snapshot:

| perturbation of the document | `expand-day` | `mixed-onroad` |
|---|---|---|
| `outNoOfRealDays` rewritten to the constant 5.0 | **6 of 109 red** | 0 of 59 red |
| the `act_dayID` key pair deleted from `act_dayVMTFraction` and `act_hourVMTFraction`'s `join.on` | **18 of 109 red** | 0 of 59 red |

The six are the four day-2 `emissionQuant` cells — each at exactly 0.4× its
reference value, 0.18117640 against 0.452942 and so on — and the two day-2
`outNoOfRealDays` cells. The eighteen add all six `act_sho` cells and the
day-5 output as well, because deleting the key pair makes the aggregate sum
both days' shares instead of selecting one.

**`mixed-onroad` does not merely pass those perturbations' assertions; it
passes the comparator.** The day-collapsed document emits 125 of 125 rows,
key set exact, worst cell 8.319 × 10⁻⁶ — the same worst cell, at the same key,
as the unperturbed one. So the statement in §0.2 is literal and now measured
from the document side as well: before this fixture, a port that hardcoded
`noOfRealDays = 5` passed every test in this repository.

---

## 8. What this fixture cannot check

`docs/esm-conventions.md` §23: say where the fixture is blind, or a reader will
assume it is not.

* **The non-zero arm of the A/C factor.** −0.2969815 at 59.5 °F is *further*
  inside the clamp than `mixed-onroad`'s −0.0189 at 66.9 °F, so a colder hour
  bought nothing here. `components/onroad_energy_output.esm` moves the heat
  index and asserts both arms; no fixture does.
* **The EV heat-index suppression at 67.0 °F.** It does not fire at either
  hour. `mixed-onroad` at 66.9 °F is 0.0999985 °F below it, which is the
  tightest approach in the corpus, and this fixture is 7.5 °F below it.
* **A third day type.** `DayOfAnyWeek` has exactly two rows, so "the day axis
  works for n values" is checked at n = 2 and no further. That is the whole
  domain, but the distinction between "indexed correctly" and "handles two
  cases" is not one this corpus can draw.
* **A second hour, and therefore `hourDayID` as a *composite*.** The run
  selects one hour, so `hourDayID` varies only with the day here. A document
  that resolved `hourday` on `dayID` alone would pass; `docs/mixed-onroad.md`'s
  and this document's hour differ, so the pair of fixtures covers the hour, but
  neither covers it *within* a run.
* **Anything `docs/mixed-onroad.md` §8.4 lists.** Start exhaust, extended idle,
  the I/M path, `generalfuelratio` and `criteriaratio` are all in scope and all
  emit nothing, for §0.3's reason.

---

## 9. Summary for the `.esm` author

1. Retarget, do not rewrite. `fixtures/expand-day.esm` is
   `fixtures/mixed-onroad.esm` with 46 `url_template`s, a source prefix and a
   model name changed. **Not one equation was edited** and it emitted the
   correct 250-row key set on the first run, because every day axis is sized by
   `n_runspecday` out of the source's own extent. That is
   `docs/esm-conventions.md` §42.1's measurement in the other direction, and it
   is the strongest evidence available that the day axis was factored rather
   than written down.
2. **Re-address by key and re-value from the reference.** All 109 assertions
   moved; none of the values came from this port's own output.
3. **Spend the second day where it can be falsified.** Both values of a factor
   asserted side by side is the claim; a structural test that passes on a
   shared vector (`dc_WTotal`, `dc_WModeCount`) is not.
4. **An ingested column cannot be asserted** (finding F43), so pin a day factor
   where it is *used* — `outNoOfRealDays` — and not where it is read.
5. Say which of your assertions a day-collapsed port would still pass. Here it
   is 40 of 109.
