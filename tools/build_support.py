#!/usr/bin/env python3
"""Builds support.json: how long each phone gets security updates, from the makers' own pages.

    python tools/build_support.py                    # download the pages, rewrite support.json if it changed
    python tools/build_support.py --pages DIR        # use saved copies (pixel_policy.html, pixel_dates.html,
                                                     # samsung_scope.html, huawei_bulletin.html,
                                                     # honor_bulletin.html) instead of downloading
    python tools/build_support.py --check            # exit 1 when the file would change; writes nothing

Sources (nothing is guessed; every entry comes from one of these pages):
- Google, "Learn when you'll get software updates on Google Pixel phones"
  (support.google.com/pixelphone/answer/4457705): Pixel phones get updates for N years from the month
  they became available on the Google Store in the US, or "no longer receive" them.
- Google, "Find when your Pixel device became available" (support.google.com/pixelphone/answer/15738422):
  that month for each phone. `until` = that month plus N years.
- Samsung, "Security Updates Scope" (security.samsungmobile.com/workScope.smsb): the models that get
  monthly, quarterly or biannual security updates now. It has no end dates; a Galaxy phone, tablet or
  watch that is not on it is "not on Samsung's list" (the source is marked "complete" for those types).
- Huawei, "Security Bulletins for HUAWEI Phones/Tablets" (consumer.huawei.com/en/support/bulletin/) and
  Honor, "MagicOS/Magic UI Security Updates" (honor.com/global/support/bulletin/): the same kind of list
  (monthly, bi-monthly, quarterly) for their phones and tablets, also "complete".

Layout (schema 1):
    { "schemaVersion": 1, "revision": 1,
      "sources": [ { "brand", "url", "modelStartsWith": [..], "types": [..], "complete": bool } ],
      "models": [ { "brand", "name", "until": "YYYY-MM" | "ended": true | "cadence": "monthly" | ... } ] }

The pages are HTML, so this depends on their layout: when a page cannot be read, or gives far fewer
models than before, nothing is written and the exit code is 1. `revision` goes up only when the
content changes. Standard library only. Run weekly by .github/workflows/support.yml.
"""

import argparse
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "support.json"

PIXEL_POLICY = "https://support.google.com/pixelphone/answer/4457705?hl=en"
PIXEL_DATES = "https://support.google.com/pixelphone/answer/15738422?hl=en"
SAMSUNG_SCOPE = "https://security.samsungmobile.com/workScope.smsb"
HUAWEI_BULLETIN = "https://consumer.huawei.com/en/support/bulletin/"
HONOR_BULLETIN = "https://www.honor.com/global/support/bulletin/"
PAGES = {
    "pixel_policy.html": PIXEL_POLICY,
    "pixel_dates.html": PIXEL_DATES,
    "samsung_scope.html": SAMSUNG_SCOPE,
    "huawei_bulletin.html": HUAWEI_BULLETIN,
    "honor_bulletin.html": HONOR_BULLETIN,
}

MIN_PIXELS = 10  # the policy page lists about 30
MIN_SAMSUNG = 50  # the scope page lists about 150
MIN_HUAWEI = 10  # the bulletin page lists about 25
MIN_HONOR = 20  # the bulletin page lists about 60
MIN_SHARE_OF_PREVIOUS = 0.7
MAX_DOWNLOAD = 8 * 1024 * 1024
MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]
CADENCES = (("monthly", "monthly"), ("quarterly", "quarterly"), ("biannual", "biannual"), ("personal computer", "regular"))


class PageError(Exception):
    pass


def text_of(fragment):
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment)).replace("\xa0", " ").strip()


def items(fragment):
    """Text of every <li> in an HTML fragment, whitespace collapsed."""
    return [re.sub(r"\s+", " ", text_of(li)) for li in re.findall(r"<li[^>]*>(.*?)</li>", fragment, re.S)]


def split_pair(name):
    """"Pixel 4 & Pixel 4 XL" / "Pixel 4 | 4 XL" / "Pixel | XL" -> separate model names."""
    parts = [p.strip() for p in re.split(r"\s*[&|]\s*", name) if p.strip()]
    if not parts:
        return []
    first = parts[0]
    return [first] + [p if p.lower().startswith("pixel") else f"Pixel {p}" for p in parts[1:]]


