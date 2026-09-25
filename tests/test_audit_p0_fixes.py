import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from PySide6.QtCore import QCoreApplication

app = QCoreApplication.instance() or QCoreApplication([])

from core.local_processor import run_ffmpeg_cancellable
from core.downloader import DownloadWorker


class TestAuditP0Fixes(unittest.TestCase):

    def test_run_ffmpeg_cancellable_no_deadlock_with_large_stderr(self):
        """Test that run_ffmpeg_cancellable does not deadlock when child process writes 250KB to stderr."""
        # This script writes ~250KB of data to stderr - exceeding OS pipe buffer
        python_script = "import sys; sys.stderr.write('E' * 250000); sys.stderr.flush()"
        cmd = [sys.executable, "-c", python_script]

        # Must finish cleanly and not hang
        res = run_ffmpeg_cancellable(cmd, temp_output=None)
        self.assertTrue(res)

    def test_instagram_cdn_video_saved_as_mp4_not_jpg(self):
        """Test that Instagram CDN video URL is downloaded as .mp4 and not treated as .jpg photo."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cdn_video_url = "https://scontent.cdninstagram.com/v/t51.2885-15/reel_video.mp4?efg=123"
            options = {
                'mode': 'best',
                'is_video': True,
                'media_type': 'video',
                'title': 'My_Insta_Reel'
            }

            worker = DownloadWorker(cdn_video_url, options, tmp_dir)

            completed_result = []
            worker.download_completed.connect(lambda res: completed_result.append(res))

            mock_resp = MagicMock()
            mock_resp.headers = {'content-length': '2048'}
            mock_resp.iter_content.return_value = [b"mock_mp4_video_data" * 128]
            mock_resp.raise_for_status = MagicMock()

            with patch('requests.get', return_value=mock_resp), \
                 patch('core.downloader.probe_video_stream', return_value=True):
                worker.run()

            self.assertEqual(len(completed_result), 1)
            res = completed_result[0]
            self.assertEqual(res['mode'], 'MP4')
            self.assertTrue(res['file_path'].endswith('.mp4'))
            self.assertFalse(res['file_path'].endswith('.jpg'))
            self.assertTrue(os.path.exists(res['file_path']))

    def test_network_download_anti_overwrite(self):
        """Test that network download does not clobber existing file in save_dir, using get_unique_path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Pre-create the first file
            existing_file = os.path.join(tmp_dir, "Cool Video [abc1234].mp4")
            with open(existing_file, "w") as f:
                f.write("ORIGINAL_FILE_CONTENT_DO_NOT_OVERWRITE")

            options = {'mode': 'best'}
            worker = DownloadWorker("https://www.youtube.com/watch?v=abc1234", options, tmp_dir)

            completed_result = []
            worker.download_completed.connect(lambda res: completed_result.append(res))

            mock_info = {
                'id': 'abc1234',
                'title': 'Cool Video',
                'ext': 'mp4'
            }

            def mock_ydl_init(opts):
                mock_ydl = MagicMock()
                # Simulate yt-dlp downloading into the staging folder
                outtmpl = opts.get('outtmpl', '')
                mock_ydl.extract_info.return_value = mock_info
                
                # prepare_filename returns staging path
                staged_file = outtmpl.replace('%(title)s', 'Cool Video').replace('%(id)s', 'abc1234').replace('%(ext)s', 'mp4')
                mock_ydl.prepare_filename.return_value = staged_file
                
                # create staged file
                os.makedirs(os.path.dirname(staged_file), exist_ok=True)
                with open(staged_file, 'w') as f:
                    f.write("NEW_DOWNLOADED_VIDEO_CONTENT")
                
                return mock_ydl

            with patch('yt_dlp.YoutubeDL', side_effect=mock_ydl_init):
                worker.run()

            # Original file MUST remain intact
            with open(existing_file, "r") as f:
                self.assertEqual(f.read(), "ORIGINAL_FILE_CONTENT_DO_NOT_OVERWRITE")

            # A new unique file must have been created: Cool Video [abc1234] (1).mp4
            self.assertEqual(len(completed_result), 1)
            res = completed_result[0]
            new_file = res['file_path']
            self.assertEqual(new_file, os.path.join(tmp_dir, "Cool Video [abc1234] (1).mp4"))
            self.assertTrue(os.path.exists(new_file))
            with open(new_file, "r") as f:
                self.assertEqual(f.read(), "NEW_DOWNLOADED_VIDEO_CONTENT")


if __name__ == '__main__':
    unittest.main()
