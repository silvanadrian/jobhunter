"""Updates der Vorlage (offline, mit temporären Git-Repositories)."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

from jobwatch import vorlage


def run(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout


def write(root, path, text):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as handle:
        handle.write(text)


def read(root, path):
    with open(os.path.join(root, path), encoding="utf-8") as handle:
        return handle.read()


def init_repo(root, files):
    os.makedirs(root, exist_ok=True)
    run(root, "init", "-q", "-b", "main")
    run(root, "config", "user.name", "Test")
    run(root, "config", "user.email", "test@example.com")
    run(root, "config", "commit.gpgsign", "false")
    for path, text in files.items():
        write(root, path, text)
    run(root, "add", "-A")
    run(root, "commit", "-q", "-m", "Initial commit")


TEMPLATE = {
    "README.md": "Vorlage v1\n",
    "jobwatch/cli.py": "print(1)\n",
    "jobwatch/alt.py": "alt\n",
    ".github/workflows/build.yml": "name: build v1\n",
    "applications/_vorlage/fit.md": "fit v1\n",
    "jobhunter.yml": "search: vorlage\n",
    "profile/cv.yaml": "name: Alex Muster\n",
}


class Paths(unittest.TestCase):
    def test_template_paths(self):
        for path in ("README.md", "GUARDRAILS.md", "Makefile", "jobhunter.example.yml",
                     ".github/workflows/build.yml", ".github/ISSUE_TEMPLATE/profil.yml",
                     "jobwatch/cli.py", "cv/cv.typ", "scripts/build-cv.sh", "fonts/x.ttf",
                     "docs/FORTGESCHRITTEN.md", "tests/test_x.py",
                     "applications/_vorlage/fit.md", "applications/README.md"):
            self.assertTrue(vorlage.is_template_path(path), path)

    def test_personal_paths_never(self):
        for path in ("jobhunter.yml", "profile/cv.yaml", "profile/evidence.md",
                     "profile/foto.jpg", "profile/dokumente/README.md",
                     "applications/acme-lead/cv.yaml", "applications/acme_x/job.md",
                     ".jobwatch/seen.json", ".jobwatch/vorlage.json", "notizen.md",
                     "cvx/a.typ", "docsx", "README.md.bak"):
            self.assertFalse(vorlage.is_template_path(path), path)

    def test_workflow_paths(self):
        self.assertTrue(vorlage.is_workflow_path(".github/workflows/x.yml"))
        self.assertFalse(vorlage.is_workflow_path(".github/actions/a/action.yml"))


class Changes(unittest.TestCase):
    def test_added_changed_deleted_only_template(self):
        local = {"README.md": "a", "jobwatch/x.py": "1", "jobwatch/weg.py": "1",
                 "profile/cv.yaml": "mein", "jobhunter.yml": "mein"}
        upstream = {"README.md": "b", "jobwatch/x.py": "1", "jobwatch/neu.py": "1",
                    "profile/cv.yaml": "vorlage", "jobhunter.yml": "vorlage",
                    "profile/neu.md": "x"}
        changes = vorlage.compute_changes(local, upstream)
        self.assertEqual(changes, {"added": ["jobwatch/neu.py"], "changed": ["README.md"],
                                   "deleted": ["jobwatch/weg.py"]})

    def test_own_files_in_template_folders_stay(self):
        local = {"docs/meine-notiz.md": "x", "docs/alt.md": "y"}
        changes = vorlage.compute_changes(local, {}, base={"docs/alt.md"})
        self.assertEqual(changes["deleted"], ["docs/alt.md"])

    def test_fingerprint_stable_and_sensitive(self):
        up1 = {"README.md": ("100644", "aaa")}
        up2 = {"README.md": ("100644", "bbb")}
        ch = {"added": [], "changed": ["README.md"], "deleted": []}
        self.assertEqual(vorlage.fingerprint(ch, up1), vorlage.fingerprint(ch, up1))
        self.assertNotEqual(vorlage.fingerprint(ch, up1), vorlage.fingerprint(ch, up2))

    def test_offered_and_open_pr(self):
        prs = [{"number": 3, "state": "CLOSED", "body": "x\n<!-- jobhunter-vorlage: abc123 -->"},
               {"number": 5, "state": "OPEN", "body": "<!-- jobhunter-vorlage: def456 -->"}]
        self.assertEqual(vorlage.offered(prs, "abc123")["number"], 3)
        self.assertIsNone(vorlage.offered(prs, "999"))
        self.assertEqual(vorlage.open_pr(prs)["number"], 5)
        self.assertIsNone(vorlage.open_pr(prs[:1]))


class Body(unittest.TestCase):
    def plan(self, pending=()):
        return {"upstream": "owner/jobhunter", "repo": "me/stellensuche", "base": "main",
                "commit": "0123456789abcdef", "fingerprint": "f00",
                "changes": {"added": ["jobwatch/neu.py", ".github/workflows/neu.yml"],
                            "changed": ["README.md", ".github/workflows/build.yml"],
                            "deleted": ["docs/alt.md"]},
                "pending": list(pending)}

    def test_text_for_laypeople(self):
        body = vorlage.pr_body(self.plan())
        self.assertIn("persönlichen Daten werden nicht angefasst", body)
        self.assertIn("«Merge pull request»", body)
        self.assertIn("«Confirm merge»", body)
        self.assertIn("offen lassen oder schliessen", body)
        self.assertIn("<details>", body)
        self.assertIn("- geändert: `README.md`", body)
        self.assertIn("- gelöscht: `docs/alt.md`", body)
        self.assertIn("<!-- jobhunter-vorlage: f00 -->", body)
        self.assertNotIn("ß", body)
        self.assertNotIn("von Hand", body)

    def test_pending_workflows_listed_with_instructions(self):
        body = vorlage.pr_body(self.plan([".github/workflows/neu.yml",
                                          ".github/workflows/build.yml"]))
        self.assertIn("von Hand", body)
        self.assertIn("https://github.com/owner/jobhunter/blob/0123456789abcdef/.github/workflows/build.yml", body)
        self.assertIn("https://github.com/me/stellensuche/edit/main/.github/workflows/build.yml", body)
        self.assertIn("https://github.com/me/stellensuche/new/main/.github/workflows?filename=neu.yml", body)
        self.assertIn("Geänderte Dateien (3)", body)
        self.assertNotIn("ß", body)


class WithGit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.up = os.path.join(self.tmp, "vorlage")
        self.copy = os.path.join(self.tmp, "kopie")
        init_repo(self.up, TEMPLATE)
        # «Use this template»: die Kopie startet mit einem eigenen ersten Commit.
        init_repo(self.copy, TEMPLATE)
        write(self.copy, "jobhunter.yml", "search: meine\n")
        write(self.copy, "profile/cv.yaml", "name: Ich\n")
        write(self.copy, "docs/meine-notiz.md", "eigene Datei\n")
        run(self.copy, "add", "-A")
        run(self.copy, "commit", "-q", "-m", "Einrichtung")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def new_template_version(self):
        write(self.up, "README.md", "Vorlage v2\n")
        write(self.up, "jobwatch/neu.py", "neu\n")
        os.remove(os.path.join(self.up, "jobwatch/alt.py"))
        write(self.up, ".github/workflows/build.yml", "name: build v2\n")
        write(self.up, "profile/cv.yaml", "name: Alex Muster v2\n")
        write(self.up, "jobhunter.yml", "search: vorlage v2\n")
        run(self.up, "add", "-A")
        run(self.up, "commit", "-q", "-m", "v2")

    def fetch(self):
        run(self.copy, "fetch", "-q", self.up, "HEAD")

    def test_up_to_date(self):
        self.fetch()
        result = vorlage.plan("owner/jobhunter", "FETCH_HEAD", cwd=self.copy)
        self.assertEqual(result["status"], "same")

    def test_plan_apply_and_no_repeat(self):
        self.new_template_version()
        self.fetch()
        result = vorlage.plan("owner/jobhunter", "FETCH_HEAD", cwd=self.copy)
        self.assertEqual(result["status"], "new")
        self.assertEqual(result["changes"], {
            "added": ["jobwatch/neu.py"],
            "changed": [".github/workflows/build.yml", "README.md"],
            "deleted": ["jobwatch/alt.py"]})
        self.assertEqual(result["pending"], [".github/workflows/build.yml"])
        self.assertIsNone(result["open_pr"])

        vorlage.apply(result, "FETCH_HEAD", cwd=self.copy)
        self.assertEqual(read(self.copy, "README.md"), "Vorlage v2\n")
        self.assertEqual(read(self.copy, "jobwatch/neu.py"), "neu\n")
        self.assertFalse(os.path.exists(os.path.join(self.copy, "jobwatch/alt.py")))
        # Persönliches, eigene Dateien und Abläufe ohne Token bleiben.
        self.assertEqual(read(self.copy, "jobhunter.yml"), "search: meine\n")
        self.assertEqual(read(self.copy, "profile/cv.yaml"), "name: Ich\n")
        self.assertEqual(read(self.copy, "docs/meine-notiz.md"), "eigene Datei\n")
        self.assertEqual(read(self.copy, ".github/workflows/build.yml"), "name: build v1\n")
        state = json.loads(read(self.copy, vorlage.STATE_FILE))
        self.assertEqual(state["fingerprint"], result["fingerprint"])
        self.assertIn("jobwatch/neu.py", state["files"])
        self.assertNotIn("profile/cv.yaml", state["files"])
        staged = run(self.copy, "diff", "--cached", "--name-only").split()
        self.assertEqual(sorted(staged), sorted([".jobwatch/vorlage.json", "README.md",
                                                 "jobwatch/alt.py", "jobwatch/neu.py"]))

        # Entwurf geschlossen, Vorlage unverändert: kein neues Angebot.
        run(self.copy, "reset", "-q", "--hard")
        prs = [{"number": 7, "state": "CLOSED", "body": vorlage.pr_body(result)}]
        again = vorlage.plan("owner/jobhunter", "FETCH_HEAD", prs, cwd=self.copy)
        self.assertEqual((again["status"], again["pr"]), ("offered", 7))

        # Neue Version der Vorlage: neues Angebot.
        write(self.up, "cv/cv.typ", "neu\n")
        run(self.up, "add", "-A")
        run(self.up, "commit", "-q", "-m", "v3")
        self.fetch()
        third = vorlage.plan("owner/jobhunter", "FETCH_HEAD", prs, cwd=self.copy)
        self.assertEqual(third["status"], "new")
        self.assertIn("cv/cv.typ", third["changes"]["added"])

    def test_with_token_workflows_come_along(self):
        self.new_template_version()
        self.fetch()
        result = vorlage.plan("owner/jobhunter", "FETCH_HEAD", include_workflows=True, cwd=self.copy)
        self.assertEqual(result["pending"], [])
        self.assertTrue(result["fingerprint"].endswith("+w"))
        vorlage.apply(result, "FETCH_HEAD", cwd=self.copy)
        with open(os.path.join(self.copy, ".github/workflows/build.yml"), encoding="utf-8") as h:
            self.assertEqual(h.read(), "name: build v2\n")

    def test_merged_state_limits_deletions(self):
        # Nach einem übernommenen Update gilt die Dateiliste aus .jobwatch/vorlage.json.
        write(self.copy, vorlage.STATE_FILE, json.dumps({"files": ["README.md", "jobwatch/cli.py"]}))
        run(self.copy, "add", "-A")
        run(self.copy, "commit", "-q", "-m", "Update übernommen")
        os.remove(os.path.join(self.up, "jobwatch/alt.py"))
        os.remove(os.path.join(self.up, "jobwatch/cli.py"))
        run(self.up, "add", "-A")
        run(self.up, "commit", "-q", "-m", "weg")
        self.fetch()
        result = vorlage.plan("owner/jobhunter", "FETCH_HEAD", cwd=self.copy)
        self.assertEqual(result["changes"]["deleted"], ["jobwatch/cli.py"])

    def test_open_pr_is_updated(self):
        self.new_template_version()
        self.fetch()
        prs = [{"number": 4, "state": "OPEN", "body": "<!-- jobhunter-vorlage: alt -->"}]
        result = vorlage.plan("owner/jobhunter", "FETCH_HEAD", prs, cwd=self.copy)
        self.assertEqual((result["status"], result["open_pr"]), ("new", 4))

    def test_cli_outputs(self):
        self.new_template_version()
        self.fetch()
        out, body = os.path.join(self.tmp, "plan.json"), os.path.join(self.tmp, "pr.md")
        proc = subprocess.run(
            ["python3", "-m", "jobwatch.vorlage", "plan", "--upstream", "owner/jobhunter",
             "--repo", "me/kopie", "--out", out, "--body", body],
            cwd=self.copy, capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("status=new", proc.stdout)
        self.assertIn("open_pr=\n", proc.stdout)
        with open(body, encoding="utf-8") as h:
            self.assertIn("Neue Version der Vorlage", h.read())


class Workflow(unittest.TestCase):
    def test_update_workflow(self):
        import yaml
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, ".github", "workflows", "update.yml"), encoding="utf-8") as h:
            data = yaml.safe_load(h)
        self.assertEqual(data["permissions"], {"contents": "write", "pull-requests": "write"})
        triggers = data[True]  # YAML liest «on» als True
        self.assertIn("schedule", triggers)
        self.assertIn("workflow_dispatch", triggers)
        text = read(root, ".github/workflows/update.yml")
        self.assertIn("JOBHUNTER_UPDATE_TOKEN", text)
        self.assertIn("JOBHUNTER_UPSTREAM", text)
        self.assertIn("template_repository", text)


if __name__ == "__main__":
    unittest.main()
