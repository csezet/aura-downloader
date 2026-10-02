import copy
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.downloader import MetadataWorker
from core.media_preview import choose_preview_format, resolve_preview
from core.settings import settings
from core.workers import worker_registry
from ui.main_window import MainWindow
from ui.trim_dialog import TrimDialog
from ui.trim_widget import TrimWidget


class TestExplicitInput(unittest.TestCase):
    def setUp(self):
        worker_registry().stopping = False
        self.defaults = copy.deepcopy(settings.settings)
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        settings.settings = self.defaults
        worker_registry().stopping = False

    def test_pasting_waits_for_button_and_preserves_entered_link(self):
        QApplication.clipboard().setText('https://example.test/other')
        with patch.object(self.window, '_start_metadata_worker') as start:
            self.window.url_input.setText('https://example.test/chosen')
            QTest.qWait(650)
            start.assert_not_called()
            self.assertEqual(self.window.cards_list.count(), 0)
            self.window._paste_and_fetch()
            start.assert_called_once_with('https://example.test/chosen')

    def test_clipboard_only_fills_empty_field_and_never_fetches(self):
        settings.settings['auto_paste'] = True
        with patch.object(self.window, '_start_metadata_worker') as start:
            self.window._on_clipboard_url('https://example.test/first')
            QTest.qWait(650)
            self.assertEqual(self.window.url_input.text(), 'https://example.test/first')
            self.window._on_clipboard_url('https://example.test/second')
            self.assertEqual(self.window.url_input.text(), 'https://example.test/first')
            start.assert_not_called()

    def test_empty_field_button_uses_clipboard_and_enter_submits_once(self):
        settings.settings['auto_paste'] = False
        QApplication.clipboard().setText('https://example.test/clipboard')
        with patch.object(self.window, '_start_metadata_worker') as start:
            self.window._paste_and_fetch()
            start.assert_called_once_with('https://example.test/clipboard')
            start.reset_mock()
            self.window.url_input.setText('https://example.test/entered')
            QTest.keyClick(self.window.url_input, Qt.Key_Return)
            start.assert_called_once_with('https://example.test/entered')

    def test_playlist_card_resolves_webpage_before_opening_player(self):
        class Playlist:
            def __init__(self, *args): pass
            def exec(self): return True
            def get_selected_entries(self):
                return [{'url': 'https://www.youtube.com/watch?v=abc', 'duration': 1800}]
        with patch('ui.main_window.PlaylistDialog', Playlist):
            self.window._on_playlist_ready({})
        self.assertEqual(self.window.trim_widget._video_source,
                         {'url': 'https://www.youtube.com/watch?v=abc'})


class TestTrimTimeline(unittest.TestCase):
    def test_half_hour_video_cannot_become_hours_after_seek(self):
        dialog = TrimDialog(duration_sec=1800)
        dialog.timeline_slider.resize(800, 54)
        dialog._on_player_duration_changed(108_000_000)
        self.assertEqual(dialog.duration_ms, 1_800_000)
        slider = dialog.timeline_slider
        QTest.mouseClick(slider, Qt.LeftButton, pos=QPoint(400, 26))
        self.assertEqual(dialog.current_pos_ms, 900_000)
        self.assertEqual(dialog.time_lbl.text(), '15:00 / 30:00')
        dialog._on_player_position_changed(108_900_000)
        self.assertEqual(dialog.time_lbl.text(), '15:00 / 30:00')
        self.assertEqual(slider.duration_ms, 1_800_000)
        self.assertEqual(slider.current_pos_ms, 900_000)
        dialog._apply()
        self.assertEqual(dialog.applied_range, ('00:00', '30:00'))
        dialog.deleteLater()

    def test_subsecond_end_is_preserved_when_reopening_editor(self):
        dialog = TrimDialog(duration_sec=1800, initial_start='29:55.25', initial_end='29:59.5')
        dialog._on_player_duration_changed(1_800_100)
        dialog._apply()
        self.assertEqual(dialog.applied_range, ('29:55.25', '29:59.5'))
        widget = TrimWidget()
        widget.set_duration_hint(1.25)
        self.assertEqual(widget.end_input.text(), '00:01.25')
        dialog.deleteLater()
        widget.deleteLater()

    def test_unknown_duration_is_learned_without_losing_custom_selection(self):
        dialog = TrimDialog(duration_sec=0, initial_start='1', initial_end='5')
        dialog._on_preview_info({'duration': 1800})
        dialog._on_player_duration_changed(108_000_000)
        self.assertEqual((dialog.duration_ms, dialog.start_ms, dialog.end_ms), (1_800_000, 1000, 5000))
        dialog.reject()
        dialog.deleteLater()


