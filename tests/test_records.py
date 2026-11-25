"""Kündigungsfrist, Bewerbungsprotokolle, Erinnerungen, Wochen-Check-in, Formulare (offline)."""

import datetime
import os
import shutil
import tempfile
import unittest

from jobwatch import records
from jobwatch.forms import apply_setup, parse_form
from jobwatch.outcome import record
from jobwatch.profile import earliest_start

D = datetime.date


def app(status="submitted", submitted="2026-10-01", deadline="", company="Muster AG", log=""):
    return (f"---\nstatus: {status}\ncompany: \"{company}\"\nrole: \"Engineer\"\n"
            f"deadline: {deadline}\nsubmitted_at: {submitted}\n---\n\n# Bewerbung: Engineer bei {company}\n\n"
            f"## Outcome log\n\n- 2026-09-30 — prepared (vorbereitet)\n{log}")


class Notice(unittest.TestCase):
    def test_month_end(self):
        self.assertEqual(earliest_start(D(2026, 11, 14), 3, "month_end"), D(2027, 3, 1))
        self.assertEqual(earliest_start(D(2026, 11, 30), 1, "month_end"), D(2027, 1, 1))

    def test_any_day(self):
        self.assertEqual(earliest_start(D(2026, 1, 31), 1, "any_day"), D(2026, 3, 1))


class Records(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root)

    def add(self, slug, text):
        os.makedirs(os.path.join(self.root, slug))
        open(os.path.join(self.root, slug, "application.md"), "w").write(text)

    def test_same_company_warning(self):
        self.add("muster-engineer", app())
        notes = records.same_company("Muster AG Zürich", records.load_all(self.root))
        self.assertTrue(notes and "schon beworben" in notes[0])

    def test_reminders(self):
        self.add("a", app(status="draft", submitted="", deadline="2026-11-16"))
        self.add("b", app(submitted="2026-10-20"))
        out = records.reminders(records.load_all(self.root), today=D(2026, 11, 14), follow_up_days=14)
        kinds = {(slug, kind) for slug, kind, _ in out}
        self.assertEqual(kinds, {("a", "deadline"), ("b", "follow-up")})
        text = [t for s, k, t in out if k == "follow-up"][0]
        self.assertIn("Freundliche Grüsse", text)
        self.assertNotIn("\u00df", text)

    def test_status_commands_and_checkin(self):
        self.add("a", app())
        self.add("b", app(company="Zweite AG"))
        recs = records.load_all(self.root)
        body = records.checkin(recs, today=D(2026, 11, 16))
        self.assertIn("/status a", body)
        self.assertEqual(records.unanswered(body, recs, D(2026, 11, 16)), ["a", "b"])
        changed, msgs = records.apply_status("/status a interview Gespräch am 3.12.\n"
                                             "/status b absage gap: Führung\n/status c foo",
                                             recs, today=D(2026, 11, 17))
        self.assertEqual(changed, ["a", "b"])
        self.assertTrue(any("keine Bewerbung" in m for m in msgs))
        recs = records.load_all(self.root)
        self.assertEqual([r["status"] for r in recs], ["interview", "declined"])
        self.assertEqual(records.unanswered(body, recs, D(2026, 11, 16)), [])

    def test_gap_clusters(self):
        self.add("a", app(status="declined", log="- 2026-11-01 — declined (Absage): gap: Führung\n"))
        self.add("b", app(status="declined", log="- 2026-11-02 — declined (Absage): gap: Führung\n"))
        body = records.checkin(records.load_all(self.root), today=D(2026, 11, 16))
        self.assertIn("Muster in den Absagen", body)
        self.assertIn("nicht umformulieren", body)

    def test_outcome_record_sets_status(self):
        text = record(app(status="draft"), "submitted", "Bestätigungsmail erhalten", D(2026, 11, 14))
        self.assertIn("status: submitted", text)
        self.assertIn("- 2026-11-14 — submitted (eingereicht): Bestätigungsmail erhalten", text)

    def test_retention(self):
        self.add("alt", app(status="declined", submitted="2025-01-01").replace("2026-09-30", "2025-01-01"))
        self.add("neu", app(status="declined", submitted="2026-11-01"))
        due = records.due_for_retention(records.load_all(self.root), 12, today=D(2026, 11, 14))
        self.assertEqual([r["slug"] for r in due], ["alt"])


class Forms(unittest.TestCase):
    BODY = """### Wunschtitel und Stichwörter

Software Engineer, Entwickler

### Stufe

Senior, Lead

### Orte

Zürich
Winterthur

### Land

Schweiz

### Remote

Ja

### Pensum

80–100%

### Ausschlusswörter

_No response_

### Firmen (Karriereseiten-URLs, eine pro Zeile)

https://boards.greenhouse.io/acme
https://example.com/karriere

### Assistent für Bewerbungspakete

copilot-cli (Standard, gratis mit Copilot Free, begrenzt)
"""

    def test_parse_and_write_config(self):
        fields = parse_form(self.BODY)
        self.assertEqual(fields["ausschlusswörter"], "")
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "jobhunter.yml")
            messages, unknown = apply_setup(fields, path)
            self.assertEqual(unknown, ["https://example.com/karriere"])
            text = open(path).read()
            self.assertIn("greenhouse:acme", text)
            self.assertIn("places: [Zürich, Winterthur]", text)
            self.assertIn("agent: copilot-cli", text)
            # erneut ausfüllen = aktualisieren
            apply_setup(parse_form(self.BODY.replace("Winterthur", "Baden")), path)
            self.assertIn("Baden", open(path).read())
            # heutige Beschriftung des Felds im Formular
            renamed = self.BODY.replace("### Firmen (Karriereseiten-URLs, eine pro Zeile)",
                                        "### Wunschfirmen (optional, Karriereseiten-URLs, eine pro Zeile)")
            apply_setup(parse_form(renamed), path)
            self.assertIn("greenhouse:acme", open(path).read())
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
