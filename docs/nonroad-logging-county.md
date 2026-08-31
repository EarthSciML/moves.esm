# `nr-logging-county` — computation specification

A precise, line-cited specification of the arithmetic behind the
`nr-logging-county` NONROAD characterization fixture, written as preparation for
porting it to EarthSciAST `.esm` (PLAN.md §3, Phase 2).

**Status of this document.** Every formula below is cited to
`../moves.rs` by file and line. Section 6 reproduces **all 144 output rows** of
the fixture from raw snapshot inputs with an independent Python/`float32`
implementation, agreeing with the expected `MOVESOutput` to
≤ 4.9 × 10⁻⁶ relative — which is the storage precision of the snapshot's own
`emissionQuant` strings (6 significant figures), not a modelling difference.
That reproduction is the evidence that the chain described here is complete and
correct. Places where I could not close the loop are called out explicitly in
§8.

Paths are relative to `../moves.rs` unless noted.

---

## 0. The fixture at a glance

`characterization/fixtures/nr-logging-county.xml`:

| RunSpec element | Value | Note |
|---|---|---|
| model | `NONROAD` | no onroad calculators fire |
| scale | `Inv` (inventory), domain `DEFAULT` | |
| geography | county `26161` (Washtenaw County, MI) | state `26` |
| year | 2020 | |
| month | `<month key="7"/>` | **⇒ `runspecmonth.monthID = 8`** (August) |
| day | `<day id="5"/>` | dayID 5 = weekday |
| hour | `<beginhour key="6"/>`…`<endhour key="6"/>` | **⇒ `runspechour.hourID = 7`** |
| offroad selections | `sectorid=7` (Logging) × `fueltypeid ∈ {1, 2}` | |
| pollutant/process | `(1,1) (2,1) (3,1) (100,1)` | THC, CO, NOx, PM10 — all Running Exhaust |
| road type | `100` (Nonroad) | |
| output detail | county; modelYear, fuelType, process, roadType, onroadSCC on; sourceUseType, offroadSCC, hpClass off | |

> **The month and hour keys in the RunSpec XML are zero-based indices, not IDs.**
> `key="7"` → `monthID = 8`; `key="6"` → `hourID = 7`. The snapshot's
> `runspecmonth` / `runspechour` tables carry the resolved IDs (8 and 7), and the
> output rows are stamped `monthID = 8`. An `.esm` assembly must take the month
> from `runspecmonth`, never from the XML key. `dayID` is *not* offset (`id="5"`
> → `dayID = 5`).

Expected output: `characterization/snapshots/nr-logging-county/tables/db__out_nr_logging_county__movesoutput.parquet`,
**144 rows** = 4 pollutants × 36 `(SCC, modelYearID)` pairs, with

| SCC | description | equipment points | model years present |
|---|---|---|---|
| `2260007005` | 2-Str Chain Saws > 6 HP | 1 | 2018–2020 (3) |
| `2265007010` | 4-Str Shredders > 6 HP | 3 | 1983–2020, gappy (29) |
| `2265007015` | 4-Str Forest Eqp – Feller/Bunch/Skidder | 2 | 2017–2020 (4) |

Diesel logging SCCs (`2270007010`, `2270007015`) produce **no** rows — see
§5.4 for why the `fuelTypeID = 2` selection matches nothing.

---

## 1. Input inventory

### 1.1 How the set was determined

`execution-trace.json` for this fixture records **157 Java classes, 0 SQL files
and 0 Go calculators** — the NONROAD path in canonical MOVES is a Java class
that writes fixed-width files and shells out to `nonroad.exe`, so there is no
SQL graph to read the table set off. The authoritative list is therefore the
calculator's declared inputs:

- `crates/moves-calculators/src/calculators/nonroad_emission.rs:77-131` —
  `NONROAD_INPUT_TABLES`, 36 entries, surfaced through
  `Calculator::input_tables` (`:180-182`). The snapshot loader only admits
  tables in the union of every calculator's declared inputs.

I cross-checked each declared name against the actual `store.get("…")` calls in
the data-plane loader `crates/moves-calculators/src/calculators/nonroad_loader.rs`.
The result splits cleanly into *read* and *declared-but-unread*.

The snapshot holds 324 tables, 204 with rows. Only the 21 below are consumed.

### 1.2 Tables that carry data into the calculation

Row counts are this snapshot's. All decimal columns are stored as **zero-padded
strings** in the Parquet, all integer keys as `int64` — see
`nonroad_loader.rs:19-26` and the `int_col`/`float_col`/`str_col` helpers at
`:103`, `:148`, `:187`, which resolve column names case-insensitively and accept
either physical type.

