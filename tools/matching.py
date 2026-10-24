"""Which sources does a device get? A Python copy of the matching in the Kithub app.

The app does this in SourceCatalog.kt (`CatalogSource.matches` and `SourceCatalog.select`).
Keep the two in step: the tests in tests/ describe the expected results, and the Kithub app has
the same cases in its own unit tests.

Rules
- Every non-empty list narrows the match; an empty or missing list means "any".
- `types`: the device type must be one of them.
- `modelStartsWith` / `modelContains`: any entry matches, case-insensitive, on the trimmed model.
- `modelNotStartsWith`: a model starting with any entry never matches (keeps Android-wide sources
  away from an iPhone someone adds by name).
- After matching, a source is dropped when one of its `supersededBy` ids also matched (same kind).
- Sources with the same url are listed once.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def display(brand, name):
    """The text the picker shows and the app stores as the model (CatalogModel.display)."""
    if not brand.strip() or name.lower().startswith(brand.lower()):
        return name
    return f"{brand} {name}"


def matches(source, device_type, model):
    types = source.get("types") or []
    if types and device_type not in types:
        return False
    text = model.strip().lower()
    starts = source.get("modelStartsWith") or []
    if starts and not any(text.startswith(s.lower()) for s in starts):
        return False
    contains = source.get("modelContains") or []
    if contains and not any(c.lower() in text for c in contains):
        return False
    if any(text.startswith(n.lower()) for n in source.get("modelNotStartsWith") or []):
        return False
    return True


def select(sources, kind, device_type, model=""):
    matched = [s for s in sources if s["kind"] == kind and matches(s, device_type, model)]
    ids = {s["id"] for s in matched}
    kept, seen_urls = [], set()
    for source in matched:
        if set(source.get("supersededBy") or []) & ids:
            continue
        if source["url"] in seen_urls:
            continue
        seen_urls.add(source["url"])
        kept.append(source)
    return kept


def sources_for(catalog, device_type, model=""):
    """{'updates': [ids], 'news': [ids]} for one device, in catalogue order."""
    sources = catalog["sources"]
    return {
        "updates": [s["id"] for s in select(sources, "updates", device_type, model)],
        "news": [s["id"] for s in select(sources, "news", device_type, model)],
    }


def all_models(models):
    """Every (type, brand, display name) in device_models.json."""
    for group in models["groups"]:
        brand = group.get("brand", "")
        for name in group["names"]:
            yield group["type"], brand, display(brand, name)
