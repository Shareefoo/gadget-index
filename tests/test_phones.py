"""Offline tests for the phone list builder (tools/build_phones.py): no network is used.

    python -m unittest discover -s tests -v        (from the repository root)
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import build_phones as bp  # noqa: E402

CSV = """Retail Branding,Marketing Name,Device,Model
"","","AD681H","Smartfren Andromax AD681H"
"Google","Pixel 8","shiba","Pixel 8"
"Google","Pixel 8","shiba2","Pixel 8"
"Google","Google Pixel 8 Pro","husky","Pixel 8 Pro"
"Samsung","Galaxy S25","s25","SM-S931B"
"samsung","Galaxy S24","s24","SM-S921B"
"samsung","Galaxy S24","s24x","SM-S921U"
"Acme","build_code_name","x","y"
"Acme","X","x","y"
"Acme","Quoted, with comma","q","q"
"""


class Parsing(unittest.TestCase):
    def test_rows_without_a_useful_name_are_dropped(self):
        groups = bp.parse(CSV)
        names = [n for g in groups.values() for n in g]
        self.assertNotIn("build_code_name", names)
        self.assertNotIn("X", names)
        self.assertEqual(["Quoted, with comma"], groups["Acme"])

    def test_models_are_listed_once_and_the_brand_is_not_repeated(self):
        groups = bp.parse(CSV)
        self.assertEqual(["Google Pixel 8 Pro", "Pixel 8"], groups["Google"])

    def test_brand_spellings_are_merged(self):
        groups = bp.parse(CSV)
        self.assertEqual(["Galaxy S24", "Galaxy S25"], groups["Samsung"])
        self.assertNotIn("samsung", groups)

    def test_utf16_with_a_byte_order_mark_is_read(self):
        raw = CSV.encode("utf-16")
        self.assertEqual(CSV, bp.decode(raw))
        self.assertEqual(CSV, bp.decode(CSV.encode("utf-8-sig")))


class Output(unittest.TestCase):
    def test_the_file_is_valid_json_with_the_model_list_layout(self):
        doc = bp.document(bp.parse(CSV), 7)
        data = json.loads(bp.render(doc))
        self.assertEqual({"schemaVersion": 1, "revision": 7}, {k: data[k] for k in ("schemaVersion", "revision")})
        self.assertTrue(all(set(g) == {"type", "brand", "names"} and g["type"] == "Phone" for g in data["groups"]))


class Running(unittest.TestCase):
    """main() against a temporary output file, with the thresholds lowered for the small sample."""

    def run_main(self, out, csv_text, *extra):
        source = out.parent / "list.csv"
        source.write_bytes(csv_text.encode("utf-16"))
        with mock.patch.object(bp, "OUTPUT", out), mock.patch.object(bp, "MIN_MODELS", 3), \
                mock.patch.object(sys, "argv", ["build_phones", "--input", str(source), *extra]):
            return bp.main()

    def test_revision_only_goes_up_when_the_content_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "phone_models.json"
            self.assertEqual(0, self.run_main(out, CSV))
            self.assertEqual(1, json.loads(out.read_text(encoding="utf-8"))["revision"])
            first = out.read_text(encoding="utf-8")
            self.assertEqual(0, self.run_main(out, CSV))
            self.assertEqual(first, out.read_text(encoding="utf-8"))
            self.assertEqual(0, self.run_main(out, CSV + '"Acme","Phone Two","p","p"\n'))
            self.assertEqual(2, json.loads(out.read_text(encoding="utf-8"))["revision"])

    def test_check_reports_a_change_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "phone_models.json"
            self.assertEqual(1, self.run_main(out, CSV, "--check"))
            self.assertFalse(out.exists())

    def test_a_much_smaller_list_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "phone_models.json"
            self.assertEqual(0, self.run_main(out, CSV))
            before = out.read_text(encoding="utf-8")
            shrunk = "Retail Branding,Marketing Name,Device,Model\n" + '"Google","Pixel 8","a","a"\n"Google","Pixel 9","b","b"\n"Google","Pixel 7","c","c"\n'
            self.assertEqual(1, self.run_main(out, shrunk))
            self.assertEqual(before, out.read_text(encoding="utf-8"))

    def test_an_unreadable_list_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "phone_models.json"
            self.assertEqual(1, self.run_main(out, "<html>Access denied</html>"))
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
