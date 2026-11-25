"""Einsteigerfreundliche Befehle: init, add-company, check, probe."""

import argparse
import concurrent.futures as futures
import os
import re
import sys
import unicodedata

from . import adapters
from .config import ConfigError, feed_from_url, find_config, load, parse_agent

INIT_TEMPLATE = """\
# jobhunter.yml — erstellt mit `python -m jobwatch init`.
# Jeder Schlüssel ist in jobhunter.example.yml erklärt. Frei anpassen und
# danach mit `python -m jobwatch check` prüfen.

# ── 1. Wonach du suchst ─────────────────────────────────────────────────────
search:
  # Ein Stellentitel muss eines dieser Wörter enthalten (Gross/klein egal).
  keywords: {keywords}
  # ...und eines dieser, ausser mit --all. [] = jede Stufe.
  seniority: {seniority}
  # Titel mit diesen Wörtern nie anzeigen.
  avoid: {avoid}
  # Voll-Remote-Stellen im Land deiner Orte mitzählen.
  remote_ok: {remote_ok}

# ── 2. Wo ───────────────────────────────────────────────────────────────────
locations:
  - name: {loc_name}
    # Städte oder Regionen, in die du pendeln kannst. Normale Wörter.
    places: {places}
    # Ein Inserat, das nur das Land nennt, zählt auch.
    country: {country}
{boards}
# ── 3. Firmen, die du beobachtest ───────────────────────────────────────────
# Karriereseiten-URLs einfügen (Greenhouse, Lever, Ashby, Personio,
# Teamtailor, Workday, ...) oder `python -m jobwatch add-company <url>`.
companies:
{companies}

# ── 4. Eigene Buchhaltung (bleibt in deinem privaten Repository) ──────────────────
ruled_out: {{}}     # firma: grund        — wird ausgeblendet
pending: {{}}       # firma: notiz        — wird markiert, nicht ausgeblendet
applied: {{}}       # inserat-URL: notiz  — wird ausgeblendet

# ── 5. Fakten, die kein Agent je raten darf ─────────────────────────────────
profile:
  notice: {{months: {notice}, until: month_end}}   # Kündigungsfrist; until: month_end | any_day
  salary_expectation: {salary}       # Lohnvorstellung — entscheidest nur du
  workload: {workload}             # Pensum
  work_permit: {permit}          # Arbeitsbewilligung/Staatsbürgerschaft, nur wo relevant

# Wer Bewerbungspakete entwirft: kopieren (Standard, gratis: Auftrag in einen Chat
# wie claude.ai oder ChatGPT kopieren, Antwort mit /paket zurück), copilot-cli
# (GitHub Copilot CLI in Actions, gratis mit Copilot Free, begrenzt), copilot
# (Coding-Agent, ab Copilot Pro), claude (Secret ANTHROPIC_API_KEY) oder none
# (lokal, ohne KI in GitHub).
# Siehe docs/FORTGESCHRITTEN.md, Abschnitt «Was kostet das?».
agent: {agent}
"""


def render_config(keywords, seniority, avoid, places, country, remote, notice=3,
                  companies=(), salary="", workload="100%", permit="", agent="kopieren"):
    """Neue jobhunter.yml als Text (mit Kommentaren). Gibt (text, unbekannte URLs) zurück."""
    feeds, unknown = [], []
    for url in companies:
        feed = feed_from_url(url) if url.startswith("http") else None
        if feed:
            feeds.append(f"  - {feed['ats']}:{feed['slug']}")
        elif ":" in url and not url.startswith("http"):
            feeds.append(f"  - {url}")
        else:
            unknown.append(url)
    quote = lambda v: '"' + str(v).replace('"', "'") + '"'
    text = INIT_TEMPLATE.format(
        keywords=_flow(keywords), seniority="[]" if not seniority else _flow(seniority),
        avoid=_flow(avoid), remote_ok="true" if remote else "false",
        loc_name=re.sub(r"[^a-z0-9]+", "_", unicodedata.normalize("NFKD", (places or ["home"])[0])
                        .encode("ascii", "ignore").decode().lower()).strip("_") or "home",
        places=_flow(places), country=_flow(country),
        boards=_boards(country, places),
        companies="\n".join(feeds) if feeds else "  []", notice=int(notice),
        salary=quote(salary), workload=quote(workload), permit=quote(permit), agent=agent)
    if not feeds:
        text = text.replace("companies:\n  []", "companies: []")
    return text, unknown