| # | Table | Rows | Columns used (type) | Role | Read at |
|---|---|---|---|---|---|
| 1 | `nremissionrate` | 55 471 | `polProcessID` i64, `SCC` str, `hpMin` i64, `hpMax` i64, `modelYearID` i64, `engTechID` i64, `meanBaseRate` str→f32, `units` str | Zero-hour exhaust emission factors **and** BSFC (`polProcessID 9901`), hp-binned per `(SCC, engTechID)`. The `.EMF` file. | `nonroad_loader.rs:298-330` |
| 2 | `nrdeterioration` | 424 | `polProcessID` i64, `engTechID` i64, `DFCoefficient` str→f32, `DFAgeExponent` str→f32, `emissionCap` i64→f32 | Deterioration `(A, B, cap)` per `(polProcessID, engTechID)`. | `:267-296` |
| 3 | `nrengtechfraction` | 9 554 | `SCC` str, `hpMin` i64, `hpMax` i64, `modelYearID` i64, `processGroupID` i64, `engTechID` i64, `NREngTechFraction` str→f32 | Technology mix by model year. **`processGroupID = 1` only** for exhaust (2 = evap, different hp binning). The `.TECH` file. | `:331-355`, `:1360-1440` |
| 4 | `nrsourceusetype` | 1 183 | `sourceTypeID` i64, `SCC` str, `hpAvg` str→f32, `hoursUsedPerYear` str→f32, `loadFactor` str→f32, `medianLifeFullLoad` str→f32 | One *equipment point* per row: the activity and physical parameters. (`NRHPRangeBinID` and the ~25 evap/tank columns are present but unused on the exhaust path.) | `:1175-1266` |
| 5 | `nrbaseyearequippopulation` | 62 699 | `sourceTypeID` i64, `stateID` i64, `population` str→f64, `NRBaseYearID` i64 | Base-year (1990) equipment population per state. | `:1182`, `:1207-1226`, `:1448-1455` |
| 6 | `nrscrappagecurve` | 197 | `NREquipTypeID` i64, `fractionLifeUsed` str→f32, `percentageScrapped` str→f32 | The **default (`NREquipTypeID = 0`)** scrappage curve, 197 points from `(0.0, 0%)` to `(2.0, 100%)`. Required — an absent/empty curve is a hard error. | `:1532-1568` |
| 7 | `nrgrowthpatternfinder` | 4 189 | `SCC` str, `stateID` i64, `growthPatternID` i64 | SCC (+ state) → growth pattern. State-specific rows win over `stateID = 0`. | `:1471-1495` |
| 8 | `nrgrowthindex` | 50 955 | `growthPatternID` i64, `yearID` i64, `growthIndex` i64 | Growth indicator time series. **Truncated toward zero** on load — `value: (idx[i] as i64) as f32` (`:1516`). | `:1497-1519` |
| 9 | `nrscc` | 214 | `SCC` str, `NREquipTypeID` i64, `fuelTypeID` i64 | SCC → equipment type and *nonroad* fuel type. | `:982-997`, `:999-1031`, `:1079-1117` |
| 10 | `nrequipmenttype` | 88 | `NREquipTypeID` i64, `sectorID` i64, `surrogateID` i64 | Equipment type → sector and spatial surrogate. Together with `nrscc` this is the DB form of NONROAD's `ALLOCATE.XRF`. | `:1001-1008`, `:1081-1088` |
| 11 | `nrstatesurrogate` | 62 821 | `surrogateID` i64, `stateID` i64, `countyID` i64, `surrogatequant` str→f64, `surrogateYearID` i64 | State→county allocation surrogate quantities. The `.ALO` files. | `:1033-1077` |
| 12 | `nrmonthallocation` | 46 428 | `SCC` str, `stateID` i64, `monthID` i64, `monthFraction` str→f32 | Monthly activity fractions, keyed by state. | `:1891-1926`, `:2231-2259` |
| 13 | `nrdayallocation` | 210 | `scc` **(lowercase)** str, `dayID` i64, `dayFraction` str→f32 | Weekday/weekend activity fractions. dayID 5 = weekday → slot 0, 2 = weekend → slot 1. | `:1928-1948`, `:2261-2270` |
| 14 | `nrsulfuradjustment` | 133 | `fuelTypeID` i64, `engTechID` i64, `PMBaseSulfur` str→f32, `sulfatePMConversionFactor` str→f32 | Per-tech PM base sulfur / conversion overrides, **filtered to `fuelTypeID ∈ {23, 24}`**. Loaded and wired (`executor.rs:1479-1487`) but inert for this fixture: only diesel PM and the SOx EF rewrite consume it, and this fixture is gasoline-only with SOx not selected. | `:1635-1662` |
| 15 | `nrfuelsupply` | 7 880 | `fuelRegionID` i64, `fuelYearID` i64, `monthGroupID` i64, `fuelFormulationID` i64, `marketShare` str→f64 | Fuel-supply market shares. | `:1709`, `:1780-1836` |
| 16 | `fuelformulation` | 2 158 | `fuelFormulationID` i64, `fuelSubtypeID` i64, `sulfurLevel` str→f64, `ETOHVolume`/`MTBEVolume`/`ETBEVolume`/`TAMEVolume` str→f64, `volToWtPercentOxy` str→f64 | Per-formulation oxygenate and sulfur content. | `:1709-1740` |
| 17 | `nrfuelsubtype` | 17 | `fuelSubtypeID` i64, `fuelTypeID` i64 | Fuel subtype → fuel type. | `:1741-1748` |
| 18 | `regioncounty` | 2 | `regionID` i64, `countyID` i64, `regionCodeID` i64, `fuelYearID` i64 | County → nonroad fuel region (**`regionCodeID = 2`**). | `:1763-1778` |
| 19 | `year` | 63 | `yearID` i64, `fuelYearID` i64 | Calendar year → fuel year. | `:1752-1761` |
| 20 | `zonemonthhour` | 930 816 | `monthID` i64, `zoneID` i64, `hourID` i64, `temperature` str→f64 | Hourly ambient temperature. **Daytime mean over `hourID ∈ [6, 18]`.** | `:1586-1633` |
| 21 | `zone` | 3 232 | `zoneID` i64, `countyID` i64 | Zone → county, to scope `zonemonthhour`. | `:1596-1602` |
| 22 | `runspecsector` | 1 | `sectorID` i64 | RunSpec sector selection (= 7). | `:959-965` |
| 23 | `runspecfueltype` | 2 | `fuelTypeID` i64 | RunSpec fuel selection (= {1, 2}). | `:973-980` |
| 24 | `runspecpollutantprocess` | 4 | `polProcessID` i64 | Gates which engine pollutant slots reach `MOVESOutput`; `pollutantID = polProcessID / 100`. | `:2192-2200` |

(Numbering runs to 24 because #22–24 are RunSpec-scope tables rather than
model data; 21 of the 24 carry model data proper.)

`nrevapemissionrate` (718 rows) is also read (`:632-660`, `:690-814`) and builds
`EvapTechEntry` values, but **contributes nothing to this fixture's output**:
evap species occupy engine pollutant slots 7–16, and `SLOT_POLLUTANT`
(`nonroad_loader.rs:2183`) maps only slots 0, 1, 2, 3, 4, 5 onto MOVES
pollutant IDs.

### 1.3 Tables declared but not read

Every one of these is in `NONROAD_INPUT_TABLES` (so the snapshot loader admits
it), but no `store.get` in the loader touches it. An `.esm` port should **not**
model them for this fixture.

| Table | Rows | Why unread |
|---|---|---|
| `nrhourallocation` | 72 | Hourly allocation is not applied. Canonical NONROAD output is a *typical day*; the output rows carry `hourID = 0`. |
| `nrhourallocpattern` | 3 | ditto |
| `nrhourpatternfinder` | 89 | ditto |
| `nrgrowthpattern` | 1 185 | Description text only; the pattern ID comes from `nrgrowthpatternfinder`. |
| `nrhprangebin` | 18 | Used only by the *post-processing* summary scripts (`moves-framework/src/aggregation/nonroad_postprocess.rs:139`), not the emission chain. HP binning inside the chain comes from the `hpMin`/`hpMax` columns on `nremissionrate` / `nrengtechfraction`. |
| `nrhpcategory` | 2 268 | Not referenced. |
| `nragecategory` | 51 | Not referenced; ages come from `scrptime`'s `nyrlif`. |
| `nrmodelyear` | 120 | Not referenced; model years are derived as `episode_year − age_index`. |
| `nrretrofitfactors` | **0** | Empty in this snapshot; retrofit is disabled. |
| `nrsourceusetypephysicsmapping` | **absent** | Declared, but the file does not exist in this snapshot. |
| `runspecmonth` | 1 | Declared but *not read by the loader* — the month reaches the calculator through the master-loop iteration position (`nonroad_emission.rs:222`). It is nonetheless the correct place for an `.esm` port to read `monthID = 8` from. |

