"""Kopieren & Einfügen: Auftrag, Antworten aus Chats (unordentlich), Ende-zu-Ende (offline)."""

import os
import shutil
import tempfile
import unittest

from jobwatch import kopieren
from jobwatch.kopieren import (AnswerError, apply_paket, apply_profil, build_paket_prompt,
                               comment_paket, find_slug, parse_answer)
from jobwatch.prepare import finish
from tests.test_guard import BASE, EVIDENCE, ROOT, Workspace

ANSWER = """slug: muster-senior-engineer
cv:
  lang: de
  position: ""
  summary:
    text: "Engineer mit Erfahrung in React und Testautomatisierung."
    evidence: [E1, E2]
  experience:
    - role: R1
      bullets:
        - id: B2
        - text: "Kundenportal mit React weiterentwickelt"
          evidence: [E1]
  skills:
    - category: "Web"
      items: "React, Playwright"
      evidence: [E1, E2]
letter:
  recipient: "Muster AG"
  recipient_address: ["Musterweg 1", "3000 Bern"]
  title: "Bewerbung als Senior Engineer"
  opening: "Sehr geehrte Damen und Herren"
  paragraphs:
    - text: "Ich habe Playwright-Tests eingeführt."
      evidence: [E2]
    - text: "Führungserfahrung bringe ich noch nicht mit; das sage ich offen."
      evidence: []
  closing: "Freundliche Grüsse"
fit_md: |
  # Passung: Senior Engineer bei Muster AG

  **Empfehlung:** bewerben — Kern passt.

  | Anforderung | Passung | Belege | Bemerkung |
  |---|---|---|---|
  | React | erfüllt | [E1] | täglich |
  | Führung | LÜCKE | — | offen ansprechen |
prep_md: |
  # Vorbereitung Vorstellungsgespräch: Senior Engineer bei Muster AG

  ## Wahrscheinliche Fragen und Antwortskizzen (STAR)

  1. **Tests?** Playwright eingeführt [E2].
"""


class Prompt(Workspace):
    def test_prompt_has_rules_and_only_confirmed_evidence(self):
        prompt, warnings = build_paket_prompt(self.package, self.cfg)
        self.assertIn("Warnformulierungen", prompt)                 # GUARDRAILS.md wörtlich
        self.assertIn("E1 (R1): Webportal mit React", prompt)
        self.assertIn("E5", prompt)
        self.assertNotIn("Team von 10 Personen", prompt)            # E3 ist unbestätigt
        self.assertNotIn("- E3", prompt)
        self.assertIn("B2: Tests mit Playwright", prompt)           # Basis-IDs
        self.assertIn("slug: muster-senior-engineer", prompt)
        self.assertIn("Frühester Stellenantritt", prompt)
        self.assertIn("React, Führung.", prompt)                     # das Inserat selbst
        self.assertEqual(warnings, [])

    def test_size_cap_trims_least_relevant_evidence(self):
        many = EVIDENCE + "".join(f"- E{n} [bestätigt]: Gartenbau und Floristik Projekt {n} " + "x" * 300 + "\n"
                                  for n in range(10, 80))
        open(os.path.join(self.dir, "profile", "evidence.md"), "w").write(many)
        prompt, warnings = build_paket_prompt(self.package, self.cfg, budget=4000)
        self.assertTrue(any("weggelassen" in w for w in warnings))
        self.assertIn("Webportal mit React", prompt)                 # passt zum Inserat: bleibt
        belege = prompt.split("BELEGE")[1].split("BASIS-LEBENSLAUF")[0]
        self.assertLess(len(belege), 4000)

    def test_comment_has_steps_privacy_and_one_block(self):
        text = comment_paket(self.package, self.cfg)
        self.assertIn("1. Den ganzen Block", text)
        self.assertIn("`/paket`", text)
        self.assertIn("Training", text)
        self.assertEqual(text.count("````text"), 1)
        self.assertNotIn("\u00df", text.split("REGELN")[0])


