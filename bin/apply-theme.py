#!/usr/bin/env python3
"""Install one omarchy-themes variant as a user theme.

Downloads colors.toml + the background image from the collection's media
host and writes:
  ~/.config/omarchy/themes/<slug>/colors.toml
  ~/.config/omarchy/themes/<slug>/backgrounds/<background-file>

Same layout Aether installs (the slug becomes a normal user theme, so
`omarchy theme set <slug>` activates it). Re-applying is idempotent:
existing files are overwritten.

Usage: apply-theme.py <slug> <base-url> <colors-toml-rel> <background-rel>
Exit: 0 success (prints {"ok":true,...}), 1 failure (prints {"ok":false,...}).
"""
import json
import os
import sys
import tempfile
import urllib.request

UA = {"User-Agent": "omarchy-themes-plugin/1.0 (+omarchy shell)"}


def fail(msg):
    print(json.dumps({"ok": False, "error": str(msg)}))
    sys.exit(1)


def download(url, dest_dir, name):
    req = urllib.request.Request(url, headers=UA)
    data = urllib.request.urlopen(req, timeout=180).read()
    fd, tmp = tempfile.mkstemp(dir=dest_dir)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, os.path.join(dest_dir, name))


def main():
    if len(sys.argv) != 5:
        fail("usage: apply-theme.py <slug> <base-url> <colors-toml-rel> <background-rel>")
    slug, base, ct, bg = sys.argv[1:5]
    if not slug or "/" in slug or slug.startswith(".") or ".." in slug:
        fail("bad slug: %r" % slug)
    base = base.rstrip("/")
    themes_root = os.path.expanduser("~/.config/omarchy/themes")
    dest = os.path.join(themes_root, slug)
    if os.path.realpath(os.path.dirname(dest)) != os.path.realpath(themes_root):
        fail("unsafe theme path")
    os.makedirs(os.path.join(dest, "backgrounds"), exist_ok=True)
    if ct:
        download(base + "/" + ct.lstrip("/"), dest, "colors.toml")
    if bg:
        download(base + "/" + bg.lstrip("/"), os.path.join(dest, "backgrounds"), os.path.basename(bg))
    print(json.dumps({"ok": True, "slug": slug, "path": dest}))


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        fail(ex)
