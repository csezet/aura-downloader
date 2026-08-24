import sys
import os
import ctypes
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

try:
    myappid = 'aura.media.downloader.pro.v1'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

from ui.main_window import MainWindow

def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    app.setApplicationName("Aura Downloader")
    app.setOrganizationName("AuraDev")

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
