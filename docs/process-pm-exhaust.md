# `process-pm-exhaust` — computation specification

The port specification for the first fixture with **no unchained parent block**,
written to the method of `docs/process-brakewear.md`: the input inventory
determined from evidence, the chain with source lines into `../moves.rs`, every
join with its exact key pairs, and worked examples whose numbers can be checked
by hand.

Every rung since `process-nox-speciation` has been a 248-row parent computed off
a rate table plus *N* × 208 species blocks that fall out of it by ratio.
**`process-pm-exhaust` has seven 208-row blocks and no 248-row parent at all.**
That is not a cosmetic difference:

1. **Two of the seven blocks ARE the parents**, and they are 208 rows for the
   same reason the species blocks are — the twenty electricity cohorts reach
   `SulfatePMCalculator`'s working table and are dropped there, by an inner
   join, one stage after the rate. The rate relation carries 124 cohorts; no
   emitted block does. §2.7.
2. **The parent is a PAIR.** `emissionratebyage` carries 11201 (unadjusted
   elemental carbon) and 11801 (composite non-EC particulate) and nothing else,
   and five of the seven emitted pollutants are functions of *both*. A
   single-parent chain cannot express PM2.5 total = EC + NonECPM.
3. **MOVES's own chain table is CYCLIC here.** `runspecchainedto` says
   11801 ← 11501 *and* 11501 ← 11801, because `SulfatePMCalculator` splits
   NonECPM into species and then re-sums NonECPM from them. The chain-root
   iteration `docs/esm-conventions.md` §32.1 introduced for
   `process-airtoxics` does not terminate on this table, so the stages are
   written the way `sulfate_pm_calculator.rs` writes them and the chain
   declaration is read for nothing but its row set. §2.8.
4. **The `criteriaratio` fuel effect is gone and `generalfuelratio` is back** —
   the reverse of `process-airtoxics`, where `generalfuelratio` was the empty
   one. And `generalfuelratio`'s two pollutants enter at **different stages**:
   the elemental-carbon rows at `BaseRateCalculator`, the residue rows inside
   `SulfatePMCalculator`. Applying both in one place squares a 1.0909 on every
   gasoline and E85 cohort. §2.3 and §2.5.3.

**The rung-6 cross-check is NOT available, and that was checked rather than
assumed.** `process-airtoxics` opened by observing that its THC parent block was
byte-identical to `process-crankcase-running`'s `(1, 1)` block. Compared against
every one of the **31** snapshots that carry a non-empty `MOVESOutput` — 51
RunSpec fixtures are on disk, 39 have a snapshot directory, and 8 of those emit
no rows at all — **no block of this snapshot is byte-identical to, or a constant
multiple of, any block of any other**, so nothing here is checked by having been
computed before.

That corpus figure is stated exactly because getting it wrong is the failure
mode. A first pass at this comparison globbed `db__out_*__movesoutput.parquet`
and read **30** snapshots, silently skipping `sample-runspec`, whose output
database is `JUnitTestOutput` and whose file the capture tool therefore names
`db__junittestoutput__movesoutput.parquet` — the same defect commit `1568548`
fixed in `tools/calculator-coverage.py --ladder`. The scan was re-run through
that tool's own `output_path()`, which lowercases the provenance name and then
globs, so a future naming change fails loudly rather than subtracting a
snapshot. **A negative result is only as wide as the corpus it was taken over**,
and this one is now taken over all 31.

What *is* shared is one level down: this snapshot's `sho` table is
**byte-identical** — 82 rows, same `(hourDayID, ageID)` keys, same decimal text
— to the `sho` of **13** other snapshots with a non-empty `MOVESOutput`, eight of
them already ported (`process-airtoxics`, `process-nox-speciation`,
`process-crankcase-running`, `process-brakewear`, `process-tirewear`,
`process-refueling`, `process-evap-fvv`, `process-evap-leaks`) and the rest not
(`chain-nonhaptog`, `chain-tog-speciation`, `expand-criteria`, `expand-day`,
`process-evap-permeation`). So the activity half S1–S9 is literally the same 82
numbers those rungs already verified. §7.1 says what each of the three
checkpoints buys.

---

## 0. The fixture at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/process-pm-exhaust.xml` |
| Model | ONROAD, `modelscale` `Inv` (inventory), `modeldomain` `DEFAULT` |
| Geography | county 26161 (Washtenaw, Michigan), zone 261610, link 2616104 |
| Time | year 2020, month **8**, hour **7**, day types **2 (weekend) and 5 (weekday)** |
| Vehicles | sourceTypeID 21 (passenger car); fuel types **1, 2, 5, 9** selected, **1, 2, 5** emitted |
| Road | roadTypeID 4 (urban restricted access) |
| Pollutant/process | seven, all on Running Exhaust: **11201** (elemental carbon) and **11801** (composite NonECPM) are rated; **11501** (sulfate), **11901** (H2O aerosol), **11101** (organic carbon), **11001** (PM2.5 total) and **10001** (PM10 total) are computed from them |
| Model years | 1980–2020 (41) |
| Output | `db__out_process_pm_exhaust__movesoutput`, **1,456 rows** |
| Output units | **grams** for all seven pollutants; `outputtimestep` **Hour** |
| Calculator path | `TotalActivityGenerator` → `SourceBinDistributionGenerator` → `BaseRateGenerator` → `BaseRateCalculator` → **`SulfatePMCalculator`**, **`PM10EmissionCalculator`** → output aggregation |
| Snapshot | 360 tables, **228 non-empty** |

### 0.1 The RunSpec on disk does not describe the captured run

The same rule as `docs/mixed-onroad.md` §0.1 and `docs/process-airtoxics.md`
§0.1, and for the same reason: the XML's `<month key>`, `<beginhour key>` and
`<day key>` are canonical `RunSpecXML` **0-based indices into sorted ID lists**,
not identifiers. The execution database's `runspecmonth`, `runspechour` and
`runspecday` say month 8, hour 7 and day types 2 **and** 5, and
`runspecpollutantprocess` says 10001, 11001, 11101, 11201, 11501, 11801 and
11901. The execution database is the authority.

### 0.2 Why 1,456 rows, and why every block is the same size

1,456 = 7 pollutants × 104 cohorts × 2 day types, and **all seven blocks carry
the same 104 cohorts** — which is the one thing that makes this fixture's key
set easier than `process-airtoxics`' and its *cause* harder.

| | rated (112, 118) | derived (100, 110, 111, 115, 119) |
|---|---|---|
| gasoline (1) | 41 model years, 1980–2020 | 41 |
| diesel (2) | 40, 1980–2019 | 40 |
| E85 (5) | 23, 1998–2020 | 23 |
| electricity (9) | **none emitted** | **none** |
| cohorts | **104** | **104** |

Three separate facts stack up behind that table, and only the first is shared
with the earlier rungs:

* **125 of the 164 (model year, fuel type) candidates pass `stmyFraction > 0`**,
  and the one that is selected and carries no rate is **model year 2000,
  electricity** — the same cohort `process-nox-speciation` and
  `process-airtoxics` lose, **for a different reason**, which is worth being
  exact about because the inherited explanation is wrong here. Those fixtures
  lost it on the **age group**: pollutant 101's fuel-type-9 rows stop at age
  group 1519 and model year 2000 is aged 20, so it needed the missing 2099.
  Here `emissionratebyage` carries **all seven age groups for fuel type 9**, on
  both 11201 and 11801, and the miss is on the **short model-year group**
  instead: the fuel-9 / engTech-30 / regClass-20 source bins run over short
  groups 8, 10–19, 21–50, 53, 55, 57–60 and 66–69, and **20 is absent** —
  which is precisely the group `pollutantprocessmodelyear` assigns model year
  2000. Enumerated over both rated pollutant-processes and all 125 candidates,
  `(2000, fuel 9)` is the **only** miss, and it leaves **124** rated cohorts.
  A row-set consequence of a rate KEY either way (`docs/esm-conventions.md`
  §30.1), but of a different key.
* **`baseratebyage_1_2020` is 496 rows = 2 pollutant-processes × 124 × 2
  hour-day ids, of which 416 are non-zero**: the 20 electricity cohorts carry a
  real rate of exactly `0.000000000000` in both blocks, exactly as model years
  2001–2020 electricity did for THC and NOx.
* **Those twenty die one stage later, inside `SulfatePMCalculator`, and they die
  twice.** `sulfatefractions` carries no fuel-type-9 row, so the NonECPM split's
  inner join drops them; `crankcaseemissionratio` carries no fuel-type-9 row
  either, so the crankcase-split inner join drops the copied EC rows as well.
  **Either miss alone would suffice**, which is why §2.7 resolves survival as a
  conjunction of the two rather than attributing it to one.

`sbweightedemissionratebyage` is 5,704 rows = 2 × 23 operating modes × 124, the
same 124 arrived at by a route this document reads (§7.1) — `process-airtoxics`
named that table and did not.

---

## 1. Input inventory

### 1.1 The tables the parent already reads

The activity chain (S1–S9), the cohort structure and the fuel-usage rebase
(S10–S12), the drive-cycle operating-mode weights, the age-group-keyed rate out
of `emissionratebyage` and the fuel-supply resolution are all
`docs/process-crankcase-running.md` §§1.2, 2.2–2.3 and are not restated. Read
`docs/mixed-onroad.md` §§1–3 for the activity half and
`docs/process-nox-speciation.md` §§2.2–2.3 for the rate half.

### 1.2 The six tables this fixture adds

| table | rows | role |
|---|---:|---|
| `sulfatefractions` | 6 | the base sulfate and water fractions of NonECPM, the base fuel's sulfur level and the sensitivity to it, per (process, fuel type, source type, model-year band) (§2.5.1) |
| `crankcaseemissionratio` | 572 | the crankcase split, keyed by `polProcessID` = species × 100 + process, fuel type, source type, regClass and a model-year band (§2.5.4) |
| `pmspeciation` | 4 | the residue-to-organic-carbon fraction, keyed by (process, input pollutant, source type, fuel type, model-year band) (§2.5.5) |
| `pm10emissionratio` | 4 | `PM10PM25Ratio`, the whole of `PM10EmissionCalculator` (§2.6) |
| `generalfuelratio` | 58 | **now populated** (0 rows in `process-airtoxics`): the fuel effect, on pollutants 112 and 120 only, applied at two different stages (§2.3, §2.5.3) |
| `runspecchainedto` | 8 | MOVES's chain declaration, read for its ROW SET and not as a computation graph, because it is cyclic (§2.8) |

Three tables the earlier rungs read are **gone**. `criteriaratio` has **0 rows**
here (733 in `process-airtoxics`), `fullacadjustment` has **0** (23), and
`fleetavgadjustment` has **0** (9). `temperatureadjustment` has 0 rows, as it
did in `process-airtoxics`. §2.3, §2.4 and §7.2 say what each costs.

### 1.3 What is NOT an input

`emissionrate` (0 rows here), `baseratebyage_1_2020`, `baserateoutput`,
`sbweightedemissionratebyage`, `sourcebindistribution`, `sho` and `MOVESOutput`
are generator or expected output. None is a `data_sources` entry. Values out of
the first, third, fifth and sixth appear as `expected` in the inline tests,
which is the opposite direction.

