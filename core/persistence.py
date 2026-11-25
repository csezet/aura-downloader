"""Atomic JSON storage with a last known good backup."""
import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path


STORAGE_LOCK = threading.RLock()


def load_json(path, validate, default):
    path = Path(path)
    errors = []
    with STORAGE_LOCK:
        for candidate in (path, path.with_suffix(path.suffix + ".bak")):
            try:
                with candidate.open("r", encoding="utf-8") as stream:
                    data = validate(json.load(stream))
                return data, errors
            except FileNotFoundError:
                continue
            except (OSError, ValueError, TypeError) as exc:
                errors.append(f"{candidate.name}: {exc}")
    return default, errors


def _replace_bytes(path, payload, retries=4, retry_delay=0.02):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(retries):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt + 1 >= retries:
                    raise
                time.sleep(retry_delay * (attempt + 1))
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_json(path, data, validate):
    path = Path(path)
    validated = validate(data)
    payload = json.dumps(validated, indent=4, ensure_ascii=False, allow_nan=False).encode("utf-8")
    with STORAGE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            previous = path.read_bytes()
            try:
                validate(json.loads(previous))
            except (ValueError, TypeError):
                damaged = path.with_suffix(path.suffix + ".corrupt")
                if not damaged.exists():
                    shutil.copy2(path, damaged)
            else:
                _replace_bytes(path.with_suffix(path.suffix + ".bak"), previous)
        else:
            _replace_bytes(path.with_suffix(path.suffix + ".bak"), payload)
        _replace_bytes(path, payload)
