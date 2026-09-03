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
        ids = [value for by, value in th.PROMPT_SELECTORS if by == th.By.ID]
        self.assertIn("text_todo_1", ids)

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
        self.assertEqual(th.keys_for_char(" "), " ")
        self.assertEqual(th.keys_for_char("\xa0"), " ")
        self.assertEqual(th.keys_for_char("a"), "a")
        self.assertEqual(th.normalize_prompt_text("a\xa0b"), "a b")

    def test_auto_install_updates_defaults_on(self):
        self.assertTrue(th.DEFAULT_CONFIG["auto_install_updates"])

    def test_app_dir_dev_is_source_folder(self):
        self.assertEqual(th.app_dir(), Path(th.__file__).resolve().parent)
        self.assertTrue(hasattr(th, "VERSION"))


class PromptExtractTests(unittest.TestCase):
    """Drive the shipped extract / pick / glyph path — the same helpers prompt_text and start_typing use."""

    LINE_WITH_SPACES = (
        '<div id="typewriter-text">'
        '<span class="letter">H</span><span class="letter">a</span>'
        '<span class="letter">l</span><span class="letter">l</span>'
        '<span class="letter">o</span>'
        '<span class="space">&nbsp;</span>'
        '<span class="letter">W</span><span class="letter">e</span>'
        '<span class="letter">l</span><span class="letter">t</span>'
        '<span class="blank"></span>'
        '<span class="letter">ö</span>'
        " "
        '<span class="letter">ü</span>'
        "</div>"
    )
    SPACE_ONLY_NBSP = '<div id="typewriter-text"><span class="space">&nbsp;</span></div>'
    SPACE_ONLY_TEXT = '<div id="typewriter-text"> </div>'
    EMPTY_WRAPPER = '<div class="current-line"></div>'
    DONE_PREFIX = (
        '<div id="typewriter-text">'
        '<span class="letter done">H</span>'
        '<span class="letter correct">a</span>'
        '<span class="letter">l</span>'
        '<span class="space">&nbsp;</span>'
        '<span class="letter">ö</span>'
        "</div>"
    )

    def test_extract_keeps_abstaende_and_umlauts(self):
        text = th.extract_prompt_from_html(self.LINE_WITH_SPACES)
        self.assertIn("Hallo", text)
        self.assertIn("Welt", text)
        self.assertIn("ö", text)
        self.assertIn("ü", text)
        self.assertIn(" ", text)
        self.assertNotEqual(text.replace(" ", ""), text)
        self.assertIn("Hallo Welt", text)

    def test_space_only_remaining_is_typeable(self):
        for html in (self.SPACE_ONLY_NBSP, self.SPACE_ONLY_TEXT):
            text = th.pick_remaining_prompt([html])
            self.assertTrue(text)
            self.assertEqual(text.strip("\n\r"), text)
            self.assertEqual(set(text), {" "})
            self.assertEqual(th.glyphs_to_type(text), [" "] * len(text))

    def test_space_only_does_not_raise_empty_prompt(self):
        th.pick_remaining_prompt([self.SPACE_ONLY_NBSP])
        th.pick_remaining_prompt([self.SPACE_ONLY_TEXT])

    def test_empty_wrapper_loses_to_real_line(self):
        picked = th.pick_remaining_prompt([self.EMPTY_WRAPPER, self.LINE_WITH_SPACES])
        self.assertEqual(picked, th.extract_prompt_from_html(self.LINE_WITH_SPACES))
        with self.assertRaises(th.TimeoutException) as ctx:
            th.pick_remaining_prompt([self.EMPTY_WRAPPER])
        self.assertIn("leer", str(ctx.exception).lower())

    def test_skips_already_typed_spans(self):
        remaining = th.extract_prompt_from_html(self.DONE_PREFIX)
        self.assertFalse(remaining.startswith("Ha"))
        self.assertTrue(remaining.startswith("l"))
        self.assertIn(" ", remaining)
        self.assertIn("ö", remaining)
        self.assertEqual(th.glyphs_to_type(remaining), list(remaining))

    # Real at4.typewriter.at remaining node: bare spans, empty span = space.
    TODO_LINE = (
        '<div id="text_todo_1">'
        "<span>H</span><span>a</span><span>l</span><span>l</span><span>o</span>"
        "<span></span>"
        "<span>W</span><span>e</span><span>l</span><span>t</span>"
        "<span> </span>"
        "<span>ö</span>"
        "</div>"
    )
    TODO_SPACE_EMPTY = '<div id="text_todo_1"><span></span></div>'
    TODO_SPACE_NBSP = '<div id="text_todo_1"><span>&nbsp;</span></div>'
    TODO_SPACE_TEXT = '<div id="text_todo_1"><span> </span></div>'
    TODO_AFTER_DONE_PARENT = (
        '<div class="tw-wrap">'
        '<div id="text_done_1"><span>H</span><span>a</span></div>'
        '<div id="text_todo_1"><span>l</span><span></span><span>ö</span></div>'
        "</div>"
    )

    def test_text_todo_1_keeps_letter_and_empty_space_spans(self):
        text = th.extract_prompt_from_html(self.TODO_LINE)
        self.assertEqual(text, "Hallo Welt ö")
        self.assertEqual(th.glyphs_to_type(text), list("Hallo Welt ö"))
        self.assertIn("text_todo_1", [v for _b, v in th.PROMPT_SELECTORS])

    def test_text_todo_1_space_only_remaining_is_typeable(self):
        for html in (self.TODO_SPACE_EMPTY, self.TODO_SPACE_NBSP, self.TODO_SPACE_TEXT):
            text = th.pick_remaining_prompt([html])
            self.assertEqual(set(text), {" "})
            self.assertEqual(th.glyphs_to_type(text), [" "] * len(text))

    def test_text_todo_1_preferred_over_done_parent(self):
        parent = self.TODO_AFTER_DONE_PARENT
        todo = '<div id="text_todo_1"><span>l</span><span></span><span>ö</span></div>'
        picked = th.pick_remaining_prompt([parent, todo, self.EMPTY_WRAPPER])
        self.assertEqual(picked, "l ö")
        self.assertFalse(picked.startswith("Ha"))

    def test_pretty_printed_indent_is_not_typed_spaces(self):
        html = """<div id="typewriter-text">
  <span class="letter done">A</span>
  <span class="letter">b</span>
  <span class="space">&nbsp;</span>
  <span class="letter">ö</span>
</div>"""
        remaining = th.extract_prompt_from_html(html)
        self.assertEqual(remaining, "b ö")
        self.assertEqual(th.glyphs_to_type(remaining), ["b", " ", "ö"])