def parse_pixel_dates(page):
    """{model name: (year, month)} from the availability table."""
    dates = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cells = [re.sub(r"\s+", " ", text_of(c)) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) != 2:
            continue
        m = re.fullmatch(r"([A-Za-z]+) (\d{4})", cells[1])
        if not m or m.group(1).lower() not in MONTHS:
            continue
        for name in split_pair(cells[0]):
            dates[name] = (int(m.group(2)), MONTHS.index(m.group(1).lower()) + 1)
    return dates


def parse_pixel_policy(page, dates):
    """[{brand, name, until | ended}] from the policy page and the availability dates."""
    models = []
    # Only the article's "How long you'll get Pixel updates" part (the phrase also appears in page metadata).
    start = page.find("How long you&#39;ll get Pixel updates")
    if start < 0:
        start = page.find("How long you'll get Pixel updates")
    end = page.find("This page is about Pixel software updates", start)
    if start < 0 or end < 0:
        raise PageError("the Pixel policy page has no \"How long you'll get Pixel updates\" section")
    page = page[start:end]
    # Each "will get updates for N years" paragraph is followed by the list of its phones.
    for m in re.finditer(r"get updates for (\d+) years", page):
        years = int(m.group(1))
        ul = re.search(r"<ul[^>]*>(.*?)</ul>", page[m.end():], re.S)
        if not ul:
            raise PageError("a Pixel update period has no list of phones")
        for item in items(ul.group(1)):
            for name in split_pair(item):
                if name not in dates:
                    raise PageError(f'no availability date for "{name}"')
                year, month = dates[name]
                models.append({"brand": "Google", "name": name, "until": f"{year + years:04d}-{month:02d}"})
    ended = re.search(r"no longer receive[^<]*</p>\s*<ul[^>]*>(.*?)</ul>", page, re.S)
    if ended:
        for item in items(ended.group(1)):
            for name in split_pair(item):
                models.append({"brand": "Google", "name": name, "ended": True})
    return models


def parse_heading_lists(page, brand, cadences):
    """Huawei's and Honor's pages: a <p class="des-tit"> heading names the cadence ("Models with monthly
    security updates"), and each following <p class="des"> is "Series: Model, Model, ..." until the
    next heading. Footnotes ("¹The models ...") have no "Series:" part and are skipped. The brand word is
    taken out of the names ("HUAWEI Mate X6" -> "Mate X6"), as the app compares names without it."""
    page = re.sub(r"<!--.*?-->", "", page, flags=re.S)
    models = []
    cadence = None
    for kind, inner in re.findall(r'<p class="(des-tit|des)"[^>]*>(.*?)</p>', page, re.S):
        line = re.sub(r"\s+", " ", text_of(inner))
        if kind == "des-tit":
            title = line.lower()
            cadence = next((value for key, value in cadences if key in title), None)
            continue
        if cadence is None or ":" not in line or line[:1] in "¹²³":
            continue
        for name in line.split(":", 1)[1].split(","):
            # "HUAWEI Mate XT | ULTIMATE DESIGN" is the Mate XT; the brand word goes wherever it is.
            name = name.split("|")[0]
            name = re.sub(rf"\b{re.escape(brand)}\b", " ", name, flags=re.I)
            name = re.sub(r"\s+", " ", name).strip()
            if len(name) >= 2:
                models.append({"brand": brand.capitalize(), "name": name, "cadence": cadence})
    return models


# Longest first: "bi-monthly" also contains "monthly".
HEADING_CADENCES = (("bi-monthly", "bimonthly"), ("monthly", "monthly"), ("quarterly", "quarterly"))


def parse_samsung(page):
    """[{brand, name, cadence}] from the scope page (commented-out sections are skipped)."""
    page = re.sub(r"<!--.*?-->", "", page, flags=re.S)
    models = []
    for block in re.split(r'<div class="txt_section txt_section_workscope">', page)[1:]:
        heading = re.search(r"<strong>(.*?)</strong>", block, re.S)
        if not heading:
            continue
        title = text_of(heading.group(1)).lower()
        cadence = next((value for key, value in CADENCES if key in title), None)
        if cadence is None:
            continue
        for inner in re.findall(r'<ul class="list_circle_s">(.*?)</ul>', block, re.S):
            for line in items(inner):
                for name in (n.strip() for n in line.split(",")):
                    if len(name) >= 2:
                        models.append({"brand": "Samsung", "name": name, "cadence": cadence})
    return models


