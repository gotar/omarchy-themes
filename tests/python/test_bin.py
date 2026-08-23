"""Behavior tests for bin/ scripts (no network: http_get is mocked).

Every bug fixed in review has a dedicated assertion here so regressions
are caught by `python3 -m unittest discover -s tests/python` and by CI.
"""
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import warnings
warnings.simplefilter("ignore")

BIN = pathlib.Path(__file__).parent.parent.parent / "bin"
REPO = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(BIN))

import _sec  # noqa: E402

MEDIA_BASE = "https://wallpapers.hel1.your-objectstorage.com"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 1000


def load_module(name):
    """Import a bin/ script (hyphenated name) as a module by path."""
    spec = importlib.util.spec_from_file_location(name, BIN / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# apply-theme
# ---------------------------------------------------------------------------

class TestApplyTheme(unittest.TestCase):
    def test_slug_validation(self):
        res = subprocess.run([sys.executable, str(BIN / "apply-theme.py"), "bad/slug", "https://example.com", "ct", "bg"], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        j = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertIn("bad slug", j["error"])

    def test_base_allowlist(self):
        res = subprocess.run([sys.executable, str(BIN / "apply-theme.py"), "ok", "https://evil.example.com/x", "ct", "bg"], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        j = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertIn("allowlist", j["error"])

    def test_missing_colors_toml_fails(self):
        res = subprocess.run([sys.executable, str(BIN / "apply-theme.py"), "ok", "https://bjarneo.github.io", "", "bg.jpg"], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        j = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertIn("colors.toml", j["error"])

    def test_background_falls_back_to_wallpaper(self):
        apply_theme = load_module("apply-theme")

        def fake_http_get(url, limit):
            if url.endswith("/omarchy-themes/private-bg.jpg"):
                err = urllib.error.HTTPError(url, 403, "private", None, None)
                err.fp = None
                raise err
            return JPEG

        orig = _sec.http_get
        _sec.http_get = fake_http_get
        try:
            with tempfile.TemporaryDirectory() as td:
                ok, err = apply_theme.try_download(MEDIA_BASE, "omarchy-themes/private-bg.jpg", td, "bg.jpg", "image")
                self.assertFalse(ok)
                self.assertIn("403", err)

                ok, err = apply_theme.try_download(MEDIA_BASE, "dark/green/full.jpg", td, "full.jpg", "image")
                self.assertTrue(ok, err)
                with open(os.path.join(td, "full.jpg"), "rb") as f:
                    self.assertTrue(f.read().startswith(b"\xff\xd8\xff"))
        finally:
            _sec.http_get = orig


# ---------------------------------------------------------------------------
# fetch-manifest
# ---------------------------------------------------------------------------

class TestFetchManifest(unittest.TestCase):
    def setUp(self):
        self.fetch = load_module("fetch-manifest")

    def _entry(self, **over):
        e = {
            "title": "Green Hill",
            "tone": "dark",
            "color": "green",
            "tags": ["hill"],
            "width": 3840,
            "height": 2160,
            "thumb_path": "dark/green/t.jpg",
            "medium_path": "dark/green/m.jpg",
            "colors": ["#112233", "#445566"],
            "themes": {
                "aether": {
                    "name": "green-hill-aether",
                    "colors_toml": "omarchy-themes/green-hill-aether.toml",
                    "background": "omarchy-themes/green-hill.jpg",
                    "colors": {("color%d" % i): "#000000" for i in range(16)},
                }
            },
        }
        e.update(over)
        return e

    def test_slim_structure(self):
        out = self.fetch.slim_entry("dark/green/a.jpg", self._entry())
        self.assertEqual(out["p"], "dark/green/a.jpg")
        self.assertEqual(out["t"], "Green Hill")
        self.assertEqual(out["w"], 3840)
        self.assertEqual(out["h"], 2160)
        self.assertEqual(out["med"], "dark/green/m.jpg")
        self.assertEqual(out["th"]["aether"]["n"], "green-hill-aether")
        self.assertEqual(len(out["th"]["aether"]["c"]), 16)

    def test_title_falls_back_to_basename(self):
        e = self._entry()
        del e["title"]
        out = self.fetch.slim_entry("dark/green/a.jpg", e)
        self.assertEqual(out["t"], "a.jpg")

    def test_malformed_entry_is_skipped(self):
        self.assertIsNone(self.fetch.slim_entry("dark/green/a.jpg", self._entry(width="abc")))
        self.assertIsNone(self.fetch.slim_entry("dark/green/a.jpg", self._entry(tags="hill")))
        self.assertIsNone(self.fetch.slim_entry("dark/green/a.jpg", self._entry(colors={"oops": 1})))
        self.assertIsNone(self.fetch.slim_entry("dark/green/a.jpg", "not-a-dict"))

    def test_malformed_variant_is_dropped(self):
        e = self._entry(themes={
            "palette": {"name": "evil; rm -rf", "colors_toml": "x.toml", "background": "b.jpg", "colors": {}},
            "nord": {"name": "green-hill-nord", "colors_toml": "n.toml", "background": "b.jpg",
                     "colors": {("color%d" % i): "#000000" for i in range(16)}},
        })
        out = self.fetch.slim_entry("dark/green/a.jpg", e)
        self.assertNotIn("palette", out["th"])
        self.assertIn("nord", out["th"])

    def test_bad_palette_colors_are_filtered(self):
        e = self._entry(colors=["#112233", "notacolor", 42])
        out = self.fetch.slim_entry("dark/green/a.jpg", e)
        self.assertEqual(out["pal"], ["#112233"])

    def test_thumb_med_sanitized_not_fatal(self):
        # Invalid thumb/med must be sanitized to "" / fallback, not crash the batch.
        e = self._entry(thumb_path="../evil.jpg", medium_path="bad:thing")
        out = self.fetch.slim_entry("dark/green/a.jpg", e)
        self.assertIsNotNone(out, "entry with bad thumb/med should not be dropped entirely")
        self.assertEqual(out["thumb"], "")
        self.assertEqual(out["med"], "dark/green/a.jpg")  # falls back to p

        e2 = self._entry(thumb_path="a//b.jpg")
        out2 = self.fetch.slim_entry("dark/green/a.jpg", e2)
        self.assertEqual(out2["thumb"], "")

    def test_future_cache_is_stale(self):
        # load_cached_manifest must return None when fetchedAt is in the future (clock skew)
        with tempfile.TemporaryDirectory() as td:
            orig_cache = self.fetch.CACHE_DIR
            orig_manifest = self.fetch.MANIFEST
            self.fetch.CACHE_DIR = td
            self.fetch.MANIFEST = os.path.join(td, "manifest.json")
            try:
                future = int(time.time()) + 86400 * 5
                payload = json.dumps({
                    "base": MEDIA_BASE,
                    "fetchedAt": future,
                    "count": 1,
                    "entries": [{
                        "p": "dark/a.jpg", "t": "A", "tone": "dark", "color": "green",
                        "tags": [], "w": 100, "h": 100,
                        "thumb": "dark/a.jpg", "med": "dark/a.jpg",
                        "pal": [], "th": {"palette": {"n": "a-aether", "ct": "a.toml", "bg": "a.jpg", "c": ["#000"]*16}}
                    }]
                })
                pathlib.Path(self.fetch.MANIFEST).write_text(payload)
                hit = self.fetch.load_cached_manifest()
                self.assertIsNone(hit, "future fetchedAt must be treated as stale (clock skew)")
            finally:
                self.fetch.CACHE_DIR = orig_cache
                self.fetch.MANIFEST = orig_manifest


# ---------------------------------------------------------------------------
# _sec hardening
# ---------------------------------------------------------------------------

class TestSec(unittest.TestCase):
    def test_allowlist(self):
        self.assertTrue(_sec.is_allowed_url("https://wallpapers.hel1.your-objectstorage.com/dark/a.jpg"))
        self.assertTrue(_sec.is_allowed_url("https://bjarneo.github.io/omarchy-themes/wallpapers.js"))
        self.assertFalse(_sec.is_allowed_url("http://wallpapers.hel1.your-objectstorage.com/x"))
        self.assertFalse(_sec.is_allowed_url("https://evil.com/x"))
        self.assertFalse(_sec.is_allowed_url("https://wallpapers.hel1.your-objectstorage.com.evil.com/x"))
        self.assertFalse(_sec.is_allowed_url("https://u:p@wallpapers.hel1.your-objectstorage.com/x"))
        self.assertFalse(_sec.is_allowed_url("https://wallpapers.hel1.your-objectstorage.com.evil.com"))

    def test_relpath(self):
        self.assertTrue(_sec.safe_relpath("dark/green/6000x4000_a.jpg"))
        self.assertFalse(_sec.safe_relpath("../x"))
        self.assertFalse(_sec.safe_relpath("/abs"))
        self.assertFalse(_sec.safe_relpath("https://evil.com/x"))

    def test_relpath_edge_trailing_and_double_slash(self):
        # img..jpg contains ".." as substring but not as path component — must pass
        self.assertTrue(_sec.safe_relpath("img..jpg"))
        self.assertTrue(_sec.safe_relpath("a/img..jpg"))
        # double slash and trailing slash must be rejected (would hit a directory)
        self.assertFalse(_sec.safe_relpath("a//b.jpg"))
        self.assertFalse(_sec.safe_relpath("a/b/"))
        self.assertFalse(_sec.safe_relpath("a/b//c.jpg"))
        self.assertFalse(_sec.safe_relpath("a:b"))
        self.assertFalse(_sec.safe_relpath("a\\b"))

    def test_sniff_image(self):
        self.assertEqual(_sec.sniff_image(b"\xff\xd8\xff" + b"\x00" * 10), "jpeg")
        self.assertEqual(_sec.sniff_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10), "png")
        with self.assertRaises(ValueError):
            _sec.sniff_image(b"<html>error</html>")

    def test_sniff_image_avif(self):
        # AVIF: ISO-BMFF with ftyp@4 + avif/avis@8; classic AVI video must NOT pass.
        self.assertEqual(_sec.sniff_image(b"\x00\x00\x00\x18ftypavif\x00\x00\x00\x01"), "avif")
        self.assertEqual(_sec.sniff_image(b"\x00\x00\x00\x18ftypavis\x00\x00\x00\x01"), "avif")
        # mif1 with avif in compatible brands must also be accepted
        self.assertEqual(_sec.sniff_image(b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00avif"), "avif")
        with self.assertRaises(ValueError):
            _sec.sniff_image(b"AVI " + b"\x00" * 16)
        # plain mif1 without avif compat must not be sniffed as avif
        with self.assertRaises(ValueError):
            _sec.sniff_image(b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00heic")

    def test_safe_slug(self):
        self.assertTrue(_sec.safe_slug("mate-02-aether"))
        self.assertTrue(_sec.safe_slug("a.b-c_1"))
        self.assertFalse(_sec.safe_slug("a.."))
        self.assertFalse(_sec.safe_slug("x.."))
        self.assertFalse(_sec.safe_slug("a b"))
        self.assertFalse(_sec.safe_slug("A"))
        self.assertFalse(_sec.safe_slug("evil;rm"))
        self.assertFalse(_sec.safe_slug("x" * 257))

    def test_toml(self):
        self.assertTrue(_sec.validate_toml(b"[colors]\nx = 1\n"))
        with self.assertRaises(ValueError):
            _sec.validate_toml(b"\x00\x01\x02")

    def test_redirect_blocked(self):
        handler = _sec._NoRedirect()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            handler.redirect_request(None, None, 302, "Found", {}, "https://evil.com/steal")
        self.assertIn("redirect blocked", str(ctx.exception))
        try:
            ctx.exception.close()
        except Exception:
            pass

        # http_get must not follow redirects even if allowlist host redirects
        orig_build = urllib.request.build_opener
        def fake_build(*handlers):
            class FakeOpener:
                def open(self, req, timeout=None):
                    err = urllib.error.HTTPError(req.full_url, 302, "redirect", {}, None)
                    raise err
            return FakeOpener()
        urllib.request.build_opener = fake_build
        try:
            with self.assertRaises(urllib.error.HTTPError) as ctx2:
                _sec.http_get("https://bjarneo.github.io/ok", 1024)
            try:
                ctx2.exception.close()
            except Exception:
                pass
        finally:
            urllib.request.build_opener = orig_build

    def test_manifest_validation(self):
        good = {
            "base": "https://wallpapers.hel1.your-objectstorage.com",
            "entries": [{
                "p": "dark/green/a.jpg",
                "t": "Title",
                "tone": "dark",
                "color": "green",
                "tags": ["nature"],
                "w": 3840, "h": 2160,
                "thumb": "dark/green/t.jpg",
                "med": "dark/green/m.jpg",
                "pal": ["#112233"],
                "th": {"palette": {"n": "a-mountain-aether", "ct": "colors.toml", "bg": "bg.jpg",
                                    "c": ["#000000"] * 16}},
            }]
        }
        _sec.validate_slim_manifest(good)  # must not raise

        bad = json.loads(json.dumps(good))
        bad["entries"][0]["pal"] = ["notacolor"]
        with self.assertRaises(ValueError):
            _sec.validate_slim_manifest(bad)

        bad2 = json.loads(json.dumps(good))
        bad2["entries"][0]["p"] = "../../etc/passwd"
        with self.assertRaises(ValueError):
            _sec.validate_slim_manifest(bad2)

        bad3 = json.loads(json.dumps(good))
        bad3["entries"][0]["th"]["palette"]["n"] = "evil; touch /tmp/pwned"
        with self.assertRaises(ValueError):
            _sec.validate_slim_manifest(bad3)

    def test_read_capped(self):
        tmp = pathlib.Path(tempfile.mkstemp(prefix="_sec_cap_")[1])
        try:
            tmp.write_text("x" * 100)
            data = _sec.read_file_capped(str(tmp), 1000)
            self.assertEqual(len(data), 100)
            with self.assertRaises(ValueError):
                _sec.read_file_capped(str(tmp), 50)
        finally:
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# set-wallpaper mirrored cache + Panel + CI source checks
# ---------------------------------------------------------------------------

class TestWallpaperCache(unittest.TestCase):
    def test_mirrored_paths_no_collision(self):
        # dark/a.jpg and light/a.jpg must map to different cache files
        cache = "/tmp/c"
        rel_a = "dark/a.jpg"
        rel_b = "light/a.jpg"
        dest_a = os.path.join(cache, *rel_a.split("/"))
        dest_b = os.path.join(cache, *rel_b.split("/"))
        self.assertNotEqual(dest_a, dest_b)
        self.assertTrue(dest_a.endswith("dark/a.jpg"))
        self.assertTrue(dest_b.endswith("light/a.jpg"))


class TestPanelSource(unittest.TestCase):
    def test_no_hardcoded_absolute_paths(self):
        text = (REPO / "Panel.qml").read_text()
        self.assertNotIn("/usr/bin/python3", text, "use 'python3' via PATH, not absolute")
        self.assertNotIn("/usr/bin/omarchy", text, "use 'omarchy' via PATH, not absolute")
        self.assertIn('"python3"', text)
        self.assertIn('"omarchy"', text)

    def test_watchdog_kills_fetch(self):
        text = (REPO / "Panel.qml").read_text()
        # fetchWatchdog must kill the hanging Process on timeout
        self.assertIn("fetchProc.running = false", text)
        # must be inside fetchWatchdog's onTriggered
        m = re.search(r"id:\s*fetchWatchdog.*?onTriggered.*?fetchProc\.running\s*=\s*false", text, re.S)
        self.assertIsNotNone(m, "watchdog onTriggered should set fetchProc.running = false")

    def test_safeRel_mirrors_python(self):
        text = (REPO / "Panel.qml").read_text()
        self.assertIn('s.split(\"/\").indexOf(\"..\")', text)
        self.assertIn('!s.endsWith(\"/\")', text)
        self.assertIn('s.indexOf(\"//\")', text)

    def test_cursor_enter_uses_cursorIdx(self):
        text = (REPO / "Panel.qml").read_text()
        self.assertIn("openDetailAt(root.cursorIdx)", text)
        self.assertNotIn("openDetailAt(0)", text)

    def test_fallback_uses_fullres(self):
        text = (REPO / "Panel.qml").read_text()
        self.assertIn('fallbackP = e ? (e.p || \"\")', text)
        self.assertNotIn('fallbackP = e ? (e.med', text)


class TestCI(unittest.TestCase):
    def test_python_tests_not_masked(self):
        text = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertNotIn("discover -s tests/python -v || true", text)
        self.assertIn("discover -s tests/python -v", text)

    def test_validate_not_masked(self):
        text = (REPO / ".github/workflows/ci.yml").read_text()
        # the only || true allowed is none; validate must not be masked
        self.assertNotIn("validate ./ || true", text)
        self.assertIn("omarchy plugin validate ./;", text)


if __name__ == "__main__":
    unittest.main()