### 1.4 Tables with rows that are *not* inputs to this chain

`nrmethanethcratio`, `nrcrankcaseemissionrate`, `nrusmonthallocation`,
`nratratio`, `nrdioxinemissionrate`, `nrmetalemissionrate`, `nrhcspeciation`,
`nrrocspeciation`, `nrpahgasratio`, `nrpahparticleratio`,
`nrintegratedspecies`, `nrprocessgroup` (0 rows) and the whole onroad tier
(`emissionratebyage`, `zonemonthhour`'s onroad users, `sourcetypeage…`, …) are
in the snapshot but outside the declared input set.

---

## 2. The computation chain

The chain runs once per `(county, year, month, day)` master-loop firing
(`nonroad_emission.rs:206-320`). Structurally it is:

```
for each SCC group                          (driver record group)
  for each equipment point (SCC, hpAvg)     ← nrsourceusetype row w/ population
    scrptime  → nyrlif, modfrc, yryrfrcscrp
    modyr     → actadj, detage
    agedist   → model-year fractions grown to 2020
    for each age index idxyr ∈ [0, nyrlif)  ← model year = 2020 − idxyr
      emfclc  → per-(pollutant, tech) EF, units, det coefficients, BSFC
      for each engine tech with fraction > 0
        clcems → short tons for each of THC/CO/NOx/CO2/SOx/PM
```

The section headings below follow PLAN.md Phase 2's seven components.

### 2.1 Geography and allocation

**Inputs:** `nrscc`, `nrequipmenttype`, `nrstatesurrogate`, RunSpec county.
**Output:** one scalar `allocFrac(SCC)` per SCC, and the state filter.

*SCC → surrogate* (`nonroad_loader.rs:999-1031`), a two-hop join:

```
nrscc.SCC → nrscc.NREquipTypeID → nrequipmenttype.NREquipTypeID → surrogateID
```

*State→county fraction* — port of `alocty.f` + `getind.f`
(`nonroad_loader.rs:1033-1077`):

```
allocFrac(surrogateID) = quant(county 26161) / quant(state row 26000)
```

where `state row = county_fips / 1000 * 1000` (`:1043`) and each FIPS's `quant`
is taken at the **latest `surrogateYearID` ≤ the episode year**, falling back to
the earliest year above it — `getind.f`'s `vallow`-else-`valhi` rule, **no
interpolation** (`:1052-1072`). `quant(state) ≤ 0` ⇒ fraction 0 (`:1076`).

For this fixture all three logging equipment types map to `surrogateID = 8`
(2002 Timber Product Output, cu ft):

```
allocFrac = 1 512 186 / 466 969 286 = 0.003 238 298 631 914 734
```

**Ordering matters.** The loader pre-allocates population in
`load_source_units` (`:1237-1245`), but canonical `prcsta.f` grows the age
distribution on the **state** population and allocates only afterwards. The
engine therefore divides `allocFrac` back out around its `age_distribution` call
— `build_alloc_fractions` (`:2088-2110`) exists purely to make that
un-allocation possible. The reason is numeric, not cosmetic: `agedist`'s
`MINGRWIND = 1e-4` clamp (`consts.rs:158`) is magnitude-sensitive, and a
pre-allocated sub-`1e-4` county population would balloon cohorts canonical
leaves alone.

**Net effect for §6's arithmetic:** age distribution is computed on the state
population; the county fraction multiplies the result.

### 2.2 Population

**Inputs:** `nrbaseyearequippopulation`, `nrsourceusetype`, `nrgrowthpatternfinder`,
`nrgrowthindex`, `nrscrappagecurve`.
**Output:** `population` (county, base-year) and `modfrc[idxyr]` (grown model-year
fractions).

#### (a) Base-year population, rounded

`nonroad_loader.rs:1207-1226`:

```rust
*pop_by_src.entry(pop_src[i]).or_default() += (pop_val[i] * 10.0).round() / 10.0;
```

Canonical writes each state population row to the `.POP` file with `%17.1f`
(`NonroadDataFileHelper.generatePopFile`), so the engine only ever sees
populations **rounded to one decimal**. This is load-bearing: sub-0.05 rows round
to zero and contribute nothing. `NRBaseYearID = 1990` for every row
(`:1448-1455`).

#### (b) Growth factor — `grwfac.f`

`crates/moves-nonroad/src/population/growth.rs:53-56`:

```
factor = (growthyearind − baseyearind) / (baseyearind * (growth_year − base_year))
```

i.e. the **annualized** fractional change, not the cumulative ratio.
FIPS-match precedence is county → state (`XX000`) → national (`00000`)
(`growth.rs:36-40`). Between tabulated years the indicator is linearly
interpolated; outside the range it is extrapolated from the boundary
year-to-year change and clamped at 0. `growth_year == base_year` ⇒ factor 0;
both indicators zero ⇒ factor 0 (`growth.rs:44-47`).

The indicator values themselves were truncated toward zero at load
(`nonroad_loader.rs:1509-1517`) because canonical writes the `/GROWTH/` packet
with `%20d`. The year-over-year factors sit near zero, so *the fraction decides
the sign* — and with it which sale-years `agedist`'s `max(0, …)` clamp zeroes
out. This is exactly what produces the gappy model-year set for `2265007010`
(1991, 2000–2002, 2006–2010 are absent from the output).

#### (c) Scrappage — `scrptime.f`

`crates/moves-nonroad/src/driver/scrptime.rs:84-176`.

```rust
let life_cap = (MXAGYR / 2) as f32;                                       // :101  = 25.0
let median_life_years = life_cap.min(median_life_hours / load_factor / activity_hours_per_year); // :102
let median_life_per_year = 1.0_f32 / median_life_years;                   // :105
```

Note the left-to-right division order — `(mdlfhrs / ldfctr) / acthpy`.

Per-age cumulative scrappage walk (`:110-135`):

```rust
for iage in 2..=MXAGYR {
    let frac_life_used = (iage as f32 - 1.0) * median_life_per_year;
    pct_scrapped[cur] = find_scrappage_percent(frac_life_used, curve);
    let year_frac_scrapped = (pct_scrapped[cur] - pct_scrapped[prev]) / 100.0;
    if pct_scrapped[prev] >= 100.0 {
        if nyrlif == 0 { nyrlif = iage - 1; }
        yryrfrcscrp[cur] = 0.0;
    } else {
        yryrfrcscrp[cur] = 100.0 * year_frac_scrapped / (100.0 - pct_scrapped[prev]);
    }
}
```

`find_scrappage_percent` (`crates/moves-nonroad/src/output/find.rs:233-244`) is a
**step function, not an interpolation** — it returns the percent of the last
breakpoint at or below `frac_life_used`:

```rust
pub fn find_scrappage_percent(frac_life_used: f32, points: &[ScrappagePoint]) -> Option<f32> {
    let first = points.first()?;
    if frac_life_used < first.bin { return Some(first.percent); }
    for win in points.windows(2) {
        if win[1].bin > frac_life_used { return Some(win[0].percent); }
    }
    points.last().map(|p| p.percent)
}
```

`nyrlif` — the number of model years the equipment spans — is the first age at
which cumulative scrappage reaches 100 %. Because the default curve reaches
100 % at `fractionLifeUsed = 2.0`, `nyrlif ≈ 2 × medianLifeYears + 1`.

Sales growth and the initial age distribution (`:139-172`):

```rust
let sales_growth = pop_growth_factor
    / ((-1.4306_f32 * pop_growth_factor) * median_life_years
        + (-0.24_f32 * pop_growth_factor)
        + 1.0);
let initial_sales = 1000.0_f32;
sales[i] = initial_sales + (initial_sales * sales_growth * i as f32);
...
surviving[idx] = sales[nyrlif - iage] * (1.0 - pct_scrapped[idx] / 100.0);   // iage <= nyrlif, else 0
modfrc[idx]    = surviving[idx] / surviving_total;
```

`pop_growth_factor` is `grwfac(base_pop_year, base_pop_year + 1)` — i.e.
`growth_factor(1990, 1991)`, **not** the growth over the whole projection.

#### (d) Model-year adjustments — `modyr.f`

`crates/moves-nonroad/src/population/modyr.rs:294-318`. With the DEFAULT age
curve (which is what this fixture uses — `disc_code: "DEFAULT"`,
`executor.rs:543`):

```rust
actadj[i] = acttmp                                   // :299 (DEFAULT branch)
stradj[i] = strhrs
...
accum += a * eload;                                  // :311
detage[i] = if accum > 0.0 { accum / uselif_used } else { 0.0 };   // :312-316
```

`acttmp` is the activity converted to annual hours (`modyr.rs:78-88`): for
`HoursPerYear` it is `hoursUsedPerYear` unchanged; `HoursPerDay` ⇒ `× 365`;
`GallonsPer*` ⇒ `1 / (2·uselif)`. `eload` = `loadFactor`, `uselif` =
`medianLifeFullLoad`.

So **the deterioration "age" is the cumulative fraction of median life
consumed**, not an age in years:

```
detage[idxyr] = (idxyr + 1) · hoursUsedPerYear · loadFactor / medianLifeFullLoad
```

This is why `emissionCap` values of 1 and 2 make sense: they cap deterioration
at one and two full useful lives. `uselif <= 0` is bumped to 1.0 *after* the
`scrptime` call (`modyr.rs:290-292`).

#### (e) Growing the age distribution — `agedist.f`

`crates/moves-nonroad/src/population/agedist.rs:128-166`, forward-growth branch:

```rust
let mut totpop = base_population;
for iyear in (base_year + 1)..=growth_year {
    let tmpfrc: Vec<f32> = mdyrfrc_out.clone();          // snapshot BEFORE any update
    let grwthfc = growth_fn(iyear - 1, iyear)?.factor;
    if grwthfc != 0.0 { totpop = totpop.max(MINGRWIND); }        // MINGRWIND = 1e-4
    totpop = (totpop * (1.0 + grwthfc)).max(0.0);
    let totpopfrc = totpop / base_population;
    let mut frcsum: f32 = 0.0;
    for iage in 1..MXAGYR {
        let updated = (tmpfrc[iage - 1] * (1.0 - yryrfrcscrp[iage])).max(0.0);
        mdyrfrc_out[iage] = updated;
        frcsum += updated;
    }
    mdyrfrc_out[0] = totpopfrc - frcsum;                 // NOT clamped — may go negative
}
```

Three properties an `.esm` port must reproduce exactly:

1. `tmpfrc` is snapshotted before the age loop (a shift, not an in-place scan).
2. The newest-model-year slot is a **residual**, `totpopfrc − frcsum`, written
   *after* the older ages are summed, and is **not clamped**. When the growth
   index dips, this goes negative and the model year is dropped (see 4 below).
3. The `MINGRWIND` clamp applies to `totpop`, once per year, only when the growth
   factor is non-zero.

Because forward growth leaves `base_population` untouched and folds the growth
into `mdyrfrc`, the fractions **sum to the cumulative growth ratio**, not to 1:

```
Σ modfrc  =  totpop / base_population  =  G(2020) / G(1990)
```

4. Downstream, `prccty.f`'s record loop skips any model year with
   `modfrc ≤ 0`, which is what makes the model-year sets gappy.

### 2.3 Activity

**Inputs:** `nrsourceusetype` (`hoursUsedPerYear`, `loadFactor`, `hpAvg`),
`nrmonthallocation`, `nrdayallocation`.

`build_activity_entries` (`nonroad_loader.rs:1330-1358`) builds **one activity
row per `(SCC, hpAvg)` point**, with a *point* HP range so the engine's
`find_activity(scc, hp)` resolves the same row canonical `fndact` does. This
matters: hours/year vary by HP bin within an SCC.

- `activity_level  = hoursUsedPerYear`, `activity_unit = HoursPerYear`
- `load_factor     = loadFactor`
- `age_code        = "DEFAULT"`

Activity is built **unscoped (national)** — only population is geographically
allocated (`:1325-1329`).

*Temporal allocation* — `daymthf.f`, `crates/moves-nonroad/src/driver/daymthf.rs:72-125`:

```rust
for month in 0..12 {
    if months_selected[month] { month_factor += monthly[month]; n_days += MONTH_DAYS[month]; }
    ...
}
let day_of_week_factor = if total_mode { 1.0 } else {
    let base = if weekday_selected { daily[0] } else { daily[1] };
    7.0 * base
};
```

and the period factors, `crates/moves-nonroad/src/geography/common.rs:987-1010`:

```rust
let adjtime = match sum_type { SumType::Total => 1.0, SumType::Typical => 1.0 / (n_days.max(1) as f32) };
let tplfac  = if daily_mode { dayf } else { mthf * dayf };
let tplful  = mthf * dayf;
```

with `temporal_adjustment` (`common.rs:1019-1024`) selecting `tplfac` for
`HoursPerYear` / `GallonsPerYear` units and `1.0` for the per-day units.
MOVES always runs typical-day (`nonroad_loader.rs:2129`, `total_mode: false`).

For this fixture:

```
mthf    = monthFraction(SCC, state 26, month 8)
dayf    = 7 × dayFraction(SCC, dayID 5)
ndays   = 31              (August)
adjtime = 1/31
tpltmp  = mthf × dayf
```

The **combined** temporal scale on an annual quantity is therefore

```
mthf × 7 × dayFraction / ndays
```

which is exactly what `build_temporal_factors` documents at
`nonroad_loader.rs:2213-2222`. Note that `build_temporal_factors` is *not* used
here: the engine applies temporal scaling internally once
`reference.temporal_profiles` is non-empty, and the post-processing map is left
empty to avoid double-counting (`nonroad_emission.rs:290-299`).

*Two independent SCC fallback searches.* Canonical searches the `/MONTHLY/` and
`/DAILY/` packets separately, each with its own global-code fallback. The tables
key at different granularities, so a naive per-SCC merge would pin one dimension
to its default. `scc_lookup` (`nonroad_loader.rs:1839-1852`) implements the
fallback: exact SCC, then progressively zero trailing digit groups of width 2, 4,
6:

```
2265007010 → 2265007000 → 2265000000 → 2265000000
```

Missing after fallback ⇒ the canonical defaults `defmth = 1/12`,
`defday = 1/7` (**not** a neutral 1.0) — `nonroad_loader.rs:2273-2288`.

For all three logging SCCs the match is at the 8-digit level:
`monthFraction = 0.0833333`, `dayFraction = 0.166667`, so

```
tpltmp = 0.0833333 × (7 × 0.166667) = 0.097 222 4
combined temporal scale = tpltmp / 31 = 0.003 136 205 734 764 5
```

### 2.4 Emission factors with deterioration (`emfclc.f`)

**Inputs:** `nremissionrate`, `nrengtechfraction`, `nrdeterioration`,
`nrsourceusetype`.
**Output:** per-`(SCC, hpAvg)` entry — `emission_factors`, `emission_units`,
`det_a`, `det_b`, `det_cap`, `bsfc`, `tech_names`, `tech_fractions_by_year`.

`build_entries_from_mix` (`nonroad_loader.rs:374-507`) is the canonical
two-separate-files model:

1. **The tech mix defines the tech list.** Take the distinct `(SCC, hpAvg)` pairs
   from `nrsourceusetype` (`:381-389`, quantised to milli-hp for dedup). Find the
   `nrengtechfraction` bin containing `hpAvg`, walking the SCC chain
   `[SCC, equipRoot, familyRoot]` where `equipRoot = SCC[0..7] + "000"`
   (`:816-824`) and `familyRoot = SCC[0..4] + "000000"` (`:826-837`). The first
   chain element with a covering bin wins (`:412-419`). Its `engTechID` set,
   truncated at `MXTECH = 32`, is the entry's tech list.
2. **Each tech's rates are looked up independently**, walking the same chain but
   with its *own* hp binning (`:433-461`). Mixes and rates key at different SCC
   levels for the same equipment, so each lookup must walk the full chain.
   `hp_pick` (`:357-362`) takes the first bin with `lo ≤ hp ≤ hi` — note both
   bounds inclusive.
3. **Deterioration** attaches by `(polProcessID, engTechID)` (`:457-461`).
4. **BSFC** is `polProcessID = 9901`, stored separately (`:308-311`) and never
   run through the units parser — its `units` column is empty in this snapshot,
   which would otherwise panic (`unit_code_for`, `:217-234`).

*Tech mix by model year.* `ExhaustTechEntry::fractions_for_year`
(`crates/moves-nonroad/src/simulation/inputs.rs:196-207`): exact year, else the
**latest year ≤ the requested year**, else the earliest. The requested year is

```rust
let tchmdyr = (options.episode_year - year_index as i32).min(options.tech_year);
```
— `crates/moves-nonroad/src/simulation/executor.rs:1449` (`prccty.f`:
`idxyr = iepyr - iyr + 1; tchmdyr = min(iyr, itchyr)`), with
`tech_year = episode_year = 2020` (`options.rs:130`).

*The deterioration curve* — `crates/moves-nonroad/src/emissions/exhaust.rs:833-836`:

```rust
pub fn apply_deterioration(coef: &DeteriorationCoefficients, age: f32) -> f32 {
    let effective_age = if age <= coef.cap { age } else { coef.cap };
    1.0 + coef.a * effective_age.powf(coef.b)
}
```

**The cap is applied to the age argument, not to the resulting multiplier** —
which matters whenever `B ≠ 1`, and `B = 0.5` for every 4-stroke tech in this
fixture. `age` is `detage[idxyr]` from §2.2(d).

*Missing factors.* When no rate is found and `tech_fraction > 0`, the EF cell is
set to `RMISS = −9.0` (`exhaust.rs:807-816`, `consts.rs:339`) and the missing
value propagates through `clcems` (`exhaust.rs:1211-1219`). When
`tech_fraction == 0` the cell is left at 0 with no warning (`:817-823`).

### 2.5 Adjustments (`emsadj.f`)

**Inputs:** `zonemonthhour` + `zone` (temperature), `nrfuelsupply` +
`fuelformulation` + `nrfuelsubtype` + `regioncounty` + `year` (fuel),
`nrsulfuradjustment` (sulfur alternates).
**Output:** `adjfac[pollutant][julian day]`, all starting at 1.0.

`calculate_emission_adjustments` — `exhaust.rs:497-681`.

#### (a) Ambient temperature

`build_ambient_temp` (`nonroad_loader.rs:1586-1633`) is the port of the `.opt`
`Average temper.` query:

```sql
SELECT avg(temperature) FROM zonemonthhour t
INNER JOIN zone z ON t.zoneid = z.zoneid
WHERE z.countyid = ? AND t.monthid = ? AND hourid >= 6 AND hourid <= 18
```

One **daytime (hourID 6–18)** mean per bundle county, applied to every SCC. The
mean is accumulated in `f64` and cast to `f32` at the end (`:1627-1631`). It
**must** be the run month's — a `month = 0` annual mean would be ~57 °F instead
of ~76 °F in August and inflate 4-stroke NOx ~18 % (`nonroad_loader.rs:2060-2072`).
Absent temperature is a hard error, not a silent 75 °F bypass
(`executor.rs:945-952`).

For this fixture: zone `261610`, month 8, 13 hours ⇒ **`tamb = 73.576 924 °F`**.

#### (b) Temperature correction — THC/CO/NOx

`exhaust.rs:539-567` (4-stroke gasoline):

```rust
let (a_thc, a_co, a_nox) = if tamb <= 75.0 {
    (-0.00240_f32, 0.0015784_f32, -0.00892_f32)
} else {
    (0.00132_f32, 0.00375_f32, -0.00873_f32)
};
let dt = tamb - 75.0;
multiply(&mut table, PollutantIndex::Thc, jday_idx, (a_thc * dt).exp());
multiply(&mut table, PollutantIndex::Co,  jday_idx, (a_co  * dt).exp());
multiply(&mut table, PollutantIndex::Nox, jday_idx, (a_nox * dt).exp());
```

`exhaust.rs:568-596` (2-stroke gasoline): all three coefficients are `0.0`, so
`exp(0·dt) = 1` — a documented no-op kept so a future data update edits one
place. Note the asymmetry the Fortran has and the port preserves: on the
`tamb < 75` branch 2-stroke NOx is **not** written at all.
Diesel/CNG/LPG: no temperature correction (`_ => {}`, `:597`).

> **Naming note for PLAN.md.** PLAN.md §3 Phase 1 calls this "the
> temperature-adjustment quadratic". As implemented it is **not** a quadratic —
> it is an exponential in a linear term, `exp(a · (T − 75))`, with the
> coefficient `a` selected by a threshold at 75 °F and by fuel/pollutant. The
> only genuine quadratics in `emsadj.f` are the permeation corrections
> (`exhaust.rs:664-666`), which this fixture does not exercise. The
> `expression_template` should be named for what it is.

#### (c) Oxygenate correction — THC/CO/NOx

`exhaust.rs:600-626`, applied only when **not** RFG and the fuel is gasoline:

```rust
// 4-stroke
multiply(… Thc …, 1.0 - 0.045 * oxy);
multiply(… Co  …, 1.0 - 0.062 * oxy);
multiply(… Nox …, 1.0 - (-0.115) * oxy);
// 2-stroke
multiply(… Thc …, 1.0 - 0.006 * oxy);
multiply(… Co  …, 1.0 - 0.065 * oxy);
multiply(… Nox …, 1.0 - (-0.186) * oxy);
```

`oxy` is the market-share-weighted gasoline oxygen weight percent, computed by
`build_fuel_properties` (`nonroad_loader.rs:1697-1868`) over the county's nonroad
fuel region:

```
oxy = Σ_gasoline-rows  marketShare × (ETOHVolume + MTBEVolume + ETBEVolume + TAMEVolume) × volToWtPercentOxy
```

with the supply rows filtered to `regionCounty.regionCodeID = 2 AND countyID = 26161
AND fuelYearID = year.fuelYearID(2020)` and `nrfuelsupply.monthGroupID = 8`
(`:1763-1778`, `:1794-1817`). **There is no fallback** — an empty join gives 0.0,
which is load-bearing behaviour (`:1720-1726`). The `fuelYearID` filter is
essential: a county capture carries every fuel year 1990–2060 and without it the
oxygen sum reaches ~140 wt% (`:1789-1793`).

For this fixture: one gasohol row, `marketShare = 1.0`, `ETOHVolume = 10.0`,
`volToWtPercentOxy = 0.3653` ⇒ **`oxy = 3.653` wt%**, `rfg = false`
(RFG share 0 of gasoline share 1.0; the RFG flag is
`gas_share > 0 && rfg_share / gas_share > 0.5`, `:1854`).

#### (d) Sulfur correction — SOx only

`exhaust.rs:632-643`:

```rust
let base = inputs.sox_base[fuel_slot];
let mut soxcor = inputs.sox_fuel[fuel_slot] / base;
if inputs.scc.starts_with("2282020") || inputs.scc.starts_with("2280002") {
    soxcor = inputs.sox_diesel_marine / base;
}
multiply(&mut table, PollutantIndex::Sox, jday_idx, soxcor);
```

`sox_base = [SWTGS2, SWTGS4, SWTDSL, SWTLPG, SWTCNG]` and `sox_fuel` is the
run's in-use sulfur weight % from the supply join
(`executor.rs:993-1002`; `Σ marketShare × sulfurLevel / 10 000` per fuel,
`nonroad_loader.rs:1818-1836`). **SOx (pollutantID 31) is not selected by this
RunSpec**, so this correction has no effect on the 144 output rows.

#### (e) Not exercised here

Altitude (`exhaust.rs:647-661`, `high_altitude: false`), RFG bins
(`:665-687`, `rfg = false`), permeation temperature corrections
(`:664-676`, evap slots only).

### 2.6 Unit conversion (`unitcf.f`) and the exhaust roll-up (`clcems.f`)

#### (a) Unit conversion

`exhaust.rs:249-276`:

```rust
match unit {
    EmissionUnitCode::GramsPerHpHour => hp_avg * load_factor,
    EmissionUnitCode::GramsPerGallon => match activity_unit {
        ActivityUnit::GallonsPerYear | ActivityUnit::GallonsPerDay => 1.0,
        _ => if density == 0.0 { 0.0 } else { (bsfc * load_factor * hp_avg) / density },
    },
    EmissionUnitCode::GramsPerDay => 1.0,
    EmissionUnitCode::Multiplier  => 1.0,
    _ => 1.0,      // G/HR, G/START, G/M2/DAY: pass-through
}
```

Every exhaust rate in this fixture is `g/hp-hr`, so `cvttmp = hpAvg × loadFactor`.
The unit string is parsed by `unit_code_for` (`nonroad_loader.rs:217-234`), which
**panics** on an unrecognized keyword rather than defaulting to `g/HP-hr` —
canonical `rdemfc.f` errors likewise.

#### (b) The roll-up

`calculate_exhaust_emissions` — `exhaust.rs:1014-1234`. Per `(julian day,
pollutant)`:

```rust
let detrat = apply_deterioration(&det, inputs.equipment_age);                 // :1064
let cvttmp = unit_conversion_factor(unit, hp_avg, load_factor, activity_unit,
                                    fuel_density, bsfc);                      // :1067
let adjems = inputs.daily_adjustments.get(pollutant, jday_idx);               // :1078
let mut emstmp = inputs.emission_factors[ef_cell]
    * cvttmp
    * detrat
    * adjems
    * inputs.adjustment_time;                                                 // :1079-1083
```

then, for a normal (non-start, non-`g/day`) pollutant, `exhaust.rs:1201-1208`:

```rust
emstmp
    * inputs.activity_adjustment      // actadj[idxyr]  = hoursUsedPerYear
    * tpltmp2                         // temporal_adjustment = mthf × dayf
    * inputs.population               // county base-year population
    * inputs.model_year_fraction      // modfrc[idxyr] (grown)
    * tchfrc                          // tech fraction for this model year
```

with the two other branches at `:1186-1200`: start pollutants
(`idxspc ≥ IDSTHC = 18`) use `starts_adjustment` instead of
`activity_adjustment`, and `g/day` units use `n_days`.

Retrofit and conversion, `exhaust.rs:1221-1229`:

```rust
let retro = inputs.retrofit_reduction[pollutant.slot()];
if retro > 0.0 { emiss *= 1.0 - retro; }
let temiss = emiss * CVTTON;                       // CVTTON = 1.102311e-06 short tons / gram
outputs.emissions_day[pollutant.slot()] += temiss;
outputs.emissions_by_model_year[pollutant.slot()] += temiss;
```

**Complete scalar form for one `(SCC, hpAvg point, model year, tech, pollutant)`
cell of this fixture** (all factors `f32`, evaluated in this order):

```
emsTons =  ((((EF × (hpAvg·loadFactor)) × DF) × adjems) × (1/ndays))
           × hoursUsedPerYear
           × (mthf · dayf)
           × population_county
           × modfrc[idxyr]
           × techFraction
           × CVTTON
```

where

```
DF                = 1 + A · min(detage[idxyr], cap)^B
detage[idxyr]     = (idxyr+1)·hoursUsedPerYear·loadFactor / medianLifeFullLoad
population_county = round1dp(pop_state) × allocFrac
modfrc            = agedist(scrptime(...), 1990 → 2020)   [sums to G(2020)/G(1990)]
adjems            = exp(a_p·(tamb−75)) × (1 − c_p·oxy)    [gasoline; 1.0 for PM]
```

#### (c) The BSFC-derived species (not selected here, but part of `clcems`)

**SOx** (`exhaust.rs:1092-1114`) rewrites the EF:

```rust
let cvtbck = 1.0 / (inputs.hp_avg * inputs.load_factor);
let new_ef = inputs.hp_avg
    * inputs.load_factor
    * (inputs.bsfc * GRMLB as f32 * (1.0 - soxcnv) - ems_thc * cvtbck)
    * 0.01
    * inputs.sox_base[fuel_slot]
    * 2.0;
emstmp = new_ef * adjems * inputs.adjustment_time;      // note: no detrat
```

**CO2** (`exhaust.rs:1131-1147`), the carbon balance:

```rust
let cvtbck = 1.0 / (inputs.hp_avg * inputs.load_factor);
let new_ef = inputs.hp_avg
    * inputs.load_factor
    * (inputs.bsfc * GRMLB as f32 - ems_thc * cvtbck)
    * cfrac
    * 44.0
    / 12.0;
emstmp = new_ef * detrat * adjems * inputs.adjustment_time;
```

`cfrac` is the fuel carbon mass fraction (`exhaust.rs:1029-1034`):
`CMFGAS = 0.87`, `CMFDSL = 0.87`, `CMFLPG = 0.817`, `CMFCNG = 0.717`.
`ems_thc` is the **un-adjusted** THC product `EF × cvttmp × detrat`, saved at
`exhaust.rs:1086-1088` — so the pollutant loop order (THC first, index 1) is
load-bearing.

**Crankcase HC** (`exhaust.rs:1118-1129`) multiplies the (MULT-unit) EF by
`ems_thc`.

**PM diesel sulfur correction** (`exhaust.rs:1150-1180`):

```rust
emstmp -= inputs.bsfc * GRMLB as f32 * inputs.hp_avg * inputs.load_factor
        * 7.0 * soxcnv * 0.01 * inputs.adjustment_time
        * (sulbas * adj_pm - inputs.sox_base[dsl_slot] * adj_sox);
```
guarded by `sulbas != 1.0`. Diesel only; inert here.

### 2.7 Output aggregation to the `MOVESOutput` schema

`emissions_to_dataframe` — `nonroad_loader.rs:2313-2392`.

- Only **by-model-year** rows are used (`model_year = Some`); the engine also
  emits per-record totals with `model_year = None`, and using both would
  double-count (`:2334-2341`).
- Pollutant slot → MOVES `pollutantID`, `SLOT_POLLUTANT` (`:2183`):
  `0→1 (THC), 1→2 (CO), 2→3 (NOx), 3→90 (CO2), 4→31 (SO2), 5→100 (PM10)`.
- Gated by `selected_output_pollutants` = `{polProcessID / 100}` from
  `runspecpollutantprocess` (`:2192-2200`) — here `{1, 2, 3, 100}`.
- Every selected pollutant of every `.BMY` record gets a row, **including zeros**
  (`:2354-2361`); canonical clamps at zero (`Math.max(0, …)`) because the SOx
  balance can go negative, and keeps the row.
- Short tons → grams: `× 1/1.102311e-6` (`GRAMS_PER_SHORT_TON`, `:2177`).
- `processID` is hard-coded to `1` (`:2371`).

Resulting emitted columns (`:2380-2390`): `yearID, monthID, dayID, hourID,
pollutantID, processID, modelYearID, SCC, emissionQuant`.

The canonical `MOVESOutput` for this fixture additionally carries
`MOVESRunID = 1`, `iterationID = 1`, `stateID = 26`, `countyID = 26161`,
`fuelTypeID = 1`, `roadTypeID = 100`, `hourID = 0`, and leaves
`zoneID, linkID, sourceTypeID, regClassID, fuelSubTypeID, engTechID, sectorID,
hpID, emissionQuantMean, emissionQuantSigma` NULL. See §8.3 — the Rust port
currently leaves `stateID/countyID/fuelTypeID/roadTypeID` NULL too, which an
`.esm` port should *not* copy.

**Group-by key for the 144 rows:**
`(yearID, monthID, dayID, hourID, stateID, countyID, pollutantID, processID,
fuelTypeID, modelYearID, roadTypeID, SCC)` with `SUM(emissionQuant)`.
Because `hpclass`, `sourceusetype` and `offroadscc` are deselected in the
RunSpec, the three `2265007010` HP points and every engine-tech slot collapse
into one row per `(SCC, modelYear, pollutant)`.

---

## 3. Join structure

Every join in the chain, in the order it is needed. "Key pairs" are exact column
names as they appear in the snapshot Parquet (note the casing inconsistencies —
`nrdayallocation.scc` is lowercase, `nrhpcategory` is fully lowercase).

| # | Left relation | Right relation | Key pairs | Card. | Purpose / code |
|---|---|---|---|---|---|
| J1 | `nrscc` | `nrequipmenttype` | `nrscc.NREquipTypeID = nrequipmenttype.NREquipTypeID` | n:1 | SCC → sector, surrogate. `nonroad_loader.rs:999-1031`, `:1079-1117` |
| J2 | `nrscc` (via J1) | `runspecsector` | `nrequipmenttype.sectorID = runspecsector.sectorID` | n:1 (semi) | Sector selection. `:1119-1174` |
| J3 | `nrscc` | `runspecfueltype` | `nrscc.fuelTypeID = runspecfueltype.fuelTypeID` | n:1 (semi) | Fuel selection. `:1119-1174` |
| J4 | `nrsourceusetype` | `nrbaseyearequippopulation` | `nrsourceusetype.sourceTypeID = nrbaseyearequippopulation.sourceTypeID` | 1:n (one pop row per state) | Attach population. `:1175-1266` |
| J5 | `nrbaseyearequippopulation` | RunSpec state | `nrbaseyearequippopulation.stateID = 26` | filter | State scope. `:1207-1213` |
| J6 | `nrstatesurrogate` (county row) | `nrstatesurrogate` (state row) | `surrogateID = surrogateID` AND `countyID = 26161` / `countyID = 26000` | 1:1 | Allocation ratio. `:1033-1077` |
| J7 | SCC (via J1) | J6 result | `nrequipmenttype.surrogateID = nrstatesurrogate.surrogateID` | n:1 | Per-SCC allocation fraction. `:1240-1245`, `:2088-2110` |
| J8 | equipment point | `nrgrowthpatternfinder` | `SCC = SCC` (with 3-step SCC fallback) AND `stateID ∈ {26, 0}` | n:1 | Growth pattern. `:1467-1495`, `:2044-2052` |
| J9 | growth pattern | `nrgrowthindex` | `growthPatternID = growthPatternID` | 1:n (by year) | Growth series. `:1497-1519` |
| J10 | equipment point | `nrscrappagecurve` | `NREquipTypeID = 0` (constant) | n:1 | Default scrappage curve. `:1532-1568` |
| J11 | equipment point | `nrengtechfraction` | `SCC = SCC` (3-step chain) AND `hpMin ≤ hpAvg ≤ hpMax` AND `processGroupID = 1` | 1:n (tech × modelYear) | Tech mix. `:400-425` |
| J12 | (SCC, tech) | `nremissionrate` | `SCC = SCC` (3-step chain, independent of J11) AND `engTechID = engTechID` AND `hpMin ≤ hpAvg ≤ hpMax` AND `polProcessID ∈ {101,201,301,10001}` | 1:1 per pollutant | Zero-hour EF. `:433-456` |
| J13 | (SCC, tech) | `nremissionrate` | same keys with `polProcessID = 9901` | 1:1 | BSFC. `:308-311`, `:435-443` |
| J14 | (pollutant, tech) | `nrdeterioration` | `polProcessID = polProcessID` AND `engTechID = engTechID` | n:1 | `(A, B, cap)`. `:267-296`, `:457-461` |
| J15 | equipment point | `nrmonthallocation` | `SCC = SCC` (`scc_lookup` fallback) AND `stateID ∈ {26, 0}` AND `monthID = 8` | n:1 | `mthf`. `:1891-1926` |
| J16 | equipment point | `nrdayallocation` | `SCC = scc` (`scc_lookup` fallback, **lowercase column**) AND `dayID = 5` | n:1 | `dayFraction`. `:1928-1948` |
| J17 | `zonemonthhour` | `zone` | `zonemonthhour.zoneID = zone.zoneID` | n:1 | Zone → county. `:1596-1602` |
| J18 | J17 result | RunSpec county | `zone.countyID = 26161` AND `monthID = 8` AND `6 ≤ hourID ≤ 18` | filter | Daytime temperature mean. `:1604-1626` |
| J19 | `year` | RunSpec year | `year.yearID = 2020` → `fuelYearID` | 1:1 | Fuel year. `:1752-1761` |
| J20 | `regioncounty` | RunSpec county + J19 | `countyID = 26161` AND `regionCodeID = 2` AND `fuelYearID = <J19>` | 1:n | Nonroad fuel region(s). `:1763-1778` |
| J21 | `nrfuelsupply` | J20 | `nrfuelsupply.fuelRegionID = regioncounty.regionID` AND `monthGroupID = 8` AND `fuelYearID = <J19>` | n:1 | Scope supply rows. `:1794-1817` |
| J22 | `nrfuelsupply` | `fuelformulation` | `fuelFormulationID = fuelFormulationID` | n:1 | Oxygenate + sulfur content. `:1709-1740` |
| J23 | `fuelformulation` | `nrfuelsubtype` | `fuelformulation.fuelSubtypeID = nrfuelsubtype.fuelSubtypeID` | n:1 | Subtype → fuel type. `:1741-1748` |
| J24 | tech name | `nrsulfuradjustment` | `engTechID = engTechID` AND `fuelTypeID ∈ {23, 24}` | n:1 | PM base-sulfur alternates. `:1635-1662`, `executor.rs:1479-1487` |
| J25 | engine output rows | `runspecpollutantprocess` | `pollutantID = polProcessID / 100` | n:1 (semi) | Output pollutant gate. `:2192-2200`, `:2344-2352` |

**Three joins are not equi-joins and need care in `.esm`:**

- **J11/J12/J13 hp containment** — `hpMin ≤ hpAvg ≤ hpMax`, both bounds
  **inclusive** (`hp_pick`, `nonroad_loader.rs:357-362`). A range predicate,
  not an `ON` clause; a `filter` is the honest spelling.
- **The SCC fallback chain** — J8/J11/J12/J13 use
  `[SCC, SCC[0..7]+"000", SCC[0..4]+"000000"]` (`:816-837`) and J15/J16 use
  `scc_lookup`'s zero-2/4/6-digits ladder (`:839-852`). These are *most-specific-
  match* joins, best modelled as a precomputed `SCC → matchedKey` mapping so
  the join itself stays an equi-join.
- **J8/J15 state precedence** — state-specific rows win over `stateID = 0`
  defaults; again best precomputed into an effective-key column.

**Two joins are on truncated/rounded values, not raw ones:** J4's population is
rounded to 1 dp before summing (`:1226`), and J9's `growthIndex` is truncated to
an integer at load (`:1516`).

---
