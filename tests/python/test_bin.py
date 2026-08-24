"""Behavior tests for bin/ scripts (no network: http_get is mocked).

Every bug fixed in review has a dedicated assertion here so regressions
are caught by `python3 -m unittest discover -s tests/python` and by CI.
"""
import contextlib
import importlib.util
import io
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
from unittest import mock
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
        # '.', 'a/.', 'a/./b' must be rejected (would hit the cache dir itself)
        self.assertFalse(_sec.safe_relpath("."))
        self.assertFalse(_sec.safe_relpath("a/."))
        self.assertFalse(_sec.safe_relpath("a/./b"))

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
        good = b'foreground = "#ffffff"\nbackground = "#000000"\ncolor0 = "#000000"\n'
        self.assertTrue(_sec.validate_toml(good))
        # Valid TOML but not an Omarchy theme shape.
        with self.assertRaises(ValueError):
            _sec.validate_toml(b"[colors]\nx = 1\n")
        # Non-TOML / HTML / binary payloads must be refused.
        with self.assertRaises(ValueError):
            _sec.validate_toml(b"this is not TOML")
        with self.assertRaises(ValueError):
            _sec.validate_toml(b"<html>error</html>")
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

        # Optional thumb/med and ct/bg may be empty (producer/validator contract).
        opt = json.loads(json.dumps(good))
        opt["entries"][0]["thumb"] = ""
        opt["entries"][0]["med"] = ""
        opt["entries"][0]["th"]["palette"]["ct"] = ""
        opt["entries"][0]["th"]["palette"]["bg"] = ""
        _sec.validate_slim_manifest(opt)

        # Non-hex theme color must be rejected.
        badc = json.loads(json.dumps(good))
        badc["entries"][0]["th"]["palette"]["c"][0] = "notacolor"
        with self.assertRaises(ValueError):
            _sec.validate_slim_manifest(badc)

        # Non-positive / bool dimensions must be rejected.
        badw = json.loads(json.dumps(good))
        badw["entries"][0]["w"] = 0
        with self.assertRaises(ValueError):
            _sec.validate_slim_manifest(badw)
        badbool = json.loads(json.dumps(good))
        badbool["entries"][0]["h"] = True
        with self.assertRaises(ValueError):
            _sec.validate_slim_manifest(badbool)

        # count mismatch must be rejected.
        badcount = json.loads(json.dumps(good))
        badcount["count"] = 99
        with self.assertRaises(ValueError):
            _sec.validate_slim_manifest(badcount)

        # Empty theme name must be rejected.
        badn = json.loads(json.dumps(good))
        badn["entries"][0]["th"]["palette"]["n"] = ""
        with self.assertRaises(ValueError):
            _sec.validate_slim_manifest(badn)

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
        self.assertIn('s.split(\"/\").indexOf(\".\")', text)
        self.assertIn('!s.endsWith(\"/\")', text)
        self.assertIn('s.indexOf(\"//\")', text)

    def test_apply_single_flight(self):
        text = (REPO / "Panel.qml").read_text()
        self.assertIn("readonly property bool operationBusy", text)
        self.assertIn("if (root.operationBusy || root.applyPhase === 1", text)
        self.assertIn("if (root.operationBusy) return", text)

    def test_activation_confirmed(self):
        text = (REPO / "Panel.qml").read_text()
        self.assertIn("function evalActivation()", text)
        self.assertIn("root.activationPending", text)

    def test_debounced_enter_flushes_first(self):
        text = (REPO / "Panel.qml").read_text()
        self.assertIn("qTimer.stop()", text)
        self.assertIn("root.refreshFilters()", text)
        self.assertIn("root.openDetailAt(root.cursorIdx)", text)

    def test_cursor_enter_uses_cursorIdx(self):
        text = (REPO / "Panel.qml").read_text()
        self.assertIn("openDetailAt(root.cursorIdx)", text)
        self.assertNotIn("openDetailAt(0)", text)

    def test_fallback_uses_fullres(self):
        text = (REPO / "Panel.qml").read_text()
        self.assertIn('fallbackP = e ? (e.p || \"\")', text)
        self.assertNotIn('fallbackP = e ? (e.med', text)


class TestCI(unittest.TestCase):
    def test_python_tests_run(self):
        text = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("discover -s tests/python -v", text)

    def test_js_tests_run(self):
        text = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("node --test tests/Model.test.js", text)

    def test_py_compile_runs(self):
        text = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("py_compile", text)

    def test_no_fake_omarchy_steps(self):
        # qmllint / omarchy plugin validate need the local shell and cannot run
        # on a generic GitHub runner; they are local-only (npm run test:qml). CI
        # must not pretend to run them with a --version masquerade or || true.
        text = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertNotIn("qmllint", text)
        self.assertNotIn("plugin validate", text)
        self.assertNotIn(" || true", text)