def _boards(country, places):
    """Für die Schweiz jobs.ch einschalten: dort stehen die meisten Stellen."""
    swiss = any(c.strip().lower() in ("schweiz", "switzerland", "suisse", "svizzera", "ch")
                for c in country or [])
    if not swiss:
        return ""
    return ("    # Jobbörse jobs.ch, durchsucht mit deinen Stichwörtern an deinen Orten.\n"
            "    boards:\n"
            "      - board: jobs.ch\n"
            f"        where: {_flow(places)}\n")


def _ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def _flow(items):
    quoted = []
    for item in items:
        item = item.strip()
        if item:
            quoted.append(item if re.fullmatch(r"[\w .&/+-]+", item) and ": " not in item
                          else '"' + item.replace('"', '\\"') + '"')
    return "[" + ", ".join(quoted) + "]"


def _split(text):
    return [p.strip() for p in re.split(r"[,;\n]", text) if p.strip()]


def init(argv):
    parser = argparse.ArgumentParser(prog="python -m jobwatch init",
                                     description="Ein paar Fragen beantworten und jobhunter.yml schreiben.")
    parser.add_argument("--output", default="jobhunter.yml")
    parser.add_argument("--force", action="store_true", help="bestehende Datei überschreiben")
    args = parser.parse_args(argv)
    if os.path.exists(args.output) and not args.force:
        print(f"{args.output} existiert bereits; mit --force überschreiben.", file=sys.stderr)
        return 1

    print("Sechs Fragen. Mehrere Antworten mit Komma trennen; Enter übernimmt den Vorschlag.\n")
    keywords = _ask("1. Wörter, die ein passender Stellentitel enthält",
                    "engineer, developer, architect, software")
    seniority = _ask("2. Wörter für die Stufe (oder 'any' für alle)", "senior, lead, staff, principal, head")
    places = _ask("3. Städte/Regionen, in denen du arbeiten kannst", "Zürich, Zug, Winterthur")
    country = _ask("   ...und das Land", "Schweiz, Switzerland")
    avoid = _ask("4. Wörter, die im Titel nicht vorkommen dürfen", "sales, praktikum, intern")
    companies = _ask("5. Karriereseiten-URLs von Firmen, die du beobachten willst (optional)", "")
    remote = _ask("   Voll-Remote-Stellen in diesem Land mitzählen? (j/n)", "j")
    notice = _ask("   Deine Kündigungsfrist in Monaten", "3")
    while True:
        answer = _ask("6. Assistent für Bewerbungspakete: kopieren (gratis, Kopieren & Einfügen "
                      "in deinen Chat), copilot-cli (gratis mit Copilot Free, begrenzt), copilot "
                      "(ab Copilot Pro), claude oder lokal", "kopieren")
        try:
            agent = parse_agent(answer)
            break
        except ConfigError as exc:
            print(f"   {exc}")

    text, unknown = render_config(
        _split(keywords), [] if seniority.lower() == "any" else _split(seniority),
        _split(avoid), _split(places), _split(country), remote.lower()[:1] in ("j", "y"),
        int(notice) if notice.isdigit() else 3, _split(companies), agent=agent)
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"\n{args.output} geschrieben.")
    for url in unknown:
        print(f"  Bewerbungssystem für {url} nicht erkannt; versuche "
              f"`python -m jobwatch add-company {url}` oder `python -m jobwatch probe <name>`.")
    if agent == "copilot-cli":
        print("copilot-cli: im Workflow genügt das eingebaute GITHUB_TOKEN (Copilot-Plan nötig, "
              "Copilot Free reicht); Details in docs/FORTGESCHRITTEN.md, Abschnitt «Copilot CLI».")
    print("Weiter: python -m jobwatch check   dann   python -m jobwatch --no-save")
    return 0


