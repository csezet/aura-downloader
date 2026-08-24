import os
import json
import time
from pathlib import Path
from core.settings import CONFIG_DIR

HISTORY_FILE = CONFIG_DIR / "history.json"

class HistoryManager:
    def __init__(self):
        self.history = []
        self.load()

    def load(self):
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception as e:
                print(f"Error loading history: {e}")
                self.history = []

    def save(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history[:100], f, indent=4, ensure_ascii=False)  # Keep last 100 entries
        except Exception as e:
            print(f"Error saving history: {e}")

    def add_entry(self, title, url, file_path, format_type, size_bytes=0, thumbnail=None):
        entry = {
            "id": int(time.time() * 1000),
            "title": title,
            "url": url,
            "file_path": file_path,
            "format_type": format_type,
            "size_bytes": size_bytes,
            "thumbnail": thumbnail,
            "timestamp": int(time.time()),
            "file_exists": os.path.exists(file_path) if file_path else False
        }
        self.history.insert(0, entry)
        self.save()
        return entry

    def get_all(self):
        # Update file_exists status
        for item in self.history:
            item["file_exists"] = os.path.exists(item.get("file_path", ""))
        return self.history

    def clear(self):
        self.history = []
        self.save()

history = HistoryManager()
