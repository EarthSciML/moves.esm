# `MeteorologyGenerator` — computation specification

The port specification for Phase 5's ninth rung, written to the method of
`docs/process-brakewear.md` and `docs/process-tirewear.md`: the input inventory
determined from evidence, the chain with source lines into `../moves.rs`, every
join with its exact key pairs, and worked examples whose numbers can be checked
by hand.

It is different from its nine predecessors in one structural way, and the
difference is the reason the rung exists.

**Every other specification in `docs/` reproduces `MOVESOutput`. This one
reproduces three columns of an INPUT table.** `MeteorologyGenerator` writes
`ZoneMonthHour.heatIndex`, `ZoneMonthHour.specificHumidity` and
`ZoneMonthHour.molWaterFraction` back into the execution database, before any
calculator runs. Nine fixtures in this repository read at least one of those
three columns off disk — `process-pm-exhaust`, `process-tirewear`,
`process-brakewear`, `process-crankcase-running`, `process-refueling`,
`process-airtoxics`, `process-nox-speciation`, `mixed-onroad` and
`nr-logging-county` — and until this document **nothing in the port had ever
produced one of them.** Three of the nine feed them straight into a NOx
correction (`lib/adjustments.esm`'s `nox_humidity_cfr86` and
`nox_humidity_cfr1065`) and the rest into air-conditioning branches gated on the
heat index.

So the thing being verified here is not a new emission. It is a set of numbers
the existing corpus has been resting on.

---

## 0. The generator at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/process-pm-exhaust.xml` |
| Model | ONROAD, `modelscale` `Inv` (inventory), `modeldomain` `DEFAULT` |
| Geography | county 26161 (Washtenaw, Michigan), zone 261610 |
| Time | year 2020, month **8**, all **24** hours — the generator ignores the RunSpec's hour selection and fills the whole day |
| Reads | `ZoneMonthHour` (temperature, relative humidity), `Zone`, `County` |
| Writes | `ZoneMonthHour.heatIndex`, `ZoneMonthHour.specificHumidity`, `ZoneMonthHour.molWaterFraction`, and two `County` columns it may back-fill |
| Output | **no `MOVESOutput` rows at all** — this is a generator, and its product is an execution-database column |
| Calculator path | **`MeteorologyGenerator`** — a generator with nothing downstream of it inside this slice |
| Rows | 24 in `process-pm-exhaust`; **532 across the whole snapshot corpus** (§7.1) |
| Ported by | `lib/meteorology.esm` (the arithmetic) and `components/meteorology.esm` (the relation and the assertions) |
| Java | `gov/epa/otaq/moves/master/implementation/general/MeteorologyGenerator.java`, method `doHeatIndex` |
| Rust | `../moves.rs/crates/moves-calculators/src/generators/meteorology.rs` |

### 0.1 Which runs it fires on, and how that was established

`MeteorologyGenerator.subscribeToMe` subscribes at `PROCESS` granularity to six
processes: Running Exhaust (1), Extended Idle Exhaust (90), Start Exhaust (2),
Auxiliary Power Exhaust (91), Tirewear (10) and Brakewear (9)
(`meteorology.rs`, `SUBSCRIBED_PROCESS_IDS`, and `calculator-dag.json`'s six
`subscriptions` entries for the module). A run that selects none of them never
schedules the generator, and the three columns stay unwritten.

That is a claim about MOVES's master loop, so it is checked against the corpus
rather than read off the Java. Of the snapshots that carry a `ZoneMonthHour`
with the three columns — **40** as this is written, and the corpus GROWS as new
rungs capture new RunSpecs, which is why §6.5 asserts a floor rather than an
equality (§7.1):

| | snapshots | `ZoneMonthHour` rows |
|---|---|---|
| populated | **21** | 532 |
| left unwritten | **19** | 6,562,248 |

and the predicate

> populated ⇔ the RunSpec is ONROAD **and** its `runspecpollutantprocess` rows
> carry at least one process in {1, 2, 9, 10, 90, 91}

decides all 40 correctly. The 19 unwritten ones are the twelve NONROAD sectors,
the three evaporative slices (processes 11, 12, 13), and
`process-crankcase-start` / `-extidle` with their `-single` variants (processes
16 and 17). `process-crankcase-running` **is** populated, because it selects
process 1 alongside process 15. The reproduction script in §6.5 asserts this;
it is the one part of this document that is about scheduling rather than
arithmetic, and it is asserted because the alternative — believing the
subscription list — is how a reader concludes that a NONROAD run's zeroed
humidity is a bug.

`sample-runspec` has no `<models>` element at all. It is populated, so an absent
element is ONROAD; that is read off the corpus, not assumed. (`moves.rs`'s
`xml_format.rs` `into_model` leaves the list empty in that case, which is why
the predicate has to say so explicitly.)

---

## 1. Input inventory

### 1.1 The three tables

| table | columns read | rows in `process-pm-exhaust` |
|---|---|---|
| `ZoneMonthHour` | `zoneID`, `monthID`, `hourID`, `temperature`, `relHumidity` | 24 |
| `Zone` | `zoneID`, `countyID` | 1 |
| `County` | `countyID`, `altitude`, `barometricPressure` | 1 |

