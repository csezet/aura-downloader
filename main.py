import sys
import os
import ctypes

if __name__ == "__main__" and "--smoke-test" in sys.argv:
    from core.smoke_check import smoke_main
    sys.exit(smoke_main(sys.argv[1:]))


def _hide_owned_console():
    """Detach a dedicated console only for windowless/frozen launches; never hide a parent terminal."""
    if sys.platform != "win32":
        return
    if not (getattr(sys, "frozen", False) or sys.executable.lower().endswith("pythonw.exe")):
        return
    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        hwnd = kernel32.GetConsoleWindow()
        if hwnd == 0:
            return
        pids = (ctypes.c_uint32 * 2)()
        if kernel32.GetConsoleProcessList(pids, 2) == 1:
            user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
            kernel32.FreeConsole()
    except Exception:
        pass


_hide_owned_console()

from core.app_logging import configure_logging, install_exception_hooks, install_qt_logging
from core.version import APP_VERSION

_is_windowless = sys.executable.lower().endswith("pythonw.exe") or bool(getattr(sys, "frozen", False))
log_path = configure_logging(redirect=_is_windowless)
install_exception_hooks(log_path)

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
from core.temp_files import release_cache_session
from core.workers import shutdown_background_tasks


def finalize_background_work():
    shutdown_background_tasks()
    release_cache_session()
    cleanup_aura_temp_files(max_age_hours=0)


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName("Aura Downloader")
    app.setOrganizationName("AuraDev")
    app.setApplicationVersion(APP_VERSION)
    install_qt_logging()

    # Clean up any leftover temporary proxies/thumbs
    try:
        cleanup_aura_temp_files(max_age_hours=24)
        app.aboutToQuit.connect(finalize_background_work)
    except Exception:
        pass

    base_dir = Path(__file__).resolve().parent
    icon_path = str(base_dir / "assets" / "app_logo.ico")
    if not os.path.exists(icon_path):
        icon_path = str(base_dir / "assets" / "icon.ico")

    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow(icon_path=icon_path)
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))
    window.show()
    sys._aura_window_started = True

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
