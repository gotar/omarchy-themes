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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sec

SOURCE = "https://bjarneo.github.io/omarchy-themes/wallpapers.js"
CACHE_DIR = os.path.expanduser("~/.cache/gotar.omarchy-themes")
MANIFEST = os.path.join(CACHE_DIR, "manifest.json")
TTL = 24 * 3600
ANSI = ["color%d" % i for i in range(16)]
VARIANTS = ["palette", "gruvbox", "nord", "material", "aether"]


def fail(msg):
    _sec.fail(msg)


def load_cached_manifest():
    """Read + validate the cached manifest, or None if unusable."""
    try:
        data = _sec.read_file_capped(MANIFEST, _sec.BYTE_LIMIT_MANIFEST)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None
    try:
        hit = json.loads(data.decode("utf-8"))
        _sec.validate_slim_manifest(hit)
        return hit
    except Exception:
        return None


def main():
    force = "--force" in sys.argv[1:]
    now = int(time.time())
    if not force:
        hit = load_cached_manifest()
        if hit and "entries" in hit and now - int(hit.get("fetchedAt", 0)) < TTL:
            print(json.dumps(hit, separators=(",", ":")))
            return

    os.makedirs(CACHE_DIR, exist_ok=True)
    if not _sec.is_allowed_url(SOURCE):
        fail("source URL not allowed")
    raw = _sec.http_get(SOURCE, _sec.BYTE_LIMIT_RAW_JS)
    if len(raw) > _sec.BYTE_LIMIT_RAW_JS:
        fail("index exceeds byte ceiling")
    try:
        rawtext = raw.decode("utf-8", "replace")
        if len(rawtext) > _sec.MAX_UTF8_WALLPAPERS_JS:
            fail("index decoded size exceeds ceiling")
    except Exception as ex:
        fail("decode failed: %s" % ex)

    base = ""
    marker = 'window.WALLPAPERS_BASE_URL = "'
    m = rawtext.find(marker)
    if m != -1:
        start = m + len(marker)
        end = rawtext.index('"', start)
        base = rawtext[start:end].rstrip("/")
    if not _sec.is_allowed_url(base):
        fail("base URL missing or not on allowlist")

    try:
        start = rawtext.index("window.WALLPAPERS = ")
        start = rawtext.index("{", start)
        end = rawtext.rindex("}")
        data = json.loads(rawtext[start:end + 1])
    except Exception as ex:
        fail("could not parse wallpapers.js: %s" % ex)
    if not isinstance(data, dict) or len(data) > _sec.MAX_ENTRIES:
        fail("wallpapers map too large or unexpected shape")

    entries = []
    for path, e in data.items():
        if not isinstance(path, str) or not _sec.safe_relpath(path):
            continue  # skip malformed keys instead of failing the whole index
        if not isinstance(e, dict):
            continue
        themes = {}
        for v in VARIANTS:
            t = (e.get("themes") or {}).get(v)
            if not isinstance(t, dict):
                continue
            c = t.get("colors") or {}
            if not isinstance(c, dict):
                c = {}
            themes[v] = {
                "n": t.get("name", "") or "",
                "ct": t.get("colors_toml", "") or "",
                "bg": t.get("background", "") or "",
                "c": [c.get(k, "") or "" for k in ANSI],
            }
        entries.append({
            "p": path,
            "t": e.get("title", "") or path.rsplit("/", 1)[-1],
            "tone": e.get("tone", "") or "",
            "color": e.get("color", "") or "",
            "tags": e.get("tags", []) or [],
            "w": int(e.get("width", 0) or 0),
            "h": int(e.get("height", 0) or 0),
            "thumb": e.get("thumb_path", "") or "",
            "med": e.get("medium_path", "") or path,
            "pal": e.get("colors", []) or [],
            "th": themes,
        })

    out = {"base": base, "fetchedAt": now, "count": len(entries),
           "entries": entries}
    try:
        _sec.validate_slim_manifest(out)
    except ValueError as ex:
        fail("manifest validation failed: %s" % ex)

    payload = json.dumps(out, separators=(",", ":"))
    if len(payload.encode("utf-8")) > _sec.BYTE_LIMIT_MANIFEST:
        fail("slim manifest exceeds byte ceiling")

    fd, tmp = tempfile.mkstemp(dir=CACHE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(payload)
        os.replace(tmp, MANIFEST)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print(payload)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as ex:
        fail(ex)