class GlyphSendTests(unittest.TestCase):
    def test_payload_is_glyph_not_scan_code(self):
        for ch in (" ", "\xa0", "z", "y", "ö", "ß"):
            info = th.glyph_payload(ch)
            want = " " if ch in (" ", "\xa0") else ch
            self.assertEqual(info["insert_text"], want)
            self.assertEqual(info["text"].replace("\r", "\n") if want == "\n" else info["insert_text"], want)
            self.assertFalse(
                (info.get("code") or "").startswith("Key"),
                f"{ch!r} must not use physical Key* (QWERTZ remaps y/z)",
            )

    def test_qwertz_y_and_z_stay_distinct(self):
        y = th.glyph_payload("y")
        z = th.glyph_payload("z")
        self.assertEqual(y["insert_text"], "y")
        self.assertEqual(z["insert_text"], "z")
        self.assertNotEqual(y["insert_text"], z["insert_text"])
        self.assertNotEqual(y["code"], "KeyZ")
        self.assertNotEqual(z["code"], "KeyY")
        self.assertEqual(y["vk"], 0)
        self.assertEqual(z["vk"], 0)

    def test_start_typing_emits_remaining_in_order(self):
        remaining = th.extract_prompt_from_html(PromptExtractTests.DONE_PREFIX)
        sent = th.glyphs_to_type(remaining)
        self.assertEqual(sent, ["l", " ", "ö"])
        self.assertNotIn("H", sent)
        self.assertNotIn("a", sent)

    def test_type_char_uses_glyph_payload(self):
        import inspect

        src = inspect.getsource(th.type_char)
        self.assertIn("glyph_payload", src)
        self.assertIn("Input.insertText", src)
        self.assertNotIn("Key{ch.upper()}", src)
        typing_src = inspect.getsource(th.TypeHackApp.start_typing)
        self.assertIn("glyphs_to_type", typing_src)
        self.assertIn("prompt_text", typing_src)


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
