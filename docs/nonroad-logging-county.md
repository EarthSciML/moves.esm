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

## 4. Reusable shapes (`expression_templates`)

Each of these appears many times in the chain and should live once, in a library
file, imported by reference (PLAN.md §3 Phase 1).

### 4.1 `deterioration_factor`

The single most-reused expression: applied to every
`(pollutant, tech, model year)` cell.

```
deterioration_factor(A, B, cap, age) = 1 + A * min(age, cap)^B
```

Source: `crates/moves-nonroad/src/emissions/exhaust.rs:833-836`.
**The cap applies to the age argument, before the power** — with `B = 0.5`
(every 4-stroke tech here) capping the product instead would be wrong.
`age` is `detage`, a *fraction of median life consumed*, not years:

```
detage(idxyr) = (idxyr + 1) * hoursUsedPerYear * loadFactor / medianLifeFullLoad
```

(`crates/moves-nonroad/src/population/modyr.rs:308-317`.) With `A = 0` the whole
thing collapses to 1, which is how NOx deterioration is switched off for
2-stroke techs — so no special case is needed.

### 4.2 `exhaust_temperature_adjustment`

```
exhaust_temperature_adjustment(a_cold, a_hot, T)
    = exp( (T <= 75 ? a_cold : a_hot) * (T - 75) )
```

Source: `exhaust.rs:539-567`. Instantiated six ways (three pollutants × two
gasoline stroke counts); the 2-stroke instantiations have both coefficients 0.

| fuel | pollutant | `a_cold` (T ≤ 75) | `a_hot` (T > 75) |
|---|---|---|---|
| Gasoline 4-stroke | THC | −0.00240 | 0.00132 |
| Gasoline 4-stroke | CO | 0.0015784 | 0.00375 |
| Gasoline 4-stroke | NOx | −0.00892 | −0.00873 |
| Gasoline 2-stroke | THC, CO, NOx | 0.0 | 0.0 |
| Diesel / CNG / LPG | — | *not applied* | *not applied* |

Not a quadratic — see the naming note in §2.5(b).

### 4.3 `oxygenate_adjustment`

```
oxygenate_adjustment(c, oxy) = 1 - c * oxy
```

Source: `exhaust.rs:606-625`. Six instantiations:

| fuel | THC `c` | CO `c` | NOx `c` |
|---|---|---|---|
| Gasoline 4-stroke | 0.045 | 0.062 | −0.115 |
| Gasoline 2-stroke | 0.006 | 0.065 | −0.186 |

Gated on `not rfg` and gasoline. Keep the sign in the coefficient, as the source
does (`1.0 - (-0.115) * oxy`), so the template stays a single form.

### 4.4 `unit_conversion` (`unitcf.f`)

```
unit_conversion(unitCode, hpAvg, loadFactor, activityUnit, density, bsfc) =
      unitCode = g/hp-hr   ->  hpAvg * loadFactor
      unitCode = g/gallon  ->  activityUnit in {gal/yr, gal/day} ? 1
                               : density = 0 ? 0
                               : (bsfc * loadFactor * hpAvg) / density
      otherwise            ->  1
```

Source: `exhaust.rs:249-276`. Only the `g/hp-hr` branch fires in this fixture,
but the whole shape belongs in the library — the other NONROAD sectors use
`g/gallon` and `g/day`.

### 4.5 `scc_fallback_key`

Not an arithmetic template but the most-repeated *relational* shape — used by at
least six joins with two different ladders:

```
equipment_chain(SCC) = [SCC, SCC[0..7] ++ "000", SCC[0..4] ++ "000000"]     # rates, mixes, growth
scc_lookup_ladder(SCC) = [SCC, SCC[0..8] ++ "00", SCC[0..6] ++ "0000", SCC[0..4] ++ "000000"]
```

Sources: `nonroad_loader.rs:816-837` and `:839-852`. Model it as a build-time
`SCC → effective key` mapping per target table (a `skolem`, in PLAN.md §3 Phase 1
terms), so the run-time join stays a plain equi-join.

### 4.6 `state_default_precedence`

```
effective_row(SCC, state) = rows[state == 26] if any else rows[state == 0]
```

Used by `nrgrowthpatternfinder` (`:1477-1494`) and `nrmonthallocation`
(`:1898-1925`, `:2237-2258`). Same remark: precompute the effective key.

### 4.7 `temporal_scale`

```
temporal_scale(mthf, dayFraction, ndays) = mthf * (7 * dayFraction) / ndays
```

Sources: `driver/daymthf.rs:108-117` (the `7 ×`), `geography/common.rs:987-1010`
(the `1/ndays`), documented together at `nonroad_loader.rs:2213-2222`. In the
engine the two halves enter the product separately — `adjustment_time = 1/ndays`
inside `emstmp`, `tpltmp2 = mthf·dayf` outside — and mixing them up
double-applies the monthly factor (`executor.rs:1513-1519` spells out the
≈2.6× error for a 31-day month).

### 4.8 `carbon_balance_ef` (present in `clcems`, not exercised here)

```
co2_ef(hpAvg, loadFactor, bsfc, ems_thc, cfrac) =
    hpAvg * loadFactor * (bsfc * 453.6 - ems_thc / (hpAvg * loadFactor)) * cfrac * 44 / 12
```

Source: `exhaust.rs:1131-1147`. Worth putting in the library now: Phase 5's other
NONROAD sectors select CO2 (pollutantID 90).

---

## 5. Literals and enums

Everything below is a magic value the chain depends on. This is the `enums`
section for the `.esm` port.

### 5.1 Pollutants

| Name | MOVES `pollutantID` | NONROAD engine slot (0-based) | Fortran `IDX*` (1-based) |
|---|---|---|---|
| `TotalGaseousHydrocarbons` | 1 | 0 | `IDXTHC` = 1 |
| `CarbonMonoxide` | 2 | 1 | `IDXCO` = 2 |
| `OxidesOfNitrogen` | 3 | 2 | `IDXNOX` = 3 |
| `AtmosphericCO2` | 90 | 3 | `IDXCO2` = 4 |
| `SulfurDioxide` | 31 | 4 | `IDXSOX` = 5 |
| `PrimaryExhaustPM10Total` | 100 | 5 | `IDXPM` = 6 |

Slot↔ID map: `nonroad_loader.rs:2183` (`SLOT_POLLUTANT`). Full engine slot
enumeration (23 slots, `MXPOL`): `exhaust.rs:56-105` — crankcase 7, evap
8–17, start emissions 18–23. The exhaust loop skips slots 8–17
(`exhaust.rs:1046-1049`).

**Selected by this RunSpec:** 1, 2, 3, 100.

### 5.2 Processes and `polProcessID`

| Name | ID |
|---|---|
| `RunningExhaust` | 1 |

`polProcessID = pollutantID * 100 + processID` (`nonroad_loader.rs:59-60`).
Selected: `101, 201, 301, 10001`.

Two `polProcessID`s are structural, not pollutants:

| Constant | Value | Meaning | Source |
|---|---|---|---|
| `PP_BSFC` | 9901 | Brake-specific fuel consumption carrier (pollutant 99). Feeds the CO2/SOx branches; never emitted. | `nonroad_loader.rs:66` |

Processes the `NonroadEmissionCalculator` subscribes to (DAY granularity):
`1, 15, 18, 19, 20, 21, 30, 31, 32` (`nonroad_emission.rs:70`). Only 1 matters
here.

### 5.3 SCCs

| SCC | Description | `NREquipTypeID` | nonroad `fuelTypeID` | `sectorID` | `surrogateID` |
|---|---|---|---|---|---|
| `2260007005` | 2-Str Chain Saws > 6 HP | 71 | 1 | 7 | 8 |
| `2265007010` | 4-Str Shredders > 6 HP | 72 | 1 | 7 | 8 |
| `2265007015` | 4-Str Forest Eqp – Feller/Bunch/Skidder | 73 | 1 | 7 | 8 |
| `2270007010` | Dsl – Shredders > 6 HP | 72 | 23 | 7 | 8 |
| `2270007015` | Dsl – Forest Eqp – Feller/Bunch/Skidder | 73 | 23 | 7 | 8 |

SCC prefix → engine fuel kind, `crates/moves-nonroad/src/driver/run.rs:276-292`:

