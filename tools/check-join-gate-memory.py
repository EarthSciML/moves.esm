#!/usr/bin/env python3
"""Gate F58 (EarthSciML/EarthSciAST#418) on a RATIO rather than on an absolute.

A join-gated `faq` retains ~80 bytes of resident memory per candidate join pair,
in a thread-local cache that never evicts, so peak memory tracks the join's
match set rather than the arrays the document declares or the answer it
produces. `docs/findings/F58_a_join_gate_retains_its_match_set.esm` is the
minimal case, and it PASSES -- the answer is right and only its cost is wrong --
so it cannot be a tripwire in the ordinary way: `run-tests.sh` reads a passing
file in `docs/findings/` as "the defect is fixed" and excludes this one by name.

So this measures it instead. Two runs of the same document differing in ONE
metaparameter:

    n_key = 1000   ->  1,000,000 candidate pairs
    n_key =  100   -> 10,000,000 candidate pairs

Everything else is identical -- the same 1,000,000-row fact table, the same
16 MB of declared arrays, the same 0.03 MB answer, the same work per pair. Only
the match set is ten times bigger. Today the peak grows with it, about 3.5x.

A RATIO and not a threshold, because an absolute number would mean different
things on different machines and would have to be re-tuned every time the
corpus or the allocator moved; the ratio is a property of the evaluator. It is
also two-sided, which is what makes it a finding gate and not a benchmark:

  * ratio >= MIN_RATIO -- F58 still holds, report it and pass.
  * ratio <  MIN_RATIO -- the peak has stopped tracking the match set. That is
    the fix landing, and the finding should be retired: #418 closed, the F58
    section moved to the retired end of docs/findings/README.md, this gate and
    the `-not -name` exclusion in run-tests.sh deleted.

MIN_RATIO is 2.0 against a measured 3.5 because the failing side must be
unambiguous: a fix takes the ratio to roughly 1.1, so anything at or above 2
is the defect and nothing in between is reported as either.

usage: check-join-gate-memory.py <esm-binary> <finding.esm> <scratch-dir>
"""
import json
import os
import re
import resource
import subprocess
import sys

MIN_RATIO = 2.0
FANOUTS = (1000, 100)


def peak_rss_bytes(esm, doc, out):
    """Run one evaluation and return the child's peak RSS in bytes."""
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    r = subprocess.run([esm, "simulate", doc, "--time", "0", "--format", "csv",
                        "--observed", "total", "--output", out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode != 0:
        tail = r.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise RuntimeError("%s did not evaluate: %s" % (doc, " / ".join(tail)))
    after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # ru_maxrss is the MAXIMUM over all reaped children, so it only ever rises;
    # a run smaller than one already reaped would read as that earlier peak.
    # The caller orders the runs small-to-large so each `after` is this run's.
    if after <= before:
        raise RuntimeError("peak RSS did not rise on %s; runs are out of order"
                           % doc)
    return after * 1024  # Linux reports kilobytes


def variant(src, dst, n_key):
    with open(src) as f:
        doc = json.load(f)
    doc["metaparameters"]["n_key"]["default"] = n_key
    with open(dst, "w") as f:
        f.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    mp = doc["metaparameters"]
    pairs = mp["n_out"]["default"] * (mp["n_big"]["default"] // n_key)
    return pairs


def main(esm, finding, scratch):
    os.makedirs(scratch, exist_ok=True)
    seen = []
    for n_key in FANOUTS:                      # ascending peak, see peak_rss_bytes
        doc = os.path.join(scratch, "f58_key%d.esm" % n_key)
        pairs = variant(finding, doc, n_key)
        rss = peak_rss_bytes(esm, doc, os.path.join(scratch, "f58.csv"))
        seen.append((n_key, pairs, rss))
        os.remove(doc)

    (_, p_lo, r_lo), (_, p_hi, r_hi) = seen
    ratio = r_hi / r_lo
    for n_key, pairs, rss in seen:
        print("  n_key=%-5d %12s candidate pairs   peak %.2f GB   %.0f bytes/pair"
              % (n_key, "{:,}".format(pairs), rss / 2**30, rss / pairs))
    print("  %.1fx the pairs, %.2fx the peak" % (p_hi / p_lo, ratio))

    if ratio >= MIN_RATIO:
        print("F58 still holds: peak memory tracks the join's match set "
              "(EarthSciML/EarthSciAST#418)")
        return 0
    print("F58 LOOKS FIXED: ten times the candidate pairs moved the peak only "
          "%.2fx, under the %.1fx this gate calls the defect. Retire the "
          "finding -- close #418, move its section to the retired end of "
          "docs/findings/README.md, and delete this gate and the `-not -name` "
          "exclusion in run-tests.sh." % (ratio, MIN_RATIO))
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("usage: check-join-gate-memory.py <esm-binary> <finding.esm> "
                 "<scratch-dir>")
    try:
        sys.exit(main(*sys.argv[1:4]))
    except RuntimeError as exc:
        print(exc)
        sys.exit(2)
