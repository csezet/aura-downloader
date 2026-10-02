import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.history import HistoryManager, _validate_history
from core.media_converter import cleanup_aura_temp_files, get_ffmpeg_path, run_ffmpeg_cancellable, get_recovery_sessions
from core.settings import SettingsManager, DEFAULT_SETTINGS, settings
from core.temp_files import OwnedDirectory, remove_owned_directory
from core.workers import start_worker, worker_registry
from ui.main_window import MainWindow
from ui.worker_dialog import WorkerDialog


app = QApplication.instance() or QApplication([])


class IsolatedTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="aura_stage1_"))).resolve()
        self.output = self.root / "output"
        self.output.mkdir()
        self.profile = self.root / "profile"
        self.profile.mkdir()
        self.cache = self.root / "cache"
        defaults = copy.deepcopy(DEFAULT_SETTINGS)
        defaults.update(download_dir=str(self.output), known_download_dirs=[str(self.output)])
        self.stack.enter_context(patch("core.settings.CONFIG_DIR", self.profile))
        self.stack.enter_context(patch("core.settings.CONFIG_FILE", self.profile / "config.json"))
        self.stack.enter_context(patch("core.settings.DEFAULT_DOWNLOAD_DIR", str(self.output)))
        self.stack.enter_context(patch("core.settings.DEFAULT_SETTINGS", defaults))
        self.stack.enter_context(patch("core.history.HISTORY_FILE", self.profile / "history.json"))
        self.stack.enter_context(patch("core.media_converter.cache_root", return_value=self.cache))
        original_get = settings.get
        self.stack.enter_context(patch.object(settings, "get", side_effect=lambda key, default=None:
                                              str(self.output) if key == "download_dir" else original_get(key, default)))
        worker_registry().stopping = False

    def tearDown(self):
        registry = worker_registry()
        registry.cancel_all()
        for worker in list(registry.workers):
            self.assertTrue(worker.wait(3000), "Background task survived test teardown")
        app.processEvents()
        registry.stopping = False
        self.stack.close()


class TestSafeCleanup(IsolatedTest):
    def test_names_never_authorize_deleting_user_files_or_legacy_directories(self):
        files = []
        for parent in (self.output, self.root):
            for name in ("sample_user.mp4", "aura_proxy_user.mp4", "aura_thumb_user.jpg", "aura_crop_user.png"):
                path = parent / name
                path.write_bytes(b"user data")
                files.append(path)
        legacy = self.output / ".aura_staging_user"
        legacy.mkdir()
        (legacy / "unfinished.part").write_bytes(b"user data")
        cleanup_aura_temp_files(0, extra_dirs=[str(self.output), str(self.root)])
        self.assertTrue(all(path.read_bytes() == b"user data" for path in files))
        self.assertTrue(legacy.is_dir())

    def test_live_staging_is_protected_then_abandoned_staging_is_cleaned(self):
        session = OwnedDirectory(self.output, ".aura_staging_", "staging")
        (session.path / "video.part").write_bytes(b"partial")
        try:
            cleanup_aura_temp_files(0, extra_dirs=[str(self.output)])
            self.assertTrue(session.path.is_dir())
        finally:
            session.release()
        cleanup_aura_temp_files(0, extra_dirs=[str(self.output)])
        self.assertFalse(session.path.exists())

    def test_cache_lock_and_recovery_protect_completed_files(self):
        cache = OwnedDirectory(self.cache, "session_", "cache")
        cached_file = cache.path / "preview.mp4"
        cached_file.write_bytes(b"preview")
        recovery = OwnedDirectory(self.output, ".aura_staging_", "staging")
        (recovery.path / "finished.mp4").write_bytes(b"completed")
        recovery.release()
        try:
            cleanup_aura_temp_files(0, extra_dirs=[str(self.output)])
            self.assertTrue(cached_file.exists())
            self.assertTrue((recovery.path / "finished.mp4").exists())
        finally:
            cache.release()
        cleanup_aura_temp_files(0, extra_dirs=[str(self.output)])
        self.assertFalse(cache.path.exists())
        self.assertTrue(recovery.path.exists())

    def test_live_completed_media_is_not_offered_for_recovery_or_manual_deletion(self):
        session = OwnedDirectory(self.output, ".aura_staging_", "staging")
        (session.path / "finished.mp4").write_bytes(b"completed")
        try:
            sessions = get_recovery_sessions([str(self.output)])
            self.assertNotIn(str(session.path), [item["path"] for item in sessions])
        finally:
            session.release()
        sessions = get_recovery_sessions([str(self.output)])
        self.assertIn(str(session.path), [item["path"] for item in sessions])

    def test_other_process_cannot_delete_a_live_session(self):
        session = OwnedDirectory(self.output, ".aura_staging_", "staging")
        code = "import sys; from core.temp_files import remove_owned_directory; print(remove_owned_directory(sys.argv[1], sys.argv[2], 'staging'))"
        try:
            child = subprocess.run([sys.executable, "-c", code, str(session.path), str(self.output)],
                                   cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                   text=True, timeout=10, creationflags=0x08000000)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertEqual(child.stdout.strip(), "False")
            self.assertTrue(session.path.exists())
        finally:
            session.release()
        self.assertTrue(remove_owned_directory(session.path, self.output, "staging"))

    def test_deletion_rejects_a_target_outside_the_expected_parent(self):
        session = OwnedDirectory(self.root, ".aura_staging_", "staging")
        session.release()
        self.assertFalse(remove_owned_directory(session.path, self.output, "staging"))
        self.assertTrue(session.path.exists())