class Parser(unittest.TestCase):
    def test_prose_around_yaml_fence(self):
        msg = ("/paket\nGerne! Hier ist das Paket:\n\n```yaml\n" + ANSWER + "```\n\n"
               "Viel Erfolg bei der Bewerbung! Sag Bescheid, wenn du Änderungen willst.")
        data = parse_answer(msg, ("cv", "letter"))
        self.assertEqual(data["cv"]["experience"][0]["role"], "R1")
        self.assertIn("| React |", data["fit_md"])

    def test_without_fence_and_trailing_prose(self):
        msg = "/paket\n" + ANSWER + "\nIch hoffe, das hilft!\n"
        data = parse_answer(msg, ("cv", "letter"))
        self.assertEqual(data["slug"], "muster-senior-engineer")

    def test_json_fence_crlf_tabs_and_nbsp(self):
        import json
        import yaml
        obj = yaml.safe_load(ANSWER)
        msg = "/paket\r\nHere you go:\r\n```json\r\n" + json.dumps(obj, ensure_ascii=False, indent="\t") \
              .replace("\n", "\r\n") + "\r\n```\r\n"
        self.assertEqual(parse_answer(msg, ("cv",))["letter"]["closing"], "Freundliche Grüsse")
        nbsp = "/paket\n```yaml\n" + ANSWER.replace("  summary:", "  summary:") + "```"
        self.assertIn("summary", parse_answer(nbsp, ("cv",))["cv"])

    def test_tilde_fence_and_slug_from_issue(self):
        msg = "/paket\n~~~\n" + ANSWER.replace("slug: muster-senior-engineer\n", "") + "~~~\n"
        self.assertEqual(find_slug(msg, "Text <!-- paket:muster-senior-engineer --> mehr"),
                         "muster-senior-engineer")
        with self.assertRaises(AnswerError):
            find_slug(msg, "kein Marker")

    def test_garbage_is_rejected(self):
        with self.assertRaises(AnswerError) as ctx:
            parse_answer("/paket\nTut mir leid, das kann ich nicht.", ("cv", "letter"))
        self.assertIn("YAML", str(ctx.exception))

    def test_missing_keys_are_named(self):
        broken = ANSWER.split("fit_md:")[0]                          # fit_md und prep_md fehlen
        broken = broken.replace("    evidence: [E1, E2]\n  experience", "  experience")
        d = tempfile.mkdtemp()
        try:
            with self.assertRaises(AnswerError) as ctx:
                apply_paket("/paket\n```yaml\n" + broken + "```", d)
            message = str(ctx.exception)
            self.assertIn("fit_md", message)
            self.assertIn("prep_md", message)
            self.assertIn("cv.summary.evidence", message)
            self.assertFalse(os.path.exists(os.path.join(d, "cv.yaml")))
        finally:
            shutil.rmtree(d)


class EndToEnd(Workspace):
    def test_apply_then_finish_and_guard(self):
        apply_paket("/paket\nHier:\n```yaml\n" + ANSWER + "```\nViel Glück!", self.package)
        code, message = finish(self.package, self.cfg)
        self.assertEqual(code, 0, open(os.path.join(self.package, "guard.md")).read())
        variant = open(os.path.join(self.package, "cv.yaml")).read()
        self.assertIn("- B2", variant)
        self.assertIn("Kopieren & Einfügen", variant)
        prep = open(os.path.join(self.package, "prep.md")).read()
        self.assertIn("Frühester Stellenantritt", prep)              # vom Code ergänzt
        self.assertIn("deadline: 2026-12-01", open(os.path.join(self.package, "application.md")).read())
        # Erneut posten ersetzt den Entwurf (gleicher Ordner, gleicher PR).
        apply_paket("/paket\n```yaml\n" + ANSWER.replace("täglich", "seit 2020") + "```", self.package)
        self.assertIn("seit 2020", open(os.path.join(self.package, "fit.md")).read())

    def test_unconfirmed_evidence_fails_guard(self):
        apply_paket("/paket\n" + ANSWER.replace("evidence: [E1, E2]\n  experience",
                                                "evidence: [E3]\n  experience"), self.package)
        code, _ = finish(self.package, self.cfg)
        self.assertEqual(code, 4)


class Profil(unittest.TestCase):
    ANSWER = """```yaml
profil:
  person:
    first_name: "Alex"
    last_name: "Muster"
    email: ""
  roles:
    - title: "Senior Engineer"
      org: "Contoso AG"
      location: "Zürich"
      dates: "2022 – heute"
      items:
        - "Kundenportal mit React weiterentwickelt"
        - "Playwright-Tests eingeführt"
    - title: "Engineer"
      org: "Northwind"
      dates: "2018 – 2022"
      items: ["REST-APIs in Python"]
  education:
    - degree: "BSc Informatik"
      school: "FH Bern"
      dates: "2018"
  skills:
    - category: "Web"
      items: "React, TypeScript"
  languages:
    - name: "Deutsch"
      level: "Muttersprache"
```"""

    def test_apply_profil_writes_unconfirmed_with_stable_ids(self):
        d = tempfile.mkdtemp()
        try:
            ev, cv = os.path.join(d, "evidence.md"), os.path.join(d, "cv.yaml")
            apply_profil("/profil\nHier dein Profil:\n" + self.ANSWER + "\nAlles klar?", ev, cv)
            evidence = open(ev).read()
            self.assertIn("## R1 | Senior Engineer | Contoso AG", evidence)
            self.assertIn("- E1 [unbestätigt]: Kundenportal mit React weiterentwickelt", evidence)
            self.assertIn("- E3 [unbestätigt]: REST-APIs in Python", evidence)
            self.assertNotRegex(evidence, r"E\d+ \[bestätigt\]")
            from jobwatch.forms import check_profile
            self.assertEqual(check_profile(ev, cv), [])
        finally:
            shutil.rmtree(d)

    def test_profil_without_roles(self):
        with self.assertRaises(AnswerError) as ctx:
            apply_profil("/profil\n```yaml\nprofil:\n  person: {first_name: A}\n  roles: []\n```",
                         "/nonexistent/e.md", "/nonexistent/c.yaml")
        self.assertIn("roles", str(ctx.exception))

    def test_profil_prompt_has_cv_and_privacy(self):
        text = kopieren.comment_profil("Lebenslauf " * 40, open(os.path.join(ROOT, "GUARDRAILS.md")).read())
        self.assertIn("`/profil`", text)
        self.assertIn("Training", text)
        self.assertIn("LEBENSLAUF\nLebenslauf", text)


if __name__ == "__main__":
    unittest.main()
