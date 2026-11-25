"""jobhunter.yml laden und prüfen.

Alles Persönliche steht in der Konfigurationsdatei, nie im Code: wonach und wo
gesucht wird, welche Firmen beobachtet werden, wer ausgeschlossen ist oder wo
schon eine Bewerbung läuft, die Kündigungsfrist. Der Code enthält nur
vernünftige Standardwerte.

    python -m jobwatch.config get agent          # einen Wert ausgeben (Pfad mit Punkten)
    python -m jobwatch.config get state_file     # aufgelöster absoluter Pfad
"""

import difflib
import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - only without PyYAML
    yaml = None

DEFAULT_PATHS = ("jobhunter.yml", "jobhunter.yaml")
EXAMPLE = "jobhunter.example.yml"

# Plain words, matched case-insensitively anywhere in the title. Words of three
# letters or fewer only match as whole words ("ai" must not match "maintain").
# Prefix an entry with "re:" to write a Python regular expression instead.
DEFAULT_KEYWORDS = ["engineer", "developer", "development", "software", "frontend",
                    "front-end", "fullstack", "full-stack", "backend", "back-end",
                    "architect", "platform", "programmer", "ai", "llm", "genai"]
DEFAULT_SENIORITY = ["senior", "lead", "head", "principal", "staff", "architect",
                     "manager", "director", "chief", "cto", "vp"]
# Noise that board searches for "engineer" drag in. Applied in addition to your
# own `avoid:` words unless advanced.noise_filter is false.
NOISE = ["sales", "account executive", "account manager", "business development",
         "recruit", "marketing", "customer success", "presales", "pre-sales",
         "technical account", "mechanical", "electrical", "hardware", "firmware",
         "chemical", "process engineer", "field engineer", "support engineer",
         "re:\\bintern\\b", "internship", "graduate", "product manager",
         "program manager", "project manager", "product owner", "data analyst",
         "civil", "structural", "hvac", "building services", "construction",
         "surveyor", "sap", "servicenow"]
CONTRACT = ["re:(?<!smart )\\bcontract\\b", "contractor", "temporary", "fixed-term",
            "fixed term", "payroll partner", "interim", "freelance",
            "re:\\b\\d{1,2}[- ]?months?\\b"]
DEFAULT_QUERIES = {
    "lead": ["tech lead", "engineering manager", "software architect", "principal engineer",
             "staff engineer", "lead software engineer", "head of engineering"],
    "broad": ["software engineer", "fullstack developer", "backend engineer"],
}

# Every key the file may contain, so a typo is reported instead of ignored.
SCHEMA = {
    "search": {"keywords", "seniority", "avoid", "contract_ok", "remote_ok"},
    "locations": None,          # list, checked separately
    "companies": None,          # list
    "ruled_out": None, "pending": None, "applied": None, "manual_check": None,
    "profile": {"name", "evidence", "target", "cv", "notice", "salary_expectation",
                "workload", "onsite_days", "work_permit", "non_compete", "languages", "cv_style"},
    "reminders": {"enabled", "follow_up_days", "deadline_days"},
    "board": {"enabled", "owner", "number", "status_field"},
    "retention": {"enabled", "months", "mode"},
    "notifications": {"email_to"},
    "documents": {"store_certificates"},
    "agent": None,
    "copilot_cli": {"model"},
    # Veraltet (GitHub Models wurde am 30.07.2026 eingestellt): werden noch
    # akzeptiert, damit ältere jobhunter.yml gültig bleiben, aber ignoriert.
    "models": {"model", "max_input_chars", "temperature", "endpoint"},
    "triage": {"enabled", "model", "max_roles"},
    "advanced": {"state_file", "source_backlog", "queries", "noise_filter",
                 "default_locations"},
}
LOCATION_KEYS = {"name", "label", "places", "country", "avoid_places", "remote_ok",
                 "salary_floor", "monthly_below", "boards", "seed_on_first_run"}


