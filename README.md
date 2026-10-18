# gadget-index

A small, public index of consumer gadgets used by the Kithub Android app: which update and news
sources belong to which device, and model names for watches, headphones and similar devices.
It holds only public source addresses and model names. No user data.

| File | What it is |
|---|---|
| `source_catalog.json` | update and news sources, and which devices get them |
| `device_models.json` | model names offered when adding a device |

Published (GitHub Pages) at:

- <https://shareefoo.github.io/gadget-index/source_catalog.json>
- <https://shareefoo.github.io/gadget-index/device_models.json>

The app also ships a copy of both files and uses whichever has the higher `revision`.

## Changing a file

1. Edit the JSON.
2. **Bump `revision`** in the file you changed. Installs ignore a published copy whose revision is
   not higher than the one they have, so a change without a bump never reaches anyone.
3. Check it:
   ```bash
   python3 tools/validate_catalog.py
   python3 tools/validate_catalog.py --base origin/main   # also requires the revision bump
   ```
4. Open a pull request. The `Catalogue` workflow validates it; once merged it publishes both files.

To roll back, publish the older content with a **higher** revision.

### `source_catalog.json`

```json
{ "schemaVersion": 1, "revision": 3,
  "sources": [
    { "id": "pixel-update-bulletins",          // unique, stable
      "name": "Pixel Update Bulletins",          // shown in the app
      "kind": "updates",                         // "updates" or "news"
      "url": "https://...",                      // https only; RSS, Atom, or a bulletin page the app can parse
      "types": ["Phone", "Tablet"],              // Phone, Watch, Headphones, Laptop, Tablet, Other; empty = any
      "modelStartsWith": ["Google"],             // any of these ...
      "modelContains": ["Pixel"],                // ... and any of these (case-insensitive); empty = any
      "supersededBy": ["other-source-id"] } ] }  // dropped when one of these also matches
```

A feed that is not RSS or Atom needs parser code in the app first. A source whose format the
app cannot read is simply skipped there, so check that it works in the app before adding it.

### `device_models.json`

```json
{ "schemaVersion": 1, "revision": 1,
  "groups": [ { "type": "Watch", "brand": "Samsung", "names": ["Galaxy Watch7", "Galaxy Watch8"] } ] }
```

The picker shows `brand + name` (the brand is not repeated if the name already starts with it).
Write names so the `modelStartsWith` / `modelContains` rules above match them, for example
"Samsung Galaxy Watch7", "Google Pixel Watch 3". Official spelling is preferred; users can
always type a model that is not listed.

## Guidelines

- Only add sources that publish freely and that you may link to. The app shows a headline, the
  source and a link; it does not copy article text.
- No brand logos or trademarked artwork. This repository only lists names and addresses.
- Prefer an official feed over a scraped page; scraped pages break when the site changes.

## License

[MIT](LICENSE).
