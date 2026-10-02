"""Frozen distributions update as a whole through the project's GitHub releases."""
import re
import requests

from core.version import APP_VERSION, REPOSITORY, RELEASES_URL


def version_tuple(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(value))
    if not match:
        raise ValueError("Неподдерживаемый номер версии релиза.")
    return tuple(int(part) for part in match.groups())


def check_latest_release(current_version=APP_VERSION):
    with requests.get(f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
                      headers={"Accept": "application/vnd.github+json", "User-Agent": "AuraDownloader"},
                      timeout=(5, 15)) as response:
        if response.status_code == 404:
            return {"available": False, "message": "Опубликованных релизов пока нет.", "url": RELEASES_URL}
        response.raise_for_status()
        release = response.json()
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        raise ValueError("GitHub вернул некорректный стабильный релиз.")
    tag = release.get("tag_name", "")
    available = version_tuple(tag) > version_tuple(current_version)
    assets = release.get("assets", [])
    has_windows_build = isinstance(assets, list) and any(
        isinstance(asset, dict) and re.fullmatch(r"AuraDownloader-v?\d+\.\d+\.\d+-windows-x64\.zip", asset.get("name", ""))
        for asset in assets)
    if available and not has_windows_build:
        return {"available": False, "message": f"Релиз {tag}: сборка Windows ещё не опубликована.", "url": RELEASES_URL}
    return {"available": available, "version": tag, "url": RELEASES_URL,
            "message": f"Доступна версия {tag}. Скачайте архив и распакуйте в новую папку." if available
                       else f"Новых версий нет. Установлена Aura Downloader {current_version}."}
