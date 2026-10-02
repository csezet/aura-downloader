"""An offline end-to-end check inside the packaged app, isolated from user data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def smoke_main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", type=Path, required=True, metavar="REPORT.json")
    args = parser.parse_args(argv)
    report_path = args.smoke_test.resolve()
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False)), "checks": []}
    with tempfile.TemporaryDirectory(prefix="aura_smoke_") as temporary:
        root = Path(temporary)
        profile = root / "profile"
        profile.mkdir()
        scratch = root / "temp"
        scratch.mkdir()
        original_home = Path.home
        original_temp = tempfile.tempdir
        Path.home = classmethod(lambda cls: profile)
        tempfile.tempdir = str(scratch)
        os.environ.update(USERPROFILE=str(profile), LOCALAPPDATA=str(profile), APPDATA=str(profile),
                          TEMP=str(scratch), TMP=str(scratch), QT_QPA_PLATFORM="offscreen")
        app = None
        try:
            from core.app_logging import configure_logging, install_qt_logging
            from core.version import APP_VERSION
            log_path = configure_logging()
            from PySide6.QtWidgets import QApplication
            app = QApplication([])
            install_qt_logging()
            report["version"] = APP_VERSION
            from core.media_converter import (get_ffmpeg_path, get_ffprobe_path, check_ffmpeg_available,
                                               get_video_dimensions, get_video_duration)
            from core.js_runtime import get_deno_path, javascript_options
            from core.local_processor import process_single_local_file, get_local_media_info
            from core.settings import settings
            from core.history import history
            from core.workers import CancellableThread, start_worker, worker_registry
            from ui.main_window import MainWindow
            from ui.settings_modal import SettingsModal
            from PySide6.QtCore import QTimer
            from PySide6.QtGui import QIcon
            import yt_dlp
            import yt_dlp_ejs

            def checked(name, condition, detail=""):
                if not condition:
                    raise AssertionError(f"{name}: {detail}")
                report["checks"].append(name)

            def execute(command):
                result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                                        creationflags=0x08000000)
                if result.returncode:
                    raise RuntimeError(result.stderr[-1500:])
                return result.stdout

            ok, detail = check_ffmpeg_available()
            checked("FFmpeg and FFprobe run", ok, detail)
            ffmpeg, ffprobe = get_ffmpeg_path(), get_ffprobe_path()
            if report["frozen"]:
                bundle = Path(sys._MEIPASS).resolve()
                checked("Media tools come from the bundle", all(Path(p).resolve().is_relative_to(bundle) for p in (ffmpeg, ffprobe)))
            deno = get_deno_path()
            checked("Deno solves JavaScript without network", deno and execute([deno, "eval", "console.log(6 * 7)"]).strip() == "42")
            if report["frozen"]:
                checked("Deno comes from the bundle", Path(deno).resolve().is_relative_to(bundle))
            with yt_dlp.YoutubeDL({"quiet": True, **javascript_options()}) as downloader:
                checked("YouTube extractor and EJS are available", downloader.get_info_extractor("Youtube") is not None)
            from importlib.resources import files
            checked("EJS scripts are bundled", any(files("yt_dlp_ejs").rglob("*.js")))

            source = root / "Исходное видео с пробелами.mp4"
            execute([ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc2=size=128x96:rate=24:duration=1.2",
                     "-f", "lavfi", "-i", "sine=frequency=440:duration=1.2", "-shortest",
                     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)])
            original = hashlib.sha256(source.read_bytes()).hexdigest()
            output = root / "Результаты обработки"
            output.mkdir()
            info = get_local_media_info(str(source))
            checked("Metadata and thumbnail", info["width"] == 128 and info["height"] == 96 and Path(info["thumbnail"]).is_file())
            video = process_single_local_file(str(source), {"mode": "custom", "res": "64x64",
                                               "trim_enabled": True, "trim_start": "00:00.2", "trim_end": "00:01"}, str(output))
            checked("Trim and resize", video and get_video_dimensions(video["file_path"]) == (64, 48)
                    and abs(get_video_duration(video["file_path"]) - 0.8) < 0.2)
            audio = process_single_local_file(str(source), {"mode": "audio_only", "audio_fmt": "opus", "audio_quality": "128"}, str(output))
            codec = execute([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name",
                             "-of", "default=noprint_wrappers=1:nokey=1", audio["file_path"]]).strip()
            checked("Audio OPUS", codec == "opus")
            gif = process_single_local_file(str(source), {"mode": "gif"}, str(output))
            checked("GIF conversion", gif and Path(gif["file_path"]).is_file() and Path(gif["file_path"]).suffix == ".gif")
            checked("Source preserved", hashlib.sha256(source.read_bytes()).hexdigest() == original)
            settings.set("audio_format", "opus")
            history.add_entry("Smoke video", str(source), video["file_path"], "MP4")
            checked("Settings and history persist outside the app", (profile / ".aura_downloader" / "config.json").is_file()
                    and (profile / ".aura_downloader" / "history.json").is_file())
            assets = Path(__file__).resolve().parents[1] / "assets"
            icon = assets / "app_logo.ico"
            checked("Application icon", not QIcon(str(icon)).isNull())
            window = MainWindow(icon_path=str(icon))
            window.show()
            app.processEvents()
            checked("Main window renders", not window.grab().isNull())
            settings_dialog = SettingsModal(window)
            settings_dialog.show()
            app.processEvents()
            checked("Settings window renders", not settings_dialog.grab().isNull())
            if report["frozen"]:
                checked("Frozen updater uses releases", "обновления" in settings_dialog.btn_update_ytdlp.text())
            settings_dialog.close()

            class BackgroundJob(CancellableThread):
                def run(self):
                    while not self.isInterruptionRequested():
                        self.msleep(10)
            job = BackgroundJob()
            start_worker(job, window)
            QTimer.singleShot(50, window.close)
            deadline = time.monotonic() + 10
            while (window.isVisible() or worker_registry().is_busy()) and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
            checked("Window closing stops background tasks", not window.isVisible() and job.wait(0))
            checked("File journal created", log_path and log_path.is_file())
            report["ok"] = True
        except Exception as error:
            import traceback
            report["error"] = str(error)
            report["traceback"] = traceback.format_exc()
        finally:
            if app is not None:
                from core.workers import shutdown_background_tasks
                from core.temp_files import release_cache_session
                shutdown_background_tasks()
                release_cache_session()
            import logging
            logging.shutdown()
            Path.home = original_home
            tempfile.tempdir = original_temp
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1
