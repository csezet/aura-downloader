import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

from core.downloader import DownloadWorker
from core.media_converter import cleanup_aura_temp_files


class TestAudit93f695bFixes(unittest.TestCase):
    def setUp(self):
        self.save_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.save_dir, ignore_errors=True)

    def test_network_failure_cleans_up_staging_and_part_file(self):
        """
        Problem 1: Verify that a network/download failure during yt-dlp (e.g. after video.mp4.part
        is created) does NOT leave .aura_staging_* on disk.
        """
        worker = DownloadWorker("https://example.com/network_fail", {}, self.save_dir)
        err_calls = []
        done_calls = []
        worker.download_error.connect(lambda e: err_calls.append(e))
        worker.download_completed.connect(lambda r: done_calls.append(r))

        def fake_extract_info_fail(url, download=True):
            staging_dirs = [os.path.join(self.save_dir, d) for d in os.listdir(self.save_dir) if d.startswith(".aura_staging_")]
            self.assertEqual(len(staging_dirs), 1, "Staging directory must exist during download")
            staging = staging_dirs[0]
            # Simulate a .part file left behind by network drop
            part_file = os.path.join(staging, "video.mp4.part")
            with open(part_file, "wb") as f:
                f.write(b"incomplete stream chunk data")
            # Simulate network failure
            raise OSError("Connection timed out (simulated network failure)")

        with patch('core.downloader.yt_dlp.YoutubeDL') as mock_ytdl_cls:
            mock_ydl = MagicMock()
            mock_ydl.extract_info.side_effect = fake_extract_info_fail
            mock_ytdl_cls.return_value.__enter__.return_value = mock_ydl

            worker.run()

        self.assertEqual(len(done_calls), 0)
        self.assertEqual(len(err_calls), 1)
        self.assertIn("Connection timed out", err_calls[0])

        # Verify that no .aura_staging_* directory remains in save_dir
        remaining_staging = [d for d in os.listdir(self.save_dir) if d.startswith(".aura_staging_")]
        self.assertEqual(len(remaining_staging), 0, "Staging directory must be removed after network failure")

    def test_cancellation_cleans_up_staging_directory(self):
        """
        Problem 1: Verify that user cancellation does NOT leave .aura_staging_* in save_dir.
        """
        worker = DownloadWorker("https://example.com/cancel_test", {}, self.save_dir)
        err_calls = []
        done_calls = []
        worker.download_error.connect(lambda e: err_calls.append(e))
        worker.download_completed.connect(lambda r: done_calls.append(r))

        def fake_extract_info_cancel(url, download=True):
            staging_dirs = [os.path.join(self.save_dir, d) for d in os.listdir(self.save_dir) if d.startswith(".aura_staging_")]
            self.assertEqual(len(staging_dirs), 1)
            staging = staging_dirs[0]
            with open(os.path.join(staging, "temp_stream.mp4"), "wb") as f:
                f.write(b"bytes")
            # User cancels
            worker.cancel()
            return {'title': 'Cancelled'}

        with patch('core.downloader.yt_dlp.YoutubeDL') as mock_ytdl_cls:
            mock_ydl = MagicMock()
            mock_ydl.extract_info.side_effect = fake_extract_info_cancel
            mock_ytdl_cls.return_value.__enter__.return_value = mock_ydl

            worker.run()

        self.assertEqual(len(done_calls), 0)
        self.assertEqual(len(err_calls), 0, "Cancellation should not emit download_error")

        remaining_staging = [d for d in os.listdir(self.save_dir) if d.startswith(".aura_staging_")]
        self.assertEqual(len(remaining_staging), 0, "Staging directory must be removed after cancellation")

    def test_group_move_rollback_on_subtitle_failure(self):
        """
        Problem 2: When video is moved and .srt move fails:
        1. Already moved video must be rolled back to staging_dir.
        2. save_dir must not retain an orphaned video.
        3. staging_dir must contain BOTH the video and .srt for user recovery.
        4. Staging directory must be preserved and its path reported in error.
        5. download_completed must NOT be emitted.
        """
        worker = DownloadWorker("https://example.com/test_video", {'download_subs': True}, self.save_dir)
        err_calls = []
        done_calls = []
        worker.download_error.connect(lambda e: err_calls.append(e))
        worker.download_completed.connect(lambda r: done_calls.append(r))

        created_staging_dir = []

        def fake_extract_info(url, download=True):
            staging_dirs = [os.path.join(self.save_dir, d) for d in os.listdir(self.save_dir) if d.startswith(".aura_staging_")]
            self.assertEqual(len(staging_dirs), 1)
            staging = staging_dirs[0]
            created_staging_dir.append(staging)
            raw_video = os.path.join(staging, "Video.mp4")
            sub_ru = os.path.join(staging, "Video.ru.srt")
            with open(raw_video, "wb") as f:
                f.write(b"video_binary_content")
            with open(sub_ru, "w", encoding="utf-8") as f:
                f.write("1\n00:00:01,000 --> 00:00:02,000\nHello")
            worker._last_filename = raw_video
            return {'title': 'Video', 'ext': 'mp4'}

        orig_move = shutil.move

        def fake_move(src, dst):
            # Fail only when moving the subtitle to save_dir
            if str(src).endswith(".ru.srt") and self.save_dir in str(dst):
                raise PermissionError("Access denied on subtitle destination")
            return orig_move(src, dst)

        with patch('core.downloader.yt_dlp.YoutubeDL') as mock_ytdl_cls, \
             patch('core.downloader.probe_video_stream', return_value=True), \
             patch('core.downloader.shutil.move', side_effect=fake_move):
            
            mock_ydl = MagicMock()
            mock_ydl.extract_info.side_effect = fake_extract_info
            mock_ydl.prepare_filename.return_value = "Video.mp4"
            mock_ytdl_cls.return_value.__enter__.return_value = mock_ydl

            worker.run()

        self.assertEqual(len(done_calls), 0, "No completion on move failure")
        self.assertEqual(len(err_calls), 1)
        self.assertIn("Сбой переноса файлов", err_calls[0])
        self.assertIn("Access denied on subtitle destination", err_calls[0])
        staging = created_staging_dir[0]
        self.assertIn(staging, err_calls[0], "Error message must report staging directory path for recovery")

        # save_dir must NOT contain Video.mp4 (it must have been rolled back!)
        save_dir_files = [f for f in os.listdir(self.save_dir) if not f.startswith(".aura_staging_")]
        self.assertEqual(len(save_dir_files), 0, f"save_dir should be empty, but found: {save_dir_files}")

        # staging_dir must be preserved and contain both files
        self.assertTrue(os.path.exists(staging), "Staging directory must be preserved for recovery")
        self.assertTrue(os.path.exists(os.path.join(staging, "Video.mp4")), "Video must be rolled back into staging")
        self.assertTrue(os.path.exists(os.path.join(staging, "Video.ru.srt")), "Subtitle must be preserved in staging")

    def test_multi_sidecar_rollback(self):
        """
        Problem 2: With video + multiple subtitles (.ru.srt, .en.vtt), failure on the last
        subtitle rolls back all previously transferred files in reverse order.
        """
        worker = DownloadWorker("https://example.com/multi_sub", {'download_subs': True}, self.save_dir)
        err_calls = []
        done_calls = []
        worker.download_error.connect(lambda e: err_calls.append(e))
        worker.download_completed.connect(lambda r: done_calls.append(r))

        created_staging_dir = []

        def fake_extract_info(url, download=True):
            staging = [os.path.join(self.save_dir, d) for d in os.listdir(self.save_dir) if d.startswith(".aura_staging_")][0]
            created_staging_dir.append(staging)
            with open(os.path.join(staging, "Clip.mp4"), "wb") as f:
                f.write(b"clip_data")
            with open(os.path.join(staging, "Clip.ru.srt"), "w", encoding="utf-8") as f:
                f.write("ru")
            with open(os.path.join(staging, "Clip.en.vtt"), "w", encoding="utf-8") as f:
                f.write("en")
            worker._last_filename = os.path.join(staging, "Clip.mp4")
            return {'title': 'Clip', 'ext': 'mp4'}

        orig_move = shutil.move

        def fake_move(src, dst):
            # Fail only on .en.vtt move
            if str(src).endswith(".en.vtt") and self.save_dir in str(dst):
                raise OSError("Disk full error on .vtt")
            return orig_move(src, dst)

        with patch('core.downloader.yt_dlp.YoutubeDL') as mock_ytdl_cls, \
             patch('core.downloader.probe_video_stream', return_value=True), \
             patch('core.downloader.shutil.move', side_effect=fake_move):
            
            mock_ydl = MagicMock()
            mock_ydl.extract_info.side_effect = fake_extract_info
            mock_ydl.prepare_filename.return_value = "Clip.mp4"
            mock_ytdl_cls.return_value.__enter__.return_value = mock_ydl

            worker.run()

        staging = created_staging_dir[0]
        # In save_dir, neither Clip.mp4 nor Clip.ru.srt should remain
        remaining_in_save = [f for f in os.listdir(self.save_dir) if not f.startswith(".aura_staging_")]
        self.assertEqual(len(remaining_in_save), 0)

        # In staging, all three must exist
        self.assertTrue(os.path.exists(os.path.join(staging, "Clip.mp4")))
        self.assertTrue(os.path.exists(os.path.join(staging, "Clip.ru.srt")))
        self.assertTrue(os.path.exists(os.path.join(staging, "Clip.en.vtt")))

    def test_cleanup_aura_temp_files_orphaned_staging(self):
        """
        Verify cleanup_aura_temp_files removes orphaned .aura_staging_* folders older than max_age_hours
        or when max_age_hours <= 0.
        """
        # Create an orphaned staging dir in self.save_dir
        old_staging = os.path.join(self.save_dir, ".aura_staging_old123")
        os.makedirs(old_staging, exist_ok=True)
        with open(os.path.join(old_staging, "stale.part"), "w") as f:
            f.write("stale")

        # Set mtime to 26 hours ago
        past_time = time.time() - (26 * 3600)
        os.utime(old_staging, (past_time, past_time))

        fresh_staging = os.path.join(self.save_dir, ".aura_staging_fresh456")
        os.makedirs(fresh_staging, exist_ok=True)

        # 1. Cleanup with max_age_hours=24 should delete old_staging, keep fresh_staging
        cleaned = cleanup_aura_temp_files(max_age_hours=24, extra_dirs=[self.save_dir])
        self.assertGreaterEqual(cleaned, 1)
        self.assertFalse(os.path.exists(old_staging))
        self.assertTrue(os.path.exists(fresh_staging))

        # 2. Cleanup with max_age_hours=0 should delete fresh_staging too
        cleaned2 = cleanup_aura_temp_files(max_age_hours=0, extra_dirs=[self.save_dir])
        self.assertGreaterEqual(cleaned2, 1)
        self.assertFalse(os.path.exists(fresh_staging))


if __name__ == '__main__':
    unittest.main()
