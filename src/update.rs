//! GitHub-release auto-updater. Runs in the background; applies when not typing.

use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use sha2::{Digest, Sha256};

use crate::install::{install_dir, installed_exe, is_dev_build};
use crate::version::{is_newer, VERSION};

pub const RELEASES_URL: &str = "https://api.github.com/repos/Nikoheld/TypeHack/releases/latest";
pub const VERSION_JSON_URL: &str = "https://raw.githubusercontent.com/Nikoheld/TypeHack/main/version.json";
pub const USER_AGENT: &str = "TypeHack-Updater";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateInfo {
    pub version: String,
    pub url: String,
    pub name: String,
    pub sha256: String,
    pub notes: String,
}

pub fn pending_new_exe() -> PathBuf {
    install_dir().join("TypeHack.exe.new")
}

pub fn digest_from_asset(asset: &serde_json::Value) -> String {
    let digest = asset.get("digest").and_then(|v| v.as_str()).unwrap_or("");
    digest
        .strip_prefix("sha256:")
        .or_else(|| digest.strip_prefix("SHA256:"))
        .unwrap_or("")
        .trim()
        .to_lowercase()
}

pub fn pick_setup_asset(release: &serde_json::Value) -> Option<serde_json::Value> {
    let assets = release.get("assets")?.as_array()?;
    let mut setup: Vec<&serde_json::Value> = assets
        .iter()
        .filter(|a| {
            let name = a.get("name").and_then(|v| v.as_str()).unwrap_or("");
            name.to_lowercase().contains("setup") && name.to_lowercase().ends_with(".exe")
        })
        .collect();
    if setup.is_empty() {
        return None;
    }
    setup.sort_by_key(|a| a.get("size").and_then(|v| v.as_u64()).unwrap_or(0));
    setup.last().cloned().cloned()
}

pub fn pick_update_asset(release: &serde_json::Value) -> Option<UpdateInfo> {
    let version = release
        .get("tag_name")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .trim_start_matches(['v', 'V'])
        .to_string();
    if version.is_empty() {
        return None;
    }
    let notes = release
        .get("body")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .chars()
        .take(2000)
        .collect::<String>();
    if let Some(asset) = pick_setup_asset(release) {
        return asset_to_info(&asset, &version, &notes);
    }
    let assets = release.get("assets")?.as_array()?;
    let mut portable: Vec<&serde_json::Value> = assets
        .iter()
        .filter(|a| {
            let name = a.get("name").and_then(|v| v.as_str()).unwrap_or("").to_lowercase();
            name.starts_with("typehack") && name.ends_with(".exe") && !name.contains("setup")
        })
        .collect();
    portable.sort_by_key(|a| a.get("size").and_then(|v| v.as_u64()).unwrap_or(0));
    portable.last().and_then(|a| asset_to_info(a, &version, &notes))
}

fn asset_to_info(asset: &serde_json::Value, version: &str, notes: &str) -> Option<UpdateInfo> {
    Some(UpdateInfo {
        version: version.to_string(),
        url: asset.get("browser_download_url")?.as_str()?.to_string(),
        name: asset.get("name")?.as_str()?.to_string(),
        sha256: digest_from_asset(asset),
        notes: notes.to_string(),
    })
}

pub fn fetch_latest() -> Result<Option<UpdateInfo>, String> {
    let body = http_get_text(RELEASES_URL)?;
    let json: serde_json::Value = serde_json::from_str(&body).map_err(|e| format!("Release-JSON: {e}"))?;
    if json.get("prerelease").and_then(|v| v.as_bool()).unwrap_or(false) {
        return Ok(None);
    }
    if json.get("tag_name").and_then(|v| v.as_str()).is_none() {
        return Ok(None);
    }
    Ok(pick_update_asset(&json))
}

pub fn sha256_file(path: &Path) -> Result<String, String> {
    let mut file = fs::File::open(path).map_err(|e| e.to_string())?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 1024 * 1024];
    loop {
        let n = file.read(&mut buf).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

pub fn installer_batch_text(setup: &Path, restart_exe: Option<&Path>) -> String {
    let mut lines = vec![
        "@echo off".to_string(),
        "setlocal EnableExtensions".into(),
        "ping -n 3 127.0.0.1 >nul".into(),
        format!(
            "start \"TypeHack-Setup\" /wait \"{}\" /VERYSILENT /NORESTART /CLOSEAPPLICATIONS /SUPPRESSMSGBOXES",
            setup.display()
        ),
    ];
    if let Some(restart) = restart_exe {
        lines.push(format!(
            "if exist \"{}\" start \"TypeHack\" \"{}\"",
            restart.display(),
            restart.display()
        ));
    }
    lines.push("endlocal".into());
    lines.join("\r\n") + "\r\n"
}

pub fn replace_batch_text(new_exe: &Path, dest: &Path) -> String {
    format!(
        "@echo off\r\n\
setlocal EnableExtensions\r\n\
ping -n 3 127.0.0.1 >nul\r\n\
set /a n=0\r\n\
:retry\r\n\
copy /Y \"{new}\" \"{dest}\" >nul\r\n\
if errorlevel 1 (\r\n\
  set /a n+=1\r\n\
  if %n% GEQ 40 goto fail\r\n\
  ping -n 2 127.0.0.1 >nul\r\n\
  goto retry\r\n\
)\r\n\
del /F /Q \"{new}\" >nul 2>nul\r\n\
if exist \"{dest}\" start \"TypeHack\" \"{dest}\"\r\n\
goto end\r\n\
:fail\r\n\
:end\r\n\
endlocal\r\n",
        new = new_exe.display(),
        dest = dest.display()
    )
}

fn spawn_cmd_script(body: &str) -> Result<(), String> {
    let bat = std::env::temp_dir().join("TypeHack-apply-update.cmd");
    let mut f = fs::File::create(&bat).map_err(|e| e.to_string())?;
    f.write_all(body.replace('\n', "\r\n").as_bytes())
        .map_err(|e| e.to_string())?;
    drop(f);
    let comspec = std::env::var("COMSPEC").unwrap_or_else(|_| "cmd.exe".into());
    let mut cmd = Command::new(comspec);
    cmd.args(["/c", &bat.to_string_lossy()])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .current_dir(std::env::temp_dir());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x00000008 | 0x00000200 | 0x08000000);
    }
    cmd.spawn().map_err(|e| format!("Update-Helfer: {e}"))?;
    Ok(())
}

