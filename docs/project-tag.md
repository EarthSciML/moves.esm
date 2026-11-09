# `ProjectTAG` — computation specification

The port specification for the PROJECT-domain **Total Activity Generator**, written to the method of
`docs/link-operating-mode-distribution.md`: what it reads, the chain with source lines into the pinned MOVES
tree, worked examples that can be checked by hand, and a reproduction script that takes nothing from the
reference.

It was ported in 2026-10-19's step 7f (PLAN.md §7.3.40) as `onroad/model.esm`'s `act_projectSho`, and
`runspecs/scale-project.esm` and `runspecs/rates-project.esm` have reproduced through it since. But nothing
claimed it, so `tools/calculator-coverage.py` listed it as unported until 2026-11-08 (PLAN.md §7.3.53).
This document is that claim, and §6.5 is the evidence for it.

**Only the SHO path is ported.** ProjectTAG also writes SHP for an off-network link, `Starts`, hotelling
hours and `SourceHours`, and none of those is ported. `run_domainUnported` counts any PROJECT-domain run
that would need one: an emitted pollutant-process other than running exhaust, or a second link or county.
`tools/check-runspec-shape.py` asserts that count is 0. So a PROJECT-domain run that needs an unported path
fails loudly rather than emitting a plausible wrong number.

---

## 0. The generator at a glance

| | |
|---|---|
| RunSpec | `../moves.rs/characterization/fixtures/scale-project.xml` (and `rates-project.xml`, its Rates-scale twin) |
| Model | ONROAD, `modeldomain` **`PROJECT`** |
| Reads | `link`, `linkSourceTypeHour`, `sourceTypeAgeDistribution`, `dayOfAnyWeek`, `hourDay`, `runSpecHourDay`, `runSpecDay`, `runSpecMonth`, `runSpecSourceType` |
| Writes | `SHO` (41 rows in each run), with its `distance` column |
| Calculator path | **`ProjectTAG`** — the PROJECT-domain counterpart of TotalActivityGenerator, whose SHO the base-rate chain reads |
| Rows | 41 `SHO` rows in each of two snapshots, 82 in all (§6.5) |
| Ported by | `onroad/model.esm`'s `act_projectSho`, selected by `act_sho` under `run_isProjectDomain`; the link's travel-time share is `lib/onroad_activity.esm`'s `link_travel_hours_share` |
| Java | `.../ghg/ProjectTAG.java` (`allocateTotalActivityBasis`, :354-385 for SHO) |
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
  distance is 0. Neither snapshot exercises this arm (§6.6).
* `sourceTypeHourFraction` is the link's share for the source type. `linkSourceTypeHour` has no hour column,
  despite its name, so the same share applies at every hour.
* `noOfRealDays` is the day type's count of days in a week: 5 for weekdays.
* `ageFraction` is `sourceTypeAgeDistribution` at the run's year. ProjectTAG builds it from
  `sourceTypeAgePopulation` when the year is missing (:315-350); the default database already has 2020, so
  neither run reaches that branch.
* There is no VMT, no road-type distribution and no SHO allocation factor. A project's activity is its
  links' volumes, which is the whole difference from `TotalActivityGenerator`. The month is a label on the
  row, not a factor in it.
* The insert is `insert ignore` on (hourDay, month, year, age, link, source type), so a repeated key keeps its
  first row. Neither run repeats a key, and §6.5 asserts that rather than assuming it.

The model writes the product in the SQL's association: ((volume x fraction) x days) x ageFraction, then the
share.

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

### 6.5 The reproduction script

`./run-project-tag-oracle.sh` extracts this fence and runs it over the snapshot corpus and the moves.rs
RunSpec XMLs. It reads only each run's execution-database inputs (§0's Reads row); `SHO` is read only to
compare against. It asserts:

* **Scheduling.** `linkSourceTypeHour`, the one table only ProjectTAG reads, is populated on exactly the
  PROJECT-domain runs. That is 2 of the 64 snapshots that carry the table; it is empty on the other 62.
* **Key set.** For each PROJECT-domain run, the computed SHO keys equal the reference's exactly: 0 missing
  and 0 extra.
* **Values.** Every `SHO` and `distance` cell, narrowed to binary32 and rendered to six digits, equals the
  reference: 82 of 82 for each column.
* **Floors.** At least 2 PROJECT-domain runs and at least 82 rows. These are lower bounds, not equalities,
  because the corpus grows (`docs/esm-conventions.md` §35.5).

