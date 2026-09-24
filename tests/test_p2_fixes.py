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

            def mock_subp_run(cmd, *args, **kwargs):
                executed_cmds.append(cmd)
                # simulate writing to output part file
                out_file = cmd[-1]
                with open(out_file, 'wb') as f:
                    f.write(b"x" * int(7.0 * 1024 * 1024))
                res = MagicMock()
                res.returncode = 0
                return res

            # Case 1: Standard 60-second video
            with patch('core.media_converter.get_video_duration', return_value=60.0), \
                 patch('subprocess.run', side_effect=mock_subp_run):
                out = compress_to_target_size(tmp_video_path, target_mb=8.0)
                self.assertTrue(out.endswith(".mp4"))
                self.assertTrue(os.path.exists(out))
                self.assertLessEqual(os.path.getsize(out), 8.0 * 1024 * 1024)
                os.remove(out)

            # Case 2: Long 300-second video (should add resolution downscaling)
            executed_cmds.clear()
            with patch('core.media_converter.get_video_duration', return_value=300.0), \
                 patch('subprocess.run', side_effect=mock_subp_run):
                out = compress_to_target_size(tmp_video_path, target_mb=8.0)
                self.assertTrue(any("-vf" in cmd for cmd in executed_cmds))
                if os.path.exists(out):
                    os.remove(out)

        finally:
            if os.path.exists(tmp_video_path):
                os.remove(tmp_video_path)

    def test_compress_non_existent_file(self):
        """Test compress_to_target_size returns input_path safely when file does not exist."""
        result = compress_to_target_size("non_existent_12345.mp4")
        self.assertEqual(result, "non_existent_12345.mp4")


if __name__ == '__main__':
    unittest.main()
