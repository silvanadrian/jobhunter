"""Stand einer Bewerbung per Häkchen (offline)."""
import contextlib
import datetime
import io
import os
import shutil
import tempfile
import unittest

from jobwatch import stand
from jobwatch.records import parse

D = datetime.date


def app(status="draft", log=""):
    return (f"---\nstatus: {status}\ncompany: \"Muster AG\"\nrole: \"Engineer\"\n"
            "deadline:\nsubmitted_at:\n---\n\n# Bewerbung: Engineer bei Muster AG\n\n"
            "<!-- application:muster -->\n\n## Outcome log\n\n"
            f"- 2026-11-01 — prepared (vorbereitet)\n{log}")


def tick(text, *labels):
    for label in labels:
        text = text.replace(f"- [ ] **{label}**", f"- [x] **{label}**")
    return text


def untick(text, *labels):
    for label in labels:
        text = text.replace(f"- [x] **{label}**", f"- [ ] **{label}**")
    return text


class StandTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "muster"))
        self.path = os.path.join(self.root, "muster", "application.md")

    def tearDown(self):
        shutil.rmtree(self.root)

    def write(self, text):
        open(self.path, "w", encoding="utf-8").write(text)

    def run_apply(self, comment):
        file = os.path.join(self.root, "kommentar.md")
        open(file, "w", encoding="utf-8").write(comment)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = stand.main(["--root", self.root, "anwenden", file])
        return code, out.getvalue()

    def test_checklist_marker_and_boxes(self):
        text = stand.checklist("muster")
        self.assertEqual(stand.slug_of(text), "muster")
        self.assertIn("- [ ] **Eingereicht** (erst anhaken, wenn die Firma den Eingang bestätigt hat)",
                      text)
        self.assertIn("/outcome declined gap:", text)
        self.assertNotIn("ß", text)
        boxes = stand.parse_boxes(tick(text, "Eingereicht"))
        self.assertEqual(boxes, {"Eingereicht": True, "1. Gespräch": False, "2. Gespräch": False,
                                 "Weitere Runde": False, "Angebot erhalten": False,
                                 "Absage erhalten": False,
                                 "Zurückgezogen / doch nicht beworben": False})

    def test_checklist_reflects_log(self):
        self.write(app("interview", "- 2026-11-02 — submitted (eingereicht)\n"
                                    "- 2026-11-05 — interview (Gespräch): 1. Runde\n"))
        text = stand.checklist("muster", parse(self.path))
        self.assertIn("- [x] **Eingereicht**", text)
        self.assertIn("- [x] **1. Gespräch**", text)       # Eintrag ohne Runde zählt als 1.
        self.assertIn("- [ ] **2. Gespräch**", text)
        self.assertIn("- [ ] **Absage erhalten**", text)

    def test_tick_records_once(self):
        self.write(app())
        comment = tick(stand.checklist("muster"), "Eingereicht")
        code, out = self.run_apply(comment)
        self.assertEqual(code, 0)
        self.assertIn("Eingereicht festgehalten", out)
        rec = parse(self.path)
        self.assertEqual(rec["status"], "submitted")
        self.assertTrue(rec["submitted_at"])
        self.assertEqual([e["status"] for e in rec["log"]], ["prepared", "submitted"])
        # Derselbe Kommentar nochmals (z. B. zweiter Lauf nach schnellen Klicks): nichts doppelt.
        code, out = self.run_apply(comment)
        self.assertEqual(code, 3)
        self.assertEqual(out, "")
        self.assertEqual(len(parse(self.path)["log"]), 2)

    def test_command_before_tick_counts(self):
        self.write(app("submitted", "- 2026-11-02 — submitted (eingereicht)\n"))
        code, _ = self.run_apply(tick(stand.checklist("muster"), "Eingereicht"))
        self.assertEqual(code, 3)

    def test_untick_is_ignored_with_note(self):
        self.write(app("submitted", "- 2026-11-02 — submitted (eingereicht)\n"))
        text = stand.checklist("muster", parse(self.path))
        code, out = self.run_apply(untick(text, "Eingereicht"))
        self.assertEqual(code, 3)
        self.assertIn("Protokoll bleibt unverändert", out)
        self.assertEqual(parse(self.path)["status"], "submitted")

    def test_withdrawn_or_skipped(self):
        self.write(app())
        rec = parse(self.path)
        gone = "Zurückgezogen / doch nicht beworben"
        self.assertEqual(stand.pending({gone: True}, rec), [("skipped", "")])
        self.assertEqual(stand.pending({"Eingereicht": True, gone: True}, rec),
                         [("submitted", ""), ("withdrawn", "")])

    def test_several_rounds(self):
        self.write(app("submitted", "- 2026-11-02 — submitted (eingereicht)\n"))
        text = stand.checklist("muster", parse(self.path))
        code, out = self.run_apply(tick(text, "1. Gespräch"))
        self.assertEqual(code, 0)
        self.assertIn("1. Gespräch festgehalten", out)
        text = stand.checklist("muster", parse(self.path))
        self.assertIn("- [x] **1. Gespräch**", text)
        self.assertIn("- [ ] **2. Gespräch**", text)
        code, out = self.run_apply(tick(tick(text, "2. Gespräch"), "Weitere Runde"))
        self.assertEqual(code, 0)
        rec = parse(self.path)
        notes = [e["note"] for e in rec["log"] if e["status"] == "interview"]
        self.assertEqual(len(notes), 3)
        self.assertTrue(any("2. Gespräch" in n for n in notes))
        self.assertEqual(rec["status"], "interview")
        # nochmals derselbe Stand: nichts doppelt
        code, _ = self.run_apply(tick(tick(stand.checklist("muster", rec), "2. Gespräch"), "Weitere Runde"))
        self.assertEqual(code, 3)

    def test_status_never_goes_back(self):
        text, status = stand.apply(app("interview", "- 2026-11-05 — interview (Gespräch)\n"),
                                   ["submitted"], "interview", D(2026, 11, 6))
        self.assertEqual(status, "interview")
        self.assertIn("status: interview", text)
        self.assertIn("- 2026-11-06 — submitted (eingereicht)", text)
        self.assertIn("submitted_at: 2026-11-06", text)

    def test_declined_is_final(self):
        self.write(app("submitted", "- 2026-11-02 — submitted (eingereicht)\n"))
        text = stand.checklist("muster", parse(self.path))
        code, out = self.run_apply(tick(text, "Absage erhalten"))
        self.assertEqual(code, 0)
        self.assertIn("Issue wird geschlossen", out)
        self.assertEqual(parse(self.path)["status"], "declined")

    def test_rejects_bad_marker(self):
        file = os.path.join(self.root, "k.md")
        open(file, "w").write("<!-- jobhunter:stand slug=../etc -->\n- [x] **Eingereicht**\n")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(stand.main(["--root", self.root, "anwenden", file]), 2)


if __name__ == "__main__":
    unittest.main()
