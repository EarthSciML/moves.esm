#!/usr/bin/env python3
"""Write the transient probe documents run-tests.sh's 7c stage needs.

Each probe is a mechanical edit of `spikes/7c/tirewear_mount.esm` or
`spikes/7c/tirewear_logic.esm`, written to a hidden file that the stage deletes
after running it. They are generated rather than checked in for the reason
`tools/make-index-set-probe.py` gives: a probe is defined by its DIFFERENCE
from the real document, and a checked-in copy would drift away from the thing
it is supposed to differ from by one field.

The probes, and what each one watches:

  f46-loud    the mount with its `index_sets` deleted. Must FAIL `esm validate`
              -- because the logic document declares one LITERAL-sized index
              set (`run_rows`, size 1), which is what stops the whole block
              from reaching the validator (finding F48).

  f46-silent  the same deletion, with `run_rows` re-expressed as a
              metaparameter so that every size in the child is a name. Must
              PASS `esm validate` and FAIL the build -- F46's original
              behaviour, and the reason the restatement is load-bearing.

  rename      the mount with every axis renamed at the mount edge by
              `index_set_rename`. Must be REFUSED as
              `subsystem_index_set_rename_unsupported_mount_form` (F49).

  bindings    the 45 metaparameters the child does not read in an equation,
              closed at the mount edge by `bindings` instead of by name. Must
              still validate: it is the two-sided half of the measurement that
              `bindings` works at scale and buys nothing (conventions 54).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGIC = os.path.join(ROOT, "spikes", "7c", "tirewear_logic.esm")
MOUNT = os.path.join(ROOT, "spikes", "7c", "tirewear_mount.esm")


def rewrite_size(size, ren):
    """Rename metaparameters inside an index-set size, literal or expression."""
    if isinstance(size, str):
        return ren.get(size, size)
    if isinstance(size, dict):
        return {k: ([rewrite_size(a, ren) for a in v] if k == "args" else v)
                for k, v in size.items()}
    return size


def main(which, out_path):
    logic = json.load(open(LOGIC))
    mount = json.load(open(MOUNT))
    child_path = None

    if which == "f46-loud":
        del mount["index_sets"]

    elif which == "f46-silent":
        literal = [k for k, v in logic["index_sets"].items()
                   if not isinstance(v["size"], (str, dict))]
        if not literal:
            sys.exit("f46-silent: the logic document no longer declares a "
                     "literal-sized index set, so F48's precondition is gone")
        for k in literal:
            logic["index_sets"][k] = {"kind": "interval", "size": "n_probe_" + k}
            mount["metaparameters"]["n_probe_" + k] = {
                "type": "integer", "default": 1, "description": "7c probe",
            }
        del mount["index_sets"]
        child_path = out_path.replace(".esm", "_child.esm")
        json.dump(logic, open(child_path, "w"), indent=2)
        mount["models"]["ProcessTirewear"]["ref"] = "./" + os.path.basename(child_path)

    elif which == "rename":
        ren = {k: "tw_" + k for k in mount["index_sets"]}
        mount["index_sets"] = {ren[k]: v for k, v in mount["index_sets"].items()}
        mount["models"]["ProcessTirewear"] = {
            "ref": "./tirewear_logic.esm", "index_set_rename": dict(ren),
        }

    elif which == "bindings":
        equations = json.dumps(logic["models"]["ProcessTirewear"]["equations"])
        # a metaparameter closed by `bindings` is not readable in an equation
        # (conventions 49.2), so the ones the child READS keep their own names
        read = {n for n in mount["metaparameters"] if '"%s"' % n in equations}
        ren = {k: ("p_" + k if k not in read else k) for k in mount["metaparameters"]}
        mount["index_sets"] = {k: dict(v, size=rewrite_size(v["size"], ren))
                               for k, v in mount["index_sets"].items()}
        mount["metaparameters"] = {ren[k]: v for k, v in mount["metaparameters"].items()}
        for entry in mount["data_sources"].values():
            if "extent" in entry:
                entry["extent"]["metaparameter"] = ren[entry["extent"]["metaparameter"]]
        mount["models"]["ProcessTirewear"] = {
            "ref": "./tirewear_logic.esm",
            "bindings": {k: v for k, v in ren.items() if k != v},
        }

    else:
        sys.exit("unknown probe: " + which)

    json.dump(mount, open(out_path, "w"), indent=2)
    print(child_path or "")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: make-7c-probes.py <f46-loud|f46-silent|rename|bindings> <out.esm>")
    main(sys.argv[1], sys.argv[2])
