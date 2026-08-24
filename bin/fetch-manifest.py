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
import re
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
        # Future timestamp (clock skew) must not pin the cache forever.
        try:
            if int(hit.get("fetchedAt", 0)) > int(time.time()) + 60:
                return None
        except Exception:
            return None
        return hit
    except Exception:
        return None


HEX6 = re.compile(r"#[0-9a-fA-F]{6}")


def _as_str(v):
    """String field: None -> "", non-string or over-long -> ValueError."""
    if v is None:
        return ""
    if not isinstance(v, str):
        raise ValueError("expected string, got %s" % type(v).__name__)
    if len(v) > _sec.MAX_STR:
        raise ValueError("string exceeds %d chars" % _sec.MAX_STR)
    return v


def _as_int(v):
    """Dimension field: None/"" -> 0, non-numeric or negative -> ValueError."""
    if v is None or v == "":
        return 0
    if isinstance(v, bool):
        raise ValueError("bad dimension: %r" % (v,))
    n = int(v)
    if n < 0:
        raise ValueError("negative dimension: %r" % (v,))
    return n


def _as_tags(v):
    """Tags field: None -> [], non-list / too many / non-string tag -> ValueError.

    Enforces MAX_TAGS here so slim_entry() drops a single over-long record
    instead of letting the whole manifest fail validation later.
    """
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > _sec.MAX_TAGS:
        raise ValueError("tags must be a list <= %d" % _sec.MAX_TAGS)
    out = []
    for t in v:
        if not isinstance(t, str) or len(t) > 128:
            raise ValueError("tag must be a short string")
        out.append(t)
    return out


def _as_pal(v):
    """Palette field: None -> [], non-list -> ValueError, bad colors dropped."""
    if v is None:
        return []
    if not isinstance(v, list):
        raise ValueError("palette must be a list")
    return [c for c in v if isinstance(c, str) and HEX6.fullmatch(c)][:_sec.MAX_PAL]


def slim_entry(path, e):
    """Slim one wallpapers.js record; None if the record is malformed.

    The upstream file is third-party and occasionally odd, so malformed
    records and variants are skipped instead of failing the whole index.
    """
    if not isinstance(e, dict):
        return None
    th_all = e.get("themes")
    if not isinstance(th_all, dict):
        th_all = {}
    themes = {}
    for v in VARIANTS:
        t = th_all.get(v)
        if not isinstance(t, dict):
            continue
        c = t.get("colors")
        if not isinstance(c, dict):
            continue
        try:
            n = _as_str(t.get("name"))
            ct = _as_str(t.get("colors_toml"))
            bg = _as_str(t.get("background"))
            colors = [_as_str(c.get(k)) for k in ANSI]
        except ValueError:
            continue  # drop one malformed variant, keep the rest
        # Mirror validate_slim_manifest exactly: a variant is kept only when
        # its name is a safe, non-empty slug; ct/bg are optional ('' is fine).
        if not _sec.safe_slug(n):
            continue  # name would break `omarchy theme set <slug>`
        if ct and not _sec.safe_relpath(ct):
            continue
        if bg and not _sec.safe_relpath(bg):
            continue
        if any(not HEX6.fullmatch(x) for x in colors):
            continue
        themes[v] = {"n": n, "ct": ct, "bg": bg, "c": colors}
    try:
        thumb_raw = _as_str(e.get("thumb_path"))
        if thumb_raw and not _sec.safe_relpath(thumb_raw):
            thumb_raw = ""
        med_raw = _as_str(e.get("medium_path"))
        if med_raw and not _sec.safe_relpath(med_raw):
            med_raw = ""
        w = _as_int(e.get("width"))
        h = _as_int(e.get("height"))
        if w <= 0 or h <= 0:
            raise ValueError("dimensions must be positive")
        return {
            "p": path,
            "t": _as_str(e.get("title")) or path.rsplit("/", 1)[-1],
            "tone": _as_str(e.get("tone")),
            "color": _as_str(e.get("color")),
            "tags": _as_tags(e.get("tags")),
            "w": w,
            "h": h,
            "thumb": thumb_raw,
            "med": med_raw or path,
            "pal": _as_pal(e.get("colors")),
            "th": themes,
        }
    except ValueError:
        return None


def main():
    force = "--force" in sys.argv[1:]
    now = int(time.time())
    stale = None
    if not force:
        hit = load_cached_manifest()
        if hit and "entries" in hit:
            try:
                fetched = int(hit.get("fetchedAt", 0))
            except Exception:
                fetched = 0
            if fetched <= now and now - fetched < TTL:
                print(json.dumps(hit, separators=(",", ":")))
                return
            # Valid but expired: keep it as a stale fallback for offline runs.
            stale = hit

    os.makedirs(CACHE_DIR, exist_ok=True)
    if not _sec.is_allowed_url(SOURCE):
        fail("source URL not allowed")

    try:
        raw = _sec.http_get(SOURCE, _sec.BYTE_LIMIT_RAW_JS)  # raises past the cap
        # "replace" decoding cannot grow past the raw byte cap, so no extra cap.
        rawtext = raw.decode("utf-8", "replace")

        base = ""
        marker = 'window.WALLPAPERS_BASE_URL = "'
        m = rawtext.find(marker)
        if m != -1:
            start = m + len(marker)
            end = rawtext.index('"', start)
            base = rawtext[start:end].rstrip("/")
        if not _sec.is_allowed_url(base):
            raise ValueError("base URL missing or not on allowlist")

        start = rawtext.index("window.WALLPAPERS = ")
        start = rawtext.index("{", start)
        end = rawtext.rindex("}")
        data = json.loads(rawtext[start:end + 1])
        if not isinstance(data, dict) or len(data) > _sec.MAX_ENTRIES:
            raise ValueError("wallpapers map too large or unexpected shape")

        entries = []
        for path, e in data.items():
            if not isinstance(path, str) or not _sec.safe_relpath(path):
                continue  # skip malformed keys instead of failing the whole index
            entry = slim_entry(path, e)
            if entry is not None:
                entries.append(entry)

        out = {"base": base, "fetchedAt": now, "count": len(entries),
               "entries": entries}
        _sec.validate_slim_manifest(out)

        payload = json.dumps(out, separators=(",", ":"))
        if len(payload.encode("utf-8")) > _sec.BYTE_LIMIT_MANIFEST:
            raise ValueError("slim manifest exceeds byte ceiling")
    except Exception as ex:
        if stale is not None:
            # A valid (if expired) local index beats a dead gallery.
            print(json.dumps(stale, separators=(",", ":")))
            return
        fail("could not fetch/slim index: %s" % ex)

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