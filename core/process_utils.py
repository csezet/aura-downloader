"""Shared OS and subprocess helpers for console-free Windows execution."""
import logging
import os
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def get_startupinfo():
    if sys.platform != "win32":
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo


def open_path_in_os(path: str) -> bool:
    """Open a file or directory using the OS shell without crashing on OSError."""
    if not path or not os.path.exists(path):
        return False
    try:
        os.startfile(os.path.normpath(path))
        return True
    except (OSError, AttributeError) as exc:
        logging.getLogger("aura.ui").warning("Failed to open path %s: %s", path, exc)
        return False


def reveal_in_explorer(path: str) -> bool:
    """Reveal a file in Windows Explorer without blocking the GUI thread."""
    if not path or not os.path.exists(path):
        return False
    try:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        return True
    except OSError as exc:
        logging.getLogger("aura.ui").warning("Failed to reveal path %s: %s", path, exc)
        return False
