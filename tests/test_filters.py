"""Filter-, Dedup- und Zustandslogik von jobwatch (offline)."""

import unittest

from jobwatch.config import ConfigError, feed_from_url, normalise
from jobwatch.filters import (already_have, annotate, below_floor, dedupe_key, in_region,
                              name_lookup, seen_key, title_ok, yearly_top)
from jobwatch.state import seed_backlogs

RAW = {
    "search": {"keywords": ["engineer", "developer", "entwickler", "ai"],
               "seniority": ["senior", "lead", "leiter"], "avoid": ["praktikum"],
               "remote_ok": True},
    "locations": [{"name": "zuerich", "places": ["Zürich", "Winterthur"],
                   "country": ["Schweiz", "Switzerland"], "avoid_places": ["Genf", "Geneva"],
                   "salary_floor": 100000}],
    "companies": ["https://boards.greenhouse.io/acme", "lever:beispiel"],
    "ruled_out": {"Nope Corp": "kein Interesse"},
    "pending": {"wartet": "beworben"},
    "applied": {"https://example.com/jobs/1": "beworben"},
}


def cfg():
    return normalise(dict(RAW))


class TitleFilter(unittest.TestCase):
    def test_keeps_senior_engineering_titles(self):
        c = cfg()
        self.assertTrue(title_ok("Senior Software Engineer", c))
        self.assertTrue(title_ok("Lead Entwickler Java", c))

    def test_drops_noise_and_wrong_level(self):
        c = cfg()
        self.assertFalse(title_ok("Senior Sales Engineer", c))          # eingebaute Liste
        self.assertFalse(title_ok("Praktikum Senior Developer", c))     # eigene avoid-Liste
        self.assertFalse(title_ok("Software Engineer", c))              # keine Stufe
        self.assertTrue(title_ok("Software Engineer", c, wide_seniority=True))

    def test_short_words_match_whole_words_only(self):
        c = cfg()
        self.assertTrue(title_ok("Senior AI Engineer", c))
        self.assertFalse(title_ok("Senior Maintainer", c))

    def test_contract_roles_dropped(self):
        c = cfg()
        self.assertFalse(title_ok("Senior Engineer (12 months contract)", c))


class Region(unittest.TestCase):
    def test_places_country_and_exclusions(self):
        r = cfg()["regions"]["zuerich"]
        self.assertTrue(in_region("Zurich, Switzerland", r))       # Umlaut-tolerant
        self.assertTrue(in_region("Zuerich", r))
        self.assertTrue(in_region("Switzerland", r))
        self.assertFalse(in_region("Geneva, Switzerland", r))
        self.assertFalse(in_region("Berlin, Germany", r))
        self.assertTrue(in_region("Remote", r))
        self.assertFalse(in_region("Remote - Brazil", r))

    def test_listed_as_suffix_is_ignored(self):
        r = cfg()["regions"]["zuerich"]
        self.assertFalse(in_region("London, United Kingdom (listed as Zurich)", r))


class Dedup(unittest.TestCase):
    def test_company_variants_and_titles(self):
        feed = {"company": "acme", "title": "Senior Engineer – Platform"}
        board = {"company": "Acme AG", "title": "Senior Engineer - Platform"}
        self.assertTrue(already_have(dedupe_key(board), {dedupe_key(feed)}))
        other = {"company": "Acme AG", "title": "Lead Engineer"}
        self.assertFalse(already_have(dedupe_key(other), {dedupe_key(feed)}))
        self.assertEqual(seen_key(feed), seen_key({"company": "ACME", "title": "senior engineer platform"}))


class Lists(unittest.TestCase):
    def test_ruled_out_pending_applied(self):
        c = cfg()
        self.assertEqual(annotate({"company": "Nope Corp AG", "url": ""}, c)[0], True)
        hide, note = annotate({"company": "Wartet GmbH", "url": ""}, c)
        self.assertFalse(hide)
        self.assertIn("läuft", note)
        self.assertTrue(annotate({"company": "x", "url": "https://example.com/jobs/1"}, c)[0])
        self.assertEqual(annotate({"company": "Anders AG", "url": "u"}, c), (False, ""))

    def test_name_lookup_folds_accents(self):
        self.assertTrue(name_lookup("Genève Beispielbank", {"geneve": "x"}))
        self.assertIsNone(name_lookup("Nopel AG", {"nope": "x"}))


