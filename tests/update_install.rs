//! Install, Edge-driver URLs, and GitHub auto-updater — no network.

use std::fs;
use std::path::PathBuf;

use typehack::driver::{latest_release_url, looks_like_version, zip_url_for, DRIVER_NAME, MIRROR};
use typehack::install::install_dir;
use typehack::update::{
    digest_from_asset, installer_batch_text, pick_setup_asset, pick_update_asset, replace_batch_text, sha256_file,
};
use typehack::{is_newer, parse_version, VERSION, WINDOW_TITLE};

#[test]
fn version_is_3_1_0() {
    assert_eq!(VERSION, "3.1.0");
    assert_eq!(WINDOW_TITLE, "TypeHack 3.1.0");
}

#[test]
fn parse_and_compare_versions() {
    assert_eq!(parse_version("v2.2.0"), vec![2, 2, 0]);
    assert_eq!(parse_version("3.1.0"), vec![3, 1, 0]);
    assert!(is_newer("2.2.1", "2.2.0"));
    assert!(!is_newer("2.2.0", "2.2.0"));
    assert!(!is_newer("2.1.9", "2.2.0"));
    assert!(is_newer("3.1.0", "3.0.2"));
}

#[test]
fn pick_setup_asset_prefers_installer() {
    let release = serde_json::json!({
        "tag_name": "v3.1.0",
        "body": "notes",
        "assets": [
            {"name": "notes.txt", "size": 10, "browser_download_url": "http://x/notes"},
            {
                "name": "TypeHack-Setup-3.1.0.exe",
                "size": 40000000,
                "browser_download_url": "http://x/setup.exe",
                "digest": "sha256:abc"
            },
            {
                "name": "TypeHack-3.1.0.exe",
                "size": 8000000,
                "browser_download_url": "http://x/portable.exe"
            }
        ]
    });
    let asset = pick_setup_asset(&release).expect("setup");
    assert_eq!(asset["name"], "TypeHack-Setup-3.1.0.exe");
    assert_eq!(digest_from_asset(&asset), "abc");
    let info = pick_update_asset(&release).expect("info");
    assert_eq!(info.name, "TypeHack-Setup-3.1.0.exe");
    assert_eq!(info.version, "3.1.0");
    assert_eq!(info.sha256, "abc");
}

#[test]
fn pick_update_falls_back_to_portable_exe() {
    let release = serde_json::json!({
        "tag_name": "v3.1.0",
        "assets": [{
            "name": "TypeHack-3.1.0.exe",
            "size": 8000000,
            "browser_download_url": "http://x/portable.exe"
        }]
    });
    let info = pick_update_asset(&release).expect("portable");
    assert_eq!(info.name, "TypeHack-3.1.0.exe");
    assert!(!info.name.to_lowercase().contains("setup"));
}

#[test]
fn sha256_of_bytes() {
    let dir = std::env::temp_dir();
    let path = dir.join("typehack-sha256-test.bin");
    fs::write(&path, b"typehack").unwrap();
    let got = sha256_file(&path).unwrap();
    assert_eq!(got.len(), 64);
    assert_eq!(got, sha256_file(&path).unwrap());
    let _ = fs::remove_file(path);
}

#[test]
fn installer_batch_never_uses_empty_start_title() {
    let setup = PathBuf::from(r"C:\Users\Niko\AppData\Local\Temp\TypeHack-Setup-2.3.1.exe");
    let restart = PathBuf::from(r"C:\Users\Niko\AppData\Local\TypeHack\TypeHack.exe");
    let text = installer_batch_text(&setup, Some(&restart));
    assert!(!text.contains("start \"\""));
    assert!(!text.contains("start ''"));
    assert!(text.contains("start \"TypeHack-Setup\" /wait"));
    assert!(text.contains("start \"TypeHack\""));
    assert!(text.contains(&setup.display().to_string()));
    assert!(text.contains("/VERYSILENT"));
}

#[test]
fn replace_batch_copies_then_restarts() {
    let new = PathBuf::from(r"C:\Users\Niko\AppData\Local\TypeHack\TypeHack.exe.new");
    let dest = PathBuf::from(r"C:\Users\Niko\AppData\Local\TypeHack\TypeHack.exe");
    let text = replace_batch_text(&new, &dest);
    assert!(!text.contains("start \"\""));
    assert!(text.contains("copy /Y"));
    assert!(text.contains("start \"TypeHack\""));
    assert!(text.contains(&new.display().to_string()));
}

#[test]
fn install_dir_is_localappdata_typehack() {
    let dir = install_dir();
    assert!(dir.ends_with("TypeHack"));
    if let Ok(local) = std::env::var("LOCALAPPDATA") {
        assert_eq!(dir, PathBuf::from(local).join("TypeHack"));
    }
}

#[test]
fn driver_urls_match_microsoft_mirror() {
    assert!(looks_like_version("131.0.2903.112"));
    assert!(!looks_like_version("msedge"));
    let url = zip_url_for("131.0.2903.112");
    assert!(url.starts_with(MIRROR));
    assert!(url.ends_with("/edgedriver_win64.zip"));
    assert!(url.contains("131.0.2903.112"));
    assert_eq!(
        latest_release_url("131"),
        format!("{MIRROR}/LATEST_RELEASE_131_WINDOWS")
    );
    assert_eq!(DRIVER_NAME, "msedgedriver.exe");
}

#[test]
fn ui_exposes_auto_update() {
    let all = typehack::ui_labels::all_controls();
    assert!(all.contains(&"Automatisch aktualisieren"));
}