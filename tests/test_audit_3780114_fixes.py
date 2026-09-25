import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QApplication

from core.downloader import DownloadWorker
from core.media_converter import probe_video_stream, crop_video
from core.interpolator import interpolate_with_ffmpeg
from core.unified_batch_worker import UnifiedBatchWorker

app = QApplication.instance() or QApplication([])


class TestAudit3780114Fixes(unittest.TestCase):

    def test_probe_video_stream_rejects_audio_and_accepts_video(self):
        """Test that probe_video_stream accurately distinguishes video from audio/invalid data."""
        # Non-existent file
        self.assertFalse(probe_video_stream("non_existent_file.mp4"))

        # Simulated audio-only response from ffprobe (streams: [])
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='{"streams": []}')
            with patch('os.path.exists', return_value=True):
                self.assertFalse(probe_video_stream("audio.wav"))

        # Simulated audio stream returned instead of video (codec_type: 'audio')
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='{"streams": [{"codec_type": "audio"}]}')
            with patch('os.path.exists', return_value=True):
                self.assertFalse(probe_video_stream("audio.mp4"))

        # Simulated valid video stream
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{"streams": [{"codec_type": "video", "width": 1920, "height": 1080}]}'
            )
            with patch('os.path.exists', return_value=True):
                self.assertTrue(probe_video_stream("real_video.mp4"))

    @patch('core.downloader.yt_dlp.YoutubeDL')
    @patch('requests.get')
    def test_instagram_reel_page_url_routes_to_ytdlp_not_requests(self, mock_requests_get, mock_ytdl_cls):
        """Test that an Instagram Reel page URL (https://www.instagram.com/reel/Cxxxx/) is routed to yt-dlp, NOT requests.get."""
        save_dir = tempfile.mkdtemp()
        try:
            reel_url = "https://www.instagram.com/reel/C12345ABC/"
            options = {
                'is_video': True,
                'media_type': 'video',
                'title': 'Test Reel'
            }

            worker = DownloadWorker(reel_url, options, save_dir)

            mock_ydl_instance = MagicMock()
            mock_ydl_instance.extract_info.side_effect = Exception("Routed to yt-dlp")
            mock_ytdl_cls.return_value.__enter__.return_value = mock_ydl_instance

            worker.run()

            # Verify requests.get was NEVER called for the Reel page URL
            mock_requests_get.assert_not_called()
            # Verify yt_dlp was called
            self.assertTrue(mock_ydl_instance.extract_info.called)
        finally:
            import shutil
            shutil.rmtree(save_dir, ignore_errors=True)

    @patch('core.downloader.yt_dlp.YoutubeDL')
    def test_subtitles_and_sidecar_files_preserved_from_staging(self, mock_ytdl_cls):
        """Test that when yt-dlp produces video and .srt sidecar files in staging_dir, both are moved to save_dir."""
        save_dir = tempfile.mkdtemp()
        try:
            worker = DownloadWorker("https://www.youtube.com/watch?v=dummy", {'download_subs': True}, save_dir)

            completed_results = []
            worker.download_completed.connect(lambda res: completed_results.append(res))

            def fake_extract_info(url, download=True):
                # find staging dir in save_dir
                staging_dirs = [os.path.join(save_dir, d) for d in os.listdir(save_dir) if d.startswith(".aura_staging_")]
                self.assertTrue(len(staging_dirs) > 0)
                staging = staging_dirs[0]
                video_file = os.path.join(staging, "TestVideo.mp4")
                sub_ru = os.path.join(staging, "TestVideo.ru.srt")
                sub_en = os.path.join(staging, "TestVideo.en.srt")
                with open(video_file, "wb") as f:
                    f.write(b"dummy_video")
                with open(sub_ru, "w", encoding="utf-8") as f:
                    f.write("1\n00:00:01 --> 00:00:02\nПривет")
                with open(sub_en, "w", encoding="utf-8") as f:
                    f.write("1\n00:00:01 --> 00:00:02\nHello")
                worker._last_filename = video_file
                return {'title': 'TestVideo', 'ext': 'mp4'}

            mock_ydl_instance = MagicMock()
            mock_ydl_instance.extract_info.side_effect = fake_extract_info
            mock_ydl_instance.prepare_filename.return_value = "TestVideo.mp4"
            mock_ytdl_cls.return_value.__enter__.return_value = mock_ydl_instance

            worker.run()

            # Check that both video and subtitles exist in save_dir
            saved_files = os.listdir(save_dir)
            self.assertTrue(any(f.endswith(".mp4") for f in saved_files))
            self.assertTrue(any(f.endswith(".ru.srt") for f in saved_files))
            self.assertTrue(any(f.endswith(".en.srt") for f in saved_files))

            # Check matching stem
            video_name = [f for f in saved_files if f.endswith(".mp4")][0]
            stem = Path(video_name).stem
            self.assertIn(f"{stem}.ru.srt", saved_files)
            self.assertIn(f"{stem}.en.srt", saved_files)
        finally:
            import shutil
            shutil.rmtree(save_dir, ignore_errors=True)

    def test_crop_video_raises_exception_when_filter_fails(self):
        """Test that crop_video raises an Exception instead of returning input_path when crop calculation fails."""
        with patch('core.media_converter.os.path.exists', return_value=True), \
             patch('core.media_converter.get_crop_filter', return_value=""):
            with self.assertRaises(Exception) as ctx:
                crop_video("dummy.mp4", {'x': 0, 'y': 0, 'w': 100, 'h': 100})
            self.assertIn("Не удалось кадрировать", str(ctx.exception))

    def test_interpolate_with_ffmpeg_raises_exception_when_both_passes_fail(self):
        """Test that interpolate_with_ffmpeg raises Exception on failure rather than silently returning input_path."""
        with patch('core.interpolator.os.path.exists', return_value=True), \
             patch('core.interpolator.run_ffmpeg_cancellable', side_effect=[Exception("MCI Error"), Exception("FPS Error")]):
            with self.assertRaises(Exception) as ctx:
                interpolate_with_ffmpeg("dummy.mp4", target_fps=60)
            self.assertIn("Не удалось выполнить увеличение плавности", str(ctx.exception))

    def test_unified_batch_worker_tracks_failed_items_for_retry(self):
        """Test that failed items in UnifiedBatchWorker are preserved in self.failed_items for retrying."""
        save_dir = tempfile.mkdtemp()
        try:
            items = [
                {'url': 'https://example.com/ok_video', 'title': 'Good Video'},
                {'url': 'https://example.com/fail_video', 'title': 'Broken Video'}
            ]
            worker = UnifiedBatchWorker(items, {'mode': 'best'}, save_dir)

            captured_summaries = []
            worker.batch_summary.connect(lambda s: captured_summaries.append(s))

            class FakeWorker:
                def __init__(self, should_succeed):
                    self.should_succeed = should_succeed
                    self._on_done = None
                    self._on_err = None
                    self.download_completed = MagicMock()
                    self.download_completed.connect = lambda cb: setattr(self, '_on_done', cb)
                    self.download_error = MagicMock()
                    self.download_error.connect = lambda cb: setattr(self, '_on_err', cb)
                    self.progress_updated = MagicMock()
                    self.status_message = MagicMock()

                def run(self):
                    if self.should_succeed and self._on_done:
                        self._on_done({'file_path': os.path.join(save_dir, 'good.mp4'), 'title': 'Good Video'})
                    elif not self.should_succeed and self._on_err:
                        self._on_err("404 Not Found")

            def mock_download_worker(url, opts, s_dir):
                return FakeWorker(should_succeed=("ok_video" in url))

            with patch('core.unified_batch_worker.DownloadWorker', side_effect=mock_download_worker):
                worker.run()

            self.assertEqual(len(worker.results), 1)
            self.assertEqual(len(worker.errors), 1)
            self.assertEqual(len(worker.failed_items), 1)
            self.assertEqual(worker.failed_items[0]['title'], 'Broken Video')
            self.assertEqual(len(captured_summaries), 1)
            self.assertEqual(len(captured_summaries[0]['failed_items']), 1)
        finally:
            import shutil
            shutil.rmtree(save_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
