#!/usr/bin/env python3
"""Write the transient probe documents run-tests.sh's 7c stage needs.

Each probe is a mechanical edit of `spikes/7c/tirewear_mount.esm` or
`spikes/7c/tirewear_logic.esm`, written to a hidden file that the stage deletes
after running it. They are generated rather than checked in for the reason
`tools/make-index-set-probe.py` gives: a probe is defined by its DIFFERENCE
from the real document, and a checked-in copy would drift away from the thing
it is supposed to differ from by one field.

The split these probes edit is `leaf-owns-shape`: the LOGIC half declares the
metaparameters and the index sets, the MOUNT declares the data_sources and no
metaparameters at all. The mount used to carry a second copy of the 49, and a
probe here deleted it and required the build to refuse the result -- finding
F50. EarthSciAST PR #317 fixed that, the copy is gone from the real document,
and so is the probe. What is left is one limit and the two capabilities Phase 7
plans on.

  bindings-carries-the-names
              The limit. The mount declares the extent names and binds each to
              itself at the edge; the LEAF declares none. Must be REFUSED at
              load with `template_import_unknown_name`, because `bindings` is
              checked against what the REFERENCED document declares: it closes
              a name the leaf has and cannot supply one it lacks. #317 made the
              duplication this used to be the workaround for unnecessary, so
              nothing depends on it any more -- it pins conventions §49.1.

  rename      the mount with every axis renamed at the mount edge by
              `index_set_rename`. This was F49, refused with
              `subsystem_index_set_rename_unsupported_mount_form`; since #298
              it is accepted, so the stage runs it and compares BYTES. It is
              what would let a shared domain document's axes be namespaced per
              fixture.

  bindings    the 45 extent metaparameters the child does not read in an
              equation, declared by the mount under `p_` names and closed at
              the mount edge by `bindings`. Must still emit the same bytes: it
              is the two-sided half of the measurement that `bindings` works at
              scale and buys nothing (conventions 54).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGIC = os.path.join(ROOT, "spikes", "7c", "tirewear_logic.esm")
MOUNT = os.path.join(ROOT, "spikes", "7c", "tirewear_mount.esm")


def extent_names(mount):
    return sorted({entry["extent"]["metaparameter"]
                   for entry in mount["data_sources"].values() if "extent" in entry})


def main(which, out_path):
    logic = json.load(open(LOGIC))
    mount = json.load(open(MOUNT))
    child_path = None

    if which == "bindings-carries-the-names":
        # The leaf keeps its axes and loses the names that size them; the mount
        # declares the names and offers them at the edge. If `bindings` could
        # supply a name the leaf lacks, this would load.
        names = extent_names(mount)
        mount["metaparameters"] = {n: logic["metaparameters"][n] for n in names}
        del logic["metaparameters"]
        child_path = out_path.replace(".esm", "_child.esm")
        json.dump(logic, open(child_path, "w"), indent=2)
        mount["models"]["ProcessTirewear"] = {
            "ref": "./" + os.path.basename(child_path),
            "bindings": {n: n for n in names},
        }

    elif which == "rename":
        # Every axis lives in the LEAF, so the rename is read from there.
        ren = {k: "tw_" + k for k in logic["index_sets"]}
        mount["models"]["ProcessTirewear"] = {
            "ref": "./tirewear_logic.esm", "index_set_rename": dict(ren),
        }

    elif which == "bindings":
        equations = json.dumps(logic["models"]["ProcessTirewear"]["equations"])
        # a metaparameter closed by `bindings` is not readable in an equation
        # (conventions 49.2), so the ones the child READS keep their own names
        # and stay declared by the leaf alone
        names = extent_names(mount)
        read = {n for n in names if '"%s"' % n in equations}
        ren = {k: ("p_" + k if k not in read else k) for k in names}
        mount["metaparameters"] = {ren[k]: logic["metaparameters"][k]
                                   for k in names if ren[k] != k}
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
        sys.exit("usage: make-7c-probes.py "
                 "<bindings-carries-the-names|rename|bindings> <out.esm>")
    main(sys.argv[1], sys.argv[2])
