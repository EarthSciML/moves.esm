# `ProjectTAG` — computation specification

The port specification for the PROJECT-domain **Total Activity Generator**, written to the method of
`docs/link-operating-mode-distribution.md`: what it reads, the chain with source lines into the pinned MOVES
tree, worked examples that can be checked by hand, and a reproduction script that takes nothing from the
reference.

It was ported in 2026-10-19's step 7f (PLAN.md §7.3.40) as `onroad/model.esm`'s `act_projectSho`, and
`runspecs/scale-project.esm` and `runspecs/rates-project.esm` have reproduced through it since. But nothing
claimed it, so `tools/calculator-coverage.py` listed it as unported until 2026-11-08 (PLAN.md §7.3.53).
This document is that claim, and §6.5 is the evidence for it.

**All five outputs are ported.** Since
2026-11-09 (PLAN.md §7.3.55) `act_projectSho` runs once per link -- one per selected road type --
`st_projectStarts` is ProjectTAG's Starts and `hot_projectHours` its hotelling hours, through which
`runspecs/project-links.esm` reproduces running, start, brake-wear and tire-wear exhaust on three links and
`runspecs/project-hotelling.esm` extended idle and APU on an off-network link. Since §7.3.56 SHP is
`act_projectShp` and `SourceHours` is `act_projectShp` on the off-network link and `act_projectSourceHours`
(the link-volume product without the travel-time share; `act_projectSho` is it times the share) on an
on-network one, through which `runspecs/project-offnetwork.esm` reproduces permeation, fuel vapor venting and
fuel leaks on both links. The three fleet products share `lib/onroad_activity.esm`'s `off_network_fleet_hours`.
Since §7.3.58 the crankcase and refueling processes read them through their parents' rows
(`runspecs/project-crankcase.esm`, `project-refueling.esm`), the evaporative processes reproduce at Rates
scale over the PROJECT population -- the same off-network fleet x ageFraction, which ActivityCalculator writes
on the off-network link (`act_projectPopulation`; `runspecs/rates-project-evap.esm`) -- and
`runspecs/project-useromd.esm` reproduces a link whose user states its operating modes. Since §7.3.60 a link
is a LOCATION rather than a (county, road type), so two links on one road type are two
(`runspecs/project-multilink.esm`), and `project-grades`, `project-useromd-gaps` and `project-startconflict`
reproduce links of different grades and speeds, user distributions that leave gaps, and conflicting start modes.
`run_domainUnported` counts any PROJECT-domain run that needs a path not ported (`rspp_hasProjectGenerator`: the
crankcase and refueling processes at Rates scale; and evaporative rows a Rates run would write to
RatePerDistance), and also a selected road type with no link, an on-network link of zero speed and a second
county; `tools/check-runspec-shape.py` asserts that count is 0.
So a PROJECT-domain run that needs an unported path fails loudly rather than emitting a plausible wrong
number.

---