| Prefix test | `FuelKind` | Fortran index |
|---|---|---|
| `SCC[0..4] == "2260"` or `SCC[0..7] ∈ {2282005, 2285003}` | `Gasoline2Stroke` | 1 |
| `SCC[0..4] == "2265"` or `SCC[0..7] ∈ {2282010, 2285004}` | `Gasoline4Stroke` | 2 |
| `SCC[0..4] == "2270"` or `SCC[0..7] ∈ {2280002, 2282020, 2285002}` | `Diesel` | 3 |
| `SCC[0..4] == "2267"` or `SCC[0..7] == "2285006"` | `Lpg` | 4 |
| `SCC[0..4] == "2268"` or `SCC[0..7] == "2285008"` | `Cng` | 5 |

Two SCC prefixes carry a rec-marine diesel sulfur override in `emsadj.f`:
`"2282020"` and `"2280002"` (`exhaust.rs:637-639`).

### 5.4 Fuel types — the two namespaces, and why diesel drops out

MOVES **onroad** `fueltype` (what the RunSpec stores):
`1 = Gasoline`, `2 = Diesel Fuel`.

NONROAD `nrfueltype` (what `nrscc.fuelTypeID` uses):

| ID | Description | Density (`fuelDensity`) |
|---|---|---|
| 1 | Gasoline | 2829 |
| 3 | Compressed Natural Gas (CNG) | 500 |
| 4 | Liquefied Petroleum Gas (LPG) | 1923 |
| 23 | Nonroad Diesel Fuel | 3198 |
| 24 | Marine Diesel Fuel | 3198 |

`selected_sccs` (`nonroad_loader.rs:1119-1174`) intersects the RunSpec selection
`{1, 2}` against `nrscc.fuelTypeID`. `1` matches the gasoline logging SCCs; `2`
matches **nothing**, because nonroad diesel is 23/24. The intersection is
therefore non-empty (three gasoline SCCs) and the restriction applies — which is
exactly why this fixture's output is gasoline-only.

> The load-bearing quirk documented at `nonroad_loader.rs:1145-1163`: if the
> intersection were **empty** (a diesel-only RunSpec), canonical would emit an
> empty `/SOURCE CATEGORY/` packet, and the NONROAD Fortran treats an empty
> packet like a missing one — running the *entire* inventory. Verified against
> the canonical binary and four other snapshots. That branch does not fire here,
> but an `.esm` port that models the selection must not "simplify" it away.

Fuel subtypes seen in the supply join: `10 = Conventional Gasoline`,
`11 = Reformulated Gasoline` (the RFG test, `:1830`), `12 = Gasohol (E10)`,
`23 = Nonroad Diesel`, `24 = Marine Diesel`, `30 = CNG`, `40 = LPG`
(`:1834-1839`).

### 5.5 Engine technology codes

`engTechID` is an opaque key into `enginetech`; the relevant ones here:

| `engTechID` | `engTechName` | tier | strokes | description |
|---|---|---|---|---|
| 121 | `G2H5` | 0 | 2 | Baseline gas 2-stroke handheld Class V |
| 122 | `G2H5C` | 0 | 2 | …with Catalyst |
| 123 | `G2H51` | 1 | 2 | Phase 1 gas 2-stroke handheld Class V |
| 124 | `G2H5C1` | 1 | 2 | Phase 1 …with Catalyst |
| 125 | `G2H52` | 2 | 2 | Phase 2 gas 2-stroke handheld Class V |
| 126 | `G2H5C2` | 2 | 2 | Phase 2 …with Catalyst |
| 127–135 | — | — | 4 | 4-stroke non-handheld, 6–25 hp bin |
| 136–144 | — | — | 4 | 4-stroke non-handheld, 0–6 hp bin |

`processGroupID`: **1 = exhaust, 2 = evap** (`nonroad_loader.rs:352-354`,
`:1376-1378`). The `nrprocessgroup` table is empty in this snapshot, so the
meaning has to come from the code.

### 5.6 Other identifiers

| Name | Value | Meaning |
|---|---|---|
| `sectorID` Logging | 7 | `sector` table |
| `roadTypeID` Nonroad | 100 | `roadtype` table; `isAffectedByNonroad = 1` |
| `dayID` weekday | 5 | slot 0 of the daily profile |
| `dayID` weekend | 2 | slot 1 |
| `regionCodeID` nonroad fuel | 2 | `regioncounty` filter (`:1770`) |
| `NREquipTypeID` default scrappage | 0 | the only curve canonical writes (`:1560-1562`) |
| `modelYearID` sentinel | 1900 | "all model years" in `nremissionrate` / `nrengtechfraction` |
| `hpMax` sentinel | 9999 | open-ended top bin |
| Base population year | 1990 | `nrbaseyearequippopulation.NRBaseYearID` |
| Pseudo county | `"00001"` | internal region code for the engine's County dispatch (`nonroad_loader.rs:48`) |

### 5.7 Physical and dimensioning constants

All from `crates/moves-nonroad/src/common/consts.rs`.

| Constant | Value | Meaning | Line |
|---|---|---|---|
| `MXPOL` | 23 | pollutant slots | `:30` |
| `MXTECH` | 32 | max engine techs per (SCC, hp bin) | `:51` |
| `MXHPC` | 18 | HP categories | `:62` |
| `MXAGYR` | 51 | max equipment ages (⇒ median-life cap `int(51/2) = 25` yr) | `:67` |
| `MXDAYS` | 365 | Julian days | `:86` |
| `MINGRWIND` | 1e-4 | growth-indicator / population floor | `:158` |
| `GRMLB` | 453.6 | grams per pound (`f64`, cast to `f32` at use) | `:225` |
| `RMISS` | −9.0 | missing-value flag | `:339` |
| `CVTTON` | 1.102311e-06 | short tons per gram | `:355` |
| `CMFGAS` | 0.87 | gasoline carbon mass fraction | `:361` |
| `CMFCNG` | 0.717 | CNG carbon mass fraction | `:366` |
| `CMFLPG` | 0.817 | LPG carbon mass fraction | `:371` |
| `CMFDSL` | 0.87 | diesel carbon mass fraction | `:376` |
| `SWTGS2` | 0.0339 | base sulfur wt %, gasoline 2-stroke | `:381` |
| `SWTGS4` | 0.0339 | base sulfur wt %, gasoline 4-stroke | `:386` |
| `SWTDSL` | 0.33 | base sulfur wt %, diesel | `:401` |
| `SFCGS2` | 0.03 | sulfur→SOx/PM conversion fraction, gas 2-stroke | `:406` |
| `SFCGS4` | 0.03 | …gas 4-stroke | `:411` |
| `SFCDSL` | 0.02247 | …diesel | `:426` |
| `GRAMS_PER_SHORT_TON` | 1 / 1.102311e-6 | inverse of `CVTTON` | `nonroad_loader.rs:2177` |
| `initial_sales` | 1000.0 | `scrptime` sales base | `scrptime.rs:147` |
| sales-growth coefficients | −1.4306, −0.24 | `scrptime` | `scrptime.rs:139-143` |
| `HP_LEVELS` | 3, 6, 11, 16, 25, 40, 50, 75, 100, 175, 300, 600, 750, 1000, 1200, 1500, 1800, 2000 | representative HP levels | `nonroad_loader.rs:52-55` |
| `defmth` / `defday` | 1/12, 1/7 | temporal fallbacks | `nonroad_loader.rs:2273-2288` |
| days per month | 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 | non-leap | `nonroad_loader.rs:2202-2209` |
| temperature threshold | 75 °F | `emsadj.f` branch point | `exhaust.rs:539-547` |
| daytime hour window | `hourID ∈ [6, 18]` | ambient-temperature mean | `nonroad_loader.rs:1613-1615` |
| sulfur divisor | 10 000 | ppm → weight % | `nonroad_loader.rs:1826` |
| CO2 stoichiometry | 44 / 12 | CO2 per carbon | `exhaust.rs:1144-1145` |
| SOx factors | 0.01, 2.0 | `clcems` SOx EF rewrite | `exhaust.rs:1110-1113` |
| PM sulfur factors | 7.0, 0.01 | diesel PM sulfur correction | `exhaust.rs:1172-1176` |

---

## 6. Hand-checkable worked examples

All numbers below were **read from the snapshot Parquet** with
`python3` + `pyarrow` (21.0.0) / `pandas` (2.3.3), and the arithmetic was
re-executed independently in `numpy.float32` — not taken from a `moves.rs`
trace. The script in §6.5 reproduces **all 144 rows** end to end; the two
examples below are the worked longhand for a subset of them.

