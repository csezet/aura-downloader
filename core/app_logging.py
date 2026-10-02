"""Rotating diagnostics for console-free launches, with URL and credential-field redaction."""
import ctypes
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
from urllib.parse import urlsplit

from core.version import APP_VERSION


def get_log_dir():
    active = next((h for h in logging.getLogger().handlers if getattr(h, "aura_handler", False)), None)
    if active is not None:
        return Path(active.baseFilename).parent
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".aura_downloader")
    return base / "AuraDownloader" / "logs"


class PrivateFormatter(logging.Formatter):
    def format(self, record):
        message = super().format(record)
        # URLs can contain signed CDN tokens or private media identifiers.
        message = re.sub(r"https?://[^\s<>\"']+", self._hide_url, message)
        return re.sub(r"(?i)\b(authorization|cookie|password|token)\s*[:=]\s*[^\r\n]+",
                      r"\1=<redacted>", message)

    @staticmethod
    def _hide_url(match):
        try:
            parsed = urlsplit(match.group())
            return f"{parsed.scheme}://{parsed.hostname}/<redacted>"
        except ValueError:
            return "<redacted URL>"


class LogStream:
    encoding = "utf-8"

    def __init__(self, level):
        self.level = level
        self.buffers = {}

    def write(self, value):
        key = threading.get_ident()
        text = self.buffers.get(key, "") + str(value)
        lines = text.split("\n")
        self.buffers[key] = lines.pop()[-8192:]
        for line in lines:
            if line.strip():
                logging.getLogger("aura.console").log(self.level, line.rstrip())
        return len(value)

    def flush(self):
        for key, value in list(self.buffers.items()):
            if value.strip():
                logging.getLogger("aura.console").log(self.level, value)
            self.buffers.pop(key, None)

    def isatty(self):
        return False


class SafeRotatingFileHandler(RotatingFileHandler):
    def handleError(self, record):
        # Disk errors must not recurse through stderr, which itself writes to this handler.
        pass


def configure_logging(redirect=False):
    root = logging.getLogger()
    handler = next((h for h in root.handlers if getattr(h, "aura_handler", False)), None)
    if handler is None:
        for folder in (get_log_dir(), Path(tempfile.gettempdir()) / "AuraDownloader" / "logs"):
            try:
                folder.mkdir(parents=True, exist_ok=True)
                handler = SafeRotatingFileHandler(folder / f"aura-{os.getpid()}.log", maxBytes=2 * 1024 * 1024,
                                              backupCount=3, encoding="utf-8")
                break
            except OSError:
                continue
        if handler is None:
            return None
        handler.aura_handler = True
        handler.setFormatter(PrivateFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    if redirect:
        sys.stdout = LogStream(logging.INFO)
        sys.stderr = LogStream(logging.ERROR)
    return Path(handler.baseFilename)


def install_exception_hooks(log_path):
    def report_exception(kind, value, traceback):
        logging.getLogger("aura").critical("Unhandled exception", exc_info=(kind, value, traceback))
        if (getattr(sys, "frozen", False) and threading.current_thread() is threading.main_thread()
                and not getattr(sys, "_aura_window_started", False)):
            ctypes.windll.user32.MessageBoxW(None, f"Не удалось запустить Aura Downloader.\nЖурнал: {log_path}",
                                            "Aura Downloader", 0x10)
    sys.excepthook = report_exception
    threading.excepthook = lambda args: report_exception(args.exc_type, args.exc_value, args.exc_traceback)


def install_qt_logging():
    from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    levels = {QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.INFO,
              QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
              QtMsgType.QtFatalMsg: logging.CRITICAL}
    qInstallMessageHandler(lambda kind, context, message: logging.getLogger("aura.qt").log(levels[kind], message))
    logging.getLogger("aura").info("Starting Aura Downloader %s (frozen=%s)", APP_VERSION, bool(getattr(sys, "frozen", False)))
