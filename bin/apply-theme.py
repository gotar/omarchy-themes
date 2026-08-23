#!/usr/bin/env python3
"""Install one omarchy-themes variant as a user theme.

Downloads colors.toml + the background image from the collection's media
host and writes:
  ~/.config/omarchy/themes/<slug>/colors.toml
  ~/.config/omarchy/themes/<slug>/backgrounds/<background-file>

Same layout Aether installs (the slug becomes a normal user theme, so
`omarchy theme set <slug>` activates it). Re-applying is idempotent:
existing files are overwritten.

Background handling: the manifest's `background` path (omarchy-themes/…)
is often private (403) on the public bucket. We try it first and fall
back to the original wallpaper path `p` (dark/…/file.jpg) which is always
public. If both fail we still install the colors.

Usage: apply-theme.py <slug> <base-url> <colors-toml-rel> <background-rel> [fallback-wallpaper-rel]
Exit: 0 success (prints {"ok":true,…}), 1 failure (prints {"ok":false,…}).
"""
import json
import os
import sys
import tempfile
import urllib.request
import urllib.error

UA = {"User-Agent": "omarchy-themes-plugin/1.0 (+omarchy shell)"}
TIMEOUT = 180


def fail(msg):
    print(json.dumps({"ok": False, "error": str(msg)}))
    sys.exit(1)


def try_download(url, dest_dir, name):
    try:
        req = urllib.request.Request(url, headers=UA)
        data = urllib.request.urlopen(req, timeout=TIMEOUT).read()
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return False, str(e)
    try:
        fd, tmp = tempfile.mkstemp(dir=dest_dir)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, os.path.join(dest_dir, name))
    except Exception as e:
        return False, str(e)
    return True, ""


def main():
    if len(sys.argv) not in (5, 6):
        fail("usage: apply-theme.py <slug> <base-url> <colors-toml-rel> <background-rel> [fallback-wallpaper-rel]")
    slug = sys.argv[1]
    base = sys.argv[2].rstrip("/")
    ct = sys.argv[3] if len(sys.argv) >= 4 else ""
    bg = sys.argv[4] if len(sys.argv) >= 5 else ""
    fallback = sys.argv[5] if len(sys.argv) >= 6 else ""
    if not slug or "/" in slug or slug.startswith(".") or ".." in slug:
        fail(f"bad slug: {slug!r}")
    themes_root = os.path.expanduser("~/.config/omarchy/themes")
    dest = os.path.join(themes_root, slug)
    if os.path.realpath(os.path.dirname(dest)) != os.path.realpath(themes_root):
        fail("unsafe theme path")
    os.makedirs(os.path.join(dest, "backgrounds"), exist_ok=True)

    # colors.toml — required
    if ct:
        ok, err = try_download(base + "/" + ct.lstrip("/"), dest, "colors.toml")
        if not ok:
            fail(f"colors.toml download failed: {err}")

    # background — try bg, then fallback (original wallpaper p)
    bg_ok = False
    bg_err = ""
    if bg:
        ok, err = try_download(base + "/" + bg.lstrip("/"), os.path.join(dest, "backgrounds"), os.path.basename(bg))
        bg_ok = ok
        bg_err = err
    if not bg_ok and fallback:
        ok2, err2 = try_download(base + "/" + fallback.lstrip("/"), os.path.join(dest, "backgrounds"), os.path.basename(fallback))
        if ok2:
            bg_ok = True
            bg_err = ""
        elif not bg_ok:
            bg_err = f"{bg_err}; fallback {err2}" if bg_err else err2

    result = {"ok": True, "slug": slug, "path": dest}
    if not bg_ok and (bg or fallback):
        result["warning"] = f"background download failed: {bg_err}"
        result["background_ok"] = False
    else:
        result["background_ok"] = True
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as ex:
        fail(ex)
