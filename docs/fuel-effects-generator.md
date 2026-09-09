# `FuelEffectsGenerator` — computation specification

The port specification for Phase 5's eleventh rung, written to the method of
`docs/meteorology-generator.md`: the input inventory determined from evidence,
the chain with source lines into `../moves.rs`, every join with its exact key
pairs, and worked examples whose numbers can be checked by hand.

It is the second specification in this repository whose product is not a
`MOVESOutput` row, and the first whose product is a table of numbers MOVES
computes **from text it stores in another table**. `generalFuelRatioExpression`
holds SQL arithmetic in a `VARCHAR` column; the Java pastes each row's text into
`insert into generalFuelRatio … select (EXPRESSION) from fuelFormulation` and
lets MariaDB evaluate it against every fuel formulation of the matching fuel
type. Those strings are equations an engine evaluates, which is the same
category of thing an `.esm` expression is, so they are ported as **code** —
the forms as expression templates, the coefficients as data
(`docs/esm-conventions.md` §24).

---

## 0. The generator at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/process-pm-exhaust.xml` |
| Model | ONROAD, `modelscale` `Inv` (inventory), `modeldomain` `DEFAULT` |
| Geography | county 26161 (Washtenaw, Michigan), fuel region 270000000 |
| Time | year 2020, month 8 |
| Reads | `generalFuelRatioExpression`, `FuelFormulation`, `FuelSubtype`, `FuelSupply` |
| Writes | `generalFuelRatio` — `fuelEffectRatio` and `fuelEffectRatioGPA`, keyed on (fuelTypeID, fuelFormulationID, polProcessID, minModelYearID, maxModelYearID, minAgeID, maxAgeID, sourceTypeID) |
| Output | **no `MOVESOutput` rows at all** — this is a generator, and its product is an execution-database table |
| Calculator path | **`FuelEffectsGenerator`** — a generator with nothing downstream of it inside this slice |
| Rows | 58 in `process-pm-exhaust`; **97 across the whole snapshot corpus** (§7.1), from two of the 42 snapshots that carry the input table |
| Ported by | `lib/fuel_effects.esm` (the forms) and `components/fuel_effects.esm` (the coefficients, the relation and the assertions) |
| Java | `gov/epa/otaq/moves/master/implementation/ghg/FuelEffectsGenerator.java`, method `doGeneralFuelRatio` |
| Rust | `../moves.rs/crates/moves-calculators/src/generators/fueleffectsgenerator/` |

### 0.1 Which runs it fires on, and how that was established

`calculator-dag.json` records fourteen `PROCESS`-granularity subscriptions for
`FuelEffectsGenerator`, at priority `GENERATOR-1` — one step after
`TankFuelGenerator`, which modifies fuel-formulation parameters:

> 1 Running Exhaust, 2 Start Exhaust, 9 Brakewear, 10 Tirewear,
> 11 Evap Permeation, 12 Evap Fuel Vapor Venting, 13 Evap Fuel Leaks,
> 15 Crankcase Running, 16 Crankcase Start, 17 Crankcase Extended Idle,
> 18 Refueling Displacement, 19 Refueling Spillage,
> 90 Extended Idle Exhaust, 91 Auxiliary Power Exhaust.

**Not all fourteen load the generator, and that is measured rather than
argued.** Every snapshot carries an `execution-trace.json` recording the Java
classes MOVES actually loaded, so the question "did the generator run here?" has
a direct answer that does not depend on reading any output table. Over the 42
snapshots that carry `generalFuelRatioExpression` (the corpus is shared and it
grows: it was 40 while this rung was being written and 42 by the time the suite
next ran — §7.5):

| RunSpec processes | snapshots | `FuelEffectsGenerator` loaded |
|---|---:|---|
| contain one of 1, 2, 9, 10, 11, 12, 13, 90 | 24 | **yes**, all 24 |
| NONROAD (`<model value="NONROAD">`) | 12 | no, none |
| `{16}`, `{17}` or `{91}` alone | 6 | **no**, none |

so the predicate the oracle asserts is

> loaded ⇔ ONROAD **and** the run's processes meet {1, 2, 9, 10, 11, 12, 13, 90}

and it decides all 42 correctly. `process-crankcase-start` selects 16 alone and does not
load it; `process-apu` selects 91 alone and does not; `process-extended-idle`
selects 90 alone and does.

**Three of the fourteen declared processes are never selected alone**, so
nothing here decides them: 15 appears only in `process-crankcase-running`
alongside process 1, and 18 and 19 only in `process-refueling` alongside 1, 2
and 90. The eight-process set above is therefore a statement about what the
corpus shows and not a claim to have read `subscribeToMe`: it is the smallest
set that decides all 42, and processes 15, 18 and 19 could belong to it without
the corpus noticing.

This is `docs/esm-conventions.md` §35.2's rule applied a second time: a
generator's claim has two halves and the second is *when it runs*. The negative
cases are the evidence, and eighteen of the forty-two are negative.

---

## 1. Input inventory

### 1.1 The four tables

| table | rows in `process-pm-exhaust` | what is read |
|---|---:|---|
| `generalFuelRatioExpression` | 58 | `fuelTypeID`, `polProcessID`, `minModelYearID`, `maxModelYearID`, `minAgeID`, `maxAgeID`, `sourceTypeID`, `fuelEffectRatioExpression`, `fuelEffectRatioGPAExpression` |
| `FuelFormulation` | 2,158 | `fuelFormulationID`, `fuelSubtypeID` and the seventeen property columns |
| `FuelSubtype` | 13 | `fuelSubtypeID` → `fuelTypeID` |
| `FuelSupply` | 5 | `fuelFormulationID` — the in-use set |

The seventeen property columns are `RVP`, `sulfurLevel`, `ETOHVolume`,
`MTBEVolume`, `ETBEVolume`, `TAMEVolume`, `aromaticContent`, `olefinContent`,
`benzeneContent`, `e200`, `e300`, `volToWtPercentOxy`, `BioDieselEsterVolume`,
`CetaneIndex`, `PAHContent`, `T50`, `T90`. An expression may reference any of
them by name, case-insensitively, because MariaDB identifiers are.

### 1.2 What is NOT an input

* **`fuelParameterName` is not an input**, and its IDs are not the property IDs
  `components/fuel_effects.esm` uses. That table's `T90` (id 10) is the derived
  expression `4.5454545*(155.47 - ff.E300)`; a `fuelEffectRatioExpression` reads
  the **stored** `T90` column. Using the one for the other would be a wrong
  number, not a missing one.
* **`criteriaRatio` and `ATRatio` are not inputs** — they are where MOVES puts
  the rows this path computes and then deletes (§8.1).
* **`altRVP` is not a column of `FuelFormulation`.** The Java `setup()` adds it
  to the table before the E85 Pseudo-THC expressions read it, so the snapshot
  never carries it. §8.3 measures what that costs, which is nothing.

---

## 2. The expression census — the data that is code

Every number in this section is `./run-fuel-effects-oracle.sh`'s or a one-pass
scan of the same tables, over the 42 snapshots that carry the table as this is
written. **The corpus is shared and it grows**: two captures landed while this
rung was being verified and moved every count below by 15 to 20 %, which is
§7.5's subject. These are the counts on that day.