class ConfigError(Exception):
    pass


# Wer Bewerbungspakete und den Profil-Entwurf schreibt (jobhunter.yml: agent:).
# "none" heisst im Formular «lokal», weil GitHub «None» als Option verbietet.
AGENTS = ("kopieren", "copilot-cli", "copilot", "claude", "none")
DEFAULT_AGENT = "kopieren"
AGENT_ALIASES = {"lokal": "none", "local": "none", "copilot_cli": "copilot-cli",
                 "copilotcli": "copilot-cli", "copy": "kopieren", "kopieren&einfügen": "kopieren"}
MODELS_RETIRED = (
    "agent: models wird nicht mehr unterstützt: GitHub Models wurde am 30.07.2026 "
    "eingestellt (Katalog, Playground und Schnittstelle sind abgeschaltet). Neuer "
    "Standard ist agent: kopieren (Kopieren & Einfügen in einen Chat wie claude.ai "
    "oder ChatGPT, gratis, kein Secret). Mit KI direkt in GitHub: agent: copilot-cli "
    "(GitHub Copilot CLI, gratis mit Copilot Free, begrenztes Kontingent). Weitere "
    "Möglichkeiten: copilot, claude oder lokal. In jobhunter.yml «agent: kopieren» "
    "oder «agent: copilot-cli» setzen oder das Formular «Einrichtung» erneut ausfüllen "
    "(docs/FORTGESCHRITTEN.md, Abschnitt «Was kostet das?»).")


def parse_agent(value):
    """Wert von agent: (auch aus dem Formular) prüfen und normalisieren.

    `models` war bis zur Einstellung von GitHub Models der Standard und gibt
    jetzt eine verständliche Fehlermeldung statt eines stillen Ausfalls."""
    text = str(value or DEFAULT_AGENT).strip().lower()
    text = text.split()[0] if text else DEFAULT_AGENT
    agent = AGENT_ALIASES.get(text, text)
    if agent == "models":
        raise ConfigError(MODELS_RETIRED)
    if agent not in AGENTS:
        raise ConfigError(f"agent: '{text}' ist keiner von kopieren, copilot-cli, copilot, "
                          "claude, lokal (none)")
    return agent


def find_config(path=None):
    candidates = [path] if path else [os.environ.get("JOBHUNTER_CONFIG"), *DEFAULT_PATHS]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    if path:
        raise ConfigError(f"Konfigurationsdatei nicht gefunden: {path}")
    raise ConfigError("keine jobhunter.yml gefunden. Erstellen mit\n"
                      "    python -m jobwatch init\n"
                      f"oder das Beispiel kopieren: cp {EXAMPLE} jobhunter.yml")


def word_pattern(word):
    word = str(word).strip()
    if word.startswith("re:"):
        return word[3:]
    escaped = re.escape(word).replace(r"\ ", r"[\s-]?").replace(r"\-", r"[\s-]?")
    # Umlaute tolerant: "Zürich" findet auch "Zurich" und "Zuerich".
    for umlaut, plain in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("Ä", "A"), ("Ö", "O"), ("Ü", "U")):
        escaped = escaped.replace(umlaut, f"(?:{umlaut}|{plain}e|{plain})")
    return rf"\b{escaped}\b" if len(word) <= 3 else escaped


def compile_words(words, where="config"):
    """Compile plain words (or re: patterns) into one case-insensitive regex."""
    patterns = [word_pattern(w) for w in (words or []) if str(w).strip()]
    if not patterns:
        return None
    try:
        return re.compile("|".join(f"(?:{p})" for p in patterns), re.I)
    except re.error as exc:
        raise ConfigError(f"{where}: ungültiges Muster ({exc}). Normale Wörter brauchen kein "
                          "Escaping; nur Einträge mit 're:' am Anfang sind reguläre Ausdrücke.") from exc


def compile_any(fragments):
    """Compile raw regex fragments (used for board options)."""
    fragments = [f for f in (fragments or []) if f]
    return re.compile("|".join(f"(?:{f})" for f in fragments), re.I) if fragments else None