SOURCES = [
    {"brand": "Google", "url": PIXEL_POLICY, "modelStartsWith": ["Google", "Pixel"], "types": ["Phone"], "complete": False},
    # The scope page lists every Galaxy phone, tablet and watch that still gets security updates.
    {"brand": "Samsung", "url": SAMSUNG_SCOPE, "modelStartsWith": ["Samsung", "Galaxy"], "types": ["Phone", "Tablet", "Watch"], "complete": True},
    # Huawei's and Honor's pages cover their phones and tablets only (not watches or earbuds).
    {"brand": "Huawei", "url": HUAWEI_BULLETIN, "modelStartsWith": ["Huawei"], "types": ["Phone", "Tablet"], "complete": True},
    {"brand": "Honor", "url": HONOR_BULLETIN, "modelStartsWith": ["Honor"], "types": ["Phone", "Tablet"], "complete": True},
]


def build(pages):
    dates = parse_pixel_dates(pages["pixel_dates.html"])
    pixels = parse_pixel_policy(pages["pixel_policy.html"], dates)
    samsung = parse_samsung(pages["samsung_scope.html"])
    huawei = parse_heading_lists(pages["huawei_bulletin.html"], "huawei", HEADING_CADENCES)
    honor = parse_heading_lists(pages["honor_bulletin.html"], "honor", HEADING_CADENCES)
    for label, found, minimum in (("Pixel phones", pixels, MIN_PIXELS), ("Samsung models", samsung, MIN_SAMSUNG),
                                  ("Huawei models", huawei, MIN_HUAWEI), ("Honor models", honor, MIN_HONOR)):
        if len(found) < minimum:
            raise PageError(f"only {len(found)} {label} read (expected at least {minimum})")
    seen = set()
    models = []
    for entry in pixels + samsung + huawei + honor:
        key = (entry["brand"], entry["name"].lower())
        if key not in seen:  # a model listed twice keeps its first (most supported) entry
            seen.add(key)
            models.append(entry)
    return models


def document(models, revision):
    return {"schemaVersion": 1, "revision": revision, "sources": SOURCES, "models": models}


def render(doc):
    """One model per line: readable diffs."""
    head = json.dumps({k: doc[k] for k in ("schemaVersion", "revision")}, separators=(",", ":"))[:-1]
    sources = ",\n".join(json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in doc["sources"])
    models = ",\n".join(json.dumps(m, ensure_ascii=False, separators=(",", ":")) for m in doc["models"])
    return f'{head},"sources":[\n{sources}\n],"models":[\n{models}\n]}}\n'


def previous():
    try:
        old = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return 0, None
    return old.get("revision", 0), {"sources": old.get("sources"), "models": old.get("models", [])}


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "gadget-index-support/1.0 (+https://github.com/Shareefoo/gadget-index)"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read(MAX_DOWNLOAD + 1)
    if len(raw) > MAX_DOWNLOAD:
        raise OSError(f"{url} is larger than 8 MB")
    return raw.decode("utf-8", "replace")


def main():
    args = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    args.add_argument("--pages", help="folder with saved copies of the three pages")
    args.add_argument("--check", action="store_true", help="only report whether the file would change")
    options = args.parse_args()

    try:
        if options.pages:
            pages = {name: (Path(options.pages) / name).read_text(encoding="utf-8") for name in PAGES}
        else:
            pages = {name: download(url) for name, url in PAGES.items()}
        models = build(pages)
    except (OSError, UnicodeError, PageError) as e:
        print(f"Could not read the support pages: {e}", file=sys.stderr)
        return 1

    old_revision, old = previous()
    before = len(old["models"]) if old else 0
    if before and len(models) < before * MIN_SHARE_OF_PREVIOUS:
        print(f"Refusing to write: {len(models)} models now, {before} in the current file (a page may have changed).", file=sys.stderr)
        return 1
    if old == {"sources": SOURCES, "models": models}:
        print(f"Unchanged: {len(models)} models, revision {old_revision}.")
        return 0
    if options.check:
        print(f"Would change: {before} -> {len(models)} models.")
        return 1
    OUTPUT.write_text(render(document(models, old_revision + 1)), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT.name}: {before} -> {len(models)} models, revision {old_revision + 1}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
