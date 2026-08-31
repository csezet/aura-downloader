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
    # Generate 1 sec test video via ffmpeg
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
    
    video_path = create_dummy_video("sample_test.mp4")
    print(f"Created test video at: {video_path}")
    print(f"is_video_file({video_path}) -> {is_video_file(video_path)}")
    
    info = get_local_media_info(video_path)
    print(f"get_local_media_info: title={info.get('title')}, dur={info.get('duration')}")

    window = MainWindow()
    window.show()
    
    print("\n--- Testing Single File Drop ---")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(video_path)])
    
    enter_evt = QDragEnterEvent(QPoint(100, 100), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.dragEnterEvent(enter_evt)
    print(f"Enter event accepted: {enter_evt.isAccepted()}")
    
    drop_evt = QDropEvent(QPoint(100, 100), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.dropEvent(drop_evt)
    print(f"Drop event accepted: {drop_evt.isAccepted()}")
    print(f"Preview card visible: {window.preview_card.isVisible()}")
    print(f"Preview card title: '{window.preview_card.title_label.text()}'")
    print(f"Queue widget visible: {window.queue_widget.isVisible()}")

    print("\n--- Testing Multi File Drop ---")
    video_path2 = create_dummy_video("sample_test2.mp4")
    mime_multi = QMimeData()
    mime_multi.setUrls([QUrl.fromLocalFile(video_path), QUrl.fromLocalFile(video_path2)])
    
    drop_evt_multi = QDropEvent(QPoint(100, 100), Qt.CopyAction, mime_multi, Qt.LeftButton, Qt.NoModifier)
    window.dropEvent(drop_evt_multi)
    print(f"Multi drop accepted: {drop_evt_multi.isAccepted()}")
    print(f"Queue count: {window.queue_widget.count()}")
    print(f"Queue widget visible: {window.queue_widget.isVisible()}")
    print(f"Download button text: '{window.download_btn.text()}'")

if __name__ == "__main__":
    run_simulation()
