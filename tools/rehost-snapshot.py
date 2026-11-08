#!/usr/bin/env python3
"""Rename a snapshot's host token, keeping it loadable.

MOVES names its execution and worker databases after the host, and a snapshot's
table files carry that name. build-snapshots.sh renames a new capture's token to
the one the tracked documents read -- and a rename has to reach three places, not
one: the files, each `.meta.json`'s `name` (so its metadata_sha256), and
`manifest.json`'s entries and aggregate_sha256. Renaming the files alone leaves a
snapshot that moves-snapshot refuses to open (2026-11-02, 24 recaptures). The
hashing is moves.rs crates/moves-snapshot/src/{manifest,snapshot}.rs; `--check`
reproduces committed manifests byte for byte.

usage: rehost-snapshot.py <snapshot_dir> <old_token> <new_token>
       rehost-snapshot.py --check <snapshot_dir>...
"""
import hashlib, json, os, struct, sys


def sha(b):
    return hashlib.sha256(b).hexdigest()


def aggregate(entries):
    h = hashlib.sha256()
    for e in entries:
        h.update(e["name"].encode()); h.update(b"\n")
        h.update(e["content_sha256"].encode()); h.update(b"\n")
        h.update(e["metadata_sha256"].encode()); h.update(b"\n")
        h.update(struct.pack("<Q", e["row_count"])); h.update(b"\n")
    return h.hexdigest()


def dump(m):
    return (json.dumps(m, indent=2, ensure_ascii=False) + "\n").encode()


def check(d):
    raw = open(os.path.join(d, "manifest.json"), "rb").read()
    m = json.loads(raw)
    bad = []
    if dump(m) != raw:
        bad.append("serialization differs")
    if aggregate(m["tables"]) != m["aggregate_sha256"]:
        bad.append("aggregate")
    for e in m["tables"]:
        t = os.path.join(d, "tables", e["name"])
        try:
            if sha(open(t + ".meta.json", "rb").read()) != e["metadata_sha256"]:
                bad.append("meta " + e["name"])
            if sha(open(t + ".parquet", "rb").read()) != e["content_sha256"]:
                bad.append("content " + e["name"])
        except FileNotFoundError:
            bad.append("missing " + e["name"])
    return bad


def rewrite(d, old, new):
    tdir = os.path.join(d, "tables")
    for f in os.listdir(tdir):
        if old in f:
            os.rename(os.path.join(tdir, f), os.path.join(tdir, f.replace(old, new)))
    mp = os.path.join(d, "manifest.json")
    m = json.load(open(mp))
    for e in m["tables"]:
        e["name"] = e["name"].replace(old, new)
        p = os.path.join(d, "tables", e["name"] + ".meta.json")
        b = open(p, "rb").read()
        nb = b.replace(old.encode(), new.encode())
        if nb != b:
            open(p, "wb").write(nb)
        e["metadata_sha256"] = sha(nb)
    m["tables"].sort(key=lambda e: e["name"].encode())
    m["aggregate_sha256"] = aggregate(m["tables"])
    open(mp, "wb").write(dump(m))


if __name__ == "__main__":
    if sys.argv[1] == "--check":
        bad_any = False
        for d in sys.argv[2:]:
            b = check(d)
            print(("ok   " if not b else "BAD  ") + d, b[:3])
            bad_any = bad_any or bool(b)
        sys.exit(1 if bad_any else 0)
    else:
        rewrite(*sys.argv[1:4])
