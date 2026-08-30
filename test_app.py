import sys
import os

def test_imports():
    print("Testing core imports...")
    from core.settings import settings
    from core.history import history
    from core.downloader import format_bytes, format_seconds, detect_platform
    from core.media_converter import crop_video, get_video_dimensions
    from core.interpolator import is_rife_available, interpolate_video, get_video_fps
    from core.local_processor import is_video_file, get_local_media_info, LocalProcessWorker
    from assets.styles import get_stylesheet
    from ui.window_effects import apply_acrylic_effect
    from ui.crop_dialog import CropCanvas, CropDialog
    from ui.crop_widget import CropWidget
    from ui.smooth_widget import SmoothWidget
    print("Imports OK!")

def test_downloader_utils():
    from core.downloader import format_bytes, format_seconds, detect_platform
    from core.local_processor import is_video_file
    assert format_bytes(1024 * 1024 * 15) == "15.0 MB"
    assert format_seconds(125) == "02:05"
    assert detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "YouTube"
    assert detect_platform("https://www.tiktok.com/@test/video/123") == "TikTok"
    assert detect_platform("https://www.instagram.com/reel/Cx123") == "Instagram"
    assert is_video_file("C:/Videos/sample.mp4") is False  # file doesn't exist
    print("Downloader utils test passed!")

def test_crop_canvas_and_dialog():
    print("Testing Crop Canvas & Dialog calculations...")
    from PySide6.QtWidgets import QApplication
    from ui.crop_dialog import CropCanvas, CropDialog
    from PySide6.QtGui import QPixmap
    
    app = QApplication.instance() or QApplication(sys.argv)
    
    canvas = CropCanvas()
    dummy_pix = QPixmap(1920, 1080)
    canvas.set_source_image(dummy_pix, 1920, 1080)
    
    # Test 1:1 Aspect ratio
    canvas.set_aspect_ratio(1.0)
    params = canvas.get_crop_params()
    assert params['w'] == params['h']
    assert params['w'] % 2 == 0
    assert params['h'] % 2 == 0
    assert params['x'] >= 0 and params['y'] >= 0
    assert params['x'] + params['w'] <= 1920
    assert params['y'] + params['h'] <= 1080
    
    # Test 9:16 Aspect ratio
    canvas.set_aspect_ratio(9.0/16.0)
    params916 = canvas.get_crop_params()
    assert params916['w'] % 2 == 0
    assert params916['h'] % 2 == 0
    assert params916['w'] < params916['h']

    print("Crop Canvas calculations test passed!")

def test_smooth_widget():
    print("Testing SmoothWidget...")
    from PySide6.QtWidgets import QApplication
    from ui.smooth_widget import SmoothWidget

    app = QApplication.instance() or QApplication(sys.argv)
    widget = SmoothWidget()
    assert not widget.is_smooth_enabled()
    assert widget.get_target_fps() == 60
    assert widget.get_model() in ["rife", "ffmpeg"]
    print("SmoothWidget test passed!")

def test_ui_init():
    print("Testing UI initialization with Drag & Drop...")
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    
    app = QApplication.instance() or QApplication(sys.argv)
    
    icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
    window = MainWindow(icon_path=icon_path)
    assert window is not None
    assert window.acceptDrops() is True
    assert hasattr(window, "file_btn")
    assert hasattr(window, "crop_widget")
    assert hasattr(window, "smooth_widget")
    print("UI initialization passed!")

if __name__ == "__main__":
    test_imports()
    test_downloader_utils()
    test_crop_canvas_and_dialog()
    test_smooth_widget()
    test_ui_init()
    print("[ALL TESTS PASSED]")
