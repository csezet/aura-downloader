import sys
import os

def test_imports():
    print("Testing core imports...")
    from core.settings import settings
    from core.history import history
    from core.downloader import format_bytes, format_seconds, detect_platform
    from assets.styles import get_stylesheet
    from ui.window_effects import apply_acrylic_effect
    print("Imports OK!")

def test_downloader_utils():
    from core.downloader import format_bytes, format_seconds, detect_platform
    assert format_bytes(1024 * 1024 * 15) == "15.0 MB"
    assert format_seconds(125) == "02:05"
    assert detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "YouTube"
    assert detect_platform("https://www.tiktok.com/@test/video/123") == "TikTok"
    assert detect_platform("https://www.instagram.com/reel/Cx123") == "Instagram"
    print("Downloader utils test passed!")

def test_ui_init():
    print("Testing UI initialization...")
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
    window = MainWindow(icon_path=icon_path)
    assert window is not None
    print("UI initialization passed!")

if __name__ == "__main__":
    test_imports()
    test_downloader_utils()
    test_ui_init()
    print("[ALL TESTS PASSED]")
