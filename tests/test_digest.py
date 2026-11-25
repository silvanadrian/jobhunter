"""Tägliches Issue: Ordnen, Pensum-Hinweis, Ein-Klick-Link (offline)."""
import os
import unittest
from unittest import mock

from jobwatch.digest import assess, build, percent_range

CONFIG = {"search": {"keywords": ["Pflegefachperson", "Psychiatrie", "HF"], "seniority": []},
          "profile": {"workload": "80–100%"}}


def job(title, company="A"):
    return {"region": "bern", "region_label": "Bern", "company": company, "title": title,
            "url": "https://www.jobs.ch/x/1/", "location": "Bern"}


class DigestTest(unittest.TestCase):
    def test_percent_range(self):
        self.assertEqual(percent_range("Pflege 80–100%"), (80, 100))
        self.assertEqual(percent_range("Pflege 80 - 100 %"), (80, 100))
        self.assertEqual(percent_range("Pflege 60%"), (60, 60))
        self.assertIsNone(percent_range("Pflege HF"))

    def test_assess(self):
        self.assertEqual(assess(job("Pflegefachperson HF Psychiatrie 80–100%"), CONFIG), (3, ""))
        score, hint = assess(job("Pflegefachperson 30–50%"), CONFIG)
        self.assertLess(score, 0)
        self.assertIn("Pensum 30–50", hint)

    def test_order_star_and_link(self):
        jobs = [job("Pflegefachperson 30–50%", "Zeta"), job("Pflegefachperson HF Psychiatrie 80%", "Alpha"),
                job("Pflegefachperson", "Beta")]
        env = {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "me/stellen"}
        with mock.patch.dict(os.environ, env):
            body, _, listed = build(jobs, ["bern"], CONFIG)
        lines = [l for l in body.splitlines() if l.startswith("- ")]
        self.assertEqual(listed, 3)
        self.assertTrue(lines[0].startswith("- ⭐ **Alpha**"))
        self.assertTrue(lines[-1].startswith("- **Zeta**"))
        self.assertIn("issues/new?template=stelle-vorbereiten.yml", lines[0])
        self.assertIn("link=https%3A%2F%2Fwww.jobs.ch", lines[0])
        self.assertIn("passt nicht", lines[-1])

    def test_no_link_without_github(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            body, _, _ = build([job("Pflegefachperson")], ["bern"], CONFIG)
        self.assertNotIn("Bewerbung vorbereiten →]", body)


if __name__ == "__main__":
    unittest.main()
