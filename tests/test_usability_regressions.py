import copy
import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from PySide6.QtCore import Qt, QPoint, QRectF
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.downloader import MetadataWorker
from core.settings import settings
from core.workers import worker_registry
from ui.crop_dialog import CropDialog
from ui.crop_widget import CropWidget
from ui.history_view import HistoryItemWidget, HistoryModal
from ui.main_window import MainWindow
from ui.trim_dialog import TrimDialog, ms_to_clock
from test_stage3_queue import DownloadStub, pump_until


class TestInstagramCropPreview(unittest.TestCase):
    def test_raw_instagram_thumbnails_reach_card_and_crop_editor(self):
        MetadataWorker._cache.clear()
        worker_registry().stopping = False
        window = MainWindow()
        png = io.BytesIO()
        Image.new('RGB', (72, 128), '#5480bc').save(png, 'PNG')
        raw = {'title': 'Instagram video', 'formats': [
            {'url': 'https://cdn.test/video.mp4', 'width': 1080, 'height': 1920}],
            'thumbnails': [{'url': 'https://cdn.test/small.jpg', 'width': 180, 'height': 320},
                           {'url': 'https://cdn.test/frame.jpg', 'width': 720, 'height': 1280}]}
        response = MagicMock(status_code=200, content=png.getvalue())
        worker = MetadataWorker('https://www.instagram.com/reel/test/')
        worker.info_ready.connect(window._on_metadata_ready)
        try:
            with patch('core.downloader.InstagramIE') as extractor, \
                 patch('core.downloader.yt_dlp.YoutubeDL'), \
                 patch('core.downloader.get_cookies_config', return_value=None), \
                 patch('ui.video_cards_list.requests.get', return_value=response) as request:
                extractor.return_value.extract.return_value = raw
                worker.run()
                self.assertTrue(pump_until(lambda: not window.cards_list.cards[0].get_pixmap().isNull()))
            self.assertEqual(request.call_args.args[0], 'https://cdn.test/frame.jpg')
            self.assertFalse(window.crop_widget._preview_pixmap.isNull())
            self.assertEqual((window.crop_widget._source_w, window.crop_widget._source_h), (1080, 1920))
            response.close.assert_called_once()
        finally:
            window.close()
            window.deleteLater()
            MetadataWorker._cache.clear()

    def test_late_thumbnail_updates_open_crop_without_resetting_selection(self):
        widget = CropWidget()
        dialog = CropDialog(source_w=1080, source_h=1920)
        dialog.canvas.crop_norm = QRectF(.1, .2, .6, .5)
        selected = QRectF(dialog.canvas.crop_norm)
        widget._crop_dialog = dialog
        pixmap = QPixmap(72, 128)
        pixmap.fill(Qt.blue)
        widget.set_source_info(pixmap, 1080, 1920)
        self.assertFalse(dialog.canvas.pixmap.isNull())
        self.assertEqual(dialog.canvas.crop_norm, selected)
        self.assertEqual((dialog.canvas.source_width, dialog.canvas.source_height), (1080, 1920))
        widget._crop_dialog = None
        dialog.reject()
        dialog.deleteLater()
        widget.deleteLater()

    def test_cover_orientation_does_not_rotate_real_video_dimensions(self):
        cover = QPixmap(320, 180)
        cover.fill(Qt.blue)
        dialog = CropDialog(pixmap=cover, source_w=1080, source_h=1920)
        self.assertEqual((dialog.canvas.source_width, dialog.canvas.source_height), (1080, 1920))
        dialog.reject()
        dialog.deleteLater()


