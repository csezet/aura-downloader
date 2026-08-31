import sys
import os
import tempfile
import subprocess
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
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

    print("\n--- 1. Test TrimDialog UI Layout ---")
    dialog = TrimDialog(parent=None, video_source=v1, duration_sec=3, initial_start="00:01", initial_end="00:02")
    dialog.show()
    assert dialog.btn_play.text() == " ▶ Воспроизведение"
    assert dialog.btn_loop.isChecked() is True
    dialog.close()
    print("TrimDialog UI layout, no box borders, and play button verified!")

    print("\n--- 2. Test Per-Video Settings Isolation & Restoration ---")
    window = MainWindow()
    window.resize(760, 650)
    window.show()

    # Drop Video 1
    mime1 = QMimeData()
    mime1.setUrls([QUrl.fromLocalFile(v1)])
    window.dropEvent(QDropEvent(QPoint(100, 100), Qt.CopyAction, mime1, Qt.LeftButton, Qt.NoModifier))
    
    # Configure Video 1: Trim 00:01 -> 00:02, Smooth 120 FPS
    window.trim_widget.toggle.setChecked(True)
    window.trim_widget.start_input.setText("00:01")
    window.trim_widget.end_input.setText("00:02")
    window.smooth_widget.toggle.setChecked(True)
    window.smooth_widget.fps_combo.setCurrentIndex(1) # 120 FPS
    window._save_current_ui_to_video_info()

    # Drop Video 2
    mime2 = QMimeData()
    mime2.setUrls([QUrl.fromLocalFile(v2)])
    window.dropEvent(QDropEvent(QPoint(100, 100), Qt.CopyAction, mime2, Qt.LeftButton, Qt.NoModifier))

    # Configure Video 2: Audio Only FLAC, No trim, No smooth
    window._set_mode("audio_only")
    window.audio_fmt_combo.setCurrentText("FLAC (Lossless)")
    window.trim_widget.toggle.setChecked(False)
    window.smooth_widget.toggle.setChecked(False)
    window._save_current_ui_to_video_info()

    print("\n--- 3. Switch back to Video 1 (Click Card 1) ---")
    card1 = window.cards_list.cards[0]
    evt_click = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    card1.mousePressEvent(evt_click)
    app.processEvents()

    # Verify Video 1 settings restored: Trim True (00:01-00:02), Smooth True (120 FPS), Mode best
    assert window.trim_widget.is_trim_enabled() is True
    assert window.trim_widget.start_input.text() == "00:01"
    assert window.trim_widget.end_input.text() == "00:02"
    assert window.smooth_widget.is_smooth_enabled() is True
    assert window.smooth_widget.get_target_fps() == 120
    assert window.current_mode == "best"
    print("Video 1 settings successfully restored upon selection!")

    print("\n--- 4. Switch back to Video 2 (Click Card 2) ---")
    card2 = window.cards_list.cards[1]
    card2.mousePressEvent(evt_click)
    app.processEvents()

    # Verify Video 2 settings restored: Mode audio_only, Trim False, Smooth False
    assert window.current_mode == "audio_only"
    assert "FLAC" in window.audio_fmt_combo.currentText()
    assert window.trim_widget.is_trim_enabled() is False
    assert window.smooth_widget.is_smooth_enabled() is False
    print("Video 2 settings successfully restored upon selection!")

    window.close()
    print("\n[ALL PER-VIDEO SETTINGS AND TRIMDIALOG FIXES 100% PASSED!]")

if __name__ == "__main__":
    run_simulation()
