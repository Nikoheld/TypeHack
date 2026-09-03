#!/usr/bin/env python3
"""GitHub-release auto-updater for TypeHack."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO = "Nikoheld/TypeHack"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
VERSION_JSON_URL = f"https://raw.githubusercontent.com/{REPO}/main/version.json"
SETUP_NAME = re.compile(r"TypeHack-Setup-.*\.exe$", re.I)


def parse_version(tag: str) -> tuple[int, ...]:
    raw = str(tag or "").strip()
    if raw.lower().startswith("v"):
        raw = raw[1:]
    parts = []
    for bit in re.split(r"[.+-]", raw):
        if bit.isdigit():
            parts.append(int(bit))
        elif bit:
            break
    return tuple(parts or (0,))


def is_newer(remote: str, local: str) -> bool:
    a, b = parse_version(remote), parse_version(local)
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


def _request_json(url: str, timeout: int = 20) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "TypeHack-Updater",
            "Accept": "application/vnd.github+json, application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def pick_setup_asset(release: dict) -> dict | None:
    assets = release.get("assets") or []
    setup = [a for a in assets if SETUP_NAME.search(str(a.get("name") or ""))]
    if not setup:
        return None
    setup.sort(key=lambda a: int(a.get("size") or 0), reverse=True)
    return setup[0]


def digest_from_asset(asset: dict) -> str:
    digest = str(asset.get("digest") or "")
    if digest.lower().startswith("sha256:"):
        return digest.split(":", 1)[1].strip().lower()
    return ""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_latest(include_prerelease: bool = False) -> dict | None:
    try:
        data = _request_json(RELEASES_URL)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        data = None
    except urllib.error.URLError:
        data = None
    if isinstance(data, dict) and data.get("tag_name"):
        if data.get("prerelease") and not include_prerelease:
            return None
        asset = pick_setup_asset(data)
        if asset and asset.get("browser_download_url"):
            return {
                "version": str(data.get("tag_name") or "").lstrip("v"),
                "url": asset["browser_download_url"],
                "name": asset.get("name") or "TypeHack-Setup.exe",
                "sha256": digest_from_asset(asset),
                "notes": str(data.get("body") or "")[:2000],
            }
    meta = _request_json(VERSION_JSON_URL)
    if not isinstance(meta, dict):
        return None
    url = str(meta.get("installer_url") or "").strip()
    if not url:
        return {
            "version": str(meta.get("version") or ""),
            "url": "",
            "name": "",
            "sha256": str(meta.get("sha256") or ""),
            "notes": str(meta.get("notes") or ""),
        }
    return {
        "version": str(meta.get("version") or ""),
        "url": url,
        "name": Path(url).name or "TypeHack-Setup.exe",
        "sha256": str(meta.get("sha256") or ""),
        "notes": str(meta.get("notes") or ""),
    }


def download_installer(url: str, dest: Path, progress=None, timeout: int = 120) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "TypeHack-Updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, part.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    part.replace(dest)
    return dest


def launch_installer(setup: Path, restart_exe: Path | None = None) -> None:
    setup = setup.resolve()
    if os.name != "nt":
        return
    wait = f'start "" /wait "{setup}" /VERYSILENT /NORESTART /CLOSEAPPLICATIONS /SUPPRESSMSGBOXES'
    if restart_exe:
        wait += f' && start "" "{restart_exe}"'
    subprocess.Popen(["cmd", "/c", wait], close_fds=True)


def apply_update(info: dict, progress=None) -> Path:
    url = str(info.get("url") or "")
    if not url:
        raise RuntimeError("Kein Installer in diesem Release.")
    name = str(info.get("name") or "TypeHack-Setup.exe")
    dest = Path(tempfile.gettempdir()) / name
    download_installer(url, dest, progress=progress)
    expected = str(info.get("sha256") or "").lower()
    if expected:
        got = sha256_file(dest)
        if got != expected:
            dest.unlink(missing_ok=True)
            raise RuntimeError("Checksum mismatch — Update abgebrochen.")
    return dest
