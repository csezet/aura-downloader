import os
import unittest
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QApplication

from core.media_converter import compress_to_target_size, crop_video, convert_to_gif, check_ffmpeg_available
from core.unified_batch_worker import UnifiedBatchWorker

app = QApplication.instance()
if not app:
    app = QApplication([])


class TestAuditP1Fixes(unittest.TestCase):

    def test_check_ffmpeg_available_structure(self):
        """Test that check_ffmpeg_available returns (bool, str) contract."""
        ok, msg = check_ffmpeg_available()
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(msg, str)
        self.assertTrue(len(msg) > 0)

    @patch('core.media_converter.run_ffmpeg_cancellable')
    @patch('core.media_converter.get_video_duration')
    @patch('core.media_converter.os.path.exists')
    @patch('core.media_converter.os.path.getsize')
    @patch('core.media_converter.os.remove')
    def test_compress_to_target_size_hard_limit_exceeded_raises_error(self, mock_remove, mock_getsize, mock_exists, mock_duration, mock_run):
        """Test that compress_to_target_size raises an Exception and removes tmp file if output still exceeds target_mb."""
        mock_duration.return_value = 10.0
        mock_exists.return_value = True
        mock_run.return_value = True

        # Simulate size consistently > 8.0MB (e.g. 9MB = 9437184 bytes)
        mock_getsize.return_value = 9 * 1024 * 1024

        with self.assertRaises(Exception) as ctx:
            compress_to_target_size("dummy_input.mp4", target_mb=8.0, output_path="dummy_output.mp4")

        self.assertIn("Не удалось сжать видео до лимита 8.0 МБ", str(ctx.exception))
        mock_remove.assert_called()

    @patch('core.media_converter.run_ffmpeg_cancellable')
    @patch('core.media_converter.os.path.exists')
    def test_crop_video_cancellation(self, mock_exists, mock_run):
        """Test that crop_video returns None when cancelled via is_cancelled_cb."""
        mock_exists.return_value = True
        mock_run.return_value = False  # simulated cancellation

        res = crop_video("dummy_input.mp4", {'x': 0, 'y': 0, 'w': 100, 'h': 100}, output_path="dummy_crop.mp4", is_cancelled_cb=lambda: True)
        self.assertIsNone(res)

    @patch('core.media_converter.run_ffmpeg_cancellable')
    @patch('core.media_converter.os.path.exists')
    def test_convert_to_gif_cancellation(self, mock_exists, mock_run):
        """Test that convert_to_gif returns None when cancelled via is_cancelled_cb."""
        mock_exists.return_value = True
        mock_run.return_value = False  # simulated cancellation

        res = convert_to_gif("dummy_input.mp4", output_path="dummy_out.gif", is_cancelled_cb=lambda: True)
        self.assertIsNone(res)

    @patch('core.local_processor.process_single_local_file')
    def test_unified_batch_worker_partial_success_summary(self, mock_process):
        """Test that UnifiedBatchWorker accurately reports partial successes and errors without masking them as 100% finished."""
        # Item 1 succeeds, Item 2 fails
        mock_process.side_effect = [
            {'title': 'Vid 1', 'file_path': 'vid1.mp4', 'file_size': 1000, 'file_size_str': '1 KB', 'mode': 'MP4'},
            Exception("FFmpeg rendering crashed")
        ]

        items = [
            {'url': 'local_vid1.mp4', 'is_local': True, 'title': 'Vid 1'},
            {'url': 'local_vid2.mp4', 'is_local': True, 'title': 'Vid 2'},
        ]

        worker = UnifiedBatchWorker(items, fallback_options={}, save_dir="test_save_dir")

        summary_received = []
        progress_states = []
        batch_results = []

        worker.batch_summary.connect(lambda s: summary_received.append(s))
        worker.progress_updated.connect(lambda p: progress_states.append(p))
        worker.batch_completed.connect(lambda r: batch_results.append(r))

        worker.run()

        self.assertEqual(len(summary_received), 1)
        s = summary_received[0]
        self.assertEqual(s['success_count'], 1)
        self.assertEqual(s['error_count'], 1)
        self.assertTrue(s['is_partial'])
        self.assertEqual(len(s['results']), 1)
        self.assertEqual(len(s['errors']), 1)

        # Worker instance properties
        self.assertEqual(len(worker.results), 1)
        self.assertEqual(len(worker.errors), 1)

        # Verify last progress update state is finished_with_errors, not plain 'finished'
        self.assertTrue(len(progress_states) > 0)
        last_prog = progress_states[-1]
        self.assertEqual(last_prog.get('status'), 'finished_with_errors')
        self.assertIn("ЧАСТИЧНО", last_prog.get('speed_str', ''))


if __name__ == '__main__':
    unittest.main()