`temperature` is dry-bulb, **°F**. `relHumidity` is **percent**, not a fraction:
every expression that reads it divides by 100 first, and reading it as a
fraction leaves the mole fraction a clean factor of 100 low and still finite.
`barometricPressure` is in **inches of mercury** and every use of it multiplies
by 3.38639 to reach kilopascals. That unit cannot be DECLARED: the format's unit
registry is a closed list holding `mmHg` but no inch, and it carries
no numeric scale factor, so `inHg`, `in`, `inch`, `25.4 mmHg` and five other
spellings are all refused. The three pressure variables in
`components/meteorology.esm` are therefore declared dimensionless with a
sentence of prose each — finding **F34**.

All five value columns are decimal TEXT in the snapshot parquet, twelve decimal
places, holding `real*4` values widened — `63.799999237061` is what `float(63.8)`
reads back as.

### 1.2 What is NOT an input

- **No `RunSpec` scope.** The generator fills every `(zone, month, hour)` row in
  `ZoneMonthHour`. `process-pm-exhaust` selects hour 7 and gets all 24 hours
  written anyway, which is why the assertions in `components/meteorology.esm`
  can range over the whole day.
- **No emission rate, no activity, no source type.** This pass touches nothing
  downstream of the geography.
- **No `heatIndex` / `specificHumidity` / `molWaterFraction`.** They are this
  pass's OUTPUT. The nine fixtures that ingest them are reading the generator's
  answer, and that is the fact this document exists to close.

---

## 2. The computation chain

Seven steps, in the order `doHeatIndex` runs them. `MG-1` and `MG-2` are two
`UPDATE County` statements; `MG-3` is two `UPDATE ZoneMonthHour SET heatIndex`
statements; `MG-4` through `MG-7` are the Java's `TK` / `PH2O` / `PV` / `XH2O`
temporary tables and the final `UPDATE`.

### 2.1 MG-1, MG-2 — the county default fill, and why the order is load-bearing

```
MG-1  UPDATE County SET barometricPressure =
          CASE WHEN altitude = 'H' THEN 24.59 ELSE 28.94 END
      WHERE barometricPressure IS NULL OR barometricPressure <= 0

MG-2  UPDATE County SET altitude =
          CASE WHEN barometricPressure >= 25.8403 THEN 'L' ELSE 'H' END
      WHERE barometricPressure IS NOT NULL
        AND (altitude IS NULL OR altitude NOT IN ('H','L'))
```

`MG-2` reads the column `MG-1` has just written. A county missing **both**
fields therefore takes `MG-1`'s `ELSE` branch — a NULL altitude is not `'H'` —
gets 28.94 inHg, and is then classed **Low** by `MG-2`, because 28.94 ≥ 25.8403.
Run the two statements in the other order and the same county is classed High
against a NULL pressure and then filled with 24.59: a 15 % pressure error that
moves every humidity output in that county by the same 15 % and raises nothing.
`components/meteorology.esm`'s county row 4 is that case, and asserting it is
how the order stays written down.

`MG-2`'s first guard (`barometricPressure IS NOT NULL`) can never fail after
`MG-1`, so only the altitude guard discriminates. The guard is `NOT IN
('H','L')`, so a value outside the domain is treated exactly as a NULL is.

The 24.59 is the value the executed SQL carries. `MeteorologyGenerator.java`'s
own `@algorithm` comment says **24.69**; `moves.rs` follows the executed literal
and so does `lib/meteorology.esm`. Neither number is exercised by anything in
the corpus (§8.1), so this is a choice made explicitly rather than quietly.

### 2.2 MG-3 — the heat index

```
MG-3a  heatIndex = temperature                                  WHERE temperature <  78
MG-3b  heatIndex = least(120, -42.379
                            + 2.04901523*T   + 10.14333127*RH
                            - 0.22475541*T*RH
                            - 0.00683783*T*T - 0.05481717*RH*RH
                            + 0.00122874*T*T*RH + 0.00085282*T*RH*RH
                            - 0.00000199*T*T*RH*RH)             WHERE temperature >= 78
```

This is the National Weather Service (Rothfusz) regression in temperature (°F)
and relative humidity (percent). Two things about it are worth stating because
neither is guessable:

1. **It is not continuous at 78 °F and it is not meant to be.** At the corpus's
   hour 13 (78.900 °F, 58.400 % RH) the regression gives 80.464 — 1.56 °F above
   the dry-bulb temperature — while hour 12, three tenths of a degree below the
   threshold at 76.900 °F, passes through unchanged.
2. **The regression is not the identity below its range.** Applied at hour 7
   (59.5 °F, 90.4 % RH) it returns 65.75 °F, and at hour 1 (63.8 °F, 84.6 %)
   67.77 °F. Across the day's **17** sub-78 °F hours it runs **1.80 to 6.25 °F
   above** the dry-bulb temperature. A document that dropped the branch would
   produce 24 finite, plausible-looking heat indices, 17 of them too high by up
   to 6.25 °F, and the downstream air-conditioning comparisons are threshold
   tests — a few degrees is what decides which side of one an hour falls on.

`MG-3` carries **no join**. It reads only `ZoneMonthHour`'s own two columns, so
it runs on every row including any whose zone has no county — which is the
narrow divergence `moves.rs`'s `AUDIT-canonical-fidelity.md` records against its
own CLI back-fill, and which the corpus does not exercise.

