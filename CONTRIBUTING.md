# Contributing — TDD

## Stack
- **JS**: `node --test tests/Model.test.js` (no deps, Node 22 built-in `node:test`). `Model.js` is `.pragma library` — tests load it via `vm`.
- **Python**: `python3 -m unittest discover -s tests/python -v` (or `pytest`). Covers `bin/fetch-manifest.py` slim + contracts, `_sec` hardening (TOML, paths, deadline, manifest), apply/set-wallpaper end-to-end with isolated `HOME`.
- **QML (local only)**: `qmllint -I /usr/share/omarchy/shell -I /usr/lib/qt6/qml Panel.qml BarWidget.qml` + `omarchy plugin validate ./`. GitHub CI cannot install Omarchy/Quickshell on generic runners, so it runs the portable JS/Python suite; always run `npm run test:qml` locally before a release.

## TDD loop
1. `npm test` — red
2. Implement minimal fix in `Model.js`/`Panel.qml`/`bin/*.py`
3. `npm test` — green
4. `npm run test:qml && omarchy-restart-shell` → `grim` → visual check

## Conventions
- No `/home/*` hardcodes — use `Qt.resolvedUrl`, `~`, `expanduser`, `StandardPaths`.
- Keep `manifest.json` valid: `omarchy plugin validate ./` must pass.
- Add preview to `preview.png` (1280px, <1 MB) and reference in README.
- Bar icon stays `\\uF03E` (`JetBrainsMono Nerd Font`), README uses `🖼️` + image.

## Adding features
- Put auto logic in `Panel.qml` root `Timer` (even when closed, `Loader active:true` keeps it alive).
- Wallpaper-only: `bin/set-wallpaper.py` + `omarchy-theme-bg-set`, no `colors.toml`.
- Random: `Model.apply` → `filtered` → `Math.random()`.

See `tests/README.md` for fixtures and `bin/*.py` for slim fields.
