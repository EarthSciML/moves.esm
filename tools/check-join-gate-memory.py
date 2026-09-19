#!/usr/bin/env python3
"""Hold the F58 FIX (EarthSciML/EarthSciAST#418) in place, in bytes per pair.

A join-gated `faq` used to retain ~80 bytes of resident memory per candidate
join pair, in a thread-local cache that never evicted, so peak memory tracked
the join's match set rather than the arrays a document declares. PR #420 held
the index's pairs once instead of four times and gave both gate caches a
resident-pair budget; PR #423 made a gate PRICED before it is built, so one
that would materialise more pairs than the tuples it could prune is declined.
Both merged 2026-09-19.

THIS NOW GUARDS THE FIX RATHER THAN THE DEFECT, which is why the document
beside it is named `F58_control_*` and not `F58_*`. It measures the marginal
cost of a candidate pair -- two runs of the same document differing in ONE
metaparameter, the same 1,000,000-row fact table and the same 0.03 MB answer,
ten times the match set:

    n_key = 1000   ->  1,000,000 candidate pairs
    n_key =  100   -> 10,000,000 candidate pairs

79 bytes a pair before the fix, 34 after, and the gate fails above 50.

IT IS THE MARGINAL CONSTANT AND NOT A RATIO, and that was a correction the fix
itself forced. This first tested whether the peak still SCALED with the match
set, on the reasoning that a fix would decouple them. It does not: #420 and
#423 together cut the marginal cost by more than half while the ratio barely
moved, 3.55x to 3.30x, because an index over N pairs costs O(N) however
cheaply it is stored. The scaling was never the defect; the constant was, and a
ratio gate would have gone on reporting "still holds" across the very fix it
was written to notice. Both directions have now been demonstrated in anger
rather than argued.

A regression here is the one that matters to this repository: at 80 bytes a
pair `runspecs/pending/expand-sourcetype.esm` could not be evaluated at all on
a 40 GB allocation, and at 34 every RunSpec in the tree runs in under 1 GB.

usage: check-join-gate-memory.py <esm-binary> <control.esm> <scratch-dir>
"""
import json
import os
import re
import resource
import subprocess
import sys

MAX_BYTES_PER_PAIR = 50.0
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
    marginal = (r_hi - r_lo) / (p_hi - p_lo)
    print("  %.1fx the pairs, %.2fx the peak, %.0f bytes per MARGINAL pair"
          % (p_hi / p_lo, ratio, marginal))

    if marginal < MAX_BYTES_PER_PAIR:
        print("F58 stays fixed: a candidate pair costs %.0f bytes, under %.0f "
              "(EarthSciML/EarthSciAST#418, PRs #420 and #423)" % (marginal,
                                                                   MAX_BYTES_PER_PAIR))
        return 0
    print("F58 HAS REGRESSED: a candidate pair now costs %.0f bytes, at or over "
          "the %.0f this gate allows -- it was 34 when #420 and #423 merged and "
          "79 before them. Every RunSpec in this tree is evaluated through that "
          "number: at 80 bytes a pair expand-sourcetype needed more than a 40 GB "
          "allocation. Check what moved in the pinned toolchain "
          "(esm-version.lock) before trusting a memory measurement from it."
          % (marginal, MAX_BYTES_PER_PAIR))
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