**`SulfatePMCalculator` has a long tail of species this run does not reach, and
they are dead by measurement rather than by claim.** `pmspeciation` has four
rows, every one of them `inputPollutantID` 120 → `outputPollutantID` 111, so the
eleven trace metals and ions (35, 36, 51–59) and NCOM (122) are produced by
nothing. Total Organic Matter (123) and NonECNonSO4NonOM (124) are gated on
`output_pol_processes` — the RunSpec's own pollutant-process list — and neither
is in it, so `sum_to_pollutant(TOM)` and `compute_non_ec_non_so4_non_om` are both
dead. §7.2 names them.

**`PM10EmissionCalculator`'s other three pollutant pairs are dead in MOVES
itself, not just here.** `PM10EmissionCalculator.java` carries commented-out
branches for organic-carbon (101 ← 111), elemental-carbon (102 ← 112) and
sulfate (105 ← 115) PM10; `sourcePollutantIDs` is only ever `"110"`, so the
SQL's `mwo.pollutantID IN (…)` admits Total PM2.5 alone. `../moves.rs`'s
`pm10.rs` ports the live `110 → 100` pair only, and so does this document.

**`atbaseemissions`, `atratio`, `hcspeciation` and `methanethcratio` are all 0
rows here**, which is the mirror image of `process-airtoxics` §1.3's
observation: a populated table is not an input, and an empty one is not
evidence of anything either. What decides is whether a column reaches
`emissionQuant`.

---

## 2. The computation chain

### 2.1 What is unchanged

S1–S18 of `docs/process-crankcase-running.md` for the two rated blocks. The rate
relation is the run's **seven** pollutant-processes crossed with the 41 × 4
cohort candidate grid, 1,148 rows, every factor a discovered extent; every rate
column is read back through `rt_polProcOrdinal` / `rt_cohortOrdinal`
(`docs/esm-conventions.md` §27.1). Five of the seven pollutant-processes have no
`emissionratebyage` row at all, so `rt_hasRate` is 0 on 820 of the 1,148 and the
rate arm contributes nothing to them — the same "a chained block's own rate path
evaluates to exactly 0" that `process-brakewear` established.

### 2.2 The parents are a PAIR, and both are emitted

`sulfate_pm_calculator.rs` names its two inputs as constants — `EC_POLLUTANT`
112 and `NON_EC_PM_POLLUTANT` 118 — and `BaseRateCalculator` produces both. So
the rate half of this fixture is `docs/process-nox-speciation.md` §§2.2–2.3 run
**twice**, once per `polProcessID`, over one rate relation that carries the
pollutant-process as a column.

Nothing about the rate lookup changes between them: both are `emissionratebyage`
rows at the same seven key pairs (fuel type, engine tech, regClass, short
model-year group, operating mode, age group and the pollutant-process itself),
both are collapsed against the same drive-cycle weights `W`, and both are
multiplied by the same activity. `sourcetypepolprocess` carries exactly two
rows, 11201 and 11801, both with `isRegClassReqd = Y` and `isMYGroupReqd = Y`,
so the source-bin key is the same shape for both as well.

### 2.3 The base-rate fuel effect is `generalfuelratio`, not `criteriaratio`

`criteriaratio` has **0 rows** in this snapshot, so `adjust.rs:477`'s criteria
arm is skipped entirely and the running-exhaust fuel effect every onroad rung
since `process-nox-speciation` carried is simply absent. What is live instead is
the arm immediately above it, `adjust.rs:452–472`:

```
r = fuelEffectRatio + GPAFract x (fuelEffectRatioGPA - fuelEffectRatio)
```

looked up on `(fuelFormulationID, polProcessID, sourceTypeID)` with an inclusive
model-year band **and** an inclusive age band. Two consequences the document has
to honour:

* **It keys on the fuel FORMULATION**, so it lives on the (rate row × supplied
  formulation) relation `criteriaratio` established in `process-airtoxics` §2.3,
  and the market-share collapse happens after it. The relation survives even
  though the table that motivated it is gone.
* **It keys on `polProcessID`, and the table carries 11201 and 12001 only.** So
  the elemental-carbon base rate is scaled by 1.090911 on gasoline and E85 of
  model year 2001 or later and by 0.9727 on diesel of model year 2006 or
  earlier, and the NonECPM base rate is scaled by nothing at all. The 12001 rows
  are not a base-rate lookup: pollutant 120 is internal to
  `SulfatePMCalculator` and never reaches `BaseRateCalculator`. §2.5.3 is where
  they are applied.

`GPAFract` is 0 in Washtenaw County, so the blend selects the normal arm — which
is exactly why it has to be written rather than assumed
(`lib/adjustments.esm`'s `gpa_blend`, and `docs/process-nox-speciation.md`
§2.3).

### 2.4 The temperature arm is the PM one, and it is the live branch

`general_temp_adjust` (`adjust.rs:87–142`) is four branches on the row's
process and pollutant, and **pollutant 112 or 118 on process 1 or 2 takes the
first one** (`adjust.rs:105–110`):

```
factor = exp(A x (72 - T))     if T <= 72
       = 1                     if T >  72
```

Three things worth separating, because a reader who checks only the answer
cannot:

* It is **multiplicative in an exponential**, not the additive quadratic every
  earlier onroad rung took. `process-airtoxics` §2.2 reached the fall-through
  arm precisely because pollutant 1 "is not 118/112 (PM)"; this fixture is the
  other side of that sentence.
* The run is at **59.5 °F**, so the `T <= 72` branch is the LIVE one. The 72 °F
  ceiling is not what makes the factor 1.
* What makes it 1 is that **`temperatureadjustment` has 0 rows**, so both the
  exact-regClass and the regClass-0 wildcard lookups miss and the additive
  identity gives `A = 0`. `exp(0) = 1` on all 1,148 rate rows.

The two-step wildcard precedence is still written — `lib/adjustments.esm`'s
`exact_else_wildcard`, which `mixed-onroad` §7 demonstrably needed — and the PM
exponential is written as `lib/adjustments.esm`'s new `pm_temperature_adjustment`
because `adjust.rs` writes it. Both are inert here and §7.2 says so.

`noxhumidityadjust` is populated (3 rows) and is **not read**: the humidity
correction multiplies only inside the NOx arm, which neither PM pollutant
enters.

### 2.5 `SulfatePMCalculator`

`sulfate_pm_calculator.rs::calculate` is five stages, and the document writes
five stages. It is a **chained** calculator in MOVES's sense —
`CalculatorInfo.txt` records `Chain SulfatePMCalculator BaseRateCalculator` and
no `Subscribe` directive — but it is not a chain in the shape rungs 4–6 used: it
consumes two blocks, produces six, and its `RunSpecChainedTo` rows describe the
result rather than drive it (§2.8).

#### 2.5.1 The fuel-sulfur sulfate fractions

`compute_sulfate_fractions`, the port of the SQL's `oneCountyYearSulfateFractions`
extract. For every `sulfatefractions` row, every run-spec model year inside its
band, and every supplied fuel formulation whose subtype maps to the row's fuel
type:

```
adjustment = 1 + BaseFuelSulfateFraction x (coalesce(sulfurLevel, 0) / BaseFuelSulfurLevel - 1)
S_adj      = SUM over supplied f of  marketShare_f x SulfatenonECPMFraction x adjustment_f
H_adj      = SUM over supplied f of  marketShare_f x H2OnonECPMFraction     x adjustment_f
```

and the **unadjusted** `SulfatenonECPMFraction` and `H2OnonECPMFraction` are
recorded verbatim alongside them, because the residue split uses those and not
the adjusted pair (§2.5.2). Six rows cover the run:

| fuel | model years | `SulfatenonECPM` | `H2OnonECPM` | base sulfur | base sulfate fraction | supplied sulfur | `S_adj` |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 gasoline | 1940–2003 | 0.08 | 0 | 161.2 | 0.69 | 7.15 | 0.027248387097 |
| 1 gasoline | 2004–2060 | 0.08 | 0 | 23.5 | 0.242 | 7.15 | 0.066530382979 |
| 2 diesel | 1940–2006 | 0.05 | 0 | 172.0 | 0.73 | 6.00 | 0.014773255814 |
| 2 diesel | 2007–2060 | 0.74 | 0 | 11.0 | 0.48 | 6.00 | 0.578545454545 |
| 5 E85 | 1940–2003 | 0.08 | 0 | 161.2 | 0.69 | 7.15 | 0.027248387097 |
| 5 E85 | 2004–2060 | 0.08 | 0 | 23.5 | 0.242 | 7.15 | 0.066530382979 |

There is **no fuel-type-9 row**, and that is the first of the two misses that
empty the electricity blocks.

`H2OnonECPMFraction` is 0 on all six, so `H_adj` is 0 everywhere and pollutant
119 is 208 rows of exactly zero. The water arm is written and dead (§7.2).

#### 2.5.2 The three-way split, which does not conserve mass

Each NonECPM row resolves its fraction cell on
`(processID, fuelTypeID, sourceTypeID, monthID, modelYearID)` — an **inner**
join — and emits three rows:

```
115 sulfate = NonECPM x S_adj
119 water   = NonECPM x H_adj
120 residue = NonECPM x greatest(1 - H_unadjusted - S_unadjusted, 0)
```

