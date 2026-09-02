#!/usr/bin/env python3
"""Is `agedist.f`'s 30-year fold equal to a closed form over its residuals?

`agedist.f` (docs/nonroad-logging-county.md §2.2(e)) folds a 51-slot vector
thirty times:

    md_y[ia] = max(md_{y-1}[ia-1] * (1 - yy[ia]), 0)     ia = 1..50
    md_y[0]  = tpf_y - sum(md_y[ia], ia = 1..50)          unclamped

The inner loop is a parallel map, which `.esm` can spell; the outer one is a
fold, which it cannot (docs/findings/README.md F12). This script tests a
CANDIDATE REDUCTION of the outer fold, which rests on one property of the
inputs -- `1 - yy[ia] >= 0` for every slot -- and one consequence: because a
non-negative cohort times a non-negative survival stays non-negative, and
because slots 1..50 are themselves a `max(., 0)`, a negative value can only
ever ENTER at the initial vector or at the unclamped residual md[0]. So along
any chain the clamp bites at most once, at the step where a negative first
meets it, and the chain is identically zero thereafter. Tracing slot `ia` back
`ia` steps therefore lands on a residual, or -- if `ia > y` -- on the initial
vector:

    md_y[ia] = max(r_{y-ia},   0) * prod(1-yy[k], k = 1..ia)      ia <= y
    md_y[ia] = max(mf0[ia-y],  0) * prod(1-yy[k], k = ia-y+1..ia) ia >  y
    r_y      = tpf_y - sum(md_y[ia], ia = 1..50)

which collapses the 51-vector fold to a SCALAR recurrence on 31 residuals.

The inputs come from the §6.5 reproduction script, extracted from the
specification rather than copied, so there is one source of truth and both
sides of the comparison see the same `yy`, `mf0`, `tpf` and `baspop`. Every
one of the fixture's six equipment points is checked at every year and every
slot, in float32.

    ./tools/verify-agedist-reduction.py [SNAPSHOT_DIR]

Exit 0 iff the closed form reproduces the fold in every cell. Cells that
differ only in the SIGN of a zero are reported separately and are not
failures: `-0.0 == 0.0`, a summation and a `<= 0` test cannot tell them apart,
and the fold produces `-0.0` only because `max(-0.0, +0.0)` returns its first
argument.
"""
import pathlib
import re
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
SPEC = HERE.parent / "docs" / "nonroad-logging-county.md"


def default_snapshot():
    d = HERE.parent
    while d != d.parent:
        p = d / "moves.rs" / "characterization" / "snapshots" / "nr-logging-county"
        if p.is_dir():
            return str(p)
        d = d.parent
    sys.exit("no nr-logging-county snapshot found; pass one on the command line")


def oracle_cases(snapshot):
    """Run §6.5's script, recording every `agedist` call's inputs and answer."""
    lines = SPEC.read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("### 6.5"))
    end = next(i for i, l in enumerate(lines) if i > start and l.startswith("### 6.6"))
    block = lines[start:end]
    b = next(i for i, l in enumerate(block) if l.strip() == "```python")
    e = next(i for i, l in enumerate(block) if i > b and l.strip() == "```")
    src = block[b + 1:e]
    hits = [i for i, l in enumerate(src) if l.strip().startswith("md = agedist(")]
    if len(hits) != 1:
        sys.exit(f"§6.5 has {len(hits)} `md = agedist(` call sites, expected 1")
    indent = re.match(r"\s*", src[hits[0]]).group(0)
    src.insert(hits[0] + 1, indent + (
        "CASES.append(dict(scc=scc, sp=f(sp), mf0=list(mf0), yy=list(yy), ny=ny,"
        " ys=list(ys), vs=list(vs), md=list(md)))"))
    ns = {"CASES": [], "__name__": "__verify_agedist__"}
    argv = sys.argv
    sys.argv = ["repro.py", snapshot]
    try:
        exec(compile("\n".join(src), "nonroad-logging-county.md §6.5", "exec"), ns)
    finally:
        sys.argv = argv
    return ns, ns["CASES"]


