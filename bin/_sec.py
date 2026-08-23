#!/usr/bin/env python3
"""Shared hardening helpers for the omarchy-themes bin scripts.

Addresses marketplace review findings:
  - every download streams with a hard byte ceiling (no unbounded .read())
  - every URL must be https and match a host allowlist (no SSRF / weird hosts)
  - the slim manifest shape is validated (types, lengths, counts) before it
    is cached or printed into the QML StdioCollector
  - image payloads are sniffed by magic bytes before they reach disk / shell
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = {"User-Agent": "omarchy-themes-plugin/1.0 (+omarchy shell)"}

ALLOWED_HOSTS = ("wallpapers.hel1.your-objectstorage.com", "bjarneo.github.io")
ALLOWED_SCHEMES = ("https",)

BYTE_LIMIT_RAW_JS = 64 << 20      # source wallpapers.js is ~35 MB
BYTE_LIMIT_MANIFEST = 32 << 20    # slim manifest json (cache + stdout)
BYTE_LIMIT_MEDIA = 32 << 20       # wallpaper / background images
BYTE_LIMIT_TOML = 1 << 20         # colors.toml

MAX_ENTRIES = 20000
MAX_TAGS = 64
MAX_PAL = 32
MAX_THEMES_VARIANTS = 8
MAX_STR = 1024
MAX_PATH = 512

SAFE_REL_RE = re.compile(r"^[A-Za-z0-9_./+@=~-]+$")
# Theme names double as slugs passed to `omarchy theme set` and later to
# bash -lc by the shared bar: only plain lowercase words/digits/dashes are
# accepted, never shell metacharacters or spaces.
SAFE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def safe_slug(slug):
    """True only for slugs safe to interpolate into a shell command.

    '..' is rejected as a substring (not just as a path component): slugs
    become directory names and later shell arguments, and a dot-dot run is
    never a legitimate theme name.
    """
    return (isinstance(slug, str) and bool(SAFE_SLUG_RE.match(slug))
            and ".." not in slug and len(slug) <= 256)


def fail(msg):
    """Print a plugin-style error payload and exit non-zero (manifest flavor)."""
    print(json.dumps({"error": str(msg)}, separators=(",", ":")))
    sys.exit(1)


def fail_apply(msg):
    """Print an apply flavor error payload and exit non-zero."""
    print(json.dumps({"ok": False, "error": str(msg)}, separators=(",", ":")))
    sys.exit(1)


def is_allowed_url(url):
    """True only for https URLs on the allowlisted media hosts.

    Subdomains of an allowlisted host are intentionally accepted (e.g. a
    future cdn.<media-host>); the suffix match is dot-anchored, so lookalike
    domains such as <media-host>.evil.com are refused.
    """
    if not isinstance(url, str) or not url or len(url) > 2048:
        return False
    try:
        p = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if p.scheme not in ALLOWED_SCHEMES:
        return False
    host = (p.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        return False
    if p.username or p.password:
        return False
    return True


def safe_relpath(rel):
    """True for manifest-relative paths: no .., no scheme, printable ascii."""
    if not isinstance(rel, str) or not rel or len(rel) > MAX_PATH:
        return False
    if rel.startswith(("/", "\\")) or ".." in rel.split("/") or ":" in rel:
        return False
    return bool(SAFE_REL_RE.match(rel))


def http_get(url, max_bytes):
    """Streaming https GET with a hard byte ceiling and host allowlist."""
    if not is_allowed_url(url):
        raise ValueError("URL not on allowlist: %r" % url[:120])
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = 0
        out = bytearray()
        while True:
            chunk = resp.read(min(1 << 16, max_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("download exceeded %d bytes" % max_bytes)
            out += chunk
        return bytes(out)


def read_file_capped(path, max_bytes):
    """Read a local file, refusing anything above the byte ceiling."""
    try:
        size = os.path.getsize(path)
    except OSError:
        raise
    if size > max_bytes:
        raise ValueError("file %r exceeds %d bytes" % (path, max_bytes))
    with open(path, "rb") as f:
        data = f.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("file %r exceeds %d bytes" % (path, max_bytes))
    return data


def sniff_image(data, what="media"):
    """Reject downloads that are not a recognized image container."""
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("%s is not bytes" % what)
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis"):
        return "avif"
    raise ValueError("%s is not a recognized image (magic %r)" % (what, data[:16]))


def validate_toml(data, what="colors.toml"):
    """Light TOML sanity: textual, under the TOML byte ceiling."""
    if not isinstance(data, bytes) or len(data) > BYTE_LIMIT_TOML:
        raise ValueError("%s exceeds %d bytes" % (what, BYTE_LIMIT_TOML))
    if b"\x00" in data[:4096]:
        raise ValueError("%s is binary, expected TOML text" % what)
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("%s is not valid UTF-8" % what)
    return True


def validate_slim_manifest(obj):
    """Validate the slim manifest shape enough that the QML UI can trust it."""
    if not isinstance(obj, dict):
        raise ValueError("manifest must be an object")
    base = obj.get("base")
    if not is_allowed_url(base):
        raise ValueError("manifest base is not an allowed URL")
    entries = obj.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise ValueError("manifest entries must be a list <= %d" % MAX_ENTRIES)
    for e in entries:
        if not isinstance(e, dict):
            raise ValueError("manifest entry must be an object")
        for key in ("p", "t", "tone", "color", "thumb", "med"):
            v = e.get(key) or ""
            if not isinstance(v, str) or len(v) > MAX_STR:
                raise ValueError("entry %r must be a short string" % key)
            if key in ("p", "thumb", "med") and not safe_relpath(v):
                raise ValueError("entry %r is not a safe relative path" % key)
        if not isinstance(e.get("w"), int) or not isinstance(e.get("h"), int):
            raise ValueError("entry w/h must be integers")
        tags = e.get("tags") or []
        if not isinstance(tags, list) or len(tags) > MAX_TAGS:
            raise ValueError("entry tags must be a list <= %d" % MAX_TAGS)
        for t in tags:
            if not isinstance(t, str) or len(t) > 128:
                raise ValueError("tag must be a short string")
        pal = e.get("pal") or []
        if not isinstance(pal, list) or len(pal) > MAX_PAL:
            raise ValueError("entry pal must be a list <= %d" % MAX_PAL)
        for c in pal:
            if not isinstance(c, str) or len(c) > 32 or not re.fullmatch(r"#[0-9a-fA-F]{6}", c):
                raise ValueError("entry pal color must be #rrggbb")
        th = e.get("th") or {}
        if not isinstance(th, dict) or len(th) > MAX_THEMES_VARIANTS:
            raise ValueError("entry th must be a dict <= %d" % MAX_THEMES_VARIANTS)
        for vname, t in th.items():
            if not isinstance(vname, str) or not isinstance(t, dict):
                raise ValueError("theme variant must map to an object")
            for k2 in ("n", "ct", "bg"):
                v2 = t.get(k2) or ""
                if not isinstance(v2, str) or len(v2) > MAX_STR:
                    raise ValueError("theme %r must be a short string" % k2)
                if k2 == "n" and not safe_slug(v2):
                    raise ValueError("theme name is not a safe slug")
                if k2 in ("ct", "bg") and not safe_relpath(v2):
                    raise ValueError("theme %r is not a safe relative path" % k2)
            c = t.get("c") or []
            if not isinstance(c, list) or len(c) != 16:
                raise ValueError("theme c must be a 16-item list")
            for x in c:
                if not isinstance(x, str) or len(x) > 32:
                    raise ValueError("theme color must be a short string")
    return obj