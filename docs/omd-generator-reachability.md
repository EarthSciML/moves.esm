# Which operating-mode-distribution generators the corpus can actually reach

`tools/calculator-coverage.py` began this rung by reporting eight live
generators unported. Seven of them are named in the table below. Before any of
them is worth writing model logic for, one question has to be answered with a
measurement: **does a snapshot in `../moves.rs/characterization/snapshots`
exercise it?** A module that MOVES loads but never runs is a rung that cannot
be verified here at all; porting it needs a RunSpec captured in `moves.rs`
first, which is a different piece of work.

This note is the measurement. It carries no `| Calculator path |` row on
purpose: it is evidence for a rung, not a port specification, and
`tools/calculator-coverage.py --check` must not read it as a coverage claim.

**One of the seven has since been reached.** `moves.rs` captured a
project-domain RunSpec (`scale-project`, 2026-09-10) for exactly this reason,
and it is the first and only snapshot in the corpus that class-loads
`LinkOperatingModeDistributionGenerator` or leaves a row in
`OpModeDistribution`. What that changed, and what it did **not** change for
the other four, is §"The four that stay unreachable".

## The two signals, and why one is not enough

**Signal 1 — class loading.** Each snapshot's `execution-trace.json` lists the
Java classes MOVES loaded for that run.

> **The brief for this work said the evidence is a `kind: "generator"` entry in
> `java_classes`. There is no such entry anywhere in the corpus.** Rolled over
> all 43 traces, `java_classes[*].kind` takes exactly five values —
> `common` (2,522), `framework` (2,716), `master` (1,942), `utils` (76) and
> `worker` (43). Generators are `kind: "master"` (or `framework`, for the
> abstract `Generator` base). The signal that works is the class NAME.

```
python3 - <<'PY'
import json, glob, os, collections
gen = collections.Counter()
for p in sorted(glob.glob('.../snapshots/*/execution-trace.json')):
    d = json.load(open(p))
    for c in d.get('java_classes', []):
        if 'Generator' in c['name']:
            gen[c['name'].split('.')[-1]] += 1
for n, c in gen.most_common(): print(c, n)
PY
```

**Signal 2 — output rows.** Class-loaded is not the same as produced-output;
the calculator track was burned by exactly this (`nr-pleasure-craft-state`
loaded `NRAirToxicsCalculator` without it ever emitting). So each generator's
loading is corroborated against the row count of the execution-database table
it writes, read from the parquet footer (`pq.ParquetFile(f).metadata.num_rows`
— never `read_table().to_pydict()`, which has OOMed this machine).

**Signal 2 has to be intersected with signal 1, and until 2026-09-10 nothing
here said so.** Three of the seven generators below write the SAME table,
`OpModeDistribution`. A count keyed on the table alone therefore reports the
same number for all three, and when `scale-project` made that number 1 the
document was being asked to claim output from two generators no snapshot has
ever loaded. The "snapshots with rows" column is now the **intersection**:
class-loaded here AND the table non-empty here.

That is a necessary condition and not a sufficient one — it does not attribute
a particular ROW to a particular generator, which needs the table's own
partitioning key. For `RatesOpModeDistribution`, written by **four** generators,
that key is `(roadTypeID, avgSpeedBinID)`, and
`docs/operating-mode-distribution.md` §6.5 is where that argument is made.
What the intersection buys is that a generator nothing loaded can no longer be
credited with a sibling's rows.

The corpus as measured: **44 snapshot directories, 43 with an
`execution-trace.json`** (`mixed-onroad-nonroad` carries `tables/` only), at
`moves.rs` commit `61f0d658`. It was 41 and 40 when this note was first
written. Every count below moves when the corpus does; that is what §35.5 is
about, and writing the date down turned out not to be enough — see "Keeping
these numbers honest".

## Keeping these numbers honest

It rotted anyway, twice.

The first time, the `moves-snapshot/v2` recapture with the `<day id=>`
correction went in, and every figure here that counts ROWS rather than
snapshots was silently wrong from that moment: fourteen of the twenty-three
per-snapshot counts, most of them exactly halved, because the fixtures that had
been running two days were now running one. Nothing failed. The note went on
being read as evidence for months, with the date it was true written at the top
of it, exactly as §35.5 asks.