**The sulfate keeps the sulfur-adjusted fraction and the residue keeps the
unadjusted one**, so the three do not sum back to the NonECPM they came from:
measured over this run's six cells they sum to 0.8385 (diesel 2007+) to 0.9865
(gasoline pre-2004). That is `sulfate_pm_calculator.rs:636–639` written out, it
is not a rounding artefact, and a document that "fixed" it by using one fraction
for both would be wrong by 62 % on the diesel 2007+ sulfate block. It is the
single most load-bearing detail in this rung (§7.2's sabotage table).

The `greatest(…, 0)` clamp never binds: the raw residue runs 0.26 to 0.95.

#### 2.5.3 The general fuel-effect ratio, restricted to the residue

`SulfatePMCalculator.sql` §75 builds `sPMOneCountyYearGeneralFuelRatio` with
`gfr.pollutantID in (120)`. **Only the residue is rescaled here** — the 112 rows
of the same table were already applied one stage earlier, by
`BaseRateCalculator` on polProcessID 11201 (§2.3). `../moves.rs` records the
consequence of getting this wrong in a comment at
`sulfate_pm_calculator.rs:2226`: applying the 112 rows here as well "would
wrongly rescale EC (and the PM2.5 total that sums it) — e.g. process-pm-exhaust
EC by ~1.09x on fuelType 1".

It is an `UPDATE` and not a join, so a residue row with no matching ratio keeps
its value; and it takes the raw `fuelEffectRatio` without the GPA blend, unlike
the base-rate arm. Both differences are written as written.

#### 2.5.4 The crankcase split is a ROW FILTER here, not a multiply

Every `spmOutput` row — the copied EC and the three split species — joins
`crankcaseemissionratio` on `(pollutantID, fuelTypeID, sourceTypeID)` with the
model year inside the row's band, and is scaled by `crankcaseRatio`. The join
does not constrain the process, so the canonical extract pre-filters the table
to the iteration's primary process and its crankcase counterpart; process 15 is
not in this RunSpec, so only the `polProcessID % 100 == 1` rows survive and each
`spmOutput` row yields exactly one `spmOutput2` row.

Twenty rows for source type 21 cover the run — four species × (gasoline
1950–1968, gasoline 1969–2060, diesel 1950–2000, diesel 2001–2060, E85
1950–2060) — and **every one of them carries `crankcaseRatio` exactly
1.000000000000**. So the multiply is inert and the join is load-bearing: it is
the second of the two misses that empty the electricity blocks, because there is
no fuel-type-9 row.

The port reconciles the SQL's `s.regClassID = mwo.regClassID` against a
worker output collapsed over regClass by treating a `regClassID` of 0 as a
wildcard; this fixture's rows all carry the collapsed 0, and the split rows for
each `(pollutant, fuel, source)` share one regClass, so the reconciliation is
unambiguous.

#### 2.5.5 The sums and the speciation

Four steps, in the order `calculate` writes them:

```
110 PM2.5 total  = 112 + 115 + 119 + 120          (Section MakePM2.5Total)
112, 115, 119    copied verbatim to the output
118 NonECPM      = 115 + 119 + 120                (the re-sum; 120 is internal)
111 organic C    = 120 x pmSpeciationFraction     (PMSpeciation, 120 -> 111)
```

then the residue 120 is dropped unconditionally, and 123/124 are dropped because
this RunSpec does not select them. Note that **118 out is not 118 in**: the
emitted NonECPM is the re-sum of the split, which is the split's non-conservation
(§2.5.2) applied to the parent — 0.9865 of it on gasoline, 0.8385 on 2007+
diesel. And **110 = 112 + 118 exactly**, which the reference's own numbers
satisfy to 6.2e-06, its six-significant-figure column storage.

`pmspeciation` is four rows: gasoline and E85 take 0.706723639947 over all model
years, diesel takes 0.725817529328 through 2006 and 0.741704256107 from 2007.
The diesel split is why the model-year band is a real predicate here and not
decoration — ignoring it double-counts every diesel cohort (§7.2).

### 2.6 `PM10EmissionCalculator`

The whole calculator is one join and one multiply (`pm10.rs::compute_pm10`):

```
PM10 (100) = PM2.5 total (110) x PM10PM25Ratio
```

with `PM10PM25Ratio` looked up on `(polProcessID 10001, sourceTypeID, fuelTypeID)`
and a model-year band. Four rows: 1.130430 for fuel types 1, 5 and 9 and
1.086960 for fuel type 2, all over 1940–2060.

Two things this makes visible. The **fuel-type-9 row is present and
unreachable** — no 110 row survives to electricity — so a document could join
on the wrong key and still agree. And there is **one band per (source, fuel)**,
so the band predicate is untested too. Both are in §7.2.

`PM10EmissionCalculator` is chained onto `SulfatePMCalculator` and not onto
`BaseRateCalculator`: `calculator-dag.json` records
`depends_on: ["SulfatePMCalculator"]` for it, because `SulfatePMCalculator` is
what produces pollutant 110 in the rates-first engine.

### 2.7 Survival: why 124 cohorts become 104

A rate row emits when it has a rate **and** the two `SulfatePMCalculator` joins
its species needs both hit. Written as a conjunction rather than as a chain:

```
rt_survives      = rt_isSelected x rt_hasRate                     -- 124 cohorts x 2 polProcesses
coh_splitLives   = coh_hasSulfateFractions                        -- no fuel-9 row
coh_ccLives      = coh_hasCrankcaseSplit (per species)            -- no fuel-9 row
rt_emits         = rt_cohortLives x (this pollutant's species chain exists)
```

The twenty electricity cohorts fail both `coh_splitLives` and `coh_ccLives`.
**Either alone would empty the blocks**, so the row set is not evidence for
which one MOVES uses, and the document writes both because
`sulfate_pm_calculator.rs` performs both. `run-pm-exhaust-oracle.sh` asserts the
two absences separately for exactly that reason.

This is the same shape as `docs/process-airtoxics.md` §2.6's transitive
survival, with one difference worth naming: there, three misses were in
*series* down a chain and any one sufficed because the later ones could not
outlive the earlier; here two misses are in *parallel* on the same cohort. A
document that implemented only one of them would produce the right key set for
the wrong reason.

### 2.8 `runspecchainedto` is cyclic, and is read for its row set only

The table's eight rows are:

| output | input |
|---|---|
| 10001 (PM10) | 11001 |
| 11001 (PM2.5) | 11201 |
| 11001 (PM2.5) | 11801 |
| 11101 (OC) | 11801 |
| 11501 (sulfate) | 11801 |
| **11801 (NonECPM)** | **11501** |
| **11801 (NonECPM)** | **11901** |
| 11901 (H2O) | 11801 |

11801 → 11501 → 11801 is a 2-cycle, and so is 11801 → 11901 → 11801.
`pollutantprocessassoc`'s `chainedto1` / `chainedto2` columns carry the same
cycle. So the fixed-point iteration `docs/esm-conventions.md` §32.1 introduced —
"iterate the parent join; do not widen it" — **does not terminate on this
table**, and a `rspp_rootPolProcessID` is not a well-defined thing to compute
here.

What the table still says correctly, and what this document reads it for, is
**which pollutant-processes are chained at all**: 11201 appears as an input and
never as an output, so it is the one unchained rate; every other selected
pollutant-process appears as an output. That is a row-set fact and it is
cycle-free. The arithmetic comes from `sulfate_pm_calculator.rs`'s stages, which
are a DAG even though MOVES's declaration of them is not.

**The tell is that MOVES's chain table describes a calculator's inputs, not a
computation order.** `SulfatePMCalculator` genuinely takes 118 in and puts 118
out; the table records both facts and cannot distinguish them.
`docs/esm-conventions.md` §33.1.

**This is not a finding.** `docs/findings/README.md` collects "conventions the
format or the toolchain could not express", and every entry there has a repro
that is *expected to fail*. A cyclic chain declaration is a property of MOVES's
own data, and the format expresses the fix — write the calculator's stages,
which are a DAG — without difficulty. Nothing was refused, nothing was silently
wrong, and there is no repro to write. The rule §32.1 stated ("iterate the
parent join; do not widen it") is not falsified either; it is simply out of
scope, because it presumes a chain declaration that *is* the computation graph.
§33.1 records the precondition it was always carrying.

---

## 3. Join structure

### 3.1 The joins this fixture adds

| # | left | right | key pairs | semiring |
|---|---|---|---|---|
| J48 | `rate_rows` | `sulfatefractions_rows` | process; fuel type; source type; **model-year band** | sum-product / max |
| J49 | `rate_rows` × `fuelsupply_rows` | `fuelformulation_rows` | formulation → `sulfurLevel` | sum-product |
| J50 | `rate_rows` | `crankcaseemissionratio_rows` | polProcess (species × 100 + process); fuel type; source type; **model-year band** | sum-product / max, **four times, one per species** |
| J51 | `rate_rows` | `pmspeciation_rows` | process; input pollutant (120); source type; fuel type; **model-year band** | sum-product / max |
| J52 | `rate_rows` | `pm10emissionratio_rows` | polProcess (10001); source type; fuel type; **model-year band** | sum-product / max |
| J53 | `rate_rows` × `fuelsupply_rows` | `generalfuelratio_rows` | formulation; polProcess; source type; **model-year band**; **age band** | sum-product / max |
| J54 | `rate_rows` | `rate_rows` (self) | pollutant ↔ EC / NonECPM, cohortOrdinal ↔ cohortOrdinal | sum-product, **twice** |

J53 is `docs/process-crankcase-running.md`'s J40 — the same table under the same
five key pairs, live again after being empty in `process-airtoxics`. J54 is the
one new *shape*: the two parents are pulled onto the cohort by a self-join on
the rate relation, once per parent pollutant, instead of one self-join on a
chain key. There is no J-numbered chain-root join at all, for the reason §2.8
gives.

### 3.2 The model-year predicates are all the same thing here

All five of the new lookups band the model year with two columns —
`minModelYearID`/`maxModelYearID` on four of them and the same pair on
`crankcaseemissionratio` — so every one is `lib/keys.esm`'s
`model_year_in_range` and nothing new is needed.
`process-airtoxics`' second and third shapes (an age identity plus a band; a
self-described `beginYYYYendYYYY` group) do not appear. The **age** band on
`generalfuelratio` is `in_inclusive_range` under its own name, which is what
`lib/keys.esm`'s description already records `process-crankcase-running` needing.

### 3.3 One rank, over the whole rate relation

`docs/esm-conventions.md` §31, unchanged in mechanism and *newly cheap in this
fixture*: `rt_emits` is the mask, `rt_prefixEmitted` an inclusive prefix count
over all 1,148 candidates giving a dense 1..728, and the output relation is
728 × 2 with the pollutant-process read *back* through the rank join like every
other key. `n_outputRateRow` = 728 is the one declared number;
`run_outputRateRowCount` recomputes it and `pp_emittedCohortCount` recomputes
the seven 104s separately.

**The blocks are rectangular here and the rank is still global.** 728 = 7 × 104
is the one factorisation the row count admits *given* seven blocks, but a row
count alone does not know there are seven: 1,456 is also 4 × 364 and 8 × 182.
The per-pollutant-process assertion is what fixes it, and it asserts against
**one shared cohort set** rather than seven counts — which is a stronger claim
than `process-airtoxics` could make and is the one thing about this key set that
is easier.

---

## 4. Reusable shapes

Two new expression templates, both forms and no coefficients
(`docs/esm-conventions.md` §24):

| template | file | source | why it is shared |
|---|---|---|---|
| `pm_temperature_adjustment` | `lib/adjustments.esm` | `adjust.rs:105–110` | `exp(A × (72 − least(T, 72)))` — the PM arm of `general_temp_adjust`, and the `least(T, 72)` form is how `start_temp_adjust` in the same file writes the identical ceiling. Written as one expression rather than as a branch so the ceiling exists once, exactly as `quadratic_temperature_adjustment` centres on `exhaust_temperature_reference` |
| `fuel_sulfur_sulfate_adjustment` | `lib/adjustments.esm` | `sulfate_pm_calculator.rs:838–841` | `1 + baseFuelSulfateFraction × (sulfurLevel / baseFuelSulfurLevel − 1)` multiplies the sulfate fraction and the water fraction, and written twice the two could disagree about which end the −1 belongs to |

Everything else is instantiated rather than re-spelled: `lib/keys.esm`'s
`in_inclusive_range`, `model_year_in_range`, `flat_relation_major` and
`flat_relation_minor`; `lib/adjustments.esm`'s `exact_else_wildcard` and
`gpa_blend`; `lib/identifiers.esm`'s `pol_process_id`, `pollutant_id_of`,
`process_id_of` and `null_output_column`; `lib/onroad_activity.esm`'s
`onroad_scc`, `weeks_per_month`, `share_of_group` and `source_bin_slot`; and the
whole of `lib/drive_cycle.esm`.

`quadratic_temperature_adjustment` is **not** instantiated by this fixture, and
that is the point of §2.4: no row of this run reaches the fall-through arm.

---

## 5. Literals and enums

`enums` gains a `pollutant` block of seven members and loses everything
speciation-related. Added: `pollutant.ElementalCarbon` (112),
`.CompositeNonECPM` (118), `.SulfateParticulate` (115), `.H2OAerosol` (119),
`.NonECNonSO4PM` (120), `.PM25Total` (110), `.OrganicCarbon` (111) and
`.PM10Total` (100).

**Every one of those eight is a named constant in the source**, which is the
test `docs/esm-conventions.md` §32.4 sets: `sulfate_pm_calculator.rs` declares
`EC_POLLUTANT`, `NON_EC_PM_POLLUTANT`, `SULFATE_POLLUTANT`, `H2O_POLLUTANT`,
`NON_EC_NON_SO4_PM_POLLUTANT`, `PM25_TOTAL_POLLUTANT` and
`ORGANIC_CARBON_POLLUTANT`, and `pm10.rs` declares `TOTAL_PM25_POLLUTANT` and
`TOTAL_PM10_POLLUTANT`. MOVES composes these species by *identity*, not by a
key it could look up — `PM25_TOTAL_INPUTS` and `NON_EC_PM_INPUTS` are literal
arrays of pollutant ids in the Java's SQL — so a document that refused to name
them would have to invent a table MOVES does not have. **Name a pollutant
exactly where the source names one** cuts the other way here from how it cut in
`process-airtoxics`, and it is the same rule.

Pollutant 120 is the interesting member: it is *internal*, never selected by a
RunSpec and never emitted, and it appears in this document because
`generalfuelratio` carries `polProcessID` 12001 rows that have to be found by
it.

**The bare numeric literals are the same seven values as
`process-crankcase-running`'s, `process-nox-speciation`'s and
`process-airtoxics`'**, measured over every equation: 0, 0.5 and 1 (masks,
comparisons and the multiplicative identity); 2 and 3 (the drive cycle's second
offsets); 10 (the decimal-slot exponent `source_bin_slot` raises); and 1000
(`countyID / 1000`, the state id). The 72 of the PM temperature ceiling lives
inside `pm_temperature_adjustment`, and the 75 of the quadratic inside the
template this fixture does not instantiate.

