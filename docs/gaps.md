# What MOVES 5 does that moves.esm does not

Two audits, 2026-11-21, read against the MOVES 5.0.1 source (Java, Go, SQL, NONROAD
Fortran) and the moves.esm tree at `cc2897c`. Every claim carries a MOVES file:line
reference and the grep or file evidence on the moves.esm side.

- [gaps-onroad.md](gaps-onroad.md): onroad, plus everything general to a MOVES run
  (domains and scales, RunSpec output options, input databases, control strategies,
  Rates, activity output).
- [gaps-nonroad.md](gaps-nonroad.md): NONROAD (processes, pollutants, sectors and
  fuels, geography and time, adjustments, output, input databases).

**Scope.** The goal is MOVES's *capabilities*, not its form factor. The GUI, the
County and Project Data Managers, the importers' spreadsheet converters, the AVFT
tool, Fuel Wizard, Summary Reporter, batch and looping tools and the other Tools-menu
utilities are out of scope; where one of them computes something a run needs (a
post-processing script's arithmetic, say), the arithmetic is in scope and the tool is
not.

**Status vocabulary.** *Silent*: MOVES does it and moves.esm neither computes nor
counts it, so a run that asks for it gets a plausible wrong number. *Counted*: the
model refuses it in a `run_*Unported` variable (onroad) or a shape scalar
(nonroad), asserted 0 for every verified run. *Ported, unverified*: equations exist,
no capture checks them. The first job is that nothing stays silent; porting follows.

**Why the captures did not show these.** Every captured county database is a copy of
the default database at the run's keys (PLAN.md §7.3.45), and every NONROAD capture
selects running exhaust with empty input databases. A table the model never reads
gives the right answer on such a capture. A capture that checks a table must state it
DIFFERENTLY from the default.
