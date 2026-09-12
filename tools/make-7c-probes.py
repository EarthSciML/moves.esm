#!/usr/bin/env python3
"""Write the transient probe documents run-tests.sh's 7c stage needs.

Each probe is a mechanical edit of `spikes/7c/tirewear_mount.esm` or
`spikes/7c/tirewear_logic.esm`, written to a hidden file that the stage deletes
after running it. They are generated rather than checked in for the reason
`tools/make-index-set-probe.py` gives: a probe is defined by its DIFFERENCE
from the real document, and a checked-in copy would drift away from the thing
it is supposed to differ from by one field.

The split these probes edit is `leaf-owns-shape`, which EarthSciAST PR #298 made the
conforming one: the LOGIC half declares the metaparameters and the index sets,
the MOUNT declares the data_sources. Three probes here watched F46, F48 and
F49, all of which #298 closed, and they are gone; what is left is F50 and the
two capabilities Phase 7 now plans on.

  no-root-metaparameters
              the mount with its `metaparameters` deleted. Must PASS
              `esm validate` and FAIL the build with
              `template_import_unknown_name` -- finding F50, that the root
              document must declare every metaparameter an `extent` binds even
              though the document owning the axes declares them too.

  bindings-carries-the-names
              F50's obvious workaround, and the measurement that it is not
              available: the mount declares the 49, the LEAF does not, and the
              edge binds each name to itself. Must be REFUSED at load, because
              `bindings` is checked against what the REFERENCED document
              declares, not against what the mount offers.

  rename      the mount with every axis renamed at the mount edge by
              `index_set_rename`. This was F49, refused with
              `subsystem_index_set_rename_unsupported_mount_form`; since #298
              it is accepted, so the stage runs it and compares BYTES. It is
              what would let a shared domain document's axes be namespaced per
              fixture.

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


def main(which, out_path):
    logic = json.load(open(LOGIC))
    mount = json.load(open(MOUNT))
    child_path = None

    if which == "no-root-metaparameters":
        del mount["metaparameters"]

    elif which == "bindings-carries-the-names":
        # The leaf keeps its axes and loses the names that size them; the mount
        # keeps the names and offers them at the edge. If `bindings` closed a
        # size the way it closes a metaparameter the leaf declares, this would
        # be F50's fix and would cost one line per name instead of a block.
        names = list(mount["metaparameters"])
        del logic["metaparameters"]
        child_path = out_path.replace(".esm", "_child.esm")
        json.dump(logic, open(child_path, "w"), indent=2)
        mount["models"]["ProcessTirewear"] = {
            "ref": "./" + os.path.basename(child_path),
            "bindings": {n: n for n in names},
        }

    elif which == "rename":
        # Every axis lives in the LEAF now, so the rename is read from there.
        ren = {k: "tw_" + k for k in logic["index_sets"]}
        mount["models"]["ProcessTirewear"] = {
            "ref": "./tirewear_logic.esm", "index_set_rename": dict(ren),
        }

    elif which == "bindings":
        equations = json.dumps(logic["models"]["ProcessTirewear"]["equations"])
        # a metaparameter closed by `bindings` is not readable in an equation
        # (conventions 49.2), so the ones the child READS keep their own names
        read = {n for n in mount["metaparameters"] if '"%s"' % n in equations}
        ren = {k: ("p_" + k if k not in read else k) for k in mount["metaparameters"]}
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
        sys.exit("usage: make-7c-probes.py "
                 "<no-root-metaparameters|bindings-carries-the-names|rename|bindings> "
                 "<out.esm>")
    main(sys.argv[1], sys.argv[2])