### 6.0 Run-level values used by every example

| Quantity | Value | Where it comes from |
|---|---|---|
| `tamb` (daytime mean, °F) | `73.576927` (f32) | `zonemonthhour` zone 261610, month 8, hourID 6–18; 13 rows, f64 mean `73.57692425067616`, cast to f32 |
| `oxy` (gasoline oxygen, wt %) | `3.653` | one supply row: formulation 9114 (Gasohol E10), `marketShare = 1.0`, `ETOHVolume = 10.0`, `volToWtPercentOxy = 0.3653` |
| `rfg` | `false` | RFG (subtype 11) share 0 of gasoline share 1.0 |
| growth pattern (all three SCCs) | `2176` | `nrgrowthpatternfinder` SCC `2265007000` / `2260007000`, `stateID = 26` |
| `G(1990)`, `G(1991)`, `G(2020)` | `321`, `449.8889`, `1508` | `nrgrowthindex` pattern 2176; 1991 interpolated between the 1990 (321) and 1999 (1481) rows |
| `pgf = grwfac(1990, 1991)` | `0.401523` | `(449.8889 − 321) / (321 × 1)` |
| `G(2020)/G(1990)` | `4.697819` | the cumulative growth the age distribution carries |
| `allocFrac` (surrogate 8) | `0.0032382987` (f32) | `nrstatesurrogate`: county 26161 quant `1512186`, state 26000 quant `466969286`, both `surrogateYearID = 2002` |
| `monthFraction` (all three SCCs) | `0.0833333` | `nrmonthallocation`, key `2260007000`/`2265007000`, state 26, month 8 |
| `dayFraction` (all three SCCs) | `0.166667` | `nrdayallocation`, key `2260007000`/`2265007000`, dayID 5 |
| `tpltmp = mthf × 7 × dayFraction` | `0.09722238` (f32) | |
| `adjtime = 1/ndays` | `1/31` | August |

Adjustment factors (`adjems`), from §4.2 + §4.3 with `tamb = 73.576927 ≤ 75`
and `oxy = 3.653`:

| fuel | THC | CO | NOx | PM |
|---|---|---|---|---|
| Gasoline 2-stroke (`2260…`) | `0.978082` | `0.7625550` | `1.6794580` | `1.0` |
| Gasoline 4-stroke (`2265…`) | `0.8384738` | `0.7717785` | `1.4382362` | `1.0` |

(4-stroke temperature parts alone: THC `1.0034212`, CO `0.9977564`,
NOx `1.0127747`.)

---

### 6.1 Worked example A — `2260007005` (2-stroke chain saws), all 12 rows

The cleanest example in the fixture: **one** equipment point, **one** active
engine tech, **three** model years.

#### Inputs read from the snapshot

`nrsourceusetype` row (`sourceTypeID = 1059`):

| column | value |
|---|---|
| `SCC` | `2260007005` |
| `hpAvg` | `6.81` |
| `hoursUsedPerYear` | `303.0` |
| `loadFactor` | `0.7` |
| `medianLifeFullLoad` | `191.0` |

`nrbaseyearequippopulation` (`sourceTypeID = 1059`, `stateID = 26`,
`NRBaseYearID = 1990`): `population = 83.279223744292`.

`nrengtechfraction` (SCC `2260007005`, bin `hpMin = 6`, `hpMax = 9999`,
`processGroupID = 1`): mix years `1900, 1996, 1997, 2002…2008`; the latest year
≤ 2020 is **2008**, with `engTechID 125 = 1.00` and every other tech `0.00`.
So a single tech, `125` (`G2H52`, Phase 2 gas 2-stroke handheld Class V).

`nremissionrate` (SCC `2260007005`, bin 6–9999, `modelYearID = 1900`,
`engTechID = 125`), units `g/hp-hr`:

| pollutant | `polProcessID` | `meanBaseRate` |
|---|---|---|
| THC | 101 | `47.98` |
| CO | 201 | `283.4` |
| NOx | 301 | `0.910` |
| PM10 | 10001 | `7.70` |
| *BSFC* | 9901 | `0.608` (units column empty; unused here) |

`nrdeterioration` (`engTechID = 125`):

| `polProcessID` | `DFCoefficient` A | `DFAgeExponent` B | `emissionCap` |
|---|---|---|---|
| 101 | `0.266` | `1.0` | `1` |
| 201 | `0.231` | `1.0` | `1` |
| 301 | `0.000` | `1.0` | `1` |
| 10001 | `0.266` | `1.0` | `1` |

#### Step 1 — population

```
pop_state  = round1dp(83.279223744292)  = 83.3
allocFrac  = 1512186 / 466969286        = 0.0032382987
pop_county = 83.3 × 0.0032382987        = 0.269750297      (f32)
```

#### Step 2 — scrappage (`scrptime`)

```
medianLifeYears = min(25, (191 / 0.7) / 303) = 0.90051866
1 / medianLifeYears                          = 1.1104711
```

Cumulative scrappage at each age (step lookup into the default curve):

| age | `fracLifeUsed` | `pctScrapped` | `yryrfrcscrp` |
|---|---|---|---|
| 1 | 0 | 0 | 0 |
| 2 | 1.1104711 | 73.5 | `100 × 0.735 / 100` = `0.735` |
| 3 | 2.2209423 | 100.0 | `100 × 0.265 / 26.5` = `0.99999994` |

`pctScrapped[age 3] = 100` ⇒ at `iage = 4` the loop sets **`nyrlif = 3`**.
Three model years: 2020, 2019, 2018 — exactly the set in the snapshot.

Sales / initial fractions:

```
salesGrowth = 0.401523 / ((−1.4306 × 0.401523) × 0.90051866 + (−0.24 × 0.401523) + 1)
modfrc(base) = [0.8506725, 0.1493275, 0.0]
```

#### Step 3 — grow the age distribution to 2020 (`agedist`)

30 iterations, 1991 → 2020. Result:

```
modfrc = [3.7072685, 0.9905483, 5.8885583e-08]     Σ = 4.697817 ≈ G(2020)/G(1990) = 4.697819 ✓
```

The third slot is `5.9e-08` rather than 0 — it is the residual of 30 rounds of
shift-and-scrap, and it is what produces the `4.27e-06 g` THC row for MY2018.

#### Step 4 — deterioration age

```
detage[i] = (i+1) × 303 × 0.7 / 191   ⇒  [1.1104711, 2.2209423, 3.3314135]
```

All three exceed `emissionCap = 1`, so `min(age, cap) = 1.0` for every model
year, and with `B = 1`:

```
DF(THC) = DF(PM) = 1 + 0.266 = 1.266
DF(CO)            = 1 + 0.231 = 1.231
DF(NOx)           = 1 + 0.000 = 1.000
```

#### Step 5 — the roll-up

`cvttmp = hpAvg × loadFactor = 6.81 × 0.7 = 4.7669997`

```
emstmp = EF × 4.7669997 × DF × adjems × (1/31)
emiss  = emstmp × 303 × 0.09722238 × 0.269750297 × modfrc[idxyr] × 1.0
grams  = emiss × CVTTON × (1/CVTTON)
```

| pollutant | `emstmp` |
|---|---|
| THC | `9.135927` |
| CO | `40.90840` |
| NOx | `0.2350141` |
| PM | `1.499022` |

#### Results — all 12 rows

| pollutantID | modelYearID | computed (g) | snapshot (g) | rel. error |
|---|---|---|---|---|
| 1 (THC) | 2020 | `269.1395` | `269.139` | `+1.9e-06` |
| 1 | 2019 | `71.91162` | `71.9116` | `+3.5e-07` |
| 1 | 2018 | `4.274964e-06` | `4.27496e-06` | `+8.6e-07` |
| 2 (CO) | 2020 | `1205.139` | `1205.140` | `−5.1e-07` |
| 2 | 2019 | `322.0022` | `322.0020` | `+7.7e-07` |
| 2 | 2018 | `1.914222e-05` | `1.91422e-05` | `+9.1e-07` |
| 3 (NOx) | 2020 | `6.923390` | `6.923380` | `+1.5e-06` |
| 3 | 2019 | `1.849867` | `1.849860` | `+3.7e-06` |
| 3 | 2018 | `1.099699e-07` | `1.09970e-07` | `−1.1e-06` |
| 100 (PM10) | 2020 | `44.16037` | `44.16030` | `+1.7e-06` |
| 100 | 2019 | `11.79925` | `11.79920` | `+4.1e-06` |
| 100 | 2018 | `7.014354e-07` | `7.01435e-07` | `+5.9e-07` |

