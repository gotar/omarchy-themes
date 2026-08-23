"""Behavior tests for bin/ scripts (no network: http_get is mocked)."""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
import urllib.error

BIN = pathlib.Path(__file__).parent.parent.parent / "bin"
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


class TestApplyTheme(unittest.TestCase):
    def test_slug_validation(self):
        # Should fail on bad slug with slash
        res = subprocess.run([sys.executable, str(BIN / "apply-theme.py"), "bad/slug", "https://example.com", "ct", "bg"], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        j = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertIn("bad slug", j["error"])

    def test_base_allowlist(self):
        # Host outside the allowlist must be refused before any download
        res = subprocess.run([sys.executable, str(BIN / "apply-theme.py"), "ok", "https://evil.example.com/x", "ct", "bg"], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        j = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertIn("allowlist", j["error"])

    def test_missing_colors_toml_fails(self):
        # colors.toml is required: empty path must fail, not silently succeed
        res = subprocess.run([sys.executable, str(BIN / "apply-theme.py"), "ok", "https://bjarneo.github.io", "", "bg.jpg"], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        j = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertIn("colors.toml", j["error"])

    def test_background_falls_back_to_wallpaper(self):
        # 403 on the theme background, 200 on the original wallpaper:
        # try_download must fail then succeed and land a valid image on disk.
        apply_theme = load_module("apply-theme")

        def fake_http_get(url, limit):
            if url.endswith("/omarchy-themes/private-bg.jpg"):
                err = urllib.error.HTTPError(url, 403, "private", None, None)
                err.fp = None  # no real response to clean up in the mock
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

    def test_sniff_image(self):
        self.assertEqual(_sec.sniff_image(b"\xff\xd8\xff" + b"\x00" * 10), "jpeg")
        self.assertEqual(_sec.sniff_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10), "png")
        with self.assertRaises(ValueError):
            _sec.sniff_image(b"<html>error</html>")

    def test_sniff_image_avif(self):
        # AVIF: ISO-BMFF with ftyp@4 + avif/avis@8; classic AVI video must NOT pass.
        self.assertEqual(_sec.sniff_image(b"\x00\x00\x00\x18ftypavif\x00\x00\x00\x01"), "avif")
        self.assertEqual(_sec.sniff_image(b"\x00\x00\x00\x18ftypavis\x00\x00\x00\x01"), "avif")
        with self.assertRaises(ValueError):
            _sec.sniff_image(b"AVI " + b"\x00" * 16)

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

        # second color in pal must be #rrggbb
        bad = json.loads(json.dumps(good))
        bad["entries"][0]["pal"] = ["notacolor"]
        with self.assertRaises(ValueError):
            _sec.validate_slim_manifest(bad)

        bad2 = json.loads(json.dumps(good))
        bad2["entries"][0]["p"] = "../../etc/passwd"
        with self.assertRaises(ValueError):
            _sec.validate_slim_manifest(bad2)

        # theme name with shell metacharacters must be rejected
        bad3 = json.loads(json.dumps(good))
        bad3["entries"][0]["th"]["palette"]["n"] = "evil; touch /tmp/pwned"
        with self.assertRaises(ValueError):
            _sec.validate_slim_manifest(bad3)

    def test_read_capped(self):
        import tempfile
        tmp = pathlib.Path(tempfile.mkstemp(prefix="_sec_cap_")[1])
        try:
            tmp.write_text("x" * 100)
            data = _sec.read_file_capped(str(tmp), 1000)
            self.assertEqual(len(data), 100)
            with self.assertRaises(ValueError):
                _sec.read_file_capped(str(tmp), 50)
        finally:
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