| | count |
|---|---:|
| `generalFuelRatioExpression` rows, summed over the corpus | **2,078** |
| distinct rows (all nine columns) | **567** |
| distinct `fuelEffectRatioExpression` strings | **118** |
| distinct parse-tree skeletons (every numeric literal replaced by `#`) | **72** |
| distinct top-level algebraic **forms** | **6** (plus a bare constant) |

The gap between 72 and 6 is the whole reason the forms are worth factoring: the
skeleton count is inflated because MOVES writes the same polynomial's terms in
different **orders** in different rows — `…+b*ETOH-c*RVP+d*T90…` in one and
`…-c*aromatics-e*T50+b*ETOH…` in another, with the same coefficients. Those are
one form and one coefficient set; only the text differs. Form C alone accounts
for **57 of the 72 skeletons**, and form C is one form.

### 2.1 The six forms

| # | form | rows | strings | where | ported |
|---|---|---:|---:|---|---|
| A | `exp(Σ aⱼ·((xⱼ−mⱼ)/sⱼ))/base` | 32 | 2 | `process-pm-exhaust` only | **yes** — `log_linear_ratio` |
| B | `1 + (least(bioDieselEsterVolume, 20)/100)·c` | 676 | 4 | 21 snapshots | **yes** — `biodiesel_ester_ratio` |
| C | `if(sulfurLevel > 30, HIGH, LOW)` | 1,013 | 100 | 15 snapshots | **yes** — `sulfur_switch_ratio` |
| D | `((c₂·O² + c₁·O + c₀)/base)·scale` | 61 | 2 | 4 snapshots | no (§8.1) |
| E | `((benzeneContent − c)·k + 1)·scale` | 61 | 2 | 4 snapshots | no (§8.1) |
| F | `exp(A)/(exp(B) − exp(C))` | 151 | 6 | 4 snapshots | no (§8.1) |
| G | a bare numeric literal | 84 | 2 | 3 snapshots | no — and it needs no template |

Row and string counts sum to 2,078 and 118 exactly, which is the check that the
classification is a partition and not a sample. Form G is a constant ratio at
polProcessID 2701, and every one of its rows sits in a snapshot where it is
either never computed (NONROAD, §0.1) or handed off (§8.1), so it has no
reachable answer to reproduce.

Form C's two arms, verbatim from a corpus string with the coefficients named:

```
HIGH = exp(P) · ( K + ( w·((303^g − 30^g)/30^g)
                        + (1−w)·( M·(S^g − 30^g)/30^g ) ) ) / (base · gpa)
LOW  = ( exp(P)/base ) · ( 1 − d·(S₀ − S) )
```

with `w = 0.425` on every string, `S` the sulfur level in ppm, and `x^g` written
throughout as `exp(g·ln(x))`. `P` is an affine polynomial in the raw fuel
properties, one of whose terms is `T50*T50` — which is why
`lib/fuel_effects.esm`'s `standardized_term` carries a power.

**`S₀` is not the 30 the `if` switches on.** Most strings write `(30 −
sulfurLevel)` in the low arm and some write `(10 − sulfurLevel)`; the switch
threshold is 30 in all of them. Two constants that coincide on most rows is
exactly the situation that produces a wrong port, so they are two columns.

### 2.2 What the port covers, and what "covers" means here

Forms A, B and C are **1,721 of the 2,078 rows**, and they are the three
`lib/fuel_effects.esm` spells. But coverage of the table is not the same as
coverage by the reference, and §8.1 is blunt about the difference: only forms A
and B are checked against MOVES anywhere, because every row that uses C, D, E or
F is moved out of `generalFuelRatio` before a snapshot is taken.

### 2.3 `fuelEffectRatioGPA` is the same expression

`generalFuelRatioExpression` carries two expression columns and
`generalFuelRatio` carries two ratios. **On all 2,078 corpus rows the two
expression strings are byte-identical**, and on all 97 reference rows the two
ratios are. So the component computes one column and this sentence records the
measurement, rather than duplicating the arithmetic to prove a thing the data
already says. The GPA column exists in MOVES for geographic-phase-in areas
whose fuel differs; no RunSpec in this corpus is one.

---

## 3. Join structure

`doGeneralFuelRatio` is four relational steps and one evaluation.

| id | join | key pairs |
|---|---|---|
| J-FE-1 | expression → term set | `fe_termSetID = fe_expressionTermSetID` |
| J-FE-2 | term → the property value on the expression's own formulation | `(fe_propFormulationID, fe_propPropertyID) = (fe_expressionFormulationID, fe_termPropertyID)` |
| J-FE-3 | expression → `BioDieselEsterVolume` | `(fe_propFormulationID, fe_propPropertyID) = (fe_expressionFormulationID, fe_expressionEsterPropertyID)` |
| J-FE-4 | expression → `sulfurLevel` | `(fe_propFormulationID, fe_propPropertyID) = (fe_expressionFormulationID, fe_expressionSulfurPropertyID)` |

J-FE-1 and J-FE-2 are one contraction over three ranges in
`components/fuel_effects.esm`, and J-FE-2 is where the whole relational content
of the generator sits: drop its formulation half and every expression sums the
terms over all five formulations at once.

The steps MOVES takes that are *not* joins in this port, because they select
rows rather than combine them:

1. **Fuel-type / fuel-supply intersection.** `getFuelFormulations(fuelTypeID)`
   inner-joins `FuelFormulation` to `FuelSubtype`, so a formulation whose
   subtype has no `FuelSubtype` row belongs to no fuel type and is dropped;
   `getFuelSupplyFormulations(fuelTypeID)` is `FuelSupply`'s set. A formulation
   must be in both.
2. **The `already_ratioed` de-duplication.** At most one row per
   `(fuelFormulationID, polProcessID)` survives; the Java carries the pairs
   already written and skips them, so the FIRST expression to reach a pair wins
   and the later ones are silently dropped.
3. **`minModelYearID > maxModelYearID` is an empty window** and the expression
   is skipped entirely.
4. **The E85 Pseudo-THC derivation** (`@step 050`). For every fuel-type-5,
   THC (pollutant 1), Running-or-Start expression whose `maxModelYearID ≥ 2001`,
   MOVES adds a copy that targets the synthetic pollutant 10001, restricts to
   fuel subtypes 51 and 52, raises `minModelYearID` to at least 2001, and
   replaces `RVP` with `altRVP` throughout both expression strings. §8.3.

---

## 4. Reusable shapes

`lib/fuel_effects.esm`, imported by reference:

| template | what it is |
|---|---|
| `capped_property` | the `least(cap, x)` clamp, guarded by an indicator rather than a sentinel |
| `standardized_term` | `a·((clamp(x)^p − m)/s)` — one template for every term of every form |
| `log_linear_ratio` | `exp(Σ)/base` |
| `biodiesel_ester_ratio` | `1 + (least(v, 20)/100)·c` |
| `power_via_exp_log` | `exp(g·ln(x))`, the spelling the SQL uses and not `pow` |
| `relative_power_step` | `(x^g − r^g)/r^g` |
| `scaled_relative_power_step` | `(m·(x^g − r^g))/r^g` — the multiplier inside the numerator, as the SQL writes it |
| `sulfur_high_multiplier` | `K + (w·rel(303,30,g) + (1−w)·scaled_rel(S,30,g,M))` |
| `sulfur_high_ratio`, `sulfur_low_ratio`, `sulfur_switch_ratio` | form C's two arms and the `if` |

