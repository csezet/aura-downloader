import copy
import os
import tempfile
import threading
from pathlib import Path

from core.persistence import load_json, save_json

DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Downloads" / "AuraDownloads")
DEFAULT_SETTINGS = {
    "download_dir": DEFAULT_DOWNLOAD_DIR,
    "known_download_dirs": [DEFAULT_DOWNLOAD_DIR],
    "recovery_registry": [],
    "auto_paste": False,
    "quality_preset": "best",
    "audio_format": "mp3",
    "audio_quality": "320",
    "acrylic_blur": True,
    "glass_opacity": 0.45,
    "browser_cookies": "none",
    "sound_notification": True,
    "notifications_enabled": True,
    "download_subtitles": False,
    "subtitles_langs": ["ru", "en"],
}
CONFIG_DIR = Path.home() / ".aura_downloader"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _valid_path(value):
    return isinstance(value, str) and bool(value.strip()) and "\0" not in value and os.path.isabs(value)


def _validate_settings(data):
    if not isinstance(data, dict):
        raise ValueError("Настройки должны быть объектом JSON.")
    result = copy.deepcopy(DEFAULT_SETTINGS)
    choices = {"audio_format": {"mp3", "flac", "m4a", "opus", "wav"},
               "quality_preset": {"best", "custom", "audio_only", "video_only", "gif", "discord_8mb"},
               "browser_cookies": {"none", "chrome", "edge", "firefox", "brave", "opera", "vivaldi"}}
    for key, default in DEFAULT_SETTINGS.items():
        value = data.get(key, default)
        if key == "download_dir":
            if _valid_path(value):
                result[key] = value
        elif key in ("known_download_dirs", "recovery_registry"):
            if isinstance(value, list):
                result[key] = list(dict.fromkeys(item for item in value if _valid_path(item)))
        elif key == "subtitles_langs":
            if isinstance(value, list):
                langs = [item for item in value if isinstance(item, str) and item.strip()]
                result[key] = list(dict.fromkeys(langs)) or copy.deepcopy(default)
        elif key == "glass_opacity":
            if type(value) in (int, float) and 0 <= value <= 1:
                result[key] = value
        elif key in choices:
            if isinstance(value, str) and value in choices[key]:
                result[key] = value
        elif key == "audio_quality":
            if isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 3 and 0 <= int(value) <= 512:
                result[key] = value
        elif type(value) is type(default):
            result[key] = value
    return result


def _ensure_writable_directory(directory):
    os.makedirs(directory, exist_ok=True)
    with tempfile.TemporaryFile(dir=directory):
        pass


class SettingsManager:
    def __init__(self):
        self._lock = threading.RLock()
        self.last_error = None
        self.startup_warning = None
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.load()
        requested = self.get("download_dir")
        candidates = list(dict.fromkeys([requested, DEFAULT_DOWNLOAD_DIR, str(CONFIG_DIR / "downloads")]))
        for directory in candidates:
            try:
                _ensure_writable_directory(directory)
            except (OSError, ValueError) as exc:
                self.last_error = str(exc)
                continue
            self.settings["download_dir"] = directory
            if directory != requested:
                self.startup_warning = f"Папка загрузок недоступна: {requested}. Используется: {directory}"
            break
        else:
            self.startup_warning = "Папка загрузок недоступна. Выберите доступную папку в настройках."
        self._remember_directory(self.settings["download_dir"])

    def load(self):
        with self._lock:
            self.settings, errors = load_json(CONFIG_FILE, _validate_settings, copy.deepcopy(DEFAULT_SETTINGS))
            if errors:
                self.startup_warning = "Не удалось прочитать настройки. Загружена резервная копия или значения по умолчанию."
                self.last_error = "; ".join(errors)
            self._remember_directory(DEFAULT_DOWNLOAD_DIR)
            self._remember_directory(self.settings["download_dir"])

    def save(self):
        with self._lock:
            try:
                save_json(CONFIG_FILE, self.settings, _validate_settings)
                self.last_error = None
                return True
            except (OSError, ValueError, TypeError) as exc:
                self.last_error = str(exc)
                return False

    def get(self, key, default=None):
        with self._lock:
            return copy.deepcopy(self.settings.get(key, default if default is not None else DEFAULT_SETTINGS.get(key)))

    def _remember_directory(self, directory):
        known = self.settings["known_download_dirs"]
        if directory not in known:
            known.append(directory)

    def set(self, key, value):
        with self._lock:
            validated = _validate_settings({key: value})
            if (key not in DEFAULT_SETTINGS or validated[key] != value
                    or (type(DEFAULT_SETTINGS[key]) is bool and type(value) is not bool)):
                raise ValueError(f"Некорректное значение настройки: {key}")
            if key == "download_dir":
                _ensure_writable_directory(value)
            previous = copy.deepcopy(self.settings)
            self.settings[key] = copy.deepcopy(value)
            if key == "download_dir":
                self._remember_directory(value)
            if self.save():
                return True
            self.settings = previous
            return False

    def add_known_download_dir(self, directory):
        if _valid_path(directory):
            with self._lock:
                self._remember_directory(directory)
                return self.save()

    def register_recovery_session(self, staging_dir):
        if _valid_path(staging_dir):
            with self._lock:
                registry = self.settings["recovery_registry"]
                if staging_dir not in registry:
                    registry.append(staging_dir)
                    return self.save()

    def unregister_recovery_session(self, staging_dir):
        with self._lock:
            registry = self.settings["recovery_registry"]
            if staging_dir in registry:
                registry.remove(staging_dir)
                return self.save()


settings = SettingsManager()
