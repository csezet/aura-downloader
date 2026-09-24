import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from PySide6.QtCore import QCoreApplication

app = QCoreApplication.instance() or QCoreApplication([])

from core.downloader import GalleryDownloadWorker
from core.unified_batch_worker import UnifiedBatchWorker


class TestStage1P0Fixes(unittest.TestCase):

    def test_gallery_video_url_selection(self):
        """Test that Instagram carousel video items choose video URL, not thumbnail best_image."""
        items = [
            {
                'id': 'item_1_video',
                'is_video': True,
                'media_type': 'video',
                'url': 'https://instagram.cdn/real_video.mp4',
                'best_image': 'https://instagram.cdn/thumbnail_preview.jpg',
                'title': 'Instagram Видео #1',
                'uploader': 'test_creator'
            },
            {
                'id': 'item_2_photo',
                'is_video': False,
                'media_type': 'photo',
                'url': 'https://instagram.com/p/test',
                'best_image': 'https://instagram.cdn/full_res_photo.jpg',
                'title': 'Instagram Фото #2',
                'uploader': 'test_creator'
            }
        ]

        worker = GalleryDownloadWorker(items, save_dir="/fake/save/dir")

        requested_urls = []

        def mock_requests_get(url, *args, **kwargs):
            requested_urls.append(url)
            mock_resp = MagicMock()
            mock_resp.headers = {'content-length': '1024'}
            mock_resp.iter_content.return_value = [b"mock_bytes_data" * 64]
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        with patch('requests.get', side_effect=mock_requests_get), \
             patch('os.makedirs'), \
             patch('os.path.exists', return_value=False), \
             patch('os.rename'), \
             patch('os.path.getsize', return_value=1024), \
             patch('builtins.open', unittest.mock.mock_open()):
            worker.run()

        # Item 1 (video) MUST request real_video.mp4, NOT thumbnail_preview.jpg!
        self.assertEqual(len(requested_urls), 2)
        self.assertEqual(requested_urls[0], 'https://instagram.cdn/real_video.mp4')
        # Item 2 (photo) MUST request full_res_photo.jpg
        self.assertEqual(requested_urls[1], 'https://instagram.cdn/full_res_photo.jpg')

    def test_unified_batch_worker_routing(self):
        """Test that UnifiedBatchWorker routes online URLs to DownloadWorker and local files to process_single_local_file."""
        items = [
            {
                'url': 'https://www.youtube.com/watch?v=online1',
                'is_local': False,
                'title': 'Online Video 1',
                'options': {'mode': 'best'}
            },
            {
                'url': r'C:\videos\local_test.mp4',
                'file_path': r'C:\videos\local_test.mp4',
                'is_local': True,
                'title': 'Local Video 1',
                'options': {'mode': 'audio_only', 'audio_fmt': 'mp3'}
            },
            {
                'url': 'https://instagram.cdn/direct_photo.jpg',
                'is_local': False,
                'is_photo': True,
                'direct_media_url': 'https://instagram.cdn/direct_photo.jpg',
                'title': 'Instagram Photo 1',
                'options': {}
            }
        ]

        batch_worker = UnifiedBatchWorker(items, fallback_options={'mode': 'best'}, save_dir=r'C:\downloads')

        online_downloads = []
        local_processes = []

        def mock_download_worker_init(self, url, options, save_dir):
            self.url = url
            self.options = options
            self.save_dir = save_dir
            self.is_cancelled = False
            self.progress_updated = MagicMock()
            self.status_message = MagicMock()
            self.download_completed = MagicMock()
            self.download_error = MagicMock()

        def mock_download_worker_run(self):
            online_downloads.append((self.url, self.options))
            # simulate download_completed emission
            for callback in [call[0][0] for call in self.download_completed.connect.call_args_list]:
                callback({
                    'title': self.options.get('title', 'Online Item'),
                    'url': self.url,
                    'file_path': f"C:\\downloads\\{self.url.split('/')[-1]}.mp4",
                    'file_size': 5000,
                    'file_size_str': '5 KB',
                    'thumbnail': None,
                    'mode': self.options.get('mode', 'MP4')
                })

        def mock_process_local(path, opts, save_dir, **kwargs):
            local_processes.append((path, opts))
            return {
                'title': 'Local Video 1',
                'url': path,
                'file_path': f"C:\\downloads\\local.mp3",
                'file_size': 3000,
                'file_size_str': '3 KB',
                'thumbnail': None,
                'mode': opts.get('mode', 'MP3')
            }

        completed_items = []
        batch_results = []
        batch_worker.item_completed.connect(completed_items.append)
        batch_worker.batch_completed.connect(lambda res: batch_results.extend(res))

        with patch('os.makedirs'), \
             patch('core.local_processor.is_video_file', side_effect=lambda p: 'local_test' in p), \
             patch('core.unified_batch_worker.DownloadWorker.__init__', mock_download_worker_init), \
             patch('core.unified_batch_worker.DownloadWorker.run', mock_download_worker_run), \
             patch('core.local_processor.process_single_local_file', side_effect=mock_process_local):
            batch_worker.run()

        # Check online downloads (item 1 and item 3 photo)
        self.assertEqual(len(online_downloads), 2)
        self.assertEqual(online_downloads[0][0], 'https://www.youtube.com/watch?v=online1')
        self.assertEqual(online_downloads[0][1].get('mode'), 'best')

        self.assertEqual(online_downloads[1][0], 'https://instagram.cdn/direct_photo.jpg')
        self.assertTrue(online_downloads[1][1].get('is_photo'))

        # Check local file process (item 2)
        self.assertEqual(len(local_processes), 1)
        self.assertEqual(local_processes[0][0], r'C:\videos\local_test.mp4')
        self.assertEqual(local_processes[0][1].get('mode'), 'audio_only')

        # Check completed items signal count and batch results
        self.assertEqual(len(completed_items), 3)
        self.assertEqual(len(batch_results), 3)


if __name__ == '__main__':
    unittest.main()
