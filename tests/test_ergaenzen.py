"""Formular «Profil ergänzen»: nur ergänzen, nie ändern (offline)."""
import copy
import os
import unittest

import yaml

from jobwatch import ergaenzen
from jobwatch.belege import align_cv, apply_to_evidence, checklist, parse_boxes
from jobwatch.guard import check_claims, red_flags, resolve
from jobwatch.kopieren import AnswerError, parse_answer
from jobwatch.profile import is_confirmed, parse_evidence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Musterprofil als Basis (nicht profile/: dort steht später das echte Profil).
BEISPIEL = os.path.join(ROOT, "tests", "fixtures", "beispiel")
EVIDENCE = open(os.path.join(BEISPIEL, "evidence.md"), encoding="utf-8").read()
CV = yaml.safe_load(open(os.path.join(BEISPIEL, "cv.yaml"), encoding="utf-8"))

FORM = """### Was ist neu?

Neue Stelle seit 03/2026: Teamleiter bei Beispiel AG in Bern. Ich führe vier Leute.

### Quelle (optional)

Arbeitsvertrag 2026
"""

ANSWER = """/ergaenzen
Hier ist die Antwort:

```yaml
ergaenzen:
  roles:
    - title: Teamleiter Entwicklung
      org: Beispiel AG
      location: Bern
      dates: "03/2026 – heute"
      items:
        - "Führt ein Team von vier Personen"
  items:
    - role: R1
      text: "Code-Reviews für das Kundenportal organisiert"
  skills:
    - category: "Sprachen & Frameworks"
      items: "Kotlin"
      level: basic
      hobby: false
  courses:
    - title: AWS Certified Cloud Practitioner
      school: Amazon Web Services
      dates: "11/2025"
```
Viel Erfolg!
"""


def run(answer=ANSWER, history=""):
    data = parse_answer(answer, ergaenzen.KEYS)
    draft = ergaenzen.validate(data, list(parse_evidence(EVIDENCE)["roles"]))
    return ergaenzen.apply(draft, EVIDENCE, CV, "Arbeitsvertrag 2026", history)


class Form(unittest.TestCase):
    def test_read_form(self):
        new, source = ergaenzen.read_form(FORM)
        self.assertIn("Teamleiter", new)
        self.assertEqual(source, "Arbeitsvertrag 2026")
        with self.assertRaises(ergaenzen.ErgaenzenError):
            ergaenzen.read_form("### Was ist neu?\n\n_No response_\n")

    def test_prompt_treats_input_as_untrusted(self):
        new, source = ergaenzen.read_form(FORM)
        prompt = ergaenzen.build_prompt(new, source, EVIDENCE, CV, "REGELN")
        self.assertIn("nicht vertrauenswürdiger", prompt)
        self.assertIn("- R1: Senior Software Engineer, Contoso AG", prompt)
        self.assertIn("ergaenzen:", prompt)
        self.assertTrue(prompt.rstrip().endswith("Ich führe vier Leute."))
        cli = ergaenzen.build_prompt(new, source, EVIDENCE, CV, "REGELN", "ergaenzung.yaml")
        self.assertIn("in die Datei `ergaenzung.yaml`", cli)
        self.assertNotIn("ß", prompt)

    def test_comment_uses_command(self):
        text = ergaenzen.comment("Neue Kenntnis: Kotlin", "", EVIDENCE, CV, "REGELN")
        self.assertIn("`/ergaenzen` in der", text)
        self.assertIn("Entwurf (Pull Request)", text)