The two relative-power templates are **two** because the SQL puts the multiplier
inside the numerator in one place and outside in the other. Algebraically the
same; not the same in binary64; and — since nothing in the corpus checks form C
against MOVES — impossible to decide here. Keeping both spellings is what stops
the difference being simplified away before anyone can measure it. It is the
same argument `components/meteorology.esm` makes for keeping `TK/273.15` and
`273.15/TK` apart.

---

## 5. Literals and enums

### 5.1 The property IDs are this document's own

1 `ETOHVolume`, 2 `aromaticContent`, 3 `T90`, 4 `BioDieselEsterVolume`,
5 `RVP`, 6 `T50`, 7 `sulfurLevel` — indices into the `fuelFormulation` **column
list**, not `fuelParameterID`s (§1.2). They exist so that a coefficient row can
name the property it multiplies and reach its value through a `join.on`.

### 5.2 The constants that are guards rather than physics

A non-sulfur expression row carries `power` 0, which makes
`exp(0·ln(x))` exactly 1 and both relative steps exactly 0, and carries `base`
1.0 and biodiesel coefficient 0. That keeps every unselected arm of the
three-way `ifelse` finite. **The one input that would still break it is a
formulation with `sulfurLevel` 0**, whose `ln` is negative infinity. None of the
five formulations in `components/fuel_effects.esm` has one, and no formulation
any fuel supply in the corpus selects has one — but that is a property of the
corpus, not of the model, and a document that ingested the whole
`FuelFormulation` table would meet formulation 0, whose every column is 0.

---

## 6. Hand-checkable worked examples

### 6.0 The values every example uses

`process-pm-exhaust`'s fuel supply carries five formulations, of which three map
to a fuel type that has expressions:

| `fuelFormulationID` | subtype | fuel type | the properties the examples read |
|---|---|---|---|
| 9114 | 12 (gasohol E10) | 1 | ETOH 10, aromatics 23.14, T90 327.77, sulfur 7.15, RVP 8, T50 222.95 |
| 25003 | 21 (diesel) | 2 | biodiesel ester 3.5 vol% |
| 27002 | 51 (E85) | 5 | ETOH 10, aromatics 23.14, T90 327.77 |

**Those are the printed decimals; the arithmetic uses the binary32 values.**
`aromaticContent` enters as 23.139999389648438 and `T90` as 327.76998901367188.
§7.2 is the measurement that decides this.

### 6.1 Worked example A — the PM log-linear ratio

`process-pm-exhaust`, fuel type 1, polProcessID 11201, formulation 9114:

```
exp( +(0.1126*((ETOHVolume-10.313704)/(7.879557)))
     +(0.1662*((aromaticContent-25.629630)/(10.015366)))
     +(0.1072*((T90-320.533333)/(19.480128))) ) / 0.911205970892
```

| term | value |
|---|---|
| `0.1126·((10 − 10.313704)/7.879557)` | −0.004482875166713046 |
| `0.1662·((23.139999389648438 − 25.629630)/10.015366)` | −0.041314177379082250 |
| `0.1072·((327.76998901367188 − 320.533333)/19.480128)` | +0.039823635895288890 |
| **exponent** | **−0.005973416650506401** |
| `exp(exponent)/0.911205970892` | **1.0909107495849824** |

The snapshot's `fuelEffectRatio` is `1.0909107495849824` — **the same f64, to
the digit**. It used to read `1.090910749585`, and this document used to
attribute those twelve decimals to a `DECIMAL(20,12)` column. They were not a
column type: they were `moves-snapshot/v1` writing every float at twelve
DECIMAL places. `moves-snapshot/v2` writes the shortest decimal that
round-trips the f64, and the 1.608e−14 residual §7.1 used to report is now
**zero** — it was the capture's rounding from end to end.

Fuel type 5's expression is the same three terms with `least(10, ETOHVolume)` in
place of `ETOHVolume`, and formulation 27002's `ETOHVolume` is exactly 10, so it
gives the **identical** ratio. §8.2 is what follows from that.

### 6.2 Worked example B — the biodiesel-ester linear

Four coefficients, five reference rows, one property:

| snapshot | polProcess | pollutant | `c` | `1 + (3.5/100)·c` | snapshot's column |
|---|---|---|---|---|---|
| `process-pm-exhaust` | 11201, 12001 | PM2.5 | −0.780 | 0.9727 | 0.972700000000 |
| `process-crankcase-running` | 115 | THC | −0.705 | 0.975325 | 0.975325000000 |
| `process-crankcase-running` | 215 | CO | −0.690 | 0.975850 | 0.975850000000 |
| `process-crankcase-running` | 315 | NOx | +0.110 | 1.003850 | 1.003850000000 |

Three reductions and one increase — the sign pattern biodiesel is known for, and
the one property of this form a reader can check without the reference. The NOx
row is also the only reference ratio in this port **above 1**: a port that
clamped the ratio at 1 would reproduce the other four exactly.

The `least(…, 20)` clamp is never reached. 3.5 is the only ester volume any
supplied formulation in the corpus carries.

### 6.3 Worked example C — the sulfur switch, on both arms

**This example's expected values are not the reference's.** They are what this
port and §6.5's independent parser both compute from the same MOVES string; §8.1
says why no third opinion is available.

The string is fuel type 1, polProcessID 101 (THC at Running Exhaust), with
`g = 0.125`, `M = 2.5`, `K = 1`, base 0.009682964656311278,
gpa 1.1424519617677948, `d = 0.0154883551740411`, `S₀ = 30`, and

```
P = −3.65275441630756 + 0.00414744109342911·ETOH − 0.0220495078142151·RVP
    + 0.00263653299169085·T90 + 5.58244506624426e−05·T50²
    − 0.00195000368524374·aromatics − 0.019529192370317·T50
```

| formulation | sulfur | arm | `P` | ratio |
|---|---:|---|---|---|
| 9114 | 7.15 ppm | LOW | −4.5478068562772247 | **0.70663961359385519** |
| 1002 | 429.96 ppm | HIGH | −4.7632892190484553 | **1.3197896196568011** |

The high arm's bracket multiplier at 429.96 ppm is 1.7100988943071584 against
0.9065409854535047 at 7.15 ppm — the two arms are not close and no rounding
choice moves a row between them.

### 6.4 Worked example D — the ethanol clamp, where the corpus cannot see it

Formulation 27001 is a real corpus `FuelFormulation` row (subtype 51, E85,
`ETOHVolume` 74, `aromaticContent` 0, `T90` 999) that no fuel supply in the
corpus selects. Run §6.1's fuel-type-5 expression against it:

| | exponent | ratio |
|---|---|---|
| with `least(10, ETOHVolume)` | 3.3038380754455403 | **29.869096664491575** |
| without the clamp | 4.2184072574439702 | 74.54429940370062 |

A factor of 2.5. This is the discriminating value the clamp never gets on any
compared cell, and `components/fuel_effects.esm` carries it as a probe for the
reason `docs/esm-conventions.md` §23 gives.

### 6.5 The reproduction script

