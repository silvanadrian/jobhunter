"""Stand einer Bewerbung per Häkchen festhalten, statt `/outcome …` zu tippen.

    python -m jobwatch.stand checkliste applications/acme-tech-lead   # Kommentar mit Checkliste
    python -m jobwatch.stand slug kommentar.md                        # zu welcher Bewerbung?
    python -m jobwatch.stand anwenden kommentar.md                    # Häkchen ins Protokoll

Im Bewerbungs-Issue steht ein Bot-Kommentar «Stand dieser Bewerbung» mit einer
unsichtbaren Markierung (Slug). Hakt die Besitzerin oder der Besitzer ein
Kästchen an, hält `anwenden` denselben Eintrag fest wie der passende
`/outcome`-Befehl (outcome.record, Front Matter `status:`, bei «Eingereicht»
`submitted_at:`).

* Idempotent: Ein Status, der schon im Protokoll steht, wird nicht noch einmal
  eingetragen (auch nicht, wenn er früher per Befehl kam).
* Ein weggenommenes Häkchen ändert nichts: Das Protokoll ist eine Historie.
* Der Status im Front Matter geht nie zurück (z. B. «Eingereicht» nachträglich
  anhaken, wenn «Gespräch» schon festgehalten ist).
* «Zurückgezogen / doch nicht beworben» wird zu `withdrawn`, wenn die
  Bewerbung eingereicht war, sonst zu `skipped`.

Exit-Code von `anwenden`: 0 = etwas festgehalten, 3 = nichts zu tun.
"""

import argparse
import datetime
import os
import re
import sys

from .outcome import FINAL, STATUSES, record, set_front
from .records import parse

MARKER = "<!-- jobhunter:stand slug={slug} -->"
MARKER_RE = re.compile(r"<!-- jobhunter:stand slug=([a-z0-9][\w.-]*) -->")
SLUG_OK = re.compile(r"^[a-z0-9][\w.-]*$")

# (Beschriftung, Erklärung, Status im Protokoll, Notiz). Die Beschriftung ist der Schlüssel.
# Bewerbungsverfahren haben oft mehrere Runden: darum mehrere Gesprächs-Kästchen,
# unterschieden über die Notiz im Protokoll.
BOXES = [
    ("Eingereicht", "erst anhaken, wenn die Firma den Eingang bestätigt hat", "submitted", ""),
    ("1. Gespräch", "Einladung erhalten", "interview", "1. Gespräch"),
    ("2. Gespräch", "", "interview", "2. Gespräch"),
    ("Weitere Runde", "z. B. 3. Gespräch, Fallstudie, Assessment, Probetag", "interview",
     "weitere Runde"),
    ("Angebot erhalten", "", "offer", ""),
    ("Absage erhalten", "", "declined", ""),
    ("Zurückgezogen / doch nicht beworben", "", "withdrawn", ""),
]
ROUNDS = [b[3] for b in BOXES if b[2] == "interview"]
# Welche Protokolleinträge ein Kästchen schon erfüllen (ausser Gesprächen, siehe _done).
SATISFIED_BY = {
    "submitted": {"submitted"},
    "offer": {"offer", "accepted"},
    "declined": {"declined"},
    "withdrawn": {"withdrawn", "skipped"},
}
BOX = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+\*\*(.+?)\*\*")
RANK = {"draft": 0, "ready": 0, "prepared": 0, "submitted": 1, "no-response": 1,
        "interview": 2, "offer": 3, "accepted": 4, "declined": 4, "withdrawn": 4, "skipped": 4}


def _logged(rec):
    return {e["status"] for e in rec["log"]}


def _rounds_done(rec):
    """Welche Gesprächsrunden im Protokoll stehen. Gesprächseinträge ohne erkennbare
    Runde (z. B. per Befehl) zählen der Reihe nach als 1., 2., weitere Runde."""
    done, loose = set(), 0
    for entry in (rec or {}).get("log", []):
        if entry["status"] != "interview":
            continue
        note = entry.get("note", "")
        named = next((r for r in ROUNDS if r in note), None)
        if named:
            done.add(named)
        else:
            loose += 1
    for r in ROUNDS:
        if loose and r not in done:
            done.add(r)
            loose -= 1
    return done


def _done(box, rec, logged=None, rounds=None):
    label, _, status, note = box
    if status == "interview":
        return note in (rounds if rounds is not None else _rounds_done(rec))
    return bool((logged if logged is not None else (_logged(rec) if rec else set()))
                & SATISFIED_BY[status])


