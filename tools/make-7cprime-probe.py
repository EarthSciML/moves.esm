#!/usr/bin/env python3
"""Write the transient probe run-tests.sh's 7c' stage needs: the same
default-database chain with the LINK SELECTION REMOVED.

7c' exists because an execution-database table arrives pre-narrowed, so a
document can read a column where it meant to join and nothing says so. `link`
was the case that bit: the execution copy has one row, the four run-level
geography columns summed it, and the national `Link` has 22,610. The fix was to
join on the runspec's county and road type. This probe deletes that join and
requires the numbers to MOVE -- otherwise the join has stopped being what
narrows them and the fix has quietly stopped applying.

Three files, because the chain is three documents and each relative path has to
keep resolving: the logic beside its original (its `expression_template_imports`
are relative), the domain document at the repo root (it names `./movesdb/`), and
the fixture beside its original (its runspec paths are relative). They are
generated rather than checked in for the reason `tools/make-index-set-probe.py`
gives: a probe is defined by its DIFFERENCE from the real document.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGIC = os.path.join(ROOT, "spikes", "7c", "tirewear_logic.esm")
DOMAIN = os.path.join(ROOT, "moves-onroad.esm")
FIXTURE = os.path.join(ROOT, "spikes", "7c", "tirewear_default_db_fixture.esm")

LINK_EQUATIONS = ("run_linkID", "run_countyID", "run_zoneID", "run_linkRoadTypeID")


def main(out_path):
    logic = json.load(open(LOGIC))
    domain = json.load(open(DOMAIN))
    fixture = json.load(open(FIXTURE))

    dropped = 0
    for eq in logic["models"]["ProcessTirewear"]["equations"]:
        if eq["lhs"] in LINK_EQUATIONS:
            rhs = eq["rhs"]
            assert rhs["join"][0]["on"][0] == ["lnk_countyID", "rsc_countyID"], eq["lhs"]
            del rhs["join"]
            del rhs["ranges"]["c"]
            del rhs["ranges"]["w"]
            dropped += 1
    if dropped != len(LINK_EQUATIONS):
        sys.exit("expected %d link equations, edited %d" % (len(LINK_EQUATIONS), dropped))

    # rsc_countyID is now read by nothing, and an ingesting document may not
    # declare a source no variable reads -- so the probe drops the variable too,
    # which is exactly the state this document was in before 7c'.
    del logic["models"]["ProcessTirewear"]["variables"]["rsc_countyID"]

    base = os.path.basename(out_path)
    logic_path = os.path.join(ROOT, "spikes", "7c", "." + base.lstrip(".").replace(".esm", "_logic.esm"))
    domain_path = os.path.join(ROOT, "." + base.lstrip(".").replace(".esm", "_domain.esm"))

    json.dump(logic, open(logic_path, "w"), indent=2)
    domain["models"]["ProcessTirewear"] = {
        "ref": "./spikes/7c/" + os.path.basename(logic_path)}
    json.dump(domain, open(domain_path, "w"), indent=2)
    del fixture["data_sources"]["tw_runspeccounty"]
    fixture["models"]["ProcessTirewear"] = {
        "ref": "../../" + os.path.basename(domain_path)}
    json.dump(fixture, open(out_path, "w"), indent=2)
    print(logic_path)
    print(domain_path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: make-7cprime-probe.py <out.esm>")
    main(sys.argv[1])
