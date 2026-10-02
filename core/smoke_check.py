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
            from PySide6.QtGui import QFontDatabase, QFont
            fonts = Path(os.environ['SystemRoot']) / 'Fonts'
            for name in ('segoeui.ttf', 'segoeuib.ttf', 'consola.ttf', 'consolab.ttf'):
                QFontDatabase.addApplicationFont(str(fonts / name))
            app.setFont(QFont('Segoe UI', 10))
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
            submitted = []
            original_start_metadata = window._start_metadata_worker
            window._start_metadata_worker = lambda url, item_id=None: submitted.append(url)
            window.url_input.setText('https://example.test/manual')
            deadline = time.monotonic() + 0.65
            while time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
            checked("Pasted link waits for explicit submission", not submitted and window.cards_list.count() == 0)
            window._paste_and_fetch()
            checked("Insert button submits the entered link", submitted == ['https://example.test/manual'])
            window._start_metadata_worker = original_start_metadata

            from ui.trim_dialog import TrimDialog
            trim_dialog = TrimDialog(window, str(source), info['duration'], initial_start='0.2', initial_end='1')
            frames = []
            trim_dialog.video_widget.videoSink().videoFrameChanged.connect(
                lambda frame: frames.append(True) if frame.isValid() else None)
            trim_dialog.show()
            deadline = time.monotonic() + 15
            while not frames and time.monotonic() < deadline:
                app.processEvents()
                if trim_dialog._preview_loaded:
                    trim_dialog.player.play()
                time.sleep(0.01)
            checked("Trim preview decodes a real video frame", bool(frames))
            trim_dialog.player.pause()
            trim_dialog._apply()
            checked("Trim editor preserves subsecond selection", trim_dialog.applied_range == ('00:00.2', '00:01'))
            long_dialog = TrimDialog(window, duration_sec=1800)
            long_dialog._on_player_duration_changed(108_000_000)
            long_dialog._seek_to_ms(900_000)
            long_dialog._on_player_position_changed(108_900_000)
            checked("Half-hour timeline ignores absolute stream timestamps",
                    long_dialog.duration_ms == 1_800_000 and long_dialog.time_lbl.text() == '00:15:00 / 00:30:00')
            long_dialog.reject()
            # Exercise the same button and queue twice, using real HTTP download
            # and FFmpeg processing with both cards already present.
            from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
            from threading import Thread
            portrait = root / 'Вертикальное видео.mp4'
            execute([ffmpeg, '-y', '-i', str(source), '-vf', 'transpose=1',
                     '-c:v', 'libx264', '-c:a', 'aac', str(portrait)])
            portrait_info = get_local_media_info(str(portrait))
            bodies = {'/first.mp4': source.read_bytes(), '/second.mp4': portrait.read_bytes()}

            class VideoServer(BaseHTTPRequestHandler):
                def do_GET(self):
                    body = bodies.get(self.path)
                    if body is None:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header('Content-Type', 'video/mp4')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *args):
                    pass

            server = ThreadingHTTPServer(('127.0.0.1', 0), VideoServer)
            server_thread = Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            try:
                settings.set('download_dir', str(output))
                window.notification_manager.show_download_complete = lambda **kw: None
                for index, media_info in enumerate((info, portrait_info), 1):
                    url = f'http://127.0.0.1:{server.server_port}/' + ('first.mp4' if index == 1 else 'second.mp4')
                    window._add_queue_item({**media_info, 'url': url, 'is_local': False,
                                           'is_video': True, 'direct_media_url': url, 'title': f'Smoke download {index}'})
                first, second = window.cards_list.cards
                for card in (first, second):
                    window.cards_list._select_single(card.item_id)
                    if card is second:
                        window.crop_widget.toggle.setChecked(True)
                        window.crop_widget._crop_params = {'x_norm': 0, 'y_norm': 0, 'w_norm': 1, 'h_norm': .75}
                    checked('First download button ready' if card is first else 'Second download button ready',
                            window.download_btn.isEnabled())
                    window.download_btn.click()
                    deadline = time.monotonic() + 20
                    while window._queue_busy and time.monotonic() < deadline:
                        app.processEvents()
                        time.sleep(.01)
                    checked('First download saved' if card is first else 'Second download saved without clearing queue',
                            not window._queue_busy and card.result_path and Path(card.result_path).is_file())
                checked('Portrait crop has correct dimensions', get_video_dimensions(second.result_path) == (96, 96))
            finally:
                server.shutdown()
                server.server_close()
                server_thread.join(timeout=2)

            from ui.history_view import HistoryModal, HistoryItemWidget
            long_path = root / (('Длинное название файла ' * 8) + '.mp4')
            long_path.touch()
            history.add_entry('Создаем свою AI модель — длинное название ' * 5, 'https://example.test/video', str(long_path), 'MP4')
            history_dialog = HistoryModal(window)
            history_dialog.resize(580, 420)
            history_dialog.show()
            app.processEvents()
            rows = history_dialog.findChildren(HistoryItemWidget)
            checked('History buttons fit with long filenames',
                    history_dialog.list_container.width() <= history_dialog.scroll.viewport().width()
                    and rows and all(not hasattr(row, 'folder_btn') or
                                     row.folder_btn.geometry().right() <= history_dialog.scroll.viewport().width()
                                     for row in rows))
            history_dialog.close()
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
                from PySide6.QtCore import QUrl
                from PySide6.QtMultimedia import QMediaPlayer
                for widget in app.topLevelWidgets():
                    for player in widget.findChildren(QMediaPlayer):
                        player.stop()
                        player.setSource(QUrl())
                app.processEvents()
                shutdown_background_tasks()
                release_cache_session()
            import logging
            logging.shutdown()
            Path.home = original_home
            tempfile.tempdir = original_temp
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1
