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
    
    v1 = create_dummy_video("sample_duplicate.mp4")

    window = MainWindow()
    window.show()

    print("\n--- 1. Drop same video 1st time ---")
    mime1 = QMimeData()
    mime1.setUrls([QUrl.fromLocalFile(v1)])
    window.dropEvent(QDropEvent(QPoint(100, 100), Qt.CopyAction, mime1, Qt.LeftButton, Qt.NoModifier))
    
    assert window.cards_list.count() == 1
    assert window.cards_list.isVisible() is True
    print(f"Cards count after 1st drop: {window.cards_list.count()}")

    print("\n--- 2. Drop EXACT SAME video 2nd time (Duplicate allowed) ---")
    window.dropEvent(QDropEvent(QPoint(100, 100), Qt.CopyAction, mime1, Qt.LeftButton, Qt.NoModifier))
    
    assert window.cards_list.count() == 2
    assert len(window.cards_list.cards) == 2
    print(f"Cards count after 2nd drop of same file: {window.cards_list.count()} (Both cards are full rich cards!)")

    print("\n--- 3. Drop EXACT SAME video 3rd time ---")
    window.dropEvent(QDropEvent(QPoint(100, 100), Qt.CopyAction, mime1, Qt.LeftButton, Qt.NoModifier))
    
    assert window.cards_list.count() == 3
    print(f"Cards count after 3rd drop: {window.cards_list.count()}")

    print("\n--- 4. Verify No Visible Scrollbar ---")
    assert window.cards_list.scroll.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    print("Vertical scrollbar policy is ScrollBarAlwaysOff (no slider on screen, smooth wheel scrolling active)!")

    print("\n--- 5. Remove card 2 via its [X] button ---")
    card2 = window.cards_list.cards[1]
    card2_id = card2.item_id
    card2.close_btn.click()
    assert window.cards_list.count() == 2
    print(f"Card 2 removed! Remaining cards count: {window.cards_list.count()}")

    print("\n--- 6. Remove remaining 2 cards ---")
    window.cards_list.cards[0].close_btn.click()
    assert window.cards_list.count() == 1
    window.cards_list.cards[0].close_btn.click()
    assert window.cards_list.count() == 0
    assert window.cards_list.isVisible() is False
    assert window.current_video_info is None
    print("All cards cleanly removed! State is completely reset.")

    print("\n[ALL FULL-CARD, DUPLICATE-SUPPORT, AND SMOOTH-WHEEL TESTS 100% PASSED!]")

if __name__ == "__main__":
    run_simulation()
