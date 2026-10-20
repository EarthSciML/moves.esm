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

  no-county-join          the output relation's county key pair, against
                          `runspecs/expand-counties.esm`. The output relation is
                          pollutant-process major, then COUNTY, then day type,
                          then cohort; without the pair that selects the county
                          every output row sums all three of them, which is
                          7c''s `link` defect one axis up -- `out_countyID` comes
                          back 49229, the sum of the three county ids.

  no-source-type-join     the source-type key pair, against
                          `runspecs/pending/expand-fueltype-diesel.esm` -- so it
                          is WRITTEN AND NOT WIRED IN: a probe needs a run that
                          reproduces, and that one waits on the source bin
                          (PLAN.md 7.3.5). It is here rather than in a commit
                          message because it is the probe that step will use,
                          and `main` below will run it by hand. The drive
                          cycle, the activity relation and the run's VMT are
                          computed once per source type; the rate row and the
                          output row say WHICH one with a key pair against
                          `rst_ordinal`. Without the pairs every row sums both
                          source types, which is `no-county-join` one dimension
                          over -- a passenger car is charged a light commercial
                          truck's activity as well as its own.

  no-road-type-filter     `rspp_rateRoadTypeID`'s off-network arm, against
                          `runspecs/expand-day.esm`. Start exhaust and extended
                          idle write their rates on road type 1;
                          `BaseRateCalculator` joins to `runSpecRoadType`; so a
                          run that selects road type 4 emits the running-exhaust
                          block alone. Without the arm every selected
                          pollutant-process claims an output block and the three
                          collide in the one that exists.

ONE FILE PER DOCUMENT OF THE CHAIN, because each carries relative paths that
have to keep resolving: the model beside its original (its
`expression_template_imports`), every document between the per-fixture one and
the model beside ITS original -- since step 7f that is two, the run's domain
document (`moves-onroad.esm` at the root, or a scale-input database's in
`inputs/`) and `onroad/default-database.esm`, which names `../movesdb/` -- and
the per-fixture document beside its original (its snapshot URLs). The chain is
walked from the per-fixture document's `ref` rather than named here, so a run
that mounts a different domain document is probed through its own. They are generated rather than checked in for the reason
`tools/make-index-set-probe.py` gives: a probe is defined by its DIFFERENCE from
the real document, and a checked-in copy drifts from the thing it differs from.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGIC = os.path.join(ROOT, "onroad", "model.esm")

LINK_EQUATIONS = ("run_linkID", "run_countyID", "run_zoneID", "run_linkRoadTypeID")


def no_link_join(logic, fixture):
    dropped = 0
    for eq in logic["models"]["Onroad"]["equations"]:
        if eq["lhs"] in LINK_EQUATIONS:
            rhs = eq["rhs"]
            assert rhs["join"][0]["on"][0] == ["lnk_countyID", "rsc_countyID"], eq["lhs"]
            del rhs["join"]
            del rhs["ranges"]["w"]
            dropped += 1
    if dropped != len(LINK_EQUATIONS):
        sys.exit("expected %d link equations, edited %d" % (len(LINK_EQUATIONS), dropped))
    # The county range `c` and `rsc_countyID` STAY. Until 2026-10-19 this probe
    # deleted both, which left the four equations an output index with no range
    # and every other join on the county id -- the barometric pressure's, and
    # since step 7f the project link's -- unresolvable, so the probe document
    # did not compile and "moved" the run by not evaluating it (PLAN.md
    # §7.3.40). Without the join each county's row sums the national table,
    # which is the defect the probe exists to show.


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


