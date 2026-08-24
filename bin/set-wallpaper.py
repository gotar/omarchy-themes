#!/usr/bin/env python3
"""Set wallpaper only (no theme) for gotar.omarchy-themes.

Downloads the wallpaper image and calls `omarchy-theme-bg-set` to set it
as the current background without changing the theme colors.

Usage: set-wallpaper.py <base-url> <wallpaper-rel>
Example: set-wallpaper.py https://wallpapers.hel1.your-objectstorage.com dark/green/6000x4000_...jpg

Downloads to ~/.cache/gotar.omarchy-themes/wallpapers/<wallpaper-rel> (path
mirrored, so dark/a.jpg and light/a.jpg cannot collide) and
then runs `omarchy-theme-bg-set <path>`. The cache avoids re-downloading.

Exit: 0 on success (prints {"ok":true,"path":...}), 1 on failure.
"""
import json
import os
import secrets
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sec

MIN_CACHED_BYTES = 1024  # keep small/invalid cache entries from being reused
MAX_CACHE_FILES = 300
MAX_CACHE_BYTES = 1 << 30  # ~1 GiB total cap on the downloaded-wallpaper cache


def fail(msg):
    _sec.fail_apply(msg)


def enforce_cache_limit(cache_dir, max_bytes=MAX_CACHE_BYTES, max_files=MAX_CACHE_FILES,
                        protected=()):
    """Prune the oldest cached wallpapers until under the size/file limits.

    `protected` is an iterable of paths (e.g. the currently-linked background)
    that must never be deleted. Returns the number of files removed.
    """
    protected = {os.path.realpath(p) for p in protected if p}
    files = []
    for root, _dirs, names in os.walk(cache_dir):
        for n in names:
            full = os.path.join(root, n)
            try:
                if os.path.islink(full) or not os.path.isfile(full):
                    continue
                st = os.stat(full)
                files.append((st.st_mtime, st.st_size, full))
            except OSError:
                continue
    total = sum(s for _, s, _ in files)
    count = len(files)
    removed = 0
    # Remove oldest unprotected files first. Protected files remain counted so
    # limits are never accidentally considered satisfied merely because a
    # protected entry was popped from an in-memory work list.
    for _mtime, size, full in sorted(files, key=lambda x: x[0]):
        if count <= max_files and total <= max_bytes:
            break
        if os.path.realpath(full) in protected:
            continue
        try:
            os.unlink(full)
            total -= size
            count -= 1
            removed += 1
        except OSError:
            pass
    return removed


def write_cache_file(cache_dir, parts, data):
    """Atomically write through retained no-follow directory descriptors."""
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0) \
        | getattr(os, "O_CLOEXEC", 0)
    dir_fd = os.open(cache_dir, flags)
    tmp_name = ""
    try:
        for comp in parts[:-1]:
            next_fd = os.open(comp, flags, dir_fd=dir_fd)
            os.close(dir_fd)
            dir_fd = next_fd
        tmp_name = ".download-%d-%s" % (os.getpid(), secrets.token_hex(8))
        file_fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                          0o600, dir_fd=dir_fd)
        try:
            with os.fdopen(file_fd, "wb") as f:
                f.write(data)
        except Exception:
            try:
                os.close(file_fd)
            except OSError:
                pass
            raise
        os.replace(tmp_name, parts[-1], src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        tmp_name = ""
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name, dir_fd=dir_fd)
            except OSError:
                pass
        os.close(dir_fd)


def set_background(dest):
    """Activate `dest` as the background. Returns (ok, error) with a real result.

    Primary path is the `omarchy-theme-bg-set` helper. If it fails, create the
    current-background symlink ourselves (the shell's background plugin reads
    this link) and only report success once the link is verified to point at
    `dest`. The `omarchy-shell -q background set` IPC is best-effort because
    quiet mode always exits 0 even when the shell is not running.
    """
    if not os.path.isfile(dest):
        return False, "wallpaper file does not exist: %s" % dest
    bg_err = ""
    link = os.path.expanduser("~/.local/state/omarchy/current/background")
    try:
        res = subprocess.run(["omarchy-theme-bg-set", dest],
                             capture_output=True, text=True, timeout=30)
        # The helper currently has no `set -e`; its final quiet IPC can return
        # 0 even if the preceding `ln` failed. Verify the actual source of
        # truth instead of trusting only its exit code.
        if res.returncode == 0 and os.path.isfile(dest) and os.path.islink(link) \
                and os.path.realpath(link) == os.path.realpath(dest):
            return True, ""
        bg_err = (res.stderr or res.stdout or "").strip() or "helper did not set background link"
    except FileNotFoundError:
        bg_err = "omarchy-theme-bg-set not found"
    except Exception as e:
        bg_err = str(e)

    tmp_link = "%s.tmp.%d" % (link, os.getpid())
    try:
        os.makedirs(os.path.dirname(link), exist_ok=True)
        try:
            os.unlink(tmp_link)
        except OSError:
            pass
        os.symlink(dest, tmp_link)
        os.replace(tmp_link, link)
        if not os.path.isfile(dest) or not os.path.islink(link) \
                or os.path.realpath(link) != os.path.realpath(dest):
            raise OSError("background symlink does not point at a wallpaper file")
    except Exception as e:
        bg_err = (bg_err + "; " if bg_err else "") + "fallback symlink failed: %s" % e
        return False, bg_err
    finally:
        try:
            os.unlink(tmp_link)
        except OSError:
            pass

    # Notify the shell (best effort; the shell may not be running).
    try:
        subprocess.run(["omarchy-shell", "-q", "background", "set", dest], timeout=5)
    except Exception:
        pass
    return True, ""


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
    # Mirror the relative path tree: safe_relpath already guarantees no '..'
    # components, and keying by basename alone would let dark/a.jpg and
    # light/a.jpg collide. Refuse cache-directory symlinks before any write.
    parts = rel.split("/")
    try:
        if os.path.islink(cache_dir):
            fail("wallpaper cache root must not be a symlink")
        _sec.ensure_not_symlink(cache_dir, parts[:-1])
    except ValueError as ex:
        fail(str(ex))
    dest = os.path.join(cache_dir, *parts)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        _sec.ensure_not_symlink(cache_dir, parts[:-1])
    except ValueError as ex:
        fail(str(ex))
    if os.path.islink(dest):
        fail("wallpaper cache entry must not be a symlink: %r" % dest)
    # Opportunistic cleanup of the old flat-cache layout (basename only)
    # that would have let dark/a.jpg and light/a.jpg collide.
    flat_old = os.path.join(cache_dir, os.path.basename(rel))
    if flat_old != dest and os.path.isfile(flat_old):
        try:
            # Only remove if it looks like the old flat file, not a
            # legitimate top-level entry (rel with no slash).
            if "/" in rel:
                os.unlink(flat_old)
        except OSError:
            pass

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
            write_cache_file(cache_dir, parts, data)
        except Exception as e:
            fail(str(e))

    # Mark this access for LRU and prune without ever deleting either the
    # currently-linked image or the image we are about to activate.
    try:
        os.utime(dest, None)
    except OSError:
        pass
    link_now = os.path.expanduser("~/.local/state/omarchy/current/background")
    protected = [dest]
    try:
        protected.append(os.readlink(link_now))
    except OSError:
        pass
    enforce_cache_limit(cache_dir, protected=protected)

    ok, err = set_background(dest)
    if not ok:
        fail("could not activate wallpaper: %s" % err)

    print(json.dumps({"ok": True, "path": dest}))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as ex:
        fail(ex)