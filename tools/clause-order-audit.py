#!/usr/bin/env python3
"""Check that no result in this repository depends on the ORDER of a join.

`perturbation-audit.py` moves the numbers and requires every assertion to go
red.  This is its dual: it moves the STRUCTURE and requires nothing to move at
all.  CONFORMANCE_SPEC §5.5.8 says which clause of a multi-clause join drives
cannot change the result, and §5.24's conjunctive gate is what makes that true
rather than merely intended.  A contract nothing exercises is a contract nobody
has checked, and this one went unchecked long enough to hide a wrong answer.

That is not hypothetical.  Finding F17 was filed as a COST problem -- a join
that had to be hand-ordered to stay fast -- and turned out to be a silent wrong
answer: every resolved `on` pair is also lowered into the aggregate's filter,
that lowered comparison carried no precision marker, and at binary32 the
spacing at SCC magnitude is 256, so 2265007010 and 2265007015 were the same
float.  Permuting one equation's three clauses changed 32 of 144 rows.  The
published fidelity numbers had been right only because the SCC clause happened
to be written first.  Nothing in the suite would have said otherwise.

So there are two order axes here and both are checked:

  * CLAUSE order  -- the order of the `join` list, i.e. which clause drives.
  * PAIR order    -- the order of the `on` list inside one clause, i.e. which
                     key of a composite contraction is compared first.  This is
                     the axis a hand-fused composite clause lives on, and it is
                     the one a reader is least likely to think of as an axis.

The check is byte-identity of the emitted relation, not "the assertions still
pass".  An assertion has a tolerance; a wrong answer inside that tolerance is
exactly the failure this is meant to catch, and only byte-identity catches it.
The inline tests are run too, but as a second signal, not the gate.

Documents are perturbed IN PLACE and restored from git, for the reason
perturbation-audit.py gives: a `data_source` url_template resolves against its
own document's directory (F15), so a copy elsewhere resolves to nothing.  The
tree must be clean before this starts and is verified clean again at the end.
"""
import hashlib, json, os, random, subprocess, sys

