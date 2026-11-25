"""Workflow-Bedingungen (offline): keine Falle mit Ausgaben übersprungener Schritte."""

import glob
import os
import re
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUMERIC_EQ = re.compile(r"steps\.([\w-]+)\.outputs\.[\w-]+\s*==\s*'\d+'")


def conditions(path):
    data = yaml.safe_load(open(path, encoding="utf-8"))
    for job in (data.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if "if" in step:
                yield step.get("name") or step.get("uses") or "?", str(step["if"]), step


class Conditions(unittest.TestCase):
    def test_numeric_output_comparison_needs_outcome(self):
        """`steps.x.outputs.code == '0'` ist auch wahr, wenn x übersprungen wurde
        (null == '0' wird zu 0 == 0). Darum muss dieselbe Bedingung prüfen, dass x lief."""
        for path in glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml")):
            for name, cond, _ in conditions(path):
                for step_id in NUMERIC_EQ.findall(cond):
                    self.assertIn(f"steps.{step_id}.outcome == 'success'", cond,
                                  f"{os.path.basename(path)}: «{name}»")

    def test_prepare_pr_only_for_copilot_cli(self):
        path = os.path.join(ROOT, ".github", "workflows", "prepare.yml")
        for name, cond, step in conditions(path):
            if step.get("run", "").strip() == "scripts/paket-pr.sh":
                self.assertIn("steps.fetch.outputs.agent == 'copilot-cli'", cond, name)
                self.assertEqual(step["env"]["SOURCE"], "der GitHub Copilot CLI")

    def test_paket_workflow_pr_needs_paket_kind(self):
        path = os.path.join(ROOT, ".github", "workflows", "paket.yml")
        found = False
        for name, cond, step in conditions(path):
            if step.get("run", "").strip() == "scripts/paket-pr.sh":
                found = True
                self.assertIn("steps.read.outputs.kind == 'paket'", cond)
                self.assertIn("Kopieren", step["env"]["SOURCE"])
        self.assertTrue(found)


    def test_pdfs_uploaded_in_same_run_before_pr(self):
        """Bot-PRs starten build.yml nicht ohne Freigabe: der Paket-Lauf lädt die PDFs selbst hoch."""
        for name in ("prepare.yml", "paket.yml"):
            data = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8"))
            steps = next(iter(data["jobs"].values()))["steps"]
            pr = next(i for i, st in enumerate(steps) if st.get("run", "").strip() == "scripts/paket-pr.sh")
            upload = [i for i, st in enumerate(steps)
                      if str(st.get("uses", "")).startswith("actions/upload-artifact")]
            self.assertTrue(upload and upload[0] < pr, name)
            self.assertEqual(steps[upload[0]]["with"]["name"], "lebenslauf-pdfs")
            self.assertEqual(steps[upload[0]]["if"], steps[pr]["if"], name)
            self.assertIn("actions/runs/${{ github.run_id }}", steps[pr]["env"]["RUN_URL"])

    def _job(self, name):
        data = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8"))
        return data, next(iter(data["jobs"].values()))

    def test_stand_only_owner_and_bot_comment(self):
        data, job = self._job("stand.yml")
        self.assertEqual(data[True]["issue_comment"]["types"], ["edited"])   # «on:» liest YAML als True
        cond = job["if"]
        self.assertIn("github.event.sender.login == github.repository_owner", cond)
        self.assertIn("github.event.comment.user.login == 'github-actions[bot]'", cond)
        self.assertIn("<!-- jobhunter:stand slug=", cond)
        self.assertNotEqual(job.get("concurrency"), "records")

    def test_application_issue_adds_checklist_once(self):
        text = open(os.path.join(ROOT, ".github", "workflows", "application-issue.yml"),
                    encoding="utf-8").read()
        self.assertIn('scripts/stand-kommentar.sh "$number" "$slug" create', text)
        script = open(os.path.join(ROOT, "scripts", "stand-kommentar.sh"), encoding="utf-8").read()
        self.assertIn('[ -n "$existing" ] && [ "$mode" != "update" ]', script)

    def test_ergaenzen_trusts_only_owner(self):
        data, job = self._job("ergaenzen.yml")
        cond = job["if"]
        self.assertIn("github.event.issue.user.login == github.repository_owner", cond)
        self.assertIn("github.event.comment.user.login == github.repository_owner", cond)
        self.assertIn("startsWith(github.event.comment.body, '/ergaenzen')", cond)
        for step in job["steps"]:
            run = step.get("run", "")
            self.assertNotIn("${{ github.event.issue.body", run, step.get("name"))
            self.assertNotIn("${{ github.event.comment.body", run, step.get("name"))
            if step.get("uses") == "./.github/actions/copilot-cli":
                self.assertEqual(step["with"]["write"], "ergaenzung.yaml")
        commands = open(os.path.join(ROOT, ".github", "workflows", "commands.yml"), encoding="utf-8").read()
        self.assertIn("!startsWith(github.event.comment.body, '/ergaenzen')", commands)

    def test_form_heading_matches_workflow(self):
        form = yaml.safe_load(open(os.path.join(ROOT, ".github", "ISSUE_TEMPLATE", "profil-ergaenzen.yml"),
                                   encoding="utf-8"))
        labels = [b["attributes"]["label"] for b in form["body"] if b["type"] != "markdown"]
        self.assertEqual(labels[0], "Was ist neu?")
        self.assertTrue(form["body"][1]["validations"]["required"])
        self.assertIn("profil-ergaenzen", form["labels"])

    def test_belege_scope_for_ergaenzen(self):
        text = open(os.path.join(ROOT, ".github", "workflows", "belege.yml"), encoding="utf-8").read()
        self.assertIn("ergaenzen/*)", text)
        self.assertIn("--scope-boxes", text)
        self.assertIn("Profil-Ergänzung entworfen", text)
        script = open(os.path.join(ROOT, "scripts", "ergaenzen-pr.sh"), encoding="utf-8").read()
        self.assertIn('git commit -m "Profil-Ergänzung entworfen', script)
        self.assertIn('--only "$NEW_IDS"', script)


if __name__ == "__main__":
    unittest.main()