def checklist(slug, rec=None):
    """Kommentar «Stand dieser Bewerbung»; was schon im Protokoll steht, ist angehakt."""
    lines = [MARKER.format(slug=slug),
             "## Stand dieser Bewerbung",
             "",
             "Hake an, was passiert ist. Gespeichert wird automatisch; nach etwa einer Minute "
             "bestätigt ein Kommentar den Eintrag. Nach jedem Häkchen kurz warten: Sehr schnelle "
             "Klicks hintereinander übernimmt GitHub manchmal nicht.",
             ""]
    for box in BOXES:
        label, hint = box[0], box[1]
        mark = "x" if rec and _done(box, rec) else " "
        lines.append(f"- [{mark}] **{label}**" + (f" ({hint})" if hint else ""))
    lines += ["",
              "Bei **Absage** und **Zurückgezogen** wird das Issue geschlossen. Ein Häkchen "
              "wegnehmen ändert nichts: Das Protokoll ist eine Historie.",
              "",
              "Grund einer Absage oder Notiz? Als Kommentar: `/outcome declined gap: …`",
              "",
              "<sub>Weitere Beispiele: `/outcome interview Fallstudie am 3.12.`, "
              "`/outcome accepted` (Angebot angenommen, schliesst das Issue).</sub>"]
    return "\n".join(lines) + "\n"


def slug_of(comment_text):
    hit = MARKER_RE.search(comment_text or "")
    return hit.group(1) if hit else None


def parse_boxes(comment_text):
    """{Beschriftung: angehakt} für die bekannten Kästchen."""
    labels = {b[0] for b in BOXES}
    out = {}
    for line in (comment_text or "").splitlines():
        hit = BOX.match(line)
        if hit and hit.group(2).strip() in labels:
            out[hit.group(2).strip()] = hit.group(1).lower() == "x"
    return out


def pending(boxes, rec):
    """(Status, Notiz)-Paare, die neu ins Protokoll gehören, in der Reihenfolge der Checkliste."""
    logged = set(_logged(rec))
    rounds = _rounds_done(rec)
    todo = []
    for box in BOXES:
        label, _, status, note = box
        if not boxes.get(label) or _done(box, rec, logged, rounds):
            continue
        if status == "withdrawn" and "submitted" not in logged:
            status = "skipped"
        todo.append((status, note))
        logged.add(status)
        if status == "interview":
            rounds.add(note)
    return todo


def removed(boxes, rec):
    """Beschriftungen, deren Häkchen fehlt, obwohl der Eintrag im Protokoll steht."""
    return [b[0] for b in BOXES if boxes.get(b[0]) is False and _done(b, rec)]


def apply(text, statuses, current, today=None):
    """Statusliste in application.md festhalten. Gibt (text, status danach) zurück."""
    today = today or datetime.date.today()
    for item in statuses:
        status, note = item if isinstance(item, tuple) else (item, "")
        keep = RANK.get(current, 0) > RANK.get(status, 0)
        text = record(text, status, note, today, keep_status=keep)
        if status == "submitted":
            text = set_front(text, "submitted_at", today.isoformat())
        if not keep:
            current = status
    return text, current


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jobwatch.stand", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default="applications")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("checkliste").add_argument("package")
    sub.add_parser("slug").add_argument("comment")
    sub.add_parser("anwenden").add_argument("comment")
    args = parser.parse_args(argv)

    if args.cmd == "checkliste":
        slug = os.path.basename(os.path.normpath(args.package))
        path = os.path.join(args.package, "application.md")
        rec = parse(path) if os.path.exists(path) else None
        sys.stdout.write(checklist(slug, rec))
        return 0
    comment = open(args.comment, encoding="utf-8").read()
    slug = slug_of(comment)
    if not slug or not SLUG_OK.match(slug) or ".." in slug:
        print("Fehler: keine Markierung «jobhunter:stand» im Kommentar", file=sys.stderr)
        return 2
    if args.cmd == "slug":
        print(slug)
        return 0
    path = os.path.join(args.root, slug, "application.md")
    if not os.path.exists(path):
        print(f"Fehler: {path} nicht gefunden", file=sys.stderr)
        return 2
    rec = parse(path)
    boxes = parse_boxes(comment)
    todo = pending(boxes, rec)
    if not todo:
        gone = removed(boxes, rec)
        if gone:
            print("Häkchen entfernt bei " + ", ".join(f"«{g}»" for g in gone) + ". Das Protokoll "
                  "bleibt unverändert (es ist eine Historie). Versehen? Einfach wieder anhaken.")
        return 3
    text, status = apply(open(path, encoding="utf-8").read(), todo, rec["status"])
    open(path, "w", encoding="utf-8").write(text)
    for s, note in todo:
        word = note or STATUSES[s]
        print(f"✅ {word[:1].upper() + word[1:]} festgehalten (`{s}`).")
    if status in FINAL:
        print(f"Die Bewerbung ist abgeschlossen ({STATUSES[status]}); das Issue wird geschlossen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