class TestResilientStorage(IsolatedTest):
    def test_truncated_config_recovers_backup_and_preserves_damaged_input(self):
        manager = SettingsManager()
        self.assertTrue(manager.set("audio_format", "flac"))
        self.assertTrue(manager.set("audio_format", "opus"))
        config = self.profile / "config.json"
        config.write_text('{"audio_format":', encoding="utf-8")
        restored = SettingsManager()
        self.assertEqual(restored.get("audio_format"), "flac")
        self.assertIsNotNone(restored.startup_warning)
        self.assertTrue(restored.set("audio_format", "wav"))
        self.assertEqual((self.profile / "config.json.corrupt").read_text(encoding="utf-8"), '{"audio_format":')
        self.assertEqual(json.loads((self.profile / "config.json.bak").read_text(encoding="utf-8"))["audio_format"], "flac")

    def test_failed_atomic_replace_preserves_previous_json_and_removes_temporary_files(self):
        manager = SettingsManager()
        manager.set("audio_format", "flac")
        config = self.profile / "config.json"
        previous = config.read_bytes()
        replace = os.replace
        def fail_primary(source, target):
            if Path(target) == config:
                raise PermissionError("simulated locked config")
            return replace(source, target)
        with patch("core.persistence.os.replace", side_effect=fail_primary):
            self.assertFalse(manager.set("audio_format", "opus"))
        self.assertEqual(config.read_bytes(), previous)
        self.assertEqual(manager.get("audio_format"), "flac")
        self.assertIsNotNone(manager.last_error)
        self.assertFalse(list(self.profile.glob("*.tmp")))

    def test_invalid_types_are_sanitized_and_defaults_are_not_shared(self):
        config = self.profile / "config.json"
        config.write_text(json.dumps({"glass_opacity": "transparent", "auto_paste": 1,
                                     "known_download_dirs": [None, 12], "recovery_registry": {},
                                     "audio_format": [], "download_dir": 12}), encoding="utf-8")
        manager = SettingsManager()
        self.assertEqual(manager.get("glass_opacity"), 0.45)
        self.assertIs(manager.get("auto_paste"), False)
        self.assertEqual(manager.get("recovery_registry"), [])
        external = manager.get("known_download_dirs")
        external.append("not stored")
        self.assertNotIn("not stored", manager.get("known_download_dirs"))
        with self.assertRaises(ValueError):
            manager.set("auto_paste", 0)

    def test_unavailable_saved_directory_falls_back_and_invalid_changes_keep_current_directory(self):
        blocked = self.root / "blocked"
        blocked.write_text("a file blocks directory creation", encoding="utf-8")
        (self.profile / "config.json").write_text(json.dumps({"download_dir": str(blocked)}), encoding="utf-8")
        manager = SettingsManager()
        self.assertEqual(manager.get("download_dir"), str(self.output))
        self.assertIn(str(blocked), manager.get("known_download_dirs"))
        self.assertIsNotNone(manager.startup_warning)
        with self.assertRaises(OSError):
            manager.set("download_dir", str(blocked))
        self.assertEqual(manager.get("download_dir"), str(self.output))

    def test_concurrent_registry_updates_are_not_lost(self):
        manager = SettingsManager()
        paths = [str(self.root / f"recovery_{index}") for index in range(24)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(manager.register_recovery_session, paths))
        self.assertEqual(set(manager.get("recovery_registry")), set(paths))
        on_disk = json.loads((self.profile / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(set(on_disk["recovery_registry"]), set(paths))

    def test_history_recovers_backup_and_rejects_malformed_records(self):
        manager = HistoryManager()
        manager.add_entry("First", "url", "first.mp4", "MP4")
        manager.add_entry("Second", "url", "second.mp4", "MP4")
        (self.profile / "history.json").write_text("{", encoding="utf-8")
        restored = HistoryManager()
        self.assertEqual([item["title"] for item in restored.get_all()], ["First"])
        normalized = _validate_history([None, {"file_path": 42}, {"file_path": "x.mp4", "title": None, "size_bytes": "large", "format_type": None}])
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["format_type"], "MP4")
        self.assertEqual(normalized[0]["size_bytes"], 0)

    def test_concurrent_history_writes_keep_valid_json_and_enforce_the_limit(self):
        manager = HistoryManager()
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda i: manager.add_entry(str(i), "url", f"{i}.mp4", "MP4"), range(120)))
        stored = json.loads((self.profile / "history.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manager.get_all()), 100)
        self.assertEqual(len(stored), 100)
        self.assertEqual(len({entry["id"] for entry in stored}), 100)


class HeldWorker(QThread):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self):
        self.entered.set()
        self.release.wait(3)


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    return predicate()


class TestSafeShutdown(IsolatedTest):
    def test_both_entry_points_stop_workers_before_cleaning_the_session_cache(self):
        code = '''
import os, sys, pathlib, tempfile, runpy
root = pathlib.Path(sys.argv[1]).resolve()
profile = root / "profile"; profile.mkdir()
temp = root / "temp"; temp.mkdir()
pathlib.Path.home = classmethod(lambda cls: profile)
tempfile.tempdir = str(temp)
os.environ.update(LOCALAPPDATA=str(profile), QT_QPA_PLATFORM="offscreen")
from PySide6.QtCore import QTimer
from core.temp_files import get_cache_dir
from core.workers import CancellableThread, start_worker
cache = pathlib.Path(get_cache_dir())
(cache / "preview.mp4").write_bytes(b"preview")
downloads = profile / "Downloads" / "AuraDownloads"; downloads.mkdir(parents=True)
user_file = downloads / "sample_user.mp4"; user_file.write_bytes(b"user data")
entry = runpy.run_path(sys.argv[2], run_name="aura_entry")
class Job(CancellableThread):
    def run(self):
        while not self.isInterruptionRequested(): self.msleep(10)
jobs = []
class Window(entry["MainWindow"]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        worker = Job(); jobs.append(worker); start_worker(worker, self)
        QTimer.singleShot(30, self.close)
entry["main"].__globals__["MainWindow"] = Window
try: entry["main"]()
except SystemExit as result: assert result.code == 0
assert all(worker.wait(0) for worker in jobs)
assert not cache.exists()
assert user_file.read_bytes() == b"user data"
print("entry point shutdown OK")
'''
        for filename in ("main.py", "main.pyw"):
            with self.subTest(entry=filename):
                sandbox = self.root / filename
                sandbox.mkdir()
                result = subprocess.run([sys.executable, "-c", code, str(sandbox), filename],
                                        cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                        text=True, timeout=15, creationflags=0x08000000)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("entry point shutdown OK", result.stdout)

    def test_main_window_remains_open_until_worker_finishes(self):
        window = MainWindow()
        window.show()
        worker = HeldWorker()
        window.download_worker = worker
        window._track_worker(worker)
        start_worker(worker, window)
        self.assertTrue(worker.entered.wait(1))
        try:
            window.close()
            self.assertTrue(worker.cancelled)
            self.assertTrue(worker.isRunning())
            self.assertTrue(window.isVisible())
            self.assertFalse(window.isEnabled())
        finally:
            worker.release.set()
        self.assertTrue(wait_until(lambda: not window.isVisible()))
        self.assertTrue(worker.wait(1000))

    def test_modal_accept_reject_and_close_wait_for_owned_workers(self):
        for method in ("accept", "reject", "close"):
            with self.subTest(method=method):
                dialog = WorkerDialog()
                dialog.show()
                worker = HeldWorker()
                start_worker(worker, dialog)
                self.assertTrue(worker.entered.wait(1))
                getattr(dialog, method)()
                try:
                    self.assertTrue(dialog.isVisible())
                    self.assertTrue(worker.cancelled)
                finally:
                    worker.release.set()
                self.assertTrue(wait_until(lambda: not dialog.isVisible()))
                self.assertTrue(worker.wait(1000))

    def test_cancelled_engine_download_keeps_existing_engine_and_removes_partial_archive(self):
        from core.interpolator import download_rife_engine
        tools = self.root / "tools"
        tools.mkdir()
        executable = tools / "rife-ncnn-vulkan.exe"
        executable.write_bytes(b"existing engine")
        response = MagicMock()
        response.headers = {"content-length": "100"}
        response.iter_content.return_value = [b"partial archive"]
        checks = iter([False, True])
        with patch("core.interpolator.get_tools_dir", return_value=str(tools)), patch("core.interpolator.requests.get", return_value=response):
            self.assertFalse(download_rife_engine(is_cancelled_cb=lambda: next(checks)))
        self.assertEqual(executable.read_bytes(), b"existing engine")
        self.assertFalse((tools / "rife.zip.part").exists())

    def test_updater_cancellation_terminates_and_reaps_its_child_process(self):
        from ui.settings_modal import UpdateYtdlpWorker
        process = MagicMock()
        process.poll.return_value = None
        entered = threading.Event()
        terminated = threading.Event()
        def communicate(timeout=None):
            entered.set()
            if terminated.is_set():
                process.poll.return_value = 0
                return "", ""
            time.sleep(0.01)
            raise subprocess.TimeoutExpired("pip", timeout)
        process.communicate.side_effect = communicate
        process.terminate.side_effect = terminated.set
        worker = UpdateYtdlpWorker()
        with patch("subprocess.Popen", return_value=process):
            start_worker(worker)
            self.assertTrue(entered.wait(1))
            worker.cancel()
            self.assertTrue(worker.wait(2000))
        process.terminate.assert_called_once()
        self.assertEqual(process.poll(), 0)

    def test_removing_a_card_does_not_destroy_its_running_preview_thread(self):
        from ui.video_cards_list import VideoCardsListWidget
        entered, release = threading.Event(), threading.Event()
        response = MagicMock(status_code=200, content=b"not an image")
        def fetch(*args, **kwargs):
            entered.set()
            release.wait(2)
            return response
        cards = VideoCardsListWidget()
        with patch("ui.video_cards_list.requests.get", side_effect=fetch):
            item_id = cards.add_video({"url": "fixture.mp4", "title": "Preview", "thumbnail": "https://example.com/preview.jpg"})
            worker = cards.cards[0]._image_worker
            self.assertTrue(entered.wait(1))
            try:
                cards.remove_card(item_id)
                app.processEvents()
                self.assertTrue(worker.isRunning())
                self.assertTrue(worker.isInterruptionRequested())
                self.assertIn(worker, worker_registry().workers)
            finally:
                release.set()
            self.assertTrue(worker.wait(2000))

    def test_closing_window_stops_real_ffmpeg_and_removes_partial_output(self):
        ffmpeg = get_ffmpeg_path()
        if not shutil.which(ffmpeg):
            self.skipTest("FFmpeg is not installed")
        part = self.output / "cancellable.tmp.mp4"
        cancelled = threading.Event()
        processes = []
        spawned = threading.Event()
        original_popen = subprocess.Popen
        def record_process(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            processes.append(process)
            spawned.set()
            return process
        class FFmpegWorker(QThread):
            def cancel(self): cancelled.set()
            def run(self):
                run_ffmpeg_cancellable([ffmpeg, "-y", "-re", "-f", "lavfi", "-i",
                                        "color=size=32x32:rate=10", "-t", "30", str(part)],
                                       str(part), cancelled.is_set)
        window = MainWindow()
        window.show()
        worker = FFmpegWorker()
        with patch("core.media_converter.subprocess.Popen", side_effect=record_process):
            start_worker(worker, window)
            self.assertTrue(spawned.wait(2))
            window.close()
            self.assertTrue(wait_until(lambda: not window.isVisible()))
        self.assertTrue(worker.wait(1000))
        self.assertIsNotNone(processes[0].poll())
        self.assertFalse(part.exists())
