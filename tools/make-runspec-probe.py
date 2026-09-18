#!/usr/bin/env python3
"""Write the transient probe documents the `runspecs/` stage needs: the same
default-database chain with ONE selection removed, and a requirement that the
numbers MOVE.

An execution-database table arrives pre-narrowed, so a document written against
one can read a column where it meant to join and nothing says so (PLAN.md
§7.3.3, docs/esm-conventions.md §59). Each probe here deletes a narrowing the
default database made necessary and re-runs the chain; if the emitted relation
is unchanged, that narrowing has stopped being what narrows and the suite says
so.

  no-link-join            `link`'s county/road-type join, against
                          `runspecs/process-tirewear.esm`. The execution copy of
                          `Link` has one row, so the four run-level geography
                          columns SUMMED it and summing one row is reading it.
                          The national table has 22,610 and the sum reads county
                          710047702.

  no-road-type-filter     `rspp_rateRoadTypeID`'s off-network arm, against
                          `runspecs/expand-day.esm`. Start exhaust and extended
                          idle write their rates on road type 1;
                          `BaseRateCalculator` joins to `runSpecRoadType`; so a
                          run that selects road type 4 emits the running-exhaust
                          block alone. Without the arm every selected
                          pollutant-process claims an output block and the three
                          collide in the one that exists.

THREE FILES PER PROBE, because the chain is three documents and each carries
relative paths that have to keep resolving: the model beside its original (its
`expression_template_imports`), the domain document at the repo root (it names
`./movesdb/`) and the per-fixture document beside its original (its snapshot
URLs). They are generated rather than checked in for the reason
`tools/make-index-set-probe.py` gives: a probe is defined by its DIFFERENCE from
the real document, and a checked-in copy drifts from the thing it differs from.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGIC = os.path.join(ROOT, "onroad", "model.esm")
DOMAIN = os.path.join(ROOT, "moves-onroad.esm")

LINK_EQUATIONS = ("run_linkID", "run_countyID", "run_zoneID", "run_linkRoadTypeID")


def no_link_join(logic, fixture):
    dropped = 0
    for eq in logic["models"]["Onroad"]["equations"]:
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
    del logic["models"]["Onroad"]["variables"]["rsc_countyID"]
    del fixture["data_sources"]["db_runspeccounty"]


def no_road_type_filter(logic, fixture):
    for eq in logic["models"]["Onroad"]["equations"]:
        if eq["lhs"] == "rspp_rateRoadTypeID":
            rhs = eq["rhs"]
            assert rhs["expr"]["op"] == "ifelse", rhs["expr"]["op"]
            # the `then` arm alone: every pollutant-process's rates on the run's
            # own road type, which is what the model assumed before 7d.
            rhs["expr"] = rhs["expr"]["args"][1]
            return
    sys.exit("rspp_rateRoadTypeID not found")


PROBES = {"no-link-join": no_link_join,
          "no-road-type-filter": no_road_type_filter}


def main(which, runspec, out_path):
    logic = json.load(open(LOGIC))
    domain = json.load(open(DOMAIN))
    fixture = json.load(open(os.path.join(ROOT, "runspecs", runspec + ".esm")))

    PROBES[which](logic, fixture)

    base = os.path.basename(out_path)
    logic_path = os.path.join(ROOT, "onroad", "." + base.lstrip(".").replace(".esm", "_logic.esm"))
    domain_path = os.path.join(ROOT, "." + base.lstrip(".").replace(".esm", "_domain.esm"))

    json.dump(logic, open(logic_path, "w"), indent=2)
    # Re-point the ref and NOTHING else: a `bindings` block dropped here would
    # silently reshape the probe's output and the comparison would report the
    # wrong difference.
    domain["models"]["Onroad"]["ref"] = "./onroad/" + os.path.basename(logic_path)
    json.dump(domain, open(domain_path, "w"), indent=2)
    fixture["models"]["Onroad"]["ref"] = "../" + os.path.basename(domain_path)
    json.dump(fixture, open(out_path, "w"), indent=2)
    print(logic_path)
    print(domain_path)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in PROBES:
        sys.exit("usage: make-runspec-probe.py <%s> <runspec> <out.esm>"
                 % "|".join(PROBES))
    main(sys.argv[1], sys.argv[2], sys.argv[3])
