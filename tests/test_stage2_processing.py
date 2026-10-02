"""Real media regression checks; RIFE inference itself is simulated without a GPU."""
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image
from PySide6.QtWidgets import QApplication

from core import interpolator
from core.downloader import DownloadWorker, GalleryDownloadWorker
from core.local_processor import process_single_local_file, get_local_media_info
from core.media_converter import get_ffmpeg_path, get_ffprobe_path
from core.media_options import trim_range
from ui.progress_widget import ProgressWidget
from ui.smooth_widget import SmoothWidget


class TestProcessing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which(get_ffmpeg_path()) or not shutil.which(get_ffprobe_path()):
            raise unittest.SkipTest("FFmpeg/FFprobe required for media regression tests")
        cls.sandbox = tempfile.TemporaryDirectory()
        cls.root = Path(cls.sandbox.name)
        cls.source_dir = cls.root / "sources"
        cls.source_dir.mkdir()
        cls.source = cls.source_dir / "clip.mp4"
        cls.silent = cls.source_dir / "silent.mp4"
        cls.opus_source = cls.source_dir / "opus.webm"
        cls.fractional = cls.source_dir / "fractional.mp4"
        cls.portrait = cls.source_dir / "portrait.mp4"
        cls.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=2",
                   "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                   "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(cls.source))
        cls.ffmpeg("-i", str(cls.source), "-c:v", "copy", "-an", str(cls.silent))
        cls.ffmpeg("-i", str(cls.source), "-c:v", "libvpx-vp9", "-deadline", "realtime",
                   "-cpu-used", "8", "-c:a", "libopus", str(cls.opus_source))
        cls.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x64:rate=24000/1001:duration=1.5",
                   "-c:v", "libx264", "-preset", "ultrafast", str(cls.fractional))
        cls.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=240x320:rate=24:duration=1",
                   "-c:v", "libx264", "-preset", "ultrafast", str(cls.portrait))
        cls.original = {p.name: p.read_bytes() for p in cls.source_dir.iterdir()}

    @classmethod
    def tearDownClass(cls):
        cls.sandbox.cleanup()

    @classmethod
    def ffmpeg(cls, *arguments):
        result = subprocess.run([get_ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", *arguments],
                                capture_output=True, timeout=40, creationflags=0x08000000)
        if result.returncode:
            raise AssertionError(result.stderr.decode(errors="replace"))

    def setUp(self):
        self.output = Path(tempfile.mkdtemp(dir=self.root))

    def tearDown(self):
        self.assertEqual({p.name: p.read_bytes() for p in self.source_dir.iterdir()}, self.original)
        self.assertFalse(list(self.output.glob(".aura_staging_*")))
        self.assertFalse(list(self.output.glob("*.tmp.*")))

    def probe(self, path):
        result = subprocess.run([get_ffprobe_path(), "-v", "error", "-show_streams", "-show_format",
                                 "-of", "json", str(path)], capture_output=True, text=True, timeout=10,
                                creationflags=0x08000000)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def process(self, options, source=None):
        result = process_single_local_file(str(source or self.source), options, str(self.output))
        self.assertEqual(Path(result["file_path"]).parent, self.output)
        self.assertGreater(result["file_size"], 0)
        return result, self.probe(result["file_path"])

    @staticmethod
    def video(data):
        return next(s for s in data["streams"] if s["codec_type"] == "video")

    def test_all_audio_choices_encode_the_requested_codec(self):
        for extension, codec in (("mp3", "mp3"), ("flac", "flac"), ("m4a", "aac"),
                                 ("opus", "opus"), ("wav", "pcm_s16le")):
            with self.subTest(extension=extension):
                result, data = self.process({"mode": "audio_only", "audio_fmt": extension})
                self.assertTrue(result["file_path"].endswith("." + extension))
                self.assertEqual([s["codec_name"] for s in data["streams"]], [codec])

    def test_trim_crop_resolution_and_mute_are_applied_together(self):
        _, data = self.process({"mode": "video_only", "res": "80p", "trim_enabled": True,
                                "trim_start": "0.5", "trim_end": "1.5", "crop_enabled": True,
                                "crop_params": {"x_norm": .25, "y_norm": .25, "w_norm": .5, "h_norm": .5}})
        self.assertEqual((self.video(data)["width"], self.video(data)["height"]), (106, 80))
        self.assertEqual(len(data["streams"]), 1)
        self.assertAlmostEqual(float(data["format"]["duration"]), 1, delta=.08)

    def test_quality_labels_and_dimension_bounds_preserve_aspect_ratio(self):
        for resolution, source, expected in (("120p HD", self.source, (160, 120)),
                                             ("160x160", self.source, (160, 120)),
                                             ("120p", self.portrait, (90, 120)),
                                             ("1080p Full HD", self.source, (320, 240))):
            with self.subTest(resolution=resolution, source=source.name):
                _, data = self.process({"mode": "custom", "res": resolution}, source)
                self.assertEqual((self.video(data)["width"], self.video(data)["height"]), expected)

    def test_crop_gif_keeps_a_real_gif_and_selected_directory(self):
        result, data = self.process({"mode": "gif", "crop_enabled": True,
                                     "crop_params": {"x": 80, "y": 60, "w": 160, "h": 120}})
        self.assertEqual(Path(result["file_path"]).suffix, ".gif")
        self.assertEqual(self.video(data)["codec_name"], "gif")
        self.assertEqual((self.video(data)["width"], self.video(data)["height"]), (160, 120))
        with Image.open(result["file_path"]) as gif:
            self.assertGreater(gif.n_frames, 1)

    def test_audio_trim_does_not_require_video_encoding(self):
        _, data = self.process({"mode": "audio_only", "audio_fmt": "opus", "trim_enabled": True,
                                "trim_start": "0.5", "trim_end": "1.5"})
        self.assertAlmostEqual(float(data["format"]["duration"]), 1, delta=.05)

    def test_invalid_ranges_and_unknown_resolution_do_not_leave_outputs(self):
        for options in ({"trim_enabled": True, "trim_start": "oops"},
                        {"trim_enabled": True, "trim_start": "1.5", "trim_end": "1"},
                        {"trim_enabled": True, "trim_start": "5"},
                        {"mode": "custom", "res": "unknown"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                process_single_local_file(str(self.source), options, str(self.output))
        self.assertEqual(list(self.output.iterdir()), [])

    def test_existing_output_is_preserved_and_cancelled_processing_is_cleaned(self):
        old = self.output / "clip_aura.mp4"
        old.write_bytes(b"user file")
        self.process({"mode": "best"})
        self.assertEqual(old.read_bytes(), b"user file")
        calls = []
        def stop_after_first_pass():
            calls.append(True)
            return len(calls) > 4
        before = set(self.output.iterdir())
        result = process_single_local_file(str(self.source), {"mode": "gif"}, str(self.output),
                                          is_cancelled_cb=stop_after_first_pass)
        self.assertIsNone(result)
        self.assertEqual(set(self.output.iterdir()), before)

    def test_smooth_then_compress_respects_the_final_limit(self):
        _, data = self.process({"mode": "discord_8mb", "smooth_enabled": True, "smooth_fps": 0,
                                "smooth_model": "ffmpeg", "crop_enabled": True,
                                "crop_params": {"x": 0, "y": 0, "w": 160, "h": 120}})
        self.assertEqual(self.video(data)["avg_frame_rate"], "48/1")
        self.assertLessEqual(int(data["format"]["size"]), 7.8 * 1024 * 1024)
        self.assertAlmostEqual(float(data["format"]["duration"]), 2, delta=.06)

    def test_ffmpeg_interpolation_keeps_duration_audio_and_fractional_double_fps(self):
        for source, requested, expected in ((self.silent, 60, 60), (self.opus_source, 60, 60),
                                            (self.fractional, 0, 48000 / 1001)):
            with self.subTest(source=source.name):
                result = interpolator.interpolate_video(str(source), requested, "ffmpeg",
                                                         str(self.output / (source.stem + "_smooth.mp4")))
                data = self.probe(result)
                video = self.video(data)
                numerator, denominator = map(int, video["avg_frame_rate"].split("/"))
                self.assertAlmostEqual(numerator / denominator, expected, places=3)
                source_duration = float(self.probe(source)["format"]["duration"])
                self.assertAlmostEqual(float(data["format"]["duration"]), source_duration, delta=.08)
                self.assertEqual(any(s["codec_type"] == "audio" for s in data["streams"]), source == self.opus_source)

    def test_direct_video_download_applies_audio_and_gif_options(self):
        for mode, extension in (("audio_only", ".opus"), ("gif", ".gif")):
            with self.subTest(mode=mode):
                worker = DownloadWorker("https://cdn.example/clip.mp4",
                                        {"is_video": True, "mode": mode, "audio_fmt": "opus"}, str(self.output))
                completed, errors = [], []
                worker.download_completed.connect(completed.append)
                worker.download_error.connect(errors.append)
                response = MagicMock(headers={"content-length": str(self.source.stat().st_size)})
                response.iter_content.return_value = [self.source.read_bytes()]
                with patch("core.downloader.requests.get", return_value=response):
                    worker.run()
                self.assertEqual(errors, [])
                self.assertEqual(len(completed), 1)
                self.assertEqual(Path(completed[0]["file_path"]).suffix, extension)
                self.probe(completed[0]["file_path"])
                response.close.assert_called_once()

    def test_online_resize_crop_gif_and_final_compression(self):
        cases = ({"mode": "custom", "res": "120p"},
                 {"mode": "gif", "crop_enabled": True,
                  "crop_params": {"x": 0, "y": 0, "w": 160, "h": 120}},
                 {"mode": "discord_8mb", "smooth_enabled": True, "smooth_model": "ffmpeg",
                  "smooth_fps": 0, "crop_enabled": True,
                  "crop_params": {"x": 0, "y": 0, "w": 160, "h": 120}})
        for options in cases:
            with self.subTest(mode=options["mode"]):
                worker = DownloadWorker("https://example.test/video", options, str(self.output))
                completed, errors = [], []
                worker.download_completed.connect(completed.append)
                worker.download_error.connect(errors.append)
                def download(url, download=True):
                    stage = next(self.output.glob(".aura_staging_*"))
                    path = stage / "Online [123].mp4"
                    shutil.copyfile(self.source, path)
                    (stage / "Online [123].ru.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\ntext", encoding="utf-8")
                    worker._last_filename = str(path)
                    return {"title": "Online", "ext": "mp4"}
                ydl = MagicMock()
                ydl.extract_info.side_effect = download
                ydl.prepare_filename.return_value = "Online [123].mp4"
                with patch("core.downloader.yt_dlp.YoutubeDL") as factory:
                    factory.return_value.__enter__.return_value = ydl
                    worker.run()
                self.assertEqual(errors, [])
                self.assertEqual(len(completed), 1)
                path = Path(completed[0]["file_path"])
                data = self.probe(path)
                self.assertEqual((self.video(data)["width"], self.video(data)["height"]), (160, 120))
                self.assertTrue(path.with_suffix(".ru.srt").exists())
                if options["mode"] == "gif":
                    self.assertEqual(self.video(data)["codec_name"], "gif")
                    self.assertEqual(path.suffix, ".gif")
                elif options["mode"] == "discord_8mb":
                    self.assertEqual(self.video(data)["avg_frame_rate"], "48/1")
                    self.assertLessEqual(path.stat().st_size, 7.8 * 1024 * 1024)
                self.assertFalse(list(self.output.glob(".aura_staging_*")))

    def test_local_resolution_menu_offers_lower_sizes(self):
        large = self.root / "large.mp4"
        self.ffmpeg("-f", "lavfi", "-i", "color=size=640x480:duration=0.1", "-c:v", "libx264", str(large))
        info = get_local_media_info(str(large))
        self.assertEqual(info["available_res"], ["640x480", "360p"])

    def test_rife_model_frame_count_and_mux_with_silent_and_opus_sources(self):
        engine = self.root / "engine"
        engine.mkdir(exist_ok=True)
        exe = engine / "rife-ncnn-vulkan.exe"
        exe.touch()
        model = engine / "rife-v4.6"
        model.mkdir(exist_ok=True)
        (model / "flownet.param").touch()
        (model / "flownet.bin").touch()
        popen = subprocess.Popen
        commands = []
        def simulate_inference(command, *args, **kwargs):
            if command[0] != str(exe):
                return popen(command, *args, **kwargs)
            commands.append(command)
            frames = sorted(Path(command[command.index("-i") + 1]).glob("*.png"))
            count = int(command[command.index("-n") + 1])
            target = Path(command[command.index("-o") + 1])
            for i in range(count):
                shutil.copyfile(frames[min(len(frames) - 1, int(i * len(frames) / count))],
                                target / f"{i + 1:08d}.png")
            return SimpleNamespace(poll=lambda: 0, returncode=0)
        for source, requested, expected, total_frames in ((self.silent, 60, 60, 120),
                                                         (self.opus_source, 60, 60, 120),
                                                         (self.fractional, 0, 48000 / 1001, 72)):
            with self.subTest(source=source.name), \
                 patch("core.interpolator.get_rife_executable", return_value=str(exe)), \
                 patch("core.interpolator.subprocess.Popen", side_effect=simulate_inference), \
                 patch("core.interpolator.interpolate_with_ffmpeg", side_effect=AssertionError("unexpected fallback")):
                output = str(self.output / (source.stem + "_rife.mp4"))
                result = interpolator.interpolate_video(str(source), requested, "rife-v4.6", output)
                command = commands[-1]
                self.assertEqual(command[command.index("-m") + 1], str(model))
                self.assertEqual(int(command[command.index("-n") + 1]), total_frames)
                data = self.probe(result)
                self.assertAlmostEqual(interpolator.get_video_fps(result), expected, places=3)
                self.assertAlmostEqual(float(data["format"]["duration"]),
                                       float(self.probe(source)["format"]["duration"]), delta=.08)
                self.assertEqual(any(s["codec_type"] == "audio" for s in data["streams"]), source == self.opus_source)


class TestProcessingUI(unittest.TestCase):
    def test_smooth_widget_double_routes_to_rife_with_computed_source_fps(self):
        widget = SmoothWidget()
        widget.fps_combo.setCurrentIndex(2)
        with tempfile.NamedTemporaryFile(suffix=".mp4") as source, \
             patch("core.interpolator.get_video_fps", return_value=24000 / 1001), \
             patch("core.interpolator.interpolate_with_rife", return_value="result.mp4") as engine:
            interpolator.interpolate_video(source.name, widget.get_target_fps(), widget.get_model())
            self.assertAlmostEqual(engine.call_args.kwargs["target_fps"], 48000 / 1001)
            self.assertEqual(engine.call_args.kwargs["model"], "rife-v4.6")
        widget.deleteLater()

    def test_rife_fallback_is_visible_and_missing_double_fps_is_rejected(self):
        statuses = []
        with patch("core.interpolator.get_rife_executable", return_value=None), \
             patch("core.interpolator.interpolate_with_ffmpeg", return_value="result.mp4"):
            interpolator.interpolate_with_rife("clip.mp4", 60, status_callback=statuses.append)
        self.assertIn("FFmpeg", statuses[0])
        with patch("core.interpolator.get_video_fps", return_value=None), self.assertRaises(ValueError):
            interpolator.resolve_target_fps("clip.mp4", 0)

    def test_motion_interpolation_fallback_reports_frame_duplication(self):
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory) / "result.mp4")
            calls, statuses = [], []
            def ffmpeg(cmd, path, cancelled):
                calls.append(cmd)
                if len(calls) == 1:
                    raise RuntimeError("MCI unavailable")
                Path(path).write_bytes(b"video")
                return True
            with patch("core.interpolator.get_video_duration", return_value=2), \
                 patch("core.interpolator.run_ffmpeg_cancellable", side_effect=ffmpeg):
                interpolator.interpolate_with_ffmpeg("source.mp4", 60, output, status_callback=statuses.append)
            self.assertTrue(any("повторением кадров" in status for status in statuses))

    def test_gallery_progress_is_compatible_with_ui_and_partial_summary_is_correct(self):
        app = QApplication.instance() or QApplication([])
        widget = ProgressWidget()
        with tempfile.TemporaryDirectory() as directory:
            items = [{"id": "1", "media_type": "photo", "best_image": "https://cdn/ok.jpg"},
                     {"id": "2", "media_type": "photo", "best_image": "https://cdn/error.jpg"}]
            worker = GalleryDownloadWorker(items, directory)
            progress, summaries = [], []
            worker.progress_updated.connect(widget.update_progress)
            worker.progress_updated.connect(progress.append)
            worker.batch_summary.connect(summaries.append)
            jpeg = io.BytesIO()
            Image.new("RGB", (8, 8)).save(jpeg, format="JPEG")
            response = MagicMock(headers={})
            response.iter_content.return_value = [jpeg.getvalue()]
            with patch("core.downloader.requests.get", side_effect=[response, RuntimeError("CDN error")]):
                worker.run()
            app.processEvents()
            self.assertTrue(all(isinstance(p, dict) for p in progress))
            self.assertEqual(progress[0]["percent"], 0)
            self.assertEqual(progress[-1]["percent"], 50)
            self.assertEqual(summaries[0]["success_count"], 1)
            self.assertTrue(summaries[0]["is_partial"])
            self.assertEqual(summaries[0]["failed_items"], [items[1]])
            self.assertEqual(widget.progress_bar.value(), 50)
            response.close.assert_called_once()
        widget.deleteLater()

    def test_trim_parser_rejects_negative_and_nonfinite_values(self):
        for invalid in ("-1", "nan", "inf", "01:99", "01:00:60"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                trim_range({"trim_enabled": True, "trim_start": invalid})