---

## 6. Hand-checkable worked examples

### 6.0 Run-level values used by every example

```
temperature       59.5 degF         heatIndex     59.5 degF
GPAFract          0.0               acActivity    0.0 (raw -0.296982, clamped)
temperatureFactor 1.0 exactly on every row (PM arm, and temperatureadjustment is EMPTY)
crankcaseRatio    1.0 exactly on every row this run reaches
H2OnonECPMFraction 0 on all six sulfatefractions rows, so pollutant 119 is 0 everywhere
```

### 6.1 Worked example A — MY 1980, gasoline, weekend

`baseratebyage_1_2020` hourDayID 72 carries meanBaseRate 0.669368 for
polProcessID 11201 and 4.111710 for 11801, both with meanBaseRateACAdj 0. The
activity is `SHO / noOfRealDays` = 1.218639356442. Model year 1980 is outside
`generalfuelratio`'s 2001–2060 gasoline band, so the base-rate fuel effect is 1.

```
EC   (112)  = 0.669368 x 1.218639356442                        = 0.815718     MOVESOutput: 0.815719000000
NonEC       = 4.111710 x 1.218639356442                        = 5.010681
sulfate(115)= 5.010681 x 0.027248387097                        = 0.136533     MOVESOutput: 0.136533000000
water  (119)= 5.010681 x 0                                     = 0            MOVESOutput: 0.000000000000
residue(120)= 5.010681 x 0.92           x 1 (no 12001 row)     = 4.609827     internal, never emitted
OC    (111) = 4.609827 x 0.706723639947                        = 3.257874     MOVESOutput: 3.257880000000
NonECPM(118)= 0.136533 + 0 + 4.609827                          = 4.746360     MOVESOutput: 4.746370000000
PM2.5 (110) = 0.815718 + 4.746360                              = 5.562078     MOVESOutput: 5.562090000000
PM10  (100) = 5.562078 x 1.130430                              = 6.287540     MOVESOutput: 6.287550000000
```

`0.027248387097 + 0 + 0.92 = 0.947248`, not 1: §2.5.2's non-conservation, and
the emitted NonECPM is 0.947248 of the parent NonECPM rather than equal to it.

### 6.2 Worked example B — MY 2020, gasoline, weekday, and both fuel-effect stages

```
EC   (112)  = 0.019685400 x 1.090910749585 x 52.011460778417   = 1.116944     MOVESOutput: 1.116950000000
NonEC       = 0.018623400 x 1              x 52.011460778417   = 0.968629
sulfate(115)= 0.968629 x 0.066530382979                        = 0.064443     MOVESOutput: 0.064443300000
residue(120)= 0.968629 x 0.92 x 1.090910749585                 = 0.972152     internal
OC    (111) = 0.972152 x 0.706723639947                        = 0.687043     MOVESOutput: 0.687043000000
NonECPM(118)= 0.064443 + 0.972152                              = 1.036596     MOVESOutput: 1.036600000000
PM2.5 (110) = 1.116944 + 1.036596                              = 2.153540     MOVESOutput: 2.153540000000
PM10  (100) = 2.153540 x 1.130430                              = 2.434426     MOVESOutput: 2.434430000000
```

**The 1.090910749585 appears twice on this row and never on the same quantity.**
It scales the EC base rate at `BaseRateCalculator` (polProcessID 11201) and it
scales the residue inside `SulfatePMCalculator` (pollutantID 120). It does NOT
scale the sulfate, the water, or the NonECPM base rate. A document that applied
it once, at either stage, to everything would be wrong on 115 by +9.1 % and on
110 by a mixture; a document that applied it at both stages to EC would be wrong
on 112 by +9.1 %.

### 6.3 Worked example C — MY 2010, diesel, weekday, where the split is 0.8385

Diesel 2007-and-later takes the `SulfatenonECPMFraction` 0.74 band, so almost
three-quarters of the composite is sulfate and the residue fraction is 0.26.

```
EC   (112)  = 0.000168101 x 46.020805821713                    = 0.0077362    MOVESOutput: 0.007736140000
NonEC       = 0.000552172 x 46.020805821713                    = 0.0254114
sulfate(115)= 0.0254114 x 0.578545454545                       = 0.0147017    MOVESOutput: 0.014701600000
residue(120)= 0.0254114 x 0.26                                 = 0.0066070    internal
OC    (111) = 0.0066070 x 0.741704256107                       = 0.0049004    MOVESOutput: 0.004900410000
NonECPM(118)= 0.0147017 + 0.0066070                            = 0.0213086    MOVESOutput: 0.021308600000
PM2.5 (110) = 0.0077362 + 0.0213086                            = 0.0290448    MOVESOutput: 0.029044800000
PM10  (100) = 0.0290448 x 1.086960                             = 0.0315705    MOVESOutput: 0.031570500000
```

Two things only diesel shows: the **PM10 ratio is 1.08696 and not 1.13043**, and
the **`pmspeciation` fraction is 0.741704256107 and not 0.706723639947** —
diesel is the only fuel with two model-year bands in that table, which is what
makes its band predicate falsifiable (§7.2).

### 6.4 Worked example D — the absences

```
MY 2020, electricity   ABSENT in all seven blocks, though baseratebyage_1_2020
                       carries it at exactly 0.000000000000 for BOTH 11201 and
                       11801. It is dropped by TWO independent inner joins:
                       sulfatefractions has no fuel-9 row and
                       crankcaseemissionratio has none either.
MY 2000, electricity   ABSENT one stage earlier still: emissionratebyage has
                       no fuel-9 source bin at shortModYrGroupID 20, which is
                       the group model year 2000 maps to, so it never reaches a
                       rate at all. NOT the age-group miss `process-airtoxics`
                       0.2 records -- fuel 9 has all seven age groups here.
MY 2020, diesel        ABSENT: not a selected cohort (no 2020 diesel
                       stmyFraction).
pollutant 119          PRESENT on all 104 cohorts, at exactly 0.
```

Four absences with four different causes, and a whole block that is present and
zero. Between them they are the whole of §0.2.

### 6.5 The reproduction script

Extracted and run by `./run-pm-exhaust-oracle.sh`. It reads only the input
tables of §1, computes S1–S18 for the two rated blocks, then both calculators,
and **asserts** its worst relative error against `sho`, against
`sbweightedemissionratebyage`, against `baseratebyage_1_2020` and against
`MOVESOutput`, plus the key set and eleven things a comparison against
`MOVESOutput` could not see.