def append_company(path, entry, comment=""):
    """Append one entry to the `companies:` list, keeping comments and layout."""
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    line = f"  - {entry}" + (f"   # {comment}" if comment else "")
    start = next((i for i, l in enumerate(lines) if re.match(r"companies:\s*(#.*)?$", l)
                  or re.match(r"companies:\s*\[\s*\]", l)), None)
    if start is None:
        lines += ["", "companies:", line]
    else:
        if re.match(r"companies:\s*\[\s*\]", lines[start]):
            lines[start] = "companies:"
        end = start + 1
        last_item = start
        while end < len(lines) and (not lines[end].strip() or lines[end].startswith((" ", "\t", "#"))):
            if lines[end].lstrip().startswith("- "):
                last_item = end
            end += 1
        lines.insert(last_item + 1, line)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def add_company(argv):
    parser = argparse.ArgumentParser(prog="python -m jobwatch add-company",
                                     description="Bewerbungssystem aus einer Karriere-URL "
                                                 "erkennen und in jobhunter.yml eintragen.")
    parser.add_argument("url")
    parser.add_argument("--name", help="Anzeigename (Standard: der Slug)")
    parser.add_argument("--config")
    parser.add_argument("--no-ping", action="store_true", help="Feed nicht testen")
    args = parser.parse_args(argv)
    feed = feed_from_url(args.url)
    if not feed:
        slug = re.sub(r"^https?://(www\.)?", "", args.url).split(".")[0].split("/")[0]
        print(f"Bewerbungssystem von {args.url} nicht erkannt.\n"
              f"Versuche: python -m jobwatch probe {slug}\n"
              "Oder auf der Karriereseite eine Stelle öffnen und deren URL verwenden: die "
              "Links verraten meist das System (greenhouse.io, lever.co, ashbyhq.com ...).",
              file=sys.stderr)
        return 1
    try:
        path = find_config(args.config)
        cfg = load(path)
    except ConfigError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    if any(c["ats"] == feed["ats"] and c["slug"] == feed["slug"] for c in cfg["companies"]):
        print(f"{feed['ats']}:{feed['slug']} steht schon in {path}.")
        return 0
    if not args.no_ping:
        name, jobs = adapters.load(feed)
        status = f"OK, {len(jobs)} offene Stellen" if jobs else "nicht bestätigt (0 Stellen oder offline)"
        print(f"{feed['ats']}:{feed['slug']}: {status}")
    entry = f"{feed['ats']}:{feed['slug']}"
    if args.name or feed.get("name"):
        entry = f"{{ats: {feed['ats']}, slug: \"{feed['slug']}\", name: \"{args.name or feed['name']}\"}}"
    append_company(path, entry)
    load(path)   # make sure the file is still valid
    print(f"{entry} in {path} eingetragen.")
    return 0


def agent_lines(cfg):
    """Hinweise zum Assistenten für check/Status-Issue. Ob ein Secret existiert,
    kann Code nicht prüfen; darum steht hier, welches nötig ist."""
    agent, lines = cfg["agent"], []
    if cfg.get("agent_error"):
        lines.append(("fail", cfg["agent_error"]))
    elif agent == "kopieren":
        lines.append(("ok", "agent: kopieren — Aufträge zum Kopieren in deinen Chat, Antwort mit "
                            "/paket bzw. /profil. Keine Secrets nötig."))
    elif agent == "copilot-cli":
        lines.append(("warn", "agent: copilot-cli braucht einen Copilot-Plan auf deinem Konto "
                              "(Copilot Free genügt, Kontingent begrenzt). Normalerweise reicht das "
                              "eingebaute GITHUB_TOKEN; nur falls GitHub es ablehnt, ist das Secret "
                              "COPILOT_GITHUB_TOKEN nötig (docs/FORTGESCHRITTEN.md, Abschnitt «Copilot CLI»)."))
    elif agent == "copilot":
        lines.append(("warn", "agent: copilot braucht Copilot Pro oder höher und das Secret "
                              "COPILOT_ASSIGN_TOKEN; der Profil-Entwurf läuft mit der Copilot CLI."))
    elif agent == "claude":
        lines.append(("warn", "agent: claude braucht das Secret ANTHROPIC_API_KEY; der "
                              "Profil-Entwurf läuft per Kopieren & Einfügen (/profil)."))
    else:
        lines.append(("ok", "agent: lokal — Bewerbungspakete entstehen auf deinem Rechner."))
    if cfg.get("deprecated"):
        lines.append(("warn", f"Veraltete Abschnitte in jobhunter.yml ({', '.join(cfg['deprecated'])}) "
                              "werden ignoriert: GitHub Models wurde eingestellt. Sie können weg."))
    return lines


FIX_HINTS = {
    "greenhouse": "boards.greenhouse.io/<slug> im Browser öffnen; der Slug unterscheidet "
                  "Gross/klein und weicht manchmal vom Firmennamen ab",
    "lever": "jobs.lever.co/<slug> prüfen",
    "ashby": "der Slug ist der Teil nach jobs.ashbyhq.com/; manchmal die Domain (acme.com)",
    "personio": "<slug>.jobs.personio.com prüfen",
    "workday": "mit `python -m jobwatch probe --workday <tenant>` Pod/Site finden",
    "smartrecruiters": "die Firmen-ID unterscheidet Gross/klein",
}


