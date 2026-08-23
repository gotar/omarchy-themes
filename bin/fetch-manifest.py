#!/usr/bin/env python3
"""Fetch + slim the omarchy-themes index for the gotar.omarchy-themes shell plugin.

Source: https://bjarneo.github.io/omarchy-themes/wallpapers.js
(~35 MB, `window.WALLPAPERS_BASE_URL = "..."; window.WALLPAPERS = {...}`).

Writes a slimmed manifest to ~/.cache/gotar.omarchy-themes/manifest.json
(only the fields the browser UI needs) and prints the slim manifest JSON
to stdout. Cached for 24h; use --force to re-fetch.

Exit: 0 on success (incl. cache hit), 1 on failure.
Failure prints {"error": "..."} to stdout.
"""
import json
import os
import sys
import tempfile
import time
import urllib.request

SOURCE = "https://bjarneo.github.io/omarchy-themes/wallpapers.js"
CACHE_DIR = os.path.expanduser("~/.cache/gotar.omarchy-themes")
MANIFEST = os.path.join(CACHE_DIR, "manifest.json")
TTL = 24 * 3600
ANSI = ["color%d" % i for i in range(16)]
VARIANTS = ["palette", "gruvbox", "nord", "material", "aether"]
UA = {"User-Agent": "omarchy-themes-plugin/1.0 (+omarchy shell)"}


def fail(msg):
    print(json.dumps({"error": str(msg)}))
    sys.exit(1)


def cached():
    try:
        with open(MANIFEST) as f:
            return json.load(f)
    except Exception:
        return None


def main():
    force = "--force" in sys.argv[1:]
    if not force:
        hit = cached()
        if hit and "entries" in hit and time.time() - int(hit.get("fetchedAt", 0)) < TTL:
            print(json.dumps(hit, separators=(",", ":")))
            return

    os.makedirs(CACHE_DIR, exist_ok=True)
    req = urllib.request.Request(SOURCE, headers=UA)
    raw = urllib.request.urlopen(req, timeout=300).read().decode("utf-8", "replace")

    base = ""
    m = raw.find('window.WALLPAPERS_BASE_URL = "')
    if m != -1:
        end = raw.index('"', m + len('window.WALLPAPERS_BASE_URL = "'))
        base = raw[m + len('window.WALLPAPERS_BASE_URL = "'):end].rstrip("/")

    start = raw.index("window.WALLPAPERS = ")
    start = raw.index("{", start)
    end = raw.rindex("}")
    data = json.loads(raw[start:end + 1])

    entries = []
    for path, e in data.items():
        themes = {}
        for v in VARIANTS:
            t = (e.get("themes") or {}).get(v)
            if not t:
                continue
            c = t.get("colors") or {}
            themes[v] = {
                "n": t.get("name", ""),
                "ct": t.get("colors_toml", ""),
                "bg": t.get("background", ""),
                "c": [c.get(k, "") for k in ANSI],
            }
        entries.append({
            "p": path,
            "t": e.get("title", "") or path.rsplit("/", 1)[-1],
            "tone": e.get("tone", ""),
            "color": e.get("color", ""),
            "tags": e.get("tags", []),
            "w": e.get("width", 0),
            "h": e.get("height", 0),
            "thumb": e.get("thumb_path", ""),
            "med": e.get("medium_path", "") or path,
            "pal": e.get("colors", []),
            "th": themes,
        })

    out = {"base": base, "fetchedAt": int(time.time()), "count": len(entries),
           "entries": entries}
    fd, tmp = tempfile.mkstemp(dir=CACHE_DIR, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    os.replace(tmp, MANIFEST)
    print(json.dumps(out, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        fail(ex)
