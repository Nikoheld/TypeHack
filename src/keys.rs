//! OS-level keystrokes. Space is virtual key 32; letters use VkKeyScanW (layout-aware).

pub const SPACE_VIRTUAL_KEY: u16 = 32;
pub const ENTER_VIRTUAL_KEY: u16 = 13;
pub const SHIFT_VIRTUAL_KEY: u16 = 0x10;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct KeyPlan {
    pub vk: u16,
    pub shift: bool,
    pub ctrl: bool,
    pub alt: bool,
}

pub fn key_plan_for_glyph(ch: char) -> KeyPlan {
    let glyph = crate::prompt::keys_for_char(ch);
    if glyph == ' ' {
        return KeyPlan {
            vk: SPACE_VIRTUAL_KEY,
            shift: false,
            ctrl: false,
            alt: false,
        };
    }
    if glyph == '\n' {
        return KeyPlan {
            vk: ENTER_VIRTUAL_KEY,
            shift: false,
            ctrl: false,
            alt: false,
        };
    }
    layout_plan(glyph).unwrap_or(KeyPlan {
        vk: 0,
        shift: false,
        ctrl: false,
        alt: false,
    })
}

#[cfg(windows)]
fn layout_plan(ch: char) -> Option<KeyPlan> {
    use windows::Win32::UI::Input::KeyboardAndMouse::VkKeyScanW;
    unsafe {
        let scan = VkKeyScanW(ch as u16);
        if scan == -1 || scan as u16 == 0xFFFF {
            return None;
        }
        let raw = scan as u16;
        Some(KeyPlan {
            vk: raw & 0xFF,
            shift: raw & 0x100 != 0,
            ctrl: raw & 0x200 != 0,
            alt: raw & 0x400 != 0,
        })
    }
}

#[cfg(not(windows))]
fn layout_plan(_ch: char) -> Option<KeyPlan> {
    None
}

/// Fire the whole remaining line in one OS burst. No Selenium between keys.
/// Sequential `keybd_event` is the fallback; a single `SendInput` array is the fast path.
pub fn send_glyphs(chars: &[char]) -> Result<(), String> {
    if chars.is_empty() {
        return Ok(());
    }
    #[cfg(windows)]
    {
        if send_glyphs_batch(chars).is_ok() {
            return Ok(());
        }
        for &ch in chars {
            send_glyph(ch)?;
        }
        Ok(())
    }
    #[cfg(not(windows))]
    {
        Err("OS-Tasten nur unter Windows".into())
    }
}

#[cfg(windows)]
pub fn send_glyph(ch: char) -> Result<(), String> {
    let plan = key_plan_for_glyph(ch);
    if plan.vk == 0 {
        return unicode_tap(crate::prompt::keys_for_char(ch));
    }
    unsafe {
        use windows::Win32::UI::Input::KeyboardAndMouse::{keybd_event, KEYEVENTF_KEYUP};
        if plan.shift {
            keybd_event(SHIFT_VIRTUAL_KEY as u8, 0, Default::default(), 0);
        }
        if plan.ctrl {
            keybd_event(0x11, 0, Default::default(), 0);
        }
        if plan.alt {
            keybd_event(0x12, 0, Default::default(), 0);
        }
        keybd_event(plan.vk as u8, 0, Default::default(), 0);
        keybd_event(plan.vk as u8, 0, KEYEVENTF_KEYUP, 0);
        if plan.alt {
            keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0);
        }
        if plan.ctrl {
            keybd_event(0x11, 0, KEYEVENTF_KEYUP, 0);
        }
        if plan.shift {
            keybd_event(SHIFT_VIRTUAL_KEY as u8, 0, KEYEVENTF_KEYUP, 0);
        }
    }
    Ok(())
}

#[cfg(not(windows))]
pub fn send_glyph(_ch: char) -> Result<(), String> {
    Err("OS-Tasten nur unter Windows".into())
}