```python
"""ProjectTAG's SHO and distance (ProjectTAG.java:354-385), from each PROJECT-
domain run's execution-database inputs alone, against that run's own SHO."""
import glob, pathlib, re, sys
import numpy as np
import pandas as pd

snaps = pathlib.Path(sys.argv[1])
xmls = pathlib.Path(sys.argv[2])  # moves.rs characterization/fixtures
KEY = ["hourDayID", "monthID", "yearID", "ageID", "linkID", "sourceTypeID"]


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


def domain(run):
    m = re.search(r'<modeldomain value="(\w+)"', (xmls / f"{run}.xml").read_text())
    return m.group(1) if m else "DEFAULT"


def float_rendering(x):
    """The reference column is a MariaDB FLOAT: binary32, six digits."""
    return float(f"{float(np.float32(x)):.6g}")


def sho(run):
    link = table(run, "link")
    lsth = table(run, "linksourcetypehour")
    stad = table(run, "sourcetypeagedistribution")
    year = int(table(run, "runspecyear")["yearID"].iloc[0])
    frame = (table(run, "hourday").merge(table(run, "runspechourday"), on="hourDayID")
             .merge(table(run, "dayofanyweek"), on="dayID")
             .merge(table(run, "runspecday"), on="dayID")
             .merge(table(run, "runspecmonth"), how="cross")
             .merge(table(run, "runspecsourcetype"), how="cross")
             .merge(stad[stad.yearID == year], on="sourceTypeID"))
    out = []
    for _, l in link.iterrows():  # the generator is called once per link
        q = frame.merge(lsth[lsth.linkID == l.linkID], on="sourceTypeID")
        base = l.linkVolume * q.sourceTypeHourFraction * q.noOfRealDays * q.ageFraction
        if l.linkAvgSpeed > 0:
            share = min(l.linkLength / l.linkAvgSpeed, 1.0)
            q["SHO"], q["distance"] = base * share, base * share * l.linkAvgSpeed
        else:
            q["SHO"], q["distance"] = base, 0.0
        q["linkID"] = l.linkID
        out.append(q)
    got = pd.concat(out)
    # `insert ignore` keeps a key's FIRST row. No run here repeats a key; if
    # one ever does, the scan order matters and has to be decided first.
    assert not got.duplicated(KEY).any(), f"{run}: a key the SQL would collapse"
    ref = table(run, "sho")
    ref = ref[ref.linkID.isin(link.linkID)]
    m = got.merge(ref, on=KEY, how="outer", suffixes=("", "_ref"), indicator=True)
    missing, extra = int((m._merge == "right_only").sum()), int((m._merge == "left_only").sum())
    print(f"{run}: {len(got)} SHO keys computed, {len(ref)} in the reference, "
          f"{missing} missing, {extra} extra")
    assert missing == 0 and extra == 0, "the key sets differ"
    for c in ("SHO", "distance"):
        bad = m[m[c].map(float_rendering) != m[c + "_ref"]]
        rel = ((m[c] - m[c + "_ref"]).abs() / m[c + "_ref"].abs().where(m[c + "_ref"] != 0, 1)).max()
        print(f"  {c}: {len(m) - len(bad)} of {len(m)} cells equal the reference's "
              f"six-digit FLOAT rendering (worst rel {rel:.3e})")
        assert bad.empty, bad[KEY + [c, c + "_ref"]].head().to_string()
    return len(got)


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
assert len(project) >= 2, "fewer PROJECT-domain snapshots than when this was written"
total = sum(sho(d) for d, _ in project)
assert total >= 82, "fewer SHO rows than when this was written"
```

### 6.6 What it does not reach

* **The `else` arm.** No snapshot has a link with `linkAvgSpeed` <= 0. The template's `ifelse` follows the
  SQL, but nothing tests it.
* **Several links or source types.** Both runs have one link, one source type and one hour. The per-link
  loop and the cross product are written as the SQL has them, and are exercised only at size 1.
  `run_domainUnported` refuses a second link.
* **Missing age distributions.** ProjectTAG grows a missing year's age distribution from population
  (:315-350, through `TotalActivityGenerator`). Both runs find 2020 in the default database.
* **The other outputs.** SHP, `Starts`, hotelling hours and `SourceHours` are not ported, and are refused as
  described at the top of this document.
