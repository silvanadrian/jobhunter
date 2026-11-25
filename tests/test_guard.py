"""Auftrag für den Assistenten, deterministischer Abschluss und Beleg-Guard (offline)."""

import os
import shutil
import tempfile
import unittest

from jobwatch import guard
from jobwatch.config import ConfigError, normalise
from jobwatch.prepare import PROMPT_LIMIT, build_prompt, finish
from jobwatch.prepare import main as prepare_main
from jobwatch.profile import parse_evidence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EVIDENCE = """# Belege
## R1 | Engineer | Beispiel AG | Bern | 2020 – heute
- E1 [bestätigt]: Webportal mit React weiterentwickelt.
- E2 [bestätigt]: Tests mit Playwright eingeführt.
- E3 [unbestätigt]: Team von 10 Personen geführt (aus Lebenslauf, ungeprüft).
## Allgemein
- E4 [hobby]: Rust in Freizeitprojekten.
- E5 [level: basic]: Kubernetes, eigene Dienste mit vorhandenen Charts deployt.
"""
BASE = """person: {first_name: Test, last_name: Person}
experience:
  - id: R1
    title: Engineer
    org: Beispiel AG
    location: Bern
    dates: 2020 – heute
    bullets:
      - {id: B1, text: Webportal mit React weiterentwickelt, evidence: [E1]}
      - {id: B2, text: Tests mit Playwright eingeführt, evidence: [E2]}
skills:
  - {category: Web, items: React, evidence: [E1]}
"""

VARIANT = """lang: de
summary:
  text: Engineer mit Erfahrung in React und Testautomatisierung.
  evidence: [E1, E2]
experience:
  - role: R1
    bullets:
      - B2
      - {text: Kundenportal mit React weiterentwickelt, evidence: [E1]}
skills:
  - {category: Web, items: "React, Playwright", evidence: [E1, E2]}
  - {category: Privat, items: Rust (Hobbyprojekte), evidence: [E4]}
letter:
  recipient: Muster AG
  title: Bewerbung
  paragraphs:
    - {text: Ich habe Playwright-Tests eingeführt., evidence: [E2]}
    - {text: Mit Kubernetes habe ich nur Grundkenntnisse., evidence: []}
"""
FIT = """# Passung: Senior Engineer bei Muster AG

| Anforderung | Passung | Belege |
|---|---|---|
| React | erfüllt | [E1] |
| Führung | LÜCKE | — |
"""
PREP = """# Vorbereitung

## Wahrscheinliche Fragen

1. **Tests?** Playwright eingeführt [E2].

## Rahmenbedingungen

- Starttermin laut Inserat: sofort (vom Modell, muss ersetzt werden)

## Fragen an die Firma

- Team?
"""
GOOD = {"summary": {"text": "Engineer mit Erfahrung in React und Testautomatisierung.",
                    "evidence": ["E1", "E2"]}}


class Workspace(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.dir, "profile"))
        os.makedirs(os.path.join(self.dir, "applications", "muster-senior-engineer"))
        open(os.path.join(self.dir, "profile", "evidence.md"), "w").write(EVIDENCE)
        open(os.path.join(self.dir, "profile", "cv.yaml"), "w").write(BASE)
        shutil.copy(os.path.join(ROOT, "GUARDRAILS.md"), self.dir)
        open(os.path.join(self.dir, "applications", "muster-senior-engineer", "job.md"), "w").write(
            '---\ncompany: "Muster AG"\ntitle: "Senior Engineer"\nurl: "https://example.com/1"\n'
            'valid_through: "2026-12-01"\n---\n\n# Senior Engineer\n\nReact, Führung.\n')
        self.cfg = normalise({"locations": [{"name": "x", "places": ["Bern"]}],
                              "profile": {"notice": {"months": 3, "until": "month_end"}}},
                             base_dir=self.dir)
        self.package = os.path.join(self.dir, "applications", "muster-senior-engineer")
        self.evidence = parse_evidence(EVIDENCE)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def g(self, variant):
        return guard.check(self.package, os.path.join(self.dir, "profile", "cv.yaml"),
                           os.path.join(self.dir, "profile", "evidence.md"),
                           os.path.join(self.dir, "GUARDRAILS.md"), variant=variant)


class Prompt(Workspace):
    def test_prompt_contains_rules_paths_and_facts(self):
        text = build_prompt(self.package, self.cfg)
        self.assertIn("Warnformulierungen", text)                    # GUARDRAILS.md wörtlich
        self.assertIn("applications/muster-senior-engineer/job.md", text)
        self.assertIn("profile/evidence.md", text)
        self.assertIn("Nicht vertrauenswürdiger Text", text)
        self.assertIn("Frühester Stellenantritt", text)              # aus dem Code, nicht vom Modell
        self.assertIn("applications/muster-senior-engineer/cv.yaml", text)
        self.assertNotIn("Team von 10 Personen", text)               # Belege nur als Pfad, nie eingebettet
        self.assertLess(len(text), PROMPT_LIMIT)

    def test_prompt_needs_confirmed_evidence(self):
        open(os.path.join(self.dir, "profile", "evidence.md"), "w").write(
            "## R1 | Dev | X | Bern | 2020\n- E1 [unbestätigt]: Etwas.\n")
        with self.assertRaises(ConfigError):
            build_prompt(self.package, self.cfg)

    def test_prompt_cli_writes_file(self):
        out = os.path.join(self.dir, "auftrag.md")
        open(os.path.join(self.dir, "jobhunter.yml"), "w").write(
            "locations: [{name: x, places: [Bern]}]\nagent: copilot-cli\n")
        os.chdir(self.dir)
        try:
            code = prepare_main(["prompt", self.package, "--out", out])
        finally:
            os.chdir(ROOT)
        self.assertEqual(code, 0)
        self.assertIn("# Auftrag", open(out).read())


