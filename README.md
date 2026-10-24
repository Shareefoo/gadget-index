# gadget-index

A small, public index of consumer gadgets used by the Kithub Android app: which update and news
sources belong to which device, and model names for watches, headphones and similar devices.
It holds only public source addresses and model names. No user data.

| File | What it is |
|---|---|
| `source_catalog.json` | update and news sources, and which devices get them |
| `device_models.json` | model names offered when adding a device (watches, headphones, ...), kept by hand |
| `phone_models.json` | phone and tablet names with Android's model codes, **generated** from Google's public device list (do not edit) |
| `support.json` | how long phones get security updates, **generated** from Google's and Samsung's pages (do not edit) |

Published (GitHub Pages) at:

- <https://shareefoo.github.io/gadget-index/source_catalog.json>
- <https://shareefoo.github.io/gadget-index/device_models.json>
- <https://shareefoo.github.io/gadget-index/phone_models.json>
- <https://shareefoo.github.io/gadget-index/support.json>

The app also ships a copy of these files and uses whichever has the higher `revision`.

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
      "supersededBy": ["other-source-id"],       // dropped when one of these also matches
      "filterByModel": false } ] }               // news only: keep stories that mention the device's model
```

**`filterByModel`** lets one general tech-news feed serve many brands. The app keeps only stories whose title or
summary mentions the device's model (whole words, case-insensitive; "Galaxy Watch8" also finds "Galaxy Watch 8"),
and does this before cutting the feed to its newest entries. A device with no real model name (`[YOUR MODEL]`)
gets nothing from such a source. Use it for broad feeds (press sites); leave it off for a brand's own feed, whose
stories are all relevant to its devices. The validator rejects it on update sources.

Adding a field that older app versions would misread (like this one: an old app would show the whole press feed
unfiltered) needs a new `kind` value or a `schemaVersion` bump, because apps skip entries with an unknown `kind`.

**Limits.** The app skips anything beyond these, and the validator rejects it: 200 sources; ids and names up to 120
characters; urls up to 2,048; 50 entries per list; and a source needs at least one of `types`, `modelStartsWith`
or `modelContains` (otherwise every device would fetch it), unless it is a news source with `filterByModel`.
For `device_models.json` and `phone_models.json`: names up to 100 characters and 100,000 names in total.

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

### `phone_models.json`

Same layout as `device_models.json` (all groups have type `Phone`; the app offers them for phones and tablets,
one group per brand, about 33,000 names, roughly 290 KB compressed). Nobody edits it: `tools/build_phones.py`
rebuilds it from Google's public list (`supported_devices.csv`) and raises `revision` by one only when the
content changes. To add a phone Google's list lacks, the user types its name in the app.

Each group also has `"codes"`: marketing name -> the model codes Android reports for it (`Build.MODEL`, the
list's Model column), e.g. `"Galaxy S10": ["SM-G973F", ...]`, so the app shows "Samsung Galaxy S10" for a phone
that calls itself "SM-G973F". Codes that already read as the name ("Pixel 8") are left out; a code listed for
several names goes to the one it is listed with most. Codes up to 40 characters, 100,000 in total. Older app
versions ignore the field.

### `support.json`

How long phones get security updates, so the app can say "Security updates until October 2027" and stop
announcing monthly patches to a phone that no longer gets them. Nobody edits it: `tools/build_support.py`
reads it from the makers' own pages and nothing in it is guessed:

- Google's [Pixel update policy](https://support.google.com/pixelphone/answer/4457705) (N years from the
  US Google Store availability month, or "no longer receive" updates) and the
  [availability months](https://support.google.com/pixelphone/answer/15738422): `"until": "YYYY-MM"` or
  `"ended": true`.
- Samsung's [security updates scope](https://security.samsungmobile.com/workScope.smsb): the models that get
  monthly, quarterly or biannual updates now, as `"cadence"`. It has no end dates. Its source is
  `"complete": true` for phones, tablets and watches: a Galaxy one that is not listed is shown as "not on
  Samsung's list of devices that get security updates".

```json
{ "schemaVersion": 1, "revision": 1,
  "sources": [ { "brand": "Samsung", "url": "https://...", "modelStartsWith": ["Samsung", "Galaxy"],
                 "types": ["Phone", "Tablet", "Watch"], "complete": true } ],
  "models": [ { "brand": "Google", "name": "Pixel 7", "until": "2027-10" },
              { "brand": "Samsung", "name": "Galaxy S23", "cadence": "monthly" } ] }
```

Up to 5,000 models; each has exactly one of `until`, `ended`, `cadence`. The pages are HTML, so a layout
change makes the builder fail (it then writes nothing) until its parser is fixed.

## Checks and tools

All standard-library Python 3, nothing to install.

| Command | What it does |
|---|---|
| `python3 tools/validate_catalog.py [--base origin/main]` | schema and consistency of all four files; with `--base`, requires the revision bump |
| `python3 -m unittest discover -s tests -v` | matching tests: `tests/matching.json` lists devices with the exact sources they must get, and `brandRules` check that every listed model of a brand still matches that brand's sources |
| `python3 tools/build_phones.py [--check] [--input list.csv]` | rebuilds `phone_models.json`; refuses a download that is too small or far smaller than the current file |
| `python3 tools/build_support.py [--check] [--pages DIR]` | rebuilds `support.json` from the Google and Samsung pages; refuses a page it cannot read or a result far smaller than the current file |
| `python3 tools/match.py Watch "Garmin Fenix 8"` | which sources one device gets |
| `python3 tools/match.py --coverage` | how many models have a news or updates source, and the biggest brands with none |
| `python3 tools/check_sources.py` | downloads every source and checks it still parses and has recent entries |

`tools/matching.py` is a copy of the app's matching rules (`SourceCatalog.kt` in Kithub). If the rules
change in the app, change them here and in `tests/matching.json` too.

Workflows:
- **Catalogue** (`catalog.yml`): on every pull request and push it runs the tests, prints the coverage
  summary and validates; after a push to the default branch it publishes the four files to GitHub Pages.
- **Phone list** (`phones.yml`): every Wednesday it rebuilds `phone_models.json`. If it changed, the workflow
  validates it, commits it to the default branch and starts the Catalogue workflow to publish it. A failing
  run (Google moved or changed the file) commits nothing. It needs permission to push to the default branch;
  with branch protection, change it to open a pull request.
- **Support list** (`support.yml`): every Wednesday after the phone list, the same for `support.json`. A failing
  run means a page changed its layout: look at the page and fix `tools/build_support.py`.
- **Source health** (`health.yml`): every Monday it runs `check_sources.py`. A broken source opens an issue
  ("Source health check failed"), later runs add to it, and it is closed when everything is healthy again.
  It can be started by hand from the Actions tab. Stale means: news older than 180 days, updates older
  than 75 days. Some sites treat data-centre addresses differently from phones, so a failure is a prompt
  to look at the source, not proof that it is broken in the app.

## Guidelines

- Only add sources that publish freely and that you may link to. The app shows a headline, the
  source and a link; it does not copy article text.
- No brand logos or trademarked artwork. This repository only lists names and addresses.
- Prefer an official feed over a scraped page; scraped pages break when the site changes.

## License

[MIT](LICENSE).
