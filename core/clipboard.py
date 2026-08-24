import re
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QApplication

URL_PATTERN = re.compile(
    r'(https?://(?:www\.)?(?:youtube\.com|youtu\.be|tiktok\.com|instagram\.com|twitter\.com|x\.com|vk\.com|vkvideo\.ru|twitch\.tv|reddit\.com|pinterest\.com|vimeo\.com|facebook\.com|fb\.watch)[^\s]+)',
    re.IGNORECASE
)

class ClipboardWatcher(QObject):
    url_detected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_clipboard_text = ""
        self._enabled = True
        self._clipboard = QApplication.clipboard()
        self._clipboard.dataChanged.connect(self._on_clipboard_changed)

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def _on_clipboard_changed(self):
        if not self._enabled:
            return
        text = self._clipboard.text().strip()
        if text and text != self._last_clipboard_text:
            self._last_clipboard_text = text
            match = URL_PATTERN.search(text)
            if match:
                detected_url = match.group(1)
                self.url_detected.emit(detected_url)
