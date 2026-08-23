# Tests

- `tests/Model.test.js` — `Model.bucketRes`, `prep`, `apply` (tone/color/res), `variantKeys`, `titleCase`. Run `npm test`.
- `tests/python/test_bin.py` — `apply-theme` slug validation + fallback presence, `fetch-manifest` slim fields. Run `python3 -m unittest discover -s tests/python -v`.
- `tests/Model.test.js` uses `vm` to load `Model.js` (cross-realm, so compare via `JSON.stringify`).

TDD: write failing test → implement → `npm test` green → `qmllint` → `grim`.