# --- companies ---------------------------------------------------------------

URL_PATTERNS = [
    # (ats, regex on the URL; group 1 is the slug)
    ("greenhouse", r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([\w.-]+)"),
    ("greenhouse", r"boards-api\.greenhouse\.io/v1/boards/([\w.-]+)"),
    ("lever", r"jobs\.(?:eu\.)?lever\.co/([\w.-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([\w.%-]+)"),
    ("personio", r"([\w-]+)\.jobs\.personio\.(?:com|de)"),
    ("recruitee", r"([\w-]+)\.recruitee\.com"),
    ("teamtailor", r"([\w-]+)\.teamtailor\.com"),
    ("bamboohr", r"([\w-]+)\.bamboohr\.com"),
    ("breezy", r"([\w-]+)\.breezy\.hr"),
    ("workable", r"apply\.workable\.com/([\w-]+)"),
    ("smartrecruiters", r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)"),
    ("workday", r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)"),
]


def feed_from_url(url):
    """Detect the ATS from a careers URL. Returns {ats, slug, name} or None."""
    for ats, pattern in URL_PATTERNS:
        hit = re.search(pattern, url)
        if not hit:
            continue
        if ats == "workday":
            tenant, pod, site = hit.groups()
            return {"ats": ats, "slug": f"{tenant}/{pod}/{site}", "name": tenant}
        slug = hit.group(1)
        if slug in ("embed", "v1", "careers", "jobs", "www"):
            continue
        return {"ats": ats, "slug": slug, "name": None}
    return None


def parse_company(item, index=0):
    """A company is a careers URL, the short form "ats:slug", or {ats, slug, name}."""
    where = f"companies[{index}]"
    if isinstance(item, str):
        if item.startswith("http"):
            feed = feed_from_url(item)
            if not feed:
                raise ConfigError(f"{where}: unklar, welches Bewerbungssystem {item} nutzt. "
                                  "Versuche `python -m jobwatch add-company <url>` oder schreibe "
                                  "'greenhouse:slug' (Liste in jobhunter.example.yml).")
            return feed
        ats, sep, slug = item.partition(":")
        if not sep or not slug:
            raise ConfigError(f"{where}: {item!r} muss eine Karriere-URL sein oder so aussehen: "
                              "'greenhouse:acme'")
        return {"ats": ats.strip(), "slug": slug.strip(), "name": None}
    if isinstance(item, dict) and "ats" in item and "slug" in item:
        return {"ats": str(item["ats"]), "slug": str(item["slug"]), "name": item.get("name")}
    raise ConfigError(f"{where}: braucht 'ats' und 'slug' (erhalten: {item!r})")


# --- loading -----------------------------------------------------------------

def _suggest(key, allowed):
    close = difflib.get_close_matches(key, sorted(allowed), n=1)
    return f" Meintest du '{close[0]}'?" if close else ""


def check_keys(raw):
    for key, value in raw.items():
        if key not in SCHEMA:
            raise ConfigError(f"unbekannter Schlüssel '{key}'.{_suggest(key, SCHEMA)} "
                              f"Alle erlaubten Schlüssel stehen in {EXAMPLE}.")
        allowed = SCHEMA[key]
        if allowed and isinstance(value, dict):
            for sub in value:
                if sub not in allowed:
                    raise ConfigError(f"unbekannter Schlüssel '{key}.{sub}'.{_suggest(sub, allowed)} "
                                      f"Erlaubt: {', '.join(sorted(allowed))}.")
    for i, loc in enumerate(raw.get("locations") or []):
        if not isinstance(loc, dict):
            raise ConfigError(f"locations[{i}] braucht mindestens 'name' und 'places'")
        for sub in loc:
            if sub not in LOCATION_KEYS:
                raise ConfigError(f"unbekannter Schlüssel 'locations[{i}].{sub}'."
                                  f"{_suggest(sub, LOCATION_KEYS)} "
                                  f"Erlaubt: {', '.join(sorted(LOCATION_KEYS))}.")


def read_yaml(path):
    if yaml is None:
        raise ConfigError("PyYAML fehlt: pip install -r requirements.txt")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"Zeile {mark.line + 1}, Spalte {mark.column + 1}" if mark else "unbekannter Stelle"
        line = text.splitlines()[mark.line] if mark and mark.line < len(text.splitlines()) else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise ConfigError(f"{path}: YAML-Fehler in {where}: {problem}\n    {line}\n"
                          "Häufige Ursachen: Tabulator statt Leerzeichen, fehlendes Leerzeichen "
                          "nach ':' oder '-', oder ein Wert mit ': ' ohne Anführungszeichen.") from exc


def load(path=None):
    """Read the config file and return a normalised dict."""
    path = find_config(path)
    return normalise(read_yaml(path), base_dir=os.path.dirname(path), path=path)


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def normalise(raw, base_dir=".", path="<memory>"):
    if not isinstance(raw, dict):
        raise ConfigError("die Konfiguration muss aus 'schlüssel: wert'-Zeilen bestehen")
    check_keys(raw)
    search = raw.get("search") or {}
    advanced = raw.get("advanced") or {}
    cfg = {"_path": path, "_base_dir": base_dir}

    state = advanced.get("state_file") or ".jobwatch/seen.json"
    cfg["state_file"] = state if os.path.isabs(state) else os.path.join(base_dir, state)
    cfg["source_backlog"] = int(advanced.get("source_backlog") or 40)
    # Jobbörsen-Suchbegriffe: ohne eigene advanced.queries die Wunschtitel aus
    # search.keywords, damit auch Nicht-Tech-Berufe (z. B. Pflege) Treffer finden.
    own = [k for k in _as_list(search.get("keywords")) if not str(k).startswith("re:")]
    defaults = {"lead": own, "broad": []} if own else DEFAULT_QUERIES
    cfg["queries"] = {**defaults, **(advanced.get("queries") or {})}

    avoid = _as_list(search.get("avoid"))
    if advanced.get("noise_filter", True):
        avoid = avoid + NOISE
    seniority = search.get("seniority", DEFAULT_SENIORITY)
    cfg["search"] = {"keywords": _as_list(search.get("keywords")) or DEFAULT_KEYWORDS,
                     "seniority": _as_list(seniority), "avoid": avoid,
                     "contract_ok": bool(search.get("contract_ok", False)),
                     "remote_ok": bool(search.get("remote_ok", False))}
    cfg["_re"] = {
        "include": compile_words(cfg["search"]["keywords"], "search.keywords"),
        "exclude": compile_words(avoid, "search.avoid"),
        "seniority": compile_words(cfg["search"]["seniority"], "search.seniority"),
        "contract": None if cfg["search"]["contract_ok"] else compile_words(CONTRACT),
        "remote": re.compile(r"remote|home ?office|work from home|anywhere", re.I),
    }

    locations = raw.get("locations") or []
    if not locations:
        raise ConfigError("unter 'locations:' fehlt mindestens ein Eintrag "
                          "(z. B. name: zurich, places: [Zürich, Zug])")
    regions = {}
    for i, loc in enumerate(locations):
        name = str(loc.get("name") or f"location{i + 1}")
        if name in regions:
            raise ConfigError(f"locations[{i}]: Name '{name}' kommt doppelt vor")
        floors = []
        for floor in _as_list(loc.get("salary_floor")):
            if isinstance(floor, (int, float)):
                floor = {"yearly": floor}
            if not isinstance(floor, dict) or "yearly" not in floor:
                raise ConfigError(f"locations[{i}].salary_floor: eine Zahl (pro Jahr) oder "
                                  "eine Liste wie {yearly: 150000, where: 'new york'}")
            floors.append({"yearly": float(floor["yearly"]),
                           "where": compile_words([floor["where"]]) if floor.get("where") else None})
        regions[name] = {
            "name": name,
            "label": loc.get("label") or name.replace("_", " ").title(),
            "boards": _as_list(loc.get("boards")),
            "places": _as_list(loc.get("places")),
            "seed_on_first_run": loc.get("seed_on_first_run", False),
            "remote_ok": bool(loc.get("remote_ok", cfg["search"]["remote_ok"])),
            "monthly_below": float(loc.get("monthly_below") or 0),
            "_floors": floors,
            "_re": {"locations": compile_words(_as_list(loc.get("places")), f"locations[{i}].places"),
                    "country": compile_words(_as_list(loc.get("country")), f"locations[{i}].country"),
                    "exclude_locations": compile_words(_as_list(loc.get("avoid_places")),
                                                       f"locations[{i}].avoid_places"),
                    "remote": cfg["_re"]["remote"]
                    if loc.get("remote_ok", cfg["search"]["remote_ok"]) else None},
        }
    cfg["regions"] = regions
    default_regions = _as_list(advanced.get("default_locations")) or list(regions)
    unknown = [r for r in default_regions if r not in regions]
    if unknown:
        raise ConfigError(f"advanced.default_locations nennt unbekannte Orte: {unknown}")
    cfg["default_regions"] = default_regions

    cfg["companies"] = [parse_company(c, i) for i, c in enumerate(_as_list(raw.get("companies")))]

    for key in ("ruled_out", "pending", "applied", "manual_check"):
        value = raw.get(key) or {}
        if isinstance(value, list):
            value = {str(v): "" for v in value}
        if not isinstance(value, dict):
            raise ConfigError(f"'{key}' muss eine Liste oder 'name: notiz'-Zeilen sein")
        cfg[key] = {(str(k).lower() if key in ("ruled_out", "pending") else str(k)): (v or "")
                    for k, v in value.items()}
    cfg["applied_urls"] = cfg.pop("applied")

    # Ein veraltetes `agent: models` darf die tägliche Stellensuche nicht
    # stoppen: Die Fehlermeldung wird gemerkt und dort gezeigt, wo ein
    # Assistent gebraucht wird (Bewerbungspaket, Profil, Status-Issue).
    cfg["agent_error"] = ""
    try:
        cfg["agent"] = parse_agent(raw.get("agent"))
    except ConfigError as exc:
        if str(raw.get("agent") or "").strip().lower() != "models":
            raise
        cfg["agent"], cfg["agent_error"] = "models", str(exc)
    cfg["copilot_cli"] = {"model": "", **(raw.get("copilot_cli") or {})}
    cfg["deprecated"] = [key for key in ("models", "triage") if key in raw]
    cfg["reminders"] = {"enabled": True, "follow_up_days": 14, "deadline_days": 2,
                        **(raw.get("reminders") or {})}
    cfg["board"] = {"enabled": False, "owner": "", "number": 0, "status_field": "Status",
                    **(raw.get("board") or {})}
    cfg["retention"] = {"enabled": False, "months": 12, "mode": "archive",
                        **(raw.get("retention") or {})}
    cfg["documents"] = {"store_certificates": False, **(raw.get("documents") or {})}
    cfg["profile"] = {"evidence": "profile/evidence.md", "target": "profile/target.md",
                      "notice": {"months": 3, "until": "month_end"},
                      **(raw.get("profile") or {})}
    return cfg


def get(cfg, dotted):
    value = cfg
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def main(argv=None):
    import argparse
    import json

    parser = argparse.ArgumentParser(prog="python -m jobwatch.config", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="Pfad zu jobhunter.yml")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("get").add_argument("key")
    args = parser.parse_args(argv)
    try:
        cfg = load(args.config)
    except ConfigError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    value = get(cfg, args.key)
    if value is None:
        return 1
    print(value if isinstance(value, (str, int, float)) else json.dumps(value, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
