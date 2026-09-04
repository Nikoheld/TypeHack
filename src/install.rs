//! Per-user install into `%LOCALAPPDATA%\TypeHack` so a downloaded exe is enough
//! on a clean Windows box (no admin, no Python).

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::version::{is_newer, VERSION};

pub fn install_dir() -> PathBuf {
    if let Ok(local) = std::env::var("LOCALAPPDATA") {
        return PathBuf::from(local).join("TypeHack");
    }
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."))
}

pub fn installed_exe() -> PathBuf {
    install_dir().join("TypeHack.exe")
}

pub fn version_file() -> PathBuf {
    install_dir().join("version.txt")
}

pub fn is_dev_build() -> bool {
    let p = std::env::current_exe()
        .map(|p| p.to_string_lossy().replace('/', "\\").to_lowercase())
        .unwrap_or_default();
    p.contains(r"\target\debug\") || p.contains(r"\target\release\")
}

pub fn read_installed_version() -> Option<String> {
    fs::read_to_string(version_file())
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

fn same_path(a: &Path, b: &Path) -> bool {
    match (fs::canonicalize(a), fs::canonicalize(b)) {
        (Ok(x), Ok(y)) => x == y,
        _ => a == b,
    }
}

/// Copy this binary into the per-user install dir and write Start-menu / desktop links.
/// `Ok(Some(exe))` means the caller should launch `exe` and exit.
pub fn ensure_installed() -> Result<Option<PathBuf>, String> {
    let dir = install_dir();
    fs::create_dir_all(&dir).map_err(|e| format!("Installationsordner: {e}"))?;
    let dest = installed_exe();
    let src = std::env::current_exe().map_err(|e| format!("exe: {e}"))?;

    if is_dev_build() {
        let _ = fs::write(version_file(), VERSION);
        return Ok(None);
    }

    let installed_ver = read_installed_version().unwrap_or_default();
    let should_copy = !dest.is_file()
        || (!same_path(&src, &dest) && (installed_ver.is_empty() || is_newer(VERSION, &installed_ver)));

    if should_copy && !same_path(&src, &dest) {
        if fs::copy(&src, &dest).is_err() {
            let pending = dir.join("TypeHack.exe.new");
            fs::copy(&src, &pending).map_err(|e| format!("Konnte TypeHack nicht installieren: {e}"))?;
        }
    }
    let _ = fs::write(version_file(), VERSION);
    create_shortcuts(&dest);
    if same_path(&src, &dest) || !dest.is_file() {
        Ok(None)
    } else {
        Ok(Some(dest))
    }
}

fn create_shortcuts(exe: &Path) {
    if let Ok(home) = std::env::var("USERPROFILE") {
        write_lnk(&PathBuf::from(home).join(r"Desktop\TypeHack.lnk"), exe);
    }
    if let Ok(appdata) = std::env::var("APPDATA") {
        let start = PathBuf::from(appdata).join(r"Microsoft\Windows\Start Menu\Programs");
        let _ = fs::create_dir_all(&start);
        write_lnk(&start.join("TypeHack.lnk"), exe);
    }
}

fn write_lnk(lnk: &Path, target: &Path) {
    let lnk_s = lnk.display().to_string().replace('\'', "''");
    let tgt_s = target.display().to_string().replace('\'', "''");
    let work = target
        .parent()
        .map(|p| p.display().to_string())
        .unwrap_or_default()
        .replace('\'', "''");
    let script = format!(
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk_s}'); $s.TargetPath='{tgt_s}'; $s.WorkingDirectory='{work}'; $s.Save()"
    );
    let mut cmd = Command::new("powershell");
    cmd.args(["-NoProfile", "-WindowStyle", "Hidden", "-Command", &script]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    let _ = cmd.status();
}

pub fn edge_is_installed() -> bool {
    crate::driver::edge_binary().is_some()
}