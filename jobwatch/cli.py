"""jobwatch: Stellen-Feeds von Firmen und Jobbörsen nach passenden Stellen durchsuchen.

    python -m jobwatch                    # passende Stellen, neue mit NEU markiert
    python -m jobwatch --new              # nur Stellen, die noch nie gemeldet wurden
    python -m jobwatch --wide             # zusätzlich die konfigurierten Jobbörsen
    python -m jobwatch --all              # alle Stufen, nicht nur Senior-Stellen
    python -m jobwatch --raw              # alles, ganz ohne Filter
    python -m jobwatch --json             # maschinenlesbare Ausgabe
    python -m jobwatch --location zurich  # nur ein Ort aus jobhunter.yml

    python -m jobwatch init               # 5 Fragen beantworten, jobhunter.yml erhalten
    python -m jobwatch add-company URL    # Bewerbungssystem aus einer Karriere-URL erkennen
    python -m jobwatch check              # Konfiguration prüfen, jeden Feed anpingen
    python -m jobwatch probe NAME         # welches Bewerbungssystem nutzt "acme"?
    python -m jobwatch fetch-ad URL       # ein vollständiges Inserat als job.md speichern

Gesehene Stellen werden in der Zustandsdatei gespeichert (Standard
.jobwatch/seen.json); ein neuer Lauf markiert nur, was seither dazukam.
Mit --no-save wird nur geschaut, nichts gespeichert.
"""

import argparse
import concurrent.futures as futures
import json
import os
import sys

from . import adapters, boards
from .config import ConfigError, load
from .filters import (already_have, annotate, below_floor, dedupe_key, in_region,
                      is_senior, seen_key, title_ok)
from .state import load_seen, save_seen, seed_backlogs

COMMANDS = ("init", "add-company", "check", "probe", "fetch-ad")


def region_for(location, regions):
    for region in regions:
        if in_region(location, region):
            return region
    return None


def collect_feeds(cfg, regions, args):
    """Fetch every company feed once; assign each posting to the first matching location."""
    with futures.ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(adapters.load, cfg["companies"]))
    matches = []
    for name, jobs in results:
        for title, location, url, salary in jobs:
            region = region_for(location, regions)
            if not args.raw:
                if region is None or not title_ok(title, cfg, args.all, url):
                    continue
            matches.append({"source": "feed",
                            "region": region["name"] if region else regions[0]["name"],
                            "company": name, "title": title.strip(),
                            "location": (location or "").strip(), "url": url,
                            "salary": salary, "senior": is_senior(title, cfg)})
    dead = [name for name, jobs in results if not jobs]
    return matches, dead


def collect_boards(cfg, regions, args, matches):
    known = {dedupe_key(m) for m in matches}
    for region in regions:
        for row in boards.search(region, cfg, broad=args.all):
            if not args.raw:
                if not title_ok(row["title"], cfg, args.all, row.get("url", "")):
                    continue
                if not row.pop("_trust_location", False) and not in_region(row["location"], region):
                    continue
            row.pop("_trust_location", None)
            key = dedupe_key(row)
            if already_have(key, known):
                continue   # the company's own feed (or another board) already has it
            known.add(key)
            row.update(region=region["name"], senior=is_senior(row["title"], cfg))
            matches.append(row)
    return matches


