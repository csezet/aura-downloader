import re
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

URL_PATTERN = re.compile(
    r'(https?://(?:www\.)?(?:'
    r'(?:m\.|music\.)?youtube\.com|youtu\.be|'
    r'(?:(?:m|vm|vt)\.)?tiktok\.com|'
    r'instagram\.com|instagr\.am|'
    r'twitter\.com|x\.com|'
    r'vk\.com|vkvideo\.ru|'
    r'(?:clips\.)?twitch\.tv|'
    r'reddit\.com|redd\.it|'
    r'pinterest\.com|pin\.it|'
    r'vimeo\.com|facebook\.com|fb\.watch'
    r')[^\s<>"\']+)',
    re.IGNORECASE,
)

_TRAILING_PUNCTUATION = '.,;:!?)]}>"\'»）。，！？'


def extract_supported_url(text: str):
    match = URL_PATTERN.search(str(text or ""))
    if not match:
        return None
    url = match.group(1)
    while url:
        last = url[-1]
        if last == ')' and url.count(')') <= url.count('('):
            break
        if last == ']' and url.count(']') <= url.count('['):
            break
        if last in _TRAILING_PUNCTUATION:
            url = url[:-1]
        else:
            break
    return url or None


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
            detected_url = extract_supported_url(text)
            if detected_url:
                self.url_detected.emit(detected_url)
