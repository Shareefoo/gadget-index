"""Checks which sources devices get, so a rule edit cannot silently change what a model gets.

    python -m unittest discover -s tests -v        (from the repository root)

- tests/matching.json lists devices with the exact sources they must get.
- Its `brandRules` apply to every model of a brand in device_models.json: the picker names must
  keep matching the source rules (that is how a picked "Garmin Fenix 8" finds the Garmin feed).
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import matching  # noqa: E402

CATALOG = matching.load("source_catalog.json")
MODELS = matching.load("device_models.json")
EXPECTED = json.loads((ROOT / "tests" / "matching.json").read_text(encoding="utf-8"))


class MatchingCases(unittest.TestCase):
    def test_listed_devices_get_exactly_these_sources(self):
        for case in EXPECTED["cases"]:
            with self.subTest(f"{case['type']}: {case['model']}"):
                result = matching.sources_for(CATALOG, case["type"], case["model"])
                self.assertEqual(sorted(case["updates"]), sorted(result["updates"]), "updates")
                self.assertEqual(sorted(case["news"]), sorted(result["news"]), "news")

    def test_every_expected_source_exists(self):
        ids = {s["id"] for s in CATALOG["sources"]}
        for case in EXPECTED["cases"]:
            for source_id in case["updates"] + case["news"]:
                self.assertIn(source_id, ids, f"{case['model']} expects unknown source {source_id}")


class BrandRules(unittest.TestCase):
    def test_every_model_of_a_brand_gets_its_brand_sources(self):
        checked = 0
        for rule in EXPECTED["brandRules"]:
            models = [
                shown for device_type, brand, shown in matching.all_models(MODELS)
                if device_type == rule["type"] and brand == rule["brand"]
            ]
            self.assertTrue(models, f"no {rule['type']} models for brand {rule['brand']}")
            for shown in models:
                got = matching.sources_for(CATALOG, rule["type"], shown)["news"]
                for source_id in rule["news"]:
                    checked += 1
                    self.assertIn(source_id, got, f"{rule['type']} '{shown}' should get {source_id}, gets {got}")
        self.assertGreater(checked, 0)


class Rules(unittest.TestCase):
    """Small cases for the matching rules themselves."""

    def source(self, **fields):
        base = {"id": "x", "name": "X", "kind": "news", "url": "https://x.example/rss"}
        base.update(fields)
        return base

    def test_empty_lists_mean_any(self):
        self.assertTrue(matching.matches(self.source(), "Laptop", "anything"))

    def test_lists_are_anded_entries_are_ored(self):
        s = self.source(types=["Watch"], modelStartsWith=["Galaxy", "Samsung"], modelContains=["Watch"])
        self.assertTrue(matching.matches(s, "Watch", "Samsung Galaxy Watch7"))
        self.assertTrue(matching.matches(s, "Watch", "galaxy watch ultra"))
        self.assertFalse(matching.matches(s, "Phone", "Samsung Galaxy Watch7"))
        self.assertFalse(matching.matches(s, "Watch", "Samsung Galaxy Buds"))
        self.assertFalse(matching.matches(s, "Watch", "Apple Watch"))

    def test_superseded_source_is_dropped_only_when_the_other_matches(self):
        a = self.source(id="a", url="https://a.example", supersededBy=["b"])
        b = self.source(id="b", url="https://b.example", types=["Phone"])
        self.assertEqual(["a"], [s["id"] for s in matching.select([a, b], "news", "Watch")])
        self.assertEqual(["b"], [s["id"] for s in matching.select([a, b], "news", "Phone")])

    def test_same_url_is_listed_once(self):
        a = self.source(id="a")
        b = self.source(id="b")
        self.assertEqual(["a"], [s["id"] for s in matching.select([a, b], "news", "Phone")])

    def test_display_does_not_repeat_the_brand(self):
        self.assertEqual("Garmin Fenix 8", matching.display("Garmin", "Fenix 8"))
        self.assertEqual("Garmin Fenix 8", matching.display("Garmin", "Garmin Fenix 8"))
        self.assertEqual("Nothing Ear", matching.display("", "Nothing Ear"))


if __name__ == "__main__":
    unittest.main()