### 2.3 MG-4 — Fahrenheit to Kelvin

```
MG-4  TK = (5/9) * (temperature - 32) + 273.15
```

The slope is the **exact** 5/9, and that is measured rather than assumed; §7.2
is the measurement and it settles an open question in `moves.rs`'s own port.

### 2.4 MG-5 — saturation vapour pressure of water

```
MG-5  PH2O = 10 ^ (  10.79574 * (1 - 273.15/TK)
                   -  5.028   * log10(TK/273.15)
                   +  1.50475 * power(10,-4) * (1 - power(10, -8.2969*(TK/273.15 - 1)))
                   +  0.42873 * power(10,-3) * (power(10, 4.76955*(1 - 273.15/TK)) - 1)
                   -  0.2138602 )
```

A Goff–Gratch form in the reduced temperature `TK/273.15` and its reciprocal
`273.15/TK`. The two are written as separate expressions in the SQL and are kept
separate in `lib/meteorology.esm` for the same reason `moves.rs` keeps them
separate: they do not round alike, and reusing one as `1/`the other is a
different computation in binary floating point.

The one property of this polynomial a reader can check without either
implementation: at the ice point every temperature-dependent term vanishes and
`PH2O` is 10<sup>−0.2138602</sup> = 0.6111 kPa, which is the saturation pressure
of water at 0 °C.

### 2.5 MG-6, MG-7 — the two humidity outputs

```
MG-6  PV   = relHumidity/100 * PH2O
MG-7  specificHumidity = 621.1 * PV / (barometricPressure*3.38639 - PV)
      molWaterFraction =         PV / (barometricPressure*3.38639)
```

The two outputs share `PV` and share the inches-of-mercury conversion, and
**differ in exactly one term**: the specific humidity's denominator is the
pressure of the *dry* air, so it subtracts the vapour pressure; the mole
fraction's is the *ambient* pressure whole. Over the 24 rows of §6.0 dropping
that subtraction moves the specific humidity by **1.59 % to 2.02 %** — small
enough that it looks like nothing on a plot, and large enough that at worst it
is 1,009× `tolerance.toml`'s per-cell gate.

`lib/meteorology.esm` carries the conversion as one `ambient_pressure_kilopascals`
template applied twice, once per output, so that a document cannot convert the
pressure one way for the mole fraction and another way for the specific
humidity — a divergence that would be invisible in either output alone because
each is separately plausible.

---

## 3. Join structure

One join, and it is a chain of two:

| id | left | right | key pairs |
|---|---|---|---|
| J-MET-1 | `ZoneMonthHour` | `Zone` | `zoneID = zoneID` |
| J-MET-2 | `Zone` | `County` | `countyID = countyID` |

`components/meteorology.esm` collapses the pair into one `join.on` from the hour
relation's own `met_hourCountyID` to `met_countyID`, because the intermediate
`Zone` row carries nothing else this pass needs. The `on` clause is real and not
decorative: `expand-counties` is the corpus's one populated multi-county
snapshot, and its three counties carry **three different pressures** — Los
Angeles 29.296, Cook 29.303, Washtenaw 29.095 inHg — so a document that dropped
the key and summed, or that joined to the wrong row, produces finite humidity
everywhere and is wrong in 48 of its 72 rows. §6.3 works one of those rows.

---

## 4. Reusable shapes

Everything in §2 is in `lib/meteorology.esm`. Two templates exist specifically
because a value is used more than once inside one expression, and both are the
kind of reuse `docs/esm-conventions.md` §6 is about:

| template | applied | why once rather than n times |
|---|---|---|
| `power_of_ten` | 5× | three times inside the MG-5 exponent (the two `power(10,·)` coefficient scalings and the inner decade), once for the other inner decade, once to raise 10 to the finished exponent |
| `ambient_pressure_kilopascals` | 2× | once per humidity output; see §2.5 |
| `temperature_over_ice_point` / `ice_point_over_temperature` | 2× / 3× | the reduced temperature and its reciprocal, five applications inside one exponent |
| `heat_index_regression` | 1× | separated from `heat_index` so that the branch and the polynomial can be read, and perturbed, apart |

The ten constants (`inches_hg_to_kilopascals`, `water_ice_point_kelvin`,
`fahrenheit_freezing_point`, `percent_scale`, `heat_index_threshold`,
`heat_index_ceiling`, `specific_humidity_constant`,
`default_pressure_high_altitude`, `default_pressure_low_altitude`,
`altitude_pressure_threshold`) are zero-parameter templates for the reason
`docs/esm-conventions.md` §24 gives: a document instantiating this chain carries
no bare 273.15, no bare 78 and no bare 3.38639.

---

## 5. Literals and enums

| literal | value | where |
|---|---|---|
| Fahrenheit→Kelvin slope | `5/9`, exact | MG-4, §7.2 |
| ice point | 273.15 K | MG-4, MG-5 |
| inHg → kPa | 3.38639 | MG-7 |
| specific-humidity constant | 621.1 g/kg | MG-7 |
| heat-index threshold | 78 °F | MG-3 |
| heat-index cap | 120 °F | MG-3b |
| high-altitude default pressure | 24.59 inHg | MG-1 (§2.1, and 24.69 in the Javadoc) |
| low-altitude default pressure | 28.94 inHg | MG-1 |
| altitude classification threshold | 25.8403 inHg | MG-2 |

