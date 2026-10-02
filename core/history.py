import copy
import math
import os
import threading
import time

from core.settings import CONFIG_DIR
from core.persistence import load_json, save_json

HISTORY_FILE = CONFIG_DIR / "history.json"
HISTORY_LIMIT = 100


def _validate_history(data):
    if not isinstance(data, list):
        raise ValueError("История должна быть массивом JSON.")
    entries = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("file_path"), str) or "\0" in item["file_path"]:
            continue
        entry = dict(item)
        for key, fallback in (("title", "Без названия"), ("url", ""), ("format_type", "MP4")):
            if not isinstance(entry.get(key), str):
                entry[key] = fallback
        for key in ("id", "timestamp", "size_bytes"):
            value = entry.get(key, 0)
            valid = type(value) is int or (type(value) is float and math.isfinite(value))
            entry[key] = value if valid and value >= 0 else 0
        if not isinstance(entry.get("thumbnail"), str):
            entry["thumbnail"] = None
        entry["file_exists"] = os.path.isfile(entry["file_path"])
        entries.append(entry)
    if data and not entries:
        raise ValueError("История не содержит корректных записей.")
    return entries[:HISTORY_LIMIT]


class HistoryManager:
    def __init__(self):
        self._lock = threading.RLock()
        self.last_error = None
        self.history = []
        self.load()

    def load(self):
        with self._lock:
            self.history, errors = load_json(HISTORY_FILE, _validate_history, [])
            self.last_error = "; ".join(errors) if errors else None

    def save(self):
        with self._lock:
            try:
                save_json(HISTORY_FILE, self.history[:HISTORY_LIMIT], _validate_history)
                self.last_error = None
                return True
            except (OSError, ValueError, TypeError) as exc:
                self.last_error = str(exc)
                return False

    def add_entry(self, title, url, file_path, format_type, size_bytes=0, thumbnail=None):
        with self._lock:
            entry = _validate_history([{
                "id": time.time_ns(), "title": title, "url": url,
                "file_path": str(file_path) if file_path else "", "format_type": format_type,
                "size_bytes": size_bytes, "thumbnail": thumbnail, "timestamp": int(time.time()),
            }])[0]
            self.history.insert(0, entry)
            del self.history[HISTORY_LIMIT:]
            self.save()
            return copy.deepcopy(entry)

    def get_all(self):
        with self._lock:
            for item in self.history:
                item["file_exists"] = os.path.isfile(item["file_path"])
            return copy.deepcopy(self.history)

    def clear(self):
        with self._lock:
            self.history = []
            return self.save()


history = HistoryManager()
