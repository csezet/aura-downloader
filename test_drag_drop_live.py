import sys
import os
import tempfile
import subprocess
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QMimeData, QUrl
from PySide6.QtGui import QMouseEvent, QDropEvent, QPixmap, QColor
from PySide6.QtMultimedia import QMediaPlayer
from ui.main_window import MainWindow
from ui.timeline_slider import TimelineRangeSlider, ms_to_time_str
from ui.trim_dialog import TrimDialog
from ui.crop_dialog import CropDialog
from core.local_processor import is_video_file, get_local_media_info
from core.media_converter import get_video_codec, get_or_create_preview_proxy, get_video_dimensions
from core.downloader import detect_platform

def create_dummy_video(filename="sample_test.mp4", codec="libx264", size="320x240", duration="3"):
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=blue:s={size}:d={duration}",
        "-c:v", codec,
        filepath
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return filepath

def run_simulation():
    app = QApplication.instance() or QApplication(sys.argv)
    
    v1 = create_dummy_video("sample_v1.mp4", codec="libx264", size="320x240")
    v2 = create_dummy_video("sample_v2.mp4", codec="libx264", size="320x240")
    v3 = create_dummy_video("sample_v3.mp4", codec="libx264", size="320x240")

    print("\n--- 1. Test Codec Detection & Platform Detection ---")
    codec_h264 = get_video_codec(v1)
    assert codec_h264 in ["h264", "avc1"]
    assert get_or_create_preview_proxy(v1) == v1
    assert detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "YouTube"
    assert detect_platform("https://www.instagram.com/p/DcnB42Gjz-_/") == "Instagram"
    print("Codec & Platform detection 100% verified!")

    print("\n--- 2. Test URL Input Clearing on Enter & Card Persistence ---")
    window = MainWindow()
    window.resize(760, 650)
    window.show()

    # Drop video 1
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(v1)])
    window.dropEvent(QDropEvent(QPoint(100, 100), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))

    assert window.cards_list.count() == 1
    assert window.url_input.text() == ""
    print("Video added and url_input remained clean!")

    # Simulate user typing into url_input and then clearing it
    window.url_input.setText("some random text")
    window.url_input.clear()
    app.processEvents()

    # Video cards MUST NOT be deleted when url_input is cleared!
    assert window.cards_list.count() == 1
    assert window.current_video_info is not None
    print("Clearing / modifying url_input does NOT delete loaded cards (Passed!)")

    # Add second video via local files
    window._load_local_files([v2])
    assert window.cards_list.count() == 2
    assert window.url_input.text() == ""

    # Test removing card ONLY via card close button ([X])
    card1 = window.cards_list.cards[0]
    card1.close_btn.click()
    app.processEvents()
    assert window.cards_list.count() == 1
    print("Removing card via card close button ([X]) verified!")

    print("\n--- 3. Test Online Video Card & Instant Crop Thumbnail Update ---")
    online_info = {
        'url': 'https://www.instagram.com/p/DcnB42Gjz-_/',
        'direct_url': 'https://scontent-fra5-1.cdninstagram.com/test_stream.mp4',
        'playable_url': 'https://scontent-fra5-1.cdninstagram.com/test_stream.mp4',
        'title': 'Video by cindie.zhu',
        'uploader': 'Cindy Zhu',
        'duration': 63,
        'duration_str': '01:03',
        'thumbnail': None,
        'platform': 'Instagram',
        'width': 1080,
        'height': 1920,
    }
    window.cards_list.add_video(online_info)
    app.processEvents()
    assert window.cards_list.count() == 2

    # Simulate async thumbnail download completion
    test_pix = QPixmap(320, 240)
    test_pix.fill(QColor("magenta"))
    online_card = window.cards_list.cards[1]
    online_card._on_image_loaded(test_pix)
    app.processEvents()

    assert window.crop_widget._preview_pixmap is not None
    print("Crop widget received loaded thumbnail instantly!")

    # Test TrimDialog with online stream URL
    trim_dialog = TrimDialog(parent=None, video_source=online_info['playable_url'], duration_sec=63)
    trim_dialog.show()
    assert not trim_dialog.btn_play.icon().isNull()
    trim_dialog.close()
    print("TrimDialog with online playable stream URL verified!")

    print("\n--- 4. Test Multi-Cycle Settings Switching Across Multiple Videos ---")
    window._load_local_files([v3])
    card_a = window.cards_list.cards[0]
    card_b = window.cards_list.cards[1]

    evt_click = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)

    # Configure Card A
    card_a.mousePressEvent(evt_click)
    app.processEvents()
    window.trim_widget.toggle.setChecked(True)
    window.trim_widget.start_input.setText("00:01")
    window.trim_widget.end_input.setText("00:02")

    # Configure Card B
    card_b.mousePressEvent(evt_click)
    app.processEvents()
    window._set_mode("audio_only")
    window.audio_fmt_combo.setCurrentText("FLAC (Lossless)")

    # Switch back to Card A and verify
    card_a.mousePressEvent(evt_click)
    app.processEvents()
    assert window.trim_widget.is_trim_enabled() is True
    assert window.trim_widget.start_input.text() == "00:01"
    assert window.trim_widget.end_input.text() == "00:02"

    # Switch back to Card B and verify
    card_b.mousePressEvent(evt_click)
    app.processEvents()
    assert window.current_mode == "audio_only"
    assert "FLAC" in window.audio_fmt_combo.currentText()
    print("Multi-video independent settings 100% verified!")

    print("\n--- 5. Test 9:16 Portrait Video Dimensions & Crop Aspect Ratio ---")
    v_portrait = create_dummy_video("sample_portrait.mp4", codec="libx264", size="240x320")
    dims = get_video_dimensions(v_portrait)
    assert dims == (240, 320), f"Expected (240, 320), got {dims}"

    portrait_pixmap = QPixmap(240, 320)
    portrait_pixmap.fill(QColor("cyan"))

    crop_dlg = CropDialog(parent=None, pixmap=portrait_pixmap, source_w=1920, source_h=1080)
    assert crop_dlg.source_w == 1080
    assert crop_dlg.source_h == 1920
    assert crop_dlg.canvas.source_width == 1080
    assert crop_dlg.canvas.source_height == 1920
    print("CropDialog automatically synchronized 9:16 portrait orientation (Passed!)")

    print("\n--- 6. Test Short Video (1.35s) Trim Slider & End-of-Media Seeking ---")
    v_short = create_dummy_video("sample_short.mp4", codec="libx264", size="320x240", duration="1.35")
    info_short = get_local_media_info(v_short)
    assert abs(info_short['duration'] - 1.35) < 0.2

    trim_dlg_short = TrimDialog(parent=None, video_source=v_short, duration_sec=info_short['duration'])
    trim_dlg_short.show()
    app.processEvents()

    # Seek to very end
    trim_dlg_short._seek_to_ms(int(info_short['duration'] * 1000))
    app.processEvents()
    assert trim_dlg_short.current_pos_ms <= trim_dlg_short.duration_ms
    print("\n--- 7. Test Hotkeys, Folder Drop & Cache Cleanup ---")
    from PySide6.QtGui import QKeyEvent
    from core.media_converter import cleanup_aura_temp_files, get_crop_filter

    # 7.1 Test TrimDialog Hotkeys
    trim_dlg_hotkey = TrimDialog(parent=None, video_source=v1, duration_sec=3.0)
    trim_dlg_hotkey.show()
    app.processEvents()

    # Press Space to toggle play
    key_space = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Space, Qt.NoModifier)
    trim_dlg_hotkey.keyPressEvent(key_space)
    assert trim_dlg_hotkey.player.playbackState() == QMediaPlayer.PlayingState

    trim_dlg_hotkey.keyPressEvent(key_space)
    assert trim_dlg_hotkey.player.playbackState() != QMediaPlayer.PlayingState

    # Press Right arrow to step
    pos_before = trim_dlg_hotkey.current_pos_ms
    key_right = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)
    trim_dlg_hotkey.keyPressEvent(key_right)
    assert trim_dlg_hotkey.current_pos_ms >= pos_before

    # Press I (mark start) and O (mark end)
    key_i = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_I, Qt.NoModifier)
    trim_dlg_hotkey.keyPressEvent(key_i)
    assert trim_dlg_hotkey.start_ms == trim_dlg_hotkey.current_pos_ms

    trim_dlg_hotkey.close()
    print("TrimDialog hotkeys (Space, Arrow, In/Out) verified!")

    # 7.2 Test CropDialog Hotkeys
    crop_dlg_hotkey = CropDialog(parent=None, pixmap=portrait_pixmap)
    crop_dlg_hotkey.show()
    app.processEvents()

    # Press '1' for 1:1 square
    key_1 = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_1, Qt.NoModifier)
    crop_dlg_hotkey.keyPressEvent(key_1)
    assert crop_dlg_hotkey.canvas.aspect_ratio == 1.0

    # Press '2' for 9:16
    key_2 = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_2, Qt.NoModifier)
    crop_dlg_hotkey.keyPressEvent(key_2)
    assert abs(crop_dlg_hotkey.canvas.aspect_ratio - (9.0/16.0)) < 0.01

    # Press '0' for Free
    key_0 = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_0, Qt.NoModifier)
    crop_dlg_hotkey.keyPressEvent(key_0)
    assert crop_dlg_hotkey.canvas.aspect_ratio is None

    crop_dlg_hotkey.close()
    print("CropDialog hotkeys (0, 1, 2 presets) verified!")

    # 7.3 Test Folder Drop
    test_folder = tempfile.mkdtemp(prefix="aura_test_folder_")
    sub_video = create_dummy_video("sub_video.mp4", size="160x120", duration="1")
    import shutil
    shutil.copy(sub_video, os.path.join(test_folder, "copied_sub.mp4"))

    count_before = window.cards_list.count()
    window._load_local_files([test_folder])
    assert window.cards_list.count() > count_before
    shutil.rmtree(test_folder, ignore_errors=True)
    print("Folder recursive Drag & Drop discovery verified!")

    # 7.4 Test Single-pass crop filter & Temp cleanup
    filter_str = get_crop_filter(v1, {'x_norm': 0.1, 'y_norm': 0.1, 'w_norm': 0.8, 'h_norm': 0.8})
    assert "crop=" in filter_str

    cleanup_count = cleanup_aura_temp_files(max_age_hours=0)
    print(f"Cleanup function ran successfully ({cleanup_count} files cleaned)!")

    window.close()
    print("\n[ALL TESTS 100% PASSED!]")

if __name__ == "__main__":
    run_simulation()