Extracted and run by `./run-fuel-effects-oracle.sh`. Like
`./run-meteorology-oracle.sh` it is handed the snapshots **directory** rather
than one snapshot, because the thing being reproduced is a generator that ran in
24 of them and deliberately did not run in 18. It **asserts** a floor under the
cell count (`docs/esm-conventions.md` §35.5 says why a floor), zero missing
keys, that every extra key is accounted for by a hand-off table, the worst
relative error, the scheduling predicate of §0.1, that the two candidate
`FLOAT` promotions of §7.2 are distinguishable, and — with the polarity
reversed — that the integer-literal division of §7.3 is **not** decidable here.
It runs in about 5.5 s over the whole corpus.

```python
#!/usr/bin/env python3
"""FuelEffectsGenerator.doGeneralFuelRatio, reproduced over every snapshot that ran it."""
import sys, os, re, glob, json, math, struct
import pyarrow.parquet as pq

ROOT = sys.argv[1]                     # the snapshots DIRECTORY, not one snapshot
# The eight processes that, on their own, make MOVES load the generator. The
# DAG declares fourteen; section 0.1 measures which of them actually do.
LOADS = {1, 2, 9, 10, 11, 12, 13, 90}
PROPS = ["RVP", "sulfurLevel", "ETOHVolume", "MTBEVolume", "ETBEVolume", "TAMEVolume",
         "aromaticContent", "olefinContent", "benzeneContent", "e200", "e300",
         "volToWtPercentOxy", "BioDieselEsterVolume", "CetaneIndex", "PAHContent",
         "T50", "T90"]

def path_of(snap, name):
    hits = [h for h in glob.glob("%s/tables/db__*__%s.parquet" % (snap, name))
            if "__out_" not in os.path.basename(h)]
    return hits[0] if len(hits) == 1 else None

def table(snap, name):
    p = path_of(snap, name)
    return None if p is None else pq.read_table(p).to_pylist()

def f32(x):
    """A MariaDB FLOAT column value: the capture stores the DECIMAL text of a
    32-bit float, so the value MOVES computed with is that text rounded back
    to binary32 and widened. Section 7.2 measures what skipping this costs."""
    return struct.unpack("f", struct.pack("f", x))[0]

# ---- the MariaDB arithmetic subset a fuelEffectRatioExpression uses ---------
TOK = re.compile(r"""\s*(?:(?P<num>\d+\.\d*(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?
                          |\d+(?:[eE][-+]?\d+)?)
                        |(?P<id>[A-Za-z_][A-Za-z_0-9]*)
                        |(?P<op><>|!=|<=|>=|[-+*/%(),<>=]))""", re.X)
CMP = {"=", "<>", "!=", "<", "<=", ">", ">="}
ARITY = {"if": 3, "pow": 2, "power": 2, "exp": 1, "log": 1, "ln": 1, "sqrt": 1,
         "abs": 1, "least": -1, "greatest": -1}

def lex(s):
    out, i = [], 0
    while i < len(s):
        if s[i].isspace():
            i += 1; continue
        m = TOK.match(s, i)
        if not m or m.end() == i:
            raise ValueError("bad character %r in %r" % (s[i], s))
        i = m.end()
        out.append(("num", m.group("num")) if m.group("num") is not None else
                   ("id", m.group("id")) if m.group("id") is not None else
                   ("op", m.group("op")))
    return out

class P:
    def __init__(self, t): self.t, self.i = t, 0
    def peek(self): return self.t[self.i] if self.i < len(self.t) else (None, None)
    def take(self): self.i += 1; return self.t[self.i - 1]
    def op(self, o):
        k, v = self.peek()
        if k == "op" and v == o: self.i += 1; return True
        return False
    def kw(self, w):
        k, v = self.peek()
        if k == "id" and v.lower() == w: self.i += 1; return True
        return False

def p_or(p):
    a = p_and(p)
    while p.kw("or"): a = ("or", a, p_and(p))
    return a
def p_and(p):
    a = p_not(p)
    while p.kw("and"): a = ("and", a, p_not(p))
    return a
def p_not(p):
    return ("not", p_not(p)) if p.kw("not") else p_cmp(p)
def p_cmp(p):
    a = p_add(p); k, v = p.peek()
    if k == "op" and v in CMP: p.take(); return ("cmp", v, a, p_add(p))
    return a
def p_add(p):
    a = p_mul(p)
    while True:
        k, v = p.peek()
        if k == "op" and v in "+-": p.take(); a = (v, a, p_mul(p))
        else: return a
def p_mul(p):
    a = p_un(p)
    while True:
        k, v = p.peek()
        if k == "op" and v in "*/%": p.take(); a = (v, a, p_un(p))
        else: return a
def p_un(p):
    k, v = p.peek()
    if k == "op" and v == "-": p.take(); return ("neg", p_un(p))
    if k == "op" and v == "+": p.take(); return p_un(p)
    return p_atom(p)
def p_atom(p):
    k, v = p.take()
    if k == "num": return ("lit", v)
    if k == "op" and v == "(":
        e = p_or(p)
        if not p.op(")"): raise ValueError("expected )")
        return e
    if k == "id":
        kk, vv = p.peek()
        if kk == "op" and vv == "(":
            p.take(); args = []
            if not p.op(")"):
                args.append(p_or(p))
                while p.op(","): args.append(p_or(p))
                if not p.op(")"): raise ValueError("expected ) in call")
            if v.lower() not in ARITY: raise ValueError("unknown function %r" % v)
            return ("call", v.lower(), args)
        return ("var", v)
    raise ValueError("unexpected token %r" % (v,))

def parse(text):
    p = P(lex(text)); e = p_or(p)
    if p.i != len(p.t): raise ValueError("trailing tokens in %r" % text)
    return e

def int_lit(n):
    return n[0] == "lit" and re.fullmatch(r"\d+", n[1]) is not None

def count_int_divisions(n):
    """`<integer literal> / <integer literal>` -- the ONE construct on which
    MariaDB's DECIMAL division and IEEE double division disagree. Section 7.3."""
    if n[0] in ("+", "-", "*", "/", "%", "and", "or"):
        k = 1 if (n[0] == "/" and int_lit(n[1]) and int_lit(n[2])) else 0
        return k + count_int_divisions(n[1]) + count_int_divisions(n[2])
    if n[0] in ("neg", "not"): return count_int_divisions(n[1])
    if n[0] == "cmp": return count_int_divisions(n[2]) + count_int_divisions(n[3])
    if n[0] == "call": return sum(count_int_divisions(a) for a in n[2])
    return 0

def ev(n, env, litdiv="double"):
    t = n[0]
    if t == "lit": return float(n[1])
    if t == "var": return env(n[1])
    if t == "neg": return -ev(n[1], env, litdiv)
    if t == "not": return 0.0 if ev(n[1], env, litdiv) != 0.0 else 1.0
    if t in ("and", "or"):
        a = ev(n[1], env, litdiv) != 0.0; b = ev(n[2], env, litdiv) != 0.0
        return 1.0 if ((a and b) if t == "and" else (a or b)) else 0.0
    if t == "cmp":
        a, b = ev(n[2], env, litdiv), ev(n[3], env, litdiv)
        return 1.0 if {"=": a == b, "<>": a != b, "!=": a != b, "<": a < b,
                       "<=": a <= b, ">": a > b, ">=": a >= b}[n[1]] else 0.0
    if t in "+-*/%":
        a, b = ev(n[1], env, litdiv), ev(n[2], env, litdiv)
        if t == "+": return a + b
        if t == "-": return a - b
        if t == "*": return a * b
        if t == "%": return math.fmod(a, b) if b else float("nan")
        if litdiv == "decimal" and int_lit(n[1]) and int_lit(n[2]):
            # MariaDB rounds an exact-value division to div_precision_increment
            # (4) decimal places before promoting to DOUBLE.
            from decimal import Decimal, ROUND_HALF_UP
            return float((Decimal(n[1][1]) / Decimal(n[2][1]))
                         .quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        return a / b if b else float("nan")
    if t == "call":
        f = n[1]
        if f == "if":                       # MariaDB IF() is lazy
            return ev(n[2][1] if ev(n[2][0], env, litdiv) != 0.0 else n[2][2],
                      env, litdiv)
        a = [ev(x, env, litdiv) for x in n[2]]
        return {"pow": lambda: math.pow(a[0], a[1]),
                "power": lambda: math.pow(a[0], a[1]),
                "exp": lambda: math.exp(a[0]), "log": lambda: math.log(a[0]),
                "ln": lambda: math.log(a[0]), "sqrt": lambda: math.sqrt(a[0]),
                "abs": lambda: abs(a[0]), "least": lambda: min(a),
                "greatest": lambda: max(a)}[f]()
    raise ValueError("bad node %r" % (n,))

# ---- doGeneralFuelRatio ----------------------------------------------------
def general_fuel_ratio(snap, promote, litdiv):
    ge = table(snap, "generalfuelratioexpression")
    if not ge: return {}, 0
    sub2type = {r["fuelSubtypeID"]: r["fuelTypeID"] for r in table(snap, "fuelsubtype")}
    forms, by_type = {}, {}
    for r in table(snap, "fuelformulation"):
        v = {}
        for c in PROPS:
            x = float(r[c]) if r[c] is not None else 0.0
            v[c.lower()] = f32(x) if promote == "float" else x
        # `altRVP` is a column the Java ADDS to fuelFormulation in setup(); the
        # snapshot does not carry it. Only the derived Pseudo-THC expressions
        # read it, and every one of those is handed off, so no compared cell
        # depends on this (section 8.3).
        v["altrvp"] = 0.0
        forms[r["fuelFormulationID"]] = (r["fuelSubtypeID"], v)
    for fid, (sid, _) in sorted(forms.items()):
        if sid in sub2type: by_type.setdefault(sub2type[sid], []).append(fid)
    supplied = {r["fuelFormulationID"] for r in (table(snap, "fuelsupply") or [])}

    exprs = [dict(ft=r["fuelTypeID"], ppid=r["polProcessID"],
                  pol=r["polProcessID"] // 100, proc=r["polProcessID"] % 100,
                  miny=r["minModelYearID"], maxy=r["maxModelYearID"],
                  mina=r["minAgeID"], maxa=r["maxAgeID"], st=r["sourceTypeID"],
                  e=r["fuelEffectRatioExpression"],
                  g=r["fuelEffectRatioGPAExpression"], sub=None) for r in ge]
    for e in list(exprs):               # @step 050: the E85 Pseudo-THC copies
        if e["ft"] == 5 and e["pol"] == 1 and e["maxy"] >= 2001 and e["proc"] in (1, 2):
            n = dict(e)
            n.update(pol=10001, ppid=1000100 + e["proc"], sub=[51, 52],
                     miny=max(e["miny"], 2001),
                     e=e["e"].replace("RVP", "altRVP"),
                     g=e["g"].replace("RVP", "altRVP"))
            exprs.append(n)

    out, intdivs = {}, 0
    for ft in sorted({e["ft"] for e in exprs}):
        touse = [f for f in by_type.get(ft, []) if f in supplied]
        if not touse: continue
        for e in exprs:
            if e["ft"] != ft or e["miny"] > e["maxy"]: continue
            pe, pg = parse(e["e"] or "1"), parse(e["g"] or "1")
            intdivs += count_int_divisions(pe) + count_int_divisions(pg)
            for fid in touse:
                sid, v = forms[fid]
                if e["sub"] is not None and sid not in e["sub"]: continue
                key = (e["ft"], fid, e["ppid"], e["miny"], e["maxy"],
                       e["mina"], e["maxa"], e["st"])
                if key in out: continue      # per (formulation, polProcessID)
                env = lambda n: v[n.lower()]
                out[key] = (ev(pe, env, litdiv), ev(pg, env, litdiv))
    return out, intdivs

def handed_off_pairs(snap):
    """(fuelFormulationID, polProcessID) the uncovered predictive paths claim."""
    pairs = set()
    for t in ("criteriaratio", "altcriteriaratio", "atratio"):
        rows = table(snap, t) or []
        pairs |= {(r["fuelFormulationID"], r["polProcessID"]) for r in rows}
    return pairs

# ---- the sweep -------------------------------------------------------------
worst = {("float", "double"): 0.0, ("double", "double"): 0.0,
         ("float", "decimal"): 0.0}
worst_key = None
cells = missing = extra = unaccounted = 0
ran, idle, predicate_checked, predicate_wrong = [], [], 0, []
int_divisions = 0

for name in sorted(os.listdir(ROOT)):
    snap = os.path.join(ROOT, name)
    if path_of(snap, "generalfuelratioexpression") is None: continue

    # Did MOVES load the class? The execution trace answers that directly, so
    # the scheduling half of the claim never has to be inferred from an output.
    trace = os.path.join(snap, "execution-trace.json")
    if os.path.exists(trace):
        loaded = any("FuelEffectsGenerator" in c["name"]
                     for c in json.load(open(trace))["java_classes"])
        (ran if loaded else idle).append(name)
        xml = "%s/../fixtures/%s.xml" % (ROOT, name)
        rpp = table(snap, "runspecpollutantprocess")
        if os.path.exists(xml) and rpp is not None:
            predicate_checked += 1
            models = set(re.findall(r'<model value="(\w+)"', open(xml).read()))
            onroad = "ONROAD" in models or not models
            if (onroad and bool({r["polProcessID"] % 100 for r in rpp} & LOADS)) != loaded:
                predicate_wrong.append(name)
    else:
        loaded = False
    if not loaded: continue

    ref = {(r["fuelTypeID"], r["fuelFormulationID"], r["polProcessID"],
            r["minModelYearID"], r["maxModelYearID"], r["minAgeID"],
            r["maxAgeID"], r["sourceTypeID"]):
           (float(r["fuelEffectRatio"]), float(r["fuelEffectRatioGPA"]))
           for r in (table(snap, "generalfuelratio") or [])}

    got = {}
    for hyp in worst:
        got[hyp], n = general_fuel_ratio(snap, hyp[0], hyp[1])
        if hyp == ("float", "double"): int_divisions += n
    base = got[("float", "double")]

    missing += len(set(ref) - set(base))
    ex = set(base) - set(ref)
    extra += len(ex)
    # An extra is only acceptable if MOVES moved that row somewhere this port
    # does not follow it to: criteriaRatio or ATRatio, keyed the same way. The
    # derived Pseudo-THC rows are claimed under the THC polProcessID they came
    # from, which is the alias below.
    hand = handed_off_pairs(snap)
    for k in ex:
        ffid, ppid = k[1], k[2]
        alias = (ffid, 100 + ppid % 100) if ppid // 100 == 10001 else None
        if (ffid, ppid) not in hand and (alias is None or alias not in hand):
            unaccounted += 1

    for k in set(ref) & set(base):
        for hyp in worst:
            for r, g in zip(ref[k], got[hyp][k]):
                rel = abs(g - r) / abs(r) if r else abs(g - r)
                if rel > worst[hyp]:
                    worst[hyp] = rel
                    if hyp == ("float", "double"): worst_key = (name,) + k
        cells += 2

print("generalFuelRatioExpression: %d snapshots carry it; MOVES loaded the "
      "generator in %d and not in %d" % (len(ran) + len(idle), len(ran), len(idle)))
print("               %d rows compared, %d cells, %d missing / %d extra keys, "
      "%d extras unaccounted for" % (cells // 2, cells, missing, extra, unaccounted))
# `worst_key` is None exactly when NOTHING beat 0.0 -- which under
# `moves-snapshot/v2` is the answer: the FLOAT-promoted hypothesis is
# bit-identical to the reference on every compared cell, where v1's twelve
# decimal places left a 1.608e-14 residual that was the CAPTURE's and not the
# arithmetic's. Say that instead of subscripting None.
if worst_key is None:
    print("               worst relative error 0.000e+00 -- BIT-IDENTICAL on "
          "every compared cell")
else:
    print("               worst relative error %.3e at %s fuel %d formulation %d "
          "polProcess %d sourceType %d"
          % (worst[("float", "double")], worst_key[0], worst_key[1], worst_key[2],
             worst_key[3], worst_key[8]))
print("subscription:  %d snapshots checked against ONROAD x processes "
      "{1,2,9,10,11,12,13,90}; %d disagree" % (predicate_checked, len(predicate_wrong)))
print("FLOAT columns: promoting binary32 gives %.3e, reading the capture's "
      "decimal straight gives %.3e"
      % (worst[("float", "double")], worst[("double", "double")]))
print("int/int:       %d integer-literal divisions in the corpus's expressions; "
      "DECIMAL rounding gives %.3e against IEEE's %.3e"
      % (int_divisions, worst[("float", "decimal")], worst[("float", "double")]))

# ASSERTED, not merely printed (docs/esm-conventions.md 21): run-tests.sh reads
# this script's EXIT CODE.
# A FLOOR, not an equality -- the corpus is shared and it grows (35.5).
assert cells >= 194, cells
assert (missing, unaccounted) == (0, 0), (missing, unaccounted)
assert worst[("float", "double")] < 1e-12, \
    "worst relative error %.3e exceeds 1e-12" % worst[("float", "double")]
assert not predicate_wrong, predicate_wrong
# The FLOAT question is decided here and nowhere else: 7.06e-08 is INSIDE
# tolerance.toml's per-cell 2e-5, so no fixture comparison could see it.
#
# A RATIO WOULD NOT DO IT ANY MORE. Under v1 the FLOAT hypothesis left a
# 1.608e-14 residual and `> 1e3 x` was a real separation; under v2 it leaves
# ZERO, and `> 1e3 x 0` is satisfied by any positive number at all -- a gate
# that reads as a comparison and tests nothing. So the two ends are asserted
# separately and absolutely: the wrong promotion must miss by a margin the
# capture cannot explain, and the right one must land inside f64 noise.
assert worst[("double", "double")] > 1e-9, \
    "the two promotions are not distinguishable: reading the capture's decimal " \
    "straight is within %.3e, so this corpus no longer decides the FLOAT " \
    "question" % worst[("double", "double")]
assert worst[("float", "double")] < 1e-13, worst[("float", "double")]
# The int/int question is NOT decided here, and these two assertions say so
# rather than leaving a reader to assume it was: the corpus holds no such
# division, so the two candidates are bit-identical on every compared cell. If
# a capture ever adds one, this goes red and the question becomes answerable --
# which is the point of asserting it.
assert int_divisions == 0, int_divisions
assert worst[("float", "decimal")] == worst[("float", "double")], \
    "DECIMAL and IEEE division disagree -- the corpus can now decide section 7.3"
```

