import io
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from core.app_logging import PrivateFormatter, LogStream
from core.js_runtime import javascript_options
from core.updater import check_latest_release, version_tuple
from core.version import RELEASES_URL
from ui.settings_modal import SettingsModal, UpdateYtdlpWorker, ReleaseCheckWorker


def release_response(tag="v1.2.0", **extra):
    response = MagicMock()
    response.status_code = 200
    response.__enter__.return_value = response
    response.json.return_value = {"tag_name": tag, "draft": False, "prerelease": False,
                                  "assets": [{"name": f"AuraDownloader-{tag}-windows-x64.zip"}], **extra}
    return response


class TestReleaseUpdates(unittest.TestCase):
    def test_only_newer_stable_windows_release_is_offered(self):
        for tag, expected in (("v1.2.0", True), ("v1.1.0", False), ("v1.0.6", False)):
            with self.subTest(tag=tag), patch("core.updater.requests.get", return_value=release_response(tag)) as request:
                result = check_latest_release("1.1.0")
                self.assertEqual(result["available"], expected)
                self.assertEqual(result["url"], RELEASES_URL)
                self.assertEqual(request.call_args.kwargs["timeout"], (5, 15))

    def test_missing_release_or_windows_archive_is_explained(self):
        response = release_response(assets=[])
        with patch("core.updater.requests.get", return_value=response):
            self.assertFalse(check_latest_release("1.1.0")["available"])
            self.assertIn("ещё не опубликована", check_latest_release("1.1.0")["message"])
        response.status_code = 404
        with patch("core.updater.requests.get", return_value=response):
            self.assertIn("пока нет", check_latest_release()["message"])

    def test_invalid_and_prerelease_tags_are_rejected(self):
        for value in ("1.1", "v1.1.0-rc1", "https://other.example/run.exe"):
            with self.assertRaises(ValueError):
                version_tuple(value)
        with patch("core.updater.requests.get", return_value=release_response(prerelease=True)):
            with self.assertRaises(ValueError):
                check_latest_release()

    def test_frozen_ytdlp_worker_never_executes_the_app_as_pip(self):
        worker = UpdateYtdlpWorker()
        messages = []
        worker.finished_signal.connect(lambda *args: messages.append(args))
        with patch.object(sys, "frozen", True, create=True), patch("subprocess.Popen") as process:
            worker.run()
        process.assert_not_called()
        self.assertFalse(messages[0][1])
        self.assertIn("релиз", messages[0][0])

    def test_frozen_settings_route_to_release_checker(self):
        with patch.object(sys, "frozen", True, create=True):
            modal = SettingsModal()
            try:
                with patch("ui.settings_modal.worker_registry") as registry, patch("ui.settings_modal.start_worker") as start:
                    registry.return_value.is_busy.return_value = False
                    modal._update_ytdlp()
                    self.assertIsInstance(modal.update_worker, ReleaseCheckWorker)
                    start.assert_called_once_with(modal.update_worker, modal)
                    self.assertIn("обновления", modal.btn_update_ytdlp.text())
            finally:
                modal.close()

    def test_release_check_cancellation_suppresses_late_result(self):
        entered, released = threading.Event(), threading.Event()
        def blocked():
            entered.set()
            released.wait(2)
            return {"available": True, "message": "new"}
        worker = ReleaseCheckWorker()
        messages = []
        worker.finished_signal.connect(lambda *args: messages.append(args))
        with patch("core.updater.check_latest_release", side_effect=blocked):
            worker.start()
            self.assertTrue(entered.wait(1))
            worker.cancel()
            released.set()
            self.assertTrue(worker.wait(2000))
        self.assertFalse(worker.update_available)
        self.assertEqual(messages, [])


