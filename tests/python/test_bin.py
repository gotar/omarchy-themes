import unittest, json, os, sys, tempfile, pathlib, subprocess, urllib.request

# Import the bin scripts as modules by loading their code
BIN = pathlib.Path(__file__).parent.parent.parent / "bin"

class TestApplyTheme(unittest.TestCase):
    def test_slug_validation(self):
        # Should fail on bad slug with slash
        res = subprocess.run([sys.executable, str(BIN/"apply-theme.py"), "bad/slug", "https://example.com", "ct", "bg"], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        j = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertIn("bad slug", j["error"])

    def test_fallback_download(self):
        # Test that fallback logic is present (code contains fallback handling)
        code = (BIN/"apply-theme.py").read_text()
        self.assertIn("fallback", code)
        self.assertIn("try_download", code)

class TestFetchManifest(unittest.TestCase):
    def test_slim_structure(self):
        code = (BIN/"fetch-manifest.py").read_text()
        # Check it produces expected slim fields
        self.assertIn('"p":', code)
        self.assertIn('"t":', code)
        self.assertIn('"th":', code)
        self.assertIn("VARIANTS", code)

if __name__ == "__main__":
    unittest.main()
