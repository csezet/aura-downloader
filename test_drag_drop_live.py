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
    
    v1 = create_dummy_video("sample_s1.mp4")
    v2 = create_dummy_video("sample_s2.mp4")
    v3 = create_dummy_video("sample_s3.mp4")

    window = MainWindow()
    window.show()

    print("\n--- 1. Drop 3 videos into app ---")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(v1), QUrl.fromLocalFile(v2), QUrl.fromLocalFile(v3)])
    window.dropEvent(QDropEvent(QPoint(100, 100), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
    
    assert window.cards_list.count() == 3
    print(f"Loaded 3 cards! Selected count: {len(window.cards_list.get_selected_videos())}")
    # Only 1 card (the latest added) is selected by default
    assert len(window.cards_list.get_selected_videos()) == 1
    assert "ОБРАБОТАТЬ И СОХРАНИТЬ" in window.download_btn.text()

    print("\n--- 2. Normal Click on Card 1 ---")
    card1 = window.cards_list.cards[0]
    evt_normal = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    card1.mousePressEvent(evt_normal)
    
    assert window.cards_list.cards[0].is_selected() is True
    assert window.cards_list.cards[1].is_selected() is False
    assert window.cards_list.cards[2].is_selected() is False
    assert len(window.cards_list.get_selected_videos()) == 1
    print("Normal click on Card 1: Only Card 1 is selected!")

    print("\n--- 3. Shift + Click on Card 3 (Range Selection) ---")
    card3 = window.cards_list.cards[2]
    evt_shift = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.ShiftModifier)
    card3.mousePressEvent(evt_shift)
    
    assert window.cards_list.cards[0].is_selected() is True
    assert window.cards_list.cards[1].is_selected() is True
    assert window.cards_list.cards[2].is_selected() is True
    assert len(window.cards_list.get_selected_videos()) == 3
    assert "ОБРАБОТАТЬ ВСЕ ВИДЕО (3)" in window.download_btn.text()
    print("Shift + Click on Card 3: All 3 cards selected via range! Button updated to: 'ОБРАБОТАТЬ ВСЕ ВИДЕО (3)'")

    print("\n--- 4. Ctrl + Click on Card 2 (Deselect Card 2) ---")
    card2 = window.cards_list.cards[1]
    evt_ctrl = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.ControlModifier)
    card2.mousePressEvent(evt_ctrl)
    
    assert window.cards_list.cards[0].is_selected() is True
    assert window.cards_list.cards[1].is_selected() is False
    assert window.cards_list.cards[2].is_selected() is True
    assert len(window.cards_list.get_selected_videos()) == 2
    assert "ОБРАБОТАТЬ ВСЕ ВИДЕО (2)" in window.download_btn.text()
    print("Ctrl + Click on Card 2: Card 2 deselected, 2 cards remaining selected! Button: 'ОБРАБОТАТЬ ВСЕ ВИДЕО (2)'")

    print("\n--- 5. Verify No Checkbox and Transparent Background ---")
    assert not hasattr(card1, 'checkbox')
    assert "transparent" in window.cards_list.styleSheet()
    print("Verified: Checkboxes removed, transparent background active!")

    print("\n[ALL SELECTION, SHIFT-CLICK, AND STYLING TESTS 100% PASSED!]")

if __name__ == "__main__":
    run_simulation()