class TestReleaseDiagnostics(unittest.TestCase):
    def test_build_does_not_resolve_dlls_from_unrelated_apps(self):
        from build_exe import clean_build_environment
        with patch.dict("os.environ", {"PATH": "C:/unrelated-app/bin", "PYTHONPATH": "C:/unrelated-python"}):
            environment = clean_build_environment()
        self.assertNotIn("unrelated-app", environment["PATH"])
        self.assertNotIn("PYTHONPATH", environment)
        self.assertIn("System32", environment["PATH"])

    def test_failed_exe_cannot_reuse_a_stale_success_report(self):
        from scripts.check_packaged_app import check_packaged_app
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / "app.exe"
            executable.write_bytes(b"binary")
            report = Path(folder) / "report.json"
            report.write_text(json.dumps({"ok": True, "frozen": True, "checks": []}), encoding="utf-8")
            with patch("scripts.check_packaged_app.subprocess.run", return_value=MagicMock(returncode=0)):
                with self.assertRaisesRegex(RuntimeError, "No diagnostic report"):
                    check_packaged_app(executable, report)

    def test_log_redacts_signed_urls_and_authorization_in_traceback(self):
        formatter = PrivateFormatter("%(message)s")
        try:
            raise RuntimeError("https://user:secret@cdn.example/video.mp4?token=private&sig=123")
        except RuntimeError:
            record = logging.LogRecord("test", logging.ERROR, __file__, 1,
                                       "Authorization: Bearer abc\nCookie=private", (), sys.exc_info())
        formatted = formatter.format(record)
        for value in ("secret", "private", "sig=123", "Bearer abc", "video.mp4"):
            self.assertNotIn(value, formatted)
        self.assertIn("RuntimeError", formatted)
        self.assertIn("cdn.example", formatted)

    def test_file_logging_rotates_without_losing_final_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "aura.log"
            handler = RotatingFileHandler(path, maxBytes=200, backupCount=2, encoding="utf-8")
            handler.setFormatter(PrivateFormatter("%(message)s"))
            logger = logging.getLogger("stage4.rotation")
            logger.setLevel(logging.ERROR)
            logger.addHandler(handler)
            try:
                for number in range(20):
                    logger.error("Проверка сохранённой ошибки %s", number)
            finally:
                logger.removeHandler(handler)
                handler.close()
            self.assertLessEqual(len(list(Path(folder).glob("aura.log*"))), 3)
            self.assertIn("19", path.read_text(encoding="utf-8"))

    def test_console_free_stream_preserves_partial_error_lines(self):
        with patch("core.app_logging.logging.getLogger") as logger:
            stream = LogStream(logging.ERROR)
            stream.write("Ошибка")
            logger.return_value.log.assert_not_called()
            stream.write(" потока\nСледующая")
            stream.flush()
            self.assertEqual(logger.return_value.log.call_count, 2)
            logger.return_value.log.assert_any_call(logging.ERROR, "Ошибка потока")
            logger.return_value.log.assert_any_call(logging.ERROR, "Следующая")

    def test_bundled_deno_is_configured_even_without_system_path(self):
        with tempfile.TemporaryDirectory() as folder:
            tools = Path(folder) / "tools"
            tools.mkdir()
            executable = tools / "deno.exe"
            executable.write_bytes(b"binary")
            with patch.object(sys, "_MEIPASS", folder, create=True), patch.dict("os.environ", {"PATH": ""}):
                self.assertEqual(Path(javascript_options()["js_runtimes"]["deno"]["path"]), executable)

    def test_archive_extraction_never_uses_member_paths_or_unexpected_files(self):
        from scripts.prepare_tools import extract_tools
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as package:
            for name in ("ffmpeg.exe", "ffprobe.exe", "LICENSE", "README.txt"):
                package.writestr("../../" + name, name)
            package.writestr("../../user-secret.txt", "extra")
        archive.seek(0)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "tools"
            extract_tools(archive, target)
            self.assertEqual({p.name for p in target.iterdir()},
                             {"ffmpeg.exe", "ffprobe.exe", "FFmpeg-LICENSE.txt", "FFmpeg-README.txt"})
            self.assertFalse((Path(folder) / "user-secret.txt").exists())

    def test_archive_requires_both_media_tools_and_notices_before_writing(self):
        from scripts.prepare_tools import extract_tools
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("ffmpeg.exe", "partial")
        archive.seek(0)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "tools"
            with self.assertRaises(ValueError):
                extract_tools(archive, target)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
