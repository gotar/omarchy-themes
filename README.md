# gotar.omarchy-themes

An Omarchy shell plugin (bar widget + panel) for browsing
[bjarneo/omarchy-themes](https://bjarneo.github.io/omarchy-themes/) —
3,000+ wallpapers, each available in five theme variants (Palette, Warm,
Cool, Material, Aether).

- Search (path + title + tags, same semantics as the website)
- Facet filters with live counts: tone, color, resolution tier range
  (`≥` / `≤`), exactly like the site
- Click a wallpaper → detail view with palette, tags, and the five
  variants
- **One-click apply**: downloads the variant's `colors.toml` + background
  into `~/.config/omarchy/themes/<slug>/` and runs `omarchy theme set
  <slug>` — the variant becomes a normal user theme

## Install

From this repository:

```sh
omarchy plugin add https://github.com/gotar/omarchy-themes.git --enable
omarchy bar put gotar.omarchy-themes --after omarchy.weather
```

Or clone it into `~/.config/omarchy/plugins/gotar.omarchy-themes/` and
run `omarchy-shell shell rescanPlugins`.

## Usage

Click the **** bar widget (center section, after the weather icon).

| Key | Action |
| --- | --- |
| `/` | focus the search field |
| `← → ↑ ↓` | move grid cursor / in detail: cycle wallpaper / variant |
| `Enter` | open detail / apply the selected variant |
| `Esc` | back / close |
| `x` | reset filters |
| `r` | re-fetch the index (bypass 24 h cache) |
| `Tab` | cycle to previous/next open panel |

Mouse works everywhere: hover + click facets, click a card, click a
variant's **Apply** button.

## How it works

- On first open the panel runs `bin/fetch-manifest.py`, which downloads
  the site's 35 MB `wallpapers.js` index, trims it to the fields the UI
  needs, and caches the result at
  `~/.cache/gotar.omarchy-themes/manifest.json` (24 h TTL).
- Applying a variant runs `bin/apply-theme.py <slug> <base-url>
  <colors.toml> <background>`, which writes the theme files atomically
  (re-applying is idempotent), then the panel runs `omarchy theme set
  <slug>`.

No network access is needed for the UI itself beyond the one-time index
fetch and the media downloads for thumbnails/previews/applied
backgrounds (served from the collection's object storage).

## Layout

```
manifest.json          plugin manifest (bar-widget kind)
BarWidget.qml          bar button ( wallpaper icon) + panel host
Panel.qml              browser UI: search, facets, grid, detail, apply
Model.js               port of the site's filter/search logic
bin/fetch-manifest.py  downloads + slims + caches the wallpaper index
bin/apply-theme.py     installs one variant as a user theme
```