There are **no enums**. The one categorical column, `County.altitude`, is a
single character (`'H'` / `'L'`) and is carried in `components/meteorology.esm`
as the pair of indicators `met_altitudeIsKnown` / `met_altitudeIsHigh` rather
than as a value, because the SQL's guard is a domain test (`NOT IN ('H','L')`)
and not an equality — a two-valued enum could not express "outside the domain",
which is the case `MG-2` exists for.

---

## 6. Hand-checkable worked examples

### 6.0 Run-level values used by every example

| | |
|---|---|
| zone | 261610 → county 26161 (Washtenaw, MI) |
| `County.altitude` | `'L'` — present, so `MG-1` and `MG-2` both no-op |
| `County.barometricPressure` | 29.095 inHg → ambient 29.095 × 3.38639 = **98.52701705 kPa** |
| month | 8 |

Nineteen of the corpus's 21 populated snapshots carry this exact 24-row
(zone 261610, month 8) block, cell for cell identical. The other two are
`sample-runspec` (the same zone, month 7) and `expand-month` (four
month-averaged rows at hour 0), and §6.4 works one of `expand-month`'s.

### 6.1 Worked example A — hour 7, the day's coldest and driest

`temperature` 59.5 °F, `relHumidity` 90.400001525879 %.

| step | | value |
|---|---|---|
| MG-4 | `TK = (5/9)(59.5 − 32) + 273.15` | 288.427777777778 K |
| | `TK/273.15` | 1.05593182419102 |
| | `273.15/TK` | 0.947030837683225 |
| MG-5 | term 1 `10.79574 × (1 − 273.15/TK)` | +0.571841304390 |
| | term 2 `−5.028 × log10(TK/273.15)` | −0.118841199895 |
| | term 3 `1.50475e−4 × (1 − 10^(−8.2969(a−1)))` | +0.0000987853490 |
| | term 4 `4.2873e−4 × (10^(4.76955(1−c)) − 1)` | +0.000338318707 |
| | term 5 | −0.2138602 |
| | exponent | 0.239577008550548 |
| | `PH2O = 10^exponent` | **1.73610908025527 kPa** |
| MG-6 | `PV = 0.904000015259 × PH2O` | 1.56944263504169 kPa |
| MG-7 | `621.1 × PV / (98.52701705 − PV)` | **10.0536840623976 g/kg** |
| MG-7 | `PV / 98.52701705` | **0.0159290586687024** |
| MG-3a | 59.5 < 78, so `heatIndex` | **59.5 °F** |

The snapshot stores 10.053684293477, 0.015929059029 and 59.500000000000. The
humidity differences are 2.30e−08 and 2.26e−08 relative, which is that column's
twelve-decimal storage and not accumulated error.

### 6.2 Worked example B — hour 13, the first hour above the threshold

`temperature` 78.900001525879 °F, `relHumidity` 58.400001525879 %. `MG-3b`
applies. The nine terms, in the order the SQL sums them:

| term | value |
|---|---|
| constant | −42.379000 |
| `2.04901523 T` | +161.667305 |
| `10.14333127 RH` | +592.370562 |
| `−0.22475541 T·RH` | −1035.619035 |
| `−0.00683783 T²` | −42.566929 |
| `−0.05481717 RH²` | −186.957257 |
| `+0.00122874 T²·RH` | +446.711238 |
| `+0.00085282 T·RH²` | +229.488066 |
| `−0.00000199 T²·RH²` | −42.250594 |
| sum | **80.4643545963085** |

which is below the 120 cap, so `least` passes it through. The snapshot stores
80.464354596308. The two agree to 13 significant figures, which is what makes
this the cleanest single check in the document: the heat index is one
polynomial, evaluated once, with no division and no transcendental.

Note the cancellation — nine terms spanning ±1,036 summing to 80.5. That is
worth knowing before writing the expression: the sum is about 13 times smaller
than its largest term, so the result carries roughly one more decimal digit of
cancellation than the inputs, and this is the one expression in the chain where
term ORDER could plausibly matter. Measured, it does not at this magnitude.

### 6.3 Worked example C — Los Angeles, and why the county join is real

`expand-counties` zone 60370 → county 6037, `barometricPressure` **29.296** inHg,
hour 15: `temperature` 84.900001525879 °F, `relHumidity` 40.700000762939 %.

| | value |
|---|---|
| ambient | 29.296 × 3.38639 = 99.20768144 kPa |
| `PH2O` | 4.09876582 kPa |
| `PV` | 1.66819772 kPa |
| `specificHumidity` | **10.6225455** g/kg (snapshot: 10.622545665582) |
| `molWaterFraction` | **0.0168152072** (snapshot: 0.016815207465) |
| `heatIndex` | **84.3452990** °F (snapshot: 84.345298991887) |

Evaluate the same row against Washtenaw's 29.095 inHg instead and the specific
humidity is 10.6972 — 0.70 % high, 350× the per-cell gate, and entirely
invisible without a per-cell comparison. That is what `J-MET-1`'s `on` clause is
holding.

