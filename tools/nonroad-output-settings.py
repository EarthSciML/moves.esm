#!/usr/bin/env python3
"""A NONROAD RunSpec's output settings, as the one-row table the model reads.

MOVES writes a RunSpec's `<outputemissionsbreakdownselection>`,
`<geographicoutputdetail>` and `<outputfactors>` nowhere in the execution
database: AggregationSQLGenerator reads them from the RunSpec object when it
builds the GROUP BY that turns MOVESWorkerOutput into MOVESOutput. So the model
reads them from a per-run declared table, `db_runspecoutputsettings`
(docs/esm-conventions.md §132, §137), which `moves-nonroad.esm` mounts EMPTY --
the settings `nonroad/model.esm` emits -- and a RunSpec document whose RunSpec
departs from them declares itself, from the file this script writes.
`nonroad/model.esm`'s `run_outputSettingUnported` counts every departure, and
`tools/check-sources.py` (check 10) fails a document whose declaration is not
its RunSpec's.

Columns (one row; a flag is 1 when the element's `selected` is "true"):

  modelYear, fuelType, emissionProcess, onRoadSCC   grouped by when 1, summed
      away (written NULL) when 0 -- AggregationSQLGenerator.java:1260-1340, :1394
  sourceUseType, sector, engTechID, hpClass         grouped by when 1, NULL when
      0 -- :1353, :1418-1470 (the NONROAD loader fills sourceTypeID, engTechID,
      sectorID and hpID on every worker row, NonroadOutputDataLoader.java:395-403)
  geographicOutputDetail   the level's position in GeographicOutputDetailLevel.java's
      declaration order: NATION 0, STATE 1, COUNTY 2, ZONE 3, ROADTYPE 4, LINK 5
  kilogramsPerMassUnit     MassMeasurementSystem.java's conversionToKilogramsFactor
      of `<massfactors units>`: Grams 0.001, Kilograms 1, Pounds 0.453592,
      U.S. Ton 907.184818

Elements AggregationSQLGenerator does not read for a NONROAD row are not
columns: `fuelsubtype` and `regclassid` group a column the NONROAD loader leaves
NULL; `roadtype` only blanks roadTypeID (100 on every NONROAD row), which the
model does not emit; `onroadoffroad`, `movesvehicletype`,
`distinguishparticulates` and `offroadscc` are read by nothing
(RunSpecXML.java:1197 says so of `offroadscc`). `<outputtimestep>` is not read
either: "no time aggregation should be done for Nonroad" (:1496).

    nonroad-output-settings.py <runspec.xml>                 print the row
    nonroad-output-settings.py <runspec.xml> --write <out.parquet>
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

FLAGS = {  # column: the XML element(s) RunSpecXML.java:1169-1218 reads it from
    "modelYear": ("modelyear",),
    "fuelType": ("fueltype",),
    "emissionProcess": ("emissionprocess",),
    "onRoadSCC": ("onroadscc",),
    "sourceUseType": ("sourceusetype",),
    "sector": ("sector", "segment"),
    "engTechID": ("engtechid",),
    "hpClass": ("hpclass",),
}
LEVELS = ["NATION", "STATE", "COUNTY", "ZONE", "ROADTYPE", "LINK"]
KG_PER_UNIT = {"Kilograms": 1.0, "Grams": 0.001, "Pounds": 0.453592, "U.S. Ton": 907.184818}

# What the model emits: (SCC, model year, fuel type, process) rows with
# sourceTypeID, sectorID, engTechID and hpID NULL, in grams, at the run's own
# scale (`out_*` in nonroad/model.esm).
MODEL = {"modelYear": 1, "fuelType": 1, "emissionProcess": 1, "onRoadSCC": 1,
         "sourceUseType": 0, "sector": 0, "engTechID": 0, "hpClass": 0,
         "kilogramsPerMassUnit": 0.001}
SCALE_LEVEL = {"NATION": 0, "STATE": 1, "COUNTY": 2}


def settings(xml_path) -> dict:
    root = ET.parse(xml_path).getroot()
    row = {}
    sel = root.find("outputemissionsbreakdownselection")
    for col, tags in FLAGS.items():
        row[col] = 0
        for node in (sel if sel is not None else []):
            if node.tag.lower() in tags:
                row[col] = 1 if (node.get("selected") or "").strip().lower() == "true" else 0
    geo = root.find("geographicoutputdetail")
    row["geographicOutputDetail"] = LEVELS.index((geo.get("description") or "").strip().upper())
    mass = root.find("outputfactors/massfactors")
    row["kilogramsPerMassUnit"] = KG_PER_UNIT[(mass.get("units") or "").strip()]
    return row


def run_level(xml_path) -> int:
    """The level the model emits: the RunSpec's own geographic selection's."""
    root = ET.parse(xml_path).getroot()
    kinds = {(g.get("type") or "").strip().upper() for g in root.find("geographicselections")}
    if len(kinds) != 1 or not kinds <= set(SCALE_LEVEL):
        return -1
    return SCALE_LEVEL[kinds.pop()]


def departures(xml_path) -> list[str]:
    """The settings of a RunSpec the model does not emit; [] for every verified run."""
    row = settings(xml_path)
    out = [c for c, v in MODEL.items() if row[c] != v]
    if row["geographicOutputDetail"] != run_level(xml_path):
        out.append("geographicOutputDetail")
    return out


def write(row: dict, path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    cols = {c: pa.array([float(row[c])], pa.float64()) for c in
            list(FLAGS) + ["geographicOutputDetail", "kilogramsPerMassUnit"]}
    pq.write_table(pa.table(cols), path)


def write_empty(path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    cols = {c: pa.array([], pa.float64()) for c in
            list(FLAGS) + ["geographicOutputDetail", "kilogramsPerMassUnit"]}
    pq.write_table(pa.table(cols), path)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        print(settings(sys.argv[1]), "departures:", departures(sys.argv[1]))
    elif len(sys.argv) == 4 and sys.argv[2] == "--write":
        write(settings(sys.argv[1]), sys.argv[3])
    else:
        sys.exit(__doc__)
