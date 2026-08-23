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
import sys
import subprocess
import tempfile
import urllib.request
import urllib.error

UA = {"User-Agent": "omarchy-themes-plugin/1.0 (+omarchy shell)"}
TIMEOUT = 180


def fail(msg):
    print(json.dumps({"ok": False, "error": str(msg)}))
    sys.exit(1)


def main():
    if len(sys.argv) != 3:
        fail("usage: set-wallpaper.py <base-url> <wallpaper-rel>")
    base = sys.argv[1].rstrip("/")
    rel = sys.argv[2].lstrip("/")
    if not rel:
        fail("empty wallpaper path")
    url = base + "/" + rel
    cache_dir = os.path.expanduser("~/.cache/gotar.omarchy-themes/wallpapers")
    os.makedirs(cache_dir, exist_ok=True)
    name = os.path.basename(rel)
    dest = os.path.join(cache_dir, name)

    # Download if not cached or if size mismatch? Simple: download if not exists
    need_dl = True
    if os.path.isfile(dest) and os.path.getsize(dest) > 1024:
        need_dl = False
    if need_dl:
        try:
            req = urllib.request.Request(url, headers=UA)
            data = urllib.request.urlopen(req, timeout=TIMEOUT).read()
            fd, tmp = tempfile.mkstemp(dir=cache_dir)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
        except urllib.error.HTTPError as e:
            fail(f"HTTP {e.code}: {e.reason} for {url}")
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
