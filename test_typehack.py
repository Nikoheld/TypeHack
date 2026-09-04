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
            self.assertEqual(th.keys_for_char(ch), want)
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
        remaining = th.extract_prompt_from_html(PromptExtractTests.TODO_LINE)
        sent = th.glyphs_to_type(remaining)
        self.assertEqual(sent, list("Hallo Welt ö"))
        self.assertIn(" ", sent)
        self.assertIn("ö", sent)

    def test_first_remaining_glyph_is_next_key(self):
        remaining = th.extract_prompt_from_html(
            '<div id="text_todo_1"><span>l</span><span></span><span>ö</span></div>'
        )
        self.assertEqual(th.first_remaining_glyph(remaining), "l")
        self.assertEqual(th.first_remaining_glyph(" ö"), " ")
        self.assertEqual(th.first_remaining_glyph("ö"), "ö")

    def test_os_space_uses_virtual_key_32(self):
        from unittest import mock

        with mock.patch.object(th, "_vk_tap") as vk:
            th.os_send_glyph(" ")
            th.os_send_glyph("\xa0")
        vk.assert_has_calls([mock.call(32), mock.call(32)])
        self.assertEqual(vk.call_count, 2)

    def test_os_letter_uses_vkkeyscan_shift(self):
        from unittest import mock

        with mock.patch.object(th, "_vk_tap") as vk:
            with mock.patch.object(th, "_vk_down") as down:
                with mock.patch.object(th, "_vk_up") as up:
                    with mock.patch.object(th.ctypes.windll.user32, "VkKeyScanW", return_value=0x141):
                        th.os_send_glyph("A")
        vk.assert_called_once_with(0x41)
        down.assert_called_with(0x10)
        up.assert_called_with(0x10)

    def test_type_char_uses_os_then_js_cdp_chains(self):
        import inspect
        from unittest import mock

        class Box:
            def click(self):
                self.clicked = True

            def send_keys(self, glyph):
                raise AssertionError("do not send_keys only on the non-editable box")

        class Driver:
            def find_element(self, by, value):
                self.value = value
                return Box()

            def execute_cdp_cmd(self, *_a, **_k):
                raise AssertionError("CDP is fallback only")

            def execute_script(self, *_a, **_k):
                raise AssertionError("JS is fallback only")

        remaining = th.extract_prompt_from_html(
            '<div id="text_todo_1"><span>l</span><span></span><span>ö</span></div>'
        )
        sent = []
        th.remember_send(None)
        with mock.patch.object(th, "os_send_glyph", side_effect=lambda ch: sent.append(ch)):
            for ch in th.glyphs_to_type(remaining):
                th.type_char(Driver(), ch)
        self.assertEqual(sent, ["l", " ", "ö"])
        src = inspect.getsource(th.type_char)
        self.assertIn("send_glyph", src)
        send_src = inspect.getsource(th.send_glyph)
        self.assertIn("_dispatch_glyph", send_src)
        dispatch_src = inspect.getsource(th._dispatch_glyph)
        self.assertIn("os_send_glyph", dispatch_src)
        self.assertIn("js_send_glyph", dispatch_src)
        self.assertIn("cdp_send_glyph", dispatch_src)
        self.assertEqual(th.SEND_METHODS[0], "os")
        self.assertIn("js", th.SEND_METHODS)
        self.assertIn("cdp", th.SEND_METHODS)
        typing_src = inspect.getsource(th.TypeHackApp.start_typing)
        self.assertIn("first_remaining_glyph", typing_src)
        self.assertIn("send_glyph_verified", typing_src)
        self.assertIn("arm_lesson", typing_src)
        self.assertIn("foreground_browser", typing_src)

    def test_verified_send_tries_next_method_if_prompt_unchanged(self):
        from unittest import mock

        htmls = [
            '<div id="text_todo_1"><span>l</span><span></span><span>ö</span></div>',
            '<div id="text_todo_1"><span></span><span>ö</span></div>',
        ]

        class Driver:
            def find_element(self, by, value):
                raise Exception("no box")

        th.remember_send(None)
        with mock.patch.object(th, "collect_prompt_html", side_effect=lambda _d: [htmls.pop(0)]):
            with mock.patch.object(th, "os_send_glyph"):
                with mock.patch.object(th, "js_send_glyph") as js:
                    used = th.send_glyph_verified(Driver(), "l", "l ö", settle_s=0)
        self.assertEqual(used, "js")
        js.assert_called_once()
        self.assertEqual(th.preferred_send(), "js")

    def test_arm_lesson_clicks_start_dialog(self):
        clicked = []

        class El:
            def __init__(self, shown=True):
                self._shown = shown
                self.text = "OK"

            def is_displayed(self):
                return self._shown

            def get_attribute(self, name):
                return ""

            def click(self):
                clicked.append("ok")

        class Driver:
            def find_elements(self, by, value):
                if value == ".ui-dialog-buttonset button":
                    return [El()]
                return []

            def execute_script(self, *_a, **_k):
                return None

        from unittest import mock

        with mock.patch.object(th, "os_send_glyph") as os_send:
            self.assertTrue(th.arm_lesson(Driver()))
        self.assertEqual(clicked, ["ok"])
        os_send.assert_called_with("\n")
        ids = [value for _by, value in th.START_CLICK]
        self.assertTrue(any("ui-dialog-buttonset" in str(v) for v in ids))
        self.assertTrue(any("cockpitStartButton" in str(v) for v in ids))


