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

def create_dummy_video(filename="sample_test.mp4"):
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=3",
        "-c:v", "libx264",
        filepath
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return filepath

def run_simulation():
    app = QApplication.instance() or QApplication(sys.argv)
    
    v1 = create_dummy_video("sample_v1.mp4")
    v2 = create_dummy_video("sample_v2.mp4")
    v3 = create_dummy_video("sample_v3.mp4")

    print("\n--- 1. Test TrimDialog Vector SVG Icons ---")
    dialog = TrimDialog(parent=None, video_source=v1, duration_sec=3, initial_start="00:01", initial_end="00:02")
    dialog.show()
    assert not dialog.btn_play.icon().isNull()
    assert not dialog.btn_jump_start.icon().isNull()
    assert not dialog.btn_jump_end.icon().isNull()
    assert not dialog.btn_mark_start.icon().isNull()
    assert not dialog.btn_mark_end.icon().isNull()
    assert not dialog.btn_loop.icon().isNull()
    dialog.close()
    print("TrimDialog vector SVG icons 100% verified!")

    print("\n--- 2. Test Multi-Cycle Settings Switching Across 3 Videos ---")
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
    # Card 1: Trim 00:01-00:05, 120 FPS
    card1.mousePressEvent(evt_click)
    app.processEvents()
    window.trim_widget.toggle.setChecked(True)
    window.trim_widget.start_input.setText("00:01")
    window.trim_widget.end_input.setText("00:05")
    window.smooth_widget.toggle.setChecked(True)
    window.smooth_widget.fps_combo.setCurrentIndex(1) # 120 FPS

    # Card 2: Audio Only MP3
    card2.mousePressEvent(evt_click)
    app.processEvents()
    window._set_mode("audio_only")
    window.audio_fmt_combo.setCurrentText("MP3 (320 kbps)")
    window.trim_widget.toggle.setChecked(False)
    window.smooth_widget.toggle.setChecked(False)

    # Card 3: GIF mode, Crop 1:1
    card3.mousePressEvent(evt_click)
    app.processEvents()
    window._set_mode("gif")
    window.crop_widget.toggle.setChecked(True)
    window.crop_widget._crop_params = {'x': 10, 'y': 10, 'w': 200, 'h': 200}
    window._auto_save_active_options()

    print("Round 1 settings configured for all 3 videos!")

    # --- ROUND 2: Verify Round 1, update to Round 2 settings ---
    # Switch to Card 1 -> Verify Round 1 -> Update to Round 2
    card1.mousePressEvent(evt_click)
    app.processEvents()
    assert window.trim_widget.is_trim_enabled() is True
    assert window.trim_widget.start_input.text() == "00:01"
    assert window.trim_widget.end_input.text() == "00:05"
    assert window.smooth_widget.is_smooth_enabled() is True
    assert window.smooth_widget.get_target_fps() == 120
    # Update Card 1 to Round 2: Trim 00:02-00:08, Smooth 60 FPS
    window.trim_widget.start_input.setText("00:02")
    window.trim_widget.end_input.setText("00:08")
    window.smooth_widget.fps_combo.setCurrentIndex(0) # 60 FPS

    # Switch to Card 2 -> Verify Round 1 -> Update to Round 2
    card2.mousePressEvent(evt_click)
    app.processEvents()
    assert window.current_mode == "audio_only"
    assert "MP3" in window.audio_fmt_combo.currentText()
    assert window.trim_widget.is_trim_enabled() is False
    # Update Card 2 to Round 2: FLAC
    window.audio_fmt_combo.setCurrentText("FLAC (Lossless)")

    # Switch to Card 3 -> Verify Round 1 -> Update to Round 2
    card3.mousePressEvent(evt_click)
    app.processEvents()
    assert window.current_mode == "gif"
    assert window.crop_widget.is_crop_enabled() is True
    # Update Card 3 to Round 2: Discord 8MB mode
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
    print("\n[ALL MULTI-VIDEO SETTINGS AND UI STYLE TESTS 100% PASSED!]")

if __name__ == "__main__":
    run_simulation()
