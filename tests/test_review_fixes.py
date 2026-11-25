"""Regression tests for all code-review fixes (bugs, UI/UX, concurrency, resource safety)."""
import copy
import io
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRectF, SIGNAL, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from assets.styles import get_stylesheet
from core.app_logging import LogStream, cleanup_old_logs
from core.clipboard import extract_supported_url
from core.downloader import (
    DownloadWorker,
    MetadataWorker,
    _choose_instagram_carousel_video_url,
    _parse_content_length,
    detect_platform,
    sanitize_filename,
)
from core.frame_capture import FrameCaptureSession
from core.http_utils import read_limited_response
from core import interpolator
from core import media_converter
from core.persistence import save_json, _replace_bytes
from core.process_utils import open_path_in_os, reveal_in_explorer
from core.settings import settings
from core.temp_files import OwnedDirectory, OWNER_FILE, remove_owned_directory
from core.unified_batch_worker import UnifiedBatchWorker
from core.workers import PooledWorker, shutdown_background_tasks, start_worker, thumbnail_thread_pool, worker_registry
from ui.batch_dialog import BatchDialog
from ui.crop_dialog import CropCanvas, CropDialog, HANDLE_BR, HANDLE_R
from ui.gallery_dialog import InstagramGalleryDialog
from ui.history_view import HistoryModal
from ui.main_window import MainWindow
from ui.playlist_dialog import PlaylistDialog
from ui.progress_widget import ProgressWidget
from ui.settings_modal import SettingsModal, UpdateYtdlpWorker
from ui.smooth_widget import SmoothWidget
from ui.title_bar import CustomTitleBar
from ui.toggle_switch import ToggleSwitch
from ui.trim_dialog import TrimDialog
from ui.trim_widget import TrimWidget
from ui.video_cards_list import VideoCardsListWidget
from ui.worker_dialog import WorkerDialog


app = QApplication.instance() or QApplication([])


def _mouse_event(ev_type, local_pos, global_pos=None, button=Qt.NoButton,
                 buttons=Qt.NoButton, modifiers=Qt.NoModifier):
    lp = QPointF(local_pos)
    gp = QPointF(global_pos) if global_pos is not None else lp
    return QMouseEvent(ev_type, lp, lp, gp, button, buttons, modifiers)


