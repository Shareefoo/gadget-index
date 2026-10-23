"""Offline tests for the source health check (tools/check_sources.py): no network is used.

    python -m unittest discover -s tests -v        (from the repository root)
"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import check_sources as hc  # noqa: E402

NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)
NEWS = {"id": "n", "kind": "news", "url": "https://news.example/feed"}
UPDATES = {"id": "u", "kind": "updates", "url": "https://source.android.com/docs/security/bulletin/asb-overview"}

RSS = """<?xml version="1.0"?><?xml-stylesheet href="x.xsl"?>
<rss version="2.0"><channel><title>T</title>
<item><title>New</title><pubDate>Wed, 21 Oct 2026 10:00:00 +0000</pubDate></item>
<item><title>Old</title><pubDate>Mon, 01 Jan 2024 10:00:00 +0000</pubDate></item></channel></rss>"""

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>T</title>
<entry><title>A</title><updated>2026-10-20T08:00:00Z</updated></entry></feed>"""

ANDROID_PAGE = """<nav><a href="/docs/security/bulletin/2026/2026-10-01">Oct</a>
<a href="/docs/security/bulletin/pixel/2026/2026-09-01">Sep</a></nav>"""

SAMSUNG_PAGE = """<div class="acc_title"><a>SMR-OCT-2026</a></div><div class="acc_title"><a>SMR-SEP-2026</a></div>"""


class Parsing(unittest.TestCase):
    def test_rss_with_a_stylesheet_line_gives_the_newest_date(self):
        self.assertEqual(datetime(2026, 10, 21, 10, tzinfo=timezone.utc), max(hc.feed_dates(RSS)))

    def test_atom(self):
        self.assertEqual([datetime(2026, 10, 20, 8, tzinfo=timezone.utc)], hc.feed_dates(ATOM))

    def test_bulletin_pages(self):
        self.assertEqual(datetime(2026, 10, 1, tzinfo=timezone.utc), max(hc.bulletin_dates(ANDROID_PAGE)))
        self.assertEqual(datetime(2026, 10, 1, tzinfo=timezone.utc), max(hc.bulletin_dates(SAMSUNG_PAGE)))
        self.assertEqual([], hc.bulletin_dates("<html>nothing</html>"))

    def test_dates_without_a_zone_are_taken_as_utc(self):
        self.assertEqual(timezone.utc, hc.parse_date("2026-10-20T08:00:00").tzinfo)
        self.assertIsNone(hc.parse_date("not a date"))


class Judging(unittest.TestCase):
    def judge(self, source, body, status=200, final=None, seconds=1.0):
        return hc.evaluate(source, status, final or source["url"], body, seconds, NOW)

    def test_a_fresh_feed_is_ok(self):
        self.assertEqual("OK", self.judge(NEWS, RSS)[0])
        self.assertEqual("OK", self.judge(NEWS, ATOM)[0])

    def test_bulletin_pages_are_ok(self):
        self.assertEqual("OK", self.judge(UPDATES, ANDROID_PAGE)[0])

    def test_http_errors_fail(self):
        result, notes, _ = self.judge(NEWS, "", status=403)
        self.assertEqual("FAIL", result)
        self.assertIn("403", notes[0])

    def test_html_that_is_not_a_known_page_fails(self):
        self.assertEqual("FAIL", self.judge(NEWS, "<html><body>Please enable JavaScript</body></html>")[0])

    def test_broken_xml_and_empty_feeds_fail(self):
        self.assertEqual("FAIL", self.judge(NEWS, "<?xml version='1.0'?><rss><channel>")[0])
        self.assertEqual("FAIL", self.judge(NEWS, '<?xml version="1.0"?><rss version="2.0"><channel/></rss>')[0])

    def test_stale_sources_warn_with_their_own_limit(self):
        old_feed = RSS.replace("Wed, 21 Oct 2026", "Wed, 01 Jan 2025").replace("Mon, 01 Jan 2024", "Mon, 01 Jan 2023")
        result, notes, _ = self.judge(NEWS, old_feed)
        self.assertEqual("WARN", result)
        self.assertIn("days old", notes[0])
        # A bulletin page 100 days behind is stale for updates (75 days) but would not be for news.
        old_bulletin = '<a href="/docs/security/bulletin/2026/2026-07-01">Jul</a>'
        self.assertEqual("WARN", self.judge(UPDATES, old_bulletin)[0])

    def test_redirect_to_another_host_and_slow_answers_warn(self):
        self.assertEqual("OK", self.judge(NEWS, RSS, final="https://www.news.example/feed")[0])
        self.assertEqual("WARN", self.judge(NEWS, RSS, final="https://other.example/feed")[0])
        self.assertEqual("WARN", self.judge(NEWS, RSS, seconds=30)[0])


class Report(unittest.TestCase):
    def test_failures_are_listed_first(self):
        rows = [
            {"id": "a", "url": "https://a.example", "result": "OK", "notes": [], "newest": NOW},
            {"id": "b", "url": "https://b.example", "result": "FAIL", "notes": ["HTTP 403"], "newest": None},
        ]
        text = hc.report(rows, NOW)
        self.assertIn("1 OK, 0 warnings, 1 failed", text)
        self.assertLess(text.index("| FAIL |"), text.index("| OK |"))


if __name__ == "__main__":
    unittest.main()