class TestHttpDeadline(unittest.TestCase):
    def test_total_deadline(self):
        class FakeClock:
            def __init__(self):
                self.n = 0
            def monotonic(self):
                self.n += 1
                return self.n
        class FakeResp:
            def __init__(self, url):
                self.url = url
            def read(self, n):
                return b"x" * 64
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        class FakeOpener:
            def open(self, req, timeout=None):
                return FakeResp(req.full_url)
        orig_time = _sec.time
        orig_build = urllib.request.build_opener
        urllib.request.build_opener = lambda *h: FakeOpener()
        try:
            _sec.time = FakeClock()
            with self.assertRaises(TimeoutError):
                _sec.http_get("https://bjarneo.github.io/x", 1 << 20, total_seconds=2)
        finally:
            _sec.time = orig_time
            urllib.request.build_opener = orig_build


class TestFetchTagsAndContract(unittest.TestCase):
    def setUp(self):
        self.fetch = load_module("fetch-manifest")

    def test_too_many_tags_skips_entry(self):
        e = {"title": "X", "tone": "dark", "color": "red", "width": 1920,
             "height": 1080, "thumb_path": "a/t.jpg", "medium_path": "a/m.jpg",
             "colors": [], "themes": {},
             "tags": ["t%d" % i for i in range(65)]}
        self.assertIsNone(self.fetch.slim_entry("a/x.jpg", e))

    def test_produced_manifest_passes_validator(self):
        e = {"title": "Y", "tone": "dark", "color": "blue", "width": 3840,
             "height": 2160, "thumb_path": "../evil.jpg", "medium_path": "a/m.jpg",
             "colors": ["#112233"],
             "themes": {"aether": {"name": "y-aether",
                                   "colors_toml": "omarchy-themes/y.toml",
                                   "background": "",
                                   "colors": {("color%d" % i): "#000000" for i in range(16)}}}}
        out = self.fetch.slim_entry("a/y.jpg", e)
        self.assertEqual(out["thumb"], "")
        _sec.validate_slim_manifest({"base": MEDIA_BASE, "count": 1, "entries": [out]})


class TestStaleCacheFallback(unittest.TestCase):
    def setUp(self):
        self.fetch = load_module("fetch-manifest")

    def _write_stale(self, td, fetched_at):
        payload = json.dumps({"base": MEDIA_BASE, "fetchedAt": fetched_at, "count": 1,
                              "entries": [{"p": "dark/a.jpg", "t": "A", "tone": "dark",
                                           "color": "green", "tags": [], "w": 100, "h": 100,
                                           "thumb": "dark/a.jpg", "med": "dark/a.jpg", "pal": [],
                                           "th": {"palette": {"n": "a-aether", "ct": "a.toml", "bg": "a.jpg", "c": ["#000000"] * 16}}}]})
        pathlib.Path(self.fetch.MANIFEST).write_text(payload)

    def _patch(self, td, force=False):
        self._oc = self.fetch.CACHE_DIR
        self._om = self.fetch.MANIFEST
        self._og = _sec.http_get
        self._oa = sys.argv
        self.fetch.CACHE_DIR = td
        self.fetch.MANIFEST = os.path.join(td, "manifest.json")
        _sec.http_get = lambda *a, **k: (_ for _ in ()).throw(OSError("network down"))
        sys.argv = ["fetch-manifest.py"] + (["--force"] if force else [])

    def _restore(self):
        self.fetch.CACHE_DIR = self._oc
        self.fetch.MANIFEST = self._om
        _sec.http_get = self._og
        sys.argv = self._oa

    def test_stale_cache_used_on_network_failure(self):
        with tempfile.TemporaryDirectory() as td:
            self._patch(td)
            try:
                self._write_stale(td, int(time.time()) - 86400 * 10)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.fetch.main()
                out = json.loads(buf.getvalue())
                self.assertEqual(out["entries"][0]["t"], "A")
            finally:
                self._restore()

    def test_stale_cache_not_used_on_force(self):
        with tempfile.TemporaryDirectory() as td:
            self._patch(td, force=True)
            try:
                self._write_stale(td, int(time.time()) - 86400 * 10)
                with self.assertRaises(SystemExit):
                    self.fetch.main()
            finally:
                self._restore()

    def test_future_cache_not_used_as_stale(self):
        with tempfile.TemporaryDirectory() as td:
            self._patch(td)
            try:
                self._write_stale(td, int(time.time()) + 86400 * 5)
                with self.assertRaises(SystemExit):
                    self.fetch.main()
            finally:
                self._restore()


