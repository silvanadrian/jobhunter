"""Assistent: Formularoptionen, veraltetes agent: models, Kommentare ohne Secret,
Profil-Entwurf der Copilot CLI, jobs.ch-Zeichen (offline)."""

import os
import shutil
import tempfile
import unittest

from jobwatch.agent import explain, fallback_message, local_steps, token_guide
from jobwatch.boards import fix_c1
from jobwatch.config import ConfigError, normalise, parse_agent
from jobwatch.forms import (apply_setup, build_profile_prompt, check_profile, form_agent,
                            force_unconfirmed, parse_form)
from jobwatch.wizard import agent_lines

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOC = {"locations": [{"name": "x", "places": ["Bern"]}]}
FORM = os.path.join(ROOT, ".github", "ISSUE_TEMPLATE", "einrichtung.yml")


class AgentOptions(unittest.TestCase):
    def test_default_is_kopieren(self):
        self.assertEqual(normalise(dict(LOC))["agent"], "kopieren")

    def test_form_options_map_to_config_values(self):
        import yaml
        form = yaml.safe_load(open(FORM, encoding="utf-8"))
        options = next(f for f in form["body"] if f.get("id") == "assistent")["attributes"]["options"]
        mapped = [form_agent(o) for o in options]
        self.assertEqual(mapped, ["kopieren", "copilot-cli", "none", "copilot", "claude"])
        # GitHub verbietet «None» als Option in Issue-Formularen.
        for field in form["body"]:
            for option in (field.get("attributes") or {}).get("options") or []:
                label = option if isinstance(option, str) else option.get("label", "")
                self.assertNotEqual(str(label).strip().lower(), "none")

    def test_aliases(self):
        self.assertEqual(parse_agent("lokal (ohne KI in GitHub)"), "none")
        self.assertEqual(parse_agent("Copilot-CLI"), "copilot-cli")
        self.assertEqual(parse_agent(""), "kopieren")
        self.assertEqual(parse_agent("Kopieren & Einfügen"), "kopieren")
        with self.assertRaises(ConfigError):
            parse_agent("gemini")

    def test_models_is_a_deprecated_alias_with_explanation(self):
        with self.assertRaises(ConfigError) as ctx:
            parse_agent("models")
        message = str(ctx.exception)
        self.assertIn("eingestellt", message)
        self.assertIn("kopieren", message)
        self.assertIn("copilot-cli", message)
        # Die tägliche Suche läuft trotzdem weiter; der Fehler erscheint im Status.
        cfg = normalise({**LOC, "agent": "models", "models": {"model": "x"}, "triage": {"enabled": False}})
        self.assertEqual(cfg["agent"], "models")
        self.assertIn("eingestellt", cfg["agent_error"])
        self.assertEqual(cfg["deprecated"], ["models", "triage"])
        self.assertEqual(agent_lines(cfg)[0][0], "fail")

    def test_form_with_models_is_rejected(self):
        body = "### Orte\n\nBern\n\n### Assistent für Bewerbungspakete\n\nmodels\n"
        d = tempfile.mkdtemp()
        try:
            with self.assertRaises(ConfigError):
                apply_setup(parse_form(body), os.path.join(d, "jobhunter.yml"))
            self.assertFalse(os.path.exists(os.path.join(d, "jobhunter.yml")))
        finally:
            shutil.rmtree(d)

    def test_status_lines(self):
        lines = " ".join(text for _, text in agent_lines(normalise(dict(LOC))))
        self.assertIn("Keine Secrets nötig", lines)
        cli = " ".join(text for _, text in agent_lines(normalise({**LOC, "agent": "copilot-cli"})))
        self.assertIn("GITHUB_TOKEN", cli)
        self.assertIn("COPILOT_GITHUB_TOKEN", cli)


