import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from PySide6.QtCore import QCoreApplication

app = QCoreApplication.instance() or QCoreApplication([])

from core.media_converter import (
    get_unique_path, check_ffmpeg_available, get_video_dimensions, get_video_duration
)
from core.interpolator import (
    get_video_fps, get_tools_dir, EXPECTED_RIFE_SHA256, download_rife_engine
)
from core.local_processor import run_ffmpeg_cancellable


class TestStage2P1Fixes(unittest.TestCase):

    def test_get_unique_path(self):
        """Test get_unique_path prevents clobbering existing files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = os.path.join(tmp_dir, "test.mp4")
            # When file does not exist, returns original
            self.assertEqual(get_unique_path(f1), f1)

            # Create f1
            with open(f1, "w") as f:
                f.write("data")

            # Now must return test (1).mp4
            u1 = get_unique_path(f1)
            self.assertEqual(u1, os.path.join(tmp_dir, "test (1).mp4"))

            # Create test (1).mp4
            with open(u1, "w") as f:
                f.write("data")

            # Now must return test (2).mp4
            u2 = get_unique_path(f1)
            self.assertEqual(u2, os.path.join(tmp_dir, "test (2).mp4"))

    def test_ffprobe_resilience_no_fake_metadata(self):
        """Test ffprobe functions return None on errors or non-existent files instead of fake values."""
        # Non-existent file
        self.assertEqual(get_video_dimensions("non_existent_file_xyz.mp4"), (None, None))
        self.assertIsNone(get_video_duration("non_existent_file_xyz.mp4"))
        self.assertIsNone(get_video_fps("non_existent_file_xyz.mp4"))

        # When ffprobe fails / exits with error
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = "Error reading stream"
            with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_f:
                self.assertEqual(get_video_dimensions(tmp_f.name), (None, None))
                self.assertIsNone(get_video_duration(tmp_f.name))
                self.assertIsNone(get_video_fps(tmp_f.name))

    def test_check_ffmpeg_available(self):
        """Test check_ffmpeg_available returns bool and status message."""
        ok, msg = check_ffmpeg_available()
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(msg, str)
        if ok:
            self.assertTrue("ffmpeg" in msg.lower() or "version" in msg.lower() or "ok" in msg.lower())

    def test_rife_tools_dir_and_hash(self):
        """Test RIFE tools directory uses %LOCALAPPDATA% and expected SHA-256 is correct."""
        tools_dir = get_tools_dir()
        self.assertTrue("AuraDownloader" in tools_dir or ".aura_downloader" in tools_dir)
        self.assertEqual(EXPECTED_RIFE_SHA256, "d8e4d772d26cd8006ef0ad0bc82eb191b53c68677d1ae2f42506d74cbbbea606")

    def test_rife_hash_mismatch_rejection(self):
        """Test that download_rife_engine rejects archives with mismatched SHA-256."""
        mock_resp = MagicMock()
        mock_resp.headers = {'content-length': '100'}
        mock_resp.iter_content.return_value = [b"bad_corrupted_data_chunk"]
        mock_resp.raise_for_status = MagicMock()

        with patch('requests.get', return_value=mock_resp):
            success = download_rife_engine()
            self.assertFalse(success)

    def test_run_ffmpeg_cancellable(self):
        """Test that run_ffmpeg_cancellable terminates the process and cleans temp file on cancel."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_out = os.path.join(tmp_dir, "output.tmp.mp4")
            with open(temp_out, "w") as f:
                f.write("partial_data")

            # Mock subprocess.Popen
            mock_proc = MagicMock()
            # poll returns None (running) on first check, then after terminate it can finish
            poll_state = [None, 0]
            mock_proc.poll.side_effect = lambda: poll_state.pop(0) if poll_state else 0
            mock_proc.wait = MagicMock()
            mock_proc.communicate = MagicMock(return_value=(b"", b""))

            with patch('subprocess.Popen', return_value=mock_proc):
                # Callback that triggers cancellation immediately
                res = run_ffmpeg_cancellable(["ffmpeg", "-i", "in.mp4"], temp_out, is_cancelled_cb=lambda: True)
                self.assertFalse(res)
                mock_proc.terminate.assert_called_once()
                # Temp file should be removed
                self.assertFalse(os.path.exists(temp_out))


if __name__ == '__main__':
    unittest.main()
