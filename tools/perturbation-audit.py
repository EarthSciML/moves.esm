#!/usr/bin/env python3
"""Check that every inline assertion in this repo is capable of failing.

A gate that cannot fail is worse than no gate: an assertion whose tolerance is
wider than the error it is meant to catch passes forever and reads, in a diff,
exactly like one that works.  So this walks every `"expected"` in the given
directories, moves it by a perturbation far larger than any tolerance the repo
declares, and requires that EVERY assertion then goes red.  One that stays
green under a 10^-3 nudge is decoration, and this names it.

The zero-valued assertions are the case that matters most and the easiest to
get wrong -- x*(1+e) leaves a zero exactly where it was, so a multiplicative
audit silently skips them and reports a clean sweep.  They are nudged
ADDITIVELY here, and counted separately in the report for that reason.

The documents are perturbed IN PLACE and restored from git afterwards, rather
than copied to a scratch directory, because two of them ingest: a `data_source`
url_template resolves against its own document's directory (finding F15), so a
copy elsewhere would resolve to a different file or to nothing.  In place is
the only location where what runs is what is checked in.  The tree must be
clean before this starts, and is verified clean again at the end.
"""
import json, os, subprocess, sys

REL = 1e-3          # multiplicative nudge for non-zero expectations
ABS = 1e-3          # additive nudge for expectations of exactly zero
DIRS = sys.argv[1:] or ["components", "runs"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(*cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def perturb(node, counts):
    """Rewrite every `expected` in place, depth first.  Returns nothing."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "expected" and isinstance(value, (int, float)) and not isinstance(value, bool):
                if value == 0.0:
                    node[key] = ABS
                    counts["zero"] += 1
                else:
                    node[key] = value * (1.0 + REL)
                    counts["nonzero"] += 1
            else:
                perturb(value, counts)
    elif isinstance(node, list):
        for item in node:
            perturb(item, counts)


def dirty():
    return run("git", "status", "--porcelain", "--", *DIRS).stdout.strip()


def main():
    if dirty():
        sys.exit("refusing to run: %s are not clean in git, and this restores "
                 "by discarding changes to them" % "/".join(DIRS))

    docs = sorted(
        os.path.join(d, f)
        for d in DIRS
        for f in os.listdir(os.path.join(ROOT, d))
        if f.endswith(".esm") and not f.startswith(".")
    )
    counts = {"zero": 0, "nonzero": 0}
    try:
        for doc in docs:
            path = os.path.join(ROOT, doc)
            with open(path) as fh:
                model = json.load(fh)
            perturb(model, counts)
            with open(path, "w") as fh:
                json.dump(model, fh, indent=2)
        result = run("./esm", "test", *DIRS)
        table = result.stdout + result.stderr
    finally:
        run("git", "checkout", "--", *DIRS)

    if dirty():
        sys.exit("PANIC: failed to restore %s -- inspect before doing anything "
                 "else" % "/".join(DIRS))

    total = counts["zero"] + counts["nonzero"]
    survivors = []
    passed = failed = 0
    for line in table.splitlines():
        parts = line.split()
        # `<name> <pass> <fail> <error>` -- the per-document rows and the TOTAL
        if len(parts) == 4 and all(p.isdigit() for p in parts[1:]):
            p, f = int(parts[1]), int(parts[2])
            if parts[0] == "TOTAL":
                passed, failed = p, f
            elif p:
                survivors.append((parts[0], p))

    print("perturbation audit of %s" % ", ".join(DIRS))
    print("  %4d assertions declared and perturbed" % total)
    print("       %4d non-zero, moved to x(1 + %g)" % (counts["nonzero"], REL))
    print("       %4d exactly zero, moved to %g additively" % (counts["zero"], ABS))
    print("  %4d evaluations (declared, plus each mounted component's re-run)" % (passed + failed))
    print("  %4d fail, %d pass" % (failed, passed))
    if survivors:
        print("\n  these assertions did NOT go red, and are not gates:")
        for name, n in survivors:
            print("    %-55s %d still passing" % (name, n))
        sys.exit(1)
    print("\n  every assertion went red.  none is decoration.")


if __name__ == "__main__":
    main()