Result:

```
generalFuelRatioExpression: 42 snapshots carry it; MOVES loaded the generator in 24 and not in 18
               97 rows compared, 194 cells, 0 missing / 1015 extra keys, 0 extras unaccounted for
               worst relative error 0.000e+00 -- BIT-IDENTICAL on every compared cell
subscription:  42 snapshots checked against ONROAD x processes {1,2,9,10,11,12,13,90}; 0 disagree
FLOAT columns: promoting binary32 gives 0.000e+00, reading the capture's decimal straight gives 7.059e-08
int/int:       0 integer-literal divisions in the corpus's expressions; DECIMAL rounding gives 0.000e+00 against IEEE's 0.000e+00
```

**Two of those numbers are dated and the rest are not**, and §7.5 is why knowing
which is which matters. The 42, the 24/18 split and the 1,015 move whenever the
corpus grows. The 97 rows, the 194 cells, the 0 missing and 0 unaccounted, the
bit-identity and the predicate's `0 disagree` are per-snapshot invariants that
any new capture has to satisfy on its own terms. **The residual itself was
dated and nobody knew it**: it was 1.608e−14 for as long as the capture wrote
twelve decimal places, and 0 the moment it stopped — see §7.1.

### 6.6 What the component's inline tests check

`components/fuel_effects.esm` carries 43 assertions in eight tests.

