//! Microsoft Edge + matching msedgedriver for a clean Windows install.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::install::install_dir;
use crate::update::{http_get_bytes, http_get_text};

pub const DRIVER_NAME: &str = "msedgedriver.exe";
pub const MIRROR: &str = "https://msedgedriver.microsoft.com";

pub fn driver_dir() -> PathBuf {
    install_dir().join("driver")
}

pub fn driver_path() -> PathBuf {
    driver_dir().join(DRIVER_NAME)
}

pub fn edge_binary() -> Option<PathBuf> {
    if let Ok(home) = std::env::var("PROGRAMFILES(X86)") {
        let p = PathBuf::from(home).join(r"Microsoft\Edge\Application\msedge.exe");
        if p.is_file() {
            return Some(p);
        }
    }
    for p in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ] {
        let p = PathBuf::from(p);
        if p.is_file() {
            return Some(p);
        }
    }
    None
}

pub fn looks_like_version(s: &str) -> bool {
    let s = s.trim();
    if s.is_empty() {
        return false;
    }
    s.chars().all(|c| c.is_ascii_digit() || c == '.') && s.chars().next().is_some_and(|c| c.is_ascii_digit())
}

pub fn zip_url_for(version: &str) -> String {
    format!("{MIRROR}/{version}/edgedriver_win64.zip")
}

pub fn latest_release_url(major: &str) -> String {
    format!("{MIRROR}/LATEST_RELEASE_{major}_WINDOWS")
}

pub fn edge_version() -> Option<String> {
    let bin = edge_binary()?;
    let parent = bin.parent()?;
    let mut versions = Vec::new();
    if let Ok(rd) = fs::read_dir(parent) {
        for ent in rd.flatten() {
            let name = ent.file_name().to_string_lossy().to_string();
            if ent.path().is_dir() && looks_like_version(&name) {
                versions.push(name);
            }
        }
    }
    versions.sort_by(|a, b| crate::version::parse_version(b).cmp(&crate::version::parse_version(a)));
    if let Some(v) = versions.into_iter().next() {
        return Some(v);
    }
    powershell_file_version(&bin)
}

fn powershell_file_version(exe: &Path) -> Option<String> {
    let path = exe.display().to_string().replace('\'', "''");
    let script = format!("(Get-Item -LiteralPath '{path}').VersionInfo.ProductVersion");
    let mut cmd = Command::new("powershell");
    cmd.args(["-NoProfile", "-WindowStyle", "Hidden", "-Command", &script]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    let out = cmd.output().ok()?;
    let text = String::from_utf8_lossy(&out.stdout).trim().to_string();
    if looks_like_version(&text) {
        Some(text)
    } else {
        None
    }
}

fn find_existing() -> Option<PathBuf> {
    let mut cands = vec![
        driver_path(),
        install_dir().join(DRIVER_NAME),
        PathBuf::from(DRIVER_NAME),
        PathBuf::from(r".\msedgedriver.exe"),
    ];
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            cands.push(dir.join(DRIVER_NAME));
            cands.push(dir.join("driver").join(DRIVER_NAME));
        }
    }
    if let Ok(home) = std::env::var("USERPROFILE") {
        let root = PathBuf::from(home).join(r".cache\selenium\msedgedriver\win64");
        if let Ok(iter) = fs::read_dir(root) {
            for ent in iter.flatten() {
                let p = ent.path().join(DRIVER_NAME);
                if p.is_file() {
                    cands.push(p);
                }
            }
        }
    }
    cands.into_iter().find(|p| p.is_file())
}

pub fn extract_msedgedriver(zip_bytes: &[u8], dest: &Path) -> Result<(), String> {
    let reader = std::io::Cursor::new(zip_bytes);
    let mut archive = zip::ZipArchive::new(reader).map_err(|e| format!("zip: {e}"))?;
    for i in 0..archive.len() {
        let mut file = archive.by_index(i).map_err(|e| format!("zip: {e}"))?;
        let name = file.name().replace('\\', "/");
        let file_name = name.rsplit('/').next().unwrap_or("");
        if file_name.eq_ignore_ascii_case(DRIVER_NAME) {
            if let Some(parent) = dest.parent() {
                fs::create_dir_all(parent).map_err(|e| e.to_string())?;
            }
            let mut out = fs::File::create(dest).map_err(|e| e.to_string())?;
            std::io::copy(&mut file, &mut out).map_err(|e| e.to_string())?;
            return Ok(());
        }
    }
    Err("zip enthält kein msedgedriver.exe".into())
}

fn download_matching(dest: &Path) -> Result<(), String> {
    let mut tried = Vec::new();
    if let Some(v) = edge_version() {
        tried.push(zip_url_for(&v));
        if let Some(major) = v.split('.').next() {
            if let Ok(latest) = http_get_text(&latest_release_url(major)) {
                let latest = latest.trim();
                if looks_like_version(latest) {
                    tried.push(zip_url_for(latest));
                }
            }
        }
    }
    if let Ok(stable) = http_get_text(&format!("{MIRROR}/LATEST_STABLE")) {
        let stable = stable.trim();
        if looks_like_version(stable) {
            tried.push(zip_url_for(stable));
        }
    }
    tried.dedup();
    let mut last = "kein Treiber-Download".to_string();
    for url in tried {
        match http_get_bytes(&url).and_then(|bytes| extract_msedgedriver(&bytes, dest)) {
            Ok(()) => return Ok(()),
            Err(e) => last = format!("{url}: {e}"),
        }
    }
    Err(last)
}

/// Find or download msedgedriver into `%LOCALAPPDATA%\TypeHack\driver`.
pub fn ensure_msedgedriver() -> Result<PathBuf, String> {
    if edge_binary().is_none() {
        return Err(
            "Microsoft Edge fehlt. Bitte Edge installieren: https://www.microsoft.com/edge".into(),
        );
    }
    let dest = driver_path();
    if dest.is_file() {
        return Ok(dest);
    }
    if let Some(found) = find_existing() {
        if found != dest {
            let _ = fs::create_dir_all(driver_dir());
            if fs::copy(&found, &dest).is_ok() {
                return Ok(dest);
            }
        }
        return Ok(found);
    }
    download_matching(&dest)?;
    if dest.is_file() {
        Ok(dest)
    } else {
        Err("msedgedriver.exe konnte nicht eingerichtet werden.".into())
    }
}