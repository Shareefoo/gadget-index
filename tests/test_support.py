"""Offline tests for the support list builder (tools/build_support.py), on small copies of the pages' HTML.

    python -m unittest discover -s tests -v        (from the repository root)
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import build_support as bs  # noqa: E402
import validate_catalog as vc  # noqa: E402

POLICY = """<meta content="Pixel phones get updates for 7 years">
<h2>How long you&#39;ll get Pixel updates</h2>
<p>Pixel 8 and later phones will get updates for 7 years starting from when ...</p>
<ul><li>Pixel 9</li><li>Pixel 8</li></ul>
<a class="zippy">Pixel 7 &amp; earlier</a>
<div><p>These phones will get updates for 5 years starting from ...</p>
<ul><li>Pixel 7</li><li>Pixel 6 Pro</li></ul></div>
<div><p>The following Pixel phones no longer receive Android version updates and security updates:</p>
<ul><li>Pixel 5</li><li>Pixel 4 &amp; Pixel 4 XL</li></ul></div>
This page is about Pixel software updates.
<ul><li>Not a phone</li></ul>
"""

DATES = """<table>
<tr><td><p>Version</p></td><td><p>Date</p></td></tr>
<tr><td><p>Pixel 9</p></td><td><p>August 2024</p></td></tr>
<tr><td><p>Pixel 8</p></td><td><p>October 2023</p></td></tr>
<tr><td><p>Pixel 7</p></td><td><p>October 2022</p></td></tr>
<tr><td><p>Pixel 6 Pro</p></td><td><p>October 2021</p></td></tr>
<tr><td><p>Pixel 4 | 4 XL</p></td><td><p>October 2019</p></td></tr>
</table>"""

SAMSUNG = """<div class="txt_section txt_section_workscope">
<strong>Current Models for Monthly Security Updates<sup>2</sup></strong>
<ul class="list_circle"><li><b>Galaxy S Series</b><ul class="list_circle_s">
<li>Galaxy S24, Galaxy S24+</li><li>Galaxy S23</li></ul></li>
<!-- <li><b>Galaxy A Series</b><ul class="list_circle_s"><li>Galaxy A99</li></ul></li> -->
</ul></div>
<div class="txt_section txt_section_workscope">
<strong>Current Wearable Models for Quarterly Security Updates<sup>4</sup></strong>
<ul class="list_circle"><li><b>Galaxy Watch Series</b><ul class="list_circle_s">
<li>Galaxy Watch7 40mm, Galaxy Watch7 44mm</li></ul></li></ul></div>
"""


class Pixel(unittest.TestCase):
    def test_until_is_the_availability_month_plus_the_update_years(self):
        models = bs.parse_pixel_policy(POLICY, bs.parse_pixel_dates(DATES))
        until = {m["name"]: m.get("until") for m in models}
        self.assertEqual("2031-08", until["Pixel 9"])
        self.assertEqual("2027-10", until["Pixel 7"])
        self.assertEqual("2026-10", until["Pixel 6 Pro"])
        self.assertNotIn("Not a phone", until)

    def test_ended_phones_and_pairs_are_split(self):
        models = bs.parse_pixel_policy(POLICY, bs.parse_pixel_dates(DATES))
        ended = [m["name"] for m in models if m.get("ended")]
        self.assertEqual(["Pixel 5", "Pixel 4", "Pixel 4 XL"], ended)
        self.assertEqual((2019, 10), bs.parse_pixel_dates(DATES)["Pixel 4 XL"])

    def test_a_phone_without_an_availability_date_is_an_error(self):
        with self.assertRaises(bs.PageError):
            bs.parse_pixel_policy(POLICY, {})


class Samsung(unittest.TestCase):
    def test_models_get_their_sections_cadence_and_comments_are_skipped(self):
        models = {m["name"]: m["cadence"] for m in bs.parse_samsung(SAMSUNG)}
        self.assertEqual("monthly", models["Galaxy S24+"])
        self.assertEqual("quarterly", models["Galaxy Watch7 44mm"])
        self.assertNotIn("Galaxy A99", models)


class Running(unittest.TestCase):
    def run_main(self, folder, out, *extra):
        with mock.patch.object(bs, "OUTPUT", out), mock.patch.object(bs, "MIN_PIXELS", 3), \
                mock.patch.object(bs, "MIN_SAMSUNG", 3), \
                mock.patch.object(sys, "argv", ["build_support", "--pages", str(folder), *extra]):
            return bs.main()

    def write_pages(self, folder, samsung=SAMSUNG):
        (folder / "pixel_policy.html").write_text(POLICY, encoding="utf-8")
        (folder / "pixel_dates.html").write_text(DATES, encoding="utf-8")
        (folder / "samsung_scope.html").write_text(samsung, encoding="utf-8")

    def test_writes_a_valid_file_and_only_bumps_the_revision_on_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, out = Path(tmp), Path(tmp) / "support.json"
            self.write_pages(folder)
            self.assertEqual(0, self.run_main(folder, out))
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(1, data["revision"])
            problems = vc.Problems("support.json")
            vc.check_support(data, problems)
            self.assertEqual([], problems.items)
            self.assertEqual(0, self.run_main(folder, out))
            self.assertEqual(1, json.loads(out.read_text(encoding="utf-8"))["revision"])

    def test_an_unreadable_page_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, out = Path(tmp), Path(tmp) / "support.json"
            self.write_pages(folder, samsung="<html>Access denied</html>")
            self.assertEqual(1, self.run_main(folder, out))
            self.assertFalse(out.exists())


class Validation(unittest.TestCase):
    def test_bad_entries_are_reported(self):
        data = {
            "schemaVersion": 1, "revision": 1,
            "sources": [{"brand": "Google", "url": "https://x.example", "modelStartsWith": ["Google"], "types": ["Phone"], "complete": False}],
            "models": [
                {"brand": "Google", "name": "Pixel 9", "until": "2031-13"},
                {"brand": "Google", "name": "Pixel 8", "until": "2030-10", "ended": True},
                {"brand": "Other", "name": "Phone", "cadence": "weekly"},
            ],
        }
        problems = vc.Problems("support.json")
        vc.check_support(data, problems)
        text = "\n".join(problems.items)
        self.assertIn('"until" must be "YYYY-MM"', text)
        self.assertIn("exactly one", text)
        self.assertIn('"cadence" must be one of', text)
        self.assertIn('"brand" must be one of', text)


if __name__ == "__main__":
    unittest.main()
