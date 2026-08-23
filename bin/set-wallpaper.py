#!/usr/bin/env python3
"""Set wallpaper only (no theme) for gotar.omarchy-themes.

Downloads the wallpaper image and calls `omarchy-theme-bg-set` to set it
as the current background without changing the theme colors.

Usage: set-wallpaper.py <base-url> <wallpaper-rel>
Example: set-wallpaper.py https://wallpapers.hel1.your-objectstorage.com dark/green/6000x4000_...jpg

Downloads to ~/.cache/gotar.omarchy-themes/wallpapers/<basename> and
then runs `omarchy-theme-bg-set <path>`. The cache avoids re-downloading.

Exit: 0 on success (prints {"ok":true,"path":...}), 1 on failure.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sec

MIN_CACHED_BYTES = 1024  # keep small/invalid cache entries from being reused


def fail(msg):
    _sec.fail_apply(msg)


def main():
    if len(sys.argv) != 3:
        fail("usage: set-wallpaper.py <base-url> <wallpaper-rel>")
    base = sys.argv[1].rstrip("/")
    rel = sys.argv[2].lstrip("/")
    if not rel:
        fail("empty wallpaper path")
    if not _sec.is_allowed_url(base):
        fail("base URL not on allowlist")
    if not _sec.safe_relpath(rel):
        fail("unsafe wallpaper path: %r" % (rel,))
    url = base + "/" + rel
    cache_dir = os.path.expanduser("~/.cache/gotar.omarchy-themes/wallpapers")
    os.makedirs(cache_dir, exist_ok=True)
    name = os.path.basename(rel)
    dest = os.path.join(cache_dir, name)

    # Reuse the cache only if the entry exists and passes the image sniff;
    # anything invalid is re-downloaded (and then re-validated).
    need_dl = True
    try:
        if os.path.isfile(dest):
            cached = _sec.read_file_capped(dest, _sec.BYTE_LIMIT_MEDIA)
            if len(cached) > MIN_CACHED_BYTES:
                _sec.sniff_image(cached, "cached wallpaper")
                need_dl = False
    except (OSError, ValueError):
        need_dl = True

    if need_dl:
        try:
            data = _sec.http_get(url, _sec.BYTE_LIMIT_MEDIA)
            _sec.sniff_image(data, "wallpaper")
            fd, tmp = tempfile.mkstemp(dir=cache_dir)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
        except Exception as e:
            fail(str(e))

    # Set as background via omarchy helper
    try:
        res = subprocess.run(["omarchy-theme-bg-set", dest], capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            # Fallback: direct symlink + shell IPC (like omarchy-theme-bg-set does)
            link = os.path.expanduser("~/.local/state/omarchy/current/background")
            os.makedirs(os.path.dirname(link), exist_ok=True)
            try:
                if os.path.islink(link) or os.path.exists(link):
                    os.unlink(link)
                os.symlink(dest, link)
            except Exception:
                pass
            # Notify shell (best effort, don't fail if shell not running)
            try:
                subprocess.run(["omarchy-shell", "-q", "background", "set", dest], timeout=5)
            except Exception:
                pass
    except FileNotFoundError:
        fail("omarchy-theme-bg-set not found")
    except Exception as e:
        fail(str(e))

    print(json.dumps({"ok": True, "path": dest}))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as ex:
        fail(ex)