Every residual is at the level of the snapshot's 6-significant-figure storage.

---

### 6.2 Worked example B — `2265007015` (4-stroke feller/buncher), all 16 rows

Chosen because it exercises what example A does not: the **temperature
exponential**, a **multi-tech mix**, a **non-unit deterioration exponent**
(`B = 0.5`, `cap = 2`), **two equipment points summed into one output row**, and
the `modfrc ≤ 0` skip.

#### Inputs

Two `nrsourceusetype` rows, both `SCC = 2265007015`:

| `sourceTypeID` | `hpAvg` | `hoursUsedPerYear` | `loadFactor` | `medianLifeFullLoad` | state-26 population |
|---|---|---|---|---|---|
| 1389 | `5.5` | `350.0` | `0.7` | `200.0` | `1.121332091290` → **1.1** |
| 1390 | `9.0` | `350.0` | `0.7` | `400.0` | `0.463483931067` → **0.5** |

Note the second population rounds *up* from 0.4635 to 0.5 — a 7.9 % change,
entirely an artefact of the `%17.1f` `.POP` format, and it is required to match.

Both points fall back to `2265000000` for rates and mixes (`2265007015` and
`2265007000` have no rows), but into **different HP bins**:

| point | mix/EF bin | mix year used (≤ 2020) | active techs |
|---|---|---|---|
| hp 5.5 | `0 ≤ hp ≤ 6` | 2014 | `143` = 0.40, `144` = 0.60 |
| hp 9.0 | `6 ≤ hp ≤ 25` | 2015 | `134` = 1.00 |

Emission factors (`modelYearID = 1900`, `g/hp-hr`) and deterioration
(`B = 0.5`, `cap = 2` for all of these):

| tech | THC EF | CO EF | NOx EF | PM EF | A(THC) | A(CO) | A(NOx) | A(PM) |
|---|---|---|---|---|---|---|---|---|
| 143 | `3.80` | `242.4` | `1.424` | `0.037` | `0.797` | `0.070` | `0.302` | `1.753` |
| 144 | `4.18` | `238.4` | `1.044` | `0.179` | `0.797` | `0.070` | `0.302` | `1.753` |
| 134 | `3.17` | `321.9` | `1.007` | `0.060` | `0.797` | `0.080` | `0.302` | `1.095` |

#### Derived per point

| | hp 5.5 point | hp 9.0 point |
|---|---|---|
| `pop_county` | `1.1 × allocFrac = 0.0035621286` | `0.5 × allocFrac = 0.0016191494` |
| `medianLifeYears = (mdl/ldf)/hrs` | `(200/0.7)/350 = 0.8163266` | `(400/0.7)/350 = 1.632653` |
| `1/medianLifeYears` | `1.225` | `0.6125` |
| `nyrlif` | `3` | `5` |
| `cvttmp = hp × ldf` | `3.85` | `6.30` |
| `detage[0..]` | `1.225, 2.45, 3.675` | `0.6125, 1.225, 1.8375, 2.45, 3.0625` |
| `modfrc` (grown) | `3.9099162, 0.7879026, 0.0` | `2.1914759, 2.0018263, 0.4327385, 0.0717785, 0.0` |

The hp-9.0 point's `nyrlif = 5` would reach back to MY2016, but its
`modfrc[4] = 0.0` (age 5 has `yryrfrcscrp = 1.0`, so the shift zeroes it), and
the `modfrc ≤ 0` skip drops it. Both points' oldest slot is likewise zero. The
union of surviving model years is **2017–2020**, matching the snapshot.

Because `B = 0.5` and `cap = 2`, the deterioration factor genuinely varies with
age here — e.g. for tech 134, THC:

```
MY2020: 1 + 0.797 × 0.6125^0.5 = 1.623713
MY2019: 1 + 0.797 × 1.2250^0.5 = 1.882109
MY2018: 1 + 0.797 × 1.8375^0.5 = 2.080366
MY2017: 1 + 0.797 × min(2.45, 2)^0.5 = 1 + 0.797 × 2^0.5 = 2.127187
```

Note MY2017 uses the **capped age 2.0 inside the square root**, not a capped
multiplier — the distinction §4.1 flags.

#### Results — all 16 rows (sum of both equipment points)

| pollutantID | modelYearID | computed (g) | snapshot (g) | rel. error |
|---|---|---|---|---|
| 1 (THC) | 2017 | `0.004543986` | `0.00454398` | `+1.3e-06` |
| 1 | 2018 | `0.02679258` | `0.0267926` | `−5.9e-07` |
| 1 | 2019 | `0.1973395` | `0.197339` | `+2.7e-06` |
| 1 | 2020 | `0.4800438` | `0.480043` | `+1.6e-06` |
| 2 (CO) | 2017 | `0.2222577` | `0.222258` | `−1.2e-06` |
| 2 | 2018 | `1.334298` | `1.334300` | `−1.7e-06` |
| 2 | 2019 | `8.476013` | `8.476010` | `+4.1e-07` |
| 2 | 2020 | `18.22461` | `18.22460` | `+5.8e-07` |
| 3 (NOx) | 2017 | `0.001661140` | `0.00166114` | `+2.1e-07` |
| 3 | 2018 | `0.009890348` | `0.00989034` | `+7.8e-07` |
| 3 | 2019 | `0.07242940` | `0.0724293` | `+1.4e-06` |
| 3 | 2020 | `0.1790237` | `0.179024` | `−1.7e-06` |
| 100 (PM10) | 2017 | `0.0001228970` | `0.000122897` | `+1.2e-07` |
| 100 | 2018 | `0.0007222449` | `0.000722244` | `+1.3e-06` |
| 100 | 2019 | `0.008017370` | `0.00801736` | `+1.3e-06` |
| 100 | 2020 | `0.02388155` | `0.0238815` | `+2.3e-06` |

---

### 6.3 Worked example C — `2265007010`, the 116 remaining rows

Not tabulated longhand (116 rows), but reproduced by the same script. It is the
one that exercises the parts A and B do not:

- **Three** equipment points (`sourceTypeID` 1386/1387/1388, `hpAvg`
  8.117 / 12.62 / 20.56), all in the `6 ≤ hp ≤ 25` bin of `2265000000`, with
  `medianLifeFullLoad` 400 / 400 / **750** and `hoursUsedPerYear = 50`,
  `loadFactor = 0.8`. The third point's `medianLifeYears = 750/0.8/50 = 18.75`
  gives `nyrlif = 38`, which is what stretches the model-year span back to 1983.
- **The gappy model-year set.** MY 1991, 2000, 2001, 2002 and 2006–2010 are
  absent from the snapshot. They are the years where `agedist`'s unclamped
  residual `mdyrfrc[0] = totpopfrc − frcsum` came out ≤ 0, because the truncated
  growth index dipped year-over-year. This is the single most fragile behaviour
  in the whole chain: it depends jointly on (i) the integer truncation of
  `growthIndex`, (ii) the residual **not** being clamped, and (iii) the
  downstream `modfrc ≤ 0` skip. Get any one wrong and the row count changes.
- **Per-model-year tech mixes** that actually move (mix years 1900, 1996, 1997,
  2001–2005, 2011, 2013, 2015 in that bin), so the "latest mix year ≤ model
  year" rule is exercised across many distinct mixes.

All 116 rows agree with the snapshot to ≤ 4.9 × 10⁻⁶ relative.

### 6.4 Aggregate check

| pollutantID | snapshot total (g) | `moves.rs` total (g) |
|---|---|---|
| 1 (THC) | `397.250859` | `397.251361` |
| 2 (CO) | `4658.921054` | `4658.924298` |
| 3 (NOx) | `33.042431` | `33.042465` |
| 100 (PM10) | `57.295225` | `57.295338` |

(`moves.rs` totals from `./target/release/moves run --runspec
characterization/fixtures/nr-logging-county.xml --snapshot
characterization/snapshots/nr-logging-county --output <dir>`, 487 ms wall.)

### 6.5 The reproduction script

Self-contained; run from the `moves.rs` repo root. Requires only `numpy` and
`pyarrow`/`pandas`. Asserts 144 rows and max relative error < 1e-5.