class Fallback(unittest.TestCase):
    def test_missing_secret_explains_token_and_local_way(self):
        text = fallback_message("missing-secret", "paket", "prepare/muster-dev", "muster-dev")
        self.assertIn("COPILOT_GITHUB_TOKEN", text)
        self.assertIn("/paket", text)                       # Kopieren & Einfügen als Ausweg
        self.assertIn("Copilot Requests", text)
        self.assertIn("persönliches Konto", text)
        self.assertIn("git switch prepare/muster-dev", text)
        self.assertIn("python -m jobwatch.prepare finish applications/muster-dev", text)
        self.assertNotIn("\u00df", text)

    def test_known_errors_are_explained(self):
        for log, word in (("Error: Authentication failed", "Anmeldung"),
                          ("Access denied by policy settings", "Richtlinie"),
                          ("Your Copilot subscription does not include this feature", "Plan"),
                          ("rate limit exceeded, try later", "Kontingent"),
                          ("Classic Personal Access Tokens (ghp_) are not supported by Copilot", "ghp_")):
            hints = " ".join(explain(log))
            self.assertIn(word, hints, log)
        self.assertEqual(explain("alles gut"), [])
        text = fallback_message("failed", "paket", "b", "s", "1", "Error: Authentication failed")
        self.assertIn("Nur falls nötig", text)              # Token-Anleitung nur bei Anmeldefehler

    def test_failed_mentions_allowance_and_log(self):
        text = fallback_message("failed", "paket", "b", "s", exit_code="1", log_text="quota exceeded")
        self.assertIn("Exit-Code 1", text)
        self.assertIn("Kontingent", text)
        self.assertIn("quota exceeded", text)

    def test_retired_and_profile(self):
        self.assertIn("eingestellt", fallback_message("retired"))
        self.assertIn("profil-check", fallback_message("missing-secret", "profil"))
        self.assertIn("profil-prompt", local_steps("profil"))

    def test_token_guide_is_classic_free(self):
        guide = token_guide()
        self.assertIn("github.com/settings/personal-access-tokens/new", guide)
        self.assertIn("ghp_", guide)                       # klassische Tokens gehen nicht
        self.assertNotIn("\u00df", guide)


class ProfileDraft(unittest.TestCase):
    EVIDENCE = ("# Belege\n\n## R1 | Dev | X AG | Bern | 2020 – heute\n\n"
                "- E1 [bestätigt]: Baute Y. Quelle: Lebenslauf (Entwurf).\n"
                "- E2 [level: basic]: Kubernetes.\n"
                "- E3 [unbestätigt]: Tests.\n")
    CV = ("lang: de\nexperience:\n  - id: R1\n    title: Dev\n    bullets:\n"
          "      - {id: B1, text: Baute Y, evidence: [E1]}\n"
          "skills:\n  - {category: Betrieb, items: Kubernetes (Grundkenntnisse), evidence: [E2]}\n")

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ev, self.cv = os.path.join(self.dir, "evidence.md"), os.path.join(self.dir, "cv.yaml")
        open(self.ev, "w").write(self.EVIDENCE)
        open(self.cv, "w").write(self.CV)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_force_unconfirmed(self):
        text = force_unconfirmed(self.EVIDENCE)
        self.assertIn("- E1 [unbestätigt]: Baute Y", text)
        self.assertIn("- E2 [unbestätigt] [level: basic]: Kubernetes", text)
        self.assertEqual(text.count("[unbestätigt]"), 3)
        self.assertNotIn("[bestätigt]", text)

    def test_check_profile_clean_and_rewrites(self):
        self.assertEqual(check_profile(self.ev, self.cv), [])
        self.assertNotIn("[bestätigt]", open(self.ev).read())

    def test_check_profile_finds_unknown_ids(self):
        open(self.cv, "w").write(self.CV.replace("[E1]", "[E9]").replace("id: R1", "id: R7"))
        problems = "\n".join(check_profile(self.ev, self.cv))
        self.assertIn("E9", problems)
        self.assertIn("R7", problems)

    def test_profile_prompt(self):
        text = build_profile_prompt("cv.txt", ROOT)
        self.assertIn("cv.txt", text)
        self.assertIn("[unbestätigt]", text)
        self.assertIn("Warnformulierungen", text)


class JobsCh(unittest.TestCase):
    def test_cp1252_dash_from_c1_control(self):
        self.assertEqual(fix_c1("Engineer (80\x96100 %)"), "Engineer (80–100 %)")
        self.assertEqual(fix_c1("Zürich – Bern"), "Zürich – Bern")
        self.assertEqual(fix_c1("Dipl. Pflegefachperson HF/FH ? Psychiatrie 80?100 / Fest"),
                         "Dipl. Pflegefachperson HF/FH – Psychiatrie 80–100 / Fest")
        self.assertEqual(fix_c1("Lust auf mehr? Teamleitung (80%)"), "Lust auf mehr? Teamleitung (80%)")


if __name__ == "__main__":
    unittest.main()