#[cfg(windows)]
fn send_glyphs_batch(chars: &[char]) -> Result<(), String> {
    use windows::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS, KEYEVENTF_KEYUP,
        KEYEVENTF_UNICODE, VIRTUAL_KEY,
    };
    fn vk_event(vk: u16, up: bool) -> INPUT {
        INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: VIRTUAL_KEY(vk),
                    wScan: 0,
                    dwFlags: if up {
                        KEYEVENTF_KEYUP
                    } else {
                        KEYBD_EVENT_FLAGS::default()
                    },
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        }
    }
    fn unicode_event(code: u16, up: bool) -> INPUT {
        INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: VIRTUAL_KEY(0),
                    wScan: code,
                    dwFlags: if up {
                        KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                    } else {
                        KEYEVENTF_UNICODE
                    },
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        }
    }
    let mut inputs: Vec<INPUT> = Vec::with_capacity(chars.len() * 4);
    let mut shift_down = false;
    for &ch in chars {
        let plan = key_plan_for_glyph(ch);
        if plan.vk == 0 {
            if shift_down {
                inputs.push(vk_event(SHIFT_VIRTUAL_KEY, true));
                shift_down = false;
            }
            let code = crate::prompt::keys_for_char(ch) as u16;
            inputs.push(unicode_event(code, false));
            inputs.push(unicode_event(code, true));
            continue;
        }
        if plan.ctrl {
            inputs.push(vk_event(0x11, false));
        }
        if plan.alt {
            inputs.push(vk_event(0x12, false));
        }
        if plan.shift && !shift_down {
            inputs.push(vk_event(SHIFT_VIRTUAL_KEY, false));
            shift_down = true;
        } else if !plan.shift && shift_down {
            inputs.push(vk_event(SHIFT_VIRTUAL_KEY, true));
            shift_down = false;
        }
        inputs.push(vk_event(plan.vk, false));
        inputs.push(vk_event(plan.vk, true));
        if plan.alt {
            inputs.push(vk_event(0x12, true));
        }
        if plan.ctrl {
            inputs.push(vk_event(0x11, true));
        }
    }
    if shift_down {
        inputs.push(vk_event(SHIFT_VIRTUAL_KEY, true));
    }
    unsafe {
        let sent = SendInput(&inputs, std::mem::size_of::<INPUT>() as i32);
        if sent as usize != inputs.len() {
            return Err(format!("SendInput {sent}/{}", inputs.len()));
        }
    }
    Ok(())
}

#[cfg(windows)]
fn unicode_tap(ch: char) -> Result<(), String> {
    use windows::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE,
    };
    let code = ch as u16;
    unsafe {
        let down = INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: Default::default(),
                    wScan: code,
                    dwFlags: KEYEVENTF_UNICODE,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        };
        let mut up = down;
        up.Anonymous.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
        let arr = [down, up];
        let sent = SendInput(&arr, std::mem::size_of::<INPUT>() as i32);
        if sent != 2 {
            return Err("SendInput failed".into());
        }
    }
    Ok(())
}

#[cfg(windows)]
pub fn force_foreground_typewriter() -> bool {
    use windows::Win32::Foundation::{BOOL, HWND, LPARAM};
    use windows::Win32::System::Threading::{AttachThreadInput, GetCurrentThreadId};
    use windows::Win32::UI::WindowsAndMessaging::{
        BringWindowToTop, EnumWindows, GetForegroundWindow, GetWindowTextW, GetWindowThreadProcessId,
        IsWindowVisible, SetForegroundWindow, ShowWindow, SW_RESTORE, SW_SHOW,
    };
    struct Found(Vec<(HWND, String)>);
    unsafe extern "system" fn cb(hwnd: HWND, lparam: LPARAM) -> BOOL {
        unsafe {
            if !IsWindowVisible(hwnd).as_bool() {
                return BOOL(1);
            }
            let mut buf = [0u16; 256];
            let n = GetWindowTextW(hwnd, &mut buf);
            if n <= 0 {
                return BOOL(1);
            }
            let title = String::from_utf16_lossy(&buf[..n as usize]);
            let bag = &mut *(lparam.0 as *mut Found);
            bag.0.push((hwnd, title));
            BOOL(1)
        }
    }
    let mut found = Found(Vec::new());
    unsafe {
        let _ = EnumWindows(Some(cb), LPARAM(&mut found as *mut Found as isize));
    }
    let skip = ["discord", "nzxt", "kennwort", "password", "spotify", "slack", "teams"];
    let mut best_score = 0i32;
    let mut best_hwnd: Option<HWND> = None;
    for (hwnd, title) in &found.0 {
        let t = title.to_lowercase();
        if skip.iter().any(|s| t.contains(s)) {
            continue;
        }
        let mut score = 0;
        if t.contains("typewriter") {
            score += 12;
        }
        if t.contains("microsoft edge") || t.contains("google chrome") {
            score += 3;
        }
        if t.contains("typehack") {
            score -= 20;
        }
        if score > best_score {
            best_score = score;
            best_hwnd = Some(*hwnd);
        }
    }
    let Some(hwnd) = best_hwnd else {
        return false;
    };
    unsafe {
        let _ = ShowWindow(hwnd, SW_RESTORE);
        let _ = ShowWindow(hwnd, SW_SHOW);
        let fg = GetForegroundWindow();
        if fg == hwnd {
            return true;
        }
        let mut fg_pid = 0u32;
        let fg_thread = GetWindowThreadProcessId(fg, Some(&mut fg_pid));
        let cur = GetCurrentThreadId();
        let mut attached = false;
        if fg_thread != 0 && cur != 0 && fg_thread != cur {
            attached = AttachThreadInput(cur, fg_thread, true).as_bool();
        }
        let _ = BringWindowToTop(hwnd);
        let ok = SetForegroundWindow(hwnd).as_bool();
        if attached {
            let _ = AttachThreadInput(cur, fg_thread, false);
        }
        ok || GetForegroundWindow() == hwnd
    }
}

#[cfg(not(windows))]
pub fn force_foreground_typewriter() -> bool {
    false
}
