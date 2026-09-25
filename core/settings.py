import os
import json
from pathlib import Path

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
    "glass_opacity": 0.45,     # 0.45 for real desktop visibility through main window
    "browser_cookies": "none",
    "sound_notification": True,
    "notifications_enabled": True,
    "download_subtitles": False,
    "subtitles_langs": ["ru", "en"],
}

CONFIG_DIR = Path.home() / ".aura_downloader"
CONFIG_FILE = CONFIG_DIR / "config.json"

class SettingsManager:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.settings = DEFAULT_SETTINGS.copy()
        self.load()
        os.makedirs(self.get("download_dir"), exist_ok=True)

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.settings.update(data)
            except Exception as e:
                print(f"Error loading settings: {e}")
        # Ensure default dirs are recorded in known_download_dirs
        known = list(self.settings.get("known_download_dirs", []))
        cur = self.settings.get("download_dir")
        if cur and cur not in known:
            known.append(cur)
        if DEFAULT_DOWNLOAD_DIR not in known:
            known.append(DEFAULT_DOWNLOAD_DIR)
        self.settings["known_download_dirs"] = known

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get(self, key, default=None):
        return self.settings.get(key, default if default is not None else DEFAULT_SETTINGS.get(key))

    def set(self, key, value):
        self.settings[key] = value
        if key == "download_dir" and value:
            known = list(self.settings.get("known_download_dirs", []))
            if value not in known:
                known.append(value)
                self.settings["known_download_dirs"] = known
        self.save()

    def add_known_download_dir(self, directory: str):
        if not directory:
            return
        known = list(self.settings.get("known_download_dirs", []))
        if directory not in known:
            known.append(directory)
            self.settings["known_download_dirs"] = known
            self.save()

    def register_recovery_session(self, staging_dir: str):
        if not staging_dir:
            return
        registry = list(self.settings.get("recovery_registry", []))
        if staging_dir not in registry:
            registry.append(staging_dir)
            self.settings["recovery_registry"] = registry
            self.save()

    def unregister_recovery_session(self, staging_dir: str):
        if not staging_dir:
            return
        registry = list(self.settings.get("recovery_registry", []))
        if staging_dir in registry:
            registry.remove(staging_dir)
            self.settings["recovery_registry"] = registry
            self.save()

settings = SettingsManager()