def fold(ns, baspop, mf0, base_year, growth_year, yy, ys, vs):
    """§2.2(e) verbatim, keeping every intermediate year."""
    f, MXAGYR, growth_factor = ns["f"], ns["MXAGYR"], ns["growth_factor"]
    md = list(mf0)
    hist = [list(md)]
    totpop = f(baspop)
    for iyear in range(base_year + 1, growth_year + 1):
        tmp = list(md)
        gf = growth_factor(ys, vs, iyear - 1, iyear)
        if gf != 0:
            totpop = max(totpop, f(0.0001))
        totpop = max(f(totpop * (f(1.0) + gf)), f(0))
        tpf = f(totpop / f(baspop))
        s = f(0)
        for ia in range(1, MXAGYR):
            u = max(f(tmp[ia - 1] * (f(1.0) - yy[ia])), f(0))
            md[ia] = u
            s = f(s + u)
        md[0] = f(tpf - s)
        hist.append(list(md))
    return hist


def closed_form(ns, baspop, mf0, base_year, growth_year, yy, ys, vs):
    """The candidate: every cell a clamped base times a run of survivals."""
    f, MXAGYR, growth_factor = ns["f"], ns["MXAGYR"], ns["growth_factor"]
    S = [f(f(1.0) - yy[ia]) for ia in range(MXAGYR)]
    span = growth_year - base_year
    tpf = [None] * (span + 1)
    totpop = f(baspop)
    for y in range(1, span + 1):
        gf = growth_factor(ys, vs, base_year + y - 1, base_year + y)
        if gf != 0:
            totpop = max(totpop, f(0.0001))
        totpop = max(f(totpop * (f(1.0) + gf)), f(0))
        tpf[y] = f(totpop / f(baspop))

    r = [mf0[0]] + [None] * span
    hist = [list(mf0)]
    for y in range(1, span + 1):
        row = [None] * MXAGYR
        s = f(0)
        for ia in range(1, MXAGYR):
            if ia <= y:
                v, lo = max(r[y - ia], f(0)), 1
            else:
                v, lo = max(mf0[ia - y], f(0)), ia - y + 1
            for k in range(lo, ia + 1):          # ascending, as the fold applies them
                v = f(v * S[k])
            row[ia] = v
            s = f(s + v)
        r[y] = f(tpf[y] - s)
        row[0] = r[y]
        hist.append(row)
    return hist


def main():
    snapshot = sys.argv[1] if len(sys.argv) > 1 else default_snapshot()
    ns, cases = oracle_cases(snapshot)
    f, MXAGYR = ns["f"], ns["MXAGYR"]
    if not cases:
        sys.exit("§6.5 ran but called agedist zero times")

    bits = lambda x: np.float32(x).tobytes()
    failed = 0
    print(f"\n{len(cases)} equipment points, {len(set(c['scc'] for c in cases))} SCCs")
    for c in cases:
        hist = fold(ns, c["sp"], c["mf0"], 1990, 2020, c["yy"], c["ys"], c["vs"])
        cand = closed_form(ns, c["sp"], c["mf0"], 1990, 2020, c["yy"], c["ys"], c["vs"])
        if any(bits(a) != bits(b) for a, b in zip(hist[-1], c["md"])):
            print(f"  {c['scc']}: BUG — the replayed fold is not §6.5's own answer")
            failed += 1
            continue
        diff = [(y, ia) for y in range(len(hist)) for ia in range(MXAGYR)
                if np.float32(hist[y][ia]) != np.float32(cand[y][ia])]
        zsign = [(y, ia) for y in range(len(hist)) for ia in range(MXAGYR)
                 if bits(hist[y][ia]) != bits(cand[y][ia]) and (y, ia) not in diff]
        neg_mf0 = [i for i, v in enumerate(c["mf0"]) if v < 0]
        neg_r = [y for y in range(1, len(hist)) if hist[y][0] < 0]
        surv_min = min(f(f(1.0) - y) for y in c["yy"])
        verdict = "ok  " if not diff else "FAIL"
        print(f"  {verdict} {c['scc']}  nyrlif={c['ny']:2d}  baspop={c['sp']:<12.6g}"
              f" min(1-yy)={surv_min:g}"
              f"  mf0<0 at {len(neg_mf0)} slots  residual<0 in {len(neg_r)} years"
              f"  differing cells {len(diff)}/{len(hist) * MXAGYR}"
              f"  (+{len(zsign)} zero-sign only)")
        if diff:
            failed += 1
            for y, ia in diff[:8]:
                print(f"          y={y} ia={ia} fold={hist[y][ia]!r} closed={cand[y][ia]!r}")
    if failed:
        print(f"\n{failed} point(s) disagree — the reduction is FALSE\n")
        return 1
    print("\nthe closed form reproduces the fold in every cell of every point\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
