import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from PySide6.QtCore import QCoreApplication

app = QCoreApplication.instance() or QCoreApplication([])

from core.media_converter import compress_to_target_size, get_video_duration


class TestStage3P2Fixes(unittest.TestCase):

    def test_compress_to_target_size_budgeting(self):
        """Test that compress_to_target_size calculates bitrates appropriately for short and long videos."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_video:
            tmp_video.write(b"dummy_video_content")
            tmp_video_path = tmp_video.name

        try:
            executed_cmds = []

            def mock_cancellable(cmd, part_path, is_cancelled_cb=None):
                executed_cmds.append(cmd)
                with open(part_path, 'wb') as f:
                    f.write(b"x" * int(7.0 * 1024 * 1024))
                return True

            # Case 1: Standard 60-second video
            with patch('core.media_converter.get_video_duration', return_value=60.0), \
                 patch('core.media_converter.run_ffmpeg_cancellable', side_effect=mock_cancellable):
                out = compress_to_target_size(tmp_video_path, target_mb=8.0)
                self.assertTrue(out.endswith(".mp4"))
                self.assertTrue(os.path.exists(out))
                self.assertLessEqual(os.path.getsize(out), 8.0 * 1024 * 1024)
                os.remove(out)

            # Case 2: Long 300-second video (should add resolution downscaling)
            executed_cmds.clear()
            with patch('core.media_converter.get_video_duration', return_value=300.0), \
                 patch('core.media_converter.run_ffmpeg_cancellable', side_effect=mock_cancellable):
                out = compress_to_target_size(tmp_video_path, target_mb=8.0)
                self.assertTrue(any("-vf" in cmd for cmd in executed_cmds))
                if os.path.exists(out):
                    os.remove(out)

        finally:
            if os.path.exists(tmp_video_path):
                os.remove(tmp_video_path)

    def test_compress_non_existent_file_raises_error(self):
        """Test compress_to_target_size raises FileNotFoundError when file does not exist (does not silently return input_path)."""
        with self.assertRaises(FileNotFoundError):
            compress_to_target_size("non_existent_12345.mp4")


if __name__ == '__main__':
    unittest.main()
