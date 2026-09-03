import os
import json
from pathlib import Path

DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Downloads" / "AuraDownloads")

DEFAULT_SETTINGS = {
    "download_dir": DEFAULT_DOWNLOAD_DIR,
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
        self.save()

settings = SettingsManager()
