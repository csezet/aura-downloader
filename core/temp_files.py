"""Owned temporary directories. Live sessions are protected by process locks."""
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QLockFile

OWNER_FILE = ".aura_owner.json"
LOCK_FILE = ".aura_active.lock"
_cache_session = None
_cache_mutex = threading.RLock()


def cache_root():
    return Path(tempfile.gettempdir()) / "AuraDownloader" / "cache"


def _directory_lock(path):
    lock = QLockFile(str(Path(path) / LOCK_FILE))
    lock.setStaleLockTime(0)
    return lock


class OwnedDirectory:
    def __init__(self, parent, prefix, kind):
        parent = Path(parent).resolve()
        parent.mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix=prefix, dir=parent)).resolve()
        self.kind = kind
        self.lock = _directory_lock(self.path)
        if not self.lock.tryLock(0):
            shutil.rmtree(self.path, ignore_errors=True)
            raise OSError("Не удалось защитить временный каталог.")
        try:
            with (self.path / OWNER_FILE).open("w", encoding="utf-8") as stream:
                json.dump({"app": "aura-downloader", "version": 1,
                           "kind": kind, "path": str(self.path)}, stream)
        except Exception:
            self.lock.unlock()
            shutil.rmtree(self.path, ignore_errors=True)
            raise

    def release(self):
        self.lock.unlock()


def owned_directory(path, kind):
    path = Path(path)
    try:
        if os.path.normcase(os.path.abspath(path)) != os.path.normcase(os.path.realpath(path)):
            return False
        with (path / OWNER_FILE).open("r", encoding="utf-8") as stream:
            marker = json.load(stream)
        return (isinstance(marker, dict) and marker.get("app") == "aura-downloader"
                and marker.get("version") == 1 and marker.get("kind") == kind
                and os.path.normcase(marker.get("path", "")) == os.path.normcase(str(path.resolve())))
    except (OSError, ValueError, TypeError):
        return False


def directory_is_active(path, kind="staging"):
    if not owned_directory(path, kind):
        return False
    lock = _directory_lock(path)
    if not lock.tryLock(0):
        return True
    lock.unlock()
    return False


def remove_owned_directory(path, parent, kind):
    path, parent = Path(path), Path(parent).resolve()
    if path.resolve().parent != parent or not owned_directory(path, kind):
        return False
    lock = _directory_lock(path)
    if not lock.tryLock(0):
        return False
    try:
        target = path.resolve()
        if target.parent != parent:
            return False
        # Remove payload files/subdirs before removing the ownership marker so a
        # partial failure (e.g. locked file) preserves ownership for future cleanup.
        for child in list(target.iterdir()):
            if child.name in (OWNER_FILE, LOCK_FILE):
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        # All payload is gone; release lock and remove marker + directory last.
        lock.unlock()
        (target / LOCK_FILE).unlink(missing_ok=True)
        (target / OWNER_FILE).unlink(missing_ok=True)
        target.rmdir()
        return True
    except OSError:
        return False
    finally:
        lock.unlock()


def get_cache_dir():
    global _cache_session
    with _cache_mutex:
        if _cache_session is None:
            _cache_session = OwnedDirectory(cache_root(), "session_", "cache")
        return str(_cache_session.path)


def release_cache_session():
    global _cache_session
    with _cache_mutex:
        if _cache_session is not None:
            _cache_session.release()
            _cache_session = None