class TestSequentialDownloads(unittest.TestCase):
    def test_second_existing_card_can_start_after_first_finishes(self):
        worker_registry().stopping = False
        defaults = copy.deepcopy(settings.settings)
        window = MainWindow()
        window.notification_manager.show_download_complete = lambda **kw: None
        DownloadStub.calls = []
        try:
            with tempfile.TemporaryDirectory() as output, patch('core.unified_batch_worker.DownloadWorker', DownloadStub):
                settings.settings['download_dir'] = output
                for number in (1, 2):
                    window._add_queue_item({'url': f'https://example.test/video{number}', 'title': f'Video {number}',
                                            'width': 320, 'height': 240, 'duration': 20})
                first, second = window.cards_list.cards
                window.show()
                QApplication.instance().processEvents()
                QTest.mouseClick(first, Qt.LeftButton, pos=QPoint(140, 80))
                window.download_btn.click()
                self.assertTrue(pump_until(lambda: not window._queue_busy))
                self.assertEqual(len(DownloadStub.calls), 1)
                self.assertIsNone(window.download_worker)
                self.assertFalse(window.download_btn.isEnabled())
                # A crop toggle without an edited area keeps the full frame valid.
                QTest.mouseClick(second, Qt.LeftButton, pos=QPoint(140, 80))
                window.crop_widget.toggle.setChecked(True)
                self.assertTrue(window.download_btn.isEnabled())
                window.download_btn.click()
                self.assertTrue(pump_until(lambda: not window._queue_busy))
                self.assertEqual([call[0] for call in DownloadStub.calls],
                                 ['https://example.test/video1', 'https://example.test/video2'])
                self.assertEqual(DownloadStub.calls[1][1]['crop_params']['w_norm'], 1.0)
                self.assertTrue(all(card.result_path for card in (first, second)))
        finally:
            window.close()
            window.deleteLater()
            settings.settings = defaults
            worker_registry().stopping = False

    def test_programmatic_selection_immediately_updates_start_button(self):
        window = MainWindow()
        try:
            window._add_queue_item({'url': 'https://example.test/video'})
            card = window.cards_list.cards[0]
            card.set_selected(False)
            self.assertFalse(window.download_btn.isEnabled())
            card.set_selected(True)
            self.assertTrue(window.download_btn.isEnabled())
        finally:
            window.close()
            window.deleteLater()


class TestHistoryLayout(unittest.TestCase):
    def test_long_filenames_do_not_hide_buttons_at_minimum_width(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / (('Очень длинное имя файла ' * 8) + '.mp4')
            path.touch()
            item = {'title': 'Длинное название видео ' * 12, 'file_path': str(path), 'format_type': 'MP4'}
            with patch('ui.history_view.history.get_all', return_value=[item] * 10):
                modal = HistoryModal()
            try:
                modal.resize(580, 420)
                modal.show()
                QApplication.instance().processEvents()
                for width in (580, 680, 840):
                    modal.resize(width, 420)
                    QApplication.instance().processEvents()
                    self.assertLessEqual(modal.list_container.width(), modal.scroll.viewport().width())
                    for row in modal.findChildren(HistoryItemWidget):
                        self.assertLessEqual(row.folder_btn.geometry().right(), row.width())
                        self.assertGreaterEqual(row.play_btn.geometry().left(), row.sub_lbl.geometry().right())
                        self.assertLessEqual(row.folder_btn.geometry().right(), modal.scroll.viewport().width())
                        self.assertIn('…', row.sub_lbl.text())
                        self.assertEqual(row.sub_lbl.toolTip(), str(path))
            finally:
                modal.close()
                modal.deleteLater()


class TestReadableTrimClock(unittest.TestCase):
    def test_screenshot_position_has_explicit_hours_minutes_seconds(self):
        dialog = TrimDialog(duration_sec=1554)
        dialog._seek_to_ms(1_002_076)
        self.assertEqual(dialog.time_lbl.text(), '00:16:42 / 00:25:54')
        dialog._apply()
        self.assertEqual(dialog.applied_range, ('00:00', '25:54'))
        self.assertEqual(ms_to_clock(3_661_500), '01:01:01')
        dialog.deleteLater()
