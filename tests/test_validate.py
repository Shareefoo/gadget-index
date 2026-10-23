"""Tests for the catalogue validator (tools/validate_catalog.py) on small made-up catalogues.

    python -m unittest discover -s tests -v        (from the repository root)
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import validate_catalog as vc  # noqa: E402


def problems_for(*sources):
    problems = vc.Problems("source_catalog.json")
    vc.check_sources({"schemaVersion": 1, "revision": 1, "sources": list(sources)}, problems)
    return problems.items


def news(**fields):
    base = {"id": "n", "name": "N", "kind": "news", "url": "https://n.example/rss"}
    base.update(fields)
    return base


class FilterByModel(unittest.TestCase):
    def test_true_and_false_are_fine_on_news_sources(self):
        self.assertEqual([], problems_for(news(filterByModel=True)))
        self.assertEqual([], problems_for(news(filterByModel=False)))

    def test_only_booleans_are_accepted(self):
        self.assertTrue(problems_for(news(filterByModel="true")))
        self.assertTrue(problems_for(news(filterByModel=1)))

    def test_update_sources_cannot_be_filtered(self):
        found = problems_for(news(kind="updates", filterByModel=True))
        self.assertTrue(any("only applies to news" in p for p in found), found)
        self.assertEqual([], problems_for(news(kind="updates", filterByModel=False)))


class BasicRules(unittest.TestCase):
    def test_a_good_source_has_no_problems(self):
        self.assertEqual([], problems_for(news(types=["Watch"], modelStartsWith=["Garmin"])))

    def test_common_mistakes_are_reported(self):
        self.assertTrue(problems_for(news(url="http://n.example/rss")))
        self.assertTrue(problems_for(news(kind="podcast")))
        self.assertTrue(problems_for(news(types=["Ring"])))
        self.assertTrue(problems_for(news(supersededBy=["missing"])))
        self.assertTrue(problems_for(news(), news()))  # duplicate id
        self.assertTrue(problems_for(news(surprise=1)))


if __name__ == "__main__":
    unittest.main()