class CaptchaReloadTests(unittest.TestCase):
    CHAL = (
        "<html><form id='chal-form'><h1>Einen Moment bitte — Sicherheitsprüfung</h1>"
        "<p>I'm not a robot</p></form></html>"
    )
    LOGIN = '<form id="login-form"><input id="LoginForm_username" name="LoginForm[username]"></form>'
    TODO = '<div id="text_todo_1"><span>a</span><span></span><span>b</span></div>'

    def test_reload_only_after_two_seconds_on_captcha(self):
        self.assertTrue(th.is_captcha_view(self.CHAL, "https://at4.typewriter.at/_chal/x"))
        self.assertFalse(th.should_reload_captcha(captcha=True, elapsed_s=1.9))
        self.assertTrue(th.should_reload_captcha(captcha=True, elapsed_s=2.0))
        self.assertTrue(th.should_reload_captcha(captcha=True, elapsed_s=2.5))

    def test_never_reload_login_or_lesson(self):
        self.assertFalse(th.is_captcha_view(self.LOGIN, "https://at4.typewriter.at/index.php?r=site/login"))
        self.assertFalse(th.is_captcha_view(self.TODO, "https://at4.typewriter.at/index.php?r=typewriter/runLevel"))
        self.assertFalse(th.should_reload_captcha(captcha=False, elapsed_s=10))

    def test_maybe_reload_calls_refresh_only_when_due(self):
        class Driver:
            def __init__(self, html, url):
                self.page_source = html
                self.current_url = url
                self.refreshes = 0

            def refresh(self):
                self.refreshes += 1

        chal = Driver(self.CHAL, "https://at4.typewriter.at/_chal/")
        t0 = 100.0
        seen = th.maybe_reload_stuck_captcha(chal, None, now=t0)
        self.assertEqual(chal.refreshes, 0)
        seen = th.maybe_reload_stuck_captcha(chal, seen, now=t0 + 1.9)
        self.assertEqual(chal.refreshes, 0)
        th.maybe_reload_stuck_captcha(chal, seen, now=t0 + 2.0)
        self.assertEqual(chal.refreshes, 1)

        login = Driver(self.LOGIN, "https://at4.typewriter.at/index.php?r=site/login")
        self.assertIsNone(th.maybe_reload_stuck_captcha(login, t0, now=t0 + 10))
        self.assertEqual(login.refreshes, 0)

        lesson = Driver(self.TODO, "https://at4.typewriter.at/index.php?r=typewriter/runLevel")
        self.assertIsNone(th.maybe_reload_stuck_captcha(lesson, t0, now=t0 + 10))
        self.assertEqual(lesson.refreshes, 0)

    def test_login_and_typing_use_captcha_reload_helper(self):
        import inspect

        login_src = inspect.getsource(th.TypeHackApp.login)
        typing_src = inspect.getsource(th.TypeHackApp.start_typing)
        self.assertIn("maybe_reload_stuck_captcha", login_src)
        self.assertIn("maybe_reload_stuck_captcha", typing_src)
        reload_src = inspect.getsource(th.pass_altcha_then_reload)
        self.assertNotIn("driver.refresh", reload_src)


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
