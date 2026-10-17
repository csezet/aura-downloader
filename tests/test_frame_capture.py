import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
from threading import Thread
import time
import unittest
from unittest.mock import patch, MagicMock

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from core.frame_capture import FrameCaptureSession, CaptureCancelled, save_frame
from core.media_converter import get_ffmpeg_path
from core.workers import worker_registry
from ui.trim_dialog import TrimDialog
from test_stage3_queue import pump_until


class TestOriginalFrames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.root = Path(cls.folder.name)
        cls.source = cls.root / 'Исходный ролик.mp4'
        cls.proxy = cls.root / 'small.mp4'
        cls.offset = cls.root / 'offset.mp4'
        cls.vfr = cls.root / 'vfr.mkv'
        cls.ffmpeg = get_ffmpeg_path()
        cls.execute(['-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30:duration=3',
                     '-c:v', 'libx264', '-g', '30', str(cls.source)])
        cls.execute(['-i', str(cls.source), '-vf', 'scale=80:46', '-c:v', 'libx264', str(cls.proxy)])
        cls.execute(['-i', str(cls.source), '-c', 'copy', '-output_ts_offset', '3600', str(cls.offset)])
        cls.execute(['-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=10:duration=2',
                     '-vf', 'setpts=if(lt(N\\,10)\\,N\\,10+2*(N-10))',
                     '-c:v', 'ffv1', '-fps_mode', 'vfr', str(cls.vfr)])

    @classmethod
    def execute(cls, arguments):
        result = subprocess.run([cls.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', *arguments],
                                capture_output=True, creationflags=0x08000000, timeout=25)
        if result.returncode:
            raise RuntimeError(result.stderr.decode('utf-8', 'replace'))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        self.session = FrameCaptureSession(str(self.source))

    def tearDown(self):
        self.session.close()

    def test_previous_and_next_are_real_adjacent_frames(self):
        frame = self.session.capture(1.005)
        after = self.session.capture(frame['position'], 1)
        before = self.session.capture(after['position'], -1)
        self.assertAlmostEqual(frame['position'], 1, places=5)
        self.assertAlmostEqual(after['position'], 31/30, places=5)
        self.assertEqual(Path(frame['path']).read_bytes(), Path(before['path']).read_bytes())
        reference = self.root / 'expected.png'
        self.execute(['-i', str(self.source), '-vf', 'select=eq(n\\,31)', '-frames:v', '1', str(reference)])
        with Image.open(after['path']) as actual, Image.open(reference) as expected:
            self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_vfr_steps_use_frame_timestamps_instead_of_average_fps(self):
        with_session = FrameCaptureSession(str(self.vfr))
        try:
            at_one = with_session.capture(1.01)
            after = with_session.capture(at_one['position'], 1)
            before = with_session.capture(after['position'], -1)
            self.assertAlmostEqual(at_one['position'], 1.0, places=3)
            self.assertAlmostEqual(after['position'], 1.2, places=3)
            self.assertAlmostEqual(before['position'], 1.0, places=3)
        finally:
            with_session.close()

    def test_offset_start_and_video_boundaries_remain_relative(self):
        session = FrameCaptureSession(str(self.offset))
        try:
            frame = session.capture(1, 1)
            self.assertAlmostEqual(frame['position'], 31/30, places=5)
            self.assertEqual(session.capture(0, -1)['position'], 0)
            last = session.capture(3, 1)
            self.assertAlmostEqual(last['position'], 89/30, places=5)
        finally:
            session.close()

    def test_png_keeps_original_pixels_and_jpeg_keeps_dimensions(self):
        original_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        frame = self.session.capture(.5)
        with tempfile.TemporaryDirectory() as folder:
            png, jpg = Path(folder) / 'Фото.png', Path(folder) / 'Фото.jpg'
            save_frame(frame, png)
            save_frame(frame, jpg)
            self.assertEqual(png.read_bytes(), Path(frame['path']).read_bytes())
            with Image.open(jpg) as image:
                self.assertEqual(image.size, (320, 180))
            png.write_bytes(b'existing')
            with self.assertRaises(CaptureCancelled):
                save_frame(frame, png, lambda: True)
            self.assertEqual(png.read_bytes(), b'existing')
            self.assertEqual(sorted(file.name for file in Path(folder).iterdir()), ['Фото.jpg', 'Фото.png'])
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), original_hash)

    def test_best_network_stream_is_used_separately_from_preview(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(handler):
                body = self.source.read_bytes()
                start = int(handler.headers.get('Range', 'bytes=0-').split('=')[1].split('-')[0])
                partial = 'Range' in handler.headers
                handler.send_response(206 if partial else 200)
                handler.send_header('Accept-Ranges', 'bytes')
                if partial:
                    handler.send_header('Content-Range', f'bytes {start}-{len(body)-1}/{len(body)}')
                handler.send_header('Content-Length', str(len(body) - start))
                handler.end_headers()
                handler.wfile.write(body[start:])

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        session = FrameCaptureSession({'url': 'https://example.test/page', 'preview_url': str(self.proxy)})
        try:
            with patch('yt_dlp.YoutubeDL') as factory:
                downloader = factory.return_value.__enter__.return_value
                downloader.extract_info.return_value = {'url': f'http://127.0.0.1:{server.server_port}/source.mp4',
                                                       'vcodec': 'h264', 'http_headers': {}}
                downloader.cookiejar.get_cookie_header.return_value = None
                frame = session.capture(.5)
                self.assertEqual(factory.call_args.args[0]['format'], 'bestvideo/best')
                self.assertFalse(downloader.extract_info.call_args.kwargs['download'])
            self.assertEqual((frame['width'], frame['height']), (320, 180))
        finally:
            session.close()
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_dialog_buttons_save_original_with_open_actions_and_no_trim_change(self):
        worker_registry().stopping = False
        dialog = TrimDialog(video_source=str(self.proxy), duration_sec=3,
                            capture_source={'url': str(self.source), 'title': 'Test video'})
        original_range = (dialog.start_ms, dialog.end_ms)
        try:
            dialog.show()
            dialog._seek_to_ms(1000)
            QTest.mouseClick(dialog.btn_next_frame, Qt.LeftButton)
            self.assertTrue(pump_until(lambda: not dialog._frame_busy, timeout=15))
            self.assertIsNotNone(dialog._frame_result, dialog.frame_status.text())
            self.assertAlmostEqual(dialog._frame_result['position'], 31/30, places=5)
            self.assertEqual(dialog.video_stack.currentWidget(), dialog.frame_preview)
            dialog._on_player_position_changed(2000)
            self.assertEqual(dialog.current_pos_ms, 1033)
            with tempfile.TemporaryDirectory() as folder:
                output = str(Path(folder) / 'Saved photo.png')
                with patch('ui.trim_dialog.QFileDialog.getSaveFileName', return_value=(output, 'PNG')):
                    QTest.mouseClick(dialog.btn_save_frame, Qt.LeftButton)
                self.assertTrue(pump_until(lambda: not dialog._frame_busy, timeout=15))
                with Image.open(output) as image:
                    self.assertEqual(image.size, (320, 180))
                self.assertFalse(dialog.btn_open_frame.isHidden())
                with patch('ui.trim_dialog.QDesktopServices.openUrl') as open_url:
                    QTest.mouseClick(dialog.btn_open_frame, Qt.LeftButton)
                    self.assertEqual(Path(open_url.call_args.args[0].toLocalFile()), Path(output))
                    QTest.mouseClick(dialog.btn_frame_folder, Qt.LeftButton)
                    self.assertEqual(Path(open_url.call_args.args[0].toLocalFile()), Path(folder))
            self.assertEqual((dialog.start_ms, dialog.end_ms), original_range)
            self.assertIsNone(dialog.applied_range)
            dialog._seek_to_ms(2000)
            self.assertEqual(dialog.video_stack.currentWidget(), dialog.video_widget)
        finally:
            dialog.reject()
            self.assertTrue(pump_until(lambda: not dialog.isVisible(), timeout=15))
            dialog.deleteLater()

    def test_closing_during_frame_capture_cancels_worker_before_cleanup(self):
        worker_registry().stopping = False
        dialog = TrimDialog(video_source=str(self.source), duration_sec=3)
        entered = []

        def wait_for_cancel(session, position, direction, cancelled, status):
            entered.append(True)
            deadline = time.monotonic() + 5
            while not cancelled() and time.monotonic() < deadline:
                time.sleep(.005)
            raise CaptureCancelled()

        dialog.show()
        with patch.object(FrameCaptureSession, 'capture', wait_for_cancel):
            dialog._request_frame(1)
            self.assertTrue(pump_until(lambda: bool(entered)))
            dialog.reject()
            self.assertTrue(pump_until(lambda: not dialog.isVisible() and dialog._frame_session is None))
        self.assertTrue(dialog._frame_worker.wait(0))
        dialog.deleteLater()
