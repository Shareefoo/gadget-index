#!/usr/bin/env python3
"""Checks that every source in source_catalog.json still works.

    python tools/check_sources.py                      # check all sources, print a table
    python tools/check_sources.py --report report.md   # also write the table to a file
    python tools/check_sources.py --strict             # warnings fail too
    python tools/check_sources.py --only samsung-mobile-news garmin-blog

For each source it downloads the url the way the app does and reads the newest entry:
- RSS 2.0 / Atom feeds: newest pubDate / updated / published
- Android and Pixel security bulletin pages: newest monthly bulletin linked from the page
- Samsung security update page: newest SMR month

FAIL  HTTP error, timeout, not a feed or a known page, or nothing found in it (layout changed).
WARN  newest entry is old (news: 180 days, updates: 75 days), the url redirects to another host,
      or the answer was slow.
OK    everything else.

Exit code 1 when anything FAILs (or WARNs with --strict). Standard library only.
Run by .github/workflows/health.yml once a week, which opens an issue when a source breaks.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "gadget-index-healthcheck/1.0 (+https://github.com/Shareefoo/gadget-index)"
MAX_BYTES = 3 * 1024 * 1024
STALE_DAYS = {"news": 180, "updates": 75}
SLOW_SECONDS = 12.0

MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
# The same layouts the app reads (BulletinIndexParser, SamsungBulletinParser).
ANDROID_BULLETIN = re.compile(r'href="/docs/security/bulletin/(?:pixel/)?(?:\d{4}/)?(\d{4})-(\d{2})-01"')
SAMSUNG_SMR = re.compile(r"SMR-([A-Z]{3})-(\d{4})")


def month_start(year, month):
    return datetime(year, month, 1, tzinfo=timezone.utc)


def bulletin_dates(body):
    """Months listed by a bulletin page, or [] when the page is not a known bulletin page."""
    dates = [month_start(int(y), int(m)) for y, m in ANDROID_BULLETIN.findall(body) if 1 <= int(m) <= 12]
    dates += [month_start(int(y), MONTHS[m]) for m, y in SAMSUNG_SMR.findall(body) if m in MONTHS]
    return dates


def parse_date(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def local(tag):
    return tag.rsplit("}", 1)[-1]


def feed_dates(body):
    """Entry dates of an RSS 2.0 or Atom document; [] when it is not one. Raises ET.ParseError for bad XML."""
    root = ET.fromstring(body.lstrip("﻿").strip().encode("utf-8"))
    if local(root.tag) not in ("rss", "feed", "RDF"):
        return []
    dates = []
    for element in root.iter():
        if local(element.tag) in ("item", "entry"):
            for child in element:
                if local(child.tag) in ("pubDate", "date", "updated", "published"):
                    parsed = parse_date(child.text)
                    if parsed:
                        dates.append(parsed)
                        break
    return dates


def newest_entry(body):
    """(newest date or None, what the document is). Raises ValueError for something unreadable."""
    dates = bulletin_dates(body)
    if dates:
        return max(dates), "bulletin page"
    stripped = body.lstrip("﻿").lstrip()
    if stripped.startswith("<?xml") or stripped.startswith("<rss") or stripped.startswith("<feed"):
        try:
            return (max(feed_dates(body)) if feed_dates(body) else None), "feed"
        except ET.ParseError as e:
            raise ValueError(f"bad XML ({e})") from e
    raise ValueError("neither a feed nor a known bulletin page")


def evaluate(source, status, final_url, body, seconds, now):
    """Pure judgement of one download: returns (result, notes, newest). No network."""
    notes = []
    if status >= 400:
        return "FAIL", [f"HTTP {status}"], None
    try:
        newest, what = newest_entry(body)
    except ValueError as e:
        return "FAIL", [str(e)], None
    if newest is None:
        return "FAIL", [f"{what} has no entries (layout changed?)"], None
    result = "OK"
    age = (now - newest).days
    limit = STALE_DAYS.get(source["kind"], 120)
    if age > limit:
        result = "WARN"
        notes.append(f"newest entry is {age} days old (limit {limit})")
    old_host, new_host = urlparse(source["url"]).hostname, urlparse(final_url).hostname
    if old_host and new_host and old_host.removeprefix("www.") != new_host.removeprefix("www."):
        result = "WARN"
        notes.append(f"redirects to {new_host}")
    if seconds > SLOW_SECONDS:
        result = "WARN"
        notes.append(f"slow ({seconds:.0f} s)")
    return result, notes, newest


def download(url, timeout=25):
    """(status, final url, body text, seconds). Network errors raise OSError."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BYTES + 1)
            status, final = response.status, response.geturl()
    except urllib.error.HTTPError as e:
        return e.code, url, "", time.monotonic() - started
    if len(raw) > MAX_BYTES:
        raise OSError("larger than 3 MB")
    return status, final, raw.decode("utf-8", errors="replace"), time.monotonic() - started


def check(source, now):
    try:
        status, final_url, body, seconds = download(source["url"])
    except OSError as e:
        return {"id": source["id"], "url": source["url"], "result": "FAIL", "notes": [str(e) or type(e).__name__], "newest": None}
    result, notes, newest = evaluate(source, status, final_url, body, seconds, now)
    return {"id": source["id"], "url": source["url"], "result": result, "notes": notes, "newest": newest}


def report(rows, now):
    counts = {k: sum(r["result"] == k for r in rows) for k in ("OK", "WARN", "FAIL")}
    lines = [
        f"Source health, {now:%Y-%m-%d}: {counts['OK']} OK, {counts['WARN']} warnings, {counts['FAIL']} failed.",
        "",
        "| Result | Source | Newest entry | Notes |",
        "|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda r: ("FAIL", "WARN", "OK").index(r["result"])):
        newest = f"{r['newest']:%Y-%m-%d}" if r["newest"] else "-"
        lines.append(f"| {r['result']} | [{r['id']}]({r['url']}) | {newest} | {'; '.join(r['notes'])} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", help="also write the table (markdown) to this file")
    parser.add_argument("--strict", action="store_true", help="warnings fail too")
    parser.add_argument("--only", nargs="+", metavar="ID", help="check only these source ids")
    args = parser.parse_args()

    sources = json.loads((ROOT / "source_catalog.json").read_text(encoding="utf-8"))["sources"]
    if args.only:
        unknown = set(args.only) - {s["id"] for s in sources}
        if unknown:
            parser.error(f"unknown source ids: {sorted(unknown)}")
        sources = [s for s in sources if s["id"] in args.only]

    now = datetime.now(timezone.utc)
    rows = [check(source, now) for source in sources]
    text = report(rows, now)
    print(text)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text)

    failed = any(r["result"] == "FAIL" for r in rows)
    warned = any(r["result"] == "WARN" for r in rows)
    return 1 if failed or (args.strict and warned) else 0


if __name__ == "__main__":
    sys.exit(main())
