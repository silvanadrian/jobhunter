"""Ehrlichkeits-Prüfung: jede Aussage muss auf profile/evidence.md zurückgehen.

    python -m jobwatch.guard                                  # Basis: profile/cv.yaml
    python -m jobwatch.guard applications/acme-tech-lead      # ein Bewerbungspaket

Prüft gemäss GUARDRAILS.md, an den Daten (nicht am PDF):

* jede Aussage im Lebenslauf (Zusammenfassung, Punkte, Kenntnisse) nennt unter
  `evidence:` mindestens eine ID, und jede ID existiert in evidence.md;
* kein zitierter Beleg ist [unbestätigt];
* ein Punkt unter einer Rolle zitiert Belege dieser Rolle (oder allgemeine);
* Ausbildungs- und Kurseinträge mit `evidence:` werden gleich geprüft;
* Belege mit [hobby] nur, wenn der Text "Hobby" oder "privat" sagt;
* Belege mit [level: ...] nur, wenn der Text dieses Niveau nennt;
* keine Warnformulierung aus GUARDRAILS.md, ausser der zitierte Beleg enthält
  sie selbst (gilt auch für den Brief);
* in fit.md und prep.md existiert jede Referenz [E12].

Exit-Code 0 = sauber, 4 = Probleme gefunden (als Markdown-Bericht ausgegeben).
"""

import argparse
import os
import re
import sys

from .profile import is_confirmed, is_hobby, parse_evidence

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

MD_REF = re.compile(r"\[(E\d+(?:\s*,\s*E\d+)*)\]")
HOBBY_WORDS = re.compile(r"hobby|privat|freizeit|personal project|side project", re.I)
LEVEL_WORDS = {
    "basic": ["basic", "grundkenntnisse", "grundlagen", "einsteiger"],
    "grundkenntnisse": ["basic", "grundkenntnisse", "grundlagen"],
    "intermediate": ["intermediate", "fortgeschritten", "gute kenntnisse"],
    "fortgeschritten": ["intermediate", "fortgeschritten", "gute kenntnisse"],
}
FALLBACK_RED_FLAGS = ["zero downtime", "world-class", "expert in", "led a team of",
                      "best-in-class", "rockstar", "ninja", "guru", "10x", "first ever",
                      "industry-leading", "seamless", "spearheaded"]


def red_flags(guardrails_path="GUARDRAILS.md"):
    """Phrasen in Backticks im Abschnitt 'Warnformulierungen' von GUARDRAILS.md."""
    try:
        text = open(guardrails_path, encoding="utf-8").read()
    except OSError:
        return FALLBACK_RED_FLAGS
    section = re.search(r"^##[^\n]*warnformulierung[^\n]*\n(.*?)(?=^## |\Z)", text,
                        re.S | re.I | re.M)
    phrases = re.findall(r"`([^`]+)`", section.group(1)) if section else []
    return [p.lower() for p in phrases] or FALLBACK_RED_FLAGS


def load_yaml(path):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def resolve(base, variant):
    """Variante wie cv/lib.typ auflösen. Gibt (claims, problems) zurück.

    claims: Liste von (wo, text, evidence-ids, rolle | None | "letter").
    """
    variant = variant or {}
    claims, problems = [], []
    index = {}
    for role in base.get("experience") or []:
        for b in role.get("bullets") or []:
            index[b.get("id")] = b

    summary = variant.get("summary", base.get("summary"))
    if summary:
        claims.append(("summary", summary.get("text", ""), summary.get("evidence") or [], None))

    roles = {r.get("id"): r for r in base.get("experience") or []}
    entries = variant.get("experience")
    if entries is None:
        entries = [{"role": r.get("id")} for r in base.get("experience") or []]
    for i, entry in enumerate(entries):
        rid = entry.get("role")
        if rid not in roles:
            problems.append(f"experience[{i}]: unbekannte Rolle {rid!r}")
            continue
        bullets = entry.get("bullets", roles[rid].get("bullets") or [])
        for j, b in enumerate(bullets):
            where = f"{rid} Punkt {j + 1}"
            if isinstance(b, str):
                if b not in index:
                    problems.append(f"{where}: unbekannter Punkt {b!r}")
                    continue
                b = index[b]
            if not isinstance(b, dict):
                problems.append(f"{where}: ungültiger Eintrag")
                continue
            claims.append((where, b.get("text", ""), b.get("evidence") or [], rid))

    for s in variant.get("skills", base.get("skills")) or []:
        claims.append((f"Kenntnisse '{s.get('category', '')}'",
                       f"{s.get('category', '')}: {s.get('items', '')}",
                       s.get("evidence") or [], None))

    # Ausbildung/Kurse mit `evidence:` (z. B. aus «Profil ergänzen») sind Aussagen wie Punkte;
    # Einträge ohne diesen Schlüssel bleiben wie bisher ungeprüft.
    for e in variant.get("education", base.get("education")) or []:
        if isinstance(e, dict) and "evidence" in e:
            claims.append((f"Ausbildung '{e.get('degree', '')}'",
                           f"{e.get('degree', '')}, {e.get('school', '')}",
                           e.get("evidence") or [], None))

    letter = variant.get("letter")
    if letter:
        for i, p in enumerate(letter.get("paragraphs") or []):
            claims.append((f"Brief Absatz {i + 1}", p.get("text", ""), p.get("evidence") or [],
                           "letter"))
    return claims, problems