```python
#!/usr/bin/env python3
"""Independent reproduction of every nr-logging-county MOVESOutput row.

Reimplements the moves.rs NONROAD chain in float32 straight from the snapshot
Parquet tables. Run from the moves.rs repo root (or pass the snapshot dir).
"""
import sys
import numpy as np
import pyarrow.parquet as pq

f = np.float32
MXAGYR = 51
SNAP = sys.argv[1] if len(sys.argv) > 1 else "characterization/snapshots/nr-logging-county"
D = SNAP + "/tables/"
PRE = "db__movesexecution1ccc0232_campuscluster_illinois_edu__"
rd = lambda t: pq.read_table(D + PRE + t + ".parquet").to_pandas()

# ---------------------------------------------------------------- run scope
COUNTY, STATE, YEAR, MONTH, DAYID, NDAYS = 26161, 26, 2020, 8, 5, 31
PP = {"THC": 101, "CO": 201, "NOx": 301, "PM": 10001}
POLID = {"THC": 1, "CO": 2, "NOx": 3, "PM": 100}

# ------------------------------------------------- growth (getgrw / grwfac)
gi = rd("nrgrowthindex")
gp = rd("nrgrowthpatternfinder")

def growth_series(pattern):
    g = gi[gi.growthPatternID == pattern].sort_values("yearID")
    # /GROWTH/ packet is written %20d -> truncate toward zero
    return [int(r.yearID) for r in g.itertuples()], [f(int(r.growthIndex)) for r in g.itertuples()]

def indicator(ys, vs, y):
    ib, ie = 0, len(ys) - 1
    if y < ys[ib]:
        s = (vs[ib + 1] - vs[ib]) / f(ys[ib + 1] - ys[ib])
        return max(f(vs[ib] + s * f(y - ys[ib])), f(0))
    if y > ys[ie]:
        s = (vs[ie] - vs[ie - 1]) / f(ys[ie] - ys[ie - 1])
        return max(f(vs[ie] + s * f(y - ys[ie])), f(0))
    if y == ys[ie]:
        return vs[ie]
    for i in range(ib, ie):
        if y == ys[i]:
            return vs[i]
        if y < ys[i + 1]:
            s = (vs[i + 1] - vs[i]) / f(ys[i + 1] - ys[i])
            return f(vs[i] + s * f(y - ys[i]))
    return vs[ie]

def growth_factor(ys, vs, y1, y2):
    if y1 == y2:
        return f(0)
    b, g = indicator(ys, vs, y1), indicator(ys, vs, y2)
    if b == 0 and g == 0:
        return f(0)
    return f((g - b) / (b * f(y2 - y1)))

# ------------------------------------------------------------ scrappage curve
sc = rd("nrscrappagecurve")
sc = sc[sc.NREquipTypeID == 0]
CURVE = [(f(k / 1e6), f(v)) for k, v in sorted(
    {round(float(r.fractionLifeused) * 1e6): float(r.percentageScrapped) for r in sc.itertuples()}.items())]

def find_scrappage_percent(x):            # output/find.rs:233 - step function
    if x < CURVE[0][0]:
        return CURVE[0][1]
    for i in range(len(CURVE) - 1):
        if CURVE[i + 1][0] > x:
            return CURVE[i][1]
    return CURVE[-1][1]

def scrptime(mdlfhrs, ldfctr, acthpy, pgf):        # driver/scrptime.rs:84
    mly = min(f(MXAGYR // 2), f(f(mdlfhrs / ldfctr) / acthpy))
    mlpy = f(1.0) / mly
    yy = [f(0)] * MXAGYR
    pct = [f(0)] * MXAGYR
    nyrlif = 0
    for iage in range(2, MXAGYR + 1):
        cur, prev = iage - 1, iage - 2
        pct[cur] = find_scrappage_percent(f(f(iage - 1) * mlpy))
        yfs = f((pct[cur] - pct[prev]) / f(100))
        if pct[prev] >= 100:
            if nyrlif == 0:
                nyrlif = iage - 1
            yy[cur] = f(0)
        else:
            yy[cur] = f(f(100) * yfs / (f(100) - pct[prev]))
    if pct[MXAGYR - 1] >= 100 and nyrlif == 0:
        nyrlif = MXAGYR
    sg = f(pgf / (f(f(-1.4306) * pgf) * mly + f(-0.24) * pgf + f(1.0)))
    sales = [f(f(1000.0) + f(f(1000.0) * sg * f(i))) for i in range(MXAGYR)]
    surv = [f(0)] * MXAGYR
    tot = f(0)
    for iage in range(1, MXAGYR + 1):
        i0 = iage - 1
        if iage <= nyrlif:
            surv[i0] = f(sales[nyrlif - iage] * (f(1.0) - f(pct[i0] / f(100))))
        tot = f(tot + surv[i0])
    return yy, [f(s / tot) for s in surv], nyrlif

def agedist(baspop, modfrc, base_year, growth_year, yy, ys, vs):   # population/agedist.rs:128
    md = list(modfrc)
    totpop = f(baspop)
    for iyear in range(base_year + 1, growth_year + 1):
        tmp = list(md)
        gf = growth_factor(ys, vs, iyear - 1, iyear)
        if gf != 0:
            totpop = max(totpop, f(0.0001))               # MINGRWIND
        totpop = max(f(totpop * (f(1.0) + gf)), f(0))
        tpf = f(totpop / f(baspop))
        s = f(0)
        for ia in range(1, MXAGYR):
            u = max(f(tmp[ia - 1] * (f(1.0) - yy[ia])), f(0))
            md[ia] = u
            s = f(s + u)
        md[0] = f(tpf - s)                                # residual, unclamped
    return md

# ------------------------------------------------------------------ geography
ss = rd("nrstatesurrogate")
def alloc_frac(sur):                                      # alocty.f / getind.f
    def pick(fips):
        rows = ss[(ss.surrogateID == sur) & (ss.countyID == fips)]
        low = rows[rows.surrogateYearID <= YEAR]
        if len(low):
            return f(float(low.sort_values("surrogateYearID").iloc[-1].surrogatequant))
        hi = rows[rows.surrogateYearID > YEAR]
        if len(hi):
            return f(float(hi.sort_values("surrogateYearID").iloc[0].surrogatequant))
        return None
    qs, qc = pick(STATE * 1000), pick(COUNTY)
    return f(qc / qs) if (qs is not None and qs > 0 and qc is not None) else f(0)

# ------------------------------------------------------------------- temporal
ma, da = rd("nrmonthallocation"), rd("nrdayallocation")
def scc_ladder(s):                                        # nonroad_loader.rs:839
    return [s] + [s[:10 - k] + "0" * k for k in (2, 4, 6)]
def equip_chain(s):                                       # nonroad_loader.rs:816
    return [s, s[:7] + "000", s[:4] + "000000"]
def month_fraction(scc):
    for k in scc_ladder(scc):
        for st in (STATE, 0):                             # state rows win
            r = ma[(ma.SCC == k) & (ma.stateID == st) & (ma.monthID == MONTH)]
            if len(r):
                return f(float(r.iloc[0].monthFraction))
    return f(1.0 / 12.0)                                  # defmth
def day_fraction(scc):
    for k in scc_ladder(scc):
        r = da[(da.scc == k) & (da.dayID == DAYID)]
        if len(r):
            return f(float(r.iloc[0].dayFraction))
    return f(1.0 / 7.0)                                   # defday

# ---------------------------------------------------------------- temperature
z = rd("zone"); zmh = rd("zonemonthhour")
zids = set(z[z.countyID == COUNTY].zoneID)
t = zmh[(zmh.zoneID.isin(zids)) & (zmh.monthID == MONTH)
        & (zmh.hourID >= 6) & (zmh.hourID <= 18)].temperature.astype(float)
TAMB = f(t.mean())

# ------------------------------------------------------------------ fuel props
yr = rd("year"); fuel_year = int(yr[yr.yearID == YEAR].fuelYearID.iloc[0])
rc = rd("regioncounty")
regions = set(rc[(rc.regionCodeID == 2) & (rc.countyID == COUNTY)
                 & (rc.fuelYearID == fuel_year)].regionID)
sup, form, fst = rd("nrfuelsupply"), rd("fuelformulation"), rd("nrfuelsubtype")
sup["marketShare"] = sup.marketShare.astype(float)
for c in ("ETOHVolume", "MTBEVolume", "ETBEVolume", "TAMEVolume", "volToWtPercentOxy"):
    form[c] = form[c].astype(float)
m = sup[sup.fuelRegionID.isin(regions) & (sup.monthGroupID == MONTH)
        & (sup.fuelYearID == fuel_year)].merge(form, on="fuelFormulationID") \
                                        .merge(fst[["fuelSubtypeID", "fuelTypeID"]], on="fuelSubtypeID")
gas = m[m.fuelTypeID == 1]
OXY = f((gas.marketShare * ((gas.ETOHVolume + gas.MTBEVolume + gas.ETBEVolume
                            + gas.TAMEVolume) * gas.volToWtPercentOxy)).sum())

def adjustments(scc):                                     # emsadj.f
    two = scc[:4] == "2260"
    dt = f(TAMB - f(75.0))
    if two:
        a = (f(0.0), f(0.0), f(0.0))
        c = (f(0.006), f(0.065), f(-0.186))
    else:
        a = (f(-0.00240), f(0.0015784), f(-0.00892)) if TAMB <= 75 else (f(0.00132), f(0.00375), f(-0.00873))
        c = (f(0.045), f(0.062), f(-0.115))
    out = {}
    for i, p in enumerate(("THC", "CO", "NOx")):
        out[p] = f(f(np.exp(f(a[i] * dt))) * f(f(1.0) - c[i] * OXY))
    out["PM"] = f(1.0)
    return out

# ------------------------------------------------- emission factors / tech mix
er, tf, det = rd("nremissionrate"), rd("nrengtechfraction"), rd("nrdeterioration")
DET = {(k, int(r.engTechID)): (f(float(r.DFCoefficient)), f(float(r.DFAgeExponent)),
                               f(float(r.emissionCap)))
       for k, pp in PP.items() for r in det[det.polProcessID == pp].itertuples()}

def tech_mix(scc, hp):                                    # .TECH, processGroupID 1
    for s in equip_chain(scc):
        sub = tf[(tf.SCC == s) & (tf.processGroupID == 1)
                 & (tf.hpMin <= hp) & (tf.hpMax >= hp)]
        if len(sub):
            out = {}
            for r in sub.itertuples():
                out.setdefault(int(r.modelYearID), {})[int(r.engTechID)] = f(float(r.NREngTechFraction))
            return out
    return {}

def ef_map(scc, hp):                                      # .EMF, independent chain
    for s in equip_chain(scc):
        e = er[(er.SCC == s) & (er.hpMin <= hp) & (er.hpMax >= hp)]
        if len(e):
            return {(k, int(r.engTechID)): f(float(r.meanBaseRate))
                    for k, pp in PP.items() for r in e[e.polProcessID == pp].itertuples()}
    return {}

# --------------------------------------------------------------- the run itself
sut, pop, scct, eqt = rd("nrsourceusetype"), rd("nrbaseyearequippopulation"), rd("nrscc"), rd("nrequipmenttype")
sectors = set(rd("runspecsector").sectorID)
fuels = set(rd("runspecfueltype").fuelTypeID)
eq_sector = dict(zip(eqt.NREquipTypeID, eqt.sectorID))
eq_surr = dict(zip(eqt.NREquipTypeID, eqt.surrogateID))
allowed = {r.SCC for r in scct.itertuples()
           if eq_sector.get(r.NREquipTypeID) in sectors and r.fuelTypeID in fuels}
scc_surr = {r.SCC: eq_surr[r.NREquipTypeID] for r in scct.itertuples() if r.NREquipTypeID in eq_surr}

pop_by_src = {}
for r in pop[pop.stateID == STATE].itertuples():          # .POP is written %17.1f
    pop_by_src[r.sourceTypeID] = pop_by_src.get(r.sourceTypeID, 0.0) + round(float(r.population) * 10) / 10

totals = {}
for r in sut.itertuples():
    if r.SCC not in allowed:
        continue
    sp = pop_by_src.get(r.sourceTypeID)
    if not sp:
        continue
    scc = r.SCC
    hp = f(float(r.hpAvg)); hrs = f(float(r.hoursUsedPerYear))
    ldf = f(float(r.loadFactor)); mdl = f(float(r.medianLifeFullLoad))
    ys, vs = growth_series(int(gp[(gp.SCC.isin(equip_chain(scc)))
                                  & (gp.stateID.isin([STATE, 0]))].iloc[0].growthPatternID))
    yy, mf0, ny = scrptime(mdl, ldf, hrs, growth_factor(ys, vs, 1990, 1991))
    md = agedist(f(sp), mf0, 1990, YEAR, yy, ys, vs)
    cp = f(f(sp) * alloc_frac(scc_surr[scc]))
    tpl = f(month_fraction(scc) * f(f(7.0) * day_fraction(scc)))
    adjtime = f(f(1.0) / f(NDAYS))
    cvt = f(hp * ldf)
    adj = adjustments(scc)
    MIX, EF = tech_mix(scc, hp), ef_map(scc, hp)
    for idx in range(ny):
        if md[idx] <= 0:                                  # prccty.f skips modfrc <= 0
            continue
        my = YEAR - idx
        detage = f(f(idx + 1) * hrs * ldf / mdl)
        years_le = [y for y in sorted(MIX) if y <= min(my, YEAR)]
        mix = MIX[years_le[-1]] if years_le else MIX[sorted(MIX)[0]]
        for p in PP:
            for tid, frac in mix.items():
                if frac <= 0:
                    continue
                A, B, cap = DET.get((p, tid), (f(0), f(1), f(0)))
                DF = f(f(1.0) + A * f((detage if detage <= cap else cap) ** B))
                emstmp = f(f(f(f(EF.get((p, tid), f(0)) * cvt) * DF) * adj[p]) * adjtime)
                emiss = f(f(f(f(f(emstmp * hrs) * tpl) * cp) * md[idx]) * frac)
                k = (POLID[p], scc, my)
                totals[k] = f(totals.get(k, f(0)) + f(emiss * f(1.102311e-06)))

# ------------------------------------------------------------------- compare
exp = pq.read_table(D + "db__out_nr_logging_county__movesoutput.parquet").to_pandas()
exp["emissionQuant"] = exp.emissionQuant.astype(float)
obs = {(int(r.pollutantID), r.SCC, int(r.modelYearID)): float(r.emissionQuant) for r in exp.itertuples()}
worst, n = 0.0, 0
for k in sorted(set(list(totals) + list(obs))):
    got = float(totals.get(k, 0.0)) / 1.102311e-6
    want = obs.get(k)
    if want is None:
        print("EXTRA", k, got); continue
    rel = (got - want) / want
    worst = max(worst, abs(rel)); n += 1
print(f"{n} rows compared, max |relative error| = {worst:.3e}")
assert n == 144 and worst < 1e-5
```

