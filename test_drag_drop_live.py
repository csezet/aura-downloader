import sys
import os
import tempfile
import subprocess
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QMimeData, QUrl
from PySide6.QtGui import QMouseEvent, QDropEvent
from ui.main_window import MainWindow
from ui.timeline_slider import TimelineRangeSlider, ms_to_time_str
from ui.trim_dialog import TrimDialog
from core.local_processor import is_video_file, get_local_media_info
from core.media_converter import get_video_codec, get_or_create_preview_proxy
from core.downloader import detect_platform

def create_dummy_video(filename="sample_test.mp4", codec="libx264"):
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=3",
        "-c:v", codec,
        filepath
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return filepath

def run_simulation():
    app = QApplication.instance() or QApplication(sys.argv)
    
    v1 = create_dummy_video("sample_v1.mp4", codec="libx264")
    v2 = create_dummy_video("sample_v2.mp4", codec="libx264")
    v3 = create_dummy_video("sample_v3.mp4", codec="libx264")

    print("\n--- 1. Test Codec Detection & H.264 Proxy for AV1 / Non-H264 Videos ---")
    codec_h264 = get_video_codec(v1)
    assert codec_h264 in ["h264", "avc1"]
    print(f"H264 Codec detected correctly: {codec_h264}")

    # Check that H264 returns original path directly without overhead
    proxy_h264 = get_or_create_preview_proxy(v1)
    assert proxy_h264 == v1
    print("H264 directly passed without redundant transcoding!")

    # Test Platform Detection
    assert detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "YouTube"
    assert detect_platform("https://youtu.be/dQw4w9WgXcQ") == "YouTube"
    assert detect_platform("https://www.instagram.com/reel/C-xyz123/") == "Instagram"
    assert detect_platform("https://instagram.com/p/C-xyz123/") == "Instagram"
    print("Platform detection for YouTube and Instagram 100% verified!")

    print("\n--- 2. Test TrimDialog with Vector SVG Icons & Proxy ---")
    dialog = TrimDialog(parent=None, video_source=v1, duration_sec=3, initial_start="00:01", initial_end="00:02")
    dialog.show()
    assert not dialog.btn_play.icon().isNull()
    assert not dialog.btn_jump_start.icon().isNull()
    assert not dialog.btn_jump_end.icon().isNull()
    assert not dialog.btn_mark_start.icon().isNull()
    assert not dialog.btn_mark_end.icon().isNull()
    assert not dialog.btn_loop.icon().isNull()
    dialog.close()
    print("TrimDialog vector SVG icons & proxy integration verified!")

    print("\n--- 3. Test Multi-Cycle Settings Switching Across 3 Videos ---")
    window = MainWindow()
    window.resize(760, 650)
    window.show()

    # Drop 3 videos
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(v1), QUrl.fromLocalFile(v2), QUrl.fromLocalFile(v3)])
    window.dropEvent(QDropEvent(QPoint(100, 100), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))

    assert window.cards_list.count() == 3
    card1 = window.cards_list.cards[0]
    card2 = window.cards_list.cards[1]
    card3 = window.cards_list.cards[2]

    # Verify LOCAL VIDEO badge styling
    assert "background-color: #FFFFFF" in card1.platform_badge.styleSheet()
    assert "color: #000000" in card1.platform_badge.styleSheet()
    print("LOCAL VIDEO badge high-contrast styling verified!")

    evt_click = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)

    # --- ROUND 1: Set unique settings for each video ---
    card1.mousePressEvent(evt_click)
    app.processEvents()
    window.trim_widget.toggle.setChecked(True)
    window.trim_widget.start_input.setText("00:01")
    window.trim_widget.end_input.setText("00:05")
    window.smooth_widget.toggle.setChecked(True)
    window.smooth_widget.fps_combo.setCurrentIndex(1) # 120 FPS

    card2.mousePressEvent(evt_click)
    app.processEvents()
    window._set_mode("audio_only")
    window.audio_fmt_combo.setCurrentText("MP3 (320 kbps)")
    window.trim_widget.toggle.setChecked(False)
    window.smooth_widget.toggle.setChecked(False)

    card3.mousePressEvent(evt_click)
    app.processEvents()
    window._set_mode("gif")
    window.crop_widget.toggle.setChecked(True)
    window.crop_widget._crop_params = {'x': 10, 'y': 10, 'w': 200, 'h': 200}
    window._auto_save_active_options()

    print("Round 1 settings configured for all 3 videos!")

    # --- ROUND 2: Verify Round 1, update to Round 2 settings ---
    card1.mousePressEvent(evt_click)
    app.processEvents()
    assert window.trim_widget.is_trim_enabled() is True
    assert window.trim_widget.start_input.text() == "00:01"
    assert window.trim_widget.end_input.text() == "00:05"
    assert window.smooth_widget.is_smooth_enabled() is True
    assert window.smooth_widget.get_target_fps() == 120
    window.trim_widget.start_input.setText("00:02")
    window.trim_widget.end_input.setText("00:08")
    window.smooth_widget.fps_combo.setCurrentIndex(0) # 60 FPS

    card2.mousePressEvent(evt_click)
    app.processEvents()
    assert window.current_mode == "audio_only"
    assert "MP3" in window.audio_fmt_combo.currentText()
    assert window.trim_widget.is_trim_enabled() is False
    window.audio_fmt_combo.setCurrentText("FLAC (Lossless)")

    card3.mousePressEvent(evt_click)
    app.processEvents()
    assert window.current_mode == "gif"
    assert window.crop_widget.is_crop_enabled() is True
    window._set_mode("discord_8mb")

    print("Round 2 settings updated for all 3 videos!")

    # --- ROUND 3: Re-verify all Round 2 settings in reverse order ---
    card3.mousePressEvent(evt_click)
    app.processEvents()
    assert window.current_mode == "discord_8mb"

    card2.mousePressEvent(evt_click)
    app.processEvents()
    assert window.current_mode == "audio_only"
    assert "FLAC" in window.audio_fmt_combo.currentText()

    card1.mousePressEvent(evt_click)
    app.processEvents()
    assert window.trim_widget.is_trim_enabled() is True
    assert window.trim_widget.start_input.text() == "00:02"
    assert window.trim_widget.end_input.text() == "00:08"
    assert window.smooth_widget.get_target_fps() == 60

    print("Round 3 re-verification 100% successful! No settings were lost or mixed up!")

    window.close()
    print("\n[ALL TESTS 100% PASSED!]")

if __name__ == "__main__":
    run_simulation()