class Salary(unittest.TestCase):
    def test_parsing(self):
        self.assertEqual(yearly_top("CHF 100'000 - 120'000"), 120000)
        self.assertEqual(yearly_top("$160-220k"), 220000)
        self.assertEqual(yearly_top("$85/hr"), 85 * 2080)
        self.assertEqual(yearly_top("CHF 9'000 per month"), 108000)
        self.assertIsNone(yearly_top(""))

    def test_floor_only_when_stated(self):
        r = cfg()["regions"]["zuerich"]
        self.assertTrue(below_floor({"salary": "CHF 80'000", "location": "Zürich"}, r))
        self.assertIsNone(below_floor({"salary": "", "location": "Zürich"}, r))
        self.assertIsNone(below_floor({"salary": "CHF 130'000", "location": "Zürich"}, r))


class Seeding(unittest.TestCase):
    def test_first_region_run_is_reported_by_default(self):
        # Neue Nutzer sollen am ersten Tag die aktuell passenden Stellen sehen.
        c = cfg()
        matches = [{"region": "zuerich", "source": "feed", "new": True} for _ in range(3)]
        markers = seed_backlogs(matches, set(), list(c["regions"].values()), 40, quiet=True)
        self.assertIn("seeded:zuerich", markers)
        self.assertTrue(all(m["new"] for m in matches))

    def test_first_region_run_is_recorded_when_seeding_enabled(self):
        c = cfg()
        regions = [dict(r, seed_on_first_run=True) for r in c["regions"].values()]
        matches = [{"region": "zuerich", "source": "feed", "new": True} for _ in range(3)]
        markers = seed_backlogs(matches, set(), regions, 40, quiet=True)
        self.assertIn("seeded:zuerich", markers)
        self.assertFalse(any(m["new"] for m in matches))

    def test_new_small_source_reports_normally(self):
        c = cfg()
        matches = [{"region": "zuerich", "source": "jobs.ch", "new": True}]
        seed_backlogs(matches, {"seeded:zuerich"}, list(c["regions"].values()), 40, quiet=True)
        self.assertTrue(matches[0]["new"])


class Config(unittest.TestCase):
    def test_unknown_key_suggests_fix(self):
        with self.assertRaises(ConfigError) as ctx:
            normalise({**RAW, "serach": {}})
        self.assertIn("search", str(ctx.exception))

    def test_feed_detection_from_urls(self):
        self.assertEqual(feed_from_url("https://boards.greenhouse.io/acme/jobs/123")["slug"], "acme")
        self.assertEqual(feed_from_url("https://jobs.lever.co/beispiel/abc")["ats"], "lever")
        self.assertEqual(feed_from_url("https://acme.jobs.personio.com/job/1")["ats"], "personio")
        self.assertEqual(feed_from_url("https://acme.wd3.myworkdayjobs.com/en-US/External")["slug"],
                         "acme/wd3/External")
        self.assertIsNone(feed_from_url("https://example.com/karriere"))


if __name__ == "__main__":
    unittest.main()


class BoardQueries(unittest.TestCase):
    def test_board_queries_follow_own_keywords(self):
        import tempfile, os, textwrap
        from jobwatch.config import load
        d = tempfile.mkdtemp()
        path = os.path.join(d, "jobhunter.yml")
        open(path, "w", encoding="utf-8").write(textwrap.dedent("""
            search:
              keywords: [Pflegefachperson, Pflege HF]
              seniority: []
            locations:
            - name: bern
              places: [Bern]
            companies: []
        """))
        cfg = load(path)
        self.assertEqual(cfg["queries"]["lead"], ["Pflegefachperson", "Pflege HF"])
        self.assertEqual(cfg["queries"]["broad"], [])
