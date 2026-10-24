#!/usr/bin/env python3
"""Builds phone_models.json from Google's public list of Android devices.

    python tools/build_phones.py                     # download the list, rewrite phone_models.json if it changed
    python tools/build_phones.py --input list.csv    # use a saved copy (UTF-16, as Google publishes it)
    python tools/build_phones.py --check             # exit 1 when the file would change; writes nothing

The source is https://storage.googleapis.com/play_public/supported_devices.csv (Retail Branding, Marketing
Name, Device, Model). The rules are those of DeviceCatalogParser in the Kithub app, which this file replaces:
a row needs a marketing name of at least 2 characters without "_" (those are build code names), and a model
is listed once per displayed name (the brand is not repeated when the name already starts with it).

The output has the same layout as device_models.json (type "Phone"; the app offers these for phones and
tablets), one group per brand, plus a "codes" object per group: marketing name -> the model codes Android
reports for it (`Build.MODEL`, the list's Model column), so the app can show "Samsung Galaxy S10" for a
phone that calls itself "SM-G973F". Codes that already read as the name ("Pixel 8") are left out, and a
code listed for several names goes to the one it is listed with most. `revision` goes up by one only when
the content changes, so running this twice in a row changes nothing. If the download looks wrong (too small, or far smaller than the current
file, which means Google changed the format) nothing is written and the exit code is 1.
Standard library only. Run weekly by .github/workflows/phones.yml.
"""

import argparse
import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "phone_models.json"
SOURCE_URL = "https://storage.googleapis.com/play_public/supported_devices.csv"
MAX_DOWNLOAD = 12 * 1024 * 1024
MAX_NAME_LENGTH = 100  # the app skips longer names
MAX_CODE_LENGTH = 40  # and longer codes
MIN_MODELS = 5000  # the list has about 40,000
MIN_SHARE_OF_PREVIOUS = 0.8


def decode(raw):
    """Google's file is UTF-16 with a byte order mark; accept UTF-8 too (saved copies)."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def displayed(brand, name):
    return name if not brand or name.lower().startswith(brand.lower()) else f"{brand} {name}"


def parse(text):
    """{brand: sorted names} from the CSV text; the same filtering as the app's parser."""
    rows = csv.reader(io.StringIO(text))
    next(rows, None)  # header
    seen = set()
    groups = {}  # lower-case brand -> names; the retail branding is spelled inconsistently ("allnet" / "Allnet")
    spellings = {}  # lower-case brand -> {spelling: rows}
    for row in rows:
        if len(row) < 2:
            continue
        brand, name = row[0].strip(), row[1].strip()
        if len(name) < 2 or len(name) > MAX_NAME_LENGTH or "_" in name:
            continue
        key = displayed(brand, name).lower()
        if key in seen:
            continue
        seen.add(key)
        groups.setdefault(brand.lower(), []).append(name)
        counts = spellings.setdefault(brand.lower(), {})
        counts[brand] = counts.get(brand, 0) + 1
    # The most common spelling names the group (ties: the one with more capitals, then alphabetical).
    return {
        max(spellings[key], key=lambda s: (spellings[key][s], sum(c.isupper() for c in s), s)): sorted(names, key=str.lower)
        for key, names in groups.items()
    }


def parse_codes(text, groups):
    """{brand: {name: sorted codes}} for the names in [groups] (from parse) whose code is not readable."""
    stored = {}  # displayed name, lower case -> (brand as in groups, name as in groups)
    for brand, names in groups.items():
        for name in names:
            stored[displayed(brand, name).lower()] = (brand, name)
    votes = {}  # code, lower case -> {(brand, name): rows}
    spelling = {}  # code, lower case -> first spelling seen
    rows = csv.reader(io.StringIO(text))
    next(rows, None)
    for row in rows:
        if len(row) < 4:
            continue
        brand, name, code = row[0].strip(), row[1].strip(), row[3].strip()
        target = stored.get(displayed(brand, name).lower())
        if target is None or not code or len(code) > MAX_CODE_LENGTH:
            continue
        # "Pixel 8" for the Pixel 8: Android's own name is fine already.
        if displayed(*target).lower().endswith(code.lower()):
            continue
        key = code.lower()
        spelling.setdefault(key, code)
        counts = votes.setdefault(key, {})
        counts[target] = counts.get(target, 0) + 1
    codes = {}
    for key, counts in votes.items():
        # Most rows win; ties go to the first one listed (dicts keep their order).
        brand, name = max(counts, key=counts.get)
        codes.setdefault(brand, {}).setdefault(name, []).append(spelling[key])
    return {brand: {name: sorted(c, key=str.lower) for name, c in by_name.items()} for brand, by_name in codes.items()}


def document(groups, revision, codes=None):
    codes = codes or {}

    def group(brand):
        g = {"type": "Phone", "brand": brand, "names": groups[brand]}
        if codes.get(brand):
            g["codes"] = {name: codes[brand][name] for name in groups[brand] if name in codes[brand]}
        return g

    return {
        "schemaVersion": 1,
        "revision": revision,
        "groups": [group(brand) for brand in sorted(groups, key=str.lower)],
    }


def render(doc):
    """One group per line: small file, readable diffs."""
    lines = [json.dumps(g, ensure_ascii=False, separators=(",", ":")) for g in doc["groups"]]
    return (
        '{"schemaVersion":%d,"revision":%d,"groups":[\n' % (doc["schemaVersion"], doc["revision"])
        + ",\n".join(lines)
        + "\n]}\n"
    )


def count(groups):
    return sum(len(names) for names in groups.values())


def previous():
    """(revision, {brand: names}, {brand: {name: codes}}) of the current file; (0, {}, {}) when there is none."""
    try:
        old = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return 0, {}, {}
    groups = {g["brand"]: g["names"] for g in old.get("groups", []) if isinstance(g, dict)}
    codes = {g["brand"]: g["codes"] for g in old.get("groups", []) if isinstance(g, dict) and g.get("codes")}
    return old.get("revision", 0), groups, codes


def download():
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "gadget-index-phones/1.0 (+https://github.com/Shareefoo/gadget-index)"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read(MAX_DOWNLOAD + 1)
    if len(raw) > MAX_DOWNLOAD:
        raise OSError("the list is larger than 12 MB")
    return raw


def main():
    args = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    args.add_argument("--input", help="read this saved copy instead of downloading")
    args.add_argument("--check", action="store_true", help="only report whether the file would change")
    options = args.parse_args()

    try:
        raw = Path(options.input).read_bytes() if options.input else download()
        text = decode(raw)
        groups = parse(text)
        codes = parse_codes(text, groups)
    except (OSError, UnicodeError, csv.Error) as e:
        print(f"Could not read the device list: {e}", file=sys.stderr)
        return 1

    old_revision, old_groups, old_codes = previous()
    total, before = count(groups), count(old_groups)
    if total < MIN_MODELS or (before and total < before * MIN_SHARE_OF_PREVIOUS):
        print(
            f"Refusing to write: {total} models now, {before} in the current file "
            f"(the list format may have changed).",
            file=sys.stderr,
        )
        return 1

    if groups == old_groups and codes == old_codes:
        print(f"Unchanged: {total} models, revision {old_revision}.")
        return 0
    if options.check:
        print(f"Would change: {before} -> {total} models.")
        return 1
    OUTPUT.write_text(render(document(groups, old_revision + 1, codes)), encoding="utf-8", newline="\n")
    coded = sum(len(c) for by_name in codes.values() for c in by_name.values())
    print(f"Wrote {OUTPUT.name}: {before} -> {total} models ({coded} model codes), revision {old_revision + 1}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
