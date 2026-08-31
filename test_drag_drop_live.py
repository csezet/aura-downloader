import sys
import os
import tempfile
import subprocess
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
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
    
    v1 = create_dummy_video("sample_vid1.mp4")
    v2 = create_dummy_video("sample_vid2.mp4")
    v3 = create_dummy_video("sample_vid3.mp4")

    window = MainWindow()
    window.show()

    print("\n--- 1. Drop 1st Video (One-by-One) ---")
    mime1 = QMimeData()
    mime1.setUrls([QUrl.fromLocalFile(v1)])
    window.dragEnterEvent(QDragEnterEvent(QPoint(100, 100), Qt.CopyAction, mime1, Qt.LeftButton, Qt.NoModifier))
    assert window.drop_overlay.isVisible() is True
    window.dropEvent(QDropEvent(QPoint(100, 100), Qt.CopyAction, mime1, Qt.LeftButton, Qt.NoModifier))
    
    assert window.preview_card.isVisible() is True
    assert window.preview_card.title_label.text() == "sample_vid1.mp4"
    assert window.queue_widget.isVisible() is False
    print(f"Video 1 loaded: preview title = {window.preview_card.title_label.text()}, queue visible = {window.queue_widget.isVisible()}")

    print("\n--- 2. Drop 2nd Video (Incremental One-by-One) ---")
    mime2 = QMimeData()
    mime2.setUrls([QUrl.fromLocalFile(v2)])
    window.dropEvent(QDropEvent(QPoint(100, 100), Qt.CopyAction, mime2, Qt.LeftButton, Qt.NoModifier))
    
    assert window.preview_card.isVisible() is True
    assert window.queue_widget.isVisible() is True
    assert window.queue_widget.count() == 2
    assert window.preview_card.title_label.text() == "sample_vid2.mp4"
    print(f"Video 2 loaded: queue count = {window.queue_widget.count()}, preview title = {window.preview_card.title_label.text()}")

    print("\n--- 3. Drop 3rd Video (Incremental One-by-One) ---")
    mime3 = QMimeData()
    mime3.setUrls([QUrl.fromLocalFile(v3)])
    window.dropEvent(QDropEvent(QPoint(100, 100), Qt.CopyAction, mime3, Qt.LeftButton, Qt.NoModifier))
    
    assert window.queue_widget.count() == 3
    assert window.preview_card.title_label.text() == "sample_vid3.mp4"
    print(f"Video 3 loaded: queue count = {window.queue_widget.count()}, preview title = {window.preview_card.title_label.text()}")

    print("\n--- 4. Remove Video 3 via Close Button [X] ---")
    window._clear_loaded_video()
    assert window.queue_widget.count() == 2
    assert window.queue_widget.isVisible() is True
    print(f"After 1st delete: queue count = {window.queue_widget.count()}, preview title = {window.preview_card.title_label.text()}")

    print("\n--- 5. Remove Video 2 via Close Button [X] ---")
    window._clear_loaded_video()
    assert window.queue_widget.count() == 1
    assert window.queue_widget.isVisible() is False
    assert window.preview_card.isVisible() is True
    assert window.preview_card.title_label.text() == "sample_vid1.mp4"
    print(f"After 2nd delete: queue count = {window.queue_widget.count()}, preview title = {window.preview_card.title_label.text()}")

    print("\n--- 6. Remove Video 1 via Close Button [X] (Complete Reset) ---")
    window._clear_loaded_video()
    print(f"queue count = {window.queue_widget.count()}")
    print(f"queue isVisible = {window.queue_widget.isVisible()}")
    print(f"preview isVisible = {window.preview_card.isVisible()}")
    print(f"current_video_info = {window.current_video_info}")
    print(f"url_input = '{window.url_input.text()}'")
    assert window.queue_widget.count() == 0
    assert window.preview_card.isVisible() is False
    assert window.current_video_info is None
    assert window.url_input.text() == ""
    print("\n[ALL INCREMENTAL QUEUE AND REAL DELETION TESTS 100% PASSED!]")

if __name__ == "__main__":
    run_simulation()
