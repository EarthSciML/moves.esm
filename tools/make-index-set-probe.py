#!/usr/bin/env python3
"""Write the F2 control probe: `runs/micro_exhaust_run.esm` with one axis wrong.

`run-tests.sh` stage 6 uses this to check that a top-level `models` {ref} still
CONFLICT-CHECKS the index sets it merges. F2 was that the merge did not happen
at that edge; it is fixed (EarthSciAST `19f929981`, PR #208), the four
assemblies stopped restating their leaves' axes, and the harness rule that
compared the two copies was deleted. What remains to check is that the loader's
own check is live, and a check is only live if it can fail -- so the probe
restates `rate_rows` one larger than `components/deteriorated_emission_rate.esm`
declares it and the suite requires `subsystem_index_set_conflict`.

The size is read from the leaf rather than written here, so the probe stays
wrong-by-one if the leaf's row count ever changes.

This writes a TRANSIENT probe, not a model document: it is hidden, it is deleted
by the stage that made it, and nothing is authored from it (CLAUDE.md).
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSEMBLY = ROOT / "runs" / "micro_exhaust_run.esm"
LEAF = ROOT / "components" / "deteriorated_emission_rate.esm"
AXIS = "rate_rows"


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} OUTPUT.esm", file=sys.stderr)
        return 2
    doc = json.loads(ASSEMBLY.read_text(encoding="utf-8"))
    leaf = json.loads(LEAF.read_text(encoding="utf-8"))
    truth = leaf["index_sets"][AXIS]
    if doc.get("index_sets", {}).get(AXIS) is not None:
        print(f"{ASSEMBLY} restates {AXIS} again; the probe assumes it does not",
              file=sys.stderr)
        return 2
    doc.setdefault("index_sets", {})[AXIS] = dict(truth, size=truth["size"] + 1)
    pathlib.Path(sys.argv[1]).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
