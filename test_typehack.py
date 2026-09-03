#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

import TypeHack as th


class CredentialTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credentials.json"
            th.save_credentials("user@example.com", "secret", path)
            email, password = th.load_credentials(path)
            self.assertEqual(email, "user@example.com")
            self.assertEqual(password, "secret")

    def test_missing_file(self):
        email, password = th.load_credentials(Path("/tmp/does-not-exist-typehack.json"))
        self.assertIsNone(email)
        self.assertIsNone(password)

    def test_login_selectors_cover_legacy_ids(self):
        ids = [value for by, value in th.LOGIN_USER if by == th.By.ID]
        self.assertIn("LoginForm_username", ids)
        pw = [value for by, value in th.LOGIN_PASS if by == th.By.ID]
        self.assertIn("LoginForm_pw", pw)

    def test_prompt_selectors_not_empty(self):
        self.assertGreaterEqual(len(th.PROMPT_SELECTORS), 3)

    def test_merge_config_keeps_defaults_and_overrides(self):
        cfg = th.merge_config({"delay_ms": 120, "unknown": 1})
        self.assertEqual(cfg["delay_ms"], 120)
        self.assertEqual(cfg["browser"], "Auto")
        self.assertNotIn("unknown", cfg)

    def test_delay_seconds_no_jitter(self):
        delay = th.delay_seconds({"delay_ms": 100, "jitter_pct": 0, "strokes_per_10min": 0})
        self.assertAlmostEqual(delay, 0.1)
        char = th.delay_seconds({"char_delay_ms": 20, "jitter_pct": 0, "strokes_per_10min": 0}, char=True)
        self.assertAlmostEqual(char, 0.02)

    def test_strokes_per_10min_interval(self):
        self.assertEqual(th.clamp_strokes(2000), 2000)
        self.assertEqual(th.clamp_strokes(50), 200)
        self.assertEqual(th.clamp_strokes(99999), 8000)
        # 2000 Anschläge / 10 min = 0.3 s Abstand
        self.assertAlmostEqual(th.interval_seconds({"strokes_per_10min": 2000, "jitter_pct": 0}), 0.3)
        self.assertAlmostEqual(th.interval_seconds({"strokes_per_10min": 600, "jitter_pct": 0}), 1.0)
        self.assertAlmostEqual(
            th.delay_seconds({"strokes_per_10min": 2000, "jitter_pct": 0}, char=True),
            0.3,
        )

    def test_merge_config_keeps_strokes(self):
        cfg = th.merge_config({"strokes_per_10min": 1800})
        self.assertEqual(cfg["strokes_per_10min"], 1800)

    def test_prompt_extractor_walks_text_nodes_and_nbsp(self):
        self.assertIn("childNodes", th.EXTRACT_PROMPT_JS)
        self.assertIn("spacey", th.EXTRACT_PROMPT_JS)
        self.assertIn("\\u00a0", th.EXTRACT_PROMPT_JS)

    def test_login_does_not_block_on_captcha_refresh(self):
        import inspect

        src = inspect.getsource(th.TypeHackApp.login)
        self.assertNotIn("pass_altcha_then_reload", src)
        self.assertIn("dismiss_overlays", src)
        self.assertIn("nudge_captcha", src)
        reload_src = inspect.getsource(th.pass_altcha_then_reload)
        self.assertNotIn("driver.refresh", reload_src)
        self.assertIn("fc-cta-consent", str(th.OVERLAY_CLICK))

    def test_load_config_missing_file(self):
        cfg = th.load_config(Path("/tmp/typehack-missing-config.json"))
        self.assertEqual(cfg["base_url"], th.DEFAULT_CONFIG["base_url"])

    def test_spaces_become_keys_space(self):
        self.assertEqual(th.keys_for_char(" "), th.Keys.SPACE)
        self.assertEqual(th.keys_for_char("\xa0"), th.Keys.SPACE)
        self.assertEqual(th.keys_for_char("a"), "a")
        self.assertEqual(th.normalize_prompt_text("a\xa0b"), "a b")

    def test_auto_install_updates_defaults_on(self):
        self.assertTrue(th.DEFAULT_CONFIG["auto_install_updates"])

    def test_app_dir_dev_is_source_folder(self):
        self.assertEqual(th.app_dir(), Path(th.__file__).resolve().parent)
        self.assertTrue(hasattr(th, "VERSION"))


class UpdaterTests(unittest.TestCase):
    def test_parse_and_compare(self):
        import updater

        self.assertEqual(updater.parse_version("v2.2.0"), (2, 2, 0))
        self.assertTrue(updater.is_newer("2.2.1", "2.2.0"))
        self.assertFalse(updater.is_newer("2.2.0", "2.2.0"))
        self.assertFalse(updater.is_newer("2.1.9", "2.2.0"))

    def test_pick_setup_asset(self):
        import updater

        release = {
            "assets": [
                {"name": "notes.txt", "size": 10, "browser_download_url": "http://x/notes"},
                {
                    "name": "TypeHack-Setup-2.2.0.exe",
                    "size": 40000000,
                    "browser_download_url": "http://x/setup.exe",
                    "digest": "sha256:abc",
                },
            ]
        }
        asset = updater.pick_setup_asset(release)
        self.assertEqual(asset["name"], "TypeHack-Setup-2.2.0.exe")
        self.assertEqual(updater.digest_from_asset(asset), "abc")

    def test_sha256_file(self):
        import updater
        import tempfile
        import hashlib

        with tempfile.NamedTemporaryFile(delete=False) as fh:
            fh.write(b"typehack")
            name = fh.name

        self.assertEqual(updater.sha256_file(Path(name)), hashlib.sha256(b"typehack").hexdigest())

    def test_installer_batch_never_uses_empty_start_title(self):
        import updater

        setup = Path(r"C:\Users\Niko\AppData\Local\Temp\TypeHack-Setup-2.3.1.exe")
        restart = Path(r"C:\Users\Niko\AppData\Local\TypeHack\TypeHack.exe")
        text = updater.installer_batch_text(setup, restart)
        self.assertNotIn('start ""', text)
        self.assertNotIn("start ''", text)
        self.assertIn('start "TypeHack-Setup" /wait', text)
        self.assertIn('start "TypeHack"', text)
        self.assertIn(str(setup), text)
        self.assertIn("/VERYSILENT", text)

    def test_launch_installer_missing_file(self):
        import updater
        from unittest import mock

        missing = Path(tempfile.gettempdir()) / "TypeHack-missing-setup.exe"
        with mock.patch.object(updater, "_is_windows", return_value=True):
            with self.assertRaises(FileNotFoundError):
                updater.launch_installer(missing)

    def test_launch_installer_writes_batch_without_empty_title(self):
        import updater
        from unittest import mock

        tmp = Path(tempfile.mkdtemp())
        setup = tmp / "TypeHack-Setup-2.3.1.exe"
        setup.write_bytes(b"MZ")
        restart = tmp / "TypeHack.exe"
        restart.write_bytes(b"MZ")
        with mock.patch.object(updater, "_is_windows", return_value=True):
            with mock.patch.object(updater.subprocess, "Popen") as popen:
                updater.launch_installer(setup, restart_exe=restart)
        popen.assert_called_once()
        argv = popen.call_args[0][0]
        self.assertEqual(argv[1], "/c")
        bat = Path(argv[2])
        body = bat.read_text(encoding="utf-8")
        self.assertNotIn('start ""', body)
        self.assertIn('start "TypeHack-Setup" /wait', body)


if __name__ == "__main__":
    unittest.main()
