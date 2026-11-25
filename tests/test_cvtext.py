"""cv.yaml als Text ergänzen: nur Zeilen dazu, Kommentare bleiben (offline)."""
import difflib
import os
import unittest

import yaml

from jobwatch import cvtext, ergaenzen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "beispiel")


class CvTextTest(unittest.TestCase):
    def setUp(self):
        self.ev = open(os.path.join(FIX, "evidence.md"), encoding="utf-8").read()
        self.txt = open(os.path.join(FIX, "cv.yaml"), encoding="utf-8").read()
        self.cv = yaml.safe_load(self.txt)
        draft = {"roles": [{"title": "Lead: Plattform", "org": "Neu AG", "location": "Bern",
                            "dates": "12/2026 – heute", "items": ["Team begleitet"]}],
                 "items": [{"role": "R1", "text": "Barrierefreiheit mit axe-core geprüft"}],
                 "skills": [{"category": "Betrieb", "items": "Kubernetes", "level": "basic",
                             "hobby": False}],
                 "courses": [{"title": "Kurs Kubernetes", "school": "BFH", "dates": "10/2026"}]}
        self.new_ev, self.new_cv, self.ids = ergaenzen.apply(draft, self.ev, self.cv, "Zertifikat", "")
        self.out = ergaenzen.cv_text_with(self.txt, self.cv, self.new_cv)

    def test_only_additions_and_same_data(self):
        diff = [l for l in difflib.unified_diff(self.txt.splitlines(), self.out.splitlines(),
                                                lineterm="", n=0)
                if not l.startswith(("+++", "---", "@@"))]
        self.assertTrue(diff)
        self.assertTrue(all(l.startswith("+") for l in diff), diff)
        self.assertEqual(yaml.safe_load(self.out), self.new_cv)
        self.assertIn("# Reihenfolge der Abschnitte", self.out)   # Kommentar bleibt

    def test_align_removes_and_restores(self):
        scope = set(self.ids)
        none = cvtext.align(self.out, self.out, set(), scope)
        self.assertEqual(yaml.safe_load(none)["skills"], self.cv["skills"])
        self.assertNotIn("axe-core", none)
        self.assertNotIn("Neu AG", none)                        # neue Stelle ohne Punkt fällt weg
        self.assertEqual(yaml.safe_load(none)["experience"], self.cv["experience"])
        self.assertEqual(cvtext.align(none, self.out, scope, scope), self.out)
        # eigene Änderung im Entwurf: nur noch weglassen, nichts überschreiben
        edited = self.out.replace("Contoso AG", "Contoso AG (Zürich)")
        kept = cvtext.align(edited, self.out, set(), scope)
        self.assertIn("Contoso AG (Zürich)", kept)


if __name__ == "__main__":
    unittest.main()
