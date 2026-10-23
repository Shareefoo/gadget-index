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
tablets), one group per brand. `revision` goes up by one only when the content changes, so running this
twice in a row changes nothing. If the download looks wrong (too small, or far smaller than the current
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


def document(groups, revision):
    return {
        "schemaVersion": 1,
        "revision": revision,
        "groups": [{"type": "Phone", "brand": brand, "names": groups[brand]} for brand in sorted(groups, key=str.lower)],
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
    """(revision, {brand: names}) of the current file; (0, {}) when there is none."""
    try:
        old = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return 0, {}
    groups = {g["brand"]: g["names"] for g in old.get("groups", []) if isinstance(g, dict)}
    return old.get("revision", 0), groups


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
        groups = parse(decode(raw))
    except (OSError, UnicodeError, csv.Error) as e:
        print(f"Could not read the device list: {e}", file=sys.stderr)
        return 1

    old_revision, old_groups = previous()
    total, before = count(groups), count(old_groups)
    if total < MIN_MODELS or (before and total < before * MIN_SHARE_OF_PREVIOUS):
        print(
            f"Refusing to write: {total} models now, {before} in the current file "
            f"(the list format may have changed).",
            file=sys.stderr,
        )
        return 1

    if groups == old_groups:
        print(f"Unchanged: {total} models, revision {old_revision}.")
        return 0
    if options.check:
        print(f"Would change: {before} -> {total} models.")
        return 1
    OUTPUT.write_text(render(document(groups, old_revision + 1)), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT.name}: {before} -> {total} models, revision {old_revision + 1}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
