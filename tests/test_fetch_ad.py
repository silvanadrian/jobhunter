"""Inserat-Extraktion mit handgeschriebenen HTML-Beispielen (offline)."""

import os
import unittest

from jobwatch import fetch_ad

HERE = os.path.join(os.path.dirname(__file__), "fixtures")


def page(name):
    return open(os.path.join(HERE, name), encoding="utf-8").read()


class Extraction(unittest.TestCase):
    def setUp(self):
        # Keine ATS-Treffer und kein Netzwerk: die Seiten kommen aus den Fixtures.
        self._ats = fetch_ad.ATS
        fetch_ad.ATS = []

    def tearDown(self):
        fetch_ad.ATS = self._ats

    def test_json_ld(self):
        ad, method = fetch_ad.extract("https://example.com/a", lambda url, timeout: page("jsonld.html"))
        self.assertEqual(method, "json-ld")
        self.assertEqual(ad["company"], "Beispiel Werke AG")
        self.assertEqual(ad["title"], "Senior Entwickler (m/w/d)")
        self.assertIn("Winterthur", ad["location"])
        self.assertTrue(ad["valid_through"].startswith("2026-12-15"))
        self.assertIn("100000-120000", ad["salary"])
        self.assertIn("- Weiterentwicklung unserer Webplattform", ad["body"])
        self.assertIn("**deine**", ad["body"])

    def test_meta_and_main_text(self):
        ad, method = fetch_ad.extract("https://example.com/b", lambda url, timeout: page("meta.html"))
        self.assertEqual(method, "meta")
        self.assertEqual(ad["title"], "Teamleiter Software (80–100%)")
        self.assertIn("Erste Führungserfahrung", ad["body"])
        self.assertNotIn("tracking", ad["body"])
        self.assertNotIn("Fusszeile", ad["body"])

    def test_nothing_usable_asks_for_paste(self):
        ad, reason = fetch_ad.extract("https://example.com/c", lambda url, timeout: page("empty.html"))
        self.assertIsNone(ad)
        self.assertIn("keine Stellenbeschreibung", reason)

    def test_linkedin_is_not_fetched(self):
        ad, reason = fetch_ad.extract("https://www.linkedin.com/jobs/view/1",
                                      lambda url, timeout: self.fail("darf nicht laden"))
        self.assertIsNone(ad)

    def test_render_front_matter(self):
        ad, method = fetch_ad.extract("https://example.com/a", lambda url, timeout: page("jsonld.html"))
        text = fetch_ad.render(ad, "https://example.com/a", "example.com", method)
        self.assertIn('extraction: "json-ld"', text)
        self.assertIn('company: "Beispiel Werke AG"', text)
        self.assertIn("fetched_at:", text)
        self.assertEqual(fetch_ad.slugify("Beispiel Werke AG"), "beispiel-werke-ag")


if __name__ == "__main__":
    unittest.main()
