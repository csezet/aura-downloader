import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from core.downloader import DownloadWorker
from core.media_converter import is_recovery_staging_dir, cleanup_aura_temp_files, get_recovery_sessions
from core.unified_batch_worker import UnifiedBatchWorker
from ui.progress_widget import ProgressWidget
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


class TestAudit58B7D23Fixes(unittest.TestCase):
    def setUp(self):
        self.save_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.save_dir, ignore_errors=True)

    def test_single_download_error_activates_open_dir_btn_and_shows_path(self):
        """
        Audit Requirement 35:
        Single download: subtitle move failure sets recovery_dir in ProgressWidget,
        displays active '📂 ОТКРЫТЬ ПАПКУ' button, full path in tooltip, and status text.
        """
        widget = ProgressWidget()
        worker = DownloadWorker("https://example.com/test_single_err", {'download_subs': True}, self.save_dir)

        captured_recovery = []
        worker.recovery_available.connect(lambda info: captured_recovery.append(info))

        def fake_extract_info(url, download=True):
            staging_dirs = [os.path.join(self.save_dir, d) for d in os.listdir(self.save_dir) if d.startswith(".aura_staging_")]
            self.assertEqual(len(staging_dirs), 1)
            staging = staging_dirs[0]
            with open(os.path.join(staging, "Movie.mp4"), "wb") as f:
                f.write(b"data")
            with open(os.path.join(staging, "Movie.ru.srt"), "w", encoding="utf-8") as f:
                f.write("sub")
            worker._last_filename = os.path.join(staging, "Movie.mp4")
            return {'title': 'Movie', 'ext': 'mp4'}

        orig_move = shutil.move
        def fake_move(src, dst):
            if str(src).endswith(".ru.srt") and self.save_dir in str(dst):
                raise PermissionError("Access denied (test)")
            return orig_move(src, dst)

        with patch('core.downloader.yt_dlp.YoutubeDL') as mock_ytdl_cls, \
             patch('core.downloader.probe_video_stream', return_value=True), \
             patch('core.downloader.shutil.move', side_effect=fake_move):
            
            mock_ydl = MagicMock()
            mock_ydl.extract_info.side_effect = fake_extract_info
            mock_ydl.prepare_filename.return_value = "Movie.mp4"
            mock_ytdl_cls.return_value.__enter__.return_value = mock_ydl

            worker.run()

        self.assertEqual(len(captured_recovery), 1)
        rec_info = captured_recovery[0]
        staging_dir = rec_info['staging_dir']
        self.assertTrue(os.path.exists(staging_dir))

        # Simulate UI passing recovery_dir to ProgressWidget
        widget.set_error("Сбой переноса файлов: Access denied (test)", recovery_dir=staging_dir)

        self.assertIn("ФАЙЛЫ СОХРАНЕНЫ", widget.status_label.text())
        self.assertTrue(widget.open_dir_btn.isVisible(), "open_dir_btn must be visible when recovery_dir exists")
        self.assertIn("ОТКРЫТЬ ПАПКУ", widget.open_dir_btn.text())
        self.assertIn(staging_dir, widget.status_label.toolTip())
        self.assertIn(staging_dir, widget.open_dir_btn.toolTip())
        self.assertEqual(widget._recovery_dir, staging_dir)

    def test_next_download_resets_recovery_dir_and_hides_button(self):
        """
        Audit Requirement 37:
        When a new download starts, previous recovery_dir and tooltip are cleared,
        and open_dir_btn is hidden (it cannot open the old file).
        """
        widget = ProgressWidget()
        widget.set_error("Error", recovery_dir=self.save_dir)
        self.assertTrue(widget.open_dir_btn.isVisible())
        self.assertEqual(widget._recovery_dir, self.save_dir)

        # Start next download
        widget.start_progress("⚡ СКАЧИВАНИЕ...")
        self.assertIsNone(widget._recovery_dir, "recovery_dir must be reset to None on new task")
        self.assertIsNone(widget._current_file_path, "current_file_path must be reset to None on new task")
        self.assertFalse(widget.open_dir_btn.isVisible(), "open_dir_btn must be hidden on new task")
        self.assertEqual(widget.status_label.toolTip(), "")

    def test_conservative_fallback_without_marker_with_part(self):
        """
        Audit Requirement 38:
        When marker is missing:
        1. Directory with completed .mp4 + .part MUST be protected from cleanup(0).
        2. Directory with uppercase .MP4 + .part MUST be protected.
        3. Directory with ONLY .part MUST be cleaned up.
        """
        # Case 1: completed .mp4 and unfinished .part (e.g. video finished, sub failed)
        case1_dir = os.path.join(self.save_dir, ".aura_staging_case1")
        os.makedirs(case1_dir, exist_ok=True)
        with open(os.path.join(case1_dir, "ready.mp4"), "wb") as f:
            f.write(b"video")
        with open(os.path.join(case1_dir, "sub.srt.part"), "wb") as f:
            f.write(b"incomplete")

        self.assertTrue(is_recovery_staging_dir(case1_dir), "ready.mp4 + .part must be protected")

        # Case 2: uppercase .MP4
        case2_dir = os.path.join(self.save_dir, ".aura_staging_case2")
        os.makedirs(case2_dir, exist_ok=True)
        with open(os.path.join(case2_dir, "CAPS_VIDEO.MP4"), "wb") as f:
            f.write(b"caps")
        with open(os.path.join(case2_dir, "stream.part"), "wb") as f:
            f.write(b"part")

        self.assertTrue(is_recovery_staging_dir(case2_dir), "CAPS_VIDEO.MP4 must be protected (case-insensitive)")

        # Case 3: only .part (aborted download)
        case3_dir = os.path.join(self.save_dir, ".aura_staging_case3_abort")
        os.makedirs(case3_dir, exist_ok=True)
        with open(os.path.join(case3_dir, "stream.mp4.part"), "wb") as f:
            f.write(b"part")

        self.assertFalse(is_recovery_staging_dir(case3_dir), "Directory with only .part must NOT be protected")

        # Run cleanup_aura_temp_files(max_age_hours=0)
        cleaned = cleanup_aura_temp_files(max_age_hours=0, extra_dirs=[self.save_dir])
        self.assertGreaterEqual(cleaned, 1)

        # Case 1 and 2 must survive, Case 3 must be deleted
        self.assertTrue(os.path.exists(case1_dir), "case1 with ready.mp4 must survive")
        self.assertTrue(os.path.exists(case2_dir), "case2 with CAPS_VIDEO.MP4 must survive")
        self.assertFalse(os.path.exists(case3_dir), "case3 with only .part must be deleted")

    def test_batch_summary_propagates_recovery_dirs(self):
        """
        Audit Requirement 36:
        Batch summary propagates recovery_dirs, and ProgressWidget complete/complete_failed
        activates recovery button for failed elements.
        """
        widget = ProgressWidget()

        # Simulate batch failure with recovery_dirs
        rec_dir = os.path.join(self.save_dir, ".aura_staging_batch_fail")
        os.makedirs(rec_dir, exist_ok=True)

        widget.complete_failed(
            errors=["Item 1: move error"],
            total=1,
            has_retry=True,
            recovery_dirs=[rec_dir]
        )

        self.assertTrue(widget.open_dir_btn.isVisible())
        self.assertEqual(widget._recovery_dir, rec_dir)
        self.assertIn("ВОССТАНОВЛЕНИЕ", widget.open_dir_btn.text())
        self.assertIn(rec_dir, widget.status_label.toolTip())

    def test_get_recovery_sessions_discovers_preserved_data(self):
        """
        Audit Requirement 30:
        get_recovery_sessions scans download folders and returns metadata.
        """
        staging_dir = os.path.join(self.save_dir, ".aura_staging_session_test")
        os.makedirs(staging_dir, exist_ok=True)
        with open(os.path.join(staging_dir, "test.mp4"), "wb") as f:
            f.write(b"data123")

        sessions = get_recovery_sessions(target_dirs=[self.save_dir])
        self.assertGreaterEqual(len(sessions), 1)
        found = [s for s in sessions if s['path'] == staging_dir]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['path'], staging_dir)
        file_names = [f['name'] for f in found[0]['files']]
        self.assertIn("test.mp4", file_names)


if __name__ == '__main__':
    unittest.main()
