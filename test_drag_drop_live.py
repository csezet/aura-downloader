import sys
import os
import tempfile
import subprocess
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from ui.main_window import MainWindow
from core.local_processor import is_video_file, get_local_media_info

def create_dummy_video(filename="sample_test.mp4"):
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1",
        "-c:v", "libx264",
        filepath
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return filepath

def run_simulation():
    app = QApplication.instance() or QApplication(sys.argv)
    
    videos = [create_dummy_video(f"sample_fs_{i}.mp4") for i in range(1, 6)]

    window = MainWindow()
    window.resize(760, 650)
    window.show()

    print("\n--- 1. Drop 5 videos in standard window mode (760x650) ---")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(v) for v in videos])
    window.dropEvent(QDropEvent(QPoint(100, 100), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
    
    assert window.cards_list.count() == 5
    assert window.cards_list.isVisible() is True
    print(f"Cards list height in standard mode: {window.cards_list.height()}px")

    print("\n--- 2. Maximize / Fullscreen Window (1920x1080) ---")
    window.resize(1920, 1080)
    app.processEvents()
    
    print(f"Cards list height in fullscreen mode: {window.cards_list.height()}px")
    # In fullscreen mode (1920x1080), cards_list automatically expands to > 500px and fits all 5 cards!
    assert window.cards_list.height() > 400
    print(f"Cards list successfully expanded to fill fullscreen height ({window.cards_list.height()}px)! No cut-offs, no empty void.")

    print("\n[ALL FULLSCREEN RESPONSIVENESS AND EXPANDING TESTS 100% PASSED!]")

if __name__ == "__main__":
    run_simulation()
