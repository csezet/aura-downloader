import os
import shutil
import tempfile
import time
import json
import unittest
from unittest.mock import patch, MagicMock

from core.downloader import DownloadWorker
from core.media_converter import cleanup_aura_temp_files, is_recovery_staging_dir


class TestAudit46830EDFixes(unittest.TestCase):
    def setUp(self):
        self.save_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.save_dir, ignore_errors=True)

    def test_full_chain_move_failure_shutdown_and_startup(self):
        """
        Audit Requirement 31 & 35:
        Verify entire chain:
        1. Subtitle move fails.
        2. Rollback returns video to staging.
        3. .aura_recovery.json is created.
        4. Application shutdown (cleanup_aura_temp_files(max_age_hours=0) as in main.py) DOES NOT delete files.
        5. Next day startup (cleanup_aura_temp_files(max_age_hours=24)) DOES NOT delete files even after 24h.
        6. Video and subtitles remain fully accessible for user recovery.
        """
        worker = DownloadWorker("https://example.com/chain_test", {'download_subs': True}, self.save_dir)
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
            raw_video = os.path.join(staging, "File.mp4")
            sub_ru = os.path.join(staging, "File.ru.srt")
            with open(raw_video, "wb") as f:
                f.write(b"video_bytes_12345")
            with open(sub_ru, "w", encoding="utf-8") as f:
                f.write("1\n00:00:00,000 --> 00:00:01,000\nSub")
            worker._last_filename = raw_video
            return {'title': 'File', 'ext': 'mp4'}

        orig_move = shutil.move

        def fake_move(src, dst):
            if str(src).endswith(".ru.srt") and self.save_dir in str(dst):
                raise PermissionError("Access denied on subtitle destination (simulated)")
            return orig_move(src, dst)

        with patch('core.downloader.yt_dlp.YoutubeDL') as mock_ytdl_cls, \
             patch('core.downloader.probe_video_stream', return_value=True), \
             patch('core.downloader.shutil.move', side_effect=fake_move):
            
            mock_ydl = MagicMock()
            mock_ydl.extract_info.side_effect = fake_extract_info
            mock_ydl.prepare_filename.return_value = "File.mp4"
            mock_ytdl_cls.return_value.__enter__.return_value = mock_ydl

            worker.run()

        # Step 1: verify failure and error reporting
        self.assertEqual(len(done_calls), 0)
        self.assertEqual(len(err_calls), 1)
        self.assertIn("Сбой переноса файлов", err_calls[0])
        self.assertIn("открыть эту папку в Проводнике", err_calls[0])

        staging = created_staging_dir[0]
        self.assertTrue(os.path.exists(staging))

        # Step 2: verify .aura_recovery.json was generated
        recovery_marker = os.path.join(staging, ".aura_recovery.json")
        self.assertTrue(os.path.exists(recovery_marker), ".aura_recovery.json must be created")
        with open(recovery_marker, "r", encoding="utf-8") as rf:
            rec_data = json.load(rf)
        self.assertIn("timestamp", rec_data)
        self.assertIn("error", rec_data)
        self.assertEqual(rec_data["save_dir"], self.save_dir)
        file_names = [f["name"] for f in rec_data["files"]]
        self.assertIn("File.mp4", file_names)
        self.assertIn("File.ru.srt", file_names)

        # Step 3: Simulate application shutdown (app.aboutToQuit -> cleanup_aura_temp_files(max_age_hours=0))
        cleaned = cleanup_aura_temp_files(max_age_hours=0, extra_dirs=[self.save_dir])
        self.assertTrue(os.path.exists(staging), "Recovery staging dir must survive app.aboutToQuit / cache clear")
        self.assertTrue(os.path.exists(os.path.join(staging, "File.mp4")), "File.mp4 must survive")
        self.assertTrue(os.path.exists(os.path.join(staging, "File.ru.srt")), "File.ru.srt must survive")

        # Step 4: Simulate next day startup (cleanup_aura_temp_files(max_age_hours=24)) after 48 hours
        past_time = time.time() - (48 * 3600)
        os.utime(staging, (past_time, past_time))
        cleanup_aura_temp_files(max_age_hours=24, extra_dirs=[self.save_dir])
        self.assertTrue(os.path.exists(staging), "Recovery staging dir must NOT be deleted even after 24 hours")
        self.assertTrue(os.path.exists(os.path.join(staging, "File.mp4")))
        self.assertTrue(os.path.exists(os.path.join(staging, "File.ru.srt")))

    def test_unprotected_staging_dir_with_part_is_cleaned_immediately(self):
        """
        Audit Requirement 32 & 33:
        Staging dir with .part file or without recovery marker must be cleaned by cleanup_aura_temp_files.
        """
        trash_staging = os.path.join(self.save_dir, ".aura_staging_trash_abort")
        os.makedirs(trash_staging, exist_ok=True)
        with open(os.path.join(trash_staging, "video.mp4.part"), "wb") as f:
            f.write(b"part data")

        self.assertFalse(is_recovery_staging_dir(trash_staging), "Trash dir with .part is not recovery dir")

        # Calling cleanup_aura_temp_files(0) should clean it
        cleaned = cleanup_aura_temp_files(max_age_hours=0, extra_dirs=[self.save_dir])
        self.assertGreaterEqual(cleaned, 1)
        self.assertFalse(os.path.exists(trash_staging), "Trash staging dir must be deleted")

    def test_safety_fallback_completed_media_protected_without_marker(self):
        """
        Audit Requirement 28:
        If creating marker failed, but directory contains completed media files (e.g. .mp4, .srt)
        and no .part files, it must still be protected from automated deletion.
        """
        safe_staging = os.path.join(self.save_dir, ".aura_staging_safe_nomarker")
        os.makedirs(safe_staging, exist_ok=True)
        with open(os.path.join(safe_staging, "Movie.mp4"), "wb") as f:
            f.write(b"valid_video_data")
        with open(os.path.join(safe_staging, "Movie.ru.srt"), "w", encoding="utf-8") as f:
            f.write("subtitles")

        self.assertTrue(is_recovery_staging_dir(safe_staging), "Completed media without .part is protected")

        # cleanup(0) should NOT delete it
        cleanup_aura_temp_files(max_age_hours=0, extra_dirs=[self.save_dir])
        self.assertTrue(os.path.exists(safe_staging), "Directory with completed media must survive cleanup")

    def test_clear_cache_preserves_recovery_files_and_cleans_proxies(self):
        """
        Audit Requirement 34:
        'Clear Cache' button in Settings clears temporary proxies/thumbs/crops but preserves recovery staging.
        """
        # Create temp files in tempdir
        temp_dir = tempfile.gettempdir()
        proxy_file = os.path.join(temp_dir, "aura_proxy_test_123.mp4")
        with open(proxy_file, "wb") as f:
            f.write(b"proxy")

        # Create recovery staging in save_dir
        rec_staging = os.path.join(self.save_dir, ".aura_staging_recovery_btn")
        os.makedirs(rec_staging, exist_ok=True)
        with open(os.path.join(rec_staging, ".aura_recovery.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(rec_staging, "File.mp4"), "wb") as f:
            f.write(b"video")

        cleaned = cleanup_aura_temp_files(max_age_hours=0, extra_dirs=[self.save_dir])
        self.assertFalse(os.path.exists(proxy_file), "Proxy file must be cleaned")
        self.assertTrue(os.path.exists(rec_staging), "Recovery staging must be preserved")
        self.assertTrue(os.path.exists(os.path.join(rec_staging, "File.mp4")))


if __name__ == '__main__':
    unittest.main()
