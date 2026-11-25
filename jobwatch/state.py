"""The seen-list: which postings earlier runs have already reported."""

import json
import os
import sys


def load_seen(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return set(json.load(handle))
    except Exception:
        return set()


def save_seen(path, keys):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(sorted(keys), handle, indent=0)
        handle.write("\n")


def seed_backlogs(matches, seen, regions, threshold, quiet=False):
    """Record a first-time region or source instead of reporting it.

    Two guards, because they fail differently. A region's first run opens with
    the whole market (hundreds of roles), which is a backlog to browse, not a
    day's news. And a source switched on inside a region that is already
    seeded (say you add an API key for a board) dumps its whole backlog with no
    warning, which can also exceed GitHub's issue-body limit.

    Flips match["new"] off for whatever it seeds and returns the markers to
    store. A new source carrying fewer than `threshold` roles reports normally.
    """
    markers = set()
    for region in regions:
        name = region["name"]
        here = [m for m in matches if m["region"] == name]
        region_marker = f"seeded:{name}"
        if region.get("seed_on_first_run", False) and region_marker not in seen:
            markers.add(region_marker)
            markers |= {f"seeded:{name}:{m.get('source', 'feed')}" for m in here}
            for match in here:
                match["new"] = False
            if not quiet:
                print(f"Erster Lauf für {name}: {len(here)} aktuelle Stellen werden als gesehen "
                      "gespeichert, aber nicht gemeldet.", file=sys.stderr)
            continue
        markers.add(region_marker)
        for source in sorted({m.get("source", "feed") for m in here}):
            marker = f"seeded:{name}:{source}"
            if marker in seen:
                continue
            markers.add(marker)
            backlog = [m for m in here if m.get("source", "feed") == source and m["new"]]
            if len(backlog) < threshold:
                continue
            for match in backlog:
                match["new"] = False
            if not quiet:
                print(f"Erster Lauf mit {source} in {name}: {len(backlog)} bestehende Stellen "
                      "werden als gesehen gespeichert, aber nicht gemeldet.", file=sys.stderr)
    return markers
