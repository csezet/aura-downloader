"""Run the suite without reading, writing or cleaning the user's data."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="aura_tests_") as workspace:
        root = Path(workspace).resolve()
        profile, temporary = root / "profile", root / "temp"
        profile.mkdir()
        temporary.mkdir()
        tempfile.tempdir = str(temporary)
        os.environ.update(TEMP=str(temporary), TMP=str(temporary), LOCALAPPDATA=str(profile),
                          QT_QPA_PLATFORM="offscreen")
        Path.home = classmethod(lambda cls: profile)
        from PySide6.QtWidgets import QApplication
        from core.workers import shutdown_background_tasks
        from core.temp_files import release_cache_session
        app = QApplication([])
        # Offscreen Qt on Windows does not discover the native font database.
        # Use the system UI fonts so layout checks measure real text, not boxes.
        from PySide6.QtGui import QFontDatabase, QFont
        fonts = Path(os.environ['SystemRoot']) / 'Fonts'
        for name in ('segoeui.ttf', 'segoeuib.ttf', 'consola.ttf', 'consolab.ttf'):
            QFontDatabase.addApplicationFont(str(fonts / name))
        app.setFont(QFont('Segoe UI', 10))
        try:
            suite = unittest.defaultTestLoader.discover(str(PROJECT_DIR / "tests"))
            result = unittest.TextTestRunner(verbosity=2).run(suite)
        finally:
            shutdown_background_tasks()
            release_cache_session()
            tempfile.tempdir = None
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
