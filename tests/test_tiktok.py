import copy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QLabel

from core.clipboard import URL_PATTERN
from core.downloader import MetadataWorker
from core.media_importer import MediaImportWorker
from core.queue_items import default_options, normalize_item, parse_sources
from core.settings import settings
from core.tiktok import gallery_from_post, is_tiktok_url, resolve_tiktok_post
from core.unified_batch_worker import UnifiedBatchWorker
from ui.gallery_dialog import InstagramGalleryDialog, ThumbnailLoader
from ui.main_window import MainWindow

URL = 'https://www.tiktok.com/@creator/photo/7696815550936337684'


def photo_post():
    return {'id': '7696815550936337684', 'author': {'uniqueId': 'creator'},
            'imagePost': {'images': [
                {'imageURL': {'urlList': [f'https://cdn.test/original-{number}.image?signature=keep']},
                 'imageWidth': 1080, 'imageHeight': 1532} for number in (1, 2)]}}


class TestTikTokLinksAndPhotos(unittest.TestCase):
    def setUp(self):
        self.defaults = copy.deepcopy(settings.settings)
        MetadataWorker._cache.clear()

    def tearDown(self):
        settings.settings = self.defaults
        MetadataWorker._cache.clear()

    def test_share_text_and_short_links_are_accepted(self):
        for host in ('vm.tiktok.com', 'vt.tiktok.com', 'www.tiktok.com'):
            url = f'https://{host}/t/ZExample/'
            self.assertEqual(URL_PATTERN.search(url).group(1), url)
            sources, errors = parse_sources(f'Смотри в TikTok! {url} Поделиться')
            self.assertEqual(sources, [url])
            self.assertFalse(errors)
        self.assertFalse(is_tiktok_url('https://tiktok.com.example.test/photo/1'))
        other = 'https://example.test/?next=https://www.tiktok.com/@creator/video/123'
        self.assertEqual(parse_sources(other)[0], [other])

    def test_photo_page_uses_video_route_and_preserves_original_images(self):
        with patch('core.tiktok.yt_dlp.YoutubeDL'), \
             patch('core.tiktok.TikTokIE') as extractor:
            extractor.return_value._extract_web_data_and_status.return_value = (photo_post(), 0)
            canonical, gallery = resolve_tiktok_post(URL + '?share=tracking')
        self.assertEqual(canonical, URL)
        self.assertEqual(gallery['platform'], 'TikTok')
        self.assertEqual([item['index'] for item in gallery['items']], [1, 2])
        self.assertEqual(gallery['items'][1]['best_image'], 'https://cdn.test/original-2.image?signature=keep')
        self.assertEqual((gallery['items'][0]['width'], gallery['items'][0]['height']), (1080, 1532))
        self.assertEqual(extractor.return_value._extract_web_data_and_status.call_args.args,
                         (URL.replace('/photo/', '/video/'), '7696815550936337684'))

    def test_short_photo_link_resolves_and_closes_redirect_response(self):
        with patch('core.tiktok.yt_dlp.YoutubeDL') as factory, \
             patch('core.tiktok.TikTokIE') as extractor:
            response = factory.return_value.__enter__.return_value.urlopen.return_value
            response.url = URL + '?shared=1'
            extractor.return_value._extract_web_data_and_status.return_value = (photo_post(), 0)
            canonical, gallery = resolve_tiktok_post('https://vm.tiktok.com/ZExample/')
        self.assertEqual(canonical, URL)
        self.assertEqual(len(gallery['items']), 2)
        response.close.assert_called_once()

    def test_short_link_cannot_redirect_to_unrelated_site(self):
        with patch('core.tiktok.yt_dlp.YoutubeDL') as factory:
            response = factory.return_value.__enter__.return_value.urlopen.return_value
            response.url = 'https://example.test/photo/1'
            with self.assertRaisesRegex(ValueError, 'другой сайт'):
                resolve_tiktok_post('https://vt.tiktok.com/ZExample/')
        response.close.assert_called_once()

    def test_cancelled_or_private_gallery_never_publishes_photos(self):
        with patch('core.tiktok.yt_dlp.YoutubeDL') as factory:
            self.assertEqual(resolve_tiktok_post(URL, lambda: True), (URL, None))
            factory.assert_not_called()
        with patch('core.tiktok.yt_dlp.YoutubeDL'), patch('core.tiktok.TikTokIE') as extractor:
            extractor.return_value._extract_web_data_and_status.return_value = (None, 10216)
            with self.assertRaisesRegex(ValueError, 'Cookies'):
                resolve_tiktok_post(URL)
        post = photo_post()
        post['imagePost']['images'][1]['imageURL']['urlList'] = []
        with self.assertRaisesRegex(ValueError, '№2'):
            gallery_from_post(post, URL)

    def test_metadata_emits_photo_gallery_instead_of_video(self):
        worker = MetadataWorker(URL)
        galleries, videos, errors = [], [], []
        worker.gallery_ready.connect(galleries.append)
        worker.info_ready.connect(videos.append)
        worker.info_error.connect(errors.append)
        with patch('core.tiktok.yt_dlp.YoutubeDL'), patch('core.tiktok.TikTokIE') as extractor:
            extractor.return_value._extract_web_data_and_status.return_value = (photo_post(), 0)
            worker.run()
        self.assertEqual(len(galleries[0]['items']), 2)
        self.assertFalse(videos or errors)

    def test_regular_video_keeps_video_extraction(self):
        url = URL.replace('/photo/', '/video/')
        worker = MetadataWorker(url)
        videos, errors = [], []
        worker.info_ready.connect(videos.append)
        worker.info_error.connect(errors.append)
        with patch('core.downloader.yt_dlp.YoutubeDL') as factory:
            factory.return_value.__enter__.return_value.extract_info.return_value = {
                'title': 'TikTok video', 'duration': 5,
                'formats': [{'url': 'https://cdn.test/video.mp4', 'width': 1080, 'height': 1920,
                             'vcodec': 'h264', 'acodec': 'aac', 'ext': 'mp4'}]}
            worker.run()
        self.assertFalse(errors)
        self.assertEqual(videos[0]['platform'], 'TikTok')
        self.assertTrue(videos[0]['has_video'])
        self.assertEqual(resolve_tiktok_post(url), (url, None))

    def test_batch_import_adds_each_original_photo_with_video_tools_disabled(self):
        worker = MediaImportWorker([URL], {'mode': 'audio_only', 'crop_enabled': True})
        added = []
        worker.item_ready.connect(added.append)
        with patch('core.tiktok.resolve_tiktok_post', return_value=(URL, gallery_from_post(photo_post(), URL))):
            worker.run()
        self.assertEqual(len(added), 2)
        self.assertNotEqual(added[0]['item_id'], added[1]['item_id'])
        self.assertEqual(added[1]['direct_media_url'], 'https://cdn.test/original-2.image?signature=keep')
        self.assertEqual(added[1]['url'], URL)
        self.assertEqual(added[0]['options']['mode'], 'best')
        self.assertFalse(added[0]['options']['crop_enabled'])

    def test_gallery_selection_keeps_tiktok_source_and_headers_in_queue(self):
        gallery = gallery_from_post(photo_post(), URL)
        window = MainWindow()
        try:
            with patch('ui.main_window.InstagramGalleryDialog') as dialog, \
                 patch('ui.video_cards_list.start_worker'):
                dialog.return_value.exec.return_value = True
                dialog.return_value.get_selected_items.return_value = [gallery['items'][1]]
                window._on_gallery_ready(gallery)
            item = window.cards_list.cards[0].data
            self.assertEqual(item['url'], URL)
            self.assertEqual(item['platform'], 'TikTok')
            self.assertTrue(item['is_photo'])
            self.assertEqual(item['http_headers']['Referer'], 'https://www.tiktok.com/')
        finally:
            window.close()
            window.deleteLater()

    def test_gallery_heading_and_thumbnail_use_tiktok_and_safe_image_type(self):
        gallery = gallery_from_post(photo_post(), URL)
        with patch('ui.gallery_dialog.start_worker'):
            dialog = InstagramGalleryDialog(gallery)
        try:
            self.assertIn('TikTok', dialog.windowTitle())
            self.assertIn('ГАЛЕРЕЯ TIKTOK', [label.text() for label in dialog.findChildren(QLabel)])
            body = io.BytesIO()
            Image.new('RGB', (108, 153), 'orange').save(body, 'PNG')
            response = MagicMock(status_code=200, content=body.getvalue())
            loader = ThumbnailLoader('https://cdn.test/image', headers={'Referer': 'https://www.tiktok.com/'})
            images = []
            loader.loaded.connect(images.append)
            with patch('ui.gallery_dialog.requests.get', return_value=response) as request:
                loader.run()
            self.assertIsInstance(images[0], QImage)
            self.assertEqual(request.call_args.kwargs['headers']['Referer'], 'https://www.tiktok.com/')
            response.close.assert_called_once()
        finally:
            dialog.reject()
            dialog.deleteLater()

    def test_photo_download_preserves_webp_bytes_extension_and_referer(self):
        body = io.BytesIO()
        Image.new('RGB', (108, 153), '#4267ac').save(body, 'WEBP')
        image_bytes = body.getvalue()
        response = MagicMock()
        response.headers = {'content-length': str(len(image_bytes))}
        response.iter_content.return_value = [image_bytes]
        photo = gallery_from_post(photo_post(), URL)['items'][0]
        item = normalize_item({**photo, 'url': URL}, default_options(settings))
        with tempfile.TemporaryDirectory() as folder:
            worker = UnifiedBatchWorker([item], {}, folder)
            completed, errors = [], []
            worker.item_completed.connect(completed.append)
            worker.download_error.connect(errors.append)
            with patch('core.downloader.requests.get', return_value=response) as request:
                worker.run()
            self.assertFalse(errors)
            self.assertEqual(len(completed), 1)
            saved = Path(completed[0]['file_path'])
            self.assertEqual(saved.suffix, '.webp')
            self.assertEqual(saved.read_bytes(), image_bytes)
            self.assertEqual(request.call_args.kwargs['headers']['Referer'], 'https://www.tiktok.com/')
            self.assertEqual(completed[0]['url'], URL)
            response.close.assert_called_once()