### 6.4 Worked example D — February, and the cold side of the reduced temperature

`expand-month` is the corpus's only snapshot with a `ZoneMonthHour` row below
freezing: month 2, hour 0, `temperature` 26.465902552983 °F,
`relHumidity` 70.802489144539 %.

| step | value |
|---|---|
| `TK` | 270.075501418324 K — **below** the ice point |
| `TK/273.15` | 0.988744284892271 |
| `273.15/TK` | 1.01138384846286 |
| MG-5 terms 1–4 | −0.122897068, +0.024717717, −0.0000360993, −0.0000503850 |
| exponent | −0.31212603520523 |
| `PH2O` | 0.487387026555631 kPa |
| `specificHumidity` | **2.18299345439443** g/kg (snapshot: 2.182993506596) |

Every one of the four temperature-dependent terms changes sign relative to §6.1,
which is the point of carrying this row: a Goff–Gratch form that had `TK/273.15`
and `273.15/TK` transposed agrees with the reference to about 1e−3 on a warm
August afternoon and is 12 % wrong here.

### 6.5 The reproduction script

Extracted and run by `./run-meteorology-oracle.sh`. Unlike its nine siblings it
is handed the snapshots **directory** rather than one snapshot, because the
thing being reproduced is a generator that ran in 21 of them and deliberately
did not run in 19. It **asserts** a floor under the cell count (§35.5 of
`docs/esm-conventions.md` says why a floor and not an equality), the **exact**
key set, the worst relative error, the scheduling predicate of §0.1, and that
the two candidate Fahrenheit slopes of §7.2 are distinguishable at all. It runs
in about 1.4 s over the whole corpus, because a snapshot the generator did not
run on is settled from one column's distinct values rather than by materialising
930,816 rows.