Output:

```
144 rows compared, max |relative error| = 4.897e-06
```

### 6.6 Suggested inline `.esm` tests

The two hand-worked examples give three tiers of inline test, all with
`const`-array inputs and no data dependency:

1. **Template level.** `deterioration_factor(0.797, 0.5, 2.0, 2.45) = 2.127187`
   (the cap-inside-the-power case);
   `exhaust_temperature_adjustment(-0.00892, -0.00873, 73.576927) = 1.0127747`;
   `oxygenate_adjustment(-0.115, 3.653) = 1.420095`;
   `unit_conversion(g/hp-hr, 6.81, 0.7) = 4.7669997`.
2. **Component level.** `scrptime(191, 0.7, 303, 0.401523)` ⇒ `nyrlif = 3`,
   `modfrc = [0.8506725, 0.1493275, 0]`; `agedist` of that over 1990→2020 with
   pattern 2176 ⇒ `[3.7072685, 0.9905483, 5.8886e-08]`.
3. **Chain level.** The 12 rows of §6.1 as literal expected values — one SCC,
   one tech, no summation, so a mismatch localises immediately.

---

## 7. Fidelity notes and tolerance

### 7.1 What `moves.rs` does

`crates/moves-nonroad/src/emissions/exhaust.rs:14-38` states the policy:

> All calculations use `f32` (single precision). The Fortran source declares
> every variable `real*4`; matching the storage type is required to produce the
> same rounding behaviour … Where the Fortran code multiplies several `real*4`
> quantities in a specific order (e.g. `a * b * c * d` versus `(a * b) * (c * d)`),
> the Rust port reproduces the original associativity.