So the date is not the mechanism. `tools/check-reachability-counts.py` is: it
parses the figures out of THIS FILE and re-derives each one from the corpus,
and `run-tests.sh` stage 2c fails when they disagree. 58 claims, covering the
corpus-size sentence, the `kind` histogram, every count in the table below,
`FuelEffectsGenerator`'s count in the prose under it, both per-snapshot grids
(membership and every row count), and the three-way set equality this note
calls its corroboration.

The second time was `scale-project`, and the checker did its job: it went red
with 25 of the 58 claims broken, on the same day the snapshot landed, instead
of leaving the prose to be quoted for another few months. It also exposed a
defect in **itself** — the table-keyed conflation described above — which is
the more interesting half. A checker can encode the same mistake the document
makes; twenty-two of the twenty-five failures were arithmetic and three were
the checker asking for a wrong answer.

The document stays the source of truth — the checker holds no copy of the
answers, only the code to re-derive them. Edit a number here and the checker
says whether the corpus agrees; change the corpus and it says which sentences
need rewriting. What it deliberately does not check is the `reachable?` column
and the interpretation around it: those are verdicts, argued from these
numbers and revised by hand, and a test that asserted them would only be
asserting that nobody had changed their mind.

## The table

`class-loaded in` is signal 1. `snapshots with rows` is the intersection of
both signals, per the section above — not the row count of the `writes` table,
which three of these rows share.

| generator | class-loaded in | writes | snapshots with rows | reachable? |
|---|---:|---|---:|---|
| `RatesOperatingModeDistributionGenerator` | **31** / 43 | `RatesOpModeDistribution` | **15** | **yes** |
| `StartOperatingModeDistributionGenerator` | **10** / 43 | `StartOpModeDistribution` | **9** | **yes** |
| `LinkOperatingModeDistributionGenerator` | **1** / 43 | `OpModeDistribution` | **1** | **yes, since 2026-09-10** |
| `OperatingModeDistributionGenerator` | 0 / 43 | `OpModeDistribution` | 0 | no — dead code |
| `MesoscaleLookupOperatingModeDistributionGenerator` | 0 / 43 | `OpModeDistribution` | 0 | no — dead code |
| `MesoscaleLookupTotalActivityGenerator` | 0 / 43 | `SourceHours`, `SHO` | 0 | no — dead code |
| `NewTvvYearGenerator` | 0 / 43 | — | — | no — no such class |

`FuelEffectsGenerator` (25 / 43) is the eighth unported generator and belongs to
a parallel rung; it is listed here only so the eight add up. It has since been
ported (`docs/fuel-effects-generator.md`), as have the first two rows of the
table (`docs/operating-mode-distribution.md`).

The three zeros in the `snapshots with rows` column are the ones the
intersection earns. `OpModeDistribution` is non-empty in exactly one snapshot
— `scale-project`, 122 rows — and a table-keyed count would put that 1 against
all three of the generators that write it.

### Which snapshots, exactly

`RatesOpModeDistribution` is non-empty in 15 snapshots:

| snapshot | rows | | snapshot | rows |
|---|---:|---|---|---:|
| `expand-counties` | 9 | | `process-apu` | 3 |
| `expand-criteria` | 33 | | `process-apu-single` | 3 |
| `expand-day` | 18 | | `process-extended-idle` | 1 |
| `expand-fueltype-diesel` | 18 | | `process-extended-idle-single` | 1 |
| `expand-month` | 9 | | `process-refueling` | 9 |
| `expand-sourcetype` | 46 | | `process-tirewear` | 16 |
| `mixed-onroad` | 9 | | `sample-runspec` | 9 |
| `scale-project` | 22 | | | |

**`scale-project`'s 22 are not all the same generator's**, and that is the
sharpest illustration in the corpus of why the `writes` column cannot be read
as attribution. One row (`roadTypeID` 1, `polProcessID` 602, `opModeID` 100) is
`StartOperatingModeDistributionGenerator`'s All-Starts row. The other 21
(`roadTypeID` **4**, the project link's own road type, `avgSpeedBinID` 0,
`avgBinSpeed` 30) are `LinkOperatingModeDistributionGenerator` copying its
freshly-computed `OpModeDistribution` across —
`LinkOperatingModeDistributionGenerator.java:448-458`. Four generators write
this table and `(roadTypeID, avgSpeedBinID)` is what separates them.

`StartOpModeDistribution` is non-empty in 9:

| snapshot | rows | | snapshot | rows |
|---|---:|---|---|---:|
| `expand-counties` | 5 | | `expand-sourcetype` | 29 |
| `expand-criteria` | 5 | | `mixed-onroad` | 7 |
| `expand-day` | 9 | | `process-refueling` | 5 |
| `expand-fueltype-diesel` | 12 | | `sample-runspec` | 4 |
| `expand-month` | 8 | | | |