```python
#!/usr/bin/env python3
"""process-pm-exhaust reproduction from the snapshot's own input tables."""
import sys, collections, math
import pyarrow.parquet as pq

SNAP = sys.argv[1]
P = SNAP + "/tables/db__movesexecution1ccc0232_campuscluster_illinois_edu__"
def T(n): return pq.read_table(P+n+".parquet").to_pylist()

YEAR, MONTH, HOUR, ZONE, ROAD, ST = 2020, 8, 7, 261610, 4, 21
COUNTY, ELECTRICITY = 26161, 9
EC_PP, NONEC_PP = 11201, 11801
EC, SULFATE, WATER, RESIDUE = 112, 115, 119, 120
DAYS=[r["dayID"] for r in T("runspecday")]
HD={r["dayID"]:r["hourDayID"] for r in T("hourday") if r["hourID"]==HOUR}
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
    # adjust.rs:105-110: pollutant 112/118 on process 1/2 take the PM arm --
    # a MULTIPLICATIVE exponential below 72 F and a flat 1 above it.
    a,_=temp_terms(pp,fuel,regclass,my)
    return math.exp(a*(72.0-TEMP)) if TEMP<=72.0 else 1.0
# A/C
GRP={r["monthID"]:r["monthGroupID"] for r in T("monthofanyyear")}[MONTH]
MGH=[r for r in T("monthgrouphour") if r["monthGroupID"]==GRP and r["hourID"]==HOUR][0]
acraw=float(MGH["ACActivityTermA"])+HEAT*(float(MGH["ACActivityTermB"])+float(MGH["ACActivityTermC"])*HEAT)
ACACT=min(max(acraw,0.0),1.0)
ACPEN={r["modelYearID"]:float(r["ACPenetrationFraction"]) for r in T("sourcetypemodelyear") if r["sourceTypeID"]==ST}
ACFUNC={r["ageID"]:float(r["functioningACFraction"]) for r in T("sourcetypeage") if r["sourceTypeID"]==ST}
def fac(pp):
    return {r["opModeID"]:float(r["fullACAdjustment"]) for r in T("fullacadjustment")
            if r["sourceTypeID"]==ST and r["polProcessID"]==pp}
# fleet average (EV sales) adjustment
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
# fuel supply
FSUB={r["fuelSubtypeID"]:r["fuelTypeID"] for r in T("fuelsubtype")}
FFROW={r["fuelFormulationID"]:r for r in T("fuelformulation")}
FFORM={k:v["fuelSubtypeID"] for k,v in FFROW.items()}
supply=collections.defaultdict(list)
for r in T("fuelsupply"):
    if r["fuelYearID"]!=FUELYEAR or r["monthGroupID"]!=GRP: continue
    st=FFORM[r["fuelFormulationID"]]
    if st not in FSUB: continue
    supply[FSUB[st]].append((r["fuelFormulationID"],float(r["marketShare"])))
def scc(fuel,proc): return "%d"%(22*10**8+fuel*10**6+ST*10**4+ROAD*10**2+proc)
GPA=float([r for r in T("county") if r["countyID"]==COUNTY][0]["GPAFract"])
GFR=T("generalfuelratio")
def base_rate_fuel_factor(pp,fuel,my):
    # adjust.rs:452-472, the BASE-RATE stage's general fuel effect: one rate per
    # SUPPLIED formulation, each blended by the county GPA fraction, then
    # re-collapsed by market share (aggregate.rs:28-45). `criteriaratio` is EMPTY
    # in this snapshot, so this is the only fuel effect the base rate takes.
    age=YEAR-my; total=0.0
    for ff,share in supply.get(fuel,[]):
        r=next((r for r in GFR
                if r["fuelFormulationID"]==ff and r["polProcessID"]==pp
                and r["sourceTypeID"]==ST
                and r["minModelYearID"]<=my<=r["maxModelYearID"]
                and r["minAgeID"]<=age<=r["maxAgeID"]),None)
        ratio=1.0 if r is None else (float(r["fuelEffectRatio"])
              +GPA*(float(r["fuelEffectRatioGPA"])-float(r["fuelEffectRatio"])))
        total+=share*ratio
    return total

# ---- the two unchained parents: EC (112) and NonECPM (118) ----------------
REGCLASS={}
def parent(pp):
    coh=cohorts(pp)
    sbaf=rebase(coh)
    rate=rates_by_age(pp)
    modes=sorted({k[4] for k in rate})
    FAC=fac(pp)
    sbw=collections.defaultdict(float); sbwac=collections.defaultdict(float)
    for (my,fuel,et,rc),frac in sbaf.items():
        smy=shortgroup[mygroup[(pp,my)]]
        ag=agegroup[YEAR-my]
        ev=evsf(pp,my,fuel,rc)
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
    q={}
    for (my,fuel,et,rc),frac in coh.items():
        age=YEAR-my
        smy=shortgroup[mygroup[(pp,my)]]
        if (fuel,et,rc,smy,agegroup[age]) not in have: continue
        REGCLASS[(my,fuel)]=rc
        acf=ACACT*ACPEN[my]*ACFUNC[age]
        tf=temp_factor(pp,fuel,rc,my)
        fuelfactor=base_rate_fuel_factor(pp,fuel,my)
        for d in DAYS:
            base_r=br[(HD[d],my,fuel)]+acf*brac[(HD[d],my,fuel)]
            act=sho[(HD[d],age)]/realdays[d]
            q[(d,my,fuel)]=base_r*fuelfactor*tf*act
    BR[pp]=br; BRAC[pp]=brac; SBW[pp]=sbw
    return q
BR={}; BRAC={}; SBW={}
ec=parent(EC_PP)
nonec=parent(NONEC_PP)

# ---- SulfatePMCalculator, stage 1: the fuel-sulfur sulfate fractions -------
# sulfate_pm_calculator.rs::compute_sulfate_fractions.  Every join is an INNER
# JOIN, and fuel type 9 has no `sulfatefractions` row at all.
MONTHS_OF_GROUP=collections.defaultdict(list)
for r in T("monthofanyyear"): MONTHS_OF_GROUP[r["monthGroupID"]].append(r["monthID"])
RUNSPEC_MY=sorted({my for (my,_f,_e,_r) in cohorts(NONEC_PP)})
SUPPLY_ROWS=[r for r in T("fuelsupply") if r["fuelYearID"]==FUELYEAR]
S_adj={}; H_adj={}; S_un={}; H_un={}
for sf in T("sulfatefractions"):
    for my in RUNSPEC_MY:
        if not sf["minModelYearID"]<=my<=sf["maxModelYearID"]: continue
        for r in SUPPLY_ROWS:
            ff=FFROW.get(r["fuelFormulationID"])
            if ff is None: continue
            if FSUB.get(ff["fuelSubtypeID"])!=sf["fuelTypeID"]: continue
            lvl=0.0 if ff["sulfurLevel"] is None else float(ff["sulfurLevel"])
            # adjustment = 1 + BaseFuelSulfateFraction x (sulfurLevel/BaseFuelSulfurLevel - 1)
            adj=1.0+float(sf["BaseFuelSulfateFraction"])*(lvl/float(sf["BaseFuelSulfurLevel"])-1.0)
            for mo in MONTHS_OF_GROUP[r["monthGroupID"]]:
                k=(sf["processID"],sf["fuelTypeID"],sf["sourceTypeID"],mo,my)
                share=float(r["marketShare"])
                S_adj[k]=S_adj.get(k,0.0)+share*float(sf["SulfatenonECPMFraction"])*adj
                H_adj[k]=H_adj.get(k,0.0)+share*float(sf["H2OnonECPMFraction"])*adj
                S_un[k]=float(sf["SulfatenonECPMFraction"])
                H_un[k]=float(sf["H2OnonECPMFraction"])

# ---- stage 2: spmOutput -- EC copied, NonECPM split three ways -------------
spm=collections.defaultdict(float)          # (pollutant, day, modelYear, fuel) -> grams
for (d,my,fuel),q in ec.items(): spm[(112,d,my,fuel)]=q
for (d,my,fuel),q in nonec.items():
    k=(1,fuel,ST,MONTH,my)
    if k not in S_adj: continue             # INNER JOIN spmSplit1
    spm[(115,d,my,fuel)]=q*S_adj[k]
    spm[(119,d,my,fuel)]=q*H_adj[k]
    spm[(120,d,my,fuel)]=q*max(1.0-H_un[k]-S_un[k],0.0)

# ---- stage 3: the general fuel-effect ratio --------------------------------
# A multi-table UPDATE, not a join: a row with no matching ratio is left alone.
# Only pollutants 112 and 120 carry rows here.
# `SulfatePMCalculator.sql` 75 restricts its own extract to pollutantID 120: the
# residue is the ONLY species this stage rescales. The EC (112) rows of the same
# table are applied one stage earlier, by `BaseRateCalculator` on polProcessID
# 11201 -- see `base_rate_fuel_factor`. Applying them here as well would square
# the 1.0909 on gasoline and E85.
SPM_GFR=[r for r in GFR if r["pollutantID"]==RESIDUE]
def gfr(pol,fuel,my):
    age=YEAR-my
    for r in SPM_GFR:
        if (r["fuelTypeID"]==fuel and r["sourceTypeID"]==ST and r["pollutantID"]==pol
                and r["processID"]==1 and r["minModelYearID"]<=my<=r["maxModelYearID"]
                and r["minAgeID"]<=age<=r["maxAgeID"]):
            return float(r["fuelEffectRatio"])
    return 1.0
for (pol,d,my,fuel) in list(spm): spm[(pol,d,my,fuel)]*=gfr(pol,fuel,my)

# ---- stage 4: the crankcase split -> spmOutput2 ----------------------------
# INNER JOIN on (pollutant, fuelType, sourceType) with the model year inside the
# split's window.  `crankcaseemissionratio` carries no fuel-type-9 row, and this
# is where the twenty electricity cohorts leave the run.
CCR=collections.defaultdict(list)
for r in T("crankcaseemissionratio"):
    pol,proc=divmod(r["polProcessID"],100)
    if proc!=1: continue                    # only the run's own process
    CCR[(pol,r["fuelTypeID"],r["sourceTypeID"])].append(r)
spm2=collections.defaultdict(float)
for (pol,d,my,fuel),q in spm.items():
    for s in CCR.get((pol,fuel,ST),()):
        if not s["minModelYearID"]<=my<=s["maxModelYearID"]: continue
        spm2[(pol,d,my,fuel)]+=q*float(s["crankcaseRatio"])

# ---- stage 5: the sums, the speciation, and the emitted species ------------
out=collections.defaultdict(float)
for (pol,d,my,fuel),q in spm2.items():
    if pol in (112,115,119):     out[(pol,d,my,fuel)]+=q      # copied verbatim
    if pol in (112,115,119,120): out[(110,d,my,fuel)]+=q      # MakePM2.5Total
    if pol in (115,119,120):     out[(118,d,my,fuel)]+=q      # NonECPM re-sum
for (pol,d,my,fuel),q in spm2.items():                        # PMSpeciation
    for r in T("pmspeciation"):
        if (r["processID"]==1 and r["inputPollutantID"]==pol and r["sourceTypeID"]==ST
                and r["fuelTypeID"]==fuel and r["minModelYearID"]<=my<=r["maxModelYearID"]):
            out[(r["outputPollutantID"],d,my,fuel)]+=q*float(r["pmSpeciationFraction"])
# The internal residue 120 is dropped unconditionally; 123 and 124 are not in
# this RunSpec's output pollutant-processes and are dropped too.
for k in [k for k in out if k[0]==120]: del out[k]

# ---- PM10EmissionCalculator: 110 -> 100 ------------------------------------
# pm10.rs::compute_pm10.  Total PM10 is the only live pair; the OC/EC/sulfate
# branches are commented out in the Java and are not ported.
for (pol,d,my,fuel),q in list(out.items()):
    if pol!=110: continue
    for r in T("pm10emissionratio"):
        if (r["polProcessID"]==10001 and r["sourceTypeID"]==ST and r["fuelTypeID"]==fuel
                and r["minModelYearID"]<=my<=r["maxModelYearID"]):
            out[(100,d,my,fuel)]+=q*float(r["PM10PM25Ratio"])

rows={(pol,1,d,my,fuel):(q,scc(fuel,1)) for (pol,d,my,fuel),q in out.items()}

# ------------------------------------------------------------------- compare
ref_sho={(r["hourDayID"],r["ageID"]):float(r["SHO"]) for r in T("sho")}
worst_sho=max(abs(sho[k]-v)/v for k,v in ref_sho.items())
print("sho:            %3d rows, worst relative error %.3e"%(len(ref_sho),worst_sho))
assert worst_sho<1e-5, "sho: worst relative error %.3e exceeds 1e-5"%worst_sho

# sbweightedemissionratebyage -- the mode-resolved rate, BEFORE the drive-cycle
# collapse.  `process-airtoxics` names this table and does not read it; checking
# it here separates a wrong rate lookup from a wrong W.
ref_sbw={(r["polProcessID"],r["modelYearID"],r["fuelTypeID"],r["opModeID"]):float(r["meanBaseRate"])
         for r in T("sbweightedemissionratebyage")}
worst_sbw,n_sbw=0.0,0
for (pp,my,fuel,om),v in ref_sbw.items():
    got=SBW[pp].get((my,fuel,om),0.0)
    if v==0.0:
        assert got==0.0,(pp,my,fuel,om,got); continue
    n_sbw+=1; worst_sbw=max(worst_sbw,abs(got-v)/v)
print("sbWeightedRate: %4d non-zero rows of %d, worst relative error %.3e"
      %(n_sbw,len(ref_sbw),worst_sbw))
assert worst_sbw<2e-5, "sbWeightedRate: worst relative error %.3e exceeds 2e-5"%worst_sbw

ref_br=collections.defaultdict(dict)
for r in T("baseratebyage_1_2020"):
    ref_br[r["polProcessID"]][(r["hourDayID"],r["modelYearID"],r["fuelTypeID"])]=float(r["meanBaseRate"])
for pp in (EC_PP,NONEC_PP):
    br,brac=BR[pp],BRAC[pp]
    worst_br,n_br=0.0,0
    for k,v in ref_br[pp].items():
        if v==0.0:
            assert br[k]+brac[k]==0.0,(pp,k)     # the 20 electricity cohorts
            continue
        n_br+=1; worst_br=max(worst_br,abs(br[k]-v)/v)
    print("baseRateByAge %d: %3d non-zero rows of %d, worst relative error %.3e"
          %(pp,n_br,len(ref_br[pp]),worst_br))
    assert worst_br<2e-5, "baseRateByAge %d: worst relative error %.3e exceeds 2e-5"%(pp,worst_br)

ref=pq.read_table(SNAP+"/tables/db__out_process_pm_exhaust__movesoutput.parquet").to_pylist()
key=lambda o:(o["pollutantID"],o["processID"],o["dayID"],o["modelYearID"],o["fuelTypeID"])
missing=[key(o) for o in ref if key(o) not in rows]
extra=sorted(set(rows)-{key(o) for o in ref})
worst,worst_key,n_zero=0.0,None,0
for o in ref:
    if key(o) not in rows: continue
    q,s=rows[key(o)]
    assert s==o["SCC"],(key(o),s,o["SCC"])
    e=float(o["emissionQuant"])
    if e==0.0: n_zero+=1
    rel=abs(q-e)/e if e!=0.0 else abs(q-e)
    if rel>worst: worst,worst_key=rel,key(o)
print("emissionQuant: %4d rows, %d missing, %d extra, worst relative error %.3e at "
      "(pollutant %d, process %d, day %d, MY %d, fuel %d)"
      %(len(ref),len(missing),len(extra),worst,*worst_key))
# ASSERTED, not merely printed (docs/esm-conventions.md 21): ./run-tests.sh reads
# this script's EXIT CODE, so a regression that leaves the key set intact and
# moves every value would otherwise be reported green with the evidence in a log.
assert not missing, missing[:8]
assert not extra, extra[:8]
assert len(rows)==len(ref), (len(rows),len(ref))
assert worst<2e-5, "emissionQuant: worst relative error %.3e exceeds 2e-5"%worst

# --- the KEY SET, exactly, and not merely its size -------------------------
# 1,456 is 7 x 208 and also 6 x 208 + 208, and 1,456 = 4 x 364 = 8 x 182: a row
# count cannot tell a seven-block set from a mis-shaped one.  So the cohort set
# is asserted PER pollutant-process, against ONE shared set, with the day-type
# axis separate and their product against the row count.
cohorts_by_pp=collections.defaultdict(set)
days=set()
for (pol,proc,day,my,fuel) in rows:
    cohorts_by_pp[(pol,proc)].add((my,fuel)); days.add(day)
assert set(cohorts_by_pp)=={(p,1) for p in (100,110,111,112,115,118,119)}, sorted(cohorts_by_pp)
shared=cohorts_by_pp[(112,1)]
assert all(v==shared for v in cohorts_by_pp.values()), \
    {k:len(v) for k,v in cohorts_by_pp.items()}
assert len(shared)==104, len(shared)
assert {f for _,f in shared}=={1,2,5}, shared
assert sorted(my for my,f in shared if f==1)==list(range(1980,2021))
assert sorted(my for my,f in shared if f==2)==list(range(1980,2020))
assert sorted(my for my,f in shared if f==5)==list(range(1998,2021))
assert days==set(DAYS) and len(days)==2, days
assert len(cohorts_by_pp)*len(shared)*len(days)==len(ref)==1456
print("key set:        7 blocks x 104 cohorts x %d day types = %d rows, exact, and ALL SEVEN"
      " BLOCKS CARRY THE SAME 104 COHORTS"%(len(days),len(ref)))
# The parent that is NOT emitted: the rate relation carries 124 cohorts, and the
# 20 electricity ones reach `spmOutput` before they die.
candidates={(my,fuel) for (my,fuel,_e,_r) in cohorts(EC_PP)}
parent={(my,fuel) for (_d,my,fuel) in ec}
assert len(candidates)==125 and len(parent)==124, (len(candidates),len(parent))
assert candidates-parent=={(2000,ELECTRICITY)}, candidates-parent
assert {(_d,my,fuel) for (_d,my,fuel) in nonec}=={(_d,my,fuel) for (_d,my,fuel) in ec}
assert parent-shared=={c for c in parent if c[1]==ELECTRICITY}
assert len(parent-shared)==20
print("                the 124-cohort rate relation loses exactly the 20 ELECTRICITY cohorts,"
      " and it loses them TWICE:")
print("                `sulfatefractions` has no fuel-9 row (the 118 split) and"
      " `crankcaseemissionratio` has none either (the")
print("                EC copy) -- either miss alone would suffice, so the row set is not"
      " evidence for which one MOVES uses.")

# --- what a comparison against MOVESOutput alone could not see -------------
# Every one of these was found by SABOTAGING this script and watching the
# comparison stay green (docs/process-pm-exhaust.md 7.2).
# 1. The crankcase split is a ROW FILTER here and not a multiply: every ratio
#    that matches is exactly 1.0, while the join itself decides 20 cohorts.
used=[float(s["crankcaseRatio"]) for k in CCR for s in CCR[k] if k[1] in {f for _m,f in shared}]
assert used and set(used)=={1.0}, sorted(set(used))
assert not CCR.get((112,ELECTRICITY,ST)) and not CCR.get((120,ELECTRICITY,ST))
print("NOTE:           every crankcaseRatio this run reaches is exactly 1.0, so the crankcase"
      " MULTIPLY is inert while")
print("                its INNER JOIN is load-bearing -- forcing the ratio to 1 leaves all"
      " 1,456 cells unchanged; removing")
print("                the join adds 40 electricity rows.")
# 2. H2O (aerosol) is 208 rows of EXACTLY zero, because H2OnonECPMFraction is 0
#    on all six sulfatefractions rows -- so the water arm of the split, its
#    market-share weighting, its sulfur adjustment and its term in the residue
#    fraction are all written and all dead.
assert all(float(sf["H2OnonECPMFraction"])==0.0 for sf in T("sulfatefractions"))
assert all(v==0.0 for (pol,_d,_m,_f),v in out.items() if pol==119)
assert all(float(o["emissionQuant"])==0.0 for o in ref if o["pollutantID"]==119)
print("NOTE:           H2OnonECPMFraction is 0 on all 6 sulfatefractions rows, so pollutant 119"
      " is 208 rows of EXACTLY")
print("                zero and the water term of the residue fraction (1 - H - S) never"
      " leaves S.")
# 3. The residue keeps the UNADJUSTED fractions while sulfate keeps the adjusted
#    one, so the three species do NOT sum to the NonECPM they came from.
mass=[(S_adj[k]+H_adj[k]+max(1.0-H_un[k]-S_un[k],0.0)) for k in S_adj]
assert all(abs(m-1.0)>1e-3 for m in mass), (min(mass),max(mass))
print("NOTE:           the split does NOT conserve mass -- 115 uses the sulfur-ADJUSTED"
      " fraction and 120 the UNADJUSTED one,")
print("                so the three species sum to %.4f..%.4f of the NonECPM they came from."
      % (min(mass),max(mass)))
# 4. greatest(1 - H - S, 0) never binds: the raw residue is 0.26 to 0.95.
raw=[1.0-H_un[k]-S_un[k] for k in S_un]
assert min(raw)>0.0, min(raw)
print("NOTE:           the greatest(1 - H - S, 0) clamp never binds -- the raw residue runs"
      " %.2f to %.2f -- so a document"%(min(raw),max(raw)))
print("                that dropped the clamp would agree on every cell.")
# 5. The temperature arm is dead twice over. Pollutant 112/118 on process 1
#    takes the PM branch of adjust.rs, a MULTIPLICATIVE exponential below 72 F;
#    the run is at 59.5 F so the >=72 flat branch is NOT what makes it 1 --
#    `temperatureadjustment` is EMPTY, so the term A is 0 and exp(0) = 1.
assert TEMP<72.0, TEMP
assert not TA, len(TA)
print("NOTE:           the PM temperature arm exp(A x (72 - T)) is the LIVE branch at %.1f F,"
      " and it is 1 only because"%TEMP)
print("                `temperatureadjustment` has 0 rows -- the 72 F cap is not what"
      " neutralises it. Swapping the PM branch")
print("                for the fall-through quadratic changes no cell.")
# 6. The A/C arm is dead twice: the activity term clamps to 0 AND
#    `fullacadjustment` has no rows for either parent.
assert ACACT==0.0 and acraw<0.0, acraw
assert not fac(EC_PP) and not fac(NONEC_PP)
print("NOTE:           the A/C activity term is %.6f and clamps to 0, and `fullacadjustment`"
      " has 0 rows for 11201 and"%acraw)
print("                11801 as well, so the A/C arm cannot be checked here at all.")
# 7. `criteriaratio` is EMPTY, so `generalfuelratio` is the only live fuel
#    effect -- and its two pollutants enter at DIFFERENT stages: the EC (112)
#    rows at `BaseRateCalculator` on polProcessID 11201 (adjust.rs:452-472,
#    GPA-blended, per formulation), the residue (120) rows inside
#    `SulfatePMCalculator` (SulfatePMCalculator.sql 75, raw). Applying both in
#    one place would square the 1.0909 on gasoline and E85.
assert not T("criteriaratio")
assert {r["pollutantID"] for r in GFR}=={EC,RESIDUE}, {r["pollutantID"] for r in GFR}
base_ratios=sorted({base_rate_fuel_factor(pp,f,m)
                    for pp in (EC_PP,NONEC_PP) for f in (1,2,5) for m in RUNSPEC_MY})
spm_ratios=sorted({gfr(p,f,m) for p in (EC,SULFATE,WATER,RESIDUE)
                   for f in (1,2,5) for m in RUNSPEC_MY})
assert base_ratios==[0.9727,1.0,1.090910749585], base_ratios
assert spm_ratios==[0.9727,1.0,1.090910749585], spm_ratios
assert all(gfr(EC,f,m)==1.0 for f in (1,2,5) for m in RUNSPEC_MY)
print("NOTE:           `criteriaratio` has 0 rows, so `generalfuelratio` is the ONLY live fuel"
      " effect -- and its two")
print("                pollutants enter at DIFFERENT stages: 112 at the base rate"
      " (adjust.rs:452, per formulation and")
print("                GPA-blended), 120 inside SulfatePMCalculator"
      " (SulfatePMCalculator.sql 75, raw). Both are %s;"%base_ratios)
print("                applying both in one place would SQUARE the 1.0909 on gasoline and E85,"
      " and deleting either")
print("                moves a cell by 8.3%.")
# 8. One formulation per fuel type at market share 1.0, so the sulfate
#    fraction's share-weighted sum is a sum of one term.
assert {f:len(v) for f,v in supply.items()}=={1:1,2:1,5:1,9:1}, supply
assert all(share==1.0 for v in supply.values() for _ff,share in v)
assert {r["fuelFormulationID"] for r in GFR}=={ff for v in supply.values() for ff,_s in v}-{90}
print("NOTE:           each fuel type is supplied by exactly one formulation at market share"
      " 1.0, so the share-weighted")
print("                sulfate fraction is a sum of one term, and `generalfuelratio`'s"
      " fuelFormulationID column -- which")
print("                MOVES does not join on -- cannot be distinguished from ignoring it.")
# 9. pm10emissionratio ships a fuel-type-9 row that nothing can reach.
p10={(r["fuelTypeID"]):float(r["PM10PM25Ratio"]) for r in T("pm10emissionratio") if r["sourceTypeID"]==ST}
assert p10=={1:1.13043,2:1.08696,5:1.13043,9:1.13043}, p10
assert not any(f==ELECTRICITY for _m,f in shared)
print("NOTE:           `pm10emissionratio` carries a fuel-type-9 row at 1.13043 that no"
      " surviving 110 row can reach, and")
print("                one model-year window per (source, fuel), so the window predicate is"
      " untested too.")
# 10. `runspecchainedto` is CYCLIC here, so the chain ROOT cannot be resolved by
#     iterating that table the way rungs 4-6 did.
edges={(c["outputPolProcessID"],c["inputPolProcessID"]) for c in T("runspecchainedto")}
assert (11801,11501) in edges and (11501,11801) in edges
print("NOTE:           `runspecchainedto` contains the 2-CYCLE 11801 <-> 11501 (and 11801 <->"
      " 11901), because MOVES")
print("                re-sums NonECPM from the species it split out of it. Iterating that"
      " table to a fixed point --")
print("                the rung 4-6 chain-root idiom -- does not terminate on this snapshot.")
# 11. The ONE rate miss is on the SHORT MODEL-YEAR GROUP, not on the age group.
#     `process-nox-speciation` and `process-airtoxics` lose the same (2000,
#     electricity) cohort because pollutant 101's fuel-9 rows stop at age group
#     1519. Here fuel 9 carries ALL SEVEN age groups and the miss is that
#     `emissionratebyage` has no fuel-9 source bin at shortModYrGroupID 20 --
#     which is the group model year 2000 maps to. Inheriting the earlier
#     explanation would have been wrong about the key while right about the row.
bins=collections.defaultdict(set)
for r in ERBA:
    b=r["sourceBinID"]
    bins[(r["polProcessID"],slot(b,10**16))].add((slot(b,10**10),r["ageGroupID"]))
for pp in (EC_PP,NONEC_PP):
    assert {a for _s,a in bins[(pp,ELECTRICITY)]}=={3,405,607,809,1014,1519,2099}
    assert 20 not in {s for s,_a in bins[(pp,ELECTRICITY)]}
    assert 20 in {s for s,_a in bins[(pp,1)]}
misses=[(pp,my,fuel) for pp in (EC_PP,NONEC_PP)
        for (my,fuel,et,rc) in cohorts(pp)
        if (fuel,et,rc,shortgroup[mygroup[(pp,my)]],agegroup[YEAR-my])
           not in {(k[0],k[1],k[2],k[3],k[5]) for k in rates_by_age(pp)}]
assert misses==[(EC_PP,2000,ELECTRICITY),(NONEC_PP,2000,ELECTRICITY)], misses
print("NOTE:           the ONE rate miss over both parents and all 125 candidates is (MY 2000,"
      " electricity), and it is a")
print("                SHORT-MODEL-YEAR-GROUP miss, not the age-group miss the earlier rungs"
      " record: fuel 9 carries all")
print("                seven age groups here, and what it lacks is a source bin at"
      " shortModYrGroupID 20.")
# 12. PMSpeciation produces Organic Carbon and nothing else here.
outs={r["outputPollutantID"] for r in T("pmspeciation")}
ins={r["inputPollutantID"] for r in T("pmspeciation")}
assert outs=={111} and ins=={120}, (outs,ins)
print("NOTE:           `pmspeciation` has 4 rows, all 120 -> 111, so NCOM (122), Total Organic"
      " Matter (123) and")
print("                NonECNonSO4NonOM (124) -- and the whole ratio124 = 1 - sum(fraction)"
      " step -- are dead here.")
```