This is accurate: the `f32` reimplementation in §6.5 lands within
**4.9 × 10⁻⁶** relative of the canonical snapshot on every one of the 144 rows,
and the `moves.rs` binary itself lands within **4.8 × 10⁻⁶**.

> **Stale documentation.** `docs/known-divergences.md` §4.2 says "NONROAD
> arithmetic uses Fortran single-precision (`real*4`) in the original; the Rust
> port uses `f64` throughout." That is **wrong** for the NONROAD engine — the
> code is `f32` throughout, as `exhaust.rs`'s header and PLAN.md §1.6 both say,
> and as the §6.5 reproduction demonstrates. The `NONROAD_REL_TOL = 1e-2`
> constant in `crates/moves-cli/tests/full_suite_regression.rs:450` carries the
> same incorrect justification in its doc comment.

### 7.2 What EarthSciAST will do, measured

ESM evaluates in `binary64`, and `domain.element_type: "Float32"` is
document-wide — it cannot reproduce *per-expression* single-precision rounding
(PLAN.md §1.6). To measure the consequence rather than guess it, I re-ran the
§6.5 script with `f = np.float64` and nothing else changed:

| | rows produced | max rel. error vs snapshot |
|---|---|---|
| `float32` (matches `moves.rs`) | **144 / 144** | 4.897 × 10⁻⁶ |
| `float64` | **140 / 144** | 6.879 × 10⁻⁶ on the 140 |

So binary64 reproduces the *arithmetic* essentially as well as binary32 —
6.9e-6 vs 4.9e-6, both at the level of the snapshot's own 6-significant-figure
storage. **The precision problem is not accuracy; it is four rows that exist
only because of an f32 rounding artefact.**

### 7.3 The one operation where precision changes the answer

`crates/moves-nonroad/src/driver/scrptime.rs:122-131`:

```rust
let year_frac_scrapped = (pct_scrapped[cur] - pct_scrapped[prev]) / 100.0;
...
yryrfrcscrp[cur] = 100.0 * year_frac_scrapped / (100.0 - pct_scrapped[prev]);
```

For `2260007005`'s age-3 transition, `pct_prev = 73.5`, `pct_cur = 100.0`:

| | `year_frac_scrapped` | `yryrfrcscrp` | `1 − yryrfrcscrp` |
|---|---|---|---|
| binary32 | `0.265` | `0.99999994` | **`5.9604645e-08`** |
| binary64 | `0.265` | `1.0` | **`0.0`** |

Algebraically the expression is `(100 − pct_cur)/(100 − pct_prev)`, which is
exactly 0 when `pct_cur = 100`. The `f32` evaluation lands one ulp short of 1,
`agedist` carries that `5.96e-08` through 30 shift-and-scrap iterations
(`population/agedist.rs:139-143`) into `modfrc[2] = 5.8886e-08`, and the
`modfrc <= 0` skip at `crates/moves-nonroad/src/geography/process.rs:380-383`
therefore does *not* fire for model year 2018.

Consequence: the four rows `(pollutantID ∈ {1,2,3,100}, SCC 2260007005,
modelYearID 2018)` — emission quantities `4.27e-06`, `1.91e-05`, `1.10e-07`,
`7.01e-07` g, **total 2.42 × 10⁻⁵ g out of the fixture's 5 146.51 g
(4.7 × 10⁻⁹ of the mass)**. They are numerical noise in the canonical Fortran,
faithfully reproduced by `moves.rs`, and unreachable from binary64.

Two non-fixes, both checked:

- **Relaxing the skip to `modfrc < 0`** recovers those four keys but adds **44
  spurious zero-valued keys** (every other model year whose `modfrc` is exactly
  0), giving 188 rows. Worse. Keep the `<= 0` skip exactly as written.
- **Rewriting the expression** as `(100 − pct_cur)/(100 − pct_prev)` — the
  algebraically equal form — gives exactly 0 in *both* precisions and so does
  not help either.

The only faithful reproduction would round `yryrfrcscrp` to single precision at
that one operation, which ESM cannot express per-expression. If exact row parity
is wanted, the honest route is to **precompute `yryrfrcscrp` in f32 outside the
document** (it depends only on the scrappage curve and `medianLifeYears`, both
inputs) and feed it in as data — a `data_sources` entry or a build-time
`skolem`, not an in-document expression.

Otherwise: **record 140/144 as a known structural difference with this cause**,
and assert the total mass separately.

### 7.4 Other precision-sensitive operations, ranked

| Rank | Operation | Why it is sensitive | Observed margin in this fixture |
|---|---|---|---|
| 1 | `yryrfrcscrp` (§7.3) | cancellation against exactly 1.0, then a sign/zero test 30 iterations later | **fails** — 4 rows |
| 2 | `agedist` residual `mdyrfrc[0] = totpopfrc − frcsum` (`agedist.rs:144`) | catastrophic cancellation whose **sign** decides whether a model year exists at all | safe: smallest surviving positive residual `0.168`, largest non-positive `−0.089` — margins of order 10⁻¹, ~10⁶× the f32/f64 gap |
| 3 | `find_scrappage_percent` step lookup (`output/find.rs:233-244`) | a discrete bin choice; crossing a breakpoint jumps `pctScrapped` by 0.5 pp and can change `nyrlif` | one **exact tie**: `medianLifeYears = 10` (the `2265007010` 400-hr points) puts `fracLifeUsed = 1.000000` exactly on a curve breakpoint at age 11. Verified to select the same bin in both precisions (next edge is `1.000050`). Every other evaluation clears its nearest edge by ≥ 1.16 × 10⁻⁴ relative. |
| 4 | Population rounding `(pop*10).round()/10` (`nonroad_loader.rs:1226`) | an explicit quantization, **not** a precision artefact | must be modelled explicitly; `0.463484 → 0.5` is a 7.9 % change that is required to match |
| 5 | `growthIndex` integer truncation (`nonroad_loader.rs:1516`) | explicit `as i64`; decides the **sign** of near-zero growth factors | must be modelled explicitly (`trunc`, not `round`) |
| 6 | `apply_deterioration` `powf(B)` with `B = 0.5` (`exhaust.rs:835`) | `sqrt` differs ~1 ulp between precisions | benign, ~1e-7 relative |
| 7 | `exp(a·(T−75))` (`exhaust.rs:551-566`) | libm difference | benign, ~1e-7 relative |
| 8 | The 10-factor roll-up product (`exhaust.rs:1079-1208`) | associativity preserved from Fortran; binary64 reassociation changes the last bits | benign, ≲ 5e-6 relative accumulated |
| 9 | Short-ton round trip `× CVTTON` then `÷ 1.102311e-6` (`exhaust.rs:1227`, `nonroad_loader.rs:2177`, `:2378`) | the f32 tons value is the stored intermediate | benign, ~6e-8 relative |

Items 4 and 5 are the ones most likely to be "simplified away" by an `.esm`
author who reads them as noise. They are not noise; they are the file formats
canonical MOVES writes.

### 7.5 Recommended tolerance

**What `characterization/tolerance.toml` uses for this fixture: nothing.** The
file sets `default_float_tolerance = 0.0` (line 21) and contains **no
per-table or per-column overrides at all** — the example block is commented out
(lines 26-32). Its own trailing NOTE says the full-suite regression gate does
not use the file, because a cell-level `moves_snapshot diff` of `MOVESOutput` is
unusable for canonical-vs-port comparison (the two sides disagree on labelling
columns that carry no mass).

The tolerance actually applied to this fixture is in
`crates/moves-cli/tests/full_suite_regression.rs`:

- `NONROAD_REL_TOL: f64 = 1e-2` (`:450`)
- `("nr-logging-county", NONROAD_REL_TOL, false),   // ~2.0e-6, 144/144` (`:498`)

— a **per-pollutant total** relative tolerance, and the in-line comment records
that the fixture actually lands at ~2 × 10⁻⁶.

For the `.esm` port I recommend **tighter and structured**, not `1e-2`:

```toml
# tolerance.toml (moves.esm)
[fixtures."nr-logging-county"]
# Per-cell relative tolerance on MOVESOutput.emissionQuant.
# Observed: f32 reimplementation 4.9e-6, binary64 6.9e-6, moves.rs 4.8e-6,
# all against a snapshot stored to 6 significant figures. 2e-5 gives ~3x
# headroom over the worst observed and still catches a 0.01% modelling error.
emissionQuant_rel = 2e-5

# Per-pollutant total, where cancellation cannot hide behind a large cell.
total_rel = 1e-5

# Key-set assertion. binary64 cannot produce the four f32-artefact rows;
# see docs/nonroad-logging-county.md section 7.3.
expected_rows = 144
allowed_missing = [
  "pollutantID=1,SCC=2260007005,modelYearID=2018",
  "pollutantID=2,SCC=2260007005,modelYearID=2018",
  "pollutantID=3,SCC=2260007005,modelYearID=2018",
  "pollutantID=100,SCC=2260007005,modelYearID=2018",
]
allowed_missing_mass_g = 2.5e-5     # total mass those four rows carry
allowed_extra = []                  # no spurious keys permitted
```

`1e-2` is three orders of magnitude looser than the physics warrants here and
would hide, for example, a wrong oxygenate coefficient (the THC/CO/NOx
coefficients differ by 4–30× between 2- and 4-stroke; a swap would show as a
2–20 % error) or a missing deterioration cap. The row-count assertion is the
part that actually needs a documented exception, and it should be an explicit
allow-list of four named keys rather than a slack number.

---

## 8. Gaps, uncertainties and things I could not verify

Listed honestly, in rough order of how much they could cost the `.esm` port.

### 8.1 Paths this fixture does not exercise — described from code only

My reading of these is a code reading, **not** validated by the fixture:

- **CO2 (pollutantID 90) and SO2 (31).** Not in the RunSpec selection, so the
  BSFC-derived branches (`exhaust.rs:1092-1147`) never ran. In particular the
  order dependence on `ems_thc` (saved at `:1086-1088`, consumed at `:1108` and
  `:1141`) means the pollutant loop must run THC first; I could not confirm the
  numerical consequence.
- **The diesel PM sulfur correction** (`exhaust.rs:1150-1180`) and the
  **SOx sulfur correction** (`exhaust.rs:632-643`). Gasoline-only fixture.
- **`nrsulfuradjustment` / `SulfurAlternate`.** Loaded and wired
  (`nonroad_loader.rs:1635-1662`, `executor.rs:1479-1487`) but inert here. Note
  the loader filters rows to `fuelTypeID ∈ {23, 24}` yet keys the resulting map
  by `engTechID` **string** alone. I did not check whether the diesel and
  gasoline `engTechID` spaces overlap; if they do, a gasoline tech could pick up
  a diesel alternate. Worth checking before porting the sulfur path.
- **RFG, altitude, evap and start-emission branches.** All gated off.
- **The `GramsPerGallon` / `GramsPerDay` unit-conversion branches**
  (`exhaust.rs:259-271`). Every rate here is `g/hp-hr`.

### 8.2 An inconsistency I noticed but did not chase

`compute_exhaust_iteration` builds its `PollutantFilter` by indexing
`emission_factors.get(pol * MXTECH + t)` — **no `year_index` stride**
(`executor.rs:1500-1507`) — while `calculate_exhaust` builds the same filter with
`inputs.year_index * (MXPOL * MXTECH) + pol * MXTECH + t`
(`executor.rs:2775-2784`), and the actual factor read uses
`ef_cell(year_index, pollutant, tech_index)` in both. For this fixture the
emission rates are model-year independent (every `nremissionrate` row is
`modelYearID = 1900`), so every year slice is identical and the discrepancy
cannot show. **I am not claiming this is a bug** — I did not read enough of the
`ExhaustFactorsLookup` construction to know which stride is correct at each call
site. A fixture with model-year-varying rates would distinguish them.

### 8.3 Output labelling I verified empirically but not in code

Running `moves.rs` on this fixture produces the 144 rows with correct keys and
quantities but leaves `stateID`, `countyID`, `fuelTypeID` and `roadTypeID`
**NULL**, where the canonical snapshot fills `26`, `26161`, `1`, `100`. It also
emits an extra `emissionRate` and `runHash` column and no `iterationID`. I
located the emission side (`emissions_to_dataframe`,
`nonroad_loader.rs:2380-2390`, which emits only nine columns) but **did not find
where canonical fills the geographic and fuel labels**. For the `.esm` port the
values are unambiguous — `countyID` from the RunSpec, `stateID = countyID/1000`,
`roadTypeID = 100`, `fuelTypeID` from `nrscc` — but the *rule* mapping nonroad
`fuelTypeID` 23/24 to MOVES `fuelTypeID` 2 is **unverified**; only gasoline
(1 → 1) appears in this fixture.

Likewise `hourID = 0` in every output row despite
`<outputtimestep value="Hour"/>` and `runspechour.hourID = 7`. I read this off
the data and it is consistent with NONROAD being a typical-day model, but I did
not find the code that zeroes it.

### 8.4 `nrhourallocation` — unused, but by inference

I verified there is no `store.get("nrhourallocation")` anywhere in the loader,
and the chain reproduces to ~5 × 10⁻⁶ without it, which is conclusive for *this*
port. I did **not** confirm that canonical MOVES also ignores it for an
hour-selected RunSpec — only that the numbers agree without it.

### 8.5 Fuel kind resolution: two mechanisms

`emission_adjustments` derives the fuel from the SCC prefix
(`fuel_for_scc(scc)`, `executor.rs:963`), while `compute_exhaust_iteration`
passes `options.fuel` — the *dispatch plan's* fuel (`executor.rs:1553`,
`simulation/mod.rs:200`) — into `clcems` for `cfrac`, `sox_conversion` and the
diesel-PM branch. For this fixture each dispatch group is a single SCC so the
two agree, and none of the `options.fuel`-dependent branches fire. **I did not
verify that `plan.fuel` is always the SCC's own fuel.** An `.esm` port should
treat fuel as a pure function of the SCC prefix (§5.3) and flag it if a fixture
ever disagrees.

### 8.6 A naming correction for PLAN.md

PLAN.md §3 Phase 1 lists "the temperature-adjustment quadratic" as a template
candidate. There is no quadratic on the exhaust path: the correction is
`exp(a · (T − 75))` with a threshold-selected coefficient (§4.2). The only
quadratic-ish forms in `emsadj.f` are the permeation corrections
`3.788519e-2 · exp(3.850818e-2 · T)` / `6.013899e-2 · exp(3.850818e-2 · T)`
(`exhaust.rs:664-666`), which are evap-only and not exercised here.

### 8.7 Things I deliberately did not model

- The engine also emits per-record total rows (`model_year = None`) alongside the
  by-model-year rows; `emissions_to_dataframe` discards them
  (`nonroad_loader.rs:2334-2341`). An `.esm` port needs only the by-model-year
  form.
- `MOVESActivityOutput` (144 rows in this snapshot) and the `translate_*` /
  `finalagg*` / `temporary*import` tables are output-pipeline artefacts, not
  inputs, and are out of scope for Phase 2's emission chain.
- Retrofit (`nrretrofitfactors` is empty; `options.retrofit_enabled` is false)
  and the `(1 − retro)` factor at `exhaust.rs:1222-1225`.

---

## 9. Summary for the `.esm` author

The whole fixture is one scalar formula evaluated over
`(SCC, equipment point, model year, engine tech, pollutant)` and summed to
`(SCC, model year, pollutant)`:

```
grams =  round1dp(pop_state)
       × surrogateFrac
       × modfrc[age]                                   ← scrptime → modyr → agedist
       × techFraction[latest mix year ≤ model year]
       × EF[pollutant, tech]                           ← nremissionrate, hp-binned
       × (hpAvg × loadFactor)                          ← unitcf.f, g/hp-hr branch
       × (1 + A · min(detage[age], cap)^B)             ← emfclc.f / clcems.f
       × exp(a_p · (tamb − 75)) × (1 − c_p · oxy)      ← emsadj.f
       × hoursUsedPerYear
       × monthFraction × 7 × dayFraction / daysInMonth
```

Seven `.esm` components, in dependency order: geography/allocation → population
→ activity → emission factors + deterioration → adjustments → unit conversion +
roll-up → output aggregation. Twenty-five joins (§3), of which three are not
plain equi-joins and want a precomputed key. Eight reusable expression templates
(§4). Expect 140 of 144 rows to match in binary64 at ≤ 7 × 10⁻⁶ relative, with
the four documented exceptions in §7.3.