| test | faces | what breaks if it is wrong |
|---|---|---|
| `the_property_join_delivers_the_expressions_own_formulation` | the port | dropping either half of J-FE-3/J-FE-4 gives 9.5 instead of 3.5 vol% of ester and a 4.8% ratio error that looks like a plausible biodiesel penalty |
| `the_term_set_join_sums_the_right_coefficients…` | the port | dropping J-FE-1 sums all twelve coefficients into every expression, 94× too small and still finite |
| `the_log_linear_form_reproduces_the_reference_pm_ratio` | **MOVES** | the `FLOAT` promotion (§7.2), the missing normalisation, an uncentred property |
| `the_biodiesel_form_reproduces_all_four_reference_coefficients` | **MOVES** | the coefficient not travelling with the polProcessID; a ratio clamped at 1 |
| `the_ethanol_clamp_is_ported_and_the_corpus_cannot_see_it` | the port | §8.2 |
| `the_sulfur_switch_takes_both_arms…` | the port | §8.1 |
| `the_unselected_arms_stay_finite…` | the port | a NaN in a discarded `ifelse` arm, whose propagation is evaluator-dependent |
| `every_expression_is_evaluated_against_a_formulation_of_its_own_fuel_type` | the port | a cross-fuel-type evaluation returns exactly 1, which MOVES then deletes — a MISSING row rather than a wrong one, which is why the oracle asserts 0 missing keys and not only a tolerance |

Nine of the twelve expression rows carry an assertion against the snapshot's own
`fuelEffectRatio`; three are probes and their tests say so in the test, not only
here (`docs/esm-conventions.md` §35.4).

