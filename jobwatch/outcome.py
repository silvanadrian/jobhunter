"""Ergebnis einer Bewerbung im Bewerbungsprotokoll festhalten.

    python -m jobwatch.outcome applications/acme-tech-lead submitted
    python -m jobwatch.outcome applications/acme-tech-lead interview --note "1. Gespräch am 3.12."
    python -m jobwatch.outcome applications/acme-tech-lead declined --note "Absage nach 1. Runde"

Hängt eine datierte Zeile an den Abschnitt "## Outcome log" in application.md
an und setzt `status:` im Front Matter. Gibt auf stdout "close" aus, wenn der
Status abschliessend ist (declined, withdrawn, accepted) — der Workflow
schliesst dann das Issue.

"submitted" nur festhalten, wenn die Bewerbungsseite eine ausdrückliche
Bestätigung angezeigt oder eine Bestätigungsmail geschickt hat.
"""

import argparse
import datetime
import os
import re
import sys

STATUSES = {
    "submitted": "eingereicht",
    "interview": "Gespräch",
    "offer": "Angebot",
    "accepted": "angenommen",
    "declined": "Absage",
    "withdrawn": "zurückgezogen",
    "skipped": "nicht beworben",
    "no-response": "keine Antwort",
    "prepared": "vorbereitet",
}
FINAL = {"declined", "withdrawn", "accepted", "skipped"}


def set_front(text, key, value):
    """Einen Schlüssel im Front Matter setzen oder ergänzen."""
    hit = re.match(r"---\n(.*?)\n---", text, re.S)
    if not hit:
        return f"---\n{key}: {value}\n---\n\n" + text
    block = hit.group(1)
    if re.search(rf"^{re.escape(key)}:", block, re.M):
        block = re.sub(rf"^{re.escape(key)}:.*$", f"{key}: {value}", block, count=1, flags=re.M)
    else:
        block = f"{block}\n{key}: {value}"
    return f"---\n{block}\n---" + text[hit.end():]


def record(text, status, note="", today=None, keep_status=False):
    today = today or datetime.date.today()
    line = f"- {today.isoformat()} — {status} ({STATUSES[status]})" + (f": {note}" if note else "")
    if not keep_status:
        text = set_front(text, "status", status)
    heading = re.search(r"^## Outcome log[^\n]*\n", text, re.M)
    if not heading:
        return text.rstrip("\n") + f"\n\n## Outcome log\n\n{line}\n"
    nxt = re.search(r"^## ", text[heading.end():], re.M)
    end = heading.end() + nxt.start() if nxt else len(text)
    section = text[heading.end():end].rstrip("\n")
    return text[:heading.end()] + section + f"\n{line}\n" + ("\n" + text[end:] if nxt else "")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jobwatch.outcome", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("package", help="Ordner applications/<slug>")
    parser.add_argument("status", choices=sorted(STATUSES))
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    path = os.path.join(args.package, "application.md")
    if not os.path.exists(path):
        print(f"Fehler: {path} nicht gefunden", file=sys.stderr)
        return 1
    text = open(path, encoding="utf-8").read()
    text = record(text, args.status, args.note, keep_status=args.status == "no-response")
    if args.status == "submitted":
        text = set_front(text, "submitted_at", datetime.date.today().isoformat())
    open(path, "w", encoding="utf-8").write(text)
    print("close" if args.status in FINAL else "open")
    return 0


if __name__ == "__main__":
    sys.exit(main())
