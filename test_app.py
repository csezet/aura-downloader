import sys
import os
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QRectF
from PySide6.QtGui import QPixmap, QImage

from core.settings import settings
from core.history import history
from core.downloader import format_bytes, format_seconds
from core.local_processor import is_video_file, get_local_media_info
from ui.video_cards_list import VideoCardsListWidget, VideoCardWidget
from ui.crop_widget import CropWidget
from ui.crop_dialog import CropDialog, CropCanvas
from ui.timeline_slider import TimelineRangeSlider, ms_to_time_str
from ui.trim_dialog import TrimDialog
from ui.trim_widget import TrimWidget
from ui.main_window import MainWindow

app = QApplication.instance() or QApplication(sys.argv)

def test_downloader_utils():
    print("Testing downloader utils...")
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1048576) == "1.0 MB"
    assert format_seconds(65) == "01:05"
    assert format_seconds(3665) == "01:01:05"
    print("Downloader utils test passed!")

def test_crop_calculations():
    print("Testing Crop Canvas & Dialog calculations...")
    dummy_img = QImage(1920, 1080, QImage.Format_RGB32)
    dummy_img.fill(Qt.white)
    pix = QPixmap.fromImage(dummy_img)

    canvas = CropCanvas()
    canvas.set_source_image(pix, 1920, 1080)
    canvas.resize(400, 300)
    canvas.set_aspect_ratio(1.0)
    
    crop_params = canvas.get_crop_params()
    assert 'w' in crop_params and 'h' in crop_params
    assert crop_params['w'] > 0 and crop_params['h'] > 0

    dialog = CropDialog(parent=None, pixmap=pix, source_w=1920, source_h=1080)
    dialog.show()
    dialog._set_preset(16/9, dialog.pill_16_9)
    dialog._apply()
    assert dialog.applied_crop_params is not None
    assert 'w' in dialog.applied_crop_params and 'h' in dialog.applied_crop_params
    dialog.close()
    print("Crop Canvas calculations test passed!")

def test_timeline_and_trim_dialog():
    print("Testing Timeline Slider and Trim Dialog...")
    slider = TimelineRangeSlider()
    slider.set_duration(60000)
    slider.set_range(10000, 40000)
    assert slider.start_ms == 10000
    assert slider.end_ms == 40000

    dialog = TrimDialog(parent=None, video_source=None, duration_sec=60, initial_start="00:10", initial_end="00:40")
    dialog.show()
    dialog._apply()
    assert dialog.applied_range == ("00:10", "00:40")
    dialog.close()
    print("Timeline Slider and Trim Dialog test passed!")

def test_video_cards_list():
    print("Testing VideoCardsListWidget...")
    list_w = VideoCardsListWidget()
    list_w.show()
    
    info1 = {
        'url': 'test1.mp4',
        'title': 'Test Video 1',
        'uploader': 'User1',
        'duration': 10,
        'duration_str': '00:10',
        'width': 1920,
        'height': 1080,
        'is_local': True
    }
    
    info2 = {
        'url': 'test1.mp4', # Duplicate url allowed
        'title': 'Test Video 1 (Copy)',
        'uploader': 'User1',
        'duration': 10,
        'duration_str': '00:10',
        'width': 1920,
        'height': 1080,
        'is_local': True
    }

    id1 = list_w.add_video(info1)
    assert list_w.count() == 1
    assert list_w.isVisible() is True

    id2 = list_w.add_video(info2)
    assert list_w.count() == 2
    assert len(list_w.get_all_videos()) == 2

    # Check that vertical scrollbar is off (no slider)
    assert list_w.scroll.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOff

    list_w.remove_card(id1)
    assert list_w.count() == 1

    list_w.clear_all()
    assert list_w.count() == 0
    print("VideoCardsListWidget test passed!")

def test_main_window_init():
    print("Testing UI initialization with Video Cards List & Trim Widget...")
    win = MainWindow()
    win.show()
    assert win.cards_list is not None
    assert win.trim_widget is not None
    assert win.download_btn is not None
    assert win.cards_list.isVisible() is False
    win.close()
    print("UI initialization passed!")

if __name__ == "__main__":
    print("Testing core imports...")
    print("Imports OK!")
    test_downloader_utils()
    test_crop_calculations()
    test_timeline_and_trim_dialog()
    test_video_cards_list()
    test_main_window_init()
    print("[ALL TESTS PASSED]")