## 0. The generator at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/scale-project.xml` and `rates-project.xml` (one link); `project-links.xml` (three links, two source types, an off-network link); `project-offnetwork.xml` and `project-hotelling.xml` (an on-network and an off-network link, source types 21 and 62; the second without the evaporative processes); since §7.3.58 `project-crankcase.xml`, `project-refueling.xml` and `project-useromd.xml` (two on-network links on road types 4 and 5 and an off-network link, source types 21 and 62) and `rates-project-evap.xml` (`project-offnetwork`'s network at Rates scale); since §7.3.60 `project-multilink.xml` (two links on each of road types 4 and 5), `project-grades.xml` (grades and out-of-bounds speeds), `project-useromd-gaps.xml` and `project-startconflict.xml` |
| Model | ONROAD, `modeldomain` **`PROJECT`** |
| Reads | `link`, `linkSourceTypeHour`, `offNetworkLink`, `avft`, `sourceTypeAgeDistribution`, `dayOfAnyWeek`, `hourDay`, `runSpecHourDay`, `runSpecDay`, `runSpecMonth`, `runSpecSourceType` |
| Writes | `SHO` (with `distance`), `Starts`, `SHP`, `SourceHours`, `hotellingHours` |
| Calculator path | **`ProjectTAG`** — the PROJECT-domain counterpart of TotalActivityGenerator, whose activity tables the base-rate chain reads |
| Rows | 328 `SHO` over four snapshots, 164 `Starts` over three (`scale-project` and `rates-project` select start exhaust, so ProjectTAG writes Starts there, unread), 82 `SHP`, 164 `SourceHours`, 123 `hotellingHours` (§6.5) |
| Ported by | SHO: `onroad/model.esm`'s `act_projectSho` (per road type), selected by `act_sho` under `run_isProjectDomain`, with `lib/onroad_activity.esm`'s `link_travel_hours_share`. Starts: `st_projectStarts`, selected by `st_starts`. Hotelling hours: `hot_projectHours`, selected by `hot_hours`, summed over the fuel split. SHP and SourceHours: `act_projectShp` and `act_projectSourceHours`, selected by `act_shp` and `act_sourceHours` (PLAN.md §7.3.56). The PROJECT population, which ActivityCalculator writes from the same fleet, is `act_projectPopulation` (§7.3.58) |
| Java | `.../ghg/ProjectTAG.java` (`allocateTotalActivityBasis`: :354-385 SHO, :387-404 SHP, :406-433 Starts, :435-463 hotelling hours, :465-519 SourceHours) |
| Rust | `../moves.rs/crates/moves-calculators/src/generators/project_tag.rs` |

## 1. The computation

`ProjectTAG.java:354-385`, once per link, for each source type, age, month and hour-day of the run:

```
SHO      = linkVolume x sourceTypeHourFraction x noOfRealDays x ageFraction x least(linkLength / linkAvgSpeed, 1)
distance = SHO x linkAvgSpeed
```

* The **link** supplies `linkVolume` (vehicles per hour), `linkLength` (miles) and `linkAvgSpeed` (mph).
  `least(length/speed, 1)` is the fraction of the hour that a vehicle entering the link spends on it, capped
  at the whole hour.
* If `linkAvgSpeed` is not positive, the SQL's `else` arm keeps the product without the share, and the
  distance is 0. An off-network link has speed 0, but no `linkSourceTypeHour` row in any snapshot, so the
  arm still writes no row (§6.6).
* `sourceTypeHourFraction` is the link's share for the source type. `linkSourceTypeHour` has no hour column,
  despite its name, so the same share applies at every hour. It is a FLOAT column, and §6.5 narrows it to
  binary32 before multiplying: `project-links`' 0.6 decides one `distance` cell's sixth digit.
* `noOfRealDays` is the day type's count of days in a week: 5 for weekdays.
* `ageFraction` is `sourceTypeAgeDistribution` at the run's year. ProjectTAG builds it from
  `sourceTypeAgePopulation` when the year is missing (:315-350); the default database already has 2020, so
  no run reaches that branch.
* There is no VMT, no road-type distribution and no SHO allocation factor. A project's activity is its
  links' volumes, which is the whole difference from `TotalActivityGenerator`. The month is a label on the
  row, not a factor in it.
* The insert is `insert ignore` on (hourDay, month, year, age, link, source type), so a repeated key keeps its
  first row. No run repeats a key, and §6.5 asserts that rather than assuming it.

The model writes the product in the SQL's association: ((volume x fraction) x days) x ageFraction, then the
share. Since the generator runs once per link, `act_projectSho` is keyed by LOCATION: the run's selected road
types, each the first link on it, followed by every further link on a road type already selected
(`lnk_locationOrdinal`, `n_projectExtraLinks`; PLAN.md §7.3.60). The Link table's length, volume and speed are
FLOAT columns: `project-multilink`'s 0.3 mi decides three SHO cells' sixth digit, and §6.5 narrows them.

The other four outputs read the zone's **off-network fleet**, `offNetworkLink`, rather than a link's volume:

```
Starts         = vehiclePopulation x startFraction x ageFraction x noOfRealDays                (:406-433)
SHP            = vehiclePopulation x parkedVehicleFraction x ageFraction x noOfRealDays        (:387-404)
hotellingHours = sum over the cohort's (engine tech) avft rows of
                 vehiclePopulation x extendedIdleFraction x ageFraction x noOfRealDays x fuelEngFraction,
                 per fuel type, source type 62 only                                             (:435-463)
SourceHours    = SHP's product on the off-network link (:467-487);
                 on an on-network link, SHO's product WITHOUT the travel-time share            (:488-516)
```

* **Starts** are written when start exhaust is selected, per zone. At Rates scale the SQL drops
  `startFraction` (`isRates ? "" : "*onl.startFraction"`). Ported as `st_projectStarts`; the starts' operating
  modes are the user's (`opModeDistribution`, StartOperatingModeDistributionGenerator's PROJECT arm;
  `docs/operating-mode-distribution.md` §8.3, `sod_weight`).
* **SHP** and **SourceHours** are written for the evaporative processes: SHP once per zone when the location
  is the off-network link, SourceHours once per link. Ported as `act_projectShp` and
  `act_projectSourceHours` (PLAN.md §7.3.56), at both scales since §7.3.58.
* **hotellingHours** are written for extended idle and APU, for source type 62 only, split by fuel through
  `avft` at the cohort's model year (`modelYearID = yearID - ageID`). Ported summed over the fuel split, as the
  DEFAULT path's `hot_hours` is: the project database's `avft` is the default `sampleVehiclePopulation` summed
  over regulatory class, so its fractions sum to the DEFAULT path's `hot_stmyTotal`. MOVES applies no
  AdjustHotelling to them here (the project databases' `hotellingHoursPerDay` is empty).

## 6. Hand-checkable worked examples

### 6.1 `scale-project`, age 0

The one link has volume 1000, length 1 mile and average speed 30 mph, on road type 4. Source type 21's
`sourceTypeHourFraction` is 1, the day type is weekdays (`noOfRealDays` 5), and `ageFraction` at
(21, 2020, age 0) is 0.032825069034021076.

```
1000 x 1 x 5 x 0.032825069034021076 = 164.12534517010538
x least(1/30, 1) = 164.12534517010538 / 30 = 5.4708448390035
```

The snapshot stores `SHO` 5.47084, and `distance` 5.4708448390035 x 30 = 164.125, stored as 164.125. Both
are FLOAT columns: binary32, rendered to six digits.

### 6.2 `project-links`, link 2, source type 32, age 0

Link 2 has volume 600, length 0.5 mile and speed 25 mph, on road type 5. Source type 32's share on it is
0.4, stored as binary32 0.4000000059604645, and `ageFraction` at (32, 2020, age 0) is 0.09161354025564963.

```
600 x 0.4000000059604645 x 5 x 0.09161354025564963 = 109.93624994...
x least(0.5/25, 1) = x 0.02 = 2.1987249988991464          stored SHO 2.19872
x 25 = 54.96812497247866                                    stored distance 54.9681
```

### 6.3 `project-links`, Starts, source type 32, age 0

`offNetworkLink` holds 400 light commercial trucks with start fraction 0.08 (binary32 0.07999999821186066):

```
400 x 0.07999999821186066 x 0.09161354025564963 x 5 = 14.65816611326839    stored starts 14.6582
```

### 6.5 The reproduction script

`./run-project-tag-oracle.sh` extracts this fence and runs it over the snapshot corpus and the moves.rs
RunSpec XMLs. It reads only each run's execution-database inputs (§0's Reads row); the five output tables
are read only to compare against. FLOAT input columns (`link`'s length, volume and speed, `linkSourceTypeHour`'s share, `offNetworkLink`'s
fractions, `avft`'s fraction) are narrowed to binary32 first, as MariaDB stores them. It asserts:

* **Scheduling.** `linkSourceTypeHour`, the one table only ProjectTAG reads, is populated on exactly the
  PROJECT-domain runs: 5 of the 67 snapshots that carry the table. And each of the five outputs is populated
  exactly on the runs whose processes subscribe to it.
* **Key sets.** For each PROJECT-domain run and output, the computed keys equal the reference's exactly.
* **Values.** Every FLOAT cell (`SHO`, `distance`, `starts`, `SHP`, `sourceHours`) equals the reference's
  binary32 six-digit rendering; `hotellingHours` is a DOUBLE column and is held within 1e-6 relative.
* **Floors.** At least 4 PROJECT-domain runs, 328 `SHO`, 164 `Starts`, 82 `SHP`, 164 `SourceHours` and 123
  `hotellingHours` rows. These are lower bounds, not equalities, because the corpus grows
  (`docs/esm-conventions.md` §35.5).

```python
"""ProjectTAG's SHO, Starts, SHP, SourceHours and hotelling hours (ProjectTAG.java:354-519),
from each PROJECT-domain run's execution-database inputs alone, against that run's own tables."""
import glob, pathlib, re, sys
import numpy as np
import pandas as pd

snaps = pathlib.Path(sys.argv[1])
xmls = pathlib.Path(sys.argv[2])  # moves.rs characterization/fixtures
TIME = ["hourDayID", "monthID", "yearID", "ageID"]


def table(run, name):
    hits = glob.glob(str(snaps / run / "tables" / f"db__movesexecution*__{name}.parquet"))
    if len(hits) != 1:
        sys.exit(f"{run}: {len(hits)} `{name}` tables")
    d = pd.read_parquet(hits[0])
    for c in d.columns:  # moves-snapshot/v2 stores DECIMAL and FLOAT as text
        if d[c].dtype == object:
            try:
                d[c] = pd.to_numeric(d[c]).astype(float)
            except (ValueError, TypeError):
                pass
    return d


def f32(col):
    """A MariaDB FLOAT input column: binary32, widened back to double for the SQL's arithmetic."""
    return col.astype(np.float32).astype(float)


def domain(run):
    m = re.search(r'<modeldomain value="(\w+)"', (xmls / f"{run}.xml").read_text())
    return m.group(1) if m else "DEFAULT"


def float_rendering(x):
    """The reference column is a MariaDB FLOAT: binary32, six digits."""
    return float(f"{float(np.float32(x)):.6g}")


def frame(run):
    """The run's (hourDay, month, source type, age) cross product, as the SQL's FROM builds it."""
    stad = table(run, "sourcetypeagedistribution")
    year = int(table(run, "runspecyear")["yearID"].iloc[0])
    return (table(run, "hourday").merge(table(run, "runspechourday"), on="hourDayID")
            .merge(table(run, "dayofanyweek"), on="dayID")
            .merge(table(run, "runspecday"), on="dayID")
            .merge(table(run, "runspecmonth"), how="cross")
            .merge(table(run, "runspecsourcetype"), how="cross")
            .merge(stad[stad.yearID == year], on="sourceTypeID"))


def off_network(run):
    onl = table(run, "offnetworklink")
    for c in ("vehiclePopulation", "startFraction", "extendedIdleFraction", "parkedVehicleFraction"):
        onl[c] = f32(onl[c])
    return frame(run).merge(onl, on="sourceTypeID")


def compare(run, what, got, ref, key, cols, rendered=True, rel_gate=0.0):
    """Key set exact; each value equal to the reference's FLOAT rendering, or within rel_gate."""
    assert not got.duplicated(key).any(), f"{run} {what}: a key the SQL's insert ignore would collapse"
    m = got.merge(ref, on=key, how="outer", suffixes=("", "_ref"), indicator=True)
    missing, extra = int((m._merge == "right_only").sum()), int((m._merge == "left_only").sum())
    print(f"{run}: {len(got)} {what} keys computed, {len(ref)} in the reference, "
          f"{missing} missing, {extra} extra")
    assert missing == 0 and extra == 0, "the key sets differ"
    for c, rc in cols:
        rel = ((m[c] - m[rc]).abs() / m[rc].abs().where(m[rc] != 0, 1))
        bad = m[m[c].map(float_rendering) != m[rc]] if rendered else m[rel > rel_gate]
        how = "equal the reference's six-digit FLOAT rendering" if rendered else f"within {rel_gate:g} relative"
        print(f"  {rc}: {len(m) - len(bad)} of {len(m)} cells {how} (worst rel {rel.max():.3e})")
        assert bad.empty, bad[key + [c, rc]].head().to_string()
    return len(got)


def sho(run):
    link = table(run, "link")
    for c in ("linkLength", "linkVolume", "linkAvgSpeed"):  # FLOAT columns (project-multilink's 0.3 mi)
        link[c] = f32(link[c])
    lsth = table(run, "linksourcetypehour")
    lsth["sourceTypeHourFraction"] = f32(lsth.sourceTypeHourFraction)
    out = []
    for _, l in link.iterrows():  # the generator is called once per link
        q = frame(run).merge(lsth[lsth.linkID == l.linkID], on="sourceTypeID")
        base = l.linkVolume * q.sourceTypeHourFraction * q.noOfRealDays * q.ageFraction
        if l.linkAvgSpeed > 0:
            share = min(l.linkLength / l.linkAvgSpeed, 1.0)
            q["SHOc"], q["distancec"] = base * share, base * share * l.linkAvgSpeed
        else:
            q["SHOc"], q["distancec"] = base, 0.0
        q["linkID"] = l.linkID
        out.append(q)
    return pd.concat(out)


def run_sho(run):
    ref = table(run, "sho")
    ref = ref[ref.linkID.isin(table(run, "link").linkID)]
    return compare(run, "SHO", sho(run), ref, TIME + ["linkID", "sourceTypeID"],
                   [("SHOc", "SHO"), ("distancec", "distance")])


def is_rates(run):
    return '<modelscale value="Rates"' in (xmls / f"{run}.xml").read_text()


def run_starts(run):
    q = off_network(run)
    if is_rates(run):  # `isRates ? "" : "*onl.startFraction"` (java:414)
        q["startsc"] = q.vehiclePopulation * q.ageFraction * q.noOfRealDays
    else:
        q["startsc"] = q.vehiclePopulation * q.startFraction * q.ageFraction * q.noOfRealDays
    return compare(run, "Starts", q, table(run, "starts"), TIME + ["sourceTypeID"], [("startsc", "starts")])


def run_shp(run):
    q = off_network(run)
    q["SHPc"] = q.vehiclePopulation * q.parkedVehicleFraction * q.ageFraction * q.noOfRealDays
    return compare(run, "SHP", q, table(run, "shp"), TIME + ["sourceTypeID"], [("SHPc", "SHP")])


def run_source_hours(run):
    link = table(run, "link")
    link["linkVolume"] = f32(link.linkVolume)
    off = off_network(run)
    off["sourceHoursc"] = off.vehiclePopulation * off.parkedVehicleFraction * off.ageFraction * off.noOfRealDays
    off["linkID"] = int(link[link.roadTypeID == 1].linkID.iloc[0])
    on = sho(run)
    on = on.merge(link[["linkID", "linkVolume"]], on="linkID")
    on["sourceHoursc"] = on.linkVolume * on.sourceTypeHourFraction * on.noOfRealDays * on.ageFraction
    return compare(run, "SourceHours", pd.concat([off, on]), table(run, "sourcehours"),
                   TIME + ["linkID", "sourceTypeID"], [("sourceHoursc", "sourceHours")])


def run_hotelling(run):
    avft = table(run, "avft")
    avft["fuelEngFraction"] = f32(avft.fuelEngFraction)
    q = off_network(run)
    q = q[q.sourceTypeID == 62].copy()
    q["modelYearID"] = q.yearID - q.ageID
    q = q.merge(avft, on=["sourceTypeID", "modelYearID"])
    q["hh"] = (q.vehiclePopulation * q.extendedIdleFraction * q.ageFraction * q.noOfRealDays
               * q.fuelEngFraction)
    q = q.groupby(TIME + ["sourceTypeID", "fuelTypeID"], as_index=False).hh.sum()
    # hotellingHours is a DOUBLE column, not a FLOAT: compared within 1e-6, not at six digits.
    return compare(run, "hotellingHours", q, table(run, "hotellinghours"),
                   TIME + ["sourceTypeID", "fuelTypeID"], [("hh", "hotellingHours")],
                   rendered=False, rel_gate=1e-6)


project, other = [], []
for d in sorted(p.name for p in snaps.iterdir() if p.is_dir()):
    lh = glob.glob(str(snaps / d / "tables" / "db__movesexecution*__linksourcetypehour.parquet"))
    if not lh or not (xmls / f"{d}.xml").exists():
        continue
    (project if domain(d) == "PROJECT" else other).append((d, len(pd.read_parquet(lh[0]))))

# Scheduling: linkSourceTypeHour, the table only ProjectTAG reads, is populated
# exactly on the PROJECT-domain runs.
for d, n in other:
    assert n == 0, f"{d}: {n} linkSourceTypeHour rows outside PROJECT domain"
for d, n in project:
    assert n > 0, f"{d}: a PROJECT-domain run with no linkSourceTypeHour"
print(f"linkSourceTypeHour populated on {len(project)} PROJECT-domain run(s) "
      f"and empty on {len(other)} others")

# Each output is checked on every PROJECT run whose reference table has rows,
# and a populated table on a run the SQL would not write it for is a failure:
# the subscription is the process (ProjectTAG.java:243-282).
totals = {"SHO": 0, "Starts": 0, "SHP": 0, "SourceHours": 0, "hotellingHours": 0}
for d, _ in project:
    pps = set(table(d, "runspecpollutantprocess").polProcessID % 100)
    rts = set(table(d, "runspecroadtype").roadTypeID)
    evap = bool(pps & {11, 12, 13})
    expect = {"SHO": True, "Starts": 2 in pps, "SHP": evap and 1 in rts, "SourceHours": evap,
              "hotellingHours": bool(pps & {90, 91}) and 62 in set(table(d, "runspecsourcetype").sourceTypeID)}
    for what, fn, name in (("SHO", run_sho, "sho"), ("Starts", run_starts, "starts"), ("SHP", run_shp, "shp"),
                           ("SourceHours", run_source_hours, "sourcehours"),
                           ("hotellingHours", run_hotelling, "hotellinghours")):
        populated = len(table(d, name)) > 0
        assert populated == expect[what], f"{d}: {what} populated={populated}, expected {expect[what]}"
        if populated:
            totals[what] += fn(d)

print("totals: " + ", ".join(f"{k} {v}" for k, v in totals.items()))
# Floors: lower bounds, not equalities, because the corpus grows.
assert len(project) >= 4, "fewer PROJECT-domain snapshots than when this was written"
for k, floor in (("SHO", 328), ("Starts", 164), ("SHP", 82), ("SourceHours", 164), ("hotellingHours", 123)):
    assert totals[k] >= floor, f"fewer {k} rows than when this was written"
```

### 6.6 What it does not reach

* **The `else` arm.** No snapshot has an on-network link with `linkAvgSpeed` <= 0, and the off-network links
  have no `linkSourceTypeHour` row. The template's `ifelse` follows the SQL, but nothing tests it.
* **Two links on one road type** is reproduced since §7.3.60 (`project-multilink`, 328 SHO and 410 SourceHours
  keys over four on-network links).
* **Missing age distributions.** ProjectTAG grows a missing year's age distribution from population
  (:315-350, through `TotalActivityGenerator`). Every run finds 2020 in the default database.
* **More than one hour-day.** Every PROJECT snapshot has one.
* **Evaporative RatePerDistance.** `rates-project-evap` (PLAN.md §7.3.58) exercises SHP and `SourceHours` at
  Rates scale off-network, where the rates are per vehicle of the PROJECT population. It selects no running
  exhaust, so MOVES writes no distance activity and no on-network RatePerDistance row; a run that would is
  refused (`run_ratesProjectEvapDistance`).
* **An avft that is not the sample vehicle population's.** The model sums the fuel split back with
  `hot_stmyTotal`; a project database whose `avft` differs from AVFTTool's default would need the split ported.