class TestMetadataLatency(unittest.TestCase):
    def setUp(self):
        MetadataWorker._cache.clear()
        self.cookies = patch('core.downloader.get_cookies_config', return_value=None)
        self.cookies.start()

    def tearDown(self):
        self.cookies.stop()
        MetadataWorker._cache.clear()

    def test_video_in_playlist_is_extracted_once_without_preparing_download(self):
        ydl = MagicMock()
        ydl.extract_info.return_value = {'title': 'Video', 'duration': 1800, 'formats': []}
        results = []
        worker = MetadataWorker('https://www.youtube.com/watch?v=abc&list=xyz')
        worker.info_ready.connect(results.append)
        with patch('core.downloader.yt_dlp.YoutubeDL') as factory:
            factory.return_value.__enter__.return_value = ydl
            worker.run()
        self.assertEqual(len(results), 1)
        ydl.extract_info.assert_called_once_with(worker.url, download=False, process=False)
        options = factory.call_args.args[0]
        self.assertTrue(options['noplaylist'])
        self.assertLessEqual(options['extractor_retries'], 1)
        self.assertIsNone(results[0]['width'])

    def test_cache_reuses_metadata_but_not_mutable_card_settings(self):
        ydl = MagicMock()
        ydl.extract_info.return_value = {'title': 'Original', 'duration': 1800}
        results = []
        with patch('core.downloader.yt_dlp.YoutubeDL') as factory:
            factory.return_value.__enter__.return_value = ydl
            for index in range(2):
                worker = MetadataWorker('https://example.test/video')
                worker.info_ready.connect(results.append)
                worker.run()
                if index == 0:
                    results[0]['title'] = 'Edited'
        ydl.extract_info.assert_called_once()
        self.assertEqual(results[1]['title'], 'Original')

    def test_instagram_video_reuses_specialized_extraction(self):
        info = {'title': 'Instagram video', 'duration': 1800,
                'formats': [{'url': 'https://cdn.test/video.mp4', 'height': 480, 'width': 640,
                             'vcodec': 'h264', 'acodec': 'aac', 'ext': 'mp4'}]}
        results = []
        worker = MetadataWorker('https://www.instagram.com/reel/abc/?igsh=test')
        worker.info_ready.connect(results.append)
        with patch('core.downloader.InstagramIE') as extractor, patch('core.downloader.yt_dlp.YoutubeDL') as factory:
            extractor.return_value.extract.return_value = info
            worker.run()
        extractor.return_value.extract.assert_called_once_with('https://www.instagram.com/reel/abc/')
        factory.return_value.__enter__.return_value.extract_info.assert_not_called()
        self.assertEqual(results[0]['duration'], 1800)

    def test_cancelled_worker_makes_no_request(self):
        worker = MetadataWorker('https://example.test/video')
        worker.cancel()
        with patch('core.downloader.yt_dlp.YoutubeDL') as factory:
            worker.run()
        factory.assert_not_called()

    def test_expired_cache_fetches_fresh_stream_links(self):
        ydl = MagicMock()
        ydl.extract_info.return_value = {'title': 'Video', 'duration': 1800}
        url = 'https://example.test/video'
        with patch('core.downloader.yt_dlp.YoutubeDL') as factory:
            factory.return_value.__enter__.return_value = ydl
            MetadataWorker(url).run()
            timestamp, name, data = MetadataWorker._cache[(url, None)]
            MetadataWorker._cache[(url, None)] = (timestamp - 100, name, data)
            MetadataWorker(url).run()
        self.assertEqual(ydl.extract_info.call_count, 2)

    def test_preview_prefers_small_progressive_video_over_audio_and_hls(self):
        formats = [
            {'url': 'audio', 'vcodec': 'none', 'ext': 'mp4'},
            {'url': 'large', 'vcodec': 'avc1', 'height': 1080, 'ext': 'mp4', 'acodec': 'aac'},
            {'url': 'preview', 'vcodec': 'avc1', 'height': 360, 'ext': 'mp4', 'acodec': 'aac'},
            {'url': 'manifest', 'vcodec': 'avc1', 'height': 480, 'ext': 'mp4', 'acodec': 'aac', 'protocol': 'm3u8_native'},
        ]
        self.assertEqual(choose_preview_format(formats)['url'], 'preview')
        self.assertIsNone(choose_preview_format(formats[:1]))

    def test_playlist_card_preview_resolves_media_without_downloading_video(self):
        ydl = MagicMock()
        ydl.extract_info.return_value = {'duration': 1800, 'formats': [
            {'url': 'https://cdn.test/media.mp4', 'height': 360, 'vcodec': 'h264', 'ext': 'mp4'}]}
        with patch('yt_dlp.YoutubeDL') as factory:
            factory.return_value.__enter__.return_value = ydl
            preview = resolve_preview('https://example.test/page', lambda: False)
        self.assertEqual(preview, {'url': 'https://cdn.test/media.mp4', 'duration': 1800})
        ydl.extract_info.assert_called_once_with('https://example.test/page', download=False, process=False)