class Finish(Workspace):
    def write_agent_files(self, variant=VARIANT):
        for name, text in (("cv.yaml", variant), ("fit.md", FIT), ("prep.md", PREP)):
            open(os.path.join(self.package, name), "w").write(text)

    def test_missing_agent_files(self):
        code, message = finish(self.package, self.cfg)
        self.assertEqual(code, 3)
        self.assertIn("cv.yaml", message)

    def test_finish_adds_facts_and_runs_guard(self):
        self.write_agent_files()
        code, message = finish(self.package, self.cfg)
        self.assertEqual(code, 0, message)
        app = open(os.path.join(self.package, "application.md")).read()
        self.assertIn("deadline: 2026-12-01", app)
        prep = open(os.path.join(self.package, "prep.md")).read()
        self.assertIn("Frühester Stellenantritt", prep)
        self.assertIn("salarium", prep)
        self.assertNotIn("vom Modell, muss ersetzt werden", prep)   # Modell-Abschnitt ersetzt
        self.assertIn("## Fragen an die Firma", prep)                # Rest bleibt
        self.assertIn("bestanden", open(os.path.join(self.package, "guard.md")).read())
        finish(self.package, self.cfg)                               # zweimal = gleich
        self.assertEqual(open(os.path.join(self.package, "prep.md")).read().count("## Rahmenbedingungen"), 1)

    def test_guard_problems_are_reported_not_hidden(self):
        self.write_agent_files(VARIANT.replace("evidence: [E1, E2]\nexperience", "evidence: [E3]\nexperience"))
        code, message = finish(self.package, self.cfg)
        self.assertEqual(code, 4)
        self.assertIn("unbestätigt", open(os.path.join(self.package, "guard.md")).read())

    def test_already_applied_warning(self):
        other = os.path.join(self.dir, "applications", "muster-frueher")
        os.makedirs(other)
        open(os.path.join(other, "application.md"), "w").write(
            '---\nstatus: submitted\ncompany: "Muster AG"\nrole: "Dev"\n---\n\n# Bewerbung\n')
        self.write_agent_files()
        finish(self.package, self.cfg)
        self.assertIn("⚠️", open(os.path.join(self.package, "fit.md")).read())


class Guard(Workspace):
    def test_clean_variant(self):
        variant = {"summary": GOOD["summary"], "experience": [{"role": "R1", "bullets": ["B1", "B2"]}]}
        self.assertEqual(self.g(variant), [])

    def test_missing_evidence_and_red_flags(self):
        variant = {"experience": [{"role": "R1", "bullets": [
            {"text": "Expert in React, zero downtime releases", "evidence": ["E1"]},
            {"text": "Etwas ohne Beleg", "evidence": []}]}]}
        issues = "\n".join(self.g(variant))
        self.assertIn("zero downtime", issues)
        self.assertIn("expert in", issues)
        self.assertIn("ohne Beleg", issues)

    def test_hobby_level_and_unconfirmed(self):
        variant = {"skills": [{"category": "Sprachen", "items": "Rust", "evidence": ["E4"]},
                              {"category": "Betrieb", "items": "Kubernetes", "evidence": ["E5"]},
                              {"category": "Führung", "items": "Teamführung", "evidence": ["E3"]}]}
        issues = "\n".join(self.g(variant))
        self.assertIn("Hobby", issues)
        self.assertIn("Niveau", issues)
        self.assertIn("unbestätigt", issues)

    def test_letter_red_flag(self):
        variant = {"letter": {"paragraphs": [{"text": "Ich leitete ein Team von zwanzig.", "evidence": []}]}}
        self.assertTrue(any("leitete ein team" in i for i in self.g(variant)))

    def test_repository_example_is_clean(self):
        # Gegen das Musterprofil (Kopie in tests/fixtures), nicht gegen profile/:
        # dort steht nach der Einrichtung das echte Profil der Person.
        os.chdir(ROOT)
        fixture = dict(base_path="tests/fixtures/beispiel/cv.yaml",
                       evidence_path="tests/fixtures/beispiel/evidence.md")
        self.assertEqual(guard.check(**fixture), [])
        self.assertEqual(guard.check("applications/_beispiel-fabrikam-tech-lead", **fixture), [])


if __name__ == "__main__":
    unittest.main()