def check(argv):
    parser = argparse.ArgumentParser(prog="python -m jobwatch check",
                                     description="jobhunter.yml prüfen und jeden Feed anpingen.")
    parser.add_argument("--config")
    parser.add_argument("--offline", action="store_true", help="nur prüfen, kein Netzwerk")
    parser.add_argument("--markdown", action="store_true",
                        help="Ergebnis als Markdown für das Status-Issue ausgeben")
    args = parser.parse_args(argv)
    out = []
    try:
        path = find_config(args.config)
        cfg = load(path)
    except ConfigError as exc:
        if args.markdown:
            print(f"## ❌ Einrichtung fehlerhaft\n\n```text\n{exc}\n```\n\n"
                  "Formular «Einrichtung» erneut ausfüllen oder jobhunter.yml korrigieren.")
        else:
            print(f"FEHLER Konfiguration: {exc}", file=sys.stderr)
        return 2
    out.append(("ok", f"Konfiguration {os.path.basename(path)}: {len(cfg['regions'])} Suchgebiet(e), "
                      f"{len(cfg['companies'])} Firmen, Assistent: {cfg['agent']}"))
    out += agent_lines(cfg)
    for name in ("evidence", "target"):
        p = os.path.join(cfg["_base_dir"], cfg["profile"][name])
        out.append(("ok", f"Profil {cfg['profile'][name]} vorhanden") if os.path.exists(p) else
                   ("warn", f"Profil {cfg['profile'][name]} fehlt — Formular «Profil» ausfüllen"))
    unsupported = [c for c in cfg["companies"] if c["ats"] not in adapters.SUPPORTED]
    for c in unsupported:
        out.append(("fail", f"{c['ats']}:{c['slug']}: unbekanntes Bewerbungssystem. Unterstützt: "
                            f"{', '.join(adapters.SUPPORTED)}"))
    feeds = [c for c in cfg["companies"] if c not in unsupported]
    ok_feeds = failed = 0
    if feeds and not args.offline:
        with futures.ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(adapters.load, feeds))
        for feed, (name, jobs) in zip(feeds, results):
            label = f"{feed['ats']}:{feed['slug']}"
            if jobs:
                ok_feeds += 1
                out.append(("ok", f"{label}: {len(jobs)} offene Stellen"))
            else:
                failed += 1
                hint = FIX_HINTS.get(feed["ats"], "python -m jobwatch probe " + feed["slug"])
                out.append(("fail", f"{label}: keine Stellen — offline, falscher Slug oder gerade "
                                    f"keine offenen Stellen. Tipp: {hint}"))
        if failed == len(feeds):
            out.append(("warn", "Alle Feeds fehlgeschlagen: zuerst die Netzwerkverbindung prüfen."))
    if args.markdown:
        bad = failed + len(unsupported)
        icon = "✅" if not bad and not cfg.get("agent_error") else "⚠️"
        print(f"## {icon} Einrichtung ok: {ok_feeds} Firmen erreichbar, {bad} Feeds fehlerhaft\n")
        symbols = {"ok": "✅", "warn": "⚠️", "fail": "❌"}
        for kind, text in out:
            print(f"- {symbols[kind]} {text}")
    else:
        labels = {"ok": "OK     ", "warn": "WARNUNG", "fail": "FEHLER "}
        for kind, text in out:
            print(f"{labels[kind]} {text}")
    return 1 if failed or unsupported else 0


def probe(argv):
    parser = argparse.ArgumentParser(prog="python -m jobwatch probe",
                                     description="Herausfinden, welches Bewerbungssystem eine Firma nutzt.")
    parser.add_argument("slugs", nargs="+", help="mögliche Slugs, z. B. der Firmenname")
    parser.add_argument("--workday", action="store_true",
                        help="Namen als Workday-Tenants behandeln und Pod/Site-Pfade ausprobieren")
    args = parser.parse_args(argv)
    for slug in args.slugs:
        hits = adapters.probe_workday(slug) if args.workday else adapters.probe(slug)
        if args.workday:
            for path, total in hits:
                print(f"{slug}: workday — {total} Stellen. Eintragen: workday:{path}")
        else:
            for ats, count in hits:
                print(f"{slug}: {ats} — {count} Stellen. Eintragen: {ats}:{slug}")
        if not hits:
            print(f"{slug}: kein Feed gefunden")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(check(sys.argv[1:]))
