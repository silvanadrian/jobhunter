"""Bewerbungsprotokolle (applications/<slug>/application.md) lesen und auswerten.

    python -m jobwatch.records list                     # alle Bewerbungen mit Status
    python -m jobwatch.records same-company "Acme AG"   # schon bei dieser Firma beworben?
    python -m jobwatch.records reminders                # Fristen und Nachfass-Vorschläge
    python -m jobwatch.records checkin                  # Text für das Wochen-Issue
    python -m jobwatch.records status < kommentar.txt   # /status-Befehle anwenden
    python -m jobwatch.records retention                # alte Bewerbungen (Aufbewahrung)

Alles hier ist deterministisch: kein Modell, kein Netzwerk.
"""

import argparse
import datetime
import os
import re
import shutil
import sys

from .filters import name_lookup
from .outcome import FINAL, STATUSES, record, set_front

# Antworten im Wochen-Issue: deutsch oder englisch.
STATUS_ALIASES = {
    "eingereicht": "submitted", "submitted": "submitted",
    "interview": "interview", "gespräch": "interview", "gespraech": "interview",
    "absage": "declined", "declined": "declined",
    "angebot": "offer", "offer": "offer",
    "angenommen": "accepted", "accepted": "accepted",
    "zurückgezogen": "withdrawn", "zurueckgezogen": "withdrawn", "withdrawn": "withdrawn",
    "keine-antwort": "no-response", "no-response": "no-response",
    "nicht-beworben": "skipped", "skipped": "skipped",
}
STATUS_LINE = re.compile(r"^/(?:status|outcome)\s+(\S+)(?:\s+(\S+))?(?:\s+(.*))?$", re.M)
LOG_LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) — (\S+)(?: \([^)]*\))?(?:: (.*))?$")


def front_matter(text):
    hit = re.match(r"---\n(.*?)\n---", text, re.S)
    data = {}
    if hit:
        for line in hit.group(1).splitlines():
            key, sep, value = line.partition(":")
            if sep and not line.startswith((" ", "-")):
                data[key.strip()] = value.strip().strip('"')
    return data