Result:

```
sho:             82 rows, worst relative error 3.610e-06
sbWeightedRate: 4784 non-zero rows of 5704, worst relative error 4.795e-06
baseRateByAge 11201: 208 non-zero rows of 248, worst relative error 4.397e-06
baseRateByAge 11801: 208 non-zero rows of 248, worst relative error 4.900e-06
emissionQuant: 1456 rows, 0 missing, 0 extra, worst relative error 9.910e-06 at (pollutant 100, process 1, day 2, MY 1991, fuel 1)
key set:        7 blocks x 104 cohorts x 2 day types = 1456 rows, exact, and ALL SEVEN BLOCKS CARRY THE SAME 104 COHORTS
                the 124-cohort rate relation loses exactly the 20 ELECTRICITY cohorts, and it loses them TWICE:
                `sulfatefractions` has no fuel-9 row (the 118 split) and `crankcaseemissionratio` has none either (the
                EC copy) -- either miss alone would suffice, so the row set is not evidence for which one MOVES uses.
NOTE:           every crankcaseRatio this run reaches is exactly 1.0, so the crankcase MULTIPLY is inert while
                its INNER JOIN is load-bearing -- forcing the ratio to 1 leaves all 1,456 cells unchanged; removing
                the join adds 40 electricity rows.
NOTE:           H2OnonECPMFraction is 0 on all 6 sulfatefractions rows, so pollutant 119 is 208 rows of EXACTLY
                zero and the water term of the residue fraction (1 - H - S) never leaves S.
NOTE:           the split does NOT conserve mass -- 115 uses the sulfur-ADJUSTED fraction and 120 the UNADJUSTED one,
                so the three species sum to 0.8385..0.9865 of the NonECPM they came from.
NOTE:           the greatest(1 - H - S, 0) clamp never binds -- the raw residue runs 0.26 to 0.95 -- so a document
                that dropped the clamp would agree on every cell.
NOTE:           the PM temperature arm exp(A x (72 - T)) is the LIVE branch at 59.5 F, and it is 1 only because
                `temperatureadjustment` has 0 rows -- the 72 F cap is not what neutralises it. Swapping the PM branch
                for the fall-through quadratic changes no cell.
NOTE:           the A/C activity term is -0.296982 and clamps to 0, and `fullacadjustment` has 0 rows for 11201 and
                11801 as well, so the A/C arm cannot be checked here at all.
NOTE:           `criteriaratio` has 0 rows, so `generalfuelratio` is the ONLY live fuel effect -- and its two
                pollutants enter at DIFFERENT stages: 112 at the base rate (adjust.rs:452, per formulation and
                GPA-blended), 120 inside SulfatePMCalculator (SulfatePMCalculator.sql 75, raw). Both are [0.9727, 1.0, 1.090910749585];
                applying both in one place would SQUARE the 1.0909 on gasoline and E85, and deleting either
                moves a cell by 8.3%.
NOTE:           each fuel type is supplied by exactly one formulation at market share 1.0, so the share-weighted
                sulfate fraction is a sum of one term, and `generalfuelratio`'s fuelFormulationID column -- which
                MOVES does not join on -- cannot be distinguished from ignoring it.
NOTE:           `pm10emissionratio` carries a fuel-type-9 row at 1.13043 that no surviving 110 row can reach, and
                one model-year window per (source, fuel), so the window predicate is untested too.
NOTE:           `runspecchainedto` contains the 2-CYCLE 11801 <-> 11501 (and 11801 <-> 11901), because MOVES
                re-sums NonECPM from the species it split out of it. Iterating that table to a fixed point --
                the rung 4-6 chain-root idiom -- does not terminate on this snapshot.
NOTE:           the ONE rate miss over both parents and all 125 candidates is (MY 2000, electricity), and it is a
                SHORT-MODEL-YEAR-GROUP miss, not the age-group miss the earlier rungs record: fuel 9 carries all
                seven age groups here, and what it lacks is a source bin at shortModYrGroupID 20.
NOTE:           `pmspeciation` has 4 rows, all 120 -> 111, so NCOM (122), Total Organic Matter (123) and
                NonECNonSO4NonOM (124) -- and the whole ratio124 = 1 - sum(fraction) step -- are dead here.
```

