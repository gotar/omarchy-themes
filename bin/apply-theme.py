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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sec


def fail(msg):
    _sec.fail_apply(msg)


def try_download(base, rel, dest_dir, name, kind):
    """Stream one allowlisted download to disk with caps + validation."""
    if not _sec.is_allowed_url(base):
        return False, "base URL not on allowlist"
    if not _sec.safe_relpath(rel):
        return False, "unsafe relative path: %r" % (rel,)
    url = base.rstrip("/") + "/" + rel
    try:
        if kind == "toml":
            data = _sec.http_get(url, _sec.BYTE_LIMIT_TOML)
            _sec.validate_toml(data)
        elif kind == "image":
            data = _sec.http_get(url, _sec.BYTE_LIMIT_MEDIA)
            _sec.sniff_image(data)
        else:
            return False, "unknown download kind"
    except Exception as e:
        return False, str(e)
    try:
        fd, tmp = tempfile.mkstemp(dir=dest_dir)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, os.path.join(dest_dir, name))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
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
    if not _sec.safe_slug(slug):
        fail("bad slug: %r" % (slug,))
    if not _sec.is_allowed_url(base):
        fail("base URL not on allowlist")
    for rel in (ct, bg, fallback):
        if rel and not _sec.safe_relpath(rel):
            fail("unsafe path: %r" % (rel,))
    if not ct:
        fail("missing colors.toml path (required)")

    themes_root = os.path.expanduser("~/.config/omarchy/themes")
    # Refuse to write through symlinks (a malicious or accidental <slug>
    # symlink must not redirect colors.toml / backgrounds outside the theme dir).
    try:
        if os.path.islink(themes_root):
            fail("themes root must not be a symlink")
        _sec.ensure_not_symlink(themes_root, [slug, "backgrounds"])
    except ValueError as ex:
        fail(str(ex))
    dest = os.path.join(themes_root, slug)
    # slug already passed safe_slug (no '/'), so dest is always directly
    # inside themes_root — there is no path to traverse.
    os.makedirs(os.path.join(dest, "backgrounds"), exist_ok=True)
    for sub in (dest, os.path.join(dest, "backgrounds")):
        if os.path.islink(sub):
            fail("themes dir is a symlink: %r" % (sub,))

    # colors.toml — required
    ok, err = try_download(base, ct, dest, "colors.toml", "toml")
    if not ok:
        fail("colors.toml download failed: %s" % err)

    # background — try bg, then fallback (original wallpaper p)
    bg_ok = False
    bg_err = ""
    if bg:
        ok, err = try_download(base, bg, os.path.join(dest, "backgrounds"),
                               os.path.basename(bg), "image")
        bg_ok = ok
        bg_err = err
    if not bg_ok and fallback:
        ok2, err2 = try_download(base, fallback, os.path.join(dest, "backgrounds"),
                                 os.path.basename(fallback), "image")
        if ok2:
            bg_ok = True
            bg_err = ""
        else:
            bg_err = err2 if not bg_err else "%s; fallback: %s" % (bg_err, err2)

    result = {"ok": True, "slug": slug, "path": dest}
    if not bg_ok and (bg or fallback):
        result["warning"] = "background download failed: %s" % bg_err
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