```python
#!/usr/bin/env python3
"""MeteorologyGenerator.doHeatIndex, reproduced over every snapshot that ran it."""
import sys, os, re, glob, math
import pyarrow.parquet as pq

ROOT = sys.argv[1]                      # the snapshots DIRECTORY, not one snapshot
SUBSCRIBED = {1, 2, 9, 10, 90, 91}      # MeteorologyGenerator.subscribeToMe

def path_of(snap, name):
    """The EXECUTION database's copy of `name`, or None."""
    hits = [h for h in glob.glob("%s/tables/db__*__%s.parquet" % (snap, name))
            if "__out_" not in os.path.basename(h)]
    return hits[0] if len(hits) == 1 else None

def table(snap, name, columns=None):
    p = path_of(snap, name)
    return None if p is None else pq.read_table(p, columns=columns).to_pylist()

def wrote_anything(path):
    """Did the generator run on this snapshot?

    Read as ONE column and reduced to its DISTINCT values before any row is
    materialised. The NONROAD `ZoneMonthHour` tables are 930,816 rows each and
    twelve of them are in the corpus; `to_pylist()` on all of that is 30 seconds
    of the suite's time to establish a single boolean, and the boolean is the
    only thing needed from a snapshot the generator did not run on.
    """
    seen = pq.read_table(path, columns=["specificHumidity"]).column(0).unique()
    return any(v is not None and float(v) != 0.0 for v in seen.to_pylist())

def num(v):
    """A decimal-text column cell as a float; None stays None."""
    return None if v is None else float(v)

# ---- the generator ---------------------------------------------------------
# County fill step 1, then step 2 -- in that order, because step 2 reads the
# pressure step 1 has just written.
def resolve_pressure(pressure, altitude):
    if pressure is not None and pressure > 0.0:
        return pressure
    return 24.59 if altitude == "H" else 28.94

def resolve_altitude(altitude, pressure):
    if altitude in ("H", "L"):
        return altitude
    return "L" if pressure >= 25.8403 else "H"

def fahrenheit_to_kelvin(t):
    return (5.0 / 9.0) * (t - 32.0) + 273.15

def saturation_vapor_pressure(tk):
    a = tk / 273.15                     # TK/273.15 and 273.15/TK are separate
    c = 273.15 / tk                     # expressions in the SQL; keep them so
    e = (10.79574 * (1.0 - c)
         - 5.028 * math.log10(a)
         + 1.50475 * 10.0 ** -4.0 * (1.0 - 10.0 ** (-8.2969 * (a - 1.0)))
         + 0.42873 * 10.0 ** -3.0 * (10.0 ** (4.76955 * (1.0 - c)) - 1.0)
         - 0.2138602)
    return 10.0 ** e

def heat_index(t, rh):
    if t < 78.0:
        return t
    return min(-42.379 + 2.04901523 * t + 10.14333127 * rh
               - 0.22475541 * t * rh - 0.00683783 * t * t - 0.05481717 * rh * rh
               + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh
               - 0.00000199 * t * t * rh * rh, 120.0)

def meteorology(t, rh, pb):
    pv = rh / 100.0 * saturation_vapor_pressure(fahrenheit_to_kelvin(t))
    ambient = pb * 3.38639
    return (heat_index(t, rh), 621.1 * pv / (ambient - pv), pv / ambient)

# ---- the sweep -------------------------------------------------------------
snapshots = sorted(d for d in os.listdir(ROOT) if os.path.isdir(ROOT + "/" + d))
worst, worst_key, cells, populated, unpopulated = 0.0, None, 0, [], []
missing, extra, predicate_checked, predicate_wrong = 0, 0, 0, []

for name in snapshots:
    snap = ROOT + "/" + name
    zmh_path = path_of(snap, "zonemonthhour")
    if zmh_path is None:
        continue
    if not {"heatIndex", "specificHumidity", "molWaterFraction"} <= set(
            pq.ParquetFile(zmh_path).schema_arrow.names):
        continue

    if not wrote_anything(zmh_path):
        unpopulated.append(name)
    else:
        populated.append(name)
        zmh = pq.read_table(zmh_path).to_pylist()
        zone = {r["zoneID"]: r["countyID"] for r in table(snap, "zone")}
        county = {}
        for r in table(snap, "county"):
            p = resolve_pressure(num(r["barometricPressure"]), r["altitude"])
            county[r["countyID"]] = (p, resolve_altitude(r["altitude"], p))

        ref, got = {}, {}
        for r in zmh:
            hi = num(r["heatIndex"])
            sh = num(r["specificHumidity"])
            xh = num(r["molWaterFraction"])
            if hi is None or sh is None or xh is None or (sh == 0.0 and xh == 0.0):
                continue                 # the generator did not run on this row
            key = (r["zoneID"], r["monthID"], r["hourID"])
            ref[key] = (hi, sh, xh)
            got[key] = meteorology(num(r["temperature"]), num(r["relHumidity"]),
                                   county[zone[r["zoneID"]]][0])

        missing += len(set(ref) - set(got))
        extra += len(set(got) - set(ref))
        for key in ref:
            for g, e in zip(got[key], ref[key]):
                rel = abs(g - e) / abs(e) if e else abs(g - e)
                if rel > worst:
                    worst, worst_key = rel, (name,) + key
            cells += 3

    # The scheduling predicate of section 0.1, checked rather than believed.
    xml = "%s/../fixtures/%s.xml" % (ROOT, name)
    rpp = table(snap, "runspecpollutantprocess", ["polProcessID"])
    if os.path.exists(xml) and rpp is not None:
        predicate_checked += 1
        models = set(re.findall(r'<model value="(\w+)"', open(xml).read()))
        # A RunSpec with no <models> element predates the NONROAD model and is
        # ONROAD; `sample-runspec` is the corpus's one such file, and it IS
        # populated, so the default is read from the corpus rather than assumed.
        onroad = "ONROAD" in models or not models
        runs = onroad and bool({r["polProcessID"] % 100 for r in rpp} & SUBSCRIBED)
        if runs != (name in populated):
            predicate_wrong.append(name)

print("ZoneMonthHour: %d snapshots carry the three columns, %d populated and "
      "%d not" % (len(populated) + len(unpopulated), len(populated), len(unpopulated)))
print("               %d rows compared, %d cells, %d missing / %d extra keys"
      % (cells // 3, cells, missing, extra))
print("               worst relative error %.3e at %s zone %d month %d hour %d"
      % ((worst,) + worst_key))
print("subscription:  %d of them checked against ONROAD x processes "
      "{1,2,9,10,90,91}; %d disagree" % (predicate_checked, len(predicate_wrong)))

# ASSERTED, not merely printed (docs/esm-conventions.md 21): run-tests.sh reads
# this script's EXIT CODE, so a regression that left the key set intact and moved
# every value would otherwise be reported green with the evidence in a log.
# A FLOOR, not an equality. The snapshot corpus is shared with the other rungs
# and it grows: it was 39 snapshots when this was written and 40 by the time the
# suite next ran, the new one NONROAD and correctly unwritten. An equality here
# would turn a sibling's capture into this oracle's failure. A floor still stops
# the thing the assertion is for -- a snapshot that quietly stopped being read
# passes by default -- because that can only make the count go DOWN.
assert cells >= 1596, cells
assert (missing, extra) == (0, 0), (missing, extra)
assert worst < 1e-7, "worst relative error %.3e exceeds 1e-7" % worst
assert not predicate_wrong, predicate_wrong

# The one substitution that would pass every gate this repository applies to a
# FIXTURE and fail here: MariaDB reads the Java's `(5/9)` literal as DECIMAL
# division, which rounds to 0.5556. Measured, not argued.
def with_slope(slope, t, rh, pb):
    tk = slope * (t - 32.0) + 273.15
    pv = rh / 100.0 * saturation_vapor_pressure(tk)
    return 621.1 * pv / (pb * 3.38639 - pv)
t, rh, pb = 59.5, 90.400001525879, 29.095
exact, decimal = with_slope(5.0 / 9.0, t, rh, pb), with_slope(0.5556, t, rh, pb)
print("slope:         exact 5/9 gives %.12f g/kg, MariaDB's decimal 0.5556 gives "
      "%.12f, a relative %.3e" % (exact, decimal, abs(decimal - exact) / exact))
assert abs(decimal - exact) / exact > 2e-5, "the two slopes are not distinguishable"
```

Result:

```
ZoneMonthHour: 40 snapshots carry the three columns, 21 populated and 19 not
               532 rows compared, 1596 cells, 0 missing / 0 extra keys
               worst relative error 2.391e-08 at expand-month zone 261610 month 2 hour 0
subscription:  40 of them checked against ONROAD x processes {1,2,9,10,90,91}; 0 disagree
slope:         exact 5/9 gives 10.053684062398 g/kg, MariaDB's decimal 0.5556 gives 10.054486480128, a relative 7.981e-05
```

### 6.6 What the component's inline tests check

`components/meteorology.esm` carries **42 assertions** in six tests:

| test | what it pins | against |
|---|---|---|
| `the_county_fill_runs_in_order_…` | `MG-1` and `MG-2` on five county cases | the SQL (rows 1–2 also the corpus) |
| `the_county_join_delivers_the_zones_own_pressure` | 29.095 inHg on all 24 hours, by `min` and `max` as well as by cell | the corpus |
| `the_heat_index_is_the_temperature_below_78_…` | six hours spanning the branch, plus `min` and `max` | the snapshot's `heatIndex` |
| `the_saturation_chain_reproduces_…` | five hours plus `min` and `max` | the snapshot's `specificHumidity` |
| `the_mole_fraction_differs_…_in_exactly_one_term` | the same five hours plus `min` and `max` | the snapshot's `molWaterFraction` |
| `the_intermediate_columns_are_the_javas_own…` | `TK`, `PH2O`, `PV` at two hours each | this port only — see below |

The last one is the only test in the file whose expected values are **not** the
reference's, and it says so: MOVES drops the `TK` / `PH2O` / `PV` temporary
tables and the snapshot does not carry them. It is kept because it is where the
chain can be perturbed one stage at a time, and because the ice-point property
of §2.4 gives it one line a reader can check independently.

Measured, the assertions can fail: substituting 0.5556 for the exact 5/9 in
`lib/meteorology.esm` turns **20 of the 42** red, including all seven
`specificHumidity` and all seven `molWaterFraction` assertions.

---

## 7. Fidelity notes and tolerance

### 7.1 The measured result

| | |
|---|---|
| snapshots reproduced | **21** of the 40 carrying the columns; the other 19 correctly produce nothing (§0.1) |
| rows | **532** |
| cells | **1,596** |
| key set | **0 missing, 0 extra** |
| assertion polarity | the cell count is asserted as a **floor** (`>= 1596`), the key set as an **equality**, per `docs/esm-conventions.md` §35.5 — the corpus is shared with the other rungs and grows |
| worst relative error | **2.391e−08**, at `expand-month` zone 261610 month 2 hour 0, `specificHumidity` |

For comparison, the **twelve** wired `MOVESOutput` fixtures sit between
4.561e−06 and 9.910e−06 (the **nine** that ingest these three columns span the
same range: `nr-logging-county` 4.561e−06 to `process-pm-exhaust` 9.910e−06),
and `tolerance.toml`'s per-cell gate is 2e−5. This rung is **two
orders of magnitude tighter than any of them**, and the reason is structural
rather than flattering: `ZoneMonthHour` stores twelve decimal places where
`MOVESOutput.emissionQuant` stores six significant figures, and there is no
chain of multiplications between the input and the output to accumulate through
— `heatIndex` is one polynomial and the humidities are four operations past one
transcendental. 2.391e−08 is that storage limit, not this port's accuracy.

`components/meteorology.esm` asserts at `rel 1e-7`, four times the worst cell in
the corpus. That is a real gate: it is 200× tighter than `tolerance.toml`'s
fixture gate and it rejects the §7.2 substitution by three orders of magnitude.

### 7.2 The Fahrenheit slope, decided by measurement

`meteorology.rs` carries an explicit open question on `fahrenheit_to_kelvin`:

> The Java writes the conversion factor as the SQL literal `(5/9)`. In MariaDB
> `5/9` is decimal division and rounds to `div_precision_increment` (default 4)
> places — 0.5556 — before promotion to a double. This port uses the exact ratio
> `5.0 / 9.0`; […] canonical-capture comparison is the place to revisit this if
> a divergence appears.

This document is that comparison, and it resolves the question:

| slope | worst relative error over the corpus's 1,596 cells |
|---|---|
| exact `5.0/9.0` | **2.391e−08** |
| MariaDB decimal `0.5556` | **1.379e−04** |

Four orders apart, and the decimal answer is **seven times outside
`tolerance.toml`'s per-cell 2e−5**. MOVES computes with the exact ratio. The
note in `moves.rs` calling the difference "far inside any generator tolerance
budget" is wrong by about an order of magnitude against this repository's gate,
and worth correcting upstream.

`lib/meteorology.esm` writes the slope as `{"op": "/", "args": [5.0, 9.0]}`
rather than as `0.5555555555555556`, so that the SQL it came from stays legible
and so that the question above is answerable by reading the document.

### 7.3 Precision-sensitive operations, ranked

1. **The Fahrenheit slope** (§7.2) — 8.0e−05 relative on the slope itself, which
   is 5.8e−03 relative on `TK`'s *offset* from the ice point and comes out as
   1.379e−04 on the humidity: the MG-5 exponent multiplies the reduced
   temperature's error by about 10.8 and then exponentiates it.