### 6.6 What the fixture's inline tests check

`fixtures/process-pm-exhaust.esm`'s `tests` section asserts against the
snapshot's own captured intermediates, so a source that silently delivered a
default fails there rather than at the comparison:

| what | against | why it is the right checkpoint |
|---|---|---|
| the run scope, the fuel year and the base year | `runspec*`, `year` | a wrong base year moves every activity number and nothing else notices |
| `act_sho` at two (hour-day, age) keys | `sho` | the activity half, which §7.1 shows is byte-identical to four ported rungs' |
| `rtMode_weightedRate` at two (polProcess, cohort, mode) keys | `sbweightedemissionratebyage` | the rate lookup BEFORE the drive-cycle collapse — separates a wrong `emissionratebyage` key from a wrong `W` |
| `rtDay_meanBaseRate` for both 11201 and 11801 | `baseratebyage_1_2020` | the collapse itself, once per parent |
| the 40 electricity rows of `baseratebyage_1_2020` are exactly 0 | `baseratebyage_1_2020` | asserts a ZERO, which no relative tolerance can check by accident |
| `run_outputRateRowCount` = 728 and `pp_emittedCohortCount` = 104 seven times | recomputed from the chain | the key-set claim §3.3 makes, in the document rather than in a comment |
| `rt_temperatureFactor` = 1 on a gasoline and a diesel row | — | asserts the PM arm's value, so the inertness of §2.4 is visible in the document |
| `coh_sulfateFractionAdj` on the four bands of §2.5.1 | hand-computed from the six table rows | the one genuinely new arithmetic |
| `out_emissionQuant` on the twelve cells of §§6.1–6.3 | `MOVESOutput` | the answer |
| `out_zoneID` and the six other NULL columns are absent | — | `output_column_is_absent`, because `expected` cannot be NaN |

---

## 7. Fidelity notes and tolerance

### 7.1 The measured result

Four checkpoints, all from the snapshot's own tables and each one a different
part of the chain:

| checkpoint | rows | worst relative error | what it isolates |
|---|---:|---|---|
| `sho` | 82 | 3.610e-06 | S1–S9, the activity half |
| `sbweightedemissionratebyage` | 4,784 non-zero of 5,704 | 4.795e-06 | the `emissionratebyage` lookup, per operating mode, before `W` |
| `baseratebyage_1_2020` (11201) | 208 non-zero of 248 | 4.397e-06 | the drive-cycle collapse, EC |
| `baseratebyage_1_2020` (11801) | 208 non-zero of 248 | 4.900e-06 | the drive-cycle collapse, NonECPM |
| `MOVESOutput` | **1,456 of 1,456**, 0 missing, 0 extra | **9.910e-06** | both calculators and the output stage |

The worst cell is `(pollutant 100, process 1, day 2, MY 1991, fuel 1)` — PM10,
which is the longest product in the document: a rate, an activity, a sulfate
fraction, a residue fraction, a speciation-free sum and then the PM10 ratio,
every one of them read out of a column the reference stores to **six
significant figures**. 9.910e-06 is the largest worst cell of the eleven
fixtures landed so far (the previous band was 4.561e-06 to 9.482e-06) and it is
still half of `tolerance.toml`'s 2e-05, which has never been widened. It is
storage, not accumulation, and §7.3 ranks the operations that carry it.

