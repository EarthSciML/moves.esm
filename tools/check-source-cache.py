#!/usr/bin/env python3
"""Refuse a run whose data-source cache disagrees with the files on disk.

WHY THIS EXISTS (finding **F42**). `esm` caches every ingested data source
under `$TMPDIR/earthsci-esm-cache/<source name>/v1/`, keyed by the source name
and the resolved **URL string**, and it does not revalidate: once a URL has
been read, the cached blob is returned whatever the file at that path now says.
Swap the corpus under `../moves.rs` — as the `moves-snapshot/v2` recapture did
— and every fixture keeps reading the corpus that is gone.

That failure is silent and it is *plausible*. It presented as ten of fourteen
fixtures red with numbers from the previous corpus: `act_sho` 27.33 where the
snapshot on disk says 260.057, and index sets sized 2 / 82 / 1288 where the
parquet holds 1 / 41 / 644. Nothing in the run mentioned a cache, and reaching
the identical directory through a differently-named symlink — a cache MISS —
gave the right answer on the same bytes, which is what finally attributed it.

**It can also fail green**, which is worse and is the reason this is a gate
rather than a note: a warm entry from a corpus that has since been deleted will
make a suite pass against data that no longer exists.

The check is cheap and needs nothing but the cache's own metadata: each
`meta/*.json` records the `url`, the `bytes` and the `sha256_content` of what
was stored. Compare that against the file the URL names. A `file://` entry
whose target still exists and whose content hash differs is STALE, and this
exits non-zero. Entries for files that have since been deleted or moved are
reported but not fatal: they are dead weight, not a wrong answer waiting to be
served to this run.

    tools/check-source-cache.py [--cache DIR] [--prune]

`--prune` deletes the stale metadata so the next run re-reads the file. It
removes only the metadata records, never a blob: blobs are content-addressed
and shared, and an orphan blob costs disk rather than correctness.
"""

import argparse
import hashlib
import json
import os
import pathlib
import sys
from urllib.parse import unquote, urlparse

DEFAULT_CACHE = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "earthsci-esm-cache"
# Reading every cached file back in full would cost more than the suite it
# guards, so the hash is only computed when the SIZE already matches. A size
# change is proof enough on its own, and it is what the v2 recapture produced
# on almost every table (12 decimal places to shortest-round-trip).
HASH_LIMIT_BYTES = 64 * 1024 * 1024


def local_path(url):
    """The filesystem path a `file://` URL names, or None for anything else."""
    parts = urlparse(url)
    if parts.scheme != "file":
        return None
    return pathlib.Path(unquote(parts.path))


def check(cache: pathlib.Path):
    stale, missing, checked = [], [], 0
    for meta in sorted(cache.glob("*/v1/meta/*.json")):
        try:
            rec = json.loads(meta.read_text())
        except (ValueError, OSError):
            continue
        url = rec.get("url")
        if not url:
            continue
        path = local_path(url)
        if path is None:
            continue
        checked += 1
        if not path.exists():
            missing.append((meta, url))
            continue
        size = path.stat().st_size
        if rec.get("bytes") is not None and size != rec["bytes"]:
            stale.append((meta, url, f"{rec['bytes']} bytes cached, {size} on disk"))
            continue
        want = rec.get("sha256_content")
        if not want or size > HASH_LIMIT_BYTES:
            continue
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != want:
            stale.append((meta, url, f"content hash {want[:12]} cached, {got[:12]} on disk"))
    return checked, stale, missing


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=pathlib.Path, default=DEFAULT_CACHE)
    ap.add_argument("--prune", action="store_true",
                    help="delete the stale metadata records so the next run re-reads")
    args = ap.parse_args(argv)

    if not args.cache.exists():
        print(f"  no data-source cache at {args.cache}; nothing to check")
        return 0

    checked, stale, missing = check(args.cache)
    print(f"  {checked} cached file:// source(s) checked against disk, "
          f"{len(stale)} stale, {len(missing)} naming a file that is gone")

    if missing and not stale:
        print("  (an entry whose file is gone is dead weight, not a wrong answer)")

    if not stale:
        return 0

    print()
    print("  STALE CACHE — this run would read data the file on disk no longer holds.")
    print("  esm keys its cache on the URL and never revalidates (finding F42), so a")
    print("  corpus swapped in place is invisible to it. Clear it and re-run:")
    print()
    print(f"      rm -rf {args.cache}")
    print()
    for meta, url, why in stale[:10]:
        print(f"    {meta.parent.parent.parent.name}: {why}")
        print(f"      {url}")
    if len(stale) > 10:
        print(f"    ... and {len(stale) - 10} more")

    if args.prune:
        for meta, _, _ in stale:
            meta.unlink()
        print(f"\n  --prune: removed {len(stale)} stale metadata record(s); "
              f"blobs left alone (content-addressed, shared).")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
