import os
from PySide6.QtWidgets import QSystemTrayIcon
from PySide6.QtGui import QIcon
from PySide6.QtCore import QObject
from core.process_utils import reveal_in_explorer
from core.settings import settings


class NotificationManager(QObject):
    def __init__(self, parent=None, icon_path=None):
        super().__init__(parent)
        self.parent_window = parent
        self.icon_path = icon_path
        self._last_file_path = None
        self.tray_icon = None
        self._init_tray()

    def _init_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon = QIcon(self.icon_path) if self.icon_path and os.path.exists(self.icon_path) else QIcon()
        self.tray_icon = QSystemTrayIcon(icon, self.parent_window)
        self.tray_icon.messageClicked.connect(self._on_message_clicked)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def show_download_complete(self, title: str, file_path: str = None):
        """
        Shows a native Windows toast notification via System Tray.
        Clicking the toast reveals the downloaded file in Windows Explorer.
        """
        toast_shown = False
        if settings.get("notifications_enabled", True):
            self._last_file_path = file_path
            msg_title = "Aura Downloader • Готово!"
            display_name = title or (os.path.basename(file_path) if file_path else "Видео")
            msg_text = f"Загрузка завершена:\n{display_name}"

            if self.tray_icon and self.tray_icon.isVisible():
                self.tray_icon.showMessage(
                    msg_title,
                    msg_text,
                    QSystemTrayIcon.Information,
                    5000
                )
                toast_shown = True

        # Play subtle system chime if sound notifications are enabled and Windows toast didn't already chime
        if (not toast_shown and settings.get("sound_notification", True)
                and os.environ.get("QT_QPA_PLATFORM") != "offscreen"):
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_OK)
            except Exception:
                pass

    def _on_message_clicked(self):
        if self._last_file_path and reveal_in_explorer(self._last_file_path):
            return

        if self.parent_window:
            self.parent_window.showNormal()
            self.parent_window.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger and self.parent_window:
            if self.parent_window.isMinimized() or not self.parent_window.isVisible():
                self.parent_window.showNormal()
                self.parent_window.activateWindow()
            else:
                self.parent_window.raise_()