---

## 7. Fidelity notes and tolerance

### 7.1 The measured result

All 97 rows of the corpus's populated `generalFuelRatio` — 194 cells, from
`process-pm-exhaust` (58) and `process-crankcase-running` (39) — **bit-identical**
to the reference, 0 missing keys, and 1,015 extra keys every one of which
`criteriaRatio`, `altCriteriaRatio` or `ATRatio` claims by the same
`(fuelFormulationID, polProcessID)`.

**It was 1.608 × 10⁻¹⁴, and that residual was the CAPTURE's.** This section used
to explain it as the reference column's own resolution — `fuelEffectRatio` read
as a `DECIMAL(20,12)`, about 4.6e−13 relative on a ratio near 1 — and that
explanation was wrong. `moves-snapshot/v1` wrote every float at twelve DECIMAL
places, so a stored 1.090910749585 was indistinguishable from a
`DECIMAL(20,12)` column holding the same string. `moves-snapshot/v2` records
1.0909107495849824 and the residual goes to exactly **zero**, which no column
type could have allowed: a `DECIMAL(20,12)` cannot hold that number.

So this port's arithmetic is not *measurably indistinguishable* from MOVES's on
these cells — it is **identical**, and the only reason that could not be said
before is the format the reference was written in.

### 7.2 The `FLOAT` columns, decided by measurement

`FuelFormulation`'s property columns are MariaDB `FLOAT` — 32-bit. MOVES reads
them into a `DOUBLE` expression, so the value that enters the arithmetic is a
binary32 widened. **The snapshot capture prints the decimal, not the float**:
it stores `aromaticContent` as `23.140000000000`, and MOVES computed with
23.139999389648438.

Running the corpus both ways:

| what a property value is taken to be | worst relative error over 194 cells |
|---|---|
| the `FLOAT` widened — `float32(23.14)` | **0.000e+00** (bit-identical) |
| the capture's decimal text read as a double | **7.059e−08** |

One is exact and the other misses by 7 × 10⁻⁸, so the corpus decides it as
cleanly as a corpus can. Under v1 these read 1.608e−14 and 7.059e−08 and the
test was a RATIO — 4,400× apart. That form does not survive an exact answer:
`> 1e3 ×` of zero is any positive number at all. §6.5 now asserts the two ends
absolutely instead, which is the general lesson — a separation stated as a
ratio stops testing anything the moment the good hypothesis becomes exact.

**But note what would have missed it.** 7.059e−08 is comfortably inside
`tolerance.toml`'s per-cell `rel = 2e-5`. A fixture comparison — the mechanism
every other rung in this repository is checked by — would have passed with the
wrong promotion and reported nothing. That makes this a different case from
`docs/meteorology-generator.md` §7.2, where the wrong candidate was seven times
**outside** the fixture gate. The rule that comes out of the pair is
`docs/esm-conventions.md` §38.

### 7.3 The integer-literal division: **not decidable here, and that is the answer**

`../moves.rs`'s `fueleffectsgenerator/expression.rs` carries an explicit open
question, left over from the `(5/9)` investigation that
`docs/meteorology-generator.md` §7.2 settled:

> MariaDB rounds an integer/integer division such as `(5/9)` to a `DECIMAL`
> before promoting to `DOUBLE` (`0.5556`, not `0.55555…`). This evaluator
> divides in plain `f64`. A `fuelEffectRatioExpression` that divides two
> integer *literals* would diverge by ~1e-4 … Whether a
> `fuelEffectRatioExpression` dividing two integer literals behaves the same way
> is a separate and still-open question — the corpus holds 58 such expressions
> and none has been compared.

**The measurement: the corpus holds ZERO such expressions.** Parsing all 118
distinct `fuelEffectRatioExpression` / `fuelEffectRatioGPAExpression` strings
and counting every `/` node whose two operands are both integer literals gives
**0**. The 58 in the upstream note is the row count of `generalFuelRatio` in
`process-pm-exhaust`, not a count of integer divisions.

The only integer denominator anywhere in the corpus is the `100` in
`least(bioDieselEsterVolume, 20)/100`, and its numerator is a `least()` over a
`FLOAT` column — a `DOUBLE` in MariaDB, which makes the division a `DOUBLE`
division and takes it out of the exact-value path entirely.

So the two hypotheses are **observationally identical on this corpus**, and the
residuals for both are the same number rather than merely close:

| hypothesis for `<int literal> / <int literal>` | worst relative error over 194 cells |
|---|---|
| IEEE binary64 division | 0.000e+00 |
| MariaDB `DECIMAL`, rounded to `div_precision_increment` = 4 | 0.000e+00 |

Bit-identical, because no expression exercises the difference. **This is not a
finding that MOVES divides one way or the other. It is a finding that the
question cannot be asked of this corpus**, and §6.5 asserts both halves of that
— `int_divisions == 0` and the two residuals equal — so that the day a capture
adds such an expression the oracle goes red and the question becomes answerable
instead of quietly staying answered wrong. `docs/esm-conventions.md` §38.

### 7.4 Precision-sensitive operations, ranked

1. **The `FLOAT` promotion** — 7.06e−08 if skipped (§7.2). The largest effect
   this port has a choice about.
2. **The order of the polynomial's terms.** MOVES writes the same coefficients
   in different orders on different rows and sums them left to right; this port
   sums over an axis in an order the evaluator chooses. Both are the same
   mathematical sum and differ in the last ulps; the effect is under 1e−15 on
   the exponent and is amplified by `exp` by a factor of about 1 near these
   values. It is inside the measured residual and cannot be separated from it.
3. **`exp(g·ln(x))` against `pow(x, g)`** — form C only, and form C is not
   checked against MOVES, so this is unmeasured here. Kept in the SQL's spelling
   rather than decided (§4).
4. ~~**The reference column's `DECIMAL(20,12)` storage**~~ — **retired, and it
   was never real.** The 4.6e−13 floor this item claimed was
   `moves-snapshot/v1`'s twelve decimal places wearing a column type's name.
   With v2 the comparison is bit-identical, so there is no storage floor here
   at all and the oracle's gate is 1e−13 as an f64-noise guard rather than as a
   storage allowance.

### 7.5 The corpus grew by two snapshots while this rung was being verified

`docs/esm-conventions.md` §35.5 records that the snapshot directory is shared,
mutable state and that an oracle over it must assert the invariant that only
breaks in the direction it cares about. This rung is the second instance and it
happened inside a single session: the corpus was 40 snapshots carrying
`generalFuelRatioExpression` when §6.5 was written and 42 when the suite next
ran, because `chain-so2-co2e-mechanism` and its `-control` twin landed on
`moves.rs` main in between.

What that moved, and what it did not:

| | before | after |
|---|---:|---:|
| snapshots carrying the table | 40 | 42 |
| snapshots that loaded the generator | 22 | 24 |
| expression-table rows | 1,744 | 2,078 |
| distinct expression strings | 116 | 118 |
| distinct parse-tree skeletons | 70 | 72 |
| **distinct algebraic forms** | **6** | **6** |
| rows the port computes | 766 | 1,112 |
| extra keys, all accounted for | 669 | 1,015 |
| **rows compared against MOVES** | **97** | **97** |
| **cells** | **194** | **194** |
| **worst relative error** | **1.608e−14** | **1.608e−14** *(both under `moves-snapshot/v1`; 0 under v2 — see §7.1)* |
| **missing / unaccounted keys** | **0 / 0** | **0 / 0** |
| **snapshots disagreeing with the predicate** | **0** | **0** |

