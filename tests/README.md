# Tests

- `tests/Model.test.js` — `Model.bucketRes`, `prep` (incl. missing tags), `apply` (tone/color/res + live res facet counts), `variantKeys`, `titleCase`. Run `npm test`.
- `tests/python/test_bin.py` — behavior tests, no network: `apply-theme` slug/allowlist/required-`ct` validation + background fallback (mocked `http_get`), `fetch-manifest` `slim_entry` build (malformed entry/variant skip), `_sec` allowlist/relpath (incl. `.` / `..`)/sniff (incl. AVIF vs AVI)/slug/manifest validation, real TOML parsing, total download deadline, stale-cache fallback, `set-wallpaper` end-to-end (isolated `HOME`, fake helpers: success / symlink fallback / hard failure), theme-dir symlink refusal, temp-file cleanup, wallpaper cache pruning. Run `python3 -m unittest discover -s tests/python -v`.
- `tests/Model.test.js` uses `vm` to load `Model.js` (cross-realm, so compare via `JSON.stringify`).

TDD: write failing test → implement → `npm test` green → `qmllint` → `grim`.
