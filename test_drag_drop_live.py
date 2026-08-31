import sys
import os
import tempfile
import subprocess
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
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
    
    v1 = create_dummy_video("sample_v1.mp4")
    v2 = create_dummy_video("sample_v2.mp4")
    v3 = create_dummy_video("sample_v3.mp4")

    window = MainWindow()
    window.show()

    print("\n--- 1. Testing Single File Drop ---")
    mime1 = QMimeData()
    mime1.setUrls([QUrl.fromLocalFile(v1)])
    
    enter_evt = QDragEnterEvent(QPoint(100, 100), Qt.CopyAction, mime1, Qt.LeftButton, Qt.NoModifier)
    window.dragEnterEvent(enter_evt)
    assert window.drop_overlay.isVisible() is True
    print(f"Drop overlay visible during drag: {window.drop_overlay.isVisible()}")

    drop_evt1 = QDropEvent(QPoint(100, 100), Qt.CopyAction, mime1, Qt.LeftButton, Qt.NoModifier)
    window.dropEvent(drop_evt1)
    assert window.drop_overlay.isVisible() is False
    assert window.preview_card.isVisible() is True
    print(f"Single drop - Preview visible: {window.preview_card.isVisible()}, Queue visible: {window.queue_widget.isVisible()}")

    print("\n--- 2. Testing Multi File Drop (3 videos) ---")
    mime_multi = QMimeData()
    mime_multi.setUrls([QUrl.fromLocalFile(v1), QUrl.fromLocalFile(v2), QUrl.fromLocalFile(v3)])
    
    enter_evt_m = QDragEnterEvent(QPoint(100, 100), Qt.CopyAction, mime_multi, Qt.LeftButton, Qt.NoModifier)
    window.dragEnterEvent(enter_evt_m)
    assert window.drop_overlay.isVisible() is True

    drop_evt_m = QDropEvent(QPoint(100, 100), Qt.CopyAction, mime_multi, Qt.LeftButton, Qt.NoModifier)
    window.dropEvent(drop_evt_m)
    assert window.drop_overlay.isVisible() is False
    assert window.preview_card.isVisible() is True
    assert window.queue_widget.isVisible() is True
    assert window.queue_widget.count() == 3
    print(f"Multi drop - Queue count: {window.queue_widget.count()}, Active: {window.queue_widget.active_url}")

    print("\n--- 3. Testing Interactive Click Selection in Queue ---")
    # Click 2nd item in queue
    item2 = window.queue_widget.item_widgets[1]
    item2.selected_for_preview.emit(item2.data)
    assert os.path.normpath(window.current_video_info['url']) == os.path.normpath(v2)
    assert window.preview_card.title_label.text() == "sample_v2.mp4"
    print(f"Item 2 selected! Active preview title: {window.preview_card.title_label.text()}")

    print("\n[ALL DRAG & DROP & QUEUE TESTS VERIFIED 100% SUCCESS!]")

if __name__ == "__main__":
    run_simulation()