DIRS = ["components", "runs", "fixtures", "lib"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESM = os.environ.get("ESM", "./esm")
# Not tempfile.mkdtemp: CLAUDE.md keeps scratch out of /tmp, which is RAM-backed
# here. Emitted CSVs are small, but the rule is the rule and a failure wants its
# artifacts somewhere the next command can still find them.
OUTDIR = os.environ.get("CLAUSE_ORDER_OUT", os.path.join(ROOT, ".clause-order-run"))


def run(*cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def dirty():
    return run("git", "status", "--porcelain", "--", *DIRS).stdout.strip()


# --- the perturbations -----------------------------------------------------
#
# Each takes a list and returns a reordering of it.  `reverse` is the strongest
# single disturbance and `rotate` is the one that moves EVERY element while
# keeping the cyclic order, which distinguishes "depends on which clause is
# first" from "depends on the relative order of two particular clauses".
# Shuffles are seeded so a failure is reproducible from its report alone.

def reverse(xs):
    return xs[::-1]


def rotate(xs):
    return xs[1:] + xs[:1]


def shuffled(seed):
    def go(xs):
        ys = list(xs)
        random.Random(seed + len(xs)).shuffle(ys)
        return ys
    return go


MODES = [("reverse", reverse), ("rotate", rotate)] + [
    ("shuffle:%d" % s, shuffled(s)) for s in (1, 2, 3)
]


def permute(node, reorder, counts):
    """Reorder every `join` list and every `on` list, depth first, in place."""
    if isinstance(node, dict):
        join = node.get("join")
        if isinstance(join, list):
            for clause in join:
                on = clause.get("on") if isinstance(clause, dict) else None
                if isinstance(on, list) and len(on) > 1:
                    clause["on"] = reorder(on)
                    counts["pairs"] += 1
                if isinstance(clause, dict) and "syms" in clause:
                    counts["syms"] += 1
            if len(join) > 1:
                node["join"] = reorder(join)
                counts["clauses"] += 1
        for value in node.values():
            permute(value, reorder, counts)
    elif isinstance(node, list):
        for item in node:
            permute(item, reorder, counts)


# --- what "the result" means -----------------------------------------------
#
# Every `runs/*.esm` is emitted exactly the way run-tests.sh emits it: one row
# per index tuple, every `out_*` variable observed.  The field list is read from
# the document rather than hard-coded, for the reason that stage gives -- which
# columns a run emits is the document's business.

def runnable(docs):
    """The documents `simulate` can be pointed at -- i.e. the FIXTURES.

    run-tests.sh's fixture stage sets `run="$f"` over `find fixtures -name
    '*.esm'`, so a fixture is its own run document; `runs/*.esm` are the
    component-level wirings and declare no `out_*` variables at all.  The first
    version of this file emitted `runs/` instead, found nothing to observe,
    skipped every document, and printed a clean sweep -- a gate that could not
    fail, which is the exact defect its sibling perturbation-audit.py exists to
    catch.  Hence `require_output` below: an empty baseline is now a refusal,
    not a pass.
    """
    return [d for d in docs if d.startswith("fixtures" + os.sep)]


def out_fields(path):
    doc = json.load(open(os.path.join(ROOT, path)))
    return sorted(
        name
        for model in doc.get("models", {}).values()
        for name in (model.get("variables") or {})
        if name.startswith("out_")
    )


def emit(runs, outdir, tag):
    """Return {run: sha256 of its emitted CSV}, or {run: '<error>'}."""
    digests = {}
    for path in runs:
        name = os.path.basename(path)[: -len(".esm")]
        dest = os.path.join(outdir, "%s.%s.csv" % (name, tag))
        obs = []
        for field in out_fields(path):
            obs += ["--observed", field]
        if not obs:
            continue
        result = run(ESM, "simulate", path, "--time", "0",
                     "--format", "csv", *obs, "--output", dest)
        if result.returncode != 0:
            digests[name] = "ERROR: " + (result.stderr or result.stdout).strip().splitlines()[-1][:120]
        else:
            digests[name] = hashlib.sha256(open(dest, "rb").read()).hexdigest()
    return digests


def test_table():
    result = run(ESM, "test", *DIRS)
    rows = {}
    for line in (result.stdout + result.stderr).splitlines():
        parts = line.split()
        if len(parts) == 4 and all(p.isdigit() for p in parts[1:]):
            rows[parts[0]] = tuple(parts[1:])
    return rows


def main():
    if dirty():
        sys.exit("refusing to run: %s are not clean in git, and this restores "
                 "by discarding changes to them" % "/".join(DIRS))

    docs = sorted(
        os.path.join(d, f)
        for d in DIRS
        if os.path.isdir(os.path.join(ROOT, d))
        for f in os.listdir(os.path.join(ROOT, d))
        if f.endswith(".esm") and not f.startswith(".")
    )
    runs = runnable(docs)
    pristine = {d: open(os.path.join(ROOT, d)).read() for d in docs}

    outdir = OUTDIR
    os.makedirs(outdir, exist_ok=True)
    print("clause-order audit of %s" % ", ".join(DIRS))
    print("  %d documents, %d of them runnable (fixtures)" % (len(docs), len(runs)))

    base_digests = emit(runs, outdir, "base")
    base_tests = test_table()
    broken = {k: v for k, v in base_digests.items() if v.startswith("ERROR")}
    if broken:
        sys.exit("refusing to run: the unperturbed tree does not emit: %r" % broken)
    if len(base_digests) != len(runs):
        sys.exit("refusing to run: %d runnable documents but %d emitted a "
                 "relation. A document that emits nothing is not checked by "
                 "this audit at all, and a silent skip here reads exactly like "
                 "a pass." % (len(runs), len(base_digests)))
    if not base_digests:
        sys.exit("refusing to run: nothing emitted a relation, so byte-identity"
                 " would be checked over an empty set and would pass vacuously.")
    print("  baseline: %d relations emitted, %d test rows\n"
          % (len(base_digests), len(base_tests)))

    failures = []
    try:
        for tag, reorder in MODES:
            counts = {"clauses": 0, "pairs": 0, "syms": 0}
            for doc in docs:
                model = json.loads(pristine[doc])
                permute(model, reorder, counts)
                with open(os.path.join(ROOT, doc), "w") as fh:
                    json.dump(model, fh, indent=2)

            digests = emit(runs, outdir, tag.replace(":", "-"))
            tests = test_table()

            moved = sorted(k for k in base_digests if digests.get(k) != base_digests[k])
            same_tests = tests == base_tests
            status = "ok " if (not moved and same_tests) else "FAIL"
            print("  %s %-12s %3d clause lists, %3d on lists reordered"
                  % (status, tag, counts["clauses"], counts["pairs"]))
            if moved:
                failures.append((tag, moved))
                for k in moved:
                    print("       %-28s %s -> %s"
                          % (k, base_digests[k][:12], digests.get(k, "<missing>")[:12]))
            if not same_tests:
                failures.append((tag, ["<inline tests>"]))
                for k in sorted(set(base_tests) | set(tests)):
                    if base_tests.get(k) != tests.get(k):
                        print("       test row %-24s %s -> %s"
                              % (k, base_tests.get(k), tests.get(k)))
    finally:
        run("git", "checkout", "--", *DIRS)

    if dirty():
        sys.exit("PANIC: failed to restore %s -- inspect before doing anything "
                 "else" % "/".join(DIRS))

    if failures:
        print("\n  a result depends on the order of a join. The emitted CSVs are")
        print("  kept in %s -- diff the base against the mode that moved it." % outdir)
        print("  Reproduce one site at a time by applying only that mode's")
        print("  reordering to a single document.")
        sys.exit(1)
    print("\n  every relation is byte-identical under all %d reorderings, and no"
          % len(MODES))
    print("  inline test row moved. No result depends on the order of a join.")


if __name__ == "__main__":
    main()
