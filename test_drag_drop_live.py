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
    
    v1 = create_dummy_video("sample_trim_video.mp4")

    print("\n--- 1. Test TimelineRangeSlider ---")
    slider = TimelineRangeSlider()
    slider.resize(600, 54)
    slider.set_duration(30000) # 30s
    slider.set_range(5000, 20000) # 5s to 20s
    assert slider.start_ms == 5000
    assert slider.end_ms == 20000
    print("TimelineRangeSlider range initialized correctly: 00:05.0 to 00:20.0!")

    print("\n--- 2. Test TrimDialog with real video file ---")
    dialog = TrimDialog(parent=None, video_source=v1, duration_sec=3, initial_start="00:01", initial_end="00:02")
    dialog.show()
    assert dialog.timeline_slider is not None
    assert dialog.video_widget is not None
    assert dialog.player is not None

    # Simulate setting current position as start/end
    dialog._seek_to_ms(500)
    dialog._set_current_as_start()
    assert dialog.start_ms == 500

    dialog._seek_to_ms(2500)
    dialog._set_current_as_end()
    assert dialog.end_ms == 2500

    dialog._apply()
    assert dialog.applied_range == ("00:00", "00:02")
    dialog.close()
    print("TrimDialog interactive preview, range selection, and apply passed!")

    print("\n--- 3. Test MainWindow Trim Integration ---")
    window = MainWindow()
    window.resize(760, 650)
    window.show()

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(v1)])
    window.dropEvent(QDropEvent(QPoint(100, 100), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))

    assert window.cards_list.count() == 1
    # Check that TrimWidget received source video
    assert os.path.normpath(window.trim_widget._video_source) == os.path.normpath(v1)
    print(f"TrimWidget successfully connected to video source: {window.trim_widget._video_source}")

    # Toggle trim on
    window.trim_widget.toggle.setChecked(True)
    assert window.trim_widget.visual_btn.isEnabled() is True
    print("Visual trim button is enabled and ready to open interactive editor!")

    window.close()
    print("\n[ALL VISUAL TIMELINE & TRIM DIALOG TESTS 100% PASSED!]")

if __name__ == "__main__":
    run_simulation()