def check_claims(claims, evidence, flags):
    issues = []
    for where, text, ids, role in claims:
        low = text.lower()
        if not ids and role != "letter":
            issues.append(f"{where}: Aussage ohne Beleg (evidence: [...]): {text[:80]}")
        for eid in ids:
            item = evidence["items"].get(eid)
            if item is None:
                issues.append(f"{where}: zitiert {eid}, das nicht in evidence.md steht")
                continue
            if not is_confirmed(item):
                issues.append(f"{where}: {eid} ist [unbestätigt]; erst in evidence.md prüfen "
                              "und auf [bestätigt] setzen")
            if role not in (None, "letter") and item["role"] and item["role"] != role:
                issues.append(f"{where}: Punkt unter {role} zitiert {eid} aus {item['role']}")
            if is_hobby(item) and not HOBBY_WORDS.search(text):
                issues.append(f"{where}: {eid} ist nur ein Hobby-Beleg; das muss im Text stehen "
                              "(z. B. \"(Hobbyprojekte)\")")
            for tag in item["tags"]:
                if tag.startswith("level:"):
                    level = tag.split(":", 1)[1].strip()
                    if not any(w in low for w in LEVEL_WORDS.get(level, [level])):
                        issues.append(f"{where}: {eid} hat Niveau \"{level}\"; der Text muss es "
                                      "nennen (z. B. \"Grundkenntnisse\")")
        for phrase in flags:
            if phrase in low and not any(
                    phrase in evidence["items"].get(i, {}).get("text", "").lower() for i in ids):
                issues.append(f"{where}: Warnformulierung \"{phrase}\" ist durch keinen "
                              "zitierten Beleg gedeckt")
    return issues


def check_markdown(text, evidence, name):
    issues = []
    for number, line in enumerate(text.splitlines(), 1):
        for group in MD_REF.findall(line):
            for eid in re.split(r"[,\s]+", group.strip()):
                if eid and eid not in evidence["items"]:
                    issues.append(f"{name}:{number}: zitiert {eid}, das nicht in evidence.md steht")
    return issues


def check(package=None, base_path="profile/cv.yaml", evidence_path="profile/evidence.md",
          guardrails="GUARDRAILS.md", variant=None):
    """Basis (package=None) oder ein Paket prüfen. Gibt eine Liste von Problemen zurück."""
    try:
        evidence = parse_evidence(open(evidence_path, encoding="utf-8").read())
    except OSError:
        return [f"{evidence_path} nicht gefunden — zuerst aus der Vorlage erstellen"]
    try:
        base = load_yaml(base_path)
    except OSError:
        return [f"{base_path} nicht gefunden"]
    issues = list(evidence["errors"])
    if package and variant is None:
        path = os.path.join(package, "cv.yaml")
        if os.path.exists(path):
            variant = load_yaml(path)
        else:
            issues.append(f"{path} fehlt")
    claims, problems = resolve(base, variant)
    issues += problems + check_claims(claims, evidence, red_flags(guardrails))
    if package:
        for name in ("fit.md", "prep.md"):
            path = os.path.join(package, name)
            if os.path.exists(path):
                issues += check_markdown(open(path, encoding="utf-8").read(), evidence, name)
    return issues


def report(issues):
    if not issues:
        return "Ehrlichkeits-Prüfung bestanden: Jede Aussage zitiert bestätigte Belege; keine Warnformulierungen.\n"
    lines = [f"Ehrlichkeits-Prüfung: {len(issues)} Problem(e). Beheben oder die Aussage streichen — "
             "nie Belege erfinden, die es nicht gibt.", ""]
    lines += [f"- {i}" for i in issues]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jobwatch.guard", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("packages", nargs="*", help="Ordner applications/<slug> (leer = Basis)")
    parser.add_argument("--base", default="profile/cv.yaml")
    parser.add_argument("--evidence", default="profile/evidence.md")
    parser.add_argument("--guardrails", default="GUARDRAILS.md")
    args = parser.parse_args(argv)
    issues = []
    for package in args.packages or [None]:
        found = check(package, args.base, args.evidence, args.guardrails)
        issues += [f"{package or 'Basis'}: {i}" for i in found]
    print(report(issues), end="")
    return 4 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