def run(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jobwatch", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="Pfad zu jobhunter.yml (Standard: ./jobhunter.yml)")
    parser.add_argument("--location", "--region", dest="location",
                        help="ein Ortsname aus jobhunter.yml oder 'all'")
    parser.add_argument("--all", action="store_true", help="alle Stufen, nicht nur Senior-Stellen")
    parser.add_argument("--wide", action="store_true", help="zusätzlich die konfigurierten Jobbörsen durchsuchen")
    parser.add_argument("--raw", action="store_true", help="alle Stellen, ungefiltert")
    parser.add_argument("--new", action="store_true", help="nur noch nie gesehene Stellen")
    parser.add_argument("--json", action="store_true", help="maschinenlesbare Ausgabe (JSON)")
    parser.add_argument("--no-save", action="store_true", help="Gesehenes nicht speichern")
    parser.add_argument("--include-ruled-out", action="store_true",
                        help="auch ausgeschlossene Firmen und bereits beworbene Stellen zeigen")
    parser.add_argument("commands", nargs="*", metavar="COMMAND",
                        help=f"optionaler Befehl: {', '.join(COMMANDS)} (siehe oben)")
    args = parser.parse_args(argv)
    if args.commands:
        if args.commands[0] in COMMANDS:
            parser.error(f"der Befehl {args.commands[0]!r} muss an erster Stelle stehen, "
                         f"z. B. python -m jobwatch {args.commands[0]} ... --config DATEI")
        parser.error(f"unbekannter Befehl {args.commands[0]!r}; möglich sind: {', '.join(COMMANDS)}")

    try:
        cfg = load(args.config)
    except ConfigError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    names = (cfg["default_regions"] if not args.location or args.location == "all"
             else [args.location])
    if any(n not in cfg["regions"] for n in names):
        print(f"Fehler: unbekannter Ort {args.location!r}; bekannt: {', '.join(cfg['regions'])}",
              file=sys.stderr)
        return 2
    regions = [cfg["regions"][n] for n in names]

    matches, dead = collect_feeds(cfg, regions, args)
    if args.wide:
        matches = collect_boards(cfg, regions, args, matches)

    from .records import load_all, same_company
    previous = load_all(os.path.join(cfg["_base_dir"], "applications"))
    kept = []
    for m in matches:
        hide, note = annotate(m, cfg)
        if not note and previous:
            earlier = same_company(m["company"], previous)
            note = earlier[0] if earlier else ""
        if hide and not args.include_ruled_out:
            continue
        m["note"] = note
        kept.append(m)
    matches = kept

    seen = load_seen(cfg["state_file"])
    for m in matches:
        # A repost gets a new URL on the boards; the company+title key keeps it
        # from showing up as new again.
        m["new"] = bool(m["url"]) and m["url"] not in seen and seen_key(m) not in seen
    seeded = seed_backlogs(matches, seen, regions, cfg["source_backlog"], quiet=False)

    dropped = {}
    if not args.raw:
        for m in matches:
            reason = m.get("dropped") or below_floor(m, cfg["regions"][m["region"]])
            if reason:
                m["dropped"] = reason
                dropped[reason] = dropped.get(reason, 0) + 1
    matches = [m for m in matches if not m.get("dropped")]
    if not args.no_save:
        save_seen(cfg["state_file"], seen | {m["url"] for m in matches if m["url"]}
                  | {seen_key(m) for m in matches} | seeded)
    if args.new:
        matches = [m for m in matches if m["new"]]

    for m in matches:
        m["region_label"] = cfg["regions"][m["region"]]["label"]
    if args.json:
        json.dump(matches, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        print_text(matches, regions)

    print(f"\n{len(matches)} Stellen aus {len(cfg['companies']) - len(dead)} aktiven Feeds "
          f"({len(dead)} ohne Ergebnis"
          + (f": {', '.join(dead[:8])}{'...' if len(dead) > 8 else ''}" if dead else "") + ")."
          + (" Aussortiert: " + ", ".join(f"{n} {why}" for why, n in dropped.items()) + "."
             if dropped else "")
          + (f" {len(cfg['manual_check'])} Firmen von Hand prüfen: "
             + ", ".join(cfg["manual_check"]) if cfg["manual_check"] else ""),
          file=sys.stderr)
    return 0


def print_text(matches, regions):
    if not matches:
        print("Keine passenden Stellen.")
    for region in regions:
        here = [m for m in matches if m["region"] == region["name"]]
        if not here:
            continue
        print(f"\n=== {region['label']} — {len(here)} Stellen ===")
        for m in sorted(here, key=lambda m: (not m["new"], m["company"].lower())):
            flag = "NEU " if m["new"] else "    "
            extra = f'  [{m["salary"]}]' if m["salary"] else ""
            if m.get("source", "feed") != "feed":
                extra += f'  über {m["source"]}'
            if m.get("note"):
                extra += f'  ({m["note"]})'
            print(f'{flag}{m["company"][:14]:14} | {m["title"][:58]:58} | '
                  f'{m["location"][:28]}{extra}')
            if m["url"]:
                print(f'{"":18} {m["url"]}')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in COMMANDS:
        command, rest = argv[0], argv[1:]
        if command == "init":
            from .wizard import init
            return init(rest)
        if command == "add-company":
            from .wizard import add_company
            return add_company(rest)
        if command == "check":
            from .wizard import check
            return check(rest)
        if command == "probe":
            from .wizard import probe
            return probe(rest)
        if command == "fetch-ad":
            from .fetch_ad import main as fetch_main
            return fetch_main(rest)
    return run(argv)