Every count that describes the *corpus* moved by 15 to 20 %. Every count that
describes the *model* did not move at all, and the oracle stayed green through
the change without a line being edited — because its cell-count assertion is a
floor, its key-set and predicate assertions are per-snapshot, and its two
fidelity assertions are about ratios between candidates rather than about
absolute counts.

**The bolded rows are the ones this specification is really claiming.** The
others are dated, and this section is the date.

---

## 8. Gaps and things not verified

### 8.1 Three of the six forms are ported and unverifiable, and three are not ported

MOVES's `doGeneralFuelRatio` computes a ratio for **every** expression row, and
then the predictive/complex-model paths this port does not cover take most of
them away. `doCOCalculations`, `doHCCalculations` and `doNOxCalculations` call
`copyGeneralFuelRatioToCriteriaRatio`, which copies polProcessIDs 101, 102, 201,
202, 301 and 302 into `criteriaRatio` and deletes them from `generalFuelRatio`;
`doAirToxicsCalculations` does the same to `ATRatio` for the air-toxic
polProcessIDs.

Measured: the port computes **1,112** rows over the 24 snapshots that ran the
generator, MOVES keeps **97** of them, and all **1,015** of the difference are
claimed by `criteriaRatio`, `altCriteriaRatio` or `ATRatio` under the same
`(fuelFormulationID, polProcessID)`. That is the oracle's `unaccounted == 0`
assertion, and it is what makes 1,015 extra keys evidence rather than a failure.

What follows for the port:

* **Form C is ported and no assertion anywhere faces MOVES on it.** 1,013 of
  the corpus's 2,078 expression rows, 100 of its 118 strings — the dominant
  form —
  and every one of its rows goes to `criteriaRatio` before capture. It is
  ported because a later `criteriaRatio` rung needs exactly this algebra, and
  because `components/fuel_effects.esm`'s two probes at least establish that
  the factoring into templates reproduces §6.5's independent evaluation of the
  same string. Two implementations of one text agreeing is evidence about the
  port; it is not evidence about MOVES.
* **Forms D, E and F are not ported.** 273 rows and 10 strings between them,
  across four snapshots: `process-airtoxics` and the two
  `chain-so2-co2e-mechanism*` captures, where every one of their rows is handed
  to `ATRatio`, and `nr-airtoxics-lawn-garden-county`, a NONROAD snapshot where
  the generator never runs. They are
  the olefin quadratic, the benzene linear and the three-`exp` complex-model
  ratio of §2.1. A later air-toxics rung should port them together with the
  `ATRatio` path that consumes them, where they can be checked.
* **The `already_ratioed` de-duplication is ported and unexercised.** No
  `(fuelFormulationID, polProcessID)` in the corpus is reached by two
  expressions, so the "first expression wins" rule is never the thing that
  decides an answer.

### 8.2 What the corpus cannot see, measured rather than assumed

`docs/esm-conventions.md` §23's rule: perturb the input and check whether any
compared cell moves.

| construct | occurrences | can any compared cell see it? |
|---|---|---|
| the E85 `least(10, ETOHVolume)` clamp | 29 of the 118 strings — 1 of 2 in form A, 25 of 100 in form C, 3 of 6 in form F | **no.** The only E85 formulation any corpus fuel supply carries is 27002, whose `ETOHVolume` is exactly 10.0, so the clamp is the identity on all 194 cells and deleting it leaves the comparison bit-identical. Probed instead: §6.4 |
| the biodiesel `least(…, 20)` clamp | all 4 form-B strings | **no.** 3.5 vol% is the only ester volume any supplied formulation carries |
| the `minModelYearID > maxModelYearID` empty-window skip | 0 rows | **no.** No corpus row has an inverted window |
| the `fuelSubtypes in (51, 52)` restriction on Pseudo-THC | all derived rows | **no.** Every derived row is handed off (§8.3) |
| the `sourceTypeID` column | 13 values in `process-crankcase-running`, 3 for fuel type 5 in `process-pm-exhaust` | **yes**, as a key — it multiplies rows without changing the ratio, so it is checked by the key-set assertion and by nothing else |

### 8.3 `altRVP` is a column nobody here has

The Pseudo-THC derivation rewrites `RVP` to `altRVP` in both expression strings,
and `altRVP` is a column the Java adds to `FuelFormulation` in `setup()` from a
source the snapshot does not capture. `../moves.rs` defaults it to 0.0; §6.5
does the same and says so at the line that does it.

**Nothing rests on the choice.** Every derived Pseudo-THC row in the corpus —
polProcessIDs 1000101 and 1000102, 48 rows across seven snapshots — is handed off
under the THC polProcessID it was derived from, so not one of them reaches a
compared cell. If a later rung needs the Pseudo-THC ratio itself, `altRVP` is
the first thing it has to find, and 0.0 is a placeholder rather than an answer.

### 8.4 What the generator does that this port does not

`FuelEffectsGenerator.java` is 4,435 lines and `doGeneralFuelRatio` is one of
them. The predictive/complex-model paths — `doAirToxicsCalculations`,
`doCOCalculations`, `doHCCalculations`, `doNOxCalculations`,
`doMTBECalculations` and their siblings — need the MOVES complex-model
expression engine and a dozen further default-database tables, and they write
`ATRatio`, `criteriaRatio`, `altCriteriaRatio` and `MTBERatio`. None of that is
here. `../moves.rs`'s port draws the same line and for the same reason.

Two `static` string helpers are ported in `../moves.rs` (`getCSV`,
`getPolProcessIDsNotAlreadyDone`) and one is not needed here at all
(`rewriteCmpExpressionToIncludeStdDev`, which belongs to the complex-model
path). They are SQL-string plumbing, not model arithmetic, and
`docs/esm-conventions.md` §1 puts them outside a `.esm` document.

---

## 9. Summary for the `.esm` author

* One template library, `lib/fuel_effects.esm`: eleven templates and six
  constants, covering three of the table's six algebraic forms.
* One component, `components/fuel_effects.esm`: four relations — five
  formulations, thirty-five property values, twelve expression instances,
  twelve coefficient rows — and 43 assertions in eight tests. **13** compare
  against the snapshot's own `generalFuelRatio.fuelEffectRatio`; **14** pin
  values read from the snapshot's `fuelFormulation` and
  `generalFuelRatioExpression` columns; the remaining **16** face this port and
  §6.5's second implementation, and every one of their tests says so
  (`docs/esm-conventions.md` §35.4).
* No fixture. `generalFuelRatio` is an execution-database table and
  `docs/esm-conventions.md` §35.1 keeps generators out of `fixtures/`; the
  row-by-row half is §6.5 and `./run-fuel-effects-oracle.sh`.
* The two questions this rung settles: the `FLOAT` promotion, **decided**
  (§7.2), and the integer-literal division, **shown not to be decidable here**
  (§7.3). Both are asserted rather than described.
