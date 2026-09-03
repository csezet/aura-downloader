import sys
import os
import ctypes

# Immediately hide and detach any console window if opened
try:
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    hwnd = kernel32.GetConsoleWindow()
    if hwnd != 0:
        user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
        kernel32.FreeConsole()
except Exception:
    pass

# Suppress console buffer output from native C libraries (FFmpeg timestamps / DirectShow)
if sys.executable.lower().endswith("pythonw.exe") or getattr(sys, 'frozen', False):
    try:
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')
    except Exception:
        pass

from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

# Set Windows Application ID for proper taskbar icon display
try:
    myappid = 'aura.media.downloader.pro.v1'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

from ui.main_window import MainWindow
from core.media_converter import cleanup_aura_temp_files

def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    app.setApplicationName("Aura Downloader")
    app.setOrganizationName("AuraDev")

    # Clean up any leftover temporary proxies/thumbs
    try:
        cleanup_aura_temp_files(max_age_hours=24)
        app.aboutToQuit.connect(lambda: cleanup_aura_temp_files(max_age_hours=0))
    except Exception:
        pass

    base_dir = Path(__file__).resolve().parent
    icon_path = str(base_dir / "assets" / "app_logo.ico")
    if not os.path.exists(icon_path):
        icon_path = str(base_dir / "assets" / "icon.ico")

    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow(icon_path=icon_path)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