class TestSetWallpaperE2E(unittest.TestCase):
    def _run(self, rel, bg_exit, block_link_dir=False):
        fem = load_module("set-wallpaper")
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as bindir:
            helper = os.path.join(bindir, "omarchy-theme-bg-set")
            with open(helper, "w") as f:
                f.write("#!/bin/sh\nexit %d\n" % bg_exit)
            os.chmod(helper, 0o755)
            sh = os.path.join(bindir, "omarchy-shell")
            with open(sh, "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(sh, 0o755)
            link = os.path.join(home, ".local/state/omarchy/current/background")
            if block_link_dir:
                os.makedirs(link, exist_ok=True)
            orig_get = _sec.http_get
            orig_argv = sys.argv
            _sec.http_get = lambda url, limit, **kw: JPEG
            sys.argv = ["set-wallpaper.py", MEDIA_BASE, rel]
            try:
                with mock.patch.dict(os.environ, {"HOME": home,
                                                  "PATH": bindir + os.pathsep + os.environ.get("PATH", "")}):
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        fem.main()
                    return buf.getvalue(), None
            finally:
                _sec.http_get = orig_get
                sys.argv = orig_argv

    def test_primary_helper_success(self):
        out, _ = self._run("dark/a.jpg", 0)
        self.assertIn('"ok": true', out)

    def test_fallback_symlink_success(self):
        out, _ = self._run("dark/b.jpg", 7)
        self.assertIn('"ok": true', out)

    def test_failure_when_all_activation_fails(self):
        with self.assertRaises(SystemExit):
            self._run("dark/c.jpg", 7, block_link_dir=True)


class TestApplySymlinkAndCleanup(unittest.TestCase):
    def test_rejects_symlinked_theme_dir(self):
        apply_theme = load_module("apply-theme")
        with tempfile.TemporaryDirectory() as home:
            themes = os.path.join(home, ".config/omarchy/themes")
            os.makedirs(themes, exist_ok=True)
            outside = os.path.join(home, "outside")
            os.makedirs(outside)
            os.symlink(outside, os.path.join(themes, "victim"))
            orig_get = _sec.http_get
            orig_argv = sys.argv
            _sec.http_get = lambda url, limit, **kw: JPEG
            sys.argv = ["apply-theme.py", "victim", MEDIA_BASE, "a.toml", "b.jpg", "c.jpg"]
            try:
                with mock.patch.dict(os.environ, {"HOME": home}):
                    with self.assertRaises(SystemExit):
                        apply_theme.main()
            finally:
                _sec.http_get = orig_get
                sys.argv = orig_argv
            self.assertFalse(os.path.exists(os.path.join(outside, "colors.toml")))

    def test_no_leftover_temp_on_replace_failure(self):
        apply_theme = load_module("apply-theme")
        orig_replace = os.replace
        orig_get = _sec.http_get
        _sec.http_get = lambda url, limit, **kw: JPEG

        def broken_replace(src, dst):
            raise OSError("replace failed")
        try:
            os.replace = broken_replace
            with tempfile.TemporaryDirectory() as td:
                ok, _err = apply_theme.try_download(MEDIA_BASE, "dark/a.jpg", td, "a.jpg", "image")
                self.assertFalse(ok)
                leftovers = [f for f in os.listdir(td) if f.startswith("tmp")]
                self.assertEqual(leftovers, [], "temp file leaked on replace failure")
        finally:
            os.replace = orig_replace
            _sec.http_get = orig_get


class TestCacheLimit(unittest.TestCase):
    def test_prunes_oldest_keeps_protected(self):
        fem = load_module("set-wallpaper")
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "sub"))
            old = os.path.join(td, "old.jpg")
            new = os.path.join(td, "sub", "new.jpg")
            for pth in (old, new):
                with open(pth, "wb") as f:
                    f.write(b"x" * 16)
            os.utime(old, (1, 1))
            os.utime(new, (2, 2))
            removed = fem.enforce_cache_limit(td, max_bytes=1 << 30, max_files=1)
            self.assertEqual(removed, 1)
            self.assertFalse(os.path.exists(old))
            self.assertTrue(os.path.exists(new))
            with open(old, "wb") as f:
                f.write(b"x" * 16)
            os.utime(old, (0, 0))
            removed2 = fem.enforce_cache_limit(td, max_bytes=1 << 30, max_files=1, protected=[new])
            self.assertEqual(removed2, 1)
            self.assertTrue(os.path.exists(new))
            self.assertFalse(os.path.exists(old))


if __name__ == "__main__":
    unittest.main()