def _pump_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestCoreDownloaderFixes(unittest.TestCase):
    def setUp(self):
        MetadataWorker._cache.clear()

    def tearDown(self):
        MetadataWorker._cache.clear()

    def test_sanitize_filename_handles_reserved_long_and_empty_names(self):
        self.assertEqual(sanitize_filename("CON"), "_CON")
        self.assertEqual(sanitize_filename("nul"), "_nul")
        self.assertEqual(sanitize_filename("LPT1"), "_LPT1")
        self.assertEqual(sanitize_filename("...   !!!", fallback="Photo"), "Photo")
        self.assertEqual(sanitize_filename("", fallback="Photo"), "Photo")
        long_name = "a" * 300
        self.assertLessEqual(len(sanitize_filename(long_name)), 120)

    def test_parse_content_length_handles_invalid_values(self):
        self.assertEqual(_parse_content_length({"content-length": "1024"}), 1024)
        self.assertEqual(_parse_content_length({"content-length": "invalid"}), 0)
        self.assertEqual(_parse_content_length({"content-length": "-5"}), 0)
        self.assertEqual(_parse_content_length({}), 0)

    def test_instagram_carousel_prefers_progressive_mp4_with_audio(self):
        entry = {
            "formats": [
                {"url": "https://cdn/audio_only.m4a", "vcodec": "none", "acodec": "mp4a", "ext": "m4a", "protocol": "https"},
                {"url": "https://cdn/progressive_audio.mp4", "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4", "height": 720, "width": 720, "protocol": "https"},
                {"url": "https://cdn/dash_no_audio.mp4", "vcodec": "avc1", "acodec": "none", "ext": "mp4", "height": 1080, "width": 1080, "protocol": "https"},
            ]
        }
        self.assertEqual(_choose_instagram_carousel_video_url(entry), "https://cdn/progressive_audio.mp4")

    def test_instagram_single_photo_uses_available_res_key(self):
        worker = MetadataWorker("https://www.instagram.com/p/Test123/")
        ready = []
        worker.info_ready.connect(ready.append)
        fake_ie = MagicMock()
        fake_ie.extract.return_value = {
            "title": "Photo",
            "uploader": "tester",
            "thumbnails": [{"url": "https://cdn/img.jpg", "width": 1080, "height": 1080}],
        }
        with patch("core.downloader.yt_dlp.YoutubeDL"), patch("core.downloader.InstagramIE", return_value=fake_ie):
            worker.run()
        self.assertEqual(len(ready), 1)
        self.assertIn("available_res", ready[0])
        self.assertNotIn("available_resolutions", ready[0])

    def test_playlist_supports_generator_entries_and_non_youtube_platform(self):
        worker = MetadataWorker("https://vimeo.com/playlist/42")
        playlists, errors = [], []
        worker.playlist_ready.connect(playlists.append)
        worker.info_error.connect(errors.append)

        def entry_gen():
            yield {"id": "10", "url": "https://vimeo.com/10", "title": "First", "duration": 12}
            yield {"id": "20", "url": "https://vimeo.com/20", "title": "Second", "duration": 24}

        ydl = MagicMock()
        ydl.extract_info.return_value = {"title": "My Vimeo Set", "entries": entry_gen()}
        with patch("core.downloader.yt_dlp.YoutubeDL") as factory:
            factory.return_value.__enter__.return_value = ydl
            worker.run()

        self.assertEqual(errors, [])
        self.assertEqual(len(playlists), 1)
        self.assertEqual(playlists[0]["platform"], "Vimeo")
        self.assertEqual(playlists[0]["entries"][0]["url"], "https://vimeo.com/10")
        self.assertEqual(playlists[0]["entries"][0]["platform"], "Vimeo")
        self.assertIsNone(playlists[0]["entries"][0]["thumbnail"])

    def test_download_worker_sets_noplaylist_and_skips_noop_trim_and_redundant_scale(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = DownloadWorker(
                "https://www.youtube.com/watch?v=abc&list=PL123",
                {"mode": "custom", "res": "1080p Full HD", "trim_enabled": True, "trim_start": "00:00", "trim_end": ""},
                folder,
            )
            completed, errors = [], []
            worker.download_completed.connect(completed.append)
            worker.download_error.connect(errors.append)

            def fake_extract(url, download=True):
                stage = next(Path(folder).glob(".aura_staging_*"))
                media = stage / "Clip [abc].mp4"
                media.write_bytes(b"mp4data")
                worker._last_filename = str(media)
                return {"title": "Clip", "ext": "mp4"}

            ydl = MagicMock()
            ydl.extract_info.side_effect = fake_extract
            ydl.prepare_filename.return_value = "Clip [abc].mp4"
            with patch("core.downloader.yt_dlp.YoutubeDL") as factory, \
                 patch("core.downloader.needs_scale", return_value=False), \
                 patch("core.downloader.transform_video") as transform:
                factory.return_value.__enter__.return_value = ydl
                worker.run()
            used_opts = factory.call_args_list[0].args[0]
            self.assertTrue(used_opts["noplaylist"])
            self.assertNotIn("download_ranges", used_opts)
            self.assertNotIn("force_keyframes_at_cuts", used_opts)
            transform.assert_not_called()
            self.assertEqual(errors, [])
            self.assertEqual(len(completed), 1)

    def test_direct_download_closes_response_on_http_error_and_handles_reserved_name(self):
        with tempfile.TemporaryDirectory() as folder:
            bad_resp = MagicMock()
            bad_resp.raise_for_status.side_effect = RuntimeError("HTTP 403")
            worker_err = DownloadWorker("https://cdn.example/pic.jpg", {"is_photo": True, "title": "CON"}, folder)
            errors = []
            worker_err.download_error.connect(errors.append)
            with patch("core.downloader.requests.get", return_value=bad_resp):
                worker_err.run()
            bad_resp.close.assert_called_once()
            self.assertTrue(errors)

            buf = io.BytesIO()
            Image.new("RGB", (8, 8), "red").save(buf, "PNG")
            ok_resp = MagicMock()
            ok_resp.headers = {"content-length": "not-a-number"}
            ok_resp.iter_content.return_value = [buf.getvalue()]
            worker_ok = DownloadWorker("https://cdn.example/pic.jpg", {"is_photo": True, "title": "CON"}, folder)
            completed, errs = [], []
            worker_ok.download_completed.connect(completed.append)
            worker_ok.download_error.connect(errs.append)
            with patch("core.downloader.requests.get", return_value=ok_resp):
                worker_ok.run()
            self.assertEqual(errs, [])
            self.assertEqual(len(completed), 1)
            self.assertEqual(Path(completed[0]["file_path"]).name, "_CON.png")
            ok_resp.close.assert_called_once()


class TestMediaAndRifeFixes(unittest.TestCase):
    def test_rife_disk_space_check_falls_back_cleanly(self):
        statuses = []
        with patch("core.interpolator.get_rife_executable", return_value="C:/rife/rife-ncnn-vulkan.exe"), \
             patch("core.interpolator.get_rife_model_path", return_value="C:/rife/rife-v4.6"), \
             patch("core.interpolator.probe_media_info", return_value={"width": 1920, "height": 1080, "duration": 120.0, "fps": 30.0}), \
             patch("core.interpolator.shutil.disk_usage", return_value=SimpleNamespace(free=100 * 1024 * 1024)), \
             patch("core.interpolator.interpolate_with_ffmpeg", return_value="fallback.mp4") as ff_mock:
            result = interpolator.interpolate_with_rife("video.mp4", 60, status_callback=statuses.append)
        self.assertEqual(result, "fallback.mp4")
        ff_mock.assert_called_once()
        self.assertTrue(any("места на диске" in s for s in statuses))

    def test_rife_cleans_temp_dir_before_calling_fallback(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            seen_temp_dirs_during_fallback = []

            def fake_extract(cmd, part_path, cancelled):
                in_dir = Path(cmd[-1]).parent
                (in_dir / "frame_00000001.png").write_bytes(b"png1")
                (in_dir / "frame_00000002.png").write_bytes(b"png2")
                return True

            def fake_fallback(*args, **kwargs):
                seen_temp_dirs_during_fallback.extend(Path(cache_dir).glob("aura_rife_*"))
                return "fallback.mp4"

            failed_proc = SimpleNamespace(poll=lambda: 1, returncode=1)
            with patch("core.interpolator.get_cache_dir", return_value=cache_dir), \
                 patch("core.interpolator.get_rife_executable", return_value=str(Path(cache_dir) / "rife.exe")), \
                 patch("core.interpolator.get_rife_model_path", return_value=str(Path(cache_dir) / "rife-v4.6")), \
                 patch("core.interpolator.probe_media_info", return_value={"width": 64, "height": 64, "duration": 0.1, "fps": 24.0}), \
                 patch("core.interpolator.shutil.disk_usage", return_value=SimpleNamespace(free=10 * 1024 ** 3)), \
                 patch("core.interpolator.run_ffmpeg_cancellable", side_effect=fake_extract), \
                 patch("core.interpolator.subprocess.Popen", return_value=failed_proc), \
                 patch("core.interpolator.interpolate_with_ffmpeg", side_effect=fake_fallback):
                res = interpolator.interpolate_with_rife("clip.mp4", 60, output_path=str(Path(cache_dir) / "out.mp4"))

            self.assertEqual(res, "fallback.mp4")
            self.assertEqual(seen_temp_dirs_during_fallback, [])

    def test_is_rife_available_uses_cache_until_refreshed(self):
        interpolator.invalidate_rife_cache()
        with patch("core.interpolator.get_rife_executable", return_value=None) as finder:
            self.assertFalse(interpolator.is_rife_available())
            self.assertFalse(interpolator.is_rife_available())
            self.assertEqual(finder.call_count, 1)
            self.assertFalse(interpolator.is_rife_available(force_refresh=True))
            self.assertEqual(finder.call_count, 2)
        interpolator.invalidate_rife_cache()

    def test_preview_proxy_rejects_10bit_h264_and_mkv_and_uses_yuv420p_faststart(self):
        with tempfile.TemporaryDirectory() as folder:
            mp4_10bit = Path(folder) / "hdr10.mp4"
            mkv_8bit = Path(folder) / "clip.mkv"
            mp4_8bit = Path(folder) / "ok.mp4"
            for p in (mp4_10bit, mkv_8bit, mp4_8bit):
                p.write_bytes(b"video")

            with patch("core.media_converter.probe_media_info", return_value={"codec": "h264", "pix_fmt": "yuv420p"}), \
                 patch("core.media_converter.run_ffmpeg_cancellable") as run_ff:
                self.assertEqual(media_converter.get_or_create_preview_proxy(str(mp4_8bit)), str(mp4_8bit))
                run_ff.assert_not_called()

            for path, probe in (
                (mp4_10bit, {"codec": "h264", "pix_fmt": "yuv420p10le"}),
                (mkv_8bit, {"codec": "h264", "pix_fmt": "yuv420p"}),
            ):
                cmds = []

                def fake_ff(cmd, part_path, cancelled):
                    cmds.append(cmd)
                    Path(part_path).write_bytes(b"proxy")
                    return True

                with patch("core.media_converter.probe_media_info", return_value=probe), \
                     patch("core.media_converter.get_cache_dir", return_value=folder), \
                     patch("core.media_converter.run_ffmpeg_cancellable", side_effect=fake_ff):
                    proxy = media_converter.get_or_create_preview_proxy(str(path))
                self.assertNotEqual(proxy, str(path))
                self.assertIn("-pix_fmt", cmds[0])
                self.assertEqual(cmds[0][cmds[0].index("-pix_fmt") + 1], "yuv420p")
                self.assertIn("-movflags", cmds[0])
                self.assertEqual(cmds[0][cmds[0].index("-movflags") + 1], "+faststart")

    def test_compress_to_target_size_includes_yuv420p_and_faststart(self):
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / "in.mp4"
            out = Path(folder) / "out.mp4"
            src.write_bytes(b"x")
            cmds = []

            def fake_ff(cmd, part_path, cancelled):
                cmds.append(cmd)
                Path(part_path).write_bytes(b"small")
                return True

            with patch("core.media_converter.get_video_duration", return_value=10.0), \
                 patch("core.media_converter.run_ffmpeg_cancellable", side_effect=fake_ff):
                res = media_converter.compress_to_target_size(str(src), target_mb=8.0, output_path=str(out))
            self.assertEqual(res, str(out))
            self.assertIn("-pix_fmt", cmds[0])
            self.assertEqual(cmds[0][cmds[0].index("-pix_fmt") + 1], "yuv420p")
            self.assertIn("-movflags", cmds[0])
            self.assertEqual(cmds[0][cmds[0].index("-movflags") + 1], "+faststart")

    def test_extract_audio_honors_bitrate_and_rejects_empty_output(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "track.mp3"
            cmds = []

            def fake_ff_ok(cmd, part_path, cancelled):
                cmds.append(cmd)
                Path(part_path).write_bytes(b"audio")
                return True

            with patch("core.media_converter.get_video_duration", return_value=10.0), \
                 patch("core.media_converter.run_ffmpeg_cancellable", side_effect=fake_ff_ok):
                media_converter.extract_audio("in.mp4", "mp3", {"audio_q": "128"}, str(out))
            self.assertEqual(cmds[0][cmds[0].index("-b:a") + 1], "128k")

            out2 = Path(folder) / "track.opus"
            with patch("core.media_converter.get_video_duration", return_value=10.0), \
                 patch("core.media_converter.run_ffmpeg_cancellable", side_effect=fake_ff_ok):
                media_converter.extract_audio("in.mp4", "opus", {"audio_quality": "96"}, str(out2))
            self.assertEqual(cmds[1][cmds[1].index("-b:a") + 1], "96k")

            def fake_ff_empty(cmd, part_path, cancelled):
                Path(part_path).write_bytes(b"")
                return True

            with patch("core.media_converter.get_video_duration", return_value=10.0), \
                 patch("core.media_converter.run_ffmpeg_cancellable", side_effect=fake_ff_empty), \
                 self.assertRaises(ValueError):
                media_converter.extract_audio("in.mp4", "mp3", {}, str(Path(folder) / "empty.mp3"))

    def test_frame_capture_boundary_caching_and_hdr_fallback(self):
        session = FrameCaptureSession("HTTPS://example.test/video.mp4")
        ffprobe_calls = []

        def fake_run(command, cancelled, timeout=45):
            if "ffprobe" in str(command[0]).lower():
                if "-show_frames" in command:
                    ffprobe_calls.append(command)
                    frames = [{"best_effort_timestamp_time": f"{i / 10:.3f}"} for i in range(11)]
                    return json.dumps({"frames": frames}).encode()
                return json.dumps({
                    "streams": [{"start_time": "0", "duration": "1.0", "color_transfer": "smpte2084",
                                 "color_primaries": "unknown", "color_space": "unknown"}],
                    "format": {"duration": "1.0", "start_time": "0"},
                }).encode()
            vf = command[command.index("-vf") + 1]
            if "zscale" in vf:
                self.assertIn("pin=bt2020", vf)
                self.assertIn("min=bt2020nc", vf)
                raise ValueError("simulated zscale failure")
            buf = io.BytesIO()
            Image.new("RGB", (16, 16), "blue").save(buf, "PNG")
            Path(command[-1]).write_bytes(buf.getvalue())
            return b""

        try:
            with patch("core.frame_capture.run_command", side_effect=fake_run):
                f0 = session.capture(0.0, 0)
                f0_prev = session.capture(0.0, -1)
                f1 = session.capture(0.0, 1)
                f_end = session.capture(0.95, 1)
            self.assertEqual(f0["width"], 16)
            self.assertEqual(f0_prev["position"], 0.0)
            self.assertAlmostEqual(f1["position"], 0.1, places=4)
            self.assertAlmostEqual(f_end["position"], 1.0, places=4)
            # Only ONE ffprobe frame-window query should have been needed for [0, 1.0]
            self.assertEqual(len(ffprobe_calls), 1)
        finally:
            session.close()


class TestConcurrencySafetyAndInfra(unittest.TestCase):
    def test_unified_batch_worker_monotonic_progress_and_safe_cancel(self):
        with tempfile.TemporaryDirectory() as folder:
            class StubWorker:
                def __init__(self, url, options, save_dir):
                    from PySide6.QtCore import QObject, Signal

                    class _Sigs(QObject):
                        progress_updated = Signal(dict)
                        status_message = Signal(str)
                        download_completed = Signal(dict)
                        download_error = Signal(str)
                        recovery_available = Signal(dict)

                    self._s = _Sigs()
                    self.progress_updated = self._s.progress_updated
                    self.status_message = self._s.status_message
                    self.download_completed = self._s.download_completed
                    self.download_error = self._s.download_error
                    self.recovery_available = self._s.recovery_available
                    self.url = url
                    self.save_dir = save_dir
                    self.cancelled = False

                def cancel(self):
                    self.cancelled = True

                def run(self):
                    if "fail" in self.url:
                        self.download_error.emit("boom")
                        return
                    self.progress_updated.emit({"percent": 50, "status": "downloading"})
                    p = Path(self.save_dir) / "ok.mp4"
                    p.write_bytes(b"ok")
                    self.download_completed.emit({"title": "ok", "file_path": str(p), "file_size": 2, "mode": "MP4"})

            worker = UnifiedBatchWorker(["https://host/fail", "https://host/ok"], {}, folder)
            percents = []
            worker.progress_updated.connect(lambda d: percents.append(d["percent"]))
            with patch("core.unified_batch_worker.DownloadWorker", StubWorker):
                worker.run()
            self.assertEqual(percents, sorted(percents))
            self.assertEqual(percents[-1], 100.0)

            # Concurrent cancel() while _current_worker is transitioning must not raise
            entered = threading.Event()
            release = threading.Event()

            class SlowStubWorker(StubWorker):
                def run(self):
                    entered.set()
                    release.wait(2.0)

            race_worker = UnifiedBatchWorker(["https://host/slow1", "https://host/slow2"], {}, folder)
            errors = []

            def run_batch():
                try:
                    with patch("core.unified_batch_worker.DownloadWorker", SlowStubWorker):
                        race_worker.run()
                except Exception as exc:
                    errors.append(exc)

            t = threading.Thread(target=run_batch)
            t.start()
            self.assertTrue(entered.wait(2.0))
            race_worker.cancel()
            release.set()
            t.join(3.0)
            self.assertFalse(t.is_alive())
            self.assertEqual(errors, [])
            self.assertTrue(race_worker.is_cancelled)

    def test_remove_owned_directory_preserves_marker_on_locked_file(self):
        with tempfile.TemporaryDirectory() as parent:
            session = OwnedDirectory(parent, ".aura_staging_", "staging")
            locked_file = session.path / "locked.tmp"
            locked_file.write_bytes(b"busy")
            session.release()

            orig_unlink = Path.unlink

            def fail_locked(self_path, *args, **kwargs):
                if self_path.name == "locked.tmp":
                    raise PermissionError("file locked")
                return orig_unlink(self_path, *args, **kwargs)

            with patch.object(Path, "unlink", fail_locked):
                self.assertFalse(remove_owned_directory(session.path, parent, "staging"))
            self.assertTrue((session.path / OWNER_FILE).is_file())
            self.assertTrue(remove_owned_directory(session.path, parent, "staging"))

    def test_owned_directory_cleans_up_on_lock_failure(self):
        with tempfile.TemporaryDirectory() as parent:
            fake_lock = MagicMock()
            fake_lock.tryLock.return_value = False
            with patch("core.temp_files._directory_lock", return_value=fake_lock):
                with self.assertRaises(OSError):
                    OwnedDirectory(parent, ".aura_staging_", "staging")
            self.assertEqual(list(Path(parent).iterdir()), [])

    def test_pooled_worker_stress_cancel_with_queued_items(self):
        worker_registry().stopping = False
        dialog = WorkerDialog()
        started = threading.Event()
        try:
            class BlockingPoolWorker(PooledWorker):
                def run(self):
                    started.set()
                    deadline = time.monotonic() + 5.0
                    while not self.isInterruptionRequested() and time.monotonic() < deadline:
                        time.sleep(0.01)

            workers = [BlockingPoolWorker() for _ in range(8)]
            for w in workers:
                start_worker(w, dialog)
            self.assertTrue(started.wait(2.0))
            dialog.reject()
            self.assertTrue(_pump_until(lambda: not dialog._owned_workers and not worker_registry().workers, timeout=3.0))
        finally:
            dialog.deleteLater()
            worker_registry().stopping = False

    def test_cleanup_aura_temp_files_scans_known_download_dirs(self):
        with tempfile.TemporaryDirectory() as root:
            dl1 = Path(root) / "dl1"
            dl2 = Path(root) / "dl2"
            dl1.mkdir()
            dl2.mkdir()
            session = OwnedDirectory(dl2, ".aura_staging_", "staging")
            (session.path / "leftover.part").write_bytes(b"part")
            session.release()
            with patch.object(settings, "get", side_effect=lambda k, d=None: str(dl1) if k == "download_dir" else ([str(dl1), str(dl2)] if k == "known_download_dirs" else d)):
                cleaned = media_converter.cleanup_aura_temp_files(max_age_hours=0)
            self.assertGreaterEqual(cleaned, 1)
            self.assertFalse(session.path.exists())

    def test_save_json_validates_before_writing_and_retries_permission_error(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "data.json"
            with self.assertRaises(ValueError):
                save_json(target, "bad", lambda d: (_ for _ in ()).throw(ValueError("invalid")))
            self.assertFalse(target.exists())

            calls = []
            orig_replace = os.replace

            def flaky_replace(src, dst):
                calls.append(1)
                if len(calls) < 3:
                    raise PermissionError("transient lock")
                return orig_replace(src, dst)

            with patch("core.persistence.os.replace", side_effect=flaky_replace):
                _replace_bytes(target, b'{"ok": true}', retries=4, retry_delay=0.001)
            self.assertEqual(len(calls), 3)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})

    def test_log_stream_thread_safety_and_old_log_pruning(self):
        stream = LogStream(logging.INFO)
        logged = []
        with patch("core.app_logging.logging.getLogger") as get_logger:
            get_logger.return_value.log.side_effect = lambda lvl, msg: logged.append(msg)
            threads = [threading.Thread(target=lambda i=i: stream.write(f"line-{i}\n")) for i in range(16)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(len(logged), 16)
        self.assertEqual(stream.buffers, {})

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for idx in range(6):
                p = root / f"aura-{10000 + idx}.log"
                p.write_text("log", encoding="utf-8")
                os.utime(p, (1000 + idx, 1000 + idx))
            current = root / f"aura-{os.getpid()}.log"
            current.write_text("active", encoding="utf-8")
            removed = cleanup_old_logs(root, max_files=2, max_age_days=36500)
            self.assertEqual(removed, 4)
            self.assertTrue(current.exists())

    def test_owned_workers_cleaned_on_finish_and_shutdown_has_timeout(self):
        worker_registry().stopping = False
        dialog = WorkerDialog()
        try:
            class QuickPoolWorker(PooledWorker):
                def run(self):
                    pass

            w = QuickPoolWorker()
            start_worker(w, dialog)
            self.assertTrue(_pump_until(lambda: w not in dialog._owned_workers and w not in worker_registry().workers))
            self.assertEqual(thumbnail_thread_pool().maxThreadCount(), 4)
        finally:
            dialog.deleteLater()

        class StuckWorker:
            def __init__(self):
                self.wait_calls = []

            def requestInterruption(self):
                pass

            def wait(self, msecs=-1):
                self.wait_calls.append(msecs)
                return False

        stuck = StuckWorker()
        reg = worker_registry()
        reg.workers.append(stuck)
        try:
            t0 = time.monotonic()
            shutdown_background_tasks(timeout_ms=40)
            self.assertLess(time.monotonic() - t0, 1.0)
            self.assertTrue(stuck.wait_calls and stuck.wait_calls[0] > 0)
        finally:
            if stuck in reg.workers:
                reg.workers.remove(stuck)
            reg.stopping = False

    def test_read_limited_response_rejects_oversize(self):
        big_header_resp = MagicMock(headers={"content-length": str(20 * 1024 * 1024)})
        self.assertIsNone(read_limited_response(big_header_resp, max_bytes=1024))

        stream_resp = MagicMock(headers={})
        stream_resp.iter_content.return_value = [b"a" * 600, b"b" * 600]
        self.assertIsNone(read_limited_response(stream_resp, max_bytes=1024))

        ok_resp = MagicMock(headers={"content-length": "10"})
        ok_resp.iter_content.return_value = [b"hello", b"world"]
        self.assertEqual(read_limited_response(ok_resp, max_bytes=1024), b"helloworld")

    def test_clipboard_url_extraction_and_new_domains(self):
        cases = [
            ("Смотри: https://music.youtube.com/watch?v=abc123.", "https://music.youtube.com/watch?v=abc123"),
            ("(https://m.youtube.com/watch?v=xyz), круто!", "https://m.youtube.com/watch?v=xyz"),
            ("https://clips.twitch.tv/ClipName!", "https://clips.twitch.tv/ClipName"),
            ("https://redd.it/abc123;", "https://redd.it/abc123"),
            ("https://pin.it/98765,", "https://pin.it/98765"),
            ("https://instagr.am/p/Code123/»", "https://instagr.am/p/Code123/"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(extract_supported_url(raw), expected)
        self.assertEqual(detect_platform("https://instagr.am/p/abc/"), "Instagram")
        self.assertEqual(detect_platform("https://redd.it/abc"), "Reddit")
        self.assertEqual(detect_platform("https://pin.it/abc"), "Pinterest")

    def test_process_utils_safe_open_and_nonblocking_reveal(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / "file.mp4"
            f.write_bytes(b"data")
            with patch("core.process_utils.os.startfile", side_effect=OSError("no app"), create=True):
                self.assertFalse(open_path_in_os(str(f)))
            with patch("core.process_utils.subprocess.Popen") as popen:
                self.assertTrue(reveal_in_explorer(str(f)))
                popen.assert_called_once()


class TestUIFixes(unittest.TestCase):
    def setUp(self):
        worker_registry().stopping = False
        self.defaults = copy.deepcopy(settings.settings)

    def tearDown(self):
        settings.settings = self.defaults
        worker_registry().stopping = False

    def test_trim_widget_enables_toggle_when_dialog_applies(self):
        widget = TrimWidget()
        try:
            self.assertFalse(widget.is_trim_enabled())
            fake_dialog = MagicMock()
            fake_dialog.exec.return_value = True
            fake_dialog.applied_range = ("00:05", "00:15")
            with patch("ui.trim_widget.TrimDialog", return_value=fake_dialog):
                widget._open_trim_dialog()
            self.assertTrue(widget.is_trim_enabled())
            self.assertEqual(widget.get_trim_range(), ("00:05", "00:15"))
        finally:
            widget.deleteLater()

    def test_trim_dialog_no_end_jump_russian_hotkeys_and_space_guard(self):
        dialog = TrimDialog(duration_sec=10, initial_start="00:01", initial_end="00:08")
        try:
            seeks = []
            dialog._seek_to_ms = lambda ms: seeks.append(ms)
            dialog._on_range_changed(2000, 8000)
            self.assertEqual(seeks, [])

            # Space before preview is loaded should NOT switch button to ПАУЗА
            dialog._preview_loaded = False
            before_text = dialog.btn_play.text()
            dialog.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier))
            self.assertEqual(dialog.btn_play.text(), before_text)

            # Russian Б/Ю and Ctrl+Ы hotkeys
            with patch.object(dialog, "_request_frame") as req_frame, \
                 patch.object(dialog, "_save_current_frame") as save_frame:
                dialog.keyPressEvent(QKeyEvent(QEvent.KeyPress, 1041, Qt.NoModifier))  # Б
                dialog.keyPressEvent(QKeyEvent(QEvent.KeyPress, 1070, Qt.NoModifier))  # Ю
                dialog.keyPressEvent(QKeyEvent(QEvent.KeyPress, 1067, Qt.ControlModifier))  # Ctrl+Ы
            self.assertEqual(req_frame.call_args_list[0].args, (-1,))
            self.assertEqual(req_frame.call_args_list[1].args, (1,))
            save_frame.assert_called_once()
        finally:
            dialog.reject()
            dialog.deleteLater()

    def test_crop_canvas_keeps_locked_ratio_at_edges_and_restores_preset_highlight(self):
        pix = QPixmap(320, 180)
        pix.fill(QColor("gray"))
        canvas = CropCanvas()
        canvas.resize(400, 300)
        canvas.set_source_image(pix, 1920, 1080)
        canvas.set_aspect_ratio(1.0)
        img_rect = canvas._get_image_draw_rect()

        # Drag right handle way beyond right edge of image
        canvas.active_handle = HANDLE_R
        canvas.drag_start_pos = QPointF(img_rect.center().x(), img_rect.center().y())
        canvas.drag_start_rect = QRectF(canvas.crop_norm)
        ev = _mouse_event(QEvent.MouseMove, QPointF(img_rect.right() + 500, img_rect.center().y()),
                          button=Qt.NoButton, buttons=Qt.LeftButton)
        canvas.mouseMoveEvent(ev)
        p = canvas.get_crop_params()
        self.assertAlmostEqual(p["w"] / p["h"], 1.0, places=2)
        self.assertLessEqual(canvas.crop_norm.right(), 1.0001)
        self.assertLessEqual(canvas.crop_norm.bottom(), 1.0001)

        # Drag bottom-right corner way past corner
        canvas.active_handle = HANDLE_BR
        canvas.drag_start_rect = QRectF(canvas.crop_norm)
        ev2 = _mouse_event(QEvent.MouseMove, QPointF(img_rect.right() + 500, img_rect.bottom() + 500),
                           button=Qt.NoButton, buttons=Qt.LeftButton)
        canvas.mouseMoveEvent(ev2)
        p2 = canvas.get_crop_params()
        self.assertAlmostEqual(p2["w"] / p2["h"], 1.0, places=2)
        canvas.deleteLater()

        # Reopen CropDialog with applied_crop_params highlights 9:16 preset
        dlg1 = CropDialog(pixmap=pix, source_w=1920, source_h=1080)
        dlg1._set_preset(9.0 / 16.0, dlg1.pill_9_16)
        dlg1._apply()
        saved = dlg1.applied_crop_params
        dlg1.deleteLater()

        dlg2 = CropDialog(pixmap=pix, source_w=1920, source_h=1080, initial_params=saved)
        self.assertEqual(dlg2.pill_9_16.property("active"), "true")
        self.assertEqual(dlg2.pill_free.property("active"), "false")
        self.assertAlmostEqual(dlg2.canvas.aspect_ratio, 9.0 / 16.0, places=4)
        dlg2.deleteLater()

    def test_title_bar_close_button_id_and_stylesheet_dedup(self):
        bar = CustomTitleBar()
        try:
            self.assertEqual(bar.close_btn.objectName(), "CloseButton")
            bar._drag_pos = QPoint(10, 10)
            bar.mouseReleaseEvent(_mouse_event(QEvent.MouseButtonRelease, QPointF(10, 10),
                                               button=Qt.LeftButton, buttons=Qt.NoButton))
            self.assertIsNone(bar._drag_pos)
        finally:
            bar.deleteLater()
        css = get_stylesheet(0.45)
        self.assertIn("#TitleButton, #CloseButton", css)
        self.assertEqual(css.count("QScrollBar:vertical"), 1)

    def test_smooth_widget_preserves_error_and_respects_toggle_state(self):
        widget = SmoothWidget()
        try:
            widget.toggle.setChecked(False)
            widget._downloading = True
            widget._on_download_status("Неверная контрольная сумма архива RIFE.")
            with patch("ui.smooth_widget.is_rife_available", return_value=False):
                widget._on_download_finished(False)
            self.assertFalse(widget._downloading)
            self.assertFalse(widget.engine_btn.isEnabled())
            self.assertIn("контрольная сумма", widget.status_lbl.text())
        finally:
            widget.deleteLater()

    def test_history_clear_requires_confirmation(self):
        from core.history import history
        previous_entries = copy.deepcopy(history.get_all())
        history.clear()
        history.add_entry("KeepMe", "https://example.test", "keep.mp4", "MP4")
        modal = HistoryModal()
        try:
            with patch("ui.history_view.QMessageBox.question", return_value=QMessageBox.No):
                modal._clear_history()
            self.assertEqual(len(history.get_all()), 1)
            with patch("ui.history_view.QMessageBox.question", return_value=QMessageBox.Yes):
                modal._clear_history()
            self.assertEqual(len(history.get_all()), 0)
        finally:
            modal.close()
            modal.deleteLater()
            history.history = previous_entries
            history.save()

    def test_video_card_center_crop_and_duration_icon_prefix(self):
        cards = VideoCardsListWidget()
        try:
            item_id = cards.add_video({"url": "v.mp4", "title": "V", "duration_str": "00:10"})
            card = cards.cards[0]
            # Vertical image: red top, green middle, blue bottom
            img = QImage(100, 300, QImage.Format_RGB32)
            img.fill(QColor(0, 255, 0))
            for y in range(100):
                for x in range(100):
                    img.setPixelColor(x, y, QColor(255, 0, 0))
            for y in range(200, 300):
                for x in range(100):
                    img.setPixelColor(x, y, QColor(0, 0, 255))
            card._on_image_loaded(img)
            center_color = card.thumb_label.pixmap().toImage().pixelColor(57, 36)
            self.assertGreater(center_color.green(), 200)
            self.assertLess(center_color.red(), 50)

            cards.update_card_info(item_id, {"duration_str": "01:23", "title": "Updated"})
            self.assertEqual(card.duration_badge.text(), "⏱ 01:23")
        finally:
            cards.deleteLater()

    def test_toggle_switch_disabled_ignores_click(self):
        sw = ToggleSwitch(checked=False)
        try:
            sw.setEnabled(False)
            sw.mousePressEvent(_mouse_event(QEvent.MouseButtonPress, QPointF(5, 5),
                                            button=Qt.LeftButton, buttons=Qt.LeftButton))
            self.assertFalse(sw.isChecked())
        finally:
            sw.deleteLater()

    def test_settings_modal_debounces_opacity_and_extracts_pip_error_tail(self):
        modal = SettingsModal()
        try:
            with patch.object(settings, "set", return_value=True) as set_mock:
                with patch.object(modal.slider, "isSliderDown", return_value=True):
                    modal._on_opacity_slider_changed(60)
                    modal._on_opacity_slider_changed(70)
                    set_mock.assert_not_called()
                modal._commit_opacity()
                set_mock.assert_called_once_with("glass_opacity", 0.70)
        finally:
            modal.close()
            modal.deleteLater()

        worker = UpdateYtdlpWorker()
        messages = []
        worker.finished_signal.connect(lambda msg, ok: messages.append((msg, ok)))
        proc = MagicMock()
        proc.returncode = 1
        proc.poll.return_value = 1
        proc.communicate.return_value = ("", "WARNING: pip old\nWARNING: other\nERROR: No matching distribution found for yt-dlp")
        with patch("subprocess.Popen", return_value=proc):
            worker.run()
        self.assertFalse(messages[0][1])
        self.assertIn("No matching distribution", messages[0][0])

    def test_dialogs_are_draggable_and_reset_drag_pos_on_release(self):
        dialogs = [
            SettingsModal(),
            PlaylistDialog({"title": "PL", "entries": []}),
            BatchDialog(),
        ]
        for dlg in dialogs:
            try:
                dlg.move(100, 100)
                press = _mouse_event(QEvent.MouseButtonPress, QPointF(10, 10),
                                     QPointF(110, 110), Qt.LeftButton, Qt.LeftButton)
                move = _mouse_event(QEvent.MouseMove, QPointF(40, 30),
                                    QPointF(140, 130), Qt.NoButton, Qt.LeftButton)
                release = _mouse_event(QEvent.MouseButtonRelease, QPointF(40, 30),
                                       QPointF(140, 130), Qt.LeftButton, Qt.NoButton)
                dlg.mousePressEvent(press)
                self.assertIsNotNone(dlg._drag_pos)
                dlg.mouseMoveEvent(move)
                dlg.mouseReleaseEvent(release)
                self.assertIsNone(dlg._drag_pos)
            finally:
                dlg.close()
                dlg.deleteLater()

    def test_progress_widget_hide_does_not_accumulate_connections(self):
        pw = ProgressWidget()
        try:
            before = pw.anim_opacity.receivers(SIGNAL("finished()"))
            self.assertEqual(before, 1)
            for _ in range(5):
                pw.hide_progress()
            pw.anim_opacity.stop()
            after = pw.anim_opacity.receivers(SIGNAL("finished()"))
            self.assertEqual(after, 1)
        finally:
            pw.deleteLater()

    def test_main_window_avif_gallery_and_single_dwm_init(self):
        window = MainWindow()
        window.notification_manager.show_download_complete = lambda **kw: None
        try:
            with patch("ui.main_window.apply_acrylic_effect") as acrylic:
                window.show()
                app.processEvents()
                window.hide()
                window.show()
                app.processEvents()
                self.assertEqual(acrylic.call_count, 1)

            with patch.object(window.progress_widget, "complete") as complete_mock:
                window._on_batch_summary({
                    "results": [{"mode": "AVIF", "file_path": "a.avif", "file_size_str": "10 KB"}],
                    "errors": [], "failed_items": [], "total": 1, "success_count": 1,
                })
            self.assertIn("Галерея", complete_mock.call_args.args[0]["mode"])
        finally:
            window.close()
            window.deleteLater()

    def test_playlist_and_gallery_item_click_does_not_drag_dialog(self):
        pl = PlaylistDialog({"title": "PL", "entries": [
            {"url": "https://example.test/1", "title": "One", "duration_str": "00:10"},
            {"url": "https://example.test/2", "title": "Two", "duration_str": "00:20"},
        ]})
        gal = InstagramGalleryDialog({"uploader": "tester", "items": [
            {"index": 1, "title": "Pic 1", "is_video": False},
            {"index": 2, "title": "Vid 2", "is_video": True},
        ]})
        try:
            pl_item = pl.item_widgets[0]
            self.assertTrue(pl_item.is_selected())
            pl_item.mousePressEvent(_mouse_event(QEvent.MouseButtonPress, QPointF(10, 10),
                                                 QPointF(10, 10), Qt.LeftButton, Qt.LeftButton))
            self.assertFalse(pl_item.is_selected())
            self.assertIsNone(pl._drag_pos)

            # Clicking dialog body below drag_height=60 must not start dragging
            pl.mousePressEvent(_mouse_event(QEvent.MouseButtonPress, QPointF(10, 120),
                                            QPointF(10, 120), Qt.LeftButton, Qt.LeftButton))
            self.assertIsNone(pl._drag_pos)

            gal_item = gal.item_widgets[0]
            self.assertTrue(gal_item.is_selected())
            gal_item.mousePressEvent(_mouse_event(QEvent.MouseButtonPress, QPointF(10, 10),
                                                  QPointF(10, 10), Qt.LeftButton, Qt.LeftButton))
            self.assertFalse(gal_item.is_selected())
            self.assertIsNone(gal._drag_pos)
        finally:
            pl.close()
            pl.deleteLater()
            gal.close()
            gal.deleteLater()

    def test_main_window_drop_event_rejects_invalid_url_schemes(self):
        window = MainWindow()
        try:
            bad_mime = QMimeData()
            bad_mime.setUrls([QUrl("mailto:user@example.com"), QUrl("javascript:alert(1)")])
            bad_event = MagicMock()
            bad_event.mimeData.return_value = bad_mime
            with patch.object(window, "_import_sources") as imp, \
                 patch.object(window, "_show_input_error") as show_err:
                window.dropEvent(bad_event)
            imp.assert_not_called()
            show_err.assert_called_once()

            ok_mime = QMimeData()
            ok_mime.setUrls([QUrl("https://example.com/watch?v=1")])
            ok_event = MagicMock()
            ok_event.mimeData.return_value = ok_mime
            with patch.object(window, "_import_sources") as imp:
                window.dropEvent(ok_event)
            imp.assert_called_once()
            self.assertEqual(imp.call_args.args[0], ["https://example.com/watch?v=1"])
        finally:
            window.close()
            window.deleteLater()

    def test_settings_modal_defaults_and_shared_recovery_dialogs(self):
        settings.settings.pop("auto_paste", None)
        settings.settings.pop("glass_opacity", None)
        modal = SettingsModal()
        pw = ProgressWidget()
        try:
            self.assertFalse(modal.clip_toggle.isChecked())
            self.assertEqual(modal.slider.value(), 45)
            self.assertEqual(modal.opacity_val_lbl.text(), "45%")

            with tempfile.TemporaryDirectory() as folder:
                rec1 = Path(folder) / ".aura_staging_1"
                rec2 = Path(folder) / ".aura_staging_2"
                rec1.mkdir()
                rec2.mkdir()
                (rec1 / "a.mp4").write_bytes(b"1")
                (rec2 / "b.mp4").write_bytes(b"2")

                with patch("ui.common_widgets.show_recovery_sessions_dialog") as shared_dlg:
                    pw._show_recovery_choice_dialog([str(rec1), str(rec2)])
                shared_dlg.assert_called_once()
                self.assertEqual(len(shared_dlg.call_args.args[1]), 2)

                with patch("core.media_converter.get_recovery_sessions", return_value=[{"path": str(rec1), "files": [], "is_accessible": True}]), \
                     patch("ui.settings_modal.show_recovery_sessions_dialog") as modal_dlg:
                    modal._open_recovery_dialog()
                modal_dlg.assert_called_once()
                self.assertIsNotNone(modal_dlg.call_args.kwargs.get("on_delete"))
        finally:
            modal.close()
            modal.deleteLater()
            pw.deleteLater()


if __name__ == "__main__":
    unittest.main()