def parse(path):
    text = open(path, encoding="utf-8").read()
    front = front_matter(text)
    slug = os.path.basename(os.path.dirname(path))
    title = re.search(r"^# (.*)$", text, re.M)
    log = []
    section = re.search(r"^## Outcome log[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    for line in (section.group(1) if section else "").splitlines():
        hit = LOG_LINE.match(line.strip())
        if hit:
            log.append({"date": hit.group(1), "status": hit.group(2), "note": hit.group(3) or ""})
    return {"slug": slug, "path": path, "status": front.get("status", "draft"),
            "company": front.get("company", ""), "role": front.get("role", ""),
            "url": front.get("url", ""), "deadline": front.get("deadline", ""),
            "submitted_at": front.get("submitted_at", ""),
            "title": title.group(1) if title else slug, "log": log}


def load_all(root="applications", include_examples=False):
    records = []
    if not os.path.isdir(root):
        return records
    for name in sorted(os.listdir(root)):
        if name.startswith("_") and not include_examples:
            continue
        path = os.path.join(root, name, "application.md")
        if os.path.isfile(path):
            records.append(parse(path))
    return records


def _date(value):
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def last_activity(rec):
    dates = [_date(e["date"]) for e in rec["log"]] + [_date(rec["submitted_at"])]
    dates = [d for d in dates if d]
    return max(dates) if dates else None


def is_open(rec):
    return rec["status"] not in FINAL


# --- schon beworben? -------------------------------------------------------------

def same_company(company, records, cfg=None, exclude_slug=None):
    """Hinweise in Deutsch, wenn es bei dieser Firma schon eine Bewerbung gibt."""
    notes = []
    for rec in records:
        if rec["slug"] == exclude_slug or not rec["company"]:
            continue
        if name_lookup(company, {rec["company"]: "x"}) or name_lookup(rec["company"], {company: "x"}):
            when = rec["submitted_at"] or (rec["log"][0]["date"] if rec["log"] else "unbekannt")
            notes.append(f"Bei dieser Firma hast du dich am {when} schon beworben "
                         f"(Stelle «{rec['role'] or rec['title']}», Status {rec['status']}).")
    if cfg:
        why = name_lookup(company, cfg.get("ruled_out") or {})
        if why:
            notes.append(f"Diese Firma steht in deiner Ausschlussliste (ruled_out): {why}.")
    return notes


# --- Fristen und Nachfassen ----------------------------------------------------

def follow_up_draft(rec, today):
    sent = rec["submitted_at"] or "kürzlich"
    role = rec["role"] or rec["title"]
    return (f"Betreff: Bewerbung als {role} — kurze Nachfrage\n\n"
            "Sehr geehrte Damen und Herren\n\n"
            f"Am {sent} habe ich mich auf die Stelle als {role} beworben. Gerne erkundige ich "
            "mich nach dem Stand des Verfahrens und ob Sie noch Unterlagen von mir benötigen.\n\n"
            "Freundliche Grüsse")


def reminders(records, today=None, follow_up_days=14, deadline_days=2):
    """Gibt eine Liste von (slug, art, markdown) zurück. art: deadline | follow-up."""
    today = today or datetime.date.today()
    out = []
    for rec in records:
        if not is_open(rec):
            continue
        deadline = _date(rec["deadline"])
        if rec["status"] in ("draft", "ready") and deadline and 0 <= (deadline - today).days <= deadline_days:
            out.append((rec["slug"], "deadline",
                        f"Erinnerung: Die Bewerbungsfrist für «{rec['title']}» endet am "
                        f"{deadline:%d.%m.%Y}. Noch nicht eingereicht."))
        submitted = _date(rec["submitted_at"])
        later = [e for e in rec["log"] if e["status"] not in ("prepared", "submitted")]
        if rec["status"] == "submitted" and submitted and not later \
                and (today - submitted).days >= follow_up_days:
            out.append((rec["slug"], "follow-up",
                        f"Seit der Einreichung am {submitted:%d.%m.%Y} sind {(today - submitted).days} "
                        "Tage ohne Antwort vergangen. Vorschlag für eine kurze Nachfrage "
                        "(nur absenden, wenn es für dich passt):\n\n```text\n"
                        + follow_up_draft(rec, today) + "\n```"))
    return out


# --- Wochen-Check-in ------------------------------------------------------------

def stats(records, since):
    count = {"vorbereitet": 0, "eingereicht": 0, "Antworten": 0, "Interviews": 0, "Absagen": 0,
             "Angebote": 0}
    for rec in records:
        for e in rec["log"]:
            d = _date(e["date"])
            if not d or d < since:
                continue
            key = {"prepared": "vorbereitet", "submitted": "eingereicht", "interview": "Interviews",
                   "declined": "Absagen", "offer": "Angebote"}.get(e["status"])
            if key:
                count[key] += 1
            if e["status"] in ("interview", "declined", "offer"):
                count["Antworten"] += 1
    return count


def gap_clusters(records, minimum=2):
    """Lücken, die in mehreren Absagen genannt wurden (Notiz mit 'gap: ...' / 'lücke: ...')."""
    seen = {}
    for rec in records:
        for e in rec["log"]:
            if e["status"] != "declined":
                continue
            for gap in re.findall(r"(?:gap|lücke|luecke):\s*([^;,.]+)", e["note"], re.I):
                key = gap.strip().lower()
                seen.setdefault(key, set()).add(rec["slug"])
    return {g: sorted(s) for g, s in seen.items() if len(s) >= minimum}


def checkin(records, today=None, found=None):
    today = today or datetime.date.today()
    week = today - datetime.timedelta(days=7)
    numbers = stats(records, week)
    lines = [f"Wochen-Check-in vom {today:%d.%m.%Y}.", "",
             "## Zahlen der letzten 7 Tage", ""]
    if found is not None:
        lines.append(f"- gefunden: {found}")
    lines += [f"- {k}: {v}" for k, v in numbers.items()]
    open_recs = [r for r in records if is_open(r) and r["status"] != "draft"]
    lines += ["", "## Wie steht es um deine offenen Bewerbungen?", ""]
    if not open_recs:
        lines.append("Keine offenen Bewerbungen. 🎉")
    else:
        lines += ["Antworte mit einem Kommentar, eine Zeile pro Bewerbung, zum Beispiel:", "",
                  "```text", f"/status {open_recs[0]['slug']} interview Gespräch am 3.12.",
                  f"/status {open_recs[0]['slug']} absage gap: Führungserfahrung", "```", "",
                  "Mögliche Antworten: `eingereicht`, `interview`, `absage`, `angebot`, "
                  "`keine-antwort`, `zurückgezogen`. Mit `gap: ...` hältst du fest, woran es lag.",
                  "", "| Bewerbung | Status | seit | Befehl |", "|---|---|---|---|"]
        for r in open_recs:
            last = last_activity(r)
            age = f"{(today - last).days} Tagen" if last else "?"
            lines.append(f"| {r['title']} | {r['status']} | {age} | `/status {r['slug']} ...` |")
        lines += ["", "<!-- open:" + ",".join(r["slug"] for r in open_recs) + " -->"]
    clusters = gap_clusters(records)
    if clusters:
        lines += ["", "## Muster in den Absagen", ""]
        for gap, slugs in clusters.items():
            lines.append(f"- «{gap}» wurde bei {len(slugs)} Absagen genannt ({', '.join(slugs)}). "
                         "Vorschlag: gezielt vorbereiten oder nachweisbar aufbauen (Kurs, "
                         "Projekt, Verantwortung im aktuellen Job) und erst dann als Beleg "
                         "erfassen. Die Lücke nicht umformulieren oder verstecken.")
    return "\n".join(lines) + "\n"


def apply_status(comment, records, today=None):
    """/status-Zeilen anwenden. Gibt (geänderte slugs, Meldungen) zurück."""
    today = today or datetime.date.today()
    by_slug = {r["slug"]: r for r in records}
    changed, messages = [], []
    for slug, state, note in STATUS_LINE.findall(comment):
        rec = by_slug.get(slug)
        status = STATUS_ALIASES.get((state or "").lower())
        if rec is None:
            messages.append(f"❓ `{slug}`: keine Bewerbung mit diesem Namen.")
            continue
        if status is None:
            messages.append(f"❓ `{slug}`: unbekannter Status «{state}». Möglich: "
                            + ", ".join(sorted(set(STATUS_ALIASES))))
            continue
        text = open(rec["path"], encoding="utf-8").read()
        if status == "no-response":
            text = record(text, "no-response", note.strip(), today, keep_status=True)
        else:
            text = record(text, status, note.strip(), today)
            if status == "submitted":
                text = set_front(text, "submitted_at", today.isoformat())
        open(rec["path"], "w", encoding="utf-8").write(text)
        changed.append(slug)
        messages.append(f"✅ `{slug}`: {STATUSES.get(status, status)} festgehalten.")
    return changed, messages


def unanswered(body, records, since):
    """Slugs aus dem Check-in, die seit dessen Erstellung noch keinen Eintrag haben."""
    hit = re.search(r"<!-- open:([^>]*) -->", body)
    slugs = [s for s in (hit.group(1).split(",") if hit else []) if s]
    by_slug = {r["slug"]: r for r in records}
    missing = []
    for slug in slugs:
        rec = by_slug.get(slug)
        if rec is None or not is_open(rec):
            continue
        if not any((_date(e["date"]) or since) >= since and e["status"] != "prepared"
                   for e in rec["log"]):
            missing.append(slug)
    return missing


# --- Aufbewahrung -----------------------------------------------------------------

def due_for_retention(records, months=12, today=None):
    today = today or datetime.date.today()
    limit = today - datetime.timedelta(days=int(months * 30.5))
    return [r for r in records if not is_open(r) and (last_activity(r) or today) < limit]


def apply_retention(records, mode="archive", root="applications", archive_root="archive"):
    done = []
    for rec in records:
        folder = os.path.dirname(rec["path"])
        if mode == "delete":
            shutil.rmtree(folder)
        else:
            os.makedirs(archive_root, exist_ok=True)
            shutil.move(folder, os.path.join(archive_root, os.path.basename(folder)))
        done.append(rec["slug"])
    return done


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jobwatch.records", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default="applications")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    same = sub.add_parser("same-company")
    same.add_argument("company")
    same.add_argument("--exclude")
    rem = sub.add_parser("reminders")
    rem.add_argument("--follow-up-days", type=int, default=14)
    chk = sub.add_parser("checkin")
    chk.add_argument("--found", type=int)
    sub.add_parser("status")
    done = sub.add_parser("checkin-done")
    done.add_argument("body_file")
    done.add_argument("--since", required=True, help="Datum JJJJ-MM-TT")
    ret = sub.add_parser("retention")
    ret.add_argument("--months", type=int, default=12)
    ret.add_argument("--apply", choices=["archive", "delete"])
    args = parser.parse_args(argv)
    records = load_all(args.root)

    if args.cmd == "list":
        for r in records:
            print(f"{r['slug']:40} {r['status']:12} {r['company']}")
    elif args.cmd == "same-company":
        cfg = None
        try:
            from .config import load
            cfg = load()
        except Exception:
            pass
        for note in same_company(args.company, records, cfg, args.exclude):
            print(note)
    elif args.cmd == "reminders":
        for slug, kind, text in reminders(records, follow_up_days=args.follow_up_days):
            print(f"### {slug} ({kind})\n\n{text}\n")
    elif args.cmd == "checkin":
        print(checkin(records, found=args.found), end="")
    elif args.cmd == "status":
        changed, messages = apply_status(sys.stdin.read(), records)
        print("\n".join(messages) or "Keine /status-Zeilen gefunden.")
        return 0 if changed or not messages else 1
    elif args.cmd == "checkin-done":
        missing = unanswered(open(args.body_file, encoding="utf-8").read(), records,
                             datetime.date.fromisoformat(args.since))
        print("Noch offen: " + ", ".join(missing) if missing else "Alles beantwortet.")
        return 1 if missing else 0
    elif args.cmd == "retention":
        due = due_for_retention(records, args.months)
        if args.apply:
            print("\n".join(apply_retention(due, args.apply, args.root)))
        else:
            for r in due:
                print(f"- {r['slug']} (Status {r['status']}, zuletzt {last_activity(r)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