**The three intermediate checkpoints are what make that claim attributable.**
`process-airtoxics` §7.1 had two (`sho` and `baseratebyage_1_2020`) and named
`sbweightedemissionratebyage` as a table it did not read. Reading it here costs
one aggregate and buys the distinction between a wrong rate key and a wrong
drive-cycle weight — which matters more in this rung than in any before it,
because the rate half runs twice and a key error on one parent alone would move
five of the seven emitted blocks.

### 7.2 What this fixture cannot see — found by SABOTAGING the oracle

Every row of this table was produced by breaking one thing in
`run-pm-exhaust-oracle.sh` and re-running it. **Eleven sabotages leave all
1,456 cells and the whole key set unchanged.** That is the measurement
`docs/esm-conventions.md` §23 asks for, and it is not the same list a reading of
the sources would have guessed.

| # | sabotage | verdict |
|---|---|---|
| 1 | the PM temperature arm replaced by the fall-through quadratic | **inert** |
| 2 | the temperature factor deleted entirely | **inert** |
| 3 | every `crankcaseRatio` forced to 1.0 | **inert** |
| 4 | the H2O arm deleted from the split and from the residue fraction | **inert** |
| 5 | the `greatest(1 − H − S, 0)` clamp removed | **inert** |
| 6 | the A/C activity term deleted | **inert** |
| 7 | the EV fleet-average adjustment deleted | **inert** |
| 8 | market share ignored in the sulfate fractions | **inert** |
| 9 | `pm10emissionratio`'s model-year band ignored | **inert** |
| 10 | the base-rate `generalfuelratio` not restricted to the SUPPLIED formulation | **inert** |
| 11 | the GPA blend dropped from the base-rate fuel effect | **inert** |
| 12 | the base-rate `generalfuelratio` age band ignored | **inert** |
| 13 | the crankcase JOIN removed, the multiply kept | red — 40 extra rows |
| 14 | the crankcase process filter dropped (15 and 2 admitted) | red — 1.400e+00 |
| 15 | the base-rate `generalfuelratio` (112) deleted | red — 8.334e-02 |
| 16 | the `SulfatePMCalculator` `generalfuelratio` (120) deleted | red — 8.334e-02 |
| 17 | that stage NOT restricted to pollutant 120 | red — 9.092e-02 |
| 18 | the fuel-sulfur adjustment deleted | red — 2.385e+00 |
| 19 | the residue split using the ADJUSTED fractions | red — 6.210e-01 |
| 20 | `pmspeciation`'s model-year band ignored | red — 1.022e+00 |
| 21 | the PM2.5 total omitting the residue 120 | red — 8.422e-01 |

Rows 1–12 are twelve things this fixture does not exercise. Read in order they
say five things worth stating plainly.

**1. The whole temperature stage is dead, and it is dead for a reason the
comparison cannot show.** Pollutant 112/118 on process 1 takes the PM
exponential and the run is at 59.5 °F, so the `T ≤ 72` arm is the live branch;
what makes the factor 1 is that `temperatureadjustment` has **0 rows**. The
document instantiates `pm_temperature_adjustment` and `exact_else_wildcard`
anyway, because `adjust.rs` writes both and `mixed-onroad` §7 is what happens
when a wildcard step is skipped on the strength of a passing comparison. Rows 1
and 2 are the two ways a reader could get this wrong, and both are invisible
here.

**2. The crankcase split is a row filter, not a multiply.** Every ratio this run
reaches is exactly `1.000000000000`, so row 3 changes nothing — while row 13,
which keeps the multiply and drops the join, adds all 40 electricity rows. The
arithmetic is untested and the join is load-bearing. A fixture on a RunSpec that
selected crankcase running exhaust (process 15) would test both, and there is
one: `process-crankcase-running`, already ported, whose particulate pollutants
are exactly these.

**3. The water arm of the split is dead in its coefficient and live in its
form.** `H2OnonECPMFraction` is 0 on all six `sulfatefractions` rows, so
pollutant 119 is 208 rows of exactly zero, the water term never leaves the
residue fraction `1 − H − S`, and the clamp `greatest(…, 0)` never binds (the
raw residue runs 0.26 to 0.95). Rows 4 and 5. This is the same shape as
`process-airtoxics` §7.2.4's `oxySpeciation` — a term whose *operands* are real
and whose coefficient is zero — and it is worth the same treatment: write it,
and record that it is not checked.

**4. Two whole adjustment stages the earlier onroad rungs carried have no rows
at all**, and they fail differently from a term that is zero. `fullacadjustment`
is empty *and* the A/C activity term clamps to 0 (raw −0.296982), so the A/C arm
is dead twice over and row 6 cannot distinguish the two reasons.
`fleetavgadjustment` is empty, so `rt_evSalesFactor` is 1 on every row and row 7
is inert; `process-refueling` and `process-nox-speciation` are where that
factor is exercised.

**5. The per-formulation half of the fuel effect is entirely untested, in four
independent ways.** Each fuel type is supplied by exactly **one** formulation at
market share **1.0**, so: the share-weighted sulfate fraction is a sum of one
term (row 8); joining `generalfuelratio` on the fuel type instead of the
supplied formulation cannot be told apart (row 10); `GPAFract` is 0 so the blend
selects the normal arm (row 11); and the age band coincides with the model-year
band on every row that matters (row 12). The market-share collapse is written in
its general form and it is the *product of the means versus the mean of the
products* problem `docs/esm-conventions.md` §32.3 records — exactly right
whenever a fuel type has one formulation, which is every county in this corpus.

Two further things are dead and are not sabotage rows because there is nothing
to break: **`pm10emissionratio` ships a fuel-type-9 row** at 1.13043 that no
surviving 110 row can reach, and **`pmspeciation` produces organic carbon and
nothing else** — 4 rows, all `120 → 111` — so the eleven trace metals and ions,
NCOM (122), Total Organic Matter (123), NonECNonSO4NonOM (124) and the whole
`ratio124 = 1 − Σ pmSpeciationFraction` step of `sulfate_pm_calculator.rs` are
reached by no emitted number.

**What IS newly tested here, and was tested nowhere before**: the fuel-sulfur
sulfate adjustment (row 18, worth a factor of 2.385), the
adjusted-versus-unadjusted asymmetry of the split (row 19, 62 %), the
`pmspeciation` model-year band — falsifiable only because diesel has two of them
(row 20), the composition of PM2.5 total out of four species including the
internal residue (row 21), and the two-stage `generalfuelratio` (rows 15–17).
Five things, and every one of them fails loudly when broken.

### 7.3 Precision-sensitive operations, ranked

1. **The PM10 product.** `PM10 = (EC + sulfate + water + residue) × ratio`, and
   every operand has already been rounded to six significant figures in the
   reference's own column storage. This is where the 9.910e-06 is, and every one
   of the ten worst cells in the run is a pollutant-100 cell.
2. **The residue fraction.** `1 − H − S` is a subtraction of table values from
   1, and on 2007+ diesel it is `1 − 0 − 0.74 = 0.26` — a catastrophic-
   cancellation shape that is benign at these magnitudes (two significant
   figures lost of sixteen) and would not be if the sulfate fraction approached
   1.
3. **The sulfur adjustment.** `1 + f × (s / S − 1)` on gasoline is
   `1 + 0.242 × (7.15 / 23.5 − 1)`, again a subtraction from 1; the quotient is
   the only division in either calculator.
4. **The drive-cycle collapse**, unchanged from `process-crankcase-running`
   §7.3: a 23-term inner product per cohort, twice over.

No `Float32` anywhere: this is an ONROAD document and evaluates in binary64,
which is what `adjust.rs` and `sulfate_pm_calculator.rs` both do.

---

## 8. Gaps and things not verified

1. **Nothing checks that the two `generalfuelratio` stages are the right way
   round.** Applying the 112 rows at the base rate and the 120 rows in
   `SulfatePMCalculator` is what `../moves.rs` does and what
   `SulfatePMCalculator.sql` §75's `gfr.pollutantID in (120)` says. Swapping
   them would move 112 and 120 by 1.0909/0.9727 in opposite directions and the
   comparison would catch it — but only because the two ratios differ per
   pollutant *band*, not by construction. A snapshot where 112 and 120 carried
   the same ratio over the same bands would make the two stages
   indistinguishable.
2. **The crankcase arithmetic is unexercised** (§7.2.2), so this fixture does
   not establish that `crankcaseemissionratio` is a multiply rather than, say, a
   share of a total. `process-crankcase-running` is where that lives.
3. **`FuelEffectsGenerator` is not ported.** `generalfuelratio` ships captured
   in the snapshot, computed from `generalfuelratioexpression`'s 58 equation
   strings and the fuel formulations' properties. Turning those strings into
   ratios is a separate rung, it is `docs/esm-conventions.md`'s "data that is
   code" case, and it is **not** claimed in §0's calculator path.
   `generalfuelratioexpression` has 58 rows here and is not read.
4. **The `regClassID` reconciliation in the crankcase join is asserted, not
   derived.** `../moves.rs` treats a collapsed `regClassID` of 0 as a wildcard
   because `baseRateOutput` emits 0 whenever the RunSpec does not break down by
   reg class. Every row here carries 0, so the concrete-regClass branch of that
   reconciliation is dead and a RunSpec with `regclassid` output would be needed
   to check it.
5. **Nothing here reaches `SulfatePMCalculator`'s crankcase processes.** The
   calculator's 133 registrations cover seven processes; this RunSpec selects
   one. The `primaryAndCrankcaseProcessIDs` filter, the second `spmOutput2`
   process, and the `MakePM2.5Total` section's multi-process list are all
   single-valued here.
6. **`process-airtoxics`' three-level chain-root iteration is not reused and
   not refuted** (§2.8). It presumes a chain declaration that is a computation
   graph; this snapshot's is cyclic. §33.1 records that precondition, which
   §32.1 was carrying implicitly.

---

## 9. Summary for the `.esm` author

* **Two rated pollutant-processes, seven emitted.** One rate relation of
  7 × 164 = 1,148 rows; `rt_hasRate` is non-zero on 328 of them (two
  pollutant-processes × 164 candidates) and the rate arm is exactly 0 on the
  other 820.
* **Pull the two parents onto the cohort with a self-join, once per parent**
  (J54), and build the four `spmOutput` species from them. Do not look for a
  chain root: `runspecchainedto` is cyclic (§2.8).
* **`generalfuelratio` twice, at two stages, on two pollutants.** 112 at the
  base rate, per supplied formulation, GPA-blended; 120 inside
  `SulfatePMCalculator`, raw. Never both on one quantity.
* **The split does not conserve mass.** Sulfate takes the sulfur-adjusted
  fraction, the residue takes the unadjusted one. This is the detail worth the
  most (§7.2, row 19).
* **The temperature arm is the PM exponential**, not the quadratic — a different
  branch of the same function, inert here, and written anyway.
* **The key set is 7 × 104 × 2 and the 104 is shared.** Assert it per
  pollutant-process against ONE cohort set, not as seven counts, and assert
  that the 124-cohort rate relation loses exactly the electricity ones.
* **Two new templates**, both in `lib/adjustments.esm`:
  `pm_temperature_adjustment` and `fuel_sulfur_sulfate_adjustment`.
