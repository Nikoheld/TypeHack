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


if __name__ == "__main__":
    unittest.main()