pub fn launch_installer(setup: &Path, restart_exe: Option<&Path>) -> Result<(), String> {
    if !setup.is_file() {
        return Err(format!("Installer fehlt: {}", setup.display()));
    }
    spawn_cmd_script(&installer_batch_text(setup, restart_exe))
}

pub fn launch_replace_helper(new_exe: &Path, dest: &Path) -> Result<(), String> {
    if !new_exe.is_file() {
        return Err(format!("Update-Datei fehlt: {}", new_exe.display()));
    }
    spawn_cmd_script(&replace_batch_text(new_exe, dest))
}

/// If a staged `TypeHack.exe.new` is waiting, start the replace helper and the caller should exit.
pub fn apply_pending_and_should_exit() -> bool {
    if is_dev_build() {
        return false;
    }
    let pending = pending_new_exe();
    if !pending.is_file() {
        return false;
    }
    launch_replace_helper(&pending, &installed_exe()).is_ok()
}

pub fn http_get_text(url: &str) -> Result<String, String> {
    let resp = agent()
        .get(url)
        .set("Accept", "application/vnd.github+json, application/json, text/plain")
        .call()
        .map_err(|e| format!("HTTP: {e}"))?;
    resp.into_string().map_err(|e| e.to_string())
}

pub fn http_get_bytes(url: &str) -> Result<Vec<u8>, String> {
    let resp = agent().get(url).call().map_err(|e| format!("HTTP: {e}"))?;
    let mut buf = Vec::new();
    resp.into_reader()
        .read_to_end(&mut buf)
        .map_err(|e| e.to_string())?;
    Ok(buf)
}

pub fn http_download(url: &str, dest: &Path) -> Result<(), String> {
    let resp = agent().get(url).call().map_err(|e| format!("Download: {e}"))?;
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let mut file = fs::File::create(dest).map_err(|e| e.to_string())?;
    std::io::copy(&mut resp.into_reader(), &mut file).map_err(|e| e.to_string())?;
    Ok(())
}

fn agent() -> ureq::Agent {
    ureq::AgentBuilder::new()
        .timeout(std::time::Duration::from_secs(120))
        .user_agent(USER_AGENT)
        .build()
}

pub fn download_and_stage(info: &UpdateInfo) -> Result<PathBuf, String> {
    if info.url.is_empty() {
        return Err("Kein Download im Release.".into());
    }
    let tmp = std::env::temp_dir().join(&info.name);
    http_download(&info.url, &tmp)?;
    if !info.sha256.is_empty() {
        let got = sha256_file(&tmp)?;
        if got != info.sha256 {
            let _ = fs::remove_file(&tmp);
            return Err("Checksum mismatch — Update abgebrochen.".into());
        }
    }
    let lower = info.name.to_lowercase();
    if lower.contains("setup") {
        Ok(tmp)
    } else {
        let dest = pending_new_exe();
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent).ok();
        }
        fs::copy(&tmp, &dest).map_err(|e| e.to_string())?;
        Ok(dest)
    }
}

pub fn apply_now(staged: &Path, restart: &Path) -> Result<(), String> {
    let name = staged
        .file_name()
        .map(|s| s.to_string_lossy().to_lowercase())
        .unwrap_or_default();
    if name.contains("setup") {
        launch_installer(staged, Some(restart))
    } else {
        launch_replace_helper(staged, restart)
    }
}

/// Check GitHub; `Ok(Some)` only when a newer release exists.
pub fn check_for_update() -> Result<Option<UpdateInfo>, String> {
    let Some(info) = fetch_latest()? else {
        return Ok(None);
    };
    if !is_newer(&info.version, VERSION) {
        return Ok(None);
    }
    Ok(Some(info))
}

pub fn background_update_once() -> Result<Option<(UpdateInfo, PathBuf)>, String> {
    let Some(info) = check_for_update()? else {
        return Ok(None);
    };
    let staged = download_and_stage(&info)?;
    Ok(Some((info, staged)))
}