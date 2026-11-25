"""Belege per Checkliste bestätigen, statt profile/evidence.md von Hand zu ändern.

    python -m jobwatch.belege checkliste <branch> [--only E12,E13]   # Kommentar mit Checkliste
    python -m jobwatch.belege anwenden <kommentar.md> [--draft-cv <datei>] [--scope-boxes]

`checkliste` liest profile/evidence.md und gibt einen Kommentar aus: ein
Kästchen pro Beleg, angehakt = bestätigt. Eine unsichtbare Markierung nennt den
Zweig des Entwurfs, damit der Workflow «Belege bestätigen» weiss, wohin er
schreibt.

`anwenden` liest den (vom Menschen abgehakten) Kommentar und setzt in
profile/evidence.md jeden aufgeführten Beleg auf [bestätigt] oder
[unbestätigt]. Danach wird profile/cv.yaml angeglichen: Punkte und Kenntnisse,
deren Belege alle unbestätigt sind, kommen aus dem Lebenslauf heraus (es wird
nur weggelassen, nie etwas dazuerfunden). Wird ein Beleg später doch angehakt,
holt `--draft-cv` (der ursprüngliche Entwurf) den Punkt zurück.

Für eine Ergänzung (Formular «Profil ergänzen», Zweig `ergaenzen/…`) enthält
die Checkliste nur die neuen Belege (`--only`). Mit `--scope-boxes` betrifft
das Angleichen von profile/cv.yaml dann nur Punkte, Kenntnisse und Kurse, die
einen dieser Belege zitieren; alle anderen bleiben genau, wie sie sind.
"""

import argparse
import re
import sys

import yaml

from .profile import ITEM, is_confirmed, parse_evidence

MARKER = "<!-- jobhunter:belege branch={branch} -->"
MARKER_RE = re.compile(r"<!-- jobhunter:belege branch=([\w./-]+) -->")
BOX = re.compile(r"^\s*-\s+\[([ xX])\]\s+\*\*(E\d+)\*\*")
STATUS_TAG = re.compile(r"\[\s*(?:un)?best(?:ä|ae)tigt\s*\]\s*", re.IGNORECASE)


DRAFT_SOURCE = re.compile(r"\s*Quelle: (?:Lebenslauf \(Entwurf\)|Formular «Profil ergänzen»)\.?$")


def checklist(evidence_text, branch, only=None):
    data = parse_evidence(evidence_text)
    roles = data["roles"]
    items = [i for i in data["items"].values() if only is None or i["id"] in only]
    lines = [MARKER.format(branch=branch),
             "## Belege bestätigen",
             "",
             "Hake jeden Punkt an, der **genau so stimmt**. Gespeichert wird automatisch; "
             "unten erscheint nach etwa einer Minute der Stand. Nach jedem Häkchen kurz "
             "warten, bis es sitzt: Sehr schnelle Klicks hintereinander übernimmt GitHub "
             "manchmal nicht.",
             "",
             "- **Nicht angehakt** heisst: kommt nicht in deinen Lebenslauf.",
             "- Stimmt etwas nur halb (z. B. übertrieben)? Nicht anhaken. Korrigieren "
             "kannst du es später im Entwurf (Datei `profile/evidence.md`, Stift-Symbol).",
             ""]
    if only is not None:
        lines += ["Hier stehen nur die **neuen** Einträge. Deine bisherigen Belege bleiben, "
                  "wie sie sind.", ""]
    current = object()
    for item in items:
        if item["role"] != current:
            current = item["role"]
            role = roles.get(current)
            heading = (f"{role['title']}, {role['org']}" if role else "Kenntnisse und Sprachen")
            lines += ["", f"**{heading}**", ""]
        mark = "x" if is_confirmed(item) else " "
        text = DRAFT_SOURCE.sub("", item["text"]).strip()
        lines.append(f"- [{mark}] **{item['id']}** {text}")
    lines += ["", "<sub>Fortgeschritten: Markierungen wie `[hobby]` oder `[level: basic]` "
              "trägst du direkt in `profile/evidence.md` ein (siehe GUARDRAILS.md).</sub>"]
    return "\n".join(lines) + "\n"


def parse_boxes(comment_text):
    """{E-ID: True/False} aus einem abgehakten Kommentar."""
    return {m.group(2): m.group(1).lower() == "x"
            for m in (BOX.match(line) for line in comment_text.splitlines()) if m}


def branch_of(comment_text):
    hit = MARKER_RE.search(comment_text or "")
    return hit.group(1) if hit else None


def apply_to_evidence(evidence_text, boxes):
    out = []
    for line in evidence_text.splitlines():
        hit = ITEM.match(line)
        if hit and hit.group(1) in boxes:
            eid = hit.group(1)
            tag = "[bestätigt]" if boxes[eid] else "[unbestätigt]"
            start = line.index(eid) + len(eid)
            colon = line.index(":", start)
            tags = STATUS_TAG.sub("", line[start:colon]).strip()
            line = f"{line[:start]} {tag}{(' ' + tags) if tags else ''}{line[colon:]}"
        out.append(line)
    return "\n".join(out) + ("\n" if evidence_text.endswith("\n") else "")


