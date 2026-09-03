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
        delay = th.delay_seconds({"delay_ms": 100, "jitter_pct": 0})
        self.assertAlmostEqual(delay, 0.1)
        char = th.delay_seconds({"char_delay_ms": 20, "jitter_pct": 0}, char=True)
        self.assertAlmostEqual(char, 0.02)

    def test_load_config_missing_file(self):
        cfg = th.load_config(Path("/tmp/typehack-missing-config.json"))
        self.assertEqual(cfg["base_url"], th.DEFAULT_CONFIG["base_url"])


if __name__ == "__main__":
    unittest.main()