class Apply(unittest.TestCase):
    def test_new_ids_follow_and_are_unconfirmed(self):
        new_ev, new_cv, ids = run()
        self.assertEqual(ids, ["E12", "E13", "E14", "E15"])
        items = parse_evidence(new_ev)["items"]
        for eid in ids:
            self.assertFalse(is_confirmed(items[eid]), eid)
            self.assertIn("Quelle: Arbeitsvertrag 2026.", items[eid]["text"])
        self.assertIn("level: basic", items["E14"]["tags"])
        self.assertEqual(items["E13"]["role"], "R1")
        self.assertEqual(items["E12"]["role"], "R4")
        self.assertIn("## R4 | Teamleiter Entwicklung | Beispiel AG | Bern | 03/2026 – heute", new_ev)
        # neue Stelle steht in evidence.md vor R1 und in cv.yaml ganz oben
        self.assertLess(new_ev.index("\n## R4 |"), new_ev.index("\n## R1 |"))
        self.assertEqual(new_cv["experience"][0]["id"], "R4")
        self.assertEqual(new_cv["experience"][0]["bullets"][0],
                         {"id": "B9", "text": "Führt ein Team von vier Personen", "evidence": ["E12"]})
        self.assertEqual(new_cv["experience"][1]["bullets"][-1]["evidence"], ["E13"])
        self.assertEqual(new_cv["experience"][1]["bullets"][-1]["id"], "B10")
        skill = new_cv["skills"][-1]
        self.assertEqual(skill["category"], "Sprachen & Frameworks (ergänzt)")
        self.assertIn("Grundkenntnisse", skill["items"])
        self.assertEqual(new_cv["education"][0]["evidence"], ["E15"])

    def test_existing_entries_unchanged(self):
        new_ev, new_cv, _ = run()
        self.assertEqual(ergaenzen.verify_append_only(EVIDENCE, new_ev, CV, new_cv), [])
        old_lines = EVIDENCE.splitlines()
        for line in old_lines:
            self.assertIn(line, new_ev.splitlines())
        self.assertEqual(new_cv["experience"][1:][0]["bullets"][:4], CV["experience"][0]["bullets"])
        self.assertEqual(new_cv["skills"][:4], CV["skills"])

    def test_history_ids_never_reused(self):
        history = "-- E40 [bestätigt]: gelöscht\n- id: B33\n-## R9 | Alt | X | Y | Z\n"
        _, new_cv, ids = run(history=history)
        self.assertEqual(ids[0], "E41")
        self.assertEqual(new_cv["experience"][0]["id"], "R10")
        self.assertEqual(new_cv["experience"][0]["bullets"][0]["id"], "B34")

    def test_unknown_role_and_empty_answer(self):
        bad = ANSWER.replace("role: R1", "role: R7")
        with self.assertRaises(AnswerError) as ctx:
            run(bad)
        self.assertIn("R7", str(ctx.exception))
        with self.assertRaises(AnswerError):
            run("```yaml\nergaenzen:\n  roles: []\n  items: []\n  skills: []\n  courses: []\n```")

    def test_input_is_flattened(self):
        sneaky = ANSWER.replace('"Führt ein Team von vier Personen"',
                                '"Text | mit <!-- Kommentar --> und\\n## R1 | Neu"')
        new_ev, _, _ = run(sneaky)
        data = parse_evidence(new_ev)
        self.assertEqual(sorted(data["roles"]), ["R1", "R2", "R3", "R4"])
        self.assertNotIn("<!--", data["items"]["E12"]["text"])


class Verify(unittest.TestCase):
    def test_detects_changed_deleted_and_confirmed(self):
        new_ev, new_cv, _ = run()
        changed = new_ev.replace("Playwright-End-to-End-Tests", "Playwright-Tests")
        self.assertIn("Beleg E2 wurde geändert",
                      ergaenzen.verify_append_only(EVIDENCE, changed, CV, new_cv))
        deleted = "\n".join(l for l in new_ev.splitlines() if not l.startswith("- E8 "))
        self.assertIn("Beleg E8 wurde gelöscht",
                      ergaenzen.verify_append_only(EVIDENCE, deleted, CV, new_cv))
        sneaky = new_ev.replace("- E12 [unbestätigt]", "- E12 [bestätigt]")
        self.assertTrue(any("E12" in p and "[unbestätigt]" in p
                            for p in ergaenzen.verify_append_only(EVIDENCE, sneaky, CV, new_cv)))
        role = new_ev.replace("| Contoso AG | Zürich |", "| Contoso AG | Basel |")
        self.assertIn("Stelle R1 wurde geändert",
                      ergaenzen.verify_append_only(EVIDENCE, role, CV, new_cv))

    def test_detects_cv_changes(self):
        new_ev, new_cv, _ = run()
        cv = copy.deepcopy(new_cv)
        cv["experience"][1]["bullets"][0]["text"] = "Leitete alles"
        self.assertTrue(ergaenzen.verify_append_only(EVIDENCE, new_ev, CV, cv))
        cv = copy.deepcopy(new_cv)
        del cv["skills"][0]
        self.assertTrue(ergaenzen.verify_append_only(EVIDENCE, new_ev, CV, cv))
        cv = copy.deepcopy(new_cv)
        cv["person"]["email"] = "x@example.com"
        self.assertTrue(ergaenzen.verify_append_only(EVIDENCE, new_ev, CV, cv))

    def test_detects_reused_id(self):
        new_ev, new_cv, _ = run()
        problems = ergaenzen.verify_append_only(EVIDENCE, new_ev, CV, new_cv, "- E13 [x]: alt\n")
        self.assertTrue(any("E12" in p and "schon einmal" in p for p in problems))


