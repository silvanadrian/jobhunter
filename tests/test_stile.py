"""Stile von Lebenslauf und Brief (klassisch, schlicht, kompakt): bauen mit Typst
und Seitenzahlen prüfen. Ohne `typst` im PATH werden die Tests übersprungen."""

import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPST = shutil.which(os.environ.get("TYPST", "typst"))
EXAMPLE = os.path.join(ROOT, "applications", "_beispiel-fabrikam-tech-lead", "cv.yaml")
THEMES = ("klassisch", "schlicht", "kompakt")
# Musterprofil als Basis (nicht profile/: dort steht später das echte Profil).
FLAGS = ["--root", ROOT, "--font-path", os.path.join(ROOT, "fonts"), "--ignore-system-fonts",
         "--input", "profile=/tests/fixtures/beispiel/cv.yaml"]


@unittest.skipUnless(TYPST, "typst ist nicht installiert")
class Styles(unittest.TestCase):
    def setUp(self):
        # Varianten müssen unter --root liegen; build/ ist in .gitignore.
        os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
        self.tmp = tempfile.mkdtemp(prefix="stil-test-", dir=os.path.join(ROOT, "build"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def variant(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return "/" + os.path.relpath(path, ROOT).replace(os.sep, "/")

    def run_typst(self, *args):
        return subprocess.run([TYPST, *args], cwd=ROOT, capture_output=True, text=True)

    def pages(self, source, variant):
        inputs = ["--input", "variant=" + variant]
        out = os.path.join(self.tmp, "out.pdf")
        res = self.run_typst("compile", *FLAGS, *inputs, source, out)
        self.assertEqual(res.returncode, 0, res.stderr)
        res = self.run_typst("query", *FLAGS, *inputs, source, "<page-count>",
                             "--field", "value", "--one")
        self.assertEqual(res.returncode, 0, res.stderr)
        return int(res.stdout.strip())

    def test_all_styles_fit(self):
        with open(EXAMPLE, encoding="utf-8") as f:
            example = f.read()
        for theme in THEMES:
            with self.subTest(theme=theme):
                style = f"\nstyle:\n  theme: {theme}\n"
                base = self.variant(f"basis-{theme}.yaml", style)
                self.assertLessEqual(self.pages("cv/cv.typ", base), 2)
                var = self.variant(f"beispiel-{theme}.yaml", example + style)
                self.assertLessEqual(self.pages("cv/cv.typ", var), 2)
                self.assertEqual(self.pages("cv/letter.typ", var), 1)

    def test_invalid_values_fail_loudly(self):
        cases = {
            "theme: modern": "ungültiger Stil",
            'accent: "blau"': "ungültige Farbe",
            "accent: #0084B8": "Anführungszeichen",
            "photo: nein": "true oder false",
            "farbe: rot": "unbekannter Schlüssel",
        }
        for line, message in cases.items():
            with self.subTest(line=line):
                var = self.variant("falsch.yaml", f"style:\n  {line}\n")
                res = self.run_typst("compile", *FLAGS, "--input", "variant=" + var,
                                     "cv/cv.typ", os.path.join(self.tmp, "falsch.pdf"))
                self.assertNotEqual(res.returncode, 0)
                self.assertIn(message, res.stderr)


if __name__ == "__main__":
    unittest.main()