2. **`TK/273.15` vs `1/(273.15/TK)`** — measured over the corpus's temperature
   range the two agree to **1.12e−16** relative (about half a ulp; they are
   bit-identical at three of the four temperatures checked and differ by one ulp
   at the sub-freezing one). They are kept apart anyway, because the MG-5
   exponent multiplies any difference by 10.8 and then exponentiates it, and
   because it costs nothing to write what the SQL writes.
3. **The heat-index polynomial's cancellation** (§6.2) — nine terms spanning
   ±1,036 summing to 80.5. Measured, term order does not move the twelve
   decimals the snapshot stores; it is ranked here because it is the only place
   in the chain where it plausibly could.
4. **Everything else** — four multiplications and two divisions, none of them
   near a cancellation.

There is **no `element_type` question here**. Unlike `nr-logging-county`
(§`docs/esm-conventions.md` 17) nothing in this chain has a row set that depends
on a comparison, so binary64 throughout is not a choice with consequences.

---

## 8. Gaps and things not verified

### 8.1 The county fallback branches are ported, not checked

`MG-1` and `MG-2`'s fallback arms are **not exercised anywhere in the corpus.**
Measured across all 40 snapshots' `County` tables: **22,815 rows, 3,286 distinct
`countyID`s, `altitude` `'L'` on 21,814 of them and `'H'` on 1,001 — and not one
row with a NULL or non-positive `barometricPressure`.** (The variety is smaller
than the row count suggests: there are 1,910 distinct `(altitude,
barometricPressure)` pairs among the 22,815.) Every county in the corpus therefore takes
`MG-1`'s "keep what is stored" path and `MG-2`'s "keep what is stored" path.

So three of `components/meteorology.esm`'s five county rows are checked against
**the SQL as ported**, not against MOVES. That includes the 24.59 / 24.69
discrepancy of §2.1: nothing in this repository can tell which number MOVES
would use, because MOVES is never asked. The component's test description says
this in the same words, so a reader who reaches the assertions before the
specification still gets told.

Closing this would need a captured run whose county input is deliberately
incomplete, which the characterization corpus does not contain and this rung
does not add.

### 8.2 What is still read rather than computed

The nine fixtures listed at the top of this document **still ingest** the three
columns. This rung produces them in `components/meteorology.esm` and proves the
arithmetic against the reference; it does not rewire the fixtures to consume the
computed values. That is a separate change to nine large documents, each of
which would have to be re-verified end to end against its own `MOVESOutput`, and
it is deliberately not bundled here — the risk profile of "prove a generator"
and "retarget nine fixtures" is not the same, and `docs/esm-conventions.md` §23
is the rule about measuring whether a fixture can see a stage before moving it
there.

What that rewiring would buy is bounded and can be stated now: the computed
columns differ from the ingested ones by at most **2.391e−08** relative, which
is 840× below `tolerance.toml`'s per-cell gate and 190× to 410× below the cells
the nine currently report. No fixture's comparison would move measurably. The value would be in removing nine reads from the reference, not in
accuracy.

### 8.3 What the generator does that this port does not

- **The `County` write-back.** MOVES mutates `County.barometricPressure` and
  `County.altitude` in place and later stages join on the altitude class.
  `components/meteorology.esm` computes both resolved values but nothing
  downstream in this repository reads them.
- **Idempotence.** `doHeatIndex` is idempotent — every step reads only original
  input columns and the fill conditions stop matching once filled — so the Java's
  `isFirst` flag is an optimisation, not a correctness requirement
  (`meteorology.rs`, module doc). Nothing here depends on that and nothing here
  checks it.
- **Rows whose zone has no county.** `MG-3` has no join and would still write a
  heat index; `MG-7` joins and would leave the humidity columns untouched. No
  snapshot has such a row.

---

## 9. Summary for the `.esm` author

1. This is a **generator**, so there is no `MOVESOutput` and no fixture in
   `fixtures/`. The arithmetic lives in `lib/meteorology.esm` and the relation
   and assertions in `components/meteorology.esm`, which is the shape
   `components/tank_temperature.esm` established for `TankTemperatureGenerator`
   TTG-1.
2. **Two `UPDATE County` statements run first and the second reads the first's
   output** (§2.1). Write them in that order or a county missing both fields is
   filled 15 % wrong.
3. **The heat index is a branch, not a formula** (§2.2). Below 78 °F it is the
   temperature; the regression runs 1.80–6.25 °F high there, over 17 of the
   day's 24 hours — small enough to look right and large enough to move a
   threshold test.
4. **The slope is the exact 5/9** (§7.2), and this is measured.
5. **The two humidity outputs differ in exactly one term** (§2.5). Convert the
   pressure once, in one template, so they cannot disagree about it.
6. **`relHumidity` is a percent.**
7. The gate is `rel 1e-7` in the component and the corpus reproduces at
   2.391e−08. Do not widen either; the room is real.
8. This rung's general lessons are `docs/esm-conventions.md` **§35**: why a
   generator does not go in `fixtures/` (§35.1), why its scheduling condition is
   half the claim and is asserted on the snapshots that FAIL it (§35.2), why a
   host-language fidelity question is settled by running both candidates
   (§35.3), why each test says whether it faces the reference or the port
   (§35.4), and why an oracle over the shared snapshot corpus asserts a floor
   rather than a count (§35.5). The one format refusal it hit is finding **F34**
   (§1.1).
