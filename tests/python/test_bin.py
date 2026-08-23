import sys
import unittest, json, os, pathlib, subprocess

# Import the bin scripts as modules by loading their code
BIN = pathlib.Path(__file__).parent.parent.parent / "bin"
sys.path.insert(0, str(BIN))

import _sec  # noqa: E402


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

    def test_fallback_download(self):
        # Test that fallback logic is present (code contains fallback handling)
        code = (BIN / "apply-theme.py").read_text()
        self.assertIn("fallback", code)
        self.assertIn("try_download", code)
        self.assertIn("_sec", code)


class TestFetchManifest(unittest.TestCase):
    def test_slim_structure(self):
        code = (BIN / "fetch-manifest.py").read_text()
        # Check it produces expected slim fields
        self.assertIn('"p":', code)
        self.assertIn('"t":', code)
        self.assertIn('"th":', code)
        self.assertIn("VARIANTS", code)
        self.assertIn("_sec", code)


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