The same 9 are the only ones carrying `SOMDGOpModes` (the generator's own
working table) and a populated `StartOpMode` input table — three independent
corroborations of one predicate.

**Those 9 are no longer the same as the snapshots that LOAD the generator.**
Until `scale-project` they were, and this note said so ("set-equal, not merely
equinumerous"). `scale-project` class-loads
`StartOperatingModeDistributionGenerator` and leaves `StartOpModeDistribution`
**empty**, so the load set is now 10 and the row set is still 9. The generator
did run — its All-Starts row is in `RatesOpModeDistribution` — but in PROJECT
domain its step 400 takes a different branch that reads `OpModeDistribution`
instead of `startsOpModeDistribution`
(`StartOperatingModeDistributionGenerator.java:381-431`), and the branch that
fills `StartOpModeDistribution` is not on that path. The three-way corroboration
among `StartOpModeDistribution`, `SOMDGOpModes` and `StartOpMode` still holds
exactly; it is the fourth set, class-loading, that has separated from them.

**`RatesOperatingModeDistributionGenerator` is the case the brief warned about:
31 loaded, 15 with rows.** Loading it and running it are different events, and
half the loads produce nothing. Its subscription list (processes 1, 90 and 91)
is what decides which; process 1's contribution is delegated to the external
`SourceTypePhysics` generator, so this module's own live output is the
degenerate hotelling distribution for processes 90 and 91.

## The one that was reached, and how

`scale-project` is a `<modeldomain value="PROJECT"/>` RunSpec over a single
1-mile urban-restricted-access link in Washtenaw County, July→August 2020,
hour 9, day 5, passenger cars only. Its input database is
`../moves.rs/characterization/county-inputs/washtenaw-project/setup-project.sql`,
which creates `OpModeDistribution` and `driveScheduleSecondLink` **empty on
purpose**: an empty `OpModeDistribution` is what makes
`LinkOperatingModeDistributionGenerator` compute one instead of echoing a
user-supplied one, and an empty `driveScheduleSecondLink` sends it down the
average-speed path rather than the trajectory path
(`LinkOperatingModeDistributionGenerator.java:325-372`).

Measured in the snapshot:

* `OpModeDistribution` — 122 rows, `isUserInput = 'N'` on all 122. The `'N'` is
  the whole point: it is MOVES marking the rows as its own output rather than
  the run's input.
* keys — `sourceTypeID` 21 only, `hourDayID` 95, `linkID` ∈ {1, −153, −1021}.
  The negative ids are the pseudo-links the generator writes for the two
  bracketing drive schedules (`…java:678-692`); link 1 is the real one.
* `polProcessID` ∈ {−1, 9101}. The −1 rows are the generator's own internal
  scratch and are explicitly excluded when it copies to
  `RatesOpModeDistribution` ("don't copy the generic polprocess entries",
  `…java:456`).

`ProjectTAG` — the PROJECT-domain **Total Activity Generator** — is
class-loaded in the same one snapshot and no other. See
`docs/link-operating-mode-distribution.md`.

## The four that stay unreachable, and why the reason is not "no RunSpec"

The previous version of this note gave one reason for all five: no RunSpec in
the corpus selects the project or mesoscale-lookup domain. That was true, and
it was the wrong level of explanation. `scale-project` supplied the missing
project RunSpec and only ONE of the four moved. The other three would not move
for any RunSpec, because **canonical MOVES does not instantiate them at all**.

### Three are dead code under `DO_RATES_FIRST`

`CompilationFlags.DO_RATES_FIRST` is `true` in the pinned MOVES source, and
`MOVESInstantiator.generateExecutionGraph` treats that as a hard reset:

* `MOVESInstantiator.java:1449` — `neededClassNames.clear()`, inside
  `if(CompilationFlags.DO_RATES_FIRST)`.
* `:1450-1456` re-adds exactly three unconditionally: `BaseRateCalculator`,
  `BaseRateGenerator`, `RatesOperatingModeDistributionGenerator`.
* `:1457-1491` is a `whiteList[]`, intersected with the pre-`clear()` set. The
  generators on it are `MeteorologyGenerator`,
  `AverageSpeedOperatingModeDistributionGenerator`,
  `EvaporativeEmissionsOperatingModeDistributionGenerator`,
  `FuelEffectsGenerator`, **`LinkOperatingModeDistributionGenerator`**,
  **`ProjectTAG`**, `SourceBinDistributionGenerator`,
  `StartOperatingModeDistributionGenerator`, `TankFuelGenerator`,
  `TankTemperatureGenerator` and `TotalActivityGenerator`.

`OperatingModeDistributionGenerator`,
`MesoscaleLookupOperatingModeDistributionGenerator` and
`MesoscaleLookupTotalActivityGenerator` are on neither list. The `clear()`
discards them and nothing puts them back. Two further details settle it:

* the `isMesoscaleLookup` block that would swap
  `MesoscaleLookupTotalActivityGenerator` in for `TotalActivityGenerator`
  (`:1427-1436`) is **commented out** in the source;
* the sibling swap that adds
  `MesoscaleLookupOperatingModeDistributionGenerator` (`:1437-1443`) is live,
  but it runs BEFORE the `clear()` at `:1449`, so its result is discarded on
  the next statement;
* `alsoInstantiate(String)` — the escape hatch a subscriber could use to pull a
  class in late — is declared at `:1817` and mentioned in a comment at `:176`,
  and has **zero call sites** anywhere under `gov/epa/otaq/moves`.

So no RunSpec, in any domain, at any scale, instantiates these three while
`DO_RATES_FIRST` is `true`. Capturing more snapshots cannot reach them. The
verdict column says "dead code" rather than "no RunSpec" because those are
different claims and only one of them is true.

**`moves.rs` diverges here, deliberately and undocumented until now.** Its
rates-first filter,
`../moves.rs/crates/moves-framework/src/calculator/registry.rs:554-597`
(`rates_first_excluded_calculators`), mirrors the canonical `whiteList[]` for
CALCULATORS and exempts generators outright — its own doc comment at `:550-553`
says "Only **calculators** are considered: generators are left untouched". So
`moves.rs` implements and can run all three (they are in its 17-generator
validation harness,
`crates/moves-calculators/tests/generator_validation/generators.rs`), where
canonical never instantiates one. Nothing in the `.esm` port depends on that,
and no fixture can see it, but it is a real difference in what the two models
consider live.

### One is not a class at all

`NewTvvYearGenerator` is the sharpest case, and the previous version of this
note got its provenance wrong in a way worth correcting explicitly. It said
"`CalculatorInfo.txt` names it against process 12, but the scan of the pinned
MOVES source found no class by that name to attach it to."

**`CalculatorInfo.txt` does not name it.** Grepped case-insensitively over the
entire pinned MOVES tree (MOVES5.0.1 @ `25dc6c83`), the string `newtvvyear`
occurs exactly three times, none of them in `CalculatorInfo.txt`:

```
database/MultidayTankVaporVentingCalculator.sql:335   -- Section NewTVVYear
database/MultidayTankVaporVentingCalculator.sql:432   -- End Section NewTVVYear
gov/.../ghg/TankVaporVentingCalculator.java:142       enabledSectionNames.add("NewTVVYear");
```

It is a **named SQL section** of the tank-vapour-venting calculator, switched
on by that calculator, in a file that calculator owns. There is no generator,
no class, no `Subscribe` line and no MasterLoop registration.

The `NewTvvYearGenerator` entry in
`../moves.rs/characterization/calculator-chains/calculator-dag.json` was added
by hand in `moves.rs` commit `f375a77c` to fix an unrelated snapshot-table
lookup, and its subscription carries `"source": "CalculatorInfo"`. That
attribution is false. Its own neighbouring fields say so: `"java_path": ""` and
`"registrations_count": 0`. `docs/new-tvv-year.md` proves the section really is
already in the corpus rather than asserting it here.

## What this leaves for the rung

Three of seven, up from two. `RatesOperatingModeDistributionGenerator` and
`StartOperatingModeDistributionGenerator` are specified in
`docs/operating-mode-distribution.md`; `LinkOperatingModeDistributionGenerator`
is specified in `docs/link-operating-mode-distribution.md`.

All three are **execution-database** generators, not `MOVESOutput` producers,
so §35 governs them: they live in `components/`, not in `fixtures/`, and their
specification borrows an existing fixture's snapshot for the coverage tool's
fixture leg — exactly as `docs/meteorology-generator.md` borrows
`process-pm-exhaust`.

The remaining four need no further capture and never will. Three are
unreachable in canonical MOVES as compiled, and the fourth is not a module.