class Checklist(unittest.TestCase):
    """belege.yml für Ergänzungen: nur neue Belege, alte Punkte bleiben unberührt."""

    def test_checklist_only_new(self):
        new_ev, _, ids = run()
        text = checklist(new_ev, "ergaenzen/issue-9", set(ids))
        self.assertEqual(sorted(parse_boxes(text)), sorted(ids))
        self.assertIn("nur die **neuen** Einträge", text)
        self.assertIn("**Teamleiter Entwicklung, Beispiel AG**", text)
        self.assertNotIn("Quelle: Formular", text)

    def test_align_scope_keeps_old_entries(self):
        new_ev, draft_cv, ids = run()
        cv = copy.deepcopy(draft_cv)
        # Altes ohne bestätigten Beleg, das ohne Geltungsbereich verschwinden würde:
        cv["experience"][1]["bullets"].insert(0, {"id": "B99", "text": "von Hand", "evidence": []})
        boxes = {eid: eid in ("E12", "E15") for eid in ids}
        new_ev = apply_to_evidence(new_ev, boxes)
        items = parse_evidence(new_ev)["items"]
        confirmed = {i for i, it in items.items() if is_confirmed(it)}
        out = align_cv(copy.deepcopy(cv), draft_cv, confirmed, set(boxes))
        self.assertEqual([b["id"] for b in out["experience"][0]["bullets"]], ["B9"])
        self.assertEqual([b["id"] for b in out["experience"][1]["bullets"]],
                         ["B1", "B2", "B3", "B4", "B99"])
        self.assertEqual(out["skills"], CV["skills"])
        self.assertEqual(out["education"][0]["evidence"], ["E15"])
        self.assertEqual(out["education"][1:], CV["education"])
        # Später doch angehakt: kommt aus dem Entwurf zurück.
        boxes["E13"] = True
        new_ev = apply_to_evidence(new_ev, boxes)
        confirmed = {i for i, it in parse_evidence(new_ev)["items"].items() if is_confirmed(it)}
        out = align_cv(out, draft_cv, confirmed, set(boxes))
        self.assertEqual([b["id"] for b in out["experience"][1]["bullets"]],
                         ["B1", "B2", "B3", "B4", "B10", "B99"])
        # Guard: der bereinigte Basis-Lebenslauf zitiert nur Bestätigtes.
        evidence = parse_evidence(new_ev)
        out["experience"][1]["bullets"].pop()   # B99 ohne Beleg ist ein eigenes Thema
        claims, problems = resolve(out, None)
        self.assertEqual(problems, [])
        self.assertEqual(check_claims(claims, evidence, red_flags(os.path.join(ROOT, "GUARDRAILS.md"))),
                         [])

    def test_guard_checks_education_with_evidence(self):
        new_ev, new_cv, _ = run()
        claims, _ = resolve(new_cv, None)
        issues = check_claims(claims, parse_evidence(new_ev), [])
        self.assertTrue(any("E15" in i and "unbestätigt" in i for i in issues))


if __name__ == "__main__":
    unittest.main()
