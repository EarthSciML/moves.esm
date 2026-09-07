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
  electricity**, whose age group at analysis year 2020 is 2099 and for which
  `emissionratebyage` has no fuel-type-9 row. That is
  `docs/process-nox-speciation.md` §2.2 unchanged, and it leaves **124** rated
  cohorts.
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
MY 2000, electricity   ABSENT one stage earlier still: no emissionratebyage
                       ageGroup-2099 row for fuel type 9, so it never reaches a
                       rate at all.
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