def _ok(entry, confirmed):
    ids = entry.get("evidence") or []
    return bool(ids) and all(i in confirmed for i in ids)


def _merge(current, drafted, key, confirmed, scope):
    """Liste angleichen: Einträge im Geltungsbereich nur, wenn alle Belege bestätigt sind
    (wieder bestätigte kommen aus dem Entwurf zurück); Einträge ausserhalb bleiben, wie sie
    sind (ohne Geltungsbereich gilt alles als darin)."""
    def k(i, entry):
        return key(entry) if key(entry) is not None else ("#", i)
    have = {k(i, e): e for i, e in enumerate(current or []) if isinstance(e, dict)}
    pool = {k(i, e): e for i, e in enumerate(drafted or []) if isinstance(e, dict)}
    order = list(pool) + [c for c in have if c not in pool]
    pool.update(have)

    def keep(c):
        entry = pool[c]
        if scope is not None and not set(entry.get("evidence") or []) & scope:
            return c in have
        return _ok(entry, confirmed)
    return [pool[c] for c in order if keep(c)]


def align_cv(cv, draft, confirmed, scope=None):
    """Nur bestätigte Punkte/Kenntnisse behalten; wieder bestätigte aus dem Entwurf zurückholen.

    `scope` (Menge von Beleg-IDs, z. B. die neuen einer Ergänzung): nur Einträge, die einen
    dieser Belege zitieren, werden angeglichen, dann auch Kurse unter `education:`."""
    draft = draft or {}
    draft_roles = {r.get("id"): r for r in draft.get("experience") or []}
    for role in cv.get("experience") or []:
        drafted = (draft_roles.get(role.get("id")) or {}).get("bullets") or []
        if scope is not None and role.get("bullets") is None and not drafted:
            continue
        role["bullets"] = _merge(role.get("bullets"), drafted, lambda b: b.get("id"),
                                 confirmed, scope)
    if scope is not None and cv.get("skills") is None and not draft.get("skills"):
        return cv
    cv["skills"] = _merge(cv.get("skills"), draft.get("skills"), lambda s: s.get("category"),
                          confirmed, scope)
    if scope is not None and (cv.get("education") or draft.get("education")):
        cv["education"] = _merge(cv.get("education"), draft.get("education"),
                                 lambda e: (e.get("degree"), e.get("school")), confirmed, scope)
    return cv


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jobwatch.belege", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("checkliste")
    s1.add_argument("branch")
    s1.add_argument("--evidence", default="profile/evidence.md")
    s1.add_argument("--only", default="", help="nur diese Beleg-IDs (kommagetrennt)")
    s2 = sub.add_parser("anwenden")
    s2.add_argument("comment")
    s2.add_argument("--evidence", default="profile/evidence.md")
    s2.add_argument("--cv", default="profile/cv.yaml")
    s2.add_argument("--draft-cv", default="")
    s2.add_argument("--scope-boxes", action="store_true",
                    help="cv.yaml nur für Einträge angleichen, die Belege der Checkliste zitieren")
    s3 = sub.add_parser("zweig")
    s3.add_argument("comment")
    args = parser.parse_args(argv)

    if args.cmd == "checkliste":
        only = {i.strip() for i in args.only.split(",") if i.strip()} or None
        sys.stdout.write(checklist(open(args.evidence, encoding="utf-8").read(), args.branch, only))
        return 0
    comment = open(args.comment, encoding="utf-8").read()
    if args.cmd == "zweig":
        branch = branch_of(comment)
        if not branch:
            return 1
        print(branch)
        return 0
    boxes = parse_boxes(comment)
    evidence = open(args.evidence, encoding="utf-8").read()
    evidence = apply_to_evidence(evidence, boxes)
    open(args.evidence, "w", encoding="utf-8").write(evidence)
    items = parse_evidence(evidence)["items"]
    confirmed = {i for i, item in items.items() if is_confirmed(item)}
    cv_text = open(args.cv, encoding="utf-8").read()
    draft_text = open(args.draft_cv, encoding="utf-8").read() if args.draft_cv else ""
    if args.scope_boxes:
        # Ergänzung: nur die neuen, einzeiligen Einträge angleichen; der Rest der
        # Datei (mit Kommentaren) bleibt Zeichen für Zeichen, wie er ist.
        from .cvtext import align
        open(args.cv, "w", encoding="utf-8").write(
            align(cv_text, draft_text, confirmed, set(boxes)))
    else:
        header = ""
        for line in cv_text.splitlines():
            if not line.startswith("#"):
                break
            header += line + "\n"
        cv = yaml.safe_load(cv_text) or {}
        draft = yaml.safe_load(draft_text) if draft_text else {}
        cv = align_cv(cv, draft, confirmed)
        with open(args.cv, "w", encoding="utf-8") as fh:
            fh.write(header + ("\n" if header else ""))
            yaml.safe_dump(cv, fh, allow_unicode=True, sort_keys=False, width=100)
    total = len(boxes)
    yes = sum(boxes.values())
    print(f"{yes} von {total} Belegen bestätigt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
