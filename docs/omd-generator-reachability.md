# Which operating-mode-distribution generators the corpus can actually reach

`tools/calculator-coverage.py` reports eight live generators unported. Seven of
them are named below. Before any of them is worth writing model logic for, one
question has to be answered with a measurement: **does a snapshot in
`../moves.rs/characterization/snapshots` exercise it?** A module that MOVES
loads but never runs is a rung that cannot be verified here at all; porting it
needs a RunSpec captured in `moves.rs` first, which is a different piece of
work.

This note is the measurement. It carries no `| Calculator path |` row on
purpose: it is evidence for a rung, not a port specification, and
`tools/calculator-coverage.py --check` must not read it as a coverage claim.

## The two signals, and why one is not enough

**Signal 1 — class loading.** Each snapshot's `execution-trace.json` lists the
Java classes MOVES loaded for that run.

> **The brief for this work said the evidence is a `kind: "generator"` entry in
> `java_classes`. There is no such entry anywhere in the corpus.** Rolled over
> all 42 traces, `java_classes[*].kind` takes exactly five values —
> `common` (2,450), `framework` (2,645), `master` (1,890), `utils` (74) and
> `worker` (42). Generators are `kind: "master"` (or `framework`, for the
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

The corpus as measured: **43 snapshot directories, 42 with an
`execution-trace.json`** (`mixed-onroad-nonroad` carries `tables/` only), at
`moves.rs` commit `eb11cb71`. It was 41 and 40 when this note was first written;
`chain-so2-co2e-mechanism` and its control landed while the rung was in
progress and moved every count below, which is §35.5's point about writing down
the date a corpus-wide figure was true. Writing it down turned out not to be
enough — see "Keeping these numbers honest" below. **Neither changes a verdict**: both are
ONROAD, both class-load `RatesOperatingModeDistributionGenerator` for Running
Exhaust, and both emit **zero** `RatesOpModeDistribution` rows.

## Keeping these numbers honest

It rotted anyway. The `moves-snapshot/v2` recapture with the `<day id=>`
correction went in, and every figure in this note that counts ROWS rather than
snapshots was silently wrong from that moment: fourteen of the twenty-three
per-snapshot counts in the two grids below, most of them exactly halved,
because the fixtures that had been running two days were now running one.
Nothing failed. The note went on being read as evidence for months, with the
date it was true written at the top of it, exactly as §35.5 asks.

So the date is not the mechanism. `tools/check-reachability-counts.py` is: it
parses the figures out of THIS FILE and re-derives each one from the corpus,
and `run-tests.sh` stage 2c fails when they disagree. 58 claims, covering the
corpus-size sentence, the `kind` histogram, every count in the table below,
`FuelEffectsGenerator`'s count in the prose under it, both per-snapshot grids
(membership and every row count), and the three-way set equality this note
calls its corroboration.

The document stays the source of truth — the checker holds no copy of the
answers, only the code to re-derive them. Edit a number here and the checker
says whether the corpus agrees; change the corpus and it says which sentences
need rewriting. What it deliberately does not check is the `reachable?` column
and the interpretation around it: those are verdicts, argued from these
numbers and revised by hand, and a test that asserted them would only be
asserting that nobody had changed their mind.

## The table

| generator | class-loaded in | writes | snapshots with rows | reachable? |
|---|---:|---|---:|---|
| `RatesOperatingModeDistributionGenerator` | **30** / 42 | `RatesOpModeDistribution` | **14** | **yes** |
| `StartOperatingModeDistributionGenerator` | **9** / 42 | `StartOpModeDistribution` | **9** | **yes** |
| `OperatingModeDistributionGenerator` | 0 / 42 | `OpModeDistribution` | 0 (empty in all 42) | no |
| `LinkOperatingModeDistributionGenerator` | 0 / 42 | `OpModeDistribution` | 0 (empty in all 42) | no |
| `MesoscaleLookupOperatingModeDistributionGenerator` | 0 / 42 | `OpModeDistribution` | 0 (empty in all 42) | no |
| `MesoscaleLookupTotalActivityGenerator` | 0 / 42 | `SourceHours`, `SHO` | — | no |
| `NewTvvYearGenerator` | 0 / 42 | — | — | no |

`FuelEffectsGenerator` (24 / 42) is the eighth unported generator and belongs to
a parallel rung; it is listed here only so the eight add up.

### Which snapshots, exactly

`RatesOpModeDistribution` is non-empty in 14 snapshots:

| snapshot | rows | | snapshot | rows |
|---|---:|---|---|---:|
| `expand-counties` | 9 | | `process-apu` | 3 |
| `expand-criteria` | 33 | | `process-apu-single` | 3 |
| `expand-day` | 18 | | `process-extended-idle` | 1 |
| `expand-fueltype-diesel` | 18 | | `process-extended-idle-single` | 1 |
| `expand-month` | 9 | | `process-refueling` | 9 |
| `expand-sourcetype` | 46 | | `process-tirewear` | 16 |
| `mixed-onroad` | 9 | | `sample-runspec` | 9 |

`StartOpModeDistribution` is non-empty in 9, and they are **exactly** the 9 in
which `StartOperatingModeDistributionGenerator` was class-loaded — set-equal,
not merely equinumerous:

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

**`RatesOperatingModeDistributionGenerator` is the case the brief warned about:
30 loaded, 14 with rows.** Loading it and running it are different events, and
half the loads produce nothing. Its subscription list (processes 1, 90 and 91)
is what decides which; process 1's contribution is delegated to the external
`SourceTypePhysics` generator, so this module's own live output is the
degenerate hotelling distribution for processes 90 and 91.

### Why the other five are unreachable, in their own terms

`calculator-dag.json` separates them from the reachable pair on a field that is
not about op modes at all — `subscriptions[*].source`:

* `RatesOperatingModeDistributionGenerator` and
  `StartOperatingModeDistributionGenerator` subscribe from
  **`CalculatorInfo`**, with real named processes (1/90/91 and 2). That is the
  registry MOVES's master loop reads, so any run selecting those processes
  loads them.
* `OperatingModeDistributionGenerator`, `LinkOperatingModeDistributionGenerator`
  and `MesoscaleLookup{OperatingModeDistribution,TotalActivity}Generator`
  subscribe from **`JavaSource`** with `process_id: 0` and the placeholder
  process names `brakeProcess` / `brakeWearProcess` — i.e. the DAG builder
  found a `subscribe()` call in the Java and could not resolve its process
  constant, because these classes are wired up by the **project-scale** and
  **mesoscale-lookup** domains rather than by `CalculatorInfo.txt`. No RunSpec
  in the corpus selects either domain, and `OpModeDistribution` is
  correspondingly empty — 0 rows — in all 42 snapshots.
* `NewTvvYearGenerator` is the sharpest case: its `java_path` in
  `calculator-dag.json` is the **empty string**. `CalculatorInfo.txt` names it
  against process 12, but the scan of the pinned MOVES source found no class by
  that name to attach it to. There is nothing to port from and nothing to check
  against.

Reaching any of the five needs a project-scale or mesoscale-lookup RunSpec
captured in `moves.rs` — the same shape of gap PLAN.md records for the five
live-but-unexercised calculators, and the same answer: it is `moves.rs` work,
not `.esm` work.

## What this leaves for the rung

Two of seven. `RatesOperatingModeDistributionGenerator` and
`StartOperatingModeDistributionGenerator` are both **execution-database**
generators, not `MOVESOutput` producers, so §35 governs them: they live in
`components/`, not in `fixtures/`, and their specification borrows an existing
fixture's snapshot for the coverage tool's fixture leg — exactly as
`docs/meteorology-generator.md` borrows `process-pm-exhaust`.

`mixed-onroad` is the snapshot that carries **both** tables non-empty and
already has a fixture (`fixtures/mixed-onroad.esm`), so it is the one the
specification names.
