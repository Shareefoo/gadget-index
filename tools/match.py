#!/usr/bin/env python3
"""Shows which sources a device gets, or how much of the model list has any.

    python tools/match.py Watch "Samsung Galaxy Watch8"   # sources for one device
    python tools/match.py --coverage                      # share of models with a source, per brand
    python tools/match.py --coverage --markdown           # same as a table (used for the CI summary)

Standard library only. The rules are in tools/matching.py.
"""

import argparse
import sys
from collections import defaultdict

import matching


def show(device_type, model, catalog):
    result = matching.sources_for(catalog, device_type, model)
    by_id = {s["id"]: s for s in catalog["sources"]}
    print(f"{device_type}: {model}")
    for kind in ("updates", "news"):
        ids = result[kind]
        print(f"  {kind}: " + (", ".join(ids) if ids else "none"))
        for source_id in ids:
            print(f"      {by_id[source_id]['url']}")


def coverage(catalog, models, markdown):
    per_brand = defaultdict(lambda: [0, 0, 0])  # models, with news, with updates
    for device_type, brand, shown in matching.all_models(models):
        result = matching.sources_for(catalog, device_type, shown)
        row = per_brand[(device_type, brand or "(no brand)")]
        row[0] += 1
        row[1] += bool(result["news"])
        row[2] += bool(result["updates"])

    total = sum(r[0] for r in per_brand.values())
    news = sum(r[1] for r in per_brand.values())
    updates = sum(r[2] for r in per_brand.values())
    none = [(k, r[0]) for k, r in per_brand.items() if r[1] == 0 and r[2] == 0]
    uncovered = sum(n for _, n in none)

    lines = [
        f"Models: {total}. With a news source: {news} ({100 * news // max(total, 1)}%). "
        f"With an updates source: {updates} ({100 * updates // max(total, 1)}%). "
        f"Brand groups with no source at all: {len(none)} of {len(per_brand)} ({uncovered} models).",
        "",
    ]
    largest = sorted(none, key=lambda item: -item[1])[:15]
    if markdown:
        lines += ["| Type | Brand | Models | No source |", "|---|---|---|---|"]
        lines += [f"| {t} | {b} | {n} | yes |" for (t, b), n in largest]
    else:
        lines.append("Largest brand groups with no source:")
        lines += [f"  {n:4d}  {t} / {b}" for (t, b), n in largest]
    print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("device_type", nargs="?", help="Phone, Watch, Headphones, Laptop, Tablet or Other")
    parser.add_argument("model", nargs="?", default="", help="the model as the picker shows it, e.g. 'Garmin Fenix 8'")
    parser.add_argument("--coverage", action="store_true", help="report how many models get a source")
    parser.add_argument("--markdown", action="store_true", help="coverage as a markdown table")
    args = parser.parse_args()

    catalog = matching.load("source_catalog.json")
    if args.coverage:
        coverage(catalog, matching.load("device_models.json"), args.markdown)
        return 0
    if not args.device_type:
        parser.error("give a device type and a model, or use --coverage")
    show(args.device_type, args.model, catalog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