def no_county_join(logic, fixture):
    pair = ["outCountyOrdinal", "rsc_ordinal"]
    dropped = 0
    for eq in logic["models"]["Onroad"]["equations"]:
        rhs = eq["rhs"]
        if not isinstance(rhs, dict) or "join" not in rhs:
            continue
        for clause in list(rhs["join"]):
            if pair in clause["on"]:
                clause["on"].remove(pair)
                dropped += 1
                if not clause["on"]:
                    # the three identity columns joined on nothing else, so the
                    # whole clause goes -- which is the shape they had before
                    # the county was an axis.
                    rhs["join"].remove(clause)
                    if not rhs["join"]:
                        del rhs["join"]
    # 10 since step 7f: `out_zoneID` and `out_linkID` select their county the
    # same way, for a PROJECT run's link-level geography (PLAN.md §7.3.40).
    if dropped != 10:
        sys.exit("expected 10 county key pairs, dropped %d" % dropped)


def no_source_type_join(logic, fixture):
    pairs = (["rt_sourceTypeOrdinal", "rst_ordinal"],
             ["outSourceTypeOrdinal", "rst_ordinal"])
    dropped = 0
    for eq in logic["models"]["Onroad"]["equations"]:
        rhs = eq["rhs"]
        if not isinstance(rhs, dict) or "join" not in rhs:
            continue
        for clause in list(rhs["join"]):
            for pair in pairs:
                if pair in clause["on"]:
                    clause["on"].remove(pair)
                    dropped += 1
                    if not clause["on"]:
                        rhs["join"].remove(clause)
                        if not rhs["join"]:
                            del rhs["join"]
    if dropped != 5:
        sys.exit("expected 5 source-type key pairs, dropped %d" % dropped)


PROBES = {"no-link-join": no_link_join,
          "no-source-type-join": no_source_type_join,
          "no-road-type-filter": no_road_type_filter,
          "no-county-join": no_county_join}


def main(which, runspec, out_path):
    logic = json.load(open(LOGIC))
    # A runspec lives in `runspecs/` or, if its model work is not finished, in
    # `runspecs/pending/`. The probe is written beside whichever one it copies,
    # so the snapshot URLs keep resolving.
    for rel in ("runspecs", os.path.join("runspecs", "pending")):
        candidate = os.path.join(ROOT, rel, runspec + ".esm")
        if os.path.exists(candidate):
            break
    else:
        sys.exit("no such runspec: %s" % runspec)
    fixture = json.load(open(candidate))

    PROBES[which](logic, fixture)

    base = os.path.basename(out_path).lstrip(".").replace(".esm", "")
    logic_path = os.path.join(ROOT, "onroad", ".%s_logic.esm" % base)
    json.dump(logic, open(logic_path, "w"), indent=2)
    written = [logic_path]

    # The documents between the fixture and the model, outermost first.
    chain = []
    here = os.path.abspath(candidate)
    doc = fixture
    while True:
        ref = os.path.normpath(os.path.join(os.path.dirname(here), doc["models"]["Onroad"]["ref"]))
        if ref == os.path.abspath(LOGIC):
            break
        here = ref
        doc = json.load(open(ref))
        chain.append((ref, doc))
    # Innermost first, so each copy's ref can name the copy below it. Re-point
    # the ref and NOTHING else: a `bindings` block dropped here would silently
    # reshape the probe's output and the comparison would report the wrong
    # difference.
    below = logic_path
    for i, (orig, doc) in reversed(list(enumerate(chain))):
        copy = os.path.join(os.path.dirname(orig), ".%s_chain%d.esm" % (base, i))
        doc["models"]["Onroad"]["ref"] = os.path.relpath(below, os.path.dirname(copy))
        json.dump(doc, open(copy, "w"), indent=2)
        written.append(copy)
        below = copy
    fixture["models"]["Onroad"]["ref"] = os.path.relpath(below, os.path.dirname(os.path.abspath(out_path)))
    json.dump(fixture, open(out_path, "w"), indent=2)
    for path in written:
        print(path)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in PROBES:
        sys.exit("usage: make-runspec-probe.py <%s> <runspec> <out.esm>"
                 % "|".join(PROBES))
    main(sys.argv[1], sys.argv[2], sys.argv[3])
