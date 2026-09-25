import os
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QApplication

from core.downloader import DownloadWorker
from core.media_converter import (
    get_unique_base_for_group, get_ffmpeg_path, get_ffprobe_path,
    get_video_codec, get_or_create_preview_proxy
)
from core.local_processor import get_local_media_info
from core.interpolator import get_video_fps
from core.unified_batch_worker import UnifiedBatchWorker

app = QApplication.instance() or QApplication([])


class TestAuditB5F077AFixes(unittest.TestCase):

    def test_subtitle_matching_stem_after_postprocessing(self):
        """Test that after video processing (e.g. crop), subtitles take the final video's stem."""
        save_dir = tempfile.mkdtemp()
        try:
            worker = DownloadWorker(
                "https://example.com/test",
                {'download_subs': True, 'crop_enabled': True, 'crop_params': {'x': 0, 'y': 0, 'w': 100, 'h': 100}},
                save_dir
            )

            completed_results = []
            worker.download_completed.connect(lambda res: completed_results.append(res))

            def fake_extract_info(url, download=True):
                staging_dirs = [os.path.join(save_dir, d) for d in os.listdir(save_dir) if d.startswith(".aura_staging_")]
                self.assertTrue(len(staging_dirs) > 0)
                staging = staging_dirs[0]
                raw_video = os.path.join(staging, "MyReel [123].mp4")
                sub_ru = os.path.join(staging, "MyReel [123].ru.srt")
                sub_en = os.path.join(staging, "MyReel [123].en.vtt")
                with open(raw_video, "wb") as f:
                    f.write(b"video_bytes")
                with open(sub_ru, "w", encoding="utf-8") as f:
                    f.write("1\n00:00:01 --> 00:00:02\nПривет")
                with open(sub_en, "w", encoding="utf-8") as f:
                    f.write("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello")
                worker._last_filename = raw_video
                return {'title': 'MyReel', 'ext': 'mp4'}

            with patch('core.downloader.yt_dlp.YoutubeDL') as mock_ytdl_cls, \
                 patch('core.downloader.crop_video') as mock_crop, \
                 patch('core.downloader.probe_video_stream', return_value=True):
                
                mock_ydl = MagicMock()
                mock_ydl.extract_info.side_effect = fake_extract_info
                mock_ydl.prepare_filename.return_value = "MyReel [123].mp4"
                mock_ytdl_cls.return_value.__enter__.return_value = mock_ydl

                def fake_crop(in_path, params, is_cancelled_cb=None):
                    base, ext = os.path.splitext(in_path)
                    cropped = f"{base}_crop{ext}"
                    with open(cropped, "wb") as f:
                        f.write(b"cropped_video_bytes")
                    return cropped

                mock_crop.side_effect = fake_crop

                worker.run()

            saved_files = os.listdir(save_dir)
            # Must contain MyReel [123]_crop.mp4, MyReel [123]_crop.ru.srt, MyReel [123]_crop.en.vtt
            self.assertIn("MyReel [123]_crop.mp4", saved_files)
            self.assertIn("MyReel [123]_crop.ru.srt", saved_files)
            self.assertIn("MyReel [123]_crop.en.vtt", saved_files)
            self.assertEqual(len(completed_results), 1)
        finally:
            shutil.rmtree(save_dir, ignore_errors=True)

    def test_shared_group_collision_stem_for_video_and_subtitles(self):
        """Test that when existing files conflict in save_dir, video and subtitles get the identical unique stem."""
        save_dir = tempfile.mkdtemp()
        try:
            # Create pre-existing file
            with open(os.path.join(save_dir, "Clip_crop.mp4"), "w") as f:
                f.write("existing")

            stem = get_unique_base_for_group(save_dir, "Clip_crop", ".mp4", [".ru.srt", ".en.vtt"])
            self.assertEqual(stem, "Clip_crop (1)")

            # Create conflict on the subtitle instead
            with open(os.path.join(save_dir, "Clip_crop (1).ru.srt"), "w") as f:
                f.write("existing sub")

            stem2 = get_unique_base_for_group(save_dir, "Clip_crop", ".mp4", [".ru.srt", ".en.vtt"])
            self.assertEqual(stem2, "Clip_crop (2)")
        finally:
            shutil.rmtree(save_dir, ignore_errors=True)

    def test_subtitle_move_failure_preserves_staging_dir(self):
        """Test that if subtitle moving fails, download_error is emitted and staging_dir is NOT deleted."""
        save_dir = tempfile.mkdtemp()
        try:
            worker = DownloadWorker("https://example.com/test", {'download_subs': True}, save_dir)
            err_calls = []
            done_calls = []
            worker.download_error.connect(lambda e: err_calls.append(e))
            worker.download_completed.connect(lambda r: done_calls.append(r))

            def fake_extract_info(url, download=True):
                staging_dirs = [os.path.join(save_dir, d) for d in os.listdir(save_dir) if d.startswith(".aura_staging_")]
                self.assertTrue(len(staging_dirs) > 0)
                staging = staging_dirs[0]
                raw_video = os.path.join(staging, "File.mp4")
                sub_ru = os.path.join(staging, "File.ru.srt")
                with open(raw_video, "wb") as f:
                    f.write(b"data")
                with open(sub_ru, "w", encoding="utf-8") as f:
                    f.write("subs")
                worker._last_filename = raw_video
                return {'title': 'File', 'ext': 'mp4'}

            with patch('core.downloader.yt_dlp.YoutubeDL') as mock_ytdl_cls, \
                 patch('core.downloader.probe_video_stream', return_value=True):
                
                mock_ydl = MagicMock()
                mock_ydl.extract_info.side_effect = fake_extract_info
                mock_ydl.prepare_filename.return_value = "File.mp4"
                mock_ytdl_cls.return_value.__enter__.return_value = mock_ydl

                # Force shutil.move to fail on the .srt file
                orig_move = shutil.move
                def fake_move(src, dst):
                    if str(src).endswith(".srt"):
                        raise OSError("Permission denied for test")
                    return orig_move(src, dst)

                with patch('core.downloader.shutil.move', side_effect=fake_move):
                    worker.run()

            self.assertEqual(len(done_calls), 0)
            self.assertEqual(len(err_calls), 1)
            self.assertIn("Permission denied", err_calls[0])

            # Staging directory must NOT be deleted so user can recover data
            staging_dirs = [os.path.join(save_dir, d) for d in os.listdir(save_dir) if d.startswith(".aura_staging_")]
            self.assertEqual(len(staging_dirs), 1)
            self.assertTrue(os.path.exists(os.path.join(staging_dirs[0], "File.ru.srt")))
            self.assertTrue(os.path.exists(os.path.join(staging_dirs[0], "File.mp4")), "File.mp4 must be rolled back into staging")
            self.assertFalse(os.path.exists(os.path.join(save_dir, "File.mp4")), "save_dir must not retain orphaned video")
        finally:
            shutil.rmtree(save_dir, ignore_errors=True)

    def test_complete_batch_failure_triggers_is_all_failed_summary(self):
        """Test that when 0/N items succeed in UnifiedBatchWorker, summary reports is_all_failed and preserves all failed_items."""
        save_dir = tempfile.mkdtemp()
        try:
            items = [
                {'url': 'https://example.com/item1', 'title': 'Item 1', 'custom_options': {'mode': 'audio_only'}},
                {'url': 'https://example.com/item2', 'title': 'Item 2', 'custom_options': {'crop_enabled': True}}
            ]
            worker = UnifiedBatchWorker(items, {'mode': 'best'}, save_dir)
            summaries = []
            worker.batch_summary.connect(lambda s: summaries.append(s))

            class AllFailWorker:
                def __init__(self):
                    self.download_completed = MagicMock()
                    self.download_completed.connect = lambda cb: None
                    self.download_error = MagicMock()
                    self.download_error.connect = lambda cb: setattr(self, '_on_err', cb)
                    self.progress_updated = MagicMock()
                    self.status_message = MagicMock()

                def run(self):
                    if hasattr(self, '_on_err'):
                        self._on_err("Network 500 error")

            with patch('core.unified_batch_worker.DownloadWorker', side_effect=lambda *args: AllFailWorker()):
                worker.run()

            self.assertEqual(len(summaries), 1)
            s = summaries[0]
            self.assertTrue(s['is_all_failed'])
            self.assertFalse(s['is_partial'])
            self.assertEqual(s['success_count'], 0)
            self.assertEqual(len(s['failed_items']), 2)
            # Custom options must be preserved
            self.assertEqual(s['failed_items'][0]['custom_options']['mode'], 'audio_only')
            self.assertTrue(s['failed_items'][1]['custom_options']['crop_enabled'])
        finally:
            shutil.rmtree(save_dir, ignore_errors=True)

    def test_portable_binary_paths_used_in_all_subprocesses(self):
        """Test that local_processor, interpolator, and media_converter use get_ffmpeg_path/get_ffprobe_path."""
        dummy_ffmpeg = r"C:\fake\portable\tools\ffmpeg.exe"
        dummy_ffprobe = r"C:\fake\portable\tools\ffprobe.exe"

        def fake_exists(p):
            if "aura_proxy_" in str(p) or "aura_thumb_" in str(p):
                return False
            return True

        with patch('core.media_converter.get_ffmpeg_path', return_value=dummy_ffmpeg), \
             patch('core.media_converter.get_ffprobe_path', return_value=dummy_ffprobe), \
             patch('core.interpolator.get_ffprobe_path', return_value=dummy_ffprobe), \
             patch('core.local_processor.get_ffmpeg_path', return_value=dummy_ffmpeg), \
             patch('subprocess.run') as mock_run, \
             patch('os.path.exists', side_effect=fake_exists):

            mock_run.return_value = MagicMock(returncode=0, stdout='h264\n')

            # 1. get_video_codec
            get_video_codec("video.mp4")
            self.assertEqual(mock_run.call_args[0][0][0], dummy_ffprobe)

            # 2. get_video_fps
            mock_run.return_value = MagicMock(returncode=0, stdout='30/1\n')
            get_video_fps("video.mp4")
            self.assertEqual(mock_run.call_args[0][0][0], dummy_ffprobe)

            # 3. get_or_create_preview_proxy for hevc
            with patch('core.media_converter.get_video_codec', return_value='hevc'):
                get_or_create_preview_proxy("video.mp4")
                self.assertEqual(mock_run.call_args[0][0][0], dummy_ffmpeg)

            # 4. get_local_media_info thumbnail generation
            with patch('core.local_processor.get_video_duration', return_value=5.0), \
                 patch('core.local_processor.get_video_dimensions', return_value=(1920, 1080)), \
                 patch('core.local_processor.get_video_fps', return_value=30.0):
                get_local_media_info("sample.mp4")
                self.assertEqual(mock_run.call_args[0][0][0], dummy_ffmpeg)


if __name__ == '__main__':
    unittest.main()
